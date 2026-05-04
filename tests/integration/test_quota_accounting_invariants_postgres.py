"""PostgreSQL invariant checks for quota, accounting, and reconciliation."""

from __future__ import annotations

import json
import os
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from slaif_gateway.config import Settings
from slaif_gateway.db.models import AuditLog, GatewayKey, QuotaReservation, UsageLedger
from slaif_gateway.db.repositories.audit import AuditRepository
from slaif_gateway.db.repositories.keys import GatewayKeysRepository
from slaif_gateway.db.repositories.owners import OwnersRepository
from slaif_gateway.db.repositories.quota import QuotaReservationsRepository
from slaif_gateway.db.repositories.usage import UsageLedgerRepository
from slaif_gateway.schemas.auth import AuthenticatedGatewayKey
from slaif_gateway.schemas.policy import ChatCompletionPolicyResult
from slaif_gateway.schemas.pricing import ChatCostEstimate
from slaif_gateway.schemas.providers import ProviderResponse, ProviderUsage
from slaif_gateway.schemas.routing import RouteResolutionResult
from slaif_gateway.services.accounting import AccountingService
from slaif_gateway.services.accounting_errors import ReservationAlreadyFinalizedError
from slaif_gateway.services.quota_service import QuotaService
from slaif_gateway.services.reconciliation_errors import ProviderCompletedRecoveryAlreadyReconciledError
from slaif_gateway.services.reservation_reconciliation import ReservationReconciliationService
from slaif_gateway.workers import tasks_reconciliation

pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL is not set; skipping optional PostgreSQL invariant tests.",
)

PROMPT_TEXT = "sensitive invariant prompt"
COMPLETION_TEXT = "sensitive invariant completion"
RAW_REQUEST_TEXT = "raw invariant request body"
RAW_RESPONSE_TEXT = "raw invariant response body"
PLAINTEXT_GATEWAY_KEY = "sk-slaif-plaintext-invariant-secret"
PROVIDER_KEY = "sk-provider-invariant-secret"
TOKEN_HASH = "token_hash"
ENCRYPTED_PAYLOAD = "encrypted_payload"
NONCE = "nonce"
PASSWORD_HASH = "password_hash"
SESSION_TOKEN = "session_token"
SAFE_FORBIDDEN_TERMS = (
    PROMPT_TEXT,
    COMPLETION_TEXT,
    RAW_REQUEST_TEXT,
    RAW_RESPONSE_TEXT,
    PLAINTEXT_GATEWAY_KEY,
    PROVIDER_KEY,
    TOKEN_HASH,
    ENCRYPTED_PAYLOAD,
    NONCE,
    PASSWORD_HASH,
    SESSION_TOKEN,
)


@pytest.mark.asyncio
async def test_postgres_double_release_finalize_and_provider_failure_invariants(
    async_test_session: AsyncSession,
) -> None:
    gateway_key = await _create_gateway_key(async_test_session)
    quota_service = _quota_service(async_test_session)
    accounting = _accounting_service(async_test_session)

    released = await quota_service.reserve_for_chat_completion(
        authenticated_key=_auth(gateway_key),
        route=_route(),
        policy=_policy(input_tokens=20, output_tokens=30),
        cost_estimate=_estimate(input_tokens=20, output_tokens=30),
        request_id=f"req-release-{uuid.uuid4()}",
        now=datetime.now(UTC),
    )
    await async_test_session.refresh(gateway_key)
    assert gateway_key.tokens_reserved_total == 50

    await quota_service.release_reservation(released.reservation_id)
    await quota_service.release_reservation(released.reservation_id)
    await _assert_key_counters(
        async_test_session,
        gateway_key.id,
        reserved_cost=Decimal("0E-9"),
        reserved_tokens=0,
        reserved_requests=0,
        used_cost=Decimal("0E-9"),
        used_tokens=0,
        used_requests=0,
    )

    finalized = await quota_service.reserve_for_chat_completion(
        authenticated_key=_auth(gateway_key),
        route=_route(),
        policy=_policy(input_tokens=20, output_tokens=30),
        cost_estimate=_estimate(input_tokens=20, output_tokens=30),
        request_id=f"req-finalize-{uuid.uuid4()}",
    )
    await accounting.finalize_successful_response(
        finalized.reservation_id,
        _auth(gateway_key),
        _route(),
        _policy(input_tokens=20, output_tokens=30),
        _estimate(input_tokens=20, output_tokens=30),
        _response(prompt_tokens=10, completion_tokens=15),
        request_id=finalized.request_id,
    )

    with pytest.raises(ReservationAlreadyFinalizedError):
        await accounting.finalize_successful_response(
            finalized.reservation_id,
            _auth(gateway_key),
            _route(),
            _policy(input_tokens=20, output_tokens=30),
            _estimate(input_tokens=20, output_tokens=30),
            _response(prompt_tokens=10, completion_tokens=15),
            request_id=f"{finalized.request_id}-again",
        )
    await _assert_key_counters(
        async_test_session,
        gateway_key.id,
        reserved_cost=Decimal("0E-9"),
        reserved_tokens=0,
        reserved_requests=0,
        used_cost=Decimal("0.060000000"),
        used_tokens=25,
        used_requests=1,
    )
    ledger_count = await _usage_count_for_request(async_test_session, finalized.request_id)
    assert ledger_count == 1

    failed = await quota_service.reserve_for_chat_completion(
        authenticated_key=_auth(gateway_key),
        route=_route(),
        policy=_policy(input_tokens=20, output_tokens=30),
        cost_estimate=_estimate(input_tokens=20, output_tokens=30),
        request_id=f"req-failure-{uuid.uuid4()}",
    )
    failure = await accounting.record_provider_failure_and_release(
        failed.reservation_id,
        _auth(gateway_key),
        _route(),
        _policy(input_tokens=20, output_tokens=30),
        _estimate(input_tokens=20, output_tokens=30),
        request_id=failed.request_id,
        error_type="provider_error",
        provider_diagnostic={
            "message": "provider failed",
            "prompt": PROMPT_TEXT,
            "completion": COMPLETION_TEXT,
            "provider_key": PROVIDER_KEY,
            "raw_request_body": RAW_REQUEST_TEXT,
            "raw_response_body": RAW_RESPONSE_TEXT,
            "token_hash": TOKEN_HASH,
            "encrypted_payload": ENCRYPTED_PAYLOAD,
            "nonce": NONCE,
        },
    )
    assert failure.released is True
    await _assert_key_counters(
        async_test_session,
        gateway_key.id,
        reserved_cost=Decimal("0E-9"),
        reserved_tokens=0,
        reserved_requests=0,
        used_cost=Decimal("0.060000000"),
        used_tokens=25,
        used_requests=1,
    )
    failure_row = await _usage_for_request(async_test_session, failed.request_id)
    assert failure_row.accounting_status == "failed"
    assert failure_row.actual_cost_eur == Decimal("0E-9")
    _assert_safe_payload(
        {
            "usage_raw": failure_row.usage_raw,
            "response_metadata": failure_row.response_metadata,
        }
    )


@pytest.mark.asyncio
async def test_postgres_reconciliation_invariants_are_idempotent_and_safe(
    async_test_session: AsyncSession,
) -> None:
    gateway_key = await _create_gateway_key(async_test_session)
    expired = await _create_expired_pending_reservation(async_test_session, gateway_key)
    provider_reservation, provider_ledger = await _create_provider_completed_recovery(
        async_test_session,
        gateway_key,
    )
    service = _reconciliation_service(async_test_session)

    expired_dry_run = await service.reconcile_expired_pending_reservations(
        now=datetime.now(UTC),
        dry_run=True,
    )
    provider_dry_run = await service.reconcile_provider_completed_recovery(
        usage_ledger_id=provider_ledger.id,
        dry_run=True,
    )
    await _assert_reservation_status(async_test_session, expired.id, "pending")
    await _assert_usage_status(async_test_session, provider_ledger.id, "failed")
    assert expired_dry_run.reconciled_count == 0
    assert provider_dry_run.reconciled is False

    expired_execute = await service.reconcile_expired_pending_reservations(
        now=datetime.now(UTC),
        dry_run=False,
        reason="operator expired reservation repair",
    )
    expired_execute_again = await service.reconcile_expired_pending_reservations(
        now=datetime.now(UTC),
        dry_run=False,
    )
    assert expired_execute.reconciled_count == 1
    assert expired_execute_again.reconciled_count == 0
    await _assert_reservation_status(async_test_session, expired.id, "expired")

    provider_execute = await service.reconcile_provider_completed_recovery(
        usage_ledger_id=provider_ledger.id,
        dry_run=False,
        reason="operator provider-completed repair",
    )
    assert provider_execute.reconciled is True
    await _assert_reservation_status(async_test_session, provider_reservation.id, "finalized")
    await _assert_usage_status(async_test_session, provider_ledger.id, "finalized")

    with pytest.raises(ProviderCompletedRecoveryAlreadyReconciledError):
        await service.reconcile_provider_completed_recovery(
            usage_ledger_id=provider_ledger.id,
            dry_run=False,
        )

    await _assert_key_counters(
        async_test_session,
        gateway_key.id,
        reserved_cost=Decimal("0E-9"),
        reserved_tokens=0,
        reserved_requests=0,
        used_cost=Decimal("0.000011000"),
        used_tokens=11,
        used_requests=1,
    )
    assert await _usage_count_for_request(async_test_session, expired.request_id) == 1
    assert await _usage_count_for_request(async_test_session, provider_reservation.request_id) == 1

    rows = (
        await async_test_session.execute(
            select(UsageLedger).where(
                UsageLedger.request_id.in_([expired.request_id, provider_reservation.request_id])
            )
        )
    ).scalars().all()
    audits = (
        await async_test_session.execute(
            select(AuditLog).where(AuditLog.entity_id.in_([expired.id, provider_ledger.id]))
        )
    ).scalars().all()
    assert {audit.action for audit in audits} == {
        "quota_reservation_expired",
        "provider_completed_reconciliation",
    }
    _assert_safe_payload(
        {
            "usage": [
                {
                    "usage_raw": row.usage_raw,
                    "response_metadata": row.response_metadata,
                    "error_message": row.error_message,
                }
                for row in rows
            ],
            "audit": [
                {
                    "action": audit.action,
                    "old_values": audit.old_values,
                    "new_values": audit.new_values,
                    "note": audit.note,
                    "request_id": audit.request_id,
                }
                for audit in audits
            ],
        }
    )


@pytest.mark.asyncio
async def test_postgres_scheduled_reconciliation_task_invariants(
    migrated_postgres_url: str,
) -> None:
    engine = create_async_engine(migrated_postgres_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory.begin() as session:
            gateway_key = await _create_gateway_key(session)
            expired = await _create_expired_pending_reservation(session, gateway_key)
            provider_reservation, provider_ledger = await _create_provider_completed_recovery(
                session,
                gateway_key,
            )
            gateway_key_id = gateway_key.id
            expired_id = expired.id
            provider_reservation_id = provider_reservation.id
            provider_request_id = provider_reservation.request_id
            expired_request_id = expired.request_id
            provider_ledger_id = provider_ledger.id

        inspect_result = await tasks_reconciliation._inspect_reconciliation_backlog(
            settings=Settings(
                DATABASE_URL=migrated_postgres_url,
                RECONCILIATION_EXPIRED_RESERVATION_LIMIT=100,
                RECONCILIATION_PROVIDER_COMPLETED_LIMIT=100,
                RECONCILIATION_PROVIDER_COMPLETED_OLDER_THAN_SECONDS=0,
            )
        )
        _assert_safe_payload(inspect_result)
        assert str(expired_id) in inspect_result["expired_reservations"]["reservation_ids"]
        assert str(provider_ledger_id) in inspect_result["provider_completed"]["usage_ledger_ids"]

        async with session_factory() as session:
            before = await _key_counter_tuple(session, gateway_key_id)
            await _assert_reservation_status(session, expired_id, "pending")
            await _assert_usage_status(session, provider_ledger_id, "failed")

        expired_default = await tasks_reconciliation._reconcile_expired_reservations(
            settings=Settings(
                DATABASE_URL=migrated_postgres_url,
                RECONCILIATION_DRY_RUN=False,
                RECONCILIATION_AUTO_EXECUTE_EXPIRED_RESERVATIONS=False,
            ),
            dry_run=False,
        )
        provider_default = await tasks_reconciliation._reconcile_provider_completed(
            settings=Settings(
                DATABASE_URL=migrated_postgres_url,
                RECONCILIATION_DRY_RUN=False,
                RECONCILIATION_AUTO_EXECUTE_PROVIDER_COMPLETED=False,
                RECONCILIATION_PROVIDER_COMPLETED_OLDER_THAN_SECONDS=0,
            ),
            dry_run=False,
        )
        assert expired_default["dry_run"] is True
        assert provider_default["dry_run"] is True
        _assert_safe_payload({"expired_default": expired_default, "provider_default": provider_default})

        async with session_factory() as session:
            assert await _key_counter_tuple(session, gateway_key_id) == before
            await _assert_reservation_status(session, expired_id, "pending")
            await _assert_usage_status(session, provider_ledger_id, "failed")

        expired_execute = await tasks_reconciliation._reconcile_expired_reservations(
            settings=Settings(
                DATABASE_URL=migrated_postgres_url,
                RECONCILIATION_DRY_RUN=False,
                RECONCILIATION_AUTO_EXECUTE_EXPIRED_RESERVATIONS=True,
            ),
            dry_run=False,
            reason="scheduled expired reservation repair",
        )
        provider_execute = await tasks_reconciliation._reconcile_provider_completed(
            settings=Settings(
                DATABASE_URL=migrated_postgres_url,
                RECONCILIATION_DRY_RUN=False,
                RECONCILIATION_AUTO_EXECUTE_PROVIDER_COMPLETED=True,
                RECONCILIATION_PROVIDER_COMPLETED_OLDER_THAN_SECONDS=0,
            ),
            dry_run=False,
            reason="scheduled provider-completed repair",
        )
        _assert_safe_payload({"expired_execute": expired_execute, "provider_execute": provider_execute})
        assert expired_execute["dry_run"] is False
        assert provider_execute["dry_run"] is False

        expired_execute_again = await tasks_reconciliation._reconcile_expired_reservations(
            settings=Settings(
                DATABASE_URL=migrated_postgres_url,
                RECONCILIATION_DRY_RUN=False,
                RECONCILIATION_AUTO_EXECUTE_EXPIRED_RESERVATIONS=True,
            ),
            dry_run=False,
        )
        provider_execute_again = await tasks_reconciliation._reconcile_provider_completed(
            settings=Settings(
                DATABASE_URL=migrated_postgres_url,
                RECONCILIATION_DRY_RUN=False,
                RECONCILIATION_AUTO_EXECUTE_PROVIDER_COMPLETED=True,
                RECONCILIATION_PROVIDER_COMPLETED_OLDER_THAN_SECONDS=0,
            ),
            dry_run=False,
        )
        assert expired_execute_again["reconciled_count"] == 0
        assert provider_execute_again["reconciled_count"] == 0

        async with session_factory() as session:
            await _assert_reservation_status(session, expired_id, "expired")
            await _assert_reservation_status(session, provider_reservation_id, "finalized")
            await _assert_usage_status(session, provider_ledger_id, "finalized")
            assert await _usage_count_for_request(session, provider_request_id) == 1
            await _assert_key_counters(
                session,
                gateway_key_id,
                reserved_cost=Decimal("0E-9"),
                reserved_tokens=0,
                reserved_requests=0,
                used_cost=Decimal("0.000011000"),
                used_tokens=11,
                used_requests=1,
            )
            task_payload = await _safe_database_payload(
                session,
                request_ids=(expired_request_id, provider_request_id),
                entity_ids=(expired_id, provider_ledger_id),
            )
            _assert_safe_payload(task_payload)
    finally:
        await engine.dispose()


async def _create_gateway_key(session: AsyncSession) -> GatewayKey:
    owner = await OwnersRepository(session).create_owner(
        name="Invariant",
        surname="Tester",
        email=f"invariant-{uuid.uuid4()}@example.test",
    )
    now = datetime.now(UTC)
    return await GatewayKeysRepository(session).create_gateway_key_record(
        public_key_id=f"k_{uuid.uuid4().hex}",
        token_hash=f"hash-{uuid.uuid4().hex}",
        owner_id=owner.id,
        valid_from=now - timedelta(minutes=5),
        valid_until=now + timedelta(hours=1),
        cost_limit_eur=Decimal("10.000000000"),
        token_limit_total=10_000,
        request_limit_total=100,
        allow_all_models=True,
        allow_all_endpoints=True,
    )


def _auth(row: GatewayKey) -> AuthenticatedGatewayKey:
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
        estimated_message_input_tokens=5,
        estimated_non_message_input_tokens=max(0, input_tokens - 5),
        estimated_non_message_input_bytes=max(0, input_tokens - 5),
        estimated_non_message_input_fields=("response_format",) if input_tokens > 5 else (),
        injected_default_output_tokens=False,
    )


def _estimate(input_tokens: int = 20, output_tokens: int = 30) -> ChatCostEstimate:
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


def _response(prompt_tokens: int = 10, completion_tokens: int = 15) -> ProviderResponse:
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
                "prompt": PROMPT_TEXT,
                "completion": COMPLETION_TEXT,
                "raw_request_body": RAW_REQUEST_TEXT,
                "raw_response_body": RAW_RESPONSE_TEXT,
                "provider_key": PROVIDER_KEY,
            },
        ),
    )


def _quota_service(session: AsyncSession) -> QuotaService:
    return QuotaService(
        gateway_keys_repository=GatewayKeysRepository(session),
        quota_reservations_repository=QuotaReservationsRepository(session),
    )


def _accounting_service(session: AsyncSession) -> AccountingService:
    return AccountingService(
        gateway_keys_repository=GatewayKeysRepository(session),
        quota_reservations_repository=QuotaReservationsRepository(session),
        usage_ledger_repository=UsageLedgerRepository(session),
    )


def _reconciliation_service(session: AsyncSession) -> ReservationReconciliationService:
    return ReservationReconciliationService(
        gateway_keys_repository=GatewayKeysRepository(session),
        quota_reservations_repository=QuotaReservationsRepository(session),
        usage_ledger_repository=UsageLedgerRepository(session),
        audit_repository=AuditRepository(session),
    )


async def _create_expired_pending_reservation(
    session: AsyncSession,
    gateway_key: GatewayKey,
) -> QuotaReservation:
    reservation = await QuotaReservationsRepository(session).create_reservation(
        gateway_key_id=gateway_key.id,
        request_id=f"req-expired-{uuid.uuid4()}",
        endpoint="/v1/chat/completions",
        requested_model="gpt-test-mini",
        reserved_cost_eur=Decimal("0.300000000"),
        reserved_tokens=200,
        reserved_requests=1,
        status="pending",
        expires_at=datetime.now(UTC) - timedelta(minutes=5),
    )
    await GatewayKeysRepository(session).add_reserved_counters(
        gateway_key,
        cost_reserved_eur=reservation.reserved_cost_eur,
        tokens_reserved_total=reservation.reserved_tokens,
        requests_reserved_total=reservation.reserved_requests,
    )
    return reservation


async def _create_provider_completed_recovery(
    session: AsyncSession,
    gateway_key: GatewayKey,
) -> tuple[QuotaReservation, UsageLedger]:
    request_id = f"req-provider-completed-{uuid.uuid4()}"
    reservation = await QuotaReservationsRepository(session).create_reservation(
        gateway_key_id=gateway_key.id,
        request_id=request_id,
        endpoint="/v1/chat/completions",
        requested_model="gpt-test-mini",
        reserved_cost_eur=Decimal("0.300000000"),
        reserved_tokens=200,
        reserved_requests=1,
        status="pending",
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )
    await GatewayKeysRepository(session).add_reserved_counters(
        gateway_key,
        cost_reserved_eur=reservation.reserved_cost_eur,
        tokens_reserved_total=reservation.reserved_tokens,
        requests_reserved_total=reservation.reserved_requests,
    )
    ledger = await UsageLedgerRepository(session).create_usage_record(
        request_id=request_id,
        quota_reservation_id=reservation.id,
        gateway_key_id=gateway_key.id,
        endpoint="chat.completions",
        provider="openai",
        requested_model="gpt-test-mini",
        resolved_model="gpt-test-mini",
        upstream_request_id="upstream-provider-completed-invariant",
        streaming=True,
        success=None,
        accounting_status="failed",
        http_status=200,
        error_type="accounting_finalization_failed",
        error_message="accounting_finalization_failed",
        prompt_tokens=5,
        completion_tokens=6,
        input_tokens=5,
        output_tokens=6,
        total_tokens=11,
        estimated_cost_eur=Decimal("0.300000000"),
        actual_cost_eur=Decimal("0.000011000"),
        actual_cost_native=Decimal("0.000011000"),
        native_currency="EUR",
        usage_raw={
            "prompt_tokens": 5,
            "completion_tokens": 6,
            "total_tokens": 11,
            "prompt": PROMPT_TEXT,
            "completion": COMPLETION_TEXT,
            "raw_request_body": RAW_REQUEST_TEXT,
            "raw_response_body": RAW_RESPONSE_TEXT,
            "provider_key": PROVIDER_KEY,
        },
        response_metadata={
            "needs_reconciliation": True,
            "recovery_state": "provider_completed_finalization_failed",
            "prompt": PROMPT_TEXT,
            "completion": COMPLETION_TEXT,
            "raw_request_body": RAW_REQUEST_TEXT,
            "raw_response_body": RAW_RESPONSE_TEXT,
            "token_hash": TOKEN_HASH,
            "encrypted_payload": ENCRYPTED_PAYLOAD,
            "nonce": NONCE,
            "password_hash": PASSWORD_HASH,
            "session_token": SESSION_TOKEN,
        },
        started_at=datetime.now(UTC) - timedelta(seconds=2),
        finished_at=datetime.now(UTC),
        latency_ms=2000,
    )
    return reservation, ledger


async def _assert_key_counters(
    session: AsyncSession,
    gateway_key_id: uuid.UUID,
    *,
    reserved_cost: Decimal,
    reserved_tokens: int,
    reserved_requests: int,
    used_cost: Decimal,
    used_tokens: int,
    used_requests: int,
) -> None:
    key = await session.get(GatewayKey, gateway_key_id)
    assert key is not None
    await session.refresh(key)
    assert key.cost_reserved_eur == reserved_cost
    assert key.tokens_reserved_total == reserved_tokens
    assert key.requests_reserved_total == reserved_requests
    assert key.cost_used_eur == used_cost
    assert key.tokens_used_total == used_tokens
    assert key.requests_used_total == used_requests
    assert key.cost_reserved_eur >= Decimal("0")
    assert key.tokens_reserved_total >= 0
    assert key.requests_reserved_total >= 0
    assert key.cost_used_eur >= Decimal("0")
    assert key.tokens_used_total >= 0
    assert key.requests_used_total >= 0


async def _key_counter_tuple(session: AsyncSession, gateway_key_id: uuid.UUID) -> tuple[object, ...]:
    key = await session.get(GatewayKey, gateway_key_id)
    assert key is not None
    return (
        key.cost_reserved_eur,
        key.tokens_reserved_total,
        key.requests_reserved_total,
        key.cost_used_eur,
        key.tokens_used_total,
        key.requests_used_total,
    )


async def _assert_reservation_status(
    session: AsyncSession,
    reservation_id: uuid.UUID,
    status: str,
) -> None:
    reservation = await session.get(QuotaReservation, reservation_id)
    assert reservation is not None
    assert reservation.status == status


async def _assert_usage_status(session: AsyncSession, usage_ledger_id: uuid.UUID, status: str) -> None:
    usage = await session.get(UsageLedger, usage_ledger_id)
    assert usage is not None
    assert usage.accounting_status == status


async def _usage_count_for_request(session: AsyncSession, request_id: str) -> int:
    return (
        await session.execute(
            select(func.count()).select_from(UsageLedger).where(UsageLedger.request_id == request_id)
        )
    ).scalar_one()


async def _usage_for_request(session: AsyncSession, request_id: str) -> UsageLedger:
    row = (
        await session.execute(select(UsageLedger).where(UsageLedger.request_id == request_id))
    ).scalar_one()
    return row


async def _safe_database_payload(
    session: AsyncSession,
    *,
    request_ids: tuple[str, ...],
    entity_ids: tuple[uuid.UUID, ...],
) -> dict[str, object]:
    usage_rows = (
        await session.execute(select(UsageLedger).where(UsageLedger.request_id.in_(request_ids)))
    ).scalars().all()
    audit_rows = (
        await session.execute(select(AuditLog).where(AuditLog.entity_id.in_(entity_ids)))
    ).scalars().all()
    return {
        "usage": [
            {
                "usage_raw": row.usage_raw,
                "response_metadata": row.response_metadata,
                "error_message": row.error_message,
            }
            for row in usage_rows
        ],
        "audit": [
            {
                "action": row.action,
                "old_values": row.old_values,
                "new_values": row.new_values,
                "note": row.note,
                "request_id": row.request_id,
            }
            for row in audit_rows
        ],
    }


def _assert_safe_payload(payload: object) -> None:
    serialized = json.dumps(payload, sort_keys=True, default=str)
    for forbidden in SAFE_FORBIDDEN_TERMS:
        assert forbidden not in serialized
