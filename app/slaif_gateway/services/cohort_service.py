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
from slaif_gateway.schemas.record_edits import (
    CohortUpdatePatch,
    assert_cohort_update_patch_safe,
    assert_cohort_current_metadata_safe,
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

        normalized_name = await self._validate_cohort_update_values(
            name, cohort_id=parsed_id, starts_at=starts_at, ends_at=ends_at
        )
        return await self._commit_cohort_update(
            parsed_id,
            name=normalized_name,
            description=description,
            starts_at=starts_at,
            ends_at=ends_at,
            actor_admin_id=actor_admin_id,
            reason=reason,
            old_values=old_values,
        )

    async def update_cohort_partial(
        self,
        cohort_id: uuid.UUID | str,
        *,
        patch: CohortUpdatePatch,
        actor_admin_id: uuid.UUID | None = None,
        reason: str,
    ) -> Cohort:
        """Apply a typed partial edit to ONE cohort (caller-owned txn).

        Enforces the shared patch boundary, then locks the target row
        FIRST, merges the provided fields with the fresh stored values
        (the FINAL merged date window is validated, so an omitted side
        still participates), and DELEGATES to the same shared
        normalization/validation and repository-write/audit helpers as
        the existing complete update (no duplicated body). A late failure
        propagates so the caller transaction rolls back the row and the
        provisional audit.

        The FRESH stored editable metadata of the selected row is guarded
        before the audit snapshot/write, so an existing recognized
        secret-shape value (omitted or explicitly cleared) is refused
        with zero writes/audits instead of leaking into the audit.
        """
        assert_cohort_update_patch_safe(patch, reason=reason)
        parsed_id = _parse_cohort_id(cohort_id)
        existing = await self._cohorts.get_cohort_for_update(parsed_id)
        if existing is None:
            raise RecordNotFoundError("Cohort")
        assert_cohort_current_metadata_safe(
            name=existing.name, description=existing.description
        )

        # Merge provided fields with the CURRENT stored values (omitted
        # flags preserve everything, including nullable fields).
        name = patch.name if patch.name is not None else existing.name
        description = (
            None
            if patch.clear_description
            else patch.description
            if patch.description is not None
            else existing.description
        )
        starts_at = (
            None
            if patch.clear_starts_at
            else patch.starts_at
            if patch.starts_at is not None
            else existing.starts_at
        )
        ends_at = (
            None
            if patch.clear_ends_at
            else patch.ends_at
            if patch.ends_at is not None
            else existing.ends_at
        )

        normalized_name = await self._validate_cohort_update_values(
            name, cohort_id=parsed_id, starts_at=starts_at, ends_at=ends_at
        )
        return await self._commit_cohort_update(
            parsed_id,
            name=normalized_name,
            description=description,
            starts_at=starts_at,
            ends_at=ends_at,
            actor_admin_id=actor_admin_id,
            reason=reason,
            old_values=_safe_audit_values(existing),
        )

    async def _validate_cohort_update_values(
        self,
        name: str,
        *,
        cohort_id: uuid.UUID,
        starts_at: datetime | None,
        ends_at: datetime | None,
    ) -> str:
        """Existing complete-update name/window/duplicate law (shared)."""
        normalized_name = name.strip()
        if not normalized_name:
            raise ValueError("Cohort name cannot be empty")
        if starts_at is not None and ends_at is not None and ends_at <= starts_at:
            raise ValueError("ends_at must be after starts_at")
        duplicate = await self._cohorts.get_cohort_by_name(normalized_name)
        if duplicate is not None and duplicate.id != cohort_id:
            raise DuplicateRecordError("Cohort", "name")
        return normalized_name

    async def _commit_cohort_update(
        self,
        parsed_id: uuid.UUID,
        *,
        name: str,
        description: str | None,
        starts_at: datetime | None,
        ends_at: datetime | None,
        actor_admin_id: uuid.UUID | None,
        reason: str | None,
        old_values: dict[str, object],
    ) -> Cohort:
        """Existing repository write + exact cohort_updated audit (shared)."""
        updated = await self._cohorts.update_cohort_metadata(
            parsed_id,
            name=name,
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
