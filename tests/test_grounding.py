from resume_agent.domain.grounding import collect_fact_texts, extract_numbers
from resume_agent.domain.models import (
    CareerFactBase, ConfidenceStatus, FactValue, QualityDimension, ResumeVersion,
)


def test_extract_numbers():
    assert extract_numbers("将耗时从 4 小时降到 30 分钟") == {"4", "30"}


def test_collect_fact_texts_uses_selected_experiences():
    base = CareerFactBase()
    selected = base.add_experience("星河科技", "实习生")
    other = base.add_experience("远帆科技", "实习生")
    selected.statements[QualityDimension.ACTION] = [
        FactValue(text="搭建看板", confidence=ConfidenceStatus.CONFIRMED)
    ]
    other.statements[QualityDimension.ACTION] = [
        FactValue(text="写周报", confidence=ConfidenceStatus.CONFIRMED)
    ]
    version = ResumeVersion(
        fact_base_id=base.id, name="默认版本", base_revision=0,
        selected_experience_ids=[selected.id],
    )
    texts = collect_fact_texts(base, version)
    assert "搭建看板" in texts
    assert "写周报" not in texts
