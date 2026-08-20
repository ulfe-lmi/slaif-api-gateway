"""PostgreSQL proof for durable external-tool hold placement/reconciliation."""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta
from dataclasses import replace
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from slaif_gateway.db.models import ModelRoute
from slaif_gateway.db.repositories.audit import AuditRepository
from slaif_gateway.db.repositories.admin_users import AdminUsersRepository
from slaif_gateway.db.repositories.keys import GatewayKeysRepository
from slaif_gateway.db.repositories.owners import OwnersRepository
from slaif_gateway.db.repositories.quota import QuotaReservationsRepository
from slaif_gateway.db.repositories.usage import UsageLedgerRepository
from slaif_gateway.schemas.external_tool_fence import (
    ExternalToolFenceAcquireInput,
    ExternalToolFenceRouteFacts,
)
from slaif_gateway.schemas.external_tool_hold import (
    ExternalToolAccountingHoldInput,
    ExternalToolHoldAction,
    ExternalToolHoldEvidenceQuality,
    ExternalToolHoldReasonCode,
    ExternalToolHoldReconciliationInput,
)
from slaif_gateway.services.external_tool_fence import ExternalToolFenceService
from slaif_gateway.services.external_tool_hold import (
    ExternalToolAccountingHoldInvariantError,
    ExternalToolAccountingHoldService,
)
from slaif_gateway.services.external_tool_fence import (
    ExternalToolFenceConflictError,
    ExternalToolFenceExhaustedError,
)
from slaif_gateway.services.reservation_reconciliation import ReservationReconciliationService
from slaif_gateway.services.external_tool_policy_contract import ExternalToolAdmissionDecision
from slaif_gateway.utils.crypto import hmac_sha256_token

pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL is not set; skipping PostgreSQL external tool hold tests.",
)

SECRET = "h" * 48
ROUTE_MODEL = "hold-test-model"
PROVIDER = "openai"
ENDPOINT = "/v1/chat/completions"


def _decision() -> ExternalToolAdmissionDecision:
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


async def _fixture():
    engine = create_async_engine(os.environ["TEST_DATABASE_URL"], pool_pre_ping=True)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    route_id = uuid.uuid4()
    key_id = None
    async with sessions() as session:
        route = ModelRoute(
            id=route_id,
            requested_model=ROUTE_MODEL,
            match_type="exact",
            endpoint=ENDPOINT,
            provider=PROVIDER,
            upstream_model="gpt-test",
        )
        session.add(route)
        owner = await OwnersRepository(session).create_owner(
            name="Hold", surname="Integration", email=f"hold-{uuid.uuid4()}@example.test"
        )
        admin = await AdminUsersRepository(session).create_admin_user(
            email=f"admin-{uuid.uuid4()}@example.test",
            display_name="Hold Admin",
            password_hash="not-used-in-test",
        )
        policy = {
            "version": 1,
            "mode": "external_tool_fenced",
            "allowed_capabilities": ["provider_connector"],
            "allowed_destination_ids": ["connector:demo"],
            "max_provider_tool_calls_per_request": 2,
            "single_request_overrun_acknowledged": True,
        }
        key = await GatewayKeysRepository(session).create_gateway_key_record(
            public_key_id=f"hold_{uuid.uuid4().hex}",
            token_hash=hmac_sha256_token(f"sk-slaif-{uuid.uuid4().hex}", SECRET),
            owner_id=owner.id,
            valid_from=datetime.now(UTC) - timedelta(minutes=1),
            valid_until=datetime.now(UTC) + timedelta(hours=1),
            cost_limit_eur=Decimal("10"),
            token_limit_total=1000,
            request_limit_total=10,
            allow_all_models=True,
            allow_all_endpoints=True,
            metadata_json={"external_tool_policy": policy},
        )
        key_id = key.id
        await session.commit()

    async with sessions() as session:
        fence = ExternalToolFenceService(
            gateway_keys_repository=GatewayKeysRepository(session),
            quota_reservations_repository=QuotaReservationsRepository(session),
            usage_ledger_repository=UsageLedgerRepository(session),
            audit_repository=AuditRepository(session),
        )
        acquired = await fence.acquire(
            ExternalToolFenceAcquireInput(
                gateway_key_id=key_id,
                request_id=f"hold-request-{uuid.uuid4().hex}",
                route=ExternalToolFenceRouteFacts(
                    endpoint=ENDPOINT,
                    requested_model=ROUTE_MODEL,
                    provider=PROVIDER,
                    route_id=route_id,
                ),
                capabilities=("provider_connector",),
                destination_ids=("connector:demo",),
                decision=_decision(),
                now=datetime.now(UTC),
            )
        )
        await session.commit()
        reservation_id = acquired.reservation_id
        request_id = acquired.request_id

    return engine, sessions, key_id, reservation_id, request_id, admin.id


@pytest.mark.asyncio
async def test_hold_placement_is_durable_and_keeps_full_reservation():
    engine, sessions, key_id, reservation_id, request_id, _ = await _fixture()
    try:
        async with sessions() as session:
            service = ExternalToolAccountingHoldService(
                gateway_keys_repository=GatewayKeysRepository(session),
                quota_reservations_repository=QuotaReservationsRepository(session),
                usage_ledger_repository=UsageLedgerRepository(session),
                audit_repository=AuditRepository(session),
            )
            result = await service.place(
                ExternalToolAccountingHoldInput(
                    gateway_key_id=key_id,
                    reservation_id=reservation_id,
                    request_id=request_id,
                    reason_code=ExternalToolHoldReasonCode.MISSING_FINAL_USAGE,
                    evidence_quality=ExternalToolHoldEvidenceQuality.MISSING,
                    streaming=True,
                    now=datetime.now(UTC),
                )
            )
            await session.commit()
            assert result.fence_state == "held"
            assert result.accounting_status == "interrupted"

        async with sessions() as session:
            service = ExternalToolAccountingHoldService(
                gateway_keys_repository=GatewayKeysRepository(session),
                quota_reservations_repository=QuotaReservationsRepository(session),
                usage_ledger_repository=UsageLedgerRepository(session),
                audit_repository=AuditRepository(session),
            )
            candidates = await service.list_holds(limit=10)
            key = await GatewayKeysRepository(session).get_gateway_key_by_id(key_id)
            reservation = await QuotaReservationsRepository(session).get_reservation_by_id(reservation_id)
            ledgers = await UsageLedgerRepository(session).get_usage_records_by_reservation_id(reservation_id)
            assert key is not None and key.external_tool_fence_state == "held"
            assert reservation is not None and reservation.status == "pending"
            assert key.cost_reserved_eur == reservation.reserved_cost_eur
            assert len(ledgers) == 1 and ledgers[0].accounting_status == "interrupted"
            assert len(candidates) == 1
            await session.commit()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_finalize_actual_charged_failure_clears_and_exact_repeat_is_idempotent():
    engine, sessions, key_id, reservation_id, request_id, actor = await _fixture()
    try:
        async with sessions() as session:
            service = ExternalToolAccountingHoldService(
                gateway_keys_repository=GatewayKeysRepository(session),
                quota_reservations_repository=QuotaReservationsRepository(session),
                usage_ledger_repository=UsageLedgerRepository(session),
                audit_repository=AuditRepository(session),
            )
            await service.place(
                ExternalToolAccountingHoldInput(
                    gateway_key_id=key_id,
                    reservation_id=reservation_id,
                    request_id=request_id,
                    reason_code=ExternalToolHoldReasonCode.AMBIGUOUS_FINAL_COST,
                    evidence_quality=ExternalToolHoldEvidenceQuality.AMBIGUOUS,
                    streaming=False,
                    now=datetime.now(UTC),
                    partial_total_tokens=20,
                    estimated_cost_eur=Decimal("1"),
                )
            )
            await session.commit()
        request = ExternalToolHoldReconciliationInput(
            reservation_id=reservation_id,
            action=ExternalToolHoldAction.FINALIZE_ACTUAL,
            execute=True,
            actor_admin_id=actor,
            reason="provider charged failed request",
            actual_cost_eur=Decimal("2.25"),
            actual_total_tokens=25,
            success=False,
        )
        async with sessions() as session:
            service = ExternalToolAccountingHoldService(
                gateway_keys_repository=GatewayKeysRepository(session),
                quota_reservations_repository=QuotaReservationsRepository(session),
                usage_ledger_repository=UsageLedgerRepository(session),
                audit_repository=AuditRepository(session),
            )
            result = await service.reconcile(request)
            await session.commit()
            assert result.accounting_status == "finalized"
        async with sessions() as session:
            service = ExternalToolAccountingHoldService(
                gateway_keys_repository=GatewayKeysRepository(session),
                quota_reservations_repository=QuotaReservationsRepository(session),
                usage_ledger_repository=UsageLedgerRepository(session),
                audit_repository=AuditRepository(session),
            )
            repeated = await service.reconcile(request)
            await session.commit()
            assert repeated.idempotent is True
            key = await GatewayKeysRepository(session).get_gateway_key_by_id(key_id)
            assert key is not None and key.external_tool_fence_state == "none"
            assert key.cost_used_eur == Decimal("2.25")
            assert key.tokens_used_total == 25
    finally:
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("reason_code", "evidence_quality", "partial_total_tokens", "estimated_cost_eur", "status"),
    [
        (ExternalToolHoldReasonCode.MISSING_FINAL_USAGE, ExternalToolHoldEvidenceQuality.MISSING, None, None, "interrupted"),
        (ExternalToolHoldReasonCode.MISSING_FINAL_COST, ExternalToolHoldEvidenceQuality.PARTIAL_ESTIMATE, 0, None, "estimated"),
        (ExternalToolHoldReasonCode.AMBIGUOUS_FINAL_COST, ExternalToolHoldEvidenceQuality.AMBIGUOUS, None, Decimal("0.25"), "estimated"),
        (ExternalToolHoldReasonCode.INTERRUPTION_DISCONNECT, ExternalToolHoldEvidenceQuality.PARTIAL_ESTIMATE, 12, Decimal("0.3"), "estimated"),
        (ExternalToolHoldReasonCode.PROVIDER_ERROR_UNKNOWN_CHARGE, ExternalToolHoldEvidenceQuality.MISSING, None, None, "interrupted"),
    ],
)
async def test_all_canonical_hold_reasons_and_evidence_statuses_are_durable(
    reason_code,
    evidence_quality,
    partial_total_tokens,
    estimated_cost_eur,
    status,
):
    engine, sessions, key_id, reservation_id, request_id, _ = await _fixture()
    try:
        async with sessions() as session:
            result = await ExternalToolAccountingHoldService(
                gateway_keys_repository=GatewayKeysRepository(session),
                quota_reservations_repository=QuotaReservationsRepository(session),
                usage_ledger_repository=UsageLedgerRepository(session),
                audit_repository=AuditRepository(session),
            ).place(
                ExternalToolAccountingHoldInput(
                    gateway_key_id=key_id,
                    reservation_id=reservation_id,
                    request_id=request_id,
                    reason_code=reason_code,
                    evidence_quality=evidence_quality,
                    streaming=False,
                    now=datetime.now(UTC),
                    partial_total_tokens=partial_total_tokens,
                    estimated_cost_eur=estimated_cost_eur,
                )
            )
            await session.commit()
            assert result.accounting_status == status
            assert result.reason_code == reason_code.value
            if partial_total_tokens is not None:
                assert result.partial_total_tokens == partial_total_tokens
            assert result.estimated_cost_eur == estimated_cost_eur
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_rolled_back_hold_has_no_ledger_fence_counters_or_audit():
    engine, sessions, key_id, reservation_id, request_id, _ = await _fixture()
    try:
        async with sessions() as session:
            await ExternalToolAccountingHoldService(
                gateway_keys_repository=GatewayKeysRepository(session),
                quota_reservations_repository=QuotaReservationsRepository(session),
                usage_ledger_repository=UsageLedgerRepository(session),
                audit_repository=AuditRepository(session),
            ).place(
                ExternalToolAccountingHoldInput(
                    gateway_key_id=key_id,
                    reservation_id=reservation_id,
                    request_id=request_id,
                    reason_code=ExternalToolHoldReasonCode.MISSING_FINAL_USAGE,
                    evidence_quality=ExternalToolHoldEvidenceQuality.MISSING,
                    streaming=True,
                    now=datetime.now(UTC),
                )
            )
            await session.rollback()

        async with sessions() as session:
            key = await GatewayKeysRepository(session).get_gateway_key_by_id(key_id)
            reservation = await QuotaReservationsRepository(session).get_reservation_by_id(reservation_id)
            ledgers = await UsageLedgerRepository(session).get_usage_records_by_reservation_id(reservation_id)
            audits = await AuditRepository(session).list_audit_logs(
                action="external_tool_accounting_hold_created"
            )
            assert key is not None and key.external_tool_fence_state == "active"
            assert reservation is not None and reservation.status == "pending"
            assert key.cost_reserved_eur == reservation.reserved_cost_eur
            assert key.tokens_reserved_total == reservation.reserved_tokens
            assert key.requests_reserved_total == reservation.reserved_requests
            assert ledgers == []
            assert not any(audit.request_id == request_id for audit in audits)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_hold_survives_engine_restart_expiry_and_ordinary_reconciliation():
    engine, sessions, key_id, reservation_id, request_id, _ = await _fixture()
    try:
        async with sessions() as session:
            service = ExternalToolAccountingHoldService(
                gateway_keys_repository=GatewayKeysRepository(session),
                quota_reservations_repository=QuotaReservationsRepository(session),
                usage_ledger_repository=UsageLedgerRepository(session),
                audit_repository=AuditRepository(session),
            )
            await service.place(
                ExternalToolAccountingHoldInput(
                    gateway_key_id=key_id,
                    reservation_id=reservation_id,
                    request_id=request_id,
                    reason_code=ExternalToolHoldReasonCode.INTERRUPTION_DISCONNECT,
                    evidence_quality=ExternalToolHoldEvidenceQuality.PARTIAL_ESTIMATE,
                    streaming=True,
                    now=datetime.now(UTC),
                    partial_total_tokens=0,
                )
            )
            await session.commit()
        await engine.dispose()

        engine = create_async_engine(os.environ["TEST_DATABASE_URL"], pool_pre_ping=True)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with engine.begin() as connection:
            await connection.execute(
                text("UPDATE quota_reservations SET expires_at = :past WHERE id = :id"),
                {"past": datetime.now(UTC) - timedelta(minutes=1), "id": reservation_id},
            )
        async with sessions() as session:
            summary = await ReservationReconciliationService(
                gateway_keys_repository=GatewayKeysRepository(session),
                quota_reservations_repository=QuotaReservationsRepository(session),
                usage_ledger_repository=UsageLedgerRepository(session),
                audit_repository=AuditRepository(session),
            ).reconcile_expired_pending_reservations(now=datetime.now(UTC))
            await session.commit()
            key = await GatewayKeysRepository(session).get_gateway_key_by_id(key_id)
            reservation = await QuotaReservationsRepository(session).get_reservation_by_id(reservation_id)
            candidates = await ExternalToolAccountingHoldService(
                gateway_keys_repository=GatewayKeysRepository(session),
                quota_reservations_repository=QuotaReservationsRepository(session),
                usage_ledger_repository=UsageLedgerRepository(session),
                audit_repository=AuditRepository(session),
            ).list_holds(limit=10)
            assert summary.reconciled_count == 0
            assert summary.skipped_count >= 1
            assert key is not None and key.external_tool_fence_state == "held"
            assert reservation is not None and reservation.status == "pending"
            matching = [candidate for candidate in candidates if candidate.reservation_id == reservation_id]
            assert len(matching) == 1 and matching[0].partial_total_tokens == 0
    finally:
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mutation",
    [
        "actual_cost_eur",
        "actual_cost_native",
        "usage_raw",
        "wrong_status",
        "wrong_success",
        "extra_metadata",
        "bad_timestamp",
        "naive_timestamp",
        "wrong_endpoint",
        "wrong_provider",
        "wrong_model",
        "wrong_request",
        "wrong_fence_request_pointer",
        "counter_drift",
    ],
)
async def test_corrupt_hold_shapes_are_not_listed_or_retried(mutation):
    engine, sessions, key_id, reservation_id, request_id, _ = await _fixture()
    try:
        hold_input = ExternalToolAccountingHoldInput(
            gateway_key_id=key_id,
            reservation_id=reservation_id,
            request_id=request_id,
            reason_code=ExternalToolHoldReasonCode.MISSING_FINAL_COST,
            evidence_quality=ExternalToolHoldEvidenceQuality.PARTIAL_ESTIMATE,
            streaming=True,
            now=datetime.now(UTC),
            partial_total_tokens=4,
            estimated_cost_eur=Decimal("0.2"),
        )
        async with sessions() as session:
            service = ExternalToolAccountingHoldService(
                gateway_keys_repository=GatewayKeysRepository(session),
                quota_reservations_repository=QuotaReservationsRepository(session),
                usage_ledger_repository=UsageLedgerRepository(session),
                audit_repository=AuditRepository(session),
            )
            await service.place(hold_input)
            await session.commit()
        async with sessions() as session:
            ledger = (await UsageLedgerRepository(session).get_usage_records_by_reservation_id(reservation_id))[0]
            reservation = await QuotaReservationsRepository(session).get_reservation_by_id(reservation_id)
            key = await GatewayKeysRepository(session).get_gateway_key_by_id(key_id)
            if mutation == "actual_cost_eur":
                ledger.actual_cost_eur = Decimal("1")
            elif mutation == "actual_cost_native":
                ledger.actual_cost_native = Decimal("1")
            elif mutation == "usage_raw":
                ledger.usage_raw = {"total_tokens": 4}
            elif mutation == "wrong_status":
                ledger.accounting_status = "failed"
            elif mutation == "wrong_success":
                ledger.success = False
            elif mutation == "extra_metadata":
                ledger.response_metadata = {**ledger.response_metadata, "extra": "unexpected"}
            elif mutation == "bad_timestamp":
                hold = dict(ledger.response_metadata["external_tool_accounting_hold"])
                hold["held_at"] = "not-a-timestamp"
                ledger.response_metadata = {
                    **ledger.response_metadata,
                    "external_tool_accounting_hold": hold,
                }
            elif mutation == "naive_timestamp":
                hold = dict(ledger.response_metadata["external_tool_accounting_hold"])
                hold["held_at"] = "2026-01-01T00:00:00"
                ledger.response_metadata = {
                    **ledger.response_metadata,
                    "external_tool_accounting_hold": hold,
                }
            elif mutation == "wrong_endpoint":
                ledger.endpoint = "/v1/embeddings"
            elif mutation == "wrong_provider":
                ledger.provider = "openrouter"
            elif mutation == "wrong_model":
                ledger.requested_model = "other-model"
            elif mutation == "wrong_request":
                ledger.request_id = "other-request"
            elif mutation == "wrong_fence_request_pointer":
                assert key is not None
                key.external_tool_fence_request_id = "other-request"
            else:
                assert key is not None and reservation is not None
                key.cost_reserved_eur += Decimal("1")
            await session.commit()
        async with sessions() as session:
            service = ExternalToolAccountingHoldService(
                gateway_keys_repository=GatewayKeysRepository(session),
                quota_reservations_repository=QuotaReservationsRepository(session),
                usage_ledger_repository=UsageLedgerRepository(session),
                audit_repository=AuditRepository(session),
            )
            assert not any(
                candidate.reservation_id == reservation_id
                for candidate in await service.list_holds(limit=100)
            )
            with pytest.raises(ExternalToolAccountingHoldInvariantError):
                await service.place(hold_input)
            await session.rollback()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("streaming", False),
        ("reason_code", ExternalToolHoldReasonCode.PROVIDER_ERROR_UNKNOWN_CHARGE),
        ("evidence_quality", ExternalToolHoldEvidenceQuality.MISSING),
        ("partial_total_tokens", 1),
        ("estimated_cost_eur", Decimal("0.3")),
    ],
)
async def test_retry_changed_safe_fact_conflicts_and_zero_tokens_project_exactly(field, value):
    engine, sessions, key_id, reservation_id, request_id, _ = await _fixture()
    try:
        initial = ExternalToolAccountingHoldInput(
            gateway_key_id=key_id,
            reservation_id=reservation_id,
            request_id=request_id,
            reason_code=ExternalToolHoldReasonCode.MISSING_FINAL_COST,
            evidence_quality=ExternalToolHoldEvidenceQuality.PARTIAL_ESTIMATE,
            streaming=True,
            now=datetime.now(UTC),
            partial_total_tokens=0,
            estimated_cost_eur=Decimal("0.2"),
        )
        async with sessions() as session:
            service = ExternalToolAccountingHoldService(
                gateway_keys_repository=GatewayKeysRepository(session),
                quota_reservations_repository=QuotaReservationsRepository(session),
                usage_ledger_repository=UsageLedgerRepository(session),
                audit_repository=AuditRepository(session),
            )
            projection = await service.place(initial)
            await session.commit()
            assert projection.partial_total_tokens == 0
        changed = replace(initial, **{field: value})
        async with sessions() as session:
            service = ExternalToolAccountingHoldService(
                gateway_keys_repository=GatewayKeysRepository(session),
                quota_reservations_repository=QuotaReservationsRepository(session),
                usage_ledger_repository=UsageLedgerRepository(session),
                audit_repository=AuditRepository(session),
            )
            with pytest.raises(ExternalToolFenceConflictError):
                await service.place(changed)
            await session.rollback()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("shape", ["zero-ledger", "multiple-ledgers", "active-plus-ledger"])
async def test_hold_requires_exactly_one_held_linked_ledger(shape):
    engine, sessions, key_id, reservation_id, request_id, _ = await _fixture()
    try:
        hold_input = ExternalToolAccountingHoldInput(
            gateway_key_id=key_id,
            reservation_id=reservation_id,
            request_id=request_id,
            reason_code=ExternalToolHoldReasonCode.MISSING_FINAL_COST,
            evidence_quality=ExternalToolHoldEvidenceQuality.MISSING,
            streaming=True,
            now=datetime.now(UTC),
        )
        async with sessions() as session:
            service = ExternalToolAccountingHoldService(
                gateway_keys_repository=GatewayKeysRepository(session),
                quota_reservations_repository=QuotaReservationsRepository(session),
                usage_ledger_repository=UsageLedgerRepository(session),
                audit_repository=AuditRepository(session),
            )
            await service.place(hold_input)
            await session.commit()
        async with sessions() as session:
            usage = UsageLedgerRepository(session)
            ledger = (await usage.get_usage_records_by_reservation_id(reservation_id))[0]
            if shape == "zero-ledger":
                await session.delete(ledger)
            elif shape == "multiple-ledgers":
                await usage.create_usage_record(
                    request_id=f"duplicate-{uuid.uuid4().hex}",
                    gateway_key_id=key_id,
                    endpoint=ledger.endpoint,
                    provider=ledger.provider,
                    requested_model=ledger.requested_model,
                    started_at=ledger.started_at,
                    quota_reservation_id=reservation_id,
                    streaming=ledger.streaming,
                    success=None,
                    accounting_status=ledger.accounting_status,
                    total_tokens=ledger.total_tokens,
                    estimated_cost_eur=ledger.estimated_cost_eur,
                    usage_raw={},
                    response_metadata=ledger.response_metadata,
                )
            else:
                key = await GatewayKeysRepository(session).get_gateway_key_by_id(key_id)
                assert key is not None
                key.external_tool_fence_state = "active"
            await session.commit()
        async with sessions() as session:
            service = ExternalToolAccountingHoldService(
                gateway_keys_repository=GatewayKeysRepository(session),
                quota_reservations_repository=QuotaReservationsRepository(session),
                usage_ledger_repository=UsageLedgerRepository(session),
                audit_repository=AuditRepository(session),
            )
            assert not any(
                candidate.reservation_id == reservation_id
                for candidate in await service.list_holds(limit=100)
            )
            with pytest.raises(ExternalToolAccountingHoldInvariantError):
                await service.place(hold_input)
            await session.rollback()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_dry_run_finalize_and_release_are_non_mutating_and_execute_audited_release():
    engine, sessions, key_id, reservation_id, request_id, actor = await _fixture()
    try:
        async with sessions() as session:
            await ExternalToolAccountingHoldService(
                gateway_keys_repository=GatewayKeysRepository(session),
                quota_reservations_repository=QuotaReservationsRepository(session),
                usage_ledger_repository=UsageLedgerRepository(session),
                audit_repository=AuditRepository(session),
            ).place(
                ExternalToolAccountingHoldInput(
                    gateway_key_id=key_id,
                    reservation_id=reservation_id,
                    request_id=request_id,
                    reason_code=ExternalToolHoldReasonCode.AMBIGUOUS_FINAL_COST,
                    evidence_quality=ExternalToolHoldEvidenceQuality.AMBIGUOUS,
                    streaming=False,
                    now=datetime.now(UTC),
                    partial_total_tokens=3,
                    estimated_cost_eur=Decimal("0.1"),
                )
            )
            await session.commit()
        def service_args(session):
            return ExternalToolAccountingHoldService(
                gateway_keys_repository=GatewayKeysRepository(session),
                quota_reservations_repository=QuotaReservationsRepository(session),
                usage_ledger_repository=UsageLedgerRepository(session),
                audit_repository=AuditRepository(session),
            )
        dry_finalize = ExternalToolHoldReconciliationInput(
            reservation_id=reservation_id,
            action=ExternalToolHoldAction.FINALIZE_ACTUAL,
            execute=False,
            actual_cost_eur=Decimal("0.2"),
            actual_total_tokens=4,
            success=True,
        )
        dry_release = ExternalToolHoldReconciliationInput(
            reservation_id=reservation_id,
            action=ExternalToolHoldAction.RELEASE_NO_CHARGE,
            execute=False,
            confirm_no_charge=True,
        )
        async with sessions() as session:
            assert (await service_args(session).reconcile(dry_finalize)).executed is False
            assert (await service_args(session).reconcile(dry_release)).executed is False
            await session.rollback()
        execute = ExternalToolHoldReconciliationInput(
            reservation_id=reservation_id,
            action=ExternalToolHoldAction.RELEASE_NO_CHARGE,
            execute=True,
            actor_admin_id=actor,
            reason="operator confirmed no charge",
            confirm_no_charge=True,
        )
        async with sessions() as session:
            result = await service_args(session).reconcile(execute)
            await session.commit()
            assert result.accounting_status == "failed"
            assert result.actual_cost_eur == Decimal("0")
            assert result.actual_total_tokens == 0
            assert result.success is False
            audits = await AuditRepository(session).list_audit_logs(
                action="external_tool_accounting_hold_reconciled"
            )
            matching = [audit for audit in audits if audit.request_id == request_id]
            assert len(matching) == 1
            assert matching[0].admin_user_id == actor
            assert matching[0].note == "operator confirmed no charge"
            reservation = await QuotaReservationsRepository(session).get_reservation_by_id(reservation_id)
            assert reservation is not None and reservation.external_tool_route_id is not None
            acquired = await ExternalToolFenceService(
                gateway_keys_repository=GatewayKeysRepository(session),
                quota_reservations_repository=QuotaReservationsRepository(session),
                usage_ledger_repository=UsageLedgerRepository(session),
                audit_repository=AuditRepository(session),
            ).acquire(
                ExternalToolFenceAcquireInput(
                    gateway_key_id=key_id,
                    request_id=f"post-release-{uuid.uuid4().hex}",
                    route=ExternalToolFenceRouteFacts(
                        endpoint=reservation.endpoint,
                        requested_model=reservation.requested_model or ROUTE_MODEL,
                        provider=reservation.external_tool_provider or PROVIDER,
                        route_id=uuid.UUID(str(reservation.external_tool_route_id)),
                    ),
                    capabilities=("provider_connector",),
                    destination_ids=("connector:demo",),
                    decision=_decision(),
                    now=datetime.now(UTC),
                )
            )
            assert acquired.fence_state == "active"
            await session.rollback()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("overrun", [False, True])
async def test_finalize_within_limit_or_overrun_moves_counters_once_and_controls_next_fence(overrun):
    engine, sessions, key_id, reservation_id, request_id, actor = await _fixture()
    try:
        async with sessions() as session:
            service = ExternalToolAccountingHoldService(
                gateway_keys_repository=GatewayKeysRepository(session),
                quota_reservations_repository=QuotaReservationsRepository(session),
                usage_ledger_repository=UsageLedgerRepository(session),
                audit_repository=AuditRepository(session),
            )
            await service.place(
                ExternalToolAccountingHoldInput(
                    gateway_key_id=key_id,
                    reservation_id=reservation_id,
                    request_id=request_id,
                    reason_code=ExternalToolHoldReasonCode.MISSING_FINAL_USAGE,
                    evidence_quality=ExternalToolHoldEvidenceQuality.MISSING,
                    streaming=False,
                    now=datetime.now(UTC),
                )
            )
            await session.commit()
        async with sessions() as session:
            reservation = await QuotaReservationsRepository(session).get_reservation_by_id(reservation_id)
            assert reservation is not None and reservation.external_tool_route_id is not None
            request = ExternalToolHoldReconciliationInput(
                reservation_id=reservation_id,
                action=ExternalToolHoldAction.FINALIZE_ACTUAL,
                execute=True,
                actor_admin_id=actor,
                reason="overrun boundary proof" if overrun else "within boundary proof",
                actual_cost_eur=Decimal("11") if overrun else Decimal("1"),
                actual_total_tokens=1001 if overrun else 10,
                success=True,
            )
            result = await ExternalToolAccountingHoldService(
                gateway_keys_repository=GatewayKeysRepository(session),
                quota_reservations_repository=QuotaReservationsRepository(session),
                usage_ledger_repository=UsageLedgerRepository(session),
                audit_repository=AuditRepository(session),
            ).reconcile(request)
            await session.commit()
            key = await GatewayKeysRepository(session).get_gateway_key_by_id(key_id)
            assert key is not None
            assert result.accounting_status == "finalized"
            assert key.external_tool_fence_state == "none"
            assert key.cost_reserved_eur == Decimal("0")
            assert key.tokens_reserved_total == 0
            assert key.cost_used_eur == (Decimal("11") if overrun else Decimal("1"))
            assert key.tokens_used_total == (1001 if overrun else 10)
            acquire_input = ExternalToolFenceAcquireInput(
                gateway_key_id=key_id,
                request_id=f"post-finalize-{uuid.uuid4().hex}",
                route=ExternalToolFenceRouteFacts(
                    endpoint=reservation.endpoint,
                    requested_model=reservation.requested_model or ROUTE_MODEL,
                    provider=reservation.external_tool_provider or PROVIDER,
                    route_id=uuid.UUID(str(reservation.external_tool_route_id)),
                ),
                capabilities=("provider_connector",),
                destination_ids=("connector:demo",),
                decision=_decision(),
                now=datetime.now(UTC),
            )
            fence = ExternalToolFenceService(
                gateway_keys_repository=GatewayKeysRepository(session),
                quota_reservations_repository=QuotaReservationsRepository(session),
                usage_ledger_repository=UsageLedgerRepository(session),
                audit_repository=AuditRepository(session),
            )
            if overrun:
                with pytest.raises(ExternalToolFenceExhaustedError):
                    await fence.acquire(acquire_input)
            else:
                acquired = await fence.acquire(acquire_input)
                assert acquired.fence_state == "active"
            await session.rollback()
    finally:
        await engine.dispose()
