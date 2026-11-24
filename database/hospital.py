"""Hospital dashboard ke endpoints."""
import json
from typing import Literal, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from app.db import query, tx
from app.auth import current_user
from app import hub, push, incidents
from app.ml_api import bed_forecast_for

router = APIRouter(prefix="/hospital")


def need_hospital(user=Depends(current_user)):
    if user["role"] != "hospital":
        raise HTTPException(403, "Hospital login required")
    return user


@router.get("/incoming")
def incoming(user=Depends(need_hospital)):
    """Mere paas kaun kaun si ambulance aa sakti hai (severity ke hisaab se sorted), unki live location ke saath."""
    rows = query(
        "SELECT i.id AS incident_id, i.status, i.severity, i.patients, i.needs, i.specialties, i.report, "
        "i.lat AS scene_lat, i.lon AS scene_lon, i.location_text, ih.status AS my_status, ih.distance_km, "
        "GREATEST(0, EXTRACT(EPOCH FROM (i.created_at + make_interval(secs => COALESCE(i.eta_to_scene_min,0)*60) - now()))) AS deadline_in_s, "
        "ih.eta_hospital_min, i.ambulance_id, a.code AS ambulance, a.lat AS amb_lat, a.lon AS amb_lon, a.location_updated_at "
        "FROM incident_hospitals ih JOIN incidents i ON i.id=ih.incident_id LEFT JOIN ambulances a ON a.id=i.ambulance_id "
        "WHERE ih.hospital_id=%s AND ih.status<>'STOOD_DOWN' AND i.status NOT IN ('ARRIVED','CANCELLED') "
        "ORDER BY CASE i.severity WHEN 'CRITICAL' THEN 0 WHEN 'MODERATE' THEN 1 WHEN 'LOW' THEN 2 ELSE 3 END, "
        "ih.eta_hospital_min", (user["hospital_id"],))
    for r in rows:                                   # WebSocket se aayi taaza live location DB se zyada naayi hai
        lv = hub.live.get(r["ambulance_id"])
        if lv:
            r["amb_lat"], r["amb_lon"], r["live_eta_min"], r["live_km"] = lv["lat"], lv["lon"], lv.get("eta"), lv.get("km")
    for r in rows:                                   # report se pehle: tum is accident ke liye kitne number par ho (andaaza)
        if r["status"] == "REPORTED":
            ranked = incidents.provisional(r["incident_id"], 50)
            pos = next((n for n, o in enumerate(ranked, 1) if o["hospital_id"] == user["hospital_id"]), None)
            r["prov_rank"], r["prov_total"] = pos, len(ranked)
    return {"inbound_ambulances": len({r["ambulance"] for r in rows if r["ambulance"]}), "incidents": rows}


class Status(BaseModel):
    load: Literal["NORMAL", "BUSY", "OVERLOADED"]
    diverting: bool = False
    note: Optional[str] = None


@router.put("/status")
def set_status(s: Status, user=Depends(need_hospital)):
    query("UPDATE hospital_status SET load=%s, diverting=%s, note=%s, updated_at=now() WHERE hospital_id=%s",
          (s.load, s.diverting, s.note, user["hospital_id"]))
    push.refresh_waiting_ambulances()
    return {"ok": True}


class ResourceUpdate(BaseModel):
    resource_type: Literal["ER_BED", "ICU_BED", "VENTILATOR", "OT"]
    available: int = Field(ge=0)               # abhi kitne khali hain (hospital bas yahi sach batata hai)


SOURCES = Literal["LOGIN", "PERIODIC", "ALERT", "MANUAL"]
CONFIRM_EVERY_MIN = 15


def log_snapshot(cur, hid: int, source: str):
    """Abhi ke saare resource counts history mein + 'aakhri update' ka time store."""
    cur.execute("SELECT resource_type, total, available, booked, occupied FROM hospital_resources "
                "WHERE hospital_id=%s ORDER BY resource_type", (hid,))
    snap = {r["resource_type"]: {k: r[k] for k in ("total", "available", "booked", "occupied")} for r in cur.fetchall()}
    cur.execute("INSERT INTO resource_updates (hospital_id, source, snapshot) VALUES (%s,%s,%s)", (hid, source, json.dumps(snap)))
    cur.execute("UPDATE hospital_status SET confirmed_at=now() WHERE hospital_id=%s", (hid,))


class Row(BaseModel):
    total: Optional[int] = Field(default=None, ge=0, le=2000)
    available: int = Field(ge=0, le=2000)


class Confirm(BaseModel):
    resources: dict[Literal["ER_BED", "ICU_BED", "VENTILATOR", "OT"], Row]
    source: SOURCES = "MANUAL"


@router.put("/resources/confirm")
def confirm_resources(c: Confirm, user=Depends(need_hospital)):
    """Hospital apni asli ginti batata hai (login par, har 15 min, ya naye alert par). Simulated data yahin khatam."""
    hid = user["hospital_id"]
    with tx() as cur:
        cur.execute("SELECT resource_type, total, booked FROM hospital_resources WHERE hospital_id=%s "
                    "ORDER BY resource_type FOR UPDATE", (hid,))
        have = {r["resource_type"]: r for r in cur.fetchall()}
        for rt in sorted(c.resources):
            row, cur_row = c.resources[rt], have.get(rt)
            total = row.total if row.total is not None else (cur_row["total"] if cur_row else 0)
            booked = cur_row["booked"] if cur_row else 0
            occupied = total - booked - row.available
            if occupied < 0:
                raise HTTPException(422, f"{rt}: free {row.available} + ambulance ke liye held {booked} total {total} se zyada hai")
            if cur_row:
                cur.execute("UPDATE hospital_resources SET total=%s, available=%s, occupied=%s, is_simulated=FALSE, "
                            "basis='hospital confirmed', updated_at=now() WHERE hospital_id=%s AND resource_type=%s",
                            (total, row.available, occupied, hid, rt))
            else:
                cur.execute("INSERT INTO hospital_resources (hospital_id, resource_type, total, available, booked, occupied, "
                            "is_simulated, basis) VALUES (%s,%s,%s,%s,0,%s,FALSE,'hospital confirmed')",
                            (hid, rt, total, row.available, occupied))
        log_snapshot(cur, hid, c.source)
    push.refresh_waiting_ambulances()
    return {"ok": True}


@router.get("/updates")
def update_history(user=Depends(need_hospital)):
    return query("SELECT at, source FROM resource_updates WHERE hospital_id=%s ORDER BY at DESC LIMIT 12", (user["hospital_id"],))


@router.put("/resources")
def set_resource(u: ResourceUpdate, user=Depends(need_hospital)):
    with tx() as cur:
        cur.execute("SELECT total, booked FROM hospital_resources WHERE hospital_id=%s AND resource_type=%s FOR UPDATE",
                    (user["hospital_id"], u.resource_type))
        r = cur.fetchone()
        if not r:
            raise HTTPException(404, "Resource nahi mila")
        occupied = r["total"] - r["booked"] - u.available     # booked ko mat chhedo, baaki occupied
        if occupied < 0:
            raise HTTPException(422, f"available zyada hai: max {r['total'] - r['booked']} (booked {r['booked']})")
        cur.execute("UPDATE hospital_resources SET available=%s, occupied=%s, is_simulated=FALSE, updated_at=now() "
                    "WHERE hospital_id=%s AND resource_type=%s", (u.available, occupied, user["hospital_id"], u.resource_type))
        log_snapshot(cur, user["hospital_id"], "MANUAL")
    push.refresh_waiting_ambulances()
    push.refresh_waiting_ambulances()
    return {"ok": True, "occupied": occupied}


@router.get("/reservations")
def reservations(user=Depends(need_hospital)):
    return query("SELECT r.id, r.incident_id, r.items, r.status, r.created_at, i.severity, i.patients "
                 "FROM reservations r JOIN incidents i ON i.id=r.incident_id "
                 "WHERE r.hospital_id=%s AND r.status IN ('BOOKED','ADMITTED') ORDER BY r.created_at DESC",
                 (user["hospital_id"],))


def _own(cur, rid, hid):
    cur.execute("SELECT * FROM reservations WHERE id=%s AND hospital_id=%s FOR UPDATE", (rid, hid))
    r = cur.fetchone()
    if not r:
        raise HTTPException(404, "Reservation nahi mili")
    return r


@router.post("/reservations/{rid}/admit")
def admit(rid: int, user=Depends(need_hospital)):
    """Patient pahunch gaya: booked -> occupied."""
    hid = user["hospital_id"]
    with tx() as cur:
        r = _own(cur, rid, hid)
        if r["status"] != "BOOKED":
            raise HTTPException(409, f"Reservation {r['status']} hai")
        for k, q in sorted(r["items"].items()):
            cur.execute("UPDATE hospital_resources SET booked=booked-%s, occupied=occupied+%s, updated_at=now() "
                        "WHERE hospital_id=%s AND resource_type=%s", (q, q, hid, k))
        cur.execute("UPDATE reservations SET status='ADMITTED', admitted_at=now() WHERE id=%s", (rid,))
    push.refresh_hospitals([hid])
    return {"ok": True}


class Release(BaseModel):
    types: Optional[list[str]] = None           # None = sab free; ya sirf ["OT"] surgery ke baad


@router.post("/reservations/{rid}/release")
def release(rid: int, body: Release = Release(), user=Depends(need_hospital)):
    """Surgery/discharge ke baad free. BOOKED hai to cancel (booked -> available), ADMITTED hai to occupied -> available."""
    hid = user["hospital_id"]
    with tx() as cur:
        r = _own(cur, rid, hid)
        if r["status"] not in ("BOOKED", "ADMITTED"):
            raise HTTPException(409, f"Reservation {r['status']} hai")
        items = r["items"]
        types = [t for t in (body.types or list(items.keys())) if t in items]
        if not types:
            raise HTTPException(422, "Koi valid resource type nahi")
        src = "booked" if r["status"] == "BOOKED" else "occupied"
        if r["status"] == "ADMITTED" and r["admitted_at"]:             # ML data: kitni der ruka tha
            cur.execute("SELECT severity FROM incidents WHERE id=%s", (r["incident_id"],))
            sev = (cur.fetchone() or {}).get("severity")
            for k in sorted(types):
                cur.execute("INSERT INTO resource_releases (hospital_id, resource_type, qty, severity, occupied_min) "
                            "SELECT %s, %s, %s, %s, EXTRACT(EPOCH FROM (now() - admitted_at))/60 FROM reservations WHERE id=%s",
                            (hid, k, items[k], sev, rid))
        for k in sorted(types):
            cur.execute(f"UPDATE hospital_resources SET {src}={src}-%s, available=available+%s, updated_at=now() "
                        "WHERE hospital_id=%s AND resource_type=%s", (items[k], items[k], hid, k))
            items.pop(k)
        if items:
            cur.execute("UPDATE reservations SET items=%s WHERE id=%s", (json.dumps(items), rid))
        else:
            final = "CANCELLED" if r["status"] == "BOOKED" else "RELEASED"
            cur.execute("UPDATE reservations SET items='{}', status=%s, released_at=now() WHERE id=%s", (final, rid))
    push.refresh_hospitals([hid])
    push.refresh_waiting_ambulances()
    push.refresh_incident(r["incident_id"])
    push.refresh_waiting_ambulances()
    return {"ok": True, "remaining": items}


@router.get("/overview")
def overview(user=Depends(need_hospital)):
    hid = user["hospital_id"]
    h = query("SELECT id, code, name, city, lat, lon, emergency_phone, phone FROM hospitals WHERE id=%s", (hid,))[0]
    st = query("SELECT load, diverting, note, confirmed_at, now() AS server_now FROM hospital_status WHERE hospital_id=%s", (hid,))[0]
    st["confirm_every_min"] = CONFIRM_EVERY_MIN
    res = query("SELECT resource_type, total, available, booked, occupied, is_simulated FROM hospital_resources "
                "WHERE hospital_id=%s ORDER BY resource_type", (hid,))
    return {"hospital": h, "status": st, "resources": res, "forecast": bed_forecast_for(hid)}


@router.get("/history")
def history(user=Depends(need_hospital)):
    """Pichhle 5 band ho chuke cases (is hospital ke) + har ek ki timeline."""
    rows = query("SELECT r.id, r.incident_id, r.status, r.created_at, r.admitted_at, r.released_at, i.severity, i.patients, "
                 "a.code AS ambulance FROM reservations r JOIN incidents i ON i.id=r.incident_id "
                 "LEFT JOIN ambulances a ON a.id=i.ambulance_id "
                 "WHERE r.hospital_id=%s AND r.status IN ('RELEASED','CANCELLED','PREEMPTED') ORDER BY r.id DESC LIMIT 5",
                 (user["hospital_id"],))
    out = []
    for r in rows:
        ev = [{"label": f"Bed held for {r['ambulance'] or 'ambulance'}", "at": r["created_at"]}]
        if r["admitted_at"]:
            ev.append({"label": "Patient admitted", "at": r["admitted_at"]})
        end = {"RELEASED": "Beds freed after treatment", "CANCELLED": "Booking cancelled",
               "PREEMPTED": "Bed given to a more critical patient"}[r["status"]]
        ev.append({"label": end, "at": r["released_at"]})
        out.append({"id": r["id"], "case_id": f"INC-{1000 + r['incident_id']}", "severity": r["severity"], "status": r["status"],
                    "ambulance": r["ambulance"], "patients": r["patients"], "date": r["created_at"], "events": ev})
    return out
