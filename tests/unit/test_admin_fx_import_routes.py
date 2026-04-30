from __future__ import annotations

from fastapi.testclient import TestClient

from tests.unit.test_admin_fx_actions_routes import _app, _login_for_actions


def _valid_csv(**overrides: str) -> str:
    row = {
        "base_currency": "USD",
        "quote_currency": "EUR",
        "rate": "0.920000000",
        "valid_from": "2026-01-01T00:00:00+00:00",
        "source": "safe source",
        "notes": "safe note",
    }
    row.update(overrides)
    headers = list(row)
    return ",".join(headers) + "\n" + ",".join(row[name] for name in headers) + "\n"


def test_fx_import_get_requires_auth() -> None:
    client = TestClient(_app())

    response = client.get("/admin/fx/import", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/login"


def test_fx_import_get_renders_csrf_form(monkeypatch) -> None:
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    response = client.get("/admin/fx/import")

    assert response.status_code == 200
    assert 'name="csrf_token" value="dashboard-csrf"' in response.text
    assert 'enctype="multipart/form-data"' in response.text
    assert "Dry-run only" in response.text
    assert "external FX services" in response.text
    assert "provider key values" not in response.text
    assert "sk-provider-secret" not in response.text


def test_fx_import_preview_requires_csrf(monkeypatch) -> None:
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    response = client.post(
        "/admin/fx/import/preview",
        data={"import_format": "csv", "import_text": _valid_csv()},
    )

    assert response.status_code == 400
    assert "Invalid CSRF token." in response.text


def test_fx_import_preview_rejects_missing_and_conflicting_input(monkeypatch) -> None:
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    missing = client.post(
        "/admin/fx/import/preview",
        data={"csrf_token": "dashboard-csrf", "import_format": "csv"},
    )
    conflict = client.post(
        "/admin/fx/import/preview",
        data={
            "csrf_token": "dashboard-csrf",
            "import_format": "csv",
            "import_text": _valid_csv(),
        },
        files={"import_file": ("fx.csv", _valid_csv(), "text/csv")},
    )

    assert missing.status_code == 400
    assert "Paste FX content or upload" in missing.text
    assert conflict.status_code == 400
    assert "Use either a file upload or pasted content" in conflict.text


def test_fx_import_preview_renders_valid_rows_without_mutation(monkeypatch) -> None:
    called = False

    async def create_fx_rate(self, **kwargs):
        nonlocal called
        called = True

    async def update_fx_rate(self, *args, **kwargs):
        nonlocal called
        called = True

    async def classify(request, preview):
        return preview

    monkeypatch.setattr("slaif_gateway.services.fx_rate_service.FxRateService.create_fx_rate", create_fx_rate)
    monkeypatch.setattr("slaif_gateway.services.fx_rate_service.FxRateService.update_fx_rate", update_fx_rate)
    monkeypatch.setattr("slaif_gateway.api.admin._classify_fx_import_preview", classify)
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    response = client.post(
        "/admin/fx/import/preview",
        data={
            "csrf_token": "dashboard-csrf",
            "import_format": "csv",
            "import_text": _valid_csv(notes="<script>alert(1)</script>"),
        },
    )

    assert response.status_code == 200
    assert "FX Import Preview Result" in response.text
    assert "Valid rows" in response.text
    assert "Database writes" in response.text
    assert "USD / EUR" in response.text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in response.text
    assert "<script>alert(1)</script>" not in response.text
    assert "sk-provider-secret" not in response.text
    assert "token_hash" not in response.text
    assert "encrypted_payload" not in response.text
    assert "nonce" not in response.text
    assert "password_hash" not in response.text
    assert "slaif_admin_session" not in response.text
    assert called is False


def test_fx_import_preview_renders_invalid_rows_safely(monkeypatch) -> None:
    async def classify(request, preview):
        return preview

    monkeypatch.setattr("slaif_gateway.api.admin._classify_fx_import_preview", classify)
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    response = client.post(
        "/admin/fx/import/preview",
        data={
            "csrf_token": "dashboard-csrf",
            "import_format": "json",
            "import_text": '[{"base_currency":"USD","quote_currency":"EUR","rate":0.92}]',
        },
    )

    assert response.status_code == 200
    assert "Invalid rows" in response.text
    assert "rate must be a decimal string" in response.text
    assert "0.92" not in response.text


def test_fx_import_preview_does_not_call_external_fx_or_providers(monkeypatch) -> None:
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
            "import_text": _valid_csv(source="manual import"),
        },
    )

    assert response.status_code == 200
    assert "External FX APIs and providers were not called" in response.text
