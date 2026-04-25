"""Integration-test DB helpers for safe PostgreSQL migration runs."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from alembic import command
from alembic.config import Config


def _assert_safe_postgres_test_url(database_url: str) -> None:
    parsed = urlparse(database_url)
    if parsed.scheme not in {"postgresql+asyncpg", "postgresql", "postgres"}:
        raise ValueError(
            "Integration migrations require a PostgreSQL URL using postgresql+asyncpg/postgresql/postgres"
        )

    db_name = (parsed.path or "").lstrip("/").lower()
    safe_markers = ("test", "dev", "local")
    if not db_name or not any(marker in db_name for marker in safe_markers):
        raise ValueError(
            "Refusing to run Alembic for integration tests against a non-test database URL. "
            "Database name must include one of: test/dev/local."
        )


def run_alembic_upgrade_head(database_url: str) -> None:
    """Run Alembic upgrade head against an explicitly supplied test database URL."""
    _assert_safe_postgres_test_url(database_url)

    repo_root = Path(__file__).resolve().parents[2]
    alembic_ini = repo_root / "alembic.ini"
    config = Config(str(alembic_ini))
    config.set_main_option("script_location", str(repo_root / "migrations"))
    config.set_main_option("sqlalchemy.url", database_url)

    command.upgrade(config, "head")
