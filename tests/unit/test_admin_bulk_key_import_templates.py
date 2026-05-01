from __future__ import annotations

from fastapi.testclient import TestClient

from slaif_gateway.config import Settings

from tests.unit.test_admin_key_actions_routes import _app, _login_for_actions
from tests.unit.test_admin_bulk_key_import_routes import _execution_result, _patch_csrf_refresh as _patch_action_csrf, _valid_csv


def _patch_csrf_refresh(monkeypatch, token: str = "rendered-bulk-key-csrf") -> None:
    async def refresh_csrf_token(self, **kwargs):
        return token

    monkeypatch.setattr(
        "slaif_gateway.services.admin_session_service.AdminSessionService.refresh_csrf_token",
        refresh_csrf_token,
    )


def test_bulk_import_form_template_includes_csrf_and_no_secret_fields(monkeypatch) -> None:
    settings = Settings(
        APP_ENV="test",
        DATABASE_URL="postgresql+asyncpg://user:secret@localhost:5432/test_db",
        ADMIN_SESSION_SECRET="admin-session-secret-that-must-not-render",
        OPENAI_UPSTREAM_API_KEY="sk-provider-secret-placeholder",
        OPENROUTER_API_KEY="sk-or-provider-secret-placeholder",
    )
    client = TestClient(_app(settings))
    _login_for_actions(monkeypatch, client)
    _patch_csrf_refresh(monkeypatch)

    html = client.get("/admin/keys/bulk-import").text

    assert 'method="post" action="/admin/keys/bulk-import/preview"' in html
    assert 'name="csrf_token" value="rendered-bulk-key-csrf"' in html
    assert 'name="import_file"' in html
    assert 'name="import_text"' in html
    assert "Preview only" in html
    assert "no keys are generated" in html
    assert "no email is sent" in html
    assert "token_hash" not in html
    assert "encrypted_payload" not in html
    assert "nonce" not in html
    assert settings.OPENAI_UPSTREAM_API_KEY not in html
    assert settings.OPENROUTER_API_KEY not in html
    assert "password_hash" not in html
    assert "session-token-must-not-render" not in html


def test_key_list_links_to_bulk_import_preview(monkeypatch) -> None:
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)
    _patch_csrf_refresh(monkeypatch, token="dashboard-csrf")

    async def list_keys(self, **kwargs):
        return []

    monkeypatch.setattr(
        "slaif_gateway.services.admin_key_dashboard.AdminKeyDashboardService.list_keys",
        list_keys,
    )

    html = client.get("/admin/keys").text

    assert 'href="/admin/keys/bulk-import"' in html
    assert "Bulk import preview" in html


def test_bulk_import_preview_template_includes_execution_controls(monkeypatch) -> None:
    async def build_preview(request, raw_rows, *, max_rows):
        from tests.unit.test_admin_bulk_key_import_routes import _preview

        return _preview()

    monkeypatch.setattr("slaif_gateway.api.admin._build_key_import_preview", build_preview)
    _patch_action_csrf(monkeypatch)
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    html = client.post(
        "/admin/keys/bulk-import/preview",
        data={"csrf_token": "dashboard-csrf", "import_format": "csv", "import_text": _valid_csv()},
    ).text

    assert 'action="/admin/keys/bulk-import/execute"' in html
    assert 'name="confirm_import"' in html
    assert 'name="confirm_plaintext_display"' in html
    assert 'name="reason"' in html
    assert "will generate gateway keys" in html


def test_bulk_import_result_template_shows_plaintext_once_and_no_secret_fields(monkeypatch) -> None:
    async def build_preview(request, raw_rows, *, max_rows):
        from tests.unit.test_admin_bulk_key_import_routes import _preview

        return _preview()

    async def execute_plan(plan, *, key_service, email_delivery_service):
        return _execution_result()

    monkeypatch.setattr("slaif_gateway.api.admin._build_key_import_preview", build_preview)
    monkeypatch.setattr("slaif_gateway.api.admin.execute_key_import_plan", execute_plan)
    _patch_action_csrf(monkeypatch)
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    response = client.post(
        "/admin/keys/bulk-import/execute",
        data={
            "csrf_token": "dashboard-csrf",
            "import_format": "csv",
            "import_text": _valid_csv(),
            "confirm_import": "true",
            "confirm_plaintext_display": "true",
            "reason": "bulk",
        },
    )
    html = response.text

    assert "Copy these keys now" in html
    assert html.count("sk-slaif-pub_bulk.plaintext-secret") == 1
    assert "owner_email,valid_days" not in html
    assert "sk-provider-secret" not in html
    assert "token_hash" not in html
    assert "encrypted_payload" not in html
    assert "nonce" not in html
    assert "password_hash" not in html
    assert "session-token-must-not-render" not in html
