from __future__ import annotations

import inspect
import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from slaif_gateway.config import get_settings
from slaif_gateway.main import create_app
from slaif_gateway.schemas.auth import AuthenticatedGatewayKey
from slaif_gateway.services.auth_service import MalformedGatewayKeyError

_DISALLOWED_IMPORT_TERMS = (
    "openrouter",
    "aiosmtplib",
    "celery",
)
_DISALLOWED_LOGIC_TERMS = (
    "quota",
    "rate_limit",
    "allowed_models",
    "allowed_endpoints",
    "commit(",
    "set_last_used_at",
    "last_used_at",
)


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


def test_missing_authorization_returns_401_without_database_url(monkeypatch) -> None:
    from slaif_gateway.api import dependencies as dependency_module

    app = create_app()
    client = TestClient(app)

    calls = {"count": 0}

    async def _failing_db_session_dependency():
        calls["count"] += 1
        raise AssertionError("DB session should not be opened for missing Authorization")
        yield  # pragma: no cover

    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(
        dependency_module,
        "_get_db_session_after_auth_header_check",
        _failing_db_session_dependency,
    )

    response = client.get("/v1/models")

    assert response.status_code == 401
    body = response.json()
    assert "error" in body
    assert body["error"]["type"] == "authentication_error"
    assert body["error"]["code"] == "missing_authorization"
    assert calls["count"] == 0


def test_invalid_auth_scheme_and_malformed_bearer_return_openai_shaped_401(monkeypatch) -> None:
    from slaif_gateway.api import dependencies as dependency_module

    app = create_app()
    client = TestClient(app)

    calls = {"count": 0}

    async def _failing_db_session_dependency():
        calls["count"] += 1
        raise AssertionError("DB session should not be opened for malformed Authorization")
        yield  # pragma: no cover

    monkeypatch.setattr(
        dependency_module,
        "_get_db_session_after_auth_header_check",
        _failing_db_session_dependency,
    )

    basic_response = client.get("/v1/models", headers={"Authorization": "Basic abc"})
    assert basic_response.status_code == 401
    basic_body = basic_response.json()
    assert "error" in basic_body
    assert basic_body["error"]["type"] == "authentication_error"

    malformed_response = client.get("/v1/models", headers={"Authorization": "Bearer"})
    assert malformed_response.status_code == 401
    malformed_body = malformed_response.json()
    assert "error" in malformed_body
    assert malformed_body["error"]["type"] == "authentication_error"
    assert calls["count"] == 0


def test_unconfigured_prefix_is_rejected_with_openai_shaped_401(monkeypatch) -> None:
    monkeypatch.setenv("GATEWAY_KEY_PREFIX", "sk-slaif-")
    monkeypatch.setenv("GATEWAY_KEY_ACCEPTED_PREFIXES", "sk-slaif-")
    get_settings.cache_clear()

    app = create_app()
    client = TestClient(app)

    response = client.get(
        "/v1/models",
        headers={"Authorization": "Bearer sk-ulfe-public1234abcd.sssssssssssssssssssssssssssssssssssssssssss"},
    )

    assert response.status_code == 401
    body = response.json()
    assert body["error"]["type"] == "authentication_error"
    assert body["error"]["code"] == "malformed_gateway_key"
    get_settings.cache_clear()


def test_configured_legacy_prefix_reaches_service_layer(monkeypatch) -> None:
    from slaif_gateway.api import dependencies as dependency_module

    monkeypatch.setenv("GATEWAY_KEY_PREFIX", "sk-slaif-")
    monkeypatch.setenv("GATEWAY_KEY_ACCEPTED_PREFIXES", "sk-slaif-,sk-ulfe-")
    get_settings.cache_clear()

    app = create_app()
    client = TestClient(app)

    async def _dummy_db_session():
        yield object()

    async def _raise_not_found(self, authorization_header, now=None):
        raise MalformedGatewayKeyError()

    monkeypatch.setattr(
        dependency_module,
        "_get_db_session_after_auth_header_check",
        _dummy_db_session,
    )
    monkeypatch.setattr(
        dependency_module.GatewayAuthService,
        "authenticate_authorization_header",
        _raise_not_found,
    )

    response = client.get(
        "/v1/models",
        headers={"Authorization": "Bearer sk-ulfe-public1234abcd.sssssssssssssssssssssssssssssssssssssssssss"},
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "malformed_gateway_key"
    get_settings.cache_clear()


def test_optional_mocked_service_auth_success_without_postgres(monkeypatch) -> None:
    from slaif_gateway.api import dependencies as dependency_module

    app = create_app()
    client = TestClient(app)

    async def _dummy_db_session():
        yield object()

    async def _fake_authenticate(self, authorization_header, now=None) -> AuthenticatedGatewayKey:
        _ = (authorization_header, now)
        return _fake_authenticated_gateway_key()

    monkeypatch.setattr(
        dependency_module,
        "_get_db_session_after_auth_header_check",
        _dummy_db_session,
    )
    monkeypatch.setattr(
        dependency_module.GatewayAuthService,
        "authenticate_authorization_header",
        _fake_authenticate,
    )

    response = client.get(
        "/v1/models",
        headers={"Authorization": "Bearer sk-slaif-public1234abcd.sssssssssssssssssssssssssssssssssssssssssss"},
    )

    assert response.status_code == 200
    assert response.json() == {"object": "list", "data": []}


def test_auth_dependency_override_supports_authenticated_test_path() -> None:
    from slaif_gateway.api.dependencies import get_authenticated_gateway_key

    app = create_app()

    async def _fake_auth_dependency() -> AuthenticatedGatewayKey:
        return _fake_authenticated_gateway_key()

    app.dependency_overrides[get_authenticated_gateway_key] = _fake_auth_dependency
    client = TestClient(app)

    response = client.get("/v1/models")

    assert response.status_code == 200
    assert response.json() == {"object": "list", "data": []}


def test_dependency_module_safety_constraints() -> None:
    import slaif_gateway.api.dependencies as dependency_module

    source = inspect.getsource(dependency_module)
    import_lines = [
        line.strip().lower()
        for line in source.splitlines()
        if line.strip().startswith(("import ", "from "))
    ]

    for line in import_lines:
        for term in _DISALLOWED_IMPORT_TERMS:
            assert term not in line, f"forbidden import term '{term}' in dependency module: {line}"

    lowered_source = source.lower()
    for term in _DISALLOWED_LOGIC_TERMS:
        assert term not in lowered_source
