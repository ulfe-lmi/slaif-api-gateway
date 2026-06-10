from fastapi.testclient import TestClient

from slaif_gateway.main import app


client = TestClient(app)


def test_unknown_v1_route_has_openai_error_shape() -> None:
    response = client.get("/v1/does-not-exist")

    assert response.status_code == 404
    body = response.json()
    assert "error" in body
    assert set(body["error"].keys()) == {"message", "type", "param", "code"}
    assert body["error"]["type"] == "invalid_request_error"


def test_unimplemented_responses_rc2_routes_keep_openai_error_shape() -> None:
    for method, path, expected_status, expected_type in (
        ("get", "/v1/responses", 405, "invalid_request_error"),
        ("post", "/v1/responses/resp_123/cancel", 404, "invalid_request_error"),
        ("post", "/v1/embeddings", 401, "authentication_error"),
        ("post", "/v1/files", 404, "invalid_request_error"),
        ("get", "/v1/files/file_123", 404, "invalid_request_error"),
        ("get", "/v1/files/file_123/content", 404, "invalid_request_error"),
        ("post", "/v1/uploads", 404, "invalid_request_error"),
        ("post", "/v1/uploads/upload_123/parts", 404, "invalid_request_error"),
        ("post", "/v1/audio/speech", 401, "authentication_error"),
        ("post", "/v1/audio/transcriptions", 401, "authentication_error"),
        ("post", "/v1/audio/translations", 401, "authentication_error"),
        ("post", "/v1/audio/voices", 404, "invalid_request_error"),
        ("post", "/v1/images/generations", 404, "invalid_request_error"),
        ("post", "/v1/moderations", 404, "invalid_request_error"),
        ("post", "/v1/vector_stores", 404, "invalid_request_error"),
        ("post", "/v1/batches", 404, "invalid_request_error"),
        ("post", "/v1/completions", 404, "invalid_request_error"),
        ("post", "/v1/realtime/sessions", 404, "invalid_request_error"),
    ):
        response = getattr(client, method)(path)

        assert response.status_code == expected_status
        body = response.json()
        assert "error" in body
        assert set(body["error"].keys()) == {"message", "type", "param", "code"}
        assert body["error"]["type"] == expected_type


def test_healthz_shape_unchanged() -> None:
    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
