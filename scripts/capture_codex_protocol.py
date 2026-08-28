#!/usr/bin/env python3
"""Capture a sanitized Codex Responses request against an isolated loopback server."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

SCHEMA_VERSION = 1
PINNED_CLI_VERSION = "0.147.0"
PINNED_RAW_VERSION = "codex-cli 0.147.0"
PINNED_SOURCE_TAG = "rust-v0.147.0"
PINNED_MODEL = "gpt-5.6-sol"
PINNED_PROFILE = "api-key-responses-baseline"
CAPTURE_PROVIDER_ID = "slaif_capture"
CAPTURE_API_KEY_ENV = "SLAIF_CODEX_CAPTURE_API_KEY"
PROMPT_CANARY = "SLAIF_CAPTURE_PROMPT_CANARY_DO_NOT_PERSIST"
TOKEN_CANARY = "SLAIF_CAPTURE_TOKEN_CANARY_DO_NOT_PERSIST"
FIXTURE_RELATIVE_PATH = Path(
    "tests/fixtures/codex/0.147.0/gpt-5.6-sol-api-key-responses.json"
)
APPROVED_CANONICAL_FIXTURE_SHA256 = (
    "436ea530b9f984807dfc73ccce0b5233d0a3047ceb10ef942fbc8d12cac47432"
)
PINNED_0149_CLI_VERSION = "0.149.0"
PINNED_0149_RAW_VERSION = "codex-cli 0.149.0"
PINNED_0149_MODEL = "qwen3.8-27b"
PINNED_0149_PROFILE = "responses-structural-capture-v2"
APPROVED_0149_CANONICAL_FIXTURE_SHA256 = (
    "baba5403949d44900d8bd3cdef3f7c65bf6abd5109b78bda0b67f3f9787118d1"
)
FIXTURE_0149_RELATIVE_PATH = Path(
    "tests/fixtures/codex/0.149.0/responses-structural-v2.json"
)
FIXTURE_INTEGRITY_ERROR = "Fixture canonical document integrity check failed."
REPO_ROOT = Path(__file__).resolve().parents[1]
MAX_HEADER_BYTES = 64 * 1024
MAX_BODY_BYTES = 4 * 1024 * 1024
MAX_CATALOG_BYTES = 4 * 1024 * 1024
VERSION_TIMEOUT_SECONDS = 5
CODEX_TIMEOUT_SECONDS = 20
SERVER_TIMEOUT_SECONDS = 15
MOCK_RESPONSE_ID = "resp_slaif_codex_capture"
MOCK_EVENTS = (
    {
        "type": "response.created",
        "response": {"id": MOCK_RESPONSE_ID},
    },
    {
        "type": "response.completed",
        "response": {
            "id": MOCK_RESPONSE_ID,
            "usage": {
                "input_tokens": 0,
                "input_tokens_details": None,
                "output_tokens": 0,
                "output_tokens_details": None,
                "total_tokens": 0,
            },
        },
    },
)

# Immutable 004-baseline classifier vocabulary. This evidence tool must keep
# reproducing the checked-in pre-005 compatibility diff even as runtime policy
# gains separately reviewed fields.
_BASELINE_004_SUPPORTED_FIELDS = frozenset(
    {
        "model",
        "input",
        "instructions",
        "max_output_tokens",
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
    }
)
_BASELINE_004_SUPPORTED_INPUT_MESSAGE_FIELDS = frozenset({"type", "role", "content"})
_BASELINE_004_SUPPORTED_INPUT_TEXT_PART_FIELDS = frozenset({"type", "text"})
_BASELINE_004_SUPPORTED_FUNCTION_TOOL_FIELDS = frozenset(
    {"type", "name", "description", "parameters", "strict"}
)
_BASELINE_004_SUPPORTED_CUSTOM_TOOL_FIELDS = frozenset(
    {"type", "name", "description", "format"}
)
_BASELINE_004_HOSTED_TOOL_TYPES = frozenset(
    {
        "web_search",
        "web_search_preview",
        "web_search_preview_2025_03_11",
        "web_search_2025_08_26",
        "file_search",
        "code_interpreter",
        "computer",
        "computer_use",
        "computer_use_preview",
        "image_generation",
        "tool_search",
        "mcp",
        "shell",
        "local_shell",
        "apply_patch",
        "namespace",
    }
)
_BASELINE_004_ALLOWED_RESPONSES_STREAM_EVENT_TYPES = frozenset(
    {"response.created", "response.in_progress", "response.output_text.delta"}
)


def _baseline_004_unsupported_code_for_field(field_name: str) -> str:
    if field_name == "parallel_tool_calls":
        return "responses_tools_not_supported"
    if field_name in {"previous_response_id", "conversation"}:
        return "responses_state_not_supported"
    if field_name == "background":
        return "responses_background_not_supported"
    if field_name in {"modalities", "audio", "include"}:
        return "responses_multimodal_not_supported"
    if field_name in {"prompt", "prompt_cache_key", "prompt_cache_retention"}:
        return "responses_state_not_supported"
    return "responses_field_not_supported"

_VERSION_RE = re.compile(r"codex-cli ([0-9]+\.[0-9]+\.[0-9]+)\n?\Z")
_SAFE_CATALOG_FIELDS = frozenset(
    {
        "apply_patch_tool_type",
        "auto_compact_token_limit",
        "context_window",
        "default_reasoning_level",
        "effective_context_window_percent",
        "include_apps_usage_instructions",
        "include_plugin_usage_instructions",
        "include_skills_usage_instructions",
        "input_modalities",
        "max_context_window",
        "multi_agent_version",
        "shell_type",
        "slug",
        "supported_in_api",
        "supported_reasoning_levels",
        "supports_image_detail_original",
        "supports_parallel_tool_calls",
        "supports_reasoning_summary_parameter",
        "supports_search_tool",
        "support_verbosity",
        "tool_mode",
        "truncation_policy",
        "use_responses_lite",
        "visibility",
    }
)
_FREE_TEXT_CATALOG_FIELDS = frozenset(
    {
        "availability_nux",
        "base_instructions",
        "description",
        "display_name",
        "migration_copy",
        "migration_markdown",
        "model_messages",
        "upgrade",
    }
)
_SAFE_CATALOG_STRING_VALUES = {
    "apply_patch_tool_type": frozenset({"freeform"}),
    "default_reasoning_level": frozenset(
        {"none", "minimal", "low", "medium", "high", "xhigh", "max", "ultra"}
    ),
    "multi_agent_version": frozenset({"v1", "v2"}),
    "shell_type": frozenset(
        {"default", "disabled", "local", "shell_command", "unified_exec"}
    ),
    "tool_mode": frozenset({"code_mode", "code_mode_only", "direct"}),
    "visibility": frozenset({"hide", "list", "none"}),
}
_SAFE_REASONING_LEVELS = _SAFE_CATALOG_STRING_VALUES["default_reasoning_level"]
_SAFE_INPUT_MODALITIES = frozenset({"audio", "image", "text"})
_SECRET_HEADER_FRAGMENTS = (
    "authorization",
    "api-key",
    "api_key",
    "cookie",
    "password",
    "secret",
    "session",
    "token",
)
_SAFE_SCHEMA_FIELD_NAMES = frozenset(
    {
        "additionalProperties",
        "allOf",
        "anyOf",
        "enum",
        "items",
        "maxItems",
        "maxLength",
        "maximum",
        "minItems",
        "minLength",
        "minimum",
        "nullable",
        "oneOf",
        "properties",
        "required",
        "type",
    }
)


class CaptureError(RuntimeError):
    """A safe capture failure whose message contains no captured values."""


@dataclass(frozen=True, slots=True)
class ParsedHttpRequest:
    method: str
    target: str
    version: str
    headers: tuple[tuple[str, str], ...]
    body: bytes


def canonical_json_bytes(value: object) -> bytes:
    """Return the deterministic checked-in fixture encoding."""

    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True) + "\n").encode("utf-8")


def parse_codex_version(raw_output: str) -> str:
    match = _VERSION_RE.fullmatch(raw_output)
    if match is None:
        raise CaptureError("Codex CLI returned an unrecognized version string.")
    return match.group(1)


def validate_target(*, expected_version: str, model: str, profile: str) -> None:
    if expected_version != PINNED_CLI_VERSION:
        raise CaptureError("Requested Codex CLI version is not the pinned capture version.")
    if model != PINNED_MODEL:
        raise CaptureError("Requested model is not the pinned capture model.")
    if profile != PINNED_PROFILE:
        raise CaptureError("Requested profile is not the pinned capture profile.")


def verify_codex_version(
    codex_binary: Path,
    expected_version: str,
    *,
    expected_raw_version: str | None = None,
) -> str:
    """Invoke only ``--version`` and enforce the exact pinned CLI family/version."""

    try:
        result = subprocess.run(
            [str(codex_binary), "--version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=VERSION_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CaptureError("Codex CLI version check failed safely.") from exc
    if result.returncode != 0:
        raise CaptureError("Codex CLI version check failed safely.")
    version = parse_codex_version(result.stdout)
    if (
        result.stdout.rstrip("\n") != (expected_raw_version or PINNED_RAW_VERSION)
        or version != expected_version
    ):
        raise CaptureError("Codex CLI version does not match the requested pinned version.")
    return version


def validate_fixture_path(
    path: Path,
    *,
    allowed_root: Path | None = None,
) -> Path:
    """Restrict writes to the exact version/model path beneath a supplied fixture root."""

    root = (allowed_root or (REPO_ROOT / "tests/fixtures/codex")).resolve()
    expected = root / PINNED_CLI_VERSION / FIXTURE_RELATIVE_PATH.name
    resolved = path.resolve()
    if resolved != expected:
        raise CaptureError("Fixture path is outside the pinned versioned fixture location.")
    return resolved


def _header_classification(name: str) -> str:
    if any(fragment in name for fragment in _SECRET_HEADER_FRAGMENTS):
        return "secret_value_redacted"
    if name == "content-type" or name == "accept":
        return "media_type_recorded_separately"
    if name == "content-length":
        return "size_value_omitted"
    if name == "host":
        return "loopback_value_omitted"
    return "value_omitted"


def sanitize_headers(headers: tuple[tuple[str, str], ...]) -> dict[str, object]:
    names = sorted({name.lower() for name, _value in headers})
    values: dict[str, list[str]] = {}
    for name, value in headers:
        values.setdefault(name.lower(), []).append(value)

    content_type_values = values.get("content-type", [])
    content_type = None
    if len(content_type_values) == 1:
        content_type = content_type_values[0].split(";", maxsplit=1)[0].strip().lower()
    content_encoding_present = "content-encoding" in values
    authorization_present = "authorization" in values or "x-api-key" in values
    return {
        "authorization": {
            "present": authorization_present,
            "redacted": authorization_present,
        },
        "content_encoding": {"present": content_encoding_present},
        "content_type": content_type,
        "entries": [
            {"classification": _header_classification(name), "name": name} for name in names
        ],
        "names": names,
    }


def _schema_shape(value: Any) -> dict[str, object]:
    if not isinstance(value, dict):
        return {"kind": _kind(value)}
    result: dict[str, object] = {
        "field_names": sorted(str(key) for key in value if key in _SAFE_SCHEMA_FIELD_NAMES),
        "kind": "object",
    }
    schema_type = value.get("type")
    if isinstance(schema_type, str):
        result["type"] = schema_type
    properties = value.get("properties")
    if isinstance(properties, dict):
        shapes = [_schema_shape(item) for item in properties.values()]
        result["properties"] = sorted(
            shapes,
            key=lambda item: json.dumps(item, sort_keys=True, separators=(",", ":")),
        )
        result["property_count"] = len(properties)
    required = value.get("required")
    if isinstance(required, list):
        result["required_count"] = len(required)
    enum = value.get("enum")
    if isinstance(enum, list):
        result["enum_count"] = len(enum)
    additional = value.get("additionalProperties")
    if isinstance(additional, bool):
        result["additional_properties"] = additional
    items = value.get("items")
    if items is not None:
        result["items"] = _schema_shape(items)
    for keyword in ("allOf", "anyOf", "oneOf"):
        variants = value.get(keyword)
        if isinstance(variants, list):
            result[keyword] = [_schema_shape(variant) for variant in variants]
    return result


def _kind(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, str):
        return "string"
    if isinstance(value, int | float):
        return "number"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return "unknown"


def _sanitize_tool(tool: Any) -> dict[str, object]:
    if not isinstance(tool, dict):
        return {"kind": _kind(tool)}
    safe: dict[str, object] = {
        "field_names": sorted(str(key) for key in tool),
        "kind": "object",
    }
    tool_type = tool.get("type")
    if isinstance(tool_type, str):
        safe["type"] = tool_type
    name = tool.get("name")
    if isinstance(name, str):
        safe["name"] = name
    if "parameters" in tool:
        safe["parameter_schema"] = _schema_shape(tool.get("parameters"))
    tool_format = tool.get("format")
    if isinstance(tool_format, dict):
        format_shape: dict[str, object] = {
            "field_names": sorted(str(key) for key in tool_format),
            "kind": "object",
        }
        format_type = tool_format.get("type")
        if isinstance(format_type, str):
            format_shape["type"] = format_type
        safe["format_shape"] = format_shape
    nested = tool.get("tools")
    if isinstance(nested, list):
        safe["tools"] = [_sanitize_tool(item) for item in nested]
    return safe


def _sanitize_content_part(part: Any) -> dict[str, object]:
    if not isinstance(part, dict):
        return {"kind": _kind(part)}
    safe: dict[str, object] = {
        "field_names": sorted(str(key) for key in part),
        "kind": "object",
    }
    part_type = part.get("type")
    if isinstance(part_type, str):
        safe["type"] = part_type
    return safe


def _sanitize_input_item(item: Any) -> dict[str, object]:
    if not isinstance(item, dict):
        return {"kind": _kind(item)}
    safe: dict[str, object] = {
        "field_names": sorted(str(key) for key in item),
        "kind": "object",
    }
    item_type = item.get("type")
    if isinstance(item_type, str):
        safe["type"] = item_type
    role = item.get("role")
    if isinstance(role, str):
        safe["role"] = role
    content = item.get("content")
    if isinstance(content, list):
        safe["content"] = [_sanitize_content_part(part) for part in content]
    elif content is not None:
        safe["content"] = {"kind": _kind(content)}
    tools = item.get("tools")
    if isinstance(tools, list):
        safe["tools"] = [_sanitize_tool(tool) for tool in tools]
    return safe


def _sanitize_control_object(value: Any) -> dict[str, object]:
    if not isinstance(value, dict):
        return {"kind": _kind(value)}
    return {
        "field_names": sorted(str(key) for key in value),
        "fields": {str(key): {"kind": _kind(item)} for key, item in sorted(value.items())},
        "kind": "object",
    }


def sanitize_request(request: ParsedHttpRequest) -> dict[str, object]:
    if request.method != "POST":
        raise CaptureError("Loopback capture received an unexpected HTTP method.")
    parsed_target = urlsplit(request.target)
    if parsed_target.path != "/v1/responses" or parsed_target.query or parsed_target.fragment:
        raise CaptureError("Loopback capture received an unexpected HTTP path.")
    header_summary = sanitize_headers(request.headers)
    if header_summary["content_encoding"] != {"present": False}:
        raise CaptureError("Loopback capture received an unsupported Content-Encoding header.")
    if header_summary["content_type"] != "application/json":
        raise CaptureError("Loopback capture received an unsupported content type.")
    if not header_summary["authorization"]["present"]:  # type: ignore[index]
        raise CaptureError("Loopback capture did not receive API-key authorization.")
    try:
        payload = json.loads(request.body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CaptureError("Loopback capture received malformed JSON.") from exc
    if not isinstance(payload, dict):
        raise CaptureError("Loopback capture received a non-object JSON request.")

    field_shapes: dict[str, object] = {}
    for field, value in sorted(payload.items()):
        if field == "model":
            field_shapes[field] = {"kind": _kind(value), "value": value}
        elif field == "input" and isinstance(value, list):
            field_shapes[field] = {
                "items": [_sanitize_input_item(item) for item in value],
                "kind": "array",
            }
        elif field == "tools" and isinstance(value, list):
            field_shapes[field] = {
                "items": [_sanitize_tool(tool) for tool in value],
                "kind": "array",
            }
        elif field in {"reasoning", "text"}:
            field_shapes[field] = _sanitize_control_object(value)
        elif field in {"parallel_tool_calls", "store", "stream"} and isinstance(value, bool):
            field_shapes[field] = {"kind": "boolean", "value": value}
        elif isinstance(value, list):
            field_shapes[field] = {
                "item_kinds": sorted({_kind(item) for item in value}),
                "kind": "array",
            }
        else:
            field_shapes[field] = {"kind": _kind(value)}

    if field_shapes.get("model") != {"kind": "string", "value": PINNED_MODEL}:
        raise CaptureError("Loopback capture request used an unexpected model.")
    return {
        "field_shapes": field_shapes,
        "headers": header_summary,
        "method": request.method,
        "path": parsed_target.path,
        "top_level_fields": sorted(str(field) for field in payload),
    }


_0149_TOP_LEVEL_FIELDS = frozenset(
    {
        "client_metadata",
        "include",
        "input",
        "instructions",
        "model",
        "parallel_tool_calls",
        "prompt_cache_key",
        "reasoning",
        "store",
        "stream",
        "text",
        "tool_choice",
        "tools",
    }
)
_0149_TOOL_TYPES = frozenset({"function", "custom", "tool_search", "web_search"})
_0149_UNSAFE_FIELD_MARKERS = frozenset(
    {"authorization", "api_key", "apikey", "cookie", "headers", "password", "secret", "token"}
)


def _0149_type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, int | float):
        return "number"
    return "unknown"


def _0149_safe_field_names(value: dict[str, Any]) -> list[str]:
    field_names = sorted(str(field) for field in value)
    if any(field.lower() in _0149_UNSAFE_FIELD_MARKERS for field in field_names):
        raise CaptureError("Codex 0.149 capture contained a secret or authority field name.")
    return field_names


def _0149_reject_nested_authority_fields(value: Any) -> None:
    if isinstance(value, dict):
        if any(str(field).lower() in _0149_UNSAFE_FIELD_MARKERS for field in value):
            raise CaptureError("Codex 0.149 capture contained a nested authority field name.")
        for child in value.values():
            _0149_reject_nested_authority_fields(child)
    elif isinstance(value, list):
        for child in value:
            _0149_reject_nested_authority_fields(child)


def sanitize_0149_request(request: ParsedHttpRequest) -> dict[str, object]:
    """Keep only exact Codex 0.149 structural facts from one request."""
    if request.method != "POST":
        raise CaptureError("Loopback capture received an unexpected HTTP method.")
    parsed_target = urlsplit(request.target)
    if parsed_target.path != "/v1/responses" or parsed_target.query or parsed_target.fragment:
        raise CaptureError("Loopback capture received an unexpected HTTP path.")
    header_summary = sanitize_headers(request.headers)
    if header_summary["content_encoding"] != {"present": False}:
        raise CaptureError("Loopback capture received an unsupported Content-Encoding header.")
    if header_summary["content_type"] != "application/json":
        raise CaptureError("Loopback capture received an unsupported content type.")
    if not header_summary["authorization"]["present"]:  # type: ignore[index]
        raise CaptureError("Loopback capture did not receive API-key authorization.")
    try:
        payload = json.loads(request.body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CaptureError("Loopback capture received malformed JSON.") from exc
    if not isinstance(payload, dict) or not set(payload) <= _0149_TOP_LEVEL_FIELDS:
        raise CaptureError("Codex 0.149 capture contained an unknown top-level field.")
    tools = payload.get("tools")
    if not isinstance(tools, list) or not tools or len(tools) > 16:
        raise CaptureError("Codex 0.149 capture contained an invalid tools array.")
    shapes: dict[tuple[str, tuple[str, ...]], int] = {}
    for tool in tools:
        if not isinstance(tool, dict) or not isinstance(tool.get("type"), str):
            raise CaptureError("Codex 0.149 capture contained an invalid tool declaration.")
        tool_type = tool["type"]
        if tool_type not in _0149_TOOL_TYPES:
            raise CaptureError("Codex 0.149 capture contained an unknown tool type.")
        field_names = tuple(_0149_safe_field_names(tool))
        _0149_reject_nested_authority_fields({key: child for key, child in tool.items() if key != "type"})
        shapes[(tool_type, field_names)] = shapes.get((tool_type, field_names), 0) + 1
    choice = payload.get("tool_choice")
    if not isinstance(choice, str) or choice != "auto":
        raise CaptureError("Codex 0.149 capture did not use the neutral auto tool choice.")
    shape_rows = [
        {"count": count, "field_names": list(field_names), "type": tool_type}
        for (tool_type, field_names), count in sorted(shapes.items())
    ]
    return {
        "field_types": {field: _0149_type_name(payload[field]) for field in sorted(payload)},
        "tool_choice": {"type": "string", "value_class": "auto"},
        "tool_declarations": {"count": len(tools), "shapes": shape_rows, "type": "array"},
    }


def validate_0149_production_path(request: ParsedHttpRequest) -> tuple[str, ...]:
    """Run one fresh raw capture through the production module and policy in memory."""
    try:
        payload = json.loads(request.body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CaptureError("Codex 0.149 production-path capture was not valid JSON.") from exc
    if not isinstance(payload, dict):
        raise CaptureError("Codex 0.149 production-path capture was not an object.")

    # Keep these production imports and the raw payload scoped to this check.
    # Nothing from this path is serialized, logged, persisted, or returned.
    try:
        from slaif_gateway.config import Settings
        from slaif_gateway.modules.clients.codex_0149 import (
            CODEX_0149_ADAPTER_MANAGED_CANDIDATE_SHAPES,
        )
        from slaif_gateway.modules.clients.registry import CODEX_0149_CLIENT_MODULE

        normalized = CODEX_0149_CLIENT_MODULE.normalize_responses(payload)
        candidates = tuple(normalized.adapter_managed_declaration_candidates)
        if candidates != ("tool_search", "web_search"):
            raise CaptureError("Codex 0.149 production path observed the wrong candidate set.")
        policy_spec = CODEX_0149_CLIENT_MODULE.policy_spec
        if policy_spec is None:
            raise CaptureError("Codex 0.149 production policy spec is unavailable.")
        policy_class = importlib.import_module(
            "slaif_gateway.services.responses_request_policy"
        ).ResponsesRequestPolicy
        policy_result = policy_class(Settings(), client_spec=policy_spec).apply(
            normalized.body,
            allow_codex_request_envelope=True,
            allow_codex_client_tools=True,
            allow_codex_streaming_tool_events=True,
            adapter_managed_declaration_candidates=frozenset(candidates),
            adapter_managed_declaration_shapes=CODEX_0149_ADAPTER_MANAGED_CANDIDATE_SHAPES,
            allow_external_tool_request=False,
        )
        policy_tools = policy_result.effective_body.get("tools")
        if policy_tools != payload.get("tools"):
            raise CaptureError("Codex 0.149 production policy changed the candidate declarations.")
        hosted_admission_requested = any(
            isinstance(item, dict)
            and item.get("type") == "web_search"
            and "web_search" not in candidates
            for item in policy_tools
        )
        if hosted_admission_requested:
            raise CaptureError("Codex 0.149 production path entered hosted-tool admission.")
        return candidates
    except CaptureError:
        raise
    except Exception as exc:  # noqa: BLE001
        error_code = getattr(exc, "error_code", "unknown")
        raise CaptureError(
            "Codex 0.149 production normalizer or policy rejected the capture "
            f"({type(exc).__name__}:{error_code})."
        ) from exc


def sanitize_model_catalog(catalog: Any, *, model: str) -> dict[str, object]:
    if not isinstance(catalog, dict) or not isinstance(catalog.get("models"), list):
        raise CaptureError("Bundled Codex model catalog has an unexpected shape.")
    matches = [entry for entry in catalog["models"] if isinstance(entry, dict) and entry.get("slug") == model]
    if len(matches) != 1:
        raise CaptureError("Pinned model is absent or ambiguous in the bundled Codex catalog.")
    entry = matches[0]
    safe: dict[str, object] = {}
    for field in sorted(_SAFE_CATALOG_FIELDS):
        if field not in entry:
            continue
        value = entry[field]
        if field == "supported_reasoning_levels":
            if not isinstance(value, list):
                raise CaptureError("Bundled Codex reasoning metadata has an unexpected shape.")
            efforts = []
            for item in value:
                if not isinstance(item, dict) or not isinstance(item.get("effort"), str):
                    raise CaptureError("Bundled Codex reasoning metadata has an unexpected shape.")
                effort = item["effort"]
                if effort not in _SAFE_REASONING_LEVELS:
                    raise CaptureError("Bundled Codex reasoning metadata is not allowlisted.")
                efforts.append(effort)
            safe[field] = efforts
        elif field == "truncation_policy":
            if not isinstance(value, dict):
                raise CaptureError("Bundled Codex truncation metadata has an unexpected shape.")
            mode = value.get("mode")
            limit = value.get("limit")
            if mode not in {"bytes", "tokens"} or not isinstance(limit, int) or limit < 0:
                raise CaptureError("Bundled Codex truncation metadata is not allowlisted.")
            safe[field] = {"limit": limit, "mode": mode}
        elif field == "input_modalities":
            if (
                not isinstance(value, list)
                or not all(isinstance(item, str) for item in value)
                or not set(value) <= _SAFE_INPUT_MODALITIES
            ):
                raise CaptureError("Bundled Codex input modality metadata is not allowlisted.")
            safe[field] = value
        elif field in _SAFE_CATALOG_STRING_VALUES:
            if value is not None and value not in _SAFE_CATALOG_STRING_VALUES[field]:
                raise CaptureError("Bundled Codex string metadata is not allowlisted.")
            safe[field] = value
        elif field in {
            "include_apps_usage_instructions",
            "include_plugin_usage_instructions",
            "include_skills_usage_instructions",
            "supported_in_api",
            "supports_image_detail_original",
            "supports_parallel_tool_calls",
            "supports_reasoning_summary_parameter",
            "supports_search_tool",
            "support_verbosity",
            "use_responses_lite",
        }:
            if not isinstance(value, bool):
                raise CaptureError("Bundled Codex boolean metadata is not allowlisted.")
            safe[field] = value
        elif field in {
            "auto_compact_token_limit",
            "context_window",
            "effective_context_window_percent",
            "max_context_window",
        }:
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, int) or value < 0
            ):
                raise CaptureError("Bundled Codex numeric metadata is not allowlisted.")
            safe[field] = value
        elif field == "slug":
            if value != model:
                raise CaptureError("Bundled Codex model slug is not the pinned model.")
            safe[field] = value
        else:
            raise CaptureError("Bundled Codex catalog sanitizer encountered an unknown field.")
    if safe.get("slug") != PINNED_MODEL or safe.get("use_responses_lite") is not True:
        raise CaptureError("Bundled Codex model metadata does not match the pinned profile.")
    if _FREE_TEXT_CATALOG_FIELDS.intersection(safe):
        raise CaptureError("Bundled Codex catalog sanitizer retained a free-text field.")
    return safe


def _flatten_tools(
    items: list[dict[str, object]],
    top_level_tools: list[object],
) -> list[dict[str, object]]:
    flattened: list[dict[str, object]] = []

    def visit(tool: object, *, parent_type: str | None = None) -> None:
        if not isinstance(tool, dict):
            return
        tool_type = tool.get("type")
        name = tool.get("name")
        if isinstance(tool_type, str):
            entry: dict[str, object] = {"type": tool_type}
            if isinstance(name, str):
                entry["name"] = name
            field_names = tool.get("field_names")
            if isinstance(field_names, list):
                entry["field_names"] = field_names
            if parent_type is not None:
                entry["parent_type"] = parent_type
            flattened.append(entry)
        nested = tool.get("tools")
        if isinstance(nested, list):
            for child in nested:
                visit(child, parent_type=tool_type if isinstance(tool_type, str) else parent_type)

    for item in items:
        tools = item.get("tools")
        if isinstance(tools, list):
            for tool in tools:
                visit(tool)
    for tool in top_level_tools:
        visit(tool)
    return sorted(
        flattened,
        key=lambda item: (str(item.get("type", "")), str(item.get("name", ""))),
    )


def build_gateway_compatibility(request: dict[str, object]) -> dict[str, object]:
    top_fields = request.get("top_level_fields")
    field_shapes = request.get("field_shapes")
    if not isinstance(top_fields, list) or not isinstance(field_shapes, dict):
        raise CaptureError("Sanitized request has an unexpected shape.")

    supported_fields: list[str] = []
    rejected_fields: list[dict[str, str]] = []
    for field in top_fields:
        if not isinstance(field, str):
            raise CaptureError("Sanitized request field names have an unexpected shape.")
        if field in _BASELINE_004_SUPPORTED_FIELDS:
            supported_fields.append(field)
        else:
            rejected_fields.append(
                {"name": field, "reason_code": _baseline_004_unsupported_code_for_field(field)}
            )

    text_shape = field_shapes.get("text")
    if isinstance(text_shape, dict) and isinstance(text_shape.get("field_names"), list):
        for nested_field in text_shape["field_names"]:
            if nested_field != "format":
                rejected_fields.append(
                    {
                        "name": f"text.{nested_field}",
                        "reason_code": "responses_field_not_supported",
                    }
                )

    if "tool_choice" in top_fields and "tools" not in top_fields:
        rejected_fields.append(
            {"name": "tool_choice", "reason_code": "responses_tool_choice_invalid"}
        )

    input_shape = field_shapes.get("input")
    input_items = input_shape.get("items") if isinstance(input_shape, dict) else None
    if not isinstance(input_items, list):
        input_items = []
    supported_input_types: set[str] = set()
    rejected_input_types: list[dict[str, str]] = []
    supported_content_types: set[str] = set()
    rejected_content_types: list[dict[str, str]] = []
    for item in input_items:
        if not isinstance(item, dict):
            continue
        item_type = item.get("type")
        fields = item.get("field_names")
        if item_type == "message" and isinstance(fields, list):
            unknown_fields = sorted(set(fields) - _BASELINE_004_SUPPORTED_INPUT_MESSAGE_FIELDS)
            if unknown_fields:
                rejected_input_types.append(
                    {"name": "message", "reason_code": "responses_input_item_invalid"}
                )
            else:
                supported_input_types.add("message")
        elif isinstance(item_type, str):
            rejected_input_types.append(
                {
                    "name": item_type,
                    "reason_code": "responses_input_item_type_not_supported",
                }
            )
        content = item.get("content")
        if isinstance(content, list):
            for part in content:
                if not isinstance(part, dict):
                    continue
                part_type = part.get("type")
                part_fields = part.get("field_names")
                if (
                    part_type == "input_text"
                    and isinstance(part_fields, list)
                    and not (set(part_fields) - _BASELINE_004_SUPPORTED_INPUT_TEXT_PART_FIELDS)
                ):
                    supported_content_types.add("input_text")
                elif isinstance(part_type, str):
                    rejected_content_types.append(
                        {
                            "name": part_type,
                            "reason_code": "responses_input_content_part_not_supported",
                        }
                    )

    top_level_tools_shape = field_shapes.get("tools")
    top_level_tools = (
        top_level_tools_shape.get("items") if isinstance(top_level_tools_shape, dict) else []
    )
    if not isinstance(top_level_tools, list):
        top_level_tools = []
    tools = _flatten_tools(
        [item for item in input_items if isinstance(item, dict)],
        top_level_tools,
    )
    tool_findings: list[dict[str, object]] = []
    stream_value = field_shapes.get("stream")
    streaming = isinstance(stream_value, dict) and stream_value.get("value") is True
    for tool in tools:
        tool_type = str(tool["type"])
        finding = {
            key: value
            for key, value in tool.items()
            if key in {"name", "parent_type", "type"}
        }
        if tool.get("parent_type") == "namespace" or tool_type == "namespace":
            finding["status"] = "rejected"
            finding["reason_code"] = "responses_hosted_tool_not_supported"
        elif tool_type == "function":
            field_names = tool.get("field_names")
            unknown = (
                set(field_names) - _BASELINE_004_SUPPORTED_FUNCTION_TOOL_FIELDS
                if isinstance(field_names, list)
                else set()
            )
            finding["status"] = "rejected" if unknown else "supported_type"
            finding["reason_code"] = (
                "responses_tool_invalid_shape"
                if unknown
                else "requires_top_level_local_tool_shape"
            )
        elif tool_type == "custom":
            field_names = tool.get("field_names")
            unknown = (
                set(field_names) - _BASELINE_004_SUPPORTED_CUSTOM_TOOL_FIELDS
                if isinstance(field_names, list)
                else set()
            )
            finding["status"] = "rejected" if streaming or unknown else "supported_type"
            if unknown:
                finding["reason_code"] = "responses_tool_invalid_shape"
            elif streaming:
                finding["reason_code"] = "responses_custom_tool_streaming_not_supported"
            else:
                finding["reason_code"] = "requires_top_level_local_tool_shape"
        elif tool_type in _BASELINE_004_HOSTED_TOOL_TYPES:
            finding["status"] = "rejected"
            finding["reason_code"] = "responses_hosted_tool_not_supported"
        else:
            finding["status"] = "rejected"
            finding["reason_code"] = "responses_tool_type_not_supported"
        tool_findings.append(finding)

    event_findings = []
    for event in ("response.created", "response.completed"):
        supported = (
            event in _BASELINE_004_ALLOWED_RESPONSES_STREAM_EVENT_TYPES
            or event == "response.completed"
        )
        event_findings.append(
            {
                "name": event,
                "reason_code": "supported_stream_event" if supported else "unsupported_stream_event",
                "status": "supported" if supported else "rejected",
            }
        )

    any_tool_rejected = any(finding.get("status") == "rejected" for finding in tool_findings)
    rejected_input_types = [
        {"name": name, "reason_code": reason_code}
        for name, reason_code in sorted(
            {(item["name"], item["reason_code"]) for item in rejected_input_types}
        )
    ]
    rejected_content_types = [
        {"name": name, "reason_code": reason_code}
        for name, reason_code in sorted(
            {(item["name"], item["reason_code"]) for item in rejected_content_types}
        )
    ]
    rejected = bool(
        rejected_fields or rejected_input_types or rejected_content_types or any_tool_rejected
    )
    return {
        "events": event_findings,
        "input_content_types": {
            "rejected": rejected_content_types,
            "supported": sorted(supported_content_types),
        },
        "input_item_types": {
            "rejected": rejected_input_types,
            "supported": sorted(supported_input_types),
        },
        "status": "not_compatible" if rejected else "compatible",
        "tools": tool_findings,
        "top_level_fields": {
            "rejected": sorted(rejected_fields, key=lambda item: (item["name"], item["reason_code"])),
            "supported": sorted(supported_fields),
        },
    }


def _parse_http_request(raw: bytes) -> ParsedHttpRequest:
    header_end = raw.find(b"\r\n\r\n")
    if header_end < 0:
        if len(raw) > MAX_HEADER_BYTES:
            raise CaptureError("Loopback request headers exceeded the capture limit.")
        raise CaptureError("Loopback capture received incomplete HTTP headers.")
    header_bytes = raw[: header_end + 4]
    if len(header_bytes) > MAX_HEADER_BYTES:
        raise CaptureError("Loopback request headers exceeded the capture limit.")
    try:
        header_text = header_bytes[:-4].decode("ascii")
    except UnicodeDecodeError as exc:
        raise CaptureError("Loopback capture received non-ASCII HTTP headers.") from exc
    lines = header_text.split("\r\n")
    request_parts = lines[0].split(" ")
    if len(request_parts) != 3:
        raise CaptureError("Loopback capture received an invalid HTTP request line.")
    headers: list[tuple[str, str]] = []
    for line in lines[1:]:
        if not line or ":" not in line:
            raise CaptureError("Loopback capture received invalid HTTP headers.")
        name, value = line.split(":", maxsplit=1)
        normalized_name = name.strip().lower()
        if not normalized_name or any(ord(char) < 33 or ord(char) > 126 for char in normalized_name):
            raise CaptureError("Loopback capture received invalid HTTP headers.")
        headers.append((normalized_name, value.strip()))
    content_lengths = [value for name, value in headers if name == "content-length"]
    if len(content_lengths) != 1 or not content_lengths[0].isdigit():
        raise CaptureError("Loopback capture requires one valid Content-Length header.")
    content_length = int(content_lengths[0])
    if content_length > MAX_BODY_BYTES:
        raise CaptureError("Loopback request body exceeded the capture limit.")
    body = raw[header_end + 4 :]
    if len(body) != content_length:
        raise CaptureError("Loopback capture received an incomplete HTTP body.")
    if any(name == "transfer-encoding" for name, _value in headers):
        raise CaptureError("Loopback capture does not accept transfer encoding.")
    return ParsedHttpRequest(
        method=request_parts[0],
        target=request_parts[1],
        version=request_parts[2],
        headers=tuple(headers),
        body=body,
    )


def validate_request_count(count: int) -> None:
    if count != 1:
        raise CaptureError("Loopback capture requires exactly one request.")


def classify_codex_failure(stderr: bytes, stdout: bytes = b"") -> str:
    """Map bounded stderr to a fixed diagnostic without returning captured text."""

    lowered = stderr[:256_000].lower()
    patterns = (
        (b"unexpected argument '--'", "argument_separator_rejected"),
        (b"unknown variant `disabled`", "web_search_config_rejected"),
        (b"error loading config", "configuration_rejected"),
        (b"failed to load config", "configuration_rejected"),
        (b"invalid configuration", "configuration_rejected"),
        (b"configuration error", "configuration_rejected"),
        (b"invalid value", "argument_or_configuration_rejected"),
        (b"invalid type", "configuration_rejected"),
        (b"unknown field", "configuration_rejected"),
        (b"toml", "configuration_rejected"),
        (b"usage: codex exec", "argument_rejected"),
        (b"missing environment variable", "dummy_auth_environment_rejected"),
        (b"stream closed before response.completed", "mock_stream_closed_early"),
        (b"idle timeout waiting for sse", "mock_stream_idle_timeout"),
        (b"failed to parse responsecompleted", "mock_completed_event_rejected"),
        (b"response.failed event received", "mock_response_failed"),
        (b"unexpected status", "mock_http_status_rejected"),
        (b"error sending request for url", "loopback_request_failed"),
        (b"request failed", "loopback_request_failed"),
        (b"internal app-server channel closed", "app_server_channel_closed"),
        (b"not inside a trusted directory", "workdir_rejected"),
        (b"not supported with this auth", "custom_provider_auth_rejected"),
        (b"stream disconnected", "mock_stream_rejected"),
        (b"error decoding response body", "mock_stream_rejected"),
        (b"failed to deserialize", "mock_stream_rejected"),
        (b"connection refused", "loopback_connection_failed"),
    )
    for marker, category in patterns:
        if marker in lowered:
            return category
    event_types: list[str] = []
    for line in stdout[:512_000].splitlines():
        try:
            event = json.loads(line)
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        if isinstance(event, dict) and isinstance(event.get("type"), str):
            event_types.append(event["type"])
    if "turn.failed" in event_types:
        return "turn_failed"
    if "error" in event_types:
        return "error_event"
    if "turn.completed" in event_types:
        return "nonzero_after_turn_completed"
    if event_types:
        return "incomplete_event_sequence"
    return "unclassified"


def ensure_subprocess_success(
    *,
    returncode: int | None = None,
    timed_out: bool = False,
    failure_category: str = "unclassified",
) -> None:
    if timed_out:
        raise CaptureError("Codex capture subprocess timed out safely.")
    if returncode != 0:
        raise CaptureError(
            f"Codex capture subprocess exited unsuccessfully ({failure_category})."
        )


def _read_bounded_request(connection: socket.socket) -> bytes:
    connection.settimeout(5)
    raw = bytearray()
    header_end = -1
    content_length: int | None = None
    while True:
        chunk = connection.recv(4096)
        if not chunk:
            break
        raw.extend(chunk)
        if header_end < 0:
            header_end = raw.find(b"\r\n\r\n")
            if header_end < 0 and len(raw) > MAX_HEADER_BYTES:
                raise CaptureError("Loopback request headers exceeded the capture limit.")
            if header_end >= 0:
                if header_end + 4 > MAX_HEADER_BYTES:
                    raise CaptureError("Loopback request headers exceeded the capture limit.")
                try:
                    header_text = bytes(raw[:header_end]).decode("ascii")
                except UnicodeDecodeError as exc:
                    raise CaptureError("Loopback capture received non-ASCII HTTP headers.") from exc
                values = []
                for line in header_text.split("\r\n")[1:]:
                    if ":" in line:
                        name, value = line.split(":", maxsplit=1)
                        if name.strip().lower() == "content-length":
                            values.append(value.strip())
                if len(values) != 1 or not values[0].isdigit():
                    raise CaptureError("Loopback capture requires one valid Content-Length header.")
                content_length = int(values[0])
                if content_length > MAX_BODY_BYTES:
                    raise CaptureError("Loopback request body exceeded the capture limit.")
        if header_end >= 0 and content_length is not None:
            expected = header_end + 4 + content_length
            if len(raw) == expected:
                return bytes(raw)
            if len(raw) > expected:
                raise CaptureError("Loopback capture received trailing HTTP request bytes.")
    return bytes(raw)


def _mock_sse_body() -> bytes:
    chunks = []
    for event in MOCK_EVENTS:
        event_name = event["type"]
        data = json.dumps(event, sort_keys=True, separators=(",", ":"))
        chunks.append(f"event: {event_name}\ndata: {data}\n\n")
    body = "".join(chunks).encode("ascii")
    validate_mock_sse(body)
    return body


def validate_mock_sse(body: bytes) -> None:
    """Validate the exact fixed mock sequence without echoing malformed bytes."""

    try:
        text = body.decode("ascii")
    except UnicodeDecodeError as exc:
        raise CaptureError("Mock SSE is not ASCII.") from exc
    blocks = [block for block in text.split("\n\n") if block]
    if len(blocks) != len(MOCK_EVENTS):
        raise CaptureError("Mock SSE event sequence is malformed.")
    for block, expected in zip(blocks, MOCK_EVENTS, strict=True):
        lines = block.splitlines()
        if len(lines) != 2 or not lines[0].startswith("event: ") or not lines[1].startswith("data: "):
            raise CaptureError("Mock SSE event sequence is malformed.")
        event_name = lines[0].removeprefix("event: ")
        if event_name != expected["type"]:
            raise CaptureError("Mock SSE event sequence is malformed.")
        try:
            data = json.loads(lines[1].removeprefix("data: "))
        except json.JSONDecodeError as exc:
            raise CaptureError("Mock SSE event JSON is malformed.") from exc
        if data != expected:
            raise CaptureError("Mock SSE event structure is malformed.")


def _write_response(connection: socket.socket, *, success: bool) -> None:
    if success:
        body = _mock_sse_body()
        status = b"200 OK"
        content_type = b"text/event-stream"
    else:
        body = b'{"error":"capture rejected"}'
        status = b"400 Bad Request"
        content_type = b"application/json"
    response = b"\r\n".join(
        (
            b"HTTP/1.1 " + status,
            b"Content-Type: " + content_type,
            f"Content-Length: {len(body)}".encode("ascii"),
            b"Connection: close",
            b"",
            body,
        )
    )
    connection.sendall(response)


def _write_0149_response(connection: socket.socket, *, success: bool) -> None:
    """Stop exact 0.149 captures with a fixed, non-model HTTP error."""
    del success
    body = b'{"error":{"type":"synthetic_capture_stop"}}'
    response = b"\r\n".join(
        (
            b"HTTP/1.1 400 Bad Request",
            b"Content-Type: application/json",
            f"Content-Length: {len(body)}".encode("ascii"),
            b"Connection: close",
            b"",
            body,
        )
    )
    connection.sendall(response)


class LoopbackCaptureServer:
    """A single-purpose, one-request bounded HTTP server."""

    def __init__(self, *, request_sanitizer=sanitize_request, response_writer=_write_response) -> None:
        self._listener: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._done = threading.Event()
        self.request: ParsedHttpRequest | None = None
        self.error: CaptureError | None = None
        self.request_count = 0
        self.port: int | None = None
        self._request_sanitizer = request_sanitizer
        self._response_writer = response_writer

    def start(self) -> None:
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("127.0.0.1", 0))
        listener.listen(2)
        listener.settimeout(0.1)
        address = listener.getsockname()
        if address[0] != "127.0.0.1":
            listener.close()
            raise CaptureError("Capture server did not bind to the required loopback address.")
        self._listener = listener
        self.port = int(address[1])
        self._thread = threading.Thread(target=self._serve, name="codex-capture-loopback", daemon=True)
        self._thread.start()

    def _serve(self) -> None:
        assert self._listener is not None
        deadline = time.monotonic() + SERVER_TIMEOUT_SECONDS
        try:
            while not self._stop.is_set() and time.monotonic() < deadline:
                try:
                    connection, peer = self._listener.accept()
                except TimeoutError:
                    continue
                except OSError:
                    if self._stop.is_set():
                        break
                    self.error = CaptureError("Loopback capture transport failed safely.")
                    break
                with connection:
                    if peer[0] != "127.0.0.1":
                        self.error = CaptureError("Capture server rejected a non-loopback peer.")
                        self._response_writer(connection, success=False)
                        break
                    self.request_count += 1
                    if self.request_count != 1:
                        self.error = CaptureError("Loopback capture received multiple requests.")
                        self._response_writer(connection, success=False)
                        break
                    try:
                        raw = _read_bounded_request(connection)
                        request = _parse_http_request(raw)
                        self._request_sanitizer(request)
                    except (CaptureError, OSError) as exc:
                        self.error = (
                            exc
                            if isinstance(exc, CaptureError)
                            else CaptureError("Loopback capture transport failed safely.")
                        )
                        self._response_writer(connection, success=False)
                        break
                    finally:
                        if "raw" in locals():
                            del raw
                    self.request = request
                    self._response_writer(connection, success=True)
            if self.request_count == 0 and not self._stop.is_set():
                self.error = CaptureError("Codex did not reach the loopback capture server.")
        finally:
            self._done.set()

    def stop(self) -> None:
        self._stop.set()
        if self._listener is not None:
            self._listener.close()
        if self._thread is not None:
            self._thread.join(timeout=2)

    def result(self) -> ParsedHttpRequest:
        if self.error is not None:
            raise self.error
        validate_request_count(self.request_count)
        if self.request is None:
            raise CaptureError("Loopback capture did not produce a request.")
        return self.request


def _isolated_environment(codex_home: Path) -> dict[str, str]:
    binary_path = os.environ.get("PATH", "/usr/bin:/bin")
    return {
        CAPTURE_API_KEY_ENV: TOKEN_CANARY,
        "CODEX_HOME": str(codex_home),
        "HOME": str(codex_home),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "NO_PROXY": "127.0.0.1",
        "PATH": binary_path,
        "RUST_BACKTRACE": "0",
        "XDG_CACHE_HOME": str(codex_home / "cache"),
        "XDG_CONFIG_HOME": str(codex_home / "config"),
        "XDG_DATA_HOME": str(codex_home / "data"),
        "no_proxy": "127.0.0.1",
    }


def _config(key: str, value: str) -> list[str]:
    return ["-c", f"{key}={value}"]


def _catalog_command(codex_binary: Path) -> list[str]:
    return [str(codex_binary), "debug", "models", "--bundled"]


def _exec_command(codex_binary: Path, *, workdir: Path, port: int) -> list[str]:
    base_url = f'"http://127.0.0.1:{port}/v1"'
    return [
        str(codex_binary),
        "--ask-for-approval",
        "never",
        "exec",
        "--ephemeral",
        "--ignore-user-config",
        "--ignore-rules",
        "--json",
        "--skip-git-repo-check",
        "--sandbox",
        "read-only",
        "--cd",
        str(workdir),
        *_config("model", f'"{PINNED_MODEL}"'),
        *_config("model_provider", f'"{CAPTURE_PROVIDER_ID}"'),
        *_config("model_reasoning_effort", '"low"'),
        *_config("model_verbosity", '"low"'),
        *_config("check_for_update_on_startup", "false"),
        *_config(f"model_providers.{CAPTURE_PROVIDER_ID}.name", '"SLAIF capture loopback"'),
        *_config(f"model_providers.{CAPTURE_PROVIDER_ID}.base_url", base_url),
        *_config(f"model_providers.{CAPTURE_PROVIDER_ID}.env_key", f'"{CAPTURE_API_KEY_ENV}"'),
        *_config(f"model_providers.{CAPTURE_PROVIDER_ID}.wire_api", '"responses"'),
        *_config(f"model_providers.{CAPTURE_PROVIDER_ID}.requires_openai_auth", "false"),
        *_config(f"model_providers.{CAPTURE_PROVIDER_ID}.request_max_retries", "0"),
        *_config(f"model_providers.{CAPTURE_PROVIDER_ID}.stream_max_retries", "0"),
        *_config(f"model_providers.{CAPTURE_PROVIDER_ID}.stream_idle_timeout_ms", "5000"),
        PROMPT_CANARY,
    ]


def _write_0149_model_catalog(
    codex_binary: Path,
    destination: Path,
    *,
    environment: dict[str, str],
    model: str,
) -> None:
    """Create a private disposable catalog using only the installed CLI schema."""
    try:
        result = subprocess.run(
            [str(codex_binary), "debug", "models", "--bundled"],
            check=False,
            capture_output=True,
            env=environment,
            timeout=CODEX_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CaptureError("Bundled Codex model catalog command failed safely.") from exc
    if result.returncode != 0 or len(result.stdout) > MAX_CATALOG_BYTES:
        raise CaptureError("Bundled Codex model catalog command failed safely.")
    try:
        catalog = json.loads(result.stdout)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CaptureError("Bundled Codex model catalog returned malformed JSON.") from exc
    models = catalog.get("models") if isinstance(catalog, dict) else None
    template = next(
        (
            item
            for item in models or []
            if isinstance(item, dict) and item.get("slug") == "gpt-5.4"
        ),
        next((item for item in models or [] if isinstance(item, dict)), None),
    )
    if template is None:
        raise CaptureError("Bundled Codex model catalog has no usable model schema.")
    local_model = dict(template)
    local_instructions = (
        "Use the provided shell_command function for workspace file reads. "
        "After a required tool result arrives, provide exactly the requested final answer."
    )
    local_model.update(
        {
            "slug": model,
            "display_name": model,
            "description": "Disposable local capture model",
            "input_modalities": ["text", "image"],
            "supports_image_detail_original": False,
            "supports_parallel_tool_calls": False,
            "context_window": 150_000,
            "max_context_window": 150_000,
            "default_reasoning_level": "low",
            "base_instructions": local_instructions,
            "model_messages": {"instructions_template": local_instructions},
        }
    )
    _atomic_write(
        destination,
        json.dumps({"models": [local_model]}, separators=(",", ":")).encode("utf-8"),
    )
    os.chmod(destination, 0o600)


def _exec_command_0149(
    codex_binary: Path,
    *,
    workdir: Path,
    port: int,
    model: str,
    model_catalog: Path,
    output_path: Path,
) -> list[str]:
    base_url = f'"http://127.0.0.1:{port}/v1"'
    return [
        str(codex_binary),
        "--dangerously-bypass-approvals-and-sandbox",
        "exec",
        "--json",
        "--ephemeral",
        "--strict-config",
        "--ignore-user-config",
        "-C",
        str(workdir),
        "-m",
        model,
        "-c",
        'model_provider="slaif-capture"',
        "-c",
        (
            "model_providers.slaif-capture={"
            f'name="Synthetic capture",base_url={base_url},'
            f'env_key="{CAPTURE_API_KEY_ENV}",wire_api="responses"'
            "}"
        ),
        "-c",
        f"model_catalog_json={json.dumps(str(model_catalog))}",
        "-c",
        "check_for_update_on_startup=false",
        "-o",
        str(output_path),
        "Return the word synthetic.",
    ]


def _run_catalog(codex_binary: Path, *, environment: dict[str, str], model: str) -> dict[str, object]:
    try:
        result = subprocess.run(
            _catalog_command(codex_binary),
            check=False,
            capture_output=True,
            env=environment,
            timeout=CODEX_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CaptureError("Bundled Codex model catalog command failed safely.") from exc
    if result.returncode != 0 or len(result.stdout) > MAX_CATALOG_BYTES:
        raise CaptureError("Bundled Codex model catalog command failed safely.")
    try:
        catalog = json.loads(result.stdout)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CaptureError("Bundled Codex model catalog returned malformed JSON.") from exc
    return sanitize_model_catalog(catalog, model=model)


def _mock_event_shapes() -> list[dict[str, object]]:
    return [
        {
            "data": _sanitize_control_object(event),
            "event": event["type"],
        }
        for event in MOCK_EVENTS
    ]


def capture_live(
    *,
    codex_binary: Path,
    expected_version: str,
    model: str,
    profile: str,
) -> dict[str, object]:
    """Perform one isolated live loopback capture and return sanitized evidence only."""

    version = verify_codex_version(codex_binary, expected_version)
    validate_target(expected_version=expected_version, model=model, profile=profile)
    with tempfile.TemporaryDirectory(prefix="slaif-codex-capture-") as temporary:
        temporary_root = Path(temporary)
        codex_home = temporary_root / "codex-home"
        workdir = temporary_root / "empty-workdir"
        codex_home.mkdir(mode=0o700)
        workdir.mkdir(mode=0o700)
        environment = _isolated_environment(codex_home)
        catalog = _run_catalog(codex_binary, environment=environment, model=model)
        server = LoopbackCaptureServer()
        server.start()
        assert server.port is not None
        timed_out = False
        returncode: int | None = None
        failure_category = "unclassified"
        try:
            try:
                result = subprocess.run(
                    _exec_command(codex_binary, workdir=workdir, port=server.port),
                    check=False,
                    capture_output=True,
                    env=environment,
                    timeout=CODEX_TIMEOUT_SECONDS,
                )
                returncode = result.returncode
                if returncode != 0:
                    failure_category = classify_codex_failure(result.stderr, result.stdout)
                del result
            except subprocess.TimeoutExpired:
                timed_out = True
            except OSError as exc:
                raise CaptureError("Codex capture subprocess failed to start safely.") from exc
            time.sleep(0.1)
        finally:
            server.stop()
        request = server.result() if server.request_count else None
        if returncode != 0:
            phase = "after_loopback_request" if server.request_count else "before_loopback_request"
            failure_category = f"{phase}:{failure_category}"
        ensure_subprocess_success(
            returncode=returncode,
            timed_out=timed_out,
            failure_category=failure_category,
        )
        if request is None:
            request = server.result()
        sanitized_request = sanitize_request(request)
        del request

    fixture = {
        "capture": {
            "mock_response": {
                "accepted_by_codex": True,
                "connection_close": True,
                "content_type": "text/event-stream",
                "events": _mock_event_shapes(),
            },
            "request": sanitized_request,
            "subprocess": {"accepted_mock": True, "exit_success": True},
        },
        "gateway_compatibility": build_gateway_compatibility(sanitized_request),
        "identity": {
            "cli_family": "codex-cli",
            "cli_version": version,
            "model": model,
            "profile": profile,
            "source_tag": PINNED_SOURCE_TAG,
        },
        "model_catalog": catalog,
        "schema_version": SCHEMA_VERSION,
    }
    validate_fixture(fixture)
    return fixture


def validate_0149_fixture_path(path: Path, *, allowed_root: Path | None = None) -> Path:
    """Restrict 0.149 writes to the separate versioned structural fixture."""
    root = (allowed_root or (REPO_ROOT / "tests/fixtures/codex")).resolve()
    expected = (root / FIXTURE_0149_RELATIVE_PATH.relative_to("tests/fixtures/codex")).resolve()
    resolved = path.resolve()
    if resolved != expected:
        raise CaptureError("Fixture path is outside the pinned 0.149 fixture location.")
    return resolved


def capture_live_0149(
    *,
    codex_binary: Path,
    expected_version: str,
    model: str,
    profile: str,
) -> dict[str, object]:
    """Perform one exact 0.149.0 disposable structural capture."""
    version = verify_codex_version(
        codex_binary,
        expected_version,
        expected_raw_version=PINNED_0149_RAW_VERSION,
    )
    if expected_version != PINNED_0149_CLI_VERSION:
        raise CaptureError("Requested Codex CLI version is not the pinned 0.149 capture version.")
    if model != PINNED_0149_MODEL or profile != PINNED_0149_PROFILE:
        raise CaptureError("Requested Codex 0.149 target does not match the pinned capture.")
    with tempfile.TemporaryDirectory(prefix="slaif-codex-0149-capture-") as temporary:
        temporary_root = Path(temporary)
        codex_home = temporary_root / "codex-home"
        workdir = temporary_root / "empty-workdir"
        model_catalog = temporary_root / "model-catalog.json"
        output_path = temporary_root / "last-message.tmp"
        codex_home.mkdir(mode=0o700)
        workdir.mkdir(mode=0o700)
        environment = _isolated_environment(codex_home)
        _write_0149_model_catalog(
            codex_binary,
            model_catalog,
            environment=environment,
            model=model,
        )
        server = LoopbackCaptureServer(
            request_sanitizer=sanitize_0149_request,
            response_writer=_write_0149_response,
        )
        server.start()
        assert server.port is not None
        timed_out = False
        returncode: int | None = None
        try:
            try:
                result = subprocess.run(
                    _exec_command_0149(
                        codex_binary,
                        workdir=workdir,
                        port=server.port,
                        model=model,
                        model_catalog=model_catalog,
                        output_path=output_path,
                    ),
                    check=False,
                    capture_output=True,
                    env=environment,
                    timeout=CODEX_TIMEOUT_SECONDS,
                )
                returncode = result.returncode
            except subprocess.TimeoutExpired:
                timed_out = True
            except OSError as exc:
                raise CaptureError("Codex 0.149 capture subprocess failed to start safely.") from exc
            time.sleep(0.1)
        finally:
            server.stop()
        if timed_out:
            raise CaptureError("Codex 0.149 capture subprocess timed out safely.")
        if returncode != 1:
            raise CaptureError("Codex 0.149 capture did not stop at the fixed synthetic rejection.")
        if server.request is None:
            server.result()
        production_candidates = validate_0149_production_path(server.request)
        sanitized_request = sanitize_0149_request(server.request)
        del server.request

    fixture = {
        "capture": {
            "subprocess": {
                "binary_version_output": PINNED_0149_RAW_VERSION,
                "cli_exit_status": "synthetic_rejection",
                "home_scope": "private_disposable",
                "model_call": "not_performed",
                "provider_key": "not_configured",
                "server": "loopback_fake_responses",
                "workspace": "empty",
            },
            "transport": {"method": "POST", "path": "/v1/responses", "wire_api": "responses"},
            "variants": [{"flags": {"search": False}, "request": sanitized_request, "variant_id": "default"}],
        },
        "findings": {
            "adapter_managed_candidate_types": ["tool_search", "web_search"],
            "built_in_search_is_not_gateway_authority": True,
            "identity_hints_transient": True,
            "no_raw_request_content_retained": True,
            "search_flag_did_not_change_captured_shape": False,
        },
        "gateway_compatibility": {
            "compatible_server_pairs": ["codex-0.149-responses-v1->local-coding-v1"],
            "module_status": "structural_capture_and_pair_reviewed_default_denied",
            "provider_e2e": False,
            "qualification": "none",
        },
        "identity": {
            "cli_family": "codex-cli",
            "cli_version": version,
            "model": model,
            "profile": profile,
            "source_tag": "npm-@openai/codex-0.149.0",
        },
        "schema_version": 1,
    }
    if production_candidates != ("tool_search", "web_search"):
        raise CaptureError("Codex 0.149 production path did not preserve both candidates.")
    validate_0149_fixture(fixture)
    return fixture


def validate_0149_fixture(fixture: Any) -> None:
    """Validate the separately versioned 0.149 structural capture."""
    if not isinstance(fixture, dict) or fixture.get("schema_version") != 1:
        raise CaptureError("Codex 0.149 fixture schema version is invalid.")
    identity = fixture.get("identity")
    if not isinstance(identity, dict) or identity != {
        "cli_family": "codex-cli",
        "cli_version": PINNED_0149_CLI_VERSION,
        "model": PINNED_0149_MODEL,
        "profile": PINNED_0149_PROFILE,
        "source_tag": "npm-@openai/codex-0.149.0",
    }:
        raise CaptureError("Codex 0.149 fixture identity is invalid.")
    capture = fixture.get("capture")
    if not isinstance(capture, dict) or capture.get("transport") != {
        "method": "POST",
        "path": "/v1/responses",
        "wire_api": "responses",
    }:
        raise CaptureError("Codex 0.149 fixture transport is invalid.")
    subprocess_result = capture.get("subprocess")
    if not isinstance(subprocess_result, dict) or subprocess_result != {
        "binary_version_output": PINNED_0149_RAW_VERSION,
        "cli_exit_status": "synthetic_rejection",
        "home_scope": "private_disposable",
        "model_call": "not_performed",
        "provider_key": "not_configured",
        "server": "loopback_fake_responses",
        "workspace": "empty",
    }:
        raise CaptureError("Codex 0.149 fixture subprocess facts are invalid.")
    variants = capture.get("variants")
    if not isinstance(variants, list) or len(variants) != 1:
        raise CaptureError("Codex 0.149 fixture variants are invalid.")
    request = variants[0].get("request") if isinstance(variants[0], dict) else None
    if not isinstance(request, dict):
        raise CaptureError("Codex 0.149 fixture request is invalid.")
    expected_field_types = {
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
    if request.get("field_types") != expected_field_types or request.get("tool_choice") != {
        "type": "string",
        "value_class": "auto",
    }:
        raise CaptureError("Codex 0.149 fixture request facts are invalid.")
    expected_shapes = [
        {"count": 1, "field_names": ["description", "format", "name", "type"], "type": "custom"},
        {
            "count": 5,
            "field_names": ["description", "name", "parameters", "strict", "type"],
            "type": "function",
        },
        {
            "count": 1,
            "field_names": ["description", "execution", "parameters", "type"],
            "type": "tool_search",
        },
        {
            "count": 1,
            "field_names": ["external_web_access", "search_content_types", "type"],
            "type": "web_search",
        },
    ]
    tool_declarations = request.get("tool_declarations")
    if not isinstance(tool_declarations, dict) or tool_declarations != {
        "count": 8,
        "shapes": expected_shapes,
        "type": "array",
    }:
        raise CaptureError("Codex 0.149 fixture tool facts are invalid.")
    if fixture.get("findings") != {
        "adapter_managed_candidate_types": ["tool_search", "web_search"],
        "built_in_search_is_not_gateway_authority": True,
        "identity_hints_transient": True,
        "no_raw_request_content_retained": True,
        "search_flag_did_not_change_captured_shape": False,
    }:
        raise CaptureError("Codex 0.149 fixture findings are invalid.")
    if fixture.get("gateway_compatibility") != {
        "compatible_server_pairs": ["codex-0.149-responses-v1->local-coding-v1"],
        "module_status": "structural_capture_and_pair_reviewed_default_denied",
        "provider_e2e": False,
        "qualification": "none",
    }:
        raise CaptureError("Codex 0.149 fixture compatibility facts are invalid.")
    serialized = canonical_json_bytes(fixture)
    if any(marker in serialized for marker in (PROMPT_CANARY.encode(), TOKEN_CANARY.encode(), b"authorization", b"Bearer ")):
        raise CaptureError("Codex 0.149 fixture contains forbidden capture content.")
    if hashlib.sha256(serialized).hexdigest() != APPROVED_0149_CANONICAL_FIXTURE_SHA256:
        raise CaptureError(FIXTURE_INTEGRITY_ERROR)


def validate_fixture(fixture: Any) -> None:
    if not isinstance(fixture, dict) or fixture.get("schema_version") != SCHEMA_VERSION:
        raise CaptureError("Fixture schema version is invalid.")
    identity = fixture.get("identity")
    expected_identity = {
        "cli_family": "codex-cli",
        "cli_version": PINNED_CLI_VERSION,
        "model": PINNED_MODEL,
        "profile": PINNED_PROFILE,
        "source_tag": PINNED_SOURCE_TAG,
    }
    if identity != expected_identity:
        raise CaptureError("Fixture identity does not match the pinned capture target.")
    capture = fixture.get("capture")
    if not isinstance(capture, dict):
        raise CaptureError("Fixture capture section is invalid.")
    request = capture.get("request")
    if not isinstance(request, dict) or request.get("method") != "POST":
        raise CaptureError("Fixture request method is invalid.")
    if request.get("path") != "/v1/responses":
        raise CaptureError("Fixture request path is invalid.")
    headers = request.get("headers")
    if not isinstance(headers, dict):
        raise CaptureError("Fixture header section is invalid.")
    if headers.get("authorization") != {"present": True, "redacted": True}:
        raise CaptureError("Fixture authorization redaction invariant failed.")
    if headers.get("content_encoding") != {"present": False}:
        raise CaptureError("Fixture content-encoding invariant failed.")
    subprocess_result = capture.get("subprocess")
    if subprocess_result != {"accepted_mock": True, "exit_success": True}:
        raise CaptureError("Fixture mock acceptance invariant failed.")
    compatibility = fixture.get("gateway_compatibility")
    if not isinstance(compatibility, dict) or compatibility.get("status") != "not_compatible":
        raise CaptureError("Fixture compatibility status is invalid.")
    expected_compatibility = build_gateway_compatibility(request)
    if compatibility != expected_compatibility:
        raise CaptureError("Fixture compatibility diff is stale or altered.")
    catalog = fixture.get("model_catalog")
    if not isinstance(catalog, dict) or set(catalog) - _SAFE_CATALOG_FIELDS:
        raise CaptureError("Fixture bundled-catalog metadata is not allowlisted.")
    serialized = canonical_json_bytes(fixture)
    forbidden = (
        PROMPT_CANARY.encode(),
        TOKEN_CANARY.encode(),
        b"base_instructions",
        b"model_messages",
        b"schema-description-canary",
    )
    if any(value in serialized for value in forbidden):
        raise CaptureError("Fixture contains forbidden capture content.")
    if hashlib.sha256(serialized).hexdigest() != APPROVED_CANONICAL_FIXTURE_SHA256:
        raise CaptureError(FIXTURE_INTEGRITY_ERROR)


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary_path, 0o644)
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _load_fixture(path: Path) -> dict[str, object]:
    try:
        raw = path.read_bytes()
        fixture = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CaptureError("Fixture could not be read as JSON.") from exc
    validate_fixture(fixture)
    if raw != canonical_json_bytes(fixture):
        raise CaptureError("Fixture is not in canonical deterministic JSON form.")
    return fixture


def _load_fixture_0149(path: Path) -> dict[str, object]:
    try:
        raw = path.read_bytes()
        fixture = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CaptureError("Codex 0.149 fixture could not be read as JSON.") from exc
    validate_0149_fixture(fixture)
    if raw != canonical_json_bytes(fixture):
        raise CaptureError("Codex 0.149 fixture is not canonical deterministic JSON.")
    return fixture


def _add_live_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--codex-binary", type=Path, required=True)
    parser.add_argument("--expected-cli-version", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--profile", required=True)


def _add_0149_live_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--codex-binary", type=Path, required=True)
    parser.add_argument("--expected-cli-version", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--profile", required=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    capture = subparsers.add_parser("capture", help="capture and explicitly write the fixture")
    _add_live_arguments(capture)
    capture.add_argument("--output", type=Path, required=True)
    capture.add_argument("--write-fixture", action="store_true")
    verify = subparsers.add_parser("verify-live", help="capture in memory and compare to fixture")
    _add_live_arguments(verify)
    verify.add_argument("--fixture", type=Path, required=True)
    capture_0149 = subparsers.add_parser(
        "capture-0149", help="capture and explicitly write the Codex 0.149 fixture"
    )
    _add_0149_live_arguments(capture_0149)
    capture_0149.add_argument("--output", type=Path, required=True)
    capture_0149.add_argument("--write-fixture", action="store_true")
    verify_0149 = subparsers.add_parser(
        "verify-live-0149", help="capture Codex 0.149 in memory and compare to its fixture"
    )
    _add_0149_live_arguments(verify_0149)
    verify_0149.add_argument("--fixture", type=Path, required=True)
    validate_0149 = subparsers.add_parser(
        "validate-0149", help="validate a checked-in Codex 0.149 fixture"
    )
    validate_0149.add_argument("--fixture", type=Path, required=True)
    validate = subparsers.add_parser("validate", help="validate a checked-in fixture without Codex")
    validate.add_argument("--fixture", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "capture":
            if not args.write_fixture:
                raise CaptureError("Live fixture writing requires the explicit --write-fixture flag.")
            fixture_path = validate_fixture_path(args.output)
            fixture = capture_live(
                codex_binary=args.codex_binary,
                expected_version=args.expected_cli_version,
                model=args.model,
                profile=args.profile,
            )
            payload = canonical_json_bytes(fixture)
            _atomic_write(fixture_path, payload)
            digest = hashlib.sha256(payload).hexdigest()
            print(f"CAPTURE_OK fixture_sha256={digest} status=not_compatible")
            return 0
        if args.command == "verify-live":
            fixture_path = validate_fixture_path(args.fixture)
            live = capture_live(
                codex_binary=args.codex_binary,
                expected_version=args.expected_cli_version,
                model=args.model,
                profile=args.profile,
            )
            checked_in = _load_fixture(fixture_path)
            if canonical_json_bytes(live) != canonical_json_bytes(checked_in):
                raise CaptureError("Live sanitized capture does not match the checked-in fixture.")
            print("VERIFY_LIVE_OK status=not_compatible")
            return 0
        if args.command == "capture-0149":
            if not args.write_fixture:
                raise CaptureError("Live fixture writing requires the explicit --write-fixture flag.")
            fixture_path = validate_0149_fixture_path(args.output)
            fixture = capture_live_0149(
                codex_binary=args.codex_binary,
                expected_version=args.expected_cli_version,
                model=args.model,
                profile=args.profile,
            )
            payload = canonical_json_bytes(fixture)
            _atomic_write(fixture_path, payload)
            digest = hashlib.sha256(payload).hexdigest()
            print(f"CAPTURE_0149_OK fixture_sha256={digest} status=structural_candidate")
            return 0
        if args.command == "verify-live-0149":
            fixture_path = validate_0149_fixture_path(args.fixture)
            live = capture_live_0149(
                codex_binary=args.codex_binary,
                expected_version=args.expected_cli_version,
                model=args.model,
                profile=args.profile,
            )
            checked_in = _load_fixture_0149(fixture_path)
            if canonical_json_bytes(live) != canonical_json_bytes(checked_in):
                raise CaptureError("Live 0.149 sanitized capture does not match its fixture.")
            print("VERIFY_LIVE_0149_OK status=structural_candidate production_path=passed")
            return 0
        if args.command == "validate-0149":
            fixture_path = validate_0149_fixture_path(args.fixture)
            _load_fixture_0149(fixture_path)
            print("FIXTURE_0149_VALID status=structural_candidate")
            return 0
        fixture_path = validate_fixture_path(args.fixture)
        _load_fixture(fixture_path)
        print("FIXTURE_VALID status=not_compatible")
        return 0
    except CaptureError as exc:
        print(f"CAPTURE_ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
