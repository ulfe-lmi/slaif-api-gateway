from __future__ import annotations

from fastapi.testclient import TestClient

from slaif_gateway.config import Settings
from slaif_gateway.db.schema_status import SchemaStatus
from slaif_gateway.db import session as db_session_module
from slaif_gateway.main import create_app
from slaif_gateway.utils.secrets import generate_secret_key


class _ConnectionContext:
    def __init__(self, *, fail: bool = False, provider_rows: list[dict[str, str]] | None = None) -> None:
        self._fail = fail
        self._provider_rows = provider_rows or []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def execute(self, statement):
        statement_text = str(statement)
        if self._fail:
            raise RuntimeError("database unavailable")
        if "FROM provider_configs" in statement_text:
            return _FakeResult(self._provider_rows)
        return None


class _FakeResult:
    def __init__(self, rows: list[dict[str, str]]) -> None:
        self._rows = rows

    def mappings(self) -> "_FakeResult":
        return self

    def all(self) -> list[dict[str, str]]:
        return self._rows


class _FakeEngine:
    def __init__(self, *, fail: bool = False, provider_rows: list[dict[str, str]] | None = None) -> None:
        self._fail = fail
        self._provider_rows = provider_rows or []
        self.connect_calls = 0

    def connect(self) -> _ConnectionContext:
        self.connect_calls += 1
        return _ConnectionContext(fail=self._fail, provider_rows=self._provider_rows)

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
            current_revision="0006_email_delivery_attempt_state",
            head_revision="0006_email_delivery_attempt_state",
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
        "alembic_current": "0006_email_delivery_attempt_state",
        "alembic_head": "0006_email_delivery_attempt_state",
        "redis": "not_required",
    }
    assert engine.connect_calls == 1


def test_readyz_production_reports_missing_provider_secret_env_vars(monkeypatch) -> None:
    env_var = "CLASSROOM_PROVIDER_SECRET"
    monkeypatch.delenv(env_var, raising=False)
    engine = _FakeEngine(provider_rows=[{"api_key_env_var": env_var}])

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
    app = create_app(
        Settings(
            APP_ENV="production",
            DATABASE_URL="postgresql+asyncpg://user:secret@localhost:5432/slaif_test",
            TOKEN_HMAC_SECRET_V1="h" * 32,
            ADMIN_SESSION_SECRET="a" * 32,
            ONE_TIME_SECRET_ENCRYPTION_KEY=generate_secret_key(),
            OPENAI_UPSTREAM_API_KEY="sk-live-openai-provider-aaaaaaaaaaaa",
            OPENROUTER_API_KEY="sk-or-live-openrouter-aaaaaaaaaaaa",
            READYZ_INCLUDE_DETAILS=True,
        )
    )

    with TestClient(app) as client:
        response = client.get("/readyz")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    assert body["provider_secrets"] == "missing"
    assert body["missing_provider_secret_env_vars"] == env_var
    assert "sk-live-openai-provider" not in response.text


def test_readyz_production_hides_missing_provider_secret_details_by_default(monkeypatch) -> None:
    env_var = "CLASSROOM_PROVIDER_SECRET"
    monkeypatch.delenv(env_var, raising=False)
    engine = _FakeEngine(provider_rows=[{"api_key_env_var": env_var}])

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
    app = create_app(
        Settings(
            APP_ENV="production",
            DATABASE_URL="postgresql+asyncpg://user:secret@localhost:5432/slaif_test",
            TOKEN_HMAC_SECRET_V1="h" * 32,
            ADMIN_SESSION_SECRET="a" * 32,
            ONE_TIME_SECRET_ENCRYPTION_KEY=generate_secret_key(),
            OPENAI_UPSTREAM_API_KEY="sk-live-openai-provider-aaaaaaaaaaaa",
            OPENROUTER_API_KEY="sk-or-live-openrouter-aaaaaaaaaaaa",
        )
    )

    with TestClient(app) as client:
        response = client.get("/readyz")

    assert response.status_code == 503
    body = response.json()
    assert body["provider_secrets"] == "missing"
    assert "missing_provider_secret_env_vars" not in body
    assert env_var not in response.text


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
