from resume_agent.application.mentor_guide import (
    MentorGuideService,
    OFFLINE_FOLLOWUP_OPTIONS,
    offline_experience_options,
)


class FakeJobAdvisor:
    def analyze(self, target_role):
        return [f"{target_role}看重A", f"{target_role}看重B"]


class FakeExperienceAdvisor:
    def options(self, target_role):
        return [
            {"label": "产品实习", "type": "internship"},
            {"label": "用户调研项目", "type": "project"},
        ]


class FakeFollowupAdvisor:
    def options(self, target_role, experience_text, dimension):
        return ["选项一", "选项二"]


class FailingAdvisor:
    def analyze(self, target_role):
        raise RuntimeError("boom")

    def options(self, *args):
        raise RuntimeError("boom")


def test_offline_experience_options_cover_types_and_projects():
    options = offline_experience_options()
    types = [item["type"] for item in options]
    assert "internship" in types and "work" in types and "campus" in types
    assert types.count("project") >= 3  # Web/Agent/课程项目
    labels = [item["label"] for item in options]
    assert "Web 开发项目" in labels and "Agent / AI 项目" in labels


def test_offline_followup_options_cover_dimensions():
    for dimension in OFFLINE_FOLLOWUP_OPTIONS:
        assert OFFLINE_FOLLOWUP_OPTIONS[dimension]


def test_guide_analyze_job_offline_and_advisor():
    assert len(MentorGuideService().analyze_job("产品经理")) >= 3
    service = MentorGuideService(job_advisor=FakeJobAdvisor())
    assert service.analyze_job("产品经理") == ["产品经理看重A", "产品经理看重B"]


def test_guide_experience_options_offline_and_advisor():
    offline = MentorGuideService().experience_options("产品经理")
    labels = [item["label"] for item in offline]
    assert "实习" in labels and "Web 开发项目" in labels
    service = MentorGuideService(experience_advisor=FakeExperienceAdvisor())
    assert service.experience_options("产品经理")[0]["label"] == "产品实习"


def test_guide_followup_options_offline_and_advisor():
    offline = MentorGuideService().followup_options("产品经理", "星河科技 · 实习生", "action")
    assert offline == OFFLINE_FOLLOWUP_OPTIONS["action"]
    service = MentorGuideService(followup_advisor=FakeFollowupAdvisor())
    assert service.followup_options("产品经理", "星河科技 · 实习生", "action") == ["选项一", "选项二"]


def test_guide_falls_back_when_advisor_fails():
    service = MentorGuideService(
        job_advisor=FailingAdvisor(),
        experience_advisor=FailingAdvisor(),
        followup_advisor=FailingAdvisor(),
    )
    assert len(service.analyze_job("产品经理")) >= 3
    assert len(service.experience_options("产品经理")) == 6
    assert service.followup_options("产品经理", "星河科技 · 实习生", "action")


def test_followup_options_passes_previous_to_advisor():
    seen = {}

    class Advisor:
        def options(self, role, text, dimension, previous=None):
            seen["previous"] = previous
            return ["新选项一", "新选项二"]

    service = MentorGuideService(followup_advisor=Advisor())
    result = service.followup_options(
        "产品经理", "实习经历 · 字节跳动 · 担任岗位", "role",
        previous=["AI产品实习生"],
    )
    assert seen["previous"] == ["AI产品实习生"]
    # 保留导师的新选项，并从轮换池补足到至少 4 条
    assert result[:2] == ["新选项一", "新选项二"]
    assert len(result) >= 4
    assert "AI产品实习生" not in result


def test_experience_options_passes_previous_to_advisor():
    seen = {}

    class Advisor:
        def options(self, role, previous=None):
            seen["previous"] = previous
            return [{"label": "Agent 开发项目", "type": "project"}]

    service = MentorGuideService(experience_advisor=Advisor())
    result = service.experience_options("产品经理", previous=["产品实习"])
    assert seen["previous"] == ["产品实习"]
    assert result[0]["label"] == "Agent 开发项目"


def test_followup_options_regenerate_excludes_previous_batch():
    """离线模式下「换一批」也必须换出不同的选项。"""
    service = MentorGuideService()
    first = service.followup_options("产品经理", "星河科技 · 实习生", "action")
    second = service.followup_options(
        "产品经理", "星河科技 · 实习生", "action", previous=first,
    )
    assert set(second).isdisjoint(first)
    assert len(second) >= 4


def test_followup_options_regenerate_with_failing_advisor_still_changes():
    """LLM 失败降级离线时，「换一批」仍然给出不同批次。"""
    service = MentorGuideService(followup_advisor=FailingAdvisor())
    first = service.followup_options("产品经理", "星河科技 · 实习生", "evidence")
    second = service.followup_options(
        "产品经理", "星河科技 · 实习生", "evidence", previous=first,
    )
    assert set(second).isdisjoint(first)
    assert len(second) >= 4


def test_followup_options_filters_llm_repeats_of_previous_batch():
    """LLM 若重复上一批选项，会被过滤并用轮换池补足。"""

    class RepeatAdvisor:
        def options(self, role, text, dimension, previous=None):
            return ["负责需求调研", "推动项目落地"]

    service = MentorGuideService(followup_advisor=RepeatAdvisor())
    result = service.followup_options(
        "产品经理", "星河科技 · 实习生", "action",
        previous=["负责需求调研", "推动项目落地"],
    )
    assert "负责需求调研" not in result
    assert "推动项目落地" not in result
    assert len(result) >= 4


def test_experience_options_regenerate_excludes_previous_labels():
    service = MentorGuideService()
    first = service.experience_options("产品经理")
    first_labels = {item["label"] for item in first}
    second = service.experience_options(
        "产品经理", previous=sorted(first_labels),
    )
    second_labels = {item["label"] for item in second}
    assert second_labels.isdisjoint(first_labels)
    assert len(second) >= 4
