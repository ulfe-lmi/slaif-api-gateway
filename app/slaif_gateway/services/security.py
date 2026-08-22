"""Focused security-hardening primitives for sessions, abuse, redirects, and secrets."""

from __future__ import annotations

import ipaddress
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit


SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'self'; img-src 'self' data:; style-src 'self'; "
        "script-src 'self'; frame-ancestors 'none'; base-uri 'self'"
    ),
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
}


@dataclass(slots=True)
class AbuseTracker:
    """Bounded in-process tracker for login throttling and identity lockouts."""

    max_attempts: int = 5
    window: timedelta = timedelta(minutes=10)
    events: dict[str, list[datetime]] = field(default_factory=dict)

    def record_failure(self, subject: str, *, now: datetime | None = None) -> None:
        timestamp = _aware(now)
        bucket = self.events.setdefault(subject, [])
        bucket[:] = [item for item in bucket if timestamp - item <= self.window]
        bucket.append(timestamp)

    def is_blocked(self, subject: str, *, now: datetime | None = None) -> bool:
        timestamp = _aware(now)
        bucket = self.events.get(subject, [])
        recent = [item for item in bucket if timestamp - item <= self.window]
        return len(recent) >= self.max_attempts

    def clear(self, subject: str) -> None:
        self.events.pop(subject, None)


def safe_admin_redirect(target: str | None, allowed_hosts: set[str]) -> str:
    """Reject open redirects; only relative paths or exact allow-listed URLs are valid."""
    if not target or not target.startswith("/") or target.startswith("//"):
        return "/"
    parsed = urlsplit(target)
    if parsed.netloc or parsed.scheme not in {"", "http", "https"}:
        return "/"
    if parsed.scheme and not _host_allowed(parsed.hostname or "", allowed_hosts):
        return "/"
    return target


def provider_base_url_is_safe(value: str) -> bool:
    """Allow HTTPS public endpoints or explicit numeric loopback only."""
    try:
        parsed = urlsplit(value)
    except ValueError:
        return False
    if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password or parsed.query or parsed.fragment:
        return False
    host = parsed.hostname or ""
    if parsed.path.rstrip("/"):
        return False
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return parsed.scheme == "https" and bool(host) and "." in host
    return address.is_loopback


def validate_secret_strength(secrets: Mapping[str, object], *, minimum_bytes: int = 32, production: bool = False):
    """Return missing/weak secret names; fail closed when required values are absent."""
    missing: list[str] = []
    weak: list[str] = []
    defaults: list[str] = []
    for name, value in secrets.items():
        if value is None or (isinstance(value, str) and not value.strip()):
            missing.append(name)
            continue
        encoded_len = len(value.encode()) if isinstance(value, str) else len(value)
        if encoded_len < minimum_bytes:
            weak.append(name)
        if production and isinstance(value, str) and any(marker in value.lower() for marker in ("example", "change-me")):
            defaults.append(name)
    if missing or weak:
        raise ValueError(f"Insecure startup secrets: missing={missing}, short={weak}")
    if defaults:
        raise ValueError(f"Default/example secret rejected in non-development environment: {defaults}")
    return True


def _host_allowed(host: str, allowed_hosts: set[str]) -> bool:
    return host.lower() in {item.lower() for item in allowed_hosts}


def _aware(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
