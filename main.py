import os
import random
import hashlib
import secrets
from datetime import datetime, timedelta

import jwt
import google.generativeai as genai

from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# =====================================================
# ENV
# =====================================================
JWT_SECRET = os.getenv("JWT_SECRET", "CHANGE_ME_SECRET")
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "FahadJassar14061436")

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
app = FastAPI(title="Nassr AI Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# =====================================================
# MODELS
# =====================================================
class AskRequest(BaseModel):
    prompt: str

class ActivateRequest(BaseModel):
    code: str

# =====================================================
# STORAGE (مؤقت - in memory)
# =====================================================
# code_hash -> expires_at
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

def create_jwt(expires_at: datetime):
    payload = {
        "type": "activation",
        "exp": expires_at
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")

def verify_jwt(token: str):
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="TOKEN_EXPIRED")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="INVALID_TOKEN")

# =====================================================
# DURATIONS
# =====================================================
DURATIONS = {
    "5m": timedelta(minutes=5),
    "30m": timedelta(minutes=30),
    "1h": timedelta(hours=1),
    "3h": timedelta(hours=3),
    "1d": timedelta(days=1),
    "3d": timedelta(days=3),
    "7d": timedelta(days=7),
    "1m": timedelta(days=30),
    "3m": timedelta(days=90),
    "5mth": timedelta(days=150),
}

# =====================================================
# ROUTES
# =====================================================

@app.get("/")
def health():
    return {
        "status": "healthy",
        "time": datetime.utcnow().isoformat()
    }

# -----------------------------------------------------
# توليد كود (مشرف)
# مثال:
# /generate-code?key=ADMIN&duration=5m
# -----------------------------------------------------
@app.get("/generate-code")
def generate_code(key: str, duration: str):
    if key != ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="Forbidden")

    if duration not in DURATIONS:
        raise HTTPException(status_code=400, detail="Invalid duration")

    code = generate_short_code()
    code_hash = hash_code(code)

    expires_at = datetime.utcnow() + DURATIONS[duration]
    VALID_CODES[code_hash] = expires_at

    return {
        "activation_code": code,
        "duration": duration,
        "expires_at": expires_at.isoformat() + "Z"
    }

# -----------------------------------------------------
# تفعيل كود
# -----------------------------------------------------
@app.post("/activate")
def activate(data: ActivateRequest):
    code = data.code.strip()
    if not code:
        raise HTTPException(status_code=400, detail="CODE_REQUIRED")

    code_hash = hash_code(code)
    expires_at = VALID_CODES.get(code_hash)

    if not expires_at:
        raise HTTPException(status_code=403, detail="INVALID_CODE")

    if expires_at < datetime.utcnow():
        VALID_CODES.pop(code_hash, None)
        raise HTTPException(status_code=403, detail="CODE_EXPIRED")

    token = create_jwt(expires_at)

    return {
        "token": token,
        "expires_at": expires_at.isoformat() + "Z"
    }

# -----------------------------------------------------
# تحقق من التوكن
# -----------------------------------------------------
@app.get("/verify")
def verify(x_token: str = Header(..., alias="X-Token")):
    verify_jwt(x_token)
    return {"status": "ok"}

# -----------------------------------------------------
# الذكاء الاصطناعي
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