"""PostgreSQL checks for provider-completed accounting recovery repair."""

from __future__ import annotations

import json
import os
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from slaif_gateway.db.models import AuditLog, UsageLedger
from slaif_gateway.db.repositories.audit import AuditRepository
from slaif_gateway.db.repositories.keys import GatewayKeysRepository
from slaif_gateway.db.repositories.owners import OwnersRepository
from slaif_gateway.db.repositories.quota import QuotaReservationsRepository
from slaif_gateway.db.repositories.usage import UsageLedgerRepository
from slaif_gateway.services.reconciliation_errors import (
    ProviderCompletedRecoveryMetadataMissingError,
    ProviderCompletedRecoveryNotRepairableError,
)
from slaif_gateway.services.reservation_reconciliation import ReservationReconciliationService

pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL is not set; skipping optional PostgreSQL reconciliation tests.",
)

PROMPT_TEXT = "sensitive prompt body"
COMPLETION_TEXT = "sensitive completion body"


async def _create_gateway_key(async_test_session: AsyncSession):
    owner = await OwnersRepository(async_test_session).create_owner(
        name="ProviderCompleted",
        surname="Repair",
        email=f"provider-completed-{uuid.uuid4()}@example.test",
    )
    now = datetime.now(UTC)
    return await GatewayKeysRepository(async_test_session).create_gateway_key_record(
        public_key_id=f"k_{uuid.uuid4().hex}",
        token_hash=f"hash-{uuid.uuid4().hex}",
        owner_id=owner.id,
        valid_from=now - timedelta(minutes=5),
        valid_until=now + timedelta(hours=1),
        cost_limit_eur=Decimal("1.000000000"),
        token_limit_total=1000,
        request_limit_total=10,
        allow_all_models=True,
        allow_all_endpoints=True,
    )


async def _create_provider_completed_recovery(async_test_session: AsyncSession, gateway_key, **ledger_overrides):
    request_id = f"req-provider-completed-{uuid.uuid4()}"
    reservation = await QuotaReservationsRepository(async_test_session).create_reservation(
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
    await GatewayKeysRepository(async_test_session).add_reserved_counters(
        gateway_key,
        cost_reserved_eur=reservation.reserved_cost_eur,
        tokens_reserved_total=reservation.reserved_tokens,
        requests_reserved_total=reservation.reserved_requests,
    )
    ledger_kwargs = {
        "request_id": request_id,
        "quota_reservation_id": reservation.id,
        "gateway_key_id": gateway_key.id,
        "endpoint": "chat.completions",
        "provider": "openai",
        "requested_model": "gpt-test-mini",
        "resolved_model": "gpt-test-mini",
        "upstream_request_id": "upstream-provider-completed-repair",
        "streaming": True,
        "http_status": 200,
        "prompt_tokens": 5,
        "completion_tokens": 6,
        "input_tokens": 5,
        "output_tokens": 6,
        "cached_tokens": 0,
        "reasoning_tokens": 0,
        "total_tokens": 11,
        "estimated_cost_eur": Decimal("0.300000000"),
        "actual_cost_eur": Decimal("0.000011000"),
        "actual_cost_native": Decimal("0.000011000"),
        "native_currency": "EUR",
        "usage_raw": {"prompt_tokens": 5, "completion_tokens": 6, "total_tokens": 11},
        "response_metadata": {
            "needs_reconciliation": True,
            "recovery_state": "provider_completed_finalization_failed",
            "prompt": PROMPT_TEXT,
            "completion": COMPLETION_TEXT,
        },
        "started_at": datetime.now(UTC) - timedelta(seconds=2),
        "finished_at": datetime.now(UTC),
        "latency_ms": 2000,
    }
    ledger_kwargs.update(ledger_overrides)
    ledger = await UsageLedgerRepository(async_test_session).create_usage_record(
        success=None,
        accounting_status="failed",
        error_type="accounting_finalization_failed",
        error_message="accounting_finalization_failed",
        **ledger_kwargs,
    )
    return reservation, ledger


def _service(async_test_session: AsyncSession) -> ReservationReconciliationService:
    return ReservationReconciliationService(
        gateway_keys_repository=GatewayKeysRepository(async_test_session),
        quota_reservations_repository=QuotaReservationsRepository(async_test_session),
        usage_ledger_repository=UsageLedgerRepository(async_test_session),
        audit_repository=AuditRepository(async_test_session),
    )


@pytest.mark.asyncio
async def test_postgres_provider_completed_recovery_dry_run_and_execute(
    async_test_session: AsyncSession,
) -> None:
    gateway_key = await _create_gateway_key(async_test_session)
    reservation, ledger = await _create_provider_completed_recovery(async_test_session, gateway_key)
    service = _service(async_test_session)

    dry_run = await service.reconcile_provider_completed_recovery(
        usage_ledger_id=ledger.id,
        dry_run=True,
    )
    await async_test_session.refresh(gateway_key)
    await async_test_session.refresh(reservation)
    await async_test_session.refresh(ledger)

    assert dry_run.reconciled is False
    assert reservation.status == "pending"
    assert gateway_key.cost_reserved_eur == Decimal("0.300000000")
    assert gateway_key.cost_used_eur == Decimal("0E-9")
    assert ledger.accounting_status == "failed"
    assert ledger.response_metadata["needs_reconciliation"] is True

    executed = await service.reconcile_provider_completed_recovery(
        usage_ledger_id=ledger.id,
        dry_run=False,
        reason="operator repair",
    )
    await async_test_session.refresh(gateway_key)
    await async_test_session.refresh(reservation)
    await async_test_session.refresh(ledger)

    assert executed.reconciled is True
    assert executed.new_accounting_status == "finalized"
    assert reservation.status == "finalized"
    assert reservation.finalized_at is not None
    assert gateway_key.cost_reserved_eur == Decimal("0E-9")
    assert gateway_key.tokens_reserved_total == 0
    assert gateway_key.requests_reserved_total == 0
    assert gateway_key.cost_used_eur == Decimal("0.000011000")
    assert gateway_key.tokens_used_total == 11
    assert gateway_key.requests_used_total == 1
    assert ledger.success is True
    assert ledger.accounting_status == "finalized"
    assert ledger.error_type is None
    assert ledger.response_metadata["needs_reconciliation"] is False
    assert ledger.response_metadata["recovery_state"] == "provider_completed_reconciled"
    assert ledger.response_metadata["reconciliation_reason"] == "operator repair"

    ledger_count = (
        await async_test_session.execute(
            select(func.count()).select_from(UsageLedger).where(UsageLedger.request_id == reservation.request_id)
        )
    ).scalar_one()
    assert ledger_count == 1

    audit = (
        await async_test_session.execute(
            select(AuditLog).where(AuditLog.entity_id == ledger.id)
        )
    ).scalar_one()
    assert audit.action == "provider_completed_reconciliation"
    assert audit.request_id == reservation.request_id
    assert audit.note == "operator repair"

    usage_payload = json.dumps(ledger.usage_raw, sort_keys=True)
    metadata_payload = json.dumps(ledger.response_metadata, sort_keys=True)
    assert PROMPT_TEXT not in usage_payload
    assert COMPLETION_TEXT not in usage_payload
    assert PROMPT_TEXT not in metadata_payload
    assert COMPLETION_TEXT not in metadata_payload


@pytest.mark.asyncio
async def test_postgres_provider_completed_recovery_missing_metadata_fails_closed(
    async_test_session: AsyncSession,
) -> None:
    gateway_key = await _create_gateway_key(async_test_session)
    reservation, ledger = await _create_provider_completed_recovery(
        async_test_session,
        gateway_key,
        actual_cost_eur=None,
    )

    with pytest.raises(ProviderCompletedRecoveryMetadataMissingError):
        await _service(async_test_session).reconcile_provider_completed_recovery(
            usage_ledger_id=ledger.id,
            dry_run=False,
        )

    await async_test_session.refresh(gateway_key)
    await async_test_session.refresh(reservation)
    await async_test_session.refresh(ledger)
    assert reservation.status == "pending"
    assert gateway_key.cost_reserved_eur == Decimal("0.300000000")
    assert gateway_key.cost_used_eur == Decimal("0E-9")
    assert ledger.accounting_status == "failed"
    assert ledger.response_metadata["needs_reconciliation"] is True


@pytest.mark.asyncio
async def test_postgres_provider_completed_recovery_non_pending_reservation_fails_safely(
    async_test_session: AsyncSession,
) -> None:
    gateway_key = await _create_gateway_key(async_test_session)
    reservation, ledger = await _create_provider_completed_recovery(async_test_session, gateway_key)
    reservation.status = "finalized"
    reservation.finalized_at = datetime.now(UTC)
    await async_test_session.flush()

    with pytest.raises(ProviderCompletedRecoveryNotRepairableError):
        await _service(async_test_session).reconcile_provider_completed_recovery(
            usage_ledger_id=ledger.id,
            dry_run=False,
        )

    await async_test_session.refresh(gateway_key)
    await async_test_session.refresh(ledger)
    assert gateway_key.cost_used_eur == Decimal("0E-9")
    assert gateway_key.cost_reserved_eur == Decimal("0.300000000")
    assert ledger.accounting_status == "failed"
    assert ledger.response_metadata["needs_reconciliation"] is True
