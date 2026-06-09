from __future__ import annotations

from decimal import Decimal

import pytest

from slaif_gateway.schemas.pricing import ChatCostEstimate
from slaif_gateway.services.responses_streaming_live_burn import (
    RESPONSES_STREAMING_LIVE_BURN_METADATA_KEY,
    ResponsesStreamingLiveBurnMonitor,
    ResponsesStreamingLiveBurnPolicyError,
    safe_responses_streaming_interrupted_estimate_metadata,
    build_responses_streaming_live_burn_budget,
    generated_responses_streaming_delta_text,
    metadata_with_responses_streaming_live_burn_policy,
    normalize_responses_streaming_live_burn_policy,
)


def _estimate() -> ChatCostEstimate:
    return ChatCostEstimate(
        provider="openai",
        requested_model="classroom",
        resolved_model="gpt-test",
        native_currency="EUR",
        estimated_input_tokens=10,
        estimated_output_tokens=100,
        estimated_input_cost_native=Decimal("0.000010000"),
        estimated_output_cost_native=Decimal("0.000100000"),
        estimated_total_cost_native=Decimal("0.000110000"),
        estimated_total_cost_eur=Decimal("0.000110000"),
        pricing_rule_id=None,
        fx_rate_id=None,
        input_price_per_1m=Decimal("1.000000000"),
        output_price_per_1m=Decimal("1.000000000"),
        fx_rate=Decimal("1"),
    )


def test_absent_metadata_defaults_to_enabled_zero_margins() -> None:
    metadata = metadata_with_responses_streaming_live_burn_policy(
        {},
        None,
        max_abs_cost_margin_eur=Decimal("100"),
        max_abs_token_margin=1000,
    )

    assert metadata[RESPONSES_STREAMING_LIVE_BURN_METADATA_KEY] == {
        "version": 1,
        "enabled": True,
        "cost_margin_eur": "0.000000000",
        "token_margin": 0,
    }


@pytest.mark.parametrize("cost_margin", ["1.25", "0", "-1.25"])
@pytest.mark.parametrize("token_margin", [10, 0, -10])
def test_positive_zero_and_negative_margins_are_accepted(
    cost_margin: str,
    token_margin: int,
) -> None:
    policy = normalize_responses_streaming_live_burn_policy(
        {
            "version": 1,
            "enabled": True,
            "cost_margin_eur": cost_margin,
            "token_margin": token_margin,
        },
        max_abs_cost_margin_eur=Decimal("10"),
        max_abs_token_margin=100,
    )

    assert policy.cost_margin_eur == Decimal(cost_margin)
    assert policy.token_margin == token_margin


def test_disabled_policy_does_not_build_runtime_budget() -> None:
    policy = normalize_responses_streaming_live_burn_policy(
        {"enabled": False, "cost_margin_eur": "-5", "token_margin": -500},
        max_abs_cost_margin_eur=Decimal("10"),
        max_abs_token_margin=1000,
    )

    budget = build_responses_streaming_live_burn_budget(
        policy=policy,
        cost_limit_eur=Decimal("1"),
        token_limit_total=100,
        cost_used_eur=Decimal("0"),
        tokens_used_total=0,
        cost_reserved_eur=Decimal("0.1"),
        tokens_reserved_total=10,
        current_reserved_cost_eur=Decimal("0.1"),
        current_reserved_tokens=10,
        cost_estimate=_estimate(),
        estimate_multiplier=Decimal("1.15"),
    )

    assert budget is None


def test_invalid_policy_shapes_are_rejected() -> None:
    with pytest.raises(ResponsesStreamingLiveBurnPolicyError):
        normalize_responses_streaming_live_burn_policy(
            {"enabled": True, "cost_margin_eur": "NaN", "token_margin": 0},
            max_abs_cost_margin_eur=Decimal("10"),
            max_abs_token_margin=100,
        )

    with pytest.raises(ResponsesStreamingLiveBurnPolicyError):
        normalize_responses_streaming_live_burn_policy(
            {"enabled": True, "cost_margin_eur": "0", "token_margin": "1.5"},
            max_abs_cost_margin_eur=Decimal("10"),
            max_abs_token_margin=100,
        )


def test_responses_delta_extractor_counts_only_output_text_delta() -> None:
    assert generated_responses_streaming_delta_text(
        {"type": "response.output_text.delta", "delta": "hello"}
    ) == "hello"
    assert generated_responses_streaming_delta_text({"type": "response.created"}) == ""
    assert generated_responses_streaming_delta_text(
        {"type": "response.output_text.delta", "delta": {"nested": "nope"}}
    ) == ""


def test_safe_lifecycle_events_do_not_change_accounting() -> None:
    policy = normalize_responses_streaming_live_burn_policy(
        {"enabled": True, "cost_margin_eur": "0", "token_margin": 0},
        max_abs_cost_margin_eur=Decimal("10"),
        max_abs_token_margin=1000,
    )
    budget = build_responses_streaming_live_burn_budget(
        policy=policy,
        cost_limit_eur=None,
        token_limit_total=50,
        cost_used_eur=Decimal("0"),
        tokens_used_total=0,
        cost_reserved_eur=Decimal("0"),
        tokens_reserved_total=0,
        current_reserved_cost_eur=Decimal("0"),
        current_reserved_tokens=0,
        cost_estimate=_estimate(),
        estimate_multiplier=Decimal("1"),
    )
    assert budget is not None
    monitor = ResponsesStreamingLiveBurnMonitor(budget)

    assert monitor.observe_chunk({"type": "response.created", "response": {"id": "resp"}}) is None
    assert monitor.estimated_output_tokens == 0


def test_interrupted_estimate_metadata_never_contains_streamed_text() -> None:
    metadata = safe_responses_streaming_interrupted_estimate_metadata(
        estimated_input_tokens=10,
        estimated_output_tokens=5,
        estimated_total_tokens=15,
        estimated_cost_eur=Decimal("0.000015000"),
        interruption_reason="responses_streaming_provider_error_estimated",
        final_provider_usage_available=False,
    )

    assert metadata["estimate_is_invoice_grade"] is False
    assert metadata["stream_interruption_reason"] == "responses_streaming_provider_error_estimated"
    assert "secret streamed text" not in str(metadata)


def test_monitor_stays_below_threshold_until_delta_crosses_it() -> None:
    policy = normalize_responses_streaming_live_burn_policy(
        {"enabled": True, "cost_margin_eur": "0", "token_margin": 0},
        max_abs_cost_margin_eur=Decimal("10"),
        max_abs_token_margin=1000,
    )
    budget = build_responses_streaming_live_burn_budget(
        policy=policy,
        cost_limit_eur=None,
        token_limit_total=22,
        cost_used_eur=Decimal("0"),
        tokens_used_total=0,
        cost_reserved_eur=Decimal("0"),
        tokens_reserved_total=0,
        current_reserved_cost_eur=Decimal("0"),
        current_reserved_tokens=0,
        cost_estimate=_estimate(),
        estimate_multiplier=Decimal("1"),
    )
    assert budget is not None
    monitor = ResponsesStreamingLiveBurnMonitor(budget)

    assert monitor.check() is None

    result = monitor.observe_chunk({"type": "response.output_text.delta", "delta": "tiny"})
    assert result is None

    result = monitor.observe_chunk(
        {
            "type": "response.output_text.delta",
            "delta": "secret streamed text " * 20,
        }
    )
    assert result is not None
    assert result.stop_reason == "tokens"
    assert "secret streamed text" not in str(result.metadata)


def test_monitor_can_abort_on_cost_threshold() -> None:
    policy = normalize_responses_streaming_live_burn_policy(
        {"enabled": True, "cost_margin_eur": "0", "token_margin": -1000},
        max_abs_cost_margin_eur=Decimal("10"),
        max_abs_token_margin=1000,
    )
    budget = build_responses_streaming_live_burn_budget(
        policy=policy,
        cost_limit_eur=Decimal("0.000020000"),
        token_limit_total=None,
        cost_used_eur=Decimal("0"),
        tokens_used_total=0,
        cost_reserved_eur=Decimal("0"),
        tokens_reserved_total=0,
        current_reserved_cost_eur=Decimal("0"),
        current_reserved_tokens=0,
        cost_estimate=_estimate(),
        estimate_multiplier=Decimal("1"),
    )
    assert budget is not None
    monitor = ResponsesStreamingLiveBurnMonitor(budget)

    result = monitor.observe_chunk(
        {"type": "response.output_text.delta", "delta": "this should cross the cost cutoff"}
    )
    assert result is not None
    assert result.stop_reason == "cost"


def test_zero_and_positive_token_margins_shift_abort_threshold() -> None:
    zero_margin_policy = normalize_responses_streaming_live_burn_policy(
        {"enabled": True, "cost_margin_eur": "0", "token_margin": 0},
        max_abs_cost_margin_eur=Decimal("10"),
        max_abs_token_margin=1000,
    )
    positive_margin_policy = normalize_responses_streaming_live_burn_policy(
        {"enabled": True, "cost_margin_eur": "0", "token_margin": 5},
        max_abs_cost_margin_eur=Decimal("10"),
        max_abs_token_margin=1000,
    )
    zero_budget = build_responses_streaming_live_burn_budget(
        policy=zero_margin_policy,
        cost_limit_eur=None,
        token_limit_total=20,
        cost_used_eur=Decimal("0"),
        tokens_used_total=0,
        cost_reserved_eur=Decimal("0"),
        tokens_reserved_total=0,
        current_reserved_cost_eur=Decimal("0"),
        current_reserved_tokens=0,
        cost_estimate=_estimate(),
        estimate_multiplier=Decimal("1"),
    )
    positive_budget = build_responses_streaming_live_burn_budget(
        policy=positive_margin_policy,
        cost_limit_eur=None,
        token_limit_total=20,
        cost_used_eur=Decimal("0"),
        tokens_used_total=0,
        cost_reserved_eur=Decimal("0"),
        tokens_reserved_total=0,
        current_reserved_cost_eur=Decimal("0"),
        current_reserved_tokens=0,
        cost_estimate=_estimate(),
        estimate_multiplier=Decimal("1"),
    )
    assert zero_budget is not None
    assert positive_budget is not None
    assert zero_budget.token_cutoff == 20
    assert positive_budget.token_cutoff == 15
