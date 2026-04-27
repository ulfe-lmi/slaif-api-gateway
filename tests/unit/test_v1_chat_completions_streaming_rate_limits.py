from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient

from slaif_gateway.api.dependencies import get_authenticated_gateway_key
from slaif_gateway.config import Settings
from slaif_gateway.main import create_app
from slaif_gateway.providers.errors import ProviderTimeoutError
from slaif_gateway.schemas.auth import AuthenticatedGatewayKey
from slaif_gateway.schemas.providers import ProviderStreamChunk, ProviderUsage
from slaif_gateway.schemas.quota import QuotaReservationResult
from slaif_gateway.schemas.rate_limits import RateLimitResult
from slaif_gateway.schemas.routing import RouteResolutionResult
from slaif_gateway.services.rate_limit_errors import RequestRateLimitExceededError


class _FakeRedis:
    pass


def _auth(policy: dict[str, int | None] | None = None) -> AuthenticatedGatewayKey:
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
        rate_limit_policy=policy or {"max_concurrent_requests": 1},
    )


def _route() -> RouteResolutionResult:
    return RouteResolutionResult(
        requested_model="classroom-cheap",
        resolved_model="gpt-4.1-mini",
        provider="openai",
        route_id=uuid.uuid4(),
        route_match_type="exact",
        route_pattern="classroom-cheap",
        priority=100,
    )


def _chat_request() -> dict[str, object]:
    return {
        "model": "classroom-cheap",
        "messages": [{"role": "user", "content": "hello"}],
        "stream": True,
        "max_tokens": 20,
    }


def _usage_chunks() -> list[ProviderStreamChunk]:
    return [
        ProviderStreamChunk(
            provider="openai",
            upstream_model="gpt-4.1-mini",
            data='{"id":"chunk","choices":[{"delta":{"content":"hi"}}]}',
            raw_sse_event='data: {"id":"chunk","choices":[{"delta":{"content":"hi"}}]}\n\n',
        ),
        ProviderStreamChunk(
            provider="openai",
            upstream_model="gpt-4.1-mini",
            data='{"id":"usage","choices":[],"usage":{"prompt_tokens":5,"completion_tokens":6,"total_tokens":11}}',
            raw_sse_event=(
                'data: {"id":"usage","choices":[],"usage":'
                '{"prompt_tokens":5,"completion_tokens":6,"total_tokens":11}}\n\n'
            ),
            json_body={
                "id": "usage",
                "choices": [],
                "usage": {"prompt_tokens": 5, "completion_tokens": 6, "total_tokens": 11},
            },
            usage=ProviderUsage(prompt_tokens=5, completion_tokens=6, total_tokens=11),
        ),
        ProviderStreamChunk(
            provider="openai",
            upstream_model="gpt-4.1-mini",
            data="[DONE]",
            raw_sse_event="data: [DONE]\n\n",
            is_done=True,
        ),
    ]


def _wire_streaming_pipeline(monkeypatch, app, *, auth, chunks=None, provider_error=None):
    from slaif_gateway.api import dependencies as dependencies_module
    import slaif_gateway.services.chat_completion_gateway as gateway_module

    state = {
        "route_calls": [],
        "reserve_calls": [],
        "stream_calls": [],
        "finalize_calls": [],
        "failure_calls": [],
    }

    class _Session:
        async def commit(self) -> None:
            return None

    async def _fake_auth_dependency() -> AuthenticatedGatewayKey:
        return auth

    async def _dummy_db_session():
        yield _Session()

    async def _fake_resolve_model(self, requested_model, authenticated_key):
        _ = (self, authenticated_key)
        state["route_calls"].append(requested_model)
        return _route()

    async def _fake_estimate(self, *, route, policy, endpoint="chat.completions", at=None):
        _ = (self, route, policy, endpoint, at)
        return object()

    async def _fake_reserve(self, *, authenticated_key, route, policy, cost_estimate, request_id, now=None):
        _ = (self, authenticated_key, route, policy, cost_estimate, now)
        state["reserve_calls"].append(request_id)
        return QuotaReservationResult(
            reservation_id=uuid.uuid4(),
            gateway_key_id=auth.gateway_key_id,
            request_id=request_id,
            reserved_cost_eur=Decimal("0.001"),
            reserved_tokens=70,
            status="pending",
            expires_at=datetime.now(UTC) + timedelta(minutes=15),
        )

    async def _fake_finalize(self, *args, **kwargs):
        _ = (self, args)
        state["finalize_calls"].append(kwargs)
        return object()

    async def _fake_failure(self, *args, **kwargs):
        _ = (self, args)
        state["failure_calls"].append(kwargs)
        return object()

    class _FakeAdapter:
        async def stream_chat_completion(self, request):
            state["stream_calls"].append(request)
            if provider_error is not None:
                raise provider_error
            for chunk in chunks or _usage_chunks():
                yield chunk

    app.dependency_overrides[get_authenticated_gateway_key] = _fake_auth_dependency
    app.state.redis_client = object()
    monkeypatch.setattr(dependencies_module, "_get_db_session_after_auth_header_check", _dummy_db_session)
    monkeypatch.setattr(gateway_module, "_get_db_session_after_auth_header_check", _dummy_db_session)
    monkeypatch.setattr(gateway_module.RouteResolutionService, "resolve_model", _fake_resolve_model)
    monkeypatch.setattr(gateway_module.PricingService, "estimate_chat_completion_cost", _fake_estimate)
    monkeypatch.setattr(gateway_module.QuotaService, "reserve_for_chat_completion", _fake_reserve)
    monkeypatch.setattr(gateway_module.AccountingService, "finalize_successful_response", _fake_finalize)
    monkeypatch.setattr(gateway_module.AccountingService, "record_provider_failure_and_release", _fake_failure)
    monkeypatch.setattr(gateway_module, "get_provider_adapter", lambda route, settings: _FakeAdapter())
    return state


def _wire_rate_service(monkeypatch, *, error=None):
    import slaif_gateway.services.chat_completion_gateway as gateway_module

    state: dict[str, object] = {"reserve_calls": [], "release_calls": []}

    class _FakeRateLimitService:
        def __init__(self, redis_client, *, fail_closed=True):
            _ = (redis_client, fail_closed)

        async def check_and_reserve(self, *, gateway_key_id, request_id, estimated_tokens, policy):
            state["reserve_calls"].append((gateway_key_id, request_id, estimated_tokens, policy))
            if error is not None:
                raise error
            return RateLimitResult(allowed=True)

        async def release_concurrency(self, *, gateway_key_id, request_id):
            state["release_calls"].append((gateway_key_id, request_id))

    monkeypatch.setattr(gateway_module, "RedisRateLimitService", _FakeRateLimitService)
    return state


def test_streaming_rate_limit_reserves_before_provider_and_releases_on_success(monkeypatch) -> None:
    app = create_app(
        Settings(
            OPENAI_UPSTREAM_API_KEY="unused",
            ENABLE_REDIS_RATE_LIMITS=True,
            REDIS_URL="redis://localhost:6379/0",
        )
    )
    auth = _auth()
    state = _wire_streaming_pipeline(monkeypatch, app, auth=auth)
    rate_state = _wire_rate_service(monkeypatch)

    with TestClient(app).stream("POST", "/v1/chat/completions", json=_chat_request()) as response:
        body = "".join(response.iter_text())

    assert response.status_code == 200
    assert "data: [DONE]" in body
    assert rate_state["reserve_calls"]
    assert state["stream_calls"]
    assert rate_state["release_calls"] == [
        (auth.gateway_key_id, rate_state["reserve_calls"][0][1])
    ]


def test_streaming_rate_limit_rejection_happens_before_provider(monkeypatch) -> None:
    app = create_app(
        Settings(
            OPENAI_UPSTREAM_API_KEY="unused",
            ENABLE_REDIS_RATE_LIMITS=True,
            REDIS_URL="redis://localhost:6379/0",
        )
    )
    state = _wire_streaming_pipeline(monkeypatch, app, auth=_auth({"requests_per_minute": 1}))
    _wire_rate_service(monkeypatch, error=RequestRateLimitExceededError())

    response = TestClient(app).post("/v1/chat/completions", json=_chat_request())

    assert response.status_code == 429
    assert state["route_calls"] == []
    assert state["stream_calls"] == []


def test_streaming_provider_failure_releases_concurrency(monkeypatch) -> None:
    app = create_app(
        Settings(
            OPENAI_UPSTREAM_API_KEY="unused",
            ENABLE_REDIS_RATE_LIMITS=True,
            REDIS_URL="redis://localhost:6379/0",
        )
    )
    auth = _auth()
    _wire_streaming_pipeline(
        monkeypatch,
        app,
        auth=auth,
        provider_error=ProviderTimeoutError(provider="openai"),
    )
    rate_state = _wire_rate_service(monkeypatch)

    with TestClient(app).stream("POST", "/v1/chat/completions", json=_chat_request()) as response:
        body = "".join(response.iter_text())

    assert response.status_code == 200
    assert "provider_timeout" in body
    assert rate_state["release_calls"] == [
        (auth.gateway_key_id, rate_state["reserve_calls"][0][1])
    ]


def test_streaming_missing_final_usage_releases_concurrency(monkeypatch) -> None:
    app = create_app(
        Settings(
            OPENAI_UPSTREAM_API_KEY="unused",
            ENABLE_REDIS_RATE_LIMITS=True,
            REDIS_URL="redis://localhost:6379/0",
        )
    )
    auth = _auth()
    chunks = [
        ProviderStreamChunk(
            provider="openai",
            upstream_model="gpt-4.1-mini",
            data="[DONE]",
            raw_sse_event="data: [DONE]\n\n",
            is_done=True,
        )
    ]
    _wire_streaming_pipeline(monkeypatch, app, auth=auth, chunks=chunks)
    rate_state = _wire_rate_service(monkeypatch)

    with TestClient(app).stream("POST", "/v1/chat/completions", json=_chat_request()) as response:
        body = "".join(response.iter_text())

    assert response.status_code == 200
    assert "data: [DONE]" in body
    assert rate_state["release_calls"] == [
        (auth.gateway_key_id, rate_state["reserve_calls"][0][1])
    ]
