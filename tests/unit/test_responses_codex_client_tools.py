from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from slaif_gateway.api.errors import OpenAICompatibleError
from slaif_gateway.config import Settings
from slaif_gateway.schemas.auth import AuthenticatedGatewayKey
from slaif_gateway.schemas.openai import ResponsesCreateRequest
from slaif_gateway.services.policy_errors import RequestPolicyError
from slaif_gateway.services.responses_request_policy import (
    ResponsesRequestPolicy,
    responses_codex_client_tools_allowed,
    responses_codex_client_tools_requested,
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
DESCRIPTION_CANARY = "private-client-tool-description-canary"
GRAMMAR_CANARY = "private-client-tool-grammar-canary"
PROPERTY_CANARY = "private_client_tool_property_canary"

TAXONOMY = {
    "functions": {
        "exec": "custom",
        "wait": "function",
        "request_user_input": "function",
    },
    "collaboration": {
        "followup_task": "function",
        "interrupt_agent": "function",
        "list_agents": "function",
        "send_message": "function",
        "spawn_agent": "function",
        "wait_agent": "function",
    },
}


def _function_tool(name: str) -> dict[str, object]:
    return {
        "type": "function",
        "name": name,
        "description": f"{DESCRIPTION_CANARY}-{name}",
        "parameters": {
            "type": "object",
            "properties": {PROPERTY_CANARY: {"type": "string"}},
            "required": [PROPERTY_CANARY],
            "additionalProperties": False,
        },
        "strict": True,
    }


def _request_user_input_parameters() -> dict[str, object]:
    return {
        "type": "object",
        "properties": {
            "questions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "header": {
                            "type": "string",
                            "description": f"short-ui-label-{DESCRIPTION_CANARY}",
                        },
                        "question": {"type": "string"},
                        "options": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "label": {"type": "string"},
                                    "description": {"type": "string"},
                                },
                                "required": ["label", "description"],
                                "additionalProperties": False,
                            },
                        },
                    },
                    "required": ["id", "header", "question", "options"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["questions"],
        "additionalProperties": False,
    }


def _additional_tools_item(*, reverse: bool = False) -> dict[str, object]:
    namespaces: list[dict[str, object]] = []
    for namespace_name, declared_tools in TAXONOMY.items():
        tools: list[dict[str, object]] = []
        for tool_name, tool_type in declared_tools.items():
            if tool_type == "custom":
                tools.append(
                    {
                        "type": "custom",
                        "name": tool_name,
                        "description": f"{DESCRIPTION_CANARY}-{tool_name}",
                        "format": {
                            "type": "grammar",
                            "syntax": "lark",
                            "definition": f"start: WORD // {GRAMMAR_CANARY}",
                        },
                    }
                )
            else:
                tools.append(_function_tool(tool_name))
        if reverse:
            tools.reverse()
        namespaces.append(
            {
                "type": "namespace",
                "name": namespace_name,
                "description": f"{DESCRIPTION_CANARY}-{namespace_name}",
                "tools": tools,
            }
        )
    if reverse:
        namespaces.reverse()
    return {"type": "additional_tools", "role": "developer", "tools": namespaces}


def _body(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "model": "classroom-codex",
        "input": [
            _additional_tools_item(),
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "hello"}],
            },
        ],
        "tool_choice": "auto",
        "max_output_tokens": 20,
        "store": False,
    }
    body.update(overrides)
    return body


def _apply(body: dict[str, object] | None = None, *, settings: Settings | None = None):
    return ResponsesRequestPolicy(settings or Settings()).apply(
        body or _body(),
        allow_codex_request_envelope=True,
        allow_codex_client_tools=True,
        allow_codex_streaming_tool_events=True,
    )


def _key_policy(*capabilities: str) -> dict[str, object]:
    return {
        "version": 1,
        "allowed_capabilities": ["text", "stateless", *capabilities],
    }


def _authenticated_key(*, responses_policy: dict[str, object] | None) -> AuthenticatedGatewayKey:
    now = datetime.now(UTC)
    return AuthenticatedGatewayKey(
        gateway_key_id=uuid.uuid4(),
        owner_id=uuid.uuid4(),
        cohort_id=None,
        public_key_id="public-codex-client-tools-test",
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


def _first_item(body: dict[str, object]) -> dict[str, object]:
    input_items = body["input"]
    assert isinstance(input_items, list)
    item = input_items[0]
    assert isinstance(item, dict)
    return item


def _namespaces(item: dict[str, object]) -> list[dict[str, object]]:
    namespaces = item["tools"]
    assert isinstance(namespaces, list)
    return namespaces


def _child_tool(
    body: dict[str, object],
    *,
    namespace_index: int,
    tool_index: int,
) -> dict[str, object]:
    tools = _namespaces(_first_item(body))[namespace_index]["tools"]
    assert isinstance(tools, list)
    tool = tools[tool_index]
    assert isinstance(tool, dict)
    return tool


def test_pinned_fixture_taxonomy_is_exact_and_immutable() -> None:
    assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == FIXTURE_SHA256
    fixture = json.loads(FIXTURE.read_bytes())
    shape = fixture["capture"]["request"]["field_shapes"]["input"]["items"][0]

    assert shape["type"] == "additional_tools"
    assert shape["role"] == "developer"
    captured = {
        namespace["name"]: {tool["name"]: tool["type"] for tool in namespace["tools"]}
        for namespace in shape["tools"]
    }
    assert captured == TAXONOMY


@pytest.mark.parametrize(
    ("allow_envelope", "allow_client_tools"),
    [(False, False), (True, False), (False, True)],
)
def test_additional_tools_requires_both_independent_key_gates(
    allow_envelope: bool,
    allow_client_tools: bool,
) -> None:
    with pytest.raises(RequestPolicyError) as exc_info:
        ResponsesRequestPolicy(Settings()).apply(
            _body(),
            allow_codex_request_envelope=allow_envelope,
            allow_codex_client_tools=allow_client_tools,
        )

    assert exc_info.value.error_code == "responses_codex_client_tools_not_allowed"
    assert exc_info.value.param == "input[0].type"


@pytest.mark.parametrize(
    ("policy", "expected"),
    [
        (None, False),
        (_key_policy("codex_request_envelope"), False),
        (_key_policy("codex_client_tools"), False),
        (_key_policy("codex_request_envelope", "codex_client_tools"), True),
        (
            _key_policy(
                "codex_request_envelope",
                "codex_client_tools",
                "codex_client_tools",
            ),
            False,
        ),
    ],
)
def test_key_policy_parser_requires_both_well_formed_capabilities(
    policy: object,
    expected: bool,
) -> None:
    assert responses_codex_client_tools_allowed(policy) is expected


def test_exact_taxonomy_is_canonicalized_estimated_and_reconstructed() -> None:
    inbound = _body(input=[_additional_tools_item(reverse=True), _body()["input"][1]])
    original = copy.deepcopy(inbound)
    result = _apply(inbound)
    item = result.effective_body["input"][0]

    assert responses_codex_client_tools_requested(inbound) is True
    assert [namespace["name"] for namespace in item["tools"]] == [
        "functions",
        "collaboration",
    ]
    assert [[tool["name"] for tool in namespace["tools"]] for namespace in item["tools"]] == [
        ["exec", "wait", "request_user_input"],
        [
            "followup_task",
            "interrupt_agent",
            "list_agents",
            "send_message",
            "spawn_agent",
            "wait_agent",
        ],
    ]
    assert result.estimated_non_message_input_bytes > 0
    assert "input[].additional_tools" in result.estimated_non_message_input_fields
    safe_evidence = repr(
        (
            result.estimated_non_message_input_bytes,
            result.estimated_non_message_input_tokens,
            result.estimated_non_message_input_fields,
        )
    )
    for private_value in (DESCRIPTION_CANARY, GRAMMAR_CANARY, PROPERTY_CANARY):
        assert private_value not in safe_evidence

    normalized = normalize_responses_upstream_request(
        result.effective_body,
        requested_model="classroom-codex",
        upstream_model="gpt-5.6-sol",
    )
    first = build_responses_upstream_body(normalized)
    first["input"][0]["tools"][0]["tools"][0]["name"] = "mutated"
    second = build_responses_upstream_body(normalized)
    assert second["input"][0] == item
    assert second["model"] == "gpt-5.6-sol"
    assert inbound == original


def test_streaming_declarations_are_admitted_for_separate_event_profile() -> None:
    result = _apply(_body(stream=True))

    assert result.effective_body["stream"] is True


def test_all_captured_request_shapes_compose_after_objective_007() -> None:
    body = _body(
        input=[
            _additional_tools_item(),
            {
                "id": "msg_developer_1",
                "type": "message",
                "role": "developer",
                "content": [{"type": "input_text", "text": "developer context"}],
            },
            {
                "id": "msg_user_1",
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "user request"}],
            },
        ],
        client_metadata={
            "x-codex-installation-id": "installation-1",
            "session_id": "session-1",
            "thread_id": "thread-1",
            "turn_id": "turn-1",
            "x-codex-window-id": "window-1",
            "x-codex-turn-metadata": '{"request_kind":"turn"}',
        },
        include=["reasoning.encrypted_content"],
        parallel_tool_calls=True,
        prompt_cache_key="cache-1",
        reasoning={"context": "all_turns", "effort": "high"},
        text={"verbosity": "high"},
        stream=True,
        tool_choice="auto",
    )

    result = _apply(body)

    assert "client_metadata" not in result.effective_body
    assert result.effective_body["stream"] is True
    assert result.effective_body["tool_choice"] == "auto"
    assert result.effective_body["input"][0]["type"] == "additional_tools"
    assert result.effective_body["input"][1]["id"] == "msg_developer_1"
    assert result.effective_body["input"][2]["id"] == "msg_user_1"


@pytest.mark.parametrize("choice", ["none", "auto", "required"])
def test_additional_tools_allows_only_bounded_string_tool_choice(choice: str) -> None:
    assert _apply(_body(tool_choice=choice)).effective_body["tool_choice"] == choice


@pytest.mark.parametrize(
    "choice",
    [
        {"type": "function", "name": "wait"},
        {"type": "custom", "name": "exec"},
        "wait",
    ],
)
def test_additional_tools_rejects_named_or_unknown_tool_choice(choice: object) -> None:
    with pytest.raises(RequestPolicyError) as exc_info:
        _apply(_body(tool_choice=choice))

    assert exc_info.value.error_code in {
        "responses_codex_client_tools_invalid",
        "responses_tool_choice_invalid",
    }


def test_additional_tools_cannot_mix_with_top_level_local_tools() -> None:
    with pytest.raises(RequestPolicyError) as exc_info:
        _apply(
            _body(
                tools=[
                    {
                        "type": "function",
                        "name": "ordinary",
                        "parameters": {"type": "object", "properties": {}},
                    }
                ]
            )
        )

    assert exc_info.value.error_code == "responses_codex_client_tools_invalid"


@pytest.mark.parametrize(
    "mutation",
    [
        "wrong_role",
        "extra_item_field",
        "non_string_namespace",
        "unknown_namespace",
        "duplicate_namespace",
        "missing_tool",
        "unknown_tool",
        "non_string_tool",
        "moved_tool",
        "wrong_tool_type",
        "nested_namespace",
        "duplicate_item",
    ],
)
def test_taxonomy_mutations_fail_closed_without_echoing_payload(mutation: str) -> None:
    body = _body()
    item = _first_item(body)
    namespaces = _namespaces(item)
    if mutation == "wrong_role":
        item["role"] = "user"
    elif mutation == "extra_item_field":
        item["metadata"] = {"private": DESCRIPTION_CANARY}
    elif mutation == "non_string_namespace":
        namespaces[0]["name"] = {"private": DESCRIPTION_CANARY}
    elif mutation == "unknown_namespace":
        namespaces[0]["name"] = "remote"
    elif mutation == "duplicate_namespace":
        namespaces[1]["name"] = "functions"
    elif mutation == "missing_tool":
        namespaces[0]["tools"].pop()
    elif mutation == "unknown_tool":
        namespaces[1]["tools"][0]["name"] = "remote_tool"
    elif mutation == "non_string_tool":
        namespaces[1]["tools"][0]["name"] = [DESCRIPTION_CANARY]
    elif mutation == "moved_tool":
        namespaces[1]["tools"][0]["name"] = "wait"
    elif mutation == "wrong_tool_type":
        namespaces[1]["tools"][0]["type"] = "custom"
    elif mutation == "nested_namespace":
        namespaces[1]["tools"][0] = {
            "type": "namespace",
            "name": "followup_task",
            "tools": [],
        }
    else:
        body["input"].insert(1, copy.deepcopy(item))

    with pytest.raises(RequestPolicyError) as exc_info:
        _apply(body)

    assert exc_info.value.error_code == "responses_codex_client_tools_invalid"
    assert DESCRIPTION_CANARY not in exc_info.value.safe_message


@pytest.mark.parametrize(
    "authority_shape",
    [
        {"server_url": "https://private.invalid"},
        {"headers": {"authorization": "private-token"}},
        {"secret_token": "private-token"},
        {"connector_id": "private-connector"},
        {"approval_mode": "always"},
        {"type": "shell"},
    ],
)
def test_recursive_provider_authority_and_hosted_shapes_are_denied(
    authority_shape: dict[str, object],
) -> None:
    body = _body()
    item = _first_item(body)
    function_tool = _namespaces(item)[1]["tools"][0]
    function_tool["parameters"]["properties"][PROPERTY_CANARY].update(authority_shape)

    with pytest.raises(RequestPolicyError) as exc_info:
        _apply(body)

    assert (
        exc_info.value.error_code
        == "responses_codex_client_tools_provider_authority_not_supported"
    )
    assert "private" not in exc_info.value.safe_message


def test_exec_requires_allowlisted_bounded_grammar_but_description_may_describe_local_work() -> None:
    body = _body()
    item = _first_item(body)
    exec_tool = _namespaces(item)[0]["tools"][0]
    exec_tool["description"] = "Run client-local shell and patch commands; provider executes nothing."
    assert _apply(body).effective_body["input"][0]["tools"][0]["tools"][0][
        "description"
    ].startswith("Run client-local")

    for invalid_format in (
        {"type": "text"},
        {"type": "grammar", "syntax": "json", "definition": "private"},
        None,
    ):
        invalid = _body()
        invalid_exec = _namespaces(_first_item(invalid))[0]["tools"][0]
        if invalid_format is None:
            invalid_exec.pop("format")
        else:
            invalid_exec["format"] = invalid_format
        with pytest.raises(RequestPolicyError):
            _apply(invalid)


@pytest.mark.parametrize("description_bytes", [18_137, 20_000])
@pytest.mark.parametrize(
    ("namespace_index", "tool_index"),
    [(0, 0), (1, 0)],
)
def test_codex_child_description_accepts_pinned_and_reviewed_boundary(
    description_bytes: int,
    namespace_index: int,
    tool_index: int,
) -> None:
    body = _body()
    tool = _child_tool(
        body,
        namespace_index=namespace_index,
        tool_index=tool_index,
    )
    tool["description"] = "d" * description_bytes

    result = _apply(body)

    description = result.effective_body["input"][0]["tools"][namespace_index]["tools"][
        tool_index
    ]["description"]
    assert len(description.encode("utf-8")) == description_bytes


@pytest.mark.parametrize(
    ("namespace_index", "tool_index"),
    [(0, 0), (1, 0)],
)
def test_codex_custom_and_function_child_description_reject_20_001_safely(
    namespace_index: int,
    tool_index: int,
) -> None:
    body = _body()
    tool = _child_tool(
        body,
        namespace_index=namespace_index,
        tool_index=tool_index,
    )
    tool["description"] = f"{DESCRIPTION_CANARY}:" + "d" * (
        20_001 - len(DESCRIPTION_CANARY) - 1
    )

    with pytest.raises(RequestPolicyError) as exc_info:
        _apply(body)

    assert exc_info.value.error_code == "responses_tool_invalid_shape"
    assert exc_info.value.param == (
        f"input[0].tools[{namespace_index}].tools[{tool_index}].description"
    )
    assert DESCRIPTION_CANARY not in exc_info.value.safe_message


def test_codex_child_descriptions_keep_32_768_aggregate_cap() -> None:
    body = _body()
    _child_tool(body, namespace_index=0, tool_index=0)["description"] = "a" * 17_000
    _child_tool(body, namespace_index=0, tool_index=1)["description"] = "b" * 17_000

    with pytest.raises(RequestPolicyError) as exc_info:
        _apply(body)

    assert exc_info.value.error_code == "responses_codex_client_tools_too_large"
    assert exc_info.value.param == "input[0].tools"


@pytest.mark.parametrize("tool_type", ["function", "custom"])
def test_ordinary_tool_description_still_rejects_4_097_bytes(tool_type: str) -> None:
    tool: dict[str, object] = {
        "type": tool_type,
        "name": "ordinary",
        "description": f"{DESCRIPTION_CANARY}:" + "d" * (
            4_097 - len(DESCRIPTION_CANARY) - 1
        ),
    }
    if tool_type == "function":
        tool["parameters"] = {"type": "object", "properties": {}}

    with pytest.raises(RequestPolicyError) as exc_info:
        ResponsesRequestPolicy(Settings()).apply(
            {
                "model": "ordinary",
                "input": "bounded",
                "tools": [tool],
                "max_output_tokens": 1,
            }
        )

    assert exc_info.value.error_code == "responses_tool_invalid_shape"
    assert exc_info.value.param == "tools[0].description"
    assert DESCRIPTION_CANARY not in exc_info.value.safe_message


def test_codex_namespace_description_still_rejects_4_097_bytes() -> None:
    body = _body()
    _namespaces(_first_item(body))[0]["description"] = "d" * 4_097

    with pytest.raises(RequestPolicyError) as exc_info:
        _apply(body)

    assert exc_info.value.error_code == "responses_codex_client_tools_invalid"
    assert exc_info.value.param == "input[0].tools[0].description"


def test_large_codex_description_is_fully_metered_but_absent_from_safe_evidence() -> None:
    baseline_body = _body()
    baseline_tool = _child_tool(baseline_body, namespace_index=0, tool_index=0)
    baseline_tool["description"] = ""
    baseline = _apply(baseline_body)

    large_body = _body()
    large_tool = _child_tool(large_body, namespace_index=0, tool_index=0)
    large_description = f"{DESCRIPTION_CANARY}:" + "d" * (
        18_137 - len(DESCRIPTION_CANARY) - 1
    )
    large_tool["description"] = large_description
    large = _apply(large_body)

    assert large.effective_body["input"][0]["tools"][0]["tools"][0][
        "description"
    ] == large_description
    assert (
        large.estimated_non_message_input_bytes - baseline.estimated_non_message_input_bytes
        == 18_137
    )
    assert large.estimated_input_tokens - baseline.estimated_input_tokens >= 18_137 // 3
    safe_evidence = repr(
        (
            large.estimated_non_message_input_bytes,
            large.estimated_non_message_input_tokens,
            large.estimated_non_message_input_fields,
        )
    )
    assert DESCRIPTION_CANARY not in safe_evidence


@pytest.mark.parametrize(
    "authority_shape",
    [
        {"server_url": "https://private.invalid"},
        {"type": "mcp"},
        {"connector_id": "private-connector"},
    ],
)
def test_large_description_does_not_bypass_recursive_provider_authority_denial(
    authority_shape: dict[str, object],
) -> None:
    body = _body()
    function_tool = _child_tool(body, namespace_index=1, tool_index=0)
    function_tool["description"] = f"{DESCRIPTION_CANARY}:" + "d" * 18_000
    parameters = function_tool["parameters"]
    assert isinstance(parameters, dict)
    properties = parameters["properties"]
    assert isinstance(properties, dict)
    property_schema = properties[PROPERTY_CANARY]
    assert isinstance(property_schema, dict)
    property_schema.update(authority_shape)

    with pytest.raises(RequestPolicyError) as exc_info:
        _apply(body)

    assert (
        exc_info.value.error_code
        == "responses_codex_client_tools_provider_authority_not_supported"
    )
    assert DESCRIPTION_CANARY not in exc_info.value.safe_message


def test_request_user_input_exact_ui_header_path_passes_and_is_fully_metered() -> None:
    baseline = _apply(_body())
    body = _body()
    request_user_input = _child_tool(body, namespace_index=0, tool_index=2)
    request_user_input["parameters"] = _request_user_input_parameters()

    result = _apply(body)

    canonical_parameters = result.effective_body["input"][0]["tools"][0]["tools"][2][
        "parameters"
    ]
    assert canonical_parameters == _request_user_input_parameters()
    assert result.estimated_non_message_input_bytes > baseline.estimated_non_message_input_bytes
    assert result.estimated_input_tokens > baseline.estimated_input_tokens
    safe_evidence = repr(
        (
            result.estimated_non_message_input_bytes,
            result.estimated_non_message_input_tokens,
            result.estimated_non_message_input_fields,
        )
    )
    assert DESCRIPTION_CANARY not in safe_evidence


def test_request_user_input_plural_headers_at_exact_location_still_fails() -> None:
    body = _body()
    request_user_input = _child_tool(body, namespace_index=0, tool_index=2)
    parameters = _request_user_input_parameters()
    question_properties = parameters["properties"]["questions"]["items"]["properties"]
    question_properties["headers"] = question_properties.pop("header")
    request_user_input["parameters"] = parameters

    with pytest.raises(RequestPolicyError) as exc_info:
        _apply(body)

    assert (
        exc_info.value.error_code
        == "responses_codex_client_tools_provider_authority_not_supported"
    )
    assert DESCRIPTION_CANARY not in exc_info.value.safe_message


@pytest.mark.parametrize("location", ["higher", "lower"])
def test_request_user_input_singular_header_at_alternate_path_fails(location: str) -> None:
    body = _body()
    request_user_input = _child_tool(body, namespace_index=0, tool_index=2)
    parameters = _request_user_input_parameters()
    if location == "higher":
        parameters["header"] = {"type": "string"}
    else:
        question_properties = parameters["properties"]["questions"]["items"]["properties"]
        question_properties["header"]["properties"] = {
            "header": {"type": "string"}
        }
    request_user_input["parameters"] = parameters

    with pytest.raises(RequestPolicyError) as exc_info:
        _apply(body)

    assert (
        exc_info.value.error_code
        == "responses_codex_client_tools_provider_authority_not_supported"
    )


@pytest.mark.parametrize(
    ("namespace_index", "tool_index"),
    [(0, 1), (1, 0)],
)
def test_ui_header_exact_schema_path_fails_for_every_other_codex_tool(
    namespace_index: int,
    tool_index: int,
) -> None:
    body = _body()
    other_tool = _child_tool(
        body,
        namespace_index=namespace_index,
        tool_index=tool_index,
    )
    other_tool["parameters"] = _request_user_input_parameters()

    with pytest.raises(RequestPolicyError) as exc_info:
        _apply(body)

    assert (
        exc_info.value.error_code
        == "responses_codex_client_tools_provider_authority_not_supported"
    )


@pytest.mark.parametrize(
    ("sibling_key", "sibling_value"),
    [
        ("authorization", {"type": "string"}),
        ("secret", {"type": "string"}),
        ("connector_id", {"type": "string"}),
        ("server_url", {"type": "string"}),
        ("approval_mode", {"type": "string"}),
        ("mcp", {"type": "object"}),
        ("hosted_sibling", {"type": "web_search"}),
    ],
)
def test_ui_header_exception_keeps_every_sibling_authority_denial(
    sibling_key: str,
    sibling_value: dict[str, object],
) -> None:
    body = _body()
    request_user_input = _child_tool(body, namespace_index=0, tool_index=2)
    parameters = _request_user_input_parameters()
    question_properties = parameters["properties"]["questions"]["items"]["properties"]
    question_properties[sibling_key] = sibling_value
    request_user_input["parameters"] = parameters

    with pytest.raises(RequestPolicyError) as exc_info:
        _apply(body)

    assert (
        exc_info.value.error_code
        == "responses_codex_client_tools_provider_authority_not_supported"
    )
    assert DESCRIPTION_CANARY not in exc_info.value.safe_message


def test_ordinary_request_user_input_schema_behavior_is_unchanged() -> None:
    result = ResponsesRequestPolicy(Settings()).apply(
        {
            "model": "ordinary",
            "input": "bounded",
            "tools": [
                {
                    "type": "function",
                    "name": "request_user_input",
                    "parameters": _request_user_input_parameters(),
                }
            ],
            "max_output_tokens": 1,
        }
    )

    assert result.effective_body["tools"][0]["parameters"] == (
        _request_user_input_parameters()
    )


def test_description_schema_grammar_depth_and_property_caps_fail_closed() -> None:
    description = _body()
    _namespaces(_first_item(description))[0]["description"] = DESCRIPTION_CANARY
    with pytest.raises(RequestPolicyError) as description_exc:
        _apply(
            description,
            settings=Settings(RESPONSES_MAX_FUNCTION_TOOL_DESCRIPTION_BYTES=4),
        )

    grammar = _body()
    _namespaces(_first_item(grammar))[0]["tools"][0]["format"][
        "definition"
    ] = GRAMMAR_CANARY
    with pytest.raises(RequestPolicyError) as grammar_exc:
        _apply(
            grammar,
            settings=Settings(RESPONSES_MAX_CUSTOM_TOOL_FORMAT_DEFINITION_BYTES=4),
        )

    schema = _body()
    function_tool = _namespaces(_first_item(schema))[1]["tools"][0]
    function_tool["parameters"] = {
        "type": "object",
        "description": DESCRIPTION_CANARY,
    }
    with pytest.raises(RequestPolicyError) as schema_exc:
        _apply(
            schema,
            settings=Settings(RESPONSES_MAX_SINGLE_FUNCTION_TOOL_SCHEMA_BYTES=16),
        )

    deep = _body()
    deep_node: dict[str, object] = {"type": "string"}
    for _ in range(20):
        deep_node = {"type": "array", "items": deep_node}
    _namespaces(_first_item(deep))[1]["tools"][0]["parameters"] = deep_node
    with pytest.raises(RequestPolicyError) as depth_exc:
        _apply(deep)

    wide = _body()
    _namespaces(_first_item(wide))[1]["tools"][0]["parameters"] = {
        "type": "object",
        "properties": {f"p{index}": {"type": "string"} for index in range(257)},
    }
    with pytest.raises(RequestPolicyError) as property_exc:
        _apply(wide)

    total_descriptions = _body()
    for namespace in _namespaces(_first_item(total_descriptions)):
        namespace["description"] = "d" * 4_000
        for tool in namespace["tools"]:
            tool["description"] = "d" * 4_000
    with pytest.raises(RequestPolicyError) as total_description_exc:
        _apply(total_descriptions)

    assert description_exc.value.error_code == "responses_codex_client_tools_invalid"
    assert grammar_exc.value.error_code == "responses_custom_tool_format_too_large"
    assert schema_exc.value.error_code == "responses_function_tool_schema_too_large"
    assert depth_exc.value.error_code == "responses_codex_client_tools_schema_too_deep"
    assert property_exc.value.error_code == "responses_codex_client_tools_property_count_exceeded"
    assert total_description_exc.value.error_code == "responses_codex_client_tools_too_large"
    for exc_info in (
        description_exc,
        grammar_exc,
        schema_exc,
        depth_exc,
        property_exc,
        total_description_exc,
    ):
        assert DESCRIPTION_CANARY not in exc_info.value.safe_message
        assert GRAMMAR_CANARY not in exc_info.value.safe_message


@pytest.mark.parametrize(
    ("envelope", "client_tools", "allowed"),
    [(False, False, False), (True, False, False), (False, True, False), (True, True, True)],
)
def test_route_requires_both_independent_capabilities(
    envelope: bool,
    client_tools: bool,
    allowed: bool,
) -> None:
    capabilities = default_responses_capabilities()
    capabilities["codex_request_envelope"] = envelope
    capabilities["codex_client_tools"] = client_tools

    if allowed:
        enforce_responses_route_capabilities(
            route_capabilities={"responses": capabilities},
            codex_client_tools_requested=True,
        )
    else:
        with pytest.raises(RequestPolicyError):
            enforce_responses_route_capabilities(
                route_capabilities={"responses": capabilities},
                codex_client_tools_requested=True,
            )


def test_key_and_shape_denials_precede_route_lookup(monkeypatch) -> None:
    import slaif_gateway.services.responses_gateway as gateway

    calls: list[str] = []

    async def unexpected_route(**kwargs):
        calls.append("route")
        raise AssertionError("route should not be called")

    monkeypatch.setattr(gateway, "_resolve_responses_route", unexpected_route)
    malformed = _body()
    _first_item(malformed)["role"] = "user"

    with pytest.raises(OpenAICompatibleError) as key_exc:
        asyncio.run(
            gateway.handle_response_create(
                payload=ResponsesCreateRequest.model_validate(malformed),
                authenticated_key=_authenticated_key(
                    responses_policy=_key_policy("codex_request_envelope")
                ),
                settings=Settings(),
            )
        )
    assert key_exc.value.code == "responses_codex_client_tools_not_allowed"

    with pytest.raises(OpenAICompatibleError) as shape_exc:
        asyncio.run(
            gateway.handle_response_create(
                payload=ResponsesCreateRequest.model_validate(malformed),
                authenticated_key=_authenticated_key(
                    responses_policy=_key_policy(
                        "codex_request_envelope",
                        "codex_client_tools",
                    )
                ),
                settings=Settings(),
            )
        )
    assert shape_exc.value.code == "responses_codex_client_tools_invalid"
    assert calls == []


def test_route_denial_precedes_redis_quota_and_provider(monkeypatch) -> None:
    import slaif_gateway.services.responses_gateway as gateway

    calls: list[str] = []

    async def deny_route(**kwargs):
        calls.append("route")
        assert kwargs["codex_request_envelope_requested"] is True
        assert kwargs["codex_client_tools_requested"] is True
        raise OpenAICompatibleError(
            "This model route does not support Codex client tool namespaces.",
            code="responses_route_capability_not_supported",
        )

    async def unexpected_later(**kwargs):
        calls.append("later")
        raise AssertionError("later pipeline work should not be called")

    monkeypatch.setattr(gateway, "_resolve_responses_route", deny_route)
    monkeypatch.setattr(gateway, "_reserve_redis_rate_limit", unexpected_later)
    monkeypatch.setattr(gateway, "_reserve_responses_quota", unexpected_later)
    monkeypatch.setattr(
        gateway,
        "get_provider_adapter",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("provider called")),
    )

    with pytest.raises(OpenAICompatibleError) as exc_info:
        asyncio.run(
            gateway.handle_response_create(
                payload=ResponsesCreateRequest.model_validate(_body()),
                authenticated_key=_authenticated_key(
                    responses_policy=_key_policy(
                        "codex_request_envelope",
                        "codex_client_tools",
                    )
                ),
                settings=Settings(),
            )
        )

    assert exc_info.value.code == "responses_route_capability_not_supported"
    assert calls == ["route"]


def test_stream_event_key_denial_precedes_route_lookup(monkeypatch) -> None:
    import slaif_gateway.services.responses_gateway as gateway

    async def unexpected_route(**kwargs):
        raise AssertionError("route should not be called")

    monkeypatch.setattr(gateway, "_resolve_responses_route", unexpected_route)

    with pytest.raises(OpenAICompatibleError) as exc_info:
        asyncio.run(
            gateway.handle_response_create(
                payload=ResponsesCreateRequest.model_validate(_body(stream=True)),
                authenticated_key=_authenticated_key(
                    responses_policy=_key_policy(
                        "codex_request_envelope",
                        "codex_client_tools",
                    )
                ),
                settings=Settings(),
            )
        )

    assert exc_info.value.code == "responses_codex_streaming_tool_events_not_allowed"


def test_stream_event_route_denial_precedes_redis_quota_and_provider(monkeypatch) -> None:
    import slaif_gateway.services.responses_gateway as gateway

    calls: list[str] = []

    async def deny_route(**kwargs):
        calls.append("route")
        assert kwargs["codex_streaming_tool_events_requested"] is True
        raise OpenAICompatibleError(
            "This model route does not support Codex streaming tool events.",
            code="responses_route_capability_not_supported",
        )

    async def unexpected_later(**kwargs):
        calls.append("later")
        raise AssertionError("later pipeline work should not be called")

    monkeypatch.setattr(gateway, "_resolve_responses_route", deny_route)
    monkeypatch.setattr(gateway, "_reserve_redis_rate_limit", unexpected_later)
    monkeypatch.setattr(gateway, "_reserve_responses_quota", unexpected_later)

    with pytest.raises(OpenAICompatibleError) as exc_info:
        asyncio.run(
            gateway.handle_response_create(
                payload=ResponsesCreateRequest.model_validate(_body(stream=True)),
                authenticated_key=_authenticated_key(
                    responses_policy=_key_policy(
                        "codex_request_envelope",
                        "codex_client_tools",
                        "codex_streaming_tool_events",
                    )
                ),
                settings=Settings(),
            )
        )

    assert exc_info.value.code == "responses_route_capability_not_supported"
    assert calls == ["route"]
