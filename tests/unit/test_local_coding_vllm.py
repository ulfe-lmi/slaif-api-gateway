"""Synthetic native-vLLM wire contracts; real backend evidence is separate."""

import copy
import json
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
async def test_native_transport_normalizes_stream_and_nonstream_without_public_key_forwarding():
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
        adapter = LocalCodingVLLMAdapter(
            Settings(),
            route_capabilities=CAPS,
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
