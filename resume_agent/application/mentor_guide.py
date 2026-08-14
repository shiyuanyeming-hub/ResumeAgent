"""Mentor-guide candidates: job analysis and dynamic answer options."""

from resume_agent.domain.questionnaire_steps import EXPERIENCE_TYPE_OPTIONS

OFFLINE_JOB_ANALYSIS = [
    "与目标岗位相关的项目或实习经历",
    "可量化的成果与数据",
    "岗位核心技能与工具",
    "团队协作与沟通能力",
]

OFFLINE_FOLLOWUP_OPTIONS = {
    "role": ["项目负责人", "核心成员", "普通成员", "实习生"],
    "context": ["解决具体业务问题", "完成课程大作业", "社团活动需求", "竞赛题目"],
    "responsibility": ["独立负责一块", "协助团队完成", "主导整个项目"],
    "action": ["搭建或开发", "调研分析", "策划执行", "沟通协调"],
    "method": ["用专业软件", "用编程工具", "用分析框架", "手工流程"],
    "result": ["效率提升", "用户增长", "成本降低", "获得认可"],
    "evidence": ["有数字指标", "有交付物", "有他人反馈", "暂时没有"],
}


def offline_experience_options():
    """固定四类经历选项（离线兜底，label 映射到类型）。"""
    return [
        {"label": label, "type": code}
        for code, label in EXPERIENCE_TYPE_OPTIONS
    ]


class MentorGuideService:
    """Job analysis and dynamic options; every LLM path has an offline fallback."""

    def __init__(self, job_advisor=None, experience_advisor=None, followup_advisor=None):
        self.job_advisor = job_advisor
        self.experience_advisor = experience_advisor
        self.followup_advisor = followup_advisor

    def analyze_job(self, target_role):
        if self.job_advisor is not None:
            try:
                analysis = self.job_advisor.analyze(target_role)
                if analysis:
                    return analysis
            except Exception:
                pass  # 离线或失败降级为模板
        return list(OFFLINE_JOB_ANALYSIS)

    def experience_options(self, target_role):
        if self.experience_advisor is not None:
            try:
                options = self.experience_advisor.options(target_role)
                if options:
                    return options
            except Exception:
                pass
        return offline_experience_options()

    def followup_options(self, target_role, experience_text, dimension):
        if self.followup_advisor is not None:
            try:
                options = self.followup_advisor.options(
                    target_role, experience_text, dimension
                )
                if options:
                    return options
            except Exception:
                pass
        return list(OFFLINE_FOLLOWUP_OPTIONS.get(dimension, []))
