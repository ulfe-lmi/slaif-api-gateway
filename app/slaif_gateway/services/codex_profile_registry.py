"""Immutable, server-owned Codex qualification profile definitions.

The registry is deliberately data-only.  Route metadata may select a profile,
but it cannot provide its limits, capabilities, or qualification claims.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from datetime import date
from types import MappingProxyType
from typing import Mapping

from slaif_gateway.modules.clients.codex_0147 import (
    CODEX_0147_CLIENT_MODULE_ID,
    CODEX_0147_CLIENT_MODULE_VERSION,
    CODEX_0147_FIXTURE_SHA256,
)

PROFILE_ID = "openai-gpt-5.6-sol-codex-0.147-v1"
PROFILE_METADATA_VERSION = 2
PROFILE_FIXTURE_SHA256 = "436ea530b9f984807dfc73ccce0b5233d0a3047ceb10ef942fbc8d12cac47432"
QWEN38_TEXT_PROFILE_ID = "qwen3.8-27b-text-codex-0.148-v1"
QWEN38_TEXT_PROFILE_FIXTURE_SHA256 = "96a05bf2f0ddd88b0f2b048589e71005aea120f7cd74c06ced4c7c4bf20f4f89"
QWEN38_VISION_PROFILE_ID = "qwen3.8-27b-vision-codex-0.148-v1"
QWEN38_VISION_PROFILE_FIXTURE_SHA256 = "f1f7d744af4cbae0f2e3556e793258a6be5144006ef20f3b3d36ddba6f91f461"

_SAFE_ID = re.compile(r"^[a-z0-9][a-z0-9.-]{2,95}$")
_SAFE_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SAFE_DISPLAY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._-]{0,127}$")
_SAFE_ENDPOINT = re.compile(r"^/v1/[A-Za-z0-9._{}-]+(?:/[A-Za-z0-9._{}-]+)*$")
_SAFE_GATE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_SUPPORTED_MODALITIES = frozenset({"text", "image"})
_SUPPORTED_GATES = frozenset(
    {
        "codex_request_envelope",
        "codex_client_tools",
        "codex_streaming_tool_events",
        "codex_encrypted_reasoning_replay",
        "codex_compaction",
        "image_input",
    }
)
_SUPPORTED_LOCAL_TOOLS = frozenset({"function", "custom"})
_CATALOG_TOP_LEVEL_FIELDS = frozenset({"models"})
_CATALOG_MODEL_FIELDS = frozenset(
    {
        "slug",
        "display_name",
        "context_window",
        "description",
        "additional_speed_tiers",
        "service_tiers",
        "default_service_tier",
        "availability_nux",
        "upgrade",
        "base_instructions",
        "model_messages",
        "supports_reasoning_summaries",
        "default_reasoning_summary",
        "default_verbosity",
        "web_search_tool_type",
        "effective_context_window_percent",
        "experimental_supported_tools",
        "max_context_window",
        "auto_compact_token_limit",
        "priority",
        "input_modalities",
        "default_reasoning_level",
        "supported_reasoning_levels",
        "shell_type",
        "tool_mode",
        "apply_patch_tool_type",
        "multi_agent_version",
        "supported_in_api",
        "supports_image_detail_original",
        "supports_parallel_tool_calls",
        "supports_reasoning_summary_parameter",
        "supports_search_tool",
        "support_verbosity",
        "include_apps_usage_instructions",
        "include_plugin_usage_instructions",
        "include_skills_usage_instructions",
        "use_responses_lite",
        "truncation_policy",
        "visibility",
    }
)
_CATALOG_ENUMS = {
    "default_reasoning_level": frozenset({"none", "minimal", "low", "medium", "high", "xhigh", "max", "ultra"}),
    "default_reasoning_summary": frozenset({"none"}),
    "shell_type": frozenset({"default", "disabled", "local", "shell_command", "unified_exec"}),
    "tool_mode": frozenset({"code_mode", "code_mode_only", "direct"}),
    "apply_patch_tool_type": frozenset({"freeform"}),
    "multi_agent_version": frozenset({"v1", "v2"}),
    "visibility": frozenset({"hide", "list", "none"}),
}
_CATALOG_BOOLEAN_FIELDS = frozenset(
    {
        "supported_in_api",
        "supports_image_detail_original",
        "supports_parallel_tool_calls",
        "supports_reasoning_summary_parameter",
        "supports_search_tool",
        "support_verbosity",
        "include_apps_usage_instructions",
        "include_plugin_usage_instructions",
        "include_skills_usage_instructions",
        "use_responses_lite",
        "supports_reasoning_summaries",
    }
)
_CATALOG_INTEGER_FIELDS = frozenset(
    {
        "context_window", "max_context_window", "auto_compact_token_limit", "priority",
        "effective_context_window_percent",
    }
)
_CATALOG_ARRAY_FIELDS = frozenset(
    {"additional_speed_tiers", "service_tiers", "experimental_supported_tools"}
)
_CATALOG_NULLABLE_FIELDS = frozenset(
    {"default_service_tier", "availability_nux", "upgrade", "base_instructions", "model_messages", "default_verbosity",
     "apply_patch_tool_type"}
)
_SECRET_MARKERS = ("sk-", "api_key", "authorization", "bearer ", "password", "secret", "token")


@dataclass(frozen=True, slots=True)
class CodexQualificationProfile:
    profile_id: str
    metadata_version: int
    cli_version: str
    public_model: str
    upstream_model: str
    wire_api: str
    provider_kind: str
    provider_slug: str | None
    required_endpoints: tuple[str, ...]
    required_route_gates: tuple[str, ...]
    context_window_tokens: int
    default_max_output_tokens: int
    max_output_tokens: int
    compaction_mode: str
    reasoning_replay: bool
    streaming_tool_events: bool
    local_tools: tuple[str, ...]
    input_modalities: tuple[str, ...]
    auto_compaction_token_threshold: int | None
    credential_free_provider_fields: Mapping[str, object]
    model_catalog_artifact: str | None
    model_catalog_target: str | None
    fixture_sha256: str
    evidence_date: str
    mocked_qualification: bool
    live_qualification: bool
    profile_name: str
    provider_display_name: str
    catalog_source: str = "bundled"
    client_module_id: str | None = None
    client_module_version: str | None = None

    def __post_init__(self) -> None:
        if not _SAFE_ID.fullmatch(self.profile_id):
            raise ValueError("Codex profile ID is not safely bounded.")
        if (self.client_module_id is None) != (self.client_module_version is None):
            raise ValueError("Codex client module metadata must be complete.")
        if self.client_module_id is not None and (
            not _SAFE_ID.fullmatch(self.client_module_id)
            or not _SAFE_TOKEN.fullmatch(self.client_module_version or "")
        ):
            raise ValueError("Codex client module metadata is unsafe.")
        if self.client_module_id == CODEX_0147_CLIENT_MODULE_ID and (
            self.client_module_version != CODEX_0147_CLIENT_MODULE_VERSION
            or self.fixture_sha256 != CODEX_0147_FIXTURE_SHA256
        ):
            raise ValueError("Codex 0.147 client module metadata does not match its fixture.")
        for name, value in {
            "cli_version": self.cli_version,
            "public_model": self.public_model,
            "upstream_model": self.upstream_model,
            "profile_name": self.profile_name,
            "catalog_source": self.catalog_source,
        }.items():
            if type(value) is not str or not _SAFE_TOKEN.fullmatch(value):
                raise ValueError(f"Codex profile {name} is unsafe.")
        if type(self.provider_display_name) is not str or not _SAFE_DISPLAY.fullmatch(
            self.provider_display_name
        ):
            raise ValueError("Codex profile provider display name is unsafe.")
        if self.metadata_version != PROFILE_METADATA_VERSION:
            raise ValueError("Unsupported Codex profile metadata version.")
        if self.wire_api not in {"responses", "chat"}:
            raise ValueError("Codex profile wire API is unsupported.")
        if self.wire_api != "responses":
            raise ValueError("Codex profiles require the Responses wire API.")
        if self.provider_kind not in {"openai", "openai_compatible"}:
            raise ValueError("Codex profile provider kind is unsupported.")
        if self.provider_slug is not None and not _SAFE_ID.fullmatch(self.provider_slug):
            raise ValueError("Codex profile provider slug is unsafe.")
        if not self.required_endpoints or any(
            not isinstance(endpoint, str) or not _SAFE_ENDPOINT.fullmatch(endpoint)
            for endpoint in self.required_endpoints
        ) or len(set(self.required_endpoints)) != len(self.required_endpoints):
            raise ValueError("Codex profile endpoint set must be non-empty and unique.")
        if any(
            not isinstance(gate, str)
            or not _SAFE_GATE.fullmatch(gate)
            or gate not in _SUPPORTED_GATES
            for gate in self.required_route_gates
        ):
            raise ValueError("Codex profile gate names are unsafe.")
        if len(set(self.required_route_gates)) != len(self.required_route_gates):
            raise ValueError("Codex profile gate names must be unique.")
        if any(
            not isinstance(tool, str)
            or not _SAFE_TOKEN.fullmatch(tool)
            or tool not in _SUPPORTED_LOCAL_TOOLS
            for tool in self.local_tools
        ):
            raise ValueError("Codex profile local tool names are unsafe.")
        if len(set(self.local_tools)) != len(self.local_tools):
            raise ValueError("Codex profile local tool names must be unique.")
        if (
            not self.input_modalities
            or len(set(self.input_modalities)) != len(self.input_modalities)
            or any(modality not in _SUPPORTED_MODALITIES for modality in self.input_modalities)
        ):
            raise ValueError("Codex profile input modalities are invalid.")
        for value in (self.context_window_tokens, self.default_max_output_tokens, self.max_output_tokens):
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError("Codex profile numeric limits are invalid.")
        if self.default_max_output_tokens > self.max_output_tokens:
            raise ValueError("Codex profile output limits are invalid.")
        if self.context_window_tokens <= self.max_output_tokens:
            raise ValueError("Codex profile context limit must exceed output limit.")
        if self.compaction_mode not in {"remote_v1", "client_local", "none"}:
            raise ValueError("Codex profile compaction mode is invalid.")
        if self.compaction_mode == "remote_v1":
            if set(self.required_endpoints) != {"/v1/responses", "/v1/responses/compact"}:
                raise ValueError("Remote compaction requires the Responses/compact endpoint pair.")
            if "codex_compaction" not in self.required_route_gates:
                raise ValueError("Remote compaction requires the Codex compaction gate.")
            if self.auto_compaction_token_threshold is not None:
                raise ValueError("Remote compaction cannot declare a client-local threshold.")
        elif self.compaction_mode == "client_local":
            if len(self.required_endpoints) != 1 or "/v1/responses/compact" in self.required_endpoints:
                raise ValueError("Client-local compaction requires one non-compact endpoint.")
            if "codex_compaction" in self.required_route_gates:
                raise ValueError("Client-local compaction cannot require the remote compaction gate.")
            if (
                isinstance(self.auto_compaction_token_threshold, bool)
                or not isinstance(self.auto_compaction_token_threshold, int)
                or self.auto_compaction_token_threshold <= 0
                or self.auto_compaction_token_threshold >= self.context_window_tokens
            ):
                raise ValueError("Client-local compaction requires a bounded positive threshold.")
        else:
            if self.auto_compaction_token_threshold is not None:
                raise ValueError("No compaction mode cannot declare a threshold.")
            if "/v1/responses/compact" in self.required_endpoints or "codex_compaction" in self.required_route_gates:
                raise ValueError("No compaction mode cannot require remote compaction.")
        if "image_input" in self.required_route_gates and "image" not in self.input_modalities:
            raise ValueError("Image input gate requires image modality.")
        if "image" in self.input_modalities and "image_input" not in self.required_route_gates:
            raise ValueError("Image modality requires the image-input gate.")
        if "codex_client_tools" in self.required_route_gates and not self.local_tools:
            raise ValueError("Client-tool gate requires local tools.")
        if "codex_streaming_tool_events" in self.required_route_gates and "codex_client_tools" not in self.required_route_gates:
            raise ValueError("Streaming tool events require client tools.")
        if "codex_encrypted_reasoning_replay" in self.required_route_gates and not self.reasoning_replay:
            raise ValueError("Encrypted reasoning replay requires reasoning replay.")
        if self.reasoning_replay and "codex_encrypted_reasoning_replay" not in self.required_route_gates:
            raise ValueError("Reasoning replay requires its route gate.")
        if self.streaming_tool_events and "codex_streaming_tool_events" not in self.required_route_gates:
            raise ValueError("Streaming tool events require their route gate.")
        for field in ("reasoning_replay", "streaming_tool_events", "mocked_qualification", "live_qualification"):
            if type(getattr(self, field)) is not bool:
                raise ValueError(f"Codex profile {field} must be a strict boolean.")
        if len(self.fixture_sha256) != 64 or any(
            character not in "0123456789abcdef" for character in self.fixture_sha256
        ):
            raise ValueError("Codex profile fixture digest is invalid.")
        if not isinstance(self.credential_free_provider_fields, MappingProxyType):
            raise ValueError("Codex provider fields must be immutable.")
        if set(self.credential_free_provider_fields) - {
            "name",
            "wire_api",
            "requires_openai_auth",
            "supports_websockets",
        }:
            raise ValueError("Codex provider fields contain an unsupported value.")
        provider_fields = self.credential_free_provider_fields
        if set(provider_fields) != {"name", "wire_api", "requires_openai_auth", "supports_websockets"}:
            raise ValueError("Codex provider fields are incomplete.")
        if (
            type(provider_fields["name"]) is not str
            or not _SAFE_TOKEN.fullmatch(provider_fields["name"])
            or provider_fields["wire_api"] != self.wire_api
            or type(provider_fields["requires_openai_auth"]) is not bool
            or type(provider_fields["supports_websockets"]) is not bool
        ):
            raise ValueError("Codex provider fields are malformed.")
        if self.provider_kind != "openai" and provider_fields["requires_openai_auth"]:
            raise ValueError("Generic profile provider fields cannot require upstream auth.")
        try:
            date.fromisoformat(self.evidence_date)
        except (TypeError, ValueError) as exc:
            raise ValueError("Codex profile evidence date is invalid.") from exc
        if self.model_catalog_artifact is not None:
            try:
                parsed = json.loads(self.model_catalog_artifact)
            except (TypeError, json.JSONDecodeError) as exc:
                raise ValueError("Codex model catalog artifact must be JSON.") from exc
            canonical = json.dumps(parsed, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
            if canonical != self.model_catalog_artifact:
                raise ValueError("Codex model catalog artifact is not deterministic.")
            if not self.model_catalog_target or not _SAFE_TOKEN.fullmatch(self.model_catalog_target) or not self.model_catalog_target.endswith(".json"):
                raise ValueError("Codex model catalog target is unsafe.")
            _validate_catalog_artifact(
                parsed,
                public_model=self.public_model,
                context_window_tokens=self.context_window_tokens,
                auto_compaction_token_threshold=self.auto_compaction_token_threshold,
                input_modalities=self.input_modalities,
            )
        elif self.model_catalog_target is not None:
            raise ValueError("Codex model catalog target requires an artifact.")
        if self.catalog_source not in {"bundled", "replacement"}:
            raise ValueError("Codex model catalog source is invalid.")
        if self.catalog_source == "bundled" and (
            self.model_catalog_artifact is not None or self.model_catalog_target is not None
        ):
            raise ValueError("Bundled catalog profiles cannot carry replacement artifacts.")
        if self.catalog_source == "replacement" and (
            self.model_catalog_artifact is None or self.model_catalog_target is None
        ):
            raise ValueError("Replacement catalog profiles require an artifact and target.")


def _profile(**values: object) -> CodexQualificationProfile:
    fields = dict(values)
    fields["credential_free_provider_fields"] = MappingProxyType(
        dict(fields["credential_free_provider_fields"])
    )
    return CodexQualificationProfile(**fields)  # type: ignore[arg-type]


OPENAI_CODEX_PROFILE = _profile(
    profile_id=PROFILE_ID,
    metadata_version=PROFILE_METADATA_VERSION,
    cli_version="0.147.0",
    public_model="gpt-5.6-sol",
    upstream_model="gpt-5.6-sol",
    wire_api="responses",
    provider_kind="openai",
    provider_slug="openai",
    required_endpoints=("/v1/responses", "/v1/responses/compact"),
    required_route_gates=(
        "codex_request_envelope",
        "codex_client_tools",
        "codex_streaming_tool_events",
        "codex_encrypted_reasoning_replay",
        "codex_compaction",
    ),
    context_window_tokens=1_050_000,
    default_max_output_tokens=32_768,
    max_output_tokens=128_000,
    compaction_mode="remote_v1",
    reasoning_replay=True,
    streaming_tool_events=True,
    local_tools=("function", "custom"),
    input_modalities=("text",),
    auto_compaction_token_threshold=None,
    credential_free_provider_fields={
        "name": "OpenAI",
        "wire_api": "responses",
        "requires_openai_auth": False,
        "supports_websockets": False,
    },
    model_catalog_artifact=None,
    model_catalog_target=None,
    fixture_sha256=PROFILE_FIXTURE_SHA256,
    evidence_date="2026-08-18",
    mocked_qualification=True,
    live_qualification=False,
    profile_name="slaif",
    provider_display_name="OpenAI",
    client_module_id=CODEX_0147_CLIENT_MODULE_ID,
    client_module_version=CODEX_0147_CLIENT_MODULE_VERSION,
)


def _validate_registry(registry: Mapping[str, CodexQualificationProfile]) -> None:
    if not isinstance(registry, MappingProxyType):
        raise ValueError("Codex profile registry must be immutable.")
    seen: set[str] = set()
    for key, profile in registry.items():
        if not isinstance(profile, CodexQualificationProfile):
            raise ValueError("Codex profile registry contains an invalid definition.")
        if not isinstance(key, str) or key in seen or key != profile.profile_id:
            raise ValueError("Codex profile registry contains a duplicate or mismatched ID.")
        seen.add(key)


def validate_codex_profile_registry(
    registry: Mapping[str, CodexQualificationProfile],
) -> None:
    """Validate a complete registry for deterministic startup/test failures."""

    _validate_registry(registry)


CODEX_PROFILE_REGISTRY: Mapping[str, CodexQualificationProfile] = MappingProxyType(
    {OPENAI_CODEX_PROFILE.profile_id: OPENAI_CODEX_PROFILE}
)
_validate_registry(CODEX_PROFILE_REGISTRY)


def get_codex_profile(profile_id: str) -> CodexQualificationProfile | None:
    """Return a registered immutable profile, or ``None`` for unknown IDs."""

    if not isinstance(profile_id, str):
        return None
    return CODEX_PROFILE_REGISTRY.get(profile_id)


def build_codex_profile_declaration(profile_id: str) -> dict[str, object]:
    """Build the only route-owned declaration accepted for a registered profile."""

    profile = get_codex_profile(profile_id)
    if profile is None:
        raise ValueError("Unknown Codex qualification profile.")
    return {
        "version": profile.metadata_version,
        "profile_id": profile.profile_id,
        "fixture_sha256": profile.fixture_sha256,
    }


def validate_codex_profile_declaration(value: object) -> tuple[str, str | None]:
    """Validate the minimal v2 route declaration without granting authority."""

    if not isinstance(value, Mapping) or set(value) != {"version", "profile_id", "fixture_sha256"}:
        return "invalid", "codex_profile_declaration_invalid"
    if value.get("version") != PROFILE_METADATA_VERSION:
        return "invalid", "codex_profile_version_invalid"
    profile_id = value.get("profile_id")
    digest = value.get("fixture_sha256")
    if not isinstance(profile_id, str) or not _SAFE_ID.fullmatch(profile_id):
        return "invalid", "codex_profile_id_invalid"
    profile = get_codex_profile(profile_id)
    if profile is None:
        return "not_ready", "codex_profile_unknown"
    if digest != profile.fixture_sha256:
        return "invalid", "codex_profile_fixture_mismatch"
    return "ready", None


_FORBIDDEN_FIXTURE_KEYS = {
    "prompt", "output", "text", "description", "schema", "arguments", "result",
    "reasoning", "encrypted", "body", "request", "response", "url", "headers",
    "key", "cookie", "authorization", "environment", "workspace", "path", "metadata",
}
_STRUCTURAL_CONTAINER_KEYS = frozenset(
    {
        "event_sequence", "request_facts", "catalog_facts", "route_facts", "credential_facts",
        "accounting_facts", "phases", "relationships", "gates", "facts", "reservations",
        "ledgers", "text_only", "no_search", "no_parallel",
    }
)
_STRUCTURAL_STRING_KEYS = frozenset(
    {
        "phase", "relation", "taxonomy_id", "endpoint", "provider_kind", "model_rewrite",
        "gate", "status", "catalog_source", "ledger_status", "reservation_status",
    }
)
_STRUCTURAL_INTEGER_KEYS = frozenset(
    {
        "event_count", "request_index", "event_index", "input_tokens", "cached_tokens",
        "output_tokens", "reasoning_tokens", "total_tokens", "cost_nano_eur", "requests_used",
        "tokens_used",
    }
)


def sanitize_codex_fixture(
    value: object,
    *,
    allowed_types: frozenset[str],
) -> dict[str, object]:
    """Return a bounded structural fixture projection or reject unsafe input."""

    if (
        not isinstance(allowed_types, frozenset)
        or not allowed_types
        or any(
            not isinstance(item, str)
            or not _SAFE_TOKEN.fullmatch(item)
            or len(item) > 64
            for item in allowed_types
        )
    ):
        raise ValueError("Codex fixture structural vocabulary must be finite and immutable.")
    nodes = 0
    identifiers: dict[str, str] = {}

    def walk(node: object, *, depth: int = 0) -> object:
        nonlocal nodes
        nodes += 1
        if nodes > 512:
            raise ValueError("Codex fixture node count is too large.")
        if depth > 8:
            raise ValueError("Codex fixture nesting is too deep.")
        if isinstance(node, Mapping):
            output: dict[str, object] = {}
            for raw_key in sorted(node):
                raw_value = node[raw_key]
                if not isinstance(raw_key, str) or raw_key.lower() in _FORBIDDEN_FIXTURE_KEYS:
                    raise ValueError("Codex fixture contains prohibited content.")
                if raw_key not in {
                    "event_type", "field_type", "tool_type", "id", "count", "index", "enabled", "digest",
                    *_STRUCTURAL_CONTAINER_KEYS, *_STRUCTURAL_STRING_KEYS, *_STRUCTURAL_INTEGER_KEYS,
                }:
                    raise ValueError("Codex fixture contains arbitrary metadata.")
                if raw_key == "digest":
                    raise ValueError("Codex fixture input digest is not accepted.")
                if raw_key == "id":
                    if not isinstance(raw_value, str) or len(raw_value) > 128:
                        raise ValueError("Codex fixture ID is invalid.")
                    if any(marker in raw_value.lower() for marker in _SECRET_MARKERS):
                        raise ValueError("Codex fixture contains secret-looking content.")
                    if raw_value not in identifiers and len(identifiers) >= 64:
                        raise ValueError("Codex fixture ID count is too large.")
                    output[raw_key] = identifiers.setdefault(
                        raw_value, f"ID_{len(identifiers) + 1}"
                    )
                elif raw_key in {"event_type", "field_type", "tool_type"}:
                    if type(raw_value) is not str or raw_value not in allowed_types:
                        raise ValueError("Codex fixture type value is not allowlisted.")
                    output[raw_key] = raw_value
                elif raw_key in {"count", "index"}:
                    if type(raw_value) is not int or raw_value < 0 or raw_value > 1_000_000:
                        raise ValueError("Codex fixture count/index is invalid.")
                    output[raw_key] = raw_value
                elif raw_key in _STRUCTURAL_INTEGER_KEYS:
                    if type(raw_value) is not int or raw_value < 0 or raw_value > 1_000_000_000:
                        raise ValueError("Codex fixture structural number is invalid.")
                    output[raw_key] = raw_value
                elif raw_key in _STRUCTURAL_STRING_KEYS:
                    if (
                        not isinstance(raw_value, str)
                        or not _SAFE_TOKEN.fullmatch(raw_value)
                        or any(marker in raw_value.lower() for marker in _SECRET_MARKERS)
                    ):
                        raise ValueError("Codex fixture structural string is invalid.")
                    output[raw_key] = raw_value
                elif raw_key == "enabled":
                    if type(raw_value) is not bool:
                        raise ValueError("Codex fixture enabled value is invalid.")
                    output[raw_key] = raw_value
                elif raw_key in _STRUCTURAL_CONTAINER_KEYS:
                    output[raw_key] = walk(raw_value, depth=depth + 1)
                else:
                    output[raw_key] = walk(raw_value, depth=depth + 1)
            return output
        if isinstance(node, list):
            if len(node) > 128:
                raise ValueError("Codex fixture cardinality is too large.")
            return [walk(item, depth=depth + 1) for item in node]
        if isinstance(node, float) and not math.isfinite(node):
            raise ValueError("Codex fixture numeric value is not finite.")
        if isinstance(node, (bool, int, float)) or node is None:
            return node
        raise ValueError("Codex fixture contains prohibited content.")

    sanitized = walk(value)
    if not isinstance(sanitized, dict):
        raise ValueError("Codex fixture root must be an object.")
    canonical = json.dumps(sanitized, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    sanitized["digest"] = hashlib.sha256(canonical.encode()).hexdigest()
    return sanitized


def _safe_catalog_string(value: object, *, field: str) -> None:
    if not isinstance(value, str) or not value or len(value.encode("utf-8")) > 128:
        raise ValueError("Codex model catalog string is invalid.")
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ValueError("Codex model catalog contains control data.")
    if any(marker in value.lower() for marker in _SECRET_MARKERS) or "://" in value or "/" in value:
        raise ValueError("Codex model catalog contains unsafe string data.")
    allowed = _CATALOG_ENUMS.get(field)
    if allowed is not None and value not in allowed:
        raise ValueError("Codex model catalog enum is not allowlisted.")


def _safe_catalog_model(entry: object, *, public_model: str) -> None:
    required_fields = {"slug", "context_window", "auto_compact_token_limit", "input_modalities"}
    if (
        not isinstance(entry, Mapping)
        or not entry
        or not required_fields.issubset(entry)
        or set(entry) - _CATALOG_MODEL_FIELDS
    ):
        raise ValueError("Codex model catalog model entry is not allowlisted.")
    if entry.get("slug") != public_model:
        raise ValueError("Codex model catalog model slug is invalid.")
    for key, value in entry.items():
        if key == "input_modalities":
            if (
                not isinstance(value, list)
                or not value
                or len(value) > 2
                or len(set(value)) != len(value)
                or any(item not in _SUPPORTED_MODALITIES for item in value)
            ):
                raise ValueError("Codex model catalog modalities are invalid.")
        elif key == "supported_reasoning_levels":
            if (
                not isinstance(value, list)
                or not value
                or len(value) > 8
            ):
                raise ValueError("Codex model catalog reasoning levels are invalid.")
            efforts = [
                item.get("effort")
                for item in value
                if isinstance(item, Mapping)
                and set(item) in ({"effort"}, {"effort", "description"})
                and (
                    set(item) == {"effort"}
                    or (
                        isinstance(item.get("description"), str)
                        and len(item["description"].encode("utf-8")) <= 128
                        and not any(
                            ord(char) < 32 or ord(char) == 127
                            for char in item["description"]
                        )
                        and not any(
                            marker in item["description"].lower()
                            for marker in _SECRET_MARKERS
                        )
                        and "://" not in item["description"]
                        and "/" not in item["description"]
                    )
                )
            ]
            if len(efforts) != len(value) or len(set(efforts)) != len(efforts) or any(
                effort not in _CATALOG_ENUMS["default_reasoning_level"] for effort in efforts
            ):
                raise ValueError("Codex model catalog reasoning levels are invalid.")
        elif key == "truncation_policy":
            if not isinstance(value, Mapping) or set(value) != {"mode", "limit"}:
                raise ValueError("Codex model catalog truncation policy is invalid.")
            if value["mode"] not in {"bytes", "tokens"} or type(value["limit"]) is not int or value["limit"] < 0:
                raise ValueError("Codex model catalog truncation policy is invalid.")
        elif key in _CATALOG_ARRAY_FIELDS:
            if (
                not isinstance(value, list)
                or len(value) > 32
                or any(type(item) is not str or len(item) > 64 for item in value)
            ):
                raise ValueError("Codex model catalog array metadata is invalid.")
        elif key in _CATALOG_NULLABLE_FIELDS:
            if value is None:
                continue
            if key == "base_instructions":
                if value != "":
                    raise ValueError("Codex model catalog instructions are invalid.")
            elif key == "apply_patch_tool_type":
                if value not in _CATALOG_ENUMS["apply_patch_tool_type"]:
                    raise ValueError("Codex model catalog patch metadata is invalid.")
            elif key in {"availability_nux", "upgrade", "model_messages"}:
                raise ValueError("Codex model catalog nullable metadata is invalid.")
            else:
                _safe_catalog_string(value, field=key)
        elif key in _CATALOG_BOOLEAN_FIELDS:
            if type(value) is not bool:
                raise ValueError("Codex model catalog boolean is invalid.")
        elif key in _CATALOG_INTEGER_FIELDS:
            if type(value) is not int or value < 0:
                raise ValueError("Codex model catalog number is invalid.")
        elif key != "slug":
            _safe_catalog_string(value, field=key)


def _validate_catalog_artifact(
    catalog: object,
    *,
    public_model: str,
    context_window_tokens: int,
    auto_compaction_token_threshold: int | None,
    input_modalities: tuple[str, ...],
) -> None:
    if not isinstance(catalog, Mapping) or set(catalog) != _CATALOG_TOP_LEVEL_FIELDS:
        raise ValueError("Codex model catalog top-level shape is invalid.")
    models = catalog["models"]
    if not isinstance(models, list) or len(models) != 1:
        raise ValueError("Codex model catalog must contain exactly one model.")
    _safe_catalog_model(models[0], public_model=public_model)
    entry = models[0]
    if not isinstance(entry, Mapping):
        raise ValueError("Codex model catalog model entry is invalid.")
    if entry["context_window"] != context_window_tokens:
        raise ValueError("Codex model catalog context window does not match profile.")
    if entry["auto_compact_token_limit"] != auto_compaction_token_threshold:
        raise ValueError("Codex model catalog compaction threshold does not match profile.")
    if entry["input_modalities"] != list(input_modalities):
        raise ValueError("Codex model catalog modalities do not match profile.")
    if input_modalities == ("text",):
        if entry.get("supports_search_tool") is not False:
            raise ValueError("Codex text catalog search capability is unsafe.")
        if entry.get("supports_parallel_tool_calls") is not False:
            raise ValueError("Codex text catalog parallel calls are unsafe.")
        if entry.get("supports_reasoning_summaries") is not False:
            raise ValueError("Codex text catalog reasoning replay is unsafe.")
        if entry.get("apply_patch_tool_type") is not None:
            raise ValueError("Codex text catalog patch authority is unsafe.")
    _validate_catalog_size(catalog)


def _validate_catalog_size(node: object, *, depth: int = 0, budget: list[int] | None = None) -> None:
    if budget is None:
        budget = [0]
    budget[0] += 1
    if budget[0] > 256 or depth > 8:
        raise ValueError("Codex model catalog is too large or deeply nested.")
    if isinstance(node, Mapping):
        for key, value in node.items():
            if not isinstance(key, str) or len(key) > 64:
                raise ValueError("Codex model catalog key is invalid.")
            _validate_catalog_size(value, depth=depth + 1, budget=budget)
    elif isinstance(node, list):
        if len(node) > 32:
            raise ValueError("Codex model catalog list is too large.")
        for value in node:
            _validate_catalog_size(value, depth=depth + 1, budget=budget)
    elif isinstance(node, str):
        if len(node) > 128:
            raise ValueError("Codex model catalog string is too long.")
    elif isinstance(node, float) and not math.isfinite(node):
        raise ValueError("Codex model catalog contains a non-finite number.")
    elif node is not None and not isinstance(node, (bool, int, float)):
        raise ValueError("Codex model catalog contains unsupported data.")


# Candidate metadata is intentionally not placed in CODEX_PROFILE_REGISTRY.
# It can be rendered and verified in isolation, but cannot be selected by a
# route or CLI until the separately required live phase succeeds.
QWEN38_TEXT_CODEX_CANDIDATE = _profile(
    profile_id=QWEN38_TEXT_PROFILE_ID,
    metadata_version=PROFILE_METADATA_VERSION,
    cli_version="0.148.0",
    public_model="qwen3.8-27b-text",
    upstream_model="qwen3.8-27b",
    wire_api="responses",
    provider_kind="openai_compatible",
    provider_slug=None,
    required_endpoints=("/v1/responses",),
    required_route_gates=(
        "codex_request_envelope",
        "codex_client_tools",
        "codex_streaming_tool_events",
    ),
    context_window_tokens=150_000,
    default_max_output_tokens=8_192,
    max_output_tokens=24_576,
    compaction_mode="client_local",
    reasoning_replay=False,
    streaming_tool_events=True,
    local_tools=("function",),
    input_modalities=("text",),
    auto_compaction_token_threshold=125_000,
    credential_free_provider_fields={
        "name": "OpenAICompatible",
        "wire_api": "responses",
        "requires_openai_auth": False,
        "supports_websockets": False,
    },
    model_catalog_artifact=(
        '{"models":[{"additional_speed_tiers":[],"auto_compact_token_limit":125000,'
        '"availability_nux":null,"base_instructions":"","context_window":150000,'
        '"default_reasoning_level":"none","default_reasoning_summary":"none",'
        '"default_service_tier":null,"default_verbosity":null,"description":"Qwen3.8 text model",'
        '"display_name":"Qwen3.8 27B Text","effective_context_window_percent":83,'
        '"experimental_supported_tools":[],"input_modalities":["text"],"max_context_window":150000,'
        '"model_messages":null,"priority":0,"service_tiers":[],"shell_type":"shell_command",'
        '"slug":"qwen3.8-27b-text","support_verbosity":false,"supported_in_api":true,'
        '"supported_reasoning_levels":[{"description":"No reasoning","effort":"none"}],'
        '"supports_image_detail_original":false,"supports_parallel_tool_calls":false,'
        '"supports_reasoning_summaries":false,"supports_search_tool":false,'
        '"truncation_policy":{"limit":150000,"mode":"tokens"},"upgrade":null,'
        '"use_responses_lite":true,"visibility":"list","web_search_tool_type":"text"}]}'
    ),
    model_catalog_target="qwen3.8-27b-text.json",
    fixture_sha256=QWEN38_TEXT_PROFILE_FIXTURE_SHA256,
    evidence_date="2026-08-21",
    mocked_qualification=True,
    live_qualification=False,
    profile_name="qwen3_8_text",
    provider_display_name="Qwen3.8 text OpenAI-compatible",
    catalog_source="replacement",
)

# Vision candidate remains isolated from selectable registry state until the
# separately required live qualification phase succeeds.
QWEN38_VISION_CODEX_CANDIDATE = _profile(
    profile_id=QWEN38_VISION_PROFILE_ID,
    metadata_version=PROFILE_METADATA_VERSION,
    cli_version="0.148.0",
    public_model="qwen3.8-27b-vision",
    upstream_model="qwen3.8-27b",
    wire_api="responses",
    provider_kind="openai_compatible",
    provider_slug=None,
    required_endpoints=("/v1/responses",),
    required_route_gates=(
        "codex_request_envelope",
        "codex_client_tools",
        "codex_streaming_tool_events",
        "image_input",
    ),
    context_window_tokens=100_000,
    default_max_output_tokens=8_192,
    max_output_tokens=24_576,
    compaction_mode="client_local",
    reasoning_replay=False,
    streaming_tool_events=True,
    local_tools=("function",),
    input_modalities=("text", "image"),
    auto_compaction_token_threshold=75_000,
    credential_free_provider_fields={
        "name": "OpenAICompatible",
        "wire_api": "responses",
        "requires_openai_auth": False,
        "supports_websockets": False,
    },
    model_catalog_artifact=(
        '{"models":[{"additional_speed_tiers":[],"auto_compact_token_limit":75000,'
        '"availability_nux":null,"base_instructions":"","context_window":100000,'
        '"default_reasoning_level":"none","default_reasoning_summary":"none",'
        '"default_service_tier":null,"default_verbosity":null,'
        '"description":"Qwen3.8 vision model","display_name":"Qwen3.8 27B Vision",'
        '"effective_context_window_percent":83,"experimental_supported_tools":[],'
        '"input_modalities":["text","image"],"max_context_window":100000,'
        '"model_messages":null,"priority":0,"service_tiers":[],'
        '"shell_type":"shell_command","slug":"qwen3.8-27b-vision",'
        '"support_verbosity":false,"supported_in_api":true,'
        '"supported_reasoning_levels":[{"description":"No reasoning","effort":"none"}],'
        '"supports_image_detail_original":false,"supports_parallel_tool_calls":false,'
        '"supports_reasoning_summaries":false,"supports_search_tool":false,'
        '"truncation_policy":{"limit":100000,"mode":"tokens"},"upgrade":null,'
        '"use_responses_lite":true,"visibility":"list","web_search_tool_type":"text"}]}'
    ),
    model_catalog_target="qwen3.8-27b-vision.json",
    fixture_sha256=QWEN38_VISION_PROFILE_FIXTURE_SHA256,
    evidence_date="2026-08-21",
    mocked_qualification=True,
    live_qualification=False,
    profile_name="qwen3_8_vision",
    provider_display_name="Qwen3.8 vision OpenAI-compatible",
    catalog_source="replacement",
)
