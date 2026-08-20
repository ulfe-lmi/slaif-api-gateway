"""PostgreSQL evidence for bounded Responses web-search accounting."""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from slaif_gateway.db.models import ModelRoute
from slaif_gateway.db.repositories.audit import AuditRepository
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
    ExternalToolHoldEvidenceQuality,
    ExternalToolHoldReasonCode,
)
from slaif_gateway.services.external_tool_fence import ExternalToolFenceService
from slaif_gateway.services.external_tool_hold import ExternalToolAccountingHoldService
from slaif_gateway.services.external_tool_policy_contract import ExternalToolAdmissionDecision

pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL is not set; skipping Responses external-tool PostgreSQL tests.",
)


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


async def _create_key(session: AsyncSession):
    owner = await OwnersRepository(session).create_owner(
        name="Responses",
        surname="Web Search",
        email=f"responses-web-search-{uuid.uuid4().hex}@example.test",
    )
    policy = {
        "version": 1,
        "mode": "external_tool_fenced",
        "allowed_capabilities": ["provider_web_search"],
        "allowed_destination_ids": [],
        "max_provider_tool_calls_per_request": 2,
        "single_request_overrun_acknowledged": True,
    }
    return await GatewayKeysRepository(session).create_gateway_key_record(
        public_key_id=f"responses_{uuid.uuid4().hex}",
        token_hash=f"hash-{uuid.uuid4().hex}",
        owner_id=owner.id,
        valid_from=datetime.now(UTC) - timedelta(minutes=1),
        valid_until=datetime.now(UTC) + timedelta(hours=1),
        cost_limit_eur=Decimal("5.000000000"),
        token_limit_total=1000,
        request_limit_total=3,
        allow_all_models=True,
        allow_all_endpoints=True,
        metadata_json={"external_tool_policy": policy},
    )


@pytest.mark.asyncio
async def test_web_search_fence_and_hold_are_content_free(
    async_test_session: AsyncSession,
) -> None:
    key = await _create_key(async_test_session)
    route_row = ModelRoute(
        requested_model="gpt-responses-web-search-test",
        match_type="exact",
        endpoint="/v1/responses",
        provider="openai",
        upstream_model="gpt-4.1-mini",
    )
    async_test_session.add(route_row)
    await async_test_session.flush()
    fence = ExternalToolFenceService(
        gateway_keys_repository=GatewayKeysRepository(async_test_session),
        quota_reservations_repository=QuotaReservationsRepository(async_test_session),
        usage_ledger_repository=UsageLedgerRepository(async_test_session),
        audit_repository=AuditRepository(async_test_session),
    )
    acquired = await fence.acquire(
        ExternalToolFenceAcquireInput(
            gateway_key_id=key.id,
            request_id=f"responses-web-search-{uuid.uuid4().hex}",
            route=ExternalToolFenceRouteFacts(
                endpoint="/v1/responses",
                requested_model="gpt-responses-web-search-test",
                provider="openai",
                route_id=route_row.id,
            ),
            capabilities=("provider_web_search",),
            destination_ids=(),
            decision=_decision(),
            now=datetime.now(UTC),
        )
    )
    assert acquired.fence_state == "active"
    assert acquired.reserved_cost_eur == Decimal("5.000000000")
    assert acquired.reserved_tokens == 1000
    assert acquired.reserved_requests == 1

    await async_test_session.refresh(key)
    assert key.external_tool_fence_state == "active"
    assert key.cost_reserved_eur == Decimal("5.000000000")
    assert key.tokens_reserved_total == 1000
    assert key.requests_reserved_total == 1

    hold = await ExternalToolAccountingHoldService(
        gateway_keys_repository=GatewayKeysRepository(async_test_session),
        quota_reservations_repository=QuotaReservationsRepository(async_test_session),
        usage_ledger_repository=UsageLedgerRepository(async_test_session),
        audit_repository=AuditRepository(async_test_session),
    ).place(
        ExternalToolAccountingHoldInput(
            gateway_key_id=key.id,
            reservation_id=acquired.reservation_id,
            request_id=acquired.request_id,
            reason_code=ExternalToolHoldReasonCode.MISSING_FINAL_USAGE,
            evidence_quality=ExternalToolHoldEvidenceQuality.MISSING,
            streaming=True,
            now=datetime.now(UTC),
        )
    )
    assert hold.fence_state == "held"
    ledgers = await UsageLedgerRepository(async_test_session).get_usage_records_by_reservation_id(
        acquired.reservation_id
    )
    assert len(ledgers) == 1
    assert ledgers[0].usage_raw == {}
    assert "external_tool_accounting_hold" in ledgers[0].response_metadata
    assert "content" not in ledgers[0].response_metadata
    assert "arguments" not in ledgers[0].response_metadata
    assert "results" not in ledgers[0].response_metadata
