from __future__ import annotations

from decimal import Decimal

import pytest

from slaif_gateway.schemas.pricing import ChatCostEstimate
from slaif_gateway.services.chat_streaming_live_burn import (
    ChatStreamingLiveBurnMonitor,
    ChatStreamingLiveBurnPolicyError,
    build_chat_streaming_live_burn_budget,
    generated_chat_streaming_delta_text,
    metadata_with_chat_streaming_live_burn_policy,
    normalize_chat_streaming_live_burn_policy,
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
    metadata = metadata_with_chat_streaming_live_burn_policy(
        {},
        None,
        max_abs_cost_margin_eur=Decimal("100"),
        max_abs_token_margin=1000,
    )

    assert metadata["chat_streaming_live_burn"] == {
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
    policy = normalize_chat_streaming_live_burn_policy(
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


def test_invalid_decimal_and_non_integer_token_margin_are_rejected() -> None:
    with pytest.raises(ChatStreamingLiveBurnPolicyError):
        normalize_chat_streaming_live_burn_policy(
            {"enabled": True, "cost_margin_eur": "NaN", "token_margin": 0},
            max_abs_cost_margin_eur=Decimal("10"),
            max_abs_token_margin=100,
        )

    with pytest.raises(ChatStreamingLiveBurnPolicyError):
        normalize_chat_streaming_live_burn_policy(
            {"enabled": True, "cost_margin_eur": "0", "token_margin": "1.5"},
            max_abs_cost_margin_eur=Decimal("10"),
            max_abs_token_margin=100,
        )


def test_absurd_margins_are_rejected_by_bounds() -> None:
    with pytest.raises(ChatStreamingLiveBurnPolicyError):
        normalize_chat_streaming_live_burn_policy(
            {"enabled": True, "cost_margin_eur": "11", "token_margin": 0},
            max_abs_cost_margin_eur=Decimal("10"),
            max_abs_token_margin=100,
        )

    with pytest.raises(ChatStreamingLiveBurnPolicyError):
        normalize_chat_streaming_live_burn_policy(
            {"enabled": True, "cost_margin_eur": "0", "token_margin": 101},
            max_abs_cost_margin_eur=Decimal("10"),
            max_abs_token_margin=100,
        )


def test_disabled_policy_does_not_build_runtime_budget() -> None:
    policy = normalize_chat_streaming_live_burn_policy(
        {"enabled": False, "cost_margin_eur": "-5", "token_margin": -500},
        max_abs_cost_margin_eur=Decimal("10"),
        max_abs_token_margin=1000,
    )

    budget = build_chat_streaming_live_burn_budget(
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


def test_cutoff_math_excludes_current_reservation() -> None:
    policy = normalize_chat_streaming_live_burn_policy(
        {"enabled": True, "cost_margin_eur": "0.20", "token_margin": 20},
        max_abs_cost_margin_eur=Decimal("10"),
        max_abs_token_margin=1000,
    )

    budget = build_chat_streaming_live_burn_budget(
        policy=policy,
        cost_limit_eur=Decimal("1.00"),
        token_limit_total=1000,
        cost_used_eur=Decimal("0.10"),
        tokens_used_total=100,
        cost_reserved_eur=Decimal("0.25"),
        tokens_reserved_total=150,
        current_reserved_cost_eur=Decimal("0.05"),
        current_reserved_tokens=50,
        cost_estimate=_estimate(),
        estimate_multiplier=Decimal("1"),
    )

    assert budget is not None
    assert budget.cost_cutoff_eur == Decimal("0.50")
    assert budget.token_cutoff == 780


def test_estimator_counts_content_tool_deltas_and_multiple_choices_without_extra_multiplier() -> None:
    text = generated_chat_streaming_delta_text(
        {
            "choices": [
                {"delta": {"content": "hello"}},
                {
                    "delta": {
                        "tool_calls": [
                            {"function": {"name": "lookup", "arguments": '{"q":"x"}'}}
                        ]
                    }
                },
            ]
        }
    )

    assert text == 'hellolookup{"q":"x"}'


def test_monitor_records_safe_stop_metadata_without_chunk_text() -> None:
    policy = normalize_chat_streaming_live_burn_policy(
        {"enabled": True, "cost_margin_eur": "0", "token_margin": 0},
        max_abs_cost_margin_eur=Decimal("10"),
        max_abs_token_margin=1000,
    )
    budget = build_chat_streaming_live_burn_budget(
        policy=policy,
        cost_limit_eur=None,
        token_limit_total=15,
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

    monitor = ChatStreamingLiveBurnMonitor(budget)
    result = monitor.observe_chunk({"choices": [{"delta": {"content": "secret streamed text"}}]})

    assert result is not None
    assert result.stop_reason == "tokens"
    serialized = str(result.metadata)
    assert "secret streamed text" not in serialized
    assert result.metadata["estimate_is_invoice_grade"] is False
