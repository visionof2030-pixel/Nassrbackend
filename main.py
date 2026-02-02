from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from enum import Enum
from datetime import datetime, timedelta
import secrets
import json
import logging
from fastapi.middleware.cors import CORSMiddleware

# ==================== الإعدادات الأولية ====================
app = FastAPI(
    title="API تفعيل أداة التقارير التربوية",
    description="API لإدارة تفعيل أداة إصدار التقارير التربوية للمعلمين",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# إعدادات CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # في الإنتاج، ضع الروابط المسموحة فقط
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# إعدادات التسجيل
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ==================== الأنماط (Enums) ====================
class ValidityPeriod(str, Enum):
    """فترات الصلاحية المتاحة"""
    THIRTY_MINUTES = "30m"
    ONE_HOUR = "1h"
    ONE_DAY = "1d"
    ONE_WEEK = "1w"
    ONE_MONTH = "30d"

# ==================== النماذج (Models) ====================
class GenerateCodeRequest(BaseModel):
    key: str
    period: ValidityPeriod = ValidityPeriod.ONE_MONTH
    custom_days: Optional[int] = None

class ActivateRequest(BaseModel):
    code: str

class ActivationResponse(BaseModel):
    token: str
    expires_at: str
    expires_in_seconds: int
    duration: str

class GenerateCodeResponse(BaseModel):
    code: str
    expires_at: str
    expires_in_seconds: int
    duration: str
    message: str

class TokenValidationResponse(BaseModel):
    valid: bool
    expires_at: str
    expires_in_seconds: int
    duration: str
    activated_at: str

# ==================== دوال المساعدة ====================
def calculate_expiration(period: str, custom_days: Optional[int] = None) -> tuple:
    """حساب وقت الانتهاء بناءً على المدة المحددة"""
    now = datetime.utcnow()
    
    if custom_days and custom_days > 0:
        # فترة مخصصة بالأيام
        expires_at = now + timedelta(days=custom_days)
        expires_in_seconds = custom_days * 24 * 3600
        duration = f"{custom_days}d"
    else:
        # فترات محددة مسبقاً
        if period == "30m":
            expires_at = now + timedelta(minutes=30)
            expires_in_seconds = 30 * 60
            duration = "30m"
        elif period == "1h":
            expires_at = now + timedelta(hours=1)
            expires_in_seconds = 3600
            duration = "1h"
        elif period == "1d":
            expires_at = now + timedelta(days=1)
            expires_in_seconds = 24 * 3600
            duration = "1d"
        elif period == "1w":
            expires_at = now + timedelta(weeks=1)
            expires_in_seconds = 7 * 24 * 3600
            duration = "1w"
        elif period == "30d":
            expires_at = now + timedelta(days=30)
            expires_in_seconds = 30 * 24 * 3600
            duration = "30d"
        else:
            # افتراضي: شهر
            expires_at = now + timedelta(days=30)
            expires_in_seconds = 30 * 24 * 3600
            duration = "30d"
    
    return expires_at, expires_in_seconds, duration

def generate_secure_code() -> str:
    """إنشاء كود تفعيل آمن"""
    # توليد كود عشوائي 16 حرف
    code = secrets.token_urlsafe(12).upper().replace('-', '').replace('_', '')[:16]
    # تأكد من أن الكود يحتوي على أرقام وحروف فقط
    return ''.join(c for c in code if c.isalnum())

# ==================== التخزين (في الذاكرة) ====================
# في الإنتاج، استخدم قاعدة بيانات حقيقية
activation_codes = {}
activated_tokens = {}

# المفتاح الإداري - في الإنتاج خزنه في متغير بيئة
ADMIN_KEY = "teacher_tool_2024_secret_key"

# ==================== النقاط الطرفية (Endpoints) ====================
@app.get("/generate-code", response_model=GenerateCodeResponse)
def generate_code(
    key: str,
    period: ValidityPeriod = Query(
        ValidityPeriod.ONE_MONTH,
        description="مدة صلاحية كود التفعيل",
        examples={
            "30m": {"summary": "30 دقيقة", "value": "30m"},
            "1h": {"summary": "ساعة واحدة", "value": "1h"},
            "1d": {"summary": "يوم واحد", "value": "1d"},
            "1w": {"summary": "أسبوع واحد", "value": "1w"},
            "30d": {"summary": "شهر واحد", "value": "30d"}
        }
    ),
    custom_days: Optional[int] = Query(
        None,
        description="عدد الأيام المخصصة (اختياري)",
        ge=1,
        le=365
    )
):
    """
    إنشاء كود تفعيل جديد
    
    **المعلمات:**
    - `key`: المفتاح الإداري للتحقق
    - `period`: مدة صلاحية الكود (القيم المسموحة: 30m, 1h, 1d, 1w, 30d)
    - `custom_days`: عدد أيام مخصص (اختياري، من 1 إلى 365)
    
    **المدة الافتراضية:** 30d (شهر واحد)
    """
    
    # التحقق من المفتاح الإداري
    if key != ADMIN_KEY:
        logger.warning(f"محاولة وصول بمفتاح خاطئ: {key}")
        raise HTTPException(status_code=401, detail="مفتاح إداري غير صحيح")
    
    # إنشاء كود جديد
    code = generate_secure_code()
    expires_at, expires_in_seconds, duration = calculate_expiration(period.value, custom_days)
    
    # تخزين الكود
    activation_codes[code] = {
        "expires_at": expires_at.isoformat(),
        "expires_in_seconds": expires_in_seconds,
        "duration": duration,
        "created_at": datetime.utcnow().isoformat(),
        "used": False,
        "period": period.value,
        "custom_days": custom_days
    }
    
    logger.info(f"تم إنشاء كود جديد: {code} - المدة: {duration}")
    
    return GenerateCodeResponse(
        code=code,
        expires_at=expires_at.isoformat(),
        expires_in_seconds=expires_in_seconds,
        duration=duration,
        message="تم إنشاء كود التفعيل بنجاح"
    )

@app.post("/activate", response_model=ActivationResponse)
def activate(request: ActivateRequest):
    """
    تفعيل كود التفعيل
    
    **المعلمات:**
    - `code`: كود التفعيل (16 حرف)
    """
    code = request.code.upper().strip()
    
    # التحقق من تنسيق الكود
    if len(code) != 16 or not code.isalnum():
        raise HTTPException(status_code=400, detail="تنسيق كود التفعيل غير صحيح")
    
    # التحقق من وجود الكود
    if code not in activation_codes:
        logger.warning(f"محاولة تفعيل كود غير موجود: {code}")
        raise HTTPException(status_code=404, detail="كود التفعيل غير صحيح")
    
    code_data = activation_codes[code]
    
    # التحقق من استخدام الكود سابقاً
    if code_data["used"]:
        raise HTTPException(status_code=400, detail="كود التفعيل مستخدم سابقاً")
    
    # التحقق من صلاحية الكود
    expires_at = datetime.fromisoformat(code_data["expires_at"])
    if datetime.utcnow() > expires_at:
        raise HTTPException(status_code=400, detail="كود التفعيل منتهي الصلاحية")
    
    # إنشاء توكن آمن
    token = secrets.token_urlsafe(32)
    
    # تخزين التوكن
    activated_tokens[token] = {
        "code": code,
        "activated_at": datetime.utcnow().isoformat(),
        "expires_at": expires_at.isoformat(),
        "expires_in_seconds": code_data["expires_in_seconds"],
        "duration": code_data["duration"],
        "period": code_data["period"]
    }
    
    # وضع علامة على الكود كمستخدم
    activation_codes[code]["used"] = True
    activation_codes[code]["used_at"] = datetime.utcnow().isoformat()
    activation_codes[code]["activated_token"] = token[:10] + "..."  # تخزين جزء من التوكن للرجوع
    
    logger.info(f"تم تفعيل الكود: {code} - التوكن: {token[:10]}...")
    
    return ActivationResponse(
        token=token,
        expires_at=expires_at.isoformat(),
        expires_in_seconds=code_data["expires_in_seconds"],
        duration=code_data["duration"]
    )

@app.get("/validate-token", response_model=TokenValidationResponse)
def validate_token(token: str):
    """
    التحقق من صلاحية التوكن
    
    **المعلمات:**
    - `token`: التوكن للتحقق
    """
    if token not in activated_tokens:
        raise HTTPException(status_code=404, detail="التوكن غير صحيح")
    
    token_data = activated_tokens[token]
    expires_at = datetime.fromisoformat(token_data["expires_at"])
    
    if datetime.utcnow() > expires_at:
        raise HTTPException(status_code=400, detail="التوكن منتهي الصلاحية")
    
    return TokenValidationResponse(
        valid=True,
        expires_at=expires_at.isoformat(),
        expires_in_seconds=token_data["expires_in_seconds"],
        duration=token_data["duration"],
        activated_at=token_data["activated_at"]
    )

@app.get("/check-code/{code}")
def check_code(code: str):
    """
    التحقق من حالة كود التفعيل
    
    **المعلمات:**
    - `code`: كود التفعيل للتحقق
    """
    code = code.upper().strip()
    
    if code not in activation_codes:
        raise HTTPException(status_code=404, detail="الكود غير موجود")
    
    code_data = activation_codes[code]
    expires_at = datetime.fromisoformat(code_data["expires_at"])
    
    # تحديد الحالة
    status = "active"
    if code_data["used"]:
        status = "used"
    elif datetime.utcnow() > expires_at:
        status = "expired"
    
    return {
        "code": code,
        "status": status,
        "expires_at": expires_at.isoformat(),
        "expires_in_seconds": code_data["expires_in_seconds"],
        "duration": code_data["duration"],
        "period": code_data["period"],
        "created_at": code_data["created_at"],
        "used": code_data["used"],
        "used_at": code_data.get("used_at"),
        "custom_days": code_data.get("custom_days")
    }

@app.get("/stats")
def get_stats():
    """
    الحصول على إحصائيات النظام
    """
    total_codes = len(activation_codes)
    used_codes = sum(1 for code in activation_codes.values() if code["used"])
    active_codes = total_codes - used_codes
    expired_codes = sum(1 for code in activation_codes.values() 
                       if datetime.fromisoformat(code["expires_at"]) < datetime.utcnow())
    
    total_tokens = len(activated_tokens)
    active_tokens = sum(1 for token in activated_tokens.values()
                       if datetime.fromisoformat(token["expires_at"]) > datetime.utcnow())
    
    return {
        "codes": {
            "total": total_codes,
            "active": active_codes,
            "used": used_codes,
            "expired": expired_codes
        },
        "tokens": {
            "total": total_tokens,
            "active": active_tokens,
            "expired": total_tokens - active_tokens
        },
        "periods_distribution": {
            "30m": sum(1 for code in activation_codes.values() if code.get("period") == "30m"),
            "1h": sum(1 for code in activation_codes.values() if code.get("period") == "1h"),
            "1d": sum(1 for code in activation_codes.values() if code.get("period") == "1d"),
            "1w": sum(1 for code in activation_codes.values() if code.get("period") == "1w"),
            "30d": sum(1 for code in activation_codes.values() if code.get("period") == "30d")
        }
    }

@app.post("/generate-report")
def generate_report(
    report_type: str,
    subject: Optional[str] = None,
    lesson: Optional[str] = None,
    grade: Optional[str] = None,
    target: Optional[str] = None,
    place: Optional[str] = None,
    count: Optional[str] = None,
    token: Optional[str] = None
):
    """
    توليد تقرير باستخدام الذكاء الاصطناعي
    
    **المعلمات:**
    - `report_type`: نوع التقرير
    - `subject`: المادة (اختياري)
    - `lesson`: الدرس (اختياري)
    - `grade`: الصف (اختياري)
    - `target`: المستهدفون (اختياري)
    - `place`: مكان التنفيذ (اختياري)
    - `count`: العدد (اختياري)
    - `token`: توكن التفعيل (مطلوب للاستخدام الفعلي)
    """
    
    # في الإنتاج، تفعيل التحقق من التوكن
    if token:
        if token not in activated_tokens:
            raise HTTPException(status_code=401, detail="التوكن غير صحيح")
        
        token_data = activated_tokens[token]
        expires_at = datetime.fromisoformat(token_data["expires_at"])
        
        if datetime.utcnow() > expires_at:
            raise HTTPException(status_code=401, detail="التوكن منتهي الصلاحية")
    
    # محاكاة استجابة الذكاء الاصطناعي
    # في الإنتاج، استخدم نموذج AI حقيقي
    
    # محتوى افتراضي للتجربة
    ai_response = f"""
1. تم تنفيذ {report_type} بنجاح لطلاب {grade} في مادة {subject}.
2. تضمن النشاط شرح {lesson} باستخدام استراتيجيات تعليمية تفاعلية.
3. تم استخدام أدوات تعليمية متنوعة لتحقيق الأهداف التربوية.
4. تفاعل الطلاب بشكل إيجابي مع الأنشطة المقدمة.
5. حقق النشاط الأهداف المخطط لها بنسبة عالية.
6. يُوصى بتكرار النشاط مع توسيع نطاق التطبيق.
7. يمكن تحسين بعض الجوانب التقنية في التنفيذ المستقبلي.
"""
    
    # تقسيم المحتوى على الحقول
    lines = [line.strip() for line in ai_response.strip().split('\n') if line.strip()]
    
    response_content = {}
    for i, line in enumerate(lines[:7], 1):
        # إزالة الرقم من بداية السطر
        clean_line = line[3:] if line[0].isdigit() and line[1] in ['.', '-', ')'] else line
        response_content[str(i)] = clean_line.strip()
    
    logger.info(f"تم توليد تقرير: {report_type}")
    
    return {
        "report_type": report_type,
        "subject": subject,
        "lesson": lesson,
        "grade": grade,
        "target": target,
        "place": place,
        "count": count,
        "answer": ai_response,
        "parsed_content": response_content,
        "timestamp": datetime.utcnow().isoformat()
    }

@app.get("/")
def root():
    """الصفحة الرئيسية"""
    return {
        "message": "مرحباً بكم في API تفعيل أداة التقارير التربوية",
        "version": "2.0.0",
        "description": "نظام إدارة تفعيل أدوات المعلمين التعليمية",
        "endpoints": {
            "/docs": "واجهة Swagger التفاعلية",
            "/redoc": "واجهة ReDoc",
            "/generate-code": "إنشاء كود تفعيل",
            "/activate": "تفعيل كود",
            "/validate-token": "التحقق من التوكن",
            "/check-code/{code}": "التحقق من حالة الكود",
            "/generate-report": "توليد تقرير (AI)",
            "/stats": "إحصائيات النظام",
            "/health": "فحص صحة الخادم"
        },
        "developer": "فريق تطوير أدوات المعلمين",
        "contact": "iFahadenglish@gmail.com"
    }

@app.get("/health")
def health_check():
    """فحص صحة الخادم"""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "uptime": "running",
        "database": {
            "codes": len(activation_codes),
            "tokens": len(activated_tokens)
        }
    }

# ==================== نقطة البداية ====================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)