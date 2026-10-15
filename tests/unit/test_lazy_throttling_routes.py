"""Call-site wiring for the lazy-throttling wait loop (Chat + Responses).

These focused cases prove that the production call sites pass the live
transport disconnect probe into the shared helper and that a disconnected
wait aborts before quota reservation and provider work. Real socket
disconnect behavior is proven by the HTTP/browser qualification tests.
"""

from __future__ import annotations

import dataclasses
import uuid
from decimal import Decimal
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from slaif_gateway.config import Settings
from slaif_gateway.main import create_app
from slaif_gateway.schemas.auth import AuthenticatedGatewayKey
from slaif_gateway.schemas.rate_limits import (
    LazyThrottlingPolicy,
    RateLimitPolicy,
    RateLimitResult,
)
from slaif_gateway.services import lazy_throttling
from slaif_gateway.services.lazy_throttling import (
    LazyAdmissionContext,
    LazyAdmissionResult,
)
from slaif_gateway.services.rate_limit_errors import (
    ClientDisconnectedError,
    RequestRateLimitExceededError,
)

from test_v1_chat_completions_rate_limits import (
    _auth,
    _wire_pipeline,
    _wire_rate_service,
)


def _auth_wait(policy: dict[str, int | None] | None = None) -> AuthenticatedGatewayKey:
    """Like the sibling _auth, but with an explicit wait-mode lazy policy."""
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
        lazy_throttling=LazyThrottlingPolicy(mode="wait", max_wait_seconds=1),
    )


class _FakeRequest:
    """Just enough of the transport request for the call-site pass-through."""

    def __init__(self, disconnected: bool = False) -> None:
        self.headers: dict[str, str] = {"authorization": "Bearer sk-slaif-test"}
        self._disconnected = disconnected

    async def is_disconnected(self) -> bool:
        return self._disconnected


class _AdmissionDouble:
    """Records lease calls; always grants (caps are integration-proven)."""

    def __init__(self) -> None:
        self.acquired = 0
        self.released = 0
        self.fail_closed = True

    async def acquire_waiting_lease(self, **kwargs: Any) -> bool:
        self.acquired += 1
        return True

    async def release_waiting_lease(self, **kwargs: Any) -> None:
        self.released += 1


def _context(key: AuthenticatedGatewayKey) -> LazyAdmissionContext:
    return LazyAdmissionContext(
        gateway_key_id=key.gateway_key_id,
        authenticated_key=key,
        limiter_policy=RateLimitPolicy(requests_per_minute=1, window_seconds=60),
        policy_result=None,
        route=None,
        estimated_tokens=10,
    )


@pytest.mark.asyncio
async def test_chat_wait_call_site_passes_live_disconnect_probe(monkeypatch) -> None:
    import slaif_gateway.services.chat_completion_gateway as chat_module

    auth = _auth({"requests_per_minute": 1})
    ctx = _context(auth)
    captured: dict[str, Any] = {}

    async def _fake_wait(**kwargs: Any) -> LazyAdmissionResult:
        captured.update(kwargs)
        return LazyAdmissionResult(result=RateLimitResult(allowed=True), context=ctx)

    monkeypatch.setattr(chat_module, "wait_for_rate_limit_admission", _fake_wait)
    request = _FakeRequest(disconnected=False)

    async def _noop_service_check(**_: Any) -> RateLimitResult:  # pragma: no cover
        raise AssertionError("not reached in this test")

    class _Service:
        check_and_reserve = staticmethod(_noop_service_check)

        async def release_concurrency(self, **_: Any) -> None:
            return None

    result = await chat_module._wait_for_lazy_admission(
        service=_Service(),
        admission=_AdmissionDouble(),
        initial_context=ctx,
        lazy_policy=LazyThrottlingPolicy(mode="wait"),
        request_id="req-wire",
        estimated_tokens=10,
        body={"model": "classroom-cheap"},
        request=request,
        settings=Settings(),
    )
    assert result is not None
    assert captured["is_disconnected"] == request.is_disconnected
    # The probe reflects the live transport state, not a stale flag.
    assert await captured["is_disconnected"]() is False
    request._disconnected = True
    assert await captured["is_disconnected"]() is True


@pytest.mark.asyncio
async def test_responses_wait_call_site_passes_live_disconnect_probe(monkeypatch) -> None:
    import slaif_gateway.services.responses_gateway as responses_module

    auth = _auth({"requests_per_minute": 1})
    ctx = _context(auth)
    captured: dict[str, Any] = {}

    async def _fake_wait(**kwargs: Any) -> LazyAdmissionResult:
        captured.update(kwargs)
        return LazyAdmissionResult(result=RateLimitResult(allowed=True), context=ctx)

    monkeypatch.setattr(responses_module, "wait_for_rate_limit_admission", _fake_wait)
    request = _FakeRequest(disconnected=False)

    class _Service:
        async def release_concurrency(self, **_: Any) -> None:
            return None

    async def _resolve_route_for_key(key: AuthenticatedGatewayKey):
        return None

    async def _route_checks_after_wait(key, new_route, current_policy_result):
        return current_policy_result

    await responses_module._wait_for_responses_lazy_admission(
        service=_Service(),
        admission=_AdmissionDouble(),
        initial_context=ctx,
        lazy_policy=LazyThrottlingPolicy(mode="wait"),
        endpoint_policy_id="responses.create",
        resolve_route_for_key=_resolve_route_for_key,
        route_checks_after_wait=_route_checks_after_wait,
        request_id="req-wire-responses",
        estimated_tokens=10,
        request=request,
        settings=Settings(),
    )
    assert captured["is_disconnected"] == request.is_disconnected
    assert await captured["is_disconnected"]() is False
    request._disconnected = True
    assert await captured["is_disconnected"]() is True


def _wire_wait_preflight_support(monkeypatch, auth: AuthenticatedGatewayKey) -> None:
    """Unit boundary for the wait phase (preflight + post-wait re-validation).

    The non-mutating pre-flight mirrors the existing atomic reservation
    inputs (coherent cost estimate + key row; no quota mutation in this
    phase). The post-wait re-validation re-authenticates through the real
    service path, which this unit boundary returns the SAME authenticated
    key for; the real HTTP/PG qualification proves re-auth against the
    database instead of this double.
    """
    import slaif_gateway.services.chat_completion_gateway as chat_module
    from types import SimpleNamespace

    from slaif_gateway.schemas.pricing import ChatCostEstimate

    estimate = ChatCostEstimate(
        provider="openai",
        requested_model="classroom-cheap",
        resolved_model="gpt-4.1-mini",
        native_currency="EUR",
        estimated_input_tokens=5,
        estimated_output_tokens=20,
        estimated_input_cost_native=Decimal("0.000002500"),
        estimated_output_cost_native=Decimal("0.000030000"),
        estimated_total_cost_native=Decimal("0.000032500"),
        estimated_total_cost_eur=Decimal("0.000032500"),
        pricing_rule_id=None,
        fx_rate_id=None,
    )

    async def _fake_estimate(
        self, *, route, policy, endpoint="chat.completions", at=None, pricing=None, fx=None
    ):
        _ = (self, route, policy, endpoint, at, pricing, fx)
        return estimate

    gateway_key = SimpleNamespace(
        id=uuid.uuid4(),
        status="active",
        valid_from=datetime.now(UTC) - timedelta(minutes=5),
        valid_until=datetime.now(UTC) + timedelta(days=1),
        cost_limit_eur=None,
        token_limit_total=None,
        request_limit_total=None,
        cost_used_eur=Decimal("0"),
        cost_reserved_eur=Decimal("0"),
        tokens_used_total=0,
        tokens_reserved_total=0,
        requests_used_total=0,
        requests_reserved_total=0,
        external_tool_fence_state="none",
    )

    async def _fake_get_gateway_key_by_id(self, key_id):
        _ = (self, key_id)
        return gateway_key

    class _FakeAuthSvc:
        def __init__(self, **kwargs: Any) -> None:
            _ = kwargs

        async def authenticate_authorization_header(self, authorization: str):
            _ = authorization
            return auth

    class _FakeOwnersRepo:
        def __init__(self, session: Any) -> None:
            _ = session

        async def get_owner_by_id(self, owner_id: Any) -> Any:
            _ = owner_id
            return SimpleNamespace(is_active=True, anonymized_at=None)

    monkeypatch.setattr(
        chat_module.PricingService, "estimate_chat_completion_cost", _fake_estimate
    )
    monkeypatch.setattr(
        chat_module.GatewayKeysRepository,
        "get_gateway_key_by_id",
        _fake_get_gateway_key_by_id,
    )
    monkeypatch.setattr(chat_module, "GatewayAuthService", _FakeAuthSvc)
    monkeypatch.setattr(chat_module, "OwnersRepository", _FakeOwnersRepo)


def test_chat_wait_mode_deadline_fails_429_before_provider(monkeypatch) -> None:
    """Full app path: wait mode, always-denied limiter, 1s max wait."""
    import slaif_gateway.services.chat_completion_gateway as chat_module

    app = create_app(
        Settings(
            OPENAI_UPSTREAM_API_KEY="unused",
            ENABLE_REDIS_RATE_LIMITS=True,
            REDIS_URL="redis://localhost:6379/0",
        )
    )
    auth = _auth_wait({"requests_per_minute": 1})
    state = _wire_pipeline(monkeypatch, app, auth=auth)
    _wire_rate_service(monkeypatch, error=RequestRateLimitExceededError(retry_after_seconds=60))
    _wire_wait_preflight_support(monkeypatch, auth)

    admission_double = _AdmissionDouble()
    monkeypatch.setattr(chat_module, "LazyThrottlingAdmission", lambda *a, **k: admission_double)

    with TestClient(app) as client:
        response = client.post(
            "/v1/chat/completions",
            headers={"authorization": f"Bearer {auth.public_key_id}"},
            json={"model": "classroom-cheap", "messages": [{"role": "user", "content": "hi"}]},
        )
    assert response.status_code == 429
    payload = response.json()
    assert payload["error"]["code"] == "lazy_throttling_deadline_exceeded"
    assert state["provider_calls"] == []
    assert state["reserve_calls"] == []
    assert admission_double.acquired == 1
    assert admission_double.released >= 1


def test_chat_wait_mode_disconnect_cancels_without_provider_or_quota(monkeypatch) -> None:
    """The helper's disconnect outcome is a cancellation: no quota, no
    provider call, no finalized accounting, and no fake 200."""
    import slaif_gateway.services.chat_completion_gateway as chat_module

    app = create_app(
        Settings(
            OPENAI_UPSTREAM_API_KEY="unused",
            ENABLE_REDIS_RATE_LIMITS=True,
            REDIS_URL="redis://localhost:6379/0",
        )
    )
    auth = _auth_wait({"requests_per_minute": 1})
    # Long deadline: the disconnect must fire long before it.
    auth = dataclasses.replace(auth, lazy_throttling=LazyThrottlingPolicy(mode="wait", max_wait_seconds=30))
    state = _wire_pipeline(monkeypatch, app, auth=auth)
    _wire_rate_service(monkeypatch, error=RequestRateLimitExceededError(retry_after_seconds=60))
    _wire_wait_preflight_support(monkeypatch, auth)

    wait_state = {"called": False}

    async def _disconnected_wait(**kwargs: Any) -> LazyAdmissionResult:
        # The helper's closed-client outcome: the request is aborted before
        # any provider work; the mapped response is undeliverable to the
        # closed peer and must not be a fabricated 200 or a 429.
        wait_state["called"] = True
        raise ClientDisconnectedError()

    monkeypatch.setattr(chat_module, "wait_for_rate_limit_admission", _disconnected_wait)

    with TestClient(app) as client:
        response = client.post(
            "/v1/chat/completions",
            headers={"authorization": f"Bearer {auth.public_key_id}"},
            json={"model": "classroom-cheap", "messages": [{"role": "user", "content": "hi"}]},
        )
    # The closed-client outcome must come FROM the wait loop, not an
    # earlier error, and keep its dedicated label (no 200/429 mislabel).
    assert wait_state["called"] is True
    assert response.status_code == 499
    assert response.json()["error"]["code"] == "client_disconnected"
    assert state["provider_calls"] == []
    assert state["reserve_calls"] == []
    assert state["finalize_calls"] == []
    assert state["failure_calls"] == []


def test_chat_default_reject_mode_keeps_immediate_429(monkeypatch) -> None:
    """Legacy/missing policy: the wait loop never runs at all."""
    app = create_app(
        Settings(
            OPENAI_UPSTREAM_API_KEY="unused",
            ENABLE_REDIS_RATE_LIMITS=True,
            REDIS_URL="redis://localhost:6379/0",
        )
    )
    auth = _auth({"requests_per_minute": 1})  # no lazy_throttling field
    state = _wire_pipeline(monkeypatch, app, auth=auth)
    _wire_rate_service(monkeypatch, error=RequestRateLimitExceededError(retry_after_seconds=60))

    called = {"wait": 0}

    original = lazy_throttling.wait_for_rate_limit_admission

    async def _must_not_run(**kwargs: Any) -> LazyAdmissionResult:
        called["wait"] += 1
        return await original(**kwargs)

    import slaif_gateway.services.chat_completion_gateway as chat_module

    monkeypatch.setattr(chat_module, "wait_for_rate_limit_admission", _must_not_run)

    with TestClient(app) as client:
        response = client.post(
            "/v1/chat/completions",
            headers={"authorization": f"Bearer {auth.public_key_id}"},
            json={"model": "classroom-cheap", "messages": [{"role": "user", "content": "hi"}]},
        )
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "request_rate_limit_exceeded"
    assert called["wait"] == 0
    assert state["provider_calls"] == []
