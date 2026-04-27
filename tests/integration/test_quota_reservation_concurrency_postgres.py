"""PostgreSQL high-contention checks for hard quota reservation limits."""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from slaif_gateway.db.models import GatewayKey
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
    reason="TEST_DATABASE_URL is not set; skipping PostgreSQL quota concurrency test.",
)


def _authenticated_key(row: GatewayKey) -> AuthenticatedGatewayKey:
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


def _policy() -> ChatCompletionPolicyResult:
    return ChatCompletionPolicyResult(
        effective_body={"model": "classroom-cheap", "messages": [], "max_completion_tokens": 5},
        requested_output_tokens=5,
        effective_output_tokens=5,
        estimated_input_tokens=5,
        injected_default_output_tokens=False,
    )


def _estimate() -> ChatCostEstimate:
    return ChatCostEstimate(
        provider="openai",
        requested_model="classroom-cheap",
        resolved_model="gpt-4.1-mini",
        native_currency="EUR",
        estimated_input_tokens=5,
        estimated_output_tokens=5,
        estimated_input_cost_native=Decimal("0.010000000"),
        estimated_output_cost_native=Decimal("0"),
        estimated_total_cost_native=Decimal("0.010000000"),
        estimated_total_cost_eur=Decimal("0.010000000"),
        pricing_rule_id=None,
        fx_rate_id=None,
    )


async def _create_gateway_key(session_factory) -> AuthenticatedGatewayKey:
    async with session_factory() as session:
        owner = await OwnersRepository(session).create_owner(
            name="Quota",
            surname="Concurrency",
            email=f"quota-concurrency-{uuid.uuid4()}@example.test",
        )
        now = datetime.now(UTC)
        gateway_key = await GatewayKeysRepository(session).create_gateway_key_record(
            public_key_id=f"k_{uuid.uuid4().hex}",
            token_hash=f"hash-{uuid.uuid4().hex}",
            owner_id=owner.id,
            valid_from=now - timedelta(minutes=5),
            valid_until=now + timedelta(hours=1),
            cost_limit_eur=Decimal("100.000000000"),
            token_limit_total=10_000,
            request_limit_total=5,
            allow_all_models=True,
            allow_all_endpoints=True,
        )
        authenticated_key = _authenticated_key(gateway_key)
        await session.commit()
        return authenticated_key


async def _reserve_once(session_factory, authenticated_key: AuthenticatedGatewayKey, attempt: int):
    async with session_factory() as session:
        service = QuotaService(
            gateway_keys_repository=GatewayKeysRepository(session),
            quota_reservations_repository=QuotaReservationsRepository(session),
        )
        try:
            reservation = await service.reserve_for_chat_completion(
                authenticated_key=authenticated_key,
                route=_route(),
                policy=_policy(),
                cost_estimate=_estimate(),
                request_id=f"req-{attempt}-{uuid.uuid4()}",
            )
            await session.commit()
            return ("success", reservation.reservation_id)
        except QuotaLimitExceededError:
            await session.rollback()
            return ("quota_exceeded", None)


async def _release_once(session_factory, reservation_id: uuid.UUID) -> None:
    async with session_factory() as session:
        service = QuotaService(
            gateway_keys_repository=GatewayKeysRepository(session),
            quota_reservations_repository=QuotaReservationsRepository(session),
        )
        await service.release_reservation(reservation_id)
        await session.commit()


async def _load_gateway_key(session_factory, gateway_key_id: uuid.UUID) -> GatewayKey:
    async with session_factory() as session:
        result = await session.execute(select(GatewayKey).where(GatewayKey.id == gateway_key_id))
        gateway_key = result.scalar_one()
        await session.commit()
        return gateway_key


@pytest.mark.asyncio
async def test_postgres_high_contention_reservations_cannot_overspend(
    migrated_postgres_url: str,
) -> None:
    engine = create_async_engine(migrated_postgres_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    try:
        authenticated_key = await _create_gateway_key(session_factory)

        results = await asyncio.gather(
            *(
                _reserve_once(session_factory, authenticated_key, attempt)
                for attempt in range(20)
            )
        )

        successful_reservation_ids = [
            reservation_id
            for status, reservation_id in results
            if status == "success" and reservation_id is not None
        ]
        failure_count = sum(1 for status, _ in results if status == "quota_exceeded")

        assert len(successful_reservation_ids) == 5
        assert failure_count == 15

        gateway_key = await _load_gateway_key(session_factory, authenticated_key.gateway_key_id)
        assert gateway_key.cost_reserved_eur == Decimal("0.050000000")
        assert gateway_key.tokens_reserved_total == 50
        assert gateway_key.requests_reserved_total == 5
        assert gateway_key.cost_reserved_eur >= Decimal("0")
        assert gateway_key.tokens_reserved_total >= 0
        assert gateway_key.requests_reserved_total >= 0

        await asyncio.gather(
            *(_release_once(session_factory, reservation_id) for reservation_id in successful_reservation_ids)
        )

        gateway_key = await _load_gateway_key(session_factory, authenticated_key.gateway_key_id)
        assert gateway_key.cost_reserved_eur == Decimal("0E-9")
        assert gateway_key.tokens_reserved_total == 0
        assert gateway_key.requests_reserved_total == 0
        assert gateway_key.cost_used_eur == Decimal("0E-9")
        assert gateway_key.tokens_used_total == 0
        assert gateway_key.requests_used_total == 0
    finally:
        await engine.dispose()
