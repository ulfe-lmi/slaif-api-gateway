"""Synthetic schema regressions for the operator-reported Sites rejection."""

import copy
from dataclasses import replace

import pytest

from slaif_gateway.config import Settings
from slaif_gateway.modules.clients.codex_0162 import (
    CODEX_0162_CLIENT_MODULE,
    codex_0162_lower_initial_additional_tools,
)
from slaif_gateway.services.responses_request_policy import (
    ResponsesRequestPolicy,
    ResponsesRequestPolicyError,
)


def _body():
    return {
        "model": "qwen38-27b",
        "input": [
            {
                "type": "additional_tools",
                "role": "developer",
                "tools": [
                    {
                        "type": "namespace",
                        "name": "mcp__codex_apps__sites",
                        "tools": [
                            {
                                "type": "function",
                                "name": "_update_environment_variables",
                                "parameters": {
                                    "type": "object",
                                    "properties": {
                                        "secret": {"type": "boolean"},
                                        "headers": {
                                            "type": "object",
                                            "properties": {"authorization": {"type": "string"}},
                                        },
                                        "connector_id": {"type": "string"},
                                    },
                                },
                            }
                        ],
                    }
                ],
            },
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "synthetic regression"}],
            },
        ],
    }


def _tool(body):
    return body["input"][0]["tools"][0]["tools"][0]


def _apply(body, *, spec=None, grants=True):
    module = CODEX_0162_CLIENT_MODULE
    return ResponsesRequestPolicy(Settings(), client_spec=spec or module.policy_spec).apply(
        module.normalize_responses(body).body,
        allow_codex_request_envelope=grants,
        allow_codex_client_tools=grants,
    )


def test_parameter_names_are_preserved_through_policy_and_translation():
    body = _body()
    original = copy.deepcopy(body)
    result = _apply(body)
    assert body == original
    assert _tool(result.effective_body)["parameters"] == _tool(body)["parameters"]
    lowered = codex_0162_lower_initial_additional_tools(result.effective_body)
    assert lowered["tools"][0]["tools"][0]["parameters"] == _tool(body)["parameters"]


@pytest.mark.parametrize("field", ["server_url", "authorization", "headers", "require_approval"])
@pytest.mark.parametrize("location", ["tool", "schema", "property_schema"])
def test_actual_authority_fields_still_rejected(field, location):
    body = _body()
    target = _tool(body)
    if location == "schema":
        target = target["parameters"]
    elif location == "property_schema":
        target = target["parameters"]["properties"]["secret"]
    target[field] = "synthetic marker"
    with pytest.raises(ResponsesRequestPolicyError) as exc:
        _apply(body)
    assert exc.value.error_code == "responses_codex_client_tools_provider_authority_not_supported"


@pytest.mark.parametrize("hosted_type", ["web_search", "mcp", "code_interpreter"])
def test_nested_hosted_shapes_still_rejected(hosted_type):
    body = _body()
    _tool(body)["parameters"]["properties"]["secret"] = {"type": hosted_type}
    with pytest.raises(ResponsesRequestPolicyError) as exc:
        _apply(body)
    assert exc.value.error_code == "responses_codex_client_tools_provider_authority_not_supported"


def test_property_exemption_does_not_escape_parameters():
    body = _body()
    _tool(body)["properties"] = {"secret": {"type": "boolean"}}
    with pytest.raises(ResponsesRequestPolicyError):
        _apply(body)


def test_missing_key_grants_still_rejected():
    with pytest.raises(ResponsesRequestPolicyError) as exc:
        _apply(_body(), grants=False)
    assert exc.value.error_code == "responses_codex_client_tools_not_allowed"


def test_previous_profile_spec_retains_old_authority_scan():
    spec = replace(CODEX_0162_CLIENT_MODULE.policy_spec, allow_schema_property_names=False)
    with pytest.raises(ResponsesRequestPolicyError) as exc:
        _apply(_body(), spec=spec)
    assert exc.value.error_code == "responses_codex_client_tools_provider_authority_not_supported"
