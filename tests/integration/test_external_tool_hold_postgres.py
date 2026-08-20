"""PostgreSQL proof for durable external-tool hold placement/reconciliation."""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
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
from slaif_gateway.services.external_tool_hold import ExternalToolAccountingHoldService
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
