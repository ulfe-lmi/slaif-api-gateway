"""Async database engine and session helpers."""

from collections.abc import AsyncIterator

from starlette.requests import Request
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


def create_engine_from_settings(settings: Settings) -> AsyncEngine:
    """Build and return an async SQLAlchemy engine from explicit settings."""
    connect_args: dict[str, object] = {
        "timeout": settings.DATABASE_CONNECT_TIMEOUT_SECONDS,
    }
    if settings.DATABASE_STATEMENT_TIMEOUT_MS is not None:
        connect_args["server_settings"] = {
            "statement_timeout": str(settings.DATABASE_STATEMENT_TIMEOUT_MS)
        }

    return create_async_engine(
        _resolve_database_url(settings),
        future=True,
        pool_size=settings.DATABASE_POOL_SIZE,
        max_overflow=settings.DATABASE_MAX_OVERFLOW,
        pool_timeout=settings.DATABASE_POOL_TIMEOUT_SECONDS,
        pool_recycle=settings.DATABASE_POOL_RECYCLE_SECONDS,
        pool_pre_ping=settings.DATABASE_POOL_PRE_PING,
        connect_args=connect_args,
    )


def create_sessionmaker_from_engine(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Build and return an async sessionmaker for an existing engine."""
    return async_sessionmaker(engine, expire_on_commit=False)


def get_engine(settings: Settings | None = None) -> AsyncEngine:
    """Build and return an async SQLAlchemy engine."""
    return create_engine_from_settings(settings or get_settings())


def get_sessionmaker(
    settings: Settings | None = None,
) -> async_sessionmaker[AsyncSession]:
    """Build and return an async sessionmaker."""
    return create_sessionmaker_from_engine(get_engine(settings))


def get_sessionmaker_from_app(request: Request) -> async_sessionmaker[AsyncSession]:
    """Return the FastAPI lifespan-managed sessionmaker from app state."""
    session_factory = getattr(request.app.state, "db_sessionmaker", None)
    if session_factory is None:
        raise RuntimeError("Database sessionmaker is not available on application state.")
    return session_factory


async def get_db_session(settings: Settings | None = None) -> AsyncIterator[AsyncSession]:
    """Yield an async DB session for request-scoped usage."""
    session_factory = get_sessionmaker(settings)
    async with session_factory() as session:
        yield session


async def get_db_session_from_app_state(request: Request) -> AsyncIterator[AsyncSession]:
    """Yield an async DB session from the lifespan-managed app sessionmaker."""
    session_factory = get_sessionmaker_from_app(request)
    async with session_factory() as session:
        yield session
