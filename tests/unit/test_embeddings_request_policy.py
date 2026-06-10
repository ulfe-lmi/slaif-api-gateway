from __future__ import annotations

import pytest

from slaif_gateway.config import Settings
from slaif_gateway.services.embeddings_request_policy import EmbeddingsRequestPolicy
from slaif_gateway.services.policy_errors import RequestPolicyError


def _settings(**overrides: object) -> Settings:
    values = {
        "EMBEDDINGS_MAX_INPUT_ITEMS": 3,
        "EMBEDDINGS_MAX_TEXT_ITEM_BYTES": 12,
        "EMBEDDINGS_MAX_TOTAL_INPUT_BYTES": 32,
        "EMBEDDINGS_MAX_TOKEN_ARRAY_LENGTH": 4,
        "EMBEDDINGS_MAX_TOTAL_ESTIMATED_TOKENS": 16,
        "EMBEDDINGS_MAX_DIMENSIONS": 8,
        "EMBEDDINGS_MAX_USER_BYTES": 12,
    }
    values.update(overrides)
    return Settings(**values)


def test_valid_single_string_input_is_accepted() -> None:
    result = EmbeddingsRequestPolicy(_settings()).apply(
        {"model": "text-embedding-3-small", "input": "hello"}
    )

    assert result.effective_body == {"model": "text-embedding-3-small", "input": "hello"}
    assert result.estimated_input_tokens > 0


def test_valid_array_of_strings_is_accepted() -> None:
    result = EmbeddingsRequestPolicy(_settings()).apply(
        {"model": "text-embedding-3-small", "input": ["hello", "world"]}
    )

    assert result.effective_body["input"] == ["hello", "world"]


def test_valid_token_shapes_are_accepted() -> None:
    policy = EmbeddingsRequestPolicy(_settings())

    token_result = policy.apply(
        {"model": "text-embedding-3-small", "input": [1, 2, 3]}
    )
    nested_result = policy.apply(
        {"model": "text-embedding-3-small", "input": [[1, 2], [3, 4]]}
    )

    assert token_result.effective_body["input"] == [1, 2, 3]
    assert nested_result.effective_body["input"] == [[1, 2], [3, 4]]


@pytest.mark.parametrize(
    ("payload", "param"),
    [
        ({"model": "text-embedding-3-small", "input": ""}, "input"),
        ({"model": "text-embedding-3-small", "input": []}, "input"),
        ({"model": "text-embedding-3-small", "input": ["hello", 1]}, "input[1]"),
        ({"model": "text-embedding-3-small", "input": [[1], "hello"]}, "input[1]"),
        ({"model": "text-embedding-3-small", "input": [[]]}, "input[0]"),
    ],
)
def test_invalid_input_shapes_are_rejected(payload: dict[str, object], param: str) -> None:
    with pytest.raises(RequestPolicyError) as exc_info:
        EmbeddingsRequestPolicy(_settings()).apply(payload)

    assert exc_info.value.param == param


def test_large_text_items_and_too_many_inputs_are_rejected() -> None:
    policy = EmbeddingsRequestPolicy(_settings(EMBEDDINGS_MAX_TEXT_ITEM_BYTES=5))

    with pytest.raises(RequestPolicyError) as text_exc:
        policy.apply({"model": "text-embedding-3-small", "input": "toolong"})
    assert text_exc.value.error_code == "embeddings_input_limit_exceeded"

    with pytest.raises(RequestPolicyError) as count_exc:
        EmbeddingsRequestPolicy(_settings(EMBEDDINGS_MAX_INPUT_ITEMS=1)).apply(
            {"model": "text-embedding-3-small", "input": ["a", "b"]}
        )
    assert count_exc.value.error_code == "embeddings_input_limit_exceeded"


def test_large_token_arrays_and_unknown_fields_are_rejected() -> None:
    with pytest.raises(RequestPolicyError) as token_exc:
        EmbeddingsRequestPolicy(_settings(EMBEDDINGS_MAX_TOKEN_ARRAY_LENGTH=2)).apply(
            {"model": "text-embedding-3-small", "input": [1, 2, 3]}
        )
    assert token_exc.value.error_code == "embeddings_input_limit_exceeded"

    with pytest.raises(RequestPolicyError) as field_exc:
        EmbeddingsRequestPolicy(_settings()).apply(
            {
                "model": "text-embedding-3-small",
                "input": "hello",
                "stream": True,
            }
        )
    assert field_exc.value.error_code == "embeddings_field_not_supported"


def test_encoding_format_dimensions_and_user_are_validated() -> None:
    result = EmbeddingsRequestPolicy(_settings()).apply(
        {
            "model": "text-embedding-3-small",
            "input": "hello",
            "encoding_format": "base64",
            "dimensions": 8,
            "user": "learner-1",
        }
    )

    assert result.effective_body["encoding_format"] == "base64"
    assert result.effective_body["dimensions"] == 8
    assert result.effective_body["user"] == "learner-1"

    with pytest.raises(RequestPolicyError) as encoding_exc:
        EmbeddingsRequestPolicy(_settings()).apply(
            {
                "model": "text-embedding-3-small",
                "input": "hello",
                "encoding_format": "hex",
            }
        )
    assert encoding_exc.value.param == "encoding_format"

    with pytest.raises(RequestPolicyError) as dimensions_exc:
        EmbeddingsRequestPolicy(_settings()).apply(
            {
                "model": "text-embedding-3-small",
                "input": "hello",
                "dimensions": 99,
            }
        )
    assert dimensions_exc.value.param == "dimensions"

    raw_user = "secret-user-value"
    with pytest.raises(RequestPolicyError) as user_exc:
        EmbeddingsRequestPolicy(_settings(EMBEDDINGS_MAX_USER_BYTES=4)).apply(
            {
                "model": "text-embedding-3-small",
                "input": "hello",
                "user": raw_user,
            }
        )
    assert user_exc.value.param == "user"
    assert raw_user not in user_exc.value.safe_message
