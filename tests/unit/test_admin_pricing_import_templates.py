from __future__ import annotations

from fastapi.testclient import TestClient

from tests.unit.test_admin_pricing_actions_routes import _app, _login_for_actions


def test_pricing_import_template_includes_dry_run_limits_and_csrf(monkeypatch) -> None:
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    response = client.get("/admin/pricing/import")

    assert response.status_code == 200
    assert "Dry-run only" in response.text
    assert "Maximum 1048576 bytes and 1000 rows" in response.text
    assert 'name="csrf_token" value="dashboard-csrf"' in response.text
    assert "provider key values" not in response.text.lower()


def test_pricing_import_preview_template_has_no_execution_form(monkeypatch) -> None:
    async def classify(request, preview):
        return preview

    monkeypatch.setattr("slaif_gateway.api.admin._classify_pricing_import_preview", classify)
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    response = client.post(
        "/admin/pricing/import/preview",
        data={
            "csrf_token": "dashboard-csrf",
            "import_format": "csv",
            "import_text": (
                "provider,model,input_price_per_1m,output_price_per_1m\n"
                "openai,gpt-4.1-mini,0.10,0.20\n"
            ),
        },
    )

    assert response.status_code == 200
    assert "Dry-run only" in response.text
    assert "No pricing rows were written" in response.text
    assert "Create pricing rule" not in response.text
    assert "Import pricing" not in response.text
