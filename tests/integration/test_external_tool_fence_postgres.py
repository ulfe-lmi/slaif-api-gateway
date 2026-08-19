"""PostgreSQL integration tests for the exclusive external-tool fence foundation.

Objective 014 scope: migration backfills, constraint violations, exact
acquisition arithmetic, idempotent retry, blocking of later requests, the
``held`` state behavior (set only via raw SQL; the service never writes it),
restart durability, evidence-gated resolution, and reconciliation skipping.
No provider calls, no real email, and no prompt/body content is stored.
"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from slaif_gateway.config import Settings
from slaif_gateway.db.models import AuditLog, GatewayKey, QuotaReservation, UsageLedger
from slaif_gateway.db.repositories.audit import AuditRepository
from slaif_gateway.db.repositories.keys import GatewayKeysRepository
from slaif_gateway.db.repositories.owners import OwnersRepository
from slaif_gateway.db.repositories.quota import QuotaReservationsRepository
from slaif_gateway.db.repositories.usage import UsageLedgerRepository
from slaif_gateway.schemas.auth import AuthenticatedGatewayKey
from slaif_gateway.schemas.external_tool_fence import (
    ExternalToolFenceAcquireInput,
    ExternalToolFenceResolveInput,
    ExternalToolFenceRouteFacts,
)
from slaif_gateway.schemas.policy import ChatCompletionPolicyResult
from slaif_gateway.schemas.pricing import ChatCostEstimate
from slaif_gateway.schemas.routing import RouteResolutionResult
from slaif_gateway.services import auth_service
from slaif_gateway.services.auth_service import GatewayKeyExternalToolFenceActiveError
from slaif_gateway.services.external_tool_fence import (
    ExternalToolFenceActiveError,
    ExternalToolFenceConflictError,
    ExternalToolFenceExhaustedError,
    ExternalToolFenceInvariantError,
    ExternalToolFenceService,
)
from slaif_gateway.services.quota_errors import (
    ExternalToolFenceActiveError as QuotaFenceActiveError,
)
from slaif_gateway.services.quota_service import QuotaService
from slaif_gateway.utils.crypto import hmac_sha256_token

pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL is not set; skipping PostgreSQL external tool fence tests.",
)

HMAC_SECRET = "h" * 48
KEY_SECRET = "s" * 43
ENDPOINT = "/v1/chat/completions"
REQUESTED_MODEL = "classroom-cheap"
PROVIDER = "openai"
CAPABILITIES = ("provider_connector", "provider_remote_mcp")
DESTINATIONS = ("connector:demo", "remote_mcp:demo")
TTL = timedelta(minutes=15)

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


def _auth_service(session) -> auth_service.GatewayAuthService:
    return auth_service.GatewayAuthService(
        settings=Settings(
            TOKEN_HMAC_SECRET_V1=HMAC_SECRET, GATEWAY_KEY_ACCEPTED_PREFIXES="sk-slaif-"
        ),
        gateway_keys_repository=GatewayKeysRepository(session),
    )


def _quota_service(session) -> QuotaService:
    return QuotaService(
        gateway_keys_repository=GatewayKeysRepository(session),
        quota_reservations_repository=QuotaReservationsRepository(session),
    )


async def _create_key(
    session_factory,
    *,
    cost_limit: Decimal,
    token_limit: int,
    request_limit: int,
    fenced_policy: bool,
) -> tuple[uuid.UUID, uuid.UUID, str, str]:
    now = datetime.now(UTC)
    async with session_factory() as session:
        owner = await OwnersRepository(session).create_owner(
            name="Fence",
            surname="Integration",
            email=f"fence-integration-{uuid.uuid4()}@example.test",
        )
        public_key_id = f"k_{uuid.uuid4().hex}"
        token = f"sk-slaif-{public_key_id}.{KEY_SECRET}"
        row = await GatewayKeysRepository(session).create_gateway_key_record(
            public_key_id=public_key_id,
            token_hash=hmac_sha256_token(token, HMAC_SECRET),
            owner_id=owner.id,
            valid_from=now - timedelta(minutes=5),
            valid_until=now + timedelta(hours=6),
            cost_limit_eur=cost_limit,
            token_limit_total=token_limit,
            request_limit_total=request_limit,
            allow_all_models=True,
            allow_all_endpoints=True,
            metadata_json={"external_tool_policy": STORED_POLICY} if fenced_policy else None,
        )
        await session.commit()
        return owner.id, row.id, public_key_id, token


def _acquire_input(
    gateway_key_id: uuid.UUID,
    request_id: str,
    *,
    requested_model: str = REQUESTED_MODEL,
) -> ExternalToolFenceAcquireInput:
    return ExternalToolFenceAcquireInput(
        gateway_key_id=gateway_key_id,
        request_id=request_id,
        route=_route_facts(requested_model),
        capabilities=CAPABILITIES,
        destination_ids=DESTINATIONS,
        decision=_FencedDecision(),
        now=datetime.now(UTC),
        ttl=TTL,
    )


async def _acquire(
    session_factory,
    gateway_key_id: uuid.UUID,
    request_id: str,
    *,
    requested_model: str = REQUESTED_MODEL,
):
    async with session_factory() as session:
        result = await _fence_service(session).acquire(
            _acquire_input(gateway_key_id, request_id, requested_model=requested_model)
        )
        await session.commit()
        return result


async def _load_key(session_factory, gateway_key_id: uuid.UUID) -> GatewayKey:
    async with session_factory() as session:
        row = await GatewayKeysRepository(session).get_gateway_key_by_id(gateway_key_id)
        await session.commit()
        assert row is not None
        return row


async def _load_reservation(session_factory, reservation_id: uuid.UUID) -> QuotaReservation:
    async with session_factory() as session:
        row = await QuotaReservationsRepository(session).get_reservation_by_id(reservation_id)
        await session.commit()
        assert row is not None
        return row


async def _seed_counters(
    session_factory,
    key_id: uuid.UUID,
    *,
    used: tuple[Decimal, int, int],
    reserved: tuple[Decimal, int, int],
) -> None:
    async with session_factory() as session:
        keys = GatewayKeysRepository(session)
        row = await keys.get_gateway_key_for_update(key_id)
        assert row is not None
        row.cost_used_eur = used[0]
        row.tokens_used_total = used[1]
        row.requests_used_total = used[2]
        await keys.add_reserved_counters(
            row,
            cost_reserved_eur=reserved[0],
            tokens_reserved_total=reserved[1],
            requests_reserved_total=reserved[2],
        )
        await session.commit()


async def _cleanup_leftover_fenced_keys(engine) -> None:
    """Remove fenced keys committed by earlier tests in this file.

    Earlier fence tests commit their keys/reservations/ledger rows on purpose,
    so this final listing test must start from a clean fence state to assert
    its exact projection set. Only rows owned by active/held fences are
    removed; nothing else is touched.
    """
    fenced = "gk.external_tool_fence_state IN ('active', 'held')"
    async with engine.begin() as conn:
        fenced_key_ids = (
            (await conn.execute(text(f"SELECT gk.id FROM gateway_keys gk WHERE {fenced}")))
            .scalars()
            .all()
        )
        if not fenced_key_ids:
            return
        await conn.execute(
            text(
                "DELETE FROM usage_ledger WHERE quota_reservation_id IN ("
                " SELECT qr.id FROM quota_reservations qr"
                f" JOIN gateway_keys gk ON gk.id = qr.gateway_key_id WHERE {fenced})"
            )
        )
        await conn.execute(
            text(
                "UPDATE gateway_keys gk"
                " SET external_tool_fence_state = 'none',"
                " external_tool_fence_reservation_id = NULL,"
                " external_tool_fence_request_id = NULL,"
                " external_tool_fence_acquired_at = NULL,"
                " external_tool_fence_expires_at = NULL"
                f" WHERE {fenced}"
            )
        )
        await conn.execute(
            text(
                "DELETE FROM quota_reservations WHERE gateway_key_id IN ("
                " SELECT gk.id FROM gateway_keys gk WHERE gk.id = ANY(:key_ids))"
            ),
            {"key_ids": list(fenced_key_ids)},
        )
        await conn.execute(
            text("DELETE FROM gateway_keys WHERE id = ANY(:key_ids)"),
            {"key_ids": list(fenced_key_ids)},
        )


@pytest.mark.asyncio
async def test_backfilled_rows_get_fence_and_quota_mode_defaults(
    migrated_postgres_url: str,
) -> None:
    engine = create_async_engine(migrated_postgres_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    key_id: uuid.UUID | None = None
    try:
        _, key_id, _, _ = await _create_key(
            session_factory,
            cost_limit=Decimal("100"),
            token_limit=10_000,
            request_limit=100,
            fenced_policy=False,
        )
        async with session_factory() as session:
            reservation = await QuotaReservationsRepository(session).create_reservation(
                gateway_key_id=key_id,
                request_id=f"plain-{uuid.uuid4()}",
                endpoint=ENDPOINT,
                requested_model=REQUESTED_MODEL,
                reserved_cost_eur=Decimal("0.5"),
                reserved_tokens=10,
                reserved_requests=1,
                status="pending",
                expires_at=datetime.now(UTC) + TTL,
            )
            await session.commit()
            key = await GatewayKeysRepository(session).get_gateway_key_by_id(key_id)
            assert key.external_tool_fence_state == "none"
            assert key.external_tool_fence_reservation_id is None
            assert key.external_tool_fence_request_id is None
            assert key.external_tool_fence_acquired_at is None
            assert key.external_tool_fence_expires_at is None
            assert reservation.quota_mode == "strict_bounded"
            assert reservation.external_tool_capabilities == []
            assert reservation.external_tool_destination_ids == []
    finally:
        # This backfill row intentionally has no counter movement, so if
        # its reservation expired, a later whole-database stale-reservation
        # batch (this file's held-fence test) would raise a counter
        # invariant error. Delete the ledger, reservation, and key so no
        # later run of the suite can be poisoned by this test.
        if key_id is not None:
            async with engine.begin() as conn:
                await conn.execute(
                    text(
                        "DELETE FROM usage_ledger WHERE request_id IN "
                        "(SELECT request_id FROM quota_reservations "
                        "WHERE gateway_key_id = :key_id)"
                    ),
                    {"key_id": key_id},
                )
                await conn.execute(
                    text("DELETE FROM quota_reservations WHERE gateway_key_id = :key_id"),
                    {"key_id": key_id},
                )
                await conn.execute(
                    text("DELETE FROM gateway_keys WHERE id = :key_id"),
                    {"key_id": key_id},
                )
        await engine.dispose()


@pytest.mark.asyncio
async def test_fence_column_constraint_violations(migrated_postgres_url: str) -> None:
    engine = create_async_engine(migrated_postgres_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        _, key_id, _, _ = await _create_key(
            session_factory,
            cost_limit=Decimal("100"),
            token_limit=10_000,
            request_limit=100,
            fenced_policy=False,
        )
        async with session_factory() as session:
            reservation = await QuotaReservationsRepository(session).create_reservation(
                gateway_key_id=key_id,
                request_id=f"plain-{uuid.uuid4()}",
                endpoint=ENDPOINT,
                requested_model=REQUESTED_MODEL,
                reserved_cost_eur=Decimal("0.5"),
                reserved_tokens=10,
                reserved_requests=1,
                status="pending",
                expires_at=datetime.now(UTC) + TTL,
            )
            await session.commit()
            reservation_id = reservation.id

        now = datetime.now(UTC)

        # Bound fence states require all four bound columns to be set.
        with pytest.raises(IntegrityError):
            async with engine.begin() as conn:
                await conn.execute(
                    text(
                        "UPDATE gateway_keys SET external_tool_fence_state = 'active' WHERE id = :key_id"
                    ),
                    {"key_id": key_id},
                )

        # none state requires all four bound columns to be NULL.
        with pytest.raises(IntegrityError):
            async with engine.begin() as conn:
                await conn.execute(
                    text(
                        "UPDATE gateway_keys SET external_tool_fence_state = 'none',"
                        " external_tool_fence_request_id = :request_id WHERE id = :key_id"
                    ),
                    {"key_id": key_id, "request_id": "req-x"},
                )

        # Unknown fence state values are rejected.
        with pytest.raises(IntegrityError):
            async with engine.begin() as conn:
                await conn.execute(
                    text(
                        "UPDATE gateway_keys SET external_tool_fence_state = 'bogus' WHERE id = :key_id"
                    ),
                    {"key_id": key_id},
                )

        # strict_bounded reservations must keep external facts empty.
        with pytest.raises(IntegrityError):
            async with engine.begin() as conn:
                await conn.execute(
                    text(
                        "UPDATE quota_reservations SET external_tool_capabilities = '"
                        '["provider_connector"]\'::jsonb WHERE id = :reservation_id'
                    ),
                    {"reservation_id": reservation_id},
                )

        # external_tool_fenced reservations require a non-empty capability array.
        with pytest.raises(IntegrityError):
            async with engine.begin() as conn:
                await conn.execute(
                    text(
                        "UPDATE quota_reservations SET quota_mode = 'external_tool_fenced',"
                        " external_tool_capabilities = '[]'::jsonb WHERE id = :reservation_id"
                    ),
                    {"reservation_id": reservation_id},
                )

        # A key that owns a fence cannot be deleted (FK RESTRICT).
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "UPDATE quota_reservations SET quota_mode = 'external_tool_fenced',"
                    ' external_tool_capabilities = \'["provider_connector", "provider_remote_mcp"]\'::jsonb,'
                    ' external_tool_destination_ids = \'["connector:demo", "remote_mcp:demo"]\'::jsonb'
                    " WHERE id = :reservation_id"
                ),
                {"reservation_id": reservation_id},
            )
            await conn.execute(
                text(
                    "UPDATE gateway_keys SET external_tool_fence_state = 'active',"
                    " external_tool_fence_reservation_id = :reservation_id,"
                    " external_tool_fence_request_id = :request_id,"
                    " external_tool_fence_acquired_at = :acquired_at,"
                    " external_tool_fence_expires_at = :expires_at WHERE id = :key_id"
                ),
                {
                    "key_id": key_id,
                    "reservation_id": reservation_id,
                    "request_id": "req-fenced",
                    "acquired_at": now,
                    "expires_at": now + TTL,
                },
            )
        with pytest.raises(IntegrityError):
            async with engine.begin() as conn:
                await conn.execute(
                    text("DELETE FROM gateway_keys WHERE id = :key_id"),
                    {"key_id": key_id},
                )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_acquire_reserves_exact_remaining_and_is_idempotent(
    migrated_postgres_url: str,
) -> None:
    engine = create_async_engine(migrated_postgres_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        _, key_id, _, _ = await _create_key(
            session_factory,
            cost_limit=Decimal("25"),
            token_limit=100_000,
            request_limit=1000,
            fenced_policy=True,
        )
        await _seed_counters(
            session_factory,
            key_id,
            used=(Decimal("1.25"), 100, 2),
            reserved=(Decimal("0.50"), 50, 1),
        )

        request_id = f"req-fence-{uuid.uuid4()}"
        acquired = await _acquire(session_factory, key_id, request_id)

        # Remaining exposure is reserved in full: 25-1.25-0.50, 100000-100-50, requests=1.
        assert acquired.fence_state == "active"
        assert acquired.idempotent is False
        assert acquired.reserved_cost_eur == Decimal("23.25")
        assert acquired.reserved_tokens == 99_850
        assert acquired.reserved_requests == 1
        assert acquired.capabilities == CAPABILITIES
        assert acquired.destination_ids == DESTINATIONS

        key = await _load_key(session_factory, key_id)
        assert key.external_tool_fence_state == "active"
        assert key.external_tool_fence_reservation_id == acquired.reservation_id
        assert key.external_tool_fence_request_id == request_id
        assert key.external_tool_fence_acquired_at == acquired.acquired_at
        assert key.external_tool_fence_expires_at == acquired.expires_at
        assert key.cost_used_eur == Decimal("1.25")
        assert key.tokens_used_total == 100
        assert key.requests_used_total == 2
        assert key.cost_reserved_eur == Decimal("23.75")
        assert key.tokens_reserved_total == 99_900
        assert key.requests_reserved_total == 2

        reservation = await _load_reservation(session_factory, acquired.reservation_id)
        assert reservation.quota_mode == "external_tool_fenced"
        assert reservation.external_tool_capabilities == list(CAPABILITIES)
        assert reservation.external_tool_destination_ids == list(DESTINATIONS)
        assert reservation.status == "pending"
        assert reservation.reserved_cost_eur == Decimal("23.25")
        assert reservation.reserved_tokens == 99_850
        assert reservation.reserved_requests == 1
        assert reservation.expires_at == acquired.expires_at

        async with session_factory() as session:
            audits = (
                (
                    await session.execute(
                        select(AuditLog).where(
                            AuditLog.entity_type == "gateway_key",
                            AuditLog.entity_id == key_id,
                            AuditLog.action == "external_tool_fence_acquired",
                        )
                    )
                )
                .scalars()
                .all()
            )
            await session.commit()
        assert [audit.request_id for audit in audits] == [request_id]
        assert all(audit.note == "external tool fence acquired" for audit in audits)

        # Idempotent retry: same request id and identical route facts.
        retry = await _acquire(session_factory, key_id, request_id)
        assert retry.idempotent is True
        assert retry.reservation_id == acquired.reservation_id
        key = await _load_key(session_factory, key_id)
        assert key.cost_reserved_eur == Decimal("23.75")
        assert key.tokens_reserved_total == 99_900
        assert key.requests_reserved_total == 2
        assert key.external_tool_fence_state == "active"
    finally:
        await engine.dispose()


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


@pytest.mark.asyncio
async def test_active_fence_blocks_auth_quota_and_other_acquires(
    migrated_postgres_url: str,
) -> None:
    engine = create_async_engine(migrated_postgres_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        _, key_id, _, token = await _create_key(
            session_factory,
            cost_limit=Decimal("25"),
            token_limit=100_000,
            request_limit=1000,
            fenced_policy=True,
        )
        acquired = await _acquire(session_factory, key_id, f"req-fence-{uuid.uuid4()}")
        before = await _load_key(session_factory, key_id)

        async with session_factory() as session:
            with pytest.raises(GatewayKeyExternalToolFenceActiveError):
                await _auth_service(session).authenticate_authorization_header(f"Bearer {token}")
            await session.rollback()

        async with session_factory() as session:
            row = await GatewayKeysRepository(session).get_gateway_key_by_id(key_id)
            assert row is not None
            with pytest.raises(QuotaFenceActiveError):
                await _quota_service(session).reserve_for_chat_completion(
                    authenticated_key=_authenticated_key(row),
                    route=RouteResolutionResult(
                        requested_model=REQUESTED_MODEL,
                        resolved_model="gpt-4.1-mini",
                        provider=PROVIDER,
                        route_id=uuid.uuid4(),
                        route_match_type="exact",
                        route_pattern=REQUESTED_MODEL,
                        priority=100,
                    ),
                    policy=ChatCompletionPolicyResult(
                        effective_body={
                            "model": REQUESTED_MODEL,
                            "messages": [],
                            "max_completion_tokens": 5,
                        },
                        requested_output_tokens=5,
                        effective_output_tokens=5,
                        estimated_input_tokens=5,
                        injected_default_output_tokens=False,
                    ),
                    cost_estimate=ChatCostEstimate(
                        provider=PROVIDER,
                        requested_model=REQUESTED_MODEL,
                        resolved_model="gpt-4.1-mini",
                        native_currency="EUR",
                        estimated_input_tokens=5,
                        estimated_output_tokens=5,
                        estimated_input_cost_native=Decimal("0.01"),
                        estimated_output_cost_native=Decimal("0.01"),
                        estimated_total_cost_native=Decimal("0.02"),
                        estimated_total_cost_eur=Decimal("0.02"),
                        pricing_rule_id=None,
                        fx_rate_id=None,
                    ),
                    request_id=f"req-quota-{uuid.uuid4()}",
                )
            await session.rollback()

        async with session_factory() as session:
            with pytest.raises(ExternalToolFenceActiveError):
                await _fence_service(session).acquire(
                    _acquire_input(key_id, f"req-other-{uuid.uuid4()}")
                )
            await session.rollback()

        after = await _load_key(session_factory, key_id)
        assert after.cost_reserved_eur == before.cost_reserved_eur
        assert after.tokens_reserved_total == before.tokens_reserved_total
        assert after.requests_reserved_total == before.requests_reserved_total
        assert after.external_tool_fence_reservation_id == acquired.reservation_id
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_acquire_conflicts_and_exhaustion(migrated_postgres_url: str) -> None:
    engine = create_async_engine(migrated_postgres_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        _, key_id, _, _ = await _create_key(
            session_factory,
            cost_limit=Decimal("25"),
            token_limit=100_000,
            request_limit=1000,
            fenced_policy=True,
        )
        request_id = f"req-conflict-{uuid.uuid4()}"
        await _acquire(session_factory, key_id, request_id)

        # Same request id but changed route facts is a conflict.
        async with session_factory() as session:
            with pytest.raises(ExternalToolFenceConflictError):
                await _fence_service(session).acquire(
                    _acquire_input(key_id, request_id, requested_model="other-model")
                )
            await session.rollback()

        # Clearing the fence (owner action) leaves the reservation's request id
        # non-reusable: a fresh acquisition with the same id conflicts.
        async with session_factory() as session:
            keys = GatewayKeysRepository(session)
            row = await keys.get_gateway_key_for_update(key_id)
            assert row is not None
            await keys.set_external_tool_fence(
                row,
                state="none",
                reservation_id=None,
                request_id=None,
                acquired_at=None,
                expires_at=None,
            )
            await session.commit()
        async with session_factory() as session:
            with pytest.raises(ExternalToolFenceConflictError) as exc_info:
                await _fence_service(session).acquire(
                    _acquire_input(key_id, request_id, requested_model="other-model")
                )
            assert exc_info.value.error_code == "external_tool_fence_request_id_reused"
            await session.rollback()

        # Exhausted key: no remaining request quota.
        _, exhausted_id, _, _ = await _create_key(
            session_factory,
            cost_limit=Decimal("1"),
            token_limit=10,
            request_limit=1,
            fenced_policy=True,
        )
        await _seed_counters(
            session_factory,
            exhausted_id,
            used=(Decimal("0"), 0, 0),
            reserved=(Decimal("0.50"), 5, 1),
        )
        async with session_factory() as session:
            with pytest.raises(ExternalToolFenceExhaustedError):
                await _fence_service(session).acquire(
                    _acquire_input(exhausted_id, f"req-exhausted-{uuid.uuid4()}")
                )
            await session.rollback()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_held_fence_blocks_and_never_auto_releases(migrated_postgres_url: str) -> None:
    engine = create_async_engine(migrated_postgres_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        _, key_id, _, token = await _create_key(
            session_factory,
            cost_limit=Decimal("25"),
            token_limit=100_000,
            request_limit=1000,
            fenced_policy=True,
        )
        acquired = await _acquire(session_factory, key_id, f"req-held-{uuid.uuid4()}")

        # ``held`` is only reachable via operator-level raw SQL in this scope.
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "UPDATE gateway_keys SET external_tool_fence_state = 'held' WHERE id = :key_id"
                ),
                {"key_id": key_id},
            )

        before = await _load_key(session_factory, key_id)
        assert before.external_tool_fence_state == "held"

        async with session_factory() as session:
            with pytest.raises(GatewayKeyExternalToolFenceActiveError):
                await _auth_service(session).authenticate_authorization_header(f"Bearer {token}")
            await session.rollback()

        async with session_factory() as session:
            with pytest.raises(ExternalToolFenceActiveError):
                await _fence_service(session).acquire(
                    _acquire_input(key_id, f"req-other-{uuid.uuid4()}")
                )
            await session.rollback()

        # Resolution is a no-op for held fences: 015 owns that transition.
        async with session_factory() as session:
            result = await _fence_service(session).resolve(
                ExternalToolFenceResolveInput(gateway_key_id=key_id, request_id=acquired.request_id)
            )
            await session.commit()
        assert result.fence_state == "held"
        assert result.resolved is False
        after = await _load_key(session_factory, key_id)
        assert after.external_tool_fence_state == "held"
        assert after.cost_reserved_eur == before.cost_reserved_eur

        # Force the fence reservation to expire, then prove ordinary
        # reconciliation never auto-releases it.
        async with engine.begin() as conn:
            await conn.execute(
                text("UPDATE quota_reservations SET expires_at = :past WHERE id = :reservation_id"),
                {
                    "past": datetime.now(UTC) - timedelta(minutes=1),
                    "reservation_id": acquired.reservation_id,
                },
            )

        from slaif_gateway.services.reservation_reconciliation import (
            ReservationReconciliationService,
        )

        async with session_factory() as session:
            summary = await ReservationReconciliationService(
                gateway_keys_repository=GatewayKeysRepository(session),
                quota_reservations_repository=QuotaReservationsRepository(session),
                usage_ledger_repository=UsageLedgerRepository(session),
                audit_repository=AuditRepository(session),
            ).reconcile_expired_pending_reservations(now=datetime.now(UTC))
            await session.commit()
        assert summary.skipped_count >= 1
        assert summary.reconciled_count == 0
        reservation = await _load_reservation(session_factory, acquired.reservation_id)
        assert reservation.status == "pending"
        held = await _load_key(session_factory, key_id)
        assert held.external_tool_fence_state == "held"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_fence_survives_restart_and_resolves_from_finalized_evidence(
    migrated_postgres_url: str,
) -> None:
    engine = create_async_engine(migrated_postgres_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        owner_id, key_id, _, _ = await _create_key(
            session_factory,
            cost_limit=Decimal("25"),
            token_limit=100_000,
            request_limit=1000,
            fenced_policy=True,
        )
        acquired = await _acquire(session_factory, key_id, f"req-restart-{uuid.uuid4()}")
    finally:
        await engine.dispose()

    # Restart: a brand-new engine/connection sees the committed fence.
    restart_engine = create_async_engine(migrated_postgres_url, future=True)
    restart_factory = async_sessionmaker(restart_engine, expire_on_commit=False)
    try:
        async with restart_factory() as session:
            row = await GatewayKeysRepository(session).get_gateway_key_for_update(key_id)
            await session.commit()
            assert row is not None
            assert row.external_tool_fence_state == "active"
            assert row.external_tool_fence_reservation_id == acquired.reservation_id
            assert row.external_tool_fence_request_id == acquired.request_id
            assert row.external_tool_fence_acquired_at is not None
            assert row.external_tool_fence_expires_at is not None

        # Simulate authoritative accounting finalization (owned by later
        # objectives): move reserved counters into used counters, finalize the
        # reservation, and record exactly one finalized success ledger row.
        async with restart_factory() as session:
            keys = GatewayKeysRepository(session)
            row = await keys.get_gateway_key_for_update(key_id)
            assert row is not None
            await keys.finalize_reserved_counters(
                row,
                reserved_cost_eur=acquired.reserved_cost_eur,
                reserved_tokens_total=acquired.reserved_tokens,
                reserved_requests_total=acquired.reserved_requests,
                actual_cost_eur=Decimal("0.20"),
                actual_tokens_total=30,
                actual_requests_total=1,
                last_used_at=datetime.now(UTC),
            )
            reservation = await QuotaReservationsRepository(
                session
            ).get_reservation_by_id_for_update(acquired.reservation_id)
            assert reservation is not None
            reservation.status = "finalized"
            reservation.finalized_at = datetime.now(UTC)
            session.add(
                UsageLedger(
                    request_id=f"ledger-{uuid.uuid4()}",
                    quota_reservation_id=reservation.id,
                    gateway_key_id=key_id,
                    owner_id=owner_id,
                    endpoint=ENDPOINT,
                    http_method="POST",
                    provider=PROVIDER,
                    requested_model=REQUESTED_MODEL,
                    resolved_model="gpt-4.1-mini",
                    streaming=False,
                    success=True,
                    accounting_status="finalized",
                    http_status=200,
                    input_tokens=10,
                    output_tokens=20,
                    total_tokens=30,
                    actual_cost_eur=Decimal("0.20"),
                    native_currency="EUR",
                    usage_raw={},
                    response_metadata={},
                    started_at=datetime.now(UTC) - timedelta(seconds=1),
                    finished_at=datetime.now(UTC),
                )
            )
            await session.commit()

        async with restart_factory() as session:
            result = await _fence_service(session).resolve(
                ExternalToolFenceResolveInput(gateway_key_id=key_id, request_id=acquired.request_id)
            )
            await session.commit()
        assert result.fence_state == "none"
        assert result.resolved is True

        async with restart_factory() as session:
            row = await GatewayKeysRepository(session).get_gateway_key_for_update(key_id)
            await session.commit()
            assert row is not None
            assert row.external_tool_fence_state == "none"
            assert row.external_tool_fence_reservation_id is None
            assert row.external_tool_fence_request_id is None
            assert row.external_tool_fence_acquired_at is None
            assert row.external_tool_fence_expires_at is None
            audits = (
                (
                    await session.execute(
                        select(AuditLog).where(
                            AuditLog.entity_type == "gateway_key",
                            AuditLog.entity_id == key_id,
                            AuditLog.action == "external_tool_fence_resolved",
                        )
                    )
                )
                .scalars()
                .all()
            )
            assert [audit.request_id for audit in audits] == [acquired.request_id]

        # Re-resolution is a no-op once the fence is cleared.
        async with restart_factory() as session:
            result = await _fence_service(session).resolve(
                ExternalToolFenceResolveInput(gateway_key_id=key_id, request_id=acquired.request_id)
            )
            await session.commit()
        assert result.fence_state == "none"
        assert result.resolved is False
    finally:
        await restart_engine.dispose()


def _ledger(
    reservation_id: uuid.UUID,
    key_id: uuid.UUID,
    owner_id: uuid.UUID,
    *,
    success: bool,
    accounting_status: str,
) -> UsageLedger:
    now = datetime.now(UTC)
    return UsageLedger(
        request_id=f"ledger-{uuid.uuid4()}",
        quota_reservation_id=reservation_id,
        gateway_key_id=key_id,
        owner_id=owner_id,
        endpoint=ENDPOINT,
        http_method="POST",
        provider=PROVIDER,
        requested_model=REQUESTED_MODEL,
        resolved_model="gpt-4.1-mini",
        streaming=False,
        success=success,
        accounting_status=accounting_status,
        http_status=200 if success else 502,
        input_tokens=10,
        output_tokens=20,
        total_tokens=30,
        actual_cost_eur=Decimal("0.20") if success else None,
        native_currency="EUR",
        usage_raw={},
        response_metadata={},
        started_at=now - timedelta(seconds=1),
        finished_at=now,
    )


async def _finalize_reservation(
    session, reservation, *, success: bool, accounting_status: str
) -> None:
    reservation.status = "finalized"
    reservation.finalized_at = datetime.now(UTC)
    session.add(
        _ledger(
            reservation.id,
            reservation.gateway_key_id,
            uuid.uuid4(),
            success=success,
            accounting_status=accounting_status,
        )
    )
    await session.flush()


@pytest.mark.asyncio
async def test_resolve_negative_evidence_never_clears_fence(migrated_postgres_url: str) -> None:
    engine = create_async_engine(migrated_postgres_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        # Key A: reservation is not terminal.
        owner_a, key_a, _, _ = await _create_key(
            session_factory,
            cost_limit=Decimal("25"),
            token_limit=100_000,
            request_limit=1000,
            fenced_policy=True,
        )
        acquired_a = await _acquire(session_factory, key_a, f"req-neg-{uuid.uuid4()}")
        async with session_factory() as session:
            with pytest.raises(ExternalToolFenceInvariantError) as exc_info:
                await _fence_service(session).resolve(
                    ExternalToolFenceResolveInput(
                        gateway_key_id=key_a, request_id=acquired_a.request_id
                    )
                )
            assert exc_info.value.error_code == "external_tool_fence_reservation_not_terminal"
            await session.rollback()
        assert (await _load_key(session_factory, key_a)).external_tool_fence_state == "active"

        # Key B: finalized reservation but no / two / mismatched ledgers.
        owner_b, key_b, _, _ = await _create_key(
            session_factory,
            cost_limit=Decimal("25"),
            token_limit=100_000,
            request_limit=1000,
            fenced_policy=True,
        )
        acquired_b = await _acquire(session_factory, key_b, f"req-neg-{uuid.uuid4()}")

        async with session_factory() as session:
            reservation = await QuotaReservationsRepository(
                session
            ).get_reservation_by_id_for_update(acquired_b.reservation_id)
            assert reservation is not None
            reservation.status = "finalized"
            reservation.finalized_at = datetime.now(UTC)
            await session.commit()
        async with session_factory() as session:
            with pytest.raises(ExternalToolFenceInvariantError) as exc_info:
                await _fence_service(session).resolve(
                    ExternalToolFenceResolveInput(
                        gateway_key_id=key_b, request_id=acquired_b.request_id
                    )
                )
            assert exc_info.value.error_code == "external_tool_fence_ledger_count"
            await session.rollback()

        async with session_factory() as session:
            reservation = await QuotaReservationsRepository(
                session
            ).get_reservation_by_id_for_update(acquired_b.reservation_id)
            assert reservation is not None
            session.add(
                _ledger(reservation.id, key_b, owner_b, success=True, accounting_status="finalized")
            )
            session.add(
                _ledger(reservation.id, key_b, owner_b, success=True, accounting_status="finalized")
            )
            await session.commit()
        async with session_factory() as session:
            with pytest.raises(ExternalToolFenceInvariantError) as exc_info:
                await _fence_service(session).resolve(
                    ExternalToolFenceResolveInput(
                        gateway_key_id=key_b, request_id=acquired_b.request_id
                    )
                )
            assert exc_info.value.error_code == "external_tool_fence_ledger_count"
            await session.rollback()

        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "DELETE FROM usage_ledger WHERE quota_reservation_id = :reservation_id"
                    " AND id <> (SELECT min(id::text) FROM usage_ledger WHERE quota_reservation_id = :reservation_id)::uuid"
                ),
                {"reservation_id": acquired_b.reservation_id},
            )
            await conn.execute(
                text(
                    "UPDATE usage_ledger SET success = false, accounting_status = 'failed',"
                    " actual_cost_eur = NULL WHERE quota_reservation_id = :reservation_id"
                ),
                {"reservation_id": acquired_b.reservation_id},
            )
        async with session_factory() as session:
            with pytest.raises(ExternalToolFenceInvariantError) as exc_info:
                await _fence_service(session).resolve(
                    ExternalToolFenceResolveInput(
                        gateway_key_id=key_b, request_id=acquired_b.request_id
                    )
                )
            assert exc_info.value.error_code == "external_tool_fence_ledger_mismatch"
            await session.rollback()
        assert (await _load_key(session_factory, key_b)).external_tool_fence_state == "active"

        # Key C: request id mismatch.
        owner_c, key_c, _, _ = await _create_key(
            session_factory,
            cost_limit=Decimal("25"),
            token_limit=100_000,
            request_limit=1000,
            fenced_policy=True,
        )
        await _acquire(session_factory, key_c, f"req-neg-{uuid.uuid4()}")
        async with session_factory() as session:
            with pytest.raises(ExternalToolFenceConflictError) as exc_info:
                await _fence_service(session).resolve(
                    ExternalToolFenceResolveInput(
                        gateway_key_id=key_c, request_id=f"req-other-{uuid.uuid4()}"
                    )
                )
            assert exc_info.value.error_code == "external_tool_fence_resolution_request_mismatch"
            await session.rollback()
        assert (await _load_key(session_factory, key_c)).external_tool_fence_state == "active"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_list_unresolved_fences_projects_bound_fences_only(
    migrated_postgres_url: str,
) -> None:
    engine = create_async_engine(migrated_postgres_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        await _cleanup_leftover_fenced_keys(engine)
        _, active_id, _, _ = await _create_key(
            session_factory,
            cost_limit=Decimal("25"),
            token_limit=100_000,
            request_limit=1000,
            fenced_policy=True,
        )
        active = await _acquire(session_factory, active_id, f"req-list-{uuid.uuid4()}")

        _, held_id, _, _ = await _create_key(
            session_factory,
            cost_limit=Decimal("25"),
            token_limit=100_000,
            request_limit=1000,
            fenced_policy=True,
        )
        held = await _acquire(session_factory, held_id, f"req-list-{uuid.uuid4()}")
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "UPDATE gateway_keys SET external_tool_fence_state = 'held' WHERE id = :key_id"
                ),
                {"key_id": held_id},
            )

        _, plain_id, _, _ = await _create_key(
            session_factory,
            cost_limit=Decimal("25"),
            token_limit=100_000,
            request_limit=1000,
            fenced_policy=False,
        )

        async with session_factory() as session:
            projections = await _fence_service(session).list_unresolved_fences(limit=100)
            await session.commit()
        by_key = {p.gateway_key_id: p for p in projections}
        assert set(by_key) == {active_id, held_id}
        assert plain_id not in by_key
        assert by_key[active_id].fence_state == "active"
        assert by_key[active_id].reservation_id == active.reservation_id
        assert by_key[active_id].request_id == active.request_id
        assert by_key[active_id].acquired_at == active.acquired_at
        assert by_key[active_id].expires_at == active.expires_at
        assert by_key[held_id].fence_state == "held"
        assert by_key[held_id].reservation_id == held.reservation_id
        assert by_key[held_id].request_id == held.request_id
    finally:
        await engine.dispose()
