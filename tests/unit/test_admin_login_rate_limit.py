from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from slaif_gateway.config import Settings
from slaif_gateway.services.admin_login_rate_limit import AdminLoginRateLimitService, normalize_admin_login_email


class _AuditRepo:
    def __init__(self) -> None:
        self.rows: list[dict[str, object]] = []

    async def add_audit_log(self, **kwargs):
        kwargs.setdefault("created_at", datetime.now(UTC))
        self.rows.append(kwargs)
        return kwargs

    async def count_recent_admin_login_failures(
        self,
        *,
        normalized_email: str,
        ip_address: str | None,
        since: datetime,
    ) -> int:
        return sum(
            1
            for row in self.rows
            if row["action"] == "admin_login_failed"
            and row["created_at"] >= since
            and (
                row.get("new_values", {}).get("email") == normalized_email
                or (ip_address is not None and row.get("ip_address") == ip_address)
            )
        )

    async def get_latest_admin_login_lockout(
        self,
        *,
        normalized_email: str,
        ip_address: str | None,
        since: datetime,
    ):
        candidates = [
            row
            for row in self.rows
            if row["action"] == "admin_login_rate_limited"
            and row["created_at"] >= since
            and (
                row.get("new_values", {}).get("email") == normalized_email
                or (ip_address is not None and row.get("ip_address") == ip_address)
            )
        ]
        if not candidates:
            return None
        latest = max(candidates, key=lambda row: row["created_at"])
        return SimpleNamespace(created_at=latest["created_at"])


def _settings(**overrides) -> Settings:
    values = {
        "APP_ENV": "test",
        "ADMIN_SESSION_SECRET": "s" * 40,
        "ADMIN_LOGIN_MAX_FAILED_ATTEMPTS": 3,
        "ADMIN_LOGIN_WINDOW_SECONDS": 300,
        "ADMIN_LOGIN_LOCKOUT_SECONDS": 120,
    }
    values.update(overrides)
    return Settings(**values)


def _service(**settings_overrides) -> tuple[AdminLoginRateLimitService, _AuditRepo]:
    audit = _AuditRepo()
    service = AdminLoginRateLimitService(
        settings=_settings(**settings_overrides),
        audit_repository=audit,
    )
    return service, audit


def _set_created_at(audit: _AuditRepo, timestamp: datetime) -> None:
    for row in audit.rows:
        row["created_at"] = timestamp


@pytest.mark.asyncio
async def test_below_threshold_allows_login() -> None:
    service, audit = _service()
    now = datetime(2026, 4, 1, 12, 0, tzinfo=UTC)
    for _ in range(2):
        await service.record_failed_login(
            normalized_email="admin@example.org",
            admin_user_id=None,
            ip_address="203.0.113.10",
            user_agent="pytest",
            now=now,
        )
    _set_created_at(audit, now)

    result = await service.check_login_allowed(
        normalized_email="admin@example.org",
        ip_address="203.0.113.10",
        now=now + timedelta(seconds=1),
    )

    assert result.allowed is True
    assert [row["action"] for row in audit.rows].count("admin_login_rate_limited") == 0


@pytest.mark.asyncio
async def test_threshold_reached_blocks_login() -> None:
    service, audit = _service()
    now = datetime(2026, 4, 1, 12, 0, tzinfo=UTC)
    admin_user_id = uuid.uuid4()
    for _ in range(3):
        await service.record_failed_login(
            normalized_email="admin@example.org",
            admin_user_id=admin_user_id,
            ip_address="203.0.113.10",
            user_agent="pytest",
            now=now,
        )
    _set_created_at(audit, now)

    result = await service.check_login_allowed(
        normalized_email="admin@example.org",
        ip_address="203.0.113.10",
        now=now + timedelta(seconds=1),
    )

    assert result.allowed is False
    assert result.retry_after_seconds is not None
    assert audit.rows[-1]["action"] == "admin_login_rate_limited"
    assert "password" not in str(audit.rows).lower()


@pytest.mark.asyncio
async def test_lockout_expires() -> None:
    service, audit = _service()
    now = datetime(2026, 4, 1, 12, 0, tzinfo=UTC)
    for _ in range(3):
        await service.record_failed_login(
            normalized_email="admin@example.org",
            admin_user_id=None,
            ip_address="203.0.113.10",
            user_agent="pytest",
            now=now,
        )
    _set_created_at(audit, now)

    result = await service.check_login_allowed(
        normalized_email="admin@example.org",
        ip_address="203.0.113.10",
        now=now + timedelta(seconds=121),
    )

    assert result.allowed is True


@pytest.mark.asyncio
async def test_email_normalization_and_ip_based_counting() -> None:
    service, audit = _service()
    now = datetime(2026, 4, 1, 12, 0, tzinfo=UTC)
    assert normalize_admin_login_email(" ADMIN@Example.ORG ") == "admin@example.org"
    for index in range(3):
        await service.record_failed_login(
            normalized_email=f"missing-{index}@example.org",
            admin_user_id=None,
            ip_address="203.0.113.10",
            user_agent="pytest",
            now=now,
        )
    _set_created_at(audit, now)

    result = await service.check_login_allowed(
        normalized_email="another@example.org",
        ip_address="203.0.113.10",
        now=now + timedelta(seconds=1),
    )

    assert result.allowed is False


@pytest.mark.asyncio
async def test_disabled_setting_allows_attempt_but_still_audits_failure() -> None:
    service, audit = _service(ADMIN_LOGIN_RATE_LIMIT_ENABLED=False)
    now = datetime(2026, 4, 1, 12, 0, tzinfo=UTC)
    for _ in range(5):
        await service.record_failed_login(
            normalized_email="admin@example.org",
            admin_user_id=None,
            ip_address="203.0.113.10",
            user_agent="pytest",
            now=now,
        )

    result = await service.check_login_allowed(
        normalized_email="admin@example.org",
        ip_address="203.0.113.10",
        now=now + timedelta(seconds=1),
    )

    assert result.allowed is True
    assert [row["action"] for row in audit.rows].count("admin_login_failed") == 5
    assert [row["action"] for row in audit.rows].count("admin_login_rate_limited") == 0
