import os
import random
import datetime
import hashlib
import secrets
import jwt
import google.generativeai as genai

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
# GEMINI KEYS (AUTO DISCOVERY) ✅ الخيار 2
# =====================================================
GEMINI_KEYS = [
    v for k, v in os.environ.items()
    if k.startswith("GEMINI_API_KEY_")
]

if not GEMINI_KEYS:
    raise RuntimeError("No Gemini API Keys found")

# =====================================================
# APP
# =====================================================
app = FastAPI(title="Educational AI Backend")

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
# SIMPLE STORAGE (in-memory)
# ⚠️ للاستعمال الإنتاجي استخدم Redis أو DB
# =====================================================
VALID_CODES = {}  # code_hash : expiration_datetime

# =====================================================
# HELPERS
# =====================================================
def pick_gemini_model():
    key = random.choice(GEMINI_KEYS)
    genai.configure(api_key=key)
    return genai.GenerativeModel("models/gemini-2.5-flash-lite")

def generate_short_code():
    return secrets.token_hex(3).upper()  # مثال: A9F3C2

def hash_code(code: str):
    return hashlib.sha256(code.encode()).hexdigest()

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
# DURATIONS MAP ✅
# =====================================================
DURATION_MAP = {
    "5m":  datetime.timedelta(minutes=5),
    "30m": datetime.timedelta(minutes=30),
    "1h":  datetime.timedelta(hours=1),
    "3h":  datetime.timedelta(hours=3),
    "1d":  datetime.timedelta(days=1),
    "3d":  datetime.timedelta(days=3),
    "7d":  datetime.timedelta(days=7),
    "1m":  datetime.timedelta(days=30),
    "3m":  datetime.timedelta(days=90),
    "5mth": datetime.timedelta(days=150),
}

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
# توليد كود تفعيل (مشرف)
# مثال:
# /generate-code?key=ADMIN_TOKEN&duration=5m
# -----------------------------------------------------
@app.get("/generate-code")
def generate_code(
    key: str = Query(...),
    duration: str = Query("1d")
):
    if key != ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="Forbidden")

    if duration not in DURATION_MAP:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid duration. Allowed: {list(DURATION_MAP.keys())}"
        )

    short_code = generate_short_code()
    code_hash = hash_code(short_code)

    expires_at = datetime.datetime.utcnow() + DURATION_MAP[duration]
    VALID_CODES[code_hash] = expires_at

    return {
        "activation_code": short_code,
        "expires_at": expires_at.isoformat(),
        "duration": duration
    }

# -----------------------------------------------------
# تفعيل الأداة (المستخدم)
# -----------------------------------------------------
@app.post("/activate")
def activate(data: ActivateRequest):
    code = data.code.strip()
    if not code:
        raise HTTPException(status_code=400, detail="Code required")

    code_hash = hash_code(code)
    expires_at = VALID_CODES.get(code_hash)

    if not expires_at:
        raise HTTPException(status_code=403, detail="Invalid code")

    if expires_at < datetime.datetime.utcnow():
        VALID_CODES.pop(code_hash, None)
        raise HTTPException(status_code=403, detail="Code expired")

    # JWT ينتهي مع نفس مدة الكود
    payload = {
        "type": "activation",
        "exp": expires_at
    }

    token = jwt.encode(payload, JWT_SECRET, algorithm="HS256")

    return {
        "token": token,
        "expires_at": expires_at.isoformat()
    }

# -----------------------------------------------------
# تحقق من التفعيل
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