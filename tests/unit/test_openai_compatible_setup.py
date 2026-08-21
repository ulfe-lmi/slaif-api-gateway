from __future__ import annotations

from decimal import Decimal
from dataclasses import replace

import pytest

from slaif_gateway.services.openai_compatible_setup import (
    CHAT_AND_RESPONSES_TEXT_PRESET,
    CHAT_TEXT_PRESET,
    EXPLICIT_PRICING,
    LOCAL_ZERO_PRICING,
    SetupError,
    SetupRequest,
    _capabilities,
    _normalize_request,
    _pricing_values,
    _preset_endpoints,
)


def test_presets_have_only_the_bounded_endpoint_families() -> None:
    assert _preset_endpoints(CHAT_TEXT_PRESET) == ("/v1/chat/completions",)
    assert _preset_endpoints("responses_text_v1") == ("/v1/responses",)
    assert _preset_endpoints(CHAT_AND_RESPONSES_TEXT_PRESET) == (
        "/v1/chat/completions",
        "/v1/responses",
    )


def test_capabilities_are_conservative_and_function_tools_are_explicit() -> None:
    chat = _capabilities("/v1/chat/completions", streaming=True, local_function_tools=False)["chat_completions"]
    responses = _capabilities("/v1/responses", streaming=True, local_function_tools=True)["responses"]
    assert chat["chat_text"] is True
    assert chat["chat_streaming"] is True
    assert chat["chat_function_tools"] is False
    assert chat["hosted_web_search"] is False
    assert chat["chat_multimodal"] is False
    assert responses["text"] is True
    assert responses["stateless"] is True
    assert responses["function_tools"] is True
    assert responses["storage"] is False
    assert responses["codex_request_envelope"] is False


def test_local_zero_and_explicit_pricing_are_exact_and_labeled() -> None:
    request = SetupRequest(
        provider="lan-qwen",
        selected_models=("qwen/a",),
        preset=CHAT_TEXT_PRESET,
        pricing_mode=LOCAL_ZERO_PRICING,
        reason="operator confirmed local test backend",
    )
    assert _pricing_values(request) == (
        Decimal("0"),
        Decimal("0"),
        {"pricing_basis": "operator_confirmed_local_zero"},
    )
    explicit = replace(
        request,
        pricing_mode=EXPLICIT_PRICING,
        input_price_per_1m="0.125",
        output_price_per_1m="1.25",
    )
    assert _pricing_values(explicit)[:2] == (Decimal("0.125"), Decimal("1.25"))


@pytest.mark.parametrize(
    "candidate",
    [
        SetupRequest(provider="lan-qwen", selected_models=(), preset=CHAT_TEXT_PRESET, reason="reason"),
        SetupRequest(provider="lan-qwen", selected_models=("qwen/a", "qwen/a"), preset=CHAT_TEXT_PRESET, reason="reason"),
        SetupRequest(provider="lan-qwen", selected_models=("sk-secret",), preset=CHAT_TEXT_PRESET, reason="reason"),
        SetupRequest(provider="lan-qwen", selected_models=("qwen/a",), preset=CHAT_TEXT_PRESET, reason=""),
    ],
)
def test_setup_rejects_unsafe_or_incomplete_confirmation(candidate: SetupRequest) -> None:
    with pytest.raises(SetupError):
        _normalize_request(candidate)
