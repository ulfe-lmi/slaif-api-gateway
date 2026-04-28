from __future__ import annotations

from fastapi.testclient import TestClient

from slaif_gateway.config import Settings
from slaif_gateway.main import create_app
from slaif_gateway.utils.secrets import generate_secret_key


def _production_settings(**overrides) -> Settings:
    values = {
        "APP_ENV": "production",
        "DATABASE_URL": None,
        "TOKEN_HMAC_SECRET_V1": "h" * 32,
        "ADMIN_SESSION_SECRET": "a" * 32,
        "ONE_TIME_SECRET_ENCRYPTION_KEY": generate_secret_key(),
    }
    values.update(overrides)
    return Settings(**values)


def test_metrics_returns_prometheus_text_in_test_when_enabled() -> None:
    app = create_app(Settings(APP_ENV="test", DATABASE_URL=None, ENABLE_METRICS=True))

    response = TestClient(app).get("/metrics")

    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
    assert "gateway_http_requests_total" in response.text


def test_metrics_disabled_returns_not_found() -> None:
    app = create_app(Settings(APP_ENV="test", DATABASE_URL=None, ENABLE_METRICS=False))

    response = TestClient(app).get("/metrics")

    assert response.status_code == 404


def test_metrics_not_public_in_production_by_default() -> None:
    app = create_app(_production_settings())

    response = TestClient(app).get("/metrics")

    assert response.status_code == 403


def test_metrics_public_in_production_requires_explicit_setting() -> None:
    app = create_app(_production_settings(METRICS_PUBLIC_IN_PRODUCTION=True))

    response = TestClient(app).get("/metrics")

    assert response.status_code == 200
    assert "gateway_http_requests_total" in response.text


def test_metrics_auth_disabled_in_production_behavior_unchanged() -> None:
    app = create_app(_production_settings(METRICS_REQUIRE_AUTH=False))

    response = TestClient(app).get("/metrics")

    assert response.status_code == 200
    assert "gateway_http_requests_total" in response.text


def test_metrics_allows_configured_ip_when_auth_required() -> None:
    app = create_app(_production_settings(METRICS_ALLOWED_IPS="testclient"))

    response = TestClient(app).get("/metrics")

    assert response.status_code == 200


def test_metrics_output_does_not_include_secrets() -> None:
    secret = "sk-slaif-public.secretvalue"
    app = create_app(Settings(APP_ENV="test", DATABASE_URL=None, ENABLE_METRICS=True))
    client = TestClient(app)

    client.get("/healthz", headers={"Authorization": f"Bearer {secret}", "X-Request-ID": "safe-id"})
    response = client.get("/metrics")

    assert response.status_code == 200
    assert secret not in response.text
    assert "Authorization" not in response.text
    assert "token_hash" not in response.text
    assert "user prompt body" not in response.text.lower()
    assert "assistant completion body" not in response.text.lower()
