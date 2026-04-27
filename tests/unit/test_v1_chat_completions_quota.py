from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient

from slaif_gateway.api.dependencies import get_authenticated_gateway_key
from slaif_gateway.main import create_app
from slaif_gateway.schemas.auth import AuthenticatedGatewayKey
from slaif_gateway.schemas.pricing import ChatCostEstimate
from slaif_gateway.schemas.providers import ProviderResponse, ProviderUsage
from slaif_gateway.schemas.quota import QuotaReservationResult
from slaif_gateway.schemas.routing import RouteResolutionResult
from slaif_gateway.services.policy_errors import OutputTokenLimitExceededError
from slaif_gateway.services.pricing_errors import PricingRuleNotFoundError
from slaif_gateway.services.quota_errors import QuotaLimitExceededError
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
        rate_limit_policy={},
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


def _estimate() -> ChatCostEstimate:
    return ChatCostEstimate(
        provider="openai",
        requested_model="classroom-cheap",
        resolved_model="gpt-4.1-mini",
        native_currency="EUR",
        estimated_input_tokens=20,
        estimated_output_tokens=30,
        estimated_input_cost_native=Decimal("0.001"),
        estimated_output_cost_native=Decimal("0.002"),
        estimated_total_cost_native=Decimal("0.003"),
        estimated_total_cost_eur=Decimal("0.003"),
        pricing_rule_id=None,
        fx_rate_id=None,
    )


def _chat_request(model: str = "classroom-cheap") -> dict[str, object]:
    return {
        "model": model,
        "messages": [{"role": "user", "content": "hello"}],
        "max_tokens": 20,
    }


def _wire_auth_and_db(monkeypatch, app, authenticated_key: AuthenticatedGatewayKey | None = None) -> None:
    from slaif_gateway.api import dependencies as dependencies_module
    import slaif_gateway.services.chat_completion_gateway as main_module

    key = authenticated_key or _fake_authenticated_gateway_key()

    async def _fake_auth_dependency() -> AuthenticatedGatewayKey:
        return key

    async def _dummy_db_session():
        yield object()

    app.dependency_overrides[get_authenticated_gateway_key] = _fake_auth_dependency
    monkeypatch.setattr(dependencies_module, "_get_db_session_after_auth_header_check", _dummy_db_session)
    monkeypatch.setattr(main_module, "_get_db_session_after_auth_header_check", _dummy_db_session)


def _wire_successful_route_pricing_quota(monkeypatch, *, quota_error=None) -> tuple[list[str], list[str]]:
    import slaif_gateway.services.chat_completion_gateway as main_module

    reserve_calls: list[str] = []
    release_calls: list[str] = []

    async def _fake_resolve_model(self, requested_model, authenticated_key):
        _ = (self, authenticated_key)
        return _route_result(requested_model)

    async def _fake_estimate_chat_completion_cost(self, *, route, policy, endpoint="chat.completions", at=None):
        _ = (self, route, policy, endpoint, at)
        return _estimate()

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
        _ = (self, authenticated_key, policy, cost_estimate, request_id, now)
        reserve_calls.append(route.requested_model)
        if quota_error is not None:
            raise quota_error
        return QuotaReservationResult(
            reservation_id=uuid.uuid4(),
            gateway_key_id=authenticated_key.gateway_key_id,
            request_id=request_id,
            reserved_cost_eur=Decimal("0.003"),
            reserved_tokens=50,
            status="pending",
            expires_at=datetime.now(UTC) + timedelta(minutes=15),
        )

    async def _fake_release(self, reservation_id, *, reason=None, now=None):
        _ = (self, reason, now)
        release_calls.append(str(reservation_id))
        return QuotaReservationResult(
            reservation_id=reservation_id,
            gateway_key_id=uuid.uuid4(),
            request_id="req",
            reserved_cost_eur=Decimal("0.003"),
            reserved_tokens=50,
            status="released",
            expires_at=datetime.now(UTC) + timedelta(minutes=15),
        )

    monkeypatch.setattr(main_module.RouteResolutionService, "resolve_model", _fake_resolve_model)
    monkeypatch.setattr(
        main_module.PricingService,
        "estimate_chat_completion_cost",
        _fake_estimate_chat_completion_cost,
    )
    monkeypatch.setattr(main_module.QuotaService, "reserve_for_chat_completion", _fake_reserve)
    monkeypatch.setattr(main_module.QuotaService, "release_reservation", _fake_release)
    return reserve_calls, release_calls


def _wire_successful_forwarding(monkeypatch) -> list[str]:
    import slaif_gateway.services.chat_completion_gateway as main_module

    finalize_calls: list[str] = []

    class _FakeAdapter:
        async def forward_chat_completion(self, request):
            return ProviderResponse(
                provider=request.provider,
                upstream_model=request.upstream_model,
                status_code=200,
                json_body={"id": "chatcmpl_test"},
                usage=ProviderUsage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
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
            policy,
            pricing_estimate,
            provider_response,
            request_id,
            endpoint,
            started_at,
            finished_at,
        )
        finalize_calls.append(route.requested_model)
        return object()

    monkeypatch.setattr(main_module, "get_provider_adapter", lambda provider, settings: _FakeAdapter())
    monkeypatch.setattr(
        main_module.AccountingService,
        "finalize_successful_response",
        _fake_finalize_successful_response,
    )
    return finalize_calls


def test_valid_path_reserves_finalizes_then_returns_provider_response(monkeypatch) -> None:
    app = create_app()
    _wire_auth_and_db(monkeypatch, app)
    reserve_calls, release_calls = _wire_successful_route_pricing_quota(monkeypatch)
    finalize_calls = _wire_successful_forwarding(monkeypatch)

    response = TestClient(app).post("/v1/chat/completions", json=_chat_request())

    assert response.status_code == 200
    assert response.json()["id"] == "chatcmpl_test"
    assert reserve_calls == ["classroom-cheap"]
    assert release_calls == []
    assert finalize_calls == ["classroom-cheap"]


def test_quota_exceeded_returns_openai_error_before_501(monkeypatch) -> None:
    app = create_app()
    _wire_auth_and_db(monkeypatch, app)
    reserve_calls, release_calls = _wire_successful_route_pricing_quota(
        monkeypatch,
        quota_error=QuotaLimitExceededError("Token quota limit exceeded", param="token_limit_total"),
    )

    response = TestClient(app).post("/v1/chat/completions", json=_chat_request())

    assert response.status_code == 429
    assert response.json()["error"]["type"] == "rate_limit_error"
    assert response.json()["error"]["code"] == "quota_limit_exceeded"
    assert reserve_calls == ["classroom-cheap"]
    assert release_calls == []


def test_pricing_failure_happens_before_quota_reservation(monkeypatch) -> None:
    import slaif_gateway.services.chat_completion_gateway as main_module

    app = create_app()
    _wire_auth_and_db(monkeypatch, app)
    quota_calls: list[str] = []

    async def _fake_resolve_model(self, requested_model, authenticated_key):
        _ = (self, authenticated_key)
        return _route_result(requested_model)

    async def _fake_estimate_chat_completion_cost(self, *, route, policy, endpoint="chat.completions", at=None):
        _ = (self, route, policy, endpoint, at)
        raise PricingRuleNotFoundError(param="model")

    async def _fake_reserve(self, **kwargs):
        _ = self
        quota_calls.append(str(kwargs))

    monkeypatch.setattr(main_module.RouteResolutionService, "resolve_model", _fake_resolve_model)
    monkeypatch.setattr(
        main_module.PricingService,
        "estimate_chat_completion_cost",
        _fake_estimate_chat_completion_cost,
    )
    monkeypatch.setattr(main_module.QuotaService, "reserve_for_chat_completion", _fake_reserve)

    response = TestClient(app).post("/v1/chat/completions", json=_chat_request())

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "pricing_rule_not_found"
    assert quota_calls == []


def test_unsupported_model_happens_before_pricing_or_quota(monkeypatch) -> None:
    import slaif_gateway.services.chat_completion_gateway as main_module

    app = create_app()
    _wire_auth_and_db(monkeypatch, app)
    pricing_calls: list[str] = []
    quota_calls: list[str] = []

    async def _fake_resolve_model(self, requested_model, authenticated_key):
        _ = (self, requested_model, authenticated_key)
        raise ModelNotFoundError()

    async def _fake_estimate_chat_completion_cost(self, **kwargs):
        _ = self
        pricing_calls.append(str(kwargs))

    async def _fake_reserve(self, **kwargs):
        _ = self
        quota_calls.append(str(kwargs))

    monkeypatch.setattr(main_module.RouteResolutionService, "resolve_model", _fake_resolve_model)
    monkeypatch.setattr(
        main_module.PricingService,
        "estimate_chat_completion_cost",
        _fake_estimate_chat_completion_cost,
    )
    monkeypatch.setattr(main_module.QuotaService, "reserve_for_chat_completion", _fake_reserve)

    response = TestClient(app).post("/v1/chat/completions", json=_chat_request("unsupported"))

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "model_not_found"
    assert pricing_calls == []
    assert quota_calls == []


def test_policy_error_happens_before_route_pricing_or_quota(monkeypatch) -> None:
    import slaif_gateway.services.chat_completion_gateway as main_module

    app = create_app()
    _wire_auth_and_db(monkeypatch, app)
    route_calls: list[str] = []
    pricing_calls: list[str] = []
    quota_calls: list[str] = []

    async def _fake_resolve_model(self, requested_model, authenticated_key):
        _ = (self, authenticated_key)
        route_calls.append(requested_model)

    async def _fake_estimate_chat_completion_cost(self, **kwargs):
        _ = self
        pricing_calls.append(str(kwargs))

    async def _fake_reserve(self, **kwargs):
        _ = self
        quota_calls.append(str(kwargs))

    monkeypatch.setattr(main_module.RouteResolutionService, "resolve_model", _fake_resolve_model)
    monkeypatch.setattr(
        main_module.PricingService,
        "estimate_chat_completion_cost",
        _fake_estimate_chat_completion_cost,
    )
    monkeypatch.setattr(main_module.QuotaService, "reserve_for_chat_completion", _fake_reserve)

    response = TestClient(app).post(
        "/v1/chat/completions",
        json={
            "model": "classroom-cheap",
            "messages": [{"role": "user", "content": "hello"}],
            "max_tokens": 999999,
        },
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == OutputTokenLimitExceededError.error_code
    assert route_calls == []
    assert pricing_calls == []
    assert quota_calls == []
