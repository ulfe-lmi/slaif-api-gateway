import uuid
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

from fastapi.testclient import TestClient

from slaif_gateway.config import Settings
from slaif_gateway.db.models import AdminSession, AdminUser
from slaif_gateway.main import create_app
from slaif_gateway.schemas.admin_catalog import AdminFxRateDetail, AdminFxRateListRow
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


def _login_for_actions(monkeypatch, client: TestClient, *, valid_csrf: str = "dashboard-csrf") -> AdminUser:
    admin_user = _admin_user()
    admin_session = _admin_session(admin_user)

    async def validate_admin_session(self, **kwargs):
        return AdminSessionContext(admin_user=admin_user, admin_session=admin_session)

    async def refresh_csrf_token(self, **kwargs):
        return valid_csrf

    def verify_session_csrf_token(self, admin_session, csrf_token):
        return csrf_token == valid_csrf

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


def _fx_detail(**overrides) -> AdminFxRateDetail:
    row = AdminFxRateListRow(
        id=uuid.uuid4(),
        base_currency="USD",
        quote_currency="EUR",
        rate=Decimal("0.920000000"),
        source="manual source",
        valid_from=datetime.now(UTC) - timedelta(days=1),
        valid_until=None,
        created_at=datetime.now(UTC),
    )
    values = asdict(row)
    values.update(overrides)
    return AdminFxRateDetail(**values)


def _valid_form(**overrides) -> dict[str, str]:
    values = {
        "csrf_token": "dashboard-csrf",
        "base_currency": "USD",
        "quote_currency": "EUR",
        "rate": "0.920000000",
        "valid_from": "2026-01-01T00:00:00+00:00",
        "valid_until": "",
        "source": "manual source",
        "reason": "fx update",
    }
    values.update(overrides)
    return values


def test_fx_rate_create_get_requires_login() -> None:
    client = TestClient(_app())

    response = client.get("/admin/fx/new", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/login"


def test_fx_rate_create_get_renders_csrf_form(monkeypatch) -> None:
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    response = client.get("/admin/fx/new")

    assert response.status_code == 200
    assert 'name="csrf_token" value="dashboard-csrf"' in response.text
    assert "external FX services" in response.text
    assert "provider key value" not in response.text
    assert "sk-provider-secret" not in response.text


def test_fx_rate_post_without_csrf_fails_before_service_call(monkeypatch) -> None:
    called = False

    async def create_fx_rate(self, **kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr("slaif_gateway.services.fx_rate_service.FxRateService.create_fx_rate", create_fx_rate)
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    response = client.post("/admin/fx/new", data=_valid_form(csrf_token=""))

    assert response.status_code == 400
    assert "Invalid CSRF token." in response.text
    assert called is False


def test_fx_rate_post_with_invalid_csrf_fails(monkeypatch) -> None:
    called = False

    async def create_fx_rate(self, **kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr("slaif_gateway.services.fx_rate_service.FxRateService.create_fx_rate", create_fx_rate)
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    response = client.post("/admin/fx/new", data=_valid_form(csrf_token="wrong"))

    assert response.status_code == 400
    assert "Invalid CSRF token." in response.text
    assert called is False


def test_fx_rate_valid_create_calls_service_with_decimal_rate(monkeypatch) -> None:
    seen: dict[str, object] = {}
    fx_rate_id = uuid.uuid4()

    async def create_fx_rate(self, **kwargs):
        seen.update(kwargs)
        return SimpleNamespace(id=fx_rate_id)

    monkeypatch.setattr("slaif_gateway.services.fx_rate_service.FxRateService.create_fx_rate", create_fx_rate)
    client = TestClient(_app())
    admin_user = _login_for_actions(monkeypatch, client)

    response = client.post("/admin/fx/new", data=_valid_form(), follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == f"/admin/fx/{fx_rate_id}?message=fx_rate_created"
    assert seen["base_currency"] == "USD"
    assert seen["quote_currency"] == "EUR"
    assert seen["rate"] == Decimal("0.920000000")
    assert seen["source"] == "manual source"
    assert seen["actor_admin_id"] == admin_user.id
    assert seen["reason"] == "fx update"
    assert all(not isinstance(value, float) for value in seen.values())
    assert "api_key_value" not in seen


def test_fx_rate_create_rejects_invalid_fields_before_service(monkeypatch) -> None:
    called = False

    async def create_fx_rate(self, **kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr("slaif_gateway.services.fx_rate_service.FxRateService.create_fx_rate", create_fx_rate)
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    invalid_decimal = client.post("/admin/fx/new", data=_valid_form(rate="not-decimal"))
    zero_rate = client.post("/admin/fx/new", data=_valid_form(rate="0"))
    negative_rate = client.post("/admin/fx/new", data=_valid_form(rate="-0.1"))
    invalid_currency = client.post("/admin/fx/new", data=_valid_form(base_currency="USDX"))
    same_currency = client.post("/admin/fx/new", data=_valid_form(base_currency="EUR", quote_currency="EUR"))
    invalid_window = client.post(
        "/admin/fx/new",
        data=_valid_form(valid_from="2026-02-01T00:00:00+00:00", valid_until="2026-01-01T00:00:00+00:00"),
    )
    secret_source = client.post("/admin/fx/new", data=_valid_form(source="sk-real-looking-secret"))

    assert invalid_decimal.status_code == 400
    assert zero_rate.status_code == 400
    assert negative_rate.status_code == 400
    assert invalid_currency.status_code == 400
    assert same_currency.status_code == 400
    assert invalid_window.status_code == 400
    assert secret_source.status_code == 400
    assert called is False


def test_fx_rate_edit_get_renders_safe_current_values(monkeypatch) -> None:
    fx_rate = _fx_detail()

    async def get_fx_rate_detail(self, fx_rate_id):
        assert fx_rate_id == fx_rate.id
        return fx_rate

    monkeypatch.setattr(
        "slaif_gateway.services.admin_catalog_dashboard.AdminCatalogDashboardService.get_fx_rate_detail",
        get_fx_rate_detail,
    )
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    response = client.get(f"/admin/fx/{fx_rate.id}/edit")

    assert response.status_code == 200
    assert fx_rate.base_currency in response.text
    assert fx_rate.source in response.text
    assert 'name="csrf_token" value="dashboard-csrf"' in response.text
    assert "sk-provider-secret" not in response.text


def test_fx_rate_edit_calls_service_with_actor_and_reason(monkeypatch) -> None:
    seen: dict[str, object] = {}
    fx_rate_id = uuid.uuid4()

    async def update_fx_rate(self, fx_or_id, **kwargs):
        seen["fx_or_id"] = fx_or_id
        seen.update(kwargs)
        return SimpleNamespace(id=fx_rate_id)

    monkeypatch.setattr("slaif_gateway.services.fx_rate_service.FxRateService.update_fx_rate", update_fx_rate)
    client = TestClient(_app())
    admin_user = _login_for_actions(monkeypatch, client)

    response = client.post(
        f"/admin/fx/{fx_rate_id}/edit",
        data=_valid_form(rate="0.930000000"),
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == f"/admin/fx/{fx_rate_id}?message=fx_rate_updated"
    assert seen["fx_or_id"] == fx_rate_id
    assert seen["rate"] == Decimal("0.930000000")
    assert seen["actor_admin_id"] == admin_user.id
    assert seen["reason"] == "fx update"


def test_fx_rate_edit_rejects_secret_source_before_service(monkeypatch) -> None:
    called = False
    fx_rate_id = uuid.uuid4()

    async def update_fx_rate(self, fx_or_id, **kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr("slaif_gateway.services.fx_rate_service.FxRateService.update_fx_rate", update_fx_rate)
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    response = client.post(f"/admin/fx/{fx_rate_id}/edit", data=_valid_form(source="sk-real-looking-secret"))

    assert response.status_code == 400
    assert "Enter valid FX metadata." in response.text
    assert called is False
