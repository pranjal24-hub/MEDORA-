"""Accident report -> hospitals notify -> paramedic report -> ranking -> atomic reservation."""
import json
import os
import threading
import time
from typing import Literal, Optional
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from app.db import query, tx
from app.auth import current_user
from app.geo import haversine_km, eta_min
from app import hub, push
from app.ml import severity as ml_severity
from app.ml_api import bed_forecast_for
from app.dispatch import dispatcher

router = APIRouter()
RESOURCES = ("ER_BED", "ICU_BED", "VENTILATOR", "OT")
RINGS_KM = (20, 40, 60, 80, 100)   # pehle 20 km ke SAARE hospitals (koi count limit nahi), jagah na mile to 40, 60...
STALE_MIN = 45                     # hospital ne itne min se resource confirm nahi kiye -> score +3
LIVE_FRESH_S = 60                  # itne second tak ambulance ki live GPS location ko sach maano
SEV = {"CRITICAL": 0, "MODERATE": 1, "LOW": 2}
PREEMPT_GAIN = float(os.environ.get("PREEMPT_GAIN_MIN", "6"))   # free hospital itna (min) kharab ho tabhi kisi ki booking cheeno
PROTECT_ETA_MIN = 2.0       # jo ambulance hospital se 2 min ke andar hai uski booking nahi cheeni
MAX_PREEMPTS = 2            # ek patient ki booking zyada se zyada 2 baar cheeni ja sakti hai (starvation se bachav)
INBOUND_PENALTY = 1.0       # is hospital ki taraf pehle se aa rahi har ambulance ke liye score +1 (max +4)
PROV_REFRESH_S = 120        # scene tak jaate hue provisional ranking har 2 min taaza
ASSUME_S = float(os.environ.get("ASSUME_REPORT_S", "90"))   # scene par pahunch kar itne second report nahi aayi to default report


def optional_user(authorization: str = Header(default="")):
    return current_user(authorization) if authorization.startswith("Bearer ") else None


def need_ambulance(user=Depends(current_user)):
    if user["role"] != "ambulance":
        raise HTTPException(403, "Ambulance login required")
    return user


class NewIncident(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    location_text: Optional[str] = None      # bola hua address (voice transcript)


class Assessment(BaseModel):
    severity: Literal["CRITICAL", "MODERATE", "LOW"]
    patients: int = Field(default=1, ge=1, le=20)
    icu: bool = False
    ventilator: bool = False
    surgery: bool = False                     # OT chahiye
    specialties: list[str] = []              # e.g. ["Neurosurgery", "Orthopaedics"]
    report: dict = {}                         # age, mechanism, gcs, spo2, bp, hr, notes (ATMIST)


class ReserveBody(BaseModel):
    hospital_id: Optional[int] = None         # None = sabse achha hospital khud chuno


class Unavailable(Exception):
    pass


# ---------- 1. Accident report ----------
@router.post("/incidents")
def create_incident(body: NewIncident, user=Depends(optional_user)):
    """MEDORA interface (login ke bina) ya ambulance ki voice entry (login ke saath)."""
    if user and user["role"] == "hospital":
        raise HTTPException(403, "Hospital accident report nahi kar sakta")
    with tx() as cur:
        if user:                                   # ambulance voice: yahi ambulance jayegi
            cur.execute("SELECT id, lat, lon, status FROM ambulances WHERE id=%s FOR UPDATE", (user["ambulance_id"],))
            amb = cur.fetchone()
            if amb["status"] != "AVAILABLE":
                raise HTTPException(409, "Ambulance pehle se kisi case par hai")
            source = "AMBULANCE_VOICE"
        else:                                      # MEDORA: sabse nazdeeki khali ambulance
            cur.execute("SELECT id, lat, lon, code FROM ambulances WHERE status='AVAILABLE' FOR UPDATE SKIP LOCKED")
            cands = cur.fetchall()
            if not cands:
                raise HTTPException(503, "Koi ambulance khali nahi")
            for c in cands:                                # abhi ki asli (live) jagah, DB ki purani nahi
                lv = hub.live.get(c["id"])
                if lv and time.time() - lv["ts"] < LIVE_FRESH_S:
                    c["lat"], c["lon"] = lv["lat"], lv["lon"]
            amb = min(cands, key=lambda a: haversine_km(a["lat"], a["lon"], body.lat, body.lon))
            source = "MEDORA"
        to_scene = eta_min(haversine_km(amb["lat"], amb["lon"], body.lat, body.lon))
        cur.execute(
            "INSERT INTO incidents (source, location_text, lat, lon, ambulance_id, eta_to_scene_min) "
            "VALUES (%s,%s,%s,%s,%s,%s) RETURNING id",
            (source, body.location_text, body.lat, body.lon, amb["id"], to_scene))
        iid = cur.fetchone()["id"]
        cur.execute("UPDATE ambulances SET status='DISPATCHED' WHERE id=%s", (amb["id"],))
        near = _notify_rings(cur, iid, body.lat, body.lon, first_only=True)
    hub.forget(amb["id"])
    push.alert(near, iid)
    push.refresh_hospitals(near)
    hub.emit(hub.ambulance(amb["id"]), {"type": "refresh"})
    return {"incident_id": iid, "source": source, "ambulance_id": amb["id"],
            "eta_to_scene_min": to_scene, "hospitals_notified": len(near),
            "ambulance_code": amb.get("code")}


# ---------- 2. Ranking (paramedic report + hospital situation + ETA) ----------
def required(a: Assessment) -> dict:
    need = {"ER_BED": a.patients}
    if a.icu:
        need["ICU_BED"] = a.patients
    if a.ventilator:
        need["VENTILATOR"] = a.patients
    if a.surgery:
        need["OT"] = 1
    return need


def rank_hospitals(incident_id: int, need: dict, severity: str, specialties: list[str], include_full=False, provisional=False):
    rows = query(
        "SELECT ih.hospital_id, h.name, h.city, h.lat, h.lon, h.trauma_centre, h.emergency_24x7, "
        "ih.distance_km, ih.eta_hospital_min, s.load, EXTRACT(EPOCH FROM (now()-s.confirmed_at))/60 AS conf_age, "
        "(SELECT json_object_agg(resource_type, available) FROM hospital_resources r WHERE r.hospital_id=h.id) AS avail, "
        "(SELECT COALESCE(array_agg(service), '{}') FROM hospital_services v WHERE v.hospital_id=h.id) AS services, "
        "(SELECT count(*) FROM reservations x WHERE x.hospital_id=h.id AND x.status='BOOKED' AND x.incident_id<>ih.incident_id) AS inbound "
        "FROM incident_hospitals ih JOIN hospitals h ON h.id=ih.hospital_id "
        "JOIN hospital_status s ON s.hospital_id=h.id "
        "WHERE ih.incident_id=%s AND ih.status='NOTIFIED' AND s.diverting=FALSE", (incident_id,))
    out = []
    for r in rows:
        avail = r["avail"] or {}
        short = any(avail.get(k, 0) < q for k, q in need.items())
        if short and not include_full:
            continue                                              # zaroori resource nahi hai
        score = r["eta_hospital_min"]
        why = [f"ETA {r['eta_hospital_min']} min"]
        score += {"NORMAL": 0, "BUSY": 4, "OVERLOADED": 10}[r["load"]]
        if r["load"] != "NORMAL":
            why.append(f"hospital {r['load'].lower()}")
        if r["conf_age"] is None or r["conf_age"] > STALE_MIN:
            score += 3
            why.append("beds not updated recently")
        if r["emergency_24x7"] is None:
            score += 3
            why.append("emergency unverified")
        if r["inbound"]:
            score += min(INBOUND_PENALTY * r["inbound"], 4)
            why.append(f"{r['inbound']} ambulance(s) already coming")
        if provisional:                                           # zaroorat abhi pata nahi: ICU/vent/OT jitna khali, utna behtar
            cap = 0.5 * min(avail.get("ICU_BED", 0), 3) + 0.5 * min(avail.get("VENTILATOR", 0), 2) + (1.0 if avail.get("OT", 0) > 0 else 0)
            score -= cap
            if cap:
                why.append("ICU / ventilator / OT available")
        if severity == "CRITICAL" and r["trauma_centre"]:
            score -= 2
            why.append("trauma centre")
        hit = [sp for sp in specialties if any(sp.lower() in sv.lower() for sv in r["services"])]
        score -= 2 * len(hit)
        if hit:
            why.append("specialty: " + ", ".join(hit))
        out.append({"hospital_id": r["hospital_id"], "name": r["name"], "city": r["city"], "lat": r["lat"],
                    "lon": r["lon"], "distance_km": r["distance_km"], "eta_min": r["eta_hospital_min"],
                    "score": round(score, 1), "why": why, "short": short})
    out.sort(key=lambda x: (x["score"], x["eta_min"], x["hospital_id"]))      # barabar score mein: kam ETA, phir fixed order
    return out


def provisional(incident_id: int, limit: int = 5) -> list:
    """Paramedic ki report se PEHLE ka andaaza: sirf resource + doori + load. Booking isse nahi hoti, sirf taiyari ke liye."""
    return rank_hospitals(incident_id, {"ER_BED": 1}, "MODERATE", [], provisional=True)[:limit]


def _soon(incident_id: int, need: dict, severity: str, specialties: list, limit: int = 3) -> list:
    """Jab abhi kisi hospital mein sab kuch nahi hai: kaunsa hospital jaldi khali hoga (ML bed forecast, sirf jaankari)."""
    out = []
    for o in rank_hospitals(incident_id, need, severity, specialties, include_full=True):
        if not o["short"]:
            continue
        fc, wait = bed_forecast_for(o["hospital_id"]), 0
        for k, q in need.items():
            f = fc.get(k)
            if not f or (f["free_now"] and f["available"] >= q):
                continue
            if f["p50_min"] is None:
                wait = None
                break
            wait = max(wait, f["p50_min"])
        if wait is None:
            continue
        o["free_in_min"], o["wait_after_arrival_min"] = wait, max(0, round(wait - o["eta_min"]))
        out.append(o)
    out.sort(key=lambda o: (o["wait_after_arrival_min"], o["eta_min"]))
    return out[:limit]


@router.post("/incidents/{incident_id}/assessment")
def assess(incident_id: int, a: Assessment, user=Depends(need_ambulance)):
    need = required(a)
    adv = ml_severity.predict(a.report)                       # sirf sujhav; final severity paramedic ki hai
    a.report["ml"] = {"suggested": adv["suggested"], "final": a.severity, "overridden": adv["suggested"] != a.severity,
                      "source": adv["source"], "fields_known": adv["fields_known"]}   # baad mein model sudharne ke kaam aayega
    with tx() as cur:
        cur.execute("SELECT ambulance_id, status FROM incidents WHERE id=%s FOR UPDATE", (incident_id,))
        inc = cur.fetchone()
        if not inc or inc["ambulance_id"] != user["ambulance_id"]:
            raise HTTPException(404, "Incident nahi mila")
        if inc["status"] not in ("REPORTED", "ASSESSED"):
            raise HTTPException(409, f"Incident {inc['status']} hai")
        cur.execute("UPDATE incidents SET severity=%s, patients=%s, needs=%s, specialties=%s, report=%s, "
                    "status='ASSESSED', assessed_at=now() WHERE id=%s",
                    (a.severity, a.patients, json.dumps(need), a.specialties, json.dumps(a.report), incident_id))
    ranked = rank_hospitals(incident_id, need, a.severity, a.specialties)
    push.refresh_incident(incident_id, also_ambulance=False)        # hospitals ko severity/needs turant dikhao
    soon = [] if ranked else _soon(incident_id, need, a.severity, a.specialties)
    return {"needs": need, "options": ranked[:5], "advisory": adv, "soon": soon}


@router.post("/incidents/{incident_id}/details")
def add_details(incident_id: int, a: Assessment, user=Depends(need_ambulance)):
    """Bed book hone ke BAAD baaki details: report, patients, needs. Naye needs usi hospital mein jodne ki koshish
    (sab ya kuch nahi); jo nahi jud sake wo `unmet` mein wapas aate hain (paramedic hospital ko call kare)."""
    want = required(a)
    adv = ml_severity.predict(a.report)
    a.report["ml"] = {"suggested": adv["suggested"], "final": a.severity, "overridden": adv["suggested"] != a.severity,
                      "source": adv["source"], "fields_known": adv["fields_known"]}
    unmet = []
    with tx() as cur:
        cur.execute("SELECT ambulance_id, status FROM incidents WHERE id=%s FOR UPDATE", (incident_id,))
        inc = cur.fetchone()
        if not inc or inc["ambulance_id"] != user["ambulance_id"]:
            raise HTTPException(404, "Incident nahi mila")
        if inc["status"] != "RESERVED":
            raise HTTPException(409, f"Incident {inc['status']} hai")
        cur.execute("SELECT id, hospital_id, items, status FROM reservations WHERE incident_id=%s "
                    "AND status='BOOKED' FOR UPDATE", (incident_id,))
        res = cur.fetchone()
        items = dict(res["items"]) if res else {}
        if res:
            delta = {k: want.get(k, 0) - items.get(k, 0) for k in set(want) | set(items)}
            cur.execute("SELECT resource_type, available FROM hospital_resources WHERE hospital_id=%s "
                        "AND resource_type = ANY(%s) ORDER BY resource_type FOR UPDATE", (res["hospital_id"], list(delta)))
            have = {r["resource_type"]: r["available"] for r in cur.fetchall()}
            unmet = sorted(k for k, d in delta.items() if d > 0 and have.get(k, 0) < d)
            if not unmet:                                              # sab jud sakta hai: badlav lagao
                for k, d in sorted(delta.items()):
                    if d:
                        cur.execute("UPDATE hospital_resources SET booked=booked+%s, available=available-%s, updated_at=now() "
                                    "WHERE hospital_id=%s AND resource_type=%s", (d, d, res["hospital_id"], k))
                items = {k: q for k, q in want.items() if q}
                cur.execute("UPDATE reservations SET items=%s WHERE id=%s", (json.dumps(items), res["id"]))
        cur.execute("UPDATE incidents SET severity=%s, patients=%s, specialties=%s, report=%s"
                    + ("" if unmet else ", needs=%s") + " WHERE id=%s",
                    (a.severity, a.patients, a.specialties, json.dumps(a.report))
                    + (() if unmet else (json.dumps(items),)) + (incident_id,))
    push.refresh_incident(incident_id)
    return {"needs": items, "unmet": unmet, "advisory": adv}


# ---------- 3. Atomic reservation (priority + preemption) ----------
def _victims(cur, hospital_id: int, my_rank: int, my_incident: int):
    """Is hospital ki wo BOOKED reservations jo meri se kam zaroori hain aur cheeni ja sakti hain.
    Order: sabse kam zaroori pehle, unmein jo hospital se sabse door (zyada ETA bachi) wo pehle."""
    cur.execute("SELECT r.id AS rid, r.items, i.id AS iid, i.severity, i.preempt_count, i.ambulance_id "
                "FROM reservations r JOIN incidents i ON i.id=r.incident_id "
                "WHERE r.hospital_id=%s AND r.status='BOOKED' AND i.id<>%s", (hospital_id, my_incident))
    out = []
    for r in cur.fetchall():
        if SEV.get(r["severity"], 1) <= my_rank or r["preempt_count"] >= MAX_PREEMPTS:
            continue
        eta = (hub.live.get(r["ambulance_id"]) or {}).get("eta")
        if eta is not None and eta < PROTECT_ETA_MIN:
            continue                                                  # lagbhag pahunch gayi: mat chhedo
        r["eta_left"] = eta if eta is not None else 99.0
        out.append(r)
    out.sort(key=lambda r: (-SEV.get(r["severity"], 1), -r["eta_left"], r["rid"]))
    return out


def _pick(have: dict, need: dict, cands: list):
    """Sabse kam victims jinke items chheen kar need poori ho. None = mumkin nahi."""
    got, chosen = dict(have), []
    short = lambda g: any(g.get(k, 0) < q for k, q in need.items())
    for c in cands:
        if not short(got):
            break
        chosen.append(c)
        for k, q in c["items"].items():
            got[k] = got.get(k, 0) + q
    if short(got):
        return None
    for c in list(reversed(chosen)):                                  # faltu victim wapas hata do
        t = dict(got)
        for k, q in c["items"].items():
            t[k] = t.get(k, 0) - q
        if not short(t):
            got, chosen = t, [x for x in chosen if x is not c]
    return chosen


def preempt_possible(incident_id: int, hospital_id: int, need: dict, severity: str) -> bool:
    """Sirf padhta hai (lock nahi): kya is hospital mein kisi kam zaroori ki booking cheen kar jagah ban sakti hai?"""
    with tx() as cur:
        cur.execute("SELECT resource_type, available FROM hospital_resources WHERE hospital_id=%s", (hospital_id,))
        have = {r["resource_type"]: r["available"] for r in cur.fetchall()}
        return _pick(have, need, _victims(cur, hospital_id, SEV.get(severity, 1), incident_id)) is not None


def try_reserve(incident_id: int, hospital_id: int, allow_preempt: bool = False) -> dict:
    """Ek transaction: incident lock -> (victims lock) -> hospital ke resource rows lock (fixed order) -> check -> book.
    Do ambulances ek saath aakhri bed maangein to ek hi jeetegi, doosri ko Unavailable milta hai."""
    with tx() as cur:
        cur.execute("SELECT status, needs, severity FROM incidents WHERE id=%s FOR UPDATE", (incident_id,))   # incident lock
        inc = cur.fetchone()
        if inc["status"] == "RESERVED":                                   # double tap: wahi reservation lauta do
            cur.execute("SELECT id, hospital_id, items FROM reservations WHERE incident_id=%s "
                        "AND status IN ('BOOKED','ADMITTED')", (incident_id,))
            r = cur.fetchone()
            return {"reservation_id": r["id"], "hospital_id": r["hospital_id"], "items": r["items"],
                    "repeat": True, "preempted": []}
        if inc["status"] != "ASSESSED":
            raise HTTPException(409, "Pehle assessment bhejo")
        need = inc["needs"]
        cur.execute("SELECT diverting FROM hospital_status WHERE hospital_id=%s FOR SHARE", (hospital_id,))
        st = cur.fetchone()
        if not st or st["diverting"]:
            raise Unavailable("hospital diverting")

        victims = []
        if allow_preempt:
            cur.execute("SELECT resource_type, available FROM hospital_resources WHERE hospital_id=%s", (hospital_id,))
            peek = {r["resource_type"]: r["available"] for r in cur.fetchall()}
            if any(peek.get(k, 0) < q for k, q in need.items()):
                # lock order: victim incidents -> victim reservations -> resources (cancel/admit se match)
                guess = _victims(cur, hospital_id, SEV.get(inc["severity"], 1), incident_id)
                if guess:
                    cur.execute("SELECT id FROM incidents WHERE id = ANY(%s) ORDER BY id FOR UPDATE", ([g["iid"] for g in guess],))
                    cur.execute("SELECT id FROM reservations WHERE id = ANY(%s) ORDER BY id FOR UPDATE", ([g["rid"] for g in guess],))
                    victims = _victims(cur, hospital_id, SEV.get(inc["severity"], 1), incident_id)   # locks ke baad dobara

        cur.execute("SELECT resource_type, available FROM hospital_resources "
                    "WHERE hospital_id=%s AND resource_type = ANY(%s) ORDER BY resource_type FOR UPDATE",
                    (hospital_id, list(need.keys())))
        have = {r["resource_type"]: r["available"] for r in cur.fetchall()}
        chosen = []
        if any(have.get(k, 0) < q for k, q in need.items()):
            chosen = _pick(have, need, victims) if victims else None
            if not chosen:
                raise Unavailable("resource khatam")
            for v in chosen:                                              # victim ki booking wapas
                for k, q in sorted(v["items"].items()):
                    cur.execute("UPDATE hospital_resources SET booked=booked-%s, available=available+%s, updated_at=now() "
                                "WHERE hospital_id=%s AND resource_type=%s", (q, q, hospital_id, k))
                cur.execute("UPDATE reservations SET status='PREEMPTED', released_at=now(), preempted_by=%s WHERE id=%s",
                            (incident_id, v["rid"]))
                cur.execute("UPDATE incidents SET status='ASSESSED', reserved_hospital_id=NULL, "
                            "preempt_count=preempt_count+1 WHERE id=%s", (v["iid"],))
                cur.execute("UPDATE incident_hospitals SET status='NOTIFIED' WHERE incident_id=%s", (v["iid"],))
        for k, q in need.items():
            cur.execute("UPDATE hospital_resources SET available=available-%s, booked=booked+%s, updated_at=now() "
                        "WHERE hospital_id=%s AND resource_type=%s", (q, q, hospital_id, k))
        cur.execute("INSERT INTO reservations (incident_id, hospital_id, items) VALUES (%s,%s,%s) RETURNING id",
                    (incident_id, hospital_id, json.dumps(need)))
        rid = cur.fetchone()["id"]
        cur.execute("UPDATE incidents SET status='RESERVED', reserved_hospital_id=%s WHERE id=%s", (hospital_id, incident_id))
        cur.execute("UPDATE incident_hospitals SET status = CASE WHEN hospital_id=%s THEN 'RESERVED' ELSE 'STOOD_DOWN' END "
                    "WHERE incident_id=%s", (hospital_id, incident_id))
        cur.execute("UPDATE ambulances SET status='TRANSPORTING' WHERE id = (SELECT ambulance_id FROM incidents WHERE id=%s)",
                    (incident_id,))
        return {"reservation_id": rid, "hospital_id": hospital_id, "items": need, "repeat": False,
                "preempted": [{"incident_id": v["iid"], "ambulance_id": v["ambulance_id"]} for v in chosen]}


def _notify_rings(cur, incident_id: int, lat: float, lon: float, first_only: bool = False) -> list:
    """Ring by ring notify: 20 km, phir 40, 60 ... Jis ring mein koi NAYA hospital mile wahin ruk jao (first_only
    ho ya widen), taaki door ke hospitals ko tabhi bulaya jaye jab paas wale kaam na aayein. Koi count limit nahi."""
    cur.execute("SELECT h.id, h.lat, h.lon FROM hospitals h LEFT JOIN hospital_status s ON s.hospital_id=h.id "
                "WHERE h.emergency_24x7 IS NOT FALSE AND COALESCE(s.diverting, FALSE)=FALSE AND h.id NOT IN "
                "(SELECT hospital_id FROM incident_hospitals WHERE incident_id=%s)", (incident_id,))
    dist = sorted((haversine_km(lat, lon, h["lat"], h["lon"]), h["id"]) for h in cur.fetchall())
    for ring in RINGS_KM:
        got = [d for d in dist if d[0] <= ring]
        if got:
            for km, hid in got:
                cur.execute("INSERT INTO incident_hospitals (incident_id, hospital_id, distance_km, eta_hospital_min) "
                            "VALUES (%s,%s,%s,%s)", (incident_id, hid, round(km, 2), eta_min(km)))
            return [hid for _, hid in got]
    return []


def widen(incident_id: int, lat: float, lon: float) -> list:
    """Notified hospitals ke paas jagah nahi bachi: agli ring (20 -> 40 -> 60 ... 100 km) ke hospitals notify karo."""
    with tx() as cur:
        return _notify_rings(cur, incident_id, lat, lon)


def hospital_card(hid: int) -> dict:
    return query("SELECT id, name, lat, lon, emergency_phone, phone FROM hospitals WHERE id=%s", (hid,))[0]


def auto_reserve(incident_id: int, allow_preempt: bool = True) -> dict:
    """Best hospital chuno. Khali hospital pehle; kisi kam zaroori ki booking tabhi cheenni jab uska fayda
    PREEMPT_GAIN minute se zyada ho (ya koi khali hospital hi na ho). Sab khatam to agli ring (20 -> 40 -> ... km)."""
    inc = query("SELECT severity, needs, specialties, lat, lon FROM incidents WHERE id=%s", (incident_id,))[0]
    sev = inc["severity"] or "MODERATE"
    tried, widened = set(), False
    while True:
        ranked = [o for o in rank_hospitals(incident_id, inc["needs"], sev, inc["specialties"], include_full=allow_preempt)
                  if o["hospital_id"] not in tried]
        free = [o for o in ranked if not o["short"]]
        full = [o for o in ranked if o["short"]
                and preempt_possible(incident_id, o["hospital_id"], inc["needs"], sev)] if allow_preempt else []
        best_free = free[0] if free else None
        best_full = full[0] if full else None
        if best_full and (not best_free or best_free["score"] - best_full["score"] >= PREEMPT_GAIN):
            cand, pre = best_full, True
        elif best_free:
            cand, pre = best_free, False
        else:
            more = widen(incident_id, inc["lat"], inc["lon"])           # agli ring; khatam hone tak baar-baar
            if not more:
                raise HTTPException(409, "Kisi hospital mein abhi resource nahi hai")
            widened = True
            push.alert(more, incident_id)
            push.refresh_hospitals(more)
            continue
        try:
            res = try_reserve(incident_id, cand["hospital_id"], allow_preempt=pre)
        except Unavailable:
            tried.add(cand["hospital_id"])                    # kisi aur ambulance ne abhi le liya
            continue
        res["tried"], res["widened"], res["preempting"] = list(tried), widened, pre
        return res


def _after_reserve(incident_id: int, res: dict):
    """Preempt hue patients ko turant naya hospital do, phir sabko WebSocket se batao."""
    amb = query("SELECT ambulance_id FROM incidents WHERE id=%s", (incident_id,))[0]["ambulance_id"]
    hub.forget(amb)
    touched = {res["hospital_id"]}
    for v in res.get("preempted", []):
        vid, vamb = v["incident_id"], v["ambulance_id"]
        hub.forget(vamb)
        try:
            new = auto_reserve(vid, allow_preempt=False)         # victim aage kisi ki booking nahi cheenta (chain nahi)
            v["new_hospital_id"] = new["hospital_id"]
            touched.add(new["hospital_id"])
            name = hospital_card(new["hospital_id"])["name"]
            push.notice(vamb, f"Your bed went to a more critical patient. New hospital: {name}", "warn")
        except HTTPException:
            v["new_hospital_id"] = None
            push.notice(vamb, "Your bed went to a more critical patient. Please choose another hospital.", "bad")
        push.refresh_incident(vid, extra_hospitals=[res["hospital_id"]])
    notified = [r["hospital_id"] for r in query("SELECT hospital_id FROM incident_hospitals WHERE incident_id=%s", (incident_id,))]
    push.refresh_incident(incident_id, extra_hospitals=touched | set(notified))     # booking wale + baaki (stood down) sabhi
    push.refresh_waiting_ambulances()                                               # jinke options mein ye bed tha unki list taaza


@router.post("/incidents/{incident_id}/reserve")
def reserve(incident_id: int, body: ReserveBody = ReserveBody(), user=Depends(need_ambulance)):
    inc = query("SELECT ambulance_id, status, severity FROM incidents WHERE id=%s", (incident_id,))
    if not inc or inc[0]["ambulance_id"] != user["ambulance_id"]:
        raise HTTPException(404, "Incident nahi mila")
    inc = inc[0]
    if inc["status"] == "RESERVED":                           # double tap: purani reservation hi lauta do
        res = try_reserve(incident_id, 0)
        return {**res, "hospital": hospital_card(res["hospital_id"]), "tried": []}

    def work():
        if body.hospital_id:                                  # paramedic ne khud hospital chuna: sirf wahi try
            try:
                res = try_reserve(incident_id, body.hospital_id, allow_preempt=True)
            except Unavailable as e:
                raise HTTPException(409, f"Ye hospital abhi nahi le sakta ({e}), dusra chuno")
            res["tried"] = []
        else:
            res = auto_reserve(incident_id)
        _after_reserve(incident_id, res)
        return res

    # sab reserve requests ek priority dispatcher se guzarti hain: CRITICAL pehle, phir pehle report wala
    res = dispatcher.submit(inc["severity"] or "MODERATE", work, label=incident_id)
    return {**res, "hospital": hospital_card(res["hospital_id"])}


# ---------- 4. Ambulance live location / arrival ----------
class Loc(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    eta_min: Optional[float] = None       # drive ka bacha hua time (client road route se)
    km_left: Optional[float] = None
    phase: Optional[str] = None           # "scene" | "hospital"
    final: bool = False                   # drive khatam: position DB mein turant likho


def _targets(amb_id: int):
    t = hub.targets.get(amb_id)
    if t and time.time() - t[0] < 2.0:
        return t
    inc = query("SELECT id, status, reserved_hospital_id FROM incidents WHERE ambulance_id=%s "
                "AND status IN ('REPORTED','ASSESSED','RESERVED') ORDER BY id DESC LIMIT 1", (amb_id,))
    code = query("SELECT code FROM ambulances WHERE id=%s", (amb_id,))[0]["code"]
    if not inc:
        hids, iid = [], None
    elif inc[0]["status"] == "RESERVED":
        hids, iid = [inc[0]["reserved_hospital_id"]], inc[0]["id"]
    else:
        iid, hids = inc[0]["id"], push._ih(inc[0]["id"])
    hub.targets[amb_id] = t = (time.time(), iid, hids, code)
    return t


def handle_location(amb_id: int, loc: Loc):
    now = time.time()
    hub.live[amb_id] = {"lat": loc.lat, "lon": loc.lon, "ts": now, "eta": loc.eta_min, "km": loc.km_left}
    if loc.phase == "scene" and loc.km_left is not None and loc.km_left < 0.15:
        hub.scene_at.setdefault(amb_id, now)                                # scene par pahunch gayi: report ka timer shuru
    if loc.final or now - hub.last_db_write.get(amb_id, 0) >= 3.0:         # DB mein har 3 second; WebSocket par har update
        hub.last_db_write[amb_id] = now
        query("UPDATE ambulances SET lat=%s, lon=%s, location_updated_at=now() WHERE id=%s", (loc.lat, loc.lon, amb_id))
    _, iid, hids, code = _targets(amb_id)
    if hids:
        hub.emit(hub.hospitals(hids), {"type": "location", "ambulance_id": amb_id, "code": code, "incident_id": iid,
                                       "lat": loc.lat, "lon": loc.lon, "eta_min": loc.eta_min,
                                       "km_left": loc.km_left, "phase": loc.phase})


@router.put("/ambulance/location")
def update_location(loc: Loc, user=Depends(need_ambulance)):
    handle_location(user["ambulance_id"], loc)
    return {"ok": True}


@router.post("/incidents/{incident_id}/arrived")
def arrived(incident_id: int, user=Depends(need_ambulance)):
    with tx() as cur:
        cur.execute("SELECT i.status, h.lat, h.lon FROM incidents i LEFT JOIN hospitals h ON h.id=i.reserved_hospital_id "
                    "WHERE i.id=%s AND i.ambulance_id=%s FOR UPDATE OF i", (incident_id, user["ambulance_id"]))
        r = cur.fetchone()
        if not r or r["status"] != "RESERVED":
            raise HTTPException(409, "Reserved incident nahi hai")
        cur.execute("UPDATE incidents SET status='ARRIVED', arrived_at=now() WHERE id=%s", (incident_id,))
        cur.execute("UPDATE ambulances SET status='AVAILABLE', lat=%s, lon=%s, location_updated_at=now() WHERE id=%s",
                    (r["lat"], r["lon"], user["ambulance_id"]))
    hub.live.pop(user["ambulance_id"], None)
    t = hub.targets.get(user["ambulance_id"])
    hub.forget(user["ambulance_id"])
    hids = t[2] if t else []
    push.refresh_hospitals(hids)
    push.refresh_incident(incident_id, extra_hospitals=hids)
    return {"ok": True}


# ---------- 5. Ambulance ka current case (dashboard reload / MEDORA se dispatch hone par) ----------
def _case(amb_id: int) -> dict:
    amb = query("SELECT id, code, base_name, city, lat, lon, status FROM ambulances WHERE id=%s", (amb_id,))[0]
    rows = query("SELECT id, source, location_text, lat, lon, eta_to_scene_min, status, severity, patients, needs, "
                 "specialties, reserved_hospital_id FROM incidents WHERE ambulance_id=%s "
                 "AND status IN ('REPORTED','ASSESSED','RESERVED') ORDER BY id DESC LIMIT 1", (amb_id,))
    if not rows:
        return {"ambulance": amb, "incident": None, "hospital": None, "options": []}
    inc = rows[0]
    out = {"ambulance": amb, "incident": inc, "hospital": None, "options": []}
    if inc["reserved_hospital_id"]:
        out["hospital"] = hospital_card(inc["reserved_hospital_id"])
        out["hospital"]["eta_min"] = (query("SELECT eta_hospital_min FROM incident_hospitals WHERE incident_id=%s AND hospital_id=%s",
                                            (inc["id"], inc["reserved_hospital_id"])) or [{}])[0].get("eta_hospital_min")
    elif inc["status"] == "ASSESSED":
        out["options"] = rank_hospitals(inc["id"], inc["needs"], inc["severity"] or "MODERATE", inc["specialties"])[:5]
    elif inc["status"] == "REPORTED":
        out["provisional"] = provisional(inc["id"], 3)             # report se pehle ka andaaza (sirf dikhane ke liye)
    return out


@router.get("/ambulance/active")
def ambulance_active(user=Depends(need_ambulance)):
    return _case(user["ambulance_id"])


@router.post("/incidents/{incident_id}/cancel")
def cancel(incident_id: int, user=Depends(need_ambulance)):
    """Galat alarm / case band: ambulance free, reserved bed wapas."""
    with tx() as cur:
        cur.execute("SELECT status FROM incidents WHERE id=%s AND ambulance_id=%s FOR UPDATE",
                    (incident_id, user["ambulance_id"]))
        r = cur.fetchone()
        if not r or r["status"] in ("ARRIVED", "CANCELLED"):
            raise HTTPException(409, "Ye case already band hai")
        cur.execute("SELECT id, hospital_id, items, status FROM reservations WHERE incident_id=%s "
                    "AND status IN ('BOOKED','ADMITTED') FOR UPDATE", (incident_id,))
        res = cur.fetchone()
        if res:
            src = "booked" if res["status"] == "BOOKED" else "occupied"
            for k, q in sorted(res["items"].items()):
                cur.execute(f"UPDATE hospital_resources SET {src}={src}-%s, available=available+%s, updated_at=now() "
                            "WHERE hospital_id=%s AND resource_type=%s", (q, q, res["hospital_id"], k))
            cur.execute("UPDATE reservations SET status='CANCELLED', released_at=now() WHERE id=%s", (res["id"],))
        cur.execute("UPDATE incidents SET status='CANCELLED', cancelled_at=now() WHERE id=%s", (incident_id,))
        cur.execute("UPDATE incident_hospitals SET status='STOOD_DOWN' WHERE incident_id=%s", (incident_id,))
        cur.execute("UPDATE ambulances SET status='AVAILABLE' WHERE id=%s", (user["ambulance_id"],))
    t = hub.targets.get(user["ambulance_id"])
    hub.live.pop(user["ambulance_id"], None)
    hub.forget(user["ambulance_id"])
    extra = list(t[2]) if t else []
    push.refresh_hospitals(extra)
    hub.emit(hub.ambulance(user["ambulance_id"]), {"type": "refresh"})
    push.refresh_waiting_ambulances()
    return {"ok": True}


# ---------- 6. Pichhle cases (last 5) + timeline ----------
def case_id(i: int) -> str:
    return f"INC-{1000 + i}"


@router.get("/ambulance/history")
def ambulance_history(user=Depends(need_ambulance)):
    rows = query("SELECT id, severity, status, created_at, assessed_at, arrived_at, cancelled_at, location_text "
                 "FROM incidents WHERE ambulance_id=%s AND status IN ('ARRIVED','CANCELLED') ORDER BY id DESC LIMIT 5",
                 (user["ambulance_id"],))
    ids = [r["id"] for r in rows]
    res = query("SELECT r.incident_id, r.status, r.created_at, r.released_at, h.name FROM reservations r "
                "JOIN hospitals h ON h.id=r.hospital_id WHERE r.incident_id = ANY(%s) ORDER BY r.id", (ids,)) if ids else []
    out = []
    for r in rows:
        mine = [x for x in res if x["incident_id"] == r["id"]]
        final = [x for x in mine if x["status"] != "PREEMPTED"]
        ev = [{"label": "Accident reported" + (f" at {r['location_text']}" if r["location_text"] else ""), "at": r["created_at"]}]
        if r["assessed_at"]:
            ev.append({"label": f"Patient assessed ({(r['severity'] or '').title()})", "at": r["assessed_at"]})
        for x in mine:
            ev.append({"label": f"Bed held at {x['name']}", "at": x["created_at"]})
            if x["status"] == "PREEMPTED":
                ev.append({"label": f"Bed at {x['name']} went to a more critical patient", "at": x["released_at"]})
        ev.append({"label": "Arrived at hospital" if r["status"] == "ARRIVED" else "Case cancelled",
                   "at": r["arrived_at"] if r["status"] == "ARRIVED" else r["cancelled_at"]})
        ev.sort(key=lambda e: (e["at"] is None, e["at"]))
        out.append({"id": r["id"], "case_id": case_id(r["id"]), "severity": r["severity"], "status": r["status"],
                    "hospital": final[-1]["name"] if final else None, "date": r["created_at"], "events": ev})
    return out


# ---------- 7. Background: provisional refresh (har 2 min) + report na aaye to default report ----------
_last_prov: dict = {}      # incident_id -> last refresh ts
_auto_done: set = set()    # jinpar default report ho chuki


def _auto_report(iid: int, amb_id: int):
    """Ambulance scene par hai par paramedic ki report ASSUME_S second mein nahi aayi: ek default report
    (MODERATE, 1 patient, 1 ER bed) se turant bed hold karo, taaki ambulance rukne ke bajay chal sake."""
    with tx() as cur:
        cur.execute("SELECT status FROM incidents WHERE id=%s FOR UPDATE", (iid,))
        if cur.fetchone()["status"] != "REPORTED":
            return
        cur.execute("UPDATE incidents SET severity='MODERATE', patients=1, needs=%s, report=%s, status='ASSESSED', "
                    "assessed_at=now() WHERE id=%s", (json.dumps({"ER_BED": 1}), json.dumps({"auto": True}), iid))

    def work():
        res = auto_reserve(iid)
        _after_reserve(iid, res)
        return res
    try:
        res = dispatcher.submit("MODERATE", work, label=iid)
        name = hospital_card(res["hospital_id"])["name"]
        push.notice(amb_id, f"No report received. Default bed held at {name}. Drive there; cancel the case to change.", "warn")
    except Exception:
        push.notice(amb_id, "No report received and no hospital could be booked. Please send the report.", "bad")


def _tick():
    now = time.time()
    rows = query("SELECT id, ambulance_id FROM incidents WHERE status='REPORTED' AND ambulance_id IS NOT NULL")
    live = {r["id"] for r in rows}
    for k in list(_last_prov):
        if k not in live:
            _last_prov.pop(k, None)
    for r in rows:
        iid, amb = r["id"], r["ambulance_id"]
        if now - _last_prov.setdefault(iid, now) >= PROV_REFRESH_S:        # provisional ranking taaza karne ke liye
            _last_prov[iid] = now
            push.refresh_incident(iid)
        t = hub.scene_at.get(amb)
        if t and now - t >= ASSUME_S and iid not in _auto_done:
            _auto_done.add(iid)
            _auto_report(iid, amb)


def _loop():
    while True:
        time.sleep(5)
        try:
            _tick()
        except Exception as e:                    # worker kabhi band na ho
            print("background tick error:", e)


def start_background():
    threading.Thread(target=_loop, daemon=True, name="medora-background").start()
