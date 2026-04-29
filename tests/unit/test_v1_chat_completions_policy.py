from __future__ import annotations

import inspect
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

from fastapi.testclient import TestClient

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


def _route_result(requested_model: str = "gpt-4.1-mini") -> RouteResolutionResult:
    return RouteResolutionResult(
        requested_model=requested_model,
        resolved_model=requested_model,
        provider="openai",
        route_id=uuid.uuid4(),
        route_match_type="exact",
        route_pattern=requested_model,
        priority=100,
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
    assert response.json()["error"]["code"] == "input_token_limit_exceeded"


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
