"""Transport-only request models for the ResumeAgent API."""

from typing import Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from resume_agent.domain.models import (
    CandidateProfile,
    CareerTarget,
    Education,
    ExperienceType,
    QualityDimension,
)


class FactBaseCreateRequest(BaseModel):
    target: CareerTarget = Field(default_factory=CareerTarget)


class ExperienceCreateRequest(BaseModel):
    organization: str = Field(min_length=1)
    role: str = Field(min_length=1)


class ProfileUpdateRequest(CandidateProfile):
    pass


class SessionCreateRequest(BaseModel):
    fact_base_id: UUID
    active_experience_id: UUID


class AnswerRequest(BaseModel):
    message: str = Field(min_length=1)


class UnknownRequest(BaseModel):
    dimension: QualityDimension


class VersionCreateRequest(BaseModel):
    name: str = Field(min_length=1)
    target_role: str = ""
    company: str = ""
    raw_jd: str = ""
    locale: str = "zh"
    selected_experience_ids: List[UUID] = Field(default_factory=list)


class VersionCloneRequest(BaseModel):
    name: str = Field(min_length=1)


class VersionRenameRequest(BaseModel):
    name: str = Field(min_length=1)


class VersionStyleRequest(BaseModel):
    style: str = Field(min_length=1)


class VersionDraftRequest(BaseModel):
    markdown: str = Field(default="", max_length=500_000)
    html: str = Field(default="", max_length=500_000)


class QuestionnaireAnswerRequest(BaseModel):
    step_id: str = Field(min_length=1)
    value: str = ""
    values: List[str] = Field(default_factory=list)
    extra: Dict[str, str] = Field(default_factory=dict)


class QuestionnaireSkipRequest(BaseModel):
    step_id: str = Field(min_length=1)


class EducationCreateRequest(BaseModel):
    school: str = Field(min_length=1)
    major: str = ""
    degree: str = ""
    start: str = ""
    end: Optional[str] = None
    core_courses: List[str] = Field(default_factory=list)


class ExperienceUpdateRequest(BaseModel):
    organization: Optional[str] = None
    role: Optional[str] = None
    type: Optional[ExperienceType] = None
    start: Optional[str] = None
    end: Optional[str] = None
    linked_skills: Optional[List[str]] = None
