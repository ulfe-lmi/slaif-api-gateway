"""Default-denied Codex CLI 0.149 Responses client dialect."""

from __future__ import annotations

import copy
import re
import uuid
from collections.abc import Mapping
from types import MappingProxyType

from slaif_gateway.modules.contracts import (
    CanonicalClientRequest,
    ModuleSelectionError,
    ResponsesClientPolicySpec,
)

CODEX_0149_CLIENT_MODULE_ID = "codex-0.149-responses-v1"
CODEX_0149_CLIENT_MODULE_VERSION = "3"
CODEX_0149_REASONING_DIALECT_VERSION = "4"
CODEX_0149_CLI_VERSION = "0.149.0"
CODEX_0149_FIXTURE_SHA256 = "ca1e03a35de1eaeceb894cec9895af0c154e0d2fa0aa8da87f98716e1567f9ec"
CODEX_0149_FIXTURE_RELATIVE_PATH = "tests/fixtures/codex/0.149.0/responses-session-relationship-v3.json"
CODEX_0149_PROFILE_ID = "responses-session-relationship-v3"
CODEX_0149_SOURCE_CONTRACT_TAG = "rust-v0.149.0"
CODEX_0149_SOURCE_CONTRACT_COMMIT = "758ef40f50c1a458425c7cfbf1eb12cbc07af0b0"
CODEX_0149_SOURCE_CONTRACT_FIXTURE_SHA256 = "d24178dc3467dfaf276b015dcf8298fcc1ddc35bc6c6dcd615f101c3e1cd76df"
CODEX_0149_SOURCE_CONTRACT_FIXTURE_RELATIVE_PATH = (
    "tests/fixtures/codex/0.149.0/responses-reasoning-dialect-v1.json"
)

_PROFILE_FACTS = MappingProxyType(
    {
        "client_module_id": CODEX_0149_CLIENT_MODULE_ID,
        "client_module_version": CODEX_0149_CLIENT_MODULE_VERSION,
        "fixture_sha256": CODEX_0149_FIXTURE_SHA256,
        "source_contract_tag": CODEX_0149_SOURCE_CONTRACT_TAG,
        "source_contract_commit": CODEX_0149_SOURCE_CONTRACT_COMMIT,
        "source_contract_fixture_sha256": CODEX_0149_SOURCE_CONTRACT_FIXTURE_SHA256,
        "reasoning_dialect_version": CODEX_0149_REASONING_DIALECT_VERSION,
    }
)
_SAFE_TOKEN = re.compile(r"^[a-z][a-z0-9_.-]{0,63}$")
_SUPPORTED_FIELDS = frozenset(
    {
        "model",
        "input",
        "instructions",
        "max_output_tokens",
        "max_tool_calls",
        "temperature",
        "top_p",
        "metadata",
        "stream",
        "store",
        "text",
        "service_tier",
        "tools",
        "tool_choice",
        "previous_response_id",
        "conversation",
        "client_metadata",
        "include",
        "parallel_tool_calls",
        "prompt_cache_key",
        "reasoning",
    }
)
_FUNCTION_FIELDS = frozenset({"type", "name", "description", "parameters", "strict"})
_CUSTOM_FIELDS = frozenset({"type", "name", "description", "format"})
_NAMESPACE_FIELDS = frozenset({"type", "name", "description", "tools"})
_TOOL_SEARCH_FIELDS = frozenset({"type", "description", "execution", "parameters"})
_WEB_SEARCH_FIELDS = frozenset({"type", "external_web_access", "search_content_types"})
_TOOL_CHOICE_FIELDS = frozenset({"type", "name"})
CODEX_0149_ADAPTER_MANAGED_CANDIDATE_TYPES = frozenset({"tool_search", "web_search"})
CODEX_0149_ADAPTER_MANAGED_CANDIDATE_SHAPES = MappingProxyType(
    {
        "tool_search": _TOOL_SEARCH_FIELDS,
        "web_search": _WEB_SEARCH_FIELDS,
    }
)
_CANDIDATE_TYPES = CODEX_0149_ADAPTER_MANAGED_CANDIDATE_TYPES
_ALLOWED_TOOL_TYPES = frozenset(
    {"function", "custom", "namespace", "tool_search", "web_search"}
)
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
    {"authorization", "api_key", "apikey", "headers", "server_url", "connector", "mcp_server"}
)
_ALLOWED_TOOL_CHOICES = frozenset({"auto", "none", "required"})
_MAX_DECLARATION_DEPTH = 32

# This is deliberately version-owned.  The values are the bounded envelope
# classes observed by the 0.149 capture plus the existing neutral Codex
# request-policy limits; no other Codex module supplies this contract.
_CODEX_0149_INCLUDE_VALUE = "reasoning.encrypted_content"
_CODEX_0149_REASONING_EFFORTS = frozenset(
    {"none", "minimal", "low", "medium", "high", "xhigh", "max", "ultra"}
)
_CODEX_0149_CLIENT_METADATA_KEYS = frozenset(
    {
        "x-codex-installation-id",
        "session_id",
        "root_turn_id",
        "thread_id",
        "turn_id",
        "x-codex-window-id",
        "x-codex-turn-metadata",
    }
)
_CODEX_0149_MESSAGE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_CODEX_0149_TOOL_CALL_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$")
CODEX_0149_DECLARED_TOOL_NAMESPACE = "functions"


def _codex_0149_taxonomy_for(
    value: object,
) -> tuple[tuple[str, tuple[tuple[str, str], ...]], ...] | None:
    _ = value
    return None


def codex_0149_declared_tool_taxonomy(
    body: Mapping[str, object],
) -> frozenset[tuple[str, str, str]]:
    """Return the bounded taxonomy of observed top-level local tools."""

    tools = body.get("tools")
    if not isinstance(tools, list):
        return frozenset()
    declarations: set[tuple[str, str, str]] = set()
    for tool in tools:
        if not isinstance(tool, Mapping):
            continue
        tool_type = tool.get("type")
        if tool_type not in {"function", "custom"}:
            continue
        name = tool.get("name")
        if not isinstance(name, str) or not _SAFE_TOKEN.fullmatch(name):
            raise _error(
                "The Codex 0.149 local tool declaration has no bounded name",
                "codex_0149_tool_declaration",
            )
        declaration = (CODEX_0149_DECLARED_TOOL_NAMESPACE, name, str(tool_type))
        if declaration in declarations:
            raise _error(
                "The Codex 0.149 local tool declaration is duplicated",
                "codex_0149_tool_declaration",
            )
        declarations.add(declaration)
    if len(declarations) > 32:
        raise _error(
            "The Codex 0.149 local tool declaration set is too large",
            "codex_0149_tool_declaration",
        )
    return frozenset(declarations)


def codex_0149_streaming_tool_events_requested(body: Mapping[str, object]) -> bool:
    """Require the exact 0.149 local declarations on a streaming request."""

    return body.get("stream") is True and bool(codex_0149_declared_tool_taxonomy(body))


CODEX_0149_POLICY_SPEC = ResponsesClientPolicySpec(
    compact_fields=frozenset(
        {"model", "input", "instructions", "tools", "parallel_tool_calls", "reasoning", "prompt_cache_key", "text"}
    ),
    function_call_output_fields=frozenset({"type", "id", "call_id", "output"}),
    custom_tool_call_output_fields=frozenset({"type", "id", "call_id", "output"}),
    function_call_fields=frozenset(
        {"type", "id", "status", "namespace", "name", "arguments", "call_id"}
    ),
    custom_tool_call_fields=frozenset(
        {"type", "id", "status", "namespace", "name", "input", "call_id"}
    ),
    tool_output_content_fields=frozenset({"type", "text"}),
    reasoning_replay_fields=frozenset({"type", "id", "summary", "encrypted_content", "content"}),
    compaction_replay_fields=frozenset({"type", "id", "encrypted_content"}),
    reasoning_summary_fields=frozenset({"type", "text"}),
    additional_tools_fields=frozenset({"type", "role", "tools"}),
    namespace_fields=_NAMESPACE_FIELDS,
    include_value=_CODEX_0149_INCLUDE_VALUE,
    reasoning_efforts=_CODEX_0149_REASONING_EFFORTS,
    reasoning_context="all_turns",
    text_verbosities=frozenset({"low", "medium", "high"}),
    message_id_pattern=_CODEX_0149_MESSAGE_ID_PATTERN,
    tool_call_id_pattern=_CODEX_0149_TOOL_CALL_ID_PATTERN,
    tool_call_statuses=frozenset({"completed"}),
    client_metadata_keys=_CODEX_0149_CLIENT_METADATA_KEYS,
    max_include_items=8,
    max_prompt_cache_key_bytes=256,
    max_reasoning_bytes=256,
    max_client_metadata_keys=len(_CODEX_0149_CLIENT_METADATA_KEYS),
    max_client_metadata_key_bytes=64,
    max_client_metadata_value_bytes=4096,
    max_client_metadata_bytes=8192,
    max_client_tool_schema_depth=16,
    max_client_tool_schema_properties=256,
    max_client_tool_description_bytes=20_000,
    max_client_tool_total_description_bytes=32_768,
    max_client_tool_declaration_bytes=589_824,
    request_user_input_allowed_authority_key_paths=frozenset(
        {("parameters", "properties", "questions", "items", "properties", "header")}
    ),
    exec_command_allowed_authority_key_paths=frozenset(
        {("parameters", "properties", "shell")}
    ),
    max_encrypted_reasoning_item_bytes=262_144,
    max_encrypted_reasoning_request_bytes=1_048_576,
    max_reasoning_summary_bytes=65_536,
    max_reasoning_summary_parts=64,
    max_compaction_item_bytes=1_048_576,
    internal_chat_message_metadata_field="internal_chat_message_metadata_passthrough",
    max_internal_chat_message_metadata_bytes=32_768,
    internal_chat_message_metadata_item_types=frozenset(
        {None, "message", "reasoning", "function_call", "function_call_output", "custom_tool_call", "custom_tool_call_output", "compaction"}
    ),
    taxonomy_for=_codex_0149_taxonomy_for,
    taxonomy_0148=(),
    taxonomy_id_0148="codex_0_149",
    function_call_item_id_optional=True,
    custom_tool_call_item_id_optional=True,
    allow_idless_tool_call_replay=True,
    reasoning_visible_id_optional=True,
    reasoning_visible_content_fields=frozenset({"type", "text"}),
    reasoning_visible_content_types=frozenset({"reasoning_text", "text"}),
    max_reasoning_visible_parts=64,
    max_reasoning_visible_part_bytes=8_192,
    max_reasoning_visible_bytes=65_536,
    allow_idless_encrypted_reasoning=False,
)
_CAPTURED_FIELD_VALUE_CLASSES = MappingProxyType(
    {
        "client_metadata": "object",
        "include": "array",
        "input": "array",
        "instructions": "string",
        "model": "string",
        "parallel_tool_calls": "boolean",
        "prompt_cache_key": "string",
        "reasoning": "object",
        "store": "boolean",
        "stream": "boolean",
        "text": "object",
        "tool_choice": "string",
        "tools": "array",
    }
)


def _error(message: str, code: str = "codex_0149_request_invalid") -> ModuleSelectionError:
    return ModuleSelectionError(message, error_code=code)


def _safe_shape_fields(value: Mapping[str, object], allowed: frozenset[str], *, label: str) -> None:
    unknown = set(value) - allowed
    if any(isinstance(key, str) and key.lower() in _FORBIDDEN_AUTHORITY_KEYS for key in unknown):
        raise _error(
            f"The Codex 0.149 {label} shape contains an authority field",
            "codex_0149_authority_shape",
        )
    if unknown:
        raise _error(f"The Codex 0.149 {label} shape contains an unknown field")


def _walk_forbidden_keys(value: object, *, depth: int = 0) -> None:
    if depth > _MAX_DECLARATION_DEPTH:
        raise _error("The Codex 0.149 declaration is too deeply nested")
    if isinstance(value, Mapping):
        for key, child in value.items():
            if isinstance(key, str) and key.lower() in _FORBIDDEN_AUTHORITY_KEYS:
                raise _error(
                    "The Codex 0.149 declaration contains an authority field",
                    "codex_0149_authority_shape",
                )
            if depth > 0 and key == "type" and isinstance(child, str) and child in _FORBIDDEN_AUTHORITY_TYPES:
                raise _error(
                    "The Codex 0.149 declaration contains a nested authority shape",
                    "codex_0149_authority_shape",
                )
            _walk_forbidden_keys(child, depth=depth + 1)
    elif isinstance(value, list):
        for child in value:
            _walk_forbidden_keys(child, depth=depth + 1)


def _walk_unsafe_candidate_values(value: object, *, depth: int = 0) -> None:
    if depth > _MAX_DECLARATION_DEPTH:
        raise _error("The Codex 0.149 declaration is too deeply nested")
    if isinstance(value, Mapping):
        for child in value.values():
            _walk_unsafe_candidate_values(child, depth=depth + 1)
    elif isinstance(value, list):
        for child in value:
            _walk_unsafe_candidate_values(child, depth=depth + 1)
    elif isinstance(value, str):
        lowered = value.lower()
        if "://" in value or any(
            marker in lowered
            for marker in ("bearer", "api_key", "apikey", "authorization", "secret", "password", "token")
        ):
            raise _error(
                "The Codex 0.149 candidate contains an authority value",
                "codex_0149_authority_shape",
            )


def _reject_nested_candidate_types(value: object, *, depth: int = 0) -> None:
    if depth > _MAX_DECLARATION_DEPTH:
        raise _error("The Codex 0.149 declaration is too deeply nested")
    if isinstance(value, Mapping):
        for key, child in value.items():
            if (
                depth > 0
                and key == "type"
                and isinstance(child, str)
                and child in _CANDIDATE_TYPES
            ):
                raise _error(
                    "The Codex 0.149 declaration contains a nested search declaration",
                    "codex_0149_authority_shape",
                )
            _reject_nested_candidate_types(child, depth=depth + 1)
    elif isinstance(value, list):
        for child in value:
            _reject_nested_candidate_types(child, depth=depth + 1)


def _validate_tool(value: object) -> str | None:
    if not isinstance(value, Mapping):
        raise _error("The Codex 0.149 tool declaration is not an object")
    tool_type = value.get("type")
    if not isinstance(tool_type, str) or not _SAFE_TOKEN.fullmatch(tool_type):
        raise _error("The Codex 0.149 tool declaration type is invalid")
    if tool_type in _FORBIDDEN_AUTHORITY_TYPES:
        raise _error(
            "The Codex 0.149 request contains an unsupported authority shape",
            "codex_0149_authority_shape",
        )
    if tool_type not in _ALLOWED_TOOL_TYPES:
        raise _error("The Codex 0.149 tool declaration type is unknown")
    allowed = {
        "function": _FUNCTION_FIELDS,
        "custom": _CUSTOM_FIELDS,
        "namespace": _NAMESPACE_FIELDS,
        "tool_search": _TOOL_SEARCH_FIELDS,
        "web_search": _WEB_SEARCH_FIELDS,
    }[tool_type]
    _safe_shape_fields(value, allowed, label="tool")
    if tool_type in _CANDIDATE_TYPES:
        if set(value) != allowed:
            raise _error(
                "The Codex 0.149 adapter-managed tool shape is not the captured shape",
                "codex_0149_candidate_shape",
            )
        if tool_type == "tool_search":
            if (
                not isinstance(value.get("description"), str)
                or not isinstance(value.get("execution"), str)
                or not _SAFE_TOKEN.fullmatch(value["execution"])
                or not isinstance(value.get("parameters"), Mapping)
            ):
                raise _error(
                    "The Codex 0.149 tool_search candidate has invalid field types",
                    "codex_0149_candidate_shape",
                )
        else:
            search_content_types = value.get("search_content_types")
            if (
                not isinstance(value.get("external_web_access"), bool)
                or not isinstance(search_content_types, list)
                or not search_content_types
                or len(search_content_types) > 8
                or not all(
                    isinstance(item, str) and _SAFE_TOKEN.fullmatch(item)
                    for item in search_content_types
                )
            ):
                raise _error(
                    "The Codex 0.149 web_search candidate has invalid field types",
                    "codex_0149_candidate_shape",
                )
    _walk_forbidden_keys(value)
    if tool_type in _CANDIDATE_TYPES:
        _walk_unsafe_candidate_values(value)
    if tool_type == "namespace":
        nested = value.get("tools")
        if not isinstance(nested, list) or not nested or len(nested) > 32:
            raise _error("The Codex 0.149 namespace declaration has invalid tools")
        for child in nested:
            child_type = _validate_tool(child)
            if child_type in _CANDIDATE_TYPES:
                raise _error(
                    "The Codex 0.149 namespace contains a search authority",
                    "codex_0149_authority_shape",
                )
    return tool_type if tool_type in _CANDIDATE_TYPES else None


def _validate_tool_choice(value: object, *, candidates: list[str], local_tools: bool) -> None:
    if value is None:
        return
    if isinstance(value, str):
        if value in _CANDIDATE_TYPES:
            raise _error(
                "The Codex 0.149 request explicitly requires a search tool",
                "codex_0149_authority_shape",
            )
        if value == "required" and candidates and not local_tools:
            raise _error(
                "The Codex 0.149 request requires an adapter-managed search tool",
                "codex_0149_authority_shape",
            )
        if value not in _ALLOWED_TOOL_CHOICES:
            raise _error("The Codex 0.149 tool choice is unsupported")
        return
    if isinstance(value, Mapping):
        _safe_shape_fields(value, _TOOL_CHOICE_FIELDS, label="tool choice")
        choice_type = value.get("type")
        if choice_type in _CANDIDATE_TYPES:
            raise _error(
                "The Codex 0.149 request explicitly requires a search tool",
                "codex_0149_authority_shape",
            )
        if choice_type not in {"function", "custom"}:
            raise _error("The Codex 0.149 tool choice is unsupported")
        return
    raise _error("The Codex 0.149 tool choice is invalid")


def _value_class(value: object) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, Mapping):
        return "object"
    return "other"


class Codex0149ResponsesClientModule:
    """Validate only the captured dialect and return non-authoritative facts."""

    module_id = CODEX_0149_CLIENT_MODULE_ID
    module_version = CODEX_0149_CLIENT_MODULE_VERSION
    fixture_sha256 = CODEX_0149_FIXTURE_SHA256
    policy_spec = CODEX_0149_POLICY_SPEC

    def normalize(
        self,
        endpoint: str,
        body: Mapping[str, object],
    ) -> CanonicalClientRequest:
        if endpoint != "/v1/responses":
            raise _error("The Codex 0.149 client module supports Responses create only")
        if not isinstance(body, Mapping):
            raise _error("The Codex 0.149 request body is not a mapping")
        unknown = set(body) - _SUPPORTED_FIELDS
        if unknown:
            raise _error("The Codex 0.149 request contains an unknown field")
        for field, expected_class in _CAPTURED_FIELD_VALUE_CLASSES.items():
            if field not in body:
                continue
            captured_class_matches = _value_class(body[field]) == expected_class
            # The established Responses tool-choice validator also accepts a
            # bounded structured local choice; the captured neutral value is
            # still the only search choice accepted by this module.
            if field == "tool_choice" and isinstance(body[field], Mapping):
                captured_class_matches = True
            if not captured_class_matches:
                raise _error(
                    f"The Codex 0.149 {field} field has an invalid captured value class",
                    "codex_0149_field_shape",
                )
        tools = body.get("tools", [])
        if not isinstance(tools, list) or len(tools) > 64:
            raise _error("The Codex 0.149 tools field is invalid")
        candidates: list[str] = []
        for tool in tools:
            candidate = _validate_tool(tool)
            if candidate is not None and candidate not in candidates:
                candidates.append(candidate)
        _validate_tool_choice(
            body.get("tool_choice"),
            candidates=candidates,
            local_tools=any(
                isinstance(tool, Mapping) and tool.get("type") in {"function", "custom", "namespace"}
                for tool in tools
            ),
        )
        _walk_forbidden_keys(body.get("tools", []))
        for tool in tools:
            _reject_nested_candidate_types(tool)
        return CanonicalClientRequest(
            module_id=self.module_id,
            module_version=self.module_version,
            endpoint=endpoint,
            body=copy.deepcopy(dict(body)),
            capability_intents=("adapter_managed_codex_search",) if candidates else (),
            adapter_managed_declaration_candidates=tuple(candidates),
            adapter_managed_declaration_shapes=CODEX_0149_ADAPTER_MANAGED_CANDIDATE_SHAPES,
            stream_profile=self.module_id,
            profile_facts=_PROFILE_FACTS,
            identity_hints=_transient_identity_hints(
                body.get("client_metadata"),
                metadata_present="client_metadata" in body,
            ),
        )

    def normalize_responses(
        self,
        body: Mapping[str, object],
    ) -> CanonicalClientRequest:
        return self.normalize("/v1/responses", body)

    def stream_profile(self, body: Mapping[str, object]) -> str:
        _ = body
        return self.module_id

    def encrypted_reasoning_output_requested(self, body: Mapping[str, object]) -> bool:
        _ = body
        return False


def _transient_identity_hints(
    value: object,
    *,
    metadata_present: bool = True,
) -> Mapping[str, str]:
    if not metadata_present:
        return {}
    if not isinstance(value, Mapping):
        raise _error("The Codex 0.149 client metadata is invalid", "codex_0149_identity_shape")
    aliases = (value.get("session_id"), value.get("thread_id"))
    if not all(isinstance(item, str) for item in aliases):
        raise _error(
            "The Codex 0.149 session aliases are unavailable",
            "codex_0149_identity_shape",
        )
    canonical: list[str] = []
    for item in aliases:
        if len(item.encode("utf-8")) != 36:
            raise _error(
                "The Codex 0.149 session alias is not canonical",
                "codex_0149_identity_shape",
            )
        try:
            parsed = uuid.UUID(item)
        except (ValueError, AttributeError):
            raise _error(
                "The Codex 0.149 session alias is not canonical",
                "codex_0149_identity_shape",
            ) from None
        if str(parsed) != item:
            raise _error(
                "The Codex 0.149 session alias is not canonical",
                "codex_0149_identity_shape",
            )
        canonical.append(item)
    if canonical[0] != canonical[1]:
        raise _error(
            "The Codex 0.149 session aliases are ambiguous",
            "codex_0149_identity_shape",
        )
    # This one canonical UUID is transient and never reaches a provider,
    # persistence, logging, audit, export, metric label, or wire header.
    return {"session_id": canonical[0]}
