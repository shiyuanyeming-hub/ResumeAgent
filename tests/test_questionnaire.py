from uuid import uuid4

import pytest

from resume_agent.application.fact_base_service import FactBaseService
from resume_agent.application.questionnaire import (
    QuestionKind, QuestionnaireEngine, QuestionnaireService,
)
from resume_agent.domain.models import (
    CareerFactBase, ConfidenceStatus, Education, ExperienceType,
    FactValue, QualityDimension, QuestionnaireState, ResumeVersion,
)
from tests.fakes import (
    InMemoryFactBaseRepository, InMemoryQuestionnaireRepository,
)


engine = QuestionnaireEngine()


def make_base():
    base = CareerFactBase()
    base.target.role = "数据分析师"
    base.target.country = "东京"
    base.profile.name = "王明"
    base.profile.email = "wang@example.com"
    base.profile.phone = "13800000000"
    base.profile.location = "东京"
    base.profile.links = ["https://example.com"]
    return base


def test_engine_starts_with_profile_name():
    engine = QuestionnaireEngine()
    card = engine.next_card(
        CareerFactBase(), QuestionnaireState(fact_base_id=uuid4())
    )
    assert card.step_id == "profile:name"


def test_engine_skips_steps_marked_skipped():
    base = make_base()
    base.target.role = ""  # 目标岗位未填，验证跳过基本信息后停在 target:role
    state = QuestionnaireState(fact_base_id=base.id)
    state.skipped = [
        f"profile:{field}" for field in ("name", "email", "phone", "location", "links")
    ]
    card = engine.next_card(base, state)
    assert card.step_id == "target:role"


def test_engine_walks_section_order_to_education():
    base = make_base()
    state = QuestionnaireState(fact_base_id=base.id)
    card = engine.next_card(base, state)
    assert card.step_id == "education:add"
    assert card.section == "education"


def test_engine_asks_experience_type_first():
    base = make_base()
    base.educations.append(Education(school="某大学", major="统计", start="2020-09"))
    state = QuestionnaireState(fact_base_id=base.id)
    state.completed_sections = ["education"]
    card = engine.next_card(base, state)
    assert card.step_id == "experience:add"
    assert card.options == ["实习", "工作", "项目", "校园经历"]


def test_engine_returns_interview_card_when_basics_filled():
    base = make_base()
    base.educations.append(Education(school="某大学", major="统计", start="2020-09"))
    experience = base.add_experience("星河科技", "实习生")
    experience.type = ExperienceType.INTERNSHIP
    experience.start = "2024-06"
    state = QuestionnaireState(fact_base_id=base.id)
    state.completed_sections = ["education"]
    card = engine.next_card(base, state)
    assert card.step_id == f"experience:{experience.id}:interview"
    assert card.kind is QuestionKind.INTERVIEW


def test_engine_summary_card_reads_version_options():
    base = make_base()
    base.educations.append(Education(school="某大学", major="统计", start="2020-09"))
    experience = base.add_experience("星河科技", "实习生")
    experience.start = "2024-06"
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
        FactValue(text="被团队采用", confidence=ConfidenceStatus.CONFIRMED)
    ]
    base.profile.skills = ["SQL"]
    state = QuestionnaireState(fact_base_id=base.id)
    state.completed_sections = ["education", "experience"]
    version = ResumeVersion(
        fact_base_id=base.id, name="默认版本", base_revision=0,
        summary_options=["稳重可靠，善于协作。", "目标导向，数据驱动。"],
    )
    card = engine.next_card(base, state, version=version)
    assert card.step_id == "summary:pick"
    assert card.options == version.summary_options


def make_service():
    fact_bases = FactBaseService(InMemoryFactBaseRepository())
    base = fact_bases.create()
    questionnaire = QuestionnaireService(
        fact_bases, InMemoryQuestionnaireRepository(), QuestionnaireEngine(),
    )
    return questionnaire, base


def test_service_answer_persists_profile_and_advances():
    questionnaire, base = make_service()
    questionnaire.answer(base.id, "profile:name", value="王明")
    questionnaire.answer(base.id, "profile:email", value="wang@example.com")
    questionnaire.answer(base.id, "profile:phone", value="13800000000")
    questionnaire.skip(base.id, "profile:location")
    questionnaire.skip(base.id, "profile:links")
    card = questionnaire.next_card(base.id)
    assert card.step_id == "target:role"
    loaded = questionnaire.fact_bases.get(base.id)
    assert loaded.profile.name == "王明"
    assert loaded.revision == 3


def test_skip_advances_card():
    questionnaire, base = make_service()
    card = questionnaire.next_card(base.id)
    assert card.step_id == "profile:name"
    card = questionnaire.skip(base.id, "profile:name")
    assert card.step_id == "profile:email"


def test_answer_rejects_bad_period():
    questionnaire, base = make_service()
    questionnaire.answer(base.id, "profile:name", value="王明")
    questionnaire.answer(base.id, "profile:email", value="wang@example.com")
    questionnaire.answer(base.id, "profile:phone", value="13800000000")
    questionnaire.answer(base.id, "target:role", value="数据分析师")
    questionnaire.answer(base.id, "education:add", value="开始填写")
    questionnaire.answer(base.id, "education:new:school", value="某大学")
    loaded = questionnaire.fact_bases.get(base.id)
    education_id = loaded.educations[0].id
    with pytest.raises(ValueError):
        questionnaire.answer(
            base.id, f"education:{education_id}:period",
            extra={"start": "2024-13", "end": ""},
        )


def test_experience_choice_creates_typed_experience():
    questionnaire, base = make_service()
    for step_id, value in [
        ("profile:name", "王明"),
        ("profile:email", "wang@example.com"),
        ("profile:phone", "13800000000"),
        ("target:role", "数据分析师"),
    ]:
        questionnaire.answer(base.id, step_id, value=value)
    questionnaire.skip(base.id, "profile:location")
    questionnaire.skip(base.id, "profile:links")
    questionnaire.skip(base.id, "target:city")
    questionnaire.skip(base.id, "education:add")
    card = questionnaire.next_card(base.id)
    assert card.step_id == "experience:add"
    questionnaire.answer(base.id, "experience:add", value="实习")
    loaded = questionnaire.fact_bases.get(base.id)
    assert loaded.experiences[0].type is ExperienceType.INTERNSHIP
    card = questionnaire.next_card(base.id)
    assert card.step_id == f"experience:{loaded.experiences[0].id}:organization"


class FakeCourseAdvisor:
    def recommend(self, major):
        return ["机器学习"]


class FakeSkillAdvisor:
    def extract(self, facts_text):
        return ["SQL", "Python"]


def test_course_options_merge_catalog_and_advisor():
    fact_bases = FactBaseService(InMemoryFactBaseRepository())
    base = fact_bases.create()
    questionnaire = QuestionnaireService(
        fact_bases, InMemoryQuestionnaireRepository(), QuestionnaireEngine(),
        course_advisor=FakeCourseAdvisor(),
    )
    questionnaire.answer(base.id, "profile:name", value="王明")
    questionnaire.answer(base.id, "profile:email", value="wang@example.com")
    questionnaire.answer(base.id, "profile:phone", value="13800000000")
    questionnaire.skip(base.id, "profile:location")
    questionnaire.skip(base.id, "profile:links")
    questionnaire.answer(base.id, "target:role", value="数据分析师")
    questionnaire.skip(base.id, "target:city")
    questionnaire.answer(base.id, "education:add", value="开始填写")
    questionnaire.answer(base.id, "education:new:school", value="某大学")
    loaded = questionnaire.fact_bases.get(base.id)
    education_id = loaded.educations[0].id
    questionnaire.answer(
        base.id, f"education:{education_id}:major", value="计算机科学与技术"
    )
    questionnaire.answer(base.id, f"education:{education_id}:degree", value="本科")
    questionnaire.answer(
        base.id, f"education:{education_id}:period",
        extra={"start": "2020-09", "end": ""},
    )
    card = questionnaire.next_card(base.id)
    assert card.step_id == f"education:{education_id}:courses"
    assert "数据结构" in card.options
    assert "机器学习（AI 推荐）" in card.options


def test_course_answer_strips_ai_suffix():
    fact_bases = FactBaseService(InMemoryFactBaseRepository())
    base = fact_bases.create()
    questionnaire = QuestionnaireService(
        fact_bases, InMemoryQuestionnaireRepository(), QuestionnaireEngine(),
        course_advisor=FakeCourseAdvisor(),
    )
    questionnaire.answer(base.id, "profile:name", value="王明")
    questionnaire.answer(base.id, "profile:email", value="wang@example.com")
    questionnaire.answer(base.id, "profile:phone", value="13800000000")
    questionnaire.answer(base.id, "target:role", value="数据分析师")
    questionnaire.answer(base.id, "education:add", value="开始填写")
    questionnaire.answer(base.id, "education:new:school", value="某大学")
    loaded = questionnaire.fact_bases.get(base.id)
    education_id = loaded.educations[0].id
    questionnaire.answer(
        base.id, f"education:{education_id}:major", value="计算机科学与技术"
    )
    questionnaire.answer(
        base.id, f"education:{education_id}:courses",
        values=["数据结构", "机器学习（AI 推荐）"],
    )
    loaded = questionnaire.fact_bases.get(base.id)
    assert loaded.educations[0].core_courses == ["数据结构", "机器学习"]


def test_skills_options_merge_linked_and_advisor():
    base = CareerFactBase()
    base.target.role = "数据分析师"
    base.target.country = "东京"
    base.profile.name = "王明"
    base.profile.email = "wang@example.com"
    base.profile.phone = "13800000000"
    base.profile.location = "东京"
    base.profile.links = ["https://example.com"]
    base.educations.append(Education(school="某大学", major="统计", start="2020-09"))
    experience = base.add_experience("星河科技", "实习生")
    experience.linked_skills = ["Excel"]
    experience.start = "2024-06"
    experience.statements[QualityDimension.CONTEXT] = [
        FactValue(text="业务需要留存分析", confidence=ConfidenceStatus.CONFIRMED)
    ]
    experience.statements[QualityDimension.RESPONSIBILITY] = [
        FactValue(text="负责看板搭建", confidence=ConfidenceStatus.CONFIRMED)
    ]
    experience.statements[QualityDimension.ACTION] = [
        FactValue(text="用 SQL 写查询", confidence=ConfidenceStatus.CONFIRMED)
    ]
    experience.statements[QualityDimension.RESULT] = [
        FactValue(text="被团队采用", confidence=ConfidenceStatus.CONFIRMED)
    ]
    state = QuestionnaireState(
        fact_base_id=base.id, completed_sections=["education", "experience"]
    )
    repository = InMemoryQuestionnaireRepository([state])
    questionnaire = QuestionnaireService(
        FactBaseService(InMemoryFactBaseRepository([base])),
        repository,
        QuestionnaireEngine(),
        skill_advisor=FakeSkillAdvisor(),
    )
    card = questionnaire.next_card(base.id)
    assert card.step_id == "skills:tags"
    assert "Excel" in card.options
    assert "SQL" in card.options


def test_experience_period_present_saves_empty_end():
    """「至今」必须存空串而非 None（Experience.end 是 str，None 会损坏 payload 重载）。"""
    questionnaire, base = make_service()
    questionnaire.answer(base.id, "profile:name", value="王明")
    questionnaire.answer(base.id, "profile:email", value="wang@example.com")
    questionnaire.answer(base.id, "profile:phone", value="13800000000")
    questionnaire.skip(base.id, "profile:location")
    questionnaire.skip(base.id, "profile:links")
    questionnaire.answer(base.id, "target:role", value="数据分析师")
    questionnaire.skip(base.id, "target:city")
    questionnaire.skip(base.id, "education:add")
    questionnaire.answer(base.id, "experience:add", value="实习")
    loaded = questionnaire.fact_bases.get(base.id)
    experience_id = loaded.experiences[0].id
    questionnaire.answer(base.id, f"experience:{experience_id}:organization", value="星河科技")
    questionnaire.answer(base.id, f"experience:{experience_id}:role", value="数据分析实习生")
    questionnaire.answer(
        base.id, f"experience:{experience_id}:period",
        extra={"start": "2024-06", "end": ""},
    )
    reloaded = questionnaire.fact_bases.get(base.id)  # 重载即验证 payload 合法
    assert reloaded.experiences[0].end == ""
    assert reloaded.experiences[0].start == "2024-06"


class FakeGuide:
    def analyze_job(self, role):
        return ["岗位要点一", "岗位要点二"]

    def experience_options(self, role):
        return [
            {"label": "产品实习", "type": "internship"},
            {"label": "用户调研项目", "type": "project"},
        ]

    def followup_options(self, role, text, dimension):
        return []


def test_guide_generates_job_analysis_and_experience_options():
    fact_bases = FactBaseService(InMemoryFactBaseRepository())
    base = fact_bases.create()
    questionnaire = QuestionnaireService(
        fact_bases, InMemoryQuestionnaireRepository(), QuestionnaireEngine(),
        guide=FakeGuide(),
    )
    questionnaire.answer(base.id, "profile:name", value="王明")
    questionnaire.answer(base.id, "profile:email", value="wang@example.com")
    questionnaire.answer(base.id, "profile:phone", value="13800000000")
    questionnaire.skip(base.id, "profile:location")
    questionnaire.skip(base.id, "profile:links")
    questionnaire.answer(base.id, "target:role", value="产品经理")
    questionnaire.skip(base.id, "target:city")
    questionnaire.skip(base.id, "education:add")
    card = questionnaire.next_card(base.id)
    assert card.step_id == "experience:add"
    assert card.options == ["产品实习", "用户调研项目"]
    state = questionnaire._state(base.id)
    assert state.job_analysis == ["岗位要点一", "岗位要点二"]
    assert state.experience_type_map == {
        "产品实习": "internship", "用户调研项目": "project",
    }


def test_guide_option_creates_typed_experience():
    fact_bases = FactBaseService(InMemoryFactBaseRepository())
    base = fact_bases.create()
    questionnaire = QuestionnaireService(
        fact_bases, InMemoryQuestionnaireRepository(), QuestionnaireEngine(),
        guide=FakeGuide(),
    )
    questionnaire.answer(base.id, "profile:name", value="王明")
    questionnaire.answer(base.id, "profile:email", value="wang@example.com")
    questionnaire.answer(base.id, "profile:phone", value="13800000000")
    questionnaire.skip(base.id, "profile:location")
    questionnaire.skip(base.id, "profile:links")
    questionnaire.answer(base.id, "target:role", value="产品经理")
    questionnaire.skip(base.id, "target:city")
    questionnaire.skip(base.id, "education:add")
    questionnaire.answer(base.id, "experience:add", value="产品实习")
    loaded = questionnaire.fact_bases.get(base.id)
    assert loaded.experiences[0].type is ExperienceType.INTERNSHIP
    # 自填：不在映射里 → 默认项目类型，且文本预填为组织名
    questionnaire.answer(base.id, "experience:more", value="自己组织的读书会")
    loaded = questionnaire.fact_bases.get(base.id)
    assert loaded.experiences[1].type is ExperienceType.PROJECT
    assert loaded.experiences[1].organization == "自己组织的读书会"
