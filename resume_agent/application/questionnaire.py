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
from resume_agent.domain.course_catalog import (
    catalog_majors,
    courses_for_major,
    majors_for_school,
)
from resume_agent.domain.quality import evaluate_experience, evaluate_profile_completeness
from resume_agent.domain.questionnaire_steps import (
    DEGREE_OPTIONS,
    EDUCATION_DONE_OPTION,
    EXPERIENCE_DONE_OPTION,
    EXPERIENCE_TYPE_OPTIONS,
    FIRST_DEGREE_OPTIONS,
    HIGH_SCHOOL_OPTION,
    NEXT_DEGREE_OPTIONS,
    PROFILE_STEPS,
    SECTION_LABELS,
    SECTION_ORDER,
    TARGET_STEPS,
)
from resume_agent.domain.year_month import is_year_month, year_month_le
from resume_agent.application.mentor_guide import (
    OFFLINE_FOLLOWUP_OPTIONS,
    OFFLINE_ROLE_OPTIONS_BY_TYPE,
)


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
    regeneratable: bool = False
    deletable: bool = False


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
                if self._skipped(state, "education:new:school"):
                    # 用户放弃这一段学历：取消整段，进入下一章节
                    state.pending_education_degree = ""
                    if "education:add" not in state.skipped:
                        state.skipped.append("education:add")
                    return None
                return self._pending_degree_school_card(state)
            return self._card(
                "education:add", "education", QuestionKind.CHOICE,
                "你目前的最高学历是？（会从最高学历开始自上而下逐段填写）",
                options=list(FIRST_DEGREE_OPTIONS), skippable=True,
            )
        if "education" in state.completed_sections:
            return None
        if state.pending_education_degree:
            if self._skipped(state, "education:new:school"):
                # 放弃上一段学历：回到学历层次选择（可跳过）
                state.pending_education_degree = ""
                return None
            return self._pending_degree_school_card(state)
        education = self._edited_education(base, state)
        if education is None:
            if self._skipped(state, "education:new:degree"):
                # 不再添加学历 → 回到「是否还有上一段学历」
                return self._card(
                    "education:more", "education", QuestionKind.CHOICE,
                    "是否还有上一段学历要填写？（例如：本科）",
                    options=["添加上一段学历", EDUCATION_DONE_OPTION],
                )
            return self._card(
                "education:new:degree", "education", QuestionKind.CHOICE,
                "还有一段学历要填写，它的层次是？",
                options=list(NEXT_DEGREE_OPTIONS), skippable=True,
            )
        card = self._education_field_card(base, state, education)
        if card is not None:
            return card
        return self._card(
            "education:more", "education", QuestionKind.CHOICE,
            "是否还有上一段学历要填写？（例如：本科）",
            options=["添加上一段学历", EDUCATION_DONE_OPTION],
        )

    def _pending_degree_school_card(self, state):
        degree = state.pending_education_degree or ""
        prompt = f"你{degree}阶段的学校是？" if degree else "学校名称是？"
        return self._card(
            "education:new:school", "education", QuestionKind.TEXT,
            prompt, skippable=True,
        )

    def _education_field_card(self, base, state, education):
        optional_degrees = ("博士", "硕士", "本科")
        steps = [
            ("school", QuestionKind.TEXT, "学校名称是？", False),
            ("major", QuestionKind.CHOICE_FREE,
             "所学专业是？（按学校类型优先展示，也可以自己填）", False),
            ("period", QuestionKind.YEAR_MONTH_RANGE,
             "这段学历的起止时间是？（结束留空表示至今）", True),
            ("gpa", QuestionKind.TEXT,
             "GPA 或均分是？（可跳过，如 3.8/4.0 或 88/100）", True),
            ("rank", QuestionKind.TEXT,
             "专业排名或占比是？（可跳过，如 前10% 或 3/120）", True),
        ]
        if education.degree in optional_degrees:
            steps.append(("research", QuestionKind.TEXT,
                          "研究方向是？（可跳过）", True))
            steps.append(("thesis", QuestionKind.TEXT,
                          "毕业论文或毕业设计题目是？（可跳过）", True))
        steps.append(("courses", QuestionKind.MULTI_CHOICE,
                      "勾选或添加核心课程（可跳过）", True))
        for field, kind, prompt, skippable in steps:
            step_id = f"education:{education.id}:{field}"
            if self._skipped(state, step_id):
                continue
            if field == "school" and education.school:
                continue
            if field == "major" and education.major:
                continue
            if field == "period" and education.start:
                continue
            if field == "gpa" and education.gpa:
                continue
            if field == "rank" and education.rank:
                continue
            if field == "research" and education.research_direction:
                continue
            if field == "thesis" and education.thesis:
                continue
            if field == "courses" and education.core_courses:
                continue
            if field == "major":
                return self._card(
                    step_id, "education", kind, prompt,
                    options=self._major_options(education), skippable=skippable,
                )
            if field == "period":
                return self._card(
                    step_id, "education", kind, prompt,
                    extra={"end": education.end or ""}, skippable=skippable,
                )
            if field == "courses":
                return self._card(
                    step_id, "education", kind, prompt,
                    options=list(state.course_options), skippable=skippable,
                )
            return self._card(step_id, "education", kind, prompt, skippable=skippable)
        return None

    @staticmethod
    def _major_options(education):
        if education.school:
            return majors_for_school(education.school)
        return catalog_majors()

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
                regeneratable=self.guide is not None,
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
        # 名称：实习/工作问公司，项目问项目名，校园问经历名
        if not experience.organization and not self._skipped(state, f"experience:{experience.id}:organization"):
            prompts = {
                ExperienceType.PROJECT: "这个项目的名称是？",
                ExperienceType.CAMPUS: "这段校园经历的名称是？",
            }
            prompt = prompts.get(
                experience.type,
                "这段实习/工作的公司名称是？（必填）",
            )
            return self._card(
                f"experience:{experience.id}:organization", "experience",
                QuestionKind.TEXT, prompt, skippable=False,
                deletable=True,  # 误选经历类型时可直接删除整段
            )
        # 岗位：仅实习/工作询问（可跳过），且选项按经历类型动态生成
        asks_role = experience.type in (
            ExperienceType.INTERNSHIP, ExperienceType.WORK,
        )
        if (
            asks_role
            and not experience.role
            and not self._skipped(state, f"experience:{experience.id}:role")
        ):
            options = self._role_options(base, experience)
            state.role_options_cache[str(experience.id)] = list(options)
            return self._card(
                f"experience:{experience.id}:role", "experience",
                QuestionKind.CHOICE_FREE, "你当时担任的岗位是？（可跳过）",
                options=options,
                skippable=True,
                regeneratable=self.guide is not None,
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
        """岗位候选：按经历类型（实习/工作）动态生成，失败走分类型离线模板。"""
        type_labels = {
            ExperienceType.INTERNSHIP: "实习",
            ExperienceType.WORK: "工作",
        }
        type_label = type_labels.get(experience.type, "实习")
        if self.guide is not None:
            options = self.guide.followup_options(
                base.target.role or "",
                f"{type_label}经历 · {experience.organization or type_label} · 担任岗位",
                "role",
            )
            if options:
                return options
        return list(
            OFFLINE_ROLE_OPTIONS_BY_TYPE.get(experience.type.value, [])
        ) or list(OFFLINE_FOLLOWUP_OPTIONS.get("role", []))

    def _skills_card(self, base, state):
        if not base.profile.skills and not self._skipped(state, "skills:tags"):
            return self._card(
                "skills:tags", "skills", QuestionKind.MULTI_CHOICE,
                "勾选或添加你的技能标签（可跳过）",
                options=list(state.skill_options),
                values=list(base.profile.skills),
            )
        if not base.profile.certificates and not self._skipped(state, "skills:certs"):
            return self._card(
                "skills:certs", "skills", QuestionKind.TEXT,
                "证书、奖学金与荣誉（可跳过，每行一条，如 CET-6 550、国家奖学金）",
                skippable=True,
            )
        if not base.profile.language_scores and not self._skipped(state, "skills:languages"):
            return self._card(
                "skills:languages", "skills", QuestionKind.TEXT,
                "语言成绩（可跳过，每行一条，如 雅思 7.0、托福 100、日语 N1）",
                skippable=True,
            )
        return None

    def _summary_card(self, state, version):
        if (
            version is None
            or not version.summary_options
            or self._skipped(state, "summary:pick")
            or "summary:pick" in state.answered
        ):
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
        card = self.engine.next_card(base, state, version=version)
        # 持久化引擎在出卡时写入的缓存（如岗位选项缓存，供「换一批」使用）
        state.updated_at = utc_now()
        self.repository.save(state)
        return card

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
        # 「是否还有下一段」类卡片跳过 = 没有更多了 → 结束该章节
        if step_id == "education:more" and "education" not in state.completed_sections:
            state.completed_sections.append("education")
        if step_id == "experience:more" and "experience" not in state.completed_sections:
            state.completed_sections.append("experience")
        state.updated_at = utc_now()
        self.repository.save(state)
        return self.next_card(fact_base_id)

    def regenerate_options(self, fact_base_id, step_id):
        """「换一批」：带上上一批选项重新生成，让 AI 换角度给出新选项。"""
        base = self.fact_bases.get(fact_base_id)
        state = self._state(fact_base_id)
        role = base.target.role.strip()
        if step_id == "experience:add":
            previous = list(state.experience_type_map.keys())
            if self.guide is None:
                return [label for _, label in EXPERIENCE_TYPE_OPTIONS]
            options = self.guide.experience_options(role, previous=previous)
            state.experience_type_map = {
                item["label"]: item["type"] for item in options
            }
            state.updated_at = utc_now()
            self.repository.save(state)
            return [item["label"] for item in options]
        if step_id.startswith("experience:") and step_id.endswith(":role"):
            experience_id = UUID(step_id.split(":")[1])
            experience = base.get_experience(experience_id)
            previous = state.role_options_cache.get(str(experience_id), [])
            if not previous:
                card = self.engine._experience_field_card(base, state, experience)
                previous = list(card.options) if card is not None else []
            if self.guide is None:
                return self._role_options(base, experience)
            type_labels = {
                ExperienceType.INTERNSHIP: "实习",
                ExperienceType.WORK: "工作",
            }
            type_label = type_labels.get(experience.type, "实习")
            options = self.guide.followup_options(
                role,
                f"{type_label}经历 · {experience.organization or type_label} · 担任岗位",
                "role",
                previous=previous,
            )
            state.role_options_cache[str(experience_id)] = list(options)
            state.updated_at = utc_now()
            self.repository.save(state)
            return options
        raise ValueError(f"该步骤不支持换一批: {step_id}")

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
            return self._education_degree_choice(base, state, value)
        if step_id == "education:new:degree":
            return self._education_degree_choice(base, state, value)
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
        if step_id == "skills:certs":
            return self._answer_skills_text(base, "certificates", value)
        if step_id == "skills:languages":
            return self._answer_skills_text(base, "language_scores", value)
        if step_id == "summary:pick":
            return base  # 自我评价写入在 API 层完成
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

    def _education_degree_choice(self, base, state, value):
        if value == HIGH_SCHOOL_OPTION:
            if "education" not in state.completed_sections:
                state.completed_sections.append("education")
            state.pending_education_degree = ""
            return base
        if value in FIRST_DEGREE_OPTIONS or value in NEXT_DEGREE_OPTIONS:
            state.pending_education_degree = value
            return base
        raise ValueError("学历选项不正确")

    def _answer_education(self, base, state, step_id, value, values, extra):
        parts = step_id.split(":")
        if parts[1] == "new" and parts[2] == "school":
            if not value:
                raise ValueError("学校名称不能为空")
            education = Education(
                school=value,
                degree=state.pending_education_degree or "",
            )
            base.educations.append(education)
            state.edited_education_id = education.id
            state.pending_education_degree = ""
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
        elif field == "gpa":
            education.gpa = value
        elif field == "rank":
            education.rank = value
        elif field == "research":
            education.research_direction = value
        elif field == "thesis":
            education.thesis = value
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
        if value == "添加上一段学历":
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

    def _answer_skills_text(self, base, field, value):
        lines = [line.strip() for line in value.splitlines() if line.strip()]
        setattr(base.profile, field, lines)
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
