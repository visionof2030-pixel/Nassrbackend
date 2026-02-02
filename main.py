from fastapi import FastAPI, Query, HTTPException, Header, Body
from enum import Enum
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
import secrets
import os
import random
import hashlib
import jwt
import google.generativeai as genai
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

# تحميل متغيرات البيئة من ملف .env
load_dotenv()

app = FastAPI(title="نظام التقارير التربوية الذكي", version="2.0.0")

# ==================== إعدادات CORS ====================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # مؤقتاً اسمح للجميع
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==================== تعريفات Enum ====================
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

# ==================== إعدادات الأمان ====================
# الحصول على المفاتيح من متغيرات البيئة
JWT_SECRET = os.getenv("JWT_SECRET", "your-jwt-secret-key-change-in-production")
ADMIN_KEY = os.getenv("ADMIN_KEY", "FahadJassar14061436")  # يمكن تغييره لاحقاً

# 7 مفاتيح Gemini مع تقنية Round Robin
GEMINI_KEYS = [
    os.getenv("GEMINI_API_KEY_1"),
    os.getenv("GEMINI_API_KEY_2"),
    os.getenv("GEMINI_API_KEY_3"),
    os.getenv("GEMINI_API_KEY_4"),
    os.getenv("GEMINI_API_KEY_5"),
    os.getenv("GEMINI_API_KEY_6"),
    os.getenv("GEMINI_API_KEY_7"),
]

# تصفية المفاتيح الفارغة
GEMINI_KEYS = [k for k in GEMINI_KEYS if k]

if not GEMINI_KEYS:
    print("⚠️  تحذير: لم يتم العثور على مفاتيح Gemini API، سيتم استخدام الردود الافتراضية")
    GEMINI_AVAILABLE = False
else:
    print(f"✅ تم تحميل {len(GEMINI_KEYS)} مفاتيح Gemini API")
    GEMINI_AVAILABLE = True

# ==================== نماذج البيانات ====================
class ActivationRequest(BaseModel):
    code: str

class GenerateReportRequest(BaseModel):
    report_type: ReportType
    subject: Optional[str] = ""
    lesson: Optional[str] = ""
    grade: Optional[str] = ""
    target: Optional[str] = ""
    place: Optional[str] = ""
    count: Optional[str] = ""
    additional_info: Optional[str] = ""

# ==================== تخزين مؤقت (للتطوير) ====================
VALID_CODES: Dict[str, datetime] = {}  # تخزين الأكواد: {hash: expiry}
ACTIVATED_TOKENS: Dict[str, datetime] = {}  # تخزين التوكنات: {token: expiry}

# ==================== دوال مساعدة ====================
def calculate_expiration(period: str, custom_days: Optional[int] = None) -> datetime:
    """حساب تاريخ انتهاء الصلاحية"""
    now = datetime.utcnow()
    
    if period == ValidityPeriod.THIRTY_MINUTES.value:
        return now + timedelta(minutes=30)
    elif period == ValidityPeriod.ONE_HOUR.value:
        return now + timedelta(hours=1)
    elif period == ValidityPeriod.ONE_DAY.value:
        return now + timedelta(days=1)
    elif period == ValidityPeriod.ONE_WEEK.value:
        return now + timedelta(weeks=1)
    elif period == ValidityPeriod.ONE_MONTH.value:
        return now + timedelta(days=30)
    elif period == ValidityPeriod.CUSTOM.value and custom_days:
        return now + timedelta(days=custom_days)
    else:
        return now + timedelta(days=30)  # الافتراضي شهر

def get_duration_name(period: str) -> str:
    """الحصول على اسم المدة بالعربية"""
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

def hash_code(code: str) -> str:
    """تجزئة الكود للتخزين الآمن"""
    return hashlib.sha256(code.encode()).hexdigest()

def generate_jwt_token(expiry_days: int = 30) -> str:
    """توليد توكن JWT"""
    payload = {
        "type": "activation",
        "exp": datetime.utcnow() + timedelta(days=expiry_days),
        "iat": datetime.utcnow(),
        "jti": secrets.token_hex(8)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")

def verify_jwt_token(token: str) -> Dict[str, Any]:
    """التحقق من صحة توكن JWT"""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        if payload.get("type") != "activation":
            raise HTTPException(status_code=401, detail="نوع التوكن غير صحيح")
        
        # التحقق من وجود التوكن في القائمة النشطة
        if token not in ACTIVATED_TOKENS:
            raise HTTPException(status_code=401, detail="التوكن غير مفعل أو منتهي")
        
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="انتهت صلاحية التوكن")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="التوكن غير صالح")

def pick_gemini_model():
    """اختيار مفتاح Gemini عشوائيًا وتكوين النموذج"""
    if not GEMINI_AVAILABLE:
        return None
    
    try:
        key = random.choice(GEMINI_KEYS)
        genai.configure(api_key=key)
        
        # إعدادات توليد النص
        generation_config = {
            "temperature": 0.7,
            "top_p": 0.9,
            "top_k": 40,
            "max_output_tokens": 2048,
        }
        
        # إعدادات السلامة
        safety_settings = [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
        ]
        
        # استخدام أحدث موديل من Gemini
        return genai.GenerativeModel(
            model_name="gemini-1.5-pro",  # يمكن تغييره إلى "gemini-2.0-flash" أو "gemini-1.5-flash"
            generation_config=generation_config,
            safety_settings=safety_settings
        )
    except Exception as e:
        print(f"❌ خطأ في تهيئة Gemini: {e}")
        return None

def generate_ai_report(prompt: str) -> str:
    """توليد تقرير باستخدام Gemini AI"""
    model = pick_gemini_model()
    
    if not model:
        # الرد الافتراضي إذا لم يتوفر Gemini
        return """
        ### تقرير تربوي
        (هذا رد افتراضي، يرجى إضافة مفاتيح Gemini API لاستخدام الذكاء الاصطناعي)
        
        1. الهدف التربوي: تطوير المهارات التعليمية
        2. النبذة المختصرة: تم تنفيذ النشاط التعليمي بنجاح
        3. إجراءات التنفيذ: استخدام استراتيجيات تعليمية متنوعة
        4. الاستراتيجيات: التعلم النشط، التعاوني، التفكير الناقد
        5. نقاط القوة: تفاعل الطلاب، تنوع الأنشطة
        6. نقاط التحسين: زيادة وقت الممارسة العملية
        7. التوصيات: الاستمرار في تطوير المهارات التعليمية
        """
    
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        print(f"❌ خطأ في توليد التقرير: {e}")
        return f"حدث خطأ أثناء توليد التقرير: {str(e)}"

# ==================== نقاط النهاية ====================

@app.get("/")
def root():
    """صفحة الترحيب"""
    return {
        "message": "مرحباً بك في نظام التقارير التربوية الذكي",
        "version": "2.0.0",
        "status": "متصل",
        "timestamp": datetime.utcnow().isoformat(),
        "features": ["تفعيل الأكواد", "توليد التقارير", "ذكاء اصطناعي"],
        "gemini_available": GEMINI_AVAILABLE,
        "gemini_keys_count": len(GEMINI_KEYS) if GEMINI_AVAILABLE else 0
    }

@app.get("/health")
def health_check():
    """فحص صحة النظام"""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "valid_codes": len(VALID_CODES),
        "active_tokens": len(ACTIVATED_TOKENS)
    }

@app.get("/generate-code")
def generate_code_endpoint(
    key: str = Query(..., description="المفتاح الإداري"),
    period: ValidityPeriod = Query(
        ValidityPeriod.ONE_MONTH,
        description="مدة صلاحية كود التفعيل"
    ),
    custom_days: Optional[int] = Query(
        None,
        ge=1,
        le=365,
        description="عدد الأيام المخصص (إذا كانت period = custom)"
    )
):
    """توليد كود تفعيل جديد (للمشرفين فقط)"""
    # التحقق من المفتاح الإداري
    if key != ADMIN_KEY:
        raise HTTPException(status_code=401, detail="المفتاح الإداري غير صحيح")
    
    # توليد كود عشوائي (6 أحرف)
    code = secrets.token_hex(3).upper()  # مثل: A1B2C3
    
    # حساب تاريخ الانتهاء
    expires_at = calculate_expiration(period.value, custom_days)
    
    # تخزين الكود (بتجزئة)
    code_hash = hash_code(code)
    VALID_CODES[code_hash] = expires_at
    
    # تنظيف الأكواد المنتهية
    cleanup_expired_codes()
    
    return {
        "code": code,
        "period": period.value,
        "period_name": get_duration_name(period.value),
        "expires_at": expires_at.isoformat(),
        "expires_in_days": (expires_at - datetime.utcnow()).days,
        "message": "تم توليد الكود بنجاح"
    }

@app.post("/activate")
def activate_endpoint(request: ActivationRequest):
    """تفعيل النظام باستخدام الكود"""
    code = request.code.strip().upper()
    
    if not code:
        raise HTTPException(status_code=400, detail="يرجى إدخال كود التفعيل")
    
    # تجزئة الكود والتحقق
    code_hash = hash_code(code)
    
    if code_hash not in VALID_CODES:
        raise HTTPException(status_code=404, detail="كود التفعيل غير صحيح")
    
    expires_at = VALID_CODES[code_hash]
    
    # التحقق من انتهاء الصلاحية
    if datetime.utcnow() > expires_at:
        # حذف الكود المنتهي
        VALID_CODES.pop(code_hash, None)
        raise HTTPException(status_code=410, detail="انتهت صلاحية الكود")
    
    # توليد توكن JWT
    token = generate_jwt_token()
    
    # تخزين التوكن النشط
    ACTIVATED_TOKENS[token] = expires_at
    
    # حذف الكود بعد الاستخدام (للاستخدام لمرة واحدة)
    VALID_CODES.pop(code_hash, None)
    
    return {
        "token": token,
        "expires_at": expires_at.isoformat(),
        "expires_in_seconds": int((expires_at - datetime.utcnow()).total_seconds()),
        "message": "تم التفعيل بنجاح"
    }

@app.post("/generate-report")
def generate_report_endpoint(
    request: GenerateReportRequest,
    x_token: str = Header(..., alias="X-Token", description="توكن التفعيل")
):
    """توليد تقرير باستخدام الذكاء الاصطناعي"""
    # التحقق من التوكن
    token_data = verify_jwt_token(x_token)
    
    # بناء الـ Prompt للتقرير
    prompt = f"""
    مطلوب كتابة تقرير تربوي احترافي باللغة العربية الفصحى.
    
    نوع التقرير: {request.report_type}
    المادة الدراسية: {request.subject if request.subject else 'غير محدد'}
    الدرس/الموضوع: {request.lesson if request.lesson else 'غير محدد'}
    الصف/المستوى: {request.grade if request.grade else 'غير محدد'}
    الهدف: {request.target if request.target else 'غير محدد'}
    المكان: {request.place if request.place else 'غير محدد'}
    عدد المشاركين: {request.count if request.count else 'غير محدد'}
    معلومات إضافية: {request.additional_info if request.additional_info else 'لا يوجد'}
    
    يرجى كتابة التقرير باحترافية مع تضمين النقاط التالية:
    1. الهدف التربوي
    2. النبذة المختصرة
    3. إجراءات التنفيذ
    4. الاستراتيجيات المستخدمة
    5. نقاط القوة
    6. نقاط التحسين
    7. التوصيات
    8. النتائج المتوقعة
    
    اجعل التقرير واضحاً، منطقياً، ومفيداً للمستفيدين.
    """
    
    # توليد التقرير باستخدام الذكاء الاصطناعي
    ai_response = generate_ai_report(prompt)
    
    return {
        "report": ai_response,
        "report_type": request.report_type,
        "generated_at": datetime.utcnow().isoformat(),
        "token_expires_at": token_data.get("exp"),
        "status": "success"
    }

@app.get("/verify-token")
def verify_token_endpoint(
    x_token: str = Header(..., alias="X-Token", description="توكن التفعيل")
):
    """التحقق من صحة التوكن"""
    token_data = verify_jwt_token(x_token)
    
    return {
        "valid": True,
        "expires_at": token_data.get("exp"),
        "token_type": token_data.get("type"),
        "message": "التوكن صالح"
    }

@app.get("/admin/codes-list")
def list_codes_endpoint(
    key: str = Query(..., description="المفتاح الإداري")
):
    """عرض قائمة الأكواد النشطة (للمشرفين فقط)"""
    if key != ADMIN_KEY:
        raise HTTPException(status_code=401, detail="المفتاح الإداري غير صحيح")
    
    cleanup_expired_codes()
    
    codes_list = []
    for code_hash, expiry in VALID_CODES.items():
        codes_list.append({
            "code_hash": code_hash[:10] + "...",  # إظهار جزء فقط للأمان
            "expires_at": expiry.isoformat(),
            "remaining_days": (expiry - datetime.utcnow()).days
        })
    
    return {
        "total_codes": len(codes_list),
        "codes": codes_list
    }

def cleanup_expired_codes():
    """تنظيف الأكواد والتوكنات المنتهية"""
    now = datetime.utcnow()
    
    # تنظيف الأكواد
    expired_codes = [
        code_hash for code_hash, expiry in VALID_CODES.items()
        if expiry < now
    ]
    for code_hash in expired_codes:
        VALID_CODES.pop(code_hash, None)
    
    # تنظيف التوكنات
    expired_tokens = [
        token for token, expiry in ACTIVATED_TOKENS.items()
        if expiry < now
    ]
    for token in expired_tokens:
        ACTIVATED_TOKENS.pop(token, None)
    
    if expired_codes or expired_tokens:
        print(f"✅ تم تنظيف {len(expired_codes)} كود و{len(expired_tokens)} توكن منتهي")

# ==================== تشغيل الخادم ====================
if __name__ == "__main__":
    import uvicorn
    print("🚀 بدء تشغيل نظام التقارير التربوية الذكي...")
    print(f"🔑 المفاتيح المتاحة: {len(GEMINI_KEYS)}")
    print(f"🔐 المفتاح الإداري: {ADMIN_KEY}")
    uvicorn.run(app, host="0.0.0.0", port=8000)