from __future__ import annotations

from fastapi.testclient import TestClient

from slaif_gateway.cache import redis as redis_module
from slaif_gateway.config import Settings
from slaif_gateway.main import create_app


class _FakeRedis:
    def __init__(self) -> None:
        self.closed = False

    async def aclose(self) -> None:
        self.closed = True


def test_redis_client_not_created_when_rate_limits_disabled(monkeypatch) -> None:
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


def test_redis_client_created_once_and_closed_when_rate_limits_enabled(monkeypatch) -> None:
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
