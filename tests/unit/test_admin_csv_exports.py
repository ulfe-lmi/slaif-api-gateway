from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from slaif_gateway.config import Settings
from slaif_gateway.db.models import AdminSession, AdminUser
from slaif_gateway.main import create_app
from slaif_gateway.services.admin_export_service import AdminCsvExportResult
from slaif_gateway.services.admin_session_service import AdminSessionContext


class _FakeSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    def begin(self):
        return self


class _FakeSessionmaker:
    def __call__(self):
        return _FakeSession()


def _app(settings: Settings | None = None):
    app = create_app(settings or _settings())
    app.state.db_sessionmaker = _FakeSessionmaker()
    return app


def _settings(**overrides: object) -> Settings:
    values = {
        "APP_ENV": "test",
        "DATABASE_URL": "postgresql+asyncpg://user:secret@localhost:5432/test_db",
        "ADMIN_SESSION_SECRET": "s" * 40,
        "ADMIN_USAGE_EXPORT_MAX_ROWS": 25,
        "ADMIN_AUDIT_EXPORT_MAX_ROWS": 30,
    }
    values.update(overrides)
    return Settings(**values)


def _login(monkeypatch, client: TestClient) -> AdminUser:
    admin_user = AdminUser(
        id=uuid.uuid4(),
        email="admin@example.org",
        display_name="Admin User",
        password_hash="argon2-hash",
        role="admin",
        is_active=True,
    )
    admin_session = AdminSession(
        id=uuid.uuid4(),
        admin_user_id=admin_user.id,
        session_token_hash="sha256:session",
        csrf_token_hash="sha256:csrf",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    admin_session.admin_user = admin_user

    async def validate_admin_session(self, **kwargs):
        return AdminSessionContext(admin_user=admin_user, admin_session=admin_session)

    async def refresh_csrf_token(self, **kwargs):
        return "dashboard-csrf"

    def verify_session_csrf_token(self, admin_session_arg, csrf_token):
        return csrf_token == "dashboard-csrf"

    monkeypatch.setattr(
        "slaif_gateway.services.admin_session_service.AdminSessionService.validate_admin_session",
        validate_admin_session,
    )
    monkeypatch.setattr(
        "slaif_gateway.services.admin_session_service.AdminSessionService.refresh_csrf_token",
        refresh_csrf_token,
    )
    monkeypatch.setattr(
        "slaif_gateway.services.admin_session_service.AdminSessionService.verify_session_csrf_token",
        verify_session_csrf_token,
    )
    client.cookies.set("slaif_admin_session", "session-plaintext")
    return admin_user


def test_usage_export_requires_auth() -> None:
    client = TestClient(_app())

    response = client.post("/admin/usage/export.csv", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/login"


def test_usage_export_requires_csrf_confirmation_and_reason(monkeypatch) -> None:
    client = TestClient(_app())
    _login(monkeypatch, client)

    missing_csrf = client.post(
        "/admin/usage/export.csv",
        data={"confirm_export": "true", "reason": "review"},
    )
    assert missing_csrf.status_code == 400

    missing_confirm = client.post(
        "/admin/usage/export.csv",
        data={"csrf_token": "dashboard-csrf", "reason": "review"},
    )
    assert missing_confirm.status_code == 400

    missing_reason = client.post(
        "/admin/usage/export.csv",
        data={"csrf_token": "dashboard-csrf", "confirm_export": "true"},
    )
    assert missing_reason.status_code == 400


def test_audit_export_requires_auth_csrf_confirmation_and_reason(monkeypatch) -> None:
    client = TestClient(_app())

    unauthenticated = client.post("/admin/audit/export.csv", follow_redirects=False)
    assert unauthenticated.status_code == 303

    _login(monkeypatch, client)
    missing_csrf = client.post(
        "/admin/audit/export.csv",
        data={"confirm_export": "true", "reason": "review"},
    )
    assert missing_csrf.status_code == 400

    missing_confirm = client.post(
        "/admin/audit/export.csv",
        data={"csrf_token": "dashboard-csrf", "reason": "review"},
    )
    assert missing_confirm.status_code == 400

    missing_reason = client.post(
        "/admin/audit/export.csv",
        data={"csrf_token": "dashboard-csrf", "confirm_export": "true"},
    )
    assert missing_reason.status_code == 400


def test_valid_usage_export_returns_csv_and_passes_filters(monkeypatch) -> None:
    client = TestClient(_app())
    admin = _login(monkeypatch, client)
    seen: dict[str, object] = {}

    async def export_usage_csv(self, **kwargs):
        seen.update(kwargs)
        return AdminCsvExportResult(
            filename_prefix="usage-export",
            content="created_at,request_id\r\n2026-01-01,req\r\n",
            row_count=1,
            audit_log_id=uuid.uuid4(),
        )

    monkeypatch.setattr(
        "slaif_gateway.services.admin_export_service.AdminCsvExportService.export_usage_csv",
        export_usage_csv,
    )

    gateway_key_id = uuid.uuid4()
    response = client.post(
        "/admin/usage/export.csv",
        data={
            "csrf_token": "dashboard-csrf",
            "confirm_export": "true",
            "reason": "operations review",
            "provider": "openai",
            "model": "gpt",
            "endpoint": "/v1/chat/completions",
            "status": "finalized",
            "gateway_key_id": str(gateway_key_id),
            "streaming": "false",
            "limit": "10",
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment; filename=\"usage-export-" in response.headers["content-disposition"]
    assert response.text.startswith("created_at,request_id")
    assert seen["actor_admin_id"] == admin.id
    assert seen["gateway_key_id"] == gateway_key_id
    assert seen["streaming"] is False
    assert seen["limit"] == 10


def test_valid_audit_export_returns_csv_and_passes_filters(monkeypatch) -> None:
    client = TestClient(_app())
    admin = _login(monkeypatch, client)
    seen: dict[str, object] = {}

    async def export_audit_csv(self, **kwargs):
        seen.update(kwargs)
        return AdminCsvExportResult(
            filename_prefix="audit-export",
            content="created_at,action\r\n2026-01-01,key.created\r\n",
            row_count=1,
            audit_log_id=uuid.uuid4(),
        )

    monkeypatch.setattr(
        "slaif_gateway.services.admin_export_service.AdminCsvExportService.export_audit_csv",
        export_audit_csv,
    )

    actor_filter_id = uuid.uuid4()
    response = client.post(
        "/admin/audit/export.csv",
        data={
            "csrf_token": "dashboard-csrf",
            "confirm_export": "true",
            "reason": "audit review",
            "actor_admin_id": str(actor_filter_id),
            "action": "key",
            "target_type": "gateway_key",
            "request_id": "req",
            "limit": "5",
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert response.text.startswith("created_at,action")
    assert seen["actor_admin_id"] == admin.id
    assert seen["actor_filter_admin_id"] == actor_filter_id
    assert seen["limit"] == 5


def test_export_limit_above_configured_max_fails(monkeypatch) -> None:
    client = TestClient(_app())
    _login(monkeypatch, client)

    response = client.post(
        "/admin/usage/export.csv",
        data={
            "csrf_token": "dashboard-csrf",
            "confirm_export": "true",
            "reason": "review",
            "limit": "26",
        },
    )

    assert response.status_code == 400
    assert "less than or equal to 25" in response.text
