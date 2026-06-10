from __future__ import annotations

import json
import uuid
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
from fastapi.testclient import TestClient

from slaif_gateway.api.dependencies import get_authenticated_gateway_key
from slaif_gateway.config import Settings
from slaif_gateway.main import create_app
from slaif_gateway.metrics import prometheus_response_body
from slaif_gateway.schemas.accounting import FinalizedAccountingResult, ProviderFailureAccountingResult
from slaif_gateway.schemas.auth import AuthenticatedGatewayKey
from slaif_gateway.schemas.pricing import ChatCostEstimate
from slaif_gateway.schemas.quota import QuotaReservationResult
from slaif_gateway.schemas.routing import RouteResolutionResult


class FakeSession:
    def __init__(self) -> None:
        self.commit_calls = 0

    async def commit(self) -> None:
        self.commit_calls += 1


def _auth(*, allowed_endpoints: tuple[str, ...] | None = None) -> AuthenticatedGatewayKey:
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
        allow_all_endpoints=allowed_endpoints is None,
        allowed_endpoints=allowed_endpoints or (),
        allowed_providers=None,
        cost_limit_eur=None,
        token_limit_total=None,
        request_limit_total=None,
        rate_limit_policy={},
        key_purpose="standard",
        capability_policy_mode="standard",
    )


def _route(
    *,
    endpoint: str,
    provider: str = "openai",
    resolved_model: str = "tts-1",
    capabilities: dict[str, object] | None = None,
) -> RouteResolutionResult:
    return RouteResolutionResult(
        requested_model="classroom-audio",
        resolved_model=resolved_model,
        provider=provider,
        route_id=uuid.uuid4(),
        route_match_type="exact",
        route_pattern="classroom-audio",
        priority=1,
        provider_base_url=None,
        provider_api_key_env_var=None,
        capabilities=capabilities,
    )


def _estimate(
    *,
    resolved_model: str = "tts-1",
    request_price: Decimal | None = Decimal("0.004000000"),
) -> ChatCostEstimate:
    return ChatCostEstimate(
        provider="openai",
        requested_model="classroom-audio",
        resolved_model=resolved_model,
        native_currency="USD",
        estimated_input_tokens=12,
        estimated_output_tokens=0,
        estimated_input_cost_native=request_price or Decimal("0.000120000"),
        estimated_output_cost_native=Decimal("0"),
        estimated_total_cost_native=request_price or Decimal("0.000120000"),
        estimated_total_cost_eur=Decimal("0.003600000") if request_price else Decimal("0.000108000"),
        pricing_rule_id=None,
        fx_rate_id=None,
        input_price_per_1m=Decimal("10.000000000"),
        output_price_per_1m=Decimal("0"),
        request_price=request_price,
        fx_rate=Decimal("0.9"),
    )


def _audio_capabilities(endpoint: str) -> dict[str, object]:
    key = {
        "/v1/audio/speech": "audio_speech",
        "/v1/audio/transcriptions": "audio_transcriptions",
        "/v1/audio/translations": "audio_translations",
    }[endpoint]
    return {"audio_endpoints": {key: True}}


def _wire_audio_pipeline(
    monkeypatch,
    app,
    *,
    endpoint: str,
    provider: str = "openai",
    request_price: Decimal | None = Decimal("0.004000000"),
    auth: AuthenticatedGatewayKey | None = None,
) -> dict[str, object]:
    from slaif_gateway.api import dependencies as dependencies_module
    import slaif_gateway.services.audio_gateway as audio_module

    state: dict[str, object] = {
        "session": FakeSession(),
        "reserve_calls": [],
        "finalize_calls": [],
        "custom_finalize_calls": [],
        "failure_release_calls": [],
        "provider_responses": [],
    }
    authenticated_key = auth or _auth()
    route_result = _route(
        endpoint=endpoint,
        provider=provider,
        resolved_model="whisper-1" if endpoint != "/v1/audio/speech" else "tts-1",
        capabilities=_audio_capabilities(endpoint),
    )
    estimate = _estimate(
        resolved_model=route_result.resolved_model,
        request_price=request_price,
    )

    async def _fake_auth_dependency() -> AuthenticatedGatewayKey:
        return authenticated_key

    async def _dummy_db_session():
        yield state["session"]

    async def _fake_resolve_model(self, requested_model, authenticated_key, *, endpoint):
        _ = (self, authenticated_key)
        assert requested_model == "classroom-audio"
        assert endpoint in {
            "/v1/audio/speech",
            "/v1/audio/transcriptions",
            "/v1/audio/translations",
        }
        return route_result

    async def _fake_estimate_audio_operation_cost(self, *, route, policy, endpoint, at=None):
        _ = (self, route, policy, endpoint, at)
        return estimate

    async def _fake_reserve(self, *, authenticated_key, route, policy, cost_estimate, request_id, endpoint, now=None):
        _ = (self, authenticated_key, policy, cost_estimate, endpoint, now)
        state["reserve_calls"].append((route.provider, request_id))
        return QuotaReservationResult(
            reservation_id=uuid.uuid4(),
            gateway_key_id=authenticated_key.gateway_key_id,
            request_id=request_id,
            reserved_cost_eur=Decimal("0.003600000"),
            reserved_tokens=12,
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
        **kwargs,
    ):
        _ = (self, authenticated_key, route, policy, pricing_estimate, endpoint, kwargs)
        state["finalize_calls"].append(request_id)
        state["provider_responses"].append(provider_response)
        return FinalizedAccountingResult(
            usage_ledger_id=uuid.uuid4(),
            reservation_id=reservation_id,
            gateway_key_id=authenticated_key.gateway_key_id,
            request_id=request_id,
            estimated_cost_eur=pricing_estimate.estimated_total_cost_eur,
            actual_cost_eur=Decimal("0.001000000"),
            actual_cost_native=Decimal("0.001200000"),
            native_currency=pricing_estimate.native_currency,
            prompt_tokens=5,
            completion_tokens=7,
            total_tokens=12,
            accounting_status="finalized",
        )

    async def _fake_finalize_successful_custom_response(
        self,
        reservation_id,
        authenticated_key,
        route,
        pricing_estimate,
        provider_response,
        request_id,
        **kwargs,
    ):
        _ = (self, authenticated_key, route, pricing_estimate, kwargs)
        state["custom_finalize_calls"].append(request_id)
        state["provider_responses"].append(provider_response)
        return FinalizedAccountingResult(
            usage_ledger_id=uuid.uuid4(),
            reservation_id=reservation_id,
            gateway_key_id=authenticated_key.gateway_key_id,
            request_id=request_id,
            estimated_cost_eur=pricing_estimate.estimated_total_cost_eur,
            actual_cost_eur=pricing_estimate.estimated_total_cost_eur,
            actual_cost_native=pricing_estimate.estimated_total_cost_native,
            native_currency=pricing_estimate.native_currency,
            prompt_tokens=kwargs["usage"].prompt_tokens,
            completion_tokens=kwargs["usage"].completion_tokens,
            total_tokens=kwargs["usage"].total_tokens,
            accounting_status="finalized",
        )

    async def _fake_record_provider_failure_and_release(self, *args, **kwargs):
        _ = (self, args)
        state["failure_release_calls"].append(kwargs.get("error_code"))
        return ProviderFailureAccountingResult(
            usage_ledger_id=uuid.uuid4(),
            reservation_id=args[0],
            gateway_key_id=authenticated_key.gateway_key_id,
            request_id=args[5],
            released=True,
            accounting_status="released",
            error_type=kwargs["error_type"],
            error_code=kwargs.get("error_code"),
        )

    app.dependency_overrides[get_authenticated_gateway_key] = _fake_auth_dependency
    monkeypatch.setattr(dependencies_module, "_get_db_session_after_auth_header_check", _dummy_db_session)
    monkeypatch.setattr(audio_module, "_get_db_session_after_auth_header_check", _dummy_db_session)
    monkeypatch.setattr(audio_module.RouteResolutionService, "resolve_model", _fake_resolve_model)
    monkeypatch.setattr(
        audio_module.PricingService,
        "estimate_audio_operation_cost",
        _fake_estimate_audio_operation_cost,
    )
    monkeypatch.setattr(audio_module.QuotaService, "reserve_for_chat_completion", _fake_reserve)
    monkeypatch.setattr(
        audio_module.AccountingService,
        "finalize_successful_response",
        _fake_finalize_successful_response,
    )
    monkeypatch.setattr(
        audio_module.AccountingService,
        "finalize_successful_custom_response",
        _fake_finalize_successful_custom_response,
    )
    monkeypatch.setattr(
        audio_module.AccountingService,
        "record_provider_failure_and_release",
        _fake_record_provider_failure_and_release,
    )
    return state


def test_chat_permission_does_not_allow_standalone_audio() -> None:
    app = create_app(Settings())

    async def _fake_auth_dependency() -> AuthenticatedGatewayKey:
        return _auth(allowed_endpoints=("/v1/chat/completions",))

    app.dependency_overrides[get_authenticated_gateway_key] = _fake_auth_dependency

    response = TestClient(app).post(
        "/v1/audio/speech",
        json={"model": "tts-1", "input": "hello", "voice": "alloy"},
        headers={"Authorization": "Bearer client-gateway-key"},
    )

    assert response.status_code == 403
    assert response.json()["error"]["type"] == "permission_error"


def test_model_permission_alone_does_not_allow_standalone_audio() -> None:
    app = create_app(Settings())

    async def _fake_auth_dependency() -> AuthenticatedGatewayKey:
        authenticated = _auth(allowed_endpoints=())
        return replace(
            authenticated,
            allow_all_models=False,
            allowed_models=("tts-1",),
        )

    app.dependency_overrides[get_authenticated_gateway_key] = _fake_auth_dependency

    response = TestClient(app).post(
        "/v1/audio/speech",
        json={"model": "tts-1", "input": "hello", "voice": "alloy"},
        headers={"Authorization": "Bearer client-gateway-key"},
    )

    assert response.status_code == 403
    assert response.json()["error"]["type"] == "permission_error"


def test_openai_speech_request_is_forwarded_and_binary_response_is_safe(
    monkeypatch,
    respx_mock,
) -> None:
    settings = Settings(OPENAI_UPSTREAM_API_KEY="openai-upstream-key")
    app = create_app(settings)
    state = _wire_audio_pipeline(monkeypatch, app, endpoint="/v1/audio/speech")
    route = respx_mock.post("https://api.openai.com/v1/audio/speech").mock(
        return_value=httpx.Response(
            200,
            content=b"audio-bytes",
            headers={
                "content-type": "audio/mpeg",
                "content-length": "11",
                "set-cookie": "secret",
                "x-request-id": "upstream-audio",
            },
        )
    )

    response = TestClient(app).post(
        "/v1/audio/speech",
        json={"model": "classroom-audio", "input": "hello", "voice": "alloy"},
        headers={"Authorization": "Bearer client-gateway-key"},
    )

    assert response.status_code == 200
    assert response.content == b"audio-bytes"
    assert response.headers["content-type"].startswith("audio/mpeg")
    assert response.headers["content-length"] == "11"
    assert "set-cookie" not in {name.lower() for name in response.headers}
    assert state["reserve_calls"]
    assert state["custom_finalize_calls"]
    assert route.called
    upstream_request = route.calls[0].request
    assert upstream_request.headers["authorization"] == "Bearer openai-upstream-key"
    assert upstream_request.headers["authorization"] != "Bearer client-gateway-key"
    upstream_body = json.loads(upstream_request.content)
    assert upstream_body == {"model": "tts-1", "input": "hello", "voice": "alloy"}
    metrics = prometheus_response_body().decode()
    assert 'gateway_cost_eur_total{model="tts-1",provider="openai"}' in metrics


def test_openai_transcription_multipart_forwarding_strips_client_headers(
    monkeypatch,
    respx_mock,
) -> None:
    settings = Settings(OPENAI_UPSTREAM_API_KEY="openai-upstream-key")
    app = create_app(settings)
    state = _wire_audio_pipeline(
        monkeypatch,
        app,
        endpoint="/v1/audio/transcriptions",
        request_price=None,
    )
    route = respx_mock.post("https://api.openai.com/v1/audio/transcriptions").mock(
        return_value=httpx.Response(
            200,
            json={
                "text": "hello",
                "usage": {"prompt_tokens": 4, "completion_tokens": 0, "total_tokens": 4},
            },
            headers={"content-type": "application/json"},
        )
    )

    response = TestClient(app).post(
        "/v1/audio/transcriptions",
        data={"model": "classroom-audio", "response_format": "json"},
        files={"file": ("sample.wav", b"audio-bytes", "audio/wav")},
        headers={
            "Authorization": "Bearer client-gateway-key",
            "Cookie": "session=value",
            "X-CSRF-Token": "csrf",
            "X-Admin-Session": "admin",
        },
    )

    assert response.status_code == 200
    assert response.json()["text"] == "hello"
    assert state["finalize_calls"]
    assert route.called
    upstream_request = route.calls[0].request
    header_names = {name.lower() for name in upstream_request.headers}
    assert "authorization" in header_names
    assert upstream_request.headers["authorization"] == "Bearer openai-upstream-key"
    assert "cookie" not in header_names
    assert "x-csrf-token" not in header_names
    assert "x-admin-session" not in header_names
    multipart_text = upstream_request.content.decode("utf-8", errors="ignore")
    assert "sample.wav" in multipart_text
    assert "whisper-1" in multipart_text


def test_openai_translation_text_response_uses_request_priced_fallback_when_usage_missing(
    monkeypatch,
    respx_mock,
) -> None:
    settings = Settings(OPENAI_UPSTREAM_API_KEY="openai-upstream-key")
    app = create_app(settings)
    state = _wire_audio_pipeline(monkeypatch, app, endpoint="/v1/audio/translations")
    route = respx_mock.post("https://api.openai.com/v1/audio/translations").mock(
        return_value=httpx.Response(
            200,
            text="Hello world",
            headers={"content-type": "text/plain; charset=utf-8"},
        )
    )

    response = TestClient(app).post(
        "/v1/audio/translations",
        data={"model": "classroom-audio", "response_format": "text"},
        files={"file": ("sample.mp3", b"audio-bytes", "audio/mpeg")},
        headers={"Authorization": "Bearer client-gateway-key"},
    )

    assert response.status_code == 200
    assert response.text == "Hello world"
    assert state["custom_finalize_calls"]
    assert not state["finalize_calls"]
    assert route.called


def test_openrouter_audio_endpoint_fails_closed(
    monkeypatch,
    respx_mock,
) -> None:
    _ = respx_mock
    settings = Settings(OPENROUTER_API_KEY="openrouter-upstream-key")
    app = create_app(settings)
    state = _wire_audio_pipeline(
        monkeypatch,
        app,
        endpoint="/v1/audio/speech",
        provider="openrouter",
    )

    response = TestClient(app).post(
        "/v1/audio/speech",
        json={"model": "classroom-audio", "input": "hello", "voice": "alloy"},
        headers={"Authorization": "Bearer client-gateway-key"},
    )

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "unsupported_provider_endpoint"
    assert state["failure_release_calls"] == ["unsupported_provider_endpoint"]
