"""PostgreSQL integration coverage for bare fresh Alembic upgrades."""

from __future__ import annotations

import asyncio
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


EXPECTED_APPLICATION_TABLES = {
    "institutions",
    "owners",
    "cohorts",
    "admin_users",
    "admin_sessions",
    "gateway_keys",
    "quota_reservations",
    "usage_ledger",
    "provider_configs",
    "model_routes",
    "pricing_rules",
    "fx_rates",
    "one_time_secrets",
    "email_deliveries",
    "audit_log",
    "background_jobs",
}


def _alembic_config(database_url: str) -> Config:
    repo_root = Path(__file__).resolve().parents[2]
    config = Config(str(repo_root / "alembic.ini"))
    config.set_main_option("script_location", str(repo_root / "migrations"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


async def _reset_public_schema(database_url: str) -> None:
    engine = create_async_engine(database_url, future=True)
    try:
        async with engine.begin() as connection:
            await connection.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
            await connection.execute(text("CREATE SCHEMA public"))
            await connection.execute(text("GRANT ALL ON SCHEMA public TO public"))
    finally:
        await engine.dispose()


async def _assert_fresh_upgrade_state(database_url: str, head_revision: str) -> None:
    engine = create_async_engine(database_url, future=True)
    try:
        async with engine.connect() as connection:
            version_length = await connection.scalar(
                text(
                    """
                    SELECT character_maximum_length
                    FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND table_name = 'alembic_version'
                      AND column_name = 'version_num'
                    """
                )
            )
            assert version_length is not None
            assert version_length >= len(head_revision)

            current_revision = await connection.scalar(text("SELECT version_num FROM alembic_version"))
            assert current_revision == head_revision

            result = await connection.execute(
                text(
                    """
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_schema = 'public'
                    """
                )
            )
            tables = {row[0] for row in result}

    finally:
        await engine.dispose()

    missing = EXPECTED_APPLICATION_TABLES - tables
    assert not missing, f"Missing expected tables after fresh migration: {sorted(missing)}"


def test_bare_fresh_alembic_upgrade_head_creates_wide_version_table(
    postgres_test_url: str,
) -> None:
    """Run Alembic directly on a clean PostgreSQL DB without test-helper precreation."""
    config = _alembic_config(postgres_test_url)
    head_revision = ScriptDirectory.from_config(config).get_current_head()
    assert head_revision is not None

    try:
        asyncio.run(_reset_public_schema(postgres_test_url))
        command.upgrade(config, "head")
        asyncio.run(_assert_fresh_upgrade_state(postgres_test_url, head_revision))
    finally:
        asyncio.run(_reset_public_schema(postgres_test_url))
        command.upgrade(config, "head")
