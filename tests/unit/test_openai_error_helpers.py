import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from slaif_gateway.api.errors import (
    OpenAICompatibleError,
    openai_compatible_error_handler,
    openai_error_response,
)


def test_openai_error_response_shape() -> None:
    response = openai_error_response(
        message="bad request",
        status_code=400,
        code="bad_request",
        param=None,
    )

    assert response.status_code == 400
    assert response.body is not None

    parsed = json.loads(response.body)
    assert "error" in parsed
    assert parsed["error"]["message"] == "bad request"
    assert parsed["error"]["type"] == "invalid_request_error"
    assert parsed["error"]["param"] is None
    assert parsed["error"]["code"] == "bad_request"


def test_openai_compatible_error_handler_shape() -> None:
    app = FastAPI()
    app.add_exception_handler(OpenAICompatibleError, openai_compatible_error_handler)

    @app.get("/v1/boom")
    def boom() -> None:
        raise OpenAICompatibleError("failed", status_code=401, code="auth_failed")

    client = TestClient(app)
    response = client.get("/v1/boom")

    assert response.status_code == 401
    body = response.json()
    assert body["error"]["message"] == "failed"
    assert body["error"]["type"] == "authentication_error"
    assert body["error"]["param"] is None
    assert body["error"]["code"] == "auth_failed"
