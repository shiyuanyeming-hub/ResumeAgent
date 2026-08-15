"""FastAPI application factory for ResumeAgent."""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.parse import quote
from uuid import UUID

from fastapi import FastAPI, File, HTTPException, Request, Response, UploadFile, status
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from resume_agent.agents.mentor import DeterministicQuestionWriter
from resume_agent.agents.runtime import AgentCapabilityStatus
from resume_agent.agents.structured import AgentOutputError
from resume_agent.agents.unavailable import (
    AgentUnavailableError,
    UnavailableFactAuditAgent,
)
from resume_agent.api.schemas import (
    AnswerRequest,
    EducationCreateRequest,
    ExperienceCreateRequest,
    ExperienceUpdateRequest,
    FactBaseCreateRequest,
    ProfileUpdateRequest,
    QuestionnaireAnswerRequest,
    QuestionnaireSkipRequest,
    SessionCreateRequest,
    SummarySetRequest,
    UnknownRequest,
    VersionCloneRequest,
    VersionCreateRequest,
    VersionDraftRequest,
    VersionRenameRequest,
    VersionSnippetAddRequest,
    VersionStyleRequest,
)
from resume_agent.application.fact_base_service import FactBaseService
from resume_agent.application.mentor_guide import MentorGuideService
from resume_agent.application.interview_service import (
    InterviewService,
    InterviewTurn,
    MentorQuestion,
    UnknownOutcome,
)
from resume_agent.application.render_service import ResumeRenderService
from resume_agent.application.summary_service import SummaryService
from resume_agent.application.ports import (
    FactAuditAgent,
    QuestionWriterAgent,
    RevisionConflict,
)
from resume_agent.application.questionnaire import (
    QuestionnaireEngine,
    QuestionnaireService,
)
from resume_agent.application.version_service import VersionService
from resume_agent.domain.course_catalog import catalog_majors
from resume_agent.domain.school_catalog import search_schools as search_school_catalog
from resume_agent.domain.models import (
    CareerFactBase,
    ConfidenceStatus,
    Education,
    InterviewSession,
    ResumeVersion,
    utc_now,
)
from resume_agent.domain.quality import QualityReport, evaluate_experience
from resume_agent.infrastructure.photo_store import (
    MAX_PHOTO_BYTES,
    PhotoStore,
)
from resume_agent.infrastructure.template_store import (
    MAX_TEMPLATE_BYTES,
    TemplateStore,
)
from resume_agent.infrastructure.sqlite_repositories import (
    SQLiteFactBaseRepository,
    SQLiteQuestionnaireRepository,
    SQLiteSessionRepository,
    SQLiteStore,
    SQLiteVersionRepository,
)
from resume_agent.rendering.exporters import (
    RenderEngineUnavailable,
    RenderFormat,
    ResumeExporter,
)
from resume_agent.rendering.models import RenderedResume
from resume_agent.rendering.renderer import ResumeRenderer


@dataclass(frozen=True)
class ServiceContainer:
    store: SQLiteStore
    fact_base_repository: SQLiteFactBaseRepository
    session_repository: SQLiteSessionRepository
    version_repository: SQLiteVersionRepository
    fact_bases: FactBaseService
    questionnaires: QuestionnaireService
    interviews: InterviewService
    versions: VersionService
    rendering: ResumeRenderService
    summaries: SummaryService
    snippet_agent: object
    capabilities: AgentCapabilityStatus
    photo_store: object
    template_store: object


def create_app(
    database_path: Path,
    *,
    fact_audit_agent: Optional[FactAuditAgent] = None,
    question_writer: Optional[QuestionWriterAgent] = None,
    course_advisor=None,
    skill_advisor=None,
    resume_exporter: Optional[ResumeExporter] = None,
    resume_renderer: Optional[ResumeRenderer] = None,
    agent_capabilities: Optional[AgentCapabilityStatus] = None,
    summary_agent=None,
    snippet_agent=None,
    job_advisor=None,
    experience_advisor=None,
    followup_advisor=None,
) -> FastAPI:
    store = SQLiteStore(Path(database_path))
    fact_base_repository = SQLiteFactBaseRepository(store)
    session_repository = SQLiteSessionRepository(store)
    version_repository = SQLiteVersionRepository(store)
    photo_store = PhotoStore(Path(database_path).resolve().parent / "photos")
    template_store = TemplateStore(Path(database_path).resolve().parent / "templates")
    renderer = resume_renderer or ResumeRenderer()
    exporter = resume_exporter or ResumeExporter()
    if agent_capabilities is not None:
        capabilities = agent_capabilities
    elif fact_audit_agent is not None:
        capabilities = AgentCapabilityStatus(
            status="ready",
            mentor=True,
            fact_audit=True,
            question_writer=question_writer is not None,
            framework="injected",
            model="injected",
        )
    else:
        capabilities = AgentCapabilityStatus.offline(
            "LLM runtime is not configured for this application instance"
        )
    fact_base_service = FactBaseService(fact_base_repository)
    mentor_guide = MentorGuideService(
        job_advisor=job_advisor,
        experience_advisor=experience_advisor,
        followup_advisor=followup_advisor,
    )
    questionnaire_service = QuestionnaireService(
        fact_base_service,
        SQLiteQuestionnaireRepository(store),
        QuestionnaireEngine(
            options_providers={
                "majors": lambda base, state: catalog_majors(),
                "courses": lambda base, state: list(state.course_options),
                "skills": lambda base, state: list(state.skill_options),
            },
            guide=mentor_guide,
        ),
        course_advisor=course_advisor,
        skill_advisor=skill_advisor,
        guide=mentor_guide,
    )
    container = ServiceContainer(
        store=store,
        fact_base_repository=fact_base_repository,
        session_repository=session_repository,
        version_repository=version_repository,
        fact_bases=fact_base_service,
        questionnaires=questionnaire_service,
        interviews=InterviewService(
            fact_base_repository,
            session_repository,
            fact_audit_agent or UnavailableFactAuditAgent(),
            question_writer or DeterministicQuestionWriter(),
            guide=mentor_guide,
        ),
        versions=VersionService(version_repository),
        rendering=ResumeRenderService(
            fact_base_repository,
            version_repository,
            renderer,
            exporter,
            photo_loader=photo_store.load,
            template_loader=template_store.load,
        ),
        summaries=SummaryService(summary_agent),
        snippet_agent=snippet_agent,
        capabilities=capabilities,
        photo_store=photo_store,
        template_store=template_store,
    )
    app = FastAPI(
        title="ResumeAgent API",
        version="0.1.0",
        description="Evidence-driven multi-agent resume mentoring service",
    )
    app.state.container = container

    def _current_version(fact_base_id: UUID) -> Optional[ResumeVersion]:
        versions = container.version_repository.list(fact_base_id)
        if not versions:
            return None
        for version in versions:
            if version.is_active:
                return version
        return versions[-1]

    @app.get("/fact-bases/{fact_base_id}/questionnaire")
    def questionnaire_view(fact_base_id: UUID):
        version = _current_version(fact_base_id)
        container.questionnaires.next_card(fact_base_id, version)  # 触发候选惰性刷新
        base = container.fact_bases.get(fact_base_id)
        state = container.questionnaires._state(fact_base_id)
        return {
            "sections": container.questionnaires.progress(fact_base_id, version),
            "next": container.questionnaires.next_card(fact_base_id, version),
            "job_analysis": state.job_analysis,
        }

    @app.post("/fact-bases/{fact_base_id}/questionnaire/answer")
    def questionnaire_answer(fact_base_id: UUID, payload: QuestionnaireAnswerRequest):
        base = container.questionnaires.answer(
            fact_base_id,
            payload.step_id,
            value=payload.value,
            values=payload.values,
            extra=payload.extra,
        )
        version = _current_version(fact_base_id)
        if payload.step_id == "summary:pick" and version is not None:
            container.versions.set_summary(
                version.id,
                "；".join(value for value in payload.values if value.strip()),
            )
        return {
            "base": base,
            "next": container.questionnaires.next_card(fact_base_id, version),
        }

    @app.post("/fact-bases/{fact_base_id}/questionnaire/skip")
    def questionnaire_skip(fact_base_id: UUID, payload: QuestionnaireSkipRequest):
        return {
            "next": container.questionnaires.skip(fact_base_id, payload.step_id),
        }

    @app.post("/fact-bases/{fact_base_id}/educations", status_code=201)
    def create_education(fact_base_id: UUID, payload: EducationCreateRequest):
        education = Education(
            school=payload.school,
            major=payload.major,
            degree=payload.degree,
            start=payload.start,
            end=payload.end,
            core_courses=payload.core_courses,
            gpa=payload.gpa,
            rank=payload.rank,
            research_direction=payload.research_direction,
            thesis=payload.thesis,
        )
        return container.fact_bases.add_education(fact_base_id, education)

    @app.patch("/fact-bases/{fact_base_id}/educations/{education_id}")
    def update_education(
        fact_base_id: UUID,
        education_id: UUID,
        payload: EducationCreateRequest,
    ):
        base = container.fact_bases.get(fact_base_id)
        current = next(
            item for item in base.educations if item.id == education_id
        )
        updated = Education(
            id=education_id,
            school=payload.school,
            major=payload.major,
            degree=payload.degree,
            start=payload.start,
            end=payload.end,
            core_courses=payload.core_courses,
            gpa=payload.gpa,
            rank=payload.rank,
            research_direction=payload.research_direction,
            thesis=payload.thesis,
            created_at=current.created_at,
            updated_at=utc_now(),
        )
        return container.fact_bases.update_education(fact_base_id, updated)

    @app.delete("/fact-bases/{fact_base_id}/educations/{education_id}")
    def delete_education(fact_base_id: UUID, education_id: UUID):
        return container.fact_bases.remove_education(fact_base_id, education_id)

    @app.patch("/fact-bases/{fact_base_id}/experiences/{experience_id}")
    def update_experience(
        fact_base_id: UUID,
        experience_id: UUID,
        payload: ExperienceUpdateRequest,
    ):
        return container.fact_bases.update_experience(
            fact_base_id,
            experience_id,
            organization=payload.organization,
            role=payload.role,
            experience_type=payload.type,
            start=payload.start,
            end=payload.end,
            linked_skills=payload.linked_skills,
        )

    @app.delete(
        "/fact-bases/{fact_base_id}/experiences/{experience_id}",
        response_model=CareerFactBase,
        tags=["fact-bases"],
    )
    def delete_experience(fact_base_id: UUID, experience_id: UUID) -> CareerFactBase:
        base = container.fact_bases.remove_experience(fact_base_id, experience_id)
        # 清理版本引用：选中列表、排序与挂在经历上的片段
        for version in container.version_repository.list(fact_base_id):
            changed = False
            if experience_id in version.selected_experience_ids:
                version.selected_experience_ids = [
                    item for item in version.selected_experience_ids
                    if item != experience_id
                ]
                changed = True
            if experience_id in version.ordering:
                version.ordering = [
                    item for item in version.ordering if item != experience_id
                ]
                changed = True
            pruned = {
                key: value
                for key, value in version.snippets.items()
                if key != experience_id
            }
            if pruned != version.snippets:
                version.snippets = pruned
                changed = True
            if changed:
                container.versions.save(version)
        return container.fact_bases.get(fact_base_id)

    web_directory = Path(__file__).resolve().parents[1] / "web"
    app.mount(
        "/assets",
        StaticFiles(directory=web_directory),
        name="web-assets",
    )

    @app.get("/", include_in_schema=False)
    def web_workbench() -> FileResponse:
        return FileResponse(web_directory / "index.html", media_type="text/html")

    @app.exception_handler(KeyError)
    def handle_not_found(request: Request, error: KeyError) -> JSONResponse:
        detail = error.args[0] if error.args else str(error)
        return JSONResponse(status_code=404, content={"detail": detail})

    @app.exception_handler(RevisionConflict)
    def handle_revision_conflict(
        request: Request,
        error: RevisionConflict,
    ) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(error)})

    @app.exception_handler(AgentUnavailableError)
    def handle_agent_unavailable(
        request: Request,
        error: AgentUnavailableError,
    ) -> JSONResponse:
        return JSONResponse(status_code=503, content={"detail": str(error)})

    @app.exception_handler(AgentOutputError)
    def handle_agent_output(
        request: Request,
        error: AgentOutputError,
    ) -> JSONResponse:
        return JSONResponse(status_code=502, content={"detail": str(error)})

    @app.exception_handler(RenderEngineUnavailable)
    def handle_render_engine_unavailable(
        request: Request,
        error: RenderEngineUnavailable,
    ) -> JSONResponse:
        return JSONResponse(status_code=503, content={"detail": str(error)})

    @app.exception_handler(ValueError)
    def handle_invalid_state(request: Request, error: ValueError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": str(error)})

    @app.get("/health", tags=["system"])
    def health() -> dict:
        return {"status": "ok"}

    @app.get(
        "/capabilities",
        response_model=AgentCapabilityStatus,
        tags=["system"],
    )
    def capabilities() -> AgentCapabilityStatus:
        return container.capabilities

    @app.get("/schools/search", tags=["catalog"])
    def search_schools(q: str = "", limit: int = 8) -> list[dict]:
        return search_school_catalog(q, limit=limit)

    PHOTO_EXTENSIONS = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
    }

    @app.put(
        "/fact-bases/{fact_base_id}/photo",
        response_model=CareerFactBase,
        tags=["fact-bases"],
    )
    async def upload_photo(fact_base_id: UUID, photo: UploadFile = File(...)):
        data = await photo.read()
        if len(data) > MAX_PHOTO_BYTES:
            raise HTTPException(status_code=413, detail="照片不能超过 5MB")
        extension = PHOTO_EXTENSIONS.get(photo.content_type or "")
        if extension is None:
            raise HTTPException(
                status_code=415, detail="仅支持 JPG / PNG / WebP 图片"
            )
        filename = container.photo_store.save(fact_base_id, data, extension)
        return container.fact_bases.set_photo(fact_base_id, filename)

    @app.get("/fact-bases/{fact_base_id}/photo", tags=["fact-bases"])
    def get_photo(fact_base_id: UUID) -> Response:
        base = container.fact_bases.get(fact_base_id)
        if not base.profile.photo:
            raise HTTPException(status_code=404, detail="尚未上传照片")
        data = container.photo_store.load(base.profile.photo)
        if data is None:
            raise HTTPException(status_code=404, detail="照片文件不存在")
        return Response(
            content=data,
            media_type=container.photo_store.media_type(base.profile.photo),
        )

    @app.delete(
        "/fact-bases/{fact_base_id}/photo",
        response_model=CareerFactBase,
        tags=["fact-bases"],
    )
    def delete_photo(fact_base_id: UUID) -> CareerFactBase:
        base = container.fact_bases.get(fact_base_id)
        if base.profile.photo:
            container.photo_store.delete(base.profile.photo)
        return container.fact_bases.clear_photo(fact_base_id)

    @app.put(
        "/fact-bases/{fact_base_id}/template",
        response_model=CareerFactBase,
        tags=["fact-bases"],
    )
    async def upload_template(
        fact_base_id: UUID,
        template: UploadFile = File(...),
    ) -> CareerFactBase:
        data = await template.read()
        if len(data) > MAX_TEMPLATE_BYTES:
            raise HTTPException(status_code=413, detail="模板不能超过 2MB")
        try:
            content = data.decode("utf-8")
        except UnicodeDecodeError:
            raise HTTPException(status_code=415, detail="仅支持 UTF-8 编码的 HTML 模板")
        if "<html" not in content.lower() and "{{" not in content:
            raise HTTPException(status_code=415, detail="模板必须是 HTML（可包含占位符）")
        filename = container.template_store.save(fact_base_id, content)
        return container.fact_bases.set_template(fact_base_id, filename)

    @app.get("/fact-bases/{fact_base_id}/template", tags=["fact-bases"])
    def get_template(fact_base_id: UUID) -> Response:
        base = container.fact_bases.get(fact_base_id)
        if not base.profile.template:
            raise HTTPException(status_code=404, detail="尚未上传学校模板")
        content = container.template_store.load(base.profile.template)
        if content is None:
            raise HTTPException(status_code=404, detail="模板文件不存在")
        return Response(content=content, media_type="text/html")

    @app.delete(
        "/fact-bases/{fact_base_id}/template",
        response_model=CareerFactBase,
        tags=["fact-bases"],
    )
    def delete_template(fact_base_id: UUID) -> CareerFactBase:
        base = container.fact_bases.get(fact_base_id)
        if base.profile.template:
            container.template_store.delete(base.profile.template)
        return container.fact_bases.clear_template(fact_base_id)

    @app.post(
        "/fact-bases",
        response_model=CareerFactBase,
        status_code=status.HTTP_201_CREATED,
        tags=["fact-bases"],
    )
    def create_fact_base(request: FactBaseCreateRequest) -> CareerFactBase:
        return container.fact_bases.create(request.target)

    @app.get(
        "/fact-bases",
        response_model=list[CareerFactBase],
        tags=["fact-bases"],
    )
    def list_fact_bases() -> list[CareerFactBase]:
        return container.fact_bases.list()

    @app.get(
        "/fact-bases/{fact_base_id}",
        response_model=CareerFactBase,
        tags=["fact-bases"],
    )
    def get_fact_base(fact_base_id: UUID) -> CareerFactBase:
        return container.fact_bases.get(fact_base_id)

    @app.post(
        "/fact-bases/{fact_base_id}/experiences",
        response_model=CareerFactBase,
        status_code=status.HTTP_201_CREATED,
        tags=["fact-bases"],
    )
    def add_experience(
        fact_base_id: UUID,
        request: ExperienceCreateRequest,
    ) -> CareerFactBase:
        return container.fact_bases.add_experience(
            fact_base_id,
            request.organization,
            request.role,
        )

    @app.patch(
        "/fact-bases/{fact_base_id}/profile",
        response_model=CareerFactBase,
        tags=["fact-bases"],
    )
    def update_profile(
        fact_base_id: UUID,
        request: ProfileUpdateRequest,
    ) -> CareerFactBase:
        return container.fact_bases.update_profile(fact_base_id, request)

    @app.get(
        "/fact-bases/{fact_base_id}/experiences/{experience_id}/quality",
        response_model=QualityReport,
        tags=["fact-bases"],
    )
    def get_experience_quality(
        fact_base_id: UUID,
        experience_id: UUID,
    ) -> QualityReport:
        base = container.fact_bases.get(fact_base_id)
        return evaluate_experience(base.get_experience(experience_id))

    @app.post("/fact-bases/{fact_base_id}/experiences/{experience_id}/snippets/generate")
    def generate_experience_snippets(fact_base_id: UUID, experience_id: UUID):
        base = container.fact_bases.get(fact_base_id)
        experience = base.get_experience(experience_id)
        facts = [
            value
            for values in experience.statements.values()
            for value in values
            if value.confidence
            in (ConfidenceStatus.CONFIRMED, ConfidenceStatus.ESTIMATED)
        ]
        if not facts:
            return {"snippets": []}
        text = "；".join(value.text for value in facts)
        if container.snippet_agent is not None:
            try:
                generated = container.snippet_agent.write(
                    experience, "\n".join(value.text for value in facts)
                )
                if generated:
                    text = generated[0]
            except Exception:
                pass  # 离线/失败时退化为事实合并卡
        return {
            "snippets": [
                {
                    "text": text,
                    "source_fact_ids": [str(value.id) for value in facts],
                }
            ]
        }

    @app.post(
        "/sessions",
        response_model=InterviewSession,
        status_code=status.HTTP_201_CREATED,
        tags=["interviews"],
    )
    def create_session(request: SessionCreateRequest) -> InterviewSession:
        return container.interviews.create_session(
            request.fact_base_id,
            request.active_experience_id,
        )

    @app.get(
        "/sessions/{session_id}",
        response_model=InterviewSession,
        tags=["interviews"],
    )
    def get_session(session_id: UUID) -> InterviewSession:
        return container.interviews.get_session(session_id)

    @app.get(
        "/fact-bases/{fact_base_id}/sessions",
        response_model=list[InterviewSession],
        tags=["interviews"],
    )
    def list_sessions(
        fact_base_id: UUID,
        experience_id: Optional[UUID] = None,
    ) -> list[InterviewSession]:
        return container.interviews.list_sessions(fact_base_id, experience_id)

    @app.post(
        "/sessions/{session_id}/answers",
        response_model=InterviewTurn,
        tags=["interviews"],
    )
    def answer(session_id: UUID, request: AnswerRequest) -> InterviewTurn:
        return container.interviews.answer(session_id, request.message)

    @app.post(
        "/sessions/{session_id}/proposals/{proposal_id}/confirm",
        response_model=InterviewTurn,
        tags=["interviews"],
    )
    def confirm(session_id: UUID, proposal_id: UUID) -> InterviewTurn:
        return container.interviews.confirm(session_id, proposal_id)

    @app.post(
        "/sessions/{session_id}/proposals/{proposal_id}/reject",
        response_model=InterviewSession,
        tags=["interviews"],
    )
    def reject(session_id: UUID, proposal_id: UUID) -> InterviewSession:
        return container.interviews.reject(session_id, proposal_id)

    @app.post(
        "/sessions/{session_id}/unknown",
        response_model=UnknownOutcome,
        tags=["interviews"],
    )
    def record_unknown(
        session_id: UUID,
        request: UnknownRequest,
    ) -> UnknownOutcome:
        return container.interviews.record_unknown(
            session_id,
            request.dimension,
        )

    @app.get(
        "/sessions/{session_id}/next-question",
        response_model=Optional[MentorQuestion],
        tags=["interviews"],
    )
    def next_question(session_id: UUID) -> Optional[MentorQuestion]:
        return container.interviews.next_question(session_id)

    @app.get(
        "/sessions/{session_id}/current-question",
        response_model=Optional[MentorQuestion],
        tags=["interviews"],
    )
    def current_question(session_id: UUID) -> Optional[MentorQuestion]:
        return container.interviews.next_question(session_id)

    @app.post(
        "/fact-bases/{fact_base_id}/versions",
        response_model=ResumeVersion,
        status_code=status.HTTP_201_CREATED,
        tags=["versions"],
    )
    def create_version(
        fact_base_id: UUID,
        request: VersionCreateRequest,
    ) -> ResumeVersion:
        base = container.fact_bases.get(fact_base_id)
        return container.versions.create(
            base,
            request.name,
            selected_experience_ids=request.selected_experience_ids,
            target_role=request.target_role,
            company=request.company,
            raw_jd=request.raw_jd,
            locale=request.locale,
        )

    @app.get(
        "/fact-bases/{fact_base_id}/versions",
        response_model=list[ResumeVersion],
        tags=["versions"],
    )
    def list_versions(fact_base_id: UUID) -> list[ResumeVersion]:
        container.fact_bases.get(fact_base_id)
        return container.versions.list(fact_base_id)

    @app.post(
        "/fact-bases/{fact_base_id}/versions/refresh-staleness",
        response_model=list[ResumeVersion],
        tags=["versions"],
    )
    def refresh_staleness(fact_base_id: UUID) -> list[ResumeVersion]:
        base = container.fact_bases.get(fact_base_id)
        return container.versions.refresh_staleness(base)

    @app.get(
        "/versions/{version_id}",
        response_model=ResumeVersion,
        tags=["versions"],
    )
    def get_version(version_id: UUID) -> ResumeVersion:
        return container.versions.get(version_id)

    @app.get(
        "/versions/{version_id}/preview",
        response_model=RenderedResume,
        tags=["rendering"],
    )
    def preview_version(version_id: UUID) -> RenderedResume:
        return container.rendering.preview(version_id)

    @app.get(
        "/versions/{version_id}/export",
        tags=["rendering"],
    )
    def export_version(version_id: UUID, format: RenderFormat) -> Response:
        exported = container.rendering.export(version_id, format)
        ascii_filename = f"resume_{format.value}.{format.value}"
        encoded_filename = quote(exported.filename)
        disposition = (
            f'attachment; filename="{ascii_filename}"; '
            f"filename*=UTF-8''{encoded_filename}"
        )
        return Response(
            content=exported.content,
            media_type=exported.media_type,
            headers={"Content-Disposition": disposition},
        )

    @app.post(
        "/versions/{version_id}/clone",
        response_model=ResumeVersion,
        status_code=status.HTTP_201_CREATED,
        tags=["versions"],
    )
    def clone_version(
        version_id: UUID,
        request: VersionCloneRequest,
    ) -> ResumeVersion:
        return container.versions.clone(version_id, request.name)

    @app.patch(
        "/versions/{version_id}",
        response_model=ResumeVersion,
        tags=["versions"],
    )
    def rename_version(
        version_id: UUID,
        request: VersionRenameRequest,
    ) -> ResumeVersion:
        return container.versions.rename(version_id, request.name)

    @app.put(
        "/versions/{version_id}/style",
        response_model=ResumeVersion,
        tags=["versions"],
    )
    def set_version_style(
        version_id: UUID,
        request: VersionStyleRequest,
    ) -> ResumeVersion:
        return container.versions.set_style(version_id, request.style)

    @app.put(
        "/versions/{version_id}/draft",
        response_model=ResumeVersion,
        tags=["versions"],
    )
    def set_version_draft(
        version_id: UUID,
        request: VersionDraftRequest,
    ) -> ResumeVersion:
        return container.versions.set_draft(
            version_id,
            request.markdown,
            request.html,
        )

    @app.post("/versions/{version_id}/summary-options/generate")
    def generate_summary_options(version_id: UUID):
        version = container.version_repository.get(version_id)
        base = container.fact_base_repository.get(version.fact_base_id)
        options = container.summaries.generate(base, version)
        updated = container.versions.set_summary_options(version_id, options)
        return {"options": updated.summary_options}

    @app.put("/versions/{version_id}/summary")
    def set_version_summary(version_id: UUID, payload: SummarySetRequest):
        return container.versions.set_summary(version_id, payload.text)

    @app.post("/versions/{version_id}/snippets")
    def add_version_snippet(version_id: UUID, payload: VersionSnippetAddRequest):
        return container.versions.add_snippet(
            version_id,
            payload.experience_id,
            payload.text,
            payload.source_fact_ids,
        )

    @app.delete("/versions/{version_id}/snippets/{snippet_id}")
    def delete_version_snippet(version_id: UUID, snippet_id: UUID):
        return container.versions.remove_snippet(version_id, snippet_id)

    @app.post("/versions/{version_id}/experiences/{experience_id}")
    def include_version_experience(version_id: UUID, experience_id: UUID):
        return container.versions.include_experience(version_id, experience_id)

    @app.post(
        "/versions/{version_id}/activate",
        response_model=ResumeVersion,
        tags=["versions"],
    )
    def activate_version(version_id: UUID) -> ResumeVersion:
        return container.versions.activate(version_id)

    @app.delete(
        "/versions/{version_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        tags=["versions"],
    )
    def delete_version(version_id: UUID) -> Response:
        container.versions.delete(version_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return app
