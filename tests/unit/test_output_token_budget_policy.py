"""Forwarded limits and accounting exposure agree without inflating client budgets."""

import copy

import pytest

from slaif_gateway.config import Settings
from slaif_gateway.modules.clients.codex_0147 import CODEX_0147_POLICY_SPEC
from slaif_gateway.services.request_policy import ChatCompletionRequestPolicy
from slaif_gateway.services.responses_request_policy import (
    ResponsesRequestPolicy,
    apply_codex_route_limits,
)
from slaif_gateway.services.realtime_request_policy import RealtimeRequestPolicy
from tests.unit.test_realtime_request_policy import _minimal_body

KINDS = (
    "chat_legacy",
    "chat_completion",
    "chat_both",
    "chat_choices",
    "responses",
    "codex",
    "realtime",
)


def budget_case(kind, requested):
    settings = Settings(
        DEFAULT_MAX_OUTPUT_TOKENS=12,
        HARD_MAX_OUTPUT_TOKENS=40,
        HARD_MAX_INPUT_TOKENS=10000,
        CODEX_ABSOLUTE_MAX_OUTPUT_TOKENS=80,
        RESPONSES_COMPACT_DEFAULT_MAX_OUTPUT_TOKENS=8,
        RESPONSES_COMPACT_HARD_MAX_OUTPUT_TOKENS=20,
        REALTIME_DEFAULT_MAX_OUTPUT_TOKENS=12,
        REALTIME_MAX_OUTPUT_TOKENS=40,
        REALTIME_ALLOWED_VOICES="cedar",
    )
    caps = {
        "codex_limits": {
            "context_window_tokens": 10000,
            "default_max_output_tokens": 24,
            "max_output_tokens": 60,
        }
    }
    if kind.startswith("chat"):
        body = {"model": "budget-test", "messages": [{"role": "user", "content": "hi"}]}
        names = ["max_tokens"] if kind == "chat_legacy" else ["max_completion_tokens"]
        if kind == "chat_both":
            names = ["max_tokens", "max_completion_tokens"]
        if requested is not None:
            body.update({name: requested for name in names})
        if kind == "chat_choices":
            body["n"] = 3
        original = copy.deepcopy(body)
        result = ChatCompletionRequestPolicy(settings).apply(body)
        assert body == original
        forwarded = result.effective_body.get(
            "max_completion_tokens", result.effective_body.get("max_tokens")
        )
        if requested is not None:
            assert all(result.effective_body[name] == forwarded for name in names)
    elif kind == "realtime":
        body = _minimal_body()
        if requested is not None:
            body["session"]["max_output_tokens"] = requested
        original = copy.deepcopy(body)
        result = RealtimeRequestPolicy(settings).apply_client_secret_create(body)
        assert body == original
        forwarded = result.effective_body["session"]["max_output_tokens"]
    else:
        body = {"model": "budget-test", "input": "hi"}
        if requested is not None:
            body["max_output_tokens"] = requested
        original = copy.deepcopy(body)
        policy = ResponsesRequestPolicy(settings, client_spec=CODEX_0147_POLICY_SPEC)
        if kind in {"compact", "codex_compact"}:
            assert requested is None
            if kind == "codex_compact":
                body["prompt_cache_key"] = "synthetic"
            result = policy.apply_compact(body, allow_codex_compaction=kind == "codex_compact")
        else:
            result = policy.apply(
                body,
                allow_codex_request_envelope=kind == "codex",
                allow_codex_extended_limits=kind == "codex",
            )
        if kind == "codex":
            result = apply_codex_route_limits(result, route_capabilities=caps, settings=settings)
        if kind == "codex_compact":
            result = apply_codex_route_limits(
                result, route_capabilities=caps, settings=settings, include_output_field=False
            )
        if kind != "codex_compact":
            assert body == original
        forwarded = result.effective_body.get("max_output_tokens")
    maximum = 60 if kind == "codex" else 40
    default = 24 if kind == "codex" else 12
    expected = min(default if requested is None else requested, maximum)
    if kind in {"compact", "codex_compact"}:
        expected = 8
    return result, forwarded, expected


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("requested", [None, 5, 40, 60, 1000000])
def test_forwarded_budget_matches_reservation_output_component(kind, requested):
    result, forwarded, expected = budget_case(kind, requested)
    assert forwarded == expected
    choices = 3 if kind == "chat_choices" else 1
    assert result.effective_output_tokens == forwarded * choices
    if kind != "realtime":
        assert result.injected_default_output_tokens is (requested is None)
        if requested is not None:
            assert result.requested_output_tokens == requested


@pytest.mark.parametrize("kind", ["compact", "codex_compact"])
def test_compact_reserves_its_own_default_without_adding_unsupported_fields(kind):
    result, forwarded, expected = budget_case(kind, None)
    assert forwarded is None
    assert result.effective_output_tokens == expected == 8


@pytest.mark.parametrize("values", [(100, 200), (5, 6)])
def test_conflicting_aliases_are_rejected_before_clipping(values):
    from slaif_gateway.services.policy_errors import AmbiguousOutputTokenLimitError

    with pytest.raises(AmbiguousOutputTokenLimitError):
        ChatCompletionRequestPolicy(
            Settings(HARD_MAX_OUTPUT_TOKENS=40, DEFAULT_MAX_OUTPUT_TOKENS=12)
        ).apply(
            {
                "model": "test",
                "messages": [{"role": "user", "content": "hi"}],
                "max_tokens": values[0],
                "max_completion_tokens": values[1],
            }
        )


@pytest.mark.parametrize("bad", [False, True, 0, -1, 1.5, "5"])
def test_both_aliases_are_validated_even_when_equal_to_the_other_field(bad):
    from slaif_gateway.services.policy_errors import InvalidOutputTokenLimitError

    with pytest.raises(InvalidOutputTokenLimitError):
        ChatCompletionRequestPolicy(Settings()).apply(
            {
                "model": "test",
                "messages": [{"role": "user", "content": "hi"}],
                "max_tokens": bad,
                "max_completion_tokens": 1,
            }
        )


def test_route_revalidation_uses_the_original_requested_budget():
    result, _, _ = budget_case("codex", 1000)
    assert result.effective_output_tokens == 60
    caps = {
        "codex_limits": {
            "context_window_tokens": 10000,
            "default_max_output_tokens": 5,
            "max_output_tokens": 20,
        }
    }
    updated = apply_codex_route_limits(
        result, route_capabilities=caps, settings=Settings(CODEX_ABSOLUTE_MAX_OUTPUT_TOKENS=80)
    )
    assert updated.requested_output_tokens == 1000
    assert updated.effective_output_tokens == updated.effective_body["max_output_tokens"] == 20
    small, _, _ = budget_case("codex", 3)
    updated = apply_codex_route_limits(small, route_capabilities=caps, settings=Settings())
    assert updated.effective_output_tokens == updated.effective_body["max_output_tokens"] == 3
