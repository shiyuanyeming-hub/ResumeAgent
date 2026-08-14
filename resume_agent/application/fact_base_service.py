"""Application operations for the canonical career fact base."""

from typing import List, Optional
from uuid import UUID

from resume_agent.application.ports import FactBaseRepository
from resume_agent.domain.models import (
    CandidateProfile,
    CareerFactBase,
    CareerTarget,
    Certification,
    Education,
    JapanExtra,
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

    def update_education(
        self,
        fact_base_id: UUID,
        education: List[Education],
    ) -> CareerFactBase:
        base = self.repository.get(fact_base_id)
        expected_revision = base.revision
        base.education = list(education)
        base.revision += 1
        base.updated_at = utc_now()
        self.repository.save(base, expected_revision=expected_revision)
        return self.repository.get(base.id)

    def update_certifications(
        self,
        fact_base_id: UUID,
        certifications: List[Certification],
    ) -> CareerFactBase:
        base = self.repository.get(fact_base_id)
        expected_revision = base.revision
        base.certifications = list(certifications)
        base.revision += 1
        base.updated_at = utc_now()
        self.repository.save(base, expected_revision=expected_revision)
        return self.repository.get(base.id)

    def update_japan_extra(
        self,
        fact_base_id: UUID,
        japan_extra: JapanExtra,
    ) -> CareerFactBase:
        base = self.repository.get(fact_base_id)
        expected_revision = base.revision
        base.japan_extra = japan_extra
        base.revision += 1
        base.updated_at = utc_now()
        self.repository.save(base, expected_revision=expected_revision)
        return self.repository.get(base.id)
