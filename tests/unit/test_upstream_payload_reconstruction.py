from __future__ import annotations

import copy

import pytest

from slaif_gateway.config import Settings
from slaif_gateway.services.upstream_request_contracts import (
    normalize_audio_speech_upstream_request,
    normalize_audio_transcription_upstream_request,
    normalize_audio_translation_upstream_request,
    normalize_conversation_items_create_upstream_request,
    normalize_conversation_items_query_request,
    normalize_conversation_update_upstream_request,
    normalize_chat_completion_upstream_request,
    normalize_embeddings_upstream_request,
    normalize_responses_compact_upstream_request,
    normalize_responses_input_tokens_upstream_request,
    normalize_responses_upstream_request,
)
from slaif_gateway.services.key_modes import CAPABILITY_POLICY_MODE_TRUSTED_CALIBRATION_DISCOVERY
from slaif_gateway.services.policy_errors import RequestPolicyError
from slaif_gateway.services.request_policy import ChatCompletionRequestPolicy
from slaif_gateway.services.responses_request_policy import ResponsesRequestPolicy
from slaif_gateway.services.upstream_payloads import (
    build_audio_speech_upstream_body,
    build_audio_transcription_upstream_body,
    build_audio_translation_upstream_body,
    build_conversation_items_create_upstream_body,
    build_conversation_items_query_params,
    build_conversation_update_upstream_body,
    build_chat_completion_upstream_body,
    build_embeddings_upstream_body,
    build_responses_compact_upstream_body,
    build_responses_input_tokens_upstream_body,
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


def _stored_responses_policy_result(body: dict[str, object], **settings_overrides: object):
    return ResponsesRequestPolicy(_settings(**settings_overrides)).apply(body, allow_store=True)


def _normalize_chat_body(body: dict[str, object], **settings_overrides: object):
    return _normalize_chat_body_with_resolved_model(body, resolved_model="gpt-4.1-mini", **settings_overrides)


def _normalize_chat_body_with_resolved_model(
    body: dict[str, object], *, resolved_model: str = "gpt-4.1-mini", **settings_overrides: object
):
    policy_result = _chat_policy_result(body, **settings_overrides)
    return normalize_chat_completion_upstream_request(
        policy_result.effective_body,
        requested_model=policy_result.effective_body["model"],
        upstream_model=resolved_model,
    )


def _normalize_responses_body(body: dict[str, object], *, resolved_model: str = "gpt-5.2"):
    policy_result = _responses_policy_result(body)
    return normalize_responses_upstream_request(
        policy_result.effective_body,
        requested_model=policy_result.effective_body["model"],
        upstream_model=resolved_model,
    )


def _normalize_responses_input_tokens_body(
    body: dict[str, object],
    *,
    resolved_model: str = "gpt-5.2",
):
    policy_result = ResponsesRequestPolicy(_settings()).apply_input_token_count(body)
    return normalize_responses_input_tokens_upstream_request(
        policy_result.effective_body,
        requested_model=policy_result.effective_body["model"],
        upstream_model=resolved_model,
    )


def _normalize_responses_compact_body(
    body: dict[str, object],
    *,
    resolved_model: str = "gpt-5.2",
):
    policy_result = ResponsesRequestPolicy(_settings()).apply_compact(body)
    return normalize_responses_compact_upstream_request(
        policy_result.effective_body,
        requested_model=policy_result.effective_body["model"],
        upstream_model=resolved_model,
    )


def _normalize_audio_speech_body(
    body: dict[str, object],
    *,
    resolved_model: str = "gpt-4o-mini-tts",
):
    from slaif_gateway.services.audio_request_policy import AudioRequestPolicy

    policy_result = AudioRequestPolicy(_settings()).apply_speech(body)
    return normalize_audio_speech_upstream_request(
        policy_result.effective_body,
        requested_model=policy_result.effective_body["model"],
        upstream_model=resolved_model,
    )


def _normalize_audio_transcription_body(
    body: dict[str, object],
    *,
    resolved_model: str = "gpt-4o-transcribe",
):
    return normalize_audio_transcription_upstream_request(
        body,
        requested_model=str(body["model"]),
        upstream_model=resolved_model,
    )


def _normalize_audio_translation_body(
    body: dict[str, object],
    *,
    resolved_model: str = "whisper-1",
):
    return normalize_audio_translation_upstream_request(
        body,
        requested_model=str(body["model"]),
        upstream_model=resolved_model,
    )


def _normalize_embeddings_body(
    body: dict[str, object],
    *,
    resolved_model: str = "text-embedding-3-small",
):
    from slaif_gateway.services.embeddings_request_policy import EmbeddingsRequestPolicy

    policy_result = EmbeddingsRequestPolicy(_settings()).apply(body)
    return normalize_embeddings_upstream_request(
        policy_result.effective_body,
        requested_model=str(policy_result.effective_body["model"]),
        upstream_model=resolved_model,
    )


def test_chat_minimal_text_request_reconstructs_exact_upstream_body() -> None:
    inbound = {
        "model": "classroom-alias",
        "messages": [{"role": "user", "content": "hello"}],
    }
    original = copy.deepcopy(inbound)

    normalized_request = _normalize_chat_body_with_resolved_model(inbound)
    outbound = build_chat_completion_upstream_body(
        normalized_request,
    )

    assert outbound == {
        "model": "gpt-4.1-mini",
        "messages": [{"role": "user", "content": "hello"}],
        "max_completion_tokens": 12,
    }
    assert inbound == original
    assert outbound is not inbound
    assert outbound["messages"] is not inbound["messages"]

    before_outbound_mutation = copy.deepcopy(inbound)
    outbound["messages"][0]["content"] = "mutated"
    assert inbound == before_outbound_mutation


def test_audio_speech_request_reconstructs_exact_upstream_body() -> None:
    inbound = {
        "model": "classroom-audio",
        "input": "Speak this sentence",
        "voice": "alloy",
        "response_format": "aac",
        "speed": 1.25,
        "instructions": "Calm voice",
    }
    original = copy.deepcopy(inbound)

    normalized_request = _normalize_audio_speech_body(inbound)
    outbound = build_audio_speech_upstream_body(normalized_request)

    assert outbound == {
        "model": "gpt-4o-mini-tts",
        "input": "Speak this sentence",
        "voice": "alloy",
        "response_format": "aac",
        "speed": 1.25,
        "instructions": "Calm voice",
    }
    assert inbound == original
    assert outbound is not inbound


def test_audio_transcription_request_reconstructs_exact_upstream_body() -> None:
    inbound = {
        "model": "classroom-audio",
        "language": "sl",
        "prompt": "Short safe hint",
        "response_format": "verbose_json",
        "temperature": 0.2,
        "timestamp_granularities": ["segment"],
        "include": ["logprobs"],
    }
    original = copy.deepcopy(inbound)

    normalized_request = _normalize_audio_transcription_body(inbound)
    outbound = build_audio_transcription_upstream_body(normalized_request)

    assert outbound == {
        "model": "gpt-4o-transcribe",
        "language": "sl",
        "prompt": "Short safe hint",
        "response_format": "verbose_json",
        "temperature": 0.2,
        "timestamp_granularities": ["segment"],
        "include": ["logprobs"],
    }
    assert inbound == original
    assert outbound is not inbound


def test_audio_translation_request_reconstructs_exact_upstream_body() -> None:
    inbound = {
        "model": "classroom-audio",
        "prompt": "Keep named entities intact",
        "response_format": "text",
        "temperature": 0.3,
    }
    original = copy.deepcopy(inbound)

    normalized_request = _normalize_audio_translation_body(inbound)
    outbound = build_audio_translation_upstream_body(normalized_request)

    assert outbound == {
        "model": "whisper-1",
        "prompt": "Keep named entities intact",
        "response_format": "text",
        "temperature": 0.3,
    }
    assert inbound == original
    assert outbound is not inbound


def test_embeddings_request_reconstructs_exact_upstream_body() -> None:
    inbound = {
        "model": "classroom-embedding",
        "input": ["hello", "world"],
        "encoding_format": "base64",
        "dimensions": 8,
        "user": "learner-1",
    }
    original = copy.deepcopy(inbound)

    normalized_request = _normalize_embeddings_body(inbound)
    outbound = build_embeddings_upstream_body(normalized_request)

    assert outbound == {
        "model": "text-embedding-3-small",
        "input": ["hello", "world"],
        "encoding_format": "base64",
        "dimensions": 8,
        "user": "learner-1",
    }
    assert inbound == original
    assert outbound is not inbound


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

    normalized_request = _normalize_chat_body_with_resolved_model(inbound)
    outbound = build_chat_completion_upstream_body(
        normalized_request,
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

    normalized_request = _normalize_chat_body_with_resolved_model(inbound)
    outbound = build_chat_completion_upstream_body(
        normalized_request,
    )

    assert outbound == {
        "model": "gpt-4.1-mini",
        "messages": [{"role": "user", "content": "hello"}],
        "max_completion_tokens": 22,
        "tools": inbound["tools"],
        "tool_choice": {"type": "custom", "custom": {"name": "emit_regex"}},
    }


def test_chat_normalized_contract_deep_copies_opaque_containers() -> None:
    inbound = {
        "model": "classroom-alias",
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "original text"},
                    {
                        "type": "image_url",
                        "image_url": {"url": "data:image/png;base64,b3JpZw==", "detail": "low"},
                    },
                    {
                        "type": "file",
                        "file": {"filename": "notes.txt", "file_data": "T1JJRw=="},
                    },
                    {"type": "input_audio", "input_audio": {"data": "T1JJRw==", "format": "wav"}},
                ],
            }
        ],
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "lookup",
                    "parameters": {
                        "type": "object",
                        "properties": {"query": {"type": "string", "description": "original"}},
                    },
                },
            },
            {
                "type": "custom",
                "custom": {
                    "name": "emit_regex",
                    "format": {
                        "type": "grammar",
                        "grammar": {"syntax": "regex", "definition": "[a-z]+"},
                    },
                },
            },
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "answer", "schema": {"type": "object"}},
        },
        "metadata": {"safe": {"nested": "original"}},
        "modalities": ["text", "audio"],
        "audio": {"format": "wav", "voice": "alloy"},
        "max_completion_tokens": 18,
    }

    normalized_request = _normalize_chat_body(inbound)

    inbound["messages"][0]["content"][0]["text"] = "changed"
    inbound["messages"][0]["content"][1]["image_url"]["url"] = "data:image/png;base64,Q0hBTkdFRA=="
    inbound["messages"][0]["content"][2]["file"]["file_data"] = "Q0hBTkdFRA=="
    inbound["messages"][0]["content"][3]["input_audio"]["data"] = "Q0hBTkdFRA=="
    inbound["tools"][0]["function"]["parameters"]["properties"]["query"]["description"] = "changed"
    inbound["tools"][1]["custom"]["format"]["grammar"]["definition"] = "[0-9]+"
    inbound["response_format"]["json_schema"]["schema"]["type"] = "array"
    inbound["metadata"]["safe"]["nested"] = "changed"
    inbound["audio"]["voice"] = "changed"

    outbound = build_chat_completion_upstream_body(normalized_request)

    assert outbound["messages"][0]["content"][0]["text"] == "original text"
    assert outbound["messages"][0]["content"][1]["image_url"]["url"] == "data:image/png;base64,b3JpZw=="
    assert outbound["messages"][0]["content"][2]["file"]["file_data"] == "T1JJRw=="
    assert outbound["messages"][0]["content"][3]["input_audio"]["data"] == "T1JJRw=="
    assert (
        outbound["tools"][0]["function"]["parameters"]["properties"]["query"]["description"]
        == "original"
    )
    assert outbound["tools"][1]["custom"]["format"]["grammar"]["definition"] == "[a-z]+"
    assert outbound["response_format"]["json_schema"]["schema"]["type"] == "object"
    assert outbound["metadata"]["safe"]["nested"] == "original"
    assert outbound["audio"]["voice"] == "alloy"

    outbound["tools"][0]["function"]["parameters"]["properties"]["query"]["description"] = "outbound"
    outbound["metadata"]["safe"]["nested"] = "outbound"
    rebuilt = build_chat_completion_upstream_body(normalized_request)
    assert rebuilt["tools"][0]["function"]["parameters"]["properties"]["query"]["description"] == "original"
    assert rebuilt["metadata"]["safe"]["nested"] == "original"


def test_chat_multimodal_audio_output_is_reconstructed_exactly() -> None:
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
        "max_completion_tokens": 18,
    }

    normalized_request = _normalize_chat_body_with_resolved_model(
        inbound,
        resolved_model="gpt-4.1-mini",
    )
    outbound = build_chat_completion_upstream_body(
        normalized_request,
    )

    assert outbound == {
        "model": "gpt-4.1-mini",
        "messages": inbound["messages"],
        "modalities": ["text", "audio"],
        "audio": {"format": "wav", "voice": "alloy"},
        "max_completion_tokens": 18,
    }


def test_chat_streaming_request_reconstructs_include_usage_mutation() -> None:
    inbound = {
        "model": "classroom-alias",
        "messages": [{"role": "user", "content": "hello"}],
        "stream": True,
        "stream_options": {"include_usage": False},
    }

    normalized_request = _normalize_chat_body_with_resolved_model(inbound)
    outbound = build_chat_completion_upstream_body(
        normalized_request,
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

    normalized_request = normalize_chat_completion_upstream_request(
        _trusted_chat_policy_result(inbound).effective_body,
        requested_model="gpt-5-search-api",
        upstream_model="gpt-5-search-api",
    )
    outbound = build_chat_completion_upstream_body(
        normalized_request,
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
    with pytest.raises(ValueError, match="unapproved top-level fields"):
        normalize_chat_completion_upstream_request(
            {
                "model": "classroom-alias",
                "messages": [{"role": "user", "content": "hello"}],
                "future_provider_field": "SHOULD_NOT_REACH_PROVIDER_NESTED",
            },
            requested_model="classroom-alias",
            upstream_model="gpt-4.1-mini",
        )


def test_chat_builder_rejects_raw_effective_body_mapping() -> None:
    with pytest.raises(TypeError, match="normalized request contract"):
        build_chat_completion_upstream_body({
            "model": "gpt-4.1-mini",
            "messages": [{"role": "user", "content": "hello"}],
        })


def test_responses_minimal_text_request_reconstructs_exact_upstream_body() -> None:
    inbound = {"model": "classroom-responses", "input": "hello"}
    original = copy.deepcopy(inbound)

    normalized_request = _normalize_responses_body(inbound)
    outbound = build_responses_upstream_body(
        normalized_request,
    )

    assert outbound == {
        "model": "gpt-5.2",
        "input": "hello",
        "max_output_tokens": 12,
        "store": False,
    }
    assert inbound == original
    assert outbound is not inbound


def test_responses_input_token_count_text_request_reconstructs_exact_upstream_body() -> None:
    inbound = {
        "model": "classroom-responses",
        "input": "hello",
        "instructions": "count carefully",
        "text": {"format": {"type": "text"}},
        "truncation": "disabled",
    }
    original = copy.deepcopy(inbound)

    normalized_request = _normalize_responses_input_tokens_body(inbound)
    outbound = build_responses_input_tokens_upstream_body(normalized_request)

    assert outbound == {
        "model": "gpt-5.2",
        "input": "hello",
        "instructions": "count carefully",
        "text": {"format": {"type": "text"}},
        "truncation": "disabled",
    }
    assert inbound == original
    assert "store" not in outbound
    assert "max_output_tokens" not in outbound


def test_responses_compact_string_input_reconstructs_exact_upstream_body() -> None:
    inbound = {
        "model": "classroom-alias",
        "input": "Compact this transcript.",
        "instructions": "Preserve decisions.",
    }

    normalized_request = _normalize_responses_compact_body(inbound)
    outbound = build_responses_compact_upstream_body(normalized_request)

    assert outbound == {
        "model": "gpt-5.2",
        "input": "Compact this transcript.",
        "instructions": "Preserve decisions.",
    }
    assert "max_output_tokens" not in outbound
    assert "stream" not in outbound


def test_responses_compact_item_array_reconstructs_exact_upstream_body_and_deep_copies() -> None:
    inbound = {
        "model": "classroom-alias",
        "input": [
            {"role": "user", "content": "Create a simple landing page."},
            {
                "id": "msg_001",
                "type": "message",
                "status": "completed",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "Previous output."}],
            },
        ],
    }
    original = copy.deepcopy(inbound)

    normalized_request = _normalize_responses_compact_body(inbound)
    inbound["input"][1]["content"][0]["text"] = "mutated"  # type: ignore[index]
    outbound = build_responses_compact_upstream_body(normalized_request)

    assert outbound == {
        "model": "gpt-5.2",
        "input": [
            {"role": "user", "content": "Create a simple landing page."},
            {
                "role": "assistant",
                "content": [{"type": "output_text", "text": "Previous output."}],
                "type": "message",
                "id": "msg_001",
                "status": "completed",
            },
        ],
    }
    rebuilt = build_responses_compact_upstream_body(normalized_request)
    assert rebuilt == outbound
    assert inbound != original


def test_responses_input_token_count_item_array_and_tools_reconstruct_exact_body() -> None:
    inbound = {
        "model": "classroom-responses",
        "input": [
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": "Count this image and file."},
                    {"type": "input_image", "image_url": "https://example.org/image.png"},
                    {"type": "input_file", "file_url": "https://example.org/file.pdf"},
                ],
            },
            {
                "type": "function_call_output",
                "call_id": "call_123",
                "output": "safe result",
            },
        ],
        "tools": [
            {
                "type": "function",
                "name": "lookup",
                "parameters": {"type": "object", "properties": {}},
            }
        ],
        "tool_choice": {"type": "function", "name": "lookup"},
        "parallel_tool_calls": False,
    }

    normalized_request = _normalize_responses_input_tokens_body(inbound)
    outbound = build_responses_input_tokens_upstream_body(normalized_request)

    assert outbound == {
        "model": "gpt-5.2",
        "input": [
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": "Count this image and file."},
                    {"type": "input_image", "image_url": "https://example.org/image.png"},
                    {"type": "input_file", "file_url": "https://example.org/file.pdf"},
                ],
            },
            {
                "type": "function_call_output",
                "call_id": "call_123",
                "output": "safe result",
            },
        ],
        "tools": [
            {
                "type": "function",
                "name": "lookup",
                "parameters": {"type": "object", "properties": {}},
            }
        ],
        "tool_choice": {"type": "function", "name": "lookup"},
        "parallel_tool_calls": False,
    }
    assert outbound["input"] is not inbound["input"]
    assert outbound["tools"] is not inbound["tools"]


def test_responses_input_token_count_builder_rejects_raw_effective_body_mapping() -> None:
    with pytest.raises(TypeError, match="normalized request contract"):
        build_responses_input_tokens_upstream_body({
            "model": "gpt-5.2",
            "input": "hello",
        })


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

    normalized_request = _normalize_responses_body(inbound)
    outbound = build_responses_upstream_body(
        normalized_request,
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


def test_responses_input_array_request_reconstructs_exact_upstream_body() -> None:
    inbound = {
        "model": "classroom-responses",
        "input": [
            {"role": "system", "content": "system text"},
            {
                "type": "message",
                "role": "user",
                "content": [
                    {"type": "input_text", "text": "first"},
                    {"type": "input_text", "text": "second"},
                ],
            },
        ],
        "instructions": "answer briefly",
    }

    normalized_request = _normalize_responses_body(inbound)
    outbound = build_responses_upstream_body(normalized_request)

    assert outbound == {
        "model": "gpt-5.2",
        "input": [
            {"role": "system", "content": "system text"},
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": "first"},
                    {"type": "input_text", "text": "second"},
                ],
                "type": "message",
            },
        ],
        "instructions": "answer briefly",
        "max_output_tokens": 12,
        "store": False,
    }
    assert outbound["input"] is not inbound["input"]
    assert outbound["input"][1]["content"] is not inbound["input"][1]["content"]


def test_responses_input_array_structured_request_reconstructs_exact_upstream_body() -> None:
    schema = {"type": "object", "properties": {"answer": {"type": "string"}}}
    inbound = {
        "model": "classroom-responses",
        "input": [{"role": "user", "content": "return an object"}],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "answer_schema",
                "schema": schema,
            }
        },
    }

    normalized_request = _normalize_responses_body(inbound)
    outbound = build_responses_upstream_body(normalized_request)

    assert outbound == {
        "model": "gpt-5.2",
        "input": [{"role": "user", "content": "return an object"}],
        "max_output_tokens": 12,
        "store": False,
        "text": {
            "format": {
                "type": "json_schema",
                "name": "answer_schema",
                "schema": schema,
            }
        },
    }


def test_responses_image_url_input_reconstructs_exact_upstream_body() -> None:
    inbound = {
        "model": "classroom-responses",
        "input": [
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": "describe this"},
                    {
                        "type": "input_image",
                        "image_url": "https://example.test/image.png",
                        "detail": "low",
                    },
                ],
            }
        ],
    }

    normalized_request = _normalize_responses_body(inbound)
    outbound = build_responses_upstream_body(normalized_request)

    assert outbound == {
        "model": "gpt-5.2",
        "input": [
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": "describe this"},
                    {
                        "type": "input_image",
                        "image_url": "https://example.test/image.png",
                        "detail": "low",
                    },
                ],
            }
        ],
        "max_output_tokens": 12,
        "store": False,
    }


def test_responses_image_data_url_input_reconstructs_exact_upstream_body_with_omitted_detail() -> None:
    data_url = "data:image/png;base64,aGVsbG8="
    inbound = {
        "model": "classroom-responses",
        "input": [
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": "describe this"},
                    {"type": "input_image", "image_url": data_url},
                ],
            }
        ],
    }

    normalized_request = _normalize_responses_body(inbound)
    outbound = build_responses_upstream_body(normalized_request)

    assert outbound == {
        "model": "gpt-5.2",
        "input": [
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": "describe this"},
                    {"type": "input_image", "image_url": data_url},
                ],
            }
        ],
        "max_output_tokens": 12,
        "store": False,
    }
    assert "detail" not in outbound["input"][0]["content"][1]


def test_responses_file_url_input_reconstructs_exact_upstream_body() -> None:
    inbound = {
        "model": "classroom-responses",
        "input": [
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": "summarize this"},
                    {
                        "type": "input_file",
                        "file_url": "https://example.test/document.pdf",
                    },
                ],
            }
        ],
    }

    normalized_request = _normalize_responses_body(inbound)
    outbound = build_responses_upstream_body(normalized_request)

    assert outbound == {
        "model": "gpt-5.2",
        "input": [
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": "summarize this"},
                    {
                        "type": "input_file",
                        "file_url": "https://example.test/document.pdf",
                    },
                ],
            }
        ],
        "max_output_tokens": 12,
        "store": False,
    }


def test_responses_file_data_input_reconstructs_exact_upstream_body() -> None:
    file_data = "data:application/pdf;base64,aGVsbG8="
    inbound = {
        "model": "classroom-responses",
        "input": [
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": "summarize this"},
                    {
                        "type": "input_file",
                        "filename": "document.pdf",
                        "file_data": file_data,
                    },
                ],
            }
        ],
    }

    normalized_request = _normalize_responses_body(inbound)
    outbound = build_responses_upstream_body(normalized_request)

    assert outbound == {
        "model": "gpt-5.2",
        "input": [
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": "summarize this"},
                    {
                        "type": "input_file",
                        "filename": "document.pdf",
                        "file_data": file_data,
                    },
                ],
            }
        ],
        "max_output_tokens": 12,
        "store": False,
    }


def test_responses_function_tools_request_reconstructs_exact_upstream_body() -> None:
    schema = {
        "type": "object",
        "properties": {"query": {"type": "string", "description": "opaque schema"}},
        "required": ["query"],
    }
    inbound = {
        "model": "classroom-responses",
        "input": [{"role": "user", "content": "use lookup"}],
        "tools": [
            {
                "type": "function",
                "name": "lookup",
                "description": "Local lookup intent.",
                "parameters": schema,
                "strict": True,
            }
        ],
        "tool_choice": {"type": "function", "name": "lookup"},
    }

    normalized_request = _normalize_responses_body(inbound)
    outbound = build_responses_upstream_body(normalized_request)

    assert outbound == {
        "model": "gpt-5.2",
        "input": [{"role": "user", "content": "use lookup"}],
        "max_output_tokens": 12,
        "store": False,
        "tools": [
            {
                "type": "function",
                "name": "lookup",
                "parameters": schema,
                "description": "Local lookup intent.",
                "strict": True,
            }
        ],
        "tool_choice": {"type": "function", "name": "lookup"},
    }
    assert outbound["tools"] is not inbound["tools"]
    assert outbound["tools"][0]["parameters"] is not schema


def test_responses_function_call_output_item_reconstructs_exact_upstream_body() -> None:
    inbound = {
        "model": "classroom-responses",
        "input": [
            {"role": "user", "content": "use lookup"},
            {
                "type": "function_call_output",
                "call_id": "call_123",
                "output": '{"result":"safe"}',
            },
        ],
    }

    normalized_request = _normalize_responses_body(inbound)
    outbound = build_responses_upstream_body(normalized_request)

    assert outbound == {
        "model": "gpt-5.2",
        "input": [
            {"role": "user", "content": "use lookup"},
            {
                "type": "function_call_output",
                "call_id": "call_123",
                "output": '{"result":"safe"}',
            },
        ],
        "max_output_tokens": 12,
        "store": False,
    }


def test_responses_custom_tools_request_reconstructs_exact_upstream_body() -> None:
    inbound = {
        "model": "classroom-responses",
        "input": [{"role": "user", "content": "use custom"}],
        "tools": [
            {"type": "custom", "name": "freeform"},
            {"type": "custom", "name": "texty", "format": {"type": "text"}},
            {
                "type": "custom",
                "name": "emit_regex",
                "description": "Local custom intent.",
                "format": {
                    "type": "grammar",
                    "syntax": "regex",
                    "definition": "[a-z]+",
                },
            },
        ],
        "tool_choice": {"type": "custom", "name": "emit_regex"},
    }

    normalized_request = _normalize_responses_body(inbound)
    outbound = build_responses_upstream_body(normalized_request)

    assert outbound == {
        "model": "gpt-5.2",
        "input": [{"role": "user", "content": "use custom"}],
        "max_output_tokens": 12,
        "store": False,
        "tools": [
            {"type": "custom", "name": "freeform"},
            {"type": "custom", "name": "texty", "format": {"type": "text"}},
            {
                "type": "custom",
                "name": "emit_regex",
                "description": "Local custom intent.",
                "format": {
                    "type": "grammar",
                    "syntax": "regex",
                    "definition": "[a-z]+",
                },
            },
        ],
        "tool_choice": {"type": "custom", "name": "emit_regex"},
    }
    assert outbound["tools"] is not inbound["tools"]
    assert "format" not in outbound["tools"][0]


def test_responses_custom_tool_output_item_reconstructs_exact_upstream_body() -> None:
    inbound = {
        "model": "classroom-responses",
        "input": [
            {"role": "user", "content": "use custom"},
            {
                "type": "custom_tool_call_output",
                "call_id": "call_123",
                "output": "safe custom result",
            },
        ],
    }

    normalized_request = _normalize_responses_body(inbound)
    outbound = build_responses_upstream_body(normalized_request)

    assert outbound == {
        "model": "gpt-5.2",
        "input": [
            {"role": "user", "content": "use custom"},
            {
                "type": "custom_tool_call_output",
                "call_id": "call_123",
                "output": "safe custom result",
            },
        ],
        "max_output_tokens": 12,
        "store": False,
    }


def test_responses_streaming_input_array_reconstructs_exact_upstream_body() -> None:
    inbound = {
        "model": "classroom-responses",
        "input": [{"role": "user", "content": "stream this"}],
        "stream": True,
    }

    normalized_request = _normalize_responses_body(inbound)
    outbound = build_responses_upstream_body(normalized_request)

    assert outbound == {
        "model": "gpt-5.2",
        "input": [{"role": "user", "content": "stream this"}],
        "max_output_tokens": 12,
        "stream": True,
        "store": False,
    }


def test_responses_streaming_text_request_reconstructs_exact_upstream_body() -> None:
    inbound = {
        "model": "classroom-responses",
        "input": "hello",
        "stream": True,
    }

    normalized_request = _normalize_responses_body(inbound)
    outbound = build_responses_upstream_body(normalized_request)

    assert outbound == {
        "model": "gpt-5.2",
        "input": "hello",
        "max_output_tokens": 12,
        "stream": True,
        "store": False,
    }


def test_responses_json_object_request_reconstructs_exact_upstream_body() -> None:
    inbound = {
        "model": "classroom-responses",
        "input": "return JSON",
        "text": {"format": {"type": "json_object"}},
    }

    normalized_request = _normalize_responses_body(inbound)
    outbound = build_responses_upstream_body(normalized_request)

    assert outbound == {
        "model": "gpt-5.2",
        "input": "return JSON",
        "max_output_tokens": 12,
        "store": False,
        "text": {"format": {"type": "json_object"}},
    }


def test_responses_json_schema_request_reconstructs_exact_upstream_body() -> None:
    schema = {
        "type": "object",
        "properties": {"answer": {"type": "string"}},
        "required": ["answer"],
        "additionalProperties": False,
    }
    inbound = {
        "model": "classroom-responses",
        "input": "answer",
        "text": {
            "format": {
                "type": "json_schema",
                "name": "answer_schema",
                "description": "Answer object.",
                "schema": schema,
                "strict": True,
            }
        },
    }

    normalized_request = _normalize_responses_body(inbound)
    outbound = build_responses_upstream_body(normalized_request)

    assert outbound == {
        "model": "gpt-5.2",
        "input": "answer",
        "max_output_tokens": 12,
        "store": False,
        "text": {
            "format": {
                "type": "json_schema",
                "name": "answer_schema",
                "description": "Answer object.",
                "schema": schema,
                "strict": True,
            }
        },
    }
    assert outbound["text"]["format"]["schema"] is not schema


def test_responses_normalized_contract_deep_copies_opaque_containers() -> None:
    inbound = {
        "model": "classroom-responses",
        "input": "hello",
        "metadata": {"safe": {"nested": "original"}},
        "text": {"format": {"type": "text"}},
    }

    normalized_request = _normalize_responses_body(inbound)
    inbound["metadata"]["safe"]["nested"] = "changed"
    inbound["text"]["format"]["type"] = "changed"

    outbound = build_responses_upstream_body(normalized_request)

    assert outbound["metadata"]["safe"]["nested"] == "original"
    assert outbound["text"]["format"]["type"] == "text"

    outbound["metadata"]["safe"]["nested"] = "outbound"
    rebuilt = build_responses_upstream_body(normalized_request)
    assert rebuilt["metadata"]["safe"]["nested"] == "original"


def test_responses_json_schema_container_deep_copy_isolation() -> None:
    inbound = {
        "model": "classroom-responses",
        "input": "hello",
        "text": {
            "format": {
                "type": "json_schema",
                "name": "answer_schema",
                "schema": {
                    "type": "object",
                    "properties": {"answer": {"type": "string"}},
                },
            }
        },
    }

    normalized_request = _normalize_responses_body(inbound)
    inbound["text"]["format"]["schema"]["properties"]["answer"]["type"] = "integer"

    outbound = build_responses_upstream_body(normalized_request)
    assert outbound["text"]["format"]["schema"]["properties"]["answer"]["type"] == "string"

    outbound["text"]["format"]["schema"]["properties"]["answer"]["type"] = "boolean"
    rebuilt = build_responses_upstream_body(normalized_request)
    assert rebuilt["text"]["format"]["schema"]["properties"]["answer"]["type"] == "string"


def test_responses_input_item_array_deep_copy_isolation() -> None:
    inbound = {
        "model": "classroom-responses",
        "input": [
            {
                "role": "user",
                "content": [{"type": "input_text", "text": "original"}],
            }
        ],
    }

    normalized_request = _normalize_responses_body(inbound)
    inbound["input"][0]["content"][0]["text"] = "changed"

    outbound = build_responses_upstream_body(normalized_request)
    assert outbound["input"][0]["content"][0]["text"] == "original"

    outbound["input"][0]["content"][0]["text"] = "outbound"
    rebuilt = build_responses_upstream_body(normalized_request)
    assert rebuilt["input"][0]["content"][0]["text"] == "original"


def test_responses_image_input_deep_copy_isolation() -> None:
    inbound = {
        "model": "classroom-responses",
        "input": [
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": "original"},
                    {
                        "type": "input_image",
                        "image_url": "data:image/png;base64,b3JpZw==",
                        "detail": "low",
                    },
                ],
            }
        ],
    }

    normalized_request = _normalize_responses_body(inbound)
    inbound["input"][0]["content"][1]["image_url"] = "data:image/png;base64,Q0hBTkdFRA=="
    inbound["input"][0]["content"][1]["detail"] = "high"

    outbound = build_responses_upstream_body(normalized_request)
    assert outbound["input"][0]["content"][1]["image_url"] == "data:image/png;base64,b3JpZw=="
    assert outbound["input"][0]["content"][1]["detail"] == "low"

    outbound["input"][0]["content"][1]["image_url"] = "https://example.test/outbound.png"
    rebuilt = build_responses_upstream_body(normalized_request)
    assert rebuilt["input"][0]["content"][1]["image_url"] == "data:image/png;base64,b3JpZw=="


def test_responses_file_input_deep_copy_isolation() -> None:
    inbound = {
        "model": "classroom-responses",
        "input": [
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": "original"},
                    {
                        "type": "input_file",
                        "filename": "document.pdf",
                        "file_data": "data:application/pdf;base64,b3JpZw==",
                    },
                ],
            }
        ],
    }

    normalized_request = _normalize_responses_body(inbound)
    inbound["input"][0]["content"][1]["filename"] = "changed.pdf"
    inbound["input"][0]["content"][1]["file_data"] = "data:application/pdf;base64,Q0hBTkdFRA=="

    outbound = build_responses_upstream_body(normalized_request)
    assert outbound["input"][0]["content"][1]["filename"] == "document.pdf"
    assert outbound["input"][0]["content"][1]["file_data"] == "data:application/pdf;base64,b3JpZw=="

    outbound["input"][0]["content"][1]["file_data"] = "data:application/pdf;base64,T1VU"
    rebuilt = build_responses_upstream_body(normalized_request)
    assert rebuilt["input"][0]["content"][1]["file_data"] == "data:application/pdf;base64,b3JpZw=="


def test_responses_function_tool_schema_deep_copy_isolation() -> None:
    inbound = {
        "model": "classroom-responses",
        "input": "hello",
        "tools": [
            {
                "type": "function",
                "name": "lookup",
                "parameters": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                },
            }
        ],
        "tool_choice": {"type": "function", "name": "lookup"},
    }

    normalized_request = _normalize_responses_body(inbound)
    inbound["tools"][0]["parameters"]["properties"]["query"]["type"] = "integer"

    outbound = build_responses_upstream_body(normalized_request)
    assert outbound["tools"][0]["parameters"]["properties"]["query"]["type"] == "string"

    outbound["tools"][0]["parameters"]["properties"]["query"]["type"] = "boolean"
    rebuilt = build_responses_upstream_body(normalized_request)
    assert rebuilt["tools"][0]["parameters"]["properties"]["query"]["type"] == "string"


def test_responses_custom_tool_format_deep_copy_isolation() -> None:
    inbound = {
        "model": "classroom-responses",
        "input": "hello",
        "tools": [
            {
                "type": "custom",
                "name": "emit_regex",
                "format": {
                    "type": "grammar",
                    "syntax": "regex",
                    "definition": "[a-z]+",
                },
            }
        ],
        "tool_choice": {"type": "custom", "name": "emit_regex"},
    }

    normalized_request = _normalize_responses_body(inbound)
    inbound["tools"][0]["format"]["definition"] = "[0-9]+"

    outbound = build_responses_upstream_body(normalized_request)
    assert outbound["tools"][0]["format"]["definition"] == "[a-z]+"

    outbound["tools"][0]["format"]["definition"] = "[A-Z]+"
    rebuilt = build_responses_upstream_body(normalized_request)
    assert rebuilt["tools"][0]["format"]["definition"] == "[a-z]+"


def test_responses_store_true_reconstructs_exact_upstream_body() -> None:
    policy_result = _stored_responses_policy_result(
        {
            "model": "classroom-responses",
            "input": "hello",
            "max_output_tokens": 12,
            "store": True,
        }
    )

    normalized_request = normalize_responses_upstream_request(
        policy_result.effective_body,
        requested_model=policy_result.effective_body["model"],
        upstream_model="gpt-5.2",
    )
    outbound = build_responses_upstream_body(normalized_request)

    assert outbound == {
        "model": "gpt-5.2",
        "input": "hello",
        "max_output_tokens": 12,
        "store": True,
    }


def test_responses_previous_response_id_reconstructs_exact_upstream_body() -> None:
    policy_result = _responses_policy_result(
        {
            "model": "classroom-responses",
            "input": "continue",
            "max_output_tokens": 12,
            "previous_response_id": "resp_previous_123",
        }
    )

    normalized_request = normalize_responses_upstream_request(
        policy_result.effective_body,
        requested_model=policy_result.effective_body["model"],
        upstream_model="gpt-5.2",
    )
    outbound = build_responses_upstream_body(normalized_request)

    assert outbound == {
        "model": "gpt-5.2",
        "input": "continue",
        "max_output_tokens": 12,
        "store": False,
        "previous_response_id": "resp_previous_123",
    }


def test_responses_conversation_reconstructs_exact_upstream_body_and_deep_copies() -> None:
    inbound = {
        "model": "classroom-responses",
        "input": [{"role": "user", "content": [{"type": "input_text", "text": "continue"}]}],
        "max_output_tokens": 12,
        "conversation": "conv_owned_123",
    }
    original = copy.deepcopy(inbound)
    policy_result = _stored_responses_policy_result(inbound)

    normalized_request = normalize_responses_upstream_request(
        policy_result.effective_body,
        requested_model=policy_result.effective_body["model"],
        upstream_model="gpt-5.2",
    )
    outbound = build_responses_upstream_body(normalized_request)
    inbound["input"][0]["content"][0]["text"] = "mutated"
    rebuilt = build_responses_upstream_body(normalized_request)

    assert outbound == {
        "model": "gpt-5.2",
        "input": [{"role": "user", "content": [{"type": "input_text", "text": "continue"}]}],
        "max_output_tokens": 12,
        "store": False,
        "conversation": "conv_owned_123",
    }
    assert rebuilt["input"][0]["content"][0]["text"] == "continue"
    assert original["input"][0]["content"][0]["text"] == "continue"


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("unknown_top_level", "SHOULD_NOT_REACH_PROVIDER_TOP_LEVEL", "responses_field_not_supported"),
        ("parallel_tool_calls", True, "responses_tools_not_supported"),
        ("background", True, "responses_background_not_supported"),
        ("include", ["output_text"], "responses_multimodal_not_supported"),
        ("prompt", {"id": "prompt_123"}, "responses_state_not_supported"),
        ("modalities", ["audio"], "responses_multimodal_not_supported"),
        ("audio", {"format": "wav"}, "responses_multimodal_not_supported"),
        ("stream_options", {"include_usage": True}, "responses_field_not_supported"),
        ("store", True, "responses_store_not_supported"),
        ("stream", "true", "responses_field_invalid_type"),
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
    with pytest.raises(ValueError, match="unapproved top-level fields"):
        normalize_responses_upstream_request(
            {
                "model": "classroom-responses",
                "input": "hello",
                "store": False,
                "max_output_tokens": 12,
                "provider_state": {"id": "SHOULD_NOT_REACH_PROVIDER_NESTED"},
            },
            requested_model="classroom-responses",
            upstream_model="gpt-5.2",
        )


def test_responses_builder_rejects_raw_effective_body_mapping() -> None:
    with pytest.raises(TypeError, match="normalized request contract"):
        build_responses_upstream_body({
            "model": "gpt-5.2",
            "input": "hello",
            "store": False,
        })


def test_conversation_items_create_reconstructs_exact_body_and_deep_copies() -> None:
    body = {
        "items": [
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "hello"}],
            }
        ]
    }
    normalized_request = normalize_conversation_items_create_upstream_request(body)
    outbound = build_conversation_items_create_upstream_body(normalized_request)

    body["items"][0]["content"][0]["text"] = "mutated"
    rebuilt = build_conversation_items_create_upstream_body(normalized_request)

    assert outbound == {
        "items": [
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "hello"}],
            }
        ]
    }
    assert rebuilt == outbound
    assert outbound["items"] is not body["items"]


def test_conversation_items_query_reconstructs_exact_query_and_deep_copies() -> None:
    query = {
        "after": "msg_1",
        "before": "msg_9",
        "include": ["message.input_image.image_url"],
        "limit": 10,
        "order": "asc",
    }
    normalized_request = normalize_conversation_items_query_request(query)
    outbound = build_conversation_items_query_params(normalized_request)

    query["include"].append("message.output_text.logprobs")
    rebuilt = build_conversation_items_query_params(normalized_request)

    assert outbound == {
        "after": "msg_1",
        "before": "msg_9",
        "include": ["message.input_image.image_url"],
        "limit": 10,
        "order": "asc",
    }
    assert rebuilt == outbound
    assert outbound["include"] is not query["include"]


def test_conversation_items_builders_reject_raw_mappings() -> None:
    with pytest.raises(TypeError, match="normalized request contract"):
        build_conversation_items_create_upstream_body({"items": []})
    with pytest.raises(TypeError, match="normalized request contract"):
        build_conversation_items_query_params({"limit": 10})


def test_conversation_update_reconstructs_exact_body_and_deep_copies() -> None:
    body = {"metadata": {"course": "slaif", "cohort": "2026-summer"}}
    normalized_request = normalize_conversation_update_upstream_request(body)
    outbound = build_conversation_update_upstream_body(normalized_request)

    body["metadata"]["course"] = "mutated"  # type: ignore[index]
    rebuilt = build_conversation_update_upstream_body(normalized_request)

    assert outbound == {"metadata": {"course": "slaif", "cohort": "2026-summer"}}
    assert rebuilt == outbound
    assert rebuilt["metadata"] is not body["metadata"]


def test_conversation_update_builder_rejects_raw_mappings() -> None:
    with pytest.raises(TypeError, match="normalized request contract"):
        build_conversation_update_upstream_body({"metadata": {"safe": "value"}})
