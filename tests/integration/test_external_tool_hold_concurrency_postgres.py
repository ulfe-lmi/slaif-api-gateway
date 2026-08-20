"""Concurrent PostgreSQL reconciliation proof for objective 015."""

from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from slaif_gateway.db.repositories.audit import AuditRepository
from slaif_gateway.db.repositories.keys import GatewayKeysRepository
from slaif_gateway.db.repositories.quota import QuotaReservationsRepository
from slaif_gateway.db.repositories.usage import UsageLedgerRepository
from slaif_gateway.schemas.external_tool_hold import (
    ExternalToolAccountingHoldInput,
    ExternalToolHoldAction,
    ExternalToolHoldEvidenceQuality,
    ExternalToolHoldReasonCode,
    ExternalToolHoldReconciliationInput,
)
from slaif_gateway.services.external_tool_hold import ExternalToolAccountingHoldService
from tests.integration.test_external_tool_hold_postgres import _fixture

pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL is not set; skipping PostgreSQL external tool hold concurrency tests.",
)


@pytest.mark.asyncio
async def test_eight_workers_have_one_mutation_and_seven_exact_retries():
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
                    reason_code=ExternalToolHoldReasonCode.MISSING_FINAL_COST,
                    evidence_quality=ExternalToolHoldEvidenceQuality.MISSING,
                    streaming=True,
                    now=datetime.now(UTC),
                )
            )
            await session.commit()

        request = ExternalToolHoldReconciliationInput(
            reservation_id=reservation_id,
            action=ExternalToolHoldAction.FINALIZE_ACTUAL,
            execute=True,
            actor_admin_id=actor,
            reason="eight worker reconciliation proof",
            actual_cost_eur=Decimal("0.75"),
            actual_total_tokens=75,
            success=True,
        )

        async def worker():
            async with sessions() as session:
                service = ExternalToolAccountingHoldService(
                    gateway_keys_repository=GatewayKeysRepository(session),
                    quota_reservations_repository=QuotaReservationsRepository(session),
                    usage_ledger_repository=UsageLedgerRepository(session),
                    audit_repository=AuditRepository(session),
                )
                result = await service.reconcile(request)
                await session.commit()
                return result

        results = await asyncio.gather(*(worker() for _ in range(8)))
        assert sum(not result.idempotent for result in results) == 1
        assert sum(result.idempotent for result in results) == 7

        async with sessions() as session:
            key = await GatewayKeysRepository(session).get_gateway_key_by_id(key_id)
            reservation = await QuotaReservationsRepository(session).get_reservation_by_id(
                reservation_id
            )
            ledgers = await UsageLedgerRepository(session).get_usage_records_by_reservation_id(
                reservation_id
            )
            audits = await AuditRepository(session).list_audit_logs(
                action="external_tool_accounting_hold_reconciled"
            )
            assert key is not None and key.external_tool_fence_state == "none"
            assert key.cost_used_eur == Decimal("0.75")
            assert key.tokens_used_total == 75
            assert reservation is not None and reservation.status == "finalized"
            assert len(ledgers) == 1 and ledgers[0].accounting_status == "finalized"
            assert len([audit for audit in audits if audit.request_id == request_id]) == 1
            await session.commit()
    finally:
        await engine.dispose()
