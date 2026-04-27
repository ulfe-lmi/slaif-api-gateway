from __future__ import annotations

from fastapi.testclient import TestClient

from slaif_gateway.config import Settings
from slaif_gateway.db import session as db_session_module
from slaif_gateway.db.schema_status import SchemaStatus
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
            raise RuntimeError(
                "could not connect to postgresql://user:secret@localhost:5432/slaif_test"
            )


class _FakeEngine:
    def __init__(self, *, fail: bool = False) -> None:
        self._fail = fail

    def connect(self) -> _ConnectionContext:
        return _ConnectionContext(fail=self._fail)

    async def dispose(self) -> None:
        return None


def _install_fake_engine(monkeypatch, engine: _FakeEngine) -> None:
    monkeypatch.setattr(db_session_module, "create_engine_from_settings", lambda settings: engine)
    monkeypatch.setattr(
        db_session_module,
        "create_sessionmaker_from_engine",
        lambda received_engine: ("sessionmaker", received_engine),
    )


def _settings() -> Settings:
    return Settings(DATABASE_URL="postgresql+asyncpg://user:secret@localhost:5432/slaif_test")


def test_readyz_with_database_and_current_schema_returns_ready(monkeypatch) -> None:
    async def schema_ok(connection) -> SchemaStatus:
        _ = connection
        return SchemaStatus(
            status="ok",
            current_revision="head",
            head_revision="head",
            message="current",
        )

    _install_fake_engine(monkeypatch, _FakeEngine())
    monkeypatch.setattr("slaif_gateway.api.health.check_schema_current", schema_ok)
    app = create_app(_settings())

    with TestClient(app) as client:
        response = client.get("/readyz")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "database": "ok",
        "schema": "ok",
        "alembic_current": "head",
        "alembic_head": "head",
        "redis": "not_required",
    }


def test_readyz_with_missing_alembic_version_returns_not_ready(monkeypatch) -> None:
    async def schema_missing(connection) -> SchemaStatus:
        _ = connection
        return SchemaStatus(
            status="missing",
            current_revision=None,
            head_revision="head",
            message="missing",
        )

    _install_fake_engine(monkeypatch, _FakeEngine())
    monkeypatch.setattr("slaif_gateway.api.health.check_schema_current", schema_missing)
    app = create_app(_settings())

    with TestClient(app) as client:
        response = client.get("/readyz")

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "database": "ok",
        "schema": "missing",
        "alembic_current": None,
        "alembic_head": "head",
        "redis": "not_required",
    }


def test_readyz_with_outdated_schema_returns_not_ready(monkeypatch) -> None:
    async def schema_outdated(connection) -> SchemaStatus:
        _ = connection
        return SchemaStatus(
            status="outdated",
            current_revision="old",
            head_revision="head",
            message="outdated",
        )

    _install_fake_engine(monkeypatch, _FakeEngine())
    monkeypatch.setattr("slaif_gateway.api.health.check_schema_current", schema_outdated)
    app = create_app(_settings())

    with TestClient(app) as client:
        response = client.get("/readyz")

    assert response.status_code == 503
    body = response.json()
    assert body["database"] == "ok"
    assert body["schema"] == "outdated"
    assert body["alembic_current"] == "old"
    assert body["alembic_head"] == "head"
    assert body["redis"] == "not_required"


def test_readyz_with_database_error_does_not_expose_credentials(monkeypatch) -> None:
    _install_fake_engine(monkeypatch, _FakeEngine(fail=True))
    app = create_app(_settings())

    with TestClient(app) as client:
        response = client.get("/readyz")

    assert response.status_code == 503
    body_text = response.text
    assert response.json() == {
        "status": "not_ready",
        "database": "error",
        "redis": "not_required",
    }
    assert "secret" not in body_text
    assert "postgresql://" not in body_text


def test_readyz_without_database_url_still_reports_not_configured() -> None:
    client = TestClient(create_app(Settings(DATABASE_URL=None)))

    response = client.get("/readyz")

    assert response.status_code == 503
    assert response.json()["database"] == "not_configured"
    assert response.json()["redis"] == "not_required"
