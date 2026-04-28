import uuid
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient

from slaif_gateway.config import Settings
from slaif_gateway.db.models import AdminSession, AdminUser
from slaif_gateway.main import create_app
from slaif_gateway.schemas.admin_keys import AdminKeyDetail, AdminKeyListRow
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


def _safe_key() -> AdminKeyDetail:
    row = AdminKeyListRow(
        id=uuid.uuid4(),
        public_key_id="public-safe-id",
        key_prefix="sk-slaif-",
        key_hint="sk-slaif-public",
        owner_id=uuid.uuid4(),
        owner_display_name="Safe Owner",
        owner_email="owner@example.org",
        institution_id=None,
        institution_name=None,
        cohort_id=None,
        cohort_name=None,
        status="active",
        computed_display_status="active",
        can_suspend=True,
        can_activate=False,
        can_revoke=True,
        can_rotate=True,
        valid_from=datetime.now(UTC) - timedelta(days=1),
        valid_until=datetime.now(UTC) + timedelta(days=1),
        cost_limit_eur=Decimal("5.000000000"),
        token_limit_total=1000,
        request_limit_total=100,
        cost_used_eur=Decimal("0"),
        tokens_used_total=0,
        requests_used_total=0,
        cost_reserved_eur=Decimal("0"),
        tokens_reserved_total=0,
        requests_reserved_total=0,
        allowed_models_summary="gpt-test",
        allowed_endpoints_summary="/v1/chat/completions",
        allowed_providers_summary="All",
        rate_limit_policy_summary="Default",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    return AdminKeyDetail(
        **asdict(row),
        revoked_at=None,
        revoked_reason=None,
        created_by_admin_user_id=None,
        last_used_at=None,
        last_quota_reset_at=None,
        quota_reset_count=0,
    )


def test_admin_key_pages_render_only_safe_metadata(monkeypatch) -> None:
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
    key = _safe_key()

    async def validate_admin_session(self, **kwargs):
        return AdminSessionContext(admin_user=admin_user, admin_session=admin_session)

    async def refresh_csrf_token(self, **kwargs):
        return "rendered-csrf-token"

    async def list_keys(self, **kwargs):
        return [key]

    async def get_key_detail(self, gateway_key_id):
        return key

    monkeypatch.setattr(
        "slaif_gateway.services.admin_session_service.AdminSessionService.validate_admin_session",
        validate_admin_session,
    )
    monkeypatch.setattr(
        "slaif_gateway.services.admin_session_service.AdminSessionService.refresh_csrf_token",
        refresh_csrf_token,
    )
    monkeypatch.setattr(
        "slaif_gateway.services.admin_key_dashboard.AdminKeyDashboardService.list_keys",
        list_keys,
    )
    monkeypatch.setattr(
        "slaif_gateway.services.admin_key_dashboard.AdminKeyDashboardService.get_key_detail",
        get_key_detail,
    )
    client = TestClient(app)
    client.cookies.set("slaif_admin_session", "session-token-must-not-render")

    combined = f"{client.get('/admin/keys').text}\n{client.get(f'/admin/keys/{key.id}').text}"

    assert key.public_key_id in combined
    assert key.key_hint in combined
    assert "password_hash_must_not_render" not in combined
    assert "session_hash_must_not_render" not in combined
    assert "session-token-must-not-render" not in combined
    assert settings.ADMIN_SESSION_SECRET not in combined
    assert settings.OPENAI_UPSTREAM_API_KEY not in combined
    assert settings.OPENROUTER_API_KEY not in combined
    assert "token_hash" not in combined
    assert "encrypted_payload" not in combined
    assert "nonce" not in combined
