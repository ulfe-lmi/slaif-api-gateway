from __future__ import annotations

from fastapi.testclient import TestClient

from slaif_gateway.config import Settings
from slaif_gateway.db import session as db_session_module
from slaif_gateway.db.schema_status import SchemaStatus
from slaif_gateway.main import create_app


class _ConnectionContext:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def execute(self, statement) -> None:
        _ = statement


class _FakeEngine:
    def connect(self) -> _ConnectionContext:
        return _ConnectionContext()

    async def dispose(self) -> None:
        return None


class _FakeRedis:
    def __init__(self, *, fail: bool = False) -> None:
        self._fail = fail

    async def ping(self) -> bool:
        if self._fail:
            raise RuntimeError("redis unavailable")
        return True

    async def aclose(self) -> None:
        return None


def _install_ready_app(monkeypatch, redis_client: _FakeRedis):
    async def schema_ok(connection) -> SchemaStatus:
        _ = connection
        return SchemaStatus(
            status="ok",
            current_revision="head",
            head_revision="head",
            message="current",
        )

    monkeypatch.setattr(db_session_module, "create_engine_from_settings", lambda settings: _FakeEngine())
    monkeypatch.setattr(
        db_session_module,
        "create_sessionmaker_from_engine",
        lambda received_engine: ("sessionmaker", received_engine),
    )
    monkeypatch.setattr("slaif_gateway.api.health.check_schema_current", schema_ok)
    monkeypatch.setattr(
        "slaif_gateway.cache.redis.create_redis_client_from_settings",
        lambda settings: redis_client,
    )
    return create_app(
        Settings(
            DATABASE_URL="postgresql+asyncpg://user:secret@localhost:5432/slaif_test",
            ENABLE_REDIS_RATE_LIMITS=True,
            REDIS_URL="redis://localhost:6379/0",
        )
    )


def test_readyz_redis_not_required_when_rate_limits_disabled() -> None:
    app = create_app(Settings(DATABASE_URL=None, ENABLE_REDIS_RATE_LIMITS=False))

    with TestClient(app) as client:
        response = client.get("/readyz")

    assert response.status_code == 503
    assert response.json()["redis"] == "not_required"


def test_readyz_redis_ok_when_enabled_and_ping_succeeds(monkeypatch) -> None:
    app = _install_ready_app(monkeypatch, _FakeRedis())

    with TestClient(app) as client:
        response = client.get("/readyz")

    assert response.status_code == 200
    assert response.json()["redis"] == "ok"


def test_readyz_redis_error_when_enabled_and_ping_fails(monkeypatch) -> None:
    app = _install_ready_app(monkeypatch, _FakeRedis(fail=True))

    with TestClient(app) as client:
        response = client.get("/readyz")

    assert response.status_code == 503
    assert response.json()["redis"] == "error"
    assert response.json()["database"] == "ok"
