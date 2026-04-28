"""Safe DTOs for read-only admin owner, institution, and cohort pages."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class AdminRelatedKeySummary:
    """Safe key summary for record detail pages."""

    id: uuid.UUID
    public_key_id: str
    key_prefix: str
    key_hint: str | None
    owner_email: str | None
    status: str
    computed_display_status: str
    valid_until: datetime


@dataclass(frozen=True, slots=True)
class AdminOwnerListRow:
    """Safe owner metadata for the admin owner list."""

    id: uuid.UUID
    name: str
    surname: str
    display_name: str
    email: str
    institution_id: uuid.UUID | None
    institution_name: str | None
    is_active: bool
    key_count: int
    active_key_count: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class AdminOwnerDetail(AdminOwnerListRow):
    """Safe owner metadata for the admin owner detail page."""

    external_id: str | None
    notes: str | None
    anonymized_at: datetime | None
    recent_keys: tuple[AdminRelatedKeySummary, ...] = ()


@dataclass(frozen=True, slots=True)
class AdminInstitutionListRow:
    """Safe institution metadata for the admin institution list."""

    id: uuid.UUID
    name: str
    country: str | None
    owner_count: int
    key_count: int
    active_key_count: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class AdminInstitutionDetail(AdminInstitutionListRow):
    """Safe institution metadata for the admin institution detail page."""

    notes: str | None
    recent_keys: tuple[AdminRelatedKeySummary, ...] = ()


@dataclass(frozen=True, slots=True)
class AdminCohortListRow:
    """Safe cohort metadata for the admin cohort list."""

    id: uuid.UUID
    name: str
    description: str | None
    starts_at: datetime | None
    ends_at: datetime | None
    owner_count: int
    key_count: int
    active_key_count: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class AdminCohortDetail(AdminCohortListRow):
    """Safe cohort metadata for the admin cohort detail page."""

    recent_keys: tuple[AdminRelatedKeySummary, ...] = ()
