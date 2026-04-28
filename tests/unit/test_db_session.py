import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from slaif_gateway.config import Settings, get_settings
from slaif_gateway.db import session as db_session_module
from slaif_gateway.db.session import create_engine_from_settings, get_engine, get_sessionmaker


@pytest.fixture(autouse=True)
def clear_settings_cache() -> None:
    get_settings.cache_clear()


def test_get_engine_raises_when_database_url_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(RuntimeError, match="DATABASE_URL is not configured"):
        get_engine()


def test_get_engine_constructs_without_connecting(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://user:secret@localhost:5432/slaif")

    engine = get_engine()

    assert isinstance(engine, AsyncEngine)
    assert engine.url.drivername == "postgresql+asyncpg"


def test_get_sessionmaker_constructs_without_connecting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://user:secret@localhost:5432/slaif")

    sessionmaker = get_sessionmaker()

    assert sessionmaker.kw["bind"].url.drivername == "postgresql+asyncpg"


def test_create_engine_from_settings_passes_pool_and_timeout_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_create_async_engine(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(db_session_module, "create_async_engine", fake_create_async_engine)
    settings = Settings(
        DATABASE_URL="postgresql+asyncpg://user:secret@localhost:5432/slaif",
        DATABASE_POOL_SIZE=7,
        DATABASE_MAX_OVERFLOW=4,
        DATABASE_POOL_TIMEOUT_SECONDS=11.5,
        DATABASE_POOL_RECYCLE_SECONDS=900,
        DATABASE_POOL_PRE_PING=False,
        DATABASE_CONNECT_TIMEOUT_SECONDS=3.5,
        DATABASE_STATEMENT_TIMEOUT_MS=25000,
    )

    engine = create_engine_from_settings(settings)

    assert engine is not None
    assert captured["url"] == "postgresql+asyncpg://user:secret@localhost:5432/slaif"
    assert captured["future"] is True
    assert captured["pool_size"] == 7
    assert captured["max_overflow"] == 4
    assert captured["pool_timeout"] == 11.5
    assert captured["pool_recycle"] == 900
    assert captured["pool_pre_ping"] is False
    assert captured["connect_args"] == {
        "timeout": 3.5,
        "server_settings": {"statement_timeout": "25000"},
    }


def test_create_engine_from_settings_omits_statement_timeout_when_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_create_async_engine(url, **kwargs):
        _ = url
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(db_session_module, "create_async_engine", fake_create_async_engine)
    settings = Settings(
        DATABASE_URL="postgresql+asyncpg://user:secret@localhost:5432/slaif",
        DATABASE_CONNECT_TIMEOUT_SECONDS=8,
        DATABASE_STATEMENT_TIMEOUT_MS=None,
    )

    create_engine_from_settings(settings)

    assert captured["connect_args"] == {"timeout": 8}
