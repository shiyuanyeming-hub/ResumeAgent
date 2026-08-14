from uuid import uuid4

import pytest

from resume_agent.domain.models import (
    CandidateProfile,
    CareerFactBase,
    ConfidenceStatus,
    FactValue,
    QualityDimension,
    ResumeVersion,
)
from resume_agent.rendering.renderer import ResumeRenderer


def evidence_fixture():
    base = CareerFactBase(
        profile=CandidateProfile(
            name="王明",
            email="wang@example.com",
            phone="138-0000-0000",
            location="东京",
        )
    )
    first = base.add_experience("第一家公司", "数据分析师")
    first.start = "2023-01"
    first.end = "2024-03"
    first.linked_skills = ["SQL", "Python"]
    first.statements[QualityDimension.ACTION] = [
        FactValue(text="搭建用户留存看板", confidence=ConfidenceStatus.CONFIRMED),
        FactValue(text="未确认内容", confidence=ConfidenceStatus.UNVERIFIED),
    ]
    first.statements[QualityDimension.RESULT] = [
        FactValue(text="将周报耗时从四小时降到三十分钟", confidence=ConfidenceStatus.ESTIMATED)
    ]
    second = base.add_experience("第二家公司", "产品分析师")
    second.statements[QualityDimension.METHOD] = [
        FactValue(text="使用漏斗分析定位流失环节", confidence=ConfidenceStatus.CONFIRMED)
    ]
    base.revision = 3
    return base, first, second


def make_version(base, experiences, *, locale="zh", style=None, base_revision=None):
    styles = {locale: style} if style else {}
    ids = [experience.id for experience in experiences]
    return ResumeVersion(
        fact_base_id=base.id,
        name="目标岗位版本",
        target_role="高级数据分析师",
        company="目标公司",
        locale=locale,
        selected_experience_ids=ids,
        ordering=ids,
        styles=styles,
        base_revision=base.revision if base_revision is None else base_revision,
    )


def test_renderer_uses_selected_order_and_excludes_unverified():
    base, first, second = evidence_fixture()
    version = make_version(base, [first, second])
    version.ordering = [second.id, first.id]

    result = ResumeRenderer().render(base, version)

    assert [item.organization for item in result.experiences] == [
        "第二家公司",
        "第一家公司",
    ]
    assert "未确认内容" not in result.markdown
    assert "将周报耗时从四小时降到三十分钟" in result.markdown


def test_renderer_only_includes_selected_experiences():
    base, first, second = evidence_fixture()
    version = make_version(base, [second])

    result = ResumeRenderer().render(base, version)

    assert [item.organization for item in result.experiences] == ["第二家公司"]
    assert "第一家公司" not in result.html


def test_renderer_escapes_profile_and_fact_html():
    base, first, _ = evidence_fixture()
    base.profile.name = "<script>alert(1)</script>"
    first.statements[QualityDimension.ACTION][0].text = '<img src=x onerror="alert(2)">'
    version = make_version(base, [first])

    result = ResumeRenderer().render(base, version)

    assert "<script>" not in result.html
    assert "<img src=x" not in result.html
    assert "&lt;script&gt;" in result.html
    assert "&lt;img src=x" in result.html


@pytest.mark.parametrize(
    ("locale", "heading", "title"),
    [
        ("zh", "实习/工作经历", "简历"),
        ("en", "Experience", "Resume"),
        ("ja", "職務経歴", "職務経歴書"),
    ],
)
def test_renderer_localizes_headings_without_translating_facts(locale, heading, title):
    base, first, _ = evidence_fixture()
    version = make_version(base, [first], locale=locale)

    result = ResumeRenderer().render(base, version)

    assert result.title == title
    assert heading in result.html
    assert "搭建用户留存看板" in result.html


def test_renderer_warns_about_estimates_staleness_and_missing_profile():
    base, first, _ = evidence_fixture()
    base.profile = CandidateProfile()
    version = make_version(base, [first], base_revision=base.revision - 1)

    result = ResumeRenderer().render(base, version)

    assert {warning.code for warning in result.warnings} >= {
        "missing_profile",
        "estimated_evidence",
        "stale_version",
    }


def test_renderer_collects_skills_once_and_is_deterministic():
    base, first, second = evidence_fixture()
    second.linked_skills = ["SQL", "Tableau"]
    version = make_version(base, [first, second])
    renderer = ResumeRenderer()

    first_result = renderer.render(base, version)
    second_result = renderer.render(base, version)

    assert first_result.skills == ["SQL", "Python", "Tableau"]
    assert first_result == second_result


def test_renderer_rejects_invalid_locale_style_and_selected_reference():
    base, first, _ = evidence_fixture()
    invalid_locale = make_version(base, [first])
    invalid_locale.locale = "fr"
    invalid_style = make_version(base, [first], style="不存在")
    invalid_reference = make_version(base, [first])
    invalid_reference.selected_experience_ids = [uuid4()]
    renderer = ResumeRenderer()

    with pytest.raises(ValueError, match="unsupported locale"):
        renderer.render(base, invalid_locale)
    with pytest.raises(ValueError, match="unsupported style"):
        renderer.render(base, invalid_style)
    with pytest.raises(ValueError, match="unknown experience"):
        renderer.render(base, invalid_reference)


from resume_agent.domain.models import Education, ExperienceType
from resume_agent.rendering.models import RenderedEducation


def test_zh_renders_education_section():
    base, first, _ = evidence_fixture()
    base.educations.append(
        Education(school="某大学", major="统计学", degree="本科",
                  start="2020-09", core_courses=["概率论", "数理统计"])
    )
    version = make_version(base, [first], locale="zh")
    rendered = ResumeRenderer().render(base, version)
    assert "## 教育背景" in rendered.markdown
    assert "某大学" in rendered.markdown
    assert "核心课程：概率论、数理统计" in rendered.markdown
    assert "教育背景" in rendered.html
    assert any(item.school == "某大学" for item in rendered.educations)


def test_zh_groups_experiences_by_type():
    base, first, second = evidence_fixture()
    second.type = ExperienceType.CAMPUS
    version = make_version(base, [first, second], locale="zh")
    rendered = ResumeRenderer().render(base, version)
    assert "## 实习/工作经历" in rendered.markdown
    assert "## 校园及项目经历" in rendered.markdown
    assert "校园及项目经历" in rendered.html


def test_zh_skills_section_uses_profile_skills():
    base, first, _ = evidence_fixture()
    base.profile.skills = ["SQL", "Python"]
    first.linked_skills = []
    version = make_version(base, [first], locale="zh")
    rendered = ResumeRenderer().render(base, version)
    assert "## 技能" in rendered.markdown
    assert "SQL · Python" in rendered.markdown


def test_zh_renders_self_summary_when_selected():
    base, first, _ = evidence_fixture()
    version = make_version(base, [first], locale="zh")
    version.selected_summary = "目标导向，数据驱动。"
    rendered = ResumeRenderer().render(base, version)
    assert "## 自我评价" in rendered.markdown
    assert "目标导向，数据驱动。" in rendered.markdown
    assert "自我评价" in rendered.html
    assert rendered.self_summary == "目标导向，数据驱动。"


def test_zh_omits_self_summary_when_empty():
    base, first, _ = evidence_fixture()
    version = make_version(base, [first], locale="zh")
    rendered = ResumeRenderer().render(base, version)
    assert "自我评价" not in rendered.markdown
    assert rendered.self_summary == ""


from resume_agent.domain.models import VersionSnippet


def test_zh_snippet_mode_replaces_auto_bullets():
    base, first, _ = evidence_fixture()
    version = make_version(base, [first], locale="zh")
    snippet = VersionSnippet(text="搭建并维护用户留存看板")
    version.snippets[first.id] = [snippet]
    rendered = ResumeRenderer().render(base, version)
    assert "搭建并维护用户留存看板" in rendered.markdown
    assert "搭建用户留存看板" not in rendered.markdown
    assert f'data-section="experience:{first.id}"' in rendered.html
    assert f'data-snippet-id="{snippet.id}"' in rendered.html


def test_zh_custom_snippets_render_and_drop_zone_exists():
    base, first, _ = evidence_fixture()
    version = make_version(base, [first], locale="zh")
    rendered = ResumeRenderer().render(base, version)
    assert 'data-section="custom"' in rendered.html
    version.custom_sections = [VersionSnippet(text="一段自由补充内容")]
    rendered = ResumeRenderer().render(base, version)
    assert "## 自定义片段" in rendered.markdown
    assert "一段自由补充内容" in rendered.markdown
    assert rendered.custom_snippets[0].text == "一段自由补充内容"
