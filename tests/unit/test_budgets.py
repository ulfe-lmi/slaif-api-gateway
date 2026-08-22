import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from slaif_gateway.db.models import BudgetPeriod
from slaif_gateway.services.budget_service import BudgetService
from slaif_gateway.services.quota_errors import QuotaLimitExceededError


def _budget(*, cost_limit: str = "10") -> BudgetPeriod:
    now = datetime.now(UTC)
    return BudgetPeriod(id=uuid.uuid4(), name="org-budget", period_type="fixed",
                        period_start=now, period_end=now + timedelta(days=1),
                        cost_limit_eur=cost_limit,
                        cost_used_eur=Decimal("0"), cost_reserved_eur=Decimal("0"),
                        tokens_used_total=0, tokens_reserved_total=0,
                        requests_used_total=0, requests_reserved_total=0,
                        carryover_policy="none")


@pytest.mark.asyncio
async def test_atomic_reservation_rejects_when_any_level_exceeds(monkeypatch):
    rows = [_budget(cost_limit="1")]
    session = SimpleNamespace()
    service = BudgetService.__new__(BudgetService)
    service._session = session

    async def fake_applicable(self, *, owner_id, now):
        return rows

    async def fake_get(object_cls, object_id, *, with_for_update=False):
        return next(row for row in rows if row.id == object_id)

    monkeypatch.setattr(BudgetService, "_applicable_budgets", fake_applicable)
    monkeypatch.setattr(session, "get", fake_get, raising=False)
    with pytest.raises(QuotaLimitExceededError):
        await service.reserve(
            gateway_key=SimpleNamespace(owner_id=uuid.uuid4()),
            reserved_cost_eur=Decimal("2"), reserved_tokens=10, reserved_requests=1,
        )


@pytest.mark.asyncio
async def test_atomic_reservation_passes_within_limits(monkeypatch):
    rows = [_budget(cost_limit="10")]
    session = SimpleNamespace()
    service = BudgetService.__new__(BudgetService)
    service._session = session

    async def fake_applicable(self, *, owner_id, now):
        return rows

    async def fake_get(object_cls, object_id, *, with_for_update=False):
        return next(row for row in rows if row.id == object_id)

    async def fake_flush():
        return None

    monkeypatch.setattr(BudgetService, "_applicable_budgets", fake_applicable)
    monkeypatch.setattr(session, "get", fake_get, raising=False)
    monkeypatch.setattr(session, "flush", fake_flush, raising=False)
    locked = await service.reserve(
        gateway_key=SimpleNamespace(owner_id=uuid.uuid4()),
        reserved_cost_eur=Decimal("2"), reserved_tokens=10, reserved_requests=1,
    )
    assert len(locked) == 1
