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


def test_unimplemented_responses_rc2_routes_keep_openai_404_error_shape() -> None:
    for method, path, expected_status in (
        ("get", "/v1/responses", 405),
        ("post", "/v1/responses/resp_123/cancel", 404),
        ("post", "/v1/files", 404),
    ):
        response = getattr(client, method)(path)

        assert response.status_code == expected_status
        body = response.json()
        assert "error" in body
        assert set(body["error"].keys()) == {"message", "type", "param", "code"}
        assert body["error"]["type"] == "invalid_request_error"


def test_healthz_shape_unchanged() -> None:
    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
