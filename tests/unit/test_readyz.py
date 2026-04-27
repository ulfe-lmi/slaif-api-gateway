from __future__ import annotations

from fastapi.testclient import TestClient

from slaif_gateway.config import Settings
from slaif_gateway.db.schema_status import SchemaStatus
from slaif_gateway.db import session as db_session_module
from slaif_gateway.main import create_app


class _ConnectionContext:
    def __init__(self, *, fail: bool = False) -> None:
        self._fail = fail

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def execute(self, statement) -> None:
        _ = statement
        if self._fail:
            raise RuntimeError("database unavailable")


class _FakeEngine:
    def __init__(self, *, fail: bool = False) -> None:
        self._fail = fail
        self.connect_calls = 0

    def connect(self) -> _ConnectionContext:
        self.connect_calls += 1
        return _ConnectionContext(fail=self._fail)

    async def dispose(self) -> None:
        return None


class _FakeRedis:
    def __init__(self, *, fail: bool = False) -> None:
        self._fail = fail
        self.ping_calls = 0

    async def ping(self) -> bool:
        self.ping_calls += 1
        if self._fail:
            raise RuntimeError("redis unavailable")
        return True

    async def aclose(self) -> None:
        return None


def test_healthz_remains_public_and_ok() -> None:
    client = TestClient(create_app(Settings(DATABASE_URL=None)))

    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readyz_without_database_url_reports_not_configured() -> None:
    client = TestClient(create_app(Settings(DATABASE_URL=None)))

    response = client.get("/readyz")

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "database": "not_configured",
        "redis": "not_required",
    }


def test_readyz_with_successful_database_check_reports_ready(monkeypatch) -> None:
    engine = _FakeEngine()
    async def schema_ok(connection) -> SchemaStatus:
        _ = connection
        return SchemaStatus(
            status="ok",
            current_revision="0005_fix_gateway_key_prefix_default",
            head_revision="0005_fix_gateway_key_prefix_default",
            message="current",
        )

    monkeypatch.setattr(db_session_module, "create_engine_from_settings", lambda settings: engine)
    monkeypatch.setattr(
        db_session_module,
        "create_sessionmaker_from_engine",
        lambda received_engine: ("sessionmaker", received_engine),
    )
    monkeypatch.setattr("slaif_gateway.api.health.check_schema_current", schema_ok)
    app = create_app(
        Settings(DATABASE_URL="postgresql+asyncpg://user:secret@localhost:5432/slaif_test")
    )

    with TestClient(app) as client:
        response = client.get("/readyz")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "database": "ok",
        "schema": "ok",
        "alembic_current": "0005_fix_gateway_key_prefix_default",
        "alembic_head": "0005_fix_gateway_key_prefix_default",
        "redis": "not_required",
    }
    assert engine.connect_calls == 1


def test_readyz_with_database_failure_reports_not_ready(monkeypatch) -> None:
    engine = _FakeEngine(fail=True)
    monkeypatch.setattr(db_session_module, "create_engine_from_settings", lambda settings: engine)
    monkeypatch.setattr(
        db_session_module,
        "create_sessionmaker_from_engine",
        lambda received_engine: ("sessionmaker", received_engine),
    )
    app = create_app(
        Settings(DATABASE_URL="postgresql+asyncpg://user:secret@localhost:5432/slaif_test")
    )

    with TestClient(app) as client:
        response = client.get("/readyz")

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "database": "error",
        "redis": "not_required",
    }


def test_readyz_reports_redis_ok_when_rate_limits_enabled(monkeypatch) -> None:
    engine = _FakeEngine()
    redis_client = _FakeRedis()

    async def schema_ok(connection) -> SchemaStatus:
        _ = connection
        return SchemaStatus(
            status="ok",
            current_revision="head",
            head_revision="head",
            message="current",
        )

    monkeypatch.setattr(db_session_module, "create_engine_from_settings", lambda settings: engine)
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
    app = create_app(
        Settings(
            DATABASE_URL="postgresql+asyncpg://user:secret@localhost:5432/slaif_test",
            ENABLE_REDIS_RATE_LIMITS=True,
            REDIS_URL="redis://localhost:6379/0",
        )
    )

    with TestClient(app) as client:
        response = client.get("/readyz")

    assert response.status_code == 200
    assert response.json()["redis"] == "ok"
    assert redis_client.ping_calls == 1


def test_readyz_returns_not_ready_when_enabled_redis_fails(monkeypatch) -> None:
    engine = _FakeEngine()
    redis_client = _FakeRedis(fail=True)

    async def schema_ok(connection) -> SchemaStatus:
        _ = connection
        return SchemaStatus(
            status="ok",
            current_revision="head",
            head_revision="head",
            message="current",
        )

    monkeypatch.setattr(db_session_module, "create_engine_from_settings", lambda settings: engine)
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
    app = create_app(
        Settings(
            DATABASE_URL="postgresql+asyncpg://user:secret@localhost:5432/slaif_test",
            ENABLE_REDIS_RATE_LIMITS=True,
            REDIS_URL="redis://localhost:6379/0",
        )
    )

    with TestClient(app) as client:
        response = client.get("/readyz")

    assert response.status_code == 503
    assert response.json()["database"] == "ok"
    assert response.json()["schema"] == "ok"
    assert response.json()["redis"] == "error"
