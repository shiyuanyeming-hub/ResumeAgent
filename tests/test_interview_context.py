"""访谈上下文：已确认事实 + GitHub 项目背景资料要喂给选项生成器。"""
from resume_agent.application.interview_service import InterviewService
from resume_agent.domain.models import (
    Experience,
    ExperienceType,
    FactValue,
    QualityDimension,
)


def make_experience():
    experience = Experience(
        organization="wangming/resume-tool",
        role="后端开发",
        start="2025-03",
        type=ExperienceType.PROJECT,
    )
    experience.statements[QualityDimension.ACTION].append(
        FactValue(text="实现了 PDF 导出接口")
    )
    return experience


def test_experience_context_includes_facts_and_source_context():
    experience = make_experience()
    experience.source_context = "\n".join([
        "项目简介：智能简历生成器",
        "主要语言：Python",
        "README 摘要：支持 AcroForm 表单填充。",
    ])
    context = InterviewService._experience_context(experience)
    assert "wangming/resume-tool · 后端开发" in context
    assert "已确认事实：实现了 PDF 导出接口" in context
    assert "项目背景资料：项目简介：智能简历生成器" in context
    assert "README 摘要：支持 AcroForm 表单填充" in context


def test_experience_context_without_source_context_omits_it():
    experience = make_experience()
    context = InterviewService._experience_context(experience)
    assert "项目背景资料" not in context
    assert "已确认事实：实现了 PDF 导出接口" in context


def test_experience_context_truncates_source_context():
    experience = make_experience()
    experience.source_context = "A" * 3000
    context = InterviewService._experience_context(experience)
    assert context.count("A") == 1600
