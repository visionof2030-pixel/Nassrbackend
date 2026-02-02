import os
import random
import datetime
import hashlib
import secrets
import jwt
import google.generativeai as genai

from enum import Enum
from fastapi import FastAPI, HTTPException, Header, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# =====================================================
# ENV
# =====================================================
JWT_SECRET = os.getenv("JWT_SECRET")
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN")

if not JWT_SECRET or not ADMIN_TOKEN:
    raise RuntimeError("JWT_SECRET or ADMIN_TOKEN missing")

# =====================================================
# Gemini API Keys
# =====================================================
GEMINI_KEYS = [
    os.getenv("GEMINI_API_KEY_1"),
    os.getenv("GEMINI_API_KEY_2"),
    os.getenv("GEMINI_API_KEY_3"),
    os.getenv("GEMINI_API_KEY_4"),
    os.getenv("GEMINI_API_KEY_5"),
    os.getenv("GEMINI_API_KEY_6"),
    os.getenv("GEMINI_API_KEY_7"),
]
GEMINI_KEYS = [k for k in GEMINI_KEYS if k]

if not GEMINI_KEYS:
    raise RuntimeError("No Gemini API Keys found")

# =====================================================
# APP
# =====================================================
app = FastAPI(title="Educational AI Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # غيّرها لاحقاً إلى دومينك
    allow_methods=["*"],
    allow_headers=["*"],
)

# =====================================================
# ENUMS
# =====================================================
class ValidityPeriod(str, Enum):
    M30 = "30m"
    H1  = "1h"
    H3  = "3h"
    D1  = "1d"
    D3  = "3d"
    D7  = "7d"
    M1  = "1m"
    M3  = "3m"
    M5  = "5m"

# =====================================================
# MODELS
# =====================================================
class AskRequest(BaseModel):
    prompt: str

class ActivateRequest(BaseModel):
    code: str

# =====================================================
# STORAGE (In-Memory)
# =====================================================
# code_hash : { expires_at, period }
VALID_CODES = {}

# =====================================================
# HELPERS
# =====================================================
def pick_gemini_model():
    key = random.choice(GEMINI_KEYS)
    genai.configure(api_key=key)
    return genai.GenerativeModel("models/gemini-2.5-flash-lite")

def generate_short_code():
    return secrets.token_hex(3).upper()

def hash_code(code: str):
    return hashlib.sha256(code.encode()).hexdigest()

def calculate_expiration(period: ValidityPeriod) -> datetime.datetime:
    now = datetime.datetime.utcnow()

    mapping = {
        ValidityPeriod.M30: datetime.timedelta(minutes=30),
        ValidityPeriod.H1:  datetime.timedelta(hours=1),
        ValidityPeriod.H3:  datetime.timedelta(hours=3),
        ValidityPeriod.D1:  datetime.timedelta(days=1),
        ValidityPeriod.D3:  datetime.timedelta(days=3),
        ValidityPeriod.D7:  datetime.timedelta(days=7),
        ValidityPeriod.M1:  datetime.timedelta(days=30),
        ValidityPeriod.M3:  datetime.timedelta(days=90),
        ValidityPeriod.M5:  datetime.timedelta(days=150),
    }

    return now + mapping[period]

def verify_jwt(token: str):
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        if payload.get("type") != "activation":
            raise HTTPException(status_code=401, detail="Invalid token type")
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

# =====================================================
# ROUTES
# =====================================================
@app.get("/")
def health():
    return {
        "status": "ok",
        "time": datetime.datetime.utcnow().isoformat()
    }

# -----------------------------------------------------
# Generate Activation Code (Admin)
# -----------------------------------------------------
@app.get("/generate-code")
def generate_code(
    key: str,
    period: ValidityPeriod = Query(
        ValidityPeriod.M1,
        description="مدة صلاحية كود التفعيل"
    )
):
    if key != ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="Forbidden")

    short_code = generate_short_code()
    code_hash = hash_code(short_code)
    expires_at = calculate_expiration(period)

    VALID_CODES[code_hash] = {
        "expires_at": expires_at,
        "period": period.value
    }

    return {
        "activation_code": short_code,
        "period": period.value,
        "expires_at": expires_at.isoformat()
    }

# -----------------------------------------------------
# Activate Code
# -----------------------------------------------------
@app.post("/activate")
def activate(data: ActivateRequest):
    code = data.code.strip()
    if not code:
        raise HTTPException(status_code=400, detail="Code required")

    code_hash = hash_code(code)
    code_data = VALID_CODES.get(code_hash)

    if not code_data:
        raise HTTPException(status_code=403, detail="Invalid code")

    expires_at = code_data["expires_at"]

    if expires_at < datetime.datetime.utcnow():
        VALID_CODES.pop(code_hash, None)
        raise HTTPException(status_code=403, detail="Code expired")

    payload = {
        "type": "activation",
        "exp": expires_at
    }

    token = jwt.encode(payload, JWT_SECRET, algorithm="HS256")

    return {
        "token": token,
        "expires_at": expires_at.isoformat(),
        "period": code_data["period"]
    }

# -----------------------------------------------------
# Verify Token
# -----------------------------------------------------
@app.get("/verify")
def verify(x_token: str = Header(..., alias="X-Token")):
    verify_jwt(x_token)
    return {"status": "ok"}

# -----------------------------------------------------
# AI Generate
# -----------------------------------------------------
@app.post("/generate")
def generate(data: AskRequest, x_token: str = Header(..., alias="X-Token")):
    verify_jwt(x_token)

    try:
        model = pick_gemini_model()
        response = model.generate_content(data.prompt)
        return {"answer": response.text}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))