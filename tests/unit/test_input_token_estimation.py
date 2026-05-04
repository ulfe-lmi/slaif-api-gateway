from __future__ import annotations

import copy

import pytest

from slaif_gateway.services.input_token_estimation import (
    canonical_json_bytes,
    estimate_chat_completion_input_tokens,
    estimate_message_input_tokens,
    estimate_non_message_input_tokens,
    estimate_serialized_json_input_tokens,
)


def _messages() -> list[dict[str, object]]:
    return [{"role": "user", "content": "hello"}]


def test_messages_only_estimate_matches_existing_message_estimator() -> None:
    messages = _messages()
    estimate = estimate_chat_completion_input_tokens(
        {"model": "gpt-4.1-mini", "messages": messages},
        messages=messages,
    )

    assert estimate.message_input_tokens_estimate == estimate_message_input_tokens(messages)
    assert estimate.non_message_input_tokens_estimate == 0
    assert estimate.total_input_tokens_estimate == estimate.message_input_tokens_estimate
    assert estimate.counted_fields == ()


def test_tools_json_schema_contributes_non_message_estimate() -> None:
    messages = _messages()
    body = {
        "model": "gpt-4.1-mini",
        "messages": messages,
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "lookup",
                    "parameters": {
                        "type": "object",
                        "properties": {"query": {"type": "string", "description": "x" * 200}},
                    },
                },
            }
        ],
    }

    estimate = estimate_chat_completion_input_tokens(body, messages=messages)

    assert estimate.non_message_input_tokens_estimate >= len(canonical_json_bytes({"tools": body["tools"]}))
    assert estimate.total_input_tokens_estimate > estimate.message_input_tokens_estimate
    assert estimate.counted_fields == ("tools",)


def test_response_format_json_schema_contributes_non_message_estimate() -> None:
    messages = _messages()
    body = {
        "model": "gpt-4.1-mini",
        "messages": messages,
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "answer",
                "schema": {"type": "object", "properties": {"answer": {"type": "string"}}},
            },
        },
    }

    estimate = estimate_chat_completion_input_tokens(body, messages=messages)

    assert estimate.non_message_input_tokens_estimate == len(
        canonical_json_bytes({"response_format": body["response_format"]})
    )
    assert estimate.counted_fields == ("response_format",)


def test_functions_contribute_non_message_estimate() -> None:
    messages = _messages()
    body = {
        "model": "gpt-4.1-mini",
        "messages": messages,
        "functions": [
            {
                "name": "legacy_lookup",
                "parameters": {"type": "object", "properties": {"query": {"type": "string"}}},
            }
        ],
    }

    estimate = estimate_non_message_input_tokens(body)

    assert estimate.input_tokens_estimate == len(canonical_json_bytes({"functions": body["functions"]}))
    assert estimate.counted_fields == ("functions",)


def test_unknown_extra_object_and_list_passthrough_fields_are_counted() -> None:
    body = {
        "model": "gpt-4.1-mini",
        "messages": _messages(),
        "x_unknown_object": {"large": "x" * 50},
        "x_unknown_list": [{"item": "y" * 50}],
    }

    estimate = estimate_non_message_input_tokens(body)

    assert estimate.counted_fields == ("x_unknown_list", "x_unknown_object")
    assert estimate.input_tokens_estimate == (
        len(canonical_json_bytes({"x_unknown_list": body["x_unknown_list"]}))
        + len(canonical_json_bytes({"x_unknown_object": body["x_unknown_object"]}))
    )


def test_scalar_controls_do_not_break_estimation() -> None:
    body = {
        "model": "gpt-4.1-mini",
        "messages": _messages(),
        "temperature": 0.2,
        "top_p": 0.9,
        "tool_choice": "auto",
        "max_completion_tokens": 20,
        "parallel_tool_calls": True,
    }

    estimate = estimate_non_message_input_tokens(body)

    assert estimate.input_tokens_estimate == 0
    assert estimate.counted_fields == ()


def test_canonicalization_is_deterministic() -> None:
    left = {"b": [2, 1], "a": {"z": "last", "m": "middle"}}
    right = {"a": {"m": "middle", "z": "last"}, "b": [2, 1]}

    assert canonical_json_bytes(left) == canonical_json_bytes(right)
    assert estimate_serialized_json_input_tokens(left) == estimate_serialized_json_input_tokens(right)


def test_estimator_result_does_not_include_raw_schema_values() -> None:
    body = {
        "model": "gpt-4.1-mini",
        "messages": _messages(),
        "response_format": {
            "type": "json_schema",
            "json_schema": {"schema": {"description": "secret raw schema marker"}},
        },
    }

    estimate = estimate_chat_completion_input_tokens(body, messages=body["messages"])

    assert "secret raw schema marker" not in repr(estimate)
    assert estimate.counted_fields == ("response_format",)


def test_estimator_does_not_mutate_input_body() -> None:
    body = {
        "model": "gpt-4.1-mini",
        "messages": _messages(),
        "tools": [{"type": "function", "function": {"name": "lookup"}}],
    }
    original = copy.deepcopy(body)

    _ = estimate_chat_completion_input_tokens(body, messages=body["messages"])

    assert body == original


def test_non_serializable_values_are_rejected_before_forwarding() -> None:
    body = {
        "model": "gpt-4.1-mini",
        "messages": _messages(),
        "x_bad": {"not_json": object()},
    }

    with pytest.raises(ValueError):
        estimate_non_message_input_tokens(body)
