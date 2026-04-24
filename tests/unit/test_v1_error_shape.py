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


def test_healthz_shape_unchanged() -> None:
    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
