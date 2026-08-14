"""Application operations for the canonical career fact base."""

from typing import List, Optional
from uuid import UUID

from resume_agent.application.ports import FactBaseRepository
from resume_agent.domain.models import (
    CandidateProfile,
    CareerFactBase,
    CareerTarget,
    Education,
    ExperienceType,
    utc_now,
)


class FactBaseService:
    def __init__(self, repository: FactBaseRepository) -> None:
        self.repository = repository

    def create(self, target: Optional[CareerTarget] = None) -> CareerFactBase:
        base = CareerFactBase(target=target or CareerTarget())
        self.repository.create(base)
        return self.repository.get(base.id)

    def get(self, fact_base_id: UUID) -> CareerFactBase:
        return self.repository.get(fact_base_id)

    def list(self) -> List[CareerFactBase]:
        return self.repository.list()

    def add_experience(
        self,
        fact_base_id: UUID,
        organization: str,
        role: str,
    ) -> CareerFactBase:
        base = self.repository.get(fact_base_id)
        expected_revision = base.revision
        base.add_experience(organization, role)
        base.revision += 1
        self.repository.save(base, expected_revision=expected_revision)
        return self.repository.get(base.id)

    def update_profile(
        self,
        fact_base_id: UUID,
        profile: CandidateProfile,
    ) -> CareerFactBase:
        base = self.repository.get(fact_base_id)
        expected_revision = base.revision
        base.profile = profile
        base.revision += 1
        base.updated_at = utc_now()
        self.repository.save(base, expected_revision=expected_revision)
        return self.repository.get(base.id)

    def set_photo(self, fact_base_id: UUID, filename: str) -> CareerFactBase:
        base = self.repository.get(fact_base_id)
        expected_revision = base.revision
        base.profile.photo = filename
        base.revision += 1
        base.updated_at = utc_now()
        self.repository.save(base, expected_revision=expected_revision)
        return self.repository.get(base.id)

    def clear_photo(self, fact_base_id: UUID) -> CareerFactBase:
        base = self.repository.get(fact_base_id)
        expected_revision = base.revision
        base.profile.photo = ""
        base.revision += 1
        base.updated_at = utc_now()
        self.repository.save(base, expected_revision=expected_revision)
        return self.repository.get(base.id)

    def save(self, base: CareerFactBase, expected_revision: int) -> None:
        self.repository.save(base, expected_revision=expected_revision)

    def add_education(self, fact_base_id: UUID, education: Education) -> CareerFactBase:
        base = self.repository.get(fact_base_id)
        expected_revision = base.revision
        base.educations.append(education)
        return self._commit(base, expected_revision)

    def update_education(self, fact_base_id: UUID, education: Education) -> CareerFactBase:
        base = self.repository.get(fact_base_id)
        expected_revision = base.revision
        for index, item in enumerate(base.educations):
            if item.id == education.id:
                education.updated_at = utc_now()
                base.educations[index] = education
                return self._commit(base, expected_revision)
        raise KeyError(f"education not found: {education.id}")

    def remove_education(self, fact_base_id: UUID, education_id: UUID) -> CareerFactBase:
        base = self.repository.get(fact_base_id)
        expected_revision = base.revision
        base.educations = [
            item for item in base.educations if item.id != education_id
        ]
        return self._commit(base, expected_revision)

    def update_experience(
        self,
        fact_base_id: UUID,
        experience_id: UUID,
        *,
        organization: Optional[str] = None,
        role: Optional[str] = None,
        experience_type: Optional[ExperienceType] = None,
        start: Optional[str] = None,
        end: Optional[str] = None,
        linked_skills: Optional[List[str]] = None,
    ) -> CareerFactBase:
        base = self.repository.get(fact_base_id)
        expected_revision = base.revision
        experience = base.get_experience(experience_id)
        if organization is not None:
            experience.organization = organization
        if role is not None:
            experience.role = role
        if experience_type is not None:
            experience.type = experience_type
        if start is not None:
            experience.start = start
        if end is not None:
            experience.end = end
        if linked_skills is not None:
            experience.linked_skills = linked_skills
        experience.updated_at = utc_now()
        return self._commit(base, expected_revision)

    def _commit(self, base: CareerFactBase, expected_revision: int) -> CareerFactBase:
        base.revision += 1
        base.updated_at = utc_now()
        self.repository.save(base, expected_revision=expected_revision)
        return self.repository.get(base.id)
