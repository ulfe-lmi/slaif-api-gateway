from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from slaif_gateway.schemas.auth import AuthenticatedGatewayKey
from slaif_gateway.schemas.policy import ChatCompletionPolicyResult
from slaif_gateway.schemas.pricing import ChatCostEstimate
from slaif_gateway.schemas.routing import RouteResolutionResult
from slaif_gateway.services.accounting import AccountingService
from slaif_gateway.services.quota_errors import QuotaCounterInvariantError


@dataclass
class FakeKeyRow:
    id: uuid.UUID
    cost_reserved_eur: Decimal = Decimal("0.300000000")
    tokens_reserved_total: int = 200
    requests_reserved_total: int = 1
    cost_used_eur: Decimal = Decimal("0")
    tokens_used_total: int = 0
    requests_used_total: int = 0


@dataclass
class FakeReservationRow:
    id: uuid.UUID
    gateway_key_id: uuid.UUID
    request_id: str = "req_1"
    reserved_cost_eur: Decimal = Decimal("0.300000000")
    reserved_tokens: int = 200
    reserved_requests: int = 1
    status: str = "pending"
    created_at: datetime = datetime(2026, 4, 25, tzinfo=UTC)
    released_at: datetime | None = None


class FakeGatewayKeysRepository:
    def __init__(self, row: FakeKeyRow) -> None:
        self.row = row
        self.commits = 0

    async def get_gateway_key_by_id_for_quota_update(self, gateway_key_id):
        return self.row if gateway_key_id == self.row.id else None

    async def subtract_reserved_counters(
        self,
        gateway_key,
        *,
        cost_reserved_eur,
        tokens_reserved_total,
        requests_reserved_total,
    ):
        if gateway_key.cost_reserved_eur < cost_reserved_eur:
            raise QuotaCounterInvariantError(param="cost_reserved_eur")
        if gateway_key.tokens_reserved_total < tokens_reserved_total:
            raise QuotaCounterInvariantError(param="tokens_reserved_total")
        if gateway_key.requests_reserved_total < requests_reserved_total:
            raise QuotaCounterInvariantError(param="requests_reserved_total")
        gateway_key.cost_reserved_eur -= cost_reserved_eur
        gateway_key.tokens_reserved_total -= tokens_reserved_total
        gateway_key.requests_reserved_total -= requests_reserved_total
        return gateway_key


class FakeQuotaReservationsRepository:
    def __init__(self, row: FakeReservationRow) -> None:
        self.row = row
        self.commits = 0

    async def get_reservation_by_id_for_update(self, reservation_id):
        return self.row if reservation_id == self.row.id else None

    async def mark_pending_reservation_released(self, reservation, *, released_at):
        reservation.status = "released"
        reservation.released_at = released_at
        return reservation


class FakeUsageLedgerRepository:
    def __init__(self) -> None:
        self.failure_calls: list[dict[str, object]] = []
        self.commits = 0

    async def create_failure_record(self, **kwargs):
        self.failure_calls.append(kwargs)
        return SimpleNamespace(id=uuid.uuid4(), accounting_status="failed", **kwargs)


def _auth(gateway_key_id: uuid.UUID) -> AuthenticatedGatewayKey:
    now = datetime.now(UTC)
    return AuthenticatedGatewayKey(
        gateway_key_id=gateway_key_id,
        owner_id=uuid.uuid4(),
        cohort_id=None,
        public_key_id="public",
        status="active",
        valid_from=now - timedelta(minutes=1),
        valid_until=now + timedelta(minutes=30),
        allow_all_models=True,
        allowed_models=(),
        allow_all_endpoints=True,
        allowed_endpoints=(),
        allowed_providers=None,
        cost_limit_eur=None,
        token_limit_total=None,
        request_limit_total=None,
        rate_limit_policy={},
    )


def _route() -> RouteResolutionResult:
    return RouteResolutionResult(
        requested_model="classroom-cheap",
        resolved_model="gpt-4.1-mini",
        provider="openai",
        route_id=uuid.uuid4(),
        route_match_type="exact",
        route_pattern="classroom-cheap",
        priority=100,
    )


def _policy() -> ChatCompletionPolicyResult:
    return ChatCompletionPolicyResult(
        effective_body={"model": "classroom-cheap", "messages": [], "max_completion_tokens": 100},
        requested_output_tokens=100,
        effective_output_tokens=100,
        estimated_input_tokens=100,
        injected_default_output_tokens=False,
    )


def _estimate() -> ChatCostEstimate:
    return ChatCostEstimate(
        provider="openai",
        requested_model="classroom-cheap",
        resolved_model="gpt-4.1-mini",
        native_currency="EUR",
        estimated_input_tokens=100,
        estimated_output_tokens=100,
        estimated_input_cost_native=Decimal("0.100000000"),
        estimated_output_cost_native=Decimal("0.200000000"),
        estimated_total_cost_native=Decimal("0.300000000"),
        estimated_total_cost_eur=Decimal("0.300000000"),
        pricing_rule_id=None,
        fx_rate_id=None,
    )


def _service():
    key = FakeKeyRow(id=uuid.uuid4())
    reservation = FakeReservationRow(id=uuid.uuid4(), gateway_key_id=key.id)
    usage_repo = FakeUsageLedgerRepository()
    return (
        AccountingService(
            gateway_keys_repository=FakeGatewayKeysRepository(key),
            quota_reservations_repository=FakeQuotaReservationsRepository(reservation),
            usage_ledger_repository=usage_repo,
        ),
        key,
        reservation,
        usage_repo,
    )


@pytest.mark.asyncio
async def test_provider_failure_releases_reservation_and_writes_failure_ledger() -> None:
    service, key, reservation, usage_repo = _service()

    result = await service.record_provider_failure_and_release(
        reservation.id,
        _auth(key.id),
        _route(),
        _policy(),
        _estimate(),
        request_id="req_1",
        error_type="provider_http_error",
        error_code="upstream_500",
        status_code=500,
    )

    assert result.released is True
    assert result.accounting_status == "failed"
    assert reservation.status == "released"
    assert key.cost_reserved_eur == Decimal("0")
    assert key.tokens_reserved_total == 0
    assert key.requests_reserved_total == 0
    assert key.cost_used_eur == Decimal("0")
    assert key.tokens_used_total == 0
    assert key.requests_used_total == 0
    assert usage_repo.failure_calls[0]["actual_cost_eur"] == Decimal("0")
    assert usage_repo.failure_calls[0]["error_type"] == "provider_http_error"
    assert usage_repo.failure_calls[0]["error_message"] == "upstream_500"
    assert usage_repo.failure_calls[0]["usage_raw"] == {}
    assert "raw provider body with secret" not in str(usage_repo.failure_calls[0])


@pytest.mark.asyncio
async def test_provider_failure_release_is_idempotent_without_second_counter_subtract() -> None:
    service, key, reservation, usage_repo = _service()

    first = await service.record_provider_failure_and_release(
        reservation.id,
        _auth(key.id),
        _route(),
        _policy(),
        _estimate(),
        request_id="req_1",
        error_type="provider_http_error",
    )
    second = await service.record_provider_failure_and_release(
        reservation.id,
        _auth(key.id),
        _route(),
        _policy(),
        _estimate(),
        request_id="req_2",
        error_type="provider_http_error",
    )

    assert first.released is True
    assert second.released is False
    assert key.cost_reserved_eur == Decimal("0")
    assert key.tokens_reserved_total == 0
    assert key.requests_reserved_total == 0
    assert len(usage_repo.failure_calls) == 2


@pytest.mark.asyncio
async def test_provider_failure_release_raises_if_reserved_counters_would_underflow() -> None:
    service, key, reservation, usage_repo = _service()
    key.cost_reserved_eur = Decimal("0")

    with pytest.raises(QuotaCounterInvariantError) as excinfo:
        await service.record_provider_failure_and_release(
            reservation.id,
            _auth(key.id),
            _route(),
            _policy(),
            _estimate(),
            request_id="req_1",
            error_type="provider_http_error",
        )

    assert excinfo.value.param == "cost_reserved_eur"
    assert reservation.status == "pending"
    assert usage_repo.failure_calls == []
