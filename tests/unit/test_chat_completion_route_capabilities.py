from __future__ import annotations

import pytest

from slaif_gateway.services.chat_completion_route_capabilities import (
    CHAT_COMPLETIONS_CAPABILITIES_KEY,
    CHAT_CAPABILITY_AUDIO_INPUTS,
    CHAT_CAPABILITY_CUSTOM_TOOLS,
    CHAT_CAPABILITY_FILE_INPUTS,
    CHAT_CAPABILITY_FUNCTION_TOOLS,
    CHAT_CAPABILITY_IMAGE_INPUTS,
    CHAT_CAPABILITY_JSON_MODE,
    CHAT_CAPABILITY_LOGPROBS,
    CHAT_CAPABILITY_MULTIPLE_CHOICES,
    CHAT_CAPABILITY_STREAMING,
    CHAT_CAPABILITY_STRUCTURED_OUTPUTS,
    CHAT_CAPABILITY_TEXT,
    ChatCompletionRouteCapabilityError,
    default_chat_completion_capabilities,
    enforce_chat_completion_route_capabilities,
)


def _payload(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "model": "gpt-4.1-mini",
        "messages": [{"role": "user", "content": "hello"}],
    }
    body.update(overrides)
    return body


def _caps(**overrides: bool) -> dict[str, object]:
    capabilities = default_chat_completion_capabilities(supports_streaming=True)
    capabilities.update(overrides)
    return {CHAT_COMPLETIONS_CAPABILITIES_KEY: capabilities}


def test_text_only_request_passes_when_route_allows_text_chat() -> None:
    enforce_chat_completion_route_capabilities(
        _payload(),
        route_capabilities=_caps(),
        route_supports_streaming=True,
        requested_model="gpt-4.1-mini",
    )


def test_text_only_request_fails_when_route_lacks_text_chat() -> None:
    with pytest.raises(ChatCompletionRouteCapabilityError) as exc_info:
        enforce_chat_completion_route_capabilities(
            _payload(),
            route_capabilities=_caps(**{CHAT_CAPABILITY_TEXT: False}),
            route_supports_streaming=True,
            requested_model="gpt-4.1-mini",
        )

    assert exc_info.value.error_code == "chat_capability_not_supported"
    assert exc_info.value.param == "model"


def test_streaming_requires_streaming_capability() -> None:
    with pytest.raises(ChatCompletionRouteCapabilityError) as exc_info:
        enforce_chat_completion_route_capabilities(
            _payload(stream=True),
            route_capabilities=_caps(**{CHAT_CAPABILITY_STREAMING: False}),
            route_supports_streaming=True,
            requested_model="gpt-4.1-mini",
        )

    assert exc_info.value.error_code == "chat_capability_not_supported"
    assert exc_info.value.param == "stream"


def test_legacy_supports_streaming_field_is_used_for_routes_without_chat_metadata() -> None:
    with pytest.raises(ChatCompletionRouteCapabilityError) as exc_info:
        enforce_chat_completion_route_capabilities(
            _payload(stream=True),
            route_capabilities={},
            route_supports_streaming=False,
            requested_model="gpt-4.1-mini",
        )

    assert exc_info.value.param == "stream"


def test_function_tools_require_function_tool_capability_without_schema_inspection() -> None:
    raw_schema_marker = "raw function schema marker"
    with pytest.raises(ChatCompletionRouteCapabilityError) as exc_info:
        enforce_chat_completion_route_capabilities(
            _payload(
                tools=[
                    {
                        "type": "function",
                        "function": {
                            "name": "delete_file",
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "authorization": {"description": raw_schema_marker}
                                },
                            },
                        },
                    }
                ]
            ),
            route_capabilities=_caps(**{CHAT_CAPABILITY_FUNCTION_TOOLS: False}),
            route_supports_streaming=True,
            requested_model="gpt-4.1-mini",
        )

    assert exc_info.value.param == "tools"
    assert raw_schema_marker not in exc_info.value.safe_message


def test_custom_tools_require_explicit_custom_tool_capability_without_semantic_policing() -> None:
    raw_grammar_marker = "raw custom grammar marker"

    with pytest.raises(ChatCompletionRouteCapabilityError) as absent_exc:
        enforce_chat_completion_route_capabilities(
            _payload(
                tools=[
                    {
                        "type": "custom",
                        "custom": {
                            "name": "run_shell",
                            "format": {
                                "type": "grammar",
                                "grammar": {
                                    "syntax": "regex",
                                    "definition": raw_grammar_marker,
                                },
                            },
                        },
                    }
                ]
            ),
            route_capabilities=_caps(),
            route_supports_streaming=True,
            requested_model="gpt-4.1-mini",
        )

    assert absent_exc.value.error_code == "chat_custom_tool_capability_not_supported"
    assert absent_exc.value.param == "tools"
    assert raw_grammar_marker not in absent_exc.value.safe_message

    with pytest.raises(ChatCompletionRouteCapabilityError) as false_exc:
        enforce_chat_completion_route_capabilities(
            _payload(tools=[{"type": "custom", "custom": {"name": "delete_file"}}]),
            route_capabilities=_caps(**{CHAT_CAPABILITY_CUSTOM_TOOLS: False}),
            route_supports_streaming=True,
            requested_model="gpt-4.1-mini",
        )

    assert false_exc.value.error_code == "chat_custom_tool_capability_not_supported"

    enforce_chat_completion_route_capabilities(
        _payload(tools=[{"type": "custom", "custom": {"name": "delete_file"}}]),
        route_capabilities=_caps(**{CHAT_CAPABILITY_CUSTOM_TOOLS: True}),
        route_supports_streaming=True,
        requested_model="gpt-4.1-mini",
    )


def test_multiple_choices_require_explicit_multiple_choice_capability() -> None:
    with pytest.raises(ChatCompletionRouteCapabilityError) as absent_exc:
        enforce_chat_completion_route_capabilities(
            _payload(n=2),
            route_capabilities=_caps(),
            route_supports_streaming=True,
            requested_model="gpt-4.1-mini",
        )

    assert absent_exc.value.error_code == "chat_multiple_choices_capability_not_supported"
    assert absent_exc.value.param == "n"

    with pytest.raises(ChatCompletionRouteCapabilityError) as false_exc:
        enforce_chat_completion_route_capabilities(
            _payload(n=2),
            route_capabilities=_caps(**{CHAT_CAPABILITY_MULTIPLE_CHOICES: False}),
            route_supports_streaming=True,
            requested_model="gpt-4.1-mini",
        )

    assert false_exc.value.error_code == "chat_multiple_choices_capability_not_supported"

    enforce_chat_completion_route_capabilities(
        _payload(n=2),
        route_capabilities=_caps(**{CHAT_CAPABILITY_MULTIPLE_CHOICES: True}),
        route_supports_streaming=True,
        requested_model="gpt-4.1-mini",
    )


def test_choice_count_one_does_not_require_multiple_choice_capability() -> None:
    enforce_chat_completion_route_capabilities(
        _payload(n=1),
        route_capabilities=_caps(**{CHAT_CAPABILITY_MULTIPLE_CHOICES: False}),
        route_supports_streaming=True,
        requested_model="gpt-4.1-mini",
    )


def test_multiple_choices_with_function_tools_require_both_capabilities() -> None:
    with pytest.raises(ChatCompletionRouteCapabilityError) as exc_info:
        enforce_chat_completion_route_capabilities(
            _payload(n=2, tools=[{"type": "function", "function": {"name": "lookup"}}]),
            route_capabilities=_caps(**{CHAT_CAPABILITY_MULTIPLE_CHOICES: True, CHAT_CAPABILITY_FUNCTION_TOOLS: False}),
            route_supports_streaming=True,
            requested_model="gpt-4.1-mini",
        )

    assert exc_info.value.error_code == "chat_capability_not_supported"
    assert exc_info.value.param == "tools"

    enforce_chat_completion_route_capabilities(
        _payload(n=2, tools=[{"type": "function", "function": {"name": "lookup"}}]),
        route_capabilities=_caps(**{CHAT_CAPABILITY_MULTIPLE_CHOICES: True, CHAT_CAPABILITY_FUNCTION_TOOLS: True}),
        route_supports_streaming=True,
        requested_model="gpt-4.1-mini",
    )


def test_multiple_choices_with_custom_tools_require_both_capabilities() -> None:
    with pytest.raises(ChatCompletionRouteCapabilityError) as exc_info:
        enforce_chat_completion_route_capabilities(
            _payload(n=2, tools=[{"type": "custom", "custom": {"name": "run_shell"}}]),
            route_capabilities=_caps(**{CHAT_CAPABILITY_MULTIPLE_CHOICES: True, CHAT_CAPABILITY_CUSTOM_TOOLS: False}),
            route_supports_streaming=True,
            requested_model="gpt-4.1-mini",
        )

    assert exc_info.value.error_code == "chat_custom_tool_capability_not_supported"
    assert exc_info.value.param == "tools"

    enforce_chat_completion_route_capabilities(
        _payload(n=2, tools=[{"type": "custom", "custom": {"name": "run_shell"}}]),
        route_capabilities=_caps(**{CHAT_CAPABILITY_MULTIPLE_CHOICES: True, CHAT_CAPABILITY_CUSTOM_TOOLS: True}),
        route_supports_streaming=True,
        requested_model="gpt-4.1-mini",
    )


def _image_payload(**overrides: object) -> dict[str, object]:
    body = _payload(
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "describe"},
                    {"type": "image_url", "image_url": {"url": "https://example.test/image.png"}},
                ],
            }
        ]
    )
    body.update(overrides)
    return body


def test_image_input_requires_explicit_image_capability_without_url_leakage() -> None:
    raw_url = "https://example.test/private.png?token=secret"

    with pytest.raises(ChatCompletionRouteCapabilityError) as absent_exc:
        enforce_chat_completion_route_capabilities(
            _payload(
                messages=[
                    {
                        "role": "user",
                        "content": [{"type": "image_url", "image_url": {"url": raw_url}}],
                    }
                ]
            ),
            route_capabilities=_caps(),
            route_supports_streaming=True,
            requested_model="gpt-4.1-mini",
        )

    assert absent_exc.value.error_code == "chat_image_input_capability_not_supported"
    assert absent_exc.value.param == "messages"
    assert raw_url not in absent_exc.value.safe_message

    with pytest.raises(ChatCompletionRouteCapabilityError) as false_exc:
        enforce_chat_completion_route_capabilities(
            _image_payload(),
            route_capabilities=_caps(**{CHAT_CAPABILITY_IMAGE_INPUTS: False}),
            route_supports_streaming=True,
            requested_model="gpt-4.1-mini",
        )

    assert false_exc.value.error_code == "chat_image_input_capability_not_supported"

    enforce_chat_completion_route_capabilities(
        _image_payload(),
        route_capabilities=_caps(**{CHAT_CAPABILITY_IMAGE_INPUTS: True}),
        route_supports_streaming=True,
        requested_model="gpt-4.1-mini",
    )


def test_text_only_request_does_not_require_image_capability() -> None:
    enforce_chat_completion_route_capabilities(
        _payload(),
        route_capabilities=_caps(**{CHAT_CAPABILITY_IMAGE_INPUTS: False}),
        route_supports_streaming=True,
        requested_model="gpt-4.1-mini",
    )


def _file_payload(**overrides: object) -> dict[str, object]:
    body = _payload(
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "summarize"},
                    {
                        "type": "file",
                        "file": {"filename": "notes.txt", "file_data": "SGVsbG8="},
                    },
                ],
            }
        ]
    )
    body.update(overrides)
    return body


def _audio_payload(**overrides: object) -> dict[str, object]:
    body = _payload(
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "transcribe"},
                    {
                        "type": "input_audio",
                        "input_audio": {"data": "UklGRiQ=", "format": "wav"},
                    },
                ],
            }
        ]
    )
    body.update(overrides)
    return body


def test_file_input_requires_explicit_file_capability_without_payload_leakage() -> None:
    raw_file_data = "c2VjcmV0IGZpbGUgcGF5bG9hZA=="

    with pytest.raises(ChatCompletionRouteCapabilityError) as absent_exc:
        enforce_chat_completion_route_capabilities(
            _payload(
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "file",
                                "file": {"filename": "secret.txt", "file_data": raw_file_data},
                            }
                        ],
                    }
                ]
            ),
            route_capabilities=_caps(),
            route_supports_streaming=True,
            requested_model="gpt-4.1-mini",
        )

    assert absent_exc.value.error_code == "chat_file_input_capability_not_supported"
    assert absent_exc.value.param == "messages"
    assert raw_file_data not in absent_exc.value.safe_message
    assert "secret.txt" not in absent_exc.value.safe_message

    with pytest.raises(ChatCompletionRouteCapabilityError) as false_exc:
        enforce_chat_completion_route_capabilities(
            _file_payload(),
            route_capabilities=_caps(**{CHAT_CAPABILITY_FILE_INPUTS: False}),
            route_supports_streaming=True,
            requested_model="gpt-4.1-mini",
        )

    assert false_exc.value.error_code == "chat_file_input_capability_not_supported"

    enforce_chat_completion_route_capabilities(
        _file_payload(),
        route_capabilities=_caps(**{CHAT_CAPABILITY_FILE_INPUTS: True}),
        route_supports_streaming=True,
        requested_model="gpt-4.1-mini",
    )


def test_text_only_request_does_not_require_file_capability() -> None:
    enforce_chat_completion_route_capabilities(
        _payload(),
        route_capabilities=_caps(**{CHAT_CAPABILITY_FILE_INPUTS: False}),
        route_supports_streaming=True,
        requested_model="gpt-4.1-mini",
    )


def test_audio_input_requires_explicit_audio_capability_without_payload_leakage() -> None:
    raw_audio_data = "c2VjcmV0LWF1ZGlvLXBheWxvYWQ="

    with pytest.raises(ChatCompletionRouteCapabilityError) as absent_exc:
        enforce_chat_completion_route_capabilities(
            _payload(
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "input_audio",
                                "input_audio": {"data": raw_audio_data, "format": "wav"},
                            }
                        ],
                    }
                ]
            ),
            route_capabilities=_caps(),
            route_supports_streaming=True,
            requested_model="gpt-4.1-mini",
        )

    assert absent_exc.value.error_code == "chat_audio_input_capability_not_supported"
    assert absent_exc.value.param == "messages"
    assert raw_audio_data not in absent_exc.value.safe_message

    with pytest.raises(ChatCompletionRouteCapabilityError) as false_exc:
        enforce_chat_completion_route_capabilities(
            _audio_payload(),
            route_capabilities=_caps(**{CHAT_CAPABILITY_AUDIO_INPUTS: False}),
            route_supports_streaming=True,
            requested_model="gpt-4.1-mini",
        )

    assert false_exc.value.error_code == "chat_audio_input_capability_not_supported"

    enforce_chat_completion_route_capabilities(
        _audio_payload(),
        route_capabilities=_caps(**{CHAT_CAPABILITY_AUDIO_INPUTS: True}),
        route_supports_streaming=True,
        requested_model="gpt-4.1-mini",
    )


def test_text_only_request_does_not_require_audio_capability() -> None:
    enforce_chat_completion_route_capabilities(
        _payload(),
        route_capabilities=_caps(**{CHAT_CAPABILITY_AUDIO_INPUTS: False}),
        route_supports_streaming=True,
        requested_model="gpt-4.1-mini",
    )


def test_file_input_with_image_function_custom_and_n_requires_all_capabilities() -> None:
    payload = _file_payload(
        n=2,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "summarize"},
                    {
                        "type": "image_url",
                        "image_url": {"url": "https://example.test/image.png"},
                    },
                    {
                        "type": "file",
                        "file": {"filename": "notes.txt", "file_data": "SGVsbG8="},
                    },
                ],
            }
        ],
        tools=[
            {"type": "function", "function": {"name": "lookup"}},
            {"type": "custom", "custom": {"name": "run_shell"}},
        ],
    )

    with pytest.raises(ChatCompletionRouteCapabilityError) as file_exc:
        enforce_chat_completion_route_capabilities(
            payload,
            route_capabilities=_caps(
                **{
                    CHAT_CAPABILITY_IMAGE_INPUTS: True,
                    CHAT_CAPABILITY_MULTIPLE_CHOICES: True,
                    CHAT_CAPABILITY_FUNCTION_TOOLS: True,
                    CHAT_CAPABILITY_CUSTOM_TOOLS: True,
                    CHAT_CAPABILITY_FILE_INPUTS: False,
                }
            ),
            route_supports_streaming=True,
            requested_model="gpt-4.1-mini",
        )

    assert file_exc.value.error_code == "chat_file_input_capability_not_supported"

    enforce_chat_completion_route_capabilities(
        payload,
        route_capabilities=_caps(
            **{
                CHAT_CAPABILITY_IMAGE_INPUTS: True,
                CHAT_CAPABILITY_MULTIPLE_CHOICES: True,
                CHAT_CAPABILITY_FUNCTION_TOOLS: True,
                CHAT_CAPABILITY_CUSTOM_TOOLS: True,
                CHAT_CAPABILITY_FILE_INPUTS: True,
            }
        ),
        route_supports_streaming=True,
        requested_model="gpt-4.1-mini",
    )


def test_audio_input_with_image_file_function_custom_and_n_requires_all_capabilities() -> None:
    payload = _audio_payload(
        n=2,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "analyze"},
                    {
                        "type": "image_url",
                        "image_url": {"url": "https://example.test/image.png"},
                    },
                    {
                        "type": "file",
                        "file": {"filename": "notes.txt", "file_data": "SGVsbG8="},
                    },
                    {
                        "type": "input_audio",
                        "input_audio": {"data": "UklGRiQ=", "format": "mp3"},
                    },
                ],
            }
        ],
        tools=[
            {"type": "function", "function": {"name": "lookup"}},
            {"type": "custom", "custom": {"name": "run_shell"}},
        ],
    )

    with pytest.raises(ChatCompletionRouteCapabilityError) as audio_exc:
        enforce_chat_completion_route_capabilities(
            payload,
            route_capabilities=_caps(
                **{
                    CHAT_CAPABILITY_IMAGE_INPUTS: True,
                    CHAT_CAPABILITY_FILE_INPUTS: True,
                    CHAT_CAPABILITY_MULTIPLE_CHOICES: True,
                    CHAT_CAPABILITY_FUNCTION_TOOLS: True,
                    CHAT_CAPABILITY_CUSTOM_TOOLS: True,
                    CHAT_CAPABILITY_AUDIO_INPUTS: False,
                }
            ),
            route_supports_streaming=True,
            requested_model="gpt-4.1-mini",
        )

    assert audio_exc.value.error_code == "chat_audio_input_capability_not_supported"

    enforce_chat_completion_route_capabilities(
        payload,
        route_capabilities=_caps(
            **{
                CHAT_CAPABILITY_IMAGE_INPUTS: True,
                CHAT_CAPABILITY_FILE_INPUTS: True,
                CHAT_CAPABILITY_MULTIPLE_CHOICES: True,
                CHAT_CAPABILITY_FUNCTION_TOOLS: True,
                CHAT_CAPABILITY_CUSTOM_TOOLS: True,
                CHAT_CAPABILITY_AUDIO_INPUTS: True,
            }
        ),
        route_supports_streaming=True,
        requested_model="gpt-4.1-mini",
    )


def test_image_input_with_function_tools_requires_both_capabilities() -> None:
    with pytest.raises(ChatCompletionRouteCapabilityError) as exc_info:
        enforce_chat_completion_route_capabilities(
            _image_payload(tools=[{"type": "function", "function": {"name": "lookup"}}]),
            route_capabilities=_caps(**{CHAT_CAPABILITY_IMAGE_INPUTS: True, CHAT_CAPABILITY_FUNCTION_TOOLS: False}),
            route_supports_streaming=True,
            requested_model="gpt-4.1-mini",
        )

    assert exc_info.value.error_code == "chat_capability_not_supported"
    assert exc_info.value.param == "tools"

    enforce_chat_completion_route_capabilities(
        _image_payload(tools=[{"type": "function", "function": {"name": "lookup"}}]),
        route_capabilities=_caps(**{CHAT_CAPABILITY_IMAGE_INPUTS: True, CHAT_CAPABILITY_FUNCTION_TOOLS: True}),
        route_supports_streaming=True,
        requested_model="gpt-4.1-mini",
    )


def test_image_input_with_custom_tools_and_n_choices_requires_all_capabilities() -> None:
    with pytest.raises(ChatCompletionRouteCapabilityError) as custom_exc:
        enforce_chat_completion_route_capabilities(
            _image_payload(n=2, tools=[{"type": "custom", "custom": {"name": "run_shell"}}]),
            route_capabilities=_caps(
                **{
                    CHAT_CAPABILITY_IMAGE_INPUTS: True,
                    CHAT_CAPABILITY_MULTIPLE_CHOICES: True,
                    CHAT_CAPABILITY_CUSTOM_TOOLS: False,
                }
            ),
            route_supports_streaming=True,
            requested_model="gpt-4.1-mini",
        )

    assert custom_exc.value.error_code == "chat_custom_tool_capability_not_supported"

    enforce_chat_completion_route_capabilities(
        _image_payload(n=2, tools=[{"type": "custom", "custom": {"name": "run_shell"}}]),
        route_capabilities=_caps(
            **{
                CHAT_CAPABILITY_IMAGE_INPUTS: True,
                CHAT_CAPABILITY_MULTIPLE_CHOICES: True,
                CHAT_CAPABILITY_CUSTOM_TOOLS: True,
            }
        ),
        route_supports_streaming=True,
        requested_model="gpt-4.1-mini",
    )


def test_legacy_functions_require_legacy_capability() -> None:
    capabilities = default_chat_completion_capabilities(supports_streaming=True)
    capabilities["chat_legacy_functions"] = False

    with pytest.raises(ChatCompletionRouteCapabilityError) as exc_info:
        enforce_chat_completion_route_capabilities(
            _payload(functions=[{"name": "lookup"}]),
            route_capabilities={CHAT_COMPLETIONS_CAPABILITIES_KEY: capabilities},
            route_supports_streaming=True,
            requested_model="gpt-4.1-mini",
        )

    assert exc_info.value.param == "functions"


def test_response_format_requires_matching_capability() -> None:
    with pytest.raises(ChatCompletionRouteCapabilityError) as json_exc:
        enforce_chat_completion_route_capabilities(
            _payload(response_format={"type": "json_object"}),
            route_capabilities=_caps(**{CHAT_CAPABILITY_JSON_MODE: False}),
            route_supports_streaming=True,
            requested_model="gpt-4.1-mini",
        )
    with pytest.raises(ChatCompletionRouteCapabilityError) as schema_exc:
        enforce_chat_completion_route_capabilities(
            _payload(response_format={"type": "json_schema", "json_schema": {"schema": {}}}),
            route_capabilities=_caps(**{CHAT_CAPABILITY_STRUCTURED_OUTPUTS: False}),
            route_supports_streaming=True,
            requested_model="gpt-4.1-mini",
        )

    assert json_exc.value.param == "response_format"
    assert schema_exc.value.param == "response_format"


def test_logprobs_requires_logprobs_capability() -> None:
    with pytest.raises(ChatCompletionRouteCapabilityError) as exc_info:
        enforce_chat_completion_route_capabilities(
            _payload(logprobs=True),
            route_capabilities=_caps(**{CHAT_CAPABILITY_LOGPROBS: False}),
            route_supports_streaming=True,
            requested_model="gpt-4.1-mini",
        )

    assert exc_info.value.param == "logprobs"


def test_search_specific_model_requires_hosted_web_search_capability() -> None:
    with pytest.raises(ChatCompletionRouteCapabilityError) as exc_info:
        enforce_chat_completion_route_capabilities(
            _payload(model="gpt-5-search-api"),
            route_capabilities=_caps(),
            route_supports_streaming=True,
            requested_model="gpt-5-search-api",
        )

    assert exc_info.value.error_code == "chat_hosted_tool_not_allowed"
    assert exc_info.value.param == "model"


def test_known_hosted_tools_require_matching_route_capability() -> None:
    with pytest.raises(ChatCompletionRouteCapabilityError) as exc_info:
        enforce_chat_completion_route_capabilities(
            _payload(tools=[{"type": "web_search_preview"}]),
            route_capabilities=_caps(),
            route_supports_streaming=True,
            requested_model="gpt-4.1-mini",
        )

    assert exc_info.value.error_code == "chat_hosted_tool_not_allowed"
    assert exc_info.value.param == "tools[0].type"


def test_unknown_and_malformed_chat_capability_metadata_fails_closed() -> None:
    with pytest.raises(ChatCompletionRouteCapabilityError) as unknown_exc:
        enforce_chat_completion_route_capabilities(
            _payload(),
            route_capabilities={CHAT_COMPLETIONS_CAPABILITIES_KEY: {"chat_text": True, "future": True}},
            route_supports_streaming=True,
            requested_model="gpt-4.1-mini",
        )
    with pytest.raises(ChatCompletionRouteCapabilityError) as malformed_exc:
        enforce_chat_completion_route_capabilities(
            _payload(),
            route_capabilities={CHAT_COMPLETIONS_CAPABILITIES_KEY: {"chat_text": "yes"}},
            route_supports_streaming=True,
            requested_model="gpt-4.1-mini",
        )

    assert unknown_exc.value.error_code == "chat_route_capability_invalid"
    assert malformed_exc.value.error_code == "chat_route_capability_invalid"
