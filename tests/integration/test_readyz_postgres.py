from __future__ import annotations

import asyncio
import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from slaif_gateway.config import Settings
from slaif_gateway.main import create_app
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
