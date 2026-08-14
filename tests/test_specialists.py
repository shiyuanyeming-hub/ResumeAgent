from resume_agent.agents.specialists import (
    StructuredCourseAgent,
    StructuredSkillAgent,
)


class QueueRunner:
    def __init__(self, responses):
        self.responses = list(responses)

    def run(self, prompt):
        return self.responses.pop(0)


def test_course_agent_returns_courses():
    agent = StructuredCourseAgent(
        QueueRunner(['{"courses": ["数据结构", "操作系统"]}'])
    )
    assert agent.recommend("计算机科学与技术") == ["数据结构", "操作系统"]


def test_skill_agent_returns_skills():
    agent = StructuredSkillAgent(
        QueueRunner(['{"skills": ["SQL", "Python"]}'])
    )
    assert agent.extract("用 SQL 和 Python 搭建看板") == ["SQL", "Python"]
