"""Request-scoped, bounded native-vLLM tool translation; no execution authority."""

from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass, field as dataclass_field

from slaif_gateway.providers.errors import ProviderResponseParseError, ProviderRequestError

MAX_ARGUMENT_BYTES = 1_048_576
MAX_TOOL_ITEMS = 3
MAX_DELTA_BYTES = 65_536
MAX_ARGUMENT_EVENTS = 65_536
_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]{0,127}$")
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$")


def _bad(code="vllm_tool_protocol_invalid") -> ProviderResponseParseError:
    return ProviderResponseParseError(
        provider="local-coding-vLLM",
        error_code=code,
        safe_message="Native vLLM tool response does not match the declared tool contract.",
    )


def _size(value: str) -> int:
    try:
        return len(value.encode("utf-8"))
    except UnicodeError as exc:
        raise _bad() from exc


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate native tool argument")
        result[key] = value
    return result


def _reject_nonfinite(_):
    raise ValueError("Nonfinite JSON argument")


def _function_arguments(arguments: str, *, replay: bool = False) -> None:
    """Native vLLM function arguments are complete JSON objects, never patches."""
    try:
        if not isinstance(arguments, str) or len(arguments.encode("utf-8")) > MAX_ARGUMENT_BYTES:
            raise ValueError
        value = json.loads(arguments, object_pairs_hook=_unique_pairs,
                           parse_constant=_reject_nonfinite)
        if not isinstance(value, dict):
            raise ValueError
    except (ValueError, TypeError, RecursionError, UnicodeError):
        if replay:
            raise ProviderRequestError(
                "Replayed function-call arguments contain invalid JSON. Start a new conversation "
                "or rewind before the interrupted tool call; existing files are unaffected.",
                provider="local-coding-vLLM", status_code=400,
                error_type="invalid_request_error", error_code="vllm_replay_arguments_invalid",
            ) from None
        raise _bad("vllm_function_arguments_invalid") from None


def _json_input(arguments: str) -> str:
    try:
        value = json.loads(arguments, object_pairs_hook=_unique_pairs)
    except (ValueError, TypeError, RecursionError) as exc:
        raise _bad("vllm_custom_arguments_invalid") from exc
    if (
        not isinstance(value, dict)
        or set(value) != {"input"}
        or not isinstance(value["input"], str)
    ):
        raise _bad("vllm_custom_arguments_invalid")
    if _size(value["input"]) > MAX_ARGUMENT_BYTES:
        raise _bad("vllm_custom_arguments_invalid")
    return value["input"]


@dataclass
class _Call:
    name: str
    index: int
    call_id: str
    kind: str
    arguments: str = ""
    deltas: list[str] = dataclass_field(default_factory=list)
    argument_bytes: int = 0
    done: bool = False
    closed: bool = False


class VLLMToolCodec:
    def __init__(self, body):
        self.body = copy.deepcopy(dict(body))
        self.original_tools = copy.deepcopy(self.body.get("tools", []))
        self.tools: dict[str, tuple[str | None, str, str]] = {}
        self.calls: dict[str, _Call] = {}
        self.in_sequence = -1
        self.out_sequence = 0
        flat = []
        for group in self.original_tools:
            namespace = group.get("name") if group.get("type") == "namespace" else None
            entries = group.get("tools", []) if namespace is not None else [group]
            if namespace is not None and (
                not isinstance(namespace, str) or not _NAME.fullmatch(namespace)
            ):
                raise ProviderRequestError(provider="local-coding-vLLM")
            for tool in entries:
                name = tool.get("name")
                kind = tool.get("type")
                if (
                    not isinstance(name, str)
                    or not _NAME.fullmatch(name)
                    or kind not in {"function", "custom"}
                ):
                    raise ProviderRequestError(provider="local-coding-vLLM")
                wire_name = f"{namespace}.{name}" if namespace else name
                if wire_name in self.tools or len(self.tools) >= 256:
                    raise ProviderRequestError(provider="local-coding-vLLM")
                self.tools[wire_name] = (namespace, name, kind)
                if kind == "custom":
                    if (namespace, name) != ("functions", "apply_patch"):
                        raise ProviderRequestError(provider="local-coding-vLLM")
                    converted = {
                        "type": "function",
                        "name": wire_name,
                        "description": tool.get("description", "")
                        + " Pass the raw patch text as input.",
                        "parameters": {
                            "type": "object",
                            "properties": {"input": {"type": "string"}},
                            "required": ["input"],
                            "additionalProperties": False,
                        },
                        "strict": False,
                    }
                else:
                    converted = dict(tool, name=wire_name)
                flat.append(converted)
        if "tools" in self.body:
            self.body["tools"] = flat
        for item in self.body.get("input", []):
            if not isinstance(item, dict):
                continue
            if item.get("role") == "user" and isinstance(item.get("content"), list):
                for part in item["content"]:
                    if isinstance(part, dict) and part.get("type") == "input_image":
                        # Native vLLM 0.27 requires the optional OpenAI detail
                        # field, even when the client chooses the default.
                        part.setdefault("detail", "auto")
            kind = item.get("type")
            if kind in {"function_call_output", "custom_tool_call_output"} and isinstance(item.get("output"), list):
                for part in item["output"]:
                    if isinstance(part, dict) and part.get("type") == "input_image":
                        part.setdefault("detail", "auto")
            if kind == "custom_tool_call_output":
                item["type"] = "function_call_output"
            elif kind in {"custom_tool_call", "function_call"}:
                namespace = item.pop("namespace", None)
                wire_name = f"{namespace}.{item.get('name')}" if namespace else item.get("name")
                declaration = self.tools.get(wire_name)
                expected = "custom" if kind == "custom_tool_call" else "function"
                if declaration is None or declaration[2] != expected:
                    raise ProviderRequestError(provider="local-coding-vLLM")
                item["name"] = wire_name
                if kind == "custom_tool_call":
                    item["type"] = "function_call"
                    item["arguments"] = json.dumps({"input": item.pop("input")}, ensure_ascii=True)
                else:
                    _function_arguments(item.get("arguments"), replay=True)

    def item(self, raw, *, added=False):
        if not isinstance(raw, dict) or raw.get("type") != "function_call":
            return raw
        item = dict(raw)
        for field in ("async", "caller"):
            if field in item:
                if item.pop(field) is not None:
                    raise _bad("vllm_native_authority_not_supported")
        wire_name = item.get("name")
        declaration = self.tools.get(wire_name) if isinstance(wire_name, str) else None
        if declaration is None:
            raise _bad()
        namespace, name, kind = declaration
        if item.get("namespace") not in (None, namespace):
            raise _bad()
        item["name"] = name
        if namespace is not None:
            item["namespace"] = namespace
        else:
            item.pop("namespace", None)
        if kind == "custom":
            arguments = item.pop("arguments", None)
            if not isinstance(arguments, str) or _size(arguments) > MAX_ARGUMENT_BYTES:
                raise _bad()
            if added and arguments != "":
                raise _bad()
            item["type"] = "custom_tool_call"
            item["input"] = "" if added else _json_input(arguments)
        elif not added:
            _function_arguments(item.get("arguments"))
        return item

    def response(self, raw, *, terminal=False):
        response = dict(raw)
        output = raw.get("output", [])
        if not isinstance(output, list) or len(output) > MAX_TOOL_ITEMS:
            raise _bad("vllm_terminal_call_mismatch")
        converted = []
        seen = set()
        for index, item in enumerate(output):
            canonical = self.item(item)
            if terminal and isinstance(item, dict) and item.get("type") == "function_call":
                matches = [
                    (item_id, state)
                    for item_id, state in self.calls.items()
                    if state.index == index
                ]
                if len(matches) != 1:
                    raise _bad("vllm_terminal_call_mismatch")
                item_id, state = matches[0]
                if (
                    not state.closed
                    or item.get("arguments") != state.arguments
                    or item.get("name") != state.name
                ):
                    raise _bad("vllm_terminal_call_mismatch")
                # Native vLLM rebuilds terminal call identifiers. Bind only by
                # the closed stream's exact index, declared name and arguments.
                for field in ("id", "call_id"):
                    value = item.get(field)
                    if not isinstance(value, str) or not _ID.fullmatch(value):
                        raise _bad("vllm_terminal_call_mismatch")
                if item.get("status") not in (None, "completed"):
                    raise _bad("vllm_terminal_call_mismatch")
                canonical.update(id=item_id, call_id=state.call_id, status="completed")
                seen.add(item_id)
            converted.append(canonical)
        if terminal and seen != set(self.calls):
            raise _bad("vllm_terminal_call_mismatch")
        if "output" in response:
            response["output"] = converted
        if "tools" in response:
            response["tools"] = self.original_tools
        return response

    def _emit(self, event):
        event["sequence_number"] = self.out_sequence
        self.out_sequence += 1
        return event

    def events(self, raw):
        event = copy.deepcopy(dict(raw))
        seq = event.get("sequence_number")
        if type(seq) is not int or seq != self.in_sequence + 1 or seq > 1_000_000:
            raise _bad()
        self.in_sequence = seq
        typ = event.get("type")
        if not isinstance(typ, str):
            raise _bad()
        if typ in {"response.output_item.added", "response.output_item.done"}:
            raw_item = event.get("item")
            event["item"] = self.item(raw_item, added=typ.endswith("added"))
            if isinstance(raw_item, dict) and raw_item.get("type") == "function_call":
                item_id = event["item"].get("id")
                index = event.get("output_index")
                if (
                    not isinstance(item_id, str)
                    or not _ID.fullmatch(item_id)
                    or type(index) is not int
                    or not 0 <= index < MAX_TOOL_ITEMS
                ):
                    raise _bad()
                if typ.endswith("added"):
                    call_id = event["item"].get("call_id")
                    if (
                        item_id in self.calls
                        or len(self.calls) >= MAX_TOOL_ITEMS
                        or not isinstance(call_id, str)
                        or not _ID.fullmatch(call_id)
                    ):
                        raise _bad()
                    if any(state.index == index for state in self.calls.values()):
                        raise _bad()
                    self.calls[item_id] = _Call(
                        raw_item["name"], index, call_id, self.tools[raw_item["name"]][2]
                    )
                else:
                    state = self.calls.get(item_id)
                    if (
                        state is None
                        or not state.done
                        or state.closed
                        or state.index != index
                        or state.call_id != event["item"].get("call_id")
                        or state.name != raw_item.get("name")
                        or state.arguments != raw_item.get("arguments")
                    ):
                        raise _bad()
                    state.closed = True
        elif typ in {
            "response.function_call_arguments.delta",
            "response.function_call_arguments.done",
        }:
            item_id = event.get("item_id")
            if not isinstance(item_id, str):
                raise _bad()
            state = self.calls.get(item_id)
            if state is not None:
                allowed = (
                    {"type", "sequence_number", "item_id", "output_index", "delta"}
                    if typ.endswith("delta")
                    else {"type", "sequence_number", "item_id", "output_index", "name", "arguments"}
                )
                if (
                    set(event) - allowed
                    or type(event.get("output_index")) is not int
                    or event.get("output_index") != state.index
                    or state.done
                    or state.closed
                ):
                    raise _bad()
                if typ.endswith("delta"):
                    delta = event.get("delta")
                    if (
                        not isinstance(delta, str)
                        or _size(delta) > MAX_DELTA_BYTES
                        or state.argument_bytes + _size(delta) > MAX_ARGUMENT_BYTES
                        or len(state.deltas) >= MAX_ARGUMENT_EVENTS
                    ):
                        raise _bad()
                    state.argument_bytes += _size(delta)
                    state.deltas.append(delta)
                    if state.kind == "custom":
                        return []
                    return [self._emit(event)]
                joined = "".join(state.deltas)
                if event.get("arguments") != joined or event.get("name", state.name) != state.name:
                    raise _bad()
                if state.kind == "function":
                    _function_arguments(joined)
                state.arguments = joined
                state.deltas.clear()
                state.done = True
                if state.kind == "function":
                    if "name" in event:
                        event["name"] = self.tools[state.name][1]
                    return [self._emit(event)]
                value = _json_input(state.arguments)
                # Small Unicode-safe chunks retain the existing 64-KiB delta ceiling.
                return [
                    self._emit(
                        {
                            "type": "response.custom_tool_call_input.delta",
                            "item_id": event["item_id"],
                            "output_index": state.index,
                            "call_id": state.call_id,
                            "delta": value[i : i + 16384],
                        }
                    )
                    for i in range(0, len(value), 16384)
                ]
            if typ.endswith("done") and "name" in event:
                if not isinstance(event["name"], str):
                    raise _bad()
                declaration = self.tools.get(event["name"])
                if declaration is None or declaration[2] != "function":
                    raise _bad()
                event["name"] = declaration[1]
        elif isinstance(event.get("response"), dict):
            if typ == "response.completed" and any(
                not state.closed for state in self.calls.values()
            ):
                raise _bad()
            event["response"] = self.response(
                event["response"], terminal=typ == "response.completed"
            )
        return [self._emit(event)]
