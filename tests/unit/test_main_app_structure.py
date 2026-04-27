from __future__ import annotations

import inspect

from fastapi.testclient import TestClient

import slaif_gateway.api.openai_compat as openai_compat_module
import slaif_gateway.main as main_module
import slaif_gateway.services.chat_completion_gateway as chat_gateway_module
from slaif_gateway.main import create_app


def test_health_routes_still_registered() -> None:
    client = TestClient(create_app())

    assert client.get("/healthz").status_code == 200
    assert client.get("/readyz").status_code == 503


def test_v1_routes_still_registered_and_require_auth() -> None:
    client = TestClient(create_app())

    models_response = client.get("/v1/models")
    chat_response = client.post("/v1/chat/completions", json={"model": "gpt-test", "messages": []})

    assert models_response.status_code == 401
    assert chat_response.status_code == 401


def test_main_app_only_wires_app_and_routes() -> None:
    source = inspect.getsource(main_module)

    assert "include_router(health_router)" in source
    assert "include_router(openai_compat_router)" in source
    assert "forward_chat_completion" not in source
    assert "reserve_for_chat_completion" not in source
    assert len(source.splitlines()) < 70


def test_openai_compat_module_exposes_v1_routes() -> None:
    paths = {route.path for route in openai_compat_module.router.routes}

    assert "/v1/models" in paths
    assert "/v1/chat/completions" in paths


def test_chat_completion_gateway_contains_orchestration_logic() -> None:
    source = inspect.getsource(chat_gateway_module)

    assert "reserve_for_chat_completion" in source
    assert "forward_chat_completion" in source
    assert "finalize_successful_response" in source
