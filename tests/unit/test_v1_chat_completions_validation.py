from __future__ import annotations

import inspect
import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from slaif_gateway.main import create_app
from slaif_gateway.schemas.auth import AuthenticatedGatewayKey


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


def test_unauthenticated_request_returns_openai_shaped_401() -> None:
    app = create_app()
    client = TestClient(app)

    response = client.post("/v1/chat/completions", json={"model": "gpt-4.1-mini", "messages": []})

    assert response.status_code == 401
    body = response.json()
    assert "error" in body
    assert set(body["error"].keys()) == {"message", "type", "param", "code"}


def test_missing_model_returns_openai_shaped_invalid_request_error(monkeypatch) -> None:
    from slaif_gateway.api import dependencies as dependencies_module
    from slaif_gateway.api.dependencies import get_authenticated_gateway_key
    import slaif_gateway.main as main_module

    app = create_app()

    async def _fake_auth_dependency() -> AuthenticatedGatewayKey:
        return _fake_authenticated_gateway_key()

    async def _dummy_db_session():
        yield object()

    app.dependency_overrides[get_authenticated_gateway_key] = _fake_auth_dependency
    monkeypatch.setattr(dependencies_module, "_get_db_session_after_auth_header_check", _dummy_db_session)
    monkeypatch.setattr(main_module, "_get_db_session_after_auth_header_check", _dummy_db_session)

    client = TestClient(app)
    response = client.post("/v1/chat/completions", json={"messages": []})

    assert response.status_code == 422
    assert response.json()["error"]["type"] == "invalid_request_error"


def test_missing_messages_returns_openai_shaped_invalid_request_error(monkeypatch) -> None:
    from slaif_gateway.api import dependencies as dependencies_module
    from slaif_gateway.api.dependencies import get_authenticated_gateway_key
    import slaif_gateway.main as main_module

    app = create_app()

    async def _fake_auth_dependency() -> AuthenticatedGatewayKey:
        return _fake_authenticated_gateway_key()

    async def _dummy_db_session():
        yield object()

    app.dependency_overrides[get_authenticated_gateway_key] = _fake_auth_dependency
    monkeypatch.setattr(dependencies_module, "_get_db_session_after_auth_header_check", _dummy_db_session)
    monkeypatch.setattr(main_module, "_get_db_session_after_auth_header_check", _dummy_db_session)

    client = TestClient(app)
    response = client.post("/v1/chat/completions", json={"model": "gpt-4.1-mini"})

    assert response.status_code == 422
    assert response.json()["error"]["type"] == "invalid_request_error"


def test_unsupported_model_returns_openai_shaped_error(monkeypatch) -> None:
    from slaif_gateway.api import dependencies as dependencies_module
    from slaif_gateway.api.dependencies import get_authenticated_gateway_key
    import slaif_gateway.main as main_module
    from slaif_gateway.services.routing_errors import ModelNotFoundError

    app = create_app()

    async def _fake_auth_dependency() -> AuthenticatedGatewayKey:
        return _fake_authenticated_gateway_key()

    async def _dummy_db_session():
        yield object()

    async def _fake_resolve_model(self, requested_model, authenticated_key):
        _ = (requested_model, authenticated_key)
        raise ModelNotFoundError()

    app.dependency_overrides[get_authenticated_gateway_key] = _fake_auth_dependency
    monkeypatch.setattr(dependencies_module, "_get_db_session_after_auth_header_check", _dummy_db_session)
    monkeypatch.setattr(main_module, "_get_db_session_after_auth_header_check", _dummy_db_session)
    monkeypatch.setattr(main_module.RouteResolutionService, "resolve_model", _fake_resolve_model)

    client = TestClient(app)
    response = client.post("/v1/chat/completions", json={"model": "nope", "messages": []})

    assert response.status_code == 404
    assert response.json()["error"]["type"] == "invalid_request_error"


def test_supported_model_reaches_route_resolution_then_returns_501(monkeypatch) -> None:
    from slaif_gateway.api import dependencies as dependencies_module
    from slaif_gateway.api.dependencies import get_authenticated_gateway_key
    import slaif_gateway.main as main_module

    app = create_app()
    resolver_calls: list[str] = []

    async def _fake_auth_dependency() -> AuthenticatedGatewayKey:
        return _fake_authenticated_gateway_key()

    async def _dummy_db_session():
        yield object()

    async def _fake_resolve_model(self, requested_model, authenticated_key):
        _ = authenticated_key
        resolver_calls.append(requested_model)
        return object()

    app.dependency_overrides[get_authenticated_gateway_key] = _fake_auth_dependency
    monkeypatch.setattr(dependencies_module, "_get_db_session_after_auth_header_check", _dummy_db_session)
    monkeypatch.setattr(main_module, "_get_db_session_after_auth_header_check", _dummy_db_session)
    monkeypatch.setattr(main_module.RouteResolutionService, "resolve_model", _fake_resolve_model)

    client = TestClient(app)
    response = client.post(
        "/v1/chat/completions",
        json={"model": "gpt-4.1-mini", "messages": [{"role": "user", "content": "hi"}]},
    )

    assert resolver_calls == ["gpt-4.1-mini"]
    assert response.status_code == 501
    assert response.json()["error"]["code"] == "provider_forwarding_not_implemented"


def test_stream_true_returns_501_not_streaming(monkeypatch) -> None:
    from slaif_gateway.api import dependencies as dependencies_module
    from slaif_gateway.api.dependencies import get_authenticated_gateway_key
    import slaif_gateway.main as main_module

    app = create_app()

    async def _fake_auth_dependency() -> AuthenticatedGatewayKey:
        return _fake_authenticated_gateway_key()

    async def _dummy_db_session():
        yield object()

    async def _fake_resolve_model(self, requested_model, authenticated_key):
        _ = (requested_model, authenticated_key)
        return object()

    app.dependency_overrides[get_authenticated_gateway_key] = _fake_auth_dependency
    monkeypatch.setattr(dependencies_module, "_get_db_session_after_auth_header_check", _dummy_db_session)
    monkeypatch.setattr(main_module, "_get_db_session_after_auth_header_check", _dummy_db_session)
    monkeypatch.setattr(main_module.RouteResolutionService, "resolve_model", _fake_resolve_model)

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

    for disallowed in ("httpx", "openrouter", "openai_upstream", "celery", "aiosmtplib"):
        assert disallowed not in source
