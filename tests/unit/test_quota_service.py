from __future__ import annotations

import inspect
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from slaif_gateway.schemas.auth import AuthenticatedGatewayKey
from slaif_gateway.schemas.policy import ChatCompletionPolicyResult
from slaif_gateway.schemas.pricing import ChatCostEstimate
from slaif_gateway.schemas.routing import RouteResolutionResult
from slaif_gateway.services.quota_errors import InvalidQuotaEstimateError, QuotaLimitExceededError
from slaif_gateway.services.quota_service import QuotaService


@dataclass
class FakeGatewayKeyRow:
    id: uuid.UUID
    status: str = "active"
    valid_from: datetime = datetime(2026, 1, 1, tzinfo=UTC)
    valid_until: datetime = datetime(2027, 1, 1, tzinfo=UTC)
    cost_limit_eur: Decimal | None = Decimal("10")
    token_limit_total: int | None = 1000
    request_limit_total: int | None = 10
    cost_used_eur: Decimal = Decimal("1")
    cost_reserved_eur: Decimal = Decimal("2")
    tokens_used_total: int = 100
    tokens_reserved_total: int = 200
    requests_used_total: int = 1
    requests_reserved_total: int = 2


@dataclass
class FakeReservationRow:
    id: uuid.UUID
    gateway_key_id: uuid.UUID
    request_id: str
    endpoint: str
    requested_model: str | None
    reserved_cost_eur: Decimal
    reserved_tokens: int
    reserved_requests: int
    status: str
    expires_at: datetime
    released_at: datetime | None = None


class FakeGatewayKeysRepository:
    def __init__(self, gateway_key: FakeGatewayKeyRow | None) -> None:
        self.gateway_key = gateway_key
        self.lock_calls: list[uuid.UUID] = []
        self.commits = 0

    async def get_gateway_key_by_id_for_quota_update(self, gateway_key_id):
        self.lock_calls.append(gateway_key_id)
        return self.gateway_key

    async def add_reserved_counters(
        self,
        gateway_key,
        *,
        cost_reserved_eur,
        tokens_reserved_total,
        requests_reserved_total,
    ):
        gateway_key.cost_reserved_eur += cost_reserved_eur
        gateway_key.tokens_reserved_total += tokens_reserved_total
        gateway_key.requests_reserved_total += requests_reserved_total
        return gateway_key

    async def subtract_reserved_counters(
        self,
        gateway_key,
        *,
        cost_reserved_eur,
        tokens_reserved_total,
        requests_reserved_total,
    ):
        gateway_key.cost_reserved_eur = max(Decimal("0"), gateway_key.cost_reserved_eur - cost_reserved_eur)
        gateway_key.tokens_reserved_total = max(0, gateway_key.tokens_reserved_total - tokens_reserved_total)
        gateway_key.requests_reserved_total = max(0, gateway_key.requests_reserved_total - requests_reserved_total)
        return gateway_key


class FakeQuotaReservationsRepository:
    def __init__(self) -> None:
        self.rows: dict[uuid.UUID, FakeReservationRow] = {}
        self.create_calls = 0
        self.release_calls = 0
        self.commits = 0

    async def create_reservation(self, **kwargs):
        self.create_calls += 1
        row = FakeReservationRow(id=uuid.uuid4(), **kwargs)
        self.rows[row.id] = row
        return row

    async def get_reservation_by_id_for_update(self, reservation_id):
        return self.rows.get(reservation_id)

    async def mark_pending_reservation_released(self, reservation, *, released_at):
        self.release_calls += 1
        reservation.status = "released"
        reservation.released_at = released_at
        return reservation


def _service(
    gateway_key: FakeGatewayKeyRow,
) -> tuple[QuotaService, FakeGatewayKeysRepository, FakeQuotaReservationsRepository]:
    key_repo = FakeGatewayKeysRepository(gateway_key)
    quota_repo = FakeQuotaReservationsRepository()
    return (
        QuotaService(
            gateway_keys_repository=key_repo,
            quota_reservations_repository=quota_repo,
        ),
        key_repo,
        quota_repo,
    )


def _authenticated_key(gateway_key_id: uuid.UUID) -> AuthenticatedGatewayKey:
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


def _policy(input_tokens: int = 30, output_tokens: int = 40) -> ChatCompletionPolicyResult:
    return ChatCompletionPolicyResult(
        effective_body={"model": "classroom-cheap", "messages": [], "max_completion_tokens": output_tokens},
        requested_output_tokens=output_tokens,
        effective_output_tokens=output_tokens,
        estimated_input_tokens=input_tokens,
        injected_default_output_tokens=False,
    )


def _estimate(cost: Decimal = Decimal("0.123"), input_tokens: int = 30, output_tokens: int = 40) -> ChatCostEstimate:
    return ChatCostEstimate(
        provider="openai",
        requested_model="classroom-cheap",
        resolved_model="gpt-4.1-mini",
        native_currency="EUR",
        estimated_input_tokens=input_tokens,
        estimated_output_tokens=output_tokens,
        estimated_input_cost_native=Decimal("0.001"),
        estimated_output_cost_native=Decimal("0.002"),
        estimated_total_cost_native=cost,
        estimated_total_cost_eur=cost,
        pricing_rule_id=None,
        fx_rate_id=None,
    )


@pytest.mark.asyncio
async def test_successful_reservation_creates_pending_row_and_updates_reserved_counters() -> None:
    key = FakeGatewayKeyRow(id=uuid.uuid4())
    service, key_repo, quota_repo = _service(key)

    result = await service.reserve_for_chat_completion(
        authenticated_key=_authenticated_key(key.id),
        route=_route(),
        policy=_policy(),
        cost_estimate=_estimate(),
        request_id="req_1",
        now=datetime(2026, 4, 25, tzinfo=UTC),
    )

    assert result.status == "pending"
    assert result.reserved_cost_eur == Decimal("0.123")
    assert result.reserved_tokens == 70
    assert isinstance(result.reserved_cost_eur, Decimal)
    assert key.cost_reserved_eur == Decimal("2.123")
    assert key.tokens_reserved_total == 270
    assert key.requests_reserved_total == 3
    assert quota_repo.create_calls == 1
    assert key_repo.lock_calls == [key.id]
    assert key_repo.commits == 0
    assert quota_repo.commits == 0


@pytest.mark.asyncio
async def test_release_subtracts_reserved_counters_and_marks_released() -> None:
    key = FakeGatewayKeyRow(id=uuid.uuid4())
    service, _, _ = _service(key)
    reservation = await service.reserve_for_chat_completion(
        authenticated_key=_authenticated_key(key.id),
        route=_route(),
        policy=_policy(),
        cost_estimate=_estimate(),
        request_id="req_1",
        now=datetime(2026, 4, 25, tzinfo=UTC),
    )

    result = await service.release_reservation(
        reservation.reservation_id,
        now=datetime(2026, 4, 25, 0, 1, tzinfo=UTC),
    )

    assert result.status == "released"
    assert key.cost_reserved_eur == Decimal("2")
    assert key.tokens_reserved_total == 200
    assert key.requests_reserved_total == 2


@pytest.mark.asyncio
async def test_release_is_idempotent_after_first_release() -> None:
    key = FakeGatewayKeyRow(id=uuid.uuid4())
    service, _, quota_repo = _service(key)
    reservation = await service.reserve_for_chat_completion(
        authenticated_key=_authenticated_key(key.id),
        route=_route(),
        policy=_policy(),
        cost_estimate=_estimate(),
        request_id="req_1",
        now=datetime(2026, 4, 25, tzinfo=UTC),
    )

    await service.release_reservation(reservation.reservation_id)
    second = await service.release_reservation(reservation.reservation_id)

    assert second.status == "released"
    assert quota_repo.release_calls == 1
    assert key.cost_reserved_eur == Decimal("2")


@pytest.mark.asyncio
async def test_cost_limit_exceeded_raises_quota_limit_error() -> None:
    key = FakeGatewayKeyRow(id=uuid.uuid4(), cost_limit_eur=Decimal("3.122"))
    service, _, quota_repo = _service(key)

    with pytest.raises(QuotaLimitExceededError) as excinfo:
        await service.reserve_for_chat_completion(
            authenticated_key=_authenticated_key(key.id),
            route=_route(),
            policy=_policy(),
            cost_estimate=_estimate(),
            request_id="req_1",
        )

    assert excinfo.value.param == "cost_limit_eur"
    assert quota_repo.create_calls == 0


@pytest.mark.asyncio
async def test_token_limit_exceeded_raises_quota_limit_error() -> None:
    key = FakeGatewayKeyRow(id=uuid.uuid4(), token_limit_total=369)
    service, _, quota_repo = _service(key)

    with pytest.raises(QuotaLimitExceededError) as excinfo:
        await service.reserve_for_chat_completion(
            authenticated_key=_authenticated_key(key.id),
            route=_route(),
            policy=_policy(),
            cost_estimate=_estimate(),
            request_id="req_1",
        )

    assert excinfo.value.param == "token_limit_total"
    assert quota_repo.create_calls == 0


@pytest.mark.asyncio
async def test_request_limit_exceeded_raises_quota_limit_error() -> None:
    key = FakeGatewayKeyRow(id=uuid.uuid4(), request_limit_total=3)
    service, _, quota_repo = _service(key)

    with pytest.raises(QuotaLimitExceededError) as excinfo:
        await service.reserve_for_chat_completion(
            authenticated_key=_authenticated_key(key.id),
            route=_route(),
            policy=_policy(),
            cost_estimate=_estimate(),
            request_id="req_1",
        )

    assert excinfo.value.param == "request_limit_total"
    assert quota_repo.create_calls == 0


@pytest.mark.asyncio
async def test_none_limits_are_unlimited() -> None:
    key = FakeGatewayKeyRow(
        id=uuid.uuid4(),
        cost_limit_eur=None,
        token_limit_total=None,
        request_limit_total=None,
    )
    service, _, _ = _service(key)

    result = await service.reserve_for_chat_completion(
        authenticated_key=_authenticated_key(key.id),
        route=_route(),
        policy=_policy(input_tokens=100_000, output_tokens=100_000),
        cost_estimate=_estimate(cost=Decimal("999999.123"), input_tokens=100_000, output_tokens=100_000),
        request_id="req_1",
    )

    assert result.status == "pending"


@pytest.mark.asyncio
async def test_negative_cost_or_tokens_raise_invalid_estimate() -> None:
    key = FakeGatewayKeyRow(id=uuid.uuid4())
    service, _, _ = _service(key)

    with pytest.raises(InvalidQuotaEstimateError):
        await service.reserve_for_chat_completion(
            authenticated_key=_authenticated_key(key.id),
            route=_route(),
            policy=_policy(),
            cost_estimate=_estimate(cost=Decimal("-0.01")),
            request_id="req_1",
        )

    with pytest.raises(InvalidQuotaEstimateError):
        await service.reserve_for_chat_completion(
            authenticated_key=_authenticated_key(key.id),
            route=_route(),
            policy=_policy(input_tokens=-1),
            cost_estimate=_estimate(input_tokens=-1),
            request_id="req_2",
        )


def test_quota_service_safety_imports() -> None:
    import slaif_gateway.services.quota_service as quota_module

    source = inspect.getsource(quota_module).lower()
    for disallowed in (
        "openai",
        "openrouter",
        "httpx",
        "smtp",
        "aiosmtplib",
        "celery",
        "redis",
        "usageledger",
        "usage_ledger",
        "fastapi",
    ):
        assert disallowed not in source


def test_quota_service_uses_locking_repository_methods_for_atomicity() -> None:
    import slaif_gateway.db.repositories.keys as keys_module
    import slaif_gateway.db.repositories.quota as quota_module

    assert "with_for_update()" in inspect.getsource(
        keys_module.GatewayKeysRepository.get_gateway_key_by_id_for_quota_update
    )
    assert "with_for_update()" in inspect.getsource(
        quota_module.QuotaReservationsRepository.get_reservation_by_id_for_update
    )
    service_source = inspect.getsource(QuotaService)
    assert "get_gateway_key_by_id_for_quota_update" in service_source
    assert "get_reservation_by_id_for_update" in service_source
