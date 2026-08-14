"""Self-summary candidate generation for zh resumes."""

from resume_agent.domain.grounding import collect_fact_texts, extract_numbers


def offline_summary_options(base, target_role):
    skills = "、".join(base.profile.skills[:3]) or "相关技能"
    count = len([
        experience for experience in base.experiences
        if any(values for values in experience.statements.values())
    ])
    role = target_role or "目标岗位"
    return [
        f"具备{count}段相关实践经历，熟悉{skills}，能快速融入团队协作节奏。",
        f"目标导向，善于拆解问题并用{skills}推进落地，注重用数据与结果说话。",
        f"学习能力强，乐于承担挑战，持续在{role}方向积累经验与方法论。",
    ]


class SummaryService:
    def __init__(self, agent=None):
        self.agent = agent

    def generate(self, base, version):
        facts_text = "\n".join(collect_fact_texts(base, version))
        skills = "、".join(base.profile.skills[:5]) or "相关技能"
        role = version.target_role or base.target.role or "目标岗位"
        allowed = extract_numbers(facts_text)
        options = []
        if self.agent is not None:
            try:
                options = [
                    item for item in self.agent.generate(facts_text, skills, role)
                    if not (extract_numbers(item) - allowed) and 40 <= len(item) <= 70
                ]
            except Exception:
                options = []
        if len(options) < 3:
            options = options + offline_summary_options(base, role)
        return options[:5]
