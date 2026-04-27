from fastapi.testclient import TestClient

from slaif_gateway.main import app


client = TestClient(app)


def test_healthz() -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readyz() -> None:
    response = client.get("/readyz")
    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"
    assert response.json()["database"] == "not_configured"


def test_v1_models_requires_authentication() -> None:
    response = client.get("/v1/models")
    assert response.status_code == 401

    body = response.json()
    assert "error" in body
    assert set(body["error"].keys()) == {"message", "type", "param", "code"}
    assert body["error"]["type"] == "authentication_error"
