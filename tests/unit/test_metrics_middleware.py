from __future__ import annotations

from fastapi.testclient import TestClient

from slaif_gateway.config import Settings
from slaif_gateway.main import create_app


def test_http_request_count_and_duration_are_emitted() -> None:
    client = TestClient(create_app(Settings(APP_ENV="test", DATABASE_URL=None)))

    response = client.get("/healthz", headers={"X-Request-ID": "metrics-test-id"})
    metrics = client.get("/metrics").text

    assert response.status_code == 200
    assert 'gateway_http_requests_total{endpoint="/healthz",method="GET",status="200"}' in metrics
    assert 'gateway_http_request_duration_seconds_count{endpoint="/healthz",method="GET"}' in metrics
    assert "metrics-test-id" not in metrics


def test_http_metrics_do_not_include_query_strings_or_api_keys() -> None:
    client = TestClient(create_app(Settings(APP_ENV="test", DATABASE_URL=None)))

    client.get("/healthz?api_key=sk-slaif-public.secretvalue")
    metrics = client.get("/metrics").text

    assert "api_key" not in metrics
    assert "sk-slaif-public.secretvalue" not in metrics
    assert 'endpoint="/healthz"' in metrics
