from __future__ import annotations

import inspect
import copy

import pytest

from slaif_gateway.config import Settings
from slaif_gateway.schemas.openai import ChatCompletionRequest
from slaif_gateway.services.chat_completion_field_policy import (
    ChatCompletionFieldClassification,
    ChatCompletionFieldPolicyError,
    classify_chat_completion_request_fields,
)
from slaif_gateway.services.hosted_tool_policy import ChatCompletionCapabilityPolicyError
from slaif_gateway.services.policy_errors import (
    AmbiguousOutputTokenLimitError,
    InputTokenLimitExceededError,
    InvalidOutputTokenLimitError,
    OutputTokenLimitExceededError,
    RequestPolicyError,
)
from slaif_gateway.services.request_policy import ChatCompletionRequestPolicy
from slaif_gateway.services.key_modes import CAPABILITY_POLICY_MODE_TRUSTED_CALIBRATION_DISCOVERY


def _settings(**overrides) -> Settings:
    values = {
        "DEFAULT_MAX_OUTPUT_TOKENS": 12,
        "HARD_MAX_OUTPUT_TOKENS": 40,
        "HARD_MAX_INPUT_TOKENS": 60,
    }
    values.update(overrides)
    return Settings(**values)


def test_missing_output_limit_injects_default() -> None:
    policy = ChatCompletionRequestPolicy(_settings())
    body = {"model": "gpt-4.1-mini", "messages": [{"role": "user", "content": "hi"}]}

    result = policy.apply(body)

    assert result.injected_default_output_tokens is True
    assert result.requested_output_tokens == 12
    assert result.effective_output_tokens == 12
    assert result.effective_body["max_completion_tokens"] == 12


def test_max_tokens_is_accepted_when_valid() -> None:
    policy = ChatCompletionRequestPolicy(_settings())

    result = policy.apply(
        {
            "model": "gpt-4.1-mini",
            "messages": [{"role": "user", "content": "hello"}],
            "max_tokens": 21,
        }
    )

    assert result.injected_default_output_tokens is False
    assert result.effective_output_tokens == 21
    assert result.effective_body["max_tokens"] == 21


def test_max_completion_tokens_is_accepted_when_valid() -> None:
    policy = ChatCompletionRequestPolicy(_settings())

    result = policy.apply(
        {
            "model": "gpt-4.1-mini",
            "messages": [{"role": "user", "content": "hello"}],
            "max_completion_tokens": 22,
        }
    )

    assert result.injected_default_output_tokens is False
    assert result.effective_output_tokens == 22
    assert result.effective_body["max_completion_tokens"] == 22


def test_both_output_fields_with_different_values_are_rejected() -> None:
    policy = ChatCompletionRequestPolicy(_settings())

    with pytest.raises(AmbiguousOutputTokenLimitError):
        policy.apply(
            {
                "model": "gpt-4.1-mini",
                "messages": [{"role": "user", "content": "hello"}],
                "max_tokens": 10,
                "max_completion_tokens": 11,
            }
        )


def test_both_output_fields_with_same_value_are_allowed() -> None:
    policy = ChatCompletionRequestPolicy(_settings())

    result = policy.apply(
        {
            "model": "gpt-4.1-mini",
            "messages": [{"role": "user", "content": "hello"}],
            "max_tokens": 12,
            "max_completion_tokens": 12,
        }
    )

    assert result.effective_output_tokens == 12


@pytest.mark.parametrize("value", [0, -1])
def test_non_positive_output_limit_fails(value: int) -> None:
    policy = ChatCompletionRequestPolicy(_settings())

    with pytest.raises(InvalidOutputTokenLimitError):
        policy.apply(
            {
                "model": "gpt-4.1-mini",
                "messages": [{"role": "user", "content": "hello"}],
                "max_tokens": value,
            }
        )


def test_output_limit_above_hard_max_fails() -> None:
    policy = ChatCompletionRequestPolicy(_settings())

    with pytest.raises(OutputTokenLimitExceededError):
        policy.apply(
            {
                "model": "gpt-4.1-mini",
                "messages": [{"role": "user", "content": "hello"}],
                "max_completion_tokens": 41,
            }
        )


@pytest.mark.parametrize("value", ["20", True])
def test_non_integer_or_bool_output_limit_fails(value: object) -> None:
    policy = ChatCompletionRequestPolicy(_settings())

    with pytest.raises(InvalidOutputTokenLimitError):
        policy.apply(
            {
                "model": "gpt-4.1-mini",
                "messages": [{"role": "user", "content": "hello"}],
                "max_tokens": value,
            }
        )


def test_input_messages_over_hard_max_fails() -> None:
    policy = ChatCompletionRequestPolicy(_settings(HARD_MAX_INPUT_TOKENS=20))

    with pytest.raises(InputTokenLimitExceededError):
        policy.apply(
            {
                "model": "gpt-4.1-mini",
                "messages": [{"role": "user", "content": "x" * 200}],
            }
        )


def test_large_tools_schema_over_hard_max_fails_without_raw_payload() -> None:
    policy = ChatCompletionRequestPolicy(_settings(HARD_MAX_INPUT_TOKENS=80))
    raw_marker = "raw tool schema marker"

    with pytest.raises(InputTokenLimitExceededError) as exc_info:
        policy.apply(
            {
                "model": "gpt-4.1-mini",
                "messages": [{"role": "user", "content": "hi"}],
                "tools": [
                    {
                        "type": "function",
                        "function": {
                            "name": "lookup",
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "query": {
                                        "type": "string",
                                        "description": raw_marker + ("x" * 200),
                                    }
                                },
                            },
                        },
                    }
                ],
            }
        )

    assert exc_info.value.param == "request"
    assert "Estimated input size exceeds" in exc_info.value.safe_message
    assert raw_marker not in exc_info.value.safe_message


def test_large_response_format_schema_over_hard_max_fails_without_raw_payload() -> None:
    policy = ChatCompletionRequestPolicy(_settings(HARD_MAX_INPUT_TOKENS=80))
    raw_marker = "raw response schema marker"

    with pytest.raises(InputTokenLimitExceededError) as exc_info:
        policy.apply(
            {
                "model": "gpt-4.1-mini",
                "messages": [{"role": "user", "content": "hi"}],
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "answer",
                        "schema": {
                            "type": "object",
                            "properties": {
                                "answer": {
                                    "type": "string",
                                    "description": raw_marker + ("x" * 200),
                                }
                            },
                        },
                    },
                },
            }
        )

    assert exc_info.value.param == "request"
    assert "Estimated input size exceeds" in exc_info.value.safe_message
    assert raw_marker not in exc_info.value.safe_message


def test_input_estimate_handles_plain_text_messages() -> None:
    policy = ChatCompletionRequestPolicy(_settings(HARD_MAX_INPUT_TOKENS=1000))

    result = policy.apply(
        {
            "model": "gpt-4.1-mini",
            "messages": [
                {"role": "system", "content": "you are helpful"},
                {"role": "user", "content": "write haiku"},
            ],
        }
    )

    assert result.estimated_input_tokens > 0


def test_input_estimate_handles_text_content_blocks() -> None:
    policy = ChatCompletionRequestPolicy(_settings(HARD_MAX_INPUT_TOKENS=1000))

    result = policy.apply(
        {
            "model": "gpt-4.1-mini",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "hello world"},
                    ],
                }
            ],
        }
    )

    assert result.estimated_input_tokens > 0


def _image_message(url: str = "https://example.test/image.png") -> dict[str, object]:
    return {
        "role": "user",
        "content": [
            {"type": "text", "text": "what is in this image?"},
            {"type": "image_url", "image_url": {"url": url}},
        ],
    }


def _file_message(
    file_data: str = "SGVsbG8sIGZpbGU=",
    filename: str = "notes.txt",
) -> dict[str, object]:
    return {
        "role": "user",
        "content": [
            {"type": "text", "text": "summarize this file"},
            {"type": "file", "file": {"filename": filename, "file_data": file_data}},
        ],
    }


def _audio_message(
    audio_data: str = "UklGRiQAAABXQVZFZm10IBAAAAABAAEA",
    audio_format: str = "wav",
) -> dict[str, object]:
    return {
        "role": "user",
        "content": [
            {"type": "text", "text": "transcribe this audio"},
            {"type": "input_audio", "input_audio": {"data": audio_data, "format": audio_format}},
        ],
    }


def test_input_estimate_includes_image_url_material_without_multiplying_input_by_n() -> None:
    policy = ChatCompletionRequestPolicy(_settings(HARD_MAX_INPUT_TOKENS=5000))
    text_only = policy.apply(
        {
            "model": "gpt-4.1-mini",
            "messages": [{"role": "user", "content": "what is in this image?"}],
            "max_completion_tokens": 8,
        }
    )

    image_result = policy.apply(
        {
            "model": "gpt-4.1-mini",
            "messages": [_image_message("https://example.test/image.png")],
            "max_completion_tokens": 8,
            "n": 3,
        }
    )

    assert image_result.estimated_input_tokens > text_only.estimated_input_tokens
    assert image_result.effective_choice_count == 3
    assert image_result.effective_output_tokens == 24


def test_input_estimate_includes_file_data_without_multiplying_input_by_n() -> None:
    policy = ChatCompletionRequestPolicy(_settings(HARD_MAX_INPUT_TOKENS=5000))
    text_only = policy.apply(
        {
            "model": "gpt-4.1-mini",
            "messages": [{"role": "user", "content": "summarize this file"}],
            "max_completion_tokens": 8,
        }
    )

    file_result = policy.apply(
        {
            "model": "gpt-4.1-mini",
            "messages": [_file_message()],
            "max_completion_tokens": 8,
            "n": 3,
        }
    )

    assert file_result.estimated_input_tokens > text_only.estimated_input_tokens
    assert file_result.effective_choice_count == 3
    assert file_result.effective_output_tokens == 24


def test_input_estimate_includes_audio_data_without_multiplying_input_by_n() -> None:
    policy = ChatCompletionRequestPolicy(_settings(HARD_MAX_INPUT_TOKENS=5000))
    text_only = policy.apply(
        {
            "model": "gpt-4.1-mini",
            "messages": [{"role": "user", "content": "transcribe this audio"}],
            "max_completion_tokens": 8,
        }
    )

    audio_result = policy.apply(
        {
            "model": "gpt-4.1-mini",
            "messages": [_audio_message()],
            "max_completion_tokens": 8,
            "n": 3,
        }
    )

    assert audio_result.estimated_input_tokens > text_only.estimated_input_tokens
    assert audio_result.effective_choice_count == 3
    assert audio_result.effective_output_tokens == 24


@pytest.mark.parametrize(
    "part",
    [
        {"type": "input_image", "image_url": "https://example.test/image.png"},
        {"type": "video", "video": {"url": "https://example.test/video.mp4"}},
    ],
)
def test_non_text_message_content_parts_are_rejected(part: dict[str, object]) -> None:
    policy = ChatCompletionRequestPolicy(_settings(HARD_MAX_INPUT_TOKENS=1000))

    with pytest.raises(RequestPolicyError) as exc_info:
        policy.apply(
            {
                "model": "gpt-4.1-mini",
                "messages": [{"role": "user", "content": [{"type": "text", "text": "hi"}, part]}],
            }
        )

    assert exc_info.value.error_code == "unsupported_chat_completion_modality"
    assert exc_info.value.param == "messages[0].content[1].type"


@pytest.mark.parametrize("detail", ["auto", "low", "high"])
def test_image_url_content_part_is_validated_and_preserved(detail: str) -> None:
    policy = ChatCompletionRequestPolicy(_settings(HARD_MAX_INPUT_TOKENS=5000))

    result = policy.apply(
        {
            "model": "gpt-4.1-mini",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "describe"},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": "https://example.test/image.png?token=private",
                                "detail": detail,
                            },
                        },
                    ],
                }
            ],
        }
    )

    image_part = result.effective_body["messages"][0]["content"][1]
    assert image_part["image_url"]["detail"] == detail


def test_image_data_url_content_part_is_validated_and_preserved() -> None:
    policy = ChatCompletionRequestPolicy(_settings(HARD_MAX_INPUT_TOKENS=5000))
    data_url = "data:image/png;base64,aGVsbG8="

    result = policy.apply(
        {
            "model": "gpt-4.1-mini",
            "messages": [_image_message(data_url)],
        }
    )

    assert result.effective_body["messages"][0]["content"][1]["image_url"]["url"] == data_url


def test_file_content_part_with_raw_base64_is_validated_and_preserved() -> None:
    policy = ChatCompletionRequestPolicy(_settings(HARD_MAX_INPUT_TOKENS=5000))

    result = policy.apply(
        {
            "model": "gpt-4.1-mini",
            "messages": [_file_message()],
        }
    )

    file_part = result.effective_body["messages"][0]["content"][1]
    assert file_part == {
        "type": "file",
        "file": {"filename": "notes.txt", "file_data": "SGVsbG8sIGZpbGU="},
    }


def test_file_data_url_can_be_enabled_and_preserved() -> None:
    policy = ChatCompletionRequestPolicy(
        _settings(HARD_MAX_INPUT_TOKENS=5000, CHAT_ALLOW_FILE_DATA_URLS=True)
    )
    data_url = "data:application/pdf;base64,SGVsbG8="

    result = policy.apply(
        {
            "model": "gpt-4.1-mini",
            "messages": [_file_message(data_url, "notes.pdf")],
        }
    )

    assert result.effective_body["messages"][0]["content"][1]["file"]["file_data"] == data_url


@pytest.mark.parametrize("audio_format", ["wav", "mp3"])
def test_audio_input_content_part_is_validated_and_preserved(audio_format: str) -> None:
    policy = ChatCompletionRequestPolicy(_settings(HARD_MAX_INPUT_TOKENS=5000))

    result = policy.apply(
        {
            "model": "gpt-4.1-mini",
            "messages": [_audio_message(audio_format=audio_format)],
        }
    )

    audio_part = result.effective_body["messages"][0]["content"][1]
    assert audio_part == {
        "type": "input_audio",
        "input_audio": {
            "data": "UklGRiQAAABXQVZFZm10IBAAAAABAAEA",
            "format": audio_format,
        },
    }


@pytest.mark.parametrize(
    ("overrides", "expected_code", "expected_param"),
    [
        ({"CHAT_MAX_IMAGES_PER_MESSAGE": 1}, "chat_image_count_exceeded", "messages[0].content"),
        ({"CHAT_MAX_IMAGES_PER_REQUEST": 1}, "chat_image_count_exceeded", "messages"),
    ],
)
def test_image_count_caps_are_enforced(
    overrides: dict[str, int],
    expected_code: str,
    expected_param: str,
) -> None:
    policy = ChatCompletionRequestPolicy(_settings(HARD_MAX_INPUT_TOKENS=5000, **overrides))

    with pytest.raises(RequestPolicyError) as exc_info:
        policy.apply(
            {
                "model": "gpt-4.1-mini",
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "image_url", "image_url": {"url": "https://example.test/1.png"}},
                            {"type": "image_url", "image_url": {"url": "https://example.test/2.png"}},
                        ],
                    }
                ],
            }
        )

    assert exc_info.value.error_code == expected_code
    assert exc_info.value.param == expected_param


@pytest.mark.parametrize(
    ("overrides", "expected_code", "expected_param"),
    [
        ({"CHAT_MAX_FILES_PER_MESSAGE": 1}, "chat_file_count_exceeded", "messages[0].content"),
        ({"CHAT_MAX_FILES_PER_REQUEST": 1}, "chat_file_count_exceeded", "messages"),
    ],
)
def test_file_count_caps_are_enforced(
    overrides: dict[str, int],
    expected_code: str,
    expected_param: str,
) -> None:
    policy = ChatCompletionRequestPolicy(_settings(HARD_MAX_INPUT_TOKENS=5000, **overrides))

    with pytest.raises(RequestPolicyError) as exc_info:
        policy.apply(
            {
                "model": "gpt-4.1-mini",
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "file", "file": {"filename": "one.txt", "file_data": "T25l"}},
                            {"type": "file", "file": {"filename": "two.txt", "file_data": "VHdv"}},
                        ],
                    }
                ],
            }
        )

    assert exc_info.value.error_code == expected_code
    assert exc_info.value.param == expected_param


@pytest.mark.parametrize(
    ("overrides", "expected_code", "expected_param"),
    [
        ({"CHAT_MAX_AUDIO_INPUTS_PER_MESSAGE": 1}, "chat_audio_count_exceeded", "messages[0].content"),
        ({"CHAT_MAX_AUDIO_INPUTS_PER_REQUEST": 1}, "chat_audio_count_exceeded", "messages"),
    ],
)
def test_audio_input_count_caps_are_enforced(
    overrides: dict[str, int],
    expected_code: str,
    expected_param: str,
) -> None:
    policy = ChatCompletionRequestPolicy(_settings(HARD_MAX_INPUT_TOKENS=5000, **overrides))

    with pytest.raises(RequestPolicyError) as exc_info:
        policy.apply(
            {
                "model": "gpt-4.1-mini",
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "input_audio", "input_audio": {"data": "T25l", "format": "wav"}},
                            {"type": "input_audio", "input_audio": {"data": "VHdv", "format": "mp3"}},
                        ],
                    }
                ],
            }
        )

    assert exc_info.value.error_code == expected_code
    assert exc_info.value.param == expected_param


@pytest.mark.parametrize(
    ("image_url", "expected_code"),
    [
        ("ftp://example.test/image.png", "chat_image_url_invalid"),
        ("https://user:pass@example.test/image.png", "chat_image_url_invalid"),
        ("data:text/plain;base64,aGVsbG8=", "chat_image_mime_not_supported"),
        ("data:image/png;base64,not valid base64", "chat_image_url_invalid"),
        ("data:image/png,not-base64", "chat_image_url_invalid"),
    ],
)
def test_invalid_image_url_shapes_are_rejected_without_raw_value(
    image_url: str,
    expected_code: str,
) -> None:
    policy = ChatCompletionRequestPolicy(_settings(HARD_MAX_INPUT_TOKENS=5000))

    with pytest.raises(RequestPolicyError) as exc_info:
        policy.apply({"model": "gpt-4.1-mini", "messages": [_image_message(image_url)]})

    assert exc_info.value.error_code == expected_code
    assert image_url not in exc_info.value.safe_message


def test_image_url_byte_caps_are_enforced_without_raw_value() -> None:
    raw_url = "https://example.test/" + ("x" * 200)
    policy = ChatCompletionRequestPolicy(
        _settings(HARD_MAX_INPUT_TOKENS=5000, CHAT_MAX_IMAGE_URL_BYTES=32)
    )

    with pytest.raises(RequestPolicyError) as exc_info:
        policy.apply({"model": "gpt-4.1-mini", "messages": [_image_message(raw_url)]})

    assert exc_info.value.error_code == "chat_image_url_too_large"
    assert raw_url not in exc_info.value.safe_message


def test_image_data_url_byte_cap_and_policy_are_enforced_without_raw_value() -> None:
    raw_data_url = "data:image/png;base64," + ("a" * 64)
    policy = ChatCompletionRequestPolicy(
        _settings(HARD_MAX_INPUT_TOKENS=5000, CHAT_MAX_IMAGE_DATA_URL_BYTES=32)
    )

    with pytest.raises(RequestPolicyError) as too_large:
        policy.apply({"model": "gpt-4.1-mini", "messages": [_image_message(raw_data_url)]})

    assert too_large.value.error_code == "chat_image_data_url_too_large"
    assert raw_data_url not in too_large.value.safe_message

    disabled_policy = ChatCompletionRequestPolicy(
        _settings(HARD_MAX_INPUT_TOKENS=5000, CHAT_ALLOW_IMAGE_DATA_URLS=False)
    )
    with pytest.raises(RequestPolicyError) as disabled:
        disabled_policy.apply({"model": "gpt-4.1-mini", "messages": [_image_message(raw_data_url)]})

    assert disabled.value.error_code == "chat_image_data_url_not_allowed"
    assert raw_data_url not in disabled.value.safe_message


def test_remote_image_urls_can_be_disabled() -> None:
    policy = ChatCompletionRequestPolicy(
        _settings(HARD_MAX_INPUT_TOKENS=5000, CHAT_ALLOW_REMOTE_IMAGE_URLS=False)
    )

    with pytest.raises(RequestPolicyError) as exc_info:
        policy.apply({"model": "gpt-4.1-mini", "messages": [_image_message()]})

    assert exc_info.value.error_code == "chat_image_url_invalid"


@pytest.mark.parametrize(
    ("file_data", "filename", "expected_code"),
    [
        ("not valid base64", "notes.txt", "chat_file_data_invalid"),
        ("https://example.test/private.pdf?token=secret", "notes.pdf", "chat_file_url_not_supported"),
        ("data:application/x-msdownload;base64,SGVsbG8=", "notes.pdf", "chat_file_mime_not_supported"),
        ("SGVsbG8=", "archive.zip", "chat_file_mime_not_supported"),
    ],
)
def test_invalid_file_data_shapes_are_rejected_without_raw_values(
    file_data: str,
    filename: str,
    expected_code: str,
) -> None:
    policy = ChatCompletionRequestPolicy(
        _settings(HARD_MAX_INPUT_TOKENS=5000, CHAT_ALLOW_FILE_DATA_URLS=True)
    )

    with pytest.raises(RequestPolicyError) as exc_info:
        policy.apply({"model": "gpt-4.1-mini", "messages": [_file_message(file_data, filename)]})

    assert exc_info.value.error_code == expected_code
    assert file_data not in exc_info.value.safe_message
    assert filename not in exc_info.value.safe_message


def test_file_data_url_is_disabled_by_default_without_raw_value() -> None:
    file_data = "data:application/pdf;base64,SGVsbG8="
    policy = ChatCompletionRequestPolicy(_settings(HARD_MAX_INPUT_TOKENS=5000))

    with pytest.raises(RequestPolicyError) as exc_info:
        policy.apply({"model": "gpt-4.1-mini", "messages": [_file_message(file_data, "notes.pdf")]})

    assert exc_info.value.error_code == "chat_file_data_url_not_allowed"
    assert file_data not in exc_info.value.safe_message


def test_file_byte_caps_are_enforced_without_raw_values() -> None:
    raw_file_data = "a" * 64
    policy = ChatCompletionRequestPolicy(
        _settings(HARD_MAX_INPUT_TOKENS=5000, CHAT_MAX_FILE_DATA_BYTES=32)
    )

    with pytest.raises(RequestPolicyError) as too_large:
        policy.apply({"model": "gpt-4.1-mini", "messages": [_file_message(raw_file_data)]})

    assert too_large.value.error_code == "chat_file_data_too_large"
    assert raw_file_data not in too_large.value.safe_message

    raw_filename = ("x" * 260) + ".txt"
    with pytest.raises(RequestPolicyError) as name_too_large:
        policy.apply(
            {
                "model": "gpt-4.1-mini",
                "messages": [_file_message("SGVsbG8=", raw_filename)],
            }
        )

    assert name_too_large.value.error_code == "chat_file_name_too_large"
    assert raw_filename not in name_too_large.value.safe_message


@pytest.mark.parametrize(
    ("audio_data", "audio_format", "expected_code"),
    [
        ("not valid base64", "wav", "chat_audio_data_invalid"),
        ("https://example.test/private.wav?token=secret", "wav", "chat_audio_url_not_supported"),
        ("data:audio/wav;base64,UklG", "wav", "chat_audio_data_url_not_allowed"),
        ("UklGRiQAAABXQVZFZm10IBAAAAABAAEA", "flac", "chat_audio_format_not_supported"),
    ],
)
def test_invalid_audio_input_shapes_are_rejected_without_raw_values(
    audio_data: str,
    audio_format: str,
    expected_code: str,
) -> None:
    policy = ChatCompletionRequestPolicy(_settings(HARD_MAX_INPUT_TOKENS=5000))

    with pytest.raises(RequestPolicyError) as exc_info:
        policy.apply(
            {
                "model": "gpt-4.1-mini",
                "messages": [_audio_message(audio_data, audio_format)],
            }
        )

    assert exc_info.value.error_code == expected_code
    assert audio_data not in exc_info.value.safe_message


def test_audio_input_byte_cap_is_enforced_without_raw_value() -> None:
    raw_audio_data = "a" * 64
    policy = ChatCompletionRequestPolicy(
        _settings(HARD_MAX_INPUT_TOKENS=5000, CHAT_MAX_AUDIO_INPUT_DATA_BYTES=32)
    )

    with pytest.raises(RequestPolicyError) as exc_info:
        policy.apply({"model": "gpt-4.1-mini", "messages": [_audio_message(raw_audio_data)]})

    assert exc_info.value.error_code == "chat_audio_data_too_large"
    assert raw_audio_data not in exc_info.value.safe_message


@pytest.mark.parametrize(
    ("message", "expected_code", "expected_param"),
    [
        (
            {"role": "system", "content": [{"type": "image_url", "image_url": {"url": "https://example.test/img.png"}}]},
            "chat_image_part_invalid_shape",
            "messages[0].content[0].type",
        ),
        (
            {"role": "user", "content": [{"type": "image_url", "image_url": "https://example.test/img.png"}]},
            "chat_image_part_invalid_shape",
            "messages[0].content[0].image_url",
        ),
        (
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": "https://example.test/img.png", "detail": "original"},
                    }
                ],
            },
            "chat_image_detail_invalid",
            "messages[0].content[0].image_url.detail",
        ),
        (
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": "https://example.test/img.png"},
                        "provider_extra": True,
                    }
                ],
            },
            "chat_image_part_invalid_shape",
            "messages[0].content[0].provider_extra",
        ),
    ],
)
def test_invalid_image_part_shapes_are_rejected(
    message: dict[str, object],
    expected_code: str,
    expected_param: str,
) -> None:
    policy = ChatCompletionRequestPolicy(_settings(HARD_MAX_INPUT_TOKENS=5000))

    with pytest.raises(RequestPolicyError) as exc_info:
        policy.apply({"model": "gpt-4.1-mini", "messages": [message]})

    assert exc_info.value.error_code == expected_code
    assert exc_info.value.param == expected_param


@pytest.mark.parametrize(
    ("message", "expected_code", "expected_param", "raw_marker"),
    [
        (
            {"role": "system", "content": [{"type": "file", "file": {"filename": "notes.txt", "file_data": "SGVsbG8="}}]},
            "chat_file_part_invalid_shape",
            "messages[0].content[0].type",
            "notes.txt",
        ),
        (
            {"role": "user", "content": [{"type": "file", "file": "SGVsbG8="}]},
            "chat_file_part_invalid_shape",
            "messages[0].content[0].file",
            "SGVsbG8=",
        ),
        (
            {"role": "user", "content": [{"type": "file", "file": {"file_id": "file-secret"}}]},
            "chat_file_id_not_supported",
            "messages[0].content[0].file.file_id",
            "file-secret",
        ),
        (
            {"role": "user", "content": [{"type": "file", "file": {"file_id": None}}]},
            "chat_file_id_not_supported",
            "messages[0].content[0].file.file_id",
            "file_id",
        ),
        (
            {
                "role": "user",
                "content": [
                    {
                        "type": "file",
                        "file": {
                            "filename": "notes.txt",
                            "file_data": "SGVsbG8=",
                            "file_id": "file-secret",
                        },
                    }
                ],
            },
            "chat_file_part_invalid_shape",
            "messages[0].content[0].file",
            "file-secret",
        ),
        (
            {"role": "user", "content": [{"type": "file", "file": {"filename": "../secret.txt", "file_data": "SGVsbG8="}}]},
            "chat_file_name_invalid",
            "messages[0].content[0].file.filename",
            "../secret.txt",
        ),
        (
            {"role": "user", "content": [{"type": "file", "file": {"filename": "notes.txt", "file_data": "SGVsbG8=", "url": "https://example.test/private.pdf"}}]},
            "chat_file_url_not_supported",
            "messages[0].content[0].file.url",
            "https://example.test/private.pdf",
        ),
        (
            {"role": "user", "content": [{"type": "file", "file": {"filename": "notes.txt", "file_data": "SGVsbG8="}, "provider_extra": True}]},
            "chat_file_part_invalid_shape",
            "messages[0].content[0].provider_extra",
            "notes.txt",
        ),
    ],
)
def test_invalid_file_part_shapes_are_rejected_without_raw_values(
    message: dict[str, object],
    expected_code: str,
    expected_param: str,
    raw_marker: str,
) -> None:
    policy = ChatCompletionRequestPolicy(_settings(HARD_MAX_INPUT_TOKENS=5000))

    with pytest.raises(RequestPolicyError) as exc_info:
        policy.apply({"model": "gpt-4.1-mini", "messages": [message]})

    assert exc_info.value.error_code == expected_code
    assert exc_info.value.param == expected_param
    assert raw_marker not in exc_info.value.safe_message


@pytest.mark.parametrize(
    ("message", "expected_code", "expected_param", "raw_marker"),
    [
        (
            {
                "role": "system",
                "content": [
                    {
                        "type": "input_audio",
                        "input_audio": {"data": "UklGRiQ=", "format": "wav"},
                    }
                ],
            },
            "chat_audio_part_invalid_shape",
            "messages[0].content[0].type",
            "UklGRiQ=",
        ),
        (
            {"role": "user", "content": [{"type": "input_audio", "input_audio": "UklGRiQ="}]},
            "chat_audio_part_invalid_shape",
            "messages[0].content[0].input_audio",
            "UklGRiQ=",
        ),
        (
            {"role": "user", "content": [{"type": "input_audio", "input_audio": {"format": "wav"}}]},
            "chat_audio_data_invalid",
            "messages[0].content[0].input_audio.data",
            "secret-audio-marker",
        ),
        (
            {"role": "user", "content": [{"type": "input_audio", "input_audio": {"data": "UklGRiQ="}}]},
            "chat_audio_format_invalid",
            "messages[0].content[0].input_audio.format",
            "UklGRiQ=",
        ),
        (
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_audio",
                        "input_audio": {"data": "UklGRiQ=", "format": "wav", "url": "https://example.test/audio.wav"},
                    }
                ],
            },
            "chat_audio_part_invalid_shape",
            "messages[0].content[0].input_audio.url",
            "https://example.test/audio.wav",
        ),
        (
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_audio",
                        "input_audio": {"data": "UklGRiQ=", "format": "wav"},
                        "provider_extra": True,
                    }
                ],
            },
            "chat_audio_part_invalid_shape",
            "messages[0].content[0].provider_extra",
            "UklGRiQ=",
        ),
    ],
)
def test_invalid_audio_input_part_shapes_are_rejected_without_raw_values(
    message: dict[str, object],
    expected_code: str,
    expected_param: str,
    raw_marker: str,
) -> None:
    policy = ChatCompletionRequestPolicy(_settings(HARD_MAX_INPUT_TOKENS=5000))

    with pytest.raises(RequestPolicyError) as exc_info:
        policy.apply({"model": "gpt-4.1-mini", "messages": [message]})

    assert exc_info.value.error_code == expected_code
    assert exc_info.value.param == expected_param
    assert raw_marker not in exc_info.value.safe_message


def test_service_does_not_mutate_original_request() -> None:
    policy = ChatCompletionRequestPolicy(_settings())
    original = {
        "model": "gpt-4.1-mini",
        "messages": [{"role": "user", "content": "hi"}],
    }

    _ = policy.apply(original)

    assert "max_completion_tokens" not in original


def test_unknown_extra_field_is_rejected_without_mutating_original() -> None:
    policy = ChatCompletionRequestPolicy(_settings(HARD_MAX_INPUT_TOKENS=1000))
    original = {
        "model": "gpt-4.1-mini",
        "messages": [{"role": "user", "content": "hi"}],
        "x_bad": {"not_json": object()},
    }
    body = copy.deepcopy(original)

    with pytest.raises(RequestPolicyError) as exc_info:
        policy.apply(body)

    assert exc_info.value.error_code == "unknown_chat_completion_field"
    assert exc_info.value.param == "x_bad"
    assert body.keys() == original.keys()
    assert body["model"] == original["model"]
    assert body["messages"] == original["messages"]


def test_known_supported_fields_are_preserved_and_classified() -> None:
    policy = ChatCompletionRequestPolicy(_settings(HARD_MAX_INPUT_TOKENS=5000))
    request = {
        "model": "gpt-4.1-mini",
        "messages": [{"role": "user", "content": "hi"}],
        "temperature": 0.2,
        "top_p": 0.9,
        "tools": [{"type": "function", "function": {"name": "lookup"}}],
        "tool_choice": "auto",
        "response_format": {"type": "json_object"},
        "seed": 123,
        "stream_options": {"include_usage": True},
        "user": "student-1",
        "logprobs": True,
        "top_logprobs": 2,
        "presence_penalty": 0.1,
        "frequency_penalty": 0.2,
        "n": 1,
        "reasoning_effort": "low",
        "modalities": ["text"],
        "parallel_tool_calls": True,
        "metadata": {"course": "week-1"},
        "store": False,
        "prediction": {"type": "content", "content": "hello"},
        "service_tier": "auto",
    }

    classifications = classify_chat_completion_request_fields(request)
    result = policy.apply(request)

    assert result.effective_body["temperature"] == 0.2
    assert result.effective_body["top_p"] == 0.9
    assert result.effective_body["tools"][0]["function"]["name"] == "lookup"
    assert result.effective_body["tool_choice"] == "auto"
    assert result.effective_body["response_format"] == {"type": "json_object"}
    assert result.effective_body["seed"] == 123
    assert result.effective_body["stream_options"] == {"include_usage": True}
    assert result.effective_body["user"] == "student-1"
    assert result.effective_body["logprobs"] is True
    assert result.effective_body["top_logprobs"] == 2
    assert result.effective_body["presence_penalty"] == 0.1
    assert result.effective_body["frequency_penalty"] == 0.2
    assert result.effective_body["n"] == 1
    assert result.effective_body["reasoning_effort"] == "low"
    assert result.effective_body["modalities"] == ["text"]
    assert result.effective_body["parallel_tool_calls"] is True
    assert result.effective_body["metadata"]["course"] == "week-1"
    assert result.effective_body["store"] is False
    assert result.effective_body["prediction"]["content"] == "hello"
    assert result.effective_body["service_tier"] == "auto"
    assert classifications["messages"] == ChatCompletionFieldClassification.FORWARDED_SUPPORTED
    assert classifications["stream_options"] == ChatCompletionFieldClassification.GATEWAY_MUTATED
    assert classifications["tools"] == ChatCompletionFieldClassification.LOCAL_TOOL_FEATURE
    assert result.estimated_non_message_input_tokens > 0
    assert set(result.estimated_non_message_input_fields) >= {
        "metadata",
        "modalities",
        "prediction",
        "response_format",
        "tools",
    }


@pytest.mark.parametrize(
    ("field", "value", "expected_code"),
    [
        ("temperature", -0.1, "chat_field_value_out_of_range"),
        ("temperature", True, "chat_field_invalid_type"),
        ("top_p", 1.1, "chat_field_value_out_of_range"),
        ("presence_penalty", -2.1, "chat_field_value_out_of_range"),
        ("frequency_penalty", 2.1, "chat_field_value_out_of_range"),
        ("stream", "true", "chat_field_invalid_type"),
        ("logprobs", "true", "chat_field_invalid_type"),
        ("parallel_tool_calls", 1, "chat_field_invalid_type"),
        ("seed", 1.5, "chat_field_invalid_type"),
        ("reasoning_effort", "extreme", "chat_field_value_out_of_range"),
    ],
)
def test_scalar_field_validation_rejects_invalid_values(
    field: str,
    value: object,
    expected_code: str,
) -> None:
    policy = ChatCompletionRequestPolicy(_settings(HARD_MAX_INPUT_TOKENS=5000))

    with pytest.raises(RequestPolicyError) as exc_info:
        policy.apply(
            {
                "model": "gpt-4.1-mini",
                "messages": [{"role": "user", "content": "hi"}],
                field: value,
            }
        )

    assert exc_info.value.error_code == expected_code
    assert exc_info.value.param == field


@pytest.mark.parametrize("value", [-101, 101, True, "1"])
def test_logit_bias_values_are_validated_without_echoing_values(value: object) -> None:
    policy = ChatCompletionRequestPolicy(_settings(HARD_MAX_INPUT_TOKENS=5000))

    with pytest.raises(RequestPolicyError) as exc_info:
        policy.apply(
            {
                "model": "gpt-4.1-mini",
                "messages": [{"role": "user", "content": "hi"}],
                "logit_bias": {"123": value},
            }
        )

    assert exc_info.value.param == "logit_bias"
    assert "123" not in exc_info.value.safe_message


def test_top_logprobs_requires_logprobs_true() -> None:
    policy = ChatCompletionRequestPolicy(_settings(HARD_MAX_INPUT_TOKENS=5000))

    with pytest.raises(RequestPolicyError) as exc_info:
        policy.apply(
            {
                "model": "gpt-4.1-mini",
                "messages": [{"role": "user", "content": "hi"}],
                "top_logprobs": 2,
            }
        )

    assert exc_info.value.error_code == "chat_field_value_out_of_range"
    assert exc_info.value.param == "top_logprobs"


def test_message_count_and_content_caps_are_enforced_without_echoing_content() -> None:
    policy = ChatCompletionRequestPolicy(
        _settings(
            HARD_MAX_INPUT_TOKENS=5000,
            CHAT_MAX_MESSAGES_PER_REQUEST=1,
            CHAT_MAX_MESSAGE_CONTENT_BYTES=8,
        )
    )
    raw_content = "raw prompt marker"

    with pytest.raises(RequestPolicyError) as exc_info:
        policy.apply(
            {
                "model": "gpt-4.1-mini",
                "messages": [{"role": "user", "content": raw_content}],
            }
        )

    assert exc_info.value.error_code == "chat_field_too_large"
    assert raw_content not in exc_info.value.safe_message

    with pytest.raises(RequestPolicyError) as count_exc:
        policy.apply(
            {
                "model": "gpt-4.1-mini",
                "messages": [
                    {"role": "user", "content": "hi"},
                    {"role": "assistant", "content": "ok"},
                ],
            }
        )

    assert count_exc.value.error_code == "chat_message_limit_exceeded"


def test_text_content_part_count_is_capped() -> None:
    policy = ChatCompletionRequestPolicy(
        _settings(
            HARD_MAX_INPUT_TOKENS=5000,
            CHAT_MAX_TEXT_PARTS_PER_MESSAGE=1,
        )
    )

    with pytest.raises(RequestPolicyError) as exc_info:
        policy.apply(
            {
                "model": "gpt-4.1-mini",
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "one"},
                            {"type": "text", "text": "two"},
                        ],
                    }
                ],
            }
        )

    assert exc_info.value.error_code == "chat_field_too_many_items"


def test_tool_count_and_schema_caps_are_enforced_without_echoing_schema() -> None:
    policy = ChatCompletionRequestPolicy(
        _settings(
            HARD_MAX_INPUT_TOKENS=5000,
            CHAT_MAX_TOOLS_PER_REQUEST=1,
            CHAT_MAX_SINGLE_TOOL_SCHEMA_BYTES=40,
        )
    )
    raw_schema_marker = "raw schema marker"

    with pytest.raises(RequestPolicyError) as schema_exc:
        policy.apply(
            {
                "model": "gpt-4.1-mini",
                "messages": [{"role": "user", "content": "hi"}],
                "tools": [
                    {
                        "type": "function",
                        "function": {
                            "name": "lookup",
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "query": {"description": raw_schema_marker * 4}
                                },
                            },
                        },
                    }
                ],
            }
        )

    assert schema_exc.value.error_code == "chat_tool_schema_too_large"
    assert raw_schema_marker not in schema_exc.value.safe_message

    with pytest.raises(RequestPolicyError) as count_exc:
        policy.apply(
            {
                "model": "gpt-4.1-mini",
                "messages": [{"role": "user", "content": "hi"}],
                "tools": [
                    {"type": "function", "function": {"name": "one"}},
                    {"type": "function", "function": {"name": "two"}},
                ],
            }
        )

    assert count_exc.value.error_code == "chat_tool_count_exceeded"


def test_function_tool_name_and_description_caps_are_enforced() -> None:
    policy = ChatCompletionRequestPolicy(
        _settings(
            HARD_MAX_INPUT_TOKENS=5000,
            CHAT_MAX_TOOL_NAME_BYTES=4,
            CHAT_MAX_TOOL_DESCRIPTION_BYTES=8,
        )
    )

    with pytest.raises(RequestPolicyError) as name_exc:
        policy.apply(
            {
                "model": "gpt-4.1-mini",
                "messages": [{"role": "user", "content": "hi"}],
                "tools": [{"type": "function", "function": {"name": "tool_name"}}],
            }
        )

    assert name_exc.value.param == "tools[0].function.name"
    assert name_exc.value.error_code == "chat_field_too_large"


def test_legacy_functions_receive_equivalent_caps() -> None:
    policy = ChatCompletionRequestPolicy(
        _settings(
            HARD_MAX_INPUT_TOKENS=5000,
            CHAT_MAX_FUNCTIONS_PER_REQUEST=1,
        )
    )

    with pytest.raises(RequestPolicyError) as exc_info:
        policy.apply(
            {
                "model": "gpt-4.1-mini",
                "messages": [{"role": "user", "content": "hi"}],
                "functions": [{"name": "one"}, {"name": "two"}],
            }
        )

    assert exc_info.value.error_code == "chat_tool_count_exceeded"


def test_response_format_metadata_prediction_stop_user_and_stream_options_caps() -> None:
    raw_marker = "raw metadata marker"
    cases = [
        (
            {"response_format": {"type": "json_schema", "json_schema": {"schema": {"x": raw_marker * 20}}}},
            "chat_response_format_schema_too_large",
            "response_format.json_schema",
            {"CHAT_MAX_RESPONSE_FORMAT_SCHEMA_BYTES": 40},
        ),
        (
            {"metadata": {"safe": raw_marker * 20}},
            "chat_metadata_too_large",
            "metadata",
            {"CHAT_MAX_METADATA_BYTES": 40},
        ),
        (
            {"prediction": {"type": "content", "content": raw_marker * 20}},
            "chat_field_too_large",
            "prediction",
            {"CHAT_MAX_PREDICTION_BYTES": 40},
        ),
        (
            {"stop": ["a", "b"]},
            "chat_stop_sequence_limit_exceeded",
            "stop",
            {"CHAT_MAX_STOP_SEQUENCES": 1},
        ),
        (
            {"user": raw_marker},
            "chat_field_too_large",
            "user",
            {"CHAT_MAX_USER_FIELD_BYTES": 4},
        ),
        (
            {"stream_options": {"raw": raw_marker * 20}},
            "chat_field_too_large",
            "stream_options",
            {"CHAT_MAX_STREAM_OPTIONS_BYTES": 40},
        ),
    ]

    for overrides, expected_code, expected_param, settings_overrides in cases:
        policy = ChatCompletionRequestPolicy(
            _settings(HARD_MAX_INPUT_TOKENS=5000, **settings_overrides)
        )
        with pytest.raises(RequestPolicyError) as exc_info:
            policy.apply(
                {
                    "model": "gpt-4.1-mini",
                    "messages": [{"role": "user", "content": "hi"}],
                    **overrides,
                }
            )

        assert exc_info.value.error_code == expected_code
        assert exc_info.value.param == expected_param
        assert raw_marker not in exc_info.value.safe_message


def test_metadata_key_caps_and_string_key_policy() -> None:
    policy = ChatCompletionRequestPolicy(
        _settings(
            HARD_MAX_INPUT_TOKENS=5000,
            CHAT_MAX_METADATA_KEYS=1,
            CHAT_MAX_METADATA_KEY_BYTES=4,
        )
    )

    with pytest.raises(RequestPolicyError) as count_exc:
        policy.apply(
            {
                "model": "gpt-4.1-mini",
                "messages": [{"role": "user", "content": "hi"}],
                "metadata": {"one": "1", "two": "2"},
            }
        )

    assert count_exc.value.error_code == "chat_field_too_many_items"

    with pytest.raises(RequestPolicyError) as key_exc:
        policy.apply(
            {
                "model": "gpt-4.1-mini",
                "messages": [{"role": "user", "content": "hi"}],
                "metadata": {"long_key": "1"},
            }
        )

    assert key_exc.value.error_code == "chat_field_too_large"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("x_future_object", {"feature": "raw future value"}),
        ("x_future_list", [{"feature": "raw future value"}]),
        ("x_future_scalar", True),
    ],
)
def test_unknown_top_level_fields_are_rejected(field: str, value: object) -> None:
    policy = ChatCompletionRequestPolicy(_settings(HARD_MAX_INPUT_TOKENS=5000))

    with pytest.raises(RequestPolicyError) as exc_info:
        policy.apply(
            {
                "model": "gpt-4.1-mini",
                "messages": [{"role": "user", "content": "hi"}],
                field: value,
            }
        )

    assert exc_info.value.error_code == "unknown_chat_completion_field"
    assert exc_info.value.param == field
    assert "raw future value" not in exc_info.value.safe_message


def test_local_function_tool_with_scary_name_is_allowed() -> None:
    policy = ChatCompletionRequestPolicy(_settings(HARD_MAX_INPUT_TOKENS=5000))

    result = policy.apply(
        {
            "model": "gpt-4.1-mini",
            "messages": [{"role": "user", "content": "hi"}],
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "delete_file",
                        "parameters": {
                            "type": "object",
                            "properties": {"path": {"type": "string"}},
                        },
                    },
                }
            ],
            "tool_choice": {"type": "function", "function": {"name": "delete_file"}},
        }
    )

    assert result.effective_body["tools"][0]["function"]["name"] == "delete_file"
    assert result.effective_body["tool_choice"]["function"]["name"] == "delete_file"


def test_function_tool_schema_with_provider_marker_property_names_is_allowed() -> None:
    policy = ChatCompletionRequestPolicy(_settings(HARD_MAX_INPUT_TOKENS=5000))

    result = policy.apply(
        {
            "model": "gpt-4.1-mini",
            "messages": [{"role": "user", "content": "hi"}],
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "inspect_record",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "authorization": {"type": "string"},
                                "server_url": {"type": "string"},
                                "connector_id": {"type": "string"},
                            },
                        },
                    },
                }
            ],
        }
    )

    assert result.effective_body["tools"][0]["function"]["parameters"]["properties"][
        "authorization"
    ] == {"type": "string"}


@pytest.mark.parametrize(
    ("request_overrides", "expected_code", "expected_param"),
    [
        ({"tools": [{"type": "web_search"}]}, "web_search_not_allowed", "tools[0].type"),
        (
            {"tools": [{"type": "web_search_preview"}]},
            "web_search_not_allowed",
            "tools[0].type",
        ),
        ({"web_search_options": {"search_context_size": "low"}}, "web_search_not_allowed", "web_search_options"),
        ({"model": "gpt-5-search-api"}, "search_model_requires_hosted_web_search", "model"),
        ({"tools": [{"type": "file_search"}]}, "hosted_tool_not_allowed", "tools[0].type"),
        ({"tools": [{"type": "code_interpreter"}]}, "hosted_tool_not_allowed", "tools[0].type"),
        ({"tools": [{"type": "computer"}]}, "hosted_tool_not_allowed", "tools[0].type"),
        ({"tools": [{"type": "computer_use"}]}, "hosted_tool_not_allowed", "tools[0].type"),
        ({"tools": [{"type": "image_generation"}]}, "hosted_tool_not_allowed", "tools[0].type"),
        ({"tools": [{"type": "tool_search"}]}, "hosted_tool_not_allowed", "tools[0].type"),
        ({"tools": [{"type": "mcp"}]}, "mcp_connectors_not_allowed", "tools[0].type"),
        ({"tools": [{"type": "custom_tool"}]}, "unknown_tool_type_not_allowed", "tools[0].type"),
        ({"background": True}, "background_not_allowed", "background"),
        ({"store": True}, "background_not_allowed", "store"),
        ({"previous_response_id": "resp_123"}, "background_not_allowed", "previous_response_id"),
        ({"conversation": "conv_123"}, "background_not_allowed", "conversation"),
        ({"external_web_access": True}, "web_search_not_allowed", "external_web_access"),
        ({"defer_loading": True}, "hosted_tool_not_allowed", "defer_loading"),
        (
            {"tool_choice": {"type": "web_search"}},
            "web_search_not_allowed",
            "tool_choice.type",
        ),
    ],
)
def test_hosted_tool_capability_surfaces_are_rejected(
    request_overrides: dict[str, object],
    expected_code: str,
    expected_param: str,
) -> None:
    policy = ChatCompletionRequestPolicy(_settings(HARD_MAX_INPUT_TOKENS=5000))
    request = {
        "model": "gpt-4.1-mini",
        "messages": [{"role": "user", "content": "hi"}],
        **request_overrides,
    }

    with pytest.raises(RequestPolicyError) as exc_info:
        policy.apply(request)

    assert exc_info.value.error_code == expected_code
    assert exc_info.value.param == expected_param
    assert "sk-" not in exc_info.value.safe_message
    assert "Authorization" not in exc_info.value.safe_message


def test_custom_tool_request_is_accepted_as_local_intent_and_counted_in_input_estimate() -> None:
    policy = ChatCompletionRequestPolicy(_settings(HARD_MAX_INPUT_TOKENS=5000))
    base_request = {
        "model": "gpt-4.1-mini",
        "messages": [{"role": "user", "content": "hi"}],
    }
    custom_tool = {
        "type": "custom",
        "custom": {
            "name": "run_shell",
            "description": "Local tool description",
            "format": {
                "type": "grammar",
                "grammar": {"syntax": "regex", "definition": "[a-z]+"},
            },
        },
    }

    without_tool = policy.apply(base_request)
    with_tool = policy.apply(
        {
            **base_request,
            "tools": [custom_tool],
            "tool_choice": {"type": "custom", "custom": {"name": "run_shell"}},
        }
    )

    assert with_tool.effective_body["tools"][0] == custom_tool
    assert with_tool.effective_body["tool_choice"]["custom"]["name"] == "run_shell"
    assert "tools" in with_tool.estimated_non_message_input_fields
    assert with_tool.estimated_input_tokens > without_tool.estimated_input_tokens


def test_custom_tool_names_are_not_semantically_policed() -> None:
    policy = ChatCompletionRequestPolicy(_settings(HARD_MAX_INPUT_TOKENS=5000))

    result = policy.apply(
        {
            "model": "gpt-4.1-mini",
            "messages": [{"role": "user", "content": "hi"}],
            "tools": [{"type": "custom", "custom": {"name": "delete_file"}}],
        }
    )

    assert result.effective_body["tools"][0]["custom"]["name"] == "delete_file"


@pytest.mark.parametrize(
    ("settings_overrides", "request_overrides", "expected_code", "expected_param"),
    [
        (
            {"CHAT_MAX_CUSTOM_TOOLS_PER_REQUEST": 1},
            {
                "tools": [
                    {"type": "custom", "custom": {"name": "one"}},
                    {"type": "custom", "custom": {"name": "two"}},
                ]
            },
            "chat_custom_tool_count_exceeded",
            "tools",
        ),
        (
            {"CHAT_MAX_CUSTOM_TOOL_NAME_BYTES": 4},
            {"tools": [{"type": "custom", "custom": {"name": "too_long"}}]},
            "chat_custom_tool_too_large",
            "tools[0].custom.name",
        ),
        (
            {"CHAT_MAX_CUSTOM_TOOL_DESCRIPTION_BYTES": 4},
            {"tools": [{"type": "custom", "custom": {"name": "ok", "description": "too long"}}]},
            "chat_custom_tool_too_large",
            "tools[0].custom.description",
        ),
        (
            {"CHAT_MAX_CUSTOM_TOOL_FORMAT_BYTES": 16},
            {
                "tools": [
                    {
                        "type": "custom",
                        "custom": {
                            "name": "ok",
                            "format": {
                                "type": "grammar",
                                "grammar": {"syntax": "regex", "definition": "x+"},
                            },
                        },
                    }
                ]
            },
            "chat_custom_tool_too_large",
            "tools[0].custom.format",
        ),
        (
            {"CHAT_MAX_CUSTOM_TOOL_GRAMMAR_BYTES": 4},
            {
                "tools": [
                    {
                        "type": "custom",
                        "custom": {
                            "name": "ok",
                            "format": {
                                "type": "grammar",
                                "grammar": {"syntax": "regex", "definition": "x" * 5},
                            },
                        },
                    }
                ]
            },
            "chat_custom_tool_grammar_too_large",
            "tools[0].custom.format.grammar.definition",
        ),
    ],
)
def test_custom_tool_caps_are_enforced(
    settings_overrides: dict[str, object],
    request_overrides: dict[str, object],
    expected_code: str,
    expected_param: str,
) -> None:
    policy = ChatCompletionRequestPolicy(
        _settings(HARD_MAX_INPUT_TOKENS=5000, **settings_overrides)
    )

    with pytest.raises(RequestPolicyError) as exc_info:
        policy.apply(
            {
                "model": "gpt-4.1-mini",
                "messages": [{"role": "user", "content": "hi"}],
                **request_overrides,
            }
        )

    assert exc_info.value.error_code == expected_code
    assert exc_info.value.param == expected_param


@pytest.mark.parametrize(
    ("request_overrides", "expected_code", "expected_param"),
    [
        (
            {"tools": [{"type": "custom"}]},
            "chat_custom_tool_invalid_shape",
            "tools[0].custom",
        ),
        (
            {"tools": [{"type": "custom", "custom": {"name": ""}}]},
            "chat_custom_tool_invalid_type",
            "tools[0].custom.name",
        ),
        (
            {"tools": [{"type": "custom", "custom": {"name": "ok", "extra": True}}]},
            "chat_custom_tool_invalid_shape",
            "tools[0].custom.extra",
        ),
        (
            {"tools": [{"type": "custom", "custom": {"name": "ok", "format": {"type": "xml"}}}]},
            "chat_custom_tool_format_not_supported",
            "tools[0].custom.format.type",
        ),
        (
            {
                "tools": [
                    {
                        "type": "custom",
                        "custom": {
                            "name": "ok",
                            "format": {
                                "type": "grammar",
                                "grammar": {"syntax": "python", "definition": "x"},
                            },
                        },
                    }
                ]
            },
            "chat_custom_tool_format_not_supported",
            "tools[0].custom.format.grammar.syntax",
        ),
        (
            {
                "tools": [{"type": "custom", "custom": {"name": "ok"}}],
                "tool_choice": {"type": "custom", "custom": {"name": "missing"}},
            },
            "chat_custom_tool_choice_invalid",
            "tool_choice.custom.name",
        ),
        (
            {"tool_choice": {"type": "custom", "custom": {"name": "missing"}}},
            "chat_custom_tool_choice_invalid",
            "tool_choice.custom.name",
        ),
        (
            {"tool_choice": {"type": "mcp"}},
            "mcp_connectors_not_allowed",
            "tool_choice.type",
        ),
        (
            {
                "stream": True,
                "tools": [{"type": "custom", "custom": {"name": "ok"}}],
            },
            "chat_streaming_custom_tool_not_supported",
            "stream",
        ),
    ],
)
def test_invalid_custom_tool_shapes_are_rejected_without_raw_payload(
    request_overrides: dict[str, object],
    expected_code: str,
    expected_param: str,
) -> None:
    policy = ChatCompletionRequestPolicy(_settings(HARD_MAX_INPUT_TOKENS=5000))

    with pytest.raises(RequestPolicyError) as exc_info:
        policy.apply(
            {
                "model": "gpt-4.1-mini",
                "messages": [{"role": "user", "content": "hi"}],
                **request_overrides,
            }
        )

    assert exc_info.value.error_code == expected_code
    assert exc_info.value.param == expected_param
    assert "definition" not in exc_info.value.safe_message


@pytest.mark.parametrize("marker", ["server_url", "connector_id", "authorization", "require_approval"])
def test_provider_side_tool_markers_are_rejected_at_tool_object_level(marker: str) -> None:
    policy = ChatCompletionRequestPolicy(_settings(HARD_MAX_INPUT_TOKENS=5000))

    with pytest.raises(ChatCompletionCapabilityPolicyError) as exc_info:
        policy.apply(
            {
                "model": "gpt-4.1-mini",
                "messages": [{"role": "user", "content": "hi"}],
                "tools": [{"type": "function", "function": {"name": "lookup"}, marker: "configured"}],
            }
        )

    assert exc_info.value.error_code == "mcp_connectors_not_allowed"
    assert exc_info.value.param == f"tools[0].{marker}"


def test_trusted_calibration_policy_allows_hosted_web_search_markers() -> None:
    policy = ChatCompletionRequestPolicy(_settings(HARD_MAX_INPUT_TOKENS=5000))

    result = policy.apply(
        {
            "model": "gpt-5-search-api",
            "messages": [{"role": "user", "content": "hi"}],
            "web_search_options": {"search_context_size": "low"},
            "tools": [{"type": "web_search_preview"}],
        },
        capability_policy_mode=CAPABILITY_POLICY_MODE_TRUSTED_CALIBRATION_DISCOVERY,
    )

    assert result.effective_body["model"] == "gpt-5-search-api"


def test_trusted_calibration_policy_allows_unknown_hosted_tool_when_enabled() -> None:
    policy = ChatCompletionRequestPolicy(
        _settings(
            HARD_MAX_INPUT_TOKENS=5000,
            TRUSTED_CALIBRATION_ALLOW_UNKNOWN_HOSTED_TOOLS=True,
        )
    )

    result = policy.apply(
        {
            "model": "gpt-4.1-mini",
            "messages": [{"role": "user", "content": "hi"}],
            "tools": [{"type": "vendor_discovery_tool"}],
        },
        capability_policy_mode=CAPABILITY_POLICY_MODE_TRUSTED_CALIBRATION_DISCOVERY,
    )

    assert result.effective_body["tools"][0]["type"] == "vendor_discovery_tool"


def test_trusted_calibration_policy_rejects_unknown_hosted_tool_when_disabled() -> None:
    policy = ChatCompletionRequestPolicy(
        _settings(
            HARD_MAX_INPUT_TOKENS=5000,
            TRUSTED_CALIBRATION_ALLOW_UNKNOWN_HOSTED_TOOLS=False,
        )
    )

    with pytest.raises(ChatCompletionCapabilityPolicyError) as exc_info:
        policy.apply(
            {
                "model": "gpt-4.1-mini",
                "messages": [{"role": "user", "content": "hi"}],
                "tools": [{"type": "vendor_discovery_tool"}],
            },
            capability_policy_mode=CAPABILITY_POLICY_MODE_TRUSTED_CALIBRATION_DISCOVERY,
        )

    assert exc_info.value.error_code == "unknown_tool_type_not_allowed"


@pytest.mark.parametrize("marker", ["server_url", "connector_id", "authorization", "require_approval"])
def test_trusted_calibration_policy_still_rejects_external_authority_markers(
    marker: str,
) -> None:
    policy = ChatCompletionRequestPolicy(_settings(HARD_MAX_INPUT_TOKENS=5000))

    with pytest.raises(ChatCompletionCapabilityPolicyError) as exc_info:
        policy.apply(
            {
                "model": "gpt-4.1-mini",
                "messages": [{"role": "user", "content": "hi"}],
                "tools": [{"type": "web_search", marker: "configured"}],
            },
            capability_policy_mode=CAPABILITY_POLICY_MODE_TRUSTED_CALIBRATION_DISCOVERY,
        )

    assert exc_info.value.error_code == "mcp_connectors_not_allowed"


def test_trusted_calibration_policy_still_rejects_mcp_and_background_state() -> None:
    policy = ChatCompletionRequestPolicy(_settings(HARD_MAX_INPUT_TOKENS=5000))

    for request_overrides, expected_code in [
        ({"tools": [{"type": "mcp"}]}, "mcp_connectors_not_allowed"),
        ({"background": True}, "background_not_allowed"),
        ({"store": True}, "background_not_allowed"),
        ({"previous_response_id": "resp_123"}, "background_not_allowed"),
    ]:
        with pytest.raises(RequestPolicyError) as exc_info:
            policy.apply(
                {
                    "model": "gpt-4.1-mini",
                    "messages": [{"role": "user", "content": "hi"}],
                    **request_overrides,
                },
                capability_policy_mode=CAPABILITY_POLICY_MODE_TRUSTED_CALIBRATION_DISCOVERY,
            )
        assert exc_info.value.error_code == expected_code


def test_trusted_calibration_still_rejects_unknown_top_level_fields() -> None:
    policy = ChatCompletionRequestPolicy(
        _settings(
            HARD_MAX_INPUT_TOKENS=5000,
            TRUSTED_CALIBRATION_ALLOW_UNKNOWN_HOSTED_TOOLS=True,
        )
    )

    with pytest.raises(ChatCompletionFieldPolicyError) as exc_info:
        policy.apply(
            {
                "model": "gpt-4.1-mini",
                "messages": [{"role": "user", "content": "hi"}],
                "x_vendor_future_feature": {"enabled": True},
            },
            capability_policy_mode=CAPABILITY_POLICY_MODE_TRUSTED_CALIBRATION_DISCOVERY,
        )

    assert exc_info.value.error_code == "unknown_chat_completion_field"
    assert exc_info.value.param == "x_vendor_future_feature"


@pytest.mark.parametrize(
    ("overrides", "expected_code", "expected_param"),
    [
        ({"modalities": ["text", "audio"]}, "unsupported_chat_completion_modality", "modalities"),
        ({"audio": {"voice": "alloy"}}, "unsupported_chat_completion_modality", "audio"),
        ({"service_tier": "flex"}, "service_tier_not_supported", "service_tier"),
        ({"metadata": ["not", "object"]}, "chat_field_invalid_type", "metadata"),
        ({"metadata": {"too_large": "x" * 20000}}, "chat_metadata_too_large", "metadata"),
    ],
)
def test_field_registry_rejects_explicit_unsupported_fields(
    overrides: dict[str, object],
    expected_code: str,
    expected_param: str,
) -> None:
    policy = ChatCompletionRequestPolicy(_settings(HARD_MAX_INPUT_TOKENS=20000))

    with pytest.raises(RequestPolicyError) as exc_info:
        policy.apply(
            {
                "model": "gpt-4.1-mini",
                "messages": [{"role": "user", "content": "hi"}],
                **overrides,
            }
        )

    assert exc_info.value.error_code == expected_code
    assert exc_info.value.param == expected_param


def test_choice_count_omitted_is_allowed() -> None:
    policy = ChatCompletionRequestPolicy(_settings())

    result = policy.apply(
        {
            "model": "gpt-4.1-mini",
            "messages": [{"role": "user", "content": "hi"}],
        }
    )

    assert "n" not in result.effective_body


def test_choice_count_one_is_allowed_and_preserved() -> None:
    policy = ChatCompletionRequestPolicy(_settings())

    result = policy.apply(
        {
            "model": "gpt-4.1-mini",
            "messages": [{"role": "user", "content": "hi"}],
            "n": 1,
        }
    )

    assert result.effective_body["n"] == 1
    assert result.effective_choice_count == 1
    assert result.effective_output_tokens_per_choice == 12
    assert result.effective_output_tokens == 12


def test_multiple_choice_count_is_choice_aware_for_output_reservation() -> None:
    policy = ChatCompletionRequestPolicy(_settings(HARD_MAX_INPUT_TOKENS=5000))
    single_choice = policy.apply(
        {
            "model": "gpt-4.1-mini",
            "messages": [{"role": "user", "content": "hi"}],
            "max_completion_tokens": 8,
        }
    )

    result = policy.apply(
        {
            "model": "gpt-4.1-mini",
            "messages": [{"role": "user", "content": "hi"}],
            "max_completion_tokens": 8,
            "n": 3,
        }
    )

    assert result.effective_body["n"] == 3
    assert result.effective_choice_count == 3
    assert result.requested_output_tokens == 8
    assert result.effective_output_tokens_per_choice == 8
    assert result.effective_output_tokens == 24
    assert result.estimated_input_tokens == single_choice.estimated_input_tokens


@pytest.mark.parametrize("value", [0, -1, True, False, "1", 1.0, {}, []])
def test_invalid_choice_count_is_rejected_without_mutating_original(value: object) -> None:
    policy = ChatCompletionRequestPolicy(_settings())
    body = {
        "model": "gpt-4.1-mini",
        "messages": [{"role": "user", "content": "hi"}],
        "n": value,
        "max_completion_tokens": 8,
    }
    original = copy.deepcopy(body)

    with pytest.raises(RequestPolicyError) as exc_info:
        policy.apply(body)

    assert exc_info.value.param == "n"
    assert exc_info.value.error_code == "chat_choice_count_invalid"
    assert body == original


def test_choice_count_above_gateway_cap_is_rejected_without_mutating_original() -> None:
    policy = ChatCompletionRequestPolicy(_settings(CHAT_MAX_CHOICES_PER_REQUEST=4))
    body = {
        "model": "gpt-4.1-mini",
        "messages": [{"role": "user", "content": "hi"}],
        "n": 5,
        "max_completion_tokens": 8,
    }
    original = copy.deepcopy(body)

    with pytest.raises(RequestPolicyError) as exc_info:
        policy.apply(body)

    assert exc_info.value.param == "n"
    assert exc_info.value.error_code == "chat_choice_count_limit_exceeded"
    assert body == original


def test_chat_completion_request_model_preserves_extra_openai_fields() -> None:
    payload = ChatCompletionRequest(
        model="gpt-4.1-mini",
        messages=[{"role": "user", "content": "hi"}],
        temperature=0.2,
        response_format={"type": "json_object"},
    )

    body = payload.model_dump(mode="python", exclude_none=True)

    assert body["temperature"] == 0.2
    assert body["response_format"] == {"type": "json_object"}


def test_streaming_policy_forces_include_usage_without_mutating_original() -> None:
    policy = ChatCompletionRequestPolicy(_settings(HARD_MAX_INPUT_TOKENS=5000))
    original = {
        "model": "gpt-4.1-mini",
        "messages": [{"role": "user", "content": "hi"}],
        "stream": True,
        "stream_options": {"include_usage": False, "other": "preserved"},
    }

    result = policy.apply(original)

    assert result.effective_body["stream_options"] == {
        "include_usage": True,
        "other": "preserved",
    }
    assert original["stream_options"] == {"include_usage": False, "other": "preserved"}


def test_streaming_policy_injects_include_usage_when_missing() -> None:
    policy = ChatCompletionRequestPolicy(_settings(HARD_MAX_INPUT_TOKENS=5000))

    result = policy.apply(
        {
            "model": "gpt-4.1-mini",
            "messages": [{"role": "user", "content": "hi"}],
            "stream": True,
        }
    )

    assert result.effective_body["stream_options"] == {"include_usage": True}


def test_streaming_function_tool_and_structured_output_fields_remain_allowed() -> None:
    policy = ChatCompletionRequestPolicy(_settings(HARD_MAX_INPUT_TOKENS=5000))

    result = policy.apply(
        {
            "model": "gpt-4.1-mini",
            "messages": [{"role": "user", "content": "hi"}],
            "stream": True,
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "lookup",
                        "parameters": {
                            "type": "object",
                            "properties": {"query": {"type": "string"}},
                        },
                    },
                }
            ],
            "tool_choice": {"type": "function", "function": {"name": "lookup"}},
            "response_format": {"type": "json_object"},
            "logprobs": True,
            "top_logprobs": 2,
        }
    )

    assert result.effective_body["stream"] is True
    assert result.effective_body["stream_options"] == {"include_usage": True}
    assert result.effective_body["tools"][0]["type"] == "function"
    assert result.effective_body["tool_choice"]["function"]["name"] == "lookup"
    assert result.effective_body["response_format"] == {"type": "json_object"}
    assert result.effective_body["logprobs"] is True
    assert result.effective_body["top_logprobs"] == 2


@pytest.mark.parametrize(
    ("overrides", "expected_code", "expected_param"),
    [
        (
            {"tools": [{"type": "custom", "custom": {"name": "ok"}}]},
            "chat_streaming_custom_tool_not_supported",
            "stream",
        ),
        ({"tools": [{"type": "web_search"}]}, "web_search_not_allowed", "tools[0].type"),
        ({"web_search_options": {"search_context_size": "low"}}, "web_search_not_allowed", "web_search_options"),
        ({"model": "gpt-5-search-api"}, "search_model_requires_hosted_web_search", "model"),
        ({"n": 99}, "chat_choice_count_limit_exceeded", "n"),
        ({"service_tier": "flex"}, "service_tier_not_supported", "service_tier"),
    ],
)
def test_streaming_requests_keep_unsupported_feature_rejections(
    overrides: dict[str, object],
    expected_code: str,
    expected_param: str,
) -> None:
    policy = ChatCompletionRequestPolicy(_settings(HARD_MAX_INPUT_TOKENS=5000))
    request = {
        "model": "gpt-4.1-mini",
        "messages": [{"role": "user", "content": "hi"}],
        "stream": True,
        **overrides,
    }

    with pytest.raises(RequestPolicyError) as exc_info:
        policy.apply(request)

    assert exc_info.value.error_code == expected_code
    assert exc_info.value.param == expected_param


def test_streaming_multiple_choices_are_allowed_by_request_policy() -> None:
    policy = ChatCompletionRequestPolicy(_settings(HARD_MAX_INPUT_TOKENS=5000))

    result = policy.apply(
        {
            "model": "gpt-4.1-mini",
            "messages": [{"role": "user", "content": "hi"}],
            "stream": True,
            "max_completion_tokens": 8,
            "n": 2,
        }
    )

    assert result.effective_body["n"] == 2
    assert result.effective_body["stream_options"] == {"include_usage": True}
    assert result.effective_output_tokens == 16


def test_streaming_policy_rejects_non_object_stream_options() -> None:
    policy = ChatCompletionRequestPolicy(_settings())

    with pytest.raises(RequestPolicyError) as exc_info:
        policy.apply(
            {
                "model": "gpt-4.1-mini",
                "messages": [{"role": "user", "content": "hi"}],
                "stream": True,
                "stream_options": "include_usage",
            }
        )
    assert exc_info.value.error_code == "invalid_stream_options"


def test_policy_service_safety_constraints() -> None:
    import slaif_gateway.services.request_policy as module

    source = inspect.getsource(module).lower()

    for disallowed in (
        "openai",
        "openrouter",
        "httpx",
        "aiosmtplib",
        "celery",
        "quota",
        "pricing",
        "accounting",
        "fastapi",
    ):
        assert disallowed not in source
