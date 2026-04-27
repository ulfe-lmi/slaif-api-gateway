from __future__ import annotations

from fastapi.testclient import TestClient

from slaif_gateway.config import Settings
from slaif_gateway.cache import redis as redis_module
from slaif_gateway.db import session as db_session_module
from slaif_gateway.main import create_app


class _FakeEngine:
    def __init__(self) -> None:
        self.disposed = False

    async def dispose(self) -> None:
        self.disposed = True


class _FakeRedis:
    def __init__(self) -> None:
        self.closed = False

    async def aclose(self) -> None:
        self.closed = True


def test_create_app_stores_settings() -> None:
    settings = Settings(DATABASE_URL=None)

    app = create_app(settings)

    assert app.state.settings is settings


def test_lifespan_creates_engine_and_sessionmaker_once(monkeypatch) -> None:
    settings = Settings(DATABASE_URL="postgresql+asyncpg://user:secret@localhost:5432/slaif_test")
    engine = _FakeEngine()
    calls = {"engines": 0}

    def _create_engine_from_settings(received_settings):
        assert received_settings is settings
        calls["engines"] += 1
        return engine

    monkeypatch.setattr(
        db_session_module,
        "create_engine_from_settings",
        _create_engine_from_settings,
    )
    monkeypatch.setattr(
        db_session_module,
        "create_sessionmaker_from_engine",
        lambda received_engine: ("sessionmaker", received_engine),
    )

    app = create_app(settings)
    with TestClient(app) as client:
        assert client.get("/healthz").status_code == 200
        assert client.get("/healthz").status_code == 200
        assert app.state.db_engine is engine
        assert app.state.db_sessionmaker == ("sessionmaker", engine)
        assert calls["engines"] == 1

    assert engine.disposed is True


def test_app_starts_without_database_url() -> None:
    app = create_app(Settings(DATABASE_URL=None))

    with TestClient(app) as client:
        assert client.get("/healthz").status_code == 200
        assert app.state.db_engine is None
        assert app.state.db_sessionmaker is None
        assert app.state.redis_client is None


def test_lifespan_does_not_create_redis_when_rate_limits_disabled(monkeypatch) -> None:
    calls = {"redis": 0}

    def _create_redis(settings):
        _ = settings
        calls["redis"] += 1
        return _FakeRedis()

    monkeypatch.setattr(redis_module, "create_redis_client_from_settings", _create_redis)
    app = create_app(Settings(DATABASE_URL=None, ENABLE_REDIS_RATE_LIMITS=False))

    with TestClient(app) as client:
        assert client.get("/healthz").status_code == 200
        assert app.state.redis_client is None

    assert calls["redis"] == 0


def test_lifespan_creates_and_closes_redis_when_rate_limits_enabled(monkeypatch) -> None:
    redis_client = _FakeRedis()
    calls = {"redis": 0}

    def _create_redis(settings):
        assert settings.REDIS_URL == "redis://localhost:6379/0"
        calls["redis"] += 1
        return redis_client

    monkeypatch.setattr(redis_module, "create_redis_client_from_settings", _create_redis)
    app = create_app(
        Settings(
            DATABASE_URL=None,
            ENABLE_REDIS_RATE_LIMITS=True,
            REDIS_URL="redis://localhost:6379/0",
        )
    )

    with TestClient(app) as client:
        assert client.get("/healthz").status_code == 200
        assert app.state.redis_client is redis_client
        assert calls["redis"] == 1

    assert redis_client.closed is True
