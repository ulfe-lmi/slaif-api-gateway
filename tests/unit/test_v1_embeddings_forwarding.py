from __future__ import annotations

import json
import uuid
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
from fastapi.testclient import TestClient

from slaif_gateway.api.dependencies import get_authenticated_gateway_key
from slaif_gateway.config import Settings
from slaif_gateway.main import create_app
from slaif_gateway.schemas.accounting import FinalizedAccountingResult, ProviderFailureAccountingResult
from slaif_gateway.schemas.auth import AuthenticatedGatewayKey
from slaif_gateway.schemas.pricing import ChatCostEstimate
from slaif_gateway.schemas.quota import QuotaReservationResult
from slaif_gateway.schemas.routing import RouteResolutionResult


class FakeSession:
    def __init__(self) -> None:
        self.commit_calls = 0

    async def commit(self) -> None:
        self.commit_calls += 1


def _auth(*, allowed_endpoints: tuple[str, ...] | None = None) -> AuthenticatedGatewayKey:
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
        allow_all_endpoints=allowed_endpoints is None,
        allowed_endpoints=allowed_endpoints or (),
        allowed_providers=None,
        cost_limit_eur=None,
        token_limit_total=None,
        request_limit_total=None,
        rate_limit_policy={},
        key_purpose="standard",
        capability_policy_mode="standard",
    )


def _route(
    *,
    provider: str = "openai",
    resolved_model: str = "text-embedding-3-small",
    capabilities: dict[str, object] | None = None,
) -> RouteResolutionResult:
    return RouteResolutionResult(
        requested_model="classroom-embedding",
        resolved_model=resolved_model,
        provider=provider,
        route_id=uuid.uuid4(),
        route_match_type="exact",
        route_pattern="classroom-embedding",
        priority=1,
        provider_base_url=None,
        provider_api_key_env_var=None,
        capabilities=capabilities,
    )


def _estimate() -> ChatCostEstimate:
    return ChatCostEstimate(
        provider="openai",
        requested_model="classroom-embedding",
        resolved_model="text-embedding-3-small",
        native_currency="USD",
        estimated_input_tokens=8,
        estimated_output_tokens=0,
        estimated_input_cost_native=Decimal("0.000160000"),
        estimated_output_cost_native=Decimal("0"),
        estimated_total_cost_native=Decimal("0.000160000"),
        estimated_total_cost_eur=Decimal("0.000144000"),
        pricing_rule_id=None,
        fx_rate_id=None,
        input_price_per_1m=Decimal("20.000000000"),
        output_price_per_1m=Decimal("0"),
        request_price=None,
        fx_rate=Decimal("0.9"),
    )


def _embeddings_capabilities(*, dimensions: bool = False) -> dict[str, object]:
    return {
        "embeddings": {
            "embeddings": True,
            "embeddings_dimensions": dimensions,
        }
    }


def _wire_embeddings_pipeline(
    monkeypatch,
    app,
    *,
    provider: str = "openai",
    auth: AuthenticatedGatewayKey | None = None,
    dimensions_capability: bool = False,
) -> dict[str, object]:
    from slaif_gateway.api import dependencies as dependencies_module
    import slaif_gateway.services.embeddings_gateway as embeddings_module

    state: dict[str, object] = {
        "session": FakeSession(),
        "reserve_calls": [],
        "finalize_calls": [],
        "custom_finalize_calls": [],
        "failure_release_calls": [],
        "provider_responses": [],
    }
    authenticated_key = auth or _auth()
    route_result = _route(
        provider=provider,
        capabilities=_embeddings_capabilities(dimensions=dimensions_capability),
    )
    estimate = _estimate()

    async def _fake_auth_dependency() -> AuthenticatedGatewayKey:
        return authenticated_key

    async def _dummy_db_session():
        yield state["session"]

    async def _fake_resolve_model(self, requested_model, authenticated_key, *, endpoint):
        _ = (self, authenticated_key)
        assert requested_model == "classroom-embedding"
        assert endpoint == "/v1/embeddings"
        return route_result

    async def _fake_estimate_embeddings_cost(self, *, route, policy, endpoint, at=None):
        _ = (self, route, policy, endpoint, at)
        return estimate

    async def _fake_reserve(self, *, authenticated_key, route, policy, cost_estimate, request_id, endpoint, now=None):
        _ = (self, authenticated_key, route, policy, cost_estimate, endpoint, now)
        state["reserve_calls"].append(request_id)
        return QuotaReservationResult(
            reservation_id=uuid.uuid4(),
            gateway_key_id=authenticated_key.gateway_key_id,
            request_id=request_id,
            reserved_cost_eur=Decimal("0.000144000"),
            reserved_tokens=8,
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
        **kwargs,
    ):
        _ = (self, authenticated_key, route, policy, pricing_estimate, endpoint, kwargs)
        state["finalize_calls"].append(request_id)
        state["provider_responses"].append(provider_response)
        return FinalizedAccountingResult(
            usage_ledger_id=uuid.uuid4(),
            reservation_id=reservation_id,
            gateway_key_id=authenticated_key.gateway_key_id,
            request_id=request_id,
            estimated_cost_eur=pricing_estimate.estimated_total_cost_eur,
            actual_cost_eur=Decimal("0.000100000"),
            actual_cost_native=Decimal("0.000110000"),
            native_currency=pricing_estimate.native_currency,
            prompt_tokens=4,
            completion_tokens=0,
            total_tokens=4,
            accounting_status="finalized",
        )

    async def _fake_finalize_successful_custom_response(
        self,
        reservation_id,
        authenticated_key,
        route,
        pricing_estimate,
        provider_response,
        request_id,
        **kwargs,
    ):
        _ = (self, authenticated_key, route, pricing_estimate, kwargs)
        state["custom_finalize_calls"].append((request_id, kwargs))
        state["provider_responses"].append(provider_response)
        return FinalizedAccountingResult(
            usage_ledger_id=uuid.uuid4(),
            reservation_id=reservation_id,
            gateway_key_id=authenticated_key.gateway_key_id,
            request_id=request_id,
            estimated_cost_eur=pricing_estimate.estimated_total_cost_eur,
            actual_cost_eur=pricing_estimate.estimated_total_cost_eur,
            actual_cost_native=pricing_estimate.estimated_total_cost_native,
            native_currency=pricing_estimate.native_currency,
            prompt_tokens=kwargs["usage"].prompt_tokens,
            completion_tokens=kwargs["usage"].completion_tokens,
            total_tokens=kwargs["usage"].total_tokens,
            accounting_status="finalized",
        )

    async def _fake_record_provider_failure_and_release(self, *args, **kwargs):
        _ = (self, args)
        state["failure_release_calls"].append(kwargs.get("error_code"))
        return ProviderFailureAccountingResult(
            usage_ledger_id=uuid.uuid4(),
            reservation_id=args[0],
            gateway_key_id=authenticated_key.gateway_key_id,
            request_id=args[5],
            released=True,
            accounting_status="released",
            error_type=kwargs["error_type"],
            error_code=kwargs.get("error_code"),
        )

    app.dependency_overrides[get_authenticated_gateway_key] = _fake_auth_dependency
    monkeypatch.setattr(dependencies_module, "_get_db_session_after_auth_header_check", _dummy_db_session)
    monkeypatch.setattr(embeddings_module, "_get_db_session_after_auth_header_check", _dummy_db_session)
    monkeypatch.setattr(embeddings_module.RouteResolutionService, "resolve_model", _fake_resolve_model)
    monkeypatch.setattr(
        embeddings_module.PricingService,
        "estimate_embeddings_cost",
        _fake_estimate_embeddings_cost,
    )
    monkeypatch.setattr(embeddings_module.QuotaService, "reserve_for_chat_completion", _fake_reserve)
    monkeypatch.setattr(
        embeddings_module.AccountingService,
        "finalize_successful_response",
        _fake_finalize_successful_response,
    )
    monkeypatch.setattr(
        embeddings_module.AccountingService,
        "finalize_successful_custom_response",
        _fake_finalize_successful_custom_response,
    )
    monkeypatch.setattr(
        embeddings_module.AccountingService,
        "record_provider_failure_and_release",
        _fake_record_provider_failure_and_release,
    )
    return state


def test_chat_responses_and_audio_permissions_do_not_allow_embeddings() -> None:
    app = create_app(Settings())

    async def _fake_auth_dependency() -> AuthenticatedGatewayKey:
        return _auth(
            allowed_endpoints=(
                "/v1/chat/completions",
                "/v1/responses",
                "/v1/audio/speech",
            )
        )

    app.dependency_overrides[get_authenticated_gateway_key] = _fake_auth_dependency

    response = TestClient(app).post(
        "/v1/embeddings",
        json={"model": "text-embedding-3-small", "input": "hello"},
        headers={"Authorization": "Bearer client-gateway-key"},
    )

    assert response.status_code == 403
    assert response.json()["error"]["type"] == "permission_error"


def test_model_permission_alone_does_not_allow_embeddings() -> None:
    app = create_app(Settings())

    async def _fake_auth_dependency() -> AuthenticatedGatewayKey:
        authenticated = _auth(allowed_endpoints=())
        return replace(
            authenticated,
            allow_all_models=False,
            allowed_models=("text-embedding-3-small",),
        )

    app.dependency_overrides[get_authenticated_gateway_key] = _fake_auth_dependency

    response = TestClient(app).post(
        "/v1/embeddings",
        json={"model": "text-embedding-3-small", "input": "hello"},
        headers={"Authorization": "Bearer client-gateway-key"},
    )

    assert response.status_code == 403
    assert response.json()["error"]["type"] == "permission_error"


def test_openai_embeddings_forwarding_uses_resolved_model_and_safe_headers(
    monkeypatch,
    respx_mock,
) -> None:
    settings = Settings(OPENAI_UPSTREAM_API_KEY="openai-upstream-key")
    app = create_app(settings)
    state = _wire_embeddings_pipeline(monkeypatch, app, dimensions_capability=True)

    upstream_route = respx_mock.post("https://api.openai.com/v1/embeddings").mock(
        return_value=httpx.Response(
            200,
            json={
                "object": "list",
                "data": [{"object": "embedding", "embedding": [0.1, 0.2], "index": 0}],
                "model": "text-embedding-3-small",
                "usage": {"prompt_tokens": 4, "total_tokens": 4},
            },
            headers={
                "content-type": "application/json",
                "x-request-id": "upstream-embedding",
                "set-cookie": "should-not-pass",
            },
        )
    )

    response = TestClient(app).post(
        "/v1/embeddings",
        json={
            "model": "classroom-embedding",
            "input": ["hello", "world"],
            "encoding_format": "float",
            "dimensions": 8,
            "user": "learner-1",
        },
        headers={"Authorization": "Bearer client-gateway-key"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert response.headers["x-request-id"]
    assert "set-cookie" not in {name.lower() for name in response.headers}
    assert state["reserve_calls"]
    assert state["finalize_calls"]

    upstream_request = upstream_route.calls[0].request
    assert upstream_request.headers["authorization"] == "Bearer openai-upstream-key"
    assert "client-gateway-key" not in upstream_request.headers["authorization"]
    assert "cookie" not in {name.lower() for name in upstream_request.headers}
    upstream_body = json.loads(upstream_request.content)
    assert upstream_body == {
        "model": "text-embedding-3-small",
        "input": ["hello", "world"],
        "encoding_format": "float",
        "dimensions": 8,
        "user": "learner-1",
    }


def test_embeddings_dimensions_require_explicit_route_capability(monkeypatch) -> None:
    settings = Settings(OPENAI_UPSTREAM_API_KEY="openai-upstream-key")
    app = create_app(settings)
    _wire_embeddings_pipeline(monkeypatch, app, dimensions_capability=False)

    response = TestClient(app).post(
        "/v1/embeddings",
        json={
            "model": "classroom-embedding",
            "input": "hello",
            "dimensions": 8,
        },
        headers={"Authorization": "Bearer client-gateway-key"},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "embeddings_dimensions_not_supported"


def test_openrouter_embeddings_fail_closed(monkeypatch) -> None:
    settings = Settings(OPENROUTER_API_KEY="openrouter-upstream-key")
    app = create_app(settings)
    state = _wire_embeddings_pipeline(monkeypatch, app, provider="openrouter")

    response = TestClient(app).post(
        "/v1/embeddings",
        json={"model": "classroom-embedding", "input": "hello"},
        headers={"Authorization": "Bearer client-gateway-key"},
    )

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "unsupported_provider_endpoint"
    assert state["failure_release_calls"] == ["unsupported_provider_endpoint"]


def test_embeddings_missing_provider_usage_uses_safe_estimated_finalization(
    monkeypatch,
    respx_mock,
) -> None:
    settings = Settings(OPENAI_UPSTREAM_API_KEY="openai-upstream-key")
    app = create_app(settings)
    state = _wire_embeddings_pipeline(monkeypatch, app)

    respx_mock.post("https://api.openai.com/v1/embeddings").mock(
        return_value=httpx.Response(
            200,
            json={
                "object": "list",
                "data": [{"object": "embedding", "embedding": [0.1, 0.2], "index": 0}],
                "model": "text-embedding-3-small",
            },
            headers={"content-type": "application/json"},
        )
    )

    response = TestClient(app).post(
        "/v1/embeddings",
        json={"model": "classroom-embedding", "input": "hello"},
        headers={"Authorization": "Bearer client-gateway-key"},
    )

    assert response.status_code == 200
    assert state["finalize_calls"] == []
    assert len(state["custom_finalize_calls"]) == 1
    _request_id, kwargs = state["custom_finalize_calls"][0]
    assert kwargs["response_metadata_extra"]["embeddings_estimate_reason"] == "usage_missing_estimated"
    assert kwargs["response_metadata_extra"]["provider_usage_available"] is False
