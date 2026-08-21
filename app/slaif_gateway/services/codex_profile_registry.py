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

PROFILE_ID = "openai-gpt-5.6-sol-codex-0.147-v1"
PROFILE_METADATA_VERSION = 2
PROFILE_FIXTURE_SHA256 = "436ea530b9f984807dfc73ccce0b5233d0a3047ceb10ef942fbc8d12cac47432"

_SAFE_ID = re.compile(r"^[a-z0-9][a-z0-9.-]{2,95}$")
_SAFE_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SAFE_DISPLAY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._-]{0,127}$")
_SAFE_ENDPOINT = re.compile(r"^/v1/[A-Za-z0-9._{}-]+(?:/[A-Za-z0-9._{}-]+)*$")
_SAFE_GATE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_FORBIDDEN_CATALOG_KEYS = {
    "prompt", "output", "tool", "tools", "reasoning", "encrypted", "request", "response",
    "url", "headers", "authorization", "cookie", "secret", "token", "environment", "workspace",
}
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

    def __post_init__(self) -> None:
        if not _SAFE_ID.fullmatch(self.profile_id):
            raise ValueError("Codex profile ID is not safely bounded.")
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
        if self.provider_kind not in {"openai", "openai_compatible"}:
            raise ValueError("Codex profile provider kind is unsupported.")
        if self.provider_slug is not None and not _SAFE_ID.fullmatch(self.provider_slug):
            raise ValueError("Codex profile provider slug is unsafe.")
        if not self.required_endpoints or any(
            not isinstance(endpoint, str) or not _SAFE_ENDPOINT.fullmatch(endpoint)
            for endpoint in self.required_endpoints
        ) or len(set(self.required_endpoints)) != len(self.required_endpoints):
            raise ValueError("Codex profile endpoint set must be non-empty and unique.")
        if any(not isinstance(gate, str) or not _SAFE_GATE.fullmatch(gate) for gate in self.required_route_gates):
            raise ValueError("Codex profile gate names are unsafe.")
        if len(set(self.required_route_gates)) != len(self.required_route_gates):
            raise ValueError("Codex profile gate names must be unique.")
        if any(not isinstance(tool, str) or not _SAFE_TOKEN.fullmatch(tool) for tool in self.local_tools):
            raise ValueError("Codex profile local tool names are unsafe.")
        if len(set(self.local_tools)) != len(self.local_tools):
            raise ValueError("Codex profile local tool names must be unique.")
        for value in (self.context_window_tokens, self.default_max_output_tokens, self.max_output_tokens):
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError("Codex profile numeric limits are invalid.")
        if self.default_max_output_tokens > self.max_output_tokens:
            raise ValueError("Codex profile output limits are invalid.")
        if self.context_window_tokens <= self.max_output_tokens:
            raise ValueError("Codex profile context limit must exceed output limit.")
        if self.compaction_mode not in {"remote_v1", "client_local", "none"}:
            raise ValueError("Codex profile compaction mode is invalid.")
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
            _validate_catalog_node(parsed)
        elif self.model_catalog_target is not None:
            raise ValueError("Codex model catalog target requires an artifact.")


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


def sanitize_codex_fixture(value: object) -> dict[str, object]:
    """Return a bounded structural fixture projection or reject unsafe input."""

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
            for raw_key, raw_value in node.items():
                if not isinstance(raw_key, str) or raw_key.lower() in _FORBIDDEN_FIXTURE_KEYS:
                    raise ValueError("Codex fixture contains prohibited content.")
                if raw_key not in {"event_type", "field_type", "tool_type", "id", "count", "index", "enabled", "digest"}:
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
        if isinstance(node, str) and len(node) <= 64 and " " not in node and "/" not in node and "://" not in node:
            lowered = node.lower()
            if any(marker in lowered for marker in _SECRET_MARKERS) or lowered in {
                "prompt", "output", "schema", "arguments", "results", "reasoning"
            }:
                raise ValueError("Codex fixture contains secret-looking content.")
            return node
        raise ValueError("Codex fixture contains prohibited content.")

    sanitized = walk(value)
    if not isinstance(sanitized, dict):
        raise ValueError("Codex fixture root must be an object.")
    canonical = json.dumps(sanitized, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    sanitized["digest"] = hashlib.sha256(canonical.encode()).hexdigest()
    return sanitized


def _validate_catalog_node(node: object, *, depth: int = 0) -> None:
    if depth > 8:
        raise ValueError("Codex model catalog artifact is too deeply nested.")
    if isinstance(node, Mapping):
        for key, value in node.items():
            lowered_key = key.lower() if isinstance(key, str) else ""
            if not isinstance(key, str) or lowered_key in _FORBIDDEN_CATALOG_KEYS or any(
                term in lowered_key for term in ("prompt", "output", "tool", "reason", "schema", "argument", "result")
            ):
                raise ValueError("Codex model catalog contains prohibited fields.")
            _validate_catalog_node(value, depth=depth + 1)
        return
    if isinstance(node, list):
        if len(node) > 128:
            raise ValueError("Codex model catalog is too large.")
        for value in node:
            _validate_catalog_node(value, depth=depth + 1)
        return
    if isinstance(node, str):
        lowered = node.lower()
        if any(marker in lowered for marker in _SECRET_MARKERS) or "://" in node or "/" in node:
            raise ValueError("Codex model catalog contains unsafe string data.")
        return
    if isinstance(node, float) and not math.isfinite(node):
        raise ValueError("Codex model catalog contains a non-finite number.")
    if node is not None and not isinstance(node, (bool, int, float)):
        raise ValueError("Codex model catalog contains unsupported data.")
