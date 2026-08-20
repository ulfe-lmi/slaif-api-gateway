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
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from slaif_gateway.db.models import GatewayKey, ModelRoute
from slaif_gateway.db.repositories.keys import GatewayKeysRepository
from slaif_gateway.db.repositories.owners import OwnersRepository
from slaif_gateway.db.repositories.quota import QuotaReservationsRepository
from slaif_gateway.db.repositories.audit import AuditRepository
from slaif_gateway.db.repositories.usage import UsageLedgerRepository
from slaif_gateway.schemas.auth import AuthenticatedGatewayKey
from slaif_gateway.schemas.external_tool_fence import (
    ExternalToolFenceAcquireInput,
    ExternalToolFenceResolveInput,
    ExternalToolFenceResult,
    ExternalToolFenceRouteFacts,
)
from slaif_gateway.schemas.policy import ChatCompletionPolicyResult
from slaif_gateway.schemas.pricing import ChatCostEstimate
from slaif_gateway.schemas.routing import RouteResolutionResult
from slaif_gateway.services.external_tool_fence import (
    ExternalToolFenceActiveError,
    ExternalToolFenceInvariantError,
    ExternalToolFenceOccupiedError,
    ExternalToolFenceService,
)
from slaif_gateway.services.external_tool_policy_contract import ExternalToolAdmissionDecision
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
    "max_provider_tool_calls_per_request": 2,
    "single_request_overrun_acknowledged": True,
}


def _decision() -> ExternalToolAdmissionDecision:
    """Build the exact positive objective-012 fenced admission decision."""
    return ExternalToolAdmissionDecision(
        allowed=True,
        quota_mode="external_tool_fenced",
        effective_tool_call_cap=2,
        reason_code="external_tool_fenced_allowed",
        exclusive_key_fence_required=True,
        single_request_overrun_accepted=True,
        hold_on_missing_or_ambiguous_final_cost=True,
        following_requests_block_after_exhaustion=True,
    )


def _fence_service(session) -> ExternalToolFenceService:
    return ExternalToolFenceService(
        gateway_keys_repository=GatewayKeysRepository(session),
        quota_reservations_repository=QuotaReservationsRepository(session),
        usage_ledger_repository=UsageLedgerRepository(session),
        audit_repository=AuditRepository(session),
    )


def _route_facts(
    route_id: uuid.UUID,
    *,
    requested_model: str = REQUESTED_MODEL,
    provider: str = PROVIDER,
) -> ExternalToolFenceRouteFacts:
    return ExternalToolFenceRouteFacts(
        endpoint=ENDPOINT,
        requested_model=requested_model,
        provider=provider,
        route_id=route_id,
    )


async def _create_model_route(dsn: str) -> uuid.UUID:
    """Insert a real model route so fence reservations satisfy the 0015 FK."""
    engine = create_async_engine(dsn, future=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            route = ModelRoute(
                requested_model=REQUESTED_MODEL,
                match_type="exact",
                endpoint=ENDPOINT,
                provider=PROVIDER,
                upstream_model="gpt-4.1-mini",
            )
            session.add(route)
            await session.commit()
            return route.id
    finally:
        await engine.dispose()


def _quota_service(session) -> QuotaService:
    return QuotaService(
        gateway_keys_repository=GatewayKeysRepository(session),
        quota_reservations_repository=QuotaReservationsRepository(session),
    )


def _acquire_input(
    gateway_key_id: uuid.UUID,
    request_id: str,
    route_id: uuid.UUID,
    *,
    requested_model: str = REQUESTED_MODEL,
    provider: str = PROVIDER,
) -> ExternalToolFenceAcquireInput:
    return ExternalToolFenceAcquireInput(
        gateway_key_id=gateway_key_id,
        request_id=request_id,
        route=_route_facts(route_id, requested_model=requested_model, provider=provider),
        capabilities=CAPABILITIES,
        destination_ids=DESTINATIONS,
        decision=_decision(),
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
    dsn: str,
    gateway_key_id: uuid.UUID,
    request_id: str,
    route_id: uuid.UUID,
) -> tuple[str, object]:
    """One fence-acquisition attempt in its own engine/session/transaction."""
    engine = create_async_engine(dsn, future=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            try:
                result = await _fence_service(session).acquire(
                    _acquire_input(gateway_key_id, request_id, route_id)
                )
                await session.commit()
                return "acquired", result
            except ExternalToolFenceActiveError as error:
                await session.rollback()
                return "rejected", error
    finally:
        await engine.dispose()


def _ordinary_authenticated_key(gateway_key_id: uuid.UUID) -> AuthenticatedGatewayKey:
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


def _ordinary_route() -> RouteResolutionResult:
    return RouteResolutionResult(
        requested_model=REQUESTED_MODEL,
        resolved_model="gpt-4.1-mini",
        provider=PROVIDER,
        route_id=uuid.uuid4(),
        route_match_type="exact",
        route_pattern=REQUESTED_MODEL,
        priority=100,
    )


def _ordinary_policy() -> ChatCompletionPolicyResult:
    return ChatCompletionPolicyResult(
        effective_body={"model": REQUESTED_MODEL, "messages": [], "max_completion_tokens": 40},
        requested_output_tokens=40,
        effective_output_tokens=40,
        estimated_input_tokens=30,
        injected_default_output_tokens=False,
    )


def _ordinary_cost_estimate() -> ChatCostEstimate:
    return ChatCostEstimate(
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


async def _ordinary_reserve_hold(
    session_factory, gateway_key_id: uuid.UUID, request_id: str
) -> tuple[str, object, object]:
    """Ordinary reservation in a caller-owned session.

    The session is left open (uncommitted) on success so the caller can hold
    the locked key row; on the fence-rejection path it is rolled back and
    closed here.
    """
    now = datetime.now(UTC)
    session = session_factory()
    try:
        result = await _quota_service(session).reserve_for_chat_completion(
            authenticated_key=_ordinary_authenticated_key(gateway_key_id),
            route=_ordinary_route(),
            policy=_ordinary_policy(),
            cost_estimate=_ordinary_cost_estimate(),
            request_id=request_id,
            now=now,
        )
    except QuotaFenceActiveError as error:
        await session.rollback()
        await session.close()
        return "rejected", error, session
    return "acquired", result, session


async def _ordinary_reserve_worker(
    dsn: str, gateway_key_id: uuid.UUID, request_id: str
) -> tuple[str, object]:
    """One ordinary chat-completion reservation attempt in its own engine/session."""
    engine = create_async_engine(dsn, future=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        kind, payload, session = await _ordinary_reserve_hold(factory, gateway_key_id, request_id)
        if kind == "acquired":
            await session.commit()
            await session.close()
            return "reserved", payload
        return "rejected", payload
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
    route_id = await _create_model_route(dsn)
    request_ids = [f"req-race2-{uuid.uuid4()}" for _ in range(2)]
    outcomes = await asyncio.gather(
        *(_acquire_worker(dsn, key_id, request_id, route_id) for request_id in request_ids)
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
    route_id = await _create_model_route(dsn)
    request_ids = [f"req-race16-{uuid.uuid4()}" for _ in range(16)]
    outcomes = await asyncio.gather(
        *(_acquire_worker(dsn, key_id, request_id, route_id) for request_id in request_ids)
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
    route_id = await _create_model_route(dsn)
    request_id = f"req-same-{uuid.uuid4()}"
    outcomes = await asyncio.gather(
        *(_acquire_worker(dsn, key_id, request_id, route_id) for _ in range(8))
    )
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
    route_id = await _create_model_route(dsn)

    engine = create_async_engine(dsn, future=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            acquired = await _fence_service(session).acquire(
                _acquire_input(key_id, f"req-fence-{uuid.uuid4()}", route_id)
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


@pytest.mark.asyncio
async def test_race_fence_lock_first_blocks_ordinary_reservation(
    migrated_postgres_url: str,
) -> None:
    """Fence holds the locked key row uncommitted; the ordinary reservation
    must block on the row lock, then be rejected by the committed fence."""
    dsn = migrated_postgres_url
    key_id = await _create_key(dsn)
    route_id = await _create_model_route(dsn)

    fence_engine = create_async_engine(dsn, future=True)
    fence_factory = async_sessionmaker(fence_engine, expire_on_commit=False)
    ordinary_engine = create_async_engine(dsn, future=True)
    ordinary_factory = async_sessionmaker(ordinary_engine, expire_on_commit=False)
    fence_session = fence_factory()
    try:
        acquired = await _fence_service(fence_session).acquire(
            _acquire_input(key_id, f"req-racef-{uuid.uuid4()}", route_id)
        )
        task = asyncio.create_task(
            _ordinary_reserve_hold(ordinary_factory, key_id, f"req-raceo-{uuid.uuid4()}")
        )
        await asyncio.sleep(0.2)
        assert not task.done(), "ordinary reservation must block on the uncommitted fence lock"

        await fence_session.commit()
        kind, error, _held_session = await task
        assert kind == "rejected"
        assert isinstance(error, QuotaFenceActiveError)
        assert error.error_code == "external_tool_fence_active"
    finally:
        await fence_session.close()
        await fence_engine.dispose()
        await ordinary_engine.dispose()

    key = await _load_key(dsn, key_id)
    assert key.external_tool_fence_state == "active"
    assert key.external_tool_fence_request_id == acquired.request_id
    assert key.external_tool_fence_reservation_id == acquired.reservation_id
    assert key.cost_reserved_eur == COST_LIMIT
    assert key.tokens_reserved_total == TOKEN_LIMIT
    assert key.requests_reserved_total == 1
    assert await _count_reservations(dsn, key_id) == 1


@pytest.mark.asyncio
async def test_race_ordinary_reservation_first_blocks_fence(
    migrated_postgres_url: str,
) -> None:
    """Ordinary holds the locked key row uncommitted; the fence must block,
    then fail closed on the committed pending reservation without mutating
    the key, fencing it, or writing an acquired audit row."""
    dsn = migrated_postgres_url
    key_id = await _create_key(dsn)
    route_id = await _create_model_route(dsn)

    ordinary_engine = create_async_engine(dsn, future=True)
    ordinary_factory = async_sessionmaker(ordinary_engine, expire_on_commit=False)
    fence_engine = create_async_engine(dsn, future=True)
    fence_factory = async_sessionmaker(fence_engine, expire_on_commit=False)
    ordinary_session = ordinary_factory()
    fence_session = fence_factory()
    try:
        keys = GatewayKeysRepository(ordinary_session)
        row = await keys.get_gateway_key_for_update(key_id)
        assert row is not None
        await QuotaReservationsRepository(ordinary_session).create_reservation(
            gateway_key_id=key_id,
            request_id=f"req-ordrace-{uuid.uuid4()}",
            endpoint=ENDPOINT,
            requested_model=REQUESTED_MODEL,
            reserved_cost_eur=Decimal("0.25"),
            reserved_tokens=50,
            reserved_requests=1,
            status="pending",
            expires_at=datetime.now(UTC) + TTL,
        )
        await keys.add_reserved_counters(
            row,
            cost_reserved_eur=Decimal("0.25"),
            tokens_reserved_total=50,
            requests_reserved_total=1,
        )

        fence_task = asyncio.create_task(
            _fence_service(fence_session).acquire(
                _acquire_input(key_id, f"req-racef-{uuid.uuid4()}", route_id)
            )
        )
        await asyncio.sleep(0.2)
        assert not fence_task.done(), "fence must block on the uncommitted ordinary lock"

        await ordinary_session.commit()
        try:
            fence_result = await fence_task
        except ExternalToolFenceOccupiedError as raised:
            fence_error = raised
        else:
            pytest.fail(f"fence acquisition unexpectedly succeeded: {fence_result!r}")
        assert fence_error.error_code == "external_tool_fence_pending_reservation"
    finally:
        await ordinary_session.close()
        await ordinary_engine.dispose()
        await fence_session.close()
        await fence_engine.dispose()

    key = await _load_key(dsn, key_id)
    assert key.external_tool_fence_state == "none"
    assert key.external_tool_fence_reservation_id is None
    assert key.external_tool_fence_request_id is None
    assert key.cost_reserved_eur == Decimal("0.25")
    assert key.tokens_reserved_total == 50
    assert key.requests_reserved_total == 1
    assert await _count_reservations(dsn, key_id) == 1

    audit_engine = create_async_engine(dsn, future=True)
    try:
        async with audit_engine.connect() as conn:
            acquired_audit = (
                await conn.execute(
                    text(
                        "SELECT count(*) FROM audit_log"
                        " WHERE entity_type = 'gateway_key' AND entity_id = :key_id"
                        " AND action = 'external_tool_fence_acquired'"
                    ),
                    {"key_id": key_id},
                )
            ).one()
    finally:
        await audit_engine.dispose()
    assert int(acquired_audit[0]) == 0


@pytest.mark.asyncio
async def test_resolve_waits_on_reservation_before_locking_key(
    migrated_postgres_url: str,
) -> None:
    """An active resolve cannot hold the key while waiting on its reservation."""
    dsn = migrated_postgres_url
    key_id = await _create_key(dsn)
    route_id = await _create_model_route(dsn)

    setup_engine = create_async_engine(dsn, future=True)
    setup_factory = async_sessionmaker(setup_engine, expire_on_commit=False)
    async with setup_factory() as session:
        acquired = await _fence_service(session).acquire(
            _acquire_input(key_id, f"req-resolve-lock-{uuid.uuid4()}", route_id)
        )
        await session.commit()
    await setup_engine.dispose()

    held_engine = create_async_engine(dsn, future=True)
    held_factory = async_sessionmaker(held_engine, expire_on_commit=False)
    resolver_engine = create_async_engine(dsn, future=True)
    resolver_factory = async_sessionmaker(resolver_engine, expire_on_commit=False)
    key_engine = create_async_engine(dsn, future=True)
    key_factory = async_sessionmaker(key_engine, expire_on_commit=False)
    held_session = held_factory()

    async def resolve_worker():
        async with resolver_factory() as session:
            result = await asyncio.wait_for(
                _fence_service(session).resolve(
                    ExternalToolFenceResolveInput(
                        gateway_key_id=key_id,
                        request_id=acquired.request_id,
                    )
                ),
                timeout=5,
            )
            await session.commit()
            return result

    try:
        held_reservation = await QuotaReservationsRepository(held_session).get_reservation_by_id_for_update(
            acquired.reservation_id
        )
        assert held_reservation is not None
        resolver_task = asyncio.create_task(resolve_worker())
        await asyncio.sleep(0.2)
        assert not resolver_task.done(), "resolve must wait on the held reservation lock"

        async with key_factory() as session:
            await session.execute(text("SET LOCAL lock_timeout = '1000ms'"))
            key = await GatewayKeysRepository(session).get_gateway_key_for_update(key_id)
            assert key is not None, "resolve must not hold the key while waiting"
            key.external_tool_fence_state = "held"
            await session.commit()

        await held_session.rollback()
        result = await asyncio.wait_for(resolver_task, timeout=5)
        assert result.fence_state == "held"
        assert result.resolved is False
    finally:
        await held_session.close()
        await held_engine.dispose()
        await resolver_engine.dispose()
        await key_engine.dispose()

    key = await _load_key(dsn, key_id)
    assert key.external_tool_fence_state == "held"
    assert key.external_tool_fence_reservation_id == acquired.reservation_id
    assert await _count_reservations(dsn, key_id) == 1


@pytest.mark.asyncio
async def test_release_and_resolve_race_uses_reservation_first_lock_order(
    migrated_postgres_url: str,
) -> None:
    """Real release/resolve races terminate without clearing the fence."""
    dsn = migrated_postgres_url
    key_id = await _create_key(dsn)
    route_id = await _create_model_route(dsn)

    setup_engine = create_async_engine(dsn, future=True)
    setup_factory = async_sessionmaker(setup_engine, expire_on_commit=False)
    async with setup_factory() as session:
        acquired = await _fence_service(session).acquire(
            _acquire_input(key_id, f"req-release-resolve-{uuid.uuid4()}", route_id)
        )
        await session.commit()
    await setup_engine.dispose()

    release_engine = create_async_engine(dsn, future=True)
    release_factory = async_sessionmaker(release_engine, expire_on_commit=False)
    resolve_engine = create_async_engine(dsn, future=True)
    resolve_factory = async_sessionmaker(resolve_engine, expire_on_commit=False)

    async def release_worker():
        async with release_factory() as session:
            result = await _quota_service(session).release_reservation(
                acquired.reservation_id,
                reason="bounded objective-014 race test",
            )
            await session.commit()
            return result

    async def resolve_worker():
        async with resolve_factory() as session:
            try:
                result = await _fence_service(session).resolve(
                    ExternalToolFenceResolveInput(
                        gateway_key_id=key_id,
                        request_id=acquired.request_id,
                    )
                )
            except ExternalToolFenceInvariantError as error:
                await session.rollback()
                return error
            await session.commit()
            return result

    try:
        release_result, resolve_result = await asyncio.wait_for(
            asyncio.gather(release_worker(), resolve_worker()),
            timeout=5,
        )
    finally:
        await release_engine.dispose()
        await resolve_engine.dispose()

    assert release_result.status == "released"
    assert isinstance(resolve_result, (ExternalToolFenceInvariantError,))
    assert resolve_result.error_code in {
        "external_tool_fence_reservation_not_terminal",
        "external_tool_fence_ledger_count",
    }
    key = await _load_key(dsn, key_id)
    reservation = await _load_reservation(dsn, acquired.reservation_id)
    assert key.external_tool_fence_state == "active"
    assert key.cost_reserved_eur == Decimal("0")
    assert key.tokens_reserved_total == 0
    assert key.requests_reserved_total == 0
    assert reservation.status == "released"
    assert await _count_reservations(dsn, key_id) == 1

    audit_engine = create_async_engine(dsn, future=True)
    try:
        async with audit_engine.connect() as conn:
            counts = (
                await conn.execute(
                    text(
                        "SELECT action, count(*) FROM audit_log "
                        "WHERE entity_type = 'gateway_key' AND entity_id = :key_id "
                        "GROUP BY action"
                    ),
                    {"key_id": key_id},
                )
            ).all()
    finally:
        await audit_engine.dispose()
    assert dict(counts) == {"external_tool_fence_acquired": 1}
