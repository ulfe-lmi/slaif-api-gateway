from __future__ import annotations

import inspect

import pytest

from slaif_gateway.config import Settings
from slaif_gateway.services.policy_errors import (
    AmbiguousOutputTokenLimitError,
    InputTokenLimitExceededError,
    InvalidOutputTokenLimitError,
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
            "metadata": {"course": "week-1"},
        }
    )

    assert result.effective_body["temperature"] == 0.2
    assert result.effective_body["metadata"]["course"] == "week-1"


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
