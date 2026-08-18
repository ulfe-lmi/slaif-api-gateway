from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
import uuid

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

from slaif_gateway.api.openai_compat import _reject_non_identity_content_encoding
from slaif_gateway.config import Settings
from slaif_gateway.main import create_app
from slaif_gateway.schemas.openai import ResponsesCreateRequest
from slaif_gateway.schemas.providers import ProviderResponse, ProviderUsage
from slaif_gateway.services import responses_gateway
from slaif_gateway.services.codex_replay_service import CodexReplayReferenceError
from slaif_gateway.services.responses_gateway import (
    _validate_compact_response,
    handle_response_compact,
)
from slaif_gateway.services.responses_request_policy import (
    ResponsesRequestPolicy,
    codex_replay_request_candidates,
)
from slaif_gateway.services.responses_route_capabilities import (
    default_responses_capabilities,
    enforce_responses_route_capabilities,
    parse_codex_compaction_compatible_route_ids,
)
from scripts.verify_codex_context_compaction import (
    VerificationError,
    _validate_captured_compact_policy,
)


def _compact_body() -> dict[str, object]:
    return {
        "model": "gpt-5.6-sol",
        "input": [
            {"type": "message", "role": "user", "content": "bounded"},
            {
                "type": "compaction",
                "id": "cmp_safe_1",
                "encrypted_content": "opaque-value",
            },
        ],
        "parallel_tool_calls": False,
        "reasoning": {"effort": "high", "context": "all_turns"},
        "prompt_cache_key": "safe-session-key",
        "text": {"verbosity": "medium"},
    }


def _pinned_compact_additional_tools(description_bytes: int) -> dict[str, object]:
    def function(name: str) -> dict[str, object]:
        return {
            "type": "function",
            "name": name,
            "description": f"bounded-{name}",
            "parameters": {"type": "object", "properties": {}},
        }

    return {
        "type": "additional_tools",
        "role": "developer",
        "tools": [
            {
                "type": "namespace",
                "name": "functions",
                "tools": [
                    {
                        "type": "custom",
                        "name": "exec",
                        "description": "d" * description_bytes,
                        "format": {
                            "type": "grammar",
                            "syntax": "lark",
                            "definition": "start: WORD\nWORD: /[A-Za-z]+/",
                        },
                    },
                    function("wait"),
                    function("request_user_input"),
                ],
            },
            {
                "type": "namespace",
                "name": "collaboration",
                "tools": [
                    function("followup_task"),
                    function("interrupt_agent"),
                    function("list_agents"),
                    function("send_message"),
                    function("spawn_agent"),
                    function("wait_agent"),
                ],
            },
        ],
    }


def test_codex_compact_requires_independent_key_gate() -> None:
    with pytest.raises(Exception) as exc_info:
        ResponsesRequestPolicy(Settings()).apply_compact(_compact_body())
    assert getattr(exc_info.value, "error_code", None) == ("responses_codex_compaction_not_allowed")


def test_codex_compact_canonicalizes_pinned_v1_fields_and_composite_candidate() -> None:
    result = ResponsesRequestPolicy(Settings()).apply_compact(
        _compact_body(),
        allow_codex_compaction=True,
    )
    assert set(result.effective_body) == {
        "model",
        "input",
        "parallel_tool_calls",
        "reasoning",
        "prompt_cache_key",
        "text",
    }
    candidates = codex_replay_request_candidates(result.effective_body)
    assert len(candidates) == 1
    assert candidates[0].item_kind == "compaction"
    assert candidates[0].encrypted_content == "opaque-value"


def test_codex_compact_accepts_pinned_18_137_byte_child_description() -> None:
    body = _compact_body()
    input_items = body["input"]
    assert isinstance(input_items, list)
    input_items.insert(0, _pinned_compact_additional_tools(18_137))

    result = ResponsesRequestPolicy(Settings()).apply_compact(
        body,
        allow_codex_compaction=True,
    )

    description = result.effective_body["input"][0]["tools"][0]["tools"][0]["description"]
    assert len(description.encode("utf-8")) == 18_137
    assert result.estimated_non_message_input_bytes >= 18_137
    assert "input[].additional_tools" in result.estimated_non_message_input_fields


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("stream", False),
        ("store", False),
        ("include", []),
        ("tool_choice", "auto"),
        ("background", False),
        ("previous_response_id", "resp_safe"),
        ("compaction_trigger", 1000),
    ],
)
def test_codex_compact_keeps_ordinary_only_and_v2_fields_closed(
    field: str,
    value: object,
) -> None:
    body = _compact_body()
    body[field] = value
    with pytest.raises(Exception) as exc_info:
        ResponsesRequestPolicy(Settings()).apply_compact(
            body,
            allow_codex_compaction=True,
        )
    assert getattr(exc_info.value, "param", None) == field


def test_codex_compact_provider_response_requires_one_exact_opaque_item_and_usage() -> None:
    response = ProviderResponse(
        provider="openai",
        upstream_model="gpt-5.6-sol",
        status_code=200,
        json_body={
            "output": [
                {
                    "type": "compaction",
                    "id": "cmp_safe_2",
                    "encrypted_content": "opaque-returned-value",
                }
            ],
            "usage": {"input_tokens": 10, "output_tokens": 2, "total_tokens": 12},
        },
        usage=ProviderUsage(prompt_tokens=10, completion_tokens=2, total_tokens=12),
    )
    candidate = _validate_compact_response(response, codex_compaction=True)
    assert candidate is not None
    assert candidate.item_kind == "compaction"

    for output in (
        [],
        [
            {
                "type": "compaction",
                "id": "cmp_safe_2",
                "encrypted_content": "opaque",
            },
            {
                "type": "compaction",
                "id": "cmp_safe_3",
                "encrypted_content": "opaque",
            },
        ],
        [{"type": "compaction", "id": "cmp_safe_2", "encrypted_content": ""}],
        [
            {
                "type": "compaction",
                "id": "cmp_safe_2",
                "encrypted_content": "opaque",
                "content": "not-allowed",
            }
        ],
    ):
        invalid = replace(response, json_body={**response.json_body, "output": output})
        with pytest.raises(Exception) as exc_info:
            _validate_compact_response(invalid, codex_compaction=True)
        assert getattr(exc_info.value, "error_code", None) == (
            "responses_codex_compaction_response_invalid"
        )

    missing_usage = replace(
        response,
        json_body={"output": response.json_body["output"]},
    )
    with pytest.raises(Exception) as exc_info:
        _validate_compact_response(missing_usage, codex_compaction=True)
    assert getattr(exc_info.value, "error_code", None) == "responses_compact_usage_missing"


def test_codex_compact_provider_response_accepts_only_safe_optional_metadata() -> None:
    response = ProviderResponse(
        provider="openai",
        upstream_model="gpt-5.6-sol",
        status_code=200,
        json_body={
            "id": "resp_compact_safe",
            "object": "response.compaction",
            "created_at": 1_800_000_000,
            "output": [
                {
                    "type": "compaction",
                    "id": "cmp_safe_2",
                    "encrypted_content": "opaque-returned-value",
                }
            ],
            "usage": {
                "input_tokens": 10,
                "input_tokens_details": {
                    "cached_tokens": 2,
                    "cache_write_tokens": 1,
                },
                "output_tokens": 2,
                "output_tokens_details": {"reasoning_tokens": 1},
                "total_tokens": 12,
            },
        },
        usage=ProviderUsage(
            prompt_tokens=10,
            completion_tokens=2,
            total_tokens=12,
            cached_tokens=2,
            cache_write_tokens=1,
            reasoning_tokens=1,
        ),
    )
    assert _validate_compact_response(response, codex_compaction=True) is not None


@pytest.mark.parametrize(
    "update",
    [
        {"unknown": "plaintext"},
        {"id": "bad\x00id"},
        {"object": "response"},
        {"created_at": True},
        {"created_at": -1},
        {"usage": {"input_tokens": 10, "output_tokens": 2}},
        {
            "usage": {
                "input_tokens": 10,
                "output_tokens": 2,
                "total_tokens": 13,
            }
        },
        {
            "usage": {
                "input_tokens": 10,
                "output_tokens": 2,
                "total_tokens": 12,
                "billable_secret_tokens": 1,
            }
        },
    ],
)
def test_codex_compact_provider_response_rejects_unknown_or_malformed_envelope(
    update: dict[str, object],
) -> None:
    response = ProviderResponse(
        provider="openai",
        upstream_model="gpt-5.6-sol",
        status_code=200,
        json_body={
            "output": [
                {
                    "type": "compaction",
                    "id": "cmp_safe_2",
                    "encrypted_content": "opaque-returned-value",
                }
            ],
            "usage": {"input_tokens": 10, "output_tokens": 2, "total_tokens": 12},
            **update,
        },
        usage=ProviderUsage(prompt_tokens=10, completion_tokens=2, total_tokens=12),
    )
    with pytest.raises(Exception) as exc_info:
        _validate_compact_response(response, codex_compaction=True)
    assert getattr(exc_info.value, "error_code", None) == (
        "responses_codex_compaction_response_invalid"
    )
    assert "plaintext" not in str(exc_info.value)


def test_captured_compact_body_runs_through_gateway_policy_without_echo() -> None:
    assert _validate_captured_compact_policy(_compact_body()) is True
    invalid = _compact_body()
    invalid["private_canary"] = "do-not-echo-this"
    with pytest.raises(VerificationError) as exc_info:
        _validate_captured_compact_policy(invalid)
    assert "do-not-echo-this" not in str(exc_info.value)


@pytest.mark.parametrize("encoding", ["gzip", "zstd", "br", "unknown"])
def test_responses_ingress_rejects_non_identity_content_encoding_without_body_echo(
    encoding: str,
) -> None:
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/v1/responses/compact",
            "headers": [(b"content-encoding", encoding.encode("ascii"))],
        }
    )
    with pytest.raises(Exception) as exc_info:
        _reject_non_identity_content_encoding(request)
    assert getattr(exc_info.value, "code", None) == "request_content_encoding_not_supported"
    assert "unknown" not in str(exc_info.value).lower()


def test_responses_ingress_allows_absent_or_identity_content_encoding() -> None:
    for headers in ([], [(b"content-encoding", b"identity")]):
        request = Request(
            {
                "type": "http",
                "method": "POST",
                "path": "/v1/responses",
                "headers": headers,
            }
        )
        assert _reject_non_identity_content_encoding(request) is None


@pytest.mark.parametrize("path", ["/v1/responses", "/v1/responses/compact"])
@pytest.mark.parametrize("encoding", ["gzip", "zstd", "unknown"])
def test_responses_routes_reject_non_identity_encoding_before_auth_or_side_effects(
    path: str,
    encoding: str,
) -> None:
    response = TestClient(create_app(Settings())).post(
        path,
        content=b'{"model":"private-model","input":"private-input"}',
        headers={
            "content-type": "application/json",
            "content-encoding": encoding,
        },
    )
    assert response.status_code == 415
    payload = response.json()
    assert payload["error"]["code"] == "request_content_encoding_not_supported"
    assert "private-model" not in response.text
    assert "private-input" not in response.text


def _codex_compact_route_capabilities() -> dict[str, object]:
    responses = default_responses_capabilities()
    responses.update(
        {
            "compact": True,
            "codex_request_envelope": True,
            "codex_client_tools": True,
            "codex_streaming_tool_events": True,
            "codex_encrypted_reasoning_replay": True,
            "codex_compaction": True,
        }
    )
    return {
        "responses": responses,
        "codex_limits": {
            "context_window_tokens": 1_050_000,
            "default_max_output_tokens": 32_768,
            "max_output_tokens": 128_000,
        },
    }


def test_codex_compaction_route_requires_all_gates_and_strict_limits() -> None:
    capabilities = _codex_compact_route_capabilities()
    enforce_responses_route_capabilities(
        route_capabilities=capabilities,
        compact_requested=True,
        codex_compaction_requested=True,
    )
    for missing in (
        "codex_request_envelope",
        "codex_client_tools",
        "codex_streaming_tool_events",
        "codex_encrypted_reasoning_replay",
        "codex_compaction",
    ):
        altered = _codex_compact_route_capabilities()
        altered["responses"][missing] = False  # type: ignore[index]
        with pytest.raises(Exception):
            enforce_responses_route_capabilities(
                route_capabilities=altered,
                compact_requested=True,
                codex_compaction_requested=True,
            )


def test_compact_route_compatibility_allowlist_is_explicit_uuid_only() -> None:
    source = uuid.uuid4()
    capabilities = _codex_compact_route_capabilities()
    capabilities["codex_compaction_compatible_route_ids"] = [str(source)]
    assert parse_codex_compaction_compatible_route_ids(capabilities) == frozenset({source})
    for invalid in (["not-a-uuid"], [str(source), str(source)], "not-a-list"):
        capabilities["codex_compaction_compatible_route_ids"] = invalid
        with pytest.raises(Exception):
            parse_codex_compaction_compatible_route_ids(capabilities)


def _compact_authenticated_key() -> SimpleNamespace:
    return SimpleNamespace(
        gateway_key_id=uuid.uuid4(),
        responses_policy={
            "version": 1,
            "allowed_capabilities": [
                "codex_request_envelope",
                "codex_client_tools",
                "codex_streaming_tool_events",
                "codex_encrypted_reasoning_replay",
                "codex_compaction",
            ],
        },
    )


def _valid_compact_provider_response() -> ProviderResponse:
    return ProviderResponse(
        provider="openai",
        upstream_model="gpt-5.6-sol",
        status_code=200,
        json_body={
            "object": "response.compaction",
            "output": [
                {
                    "type": "compaction",
                    "id": "cmp_response_canary",
                    "encrypted_content": "opaque-response-canary",
                }
            ],
            "usage": {"input_tokens": 10, "output_tokens": 2, "total_tokens": 12},
        },
        usage=ProviderUsage(prompt_tokens=10, completion_tokens=2, total_tokens=12),
    )


def _install_compact_handler_mocks(
    monkeypatch: pytest.MonkeyPatch,
    *,
    timeline: list[str],
    persistence_error: bool,
) -> dict[str, object]:
    captured: dict[str, object] = {}
    route = SimpleNamespace(
        provider="openai",
        resolved_model="gpt-5.6-sol",
        route_id=uuid.uuid4(),
        capabilities=_codex_compact_route_capabilities(),
    )

    async def verify_replay(**_kwargs):
        return SimpleNamespace(references=())

    async def resolve_route(**_kwargs):
        return route

    async def reserve_rate_limit(**_kwargs):
        return SimpleNamespace(concurrency_reserved=True)

    async def reserve_quota(**kwargs):
        captured["policy_result"] = kwargs["policy_result"]
        return SimpleNamespace(cost_estimate=object(), reservation=object())

    class Adapter:
        async def compact_response(self, provider_request):
            captured["provider_body"] = dict(provider_request.body)
            return _valid_compact_provider_response()

    async def observe_provider(**kwargs):
        return await kwargs["call"]()

    async def finalize(**_kwargs):
        timeline.append("accounting")
        return SimpleNamespace(usage_ledger_id=uuid.uuid4())

    async def persist(**_kwargs):
        if persistence_error:
            timeline.append("hmac-failed")
            raise CodexReplayReferenceError(
                "Codex replay references could not be persisted safely.",
                error_code="responses_codex_replay_persistence_failed",
            )
        timeline.append("hmac")
        return 1

    def metrics(**_kwargs):
        timeline.append("metrics")

    async def release(_reservation, *, suppress):
        timeline.append(f"release:{str(suppress).lower()}")

    monkeypatch.setattr(responses_gateway, "_verify_owned_codex_replay_references", verify_replay)
    monkeypatch.setattr(responses_gateway, "_resolve_responses_route", resolve_route)
    monkeypatch.setattr(responses_gateway, "_verify_codex_replay_route", lambda **_kwargs: None)
    monkeypatch.setattr(responses_gateway, "_reserve_redis_rate_limit", reserve_rate_limit)
    monkeypatch.setattr(responses_gateway, "_reserve_responses_quota", reserve_quota)
    monkeypatch.setattr(responses_gateway, "get_provider_adapter", lambda *_args: Adapter())
    monkeypatch.setattr(responses_gateway, "observe_provider_call", observe_provider)
    monkeypatch.setattr(responses_gateway, "_finalize_successful_response", finalize)
    monkeypatch.setattr(responses_gateway, "_persist_codex_replay_references", persist)
    monkeypatch.setattr(responses_gateway, "_record_success_metrics", metrics)
    monkeypatch.setattr(responses_gateway, "_release_rate_limit_concurrency", release)
    return captured


@pytest.mark.asyncio
async def test_compact_handler_reserves_route_max_and_orders_success_after_hmac(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    timeline: list[str] = []
    captured = _install_compact_handler_mocks(
        monkeypatch,
        timeline=timeline,
        persistence_error=False,
    )
    response = await handle_response_compact(
        payload=ResponsesCreateRequest.model_validate(_compact_body()),
        authenticated_key=_compact_authenticated_key(),
        settings=Settings(),
    )
    assert response.status_code == 200
    policy_result = captured["policy_result"]
    assert policy_result.requested_output_tokens == 128_000
    assert policy_result.effective_output_tokens == 128_000
    assert "max_output_tokens" not in policy_result.effective_body
    assert "max_output_tokens" not in captured["provider_body"]
    assert timeline == ["accounting", "hmac", "metrics", "release:false"]


@pytest.mark.asyncio
async def test_compact_hmac_failure_stays_charged_without_success_metric_or_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    timeline: list[str] = []
    _install_compact_handler_mocks(
        monkeypatch,
        timeline=timeline,
        persistence_error=True,
    )
    with pytest.raises(Exception) as exc_info:
        await handle_response_compact(
            payload=ResponsesCreateRequest.model_validate(_compact_body()),
            authenticated_key=_compact_authenticated_key(),
            settings=Settings(),
        )
    error = exc_info.value
    assert getattr(error, "status_code", None) == 500
    assert getattr(error, "code", None) == "responses_codex_replay_persistence_failed"
    assert timeline == ["accounting", "hmac-failed", "release:true"]
    assert "metrics" not in timeline
    assert "cmp_response_canary" not in str(error)
    assert "opaque-response-canary" not in str(error)
