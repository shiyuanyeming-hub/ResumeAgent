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


SUMMARY_OPTIONS_PROMPT = """你是简历自我评价撰写顾问。基于给定的已确认经历事实、技能和目标岗位，撰写 3~5 条中文自我评价备选（每条 40~70 字），风格错开（稳重 / 进取 / 技术驱动等）。

写作要求：
1. 每条必须提炼自「已确认事实」中用户亲身做过的经历（做了什么、怎么做的、结果如何），体现这些经历沉淀出的能力、方法与特质，而不是空话套话；
2. 面向目标岗位调整侧重点，但不得编造经历之外的内容；
3. 禁止出现给定事实之外的数字、公司名、职位名。

只输出 JSON：{"options": ["备选1", "备选2", ...]}"""


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


EXPERIENCE_OPTIONS_PROMPT = """你是简历导师。给定目标岗位，生成 4~6 个候选「经历/项目类型」选项（中文短标签），帮助用户选出自己做过的事情。必须覆盖：岗位相关实习/工作，以及互联网类项目（如「Web 开发项目」「Agent / AI 开发项目」「小程序项目」「开源项目」「课程项目」等）。每个选项标注 type，只能取：internship（实习）、work（工作）、project（项目）、campus（校园）。只输出 JSON：{"options": [{"label": "...", "type": "internship"}, ...]}"""


class FollowUpOptionsPayload(BaseModel):
    options: List[str] = Field(min_length=1, max_length=6)


FOLLOWUP_OPTIONS_PROMPT = """你是资深简历导师。给定目标岗位、当前经历（含已确认事实）与正在追问的维度，生成 3~5 个中文候选回答选项（短短的完整短句，8~20 字）。

要求：
1. 必须贴合这段经历与岗位：参考「已确认事实」，选项应是用户最可能做出的具体回答，而不是放之四海皆准的空话；
2. 覆盖不同侧重点（如不同动作、不同产出、不同规模），让用户总能找到接近自己情况的选项；
3. 用用户第一人称口吻（「我……」开头可不加，直接给短句）；
4. 不要包含任何解释、编号或括号说明。

只输出 JSON：{"options": ["选项1", ...]}"""

ROLE_OPTIONS_PROMPT = """你是简历导师。给定目标岗位与一段经历，生成 3~5 个用户在这段经历里最可能担任的角色名（中文短标签，如「数据分析实习生」「产品实习生」「项目负责人」「核心成员」）。角色名必须贴合经历类型与目标岗位，不要空泛（避免只输出「实习生」「成员」）。只输出 JSON：{"options": ["角色1", ...]}"""


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
        prompt_template = ROLE_OPTIONS_PROMPT if dimension == "role" else FOLLOWUP_OPTIONS_PROMPT
        prompt = (
            f"{prompt_template}\n"
            f"目标岗位：{target_role}\n"
            f"当前经历：{experience_text}\n"
            f"追问维度：{dimension}"
        )
        payload = run_structured(self.runner, prompt, FollowUpOptionsPayload)
        return [item.strip() for item in payload.options if item.strip()]
