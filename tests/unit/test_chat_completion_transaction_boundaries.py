from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

import slaif_gateway.services.chat_completion_gateway as gateway_module
from slaif_gateway.api.errors import OpenAICompatibleError
from slaif_gateway.config import Settings
from slaif_gateway.providers.errors import ProviderTimeoutError
from slaif_gateway.schemas.auth import AuthenticatedGatewayKey
from slaif_gateway.schemas.openai import ChatCompletionRequest
from slaif_gateway.schemas.pricing import ChatCostEstimate
from slaif_gateway.schemas.providers import ProviderResponse, ProviderUsage
from slaif_gateway.schemas.quota import QuotaReservationResult
from slaif_gateway.schemas.routing import RouteResolutionResult
from slaif_gateway.services.accounting_errors import ReservationFinalizationError
from slaif_gateway.services.quota_errors import QuotaLimitExceededError


class _FakeSession:
    def __init__(self, label: str, state: dict[str, object]) -> None:
        self.label = label
        self._state = state

    async def commit(self) -> None:
        self._state["events"].append(f"{self.label}:commit")


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


def _payload() -> ChatCompletionRequest:
    return ChatCompletionRequest(
        model="classroom-cheap",
        messages=[{"role": "user", "content": "hello"}],
        max_tokens=20,
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


def _estimate() -> ChatCostEstimate:
    return ChatCostEstimate(
        provider="openai",
        requested_model="classroom-cheap",
        resolved_model="gpt-4.1-mini",
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


def _reservation(auth: AuthenticatedGatewayKey) -> QuotaReservationResult:
    return QuotaReservationResult(
        reservation_id=uuid.uuid4(),
        gateway_key_id=auth.gateway_key_id,
        request_id="gw-test",
        reserved_cost_eur=Decimal("0.003"),
        reserved_tokens=70,
        status="pending",
        expires_at=datetime.now(UTC) + timedelta(minutes=15),
    )


def _provider_response() -> ProviderResponse:
    return ProviderResponse(
        provider="openai",
        upstream_model="gpt-4.1-mini",
        status_code=200,
        json_body={"id": "chatcmpl_test", "choices": []},
        usage=ProviderUsage(prompt_tokens=5, completion_tokens=7, total_tokens=12),
    )


def _session_state(monkeypatch) -> dict[str, object]:
    state: dict[str, object] = {
        "events": [],
        "active_sessions": set(),
        "session_count": 0,
    }

    async def _session_generator():
        state["session_count"] += 1
        label = f"tx{state['session_count']}"
        session = _FakeSession(label, state)
        state["active_sessions"].add(label)
        state["events"].append(f"{label}:open")
        try:
            yield session
        finally:
            state["events"].append(f"{label}:close")
            state["active_sessions"].remove(label)

    monkeypatch.setattr(gateway_module, "_get_db_session_after_auth_header_check", _session_generator)
    return state


def _wire_success(monkeypatch, state: dict[str, object], auth: AuthenticatedGatewayKey) -> None:
    route = _route()
    estimate = _estimate()
    reservation = _reservation(auth)

    async def _resolve_model(self, requested_model, authenticated_key):
        assert requested_model == "classroom-cheap"
        assert authenticated_key == auth
        state["events"].append(f"{self._model_routes_repository._session.label}:resolve")
        return route

    async def _estimate_cost(self, *, route, policy, endpoint="chat.completions", at=None):
        _ = (route, policy, endpoint, at)
        state["events"].append(f"{self._pricing_rules_repository._session.label}:price")
        return estimate

    async def _reserve(self, *, authenticated_key, route, policy, cost_estimate, request_id, now=None):
        _ = (authenticated_key, route, policy, cost_estimate, request_id, now)
        state["events"].append(f"{self._gateway_keys_repository._session.label}:reserve")
        return reservation

    async def _finalize(self, *args, **kwargs):
        _ = (args, kwargs)
        state["events"].append(f"{self._gateway_keys_repository._session.label}:finalize")
        return object()

    class _Adapter:
        async def forward_chat_completion(self, request):
            _ = request
            state["events"].append("provider:called")
            assert state["active_sessions"] == set()
            return _provider_response()

    monkeypatch.setattr(gateway_module.RouteResolutionService, "resolve_model", _resolve_model)
    monkeypatch.setattr(gateway_module.PricingService, "estimate_chat_completion_cost", _estimate_cost)
    monkeypatch.setattr(gateway_module.QuotaService, "reserve_for_chat_completion", _reserve)
    monkeypatch.setattr(gateway_module.AccountingService, "finalize_successful_response", _finalize)
    monkeypatch.setattr(gateway_module, "get_provider_adapter", lambda provider, settings: _Adapter())


@pytest.mark.asyncio
async def test_reservation_commits_and_closes_before_provider_call(monkeypatch) -> None:
    state = _session_state(monkeypatch)
    auth = _auth()
    _wire_success(monkeypatch, state, auth)

    response = await gateway_module.handle_chat_completion(
        payload=_payload(),
        authenticated_key=auth,
        settings=Settings(OPENAI_UPSTREAM_API_KEY="unused"),
    )

    assert response.status_code == 200
    assert state["events"] == [
        "tx1:open",
        "tx1:resolve",
        "tx1:price",
        "tx1:reserve",
        "tx1:commit",
        "tx1:close",
        "provider:called",
        "tx2:open",
        "tx2:finalize",
        "tx2:commit",
        "tx2:close",
    ]


@pytest.mark.asyncio
async def test_finalization_uses_separate_transaction_after_provider_response(monkeypatch) -> None:
    state = _session_state(monkeypatch)
    auth = _auth()
    _wire_success(monkeypatch, state, auth)

    await gateway_module.handle_chat_completion(
        payload=_payload(),
        authenticated_key=auth,
        settings=Settings(OPENAI_UPSTREAM_API_KEY="unused"),
    )

    assert state["events"].index("provider:called") < state["events"].index("tx2:open")
    assert "tx2:finalize" in state["events"]


@pytest.mark.asyncio
async def test_provider_failure_releases_reservation_in_separate_transaction(monkeypatch) -> None:
    state = _session_state(monkeypatch)
    auth = _auth()
    _wire_success(monkeypatch, state, auth)

    class _Adapter:
        async def forward_chat_completion(self, request):
            _ = request
            state["events"].append("provider:called")
            assert state["active_sessions"] == set()
            raise ProviderTimeoutError(provider="openai")

    async def _record_failure(self, *args, **kwargs):
        _ = (args, kwargs)
        state["events"].append(f"{self._gateway_keys_repository._session.label}:release")
        return object()

    monkeypatch.setattr(gateway_module, "get_provider_adapter", lambda provider, settings: _Adapter())
    monkeypatch.setattr(
        gateway_module.AccountingService,
        "record_provider_failure_and_release",
        _record_failure,
    )

    with pytest.raises(OpenAICompatibleError) as exc_info:
        await gateway_module.handle_chat_completion(
            payload=_payload(),
            authenticated_key=auth,
            settings=Settings(OPENAI_UPSTREAM_API_KEY="unused"),
        )

    assert exc_info.value.code == "provider_timeout"
    assert state["events"] == [
        "tx1:open",
        "tx1:resolve",
        "tx1:price",
        "tx1:reserve",
        "tx1:commit",
        "tx1:close",
        "provider:called",
        "tx2:open",
        "tx2:release",
        "tx2:commit",
        "tx2:close",
    ]


@pytest.mark.asyncio
async def test_provider_is_not_called_when_quota_reservation_fails(monkeypatch) -> None:
    state = _session_state(monkeypatch)
    auth = _auth()
    _wire_success(monkeypatch, state, auth)

    async def _raise_quota(self, *args, **kwargs):
        _ = (self, args, kwargs)
        state["events"].append("tx1:reserve")
        raise QuotaLimitExceededError("Token quota limit exceeded", param="token_limit_total")

    def _get_provider_adapter(provider, settings):
        _ = (provider, settings)
        raise AssertionError("provider must not be called after quota failure")

    monkeypatch.setattr(gateway_module.QuotaService, "reserve_for_chat_completion", _raise_quota)
    monkeypatch.setattr(gateway_module, "get_provider_adapter", _get_provider_adapter)

    with pytest.raises(OpenAICompatibleError) as exc_info:
        await gateway_module.handle_chat_completion(
            payload=_payload(),
            authenticated_key=auth,
            settings=Settings(OPENAI_UPSTREAM_API_KEY="unused"),
        )

    assert exc_info.value.code == "quota_limit_exceeded"
    assert "provider:called" not in state["events"]
    assert "tx1:commit" not in state["events"]


@pytest.mark.asyncio
async def test_accounting_failure_after_provider_success_does_not_return_success(monkeypatch) -> None:
    state = _session_state(monkeypatch)
    auth = _auth()
    _wire_success(monkeypatch, state, auth)

    async def _raise_accounting(self, *args, **kwargs):
        _ = (self, args, kwargs)
        state["events"].append(f"{self._gateway_keys_repository._session.label}:finalize")
        raise ReservationFinalizationError()

    monkeypatch.setattr(
        gateway_module.AccountingService,
        "finalize_successful_response",
        _raise_accounting,
    )

    with pytest.raises(OpenAICompatibleError) as exc_info:
        await gateway_module.handle_chat_completion(
            payload=_payload(),
            authenticated_key=auth,
            settings=Settings(OPENAI_UPSTREAM_API_KEY="unused"),
        )

    assert exc_info.value.code == "reservation_finalization_error"
    assert "provider:called" in state["events"]
    assert "tx2:commit" not in state["events"]
