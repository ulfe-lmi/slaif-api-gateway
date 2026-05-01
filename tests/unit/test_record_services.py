import uuid
from datetime import UTC, datetime, timedelta

import pytest

from slaif_gateway.db.models import Cohort, Institution, Owner
from slaif_gateway.services.cohort_service import CohortService
from slaif_gateway.services.institution_service import InstitutionService
from slaif_gateway.services.owner_service import OwnerService
from slaif_gateway.services.record_errors import DuplicateRecordError, RecordNotFoundError


class _AuditRepo:
    def __init__(self) -> None:
        self.rows: list[dict[str, object]] = []

    async def add_audit_log(self, **kwargs):
        self.rows.append(kwargs)


class _InstitutionRepo:
    def __init__(self, rows: list[Institution]) -> None:
        self.rows = {row.id: row for row in rows}

    async def get_institution_by_id(self, institution_id):
        return self.rows.get(institution_id)

    async def get_institution_by_name(self, name):
        for row in self.rows.values():
            if row.name.lower() == name.lower():
                return row
        return None

    async def update_institution_metadata(self, institution_id, **kwargs):
        row = self.rows.get(institution_id)
        if row is None:
            return None
        row.name = kwargs["name"]
        row.country = kwargs["country"]
        row.notes = kwargs["notes"]
        return row


class _CohortRepo:
    def __init__(self, rows: list[Cohort]) -> None:
        self.rows = {row.id: row for row in rows}

    async def get_cohort_by_id(self, cohort_id):
        return self.rows.get(cohort_id)

    async def get_cohort_by_name(self, name):
        for row in self.rows.values():
            if row.name == name:
                return row
        return None

    async def update_cohort_metadata(self, cohort_id, **kwargs):
        row = self.rows.get(cohort_id)
        if row is None:
            return None
        row.name = kwargs["name"]
        row.description = kwargs["description"]
        row.starts_at = kwargs["starts_at"]
        row.ends_at = kwargs["ends_at"]
        return row


class _OwnerRepo:
    def __init__(self, rows: list[Owner]) -> None:
        self.rows = {row.id: row for row in rows}

    async def get_owner_by_id(self, owner_id):
        return self.rows.get(owner_id)

    async def get_owner_by_email(self, email):
        for row in self.rows.values():
            if row.email == email:
                return row
        return None

    async def update_owner_metadata(self, owner_id, **kwargs):
        row = self.rows.get(owner_id)
        if row is None:
            return None
        for key, value in kwargs.items():
            setattr(row, key, value)
        return row


def _institution(name: str = "Old University") -> Institution:
    return Institution(id=uuid.uuid4(), name=name, country="SI", notes="old")


def _cohort(name: str = "Old Cohort") -> Cohort:
    now = datetime.now(UTC)
    return Cohort(
        id=uuid.uuid4(),
        name=name,
        description="old",
        starts_at=now - timedelta(days=1),
        ends_at=now + timedelta(days=1),
    )


def _owner(email: str = "old@example.org", institution_id: uuid.UUID | None = None) -> Owner:
    return Owner(
        id=uuid.uuid4(),
        name="Old",
        surname="Owner",
        email=email,
        institution_id=institution_id,
        external_id="old",
        notes="old",
        is_active=True,
    )


@pytest.mark.asyncio
async def test_institution_update_writes_safe_audit() -> None:
    row = _institution()
    audit = _AuditRepo()
    service = InstitutionService(institutions_repository=_InstitutionRepo([row]), audit_repository=audit)
    actor_id = uuid.uuid4()

    updated = await service.update_institution(
        row.id,
        name="New University",
        country="AT",
        notes="safe note",
        actor_admin_id=actor_id,
        reason="records update",
    )

    assert updated.name == "New University"
    assert audit.rows[0]["admin_user_id"] == actor_id
    assert audit.rows[0]["action"] == "institution_updated"
    assert audit.rows[0]["old_values"]["name"] == "Old University"
    assert audit.rows[0]["new_values"]["notes"] == "safe note"


@pytest.mark.asyncio
async def test_cohort_update_rejects_duplicate_and_invalid_window() -> None:
    row = _cohort("Workshop A")
    duplicate = _cohort("Workshop B")
    service = CohortService(cohorts_repository=_CohortRepo([row, duplicate]), audit_repository=_AuditRepo())

    with pytest.raises(DuplicateRecordError):
        await service.update_cohort(row.id, name="Workshop B")

    with pytest.raises(ValueError, match="ends_at"):
        await service.update_cohort(
            row.id,
            name="Workshop A",
            starts_at=datetime(2026, 2, 1, tzinfo=UTC),
            ends_at=datetime(2026, 1, 1, tzinfo=UTC),
        )


@pytest.mark.asyncio
async def test_owner_update_validates_institution_and_audits() -> None:
    institution = _institution()
    owner = _owner(institution_id=institution.id)
    audit = _AuditRepo()
    service = OwnerService(
        owners_repository=_OwnerRepo([owner]),
        institutions_repository=_InstitutionRepo([institution]),
        audit_repository=audit,
    )

    updated = await service.update_owner(
        owner.id,
        name="Ada",
        surname="Lovelace",
        email="ADA@EXAMPLE.ORG",
        institution_id=None,
        external_id="safe-id",
        notes="safe note",
        is_active=False,
        actor_admin_id=uuid.uuid4(),
        reason="records update",
    )

    assert updated.email == "ada@example.org"
    assert updated.institution_id is None
    assert updated.is_active is False
    assert audit.rows[0]["action"] == "owner_updated"
    assert "password_hash" not in str(audit.rows[0])


@pytest.mark.asyncio
async def test_owner_update_rejects_unknown_institution() -> None:
    owner = _owner()
    service = OwnerService(
        owners_repository=_OwnerRepo([owner]),
        institutions_repository=_InstitutionRepo([]),
        audit_repository=_AuditRepo(),
    )

    with pytest.raises(RecordNotFoundError):
        await service.update_owner(
            owner.id,
            name="Ada",
            surname="Lovelace",
            email="ada@example.org",
            institution_id=uuid.uuid4(),
            external_id=None,
            notes=None,
            is_active=True,
        )
