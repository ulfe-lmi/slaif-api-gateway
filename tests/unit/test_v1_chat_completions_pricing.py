from __future__ import annotations

import inspect
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient

from slaif_gateway.api.dependencies import get_authenticated_gateway_key
from slaif_gateway.main import create_app
from slaif_gateway.schemas.auth import AuthenticatedGatewayKey
from slaif_gateway.schemas.providers import ProviderResponse, ProviderUsage
from slaif_gateway.schemas.quota import QuotaReservationResult
from slaif_gateway.schemas.routing import RouteResolutionResult
from slaif_gateway.services.pricing_errors import (
    FxRateNotFoundError,
    InvalidFxRateError,
    InvalidPricingDataError,
    PricingRuleNotFoundError,
)
from slaif_gateway.services.routing_errors import ModelNotFoundError


def _fake_authenticated_gateway_key() -> AuthenticatedGatewayKey:
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
        rate_limit_policy={
            "requests_per_minute": None,
            "tokens_per_minute": None,
            "max_concurrent_requests": None,
        },
    )


def _route_result(requested_model: str = "classroom-cheap") -> RouteResolutionResult:
    return RouteResolutionResult(
        requested_model=requested_model,
        resolved_model="gpt-4.1-mini",
        provider="openai",
        route_id=uuid.uuid4(),
        route_match_type="exact",
        route_pattern=requested_model,
        priority=100,
    )


def _wire_auth_and_db(monkeypatch, app) -> None:
    from slaif_gateway.api import dependencies as dependencies_module
    import slaif_gateway.services.chat_completion_gateway as main_module

    async def _fake_auth_dependency() -> AuthenticatedGatewayKey:
        return _fake_authenticated_gateway_key()

    async def _dummy_db_session():
        yield object()

    async def _fake_reserve(
        self,
        *,
        authenticated_key,
        route,
        policy,
        cost_estimate,
        request_id,
        now=None,
    ):
        _ = (self, route, policy, cost_estimate, now)
        return QuotaReservationResult(
            reservation_id=uuid.uuid4(),
            gateway_key_id=authenticated_key.gateway_key_id,
            request_id=request_id,
            reserved_cost_eur=Decimal("0"),
            reserved_tokens=0,
            status="pending",
            expires_at=datetime.now(UTC) + timedelta(minutes=15),
        )

    async def _fake_release(self, reservation_id, *, reason=None, now=None):
        _ = (self, reason, now)
        return QuotaReservationResult(
            reservation_id=reservation_id,
            gateway_key_id=uuid.uuid4(),
            request_id="req",
            reserved_cost_eur=Decimal("0"),
            reserved_tokens=0,
            status="released",
            expires_at=datetime.now(UTC) + timedelta(minutes=15),
        )

    app.dependency_overrides[get_authenticated_gateway_key] = _fake_auth_dependency
    monkeypatch.setattr(dependencies_module, "_get_db_session_after_auth_header_check", _dummy_db_session)
    monkeypatch.setattr(main_module, "_get_db_session_after_auth_header_check", _dummy_db_session)
    monkeypatch.setattr(main_module.QuotaService, "reserve_for_chat_completion", _fake_reserve)
    monkeypatch.setattr(main_module.QuotaService, "release_reservation", _fake_release)


def _chat_request(model: str = "classroom-cheap") -> dict[str, object]:
    return {
        "model": model,
        "messages": [{"role": "user", "content": "hello"}],
        "max_tokens": 20,
    }


def _wire_successful_forwarding(monkeypatch) -> None:
    import slaif_gateway.services.chat_completion_gateway as main_module

    class _FakeAdapter:
        async def forward_chat_completion(self, request):
            return ProviderResponse(
                provider=request.provider,
                upstream_model=request.upstream_model,
                status_code=200,
                json_body={"id": "chatcmpl_test"},
                usage=ProviderUsage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
            )

    async def _fake_finalize_successful_response(self, *args, **kwargs):
        _ = (self, args, kwargs)
        return object()

    monkeypatch.setattr(main_module, "get_provider_adapter", lambda provider, settings: _FakeAdapter())
    monkeypatch.setattr(
        main_module.AccountingService,
        "finalize_successful_response",
        _fake_finalize_successful_response,
    )


def test_valid_route_and_pricing_reaches_provider_forwarding(monkeypatch) -> None:
    import slaif_gateway.services.chat_completion_gateway as main_module

    app = create_app()
    _wire_auth_and_db(monkeypatch, app)
    calls: list[tuple[str, str, str]] = []

    async def _fake_resolve_model(self, requested_model, authenticated_key):
        _ = (self, authenticated_key)
        return _route_result(requested_model)

    async def _fake_estimate_chat_completion_cost(
        self,
        *,
        route,
        policy,
        endpoint="chat.completions",
        at=None,
    ):
        _ = (self, policy, at)
        calls.append((route.requested_model, route.resolved_model, endpoint))
        return object()

    monkeypatch.setattr(main_module.RouteResolutionService, "resolve_model", _fake_resolve_model)
    monkeypatch.setattr(
        main_module.PricingService,
        "estimate_chat_completion_cost",
        _fake_estimate_chat_completion_cost,
    )
    _wire_successful_forwarding(monkeypatch)

    response = TestClient(app).post("/v1/chat/completions", json=_chat_request())

    assert calls == [("classroom-cheap", "gpt-4.1-mini", "chat.completions")]
    assert response.status_code == 200
    assert response.json()["id"] == "chatcmpl_test"


def test_missing_pricing_rule_returns_openai_error_before_501(monkeypatch) -> None:
    _assert_pricing_error(monkeypatch, PricingRuleNotFoundError(param="model"), 400, "pricing_rule_not_found")


def test_missing_fx_rate_returns_openai_error_before_501(monkeypatch) -> None:
    _assert_pricing_error(monkeypatch, FxRateNotFoundError(param="currency"), 400, "fx_rate_not_found")


def test_invalid_pricing_data_returns_openai_error_before_501(monkeypatch) -> None:
    _assert_pricing_error(monkeypatch, InvalidPricingDataError(), 500, "invalid_pricing_data")


def test_invalid_fx_data_returns_openai_error_before_501(monkeypatch) -> None:
    _assert_pricing_error(monkeypatch, InvalidFxRateError(), 500, "invalid_fx_rate")


def _assert_pricing_error(monkeypatch, pricing_error, expected_status: int, expected_code: str) -> None:
    import slaif_gateway.services.chat_completion_gateway as main_module

    app = create_app()
    _wire_auth_and_db(monkeypatch, app)

    async def _fake_resolve_model(self, requested_model, authenticated_key):
        _ = (self, authenticated_key)
        return _route_result(requested_model)

    async def _fake_estimate_chat_completion_cost(self, *, route, policy, endpoint="chat.completions", at=None):
        _ = (self, route, policy, endpoint, at)
        raise pricing_error

    monkeypatch.setattr(main_module.RouteResolutionService, "resolve_model", _fake_resolve_model)
    monkeypatch.setattr(
        main_module.PricingService,
        "estimate_chat_completion_cost",
        _fake_estimate_chat_completion_cost,
    )

    response = TestClient(app).post("/v1/chat/completions", json=_chat_request())

    assert response.status_code == expected_status
    body = response.json()
    assert body["error"]["code"] == expected_code
    assert body["error"]["code"] != "provider_forwarding_not_implemented"


def test_missing_model_returns_shape_error_before_route_or_pricing(monkeypatch) -> None:
    route_calls, pricing_calls = _wire_counting_route_and_pricing(monkeypatch)
    app = create_app()
    _wire_auth_and_db(monkeypatch, app)

    response = TestClient(app).post(
        "/v1/chat/completions",
        json={"messages": [{"role": "user", "content": "hello"}]},
    )

    assert response.status_code == 422
    assert response.json()["error"]["type"] == "invalid_request_error"
    assert route_calls == []
    assert pricing_calls == []


def test_excessive_max_tokens_returns_policy_error_before_route_or_pricing(monkeypatch) -> None:
    route_calls, pricing_calls = _wire_counting_route_and_pricing(monkeypatch)
    app = create_app()
    _wire_auth_and_db(monkeypatch, app)

    response = TestClient(app).post(
        "/v1/chat/completions",
        json={
            "model": "classroom-cheap",
            "messages": [{"role": "user", "content": "hello"}],
            "max_tokens": 999999,
        },
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "output_token_limit_exceeded"
    assert route_calls == []
    assert pricing_calls == []


def test_unsupported_model_returns_route_error_before_pricing(monkeypatch) -> None:
    import slaif_gateway.services.chat_completion_gateway as main_module

    app = create_app()
    _wire_auth_and_db(monkeypatch, app)
    pricing_calls: list[str] = []

    async def _fake_resolve_model(self, requested_model, authenticated_key):
        _ = (self, requested_model, authenticated_key)
        raise ModelNotFoundError()

    async def _fake_estimate_chat_completion_cost(self, *, route, policy, endpoint="chat.completions", at=None):
        _ = (self, route, policy, endpoint, at)
        pricing_calls.append("called")
        return object()

    monkeypatch.setattr(main_module.RouteResolutionService, "resolve_model", _fake_resolve_model)
    monkeypatch.setattr(
        main_module.PricingService,
        "estimate_chat_completion_cost",
        _fake_estimate_chat_completion_cost,
    )

    response = TestClient(app).post("/v1/chat/completions", json=_chat_request("unsupported"))

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "model_not_found"
    assert pricing_calls == []


def test_missing_pricing_for_supported_route_returns_pricing_error_before_501(monkeypatch) -> None:
    _assert_pricing_error(monkeypatch, PricingRuleNotFoundError(param="model"), 400, "pricing_rule_not_found")


def _wire_counting_route_and_pricing(monkeypatch) -> tuple[list[str], list[str]]:
    import slaif_gateway.services.chat_completion_gateway as main_module

    route_calls: list[str] = []
    pricing_calls: list[str] = []

    async def _fake_resolve_model(self, requested_model, authenticated_key):
        _ = (self, authenticated_key)
        route_calls.append(requested_model)
        return _route_result(requested_model)

    async def _fake_estimate_chat_completion_cost(self, *, route, policy, endpoint="chat.completions", at=None):
        _ = (self, policy, endpoint, at)
        pricing_calls.append(route.requested_model)
        return object()

    monkeypatch.setattr(main_module.RouteResolutionService, "resolve_model", _fake_resolve_model)
    monkeypatch.setattr(
        main_module.PricingService,
        "estimate_chat_completion_cost",
        _fake_estimate_chat_completion_cost,
    )
    return route_calls, pricing_calls


def test_chat_completions_pricing_path_safety_constraints() -> None:
    import slaif_gateway.services.chat_completion_gateway as main_module

    source = inspect.getsource(main_module).lower()

    for disallowed in (
        "httpx",
        "openai_upstream",
        "openrouter_api_key",
        "celery",
        "aiosmtplib",
    ):
        assert disallowed not in source
