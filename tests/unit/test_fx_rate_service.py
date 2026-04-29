from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from slaif_gateway.services.fx_rate_service import FxRateService
from slaif_gateway.services.record_errors import RecordNotFoundError


FX_ID = uuid.UUID("55555555-5555-4555-8555-555555555555")


@dataclass
class FakeFxRate:
    id: uuid.UUID = FX_ID
    base_currency: str = "USD"
    quote_currency: str = "EUR"
    rate: Decimal = Decimal("0.920000000")
    valid_from: datetime = datetime(2026, 1, 1, tzinfo=UTC)
    valid_until: datetime | None = None
    source: str | None = "manual source"


class FakeFxRatesRepository:
    def __init__(self, row: FakeFxRate | None = None) -> None:
        self.row = row
        self.created: dict[str, object] | None = None
        self.updated: dict[str, object] | None = None

    async def create_fx_rate(self, **kwargs):
        self.created = kwargs
        self.row = FakeFxRate(**kwargs)
        return self.row

    async def get_fx_rate_by_id(self, fx_rate_id):
        return self.row if self.row is not None and fx_rate_id == self.row.id else None

    async def update_fx_rate_metadata(self, fx_rate_id, **kwargs):
        if self.row is None or fx_rate_id != self.row.id:
            return None
        self.updated = kwargs
        for key, value in kwargs.items():
            setattr(self.row, key, value)
        return self.row


class FakeAuditRepository:
    def __init__(self) -> None:
        self.rows: list[dict[str, object]] = []

    async def add_audit_log(self, **kwargs):
        self.rows.append(kwargs)


def _service(row: FakeFxRate | None = None) -> tuple[FxRateService, FakeFxRatesRepository, FakeAuditRepository]:
    fx_repo = FakeFxRatesRepository(row)
    audit_repo = FakeAuditRepository()
    return FxRateService(fx_rates_repository=fx_repo, audit_repository=audit_repo), fx_repo, audit_repo


@pytest.mark.asyncio
async def test_create_fx_rate_writes_safe_actor_audit() -> None:
    service, fx_repo, audit_repo = _service()
    actor_admin_id = uuid.uuid4()

    row = await service.create_fx_rate(
        base_currency="usd",
        quote_currency="eur",
        rate=Decimal("0.920000000"),
        valid_from=datetime(2026, 1, 1),
        valid_until=None,
        source="manual source",
        actor_admin_id=actor_admin_id,
        reason="dashboard create",
    )

    assert row.base_currency == "USD"
    assert row.quote_currency == "EUR"
    assert fx_repo.created is not None
    assert audit_repo.rows[0]["action"] == "fx_rate_created"
    assert audit_repo.rows[0]["admin_user_id"] == actor_admin_id
    assert audit_repo.rows[0]["note"] == "dashboard create"
    assert "sk-" not in str(audit_repo.rows[0])


@pytest.mark.asyncio
async def test_update_fx_rate_writes_safe_actor_audit() -> None:
    existing = FakeFxRate()
    service, fx_repo, audit_repo = _service(existing)
    actor_admin_id = uuid.uuid4()

    row = await service.update_fx_rate(
        FX_ID,
        base_currency="GBP",
        quote_currency="EUR",
        rate=Decimal("1.160000000"),
        valid_from=datetime(2026, 2, 1, tzinfo=UTC),
        valid_until=None,
        source="manual update",
        actor_admin_id=actor_admin_id,
        reason="dashboard edit",
    )

    assert row.base_currency == "GBP"
    assert row.rate == Decimal("1.160000000")
    assert fx_repo.updated is not None
    assert audit_repo.rows[0]["action"] == "fx_rate_updated"
    assert audit_repo.rows[0]["old_values"]["base_currency"] == "USD"
    assert audit_repo.rows[0]["new_values"]["base_currency"] == "GBP"
    assert audit_repo.rows[0]["admin_user_id"] == actor_admin_id
    assert audit_repo.rows[0]["note"] == "dashboard edit"


@pytest.mark.asyncio
async def test_update_fx_rate_missing_row_raises() -> None:
    service, _, _ = _service()

    with pytest.raises(RecordNotFoundError):
        await service.update_fx_rate(
            uuid.uuid4(),
            base_currency="USD",
            quote_currency="EUR",
            rate=Decimal("0.920000000"),
            valid_from=datetime(2026, 1, 1, tzinfo=UTC),
            valid_until=None,
            source=None,
        )


@pytest.mark.parametrize("rate", [Decimal("0"), Decimal("-0.1")])
@pytest.mark.asyncio
async def test_fx_rate_rejects_non_positive_rate(rate: Decimal) -> None:
    service, _, _ = _service(FakeFxRate())

    with pytest.raises(ValueError, match="positive"):
        await service.update_fx_rate(
            FX_ID,
            base_currency="USD",
            quote_currency="EUR",
            rate=rate,
            valid_from=datetime(2026, 1, 1, tzinfo=UTC),
            valid_until=None,
            source=None,
        )


@pytest.mark.asyncio
async def test_fx_rate_rejects_same_currency_pair() -> None:
    service, _, _ = _service(FakeFxRate())

    with pytest.raises(ValueError, match="must differ"):
        await service.update_fx_rate(
            FX_ID,
            base_currency="EUR",
            quote_currency="EUR",
            rate=Decimal("1.000000000"),
            valid_from=datetime(2026, 1, 1, tzinfo=UTC),
            valid_until=None,
            source=None,
        )
