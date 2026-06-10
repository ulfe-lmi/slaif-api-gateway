from __future__ import annotations

import json
import uuid
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
import respx
from fastapi.testclient import TestClient

from slaif_gateway.api.dependencies import get_authenticated_gateway_key
from slaif_gateway.config import Settings
from slaif_gateway.main import create_app
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
    provider: str = "openai",
    resolved_model: str = "gpt-realtime-mini",
    capabilities: dict[str, object] | None = None,
) -> RouteResolutionResult:
    return RouteResolutionResult(
        requested_model="classroom-realtime",
        resolved_model=resolved_model,
        provider=provider,
        route_id=uuid.uuid4(),
        route_match_type="exact",
        route_pattern="classroom-realtime",
        priority=1,
        provider_base_url=None,
        provider_api_key_env_var=None,
        capabilities=capabilities,
    )


def _estimate() -> ChatCostEstimate:
    return ChatCostEstimate(
        provider="openai",
        requested_model="classroom-realtime",
        resolved_model="gpt-realtime-mini",
        native_currency="EUR",
        estimated_input_tokens=120,
        estimated_output_tokens=512,
        estimated_input_cost_native=Decimal("0.000120000"),
        estimated_output_cost_native=Decimal("0.000256000"),
        estimated_total_cost_native=Decimal("0.005000000"),
        estimated_total_cost_eur=Decimal("0.005000000"),
        pricing_rule_id=None,
        fx_rate_id=None,
        input_price_per_1m=Decimal("1.000000000"),
        output_price_per_1m=Decimal("0.500000000"),
        request_price=Decimal("0.005000000"),
        fx_rate=Decimal("1"),
    )


def _realtime_capabilities() -> dict[str, object]:
    return {
        "realtime": {
            "audio": True,
            "webrtc_client_secrets": True,
            "transcription": False,
            "client_secret_direct_provider_exposure_accepted": False,
        }
    }


def _wire_realtime_pipeline(
    monkeypatch,
    app,
    *,
    provider: str = "openai",
    auth: AuthenticatedGatewayKey | None = None,
    capabilities: dict[str, object] | None = None,
) -> dict[str, object]:
    from slaif_gateway.api import dependencies as dependencies_module
    import slaif_gateway.services.realtime_gateway as realtime_module

    state: dict[str, object] = {
        "session": FakeSession(),
        "reserve_calls": [],
        "finalize_calls": [],
        "custom_finalize_calls": [],
        "failure_release_calls": [],
        "estimate_kwargs": [],
    }
    authenticated_key = auth or _auth()
    route_result = _route(provider=provider, capabilities=capabilities or _realtime_capabilities())
    estimate = _estimate()

    async def _fake_auth_dependency() -> AuthenticatedGatewayKey:
        return authenticated_key

    async def _dummy_db_session(*_args, **_kwargs):
        yield state["session"]

    async def _fake_resolve_model(self, requested_model, authenticated_key, *, endpoint):
        _ = (self, authenticated_key)
        assert requested_model == "classroom-realtime"
        assert endpoint == "/v1/realtime/client_secrets"
        return route_result

    async def _fake_estimate(self, *, route, policy, endpoint, admission_pricing_only=False, at=None):
        _ = (self, route, policy, endpoint, at)
        state["estimate_kwargs"].append(
            {
                "admission_pricing_only": admission_pricing_only,
            }
        )
        return estimate

    async def _fake_reserve(self, *, authenticated_key, route, policy, cost_estimate, request_id, endpoint, now=None):
        _ = (self, authenticated_key, route, policy, cost_estimate, endpoint, now)
        state["reserve_calls"].append(request_id)
        return QuotaReservationResult(
            reservation_id=uuid.uuid4(),
            gateway_key_id=authenticated_key.gateway_key_id,
            request_id=request_id,
            reserved_cost_eur=estimate.estimated_total_cost_eur,
            reserved_tokens=estimate.estimated_input_tokens + estimate.estimated_output_tokens,
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
        _ = (self, authenticated_key, route, policy, pricing_estimate, provider_response, endpoint, kwargs)
        state["finalize_calls"].append(request_id)
        return FinalizedAccountingResult(
            usage_ledger_id=uuid.uuid4(),
            reservation_id=reservation_id,
            gateway_key_id=authenticated_key.gateway_key_id,
            request_id=request_id,
            estimated_cost_eur=pricing_estimate.estimated_total_cost_eur,
            actual_cost_eur=Decimal("0.002000000"),
            actual_cost_native=Decimal("0.002000000"),
            native_currency=pricing_estimate.native_currency,
            prompt_tokens=4,
            completion_tokens=2,
            total_tokens=6,
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
        _ = (self, authenticated_key, route, pricing_estimate, provider_response)
        state["custom_finalize_calls"].append((request_id, kwargs))
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
    monkeypatch.setattr(realtime_module, "_get_db_session_after_auth_header_check", _dummy_db_session)
    monkeypatch.setattr(realtime_module.RouteResolutionService, "resolve_model", _fake_resolve_model)
    monkeypatch.setattr(realtime_module.PricingService, "estimate_realtime_client_secret_cost", _fake_estimate)
    monkeypatch.setattr(realtime_module.QuotaService, "reserve_for_chat_completion", _fake_reserve)
    monkeypatch.setattr(realtime_module.AccountingService, "finalize_successful_response", _fake_finalize_successful_response)
    monkeypatch.setattr(
        realtime_module.AccountingService,
        "finalize_successful_custom_response",
        _fake_finalize_successful_custom_response,
    )
    monkeypatch.setattr(
        realtime_module.AccountingService,
        "record_provider_failure_and_release",
        _fake_record_provider_failure_and_release,
    )
    return state


def _app() -> tuple[TestClient, object]:
    settings = Settings(
        OPENAI_UPSTREAM_API_KEY="sk-live-openai-provider-aaaaaaaaaaaa",
        OPENROUTER_API_KEY="sk-or-live-openrouter-aaaaaaaaaaaa",
        REALTIME_ALLOWED_AUDIO_FORMAT_TYPES="audio/pcm,audio/pcmu,audio/pcma",
        REALTIME_ALLOWED_VOICES="alloy,cedar,marin",
        REALTIME_PCM_AUDIO_RATE=24000,
        REALTIME_CLIENT_SECRET_DEFAULT_TTL_SECONDS=600,
        REALTIME_CLIENT_SECRET_MIN_TTL_SECONDS=10,
        REALTIME_CLIENT_SECRET_MAX_TTL_SECONDS=7200,
        REALTIME_MAX_INSTRUCTIONS_BYTES=2048,
        REALTIME_DEFAULT_MAX_OUTPUT_TOKENS=512,
        REALTIME_MAX_OUTPUT_TOKENS=4096,
    )
    app = create_app(settings)
    return TestClient(app), app


def _request_body() -> dict[str, object]:
    return {
        "expires_after": {"anchor": "created_at", "seconds": 600},
        "session": {
            "type": "realtime",
            "model": "classroom-realtime",
            "output_modalities": ["audio"],
            "audio": {
                "input": {"format": {"type": "audio/pcm", "rate": 24000}},
                "output": {"format": {"type": "audio/pcmu"}, "voice": "cedar"},
            },
            "instructions": "Keep answers short.",
            "max_output_tokens": 256,
        },
    }


def test_chat_responses_audio_and_embeddings_permissions_do_not_allow_realtime(monkeypatch) -> None:
    client, app = _app()
    _wire_realtime_pipeline(
        monkeypatch,
        app,
        auth=_auth(allowed_endpoints=("/v1/chat/completions", "/v1/responses", "/v1/audio/speech", "/v1/embeddings")),
    )

    response = client.post("/v1/realtime/client_secrets", json=_request_body())

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "endpoint_not_allowed"


def test_model_permission_alone_does_not_allow_realtime(monkeypatch) -> None:
    client, app = _app()
    auth = _auth(allowed_endpoints=("/v1/models",))
    auth = replace(auth, allow_all_models=False, allowed_models=("classroom-realtime",))
    _wire_realtime_pipeline(monkeypatch, app, auth=auth)

    response = client.post("/v1/realtime/client_secrets", json=_request_body())

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "endpoint_not_allowed"


def test_quota_limited_key_requires_direct_provider_exposure_acceptance(monkeypatch) -> None:
    client, app = _app()
    auth = replace(_auth(), cost_limit_eur=Decimal("5.000000000"))
    state = _wire_realtime_pipeline(monkeypatch, app, auth=auth)

    response = client.post("/v1/realtime/client_secrets", json=_request_body())

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "realtime_direct_provider_exposure_not_accepted"
    assert state["reserve_calls"] == []


@respx.mock
def test_unlimited_key_can_issue_realtime_client_secret_without_direct_provider_exposure_acceptance(
    monkeypatch,
    respx_mock,
) -> None:
    client, app = _app()
    state = _wire_realtime_pipeline(monkeypatch, app)

    upstream_route = respx_mock.post("https://api.openai.com/v1/realtime/client_secrets").mock(
        return_value=httpx.Response(
            200,
            json={
                "value": "rtcs_unlimited",
                "expires_at": 1893456000,
                "session": {
                    "id": "sess_unlimited",
                    "object": "realtime.session",
                    "type": "realtime",
                    "model": "gpt-realtime-mini",
                    "output_modalities": ["audio"],
                    "audio": {
                        "output": {"voice": "cedar", "format": {"type": "audio/pcmu"}}
                    },
                },
            },
            headers={"content-type": "application/json"},
        )
    )

    response = client.post("/v1/realtime/client_secrets", json=_request_body())

    assert response.status_code == 200
    assert len(upstream_route.calls) == 1
    assert state["estimate_kwargs"] == [{"admission_pricing_only": False}]


@respx.mock
def test_openai_realtime_client_secret_forwarding_uses_resolved_model_and_safe_headers(monkeypatch, respx_mock) -> None:
    client, app = _app()
    capabilities = _realtime_capabilities()
    capabilities["realtime"]["client_secret_direct_provider_exposure_accepted"] = True
    auth = replace(_auth(), cost_limit_eur=Decimal("5.000000000"))
    state = _wire_realtime_pipeline(monkeypatch, app, auth=auth, capabilities=capabilities)

    upstream_route = respx_mock.post("https://api.openai.com/v1/realtime/client_secrets").mock(
        return_value=httpx.Response(
            200,
            json={
                "value": "rtcs_123",
                "expires_at": 1893456000,
                "session": {
                    "id": "sess_123",
                    "object": "realtime.session",
                    "type": "realtime",
                    "model": "gpt-realtime-mini",
                    "output_modalities": ["audio"],
                    "audio": {
                        "output": {"voice": "cedar", "format": {"type": "audio/pcmu"}}
                    },
                },
            },
            headers={
                "content-type": "application/json",
                "openai-request-id": "rt_req_123",
                "set-cookie": "should-not-pass",
            },
        )
    )

    response = client.post("/v1/realtime/client_secrets", json=_request_body())

    assert response.status_code == 200
    assert response.json()["value"] == "rtcs_123"
    assert "set-cookie" not in {key.lower() for key in response.headers}
    assert response.headers["openai-request-id"] == "rt_req_123"
    assert len(upstream_route.calls) == 1
    assert state["finalize_calls"] == []
    assert len(state["custom_finalize_calls"]) == 1

    upstream_request = upstream_route.calls[0].request
    assert upstream_request.headers["authorization"] == "Bearer sk-live-openai-provider-aaaaaaaaaaaa"
    assert "cookie" not in {key.lower() for key in upstream_request.headers}
    assert "x-admin-session" not in {key.lower() for key in upstream_request.headers}
    upstream_body = json.loads(upstream_request.content)
    assert upstream_body["session"]["model"] == "gpt-realtime-mini"
    assert upstream_body["session"]["audio"]["output"]["voice"] == "cedar"
    assert upstream_body["expires_after"] == {"anchor": "created_at", "seconds": 600}

    _, kwargs = state["custom_finalize_calls"][0]
    metadata = kwargs["response_metadata_extra"]
    assert metadata["realtime_estimate_reason"] == "realtime_client_secret_issued"
    assert metadata["realtime_direct_provider_exposure_admission"] is True
    assert metadata["estimate_is_invoice_grade"] is False
    assert metadata["audio_output_voice"] == "cedar"
    assert "instructions" not in metadata
    assert "session" not in metadata
    assert "value" not in json.dumps(metadata)
    assert state["estimate_kwargs"] == [{"admission_pricing_only": True}]


def test_realtime_transcription_session_is_rejected(monkeypatch) -> None:
    client, app = _app()
    _wire_realtime_pipeline(monkeypatch, app)
    body = _request_body()
    body["session"]["type"] = "transcription"  # type: ignore[index]

    response = client.post("/v1/realtime/client_secrets", json=body)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "realtime_option_not_supported"


def test_openrouter_realtime_client_secrets_fail_closed(monkeypatch) -> None:
    client, app = _app()
    _wire_realtime_pipeline(monkeypatch, app, provider="openrouter")

    response = client.post("/v1/realtime/client_secrets", json=_request_body())

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "unsupported_provider_endpoint"
