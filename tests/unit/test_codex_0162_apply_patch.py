"""Bounded custom apply_patch declaration, transport, replay, and stream tests."""

from dataclasses import replace

import pytest

from slaif_gateway.config import Settings
from slaif_gateway.modules.clients.codex_0162 import (
    CODEX_0162_CLIENT_MODULE,
    codex_0162_lower_initial_additional_tools,
)
from slaif_gateway.providers.streaming import (
    ResponsesStreamEventValidator,
    ResponsesStreamValidationProfile,
)
from slaif_gateway.services.responses_request_policy import (
    ResponsesRequestPolicy,
    ResponsesRequestPolicyError,
    codex_client_tool_declarations,
)


def _body():
    return {
        "model": "qwen38-27b",
        "stream": True,
        "input": [
            {
                "type": "additional_tools",
                "role": "developer",
                "tools": [
                    {
                        "type": "namespace",
                        "name": "functions",
                        "tools": [
                            {
                                "type": "custom",
                                "name": "apply_patch",
                                "format": {
                                    "type": "grammar",
                                    "syntax": "lark",
                                    "definition": "start: /.+/",
                                },
                            }
                        ],
                    }
                ],
            },
            {"type": "message", "role": "user", "content": "Synthetic fixture"},
        ],
    }


def _apply(body, spec=None):
    module = CODEX_0162_CLIENT_MODULE
    return ResponsesRequestPolicy(Settings(), client_spec=spec or module.policy_spec).apply(
        module.normalize_responses(body).body,
        allow_codex_request_envelope=True,
        allow_codex_client_tools=True,
        allow_codex_streaming_tool_events=True,
    )


def _tool(body):
    return body["input"][0]["tools"][0]["tools"][0]


def test_apply_patch_grammar_preserved_for_backend():
    body = _body()
    accepted = _apply(body).effective_body
    lowered = codex_0162_lower_initial_additional_tools(accepted)
    assert lowered["tools"][0]["tools"][0] == _tool(body)
    assert ("functions", "apply_patch", "custom") in codex_client_tool_declarations(accepted)


@pytest.mark.parametrize(
    "namespace,name",
    [
        ("functions", "other"),
        ("multi_agent_v1", "apply_patch"),
        ("mcp__codex_apps__sites", "apply_patch"),
    ],
)
def test_custom_exception_is_exact(namespace, name):
    body = _body()
    body["input"][0]["tools"][0]["name"] = namespace
    _tool(body)["name"] = name
    with pytest.raises(ResponsesRequestPolicyError):
        _apply(body)


@pytest.mark.parametrize(
    "format_value",
    [
        None,
        {"type": "text"},
        {"type": "grammar", "syntax": "unknown", "definition": "start"},
        {"type": "grammar", "syntax": "lark", "definition": ""},
    ],
)
def test_grammar_stays_required_and_bounded(format_value):
    body = _body()
    if format_value is None:
        del _tool(body)["format"]
    else:
        _tool(body)["format"] = format_value
    with pytest.raises(ResponsesRequestPolicyError):
        _apply(body)


def test_apply_patch_call_output_replay():
    body = _body()
    body["input"] += [
        {
            "type": "custom_tool_call",
            "id": "ctc_patch_1",
            "call_id": "call_patch_1",
            "namespace": "functions",
            "name": "apply_patch",
            "input": "synthetic patch",
        },
        {
            "type": "custom_tool_call_output",
            "call_id": "call_patch_1",
            "output": "synthetic result",
        },
    ]
    result = _apply(body)
    assert result.effective_body["input"][-2]["name"] == "apply_patch"
    old = replace(CODEX_0162_CLIENT_MODULE.policy_spec, custom_client_tools=frozenset())
    with pytest.raises(ResponsesRequestPolicyError):
        _apply(body, old)


def test_apply_patch_stream_requires_selected_profile_and_declaration():
    event = {
        "type": "response.output_item.done",
        "output_index": 0,
        "item": {
            "type": "custom_tool_call",
            "id": "ctc_patch_1",
            "status": "completed",
            "call_id": "call_patch_1",
            "namespace": "functions",
            "name": "apply_patch",
            "input": "synthetic patch",
        },
    }
    profile = ResponsesStreamValidationProfile(
        codex_streaming_tool_events=True,
        declared_client_tools=frozenset({("functions", "apply_patch", "custom")}),
        custom_client_tools=CODEX_0162_CLIENT_MODULE.policy_spec.custom_client_tools,
    )
    assert ResponsesStreamEventValidator(profile).validate(event)
    assert not ResponsesStreamEventValidator(
        replace(profile, custom_client_tools=frozenset())
    ).validate(event)
    assert not ResponsesStreamEventValidator(
        replace(profile, declared_client_tools=frozenset())
    ).validate(event)
