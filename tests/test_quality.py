from resume_agent.domain.models import (
    CareerFactBase,
    ConfidenceStatus,
    Education,
    Experience,
    FactValue,
    QualityDimension,
    Specificity,
)
from resume_agent.domain.quality import (
    evaluate_experience,
    evaluate_profile_completeness,
)


def put(
    experience: Experience,
    dimension: QualityDimension,
    text: str,
    specificity: Specificity = Specificity.PRESENT,
) -> None:
    experience.statements[dimension].append(
        FactValue(text=text, specificity=specificity)
    )


def test_gate_requires_action_even_with_four_other_dimensions():
    experience = Experience(organization="A", role="Analyst")
    for dimension in [
        QualityDimension.CONTEXT,
        QualityDimension.RESPONSIBILITY,
        QualityDimension.METHOD,
        QualityDimension.RESULT,
    ]:
        put(experience, dimension, dimension.value)

    assert evaluate_experience(experience).passes_gate is False


def test_gate_passes_with_four_dimensions_action_and_result():
    experience = Experience(organization="A", role="Analyst")
    for dimension in [
        QualityDimension.CONTEXT,
        QualityDimension.RESPONSIBILITY,
        QualityDimension.ACTION,
        QualityDimension.RESULT,
    ]:
        put(experience, dimension, dimension.value)

    report = evaluate_experience(experience)

    assert report.passes_gate is True
    assert report.scores[QualityDimension.ACTION] == 1


def test_concrete_fact_scores_two():
    experience = Experience(organization="A", role="Analyst")
    put(
        experience,
        QualityDimension.EVIDENCE,
        "Saved four hours weekly",
        Specificity.CONCRETE,
    )

    assert evaluate_experience(experience).scores[QualityDimension.EVIDENCE] == 2


def test_profile_completeness_zh_sections():
    base = CareerFactBase()
    report = evaluate_profile_completeness(base)
    assert report.sections == {
        "profile": False, "target": False, "education": False,
        "experience": False, "skills": False, "summary": False,
    }
    assert report.complete is False


def test_profile_completeness_reflects_filled_sections():
    base = CareerFactBase()
    base.profile.name = "王明"
    base.profile.email = "wang@example.com"
    base.profile.phone = "138-0000-0000"
    base.target.role = "数据分析师"
    base.educations.append(Education(school="某大学", major="统计学", start="2020-09"))
    experience = base.add_experience("星河科技", "实习生")
    experience.statements[QualityDimension.CONTEXT] = [
        FactValue(text="业务需要留存分析", confidence=ConfidenceStatus.CONFIRMED)
    ]
    experience.statements[QualityDimension.RESPONSIBILITY] = [
        FactValue(text="负责看板搭建", confidence=ConfidenceStatus.CONFIRMED)
    ]
    experience.statements[QualityDimension.ACTION] = [
        FactValue(text="搭建看板", confidence=ConfidenceStatus.CONFIRMED)
    ]
    experience.statements[QualityDimension.RESULT] = [
        FactValue(text="看板被团队采用", confidence=ConfidenceStatus.CONFIRMED)
    ]
    base.profile.skills = ["SQL"]
    report = evaluate_profile_completeness(base, selected_summary="稳重可靠。")
    assert report.sections == {
        "profile": True, "target": True, "education": True,
        "experience": True, "skills": True, "summary": True,
    }
    assert report.complete is True
