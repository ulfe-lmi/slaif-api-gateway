from __future__ import annotations

import asyncio
import json
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from slaif_gateway.api.dependencies import get_authenticated_gateway_key
from slaif_gateway.main import create_app
from slaif_gateway.providers.errors import MissingProviderApiKeyError, ProviderTimeoutError
from slaif_gateway.schemas.accounting import FinalizedAccountingResult
from slaif_gateway.schemas.auth import AuthenticatedGatewayKey
from slaif_gateway.schemas.pricing import ChatCostEstimate
from slaif_gateway.schemas.providers import ProviderResponse, ProviderStreamChunk, ProviderUsage
from slaif_gateway.schemas.quota import QuotaReservationResult
from slaif_gateway.schemas.routing import RouteResolutionResult
from slaif_gateway.services.accounting_errors import ReservationFinalizationError
from slaif_gateway.services.pricing_errors import PricingRuleNotFoundError
from slaif_gateway.services.quota_errors import QuotaLimitExceededError
from slaif_gateway.services.responses_route_capabilities import default_responses_capabilities
from slaif_gateway.services.routing_errors import ModelNotFoundError


def _fake_authenticated_gateway_key(
    *,
    allowed_endpoints: tuple[str, ...] = ("/v1/responses",),
    cost_limit_eur: Decimal | None = None,
    token_limit_total: int | None = None,
    responses_streaming_live_burn_policy: dict[str, object] | None = None,
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
        allow_all_endpoints=False,
        allowed_endpoints=allowed_endpoints,
        allowed_providers=None,
        cost_limit_eur=cost_limit_eur,
        token_limit_total=token_limit_total,
        request_limit_total=None,
        rate_limit_policy={},
        responses_streaming_live_burn_policy=responses_streaming_live_burn_policy,
    )


def _route_result(
    requested_model: str = "classroom-responses",
    *,
    responses_streaming: bool = False,
    route_supports_streaming: bool = False,
    responses_json_mode: bool = False,
    responses_structured_outputs: bool = False,
    responses_function_tools: bool = False,
    responses_custom_tools: bool = False,
    responses_image_input: bool = False,
    responses_file_input: bool = False,
    responses_input_token_count: bool = False,
    responses_stored_responses: bool = False,
    responses_previous_response_id: bool = False,
    responses_list_input_items: bool = False,
    responses_compact: bool = False,
    responses_conversations: bool = False,
) -> RouteResolutionResult:
    capabilities = default_responses_capabilities()
    capabilities["streaming"] = responses_streaming
    capabilities["json_mode"] = responses_json_mode
    capabilities["structured_outputs"] = responses_structured_outputs
    capabilities["function_tools"] = responses_function_tools
    capabilities["custom_tools"] = responses_custom_tools
    capabilities["image_input"] = responses_image_input
    capabilities["file_input"] = responses_file_input
    capabilities["input_token_count"] = responses_input_token_count
    capabilities["stored_responses"] = responses_stored_responses
    capabilities["previous_response_id"] = responses_previous_response_id
    capabilities["list_input_items"] = responses_list_input_items
    capabilities["compact"] = responses_compact
    capabilities["conversations"] = responses_conversations
    return RouteResolutionResult(
        requested_model=requested_model,
        resolved_model="gpt-5.2",
        provider="openai",
        route_id=uuid.uuid4(),
        route_match_type="exact",
        route_pattern=requested_model,
        priority=100,
        capabilities={"responses": capabilities},
        supports_streaming=route_supports_streaming,
    )


def _estimate() -> ChatCostEstimate:
    return ChatCostEstimate(
        provider="openai",
        requested_model="classroom-responses",
        resolved_model="gpt-5.2",
        native_currency="EUR",
        estimated_input_tokens=20,
        estimated_output_tokens=30,
        estimated_input_cost_native=Decimal("0.001"),
        estimated_output_cost_native=Decimal("0.002"),
        estimated_total_cost_native=Decimal("0.003"),
        estimated_total_cost_eur=Decimal("0.003"),
        pricing_rule_id=None,
        fx_rate_id=None,
    )


def _responses_request(model: str = "classroom-responses") -> dict[str, object]:
    return {
        "model": model,
        "input": "hello",
        "max_output_tokens": 20,
    }


def _responses_function_tool_request(model: str = "classroom-responses") -> dict[str, object]:
    return {
        **_responses_request(model),
        "tools": [
            {
                "type": "function",
                "name": "lookup",
                "parameters": {"type": "object", "properties": {}},
            }
        ],
        "tool_choice": {"type": "function", "name": "lookup"},
    }


def _responses_custom_tool_request(model: str = "classroom-responses") -> dict[str, object]:
    return {
        **_responses_request(model),
        "tools": [
            {
                "type": "custom",
                "name": "emit_regex",
                "description": "Local custom intent.",
                "format": {
                    "type": "grammar",
                    "syntax": "regex",
                    "definition": "[a-z]+",
                },
            }
        ],
        "tool_choice": {"type": "custom", "name": "emit_regex"},
    }


def _responses_image_input_request(model: str = "classroom-responses") -> dict[str, object]:
    return {
        **_responses_request(model),
        "input": [
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": "describe the image"},
                    {
                        "type": "input_image",
                        "image_url": "https://example.test/image.png",
                        "detail": "low",
                    },
                ],
            }
        ],
    }


def _responses_file_input_request(model: str = "classroom-responses") -> dict[str, object]:
    return {
        **_responses_request(model),
        "input": [
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": "summarize the file"},
                    {
                        "type": "input_file",
                        "file_url": "https://example.test/document.pdf",
                    },
                ],
            }
        ],
    }


def _sse(payload: dict[str, object]) -> str:
    return f"data: {json.dumps(payload, separators=(',', ':'))}\n\n"


def _response_stream_chunk(
    payload: dict[str, object],
    *,
    usage: ProviderUsage | None = None,
) -> ProviderStreamChunk:
    return ProviderStreamChunk(
        provider="openai",
        upstream_model="gpt-5.2",
        data=json.dumps(payload, separators=(",", ":")),
        raw_sse_event=_sse(payload),
        json_body=payload,
        usage=usage,
        upstream_request_id="upstream-responses-stream",
    )


def _done_chunk() -> ProviderStreamChunk:
    return ProviderStreamChunk(
        provider="openai",
        upstream_model="gpt-5.2",
        data="[DONE]",
        raw_sse_event="data: [DONE]\n\n",
        is_done=True,
        upstream_request_id="upstream-responses-stream",
    )


def _completed_payload(*, include_usage: bool = True) -> dict[str, object]:
    response: dict[str, object] = {"id": "resp_test"}
    if include_usage:
        response["usage"] = {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2}
    return {"type": "response.completed", "response": response}


def _wire_auth_and_db(monkeypatch, app, authenticated_key: AuthenticatedGatewayKey | None = None) -> None:
    from slaif_gateway.api import dependencies as dependencies_module
    import slaif_gateway.services.responses_gateway as main_module

    key = authenticated_key or _fake_authenticated_gateway_key()

    async def _fake_auth_dependency() -> AuthenticatedGatewayKey:
        return key

    async def _dummy_db_session():
        yield object()

    app.dependency_overrides[get_authenticated_gateway_key] = _fake_auth_dependency
    monkeypatch.setattr(dependencies_module, "_get_db_session_after_auth_header_check", _dummy_db_session)
    monkeypatch.setattr(main_module, "_get_db_session_after_auth_header_check", _dummy_db_session)


def _wire_successful_route_pricing_quota(monkeypatch, *, quota_error=None) -> tuple[list[str], list[str]]:
    import slaif_gateway.services.responses_gateway as main_module

    reserve_calls: list[str] = []
    release_calls: list[str] = []

    async def _fake_resolve_model(self, requested_model, authenticated_key, *, endpoint="/v1/chat/completions"):
        _ = (self, authenticated_key)
        assert endpoint == "/v1/responses"
        return _route_result(requested_model)

    async def _fake_estimate_chat_completion_cost(self, *, route, policy, endpoint="chat.completions", at=None):
        _ = (self, route, policy, at)
        assert endpoint == "/v1/responses"
        return _estimate()

    async def _fake_reserve(
        self,
        *,
        authenticated_key,
        route,
        policy,
        cost_estimate,
        request_id,
        endpoint="/v1/chat/completions",
        now=None,
    ):
        _ = (self, authenticated_key, policy, cost_estimate, request_id, now)
        assert endpoint == "/v1/responses"
        reserve_calls.append(route.requested_model)
        if quota_error is not None:
            raise quota_error
        return QuotaReservationResult(
            reservation_id=uuid.uuid4(),
            gateway_key_id=authenticated_key.gateway_key_id,
            request_id=request_id,
            reserved_cost_eur=Decimal("0.003"),
            reserved_tokens=50,
            status="pending",
            expires_at=datetime.now(UTC) + timedelta(minutes=15),
        )

    async def _fake_release(self, reservation_id, *, reason=None, now=None):
        _ = (self, reason, now)
        release_calls.append(str(reservation_id))
        return QuotaReservationResult(
            reservation_id=reservation_id,
            gateway_key_id=uuid.uuid4(),
            request_id="req",
            reserved_cost_eur=Decimal("0.003"),
            reserved_tokens=50,
            status="released",
            expires_at=datetime.now(UTC) + timedelta(minutes=15),
        )

    monkeypatch.setattr(main_module.RouteResolutionService, "resolve_model", _fake_resolve_model)
    monkeypatch.setattr(
        main_module.PricingService,
        "estimate_chat_completion_cost",
        _fake_estimate_chat_completion_cost,
    )
    monkeypatch.setattr(main_module.QuotaService, "reserve_for_chat_completion", _fake_reserve)
    monkeypatch.setattr(main_module.QuotaService, "release_reservation", _fake_release)
    return reserve_calls, release_calls


def _wire_streaming_route(monkeypatch) -> None:
    import slaif_gateway.services.responses_gateway as main_module

    async def _fake_resolve_model(self, requested_model, authenticated_key, *, endpoint="/v1/chat/completions"):
        _ = (self, authenticated_key, endpoint)
        return _route_result(
            requested_model,
            responses_streaming=True,
            route_supports_streaming=True,
        )

    monkeypatch.setattr(main_module.RouteResolutionService, "resolve_model", _fake_resolve_model)


def _wire_successful_forwarding(monkeypatch) -> list[str]:
    import slaif_gateway.services.responses_gateway as main_module

    finalize_calls: list[str] = []

    class _FakeAdapter:
        async def forward_response(self, request):
            assert request.endpoint == "responses"
            assert request.body["store"] is False
            return ProviderResponse(
                provider=request.provider,
                upstream_model=request.upstream_model,
                status_code=200,
                json_body={"id": "resp_test", "object": "response"},
                usage=ProviderUsage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
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
        provider_completed_usage_ledger_id=None,
        streaming=False,
    ):
        _ = (
            self,
            reservation_id,
            authenticated_key,
            policy,
            pricing_estimate,
            provider_response,
            request_id,
            started_at,
            finished_at,
            provider_completed_usage_ledger_id,
            streaming,
        )
        assert endpoint == "responses"
        finalize_calls.append(route.requested_model)
        return FinalizedAccountingResult(
            usage_ledger_id=uuid.uuid4(),
            reservation_id=reservation_id,
            gateway_key_id=authenticated_key.gateway_key_id,
            request_id=request_id,
            estimated_cost_eur=Decimal("0.003"),
            actual_cost_eur=Decimal("0.003"),
            actual_cost_native=Decimal("0.003"),
            native_currency="EUR",
            prompt_tokens=1,
            completion_tokens=1,
            total_tokens=2,
            accounting_status="finalized",
        )

    monkeypatch.setattr(main_module, "get_provider_adapter", lambda provider, settings: _FakeAdapter())
    monkeypatch.setattr(
        main_module.AccountingService,
        "finalize_successful_response",
        _fake_finalize_successful_response,
    )
    return finalize_calls


def test_valid_responses_path_reserves_finalizes_then_returns_provider_response(monkeypatch) -> None:
    app = create_app()
    _wire_auth_and_db(monkeypatch, app)
    reserve_calls, release_calls = _wire_successful_route_pricing_quota(monkeypatch)
    finalize_calls = _wire_successful_forwarding(monkeypatch)

    response = TestClient(app).post("/v1/responses", json=_responses_request())

    assert response.status_code == 200
    assert response.json()["id"] == "resp_test"
    assert reserve_calls == ["classroom-responses"]
    assert release_calls == []
    assert finalize_calls == ["classroom-responses"]


def test_stored_response_create_requires_capability_and_persists_safe_reference(monkeypatch) -> None:
    import slaif_gateway.services.responses_gateway as main_module

    app = create_app()
    _wire_auth_and_db(monkeypatch, app)
    reserve_calls, release_calls = _wire_successful_route_pricing_quota(monkeypatch)
    finalize_calls: list[str] = []
    persist_calls: list[tuple[uuid.UUID, str, str]] = []

    async def _fake_resolve_model(self, requested_model, authenticated_key, *, endpoint="/v1/chat/completions"):
        _ = (self, authenticated_key, endpoint)
        return _route_result(requested_model, responses_stored_responses=True)

    class _FakeAdapter:
        async def forward_response(self, request):
            assert request.body["store"] is True
            assert request.body["model"] == "gpt-5.2"
            return ProviderResponse(
                provider=request.provider,
                upstream_model=request.upstream_model,
                status_code=200,
                json_body={"id": "resp_stored_test", "object": "response"},
                upstream_request_id="upstream-req-stored",
                usage=ProviderUsage(prompt_tokens=1, completion_tokens=2, total_tokens=3),
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
        provider_completed_usage_ledger_id=None,
        streaming=False,
    ):
        _ = (
            self,
            reservation_id,
            authenticated_key,
            policy,
            pricing_estimate,
            provider_response,
            request_id,
            endpoint,
            started_at,
            finished_at,
            provider_completed_usage_ledger_id,
            streaming,
        )
        finalize_calls.append(route.requested_model)
        return FinalizedAccountingResult(
            usage_ledger_id=uuid.uuid4(),
            reservation_id=reservation_id,
            gateway_key_id=authenticated_key.gateway_key_id,
            request_id=request_id,
            estimated_cost_eur=Decimal("0.003"),
            actual_cost_eur=Decimal("0.003"),
            actual_cost_native=Decimal("0.003"),
            native_currency="EUR",
            prompt_tokens=1,
            completion_tokens=2,
            total_tokens=3,
            accounting_status="finalized",
        )

    async def _fake_persist_reference(*, authenticated_key, route, provider_response, request):
        _ = request
        persist_calls.append(
            (
                authenticated_key.gateway_key_id,
                route.provider,
                provider_response.json_body["id"],
            )
        )

    monkeypatch.setattr(main_module.RouteResolutionService, "resolve_model", _fake_resolve_model)
    monkeypatch.setattr(main_module, "get_provider_adapter", lambda route, settings: _FakeAdapter())
    monkeypatch.setattr(
        main_module.AccountingService,
        "finalize_successful_response",
        _fake_finalize_successful_response,
    )
    monkeypatch.setattr(main_module, "_persist_stored_response_reference", _fake_persist_reference)

    response = TestClient(app).post("/v1/responses", json={**_responses_request(), "store": True})

    assert response.status_code == 200
    assert response.json()["id"] == "resp_stored_test"
    assert reserve_calls == ["classroom-responses"]
    assert release_calls == []
    assert finalize_calls == ["classroom-responses"]
    assert len(persist_calls) == 1
    assert persist_calls[0][1:] == ("openai", "resp_stored_test")


def test_stored_response_create_rejects_missing_capability_before_rate_pricing_quota_provider(
    monkeypatch,
) -> None:
    import slaif_gateway.services.responses_gateway as main_module

    app = create_app()
    _wire_auth_and_db(monkeypatch, app)
    rate_calls: list[str] = []
    pricing_calls: list[str] = []
    quota_calls: list[str] = []
    provider_calls: list[str] = []

    async def _fake_resolve_model(self, requested_model, authenticated_key, *, endpoint="/v1/chat/completions"):
        _ = (self, authenticated_key, endpoint)
        return _route_result(requested_model)

    async def _fake_reserve_rate_limit(**kwargs):
        rate_calls.append(str(kwargs))

    async def _fake_estimate_chat_completion_cost(self, **kwargs):
        _ = self
        pricing_calls.append(str(kwargs))

    async def _fake_reserve(self, **kwargs):
        _ = self
        quota_calls.append(str(kwargs))

    def _fake_get_provider_adapter(route, settings):
        _ = (route, settings)
        provider_calls.append("provider")
        raise AssertionError("provider adapter should not be called")

    monkeypatch.setattr(main_module.RouteResolutionService, "resolve_model", _fake_resolve_model)
    monkeypatch.setattr(main_module, "_reserve_redis_rate_limit", _fake_reserve_rate_limit)
    monkeypatch.setattr(
        main_module.PricingService,
        "estimate_chat_completion_cost",
        _fake_estimate_chat_completion_cost,
    )
    monkeypatch.setattr(main_module.QuotaService, "reserve_for_chat_completion", _fake_reserve)
    monkeypatch.setattr(main_module, "get_provider_adapter", _fake_get_provider_adapter)

    response = TestClient(app).post("/v1/responses", json={**_responses_request(), "store": True})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "responses_stored_response_capability_not_supported"
    assert rate_calls == []
    assert pricing_calls == []
    assert quota_calls == []
    assert provider_calls == []


def test_previous_response_id_owned_reference_forwards_canonical_body(monkeypatch) -> None:
    import slaif_gateway.services.responses_gateway as main_module

    app = create_app()
    auth = _fake_authenticated_gateway_key()
    _wire_auth_and_db(monkeypatch, app, auth)
    reserve_calls, release_calls = _wire_successful_route_pricing_quota(monkeypatch)
    finalize_calls = _wire_successful_forwarding(monkeypatch)
    route = _route_result("classroom-responses", responses_previous_response_id=True)
    lookup_calls: list[str] = []
    forwarded_bodies: list[dict[str, object]] = []

    async def _fake_resolve_model(self, requested_model, authenticated_key, *, endpoint="/v1/chat/completions"):
        _ = (self, authenticated_key, endpoint)
        assert requested_model == "classroom-responses"
        return route

    async def _fake_get_reference(*, response_id, authenticated_key, request):
        _ = request
        assert authenticated_key.gateway_key_id == auth.gateway_key_id
        lookup_calls.append(response_id)
        return SimpleNamespace(
            id=uuid.uuid4(),
            provider="openai",
            provider_response_id=response_id,
            upstream_model="gpt-5.2",
            route_id=route.route_id,
        )

    class _FakeAdapter:
        async def forward_response(self, request):
            assert request.endpoint == "responses"
            forwarded_bodies.append(dict(request.body))
            return ProviderResponse(
                provider=request.provider,
                upstream_model=request.upstream_model,
                status_code=200,
                json_body={"id": "resp_next", "object": "response"},
                usage=ProviderUsage(prompt_tokens=1, completion_tokens=2, total_tokens=3),
            )

    monkeypatch.setattr(main_module.RouteResolutionService, "resolve_model", _fake_resolve_model)
    monkeypatch.setattr(main_module, "_get_owned_active_response_reference", _fake_get_reference)
    monkeypatch.setattr(main_module, "get_provider_adapter", lambda route, settings: _FakeAdapter())

    response = TestClient(app).post(
        "/v1/responses",
        json={**_responses_request(), "previous_response_id": "resp_previous"},
    )

    assert response.status_code == 200
    assert lookup_calls == ["resp_previous"]
    assert forwarded_bodies == [
        {
            "model": "gpt-5.2",
            "input": "hello",
            "max_output_tokens": 20,
            "store": False,
            "previous_response_id": "resp_previous",
        }
    ]
    assert reserve_calls == ["classroom-responses"]
    assert release_calls == []
    assert finalize_calls == ["classroom-responses"]


def test_previous_response_id_unknown_reference_returns_404_before_rate_pricing_quota_provider(
    monkeypatch,
) -> None:
    import slaif_gateway.services.responses_gateway as main_module

    app = create_app()
    _wire_auth_and_db(monkeypatch, app)
    route = _route_result("classroom-responses", responses_previous_response_id=True)
    rate_calls: list[str] = []
    pricing_calls: list[str] = []
    quota_calls: list[str] = []
    provider_calls: list[str] = []

    async def _fake_resolve_model(self, requested_model, authenticated_key, *, endpoint="/v1/chat/completions"):
        _ = (self, requested_model, authenticated_key, endpoint)
        return route

    async def _fake_get_reference(*, response_id, authenticated_key, request):
        _ = (response_id, authenticated_key, request)
        return None

    async def _fake_reserve_rate_limit(**kwargs):
        rate_calls.append(str(kwargs))

    async def _fake_estimate_chat_completion_cost(self, **kwargs):
        _ = self
        pricing_calls.append(str(kwargs))

    async def _fake_reserve(self, **kwargs):
        _ = self
        quota_calls.append(str(kwargs))

    def _fake_get_provider_adapter(route, settings):
        _ = (route, settings)
        provider_calls.append("provider")
        raise AssertionError("provider adapter should not be called")

    monkeypatch.setattr(main_module.RouteResolutionService, "resolve_model", _fake_resolve_model)
    monkeypatch.setattr(main_module, "_get_owned_active_response_reference", _fake_get_reference)
    monkeypatch.setattr(main_module, "_reserve_redis_rate_limit", _fake_reserve_rate_limit)
    monkeypatch.setattr(
        main_module.PricingService,
        "estimate_chat_completion_cost",
        _fake_estimate_chat_completion_cost,
    )
    monkeypatch.setattr(main_module.QuotaService, "reserve_for_chat_completion", _fake_reserve)
    monkeypatch.setattr(main_module, "get_provider_adapter", _fake_get_provider_adapter)

    response = TestClient(app).post(
        "/v1/responses",
        json={**_responses_request(), "previous_response_id": "resp_missing"},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "response_not_found"
    assert rate_calls == []
    assert pricing_calls == []
    assert quota_calls == []
    assert provider_calls == []


def test_previous_response_id_provider_mismatch_returns_404_before_provider(monkeypatch) -> None:
    import slaif_gateway.services.responses_gateway as main_module

    app = create_app()
    _wire_auth_and_db(monkeypatch, app)
    route = _route_result("classroom-responses", responses_previous_response_id=True)
    provider_calls: list[str] = []

    async def _fake_resolve_model(self, requested_model, authenticated_key, *, endpoint="/v1/chat/completions"):
        _ = (self, requested_model, authenticated_key, endpoint)
        return route

    async def _fake_get_reference(*, response_id, authenticated_key, request):
        _ = (response_id, authenticated_key, request)
        return SimpleNamespace(
            id=uuid.uuid4(),
            provider="openrouter",
            provider_response_id=response_id,
            upstream_model="gpt-5.2",
            route_id=route.route_id,
        )

    def _fake_get_provider_adapter(route, settings):
        _ = (route, settings)
        provider_calls.append("provider")
        raise AssertionError("provider adapter should not be called")

    monkeypatch.setattr(main_module.RouteResolutionService, "resolve_model", _fake_resolve_model)
    monkeypatch.setattr(main_module, "_get_owned_active_response_reference", _fake_get_reference)
    monkeypatch.setattr(main_module, "get_provider_adapter", _fake_get_provider_adapter)

    response = TestClient(app).post(
        "/v1/responses",
        json={**_responses_request(), "previous_response_id": "resp_openrouter"},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "response_not_found"
    assert provider_calls == []


def test_responses_create_with_owned_conversation_forwards_canonical_body(monkeypatch) -> None:
    import slaif_gateway.services.responses_gateway as main_module

    app = create_app()
    auth = _fake_authenticated_gateway_key()
    _wire_auth_and_db(monkeypatch, app, auth)
    reserve_calls, release_calls = _wire_successful_route_pricing_quota(monkeypatch)
    finalize_calls = _wire_successful_forwarding(monkeypatch)
    route = _route_result("classroom-responses", responses_conversations=True)
    lookup_calls: list[str] = []
    forwarded_bodies: list[dict[str, object]] = []

    async def _fake_resolve_model(self, requested_model, authenticated_key, *, endpoint="/v1/chat/completions"):
        _ = (self, authenticated_key, endpoint)
        assert requested_model == "classroom-responses"
        return route

    async def _fake_get_reference(*, conversation_id, authenticated_key, request):
        _ = request
        assert authenticated_key.gateway_key_id == auth.gateway_key_id
        lookup_calls.append(conversation_id)
        return SimpleNamespace(
            id=uuid.uuid4(),
            provider="openai",
            provider_conversation_id=conversation_id,
            route_id=None,
        )

    class _FakeAdapter:
        async def forward_response(self, request):
            assert request.endpoint == "responses"
            forwarded_bodies.append(dict(request.body))
            return ProviderResponse(
                provider=request.provider,
                upstream_model=request.upstream_model,
                status_code=200,
                json_body={"id": "resp_conversation", "object": "response"},
                usage=ProviderUsage(prompt_tokens=1, completion_tokens=2, total_tokens=3),
            )

    monkeypatch.setattr(main_module.RouteResolutionService, "resolve_model", _fake_resolve_model)
    monkeypatch.setattr(main_module, "_get_owned_active_conversation_reference", _fake_get_reference)
    monkeypatch.setattr(main_module, "get_provider_adapter", lambda route, settings: _FakeAdapter())

    response = TestClient(app).post(
        "/v1/responses",
        json={**_responses_request(), "conversation": "conv_owned"},
    )

    assert response.status_code == 200
    assert lookup_calls == ["conv_owned"]
    assert forwarded_bodies == [
        {
            "model": "gpt-5.2",
            "input": "hello",
            "max_output_tokens": 20,
            "store": False,
            "conversation": "conv_owned",
        }
    ]
    assert reserve_calls == ["classroom-responses"]
    assert release_calls == []
    assert finalize_calls == ["classroom-responses"]


def test_responses_create_with_unknown_conversation_returns_404_before_provider(monkeypatch) -> None:
    import slaif_gateway.services.responses_gateway as main_module

    app = create_app()
    _wire_auth_and_db(monkeypatch, app)
    route = _route_result("classroom-responses", responses_conversations=True)
    rate_calls: list[str] = []
    pricing_calls: list[str] = []
    quota_calls: list[str] = []
    provider_calls: list[str] = []

    async def _fake_resolve_model(self, requested_model, authenticated_key, *, endpoint="/v1/chat/completions"):
        _ = (self, requested_model, authenticated_key, endpoint)
        return route

    async def _fake_get_reference(*, conversation_id, authenticated_key, request):
        _ = (conversation_id, authenticated_key, request)
        return None

    async def _fake_reserve_rate_limit(**kwargs):
        rate_calls.append(str(kwargs))

    async def _fake_estimate_chat_completion_cost(self, **kwargs):
        _ = self
        pricing_calls.append(str(kwargs))

    async def _fake_reserve(self, **kwargs):
        _ = self
        quota_calls.append(str(kwargs))

    def _fake_get_provider_adapter(route, settings):
        _ = (route, settings)
        provider_calls.append("provider")
        raise AssertionError("provider adapter should not be called")

    monkeypatch.setattr(main_module.RouteResolutionService, "resolve_model", _fake_resolve_model)
    monkeypatch.setattr(main_module, "_get_owned_active_conversation_reference", _fake_get_reference)
    monkeypatch.setattr(main_module, "_reserve_redis_rate_limit", _fake_reserve_rate_limit)
    monkeypatch.setattr(
        main_module.PricingService,
        "estimate_chat_completion_cost",
        _fake_estimate_chat_completion_cost,
    )
    monkeypatch.setattr(main_module.QuotaService, "reserve_for_chat_completion", _fake_reserve)
    monkeypatch.setattr(main_module, "get_provider_adapter", _fake_get_provider_adapter)

    response = TestClient(app).post(
        "/v1/responses",
        json={**_responses_request(), "conversation": "conv_missing"},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "conversation_not_found"
    assert rate_calls == []
    assert pricing_calls == []
    assert quota_calls == []
    assert provider_calls == []


def test_responses_create_with_provider_mismatched_conversation_returns_404_before_provider(
    monkeypatch,
) -> None:
    import slaif_gateway.services.responses_gateway as main_module

    app = create_app()
    _wire_auth_and_db(monkeypatch, app)
    route = _route_result("classroom-responses", responses_conversations=True)
    provider_calls: list[str] = []

    async def _fake_resolve_model(self, requested_model, authenticated_key, *, endpoint="/v1/chat/completions"):
        _ = (self, requested_model, authenticated_key, endpoint)
        return route

    async def _fake_get_reference(*, conversation_id, authenticated_key, request):
        _ = (conversation_id, authenticated_key, request)
        return SimpleNamespace(
            id=uuid.uuid4(),
            provider="openrouter",
            provider_conversation_id="conv_openrouter",
            route_id=route.route_id,
        )

    def _fake_get_provider_adapter(route, settings):
        _ = (route, settings)
        provider_calls.append("provider")
        raise AssertionError("provider adapter should not be called")

    monkeypatch.setattr(main_module.RouteResolutionService, "resolve_model", _fake_resolve_model)
    monkeypatch.setattr(main_module, "_get_owned_active_conversation_reference", _fake_get_reference)
    monkeypatch.setattr(main_module, "get_provider_adapter", _fake_get_provider_adapter)

    response = TestClient(app).post(
        "/v1/responses",
        json={**_responses_request(), "conversation": "conv_openrouter"},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "conversation_not_found"
    assert provider_calls == []


def test_store_true_with_previous_response_id_persists_new_response_reference(monkeypatch) -> None:
    import slaif_gateway.services.responses_gateway as main_module

    app = create_app()
    auth = _fake_authenticated_gateway_key()
    _wire_auth_and_db(monkeypatch, app, auth)
    reserve_calls, release_calls = _wire_successful_route_pricing_quota(monkeypatch)
    finalize_calls: list[str] = []
    persist_calls: list[str] = []
    route = _route_result(
        "classroom-responses",
        responses_stored_responses=True,
        responses_previous_response_id=True,
    )

    async def _fake_resolve_model(self, requested_model, authenticated_key, *, endpoint="/v1/chat/completions"):
        _ = (self, requested_model, authenticated_key, endpoint)
        return route

    async def _fake_get_reference(*, response_id, authenticated_key, request):
        _ = (authenticated_key, request)
        return SimpleNamespace(
            id=uuid.uuid4(),
            provider="openai",
            provider_response_id=response_id,
            upstream_model="gpt-5.2",
            route_id=route.route_id,
        )

    class _FakeAdapter:
        async def forward_response(self, request):
            assert request.body["store"] is True
            assert request.body["previous_response_id"] == "resp_previous"
            return ProviderResponse(
                provider=request.provider,
                upstream_model=request.upstream_model,
                status_code=200,
                json_body={"id": "resp_next_stored", "object": "response"},
                upstream_request_id="upstream-req-next-stored",
                usage=ProviderUsage(prompt_tokens=1, completion_tokens=2, total_tokens=3),
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
        provider_completed_usage_ledger_id=None,
        streaming=False,
    ):
        _ = (
            self,
            reservation_id,
            authenticated_key,
            policy,
            pricing_estimate,
            provider_response,
            request_id,
            endpoint,
            started_at,
            finished_at,
            provider_completed_usage_ledger_id,
            streaming,
        )
        finalize_calls.append(route.requested_model)
        return FinalizedAccountingResult(
            usage_ledger_id=uuid.uuid4(),
            reservation_id=reservation_id,
            gateway_key_id=authenticated_key.gateway_key_id,
            request_id=request_id,
            estimated_cost_eur=Decimal("0.003"),
            actual_cost_eur=Decimal("0.003"),
            actual_cost_native=Decimal("0.003"),
            native_currency="EUR",
            prompt_tokens=1,
            completion_tokens=2,
            total_tokens=3,
            accounting_status="finalized",
        )

    async def _fake_persist_reference(*, authenticated_key, route, provider_response, request):
        _ = (authenticated_key, route, request)
        persist_calls.append(provider_response.json_body["id"])

    monkeypatch.setattr(main_module.RouteResolutionService, "resolve_model", _fake_resolve_model)
    monkeypatch.setattr(main_module, "_get_owned_active_response_reference", _fake_get_reference)
    monkeypatch.setattr(main_module, "get_provider_adapter", lambda route, settings: _FakeAdapter())
    monkeypatch.setattr(
        main_module.AccountingService,
        "finalize_successful_response",
        _fake_finalize_successful_response,
    )
    monkeypatch.setattr(main_module, "_persist_stored_response_reference", _fake_persist_reference)

    response = TestClient(app).post(
        "/v1/responses",
        json={
            **_responses_request(),
            "store": True,
            "previous_response_id": "resp_previous",
        },
    )

    assert response.status_code == 200
    assert response.json()["id"] == "resp_next_stored"
    assert reserve_calls == ["classroom-responses"]
    assert release_calls == []
    assert finalize_calls == ["classroom-responses"]
    assert persist_calls == ["resp_next_stored"]


def test_response_retrieve_requires_explicit_endpoint_permission(monkeypatch) -> None:
    app = create_app()
    _wire_auth_and_db(
        monkeypatch,
        app,
        _fake_authenticated_gateway_key(allowed_endpoints=("/v1/responses",)),
    )

    response = TestClient(app).get("/v1/responses/resp_owned")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "endpoint_not_allowed"


def test_response_retrieve_owned_reference_proxies_without_generation_accounting(monkeypatch) -> None:
    import slaif_gateway.services.responses_gateway as main_module

    app = create_app()
    auth = _fake_authenticated_gateway_key(allowed_endpoints=("GET /v1/responses/{response_id}",))
    _wire_auth_and_db(monkeypatch, app, auth)
    pricing_calls: list[str] = []
    quota_calls: list[str] = []
    provider_calls: list[str] = []

    async def _fake_get_reference(*, response_id, authenticated_key, request):
        _ = request
        assert authenticated_key.gateway_key_id == auth.gateway_key_id
        assert response_id == "resp_owned"
        return SimpleNamespace(
            id=uuid.uuid4(),
            provider="openai",
            provider_response_id=response_id,
            upstream_model="gpt-5.2",
        )

    async def _fake_route_for_reference(reference, *, request):
        _ = (reference, request)
        return SimpleNamespace(provider="openai")

    class _FakeAdapter:
        async def retrieve_response(self, request, *, response_id):
            provider_calls.append(response_id)
            assert request.endpoint == "responses.retrieve"
            assert request.body == {}
            return ProviderResponse(
                provider=request.provider,
                upstream_model=request.upstream_model,
                status_code=200,
                json_body={"id": response_id, "object": "response", "status": "completed"},
            )

    async def _fake_estimate_chat_completion_cost(self, **kwargs):
        _ = self
        pricing_calls.append(str(kwargs))

    async def _fake_reserve(self, **kwargs):
        _ = self
        quota_calls.append(str(kwargs))

    monkeypatch.setattr(main_module, "_get_owned_active_response_reference", _fake_get_reference)
    monkeypatch.setattr(main_module, "_provider_route_for_reference", _fake_route_for_reference)
    monkeypatch.setattr(main_module, "get_provider_adapter", lambda route, settings: _FakeAdapter())
    monkeypatch.setattr(
        main_module.PricingService,
        "estimate_chat_completion_cost",
        _fake_estimate_chat_completion_cost,
    )
    monkeypatch.setattr(main_module.QuotaService, "reserve_for_chat_completion", _fake_reserve)

    response = TestClient(app).get("/v1/responses/resp_owned")

    assert response.status_code == 200
    assert response.json()["id"] == "resp_owned"
    assert provider_calls == ["resp_owned"]
    assert pricing_calls == []
    assert quota_calls == []


def test_response_retrieve_missing_or_non_owned_reference_returns_404_before_provider(monkeypatch) -> None:
    import slaif_gateway.services.responses_gateway as main_module

    app = create_app()
    _wire_auth_and_db(
        monkeypatch,
        app,
        _fake_authenticated_gateway_key(allowed_endpoints=("GET /v1/responses/{response_id}",)),
    )
    provider_calls: list[str] = []

    async def _fake_get_reference(*, response_id, authenticated_key, request):
        _ = (response_id, authenticated_key, request)
        return None

    def _fake_get_provider_adapter(route, settings):
        _ = (route, settings)
        provider_calls.append("provider")
        raise AssertionError("provider adapter should not be called")

    monkeypatch.setattr(main_module, "_get_owned_active_response_reference", _fake_get_reference)
    monkeypatch.setattr(main_module, "get_provider_adapter", _fake_get_provider_adapter)

    response = TestClient(app).get("/v1/responses/resp_missing")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "response_not_found"
    assert provider_calls == []


def test_response_retrieve_rejects_unsupported_query_params_before_lookup_or_proxy(
    monkeypatch,
) -> None:
    import slaif_gateway.services.responses_gateway as main_module

    app = create_app()
    _wire_auth_and_db(
        monkeypatch,
        app,
        _fake_authenticated_gateway_key(allowed_endpoints=("GET /v1/responses/{response_id}",)),
    )
    lookup_calls: list[str] = []
    provider_calls: list[str] = []

    async def _fake_get_reference(*, response_id, authenticated_key, request):
        _ = (authenticated_key, request)
        lookup_calls.append(response_id)
        return SimpleNamespace(
            id=uuid.uuid4(),
            provider="openai",
            provider_response_id=response_id,
            upstream_model="gpt-5.2",
        )

    def _fake_get_provider_adapter(route, settings):
        _ = (route, settings)
        provider_calls.append("provider")
        raise AssertionError("provider adapter should not be called")

    monkeypatch.setattr(main_module, "_get_owned_active_response_reference", _fake_get_reference)
    monkeypatch.setattr(main_module, "get_provider_adapter", _fake_get_provider_adapter)

    response = TestClient(app).get("/v1/responses/resp_owned?starting_after=evt_123")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_response_retrieve_query"
    assert lookup_calls == []
    assert provider_calls == []


def test_response_input_items_requires_explicit_endpoint_permission(monkeypatch) -> None:
    app = create_app()
    _wire_auth_and_db(
        monkeypatch,
        app,
        _fake_authenticated_gateway_key(allowed_endpoints=("/v1/responses",)),
    )

    response = TestClient(app).get("/v1/responses/resp_owned/input_items")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "endpoint_not_allowed"


def test_response_input_items_validates_query_params(monkeypatch) -> None:
    app = create_app()
    _wire_auth_and_db(
        monkeypatch,
        app,
        _fake_authenticated_gateway_key(
            allowed_endpoints=("GET /v1/responses/{response_id}/input_items",)
        ),
    )
    client = TestClient(app)

    for query in (
        "?unknown=value",
        "?limit=0",
        "?limit=101",
        "?limit=abc",
        "?order=newest",
        "?after=",
        "?include=web_search_call.action.sources",
    ):
        response = client.get(f"/v1/responses/resp_owned/input_items{query}")
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "invalid_response_input_items_query"


def test_response_input_items_owned_reference_proxies_without_generation_accounting(monkeypatch) -> None:
    import slaif_gateway.services.responses_gateway as main_module

    app = create_app()
    auth = _fake_authenticated_gateway_key(
        allowed_endpoints=("GET /v1/responses/{response_id}/input_items",)
    )
    _wire_auth_and_db(monkeypatch, app, auth)
    pricing_calls: list[str] = []
    quota_calls: list[str] = []
    provider_calls: list[str] = []

    async def _fake_get_reference(*, response_id, authenticated_key, request):
        _ = request
        assert authenticated_key.gateway_key_id == auth.gateway_key_id
        assert response_id == "resp_owned"
        return SimpleNamespace(
            id=uuid.uuid4(),
            provider="openai",
            provider_response_id=response_id,
            upstream_model="gpt-5.2",
            route_id=uuid.uuid4(),
        )

    async def _fake_route_for_reference(reference, *, request, list_input_items_requested=False):
        _ = (reference, request)
        assert list_input_items_requested is True
        return SimpleNamespace(provider="openai")

    class _FakeAdapter:
        async def list_response_input_items(self, request, *, response_id):
            provider_calls.append(response_id)
            assert request.endpoint == "responses.input_items"
            assert request.body == {
                "after": "item_1",
                "include": ["message.input_image.image_url"],
                "limit": 25,
                "order": "asc",
            }
            return ProviderResponse(
                provider=request.provider,
                upstream_model=request.upstream_model,
                status_code=200,
                json_body={
                    "object": "list",
                    "data": [],
                    "first_id": None,
                    "last_id": None,
                    "has_more": False,
                },
            )

    async def _fake_estimate_chat_completion_cost(self, **kwargs):
        _ = self
        pricing_calls.append(str(kwargs))

    async def _fake_reserve(self, **kwargs):
        _ = self
        quota_calls.append(str(kwargs))

    monkeypatch.setattr(main_module, "_get_owned_active_response_reference", _fake_get_reference)
    monkeypatch.setattr(main_module, "_provider_route_for_reference", _fake_route_for_reference)
    monkeypatch.setattr(main_module, "get_provider_adapter", lambda route, settings: _FakeAdapter())
    monkeypatch.setattr(
        main_module.PricingService,
        "estimate_chat_completion_cost",
        _fake_estimate_chat_completion_cost,
    )
    monkeypatch.setattr(main_module.QuotaService, "reserve_for_chat_completion", _fake_reserve)

    response = TestClient(app).get(
        "/v1/responses/resp_owned/input_items"
        "?after=item_1&include=message.input_image.image_url&limit=25&order=asc"
    )

    assert response.status_code == 200
    assert response.json() == {
        "object": "list",
        "data": [],
        "first_id": None,
        "last_id": None,
        "has_more": False,
    }
    assert provider_calls == ["resp_owned"]
    assert pricing_calls == []
    assert quota_calls == []


def test_response_input_items_missing_or_non_owned_reference_returns_404_before_provider(
    monkeypatch,
) -> None:
    import slaif_gateway.services.responses_gateway as main_module

    app = create_app()
    _wire_auth_and_db(
        monkeypatch,
        app,
        _fake_authenticated_gateway_key(
            allowed_endpoints=("GET /v1/responses/{response_id}/input_items",)
        ),
    )
    provider_calls: list[str] = []

    async def _fake_get_reference(*, response_id, authenticated_key, request):
        _ = (response_id, authenticated_key, request)
        return None

    def _fake_get_provider_adapter(route, settings):
        _ = (route, settings)
        provider_calls.append("provider")
        raise AssertionError("provider adapter should not be called")

    monkeypatch.setattr(main_module, "_get_owned_active_response_reference", _fake_get_reference)
    monkeypatch.setattr(main_module, "get_provider_adapter", _fake_get_provider_adapter)

    response = TestClient(app).get("/v1/responses/resp_missing/input_items")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "response_not_found"
    assert provider_calls == []


def test_conversation_create_requires_explicit_endpoint_permission(monkeypatch) -> None:
    app = create_app()
    _wire_auth_and_db(
        monkeypatch,
        app,
        _fake_authenticated_gateway_key(allowed_endpoints=("/v1/responses",)),
    )

    response = TestClient(app).post("/v1/conversations", json={})

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "endpoint_not_allowed"


def test_conversation_create_empty_body_proxies_and_persists_without_generation_accounting(
    monkeypatch,
) -> None:
    import slaif_gateway.services.responses_gateway as main_module

    app = create_app()
    auth = _fake_authenticated_gateway_key(allowed_endpoints=("/v1/conversations",))
    _wire_auth_and_db(monkeypatch, app, auth)
    persisted: list[tuple[str, str]] = []
    pricing_calls: list[str] = []
    quota_calls: list[str] = []

    async def _fake_route_for_new_conversation(*, authenticated_key, request):
        _ = request
        assert authenticated_key.gateway_key_id == auth.gateway_key_id
        return SimpleNamespace(provider="openai")

    class _FakeAdapter:
        async def create_conversation(self, request):
            assert request.endpoint == "conversations.create"
            assert request.body == {}
            return ProviderResponse(
                provider=request.provider,
                upstream_model="",
                status_code=200,
                json_body={"id": "conv_owned", "object": "conversation"},
                upstream_request_id="req-conversation-create",
            )

    async def _fake_persist(*, authenticated_key, provider, provider_response, request):
        _ = request
        assert authenticated_key.gateway_key_id == auth.gateway_key_id
        persisted.append((provider, provider_response.json_body["id"]))

    async def _fake_estimate_chat_completion_cost(self, **kwargs):
        _ = self
        pricing_calls.append(str(kwargs))

    async def _fake_reserve(self, **kwargs):
        _ = self
        quota_calls.append(str(kwargs))

    monkeypatch.setattr(main_module, "_provider_route_for_new_conversation", _fake_route_for_new_conversation)
    monkeypatch.setattr(main_module, "_persist_conversation_reference", _fake_persist)
    monkeypatch.setattr(main_module, "get_provider_adapter", lambda route, settings: _FakeAdapter())
    monkeypatch.setattr(
        main_module.PricingService,
        "estimate_chat_completion_cost",
        _fake_estimate_chat_completion_cost,
    )
    monkeypatch.setattr(main_module.QuotaService, "reserve_for_chat_completion", _fake_reserve)

    response = TestClient(app).post("/v1/conversations", json={})

    assert response.status_code == 200
    assert response.json() == {"id": "conv_owned", "object": "conversation"}
    assert persisted == [("openai", "conv_owned")]
    assert pricing_calls == []
    assert quota_calls == []


def test_conversation_create_rejects_initial_items_in_first_slice(monkeypatch) -> None:
    app = create_app()
    _wire_auth_and_db(
        monkeypatch,
        app,
        _fake_authenticated_gateway_key(allowed_endpoints=("/v1/conversations",)),
    )

    response = TestClient(app).post(
        "/v1/conversations",
        json={"items": [{"role": "user", "content": "must not be stored"}]},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "conversation_create_fields_not_supported"


def test_conversation_update_requires_explicit_endpoint_permission(monkeypatch) -> None:
    app = create_app()
    _wire_auth_and_db(
        monkeypatch,
        app,
        _fake_authenticated_gateway_key(allowed_endpoints=("/v1/conversations",)),
    )

    response = TestClient(app).post(
        "/v1/conversations/conv_owned",
        json={"metadata": {"course": "slaif"}},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "endpoint_not_allowed"


def test_conversation_update_owned_reference_proxies_metadata_without_generation_accounting(
    monkeypatch,
) -> None:
    import slaif_gateway.services.responses_gateway as main_module

    app = create_app()
    auth = _fake_authenticated_gateway_key(
        allowed_endpoints=("POST /v1/conversations/{conversation_id}",)
    )
    _wire_auth_and_db(monkeypatch, app, auth)
    pricing_calls: list[str] = []
    quota_calls: list[str] = []
    provider_calls: list[tuple[str, dict[str, object], str]] = []

    async def _fake_get_reference(*, conversation_id, authenticated_key, request):
        _ = request
        assert authenticated_key.gateway_key_id == auth.gateway_key_id
        assert conversation_id == "conv_owned"
        return SimpleNamespace(
            id=uuid.uuid4(),
            provider="openai",
            provider_conversation_id="conv_provider",
            route_id=None,
        )

    async def _fake_route_for_reference(reference, *, request):
        _ = request
        assert reference.provider == "openai"
        return SimpleNamespace(provider="openai")

    class _FakeAdapter:
        async def update_conversation(self, request, *, conversation_id):
            provider_calls.append((conversation_id, request.body, request.endpoint))
            return ProviderResponse(
                provider=request.provider,
                upstream_model="",
                status_code=200,
                json_body={"id": conversation_id, "object": "conversation"},
            )

    async def _fake_estimate_chat_completion_cost(self, **kwargs):
        _ = self
        pricing_calls.append(str(kwargs))

    async def _fake_reserve(self, **kwargs):
        _ = self
        quota_calls.append(str(kwargs))

    monkeypatch.setattr(main_module, "_get_owned_active_conversation_reference", _fake_get_reference)
    monkeypatch.setattr(main_module, "_provider_route_for_conversation_reference", _fake_route_for_reference)
    monkeypatch.setattr(main_module, "get_provider_adapter", lambda route, settings: _FakeAdapter())
    monkeypatch.setattr(
        main_module.PricingService,
        "estimate_chat_completion_cost",
        _fake_estimate_chat_completion_cost,
    )
    monkeypatch.setattr(main_module.QuotaService, "reserve_for_chat_completion", _fake_reserve)

    response = TestClient(app).post(
        "/v1/conversations/conv_owned",
        json={"metadata": {"course": "slaif"}},
    )

    assert response.status_code == 200
    assert response.json() == {"id": "conv_provider", "object": "conversation"}
    assert provider_calls == [
        ("conv_provider", {"metadata": {"course": "slaif"}}, "conversations.update")
    ]
    assert pricing_calls == []
    assert quota_calls == []


def test_conversation_update_missing_or_non_owned_returns_404_before_provider(monkeypatch) -> None:
    import slaif_gateway.services.responses_gateway as main_module

    app = create_app()
    _wire_auth_and_db(
        monkeypatch,
        app,
        _fake_authenticated_gateway_key(
            allowed_endpoints=("POST /v1/conversations/{conversation_id}",)
        ),
    )
    provider_calls: list[str] = []

    async def _fake_get_reference(*, conversation_id, authenticated_key, request):
        _ = (conversation_id, authenticated_key, request)
        return None

    def _fake_get_provider_adapter(route, settings):
        _ = (route, settings)
        provider_calls.append("provider")
        raise AssertionError("provider adapter should not be called")

    monkeypatch.setattr(main_module, "_get_owned_active_conversation_reference", _fake_get_reference)
    monkeypatch.setattr(main_module, "get_provider_adapter", _fake_get_provider_adapter)

    response = TestClient(app).post(
        "/v1/conversations/conv_missing",
        json={"metadata": {"course": "slaif"}},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "conversation_not_found"
    assert provider_calls == []


def test_conversation_retrieve_owned_reference_proxies_without_generation_accounting(monkeypatch) -> None:
    import slaif_gateway.services.responses_gateway as main_module

    app = create_app()
    auth = _fake_authenticated_gateway_key(
        allowed_endpoints=("GET /v1/conversations/{conversation_id}",)
    )
    _wire_auth_and_db(monkeypatch, app, auth)
    pricing_calls: list[str] = []
    quota_calls: list[str] = []
    provider_calls: list[str] = []

    async def _fake_get_reference(*, conversation_id, authenticated_key, request):
        _ = request
        assert authenticated_key.gateway_key_id == auth.gateway_key_id
        assert conversation_id == "conv_owned"
        return SimpleNamespace(
            id=uuid.uuid4(),
            provider="openai",
            provider_conversation_id=conversation_id,
            route_id=None,
        )

    async def _fake_route_for_reference(reference, *, request):
        _ = (reference, request)
        return SimpleNamespace(provider="openai")

    class _FakeAdapter:
        async def retrieve_conversation(self, request, *, conversation_id):
            provider_calls.append(conversation_id)
            assert request.endpoint == "conversations.retrieve"
            return ProviderResponse(
                provider=request.provider,
                upstream_model="",
                status_code=200,
                json_body={"id": conversation_id, "object": "conversation"},
            )

    async def _fake_estimate_chat_completion_cost(self, **kwargs):
        _ = self
        pricing_calls.append(str(kwargs))

    async def _fake_reserve(self, **kwargs):
        _ = self
        quota_calls.append(str(kwargs))

    monkeypatch.setattr(main_module, "_get_owned_active_conversation_reference", _fake_get_reference)
    monkeypatch.setattr(main_module, "_provider_route_for_conversation_reference", _fake_route_for_reference)
    monkeypatch.setattr(main_module, "get_provider_adapter", lambda route, settings: _FakeAdapter())
    monkeypatch.setattr(
        main_module.PricingService,
        "estimate_chat_completion_cost",
        _fake_estimate_chat_completion_cost,
    )
    monkeypatch.setattr(main_module.QuotaService, "reserve_for_chat_completion", _fake_reserve)

    response = TestClient(app).get("/v1/conversations/conv_owned")

    assert response.status_code == 200
    assert response.json() == {"id": "conv_owned", "object": "conversation"}
    assert provider_calls == ["conv_owned"]
    assert pricing_calls == []
    assert quota_calls == []


def test_conversation_retrieve_missing_or_non_owned_returns_404_before_provider(
    monkeypatch,
) -> None:
    import slaif_gateway.services.responses_gateway as main_module

    app = create_app()
    _wire_auth_and_db(
        monkeypatch,
        app,
        _fake_authenticated_gateway_key(allowed_endpoints=("GET /v1/conversations/{conversation_id}",)),
    )
    provider_calls: list[str] = []

    async def _fake_get_reference(*, conversation_id, authenticated_key, request):
        _ = (conversation_id, authenticated_key, request)
        return None

    def _fake_get_provider_adapter(route, settings):
        _ = (route, settings)
        provider_calls.append("provider")
        raise AssertionError("provider adapter should not be called")

    monkeypatch.setattr(main_module, "_get_owned_active_conversation_reference", _fake_get_reference)
    monkeypatch.setattr(main_module, "get_provider_adapter", _fake_get_provider_adapter)

    response = TestClient(app).get("/v1/conversations/conv_missing")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "conversation_not_found"
    assert provider_calls == []


def test_conversation_delete_owned_reference_marks_deleted_without_generation_accounting(monkeypatch) -> None:
    import slaif_gateway.services.responses_gateway as main_module

    app = create_app()
    auth = _fake_authenticated_gateway_key(
        allowed_endpoints=("DELETE /v1/conversations/{conversation_id}",)
    )
    _wire_auth_and_db(monkeypatch, app, auth)
    deleted: list[uuid.UUID] = []
    pricing_calls: list[str] = []
    quota_calls: list[str] = []
    reference_id = uuid.uuid4()

    async def _fake_get_reference(*, conversation_id, authenticated_key, request):
        _ = request
        assert authenticated_key.gateway_key_id == auth.gateway_key_id
        assert conversation_id == "conv_owned"
        return SimpleNamespace(
            id=reference_id,
            provider="openai",
            provider_conversation_id=conversation_id,
            route_id=None,
        )

    async def _fake_route_for_reference(reference, *, request):
        _ = (reference, request)
        return SimpleNamespace(provider="openai")

    async def _fake_mark_deleted(*, reference_id, request):
        _ = request
        deleted.append(reference_id)

    class _FakeAdapter:
        async def delete_conversation(self, request, *, conversation_id):
            assert request.endpoint == "conversations.delete"
            return ProviderResponse(
                provider=request.provider,
                upstream_model="",
                status_code=200,
                json_body={"id": conversation_id, "object": "conversation.deleted", "deleted": True},
            )

    async def _fake_estimate_chat_completion_cost(self, **kwargs):
        _ = self
        pricing_calls.append(str(kwargs))

    async def _fake_reserve(self, **kwargs):
        _ = self
        quota_calls.append(str(kwargs))

    monkeypatch.setattr(main_module, "_get_owned_active_conversation_reference", _fake_get_reference)
    monkeypatch.setattr(main_module, "_provider_route_for_conversation_reference", _fake_route_for_reference)
    monkeypatch.setattr(main_module, "_mark_conversation_reference_deleted", _fake_mark_deleted)
    monkeypatch.setattr(main_module, "get_provider_adapter", lambda route, settings: _FakeAdapter())
    monkeypatch.setattr(
        main_module.PricingService,
        "estimate_chat_completion_cost",
        _fake_estimate_chat_completion_cost,
    )
    monkeypatch.setattr(main_module.QuotaService, "reserve_for_chat_completion", _fake_reserve)

    response = TestClient(app).delete("/v1/conversations/conv_owned")

    assert response.status_code == 200
    assert response.json()["object"] == "conversation.deleted"
    assert deleted == [reference_id]
    assert pricing_calls == []
    assert quota_calls == []


def test_conversation_items_require_explicit_endpoint_permission(monkeypatch) -> None:
    app = create_app()
    _wire_auth_and_db(
        monkeypatch,
        app,
        _fake_authenticated_gateway_key(allowed_endpoints=("/v1/conversations",)),
    )
    client = TestClient(app)

    create_response = client.post("/v1/conversations/conv_owned/items", json={"items": []})
    list_response = client.get("/v1/conversations/conv_owned/items")
    retrieve_response = client.get("/v1/conversations/conv_owned/items/msg_1")
    delete_response = client.delete("/v1/conversations/conv_owned/items/msg_1")

    assert create_response.status_code == 403
    assert list_response.status_code == 403
    assert retrieve_response.status_code == 403
    assert delete_response.status_code == 403


def test_conversation_item_create_owned_reference_proxies_text_items_without_generation_accounting(
    monkeypatch,
) -> None:
    import slaif_gateway.services.responses_gateway as main_module

    app = create_app()
    auth = _fake_authenticated_gateway_key(
        allowed_endpoints=("POST /v1/conversations/{conversation_id}/items",)
    )
    _wire_auth_and_db(monkeypatch, app, auth)
    pricing_calls: list[str] = []
    quota_calls: list[str] = []
    provider_calls: list[dict[str, object]] = []

    async def _fake_get_reference(*, conversation_id, authenticated_key, request):
        _ = request
        assert authenticated_key.gateway_key_id == auth.gateway_key_id
        assert conversation_id == "conv_owned"
        return SimpleNamespace(
            id=uuid.uuid4(),
            provider="openai",
            provider_conversation_id="conv_provider",
            route_id=None,
        )

    async def _fake_route_for_reference(reference, *, request):
        _ = (reference, request)
        return SimpleNamespace(provider="openai")

    class _FakeAdapter:
        async def create_conversation_items(self, request, *, conversation_id):
            assert conversation_id == "conv_provider"
            assert request.endpoint == "conversations.items.create"
            provider_calls.append(request.body)
            return ProviderResponse(
                provider=request.provider,
                upstream_model="",
                status_code=200,
                json_body={"object": "list", "data": [{"id": "msg_1", "type": "message"}]},
            )

    async def _fake_estimate_chat_completion_cost(self, **kwargs):
        _ = self
        pricing_calls.append(str(kwargs))

    async def _fake_reserve(self, **kwargs):
        _ = self
        quota_calls.append(str(kwargs))

    monkeypatch.setattr(main_module, "_get_owned_active_conversation_reference", _fake_get_reference)
    monkeypatch.setattr(main_module, "_provider_route_for_conversation_reference", _fake_route_for_reference)
    monkeypatch.setattr(main_module, "get_provider_adapter", lambda route, settings: _FakeAdapter())
    monkeypatch.setattr(
        main_module.PricingService,
        "estimate_chat_completion_cost",
        _fake_estimate_chat_completion_cost,
    )
    monkeypatch.setattr(main_module.QuotaService, "reserve_for_chat_completion", _fake_reserve)

    response = TestClient(app).post(
        "/v1/conversations/conv_owned/items",
        json={
            "items": [
                {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": "hello"}],
                }
            ]
        },
    )

    assert response.status_code == 200
    assert response.json()["object"] == "list"
    assert provider_calls == [
        {
            "items": [
                {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": "hello"}],
                }
            ]
        }
    ]
    assert pricing_calls == []
    assert quota_calls == []


def test_conversation_item_create_rejects_tool_and_media_payloads(monkeypatch) -> None:
    app = create_app()
    _wire_auth_and_db(
        monkeypatch,
        app,
        _fake_authenticated_gateway_key(
            allowed_endpoints=("POST /v1/conversations/{conversation_id}/items",)
        ),
    )
    import slaif_gateway.services.responses_gateway as main_module

    async def _fake_get_reference(*, conversation_id, authenticated_key, request):
        _ = (conversation_id, authenticated_key, request)
        return SimpleNamespace(
            id=uuid.uuid4(),
            provider="openai",
            provider_conversation_id="conv_provider",
            route_id=None,
        )

    monkeypatch.setattr(main_module, "_get_owned_active_conversation_reference", _fake_get_reference)
    client = TestClient(app)

    for item in (
        {"type": "function_call_output", "call_id": "call_1", "output": "result"},
        {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_image", "image_url": "https://example.test/image.png"}],
        },
        {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_file", "file_url": "https://example.test/file.pdf"}],
        },
    ):
        response = client.post("/v1/conversations/conv_owned/items", json={"items": [item]})
        assert response.status_code == 400
        assert response.json()["error"]["code"] in {
            "conversation_item_create_item_not_supported",
            "conversation_item_create_content_not_supported",
        }


def test_conversation_items_list_retrieve_delete_owned_reference_proxy_without_generation_accounting(
    monkeypatch,
) -> None:
    import slaif_gateway.services.responses_gateway as main_module

    app = create_app()
    auth = _fake_authenticated_gateway_key(
        allowed_endpoints=(
            "GET /v1/conversations/{conversation_id}/items",
            "GET /v1/conversations/{conversation_id}/items/{item_id}",
            "DELETE /v1/conversations/{conversation_id}/items/{item_id}",
        )
    )
    _wire_auth_and_db(monkeypatch, app, auth)
    pricing_calls: list[str] = []
    quota_calls: list[str] = []
    provider_calls: list[tuple[str, dict[str, object]]] = []

    async def _fake_get_reference(*, conversation_id, authenticated_key, request):
        _ = request
        assert authenticated_key.gateway_key_id == auth.gateway_key_id
        assert conversation_id == "conv_owned"
        return SimpleNamespace(
            id=uuid.uuid4(),
            provider="openai",
            provider_conversation_id="conv_provider",
            route_id=None,
        )

    async def _fake_route_for_reference(reference, *, request):
        _ = (reference, request)
        return SimpleNamespace(provider="openai")

    class _FakeAdapter:
        async def list_conversation_items(self, request, *, conversation_id):
            assert conversation_id == "conv_provider"
            assert request.endpoint == "conversations.items.list"
            provider_calls.append(("list", request.body))
            return ProviderResponse(
                provider=request.provider,
                upstream_model="",
                status_code=200,
                json_body={"object": "list", "data": [], "has_more": False},
            )

        async def retrieve_conversation_item(self, request, *, conversation_id, item_id):
            assert conversation_id == "conv_provider"
            assert item_id == "msg_1"
            assert request.endpoint == "conversations.items.retrieve"
            provider_calls.append(("retrieve", request.body))
            return ProviderResponse(
                provider=request.provider,
                upstream_model="",
                status_code=200,
                json_body={"id": item_id, "type": "message", "role": "user"},
            )

        async def delete_conversation_item(self, request, *, conversation_id, item_id):
            assert conversation_id == "conv_provider"
            assert item_id == "msg_1"
            assert request.endpoint == "conversations.items.delete"
            provider_calls.append(("delete", request.body))
            return ProviderResponse(
                provider=request.provider,
                upstream_model="",
                status_code=200,
                json_body={"id": "conv_provider", "object": "conversation"},
            )

    async def _fake_estimate_chat_completion_cost(self, **kwargs):
        _ = self
        pricing_calls.append(str(kwargs))

    async def _fake_reserve(self, **kwargs):
        _ = self
        quota_calls.append(str(kwargs))

    monkeypatch.setattr(main_module, "_get_owned_active_conversation_reference", _fake_get_reference)
    monkeypatch.setattr(main_module, "_provider_route_for_conversation_reference", _fake_route_for_reference)
    monkeypatch.setattr(main_module, "get_provider_adapter", lambda route, settings: _FakeAdapter())
    monkeypatch.setattr(
        main_module.PricingService,
        "estimate_chat_completion_cost",
        _fake_estimate_chat_completion_cost,
    )
    monkeypatch.setattr(main_module.QuotaService, "reserve_for_chat_completion", _fake_reserve)

    client = TestClient(app)
    listed = client.get(
        "/v1/conversations/conv_owned/items"
        "?after=msg_0&before=msg_9&limit=10&order=asc&include=message.input_image.image_url"
    )
    retrieved = client.get(
        "/v1/conversations/conv_owned/items/msg_1?include=message.input_image.image_url"
    )
    deleted = client.delete("/v1/conversations/conv_owned/items/msg_1")

    assert listed.status_code == 200
    assert retrieved.status_code == 200
    assert deleted.status_code == 200
    assert provider_calls == [
        (
            "list",
            {
                "after": "msg_0",
                "before": "msg_9",
                "include": ["message.input_image.image_url"],
                "limit": 10,
                "order": "asc",
            },
        ),
        ("retrieve", {"include": ["message.input_image.image_url"]}),
        ("delete", {}),
    ]
    assert pricing_calls == []
    assert quota_calls == []


def test_conversation_items_missing_or_non_owned_reference_returns_404_before_provider(
    monkeypatch,
) -> None:
    import slaif_gateway.services.responses_gateway as main_module

    app = create_app()
    _wire_auth_and_db(
        monkeypatch,
        app,
        _fake_authenticated_gateway_key(
            allowed_endpoints=(
                "GET /v1/conversations/{conversation_id}/items",
                "GET /v1/conversations/{conversation_id}/items/{item_id}",
                "DELETE /v1/conversations/{conversation_id}/items/{item_id}",
            )
        ),
    )
    provider_calls: list[str] = []

    async def _fake_get_reference(*, conversation_id, authenticated_key, request):
        _ = (conversation_id, authenticated_key, request)
        return None

    def _fake_get_provider_adapter(route, settings):
        _ = (route, settings)
        provider_calls.append("provider")
        raise AssertionError("provider adapter should not be called")

    monkeypatch.setattr(main_module, "_get_owned_active_conversation_reference", _fake_get_reference)
    monkeypatch.setattr(main_module, "get_provider_adapter", _fake_get_provider_adapter)
    client = TestClient(app)

    for response in (
        client.get("/v1/conversations/conv_missing/items"),
        client.get("/v1/conversations/conv_missing/items/msg_1"),
        client.delete("/v1/conversations/conv_missing/items/msg_1"),
    ):
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "conversation_not_found"
    assert provider_calls == []


def test_conversation_items_query_params_are_validated(monkeypatch) -> None:
    import slaif_gateway.services.responses_gateway as main_module

    app = create_app()
    _wire_auth_and_db(
        monkeypatch,
        app,
        _fake_authenticated_gateway_key(
            allowed_endpoints=("GET /v1/conversations/{conversation_id}/items",)
        ),
    )

    async def _fake_get_reference(*, conversation_id, authenticated_key, request):
        _ = (conversation_id, authenticated_key, request)
        return SimpleNamespace(
            id=uuid.uuid4(),
            provider="openai",
            provider_conversation_id="conv_provider",
            route_id=None,
        )

    monkeypatch.setattr(main_module, "_get_owned_active_conversation_reference", _fake_get_reference)
    client = TestClient(app)

    for query in (
        "?limit=0",
        "?limit=101",
        "?order=newest",
        "?after=" + ("x" * 257),
        "?unknown=1",
        "?include=web_search_call.action.sources",
    ):
        response = client.get(f"/v1/conversations/conv_owned/items{query}")
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "invalid_conversation_items_query"


def test_response_delete_owned_reference_marks_deleted_without_generation_accounting(monkeypatch) -> None:
    import slaif_gateway.services.responses_gateway as main_module

    app = create_app()
    auth = _fake_authenticated_gateway_key(allowed_endpoints=("DELETE /v1/responses/{response_id}",))
    _wire_auth_and_db(monkeypatch, app, auth)
    deleted: list[uuid.UUID] = []
    pricing_calls: list[str] = []
    quota_calls: list[str] = []
    reference_id = uuid.uuid4()

    async def _fake_get_reference(*, response_id, authenticated_key, request):
        _ = (authenticated_key, request)
        return SimpleNamespace(
            id=reference_id,
            provider="openai",
            provider_response_id=response_id,
            upstream_model="gpt-5.2",
        )

    async def _fake_route_for_reference(reference, *, request):
        _ = (reference, request)
        return SimpleNamespace(provider="openai")

    class _FakeAdapter:
        async def delete_response(self, request, *, response_id):
            assert request.endpoint == "responses.delete"
            assert response_id == "resp_delete"
            return ProviderResponse(
                provider=request.provider,
                upstream_model=request.upstream_model,
                status_code=200,
                json_body={"id": response_id, "object": "response.deleted", "deleted": True},
            )

    async def _fake_mark_deleted(*, reference_id, request):
        _ = request
        deleted.append(reference_id)

    async def _fake_estimate_chat_completion_cost(self, **kwargs):
        _ = self
        pricing_calls.append(str(kwargs))

    async def _fake_reserve(self, **kwargs):
        _ = self
        quota_calls.append(str(kwargs))

    monkeypatch.setattr(main_module, "_get_owned_active_response_reference", _fake_get_reference)
    monkeypatch.setattr(main_module, "_provider_route_for_reference", _fake_route_for_reference)
    monkeypatch.setattr(main_module, "_mark_response_reference_deleted", _fake_mark_deleted)
    monkeypatch.setattr(main_module, "get_provider_adapter", lambda route, settings: _FakeAdapter())
    monkeypatch.setattr(
        main_module.PricingService,
        "estimate_chat_completion_cost",
        _fake_estimate_chat_completion_cost,
    )
    monkeypatch.setattr(main_module.QuotaService, "reserve_for_chat_completion", _fake_reserve)

    response = TestClient(app).delete("/v1/responses/resp_delete")

    assert response.status_code == 200
    assert response.json() == {"id": "resp_delete", "object": "response.deleted", "deleted": True}
    assert deleted == [reference_id]
    assert pricing_calls == []
    assert quota_calls == []


def test_responses_input_token_count_forwards_without_generation_quota_or_ledger(monkeypatch) -> None:
    import slaif_gateway.services.responses_gateway as main_module

    app = create_app()
    _wire_auth_and_db(
        monkeypatch,
        app,
        _fake_authenticated_gateway_key(allowed_endpoints=("/v1/responses/input_tokens",)),
    )
    route_calls: list[tuple[str, str]] = []
    pricing_calls: list[str] = []
    quota_calls: list[str] = []
    finalize_calls: list[str] = []
    provider_bodies: list[dict[str, object]] = []

    async def _fake_resolve_model(self, requested_model, authenticated_key, *, endpoint="/v1/chat/completions"):
        _ = (self, authenticated_key)
        route_calls.append((requested_model, endpoint))
        return _route_result(requested_model, responses_input_token_count=True)

    async def _fake_estimate_chat_completion_cost(self, **kwargs):
        _ = self
        pricing_calls.append(str(kwargs))

    async def _fake_reserve(self, **kwargs):
        _ = self
        quota_calls.append(str(kwargs))

    async def _fake_finalize_successful_response(self, *args, **kwargs):
        _ = (self, args, kwargs)
        finalize_calls.append("finalize")

    class _FakeAdapter:
        async def forward_response_input_tokens(self, request):
            assert request.endpoint == "responses.input_tokens"
            provider_bodies.append(dict(request.body))
            return ProviderResponse(
                provider=request.provider,
                upstream_model=request.upstream_model,
                status_code=200,
                json_body={"object": "response.input_tokens", "input_tokens": 123},
            )

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
    monkeypatch.setattr(main_module, "get_provider_adapter", lambda route, settings: _FakeAdapter())

    response = TestClient(app).post(
        "/v1/responses/input_tokens",
        json={
            "model": "classroom-responses",
            "input": "hello",
            "truncation": "disabled",
        },
    )

    assert response.status_code == 200
    assert response.json() == {"object": "response.input_tokens", "input_tokens": 123}
    assert route_calls == [("classroom-responses", "/v1/responses/input_tokens")]
    assert provider_bodies == [
        {"model": "gpt-5.2", "input": "hello", "truncation": "disabled"}
    ]
    assert pricing_calls == []
    assert quota_calls == []
    assert finalize_calls == []


def test_responses_permission_does_not_allow_input_token_count(monkeypatch) -> None:
    app = create_app()
    _wire_auth_and_db(
        monkeypatch,
        app,
        _fake_authenticated_gateway_key(allowed_endpoints=("/v1/responses",)),
    )

    response = TestClient(app).post(
        "/v1/responses/input_tokens",
        json={"model": "classroom-responses", "input": "hello"},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "endpoint_not_allowed"


def test_responses_input_token_count_rejects_missing_route_capability_before_provider(
    monkeypatch,
) -> None:
    import slaif_gateway.services.responses_gateway as main_module

    app = create_app()
    _wire_auth_and_db(
        monkeypatch,
        app,
        _fake_authenticated_gateway_key(allowed_endpoints=("/v1/responses/input_tokens",)),
    )
    provider_calls: list[str] = []

    async def _fake_resolve_model(self, requested_model, authenticated_key, *, endpoint="/v1/chat/completions"):
        _ = (self, authenticated_key, endpoint)
        return _route_result(requested_model)

    def _fake_get_provider_adapter(route, settings):
        _ = (route, settings)
        provider_calls.append("provider")
        raise AssertionError("provider adapter should not be called")

    monkeypatch.setattr(main_module.RouteResolutionService, "resolve_model", _fake_resolve_model)
    monkeypatch.setattr(main_module, "get_provider_adapter", _fake_get_provider_adapter)

    response = TestClient(app).post(
        "/v1/responses/input_tokens",
        json={"model": "classroom-responses", "input": "hello"},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "responses_input_token_count_capability_not_supported"
    assert provider_calls == []


def test_responses_input_token_count_rejects_malformed_provider_response(monkeypatch) -> None:
    import slaif_gateway.services.responses_gateway as main_module

    app = create_app()
    _wire_auth_and_db(
        monkeypatch,
        app,
        _fake_authenticated_gateway_key(allowed_endpoints=("/v1/responses/input_tokens",)),
    )

    async def _fake_resolve_model(self, requested_model, authenticated_key, *, endpoint="/v1/chat/completions"):
        _ = (self, authenticated_key, endpoint)
        return _route_result(requested_model, responses_input_token_count=True)

    class _FakeAdapter:
        async def forward_response_input_tokens(self, request):
            _ = request
            return ProviderResponse(
                provider="openai",
                upstream_model="gpt-5.2",
                status_code=200,
                json_body={"object": "response.input_tokens", "input_tokens": "123"},
            )

    monkeypatch.setattr(main_module.RouteResolutionService, "resolve_model", _fake_resolve_model)
    monkeypatch.setattr(main_module, "get_provider_adapter", lambda route, settings: _FakeAdapter())

    response = TestClient(app).post(
        "/v1/responses/input_tokens",
        json={"model": "classroom-responses", "input": "hello"},
    )

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "provider_response_invalid"


def test_responses_compact_permission_is_explicit(monkeypatch) -> None:
    app = create_app()
    _wire_auth_and_db(
        monkeypatch,
        app,
        _fake_authenticated_gateway_key(allowed_endpoints=("/v1/responses",)),
    )

    response = TestClient(app).post(
        "/v1/responses/compact",
        json={"model": "classroom-responses", "input": "compact this"},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "endpoint_not_allowed"


def test_responses_compact_reserves_and_finalizes_with_endpoint_specific_pricing(monkeypatch) -> None:
    import slaif_gateway.services.responses_gateway as main_module

    app = create_app()
    _wire_auth_and_db(
        monkeypatch,
        app,
        _fake_authenticated_gateway_key(allowed_endpoints=("/v1/responses/compact",)),
    )
    route_calls: list[tuple[str, str]] = []
    pricing_calls: list[str] = []
    reserve_calls: list[str] = []
    finalize_calls: list[str] = []
    provider_bodies: list[dict[str, object]] = []

    async def _fake_resolve_model(self, requested_model, authenticated_key, *, endpoint="/v1/chat/completions"):
        _ = (self, authenticated_key)
        route_calls.append((requested_model, endpoint))
        return _route_result(requested_model, responses_compact=True)

    async def _fake_estimate_chat_completion_cost(self, *, route, policy, endpoint="chat.completions", at=None):
        _ = (self, route, at)
        pricing_calls.append(endpoint)
        assert policy.effective_output_tokens == 12000
        return _estimate()

    async def _fake_reserve(
        self,
        *,
        authenticated_key,
        route,
        policy,
        cost_estimate,
        request_id,
        endpoint="/v1/chat/completions",
        now=None,
    ):
        _ = (self, route, policy, cost_estimate, now)
        reserve_calls.append(endpoint)
        return QuotaReservationResult(
            reservation_id=uuid.uuid4(),
            gateway_key_id=authenticated_key.gateway_key_id,
            request_id=request_id,
            reserved_cost_eur=Decimal("0.003"),
            reserved_tokens=50,
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
        provider_completed_usage_ledger_id=None,
        streaming=False,
    ):
        _ = (
            self,
            authenticated_key,
            route,
            policy,
            pricing_estimate,
            provider_response,
            request_id,
            started_at,
            finished_at,
            provider_completed_usage_ledger_id,
            streaming,
        )
        finalize_calls.append(endpoint)
        return FinalizedAccountingResult(
            usage_ledger_id=uuid.uuid4(),
            reservation_id=reservation_id,
            gateway_key_id=authenticated_key.gateway_key_id,
            request_id=request_id,
            estimated_cost_eur=Decimal("0.003"),
            actual_cost_eur=Decimal("0.003"),
            actual_cost_native=Decimal("0.003"),
            native_currency="EUR",
            prompt_tokens=5,
            completion_tokens=2,
            total_tokens=7,
            accounting_status="finalized",
        )

    class _FakeAdapter:
        async def compact_response(self, request):
            assert request.endpoint == "responses.compact"
            provider_bodies.append(dict(request.body))
            return ProviderResponse(
                provider=request.provider,
                upstream_model=request.upstream_model,
                status_code=200,
                json_body={
                    "id": "cmpct_test",
                    "object": "response.compaction",
                    "created_at": 1,
                    "output": [],
                    "usage": {"input_tokens": 5, "output_tokens": 2, "total_tokens": 7},
                },
                usage=ProviderUsage(prompt_tokens=5, completion_tokens=2, total_tokens=7),
            )

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
    monkeypatch.setattr(main_module, "get_provider_adapter", lambda route, settings: _FakeAdapter())

    response = TestClient(app).post(
        "/v1/responses/compact",
        json={
            "model": "classroom-responses",
            "input": [
                {"role": "user", "content": "compact this"},
                {
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "previous"}],
                },
            ],
        },
    )

    assert response.status_code == 200
    assert response.json()["object"] == "response.compaction"
    assert route_calls == [("classroom-responses", "/v1/responses/compact")]
    assert pricing_calls == ["/v1/responses/compact"]
    assert reserve_calls == ["/v1/responses/compact"]
    assert finalize_calls == ["responses.compact"]
    assert provider_bodies == [
        {
            "model": "gpt-5.2",
            "input": [
                {"role": "user", "content": "compact this"},
                {
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "previous"}],
                },
            ],
        }
    ]


def test_responses_compact_rejects_missing_capability_before_provider(monkeypatch) -> None:
    import slaif_gateway.services.responses_gateway as main_module

    app = create_app()
    _wire_auth_and_db(
        monkeypatch,
        app,
        _fake_authenticated_gateway_key(allowed_endpoints=("/v1/responses/compact",)),
    )
    provider_calls: list[str] = []

    async def _fake_resolve_model(self, requested_model, authenticated_key, *, endpoint="/v1/chat/completions"):
        _ = (self, requested_model, authenticated_key, endpoint)
        return _route_result(requested_model)

    def _fake_get_provider_adapter(route, settings):
        _ = (route, settings)
        provider_calls.append("provider")
        raise AssertionError("provider adapter should not be called")

    monkeypatch.setattr(main_module.RouteResolutionService, "resolve_model", _fake_resolve_model)
    monkeypatch.setattr(main_module, "get_provider_adapter", _fake_get_provider_adapter)

    response = TestClient(app).post(
        "/v1/responses/compact",
        json={"model": "classroom-responses", "input": "compact this"},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "responses_compact_capability_not_supported"
    assert provider_calls == []


def test_responses_compact_missing_usage_releases_reservation_and_fails_safely(monkeypatch) -> None:
    import slaif_gateway.services.responses_gateway as main_module

    app = create_app()
    _wire_auth_and_db(
        monkeypatch,
        app,
        _fake_authenticated_gateway_key(allowed_endpoints=("/v1/responses/compact",)),
    )
    released_errors: list[tuple[str, str]] = []

    async def _fake_resolve_model(self, requested_model, authenticated_key, *, endpoint="/v1/chat/completions"):
        _ = (self, authenticated_key, endpoint)
        return _route_result(requested_model, responses_compact=True)

    async def _fake_estimate_chat_completion_cost(self, *, route, policy, endpoint="chat.completions", at=None):
        _ = (self, route, policy, endpoint, at)
        return _estimate()

    async def _fake_reserve(
        self,
        *,
        authenticated_key,
        route,
        policy,
        cost_estimate,
        request_id,
        endpoint="/v1/chat/completions",
        now=None,
    ):
        _ = (self, authenticated_key, route, policy, cost_estimate, endpoint, now)
        return QuotaReservationResult(
            reservation_id=uuid.uuid4(),
            gateway_key_id=authenticated_key.gateway_key_id,
            request_id=request_id,
            reserved_cost_eur=Decimal("0.003"),
            reserved_tokens=50,
            status="pending",
            expires_at=datetime.now(UTC) + timedelta(minutes=15),
        )

    async def _fake_record_failure(
        *,
        reservation,
        authenticated_key,
        route,
        policy_result,
        cost_estimate,
        request_id,
        provider_error,
        request,
        streaming=False,
        provider_endpoint="responses",
    ):
        _ = (
            reservation,
            authenticated_key,
            route,
            policy_result,
            cost_estimate,
            request_id,
            request,
            streaming,
        )
        released_errors.append((provider_error.error_code, provider_endpoint))

    class _FakeAdapter:
        async def compact_response(self, request):
            return ProviderResponse(
                provider=request.provider,
                upstream_model=request.upstream_model,
                status_code=200,
                json_body={
                    "id": "cmpct_missing_usage",
                    "object": "response.compaction",
                    "created_at": 1,
                    "output": [],
                },
                usage=None,
            )

    monkeypatch.setattr(main_module.RouteResolutionService, "resolve_model", _fake_resolve_model)
    monkeypatch.setattr(
        main_module.PricingService,
        "estimate_chat_completion_cost",
        _fake_estimate_chat_completion_cost,
    )
    monkeypatch.setattr(main_module.QuotaService, "reserve_for_chat_completion", _fake_reserve)
    monkeypatch.setattr(main_module, "_record_provider_failure_and_release", _fake_record_failure)
    monkeypatch.setattr(main_module, "get_provider_adapter", lambda route, settings: _FakeAdapter())

    response = TestClient(app).post(
        "/v1/responses/compact",
        json={"model": "classroom-responses", "input": "compact this"},
    )

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "responses_compact_usage_missing"
    assert released_errors == [("responses_compact_usage_missing", "responses.compact")]


def test_responses_function_tools_require_capability_before_rate_pricing_quota_provider(
    monkeypatch,
) -> None:
    import slaif_gateway.services.responses_gateway as main_module

    app = create_app()
    _wire_auth_and_db(monkeypatch, app)
    rate_calls: list[str] = []
    pricing_calls: list[str] = []
    quota_calls: list[str] = []
    provider_calls: list[str] = []

    async def _fake_resolve_model(self, requested_model, authenticated_key, *, endpoint="/v1/chat/completions"):
        _ = (self, authenticated_key, endpoint)
        return _route_result(requested_model)

    async def _fake_reserve_rate_limit(**kwargs):
        rate_calls.append(str(kwargs))

    async def _fake_estimate_chat_completion_cost(self, **kwargs):
        _ = self
        pricing_calls.append(str(kwargs))

    async def _fake_reserve(self, **kwargs):
        _ = self
        quota_calls.append(str(kwargs))

    def _fake_get_provider_adapter(route, settings):
        _ = (route, settings)
        provider_calls.append("provider")
        raise AssertionError("provider adapter should not be called")

    monkeypatch.setattr(main_module.RouteResolutionService, "resolve_model", _fake_resolve_model)
    monkeypatch.setattr(main_module, "_reserve_redis_rate_limit", _fake_reserve_rate_limit)
    monkeypatch.setattr(
        main_module.PricingService,
        "estimate_chat_completion_cost",
        _fake_estimate_chat_completion_cost,
    )
    monkeypatch.setattr(main_module.QuotaService, "reserve_for_chat_completion", _fake_reserve)
    monkeypatch.setattr(main_module, "get_provider_adapter", _fake_get_provider_adapter)

    response = TestClient(app).post(
        "/v1/responses",
        json=_responses_function_tool_request(),
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "responses_function_tool_capability_not_supported"
    assert rate_calls == []
    assert pricing_calls == []
    assert quota_calls == []
    assert provider_calls == []


def test_responses_custom_tools_require_capability_before_rate_pricing_quota_provider(
    monkeypatch,
) -> None:
    import slaif_gateway.services.responses_gateway as main_module

    app = create_app()
    _wire_auth_and_db(monkeypatch, app)
    rate_calls: list[str] = []
    pricing_calls: list[str] = []
    quota_calls: list[str] = []
    provider_calls: list[str] = []

    async def _fake_resolve_model(self, requested_model, authenticated_key, *, endpoint="/v1/chat/completions"):
        _ = (self, authenticated_key, endpoint)
        return _route_result(requested_model, responses_function_tools=True)

    async def _fake_reserve_rate_limit(**kwargs):
        rate_calls.append(str(kwargs))

    async def _fake_estimate_chat_completion_cost(self, **kwargs):
        _ = self
        pricing_calls.append(str(kwargs))

    async def _fake_reserve(self, **kwargs):
        _ = self
        quota_calls.append(str(kwargs))

    def _fake_get_provider_adapter(route, settings):
        _ = (route, settings)
        provider_calls.append("provider")
        raise AssertionError("provider adapter should not be called")

    monkeypatch.setattr(main_module.RouteResolutionService, "resolve_model", _fake_resolve_model)
    monkeypatch.setattr(main_module, "_reserve_redis_rate_limit", _fake_reserve_rate_limit)
    monkeypatch.setattr(
        main_module.PricingService,
        "estimate_chat_completion_cost",
        _fake_estimate_chat_completion_cost,
    )
    monkeypatch.setattr(main_module.QuotaService, "reserve_for_chat_completion", _fake_reserve)
    monkeypatch.setattr(main_module, "get_provider_adapter", _fake_get_provider_adapter)

    response = TestClient(app).post(
        "/v1/responses",
        json=_responses_custom_tool_request(),
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "responses_custom_tool_capability_not_supported"
    assert rate_calls == []
    assert pricing_calls == []
    assert quota_calls == []
    assert provider_calls == []


def test_responses_image_input_requires_capability_before_rate_pricing_quota_provider(
    monkeypatch,
) -> None:
    import slaif_gateway.services.responses_gateway as main_module

    app = create_app()
    _wire_auth_and_db(monkeypatch, app)
    rate_calls: list[str] = []
    pricing_calls: list[str] = []
    quota_calls: list[str] = []
    provider_calls: list[str] = []

    async def _fake_resolve_model(self, requested_model, authenticated_key, *, endpoint="/v1/chat/completions"):
        _ = (self, authenticated_key, endpoint)
        return _route_result(requested_model)

    async def _fake_reserve_rate_limit(**kwargs):
        rate_calls.append(str(kwargs))

    async def _fake_estimate_chat_completion_cost(self, **kwargs):
        _ = self
        pricing_calls.append(str(kwargs))

    async def _fake_reserve(self, **kwargs):
        _ = self
        quota_calls.append(str(kwargs))

    def _fake_get_provider_adapter(route, settings):
        _ = (route, settings)
        provider_calls.append("provider")
        raise AssertionError("provider adapter should not be called")

    monkeypatch.setattr(main_module.RouteResolutionService, "resolve_model", _fake_resolve_model)
    monkeypatch.setattr(main_module, "_reserve_redis_rate_limit", _fake_reserve_rate_limit)
    monkeypatch.setattr(
        main_module.PricingService,
        "estimate_chat_completion_cost",
        _fake_estimate_chat_completion_cost,
    )
    monkeypatch.setattr(main_module.QuotaService, "reserve_for_chat_completion", _fake_reserve)
    monkeypatch.setattr(main_module, "get_provider_adapter", _fake_get_provider_adapter)

    response = TestClient(app).post(
        "/v1/responses",
        json=_responses_image_input_request(),
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "responses_image_input_capability_not_supported"
    assert rate_calls == []
    assert pricing_calls == []
    assert quota_calls == []
    assert provider_calls == []


def test_responses_file_input_requires_capability_before_rate_pricing_quota_provider(
    monkeypatch,
) -> None:
    import slaif_gateway.services.responses_gateway as main_module

    app = create_app()
    _wire_auth_and_db(monkeypatch, app)
    rate_calls: list[str] = []
    pricing_calls: list[str] = []
    quota_calls: list[str] = []
    provider_calls: list[str] = []

    async def _fake_resolve_model(self, requested_model, authenticated_key, *, endpoint="/v1/chat/completions"):
        _ = (self, authenticated_key, endpoint)
        return _route_result(requested_model)

    async def _fake_reserve_rate_limit(**kwargs):
        rate_calls.append(str(kwargs))

    async def _fake_estimate_chat_completion_cost(self, **kwargs):
        _ = self
        pricing_calls.append(str(kwargs))

    async def _fake_reserve(self, **kwargs):
        _ = self
        quota_calls.append(str(kwargs))

    def _fake_get_provider_adapter(route, settings):
        _ = (route, settings)
        provider_calls.append("provider")
        raise AssertionError("provider adapter should not be called")

    monkeypatch.setattr(main_module.RouteResolutionService, "resolve_model", _fake_resolve_model)
    monkeypatch.setattr(main_module, "_reserve_redis_rate_limit", _fake_reserve_rate_limit)
    monkeypatch.setattr(
        main_module.PricingService,
        "estimate_chat_completion_cost",
        _fake_estimate_chat_completion_cost,
    )
    monkeypatch.setattr(main_module.QuotaService, "reserve_for_chat_completion", _fake_reserve)
    monkeypatch.setattr(main_module, "get_provider_adapter", _fake_get_provider_adapter)

    response = TestClient(app).post(
        "/v1/responses",
        json=_responses_file_input_request(),
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "responses_file_input_capability_not_supported"
    assert rate_calls == []
    assert pricing_calls == []
    assert quota_calls == []
    assert provider_calls == []


def test_responses_function_tool_path_forwards_canonical_body_and_finalizes(monkeypatch) -> None:
    import slaif_gateway.services.responses_gateway as main_module

    app = create_app()
    _wire_auth_and_db(monkeypatch, app)
    reserve_calls, release_calls = _wire_successful_route_pricing_quota(monkeypatch)
    finalize_calls: list[str] = []
    seen_bodies: list[dict[str, object]] = []

    async def _fake_resolve_model(self, requested_model, authenticated_key, *, endpoint="/v1/chat/completions"):
        _ = (self, authenticated_key, endpoint)
        return _route_result(requested_model, responses_function_tools=True)

    class _FakeAdapter:
        async def forward_response(self, request):
            seen_bodies.append(dict(request.body))
            return ProviderResponse(
                provider=request.provider,
                upstream_model=request.upstream_model,
                status_code=200,
                json_body={
                    "id": "resp_tool_test",
                    "object": "response",
                    "output": [
                        {
                            "id": "fc_123",
                            "type": "function_call",
                            "call_id": "call_123",
                            "name": "lookup",
                            "arguments": '{"query":"safe"}',
                        }
                    ],
                },
                usage=ProviderUsage(prompt_tokens=5, completion_tokens=6, total_tokens=11),
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
        provider_completed_usage_ledger_id=None,
        streaming=False,
    ):
        _ = (
            self,
            reservation_id,
            authenticated_key,
            policy,
            pricing_estimate,
            provider_response,
            request_id,
            started_at,
            finished_at,
            provider_completed_usage_ledger_id,
            streaming,
        )
        assert endpoint == "responses"
        finalize_calls.append(route.requested_model)
        return FinalizedAccountingResult(
            usage_ledger_id=uuid.uuid4(),
            reservation_id=reservation_id,
            gateway_key_id=authenticated_key.gateway_key_id,
            request_id=request_id,
            estimated_cost_eur=Decimal("0.003"),
            actual_cost_eur=Decimal("0.003"),
            actual_cost_native=Decimal("0.003"),
            native_currency="EUR",
            prompt_tokens=5,
            completion_tokens=6,
            total_tokens=11,
            accounting_status="finalized",
        )

    monkeypatch.setattr(main_module.RouteResolutionService, "resolve_model", _fake_resolve_model)
    monkeypatch.setattr(main_module, "get_provider_adapter", lambda route, settings: _FakeAdapter())
    monkeypatch.setattr(
        main_module.AccountingService,
        "finalize_successful_response",
        _fake_finalize_successful_response,
    )

    response = TestClient(app).post(
        "/v1/responses",
        json=_responses_function_tool_request(),
    )

    assert response.status_code == 200
    assert response.json()["output"][0]["type"] == "function_call"
    assert seen_bodies == [
        {
            "model": "gpt-5.2",
            "input": "hello",
            "max_output_tokens": 20,
            "store": False,
            "tools": [
                {
                    "type": "function",
                    "name": "lookup",
                    "parameters": {"type": "object", "properties": {}},
                }
            ],
            "tool_choice": {"type": "function", "name": "lookup"},
        }
    ]
    assert reserve_calls == ["classroom-responses"]
    assert release_calls == []
    assert finalize_calls == ["classroom-responses"]


def test_responses_custom_tool_path_forwards_canonical_body_and_finalizes(monkeypatch) -> None:
    import slaif_gateway.services.responses_gateway as main_module

    app = create_app()
    _wire_auth_and_db(monkeypatch, app)
    reserve_calls, release_calls = _wire_successful_route_pricing_quota(monkeypatch)
    finalize_calls: list[str] = []
    seen_bodies: list[dict[str, object]] = []

    async def _fake_resolve_model(self, requested_model, authenticated_key, *, endpoint="/v1/chat/completions"):
        _ = (self, authenticated_key, endpoint)
        return _route_result(requested_model, responses_custom_tools=True)

    class _FakeAdapter:
        async def forward_response(self, request):
            seen_bodies.append(dict(request.body))
            return ProviderResponse(
                provider=request.provider,
                upstream_model=request.upstream_model,
                status_code=200,
                json_body={
                    "id": "resp_custom_tool_test",
                    "object": "response",
                    "output": [
                        {
                            "id": "ctc_123",
                            "type": "custom_tool_call",
                            "call_id": "call_123",
                            "name": "emit_regex",
                            "input": "safe",
                        }
                    ],
                },
                usage=ProviderUsage(prompt_tokens=5, completion_tokens=6, total_tokens=11),
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
        provider_completed_usage_ledger_id=None,
        streaming=False,
    ):
        _ = (
            self,
            reservation_id,
            authenticated_key,
            policy,
            pricing_estimate,
            provider_response,
            request_id,
            started_at,
            finished_at,
            provider_completed_usage_ledger_id,
            streaming,
        )
        assert endpoint == "responses"
        finalize_calls.append(route.requested_model)
        return FinalizedAccountingResult(
            usage_ledger_id=uuid.uuid4(),
            reservation_id=reservation_id,
            gateway_key_id=authenticated_key.gateway_key_id,
            request_id=request_id,
            estimated_cost_eur=Decimal("0.003"),
            actual_cost_eur=Decimal("0.003"),
            actual_cost_native=Decimal("0.003"),
            native_currency="EUR",
            prompt_tokens=5,
            completion_tokens=6,
            total_tokens=11,
            accounting_status="finalized",
        )

    monkeypatch.setattr(main_module.RouteResolutionService, "resolve_model", _fake_resolve_model)
    monkeypatch.setattr(main_module, "get_provider_adapter", lambda route, settings: _FakeAdapter())
    monkeypatch.setattr(
        main_module.AccountingService,
        "finalize_successful_response",
        _fake_finalize_successful_response,
    )

    response = TestClient(app).post(
        "/v1/responses",
        json=_responses_custom_tool_request(),
    )

    assert response.status_code == 200
    assert response.json()["output"][0]["type"] == "custom_tool_call"
    assert seen_bodies == [
        {
            "model": "gpt-5.2",
            "input": "hello",
            "max_output_tokens": 20,
            "store": False,
            "tools": [
                {
                    "type": "custom",
                    "name": "emit_regex",
                    "description": "Local custom intent.",
                    "format": {
                        "type": "grammar",
                        "syntax": "regex",
                        "definition": "[a-z]+",
                    },
                }
            ],
            "tool_choice": {"type": "custom", "name": "emit_regex"},
        }
    ]
    assert reserve_calls == ["classroom-responses"]
    assert release_calls == []
    assert finalize_calls == ["classroom-responses"]


def test_responses_image_input_path_forwards_canonical_body_and_finalizes(monkeypatch) -> None:
    import slaif_gateway.services.responses_gateway as main_module

    app = create_app()
    _wire_auth_and_db(monkeypatch, app)
    reserve_calls, release_calls = _wire_successful_route_pricing_quota(monkeypatch)
    finalize_calls: list[str] = []
    seen_bodies: list[dict[str, object]] = []

    async def _fake_resolve_model(self, requested_model, authenticated_key, *, endpoint="/v1/chat/completions"):
        _ = (self, authenticated_key, endpoint)
        return _route_result(requested_model, responses_image_input=True)

    class _FakeAdapter:
        async def forward_response(self, request):
            seen_bodies.append(dict(request.body))
            return ProviderResponse(
                provider=request.provider,
                upstream_model=request.upstream_model,
                status_code=200,
                json_body={
                    "id": "resp_image_test",
                    "object": "response",
                    "output": [{"type": "message", "content": [{"type": "output_text", "text": "A chart."}]}],
                },
                usage=ProviderUsage(prompt_tokens=15, completion_tokens=6, total_tokens=21),
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
        provider_completed_usage_ledger_id=None,
        streaming=False,
    ):
        _ = (
            self,
            reservation_id,
            authenticated_key,
            policy,
            pricing_estimate,
            provider_response,
            request_id,
            started_at,
            finished_at,
            provider_completed_usage_ledger_id,
            streaming,
        )
        assert endpoint == "responses"
        finalize_calls.append(route.requested_model)
        return FinalizedAccountingResult(
            usage_ledger_id=uuid.uuid4(),
            reservation_id=reservation_id,
            gateway_key_id=authenticated_key.gateway_key_id,
            request_id=request_id,
            estimated_cost_eur=Decimal("0.003"),
            actual_cost_eur=Decimal("0.003"),
            actual_cost_native=Decimal("0.003"),
            native_currency="EUR",
            prompt_tokens=15,
            completion_tokens=6,
            total_tokens=21,
            accounting_status="finalized",
        )

    monkeypatch.setattr(main_module.RouteResolutionService, "resolve_model", _fake_resolve_model)
    monkeypatch.setattr(main_module, "get_provider_adapter", lambda route, settings: _FakeAdapter())
    monkeypatch.setattr(
        main_module.AccountingService,
        "finalize_successful_response",
        _fake_finalize_successful_response,
    )

    response = TestClient(app).post(
        "/v1/responses",
        json=_responses_image_input_request(),
    )

    assert response.status_code == 200
    assert response.json()["id"] == "resp_image_test"
    assert seen_bodies == [
        {
            "model": "gpt-5.2",
            "input": [
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": "describe the image"},
                        {
                            "type": "input_image",
                            "image_url": "https://example.test/image.png",
                            "detail": "low",
                        },
                    ],
                }
            ],
            "max_output_tokens": 20,
            "store": False,
        }
    ]
    assert reserve_calls == ["classroom-responses"]
    assert release_calls == []
    assert finalize_calls == ["classroom-responses"]


def test_responses_file_input_path_forwards_canonical_body_and_finalizes(monkeypatch) -> None:
    import slaif_gateway.services.responses_gateway as main_module

    app = create_app()
    _wire_auth_and_db(monkeypatch, app)
    reserve_calls, release_calls = _wire_successful_route_pricing_quota(monkeypatch)
    finalize_calls: list[str] = []
    seen_bodies: list[dict[str, object]] = []

    async def _fake_resolve_model(self, requested_model, authenticated_key, *, endpoint="/v1/chat/completions"):
        _ = (self, authenticated_key, endpoint)
        return _route_result(requested_model, responses_file_input=True)

    class _FakeAdapter:
        async def forward_response(self, request):
            seen_bodies.append(dict(request.body))
            return ProviderResponse(
                provider=request.provider,
                upstream_model=request.upstream_model,
                status_code=200,
                json_body={
                    "id": "resp_file_test",
                    "object": "response",
                    "output": [{"type": "message", "content": [{"type": "output_text", "text": "A PDF."}]}],
                },
                usage=ProviderUsage(prompt_tokens=17, completion_tokens=6, total_tokens=23),
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
        provider_completed_usage_ledger_id=None,
        streaming=False,
    ):
        _ = (
            self,
            reservation_id,
            authenticated_key,
            policy,
            pricing_estimate,
            provider_response,
            request_id,
            started_at,
            finished_at,
            provider_completed_usage_ledger_id,
            streaming,
        )
        assert endpoint == "responses"
        finalize_calls.append(route.requested_model)
        return FinalizedAccountingResult(
            usage_ledger_id=uuid.uuid4(),
            reservation_id=reservation_id,
            gateway_key_id=authenticated_key.gateway_key_id,
            request_id=request_id,
            estimated_cost_eur=Decimal("0.003"),
            actual_cost_eur=Decimal("0.003"),
            actual_cost_native=Decimal("0.003"),
            native_currency="EUR",
            prompt_tokens=17,
            completion_tokens=6,
            total_tokens=23,
            accounting_status="finalized",
        )

    monkeypatch.setattr(main_module.RouteResolutionService, "resolve_model", _fake_resolve_model)
    monkeypatch.setattr(main_module, "get_provider_adapter", lambda route, settings: _FakeAdapter())
    monkeypatch.setattr(
        main_module.AccountingService,
        "finalize_successful_response",
        _fake_finalize_successful_response,
    )

    response = TestClient(app).post(
        "/v1/responses",
        json=_responses_file_input_request(),
    )

    assert response.status_code == 200
    assert response.json()["id"] == "resp_file_test"
    assert seen_bodies == [
        {
            "model": "gpt-5.2",
            "input": [
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": "summarize the file"},
                        {
                            "type": "input_file",
                            "file_url": "https://example.test/document.pdf",
                        },
                    ],
                }
            ],
            "max_output_tokens": 20,
            "store": False,
        }
    ]
    assert reserve_calls == ["classroom-responses"]
    assert release_calls == []
    assert finalize_calls == ["classroom-responses"]


def test_streaming_responses_path_finalizes_from_completed_usage(monkeypatch) -> None:
    import slaif_gateway.services.responses_gateway as main_module

    app = create_app()
    _wire_auth_and_db(monkeypatch, app)
    reserve_calls, release_calls = _wire_successful_route_pricing_quota(monkeypatch)
    finalize_calls: list[tuple[str, bool, uuid.UUID | None]] = []
    completed_record_id = uuid.uuid4()

    async def _fake_resolve_model(self, requested_model, authenticated_key, *, endpoint="/v1/chat/completions"):
        _ = (self, authenticated_key, endpoint)
        return _route_result(
            requested_model,
            responses_streaming=True,
            route_supports_streaming=True,
        )

    class _FakeAdapter:
        async def stream_response(self, request):
            assert request.endpoint == "responses"
            assert request.body == {
                "model": "gpt-5.2",
                "input": "hello",
                "max_output_tokens": 20,
                "stream": True,
                "store": False,
            }
            yield ProviderStreamChunk(
                provider=request.provider,
                upstream_model=request.upstream_model,
                data='{"type":"response.created","response":{"id":"resp_test"}}',
                raw_sse_event='data: {"type":"response.created","response":{"id":"resp_test"}}\n\n',
                json_body={"type": "response.created", "response": {"id": "resp_test"}},
                upstream_request_id="upstream-responses-stream",
            )
            yield ProviderStreamChunk(
                provider=request.provider,
                upstream_model=request.upstream_model,
                data='{"type":"response.output_text.delta","delta":"hello"}',
                raw_sse_event='data: {"type":"response.output_text.delta","delta":"hello"}\n\n',
                json_body={"type": "response.output_text.delta", "delta": "hello"},
                upstream_request_id="upstream-responses-stream",
            )
            yield ProviderStreamChunk(
                provider=request.provider,
                upstream_model=request.upstream_model,
                data='{"type":"response.completed","response":{"id":"resp_test"}}',
                raw_sse_event='data: {"type":"response.completed","response":{"id":"resp_test"}}\n\n',
                json_body={"type": "response.completed", "response": {"id": "resp_test"}},
                usage=ProviderUsage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
                upstream_request_id="upstream-responses-stream",
            )

    async def _fake_record_provider_completed_before_finalization(
        self,
        reservation_id,
        authenticated_key,
        route,
        pricing_estimate,
        provider_response,
        request_id,
        endpoint="chat.completions",
        streaming=False,
        started_at=None,
        finished_at=None,
    ):
        _ = (
            self,
            reservation_id,
            authenticated_key,
            route,
            pricing_estimate,
            request_id,
            started_at,
            finished_at,
        )
        assert endpoint == "responses"
        assert streaming is True
        assert provider_response.usage is not None
        return type(
            "ProviderCompletedRecord",
            (),
            {"usage_ledger_id": completed_record_id},
        )()

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
        provider_completed_usage_ledger_id=None,
        streaming=False,
    ):
        _ = (
            self,
            reservation_id,
            authenticated_key,
            policy,
            pricing_estimate,
            provider_response,
            request_id,
            started_at,
            finished_at,
        )
        assert endpoint == "responses"
        finalize_calls.append((route.requested_model, streaming, provider_completed_usage_ledger_id))
        return FinalizedAccountingResult(
            usage_ledger_id=uuid.uuid4(),
            reservation_id=reservation_id,
            gateway_key_id=authenticated_key.gateway_key_id,
            request_id=request_id,
            estimated_cost_eur=Decimal("0.003"),
            actual_cost_eur=Decimal("0.003"),
            actual_cost_native=Decimal("0.003"),
            native_currency="EUR",
            prompt_tokens=1,
            completion_tokens=1,
            total_tokens=2,
            accounting_status="finalized",
        )

    monkeypatch.setattr(main_module.RouteResolutionService, "resolve_model", _fake_resolve_model)
    monkeypatch.setattr(main_module, "get_provider_adapter", lambda route, settings: _FakeAdapter())
    monkeypatch.setattr(
        main_module.AccountingService,
        "record_provider_completed_before_finalization",
        _fake_record_provider_completed_before_finalization,
    )
    monkeypatch.setattr(
        main_module.AccountingService,
        "finalize_successful_response",
        _fake_finalize_successful_response,
    )

    response = TestClient(app).post(
        "/v1/responses",
        json={**_responses_request(), "stream": True},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    body = response.text
    assert "response.created" in body
    assert "response.output_text.delta" in body
    assert "response.completed" in body
    assert reserve_calls == ["classroom-responses"]
    assert release_calls == []
    assert finalize_calls == [("classroom-responses", True, completed_record_id)]


def _wire_streaming_gateway(
    monkeypatch,
    *,
    chunks: list[ProviderStreamChunk],
    provider_error: Exception | None = None,
    finalize_error: Exception | None = None,
):
    import slaif_gateway.services.responses_gateway as main_module

    state: dict[str, list[object]] = {
        "stream_calls": [],
        "provider_completed_calls": [],
        "finalize_calls": [],
        "recovery_failure_calls": [],
        "failure_calls": [],
        "streaming_estimate_calls": [],
        "rate_release_calls": [],
    }
    completed_record_id = uuid.uuid4()
    rate_reservation = SimpleNamespace(concurrency_reserved=False)

    async def _fake_reserve_rate_limit(**kwargs):
        _ = kwargs
        return rate_reservation

    async def _fake_release_rate_limit(reservation, *, suppress):
        state["rate_release_calls"].append((reservation, suppress))

    class _FakeAdapter:
        async def stream_response(self, request):
            state["stream_calls"].append(request)
            for chunk in chunks:
                yield chunk
            if provider_error is not None:
                raise provider_error

    async def _fake_record_provider_completed_before_finalization(
        self,
        reservation_id,
        authenticated_key,
        route,
        pricing_estimate,
        provider_response,
        request_id,
        endpoint="chat.completions",
        streaming=False,
        started_at=None,
        finished_at=None,
    ):
        _ = (
            self,
            reservation_id,
            authenticated_key,
            route,
            pricing_estimate,
            request_id,
            started_at,
            finished_at,
        )
        state["provider_completed_calls"].append(
            {
                "endpoint": endpoint,
                "streaming": streaming,
                "usage": provider_response.usage,
            }
        )
        return SimpleNamespace(usage_ledger_id=completed_record_id)

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
        provider_completed_usage_ledger_id=None,
        streaming=False,
    ):
        _ = (
            self,
            reservation_id,
            authenticated_key,
            route,
            policy,
            pricing_estimate,
            provider_response,
            request_id,
            started_at,
            finished_at,
        )
        if finalize_error is not None:
            raise finalize_error
        state["finalize_calls"].append(
            {
                "endpoint": endpoint,
                "streaming": streaming,
                "provider_completed_usage_ledger_id": provider_completed_usage_ledger_id,
            }
        )
        return FinalizedAccountingResult(
            usage_ledger_id=uuid.uuid4(),
            reservation_id=reservation_id,
            gateway_key_id=authenticated_key.gateway_key_id,
            request_id=request_id,
            estimated_cost_eur=Decimal("0.003"),
            actual_cost_eur=Decimal("0.003"),
            actual_cost_native=Decimal("0.003"),
            native_currency="EUR",
            prompt_tokens=1,
            completion_tokens=1,
            total_tokens=2,
            accounting_status="finalized",
        )

    async def _fake_mark_provider_completed_finalization_failed(
        self,
        usage_ledger_id,
        reservation_id,
        error,
    ):
        _ = self
        state["recovery_failure_calls"].append(
            {
                "usage_ledger_id": usage_ledger_id,
                "reservation_id": reservation_id,
                "error": error,
            }
        )

    async def _fake_record_provider_failure_and_release(self, *args, **kwargs):
        _ = (self, args)
        state["failure_calls"].append(kwargs)

    async def _fake_streaming_estimate(self, *args, **kwargs):
        _ = (self, args)
        state["streaming_estimate_calls"].append(kwargs)
        return SimpleNamespace(accounting_status="estimated")

    monkeypatch.setattr(main_module, "_reserve_redis_rate_limit", _fake_reserve_rate_limit)
    monkeypatch.setattr(main_module, "_release_rate_limit_concurrency", _fake_release_rate_limit)
    monkeypatch.setattr(main_module, "get_provider_adapter", lambda route, settings: _FakeAdapter())
    monkeypatch.setattr(
        main_module.AccountingService,
        "record_provider_completed_before_finalization",
        _fake_record_provider_completed_before_finalization,
    )
    monkeypatch.setattr(
        main_module.AccountingService,
        "finalize_successful_response",
        _fake_finalize_successful_response,
    )
    monkeypatch.setattr(
        main_module.AccountingService,
        "mark_provider_completed_finalization_failed",
        _fake_mark_provider_completed_finalization_failed,
    )
    monkeypatch.setattr(
        main_module.AccountingService,
        "record_provider_failure_and_release",
        _fake_record_provider_failure_and_release,
    )
    monkeypatch.setattr(
        main_module.AccountingService,
        "record_streaming_live_burn_interrupted_estimate",
        _fake_streaming_estimate,
    )
    monkeypatch.setattr(
        main_module.AccountingService,
        "record_streaming_interrupted_estimate",
        _fake_streaming_estimate,
    )
    return state, completed_record_id, rate_reservation


def test_streaming_provider_adapter_construction_failure_releases_reservation_and_rate_limit(
    monkeypatch,
) -> None:
    import slaif_gateway.services.responses_gateway as main_module

    app = create_app()
    _wire_auth_and_db(monkeypatch, app)
    reserve_calls, _release_calls = _wire_successful_route_pricing_quota(monkeypatch)
    _wire_streaming_route(monkeypatch)
    failure_calls: list[dict[str, object]] = []
    rate_release_calls: list[tuple[object, bool]] = []
    rate_reservation = SimpleNamespace(concurrency_reserved=False)

    async def _fake_reserve_rate_limit(**kwargs):
        _ = kwargs
        return rate_reservation

    async def _fake_release_rate_limit(reservation, *, suppress):
        rate_release_calls.append((reservation, suppress))

    async def _fake_failure_and_release(**kwargs):
        failure_calls.append(kwargs)

    def _raise_missing_key(route, settings):
        _ = (route, settings)
        raise MissingProviderApiKeyError(provider="openai")

    monkeypatch.setattr(main_module, "_reserve_redis_rate_limit", _fake_reserve_rate_limit)
    monkeypatch.setattr(main_module, "_release_rate_limit_concurrency", _fake_release_rate_limit)
    monkeypatch.setattr(main_module, "_record_provider_failure_and_release", _fake_failure_and_release)
    monkeypatch.setattr(main_module, "get_provider_adapter", _raise_missing_key)

    response = TestClient(app).post(
        "/v1/responses",
        json={**_responses_request(), "stream": True},
    )

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "missing_provider_api_key"
    assert reserve_calls == ["classroom-responses"]
    assert len(failure_calls) == 1
    assert failure_calls[0]["streaming"] is True
    assert failure_calls[0]["provider_error"].error_code == "missing_provider_api_key"
    assert rate_release_calls == [(rate_reservation, True)]
    assert "hello" not in response.text
    assert "sk-" not in response.text


def test_streaming_responses_withholds_done_until_after_finalization(monkeypatch) -> None:
    app = create_app()
    _wire_auth_and_db(monkeypatch, app)
    reserve_calls, release_calls = _wire_successful_route_pricing_quota(monkeypatch)
    _wire_streaming_route(monkeypatch)
    chunks = [
        _response_stream_chunk({"type": "response.created", "response": {"id": "resp_test"}}),
        _response_stream_chunk({"type": "response.output_text.delta", "delta": "visible"}),
        _response_stream_chunk(
            _completed_payload(),
            usage=ProviderUsage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
        ),
        _done_chunk(),
    ]
    state, completed_record_id, rate_reservation = _wire_streaming_gateway(
        monkeypatch,
        chunks=chunks,
    )

    response = TestClient(app).post(
        "/v1/responses",
        json={**_responses_request(), "stream": True},
    )

    assert response.status_code == 200
    body = response.text
    assert body.index("response.completed") < body.index("[DONE]")
    assert state["provider_completed_calls"]
    assert state["finalize_calls"] == [
        {
            "endpoint": "responses",
            "streaming": True,
            "provider_completed_usage_ledger_id": completed_record_id,
        }
    ]
    assert state["failure_calls"] == []
    assert state["rate_release_calls"] == [(rate_reservation, True)]
    assert reserve_calls == ["classroom-responses"]
    assert release_calls == []


def test_streaming_responses_missing_usage_emits_error_without_success_done(monkeypatch) -> None:
    app = create_app()
    _wire_auth_and_db(monkeypatch, app)
    reserve_calls, release_calls = _wire_successful_route_pricing_quota(monkeypatch)
    _wire_streaming_route(monkeypatch)
    chunks = [
        _response_stream_chunk({"type": "response.created", "response": {"id": "resp_test"}}),
        _response_stream_chunk({"type": "response.output_text.delta", "delta": "visible"}),
        _response_stream_chunk(_completed_payload(include_usage=False), usage=None),
        _done_chunk(),
    ]
    state, _completed_record_id, rate_reservation = _wire_streaming_gateway(
        monkeypatch,
        chunks=chunks,
    )

    response = TestClient(app).post(
        "/v1/responses",
        json={**_responses_request(), "stream": True},
    )

    assert response.status_code == 200
    body = response.text
    assert "response.output_text.delta" in body
    assert "responses_stream_usage_missing" in body
    assert "data: [DONE]" not in body
    assert body.count("response.completed") == 0
    assert state["finalize_calls"] == []
    assert state["failure_calls"] == []
    assert len(state["streaming_estimate_calls"]) == 1
    assert state["streaming_estimate_calls"][0]["estimate_reason"] == (
        "responses_streaming_usage_missing_estimated"
    )
    assert state["streaming_estimate_calls"][0]["error_type"] == "responses_stream_usage_missing"
    assert state["rate_release_calls"] == [(rate_reservation, True)]
    assert reserve_calls == ["classroom-responses"]
    assert release_calls == []


def test_streaming_responses_finalization_failure_records_recovery_and_no_success_done(
    monkeypatch,
) -> None:
    app = create_app()
    _wire_auth_and_db(monkeypatch, app)
    _wire_successful_route_pricing_quota(monkeypatch)
    _wire_streaming_route(monkeypatch)
    chunks = [
        _response_stream_chunk({"type": "response.created", "response": {"id": "resp_test"}}),
        _response_stream_chunk({"type": "response.output_text.delta", "delta": "visible"}),
        _response_stream_chunk(
            _completed_payload(),
            usage=ProviderUsage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
        ),
        _done_chunk(),
    ]
    error = ReservationFinalizationError("finalization failed")
    state, completed_record_id, rate_reservation = _wire_streaming_gateway(
        monkeypatch,
        chunks=chunks,
        finalize_error=error,
    )

    response = TestClient(app).post(
        "/v1/responses",
        json={**_responses_request(), "stream": True},
    )

    assert response.status_code == 200
    body = response.text
    assert "reservation_finalization_error" in body
    assert "data: [DONE]" not in body
    assert body.count("response.completed") == 0
    assert state["provider_completed_calls"]
    assert state["finalize_calls"] == []
    assert len(state["recovery_failure_calls"]) == 1
    assert state["recovery_failure_calls"][0]["usage_ledger_id"] == completed_record_id
    assert state["recovery_failure_calls"][0]["error"] is error
    assert state["failure_calls"] == []
    assert state["rate_release_calls"] == [(rate_reservation, True)]


def test_streaming_responses_provider_error_after_partial_output_records_estimated_interruption(
    monkeypatch,
) -> None:
    app = create_app()
    _wire_auth_and_db(monkeypatch, app)
    _wire_successful_route_pricing_quota(monkeypatch)
    _wire_streaming_route(monkeypatch)
    chunks = [
        _response_stream_chunk({"type": "response.created", "response": {"id": "resp_test"}}),
        _response_stream_chunk({"type": "response.output_text.delta", "delta": "visible"}),
    ]
    state, _completed_record_id, rate_reservation = _wire_streaming_gateway(
        monkeypatch,
        chunks=chunks,
        provider_error=ProviderTimeoutError(provider="openai"),
    )

    response = TestClient(app).post(
        "/v1/responses",
        json={**_responses_request(), "stream": True},
    )

    assert response.status_code == 200
    body = response.text
    assert "response.output_text.delta" in body
    assert "provider_timeout" in body
    assert "data: [DONE]" not in body
    assert "hello" not in body
    assert state["finalize_calls"] == []
    assert state["provider_completed_calls"] == []
    assert state["failure_calls"] == []
    assert len(state["streaming_estimate_calls"]) == 1
    assert state["streaming_estimate_calls"][0]["estimate_reason"] == (
        "responses_streaming_provider_error_estimated"
    )
    assert state["streaming_estimate_calls"][0]["error_type"] == "provider_timeout"
    assert state["rate_release_calls"] == [(rate_reservation, True)]


def test_streaming_responses_live_burn_abort_emits_safe_error_without_success(
    monkeypatch,
) -> None:
    app = create_app()
    auth_key = _fake_authenticated_gateway_key(
        token_limit_total=24,
        responses_streaming_live_burn_policy={
            "version": 1,
            "enabled": True,
            "cost_margin_eur": "0.000000000",
            "token_margin": 0,
        },
    )
    _wire_auth_and_db(monkeypatch, app, auth_key)
    _wire_successful_route_pricing_quota(monkeypatch)
    _wire_streaming_route(monkeypatch)
    chunks = [
        _response_stream_chunk({"type": "response.created", "response": {"id": "resp_test"}}),
        _response_stream_chunk(
            {"type": "response.output_text.delta", "delta": "secret streamed text"}
        ),
        _response_stream_chunk(
            _completed_payload(),
            usage=ProviderUsage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
        ),
        _done_chunk(),
    ]
    state, _completed_record_id, rate_reservation = _wire_streaming_gateway(
        monkeypatch,
        chunks=chunks,
    )

    response = TestClient(app).post(
        "/v1/responses",
        json={**_responses_request(), "stream": True},
    )

    assert response.status_code == 200
    body = response.text
    assert "secret streamed text" not in body
    assert "streaming_live_burn_limit_exceeded" in body
    assert "response.completed" not in body
    assert "data: [DONE]" not in body
    assert state["provider_completed_calls"] == []
    assert state["finalize_calls"] == []
    assert state["failure_calls"] == []
    assert len(state["streaming_estimate_calls"]) == 1
    response_metadata = state["streaming_estimate_calls"][0]["response_metadata"]
    assert response_metadata["streaming_live_burn_triggered"] is True
    assert response_metadata["streaming_live_burn_stop_reason"] == "tokens"
    assert "secret streamed text" not in json.dumps(response_metadata)
    assert state["rate_release_calls"] == [(rate_reservation, True)]


def test_streaming_responses_unknown_generated_event_is_not_forwarded_unmetered(monkeypatch) -> None:
    app = create_app()
    _wire_auth_and_db(monkeypatch, app)
    _wire_successful_route_pricing_quota(monkeypatch)
    _wire_streaming_route(monkeypatch)
    chunks = [
        _response_stream_chunk({"type": "response.created", "response": {"id": "resp_test"}}),
        _response_stream_chunk({"type": "response.output_audio.delta", "delta": "secret audio"}),
    ]
    state, _completed_record_id, rate_reservation = _wire_streaming_gateway(
        monkeypatch,
        chunks=chunks,
    )

    response = TestClient(app).post(
        "/v1/responses",
        json={**_responses_request(), "stream": True},
    )

    assert response.status_code == 200
    body = response.text
    assert "response.created" in body
    assert "response.output_audio.delta" not in body
    assert "responses_stream_event_not_supported" in body
    assert state["failure_calls"]
    assert state["streaming_estimate_calls"] == []
    assert state["rate_release_calls"] == [(rate_reservation, True)]


def test_streaming_responses_client_disconnect_after_output_records_estimated_interruption(
    monkeypatch,
) -> None:
    app = create_app()
    _wire_auth_and_db(monkeypatch, app)
    _wire_successful_route_pricing_quota(monkeypatch)
    _wire_streaming_route(monkeypatch)
    chunks = [
        _response_stream_chunk({"type": "response.created", "response": {"id": "resp_test"}}),
        _response_stream_chunk({"type": "response.output_text.delta", "delta": "visible"}),
    ]
    state, _completed_record_id, rate_reservation = _wire_streaming_gateway(
        monkeypatch,
        chunks=chunks,
        provider_error=asyncio.CancelledError(),
    )

    response = TestClient(app).post(
        "/v1/responses",
        json={**_responses_request(), "stream": True},
    )

    assert response.status_code == 200
    body = response.text
    assert "visible" in body
    assert state["failure_calls"] == []
    assert len(state["streaming_estimate_calls"]) == 1
    assert state["streaming_estimate_calls"][0]["estimate_reason"] == (
        "responses_streaming_client_disconnected_estimated"
    )
    assert state["streaming_estimate_calls"][0]["error_type"] == "client_disconnected"
    assert state["rate_release_calls"] == [(rate_reservation, True)]


def test_chat_endpoint_permission_does_not_allow_responses(monkeypatch) -> None:
    app = create_app()
    _wire_auth_and_db(
        monkeypatch,
        app,
        _fake_authenticated_gateway_key(allowed_endpoints=("/v1/chat/completions",)),
    )
    _wire_successful_route_pricing_quota(monkeypatch)
    _wire_successful_forwarding(monkeypatch)

    response = TestClient(app).post("/v1/responses", json=_responses_request())

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "endpoint_not_allowed"


@pytest.mark.parametrize(
    ("payload_extra", "expected_code"),
    [
        ({"background": True}, "responses_background_not_supported"),
        ({"modalities": ["audio"]}, "responses_multimodal_not_supported"),
        ({"audio": {"format": "wav"}}, "responses_multimodal_not_supported"),
        (
            {
                "input": [
                    {
                        "role": "user",
                        "content": [{"type": "input_audio", "data": "secret-audio"}],
                    }
                ]
            },
            "responses_input_multimodal_not_supported",
        ),
    ],
)
def test_policy_error_happens_before_route_pricing_or_quota(
    monkeypatch,
    payload_extra: dict[str, object],
    expected_code: str,
) -> None:
    import slaif_gateway.services.responses_gateway as main_module

    app = create_app()
    _wire_auth_and_db(monkeypatch, app)
    route_calls: list[str] = []
    pricing_calls: list[str] = []
    quota_calls: list[str] = []

    async def _fake_resolve_model(self, requested_model, authenticated_key, *, endpoint="/v1/chat/completions"):
        _ = (self, authenticated_key, endpoint)
        route_calls.append(requested_model)

    async def _fake_estimate_chat_completion_cost(self, **kwargs):
        _ = self
        pricing_calls.append(str(kwargs))

    async def _fake_reserve(self, **kwargs):
        _ = self
        quota_calls.append(str(kwargs))

    monkeypatch.setattr(main_module.RouteResolutionService, "resolve_model", _fake_resolve_model)
    monkeypatch.setattr(
        main_module.PricingService,
        "estimate_chat_completion_cost",
        _fake_estimate_chat_completion_cost,
    )
    monkeypatch.setattr(main_module.QuotaService, "reserve_for_chat_completion", _fake_reserve)

    response = TestClient(app).post(
        "/v1/responses",
        json={**_responses_request(), **payload_extra},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == expected_code
    assert "secret-audio" not in response.text
    assert route_calls == []
    assert pricing_calls == []
    assert quota_calls == []


def test_invalid_input_item_array_happens_before_rate_pricing_quota_provider(monkeypatch) -> None:
    import slaif_gateway.services.responses_gateway as main_module

    app = create_app()
    _wire_auth_and_db(monkeypatch, app)
    route_calls: list[str] = []
    rate_calls: list[str] = []
    pricing_calls: list[str] = []
    quota_calls: list[str] = []
    provider_calls: list[str] = []

    async def _fake_resolve_model(self, requested_model, authenticated_key, *, endpoint="/v1/chat/completions"):
        _ = (self, authenticated_key, endpoint)
        route_calls.append(requested_model)

    async def _fake_reserve_rate_limit(**kwargs):
        rate_calls.append(str(kwargs))

    async def _fake_estimate_chat_completion_cost(self, **kwargs):
        _ = self
        pricing_calls.append(str(kwargs))

    async def _fake_reserve(self, **kwargs):
        _ = self
        quota_calls.append(str(kwargs))

    def _fake_get_provider_adapter(route, settings):
        _ = (route, settings)
        provider_calls.append("provider")
        raise AssertionError("provider adapter should not be called")

    monkeypatch.setattr(main_module.RouteResolutionService, "resolve_model", _fake_resolve_model)
    monkeypatch.setattr(main_module, "_reserve_redis_rate_limit", _fake_reserve_rate_limit)
    monkeypatch.setattr(
        main_module.PricingService,
        "estimate_chat_completion_cost",
        _fake_estimate_chat_completion_cost,
    )
    monkeypatch.setattr(main_module.QuotaService, "reserve_for_chat_completion", _fake_reserve)
    monkeypatch.setattr(main_module, "get_provider_adapter", _fake_get_provider_adapter)

    response = TestClient(app).post(
        "/v1/responses",
        json={
            **_responses_request(),
            "input": [
                {
                    "role": "user",
                    "content": [{"type": "input_file", "file_data": "secret"}],
                }
            ],
        },
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "responses_input_file_name_invalid"
    assert "secret" not in response.text
    assert route_calls == []
    assert rate_calls == []
    assert pricing_calls == []
    assert quota_calls == []
    assert provider_calls == []


def test_streaming_capability_error_happens_before_rate_pricing_quota_provider(monkeypatch) -> None:
    import slaif_gateway.services.responses_gateway as main_module

    app = create_app()
    _wire_auth_and_db(monkeypatch, app)
    rate_calls: list[str] = []
    pricing_calls: list[str] = []
    quota_calls: list[str] = []
    provider_calls: list[str] = []

    async def _fake_resolve_model(self, requested_model, authenticated_key, *, endpoint="/v1/chat/completions"):
        _ = (self, authenticated_key, endpoint)
        return _route_result(requested_model)

    async def _fake_reserve_rate_limit(**kwargs):
        rate_calls.append(str(kwargs))

    async def _fake_estimate_chat_completion_cost(self, **kwargs):
        _ = self
        pricing_calls.append(str(kwargs))

    async def _fake_reserve(self, **kwargs):
        _ = self
        quota_calls.append(str(kwargs))

    def _fake_get_provider_adapter(route, settings):
        _ = (route, settings)
        provider_calls.append("provider")
        raise AssertionError("provider adapter should not be called")

    monkeypatch.setattr(main_module.RouteResolutionService, "resolve_model", _fake_resolve_model)
    monkeypatch.setattr(main_module, "_reserve_redis_rate_limit", _fake_reserve_rate_limit)
    monkeypatch.setattr(
        main_module.PricingService,
        "estimate_chat_completion_cost",
        _fake_estimate_chat_completion_cost,
    )
    monkeypatch.setattr(main_module.QuotaService, "reserve_for_chat_completion", _fake_reserve)
    monkeypatch.setattr(main_module, "get_provider_adapter", _fake_get_provider_adapter)

    response = TestClient(app).post(
        "/v1/responses",
        json={**_responses_request(), "stream": True},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "responses_route_capability_not_supported"
    assert rate_calls == []
    assert pricing_calls == []
    assert quota_calls == []
    assert provider_calls == []


def test_route_capability_error_happens_before_pricing_quota_provider(monkeypatch) -> None:
    import slaif_gateway.services.responses_gateway as main_module

    app = create_app()
    _wire_auth_and_db(monkeypatch, app)
    pricing_calls: list[str] = []
    quota_calls: list[str] = []
    provider_calls: list[str] = []

    async def _fake_resolve_model(self, requested_model, authenticated_key, *, endpoint="/v1/chat/completions"):
        _ = (self, authenticated_key, endpoint)
        return RouteResolutionResult(
            requested_model=requested_model,
            resolved_model="gpt-5.2",
            provider="openai",
            route_id=uuid.uuid4(),
            route_match_type="exact",
            route_pattern=requested_model,
            priority=100,
            capabilities={"chat_completions": {"chat_text": True}},
        )

    async def _fake_estimate_chat_completion_cost(self, **kwargs):
        _ = self
        pricing_calls.append(str(kwargs))

    async def _fake_reserve(self, **kwargs):
        _ = self
        quota_calls.append(str(kwargs))

    def _fake_get_provider_adapter(route, settings):
        _ = (route, settings)
        provider_calls.append("provider")
        raise AssertionError("provider adapter should not be called")

    monkeypatch.setattr(main_module.RouteResolutionService, "resolve_model", _fake_resolve_model)
    monkeypatch.setattr(
        main_module.PricingService,
        "estimate_chat_completion_cost",
        _fake_estimate_chat_completion_cost,
    )
    monkeypatch.setattr(main_module.QuotaService, "reserve_for_chat_completion", _fake_reserve)
    monkeypatch.setattr(main_module, "get_provider_adapter", _fake_get_provider_adapter)

    response = TestClient(app).post("/v1/responses", json=_responses_request())

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "responses_route_capability_missing"
    assert pricing_calls == []
    assert quota_calls == []
    assert provider_calls == []


def test_structured_output_capability_error_happens_before_rate_pricing_quota_provider(
    monkeypatch,
) -> None:
    import slaif_gateway.services.responses_gateway as main_module

    app = create_app()
    _wire_auth_and_db(monkeypatch, app)
    rate_calls: list[str] = []
    pricing_calls: list[str] = []
    quota_calls: list[str] = []
    provider_calls: list[str] = []

    async def _fake_resolve_model(self, requested_model, authenticated_key, *, endpoint="/v1/chat/completions"):
        _ = (self, authenticated_key, endpoint)
        return _route_result(requested_model)

    async def _fake_reserve_rate_limit(**kwargs):
        rate_calls.append(str(kwargs))

    async def _fake_estimate_chat_completion_cost(self, **kwargs):
        _ = self
        pricing_calls.append(str(kwargs))

    async def _fake_reserve(self, **kwargs):
        _ = self
        quota_calls.append(str(kwargs))

    def _fake_get_provider_adapter(route, settings):
        _ = (route, settings)
        provider_calls.append("provider")
        raise AssertionError("provider adapter should not be called")

    monkeypatch.setattr(main_module.RouteResolutionService, "resolve_model", _fake_resolve_model)
    monkeypatch.setattr(main_module, "_reserve_redis_rate_limit", _fake_reserve_rate_limit)
    monkeypatch.setattr(
        main_module.PricingService,
        "estimate_chat_completion_cost",
        _fake_estimate_chat_completion_cost,
    )
    monkeypatch.setattr(main_module.QuotaService, "reserve_for_chat_completion", _fake_reserve)
    monkeypatch.setattr(main_module, "get_provider_adapter", _fake_get_provider_adapter)

    response = TestClient(app).post(
        "/v1/responses",
        json={
            **_responses_request(),
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "answer_schema",
                    "schema": {"type": "object"},
                }
            },
        },
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "responses_structured_output_not_supported"
    assert rate_calls == []
    assert pricing_calls == []
    assert quota_calls == []
    assert provider_calls == []


def test_json_mode_capability_error_happens_before_rate_pricing_quota_provider(
    monkeypatch,
) -> None:
    import slaif_gateway.services.responses_gateway as main_module

    app = create_app()
    _wire_auth_and_db(monkeypatch, app)
    rate_calls: list[str] = []
    pricing_calls: list[str] = []
    quota_calls: list[str] = []
    provider_calls: list[str] = []

    async def _fake_resolve_model(self, requested_model, authenticated_key, *, endpoint="/v1/chat/completions"):
        _ = (self, authenticated_key, endpoint)
        return _route_result(requested_model)

    async def _fake_reserve_rate_limit(**kwargs):
        rate_calls.append(str(kwargs))

    async def _fake_estimate_chat_completion_cost(self, **kwargs):
        _ = self
        pricing_calls.append(str(kwargs))

    async def _fake_reserve(self, **kwargs):
        _ = self
        quota_calls.append(str(kwargs))

    def _fake_get_provider_adapter(route, settings):
        _ = (route, settings)
        provider_calls.append("provider")
        raise AssertionError("provider adapter should not be called")

    monkeypatch.setattr(main_module.RouteResolutionService, "resolve_model", _fake_resolve_model)
    monkeypatch.setattr(main_module, "_reserve_redis_rate_limit", _fake_reserve_rate_limit)
    monkeypatch.setattr(
        main_module.PricingService,
        "estimate_chat_completion_cost",
        _fake_estimate_chat_completion_cost,
    )
    monkeypatch.setattr(main_module.QuotaService, "reserve_for_chat_completion", _fake_reserve)
    monkeypatch.setattr(main_module, "get_provider_adapter", _fake_get_provider_adapter)

    response = TestClient(app).post(
        "/v1/responses",
        json={**_responses_request(), "text": {"format": {"type": "json_object"}}},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "responses_json_mode_not_supported"
    assert rate_calls == []
    assert pricing_calls == []
    assert quota_calls == []
    assert provider_calls == []


def test_structured_output_request_forwards_with_explicit_capability(monkeypatch) -> None:
    import slaif_gateway.services.responses_gateway as main_module

    app = create_app()
    _wire_auth_and_db(monkeypatch, app)
    reserve_calls, _release_calls = _wire_successful_route_pricing_quota(monkeypatch)
    finalize_calls = _wire_successful_forwarding(monkeypatch)

    async def _fake_resolve_model(self, requested_model, authenticated_key, *, endpoint="/v1/chat/completions"):
        _ = (self, authenticated_key, endpoint)
        return _route_result(requested_model, responses_structured_outputs=True)

    forwarded_bodies: list[dict[str, object]] = []

    class _FakeAdapter:
        async def forward_response(self, request):
            assert request.endpoint == "responses"
            forwarded_bodies.append(dict(request.body))
            return ProviderResponse(
                provider=request.provider,
                upstream_model=request.upstream_model,
                status_code=200,
                json_body={"id": "resp_test", "object": "response"},
                usage=ProviderUsage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
            )

    monkeypatch.setattr(main_module.RouteResolutionService, "resolve_model", _fake_resolve_model)
    monkeypatch.setattr(main_module, "get_provider_adapter", lambda route, settings: _FakeAdapter())

    response = TestClient(app).post(
        "/v1/responses",
        json={
            **_responses_request(),
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "answer_schema",
                    "schema": {"type": "object"},
                }
            },
        },
    )

    assert response.status_code == 200
    assert forwarded_bodies == [
        {
            "model": "gpt-5.2",
            "input": "hello",
            "max_output_tokens": 20,
            "store": False,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "answer_schema",
                    "schema": {"type": "object"},
                }
            },
        }
    ]
    assert reserve_calls == ["classroom-responses"]
    assert finalize_calls == ["classroom-responses"]


def test_input_item_array_request_forwards_canonical_body(monkeypatch) -> None:
    import slaif_gateway.services.responses_gateway as main_module

    app = create_app()
    _wire_auth_and_db(monkeypatch, app)
    reserve_calls, _release_calls = _wire_successful_route_pricing_quota(monkeypatch)
    finalize_calls = _wire_successful_forwarding(monkeypatch)

    forwarded_bodies: list[dict[str, object]] = []

    class _FakeAdapter:
        async def forward_response(self, request):
            assert request.endpoint == "responses"
            forwarded_bodies.append(dict(request.body))
            return ProviderResponse(
                provider=request.provider,
                upstream_model=request.upstream_model,
                status_code=200,
                json_body={"id": "resp_test", "object": "response"},
                usage=ProviderUsage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
            )

    monkeypatch.setattr(main_module, "get_provider_adapter", lambda route, settings: _FakeAdapter())

    response = TestClient(app).post(
        "/v1/responses",
        json={
            **_responses_request(),
            "input": [
                {"role": "system", "content": "system text"},
                {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": "hello"}],
                },
            ],
        },
    )

    assert response.status_code == 200
    assert forwarded_bodies == [
        {
            "model": "gpt-5.2",
            "input": [
                {"role": "system", "content": "system text"},
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": "hello"}],
                    "type": "message",
                },
            ],
            "max_output_tokens": 20,
            "store": False,
        }
    ]
    assert reserve_calls == ["classroom-responses"]
    assert finalize_calls == ["classroom-responses"]


def test_pricing_failure_happens_before_quota_reservation(monkeypatch) -> None:
    import slaif_gateway.services.responses_gateway as main_module

    app = create_app()
    _wire_auth_and_db(monkeypatch, app)
    quota_calls: list[str] = []

    async def _fake_resolve_model(self, requested_model, authenticated_key, *, endpoint="/v1/chat/completions"):
        _ = (self, authenticated_key, endpoint)
        return _route_result(requested_model)

    async def _fake_estimate_chat_completion_cost(self, *, route, policy, endpoint="chat.completions", at=None):
        _ = (self, route, policy, endpoint, at)
        raise PricingRuleNotFoundError(param="model")

    async def _fake_reserve(self, **kwargs):
        _ = self
        quota_calls.append(str(kwargs))

    monkeypatch.setattr(main_module.RouteResolutionService, "resolve_model", _fake_resolve_model)
    monkeypatch.setattr(
        main_module.PricingService,
        "estimate_chat_completion_cost",
        _fake_estimate_chat_completion_cost,
    )
    monkeypatch.setattr(main_module.QuotaService, "reserve_for_chat_completion", _fake_reserve)

    response = TestClient(app).post("/v1/responses", json=_responses_request())

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "pricing_rule_not_found"
    assert quota_calls == []


def test_unsupported_model_happens_before_pricing_or_quota(monkeypatch) -> None:
    import slaif_gateway.services.responses_gateway as main_module

    app = create_app()
    _wire_auth_and_db(monkeypatch, app)
    pricing_calls: list[str] = []
    quota_calls: list[str] = []

    async def _fake_resolve_model(self, requested_model, authenticated_key, *, endpoint="/v1/chat/completions"):
        _ = (self, requested_model, authenticated_key, endpoint)
        raise ModelNotFoundError()

    async def _fake_estimate_chat_completion_cost(self, **kwargs):
        _ = self
        pricing_calls.append(str(kwargs))

    async def _fake_reserve(self, **kwargs):
        _ = self
        quota_calls.append(str(kwargs))

    monkeypatch.setattr(main_module.RouteResolutionService, "resolve_model", _fake_resolve_model)
    monkeypatch.setattr(
        main_module.PricingService,
        "estimate_chat_completion_cost",
        _fake_estimate_chat_completion_cost,
    )
    monkeypatch.setattr(main_module.QuotaService, "reserve_for_chat_completion", _fake_reserve)

    response = TestClient(app).post("/v1/responses", json=_responses_request("unsupported"))

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "model_not_found"
    assert pricing_calls == []
    assert quota_calls == []


def test_quota_exceeded_returns_openai_error(monkeypatch) -> None:
    app = create_app()
    _wire_auth_and_db(monkeypatch, app)
    reserve_calls, release_calls = _wire_successful_route_pricing_quota(
        monkeypatch,
        quota_error=QuotaLimitExceededError("Token quota limit exceeded", param="token_limit_total"),
    )

    response = TestClient(app).post("/v1/responses", json=_responses_request())

    assert response.status_code == 429
    assert response.json()["error"]["code"] == "quota_limit_exceeded"
    assert reserve_calls == ["classroom-responses"]
    assert release_calls == []
