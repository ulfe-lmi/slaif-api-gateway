from __future__ import annotations

import asyncio
import os
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from slaif_gateway.config import Settings
from slaif_gateway.main import create_app
from slaif_gateway.utils.secrets import generate_secret_key
from tests.integration.db_test_utils import run_alembic_upgrade_head

pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL is required for readiness PostgreSQL integration tests.",
)


def test_readyz_reports_database_ok_without_redis(migrated_postgres_url: str) -> None:
    app = create_app(Settings(DATABASE_URL=migrated_postgres_url))

    with TestClient(app) as client:
        response = client.get("/readyz")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["database"] == "ok"
    assert response.json()["schema"] == "ok"
    assert response.json()["alembic_current"] == response.json()["alembic_head"]
    assert response.json()["redis"] == "not_required"


def test_readyz_production_hides_schema_revisions_by_default(migrated_postgres_url: str) -> None:
    app = create_app(
        Settings(
            APP_ENV="production",
            DATABASE_URL=migrated_postgres_url,
            TOKEN_HMAC_SECRET_V1="h" * 32,
            ADMIN_SESSION_SECRET="a" * 32,
            ONE_TIME_SECRET_ENCRYPTION_KEY=generate_secret_key(),
            OPENAI_UPSTREAM_API_KEY="sk-live-openai-provider-aaaaaaaaaaaa",
            OPENROUTER_API_KEY="sk-or-live-openrouter-aaaaaaaaaaaa",
        )
    )

    with TestClient(app) as client:
        response = client.get("/readyz")

    assert response.status_code == 200
    body = response.json()
    assert body == {
        "status": "ok",
        "database": "ok",
        "schema": "ok",
        "redis": "not_required",
        "provider_secrets": "ok",
    }
    assert "alembic_current" not in body
    assert "alembic_head" not in body
    assert "postgresql://" not in response.text


def test_readyz_production_can_include_schema_revisions(migrated_postgres_url: str) -> None:
    app = create_app(
        Settings(
            APP_ENV="production",
            DATABASE_URL=migrated_postgres_url,
            TOKEN_HMAC_SECRET_V1="h" * 32,
            ADMIN_SESSION_SECRET="a" * 32,
            ONE_TIME_SECRET_ENCRYPTION_KEY=generate_secret_key(),
            OPENAI_UPSTREAM_API_KEY="sk-live-openai-provider-aaaaaaaaaaaa",
            OPENROUTER_API_KEY="sk-or-live-openrouter-aaaaaaaaaaaa",
            READYZ_INCLUDE_DETAILS=True,
        )
    )

    with TestClient(app) as client:
        response = client.get("/readyz")

    assert response.status_code == 200
    body = response.json()
    assert body["schema"] == "ok"
    assert body["provider_secrets"] == "ok"
    assert body["alembic_current"] == body["alembic_head"]
    assert "postgresql://" not in response.text


async def _insert_enabled_provider_config(database_url: str, *, env_var: str) -> None:
    engine = create_async_engine(database_url, future=True)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO provider_configs "
                    "(id, provider, display_name, kind, base_url, api_key_env_var, enabled, "
                    "created_at, updated_at) "
                    "VALUES (:id, 'classroom-openai', 'Classroom OpenAI', "
                    "'openai_compatible', 'https://provider.example/v1', :env_var, true, "
                    "now(), now()) "
                    "ON CONFLICT (provider) DO UPDATE SET api_key_env_var = EXCLUDED.api_key_env_var, "
                    "enabled = true"
                ),
                {"id": uuid.uuid4(), "env_var": env_var},
            )
    finally:
        await engine.dispose()


async def _delete_provider_config(database_url: str) -> None:
    engine = create_async_engine(database_url, future=True)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text("DELETE FROM provider_configs WHERE provider = 'classroom-openai'")
            )
    finally:
        await engine.dispose()


def test_readyz_production_checks_enabled_provider_config_env_vars(
    migrated_postgres_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env_var = "CLASSROOM_PROVIDER_SECRET"
    monkeypatch.delenv(env_var, raising=False)
    try:
        asyncio.run(_insert_enabled_provider_config(migrated_postgres_url, env_var=env_var))
        settings_kwargs = {
            "APP_ENV": "production",
            "DATABASE_URL": migrated_postgres_url,
            "TOKEN_HMAC_SECRET_V1": "h" * 32,
            "ADMIN_SESSION_SECRET": "a" * 32,
            "ONE_TIME_SECRET_ENCRYPTION_KEY": generate_secret_key(),
            "OPENAI_UPSTREAM_API_KEY": "sk-live-openai-provider-aaaaaaaaaaaa",
            "OPENROUTER_API_KEY": "sk-or-live-openrouter-aaaaaaaaaaaa",
            "READYZ_INCLUDE_DETAILS": True,
        }
        app = create_app(Settings(**settings_kwargs))

        with TestClient(app) as client:
            response = client.get("/readyz")

        assert response.status_code == 503
        body = response.json()
        assert body["status"] == "not_ready"
        assert body["provider_secrets"] == "missing"
        assert body["missing_provider_secret_env_vars"] == env_var
        assert "sk-live-openai-provider" not in response.text

        monkeypatch.setenv(env_var, "sk-classroom-provider-aaaaaaaaaaaa")
        app = create_app(Settings(**settings_kwargs))

        with TestClient(app) as client:
            response = client.get("/readyz")

        assert response.status_code == 200
        body = response.json()
        assert body["provider_secrets"] == "ok"
        assert "missing_provider_secret_env_vars" not in body
        assert "sk-classroom-provider" not in response.text
    finally:
        asyncio.run(_delete_provider_config(migrated_postgres_url))


async def _reset_public_schema(database_url: str) -> None:
    engine = create_async_engine(database_url, future=True)
    try:
        async with engine.begin() as connection:
            await connection.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
            await connection.execute(text("CREATE SCHEMA public"))
            await connection.execute(text("GRANT ALL ON SCHEMA public TO public"))
    finally:
        await engine.dispose()


def test_readyz_reports_missing_schema_on_fresh_database(postgres_test_url: str) -> None:
    try:
        asyncio.run(_reset_public_schema(postgres_test_url))
        app = create_app(Settings(DATABASE_URL=postgres_test_url))

        with TestClient(app) as client:
            response = client.get("/readyz")

        assert response.status_code == 503
        body = response.json()
        assert body["status"] == "not_ready"
        assert body["database"] == "ok"
        assert body["schema"] == "missing"
        assert body["alembic_current"] is None
        assert body["alembic_head"]
        assert body["redis"] == "not_required"
    finally:
        asyncio.run(_reset_public_schema(postgres_test_url))
        run_alembic_upgrade_head(postgres_test_url)
