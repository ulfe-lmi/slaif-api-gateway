from __future__ import annotations

from fastapi.testclient import TestClient

from slaif_gateway.services.pricing_import import PricingImportExecutionResult, PricingImportExecutionRow

from tests.unit.test_admin_pricing_actions_routes import _app, _login_for_actions


def test_pricing_import_template_includes_dry_run_limits_and_csrf(monkeypatch) -> None:
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    response = client.get("/admin/pricing/import")

    assert response.status_code == 200
    assert "Dry-run only" in response.text
    assert "Execute Import" in response.text
    assert 'name="confirm_import" value="true"' in response.text
    assert 'name="reason"' in response.text
    assert "Maximum 1048576 bytes and 1000 rows" in response.text
    assert 'name="csrf_token" value="dashboard-csrf"' in response.text
    assert "provider key values" not in response.text.lower()


def test_pricing_import_preview_template_keeps_preview_no_mutation(monkeypatch) -> None:
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
    assert "resubmit the original file or pasted content" in response.text


def test_pricing_import_execute_result_template_is_safe(monkeypatch) -> None:
    async def classify(request, preview):
        return preview

    async def execute(plan, **kwargs):
        return PricingImportExecutionResult(
            total_rows=1,
            created_count=1,
            updated_count=0,
            skipped_count=0,
            error_count=0,
            rows=(
                PricingImportExecutionRow(
                    row_number=1,
                    action="created",
                    status="created",
                    provider="openai",
                    model="gpt-4.1-mini",
                    endpoint="/v1/chat/completions",
                    currency="EUR",
                    input_price_per_1m="0.10",
                    output_price_per_1m="0.20",
                    notes="<script>alert(1)</script>",
                ),
            ),
            audit_summary="Created pricing rules were audited individually.",
        )

    monkeypatch.setattr("slaif_gateway.api.admin._classify_pricing_import_preview", classify)
    monkeypatch.setattr("slaif_gateway.api.admin.execute_pricing_import_plan", execute)
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    response = client.post(
        "/admin/pricing/import/execute",
        data={
            "csrf_token": "dashboard-csrf",
            "import_format": "csv",
            "import_text": (
                "provider,model,input_price_per_1m,output_price_per_1m,notes\n"
                "openai,gpt-4.1-mini,0.10,0.20,<script>alert(1)</script>\n"
            ),
            "confirm_import": "true",
            "reason": "pricing import",
        },
    )

    assert response.status_code == 200
    assert "Pricing Import Result" in response.text
    assert "Pricing import completed" in response.text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in response.text
    assert "<script>alert(1)</script>" not in response.text
    assert "provider,model,input_price_per_1m" not in response.text
    assert "token_hash" not in response.text
    assert "encrypted_payload" not in response.text
    assert "nonce" not in response.text
    assert "password_hash" not in response.text
    assert "slaif_admin_session" not in response.text
