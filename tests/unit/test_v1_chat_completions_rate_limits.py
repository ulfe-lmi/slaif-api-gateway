from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient

from slaif_gateway.api.dependencies import get_authenticated_gateway_key
from slaif_gateway.config import Settings
from slaif_gateway.main import create_app
from slaif_gateway.schemas.auth import AuthenticatedGatewayKey
from slaif_gateway.schemas.providers import ProviderResponse, ProviderUsage
from slaif_gateway.schemas.quota import QuotaReservationResult
from slaif_gateway.schemas.rate_limits import RateLimitResult
from slaif_gateway.schemas.routing import RouteResolutionResult
from slaif_gateway.services.rate_limit_errors import (
    ConcurrencyRateLimitExceededError,
    RedisRateLimitUnavailableError,
    RequestRateLimitExceededError,
    TokenRateLimitExceededError,
)


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
        rate_limit_policy=policy or {},
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


def _chat_request(**overrides) -> dict[str, object]:
    body: dict[str, object] = {
        "model": "classroom-cheap",
        "messages": [{"role": "user", "content": "hello"}],
        "max_tokens": 20,
    }
    body.update(overrides)
    return body


def _wire_pipeline(monkeypatch, app, *, auth: AuthenticatedGatewayKey, quota_error=None, accounting_error=None):
    from slaif_gateway.api import dependencies as dependencies_module
    import slaif_gateway.services.chat_completion_gateway as gateway_module

    state: dict[str, object] = {
        "route_calls": [],
        "pricing_calls": [],
        "reserve_calls": [],
        "provider_calls": [],
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
        state["pricing_calls"].append("priced")
        return object()

    async def _fake_reserve(self, *, authenticated_key, route, policy, cost_estimate, request_id, now=None):
        _ = (self, authenticated_key, route, policy, cost_estimate, now)
        state["reserve_calls"].append(request_id)
        if quota_error is not None:
            raise quota_error
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
        if accounting_error is not None:
            raise accounting_error
        return object()

    async def _fake_failure(self, *args, **kwargs):
        _ = (self, args)
        state["failure_calls"].append(kwargs)
        return object()

    class _FakeAdapter:
        async def forward_chat_completion(self, request):
            state["provider_calls"].append(request)
            return ProviderResponse(
                provider=request.provider,
                upstream_model=request.upstream_model,
                status_code=200,
                json_body={"id": "chatcmpl_test", "choices": []},
                usage=ProviderUsage(prompt_tokens=5, completion_tokens=6, total_tokens=11),
            )

    app.dependency_overrides[get_authenticated_gateway_key] = _fake_auth_dependency
    app.state.redis_client = _FakeRedis()
    monkeypatch.setattr(dependencies_module, "_get_db_session_after_auth_header_check", _dummy_db_session)
    monkeypatch.setattr(gateway_module, "_get_db_session_after_auth_header_check", _dummy_db_session)
    monkeypatch.setattr(gateway_module.RouteResolutionService, "resolve_model", _fake_resolve_model)
    monkeypatch.setattr(gateway_module.PricingService, "estimate_chat_completion_cost", _fake_estimate)
    monkeypatch.setattr(gateway_module.QuotaService, "reserve_for_chat_completion", _fake_reserve)
    monkeypatch.setattr(gateway_module.AccountingService, "finalize_successful_response", _fake_finalize)
    monkeypatch.setattr(gateway_module.AccountingService, "record_provider_failure_and_release", _fake_failure)
    monkeypatch.setattr(gateway_module, "get_provider_adapter", lambda route, settings: _FakeAdapter())
    return state


def _wire_rate_service(monkeypatch, *, error=None, degraded: bool = False):
    import slaif_gateway.services.chat_completion_gateway as gateway_module

    state: dict[str, object] = {"reserve_calls": [], "release_calls": []}

    class _FakeRateLimitService:
        def __init__(self, redis_client, *, fail_closed=True):
            state["fail_closed"] = fail_closed
            state["redis_client"] = redis_client

        async def check_and_reserve(self, *, gateway_key_id, request_id, estimated_tokens, policy):
            state["reserve_calls"].append(
                {
                    "gateway_key_id": gateway_key_id,
                    "request_id": request_id,
                    "estimated_tokens": estimated_tokens,
                    "policy": policy,
                }
            )
            if error is not None:
                raise error
            return RateLimitResult(allowed=True, degraded=degraded)

        async def release_concurrency(self, *, gateway_key_id, request_id):
            state["release_calls"].append((gateway_key_id, request_id))

    monkeypatch.setattr(gateway_module, "RedisRateLimitService", _FakeRateLimitService)
    return state


def test_rate_limit_disabled_keeps_existing_nonstreaming_flow(monkeypatch) -> None:
    app = create_app(Settings(OPENAI_UPSTREAM_API_KEY="unused"))
    auth = _auth({"requests_per_minute": 1, "tokens_per_minute": 1, "max_concurrent_requests": 1})
    pipeline_state = _wire_pipeline(monkeypatch, app, auth=auth)
    rate_state = _wire_rate_service(monkeypatch)

    response = TestClient(app).post("/v1/chat/completions", json=_chat_request())

    assert response.status_code == 200
    assert rate_state["reserve_calls"] == []
    assert pipeline_state["route_calls"] == ["classroom-cheap"]
    assert pipeline_state["provider_calls"]


def test_request_rate_limit_rejection_happens_before_expensive_work(monkeypatch) -> None:
    app = create_app(
        Settings(
            OPENAI_UPSTREAM_API_KEY="unused",
            ENABLE_REDIS_RATE_LIMITS=True,
            REDIS_URL="redis://localhost:6379/0",
        )
    )
    auth = _auth({"requests_per_minute": 1})
    pipeline_state = _wire_pipeline(monkeypatch, app, auth=auth)
    _wire_rate_service(monkeypatch, error=RequestRateLimitExceededError(retry_after_seconds=60))

    response = TestClient(app).post("/v1/chat/completions", json=_chat_request())

    assert response.status_code == 429
    assert response.json()["error"]["type"] == "rate_limit_error"
    assert response.json()["error"]["code"] == "request_rate_limit_exceeded"
    assert pipeline_state["route_calls"] == []
    assert pipeline_state["pricing_calls"] == []
    assert pipeline_state["reserve_calls"] == []
    assert pipeline_state["provider_calls"] == []


def test_token_and_concurrency_rate_limit_errors_are_openai_shaped(monkeypatch) -> None:
    cases = [
        (TokenRateLimitExceededError(), "token_rate_limit_exceeded"),
        (ConcurrencyRateLimitExceededError(), "concurrency_rate_limit_exceeded"),
    ]
    for error, code in cases:
        app = create_app(
            Settings(
                OPENAI_UPSTREAM_API_KEY="unused",
                ENABLE_REDIS_RATE_LIMITS=True,
                REDIS_URL="redis://localhost:6379/0",
            )
        )
        _wire_pipeline(monkeypatch, app, auth=_auth({"tokens_per_minute": 50, "max_concurrent_requests": 1}))
        _wire_rate_service(monkeypatch, error=error)

        response = TestClient(app).post("/v1/chat/completions", json=_chat_request())

        assert response.status_code == 429
        assert response.json()["error"]["code"] == code


def test_redis_fail_closed_unavailable_returns_before_expensive_work(monkeypatch) -> None:
    app = create_app(
        Settings(
            OPENAI_UPSTREAM_API_KEY="unused",
            ENABLE_REDIS_RATE_LIMITS=True,
            REDIS_URL="redis://localhost:6379/0",
            RATE_LIMIT_FAIL_CLOSED=True,
        )
    )
    pipeline_state = _wire_pipeline(monkeypatch, app, auth=_auth({"requests_per_minute": 1}))
    _wire_rate_service(monkeypatch, error=RedisRateLimitUnavailableError())

    response = TestClient(app).post("/v1/chat/completions", json=_chat_request())

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "redis_rate_limit_unavailable"
    assert pipeline_state["route_calls"] == []


def test_redis_fail_open_allows_request(monkeypatch) -> None:
    app = create_app(
        Settings(
            OPENAI_UPSTREAM_API_KEY="unused",
            ENABLE_REDIS_RATE_LIMITS=True,
            REDIS_URL="redis://localhost:6379/0",
            RATE_LIMIT_FAIL_CLOSED=False,
        )
    )
    pipeline_state = _wire_pipeline(monkeypatch, app, auth=_auth({"requests_per_minute": 1}))
    rate_state = _wire_rate_service(monkeypatch, degraded=True)

    response = TestClient(app).post("/v1/chat/completions", json=_chat_request())

    assert response.status_code == 200
    assert rate_state["fail_closed"] is False
    assert pipeline_state["provider_calls"]


def test_concurrency_released_after_nonstreaming_success(monkeypatch) -> None:
    app = create_app(
        Settings(
            OPENAI_UPSTREAM_API_KEY="unused",
            ENABLE_REDIS_RATE_LIMITS=True,
            REDIS_URL="redis://localhost:6379/0",
        )
    )
    auth = _auth({"max_concurrent_requests": 1})
    _wire_pipeline(monkeypatch, app, auth=auth)
    rate_state = _wire_rate_service(monkeypatch)

    response = TestClient(app).post("/v1/chat/completions", json=_chat_request())

    assert response.status_code == 200
    assert rate_state["reserve_calls"]
    assert rate_state["release_calls"] == [
        (auth.gateway_key_id, rate_state["reserve_calls"][0]["request_id"])
    ]


def test_concurrency_released_after_quota_failure(monkeypatch) -> None:
    from slaif_gateway.services.quota_errors import QuotaLimitExceededError

    app = create_app(
        Settings(
            OPENAI_UPSTREAM_API_KEY="unused",
            ENABLE_REDIS_RATE_LIMITS=True,
            REDIS_URL="redis://localhost:6379/0",
        )
    )
    auth = _auth({"max_concurrent_requests": 1})
    _wire_pipeline(
        monkeypatch,
        app,
        auth=auth,
        quota_error=QuotaLimitExceededError("Token quota limit exceeded", param="token_limit_total"),
    )
    rate_state = _wire_rate_service(monkeypatch)

    response = TestClient(app).post("/v1/chat/completions", json=_chat_request())

    assert response.status_code == 429
    assert rate_state["release_calls"] == [
        (auth.gateway_key_id, rate_state["reserve_calls"][0]["request_id"])
    ]


def test_concurrency_released_after_accounting_failure(monkeypatch) -> None:
    from slaif_gateway.services.accounting_errors import ReservationFinalizationError

    app = create_app(
        Settings(
            OPENAI_UPSTREAM_API_KEY="unused",
            ENABLE_REDIS_RATE_LIMITS=True,
            REDIS_URL="redis://localhost:6379/0",
        )
    )
    auth = _auth({"max_concurrent_requests": 1})
    _wire_pipeline(monkeypatch, app, auth=auth, accounting_error=ReservationFinalizationError())
    rate_state = _wire_rate_service(monkeypatch)

    response = TestClient(app).post("/v1/chat/completions", json=_chat_request())

    assert response.status_code == 409
    assert rate_state["release_calls"] == [
        (auth.gateway_key_id, rate_state["reserve_calls"][0]["request_id"])
    ]


def test_rate_limit_estimated_tokens_combines_input_and_effective_output(monkeypatch) -> None:
    app = create_app(
        Settings(
            OPENAI_UPSTREAM_API_KEY="unused",
            ENABLE_REDIS_RATE_LIMITS=True,
            REDIS_URL="redis://localhost:6379/0",
        )
    )
    _wire_pipeline(monkeypatch, app, auth=_auth({"tokens_per_minute": 1000}))
    rate_state = _wire_rate_service(monkeypatch)

    response = TestClient(app).post("/v1/chat/completions", json=_chat_request(max_tokens=20))

    assert response.status_code == 200
    assert rate_state["reserve_calls"][0]["estimated_tokens"] >= 20
