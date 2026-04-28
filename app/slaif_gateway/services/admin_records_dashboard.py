"""Read-only service for admin owner, institution, and cohort pages."""

from __future__ import annotations

import uuid
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Protocol

from slaif_gateway.db.models import Cohort, GatewayKey, Institution, Owner
from slaif_gateway.schemas.admin_records import (
    AdminCohortDetail,
    AdminCohortListRow,
    AdminInstitutionDetail,
    AdminInstitutionListRow,
    AdminOwnerDetail,
    AdminOwnerListRow,
    AdminRelatedKeySummary,
)
from slaif_gateway.services.admin_key_dashboard import compute_key_display_status


class AdminRecordNotFoundError(Exception):
    """Raised when a requested admin dashboard record is not found."""


class _OwnersAdminRepository(Protocol):
    async def list_owners_for_admin(
        self,
        *,
        email: str | None = None,
        institution_id: uuid.UUID | None = None,
        cohort_id: uuid.UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Owner]: ...

    async def get_owner_for_admin_detail(self, owner_id: uuid.UUID) -> Owner | None: ...


class _InstitutionsAdminRepository(Protocol):
    async def list_institutions_for_admin(
        self,
        *,
        name: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Institution]: ...

    async def get_institution_for_admin_detail(self, institution_id: uuid.UUID) -> Institution | None: ...


class _CohortsAdminRepository(Protocol):
    async def list_cohorts_for_admin(
        self,
        *,
        name: str | None = None,
        active: bool | None = None,
        now: datetime | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Cohort]: ...

    async def get_cohort_for_admin_detail(self, cohort_id: uuid.UUID) -> Cohort | None: ...


class AdminRecordsDashboardService:
    """Build safe read-only DTOs for admin owner, institution, and cohort pages."""

    def __init__(
        self,
        *,
        owners_repository: _OwnersAdminRepository,
        institutions_repository: _InstitutionsAdminRepository,
        cohorts_repository: _CohortsAdminRepository,
    ) -> None:
        self._owners = owners_repository
        self._institutions = institutions_repository
        self._cohorts = cohorts_repository

    async def list_owners(
        self,
        *,
        email: str | None = None,
        institution_id: uuid.UUID | None = None,
        cohort_id: uuid.UUID | None = None,
        limit: int = 50,
        offset: int = 0,
        now: datetime | None = None,
    ) -> list[AdminOwnerListRow]:
        timestamp = _utcnow(now)
        rows = await self._owners.list_owners_for_admin(
            email=_clean_filter(email),
            institution_id=institution_id,
            cohort_id=cohort_id,
            limit=limit,
            offset=offset,
        )
        return [_to_owner_list_row(row, now=timestamp) for row in rows]

    async def get_owner_detail(
        self,
        owner_id: uuid.UUID,
        *,
        now: datetime | None = None,
    ) -> AdminOwnerDetail:
        timestamp = _utcnow(now)
        row = await self._owners.get_owner_for_admin_detail(owner_id)
        if row is None:
            raise AdminRecordNotFoundError("Owner not found")
        list_row = _to_owner_list_row(row, now=timestamp)
        return AdminOwnerDetail(
            **asdict(list_row),
            external_id=row.external_id,
            notes=row.notes,
            anonymized_at=row.anonymized_at,
            recent_keys=_recent_key_summaries(row.gateway_keys, now=timestamp),
        )

    async def list_institutions(
        self,
        *,
        name: str | None = None,
        limit: int = 50,
        offset: int = 0,
        now: datetime | None = None,
    ) -> list[AdminInstitutionListRow]:
        timestamp = _utcnow(now)
        rows = await self._institutions.list_institutions_for_admin(
            name=_clean_filter(name),
            limit=limit,
            offset=offset,
        )
        return [_to_institution_list_row(row, now=timestamp) for row in rows]

    async def get_institution_detail(
        self,
        institution_id: uuid.UUID,
        *,
        now: datetime | None = None,
    ) -> AdminInstitutionDetail:
        timestamp = _utcnow(now)
        row = await self._institutions.get_institution_for_admin_detail(institution_id)
        if row is None:
            raise AdminRecordNotFoundError("Institution not found")
        list_row = _to_institution_list_row(row, now=timestamp)
        return AdminInstitutionDetail(
            **asdict(list_row),
            notes=row.notes,
            recent_keys=_recent_key_summaries(_institution_keys(row), now=timestamp),
        )

    async def list_cohorts(
        self,
        *,
        name: str | None = None,
        active: bool | None = None,
        limit: int = 50,
        offset: int = 0,
        now: datetime | None = None,
    ) -> list[AdminCohortListRow]:
        timestamp = _utcnow(now)
        rows = await self._cohorts.list_cohorts_for_admin(
            name=_clean_filter(name),
            active=active,
            now=timestamp,
            limit=limit,
            offset=offset,
        )
        return [_to_cohort_list_row(row, now=timestamp) for row in rows]

    async def get_cohort_detail(
        self,
        cohort_id: uuid.UUID,
        *,
        now: datetime | None = None,
    ) -> AdminCohortDetail:
        timestamp = _utcnow(now)
        row = await self._cohorts.get_cohort_for_admin_detail(cohort_id)
        if row is None:
            raise AdminRecordNotFoundError("Cohort not found")
        list_row = _to_cohort_list_row(row, now=timestamp)
        return AdminCohortDetail(
            **asdict(list_row),
            recent_keys=_recent_key_summaries(row.gateway_keys, now=timestamp),
        )


def _to_owner_list_row(row: Owner, *, now: datetime) -> AdminOwnerListRow:
    keys = list(row.gateway_keys)
    display_name = _owner_display_name(row)
    institution = row.institution
    return AdminOwnerListRow(
        id=row.id,
        name=row.name,
        surname=row.surname,
        display_name=display_name,
        email=row.email,
        institution_id=row.institution_id,
        institution_name=institution.name if institution is not None else None,
        is_active=row.is_active,
        key_count=len(keys),
        active_key_count=_active_key_count(keys, now=now),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _to_institution_list_row(row: Institution, *, now: datetime) -> AdminInstitutionListRow:
    keys = _institution_keys(row)
    return AdminInstitutionListRow(
        id=row.id,
        name=row.name,
        country=row.country,
        owner_count=len(row.owners),
        key_count=len(keys),
        active_key_count=_active_key_count(keys, now=now),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _to_cohort_list_row(row: Cohort, *, now: datetime) -> AdminCohortListRow:
    keys = list(row.gateway_keys)
    owner_ids = {key.owner_id for key in keys}
    return AdminCohortListRow(
        id=row.id,
        name=row.name,
        description=row.description,
        starts_at=row.starts_at,
        ends_at=row.ends_at,
        owner_count=len(owner_ids),
        key_count=len(keys),
        active_key_count=_active_key_count(keys, now=now),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _recent_key_summaries(keys: list[GatewayKey], *, now: datetime, limit: int = 5) -> tuple[AdminRelatedKeySummary, ...]:
    sorted_keys = sorted(keys, key=lambda key: key.created_at, reverse=True)
    return tuple(_to_key_summary(key, now=now) for key in sorted_keys[:limit])


def _to_key_summary(key: GatewayKey, *, now: datetime) -> AdminRelatedKeySummary:
    owner = key.owner
    return AdminRelatedKeySummary(
        id=key.id,
        public_key_id=key.public_key_id,
        key_prefix=key.key_prefix,
        key_hint=key.key_hint,
        owner_email=owner.email if owner is not None else None,
        status=key.status,
        computed_display_status=compute_key_display_status(key.status, key.valid_from, key.valid_until, now=now),
        valid_until=key.valid_until,
    )


def _institution_keys(row: Institution) -> list[GatewayKey]:
    keys: list[GatewayKey] = []
    for owner in row.owners:
        keys.extend(owner.gateway_keys)
    return keys


def _active_key_count(keys: list[GatewayKey], *, now: datetime) -> int:
    return sum(
        1
        for key in keys
        if compute_key_display_status(key.status, key.valid_from, key.valid_until, now=now) == "active"
    )


def _owner_display_name(owner: Owner) -> str:
    return f"{owner.name} {owner.surname}".strip() or owner.email


def _clean_filter(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _utcnow(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(UTC)
    if now.tzinfo is None:
        return now.replace(tzinfo=UTC)
    return now.astimezone(UTC)
