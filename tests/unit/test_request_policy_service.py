from __future__ import annotations

import inspect
import copy

import pytest

from slaif_gateway.config import Settings
from slaif_gateway.schemas.openai import ChatCompletionRequest
from slaif_gateway.services.policy_errors import (
    AmbiguousOutputTokenLimitError,
    InputTokenLimitExceededError,
    InvalidOutputTokenLimitError,
    InvalidChoiceCountError,
    InvalidStreamOptionsError,
    OutputTokenLimitExceededError,
)
from slaif_gateway.services.request_policy import ChatCompletionRequestPolicy


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


def test_input_estimate_handles_structured_content_blocks() -> None:
    policy = ChatCompletionRequestPolicy(_settings(HARD_MAX_INPUT_TOKENS=1000))

    result = policy.apply(
        {
            "model": "gpt-4.1-mini",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "hello world"},
                        {"type": "input_image", "image_url": "https://example.test/image.png"},
                    ],
                }
            ],
        }
    )

    assert result.estimated_input_tokens > 0


def test_service_does_not_mutate_original_request() -> None:
    policy = ChatCompletionRequestPolicy(_settings())
    original = {
        "model": "gpt-4.1-mini",
        "messages": [{"role": "user", "content": "hi"}],
    }

    _ = policy.apply(original)

    assert "max_completion_tokens" not in original


def test_unrelated_fields_are_preserved() -> None:
    policy = ChatCompletionRequestPolicy(_settings())

    result = policy.apply(
        {
            "model": "gpt-4.1-mini",
            "messages": [{"role": "user", "content": "hi"}],
            "temperature": 0.2,
            "top_p": 0.9,
            "tools": [{"type": "function", "function": {"name": "lookup"}}],
            "tool_choice": "auto",
            "response_format": {"type": "json_object"},
            "seed": 123,
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
    )

    assert result.effective_body["temperature"] == 0.2
    assert result.effective_body["top_p"] == 0.9
    assert result.effective_body["tools"][0]["function"]["name"] == "lookup"
    assert result.effective_body["tool_choice"] == "auto"
    assert result.effective_body["response_format"] == {"type": "json_object"}
    assert result.effective_body["seed"] == 123
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


@pytest.mark.parametrize("value", [2, 10, 0, -1, True, False, "1", 1.0, {}, []])
def test_invalid_choice_count_is_rejected_without_mutating_original(value: object) -> None:
    policy = ChatCompletionRequestPolicy(_settings())
    body = {
        "model": "gpt-4.1-mini",
        "messages": [{"role": "user", "content": "hi"}],
        "n": value,
        "max_completion_tokens": 8,
    }
    original = copy.deepcopy(body)

    with pytest.raises(InvalidChoiceCountError) as exc_info:
        policy.apply(body)

    assert exc_info.value.param == "n"
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
    policy = ChatCompletionRequestPolicy(_settings())
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
    policy = ChatCompletionRequestPolicy(_settings())

    result = policy.apply(
        {
            "model": "gpt-4.1-mini",
            "messages": [{"role": "user", "content": "hi"}],
            "stream": True,
        }
    )

    assert result.effective_body["stream_options"] == {"include_usage": True}


def test_streaming_policy_rejects_non_object_stream_options() -> None:
    policy = ChatCompletionRequestPolicy(_settings())

    with pytest.raises(InvalidStreamOptionsError):
        policy.apply(
            {
                "model": "gpt-4.1-mini",
                "messages": [{"role": "user", "content": "hi"}],
                "stream": True,
                "stream_options": "include_usage",
            }
        )


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
