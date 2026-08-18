from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from slaif_gateway.config import Settings
from slaif_gateway.schemas.policy import ResponsesPolicyResult
from slaif_gateway.schemas.providers import ProviderResponse, ProviderUsage
from slaif_gateway.schemas.routing import RouteResolutionResult
from slaif_gateway.services.accounting import AccountingService
from slaif_gateway.services.accounting_errors import UnsupportedProviderCostError
from slaif_gateway.services.pricing import PricingService
from slaif_gateway.services.pricing_errors import InvalidPricingDataError
from slaif_gateway.services.responses_request_policy import (
    ResponsesRequestPolicy,
    apply_codex_route_limits,
)
from slaif_gateway.services.responses_route_capabilities import (
    default_responses_capabilities,
    enforce_responses_route_capabilities,
)


def _route_capabilities(**limits: object) -> dict[str, object]:
    responses = default_responses_capabilities()
    responses.update(
        {
            "codex_request_envelope": True,
            "codex_client_tools": True,
            "codex_streaming_tool_events": True,
            "codex_encrypted_reasoning_replay": True,
        }
    )
    return {
        "responses": responses,
        "codex_limits": {
            "context_window_tokens": 1_050_000,
            "default_max_output_tokens": 32_768,
            "max_output_tokens": 128_000,
            **limits,
        },
    }


def _codex_policy(*, max_output_tokens: int | None = None) -> ResponsesPolicyResult:
    body: dict[str, object] = {
        "model": "gpt-5.6-sol",
        "input": "bounded",
        "prompt_cache_key": "safe-session-key",
    }
    if max_output_tokens is not None:
        body["max_output_tokens"] = max_output_tokens
    return ResponsesRequestPolicy(Settings()).apply(
        body,
        allow_codex_request_envelope=True,
        allow_codex_extended_limits=True,
    )


def test_codex_route_default_replaces_only_legacy_injected_default() -> None:
    initial = _codex_policy()
    assert initial.effective_output_tokens == 1024

    final = apply_codex_route_limits(
        initial,
        route_capabilities=_route_capabilities(),
        settings=Settings(),
    )
    assert final.effective_output_tokens == 32_768
    assert final.effective_body["max_output_tokens"] == 32_768
    assert final.codex_limits_applied is True

    explicit = apply_codex_route_limits(
        _codex_policy(max_output_tokens=32_767),
        route_capabilities=_route_capabilities(),
        settings=Settings(),
    )
    assert explicit.effective_output_tokens == 32_767


def test_ordinary_responses_keeps_legacy_default() -> None:
    result = ResponsesRequestPolicy(Settings()).apply({"model": "ordinary", "input": "bounded"})
    assert result.effective_output_tokens == 1024
    assert result.codex_limits_applied is False


def test_codex_compact_reserves_route_maximum_without_forwarding_output_field() -> None:
    compact = ResponsesRequestPolicy(Settings()).apply_compact(
        {
            "model": "gpt-5.6-sol",
            "input": [{"type": "message", "role": "user", "content": "bounded"}],
            "prompt_cache_key": "safe-session-key",
        },
        allow_codex_compaction=True,
    )
    final = apply_codex_route_limits(
        compact,
        route_capabilities=_route_capabilities(),
        settings=Settings(),
        include_output_field=False,
        reserve_route_max_output=True,
    )
    assert final.requested_output_tokens == 128_000
    assert final.effective_output_tokens == 128_000
    assert "max_output_tokens" not in final.effective_body

    with pytest.raises(Exception) as context_exc:
        apply_codex_route_limits(
            compact.model_copy(update={"estimated_input_tokens": 922_001}),
            route_capabilities=_route_capabilities(),
            settings=Settings(),
            include_output_field=False,
            reserve_route_max_output=True,
        )
    assert getattr(context_exc.value, "error_code", None) == (
        "responses_codex_context_window_exceeded"
    )


@pytest.mark.parametrize(
    "metadata",
    [
        {},
        {"codex_limits": {}},
        {
            "codex_limits": {
                "context_window_tokens": 1_050_000,
                "default_max_output_tokens": 32_768,
                "max_output_tokens": 128_000,
                "unknown": 1,
            }
        },
        {
            "codex_limits": {
                "context_window_tokens": 1_050_000.0,
                "default_max_output_tokens": 32_768,
                "max_output_tokens": 128_000,
            }
        },
        {
            "codex_limits": {
                "context_window_tokens": 1_050_000,
                "default_max_output_tokens": True,
                "max_output_tokens": 128_000,
            }
        },
    ],
)
def test_codex_limits_reject_missing_unknown_and_non_integer_metadata(
    metadata: dict[str, object],
) -> None:
    responses = _route_capabilities()["responses"]
    with pytest.raises(Exception) as exc_info:
        enforce_responses_route_capabilities(
            route_capabilities={"responses": responses, **metadata},
            codex_extended_limits_requested=True,
        )
    assert getattr(exc_info.value, "error_code", None) == "responses_codex_limits_invalid"


def test_codex_output_and_context_edges_are_not_clamped() -> None:
    exact = apply_codex_route_limits(
        _codex_policy(max_output_tokens=128_000),
        route_capabilities=_route_capabilities(),
        settings=Settings(),
    )
    assert exact.effective_output_tokens == 128_000
    with pytest.raises(Exception) as max_exc:
        apply_codex_route_limits(
            _codex_policy(max_output_tokens=128_001),
            route_capabilities=_route_capabilities(),
            settings=Settings(),
        )
    assert getattr(max_exc.value, "error_code", None) == "output_token_limit_exceeded"

    edge = _codex_policy(max_output_tokens=128_000).model_copy(
        update={"estimated_input_tokens": 922_000}
    )
    apply_codex_route_limits(
        edge,
        route_capabilities=_route_capabilities(),
        settings=Settings(),
    )
    with pytest.raises(Exception) as context_exc:
        apply_codex_route_limits(
            edge.model_copy(update={"estimated_input_tokens": 922_001}),
            route_capabilities=_route_capabilities(),
            settings=Settings(),
        )
    assert getattr(context_exc.value, "error_code", None) == (
        "responses_codex_context_window_exceeded"
    )


class _PricingRepository:
    def __init__(self, row: SimpleNamespace) -> None:
        self.row = row

    async def find_active_pricing_rule(self, **_kwargs):
        return self.row


class _FxRepository:
    async def find_latest_rate(self, **_kwargs):  # pragma: no cover - EUR avoids lookup
        raise AssertionError("EUR pricing must not look up FX")


def _pricing_row(*, metadata: dict[str, object] | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        provider="openai",
        upstream_model="gpt-5.6-sol",
        endpoint="/v1/responses",
        currency="EUR",
        input_price_per_1m=Decimal("5"),
        cached_input_price_per_1m=Decimal("0.5"),
        output_price_per_1m=Decimal("30"),
        reasoning_price_per_1m=Decimal("30"),
        request_price=None,
        pricing_metadata=metadata
        or {
            "codex_accounting": {
                "cache_write_input_multiplier": "1.25",
                "long_context_threshold_tokens": 272_000,
                "long_context_input_multiplier": "2",
                "long_context_output_multiplier": "1.5",
            }
        },
        valid_from=datetime(2026, 1, 1, tzinfo=UTC),
        valid_until=None,
    )


def _route() -> RouteResolutionResult:
    return RouteResolutionResult(
        requested_model="gpt-5.6-sol",
        resolved_model="gpt-5.6-sol",
        provider="openai",
        route_id=uuid.uuid4(),
        route_match_type="exact",
        route_pattern="gpt-5.6-sol",
        priority=100,
    )


@pytest.mark.asyncio
async def test_codex_admission_uses_maximum_cache_write_and_long_context_rates() -> None:
    service = PricingService(
        pricing_rules_repository=_PricingRepository(_pricing_row()),
        fx_rates_repository=_FxRepository(),
    )
    policy = apply_codex_route_limits(
        _codex_policy(),
        route_capabilities=_route_capabilities(),
        settings=Settings(),
    ).model_copy(update={"estimated_input_tokens": 1_000})
    estimate = await service.estimate_chat_completion_cost(
        route=_route(),
        policy=policy,
        endpoint="/v1/responses",
    )
    assert estimate.estimated_input_cost_native == Decimal("0.0125")
    assert estimate.estimated_output_cost_native == Decimal("1.47456")
    assert estimate.cache_write_input_price_per_1m == Decimal("6.25")
    assert estimate.codex_accounting is True


@pytest.mark.asyncio
async def test_codex_pricing_metadata_rejects_partial_unknown_and_non_decimal() -> None:
    invalid = [
        {"codex_accounting": {"cache_write_input_multiplier": "1.25"}},
        {
            "codex_accounting": {
                "cache_write_input_multiplier": 1.25,
                "long_context_threshold_tokens": 272_000,
                "long_context_input_multiplier": "2",
                "long_context_output_multiplier": "1.5",
            }
        },
        {
            "codex_accounting": {
                "cache_write_input_multiplier": "1.25",
                "long_context_threshold_tokens": 272_000,
                "long_context_input_multiplier": "2",
                "long_context_output_multiplier": "1.5",
                "unknown": "1",
            }
        },
    ]
    for metadata in invalid:
        service = PricingService(
            pricing_rules_repository=_PricingRepository(_pricing_row(metadata=metadata)),
            fx_rates_repository=_FxRepository(),
        )
        with pytest.raises(InvalidPricingDataError):
            await service.find_active_pricing_rule(
                provider="openai",
                model="gpt-5.6-sol",
                endpoint="/v1/responses",
            )


def _accounting_service() -> AccountingService:
    placeholder = SimpleNamespace()
    return AccountingService(
        gateway_keys_repository=placeholder,
        quota_reservations_repository=placeholder,
        usage_ledger_repository=placeholder,
    )


@pytest.mark.parametrize(
    ("prompt_tokens", "expected_long_tier"),
    [(271_999, 0), (272_000, 0), (272_001, 1)],
)
@pytest.mark.asyncio
async def test_codex_actual_cost_threshold_and_disjoint_components(
    prompt_tokens: int,
    expected_long_tier: int,
) -> None:
    pricing = PricingService(
        pricing_rules_repository=_PricingRepository(_pricing_row()),
        fx_rates_repository=_FxRepository(),
    )
    policy = apply_codex_route_limits(
        _codex_policy(),
        route_capabilities=_route_capabilities(),
        settings=Settings(),
    )
    estimate = await pricing.estimate_chat_completion_cost(
        route=_route(), policy=policy, endpoint="/v1/responses"
    )
    cached = 100_000
    cache_write = 50_000
    response = ProviderResponse(
        provider="openai",
        upstream_model="gpt-5.6-sol",
        status_code=200,
        json_body={},
        usage=ProviderUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=10_000,
            total_tokens=prompt_tokens + 10_000,
            cached_tokens=cached,
            cache_write_tokens=cache_write,
            reasoning_tokens=4_000,
            other_usage={
                "input_tokens_details": {
                    "cached_tokens": cached,
                    "cache_write_tokens": cache_write,
                },
                "output_tokens_details": {"reasoning_tokens": 4_000},
            },
        ),
    )
    accounting = _accounting_service()
    usage = accounting.extract_usage(response)
    actual = accounting.compute_actual_cost(response, _route(), usage, estimate)
    assert actual.component_token_counts["input_cached_tokens"] == cached
    assert actual.component_token_counts["input_cache_write_tokens"] == cache_write
    assert actual.component_token_counts["output_reasoning_tokens"] == 4_000
    assert actual.component_token_counts["long_context_tier_applied"] == expected_long_tier


@pytest.mark.asyncio
async def test_codex_contradictory_component_counts_fail_closed() -> None:
    pricing = PricingService(
        pricing_rules_repository=_PricingRepository(_pricing_row()),
        fx_rates_repository=_FxRepository(),
    )
    estimate = await pricing.estimate_chat_completion_cost(
        route=_route(),
        policy=apply_codex_route_limits(
            _codex_policy(),
            route_capabilities=_route_capabilities(),
            settings=Settings(),
        ),
        endpoint="/v1/responses",
    )
    response = ProviderResponse(
        provider="openai",
        upstream_model="gpt-5.6-sol",
        status_code=200,
        json_body={},
        usage=ProviderUsage(
            prompt_tokens=10,
            completion_tokens=2,
            total_tokens=12,
            cached_tokens=8,
            cache_write_tokens=3,
            reasoning_tokens=0,
            other_usage={
                "input_tokens_details": {"cached_tokens": 8, "cache_write_tokens": 3},
                "output_tokens_details": {"reasoning_tokens": 0},
            },
        ),
    )
    accounting = _accounting_service()
    with pytest.raises(UnsupportedProviderCostError):
        accounting.compute_actual_cost(
            response,
            _route(),
            accounting.extract_usage(response),
            estimate,
        )


@pytest.mark.asyncio
async def test_codex_unpartitioned_total_tokens_fail_closed() -> None:
    pricing = PricingService(
        pricing_rules_repository=_PricingRepository(_pricing_row()),
        fx_rates_repository=_FxRepository(),
    )
    estimate = await pricing.estimate_chat_completion_cost(
        route=_route(),
        policy=apply_codex_route_limits(
            _codex_policy(),
            route_capabilities=_route_capabilities(),
            settings=Settings(),
        ),
        endpoint="/v1/responses",
    )
    response = ProviderResponse(
        provider="openai",
        upstream_model="gpt-5.6-sol",
        status_code=200,
        json_body={},
        usage=ProviderUsage(
            prompt_tokens=10,
            completion_tokens=2,
            total_tokens=13,
            cached_tokens=0,
            cache_write_tokens=0,
            reasoning_tokens=0,
            other_usage={
                "input_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 0},
                "output_tokens_details": {"reasoning_tokens": 0},
            },
        ),
    )
    accounting = _accounting_service()
    with pytest.raises(UnsupportedProviderCostError):
        accounting.compute_actual_cost(
            response,
            _route(),
            accounting.extract_usage(response),
            estimate,
        )
