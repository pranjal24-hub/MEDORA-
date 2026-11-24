import asyncio
import json
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Depends, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from app.db import query
from app.auth import make_token, current_user, decode
from app.dispatch import dispatcher
import threading
from app import incidents, hospital as hospital_api, signup, hub, ml_api
from app.ml import severity as ml_severity


@asynccontextmanager
async def lifespan(_app):
    hub.bind_loop()
    incidents.start_background()
    threading.Thread(target=ml_severity.warm, daemon=True, name="ml-warm").start()   # model load / train (background)
    yield


app = FastAPI(title="MEDORA", lifespan=lifespan)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


app.include_router(incidents.router)
app.include_router(hospital_api.router)
app.include_router(signup.router)
app.include_router(ml_api.router)


@app.websocket("/ws")
async def ws(websocket: WebSocket):
    """Live push. Connect hone ke baad pehle message mein token aata hai."""
    await websocket.accept()
    try:
        first = await asyncio.wait_for(websocket.receive_text(), 5)
        u = decode(json.loads(first).get("token", ""))
    except Exception:
        await websocket.close(code=4401)
        return
    key = ("hospital", u["hospital_id"]) if u["role"] == "hospital" else ("ambulance", u["ambulance_id"])
    await hub.add(key, websocket)
    await websocket.send_json({"type": "hello", "role": u["role"]})
    try:
        while True:
            if (await websocket.receive_text()) == "ping":     # connection zinda rakhne ke liye
                await websocket.send_text("pong")
    except Exception:                      # disconnect ya koi bhi error: bas connection hata do
        pass
    finally:
        hub.remove(key, websocket)


class Login(BaseModel):
    username: str
    password: str


@app.get("/health")
def health():
    return {"ok": True, "hospitals": query("SELECT count(*) AS n FROM hospitals")[0]["n"],
            "last_batches": list(dispatcher.batches)[-3:], "ws_clients": hub.connected()}


@app.post("/auth/login")
def login(body: Login):
    # password check database ke andar (pgcrypto bcrypt), plain text kahin store nahi hota
    rows = query(
        "SELECT username, role, hospital_id, ambulance_id FROM users "
        "WHERE username = %s AND password_hash = crypt(%s, password_hash)",
        (body.username.strip().lower(), body.password),
    )
    if not rows:
        raise HTTPException(401, "Wrong username or password")
    user = rows[0]
    return {"token": make_token(user), "role": user["role"],
            "hospital_id": user["hospital_id"], "ambulance_id": user["ambulance_id"]}


@app.get("/me")
def me(user=Depends(current_user)):
    if user["role"] == "hospital":
        info = query("SELECT id, code, name, city FROM hospitals WHERE id = %s", (user["hospital_id"],))
    else:
        info = query("SELECT id, code, base_name, city, lat, lon, status FROM ambulances WHERE id = %s",
                     (user["ambulance_id"],))
    return {"username": user["sub"], "role": user["role"], "profile": info[0] if info else None}


@app.get("/hospitals")
def hospitals(city: str | None = None):
    sql = ("SELECT h.id, h.code, h.name, h.city, h.ownership, h.lat, h.lon, h.phone, h.emergency_phone, "
           "h.emergency_24x7, h.trauma_centre, h.ambulance_service, h.data_quality, "
           "COALESCE(json_object_agg(r.resource_type, json_build_object('total', r.total, 'available', r.available, "
           "'booked', r.booked, 'occupied', r.occupied)) FILTER (WHERE r.resource_type IS NOT NULL), '{}') AS resources "
           "FROM hospitals h LEFT JOIN hospital_resources r ON r.hospital_id = h.id ")
    params = ()
    if city:
        sql += "WHERE lower(h.city) = lower(%s) "
        params = (city,)
    sql += "GROUP BY h.id ORDER BY h.city, h.name"
    return query(sql, params)


@app.get("/hospitals/{hospital_id}")
def hospital(hospital_id: int):
    rows = query("SELECT * FROM hospitals WHERE id = %s", (hospital_id,))
    if not rows:
        raise HTTPException(404, "Hospital not found")
    h = rows[0]
    h["services"] = [r["service"] for r in query(
        "SELECT service FROM hospital_services WHERE hospital_id = %s ORDER BY service", (hospital_id,))]
    h["resources"] = query(
        "SELECT resource_type, total, available, booked, occupied, is_simulated FROM hospital_resources "
        "WHERE hospital_id = %s ORDER BY resource_type", (hospital_id,))
    return h


@app.get("/ambulances")
def ambulances(user=Depends(current_user)):
    return query("SELECT id, code, base_name, city, lat, lon, status, location_updated_at FROM ambulances ORDER BY code")


@app.get("/ambulances/bases")
def ambulance_bases(user=Depends(current_user)):
    """Map ke liye: har ambulance ka base (sthir jagah)."""
    return query("SELECT id, code, base_name, city, base_lat AS lat, base_lon AS lon, status FROM ambulances ORDER BY code")
