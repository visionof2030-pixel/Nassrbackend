import os
import random
import datetime
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

if not JWT_SECRET:
    raise RuntimeError("JWT_SECRET missing")

# 7 مفاتيح Gemini
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
    raise RuntimeError("No Gemini API keys found")

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
    subject: str | None = ""
    lesson: str | None = ""
    grade: str | None = ""
    target: str | None = ""
    place: str | None = ""
    count: str | None = ""

# =====================================================
# HELPERS
# =====================================================
def pick_gemini_model():
    key = random.choice(GEMINI_KEYS)
    genai.configure(api_key=key)
    return genai.GenerativeModel("models/gemini-2.5-flash-lite")

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
# 🔥 ALL PROMPTS (هنا الذكاء بالكامل)
# =====================================================

BASE_SYSTEM_PROMPT = """
أنت خبير تربوي تعليمي محترف تمتلك خبرة ميدانية واسعة في التعليم العام داخل المدارس.
تكتب التقارير التربوية بلغة عربية فصحى سليمة، مهنية، دقيقة، ومتزنة.
تراعي واقع الميدان التعليمي وسياق المدرسة السعودية.
تركّز على جودة التعليم، تطوير أداء attaching المعلم، وتحسين نواتج التعلّم.
"""

CONTENT_RULES_PROMPT = """
قواعد إلزامية:
- لا تذكر عناوين الحقول داخل النص.
- لا تبدأ بجمل تمهيدية مثل: الهدف التربوي هو.
- اكتب بصيغة تقريرية مهنية وكأن التقرير صادر عن المعلم.
- طول كل فقرة يقارب 25 كلمة.
- تجنب الحشو والتكرار.
- اربط المحتوى بالمادة والدرس والبيئة الصفية عند توفرها.
"""

FIELDS_PROMPT = """
الحقول المطلوبة بالترتيب:
1. الهدف التربوي
2. نبذة مختصرة
3. إجراءات التنفيذ
4. الاستراتيجيات
5. نقاط القوة
6. نقاط التحسين
7. التوصيات

اكتب كل حقل في سطر مستقل يبدأ برقمه فقط.
"""

def build_prompt(data: GenerateRequest) -> str:
    context = f"""
نوع التقرير: {data.report_type}
"""
    if data.subject:
        context += f"\nالمادة: {data.subject}"
    if data.lesson:
        context += f"\nالدرس: {data.lesson}"
    if data.grade:
        context += f"\nالصف: {data.grade}"
    if data.target:
        context += f"\nالمستهدفون: {data.target}"
    if data.place:
        context += f"\nمكان التنفيذ: {data.place}"
    if data.count:
        context += f"\nعدد الحضور: {data.count}"

    final_prompt = f"""
{BASE_SYSTEM_PROMPT}

{context}

{CONTENT_RULES_PROMPT}

{FIELDS_PROMPT}
"""
    return final_prompt.strip()

# =====================================================
# ROUTES
# =====================================================

@app.get("/")
def health():
    return {
        "status": "ok",
        "time": datetime.datetime.utcnow().isoformat()
    }

@app.post("/generate")
def generate(
    data: GenerateRequest,
    x_token: str = Header(..., alias="X-Token")
):
    verify_jwt(x_token)

    try:
        model = pick_gemini_model()
        prompt = build_prompt(data)
        response = model.generate_content(prompt)

        return {
            "answer": response.text
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))