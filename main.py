import os
import random
import datetime
import hashlib
import secrets
import jwt
import google.generativeai as genai

from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# =====================================================
# ENV
# =====================================================
JWT_SECRET = os.getenv("JWT_SECRET")
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN")

if not JWT_SECRET or not ADMIN_TOKEN:
    raise RuntimeError("JWT_SECRET or ADMIN_TOKEN missing")

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
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# =====================================================
# MODELS
# =====================================================
class GenerateRequest(BaseModel):
    report_type: str
    subject: str | None = None
    lesson: str | None = None
    grade: str | None = None
    target: str | None = None
    place: str | None = None
    count: str | None = None

class ActivateRequest(BaseModel):
    code: str

# =====================================================
# STORAGE (ذاكرة مؤقتة)
# =====================================================
VALID_CODES = {}  # code_hash: expiry_datetime

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

def verify_jwt(token: str):
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        if payload.get("type") != "activation":
            raise HTTPException(status_code=401, detail="Invalid token")
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

# =====================================================
# 🔴 جميع البرومبتات (هنا فقط)
# =====================================================

MASTER_PROMPT = """
أنت خبير تربوي تعليمي محترف تمتلك خبرة ميدانية واسعة في التعليم العام.
تعتمد منظورًا تربويًا مهنيًا احترافيًا يركّز على تحسين جودة التعليم،
ودعم المعلم، وتعزيز بيئة التعلّم، وخدمة القيادة المدرسية.

اكتب المحتوى وكأنه صادر عن معلم متمرس يعمل داخل الميدان التعليمي.
استخدم لغة عربية فصحى سليمة وخالية من الأخطاء.
التزم بالصياغة التقريرّية المهنية.
تجنب الأسلوب الإنشائي أو العاطفي.
"""

PROFESSIONAL_RULES = """
التوجيهات المهنية الملزمة:
- لا تكتب عناوين الحقول داخل النص إطلاقًا
- ابدأ بالمضمون مباشرة دون تمهيد
- اربط المحتوى بواقع المدرسة والميدان التعليمي
- راعِ الفروق الفردية
- اربط بين المعلم والطالب والمنهج والبيئة الصفية
- تجنب الحشو أو التكرار
"""

CONTENT_RULES = """
شروط المحتوى:
- كل فقرة تقريبًا 25 كلمة
- لا تقل عن 20 كلمة ولا تزيد عن 30 كلمة
- وجود ترابط منطقي بين جميع الفقرات
- كل فقرة تضيف قيمة تعليمية حقيقية
"""

FIELDS_ORDER = """
اكتب النتائج بالترتيب التالي فقط:
1. الهدف التربوي
2. نبذة مختصرة
3. إجراءات التنفيذ
4. الاستراتيجيات
5. نقاط القوة
6. نقاط التحسين
7. التوصيات
"""

ANTI_PATTERNS = """
ممنوع تمامًا:
- كتابة عناوين الحقول داخل النص
- إعادة صياغة السؤال
- استخدام تعداد نقطي
- استخدام أسلوب أدبي أو إنشائي
- إضافة مقدمات أو خاتمة
"""

def build_prompt(data: GenerateRequest) -> str:
    context = f"""
التقرير المطلوب: "{data.report_type}"
"""
    if data.subject:
        context += f"المادة: {data.subject}\n"
    if data.lesson:
        context += f"الدرس: {data.lesson}\n"
    if data.grade:
        context += f"الصف: {data.grade}\n"
    if data.target:
        context += f"المستهدفون: {data.target}\n"
    if data.place:
        context += f"مكان التنفيذ: {data.place}\n"
    if data.count:
        context += f"عدد الحضور: {data.count}\n"

    final_prompt = f"""
{MASTER_PROMPT}

{context}

{PROFESSIONAL_RULES}

{CONTENT_RULES}

{ANTI_PATTERNS}

{FIELDS_ORDER}
"""
    return final_prompt.strip()

# =====================================================
# ROUTES
# =====================================================

@app.get("/")
def health():
    return {"status": "ok", "time": datetime.datetime.utcnow().isoformat()}

# -------- توليد كود --------
@app.get("/generate-code")
def generate_code(key: str):
    if key != ADMIN_TOKEN:
        raise HTTPException(status_code=403)

    code = generate_short_code()
    VALID_CODES[hash_code(code)] = datetime.datetime.utcnow() + datetime.timedelta(days=30)

    return {
        "activation_code": code,
        "expires_in": "30 days"
    }

# -------- تفعيل --------
@app.post("/activate")
def activate(data: ActivateRequest):
    code_hash = hash_code(data.code)
    expiry = VALID_CODES.get(code_hash)

    if not expiry or expiry < datetime.datetime.utcnow():
        raise HTTPException(status_code=403, detail="Invalid or expired code")

    token = jwt.encode(
        {"type": "activation", "exp": datetime.datetime.utcnow() + datetime.timedelta(days=30)},
        JWT_SECRET,
        algorithm="HS256"
    )

    return {"token": token}

# -------- توليد التقرير --------
@app.post("/generate")
def generate(data: GenerateRequest, x_token: str = Header(..., alias="X-Token")):
    verify_jwt(x_token)

    try:
        prompt = build_prompt(data)
        model = pick_gemini_model()
        response = model.generate_content(prompt)

        return {"answer": response.text}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
