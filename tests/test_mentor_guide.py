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


def test_offline_experience_options_map_four_types():
    options = offline_experience_options()
    assert [item["type"] for item in options] == ["internship", "work", "project", "campus"]


def test_offline_followup_options_cover_dimensions():
    for dimension in OFFLINE_FOLLOWUP_OPTIONS:
        assert OFFLINE_FOLLOWUP_OPTIONS[dimension]


def test_guide_analyze_job_offline_and_advisor():
    assert len(MentorGuideService().analyze_job("产品经理")) >= 3
    service = MentorGuideService(job_advisor=FakeJobAdvisor())
    assert service.analyze_job("产品经理") == ["产品经理看重A", "产品经理看重B"]


def test_guide_experience_options_offline_and_advisor():
    offline = MentorGuideService().experience_options("产品经理")
    assert [item["label"] for item in offline] == ["实习", "工作", "项目", "校园经历"]
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
    assert len(service.experience_options("产品经理")) == 4
    assert service.followup_options("产品经理", "星河科技 · 实习生", "action")
