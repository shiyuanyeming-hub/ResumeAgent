from io import BytesIO

from fastapi.testclient import TestClient
from pypdf import PdfReader, PdfWriter
from pypdf.generic import (
    ArrayObject,
    BooleanObject,
    DictionaryObject,
    NameObject,
    NumberObject,
    RectangleObject,
    TextStringObject,
)

from resume_agent.api.app import create_app
from resume_agent.application.pdf_template_service import (
    analyze_and_fill,
    has_form_fields,
    match_field,
)


def build_form_pdf(field_names):
    """构造带文本表单字段的 PDF。"""
    writer = PdfWriter()
    writer.add_blank_page(width=595, height=842)
    page_ref = writer.pages[0]
    fields = ArrayObject()
    for index, name in enumerate(field_names):
        field = DictionaryObject({
            NameObject("/FT"): NameObject("/Tx"),
            NameObject("/T"): TextStringObject(name),
            NameObject("/Type"): NameObject("/Annot"),
            NameObject("/Subtype"): NameObject("/Widget"),
            NameObject("/Rect"): RectangleObject((50, 700 - index * 30, 300, 716 - index * 30)),
            NameObject("/F"): NumberObject(4),
            NameObject("/V"): TextStringObject(""),
            NameObject("/DA"): TextStringObject("/Helv 0 Tf 0 g"),
        })
        field_ref = writer._add_object(field)
        fields.append(field_ref)
        annots = page_ref.get(NameObject("/Annots"))
        if annots is None:
            annots = ArrayObject()
            page_ref[NameObject("/Annots")] = annots
        annots.append(field_ref)
    writer._root_object[NameObject("/AcroForm")] = DictionaryObject({
        NameObject("/Fields"): fields,
        NameObject("/DR"): DictionaryObject(),
        NameObject("/NeedAppearances"): BooleanObject(True),
    })
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def test_match_field_rules():
    assert match_field("姓名") == "name"
    assert match_field("Full Name") == "name"
    assert match_field("手机号码") == "phone"
    assert match_field("Email") == "email"
    assert match_field("毕业院校") == "school"
    assert match_field("自我评价") == "summary"
    assert match_field("工作经历") == "experience"
    assert match_field("应聘职位") == "target"
    assert match_field("无关字段xyz") is None


def test_analyze_and_fill_forms():
    from resume_agent.domain.models import (
        CareerFactBase,
        CandidateProfile,
        ConfidenceStatus,
        Education,
        Experience,
        FactValue,
        QualityDimension,
    )

    base = CareerFactBase()
    base.profile = CandidateProfile(
        name="张伟", email="zw@example.com", phone="13912345678",
        location="上海", skills=["Python", "SQL"],
    )
    base.target.role = "数据分析师"
    base.educations.append(
        Education(school="同济大学", major="软件工程", degree="硕士", start="2023-09")
    )
    experience = base.add_experience("字节跳动", "数据分析实习生")
    experience.start = "2025-07"
    experience.statements[QualityDimension.ACTION] = [
        FactValue(text="搭建看板", confidence=ConfidenceStatus.CONFIRMED)
    ]
    pdf_bytes = build_form_pdf(["姓名", "电话", "邮箱", "毕业院校", "工作经历"])
    result = analyze_and_fill(pdf_bytes, base, selected_summary="")

    assert set(result["matched_fields"]) == {"姓名", "电话", "邮箱", "毕业院校", "工作经历"}
    reader = PdfReader(BytesIO(result["filled_pdf"]))
    fields = reader.get_fields()
    assert fields["姓名"].get("/V") == "张伟"
    assert fields["电话"].get("/V") == "13912345678"
    assert fields["毕业院校"].get("/V") == "同济大学"
    assert "字节跳动" in str(fields["工作经历"].get("/V"))


def test_has_form_fields():
    assert has_form_fields(build_form_pdf(["姓名"])) is True
    assert has_form_fields(b"%PDF-1.4\n" + b"0" * 100) is False


def test_pdf_template_endpoints_and_export(tmp_path):
    app = create_app(tmp_path / "resume-agent.db")
    with TestClient(app) as client:
        base = client.post("/fact-bases", json={"target": {"role": "数据分析师"}}).json()
        client.patch(
            f"/fact-bases/{base['id']}/profile",
            json={
                "name": "张伟", "email": "zw@example.com", "phone": "13912345678",
                "location": "", "links": [], "skills": ["Python"],
                "certificates": [], "language_scores": [], "photo": "",
                "template": "", "pdf_template": "",
            },
        )
        client.post(
            f"/fact-bases/{base['id']}/educations",
            json={"school": "同济大学", "major": "软件工程",
                  "degree": "本科", "start": "2020-09"},
        )
        version = client.post(
            f"/fact-bases/{base['id']}/versions",
            json={"name": "默认版本", "locale": "zh"},
        ).json()
        pdf_bytes = build_form_pdf(["姓名", "电话", "毕业院校"])

        up = client.put(
            f"/fact-bases/{base['id']}/pdf-template",
            files={"template": ("school.pdf", pdf_bytes, "application/pdf")},
        )
        assert up.status_code == 200
        payload = up.json()
        assert payload["total_fields"] == 3
        assert set(payload["matched_fields"]) == {"姓名", "电话", "毕业院校"}
        assert payload["base"]["profile"]["pdf_template"].endswith(".pdf")

        # GET 填充后的 PDF
        filled = client.get(f"/fact-bases/{base['id']}/pdf-template")
        assert filled.status_code == 200
        assert filled.content.startswith(b"%PDF-")
        reader = PdfReader(BytesIO(filled.content))
        assert reader.get_fields()["姓名"].get("/V") == "张伟"

        # 导出 PDF 走学校模板
        exported = client.get(f"/versions/{version['id']}/export?format=pdf")
        assert exported.status_code == 200
        exported_reader = PdfReader(BytesIO(exported.content))
        assert exported_reader.get_fields()["姓名"].get("/V") == "张伟"

        # 删除恢复
        removed = client.delete(f"/fact-bases/{base['id']}/pdf-template")
        assert removed.status_code == 200
        assert removed.json()["profile"]["pdf_template"] == ""


def test_pdf_template_rejects_plain_pdf(tmp_path):
    app = create_app(tmp_path / "resume-agent.db")
    with TestClient(app) as client:
        base = client.post("/fact-bases", json={}).json()
        up = client.put(
            f"/fact-bases/{base['id']}/pdf-template",
            files={"template": ("plain.pdf", b"%PDF-1.4\n" + b"0" * 200, "application/pdf")},
        )
        assert up.status_code == 415
