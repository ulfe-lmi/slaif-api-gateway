from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient

from slaif_gateway.api.dependencies import get_authenticated_gateway_key
from slaif_gateway.main import create_app
from slaif_gateway.schemas.accounting import FinalizedAccountingResult
from slaif_gateway.schemas.auth import AuthenticatedGatewayKey
from slaif_gateway.schemas.pricing import ChatCostEstimate
from slaif_gateway.schemas.providers import ProviderResponse, ProviderStreamChunk, ProviderUsage
from slaif_gateway.schemas.quota import QuotaReservationResult
from slaif_gateway.schemas.routing import RouteResolutionResult
from slaif_gateway.services.pricing_errors import PricingRuleNotFoundError
from slaif_gateway.services.quota_errors import QuotaLimitExceededError
from slaif_gateway.services.responses_route_capabilities import default_responses_capabilities
from slaif_gateway.services.routing_errors import ModelNotFoundError


def _fake_authenticated_gateway_key(
    *,
    allowed_endpoints: tuple[str, ...] = ("/v1/responses",),
) -> AuthenticatedGatewayKey:
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
        allow_all_endpoints=False,
        allowed_endpoints=allowed_endpoints,
        allowed_providers=None,
        cost_limit_eur=None,
        token_limit_total=None,
        request_limit_total=None,
        rate_limit_policy={},
    )


def _route_result(
    requested_model: str = "classroom-responses",
    *,
    responses_streaming: bool = False,
    route_supports_streaming: bool = False,
) -> RouteResolutionResult:
    capabilities = default_responses_capabilities()
    capabilities["streaming"] = responses_streaming
    return RouteResolutionResult(
        requested_model=requested_model,
        resolved_model="gpt-5.2",
        provider="openai",
        route_id=uuid.uuid4(),
        route_match_type="exact",
        route_pattern=requested_model,
        priority=100,
        capabilities={"responses": capabilities},
        supports_streaming=route_supports_streaming,
    )


def _estimate() -> ChatCostEstimate:
    return ChatCostEstimate(
        provider="openai",
        requested_model="classroom-responses",
        resolved_model="gpt-5.2",
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


def _responses_request(model: str = "classroom-responses") -> dict[str, object]:
    return {
        "model": model,
        "input": "hello",
        "max_output_tokens": 20,
    }


def _wire_auth_and_db(monkeypatch, app, authenticated_key: AuthenticatedGatewayKey | None = None) -> None:
    from slaif_gateway.api import dependencies as dependencies_module
    import slaif_gateway.services.responses_gateway as main_module

    key = authenticated_key or _fake_authenticated_gateway_key()

    async def _fake_auth_dependency() -> AuthenticatedGatewayKey:
        return key

    async def _dummy_db_session():
        yield object()

    app.dependency_overrides[get_authenticated_gateway_key] = _fake_auth_dependency
    monkeypatch.setattr(dependencies_module, "_get_db_session_after_auth_header_check", _dummy_db_session)
    monkeypatch.setattr(main_module, "_get_db_session_after_auth_header_check", _dummy_db_session)


def _wire_successful_route_pricing_quota(monkeypatch, *, quota_error=None) -> tuple[list[str], list[str]]:
    import slaif_gateway.services.responses_gateway as main_module

    reserve_calls: list[str] = []
    release_calls: list[str] = []

    async def _fake_resolve_model(self, requested_model, authenticated_key, *, endpoint="/v1/chat/completions"):
        _ = (self, authenticated_key)
        assert endpoint == "/v1/responses"
        return _route_result(requested_model)

    async def _fake_estimate_chat_completion_cost(self, *, route, policy, endpoint="chat.completions", at=None):
        _ = (self, route, policy, at)
        assert endpoint == "/v1/responses"
        return _estimate()

    async def _fake_reserve(
        self,
        *,
        authenticated_key,
        route,
        policy,
        cost_estimate,
        request_id,
        endpoint="/v1/chat/completions",
        now=None,
    ):
        _ = (self, authenticated_key, policy, cost_estimate, request_id, now)
        assert endpoint == "/v1/responses"
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
    import slaif_gateway.services.responses_gateway as main_module

    finalize_calls: list[str] = []

    class _FakeAdapter:
        async def forward_response(self, request):
            assert request.endpoint == "responses"
            assert request.body["store"] is False
            return ProviderResponse(
                provider=request.provider,
                upstream_model=request.upstream_model,
                status_code=200,
                json_body={"id": "resp_test", "object": "response"},
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
        provider_completed_usage_ledger_id=None,
        streaming=False,
    ):
        _ = (
            self,
            reservation_id,
            authenticated_key,
            policy,
            pricing_estimate,
            provider_response,
            request_id,
            started_at,
            finished_at,
            provider_completed_usage_ledger_id,
            streaming,
        )
        assert endpoint == "responses"
        finalize_calls.append(route.requested_model)
        return FinalizedAccountingResult(
            usage_ledger_id=uuid.uuid4(),
            reservation_id=reservation_id,
            gateway_key_id=authenticated_key.gateway_key_id,
            request_id=request_id,
            estimated_cost_eur=Decimal("0.003"),
            actual_cost_eur=Decimal("0.003"),
            actual_cost_native=Decimal("0.003"),
            native_currency="EUR",
            prompt_tokens=1,
            completion_tokens=1,
            total_tokens=2,
            accounting_status="finalized",
        )

    monkeypatch.setattr(main_module, "get_provider_adapter", lambda provider, settings: _FakeAdapter())
    monkeypatch.setattr(
        main_module.AccountingService,
        "finalize_successful_response",
        _fake_finalize_successful_response,
    )
    return finalize_calls


def test_valid_responses_path_reserves_finalizes_then_returns_provider_response(monkeypatch) -> None:
    app = create_app()
    _wire_auth_and_db(monkeypatch, app)
    reserve_calls, release_calls = _wire_successful_route_pricing_quota(monkeypatch)
    finalize_calls = _wire_successful_forwarding(monkeypatch)

    response = TestClient(app).post("/v1/responses", json=_responses_request())

    assert response.status_code == 200
    assert response.json()["id"] == "resp_test"
    assert reserve_calls == ["classroom-responses"]
    assert release_calls == []
    assert finalize_calls == ["classroom-responses"]


def test_streaming_responses_path_finalizes_from_completed_usage(monkeypatch) -> None:
    import slaif_gateway.services.responses_gateway as main_module

    app = create_app()
    _wire_auth_and_db(monkeypatch, app)
    reserve_calls, release_calls = _wire_successful_route_pricing_quota(monkeypatch)
    finalize_calls: list[tuple[str, bool, uuid.UUID | None]] = []
    completed_record_id = uuid.uuid4()

    async def _fake_resolve_model(self, requested_model, authenticated_key, *, endpoint="/v1/chat/completions"):
        _ = (self, authenticated_key, endpoint)
        return _route_result(
            requested_model,
            responses_streaming=True,
            route_supports_streaming=True,
        )

    class _FakeAdapter:
        async def stream_response(self, request):
            assert request.endpoint == "responses"
            assert request.body == {
                "model": "gpt-5.2",
                "input": "hello",
                "max_output_tokens": 20,
                "stream": True,
                "store": False,
            }
            yield ProviderStreamChunk(
                provider=request.provider,
                upstream_model=request.upstream_model,
                data='{"type":"response.created","response":{"id":"resp_test"}}',
                raw_sse_event='data: {"type":"response.created","response":{"id":"resp_test"}}\n\n',
                json_body={"type": "response.created", "response": {"id": "resp_test"}},
                upstream_request_id="upstream-responses-stream",
            )
            yield ProviderStreamChunk(
                provider=request.provider,
                upstream_model=request.upstream_model,
                data='{"type":"response.output_text.delta","delta":"hello"}',
                raw_sse_event='data: {"type":"response.output_text.delta","delta":"hello"}\n\n',
                json_body={"type": "response.output_text.delta", "delta": "hello"},
                upstream_request_id="upstream-responses-stream",
            )
            yield ProviderStreamChunk(
                provider=request.provider,
                upstream_model=request.upstream_model,
                data='{"type":"response.completed","response":{"id":"resp_test"}}',
                raw_sse_event='data: {"type":"response.completed","response":{"id":"resp_test"}}\n\n',
                json_body={"type": "response.completed", "response": {"id": "resp_test"}},
                usage=ProviderUsage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
                upstream_request_id="upstream-responses-stream",
            )

    async def _fake_record_provider_completed_before_finalization(
        self,
        reservation_id,
        authenticated_key,
        route,
        pricing_estimate,
        provider_response,
        request_id,
        endpoint="chat.completions",
        streaming=False,
        started_at=None,
        finished_at=None,
    ):
        _ = (
            self,
            reservation_id,
            authenticated_key,
            route,
            pricing_estimate,
            request_id,
            started_at,
            finished_at,
        )
        assert endpoint == "responses"
        assert streaming is True
        assert provider_response.usage is not None
        return type(
            "ProviderCompletedRecord",
            (),
            {"usage_ledger_id": completed_record_id},
        )()

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
        provider_completed_usage_ledger_id=None,
        streaming=False,
    ):
        _ = (
            self,
            reservation_id,
            authenticated_key,
            policy,
            pricing_estimate,
            provider_response,
            request_id,
            started_at,
            finished_at,
        )
        assert endpoint == "responses"
        finalize_calls.append((route.requested_model, streaming, provider_completed_usage_ledger_id))
        return FinalizedAccountingResult(
            usage_ledger_id=uuid.uuid4(),
            reservation_id=reservation_id,
            gateway_key_id=authenticated_key.gateway_key_id,
            request_id=request_id,
            estimated_cost_eur=Decimal("0.003"),
            actual_cost_eur=Decimal("0.003"),
            actual_cost_native=Decimal("0.003"),
            native_currency="EUR",
            prompt_tokens=1,
            completion_tokens=1,
            total_tokens=2,
            accounting_status="finalized",
        )

    monkeypatch.setattr(main_module.RouteResolutionService, "resolve_model", _fake_resolve_model)
    monkeypatch.setattr(main_module, "get_provider_adapter", lambda route, settings: _FakeAdapter())
    monkeypatch.setattr(
        main_module.AccountingService,
        "record_provider_completed_before_finalization",
        _fake_record_provider_completed_before_finalization,
    )
    monkeypatch.setattr(
        main_module.AccountingService,
        "finalize_successful_response",
        _fake_finalize_successful_response,
    )

    response = TestClient(app).post(
        "/v1/responses",
        json={**_responses_request(), "stream": True},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    body = response.text
    assert "response.created" in body
    assert "response.output_text.delta" in body
    assert "response.completed" in body
    assert reserve_calls == ["classroom-responses"]
    assert release_calls == []
    assert finalize_calls == [("classroom-responses", True, completed_record_id)]


def test_chat_endpoint_permission_does_not_allow_responses(monkeypatch) -> None:
    app = create_app()
    _wire_auth_and_db(
        monkeypatch,
        app,
        _fake_authenticated_gateway_key(allowed_endpoints=("/v1/chat/completions",)),
    )
    _wire_successful_route_pricing_quota(monkeypatch)
    _wire_successful_forwarding(monkeypatch)

    response = TestClient(app).post("/v1/responses", json=_responses_request())

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "endpoint_not_allowed"


def test_policy_error_happens_before_route_pricing_or_quota(monkeypatch) -> None:
    import slaif_gateway.services.responses_gateway as main_module

    app = create_app()
    _wire_auth_and_db(monkeypatch, app)
    route_calls: list[str] = []
    pricing_calls: list[str] = []
    quota_calls: list[str] = []

    async def _fake_resolve_model(self, requested_model, authenticated_key, *, endpoint="/v1/chat/completions"):
        _ = (self, authenticated_key, endpoint)
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
        "/v1/responses",
        json={**_responses_request(), "store": True},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "responses_store_not_supported"
    assert route_calls == []
    assert pricing_calls == []
    assert quota_calls == []


def test_streaming_capability_error_happens_before_rate_pricing_quota_provider(monkeypatch) -> None:
    import slaif_gateway.services.responses_gateway as main_module

    app = create_app()
    _wire_auth_and_db(monkeypatch, app)
    rate_calls: list[str] = []
    pricing_calls: list[str] = []
    quota_calls: list[str] = []
    provider_calls: list[str] = []

    async def _fake_resolve_model(self, requested_model, authenticated_key, *, endpoint="/v1/chat/completions"):
        _ = (self, authenticated_key, endpoint)
        return _route_result(requested_model)

    async def _fake_reserve_rate_limit(**kwargs):
        rate_calls.append(str(kwargs))

    async def _fake_estimate_chat_completion_cost(self, **kwargs):
        _ = self
        pricing_calls.append(str(kwargs))

    async def _fake_reserve(self, **kwargs):
        _ = self
        quota_calls.append(str(kwargs))

    def _fake_get_provider_adapter(route, settings):
        _ = (route, settings)
        provider_calls.append("provider")
        raise AssertionError("provider adapter should not be called")

    monkeypatch.setattr(main_module.RouteResolutionService, "resolve_model", _fake_resolve_model)
    monkeypatch.setattr(main_module, "_reserve_redis_rate_limit", _fake_reserve_rate_limit)
    monkeypatch.setattr(
        main_module.PricingService,
        "estimate_chat_completion_cost",
        _fake_estimate_chat_completion_cost,
    )
    monkeypatch.setattr(main_module.QuotaService, "reserve_for_chat_completion", _fake_reserve)
    monkeypatch.setattr(main_module, "get_provider_adapter", _fake_get_provider_adapter)

    response = TestClient(app).post(
        "/v1/responses",
        json={**_responses_request(), "stream": True},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "responses_route_capability_not_supported"
    assert rate_calls == []
    assert pricing_calls == []
    assert quota_calls == []
    assert provider_calls == []


def test_route_capability_error_happens_before_pricing_quota_provider(monkeypatch) -> None:
    import slaif_gateway.services.responses_gateway as main_module

    app = create_app()
    _wire_auth_and_db(monkeypatch, app)
    pricing_calls: list[str] = []
    quota_calls: list[str] = []
    provider_calls: list[str] = []

    async def _fake_resolve_model(self, requested_model, authenticated_key, *, endpoint="/v1/chat/completions"):
        _ = (self, authenticated_key, endpoint)
        return RouteResolutionResult(
            requested_model=requested_model,
            resolved_model="gpt-5.2",
            provider="openai",
            route_id=uuid.uuid4(),
            route_match_type="exact",
            route_pattern=requested_model,
            priority=100,
            capabilities={"chat_completions": {"chat_text": True}},
        )

    async def _fake_estimate_chat_completion_cost(self, **kwargs):
        _ = self
        pricing_calls.append(str(kwargs))

    async def _fake_reserve(self, **kwargs):
        _ = self
        quota_calls.append(str(kwargs))

    def _fake_get_provider_adapter(route, settings):
        _ = (route, settings)
        provider_calls.append("provider")
        raise AssertionError("provider adapter should not be called")

    monkeypatch.setattr(main_module.RouteResolutionService, "resolve_model", _fake_resolve_model)
    monkeypatch.setattr(
        main_module.PricingService,
        "estimate_chat_completion_cost",
        _fake_estimate_chat_completion_cost,
    )
    monkeypatch.setattr(main_module.QuotaService, "reserve_for_chat_completion", _fake_reserve)
    monkeypatch.setattr(main_module, "get_provider_adapter", _fake_get_provider_adapter)

    response = TestClient(app).post("/v1/responses", json=_responses_request())

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "responses_route_capability_missing"
    assert pricing_calls == []
    assert quota_calls == []
    assert provider_calls == []


def test_pricing_failure_happens_before_quota_reservation(monkeypatch) -> None:
    import slaif_gateway.services.responses_gateway as main_module

    app = create_app()
    _wire_auth_and_db(monkeypatch, app)
    quota_calls: list[str] = []

    async def _fake_resolve_model(self, requested_model, authenticated_key, *, endpoint="/v1/chat/completions"):
        _ = (self, authenticated_key, endpoint)
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

    response = TestClient(app).post("/v1/responses", json=_responses_request())

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "pricing_rule_not_found"
    assert quota_calls == []


def test_unsupported_model_happens_before_pricing_or_quota(monkeypatch) -> None:
    import slaif_gateway.services.responses_gateway as main_module

    app = create_app()
    _wire_auth_and_db(monkeypatch, app)
    pricing_calls: list[str] = []
    quota_calls: list[str] = []

    async def _fake_resolve_model(self, requested_model, authenticated_key, *, endpoint="/v1/chat/completions"):
        _ = (self, requested_model, authenticated_key, endpoint)
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

    response = TestClient(app).post("/v1/responses", json=_responses_request("unsupported"))

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "model_not_found"
    assert pricing_calls == []
    assert quota_calls == []


def test_quota_exceeded_returns_openai_error(monkeypatch) -> None:
    app = create_app()
    _wire_auth_and_db(monkeypatch, app)
    reserve_calls, release_calls = _wire_successful_route_pricing_quota(
        monkeypatch,
        quota_error=QuotaLimitExceededError("Token quota limit exceeded", param="token_limit_total"),
    )

    response = TestClient(app).post("/v1/responses", json=_responses_request())

    assert response.status_code == 429
    assert response.json()["error"]["code"] == "quota_limit_exceeded"
    assert reserve_calls == ["classroom-responses"]
    assert release_calls == []
