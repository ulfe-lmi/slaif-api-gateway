from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient

from slaif_gateway.api.dependencies import get_authenticated_gateway_key
from slaif_gateway.config import Settings
from slaif_gateway.main import create_app
from slaif_gateway.providers.errors import (
    ProviderHTTPError,
    ProviderResponseParseError,
    ProviderTimeoutError,
)
from slaif_gateway.schemas.auth import AuthenticatedGatewayKey
from slaif_gateway.schemas.pricing import ChatCostEstimate
from slaif_gateway.schemas.providers import ProviderResponse
from slaif_gateway.schemas.quota import QuotaReservationResult
from slaif_gateway.schemas.routing import RouteResolutionResult
from slaif_gateway.services.accounting_errors import ReservationFinalizationError, UsageMissingError
from slaif_gateway.services.policy_errors import OutputTokenLimitExceededError
from slaif_gateway.services.pricing_errors import PricingRuleNotFoundError
from slaif_gateway.services.quota_errors import QuotaLimitExceededError
from slaif_gateway.services.routing_errors import ModelNotFoundError


def _auth() -> AuthenticatedGatewayKey:
    now = datetime.now(UTC)
    return AuthenticatedGatewayKey(
        gateway_key_id=uuid.uuid4(),
        owner_id=uuid.uuid4(),
        cohort_id=None,
        public_key_id="public1234abcd",
        status="active",
        valid_from=now - timedelta(minutes=5),
        valid_until=now + timedelta(minutes=30),
        allow_all_models=True,
        allowed_models=(),
        allow_all_endpoints=True,
        allowed_endpoints=(),
        allowed_providers=None,
        cost_limit_eur=None,
        token_limit_total=None,
        request_limit_total=None,
        rate_limit_policy={},
    )


def _route(provider: str = "openai") -> RouteResolutionResult:
    return RouteResolutionResult(
        requested_model="classroom-cheap",
        resolved_model="gpt-4.1-mini",
        provider=provider,
        route_id=uuid.uuid4(),
        route_match_type="exact",
        route_pattern="classroom-cheap",
        priority=100,
    )


def _estimate() -> ChatCostEstimate:
    return ChatCostEstimate(
        provider="openai",
        requested_model="classroom-cheap",
        resolved_model="gpt-4.1-mini",
        native_currency="EUR",
        estimated_input_tokens=50,
        estimated_output_tokens=20,
        estimated_input_cost_native=Decimal("0.001"),
        estimated_output_cost_native=Decimal("0.002"),
        estimated_total_cost_native=Decimal("0.003"),
        estimated_total_cost_eur=Decimal("0.003"),
        pricing_rule_id=None,
        fx_rate_id=None,
    )


def _chat_request(**overrides) -> dict[str, object]:
    body: dict[str, object] = {
        "model": "classroom-cheap",
        "messages": [{"role": "user", "content": "hello"}],
        "max_tokens": 20,
    }
    body.update(overrides)
    return body


def _wire_pipeline(
    monkeypatch,
    app,
    *,
    provider: str = "openai",
    route_error=None,
    pricing_error=None,
    quota_error=None,
) -> dict[str, object]:
    from slaif_gateway.api import dependencies as dependencies_module
    import slaif_gateway.services.chat_completion_gateway as main_module

    state: dict[str, object] = {
        "route_calls": [],
        "pricing_calls": [],
        "reserve_calls": [],
        "failure_accounting_calls": [],
        "finalize_calls": [],
        "commit_calls": 0,
    }
    auth = _auth()

    class _Session:
        async def commit(self) -> None:
            state["commit_calls"] += 1

    async def _fake_auth_dependency() -> AuthenticatedGatewayKey:
        return auth

    async def _dummy_db_session():
        yield _Session()

    async def _fake_resolve_model(self, requested_model, authenticated_key):
        _ = (self, authenticated_key)
        state["route_calls"].append(requested_model)
        if route_error is not None:
            raise route_error
        return _route(provider)

    async def _fake_estimate_chat_completion_cost(self, *, route, policy, endpoint="chat.completions", at=None):
        _ = (self, policy, endpoint, at)
        state["pricing_calls"].append(route.requested_model)
        if pricing_error is not None:
            raise pricing_error
        return _estimate()

    async def _fake_reserve(self, *, authenticated_key, route, policy, cost_estimate, request_id, now=None):
        _ = (self, authenticated_key, route, policy, cost_estimate, now)
        state["reserve_calls"].append(request_id)
        if quota_error is not None:
            raise quota_error
        return QuotaReservationResult(
            reservation_id=uuid.uuid4(),
            gateway_key_id=auth.gateway_key_id,
            request_id=request_id,
            reserved_cost_eur=Decimal("0.003"),
            reserved_tokens=70,
            status="pending",
            expires_at=datetime.now(UTC) + timedelta(minutes=15),
        )

    async def _fake_record_failure(self, *args, **kwargs):
        _ = (self, args, kwargs)
        state["failure_accounting_calls"].append(kwargs.get("request_id"))
        return object()

    async def _fake_finalize(self, *args, **kwargs):
        _ = (self, args, kwargs)
        state["finalize_calls"].append(kwargs.get("request_id"))
        return object()

    app.dependency_overrides[get_authenticated_gateway_key] = _fake_auth_dependency
    monkeypatch.setattr(dependencies_module, "_get_db_session_after_auth_header_check", _dummy_db_session)
    monkeypatch.setattr(main_module, "_get_db_session_after_auth_header_check", _dummy_db_session)
    monkeypatch.setattr(main_module.RouteResolutionService, "resolve_model", _fake_resolve_model)
    monkeypatch.setattr(
        main_module.PricingService,
        "estimate_chat_completion_cost",
        _fake_estimate_chat_completion_cost,
    )
    monkeypatch.setattr(main_module.QuotaService, "reserve_for_chat_completion", _fake_reserve)
    monkeypatch.setattr(main_module.AccountingService, "record_provider_failure_and_release", _fake_record_failure)
    monkeypatch.setattr(main_module.AccountingService, "finalize_successful_response", _fake_finalize)
    return state


def _wire_provider_error(monkeypatch, provider_error) -> None:
    import slaif_gateway.services.chat_completion_gateway as main_module

    class _FakeAdapter:
        async def forward_chat_completion(self, request):
            _ = request
            raise provider_error

        async def stream_chat_completion(self, request):
            _ = request
            raise provider_error
            yield  # pragma: no cover

    monkeypatch.setattr(main_module, "get_provider_adapter", lambda provider, settings: _FakeAdapter())


def test_missing_provider_api_key_returns_provider_error_and_records_failure(monkeypatch) -> None:
    app = create_app(Settings())
    state = _wire_pipeline(monkeypatch, app)

    response = TestClient(app).post("/v1/chat/completions", json=_chat_request())

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "missing_provider_api_key"
    assert state["reserve_calls"]
    assert state["failure_accounting_calls"]


def test_unknown_provider_returns_provider_configuration_error(monkeypatch) -> None:
    app = create_app(Settings())
    state = _wire_pipeline(monkeypatch, app, provider="unknown-provider")

    response = TestClient(app).post("/v1/chat/completions", json=_chat_request())

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "unsupported_provider"
    assert state["failure_accounting_calls"]


def test_provider_non_2xx_timeout_and_parse_errors_are_openai_shaped(monkeypatch) -> None:
    cases = [
        (ProviderHTTPError(provider="openai", upstream_status_code=429), 429, "provider_http_error"),
        (ProviderTimeoutError(provider="openai"), 504, "provider_timeout"),
        (ProviderResponseParseError(provider="openai"), 502, "provider_response_parse_error"),
    ]

    for provider_error, expected_status, expected_code in cases:
        app = create_app(Settings(OPENAI_UPSTREAM_API_KEY="unused"))
        state = _wire_pipeline(monkeypatch, app)
        _wire_provider_error(monkeypatch, provider_error)

        response = TestClient(app).post("/v1/chat/completions", json=_chat_request())

        assert response.status_code == expected_status
        assert response.json()["error"]["code"] == expected_code
        assert state["reserve_calls"]
        assert state["failure_accounting_calls"]


def test_provider_success_missing_usage_returns_accounting_error(monkeypatch) -> None:
    import slaif_gateway.services.chat_completion_gateway as main_module

    app = create_app(Settings(OPENAI_UPSTREAM_API_KEY="unused"))
    state = _wire_pipeline(monkeypatch, app)

    class _FakeAdapter:
        async def forward_chat_completion(self, request):
            return ProviderResponse(
                provider=request.provider,
                upstream_model=request.upstream_model,
                status_code=200,
                json_body={"id": "must_not_return"},
                usage=None,
            )

    async def _raise_usage_missing(self, *args, **kwargs):
        _ = (self, args, kwargs)
        raise UsageMissingError()

    monkeypatch.setattr(main_module, "get_provider_adapter", lambda provider, settings: _FakeAdapter())
    monkeypatch.setattr(main_module.AccountingService, "finalize_successful_response", _raise_usage_missing)

    response = TestClient(app).post("/v1/chat/completions", json=_chat_request())

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "usage_missing"
    assert response.json().get("id") != "must_not_return"
    assert state["reserve_calls"]


def test_accounting_finalization_error_does_not_return_provider_json(monkeypatch) -> None:
    import slaif_gateway.services.chat_completion_gateway as main_module

    app = create_app(Settings(OPENAI_UPSTREAM_API_KEY="unused"))
    _wire_pipeline(monkeypatch, app)

    class _FakeAdapter:
        async def forward_chat_completion(self, request):
            return ProviderResponse(
                provider=request.provider,
                upstream_model=request.upstream_model,
                status_code=200,
                json_body={"id": "must_not_return"},
                usage=None,
            )

    async def _raise_accounting_error(self, *args, **kwargs):
        _ = (self, args, kwargs)
        raise ReservationFinalizationError()

    monkeypatch.setattr(main_module, "get_provider_adapter", lambda provider, settings: _FakeAdapter())
    monkeypatch.setattr(main_module.AccountingService, "finalize_successful_response", _raise_accounting_error)

    response = TestClient(app).post("/v1/chat/completions", json=_chat_request())

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "reservation_finalization_error"
    assert response.json().get("id") != "must_not_return"


def test_stream_true_provider_error_releases_reservation(monkeypatch) -> None:
    app = create_app(Settings(OPENAI_UPSTREAM_API_KEY="unused"))
    state = _wire_pipeline(monkeypatch, app)
    _wire_provider_error(monkeypatch, ProviderTimeoutError(provider="openai"))

    with TestClient(app).stream("POST", "/v1/chat/completions", json=_chat_request(stream=True)) as response:
        body = "".join(response.iter_text())

    assert response.status_code == 200
    assert "provider_timeout" in body
    assert state["route_calls"] == ["classroom-cheap"]
    assert state["reserve_calls"]
    assert state["failure_accounting_calls"]


def test_error_order_before_provider(monkeypatch) -> None:
    app = create_app(Settings(OPENAI_UPSTREAM_API_KEY="unused"))
    state = _wire_pipeline(monkeypatch, app)
    response = TestClient(app).post(
        "/v1/chat/completions",
        json={"messages": [{"role": "user", "content": "hello"}]},
    )
    assert response.status_code == 422
    assert state["route_calls"] == []

    app = create_app(Settings(OPENAI_UPSTREAM_API_KEY="unused"))
    state = _wire_pipeline(monkeypatch, app)
    response = TestClient(app).post("/v1/chat/completions", json=_chat_request(max_tokens=999999))
    assert response.status_code == 400
    assert response.json()["error"]["code"] == OutputTokenLimitExceededError.error_code
    assert state["route_calls"] == []

    app = create_app(Settings(OPENAI_UPSTREAM_API_KEY="unused"))
    state = _wire_pipeline(monkeypatch, app, route_error=ModelNotFoundError())
    response = TestClient(app).post("/v1/chat/completions", json=_chat_request())
    assert response.status_code == 404
    assert state["pricing_calls"] == []

    app = create_app(Settings(OPENAI_UPSTREAM_API_KEY="unused"))
    state = _wire_pipeline(monkeypatch, app, pricing_error=PricingRuleNotFoundError(param="model"))
    response = TestClient(app).post("/v1/chat/completions", json=_chat_request())
    assert response.status_code == 400
    assert state["reserve_calls"] == []

    app = create_app(Settings(OPENAI_UPSTREAM_API_KEY="unused"))
    state = _wire_pipeline(
        monkeypatch,
        app,
        quota_error=QuotaLimitExceededError("Token quota limit exceeded", param="token_limit_total"),
    )
    response = TestClient(app).post("/v1/chat/completions", json=_chat_request())
    assert response.status_code == 429
    assert state["failure_accounting_calls"] == []
