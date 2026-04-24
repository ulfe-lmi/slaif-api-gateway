"""Cryptographic helpers for gateway key and token digest handling."""

from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets
from dataclasses import dataclass

_GATEWAY_KEY_PREFIX = "sk-ulfe-"
_PUBLIC_ID_LENGTH = 16
_SECRET_BYTES = 32
_SECRET_TOKEN_BYTES = 43
_PUBLIC_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{8,64}$")


@dataclass(frozen=True, slots=True)
class GeneratedGatewayKey:
    """Container for freshly generated gateway key material."""

    plaintext_key: str
    public_key_id: str
    display_prefix: str


def _urlsafe_b64_no_padding(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def generate_gateway_key() -> GeneratedGatewayKey:
    """Generate an OpenAI-compatible gateway key in sk-ulfe-<public_id>.<secret> format."""
    public_key_id = _urlsafe_b64_no_padding(secrets.token_bytes(_PUBLIC_ID_LENGTH))
    secret = _urlsafe_b64_no_padding(secrets.token_bytes(_SECRET_BYTES))
    plaintext_key = f"{_GATEWAY_KEY_PREFIX}{public_key_id}.{secret}"
    return GeneratedGatewayKey(
        plaintext_key=plaintext_key,
        public_key_id=public_key_id,
        display_prefix=f"{_GATEWAY_KEY_PREFIX}{public_key_id[:8]}",
    )


def parse_gateway_key_public_id(key: str) -> str:
    """Parse and return public_key_id from gateway key, raising ValueError if malformed."""
    if not key or not isinstance(key, str):
        raise ValueError("gateway key must be a non-empty string")
    if not key.startswith(_GATEWAY_KEY_PREFIX):
        raise ValueError("gateway key has invalid prefix")

    payload = key[len(_GATEWAY_KEY_PREFIX) :]
    if "." not in payload:
        raise ValueError("gateway key must contain public key id and secret separated by '.'")

    public_key_id, secret = payload.split(".", 1)
    if not public_key_id or not secret:
        raise ValueError("gateway key must contain non-empty public key id and secret")
    if not _PUBLIC_ID_PATTERN.fullmatch(public_key_id):
        raise ValueError("gateway key public key id is malformed")
    if len(secret) < _SECRET_TOKEN_BYTES:
        raise ValueError("gateway key secret is too short")

    return public_key_id


def is_plausible_gateway_key(key: str) -> bool:
    """Return True when key appears to match gateway key format and constraints."""
    try:
        parse_gateway_key_public_id(key)
    except ValueError:
        return False
    return True


def redact_gateway_key(key: str) -> str:
    """Redact a gateway key to keep only safe shape information."""
    if not key:
        return "<redacted>"

    if not is_plausible_gateway_key(key):
        return "<redacted>"

    public_key_id = parse_gateway_key_public_id(key)
    payload = key[len(_GATEWAY_KEY_PREFIX) :]
    _, secret = payload.split(".", 1)
    secret_hint = f"{secret[:4]}...{secret[-4:]}"
    return f"{_GATEWAY_KEY_PREFIX}{public_key_id}.{secret_hint}"


def hmac_sha256_token(token: str, secret: str | bytes) -> str:
    """Return deterministic lowercase-hex HMAC-SHA-256 digest for token."""
    if not token:
        raise ValueError("token must be non-empty")

    secret_bytes = secret.encode("utf-8") if isinstance(secret, str) else secret
    if not secret_bytes:
        raise ValueError("secret must be non-empty")

    return hmac.new(secret_bytes, token.encode("utf-8"), hashlib.sha256).hexdigest()


def verify_hmac_sha256_token(token: str, expected_hex_digest: str, secret: str | bytes) -> bool:
    """Verify token digest using constant-time comparison."""
    if not expected_hex_digest:
        raise ValueError("expected_hex_digest must be non-empty")

    digest = hmac_sha256_token(token=token, secret=secret)
    return hmac.compare_digest(digest, expected_hex_digest.lower())
