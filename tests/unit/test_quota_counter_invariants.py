from __future__ import annotations

import inspect
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from slaif_gateway.db.repositories import keys as keys_repository_module
from slaif_gateway.db.repositories.keys import GatewayKeysRepository
from slaif_gateway.services.quota_errors import QuotaCounterInvariantError


class FakeSession:
    def __init__(self) -> None:
        self.flush_count = 0

    async def flush(self) -> None:
        self.flush_count += 1


def _gateway_key(**overrides):
    values = {
        "cost_reserved_eur": Decimal("0.300000000"),
        "tokens_reserved_total": 200,
        "requests_reserved_total": 1,
        "cost_used_eur": Decimal("0"),
        "tokens_used_total": 0,
        "requests_used_total": 0,
        "last_used_at": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.asyncio
async def test_subtract_reserved_counters_decrements_once_without_clamping() -> None:
    session = FakeSession()
    gateway_key = _gateway_key()
    repository = GatewayKeysRepository(session)  # type: ignore[arg-type]

    await repository.subtract_reserved_counters(
        gateway_key,  # type: ignore[arg-type]
        cost_reserved_eur=Decimal("0.100000000"),
        tokens_reserved_total=50,
        requests_reserved_total=1,
    )

    assert gateway_key.cost_reserved_eur == Decimal("0.200000000")
    assert gateway_key.tokens_reserved_total == 150
    assert gateway_key.requests_reserved_total == 0
    assert session.flush_count == 1


@pytest.mark.asyncio
async def test_subtract_reserved_counters_raises_before_underflow() -> None:
    session = FakeSession()
    gateway_key = _gateway_key(cost_reserved_eur=Decimal("0.010000000"))
    repository = GatewayKeysRepository(session)  # type: ignore[arg-type]

    with pytest.raises(QuotaCounterInvariantError) as excinfo:
        await repository.subtract_reserved_counters(
            gateway_key,  # type: ignore[arg-type]
            cost_reserved_eur=Decimal("0.100000000"),
            tokens_reserved_total=50,
            requests_reserved_total=1,
        )

    assert excinfo.value.param == "cost_reserved_eur"
    assert gateway_key.cost_reserved_eur == Decimal("0.010000000")
    assert gateway_key.tokens_reserved_total == 200
    assert gateway_key.requests_reserved_total == 1
    assert session.flush_count == 0


@pytest.mark.asyncio
async def test_finalize_reserved_counters_decrements_and_increments_used_counters() -> None:
    session = FakeSession()
    gateway_key = _gateway_key()
    repository = GatewayKeysRepository(session)  # type: ignore[arg-type]
    finished_at = datetime(2026, 4, 25, tzinfo=UTC)

    await repository.finalize_reserved_counters(
        gateway_key,  # type: ignore[arg-type]
        reserved_cost_eur=Decimal("0.300000000"),
        reserved_tokens_total=200,
        reserved_requests_total=1,
        actual_cost_eur=Decimal("0.100000000"),
        actual_tokens_total=75,
        actual_requests_total=1,
        last_used_at=finished_at,
    )

    assert gateway_key.cost_reserved_eur == Decimal("0E-9")
    assert gateway_key.tokens_reserved_total == 0
    assert gateway_key.requests_reserved_total == 0
    assert gateway_key.cost_used_eur == Decimal("0.100000000")
    assert gateway_key.tokens_used_total == 75
    assert gateway_key.requests_used_total == 1
    assert gateway_key.last_used_at == finished_at
    assert session.flush_count == 1


@pytest.mark.asyncio
async def test_finalize_reserved_counters_raises_before_underflow_or_used_increment() -> None:
    session = FakeSession()
    gateway_key = _gateway_key(tokens_reserved_total=100)
    repository = GatewayKeysRepository(session)  # type: ignore[arg-type]

    with pytest.raises(QuotaCounterInvariantError) as excinfo:
        await repository.finalize_reserved_counters(
            gateway_key,  # type: ignore[arg-type]
            reserved_cost_eur=Decimal("0.300000000"),
            reserved_tokens_total=200,
            reserved_requests_total=1,
            actual_cost_eur=Decimal("0.100000000"),
            actual_tokens_total=75,
            actual_requests_total=1,
            last_used_at=datetime(2026, 4, 25, tzinfo=UTC),
        )

    assert excinfo.value.param == "tokens_reserved_total"
    assert gateway_key.cost_reserved_eur == Decimal("0.300000000")
    assert gateway_key.tokens_reserved_total == 100
    assert gateway_key.requests_reserved_total == 1
    assert gateway_key.cost_used_eur == Decimal("0")
    assert gateway_key.tokens_used_total == 0
    assert gateway_key.requests_used_total == 0
    assert session.flush_count == 0


def test_gateway_key_repository_no_longer_silently_clamps_reserved_counters() -> None:
    source = inspect.getsource(keys_repository_module.GatewayKeysRepository.subtract_reserved_counters)
    source += inspect.getsource(keys_repository_module.GatewayKeysRepository.finalize_reserved_counters)

    assert "max(" not in source
    assert "QuotaCounterInvariantError" in inspect.getsource(
        keys_repository_module._ensure_reserved_counters_can_decrement
    )
