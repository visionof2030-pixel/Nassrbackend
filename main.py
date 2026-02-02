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
from typing import Optional, Dict, Any
from enum import Enum

# =====================================================
# ENV
# =====================================================
JWT_SECRET = os.getenv("JWT_SECRET")
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN")

if not JWT_SECRET or not ADMIN_TOKEN:
    raise RuntimeError("JWT_SECRET or ADMIN_TOKEN missing")

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
# ENUMS & CONSTANTS
# =====================================================
class ValidityPeriod(str, Enum):
    HALF_HOUR = "30m"
    ONE_HOUR = "1h"
    ONE_DAY = "1d"
    ONE_WEEK = "1w"
    ONE_MONTH = "30d"

VALIDITY_PERIODS = {
    ValidityPeriod.HALF_HOUR: {"name": "نصف ساعة", "minutes": 30},
    ValidityPeriod.ONE_HOUR: {"name": "ساعة واحدة", "hours": 1},
    ValidityPeriod.ONE_DAY: {"name": "يوم واحد", "days": 1},
    ValidityPeriod.ONE_WEEK: {"name": "أسبوع", "days": 7},
    ValidityPeriod.ONE_MONTH: {"name": "شهر", "days": 30},
}

# =====================================================
# MODELS
# =====================================================
class AskRequest(BaseModel):
    prompt: str

class ActivateRequest(BaseModel):
    code: str
    duration: str = "30d"  # القيمة الافتراضية: شهر

class ReportRequest(BaseModel):
    report_type: str
    subject: Optional[str] = ""
    lesson: Optional[str] = ""
    grade: Optional[str] = ""
    target: Optional[str] = ""
    place: Optional[str] = ""
    count: Optional[str] = ""

# =====================================================
# SIMPLE STORAGE (in-memory)
# =====================================================
VALID_CODES: Dict[str, Dict[str, Any]] = {}  # code_hash: {expires_at, period, created_at}

# =====================================================
# PROFESSIONAL PHRASES
# =====================================================
PROFESSIONAL_PHRASES = [
    'مع التركيز على تحقيق أهداف التعلم وتنمية المهارات الأساسية',
    'بما يسهم في رفع مستوى التحصيل الدراسي وتحسين المخرجات التعليمية',
    'وذلك لتحقيق التكامل بين الجوانب المعرفية والمهارية والوجدانية',
    'مع مراعاة الفروق الفردية وتنويع أساليب التدريس لتناسب جميع الطلاب',
    'لضمان تحقيق رؤية التعليم وتطوير العملية التعليمية بصورة شاملة',
    'مع الاستفادة من أفضل الممارسات التربوية والتقنيات التعليمية الحديثة',
    'بما يعزز من دور المعلم كميسر للتعلم وموجه للطالب نحو التميز'
]

PROFESSIONAL_ADDITIONS = {
    'goal': ' بما يعزز من جودة التعليم ويدعم تحقيق رؤية المدرسة التعليمية',
    'summary': ' مع التركيز على الأثر الإيجابي في تحسين الممارسات التعليمية',
    'steps': ' ومراعاة الجوانب التربوية والنفسية للطلاب في جميع المراحل',
    'strategies': ' بما يناسب البيئة الصفية ويحقق أقصى استفادة تعليمية',
    'strengths': ' مما يسهم في تحقيق بيئة تعلم إيجابية ومنتجة',
    'improve': ' مع وضع خطط تطويرية قابلة للتنفيذ في الفصول القادمة',
    'recomm': ' بما يدعم التطوير المهني المستمر ويعزز جودة التعليم'
}

# =====================================================
# HELPERS
# =====================================================
def pick_gemini_model():
    key = random.choice(GEMINI_KEYS)
    genai.configure(api_key=key)
    return genai.GenerativeModel("models/gemini-2.5-flash-lite")

def generate_short_code():
    """توليد كود تفعيل قصير"""
    return secrets.token_hex(3).upper()  # مثال: A9F3C2

def hash_code(code: str):
    """تجزئة الكود للتخزين الآمن"""
    return hashlib.sha256(code.encode()).hexdigest()

def verify_jwt(token: str):
    """التحقق من صحة JWT"""
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
    """حساب وقت انتهاء الصلاحية"""
    now = datetime.datetime.utcnow()
    
    if custom_days and 1 <= custom_days <= 365:
        return now + datetime.timedelta(days=custom_days)
    
    # البحث عن الفترة في ENUM
    try:
        period_enum = ValidityPeriod(period)
        period_config = VALIDITY_PERIODS[period_enum]
        
        if "minutes" in period_config:
            return now + datetime.timedelta(minutes=period_config["minutes"])
        elif "hours" in period_config:
            return now + datetime.timedelta(hours=period_config["hours"])
        elif "days" in period_config:
            return now + datetime.timedelta(days=period_config["days"])
    except:
        pass
    
    # الافتراضي: شهر واحد
    return now + datetime.timedelta(days=30)

def get_period_name(period: str) -> str:
    """الحصول على اسم الفترة بالعربية"""
    try:
        period_enum = ValidityPeriod(period)
        return VALIDITY_PERIODS[period_enum]["name"]
    except:
        return "شهر"  # افتراضي

def format_remaining_time(expires_at: datetime.datetime) -> str:
    """تنسيق الوقت المتبقي"""
    now = datetime.datetime.utcnow()
    if expires_at < now:
        return "منتهي"
    
    diff = expires_at - now
    
    if diff.days > 0:
        if diff.days == 1:
            return "يوم واحد"
        elif diff.days == 2:
            return "يومين"
        elif diff.days <= 10:
            return f"{diff.days} أيام"
        else:
            return f"{diff.days} يوم"
    elif diff.seconds >= 3600:
        hours = diff.seconds // 3600
        if hours == 1:
            return "ساعة واحدة"
        elif hours == 2:
            return "ساعتين"
        else:
            return f"{hours} ساعات"
    elif diff.seconds >= 60:
        minutes = diff.seconds // 60
        if minutes == 1:
            return "دقيقة واحدة"
        elif minutes == 2:
            return "دقيقتين"
        else:
            return f"{minutes} دقائق"
    else:
        return "أقل من دقيقة"

def cleanup_expired_codes():
    """تنظيف الرموز المنتهية الصلاحية"""
    now = datetime.datetime.utcnow()
    expired_hashes = []
    
    for code_hash, code_data in VALID_CODES.items():
        if code_data["expires_at"] < now:
            expired_hashes.append(code_hash)
    
    for code_hash in expired_hashes:
        VALID_CODES.pop(code_hash, None)
    
    if expired_hashes:
        print(f"تم تنظيف {len(expired_hashes)} كود منتهي")

def duration_to_seconds(duration: str) -> int:
    """تحويل المدة إلى ثواني"""
    if duration == "30m":
        return 30 * 60  # 30 دقيقة
    elif duration == "1h":
        return 60 * 60  # ساعة واحدة
    elif duration == "1d":
        return 24 * 60 * 60  # يوم واحد
    elif duration == "30d":
        return 30 * 24 * 60 * 60  # شهر
    else:
        return 30 * 24 * 60 * 60  # افتراضي شهر

# =====================================================
# PROFESSIONAL ENHANCEMENT FUNCTIONS
# =====================================================
def ensure_word_count(content: str, target_words: int = 25) -> str:
    """تأكيد عدد الكلمات مع لمسة مهنية"""
    words = content.split()
    
    if len(words) >= target_words - 5 and len(words) <= target_words + 5:
        return content
    
    if len(words) < target_words - 5:
        extended_content = content
        while len(extended_content.split()) < target_words:
            random_phrase = random.choice(PROFESSIONAL_PHRASES)
            extended_content += ' ' + random_phrase
        
        extended_words = extended_content.split()
        if len(extended_words) > target_words + 5:
            return ' '.join(extended_words[:target_words])
        
        return extended_content
    
    if len(words) > target_words + 5:
        return ' '.join(words[:target_words])
    
    return content

def add_professional_touch(content: str, field_id: str) -> str:
    """إضافة لمسة مهنية للمحتوى"""
    words = content.split()
    if len(words) >= 20:
        return content
    
    if field_id in PROFESSIONAL_ADDITIONS:
        return content + PROFESSIONAL_ADDITIONS[field_id]
    
    return content

def build_educational_prompt(report_data: ReportRequest) -> str:
    """بناء البرومبت التربوي المحترف"""
    
    prompt_template = """أنت خبير تربوي تعليمي محترف تمتلك خبرة ميدانية واسعة في التعليم العام.  
اعتمد منظورًا تربويًا مهنيًا احترافيًا يركّز على تحسين جودة التعليم، ودعم المعلم، وتعزيز بيئة التعلّم، وخدمة القيادة المدرسية.  

التقرير المطلوب: "{report_type}"
{subject_section}{lesson_section}{grade_section}{target_section}{place_section}{count_section}

**توجيهات مهنية:**
- كن موضوعيًا ومتزنًا وبنّاءً  
- قدّم الملاحظات بصيغة تطويرية غير نقدية  
- راعِ واقع الميدان التعليمي وسياق المدرسة  
- اربط بين المعلم والطالب والمنهج والبيئة الصفية والقيادة المدرسية  
- ركّز على جودة التعليم وأثر الممارسات على تعلم الطلاب  
- التزم بلغة عربية فصيحة سليمة وخالية من الأخطاء  

**شروط المحتوى:**
اكتب محتوى كل حقل بصيغة تقريرية مهنية وكأنه صادر عن المعلم.
لا تكتب أبداً عنوان الحقل داخل المحتوى ولا تعِد صياغته بصيغة مباشرة (مثل: الهدف التربوي هو، النبذة المختصرة).
يجب أن يحتوي كل حقل على ما يقارب 25 كلمة.
ابدأ بالمضمون مباشرة دون تمهيد أو عبارات إنشائية.
يمكن الاستفادة من معنى العنوان أو أحد مفاهيمه بشكل غير مباشر فقط عند الحاجة وبما يخدم الفكرة دون تكرار أو حشو.
احرص على وجود ترابط منطقي بين الأهداف، النبذة المختصرة، الاستراتيجيات، إجراءات التنفيذ، نقاط القوة، نقاط التحسين، والتوصيات.
اربط المحتوى بالمادة الدراسية وعنوان الدرس إن وُجد، وكذلك بمكان التنفيذ، بأسلوب مهني متوازن يجمع بين الإشارة المباشرة وغير المباشرة دون تكلف.
اجعل الهدف النهائي للمحتوى تحسين الممارسة التعليمية ودعم التطوير المهني المستدام.
راعِ الوضوح والترابط، واجعل كل جملة تضيف قيمة تعليمية فعلية.

**الحقول المطلوبة:**
1. الهدف التربوي
2. نبذة مختصرة  
3. إجراءات التنفيذ
4. الاستراتيجيات
5. نقاط القوة
6. نقاط التحسين
7. التوصيات

يرجى تقديم الإجابة باللغة العربية الفصحى، وتنظيمها بحيث يكون كل حقل في سطر منفصل يبدأ برقمه فقط دون ذكر العنوان."""
    
    # بناء أقسام البيانات
    sections = []
    if report_data.subject:
        sections.append(f"المادة: {report_data.subject}")
    if report_data.lesson:
        sections.append(f"الدرس: {report_data.lesson}")
    if report_data.grade:
        sections.append(f"الصف: {report_data.grade}")
    if report_data.target:
        sections.append(f"المستهدفون: {report_data.target}")
    if report_data.place:
        sections.append(f"مكان التنفيذ: {report_data.place}")
    if report_data.count:
        sections.append(f"عدد الحضور: {report_data.count}")
    
    data_section = "\n".join(sections)
    
    prompt = prompt_template.format(
        report_type=report_data.report_type,
        subject_section=f"{report_data.subject}\n" if report_data.subject else "",
        lesson_section=f"{report_data.lesson}\n" if report_data.lesson else "",
        grade_section=f"{report_data.grade}\n" if report_data.grade else "",
        target_section=f"{report_data.target}\n" if report_data.target else "",
        place_section=f"{report_data.place}\n" if report_data.place else "",
        count_section=f"{report_data.count}\n" if report_data.count else "",
    )
    
    return prompt

def post_process_response(response_text: str) -> str:
    """معالجة النتيجة مع التحسينات المهنية"""
    
    # قائمة عناوين الحقول لإزالتها
    field_titles = [
        'الهدف التربوي', 'الهدف التربوي', 
        'نبذة مختصرة', 'نبذة مختصرة', 
        'إجراءات التنفيذ', 'إجراءات التنفيذ', 
        'الاستراتيجيات', 'الاستراتيجيات',
        'نقاط القوة', 'نقاط القوة',
        'نقاط التحسين', 'نقاط تحسين',
        'التوصيات', 'التوصيات',
        'هو:', 'تشمل:', 'تشمل', 'يتضمن:', 'يتضمن',
        'يتمثل في', 'يتمثل', 'يمثل', 'يتم',
        'يشمل', 'تحتوي', 'تتضمن'
    ]
    
    lines = response_text.split('\n')
    processed_lines = []
    
    field_mapping = {
        1: 'goal',
        2: 'summary',
        3: 'steps',
        4: 'strategies',
        5: 'strengths',
        6: 'improve',
        7: 'recomm'
    }
    
    current_field = 1
    
    for line in lines:
        cleaned_line = line.strip()
        
        if cleaned_line:
            # إذا كان السطر يبدأ برقم
            if cleaned_line[0].isdigit():
                match = None
                # البحث عن النمط 1. أو 1) أو 1-
                for pattern in ['. ', ') ', '- ']:
                    if pattern in cleaned_line:
                        parts = cleaned_line.split(pattern, 1)
                        if parts[0].isdigit():
                            current_field = int(parts[0])
                            content = parts[1] if len(parts) > 1 else ""
                            match = (current_field, content)
                            break
                
                if not match:
                    # محاولة استخراج الرقم من البداية
                    import re
                    match_num = re.match(r'^(\d+)\s*(.*)', cleaned_line)
                    if match_num:
                        current_field = int(match_num.group(1))
                        content = match_num.group(2)
                        match = (current_field, content)
            
            # إذا لم نجد رقماً، نستخدم الرقم الحالي
            if not match:
                content = cleaned_line
            else:
                _, content = match
            
            # إزالة عناوين الحقول
            for title in field_titles:
                title_lower = title.lower()
                content_lower = content.lower()
                if content_lower.startswith(title_lower):
                    # إزالة العنوان مع أي علامات ترقيم بعده
                    import re
                    pattern = f"^{title}[:\\.\\-]?\\s*"
                    content = re.sub(pattern, '', content, flags=re.IGNORECASE)
                    break
            
            # تطبيق التحسينات المهنية
            if 1 <= current_field <= 7:
                field_id = field_mapping[current_field]
                content = ensure_word_count(content, 25)
                content = add_professional_touch(content, field_id)
                processed_lines.append(f"{current_field}. {content}")
                current_field += 1
    
    # التأكد من وجود 7 حقول
    if len(processed_lines) < 7:
        while len(processed_lines) < 7:
            field_id = field_mapping[len(processed_lines) + 1]
            default_content = "استكمالًا للجهود التربوية والتعليمية."
            content = ensure_word_count(default_content, 25)
            content = add_professional_touch(content, field_id)
            processed_lines.append(f"{len(processed_lines) + 1}. {content}")
    
    # اقتطاع إلى 7 حقول فقط
    processed_lines = processed_lines[:7]
    
    return "\n".join(processed_lines)

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
# توليد كود تفعيل مع صلاحية محددة (GET - يجب استخدام GET هنا)
# -----------------------------------------------------
@app.get("/generate-code")
def generate_code(
    key: str,
    period: str = "30d",
    custom_days: Optional[int] = None
):
    """توليد كود تفعيل مع صلاحية محددة"""
    
    # التحقق من صلاحية المشرف
    if key != ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="Forbidden")
    
    # توليد الكود
    short_code = generate_short_code()
    code_hash = hash_code(short_code)
    
    # حساب وقت الانتهاء
    expires_at = calculate_expiration(period, custom_days)
    
    # حفظ الكود
    VALID_CODES[code_hash] = {
        "expires_at": expires_at,
        "period": period,
        "period_name": get_period_name(period),
        "created_at": datetime.datetime.utcnow(),
        "custom_days": custom_days
    }
    
    # تنظيف الرموز المنتهية
    cleanup_expired_codes()
    
    return {
        "activation_code": short_code,
        "validity_period": {
            "id": period,
            "name": get_period_name(period),
            "expires_at": expires_at.isoformat(),
            "remaining": format_remaining_time(expires_at)
        },
        "expires_in": format_remaining_time(expires_at),
        "generated_at": datetime.datetime.utcnow().isoformat()
    }

# -----------------------------------------------------
# الحصول على خيارات الصلاحيات المتاحة
# -----------------------------------------------------
@app.get("/validity-periods")
def get_validity_periods():
    """الحصول على قائمة فترات الصلاحية المتاحة"""
    periods = []
    for period_key, period_info in VALIDITY_PERIODS.items():
        periods.append({
            "id": period_key.value,
            "name": period_info["name"],
            "description": f"صلاحية لمدة {period_info['name']}"
        })
    
    return {
        "periods": periods,
        "default": ValidityPeriod.ONE_MONTH.value
    }

# -----------------------------------------------------
# تفعيل الأداة (المستخدم) - POST
# -----------------------------------------------------
@app.post("/activate")
def activate(data: ActivateRequest):
    code = data.code.strip()
    duration = data.duration
    
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
    
    # تحديد مدة التوكن بناءً على المدة المحددة
    if duration == "30m":
        delta = datetime.timedelta(minutes=30)
    elif duration == "1h":
        delta = datetime.timedelta(hours=1)
    elif duration == "1d":
        delta = datetime.timedelta(days=1)
    elif duration == "30d":
        delta = datetime.timedelta(days=30)
    else:
        delta = datetime.timedelta(days=30)  # افتراضي
    
    # إصدار JWT
    payload = {
        "type": "activation",
        "code_period": code_data["period"],
        "user_duration": duration,
        "exp": datetime.datetime.utcnow() + delta
    }
    
    token = jwt.encode(payload, JWT_SECRET, algorithm="HS256")
    
    return {
        "token": token,
        "validity_info": {
            "period": code_data["period_name"],
            "user_duration": duration,
            "expires_at": (datetime.datetime.utcnow() + delta).isoformat(),
            "remaining": format_remaining_time(datetime.datetime.utcnow() + delta)
        }
    }

# -----------------------------------------------------
# تحقق من التفعيل
# -----------------------------------------------------
@app.get("/verify")
def verify(x_token: str = Header(..., alias="X-Token")):
    payload = verify_jwt(x_token)
    return {
        "status": "ok",
        "valid": True,
        "token_info": {
            "type": payload.get("type"),
            "period": payload.get("code_period", "unknown"),
            "user_duration": payload.get("user_duration", "30d"),
            "expires_at": datetime.datetime.fromtimestamp(payload["exp"]).isoformat()
        }
    }

# -----------------------------------------------------
# الذكاء الاصطناعي - الطريقة القديمة
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

# -----------------------------------------------------
# الذكاء الاصطناعي للتقرير التربوي
# -----------------------------------------------------
@app.post("/generate-report")
def generate_report(data: ReportRequest, x_token: str = Header(..., alias="X-Token")):
    """توليد تقرير تربوي كامل"""
    verify_jwt(x_token)
    
    try:
        prompt = build_educational_prompt(data)
        model = pick_gemini_model()
        response = model.generate_content(prompt)
        processed_response = post_process_response(response.text)
        
        return {
            "answer": processed_response,
            "report_type": data.report_type,
            "generated_at": datetime.datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"خطأ في توليد التقرير: {str(e)}")

# -----------------------------------------------------
# النسخة المتوافقة
# -----------------------------------------------------
@app.post("/v2/generate")
def generate_v2(data: dict, x_token: str = Header(..., alias="X-Token")):
    """نسخة متوافقة مع الفرونت إند الجديد"""
    verify_jwt(x_token)
    
    try:
        if "report_type" in data:
            report_data = ReportRequest(**data)
            prompt = build_educational_prompt(report_data)
        else:
            prompt = data.get("prompt", "")
        
        if not prompt:
            raise HTTPException(status_code=400, detail="No prompt provided")
        
        model = pick_gemini_model()
        response = model.generate_content(prompt)
        
        if "report_type" in data:
            processed_response = post_process_response(response.text)
            return {"answer": processed_response}
        else:
            return {"answer": response.text}
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)