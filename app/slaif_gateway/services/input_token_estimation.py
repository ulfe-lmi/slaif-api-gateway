"""Conservative dependency-free input token estimation helpers."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class NonMessageInputEstimate:
    """Safe summary of serialized non-message request fields included in input estimates."""

    input_tokens_estimate: int
    counted_fields: tuple[str, ...]
    counted_bytes: int


@dataclass(frozen=True, slots=True)
class ChatInputEstimate:
    """Safe summary of chat input estimates."""

    message_input_tokens_estimate: int
    non_message_input_tokens_estimate: int
    total_input_tokens_estimate: int
    counted_fields: tuple[str, ...]
    counted_bytes: int


def canonical_json_bytes(value: Any) -> bytes:
    """Serialize JSON-compatible values deterministically for estimation."""
    try:
        text = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("Request field is not JSON-serializable.") from exc
    return text.encode("utf-8")


def estimate_serialized_json_input_tokens(value: Any) -> int:
    """Return a conservative token upper-bound for serialized JSON values."""
    return len(canonical_json_bytes(value))


def estimate_non_message_input_tokens(
    provider_body: Mapping[str, Any],
) -> NonMessageInputEstimate:
    """Estimate forwarded non-message fields that can affect provider context.

    Object and list fields are counted with a byte-length upper bound over
    deterministic JSON serialization. Scalar generation controls are ignored.
    """
    counted_fields: list[str] = []
    counted_bytes = 0

    for field_name in sorted(provider_body):
        if field_name == "messages":
            continue
        value = provider_body[field_name]
        if not isinstance(value, Mapping | list):
            continue

        field_bytes = canonical_json_bytes({field_name: value})
        counted_fields.append(field_name)
        counted_bytes += len(field_bytes)

    return NonMessageInputEstimate(
        input_tokens_estimate=counted_bytes,
        counted_fields=tuple(counted_fields),
        counted_bytes=counted_bytes,
    )


def estimate_chat_completion_input_tokens(
    provider_body: Mapping[str, Any],
    *,
    messages: list[Mapping[str, Any]],
) -> ChatInputEstimate:
    """Estimate total Chat Completions input tokens for policy and reservation."""
    message_tokens = estimate_message_input_tokens(messages)
    non_message = estimate_non_message_input_tokens(provider_body)
    total = message_tokens + non_message.input_tokens_estimate

    return ChatInputEstimate(
        message_input_tokens_estimate=message_tokens,
        non_message_input_tokens_estimate=non_message.input_tokens_estimate,
        total_input_tokens_estimate=total,
        counted_fields=non_message.counted_fields,
        counted_bytes=non_message.counted_bytes,
    )


def estimate_message_input_tokens(messages: list[Mapping[str, Any]]) -> int:
    """Conservative message estimator used by Chat Completions policy."""
    total_tokens = 0

    for message in messages:
        total_tokens += 16
        for value in message.values():
            total_tokens += _estimate_value_tokens(value)

    return total_tokens


def _estimate_value_tokens(value: Any) -> int:
    if value is None:
        return 0

    if isinstance(value, str):
        return _estimate_text_tokens(value)

    if isinstance(value, Mapping):
        if "text" in value and isinstance(value.get("text"), str):
            return _estimate_text_tokens(value["text"]) + 4
        return _estimate_text_tokens(canonical_json_bytes(value).decode("utf-8"))

    if isinstance(value, list):
        subtotal = 0
        for item in value:
            subtotal += _estimate_value_tokens(item)
        return subtotal + 4

    return _estimate_text_tokens(canonical_json_bytes(value).decode("utf-8"))


def _estimate_text_tokens(text: str) -> int:
    byte_len = len(text.encode("utf-8"))
    return max(1, (byte_len + 2) // 3)
