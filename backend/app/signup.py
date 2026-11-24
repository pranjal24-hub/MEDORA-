"""Nayi ambulance / naye hospital ka sign up (login ke bina khula endpoint)."""
import re
from typing import Literal, Optional
import psycopg2.errors
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator
from app.db import tx, query
from app.auth import make_token

router = APIRouter(prefix="/signup")
CITIES = Literal["Dehradun", "Haridwar", "Rishikesh", "Roorkee"]
USER_RE = re.compile(r"^[a-z0-9_-]{3,30}$")


class _Base(BaseModel):
    username: str
    password: str = Field(min_length=8, max_length=72)
    city: CITIES
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)

    @field_validator("password")
    @classmethod
    def _p(cls, v):
        if not (re.search(r"[A-Za-z]", v) and re.search(r"\d", v)):
            raise ValueError("password: kam se kam 8 characters, ek letter aur ek number")
        return v

    @field_validator("username")
    @classmethod
    def _u(cls, v):
        v = v.strip().lower()
        if not USER_RE.match(v):
            raise ValueError("username 3-30 chars: a-z, 0-9, _ ya -")
        return v


class AmbulanceSignup(_Base):
    base_name: str = Field(min_length=2, max_length=60)
    plate: Optional[str] = Field(default=None, max_length=20)


class HospitalSignup(_Base):
    name: str = Field(min_length=3, max_length=100)
    ownership: Literal["government", "private"] = "private"
    phone: Optional[str] = Field(default=None, max_length=30)
    emergency_phone: Optional[str] = Field(default=None, max_length=30)
    trauma_centre: bool = False
    er_beds: int = Field(default=10, ge=0, le=500)
    icu_beds: int = Field(default=0, ge=0, le=500)
    ventilators: int = Field(default=0, ge=0, le=500)
    ot: int = Field(default=0, ge=0, le=100)
    address: Optional[str] = Field(default=None, max_length=200)
    emergency_24x7: bool = True
    services: list[str] = []


def _taken():
    return HTTPException(409, "Ye username pehle se hai, doosra chuno")


@router.post("/ambulance")
def signup_ambulance(b: AmbulanceSignup):
    try:
        with tx() as cur:
            cur.execute("SELECT nextval(pg_get_serial_sequence('ambulances','id')) AS id")
            aid = cur.fetchone()["id"]
            cur.execute("INSERT INTO ambulances (id, code, plate, base_name, city, base_lat, base_lon, lat, lon) "
                        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                        (aid, f"AMB-{aid:02d}", b.plate, b.base_name.strip(), b.city, b.lat, b.lon, b.lat, b.lon))
            cur.execute("INSERT INTO users (username, password_hash, role, ambulance_id) "
                        "VALUES (%s, crypt(%s, gen_salt('bf')), 'ambulance', %s)", (b.username, b.password, aid))
    except psycopg2.errors.UniqueViolation:
        raise _taken()
    user = {"username": b.username, "role": "ambulance", "hospital_id": None, "ambulance_id": aid}
    return {"token": make_token(user), "role": "ambulance", "ambulance_id": aid, "hospital_id": None, "code": f"AMB-{aid:02d}"}


@router.post("/hospital")
def signup_hospital(b: HospitalSignup):
    try:
        with tx() as cur:
            cur.execute("SELECT nextval(pg_get_serial_sequence('hospitals','id')) AS id")
            hid = cur.fetchone()["id"]
            cur.execute("INSERT INTO hospitals (id, code, name, city, ownership, lat, lon, address, phone, emergency_phone, "
                        "emergency_24x7, trauma_centre, data_quality, notes) "
                        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'self_registered','Self registered, verify karna baaki')",
                        (hid, f"SELF-{hid:03d}", b.name.strip(), b.city, b.ownership, b.lat, b.lon, b.address,
                         b.phone or b.emergency_phone, b.emergency_phone, b.emergency_24x7, b.trauma_centre))
            cur.execute("INSERT INTO hospital_status (hospital_id, confirmed_at) VALUES (%s, now())", (hid,))
            for rt, n in (("ER_BED", b.er_beds), ("ICU_BED", b.icu_beds), ("VENTILATOR", b.ventilators), ("OT", b.ot)):
                cur.execute("INSERT INTO hospital_resources (hospital_id, resource_type, total, available, is_simulated, basis) "
                            "VALUES (%s,%s,%s,%s,FALSE,'self registered')", (hid, rt, n, n))
            cur.execute("INSERT INTO resource_updates (hospital_id, source, snapshot) SELECT %s, 'SIGNUP', "
                        "json_object_agg(resource_type, json_build_object('total',total,'available',available,'booked',booked,'occupied',occupied)) "
                        "FROM hospital_resources WHERE hospital_id=%s", (hid, hid))
            for sv in {s.strip() for s in b.services if s.strip()}:
                cur.execute("INSERT INTO hospital_services (hospital_id, service) VALUES (%s,%s)", (hid, sv[:60]))
            cur.execute("INSERT INTO users (username, password_hash, role, hospital_id) "
                        "VALUES (%s, crypt(%s, gen_salt('bf')), 'hospital', %s)", (b.username, b.password, hid))
    except psycopg2.errors.UniqueViolation:
        raise _taken()
    user = {"username": b.username, "role": "hospital", "hospital_id": hid, "ambulance_id": None}
    return {"token": make_token(user), "role": "hospital", "hospital_id": hid, "ambulance_id": None, "code": f"SELF-{hid:03d}"}


@router.get("/check")
def check(username: str):
    return {"free": not query("SELECT 1 FROM users WHERE username=%s", (username.strip().lower(),))}
