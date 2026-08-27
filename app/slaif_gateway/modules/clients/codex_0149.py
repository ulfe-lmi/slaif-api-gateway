"""Default-denied Codex CLI 0.149 Responses client dialect."""

from __future__ import annotations

import copy
import re
from collections.abc import Mapping
from types import MappingProxyType

from slaif_gateway.modules.contracts import (
    CanonicalClientRequest,
    ModuleSelectionError,
)

CODEX_0149_CLIENT_MODULE_ID = "codex-0.149-responses-v1"
CODEX_0149_CLIENT_MODULE_VERSION = "2"
CODEX_0149_CLI_VERSION = "0.149.0"
CODEX_0149_FIXTURE_SHA256 = "baba5403949d44900d8bd3cdef3f7c65bf6abd5109b78bda0b67f3f9787118d1"
CODEX_0149_FIXTURE_RELATIVE_PATH = "tests/fixtures/codex/0.149.0/responses-structural-v2.json"
CODEX_0149_PROFILE_ID = "responses-structural-capture-v2"

_PROFILE_FACTS = MappingProxyType(
    {
        "client_module_id": CODEX_0149_CLIENT_MODULE_ID,
        "client_module_version": CODEX_0149_CLIENT_MODULE_VERSION,
        "fixture_sha256": CODEX_0149_FIXTURE_SHA256,
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
    if depth > 8:
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
    if depth > 8:
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
    if depth > 8:
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


def _validate_tool_choice(value: object) -> None:
    if value is None:
        return
    if isinstance(value, str):
        if value in _CANDIDATE_TYPES:
            raise _error(
                "The Codex 0.149 request explicitly requires a search tool",
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
    policy_spec = None

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
        _validate_tool_choice(body.get("tool_choice"))
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
            identity_hints=_transient_identity_hints(body.get("client_metadata")),
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


def _transient_identity_hints(value: object) -> Mapping[str, str]:
    if not isinstance(value, Mapping):
        return {}
    # Values are deliberately transient: this mapping is never placed in a
    # profile, audit record, log, export, provider body, or database row.
    return {
        key: item
        for key, item in value.items()
        if isinstance(key, str) and isinstance(item, str) and key.startswith("x-codex-")
    }
