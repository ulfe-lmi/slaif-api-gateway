from __future__ import annotations

import uuid
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
from fastapi.testclient import TestClient

from slaif_gateway.api.dependencies import get_authenticated_gateway_key
from slaif_gateway.config import Settings
from slaif_gateway.main import create_app
from slaif_gateway.schemas.auth import AuthenticatedGatewayKey
from slaif_gateway.schemas.pricing import ChatCostEstimate
from slaif_gateway.schemas.quota import QuotaReservationResult
from slaif_gateway.schemas.routing import RouteResolutionResult


class FakeSession:
    def __init__(self) -> None:
        self.commit_calls = 0

    async def commit(self) -> None:
        self.commit_calls += 1


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


def _route(provider: str = "openai", resolved_model: str = "gpt-4.1-mini") -> RouteResolutionResult:
    return RouteResolutionResult(
        requested_model="classroom-cheap",
        resolved_model=resolved_model,
        provider=provider,
        route_id=uuid.uuid4(),
        route_match_type="exact",
        route_pattern="classroom-cheap",
        priority=100,
    )


def _estimate(provider: str = "openai", resolved_model: str = "gpt-4.1-mini") -> ChatCostEstimate:
    return ChatCostEstimate(
        provider=provider,
        requested_model="classroom-cheap",
        resolved_model=resolved_model,
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


def _chat_request() -> dict[str, object]:
    return {
        "model": "classroom-cheap",
        "messages": [{"role": "user", "content": "hello"}],
        "max_tokens": 20,
    }


def _wire_pipeline(
    monkeypatch,
    app,
    *,
    provider: str = "openai",
    resolved_model: str = "gpt-4.1-mini",
) -> dict[str, object]:
    from slaif_gateway.api import dependencies as dependencies_module
    import slaif_gateway.main as main_module

    state: dict[str, object] = {
        "session": FakeSession(),
        "reserve_calls": [],
        "finalize_calls": [],
        "provider_responses": [],
    }
    auth = _auth()
    route_result = _route(provider=provider, resolved_model=resolved_model)
    estimate = _estimate(provider=provider, resolved_model=resolved_model)

    async def _fake_auth_dependency() -> AuthenticatedGatewayKey:
        return auth

    async def _dummy_db_session():
        yield state["session"]

    async def _fake_resolve_model(self, requested_model, authenticated_key):
        _ = (self, authenticated_key)
        assert requested_model == "classroom-cheap"
        return route_result

    async def _fake_estimate_chat_completion_cost(self, *, route, policy, endpoint="chat.completions", at=None):
        _ = (self, route, policy, endpoint, at)
        return estimate

    async def _fake_reserve(self, *, authenticated_key, route, policy, cost_estimate, request_id, now=None):
        _ = (self, authenticated_key, policy, cost_estimate, now)
        state["reserve_calls"].append((route.provider, request_id))
        return QuotaReservationResult(
            reservation_id=uuid.uuid4(),
            gateway_key_id=auth.gateway_key_id,
            request_id=request_id,
            reserved_cost_eur=Decimal("0.003"),
            reserved_tokens=70,
            status="pending",
            expires_at=datetime.now(UTC) + timedelta(minutes=15),
        )

    async def _fake_finalize_successful_response(
        self,
        reservation_id,
        authenticated_key,
        route,
        policy,
        pricing_estimate,
        provider_response,
        request_id,
        endpoint="chat.completions",
        started_at=None,
        finished_at=None,
    ):
        _ = (
            self,
            reservation_id,
            authenticated_key,
            route,
            policy,
            pricing_estimate,
            endpoint,
            started_at,
            finished_at,
        )
        state["finalize_calls"].append(request_id)
        state["provider_responses"].append(provider_response)
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
    monkeypatch.setattr(
        main_module.AccountingService,
        "finalize_successful_response",
        _fake_finalize_successful_response,
    )
    return state


def test_openai_nonstreaming_happy_path_uses_adapter_and_finalizes(
    monkeypatch,
    respx_mock,
) -> None:
    settings = Settings(OPENAI_UPSTREAM_API_KEY="openai-upstream-key")
    app = create_app(settings)
    state = _wire_pipeline(monkeypatch, app, provider="openai", resolved_model="gpt-4.1-mini")
    route = respx_mock.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "chatcmpl_openai",
                "object": "chat.completion",
                "model": "gpt-4.1-mini",
                "choices": [],
                "usage": {"prompt_tokens": 5, "completion_tokens": 7, "total_tokens": 12},
            },
            headers={"x-request-id": "upstream-openai"},
        )
    )

    response = TestClient(app).post(
        "/v1/chat/completions",
        json=_chat_request(),
        headers={"Authorization": "Bearer client-gateway-key"},
    )

    assert response.status_code == 200
    assert response.json()["id"] == "chatcmpl_openai"
    assert state["reserve_calls"]
    assert state["finalize_calls"]
    assert route.called
    upstream_request = route.calls[0].request
    assert upstream_request.headers["authorization"] == "Bearer openai-upstream-key"
    assert upstream_request.headers["authorization"] != "Bearer client-gateway-key"
    upstream_body = json.loads(upstream_request.content)
    assert upstream_body["model"] == "gpt-4.1-mini"
    assert upstream_body["max_tokens"] == 20
    assert state["provider_responses"][0].usage.total_tokens == 12
    assert state["session"].commit_calls == 1


def test_openrouter_route_uses_openrouter_adapter_path(monkeypatch, respx_mock) -> None:
    settings = Settings(OPENROUTER_API_KEY="openrouter-upstream-key")
    app = create_app(settings)
    state = _wire_pipeline(
        monkeypatch,
        app,
        provider="openrouter",
        resolved_model="openai/gpt-4.1-mini",
    )
    route = respx_mock.post("https://openrouter.ai/api/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "or_chatcmpl",
                "choices": [],
                "usage": {"prompt_tokens": 3, "completion_tokens": 4, "total_tokens": 7},
            },
        )
    )

    response = TestClient(app).post("/v1/chat/completions", json=_chat_request())

    assert response.status_code == 200
    assert response.json()["id"] == "or_chatcmpl"
    assert route.called
    upstream_request = route.calls[0].request
    assert upstream_request.headers["authorization"] == "Bearer openrouter-upstream-key"
    upstream_body = json.loads(upstream_request.content)
    assert upstream_body["model"] == "openai/gpt-4.1-mini"
    assert state["finalize_calls"]
