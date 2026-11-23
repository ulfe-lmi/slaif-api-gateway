"""Pinned native OpenCode 1.19.3 Responses client module, profile, policy, and registry contracts."""

import json
from pathlib import Path
from types import MappingProxyType

import pytest

from slaif_gateway.modules.agent_chat_profile_data import AgentChatProfileDataError
from slaif_gateway.modules.clients.codex_0149 import (
    CODEX_0149_POLICY_SPEC,
    codex_0149_declared_tool_taxonomy,
    codex_0149_zero_argument_function_names,
)
from slaif_gateway.modules.clients.opencode_1193_responses import (
    OPENCODE_1193_RESPONSES_CLIENT_MODULE as MODULE,
    OPENCODE_1193_RESPONSES_CLIENT_MODULE_ID as MOD_ID,
    OPENCODE_1193_RESPONSES_PROFILE_DATA as DATA,
    OPENCODE_1193_RESPONSES_PROFILE_FIXTURE_SHA256 as DIGEST,
    OPENCODE_1193_RESPONSES_POLICY_SPEC as SPEC,
    parse_opencode_1193_responses_profile_data as parse,
)
from slaif_gateway.modules.clients.registry import (
    _LEGACY_CODEX_GATES,
    CODEX_0147_CLIENT_MODULE,
    DEFAULT_CLIENT_MODULE,
    OPENCODE_1193_RESPONSES_CLIENT_MODULE_INSTANCE,
    client_module_metadata,
    get_client_module,
    resolve_responses_client_module,
)
from slaif_gateway.modules.contracts import ModuleSelectionError
from slaif_gateway.modules.servers.registry import (
    OPENAI_COMPATIBLE_SERVER_MODULE_ID,
    OPENAI_SERVER_MODULE_ID,
    ensure_client_server_pair,
)
from slaif_gateway.providers.errors import ProviderConfigurationError
from slaif_gateway.services.responses_request_policy import (
    responses_codex_0149_tool_roundtrip_requested,
)

PROFILE_JSON = Path("app/slaif_gateway/modules/clients/profiles/opencode-1.19.3-responses.json")
NAMES = ["bash", "edit", "glob", "grep", "read", "skill", "task", "todowrite", "write"]
COMMIT = "e3c4eb242585dcd77be1a867391b7c25fd47ce52"
DIGEST_LITERAL = "592c5d1baa7aa3a805320411f3f961521ba72b30cc34cafe01cb755ddf69f0ff"
INCLUDE = "reasoning.encrypted_content"
EFFORTS = frozenset({"minimal", "low", "medium", "high", "xhigh"})
PIN = {"id": MOD_ID, "version": "1", "fixture_sha256": DIGEST_LITERAL}


def _tool(name):
    return {
        "type": "function",
        "name": name,
        "description": f"Tool {name}",
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        "strict": True,
    }


def _turn1():
    return {
        "model": "qwen38-27b",
        "stream": True,
        "store": False,
        "tool_choice": "auto",
        "include": [INCLUDE],
        "reasoning": {"effort": "xhigh"},
        "max_output_tokens": 32000,
        "input": [
            {"role": "developer", "content": "You are a bounded local tool harness."},
            {
                "role": "user",
                "content": [{"type": "input_text", "text": "Read the marker file exactly."}],
            },
        ],
        "tools": [_tool(name) for name in NAMES],
    }


def _continuation():
    body = _turn1()
    body["input"] = [
        {"role": "developer", "content": "You are a bounded local tool harness."},
        {"type": "function_call", "name": "read", "arguments": "{}", "call_id": "call_abc"},
        {"type": "function_call_output", "call_id": "call_abc", "output": "ok"},
    ]
    return body


def _parse_mutated(mutate):
    doc = json.loads(PROFILE_JSON.read_text())
    mutate(doc)
    return parse(json.dumps(doc).encode())


def _parse_reject(raw, field):
    with pytest.raises(AgentChatProfileDataError) as exc:
        parse(raw)
    assert exc.value.field == field


def _norm(body):
    return MODULE.normalize_responses(body)


def _norm_reject(mutate, code):
    body = _turn1()
    mutate(body)
    with pytest.raises(ModuleSelectionError) as exc:
        _norm(body)
    assert exc.value.error_code == code


def _resolve_reject(policy, code):
    with pytest.raises(ModuleSelectionError) as exc:
        resolve_responses_client_module(policy)
    assert exc.value.error_code == code


def _deep_params(levels):
    node = {"type": "object", "properties": {}, "additionalProperties": False}
    for _ in range(levels):
        node = {"type": "object", "properties": {"n": node}, "additionalProperties": False}
    return node


# ---------------------------------------------------------------------------
# Profile DATA acceptance
# ---------------------------------------------------------------------------


def test_profile_data_facts():
    assert DATA.profile_id == MOD_ID
    assert DATA.profile_version == "1"
    assert DATA.client_name == "opencode"
    assert DATA.distribution_version == "1.19.3"
    assert DATA.source_tag == "v1.19.3"
    assert DATA.source_commit == COMMIT
    assert DATA.sdk_name == "@ai-sdk/openai"
    assert DATA.sdk_version == "3.0.88"
    assert DATA.reasoning_efforts == EFFORTS
    assert DATA.tool_names == frozenset(NAMES)
    assert DATA.max_tool_declarations == 32
    assert DATA.max_description_bytes == 20000
    assert DATA.max_schema_depth == 8
    assert DATA.max_schema_properties == 64
    assert DATA.max_declaration_bytes == 65536
    assert DATA.tool_call_id_min_length == 1
    assert DATA.tool_call_id_max_length == 128
    assert DATA.tool_call_arguments_max_bytes == 65536
    assert isinstance(DATA.document, MappingProxyType)


def test_profile_reparse_is_stable():
    assert parse(PROFILE_JSON.read_bytes()) == DATA


def test_fixture_digest_pin():
    assert DIGEST_LITERAL == DIGEST
    assert DIGEST == DATA.fixture_sha256
    assert DIGEST == MODULE.fixture_sha256


# ---------------------------------------------------------------------------
# Profile DATA rejection (raw bytes and mutated documents)
# ---------------------------------------------------------------------------


def test_profile_rejects_raw_bytes():
    cases = [
        ("str", "profile"),
        (b"\xff\xfe\xfd", "profile"),
        (b'{"schema_version": 1, "schema_version": 2}', "key"),
        (b'{"schema_version": NaN}', "constant"),
        (b"[]", "profile"),
        (b'{"pad": "' + b"x" * 70000 + b'"}', "profile"),
    ]
    for raw, field in cases:
        _parse_reject(raw, field)


def test_profile_rejects_mutated_documents():
    mutations = [
        (lambda d: d.update({"extra": 1}), "profile"),
        (lambda d: d.pop("dialect"), "profile"),
        (lambda d: d.update({"schema_version": 2}), "schema_version"),
        (lambda d: d.update({"schema_version": True}), "schema_version"),
        (lambda d: d.update({"id": "Opencode-1.19.3-responses-v1"}), "id"),
        (lambda d: d.update({"id": "a" * 62 + "-v1"}), "id"),
        (lambda d: d.update({"version": "1.0"}), "version"),
        (lambda d: d["client"].update({"source_commit": "e3c4eb"}), "client.source_commit"),
        (lambda d: d["client"].update({"wire_api": "chat"}), "client.wire_api"),
        (lambda d: d["client"].update({"extra": 1}), "client"),
        (lambda d: d["dialect"].update({"tool_call": "str"}), "dialect.tool_call"),
        (
            lambda d: d["dialect"]["tool_call"].update({"id_max_length": 0}),
            "dialect.tool_call.id_max_length",
        ),
        (lambda d: d["dialect"].update({"reasoning_efforts": ["none"]}), "dialect.reasoning_efforts"),
        (
            lambda d: d["dialect"].update({"reasoning_efforts": ["minimal", "minimal"]}),
            "dialect.reasoning_efforts",
        ),
        (
            lambda d: d["dialect"]["tools"].update({"names": ["read", "read"]}),
            "dialect.tools.names",
        ),
        (
            lambda d: d["dialect"]["tools"].update({"max_declarations": 65}),
            "dialect.tools.max_declarations",
        ),
        (
            lambda d: d["dialect"]["tools"].update({"max_declarations": True}),
            "dialect.tools.max_declarations",
        ),
        (
            lambda d: d["dialect"]["tools"].update({"max_schema_depth": 0}),
            "dialect.tools.max_schema_depth",
        ),
        (
            lambda d: d["dialect"]["tool_call"].update({"arguments_max_bytes": 262145}),
            "dialect.tool_call.arguments_max_bytes",
        ),
    ]
    for mutate, field in mutations:
        def _mutate(doc, _mutate=mutate):
            _mutate(doc)

        with pytest.raises(AgentChatProfileDataError) as exc:
            _parse_mutated(_mutate)
        assert exc.value.field == field


# ---------------------------------------------------------------------------
# normalize acceptance
# ---------------------------------------------------------------------------


def test_turn1_accepts_full_contract():
    body = _turn1()
    result = _norm(body)
    assert result.module_id == MOD_ID
    assert result.module_version == "1"
    assert result.endpoint == "/v1/responses"
    assert result.body == body
    assert result.stream_profile == MOD_ID
    assert result.zero_argument_function_names == frozenset(NAMES)
    assert result.capability_intents == ()
    assert result.adapter_managed_declaration_candidates == ()
    assert dict(result.adapter_managed_declaration_shapes) == {}
    assert result.identity_hints == {}


def test_profile_facts_shape():
    result = _norm(_turn1())
    assert set(result.profile_facts) == {
        "client_module_id",
        "client_module_version",
        "fixture_sha256",
        "source_tag",
        "source_commit",
        "sdk_name",
        "sdk_version",
    }
    assert result.profile_facts["client_module_id"] == MOD_ID
    assert result.profile_facts["client_module_version"] == "1"
    assert result.profile_facts["fixture_sha256"] == DIGEST_LITERAL
    assert result.profile_facts["source_tag"] == "v1.19.3"
    assert result.profile_facts["source_commit"] == COMMIT
    assert result.profile_facts["sdk_name"] == "@ai-sdk/openai"
    assert result.profile_facts["sdk_version"] == "3.0.88"


def test_normalize_deepcopies_body():
    body = _turn1()
    result = _norm(body)
    result.body["model"] = "mutated"
    result.body["input"][0]["content"] = "mutated"
    assert body["model"] == "qwen38-27b"
    assert body["input"][0]["content"] == "You are a bounded local tool harness."


def test_normalize_responses_alias():
    body = _turn1()
    assert MODULE.normalize_responses(body) == MODULE.normalize("/v1/responses", body)


def test_stream_profile_ignores_body():
    assert MODULE.stream_profile({"nonsense": 1}) == MOD_ID


def test_zero_arg_empty_for_parametric_tool():
    body = _turn1()
    body["tools"] = [
        {
            "type": "function",
            "name": "read",
            "description": "d",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "additionalProperties": False,
            },
            "strict": True,
        }
    ]
    assert _norm(body).zero_argument_function_names == frozenset()


def test_numeric_call_id_accepts():
    body = _continuation()
    body["input"][1]["call_id"] = "123"
    body["input"][2]["call_id"] = "123"
    _norm(body)


def test_depth0_type_key_is_not_forbidden():
    body = _turn1()
    body["tools"] = [
        {
            "type": "function",
            "name": "read",
            "description": "d",
            "parameters": {"type": "mcp"},
            "strict": True,
        }
    ]
    _norm(body)


# ---------------------------------------------------------------------------
# normalize rejection
# ---------------------------------------------------------------------------


def test_normalize_rejects_wrong_endpoint_and_body_type():
    with pytest.raises(ModuleSelectionError) as exc:
        MODULE.normalize("/v1/chat/completions", _turn1())
    assert exc.value.error_code == "opencode_1193_request_invalid"
    with pytest.raises(ModuleSelectionError) as exc:
        _norm("str")
    assert exc.value.error_code == "opencode_1193_request_invalid"


def test_normalize_rejects_field_set():
    _norm_reject(lambda b: b.update({"temperature": 1}), "opencode_1193_fields")
    _norm_reject(lambda b: b.pop("include"), "opencode_1193_fields")


def test_normalize_rejects_field_shapes():
    cases = [
        lambda b: b.update({"stream": False}),
        lambda b: b.update({"store": True}),
        lambda b: b.update({"tool_choice": "required"}),
        lambda b: b.update({"include": []}),
        lambda b: b.update({"include": [INCLUDE, INCLUDE]}),
        lambda b: b.update({"include": ["bogus"]}),
        lambda b: b.update({"include": [INCLUDE, "bogus"]}),
        lambda b: b.update({"reasoning": {"effort": "none"}}),
        lambda b: b.update({"reasoning": {"effort": "xhigh", "summary": "x"}}),
        lambda b: b.update({"reasoning": "xhigh"}),
        lambda b: b.update({"model": ""}),
        lambda b: b.update({"model": "m" * 257}),
        lambda b: b.update({"max_output_tokens": True}),
        lambda b: b.update({"max_output_tokens": 0}),
        lambda b: b.update({"max_output_tokens": "32000"}),
        lambda b: b.update({"max_output_tokens": 2000000}),
        lambda b: b.update({"input": []}),
        lambda b: b.update({"input": "str"}),
        lambda b: b.update({"tools": []}),
        lambda b: b.update({"tools": [_tool("read")] * 36}),
    ]
    for mutate in cases:
        _norm_reject(mutate, "opencode_1193_field_shape")


def test_normalize_rejects_input_items():
    developer = {"role": "developer", "content": "You are a bounded local tool harness."}
    cases = [
        lambda b: b.update({"input": ["str"]}),
        lambda b: b.update({"input": [{"role": "assistant", "content": "x"}]}),
        lambda b: b.update({"input": [{"role": "user", "content": ""}]}),
        lambda b: b.update({"input": [{"role": "user", "content": "x" * 1048577}]}),
        lambda b: b.update({"input": [{"role": "user", "content": [{"type": "text", "text": "x"}]}]}),
        lambda b: b.update({"input": [{"role": "user", "content": [{"type": "input_text"}]}]}),
        lambda b: b.update(
            {
                "input": [
                    {
                        "role": "user",
                        "content": [{"type": "input_text", "text": "x"}] * 65,
                    }
                ]
            }
        ),
        lambda b: b.update(
            {
                "input": [
                    {
                        "type": "custom_tool_call",
                        "name": "read",
                        "arguments": "{}",
                        "call_id": "c1",
                    }
                ]
            }
        ),
        lambda b: b.update(
            {
                "input": [
                    {
                        "type": "function_call",
                        "name": "Bad Name!",
                        "arguments": "{}",
                        "call_id": "c1",
                    }
                ]
            }
        ),
        lambda b: b.update(
            {
                "input": [
                    {
                        "type": "function_call",
                        "name": "read",
                        "arguments": "x" * 70000,
                        "call_id": "c1",
                    }
                ]
            }
        ),
        lambda b: b.update(
            {
                "input": [
                    {
                        "type": "function_call",
                        "name": "read",
                        "arguments": "{}",
                        "call_id": "",
                    }
                ]
            }
        ),
        lambda b: b.update(
            {
                "input": [
                    {
                        "type": "function_call",
                        "name": "read",
                        "arguments": "{}",
                        "call_id": "c" * 129,
                    }
                ]
            }
        ),
        lambda b: b.update(
            {
                "input": [
                    {
                        "type": "function_call",
                        "name": "read",
                        "arguments": "{}",
                        "call_id": "call abc!",
                    }
                ]
            }
        ),
        lambda b: b.update({"input": [{"type": "function_call_output", "output": "ok"}]}),
        lambda b: b.update(
            {
                "input": [
                    {
                        "type": "function_call_output",
                        "call_id": "c1",
                        "output": "x" * 1048577,
                    }
                ]
            }
        ),
    ]
    for mutate in cases:
        _norm_reject(mutate, "opencode_1193_input_item")


def _tool_reject(parameters=None, **tool_overrides):
    def mutate(body):
        tool = _tool("read")
        if parameters is not None:
            tool["parameters"] = parameters
        tool.update(tool_overrides)
        body["tools"] = [tool]

    return mutate


def test_normalize_rejects_tool_declarations():
    _norm_reject(
        lambda b: b.update({"tools": [_tool("read"), _tool("read")]}),
        "opencode_1193_tool_declaration",
    )
    _norm_reject(_tool_reject(name="cat"), "opencode_1193_tool_declaration")
    _norm_reject(_tool_reject(type="computer"), "opencode_1193_tool_declaration")
    _norm_reject(_tool_reject(strict=False), "opencode_1193_tool_declaration")
    _norm_reject(_tool_reject(description="x" * 20001), "opencode_1193_tool_declaration")
    _norm_reject(_tool_reject(parameters="str"), "opencode_1193_tool_declaration")
    _norm_reject(_tool_reject(parameters=_deep_params(8)), "opencode_1193_tool_declaration")
    _norm_reject(
        _tool_reject(
            parameters={
                "type": "object",
                "properties": {f"p{i}": {"type": "string"} for i in range(65)},
                "additionalProperties": False,
            }
        ),
        "opencode_1193_tool_declaration",
    )
    _norm_reject(
        _tool_reject(
            parameters={
                "type": "object",
                "properties": {f"p{i}": {"description": "x" * 1100} for i in range(64)},
                "additionalProperties": False,
            }
        ),
        "opencode_1193_tool_declaration",
    )
    _norm_reject(
        _tool_reject(
            parameters={
                "type": "object",
                "properties": {"ok": 1, 5: 2},
                "additionalProperties": False,
            }
        ),
        "opencode_1193_tool_declaration",
    )
    _norm_reject(
        _tool_reject(
            parameters={
                "type": "object",
                "properties": {"x": [frozenset()]},
                "additionalProperties": False,
            }
        ),
        "opencode_1193_tool_declaration",
    )


def _leaf_chain(levels):
    """Single-key Mapping chain whose leaf Mapping is visited at depth `levels`."""
    node = {"a": 1}
    for _ in range(levels):
        node = {"n": node}
    return node


def _params_tool(parameters):
    return [
        {
            "type": "function",
            "name": "read",
            "description": "d",
            "parameters": parameters,
            "strict": True,
        }
    ]


def test_declaration_depth_boundary():
    body = _turn1()
    body["tools"] = _params_tool(_leaf_chain(8))
    _norm(body)
    _norm_reject(lambda b: b.update({"tools": _params_tool(_leaf_chain(9))}), "opencode_1193_tool_declaration")


def test_normalize_rejects_authority_shapes():
    cases = [
        {
            "api_key": "sk-x",
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
        {
            "API_KEY": "sk-x",
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
        {
            "type": "object",
            "properties": {"w": {"type": "web_search_preview"}},
            "additionalProperties": False,
        },
        {
            "type": "object",
            "properties": {"m": {"type": "mcp"}},
            "additionalProperties": False,
        },
        {
            "type": "object",
            "properties": {"h": {"headers": "x"}},
            "additionalProperties": False,
        },
    ]
    for parameters in cases:
        _norm_reject(_tool_reject(parameters=parameters), "opencode_1193_authority_shape")


# ---------------------------------------------------------------------------
# Policy spec
# ---------------------------------------------------------------------------


def test_policy_spec_owned_overrides():
    assert SPEC.allow_idless_encrypted_reasoning is True
    assert SPEC.reasoning_efforts == EFFORTS
    assert SPEC.client_metadata_keys == frozenset()
    assert SPEC.max_client_metadata_keys == 0
    assert SPEC.max_client_metadata_key_bytes == 0
    assert SPEC.max_client_metadata_value_bytes == 0
    assert SPEC.max_client_metadata_bytes == 0


def test_policy_spec_inherited_codex_gates():
    assert SPEC.include_value == "reasoning.encrypted_content"
    assert SPEC.reasoning_context == "all_turns"
    assert SPEC.tool_call_statuses == frozenset({"completed"})
    assert SPEC.allow_idless_tool_call_replay is True
    assert SPEC.function_call_item_id_optional is True
    assert SPEC.custom_tool_call_item_id_optional is True
    assert SPEC.reasoning_visible_id_optional is True
    assert CODEX_0149_POLICY_SPEC.allow_idless_encrypted_reasoning is False


# ---------------------------------------------------------------------------
# encrypted_reasoning_output_requested
# ---------------------------------------------------------------------------


def test_encrypted_reasoning_output_requested():
    body = _turn1()
    assert MODULE.encrypted_reasoning_output_requested(body) is True
    body["include"] = [INCLUDE, "other"]
    assert MODULE.encrypted_reasoning_output_requested(body) is True
    body["include"] = ["other"]
    assert MODULE.encrypted_reasoning_output_requested(body) is False
    body["include"] = ["bogus"]
    assert MODULE.encrypted_reasoning_output_requested(body) is False
    del body["include"]
    assert MODULE.encrypted_reasoning_output_requested(body) is False
    body["include"] = "str"
    assert MODULE.encrypted_reasoning_output_requested(body) is False
    body["include"] = [1]
    assert MODULE.encrypted_reasoning_output_requested(body) is False
    assert MODULE.encrypted_reasoning_output_requested("str") is False


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def test_registry_lookup_and_metadata():
    assert get_client_module(MOD_ID) is MODULE
    assert OPENCODE_1193_RESPONSES_CLIENT_MODULE_INSTANCE is MODULE
    assert client_module_metadata(MODULE) == PIN


def test_resolve_none_defaults():
    assert resolve_responses_client_module(None) is DEFAULT_CLIENT_MODULE


def test_resolve_pin_returns_module():
    assert resolve_responses_client_module({"client_module": dict(PIN)}) is MODULE


def test_resolve_legacy_codex_gates():
    policy = {
        "version": 1,
        "allowed_capabilities": sorted(_LEGACY_CODEX_GATES),
        "allowed_local_tool_types": ["function", "custom"],
    }
    assert resolve_responses_client_module(policy) is CODEX_0147_CLIENT_MODULE


def test_resolve_nonlegacy_without_pin_defaults():
    policy = {"version": 1, "allowed_capabilities": ["x"], "allowed_local_tool_types": []}
    assert resolve_responses_client_module(policy) is DEFAULT_CLIENT_MODULE


def test_resolve_rejects_metadata():
    _resolve_reject("str", "client_module_metadata_invalid")
    _resolve_reject({"client_module": "str"}, "client_module_metadata_invalid")
    _resolve_reject(
        {"client_module": {"id": MOD_ID, "version": "1"}},
        "client_module_metadata_invalid",
    )
    _resolve_reject(
        {"client_module": dict(PIN, extra=1)},
        "client_module_metadata_invalid",
    )
    _resolve_reject(
        {"client_module": {"id": MOD_ID, "version": 2, "fixture_sha256": DIGEST_LITERAL}},
        "client_module_metadata_invalid",
    )
    _resolve_reject(
        {"client_module": {"id": 5, "version": "1", "fixture_sha256": DIGEST_LITERAL}},
        "client_module_metadata_invalid",
    )


def test_resolve_rejects_fixture_mismatch_and_unknown_id():
    _resolve_reject(
        {"client_module": {"id": MOD_ID, "version": "2", "fixture_sha256": DIGEST_LITERAL}},
        "client_module_fixture_mismatch",
    )
    _resolve_reject(
        {"client_module": {"id": MOD_ID, "version": "1", "fixture_sha256": "0" * 64}},
        "client_module_fixture_mismatch",
    )
    _resolve_reject(
        {"client_module": {"id": "unknown-module", "version": "1", "fixture_sha256": DIGEST_LITERAL}},
        "unsupported_client_module",
    )


# ---------------------------------------------------------------------------
# Server pairs
# ---------------------------------------------------------------------------


def test_server_pairs_accepted():
    ensure_client_server_pair(MOD_ID, OPENAI_SERVER_MODULE_ID)
    ensure_client_server_pair(MOD_ID, OPENAI_COMPATIBLE_SERVER_MODULE_ID)


@pytest.mark.parametrize(
    "server",
    ["openrouter", "local-coding-v1", "local-coding-vLLM", "configured-upstream-llm"],
)
def test_server_pairs_rejected(server):
    with pytest.raises(ProviderConfigurationError) as exc:
        ensure_client_server_pair(MOD_ID, server)
    assert exc.value.error_code == "incompatible_module_pair"
    assert exc.value.provider == server


# ---------------------------------------------------------------------------
# Gateway branch sanity
# ---------------------------------------------------------------------------


def test_taxonomy_full_nine_tools():
    body = _turn1()
    expected = frozenset(("functions", name, "function") for name in NAMES)
    assert codex_0149_declared_tool_taxonomy(body) == expected


def test_roundtrip_requested_continuation():
    body = _continuation()
    _norm(body)
    assert responses_codex_0149_tool_roundtrip_requested(body) is True


def test_roundtrip_not_requested_turn1():
    assert responses_codex_0149_tool_roundtrip_requested(_turn1()) is False


def test_roundtrip_not_requested_two_pairs():
    body = _turn1()
    body["input"] = [
        body["input"][0],
        {"type": "function_call", "name": "read", "arguments": "{}", "call_id": "c1"},
        {"type": "function_call_output", "call_id": "c1", "output": "ok"},
        {"type": "function_call", "name": "grep", "arguments": "{}", "call_id": "c2"},
        {"type": "function_call_output", "call_id": "c2", "output": "ok"},
    ]
    assert responses_codex_0149_tool_roundtrip_requested(body) is False


def test_roundtrip_not_requested_stream_false():
    body = _continuation()
    body["stream"] = False
    assert responses_codex_0149_tool_roundtrip_requested(body) is False
