from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from slaif_gateway.schemas.accounting import ActualUsage
from slaif_gateway.schemas.pricing import ChatCostEstimate
from slaif_gateway.schemas.providers import ProviderResponse, ProviderUsage
from slaif_gateway.schemas.routing import RouteResolutionResult
from slaif_gateway.services.accounting import AccountingService
from slaif_gateway.services.accounting_errors import (
    InvalidUsageError,
    UnsupportedProviderCostError,
    UsageMissingError,
)


class FakeRepository:
    commits = 0


def _service() -> AccountingService:
    return AccountingService(
        gateway_keys_repository=FakeRepository(),
        quota_reservations_repository=FakeRepository(),
        usage_ledger_repository=FakeRepository(),
    )


def _response(usage: ProviderUsage | None, **kwargs) -> ProviderResponse:
    return ProviderResponse(
        provider="openai",
        upstream_model="gpt-4.1-mini",
        status_code=200,
        json_body={},
        usage=usage,
        **kwargs,
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


def _estimate(
    *,
    input_tokens: int = 100,
    output_tokens: int = 100,
    input_cost: Decimal = Decimal("0.100000000"),
    output_cost: Decimal = Decimal("0.200000000"),
    total_native: Decimal = Decimal("0.300000000"),
    total_eur: Decimal = Decimal("0.300000000"),
) -> ChatCostEstimate:
    return ChatCostEstimate(
        provider="openai",
        requested_model="classroom-cheap",
        resolved_model="gpt-4.1-mini",
        native_currency="EUR",
        estimated_input_tokens=input_tokens,
        estimated_output_tokens=output_tokens,
        estimated_input_cost_native=input_cost,
        estimated_output_cost_native=output_cost,
        estimated_total_cost_native=total_native,
        estimated_total_cost_eur=total_eur,
        pricing_rule_id=None,
        fx_rate_id=None,
    )


def test_extract_usage_parses_prompt_completion_and_total_tokens() -> None:
    usage = _service().extract_usage(
        _response(
            ProviderUsage(
                prompt_tokens=12,
                completion_tokens=8,
                total_tokens=20,
                other_usage={"prompt_tokens": 12},
            )
        )
    )

    assert usage == ActualUsage(
        prompt_tokens=12,
        completion_tokens=8,
        total_tokens=20,
        other_usage={"prompt_tokens": 12},
    )


def test_extract_usage_computes_total_when_missing() -> None:
    usage = _service().extract_usage(
        _response(ProviderUsage(prompt_tokens=12, completion_tokens=8))
    )

    assert usage.total_tokens == 20


def test_extract_usage_rejects_negative_tokens() -> None:
    with pytest.raises(InvalidUsageError):
        _service().extract_usage(
            _response(ProviderUsage(prompt_tokens=-1, completion_tokens=8, total_tokens=7))
        )


def test_extract_usage_rejects_impossible_component_total() -> None:
    with pytest.raises(InvalidUsageError):
        _service().extract_usage(
            _response(ProviderUsage(prompt_tokens=12, completion_tokens=8, total_tokens=19))
        )


def test_extract_usage_handles_cached_reasoning_and_filters_content_fields() -> None:
    usage = _service().extract_usage(
        _response(
            ProviderUsage(
                prompt_tokens=10,
                completion_tokens=5,
                total_tokens=15,
                cached_tokens=3,
                reasoning_tokens=2,
                other_usage={
                    "prompt_tokens": 10,
                    "prompt": "do not store",
                    "completion": "do not store",
                    "nested": {"content": "do not store", "cached_tokens": 3},
                },
            )
        )
    )

    assert usage.cached_tokens == 3
    assert usage.reasoning_tokens == 2
    assert "prompt" not in usage.other_usage
    assert "completion" not in usage.other_usage
    assert usage.other_usage["nested"] == {"cached_tokens": 3}


def test_extract_usage_preserves_total_when_components_are_missing() -> None:
    usage = _service().extract_usage(_response(ProviderUsage(total_tokens=11)))

    assert usage.prompt_tokens == 0
    assert usage.completion_tokens == 0
    assert usage.total_tokens == 11


def test_extract_usage_missing_usage_raises_usage_missing_error() -> None:
    with pytest.raises(UsageMissingError):
        _service().extract_usage(_response(None))


def test_compute_actual_cost_uses_decimal_and_actual_usage() -> None:
    usage = ActualUsage(prompt_tokens=50, completion_tokens=25, total_tokens=75)
    actual = _service().compute_actual_cost(
        _response(ProviderUsage(prompt_tokens=50, completion_tokens=25, total_tokens=75)),
        _route(),
        usage,
        _estimate(),
        at=datetime(2026, 4, 25, tzinfo=UTC),
    )

    assert actual.actual_cost_eur == Decimal("0.1000000000")
    assert actual.actual_cost_native == Decimal("0.1000000000")
    assert isinstance(actual.actual_cost_eur, Decimal)


def test_compute_actual_cost_records_provider_reported_cost_without_trusting_for_eur() -> None:
    usage = ActualUsage(prompt_tokens=50, completion_tokens=25, total_tokens=75)
    actual = _service().compute_actual_cost(
        _response(
            ProviderUsage(prompt_tokens=50, completion_tokens=25, total_tokens=75),
            raw_cost_native=Decimal("9.990000000"),
            native_currency="USD",
        ),
        _route(),
        usage,
        _estimate(),
    )

    assert actual.actual_cost_eur == Decimal("0.1000000000")
    assert actual.provider_reported_cost_native == Decimal("9.990000000")
    assert actual.provider_reported_currency == "USD"


def test_compute_actual_cost_fails_closed_when_pricing_data_is_missing() -> None:
    usage = ActualUsage(prompt_tokens=1, completion_tokens=0, total_tokens=1)

    with pytest.raises(UnsupportedProviderCostError):
        _service().compute_actual_cost(
            _response(ProviderUsage(prompt_tokens=1, completion_tokens=0, total_tokens=1)),
            _route(),
            usage,
            _estimate(input_tokens=0, input_cost=Decimal("0")),
        )
