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
        actor_admin_id: uuid.UUID | None = None,
        reason: str | None = None,
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
            admin_user_id=actor_admin_id,
            entity_id=cohort.id,
            new_values=_safe_audit_values(cohort),
            note=_clean_optional(reason),
        )
        return cohort

    async def update_cohort(
        self,
        cohort_id: uuid.UUID | str,
        *,
        name: str,
        description: str | None = None,
        starts_at: datetime | None = None,
        ends_at: datetime | None = None,
        institution_id: uuid.UUID | None = None,
        actor_admin_id: uuid.UUID | None = None,
        reason: str | None = None,
    ) -> Cohort:
        if institution_id is not None:
            raise UnsupportedRecordOperationError(
                "Cohorts are not linked to institutions in the current database schema"
            )
        parsed_id = _parse_cohort_id(cohort_id)
        existing = await self._cohorts.get_cohort_by_id(parsed_id)
        if existing is None:
            raise RecordNotFoundError("Cohort")
        old_values = _safe_audit_values(existing)

        normalized_name = name.strip()
        if not normalized_name:
            raise ValueError("Cohort name cannot be empty")
        if starts_at is not None and ends_at is not None and ends_at <= starts_at:
            raise ValueError("ends_at must be after starts_at")
        duplicate = await self._cohorts.get_cohort_by_name(normalized_name)
        if duplicate is not None and duplicate.id != existing.id:
            raise DuplicateRecordError("Cohort", "name")

        updated = await self._cohorts.update_cohort_metadata(
            parsed_id,
            name=normalized_name,
            description=_clean_optional(description),
            starts_at=starts_at,
            ends_at=ends_at,
        )
        if updated is None:
            raise RecordNotFoundError("Cohort")
        await self._audit.add_audit_log(
            action="cohort_updated",
            entity_type="cohort",
            admin_user_id=actor_admin_id,
            entity_id=updated.id,
            old_values=old_values,
            new_values=_safe_audit_values(updated),
            note=_clean_optional(reason),
        )
        return updated

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


def _parse_cohort_id(value: uuid.UUID | str) -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise RecordNotFoundError("Cohort") from exc


def _safe_audit_values(cohort: Cohort) -> dict[str, object]:
    return {
        "name": cohort.name,
        "description": cohort.description,
        "starts_at": cohort.starts_at.isoformat() if cohort.starts_at else None,
        "ends_at": cohort.ends_at.isoformat() if cohort.ends_at else None,
    }
