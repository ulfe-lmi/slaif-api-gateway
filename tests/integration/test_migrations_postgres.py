"""Integration smoke tests for PostgreSQL Alembic migrations."""

from __future__ import annotations

from alembic.config import Config
from alembic.script import ScriptDirectory
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine


EXPECTED_TABLES = {
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


@pytest.mark.asyncio
async def test_expected_tables_exist_after_migration(migrated_engine: AsyncEngine) -> None:
    async with migrated_engine.connect() as connection:
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

    missing = EXPECTED_TABLES - tables
    assert not missing, f"Missing expected tables after migration: {sorted(missing)}"


@pytest.mark.asyncio
async def test_citext_extension_exists(migrated_engine: AsyncEngine) -> None:
    async with migrated_engine.connect() as connection:
        result = await connection.execute(
            text("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'citext')")
        )
        assert result.scalar_one() is True


def test_alembic_has_exactly_one_head() -> None:
    config = Config("alembic.ini")
    script = ScriptDirectory.from_config(config)
    heads = script.get_heads()
    assert len(heads) == 1, f"Expected exactly one Alembic head, got: {heads}"
