"""Bounded local concurrency qualification for SME profiles.

These are deterministic correctness tests, not internet-scale load claims.
They exercise concurrent reservation accounting against a safe disposable
PostgreSQL target when provided, and otherwise skip safely.
"""

from __future__ import annotations

import asyncio
import os
from decimal import Decimal
from urllib.parse import urlparse

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


PROFILES = {
    "workshop_burst": 10,
    "sme_daily": 50,
    "codex_loop": 1,
}


def _safe_url() -> str | None:
    value = os.getenv("TEST_DATABASE_URL")
    if not value:
        return None
    parsed = urlparse(value)
    database = (parsed.path or "").lstrip("/").lower()
    if not value.startswith("postgresql") or not any(
        marker in database for marker in ("test", "dev", "local")
    ):
        return None
    return value.replace("postgresql://", "postgresql+asyncpg://")


@pytest.mark.parametrize("profile,count", PROFILES.items())
@pytest.mark.asyncio
async def test_concurrent_reservations_never_overspend(profile, count):
    url = _safe_url()
    if url is None:
        pytest.skip("safe TEST_DATABASE_URL is required")
    engine = create_async_engine(url, pool_size=10, max_overflow=5)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with engine.begin() as connection:
            await connection.execute(text("""
                CREATE TABLE IF NOT EXISTS concurrency_budget_probe (
                    id uuid primary key default gen_random_uuid(),
                    used numeric(18,9) not null default 0,
                    reserved numeric(18,9) not null default 0,
                    limit_value numeric(18,9) not null check (limit_value >= 0)
                )
            """))
            await connection.execute(text(
                "INSERT INTO concurrency_budget_probe (used, reserved, limit_value) VALUES (0, 0, 1)"
            ))

        async with sessions() as session:
            budget_id = await session.scalar(text("SELECT id FROM concurrency_budget_probe LIMIT 1"))

        async def reserve(session_factory, amount: Decimal):
            async with session_factory() as session:
                async with session.begin():
                    locked = await session.execute(
                        text("SELECT used, reserved FROM concurrency_budget_probe WHERE id = :id FOR UPDATE"),
                        {"id": budget_id},
                    )
                    row = locked.one()
                    projected = row.used + row.reserved + amount
                    if projected > Decimal("1"):
                        return "rejected"
                    await session.execute(
                        text("UPDATE concurrency_budget_probe SET reserved = reserved + :a WHERE id = :id"),
                        {"a": amount, "id": budget_id},
                    )
                    return "reserved"

        outcomes = await asyncio.gather(*(reserve(sessions, Decimal("0.25")) for _ in range(count)))
        assert "overspend" not in outcomes
        final = await sessions().scalar(
            text("SELECT used + reserved FROM concurrency_budget_probe LIMIT 1")
        )
        assert final <= 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_cleanup_probe_table():
    url = _safe_url()
    if url is None:
        pytest.skip("safe TEST_DATABASE_URL is required")
    engine = create_async_engine(url)
    try:
        async with engine.begin() as connection:
            await connection.execute(text("DROP TABLE IF EXISTS concurrency_budget_probe"))
    finally:
        await engine.dispose()
