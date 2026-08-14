"""Transport-neutral models produced by the resume renderer."""

from typing import List
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from resume_agent.domain.models import ExperienceType, VersionSnippet


class RenderWarning(BaseModel):
    code: str
    message: str


class RenderedExperience(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    organization: str
    role: str
    period: str
    bullets: list[str] = Field(default_factory=list)
    type: ExperienceType = ExperienceType.WORK
    snippet_ids: List[UUID] = Field(default_factory=list)


class RenderedEducation(BaseModel):
    school: str
    major: str = ""
    degree: str = ""
    period: str = ""
    courses: List[str] = Field(default_factory=list)


class RenderedResume(BaseModel):
    version_id: UUID
    base_revision: int
    version_base_revision: int
    locale: str
    style: str
    title: str
    filename_stem: str
    candidate_name: str
    headline: str
    contact_line: str
    summary: str
    experiences: list[RenderedExperience] = Field(default_factory=list)
    educations: List[RenderedEducation] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    self_summary: str = ""
    custom_snippets: List[VersionSnippet] = Field(default_factory=list)
    markdown: str
    html: str
    warnings: list[RenderWarning] = Field(default_factory=list)
