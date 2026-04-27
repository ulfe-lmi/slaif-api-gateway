"""Helpers for redacting sensitive values in logs and CLI output."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from sqlalchemy.engine import make_url

from slaif_gateway.utils.crypto import redact_gateway_key

_REDACTED = "***"
_SENSITIVE_KEY_PARTS = (
    "authorization",
    "apikey",
    "providerapikey",
    "openaiapikey",
    "openrouterapikey",
    "token",
    "secret",
    "password",
    "csrf",
    "cookie",
    "session",
    "credential",
    "bearer",
    "nonce",
    "encryptedpayload",
    "tokenhash",
    "plaintextkey",
    "gatewaykey",
    "providerkey",
    "passwordhash",
)
_SAFE_TOKEN_COUNTER_KEYS = {
    "prompttokens",
    "completiontokens",
    "totaltokens",
    "cachedtokens",
    "reasoningtokens",
    "inputtokens",
    "outputtokens",
    "estimatedtokens",
    "reservedtokens",
    "releasedtokens",
    "tokensusedtotal",
    "tokensreservedtotal",
    "tokenlimittotal",
}
_GATEWAY_KEY_TEXT_PATTERN = re.compile(
    r"\b(?P<key>sk-[a-z0-9-]+-[A-Za-z0-9_-]{4,64}\.[A-Za-z0-9._~+/=-]{8,})\b",
    re.IGNORECASE,
)
_BEARER_PATTERN = re.compile(r"\b(Bearer)\s+([A-Za-z0-9._~+/=-]{8,})", re.IGNORECASE)
_PROVIDER_KEY_PATTERN = re.compile(
    r"\b(?:sk-(?:proj-|or-)[A-Za-z0-9._-]{10,}|sk-[A-Za-z0-9]{20,}|"
    r"sk-[A-Za-z0-9-]{12,}(?![A-Za-z0-9_.-]))"
)
_SENSITIVE_ASSIGNMENT_PATTERN = re.compile(
    r"(?i)\b(api[_-]?key|access[_-]?token|refresh[_-]?token|session[_-]?token|"
    r"csrf[_-]?token|password|secret|token)=([^&\s;,]+)"
)


def normalize_sensitive_key(key: str) -> str:
    """Normalize metadata/header keys for robust sensitivity checks."""
    return re.sub(r"[^a-z0-9]", "", key.lower())


def is_sensitive_key(key: str) -> bool:
    """Return True when a metadata key is sensitive across casing/separator styles."""
    normalized = normalize_sensitive_key(key)
    if normalized in _SAFE_TOKEN_COUNTER_KEYS:
        return False
    return any(part in normalized for part in _SENSITIVE_KEY_PARTS)


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

    scheme, _token = parts
    return f"{scheme} {_REDACTED}"


def redact_text(value: str, accepted_gateway_key_prefixes: tuple[str, ...] | None = None) -> str:
    """Redact secret-looking substrings from free-form log text."""
    redacted = value
    redacted = _BEARER_PATTERN.sub(lambda match: f"{match.group(1)} {_REDACTED}", redacted)
    redacted = _GATEWAY_KEY_TEXT_PATTERN.sub(
        lambda match: redact_gateway_key(
            match.group("key"),
            accepted_prefixes=accepted_gateway_key_prefixes,
        ),
        redacted,
    )
    redacted = _PROVIDER_KEY_PATTERN.sub(_REDACTED, redacted)
    redacted = _SENSITIVE_ASSIGNMENT_PATTERN.sub(lambda match: f"{match.group(1)}={_REDACTED}", redacted)
    return redacted


def redact_mapping(
    mapping: Mapping[str, Any],
    accepted_gateway_key_prefixes: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    """Return a recursively redacted dict for sensitive mappings."""
    redacted: dict[str, Any] = {}

    for key, value in mapping.items():
        if is_sensitive_key(key):
            if normalize_sensitive_key(key) == "authorization":
                redacted[key] = redact_authorization_header(value if isinstance(value, str) else None)
            else:
                redacted[key] = _REDACTED if value is not None else "<not set>"
            continue

        if isinstance(value, Mapping):
            redacted[key] = redact_mapping(
                value,
                accepted_gateway_key_prefixes=accepted_gateway_key_prefixes,
            )
        elif isinstance(value, list | tuple):
            redacted[key] = [
                redact_mapping(item, accepted_gateway_key_prefixes=accepted_gateway_key_prefixes)
                if isinstance(item, Mapping)
                else redact_text(item, accepted_gateway_key_prefixes)
                if isinstance(item, str)
                else item
                for item in value
            ]
        elif isinstance(value, str):
            redacted[key] = redact_text(value, accepted_gateway_key_prefixes)
        else:
            redacted[key] = value

    return redacted
