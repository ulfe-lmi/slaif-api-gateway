"""Pinned OpenCode 1.19.3 flat Responses client module.

Provenance: OpenCode 1.19.3 (tag ``v1.19.3``, commit
``e3c4eb242585dcd77be1a867391b7c25fd47ce52``); reviewed execution sha256
``179ca421d61eefeadfa0c50e084a6e79c1623734732f0f4593f81ccfd3ab7ee9``.
The SDK entry point is ``@ai-sdk/openai`` 3.0.88 with nested 3.0.84 copies;
the evidence does not identify which copy loaded, so no loaded-copy
inference is made.

The module encodes the captured flat dialect only: nine top-level request
fields (``stream`` true, ``store`` false, ``tool_choice`` "auto", ``include``
limited to ``reasoning.encrypted_content``, ``reasoning`` limited to a five-valued
``effort``), typeless developer/user messages, id-less
``function_call``/``function_call_output`` replay, and flat strict function
tool declarations whose nine names are a bounded vocabulary, not authority.
The provider replays function calls, outputs, and encrypted reasoning without
item IDs or status, so id-less encrypted reasoning relies on the gateway's
owned ciphertext-derived reference path (the 228-a security decision): a
domain-separated bounded-cipher HMAC held in immediate memory only, with no
fabricated protocol ID, no raw content storage, persistence from successful
finalized output, and same-key plus route/provider/model binding.  Selection
is key-metadata-only; no user-agent or session hints carry authority.
"""

from __future__ import annotations

import copy
import dataclasses
import json
import re
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType
from typing import Any

from slaif_gateway.modules.agent_chat_profile_data import (
    AgentChatProfileDataError,
    canonical_profile_digest,
)
from slaif_gateway.modules.clients.codex_0149 import (
    CODEX_0149_POLICY_SPEC,
    codex_0149_zero_argument_function_names,
)
from slaif_gateway.modules.contracts import (
    CanonicalClientRequest,
    ModuleSelectionError,
)

OPENCODE_1193_RESPONSES_CLIENT_MODULE_ID = "opencode-1.19.3-responses-v1"
OPENCODE_1193_RESPONSES_CLIENT_MODULE_VERSION = "1"

_MAX_PROFILE_DATA_BYTES = 64 * 1024
_PROFILE_PATH = Path(__file__).parent / "profiles" / "opencode-1.19.3-responses.json"

_PROFILE_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]*-v[0-9]+$")
_PROFILE_VERSION_PATTERN = re.compile(r"^[0-9]+$")
_CLIENT_NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
_SDK_VERSION_PATTERN = re.compile(
    r"^[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z][0-9A-Za-z.-]*)?$"
)
_SOURCE_TAG_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")
_SOURCE_COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")
_SDK_NAME_PATTERN = re.compile(
    r"^(?:@[a-z0-9][a-z0-9._-]*/)?[a-z0-9][a-z0-9._-]*$"
)
_TOOL_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9._-]*$")
_TOOL_CALL_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
_KNOWN_REASONING_EFFORTS = frozenset({"minimal", "low", "medium", "high", "xhigh"})

# Local copies of the Codex 0.149 security vocabulary; the 0.149 names are
# private, so the same bounded denial set is mirrored here.
_FORBIDDEN_AUTHORITY_TYPES = frozenset(
    {
        "web_search_preview",
        "web_search_preview_2025_03_11",
        "web_search_2025_08_26",
        "file_search",
        "code_interpreter",
        "computer",
        "computer_use",
        "computer_use_preview",
        "image_generation",
        "mcp",
        "shell",
        "local_shell",
        "apply_patch",
    }
)
_FORBIDDEN_AUTHORITY_KEYS = frozenset(
    {
        "authorization",
        "api_key",
        "apikey",
        "headers",
        "server_url",
        "connector",
        "mcp_server",
    }
)
_MAX_DECLARATION_DEPTH = 32

_ALLOWED_FIELDS = frozenset(
    {
        "include",
        "input",
        "max_output_tokens",
        "model",
        "reasoning",
        "store",
        "stream",
        "tool_choice",
        "tools",
    }
)
_ALLOWED_INCLUDE_VALUES = frozenset({"reasoning.encrypted_content"})
_ALLOWED_INPUT_ROLES = frozenset({"developer", "user"})
_MAX_MODEL_BYTES = 256
_MAX_MAX_OUTPUT_TOKENS = 1_048_576
_MAX_INPUT_ITEMS = 1024
_MAX_INPUT_TEXT_BYTES = 1_048_576
_MAX_INPUT_PARTS = 64


@dataclasses.dataclass(frozen=True)
class Opencode1193ResponsesProfileData:
    """Reviewed, frozen OpenCode 1.19.3 Responses profile facts."""

    profile_id: str
    profile_version: str
    client_name: str
    distribution_version: str
    source_tag: str
    source_commit: str
    sdk_name: str
    sdk_version: str
    reasoning_efforts: frozenset[str]
    tool_names: frozenset[str]
    max_tool_declarations: int
    max_description_bytes: int
    max_schema_depth: int
    max_schema_properties: int
    max_declaration_bytes: int
    tool_call_id_min_length: int
    tool_call_id_max_length: int
    tool_call_arguments_max_bytes: int
    document: Mapping[str, Any]
    fixture_sha256: str


def _strict_pairs_hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise AgentChatProfileDataError(
                "key", "The profile object contains a duplicate key"
            )
        result[key] = value
    return result


def _reject_constant(name: str) -> object:
    raise AgentChatProfileDataError(
        "constant", "The profile contains a non-portable JSON constant"
    )


def _deep_freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _deep_freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_deep_freeze(item) for item in value)
    return value


def _require_mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise AgentChatProfileDataError(field, "The value must be an object")
    return value


def _require_str(
    value: Any,
    field: str,
    *,
    pattern: re.Pattern[str] | None = None,
    max_length: int | None = None,
) -> str:
    if not isinstance(value, str):
        raise AgentChatProfileDataError(field, "The value must be a string")
    if max_length is not None and len(value) > max_length:
        raise AgentChatProfileDataError(field, "The value exceeds the length limit")
    if pattern is not None and pattern.fullmatch(value) is None:
        raise AgentChatProfileDataError(field, "The value has an invalid format")
    return value


def _require_int(value: Any, field: str, *, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise AgentChatProfileDataError(field, "The value must be an integer")
    if not minimum <= value <= maximum:
        raise AgentChatProfileDataError(field, "The value is outside the allowed range")
    return value


def _require_str_list(
    value: Any,
    field: str,
    *,
    minimum: int,
    maximum: int,
    pattern: re.Pattern[str] | None = None,
    allowed: frozenset[str] | None = None,
) -> list[str]:
    if not isinstance(value, list):
        raise AgentChatProfileDataError(field, "The value must be an array")
    if not minimum <= len(value) <= maximum:
        raise AgentChatProfileDataError(field, "The value has an invalid count")
    if not all(isinstance(item, str) for item in value):
        raise AgentChatProfileDataError(field, "The value contains a non-string entry")
    if len(set(value)) != len(value):
        raise AgentChatProfileDataError(field, "The value contains duplicate entries")
    for item in value:
        if pattern is not None and pattern.fullmatch(item) is None:
            raise AgentChatProfileDataError(field, "The value contains an invalid entry")
    if allowed is not None and not set(value) <= allowed:
        raise AgentChatProfileDataError(field, "The value contains an unsupported entry")
    return value


def _parse_client_block(document: Mapping[str, Any]) -> dict[str, str]:
    client = _require_mapping(document["client"], "client")
    if set(client) != {
        "name",
        "distribution_version",
        "source_tag",
        "source_commit",
        "sdk_name",
        "sdk_version",
        "wire_api",
    }:
        raise AgentChatProfileDataError("client", "The client object has an unsupported key set")
    wire_api = client["wire_api"]
    if not isinstance(wire_api, str) or wire_api != "responses":
        raise AgentChatProfileDataError("client.wire_api", "The wire API is not supported")
    return {
        "client_name": _require_str(
            client["name"], "client.name", pattern=_CLIENT_NAME_PATTERN, max_length=64
        ),
        "distribution_version": _require_str(
            client["distribution_version"],
            "client.distribution_version",
            pattern=_SDK_VERSION_PATTERN,
        ),
        "source_tag": _require_str(
            client["source_tag"],
            "client.source_tag",
            pattern=_SOURCE_TAG_PATTERN,
            max_length=128,
        ),
        "source_commit": _require_str(
            client["source_commit"],
            "client.source_commit",
            pattern=_SOURCE_COMMIT_PATTERN,
        ),
        "sdk_name": _require_str(
            client["sdk_name"],
            "client.sdk_name",
            pattern=_SDK_NAME_PATTERN,
            max_length=128,
        ),
        "sdk_version": _require_str(
            client["sdk_version"], "client.sdk_version", pattern=_SDK_VERSION_PATTERN
        ),
    }


def _parse_dialect_block(document: Mapping[str, Any]) -> dict[str, Any]:
    dialect = _require_mapping(document["dialect"], "dialect")
    if set(dialect) != {"reasoning_efforts", "tools", "tool_call"}:
        raise AgentChatProfileDataError("dialect", "The dialect object has an unsupported key set")
    tools = _require_mapping(dialect["tools"], "dialect.tools")
    if set(tools) != {
        "names",
        "max_declarations",
        "max_description_bytes",
        "max_schema_depth",
        "max_schema_properties",
        "max_declaration_bytes",
    }:
        raise AgentChatProfileDataError("dialect.tools", "The tools object has an unsupported key set")
    tool_call = _require_mapping(dialect["tool_call"], "dialect.tool_call")
    if set(tool_call) != {"id_min_length", "id_max_length", "arguments_max_bytes"}:
        raise AgentChatProfileDataError("dialect.tool_call", "The tool_call object has an unsupported key set")
    id_min_length = _require_int(
        tool_call["id_min_length"], "dialect.tool_call.id_min_length", minimum=1, maximum=512
    )
    id_max_length = _require_int(
        tool_call["id_max_length"], "dialect.tool_call.id_max_length", minimum=1, maximum=512
    )
    if id_min_length > id_max_length:
        raise AgentChatProfileDataError(
            "dialect.tool_call", "The tool-call id bounds are inconsistent"
        )
    return {
        "reasoning_efforts": frozenset(
            _require_str_list(
                dialect["reasoning_efforts"],
                "dialect.reasoning_efforts",
                minimum=1,
                maximum=5,
                allowed=_KNOWN_REASONING_EFFORTS,
            )
        ),
        "tool_names": frozenset(
            _require_str_list(
                tools["names"],
                "dialect.tools.names",
                minimum=1,
                maximum=64,
                pattern=_TOOL_NAME_PATTERN,
            )
        ),
        "max_tool_declarations": _require_int(
            tools["max_declarations"], "dialect.tools.max_declarations", minimum=1, maximum=64
        ),
        "max_description_bytes": _require_int(
            tools["max_description_bytes"],
            "dialect.tools.max_description_bytes",
            minimum=1,
            maximum=262144,
        ),
        "max_schema_depth": _require_int(
            tools["max_schema_depth"], "dialect.tools.max_schema_depth", minimum=1, maximum=16
        ),
        "max_schema_properties": _require_int(
            tools["max_schema_properties"],
            "dialect.tools.max_schema_properties",
            minimum=1,
            maximum=256,
        ),
        "max_declaration_bytes": _require_int(
            tools["max_declaration_bytes"],
            "dialect.tools.max_declaration_bytes",
            minimum=1,
            maximum=262144,
        ),
        "tool_call_id_min_length": id_min_length,
        "tool_call_id_max_length": id_max_length,
        "tool_call_arguments_max_bytes": _require_int(
            tool_call["arguments_max_bytes"],
            "dialect.tool_call.arguments_max_bytes",
            minimum=1,
            maximum=262144,
        ),
    }


def parse_opencode_1193_responses_profile_data(raw: bytes) -> Opencode1193ResponsesProfileData:
    """Parse and validate the packaged OpenCode 1.19.3 profile bytes."""
    if not isinstance(raw, (bytes, bytearray)):
        raise AgentChatProfileDataError("profile", "The profile data is not bytes")
    if len(raw) > _MAX_PROFILE_DATA_BYTES:
        raise AgentChatProfileDataError("profile", "The profile data exceeds the byte limit")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise AgentChatProfileDataError("profile", "The profile data is not UTF-8") from None
    try:
        document = json.loads(
            text,
            object_pairs_hook=_strict_pairs_hook,
            parse_constant=_reject_constant,
        )
    except (json.JSONDecodeError, RecursionError):
        raise AgentChatProfileDataError(
            "profile", "The profile data is not valid strict JSON"
        ) from None
    if not isinstance(document, Mapping):
        raise AgentChatProfileDataError("profile", "The profile must be an object")
    if set(document) != {"schema_version", "id", "version", "client", "dialect"}:
        raise AgentChatProfileDataError(
            "profile", "The profile object has an unsupported key set"
        )
    if isinstance(document["schema_version"], bool) or document["schema_version"] != 1:
        raise AgentChatProfileDataError(
            "schema_version", "The profile schema version is not supported"
        )
    profile_id = _require_str(
        document["id"], "id", pattern=_PROFILE_ID_PATTERN, max_length=64
    )
    profile_version = _require_str(
        document["version"], "version", pattern=_PROFILE_VERSION_PATTERN, max_length=9
    )
    client_facts = _parse_client_block(document)
    dialect_facts = _parse_dialect_block(document)
    fixture_sha256 = canonical_profile_digest(dict(document))
    return Opencode1193ResponsesProfileData(
        profile_id=profile_id,
        profile_version=profile_version,
        **client_facts,
        **dialect_facts,
        document=_deep_freeze(dict(document)),
        fixture_sha256=fixture_sha256,
    )


OPENCODE_1193_RESPONSES_PROFILE_DATA = parse_opencode_1193_responses_profile_data(
    _PROFILE_PATH.read_bytes()
)

OPENCODE_1193_RESPONSES_PROFILE_FIXTURE_SHA256 = (
    OPENCODE_1193_RESPONSES_PROFILE_DATA.fixture_sha256
)

OPENCODE_1193_RESPONSES_POLICY_SPEC = dataclasses.replace(
    CODEX_0149_POLICY_SPEC,
    allow_idless_encrypted_reasoning=True,
    # Native wire is flat (no namespace field): a removed function tool may
    # still replay after its same-key CALL-ID HMAC proof, without ever
    # rejoining the active declaration set.
    historical_flat_tool_identity=True,
    # The pinned OpenCode SDK wire requires a valid ``output_index`` on
    # every ``response.output_item.added``/``done`` event; optional-index
    # acceptance is not conformance proof for this profile.
    require_stream_output_indices=True,
    reasoning_efforts=OPENCODE_1193_RESPONSES_PROFILE_DATA.reasoning_efforts,
    client_metadata_keys=frozenset(),
    max_client_metadata_keys=0,
    max_client_metadata_key_bytes=0,
    max_client_metadata_value_bytes=0,
    max_client_metadata_bytes=0,
)

_PROFILE_FACTS = MappingProxyType(
    {
        "client_module_id": OPENCODE_1193_RESPONSES_CLIENT_MODULE_ID,
        "client_module_version": OPENCODE_1193_RESPONSES_CLIENT_MODULE_VERSION,
        "fixture_sha256": OPENCODE_1193_RESPONSES_PROFILE_FIXTURE_SHA256,
        "source_tag": OPENCODE_1193_RESPONSES_PROFILE_DATA.source_tag,
        "source_commit": OPENCODE_1193_RESPONSES_PROFILE_DATA.source_commit,
        "sdk_name": OPENCODE_1193_RESPONSES_PROFILE_DATA.sdk_name,
        "sdk_version": OPENCODE_1193_RESPONSES_PROFILE_DATA.sdk_version,
    }
)


def _error(message: str, code: str = "opencode_1193_request_invalid") -> ModuleSelectionError:
    return ModuleSelectionError(message, error_code=code)


def _validate_declaration_node(value: Any, *, depth: int) -> None:
    """Bound a tool declaration node and deny authority shapes."""
    if depth > _MAX_DECLARATION_DEPTH:
        raise _error(
            "The OpenCode 1.19.3 tool declaration is too deeply nested",
            "opencode_1193_tool_declaration",
        )
    if isinstance(value, Mapping):
        if depth > OPENCODE_1193_RESPONSES_PROFILE_DATA.max_schema_depth:
            raise _error(
                "The OpenCode 1.19.3 tool declaration is too deeply nested",
                "opencode_1193_tool_declaration",
            )
        if len(value) > OPENCODE_1193_RESPONSES_PROFILE_DATA.max_schema_properties:
            raise _error(
                "The OpenCode 1.19.3 tool declaration has too many properties",
                "opencode_1193_tool_declaration",
            )
        for key, child in value.items():
            if not isinstance(key, str):
                raise _error(
                    "The OpenCode 1.19.3 tool declaration has an invalid property",
                    "opencode_1193_tool_declaration",
                )
            if key.lower() in _FORBIDDEN_AUTHORITY_KEYS:
                raise _error(
                    "The OpenCode 1.19.3 tool declaration contains a prohibited authority field",
                    "opencode_1193_authority_shape",
                )
            if (
                depth > 0
                and key == "type"
                and isinstance(child, str)
                and child in _FORBIDDEN_AUTHORITY_TYPES
            ):
                raise _error(
                    "The OpenCode 1.19.3 tool declaration contains a prohibited authority shape",
                    "opencode_1193_authority_shape",
                )
            _validate_declaration_node(child, depth=depth + 1)
        return
    if isinstance(value, list):
        for child in value:
            _validate_declaration_node(child, depth=depth + 1)
        return
    # Scalars (string, number, boolean, null) are leaf JSON values.


def _validate_input_content(content: Any) -> None:
    if isinstance(content, str):
        if not content or len(content.encode("utf-8")) > _MAX_INPUT_TEXT_BYTES:
            raise _error(
                "The OpenCode 1.19.3 input content has an invalid captured value",
                "opencode_1193_input_item",
            )
        return
    if isinstance(content, list) and 1 <= len(content) <= _MAX_INPUT_PARTS:
        for part in content:
            if (
                not isinstance(part, Mapping)
                or set(part) != {"type", "text"}
                or part["type"] != "input_text"
            ):
                raise _error(
                    "The OpenCode 1.19.3 input part has an invalid captured value",
                    "opencode_1193_input_item",
                )
            text = part["text"]
            if not isinstance(text, str) or not text or len(text.encode("utf-8")) > _MAX_INPUT_TEXT_BYTES:
                raise _error(
                    "The OpenCode 1.19.3 input part has an invalid captured value",
                    "opencode_1193_input_item",
                )
        return
    raise _error(
        "The OpenCode 1.19.3 input content has an invalid captured value",
        "opencode_1193_input_item",
    )


def _validate_tool_call_id(call_id: Any) -> None:
    profile_data = OPENCODE_1193_RESPONSES_PROFILE_DATA
    if not isinstance(call_id, str):
        raise _error(
            "The OpenCode 1.19.3 tool call id has an invalid captured value",
            "opencode_1193_input_item",
        )
    if not profile_data.tool_call_id_min_length <= len(call_id) <= profile_data.tool_call_id_max_length:
        raise _error(
            "The OpenCode 1.19.3 tool call id has an invalid captured value",
            "opencode_1193_input_item",
        )
    if _TOOL_CALL_ID_PATTERN.fullmatch(call_id) is None:
        raise _error(
            "The OpenCode 1.19.3 tool call id has an invalid captured value",
            "opencode_1193_input_item",
        )


def _validate_input_item(item: Any) -> None:
    if not isinstance(item, Mapping):
        raise _error(
            "The OpenCode 1.19.3 input item is not a mapping",
            "opencode_1193_input_item",
        )
    keys = set(item)
    if keys == {"role", "content"}:
        role = item["role"]
        if not isinstance(role, str) or role not in _ALLOWED_INPUT_ROLES:
            raise _error(
                "The OpenCode 1.19.3 input item has an invalid captured value",
                "opencode_1193_input_item",
            )
        _validate_input_content(item["content"])
        return
    if keys == {"type", "name", "arguments", "call_id"}:
        if item["type"] != "function_call":
            raise _error(
                "The OpenCode 1.19.3 input item has an invalid captured value",
                "opencode_1193_input_item",
            )
        name = item["name"]
        if (
            not isinstance(name, str)
            or not 1 <= len(name) <= 128
            or _TOOL_NAME_PATTERN.fullmatch(name) is None
        ):
            raise _error(
                "The OpenCode 1.19.3 input item has an invalid captured value",
                "opencode_1193_input_item",
            )
        arguments = item["arguments"]
        if not isinstance(arguments, str) or len(
            arguments.encode("utf-8")
        ) > OPENCODE_1193_RESPONSES_PROFILE_DATA.tool_call_arguments_max_bytes:
            raise _error(
                "The OpenCode 1.19.3 input item has an invalid captured value",
                "opencode_1193_input_item",
            )
        _validate_tool_call_id(item["call_id"])
        return
    if keys == {"type", "call_id", "output"}:
        if item["type"] != "function_call_output":
            raise _error(
                "The OpenCode 1.19.3 input item has an invalid captured value",
                "opencode_1193_input_item",
            )
        _validate_tool_call_id(item["call_id"])
        output = item["output"]
        if not isinstance(output, str) or len(output.encode("utf-8")) > _MAX_INPUT_TEXT_BYTES:
            raise _error(
                "The OpenCode 1.19.3 input item has an invalid captured value",
                "opencode_1193_input_item",
            )
        return
    if keys == {"type", "summary", "encrypted_content"}:
        # Native-only ID-less captured form (observed OpenCode 1.19.3
        # turn-N input); the core replay policy owns ciphertext reference
        # validation. Exact-key check denies present id/status/extras.
        if item["type"] != "reasoning":
            raise _error(
                "The OpenCode 1.19.3 input item has an invalid captured value",
                "opencode_1193_input_item",
            )
        summary = item["summary"]
        if not isinstance(summary, list) or len(summary) > _MAX_INPUT_PARTS:
            raise _error(
                "The OpenCode 1.19.3 input item has an invalid captured value",
                "opencode_1193_input_item",
            )
        total_bytes = 0
        for part in summary:
            if not isinstance(part, Mapping) or set(part) != {"type", "text"}:
                raise _error(
                    "The OpenCode 1.19.3 input item has an invalid captured value",
                    "opencode_1193_input_item",
                )
            if part["type"] != "summary_text" or not isinstance(part["text"], str):
                raise _error(
                    "The OpenCode 1.19.3 input item has an invalid captured value",
                    "opencode_1193_input_item",
                )
            total_bytes += len(part["text"].encode("utf-8"))
        if total_bytes > _MAX_INPUT_TEXT_BYTES:
            raise _error(
                "The OpenCode 1.19.3 input item has an invalid captured value",
                "opencode_1193_input_item",
            )
        encrypted_content = item["encrypted_content"]
        if (
            not isinstance(encrypted_content, str)
            or not encrypted_content
            or len(encrypted_content.encode("utf-8")) > _MAX_INPUT_TEXT_BYTES
        ):
            raise _error(
                "The OpenCode 1.19.3 input item has an invalid captured value",
                "opencode_1193_input_item",
            )
        return
    raise _error(
        "The OpenCode 1.19.3 input item has an invalid captured value",
        "opencode_1193_input_item",
    )


def _validate_tool_declaration(tool: Mapping[str, Any], seen_names: set[str]) -> None:
    profile_data = OPENCODE_1193_RESPONSES_PROFILE_DATA
    if (
        not isinstance(tool, Mapping)
        or set(tool) != {"type", "name", "description", "parameters", "strict"}
    ):
        raise _error(
            "The OpenCode 1.19.3 tool declaration has an invalid shape",
            "opencode_1193_tool_declaration",
        )
    if tool["type"] != "function" or tool["strict"] is not True:
        raise _error(
            "The OpenCode 1.19.3 tool declaration has an invalid shape",
            "opencode_1193_tool_declaration",
        )
    name = tool["name"]
    if not isinstance(name, str) or name not in profile_data.tool_names or name in seen_names:
        raise _error(
            "The OpenCode 1.19.3 tool declaration has an invalid name",
            "opencode_1193_tool_declaration",
        )
    seen_names.add(name)
    description = tool["description"]
    if not isinstance(description, str) or len(
        description.encode("utf-8")
    ) > profile_data.max_description_bytes:
        raise _error(
            "The OpenCode 1.19.3 tool declaration has an invalid description",
            "opencode_1193_tool_declaration",
        )
    parameters = tool["parameters"]
    if not isinstance(parameters, Mapping):
        raise _error(
            "The OpenCode 1.19.3 tool declaration has invalid parameters",
            "opencode_1193_tool_declaration",
        )
    _validate_declaration_node(parameters, depth=0)
    try:
        serialized = json.dumps(
            dict(tool), sort_keys=True, separators=(",", ":"), ensure_ascii=True
        )
    except (TypeError, ValueError):
        raise _error(
            "The OpenCode 1.19.3 tool declaration is not strict JSON",
            "opencode_1193_tool_declaration",
        ) from None
    if len(serialized.encode("utf-8")) > profile_data.max_declaration_bytes:
        raise _error(
            "The OpenCode 1.19.3 tool declaration exceeds the byte limit",
            "opencode_1193_tool_declaration",
        )


class Opencode1193ResponsesClientModule:
    """Validate only the captured flat dialect and return non-authoritative facts."""

    module_id = OPENCODE_1193_RESPONSES_CLIENT_MODULE_ID
    module_version = OPENCODE_1193_RESPONSES_CLIENT_MODULE_VERSION
    fixture_sha256 = OPENCODE_1193_RESPONSES_PROFILE_FIXTURE_SHA256
    policy_spec = OPENCODE_1193_RESPONSES_POLICY_SPEC

    def normalize(
        self,
        endpoint: str,
        body: Mapping[str, object],
    ) -> CanonicalClientRequest:
        if endpoint != "/v1/responses":
            raise _error("The OpenCode 1.19.3 client module supports Responses create only")
        if not isinstance(body, Mapping):
            raise _error("The OpenCode 1.19.3 request body is not a mapping")
        if set(body) != _ALLOWED_FIELDS:
            raise _error(
                "The OpenCode 1.19.3 request contains unsupported fields",
                "opencode_1193_fields",
            )
        if body["stream"] is not True:
            raise _error(
                "The OpenCode 1.19.3 stream field has an invalid captured value",
                "opencode_1193_field_shape",
            )
        if body["store"] is not False:
            raise _error(
                "The OpenCode 1.19.3 store field has an invalid captured value",
                "opencode_1193_field_shape",
            )
        if body["tool_choice"] != "auto":
            raise _error(
                "The OpenCode 1.19.3 tool_choice field has an invalid captured value",
                "opencode_1193_field_shape",
            )
        include = body["include"]
        if (
            not isinstance(include, list)
            or not all(isinstance(value, str) for value in include)
            or not 1 <= len(include) <= 4
            or len(set(include)) != len(include)
            or not set(include) <= _ALLOWED_INCLUDE_VALUES
        ):
            raise _error(
                "The OpenCode 1.19.3 include field has an invalid captured value",
                "opencode_1193_field_shape",
            )
        reasoning = body["reasoning"]
        if (
            not isinstance(reasoning, Mapping)
            or set(reasoning) != {"effort"}
            or not isinstance(reasoning["effort"], str)
            or reasoning["effort"] not in OPENCODE_1193_RESPONSES_PROFILE_DATA.reasoning_efforts
        ):
            raise _error(
                "The OpenCode 1.19.3 reasoning field has an invalid captured value",
                "opencode_1193_field_shape",
            )
        model = body["model"]
        if not isinstance(model, str) or not model or len(model.encode("utf-8")) > _MAX_MODEL_BYTES:
            raise _error(
                "The OpenCode 1.19.3 model field has an invalid captured value",
                "opencode_1193_field_shape",
            )
        max_output_tokens = body["max_output_tokens"]
        if (
            isinstance(max_output_tokens, bool)
            or not isinstance(max_output_tokens, int)
            or not 1 <= max_output_tokens <= _MAX_MAX_OUTPUT_TOKENS
        ):
            raise _error(
                "The OpenCode 1.19.3 max_output_tokens field has an invalid captured value",
                "opencode_1193_field_shape",
            )
        input_items = body["input"]
        if not isinstance(input_items, list) or not 1 <= len(input_items) <= _MAX_INPUT_ITEMS:
            raise _error(
                "The OpenCode 1.19.3 input field has an invalid captured value",
                "opencode_1193_field_shape",
            )
        for item in input_items:
            _validate_input_item(item)
        tools = body["tools"]
        if (
            not isinstance(tools, list)
            or not 1 <= len(tools) <= OPENCODE_1193_RESPONSES_PROFILE_DATA.max_tool_declarations
        ):
            raise _error(
                "The OpenCode 1.19.3 tools field has an invalid captured value",
                "opencode_1193_field_shape",
            )
        seen_names: set[str] = set()
        for tool in tools:
            _validate_tool_declaration(tool, seen_names)
        return CanonicalClientRequest(
            module_id=self.module_id,
            module_version=self.module_version,
            endpoint=endpoint,
            body=copy.deepcopy(dict(body)),
            capability_intents=(),
            adapter_managed_declaration_candidates=(),
            adapter_managed_declaration_shapes=MappingProxyType({}),
            stream_profile=self.module_id,
            zero_argument_function_names=codex_0149_zero_argument_function_names(body),
            profile_facts=_PROFILE_FACTS,
            identity_hints={},
        )

    def normalize_responses(
        self,
        body: Mapping[str, object],
    ) -> CanonicalClientRequest:
        return self.normalize("/v1/responses", body)

    def stream_profile(self, body: Mapping[str, object]) -> str | None:
        return self.module_id

    def encrypted_reasoning_output_requested(
        self,
        body: Mapping[str, object],
    ) -> bool:
        if not isinstance(body, Mapping):
            return False
        include = body.get("include")
        if not isinstance(include, list):
            return False
        return (
            all(isinstance(value, str) for value in include)
            and "reasoning.encrypted_content" in include
        )


OPENCODE_1193_RESPONSES_CLIENT_MODULE = Opencode1193ResponsesClientModule()
