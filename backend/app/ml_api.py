"""ML endpoints (sirf SUJHAV). Faisla hamesha paramedic / hospital / matching engine ka rehta hai."""
import time
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from app.db import query
from app.auth import current_user
from app.ml import bed_forecast, severity

router = APIRouter(prefix="/ml")
_cache: dict = {}        # hospital_id -> (ts, resource signature, forecast)  (30 second)


class Vitals(BaseModel):
    """Sab optional: paramedic jo jaanta hai wahi bharta hai. Khali = pata nahi."""
    age: Optional[float] = Field(default=None, ge=0, le=120)
    rr: Optional[float] = Field(default=None, ge=0, le=100)          # saans / min
    sbp: Optional[float] = Field(default=None, ge=0, le=300)         # systolic BP
    pulse: Optional[float] = Field(default=None, ge=0, le=300)
    spo2: Optional[float] = Field(default=None, ge=0, le=100)
    gcs: Optional[float] = Field(default=None, ge=3, le=15)
    walking: Optional[bool] = None
    obeys: Optional[bool] = None                                      # simple aadesh maanta hai?
    penetrating: Optional[bool] = None
    pelvis: Optional[bool] = None
    flail: Optional[bool] = None
    crush_amput: Optional[bool] = None
    bleed: Optional[bool] = None
    high_mech: Optional[bool] = None


@router.post("/severity")
def suggest_severity(v: Vitals, user=Depends(current_user)):
    if user["role"] != "ambulance":
        raise HTTPException(403, "Sirf ambulance ke liye")
    return severity.predict(v.model_dump())


@router.get("/info")
def info(user=Depends(current_user)):
    """Model card: kis data par train hua, confusion matrix, recall (viva ke liye)."""
    return {"severity": severity.info(), "bed_forecast": {"prior_minutes": bed_forecast.PRIOR,
            "note": "Hospital ke asli release data aate hi prior se hat kar us data par aata hai"}}


def bed_forecast_for(hid: int) -> dict:
    now = time.time()
    res = query("SELECT resource_type, available, booked, occupied FROM hospital_resources WHERE hospital_id=%s", (hid,))
    sig = tuple((r["resource_type"], r["available"], r["booked"], r["occupied"]) for r in sorted(res, key=lambda r: r["resource_type"]))
    hit = _cache.get(hid)
    if hit and now - hit[0] < 30 and hit[1] == sig:          # bed ginti badli ho to turant dobara nikalo
        return hit[2]
    hist: dict = {}
    for r in query("SELECT resource_type, occupied_min FROM (SELECT resource_type, occupied_min, row_number() OVER "
                   "(PARTITION BY resource_type ORDER BY id DESC) AS n FROM resource_releases WHERE hospital_id=%s) x "
                   "WHERE n <= 200", (hid,)):
        hist.setdefault(r["resource_type"], []).append(r["occupied_min"])
    adm: dict = {}
    for r in query("SELECT items, EXTRACT(EPOCH FROM (now() - admitted_at))/60 AS el FROM reservations "
                   "WHERE hospital_id=%s AND status='ADMITTED' AND admitted_at IS NOT NULL", (hid,)):
        for k, q in (r["items"] or {}).items():
            adm.setdefault(k, []).extend([r["el"]] * int(q))
    out = bed_forecast.hospital_forecast(res, hist, adm, seed_base=hid * 100 + int(now // 300))   # 5 min tak sthir
    _cache[hid] = (now, sig, out)
    return out


@router.get("/bed-forecast")
def bed_forecast_api(hospital_id: int, user=Depends(current_user)):
    if not query("SELECT 1 FROM hospitals WHERE id=%s", (hospital_id,)):
        raise HTTPException(404, "Hospital nahi mila")
    return bed_forecast_for(hospital_id)
