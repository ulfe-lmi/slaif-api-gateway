"""Optional PostgreSQL checks for stale quota reservation reconciliation."""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from slaif_gateway.db.models import AuditLog, UsageLedger
from slaif_gateway.db.repositories.audit import AuditRepository
from slaif_gateway.db.repositories.keys import GatewayKeysRepository
from slaif_gateway.db.repositories.owners import OwnersRepository
from slaif_gateway.db.repositories.quota import QuotaReservationsRepository
from slaif_gateway.db.repositories.usage import UsageLedgerRepository
from slaif_gateway.services.reconciliation_errors import ReservationNotExpiredError
from slaif_gateway.services.reservation_reconciliation import ReservationReconciliationService

pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL is not set; skipping optional PostgreSQL reconciliation tests.",
)


async def _create_gateway_key(async_test_session: AsyncSession):
    owner = await OwnersRepository(async_test_session).create_owner(
        name="Reconciliation",
        surname="Tester",
        email=f"reconcile-{uuid.uuid4()}@example.test",
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


async def _create_pending_reservation(
    async_test_session: AsyncSession,
    gateway_key,
    *,
    expires_at: datetime,
):
    reservation = await QuotaReservationsRepository(async_test_session).create_reservation(
        gateway_key_id=gateway_key.id,
        request_id=f"req-{uuid.uuid4()}",
        endpoint="/v1/chat/completions",
        requested_model="gpt-test-mini",
        reserved_cost_eur=Decimal("0.300000000"),
        reserved_tokens=200,
        reserved_requests=1,
        status="pending",
        expires_at=expires_at,
    )
    await GatewayKeysRepository(async_test_session).add_reserved_counters(
        gateway_key,
        cost_reserved_eur=reservation.reserved_cost_eur,
        tokens_reserved_total=reservation.reserved_tokens,
        requests_reserved_total=reservation.reserved_requests,
    )
    return reservation


def _service(async_test_session: AsyncSession) -> ReservationReconciliationService:
    return ReservationReconciliationService(
        gateway_keys_repository=GatewayKeysRepository(async_test_session),
        quota_reservations_repository=QuotaReservationsRepository(async_test_session),
        usage_ledger_repository=UsageLedgerRepository(async_test_session),
        audit_repository=AuditRepository(async_test_session),
    )


@pytest.mark.asyncio
async def test_postgres_reconciles_expired_pending_reservation(
    async_test_session: AsyncSession,
) -> None:
    gateway_key = await _create_gateway_key(async_test_session)
    now = datetime.now(UTC)
    reservation = await _create_pending_reservation(
        async_test_session,
        gateway_key,
        expires_at=now - timedelta(minutes=1),
    )
    service = _service(async_test_session)

    dry_run = await service.reconcile_expired_pending_reservation(
        reservation.id,
        now=now,
        dry_run=True,
    )
    await async_test_session.refresh(gateway_key)
    await async_test_session.refresh(reservation)

    assert dry_run.dry_run is True
    assert reservation.status == "pending"
    assert gateway_key.cost_reserved_eur == Decimal("0.300000000")
    assert gateway_key.tokens_reserved_total == 200
    assert gateway_key.requests_reserved_total == 1

    executed = await service.reconcile_expired_pending_reservation(
        reservation.id,
        now=now,
        reason="integration repair",
    )
    await async_test_session.refresh(gateway_key)
    await async_test_session.refresh(reservation)

    assert executed.new_status == "expired"
    assert executed.ledger_created is True
    assert executed.audit_created is True
    assert reservation.status == "expired"
    assert reservation.released_at is not None
    assert gateway_key.cost_reserved_eur == Decimal("0E-9")
    assert gateway_key.tokens_reserved_total == 0
    assert gateway_key.requests_reserved_total == 0
    assert gateway_key.cost_used_eur == Decimal("0E-9")
    assert gateway_key.tokens_used_total == 0
    assert gateway_key.requests_used_total == 0

    ledger = (
        await async_test_session.execute(
            select(UsageLedger).where(UsageLedger.request_id == reservation.request_id)
        )
    ).scalar_one()
    assert ledger.success is False
    assert ledger.accounting_status == "failed"
    assert ledger.error_type == "stale_quota_reservation"
    assert ledger.actual_cost_eur == Decimal("0E-9")
    assert ledger.prompt_tokens == 0
    assert ledger.completion_tokens == 0
    assert ledger.response_metadata == {"reconciled_status": "expired"}

    audit = (
        await async_test_session.execute(
            select(AuditLog).where(AuditLog.entity_id == reservation.id)
        )
    ).scalar_one()
    assert audit.action == "quota_reservation_expired"
    assert audit.request_id == reservation.request_id
    assert audit.note == "integration repair"


@pytest.mark.asyncio
async def test_postgres_non_expired_pending_reservation_is_not_reconciled(
    async_test_session: AsyncSession,
) -> None:
    gateway_key = await _create_gateway_key(async_test_session)
    now = datetime.now(UTC)
    reservation = await _create_pending_reservation(
        async_test_session,
        gateway_key,
        expires_at=now + timedelta(minutes=10),
    )

    with pytest.raises(ReservationNotExpiredError):
        await _service(async_test_session).reconcile_expired_pending_reservation(
            reservation.id,
            now=now,
        )

    await async_test_session.refresh(gateway_key)
    await async_test_session.refresh(reservation)
    assert reservation.status == "pending"
    assert gateway_key.cost_reserved_eur == Decimal("0.300000000")
