"""PostgreSQL checks for scheduled reconciliation task foundations."""

from __future__ import annotations

import json
import os
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from slaif_gateway.config import Settings
from slaif_gateway.db.models import AuditLog, UsageLedger
from slaif_gateway.db.repositories.keys import GatewayKeysRepository
from slaif_gateway.db.repositories.owners import OwnersRepository
from slaif_gateway.db.repositories.quota import QuotaReservationsRepository
from slaif_gateway.db.repositories.usage import UsageLedgerRepository
from slaif_gateway.workers import tasks_reconciliation

pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL is not set; skipping optional PostgreSQL reconciliation task tests.",
)

PROMPT_TEXT = "sensitive scheduled reconciliation prompt"
COMPLETION_TEXT = "sensitive scheduled reconciliation completion"


@pytest.mark.asyncio
async def test_postgres_reconciliation_tasks_inspect_dry_run_and_execute(
    migrated_postgres_url: str,
) -> None:
    engine = create_async_engine(migrated_postgres_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory.begin() as session:
            gateway_key = await _create_gateway_key(session)
            expired_reservation = await _create_expired_pending_reservation(session, gateway_key)
            provider_reservation, provider_ledger = await _create_provider_completed_recovery(
                session,
                gateway_key,
            )
            gateway_key_id = gateway_key.id
            expired_reservation_id = expired_reservation.id
            provider_reservation_id = provider_reservation.id
            provider_ledger_id = provider_ledger.id

        inspect_result = await tasks_reconciliation._inspect_reconciliation_backlog(
            settings=Settings(
                DATABASE_URL=migrated_postgres_url,
                RECONCILIATION_EXPIRED_RESERVATION_LIMIT=100,
                RECONCILIATION_PROVIDER_COMPLETED_LIMIT=100,
            )
        )

        assert str(expired_reservation_id) in inspect_result["expired_reservations"]["reservation_ids"]
        assert str(provider_ledger_id) in inspect_result["provider_completed"]["usage_ledger_ids"]

        expired_dry_run = await tasks_reconciliation._reconcile_expired_reservations(
            settings=Settings(
                DATABASE_URL=migrated_postgres_url,
                RECONCILIATION_DRY_RUN=True,
                RECONCILIATION_AUTO_EXECUTE_EXPIRED_RESERVATIONS=False,
            ),
            dry_run=True,
        )
        provider_dry_run = await tasks_reconciliation._reconcile_provider_completed(
            settings=Settings(
                DATABASE_URL=migrated_postgres_url,
                RECONCILIATION_DRY_RUN=True,
                RECONCILIATION_AUTO_EXECUTE_PROVIDER_COMPLETED=False,
            ),
            dry_run=True,
        )

        assert expired_dry_run["dry_run"] is True
        assert provider_dry_run["dry_run"] is True
        async with session_factory() as session:
            expired_reservation = await QuotaReservationsRepository(session).get_reservation_by_id(
                expired_reservation_id
            )
            provider_ledger = await UsageLedgerRepository(session).get_usage_record_by_id(provider_ledger_id)
            gateway_key = await GatewayKeysRepository(session).get_gateway_key_by_id(gateway_key_id)
            assert expired_reservation.status == "pending"
            assert provider_ledger.accounting_status == "failed"
            assert gateway_key.cost_reserved_eur == Decimal("0.600000000")

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
            ),
            dry_run=False,
            reason="scheduled provider completed repair",
        )

        assert expired_execute["dry_run"] is False
        assert str(expired_reservation_id) in json.dumps(expired_execute)
        assert provider_execute["dry_run"] is False
        assert str(provider_ledger_id) in json.dumps(provider_execute)

        async with session_factory() as session:
            expired_reservation = await QuotaReservationsRepository(session).get_reservation_by_id(
                expired_reservation_id
            )
            provider_reservation = await QuotaReservationsRepository(session).get_reservation_by_id(
                provider_reservation_id
            )
            provider_ledger = await UsageLedgerRepository(session).get_usage_record_by_id(provider_ledger_id)
            gateway_key = await GatewayKeysRepository(session).get_gateway_key_by_id(gateway_key_id)

            assert expired_reservation.status == "expired"
            assert provider_reservation.status == "finalized"
            assert provider_ledger.accounting_status == "finalized"
            assert provider_ledger.success is True
            assert gateway_key.cost_reserved_eur == Decimal("0E-9")
            assert gateway_key.cost_used_eur == Decimal("0.000011000")
            assert gateway_key.tokens_used_total == 11
            assert gateway_key.requests_used_total == 1

            ledger_count = (
                await session.execute(
                    select(func.count())
                    .select_from(UsageLedger)
                    .where(UsageLedger.request_id == provider_reservation.request_id)
                )
            ).scalar_one()
            assert ledger_count == 1

            audits = (
                await session.execute(
                    select(AuditLog).where(
                        AuditLog.entity_id.in_([expired_reservation_id, provider_ledger_id])
                    )
                )
            ).scalars().all()
            assert {audit.action for audit in audits} == {
                "quota_reservation_expired",
                "provider_completed_reconciliation",
            }

            safe_payload = json.dumps(
                {
                    "task_results": [inspect_result, expired_dry_run, provider_dry_run, expired_execute, provider_execute],
                    "ledger_usage": provider_ledger.usage_raw,
                    "ledger_metadata": provider_ledger.response_metadata,
                    "audit_values": [
                        {
                            "old_values": audit.old_values,
                            "new_values": audit.new_values,
                            "note": audit.note,
                        }
                        for audit in audits
                    ],
                },
                sort_keys=True,
                default=str,
            )
            assert PROMPT_TEXT not in safe_payload
            assert COMPLETION_TEXT not in safe_payload
            assert "token_hash" not in safe_payload
            assert "encrypted_payload" not in safe_payload
            assert "nonce" not in safe_payload
            assert "provider-key" not in safe_payload
    finally:
        await engine.dispose()


async def _create_gateway_key(session):
    owner = await OwnersRepository(session).create_owner(
        name="Scheduled",
        surname="Reconciliation",
        email=f"scheduled-reconciliation-{uuid.uuid4()}@example.test",
    )
    now = datetime.now(UTC)
    return await GatewayKeysRepository(session).create_gateway_key_record(
        public_key_id=f"k_{uuid.uuid4().hex}",
        token_hash=f"hash-{uuid.uuid4().hex}",
        owner_id=owner.id,
        valid_from=now - timedelta(minutes=5),
        valid_until=now + timedelta(hours=1),
        cost_limit_eur=Decimal("2.000000000"),
        token_limit_total=2000,
        request_limit_total=20,
        allow_all_models=True,
        allow_all_endpoints=True,
    )


async def _create_expired_pending_reservation(session, gateway_key):
    reservation = await QuotaReservationsRepository(session).create_reservation(
        gateway_key_id=gateway_key.id,
        request_id=f"req-expired-task-{uuid.uuid4()}",
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


async def _create_provider_completed_recovery(session, gateway_key):
    request_id = f"req-provider-task-{uuid.uuid4()}"
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
        upstream_request_id="upstream-provider-completed-task",
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
        usage_raw={"prompt_tokens": 5, "completion_tokens": 6, "total_tokens": 11},
        response_metadata={
            "needs_reconciliation": True,
            "recovery_state": "provider_completed_finalization_failed",
            "prompt": PROMPT_TEXT,
            "completion": COMPLETION_TEXT,
        },
        started_at=datetime.now(UTC) - timedelta(seconds=2),
        finished_at=datetime.now(UTC),
        latency_ms=2000,
    )
    return reservation, ledger
