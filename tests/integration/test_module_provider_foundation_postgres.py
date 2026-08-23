"""PostgreSQL proof for the native module foundation and fixed billing mode."""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from slaif_gateway.db.models import GatewayKey, ProviderConfig
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
    reason="TEST_DATABASE_URL is not set; skipping optional PostgreSQL module tests.",
)


def _route(provider: str) -> RouteResolutionResult:
    return RouteResolutionResult(
        requested_model="module-score",
        resolved_model="module-score-v1",
        provider=provider,
        route_id=uuid.uuid4(),
        route_match_type="exact",
        route_pattern="module-score",
        priority=100,
        provider_kind="module",
        provider_base_url="https://module.example/score",
        provider_api_key_env_var="MODULE_PROVIDER_KEY",
    )


def _policy() -> ChatCompletionPolicyResult:
    return ChatCompletionPolicyResult(
        effective_body={
            "model": "module-score",
            "messages": [{"role": "user", "content": "bounded input"}],
            "max_completion_tokens": 4096,
        },
        requested_output_tokens=4096,
        effective_output_tokens=4096,
        estimated_input_tokens=128,
        injected_default_output_tokens=False,
    )


def _estimate(provider: str) -> ChatCostEstimate:
    return ChatCostEstimate(
        provider=provider,
        requested_model="module-score",
        resolved_model="module-score-v1",
        native_currency="EUR",
        estimated_input_tokens=0,
        estimated_output_tokens=0,
        estimated_input_cost_native=Decimal("0"),
        estimated_output_cost_native=Decimal("0"),
        estimated_total_cost_native=Decimal("0"),
        estimated_total_cost_eur=Decimal("0"),
        pricing_rule_id=None,
        fx_rate_id=None,
        request_price=Decimal("0"),
    )


async def _create_key(session: AsyncSession) -> GatewayKey:
    owner = await OwnersRepository(session).create_owner(
        name="Module",
        surname="Tester",
        email=f"module-{uuid.uuid4()}@example.org",
    )
    now = datetime.now(UTC)
    return await GatewayKeysRepository(session).create_gateway_key_record(
        public_key_id=f"module-{uuid.uuid4().hex}",
        token_hash=f"test-hash-{uuid.uuid4().hex}",
        owner_id=owner.id,
        valid_from=now - timedelta(minutes=1),
        valid_until=now + timedelta(hours=1),
        cost_limit_eur=Decimal("1"),
        token_limit_total=1000,
        request_limit_total=3,
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


@pytest.mark.asyncio
async def test_postgres_module_kind_constraint_and_fixed_request_accounting(
    async_test_session: AsyncSession,
) -> None:
    provider_name = f"module-{uuid.uuid4().hex}"
    provider = ProviderConfig(
        provider=provider_name,
        display_name="Native module foundation",
        kind="module",
        base_url="https://module.example/score",
        api_key_env_var="MODULE_PROVIDER_KEY",
        enabled=True,
        timeout_seconds=30,
        max_retries=0,
        notes="foundation test metadata",
    )
    async_test_session.add(provider)
    await async_test_session.flush()

    try:
        async with async_test_session.begin_nested():
            async_test_session.add(
                ProviderConfig(
                    provider=f"invalid-{uuid.uuid4().hex}",
                    display_name="Invalid kind",
                    kind="dynamic_import",
                    base_url="https://module.example/score",
                    api_key_env_var="MODULE_PROVIDER_KEY",
                    enabled=True,
                    timeout_seconds=30,
                    max_retries=0,
                )
            )
            await async_test_session.flush()
    except IntegrityError:
        pass
    else:
        pytest.fail("provider_configs accepted an unsupported provider kind")

    gateway_key = await _create_key(async_test_session)
    route = _route(provider_name)
    estimate = _estimate(provider_name)
    quota = QuotaService(
        gateway_keys_repository=GatewayKeysRepository(async_test_session),
        quota_reservations_repository=QuotaReservationsRepository(async_test_session),
    )
    reservation = await quota.reserve_for_chat_completion(
        authenticated_key=_auth(gateway_key),
        route=route,
        policy=_policy(),
        cost_estimate=estimate,
        request_id=f"module-{uuid.uuid4()}",
    )
    assert reservation.reserved_tokens == 0
    assert reservation.reserved_cost_eur == Decimal("0E-9")
    reservation_row = await QuotaReservationsRepository(async_test_session).get_reservation_by_id(
        reservation.reservation_id
    )
    assert reservation_row is not None
    assert reservation_row.reserved_requests == 1

    result = await AccountingService(async_test_session).finalize_successful_response(
        reservation.reservation_id,
        _auth(gateway_key),
        route,
        _policy(),
        estimate,
        ProviderResponse(
            provider=provider_name,
            upstream_model="module-score-v1",
            status_code=200,
            json_body={"id": "module-response"},
            usage=ProviderUsage(prompt_tokens=50, completion_tokens=25, total_tokens=75),
        ),
        request_id=reservation.request_id,
    )

    await async_test_session.refresh(gateway_key)
    ledger = await UsageLedgerRepository(async_test_session).get_usage_record_by_request_id(
        reservation.request_id
    )
    assert result.total_tokens == 0
    assert gateway_key.tokens_used_total == 0
    assert gateway_key.requests_used_total == 1
    assert ledger is not None
    assert ledger.total_tokens == 0
    assert ledger.actual_cost_eur == Decimal("0E-9")
    assert ledger.usage_raw == {}
