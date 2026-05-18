from __future__ import annotations

import uuid
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
from fastapi.testclient import TestClient

from slaif_gateway.api.dependencies import get_authenticated_gateway_key
from slaif_gateway.config import Settings
from slaif_gateway.main import create_app
from slaif_gateway.metrics import prometheus_response_body
from slaif_gateway.schemas.accounting import FinalizedAccountingResult
from slaif_gateway.schemas.auth import AuthenticatedGatewayKey
from slaif_gateway.schemas.pricing import ChatCostEstimate
from slaif_gateway.schemas.quota import QuotaReservationResult
from slaif_gateway.schemas.routing import RouteResolutionResult
from slaif_gateway.services.key_modes import (
    CAPABILITY_POLICY_MODE_TRUSTED_CALIBRATION_DISCOVERY,
    KEY_PURPOSE_TRUSTED_CALIBRATION,
)
from slaif_gateway.services.chat_completion_route_capabilities import default_chat_completion_capabilities


class FakeSession:
    def __init__(self) -> None:
        self.commit_calls = 0

    async def commit(self) -> None:
        self.commit_calls += 1


def _auth(
    *,
    key_purpose: str = "standard",
    capability_policy_mode: str = "standard",
) -> AuthenticatedGatewayKey:
    now = datetime.now(UTC)
    return AuthenticatedGatewayKey(
        gateway_key_id=uuid.uuid4(),
        owner_id=uuid.uuid4(),
        cohort_id=None,
        public_key_id="public1234abcd",
        status="active",
        valid_from=now - timedelta(minutes=5),
        valid_until=now + timedelta(minutes=30),
        allow_all_models=True,
        allowed_models=(),
        allow_all_endpoints=True,
        allowed_endpoints=(),
        allowed_providers=None,
        cost_limit_eur=None,
        token_limit_total=None,
        request_limit_total=None,
        rate_limit_policy={},
        key_purpose=key_purpose,
        capability_policy_mode=capability_policy_mode,
    )


def _route(
    provider: str = "openai",
    resolved_model: str = "gpt-4.1-mini",
    *,
    provider_base_url: str | None = None,
    provider_api_key_env_var: str | None = None,
    capabilities: dict[str, object] | None = None,
) -> RouteResolutionResult:
    return RouteResolutionResult(
        requested_model="classroom-cheap",
        resolved_model=resolved_model,
        provider=provider,
        route_id=uuid.uuid4(),
        route_match_type="exact",
        route_pattern="classroom-cheap",
        priority=100,
        provider_base_url=provider_base_url,
        provider_api_key_env_var=provider_api_key_env_var,
        capabilities=capabilities,
    )


def _estimate(provider: str = "openai", resolved_model: str = "gpt-4.1-mini") -> ChatCostEstimate:
    return ChatCostEstimate(
        provider=provider,
        requested_model="classroom-cheap",
        resolved_model=resolved_model,
        native_currency="EUR",
        estimated_input_tokens=50,
        estimated_output_tokens=20,
        estimated_input_cost_native=Decimal("0.001"),
        estimated_output_cost_native=Decimal("0.002"),
        estimated_total_cost_native=Decimal("0.003"),
        estimated_total_cost_eur=Decimal("0.003"),
        pricing_rule_id=None,
        fx_rate_id=None,
    )


def _chat_request() -> dict[str, object]:
    return {
        "model": "classroom-cheap",
        "messages": [{"role": "user", "content": "hello"}],
        "max_tokens": 20,
    }


def _image_chat_request(url: str = "https://example.test/image.png") -> dict[str, object]:
    return {
        "model": "classroom-cheap",
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "describe"},
                    {"type": "image_url", "image_url": {"url": url, "detail": "low"}},
                ],
            }
        ],
        "max_tokens": 20,
    }


def _file_chat_request(
    file_data: str = "SGVsbG8sIGZpbGU=",
    filename: str = "notes.txt",
) -> dict[str, object]:
    return {
        "model": "classroom-cheap",
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "summarize"},
                    {"type": "file", "file": {"filename": filename, "file_data": file_data}},
                ],
            }
        ],
        "max_tokens": 20,
    }


def _audio_chat_request(
    audio_data: str = "UklGRiQAAABXQVZFZm10IBAAAAABAAEA",
    audio_format: str = "wav",
) -> dict[str, object]:
    return {
        "model": "classroom-cheap",
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "transcribe"},
                    {
                        "type": "input_audio",
                        "input_audio": {"data": audio_data, "format": audio_format},
                    },
                ],
            }
        ],
        "max_tokens": 20,
    }


def _chat_capabilities(**overrides: bool) -> dict[str, object]:
    capabilities = default_chat_completion_capabilities()
    capabilities.update(overrides)
    return {"chat_completions": capabilities}


def _wire_pipeline(
    monkeypatch,
    app,
    *,
    provider: str = "openai",
    resolved_model: str = "gpt-4.1-mini",
    provider_base_url: str | None = None,
    provider_api_key_env_var: str | None = None,
    authenticated_key: AuthenticatedGatewayKey | None = None,
    expected_requested_model: str = "classroom-cheap",
    route_capabilities: dict[str, object] | None = None,
) -> dict[str, object]:
    from slaif_gateway.api import dependencies as dependencies_module
    import slaif_gateway.services.chat_completion_gateway as main_module

    state: dict[str, object] = {
        "session": FakeSession(),
        "reserve_calls": [],
        "finalize_calls": [],
        "provider_responses": [],
    }
    auth = authenticated_key or _auth()
    route_result = _route(
        provider=provider,
        resolved_model=resolved_model,
        provider_base_url=provider_base_url,
        provider_api_key_env_var=provider_api_key_env_var,
        capabilities=route_capabilities,
    )
    estimate = _estimate(provider=provider, resolved_model=resolved_model)

    async def _fake_auth_dependency() -> AuthenticatedGatewayKey:
        return auth

    async def _dummy_db_session():
        yield state["session"]

    async def _fake_resolve_model(self, requested_model, authenticated_key):
        _ = (self, authenticated_key)
        assert requested_model == expected_requested_model
        return route_result

    async def _fake_estimate_chat_completion_cost(self, *, route, policy, endpoint="chat.completions", at=None):
        _ = (self, route, policy, endpoint, at)
        return estimate

    async def _fake_reserve(self, *, authenticated_key, route, policy, cost_estimate, request_id, now=None):
        _ = (self, authenticated_key, policy, cost_estimate, now)
        state["reserve_calls"].append((route.provider, request_id))
        return QuotaReservationResult(
            reservation_id=uuid.uuid4(),
            gateway_key_id=auth.gateway_key_id,
            request_id=request_id,
            reserved_cost_eur=Decimal("0.003"),
            reserved_tokens=70,
            status="pending",
            expires_at=datetime.now(UTC) + timedelta(minutes=15),
        )

    async def _fake_finalize_successful_response(
        self,
        reservation_id,
        authenticated_key,
        route,
        policy,
        pricing_estimate,
        provider_response,
        request_id,
        endpoint="chat.completions",
        started_at=None,
        finished_at=None,
    ):
        _ = (
            self,
            reservation_id,
            authenticated_key,
            route,
            policy,
            pricing_estimate,
            endpoint,
            started_at,
            finished_at,
        )
        state["finalize_calls"].append(request_id)
        state["provider_responses"].append(provider_response)
        return FinalizedAccountingResult(
            usage_ledger_id=uuid.uuid4(),
            reservation_id=reservation_id,
            gateway_key_id=authenticated_key.gateway_key_id,
            request_id=request_id,
            estimated_cost_eur=pricing_estimate.estimated_total_cost_eur,
            actual_cost_eur=Decimal("0.001234000"),
            actual_cost_native=Decimal("0.001234000"),
            native_currency=pricing_estimate.native_currency,
            prompt_tokens=5,
            completion_tokens=7,
            total_tokens=12,
            accounting_status="finalized",
        )

    app.dependency_overrides[get_authenticated_gateway_key] = _fake_auth_dependency
    monkeypatch.setattr(dependencies_module, "_get_db_session_after_auth_header_check", _dummy_db_session)
    monkeypatch.setattr(main_module, "_get_db_session_after_auth_header_check", _dummy_db_session)
    monkeypatch.setattr(main_module.RouteResolutionService, "resolve_model", _fake_resolve_model)
    monkeypatch.setattr(
        main_module.PricingService,
        "estimate_chat_completion_cost",
        _fake_estimate_chat_completion_cost,
    )
    monkeypatch.setattr(main_module.QuotaService, "reserve_for_chat_completion", _fake_reserve)
    monkeypatch.setattr(
        main_module.AccountingService,
        "finalize_successful_response",
        _fake_finalize_successful_response,
    )
    return state


def test_openai_nonstreaming_happy_path_uses_adapter_and_finalizes(
    monkeypatch,
    respx_mock,
) -> None:
    settings = Settings(OPENAI_UPSTREAM_API_KEY="openai-upstream-key")
    app = create_app(settings)
    state = _wire_pipeline(monkeypatch, app, provider="openai", resolved_model="gpt-4.1-mini")
    route = respx_mock.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "chatcmpl_openai",
                "object": "chat.completion",
                "model": "gpt-4.1-mini",
                "choices": [],
                "usage": {"prompt_tokens": 5, "completion_tokens": 7, "total_tokens": 12},
            },
            headers={"x-request-id": "upstream-openai"},
        )
    )

    response = TestClient(app).post(
        "/v1/chat/completions",
        json=_chat_request(),
        headers={"Authorization": "Bearer client-gateway-key"},
    )

    assert response.status_code == 200
    assert response.json()["id"] == "chatcmpl_openai"
    assert state["reserve_calls"]
    assert state["finalize_calls"]
    assert route.called
    upstream_request = route.calls[0].request
    assert upstream_request.headers["authorization"] == "Bearer openai-upstream-key"
    assert upstream_request.headers["authorization"] != "Bearer client-gateway-key"
    upstream_body = json.loads(upstream_request.content)
    assert upstream_body["model"] == "gpt-4.1-mini"
    assert upstream_body["max_tokens"] == 20
    assert state["provider_responses"][0].usage.total_tokens == 12
    assert state["session"].commit_calls == 2
    metrics = prometheus_response_body().decode()
    assert 'gateway_cost_eur_total{model="gpt-4.1-mini",provider="openai"}' in metrics


def test_nonstreaming_request_preserves_openai_sdk_fields_to_upstream(
    monkeypatch,
    respx_mock,
) -> None:
    settings = Settings(OPENAI_UPSTREAM_API_KEY="openai-upstream-key")
    app = create_app(settings)
    _wire_pipeline(monkeypatch, app, provider="openai", resolved_model="gpt-4.1-mini")
    route = respx_mock.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "chatcmpl_openai",
                "object": "chat.completion",
                "model": "gpt-4.1-mini",
                "choices": [],
                "usage": {"prompt_tokens": 5, "completion_tokens": 7, "total_tokens": 12},
            },
        )
    )
    body = {
        **_chat_request(),
        "temperature": 0.2,
        "top_p": 0.9,
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "delete_file",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "authorization": {"type": "string"},
                            "path": {"type": "string"},
                        },
                    },
                },
            }
        ],
        "tool_choice": {"type": "function", "function": {"name": "delete_file"}},
        "response_format": {"type": "json_object"},
        "seed": 123,
        "user": "student-1",
        "logit_bias": {"123": -1},
        "logprobs": True,
        "top_logprobs": 2,
        "presence_penalty": 0.1,
        "frequency_penalty": 0.2,
        "n": 1,
        "stream_options": {"include_usage": False},
        "reasoning_effort": "low",
        "modalities": ["text"],
        "parallel_tool_calls": True,
        "metadata": {"course": "week-1"},
        "store": False,
        "prediction": {"type": "content", "content": "hello"},
        "service_tier": "auto",
    }

    response = TestClient(app).post(
        "/v1/chat/completions",
        json=body,
        headers={"Authorization": "Bearer client-gateway-key"},
    )

    assert response.status_code == 200
    upstream_body = json.loads(route.calls[0].request.content)
    assert upstream_body["model"] == "gpt-4.1-mini"
    for key, value in body.items():
        if key == "model":
            continue
        assert upstream_body[key] == value


def test_openrouter_route_uses_openrouter_adapter_path(monkeypatch, respx_mock) -> None:
    settings = Settings(OPENROUTER_API_KEY="openrouter-upstream-key")
    app = create_app(settings)
    state = _wire_pipeline(
        monkeypatch,
        app,
        provider="openrouter",
        resolved_model="openai/gpt-4.1-mini",
    )
    route = respx_mock.post("https://openrouter.ai/api/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "or_chatcmpl",
                "choices": [],
                "usage": {"prompt_tokens": 3, "completion_tokens": 4, "total_tokens": 7},
            },
        )
    )

    response = TestClient(app).post("/v1/chat/completions", json=_chat_request())

    assert response.status_code == 200
    assert response.json()["id"] == "or_chatcmpl"
    assert route.called
    upstream_request = route.calls[0].request
    assert upstream_request.headers["authorization"] == "Bearer openrouter-upstream-key"
    upstream_body = json.loads(upstream_request.content)
    assert upstream_body["model"] == "openai/gpt-4.1-mini"
    assert state["finalize_calls"]


def test_openai_nonstreaming_multiple_choices_are_forwarded_and_preserved(
    monkeypatch,
    respx_mock,
) -> None:
    settings = Settings(OPENAI_UPSTREAM_API_KEY="openai-upstream-key")
    app = create_app(settings)
    state = _wire_pipeline(
        monkeypatch,
        app,
        provider="openai",
        resolved_model="gpt-4.1-mini",
        route_capabilities=_chat_capabilities(chat_multiple_choices=True),
    )
    upstream_payload = {
        "id": "chatcmpl_multi",
        "object": "chat.completion",
        "model": "gpt-4.1-mini",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "first"},
                "finish_reason": "stop",
                "logprobs": {"content": [{"token": "first", "logprob": -0.1, "bytes": [102]}]},
            },
            {
                "index": 1,
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {"name": "lookup", "arguments": "{}"},
                        }
                    ],
                },
                "finish_reason": "tool_calls",
                "logprobs": None,
            },
        ],
        "usage": {"prompt_tokens": 5, "completion_tokens": 17, "total_tokens": 22},
    }
    route = respx_mock.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=upstream_payload)
    )

    body = {
        **_chat_request(),
        "n": 2,
        "tools": [{"type": "function", "function": {"name": "lookup"}}],
    }
    response = TestClient(app).post(
        "/v1/chat/completions",
        json=body,
        headers={"Authorization": "Bearer client-gateway-key"},
    )

    assert response.status_code == 200
    assert response.json() == upstream_payload
    upstream_request = route.calls[0].request
    upstream_body = json.loads(upstream_request.content)
    assert upstream_body["n"] == 2
    assert upstream_body["tools"] == body["tools"]
    assert response.json()["choices"][0]["index"] == 0
    assert response.json()["choices"][1]["index"] == 1
    assert response.json()["choices"][0]["finish_reason"] == "stop"
    assert response.json()["choices"][1]["finish_reason"] == "tool_calls"
    assert state["provider_responses"][0].usage.completion_tokens == 17
    assert state["provider_responses"][0].usage.total_tokens == 22
    assert state["finalize_calls"]


def test_openrouter_nonstreaming_multiple_choices_preserves_provider_reported_cost(
    monkeypatch,
    respx_mock,
) -> None:
    settings = Settings(OPENROUTER_API_KEY="openrouter-upstream-key")
    app = create_app(settings)
    state = _wire_pipeline(
        monkeypatch,
        app,
        provider="openrouter",
        resolved_model="openai/gpt-4.1-mini",
        route_capabilities=_chat_capabilities(chat_multiple_choices=True),
    )
    upstream_payload = {
        "id": "or_chatcmpl_multi",
        "choices": [
            {"index": 0, "message": {"role": "assistant", "content": "first"}, "finish_reason": "stop"},
            {"index": 1, "message": {"role": "assistant", "content": "second"}, "finish_reason": "length"},
        ],
        "usage": {
            "prompt_tokens": 3,
            "completion_tokens": 9,
            "total_tokens": 12,
            "cost_usd": "0.0012",
        },
    }
    route = respx_mock.post("https://openrouter.ai/api/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=upstream_payload)
    )

    response = TestClient(app).post(
        "/v1/chat/completions",
        json={**_chat_request(), "n": 2},
    )

    assert response.status_code == 200
    assert response.json()["choices"][1]["finish_reason"] == "length"
    upstream_body = json.loads(route.calls[0].request.content)
    assert upstream_body["n"] == 2
    provider_response = state["provider_responses"][0]
    assert provider_response.usage.completion_tokens == 9
    assert provider_response.raw_cost_native == Decimal("0.0012")


def test_openai_nonstreaming_image_request_is_forwarded_and_finalized_once(
    monkeypatch,
    respx_mock,
) -> None:
    settings = Settings(OPENAI_UPSTREAM_API_KEY="openai-upstream-key")
    app = create_app(settings)
    state = _wire_pipeline(
        monkeypatch,
        app,
        provider="openai",
        resolved_model="gpt-4.1-mini",
        route_capabilities=_chat_capabilities(
            chat_image_inputs=True,
            chat_multiple_choices=True,
            chat_function_tools=True,
        ),
    )
    upstream_payload = {
        "id": "chatcmpl_image",
        "object": "chat.completion",
        "model": "gpt-4.1-mini",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "image answer"},
                "finish_reason": "stop",
            },
            {
                "index": 1,
                "message": {"role": "assistant", "content": "second image answer"},
                "finish_reason": "stop",
            },
        ],
        "usage": {"prompt_tokens": 111, "completion_tokens": 17, "total_tokens": 128},
    }
    route = respx_mock.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=upstream_payload)
    )

    body = {
        **_image_chat_request("https://example.test/private.png?token=upstream-only"),
        "n": 2,
        "tools": [{"type": "function", "function": {"name": "lookup"}}],
    }
    response = TestClient(app).post(
        "/v1/chat/completions",
        json=body,
        headers={"Authorization": "Bearer client-gateway-key"},
    )

    assert response.status_code == 200
    assert response.json() == upstream_payload
    upstream_request = route.calls[0].request
    assert upstream_request.headers["authorization"] == "Bearer openai-upstream-key"
    assert upstream_request.headers["authorization"] != "Bearer client-gateway-key"
    upstream_body = json.loads(upstream_request.content)
    assert upstream_body["messages"] == body["messages"]
    assert upstream_body["n"] == 2
    assert upstream_body["tools"] == body["tools"]
    assert state["provider_responses"][0].usage.prompt_tokens == 111
    assert state["provider_responses"][0].usage.completion_tokens == 17
    assert state["finalize_calls"] and len(state["finalize_calls"]) == 1


def test_openrouter_nonstreaming_image_request_preserves_provider_reported_cost(
    monkeypatch,
    respx_mock,
) -> None:
    settings = Settings(OPENROUTER_API_KEY="openrouter-upstream-key")
    app = create_app(settings)
    chat_capabilities = default_chat_completion_capabilities()
    chat_capabilities["chat_image_inputs"] = True
    chat_capabilities["chat_custom_tools"] = True
    state = _wire_pipeline(
        monkeypatch,
        app,
        provider="openrouter",
        resolved_model="openai/gpt-4.1-mini",
        route_capabilities={"chat_completions": chat_capabilities},
    )
    upstream_payload = {
        "id": "or_chatcmpl_image",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "image answer"},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 44,
            "completion_tokens": 8,
            "total_tokens": 52,
            "cost_usd": "0.0042",
        },
    }
    route = respx_mock.post("https://openrouter.ai/api/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=upstream_payload)
    )

    body = {
        **_image_chat_request("data:image/png;base64,aGVsbG8="),
        "tools": [{"type": "custom", "custom": {"name": "local_image_tool"}}],
    }
    response = TestClient(app).post("/v1/chat/completions", json=body)

    assert response.status_code == 200
    upstream_request = route.calls[0].request
    assert upstream_request.headers["authorization"] == "Bearer openrouter-upstream-key"
    upstream_body = json.loads(upstream_request.content)
    assert upstream_body["messages"] == body["messages"]
    assert upstream_body["tools"] == body["tools"]
    provider_response = state["provider_responses"][0]
    assert provider_response.usage.prompt_tokens == 44
    assert provider_response.raw_cost_native == Decimal("0.0042")


def test_openai_nonstreaming_file_request_is_forwarded_and_finalized_once(
    monkeypatch,
    respx_mock,
) -> None:
    settings = Settings(OPENAI_UPSTREAM_API_KEY="openai-upstream-key")
    app = create_app(settings)
    state = _wire_pipeline(
        monkeypatch,
        app,
        provider="openai",
        resolved_model="gpt-4.1-mini",
        route_capabilities=_chat_capabilities(
            chat_file_inputs=True,
            chat_multiple_choices=True,
            chat_function_tools=True,
        ),
    )
    upstream_payload = {
        "id": "chatcmpl_file",
        "object": "chat.completion",
        "model": "gpt-4.1-mini",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "file answer"},
                "finish_reason": "stop",
            },
            {
                "index": 1,
                "message": {"role": "assistant", "content": "second file answer"},
                "finish_reason": "stop",
            },
        ],
        "usage": {"prompt_tokens": 121, "completion_tokens": 19, "total_tokens": 140},
    }
    route = respx_mock.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=upstream_payload)
    )

    body = {
        **_file_chat_request("cHJpdmF0ZSBmaWxlIHBheWxvYWQ=", "private-notes.txt"),
        "n": 2,
        "tools": [{"type": "function", "function": {"name": "lookup"}}],
    }
    response = TestClient(app).post(
        "/v1/chat/completions",
        json=body,
        headers={"Authorization": "Bearer client-gateway-key"},
    )

    assert response.status_code == 200
    assert response.json() == upstream_payload
    upstream_request = route.calls[0].request
    assert upstream_request.headers["authorization"] == "Bearer openai-upstream-key"
    assert upstream_request.headers["authorization"] != "Bearer client-gateway-key"
    upstream_body = json.loads(upstream_request.content)
    assert upstream_body["messages"] == body["messages"]
    assert upstream_body["n"] == 2
    assert upstream_body["tools"] == body["tools"]
    assert state["provider_responses"][0].usage.prompt_tokens == 121
    assert state["provider_responses"][0].usage.completion_tokens == 19
    assert state["finalize_calls"] and len(state["finalize_calls"]) == 1


def test_openrouter_nonstreaming_file_request_preserves_provider_reported_cost(
    monkeypatch,
    respx_mock,
) -> None:
    settings = Settings(
        OPENROUTER_API_KEY="openrouter-upstream-key",
        CHAT_ALLOW_FILE_DATA_URLS=True,
    )
    app = create_app(settings)
    chat_capabilities = default_chat_completion_capabilities()
    chat_capabilities["chat_file_inputs"] = True
    chat_capabilities["chat_image_inputs"] = True
    chat_capabilities["chat_custom_tools"] = True
    state = _wire_pipeline(
        monkeypatch,
        app,
        provider="openrouter",
        resolved_model="openai/gpt-4.1-mini",
        route_capabilities={"chat_completions": chat_capabilities},
    )
    upstream_payload = {
        "id": "or_chatcmpl_file",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "file answer"},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 54,
            "completion_tokens": 9,
            "total_tokens": 63,
            "cost_usd": "0.0052",
        },
    }
    route = respx_mock.post("https://openrouter.ai/api/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=upstream_payload)
    )

    file_data = "data:application/pdf;base64,SGVsbG8="
    body = {
        **_file_chat_request(file_data, "notes.pdf"),
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "summarize"},
                    {
                        "type": "image_url",
                        "image_url": {"url": "https://example.test/chart.png"},
                    },
                    {"type": "file", "file": {"filename": "notes.pdf", "file_data": file_data}},
                ],
            }
        ],
        "tools": [{"type": "custom", "custom": {"name": "local_file_tool"}}],
    }
    response = TestClient(app).post("/v1/chat/completions", json=body)

    assert response.status_code == 200
    upstream_request = route.calls[0].request
    assert upstream_request.headers["authorization"] == "Bearer openrouter-upstream-key"
    upstream_body = json.loads(upstream_request.content)
    assert upstream_body["messages"] == body["messages"]
    assert upstream_body["tools"] == body["tools"]
    provider_response = state["provider_responses"][0]
    assert provider_response.usage.prompt_tokens == 54
    assert provider_response.raw_cost_native == Decimal("0.0052")


def test_openai_nonstreaming_audio_input_request_is_forwarded_and_finalized_once(
    monkeypatch,
    respx_mock,
) -> None:
    settings = Settings(OPENAI_UPSTREAM_API_KEY="openai-upstream-key")
    app = create_app(settings)
    state = _wire_pipeline(
        monkeypatch,
        app,
        provider="openai",
        resolved_model="gpt-4.1-mini",
        route_capabilities=_chat_capabilities(
            chat_audio_inputs=True,
            chat_multiple_choices=True,
            chat_function_tools=True,
        ),
    )
    upstream_payload = {
        "id": "chatcmpl_audio",
        "object": "chat.completion",
        "model": "gpt-4.1-mini",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "audio answer"},
                "finish_reason": "stop",
            },
            {
                "index": 1,
                "message": {"role": "assistant", "content": "second audio answer"},
                "finish_reason": "stop",
            },
        ],
        "usage": {
            "prompt_tokens": 131,
            "completion_tokens": 19,
            "total_tokens": 150,
            "prompt_tokens_details": {"audio_tokens": 42},
        },
    }
    route = respx_mock.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=upstream_payload)
    )

    body = {
        **_audio_chat_request("cHJpdmF0ZSBhdWRpbyBwYXlsb2Fk", "wav"),
        "n": 2,
        "tools": [{"type": "function", "function": {"name": "lookup"}}],
    }
    response = TestClient(app).post(
        "/v1/chat/completions",
        json=body,
        headers={"Authorization": "Bearer client-gateway-key"},
    )

    assert response.status_code == 200
    assert response.json() == upstream_payload
    upstream_request = route.calls[0].request
    assert upstream_request.headers["authorization"] == "Bearer openai-upstream-key"
    assert upstream_request.headers["authorization"] != "Bearer client-gateway-key"
    upstream_body = json.loads(upstream_request.content)
    assert upstream_body["messages"] == body["messages"]
    assert upstream_body["n"] == 2
    assert upstream_body["tools"] == body["tools"]
    provider_response = state["provider_responses"][0]
    assert provider_response.usage.prompt_tokens == 131
    assert provider_response.usage.completion_tokens == 19
    assert provider_response.usage.other_usage["prompt_tokens_details"] == {"audio_tokens": 42}
    assert state["finalize_calls"] and len(state["finalize_calls"]) == 1


def test_openrouter_nonstreaming_audio_input_request_preserves_provider_reported_cost(
    monkeypatch,
    respx_mock,
) -> None:
    settings = Settings(OPENROUTER_API_KEY="openrouter-upstream-key")
    app = create_app(settings)
    chat_capabilities = default_chat_completion_capabilities()
    chat_capabilities["chat_audio_inputs"] = True
    chat_capabilities["chat_image_inputs"] = True
    chat_capabilities["chat_file_inputs"] = True
    chat_capabilities["chat_custom_tools"] = True
    state = _wire_pipeline(
        monkeypatch,
        app,
        provider="openrouter",
        resolved_model="openai/gpt-4.1-mini",
        route_capabilities={"chat_completions": chat_capabilities},
    )
    upstream_payload = {
        "id": "or_chatcmpl_audio",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "audio answer"},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 64,
            "completion_tokens": 9,
            "total_tokens": 73,
            "cost_usd": "0.0062",
            "prompt_tokens_details": {"audio_tokens": 22},
        },
    }
    route = respx_mock.post("https://openrouter.ai/api/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=upstream_payload)
    )

    body = {
        **_audio_chat_request("cHJpdmF0ZSBvcGVucm91dGVyIGF1ZGlv", "mp3"),
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "analyze"},
                    {
                        "type": "image_url",
                        "image_url": {"url": "https://example.test/chart.png"},
                    },
                    {"type": "file", "file": {"filename": "notes.txt", "file_data": "SGVsbG8="}},
                    {
                        "type": "input_audio",
                        "input_audio": {
                            "data": "cHJpdmF0ZSBvcGVucm91dGVyIGF1ZGlv",
                            "format": "mp3",
                        },
                    },
                ],
            }
        ],
        "tools": [{"type": "custom", "custom": {"name": "local_audio_tool"}}],
    }
    response = TestClient(app).post("/v1/chat/completions", json=body)

    assert response.status_code == 200
    upstream_request = route.calls[0].request
    assert upstream_request.headers["authorization"] == "Bearer openrouter-upstream-key"
    upstream_body = json.loads(upstream_request.content)
    assert upstream_body["messages"] == body["messages"]
    assert upstream_body["tools"] == body["tools"]
    provider_response = state["provider_responses"][0]
    assert provider_response.usage.prompt_tokens == 64
    assert provider_response.usage.other_usage["prompt_tokens_details"] == {"audio_tokens": 22}
    assert provider_response.raw_cost_native == Decimal("0.0062")


def test_openai_nonstreaming_custom_tool_request_and_response_are_preserved(
    monkeypatch,
    respx_mock,
) -> None:
    settings = Settings(OPENAI_UPSTREAM_API_KEY="openai-upstream-key")
    app = create_app(settings)
    chat_capabilities = default_chat_completion_capabilities()
    chat_capabilities["chat_custom_tools"] = True
    chat_capabilities["chat_multiple_choices"] = True
    state = _wire_pipeline(
        monkeypatch,
        app,
        provider="openai",
        resolved_model="gpt-4.1-mini",
        route_capabilities={"chat_completions": chat_capabilities},
    )
    upstream_payload = {
        "id": "chatcmpl_custom",
        "object": "chat.completion",
        "model": "gpt-4.1-mini",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_custom_1",
                            "type": "custom",
                            "custom": {"name": "run_shell", "input": "echo hello"},
                        }
                    ],
                },
                "finish_reason": "tool_calls",
            },
            {
                "index": 1,
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_custom_2",
                            "type": "custom",
                            "custom": {"name": "run_shell", "input": "echo bye"},
                        }
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ],
        "usage": {"prompt_tokens": 9, "completion_tokens": 4, "total_tokens": 13},
    }
    route = respx_mock.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=upstream_payload)
    )

    body = {
        **_chat_request(),
        "n": 2,
        "tools": [
            {
                "type": "custom",
                "custom": {
                    "name": "run_shell",
                    "description": "local command intent",
                    "format": {
                        "type": "grammar",
                        "grammar": {"syntax": "regex", "definition": "[a-z ]+"},
                    },
                },
            }
        ],
        "tool_choice": {"type": "custom", "custom": {"name": "run_shell"}},
    }
    response = TestClient(app).post(
        "/v1/chat/completions",
        json=body,
        headers={"Authorization": "Bearer client-gateway-key"},
    )

    assert response.status_code == 200
    assert response.json() == upstream_payload
    upstream_request = route.calls[0].request
    assert upstream_request.headers["authorization"] == "Bearer openai-upstream-key"
    assert upstream_request.headers["authorization"] != "Bearer client-gateway-key"
    upstream_body = json.loads(upstream_request.content)
    assert upstream_body["tools"] == body["tools"]
    assert upstream_body["tool_choice"] == body["tool_choice"]
    assert upstream_body["n"] == 2
    assert response.json()["choices"][1]["message"]["tool_calls"][0]["type"] == "custom"
    assert state["provider_responses"][0].usage.total_tokens == 13
    assert state["finalize_calls"]


def test_openrouter_nonstreaming_custom_tool_request_is_preserved(
    monkeypatch,
    respx_mock,
) -> None:
    settings = Settings(OPENROUTER_API_KEY="openrouter-upstream-key")
    app = create_app(settings)
    chat_capabilities = default_chat_completion_capabilities()
    chat_capabilities["chat_custom_tools"] = True
    _wire_pipeline(
        monkeypatch,
        app,
        provider="openrouter",
        resolved_model="openai/gpt-4.1-mini",
        route_capabilities={"chat_completions": chat_capabilities},
    )
    route = respx_mock.post("https://openrouter.ai/api/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "or_chatcmpl_custom",
                "choices": [],
                "usage": {"prompt_tokens": 3, "completion_tokens": 4, "total_tokens": 7},
                "usage_cost": 0.00001,
            },
        )
    )

    body = {
        **_chat_request(),
        "tools": [{"type": "custom", "custom": {"name": "local_router_tool"}}],
    }
    response = TestClient(app).post("/v1/chat/completions", json=body)

    assert response.status_code == 200
    assert response.json()["id"] == "or_chatcmpl_custom"
    upstream_request = route.calls[0].request
    assert upstream_request.headers["authorization"] == "Bearer openrouter-upstream-key"
    upstream_body = json.loads(upstream_request.content)
    assert upstream_body["tools"] == body["tools"]


def test_trusted_calibration_hosted_tool_request_is_forwarded(monkeypatch, respx_mock) -> None:
    settings = Settings(OPENAI_UPSTREAM_API_KEY="openai-upstream-key")
    app = create_app(settings)
    chat_capabilities = default_chat_completion_capabilities()
    chat_capabilities["hosted_web_search"] = True
    _wire_pipeline(
        monkeypatch,
        app,
        provider="openai",
        resolved_model="gpt-5-search-api",
        authenticated_key=_auth(
            key_purpose=KEY_PURPOSE_TRUSTED_CALIBRATION,
            capability_policy_mode=CAPABILITY_POLICY_MODE_TRUSTED_CALIBRATION_DISCOVERY,
        ),
        expected_requested_model="gpt-5-search-api",
        route_capabilities={"chat_completions": chat_capabilities},
    )
    route = respx_mock.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "chatcmpl_search",
                "object": "chat.completion",
                "model": "gpt-5-search-api",
                "choices": [],
                "usage": {"prompt_tokens": 5, "completion_tokens": 7, "total_tokens": 12},
            },
        )
    )

    response = TestClient(app).post(
        "/v1/chat/completions",
        json={
            **_chat_request(),
            "model": "gpt-5-search-api",
            "web_search_options": {"search_context_size": "low"},
            "tools": [{"type": "web_search_preview"}],
        },
        headers={"Authorization": "Bearer client-gateway-key"},
    )

    assert response.status_code == 200
    upstream_body = json.loads(route.calls[0].request.content)
    assert upstream_body["web_search_options"] == {"search_context_size": "low"}
    assert upstream_body["tools"] == [{"type": "web_search_preview"}]


def test_route_provider_config_controls_adapter_base_url_and_key_env_var(
    monkeypatch,
    respx_mock,
) -> None:
    monkeypatch.setenv("CLASSROOM_OPENAI_KEY", "configured-openai-key")
    app = create_app(Settings(OPENAI_UPSTREAM_API_KEY=None))
    _wire_pipeline(
        monkeypatch,
        app,
        provider="openai",
        resolved_model="gpt-test-mini",
        provider_base_url="https://openai-proxy.example/v1",
        provider_api_key_env_var="CLASSROOM_OPENAI_KEY",
    )
    route = respx_mock.post("https://openai-proxy.example/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "chatcmpl_configured",
                "object": "chat.completion",
                "model": "gpt-test-mini",
                "choices": [],
                "usage": {"prompt_tokens": 5, "completion_tokens": 7, "total_tokens": 12},
            },
        )
    )

    response = TestClient(app).post(
        "/v1/chat/completions",
        json=_chat_request(),
        headers={"Authorization": "Bearer client-gateway-key"},
    )

    assert response.status_code == 200
    assert response.json()["id"] == "chatcmpl_configured"
    assert route.called
    upstream_request = route.calls[0].request
    assert upstream_request.headers["authorization"] == "Bearer configured-openai-key"
    assert upstream_request.headers["authorization"] != "Bearer client-gateway-key"
    assert "client-gateway-key" not in upstream_request.headers["authorization"]
