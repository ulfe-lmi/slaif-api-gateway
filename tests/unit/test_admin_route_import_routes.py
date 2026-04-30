from __future__ import annotations

from fastapi.testclient import TestClient

from slaif_gateway.services.route_import import (
    RouteImportExecutionResult,
    RouteImportPreview,
    RouteImportRowPreview,
)

from tests.unit.test_admin_route_actions_routes import _app, _login_for_actions


def _valid_csv(**overrides: str) -> str:
    row = {
        "requested_model": "gpt-4.1-mini",
        "match_type": "exact",
        "provider": "openai",
        "upstream_model": "gpt-4.1-mini",
        "priority": "10",
        "notes": "safe note",
    }
    row.update(overrides)
    headers = list(row)
    return ",".join(headers) + "\n" + ",".join(row[name] for name in headers) + "\n"


def _preview() -> RouteImportPreview:
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


def test_route_import_get_requires_auth() -> None:
    client = TestClient(_app())

    response = client.get("/admin/routes/import", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/login"


def test_route_import_get_renders_csrf_form(monkeypatch) -> None:
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    response = client.get("/admin/routes/import")

    assert response.status_code == 200
    assert 'name="csrf_token" value="dashboard-csrf"' in response.text
    assert 'enctype="multipart/form-data"' in response.text
    assert "Dry-run only" in response.text
    assert "provider key values are rejected" in response.text


def test_route_import_preview_requires_csrf(monkeypatch) -> None:
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    response = client.post(
        "/admin/routes/import/preview",
        data={"import_format": "csv", "import_text": _valid_csv()},
    )

    assert response.status_code == 400
    assert "Invalid CSRF token." in response.text


def test_route_import_preview_rejects_missing_and_conflicting_input(monkeypatch) -> None:
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    missing = client.post(
        "/admin/routes/import/preview",
        data={"csrf_token": "dashboard-csrf", "import_format": "csv"},
    )
    conflict = client.post(
        "/admin/routes/import/preview",
        data={
            "csrf_token": "dashboard-csrf",
            "import_format": "csv",
            "import_text": _valid_csv(),
        },
        files={"import_file": ("routes.csv", _valid_csv(), "text/csv")},
    )

    assert missing.status_code == 400
    assert "Paste route content or upload" in missing.text
    assert conflict.status_code == 400
    assert "Use either a file upload or pasted content" in conflict.text


def test_route_import_preview_renders_valid_rows_without_mutation(monkeypatch) -> None:
    called = False

    async def create_model_route(self, **kwargs):
        nonlocal called
        called = True

    async def update_model_route(self, *args, **kwargs):
        nonlocal called
        called = True

    async def build_preview(request, raw_rows, *, max_rows):
        return _preview()

    monkeypatch.setattr(
        "slaif_gateway.services.model_route_service.ModelRouteService.create_model_route",
        create_model_route,
    )
    monkeypatch.setattr(
        "slaif_gateway.services.model_route_service.ModelRouteService.update_model_route",
        update_model_route,
    )
    monkeypatch.setattr("slaif_gateway.api.admin._build_route_import_preview", build_preview)
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    response = client.post(
        "/admin/routes/import/preview",
        data={
            "csrf_token": "dashboard-csrf",
            "import_format": "csv",
            "import_text": _valid_csv(notes="<script>alert(1)</script>"),
        },
    )

    assert response.status_code == 200
    assert "Route Import Preview Result" in response.text
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


def test_route_import_preview_renders_parser_errors_safely(monkeypatch) -> None:
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    response = client.post(
        "/admin/routes/import/preview",
        data={
            "csrf_token": "dashboard-csrf",
            "import_format": "json",
            "import_text": '{"provider":"openai"}',
        },
    )

    assert response.status_code == 400
    assert "Route JSON import must be a list of objects" in response.text
    assert "sk-provider-secret" not in response.text


def test_route_import_execute_requires_csrf_confirmation_and_reason(monkeypatch) -> None:
    called = False

    async def execute(*args, **kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr("slaif_gateway.api.admin.execute_route_import_plan", execute)
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    without_csrf = client.post(
        "/admin/routes/import/execute",
        data={"import_format": "csv", "import_text": _valid_csv(), "confirm_import": "true", "reason": "import"},
    )
    without_confirm = client.post(
        "/admin/routes/import/execute",
        data={"csrf_token": "dashboard-csrf", "import_format": "csv", "import_text": _valid_csv(), "reason": "import"},
    )
    without_reason = client.post(
        "/admin/routes/import/execute",
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
    assert "Confirm route import execution" in without_confirm.text
    assert without_reason.status_code == 400
    assert "Enter an audit reason" in without_reason.text
    assert called is False


def test_route_import_execute_rejects_conflicting_input_before_service(monkeypatch) -> None:
    called = False

    async def execute(*args, **kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr("slaif_gateway.api.admin.execute_route_import_plan", execute)
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    response = client.post(
        "/admin/routes/import/execute",
        data={
            "csrf_token": "dashboard-csrf",
            "import_format": "csv",
            "import_text": _valid_csv(),
            "confirm_import": "true",
            "reason": "route import",
        },
        files={"import_file": ("routes.csv", _valid_csv(), "text/csv")},
    )

    assert response.status_code == 400
    assert "Use either a file upload or pasted content" in response.text
    assert called is False


def test_route_import_execute_invalid_content_writes_nothing(monkeypatch) -> None:
    called = False

    async def execute(*args, **kwargs):
        nonlocal called
        called = True

    async def build_preview(request, raw_rows, *, max_rows):
        return RouteImportPreview(
            total_rows=1,
            valid_count=0,
            invalid_count=1,
            rows=(
                RouteImportRowPreview(
                    row_number=1,
                    status="invalid",
                    classification="invalid",
                    errors=("match_type must be one of: exact, prefix, glob",),
                ),
            ),
        )

    monkeypatch.setattr("slaif_gateway.api.admin._build_route_import_preview", build_preview)
    monkeypatch.setattr("slaif_gateway.api.admin.execute_route_import_plan", execute)
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    response = client.post(
        "/admin/routes/import/execute",
        data={
            "csrf_token": "dashboard-csrf",
            "import_format": "json",
            "import_text": (
                '[{"requested_model":"gpt-4.1-mini","match_type":"regex",'
                '"provider":"openai","upstream_model":"gpt-4.1-mini"}]'
            ),
            "confirm_import": "true",
            "reason": "route import",
        },
    )

    assert response.status_code == 400
    assert "Import blocked" in response.text
    assert "match_type must be one of" in response.text
    assert called is False


def test_route_import_execute_valid_content_calls_service(monkeypatch) -> None:
    called = False

    async def build_preview(request, raw_rows, *, max_rows):
        return _preview()

    async def execute(plan, **kwargs):
        nonlocal called
        called = True
        assert plan.executable is True
        assert kwargs["reason"] == "route import"
        return RouteImportExecutionResult(
            total_rows=1,
            created_count=1,
            updated_count=0,
            skipped_count=0,
            error_count=0,
            rows=(),
            audit_summary="Created model route rows were audited individually.",
        )

    monkeypatch.setattr("slaif_gateway.api.admin._build_route_import_preview", build_preview)
    monkeypatch.setattr("slaif_gateway.api.admin.execute_route_import_plan", execute)
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    response = client.post(
        "/admin/routes/import/execute",
        data={
            "csrf_token": "dashboard-csrf",
            "import_format": "csv",
            "import_text": _valid_csv(notes="<script>alert(1)</script>"),
            "confirm_import": "true",
            "reason": "route import",
        },
    )

    assert response.status_code == 200
    assert "Route Import Result" in response.text
    assert "Created rows" in response.text
    assert called is True
    assert "<script>alert(1)</script>" not in response.text
    assert "sk-provider-secret" not in response.text
    assert "token_hash" not in response.text
    assert "encrypted_payload" not in response.text
    assert "nonce" not in response.text
    assert "password_hash" not in response.text
    assert "slaif_admin_session" not in response.text
