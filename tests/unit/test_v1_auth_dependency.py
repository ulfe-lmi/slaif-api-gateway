from __future__ import annotations

import inspect
import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from slaif_gateway.main import create_app
from slaif_gateway.schemas.auth import AuthenticatedGatewayKey

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


def test_invalid_auth_scheme_and_malformed_bearer_return_openai_shaped_401() -> None:
    app = create_app()
    client = TestClient(app)

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
