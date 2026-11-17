"""Synthetic native-vLLM wire contracts; real backend evidence is separate."""

import copy
import json
import re
from dataclasses import replace

import httpx
import pytest

from slaif_gateway.config import Settings
from slaif_gateway.modules.servers.local_coding_vllm.adapter import LocalCodingVLLMAdapter
from slaif_gateway.modules.servers.local_coding_vllm.codec import MAX_ARGUMENT_BYTES, VLLMToolCodec
from slaif_gateway.modules.servers.local_coding_vllm.contract import (
    VLLM_SERVER_MODULE_ID,
    parse_vllm_route_contract,
)
from slaif_gateway.modules.servers.registry import resolve_server_module, ensure_client_server_pair
from slaif_gateway.providers.errors import (
    ProviderConfigurationError,
    ProviderResponseParseError,
    ProviderRequestError,
)
from slaif_gateway.providers.streaming import (
    ResponsesStreamEventValidator,
    ResponsesStreamValidationProfile,
)
from slaif_gateway.schemas.providers import ProviderRequest

CAPS = {
    "local_coding_vllm": {
        "contract_version": VLLM_SERVER_MODULE_ID,
        "route_name": "synthetic",
        "identity_mode": "static",
        "tool_policy_version": "responses-tool-policy-v1",
        "replay_mode": "process_local_inclusive_horizon_fail_closed",
        "deployment_mode": "single_worker",
    }
}


def body():
    return {
        "model": "synthetic",
        "input": [{"role": "user", "content": "Synthetic patch test"}],
        "tools": [
            {
                "type": "namespace",
                "name": "functions",
                "tools": [
                    {
                        "type": "custom",
                        "name": "apply_patch",
                        "description": "Apply a patch",
                        "format": {
                            "type": "grammar",
                            "syntax": "lark",
                            "definition": "start: /.+/",
                        },
                    },
                    {
                        "type": "function",
                        "name": "exec_command",
                        "parameters": {
                            "type": "object",
                            "properties": {"cmd": {"type": "string"}},
                            "required": ["cmd"],
                        },
                        "strict": False,
                    },
                ],
            }
        ],
    }


def item(arguments="", name="functions.apply_patch"):
    return {
        "type": "function_call",
        "id": "fc_synthetic",
        "call_id": "call_synthetic",
        "name": name,
        "arguments": arguments,
        "namespace": None,
        "async": None,
        "caller": None,
        "status": "in_progress",
    }


def native_events(arguments):
    return [
        {
            "type": "response.output_item.added",
            "output_index": 0,
            "item": item(),
            "sequence_number": 0,
        },
        {
            "type": "response.function_call_arguments.delta",
            "item_id": "fc_synthetic",
            "output_index": 0,
            "delta": arguments[:4],
            "sequence_number": 1,
        },
        {
            "type": "response.function_call_arguments.delta",
            "item_id": "fc_synthetic",
            "output_index": 0,
            "delta": arguments[4:],
            "sequence_number": 2,
        },
        {
            "type": "response.function_call_arguments.done",
            "item_id": "fc_synthetic",
            "output_index": 0,
            "name": "functions.apply_patch",
            "arguments": arguments,
            "sequence_number": 3,
        },
        {
            "type": "response.output_item.done",
            "output_index": 0,
            "item": dict(item(arguments), status="completed"),
            "sequence_number": 4,
        },
    ]


def test_explicit_selection_is_provider_independent_and_old_adapter_is_unchanged():
    for provider in ("first-host", "second-host"):
        assert (
            resolve_server_module(provider, "openai_compatible", CAPS).module_id
            == VLLM_SERVER_MODULE_ID
        )
        assert resolve_server_module(provider, "openai_compatible").module_id == "openai-compatible"
    assert ensure_client_server_pair("codex-0.162-responses-v1", VLLM_SERVER_MODULE_ID) is None
    with pytest.raises(ProviderConfigurationError):
        ensure_client_server_pair("codex-0.149-responses-v1", VLLM_SERVER_MODULE_ID)
    mixed = dict(
        CAPS, local_coding=dict(CAPS["local_coding_vllm"], contract_version="local-coding-v1")
    )
    with pytest.raises(ProviderConfigurationError):
        resolve_server_module("test", "openai_compatible", mixed)
    for change in (
        {"identity_mode": "signed_identity_v1"},
        {"contract_version": "other"},
        {"unknown": True},
    ):
        with pytest.raises(ValueError):
            parse_vllm_route_contract(
                {"local_coding_vllm": dict(CAPS["local_coding_vllm"], **change)}
            )


def test_request_translation_preserves_original_and_replays_both_tool_kinds():
    original = body()
    original["input"] += [
        {
            "type": "custom_tool_call",
            "id": "ct1",
            "call_id": "c1",
            "namespace": "functions",
            "name": "apply_patch",
            "input": "patch",
        },
        {"type": "custom_tool_call_output", "call_id": "c1", "output": "ok"},
        {
            "type": "function_call",
            "call_id": "c2",
            "namespace": "functions",
            "name": "exec_command",
            "arguments": '{"cmd":"true"}',
        },
    ]
    snapshot = copy.deepcopy(original)
    codec = VLLMToolCodec(original)
    assert original == snapshot
    assert [x["name"] for x in codec.body["tools"]] == [
        "functions.apply_patch",
        "functions.exec_command",
    ]
    custom = codec.body["tools"][0]
    assert custom["type"] == "function" and custom["parameters"]["required"] == ["input"]
    assert json.loads(codec.body["input"][1]["arguments"]) == {"input": "patch"}
    assert codec.body["input"][2]["type"] == "function_call_output"
    assert codec.body["input"][3]["name"] == "functions.exec_command"


def test_native_vllm_image_default_is_explicit_without_changing_client_input():
    original = body()
    original["input"] = [
        {"type": "message", "role": "user", "content": [
            {"type": "input_text", "text": "Which color?"},
            {"type": "input_image", "image_url": "data:image/png;base64,synthetic"},
        ]}
    ]
    codec = VLLMToolCodec(original)
    assert "detail" not in original["input"][0]["content"][1]
    assert codec.body["input"][0]["content"][1]["detail"] == "auto"
    original["input"][0]["content"][1]["detail"] = "high"
    assert VLLMToolCodec(original).body["input"][0]["content"][1]["detail"] == "high"


def test_custom_stream_roundtrip_passes_existing_validator_and_keeps_call_identity():
    codec = VLLMToolCodec(body())
    arguments = json.dumps({"input": "*** Begin Patch\nUnicode: č\n*** End Patch\n"})
    events = [
        normalized for event in native_events(arguments) for normalized in codec.events(event)
    ]
    profile = ResponsesStreamValidationProfile(
        codex_streaming_tool_events=True,
        declared_client_tools=frozenset({("functions", "apply_patch", "custom")}),
        custom_client_tools=frozenset({("functions", "apply_patch", "custom")}),
    )
    validator = ResponsesStreamEventValidator(profile)
    assert all(validator.validate(event) for event in events)
    assert [event["sequence_number"] for event in events] == list(range(len(events)))
    assert events[1]["type"] == "response.custom_tool_call_input.delta"
    assert events[1]["delta"] == json.loads(arguments)["input"]
    assert events[-1]["item"]["call_id"] == "call_synthetic"
    assert not ResponsesStreamEventValidator(
        replace(profile, declared_client_tools=frozenset())
    ).validate(events[0])
    terminal = {
        "type": "response.completed",
        "sequence_number": 5,
        "response": {
            "output": [dict(item(arguments), status="completed")],
            "tools": codec.body["tools"],
        },
    }
    result = codec.events(terminal)[0]["response"]
    assert result["output"][0]["type"] == "custom_tool_call"
    assert result["tools"] == body()["tools"]


@pytest.mark.parametrize(
    "change", [{"async": True}, {"caller": {}}, {"name": "undeclared"}, {"namespace": "other"}]
)
def test_native_response_cannot_add_authority(change):
    with pytest.raises(ProviderResponseParseError):
        VLLMToolCodec(body()).item(dict(item(), **change), added=True)


@pytest.mark.parametrize(
    "arguments",
    ['{"input":"a","input":"b"}', '{"input":3}', '{"input":"a","extra":true}', "not json"],
)
def test_custom_argument_translation_rejects_invalid_or_ambiguous_json(arguments):
    codec = VLLMToolCodec(body())
    with pytest.raises(ProviderResponseParseError):
        for event in native_events(arguments):
            codec.events(event)


def test_custom_buffer_and_lifecycle_bounds():
    codec = VLLMToolCodec(body())
    codec.events(native_events("")[0])
    event = native_events("")[1]
    event["delta"] = "x" * (MAX_ARGUMENT_BYTES + 1)
    with pytest.raises(ProviderResponseParseError):
        codec.events(event)
    codec = VLLMToolCodec(body())
    with pytest.raises(ProviderResponseParseError):
        codec.events(dict(native_events("")[0], sequence_number=1))
    codec = VLLMToolCodec(body())
    codec.events(native_events("")[0])
    with pytest.raises(ProviderResponseParseError):
        codec.events(
            {"type": "response.completed", "sequence_number": 1, "response": {"output": []}}
        )
    duplicate = body()
    duplicate["tools"][0]["tools"].append(copy.deepcopy(duplicate["tools"][0]["tools"][0]))
    with pytest.raises(ProviderRequestError):
        VLLMToolCodec(duplicate)


def test_regular_function_calls_keep_arguments_and_namespace():
    codec = VLLMToolCodec(body())
    output = codec.item(
        dict(item('{"cmd":"true"}', name="functions.exec_command"), status="completed")
    )
    assert output["type"] == "function_call" and output["arguments"] == '{"cmd":"true"}'
    assert output["name"] == "exec_command" and output["namespace"] == "functions"
    assert "async" not in output and "caller" not in output


@pytest.mark.asyncio
@pytest.mark.parametrize("configured", [False, True])
async def test_native_transport_normalizes_stream_and_nonstream_without_public_key_forwarding(configured):
    arguments = json.dumps({"input": "synthetic patch"})
    seen = []

    class Stream(httpx.AsyncByteStream):
        def __init__(self, content):
            self.content = content

        async def __aiter__(self):
            yield self.content

    def handler(request):
        seen.append(json.loads(request.content))
        assert request.headers["authorization"] == "Bearer backend-only-synthetic-0123456789abcdef"
        assert "cookie" not in request.headers
        if seen[-1].get("stream"):
            content = "".join(
                "data: " + json.dumps(event) + "\n\n" for event in native_events(arguments)
            )
            return httpx.Response(
                200, headers={"content-type": "text/event-stream"}, stream=Stream(content.encode())
            )
        return httpx.Response(200, json={"output": [dict(item(arguments), status="completed")]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter_class = LocalCodingVLLMAdapter
        caps = CAPS
        if configured:
            from slaif_gateway.modules.servers.upstream_llm.adapter import ConfiguredUpstreamLLMAdapter
            from slaif_gateway.modules.servers.upstream_llm.profiles import load_profiles

            profile = load_profiles()["native-vllm-v1"]
            adapter_class = ConfiguredUpstreamLLMAdapter
            caps = {
                "local_coding": dict(CAPS["local_coding_vllm"], contract_version="local-coding-v1"),
                "upstream_llm": {"version": 1, "profile": profile.profile_id,
                    "revision": profile.revision, "sha256": profile.sha256},
            }
        adapter = adapter_class(
            Settings(),
            route_capabilities=caps,
            base_url="https://backend.example/v1",
            api_key="backend-only-synthetic-0123456789abcdef",
            http_client=client,
        )
        request = ProviderRequest(
            provider="test", upstream_model="synthetic", endpoint="/v1/responses", body=body()
        )
        chunks = [chunk async for chunk in adapter.stream_response(request)]
        assert chunks[-1].json_body["item"]["type"] == "custom_tool_call"
        for chunk in chunks:
            assert json.loads(chunk.data) == chunk.json_body
            assert "data: " + chunk.data in chunk.raw_sse_event
        response = await adapter.forward_response(request)
        assert response.json_body["output"][0]["input"] == "synthetic patch"
        assert seen[0]["tools"][0]["name"] == "functions.apply_patch"


@pytest.mark.parametrize(
    "kind,name", [("custom", "functions.apply_patch"), ("function", "functions.exec_command")]
)
def test_native_terminal_regenerated_ids_restore_only_exact_closed_stream_call(kind, name):
    codec = VLLMToolCodec(body())
    arguments = json.dumps({"input": "synthetic patch"} if kind == "custom" else {"cmd": "true"})
    for event in native_events(arguments):
        if isinstance(event.get("item"), dict):
            event["item"]["name"] = name
        if "name" in event:
            event["name"] = name
        codec.events(event)
    native = dict(
        item(arguments, name=name), id="fc_terminal_new", call_id="call_terminal_new", status=None
    )
    result = codec.events(
        {"type": "response.completed", "sequence_number": 5, "response": {"output": [native]}}
    )[0]
    canonical = result["response"]["output"][0]
    assert canonical["id"] == "fc_synthetic" and canonical["call_id"] == "call_synthetic"
    assert canonical["type"] == ("custom_tool_call" if kind == "custom" else "function_call")
    assert canonical["status"] == "completed"
    for changed in (dict(native, arguments="{}"), dict(native, name="functions.unknown")):
        with pytest.raises(ProviderResponseParseError):
            codec.response({"output": [changed]}, terminal=True)


def test_native_argument_aggregate_and_fragment_count_are_bounded(monkeypatch):
    from slaif_gateway.modules.servers.local_coding_vllm import codec as module

    monkeypatch.setattr(module, "MAX_ARGUMENT_BYTES", 8)
    native = VLLMToolCodec(body())
    events = native_events("abcdefghij")
    native.events(events[0])
    native.events(events[1])
    with pytest.raises(ProviderResponseParseError):
        native.events(events[2])
    monkeypatch.setattr(module, "MAX_ARGUMENT_BYTES", 1024)
    monkeypatch.setattr(module, "MAX_ARGUMENT_EVENTS", 1)
    native = VLLMToolCodec(body())
    native.events(events[0])
    native.events(events[1])
    with pytest.raises(ProviderResponseParseError):
        native.events(events[2])


@pytest.mark.parametrize("field,value", [("type", []), ("item_id", {}), ("delta", "\ud800")])
def test_malformed_native_values_fail_without_raw_exceptions(field, value):
    native = VLLMToolCodec(body())
    events = native_events("{}")
    native.events(events[0])
    with pytest.raises(ProviderResponseParseError):
        native.events(dict(events[1], **{field: value}))


# --- Codex tool-call bindings (226-a secondary adapter scope) -------------
# Bindings are ephemeral core-validated per-call translation facts: they
# translate historical calls for removed tools without expanding authority.


def removed_history_body():
    """History calls functions.apply_patch after it left the current tools."""
    base = body()
    base["tools"][0]["tools"] = [base["tools"][0]["tools"][1]]
    base["input"] += [
        {
            "type": "custom_tool_call",
            "id": "ct_removed",
            "call_id": "c_removed",
            "namespace": "functions",
            "name": "apply_patch",
            "input": "synthetic patch",
        },
        {"type": "custom_tool_call_output", "call_id": "c_removed", "output": "ok"},
    ]
    return base


def exec_events(arguments='{"cmd":"true"}'):
    return [
        {
            "type": "response.output_item.added",
            "output_index": 0,
            "item": dict(item(arguments, name="functions.exec_command"), status="in_progress"),
            "sequence_number": 0,
        },
        {
            "type": "response.function_call_arguments.delta",
            "item_id": "fc_synthetic",
            "output_index": 0,
            "delta": arguments,
            "sequence_number": 1,
        },
        {
            "type": "response.function_call_arguments.done",
            "item_id": "fc_synthetic",
            "output_index": 0,
            "name": "functions.exec_command",
            "arguments": arguments,
            "sequence_number": 2,
        },
        {
            "type": "response.output_item.done",
            "output_index": 0,
            "item": dict(item(arguments, name="functions.exec_command"), status="completed"),
            "sequence_number": 3,
        },
    ]


def test_removed_history_is_translated_against_bindings_without_active_declaration():
    original = removed_history_body()
    snapshot = copy.deepcopy(original)
    codec = VLLMToolCodec(
        original, tool_call_bindings={"c_removed": ("functions", "apply_patch", "custom")}
    )
    assert original == snapshot
    # Active tools stay exactly the current declarations; no history union.
    assert [x["name"] for x in codec.body["tools"]] == ["functions.exec_command"]
    call = codec.body["input"][1]
    assert call["type"] == "function_call"
    assert call["name"] == "functions.apply_patch"
    assert json.loads(call["arguments"]) == {"input": "synthetic patch"}
    assert codec.body["input"][2] == {
        "type": "function_call_output", "call_id": "c_removed", "output": "ok"
    }


@pytest.mark.parametrize("portable", [False, True])
def test_removed_history_wire_names_are_stable_across_native_and_portable(portable):
    bindings = {"c_removed": ("functions", "apply_patch", "custom")}
    codec = VLLMToolCodec(
        removed_history_body(), portable_names=portable, tool_call_bindings=bindings
    )
    wire_name = codec.body["input"][1]["name"]
    # Same deterministic wire name as an equivalent still-declared tool.
    declared = VLLMToolCodec(body(), portable_names=portable)
    assert wire_name == declared.body["tools"][0]["name"]
    if portable:
        assert re.fullmatch(r"tool_[A-Za-z0-9_]{1,32}_[0-9a-f]{24}", wire_name)
    other = VLLMToolCodec(
        removed_history_body(), portable_names=portable, tool_call_bindings=bindings
    )
    assert other.body["input"][1]["name"] == wire_name
    assert codec.tool_call_bindings == bindings


def test_removed_new_output_is_denied_while_active_new_output_passes():
    codec = VLLMToolCodec(
        removed_history_body(), tool_call_bindings={"c_removed": ("functions", "apply_patch", "custom")}
    )
    removed_wire_name = codec.body["input"][1]["name"]
    with pytest.raises(ProviderResponseParseError):
        codec.item(
            dict(item(name=removed_wire_name), id="fc_new", call_id="call_new"), added=True
        )
    active = dict(
        item('{"cmd":"true"}', name="functions.exec_command"), id="fc_active", call_id="call_active"
    )
    assert codec.item(active, added=True)["name"] == "exec_command"


@pytest.mark.parametrize(
    "bindings",
    [
        # Missing entry: the historical call has no verified fact.
        {"other_call": ("functions", "apply_patch", "custom")},
        # Mismatched kind.
        {"c_removed": ("functions", "apply_patch", "function")},
        # Mismatched name.
        {"c_removed": ("functions", "other_tool", "custom")},
        # Explicit namespace contradicting the bound identity.
        {"c_removed": (None, "apply_patch", "custom")},
        # Malformed entries fail closed.
        {"c_removed": ("functions", "apply_patch")},
        {"c_removed": ("functions", "apply patch", "custom")},
        {"c_removed": (None, "apply_patch", "other")},
        {"bad id!": ("functions", "apply_patch", "custom")},
        ["not", "a", "mapping"],
    ],
)
def test_missing_or_mismatched_bindings_are_denied(bindings):
    with pytest.raises(ProviderRequestError):
        VLLMToolCodec(removed_history_body(), tool_call_bindings=bindings)


def test_history_call_without_call_id_is_denied_with_bindings():
    original = removed_history_body()
    del original["input"][1]["call_id"]
    with pytest.raises(ProviderRequestError):
        VLLMToolCodec(
            original, tool_call_bindings={"c_removed": ("functions", "apply_patch", "custom")}
        )


def test_omitted_namespace_resolves_through_binding_but_explicit_contradiction_denies():
    original = removed_history_body()
    del original["input"][1]["namespace"]
    codec = VLLMToolCodec(
        original, tool_call_bindings={"c_removed": ("functions", "apply_patch", "custom")}
    )
    assert codec.body["input"][1]["name"] == "functions.apply_patch"
    explicit = removed_history_body()
    explicit["input"][1]["namespace"] = None
    with pytest.raises(ProviderRequestError):
        VLLMToolCodec(
            explicit, tool_call_bindings={"c_removed": ("functions", "apply_patch", "custom")}
        )


@pytest.mark.parametrize(
    "current_tool,historical_item,historical_binding",
    [
        # Old custom call; the tool is currently declared as a function.
        (
            {
                "type": "function",
                "name": "apply_patch",
                "description": "Apply a patch",
                "parameters": {"type": "object", "properties": {}},
            },
            {
                "type": "custom_tool_call",
                "id": "ct1",
                "call_id": "c1",
                "namespace": "functions",
                "name": "apply_patch",
                "input": "patch",
            },
            ("functions", "apply_patch", "custom"),
        ),
        # Old function call; the tool is currently declared as custom.
        (
            {
                "type": "custom",
                "name": "apply_patch",
                "description": "Apply a patch",
                "format": {"type": "grammar", "syntax": "lark", "definition": "start: /.+/"},
            },
            {
                "type": "function_call",
                "id": "fc1",
                "call_id": "c1",
                "namespace": "functions",
                "name": "apply_patch",
                "arguments": '{"cmd":"x"}',
            },
            ("functions", "apply_patch", "function"),
        ),
    ],
)
def test_same_name_kind_transition_uses_historical_wrapper_and_active_map(
    current_tool, historical_item, historical_binding
):
    base = body()
    base["tools"] = [{"type": "namespace", "name": "functions", "tools": [current_tool]}]
    base["input"] += [
        historical_item,
        {"type": "function_call_output", "call_id": "c1", "output": "ok"},
    ]
    codec = VLLMToolCodec(base, tool_call_bindings={"c1": historical_binding})
    call = codec.body["input"][1]
    # Exact historical encoding per call kind, identity from the binding.
    assert call["id"] == historical_item["id"]
    assert call["call_id"] == "c1"
    assert call["type"] == "function_call"
    assert call["name"] == "functions.apply_patch"
    if historical_item["type"] == "custom_tool_call":
        assert json.loads(call["arguments"]) == {"input": "patch"}
    else:
        assert call["arguments"] == '{"cmd":"x"}'
    # Call/output association and original history order preserved.
    assert codec.body["input"][2] == {
        "type": "function_call_output", "call_id": "c1", "output": "ok"
    }
    # Active response map is exactly the current declaration; no history union.
    if current_tool["type"] == "custom":
        assert codec.body["tools"] == [
            {
                "type": "function",
                "name": "functions.apply_patch",
                "description": "Apply a patch Pass the raw custom-tool text as input.",
                "parameters": {
                    "type": "object",
                    "properties": {"input": {"type": "string"}},
                    "required": ["input"],
                    "additionalProperties": False,
                },
                "strict": False,
            }
        ]
    else:
        assert codec.body["tools"] == [dict(current_tool, name="functions.apply_patch")]
    # New response calls decode only with the active (current) kind.
    if current_tool["type"] == "custom":
        new = dict(
            item(json.dumps({"input": "new"}), name="functions.apply_patch"),
            id="fc_new",
            call_id="call_new",
        )
        decoded = codec.item(new)
        assert decoded["type"] == "custom_tool_call"
        assert decoded["input"] == "new"
    else:
        new = dict(item('{"cmd":"y"}', name="functions.apply_patch"), id="fc_new", call_id="call_new")
        decoded = codec.item(new)
        assert decoded["type"] == "function_call"
        assert decoded["arguments"] == '{"cmd":"y"}'
    assert decoded["namespace"] == "functions" and decoded["name"] == "apply_patch"


def test_active_same_kind_history_uses_binding_and_active_map():
    original = body()
    original["input"] += [
        {
            "type": "custom_tool_call",
            "id": "ct1",
            "call_id": "c1",
            "namespace": "functions",
            "name": "apply_patch",
            "input": "patch",
        },
        {"type": "custom_tool_call_output", "call_id": "c1", "output": "ok"},
    ]
    codec = VLLMToolCodec(
        original, tool_call_bindings={"c1": ("functions", "apply_patch", "custom")}
    )
    assert [x["name"] for x in codec.body["tools"]] == [
        "functions.apply_patch",
        "functions.exec_command",
    ]
    assert json.loads(codec.body["input"][1]["arguments"]) == {"input": "patch"}


def test_bindings_are_ephemeral_and_never_mutated():
    original = removed_history_body()
    snapshot = copy.deepcopy(original)
    bindings = {"c_removed": ("functions", "apply_patch", "custom")}
    bindings_snapshot = dict(bindings)
    codec = VLLMToolCodec(original, tool_call_bindings=bindings)
    assert original == snapshot
    assert bindings == bindings_snapshot
    assert "codex_tool_call_bindings" not in json.dumps(codec.body, ensure_ascii=True)
    assert set(codec.body["input"][1]) == {"type", "id", "call_id", "name", "arguments"}


def test_legacy_none_bindings_keep_current_map_behavior():
    assert VLLMToolCodec(body()).tool_call_bindings is None
    # Without bindings a historical call to a removed tool stays denied.
    with pytest.raises(ProviderRequestError):
        VLLMToolCodec(removed_history_body())


def dot_collision_history():
    """Two distinct approved identities collapse onto one native wire string."""
    base = body()
    base["tools"][0]["tools"] = [base["tools"][0]["tools"][1]]
    base["input"] += [
        {"type": "function_call", "id": "fc_a", "call_id": "c_a",
         "namespace": "mcp__codex_apps__space", "name": "sub.read", "arguments": "{}"},
        {"type": "function_call_output", "call_id": "c_a", "output": "a"},
        {"type": "function_call", "id": "fc_b", "call_id": "c_b",
         "namespace": "mcp__codex_apps__space.sub", "name": "read", "arguments": "{}"},
        {"type": "function_call_output", "call_id": "c_b", "output": "b"},
    ]
    return base


def test_native_wire_identity_collision_between_historical_calls_is_denied():
    with pytest.raises(ProviderRequestError) as exc:
        VLLMToolCodec(dot_collision_history(), tool_call_bindings={
            "c_a": ("mcp__codex_apps__space", "sub.read", "function"),
            "c_b": ("mcp__codex_apps__space.sub", "read", "function"),
        })
    assert exc.value.error_code == "vllm_native_wire_identity_collision"
    assert "mcp__codex_apps__space" not in exc.value.safe_message


def test_native_wire_identity_collision_with_current_declaration_is_denied():
    base = body()
    base["tools"] = [
        {"type": "namespace", "name": "mcp__codex_apps__space.sub", "tools": [
            {"type": "function", "name": "read",
             "parameters": {"type": "object", "properties": {}}},
        ]},
    ]
    base["input"] += [
        {"type": "function_call", "id": "fc_a", "call_id": "c_a",
         "namespace": "mcp__codex_apps__space", "name": "sub.read", "arguments": "{}"},
        {"type": "function_call_output", "call_id": "c_a", "output": "a"},
    ]
    with pytest.raises(ProviderRequestError) as exc:
        VLLMToolCodec(base, tool_call_bindings={
            "c_a": ("mcp__codex_apps__space", "sub.read", "function")
        })
    assert exc.value.error_code == "vllm_native_wire_identity_collision"


def test_portable_wire_identities_remain_distinct_for_dot_colliding_names():
    base = dot_collision_history()
    base["input"] += [
        {"type": "function_call", "id": "fc_a2", "call_id": "c_a2",
         "namespace": "mcp__codex_apps__space", "name": "sub.read", "arguments": "{}"},
        {"type": "function_call_output", "call_id": "c_a2", "output": "a2"},
    ]
    codec = VLLMToolCodec(base, portable_names=True, tool_call_bindings={
        "c_a": ("mcp__codex_apps__space", "sub.read", "function"),
        "c_b": ("mcp__codex_apps__space.sub", "read", "function"),
        "c_a2": ("mcp__codex_apps__space", "sub.read", "function"),
    })
    names = [codec.body["input"][i]["name"] for i in (1, 3, 5)]
    assert names[0] != names[1]
    # Repeated calls of one identity keep the same deterministic wire name.
    assert names[0] == names[2]
    assert all(re.fullmatch(r"tool_[A-Za-z0-9_]{1,32}_[0-9a-f]{24}", n) for n in names)


@pytest.mark.asyncio
async def test_vllm_transport_translates_bound_removed_history_and_leaks_nothing():
    arguments = '{"cmd":"true"}'
    seen = []

    class Stream(httpx.AsyncByteStream):
        def __init__(self, content):
            self.content = content

        async def __aiter__(self):
            yield self.content

    def handler(request):
        wire = json.loads(request.content)
        seen.append(wire)
        expected_keys = {"model", "input", "tools"} | ({"stream"} if wire.get("stream") else set())
        assert set(wire) == expected_keys
        assert [t["name"] for t in wire["tools"]] == ["functions.exec_command"]
        assert wire["input"][1] == {
            "type": "function_call",
            "id": "ct_removed",
            "call_id": "c_removed",
            "name": "functions.apply_patch",
            "arguments": '{"input": "synthetic patch"}',
        }
        assert wire["input"][2]["type"] == "function_call_output"
        assert request.headers["authorization"] == "Bearer backend-only-synthetic-0123456789abcdef"
        assert "cookie" not in request.headers
        if wire.get("stream"):
            content = "".join(
                "data: " + json.dumps(event) + "\n\n" for event in exec_events()
            )
            return httpx.Response(
                200, headers={"content-type": "text/event-stream"}, stream=Stream(content.encode())
            )
        return httpx.Response(
            200,
            json={"output": [dict(item(arguments, name="functions.exec_command"), status="completed")]},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter = LocalCodingVLLMAdapter(
            Settings(),
            route_capabilities=CAPS,
            base_url="https://backend.example/v1",
            api_key="backend-only-synthetic-0123456789abcdef",
            http_client=client,
        )
        request = ProviderRequest(
            provider="test",
            upstream_model="synthetic",
            endpoint="/v1/responses",
            body=removed_history_body(),
            codex_tool_call_bindings={"c_removed": ("functions", "apply_patch", "custom")},
        )
        chunks = [chunk async for chunk in adapter.stream_response(request)]
        assert chunks[-1].json_body["item"]["type"] == "function_call"
        assert chunks[-1].json_body["item"]["name"] == "exec_command"
        assert chunks[-1].json_body["item"]["namespace"] == "functions"
        response = await adapter.forward_response(request)
        assert response.json_body["output"][0]["type"] == "function_call"
        assert response.json_body["output"][0]["arguments"] == arguments
    for wire in seen:
        assert "codex_tool_call_bindings" not in wire
