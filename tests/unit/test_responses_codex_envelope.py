from __future__ import annotations

import asyncio
import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import capture_codex_protocol as capture
from slaif_gateway.api.errors import OpenAICompatibleError
from slaif_gateway.config import Settings
from slaif_gateway.schemas.accounting import FinalizedAccountingResult
from slaif_gateway.schemas.auth import AuthenticatedGatewayKey
from slaif_gateway.schemas.openai import ResponsesCreateRequest
from slaif_gateway.schemas.pricing import ChatCostEstimate
from slaif_gateway.schemas.providers import ProviderResponse, ProviderUsage
from slaif_gateway.schemas.quota import QuotaReservationResult
from slaif_gateway.schemas.routing import RouteResolutionResult
from slaif_gateway.services.policy_errors import RequestPolicyError
from slaif_gateway.services.responses_request_policy import (
    ResponsesRequestPolicy,
    responses_codex_request_envelope_allowed,
    responses_codex_request_envelope_requested,
)
from slaif_gateway.services.responses_route_capabilities import (
    default_responses_capabilities,
    enforce_responses_route_capabilities,
)
from slaif_gateway.services.upstream_payloads import build_responses_upstream_body
from slaif_gateway.services.upstream_request_contracts import (
    normalize_responses_upstream_request,
)


FIXTURE = Path("tests/fixtures/codex/0.147.0/gpt-5.6-sol-api-key-responses.json")
FIXTURE_SHA256 = "436ea530b9f984807dfc73ccce0b5233d0a3047ceb10ef942fbc8d12cac47432"
CLIENT_METADATA_CANARY = "client-metadata-private-canary"
PROMPT_CACHE_CANARY = "prompt-cache-private-canary"
MESSAGE_ID_CANARY = "msg-private-canary-123"


def _ordinary_body(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "model": "classroom-codex",
        "input": "hello",
        "max_output_tokens": 20,
    }
    body.update(overrides)
    return body


def _envelope_body(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "model": "classroom-codex",
        "input": [
            {
                "id": "msg_opaque_123",
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "hello"}],
            }
        ],
        "client_metadata": {
            "x-codex-installation-id": "install-123",
            "session_id": "session-123",
            "thread_id": "thread-123",
            "turn_id": "turn-123",
            "x-codex-window-id": "window-123",
            "x-codex-turn-metadata": '{"request_kind":"turn"}',
        },
        "include": ["reasoning.encrypted_content", "reasoning.encrypted_content"],
        "parallel_tool_calls": False,
        "prompt_cache_key": "cache-opaque-123",
        "reasoning": {"context": "all_turns", "effort": "low"},
        "text": {"verbosity": "low"},
        "store": False,
        "stream": True,
        "max_output_tokens": 20,
    }
    body.update(overrides)
    return body


def _key_policy() -> dict[str, object]:
    return {
        "version": 1,
        "allowed_capabilities": ["text", "stateless", "codex_request_envelope"],
    }


def _authenticated_key(*, responses_policy: dict[str, object] | None) -> AuthenticatedGatewayKey:
    now = datetime.now(UTC)
    return AuthenticatedGatewayKey(
        gateway_key_id=uuid.uuid4(),
        owner_id=uuid.uuid4(),
        cohort_id=None,
        public_key_id="public-codex-test",
        status="active",
        valid_from=now - timedelta(minutes=5),
        valid_until=now + timedelta(minutes=30),
        allow_all_models=True,
        allowed_models=(),
        allow_all_endpoints=False,
        allowed_endpoints=("/v1/responses",),
        allowed_providers=None,
        cost_limit_eur=None,
        token_limit_total=None,
        request_limit_total=None,
        rate_limit_policy={},
        responses_policy=responses_policy,
    )


def _route(*, codex_request_envelope: bool) -> RouteResolutionResult:
    capabilities = default_responses_capabilities()
    capabilities["streaming"] = True
    capabilities["codex_request_envelope"] = codex_request_envelope
    return RouteResolutionResult(
        requested_model="classroom-codex",
        resolved_model="gpt-5.6-sol",
        provider="openai",
        route_id=uuid.uuid4(),
        route_match_type="exact",
        route_pattern="classroom-codex",
        priority=100,
        supports_streaming=True,
        capabilities={"responses": capabilities},
    )


def _apply_envelope(body: dict[str, object] | None = None):
    return ResponsesRequestPolicy(Settings()).apply(
        body or _envelope_body(stream=False),
        allow_codex_request_envelope=True,
    )


def test_ordinary_responses_are_unchanged_and_do_not_request_codex_capability() -> None:
    body = _ordinary_body()

    default_result = ResponsesRequestPolicy(Settings()).apply(body)
    enabled_result = ResponsesRequestPolicy(Settings()).apply(
        body,
        allow_codex_request_envelope=True,
    )

    assert responses_codex_request_envelope_requested(body) is False
    assert default_result == enabled_result
    assert default_result.effective_body["store"] is False


@pytest.mark.parametrize(
    "extra",
    [
        {"client_metadata": {}},
        {"include": ["reasoning.encrypted_content"]},
        {"parallel_tool_calls": False},
        {"prompt_cache_key": "cache"},
        {"reasoning": {"effort": "low"}},
        {"text": {"verbosity": "low"}},
        {
            "input": [
                {"type": "message", "id": "msg_1", "role": "user", "content": "hello"}
            ]
        },
    ],
)
def test_each_envelope_signal_is_default_denied_by_key(extra: dict[str, object]) -> None:
    with pytest.raises(RequestPolicyError) as exc_info:
        ResponsesRequestPolicy(Settings()).apply(_ordinary_body(**extra))

    assert exc_info.value.error_code == "responses_codex_envelope_not_allowed"
    assert responses_codex_request_envelope_requested(_ordinary_body(**extra)) is True


@pytest.mark.parametrize(
    "policy",
    [
        None,
        {},
        {"version": 2, "allowed_capabilities": ["codex_request_envelope"]},
        {"version": 1, "allowed_capabilities": "codex_request_envelope"},
        {"version": 1, "allowed_capabilities": ["codex_request_envelope", 3]},
        {"version": 1, "allowed_capabilities": ["codex_request_envelope", "unknown"]},
        {
            "version": 1,
            "allowed_capabilities": ["codex_request_envelope", "codex_request_envelope"],
        },
    ],
)
def test_missing_or_malformed_key_policy_never_enables_envelope(policy: object) -> None:
    assert responses_codex_request_envelope_allowed(policy) is False


def test_explicit_well_formed_key_policy_enables_envelope() -> None:
    assert responses_codex_request_envelope_allowed(_key_policy()) is True


def test_tool_free_pinned_projection_is_canonicalized_and_metadata_is_dropped() -> None:
    inbound = _envelope_body(stream=False)
    result = _apply_envelope(inbound)

    assert "client_metadata" not in result.effective_body
    assert result.effective_body["include"] == ["reasoning.encrypted_content"]
    assert result.effective_body["parallel_tool_calls"] is False
    assert result.effective_body["prompt_cache_key"] == "cache-opaque-123"
    assert result.effective_body["reasoning"] == {"effort": "low", "context": "all_turns"}
    assert result.effective_body["text"] == {"verbosity": "low"}
    assert result.effective_body["input"][0]["id"] == "msg_opaque_123"

    normalized = normalize_responses_upstream_request(
        result.effective_body,
        requested_model="classroom-codex",
        upstream_model="gpt-5.6-sol",
    )
    outbound = build_responses_upstream_body(normalized)
    assert outbound == {
        "model": "gpt-5.6-sol",
        "input": [
            {
                "id": "msg_opaque_123",
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "hello"}],
            }
        ],
        "max_output_tokens": 20,
        "stream": False,
        "store": False,
        "text": {"verbosity": "low"},
        "include": ["reasoning.encrypted_content"],
        "parallel_tool_calls": False,
        "prompt_cache_key": "cache-opaque-123",
        "reasoning": {"effort": "low", "context": "all_turns"},
    }


@pytest.mark.parametrize("effort", ["none", "minimal", "low", "medium", "high", "xhigh", "max", "ultra"])
def test_each_pinned_reasoning_effort_is_accepted(effort: str) -> None:
    result = _apply_envelope(
        _envelope_body(stream=False, reasoning={"effort": effort})
    )

    assert result.effective_body["reasoning"] == {"effort": effort}


@pytest.mark.parametrize("verbosity", ["low", "medium", "high"])
def test_each_pinned_text_verbosity_is_accepted(verbosity: str) -> None:
    result = _apply_envelope(
        _envelope_body(stream=False, text={"verbosity": verbosity})
    )

    assert result.effective_body["text"] == {"verbosity": verbosity}


def test_reasoning_context_boolean_parallel_and_utf8_cache_boundary_are_accepted() -> None:
    result = _apply_envelope(
        _envelope_body(
            stream=False,
            parallel_tool_calls=True,
            prompt_cache_key="ü" * 128,
            reasoning={"effort": "low", "context": "all_turns"},
        )
    )

    assert result.effective_body["parallel_tool_calls"] is True
    assert result.effective_body["prompt_cache_key"] == "ü" * 128
    assert result.effective_body["reasoning"] == {
        "effort": "low",
        "context": "all_turns",
    }


@pytest.mark.parametrize(
    ("overrides", "param"),
    [
        ({"include": "reasoning.encrypted_content"}, "include"),
        ({"include": []}, "include"),
        ({"include": ["output_text"]}, "include"),
        ({"include": ["reasoning.encrypted_content"] * 9}, "include"),
        ({"parallel_tool_calls": 0}, "parallel_tool_calls"),
        ({"prompt_cache_key": ""}, "prompt_cache_key"),
        ({"prompt_cache_key": "bad\ncache"}, "prompt_cache_key"),
        ({"prompt_cache_key": "x" * 257}, "prompt_cache_key"),
        ({"reasoning": "low"}, "reasoning"),
        ({"reasoning": {}}, "reasoning"),
        ({"reasoning": {"context": "all_turns"}}, "reasoning.effort"),
        ({"reasoning": {"summary": "auto"}}, "reasoning"),
        ({"reasoning": {"effort": "extreme"}}, "reasoning.effort"),
        ({"reasoning": {"effort": "low", "context": "turn"}}, "reasoning.context"),
        ({"text": {"verbosity": "max"}}, "text.verbosity"),
        ({"text": {"verbosity": 1}}, "text.verbosity"),
        ({"client_metadata": []}, "client_metadata"),
        ({"client_metadata": {"origin": "codex"}}, "client_metadata"),
        ({"client_metadata": {"session_id": 7}}, "client_metadata.session_id"),
        ({"client_metadata": {"session_id": "bad\u007fvalue"}}, "client_metadata.session_id"),
        ({"client_metadata": {"session_id": "x" * 4097}}, "client_metadata.session_id"),
        (
            {
                "client_metadata": {
                    "session_id": "s" * 3000,
                    "thread_id": "t" * 3000,
                    "turn_id": "u" * 3000,
                }
            },
            "client_metadata",
        ),
        (
            {
                "input": [
                    {"type": "message", "id": "", "role": "user", "content": "hello"}
                ]
            },
            "input[0].id",
        ),
        (
            {
                "input": [
                    {
                        "type": "message",
                        "id": "message id",
                        "role": "user",
                        "content": "hello",
                    }
                ]
            },
            "input[0].id",
        ),
        (
            {
                "input": [
                    {
                        "type": "message",
                        "id": "https://example.test/id",
                        "role": "user",
                        "content": "hello",
                    }
                ]
            },
            "input[0].id",
        ),
        (
            {
                "input": [
                    {"type": "message", "id": "sk-secret", "role": "user", "content": "hello"}
                ]
            },
            "input[0].id",
        ),
        (
            {
                "input": [
                    {"type": "message", "id": "ü", "role": "user", "content": "hello"}
                ]
            },
            "input[0].id",
        ),
        (
            {
                "input": [
                    {"type": "message", "id": "x" * 129, "role": "user", "content": "hello"}
                ]
            },
            "input[0].id",
        ),
    ],
)
def test_envelope_field_validation_is_bounded_and_safe(
    overrides: dict[str, object],
    param: str,
) -> None:
    with pytest.raises(RequestPolicyError) as exc_info:
        _apply_envelope(_envelope_body(stream=False, **overrides))

    assert exc_info.value.error_code == "responses_codex_envelope_invalid"
    assert exc_info.value.param == param
    assert CLIENT_METADATA_CANARY not in str(exc_info.value)


@pytest.mark.parametrize(
    "overrides",
    [
        {"client_metadata": {CLIENT_METADATA_CANARY: "value"}},
        {"prompt_cache_key": f"bad\n{PROMPT_CACHE_CANARY}"},
        {
            "input": [
                {
                    "type": "message",
                    "id": f"sk-{MESSAGE_ID_CANARY}",
                    "role": "user",
                    "content": "hello",
                }
            ]
        },
    ],
)
def test_envelope_validation_errors_never_echo_private_values(
    overrides: dict[str, object],
) -> None:
    with pytest.raises(RequestPolicyError) as exc_info:
        _apply_envelope(_envelope_body(stream=False, **overrides))

    evidence = str(exc_info.value)
    assert CLIENT_METADATA_CANARY not in evidence
    assert PROMPT_CACHE_CANARY not in evidence
    assert MESSAGE_ID_CANARY not in evidence


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"additional_tools": []}, "responses_field_not_supported"),
        (
            {
                "input": [
                    {"type": "additional_tools", "tools": [], "role": "developer"}
                ]
            },
            "responses_codex_client_tools_not_allowed",
        ),
        (
            {"tools": [{"type": "namespace", "name": "functions", "tools": []}]},
            "responses_hosted_tool_not_supported",
        ),
        ({"tool_choice": "none"}, "responses_tool_choice_invalid"),
        ({"background": True}, "responses_background_not_supported"),
    ],
)
def test_envelope_gate_does_not_enable_tool_or_authority_surfaces(
    overrides: dict[str, object],
    code: str,
) -> None:
    with pytest.raises(RequestPolicyError) as exc_info:
        _apply_envelope(_envelope_body(stream=False, **overrides))

    assert exc_info.value.error_code == code


def test_route_capability_is_default_false_and_explicit_true_only() -> None:
    defaults = default_responses_capabilities()
    assert defaults["codex_request_envelope"] is False

    with pytest.raises(RequestPolicyError) as exc_info:
        enforce_responses_route_capabilities(
            route_capabilities={"responses": defaults},
            codex_request_envelope_requested=True,
        )
    assert exc_info.value.error_code == "responses_route_capability_not_supported"

    enabled = dict(defaults)
    enabled["codex_request_envelope"] = True
    enforce_responses_route_capabilities(
        route_capabilities={"responses": enabled},
        codex_request_envelope_requested=True,
    )

    enabled["codex_future_envelope"] = True
    with pytest.raises(RequestPolicyError) as exc_info:
        enforce_responses_route_capabilities(
            route_capabilities={"responses": enabled},
            codex_request_envelope_requested=True,
        )
    assert exc_info.value.error_code == "responses_route_capability_invalid"


def test_envelope_and_message_ids_increase_estimate_without_exposing_values() -> None:
    ordinary = ResponsesRequestPolicy(Settings()).apply(_ordinary_body())
    envelope = _apply_envelope(_envelope_body(stream=False))

    assert envelope.estimated_input_tokens > ordinary.estimated_input_tokens
    assert envelope.estimated_non_message_input_bytes > 0
    assert set(envelope.estimated_non_message_input_fields) == {
        "include",
        "input[].id",
        "parallel_tool_calls",
        "prompt_cache_key",
        "reasoning",
        "text",
    }
    evidence = repr(
        (
            envelope.estimated_non_message_input_bytes,
            envelope.estimated_non_message_input_tokens,
            envelope.estimated_non_message_input_fields,
        )
    )
    assert "cache-opaque-123" not in evidence
    assert "msg_opaque_123" not in evidence


def test_normalized_contract_is_deep_copy_isolated_and_rejects_unapproved_fields() -> None:
    result = _apply_envelope(_envelope_body(stream=False))
    normalized = normalize_responses_upstream_request(
        result.effective_body,
        requested_model="classroom-codex",
        upstream_model="gpt-5.6-sol",
    )
    first = build_responses_upstream_body(normalized)
    first["reasoning"]["effort"] = "mutated"
    first["input"][0]["id"] = "mutated"
    second = build_responses_upstream_body(normalized)

    assert second["reasoning"]["effort"] == "low"
    assert second["input"][0]["id"] == "msg_opaque_123"
    assert "client_metadata" not in normalized.__dataclass_fields__

    unsafe = dict(result.effective_body)
    unsafe["client_metadata"] = {"session_id": "must-not-pass"}
    with pytest.raises(ValueError, match="unapproved top-level fields"):
        normalize_responses_upstream_request(
            unsafe,
            requested_model="classroom-codex",
            upstream_model="gpt-5.6-sol",
        )


def test_key_denial_precedes_route_and_all_later_side_effects(monkeypatch) -> None:
    import slaif_gateway.services.responses_gateway as gateway

    calls: list[str] = []

    async def _unexpected_route(**kwargs):
        calls.append("route")
        raise AssertionError("route should not be called")

    monkeypatch.setattr(gateway, "_resolve_responses_route", _unexpected_route)

    with pytest.raises(OpenAICompatibleError) as exc_info:
        asyncio.run(
            gateway.handle_response_create(
                payload=ResponsesCreateRequest.model_validate(_envelope_body(stream=False)),
                authenticated_key=_authenticated_key(responses_policy=None),
                settings=Settings(),
            )
        )

    assert exc_info.value.code == "responses_codex_envelope_not_allowed"
    assert calls == []


def test_invalid_envelope_shape_precedes_route_and_all_later_side_effects(monkeypatch) -> None:
    import slaif_gateway.services.responses_gateway as gateway

    calls: list[str] = []

    async def _unexpected_route(**kwargs):
        calls.append("route")
        raise AssertionError("route should not be called")

    monkeypatch.setattr(gateway, "_resolve_responses_route", _unexpected_route)

    with pytest.raises(OpenAICompatibleError) as exc_info:
        asyncio.run(
            gateway.handle_response_create(
                payload=ResponsesCreateRequest.model_validate(
                    _envelope_body(stream=False, prompt_cache_key="bad\ncache")
                ),
                authenticated_key=_authenticated_key(responses_policy=_key_policy()),
                settings=Settings(),
            )
        )

    assert exc_info.value.code == "responses_codex_envelope_invalid"
    assert calls == []


def test_route_denial_precedes_redis_pricing_quota_and_provider(monkeypatch) -> None:
    import slaif_gateway.services.responses_gateway as gateway

    calls: list[str] = []

    async def _deny_route(**kwargs):
        calls.append("route")
        assert kwargs["codex_request_envelope_requested"] is True
        capabilities = default_responses_capabilities()
        with pytest.raises(RequestPolicyError):
            enforce_responses_route_capabilities(
                route_capabilities={"responses": capabilities},
                codex_request_envelope_requested=True,
            )
        raise OpenAICompatibleError(
            "This model route does not support the Codex request envelope.",
            code="responses_route_capability_not_supported",
        )

    async def _unexpected_rate(**kwargs):
        calls.append("redis")

    async def _unexpected_quota(**kwargs):
        calls.append("quota")

    def _unexpected_provider(*args, **kwargs):
        calls.append("provider")
        raise AssertionError("provider should not be called")

    monkeypatch.setattr(gateway, "_resolve_responses_route", _deny_route)
    monkeypatch.setattr(gateway, "_reserve_redis_rate_limit", _unexpected_rate)
    monkeypatch.setattr(gateway, "_reserve_responses_quota", _unexpected_quota)
    monkeypatch.setattr(gateway, "get_provider_adapter", _unexpected_provider)

    with pytest.raises(OpenAICompatibleError) as exc_info:
        asyncio.run(
            gateway.handle_response_create(
                payload=ResponsesCreateRequest.model_validate(_envelope_body(stream=False)),
                authenticated_key=_authenticated_key(responses_policy=_key_policy()),
                settings=Settings(),
            )
        )

    assert exc_info.value.code == "responses_route_capability_not_supported"
    assert calls == ["route"]


def test_dual_gated_runtime_forwards_only_canonical_body_and_drops_metadata_privately(
    monkeypatch,
    caplog,
) -> None:
    import slaif_gateway.services.responses_gateway as gateway

    inbound = _envelope_body(
        stream=False,
        client_metadata={"session_id": CLIENT_METADATA_CANARY},
        prompt_cache_key=PROMPT_CACHE_CANARY,
        input=[
            {
                "id": MESSAGE_ID_CANARY,
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "hello"}],
            }
        ],
    )
    captured_provider_bodies: list[dict[str, object]] = []
    captured_policy_evidence: list[tuple[int, tuple[str, ...]]] = []
    captured_ledger_results: list[FinalizedAccountingResult] = []
    captured_metric_evidence: list[dict[str, object]] = []

    async def _resolve(**kwargs):
        assert kwargs["codex_request_envelope_requested"] is True
        return _route(codex_request_envelope=True)

    async def _reserve_rate(**kwargs):
        return None

    async def _reserve_quota(**kwargs):
        policy = kwargs["policy_result"]
        captured_policy_evidence.append(
            (policy.estimated_non_message_input_bytes, policy.estimated_non_message_input_fields)
        )
        estimate = ChatCostEstimate(
            provider="openai",
            requested_model="classroom-codex",
            resolved_model="gpt-5.6-sol",
            native_currency="EUR",
            estimated_input_tokens=policy.estimated_input_tokens,
            estimated_output_tokens=20,
            estimated_input_cost_native=Decimal("0.001"),
            estimated_output_cost_native=Decimal("0.001"),
            estimated_total_cost_native=Decimal("0.002"),
            estimated_total_cost_eur=Decimal("0.002"),
            pricing_rule_id=None,
            fx_rate_id=None,
        )
        reservation = QuotaReservationResult(
            reservation_id=uuid.uuid4(),
            gateway_key_id=kwargs["authenticated_key"].gateway_key_id,
            request_id=kwargs["request_id"],
            reserved_cost_eur=Decimal("0.002"),
            reserved_tokens=policy.estimated_input_tokens + 20,
            status="pending",
            expires_at=datetime.now(UTC) + timedelta(minutes=15),
        )
        return SimpleNamespace(
            cost_estimate=estimate,
            reservation=reservation,
            live_burn_budget=None,
        )

    class _Adapter:
        async def forward_response(self, request):
            captured_provider_bodies.append(dict(request.body))
            return ProviderResponse(
                provider="openai",
                upstream_model="gpt-5.6-sol",
                status_code=200,
                json_body={"id": "resp_test", "object": "response"},
                usage=ProviderUsage(prompt_tokens=5, completion_tokens=2, total_tokens=7),
            )

    async def _finalize(**kwargs):
        reservation = kwargs["reservation"]
        result = FinalizedAccountingResult(
            usage_ledger_id=uuid.uuid4(),
            reservation_id=reservation.reservation_id,
            gateway_key_id=reservation.gateway_key_id,
            request_id=reservation.request_id,
            estimated_cost_eur=Decimal("0.002"),
            actual_cost_eur=Decimal("0.001"),
            actual_cost_native=Decimal("0.001"),
            native_currency="EUR",
            prompt_tokens=5,
            completion_tokens=2,
            total_tokens=7,
            accounting_status="finalized",
        )
        captured_ledger_results.append(result)
        return result

    def _record_metrics(**kwargs):
        captured_metric_evidence.append(dict(kwargs))

    monkeypatch.setattr(gateway, "_resolve_responses_route", _resolve)
    monkeypatch.setattr(gateway, "_reserve_redis_rate_limit", _reserve_rate)
    monkeypatch.setattr(gateway, "_reserve_responses_quota", _reserve_quota)
    monkeypatch.setattr(gateway, "get_provider_adapter", lambda route, settings: _Adapter())
    monkeypatch.setattr(gateway, "_finalize_successful_response", _finalize)
    monkeypatch.setattr(gateway, "_record_success_metrics", _record_metrics)

    response = asyncio.run(
        gateway.handle_response_create(
            payload=ResponsesCreateRequest.model_validate(inbound),
            authenticated_key=_authenticated_key(responses_policy=_key_policy()),
            settings=Settings(),
        )
    )

    assert response.status_code == 200
    assert len(captured_provider_bodies) == 1
    provider_body = captured_provider_bodies[0]
    assert provider_body["model"] == "gpt-5.6-sol"
    assert provider_body["prompt_cache_key"] == PROMPT_CACHE_CANARY
    assert provider_body["input"][0]["id"] == MESSAGE_ID_CANARY
    assert "client_metadata" not in provider_body
    safe_surfaces = repr(
        (
            captured_policy_evidence,
            captured_ledger_results,
            captured_metric_evidence,
            caplog.records,
            response.body,
            response.headers,
        )
    )
    for canary in (CLIENT_METADATA_CANARY, PROMPT_CACHE_CANARY, MESSAGE_ID_CANARY):
        assert canary not in safe_surfaces


def test_full_captured_profile_still_has_separate_tool_namespace_and_choice_gaps() -> None:
    from slaif_gateway.services.responses_gateway import _ALLOWED_RESPONSES_STREAM_EVENT_TYPES

    fixture = json.loads(FIXTURE.read_bytes())
    request = fixture["capture"]["request"]
    compatibility = capture.build_gateway_compatibility(request)

    assert compatibility == fixture["gateway_compatibility"]
    assert compatibility["status"] == "not_compatible"
    assert any(item["name"] == "tool_choice" for item in compatibility["top_level_fields"]["rejected"])
    assert any(item["name"] == "additional_tools" for item in compatibility["input_item_types"]["rejected"])
    assert any(
        item["type"] == "namespace" and item["status"] == "rejected"
        for item in compatibility["tools"]
    )
    assert {
        "response.function_call_arguments.delta",
        "response.output_item.added",
        "response.reasoning_summary_text.delta",
    }.isdisjoint(_ALLOWED_RESPONSES_STREAM_EVENT_TYPES)


def test_immutable_004_fixture_and_frozen_classifier_remain_exact() -> None:
    assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == FIXTURE_SHA256
    fixture = json.loads(FIXTURE.read_bytes())
    assert capture.build_gateway_compatibility(fixture["capture"]["request"]) == fixture[
        "gateway_compatibility"
    ]
    source = Path(capture.__file__).read_text()
    assert "_BASELINE_004_SUPPORTED_FIELDS" in source
    assert "from slaif_gateway.services.responses_request_policy import" not in source
