from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from slaif_gateway.schemas.auth import AuthenticatedGatewayKey
from slaif_gateway.schemas.policy import ChatCompletionPolicyResult
from slaif_gateway.schemas.pricing import ChatCostEstimate
from slaif_gateway.schemas.providers import ProviderResponse, ProviderUsage
from slaif_gateway.schemas.routing import RouteResolutionResult
from slaif_gateway.services.accounting import AccountingService
from tests.unit.test_accounting_service_finalize import (
    FakeGatewayKeysRepository,
    FakeKeyRow,
    FakeQuotaReservationsRepository,
    FakeReservationRow,
    FakeUsageLedgerRepository,
)


@pytest.mark.asyncio
async def test_accounting_usage_metadata_sanitizes_nested_sensitive_values() -> None:
    key = FakeKeyRow(id=uuid.uuid4())
    reservation = FakeReservationRow(id=uuid.uuid4(), gateway_key_id=key.id)
    usage_repo = FakeUsageLedgerRepository()
    service = AccountingService(
        gateway_keys_repository=FakeGatewayKeysRepository(key),
        quota_reservations_repository=FakeQuotaReservationsRepository(reservation),
        usage_ledger_repository=usage_repo,
    )

    response = ProviderResponse(
        provider="openai",
        upstream_model="gpt-4.1-mini",
        status_code=200,
        json_body={"id": "chatcmpl_1"},
        upstream_request_id="upstream_req_1",
        usage=ProviderUsage(
            prompt_tokens=50,
            completion_tokens=25,
            total_tokens=75,
            other_usage={
                "prompt_tokens": 50,
                "prompt": "prompt secret",
                "completion": "completion secret",
                "nested": {
                    "providerApiKey": "sk-proj-providersecret123456",
                    "tokenHash": "hash-secret",
                    "safe_count": 2,
                },
                "events": [{"authorizationHeader": "Bearer sk-or-providersecret123"}],
            },
        ),
    )

    await service.finalize_successful_response(
        reservation.id,
        _auth(key.id),
        _route(),
        _policy(),
        _estimate(),
        response,
        request_id="req_1",
    )

    usage_raw = usage_repo.success_calls[0]["usage_raw"]
    serialized = str(usage_raw)

    assert usage_raw["prompt_tokens"] == 50
    assert usage_raw["nested"]["safe_count"] == 2
    assert "prompt secret" not in serialized
    assert "completion secret" not in serialized
    assert "providersecret" not in serialized
    assert "hash-secret" not in serialized


def _auth(gateway_key_id: uuid.UUID) -> AuthenticatedGatewayKey:
    now = datetime.now(UTC)
    return AuthenticatedGatewayKey(
        gateway_key_id=gateway_key_id,
        owner_id=uuid.uuid4(),
        cohort_id=uuid.uuid4(),
        public_key_id="public",
        status="active",
        valid_from=now - timedelta(minutes=1),
        valid_until=now + timedelta(minutes=30),
        allow_all_models=True,
        allowed_models=(),
        allow_all_endpoints=True,
        allowed_endpoints=(),
        allowed_providers=None,
        cost_limit_eur=None,
        token_limit_total=None,
        request_limit_total=None,
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
