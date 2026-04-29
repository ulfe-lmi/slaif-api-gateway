"""PostgreSQL integration test for migration 0005 gateway key-prefix normalization."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from urllib.parse import urlparse

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

TARGET_REVISION_0004 = "0004_email_secrets_and_background_jobs"
TARGET_HEAD_0005 = "0005_fix_gateway_key_prefix_default"
CURRENT_HEAD = "0006_email_delivery_attempt_state"



def _safe_test_database_url_from_env() -> str:
    database_url = os.getenv("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("TEST_DATABASE_URL is required for migration integration validation")

    parsed = urlparse(database_url)
    db_name = (parsed.path or "").lstrip("/").lower()
    if parsed.scheme not in {"postgresql+asyncpg", "postgresql", "postgres"} or not any(
        marker in db_name for marker in ("test", "dev", "local")
    ):
        pytest.skip(
            "TEST_DATABASE_URL does not look like a safe PostgreSQL test URL "
            "(must use postgres scheme and include test/dev/local in DB name)."
        )

    return database_url


def _alembic_config(database_url: str) -> Config:
    repo_root = Path(__file__).resolve().parents[2]
    config = Config(str(repo_root / "alembic.ini"))
    config.set_main_option("script_location", str(repo_root / "migrations"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def _upgrade_to_revision(database_url: str, revision: str) -> None:
    command.upgrade(_alembic_config(database_url), revision)


async def _reset_public_schema(database_url: str) -> None:
    engine = create_async_engine(database_url, future=True)
    try:
        async with engine.begin() as connection:
            await connection.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
            await connection.execute(text("CREATE SCHEMA public"))
            await connection.execute(text("GRANT ALL ON SCHEMA public TO public"))
    finally:
        await engine.dispose()


async def _seed_prefix_rows_and_get_hashes(database_url: str) -> dict[str, str]:
    engine = create_async_engine(database_url, future=True)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    INSERT INTO institutions (id, name, country, notes, created_at, updated_at)
                    VALUES
                        ('00000000-0000-0000-0000-000000000001', 'Test Institution', 'SI', 'safe test data', NOW(), NOW())
                    """
                )
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO cohorts (id, name, description, starts_at, ends_at, created_at, updated_at)
                    VALUES
                        ('00000000-0000-0000-0000-000000000002', 'test-cohort-prefix', 'safe test data', NOW(), NOW() + INTERVAL '7 day', NOW(), NOW())
                    """
                )
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO owners (id, name, surname, email, institution_id, created_at, updated_at)
                    VALUES
                        ('00000000-0000-0000-0000-000000000003', 'Test', 'Owner', 'test.owner@example.org', '00000000-0000-0000-0000-000000000001', NOW(), NOW())
                    """
                )
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO admin_users (id, email, display_name, password_hash, role, is_active, created_at, updated_at)
                    VALUES
                        ('00000000-0000-0000-0000-000000000004', 'admin.prefix@example.org', 'Prefix Admin', '$argon2id$placeholder', 'admin', true, NOW(), NOW())
                    """
                )
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO gateway_keys (
                        id, public_key_id, key_prefix, token_hash, owner_id, cohort_id, status,
                        valid_from, valid_until, created_by_admin_user_id, created_at, updated_at
                    )
                    VALUES
                        (
                            '00000000-0000-0000-0000-000000000011',
                            'k_prefix_plain', 'sk-slaif', 'hmac-sha256:fake-digest-1',
                            '00000000-0000-0000-0000-000000000003', '00000000-0000-0000-0000-000000000002', 'active',
                            NOW(), NOW() + INTERVAL '30 day', '00000000-0000-0000-0000-000000000004', NOW(), NOW()
                        ),
                        (
                            '00000000-0000-0000-0000-000000000012',
                            'k_prefix_normalized', 'sk-slaif-', 'hmac-sha256:fake-digest-2',
                            '00000000-0000-0000-0000-000000000003', '00000000-0000-0000-0000-000000000002', 'active',
                            NOW(), NOW() + INTERVAL '30 day', '00000000-0000-0000-0000-000000000004', NOW(), NOW()
                        ),
                        (
                            '00000000-0000-0000-0000-000000000013',
                            'k_prefix_custom', 'sk-custom-', 'hmac-sha256:fake-digest-3',
                            '00000000-0000-0000-0000-000000000003', '00000000-0000-0000-0000-000000000002', 'active',
                            NOW(), NOW() + INTERVAL '30 day', '00000000-0000-0000-0000-000000000004', NOW(), NOW()
                        )
                    """
                )
            )

        async with engine.connect() as connection:
            rows = await connection.execute(
                text(
                    """
                    SELECT public_key_id, token_hash
                    FROM gateway_keys
                    WHERE public_key_id IN ('k_prefix_plain', 'k_prefix_normalized', 'k_prefix_custom')
                    ORDER BY public_key_id
                    """
                )
            )
            return {row[0]: row[1] for row in rows}
    finally:
        await engine.dispose()


async def _assert_post_migration_state(database_url: str, before_token_hashes: dict[str, str]) -> None:
    engine = create_async_engine(database_url, future=True)
    try:
        async with engine.connect() as connection:
            result = await connection.execute(
                text(
                    """
                    SELECT public_key_id, key_prefix, token_hash
                    FROM gateway_keys
                    WHERE public_key_id IN ('k_prefix_plain', 'k_prefix_normalized', 'k_prefix_custom')
                    ORDER BY public_key_id
                    """
                )
            )
            by_public_id = {row[0]: {"key_prefix": row[1], "token_hash": row[2]} for row in result.all()}

            assert by_public_id["k_prefix_plain"]["key_prefix"] == "sk-slaif-"
            assert by_public_id["k_prefix_normalized"]["key_prefix"] == "sk-slaif-"
            assert by_public_id["k_prefix_custom"]["key_prefix"] == "sk-custom-"

            for public_key_id, row in by_public_id.items():
                assert row["token_hash"] == before_token_hashes[public_key_id]
                assert not row["token_hash"].startswith("sk-")

            default_result = await connection.execute(
                text(
                    """
                    SELECT column_default
                    FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND table_name = 'gateway_keys'
                      AND column_name = 'key_prefix'
                    """
                )
            )
            column_default = default_result.scalar_one()
            assert "sk-slaif-" in column_default
    finally:
        await engine.dispose()


def test_migration_0005_normalizes_gateway_key_prefix_and_default() -> None:
    """Validate migration 0005 against a real PostgreSQL test database."""
    database_url = _safe_test_database_url_from_env()

    try:
        asyncio.run(_reset_public_schema(database_url))
        _upgrade_to_revision(database_url, TARGET_REVISION_0004)
        before_token_hashes = asyncio.run(_seed_prefix_rows_and_get_hashes(database_url))
        _upgrade_to_revision(database_url, "head")
        asyncio.run(_assert_post_migration_state(database_url, before_token_hashes))

        script = ScriptDirectory.from_config(_alembic_config(database_url))
        heads = script.get_heads()
        assert TARGET_HEAD_0005 in {revision.revision for revision in script.walk_revisions()}
        assert heads == [CURRENT_HEAD]
    finally:
        asyncio.run(_reset_public_schema(database_url))
        _upgrade_to_revision(database_url, "head")
