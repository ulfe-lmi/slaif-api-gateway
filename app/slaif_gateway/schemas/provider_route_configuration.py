"""Strict, versioned, NON-secret provider/route configuration files (objective 199).

Two file contracts shared by the ``providers`` and ``routes`` CLI groups:

1. A capabilities file (``--capabilities-file``): a COMPLETE replacement
   capabilities document for a model route.
2. A route update plan file (``routes update --dry-run``/``--execute``):
   reviewed NON-secret data for a stable-ID single-row route update.

Neither file ever contains credentials, provider secret values, key
material, or ORM/Settings dumps. Files are strict version-1 JSON: unknown
or duplicate fields, wrong types, non-finite constants, and oversized
payloads are rejected with fixed safe messages that never echo file
bodies, paths, or operator-supplied values.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from slaif_gateway.modules.servers.completion_service.profiles import (
    PROFILE_KEY,
    load_profile,
    profile_id_from_capabilities,
)
from slaif_gateway.modules.servers.local_coding.contract import (
    LOCAL_CODING_ROUTE_CAPABILITY_KEY,
)
from slaif_gateway.modules.servers.local_coding_vllm.contract import (
    VLLM_ROUTE_CAPABILITY_KEY,
)
from slaif_gateway.modules.servers.upstream_llm.profiles import (
    CAPABILITY_KEY as UPSTREAM_LLM_CAPABILITY_KEY,
    validate_route as validate_upstream_llm_route,
)
from slaif_gateway.services.audio_route_capabilities import (
    AUDIO_ENDPOINT_CAPABILITIES_KEY,
    KNOWN_AUDIO_ENDPOINT_CAPABILITIES,
)
from slaif_gateway.services.chat_completion_route_capabilities import (
    CHAT_COMPLETIONS_CAPABILITIES_KEY,
    KNOWN_CHAT_COMPLETION_CAPABILITIES,
    validate_chat_completion_capability_block,
)
from slaif_gateway.services.embeddings_route_capabilities import (
    EMBEDDINGS_CAPABILITIES_KEY,
    EMBEDDINGS_CAPABILITY_DIMENSIONS,
    EMBEDDINGS_CAPABILITY_ENABLED,
)
from slaif_gateway.services.external_tool_policy_contract import (
    DEFAULT_EXTERNAL_TOOL_OPERATOR_CEILINGS,
    ExternalToolOperatorCeilings,
    parse_route_external_tool_policy,
)
from slaif_gateway.services.media_input_estimation import (
    validate_media_input_estimation_block,
)
from slaif_gateway.services.realtime_route_capabilities import (
    REALTIME_CAPABILITIES_KEY,
    REALTIME_CAPABILITY_AUDIO,
    REALTIME_CAPABILITY_DIRECT_PROVIDER_EXPOSURE_ACCEPTED,
    REALTIME_CAPABILITY_TRANSCRIPTION,
    REALTIME_CAPABILITY_WEBRTC_CLIENT_SECRETS,
)
from slaif_gateway.services.responses_route_capabilities import (
    CODEX_COMPACTION_COMPATIBLE_ROUTE_IDS_KEY,
    CODEX_LIMITS_KEY,
    KNOWN_RESPONSES_CAPABILITIES,
    RESPONSES_CAPABILITIES_KEY,
    parse_codex_compaction_compatible_route_ids,
    parse_codex_route_limits,
    validate_responses_capability_block,
)
from slaif_gateway.utils.redaction import (
    _BEARER_PATTERN,
    _GATEWAY_KEY_TEXT_PATTERN,
    _PROVIDER_KEY_PATTERN,
    _SENSITIVE_ASSIGNMENT_PATTERN,
)

# Bounded file envelopes. The capabilities file wraps one capabilities
# document; the route update plan wraps capabilities plus identity fields.
CAPABILITIES_FILE_MAX_BYTES = 64 * 1024
ROUTE_PLAN_FILE_MAX_BYTES = 128 * 1024

CAPABILITIES_FILE_SCHEMA_VERSION = 1
ROUTE_PLAN_SCHEMA_VERSION = 1

_UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
_HEX64_RE = re.compile(r"^[0-9a-fA-F]{64}$")

# The finite set of contract-defined top-level capability groups.
KNOWN_CAPABILITY_GROUPS = frozenset(
    {
        CHAT_COMPLETIONS_CAPABILITIES_KEY,
        RESPONSES_CAPABILITIES_KEY,
        CODEX_LIMITS_KEY,
        CODEX_COMPACTION_COMPATIBLE_ROUTE_IDS_KEY,
        "media_input_estimation",
        PROFILE_KEY,
        "external_tools",
        "vllm_chat_video",
        AUDIO_ENDPOINT_CAPABILITIES_KEY,
        EMBEDDINGS_CAPABILITIES_KEY,
        REALTIME_CAPABILITIES_KEY,
    }
)

# Contract-defined groups outside this configuration surface. Existing
# routes may already carry them (upstream-LLM transport profile, Local
# Coding config-secret groups); a reviewed update PRESERVES them instead
# of re-authoring them. The upstream-LLM group keeps its existing pure
# transport-contract check; the Local Coding groups carry configuration
# secrets, are conflict-checked only here, and remain enforced fail-closed
# by their runtime contract parsers.
PRESERVED_CONTRACT_GROUPS = frozenset(
    {
        LOCAL_CODING_ROUTE_CAPABILITY_KEY,
        VLLM_ROUTE_CAPABILITY_KEY,
        UPSTREAM_LLM_CAPABILITY_KEY,
    }
)

_KNOWN_EMBEDDINGS_CAPABILITIES = frozenset(
    {EMBEDDINGS_CAPABILITY_ENABLED, EMBEDDINGS_CAPABILITY_DIMENSIONS}
)
_KNOWN_REALTIME_CAPABILITIES = frozenset(
    {
        REALTIME_CAPABILITY_AUDIO,
        REALTIME_CAPABILITY_WEBRTC_CLIENT_SECRETS,
        REALTIME_CAPABILITY_TRANSCRIPTION,
        REALTIME_CAPABILITY_DIRECT_PROVIDER_EXPOSURE_ACCEPTED,
    }
)

# Known secret shapes reused from the existing redaction contract. These are
# finite, recognized authentication/provider secret patterns - not a general
# content sanitizer.
_SECRET_SHAPE_PATTERNS = (
    _GATEWAY_KEY_TEXT_PATTERN,
    _BEARER_PATTERN,
    _PROVIDER_KEY_PATTERN,
    _SENSITIVE_ASSIGNMENT_PATTERN,
)


class ProviderRouteConfigError(ValueError):
    """A safe, fixed-message provider/route configuration error.

    Messages use fixed vocabulary only; they never echo file bodies, paths,
    field values, or operator-supplied input.
    """


class ProviderRouteStaleError(ProviderRouteConfigError):
    """The reviewed expected pre-state no longer matches the live row."""


def _fail(field: str, message: str) -> None:
    raise ProviderRouteConfigError(f"{field}: {message}")


_ABSENT = object()


def _strict_pairs_hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    seen: set[str] = set()
    for key, _value in pairs:
        if not isinstance(key, str):
            _fail("file", "JSON object keys must be strings.")
        if key in seen:
            _fail("file", "JSON object contains a duplicate key.")
        seen.add(key)
    return dict(pairs)


def _strict_constant(name: str) -> Any:
    _fail("file", "JSON constants such as NaN or Infinity are not allowed.")


def _load_strict_object(data: bytes, cap: int, label: str) -> dict[str, Any]:
    if len(data) > cap:
        _fail("file", f"{label} exceeds the bounded size.")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        _fail("file", f"{label} must be valid UTF-8 JSON.")
    try:
        value = json.loads(
            text,
            object_pairs_hook=_strict_pairs_hook,
            parse_constant=_strict_constant,
            parse_float=Decimal,
        )
    except ProviderRouteConfigError:
        raise
    except json.JSONDecodeError:
        _fail("file", f"{label} is not valid JSON.")
    if not isinstance(value, dict):
        _fail("file", "Top level must be a JSON object.")
    return value


def _check_no_known_secret_shapes(document: Any, field: str) -> None:
    """Refuse a RECOGNIZED secret shape anywhere in reviewed configuration.

    Reuses the existing redaction patterns (gateway key text, bearer
    tokens, provider keys, sensitive assignments). A matched shape fails
    with a fixed safe explanation instead of being stored or echoed. This
    is known-shape protection, not universal content sanitization.
    """

    def _contains(value: Any) -> bool:
        if isinstance(value, str):
            return any(pattern.search(value) for pattern in _SECRET_SHAPE_PATTERNS)
        if isinstance(value, dict):
            return any(_contains(item) for item in value.values())
        if isinstance(value, (list, tuple)):
            return any(_contains(item) for item in value)
        return False

    if _contains(document):
        _fail(field, "Value carries a recognized secret shape.")


def _require_bool_block(raw: Any, group: str, known: frozenset[str]) -> dict[str, bool]:
    if not isinstance(raw, dict):
        _fail(group, "Value must be a JSON object of boolean flags.")
    if not raw:
        _fail(group, "Object must not be empty.")
    extra = sorted(set(raw) - known)
    if extra:
        _fail(group, "Object contains unsupported flags.")
    for name, value in raw.items():
        if not isinstance(value, bool):
            _fail(f"{group}.{name}", "Value must be a boolean.")
    return dict(raw)


def _validate_codex_compaction_group(raw: Any) -> None:
    try:
        parse_codex_compaction_compatible_route_ids(
            {CODEX_COMPACTION_COMPATIBLE_ROUTE_IDS_KEY: raw}
        )
    except Exception:
        _fail(
            CODEX_COMPACTION_COMPATIBLE_ROUTE_IDS_KEY,
            "Value must be a bounded list of route UUID strings."
        )


def _validate_vllm_chat_video_group(raw: Any, capabilities: dict[str, Any]) -> None:
    from slaif_gateway.modules.servers.vllm_chat_video import parse_video_frames

    try:
        parse_video_frames(capabilities)
    except ValueError:
        _fail("vllm_chat_video", "Value must satisfy the native video contract.")
    _ = raw


def validate_capabilities_document(
    capabilities: Any,
    *,
    external_tool_ceilings: ExternalToolOperatorCeilings = (
        DEFAULT_EXTERNAL_TOOL_OPERATOR_CEILINGS
    ),
) -> dict[str, Any]:
    """Strict config-time validation of a COMPLETE capabilities document.

    Reuses the existing pure parsers/validators for every contract-defined
    group; unknown groups, wrong types, unknown flags, invalid numeric
    relationships, and media ceilings are all refused here, before any
    write. This validates CONFIGURATION, not credential/model readiness.
    """
    if not isinstance(capabilities, dict):
        _fail("capabilities", "Value must be a JSON object.")
    if not capabilities:
        _fail("capabilities", "Object must not be empty.")
    extra = sorted(set(capabilities) - KNOWN_CAPABILITY_GROUPS - PRESERVED_CONTRACT_GROUPS)
    if extra:
        _fail("capabilities", "Object contains unsupported groups.")
    _check_no_known_secret_shapes(capabilities, "capabilities")

    for group in (
        AUDIO_ENDPOINT_CAPABILITIES_KEY,
        EMBEDDINGS_CAPABILITIES_KEY,
        REALTIME_CAPABILITIES_KEY,
    ):
        if group in capabilities:
            known = {
                AUDIO_ENDPOINT_CAPABILITIES_KEY: KNOWN_AUDIO_ENDPOINT_CAPABILITIES,
                EMBEDDINGS_CAPABILITIES_KEY: _KNOWN_EMBEDDINGS_CAPABILITIES,
                REALTIME_CAPABILITIES_KEY: _KNOWN_REALTIME_CAPABILITIES,
            }[group]
            _require_bool_block(capabilities[group], group, known)

    if CHAT_COMPLETIONS_CAPABILITIES_KEY in capabilities:
        try:
            validate_chat_completion_capability_block(
                capabilities[CHAT_COMPLETIONS_CAPABILITIES_KEY]
            )
        except Exception:
            _fail(
                CHAT_COMPLETIONS_CAPABILITIES_KEY,
                "Value must contain known boolean flags only."
            )
    if RESPONSES_CAPABILITIES_KEY in capabilities:
        try:
            validate_responses_capability_block(capabilities[RESPONSES_CAPABILITIES_KEY])
        except Exception:
            _fail(
                RESPONSES_CAPABILITIES_KEY,
                "Value must contain known boolean flags only."
            )
    if CODEX_LIMITS_KEY in capabilities:
        try:
            parse_codex_route_limits({CODEX_LIMITS_KEY: capabilities[CODEX_LIMITS_KEY]})
        except Exception:
            _fail(
                CODEX_LIMITS_KEY,
                "Value must set all three positive integer limits in order."
            )
    if CODEX_COMPACTION_COMPATIBLE_ROUTE_IDS_KEY in capabilities:
        _validate_codex_compaction_group(capabilities[CODEX_COMPACTION_COMPATIBLE_ROUTE_IDS_KEY])
    if "media_input_estimation" in capabilities:
        try:
            validate_media_input_estimation_block(capabilities["media_input_estimation"])
        except Exception:
            _fail(
                "media_input_estimation",
                "Value must be a version-1 envelope within the engine ceilings."
            )
    if PROFILE_KEY in capabilities:
        try:
            profile_id = profile_id_from_capabilities(
                {PROFILE_KEY: capabilities[PROFILE_KEY]}
            )
            load_profile(profile_id)
        except Exception:
            _fail(PROFILE_KEY, "Value must be a valid available profile selector.")
        if (
            LOCAL_CODING_ROUTE_CAPABILITY_KEY in capabilities
            or VLLM_ROUTE_CAPABILITY_KEY in capabilities
            or "vllm_chat_video" in capabilities
        ):
            _fail(PROFILE_KEY, "Value conflicts with an exclusive transport selector.")
    if UPSTREAM_LLM_CAPABILITY_KEY in capabilities:
        try:
            validate_upstream_llm_route(capabilities)
        except Exception:
            _fail(
                UPSTREAM_LLM_CAPABILITY_KEY,
                "Value must satisfy the native upstream-LLM transport contract."
            )
    if "external_tools" in capabilities:
        parsed = parse_route_external_tool_policy(
            capabilities["external_tools"],
            ceilings=external_tool_ceilings,
        )
        if not parsed.valid or parsed.policy is None:
            _fail("external_tools", "Value must be a valid bounded route policy.")
    if "vllm_chat_video" in capabilities:
        _validate_vllm_chat_video_group(capabilities["vllm_chat_video"], capabilities)

    return dict(capabilities)


def parse_capabilities_file(data: bytes) -> dict[str, Any]:
    """Read and strictly validate one capabilities file payload."""
    document = _load_strict_object(
        data, CAPABILITIES_FILE_MAX_BYTES, "Capabilities file"
    )
    known = {"schema_version", "capabilities"}
    extra = sorted(str(k) for k in set(document) - known)
    if extra:
        _fail("schema", "Document contains unsupported fields.")
    version = document.get("schema_version", _ABSENT)
    if version is _ABSENT:
        _fail("schema_version", "Field is required.")
    if type(version) is not int or version != CAPABILITIES_FILE_SCHEMA_VERSION:
        _fail("schema_version", "Value must be exactly the current schema version.")
    capabilities = document.get("capabilities", _ABSENT)
    if capabilities is _ABSENT:
        _fail("capabilities", "Field is required.")
    return validate_capabilities_document(capabilities)


@dataclass(frozen=True, slots=True)
class CapabilityPatch:
    """Typed partial capability leaves (explicit leaves only)."""

    codex_limits: dict[str, int] | None = None
    media_input_estimation: dict[str, int] | None = None
    chat_completions: dict[str, bool] | None = None
    responses: dict[str, bool] | None = None
    completion_service: dict[str, object] | None | object = _ABSENT  # None = clear

    def is_empty(self) -> bool:
        return (
            self.codex_limits is None
            and self.media_input_estimation is None
            and self.chat_completions is None
            and self.responses is None
            and self.completion_service is _ABSENT
        )


_CODEX_PATCH_FIELDS = frozenset(
    {"context_window_tokens", "default_max_output_tokens", "max_output_tokens"}
)
_MEDIA_PATCH_FIELDS = frozenset({"image_tokens", "video_tokens", "video_frames"})


def parse_capability_patch(document: Any) -> CapabilityPatch:
    """Strict parse of the typed partial capability patch.

    Only explicit leaves are accepted; omission means preserve, not
    false/null/default. ``completion_service`` may be the complete
    selector object or explicit null (clear the selector). No arbitrary
    dotted paths, regex, or code.
    """
    if document is _ABSENT or document is None:
        return CapabilityPatch()
    if not isinstance(document, dict):
        _fail("capability_patch", "Value must be a JSON object.")
    known = {
        CODEX_LIMITS_KEY,
        "media_input_estimation",
        CHAT_COMPLETIONS_CAPABILITIES_KEY,
        RESPONSES_CAPABILITIES_KEY,
        PROFILE_KEY,
    }
    extra = sorted(set(document) - known)
    if extra:
        _fail("capability_patch", "Object contains unsupported groups.")
    _check_no_known_secret_shapes(document, "capability_patch")

    codex_limits: dict[str, int] | None = None
    if CODEX_LIMITS_KEY in document:
        raw = document[CODEX_LIMITS_KEY]
        if not isinstance(raw, dict) or not raw:
            _fail(CODEX_LIMITS_KEY, "Value must be a non-empty object of integer leaves.")
        if set(raw) - _CODEX_PATCH_FIELDS:
            _fail(CODEX_LIMITS_KEY, "Object contains unsupported fields.")
        for name, value in raw.items():
            if type(value) is not int or value <= 0:
                _fail(f"{CODEX_LIMITS_KEY}.{name}", "Value must be a positive integer.")
        codex_limits = dict(raw)

    media: dict[str, int] | None = None
    if "media_input_estimation" in document:
        raw = document["media_input_estimation"]
        if not isinstance(raw, dict) or not raw:
            _fail(
                "media_input_estimation",
                "Value must be a non-empty object of integer leaves."
            )
        if set(raw) - _MEDIA_PATCH_FIELDS:
            _fail("media_input_estimation", "Object contains unsupported fields.")
        for name, value in raw.items():
            if type(value) is not int or value <= 0:
                _fail(
                    f"media_input_estimation.{name}", "Value must be a positive integer."
                )
        media = dict(raw)

    chat = None
    if CHAT_COMPLETIONS_CAPABILITIES_KEY in document:
        chat = _require_bool_block(
            document[CHAT_COMPLETIONS_CAPABILITIES_KEY],
            CHAT_COMPLETIONS_CAPABILITIES_KEY,
            KNOWN_CHAT_COMPLETION_CAPABILITIES,
        )
    responses = None
    if RESPONSES_CAPABILITIES_KEY in document:
        responses = _require_bool_block(
            document[RESPONSES_CAPABILITIES_KEY],
            RESPONSES_CAPABILITIES_KEY,
            KNOWN_RESPONSES_CAPABILITIES,
        )

    completion_service: dict[str, object] | None | object = _ABSENT
    if PROFILE_KEY in document:
        raw = document[PROFILE_KEY]
        if raw is None:
            completion_service = None
        else:
            try:
                profile_id = profile_id_from_capabilities({PROFILE_KEY: raw})
                load_profile(profile_id)
            except Exception:
                _fail(PROFILE_KEY, "Value must be a valid available profile selector.")
            completion_service = dict(raw)

    patch = CapabilityPatch(
        codex_limits=codex_limits,
        media_input_estimation=media,
        chat_completions=chat,
        responses=responses,
        completion_service=completion_service,
    )
    if patch.is_empty():
        _fail("capability_patch", "Object must contain at least one explicit leaf.")
    return patch


def merge_capability_patch(
    current: dict[str, Any] | None, patch: CapabilityPatch
) -> dict[str, Any]:
    """Merge ONLY explicit leaves, deeply preserving all siblings.

    A codex_limits/media leaf updates the sibling block in place (an
    incomplete merged codex block is refused later by the strict numeric
    contract, never silently completed). completion_service null clears
    the selector.
    """
    merged = dict(current or {})
    if patch.codex_limits is not None:
        block = dict(merged.get(CODEX_LIMITS_KEY) or {})
        block.update(patch.codex_limits)
        merged[CODEX_LIMITS_KEY] = block
    if patch.media_input_estimation is not None:
        block = dict(merged.get("media_input_estimation") or {})
        block.update(patch.media_input_estimation)
        merged["media_input_estimation"] = block
    if patch.chat_completions is not None:
        block = dict(merged.get(CHAT_COMPLETIONS_CAPABILITIES_KEY) or {})
        block.update(patch.chat_completions)
        merged[CHAT_COMPLETIONS_CAPABILITIES_KEY] = block
    if patch.responses is not None:
        block = dict(merged.get(RESPONSES_CAPABILITIES_KEY) or {})
        block.update(patch.responses)
        merged[RESPONSES_CAPABILITIES_KEY] = block
    if patch.completion_service is not _ABSENT:
        if patch.completion_service is None:
            merged.pop(PROFILE_KEY, None)
        else:
            merged[PROFILE_KEY] = dict(patch.completion_service)
    return merged


@dataclass(frozen=True, slots=True)
class RouteUpdatePlan:
    """A typed, non-secret route update plan (reviewed data, not authority)."""

    route_id: str
    requested_model: str
    match_type: str
    endpoint: str
    provider: str
    upstream_model: str | None
    priority: int
    visible_in_models: bool
    supports_streaming: bool
    enabled: bool
    notes: str | None
    capabilities_mode: str  # "unchanged" | "partial" | "full-replacement"
    capabilities: dict[str, Any] | None
    capability_patch: CapabilityPatch
    expected_configuration_fingerprint: str
    preview: dict[str, Any] | None = None


def _require_str(document: dict[str, Any], name: str) -> str:
    value = document.get(name, _ABSENT)
    if value is _ABSENT:
        _fail(name, "Field is required.")
    if not isinstance(value, str) or not value.strip():
        _fail(name, "Value must be a non-empty string.")
    return value


def _require_bool(document: dict[str, Any], name: str) -> bool:
    value = document.get(name, _ABSENT)
    if value is _ABSENT:
        _fail(name, "Field is required.")
    if not isinstance(value, bool):
        _fail(name, "Value must be a boolean.")
    return value


def parse_route_update_plan_document(document: Any) -> RouteUpdatePlan:
    """Strictly parse one route update plan document."""
    if not isinstance(document, dict):
        _fail("file", "Top level must be a JSON object.")
    version = document.get("schema_version", _ABSENT)
    if type(version) is not int or version != ROUTE_PLAN_SCHEMA_VERSION:
        _fail("schema_version", "Value must be exactly the current schema version.")
    known = {
        "schema_version",
        "route_id",
        "requested_model",
        "match_type",
        "endpoint",
        "provider",
        "upstream_model",
        "priority",
        "visible_in_models",
        "supports_streaming",
        "enabled",
        "notes",
        "capabilities_mode",
        "capabilities",
        "capability_patch",
        "expected_configuration_fingerprint",
        "preview",
    }
    extra = sorted(str(k) for k in set(document) - known)
    if extra:
        _fail("schema", "Document contains unsupported fields.")
    _check_no_known_secret_shapes(document, "plan")

    route_id = _require_str(document, "route_id")
    if not _UUID_RE.match(route_id):
        _fail("route_id", "Value must be a UUID string.")
    requested_model = _require_str(document, "requested_model")
    match_type = _require_str(document, "match_type")
    if match_type not in {"exact", "prefix", "glob"}:
        _fail("match_type", "Value must be exact, prefix, or glob.")
    endpoint = _require_str(document, "endpoint")
    provider = _require_str(document, "provider")
    raw_upstream = document.get("upstream_model", _ABSENT)
    if raw_upstream is _ABSENT:
        _fail("upstream_model", "Field is required.")
    if raw_upstream is not None and (
        not isinstance(raw_upstream, str) or not raw_upstream.strip()
    ):
        _fail("upstream_model", "Value must be null or a non-empty string.")
    priority = document.get("priority", _ABSENT)
    if priority is _ABSENT:
        _fail("priority", "Field is required.")
    if type(priority) is not int or priority < 0:
        _fail("priority", "Value must be a non-negative integer.")
    visible = _require_bool(document, "visible_in_models")
    streaming = _require_bool(document, "supports_streaming")
    enabled = _require_bool(document, "enabled")
    raw_notes = document.get("notes", _ABSENT)
    if raw_notes is _ABSENT:
        _fail("notes", "Field is required.")
    if raw_notes is not None and (not isinstance(raw_notes, str) or not raw_notes.strip()):
        _fail("notes", "Value must be null or a non-empty string.")

    mode = _require_str(document, "capabilities_mode")
    if mode not in {"unchanged", "partial", "full-replacement"}:
        _fail("capabilities_mode", "Value must be unchanged, partial, or full-replacement.")
    raw_capabilities = document.get("capabilities", _ABSENT)
    raw_patch = document.get("capability_patch", _ABSENT)
    capabilities = None
    if mode == "full-replacement":
        if raw_capabilities is _ABSENT:
            _fail("capabilities", "Field is required for full replacement.")
        capabilities = validate_capabilities_document(raw_capabilities)
        if raw_patch is not _ABSENT and raw_patch is not None:
            _fail("capability_patch", "Cannot combine full replacement with a patch.")
    elif mode == "partial":
        if raw_patch is _ABSENT or raw_patch is None:
            _fail("capability_patch", "Field is required for a partial patch.")
        if raw_capabilities is not _ABSENT and raw_capabilities is not None:
            _fail("capabilities", "Cannot combine a patch with full capabilities.")
    else:
        if raw_capabilities is not _ABSENT and raw_capabilities is not None:
            _fail("capabilities", "Field must be omitted or null when unchanged.")
        if raw_patch is not _ABSENT and raw_patch is not None:
            _fail("capability_patch", "Field must be omitted or null when unchanged.")

    if mode == "partial":
        patch = parse_capability_patch(raw_patch)
    else:
        patch = CapabilityPatch()

    fingerprint = _require_str(document, "expected_configuration_fingerprint")
    if not _HEX64_RE.match(fingerprint):
        _fail("expected_configuration_fingerprint", "Value must be a 64-character hex digest.")

    preview = document.get("preview")
    if preview is not None:
        if not isinstance(preview, dict):
            _fail("preview", "Value must be a JSON object.")
        extra_preview = sorted(
            str(k) for k in set(preview) - {"note", "changed_fields", "current_configuration_fingerprint"}
        )
        if extra_preview:
            _fail("preview", "Object contains unsupported fields.")

    return RouteUpdatePlan(
        route_id=route_id,
        requested_model=requested_model,
        match_type=match_type,
        endpoint=endpoint,
        provider=provider,
        upstream_model=raw_upstream,
        priority=priority,
        visible_in_models=visible,
        supports_streaming=streaming,
        enabled=enabled,
        notes=raw_notes,
        capabilities_mode=mode,
        capabilities=capabilities,
        capability_patch=patch,
        expected_configuration_fingerprint=fingerprint,
        preview=preview,
    )


def render_route_update_plan(plan: RouteUpdatePlan) -> dict[str, Any]:
    """Render a typed plan to its strict version-1 document form."""
    patch_document: dict[str, Any] = {}
    if plan.capabilities_mode == "partial":
        if plan.capability_patch.codex_limits is not None:
            patch_document[CODEX_LIMITS_KEY] = dict(plan.capability_patch.codex_limits)
        if plan.capability_patch.media_input_estimation is not None:
            patch_document["media_input_estimation"] = dict(
                plan.capability_patch.media_input_estimation
            )
        if plan.capability_patch.chat_completions is not None:
            patch_document[CHAT_COMPLETIONS_CAPABILITIES_KEY] = dict(
                plan.capability_patch.chat_completions
            )
        if plan.capability_patch.responses is not None:
            patch_document[RESPONSES_CAPABILITIES_KEY] = dict(
                plan.capability_patch.responses
            )
        if plan.capability_patch.completion_service is not _ABSENT:
            patch_document[PROFILE_KEY] = (
                None
                if plan.capability_patch.completion_service is None
                else dict(plan.capability_patch.completion_service)
            )
    document: dict[str, Any] = {
        "schema_version": ROUTE_PLAN_SCHEMA_VERSION,
        "route_id": plan.route_id,
        "requested_model": plan.requested_model,
        "match_type": plan.match_type,
        "endpoint": plan.endpoint,
        "provider": plan.provider,
        "upstream_model": plan.upstream_model,
        "priority": plan.priority,
        "visible_in_models": plan.visible_in_models,
        "supports_streaming": plan.supports_streaming,
        "enabled": plan.enabled,
        "notes": plan.notes,
        "capabilities_mode": plan.capabilities_mode,
        "capabilities": dict(plan.capabilities) if plan.capabilities is not None else None,
        "capability_patch": patch_document or None,
        "expected_configuration_fingerprint": plan.expected_configuration_fingerprint,
    }
    if plan.preview is not None:
        document["preview"] = dict(plan.preview)
    return document


def parse_route_update_plan_file(data: bytes) -> RouteUpdatePlan:
    """Read and strictly parse one route update plan file payload."""
    document = _load_strict_object(
        data, ROUTE_PLAN_FILE_MAX_BYTES, "Route plan file"
    )
    return parse_route_update_plan_document(document)


def compute_capabilities_document_fingerprint(document: dict[str, Any] | None) -> str:
    """Canonical digest over a capabilities document (dedup/staleness data)."""
    canonical = json.dumps(document, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
