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


def test_list_input_rejected_for_first_text_only_slice() -> None:
    with pytest.raises(RequestPolicyError) as exc_info:
        ResponsesRequestPolicy(Settings()).apply(
            _body(input=[{"role": "user", "content": "hello"}])
        )

    assert exc_info.value.error_code == "responses_field_invalid_type"
    assert exc_info.value.param == "input"


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


def test_structured_text_format_rejected() -> None:
    with pytest.raises(RequestPolicyError) as exc_info:
        ResponsesRequestPolicy(Settings()).apply(
            _body(text={"format": {"type": "json_schema", "schema": {"secret": "value"}}})
        )

    assert exc_info.value.error_code == "responses_field_not_supported"
    assert "secret" not in exc_info.value.safe_message


def test_json_output_is_secret_safe_for_policy_result() -> None:
    result = ResponsesRequestPolicy(Settings()).apply(_body(metadata={"safe": "value"}))
    payload = json.dumps(result.model_dump(mode="json"), sort_keys=True)

    assert "sk-" not in payload
