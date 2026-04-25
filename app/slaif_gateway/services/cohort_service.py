"""Service helpers for cohort records."""

from __future__ import annotations

import uuid
from datetime import datetime

from slaif_gateway.db.models import Cohort
from slaif_gateway.db.repositories.audit import AuditRepository
from slaif_gateway.db.repositories.cohorts import CohortsRepository
from slaif_gateway.services.record_errors import (
    DuplicateRecordError,
    RecordNotFoundError,
    UnsupportedRecordOperationError,
)


class CohortService:
    """Small service layer for cohort CLI operations."""

    def __init__(
        self,
        *,
        cohorts_repository: CohortsRepository,
        audit_repository: AuditRepository,
    ) -> None:
        self._cohorts = cohorts_repository
        self._audit = audit_repository

    async def create_cohort(
        self,
        *,
        name: str,
        description: str | None = None,
        starts_at: datetime | None = None,
        ends_at: datetime | None = None,
        institution_id: uuid.UUID | None = None,
    ) -> Cohort:
        if institution_id is not None:
            raise UnsupportedRecordOperationError(
                "Cohorts are not linked to institutions in the current database schema"
            )
        normalized_name = name.strip()
        if not normalized_name:
            raise ValueError("Cohort name cannot be empty")
        if starts_at is not None and ends_at is not None and ends_at <= starts_at:
            raise ValueError("ends_at must be after starts_at")
        if await self._cohorts.get_cohort_by_name(normalized_name) is not None:
            raise DuplicateRecordError("Cohort", "name")

        cohort = await self._cohorts.create_cohort(
            name=normalized_name,
            description=_clean_optional(description),
            starts_at=starts_at,
            ends_at=ends_at,
        )
        await self._audit.add_audit_log(
            action="cohort_created",
            entity_type="cohort",
            entity_id=cohort.id,
            new_values={
                "name": cohort.name,
                "description": cohort.description,
                "starts_at": cohort.starts_at.isoformat() if cohort.starts_at else None,
                "ends_at": cohort.ends_at.isoformat() if cohort.ends_at else None,
            },
        )
        return cohort

    async def list_cohorts(
        self,
        *,
        limit: int,
        institution_id: uuid.UUID | None = None,
    ) -> list[Cohort]:
        if institution_id is not None:
            raise UnsupportedRecordOperationError(
                "Cohorts are not linked to institutions in the current database schema"
            )
        return await self._cohorts.list_cohorts(limit=limit)

    async def get_cohort(self, cohort_id: uuid.UUID) -> Cohort:
        cohort = await self._cohorts.get_cohort_by_id(cohort_id)
        if cohort is None:
            raise RecordNotFoundError("Cohort")
        return cohort


def _clean_optional(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None
