import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from slaif_gateway.config import get_settings
from slaif_gateway.db.session import get_engine, get_sessionmaker


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
