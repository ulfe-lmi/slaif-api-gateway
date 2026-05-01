from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from slaif_gateway.services.key_import import (
    KeyImportExecutionResult,
    KeyImportExecutionRow,
    KeyImportPreview,
    KeyImportRowPreview,
)

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


def _preview(*, valid: bool = True, email_delivery_mode: str = "none") -> KeyImportPreview:
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
        allowed_providers=(),
        email_delivery_mode=email_delivery_mode,
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


def _execution_result(*, plaintext: bool = True) -> KeyImportExecutionResult:
    key_id = uuid.UUID("22222222-2222-4222-8222-222222222222")
    row = KeyImportExecutionRow(
        row_number=1,
        action="created",
        owner_id=uuid.UUID("11111111-1111-4111-8111-111111111111"),
        owner_email="ada@example.org",
        owner_name="Ada Lovelace",
        gateway_key_id=key_id,
        public_key_id="pub_bulk",
        display_prefix="sk-slaif-pub_bulk",
        one_time_secret_id=uuid.UUID("33333333-3333-4333-8333-333333333333"),
        email_delivery_mode="none",
        valid_from=datetime(2026, 1, 1, tzinfo=UTC),
        valid_until=datetime(2026, 2, 1, tzinfo=UTC),
        cost_limit_eur="10.00",
        token_limit=100000,
        request_limit=1000,
        allowed_models=("gpt-test",),
        allowed_endpoints=("/v1/chat/completions",),
        plaintext_key="sk-slaif-pub_bulk.plaintext-secret" if plaintext else None,
    )
    return KeyImportExecutionResult(
        total_rows=1,
        created_count=1,
        invalid_count=0,
        rows=(row,),
        plaintext_display_count=1 if plaintext else 0,
    )


def _enqueue_execution_result() -> KeyImportExecutionResult:
    row = KeyImportExecutionRow(
        row_number=1,
        action="created",
        owner_id=uuid.UUID("11111111-1111-4111-8111-111111111111"),
        owner_email="ada@example.org",
        owner_name="Ada Lovelace",
        gateway_key_id=uuid.UUID("22222222-2222-4222-8222-222222222222"),
        public_key_id="pub_bulk",
        display_prefix="sk-slaif-pub_bulk",
        one_time_secret_id=uuid.UUID("33333333-3333-4333-8333-333333333333"),
        email_delivery_id=uuid.UUID("44444444-4444-4444-8444-444444444444"),
        email_delivery_mode="enqueue",
        email_delivery_status="pending",
        enqueue_status="pending",
        valid_from=datetime(2026, 1, 1, tzinfo=UTC),
        valid_until=datetime(2026, 2, 1, tzinfo=UTC),
    )
    return KeyImportExecutionResult(
        total_rows=1,
        created_count=1,
        invalid_count=0,
        rows=(row,),
        plaintext_display_count=0,
        pending_email_delivery_count=1,
    )


def test_bulk_key_import_execute_requires_auth_and_csrf(monkeypatch) -> None:
    client = TestClient(_app())
    unauthenticated = client.post("/admin/keys/bulk-import/execute", follow_redirects=False)
    assert unauthenticated.status_code == 303
    assert unauthenticated.headers["location"] == "/admin/login"

    _login_for_actions(monkeypatch, client)
    without_csrf = client.post(
        "/admin/keys/bulk-import/execute",
        data={"import_format": "csv", "import_text": _valid_csv()},
    )
    assert without_csrf.status_code == 400
    assert "Invalid CSRF token." in without_csrf.text


def test_bulk_key_import_execute_requires_confirmation_reason_and_plaintext_confirmation(monkeypatch) -> None:
    async def build_preview(request, raw_rows, *, max_rows):
        return _preview()

    monkeypatch.setattr("slaif_gateway.api.admin._build_key_import_preview", build_preview)
    _patch_csrf_refresh(monkeypatch)
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    missing_confirm = client.post(
        "/admin/keys/bulk-import/execute",
        data={"csrf_token": "dashboard-csrf", "import_format": "csv", "import_text": _valid_csv(), "reason": "bulk"},
    )
    missing_reason = client.post(
        "/admin/keys/bulk-import/execute",
        data={
            "csrf_token": "dashboard-csrf",
            "import_format": "csv",
            "import_text": _valid_csv(),
            "confirm_import": "true",
            "confirm_plaintext_display": "true",
        },
    )
    missing_plaintext = client.post(
        "/admin/keys/bulk-import/execute",
        data={
            "csrf_token": "dashboard-csrf",
            "import_format": "csv",
            "import_text": _valid_csv(),
            "confirm_import": "true",
            "reason": "bulk",
        },
    )

    assert missing_confirm.status_code == 400
    assert "Confirm bulk key import" in missing_confirm.text
    assert missing_reason.status_code == 400
    assert "audit reason" in missing_reason.text
    assert missing_plaintext.status_code == 400
    assert "one-time plaintext display" in missing_plaintext.text


def test_bulk_key_import_execute_rejects_invalid_content_without_service_mutation(monkeypatch) -> None:
    called = False

    async def create_gateway_key(self, payload):
        nonlocal called
        called = True

    async def build_preview(request, raw_rows, *, max_rows):
        return _preview(valid=False)

    monkeypatch.setattr("slaif_gateway.services.key_service.KeyService.create_gateway_key", create_gateway_key)
    monkeypatch.setattr("slaif_gateway.api.admin._build_key_import_preview", build_preview)
    _patch_csrf_refresh(monkeypatch)
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

    assert response.status_code == 400
    assert "All rows must validate" in response.text
    assert called is False


def test_bulk_key_import_execute_calls_execution_service_and_returns_no_cache_result(monkeypatch) -> None:
    called = False

    async def build_preview(request, raw_rows, *, max_rows):
        return _preview()

    async def execute_plan(plan, *, key_service, email_delivery_service):
        nonlocal called
        called = True
        assert plan.reason == "bulk"
        return _execution_result()

    monkeypatch.setattr("slaif_gateway.api.admin._build_key_import_preview", build_preview)
    monkeypatch.setattr("slaif_gateway.api.admin.execute_key_import_plan", execute_plan)
    _patch_csrf_refresh(monkeypatch)
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

    assert response.status_code == 200
    assert called is True
    assert response.headers["Cache-Control"] == "no-store, no-cache, must-revalidate"
    assert response.headers["Pragma"] == "no-cache"
    assert "Bulk Key Import Result" in response.text
    assert response.text.count("sk-slaif-pub_bulk.plaintext-secret") == 1
    assert "token_hash" not in response.text
    assert "encrypted_payload" not in response.text
    assert "nonce" not in response.text
    assert "password_hash" not in response.text


def test_bulk_key_import_execute_accepts_enqueue_and_queues_ids_only(monkeypatch) -> None:
    queued: list[dict[str, object]] = []

    async def build_preview(request, raw_rows, *, max_rows):
        return _preview(email_delivery_mode="enqueue")

    async def execute_plan(plan, *, key_service, email_delivery_service):
        assert plan.plaintext_display_required is False
        return _enqueue_execution_result()

    def enqueue_func(**kwargs):
        queued.append(kwargs)
        return "task-123"

    monkeypatch.setattr("slaif_gateway.api.admin._build_key_import_preview", build_preview)
    monkeypatch.setattr("slaif_gateway.api.admin.execute_key_import_plan", execute_plan)
    monkeypatch.setattr("slaif_gateway.api.admin._enqueue_admin_pending_key_email", enqueue_func)
    _patch_csrf_refresh(monkeypatch)
    client = TestClient(_app())
    admin_user = _login_for_actions(monkeypatch, client)

    response = client.post(
        "/admin/keys/bulk-import/execute",
        data={
            "csrf_token": "dashboard-csrf",
            "import_format": "csv",
            "import_text": _valid_csv(email_delivery_mode="enqueue"),
            "confirm_import": "true",
            "reason": "bulk",
        },
    )

    assert response.status_code == 200
    assert queued == [
        {
            "one_time_secret_id": uuid.UUID("33333333-3333-4333-8333-333333333333"),
            "email_delivery_id": uuid.UUID("44444444-4444-4444-8444-444444444444"),
            "actor_admin_id": admin_user.id,
        }
    ]
    assert "task-123" in response.text
    assert "sk-slaif-pub_bulk.plaintext-secret" not in response.text
    assert "encrypted_payload" not in response.text


def test_bulk_key_import_execute_rejects_send_now_before_mutation(monkeypatch) -> None:
    called = False

    async def execute_plan(plan, *, key_service, email_delivery_service):
        nonlocal called
        called = True
        return _execution_result()

    async def build_preview(request, raw_rows, *, max_rows):
        return _preview(email_delivery_mode="send-now")

    monkeypatch.setattr("slaif_gateway.api.admin._build_key_import_preview", build_preview)
    monkeypatch.setattr("slaif_gateway.api.admin.execute_key_import_plan", execute_plan)
    _patch_csrf_refresh(monkeypatch)
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    response = client.post(
        "/admin/keys/bulk-import/execute",
        data={
            "csrf_token": "dashboard-csrf",
            "import_format": "csv",
            "import_text": _valid_csv(email_delivery_mode="send-now"),
            "confirm_import": "true",
            "confirm_plaintext_display": "true",
            "reason": "bulk",
        },
    )

    assert response.status_code == 400
    assert "send-now email delivery is not implemented" in response.text
    assert called is False


def test_bulk_key_import_execute_rejects_conflicting_input(monkeypatch) -> None:
    _patch_csrf_refresh(monkeypatch)
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
        files={"import_file": ("keys.csv", _valid_csv(), "text/csv")},
    )

    assert response.status_code == 400
    assert "Use either a file upload or pasted content" in response.text
