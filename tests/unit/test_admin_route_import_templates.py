from __future__ import annotations

from fastapi.testclient import TestClient

from slaif_gateway.services.route_import import RouteImportPreview, RouteImportRowPreview

from tests.unit.test_admin_route_actions_routes import _app, _login_for_actions


def test_route_import_template_includes_dry_run_limits_and_csrf(monkeypatch) -> None:
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    response = client.get("/admin/routes/import")

    assert response.status_code == 200
    assert "Dry-run only" in response.text
    assert "Maximum 1048576 bytes and 1000 rows" in response.text
    assert 'name="csrf_token" value="dashboard-csrf"' in response.text
    assert "provider key values are rejected" in response.text


def test_route_import_preview_template_is_no_mutation_and_safe(monkeypatch) -> None:
    async def build_preview(request, raw_rows, *, max_rows):
        return RouteImportPreview(
            total_rows=1,
            valid_count=1,
            invalid_count=0,
            rows=(
                RouteImportRowPreview(
                    row_number=1,
                    status="valid",
                    classification="create",
                    requested_model="gpt-4.1-mini",
                    match_type="exact",
                    endpoint="/v1/chat/completions",
                    provider="openai",
                    upstream_model="gpt-4.1-mini",
                    priority=10,
                    enabled=True,
                    visible_in_models=True,
                    supports_streaming=True,
                    capabilities={"vision": False},
                    notes="<script>alert(1)</script>",
                ),
            ),
        )

    monkeypatch.setattr("slaif_gateway.api.admin._build_route_import_preview", build_preview)
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    response = client.post(
        "/admin/routes/import/preview",
        data={
            "csrf_token": "dashboard-csrf",
            "import_format": "csv",
            "import_text": (
                "requested_model,match_type,provider,upstream_model,notes\n"
                "gpt-4.1-mini,exact,openai,gpt-4.1-mini,<script>alert(1)</script>\n"
            ),
        },
    )

    assert response.status_code == 200
    assert "Dry-run only" in response.text
    assert "No model route rows were written" in response.text
    assert "route resolution changes" in response.text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in response.text
    assert "<script>alert(1)</script>" not in response.text
    assert "provider key values" not in response.text.lower()
    assert "token_hash" not in response.text
    assert "encrypted_payload" not in response.text
    assert "nonce" not in response.text
    assert "password_hash" not in response.text
    assert "slaif_admin_session" not in response.text
