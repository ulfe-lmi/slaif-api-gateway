from __future__ import annotations

from decimal import Decimal

import pytest

from slaif_gateway.schemas.pricing import ExternalToolPricing
from slaif_gateway.services.external_tool_policy_contract import (
    ExternalToolKeyLimitFacts,
    PROVIDER_WEB_SEARCH,
)
from slaif_gateway.services.openai_web_search_contract import (
    WebSearchContractError,
    actual_tool_fee,
    maximum_tool_fee,
    parse_web_search_output,
    parse_web_search_stream,
    validate_web_search_request,
)


def _key_policy(cap: int = 4) -> dict[str, object]:
    return {
        "version": 1,
        "mode": "external_tool_fenced",
        "allowed_capabilities": [PROVIDER_WEB_SEARCH],
        "allowed_destination_ids": [],
        "max_provider_tool_calls_per_request": cap,
        "single_request_overrun_acknowledged": True,
    }


def _route_policy(cap: int = 3) -> dict[str, object]:
    return {
        "version": 1,
        "supported_capabilities": [PROVIDER_WEB_SEARCH],
        "approved_destination_ids": [],
        "max_provider_tool_calls_per_request": cap,
        "call_limit_enforced": True,
        "final_usage_required": True,
        "final_cost_required": True,
    }


def _limits() -> ExternalToolKeyLimitFacts:
    return ExternalToolKeyLimitFacts(
        key_purpose="standard",
        request_limit_total=10,
        token_limit_total=100_000,
        cost_limit_eur=Decimal("5"),
    )


def _request(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "store": False,
        "tools": [{"type": "web_search", "search_context_size": "low"}],
        "max_tool_calls": 2,
    }
    body.update(overrides)
    return body


def test_request_is_exactly_reconstructed_and_policy_bound() -> None:
    facts = validate_web_search_request(
        _request(),
        provider="openai",
        key_policy=_key_policy(),
        route_policy=_route_policy(),
        key_limits=_limits(),
    )

    assert facts.provider_body == {
        "tools": [{"type": "web_search", "search_context_size": "low"}],
        "max_tool_calls": 2,
    }
    assert facts.effective_tool_call_cap == 3
    assert facts.quota_mode == "external_tool_fenced"


@pytest.mark.parametrize(
    "body",
    [
        _request(tools=[{"type": "web_search_preview"}]),
        _request(tools=[{"type": "web_search", "user_location": {}}]),
        _request(tools=[{"type": "web_search"}, {"type": "web_search"}]),
        _request(tools=[{"type": "web_search"}, {"type": "mcp", "server_url": "x"}]),
        _request(max_tool_calls=True),
        _request(max_tool_calls=0),
        _request(max_tool_calls=4),
        _request(store=True),
        _request(tool_choice="required"),
    ],
)
def test_unsupported_or_unsafe_shapes_fail_closed(body: dict[str, object]) -> None:
    with pytest.raises(WebSearchContractError):
        validate_web_search_request(
            body,
            provider="openai",
            key_policy=_key_policy(),
            route_policy=_route_policy(),
            key_limits=_limits(),
        )


def test_client_function_can_coexist_but_other_hosted_tools_cannot() -> None:
    body = _request(
        tools=[
            {"type": "web_search"},
            {"type": "function", "name": "lookup", "parameters": {}},
        ]
    )
    assert validate_web_search_request(
        body,
        provider="openai",
        key_policy=_key_policy(),
        route_policy=_route_policy(),
        key_limits=_limits(),
    ).provider_body["max_tool_calls"] == 2


def test_output_counts_completed_search_once_and_hides_content() -> None:
    secret = "PRIVATE-CANARY-QUERY https://private.invalid token-secret"
    private_id = "private-call-id-token"
    result = parse_web_search_output(
        {
            "status": "completed",
            "output": [
                {
                    "type": "web_search_call",
                    "id": private_id,
                    "status": "completed",
                    "action": {"type": "search", "query": secret},
                },
                {"type": "message", "content": secret},
            ]
        },
        admitted_call_cap=2,
        pricing=ExternalToolPricing("USD", Decimal("0.01"), "openai_published_per_call"),
    )
    assert result.authoritative is True
    assert result.completed_call_count == 1
    assert result.total_tool_fee_native == Decimal("0.01")
    assert secret not in repr(result)
    assert secret not in repr(result.to_safe_dict())
    assert private_id not in repr(result)
    assert private_id not in repr(result.to_safe_dict())


def test_stream_requires_terminal_and_accepts_duplicate_completion_evidence() -> None:
    pricing = ExternalToolPricing("USD", Decimal("0.01"), "openai_published_per_call")
    result = parse_web_search_stream(
        [
            {
                "type": "response.web_search_call.in_progress",
                "item_id": "call_1",
                "output_index": 0,
                "sequence_number": 0,
            },
            {
                "type": "response.web_search_call.completed",
                "item_id": "call_1",
                "output_index": 0,
                "sequence_number": 1,
            },
            {
                "type": "response.output_item.done",
                "output_index": 0,
                "sequence_number": 2,
                "item": {
                    "type": "web_search_call",
                    "id": "call_1",
                    "status": "completed",
                    "action": {"type": "search"},
                },
            },
            {
                "type": "response.completed",
                "sequence_number": 3,
                "response": {"status": "completed", "usage": {}},
            },
        ],
        admitted_call_cap=1,
        pricing=pricing,
    )
    assert result.authoritative is True
    assert result.completed_call_count == 1

    incomplete = parse_web_search_stream(
        [
            {
                "type": "response.web_search_call.searching",
                "item_id": "call_1",
                "output_index": 0,
                "sequence_number": 0,
            }
        ],
        admitted_call_cap=1,
    )
    assert incomplete.authoritative is False
    assert incomplete.reason_code == "stream_terminal_missing"


def test_completed_zero_call_outcomes_are_non_authoritative_without_call_evidence() -> None:
    pricing = ExternalToolPricing("EUR", Decimal("0.010000000"), "openai_published_per_call")
    non_stream = parse_web_search_output(
        {"status": "completed", "output": []},
        admitted_call_cap=2,
        pricing=pricing,
    )
    stream = parse_web_search_stream(
        [
            {
                "type": "response.completed",
                "sequence_number": 0,
                "response": {"status": "completed", "usage": {}},
            }
        ],
        admitted_call_cap=2,
        pricing=pricing,
    )
    assert non_stream.authoritative is False
    assert stream.authoritative is False
    assert non_stream.reason_code == stream.reason_code == "call_evidence_missing"
    assert (
        parse_web_search_output(
            {"status": "completed", "output": []},
            admitted_call_cap=2,
            pricing=pricing,
            tool_choice="required",
        ).reason_code
        == "non_neutral_tool_choice"
    )

    missing_pricing = parse_web_search_output(
        {"status": "completed", "output": []}, admitted_call_cap=2
    )
    assert missing_pricing.authoritative is False
    assert missing_pricing.reason_code == "call_evidence_missing"


def test_official_event_bounds_and_conflicts_require_hold() -> None:
    malformed = parse_web_search_stream(
        [
            {
                "type": "response.web_search_call.completed",
                "item_id": "call_1",
                "output_index": True,
                "sequence_number": 0,
            },
            {"type": "response.completed", "sequence_number": 1},
        ],
        admitted_call_cap=1,
        pricing=ExternalToolPricing("USD", Decimal("0.01"), "openai_published_per_call"),
    )
    assert malformed.authoritative is False
    assert malformed.reason_code == "web_search_lifecycle_invalid"


def test_cap_overflow_and_failed_output_require_hold() -> None:
    result = parse_web_search_output(
        {
            "status": "completed",
            "output": [
                {
                    "type": "web_search_call",
                    "id": "a",
                    "status": "completed",
                    "action": {"type": "search"},
                },
                {
                    "type": "web_search_call",
                    "id": "b",
                    "status": "completed",
                    "action": {"type": "search"},
                },
            ]
        },
        admitted_call_cap=1,
    )
    assert result.authoritative is False
    assert result.reason_code == "call_cap_exceeded"


def test_tool_fee_helpers_are_exact_decimal_arithmetic() -> None:
    pricing = ExternalToolPricing("EUR", Decimal("0.010000000"), "openai_published_per_call")
    assert maximum_tool_fee(3, pricing) == Decimal("0.030000000")
    assert actual_tool_fee(2, pricing) == Decimal("0.020000000")


def test_provider_canary_is_rejected_without_reflection() -> None:
    canary = "PRIVATE-PROVIDER-CANARY"
    result = parse_web_search_output(
        {"status": "completed", "output": []},
        admitted_call_cap=1,
        pricing=ExternalToolPricing("USD", Decimal("0.01"), "openai_published_per_call"),
        provider=canary,
    )
    assert result.authoritative is False
    assert result.reason_code == "provider_not_supported"
    assert canary not in repr(result)
    assert canary not in repr(result.to_safe_dict())


def test_stream_terminal_requires_official_completed_response_and_usage() -> None:
    base_event = {"type": "response.completed", "sequence_number": 0}
    for response in [None, {}, {"status": "incomplete", "usage": {}}, {"status": "completed"}]:
        event = dict(base_event)
        if response is not None:
            event["response"] = response
        result = parse_web_search_stream(
            [event],
            admitted_call_cap=1,
            pricing=ExternalToolPricing("USD", Decimal("0.01"), "openai_published_per_call"),
        )
        assert result.authoritative is False
        assert result.reason_code == "terminal_response_invalid"


def test_non_stream_duplicate_id_at_distinct_positions_requires_hold() -> None:
    result = parse_web_search_output(
        {
            "status": "completed",
            "output": [
                {"type": "web_search_call", "id": "same", "status": "completed", "action": {"type": "search"}},
                {"type": "web_search_call", "id": "same", "status": "completed", "action": {"type": "search"}},
            ],
        },
        admitted_call_cap=2,
        pricing=ExternalToolPricing("USD", Decimal("0.01"), "openai_published_per_call"),
    )
    assert result.authoritative is False
    assert result.reason_code == "conflicting_call_evidence"


@pytest.mark.parametrize(
    "action",
    [
        {"type": "search", "query": "q", "queries": ["q2"], "sources": [{"type": "url", "url": "https://example.invalid"}]},
        {"type": "open_page", "url": "https://example.invalid"},
        {"type": "find_in_page", "url": "https://example.invalid", "pattern": "needle"},
    ],
)
def test_official_action_variants_are_validated_without_retention(action: dict[str, object]) -> None:
    secret = "PRIVATE-ACTION-CANARY"
    action = {key: (secret if key in {"query", "url", "pattern"} else value) for key, value in action.items()}
    result = parse_web_search_output(
        {
            "status": "completed",
            "output": [{"type": "web_search_call", "id": "call", "status": "completed", "action": action}],
        },
        admitted_call_cap=1,
        pricing=ExternalToolPricing("USD", Decimal("0.01"), "openai_published_per_call"),
    )
    assert result.authoritative is True
    assert secret not in repr(result)
    assert secret not in repr(result.to_safe_dict())


@pytest.mark.parametrize(
    "action",
    [
        {"type": "search", "query": 1},
        {"type": "search", "unknown": "x"},
        {"type": "open_page", "url": 1},
        {"type": "find_in_page", "url": "x"},
        {"type": "find_in_page", "url": "x", "pattern": "y", "extra": "z"},
    ],
)
def test_malformed_official_actions_require_hold(action: dict[str, object]) -> None:
    result = parse_web_search_output(
        {
            "status": "completed",
            "output": [{"type": "web_search_call", "id": "call", "status": "completed", "action": action}],
        },
        admitted_call_cap=1,
        pricing=ExternalToolPricing("USD", Decimal("0.01"), "openai_published_per_call"),
    )
    assert result.authoritative is False
    assert result.reason_code == "output_item_invalid"
