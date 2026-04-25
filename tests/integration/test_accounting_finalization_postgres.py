"""Optional PostgreSQL checks for accounting finalization."""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncSession

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
    reason="TEST_DATABASE_URL is not set; skipping optional PostgreSQL accounting tests.",
)


def _usage_ledger_column_names(sync_connection) -> set[str]:
    return {column["name"] for column in inspect(sync_connection).get_columns("usage_ledger")}


async def _create_gateway_key(async_test_session: AsyncSession):
    owner = await OwnersRepository(async_test_session).create_owner(
        name="Accounting",
        surname="Tester",
        email=f"accounting-{uuid.uuid4()}@example.test",
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
        request_limit_total=5,
        allow_all_models=True,
        allow_all_endpoints=True,
    )


def _authenticated_key(row) -> AuthenticatedGatewayKey:
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


def _policy() -> ChatCompletionPolicyResult:
    return ChatCompletionPolicyResult(
        effective_body={"model": "classroom-cheap", "messages": [], "max_completion_tokens": 100},
        requested_output_tokens=100,
        effective_output_tokens=100,
        estimated_input_tokens=100,
        injected_default_output_tokens=False,
    )


def _estimate() -> ChatCostEstimate:
    return ChatCostEstimate(
        provider="openai",
        requested_model="classroom-cheap",
        resolved_model="gpt-4.1-mini",
        native_currency="EUR",
        estimated_input_tokens=100,
        estimated_output_tokens=100,
        estimated_input_cost_native=Decimal("0.100000000"),
        estimated_output_cost_native=Decimal("0.200000000"),
        estimated_total_cost_native=Decimal("0.300000000"),
        estimated_total_cost_eur=Decimal("0.300000000"),
        pricing_rule_id=None,
        fx_rate_id=None,
    )


async def _reserve(async_test_session: AsyncSession, gateway_key, request_id: str):
    return await QuotaService(
        gateway_keys_repository=GatewayKeysRepository(async_test_session),
        quota_reservations_repository=QuotaReservationsRepository(async_test_session),
    ).reserve_for_chat_completion(
        authenticated_key=_authenticated_key(gateway_key),
        route=_route(),
        policy=_policy(),
        cost_estimate=_estimate(),
        request_id=request_id,
    )


@pytest.mark.asyncio
async def test_postgres_finalize_success_updates_counters_and_ledger(
    async_test_session: AsyncSession,
) -> None:
    gateway_key = await _create_gateway_key(async_test_session)
    reservation = await _reserve(async_test_session, gateway_key, f"req-{uuid.uuid4()}")

    result = await AccountingService(async_test_session).finalize_successful_response(
        reservation.reservation_id,
        _authenticated_key(gateway_key),
        _route(),
        _policy(),
        _estimate(),
        ProviderResponse(
            provider="openai",
            upstream_model="gpt-4.1-mini",
            status_code=200,
            json_body={},
            upstream_request_id="upstream_req_1",
            usage=ProviderUsage(prompt_tokens=50, completion_tokens=25, total_tokens=75),
        ),
        request_id=reservation.request_id,
    )

    await async_test_session.refresh(gateway_key)
    reservation_row = await QuotaReservationsRepository(async_test_session).get_reservation_by_id(
        reservation.reservation_id
    )
    ledger = await UsageLedgerRepository(async_test_session).get_usage_record_by_request_id(
        reservation.request_id
    )

    assert result.accounting_status == "finalized"
    assert gateway_key.cost_reserved_eur == Decimal("0E-9")
    assert gateway_key.tokens_reserved_total == 0
    assert gateway_key.requests_reserved_total == 0
    assert gateway_key.cost_used_eur == Decimal("0.100000000")
    assert gateway_key.tokens_used_total == 75
    assert gateway_key.requests_used_total == 1
    assert reservation_row is not None
    assert reservation_row.status == "finalized"
    assert ledger is not None
    assert ledger.accounting_status == "finalized"
    assert ledger.upstream_request_id == "upstream_req_1"

    connection = await async_test_session.connection()
    columns = await connection.run_sync(_usage_ledger_column_names)
    assert "prompt_content" not in columns
    assert "completion_content" not in columns


@pytest.mark.asyncio
async def test_postgres_provider_failure_releases_reservation(
    async_test_session: AsyncSession,
) -> None:
    gateway_key = await _create_gateway_key(async_test_session)
    reservation = await _reserve(async_test_session, gateway_key, f"req-{uuid.uuid4()}")

    result = await AccountingService(async_test_session).record_provider_failure_and_release(
        reservation.reservation_id,
        _authenticated_key(gateway_key),
        _route(),
        _policy(),
        _estimate(),
        request_id=reservation.request_id,
        error_type="provider_http_error",
        error_code="upstream_500",
        status_code=500,
    )

    await async_test_session.refresh(gateway_key)
    reservation_row = await QuotaReservationsRepository(async_test_session).get_reservation_by_id(
        reservation.reservation_id
    )

    assert result.released is True
    assert gateway_key.cost_reserved_eur == Decimal("0E-9")
    assert gateway_key.tokens_reserved_total == 0
    assert gateway_key.requests_reserved_total == 0
    assert gateway_key.cost_used_eur == Decimal("0E-9")
    assert reservation_row is not None
    assert reservation_row.status == "released"
