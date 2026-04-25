"""PostgreSQL integration-test fixtures with safe fallback behavior."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from urllib.parse import urlparse

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from tests.integration.db_test_utils import run_alembic_upgrade_head


@dataclass(slots=True)
class _DatabaseTarget:
    url: str
    source: str
    container: object | None = None


def _require_non_production() -> None:
    if os.getenv("APP_ENV", "").lower() == "production":
        pytest.skip("Integration DB setup is disabled when APP_ENV=production")


def _looks_like_safe_test_database_url(database_url: str) -> bool:
    parsed = urlparse(database_url)
    db_name = (parsed.path or "").lstrip("/").lower()
    return parsed.scheme in {"postgresql+asyncpg", "postgresql", "postgres"} and any(
        marker in db_name for marker in ("test", "dev", "local")
    )


def _with_asyncpg_scheme(database_url: str) -> str:
    if database_url.startswith("postgresql+asyncpg://"):
        return database_url
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if database_url.startswith("postgres://"):
        return database_url.replace("postgres://", "postgresql+asyncpg://", 1)
    return database_url


def _try_start_testcontainer() -> _DatabaseTarget | None:
    try:
        from testcontainers.postgres import PostgresContainer
    except Exception:  # noqa: BLE001
        return None

    try:
        container = PostgresContainer("postgres:16")
        container.start()
        sync_url = container.get_connection_url()
        return _DatabaseTarget(url=_with_asyncpg_scheme(sync_url), source="testcontainers", container=container)
    except Exception:  # noqa: BLE001
        return None


@pytest.fixture(scope="session")
def postgres_test_url() -> Iterator[str]:
    """Resolve a PostgreSQL URL for integration tests (env URL or Testcontainers)."""
    _require_non_production()

    env_url = os.getenv("TEST_DATABASE_URL")
    if env_url:
        if not _looks_like_safe_test_database_url(env_url):
            pytest.skip(
                "TEST_DATABASE_URL was provided but does not look like a safe PostgreSQL test URL "
                "(must include test/dev/local in DB name)."
            )
        yield env_url
        return

    target = _try_start_testcontainer()
    if target is None:
        pytest.skip(
            "Skipping integration tests: TEST_DATABASE_URL not set and Docker/Testcontainers is unavailable."
        )

    try:
        yield target.url
    finally:
        if target.container is not None:
            target.container.stop()


@pytest.fixture(scope="session")
def migrated_postgres_url(postgres_test_url: str) -> Iterator[str]:
    """Apply Alembic migrations to the resolved PostgreSQL test database."""
    run_alembic_upgrade_head(postgres_test_url)
    yield postgres_test_url


@pytest_asyncio.fixture
async def async_test_session(migrated_postgres_url: str) -> AsyncIterator[AsyncSession]:
    """Provide an async SQLAlchemy session wrapped in a rollback-only transaction."""
    engine: AsyncEngine = create_async_engine(migrated_postgres_url, future=True)
    async with engine.connect() as connection:
        transaction = await connection.begin()
        session_factory = async_sessionmaker(bind=connection, class_=AsyncSession, expire_on_commit=False)
        async with session_factory() as session:
            try:
                yield session
            finally:
                await session.close()
                if transaction.is_active:
                    await transaction.rollback()

    await engine.dispose()


@pytest_asyncio.fixture
async def migrated_engine(migrated_postgres_url: str) -> AsyncIterator[AsyncEngine]:
    """Provide a migrated engine for schema-level checks."""
    engine = create_async_engine(migrated_postgres_url, future=True)
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        yield engine
    finally:
        await engine.dispose()
