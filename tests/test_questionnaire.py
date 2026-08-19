from uuid import uuid4

import pytest

from resume_agent.application.fact_base_service import FactBaseService
from resume_agent.application.questionnaire import (
    QuestionKind, QuestionnaireEngine, QuestionnaireService,
)
from resume_agent.domain.models import (
    CareerFactBase, ConfidenceStatus, Education, Experience, ExperienceType,
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
    base.profile.certificates = ["CET-6 550"]
    base.profile.language_scores = ["雅思 7.0"]
    state = QuestionnaireState(fact_base_id=base.id)
    state.completed_sections = ["education", "experience"]
    version = ResumeVersion(
        fact_base_id=base.id, name="默认版本", base_revision=0,
        summary_options=["稳重可靠，善于协作。", "目标导向，数据驱动。"],
    )
    card = engine.next_card(base, state, version=version)
    assert card.step_id == "summary:pick"
    assert card.options == version.summary_options


def test_engine_summary_card_hidden_after_answer():
    """勾选自我评价后不得再次弹出该卡（回归：点确认无法进行下一步）。"""
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
    base.profile.certificates = ["CET-6 550"]
    base.profile.language_scores = ["雅思 7.0"]
    state = QuestionnaireState(fact_base_id=base.id)
    state.completed_sections = ["education", "experience"]
    state.answered = ["summary:pick"]
    version = ResumeVersion(
        fact_base_id=base.id, name="默认版本", base_revision=0,
        summary_options=["稳重可靠，善于协作。"],
    )
    card = engine.next_card(base, state, version=version)
    assert card is None


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
    questionnaire.answer(base.id, "education:add", value="硕士")
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
    questionnaire.answer(base.id, "education:add", value="硕士")
    questionnaire.answer(base.id, "education:new:school", value="某大学")
    loaded = questionnaire.fact_bases.get(base.id)
    education_id = loaded.educations[0].id
    questionnaire.answer(
        base.id, f"education:{education_id}:major", value="计算机科学与技术"
    )
    questionnaire.answer(
        base.id, f"education:{education_id}:period",
        extra={"start": "2020-09", "end": ""},
    )
    for field in ("gpa", "rank", "research", "thesis"):
        questionnaire.skip(base.id, f"education:{education_id}:{field}")
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
    questionnaire.answer(base.id, "education:add", value="硕士")
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
    def generate_jd(self, role, company=""):
        return "岗位职责：负责数据分析与产品迭代。"

    def analyze_job(self, role, jd=""):
        return ["岗位要点一", "岗位要点二"]

    def experience_options(self, role, previous=None, jd=""):
        return [
            {"label": "产品实习", "type": "internship"},
            {"label": "用户调研项目", "type": "project"},
        ]

    def followup_options(self, role, text, dimension, previous=None):
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


def test_engine_role_card_offline_options_without_guide():
    base = make_base()
    experience = Experience(organization="星河科技", role="")
    base.experiences.append(experience)
    state = QuestionnaireState(fact_base_id=base.id)
    state.skipped = ["education:add"]
    card = engine.next_card(base, state)
    assert card.step_id == f"experience:{experience.id}:role"
    assert card.kind is QuestionKind.CHOICE_FREE
    assert card.skippable is True  # 岗位可跳过
    # 工作经历 → 正式岗位选项
    assert card.options == ["产品经理", "运营专员", "数据分析师", "项目经理", "市场专员"]


def test_project_experience_asks_name_only_without_role():
    base = make_base()
    experience = Experience(
        organization="", role="", type=ExperienceType.PROJECT,
    )
    base.experiences.append(experience)
    state = QuestionnaireState(fact_base_id=base.id)
    state.skipped = ["education:add"]
    # 先问 GitHub 链接（可跳过），跳过后才问项目名
    card = engine.next_card(base, state)
    assert card.step_id == f"experience:{experience.id}:github"
    state.skipped.append(f"experience:{experience.id}:github")
    card = engine.next_card(base, state)
    assert card.step_id == f"experience:{experience.id}:organization"
    assert "项目" in card.prompt
    # 填完项目名后直接问时间，不再问岗位
    state.answered = [f"experience:{experience.id}:organization"]
    experience.organization = "全国商赛项目"
    card = engine.next_card(base, state)
    assert card.step_id == f"experience:{experience.id}:period"


def test_internship_role_options_differ_by_type():
    base = make_base()
    experience = Experience(
        organization="某互联网公司", role="", type=ExperienceType.INTERNSHIP,
    )
    base.experiences.append(experience)
    state = QuestionnaireState(fact_base_id=base.id)
    state.skipped = ["education:add"]
    card = engine.next_card(base, state)
    assert card.step_id == f"experience:{experience.id}:role"
    assert "产品实习生" in card.options
    assert "数据分析实习生" in card.options


def test_engine_role_card_uses_guide_role_options():
    class RoleGuide:
        def followup_options(self, role, text, dimension):
            assert dimension == "role"
            return ["数据分析实习生", "产品实习生"]

    base = make_base()
    experience = Experience(organization="星河科技", role="")
    base.experiences.append(experience)
    state = QuestionnaireState(fact_base_id=base.id)
    state.skipped = ["education:add"]
    card = QuestionnaireEngine(guide=RoleGuide()).next_card(base, state)
    assert card.step_id == f"experience:{experience.id}:role"
    assert card.options == ["数据分析实习生", "产品实习生"]


def test_education_add_answer_advances_to_school_card():
    """回答最高学历后必须推进到学校名称，而不是停在原卡（回归：确认无反应）。"""
    questionnaire, base = make_service()
    questionnaire.answer(base.id, "profile:name", value="王明")
    questionnaire.answer(base.id, "profile:email", value="wang@example.com")
    questionnaire.answer(base.id, "profile:phone", value="13800000000")
    questionnaire.skip(base.id, "profile:location")
    questionnaire.skip(base.id, "profile:links")
    questionnaire.answer(base.id, "target:role", value="数据分析师")
    questionnaire.skip(base.id, "target:city")
    card = questionnaire.next_card(base.id)
    assert card.step_id == "education:add"
    questionnaire.answer(base.id, "education:add", value="硕士")
    card = questionnaire.next_card(base.id)
    assert card.step_id == "education:new:school"


def test_education_degree_first_flow():
    """先问最高学历→学校（带学位）→专业→时间→GPA/排名/方向/论文→上一段学历。"""
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

    card = questionnaire.next_card(base.id)
    assert card.step_id == "education:add"
    assert "博士" in card.options and "硕士" in card.options

    questionnaire.answer(base.id, "education:add", value="硕士")
    card = questionnaire.next_card(base.id)
    assert card.step_id == "education:new:school"
    assert "硕士" in card.prompt

    questionnaire.answer(base.id, "education:new:school", value="华中科技大学")
    loaded = questionnaire.fact_bases.get(base.id)
    education_id = loaded.educations[0].id
    assert loaded.educations[0].degree == "硕士"

    card = questionnaire.next_card(base.id)
    assert card.step_id == f"education:{education_id}:major"
    # 理工类学校：工科专业优先
    assert card.options[0] == "计算机科学与技术"

    questionnaire.answer(base.id, f"education:{education_id}:major", value="计算机科学与技术")
    questionnaire.answer(
        base.id, f"education:{education_id}:period",
        extra={"start": "2023-09", "end": ""},
    )
    questionnaire.answer(base.id, f"education:{education_id}:gpa", value="3.7/4.0")
    questionnaire.answer(base.id, f"education:{education_id}:rank", value="前10%")
    questionnaire.answer(base.id, f"education:{education_id}:research", value="数据挖掘")
    questionnaire.answer(base.id, f"education:{education_id}:thesis", value="基于深度学习的推荐系统")
    questionnaire.skip(base.id, f"education:{education_id}:courses")

    card = questionnaire.next_card(base.id)
    assert card.step_id == "education:more"
    questionnaire.answer(base.id, "education:more", value="添加上一段学历")

    card = questionnaire.next_card(base.id)
    assert card.step_id == "education:new:degree"
    questionnaire.answer(base.id, "education:new:degree", value="本科")
    card = questionnaire.next_card(base.id)
    assert card.step_id == "education:new:school"
    assert "本科" in card.prompt
    questionnaire.answer(base.id, "education:new:school", value="某大学")

    loaded = questionnaire.fact_bases.get(base.id)
    assert [item.degree for item in loaded.educations] == ["硕士", "本科"]
    assert loaded.educations[0].gpa == "3.7/4.0"
    assert loaded.educations[0].rank == "前10%"
    assert loaded.educations[0].research_direction == "数据挖掘"
    assert loaded.educations[0].thesis == "基于深度学习的推荐系统"


def test_regenerate_experience_options_passes_previous_and_updates_map():
    calls = {}

    class RegenerateGuide:
        def generate_jd(self, role, company=""):
            return "JD 文本"

        def analyze_job(self, role, jd=""):
            return []

        def experience_options(self, role, previous=None, jd=""):
            calls["previous"] = list(previous or [])
            return [
                {"label": "Agent 开发项目", "type": "project"},
                {"label": "AI 产品实习", "type": "internship"},
            ]

        def followup_options(self, role, text, dimension, previous=None):
            return []

    fact_bases = FactBaseService(InMemoryFactBaseRepository())
    base = fact_bases.create()
    regenerate_guide = RegenerateGuide()
    questionnaire = QuestionnaireService(
        fact_bases, InMemoryQuestionnaireRepository(),
        QuestionnaireEngine(guide=regenerate_guide),
        guide=regenerate_guide,
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
    assert card.regeneratable is True
    initial_labels = list(card.options)

    options = questionnaire.regenerate_options(base.id, "experience:add")
    assert calls["previous"] == initial_labels
    assert options == ["Agent 开发项目", "AI 产品实习"]
    state = questionnaire._state(base.id)
    assert state.experience_type_map == {
        "Agent 开发项目": "project", "AI 产品实习": "internship",
    }


def test_regenerate_role_options_passes_previous():
    calls = []

    class RoleGuide:
        def generate_jd(self, role, company=""):
            return "JD 文本"

        def analyze_job(self, role, jd=""):
            return []

        def experience_options(self, role, previous=None, jd=""):
            return [{"label": "产品实习", "type": "internship"}]

        def followup_options(self, role, text, dimension, previous=None):
            calls.append(list(previous or []))
            return [f"新岗位{len(calls)}"]

    fact_bases = FactBaseService(InMemoryFactBaseRepository())
    base = fact_bases.create()
    role_guide = RoleGuide()
    questionnaire = QuestionnaireService(
        fact_bases, InMemoryQuestionnaireRepository(),
        QuestionnaireEngine(guide=role_guide),
        guide=role_guide,
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
    experience_id = loaded.experiences[0].id
    questionnaire.answer(base.id, f"experience:{experience_id}:organization", value="字节跳动")
    card = questionnaire.next_card(base.id)
    assert card.step_id == f"experience:{experience_id}:role"
    assert card.regeneratable is True
    assert card.options == ["新岗位1"]

    options = questionnaire.regenerate_options(base.id, f"experience:{experience_id}:role")
    assert calls[-1] == ["新岗位1"]
    assert options == ["新岗位2"]


def test_experience_name_card_deletable_for_mispick():
    base = make_base()
    experience = Experience(organization="", role="", type=ExperienceType.PROJECT)
    base.experiences.append(experience)
    state = QuestionnaireState(fact_base_id=base.id)
    state.skipped = ["education:add"]
    card = engine.next_card(base, state)
    # 项目先问 GitHub 链接（可删），跳过后的项目名卡同样可删
    assert card.step_id == f"experience:{experience.id}:github"
    assert card.deletable is True
    assert card.skippable is True
    state.skipped.append(f"experience:{experience.id}:github")
    card = engine.next_card(base, state)
    assert card.step_id == f"experience:{experience.id}:organization"
    assert card.deletable is True
    assert card.skippable is False

    experience.organization = "某项目"
    card = engine.next_card(base, state)
    assert card.step_id == f"experience:{experience.id}:period"
    assert card.deletable is False


def test_education_degree_card_skippable():
    questionnaire, base = make_service()
    questionnaire.answer(base.id, "profile:name", value="王明")
    questionnaire.answer(base.id, "profile:email", value="wang@example.com")
    questionnaire.answer(base.id, "profile:phone", value="13800000000")
    questionnaire.skip(base.id, "profile:location")
    questionnaire.skip(base.id, "profile:links")
    questionnaire.answer(base.id, "target:role", value="数据分析师")
    questionnaire.skip(base.id, "target:city")
    card = questionnaire.next_card(base.id)
    assert card.step_id == "education:add"
    assert card.skippable is True
    questionnaire.skip(base.id, "education:add")
    card = questionnaire.next_card(base.id)
    assert card.step_id == "experience:add"


def test_skip_school_cancels_pending_education():
    questionnaire, base = make_service()
    questionnaire.answer(base.id, "profile:name", value="王明")
    questionnaire.answer(base.id, "profile:email", value="wang@example.com")
    questionnaire.answer(base.id, "profile:phone", value="13800000000")
    questionnaire.skip(base.id, "profile:location")
    questionnaire.skip(base.id, "profile:links")
    questionnaire.answer(base.id, "target:role", value="数据分析师")
    questionnaire.skip(base.id, "target:city")
    questionnaire.answer(base.id, "education:add", value="硕士")
    card = questionnaire.next_card(base.id)
    assert card.step_id == "education:new:school"
    assert card.skippable is True
    questionnaire.skip(base.id, "education:new:school")
    card = questionnaire.next_card(base.id)
    assert card.step_id == "experience:add"


def test_skip_new_degree_returns_to_education_more():
    base = make_base()
    base.educations.append(
        Education(school="某大学", major="统计", degree="本科", start="2020-09")
    )
    state = QuestionnaireState(fact_base_id=base.id)
    state.edited_education_id = None
    state.skipped = ["education:new:degree"]
    card = engine.next_card(base, state)
    assert card.step_id == "education:more"


def test_skip_education_more_completes_education_section():
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
    questionnaire.answer(base.id, "education:add", value="本科")
    questionnaire.answer(base.id, "education:new:school", value="某大学")
    loaded = questionnaire.fact_bases.get(base.id)
    education_id = loaded.educations[0].id
    questionnaire.answer(base.id, f"education:{education_id}:major", value="统计")
    questionnaire.answer(
        base.id, f"education:{education_id}:period",
        extra={"start": "2020-09", "end": "2024-06"},
    )
    for field in ("gpa", "rank", "research", "thesis", "courses"):
        questionnaire.skip(base.id, f"education:{education_id}:{field}")
    card = questionnaire.next_card(base.id)
    assert card.step_id == "education:more"
    # 跳过「是否还有上一段学历」= 没有更多了
    questionnaire.skip(base.id, "education:more")
    card = questionnaire.next_card(base.id)
    assert card.step_id == "experience:add"


def test_skip_experience_more_completes_experience_section():
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
    questionnaire.answer(base.id, "experience:add", value="实习")
    loaded = questionnaire.fact_bases.get(base.id)
    experience_id = loaded.experiences[0].id
    questionnaire.answer(base.id, f"experience:{experience_id}:organization", value="星河科技")
    questionnaire.answer(base.id, f"experience:{experience_id}:role", value="实习生")
    questionnaire.answer(
        base.id, f"experience:{experience_id}:period",
        extra={"start": "2024-06", "end": ""},
    )
    questionnaire.skip(base.id, f"experience:{experience_id}:interview")
    card = questionnaire.next_card(base.id)
    assert card.step_id == "experience:more"
    questionnaire.skip(base.id, "experience:more")
    card = questionnaire.next_card(base.id)
    assert card.step_id == "skills:tags"


def test_github_import_flow_for_project_experience():
    """项目经历：先问 GitHub 链接 → 列候选 → 点选后写入项目名。"""
    def fake_fetcher(url):
        return [
            {"full_name": "wangming/agent-demo", "description": "", "language": "Python", "stars": 3, "html_url": ""},
            {"full_name": "wangming/resume-tool", "description": "", "language": "Python", "stars": 9, "html_url": ""},
        ]

    fact_bases = FactBaseService(InMemoryFactBaseRepository())
    base = fact_bases.create()
    questionnaire = QuestionnaireService(
        fact_bases, InMemoryQuestionnaireRepository(), QuestionnaireEngine(),
        github_fetcher=fake_fetcher,
    )
    questionnaire.answer(base.id, "profile:name", value="王明")
    questionnaire.answer(base.id, "profile:email", value="wang@example.com")
    questionnaire.answer(base.id, "profile:phone", value="13800000000")
    questionnaire.skip(base.id, "profile:location")
    questionnaire.skip(base.id, "profile:links")
    questionnaire.answer(base.id, "target:role", value="产品经理")
    questionnaire.skip(base.id, "target:city")
    questionnaire.skip(base.id, "education:add")
    # 选一个项目类经历
    card = questionnaire.next_card(base.id)
    project_label = next(
        label for label in card.options
        if "项目" in label or "开发" in label
    )
    questionnaire.answer(base.id, "experience:add", value=project_label)
    loaded = questionnaire.fact_bases.get(base.id)
    experience_id = loaded.experiences[0].id
    assert loaded.experiences[0].type is ExperienceType.PROJECT

    card = questionnaire.next_card(base.id)
    assert card.step_id == f"experience:{experience_id}:github"
    assert card.skippable is True

    questionnaire.answer(
        base.id, f"experience:{experience_id}:github",
        value="https://github.com/wangming",
    )
    card = questionnaire.next_card(base.id)
    assert card.step_id == f"experience:{experience_id}:project_pick"
    assert card.options == ["wangming/agent-demo", "wangming/resume-tool"]

    questionnaire.answer(
        base.id, f"experience:{experience_id}:project_pick",
        value="wangming/resume-tool",
    )
    loaded = questionnaire.fact_bases.get(base.id)
    assert loaded.experiences[0].organization == "wangming/resume-tool"
    card = questionnaire.next_card(base.id)
    assert card.step_id == f"experience:{experience_id}:period"


def test_github_project_pick_attaches_source_context():
    """点选 GitHub 项目后，把 README/描述/语言等抓成项目背景资料。"""
    def fake_fetcher(url):
        return [{"full_name": "wangming/resume-tool", "description": "",
                 "language": "Python", "stars": 9, "html_url": ""}]

    def fake_context_fetcher(full_name):
        assert full_name == "wangming/resume-tool"
        return {
            "description": "智能简历生成器",
            "language": "Python",
            "topics": "resume、llm",
            "readme": "# ResumeAgent\n\n基于大模型的简历生成工具。",
        }

    fact_bases = FactBaseService(InMemoryFactBaseRepository())
    base = fact_bases.create()
    questionnaire = QuestionnaireService(
        fact_bases, InMemoryQuestionnaireRepository(), QuestionnaireEngine(),
        github_fetcher=fake_fetcher,
        github_context_fetcher=fake_context_fetcher,
    )
    questionnaire.answer(base.id, "profile:name", value="王明")
    questionnaire.answer(base.id, "profile:email", value="wang@example.com")
    questionnaire.answer(base.id, "profile:phone", value="13800000000")
    questionnaire.skip(base.id, "profile:location")
    questionnaire.skip(base.id, "profile:links")
    questionnaire.answer(base.id, "target:role", value="后端工程师")
    questionnaire.skip(base.id, "target:city")
    questionnaire.skip(base.id, "education:add")
    card = questionnaire.next_card(base.id)
    project_label = next(
        label for label in card.options
        if "项目" in label or "开发" in label
    )
    questionnaire.answer(base.id, "experience:add", value=project_label)
    loaded = questionnaire.fact_bases.get(base.id)
    experience_id = loaded.experiences[0].id
    questionnaire.answer(
        base.id, f"experience:{experience_id}:github",
        value="https://github.com/wangming",
    )
    questionnaire.answer(
        base.id, f"experience:{experience_id}:project_pick",
        value="wangming/resume-tool",
    )
    loaded = questionnaire.fact_bases.get(base.id)
    experience = loaded.experiences[0]
    assert experience.organization == "wangming/resume-tool"
    assert "项目简介：智能简历生成器" in experience.source_context
    assert "主要语言：Python" in experience.source_context
    assert "主题：resume、llm" in experience.source_context
    assert "README 摘要：# ResumeAgent" in experience.source_context
    card = questionnaire.next_card(base.id)
    assert card.step_id == f"experience:{experience_id}:period"


def test_github_context_fetch_failure_keeps_flow_alive():
    """背景资料抓取失败不影响点选流程，source_context 留空。"""
    fact_bases = FactBaseService(InMemoryFactBaseRepository())
    base = fact_bases.create()
    questionnaire = QuestionnaireService(
        fact_bases, InMemoryQuestionnaireRepository(), QuestionnaireEngine(),
        github_fetcher=lambda url: [
            {"full_name": "wangming/resume-tool", "description": "",
             "language": "Python", "stars": 9, "html_url": ""},
        ],
        github_context_fetcher=lambda full_name: (_ for _ in ()).throw(
            RuntimeError("network down")),
    )
    questionnaire.answer(base.id, "profile:name", value="王明")
    questionnaire.answer(base.id, "profile:email", value="wang@example.com")
    questionnaire.answer(base.id, "profile:phone", value="13800000000")
    questionnaire.skip(base.id, "profile:location")
    questionnaire.skip(base.id, "profile:links")
    questionnaire.answer(base.id, "target:role", value="后端工程师")
    questionnaire.skip(base.id, "target:city")
    questionnaire.skip(base.id, "education:add")
    card = questionnaire.next_card(base.id)
    project_label = next(
        label for label in card.options
        if "项目" in label or "开发" in label
    )
    questionnaire.answer(base.id, "experience:add", value=project_label)
    loaded = questionnaire.fact_bases.get(base.id)
    experience_id = loaded.experiences[0].id
    questionnaire.answer(
        base.id, f"experience:{experience_id}:github",
        value="https://github.com/wangming",
    )
    questionnaire.answer(
        base.id, f"experience:{experience_id}:project_pick",
        value="wangming/resume-tool",
    )
    loaded = questionnaire.fact_bases.get(base.id)
    assert loaded.experiences[0].organization == "wangming/resume-tool"
    assert loaded.experiences[0].source_context == ""
    card = questionnaire.next_card(base.id)
    assert card.step_id == f"experience:{experience_id}:period"


def test_github_step_skip_falls_back_to_manual_name():
    fact_bases = FactBaseService(InMemoryFactBaseRepository())
    base = fact_bases.create()
    questionnaire = QuestionnaireService(
        fact_bases, InMemoryQuestionnaireRepository(), QuestionnaireEngine(),
        github_fetcher=lambda url: [],
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
    questionnaire.answer(base.id, "experience:add", value=card.options[0])
    loaded = questionnaire.fact_bases.get(base.id)
    experience_id = loaded.experiences[0].id
    if loaded.experiences[0].type is not ExperienceType.PROJECT:
        # 直接构造项目经历场景
        loaded.experiences[0].type = ExperienceType.PROJECT
        loaded.experiences[0].organization = ""
        questionnaire.fact_bases.save(loaded, expected_revision=loaded.revision)
        loaded = questionnaire.fact_bases.get(base.id)
    card = questionnaire.next_card(base.id)
    github_step = f"experience:{experience_id}:github"
    assert card.step_id == github_step
    questionnaire.skip(base.id, github_step)
    card = questionnaire.next_card(base.id)
    assert card.step_id == f"experience:{experience_id}:organization"
    assert "项目" in card.prompt


def test_refresh_auto_generates_jd_when_missing():
    """岗位已填但没贴 JD 时，自动生成岗位描述并让分析/选项结合 JD。"""
    seen = {}

    class JdGuide:
        def generate_jd(self, role, company=""):
            seen["company"] = company
            return f"{role}的岗位描述：负责数据分析。"

        def analyze_job(self, role, jd=""):
            seen["analyze_jd"] = jd
            return ["要点一"]

        def experience_options(self, role, previous=None, jd=""):
            seen["options_jd"] = jd
            return [{"label": "数据分析项目", "type": "project"}]

        def followup_options(self, role, text, dimension, previous=None):
            return []

    fact_bases = FactBaseService(InMemoryFactBaseRepository())
    base = fact_bases.create()
    questionnaire = QuestionnaireService(
        fact_bases, InMemoryQuestionnaireRepository(), QuestionnaireEngine(),
        guide=JdGuide(),
    )
    questionnaire.answer(base.id, "profile:name", value="王明")
    questionnaire.answer(base.id, "profile:email", value="wang@example.com")
    questionnaire.answer(base.id, "profile:phone", value="13800000000")
    questionnaire.skip(base.id, "profile:location")
    questionnaire.skip(base.id, "profile:links")
    questionnaire.answer(base.id, "target:role", value="数据分析师")
    questionnaire.skip(base.id, "target:city")
    questionnaire.skip(base.id, "education:add")
    questionnaire.next_card(base.id)

    loaded = questionnaire.fact_bases.get(base.id)
    assert loaded.target.job_description == "数据分析师的岗位描述：负责数据分析。"
    assert loaded.target.jd_source == "generated"
    assert "数据分析师的岗位描述" in seen["analyze_jd"]
    assert seen["options_jd"] == "数据分析师的岗位描述：负责数据分析。"


def test_user_provided_jd_is_kept():
    """用户粘贴了 JD 时，不再自动生成、也不覆盖。"""
    fact_bases = FactBaseService(InMemoryFactBaseRepository())
    base = fact_bases.create()
    base.target.role = "产品经理"
    base.target.job_description = "用户手写的 JD"
    base.target.jd_source = "user"
    fact_bases.save(base, expected_revision=0)
    questionnaire = QuestionnaireService(
        fact_bases, InMemoryQuestionnaireRepository(), QuestionnaireEngine(),
        guide=FakeGuide(),
    )
    questionnaire.next_card(base.id)

    loaded = questionnaire.fact_bases.get(base.id)
    assert loaded.target.job_description == "用户手写的 JD"
    assert loaded.target.jd_source == "user"
