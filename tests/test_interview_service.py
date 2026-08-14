from resume_agent.agents.unavailable import AgentUnavailableError
from resume_agent.application.interview_service import InterviewService
from resume_agent.agents.mentor import DeterministicQuestionWriter
from resume_agent.application.question_planner import QuestionPlanner
from resume_agent.domain.models import (
    CareerFactBase,
    FactProposal,
    FactValue,
    InterviewQuestion,
    InterviewSession,
    QualityDimension,
)
from tests.fakes import (
    InMemoryFactBaseRepository,
    InMemorySessionRepository,
    StubAuditAgent,
    StubQuestionWriter,
)


def make_interview():
    base = CareerFactBase()
    experience = base.add_experience("Yunshu", "Data Analyst")
    session = InterviewSession(
        fact_base_id=base.id,
        active_experience_id=experience.id,
    )
    bases = InMemoryFactBaseRepository([base])
    sessions = InMemorySessionRepository([session])
    service = InterviewService(
        bases,
        sessions,
        StubAuditAgent(),
        StubQuestionWriter(),
    )
    return service, session, bases, sessions, experience


def test_answer_creates_unconfirmed_proposal_without_mutating_fact_base():
    service, session, bases, sessions, experience = make_interview()

    turn = service.answer(session.id, "I built the weekly dashboard myself")

    assert turn.proposal is not None
    assert turn.proposal.dimension is QualityDimension.ACTION
    assert (
        bases.get(session.fact_base_id)
        .get_experience(experience.id)
        .statements[QualityDimension.ACTION]
        == []
    )
    assert turn.proposal.id in sessions.get(session.id).pending_proposals


def test_confirmation_updates_base_and_returns_one_next_question():
    service, session, bases, sessions, experience = make_interview()
    turn = service.answer(session.id, "I built the weekly dashboard myself")

    result = service.confirm(session.id, turn.proposal.id)

    assert bases.get(session.fact_base_id).revision == 1
    assert len(result.questions) == 1
    assert turn.proposal.id not in sessions.get(session.id).pending_proposals


def test_off_dimension_answer_is_anchored_to_asked_dimension():
    service, session, bases, sessions, experience = make_interview()
    service.question_writer = DeterministicQuestionWriter()
    session.skipped_dimensions = set(QualityDimension) - {
        QualityDimension.CONTEXT,
    }
    sessions.save(session)

    asked = service.next_question(session.id)
    assert asked is not None
    assert asked.dimension is QualityDimension.CONTEXT
    assert asked.escalation == "direct"

    turn = service.answer(session.id, "I built the weekly dashboard myself")
    assert turn.proposal is not None
    # 审计分类（action）与追问维度（context）不一致时，以追问的问题为准
    assert turn.proposal.dimension is QualityDimension.CONTEXT

    next_turn = service.confirm(session.id, turn.proposal.id)

    # 其他维度均已跳过、上下文证据仍不完整 → 继续追问上下文（但不记惩罚次数）
    assert next_turn.question is not None
    assert next_turn.question.dimension is QualityDimension.CONTEXT
    assert sessions.get(session.id).attempts == {}


def test_skip_after_two_unknown_answers_prevents_same_gap():
    service, session, bases, sessions, experience = make_interview()

    first = service.record_unknown(session.id, QualityDimension.RESULT)
    second = service.record_unknown(session.id, QualityDimension.RESULT)

    assert first.skipped is False
    assert second.skipped is True
    assert service.next_question(session.id).dimension is not QualityDimension.RESULT


def test_off_dimension_answer_does_not_count_as_explicit_unknown():
    service, session, bases, sessions, experience = make_interview()
    service.question_writer = DeterministicQuestionWriter()
    session.skipped_dimensions = set(QualityDimension) - {
        QualityDimension.CONTEXT,
    }
    sessions.save(session)

    service.next_question(session.id)
    turn = service.answer(session.id, "I built the weekly dashboard myself")
    service.confirm(session.id, turn.proposal.id)

    first = service.record_unknown(session.id, QualityDimension.CONTEXT)
    second = service.record_unknown(session.id, QualityDimension.CONTEXT)

    assert first.attempts == 1
    assert first.skipped is False
    assert second.attempts == 2
    assert second.skipped is True
    stored = sessions.get(session.id)
    assert stored.attempts[QualityDimension.CONTEXT] == 2
    assert stored.unknown_attempts[QualityDimension.CONTEXT] == 2


def test_interview_asks_only_one_question_per_turn():
    service, session, bases, sessions, experience = make_interview()
    turn = service.answer(session.id, "I built the weekly dashboard myself")

    result = service.confirm(session.id, turn.proposal.id)

    assert result.questions == [result.question.text]


def test_confirmation_rejects_unknown_proposal():
    service, session, bases, sessions, experience = make_interview()

    try:
        service.confirm(session.id, experience.id)
    except KeyError as error:
        assert "proposal not pending" in str(error)
    else:
        raise AssertionError("unknown proposal must be rejected")


class RecordingAudit:
    def __init__(self):
        self.predicted = []

    def propose(self, message, session, base, predicted_dimension=None):
        self.predicted.append(predicted_dimension)
        return FactProposal(
            fact_base_revision=base.revision,
            experience_id=session.active_experience_id,
            dimension=QualityDimension.ACTION,
            values=[FactValue(text=message)],
            next_question="这条行动的结果是什么？",
        )


class RecordingWriter:
    def __init__(self):
        self.calls = 0

    def write(self, plan, experience, target):
        self.calls += 1
        return f"请补充{plan.dimension.value}。"


def interview_fixture():
    base = CareerFactBase()
    experience = base.add_experience("星河科技", "实习生")
    session = InterviewSession(
        fact_base_id=base.id, active_experience_id=experience.id
    )
    audit = RecordingAudit()
    writer = RecordingWriter()
    service = InterviewService(
        InMemoryFactBaseRepository([base]),
        InMemorySessionRepository([session]),
        audit,
        writer,
        QuestionPlanner(),
    )
    return service, session, audit, writer


def test_answer_receives_predicted_dimension_excluding_asked():
    service, session, audit, _ = interview_fixture()
    session.current_question = InterviewQuestion(
        dimension=QualityDimension.ACTION, text="你做了什么？", priority=1.0, escalation="direct"
    )
    service.sessions.save(session)
    service.answer(session.id, "我搭了看板")
    # 空经历所有维度同分时 planner 取枚举序第一个（CONTEXT）；排除所问 ACTION 后即为 CONTEXT
    assert audit.predicted == [QualityDimension.CONTEXT]


def test_confirm_uses_prewritten_question_without_writer_call():
    service, session, _, writer = interview_fixture()
    service.answer(session.id, "我搭了看板")
    stored = service.get_session(session.id)
    proposal = list(stored.pending_proposals.values())[0]
    turn = service.confirm(stored.id, proposal.id)
    assert turn.question is not None
    assert turn.question.text == "这条行动的结果是什么？"
    assert writer.calls == 0
    updated = service.get_session(session.id)
    assert updated.pending_next_text == ""
    assert updated.pending_next_dimension is None


def test_confirm_falls_back_to_writer_on_dimension_mismatch():
    service, session, _, writer = interview_fixture()
    service.answer(session.id, "我搭了看板")
    stored = service.get_session(session.id)
    proposal = list(stored.pending_proposals.values())[0]
    # 人为制造不匹配：把 pending 维度改成已跳过的维度，planner 必不会选中它
    stored.pending_next_dimension = QualityDimension.EVIDENCE
    stored.skipped_dimensions.add(QualityDimension.EVIDENCE)
    service.sessions.save(stored)
    turn = service.confirm(stored.id, proposal.id)
    assert turn.question is not None
    assert turn.question.text != "这条行动的结果是什么？"
    assert writer.calls == 1


def test_reject_clears_pending_next_question():
    service, session, _, writer = interview_fixture()
    service.answer(session.id, "我搭了看板")
    stored = service.get_session(session.id)
    proposal = list(stored.pending_proposals.values())[0]
    rejected = service.reject(stored.id, proposal.id)
    assert rejected.pending_next_text == ""
    assert rejected.pending_next_dimension is None
    service.next_question(session.id)
    assert writer.calls == 1


class OptionGuide:
    def followup_options(self, role, text, dimension):
        return ["选项A", "选项B"]


def test_confirm_question_carries_followup_options():
    base = CareerFactBase()
    experience = base.add_experience("星河科技", "实习生")
    session = InterviewSession(
        fact_base_id=base.id, active_experience_id=experience.id
    )
    service = InterviewService(
        InMemoryFactBaseRepository([base]),
        InMemorySessionRepository([session]),
        RecordingAudit(),
        RecordingWriter(),
        QuestionPlanner(),
        guide=OptionGuide(),
    )
    service.answer(session.id, "我搭了看板")
    stored = service.get_session(session.id)
    proposal = list(stored.pending_proposals.values())[0]
    turn = service.confirm(stored.id, proposal.id)
    assert turn.question is not None
    assert turn.question.options == ["选项A", "选项B"]


class FailingAuditAgent:
    def propose(self, message, session, base, predicted_dimension=None):
        raise AgentUnavailableError("model request failed")


class FailingQuestionWriter:
    def write(self, plan, experience, target):
        raise AgentUnavailableError("model request failed")


def test_answer_falls_back_offline_when_audit_agent_unavailable():
    base = CareerFactBase()
    experience = base.add_experience("校园创业项目", "核心产品成员")
    session = InterviewSession(
        fact_base_id=base.id, active_experience_id=experience.id
    )
    service = InterviewService(
        InMemoryFactBaseRepository([base]),
        InMemorySessionRepository([session]),
        FailingAuditAgent(),
        StubQuestionWriter(),
    )
    turn = service.answer(session.id, "我负责组织商赛报名与宣传")
    assert turn.proposal is not None
    assert turn.proposal.values[0].text == "我负责组织商赛报名与宣传"
    assert "？" in turn.proposal.next_question
    stored = service.get_session(session.id)
    assert len(stored.pending_proposals) == 1


def test_question_writer_falls_back_offline_when_unavailable():
    service, session, bases, sessions, experience = make_interview()
    service.question_writer = FailingQuestionWriter()
    session.skipped_dimensions = set(QualityDimension) - {QualityDimension.CONTEXT}
    sessions.save(session)
    question = service.next_question(session.id)
    assert question is not None
    assert question.dimension is QualityDimension.CONTEXT
    assert question.text == "这段经历当时要解决的具体问题或背景是什么？"
