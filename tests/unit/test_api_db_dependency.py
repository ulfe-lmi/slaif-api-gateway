from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from slaif_gateway.api import dependencies as dependency_module
from slaif_gateway.api.dependencies import get_authenticated_gateway_key
from slaif_gateway.api.errors import OpenAICompatibleError
from slaif_gateway.config import Settings
from slaif_gateway.main import create_app
from tests.unit.test_v1_models_auth import _fake_authenticated_gateway_key


class _SessionContext:
    def __init__(self, session: object) -> None:
        self.session = session

    async def __aenter__(self) -> object:
        return self.session

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


class _SessionFactory:
    def __init__(self) -> None:
        self.calls = 0
        self.session = object()

    def __call__(self) -> _SessionContext:
        self.calls += 1
        return _SessionContext(self.session)


def _request_with_sessionmaker(session_factory: object):
    return SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(db_sessionmaker=session_factory))
    )


@pytest.mark.asyncio
async def test_public_db_dependency_uses_app_state_sessionmaker() -> None:
    session_factory = _SessionFactory()
    request = _request_with_sessionmaker(session_factory)

    sessions = [
        session
        async for session in dependency_module.get_db_session_after_auth_header_check(request)
    ]

    assert sessions == [session_factory.session]
    assert session_factory.calls == 1


@pytest.mark.asyncio
async def test_missing_app_state_sessionmaker_returns_clear_openai_error() -> None:
    request = _request_with_sessionmaker(None)

    with pytest.raises(OpenAICompatibleError) as exc_info:
        sessions = [
            session
            async for session in dependency_module.get_db_session_after_auth_header_check(request)
        ]
        _ = sessions

    assert exc_info.value.status_code == 500
    assert exc_info.value.code == "database_session_unavailable"
    assert "Database session could not be created" in exc_info.value.message


def test_missing_authorization_does_not_open_db_session(monkeypatch) -> None:
    app = create_app(Settings(DATABASE_URL=None))
    calls = {"count": 0}

    async def _failing_db_session_dependency(*args):
        _ = args
        calls["count"] += 1
        raise AssertionError("DB session should not be opened for missing Authorization")
        yield  # pragma: no cover

    monkeypatch.setattr(
        dependency_module,
        "_get_db_session_after_auth_header_check",
        _failing_db_session_dependency,
    )

    response = TestClient(app).get("/v1/models")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "missing_authorization"
    assert calls["count"] == 0


def test_malformed_authorization_does_not_open_db_session(monkeypatch) -> None:
    app = create_app(Settings(DATABASE_URL=None))
    calls = {"count": 0}

    async def _failing_db_session_dependency(*args):
        _ = args
        calls["count"] += 1
        raise AssertionError("DB session should not be opened for malformed Authorization")
        yield  # pragma: no cover

    monkeypatch.setattr(
        dependency_module,
        "_get_db_session_after_auth_header_check",
        _failing_db_session_dependency,
    )

    response = TestClient(app).get("/v1/models", headers={"Authorization": "Bearer"})

    assert response.status_code == 401
    assert response.json()["error"]["type"] == "authentication_error"
    assert calls["count"] == 0


def test_missing_app_sessionmaker_on_db_backed_route_returns_openai_error() -> None:
    app = create_app(Settings(DATABASE_URL=None))

    async def _fake_auth_dependency():
        return _fake_authenticated_gateway_key()

    app.dependency_overrides[get_authenticated_gateway_key] = _fake_auth_dependency

    response = TestClient(app).get("/v1/models")

    assert response.status_code == 500
    assert response.json()["error"]["type"] == "server_error"
    assert response.json()["error"]["code"] == "database_session_unavailable"
