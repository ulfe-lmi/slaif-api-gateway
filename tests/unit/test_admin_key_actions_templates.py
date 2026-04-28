import uuid
from dataclasses import asdict, replace
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


def _settings(**overrides) -> Settings:
    values = {
        "APP_ENV": "test",
        "DATABASE_URL": "postgresql+asyncpg://user:secret@localhost:5432/test_db",
        "ADMIN_SESSION_SECRET": "admin-session-secret-that-must-not-render",
        "OPENAI_UPSTREAM_API_KEY": "sk-provider-secret-placeholder",
        "OPENROUTER_API_KEY": "sk-or-provider-secret-placeholder",
    }
    values.update(overrides)
    return Settings(**values)


def _app(settings: Settings | None = None):
    app = create_app(settings or _settings())
    app.state.db_sessionmaker = _FakeSessionmaker()
    return app


def _detail(
    *,
    status: str = "active",
    display_status: str = "active",
    can_suspend: bool = True,
    can_activate: bool = False,
    can_revoke: bool = True,
) -> AdminKeyDetail:
    row = AdminKeyListRow(
        id=uuid.uuid4(),
        public_key_id="public-action-id",
        key_prefix="sk-slaif-",
        key_hint="sk-slaif-public",
        owner_id=uuid.uuid4(),
        owner_display_name="Safe Owner",
        owner_email="owner@example.org",
        institution_id=None,
        institution_name=None,
        cohort_id=None,
        cohort_name=None,
        status=status,
        computed_display_status=display_status,
        can_suspend=can_suspend,
        can_activate=can_activate,
        can_revoke=can_revoke,
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


def _login_and_detail(monkeypatch, client: TestClient, key: AdminKeyDetail) -> None:
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
        "slaif_gateway.services.admin_key_dashboard.AdminKeyDashboardService.get_key_detail",
        get_key_detail,
    )
    client.cookies.set("slaif_admin_session", "session-token-must-not-render")


def test_key_detail_renders_lifecycle_forms_for_valid_actions(monkeypatch) -> None:
    key = _detail()
    client = TestClient(_app())
    _login_and_detail(monkeypatch, client, key)

    html = client.get(f"/admin/keys/{key.id}").text

    assert f'action="/admin/keys/{key.id}/suspend"' in html
    assert f'action="/admin/keys/{key.id}/revoke"' in html
    assert f'action="/admin/keys/{key.id}/activate"' not in html
    assert 'name="csrf_token" value="rendered-csrf-token"' in html
    assert 'name="confirm_revoke" value="true"' in html
    assert "I understand revocation is permanent." in html
    assert "Revoke key" in html


def test_key_detail_renders_validity_and_limit_forms(monkeypatch) -> None:
    key = _detail()
    client = TestClient(_app())
    _login_and_detail(monkeypatch, client, key)

    html = client.get(f"/admin/keys/{key.id}").text

    assert f'action="/admin/keys/{key.id}/validity"' in html
    assert f'action="/admin/keys/{key.id}/limits"' in html
    assert 'name="csrf_token" value="rendered-csrf-token"' in html
    assert 'name="valid_from"' in html
    assert 'name="valid_until"' in html
    assert key.valid_from.isoformat() in html
    assert key.valid_until.isoformat() in html
    assert 'name="cost_limit_eur"' in html
    assert 'name="token_limit"' in html
    assert 'name="request_limit"' in html
    assert 'name="clear_cost_limit" value="true"' in html
    assert 'name="clear_token_limit" value="true"' in html
    assert 'name="clear_request_limit" value="true"' in html
    assert str(key.cost_limit_eur) in html
    assert str(key.token_limit_total) in html
    assert str(key.request_limit_total) in html
    assert "PostgreSQL-backed key policy" in html
    assert "Redis operational rate limits are configured separately" in html
    assert "Used and reserved counters are not reset" in html


def test_suspended_key_detail_renders_activation_form(monkeypatch) -> None:
    key = _detail(status="suspended", display_status="suspended", can_suspend=False, can_activate=True)
    client = TestClient(_app())
    _login_and_detail(monkeypatch, client, key)

    html = client.get(f"/admin/keys/{key.id}").text

    assert f'action="/admin/keys/{key.id}/activate"' in html
    assert f'action="/admin/keys/{key.id}/suspend"' not in html
    assert f'action="/admin/keys/{key.id}/revoke"' in html


def test_revoked_key_detail_disables_lifecycle_forms(monkeypatch) -> None:
    key = replace(
        _detail(
            status="revoked",
            display_status="revoked",
            can_suspend=False,
            can_activate=False,
            can_revoke=False,
        ),
        revoked_at=datetime.now(UTC),
        revoked_reason="course ended",
    )
    client = TestClient(_app())
    _login_and_detail(monkeypatch, client, key)

    html = client.get(f"/admin/keys/{key.id}").text

    assert f"/admin/keys/{key.id}/suspend" not in html
    assert f"/admin/keys/{key.id}/activate" not in html
    assert f"/admin/keys/{key.id}/revoke" not in html
    assert "disabled" in html


def test_key_detail_action_panel_does_not_render_sensitive_values(monkeypatch) -> None:
    settings = _settings()
    key = _detail()
    client = TestClient(_app(settings))
    _login_and_detail(monkeypatch, client, key)

    html = client.get(f"/admin/keys/{key.id}").text

    assert key.public_key_id in html
    assert "plaintext-key-must-not-render" not in html
    assert "token_hash" not in html
    assert "encrypted_payload" not in html
    assert "nonce" not in html
    assert settings.OPENAI_UPSTREAM_API_KEY not in html
    assert settings.OPENROUTER_API_KEY not in html
    assert "password_hash_must_not_render" not in html
    assert "session-token-must-not-render" not in html
    assert "session_hash_must_not_render" not in html
    assert "resend" not in html.lower()
