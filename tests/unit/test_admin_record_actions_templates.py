import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from slaif_gateway.config import Settings
from slaif_gateway.db.models import AdminSession, AdminUser
from slaif_gateway.main import create_app
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


def test_record_mutation_forms_render_safe_controls(monkeypatch) -> None:
    settings = Settings(
        APP_ENV="test",
        DATABASE_URL="postgresql+asyncpg://user:secret@localhost:5432/test_db",
        ADMIN_SESSION_SECRET="admin-session-secret-that-must-not-render",
        OPENAI_UPSTREAM_API_KEY="sk-provider-secret-placeholder",
        OPENROUTER_API_KEY="sk-or-provider-secret-placeholder",
    )
    app = create_app(settings)
    app.state.db_sessionmaker = _FakeSessionmaker()
    admin_user = AdminUser(
        id=uuid.uuid4(),
        email="admin@example.org",
        display_name="Admin User",
        password_hash="password_hash_must_not_render",
        role="admin",
        is_active=True,
    )
    admin_session = AdminSession(
        id=uuid.uuid4(),
        admin_user_id=admin_user.id,
        session_token_hash="session_hash_must_not_render",
        csrf_token_hash="csrf_hash_must_not_render",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    admin_session.admin_user = admin_user

    async def validate_admin_session(self, **kwargs):
        return AdminSessionContext(admin_user=admin_user, admin_session=admin_session)

    async def refresh_csrf_token(self, **kwargs):
        return "rendered-csrf-token"

    async def list_institutions(self, **kwargs):
        return []

    monkeypatch.setattr(
        "slaif_gateway.services.admin_session_service.AdminSessionService.validate_admin_session",
        validate_admin_session,
    )
    monkeypatch.setattr(
        "slaif_gateway.services.admin_session_service.AdminSessionService.refresh_csrf_token",
        refresh_csrf_token,
    )
    monkeypatch.setattr(
        "slaif_gateway.services.admin_records_dashboard.AdminRecordsDashboardService.list_institutions",
        list_institutions,
    )
    client = TestClient(app)
    client.cookies.set("slaif_admin_session", "session-token-must-not-render")

    combined = "\n".join(
        [
            client.get("/admin/institutions/new").text,
            client.get("/admin/cohorts/new").text,
            client.get("/admin/owners/new").text,
        ]
    )

    assert 'name="csrf_token" value="rendered-csrf-token"' in combined
    assert 'name="reason"' in combined
    assert "Create institution" in combined
    assert "Create cohort" in combined
    assert "Create owner" in combined
    assert "password_hash_must_not_render" not in combined
    assert "session_hash_must_not_render" not in combined
    assert "session-token-must-not-render" not in combined
    assert settings.ADMIN_SESSION_SECRET not in combined
    assert settings.OPENAI_UPSTREAM_API_KEY not in combined
    assert settings.OPENROUTER_API_KEY not in combined
    assert "token_hash" not in combined
    assert "encrypted_payload" not in combined
    assert "nonce" not in combined
    assert "plaintext gateway key" not in combined.lower()
