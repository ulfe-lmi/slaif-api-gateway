"""Focused PostgreSQL accounting/privacy evidence for generic backends."""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, inspect, select
from sqlalchemy.ext.asyncio import AsyncSession

from slaif_gateway.db.models import QuotaReservation, UsageLedger
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
from slaif_gateway.services.quota_service import QuotaService

pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL is required for generic conformance PostgreSQL tests.",
)


async def _create_key(session: AsyncSession):
    owner = await OwnersRepository(session).create_owner(
        name="Generic",
        surname="Conformance",
        email=f"generic-conformance-{uuid.uuid4()}@example.test",
    )
    now = datetime.now(UTC)
    return await GatewayKeysRepository(session).create_gateway_key_record(
        public_key_id=f"generic-{uuid.uuid4().hex}",
        token_hash=f"hmac-{uuid.uuid4().hex}",
        owner_id=owner.id,
        valid_from=now - timedelta(minutes=5),
        valid_until=now + timedelta(hours=1),
        cost_limit_eur=Decimal("1.000000000"),
        token_limit_total=1000,
        request_limit_total=5,
        allow_all_models=True,
        allow_all_endpoints=True,
    )


def _auth(row) -> AuthenticatedGatewayKey:
    return AuthenticatedGatewayKey(
        gateway_key_id=row.id,
        owner_id=row.owner_id,
        cohort_id=row.cohort_id,
        public_key_id=row.public_key_id,
        status=row.status,
        valid_from=row.valid_from,
        valid_until=row.valid_until,
        allow_all_models=True,
        allowed_models=(),
        allow_all_endpoints=True,
        allowed_endpoints=(),
        allowed_providers=None,
        cost_limit_eur=row.cost_limit_eur,
        token_limit_total=row.token_limit_total,
        request_limit_total=row.request_limit_total,
        rate_limit_policy={},
    )


def _route() -> RouteResolutionResult:
    return RouteResolutionResult(
        requested_model="public-qwen",
        resolved_model="qwen/a",
        provider="lan-qwen",
        route_id=uuid.uuid4(),
        route_match_type="exact",
        route_pattern="public-qwen",
        priority=100,
        provider_kind="openai_compatible",
    )


def _policy() -> ChatCompletionPolicyResult:
    return ChatCompletionPolicyResult(
        effective_body={
            "model": "public-qwen",
            "messages": [{"role": "user", "content": "PROMPT_SECRET"}],
            "max_completion_tokens": 20,
        },
        requested_output_tokens=20,
        effective_output_tokens=20,
        estimated_input_tokens=5,
        injected_default_output_tokens=False,
    )


def _estimate() -> ChatCostEstimate:
    return ChatCostEstimate(
        provider="lan-qwen",
        requested_model="public-qwen",
        resolved_model="qwen/a",
        native_currency="EUR",
        estimated_input_tokens=5,
        estimated_output_tokens=20,
        estimated_input_cost_native=Decimal("0.001000000"),
        estimated_output_cost_native=Decimal("0.002000000"),
        estimated_total_cost_native=Decimal("0.003000000"),
        estimated_total_cost_eur=Decimal("0.003000000"),
        pricing_rule_id=None,
        fx_rate_id=None,
    )


@pytest.mark.asyncio
async def test_generic_accounting_finalizes_once_with_route_identity_and_no_content(
    async_test_session: AsyncSession,
) -> None:
    key = await _create_key(async_test_session)
    route = _route()
    policy = _policy()
    estimate = _estimate()
    request_id = f"generic-conformance-{uuid.uuid4()}"
    reservation = await QuotaService(
        gateway_keys_repository=GatewayKeysRepository(async_test_session),
        quota_reservations_repository=QuotaReservationsRepository(async_test_session),
    ).reserve_for_chat_completion(
        authenticated_key=_auth(key),
        route=route,
        policy=policy,
        cost_estimate=estimate,
        request_id=request_id,
    )

    result = await AccountingService(async_test_session).finalize_successful_response(
        reservation.reservation_id,
        _auth(key),
        route,
        policy,
        estimate,
        ProviderResponse(
            provider="lan-qwen",
            upstream_model="qwen/a",
            status_code=200,
            json_body={"completion": "COMPLETION_SECRET", "image": "BASE64_SECRET"},
            upstream_request_id="generic-upstream-request",
            usage=ProviderUsage(prompt_tokens=5, completion_tokens=7, total_tokens=12),
        ),
        request_id=request_id,
    )

    assert result.accounting_status == "finalized"
    ledger = await UsageLedgerRepository(async_test_session).get_usage_record_by_request_id(request_id)
    reservation_row = await QuotaReservationsRepository(async_test_session).get_reservation_by_id(
        reservation.reservation_id
    )
    assert ledger is not None
    assert reservation_row is not None
    assert reservation_row.status == "finalized"
    assert ledger.provider == "lan-qwen"
    assert ledger.requested_model == "public-qwen"
    assert ledger.resolved_model == "qwen/a"
    assert ledger.endpoint == "/v1/chat/completions"
    assert ledger.accounting_status == "finalized"
    assert ledger.total_tokens == 12
    assert await async_test_session.scalar(
        select(func.count()).select_from(UsageLedger).where(UsageLedger.request_id == request_id)
    ) == 1
    assert await async_test_session.scalar(
        select(func.count())
        .select_from(QuotaReservation)
        .where(
            QuotaReservation.request_id == request_id,
            QuotaReservation.status == "pending",
        )
    ) == 0
    persisted = str(ledger.__dict__)
    assert all(secret not in persisted for secret in ("PROMPT_SECRET", "COMPLETION_SECRET", "BASE64_SECRET"))

    columns = await (await async_test_session.connection()).run_sync(
        lambda connection: {column["name"] for column in inspect(connection).get_columns("usage_ledger")}
    )
    assert "prompt_content" not in columns
    assert "completion_content" not in columns
    assert "raw_request" not in columns
    assert "raw_response" not in columns
