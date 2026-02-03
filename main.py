def parse_ai_response(response_text: str, report_type: str = "") -> Dict[str, str]:
    """تحليل النص الذي يرجع من الذكاء الاصطناعي إلى حقول مع إثراء ذكي"""
    
    lines = response_text.split('\n')
    parsed = {
        "goal": "",
        "summary": "",
        "steps": "",
        "strategies": "",
        "strengths": "",
        "improve": "",
        "recomm": ""
    }
    
    current_field = None
    field_content = []
    
    for line in lines:
        line = line.strip()
        
        # البحث عن بداية حقل جديد
        if line.startswith('1.') or line.startswith('١.'):
            if current_field and field_content:
                parsed[current_field] = ' '.join(field_content).strip()
            current_field = "goal"
            field_content = [line[2:].strip()]
            
        elif line.startswith('2.') or line.startswith('٢.'):
            if current_field and field_content:
                parsed[current_field] = ' '.join(field_content).strip()
            current_field = "summary"
            field_content = [line[2:].strip()]
            
        elif line.startswith('3.') or line.startswith('٣.'):
            if current_field and field_content:
                parsed[current_field] = ' '.join(field_content).strip()
            current_field = "steps"
            field_content = [line[2:].strip()]
            
        elif line.startswith('4.') or line.startswith('٤.'):
            if current_field and field_content:
                parsed[current_field] = ' '.join(field_content).strip()
            current_field = "strategies"
            field_content = [line[2:].strip()]
            
        elif line.startswith('5.') or line.startswith('٥.'):
            if current_field and field_content:
                parsed[current_field] = ' '.join(field_content).strip()
            current_field = "strengths"
            field_content = [line[2:].strip()]
            
        elif line.startswith('6.') or line.startswith('٦.'):
            if current_field and field_content:
                parsed[current_field] = ' '.join(field_content).strip()
            current_field = "improve"
            field_content = [line[2:].strip()]
            
        elif line.startswith('7.') or line.startswith('٧.'):
            if current_field and field_content:
                parsed[current_field] = ' '.join(field_content).strip()
            current_field = "recomm"
            field_content = [line[2:].strip()]
            
        elif current_field and line and not line.startswith(('1','2','3','4','5','6','7','١','٢','٣','٤','٥','٦','٧')):
            field_content.append(line)
    
    # الحقل الأخير
    if current_field and field_content:
        parsed[current_field] = ' '.join(field_content).strip()
    
    # تطبيق الإثراء الذكي على كل حقل
    for key in parsed:
        if parsed[key]:  # إذا كان النص غير فارغ
            parsed[key] = enrich_and_enforce(parsed[key], 25, 35, report_type)
    
    # إذا فشل التحليل، نستخدم النصوص الافتراضية مع الإثراء
    if not any(parsed.values()):
        for key in parsed:
            if key in DEFAULT_REPORT_TEXTS:
                parsed[key] = enrich_and_enforce(
                    random.choice(DEFAULT_REPORT_TEXTS[key]), 
                    25, 35, 
                    report_type
                )
    
    return parsed