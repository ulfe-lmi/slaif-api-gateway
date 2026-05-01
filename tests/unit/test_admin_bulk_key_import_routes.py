from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from slaif_gateway.services.key_import import KeyImportPreview, KeyImportRowPreview

from tests.unit.test_admin_key_actions_routes import _app, _login_for_actions


def _patch_csrf_refresh(monkeypatch) -> None:
    async def refresh_csrf_token(self, **kwargs):
        return "dashboard-csrf"

    monkeypatch.setattr(
        "slaif_gateway.services.admin_session_service.AdminSessionService.refresh_csrf_token",
        refresh_csrf_token,
    )


def _valid_csv(**overrides: str) -> str:
    row = {
        "owner_email": "ada@example.org",
        "valid_days": "30",
        "cost_limit_eur": "10.00",
        "token_limit_total": "100000",
        "request_limit_total": "1000",
        "email_delivery_mode": "none",
    }
    row.update(overrides)
    headers = list(row)
    return ",".join(headers) + "\n" + ",".join(row[name] for name in headers) + "\n"


def _preview(*, valid: bool = True) -> KeyImportPreview:
    owner_id = uuid.UUID("11111111-1111-4111-8111-111111111111")
    valid_from = datetime(2026, 1, 1, tzinfo=UTC)
    row = KeyImportRowPreview(
        row_number=1,
        status="valid" if valid else "invalid",
        classification="create" if valid else "invalid",
        owner_id=owner_id if valid else None,
        owner_email="ada@example.org" if valid else None,
        owner_name="Ada Lovelace" if valid else None,
        institution_name="SLAIF" if valid else None,
        valid_from=valid_from if valid else None,
        valid_until=valid_from + timedelta(days=30) if valid else None,
        cost_limit_eur="10.00" if valid else None,
        token_limit=100000 if valid else None,
        request_limit=1000 if valid else None,
        allowed_models=("gpt-test",) if valid else (),
        allowed_endpoints=("/v1/chat/completions",) if valid else (),
        allowed_providers=("openai",) if valid else (),
        email_delivery_mode="none",
        note="&lt;script&gt;" if valid else None,
        errors=() if valid else ("owner_id must reference an existing owner",),
    )
    return KeyImportPreview(
        total_rows=1,
        valid_count=1 if valid else 0,
        invalid_count=0 if valid else 1,
        rows=(row,),
    )


def test_bulk_key_import_get_requires_auth() -> None:
    client = TestClient(_app())

    response = client.get("/admin/keys/bulk-import", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/login"


def test_bulk_key_import_get_renders_csrf_form(monkeypatch) -> None:
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)
    _patch_csrf_refresh(monkeypatch)

    response = client.get("/admin/keys/bulk-import")

    assert response.status_code == 200
    assert 'name="csrf_token" value="dashboard-csrf"' in response.text
    assert 'enctype="multipart/form-data"' in response.text
    assert "Dry-run only" in response.text
    assert "no keys are generated" in response.text
    assert "token_hash" not in response.text
    assert "sk-provider-secret" not in response.text


def test_bulk_key_import_preview_requires_csrf(monkeypatch) -> None:
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    response = client.post(
        "/admin/keys/bulk-import/preview",
        data={"import_format": "csv", "import_text": _valid_csv()},
    )

    assert response.status_code == 400
    assert "Invalid CSRF token." in response.text


def test_bulk_key_import_preview_rejects_missing_and_conflicting_input(monkeypatch) -> None:
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    missing = client.post(
        "/admin/keys/bulk-import/preview",
        data={"csrf_token": "dashboard-csrf", "import_format": "csv"},
    )
    conflict = client.post(
        "/admin/keys/bulk-import/preview",
        data={
            "csrf_token": "dashboard-csrf",
            "import_format": "csv",
            "import_text": _valid_csv(),
        },
        files={"import_file": ("keys.csv", _valid_csv(), "text/csv")},
    )

    assert missing.status_code == 400
    assert "Paste key import content or upload" in missing.text
    assert conflict.status_code == 400
    assert "Use either a file upload or pasted content" in conflict.text


def test_bulk_key_import_preview_renders_valid_rows_without_mutation(monkeypatch) -> None:
    called = False

    async def create_gateway_key(self, payload):
        nonlocal called
        called = True

    async def build_preview(request, raw_rows, *, max_rows):
        return _preview()

    monkeypatch.setattr("slaif_gateway.services.key_service.KeyService.create_gateway_key", create_gateway_key)
    monkeypatch.setattr("slaif_gateway.api.admin._build_key_import_preview", build_preview)
    _patch_csrf_refresh(monkeypatch)
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    response = client.post(
        "/admin/keys/bulk-import/preview",
        data={
            "csrf_token": "dashboard-csrf",
            "import_format": "csv",
            "import_text": _valid_csv(note="<script>alert(1)</script>"),
        },
    )

    assert response.status_code == 200
    assert "Bulk Key Import Preview Result" in response.text
    assert "Valid rows" in response.text
    assert "No plaintext gateway keys were generated" in response.text
    assert "Ada Lovelace" in response.text
    assert "<script>alert(1)</script>" not in response.text
    assert "token_hash" not in response.text
    assert "encrypted_payload" not in response.text
    assert "nonce" not in response.text
    assert "password_hash" not in response.text
    assert "slaif_admin_session" not in response.text
    assert called is False


def test_bulk_key_import_preview_renders_invalid_rows_safely(monkeypatch) -> None:
    async def build_preview(request, raw_rows, *, max_rows):
        return _preview(valid=False)

    monkeypatch.setattr("slaif_gateway.api.admin._build_key_import_preview", build_preview)
    _patch_csrf_refresh(monkeypatch)
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    response = client.post(
        "/admin/keys/bulk-import/preview",
        data={
            "csrf_token": "dashboard-csrf",
            "import_format": "json",
            "import_text": '[{"owner_id":"00000000-0000-4000-8000-000000000001","valid_days":"30"}]',
        },
    )

    assert response.status_code == 200
    assert "Invalid rows" in response.text
    assert "owner_id must reference an existing owner" in response.text
    assert "sk-provider-secret" not in response.text


def test_bulk_key_import_preview_parses_before_service_call(monkeypatch) -> None:
    called = False

    async def build_preview(request, raw_rows, *, max_rows):
        nonlocal called
        called = True
        return _preview()

    monkeypatch.setattr("slaif_gateway.api.admin._build_key_import_preview", build_preview)
    _patch_csrf_refresh(monkeypatch)
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    response = client.post(
        "/admin/keys/bulk-import/preview",
        data={
            "csrf_token": "dashboard-csrf",
            "import_format": "json",
            "import_text": '[{"owner_email":"ada@example.org","valid_days":"30"}]',
        },
    )

    assert response.status_code == 200
    assert called is True


def test_bulk_key_import_preview_does_not_call_email_celery_or_providers(monkeypatch) -> None:
    async def build_preview(request, raw_rows, *, max_rows):
        return _preview()

    monkeypatch.setattr("slaif_gateway.api.admin._build_key_import_preview", build_preview)
    _patch_csrf_refresh(monkeypatch)
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    response = client.post(
        "/admin/keys/bulk-import/preview",
        data={
            "csrf_token": "dashboard-csrf",
            "import_format": "csv",
            "import_text": _valid_csv(),
        },
    )

    assert response.status_code == 200
    assert "email delivery rows" in response.text
    assert "providers" in response.text
    assert "Celery tasks" in response.text
