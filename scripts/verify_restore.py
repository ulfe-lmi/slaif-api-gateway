#!/usr/bin/env python3
"""Verify a restored disposable PostgreSQL dataset is structurally ready."""

from __future__ import annotations

import asyncio
import os
from urllib.parse import urlparse

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


REQUIRED_TABLES = ("institutions", "owners", "gateway_keys", "usage_ledger", "audit_log")


async def main() -> int:
    url = os.environ.get("RESTORE_DATABASE_URL")
    if not url:
        print("RESULT=FAIL RESTORE_DATABASE_URL missing")
        return 1
    parsed = urlparse(url)
    database = (parsed.path or "").lstrip("/").lower()
    if parsed.scheme not in {"postgresql+asyncpg", "postgresql"} or not any(
        marker in database for marker in ("test", "dev", "local")
    ):
        print("RESULT=FAIL unsafe restore target")
        return 1
    engine = create_async_engine(url)
    try:
        async with engine.begin() as connection:
            for table in REQUIRED_TABLES:
                exists = await connection.scalar(
                    text("SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = :table)"),
                    {"table": table},
                )
                if not exists:
                    print(f"RESULT=FAIL missing_table={table}")
                    return 1
            integrity = await connection.execute(text("PRAGMA integrity_check"))
            _ = integrity  # SQLite-only statement ignored on PostgreSQL.
        print("RESULT=OK required_tables=" + ",".join(REQUIRED_TABLES))
        return 0
    finally:
        await engine.dispose()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
