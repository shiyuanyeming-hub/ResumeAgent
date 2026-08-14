from resume_agent.application.summary_service import (
    SummaryService,
    offline_summary_options,
)
from resume_agent.domain.models import (
    CareerFactBase, ConfidenceStatus, FactValue, QualityDimension, ResumeVersion,
)


class FakeSummaryAgent:
    def __init__(self, options):
        self.options = list(options)

    def generate(self, facts_text, skills, target_role):
        return list(self.options)


def test_offline_summary_has_three_options():
    base = CareerFactBase()
    base.profile.skills = ["SQL"]
    options = offline_summary_options(base, "数据分析师")
    assert len(options) == 3
    assert all(options)


def test_generate_drops_fabricated_numbers():
    base = CareerFactBase()
    base.profile.skills = ["SQL"]
    experience = base.add_experience("星河科技", "实习生")
    experience.statements[QualityDimension.ACTION] = [
        FactValue(text="搭建看板", confidence=ConfidenceStatus.CONFIRMED)
    ]
    version = ResumeVersion(
        fact_base_id=base.id, name="默认版本", base_revision=0,
        target_role="数据分析师", selected_experience_ids=[experience.id],
    )
    service = SummaryService(FakeSummaryAgent([
        "将看板效率提升了50个百分点，团队反馈良好，工作扎实可靠，适合数据分析岗位。",
    ]))
    options = service.generate(base, version)
    assert not any("50" in item for item in options)
    assert len(options) >= 3


def test_generate_keeps_grounded_options():
    base = CareerFactBase()
    base.profile.skills = ["SQL"]
    experience = base.add_experience("星河科技", "实习生")
    experience.statements[QualityDimension.ACTION] = [
        FactValue(text="搭建看板", confidence=ConfidenceStatus.CONFIRMED)
    ]
    version = ResumeVersion(
        fact_base_id=base.id, name="默认版本", base_revision=0,
        target_role="数据分析师", selected_experience_ids=[experience.id],
    )
    grounded = [
        "具备数据类实习经历，熟悉SQL与看板搭建方法，能够快速融入团队协作节奏，适合数据分析岗位。",
        "目标导向，善于拆解业务问题并用数据分析工具推进落地，注重过程记录与结果验证方法。",
        "学习能力强，乐于承担新的挑战，持续在数据分析方向积累实践经验与解决问题的方法论。",
    ]
    service = SummaryService(FakeSummaryAgent(grounded))
    assert service.generate(base, version) == grounded
