from fastapi import FastAPI, Query, HTTPException
from enum import Enum
from typing import Optional
from datetime import datetime, timedelta
import secrets

app = FastAPI()

# ==================== تعريف enum جديد للمدة ====================
class ValidityPeriod(str, Enum):
    THIRTY_MINUTES = "30m"
    ONE_HOUR = "1h"
    ONE_DAY = "1d"
    ONE_WEEK = "1w"
    ONE_MONTH = "30d"

# ==================== دالة حساب الانتهاء ====================
def calculate_expiration(period: str, custom_days: Optional[int] = None) -> datetime:
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
    elif custom_days:
        return now + timedelta(days=custom_days)
    else:
        # Default to one month
        return now + timedelta(days=30)

# ==================== Endpoint لتوليد الأكواد ====================
@app.get("/generate-code")
def generate_code(
    key: str,
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
    # المفتاح الإداري الثابت
    ADMIN_KEY = "FahadJassar14061436"
    
    # التحقق من المفتاح
    if key != ADMIN_KEY:
        raise HTTPException(status_code=401, detail="المفتاح غير صحيح")
    
    # توليد كود عشوائي
    code = secrets.token_hex(8)
    
    # حساب تاريخ الانتهاء
    expires_at = calculate_expiration(period.value, custom_days)
    
    # حساب المدة بالثواني للإشعارات
    now = datetime.utcnow()
    expires_in_seconds = int((expires_at - now).total_seconds())
    
    # إرجاع النتيجة
    return {
        "code": code,
        "period": period.value,
        "expires_at": expires_at.isoformat(),
        "expires_in_seconds": expires_in_seconds,
        "duration_name": get_duration_name(period.value)
    }

# ==================== Endpoint للتفعيل ====================
@app.post("/activate")
def activate(code: str):
    # هذا مجرد مثال - يجب أن يكون لديك قاعدة بيانات هنا
    # للتحقق من صحة الكود وتاريخ انتهائه
    
    # محاكاة قاعدة بيانات مؤقتة
    CODES_DB = {
        "12345678": {
            "expires_at": "2024-12-31T23:59:59",
            "period": "30d"
        }
    }
    
    if code not in CODES_DB:
        raise HTTPException(status_code=404, detail="كود التفعيل غير صحيح")
    
    item = CODES_DB[code]
    expires_at = datetime.fromisoformat(item["expires_at"])
    now = datetime.utcnow()
    
    if now > expires_at:
        raise HTTPException(status_code=410, detail="انتهت صلاحية الكود")
    
    # توليد توكن
    token = secrets.token_hex(32)
    
    return {
        "token": token,
        "expires_at": expires_at.isoformat(),
        "expires_in_seconds": int((expires_at - now).total_seconds()),
        "duration": item["period"]
    }

# ==================== دالة مساعدة للحصول على اسم المدة ====================
def get_duration_name(period: str) -> str:
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
    else:
        return "غير محدد"

# ==================== Endpoint لتوليد التقارير ====================
@app.post("/generate-report")
def generate_report(
    report_type: str,
    subject: str = "",
    lesson: str = "",
    grade: str = "",
    target: str = "",
    place: str = "",
    count: str = "",
    x_token: Optional[str] = None
):
    # التحقق من التوكن
    if not x_token:
        raise HTTPException(status_code=401, detail="مطلوب توكن التفعيل")
    
    # هنا يمكنك إضافة منطق الذكاء الاصطناعي
    # محاكاة استجابة
    ai_response = f"""
1. الهدف التربوي: فهم {report_type} في مادة {subject}
2. النبذة المختصرة: تم تنفيذ {report_type} للصف {grade}
3. إجراءات التنفيذ: شرح {lesson} باستخدام استراتيجيات متنوعة
4. الاستراتيجيات: التعلم النشط، التعاوني، التفكير الناقد
5. نقاط القوة: تفاعل الطلاب، استخدام الوسائل التعليمية
6. نقاط التحسين: زيادة وقت الممارسة العملية
7. التوصيات: الاستمرار في تطوير المهارات العملية
"""
    
    return {
        "answer": ai_response,
        "status": "success",
        "report_type": report_type
    }