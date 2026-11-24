import os, time
import jwt
from fastapi import Header, HTTPException


SECRET = os.environ.get("JWT_SECRET", "dev-secret-change-me")
ALGO = "HS256"
TTL = 12 * 3600  # 12 ghante


def make_token(user: dict) -> str:
    # token me user ki imp info rkho
    payload = {
        "sub": user["username"],
        "role": user["role"],
        "hospital_id": user["hospital_id"],
        "ambulance_id": user["ambulance_id"],
        "exp": int(time.time()) + TTL,
    }
    return jwt.encode(payload, SECRET, algorithm=ALGO)


def decode(token: str) -> dict:
    # token verify/decode kro
    return jwt.decode(token, SECRET, algorithms=[ALGO])


def current_user(authorization: str = Header(default="")) -> dict:
    # request ka auth header chk kro
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "Login required")
    try:
        return decode(authorization[7:])
    except jwt.PyJWTError:
        # invalid ya expired token ko reject kro
        raise HTTPException(401, "Invalid or expired token")