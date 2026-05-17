from __future__ import annotations

from dataclasses import dataclass

from fastapi.testclient import TestClient

from slaif_gateway.services.openai_assisted_catalog import OpenAIAssistedProposalTextResult

from tests.unit.test_admin_pricing_actions_routes import _app, _login_for_actions, _settings as _app_settings


FAKE_DISCOVERY_KEY = "sk-admin-discovery-secret-must-not-render-123456"
FAKE_PROVIDER_KEY = "sk-provider-secret-must-not-render-123456"
FAKE_GATEWAY_KEY = "sk-slaif-user-secret-must-not-render"
FAKE_BEARER = "Bearer sk-slaif-authorization-secret-must-not-render"
FAKE_CSRF = "csrf_token_fake_should_only_be_form_field"
FAKE_SESSION = "session_token_fake_should_not_render"
RAW_MODEL_RESPONSE_TEXT = "raw model response text must not render"


@dataclass
class _LogEvent:
    event: str
    values: dict[str, object]


class _FakeLogger:
    def __init__(self) -> None:
        self.events: list[_LogEvent] = []

    def info(self, event: str, **values: object) -> None:
        self.events.append(_LogEvent(event, values))

    def warning(self, event: str, **values: object) -> None:
        self.events.append(_LogEvent(event, values))


def _pricing_result() -> OpenAIAssistedProposalTextResult:
    return OpenAIAssistedProposalTextResult(
        proposal_type="pricing",
        tsv_text=(
            "provider\tmodel\tendpoint\tcurrency\tinput_price_per_1m\toutput_price_per_1m\n"
            "openai\tgpt-4.1-mini\tchat.completions\tUSD\t0.10\t0.20\n"
        ),
        row_count=1,
        warnings=("review cached-token assumptions",),
        source_urls=(
            "https://platform.openai.com/docs/pricing",
            "https://platform.openai.com/docs/models/compare",
        ),
    )


def _route_result() -> OpenAIAssistedProposalTextResult:
    return OpenAIAssistedProposalTextResult(
        proposal_type="route",
        tsv_text=(
            "requested_model\tmatch_type\tendpoint\tprovider\tupstream_model\n"
            "gpt-4.1-mini\texact\tchat.completions\topenai\tgpt-4.1-mini\n"
        ),
        row_count=1,
        warnings=(),
        source_urls=("https://platform.openai.com/docs/models/compare",),
    )


def test_openai_assisted_pages_require_login() -> None:
    client = TestClient(_app())

    for path in ("/admin/openai-assisted", "/admin/openai-assisted/pricing", "/admin/openai-assisted/routes"):
        response = client.get(path, follow_redirects=False)

        assert response.status_code == 303
        assert response.headers["location"] == "/admin/login"


def test_openai_assisted_post_requires_csrf(monkeypatch) -> None:
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    response = client.post(
        "/admin/openai-assisted/pricing/propose",
        data={"acknowledge_proposal": "true"},
    )

    assert response.status_code == 400
    assert "Invalid CSRF token." in response.text


def test_openai_assisted_missing_acknowledgement_fails_before_openai(monkeypatch) -> None:
    called = False

    async def generate(*args, **kwargs):
        nonlocal called
        called = True
        return _pricing_result()

    monkeypatch.setattr("slaif_gateway.api.admin.generate_openai_pricing_proposal_text", generate)
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    response = client.post(
        "/admin/openai-assisted/pricing/propose",
        data={"csrf_token": "dashboard-csrf"},
    )

    assert response.status_code == 400
    assert "Confirm that this is a proposal before calling OpenAI" in response.text
    assert called is False


def test_openai_assisted_missing_discovery_key_fails_safely(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_ADMIN_DISCOVERY_API_KEY", raising=False)
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    response = client.post(
        "/admin/openai-assisted/pricing/propose",
        data={
            "csrf_token": "dashboard-csrf",
            "acknowledge_proposal": "true",
            "source_url": "https://platform.openai.com/docs/pricing",
            "models_source_url": "https://platform.openai.com/docs/models/compare",
        },
    )

    assert response.status_code == 400
    assert "Proposal generation failed safely. Diagnostic ID:" in response.text
    assert "OPENAI_ADMIN_DISCOVERY_API_KEY is not configured" not in response.text


def test_openai_assisted_pricing_result_is_no_cache_and_links_to_import(monkeypatch) -> None:
    audit_payloads: list[dict[str, object]] = []

    async def generate(*args, **kwargs):
        return _pricing_result()

    async def audit(*args, **kwargs):
        audit_payloads.append(dict(kwargs))

    monkeypatch.setattr("slaif_gateway.api.admin.generate_openai_pricing_proposal_text", generate)
    monkeypatch.setattr("slaif_gateway.api.admin._audit_openai_assisted_proposal", audit)
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    response = client.post(
        "/admin/openai-assisted/pricing/propose",
        data={
            "csrf_token": "dashboard-csrf",
            "acknowledge_proposal": "true",
            "source_url": "https://platform.openai.com/docs/pricing",
            "models_source_url": "https://platform.openai.com/docs/models/compare",
            "include_models": "gpt-4.1-mini",
        },
    )

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store, no-cache, must-revalidate"
    assert "Generated TSV" in response.text
    assert "gpt-4.1-mini" in response.text
    assert "https://platform.openai.com/docs/pricing" in response.text
    assert 'href="/admin/pricing/import"' in response.text
    assert "does not execute import" in response.text
    assert "Preview pricing import" in response.text
    assert 'action="/admin/pricing/import/preview"' in response.text
    assert 'name="import_format" value="tsv"' in response.text
    assert 'name="source_label" value="OpenAI assisted pricing proposal"' in response.text
    assert 'name="csrf_token" value="dashboard-csrf"' in response.text
    assert "provider\tmodel\tendpoint\tcurrency" in response.text
    assert "Execution requires explicit confirmation and an audit reason" in response.text
    assert "not invoice-grade provider truth" in response.text
    assert audit_payloads[0]["proposal_kind"] == "pricing"


def test_openai_assisted_route_result_links_to_import(monkeypatch) -> None:
    async def generate(*args, **kwargs):
        return _route_result()

    async def audit(*args, **kwargs):
        return None

    monkeypatch.setattr("slaif_gateway.api.admin.generate_openai_route_proposal_text", generate)
    monkeypatch.setattr("slaif_gateway.api.admin._audit_openai_assisted_proposal", audit)
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    response = client.post(
        "/admin/openai-assisted/routes/propose",
        data={
            "csrf_token": "dashboard-csrf",
            "acknowledge_proposal": "true",
            "source_url": "https://platform.openai.com/docs/models/compare",
        },
    )

    assert response.status_code == 200
    assert "OpenAI Assisted Proposal Result" in response.text
    assert "gpt-4.1-mini" in response.text
    assert 'href="/admin/routes/import"' in response.text
    assert "Preview route import" in response.text
    assert 'action="/admin/routes/import/preview"' in response.text
    assert 'name="import_format" value="tsv"' in response.text
    assert 'name="source_label" value="OpenAI assisted route proposal"' in response.text
    assert 'name="csrf_token" value="dashboard-csrf"' in response.text
    assert "requested_model\tmatch_type\tendpoint\tprovider\tupstream_model" in response.text
    assert "https://platform.openai.com/docs/models/compare" in response.text


def test_openai_assisted_does_not_call_import_execution_services(monkeypatch) -> None:
    async def generate(*args, **kwargs):
        return _pricing_result()

    async def audit(*args, **kwargs):
        return None

    async def execute_pricing(*args, **kwargs):
        raise AssertionError("pricing import execution must not run")

    async def execute_routes(*args, **kwargs):
        raise AssertionError("route import execution must not run")

    monkeypatch.setattr("slaif_gateway.api.admin.generate_openai_pricing_proposal_text", generate)
    monkeypatch.setattr("slaif_gateway.api.admin._audit_openai_assisted_proposal", audit)
    monkeypatch.setattr("slaif_gateway.api.admin.execute_pricing_import_plan", execute_pricing)
    monkeypatch.setattr("slaif_gateway.api.admin.execute_route_import_plan", execute_routes)
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    response = client.post(
        "/admin/openai-assisted/pricing/propose",
        data={"csrf_token": "dashboard-csrf", "acknowledge_proposal": "true"},
    )

    assert response.status_code == 200
    assert "Generated TSV" in response.text


def test_openai_assisted_pricing_bridge_submission_reaches_preview_only(monkeypatch) -> None:
    executed = False

    async def classify(request, preview):
        return preview

    async def execute_pricing(*args, **kwargs):
        nonlocal executed
        executed = True
        raise AssertionError("pricing import execution must not run from preview bridge")

    monkeypatch.setattr("slaif_gateway.api.admin._classify_pricing_import_preview", classify)
    monkeypatch.setattr("slaif_gateway.api.admin.execute_pricing_import_plan", execute_pricing)
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    response = client.post(
        "/admin/pricing/import/preview",
        data={
            "csrf_token": "dashboard-csrf",
            "import_format": "tsv",
            "import_text": _pricing_result().tsv_text,
            "source_label": "OpenAI assisted pricing proposal",
        },
    )

    assert response.status_code == 200
    assert "Pricing Import Preview Result" in response.text
    assert "Database writes" in response.text
    assert "Source label: OpenAI assisted pricing proposal" in response.text
    assert "gpt-4.1-mini" in response.text
    assert executed is False


def test_openai_assisted_route_bridge_submission_reaches_preview_only(monkeypatch) -> None:
    executed = False

    async def build_preview(request, raw_rows, *, max_rows):
        from slaif_gateway.services.route_import import RouteImportPreview, RouteImportRowPreview

        assert raw_rows[0]["requested_model"] == "gpt-4.1-mini"
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
                    priority=100,
                    enabled=True,
                    visible_in_models=True,
                    supports_streaming=True,
                ),
            ),
        )

    async def execute_routes(*args, **kwargs):
        nonlocal executed
        executed = True
        raise AssertionError("route import execution must not run from preview bridge")

    monkeypatch.setattr("slaif_gateway.api.admin._build_route_import_preview", build_preview)
    monkeypatch.setattr("slaif_gateway.api.admin.execute_route_import_plan", execute_routes)
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    response = client.post(
        "/admin/routes/import/preview",
        data={
            "csrf_token": "dashboard-csrf",
            "import_format": "tsv",
            "import_text": _route_result().tsv_text,
            "source_label": "OpenAI assisted route proposal",
        },
    )

    assert response.status_code == 200
    assert "Route Import Preview Result" in response.text
    assert "Database writes" in response.text
    assert "Source label: OpenAI assisted route proposal" in response.text
    assert "gpt-4.1-mini" in response.text
    assert executed is False


def test_openai_assisted_bridge_does_not_relax_execution_gate(monkeypatch) -> None:
    called = False

    async def execute(*args, **kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr("slaif_gateway.api.admin.execute_pricing_import_plan", execute)
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    without_confirm = client.post(
        "/admin/pricing/import/execute",
        data={
            "csrf_token": "dashboard-csrf",
            "import_format": "tsv",
            "import_text": _pricing_result().tsv_text,
            "source_label": "OpenAI assisted pricing proposal",
            "reason": "reviewed proposal import",
        },
    )
    without_reason = client.post(
        "/admin/pricing/import/execute",
        data={
            "csrf_token": "dashboard-csrf",
            "import_format": "tsv",
            "import_text": _pricing_result().tsv_text,
            "source_label": "OpenAI assisted pricing proposal",
            "confirm_import": "true",
        },
    )

    assert without_confirm.status_code == 400
    assert "Confirm pricing import execution" in without_confirm.text
    assert without_reason.status_code == 400
    assert "Enter an audit reason" in without_reason.text
    assert called is False


def test_openai_assisted_discovery_key_does_not_render_or_enter_logs_or_audit(monkeypatch) -> None:
    fake_logger = _FakeLogger()
    audit_payloads: list[dict[str, object]] = []

    async def generate(*args, **kwargs):
        return _pricing_result()

    async def audit(*args, **kwargs):
        audit_payloads.append(dict(kwargs))

    monkeypatch.setenv("OPENAI_ADMIN_DISCOVERY_API_KEY", FAKE_DISCOVERY_KEY)
    monkeypatch.setattr("slaif_gateway.api.admin.generate_openai_pricing_proposal_text", generate)
    monkeypatch.setattr("slaif_gateway.api.admin._audit_openai_assisted_proposal", audit)
    monkeypatch.setattr("slaif_gateway.api.admin.logger", fake_logger)
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    response = client.post(
        "/admin/openai-assisted/pricing/propose",
        data={"csrf_token": "dashboard-csrf", "acknowledge_proposal": "true"},
    )

    assert response.status_code == 200
    assert FAKE_DISCOVERY_KEY not in response.text
    assert FAKE_DISCOVERY_KEY not in repr(audit_payloads)
    assert FAKE_DISCOVERY_KEY not in repr(fake_logger.events)


def test_openai_assisted_bridge_does_not_expose_secrets_or_raw_model_text(monkeypatch) -> None:
    fake_logger = _FakeLogger()
    audit_payloads: list[dict[str, object]] = []

    async def generate(*args, **kwargs):
        return _pricing_result()

    async def audit(*args, **kwargs):
        audit_payloads.append(dict(kwargs))

    monkeypatch.setenv("OPENAI_ADMIN_DISCOVERY_API_KEY", FAKE_DISCOVERY_KEY)
    monkeypatch.setenv("OPENAI_UPSTREAM_API_KEY", FAKE_PROVIDER_KEY)
    monkeypatch.setattr("slaif_gateway.api.admin.generate_openai_pricing_proposal_text", generate)
    monkeypatch.setattr("slaif_gateway.api.admin._audit_openai_assisted_proposal", audit)
    monkeypatch.setattr("slaif_gateway.api.admin.logger", fake_logger)
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client, valid_csrf=FAKE_CSRF)
    client.cookies.set("slaif_admin_session", FAKE_SESSION)

    response = client.post(
        "/admin/openai-assisted/pricing/propose",
        headers={"Authorization": FAKE_BEARER},
        data={
            "csrf_token": FAKE_CSRF,
            "acknowledge_proposal": "true",
            "include_models": FAKE_GATEWAY_KEY,
            "exclude_models": RAW_MODEL_RESPONSE_TEXT,
        },
    )

    assert response.status_code == 200
    for forbidden in (
        FAKE_DISCOVERY_KEY,
        FAKE_PROVIDER_KEY,
        FAKE_GATEWAY_KEY,
        FAKE_BEARER,
        FAKE_SESSION,
        RAW_MODEL_RESPONSE_TEXT,
        "session_token",
        "encrypted_payload",
        "nonce",
        "raw model response",
    ):
        assert forbidden not in response.text
        assert forbidden not in repr(audit_payloads)
        assert forbidden not in repr(fake_logger.events)
    assert f'name="csrf_token" value="{FAKE_CSRF}"' in response.text


def test_openai_assisted_oversized_tsv_suppresses_hidden_preview_form(monkeypatch) -> None:
    async def generate(*args, **kwargs):
        return _pricing_result()

    async def audit(*args, **kwargs):
        return None

    monkeypatch.setattr("slaif_gateway.api.admin.generate_openai_pricing_proposal_text", generate)
    monkeypatch.setattr("slaif_gateway.api.admin._audit_openai_assisted_proposal", audit)
    client = TestClient(_app(_app_settings(PRICING_IMPORT_MAX_BYTES=10)))
    _login_for_actions(monkeypatch, client)

    response = client.post(
        "/admin/openai-assisted/pricing/propose",
        data={"csrf_token": "dashboard-csrf", "acknowledge_proposal": "true"},
    )

    assert response.status_code == 200
    assert "Generated TSV" in response.text
    assert "larger than the browser import preview limit" in response.text
    assert 'action="/admin/pricing/import/preview"' not in response.text
    assert "Preview pricing import" not in response.text
    assert "gpt-4.1-mini" in response.text


def test_openai_assisted_source_urls_are_visible(monkeypatch) -> None:
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    pricing = client.get("/admin/openai-assisted/pricing")
    routes = client.get("/admin/openai-assisted/routes")

    assert pricing.status_code == 200
    assert "https://platform.openai.com/docs/pricing" in pricing.text
    assert "https://platform.openai.com/docs/models/compare" in pricing.text
    assert routes.status_code == 200
    assert "https://platform.openai.com/docs/models/compare" in routes.text


def test_openai_assisted_routes_do_not_claim_responses_or_completions_are_implemented(monkeypatch) -> None:
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    response = client.get("/admin/openai-assisted/routes")

    assert response.status_code == 200
    assert "Implemented Chat Completions only" in response.text
    assert "/v1/responses" in response.text
    assert "/v1/completions" in response.text
    assert "rows are excluded" in response.text
    assert "/v1/responses implemented" not in response.text.lower()
    assert "/v1/completions implemented" not in response.text.lower()
