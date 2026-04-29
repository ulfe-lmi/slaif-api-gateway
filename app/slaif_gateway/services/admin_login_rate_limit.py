"""Audit-backed admin login failed-attempt rate limiting."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from slaif_gateway.config import Settings
from slaif_gateway.db.repositories.audit import AuditRepository


@dataclass(frozen=True, slots=True)
class AdminLoginRateLimitResult:
    """Safe login rate-limit check result."""

    allowed: bool
    retry_after_seconds: int | None = None


class AdminLoginRateLimitService:
    """Track admin login failures through audit rows and enforce temporary lockout."""

    def __init__(self, *, settings: Settings, audit_repository: AuditRepository) -> None:
        self._settings = settings
        self._audit = audit_repository

    async def check_login_allowed(
        self,
        *,
        normalized_email: str,
        ip_address: str | None,
        now: datetime | None = None,
    ) -> AdminLoginRateLimitResult:
        """Return whether password verification may proceed."""
        if not self._settings.ADMIN_LOGIN_RATE_LIMIT_ENABLED:
            return AdminLoginRateLimitResult(allowed=True)

        timestamp = _utcnow(now)
        lockout_since = timestamp - timedelta(
            seconds=max(self._settings.ADMIN_LOGIN_WINDOW_SECONDS, self._settings.ADMIN_LOGIN_LOCKOUT_SECONDS)
        )
        latest_lockout = await self._audit.get_latest_admin_login_lockout(
            normalized_email=normalized_email,
            ip_address=_safe_ip_address(ip_address),
            since=lockout_since,
        )
        if latest_lockout is not None:
            locked_until = latest_lockout.created_at + timedelta(seconds=self._settings.ADMIN_LOGIN_LOCKOUT_SECONDS)
            if locked_until > timestamp:
                retry_after = max(1, int((locked_until - timestamp).total_seconds()))
                return AdminLoginRateLimitResult(allowed=False, retry_after_seconds=retry_after)
            return AdminLoginRateLimitResult(allowed=True)

        failure_since = timestamp - timedelta(seconds=self._settings.ADMIN_LOGIN_WINDOW_SECONDS)
        failure_count = await self._audit.count_recent_admin_login_failures(
            normalized_email=normalized_email,
            ip_address=_safe_ip_address(ip_address),
            since=failure_since,
        )
        if failure_count >= self._settings.ADMIN_LOGIN_MAX_FAILED_ATTEMPTS:
            return AdminLoginRateLimitResult(
                allowed=False,
                retry_after_seconds=self._settings.ADMIN_LOGIN_LOCKOUT_SECONDS,
            )
        return AdminLoginRateLimitResult(allowed=True)

    async def record_failed_login(
        self,
        *,
        normalized_email: str,
        admin_user_id: uuid.UUID | None,
        ip_address: str | None,
        user_agent: str | None,
        now: datetime | None = None,
    ) -> None:
        """Audit a failed login and create a lockout audit row when the threshold is reached."""
        timestamp = _utcnow(now)
        safe_ip_address = _safe_ip_address(ip_address)
        await self._audit.add_audit_log(
            action="admin_login_failed",
            entity_type="admin_user",
            entity_id=admin_user_id,
            ip_address=safe_ip_address,
            user_agent=user_agent,
            new_values={"email": normalized_email},
        )

        if not self._settings.ADMIN_LOGIN_RATE_LIMIT_ENABLED:
            return

        failure_since = timestamp - timedelta(seconds=self._settings.ADMIN_LOGIN_WINDOW_SECONDS)
        failure_count = await self._audit.count_recent_admin_login_failures(
            normalized_email=normalized_email,
            ip_address=safe_ip_address,
            since=failure_since,
        )
        if failure_count >= self._settings.ADMIN_LOGIN_MAX_FAILED_ATTEMPTS:
            await self.record_lockout_event(
                normalized_email=normalized_email,
                admin_user_id=admin_user_id,
                ip_address=safe_ip_address,
                user_agent=user_agent,
                now=timestamp,
            )

    async def record_lockout_event(
        self,
        *,
        normalized_email: str,
        admin_user_id: uuid.UUID | None,
        ip_address: str | None,
        user_agent: str | None,
        now: datetime | None = None,
    ) -> None:
        """Audit that a login attempt was blocked by failed-attempt rate limiting."""
        _ = now
        await self._audit.add_audit_log(
            action="admin_login_rate_limited",
            entity_type="admin_login",
            entity_id=admin_user_id,
            ip_address=_safe_ip_address(ip_address),
            user_agent=user_agent,
            new_values={"email": normalized_email},
        )


def normalize_admin_login_email(email: str) -> str:
    """Normalize admin login email for lookup and rate-limit grouping."""
    return email.strip().lower()


def _safe_ip_address(ip_address: str | None) -> str | None:
    normalized = (ip_address or "").strip()
    return normalized or None


def _utcnow(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(UTC)
    if now.tzinfo is None:
        return now.replace(tzinfo=UTC)
    return now.astimezone(UTC)
