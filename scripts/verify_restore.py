#!/usr/bin/env python3
"""Verify a restored disposable PostgreSQL dataset is structurally readable."""

from __future__ import annotations

import asyncio
import os
from collections.abc import Mapping
from urllib.parse import urlparse

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine


REQUIRED_TABLES = ("institutions", "owners", "gateway_keys", "usage_ledger", "audit_log")
COUNT_TABLES = ("gateway_keys", "usage_ledger")
ALLOWED_SCHEMES = {"postgresql+asyncpg", "postgresql"}
ALLOWED_DATABASE_MARKERS = ("test", "dev", "local")


def validate_restore_target(url: str | None) -> tuple[bool, str]:
    """Validate the URL without exposing credentials or the raw target."""
    if not url:
        return False, "RESTORE_DATABASE_URL missing"
    parsed = urlparse(url)
    database = (parsed.path or "").lstrip("/").lower()
    if parsed.scheme not in ALLOWED_SCHEMES or not any(
        marker in database for marker in ALLOWED_DATABASE_MARKERS
    ):
        return False, "unsafe restore target"
    return True, database


async def verify_database(connection: AsyncConnection) -> Mapping[str, int]:
    """Check required tables and return bounded counts from the restored DB."""
    counts: dict[str, int] = {}
    for table in REQUIRED_TABLES:
        exists = await connection.scalar(
            text("SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = :table)"),
            {"table": table},
        )
        if not exists:
            raise LookupError(f"missing table: {table}")
        if table in COUNT_TABLES:
            # This identifier is selected from the fixed COUNT_TABLES constant,
            # never from user input.
            counts[table] = int(await connection.scalar(text(f"SELECT COUNT(*) FROM {table}")))
    return counts


def format_success(counts: Mapping[str, int]) -> str:
    row_counts = ",".join(f"{table}:{int(counts[table])}" for table in COUNT_TABLES)
    return (
        "RESULT=OK required_tables="
        + ",".join(REQUIRED_TABLES)
        + " row_counts="
        + row_counts
    )


async def main() -> int:
    url = os.environ.get("RESTORE_DATABASE_URL")
    valid, detail = validate_restore_target(url)
    if not valid:
        print(f"RESULT=FAIL {detail}")
        return 1

    engine = create_async_engine(url)  # type: ignore[arg-type]
    try:
        async with engine.connect() as connection:
            counts = await verify_database(connection)
    finally:
        await engine.dispose()
    print(format_success(counts))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
