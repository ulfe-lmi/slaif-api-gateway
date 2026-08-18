from __future__ import annotations

from dataclasses import replace
import uuid

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

from slaif_gateway.api.openai_compat import _reject_non_identity_content_encoding
from slaif_gateway.config import Settings
from slaif_gateway.main import create_app
from slaif_gateway.schemas.providers import ProviderResponse, ProviderUsage
from slaif_gateway.services.responses_gateway import _validate_compact_response
from slaif_gateway.services.responses_request_policy import (
    ResponsesRequestPolicy,
    codex_replay_request_candidates,
)
from slaif_gateway.services.responses_route_capabilities import (
    default_responses_capabilities,
    enforce_responses_route_capabilities,
    parse_codex_compaction_compatible_route_ids,
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
        invalid = replace(response, json_body={"output": output})
        with pytest.raises(Exception) as exc_info:
            _validate_compact_response(invalid, codex_compaction=True)
        assert getattr(exc_info.value, "error_code", None) == (
            "responses_codex_compaction_response_invalid"
        )


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
