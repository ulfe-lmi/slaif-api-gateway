"""Recursive metadata sanitization for durable records and logs."""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from typing import Any

from slaif_gateway.utils.redaction import (
    is_sensitive_key,
    normalize_sensitive_key,
    redact_text,
)

REDACTED_VALUE = "***"

_CONTENT_KEY_NAMES = {
    "messages",
    "choices",
    "content",
    "prompt",
    "completion",
    "requestbody",
    "responsebody",
    "requestpayload",
    "responsepayload",
    "rawrequest",
    "rawresponse",
}


def is_content_key(key: str) -> bool:
    """Return True when a metadata key can contain prompt/completion/body content."""
    return normalize_sensitive_key(key) in _CONTENT_KEY_NAMES


def sanitize_metadata(
    value: Any,
    *,
    drop_content_keys: bool = False,
    accepted_gateway_key_prefixes: tuple[str, ...] | None = None,
) -> object:
    """Return JSON-safe metadata with secrets and optional content fields removed/redacted."""
    return _sanitize_value(
        value,
        drop_content_keys=drop_content_keys,
        accepted_gateway_key_prefixes=accepted_gateway_key_prefixes,
    )


def sanitize_metadata_mapping(
    mapping: Mapping[str, Any] | None,
    *,
    drop_content_keys: bool = False,
    accepted_gateway_key_prefixes: tuple[str, ...] | None = None,
) -> dict[str, object]:
    """Return sanitized metadata mapping suitable for JSONB persistence."""
    if mapping is None:
        return {}
    sanitized = _sanitize_mapping(
        mapping,
        drop_content_keys=drop_content_keys,
        accepted_gateway_key_prefixes=accepted_gateway_key_prefixes,
    )
    return sanitized


def _sanitize_mapping(
    mapping: Mapping[str, Any],
    *,
    drop_content_keys: bool,
    accepted_gateway_key_prefixes: tuple[str, ...] | None,
) -> dict[str, object]:
    safe: dict[str, object] = {}
    for key, item in mapping.items():
        if not isinstance(key, str):
            continue
        if drop_content_keys and is_content_key(key):
            continue
        if is_sensitive_key(key):
            safe[key] = REDACTED_VALUE
            continue
        safe[key] = _sanitize_value(
            item,
            drop_content_keys=drop_content_keys,
            accepted_gateway_key_prefixes=accepted_gateway_key_prefixes,
        )
    return safe


def _sanitize_value(
    value: Any,
    *,
    drop_content_keys: bool,
    accepted_gateway_key_prefixes: tuple[str, ...] | None,
) -> object:
    if value is None or isinstance(value, bool | int):
        return value
    if isinstance(value, str):
        return redact_text(value, accepted_gateway_key_prefixes)
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, float):
        return str(value)
    if isinstance(value, Mapping):
        return _sanitize_mapping(
            value,
            drop_content_keys=drop_content_keys,
            accepted_gateway_key_prefixes=accepted_gateway_key_prefixes,
        )
    if isinstance(value, list | tuple):
        return [
            _sanitize_value(
                item,
                drop_content_keys=drop_content_keys,
                accepted_gateway_key_prefixes=accepted_gateway_key_prefixes,
            )
            for item in value
        ]
    return redact_text(str(value), accepted_gateway_key_prefixes)
