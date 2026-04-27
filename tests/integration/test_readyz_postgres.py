from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from slaif_gateway.config import Settings
from slaif_gateway.main import create_app

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
    assert response.json()["redis"] == "not_required"
