from __future__ import annotations

from fastapi.testclient import TestClient

from tests.unit.test_admin_fx_actions_routes import _app, _login_for_actions


def test_fx_import_template_includes_dry_run_limits_and_csrf(monkeypatch) -> None:
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    response = client.get("/admin/fx/import")

    assert response.status_code == 200
    assert "Dry-run only" in response.text
    assert "1048576 bytes" in response.text
    assert "1000 rows" in response.text
    assert 'name="csrf_token" value="dashboard-csrf"' in response.text
    assert "external FX services" in response.text
    assert "provider key values" not in response.text.lower()


def test_fx_import_preview_template_is_no_mutation_and_safe(monkeypatch) -> None:
    async def classify(request, preview):
        return preview

    monkeypatch.setattr("slaif_gateway.api.admin._classify_fx_import_preview", classify)
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    response = client.post(
        "/admin/fx/import/preview",
        data={
            "csrf_token": "dashboard-csrf",
            "import_format": "csv",
            "import_text": (
                "base_currency,quote_currency,rate,valid_from,notes\n"
                "USD,EUR,0.920000000,2026-01-01T00:00:00+00:00,<script>alert(1)</script>\n"
            ),
        },
    )

    assert response.status_code == 200
    assert "Dry-run only" in response.text
    assert "No fx_rates rows were written" in response.text
    assert "External FX APIs and providers were not called" in response.text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in response.text
    assert "<script>alert(1)</script>" not in response.text
    assert "provider key values" not in response.text.lower()
    assert "base_currency,quote_currency,rate" not in response.text
    assert "token_hash" not in response.text
    assert "encrypted_payload" not in response.text
    assert "nonce" not in response.text
    assert "password_hash" not in response.text
    assert "slaif_admin_session" not in response.text
