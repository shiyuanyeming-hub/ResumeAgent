from uuid import uuid4

import pytest
from pydantic import ValidationError

from resume_agent.domain.models import (
    CareerFactBase,
    ConfidenceStatus,
    Education,
    ExperienceType,
    FactProposal,
    FactValue,
    InterviewSession,
    QualityDimension,
    ResumeVersion,
    Specificity,
    VersionSnippet,
)
from resume_agent.domain.year_month import is_year_month, year_month_le


def test_sensitive_confirmed_fact_keeps_both_attributes():
    fact = FactValue(
        text="Managed a six-person team",
        confidence=ConfidenceStatus.CONFIRMED,
        specificity=Specificity.CONCRETE,
        sensitive=True,
    )

    assert fact.confidence is ConfidenceStatus.CONFIRMED
    assert fact.sensitive is True


def test_empty_fact_text_is_rejected():
    with pytest.raises(ValidationError):
        FactValue(text="   ")


def test_confirming_proposal_updates_experience_and_revision():
    base = CareerFactBase()
    experience = base.add_experience("Yunshu", "Data Analyst")
    proposal = FactProposal(
        fact_base_revision=0,
        experience_id=experience.id,
        dimension=QualityDimension.ACTION,
        values=[FactValue(text="Built an automated dashboard")],
    )

    base.confirm(proposal)

    assert base.revision == 1
    assert (
        base.get_experience(experience.id)
        .statements[QualityDimension.ACTION][0]
        .text
        == "Built an automated dashboard"
    )


def test_stale_proposal_is_rejected():
    base = CareerFactBase(revision=2)
    experience = base.add_experience("Yunshu", "Data Analyst")
    proposal = FactProposal(
        fact_base_revision=1,
        experience_id=experience.id,
        dimension=QualityDimension.ACTION,
        values=[FactValue(text="Built an automated dashboard")],
    )

    with pytest.raises(ValueError, match="revision conflict"):
        base.confirm(proposal)


def test_fact_proposal_defaults_next_question():
    proposal = FactProposal(
        fact_base_revision=0,
        experience_id=uuid4(),
        dimension=QualityDimension.ACTION,
        values=[FactValue(text="搭建了看板")],
    )
    assert proposal.next_question == ""


def test_interview_session_pending_next_defaults():
    session = InterviewSession(fact_base_id=uuid4())
    assert session.pending_next_text == ""
    assert session.pending_next_dimension is None


def test_year_month_helpers():
    assert is_year_month("2023-09")
    assert not is_year_month("2023-9")
    assert not is_year_month("2023/09")
    assert not is_year_month("2023-13")
    assert year_month_le("2023-09", "2024-01")
    with pytest.raises(ValueError):
        year_month_le("2023-9", "2024-01")
    with pytest.raises(ValueError):
        year_month_le("2023-09", "2024-1")


def test_experience_defaults_to_work_type():
    base = CareerFactBase()
    experience = base.add_experience("星河科技", "实习生")
    assert experience.type is ExperienceType.WORK


def test_education_validates_year_month_fields():
    with pytest.raises(ValidationError):
        Education(school="某大学", start="2023-9")


def test_version_carries_snippet_and_summary_fields():
    version = ResumeVersion(fact_base_id=uuid4(), name="默认版本", base_revision=0)
    assert version.summary_options == []
    assert version.selected_summary == ""
    assert version.snippets == {}
    assert version.custom_sections == []


def test_version_snippet_requires_text():
    with pytest.raises(ValidationError):
        VersionSnippet(text=" ")


def test_experience_null_end_normalizes_to_empty_string():
    """历史数据曾把「至今」存成 null，加载时必须归一化为空串，否则档案列表整个 422。"""
    import json

    base = CareerFactBase()
    base.add_experience("星河科技", "实习生")
    payload = json.loads(base.model_dump_json())
    payload["experiences"][0]["end"] = None
    loaded = CareerFactBase.model_validate(payload)
    assert loaded.experiences[0].end == ""
