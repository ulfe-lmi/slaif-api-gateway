from __future__ import annotations

import inspect
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient

from slaif_gateway.main import create_app
from slaif_gateway.schemas.auth import AuthenticatedGatewayKey
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
    import slaif_gateway.main as main_module

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
    import slaif_gateway.main as main_module

    async def _fake_estimate_chat_completion_cost(self, *, route, policy, endpoint="chat.completions", at=None):
        _ = (self, route, policy, endpoint, at)
        return object()

    monkeypatch.setattr(
        main_module.PricingService,
        "estimate_chat_completion_cost",
        _fake_estimate_chat_completion_cost,
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


def test_unsupported_model_returns_openai_shaped_route_error(monkeypatch) -> None:
    import slaif_gateway.main as main_module
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


def test_valid_request_with_no_output_limit_reaches_route_resolution_then_returns_501(monkeypatch) -> None:
    import slaif_gateway.main as main_module

    app = create_app()
    resolver_calls: list[str] = []
    _wire_auth_and_db(monkeypatch, app)

    async def _fake_resolve_model(self, requested_model, authenticated_key):
        _ = authenticated_key
        resolver_calls.append(requested_model)
        return _route_result(requested_model)

    monkeypatch.setattr(main_module.RouteResolutionService, "resolve_model", _fake_resolve_model)
    _wire_successful_pricing(monkeypatch)

    client = TestClient(app)
    response = client.post(
        "/v1/chat/completions",
        json={"model": "gpt-4.1-mini", "messages": [{"role": "user", "content": "hi"}]},
    )

    assert resolver_calls == ["gpt-4.1-mini"]
    assert response.status_code == 501
    assert response.json()["error"]["code"] == "provider_forwarding_not_implemented"


def test_valid_request_with_route_still_returns_501_not_model_response(monkeypatch) -> None:
    import slaif_gateway.main as main_module

    app = create_app()
    _wire_auth_and_db(monkeypatch, app)

    async def _fake_resolve_model(self, requested_model, authenticated_key):
        _ = (requested_model, authenticated_key)
        return _route_result(requested_model)

    monkeypatch.setattr(main_module.RouteResolutionService, "resolve_model", _fake_resolve_model)
    _wire_successful_pricing(monkeypatch)

    client = TestClient(app)
    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "gpt-4.1-mini",
            "messages": [{"role": "user", "content": "hello"}],
            "max_tokens": 20,
        },
    )

    assert response.status_code == 501
    assert response.json()["error"]["message"] == "Provider forwarding is not implemented yet."


def test_stream_true_returns_501_not_streaming(monkeypatch) -> None:
    import slaif_gateway.main as main_module

    app = create_app()
    _wire_auth_and_db(monkeypatch, app)

    async def _fake_resolve_model(self, requested_model, authenticated_key):
        _ = (requested_model, authenticated_key)
        return _route_result(requested_model)

    monkeypatch.setattr(main_module.RouteResolutionService, "resolve_model", _fake_resolve_model)
    _wire_successful_pricing(monkeypatch)

    client = TestClient(app)
    response = client.post(
        "/v1/chat/completions",
        json={"model": "gpt-4.1-mini", "messages": [{"role": "user", "content": "hi"}], "stream": True},
    )

    assert response.status_code == 501
    assert response.json()["error"]["message"] == "Provider forwarding is not implemented yet."


def test_chat_completions_module_safety_constraints() -> None:
    import slaif_gateway.main as main_module

    source = inspect.getsource(main_module).lower()

    for disallowed in (
        "httpx",
        "openrouter",
        "openai_upstream",
        "celery",
        "aiosmtplib",
        "accounting",
    ):
        assert disallowed not in source
