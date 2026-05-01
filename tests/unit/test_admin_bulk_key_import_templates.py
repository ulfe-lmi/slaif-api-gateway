from __future__ import annotations

from fastapi.testclient import TestClient

from slaif_gateway.config import Settings

from tests.unit.test_admin_key_actions_routes import _app, _login_for_actions


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
