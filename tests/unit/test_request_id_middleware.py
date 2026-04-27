from __future__ import annotations

from fastapi import Request
from fastapi.testclient import TestClient

from slaif_gateway.config import Settings
from slaif_gateway.main import create_app


def _app():
    app = create_app(Settings(DATABASE_URL=None, APP_ENV="test"))

    @app.get("/request-id-state")
    async def request_id_state(request: Request):
        return {"request_id": request.state.request_id}

    return app


def test_response_includes_generated_request_id() -> None:
    response = TestClient(_app()).get("/healthz")

    assert response.status_code == 200
    assert response.headers["X-Request-ID"].startswith("req-")


def test_safe_incoming_request_id_is_preserved_and_available_in_state() -> None:
    response = TestClient(_app()).get(
        "/request-id-state",
        headers={"X-Request-ID": "client-request-123"},
    )

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "client-request-123"
    assert response.json() == {"request_id": "client-request-123"}


def test_unsafe_incoming_request_id_is_replaced() -> None:
    unsafe = "x" * 200

    response = TestClient(_app()).get("/request-id-state", headers={"X-Request-ID": unsafe})

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] != unsafe
    assert response.headers["X-Request-ID"].startswith("req-")
    assert response.json()["request_id"] == response.headers["X-Request-ID"]
