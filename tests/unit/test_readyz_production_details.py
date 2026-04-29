from __future__ import annotations

from fastapi.testclient import TestClient

from slaif_gateway.config import Settings
from slaif_gateway.db import session as db_session_module
from slaif_gateway.db.schema_status import SchemaStatus
from slaif_gateway.main import create_app
from slaif_gateway.utils.secrets import generate_secret_key


class _ConnectionContext:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def execute(self, statement):
        statement_text = str(statement)
        if "FROM provider_configs" in statement_text:
            return _FakeResult([])
        return None


class _FakeResult:
    def __init__(self, rows: list[dict[str, str]]) -> None:
        self._rows = rows

    def mappings(self) -> "_FakeResult":
        return self

    def all(self) -> list[dict[str, str]]:
        return self._rows


class _FakeEngine:
    def connect(self) -> _ConnectionContext:
        return _ConnectionContext()

    async def dispose(self) -> None:
        return None


def _production_settings(**overrides) -> Settings:
    values = {
        "APP_ENV": "production",
        "DATABASE_URL": "postgresql+asyncpg://user:secret@localhost:5432/slaif_test",
        "TOKEN_HMAC_SECRET_V1": "h" * 32,
        "ADMIN_SESSION_SECRET": "a" * 32,
        "ONE_TIME_SECRET_ENCRYPTION_KEY": generate_secret_key(),
        "OPENAI_UPSTREAM_API_KEY": "sk-live-openai-provider-aaaaaaaaaaaa",
        "OPENROUTER_API_KEY": "sk-or-live-openrouter-aaaaaaaaaaaa",
    }
    values.update(overrides)
    return Settings(**values)


def _install_fake_engine(monkeypatch) -> None:
    monkeypatch.setattr(db_session_module, "create_engine_from_settings", lambda settings: _FakeEngine())
    monkeypatch.setattr(
        db_session_module,
        "create_sessionmaker_from_engine",
        lambda received_engine: ("sessionmaker", received_engine),
    )


def test_readyz_production_hides_revision_details_by_default(monkeypatch) -> None:
    async def schema_ok(connection) -> SchemaStatus:
        _ = connection
        return SchemaStatus(
            status="ok",
            current_revision="current-secret-looking-revision",
            head_revision="head-secret-looking-revision",
            message="current",
        )

    _install_fake_engine(monkeypatch)
    monkeypatch.setattr("slaif_gateway.api.health.check_schema_current", schema_ok)
    app = create_app(_production_settings())

    with TestClient(app) as client:
        response = client.get("/readyz")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "database": "ok",
        "schema": "ok",
        "redis": "not_required",
        "provider_secrets": "ok",
    }
    assert "alembic_current" not in response.json()
    assert "alembic_head" not in response.json()
    assert "current-secret-looking-revision" not in response.text
    assert "postgresql://" not in response.text
    assert "current-secret-looking-revision" not in response.text


def test_readyz_production_can_include_revision_details_when_configured(monkeypatch) -> None:
    async def schema_ok(connection) -> SchemaStatus:
        _ = connection
        return SchemaStatus(
            status="ok",
            current_revision="current-revision",
            head_revision="head-revision",
            message="current",
        )

    _install_fake_engine(monkeypatch)
    monkeypatch.setattr("slaif_gateway.api.health.check_schema_current", schema_ok)
    app = create_app(_production_settings(READYZ_INCLUDE_DETAILS=True))

    with TestClient(app) as client:
        response = client.get("/readyz")

    assert response.status_code == 200
    assert response.json()["alembic_current"] == "current-revision"
    assert response.json()["alembic_head"] == "head-revision"
    assert response.json()["provider_secrets"] == "ok"
    assert "postgresql://" not in response.text
    assert "sk-live-openai-provider" not in response.text


def test_readyz_production_not_ready_hides_revision_details(monkeypatch) -> None:
    async def schema_outdated(connection) -> SchemaStatus:
        _ = connection
        return SchemaStatus(
            status="outdated",
            current_revision="old-revision",
            head_revision="head-revision",
            message="outdated",
        )

    _install_fake_engine(monkeypatch)
    monkeypatch.setattr("slaif_gateway.api.health.check_schema_current", schema_outdated)
    app = create_app(_production_settings())

    with TestClient(app) as client:
        response = client.get("/readyz")

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "database": "ok",
        "schema": "outdated",
        "redis": "not_required",
    }
    assert "old-revision" not in response.text
    assert "head-revision" not in response.text
