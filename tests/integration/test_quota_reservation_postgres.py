"""Optional PostgreSQL checks for quota reservation counter atomicity."""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from slaif_gateway.db.repositories.keys import GatewayKeysRepository
from slaif_gateway.db.repositories.owners import OwnersRepository
from slaif_gateway.db.repositories.quota import QuotaReservationsRepository
from slaif_gateway.schemas.auth import AuthenticatedGatewayKey
from slaif_gateway.schemas.policy import ChatCompletionPolicyResult
from slaif_gateway.schemas.pricing import ChatCostEstimate
from slaif_gateway.schemas.routing import RouteResolutionResult
from slaif_gateway.services.quota_errors import QuotaLimitExceededError
from slaif_gateway.services.quota_service import QuotaService

pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL is not set; skipping optional PostgreSQL quota tests.",
)


async def _create_gateway_key(async_test_session: AsyncSession):
    owner = await OwnersRepository(async_test_session).create_owner(
        name="Quota",
        surname="Tester",
        email=f"quota-{uuid.uuid4()}@example.test",
    )
    now = datetime.now(UTC)
    return await GatewayKeysRepository(async_test_session).create_gateway_key_record(
        public_key_id=f"k_{uuid.uuid4().hex}",
        token_hash=f"hash-{uuid.uuid4().hex}",
        owner_id=owner.id,
        valid_from=now - timedelta(minutes=5),
        valid_until=now + timedelta(hours=1),
        cost_limit_eur=Decimal("1.000000000"),
        token_limit_total=200,
        request_limit_total=5,
        allow_all_models=True,
        allow_all_endpoints=True,
    )


def _authenticated_key(row) -> AuthenticatedGatewayKey:
    return AuthenticatedGatewayKey(
        gateway_key_id=row.id,
        owner_id=row.owner_id,
        cohort_id=row.cohort_id,
        public_key_id=row.public_key_id,
        status=row.status,
        valid_from=row.valid_from,
        valid_until=row.valid_until,
        allow_all_models=row.allow_all_models,
        allowed_models=tuple(row.allowed_models),
        allow_all_endpoints=row.allow_all_endpoints,
        allowed_endpoints=tuple(row.allowed_endpoints),
        allowed_providers=None,
        cost_limit_eur=row.cost_limit_eur,
        token_limit_total=row.token_limit_total,
        request_limit_total=row.request_limit_total,
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


def _policy(input_tokens: int = 20, output_tokens: int = 30) -> ChatCompletionPolicyResult:
    return ChatCompletionPolicyResult(
        effective_body={"model": "classroom-cheap", "messages": [], "max_completion_tokens": output_tokens},
        requested_output_tokens=output_tokens,
        effective_output_tokens=output_tokens,
        estimated_input_tokens=input_tokens,
        injected_default_output_tokens=False,
    )


def _estimate(cost: Decimal = Decimal("0.100000000"), input_tokens: int = 20, output_tokens: int = 30):
    return ChatCostEstimate(
        provider="openai",
        requested_model="classroom-cheap",
        resolved_model="gpt-4.1-mini",
        native_currency="EUR",
        estimated_input_tokens=input_tokens,
        estimated_output_tokens=output_tokens,
        estimated_input_cost_native=cost,
        estimated_output_cost_native=Decimal("0"),
        estimated_total_cost_native=cost,
        estimated_total_cost_eur=cost,
        pricing_rule_id=None,
        fx_rate_id=None,
    )


def _service(async_test_session: AsyncSession) -> QuotaService:
    return QuotaService(
        gateway_keys_repository=GatewayKeysRepository(async_test_session),
        quota_reservations_repository=QuotaReservationsRepository(async_test_session),
    )


@pytest.mark.asyncio
async def test_postgres_reserve_and_release_restore_reserved_counters(
    async_test_session: AsyncSession,
) -> None:
    gateway_key = await _create_gateway_key(async_test_session)
    service = _service(async_test_session)

    reservation = await service.reserve_for_chat_completion(
        authenticated_key=_authenticated_key(gateway_key),
        route=_route(),
        policy=_policy(),
        cost_estimate=_estimate(),
        request_id=f"req-{uuid.uuid4()}",
    )
    await async_test_session.refresh(gateway_key)

    assert gateway_key.cost_reserved_eur == Decimal("0.100000000")
    assert gateway_key.tokens_reserved_total == 50
    assert gateway_key.requests_reserved_total == 1

    released = await service.release_reservation(reservation.reservation_id)
    await async_test_session.refresh(gateway_key)

    assert released.status == "released"
    assert gateway_key.cost_reserved_eur == Decimal("0E-9")
    assert gateway_key.tokens_reserved_total == 0
    assert gateway_key.requests_reserved_total == 0


@pytest.mark.asyncio
async def test_postgres_reserve_beyond_cost_limit_fails(async_test_session: AsyncSession) -> None:
    gateway_key = await _create_gateway_key(async_test_session)

    with pytest.raises(QuotaLimitExceededError):
        await _service(async_test_session).reserve_for_chat_completion(
            authenticated_key=_authenticated_key(gateway_key),
            route=_route(),
            policy=_policy(),
            cost_estimate=_estimate(cost=Decimal("1.000000001")),
            request_id=f"req-{uuid.uuid4()}",
        )


@pytest.mark.asyncio
async def test_postgres_reserve_beyond_token_limit_fails(async_test_session: AsyncSession) -> None:
    gateway_key = await _create_gateway_key(async_test_session)

    with pytest.raises(QuotaLimitExceededError):
        await _service(async_test_session).reserve_for_chat_completion(
            authenticated_key=_authenticated_key(gateway_key),
            route=_route(),
            policy=_policy(input_tokens=101, output_tokens=100),
            cost_estimate=_estimate(input_tokens=101, output_tokens=100),
            request_id=f"req-{uuid.uuid4()}",
        )

