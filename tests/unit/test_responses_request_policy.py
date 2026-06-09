from __future__ import annotations

import json

import pytest

from slaif_gateway.config import Settings
from slaif_gateway.services.policy_errors import RequestPolicyError
from slaif_gateway.services.responses_request_policy import (
    ResponsesRequestPolicy,
    validate_conversation_items_create_body,
)


def _body(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "model": "gpt-test",
        "input": "hello",
        "max_output_tokens": 20,
    }
    body.update(overrides)
    return body


def test_valid_string_input_injects_store_false_and_preserves_supported_fields() -> None:
    result = ResponsesRequestPolicy(Settings()).apply(
        _body(
            instructions="answer briefly",
            temperature=0.2,
            top_p=0.9,
            metadata={"safe": "value"},
            text={"format": {"type": "text"}},
        )
    )

    assert result.effective_body["store"] is False
    assert result.effective_body["input"] == "hello"
    assert result.effective_body["max_output_tokens"] == 20
    assert result.estimated_input_tokens > 0


def test_stream_true_is_policy_valid_before_route_capability_check() -> None:
    result = ResponsesRequestPolicy(Settings()).apply(_body(stream=True))

    assert result.effective_body["stream"] is True
    assert result.effective_body["store"] is False


def test_store_true_passes_only_in_stored_response_policy_mode() -> None:
    result = ResponsesRequestPolicy(Settings()).apply(_body(store=True), allow_store=True)

    assert result.effective_body["store"] is True
    assert "stream" not in result.effective_body


def test_store_true_stream_true_rejects_before_route_provider() -> None:
    with pytest.raises(RequestPolicyError) as exc_info:
        ResponsesRequestPolicy(Settings()).apply(
            _body(store=True, stream=True),
            allow_store=True,
        )

    assert exc_info.value.error_code == "responses_stored_response_streaming_not_supported"
    assert exc_info.value.param == "stream"


def test_previous_response_id_passes_for_non_streaming_create() -> None:
    result = ResponsesRequestPolicy(Settings()).apply(
        _body(previous_response_id="resp_previous_123"),
        allow_store=True,
    )

    assert result.effective_body["previous_response_id"] == "resp_previous_123"
    assert result.effective_body["store"] is False


@pytest.mark.parametrize("value", ["", 123, None])
def test_previous_response_id_rejects_invalid_shape(value: object) -> None:
    with pytest.raises(RequestPolicyError) as exc_info:
        ResponsesRequestPolicy(Settings()).apply(
            _body(previous_response_id=value),
            allow_store=True,
        )

    assert exc_info.value.error_code == "responses_previous_response_id_invalid"
    assert exc_info.value.param == "previous_response_id"


def test_previous_response_id_rejects_oversized_value() -> None:
    with pytest.raises(RequestPolicyError) as exc_info:
        ResponsesRequestPolicy(
            Settings(RESPONSES_MAX_PREVIOUS_RESPONSE_ID_BYTES=8)
        ).apply(
            _body(previous_response_id="resp_previous_123"),
            allow_store=True,
        )

    assert exc_info.value.error_code == "responses_previous_response_id_too_large"
    assert exc_info.value.param == "previous_response_id"


def test_previous_response_id_stream_true_rejects_before_route_provider() -> None:
    with pytest.raises(RequestPolicyError) as exc_info:
        ResponsesRequestPolicy(Settings()).apply(
            _body(previous_response_id="resp_previous_123", stream=True),
            allow_store=True,
        )

    assert exc_info.value.error_code == "responses_previous_response_streaming_not_supported"
    assert exc_info.value.param == "previous_response_id"


def test_conversation_passes_for_non_streaming_create() -> None:
    result = ResponsesRequestPolicy(Settings()).apply(
        _body(conversation="conv_owned_123"),
        allow_store=True,
    )

    assert result.effective_body["conversation"] == "conv_owned_123"
    assert result.effective_body["store"] is False


@pytest.mark.parametrize("value", ["", 123, None, {"id": "conv_123"}])
def test_conversation_rejects_invalid_shape(value: object) -> None:
    with pytest.raises(RequestPolicyError) as exc_info:
        ResponsesRequestPolicy(Settings()).apply(
            _body(conversation=value),
            allow_store=True,
        )

    assert exc_info.value.error_code == "responses_conversation_invalid"
    assert exc_info.value.param == "conversation"


def test_conversation_rejects_oversized_value() -> None:
    with pytest.raises(RequestPolicyError) as exc_info:
        ResponsesRequestPolicy(Settings(RESPONSES_MAX_CONVERSATION_ID_BYTES=8)).apply(
            _body(conversation="conv_owned_123"),
            allow_store=True,
        )

    assert exc_info.value.error_code == "responses_conversation_too_large"
    assert exc_info.value.param == "conversation"


def test_conversation_with_previous_response_id_rejects_before_route_provider() -> None:
    with pytest.raises(RequestPolicyError) as exc_info:
        ResponsesRequestPolicy(Settings()).apply(
            _body(conversation="conv_123", previous_response_id="resp_123"),
            allow_store=True,
        )

    assert exc_info.value.error_code == "responses_conversation_previous_response_not_supported"
    assert exc_info.value.param == "conversation"


def test_conversation_stream_true_rejects_before_route_provider() -> None:
    with pytest.raises(RequestPolicyError) as exc_info:
        ResponsesRequestPolicy(Settings()).apply(
            _body(conversation="conv_123", stream=True),
            allow_store=True,
        )

    assert exc_info.value.error_code == "responses_conversation_streaming_not_supported"
    assert exc_info.value.param == "conversation"


def test_omitted_max_output_tokens_injects_default() -> None:
    result = ResponsesRequestPolicy(Settings(DEFAULT_MAX_OUTPUT_TOKENS=77)).apply(
        {"model": "gpt-test", "input": "hello"}
    )

    assert result.effective_body["max_output_tokens"] == 77
    assert result.injected_default_output_tokens is True


def test_input_token_count_accepts_supported_stateless_subset_without_output_defaults() -> None:
    result = ResponsesRequestPolicy(Settings()).apply_input_token_count(
        {
            "model": "gpt-5.2",
            "input": "Count these tokens.",
            "instructions": "Be concise.",
            "text": {"format": {"type": "text"}},
            "tools": [
                {
                    "type": "function",
                    "name": "lookup",
                    "parameters": {"type": "object", "properties": {}},
                },
                {
                    "type": "custom",
                    "name": "emit_text",
                    "format": {"type": "text"},
                },
            ],
            "tool_choice": "auto",
            "parallel_tool_calls": True,
            "truncation": "auto",
        }
    )

    assert result.effective_body == {
        "model": "gpt-5.2",
        "input": "Count these tokens.",
        "instructions": "Be concise.",
        "text": {"format": {"type": "text"}},
        "tools": [
            {
                "type": "function",
                "name": "lookup",
                "parameters": {"type": "object", "properties": {}},
            },
            {
                "type": "custom",
                "name": "emit_text",
                "format": {"type": "text"},
            },
        ],
        "tool_choice": "auto",
        "parallel_tool_calls": True,
        "truncation": "auto",
    }
    assert result.effective_output_tokens == 0
    assert result.requested_output_tokens == 0
    assert result.injected_default_output_tokens is False
    assert "store" not in result.effective_body
    assert "max_output_tokens" not in result.effective_body
    assert result.estimated_input_tokens > 0


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("stream", True),
        ("store", False),
        ("max_output_tokens", 10),
        ("previous_response_id", "resp_123"),
        ("conversation", "conv_123"),
        ("background", True),
        ("reasoning", {"effort": "low"}),
    ],
)
def test_input_token_count_rejects_create_or_stateful_fields(field: str, value: object) -> None:
    with pytest.raises(RequestPolicyError) as exc_info:
        ResponsesRequestPolicy(Settings()).apply_input_token_count(
            {
                "model": "gpt-5.2",
                "input": "hello",
                field: value,
            }
        )

    assert exc_info.value.param == field


def test_input_token_count_rejects_invalid_parallel_tool_calls_and_truncation() -> None:
    with pytest.raises(RequestPolicyError) as parallel_exc:
        ResponsesRequestPolicy(Settings()).apply_input_token_count(
            {"model": "gpt-5.2", "input": "hello", "parallel_tool_calls": "yes"}
        )
    assert parallel_exc.value.error_code == "responses_field_invalid_type"

    with pytest.raises(RequestPolicyError) as truncation_exc:
        ResponsesRequestPolicy(Settings()).apply_input_token_count(
            {"model": "gpt-5.2", "input": "hello", "truncation": "unsupported"}
        )
    assert truncation_exc.value.error_code == "responses_field_value_not_supported"


def test_compact_accepts_string_input_with_bounded_output_reservation() -> None:
    result = ResponsesRequestPolicy(
        Settings(RESPONSES_COMPACT_DEFAULT_MAX_OUTPUT_TOKENS=111)
    ).apply_compact(
        {
            "model": "gpt-5.2",
            "input": "Compact this transcript.",
            "instructions": "Preserve decisions.",
        }
    )

    assert result.effective_body == {
        "model": "gpt-5.2",
        "input": "Compact this transcript.",
        "instructions": "Preserve decisions.",
    }
    assert result.effective_output_tokens == 111
    assert result.requested_output_tokens == 111
    assert result.injected_default_output_tokens is True
    assert result.estimated_input_tokens > 0


def test_compact_accepts_text_focused_item_array() -> None:
    result = ResponsesRequestPolicy(Settings()).apply_compact(
        {
            "model": "gpt-5.2",
            "input": [
                {"role": "user", "content": "Create a landing page."},
                {
                    "id": "msg_001",
                    "type": "message",
                    "status": "completed",
                    "role": "assistant",
                    "content": [
                        {"type": "output_text", "text": "Previous output."},
                        {"type": "input_text", "text": "Additional instruction."},
                    ],
                },
            ],
        }
    )

    assert result.effective_body["input"] == [
        {"role": "user", "content": "Create a landing page."},
        {
            "role": "assistant",
            "content": [
                {"type": "output_text", "text": "Previous output."},
                {"type": "input_text", "text": "Additional instruction."},
            ],
            "type": "message",
            "id": "msg_001",
            "status": "completed",
        },
    ]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("stream", True),
        ("store", False),
        ("background", True),
        ("conversation", "conv_123"),
        ("previous_response_id", "resp_123"),
        ("max_output_tokens", 10),
        ("tools", [{"type": "function", "name": "lookup", "parameters": {}}]),
        ("tool_choice", "auto"),
        ("file_id", "file_123"),
    ],
)
def test_compact_rejects_create_stateful_tools_and_file_fields(field: str, value: object) -> None:
    with pytest.raises(RequestPolicyError) as exc_info:
        ResponsesRequestPolicy(Settings()).apply_compact(
            {
                "model": "gpt-5.2",
                "input": "hello",
                field: value,
            }
        )

    assert exc_info.value.param == field


def test_compact_requires_model_and_input() -> None:
    with pytest.raises(RequestPolicyError) as model_exc:
        ResponsesRequestPolicy(Settings()).apply_compact({"input": "hello"})
    assert model_exc.value.param == "model"

    with pytest.raises(RequestPolicyError) as input_exc:
        ResponsesRequestPolicy(Settings()).apply_compact({"model": "gpt-5.2"})
    assert input_exc.value.error_code == "responses_compact_input_required"
    assert input_exc.value.param == "input"


@pytest.mark.parametrize(
    "part",
    [
        {"type": "input_image", "image_url": "https://example.test/image.png"},
        {"type": "input_file", "file_url": "https://example.test/file.pdf"},
        {"type": "tool_call", "text": "no"},
        {"type": "output_text", "text": "hello", "annotations": []},
    ],
)
def test_compact_rejects_non_text_or_extra_content_parts(part: dict[str, object]) -> None:
    with pytest.raises(RequestPolicyError):
        ResponsesRequestPolicy(Settings()).apply_compact(
            {
                "model": "gpt-5.2",
                "input": [
                    {
                        "role": "assistant",
                        "content": [part],
                    }
                ],
            }
        )


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("background", True, "responses_background_not_supported"),
        ("store", True, "responses_store_not_supported"),
        ("include", ["message.input_image.image_url"], "responses_multimodal_not_supported"),
        ("unknown_future_field", {"x": "y"}, "responses_field_not_supported"),
    ],
)
def test_unsupported_fields_reject_before_forwarding(field: str, value: object, code: str) -> None:
    with pytest.raises(RequestPolicyError) as exc_info:
        ResponsesRequestPolicy(Settings()).apply(_body(**{field: value}))

    assert exc_info.value.error_code == code
    assert exc_info.value.param == field
    assert "hello" not in exc_info.value.safe_message
    assert "resp_123" not in exc_info.value.safe_message


def test_list_input_with_user_text_message_passes() -> None:
    result = ResponsesRequestPolicy(Settings()).apply(
        _body(input=[{"role": "user", "content": "hello"}])
    )

    assert result.effective_body["input"] == [{"role": "user", "content": "hello"}]
    assert result.estimated_input_tokens > 0


def test_list_input_with_supported_roles_and_text_parts_passes() -> None:
    result = ResponsesRequestPolicy(Settings()).apply(
        _body(
            input=[
                {"role": "system", "content": "system text"},
                {"role": "developer", "content": "developer text"},
                {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": "user part"}],
                },
                {"role": "assistant", "content": "assistant text"},
            ]
        )
    )

    assert result.effective_body["input"] == [
        {"role": "system", "content": "system text"},
        {"role": "developer", "content": "developer text"},
        {
            "role": "user",
            "content": [{"type": "input_text", "text": "user part"}],
            "type": "message",
        },
        {"role": "assistant", "content": "assistant text"},
    ]


def test_list_input_with_user_image_url_part_passes_and_preserves_detail() -> None:
    result = ResponsesRequestPolicy(Settings()).apply(
        _body(
            input=[
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": "What is in this image?"},
                        {
                            "type": "input_image",
                            "image_url": "https://example.test/image.png",
                            "detail": "low",
                        },
                    ],
                }
            ]
        )
    )

    assert result.effective_body["input"] == [
        {
            "role": "user",
            "content": [
                {"type": "input_text", "text": "What is in this image?"},
                {
                    "type": "input_image",
                    "image_url": "https://example.test/image.png",
                    "detail": "low",
                },
            ],
        }
    ]
    assert result.estimated_input_tokens > 0


def test_list_input_with_image_data_url_part_passes_and_omits_detail_when_omitted() -> None:
    data_url = "data:image/png;base64,aGVsbG8="

    result = ResponsesRequestPolicy(Settings()).apply(
        _body(
            input=[
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": "Describe this."},
                        {"type": "input_image", "image_url": data_url},
                    ],
                }
            ]
        )
    )

    image_part = result.effective_body["input"][0]["content"][1]
    assert image_part == {"type": "input_image", "image_url": data_url}


def test_list_input_with_file_url_part_passes() -> None:
    result = ResponsesRequestPolicy(Settings()).apply(
        _body(
            input=[
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": "Summarize this PDF."},
                        {
                            "type": "input_file",
                            "file_url": "https://example.test/document.pdf",
                        },
                    ],
                }
            ]
        )
    )

    assert result.effective_body["input"] == [
        {
            "role": "user",
            "content": [
                {"type": "input_text", "text": "Summarize this PDF."},
                {
                    "type": "input_file",
                    "file_url": "https://example.test/document.pdf",
                },
            ],
        }
    ]
    assert result.estimated_input_tokens > 0


@pytest.mark.parametrize(
    ("filename", "file_data"),
    [
        ("document.pdf", "data:application/pdf;base64,aGVsbG8="),
        ("notes.txt", "data:text/plain;base64,aGVsbG8="),
        ("readme.md", "data:text/markdown;base64,aGVsbG8="),
        ("rows.csv", "data:text/csv;base64,aGVsbG8="),
        ("payload.json", "data:application/json;base64,e30="),
    ],
)
def test_list_input_with_file_data_part_passes(filename: str, file_data: str) -> None:
    result = ResponsesRequestPolicy(Settings()).apply(
        _body(
            input=[
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": "Summarize this file."},
                        {
                            "type": "input_file",
                            "filename": filename,
                            "file_data": file_data,
                        },
                    ],
                }
            ]
        )
    )

    assert result.effective_body["input"][0]["content"][1] == {
        "type": "input_file",
        "filename": filename,
        "file_data": file_data,
    }


@pytest.mark.parametrize("detail", ["auto", "low", "high", "original"])
def test_list_input_with_supported_image_detail_values_passes(detail: str) -> None:
    result = ResponsesRequestPolicy(Settings()).apply(
        _body(
            input=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_image",
                            "image_url": "https://example.test/image.png",
                            "detail": detail,
                        }
                    ],
                }
            ]
        )
    )

    assert result.effective_body["input"][0]["content"][0]["detail"] == detail


def test_function_call_output_input_item_passes_as_string_only_tool_result() -> None:
    result = ResponsesRequestPolicy(Settings()).apply(
        _body(
            input=[
                {"role": "user", "content": "call the tool"},
                {
                    "type": "function_call_output",
                    "call_id": "call_123",
                    "output": '{"result":"safe"}',
                },
            ]
        )
    )

    assert result.effective_body["input"] == [
        {"role": "user", "content": "call the tool"},
        {
            "type": "function_call_output",
            "call_id": "call_123",
            "output": '{"result":"safe"}',
        },
    ]
    assert result.estimated_input_tokens > 0


def test_custom_tool_call_output_input_item_passes_as_string_only_tool_result() -> None:
    result = ResponsesRequestPolicy(Settings()).apply(
        _body(
            input=[
                {"role": "user", "content": "call the custom tool"},
                {
                    "type": "custom_tool_call_output",
                    "call_id": "call_123",
                    "output": "safe custom result",
                },
            ]
        )
    )

    assert result.effective_body["input"] == [
        {"role": "user", "content": "call the custom tool"},
        {
            "type": "custom_tool_call_output",
            "call_id": "call_123",
            "output": "safe custom result",
        },
    ]
    assert result.estimated_input_tokens > 0


@pytest.mark.parametrize(
    ("input_value", "param", "code"),
    [
        ([], "input", "responses_input_invalid"),
        ([{"role": "user", "content": ""}], "input[0].content", "responses_input_invalid"),
        ([{"role": "admin", "content": "secret"}], "input[0].role", "responses_input_item_role_not_supported"),
        ([{"role": "user", "content": "secret", "name": "x"}], "input[0].name", "responses_input_item_invalid"),
        ([{"type": "function_call", "role": "user", "content": "secret"}], "input[0].type", "responses_input_tool_item_not_supported"),
        ([{"type": "reasoning", "role": "user", "content": "secret"}], "input[0].type", "responses_input_item_type_not_supported"),
        ([{"type": "function_call_output", "call_id": "call_123", "output": [{"type": "input_image", "image_url": "secret"}]}], "input[0].output", "responses_function_call_output_invalid"),
        ([{"type": "function_call_output", "output": "secret"}], "input[0].call_id", "responses_function_call_output_invalid"),
        ([{"type": "function_call_output", "call_id": "call_123", "output": "secret", "extra": "x"}], "input[0].extra", "responses_function_call_output_invalid"),
        ([{"type": "custom_tool_call", "call_id": "call_123", "input": "secret"}], "input[0].type", "responses_input_tool_item_not_supported"),
        ([{"type": "custom_tool_call_output", "call_id": "call_123", "output": [{"type": "input_text", "text": "secret"}]}], "input[0].output", "responses_custom_tool_call_output_invalid"),
        ([{"type": "custom_tool_call_output", "output": "secret"}], "input[0].call_id", "responses_custom_tool_call_output_invalid"),
        ([{"type": "custom_tool_call_output", "call_id": "call_123", "output": "secret", "id": "item_123"}], "input[0].id", "responses_custom_tool_call_output_invalid"),
        ([{"role": "user", "content": [{"type": "input_file", "file_id": "secret"}]}], "input[0].content[0].file_id", "responses_input_file_id_not_supported"),
        ([{"role": "user", "content": [{"type": "input_audio", "data": "secret"}]}], "input[0].content[0].type", "responses_input_multimodal_not_supported"),
        ([{"role": "user", "content": [{"type": "input_text", "text": "secret", "extra": "x"}]}], "input[0].content[0].extra", "responses_input_content_part_not_supported"),
        ([{"role": "user", "content": [{"type": "output_text", "text": "secret"}]}], "input[0].content[0].type", "responses_input_content_part_not_supported"),
    ],
)
def test_list_input_rejects_unsupported_shapes_without_raw_text(
    input_value: object,
    param: str,
    code: str,
) -> None:
    with pytest.raises(RequestPolicyError) as exc_info:
        ResponsesRequestPolicy(Settings()).apply(_body(input=input_value))

    assert exc_info.value.error_code == code
    assert exc_info.value.param == param
    assert "secret" not in exc_info.value.safe_message


def test_list_input_caps_reject_without_raw_text() -> None:
    settings = Settings(
        RESPONSES_MAX_INPUT_ITEMS=1,
        RESPONSES_MAX_INPUT_ITEM_TEXT_BYTES=4,
        RESPONSES_MAX_TOTAL_INPUT_TEXT_BYTES=8,
        RESPONSES_MAX_TEXT_CONTENT_PARTS_PER_ITEM=1,
    )

    with pytest.raises(RequestPolicyError) as count_exc:
        ResponsesRequestPolicy(settings).apply(
            _body(input=[{"role": "user", "content": "one"}, {"role": "user", "content": "two"}])
        )
    with pytest.raises(RequestPolicyError) as item_exc:
        ResponsesRequestPolicy(settings).apply(
            _body(input=[{"role": "user", "content": "secret text"}])
        )
    with pytest.raises(RequestPolicyError) as total_exc:
        ResponsesRequestPolicy(
            Settings(RESPONSES_MAX_TOTAL_INPUT_TEXT_BYTES=4)
        ).apply(
            _body(
                input=[
                    {"role": "user", "content": "abc"},
                    {"role": "user", "content": "def"},
                ]
            )
        )
    with pytest.raises(RequestPolicyError) as parts_exc:
        ResponsesRequestPolicy(settings).apply(
            _body(
                input=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": "a"},
                            {"type": "input_text", "text": "b"},
                        ],
                    }
                ]
            )
        )

    assert count_exc.value.error_code == "responses_input_item_count_exceeded"
    assert item_exc.value.error_code == "responses_input_item_too_large"
    assert "secret text" not in item_exc.value.safe_message
    assert total_exc.value.error_code == "responses_input_item_too_large"
    assert parts_exc.value.error_code == "responses_input_item_count_exceeded"


@pytest.mark.parametrize(
    ("part", "param", "code"),
    [
        (
            {"type": "input_image", "image_url": "https://example.test/image.png", "detail": "medium"},
            "input[0].content[0].detail",
            "responses_input_image_detail_invalid",
        ),
        (
            {"type": "input_image", "image_url": "https://example.test/image.png", "detail": 3},
            "input[0].content[0].detail",
            "responses_input_image_detail_invalid",
        ),
        (
            {"type": "input_image", "image_url": "ftp://example.test/image.png"},
            "input[0].content[0].image_url",
            "responses_input_image_url_invalid",
        ),
        (
            {"type": "input_image", "image_url": "https://user:pass@example.test/image.png"},
            "input[0].content[0].image_url",
            "responses_input_image_url_invalid",
        ),
        (
            {"type": "input_image", "image_url": "https://example.test/image.png#secret"},
            "input[0].content[0].image_url",
            "responses_input_image_url_invalid",
        ),
        (
            {"type": "input_image", "image_url": "data:image/png,not-base64"},
            "input[0].content[0].image_url",
            "responses_input_image_url_invalid",
        ),
        (
            {"type": "input_image", "image_url": "data:image/png;base64,not valid base64"},
            "input[0].content[0].image_url",
            "responses_input_image_url_invalid",
        ),
        (
            {"type": "input_image", "image_url": "data:image/tiff;base64,aGVsbG8="},
            "input[0].content[0].image_url",
            "responses_input_image_mime_not_supported",
        ),
        (
            {"type": "input_image", "file_id": "file_secret"},
            "input[0].content[0].file_id",
            "responses_input_image_file_id_not_supported",
        ),
        (
            {"type": "input_image", "image_url": "https://example.test/image.png", "alt": "secret"},
            "input[0].content[0].alt",
            "responses_input_image_part_invalid",
        ),
    ],
)
def test_image_input_rejects_unsupported_shapes_without_raw_values(
    part: dict[str, object],
    param: str,
    code: str,
) -> None:
    with pytest.raises(RequestPolicyError) as exc_info:
        ResponsesRequestPolicy(Settings()).apply(
            _body(input=[{"role": "user", "content": [part]}])
        )

    assert exc_info.value.param == param
    assert exc_info.value.error_code == code
    assert "secret" not in exc_info.value.safe_message
    assert "example.test" not in exc_info.value.safe_message


def test_image_input_rejects_non_user_role_without_raw_url() -> None:
    raw_url = "https://example.test/private.png?token=secret"

    with pytest.raises(RequestPolicyError) as exc_info:
        ResponsesRequestPolicy(Settings()).apply(
            _body(input=[{"role": "assistant", "content": [{"type": "input_image", "image_url": raw_url}]}])
        )

    assert exc_info.value.error_code == "responses_input_image_part_invalid"
    assert exc_info.value.param == "input[0].content[0].type"
    assert raw_url not in exc_info.value.safe_message


def test_image_input_caps_reject_without_raw_values() -> None:
    raw_url = "https://example.test/" + ("a" * 64)
    raw_data_url = "data:image/png;base64," + ("a" * 64)

    with pytest.raises(RequestPolicyError) as url_exc:
        ResponsesRequestPolicy(Settings(RESPONSES_MAX_IMAGE_URL_BYTES=16)).apply(
            _body(input=[{"role": "user", "content": [{"type": "input_image", "image_url": raw_url}]}])
        )
    with pytest.raises(RequestPolicyError) as data_exc:
        ResponsesRequestPolicy(Settings(RESPONSES_MAX_IMAGE_DATA_URL_BYTES=16)).apply(
            _body(input=[{"role": "user", "content": [{"type": "input_image", "image_url": raw_data_url}]}])
        )
    with pytest.raises(RequestPolicyError) as total_exc:
        ResponsesRequestPolicy(Settings(RESPONSES_MAX_TOTAL_IMAGE_DATA_URL_BYTES=32)).apply(
            _body(
                input=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "input_image", "image_url": raw_data_url},
                            {"type": "input_image", "image_url": raw_data_url},
                        ],
                    }
                ]
            )
        )
    with pytest.raises(RequestPolicyError) as count_exc:
        ResponsesRequestPolicy(Settings(RESPONSES_MAX_IMAGE_PARTS_PER_REQUEST=1)).apply(
            _body(
                input=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "input_image", "image_url": "https://example.test/1.png"},
                            {"type": "input_image", "image_url": "https://example.test/2.png"},
                        ],
                    }
                ]
            )
        )

    assert url_exc.value.error_code == "responses_input_image_url_too_large"
    assert data_exc.value.error_code == "responses_input_image_data_url_too_large"
    assert total_exc.value.error_code == "responses_input_image_data_url_too_large"
    assert count_exc.value.error_code == "responses_input_image_count_exceeded"
    assert raw_url not in url_exc.value.safe_message
    assert raw_data_url not in data_exc.value.safe_message


def test_image_input_material_contributes_to_admission_estimate() -> None:
    text_only = ResponsesRequestPolicy(Settings()).apply(
        _body(input=[{"role": "user", "content": [{"type": "input_text", "text": "describe"}]}])
    )
    with_image = ResponsesRequestPolicy(Settings()).apply(
        _body(
            input=[
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": "describe"},
                        {
                            "type": "input_image",
                            "image_url": "data:image/png;base64," + ("QUFB" * 8),
                        },
                    ],
                }
            ]
        )
    )

    assert with_image.estimated_input_tokens > text_only.estimated_input_tokens


@pytest.mark.parametrize(
    ("part", "param", "code"),
    [
        (
            {"type": "input_file", "file_url": "http://example.test/document.pdf"},
            "input[0].content[0].file_url",
            "responses_input_file_url_invalid",
        ),
        (
            {"type": "input_file", "file_url": "https://user:pass@example.test/document.pdf"},
            "input[0].content[0].file_url",
            "responses_input_file_url_invalid",
        ),
        (
            {"type": "input_file", "file_url": "https://example.test/document.pdf#secret"},
            "input[0].content[0].file_url",
            "responses_input_file_url_invalid",
        ),
        (
            {"type": "input_file", "file_url": "https://example.test/document.docx"},
            "input[0].content[0].file_url",
            "responses_input_file_extension_not_supported",
        ),
        (
            {
                "type": "input_file",
                "filename": "document.pdf",
                "file_data": "data:application/pdf,not-base64",
            },
            "input[0].content[0].file_data",
            "responses_input_file_data_invalid",
        ),
        (
            {
                "type": "input_file",
                "filename": "document.pdf",
                "file_data": "data:application/pdf;base64,not valid base64",
            },
            "input[0].content[0].file_data",
            "responses_input_file_data_invalid",
        ),
        (
            {
                "type": "input_file",
                "filename": "document.pdf",
                "file_data": "data:application/msword;base64,aGVsbG8=",
            },
            "input[0].content[0].file_data",
            "responses_input_file_mime_not_supported",
        ),
        (
            {
                "type": "input_file",
                "filename": "../document.pdf",
                "file_data": "data:application/pdf;base64,aGVsbG8=",
            },
            "input[0].content[0].filename",
            "responses_input_file_name_invalid",
        ),
        (
            {
                "type": "input_file",
                "filename": "secret-token.pdf",
                "file_data": "data:application/pdf;base64,aGVsbG8=",
            },
            "input[0].content[0].filename",
            "responses_input_file_name_invalid",
        ),
        (
            {
                "type": "input_file",
                "filename": "document.exe",
                "file_data": "data:application/pdf;base64,aGVsbG8=",
            },
            "input[0].content[0].filename",
            "responses_input_file_extension_not_supported",
        ),
        (
            {"type": "input_file", "filename": "document.pdf"},
            "input[0].content[0]",
            "responses_input_file_source_invalid",
        ),
        (
            {
                "type": "input_file",
                "file_url": "https://example.test/document.pdf",
                "filename": "document.pdf",
                "file_data": "data:application/pdf;base64,aGVsbG8=",
            },
            "input[0].content[0]",
            "responses_input_file_source_invalid",
        ),
        (
            {
                "type": "input_file",
                "filename": "document.pdf",
                "file_data": "data:application/pdf;base64,aGVsbG8=",
                "extra": "secret",
            },
            "input[0].content[0].extra",
            "responses_input_file_part_invalid",
        ),
    ],
)
def test_file_input_rejects_unsupported_shapes_without_raw_values(
    part: dict[str, object],
    param: str,
    code: str,
) -> None:
    with pytest.raises(RequestPolicyError) as exc_info:
        ResponsesRequestPolicy(Settings()).apply(
            _body(input=[{"role": "user", "content": [part]}])
        )

    assert exc_info.value.error_code == code
    assert exc_info.value.param == param
    assert "secret" not in exc_info.value.safe_message
    assert "example.test" not in exc_info.value.safe_message


def test_file_input_rejects_non_user_role_without_raw_url() -> None:
    raw_url = "https://example.test/secret.pdf"

    with pytest.raises(RequestPolicyError) as exc_info:
        ResponsesRequestPolicy(Settings()).apply(
            _body(input=[{"role": "assistant", "content": [{"type": "input_file", "file_url": raw_url}]}])
        )

    assert exc_info.value.error_code == "responses_input_file_part_invalid"
    assert exc_info.value.param == "input[0].content[0].type"
    assert raw_url not in exc_info.value.safe_message


def test_file_input_caps_reject_without_raw_values() -> None:
    raw_url = "https://example.test/secret-document.pdf"
    raw_data_url = "data:application/pdf;base64,c2VjcmV0"

    with pytest.raises(RequestPolicyError) as url_exc:
        ResponsesRequestPolicy(Settings(RESPONSES_MAX_FILE_URL_BYTES=16)).apply(
            _body(input=[{"role": "user", "content": [{"type": "input_file", "file_url": raw_url}]}])
        )
    with pytest.raises(RequestPolicyError) as data_exc:
        ResponsesRequestPolicy(Settings(RESPONSES_MAX_FILE_DATA_URL_BYTES=16)).apply(
            _body(
                input=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "input_file",
                                "filename": "document.pdf",
                                "file_data": raw_data_url,
                            }
                        ],
                    }
                ]
            )
        )
    with pytest.raises(RequestPolicyError) as total_exc:
        ResponsesRequestPolicy(Settings(RESPONSES_MAX_TOTAL_FILE_DATA_URL_BYTES=32)).apply(
            _body(
                input=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "input_file",
                                "filename": "one.pdf",
                                "file_data": raw_data_url,
                            },
                            {
                                "type": "input_file",
                                "filename": "two.pdf",
                                "file_data": raw_data_url,
                            },
                        ],
                    }
                ]
            )
        )
    with pytest.raises(RequestPolicyError) as count_exc:
        ResponsesRequestPolicy(Settings(RESPONSES_MAX_FILE_PARTS_PER_REQUEST=1)).apply(
            _body(
                input=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "input_file", "file_url": "https://example.test/1.pdf"},
                            {"type": "input_file", "file_url": "https://example.test/2.pdf"},
                        ],
                    }
                ]
            )
        )
    with pytest.raises(RequestPolicyError) as name_exc:
        ResponsesRequestPolicy(Settings(RESPONSES_MAX_FILE_NAME_BYTES=4)).apply(
            _body(
                input=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "input_file",
                                "filename": "document.pdf",
                                "file_data": raw_data_url,
                            }
                        ],
                    }
                ]
            )
        )

    assert url_exc.value.error_code == "responses_input_file_url_too_large"
    assert data_exc.value.error_code == "responses_input_file_data_url_too_large"
    assert total_exc.value.error_code == "responses_input_file_data_url_too_large"
    assert count_exc.value.error_code == "responses_input_file_count_exceeded"
    assert name_exc.value.error_code == "responses_input_file_name_invalid"
    assert raw_url not in url_exc.value.safe_message
    assert raw_data_url not in data_exc.value.safe_message


def test_file_input_material_contributes_to_admission_estimate() -> None:
    text_only = ResponsesRequestPolicy(Settings()).apply(
        _body(input=[{"role": "user", "content": [{"type": "input_text", "text": "summarize"}]}])
    )
    with_file = ResponsesRequestPolicy(Settings()).apply(
        _body(
            input=[
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": "summarize"},
                        {
                            "type": "input_file",
                            "filename": "document.pdf",
                            "file_data": "data:application/pdf;base64," + ("QUFB" * 8),
                        },
                    ],
                }
            ]
        )
    )

    assert with_file.estimated_input_tokens > text_only.estimated_input_tokens


def test_function_call_output_cap_rejects_without_raw_output() -> None:
    with pytest.raises(RequestPolicyError) as exc_info:
        ResponsesRequestPolicy(Settings(RESPONSES_MAX_FUNCTION_CALL_OUTPUT_BYTES=4)).apply(
            _body(
                input=[
                    {
                        "type": "function_call_output",
                        "call_id": "call_123",
                        "output": "secret output",
                    }
                ]
            )
        )

    assert exc_info.value.error_code == "responses_function_call_output_too_large"
    assert "secret output" not in exc_info.value.safe_message


def test_custom_tool_call_output_cap_rejects_without_raw_output() -> None:
    with pytest.raises(RequestPolicyError) as exc_info:
        ResponsesRequestPolicy(Settings(RESPONSES_MAX_CUSTOM_TOOL_CALL_OUTPUT_BYTES=4)).apply(
            _body(
                input=[
                    {
                        "type": "custom_tool_call_output",
                        "call_id": "call_123",
                        "output": "secret output",
                    }
                ]
            )
        )

    assert exc_info.value.error_code == "responses_custom_tool_call_output_too_large"
    assert "secret output" not in exc_info.value.safe_message


def test_oversized_input_and_instructions_reject_without_raw_text() -> None:
    settings = Settings(RESPONSES_MAX_INPUT_TEXT_BYTES=4, RESPONSES_MAX_INSTRUCTIONS_BYTES=4)
    with pytest.raises(RequestPolicyError) as input_exc:
        ResponsesRequestPolicy(settings).apply(_body(input="secret prompt text"))
    with pytest.raises(RequestPolicyError) as instructions_exc:
        ResponsesRequestPolicy(settings).apply(_body(instructions="secret instructions"))

    assert input_exc.value.error_code == "responses_field_too_large"
    assert "secret" not in input_exc.value.safe_message
    assert instructions_exc.value.error_code == "responses_field_too_large"
    assert "secret" not in instructions_exc.value.safe_message


@pytest.mark.parametrize(
    "field",
    ["temperature", "top_p"],
)
def test_scalar_controls_reject_invalid_types(field: str) -> None:
    with pytest.raises(RequestPolicyError) as exc_info:
        ResponsesRequestPolicy(Settings()).apply(_body(**{field: True}))

    assert exc_info.value.error_code == "responses_field_invalid_type"
    assert exc_info.value.param == field


@pytest.mark.parametrize("value", ["true", 1, {}, []])
def test_stream_rejects_non_bool_values(value: object) -> None:
    with pytest.raises(RequestPolicyError) as exc_info:
        ResponsesRequestPolicy(Settings()).apply(_body(stream=value))

    assert exc_info.value.error_code == "responses_field_invalid_type"
    assert exc_info.value.param == "stream"


def test_metadata_must_be_bounded_object_without_leaking_values() -> None:
    settings = Settings(RESPONSES_MAX_METADATA_BYTES=10)

    with pytest.raises(RequestPolicyError) as exc_info:
        ResponsesRequestPolicy(settings).apply(_body(metadata={"token": "sk-secret"}))

    assert exc_info.value.error_code == "responses_field_too_large"
    assert "sk-secret" not in exc_info.value.safe_message


def test_json_object_text_format_passes() -> None:
    result = ResponsesRequestPolicy(Settings()).apply(
        _body(text={"format": {"type": "json_object"}})
    )

    assert result.effective_body["text"] == {"format": {"type": "json_object"}}
    assert result.estimated_input_tokens > 0


def test_json_schema_text_format_passes() -> None:
    schema = {
        "type": "object",
        "properties": {"answer": {"type": "string"}},
        "required": ["answer"],
        "additionalProperties": False,
    }

    result = ResponsesRequestPolicy(Settings()).apply(
        _body(
            text={
                "format": {
                    "type": "json_schema",
                    "name": "answer_schema",
                    "description": "A compact answer object.",
                    "schema": schema,
                    "strict": True,
                }
            }
        )
    )

    assert result.effective_body["text"]["format"]["schema"] == schema
    assert result.estimated_input_tokens > 0


@pytest.mark.parametrize(
    ("text", "param", "code"),
    [
        (
            {"format": {"type": "json_schema", "schema": {"secret": "value"}}},
            "text.format.name",
            "responses_text_format_invalid",
        ),
        (
            {"format": {"type": "json_schema", "name": "bad name", "schema": {}}},
            "text.format.name",
            "responses_text_format_invalid",
        ),
        (
            {"format": {"type": "json_schema", "name": "answer", "schema": []}},
            "text.format.schema",
            "responses_json_schema_invalid",
        ),
        (
            {
                "format": {
                    "type": "json_schema",
                    "name": "answer",
                    "schema": {},
                    "strict": "true",
                }
            },
            "text.format.strict",
            "responses_field_invalid_type",
        ),
        (
            {"format": {"type": "xml"}},
            "text.format",
            "responses_text_format_not_supported",
        ),
        (
            {"format": {"type": "json_object", "schema": {"secret": "value"}}},
            "text.format.schema",
            "responses_field_not_supported",
        ),
    ],
)
def test_text_format_validation_rejects_invalid_shapes_without_schema_leakage(
    text: dict[str, object],
    param: str,
    code: str,
) -> None:
    with pytest.raises(RequestPolicyError) as exc_info:
        ResponsesRequestPolicy(Settings()).apply(_body(text=text))

    assert exc_info.value.error_code == code
    assert exc_info.value.param == param
    assert "secret" not in exc_info.value.safe_message


def test_text_format_size_caps_reject_without_raw_schema() -> None:
    settings = Settings(
        RESPONSES_MAX_TEXT_FORMAT_BYTES=64,
        RESPONSES_MAX_JSON_SCHEMA_BYTES=32,
        RESPONSES_MAX_TEXT_FORMAT_NAME_BYTES=4,
        RESPONSES_MAX_TEXT_FORMAT_DESCRIPTION_BYTES=4,
    )
    schema = {"type": "object", "description": "secret schema marker"}

    with pytest.raises(RequestPolicyError) as schema_exc:
        ResponsesRequestPolicy(settings).apply(
            _body(
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "ok",
                        "schema": schema,
                    }
                }
            )
        )
    with pytest.raises(RequestPolicyError) as name_exc:
        ResponsesRequestPolicy(settings).apply(
            _body(
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "too_long",
                        "schema": {},
                    }
                }
            )
        )
    with pytest.raises(RequestPolicyError) as description_exc:
        ResponsesRequestPolicy(settings).apply(
            _body(
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "ok",
                        "description": "secret description",
                        "schema": {},
                    }
                }
            )
        )

    assert schema_exc.value.error_code == "responses_json_schema_too_large"
    assert "secret schema marker" not in schema_exc.value.safe_message
    assert name_exc.value.error_code == "responses_text_format_too_large"
    assert description_exc.value.error_code == "responses_text_format_too_large"
    assert "secret description" not in description_exc.value.safe_message


def test_streaming_structured_text_format_rejected_before_forwarding() -> None:
    with pytest.raises(RequestPolicyError) as exc_info:
        ResponsesRequestPolicy(Settings()).apply(
            _body(stream=True, text={"format": {"type": "json_object"}})
        )

    assert exc_info.value.error_code == "responses_structured_streaming_not_supported"
    assert exc_info.value.param == "text.format"


def test_function_tool_request_passes_and_canonicalizes_tool_choice() -> None:
    schema = {
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
        "additionalProperties": False,
    }

    result = ResponsesRequestPolicy(Settings()).apply(
        _body(
            tools=[
                {
                    "type": "function",
                    "name": "lookup",
                    "description": "Perform a local lookup.",
                    "parameters": schema,
                    "strict": True,
                }
            ],
            tool_choice={"type": "function", "name": "lookup"},
        )
    )

    assert result.effective_body["tools"] == [
        {
            "type": "function",
            "name": "lookup",
            "parameters": schema,
            "description": "Perform a local lookup.",
            "strict": True,
        }
    ]
    assert result.effective_body["tool_choice"] == {"type": "function", "name": "lookup"}
    assert result.estimated_input_tokens > 0


@pytest.mark.parametrize("tool_choice", ["auto", "none", "required"])
def test_function_tool_choice_string_options_pass(tool_choice: str) -> None:
    result = ResponsesRequestPolicy(Settings()).apply(
        _body(
            tools=[
                {
                    "type": "function",
                    "name": "lookup",
                    "parameters": {"type": "object", "properties": {}},
                }
            ],
            tool_choice=tool_choice,
        )
    )

    assert result.effective_body["tool_choice"] == tool_choice


@pytest.mark.parametrize(
    ("tools", "param", "code"),
    [
        ([], "tools", "responses_tool_invalid_shape"),
        ([{"type": "web_search"}], "tools[0].type", "responses_hosted_tool_not_supported"),
        ([{"type": "mcp", "server_url": "https://example.invalid"}], "tools[0].type", "responses_mcp_not_supported"),
        ([{"type": "function", "name": "bad name", "parameters": {}}], "tools[0].name", "responses_tool_invalid_shape"),
        ([{"type": "function", "name": "lookup", "parameters": []}], "tools[0].parameters", "responses_tool_invalid_shape"),
        ([{"type": "function", "name": "lookup", "parameters": {}, "server_url": "https://example.invalid"}], "tools[0]", "responses_mcp_not_supported"),
        ([{"type": "function", "name": "lookup", "parameters": {}, "strict": "true"}], "tools[0].strict", "responses_tool_invalid_shape"),
    ],
)
def test_function_tool_validation_rejects_invalid_shapes_without_schema_leakage(
    tools: list[dict[str, object]],
    param: str,
    code: str,
) -> None:
    with pytest.raises(RequestPolicyError) as exc_info:
        ResponsesRequestPolicy(Settings()).apply(_body(tools=tools))

    assert exc_info.value.error_code == code
    assert exc_info.value.param == param
    assert "https://example.invalid" not in exc_info.value.safe_message


def test_function_tool_caps_reject_without_schema_leakage() -> None:
    schema = {"type": "object", "description": "secret schema marker"}

    with pytest.raises(RequestPolicyError) as schema_exc:
        ResponsesRequestPolicy(Settings(RESPONSES_MAX_SINGLE_FUNCTION_TOOL_SCHEMA_BYTES=16)).apply(
            _body(tools=[{"type": "function", "name": "lookup", "parameters": schema}])
        )
    with pytest.raises(RequestPolicyError) as name_exc:
        ResponsesRequestPolicy(Settings(RESPONSES_MAX_FUNCTION_TOOL_NAME_BYTES=4)).apply(
            _body(tools=[{"type": "function", "name": "lookup", "parameters": {}}])
        )
    with pytest.raises(RequestPolicyError) as description_exc:
        ResponsesRequestPolicy(Settings(RESPONSES_MAX_FUNCTION_TOOL_DESCRIPTION_BYTES=4)).apply(
            _body(
                tools=[
                    {
                        "type": "function",
                        "name": "find",
                        "description": "secret description",
                        "parameters": {},
                    }
                ]
            )
        )

    assert schema_exc.value.error_code == "responses_function_tool_schema_too_large"
    assert "secret schema marker" not in schema_exc.value.safe_message
    assert name_exc.value.error_code == "responses_tool_invalid_shape"
    assert description_exc.value.error_code == "responses_tool_invalid_shape"
    assert "secret description" not in description_exc.value.safe_message


def test_custom_tools_pass_with_omitted_text_and_grammar_formats() -> None:
    result = ResponsesRequestPolicy(Settings()).apply(
        _body(
            tools=[
                {"type": "custom", "name": "freeform", "description": "Local custom intent."},
                {"type": "custom", "name": "texty", "format": {"type": "text"}},
                {
                    "type": "custom",
                    "name": "emit_lark",
                    "format": {
                        "type": "grammar",
                        "syntax": "lark",
                        "definition": "start: WORD",
                    },
                },
                {
                    "type": "custom",
                    "name": "emit_regex",
                    "format": {
                        "type": "grammar",
                        "syntax": "regex",
                        "definition": "[a-z]+",
                    },
                },
            ],
            tool_choice={"type": "custom", "name": "emit_regex"},
        )
    )

    assert result.effective_body["tools"] == [
        {"type": "custom", "name": "freeform", "description": "Local custom intent."},
        {"type": "custom", "name": "texty", "format": {"type": "text"}},
        {
            "type": "custom",
            "name": "emit_lark",
            "format": {"type": "grammar", "syntax": "lark", "definition": "start: WORD"},
        },
        {
            "type": "custom",
            "name": "emit_regex",
            "format": {"type": "grammar", "syntax": "regex", "definition": "[a-z]+"},
        },
    ]
    assert result.effective_body["tool_choice"] == {"type": "custom", "name": "emit_regex"}
    assert result.estimated_input_tokens > 0


@pytest.mark.parametrize(
    ("tool", "param", "code"),
    [
        ({"type": "custom", "name": "bad name"}, "tools[0].name", "responses_tool_invalid_shape"),
        ({"type": "custom", "name": "run", "defer_loading": True}, "tools[0].defer_loading", "responses_tool_invalid_shape"),
        ({"type": "custom", "name": "run", "server_url": "https://example.invalid"}, "tools[0]", "responses_mcp_not_supported"),
        ({"type": "custom", "name": "run", "description": 1}, "tools[0].description", "responses_tool_invalid_shape"),
        ({"type": "custom", "name": "run", "format": "text"}, "tools[0].format", "responses_tool_invalid_shape"),
        ({"type": "custom", "name": "run", "format": {"type": "json"}}, "tools[0].format.type", "responses_custom_tool_format_not_supported"),
        ({"type": "custom", "name": "run", "format": {"type": "text", "extra": "x"}}, "tools[0].format.extra", "responses_tool_invalid_shape"),
        ({"type": "custom", "name": "run", "format": {"type": "grammar", "syntax": "json", "definition": "secret"}}, "tools[0].format.syntax", "responses_custom_tool_format_not_supported"),
        ({"type": "custom", "name": "run", "format": {"type": "grammar", "syntax": "regex"}}, "tools[0].format.definition", "responses_tool_invalid_shape"),
        ({"type": "custom", "name": "run", "format": {"type": "grammar", "syntax": "regex", "definition": ""}}, "tools[0].format.definition", "responses_tool_invalid_shape"),
        ({"type": "custom", "name": "run", "format": {"type": "grammar", "syntax": "regex", "definition": "secret", "extra": "x"}}, "tools[0].format.extra", "responses_tool_invalid_shape"),
    ],
)
def test_custom_tool_validation_rejects_invalid_shapes_without_payload_leakage(
    tool: dict[str, object],
    param: str,
    code: str,
) -> None:
    with pytest.raises(RequestPolicyError) as exc_info:
        ResponsesRequestPolicy(Settings()).apply(_body(tools=[tool]))

    assert exc_info.value.error_code == code
    assert exc_info.value.param == param
    assert "secret" not in exc_info.value.safe_message
    assert "https://example.invalid" not in exc_info.value.safe_message


def test_custom_tool_caps_reject_without_definition_leakage() -> None:
    with pytest.raises(RequestPolicyError) as name_exc:
        ResponsesRequestPolicy(Settings(RESPONSES_MAX_CUSTOM_TOOL_NAME_BYTES=4)).apply(
            _body(tools=[{"type": "custom", "name": "lookup"}])
        )
    with pytest.raises(RequestPolicyError) as description_exc:
        ResponsesRequestPolicy(Settings(RESPONSES_MAX_CUSTOM_TOOL_DESCRIPTION_BYTES=4)).apply(
            _body(tools=[{"type": "custom", "name": "run", "description": "secret description"}])
        )
    with pytest.raises(RequestPolicyError) as definition_exc:
        ResponsesRequestPolicy(
            Settings(RESPONSES_MAX_CUSTOM_TOOL_FORMAT_DEFINITION_BYTES=4)
        ).apply(
            _body(
                tools=[
                    {
                        "type": "custom",
                        "name": "run",
                        "format": {
                            "type": "grammar",
                            "syntax": "regex",
                            "definition": "secret grammar",
                        },
                    }
                ]
            )
        )
    with pytest.raises(RequestPolicyError) as count_exc:
        ResponsesRequestPolicy(Settings(RESPONSES_MAX_CUSTOM_TOOLS_PER_REQUEST=1)).apply(
            _body(
                tools=[
                    {"type": "custom", "name": "one"},
                    {"type": "custom", "name": "two"},
                ]
            )
        )
    with pytest.raises(RequestPolicyError) as total_exc:
        ResponsesRequestPolicy(Settings(RESPONSES_MAX_TOTAL_CUSTOM_TOOL_FORMAT_BYTES=64)).apply(
            _body(
                tools=[
                    {
                        "type": "custom",
                        "name": "one",
                        "format": {
                            "type": "grammar",
                            "syntax": "regex",
                            "definition": "secret grammar one",
                        },
                    },
                    {
                        "type": "custom",
                        "name": "two",
                        "format": {
                            "type": "grammar",
                            "syntax": "regex",
                            "definition": "secret grammar two",
                        },
                    },
                ]
            )
        )

    assert name_exc.value.error_code == "responses_tool_invalid_shape"
    assert description_exc.value.error_code == "responses_tool_invalid_shape"
    assert "secret description" not in description_exc.value.safe_message
    assert definition_exc.value.error_code == "responses_custom_tool_format_too_large"
    assert "secret grammar" not in definition_exc.value.safe_message
    assert count_exc.value.error_code == "responses_tool_count_exceeded"
    assert total_exc.value.error_code == "responses_custom_tool_format_too_large"
    assert "secret grammar" not in total_exc.value.safe_message


def test_duplicate_tool_names_across_function_and_custom_reject() -> None:
    with pytest.raises(RequestPolicyError) as exc_info:
        ResponsesRequestPolicy(Settings()).apply(
            _body(
                tools=[
                    {"type": "function", "name": "lookup", "parameters": {}},
                    {"type": "custom", "name": "lookup"},
                ]
            )
        )

    assert exc_info.value.error_code == "responses_tool_invalid_shape"
    assert exc_info.value.param == "tools[1].name"


@pytest.mark.parametrize(
    ("tool_choice", "param", "code"),
    [
        ("sometimes", "tool_choice", "responses_tool_choice_invalid"),
        ({"type": "function", "name": "missing"}, "tool_choice.name", "responses_tool_choice_invalid"),
        ({"type": "custom", "name": "missing"}, "tool_choice.name", "responses_tool_choice_invalid"),
        ({"type": "web_search"}, "tool_choice.type", "responses_hosted_tool_not_supported"),
        ({"type": "mcp", "server_label": "x"}, "tool_choice.type", "responses_mcp_not_supported"),
        ({"type": "function", "function": {"name": "lookup"}}, "tool_choice.function", "responses_tool_choice_invalid"),
    ],
)
def test_function_tool_choice_rejects_invalid_shapes(
    tool_choice: object,
    param: str,
    code: str,
) -> None:
    with pytest.raises(RequestPolicyError) as exc_info:
        ResponsesRequestPolicy(Settings()).apply(
            _body(
                tools=[
                    {
                        "type": "function",
                        "name": "lookup",
                        "parameters": {"type": "object", "properties": {}},
                    }
                ],
                tool_choice=tool_choice,
            )
        )

    assert exc_info.value.error_code == code
    assert exc_info.value.param == param


def test_tool_choice_without_tools_rejects() -> None:
    with pytest.raises(RequestPolicyError) as exc_info:
        ResponsesRequestPolicy(Settings()).apply(_body(tool_choice="none"))

    assert exc_info.value.error_code == "responses_tool_choice_invalid"
    assert exc_info.value.param == "tool_choice"


def test_streaming_function_tools_rejected_before_forwarding() -> None:
    with pytest.raises(RequestPolicyError) as exc_info:
        ResponsesRequestPolicy(Settings()).apply(
            _body(
                stream=True,
                tools=[
                    {
                        "type": "function",
                        "name": "lookup",
                        "parameters": {"type": "object", "properties": {}},
                    }
                ],
            )
        )

    assert exc_info.value.error_code == "responses_function_tool_streaming_not_supported"
    assert exc_info.value.param == "tools"


def test_streaming_custom_tools_rejected_before_forwarding() -> None:
    with pytest.raises(RequestPolicyError) as exc_info:
        ResponsesRequestPolicy(Settings()).apply(
            _body(
                stream=True,
                tools=[{"type": "custom", "name": "emit_text"}],
            )
        )

    assert exc_info.value.error_code == "responses_custom_tool_streaming_not_supported"
    assert exc_info.value.param == "tools"


def test_streaming_custom_tool_output_rejected_before_forwarding() -> None:
    with pytest.raises(RequestPolicyError) as exc_info:
        ResponsesRequestPolicy(Settings()).apply(
            _body(
                stream=True,
                input=[
                    {"role": "user", "content": "continue"},
                    {
                        "type": "custom_tool_call_output",
                        "call_id": "call_123",
                        "output": "safe custom result",
                    },
                ],
            )
        )

    assert exc_info.value.error_code == "responses_custom_tool_streaming_not_supported"
    assert exc_info.value.param == "tools"


def test_json_output_is_secret_safe_for_policy_result() -> None:
    result = ResponsesRequestPolicy(Settings()).apply(_body(metadata={"safe": "value"}))
    payload = json.dumps(result.model_dump(mode="json"), sort_keys=True)

    assert "sk-" not in payload


def test_conversation_item_create_accepts_text_message_items() -> None:
    result = validate_conversation_items_create_body(
        {
            "items": [
                {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": "hello"}],
                }
            ]
        },
        settings=Settings(),
    )

    assert result == {
        "items": [
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "hello"}],
            }
        ]
    }


@pytest.mark.parametrize(
    "item",
    [
        {"type": "function_call_output", "call_id": "call_1", "output": "result"},
        {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_image", "image_url": "https://example.test/image.png"}],
        },
        {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_file", "file_url": "https://example.test/file.pdf"}],
        },
        {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": "hello", "server_url": "https://mcp.test"}],
        },
    ],
)
def test_conversation_item_create_rejects_tool_media_and_hosted_markers(item: dict[str, object]) -> None:
    with pytest.raises(RequestPolicyError):
        validate_conversation_items_create_body({"items": [item]}, settings=Settings())
