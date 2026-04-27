"""Helpers for redacting sensitive values in logs and CLI output."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from sqlalchemy.engine import make_url

_REDACTED = "***"
_SECRET_KEYWORDS = (
    "authorization",
    "api_key",
    "apikey",
    "token",
    "secret",
    "password",
    "csrf",
    "cookie",
    "session",
)
_SECRET_TEXT_PATTERNS = (
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{12,}", re.IGNORECASE),
    re.compile(r"\bsk-(?:slaif|ulfe|or|proj|test)?-[A-Za-z0-9._-]{8,}"),
)


def redact_database_url(database_url: str | None) -> str:
    """Return a redacted database URL safe for user-facing output."""
    if not database_url:
        return "<not set>"

    try:
        return make_url(database_url).render_as_string(hide_password=True)
    except Exception:
        return database_url.replace("//", f"//{_REDACTED}:", 1)


def redact_secret(value: str | None, visible_prefix: int = 6, visible_suffix: int = 4) -> str:
    """Redact a generic secret while preserving small edge hints."""
    if value is None:
        return "<not set>"
    if value == "":
        return "<empty>"

    if len(value) <= visible_prefix + visible_suffix:
        return _REDACTED

    return f"{value[:visible_prefix]}{_REDACTED}{value[-visible_suffix:]}"


def redact_authorization_header(value: str | None) -> str:
    """Redact Authorization header values, never returning raw bearer tokens."""
    if not value:
        return "<not set>"

    parts = value.split(None, 1)
    if len(parts) != 2:
        return _REDACTED

    scheme, token = parts
    return f"{scheme} {redact_secret(token, visible_prefix=4, visible_suffix=4)}"


def redact_text(value: str) -> str:
    """Redact secret-looking substrings from free-form log text."""
    redacted = value
    for pattern in _SECRET_TEXT_PATTERNS:
        redacted = pattern.sub(_REDACTED, redacted)
    return redacted


def redact_mapping(mapping: Mapping[str, Any]) -> dict[str, Any]:
    """Return a recursively redacted dict for sensitive mappings."""
    redacted: dict[str, Any] = {}

    for key, value in mapping.items():
        key_lower = key.lower()
        if any(keyword in key_lower for keyword in _SECRET_KEYWORDS):
            if key_lower == "authorization":
                redacted[key] = redact_authorization_header(value if isinstance(value, str) else None)
            else:
                redacted[key] = redact_secret(str(value) if value is not None else None)
            continue

        if isinstance(value, Mapping):
            redacted[key] = redact_mapping(value)
        elif isinstance(value, list):
            redacted[key] = [
                redact_mapping(item) if isinstance(item, Mapping) else item for item in value
            ]
        elif isinstance(value, str):
            redacted[key] = redact_text(value)
        else:
            redacted[key] = value

    return redacted
