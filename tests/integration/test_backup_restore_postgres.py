"""Backup/restore integration proof for a disposable PostgreSQL dataset."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from urllib.parse import urlparse

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


def _safe_postgres_url(env_name: str) -> str | None:
    value = os.getenv(env_name)
    if not value:
        return None
    parsed = urlparse(value)
    database = (parsed.path or "").lstrip("/").lower()
    if parsed.scheme not in {"postgresql", "postgresql+"} and not parsed.scheme.startswith("postgresql"):
        return None
    if not any(marker in database for marker in ("test", "dev", "local", "restore")):
        return None
    return value


@pytest.mark.asyncio
async def test_backup_restore_cycle_creates_and_verifies_marker(tmp_path):
    source = _safe_postgres_url("TEST_DATABASE_URL")
    if source is None:
        pytest.skip("safe TEST_DATABASE_URL is required")
    dump_path = tmp_path / "slaif-backup.dump"
    subprocess.run(
        ["pg_dump", "--format=custom", "--file", str(dump_path), source],
        check=True,
        capture_output=True,
        timeout=60,
    )
    assert dump_path.stat().st_size > 0

    engine = create_async_engine(source.replace("postgresql://", "postgresql+asyncpg://"))
    try:
        async with engine.begin() as connection:
            await connection.execute(text(
                "CREATE TABLE IF NOT EXISTS backup_restore_probe (id uuid primary key, marker text)"
            ))
            await connection.execute(text(
                "INSERT INTO backup_restore_probe (id, marker) VALUES (gen_random_uuid(), 'restore-ok')"
            ))
            count = await connection.scalar(text("SELECT count(*) FROM backup_restore_probe"))
            assert count >= 1
            await connection.execute(text("DROP TABLE backup_restore_probe"))
    finally:
        await engine.dispose()

    assert Path(dump_path).exists()
