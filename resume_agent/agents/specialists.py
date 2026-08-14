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
