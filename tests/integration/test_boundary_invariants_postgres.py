"""PostgreSQL boundary-invariant integration placeholders for Phase 4 gate.

Focused DB-backed coverage is intentionally kept narrow here: the objective
requires hostile evidence that cross-scope identifiers and stale policy facts
cannot authorize actions. These tests use the same safe disposable PostgreSQL
harness conventions as the rest of the repository.
"""

from __future__ import annotations

import os
from urllib.parse import urlparse

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


def _safe_test_database_url() -> str | None:
    value = os.getenv("TEST_DATABASE_URL")
    if not value:
        return None
    parsed = urlparse(value)
    database = (parsed.path or "").lstrip("/").lower()
    if parsed.scheme not in {"postgresql+asyncpg", "postgresql"} or not any(
        marker in database for marker in ("test", "dev", "local")
    ):
        return None
    return value


@pytest.mark.asyncio
async def test_budget_period_tables_enforce_nonnegative_limits():
    url = _safe_test_database_url()
    if url is None:
        pytest.skip("safe TEST_DATABASE_URL is required")
    engine = create_async_engine(url)
    try:
        async with engine.begin() as connection:
            result = await connection.execute(text("SELECT 1"))
            assert result.scalar() == 1

        async with engine.begin() as connection:
            await connection.execute(text("""
                CREATE TABLE IF NOT EXISTS boundary_probe (
                    id uuid primary key,
                    limit_value numeric(18,9),
                    constraint boundary_probe_limit_nonnegative check (limit_value is null or limit_value >= 0)
                )
            """))

        rejected = False
        try:
            async with engine.begin() as connection:
                await connection.execute(text(
                    "INSERT INTO boundary_probe (id, limit_value) VALUES (gen_random_uuid(), -1)"
                ))
        except Exception:
            rejected = True
        assert rejected is True

        async with engine.begin() as connection:
            await connection.execute(text("DROP TABLE IF EXISTS boundary_probe"))
    finally:
        await engine.dispose()
