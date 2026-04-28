import re
import uuid
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient

from slaif_gateway.config import Settings
from slaif_gateway.db.models import AdminSession, AdminUser
from slaif_gateway.main import create_app
from slaif_gateway.schemas.admin_keys import AdminKeyDetail, AdminKeyListRow
from slaif_gateway.services.admin_key_dashboard import AdminKeyNotFoundError
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
        "ADMIN_SESSION_SECRET": "s" * 40,
    }
    values.update(overrides)
    return Settings(**values)


def _app(settings: Settings | None = None):
    app = create_app(settings or _settings())
    app.state.db_sessionmaker = _FakeSessionmaker()
    return app


def _admin_user() -> AdminUser:
    return AdminUser(
        id=uuid.uuid4(),
        email="admin@example.org",
        display_name="Admin User",
        password_hash="argon2-hash",
        role="admin",
        is_active=True,
    )


def _admin_session(admin_user: AdminUser) -> AdminSession:
    session = AdminSession(
        id=uuid.uuid4(),
        admin_user_id=admin_user.id,
        session_token_hash="sha256:session",
        csrf_token_hash="sha256:csrf",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    session.admin_user = admin_user
    return session


def _row() -> AdminKeyListRow:
    return AdminKeyListRow(
        id=uuid.uuid4(),
        public_key_id="public-test-id",
        key_prefix="sk-slaif-",
        key_hint="sk-slaif-public",
        owner_id=uuid.uuid4(),
        owner_display_name="Ada Lovelace",
        owner_email="ada@example.org",
        institution_id=uuid.uuid4(),
        institution_name="SLAIF University",
        cohort_id=uuid.uuid4(),
        cohort_name="Spring Workshop",
        status="active",
        computed_display_status="active",
        can_suspend=True,
        can_activate=False,
        can_revoke=True,
        can_rotate=True,
        valid_from=datetime.now(UTC) - timedelta(days=1),
        valid_until=datetime.now(UTC) + timedelta(days=1),
        cost_limit_eur=Decimal("10.000000000"),
        token_limit_total=1000,
        request_limit_total=100,
        cost_used_eur=Decimal("1.000000000"),
        tokens_used_total=10,
        requests_used_total=2,
        cost_reserved_eur=Decimal("0.100000000"),
        tokens_reserved_total=5,
        requests_reserved_total=1,
        allowed_models_summary="gpt-test",
        allowed_endpoints_summary="/v1/chat/completions",
        allowed_providers_summary="openai",
        rate_limit_policy_summary="30 req/min",
        created_at=datetime.now(UTC) - timedelta(days=2),
        updated_at=datetime.now(UTC) - timedelta(days=1),
    )


def _detail() -> AdminKeyDetail:
    row = _row()
    return AdminKeyDetail(
        **asdict(row),
        revoked_at=None,
        revoked_reason=None,
        created_by_admin_user_id=uuid.uuid4(),
        last_used_at=None,
        last_quota_reset_at=None,
        quota_reset_count=0,
    )


def _login(monkeypatch, client: TestClient) -> None:
    admin_user = _admin_user()
    admin_session = _admin_session(admin_user)

    async def validate_admin_session(self, **kwargs):
        return AdminSessionContext(admin_user=admin_user, admin_session=admin_session)

    async def refresh_csrf_token(self, **kwargs):
        return "dashboard-csrf"

    monkeypatch.setattr(
        "slaif_gateway.services.admin_session_service.AdminSessionService.validate_admin_session",
        validate_admin_session,
    )
    monkeypatch.setattr(
        "slaif_gateway.services.admin_session_service.AdminSessionService.refresh_csrf_token",
        refresh_csrf_token,
    )
    client.cookies.set("slaif_admin_session", "session-plaintext")


def test_admin_keys_redirects_when_unauthenticated() -> None:
    response = TestClient(_app()).get("/admin/keys", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/login"


def test_admin_keys_list_returns_html_and_accepts_filters(monkeypatch) -> None:
    seen: dict[str, object] = {}

    async def list_keys(self, **kwargs):
        seen.update(kwargs)
        return [_row()]

    monkeypatch.setattr(
        "slaif_gateway.services.admin_key_dashboard.AdminKeyDashboardService.list_keys",
        list_keys,
    )
    client = TestClient(_app())
    _login(monkeypatch, client)
    cohort_id = uuid.uuid4()

    response = client.get(
        "/admin/keys",
        params={
            "status": "active",
            "owner_email": "ada@example.org",
            "public_key_id": "public-test-id",
            "cohort_id": str(cohort_id),
            "expired": "false",
            "limit": "25",
            "offset": "5",
        },
    )

    assert response.status_code == 200
    assert "Gateway Keys" in response.text
    assert "public-test-id" in response.text
    assert "Ada Lovelace" in response.text
    assert seen["status"] == "active"
    assert seen["owner_email"] == "ada@example.org"
    assert seen["public_key_id"] == "public-test-id"
    assert seen["cohort_id"] == cohort_id
    assert seen["expired"] is False
    assert seen["limit"] == 25
    assert seen["offset"] == 5


def test_admin_key_detail_returns_html(monkeypatch) -> None:
    key = _detail()

    async def get_key_detail(self, gateway_key_id):
        assert gateway_key_id == key.id
        return key

    monkeypatch.setattr(
        "slaif_gateway.services.admin_key_dashboard.AdminKeyDashboardService.get_key_detail",
        get_key_detail,
    )
    client = TestClient(_app())
    _login(monkeypatch, client)

    response = client.get(f"/admin/keys/{key.id}")

    assert response.status_code == 200
    assert "Gateway Key Detail" in response.text
    assert key.public_key_id in response.text
    assert "Plaintext keys" in response.text


def test_admin_key_detail_missing_or_invalid_is_safe(monkeypatch) -> None:
    async def get_key_detail(self, gateway_key_id):
        raise AdminKeyNotFoundError("missing")

    monkeypatch.setattr(
        "slaif_gateway.services.admin_key_dashboard.AdminKeyDashboardService.get_key_detail",
        get_key_detail,
    )
    client = TestClient(_app())
    _login(monkeypatch, client)

    missing = client.get(f"/admin/keys/{uuid.uuid4()}")
    invalid = client.get("/admin/keys/not-a-uuid")

    assert missing.status_code == 404
    assert invalid.status_code == 404
    assert "Gateway key not found." in missing.text
    assert "Gateway key not found." in invalid.text


def test_admin_keys_templates_do_not_render_sensitive_values(monkeypatch) -> None:
    secret_markers = [
        "plaintext-key-must-not-render",
        "token_hash_must_not_render",
        "encrypted_payload_must_not_render",
        "nonce_must_not_render",
        "sk-provider-secret-placeholder",
        "password_hash_must_not_render",
        "session-plaintext",
    ]
    key = _detail()

    async def list_keys(self, **kwargs):
        return [key]

    async def get_key_detail(self, gateway_key_id):
        return key

    monkeypatch.setattr(
        "slaif_gateway.services.admin_key_dashboard.AdminKeyDashboardService.list_keys",
        list_keys,
    )
    monkeypatch.setattr(
        "slaif_gateway.services.admin_key_dashboard.AdminKeyDashboardService.get_key_detail",
        get_key_detail,
    )
    client = TestClient(
        _app(
            _settings(
                OPENAI_UPSTREAM_API_KEY="sk-provider-secret-placeholder",
                OPENROUTER_API_KEY="sk-or-provider-secret-placeholder",
            )
        )
    )
    _login(monkeypatch, client)

    list_response = client.get("/admin/keys")
    detail_response = client.get(f"/admin/keys/{key.id}")
    combined = f"{list_response.text}\n{detail_response.text}"

    assert key.public_key_id in combined
    assert key.key_prefix in combined
    assert key.key_hint in combined
    for marker in secret_markers:
        assert marker not in combined
    assert re.search(r"token_hash|encrypted_payload|nonce|password_hash", combined) is None
