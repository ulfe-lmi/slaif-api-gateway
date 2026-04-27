from __future__ import annotations

import inspect
import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from slaif_gateway.main import create_app
from slaif_gateway.schemas.auth import AuthenticatedGatewayKey
from slaif_gateway.schemas.openai import OpenAIModel


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

    response = client.get("/v1/models")

    assert response.status_code == 401
    body = response.json()
    assert "error" in body
    assert set(body["error"].keys()) == {"message", "type", "param", "code"}


def test_authenticated_request_returns_empty_catalog_without_provider_calls(monkeypatch) -> None:
    from slaif_gateway.api import dependencies as dependencies_module
    from slaif_gateway.api.dependencies import get_authenticated_gateway_key
    import slaif_gateway.api.openai_compat as main_module

    app = create_app()

    async def _fake_auth_dependency() -> AuthenticatedGatewayKey:
        return _fake_authenticated_gateway_key()

    async def _dummy_db_session():
        yield object()

    async def _fake_list_visible_models(self, authenticated_key: AuthenticatedGatewayKey):
        _ = authenticated_key
        return []

    app.dependency_overrides[get_authenticated_gateway_key] = _fake_auth_dependency
    monkeypatch.setattr(dependencies_module, "_get_db_session_after_auth_header_check", _dummy_db_session)
    monkeypatch.setattr(main_module, "_get_db_session_after_auth_header_check", _dummy_db_session)
    monkeypatch.setattr(main_module.ModelCatalogService, "list_visible_models", _fake_list_visible_models)

    client = TestClient(app)
    response = client.get("/v1/models")

    assert response.status_code == 200
    assert response.json() == {"object": "list", "data": []}


def test_authenticated_request_returns_openai_model_objects(monkeypatch) -> None:
    from slaif_gateway.api import dependencies as dependencies_module
    from slaif_gateway.api.dependencies import get_authenticated_gateway_key
    import slaif_gateway.api.openai_compat as main_module

    app = create_app()

    async def _fake_auth_dependency() -> AuthenticatedGatewayKey:
        return _fake_authenticated_gateway_key()

    async def _dummy_db_session():
        yield object()

    async def _fake_list_visible_models(self, authenticated_key: AuthenticatedGatewayKey):
        _ = authenticated_key
        return [
            OpenAIModel(id="gpt-4.1-mini", owned_by="openai"),
            OpenAIModel(id="classroom-cheap", owned_by="openrouter"),
        ]

    app.dependency_overrides[get_authenticated_gateway_key] = _fake_auth_dependency
    monkeypatch.setattr(dependencies_module, "_get_db_session_after_auth_header_check", _dummy_db_session)
    monkeypatch.setattr(main_module, "_get_db_session_after_auth_header_check", _dummy_db_session)
    monkeypatch.setattr(main_module.ModelCatalogService, "list_visible_models", _fake_list_visible_models)

    client = TestClient(app)
    response = client.get("/v1/models")

    assert response.status_code == 200
    body = response.json()
    assert body["object"] == "list"
    assert len(body["data"]) == 2
    assert body["data"][0] == {
        "id": "gpt-4.1-mini",
        "object": "model",
        "created": 0,
        "owned_by": "openai",
    }


def test_v1_models_route_module_safety_constraints() -> None:
    import slaif_gateway.api.openai_compat as main_module

    source = inspect.getsource(main_module).lower()

    for disallowed in ("httpx", "celery", "aiosmtplib"):
        assert disallowed not in source
