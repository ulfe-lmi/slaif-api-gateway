from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from slaif_gateway.db.repositories.keys import GatewayKeysRepository
from slaif_gateway.schemas.auth import AuthenticatedGatewayKey
from slaif_gateway.schemas.policy import ChatCompletionPolicyResult
from slaif_gateway.schemas.pricing import ChatCostEstimate
from slaif_gateway.schemas.providers import ProviderResponse, ProviderUsage
from slaif_gateway.schemas.routing import RouteResolutionResult
from slaif_gateway.services.accounting import AccountingService
from slaif_gateway.services.accounting_errors import (
    ActualCostExceededReservationError,
    InvalidUsageError,
    ReservationAlreadyFinalizedError,
)
from slaif_gateway.services.quota_errors import InvalidQuotaEstimateError, QuotaCounterInvariantError
from slaif_gateway.services.quota_service import QuotaService


class FakeSession:
    def __init__(self) -> None:
        self.flush_count = 0

    async def flush(self) -> None:
        self.flush_count += 1


@dataclass
class FakeGatewayKeyRow:
    id: uuid.UUID
    status: str = "active"
    valid_from: datetime = datetime(2026, 1, 1, tzinfo=UTC)
    valid_until: datetime = datetime(2027, 1, 1, tzinfo=UTC)
    cost_limit_eur: Decimal | None = Decimal("1000000")
    token_limit_total: int | None = 1_000_000
    request_limit_total: int | None = 10_000
    cost_used_eur: Decimal = Decimal("0")
    cost_reserved_eur: Decimal = Decimal("0")
    tokens_used_total: int = 0
    tokens_reserved_total: int = 0
    requests_used_total: int = 0
    requests_reserved_total: int = 0
    last_used_at: datetime | None = None


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
    created_at: datetime = datetime(2026, 5, 4, tzinfo=UTC)
    finalized_at: datetime | None = None
    released_at: datetime | None = None


class FakeGatewayKeysRepository:
    def __init__(self, gateway_key: FakeGatewayKeyRow) -> None:
        self.gateway_key = gateway_key
        self.lock_calls: list[uuid.UUID] = []

    async def get_gateway_key_by_id_for_quota_update(self, gateway_key_id: uuid.UUID):
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

    async def finalize_reserved_counters(
        self,
        gateway_key,
        *,
        reserved_cost_eur,
        reserved_tokens_total,
        reserved_requests_total,
        actual_cost_eur,
        actual_tokens_total,
        actual_requests_total,
        last_used_at,
    ):
        await self.subtract_reserved_counters(
            gateway_key,
            cost_reserved_eur=reserved_cost_eur,
            tokens_reserved_total=reserved_tokens_total,
            requests_reserved_total=reserved_requests_total,
        )
        gateway_key.cost_used_eur += actual_cost_eur
        gateway_key.tokens_used_total += actual_tokens_total
        gateway_key.requests_used_total += actual_requests_total
        gateway_key.last_used_at = last_used_at
        return gateway_key


class FakeQuotaReservationsRepository:
    def __init__(self) -> None:
        self.rows: dict[uuid.UUID, FakeReservationRow] = {}

    async def create_reservation(self, **kwargs):
        row = FakeReservationRow(id=uuid.uuid4(), **kwargs)
        self.rows[row.id] = row
        return row

    async def get_reservation_by_id_for_update(self, reservation_id):
        return self.rows.get(reservation_id)

    async def get_reservation_by_id(self, reservation_id):
        return self.rows.get(reservation_id)

    async def mark_pending_reservation_released(self, reservation, *, released_at):
        reservation.status = "released"
        reservation.released_at = released_at
        return reservation

    async def mark_pending_reservation_finalized(self, reservation, *, finalized_at):
        reservation.status = "finalized"
        reservation.finalized_at = finalized_at
        return reservation


class FakeUsageLedgerRepository:
    def __init__(self) -> None:
        self.rows: dict[uuid.UUID, SimpleNamespace] = {}
        self.failure_calls = 0

    async def create_success_record(self, **kwargs):
        row = SimpleNamespace(id=uuid.uuid4(), success=True, accounting_status="finalized", **kwargs)
        self.rows[row.id] = row
        return row

    async def create_failure_record(self, **kwargs):
        self.failure_calls += 1
        row = SimpleNamespace(id=uuid.uuid4(), success=False, accounting_status="failed", **kwargs)
        self.rows[row.id] = row
        return row

    async def get_usage_record_by_request_id(self, request_id):
        return next((row for row in self.rows.values() if row.request_id == request_id), None)

    async def get_usage_record_by_id(self, usage_id):
        return self.rows.get(usage_id)


def _decimal_cents(value: int) -> Decimal:
    return Decimal(value).scaleb(-9)


@settings(max_examples=40, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    cost_units=st.integers(min_value=0, max_value=10_000),
    token_count=st.integers(min_value=0, max_value=10_000),
    request_count=st.integers(min_value=0, max_value=10),
)
def test_reserved_counter_subtract_property_never_underflows(
    cost_units: int,
    token_count: int,
    request_count: int,
) -> None:
    async def _run() -> None:
        key = SimpleNamespace(
            cost_reserved_eur=_decimal_cents(cost_units),
            tokens_reserved_total=token_count,
            requests_reserved_total=request_count,
            cost_used_eur=Decimal("0"),
            tokens_used_total=0,
            requests_used_total=0,
            last_used_at=None,
        )
        decrement_cost = _decimal_cents(cost_units // 2)
        decrement_tokens = token_count // 2
        decrement_requests = request_count // 2

        await GatewayKeysRepository(FakeSession()).subtract_reserved_counters(
            key,  # type: ignore[arg-type]
            cost_reserved_eur=decrement_cost,
            tokens_reserved_total=decrement_tokens,
            requests_reserved_total=decrement_requests,
        )

        assert key.cost_reserved_eur >= Decimal("0")
        assert key.tokens_reserved_total >= 0
        assert key.requests_reserved_total >= 0
        assert key.cost_reserved_eur == _decimal_cents(cost_units) - decrement_cost
        assert key.tokens_reserved_total == token_count - decrement_tokens
        assert key.requests_reserved_total == request_count - decrement_requests

    asyncio.run(_run())


@settings(max_examples=40)
@given(
    cost_units=st.integers(min_value=0, max_value=10_000),
    token_count=st.integers(min_value=0, max_value=10_000),
    request_count=st.integers(min_value=0, max_value=10),
)
def test_reserved_counter_underflow_property_preserves_existing_counters(
    cost_units: int,
    token_count: int,
    request_count: int,
) -> None:
    async def _run() -> None:
        key = SimpleNamespace(
            cost_reserved_eur=_decimal_cents(cost_units),
            tokens_reserved_total=token_count,
            requests_reserved_total=request_count,
            cost_used_eur=Decimal("0"),
            tokens_used_total=0,
            requests_used_total=0,
            last_used_at=None,
        )
        before = (
            key.cost_reserved_eur,
            key.tokens_reserved_total,
            key.requests_reserved_total,
            key.cost_used_eur,
            key.tokens_used_total,
            key.requests_used_total,
        )

        with pytest.raises(QuotaCounterInvariantError):
            await GatewayKeysRepository(FakeSession()).subtract_reserved_counters(
                key,  # type: ignore[arg-type]
                cost_reserved_eur=key.cost_reserved_eur + Decimal("0.000000001"),
                tokens_reserved_total=token_count,
                requests_reserved_total=request_count,
            )

        assert (
            key.cost_reserved_eur,
            key.tokens_reserved_total,
            key.requests_reserved_total,
            key.cost_used_eur,
            key.tokens_used_total,
            key.requests_used_total,
        ) == before

    asyncio.run(_run())


@settings(max_examples=35)
@given(
    message_tokens=st.integers(min_value=0, max_value=500),
    non_message_tokens=st.integers(min_value=0, max_value=5_000),
    output_tokens=st.integers(min_value=1, max_value=2_000),
)
def test_quota_reservation_math_includes_input_output_and_non_message_estimates(
    message_tokens: int,
    non_message_tokens: int,
    output_tokens: int,
) -> None:
    async def _run() -> None:
        total_input = message_tokens + non_message_tokens
        key = FakeGatewayKeyRow(id=uuid.uuid4())
        key_repo = FakeGatewayKeysRepository(key)
        quota_repo = FakeQuotaReservationsRepository()
        service = QuotaService(
            gateway_keys_repository=key_repo,  # type: ignore[arg-type]
            quota_reservations_repository=quota_repo,  # type: ignore[arg-type]
        )

        reservation = await service.reserve_for_chat_completion(
            authenticated_key=_auth(key.id),
            route=_route(),
            policy=_policy(
                input_tokens=total_input,
                output_tokens=output_tokens,
                message_tokens=message_tokens,
                non_message_tokens=non_message_tokens,
            ),
            cost_estimate=_estimate(input_tokens=total_input, output_tokens=output_tokens),
            request_id=f"req-{uuid.uuid4()}",
            now=datetime(2026, 5, 4, tzinfo=UTC),
        )

        assert reservation.reserved_tokens == total_input + output_tokens
        assert key.tokens_reserved_total == total_input + output_tokens
        assert key.requests_reserved_total == 1
        assert isinstance(key.cost_reserved_eur, Decimal)
        assert key.cost_reserved_eur == Decimal("0.120000000")

    asyncio.run(_run())


def test_negative_quota_estimates_are_rejected_before_counter_mutation() -> None:
    async def _run() -> None:
        key = FakeGatewayKeyRow(id=uuid.uuid4())
        service = QuotaService(
            gateway_keys_repository=FakeGatewayKeysRepository(key),  # type: ignore[arg-type]
            quota_reservations_repository=FakeQuotaReservationsRepository(),  # type: ignore[arg-type]
        )

        with pytest.raises(InvalidQuotaEstimateError):
            await service.reserve_for_chat_completion(
                authenticated_key=_auth(key.id),
                route=_route(),
                policy=_policy(input_tokens=-1),
                cost_estimate=_estimate(input_tokens=0),
                request_id=f"req-{uuid.uuid4()}",
            )

        assert key.cost_reserved_eur == Decimal("0")
        assert key.tokens_reserved_total == 0
        assert key.requests_reserved_total == 0

    asyncio.run(_run())


def test_release_finalize_and_failure_paths_are_idempotent_or_fail_safe() -> None:
    async def _run() -> None:
        key = FakeGatewayKeyRow(id=uuid.uuid4())
        key_repo = FakeGatewayKeysRepository(key)
        quota_repo = FakeQuotaReservationsRepository()
        usage_repo = FakeUsageLedgerRepository()
        quota_service = QuotaService(
            gateway_keys_repository=key_repo,  # type: ignore[arg-type]
            quota_reservations_repository=quota_repo,  # type: ignore[arg-type]
        )
        accounting = AccountingService(
            gateway_keys_repository=key_repo,  # type: ignore[arg-type]
            quota_reservations_repository=quota_repo,  # type: ignore[arg-type]
            usage_ledger_repository=usage_repo,  # type: ignore[arg-type]
        )

        released = await quota_service.reserve_for_chat_completion(
            authenticated_key=_auth(key.id),
            route=_route(),
            policy=_policy(input_tokens=20, output_tokens=30),
            cost_estimate=_estimate(input_tokens=20, output_tokens=30),
            request_id="req-release",
        )
        await quota_service.release_reservation(released.reservation_id)
        await quota_service.release_reservation(released.reservation_id)
        assert key.cost_reserved_eur == Decimal("0")
        assert key.tokens_reserved_total == 0
        assert key.requests_reserved_total == 0
        assert key.cost_used_eur == Decimal("0")
        assert key.tokens_used_total == 0
        assert key.requests_used_total == 0

        finalized = await quota_service.reserve_for_chat_completion(
            authenticated_key=_auth(key.id),
            route=_route(),
            policy=_policy(input_tokens=20, output_tokens=30),
            cost_estimate=_estimate(input_tokens=20, output_tokens=30),
            request_id="req-finalize",
        )
        await accounting.finalize_successful_response(
            finalized.reservation_id,
            _auth(key.id),
            _route(),
            _policy(input_tokens=20, output_tokens=30),
            _estimate(input_tokens=20, output_tokens=30),
            _response(prompt_tokens=10, completion_tokens=15),
            request_id="req-finalize",
        )
        with pytest.raises(ReservationAlreadyFinalizedError):
            await accounting.finalize_successful_response(
                finalized.reservation_id,
                _auth(key.id),
                _route(),
                _policy(input_tokens=20, output_tokens=30),
                _estimate(input_tokens=20, output_tokens=30),
                _response(prompt_tokens=10, completion_tokens=15),
                request_id="req-finalize-again",
            )
        assert key.cost_reserved_eur == Decimal("0")
        assert key.tokens_reserved_total == 0
        assert key.requests_reserved_total == 0
        assert key.cost_used_eur == Decimal("0.0600000000")
        assert key.tokens_used_total == 25
        assert key.requests_used_total == 1

        failed = await quota_service.reserve_for_chat_completion(
            authenticated_key=_auth(key.id),
            route=_route(),
            policy=_policy(input_tokens=20, output_tokens=30),
            cost_estimate=_estimate(input_tokens=20, output_tokens=30),
            request_id="req-provider-failure",
        )
        result = await accounting.record_provider_failure_and_release(
            failed.reservation_id,
            _auth(key.id),
            _route(),
            _policy(input_tokens=20, output_tokens=30),
            _estimate(input_tokens=20, output_tokens=30),
            request_id="req-provider-failure",
            error_type="provider_error",
        )
        assert result.released is True
        assert key.cost_reserved_eur == Decimal("0")
        assert key.tokens_reserved_total == 0
        assert key.requests_reserved_total == 0
        assert key.cost_used_eur == Decimal("0.0600000000")
        assert key.tokens_used_total == 25
        assert key.requests_used_total == 1

    asyncio.run(_run())


def test_actual_usage_and_cost_invariants_reject_invalid_values() -> None:
    service = AccountingService(
        gateway_keys_repository=FakeGatewayKeysRepository(FakeGatewayKeyRow(id=uuid.uuid4())),  # type: ignore[arg-type]
        quota_reservations_repository=FakeQuotaReservationsRepository(),  # type: ignore[arg-type]
        usage_ledger_repository=FakeUsageLedgerRepository(),  # type: ignore[arg-type]
    )

    with pytest.raises(InvalidUsageError):
        service.extract_usage(_response(prompt_tokens=-1))

    usage = service.extract_usage(_response(prompt_tokens=3, completion_tokens=4))
    cost = service.compute_actual_cost(
        _response(prompt_tokens=3, completion_tokens=4),
        _route(),
        usage,
        ChatCostEstimate(
            provider="openai",
            requested_model="classroom-cheap",
            resolved_model="gpt-4.1-mini",
            native_currency="EUR",
            estimated_input_tokens=10,
            estimated_output_tokens=10,
            estimated_input_cost_native=Decimal("123456789.123456789"),
            estimated_output_cost_native=Decimal("987654321.987654321"),
            estimated_total_cost_native=Decimal("1111111111.111111110"),
            estimated_total_cost_eur=Decimal("1111111111.111111110"),
            pricing_rule_id=None,
            fx_rate_id=None,
        ),
    )

    assert isinstance(cost.actual_cost_eur, Decimal)
    assert cost.actual_cost_eur == (
        Decimal(3) * (Decimal("123456789.123456789") / Decimal(10))
        + Decimal(4) * (Decimal("987654321.987654321") / Decimal(10))
    )

    with pytest.raises(ActualCostExceededReservationError):
        # The response cost is above this reservation in finalize paths.
        from slaif_gateway.services.accounting import _validate_actual_within_reservation

        _validate_actual_within_reservation(
            actual_cost_eur=Decimal("2"),
            actual_tokens=1,
            reserved_cost_eur=Decimal("1"),
            reserved_tokens=1,
        )


def _auth(gateway_key_id: uuid.UUID) -> AuthenticatedGatewayKey:
    now = datetime.now(UTC)
    return AuthenticatedGatewayKey(
        gateway_key_id=gateway_key_id,
        owner_id=uuid.uuid4(),
        cohort_id=None,
        public_key_id="public",
        status="active",
        valid_from=now - timedelta(minutes=1),
        valid_until=now + timedelta(hours=1),
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


def _policy(
    *,
    input_tokens: int = 20,
    output_tokens: int = 30,
    message_tokens: int | None = None,
    non_message_tokens: int = 0,
) -> ChatCompletionPolicyResult:
    if message_tokens is None:
        message_tokens = input_tokens - non_message_tokens
    return ChatCompletionPolicyResult(
        effective_body={
            "model": "classroom-cheap",
            "messages": [],
            "max_completion_tokens": output_tokens,
        },
        requested_output_tokens=output_tokens,
        effective_output_tokens=output_tokens,
        estimated_input_tokens=input_tokens,
        estimated_message_input_tokens=message_tokens,
        estimated_non_message_input_tokens=non_message_tokens,
        estimated_non_message_input_bytes=non_message_tokens,
        estimated_non_message_input_fields=("tools",) if non_message_tokens else (),
        injected_default_output_tokens=False,
    )


def _estimate(*, input_tokens: int = 20, output_tokens: int = 30) -> ChatCostEstimate:
    return ChatCostEstimate(
        provider="openai",
        requested_model="classroom-cheap",
        resolved_model="gpt-4.1-mini",
        native_currency="EUR",
        estimated_input_tokens=input_tokens,
        estimated_output_tokens=output_tokens,
        estimated_input_cost_native=Decimal("0.040000000"),
        estimated_output_cost_native=Decimal("0.080000000"),
        estimated_total_cost_native=Decimal("0.120000000"),
        estimated_total_cost_eur=Decimal("0.120000000"),
        pricing_rule_id=None,
        fx_rate_id=None,
    )


def _response(*, prompt_tokens: int = 10, completion_tokens: int = 15) -> ProviderResponse:
    return ProviderResponse(
        provider="openai",
        upstream_model="gpt-4.1-mini",
        status_code=200,
        json_body={"id": "chatcmpl_invariant"},
        upstream_request_id="upstream_invariant",
        usage=ProviderUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            other_usage={
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "prompt": "sensitive prompt",
                "completion": "sensitive completion",
            },
        ),
    )
