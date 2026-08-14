from io import BytesIO
from zipfile import ZipFile

import pytest

from resume_agent.domain.models import CareerFactBase, ConfidenceStatus, FactValue, QualityDimension
from resume_agent.application.version_service import VersionService
from resume_agent.rendering.exporters import (
    PdfExporter,
    RenderEngineUnavailable,
    RenderFormat,
    ResumeExporter,
)
from resume_agent.rendering.renderer import ResumeRenderer
from tests.fakes import InMemoryVersionRepository


@pytest.fixture
def rendered_resume():
    base = CareerFactBase()
    base.profile.name = "王明"
    base.profile.email = "wang@example.com"
    base.profile.phone = "138-0000-0000"
    experience = base.add_experience("云数科技", "数据分析师")
    experience.statements[QualityDimension.ACTION].append(
        FactValue(text="搭建自动化数据看板", confidence=ConfidenceStatus.CONFIRMED)
    )
    version = VersionService(InMemoryVersionRepository()).create(
        base,
        "数据分析师版本",
        selected_experience_ids=[experience.id],
    )
    return ResumeRenderer().render(base, version)


def test_html_and_markdown_export_are_utf8(rendered_resume):
    exporter = ResumeExporter()

    html = exporter.export(rendered_resume, RenderFormat.HTML)
    markdown = exporter.export(rendered_resume, RenderFormat.MARKDOWN)

    assert html.media_type == "text/html"
    assert html.content.decode("utf-8").startswith("<!DOCTYPE html>")
    assert markdown.media_type == "text/markdown"
    assert "搭建自动化数据看板" in markdown.content.decode("utf-8")


def test_docx_export_is_a_readable_office_zip(rendered_resume):
    exported = ResumeExporter().export(rendered_resume, RenderFormat.DOCX)

    assert (
        exported.media_type
        == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    with ZipFile(BytesIO(exported.content)) as archive:
        assert "word/document.xml" in archive.namelist()
        document_xml = archive.read("word/document.xml").decode("utf-8")
    assert "云数科技" in document_xml


def test_pdf_export_reports_missing_engine(rendered_resume):
    exporter = ResumeExporter(pdf_exporter=PdfExporter(browser_candidates=[]))

    with pytest.raises(RenderEngineUnavailable, match="browser"):
        exporter.export(rendered_resume, RenderFormat.PDF)


def test_pdf_export_uses_injected_browser_command(tmp_path, rendered_resume):
    browser = tmp_path / "fake-browser"
    browser.write_text(
        "#!/bin/sh\n"
        "for arg in \"$@\"; do\n"
        "  case \"$arg\" in --print-to-pdf=*) out=${arg#*=};; esac\n"
        "done\n"
        "printf '%%PDF-1.4 fake' > \"$out\"\n",
        encoding="utf-8",
    )
    browser.chmod(0o755)
    exporter = ResumeExporter(
        pdf_exporter=PdfExporter(browser_candidates=[browser])
    )

    exported = exporter.export(rendered_resume, RenderFormat.PDF)

    assert exported.media_type == "application/pdf"
    assert exported.content.startswith(b"%PDF-")


def test_export_secondary_rirekisho_for_japanese(tmp_path):
    from resume_agent.domain.models import Certification, Education

    base = CareerFactBase()
    base.profile.name = "王明"
    base.profile.name_kana = "オウ メイ"
    base.profile.birth = "2002-03-15"
    base.education = [Education(school="復旦大学", start="2020-09", end="2024-06")]
    base.certifications = [Certification(name_ja="日本語能力試験 N2", date="2023-12")]
    experience = base.add_experience("云数科技", "数据分析师")
    experience.start = "2023-07"
    experience.end = "2024-06"
    version = VersionService(InMemoryVersionRepository()).create(
        base,
        "日文版本",
        selected_experience_ids=[experience.id],
    )
    version.locale = "ja"
    rendered = ResumeRenderer().render(base, version)

    exporter = ResumeExporter()
    markdown = exporter.export_secondary(rendered, RenderFormat.MARKDOWN)
    html = exporter.export_secondary(rendered, RenderFormat.HTML)
    docx = exporter.export_secondary(rendered, RenderFormat.DOCX)

    assert "rirekisho" in markdown.filename
    assert "履歴書" in markdown.content.decode("utf-8")
    assert "オウ メイ" in markdown.content.decode("utf-8")
    assert html.content.decode("utf-8").startswith("<!DOCTYPE html>")
    with ZipFile(BytesIO(docx.content)) as archive:
        assert "word/document.xml" in archive.namelist()


def test_export_secondary_rejects_non_japanese(rendered_resume):
    exporter = ResumeExporter()
    with pytest.raises(ValueError, match="secondary"):
        exporter.export_secondary(rendered_resume, RenderFormat.MARKDOWN)
