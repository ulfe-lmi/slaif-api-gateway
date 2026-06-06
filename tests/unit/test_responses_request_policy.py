from __future__ import annotations

import json

import pytest

from slaif_gateway.config import Settings
from slaif_gateway.services.policy_errors import RequestPolicyError
from slaif_gateway.services.responses_request_policy import ResponsesRequestPolicy


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


def test_omitted_max_output_tokens_injects_default() -> None:
    result = ResponsesRequestPolicy(Settings(DEFAULT_MAX_OUTPUT_TOKENS=77)).apply(
        {"model": "gpt-test", "input": "hello"}
    )

    assert result.effective_body["max_output_tokens"] == 77
    assert result.injected_default_output_tokens is True


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("tools", [], "responses_tools_not_supported"),
        ("tool_choice", "auto", "responses_tools_not_supported"),
        ("previous_response_id", "resp_123", "responses_state_not_supported"),
        ("conversation", "conv_123", "responses_state_not_supported"),
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


@pytest.mark.parametrize(
    ("input_value", "param", "code"),
    [
        ([], "input", "responses_input_invalid"),
        ([{"role": "user", "content": ""}], "input[0].content", "responses_input_invalid"),
        ([{"role": "admin", "content": "secret"}], "input[0].role", "responses_input_item_role_not_supported"),
        ([{"role": "user", "content": "secret", "name": "x"}], "input[0].name", "responses_input_item_invalid"),
        ([{"type": "function_call", "role": "user", "content": "secret"}], "input[0].type", "responses_input_tool_item_not_supported"),
        ([{"type": "reasoning", "role": "user", "content": "secret"}], "input[0].type", "responses_input_item_type_not_supported"),
        ([{"role": "user", "content": [{"type": "input_image", "image_url": "secret"}]}], "input[0].content[0].type", "responses_input_multimodal_not_supported"),
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


def test_json_output_is_secret_safe_for_policy_result() -> None:
    result = ResponsesRequestPolicy(Settings()).apply(_body(metadata={"safe": "value"}))
    payload = json.dumps(result.model_dump(mode="json"), sort_keys=True)

    assert "sk-" not in payload
