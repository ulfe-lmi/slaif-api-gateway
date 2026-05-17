from __future__ import annotations

from dataclasses import dataclass

from fastapi.testclient import TestClient

from slaif_gateway.services.openai_assisted_catalog import OpenAIAssistedProposalTextResult

from tests.unit.test_admin_pricing_actions_routes import _app, _login_for_actions


FAKE_DISCOVERY_KEY = "sk-admin-discovery-secret-must-not-render-123456"


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
