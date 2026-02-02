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
from typing import Optional
from enum import Enum

# =====================================================
# ENV (Render injects env vars automatically)
# =====================================================
JWT_SECRET = os.getenv("JWT_SECRET")
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN")

if not JWT_SECRET or not ADMIN_TOKEN:
    raise RuntimeError("JWT_SECRET or ADMIN_TOKEN missing")

# Gemini API Keys
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
# ENUMS
# =====================================================
class ValidityPeriod(str, Enum):
    THIRTY_MINUTES = "30m"
    ONE_HOUR = "1h"
    ONE_DAY = "1d"
    ONE_WEEK = "1w"
    ONE_MONTH = "30d"
    CUSTOM = "custom"

class ReportType(str, Enum):
    LESSON = "تحضير درس"
    SUPERVISION = "تقرير إشرافي"
    ACTIVITY = "تقرير نشاط"
    MEETING = "محضر اجتماع"
    TRAINING = "تقرير تدريبي"
    EVALUATION = "تقرير تقييمي"
    VISIT = "تقرير زيارة صفية"
    WORKSHOP = "تقرير ورشة عمل"
    EVENT = "تقرير فعالية"
    PROJECT = "تقرير مشروع"

# =====================================================
# MODELS
# =====================================================
class AskRequest(BaseModel):
    prompt: str

class ActivateRequest(BaseModel):
    code: str

class ReportRequest(BaseModel):
    report_type: str
    subject: Optional[str] = ""
    lesson: Optional[str] = ""
    grade: Optional[str] = ""
    target: Optional[str] = ""
    place: Optional[str] = ""
    count: Optional[str] = ""
    additional_info: Optional[str] = ""

# =====================================================
# STORAGE (in-memory)
# =====================================================
VALID_CODES = {}  # code_hash -> expiry datetime

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
            raise HTTPException(status_code=401, detail="Invalid token type")
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

def calculate_expiration(period: str, custom_days: Optional[int] = None) -> datetime.datetime:
    """Calculate expiration date based on period"""
    now = datetime.datetime.utcnow()
    
    if period == ValidityPeriod.THIRTY_MINUTES.value:
        return now + datetime.timedelta(minutes=30)
    elif period == ValidityPeriod.ONE_HOUR.value:
        return now + datetime.timedelta(hours=1)
    elif period == ValidityPeriod.ONE_DAY.value:
        return now + datetime.timedelta(days=1)
    elif period == ValidityPeriod.ONE_WEEK.value:
        return now + datetime.timedelta(weeks=1)
    elif period == ValidityPeriod.ONE_MONTH.value:
        return now + datetime.timedelta(days=30)
    elif period == ValidityPeriod.CUSTOM.value and custom_days:
        return now + datetime.timedelta(days=custom_days)
    else:
        return now + datetime.timedelta(days=30)  # Default one month

def get_duration_name(period: str) -> str:
    """Get Arabic name for duration"""
    if period == ValidityPeriod.THIRTY_MINUTES.value:
        return "نصف ساعة"
    elif period == ValidityPeriod.ONE_HOUR.value:
        return "ساعة واحدة"
    elif period == ValidityPeriod.ONE_DAY.value:
        return "يوم واحد"
    elif period == ValidityPeriod.ONE_WEEK.value:
        return "أسبوع واحد"
    elif period == ValidityPeriod.ONE_MONTH.value:
        return "شهر كامل"
    elif period == ValidityPeriod.CUSTOM.value:
        return "مخصص"
    else:
        return "غير محدد"

# =====================================================
# PROMPT BUILDER
# =====================================================
def build_educational_prompt(data: ReportRequest) -> str:
    # Different prompts for different report types
    report_type = data.report_type
    
    # Common prompt template
    base_prompt = f"""
أنت خبير تربوي تعليمي محترف.

التقرير المطلوب: {data.report_type}

المادة: {data.subject if data.subject else "غير محدد"}
الدرس/الموضوع: {data.lesson if data.lesson else "غير محدد"}
الصف/المستوى: {data.grade if data.grade else "غير محدد"}
المستهدفون: {data.target if data.target else "غير محدد"}
مكان التنفيذ: {data.place if data.place else "غير محدد"}
عدد الحضور: {data.count if data.count else "غير محدد"}
معلومات إضافية: {data.additional_info if data.additional_info else "لا يوجد"}

"""
    
    # Add specific requirements based on report type
    if "درس" in report_type or "تحضير" in report_type:
        base_prompt += """
اكتب تحضير درس احترافي وفق البنود التالية:
1. الهدف التربوي: (حدد الأهداف المعرفية والمهارية والوجدانية)
2. المقدمة: (كيفية استثارة الدافعية وربط الدرس بالحياة)
3. العرض: (الأنشطة والاستراتيجيات التعليمية خطوة بخطوة)
4. التقويم: (أساليب تقييم التعلم خلال وبعد الدرس)
5. الوسائل التعليمية: (المواد والأدوات المستخدمة)
6. التمايز: (كيفية تلبية احتياجات الطلاب المتفوقين والبطيئين)
7. الواجبات والتكليفات: (المهام المنزلية وأنشطة المتابعة)

الشروط:
- لغة عربية فصيحة
- كل بند يقارب 30-40 كلمة
- ترتيب منطقي للخطوات
- مراعاة الفروق الفردية
"""
    
    elif "إشرافي" in report_type or "زيارة" in report_type:
        base_prompt += """
اكتب تقريرًا إشرافيًا مهنيًا وفق البنود التالية:
1. الهدف من الزيارة/الإشراف: (ما الغرض الرئيسي)
2. الملاحظات الإيجابية: (نقاط القوة في الأداء)
3. الملاحظات التطويرية: (مجالات التحسين)
4. التوصيات: (مقترحات عملية للتحسين)
5. الأدلة والبراهين: (أمثلة من الملاحظة)
6. خطة المتابعة: (آلية متابعة التنفيذ)
7. الملخص التنفيذي: (تقييم عام ومستوى الأداء)

الشروط:
- لغة عربية فصيحة
- موضوعية ودقة في الوصف
- اقتراحات قابلة للتنفيذ
- التركيز على التطوير لا النقد
"""
    
    elif "اجتماع" in report_type or "محضر" in report_type:
        base_prompt += """
اكتب محضر اجتماع احترافي وفق البنود التالية:
1. الهدف من الاجتماع: (الغرض والأهداف المحددة)
2. الحضور: (قائمة المشاركين والغياب)
3. جدول الأعمال: (البنود التي نوقشت)
4. القرارات المتخذة: (ما تم الاتفاق عليه)
5. المهام والتكليفات: (المسؤوليات والمهام)
6. المواعيد النهائية: (آجال التنفيذ)
7. الاجتماع القادم: (موعد وبنود الاجتماع التالي)

الشروط:
- لغة عربية رسمية
- وضوح ودقة في التسجيل
- تحديد المسؤوليات بوضوح
- سهولة المتابعة والتنفيذ
"""
    
    elif "تدريبي" in report_type or "ورشة" in report_type:
        base_prompt += """
اكتب تقريرًا تدريبيًا احترافيًا وفق البنود التالية:
1. الهدف من البرنامج: (المخرجات المتوقعة)
2. المحتوى العلمي: (الموضوعات والمواد)
3. الأساليب التدريبية: (الطرق والاستراتيجيات)
4. تقييم المتدربين: (مستوى التفاعل والإنجاز)
5. نقاط القوة: (إيجابيات البرنامج)
6. نقاط التحسين: (مجالات التطوير)
7. التوصيات: (مقترحات للمستقبل)

الشروط:
- لغة عربية فصيحة
- تقييم موضوعي وشامل
- اقتراحات عملية
- الربط بين النظرية والتطبيق
"""
    
    elif "نشاط" in report_type or "فعالية" in report_type:
        base_prompt += """
اكتب تقريرًا عن النشاط وفق البنود التالية:
1. الهدف من النشاط: (الغاية التربوية)
2. وصف النشاط: (كيفية التنفيذ)
3. الفئة المستهدفة: (المشاركون)
4. الإنجازات: (ما تحقق من أهداف)
5. التحديات: (الصعوبات التي واجهت)
6. الدروس المستفادة: (ما يمكن تطبيقه مستقبلاً)
7. التوصيات: (لمشاريع مماثلة)

الشروط:
- لغة عربية واضحة
- التركيز على القيمة التعليمية
- تسجيل التفاعل والمشاركة
- اقتراحات للتطوير
"""
    
    elif "تقييمي" in report_type or "تقييم" in report_type:
        base_prompt += """
اكتب تقريرًا تقييميًا احترافيًا وفق البنود التالية:
1. الغرض من التقييم: (الهدف والمبرر)
2. معايير التقييم: (المقاييس المستخدمة)
3. النتائج: (ما تم رصده وتسجيله)
4. التحليل: (تفسير النتائج)
5. نقاط القوة: (الجوانب الإيجابية)
6. نقاط الضعف: (الجوانب التي تحتاج تحسين)
7. الخطة العلاجية: (آليات التطوير والتحسين)

الشروط:
- لغة عربية فصيحة
- موضوعية وعدم التحيز
- اعتماد على أدلة ومؤشرات
- اقتراحات عملية قابلة للقياس
"""
    
    else:
        # Default prompt for other report types
        base_prompt += """
اكتب تقريرًا مهنيًا وفق البنود التالية:
1. الهدف التربوي: (الغاية التعليمية)
2. النبذة المختصرة: (ملخص عام)
3. إجراءات التنفيذ: (الخطوات العملية)
4. الاستراتيجيات: (الأساليب المستخدمة)
5. نقاط القوة: (الإيجابيات)
6. نقاط التحسين: (مجالات التطوير)
7. التوصيات: (المقترحات المستقبلية)

الشروط:
- لغة عربية فصيحة
- كل بند يقارب 25-35 كلمة
- وضوح ودقة في الوصف
- تركيز على الجانب التطبيقي
"""
    
    return base_prompt

def post_process_response(text: str) -> str:
    """Post-process AI response to ensure proper format"""
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    
    # Look for numbered lines (1., 2., etc.)
    numbered_lines = []
    for line in lines:
        if line and line[0].isdigit() and ('.' in line[:3] or ')' in line[:3]):
            numbered_lines.append(line)
    
    # If we have at least 5 numbered lines, use them
    if len(numbered_lines) >= 5:
        return "\n".join(numbered_lines[:7])  # Return up to 7 points
    
    # Otherwise, extract sentences and number them
    import re
    sentences = re.split(r'[.!؟]\s+', text)
    sentences = [s.strip() for s in sentences if s.strip()]
    
    result = []
    for i in range(min(7, len(sentences))):
        result.append(f"{i+1}. {sentences[i]}")
    
    # If not enough sentences, add generic points
    if len(result) < 7:
        generic_points = [
            "الهدف التربوي واضح ومحدد",
            "الأنشطة متنوعة وملائمة",
            "استراتيجيات التعلم فعالة",
            "التفاعل الإيجابي مع المحتوى",
            "التقويم شامل ومتنوع",
            "الوسائل التعليمية ملائمة",
            "التحسينات المقترحة عملية"
        ]
        for i in range(len(result), 7):
            result.append(f"{i+1}. {generic_points[i]}")
    
    return "\n".join(result)

def build_detailed_prompt(data: ReportRequest) -> str:
    """Alternative detailed prompt for advanced reports"""
    return f"""
أنت مستشار تربوي محترف مع خبرة 20 عاماً في مجال التعليم.

**مهمتك:** كتابة تقرير {data.report_type} احترافي متكامل.

**البيانات المدخلة:**
- نوع التقرير: {data.report_type}
- المادة: {data.subject}
- الموضوع: {data.lesson}
- الصف: {data.grade}
- المستهدف: {data.target}
- المكان: {data.place}
- العدد: {data.count}
- معلومات إضافية: {data.additional_info}

**متطلبات التقرير:**
1. البداية بتعريف مختصر للسياق التعليمي
2. تحليل احتياجات الفئة المستهدفة
3. تصميم الأنشطة والاستراتيجيات المناسبة
4. آليات التنفيذ العملية
5. معايير التقييم والقياس
6. آليات المتابعة والتطوير
7. الخلاصة والتوصيات التنفيذية

**معايير الجودة:**
- اللغة العربية الفصحى
- الترابط المنطقي بين الأجزاء
- التوازن بين النظرية والتطبيق
- مراعاة الفروق الفردية
- اقتراحات قابلة للتنفيذ
- الابتكار والتجديد

**التنسيق النهائي:**
كل نقطة يجب أن تحتوي على:
• الفكرة الرئيسية
• التطبيق العملي
• المؤشرات القابلة للقياس
• الزمن المقترح (إن وجد)
"""

def build_arabic_only_prompt(data: ReportRequest) -> str:
    """Prompt for Arabic language reports only"""
    return f"""
أنت خبير تربوي عربي متخصص في صياغة التقارير التعليمية باللغة العربية الفصحى.

**التفاصيل:**
• نوع التقرير: {data.report_type}
• المادة الدراسية: {data.subject}
• الموضوع: {data.lesson}
• الصف الدراسي: {data.grade}

**المطلوب:** كتابة تقرير عربي متكامل يشمل:

١. المقدمة التربوية
٢. الأهداف التعليمية (المعرفية - المهارية - الوجدانية)
٣. المحتوى التعليمي
٤. الاستراتيجيات التدريسية
٥. الأنشطة التعليمية
٦. التقويم والقياس
٧. التوصيات التطويرية

**شروط الكتابة:**
• استخدام اللغة العربية الفصحى السليمة
• تجنب المصطلحات الأجنبية
• الاعتماد على المصطلحات التربوية العربية
• الوضوح والإيجاز
• التدرج المنطقي في العرض
• ربط المحتوى بالواقع التعليمي
"""

# =====================================================
# ROUTES
# =====================================================
@app.get("/")
def health():
    return {"status": "ok", "time": datetime.datetime.utcnow().isoformat()}

@app.get("/health")
def health_check():
    """Comprehensive health check"""
    return {
        "status": "healthy",
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "gemini_keys": len(GEMINI_KEYS),
        "valid_codes": len(VALID_CODES),
        "service": "educational-ai-backend"
    }

# -----------------------------------------------------
# Generate activation code with different periods (admin)
# -----------------------------------------------------
@app.get("/generate-code")
def generate_code(
    key: str = Query(..., description="Admin key"),
    period: ValidityPeriod = Query(ValidityPeriod.ONE_MONTH, description="Validity period"),
    custom_days: Optional[int] = Query(None, ge=1, le=365, description="Custom days if period=custom")
):
    if key != ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="Forbidden")

    code = generate_short_code()
    code_hash = hash_code(code)
    
    # Calculate expiration based on period
    expiry = calculate_expiration(period.value, custom_days)
    VALID_CODES[code_hash] = expiry

    # Clean expired codes
    cleanup_expired_codes()

    return {
        "activation_code": code,
        "expires_at": expiry.isoformat(),
        "period": period.value,
        "period_name": get_duration_name(period.value),
        "expires_in_days": (expiry - datetime.datetime.utcnow()).days,
        "message": "Code generated successfully"
    }

# -----------------------------------------------------
# Activate
# -----------------------------------------------------
@app.post("/activate")
def activate(data: ActivateRequest):
    code_hash = hash_code(data.code.strip().upper())
    expiry = VALID_CODES.get(code_hash)

    if not expiry:
        raise HTTPException(status_code=403, detail="Invalid code")

    if expiry < datetime.datetime.utcnow():
        VALID_CODES.pop(code_hash, None)
        raise HTTPException(status_code=403, detail="Code expired")

    payload = {
        "type": "activation",
        "exp": expiry,
        "iat": datetime.datetime.utcnow(),
        "jti": secrets.token_hex(8)
    }

    token = jwt.encode(payload, JWT_SECRET, algorithm="HS256")
    
    # Remove used code
    VALID_CODES.pop(code_hash, None)
    
    return {
        "token": token,
        "expires_at": expiry.isoformat(),
        "expires_in_seconds": int((expiry - datetime.datetime.utcnow()).total_seconds())
    }

# -----------------------------------------------------
# Verify
# -----------------------------------------------------
@app.get("/verify")
def verify(x_token: str = Header(..., alias="X-Token")):
    verify_jwt(x_token)
    return {"status": "ok"}

# -----------------------------------------------------
# Legacy generate
# -----------------------------------------------------
@app.post("/generate")
def generate(data: AskRequest, x_token: str = Header(..., alias="X-Token")):
    verify_jwt(x_token)
    model = pick_gemini_model()
    response = model.generate_content(data.prompt)
    return {"answer": response.text}

# -----------------------------------------------------
# Educational report (NEW)
# -----------------------------------------------------
@app.post("/generate-report")
def generate_report(data: ReportRequest, x_token: str = Header(..., alias="X-Token")):
    verify_jwt(x_token)
    model = pick_gemini_model()
    
    # Choose prompt based on report type
    if data.report_type in ["تحضير درس", "درس"]:
        prompt = build_educational_prompt(data)
    elif "عربي" in data.subject or "لغة عربية" in data.subject:
        prompt = build_arabic_only_prompt(data)
    else:
        prompt = build_detailed_prompt(data)
    
    response = model.generate_content(prompt)
    
    return {
        "answer": post_process_response(response.text),
        "report_type": data.report_type,
        "generated_at": datetime.datetime.utcnow().isoformat(),
        "prompt_used": "detailed" if "detailed" in locals() else "standard"
    }

# -----------------------------------------------------
# v2 compatible endpoint (FRONTEND USES THIS)
# -----------------------------------------------------
@app.post("/v2/generate")
def generate_v2(data: dict, x_token: str = Header(..., alias="X-Token")):
    verify_jwt(x_token)

    if "report_type" in data:
        # Handle report generation
        try:
            report = ReportRequest(**data)
            prompt = build_educational_prompt(report)
            model = pick_gemini_model()
            response = model.generate_content(prompt)
            
            return {
                "answer": post_process_response(response.text),
                "status": "success",
                "report_type": report.report_type
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error generating report: {str(e)}")
    
    # Handle generic prompt
    prompt = data.get("prompt", "")
    if not prompt:
        raise HTTPException(status_code=400, detail="No prompt provided")

    model = pick_gemini_model()
    response = model.generate_content(prompt)
    return {"answer": response.text}

# -----------------------------------------------------
# Advanced report with prompt selection
# -----------------------------------------------------
@app.post("/advanced-report")
def advanced_report(
    data: ReportRequest,
    prompt_type: str = Query("standard", description="Prompt type: standard, detailed, or arabic"),
    x_token: str = Header(..., alias="X-Token")
):
    verify_jwt(x_token)
    model = pick_gemini_model()
    
    # Select prompt based on type
    if prompt_type == "detailed":
        prompt = build_detailed_prompt(data)
    elif prompt_type == "arabic":
        prompt = build_arabic_only_prompt(data)
    else:
        prompt = build_educational_prompt(data)
    
    response = model.generate_content(prompt)
    
    return {
        "answer": response.text,
        "report_type": data.report_type,
        "prompt_type": prompt_type,
        "generated_at": datetime.datetime.utcnow().isoformat()
    }

# -----------------------------------------------------
# List active codes (admin only)
# -----------------------------------------------------
@app.get("/admin/codes")
def list_codes(key: str = Query(..., description="Admin key")):
    if key != ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="Forbidden")
    
    cleanup_expired_codes()
    
    codes = []
    for code_hash, expiry in VALID_CODES.items():
        codes.append({
            "code_hash_short": code_hash[:12] + "...",
            "expires_at": expiry.isoformat(),
            "remaining_days": (expiry - datetime.datetime.utcnow()).days
        })
    
    return {
        "total_codes": len(codes),
        "codes": codes
    }

# -----------------------------------------------------
# Cleanup function
# -----------------------------------------------------
def cleanup_expired_codes():
    """Remove expired codes from memory"""
    now = datetime.datetime.utcnow()
    expired = []
    
    for code_hash, expiry in list(VALID_CODES.items()):
        if expiry < now:
            expired.append(code_hash)
            VALID_CODES.pop(code_hash, None)
    
    if expired:
        print(f"Cleaned up {len(expired)} expired codes")

# -----------------------------------------------------
# Get system info
# -----------------------------------------------------
@app.get("/system/info")
def system_info():
    """Get system information"""
    return {
        "service": "Educational AI Backend",
        "version": "2.0.0",
        "gemini_keys_available": len(GEMINI_KEYS),
        "supported_report_types": [rt.value for rt in ReportType],
        "supported_periods": [vp.value for vp in ValidityPeriod],
        "timestamp": datetime.datetime.utcnow().isoformat()
    }

# =====================================================
# MAIN
# =====================================================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=10000)