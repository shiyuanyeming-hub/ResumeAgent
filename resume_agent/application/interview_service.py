"""Stateful interview orchestration across specialized agent ports."""

from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from resume_agent.agents.mentor import DeterministicQuestionWriter
from resume_agent.agents.structured import AgentOutputError
from resume_agent.agents.unavailable import AgentUnavailableError
from resume_agent.application.mentor_guide import (
    OFFLINE_FOLLOWUP_POOLS,
    _fresh_text_options,
)
from resume_agent.application.ports import (
    FactAuditAgent,
    FactBaseRepository,
    QuestionWriterAgent,
    SessionRepository,
)
from resume_agent.application.question_planner import (
    PlanningSignals,
    QuestionHistory,
    QuestionPlan,
    QuestionPlanner,
)
from resume_agent.domain.models import (
    CareerFactBase,
    ConfidenceStatus,
    FactProposal,
    FactValue,
    InterviewQuestion,
    InterviewMessage,
    InterviewSession,
    QualityDimension,
    utc_now,
)


MentorQuestion = InterviewQuestion


class InterviewTurn(BaseModel):
    proposal: Optional[FactProposal] = None
    question: Optional[MentorQuestion] = None
    questions: List[str] = Field(default_factory=list, max_length=1)


class UnknownOutcome(BaseModel):
    dimension: QualityDimension
    attempts: int
    skipped: bool


class InterviewService:
    def __init__(
        self,
        fact_bases: FactBaseRepository,
        sessions: SessionRepository,
        audit_agent: FactAuditAgent,
        question_writer: QuestionWriterAgent,
        planner: Optional[QuestionPlanner] = None,
        guide=None,
    ) -> None:
        self.fact_bases = fact_bases
        self.sessions = sessions
        self.audit_agent = audit_agent
        self.question_writer = question_writer
        self.planner = planner or QuestionPlanner()
        self.guide = guide

    def create_session(
        self,
        fact_base_id: UUID,
        active_experience_id: UUID,
    ) -> InterviewSession:
        base = self.fact_bases.get(fact_base_id)
        try:
            base.get_experience(active_experience_id)
        except KeyError as error:
            raise ValueError(
                "active experience does not belong to the selected fact base"
            ) from error
        session = InterviewSession(
            fact_base_id=fact_base_id,
            active_experience_id=active_experience_id,
        )
        self.sessions.create(session)
        return self.sessions.get(session.id)

    def get_session(self, session_id: UUID) -> InterviewSession:
        return self.sessions.get(session_id)

    def list_sessions(
        self,
        fact_base_id: UUID,
        experience_id: Optional[UUID] = None,
    ) -> List[InterviewSession]:
        self.fact_bases.get(fact_base_id)
        sessions = self.sessions.list(fact_base_id)
        if experience_id is not None:
            sessions = [
                session
                for session in sessions
                if session.active_experience_id == experience_id
            ]
        return sessions

    def answer(self, session_id: UUID, message: str) -> InterviewTurn:
        session = self.sessions.get(session_id)
        base = self.fact_bases.get(session.fact_base_id)
        if session.active_experience_id is None:
            raise ValueError("an active experience is required before deepening")

        asked_dimension = (
            session.current_question.dimension
            if session.current_question is not None
            else None
        )
        session.messages.append(InterviewMessage(role="user", content=message))
        session.current_question = None
        session.updated_at = utc_now()
        self.sessions.save(session)
        predicted = self._predict_next_dimension(session, base, asked_dimension)
        try:
            proposal = self.audit_agent.propose(
                message, session, base, predicted_dimension=predicted
            )
        except (AgentUnavailableError, AgentOutputError):
            proposal = self._offline_proposal(
                message, session, base, asked_dimension, predicted
            )
        if proposal.experience_id != session.active_experience_id:
            raise ValueError("agent proposal targeted a different experience")
        if proposal.fact_base_revision != base.revision:
            raise ValueError("agent proposal used a stale fact-base revision")

        # 收敛：回答的是哪个维度的问题，事实就归到哪个维度。
        # 审计分类与追问维度不一致时，以追问的问题为准，保证每轮都能推进证据。
        if asked_dimension is not None and proposal.dimension is not asked_dimension:
            proposal.dimension = asked_dimension

        # 去重：过滤与已有事实完全相同的提议，避免反复确认同一句话。
        experience = base.get_experience(session.active_experience_id)
        existing_texts = {
            value.text.strip()
            for values in experience.statements.values()
            for value in values
        }
        unique_values = [
            value for value in proposal.values
            if value.text.strip() not in existing_texts
        ]
        if unique_values:
            proposal.values = unique_values

        session.pending_proposals[proposal.id] = proposal
        session.pending_next_text = proposal.next_question
        session.pending_next_dimension = predicted
        session.updated_at = utc_now()
        self.sessions.save(session)
        return InterviewTurn(proposal=proposal)

    def _predict_next_dimension(
        self,
        session: InterviewSession,
        base: CareerFactBase,
        asked_dimension: Optional[QualityDimension],
    ) -> Optional[QualityDimension]:
        if session.active_experience_id is None:
            return None
        experience = base.get_experience(session.active_experience_id)
        history = QuestionHistory(
            attempts=session.attempts,
            skipped=session.skipped_dimensions,
        )
        ranked = self.planner.rank(experience, PlanningSignals(), history)
        candidates = {
            dimension: priority
            for dimension, priority in ranked.items()
            if dimension is not asked_dimension
        }
        if not candidates:
            return None
        return max(candidates, key=candidates.get)

    def confirm(self, session_id: UUID, proposal_id: UUID) -> InterviewTurn:
        session = self.sessions.get(session_id)
        try:
            proposal = session.pending_proposals[proposal_id]
        except KeyError as error:
            raise KeyError(f"proposal not pending: {proposal_id}") from error

        base = self.fact_bases.get(session.fact_base_id)
        expected_revision = base.revision
        base.confirm(proposal)
        self.fact_bases.save(base, expected_revision=expected_revision)

        del session.pending_proposals[proposal_id]
        question = self._make_question(session, base)
        if question is not None:
            session.messages.append(
                InterviewMessage(role="assistant", content=question.text)
            )
            session.current_question = question
        session.updated_at = utc_now()
        self.sessions.save(session)
        return InterviewTurn(
            question=question,
            questions=[question.text] if question is not None else [],
        )

    def reject(self, session_id: UUID, proposal_id: UUID) -> InterviewSession:
        session = self.sessions.get(session_id)
        if proposal_id not in session.pending_proposals:
            raise KeyError(f"proposal not pending: {proposal_id}")
        del session.pending_proposals[proposal_id]
        session.pending_next_text = ""
        session.pending_next_dimension = None
        session.updated_at = utc_now()
        self.sessions.save(session)
        return self.sessions.get(session_id)

    def record_unknown(
        self,
        session_id: UUID,
        dimension: QualityDimension,
    ) -> UnknownOutcome:
        session = self.sessions.get(session_id)
        attempts = session.unknown_attempts.get(dimension, 0) + 1
        session.unknown_attempts[dimension] = attempts
        session.attempts[dimension] = session.attempts.get(dimension, 0) + 1
        skipped = attempts >= 2
        if skipped:
            session.skipped_dimensions.add(dimension)
        if (
            session.current_question is not None
            and session.current_question.dimension is dimension
        ):
            session.current_question = None
        session.updated_at = utc_now()
        self.sessions.save(session)
        return UnknownOutcome(
            dimension=dimension,
            attempts=attempts,
            skipped=skipped,
        )

    def next_question(self, session_id: UUID) -> Optional[MentorQuestion]:
        session = self.sessions.get(session_id)
        if session.current_question is not None:
            return session.current_question
        base = self.fact_bases.get(session.fact_base_id)
        question = self._make_question(session, base)
        if question is not None:
            session.messages.append(
                InterviewMessage(role="assistant", content=question.text)
            )
            session.current_question = question
            session.updated_at = utc_now()
            self.sessions.save(session)
        return question

    def regenerate_options(self, session_id: UUID) -> Optional[MentorQuestion]:
        """「换一批」：把当前问题的上一批选项作为反例，让 AI 重新生成选项。"""
        session = self.sessions.get(session_id)
        question = session.current_question
        if question is None:
            raise ValueError("当前没有等待回答的问题，无法换一批")
        base = self.fact_bases.get(session.fact_base_id)
        experience = base.get_experience(session.active_experience_id)
        if self.guide is not None:
            options = self.guide.followup_options(
                base.target.role,
                self._experience_context(experience),
                question.dimension.value,
                previous=list(question.options),
            )
            question.options = options
            session.updated_at = utc_now()
            self.sessions.save(session)
        else:
            # 无导师时用离线轮换池兜底，保证「换一批」也有新内容
            dimension = question.dimension.value
            pool = OFFLINE_FOLLOWUP_POOLS.get(dimension, [])
            previous = list(question.options)
            seed = list(question.options) if previous else pool[:4]
            question.options = _fresh_text_options(
                seed, pool, previous=previous or None,
            )
            session.updated_at = utc_now()
            self.sessions.save(session)
        return question

    def _offline_proposal(
        self,
        message: str,
        session: InterviewSession,
        base: CareerFactBase,
        asked_dimension: Optional[QualityDimension],
        predicted_dimension: Optional[QualityDimension],
    ) -> FactProposal:
        """LLM 不可用时的确定性兜底：直接引用用户原话生成待确认事实。"""
        experience = base.get_experience(session.active_experience_id)
        dimension = asked_dimension or predicted_dimension or QualityDimension.RESPONSIBILITY
        next_plan = QuestionPlan(
            dimension=predicted_dimension or QualityDimension.RESULT,
            priority=0,
            attempt=0,
            escalation="direct",
        )
        next_question = DeterministicQuestionWriter().write(
            next_plan, experience, base.target
        )
        source_ids = [
            item.id for item in session.messages[-1:] if item.role == "user"
        ]
        return FactProposal(
            fact_base_revision=base.revision,
            experience_id=session.active_experience_id,
            dimension=dimension,
            values=[
                FactValue(
                    text=message.strip(),
                    confidence=ConfidenceStatus.UNVERIFIED,
                    source_message_ids=source_ids,
                )
            ],
            rationale="导师暂不可用，直接引用你的原话作为待确认事实。",
            next_question=next_question,
        )

    def _make_question(
        self,
        session: InterviewSession,
        base: CareerFactBase,
    ) -> Optional[MentorQuestion]:
        if session.active_experience_id is None:
            return None
        experience = base.get_experience(session.active_experience_id)
        plan = self.planner.plan(
            experience,
            PlanningSignals(),
            QuestionHistory(
                attempts=session.attempts,
                skipped=session.skipped_dimensions,
            ),
        )
        if plan is None:
            session.pending_next_text = ""
            session.pending_next_dimension = None
            return None
        if (
            session.pending_next_text
            and plan.dimension == session.pending_next_dimension
        ):
            text = session.pending_next_text
        else:
            try:
                text = self.question_writer.write(plan, experience, base.target).strip()
            except (AgentUnavailableError, AgentOutputError):
                text = DeterministicQuestionWriter().write(plan, experience, base.target)
            if not text:
                raise ValueError("question writer returned an empty question")
        session.pending_next_text = ""
        session.pending_next_dimension = None
        options: List[str] = []
        if self.guide is not None:
            options = self.guide.followup_options(
                base.target.role,
                self._experience_context(experience),
                plan.dimension.value,
            )
        return MentorQuestion(
            dimension=plan.dimension,
            text=text,
            priority=plan.priority,
            escalation=plan.escalation,
            options=options,
        )

    @staticmethod
    def _experience_context(experience) -> str:
        """给选项生成器提供更贴合经历的上下文（含已确认事实与项目背景资料）。"""
        facts = "；".join(
            value.text
            for values in experience.statements.values()
            for value in values
        )
        context = f"{experience.organization} · {experience.role}"
        if experience.start:
            context += f"（{experience.start} 起）"
        if facts:
            context += f"；已确认事实：{facts}"
        if experience.source_context:
            context += f"；项目背景资料：{experience.source_context[:1600]}"
        return context
