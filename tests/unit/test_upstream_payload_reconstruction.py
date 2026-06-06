from __future__ import annotations

import copy

import pytest

from slaif_gateway.config import Settings
from slaif_gateway.services.key_modes import CAPABILITY_POLICY_MODE_TRUSTED_CALIBRATION_DISCOVERY
from slaif_gateway.services.policy_errors import RequestPolicyError
from slaif_gateway.services.request_policy import ChatCompletionRequestPolicy
from slaif_gateway.services.responses_request_policy import ResponsesRequestPolicy
from slaif_gateway.services.upstream_payloads import (
    build_chat_completion_upstream_body,
    build_responses_upstream_body,
)


def _settings(**overrides: object) -> Settings:
    values = {
        "DEFAULT_MAX_OUTPUT_TOKENS": 12,
        "HARD_MAX_OUTPUT_TOKENS": 80,
        "HARD_MAX_INPUT_TOKENS": 20_000,
    }
    values.update(overrides)
    return Settings(**values)


def _chat_policy_result(body: dict[str, object], **settings_overrides: object):
    return ChatCompletionRequestPolicy(_settings(**settings_overrides)).apply(body)


def _trusted_chat_policy_result(body: dict[str, object], **settings_overrides: object):
    return ChatCompletionRequestPolicy(_settings(**settings_overrides)).apply(
        body,
        capability_policy_mode=CAPABILITY_POLICY_MODE_TRUSTED_CALIBRATION_DISCOVERY,
    )


def _responses_policy_result(body: dict[str, object], **settings_overrides: object):
    return ResponsesRequestPolicy(_settings(**settings_overrides)).apply(body)


def test_chat_minimal_text_request_reconstructs_exact_upstream_body() -> None:
    inbound = {
        "model": "classroom-alias",
        "messages": [{"role": "user", "content": "hello"}],
    }
    original = copy.deepcopy(inbound)

    policy_result = _chat_policy_result(inbound)
    outbound = build_chat_completion_upstream_body(
        policy_result.effective_body,
        upstream_model="gpt-4.1-mini",
    )

    assert outbound == {
        "model": "gpt-4.1-mini",
        "messages": [{"role": "user", "content": "hello"}],
        "max_completion_tokens": 12,
    }
    assert inbound == original
    assert outbound is not inbound
    assert outbound["messages"] is not inbound["messages"]

    outbound["messages"][0]["content"] = "mutated"
    inbound["messages"][0]["content"] = "changed after build"
    assert policy_result.effective_body["messages"][0]["content"] == "hello"


def test_chat_scalar_function_and_response_format_fields_are_reconstructed_exactly() -> None:
    inbound = {
        "model": "classroom-alias",
        "messages": [{"role": "user", "content": "hello"}],
        "temperature": 0.2,
        "top_p": 0.9,
        "presence_penalty": -0.1,
        "frequency_penalty": 0.4,
        "seed": 123,
        "logprobs": True,
        "top_logprobs": 2,
        "user": "student-1",
        "stop": ["END"],
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "lookup",
                    "description": "safe local lookup",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "authorization": {
                                "type": "string",
                                "description": "local schema metadata only",
                            }
                        },
                    },
                },
            }
        ],
        "tool_choice": {"type": "function", "function": {"name": "lookup"}},
        "parallel_tool_calls": True,
        "response_format": {"type": "json_schema", "json_schema": {"name": "answer"}},
        "metadata": {"safe": "value"},
        "reasoning_effort": "low",
        "max_tokens": 20,
    }

    policy_result = _chat_policy_result(inbound)
    outbound = build_chat_completion_upstream_body(
        policy_result.effective_body,
        upstream_model="gpt-4.1-mini",
    )

    assert outbound == {
        "model": "gpt-4.1-mini",
        "messages": [{"role": "user", "content": "hello"}],
        "temperature": 0.2,
        "top_p": 0.9,
        "stop": ["END"],
        "seed": 123,
        "user": "student-1",
        "logprobs": True,
        "top_logprobs": 2,
        "presence_penalty": -0.1,
        "frequency_penalty": 0.4,
        "max_tokens": 20,
        "tools": inbound["tools"],
        "tool_choice": {"type": "function", "function": {"name": "lookup"}},
        "response_format": {"type": "json_schema", "json_schema": {"name": "answer"}},
        "metadata": {"safe": "value"},
        "reasoning_effort": "low",
        "parallel_tool_calls": True,
    }
    assert "authorization" in outbound["tools"][0]["function"]["parameters"]["properties"]
    assert outbound["tools"] is not inbound["tools"]


def test_chat_custom_tool_reconstructs_opaque_format_only_under_custom_container() -> None:
    inbound = {
        "model": "classroom-alias",
        "messages": [{"role": "user", "content": "hello"}],
        "tools": [
            {
                "type": "custom",
                "custom": {
                    "name": "emit_regex",
                    "description": "local custom intent",
                    "format": {
                        "type": "grammar",
                        "grammar": {"syntax": "regex", "definition": "[a-z]+"},
                    },
                },
            }
        ],
        "tool_choice": {"type": "custom", "custom": {"name": "emit_regex"}},
        "max_completion_tokens": 22,
    }

    policy_result = _chat_policy_result(inbound)
    outbound = build_chat_completion_upstream_body(
        policy_result.effective_body,
        upstream_model="gpt-4.1-mini",
    )

    assert outbound == {
        "model": "gpt-4.1-mini",
        "messages": [{"role": "user", "content": "hello"}],
        "max_completion_tokens": 22,
        "tools": inbound["tools"],
        "tool_choice": {"type": "custom", "custom": {"name": "emit_regex"}},
    }


def test_chat_multimodal_multiple_choice_and_audio_output_are_reconstructed_exactly() -> None:
    inbound = {
        "model": "classroom-alias",
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "describe and transcribe"},
                    {
                        "type": "image_url",
                        "image_url": {"url": "data:image/png;base64,aGk=", "detail": "low"},
                    },
                    {
                        "type": "file",
                        "file": {"filename": "notes.txt", "file_data": "SGVsbG8="},
                    },
                    {"type": "input_audio", "input_audio": {"data": "UklGRg==", "format": "wav"}},
                ],
            }
        ],
        "modalities": ["text", "audio"],
        "audio": {"format": "wav", "voice": "alloy"},
        "n": 2,
        "max_completion_tokens": 18,
    }

    policy_result = _chat_policy_result(inbound, CHAT_ALLOW_AUDIO_OUTPUT_WITH_N_CHOICES=True)
    outbound = build_chat_completion_upstream_body(
        policy_result.effective_body,
        upstream_model="gpt-4.1-mini",
    )

    assert outbound == {
        "model": "gpt-4.1-mini",
        "messages": inbound["messages"],
        "modalities": ["text", "audio"],
        "audio": {"format": "wav", "voice": "alloy"},
        "n": 2,
        "max_completion_tokens": 18,
    }


def test_chat_streaming_request_reconstructs_include_usage_mutation() -> None:
    inbound = {
        "model": "classroom-alias",
        "messages": [{"role": "user", "content": "hello"}],
        "stream": True,
        "stream_options": {"include_usage": False},
    }

    policy_result = _chat_policy_result(inbound)
    outbound = build_chat_completion_upstream_body(
        policy_result.effective_body,
        upstream_model="gpt-4.1-mini",
    )

    assert outbound == {
        "model": "gpt-4.1-mini",
        "messages": [{"role": "user", "content": "hello"}],
        "stream": True,
        "stream_options": {"include_usage": True},
        "max_completion_tokens": 12,
    }


def test_trusted_calibration_known_hosted_discovery_fields_are_reconstructed() -> None:
    inbound = {
        "model": "gpt-5-search-api",
        "messages": [{"role": "user", "content": "hello"}],
        "web_search_options": {"search_context_size": "low"},
        "tools": [{"type": "web_search_preview"}],
        "max_tokens": 20,
    }

    policy_result = _trusted_chat_policy_result(inbound)
    outbound = build_chat_completion_upstream_body(
        policy_result.effective_body,
        upstream_model="gpt-5-search-api",
    )

    assert outbound == {
        "model": "gpt-5-search-api",
        "messages": [{"role": "user", "content": "hello"}],
        "max_tokens": 20,
        "tools": [{"type": "web_search_preview"}],
        "web_search_options": {"search_context_size": "low"},
    }


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("unknown_top_level", "SHOULD_NOT_REACH_PROVIDER_TOP_LEVEL", "unknown_chat_completion_field"),
        ("web_search_options", {"search_context_size": "low"}, "web_search_not_allowed"),
        ("tools", [{"type": "web_search"}], "web_search_not_allowed"),
        ("tool_choice", {"type": "mcp"}, "mcp_connectors_not_allowed"),
        ("background", True, "background_not_allowed"),
        ("store", True, "background_not_allowed"),
        ("previous_response_id", "resp_SHOULD_NOT_APPEAR_IN_ERROR", "background_not_allowed"),
        ("service_tier", "priority", "service_tier_not_supported"),
        ("n", 99, "chat_choice_count_limit_exceeded"),
    ],
)
def test_chat_unsupported_fields_reject_before_upstream_body_build(
    field: str,
    value: object,
    code: str,
) -> None:
    with pytest.raises(RequestPolicyError) as exc_info:
        _chat_policy_result(
            {
                "model": "classroom-alias",
                "messages": [{"role": "user", "content": "SHOULD_NOT_APPEAR_IN_ERROR"}],
                field: value,
            }
        )

    assert exc_info.value.error_code == code
    assert "SHOULD_NOT_APPEAR_IN_ERROR" not in exc_info.value.safe_message
    assert "SHOULD_NOT_REACH_PROVIDER_TOP_LEVEL" not in exc_info.value.safe_message


def test_chat_builder_fails_closed_if_policy_result_contains_unapproved_field() -> None:
    with pytest.raises(ValueError, match="unapproved fields"):
        build_chat_completion_upstream_body(
            {
                "model": "classroom-alias",
                "messages": [{"role": "user", "content": "hello"}],
                "future_provider_field": "SHOULD_NOT_REACH_PROVIDER_NESTED",
            },
            upstream_model="gpt-4.1-mini",
        )


def test_responses_minimal_text_request_reconstructs_exact_upstream_body() -> None:
    inbound = {"model": "classroom-responses", "input": "hello"}
    original = copy.deepcopy(inbound)

    policy_result = _responses_policy_result(inbound)
    outbound = build_responses_upstream_body(
        policy_result.effective_body,
        upstream_model="gpt-5.2",
    )

    assert outbound == {
        "model": "gpt-5.2",
        "input": "hello",
        "max_output_tokens": 12,
        "store": False,
    }
    assert inbound == original
    assert outbound is not inbound


def test_responses_full_supported_text_request_reconstructs_exact_upstream_body() -> None:
    inbound = {
        "model": "classroom-responses",
        "input": "hello",
        "instructions": "answer briefly",
        "max_output_tokens": 20,
        "temperature": 0.2,
        "top_p": 0.9,
        "metadata": {"safe": "value"},
        "stream": False,
        "store": False,
        "text": {"format": {"type": "text"}},
        "service_tier": "auto",
    }

    policy_result = _responses_policy_result(inbound)
    outbound = build_responses_upstream_body(
        policy_result.effective_body,
        upstream_model="gpt-5.2",
    )

    assert outbound == {
        "model": "gpt-5.2",
        "input": "hello",
        "instructions": "answer briefly",
        "max_output_tokens": 20,
        "temperature": 0.2,
        "top_p": 0.9,
        "metadata": {"safe": "value"},
        "stream": False,
        "store": False,
        "text": {"format": {"type": "text"}},
        "service_tier": "auto",
    }
    assert outbound["metadata"] is not inbound["metadata"]


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("unknown_top_level", "SHOULD_NOT_REACH_PROVIDER_TOP_LEVEL", "responses_field_not_supported"),
        ("tools", [], "responses_tools_not_supported"),
        ("tool_choice", "auto", "responses_tools_not_supported"),
        ("parallel_tool_calls", True, "responses_tools_not_supported"),
        ("previous_response_id", "resp_SHOULD_NOT_APPEAR_IN_ERROR", "responses_state_not_supported"),
        ("conversation", "conv_SHOULD_NOT_APPEAR_IN_ERROR", "responses_state_not_supported"),
        ("background", True, "responses_background_not_supported"),
        ("include", ["output_text"], "responses_multimodal_not_supported"),
        ("prompt", {"id": "prompt_123"}, "responses_state_not_supported"),
        ("modalities", ["audio"], "responses_multimodal_not_supported"),
        ("audio", {"format": "wav"}, "responses_multimodal_not_supported"),
        ("stream_options", {"include_usage": True}, "responses_field_not_supported"),
        ("store", True, "responses_store_not_supported"),
        ("stream", True, "responses_streaming_not_supported"),
        ("service_tier", "priority", "responses_service_tier_not_supported"),
    ],
)
def test_responses_unsupported_fields_reject_before_upstream_body_build(
    field: str,
    value: object,
    code: str,
) -> None:
    with pytest.raises(RequestPolicyError) as exc_info:
        _responses_policy_result(
            {
                "model": "classroom-responses",
                "input": "SHOULD_NOT_APPEAR_IN_ERROR",
                field: value,
            }
        )

    assert exc_info.value.error_code == code
    assert "SHOULD_NOT_APPEAR_IN_ERROR" not in exc_info.value.safe_message
    assert "SHOULD_NOT_REACH_PROVIDER_TOP_LEVEL" not in exc_info.value.safe_message


def test_responses_nested_unsupported_fields_reject_without_value_leakage() -> None:
    with pytest.raises(RequestPolicyError) as text_exc:
        _responses_policy_result(
            {
                "model": "classroom-responses",
                "input": "safe",
                "text": {
                    "format": {"type": "text", "schema": "SHOULD_NOT_APPEAR_IN_ERROR"}
                },
            }
        )
    with pytest.raises(RequestPolicyError) as metadata_exc:
        _responses_policy_result(
            {
                "model": "classroom-responses",
                "input": "safe",
                "metadata": {"authorization": "Bearer should-not-leak"},
            },
            RESPONSES_MAX_METADATA_BYTES=20,
        )

    assert text_exc.value.param == "text.format.schema"
    assert "SHOULD_NOT_APPEAR_IN_ERROR" not in text_exc.value.safe_message
    assert metadata_exc.value.error_code == "responses_field_too_large"
    assert "Bearer should-not-leak" not in metadata_exc.value.safe_message


def test_responses_builder_fails_closed_if_policy_result_contains_unapproved_field() -> None:
    with pytest.raises(ValueError, match="unapproved fields"):
        build_responses_upstream_body(
            {
                "model": "classroom-responses",
                "input": "hello",
                "store": False,
                "max_output_tokens": 12,
                "provider_state": {"id": "SHOULD_NOT_REACH_PROVIDER_NESTED"},
            },
            upstream_model="gpt-5.2",
        )
