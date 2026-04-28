import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import pytest

from slaif_gateway.services.admin_records_dashboard import (
    AdminRecordNotFoundError,
    AdminRecordsDashboardService,
)


@dataclass
class _Institution:
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    name: str = "SLAIF University"
    country: str | None = "SI"
    notes: str | None = "institution note"
    owners: list[object] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC) - timedelta(days=10))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC) - timedelta(days=9))


@dataclass
class _Owner:
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    name: str = "Ada"
    surname: str = "Lovelace"
    email: str = "ada@example.org"
    institution_id: uuid.UUID | None = None
    institution: _Institution | None = None
    external_id: str | None = "external-safe-id"
    notes: str | None = "owner note"
    is_active: bool = True
    anonymized_at: datetime | None = None
    gateway_keys: list[object] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC) - timedelta(days=8))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC) - timedelta(days=7))


@dataclass
class _Cohort:
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    name: str = "Spring Workshop"
    description: str | None = "cohort description"
    starts_at: datetime | None = field(default_factory=lambda: datetime.now(UTC) - timedelta(days=1))
    ends_at: datetime | None = field(default_factory=lambda: datetime.now(UTC) + timedelta(days=10))
    gateway_keys: list[object] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC) - timedelta(days=6))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC) - timedelta(days=5))


@dataclass
class _GatewayKey:
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    public_key_id: str = "public-id"
    key_prefix: str = "sk-slaif-"
    key_hint: str | None = "sk-slaif-public"
    token_hash: str = "token_hash_must_not_escape"
    owner_id: uuid.UUID = field(default_factory=uuid.uuid4)
    owner: _Owner | None = None
    cohort_id: uuid.UUID | None = None
    cohort: _Cohort | None = None
    status: str = "active"
    valid_from: datetime = field(default_factory=lambda: datetime.now(UTC) - timedelta(days=1))
    valid_until: datetime = field(default_factory=lambda: datetime.now(UTC) + timedelta(days=1))
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC) - timedelta(days=4))


class _OwnersRepo:
    def __init__(self, row: _Owner | None) -> None:
        self.row = row
        self.list_calls: list[dict[str, object]] = []

    async def list_owners_for_admin(self, **kwargs):
        self.list_calls.append(kwargs)
        return [self.row] if self.row is not None else []

    async def get_owner_for_admin_detail(self, owner_id: uuid.UUID):
        if self.row is not None and self.row.id == owner_id:
            return self.row
        return None


class _InstitutionsRepo:
    def __init__(self, row: _Institution | None) -> None:
        self.row = row
        self.list_calls: list[dict[str, object]] = []

    async def list_institutions_for_admin(self, **kwargs):
        self.list_calls.append(kwargs)
        return [self.row] if self.row is not None else []

    async def get_institution_for_admin_detail(self, institution_id: uuid.UUID):
        if self.row is not None and self.row.id == institution_id:
            return self.row
        return None


class _CohortsRepo:
    def __init__(self, row: _Cohort | None) -> None:
        self.row = row
        self.list_calls: list[dict[str, object]] = []

    async def list_cohorts_for_admin(self, **kwargs):
        self.list_calls.append(kwargs)
        return [self.row] if self.row is not None else []

    async def get_cohort_for_admin_detail(self, cohort_id: uuid.UUID):
        if self.row is not None and self.row.id == cohort_id:
            return self.row
        return None


def _records() -> tuple[_Owner, _Institution, _Cohort, _GatewayKey]:
    institution = _Institution()
    owner = _Owner(institution_id=institution.id, institution=institution)
    cohort = _Cohort()
    key = _GatewayKey(owner_id=owner.id, owner=owner, cohort_id=cohort.id, cohort=cohort)
    owner.gateway_keys = [key]
    institution.owners = [owner]
    cohort.gateway_keys = [key]
    return owner, institution, cohort, key


def _service(owner: _Owner | None, institution: _Institution | None, cohort: _Cohort | None):
    owners = _OwnersRepo(owner)
    institutions = _InstitutionsRepo(institution)
    cohorts = _CohortsRepo(cohort)
    service = AdminRecordsDashboardService(
        owners_repository=owners,
        institutions_repository=institutions,
        cohorts_repository=cohorts,
    )
    return service, owners, institutions, cohorts


@pytest.mark.asyncio
async def test_owner_list_and_detail_return_safe_rows_and_pass_filters() -> None:
    owner, institution, cohort, _ = _records()
    service, owners, _, _ = _service(owner, institution, cohort)

    rows = await service.list_owners(
        email="ada@example.org",
        institution_id=institution.id,
        cohort_id=cohort.id,
        limit=25,
        offset=5,
    )
    detail = await service.get_owner_detail(owner.id)

    assert rows[0].display_name == "Ada Lovelace"
    assert rows[0].institution_name == "SLAIF University"
    assert rows[0].key_count == 1
    assert rows[0].active_key_count == 1
    assert detail.recent_keys[0].public_key_id == "public-id"
    assert "token_hash" not in rows[0].__dataclass_fields__
    assert "token_hash" not in detail.__dataclass_fields__
    assert owners.list_calls[0]["email"] == "ada@example.org"
    assert owners.list_calls[0]["institution_id"] == institution.id
    assert owners.list_calls[0]["cohort_id"] == cohort.id
    assert owners.list_calls[0]["limit"] == 25
    assert owners.list_calls[0]["offset"] == 5


@pytest.mark.asyncio
async def test_institution_list_and_detail_return_safe_rows_and_pass_filters() -> None:
    owner, institution, cohort, _ = _records()
    service, _, institutions, _ = _service(owner, institution, cohort)

    rows = await service.list_institutions(name="slaif", limit=20, offset=3)
    detail = await service.get_institution_detail(institution.id)

    assert rows[0].name == "SLAIF University"
    assert rows[0].owner_count == 1
    assert rows[0].key_count == 1
    assert rows[0].active_key_count == 1
    assert detail.recent_keys[0].owner_email == "ada@example.org"
    assert "token_hash" not in detail.__dataclass_fields__
    assert institutions.list_calls[0]["name"] == "slaif"
    assert institutions.list_calls[0]["limit"] == 20
    assert institutions.list_calls[0]["offset"] == 3


@pytest.mark.asyncio
async def test_cohort_list_and_detail_return_safe_rows_and_pass_filters() -> None:
    owner, institution, cohort, _ = _records()
    service, _, _, cohorts = _service(owner, institution, cohort)

    rows = await service.list_cohorts(name="spring", active=True, limit=10, offset=2)
    detail = await service.get_cohort_detail(cohort.id)

    assert rows[0].name == "Spring Workshop"
    assert rows[0].owner_count == 1
    assert rows[0].key_count == 1
    assert rows[0].active_key_count == 1
    assert detail.recent_keys[0].public_key_id == "public-id"
    assert "token_hash" not in detail.__dataclass_fields__
    assert cohorts.list_calls[0]["name"] == "spring"
    assert cohorts.list_calls[0]["active"] is True
    assert cohorts.list_calls[0]["limit"] == 10
    assert cohorts.list_calls[0]["offset"] == 2


@pytest.mark.asyncio
async def test_missing_records_raise_safe_not_found() -> None:
    service, _, _, _ = _service(None, None, None)

    with pytest.raises(AdminRecordNotFoundError):
        await service.get_owner_detail(uuid.uuid4())
    with pytest.raises(AdminRecordNotFoundError):
        await service.get_institution_detail(uuid.uuid4())
    with pytest.raises(AdminRecordNotFoundError):
        await service.get_cohort_detail(uuid.uuid4())
