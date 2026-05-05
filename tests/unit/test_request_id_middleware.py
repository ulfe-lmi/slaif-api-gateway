from __future__ import annotations

import json

from fastapi import Request
from fastapi.testclient import TestClient
import structlog

from slaif_gateway.api.middleware import SLAIF_DIAGNOSTIC_ID_HEADER
from slaif_gateway.config import Settings
from slaif_gateway.main import create_app


def _app():
    app = create_app(Settings(DATABASE_URL=None, APP_ENV="test"))

    @app.get("/request-id-state")
    async def request_id_state(request: Request):
        return {
            "request_id": request.state.request_id,
            "gateway_request_id": request.state.gateway_request_id,
        }

    @app.get("/request-id-log")
    async def request_id_log(request: Request):
        structlog.get_logger("tests.request_id").info("request.id.bound")
        return {
            "request_id": request.state.request_id,
            "gateway_request_id": request.state.gateway_request_id,
        }

    return app


def test_response_includes_generated_request_id() -> None:
    response = TestClient(_app()).get("/healthz")

    assert response.status_code == 200
    assert response.headers["X-Request-ID"].startswith("req-")
    assert response.headers[SLAIF_DIAGNOSTIC_ID_HEADER].startswith("gw-")


def test_safe_incoming_request_id_is_preserved_and_available_in_state() -> None:
    response = TestClient(_app()).get(
        "/request-id-state",
        headers={"X-Request-ID": "client-request-123"},
    )

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "client-request-123"
    assert response.headers[SLAIF_DIAGNOSTIC_ID_HEADER].startswith("gw-")
    assert response.json()["request_id"] == "client-request-123"
    assert response.json()["gateway_request_id"] == response.headers[SLAIF_DIAGNOSTIC_ID_HEADER]


def test_unsafe_incoming_request_id_is_replaced() -> None:
    unsafe = "x" * 200

    response = TestClient(_app()).get("/request-id-state", headers={"X-Request-ID": unsafe})

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] != unsafe
    assert response.headers["X-Request-ID"].startswith("req-")
    assert response.json()["request_id"] == response.headers["X-Request-ID"]
    assert response.json()["gateway_request_id"] == response.headers[SLAIF_DIAGNOSTIC_ID_HEADER]


def test_request_ids_are_bound_to_structlog_context(capsys) -> None:
    response = TestClient(_app()).get(
        "/request-id-log",
        headers={"X-Request-ID": "client-request-456"},
    )

    assert response.status_code == 200
    log_event = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert log_event["event"] == "request.id.bound"
    assert log_event["request_id"] == "client-request-456"
    assert log_event["gateway_request_id"] == response.headers[SLAIF_DIAGNOSTIC_ID_HEADER]
