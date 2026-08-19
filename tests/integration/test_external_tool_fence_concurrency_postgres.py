"""PostgreSQL concurrency tests for the exclusive external-tool fence foundation.

Objective 014 scope: the locked ``gateway_keys`` row is the single
concurrency truth (no Redis or in-memory lock is authority). These tests
prove, against real PostgreSQL row locks with independent engines and
sessions per worker:

- distinct-request-ID races (2 workers and 16 workers) produce exactly one
  winner (fence + reservation + counters) while every loser receives the
  fixed ``external_tool_fence_active`` rejection;
- concurrent same-request-ID retries produce exactly one fence with no
  double counter increment (idempotent replays share the reservation);
- ordinary chat-completion reservations racing after a committed fence are
  all rejected and cannot bypass it.

No provider calls, no real email, and no prompt/body content is stored.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from slaif_gateway.db.models import GatewayKey
from slaif_gateway.db.repositories.keys import GatewayKeysRepository
from slaif_gateway.db.repositories.owners import OwnersRepository
from slaif_gateway.db.repositories.quota import QuotaReservationsRepository
from slaif_gateway.db.repositories.audit import AuditRepository
from slaif_gateway.db.repositories.usage import UsageLedgerRepository
from slaif_gateway.schemas.auth import AuthenticatedGatewayKey
from slaif_gateway.schemas.external_tool_fence import (
    ExternalToolFenceAcquireInput,
    ExternalToolFenceResult,
    ExternalToolFenceRouteFacts,
)
from slaif_gateway.schemas.policy import ChatCompletionPolicyResult
from slaif_gateway.schemas.pricing import ChatCostEstimate
from slaif_gateway.schemas.routing import RouteResolutionResult
from slaif_gateway.services.external_tool_fence import (
    ExternalToolFenceActiveError,
    ExternalToolFenceService,
)
from slaif_gateway.services.quota_errors import (
    ExternalToolFenceActiveError as QuotaFenceActiveError,
)
from slaif_gateway.services.quota_service import QuotaService
from slaif_gateway.utils.crypto import hmac_sha256_token

pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL is not set; skipping PostgreSQL external tool fence concurrency tests.",
)

HMAC_SECRET = "h" * 48
KEY_SECRET = "s" * 43
ENDPOINT = "/v1/chat/completions"
REQUESTED_MODEL = "classroom-cheap"
PROVIDER = "openai"
CAPABILITIES = ("provider_connector", "provider_remote_mcp")
DESTINATIONS = ("connector:demo", "remote_mcp:demo")
TTL = timedelta(minutes=15)

COST_LIMIT = Decimal("25")
TOKEN_LIMIT = 100_000
REQUEST_LIMIT = 1000

STORED_POLICY = {
    "version": 1,
    "mode": "external_tool_fenced",
    "allowed_capabilities": ["provider_connector", "provider_remote_mcp"],
    "allowed_destination_ids": ["connector:demo", "remote_mcp:demo"],
}


@dataclass(frozen=True)
class _FencedDecision:
    allowed: bool = True
    quota_mode: str = "external_tool_fenced"
    exclusive_key_fence_required: bool = True
    single_request_overrun_accepted: bool = True
    hold_on_missing_or_ambiguous_final_cost: bool = True
    following_requests_block_after_exhaustion: bool = True


def _fence_service(session) -> ExternalToolFenceService:
    return ExternalToolFenceService(
        gateway_keys_repository=GatewayKeysRepository(session),
        quota_reservations_repository=QuotaReservationsRepository(session),
        usage_ledger_repository=UsageLedgerRepository(session),
        audit_repository=AuditRepository(session),
    )


def _route_facts(requested_model: str = REQUESTED_MODEL) -> ExternalToolFenceRouteFacts:
    return ExternalToolFenceRouteFacts(
        endpoint=ENDPOINT,
        requested_model=requested_model,
        provider=PROVIDER,
        route_id=uuid.uuid4(),
    )


def _quota_service(session) -> QuotaService:
    return QuotaService(
        gateway_keys_repository=GatewayKeysRepository(session),
        quota_reservations_repository=QuotaReservationsRepository(session),
    )


def _acquire_input(gateway_key_id: uuid.UUID, request_id: str) -> ExternalToolFenceAcquireInput:
    return ExternalToolFenceAcquireInput(
        gateway_key_id=gateway_key_id,
        request_id=request_id,
        route=_route_facts(),
        capabilities=CAPABILITIES,
        destination_ids=DESTINATIONS,
        decision=_FencedDecision(),
        now=datetime.now(UTC),
        ttl=TTL,
    )


async def _create_key(dsn: str) -> uuid.UUID:
    engine = create_async_engine(dsn, future=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        now = datetime.now(UTC)
        async with factory() as session:
            owner = await OwnersRepository(session).create_owner(
                name="FenceRace",
                surname="Integration",
                email=f"fence-race-{uuid.uuid4()}@example.test",
            )
            public_key_id = f"k_{uuid.uuid4().hex}"
            token = f"sk-slaif-{public_key_id}.{KEY_SECRET}"
            row = await GatewayKeysRepository(session).create_gateway_key_record(
                public_key_id=public_key_id,
                token_hash=hmac_sha256_token(token, HMAC_SECRET),
                owner_id=owner.id,
                valid_from=now - timedelta(minutes=5),
                valid_until=now + timedelta(hours=6),
                cost_limit_eur=COST_LIMIT,
                token_limit_total=TOKEN_LIMIT,
                request_limit_total=REQUEST_LIMIT,
                allow_all_models=True,
                allow_all_endpoints=True,
                metadata_json={"external_tool_policy": STORED_POLICY},
            )
            await session.commit()
            return row.id
    finally:
        await engine.dispose()


async def _load_key(dsn: str, gateway_key_id: uuid.UUID) -> GatewayKey:
    engine = create_async_engine(dsn, future=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            row = await GatewayKeysRepository(session).get_gateway_key_by_id(gateway_key_id)
            await session.commit()
            assert row is not None
            return row
    finally:
        await engine.dispose()


async def _load_reservation(dsn: str, reservation_id: uuid.UUID):
    engine = create_async_engine(dsn, future=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            row = await QuotaReservationsRepository(session).get_reservation_by_id(reservation_id)
            await session.commit()
            assert row is not None
            return row
    finally:
        await engine.dispose()


async def _count_reservations(dsn: str, gateway_key_id: uuid.UUID) -> int:
    engine = create_async_engine(dsn, future=True)
    try:
        async with engine.connect() as conn:
            row = (
                await conn.execute(
                    text("SELECT count(*) FROM quota_reservations WHERE gateway_key_id = :key_id"),
                    {"key_id": gateway_key_id},
                )
            ).one()
            return int(row[0])
    finally:
        await engine.dispose()


async def _acquire_worker(
    dsn: str, gateway_key_id: uuid.UUID, request_id: str
) -> tuple[str, object]:
    """One fence-acquisition attempt in its own engine/session/transaction."""
    engine = create_async_engine(dsn, future=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            try:
                result = await _fence_service(session).acquire(
                    _acquire_input(gateway_key_id, request_id)
                )
                await session.commit()
                return "acquired", result
            except ExternalToolFenceActiveError as error:
                await session.rollback()
                return "rejected", error
    finally:
        await engine.dispose()


async def _ordinary_reserve_worker(
    dsn: str, gateway_key_id: uuid.UUID, request_id: str
) -> tuple[str, object]:
    """One ordinary chat-completion reservation attempt in its own engine/session."""
    engine = create_async_engine(dsn, future=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(UTC)
    authenticated_key = AuthenticatedGatewayKey(
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
    route = RouteResolutionResult(
        requested_model=REQUESTED_MODEL,
        resolved_model="gpt-4.1-mini",
        provider=PROVIDER,
        route_id=uuid.uuid4(),
        route_match_type="exact",
        route_pattern=REQUESTED_MODEL,
        priority=100,
    )
    policy = ChatCompletionPolicyResult(
        effective_body={"model": REQUESTED_MODEL, "messages": [], "max_completion_tokens": 40},
        requested_output_tokens=40,
        effective_output_tokens=40,
        estimated_input_tokens=30,
        injected_default_output_tokens=False,
    )
    cost_estimate = ChatCostEstimate(
        provider=PROVIDER,
        requested_model=REQUESTED_MODEL,
        resolved_model="gpt-4.1-mini",
        native_currency="EUR",
        estimated_input_tokens=30,
        estimated_output_tokens=40,
        estimated_input_cost_native=Decimal("0.001"),
        estimated_output_cost_native=Decimal("0.002"),
        estimated_total_cost_native=Decimal("0.123"),
        estimated_total_cost_eur=Decimal("0.123"),
        pricing_rule_id=None,
        fx_rate_id=None,
    )
    try:
        async with factory() as session:
            try:
                result = await _quota_service(session).reserve_for_chat_completion(
                    authenticated_key=authenticated_key,
                    route=route,
                    policy=policy,
                    cost_estimate=cost_estimate,
                    request_id=request_id,
                    now=now,
                )
                await session.commit()
                return "reserved", result
            except QuotaFenceActiveError as error:
                await session.rollback()
                return "rejected", error
    finally:
        await engine.dispose()


def _assert_single_fence_state(
    key: GatewayKey,
    *,
    winner_request_id: str,
    reservation: object,
) -> None:
    assert key.external_tool_fence_state == "active"
    assert key.external_tool_fence_request_id == winner_request_id
    assert key.external_tool_fence_reservation_id == reservation.id
    assert key.cost_reserved_eur == COST_LIMIT
    assert key.tokens_reserved_total == TOKEN_LIMIT
    assert key.requests_reserved_total == 1
    assert reservation.quota_mode == "external_tool_fenced"
    assert reservation.request_id == winner_request_id
    assert reservation.reserved_cost_eur == COST_LIMIT
    assert reservation.reserved_tokens == TOKEN_LIMIT
    assert reservation.reserved_requests == 1
    assert reservation.status == "pending"


@pytest.mark.asyncio
async def test_distinct_request_id_race_two_workers_single_winner(
    migrated_postgres_url: str,
) -> None:
    dsn = migrated_postgres_url
    key_id = await _create_key(dsn)
    request_ids = [f"req-race2-{uuid.uuid4()}" for _ in range(2)]
    outcomes = await asyncio.gather(
        *(_acquire_worker(dsn, key_id, request_id) for request_id in request_ids)
    )
    acquired = [r for kind, r in outcomes if kind == "acquired"]
    rejected = [r for kind, r in outcomes if kind == "rejected"]
    assert len(acquired) == 1, f"expected exactly one winner, got {len(acquired)}"
    assert len(rejected) == 1
    assert all(isinstance(r, ExternalToolFenceActiveError) for r in rejected)
    assert all(r.error_code == "external_tool_fence_active" for r in rejected)

    winner: ExternalToolFenceResult = acquired[0]
    assert winner.idempotent is False
    reservation = await _load_reservation(dsn, winner.reservation_id)
    _assert_single_fence_state(
        await _load_key(dsn, key_id),
        winner_request_id=winner.request_id,
        reservation=reservation,
    )
    assert await _count_reservations(dsn, key_id) == 1


@pytest.mark.asyncio
async def test_distinct_request_id_race_sixteen_workers_single_winner(
    migrated_postgres_url: str,
) -> None:
    dsn = migrated_postgres_url
    key_id = await _create_key(dsn)
    request_ids = [f"req-race16-{uuid.uuid4()}" for _ in range(16)]
    outcomes = await asyncio.gather(
        *(_acquire_worker(dsn, key_id, request_id) for request_id in request_ids)
    )
    acquired = [r for kind, r in outcomes if kind == "acquired"]
    rejected = [r for kind, r in outcomes if kind == "rejected"]
    assert len(acquired) == 1, f"expected exactly one winner, got {len(acquired)}"
    assert len(rejected) == 15
    assert all(isinstance(r, ExternalToolFenceActiveError) for r in rejected)
    assert all(r.error_code == "external_tool_fence_active" for r in rejected)

    winner: ExternalToolFenceResult = acquired[0]
    assert winner.idempotent is False
    reservation = await _load_reservation(dsn, winner.reservation_id)
    _assert_single_fence_state(
        await _load_key(dsn, key_id),
        winner_request_id=winner.request_id,
        reservation=reservation,
    )
    assert await _count_reservations(dsn, key_id) == 1


@pytest.mark.asyncio
async def test_same_request_id_concurrent_retries_create_single_fence(
    migrated_postgres_url: str,
) -> None:
    dsn = migrated_postgres_url
    key_id = await _create_key(dsn)
    request_id = f"req-same-{uuid.uuid4()}"
    outcomes = await asyncio.gather(*(_acquire_worker(dsn, key_id, request_id) for _ in range(8)))
    assert all(kind == "acquired" for kind, _ in outcomes)
    results: list[ExternalToolFenceResult] = [r for _, r in outcomes]
    assert all(r.reservation_id == results[0].reservation_id for r in results)
    idempotent_count = sum(1 for r in results if r.idempotent)
    assert idempotent_count == 7, (
        f"expected exactly one fresh acquisition, got {8 - idempotent_count}"
    )
    assert all(r.request_id == request_id for r in results)

    reservation = await _load_reservation(dsn, results[0].reservation_id)
    _assert_single_fence_state(
        await _load_key(dsn, key_id),
        winner_request_id=request_id,
        reservation=reservation,
    )
    assert await _count_reservations(dsn, key_id) == 1


@pytest.mark.asyncio
async def test_ordinary_reservations_cannot_bypass_active_fence(migrated_postgres_url: str) -> None:
    dsn = migrated_postgres_url
    key_id = await _create_key(dsn)

    engine = create_async_engine(dsn, future=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            acquired = await _fence_service(session).acquire(
                _acquire_input(key_id, f"req-fence-{uuid.uuid4()}")
            )
            await session.commit()
        fence_request_id = acquired.request_id
        fence_reservation_id = acquired.reservation_id
    finally:
        await engine.dispose()

    request_ids = [f"req-ordinary-{uuid.uuid4()}" for _ in range(8)]
    outcomes = await asyncio.gather(
        *(_ordinary_reserve_worker(dsn, key_id, request_id) for request_id in request_ids)
    )
    assert all(kind == "rejected" for kind, _ in outcomes), (
        f"ordinary reservations must not bypass an active fence: {outcomes}"
    )
    assert all(isinstance(r, QuotaFenceActiveError) for _, r in outcomes)

    key = await _load_key(dsn, key_id)
    reservation = await _load_reservation(dsn, fence_reservation_id)
    assert key.external_tool_fence_state == "active"
    assert key.external_tool_fence_request_id == fence_request_id
    assert key.cost_reserved_eur == COST_LIMIT
    assert key.tokens_reserved_total == TOKEN_LIMIT
    assert key.requests_reserved_total == 1
    assert reservation.status == "pending"
    assert await _count_reservations(dsn, key_id) == 1
