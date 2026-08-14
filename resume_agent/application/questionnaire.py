"""Deterministic section-ordered questionnaire (zh-first wizard)."""

from enum import Enum
from typing import Callable, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from resume_agent.domain.models import (
    CareerFactBase,
    Education,
    Experience,
    ExperienceType,
    QuestionnaireState,
    ResumeVersion,
    utc_now,
)
from resume_agent.domain.course_catalog import courses_for_major
from resume_agent.domain.quality import evaluate_experience, evaluate_profile_completeness
from resume_agent.domain.questionnaire_steps import (
    DEGREE_OPTIONS,
    EDUCATION_DONE_OPTION,
    EXPERIENCE_DONE_OPTION,
    EXPERIENCE_TYPE_OPTIONS,
    PROFILE_STEPS,
    SECTION_LABELS,
    SECTION_ORDER,
    TARGET_STEPS,
)
from resume_agent.domain.year_month import is_year_month, year_month_le
from resume_agent.application.mentor_guide import OFFLINE_FOLLOWUP_OPTIONS


class QuestionKind(str, Enum):
    TEXT = "text"
    CHOICE = "choice"
    CHOICE_FREE = "choice_free"
    MULTI_CHOICE = "multi_choice"
    YEAR_MONTH_RANGE = "year_month_range"
    INTERVIEW = "interview"


class QuestionCard(BaseModel):
    step_id: str
    section: str
    kind: QuestionKind
    prompt: str
    options: List[str] = Field(default_factory=list)
    value: str = ""
    values: List[str] = Field(default_factory=list)
    extra: Dict[str, str] = Field(default_factory=dict)
    skippable: bool = True


class SectionProgress(BaseModel):
    section: str
    label: str
    done: bool
    current: bool = False


class QuestionnaireEngine:
    """Choose the next unsatisfied question in section order."""

    def __init__(self, options_providers: Optional[Dict[str, Callable]] = None, guide=None):
        self.options_providers = options_providers or {}
        self.guide = guide

    def next_card(self, base, state, version=None):
        for section in SECTION_ORDER:
            card = self._section_card(base, state, section, version)
            if card is not None:
                return card
        return None

    @staticmethod
    def _card(step_id, section, kind, prompt, **fields):
        return QuestionCard(
            step_id=step_id, section=section, kind=kind, prompt=prompt, **fields
        )

    @staticmethod
    def _skipped(state, step_id):
        return step_id in state.skipped

    def _provider(self, name, base, state):
        provider = self.options_providers.get(name)
        return provider(base, state) if provider else []

    def _section_card(self, base, state, section, version):
        if section == "profile":
            return self._profile_card(base, state)
        if section == "target":
            return self._target_card(base, state)
        if section == "education":
            return self._education_card(base, state)
        if section == "experience":
            return self._experience_card(base, state)
        if section == "skills":
            return self._skills_card(base, state)
        return self._summary_card(state, version)

    def _profile_card(self, base, state):
        for field, prompt in PROFILE_STEPS:
            step_id = f"profile:{field}"
            if self._skipped(state, step_id):
                continue
            value = getattr(base.profile, field, "") or ""
            if field == "links":
                value = "\n".join(base.profile.links)
            if not value:
                return self._card(
                    step_id, "profile", QuestionKind.TEXT, prompt,
                    skippable=field in ("location", "links"),
                )
        return None

    def _target_card(self, base, state):
        steps = [
            ("role", base.target.role, TARGET_STEPS[0][1], False),
            ("city", base.target.country, TARGET_STEPS[1][1], True),
        ]
        for field, value, prompt, skippable in steps:
            step_id = f"target:{field}"
            if self._skipped(state, step_id):
                continue
            if not value:
                return self._card(
                    step_id, "target", QuestionKind.TEXT, prompt, skippable=skippable
                )
        return None

    def _education_card(self, base, state):
        if not base.educations:
            if self._skipped(state, "education:add"):
                return None
            if "education:add" in state.answered:
                return self._card(
                    "education:new:school", "education", QuestionKind.TEXT,
                    "学校名称是？", skippable=False,
                )
            return self._card(
                "education:add", "education", QuestionKind.CHOICE,
                "开始填写教育背景？", options=["开始填写"],
            )
        if "education" in state.completed_sections:
            return None
        education = self._edited_education(base, state)
        if education is None:
            return self._card(
                "education:new:school", "education", QuestionKind.TEXT,
                "学校名称是？", skippable=False,
            )
        if not education.school and not self._skipped(state, f"education:{education.id}:school"):
            return self._card(
                f"education:{education.id}:school", "education", QuestionKind.TEXT,
                "学校名称是？", skippable=False,
            )
        if not education.major and not self._skipped(state, f"education:{education.id}:major"):
            return self._card(
                f"education:{education.id}:major", "education", QuestionKind.CHOICE_FREE,
                "所学专业是？（可选推荐项，也可以自己填）",
                options=self._provider("majors", base, state),
            )
        if not education.degree and not self._skipped(state, f"education:{education.id}:degree"):
            return self._card(
                f"education:{education.id}:degree", "education", QuestionKind.CHOICE,
                "最高学历是？", options=DEGREE_OPTIONS,
            )
        if not education.start and not self._skipped(state, f"education:{education.id}:period"):
            return self._card(
                f"education:{education.id}:period", "education",
                QuestionKind.YEAR_MONTH_RANGE,
                "这段教育的起止时间是？（结束留空表示至今）",
                extra={"end": education.end or ""},
            )
        if not education.core_courses and not self._skipped(state, f"education:{education.id}:courses"):
            return self._card(
                f"education:{education.id}:courses", "education",
                QuestionKind.MULTI_CHOICE, "勾选或添加核心课程（可跳过）",
                options=list(state.course_options),
            )
        return self._card(
            "education:more", "education", QuestionKind.CHOICE,
            "是否还有下一段教育经历？",
            options=["添加下一段教育", EDUCATION_DONE_OPTION],
        )

    def _experience_card(self, base, state):
        default_labels = [label for _, label in EXPERIENCE_TYPE_OPTIONS]
        type_options = list(state.experience_type_map.keys()) or default_labels
        if not base.experiences:
            if self._skipped(state, "experience:add"):
                return None
            return self._card(
                "experience:add", "experience", QuestionKind.CHOICE_FREE,
                "你做过以下哪些事情？（选一个，也可以自己补充）",
                options=type_options,
            )
        for experience in base.experiences:
            card = self._experience_field_card(base, state, experience)
            if card is not None:
                return card
        if "experience" in state.completed_sections:
            return None
        return self._card(
            "experience:more", "experience", QuestionKind.CHOICE_FREE,
            "是否还有下一段经历？",
            options=type_options + [EXPERIENCE_DONE_OPTION],
        )

    def _experience_field_card(self, base, state, experience):
        if not experience.organization and not self._skipped(state, f"experience:{experience.id}:organization"):
            return self._card(
                f"experience:{experience.id}:organization", "experience",
                QuestionKind.TEXT, "这段经历的公司、组织或项目名称是？", skippable=False,
            )
        if not experience.role and not self._skipped(state, f"experience:{experience.id}:role"):
            return self._card(
                f"experience:{experience.id}:role", "experience",
                QuestionKind.CHOICE_FREE, "你当时担任的角色是？（点选或自己填写）",
                options=self._role_options(base, experience),
                skippable=False,
            )
        if not experience.start and not self._skipped(state, f"experience:{experience.id}:period"):
            return self._card(
                f"experience:{experience.id}:period", "experience",
                QuestionKind.YEAR_MONTH_RANGE,
                "这段经历的起止时间是？（结束留空表示至今）",
                extra={"end": experience.end or ""},
            )
        if (
            not evaluate_experience(experience).passes_gate
            and not self._skipped(state, f"experience:{experience.id}:interview")
        ):
            return self._card(
                f"experience:{experience.id}:interview", "experience",
                QuestionKind.INTERVIEW,
                "导师会针对这段经历一步步追问（每个问题都有选项可点），攒够证据就能写进简历。",
                skippable=True,
            )
        return None

    def _role_options(self, base, experience):
        """角色候选：优先 LLM 动态生成（结合岗位与经历类型），失败走离线模板。"""
        if self.guide is not None:
            options = self.guide.followup_options(
                base.target.role or "",
                f"{experience.organization or experience.type.value} · 担任角色",
                "role",
            )
            if options:
                return options
        return list(OFFLINE_FOLLOWUP_OPTIONS.get("role", []))

    def _skills_card(self, base, state):
        if base.profile.skills or self._skipped(state, "skills:tags"):
            return None
        return self._card(
            "skills:tags", "skills", QuestionKind.MULTI_CHOICE,
            "勾选或添加你的技能标签（可跳过）",
            options=list(state.skill_options),
            values=list(base.profile.skills),
        )

    def _summary_card(self, state, version):
        if version is None or not version.summary_options or self._skipped(state, "summary:pick"):
            return None
        return self._card(
            "summary:pick", "summary", QuestionKind.MULTI_CHOICE,
            "从备选中勾选 1~2 条自我评价（可稍后重新生成）",
            options=list(version.summary_options),
            values=[version.selected_summary] if version.selected_summary else [],
        )

    @staticmethod
    def _edited_education(base, state):
        for education in base.educations:
            if education.id == state.edited_education_id:
                return education
        return None


class QuestionnaireService:
    """Side-effecting orchestration: writes answers into models, returns next card."""

    def __init__(
        self,
        fact_bases,
        repository,
        engine,
        course_advisor=None,
        skill_advisor=None,
        guide=None,
    ):
        self.fact_bases = fact_bases
        self.repository = repository
        self.engine = engine
        self.course_advisor = course_advisor
        self.skill_advisor = skill_advisor
        self.guide = guide

    def _state(self, fact_base_id):
        try:
            return self.repository.get(fact_base_id)
        except KeyError:
            state = QuestionnaireState(fact_base_id=fact_base_id)
            self.repository.save(state)
            return state

    def _refresh_mentor_candidates(self, base, state):
        """按目标岗位惰性刷新岗位分析与经历类型选项（LLM 失败走离线模板）。"""
        changed = False
        role = base.target.role.strip()
        if self.guide is not None:
            if role and state.job_analysis_role != role:
                state.job_analysis = self.guide.analyze_job(role)
                state.job_analysis_role = role
                changed = True
            if state.experience_options_role != role:
                options = self.guide.experience_options(role)
                state.experience_type_map = {
                    item["label"]: item["type"] for item in options
                }
                state.experience_options_role = role
                changed = True
        elif not state.experience_type_map:
            from resume_agent.application.mentor_guide import offline_experience_options
            state.experience_type_map = {
                item["label"]: item["type"]
                for item in offline_experience_options()
            }
            state.experience_options_role = role
            changed = True
        if changed:
            state.updated_at = utc_now()
            self.repository.save(state)

    def next_card(self, fact_base_id, version=None):
        base = self.fact_bases.get(fact_base_id)
        state = self._state(fact_base_id)
        if not state.skill_options and not base.profile.skills:
            state.skill_options = self._skill_options(base)
            state.updated_at = utc_now()
            self.repository.save(state)
        self._refresh_mentor_candidates(base, state)
        return self.engine.next_card(base, state, version=version)

    def progress(self, fact_base_id, version=None):
        base = self.fact_bases.get(fact_base_id)
        state = self._state(fact_base_id)
        completeness = evaluate_profile_completeness(
            base, version.selected_summary if version else ""
        )
        card = self.engine.next_card(base, state, version=version)
        current_section = card.section if card else ""
        return [
            SectionProgress(
                section=section,
                label=SECTION_LABELS[section],
                done=completeness.sections[section],
                current=section == current_section,
            )
            for section in SECTION_ORDER
        ]

    def answer(self, fact_base_id, step_id, value="", values=None, extra=None):
        values = list(values or [])
        extra = dict(extra or {})
        base = self.fact_bases.get(fact_base_id)
        state = self._state(fact_base_id)
        self._dispatch(base, state, step_id, value, values, extra)
        if step_id not in state.answered:
            state.answered.append(step_id)
        state.updated_at = utc_now()
        self.repository.save(state)
        return self.fact_bases.get(base.id)

    def skip(self, fact_base_id, step_id):
        self.fact_bases.get(fact_base_id)
        state = self._state(fact_base_id)
        if step_id not in state.skipped:
            state.skipped.append(step_id)
        state.updated_at = utc_now()
        self.repository.save(state)
        return self.next_card(fact_base_id)

    def _bump(self, base):
        expected_revision = base.revision
        base.revision += 1
        base.updated_at = utc_now()
        self.fact_bases.save(base, expected_revision=expected_revision)
        return self.fact_bases.get(base.id)

    def _dispatch(self, base, state, step_id, value, values, extra):
        value = value.strip()
        if step_id.startswith("profile:"):
            return self._answer_profile(base, step_id, value)
        if step_id.startswith("target:"):
            return self._answer_target(base, step_id, value)
        if step_id == "education:add":
            if value != "开始填写":
                raise ValueError("选项不正确")
            return base
        if step_id == "education:more":
            return self._education_more(base, state, value)
        if step_id.startswith("education:"):
            return self._answer_education(base, state, step_id, value, values, extra)
        if step_id in ("experience:add", "experience:more"):
            return self._experience_choice(base, state, value)
        if step_id.startswith("experience:"):
            return self._answer_experience(base, state, step_id, value, extra)
        if step_id == "skills:tags":
            return self._answer_skills(base, values)
        if step_id == "summary:pick":
            return base  # 自我评价写入在 Task 15 实现
        raise ValueError(f"unknown questionnaire step: {step_id}")

    def _answer_profile(self, base, step_id, value):
        field = step_id.split(":", 1)[1]
        if field == "name":
            if not value:
                raise ValueError("姓名不能为空")
            base.profile.name = value
        elif field == "email":
            if "@" not in value:
                raise ValueError("邮箱格式不正确")
            base.profile.email = value
        elif field == "phone":
            if not value:
                raise ValueError("电话不能为空")
            base.profile.phone = value
        elif field == "location":
            base.profile.location = value
        elif field == "links":
            base.profile.links = [
                line.strip() for line in value.splitlines() if line.strip()
            ]
        else:
            raise ValueError(f"unknown profile step: {step_id}")
        return self._bump(base)

    def _answer_target(self, base, step_id, value):
        field = step_id.split(":", 1)[1]
        if field == "role":
            if not value:
                raise ValueError("目标岗位不能为空")
            base.target.role = value
        elif field == "city":
            base.target.country = value
        else:
            raise ValueError(f"unknown target step: {step_id}")
        return self._bump(base)

    def _answer_education(self, base, state, step_id, value, values, extra):
        parts = step_id.split(":")
        if parts[1] == "new" and parts[2] == "school":
            if not value:
                raise ValueError("学校名称不能为空")
            education = Education(school=value)
            base.educations.append(education)
            state.edited_education_id = education.id
            return self._bump(base)
        education_id = UUID(parts[1])
        education = next(
            item for item in base.educations if item.id == education_id
        )
        field = parts[2]
        if field == "school":
            if not value:
                raise ValueError("学校名称不能为空")
            education.school = value
        elif field == "major":
            if not value:
                raise ValueError("专业不能为空")
            education.major = value
            state.course_options = self._course_options(value)
        elif field == "degree":
            if value not in DEGREE_OPTIONS:
                raise ValueError("学历选项不正确")
            education.degree = value
        elif field == "period":
            start, end = self._period(extra)
            education.start = start
            education.end = end
        elif field == "courses":
            education.core_courses = [
                item.replace("（AI 推荐）", "").strip()
                for item in values
                if item.strip()
            ]
        else:
            raise ValueError(f"unknown education step: {step_id}")
        education.updated_at = utc_now()
        return self._bump(base)

    def _education_more(self, base, state, value):
        if value == EDUCATION_DONE_OPTION:
            if "education" not in state.completed_sections:
                state.completed_sections.append("education")
            state.edited_education_id = None
            return base
        if value == "添加下一段教育":
            state.edited_education_id = None
            return base
        raise ValueError("选项不正确")

    def _experience_choice(self, base, state, value):
        if value == EXPERIENCE_DONE_OPTION:
            if "experience" not in state.completed_sections:
                state.completed_sections.append("experience")
            return base
        kind = state.experience_type_map.get(value)
        if kind is None:
            kind = "project"  # 用户自填的经历类型：默认按项目创建
        experience = Experience(
            organization=value if value not in state.experience_type_map else "",
            role="",
            type=ExperienceType(kind),
        )
        base.experiences.append(experience)
        state.edited_experience_id = experience.id
        return self._bump(base)

    def _answer_experience(self, base, state, step_id, value, extra):
        _, experience_id_text, field = step_id.split(":")
        if field == "interview":
            raise ValueError("该步骤请通过访谈流程完成")
        experience = base.get_experience(UUID(experience_id_text))
        if field == "organization":
            if not value:
                raise ValueError("组织名称不能为空")
            experience.organization = value
        elif field == "role":
            if not value:
                raise ValueError("角色不能为空")
            experience.role = value
        elif field == "period":
            start, end = self._period(extra)
            experience.start = start
            # Experience.end 是 str 字段：「至今」用空串表示（None 会损坏旧 payload 加载）
            experience.end = end or ""
        else:
            raise ValueError(f"unknown experience step: {step_id}")
        experience.updated_at = utc_now()
        return self._bump(base)

    def _answer_skills(self, base, values):
        base.profile.skills = [item.strip() for item in values if item.strip()]
        return self._bump(base)

    def _course_options(self, major):
        options = list(courses_for_major(major))
        if self.course_advisor is not None:
            try:
                for item in self.course_advisor.recommend(major):
                    if item and item not in options:
                        options.append(f"{item}（AI 推荐）")
            except Exception:
                pass  # AI 推荐失败时静默降级为词典
        return options

    def _skill_options(self, base):
        options = []
        for experience in base.experiences:
            for skill in experience.linked_skills:
                if skill and skill not in options:
                    options.append(skill)
        if self.skill_advisor is not None:
            facts_text = "\n".join(
                value.text
                for experience in base.experiences
                for values in experience.statements.values()
                for value in values
            )
            try:
                for skill in self.skill_advisor.extract(facts_text):
                    if skill and skill not in options:
                        options.append(skill)
            except Exception:
                pass
        return options

    @staticmethod
    def _period(extra):
        start = extra.get("start", "").strip()
        end = extra.get("end", "").strip()
        if not is_year_month(start):
            raise ValueError("起始年月格式不正确（YYYY-MM）")
        if end and not is_year_month(end):
            raise ValueError("结束年月格式不正确（YYYY-MM）")
        if end and not year_month_le(start, end):
            raise ValueError("结束时间不能早于开始时间")
        return start, (end or None)
