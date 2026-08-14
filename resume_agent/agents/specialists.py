"""Generation specialists for courses, skills, summaries and snippets."""

from typing import List

from pydantic import BaseModel, Field

from resume_agent.agents.structured import run_structured


class CoursePayload(BaseModel):
    courses: List[str] = Field(min_length=1)


class SkillsPayload(BaseModel):
    skills: List[str] = Field(min_length=1)


COURSE_RECOMMEND_PROMPT = """你是高校课程顾问。给定专业名称，推荐 5~8 门该专业最核心、最常见的本科课程名称（只输出课程名，不要编号、不要解释）。只输出 JSON：{"courses": ["课程1", "课程2", ...]}"""

SKILL_EXTRACT_PROMPT = """你是简历技能提炼员。从给定的事实文本中提取 3~8 个技能关键词（工具、语言、方法均可）。只输出事实中已出现或可直接推断的技能词，禁止编造。只输出 JSON：{"skills": ["技能1", ...]}"""


class StructuredCourseAgent:
    def __init__(self, runner) -> None:
        self.runner = runner

    def recommend(self, major: str) -> List[str]:
        prompt = f"{COURSE_RECOMMEND_PROMPT}\n专业：{major}"
        payload = run_structured(self.runner, prompt, CoursePayload)
        return [item.strip() for item in payload.courses if item.strip()]


class StructuredSkillAgent:
    def __init__(self, runner) -> None:
        self.runner = runner

    def extract(self, facts_text: str) -> List[str]:
        prompt = f"{SKILL_EXTRACT_PROMPT}\n事实文本：\n{facts_text}"
        payload = run_structured(self.runner, prompt, SkillsPayload)
        return [item.strip() for item in payload.skills if item.strip()]


class SummaryOptionsPayload(BaseModel):
    options: List[str] = Field(min_length=3, max_length=5)


SUMMARY_OPTIONS_PROMPT = """你是简历自我评价撰写顾问。基于给定的已确认经历事实、技能和目标岗位，撰写 3~5 条中文自我评价备选（每条 40~70 字），风格错开（稳重 / 进取 / 技术驱动等）。严格基于给定内容：禁止出现给定事实之外的数字、公司名、职位名。只输出 JSON：{"options": ["备选1", "备选2", ...]}"""


class StructuredSummaryAgent:
    def __init__(self, runner) -> None:
        self.runner = runner

    def generate(self, facts_text: str, skills: str, target_role: str) -> List[str]:
        prompt = (
            f"{SUMMARY_OPTIONS_PROMPT}\n"
            f"目标岗位：{target_role}\n"
            f"技能：{skills}\n"
            f"已确认事实：\n{facts_text}"
        )
        payload = run_structured(self.runner, prompt, SummaryOptionsPayload)
        return [item.strip() for item in payload.options if item.strip()]


class SnippetPayload(BaseModel):
    snippets: List[str] = Field(min_length=1, max_length=3)


SNIPPET_WRITE_PROMPT = """你是简历经历润色员。基于给定经历与已确认事实，改写合并为 1~3 条可直接写入简历的中文要点（每条一句话、动词开头；保留事实中的数字与原意，禁止新增数字或成果）。只输出 JSON：{"snippets": ["要点1", ...]}"""


class StructuredSnippetAgent:
    def __init__(self, runner) -> None:
        self.runner = runner

    def write(self, experience, facts_text: str) -> List[str]:
        prompt = (
            f"{SNIPPET_WRITE_PROMPT}\n"
            f"经历：{experience.organization} · {experience.role}\n"
            f"已确认事实：\n{facts_text}"
        )
        payload = run_structured(self.runner, prompt, SnippetPayload)
        return [item.strip() for item in payload.snippets if item.strip()]


class JobAnalysisPayload(BaseModel):
    analysis: List[str] = Field(min_length=1, max_length=5)


JOB_ANALYSIS_PROMPT = """你是资深求职导师。给定目标岗位，用中文输出 3~5 条该岗位最看重的经历与能力要点，每条一句话（不超过 30 字），用于引导用户准备简历。只输出 JSON：{"analysis": ["要点1", "要点2", ...]}"""


class ExperienceOptionPayload(BaseModel):
    label: str
    type: str


class ExperienceOptionsPayload(BaseModel):
    options: List[ExperienceOptionPayload] = Field(min_length=1, max_length=6)


EXPERIENCE_OPTIONS_PROMPT = """你是简历导师。给定目标岗位，生成 4~6 个候选「经历/项目类型」选项（中文短标签，如「产品实习」「用户调研项目」「数据分析项目」「校园活动」），帮助用户选出自己做过的事情。每个选项标注 type，只能取：internship（实习）、work（工作）、project（项目）、campus（校园）。只输出 JSON：{"options": [{"label": "...", "type": "internship"}, ...]}"""


class FollowUpOptionsPayload(BaseModel):
    options: List[str] = Field(min_length=1, max_length=6)


FOLLOWUP_OPTIONS_PROMPT = """你是简历导师。给定目标岗位、当前经历与正在追问的维度，生成 3~5 个具体的中文选项（短短语），供用户快速回答该维度问题；选项要贴合这段经历的上下文，不要空泛。只输出 JSON：{"options": ["选项1", ...]}"""


class StructuredJobAnalysisAgent:
    def __init__(self, runner) -> None:
        self.runner = runner

    def analyze(self, target_role: str) -> List[str]:
        prompt = f"{JOB_ANALYSIS_PROMPT}\n目标岗位：{target_role}"
        payload = run_structured(self.runner, prompt, JobAnalysisPayload)
        return [item.strip() for item in payload.analysis if item.strip()]


class StructuredExperienceOptionsAgent:
    def __init__(self, runner) -> None:
        self.runner = runner

    def options(self, target_role: str) -> List[dict]:
        prompt = f"{EXPERIENCE_OPTIONS_PROMPT}\n目标岗位：{target_role}"
        payload = run_structured(self.runner, prompt, ExperienceOptionsPayload)
        return [
            {"label": item.label.strip(), "type": item.type}
            for item in payload.options
            if item.label.strip() and item.type in ("internship", "work", "project", "campus")
        ]


class StructuredFollowUpOptionsAgent:
    def __init__(self, runner) -> None:
        self.runner = runner

    def options(self, target_role: str, experience_text: str, dimension: str) -> List[str]:
        prompt = (
            f"{FOLLOWUP_OPTIONS_PROMPT}\n"
            f"目标岗位：{target_role}\n"
            f"当前经历：{experience_text}\n"
            f"追问维度：{dimension}"
        )
        payload = run_structured(self.runner, prompt, FollowUpOptionsPayload)
        return [item.strip() for item in payload.options if item.strip()]
