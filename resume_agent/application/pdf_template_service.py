"""学校 PDF 模板：分析可填写表单字段并自动填充简历内容。"""

from io import BytesIO
from typing import List, Optional, Tuple

from pypdf import PdfReader, PdfWriter

# 字段名关键词 → 简历字段（顺序即匹配优先级，长关键词在前）
FIELD_RULES: List[Tuple[List[str], str]] = [
    (["姓名", "名字", "candidate", "full name", "name"], "name"),
    (["e-mail", "email", "邮箱", "邮件", "mail"], "email"),
    (["手机", "电话", "mobile", "phone", "tel"], "phone"),
    (["所在地", "地址", "address", "location"], "location"),
    (["毕业院校", "学校", "college", "university", "school", "大学"], "school"),
    (["专业", "major"], "major"),
    (["学历", "degree"], "degree"),
    (["技能", "特长", "skill"], "skills"),
    (["自我评价", "简介", "评价", "summary", "profile"], "summary"),
    (["项目经历", "工作经历", "实习经历", "经历", "experience", "实践"], "experience"),
    (["求职意向", "应聘", "目标岗位", "岗位", "职位", "job", "target"], "target"),
]

MAX_PDF_TEMPLATE_BYTES = 10 * 1024 * 1024


def match_field(field_name: str) -> Optional[str]:
    normalized = (field_name or "").strip().lower()
    if not normalized:
        return None
    for keywords, key in FIELD_RULES:
        for keyword in keywords:
            if keyword in normalized:
                return key
    return None


def resume_values(base, selected_summary: str = "") -> dict:
    """把事实库内容整理成可填入表单的字符串。"""
    experiences_text = "；".join(
        _experience_line(experience) for experience in base.experiences
    )
    return {
        "name": base.profile.name.strip(),
        "email": base.profile.email.strip(),
        "phone": base.profile.phone.strip(),
        "location": base.profile.location.strip(),
        "school": "、".join(
            education.school for education in base.educations if education.school
        ),
        "major": "、".join(
            education.major for education in base.educations if education.major
        ),
        "degree": "、".join(
            education.degree for education in base.educations if education.degree
        ),
        "skills": "、".join(
            item for item in (
                *base.profile.skills,
                *base.profile.certificates,
                *base.profile.language_scores,
            ) if item.strip()
        ),
        "summary": selected_summary.strip(),
        "experience": experiences_text,
        "target": base.target.role.strip(),
    }


def _experience_line(experience) -> str:
    from resume_agent.domain.models import ConfidenceStatus

    period = f"{experience.start or '?'}–{experience.end or '至今'}"
    facts = "；".join(
        value.text
        for values in experience.statements.values()
        for value in values
        if value.confidence is not ConfidenceStatus.UNVERIFIED
    )
    head = f"{experience.organization} · {experience.role}（{period}）"
    return f"{head}：{facts}" if facts else head


def analyze_and_fill(pdf_bytes: bytes, base, selected_summary: str = "") -> dict:
    """解析表单字段、匹配简历内容并生成填充后的 PDF。"""
    reader = PdfReader(BytesIO(pdf_bytes))
    fields = reader.get_fields() or {}
    mapping: dict = {}
    for field_name, field in fields.items():
        field_type = str(field.get("/FT", "/Tx"))
        if field_type not in ("/Tx", "/Text"):
            continue
        key = match_field(field_name)
        if key is not None and key not in mapping:
            mapping[key] = field_name

    values = resume_values(base, selected_summary)
    filled_values = {
        field_name: values[key]
        for key, field_name in mapping.items()
        if values.get(key)
    }
    writer = PdfWriter()
    writer.append(reader)
    if filled_values:
        writer.update_page_form_field_values(
            writer.pages[0], filled_values, auto_regenerate=True
        )
    output = BytesIO()
    writer.write(output)
    return {
        "total_fields": len(fields),
        "matched_fields": list(filled_values.keys()),
        "matched_keys": sorted(mapping.keys()),
        "unfilled_keys": sorted(
            key for key in mapping if not values.get(key)
        ),
        "filled_pdf": output.getvalue(),
    }


def has_form_fields(pdf_bytes: bytes) -> bool:
    try:
        reader = PdfReader(BytesIO(pdf_bytes))
    except Exception:
        return False
    return bool(reader.get_fields())
