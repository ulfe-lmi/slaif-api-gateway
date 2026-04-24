"""Async database engine and session helpers."""

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from slaif_gateway.config import Settings, get_settings


def _resolve_database_url(settings: Settings | None = None) -> str:
    resolved_settings = settings or get_settings()
    database_url = resolved_settings.DATABASE_URL
    if not database_url:
        raise RuntimeError(
            "DATABASE_URL is not configured. Set DATABASE_URL to use database functionality."
        )
    return database_url


def get_engine(settings: Settings | None = None) -> AsyncEngine:
    """Build and return an async SQLAlchemy engine."""
    return create_async_engine(_resolve_database_url(settings), future=True)


def get_sessionmaker(
    settings: Settings | None = None,
) -> async_sessionmaker[AsyncSession]:
    """Build and return an async sessionmaker."""
    return async_sessionmaker(get_engine(settings), expire_on_commit=False)


async def get_db_session(settings: Settings | None = None) -> AsyncIterator[AsyncSession]:
    """Yield an async DB session for request-scoped usage."""
    session_factory = get_sessionmaker(settings)
    async with session_factory() as session:
        yield session
