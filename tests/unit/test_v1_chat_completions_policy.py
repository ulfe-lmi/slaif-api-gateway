from __future__ import annotations

import inspect
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from slaif_gateway.config import Settings
from slaif_gateway.main import create_app
from slaif_gateway.schemas.auth import AuthenticatedGatewayKey
from slaif_gateway.schemas.providers import ProviderResponse, ProviderStreamChunk, ProviderUsage
from slaif_gateway.schemas.quota import QuotaReservationResult
from slaif_gateway.schemas.routing import RouteResolutionResult


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


def _wire_auth_and_db(monkeypatch, app) -> None:
    from slaif_gateway.api import dependencies as dependencies_module
    from slaif_gateway.api.dependencies import get_authenticated_gateway_key
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


def _route_result(
    requested_model: str = "gpt-4.1-mini",
    *,
    supports_streaming: bool = True,
    capabilities: dict[str, object] | None = None,
) -> RouteResolutionResult:
    return RouteResolutionResult(
        requested_model=requested_model,
        resolved_model=requested_model,
        provider="openai",
        route_id=uuid.uuid4(),
        route_match_type="exact",
        route_pattern=requested_model,
        priority=100,
        supports_streaming=supports_streaming,
        capabilities=capabilities,
    )


def _wire_successful_pricing(monkeypatch) -> None:
    import slaif_gateway.services.chat_completion_gateway as main_module

    async def _fake_estimate_chat_completion_cost(self, *, route, policy, endpoint="chat.completions", at=None):
        _ = (self, route, policy, endpoint, at)
        return object()

    monkeypatch.setattr(
        main_module.PricingService,
        "estimate_chat_completion_cost",
        _fake_estimate_chat_completion_cost,
    )


def _wire_successful_forwarding(monkeypatch, response_body: dict[str, object] | None = None) -> None:
    import slaif_gateway.services.chat_completion_gateway as main_module

    class _FakeAdapter:
        async def forward_chat_completion(self, request):
            return ProviderResponse(
                provider=request.provider,
                upstream_model=request.upstream_model,
                status_code=200,
                json_body=response_body or {"id": "chatcmpl_test", "object": "chat.completion"},
                usage=ProviderUsage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
            )

        async def stream_chat_completion(self, request):
            yield ProviderStreamChunk(
                provider=request.provider,
                upstream_model=request.upstream_model,
                data='{"id":"chatcmpl_stream","choices":[],"usage":{"prompt_tokens":1,"completion_tokens":1,"total_tokens":2}}',
                raw_sse_event=(
                    'data: {"id":"chatcmpl_stream","choices":[],"usage":'
                    '{"prompt_tokens":1,"completion_tokens":1,"total_tokens":2}}\n\n'
                ),
                json_body={
                    "id": "chatcmpl_stream",
                    "choices": [],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
                },
                usage=ProviderUsage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
            )
            yield ProviderStreamChunk(
                provider=request.provider,
                upstream_model=request.upstream_model,
                data="[DONE]",
                raw_sse_event="data: [DONE]\n\n",
                is_done=True,
            )

    async def _fake_finalize_successful_response(self, *args, **kwargs):
        _ = (self, args, kwargs)
        return object()

    async def _fake_provider_completed(self, *args, **kwargs):
        _ = (self, args, kwargs)
        return SimpleNamespace(usage_ledger_id=uuid.uuid4())

    async def _fake_mark_finalization_failed(self, *args, **kwargs):
        _ = (self, args, kwargs)
        return object()

    monkeypatch.setattr(main_module, "get_provider_adapter", lambda provider, settings: _FakeAdapter())
    monkeypatch.setattr(
        main_module.AccountingService,
        "record_provider_completed_before_finalization",
        _fake_provider_completed,
    )
    monkeypatch.setattr(
        main_module.AccountingService,
        "finalize_successful_response",
        _fake_finalize_successful_response,
    )
    monkeypatch.setattr(
        main_module.AccountingService,
        "mark_provider_completed_finalization_failed",
        _fake_mark_finalization_failed,
    )


def test_unauthenticated_request_returns_openai_shaped_401() -> None:
    app = create_app()
    client = TestClient(app)

    response = client.post("/v1/chat/completions", json={"model": "gpt-4.1-mini", "messages": []})

    assert response.status_code == 401
    body = response.json()
    assert "error" in body
    assert set(body["error"].keys()) == {"message", "type", "param", "code"}


def test_missing_model_returns_openai_shaped_invalid_request_error(monkeypatch) -> None:
    app = create_app()
    _wire_auth_and_db(monkeypatch, app)

    client = TestClient(app)
    response = client.post("/v1/chat/completions", json={"messages": []})

    assert response.status_code == 422
    assert response.json()["error"]["type"] == "invalid_request_error"


def test_missing_messages_returns_openai_shaped_invalid_request_error(monkeypatch) -> None:
    app = create_app()
    _wire_auth_and_db(monkeypatch, app)

    client = TestClient(app)
    response = client.post("/v1/chat/completions", json={"model": "gpt-4.1-mini"})

    assert response.status_code == 422
    assert response.json()["error"]["type"] == "invalid_request_error"


def test_excessive_max_tokens_returns_openai_shaped_invalid_request_error(monkeypatch) -> None:
    app = create_app()
    _wire_auth_and_db(monkeypatch, app)

    client = TestClient(app)
    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "gpt-4.1-mini",
            "messages": [{"role": "user", "content": "hello"}],
            "max_tokens": 999999,
        },
    )

    assert response.status_code == 400
    assert response.json()["error"]["type"] == "invalid_request_error"
    assert response.json()["error"]["code"] == "output_token_limit_exceeded"


def test_excessive_max_completion_tokens_returns_openai_shaped_invalid_request_error(
    monkeypatch,
) -> None:
    app = create_app()
    _wire_auth_and_db(monkeypatch, app)

    client = TestClient(app)
    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "gpt-4.1-mini",
            "messages": [{"role": "user", "content": "hello"}],
            "max_completion_tokens": 999999,
        },
    )

    assert response.status_code == 400
    assert response.json()["error"]["type"] == "invalid_request_error"
    assert response.json()["error"]["code"] == "output_token_limit_exceeded"


def test_excessive_estimated_input_returns_openai_shaped_invalid_request_error(monkeypatch) -> None:
    app = create_app()
    _wire_auth_and_db(monkeypatch, app)

    client = TestClient(app)
    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "gpt-4.1-mini",
            "messages": [{"role": "user", "content": "x" * 500000}],
        },
    )

    assert response.status_code == 400
    assert response.json()["error"]["type"] == "invalid_request_error"
    assert response.json()["error"]["code"] == "chat_field_too_large"


def test_large_tools_schema_rejects_before_redis_route_pricing_quota_or_provider(monkeypatch) -> None:
    import slaif_gateway.services.chat_completion_gateway as main_module

    app = create_app(Settings(HARD_MAX_INPUT_TOKENS=100))
    _wire_auth_and_db(monkeypatch, app)
    calls: list[str] = []

    async def _fake_redis_reserve(**kwargs):
        _ = kwargs
        calls.append("redis")
        return None

    async def _fake_resolve_model(self, requested_model, authenticated_key):
        _ = (self, requested_model, authenticated_key)
        calls.append("route")
        return _route_result()

    async def _fake_estimate_chat_completion_cost(self, *, route, policy, endpoint="chat.completions", at=None):
        _ = (self, route, policy, endpoint, at)
        calls.append("pricing")
        return object()

    async def _fake_reserve(self, *, authenticated_key, route, policy, cost_estimate, request_id, now=None):
        _ = (self, authenticated_key, route, policy, cost_estimate, request_id, now)
        calls.append("quota")
        raise AssertionError("quota reservation should not be called")

    def _fake_get_provider_adapter(route, settings):
        _ = (route, settings)
        calls.append("provider")
        raise AssertionError("provider adapter should not be called")

    monkeypatch.setattr(main_module, "_reserve_redis_rate_limit", _fake_redis_reserve)
    monkeypatch.setattr(main_module.RouteResolutionService, "resolve_model", _fake_resolve_model)
    monkeypatch.setattr(
        main_module.PricingService,
        "estimate_chat_completion_cost",
        _fake_estimate_chat_completion_cost,
    )
    monkeypatch.setattr(main_module.QuotaService, "reserve_for_chat_completion", _fake_reserve)
    monkeypatch.setattr(main_module, "get_provider_adapter", _fake_get_provider_adapter)

    response = TestClient(app).post(
        "/v1/chat/completions",
        json={
            "model": "gpt-4.1-mini",
            "messages": [{"role": "user", "content": "hi"}],
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "lookup",
                        "parameters": {
                            "type": "object",
                            "properties": {"query": {"type": "string", "description": "x" * 300}},
                        },
                    },
                }
            ],
        },
    )

    assert response.status_code == 400
    assert response.json()["error"]["type"] == "invalid_request_error"
    assert response.json()["error"]["code"] == "input_token_limit_exceeded"
    assert response.json()["error"]["param"] == "request"
    assert "description" not in response.json()["error"]["message"]
    assert calls == []


def test_large_response_format_schema_rejects_before_provider_adapter(monkeypatch) -> None:
    import slaif_gateway.services.chat_completion_gateway as main_module

    app = create_app(Settings(HARD_MAX_INPUT_TOKENS=100))
    _wire_auth_and_db(monkeypatch, app)
    provider_calls: list[str] = []

    def _fake_get_provider_adapter(route, settings):
        _ = (route, settings)
        provider_calls.append("provider")
        raise AssertionError("provider adapter should not be called")

    monkeypatch.setattr(main_module, "get_provider_adapter", _fake_get_provider_adapter)

    response = TestClient(app).post(
        "/v1/chat/completions",
        json={
            "model": "gpt-4.1-mini",
            "messages": [{"role": "user", "content": "hi"}],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "answer",
                    "schema": {
                        "type": "object",
                        "properties": {"answer": {"type": "string", "description": "x" * 300}},
                    },
                },
            },
        },
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "input_token_limit_exceeded"
    assert provider_calls == []


def test_multi_choice_count_is_rejected_before_side_effects(monkeypatch) -> None:
    import slaif_gateway.services.chat_completion_gateway as main_module

    app = create_app()
    _wire_auth_and_db(monkeypatch, app)
    calls: list[str] = []

    async def _fake_redis_reserve(**kwargs):
        _ = kwargs
        calls.append("redis")
        return None

    async def _fake_resolve_model(self, requested_model, authenticated_key):
        _ = (self, requested_model, authenticated_key)
        calls.append("route")
        return _route_result()

    async def _fake_estimate_chat_completion_cost(self, *, route, policy, endpoint="chat.completions", at=None):
        _ = (self, route, policy, endpoint, at)
        calls.append("pricing")
        return object()

    async def _fake_reserve(self, *, authenticated_key, route, policy, cost_estimate, request_id, now=None):
        _ = (self, authenticated_key, route, policy, cost_estimate, request_id, now)
        calls.append("quota")
        raise AssertionError("quota reservation should not be called")

    def _fake_get_provider_adapter(route, settings):
        _ = (route, settings)
        calls.append("provider")
        raise AssertionError("provider adapter should not be called")

    monkeypatch.setattr(main_module, "_reserve_redis_rate_limit", _fake_redis_reserve)
    monkeypatch.setattr(main_module.RouteResolutionService, "resolve_model", _fake_resolve_model)
    monkeypatch.setattr(
        main_module.PricingService,
        "estimate_chat_completion_cost",
        _fake_estimate_chat_completion_cost,
    )
    monkeypatch.setattr(main_module.QuotaService, "reserve_for_chat_completion", _fake_reserve)
    monkeypatch.setattr(main_module, "get_provider_adapter", _fake_get_provider_adapter)

    client = TestClient(app)
    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "gpt-4.1-mini",
            "messages": [{"role": "user", "content": "hello"}],
            "n": 2,
        },
    )

    assert response.status_code == 400
    assert response.json()["error"] == {
        "message": "n > 1 is not supported by this gateway until multi-choice quota accounting is implemented.",
        "type": "invalid_request_error",
        "param": "n",
        "code": "invalid_choice_count",
    }
    assert calls == []


@pytest.mark.parametrize(
    ("payload_extra", "expected_code", "expected_param"),
    [
        ({"tools": [{"type": "web_search"}]}, "web_search_not_allowed", "tools[0].type"),
        (
            {"tools": [{"type": "web_search_preview"}]},
            "web_search_not_allowed",
            "tools[0].type",
        ),
        ({"web_search_options": {"search_context_size": "low"}}, "web_search_not_allowed", "web_search_options"),
        ({"model": "gpt-5-search-api"}, "search_model_requires_hosted_web_search", "model"),
        ({"tools": [{"type": "file_search"}]}, "hosted_tool_not_allowed", "tools[0].type"),
        ({"tools": [{"type": "code_interpreter"}]}, "hosted_tool_not_allowed", "tools[0].type"),
        ({"tools": [{"type": "computer"}]}, "hosted_tool_not_allowed", "tools[0].type"),
        ({"tools": [{"type": "computer_use"}]}, "hosted_tool_not_allowed", "tools[0].type"),
        ({"tools": [{"type": "image_generation"}]}, "hosted_tool_not_allowed", "tools[0].type"),
        ({"tools": [{"type": "tool_search"}]}, "hosted_tool_not_allowed", "tools[0].type"),
        ({"tools": [{"type": "mcp"}]}, "mcp_connectors_not_allowed", "tools[0].type"),
        ({"tools": [{"type": "custom"}]}, "custom_tool_not_supported", "tools[0].type"),
        (
            {"tools": [{"type": "function", "function": {"name": "lookup"}, "server_url": "https://mcp.test"}]},
            "mcp_connectors_not_allowed",
            "tools[0].server_url",
        ),
        (
            {"tools": [{"type": "function", "function": {"name": "lookup"}, "connector_id": "conn_123"}]},
            "mcp_connectors_not_allowed",
            "tools[0].connector_id",
        ),
        (
            {"tools": [{"type": "function", "function": {"name": "lookup"}, "authorization": "Bearer sk-live"}]},
            "mcp_connectors_not_allowed",
            "tools[0].authorization",
        ),
        (
            {"tools": [{"type": "function", "function": {"name": "lookup"}, "require_approval": True}]},
            "mcp_connectors_not_allowed",
            "tools[0].require_approval",
        ),
        ({"tools": [{"type": "unknown_hosted"}]}, "unknown_tool_type_not_allowed", "tools[0].type"),
        ({"background": True}, "background_not_allowed", "background"),
        ({"store": True}, "background_not_allowed", "store"),
        ({"previous_response_id": "resp_123"}, "background_not_allowed", "previous_response_id"),
        ({"conversation": "conv_123"}, "background_not_allowed", "conversation"),
        ({"service_tier": "flex"}, "service_tier_not_supported", "service_tier"),
        ({"metadata": {"oversized": "raw request body marker" * 2000}}, "chat_metadata_too_large", "metadata"),
        ({"x_future": {"secret": "raw request body marker"}}, "unknown_chat_completion_field", "x_future"),
        ({"audio": {"voice": "alloy"}}, "unsupported_chat_completion_modality", "audio"),
    ],
)
def test_hosted_tool_policy_rejects_before_redis_route_pricing_quota_or_provider(
    monkeypatch,
    payload_extra: dict[str, object],
    expected_code: str,
    expected_param: str,
) -> None:
    import slaif_gateway.services.chat_completion_gateway as main_module

    app = create_app()
    _wire_auth_and_db(monkeypatch, app)
    calls: list[str] = []

    async def _fake_redis_reserve(**kwargs):
        _ = kwargs
        calls.append("redis")
        return None

    async def _fake_resolve_model(self, requested_model, authenticated_key):
        _ = (self, requested_model, authenticated_key)
        calls.append("route")
        return _route_result()

    async def _fake_estimate_chat_completion_cost(self, *, route, policy, endpoint="chat.completions", at=None):
        _ = (self, route, policy, endpoint, at)
        calls.append("pricing")
        return object()

    async def _fake_reserve(self, *, authenticated_key, route, policy, cost_estimate, request_id, now=None):
        _ = (self, authenticated_key, route, policy, cost_estimate, request_id, now)
        calls.append("quota")
        raise AssertionError("quota reservation should not be called")

    def _fake_get_provider_adapter(route, settings):
        _ = (route, settings)
        calls.append("provider")
        raise AssertionError("provider adapter should not be called")

    monkeypatch.setattr(main_module, "_reserve_redis_rate_limit", _fake_redis_reserve)
    monkeypatch.setattr(main_module.RouteResolutionService, "resolve_model", _fake_resolve_model)
    monkeypatch.setattr(
        main_module.PricingService,
        "estimate_chat_completion_cost",
        _fake_estimate_chat_completion_cost,
    )
    monkeypatch.setattr(main_module.QuotaService, "reserve_for_chat_completion", _fake_reserve)
    monkeypatch.setattr(main_module, "get_provider_adapter", _fake_get_provider_adapter)

    payload = {
        "model": "gpt-4.1-mini",
        "messages": [{"role": "user", "content": "raw request body marker sk-slaif-secret"}],
        **payload_extra,
    }
    response = TestClient(app).post(
        "/v1/chat/completions",
        json=payload,
        headers={
            "Authorization": "Bearer sk-slaif-raw-gateway-key",
            "Cookie": "session_token=raw-session-token",
            "X-CSRF-Token": "csrf_token_raw",
        },
    )

    assert response.status_code == 400
    assert response.json()["error"]["type"] == "invalid_request_error"
    assert response.json()["error"]["code"] == expected_code
    assert response.json()["error"]["param"] == expected_param
    assert calls == []
    response_text = response.text
    for forbidden in (
        "raw request body marker",
        "sk-slaif-raw-gateway-key",
        "raw-session-token",
        "csrf_token_raw",
        "Bearer sk-live",
        "https://mcp.test",
    ):
        assert forbidden not in response_text


def test_request_caps_reject_before_redis_route_pricing_quota_or_provider(monkeypatch) -> None:
    import slaif_gateway.services.chat_completion_gateway as main_module

    app = create_app(Settings(CHAT_MAX_MESSAGE_CONTENT_BYTES=8))
    _wire_auth_and_db(monkeypatch, app)
    calls: list[str] = []

    async def _fake_redis_reserve(**kwargs):
        _ = kwargs
        calls.append("redis")
        return None

    async def _fake_resolve_model(self, requested_model, authenticated_key):
        _ = (self, requested_model, authenticated_key)
        calls.append("route")
        return _route_result()

    async def _fake_estimate_chat_completion_cost(self, *, route, policy, endpoint="chat.completions", at=None):
        _ = (self, route, policy, endpoint, at)
        calls.append("pricing")
        return object()

    async def _fake_reserve(self, *, authenticated_key, route, policy, cost_estimate, request_id, now=None):
        _ = (self, authenticated_key, route, policy, cost_estimate, request_id, now)
        calls.append("quota")
        raise AssertionError("quota reservation should not be called")

    def _fake_get_provider_adapter(route, settings):
        _ = (route, settings)
        calls.append("provider")
        raise AssertionError("provider adapter should not be called")

    monkeypatch.setattr(main_module, "_reserve_redis_rate_limit", _fake_redis_reserve)
    monkeypatch.setattr(main_module.RouteResolutionService, "resolve_model", _fake_resolve_model)
    monkeypatch.setattr(
        main_module.PricingService,
        "estimate_chat_completion_cost",
        _fake_estimate_chat_completion_cost,
    )
    monkeypatch.setattr(main_module.QuotaService, "reserve_for_chat_completion", _fake_reserve)
    monkeypatch.setattr(main_module, "get_provider_adapter", _fake_get_provider_adapter)

    response = TestClient(app).post(
        "/v1/chat/completions",
        json={
            "model": "gpt-4.1-mini",
            "messages": [{"role": "user", "content": "raw request body marker"}],
        },
        headers={"Authorization": "Bearer sk-slaif-raw-gateway-key"},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "chat_field_too_large"
    assert response.json()["error"]["param"] == "messages[0].content"
    assert calls == []


def test_route_capability_mismatch_rejects_before_redis_pricing_quota_or_provider(monkeypatch) -> None:
    import slaif_gateway.services.chat_completion_gateway as main_module

    app = create_app()
    _wire_auth_and_db(monkeypatch, app)
    calls: list[str] = []

    async def _fake_redis_reserve(**kwargs):
        _ = kwargs
        calls.append("redis")
        return None

    async def _fake_resolve_model(self, requested_model, authenticated_key):
        _ = (self, authenticated_key)
        calls.append("route")
        return _route_result(
            requested_model,
            capabilities={"chat_completions": {"chat_text": False}},
        )

    async def _fake_estimate_chat_completion_cost(self, *, route, policy, endpoint="chat.completions", at=None):
        _ = (self, route, policy, endpoint, at)
        calls.append("pricing")
        return object()

    async def _fake_reserve(self, *, authenticated_key, route, policy, cost_estimate, request_id, now=None):
        _ = (self, authenticated_key, route, policy, cost_estimate, request_id, now)
        calls.append("quota")
        raise AssertionError("quota reservation should not be called")

    def _fake_get_provider_adapter(route, settings):
        _ = (route, settings)
        calls.append("provider")
        raise AssertionError("provider adapter should not be called")

    monkeypatch.setattr(main_module, "_reserve_redis_rate_limit", _fake_redis_reserve)
    monkeypatch.setattr(main_module.RouteResolutionService, "resolve_model", _fake_resolve_model)
    monkeypatch.setattr(
        main_module.PricingService,
        "estimate_chat_completion_cost",
        _fake_estimate_chat_completion_cost,
    )
    monkeypatch.setattr(main_module.QuotaService, "reserve_for_chat_completion", _fake_reserve)
    monkeypatch.setattr(main_module, "get_provider_adapter", _fake_get_provider_adapter)

    response = TestClient(app).post(
        "/v1/chat/completions",
        json={
            "model": "gpt-4.1-mini",
            "messages": [{"role": "user", "content": "raw prompt marker"}],
        },
        headers={"Authorization": "Bearer sk-slaif-raw-gateway-key"},
    )

    assert response.status_code == 400
    assert response.json()["error"] == {
        "message": "This model route does not support text Chat Completions.",
        "type": "invalid_request_error",
        "param": "model",
        "code": "chat_capability_not_supported",
    }
    assert calls == ["route"]
    assert "raw prompt marker" not in response.text
    assert "sk-slaif-raw-gateway-key" not in response.text


def test_unsupported_model_returns_openai_shaped_route_error(monkeypatch) -> None:
    import slaif_gateway.services.chat_completion_gateway as main_module
    from slaif_gateway.services.routing_errors import ModelNotFoundError

    app = create_app()
    _wire_auth_and_db(monkeypatch, app)

    async def _fake_resolve_model(self, requested_model, authenticated_key):
        _ = (requested_model, authenticated_key)
        raise ModelNotFoundError()

    monkeypatch.setattr(main_module.RouteResolutionService, "resolve_model", _fake_resolve_model)

    client = TestClient(app)
    response = client.post(
        "/v1/chat/completions",
        json={"model": "nope", "messages": [{"role": "user", "content": "hi"}]},
    )

    assert response.status_code == 404
    assert response.json()["error"]["type"] == "invalid_request_error"


def test_valid_request_with_no_output_limit_reaches_route_resolution_then_forwards(monkeypatch) -> None:
    import slaif_gateway.services.chat_completion_gateway as main_module

    app = create_app()
    resolver_calls: list[str] = []
    _wire_auth_and_db(monkeypatch, app)

    async def _fake_resolve_model(self, requested_model, authenticated_key):
        _ = authenticated_key
        resolver_calls.append(requested_model)
        return _route_result(requested_model)

    monkeypatch.setattr(main_module.RouteResolutionService, "resolve_model", _fake_resolve_model)
    _wire_successful_pricing(monkeypatch)
    _wire_successful_forwarding(monkeypatch)

    client = TestClient(app)
    response = client.post(
        "/v1/chat/completions",
        json={"model": "gpt-4.1-mini", "messages": [{"role": "user", "content": "hi"}]},
    )

    assert resolver_calls == ["gpt-4.1-mini"]
    assert response.status_code == 200
    assert response.json()["id"] == "chatcmpl_test"


def test_valid_request_with_route_returns_provider_response(monkeypatch) -> None:
    import slaif_gateway.services.chat_completion_gateway as main_module

    app = create_app()
    _wire_auth_and_db(monkeypatch, app)

    async def _fake_resolve_model(self, requested_model, authenticated_key):
        _ = (requested_model, authenticated_key)
        return _route_result(requested_model)

    monkeypatch.setattr(main_module.RouteResolutionService, "resolve_model", _fake_resolve_model)
    _wire_successful_pricing(monkeypatch)
    _wire_successful_forwarding(monkeypatch, {"id": "chatcmpl_ok", "choices": []})

    client = TestClient(app)
    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "gpt-4.1-mini",
            "messages": [{"role": "user", "content": "hello"}],
            "max_tokens": 20,
        },
    )

    assert response.status_code == 200
    assert response.json() == {"id": "chatcmpl_ok", "choices": []}


def test_stream_true_reaches_route_resolution_and_streams(monkeypatch) -> None:
    import slaif_gateway.services.chat_completion_gateway as main_module

    app = create_app()
    _wire_auth_and_db(monkeypatch, app)
    route_calls: list[str] = []

    async def _fake_resolve_model(self, requested_model, authenticated_key):
        _ = (requested_model, authenticated_key)
        route_calls.append(requested_model)
        return _route_result(requested_model)

    monkeypatch.setattr(main_module.RouteResolutionService, "resolve_model", _fake_resolve_model)
    _wire_successful_pricing(monkeypatch)
    _wire_successful_forwarding(monkeypatch)

    client = TestClient(app)
    with client.stream(
        "POST",
        "/v1/chat/completions",
        json={"model": "gpt-4.1-mini", "messages": [{"role": "user", "content": "hi"}], "stream": True},
    ) as response:
        body = "".join(response.iter_text())

    assert response.status_code == 200
    assert "data: [DONE]" in body
    assert route_calls == ["gpt-4.1-mini"]


def test_chat_completions_module_safety_constraints() -> None:
    import slaif_gateway.services.chat_completion_gateway as main_module

    source = inspect.getsource(main_module).lower()

    for disallowed in (
        "httpx",
        "openai_upstream",
        "celery",
        "aiosmtplib",
    ):
        assert disallowed not in source
