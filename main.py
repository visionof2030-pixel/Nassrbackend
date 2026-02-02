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
from typing import Optional

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

# =====================================================
# SIMPLE STORAGE (in-memory)
# ⚠️ يمكن لاحقًا استبداله Redis أو DB
# =====================================================
VALID_CODES = {}  # code_hash: expiration_datetime

# =====================================================
# PROFESSIONAL PHRASES (من الفرونت إند السابق)
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
# PROFESSIONAL ENHANCEMENT FUNCTIONS (من الفرونت إند السابق)
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

# =====================================================
# PROMPT TEMPLATES (من الفرونت إند السابق)
# =====================================================
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
    
    # قائمة عناوين الحقول لإزالتها (من removeFieldTitles())
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
    
    # التأكد من وجود 7 حقول (من fallbackProfessionalAIParsing())
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
# توليد كود تفعيل (مشرف فقط)
# -----------------------------------------------------
@app.get("/generate-code")
def generate_code(key: str):
    if key != ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="Forbidden")

    short_code = generate_short_code()
    code_hash = hash_code(short_code)

    expires_at = datetime.datetime.utcnow() + datetime.timedelta(days=30)
    VALID_CODES[code_hash] = expires_at

    return {
        "activation_code": short_code,
        "expires_in": "30 days"
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

    # إصدار JWT استخدام
    payload = {
        "type": "activation",
        "exp": datetime.datetime.utcnow() + datetime.timedelta(days=30)
    }

    token = jwt.encode(payload, JWT_SECRET, algorithm="HS256")

    return {"token": token}

# -----------------------------------------------------
# تحقق من التفعيل
# -----------------------------------------------------
@app.get("/verify")
def verify(x_token: str = Header(..., alias="X-Token")):
    verify_jwt(x_token)
    return {"status": "ok"}

# -----------------------------------------------------
# الذكاء الاصطناعي - الطريقة القديمة (للتوافق)
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
# الذكاء الاصطناعي للتقرير التربوي (الجديد)
# -----------------------------------------------------
@app.post("/generate-report")
def generate_report(data: ReportRequest, x_token: str = Header(..., alias="X-Token")):
    """توليد تقرير تربوي كامل"""
    verify_jwt(x_token)
    
    try:
        # 1. بناء البرومبت التربوي
        prompt = build_educational_prompt(data)
        
        # 2. استدعاء نموذج Gemini
        model = pick_gemini_model()
        response = model.generate_content(prompt)
        
        # 3. معالجة النتيجة مع جميع التحسينات
        processed_response = post_process_response(response.text)
        
        return {
            "answer": processed_response,
            "report_type": data.report_type,
            "generated_at": datetime.datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"خطأ في توليد التقرير: {str(e)}")

# -----------------------------------------------------
# تحديث نقطة النهاية القديمة لدعم كلا الطريقتين
# -----------------------------------------------------
@app.post("/v2/generate")
def generate_v2(data: dict, x_token: str = Header(..., alias="X-Token")):
    """نسخة متوافقة مع الفرونت إند الجديد"""
    verify_jwt(x_token)
    
    try:
        # الطريقة الجديدة: إذا كان يحتوي على بيانات التقرير
        if "report_type" in data:
            report_data = ReportRequest(**data)
            prompt = build_educational_prompt(report_data)
        else:
            # الطريقة القديمة: إذا كان يحتوي على prompt مباشر
            prompt = data.get("prompt", "")
        
        if not prompt:
            raise HTTPException(status_code=400, detail="No prompt provided")
        
        model = pick_gemini_model()
        response = model.generate_content(prompt)
        
        # إذا كان طلب تقرير، قم بمعالجته مع جميع التحسينات
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