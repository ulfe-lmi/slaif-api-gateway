"""CSRF helpers for server-rendered admin forms."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import UTC, datetime

from slaif_gateway.config import Settings

_LOGIN_CSRF_NONCE_BYTES = 24


class CsrfError(Exception):
    """Raised when a CSRF token is missing, tampered with, or expired."""


def create_login_csrf_token(settings: Settings, *, now: datetime | None = None) -> str:
    """Create a signed login CSRF token safe to render in a hidden form field."""
    timestamp = int(_utcnow(now).timestamp())
    nonce = secrets.token_urlsafe(_LOGIN_CSRF_NONCE_BYTES)
    payload = _b64encode(f"{timestamp}:{nonce}".encode("utf-8"))
    signature = _sign(settings, "admin-login-csrf", payload)
    return f"{payload}.{signature}"


def verify_login_csrf_token(
    settings: Settings,
    *,
    form_token: str | None,
    cookie_token: str | None,
    now: datetime | None = None,
) -> None:
    """Verify login CSRF token from both hidden form field and signed cookie."""
    if not form_token or not cookie_token:
        raise CsrfError("CSRF token is required")
    if not hmac.compare_digest(form_token, cookie_token):
        raise CsrfError("CSRF token is invalid")

    try:
        payload, signature = form_token.split(".", 1)
    except ValueError as exc:
        raise CsrfError("CSRF token is invalid") from exc

    expected = _sign(settings, "admin-login-csrf", payload)
    if not hmac.compare_digest(signature, expected):
        raise CsrfError("CSRF token is invalid")

    try:
        decoded = _b64decode(payload).decode("utf-8")
        timestamp_text, nonce = decoded.split(":", 1)
        issued_at = int(timestamp_text)
    except (ValueError, UnicodeDecodeError) as exc:
        raise CsrfError("CSRF token is invalid") from exc

    if not nonce:
        raise CsrfError("CSRF token is invalid")

    age_seconds = int(_utcnow(now).timestamp()) - issued_at
    if age_seconds < 0 or age_seconds > settings.ADMIN_CSRF_TTL_SECONDS:
        raise CsrfError("CSRF token has expired")


def _sign(settings: Settings, purpose: str, payload: str) -> str:
    secret = settings.ADMIN_SESSION_SECRET
    if not secret:
        raise CsrfError("ADMIN_SESSION_SECRET is required for admin CSRF protection")
    digest = hmac.new(
        secret.encode("utf-8"),
        f"{purpose}:{payload}".encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return _b64encode(digest)


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def _utcnow(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(UTC)
    if now.tzinfo is None:
        return now.replace(tzinfo=UTC)
    return now.astimezone(UTC)
