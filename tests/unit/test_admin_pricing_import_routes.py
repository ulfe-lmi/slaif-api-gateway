from __future__ import annotations

from fastapi.testclient import TestClient

from slaif_gateway.services.pricing_import import PricingImportExecutionResult

from tests.unit.test_admin_pricing_actions_routes import _app, _login_for_actions


def _valid_csv(**overrides: str) -> str:
    row = {
        "provider": "openai",
        "model": "gpt-4.1-mini",
        "input_price_per_1m": "0.10",
        "output_price_per_1m": "0.20",
        "notes": "safe note",
    }
    row.update(overrides)
    headers = list(row)
    return ",".join(headers) + "\n" + ",".join(row[name] for name in headers) + "\n"


def test_pricing_import_get_requires_auth() -> None:
    client = TestClient(_app())

    response = client.get("/admin/pricing/import", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/login"


def test_pricing_import_get_renders_csrf_form(monkeypatch) -> None:
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    response = client.get("/admin/pricing/import")

    assert response.status_code == 200
    assert 'name="csrf_token" value="dashboard-csrf"' in response.text
    assert 'enctype="multipart/form-data"' in response.text
    assert "Dry-run only" in response.text


def test_pricing_import_preview_requires_csrf(monkeypatch) -> None:
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    response = client.post(
        "/admin/pricing/import/preview",
        data={"import_format": "csv", "import_text": _valid_csv()},
    )

    assert response.status_code == 400
    assert "Invalid CSRF token." in response.text


def test_pricing_import_preview_rejects_missing_and_conflicting_input(monkeypatch) -> None:
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    missing = client.post(
        "/admin/pricing/import/preview",
        data={"csrf_token": "dashboard-csrf", "import_format": "csv"},
    )
    conflict = client.post(
        "/admin/pricing/import/preview",
        data={
            "csrf_token": "dashboard-csrf",
            "import_format": "csv",
            "import_text": _valid_csv(),
        },
        files={"import_file": ("pricing.csv", _valid_csv(), "text/csv")},
    )

    assert missing.status_code == 400
    assert "Paste pricing content or upload" in missing.text
    assert conflict.status_code == 400
    assert "Use either a file upload or pasted content" in conflict.text


def test_pricing_import_preview_renders_valid_rows_without_mutation(monkeypatch) -> None:
    called = False

    async def create_pricing_rule(self, **kwargs):
        nonlocal called
        called = True

    async def update_pricing_rule(self, *args, **kwargs):
        nonlocal called
        called = True

    async def classify(request, preview):
        return preview

    monkeypatch.setattr(
        "slaif_gateway.services.pricing_rule_service.PricingRuleService.create_pricing_rule",
        create_pricing_rule,
    )
    monkeypatch.setattr(
        "slaif_gateway.services.pricing_rule_service.PricingRuleService.update_pricing_rule",
        update_pricing_rule,
    )
    monkeypatch.setattr("slaif_gateway.api.admin._classify_pricing_import_preview", classify)
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    response = client.post(
        "/admin/pricing/import/preview",
        data={
            "csrf_token": "dashboard-csrf",
            "import_format": "csv",
            "import_text": _valid_csv(notes="<script>alert(1)</script>"),
        },
    )

    assert response.status_code == 200
    assert "Pricing Import Preview Result" in response.text
    assert "Valid rows" in response.text
    assert "Database writes" in response.text
    assert "gpt-4.1-mini" in response.text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in response.text
    assert "<script>alert(1)</script>" not in response.text
    assert "sk-provider-secret" not in response.text
    assert "token_hash" not in response.text
    assert "encrypted_payload" not in response.text
    assert "nonce" not in response.text
    assert "password_hash" not in response.text
    assert "slaif_admin_session" not in response.text
    assert called is False


def test_pricing_import_preview_renders_invalid_row_safely(monkeypatch) -> None:
    async def classify(request, preview):
        return preview

    monkeypatch.setattr("slaif_gateway.api.admin._classify_pricing_import_preview", classify)
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    response = client.post(
        "/admin/pricing/import/preview",
        data={
            "csrf_token": "dashboard-csrf",
            "import_format": "json",
            "import_text": (
                '[{"provider":"openai","model":"gpt-4.1-mini",'
                '"input_price_per_1m":0.10,"output_price_per_1m":"0.20"}]'
            ),
        },
    )

    assert response.status_code == 200
    assert "Invalid rows" in response.text
    assert "decimal string" in response.text
    assert "0.10" not in response.text


def test_pricing_import_execute_requires_csrf_confirmation_and_reason(monkeypatch) -> None:
    called = False

    async def execute(*args, **kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr("slaif_gateway.api.admin.execute_pricing_import_plan", execute)
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    without_csrf = client.post(
        "/admin/pricing/import/execute",
        data={"import_format": "csv", "import_text": _valid_csv(), "confirm_import": "true", "reason": "import"},
    )
    without_confirm = client.post(
        "/admin/pricing/import/execute",
        data={"csrf_token": "dashboard-csrf", "import_format": "csv", "import_text": _valid_csv(), "reason": "import"},
    )
    without_reason = client.post(
        "/admin/pricing/import/execute",
        data={
            "csrf_token": "dashboard-csrf",
            "import_format": "csv",
            "import_text": _valid_csv(),
            "confirm_import": "true",
        },
    )

    assert without_csrf.status_code == 400
    assert "Invalid CSRF token." in without_csrf.text
    assert without_confirm.status_code == 400
    assert "Confirm pricing import execution" in without_confirm.text
    assert without_reason.status_code == 400
    assert "Enter an audit reason" in without_reason.text
    assert called is False


def test_pricing_import_execute_rejects_conflicting_input_before_service(monkeypatch) -> None:
    called = False

    async def execute(*args, **kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr("slaif_gateway.api.admin.execute_pricing_import_plan", execute)
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    response = client.post(
        "/admin/pricing/import/execute",
        data={
            "csrf_token": "dashboard-csrf",
            "import_format": "csv",
            "import_text": _valid_csv(),
            "confirm_import": "true",
            "reason": "pricing import",
        },
        files={"import_file": ("pricing.csv", _valid_csv(), "text/csv")},
    )

    assert response.status_code == 400
    assert "Use either a file upload or pasted content" in response.text
    assert called is False


def test_pricing_import_execute_invalid_content_writes_nothing(monkeypatch) -> None:
    called = False

    async def execute(*args, **kwargs):
        nonlocal called
        called = True

    async def classify(request, preview):
        return preview

    monkeypatch.setattr("slaif_gateway.api.admin.execute_pricing_import_plan", execute)
    monkeypatch.setattr("slaif_gateway.api.admin._classify_pricing_import_preview", classify)
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    response = client.post(
        "/admin/pricing/import/execute",
        data={
            "csrf_token": "dashboard-csrf",
            "import_format": "json",
            "import_text": (
                '[{"provider":"openai","model":"gpt-4.1-mini",'
                '"input_price_per_1m":0.10,"output_price_per_1m":"0.20"}]'
            ),
            "confirm_import": "true",
            "reason": "pricing import",
        },
    )

    assert response.status_code == 400
    assert "Import blocked" in response.text
    assert "decimal string" in response.text
    assert called is False


def test_pricing_import_execute_valid_content_calls_service(monkeypatch) -> None:
    called = False

    async def execute(plan, **kwargs):
        nonlocal called
        called = True
        assert plan.executable is True
        assert kwargs["reason"] == "pricing import"
        return PricingImportExecutionResult(
            total_rows=1,
            created_count=1,
            updated_count=0,
            skipped_count=0,
            error_count=0,
            rows=(),
            audit_summary="Created pricing rules were audited individually.",
        )

    async def classify(request, preview):
        return preview

    monkeypatch.setattr("slaif_gateway.api.admin.execute_pricing_import_plan", execute)
    monkeypatch.setattr("slaif_gateway.api.admin._classify_pricing_import_preview", classify)
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    response = client.post(
        "/admin/pricing/import/execute",
        data={
            "csrf_token": "dashboard-csrf",
            "import_format": "csv",
            "import_text": _valid_csv(notes="<script>alert(1)</script>"),
            "confirm_import": "true",
            "reason": "pricing import",
        },
    )

    assert response.status_code == 200
    assert "Pricing Import Result" in response.text
    assert "Created rows" in response.text
    assert called is True
    assert "<script>alert(1)</script>" not in response.text
    assert "sk-provider-secret" not in response.text
    assert "token_hash" not in response.text
    assert "encrypted_payload" not in response.text
    assert "nonce" not in response.text
    assert "password_hash" not in response.text
    assert "slaif_admin_session" not in response.text
