from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from slaif_gateway.api.dependencies import get_authenticated_gateway_key
from slaif_gateway.main import create_app
from slaif_gateway.schemas.auth import AuthenticatedGatewayKey


def _auth(
    *,
    allow_all_endpoints: bool = False,
    allowed_endpoints: tuple[str, ...] = (),
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
        allow_all_endpoints=allow_all_endpoints,
        allowed_endpoints=allowed_endpoints,
        allowed_providers=None,
        cost_limit_eur=None,
        token_limit_total=None,
        request_limit_total=None,
        rate_limit_policy={},
    )


def _chat_body() -> dict[str, object]:
    return {
        "model": "classroom-cheap",
        "messages": [{"role": "user", "content": "hello"}],
        "max_tokens": 20,
    }


def _app_with_auth(monkeypatch, authenticated_key: AuthenticatedGatewayKey):
    import slaif_gateway.api.openai_compat as openai_module

    app = create_app()
    state: dict[str, int] = {"models_calls": 0, "chat_calls": 0}

    async def _fake_auth_dependency() -> AuthenticatedGatewayKey:
        return authenticated_key

    async def _dummy_db_session():
        yield object()

    async def _fake_list_visible_models(self, auth: AuthenticatedGatewayKey):
        _ = (self, auth)
        state["models_calls"] += 1
        return []

    async def _fake_handle_chat_completion(*, payload, authenticated_key, settings):
        _ = (payload, authenticated_key, settings)
        state["chat_calls"] += 1
        return JSONResponse(status_code=200, content={"id": "chatcmpl_test", "choices": []})

    app.dependency_overrides[get_authenticated_gateway_key] = _fake_auth_dependency
    monkeypatch.setattr(openai_module, "_get_db_session_after_auth_header_check", _dummy_db_session)
    monkeypatch.setattr(openai_module.ModelCatalogService, "list_visible_models", _fake_list_visible_models)
    monkeypatch.setattr(openai_module, "handle_chat_completion", _fake_handle_chat_completion)
    return app, state


def test_allow_all_endpoints_can_call_models_and_chat(monkeypatch) -> None:
    app, state = _app_with_auth(monkeypatch, _auth(allow_all_endpoints=True))
    client = TestClient(app)

    models_response = client.get("/v1/models")
    chat_response = client.post("/v1/chat/completions", json=_chat_body())

    assert models_response.status_code == 200
    assert chat_response.status_code == 200
    assert state == {"models_calls": 1, "chat_calls": 1}


def test_models_endpoint_allow_list_allows_models_and_rejects_chat(monkeypatch) -> None:
    app, state = _app_with_auth(monkeypatch, _auth(allowed_endpoints=("models.list",)))
    client = TestClient(app)

    models_response = client.get("/v1/models")
    chat_response = client.post("/v1/chat/completions", json=_chat_body())

    assert models_response.status_code == 200
    assert chat_response.status_code == 403
    assert chat_response.json()["error"] == {
        "message": "The requested endpoint is not allowed for this key",
        "type": "permission_error",
        "param": None,
        "code": "endpoint_not_allowed",
    }
    assert state == {"models_calls": 1, "chat_calls": 0}


def test_chat_endpoint_allow_list_allows_chat_and_rejects_models(monkeypatch) -> None:
    app, state = _app_with_auth(monkeypatch, _auth(allowed_endpoints=("chat.completions",)))
    client = TestClient(app)

    models_response = client.get("/v1/models")
    chat_response = client.post("/v1/chat/completions", json=_chat_body())

    assert models_response.status_code == 403
    assert chat_response.status_code == 200
    assert models_response.json()["error"]["type"] == "permission_error"
    assert models_response.json()["error"]["code"] == "endpoint_not_allowed"
    assert state == {"models_calls": 0, "chat_calls": 1}


def test_empty_endpoint_allow_list_rejects_existing_v1_endpoints(monkeypatch) -> None:
    app, state = _app_with_auth(monkeypatch, _auth())
    client = TestClient(app)

    models_response = client.get("/v1/models")
    chat_response = client.post("/v1/chat/completions", json=_chat_body())

    assert models_response.status_code == 403
    assert chat_response.status_code == 403
    assert models_response.json()["error"]["code"] == "endpoint_not_allowed"
    assert chat_response.json()["error"]["code"] == "endpoint_not_allowed"
    assert state == {"models_calls": 0, "chat_calls": 0}


def test_endpoint_rejection_happens_before_route_pricing_quota_or_provider_work(monkeypatch) -> None:
    app, state = _app_with_auth(monkeypatch, _auth(allowed_endpoints=("models.list",)))
    client = TestClient(app)

    response = client.post("/v1/chat/completions", json=_chat_body())

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "endpoint_not_allowed"
    assert state["chat_calls"] == 0

