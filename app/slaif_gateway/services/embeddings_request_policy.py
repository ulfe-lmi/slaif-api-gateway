"""Request policy for standalone Embeddings API requests."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from slaif_gateway.config import Settings
from slaif_gateway.schemas.embeddings import EmbeddingsPolicyResult
from slaif_gateway.services.policy_errors import (
    EmbeddingsInputInvalidError,
    EmbeddingsInputLimitExceededError,
    EmbeddingsUnsupportedFieldError,
    EmbeddingsUnsupportedOptionError,
)

_EMBEDDINGS_FIELDS = frozenset({"input", "model", "dimensions", "encoding_format", "user"})
_SUPPORTED_ENCODING_FORMATS = frozenset({"float", "base64"})


class EmbeddingsRequestPolicy:
    """Apply standalone Embeddings API request validation and normalization."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def apply(self, body: Mapping[str, Any]) -> EmbeddingsPolicyResult:
        effective_body = dict(body)
        _reject_unknown_fields(effective_body)

        model = _required_str(effective_body.get("model"), field_name="model")
        normalized_input, estimated_input_tokens = _normalize_embeddings_input(
            effective_body.get("input"),
            settings=self._settings,
        )

        encoding_format = effective_body.get("encoding_format")
        if encoding_format is not None:
            encoding_format = _required_str(encoding_format, field_name="encoding_format").lower()
            if encoding_format not in _SUPPORTED_ENCODING_FORMATS:
                raise EmbeddingsUnsupportedOptionError(
                    "The requested embeddings encoding_format is not supported.",
                    param="encoding_format",
                )
            effective_body["encoding_format"] = encoding_format

        dimensions = effective_body.get("dimensions")
        if dimensions is not None:
            if isinstance(dimensions, bool) or not isinstance(dimensions, int):
                raise EmbeddingsUnsupportedOptionError(
                    "Embeddings dimensions must be a positive integer.",
                    param="dimensions",
                )
            if dimensions <= 0 or dimensions > self._settings.EMBEDDINGS_MAX_DIMENSIONS:
                raise EmbeddingsUnsupportedOptionError(
                    "Embeddings dimensions exceed the configured gateway limit.",
                    param="dimensions",
                )
            effective_body["dimensions"] = dimensions

        user = effective_body.get("user")
        if user is not None:
            user = _required_str(user, field_name="user")
            if len(user.encode("utf-8")) > self._settings.EMBEDDINGS_MAX_USER_BYTES:
                raise EmbeddingsInputLimitExceededError(
                    "Embeddings user exceeds the configured gateway size limit.",
                    param="user",
                )
            effective_body["user"] = user

        if estimated_input_tokens > self._settings.EMBEDDINGS_MAX_TOTAL_ESTIMATED_TOKENS:
            raise EmbeddingsInputLimitExceededError(
                "Embeddings input exceeds the configured estimated token limit.",
                param="input",
            )

        effective_body["model"] = model
        effective_body["input"] = normalized_input

        return EmbeddingsPolicyResult(
            effective_body=effective_body,
            estimated_input_tokens=estimated_input_tokens,
        )


def _reject_unknown_fields(body: Mapping[str, Any]) -> None:
    unknown = sorted(set(body) - _EMBEDDINGS_FIELDS)
    if not unknown:
        return
    raise EmbeddingsUnsupportedFieldError(
        "Embeddings requests may only include documented top-level fields.",
        param=str(unknown[0]),
    )


def _required_str(value: object, *, field_name: str) -> str:
    if not isinstance(value, str):
        raise EmbeddingsInputInvalidError(
            f"Embeddings {field_name} must be a string.",
            param=field_name,
        )
    normalized = value.strip()
    if not normalized:
        raise EmbeddingsInputInvalidError(
            f"Embeddings {field_name} must not be empty.",
            param=field_name,
        )
    return normalized if field_name == "model" else value


def _normalize_embeddings_input(
    value: object,
    *,
    settings: Settings,
) -> tuple[object, int]:
    if isinstance(value, str):
        normalized_text, estimated_tokens = _normalize_text_item(
            value,
            field_name="input",
            settings=settings,
        )
        if len(normalized_text.encode("utf-8")) > settings.EMBEDDINGS_MAX_TOTAL_INPUT_BYTES:
            raise EmbeddingsInputLimitExceededError(
                "Embeddings input exceeds the configured total byte limit.",
                param="input",
            )
        return normalized_text, estimated_tokens

    if not isinstance(value, Sequence) or isinstance(value, bytes | bytearray | str):
        raise EmbeddingsInputInvalidError(
            "Embeddings input must be a string, an array of strings, a token array, or an array of token arrays.",
            param="input",
        )

    items = list(value)
    if not items:
        raise EmbeddingsInputInvalidError(
            "Embeddings input arrays must not be empty.",
            param="input",
        )
    if len(items) > settings.EMBEDDINGS_MAX_INPUT_ITEMS:
        raise EmbeddingsInputLimitExceededError(
            "Embeddings input includes too many items.",
            param="input",
        )

    first = items[0]
    if isinstance(first, str):
        normalized: list[str] = []
        total_estimated_tokens = 0
        total_bytes = 0
        for index, item in enumerate(items):
            if not isinstance(item, str):
                raise EmbeddingsInputInvalidError(
                    "Embeddings input arrays must not mix strings and token arrays.",
                    param=f"input[{index}]",
                )
            normalized_item, estimated_tokens = _normalize_text_item(
                item,
                field_name=f"input[{index}]",
                settings=settings,
            )
            normalized.append(normalized_item)
            total_estimated_tokens += estimated_tokens
            total_bytes += len(normalized_item.encode("utf-8"))
        if total_bytes > settings.EMBEDDINGS_MAX_TOTAL_INPUT_BYTES:
            raise EmbeddingsInputLimitExceededError(
                "Embeddings input exceeds the configured total byte limit.",
                param="input",
            )
        return normalized, total_estimated_tokens

    if _is_token_scalar(first):
        normalized_tokens = _normalize_token_array(
            items,
            field_name="input",
            settings=settings,
        )
        if len(str(normalized_tokens).encode("utf-8")) > settings.EMBEDDINGS_MAX_TOTAL_INPUT_BYTES:
            raise EmbeddingsInputLimitExceededError(
                "Embeddings input exceeds the configured total byte limit.",
                param="input",
            )
        return normalized_tokens, len(normalized_tokens)

    if isinstance(first, Sequence) and not isinstance(first, bytes | bytearray | str):
        normalized_nested: list[list[int]] = []
        total_estimated_tokens = 0
        total_bytes = 0
        for index, item in enumerate(items):
            if not isinstance(item, Sequence) or isinstance(item, bytes | bytearray | str):
                raise EmbeddingsInputInvalidError(
                    "Embeddings nested input arrays must contain only token arrays.",
                    param=f"input[{index}]",
                )
            normalized_item = _normalize_token_array(
                item,
                field_name=f"input[{index}]",
                settings=settings,
            )
            normalized_nested.append(normalized_item)
            total_estimated_tokens += len(normalized_item)
            total_bytes += len(str(normalized_item).encode("utf-8"))
        if total_bytes > settings.EMBEDDINGS_MAX_TOTAL_INPUT_BYTES:
            raise EmbeddingsInputLimitExceededError(
                "Embeddings input exceeds the configured total byte limit.",
                param="input",
            )
        return normalized_nested, total_estimated_tokens

    raise EmbeddingsInputInvalidError(
        "Embeddings input uses an unsupported item shape.",
        param="input",
    )


def _normalize_text_item(
    value: str,
    *,
    field_name: str,
    settings: Settings,
) -> tuple[str, int]:
    if not value.strip():
        raise EmbeddingsInputInvalidError(
            "Embeddings text input items must not be empty.",
            param=field_name,
        )
    item_bytes = len(value.encode("utf-8"))
    if item_bytes > settings.EMBEDDINGS_MAX_TEXT_ITEM_BYTES:
        raise EmbeddingsInputLimitExceededError(
            "An embeddings text input item exceeds the configured size limit.",
            param=field_name,
        )
    estimated_tokens = max(1, (item_bytes + 2) // 3)
    return value, estimated_tokens


def _normalize_token_array(
    values: Sequence[object],
    *,
    field_name: str,
    settings: Settings,
) -> list[int]:
    if not values:
        raise EmbeddingsInputInvalidError(
            "Embeddings token arrays must not be empty.",
            param=field_name,
        )
    if len(values) > settings.EMBEDDINGS_MAX_TOKEN_ARRAY_LENGTH:
        raise EmbeddingsInputLimitExceededError(
            "An embeddings token array exceeds the configured length limit.",
            param=field_name,
        )
    normalized: list[int] = []
    for index, value in enumerate(values):
        if not _is_token_scalar(value):
            raise EmbeddingsInputInvalidError(
                "Embeddings token arrays must contain only integers.",
                param=f"{field_name}[{index}]",
            )
        token = int(value)
        if token < 0:
            raise EmbeddingsInputInvalidError(
                "Embeddings token arrays must not contain negative integers.",
                param=f"{field_name}[{index}]",
            )
        normalized.append(token)
    return normalized


def _is_token_scalar(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)
