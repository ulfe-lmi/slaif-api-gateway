"""Reviewed provider/route configuration GUI (objective 210-a).

Server-rendered reviewed route-configuration workflow for ONE exact route:

- ``GET  /admin/routes/{route_id}/configuration``            form
- ``POST /admin/routes/{route_id}/configuration/plan``       READ ONLY
  shared preview + purpose-bound signed review state
- ``POST /admin/routes/{route_id}/configuration/apply``      verify /
  rebind / strict-reparse, then execute the SAME reviewed plan

The GUI parses and renders only. Merging, fingerprints, locks,
staleness, candidate validation, audit, and no-op law all live in the
shared :mod:`slaif_gateway.services.provider_route_configuration`
services and the strict ``provider_route_configuration`` schemas. The
review token is the purpose-bound 210-a route extension of the 208
review-intent state: reviewed data, never authority, never persisted,
and never echoed.

Routing note: the admin router already registers the dynamic
``GET /routes/{route_id}`` and ``.../edit`` pages. This module uses the
unambiguous longer target-bound ``/routes/{route_id}/configuration/...``
paths, so the existing detail/edit/enable/disable pages keep working
with plain registration order.

The route's ENABLED state is deliberately preserved by the shared
preview: enable/disable stay on the existing status actions and full
editor. The destination provider's display fields and enabled flag are
intentionally outside the reviewed provider-context digest: preparation
stays separate from readiness.
"""

from __future__ import annotations

from collections.abc import Mapping
import uuid
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from fastapi import APIRouter, Request, Response
from fastapi.responses import HTMLResponse

from slaif_gateway.api.admin import (
    _admin_action_context,
    _admin_bounded_reason,
    _admin_error_page,
    _admin_not_found,
    _admin_page_context,
    _admin_redact_key_form_value,
    _admin_redact_key_form_values,
    _admin_url_display_value,
    _choice_selected_labels,
    _is_checked,
    _load_admin_record_choices_safe,
    _log_admin_action_failure,
    _parse_provider_slug,
    _parse_route_endpoint,
    _parse_route_text,
    _set_no_store_headers,
    _settings,
    templates,
)
from slaif_gateway.api.admin_review_intent import (
    AdminReviewIntentError,
    build_route_review_token,
    verify_route_review_token,
)
from slaif_gateway.config import Settings
from slaif_gateway.db.models import ModelRoute
from slaif_gateway.db.repositories.provider_configs import ProviderConfigsRepository
from slaif_gateway.db.repositories.routing import ModelRoutesRepository
from slaif_gateway.db.session import get_sessionmaker_from_app
from slaif_gateway.modules.servers.completion_service.profiles import (
    PROFILE_KEY,
    profile_id_from_capabilities,
)
from slaif_gateway.schemas.provider_route_configuration import (
    ProviderRouteConfigError,
    ProviderRouteStaleError,
    RouteUpdatePlan,
    parse_capabilities_file,
    parse_route_update_plan_document,
    render_route_update_plan,
)
from slaif_gateway.schemas.provider_route_configuration import (
    CapabilityPatch,
)
from slaif_gateway.services.chat_completion_route_capabilities import (
    KNOWN_CHAT_COMPLETION_CAPABILITIES,
)
from slaif_gateway.services.model_route_service import (
    CHAT_COMPLETIONS_ENDPOINT,
)
from slaif_gateway.services.provider_route_configuration import (
    compute_route_configuration_fingerprint,
    execute_route_update_plan,
    preview_route_update_for_route,
)
from slaif_gateway.services.record_errors import RecordNotFoundError
from slaif_gateway.services.responses_route_capabilities import (
    KNOWN_RESPONSES_CAPABILITIES,
)
from slaif_gateway.utils.redaction import redact_mapping, redact_text
from slaif_gateway.web.formatting import format_number, format_tokens_m

router = APIRouter(prefix="/admin", include_in_schema=False)

# ---------------------------------------------------------------------------
# Fixed form vocabulary (guided controls; the shared services are the
# authoritative law - this module only maps form state to them)
# ---------------------------------------------------------------------------

_SOURCE_UNCHANGED = "unchanged"
_SOURCE_GUIDED = "guided"
_SOURCE_FULL = "full"
_CAPABILITY_SOURCES = frozenset({_SOURCE_UNCHANGED, _SOURCE_GUIDED, _SOURCE_FULL})

_MATCH_TYPES = frozenset({"exact", "prefix", "glob"})
_NOTES_INTENTS = frozenset({"preserve", "replace", "clear"})
_COMPLETION_ACTIONS = frozenset({"unchanged", "set", "clear"})

# (action_field, value_field, canonical leaf, label)
_CODEX_LEAF_FIELDS: tuple[tuple[str, str, str, str], ...] = (
    (
        "codex_context_action",
        "codex_context_value",
        "context_window_tokens",
        "Context window",
    ),
    (
        "codex_default_output_action",
        "codex_default_output_value",
        "default_max_output_tokens",
        "Default max output",
    ),
    (
        "codex_max_output_action",
        "codex_max_output_value",
        "max_output_tokens",
        "Max output",
    ),
)
_MEDIA_LEAF_FIELDS: tuple[tuple[str, str, str, str], ...] = (
    ("media_image_action", "media_image_value", "image_tokens", "Image tokens"),
    (
        "media_video_tokens_action",
        "media_video_tokens_value",
        "video_tokens",
        "Video tokens",
    ),
    (
        "media_video_frames_action",
        "media_video_frames_value",
        "video_frames",
        "Video frames",
    ),
)

# Field names for the closed Chat/Responses boolean leaves (one tri-state
# select per leaf; omission = preserve, true/false are explicit).
def _flag_field(flag: str) -> str:
    return flag.replace("-", "_")


_CHAT_FLAG_FIELDS: tuple[tuple[str, str], ...] = (
    tuple(
        (f"chat_{_flag_field(flag)}_action", flag)
        for flag in sorted(KNOWN_CHAT_COMPLETION_CAPABILITIES)
    )
)
_RESPONSES_FLAG_FIELDS: tuple[tuple[str, str], ...] = (
    tuple(
        (f"responses_{_flag_field(flag)}_action", flag)
        for flag in sorted(KNOWN_RESPONSES_CAPABILITIES)
    )
)


def _default_route_config_form(route: ModelRoute | None = None) -> dict[str, str]:
    """Form state with every action at 'unchanged' (no change requested).

    The displayed values are the route's CURRENT values (so the operator
    sees what 'keep current' keeps); an unchecked action never submits a
    change. ``route=None`` (defensive) yields blank display values.
    """
    capabilities = (getattr(route, "capabilities", {}) or {}) if route else {}
    chat = capabilities.get("chat_completions") if isinstance(capabilities, dict) else None
    if not isinstance(chat, dict):
        chat = {}
    responses = (
        capabilities.get("responses") if isinstance(capabilities, dict) else None
    )
    if not isinstance(responses, dict):
        responses = {}
    completion_profile = ""
    if isinstance(capabilities, dict) and PROFILE_KEY in capabilities:
        try:
            completion_profile = profile_id_from_capabilities(capabilities) or ""
        except Exception:  # noqa: BLE001 - malformed retained state: display only
            completion_profile = ""
    form: dict[str, str] = {
        "capabilities_source": _SOURCE_UNCHANGED,
        # Match (effective current values; 'unchanged' keeps them).
        "requested_model": str(getattr(route, "requested_model", "")) if route else "",
        "requested_model_action": "unchanged",
        "match_type": str(getattr(route, "match_type", "exact")) if route else "exact",
        "match_type_action": "unchanged",
        "endpoint": str(getattr(route, "endpoint", CHAT_COMPLETIONS_ENDPOINT)) if route else CHAT_COMPLETIONS_ENDPOINT,
        "endpoint_action": "unchanged",
        # Target.
        "provider": str(getattr(route, "provider", "")) if route else "",
        "provider_action": "unchanged",
        "upstream_model": (
            str(getattr(route, "upstream_model") or "") if route else ""
        ),
        "upstream_model_action": "unchanged",
        "priority": str(getattr(route, "priority", "")) if route else "",
        "priority_action": "unchanged",
        # Flags (the shared preview preserves enabled deliberately).
        "visible_in_models_action": "unchanged",
        "supports_streaming_action": "unchanged",
        # Notes: the replacement entry starts BLANK (current notes are
        # shown read-only by the template from THIS projected form, so a
        # no-JS 'clear' never conflicts with a stale pre-filled value and
        # the raw ORM free-form value is never rendered).
        "notes_intent": "preserve",
        "notes": "",
        "notes_current": str(getattr(route, "notes", "") or "") if route else "",
        # Guided capability leaves (all 'unchanged' = preserve deep siblings).
        "completion_action": "unchanged",
        "completion_profile": completion_profile,
        "capabilities_document": "",
    }
    for action_field, _value_field, _leaf, _label in _CODEX_LEAF_FIELDS:
        form[action_field] = "unchanged"
        form[action_field.replace("_action", "_value")] = ""
    for action_field, _value_field, _leaf, _label in _MEDIA_LEAF_FIELDS:
        form[action_field] = "unchanged"
        form[action_field.replace("_action", "_value")] = ""
    for action_field, flag in _CHAT_FLAG_FIELDS:
        form[action_field] = "unchanged"
        form[f"chat_{_flag_field(flag)}"] = "true" if chat.get(flag) else ""
    for action_field, flag in _RESPONSES_FLAG_FIELDS:
        form[action_field] = "unchanged"
        form[f"responses_{_flag_field(flag)}"] = "true" if responses.get(flag) else ""
    return form


def _active_capability_controls(form: dict[str, str]) -> list[str]:
    """Named guided capability controls that deviate from 'unchanged'."""
    active: list[str] = []
    for action_field, value_field, _leaf, _label in (
        _CODEX_LEAF_FIELDS + _MEDIA_LEAF_FIELDS
    ):
        if (form.get(action_field) or "unchanged") != "unchanged":
            active.append(_label)
        elif (form.get(value_field) or "").strip():
            active.append(_label)
    for action_field, _flag in _CHAT_FLAG_FIELDS + _RESPONSES_FLAG_FIELDS:
        if (form.get(action_field) or "unchanged") != "unchanged":
            active.append(action_field)
    if (form.get("completion_action") or "unchanged") != "unchanged":
        active.append("completion service")
    return active


# ---------------------------------------------------------------------------
# Form parsing (fixed safe vocabulary; the shared services remain the law)
# ---------------------------------------------------------------------------


def _check_action(form: dict[str, str], field: str, allowed: frozenset[str]) -> str:
    """Validate one action selector against its CLOSED enum (fixed error).

    Unknown action strings are refused, never silently ignored: a silent
    ignore would turn a typo into a quiet no-change plan.
    """
    action = (form.get(field) or "unchanged").strip()
    if action not in allowed:
        label = field.replace("_action", " ").replace("_", " ").strip().capitalize()
        raise ValueError(f"{label} action must be one of: " + ", ".join(sorted(allowed)) + ".")
    return action


def _parse_positive_leaf_int(raw: str | None, *, label: str) -> int:
    cleaned = (raw or "").strip()
    try:
        value = int(cleaned)
    except ValueError:
        raise ValueError(f"{label} must be a positive whole number.") from None
    if value <= 0:
        raise ValueError(f"{label} must be a positive whole number.")
    return value


def _parse_route_edit_fields(form: dict[str, str]) -> dict[str, Any]:
    """Explicitly-changed route edit fields only (omitted = preserve).

    ``upstream_model`` has no null-clear in the shared preview: an active
    'set' action requires a nonblank value; keeping the current value (or
    its stored null) is the 'unchanged' action.
    """
    edits: dict[str, Any] = {}
    for field in (
        "requested_model_action",
        "match_type_action",
        "endpoint_action",
        "provider_action",
        "upstream_model_action",
        "priority_action",
    ):
        _check_action(form, field, frozenset({"unchanged", "set"}))
    if _check_action(form, "requested_model_action", frozenset({"unchanged", "set"})) == "set":
        edits["requested_model"] = _parse_route_text(
            form.get("requested_model"), field_name="Requested model"
        )
    if _check_action(form, "match_type_action", frozenset({"unchanged", "set"})) == "set":
        match_type = (form.get("match_type") or "").strip()
        if match_type not in _MATCH_TYPES:
            raise ValueError("Match type must be exact, prefix, or glob.")
        edits["match_type"] = match_type
    if _check_action(form, "endpoint_action", frozenset({"unchanged", "set"})) == "set":
        edits["endpoint"] = _parse_route_endpoint(form.get("endpoint"))
    if _check_action(form, "provider_action", frozenset({"unchanged", "set"})) == "set":
        edits["provider"] = _parse_provider_slug(form.get("provider"))
    if _check_action(form, "upstream_model_action", frozenset({"unchanged", "set"})) == "set":
        cleaned = (form.get("upstream_model") or "").strip()
        if not cleaned:
            raise ValueError(
                "Upstream model is required when changing it; keeping the "
                "current value is the 'Keep current' choice (no null clear "
                "is supported by the shared preview)."
            )
        edits["upstream_model"] = cleaned
    if _check_action(form, "priority_action", frozenset({"unchanged", "set"})) == "set":
        raw = (form.get("priority") or "").strip()
        try:
            priority = int(raw)
        except ValueError:
            raise ValueError("Priority must be a whole number (0 is valid).") from None
        if priority < 0:
            raise ValueError("Priority must be a whole number (0 is valid).")
        edits["priority"] = priority
    for field, action_field in (
        ("visible_in_models", "visible_in_models_action"),
        ("supports_streaming", "supports_streaming_action"),
    ):
        action = _check_action(
            form, action_field, frozenset({"unchanged", "true", "false"})
        )
        if action == "true":
            edits[field] = True
        elif action == "false":
            edits[field] = False
    return edits


def _parse_notes_intent(form: dict[str, str]) -> dict[str, Any]:
    """Unambiguous preserve / replace / clear notes intent.

    A blank REPLACE is not an implicit clear: it preserves the stored
    notes (the shared preview treats a None replacement as preserve).
    Clearing with replacement text present is a conflicting explicit
    input and is refused before any service call.
    """
    intent = (form.get("notes_intent") or "preserve").strip()
    if intent not in _NOTES_INTENTS:
        raise ValueError("Notes intent must be preserve, replace, or clear.")
    notes_text = (form.get("notes") or "").strip()
    if intent == "clear" and notes_text:
        raise ValueError(
            "Choose either notes replacement or clearing, not both: "
            "clearing does not keep the replacement text."
        )
    if intent == "preserve":
        return {}
    if intent == "replace":
        return {"notes": notes_text or None}
    return {"clear_notes": True}


def _parse_capability_leaves(
    form: dict[str, str],
    *,
    settings: Settings,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Build the explicit CapabilityPatch leaves (or a full document).

    Returns ``(patch_kwargs, capabilities_document)`` - exactly one of
    the two capability sources may be active (the single-source law is
    checked here against ``capabilities_source``).
    """
    source = (form.get("capabilities_source") or _SOURCE_UNCHANGED).strip()
    if source not in _CAPABILITY_SOURCES:
        raise ValueError(
            "Capability source must be unchanged, guided partial, or "
            "complete replacement."
        )
    document_raw = (form.get("capabilities_document") or "").strip()
    active = _active_capability_controls(form)

    if source == _SOURCE_UNCHANGED and (document_raw or active):
        raise ValueError(
            "The plan keeps capabilities unchanged: clear the guided "
            "capability controls or choose a capability source."
        )
    if source == _SOURCE_FULL and active:
        raise ValueError(
            "Choose either the guided partial controls or the complete "
            "replacement document, not both."
        )
    if source == _SOURCE_GUIDED and document_raw:
        raise ValueError(
            "Choose either the guided partial controls or the complete "
            "replacement document, not both."
        )

    if source == _SOURCE_FULL:
        if not document_raw:
            raise ValueError(
                "Complete replacement requires the strict version-1 "
                "capabilities document."
            )
        document = parse_capabilities_file(
            document_raw.encode("utf-8"),
            external_tool_ceilings=settings.get_external_tool_operator_ceilings(),
            profile_dir=settings.COMPLETION_SERVICE_PROFILE_DIR,
        )
        return {}, document

    codex: dict[str, int] = {}
    for action_field, value_field, leaf, label in _CODEX_LEAF_FIELDS:
        if _check_action(form, action_field, frozenset({"unchanged", "set"})) == "set":
            codex[leaf] = _parse_positive_leaf_int(
                form.get(value_field), label=f"Codex {label.lower()}"
            )
    media: dict[str, int] = {}
    for action_field, value_field, leaf, label in _MEDIA_LEAF_FIELDS:
        if _check_action(form, action_field, frozenset({"unchanged", "set"})) == "set":
            media[leaf] = _parse_positive_leaf_int(
                form.get(value_field), label=f"Media {label.lower()}"
            )
    _FLAG_ACTIONS = frozenset({"unchanged", "true", "false"})
    chat: dict[str, bool] = {}
    for action_field, flag in _CHAT_FLAG_FIELDS:
        if _check_action(form, action_field, _FLAG_ACTIONS) == "true":
            chat[flag] = True
        elif _check_action(form, action_field, _FLAG_ACTIONS) == "false":
            chat[flag] = False
    responses: dict[str, bool] = {}
    for action_field, flag in _RESPONSES_FLAG_FIELDS:
        if _check_action(form, action_field, _FLAG_ACTIONS) == "true":
            responses[flag] = True
        elif _check_action(form, action_field, _FLAG_ACTIONS) == "false":
            responses[flag] = False

    completion: Any
    completion_action = _check_action(form, "completion_action", _COMPLETION_ACTIONS)
    if completion_action == "set":
        profile = (form.get("completion_profile") or "").strip()
        if not profile:
            raise ValueError(
                "Select an installed completion service profile to set it."
            )
        completion = {"version": 1, "profile": profile}
    elif completion_action == "clear":
        completion = None
    else:
        completion = _OMITTED

    patch_kwargs: dict[str, Any] = {}
    if codex:
        patch_kwargs["codex_limits"] = codex
    if media:
        patch_kwargs["media_input_estimation"] = media
    if chat:
        patch_kwargs["chat_completions"] = chat
    if responses:
        patch_kwargs["responses"] = responses
    if completion_action != "unchanged":
        patch_kwargs["completion_service"] = completion
    return patch_kwargs, None


_OMITTED = object()


def _parse_route_config_form(
    form: dict[str, str],
    *,
    provider_choices: list[object],
    settings: Settings,
) -> dict[str, Any]:
    """One reviewed plan input: explicit edits + ONE capability source."""
    edits = _parse_route_edit_fields(form)
    edits.update(_parse_notes_intent(form))
    patch_kwargs, capabilities_document = _parse_capability_leaves(form, settings=settings)
    if edits.get("provider") is not None:
        known = {str(getattr(choice, "id")) for choice in provider_choices}
        if edits["provider"] not in known:
            raise ValueError("Select a known provider config for the destination.")
    if patch_kwargs:
        patch = CapabilityPatch(**patch_kwargs)
        if patch.is_empty():
            raise ValueError(
                "Guided partial mode needs at least one explicit capability "
                "leaf; keep capabilities unchanged otherwise."
            )
        edits["capability_patch"] = patch
    if capabilities_document is not None:
        edits["capabilities_document"] = capabilities_document
    return {"edits": edits, "form": form}


# ---------------------------------------------------------------------------
# Strict plan document gate (pre-render / pre-HMAC and again at apply)
# ---------------------------------------------------------------------------


def _strict_route_plan_document(
    plan_document: dict[str, Any],
    *,
    settings: Settings,
) -> RouteUpdatePlan:
    """Explicit strict reparse + 128 KiB canonical byte bound.

    ``render_route_update_plan`` serializes; the service comment is not
    proof of strict reparse. The whole-plan known-shape guard (including
    retained current values and preview data) runs here BEFORE any review
    rendering or signed-token construction, and again at apply.
    """
    import json as _json

    canonical = _json.dumps(
        plan_document, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    from slaif_gateway.schemas.provider_route_configuration import (
        ROUTE_PLAN_FILE_MAX_BYTES,
    )

    if len(canonical) > ROUTE_PLAN_FILE_MAX_BYTES:
        raise ProviderRouteConfigError(
            "plan: The reviewed plan exceeds the bounded review size."
        )
    return parse_route_update_plan_document(
        plan_document,
        external_tool_ceilings=settings.get_external_tool_operator_ceilings(),
        profile_dir=settings.COMPLETION_SERVICE_PROFILE_DIR,
    )


# ---------------------------------------------------------------------------
# Readable review display (values only; raw JSON stays the detail block)
# ---------------------------------------------------------------------------

_CANONICAL_FIELD_LABELS: dict[str, str] = {
    "requested_model": "Requested model",
    "match_type": "Match type",
    "endpoint": "Endpoint",
    "provider": "Destination provider",
    "upstream_model": "Upstream model",
    "priority": "Priority",
    "enabled": "Route status",
    "visible_in_models": "Visible in /v1/models",
    "supports_streaming": "Supports streaming",
    "capabilities": "Capabilities",
    "notes": "Notes",
}


def _route_config_value_readable(field: str, value: Any) -> str:
    if value is None:
        return "(none)"
    if field == "priority":
        return format_number(value)
    if field == "enabled":
        return "enabled" if value else "disabled"
    if field == "visible_in_models":
        return "visible" if value else "hidden"
    if field == "supports_streaming":
        return "supported" if value else "not supported"
    if field == "notes":
        return "No notes." if value is None else str(value)
    if field == "capabilities":
        return _capabilities_readable(value)
    return str(value)


def _capabilities_readable(document: Any) -> str:
    """Compact readable summary of one capabilities document.

    Distinguishes gateway route limits (Codex ceilings), media input
    estimates, capability flags, and the completion-service selector; the
    exact raw JSON remains available in the detail block.
    """
    if not isinstance(document, dict) or not document:
        return "None."
    parts: list[str] = []
    def _tokens(value: Any) -> str:
        # Shared M-token display PLUS the exact raw count (the raw JSON
        # detail block carries the machine values).
        if value is None:
            return "n/a"
        return f"{format_tokens_m(value)}M ({format_number(value)})"

    codex = document.get("codex_limits")
    if isinstance(codex, dict) and codex:
        parts.append(
            "Codex limits: context "
            + _tokens(codex.get("context_window_tokens"))
            + ", default output "
            + _tokens(codex.get("default_max_output_tokens"))
            + ", max output "
            + _tokens(codex.get("max_output_tokens"))
        )
    media = document.get("media_input_estimation")
    if isinstance(media, dict) and media:
        parts.append(
            "Media input estimates: image "
            + _tokens(media.get("image_tokens"))
            + ", video "
            + _tokens(media.get("video_tokens"))
            + " / "
            + format_number(media.get("video_frames"))
            + " frames"
        )
    for group in ("chat_completions", "responses"):
        block = document.get(group)
        if isinstance(block, dict) and block:
            on = sum(1 for value in block.values() if value is True)
            parts.append(f"{group}: {on} of {len(block)} flags enabled")
    completion = document.get(PROFILE_KEY)
    if isinstance(completion, dict) and completion.get("profile"):
        parts.append(f"completion service: profile {completion['profile']}")
    if "external_tools" in document:
        parts.append("external tool route policy present")
    other = sorted(
        set(document)
        - {
            "codex_limits",
            "media_input_estimation",
            "chat_completions",
            "responses",
            PROFILE_KEY,
            "external_tools",
        }
    )
    if other:
        parts.append("other groups: " + ", ".join(other))
    return "; ".join(parts) if parts else "Empty."


def _capability_group_value_readable(value: Any, settings: Settings) -> str:
    """Read-only rendering of ONE capability group's actual value.

    Full replacement can change or remove the external_tools and
    transport-contract groups, so the review shows their ACTUAL
    non-secret before/after state as a structured key=value rendering
    instead of a count-only placeholder. Sensitive-named members are
    masked and recognized credential shapes redacted with the shared
    rules before rendering; the exact raw JSON stays available in the
    detail block as the machine view.
    """
    if value is None:
        return "(absent)"
    prefixes = settings.get_gateway_key_accepted_prefixes()
    if isinstance(value, Mapping):
        value = redact_mapping(value, prefixes)
    elif isinstance(value, str):
        value = redact_text(value, prefixes)
    rendered = _render_group_value(value)
    if len(rendered) > 1000:
        rendered = rendered[:1000] + " … (see raw plan JSON)"
    return rendered


def _render_group_value(value: Any) -> str:
    """Compact structured rendering of one redacted group value."""
    if value is None:
        return "(none)"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return format_number(value)
    if isinstance(value, str):
        return value if value else "(empty)"
    if isinstance(value, Mapping):
        parts = [f"{key}={_render_group_value(item)}" for key, item in sorted(value.items())]
        return "{" + ", ".join(parts) + "}" if parts else "{}"
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_render_group_value(item) for item in value) + "]"
    return str(value)


def _capabilities_diff(
    current: Any, proposed: Any, *, settings: Settings
) -> list[dict[str, str]]:
    """Leaf-level changes between two capabilities documents.

    The primary readable review names the ACTUAL changed leaves with
    before/after values (a flag swap at the same enabled count is still
    visible). Whole groups outside the known leaf sets (external_tools,
    the transport-contract groups, audio/embeddings/realtime) compare
    by exact equality and render their actual non-secret before/after
    state, not a count-only placeholder.
    """
    cur = current if isinstance(current, dict) else {}
    pro = proposed if isinstance(proposed, dict) else {}
    changes: list[dict[str, str]] = []

    def _tokens(value: Any) -> str:
        if value is None:
            return "(none)"
        return f"{format_tokens_m(value)}M ({format_number(value)})"

    for leaf, label in (
        ("context_window_tokens", "Codex context window"),
        ("default_max_output_tokens", "Codex default max output"),
        ("max_output_tokens", "Codex max output"),
    ):
        c = cur.get("codex_limits", {}).get(leaf) if isinstance(cur.get("codex_limits"), dict) else None
        p = pro.get("codex_limits", {}).get(leaf) if isinstance(pro.get("codex_limits"), dict) else None
        if c != p:
            changes.append({"label": label, "before": _tokens(c), "after": _tokens(p)})
    for leaf, label in (
        ("image_tokens", "Media image estimate"),
        ("video_tokens", "Media video tokens"),
        ("video_frames", "Media video frames"),
    ):
        c = cur.get("media_input_estimation", {}).get(leaf) if isinstance(cur.get("media_input_estimation"), dict) else None
        p = pro.get("media_input_estimation", {}).get(leaf) if isinstance(pro.get("media_input_estimation"), dict) else None
        if c != p:
            changes.append(
                {
                    "label": label,
                    "before": _tokens(c) if leaf != "video_frames" else (format_number(c) if c is not None else "(none)"),
                    "after": _tokens(p) if leaf != "video_frames" else (format_number(p) if p is not None else "(none)"),
                }
            )
    for group, prefix in (("chat_completions", "Chat"), ("responses", "Responses")):
        cblock = cur.get(group) if isinstance(cur.get(group), dict) else {}
        pblock = pro.get(group) if isinstance(pro.get(group), dict) else {}
        for flag in sorted(set(cblock) | set(pblock)):
            c, p = cblock.get(flag), pblock.get(flag)
            if c != p:
                changes.append(
                    {
                        "label": f"{prefix} capability: {flag}",
                        "before": "enabled" if c is True else ("disabled" if c is False else "(absent)"),
                        "after": "enabled" if p is True else ("disabled" if p is False else "(absent)"),
                    }
                )
    c_comp = cur.get(PROFILE_KEY)
    p_comp = pro.get(PROFILE_KEY)
    if c_comp != p_comp:
        def _comp(value: Any) -> str:
            if isinstance(value, dict) and value.get("profile"):
                return f"profile {value['profile']} (selector version {value.get('version')})"
            return "(cleared)" if value is None else "(absent)"
        changes.append(
            {"label": "Completion service", "before": _comp(c_comp), "after": _comp(p_comp)}
        )
    for group in sorted((set(cur) | set(pro)) - {"codex_limits", "media_input_estimation", "chat_completions", "responses", PROFILE_KEY}):
        c, p = cur.get(group), pro.get(group)
        if c != p:
            changes.append(
                {
                    "label": f"Group: {group}",
                    "before": _capability_group_value_readable(c, settings),
                    "after": _capability_group_value_readable(p, settings),
                }
            )
    return changes


def _provider_context_readable(provider: Any, settings: Settings) -> dict[str, str]:
    """Readable destination-provider context (ENV-var NAME literal).

    Display fields and the enabled flag are deliberately outside the
    reviewed context digest - preparation stays separate from readiness.
    The free-form base URL is projected with the established known-shape
    redaction before rendering (credential-bearing URL values are
    withheld entirely); the credential ENV-var NAME is never masked.
    The signed context digest itself is untouched.
    """
    return {
        "kind": str(getattr(provider, "kind", "")),
        "base_url": _admin_redact_key_form_value(
            _admin_url_display_value(str(getattr(provider, "base_url", ""))),
            settings,
        ),
        "api_key_env_var": str(getattr(provider, "api_key_env_var", "")),
        "timeout_seconds": format_number(getattr(provider, "timeout_seconds", 0)),
        "max_retries": format_number(getattr(provider, "max_retries", 0)),
        "enabled": "enabled" if getattr(provider, "enabled", False) else "disabled (preparation only)",
    }


# ---------------------------------------------------------------------------
# Runtime scopes (caller-owned transactions; the shared services flush only)
# ---------------------------------------------------------------------------


@asynccontextmanager
async def _admin_route_config_scope(request: Request) -> AsyncIterator[Any]:
    session_factory = get_sessionmaker_from_app(request)
    async with session_factory() as session:
        async with session.begin():
            yield session


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


async def _load_route_readonly(session: Any, route_id: str) -> ModelRoute:
    routes = ModelRoutesRepository(session)
    row = await routes.get_model_route_by_id(uuid.UUID(route_id))
    if row is None:
        raise RecordNotFoundError("Model route")
    return row


async def _route_config_form_choices(
    request: Request, form: dict[str, str]
) -> dict[str, Any]:
    return await _load_admin_record_choices_safe(
        request,
        (
            ("provider", "provider", form.get("provider") or None),
            ("requested_model", "model", form.get("requested_model") or None),
            ("upstream_model", "model", form.get("upstream_model") or None),
            ("endpoint", "endpoint", form.get("endpoint") or None),
            ("completion_profile", "completion_profile", form.get("completion_profile") or None),
        ),
    )


def _render_route_config_form(
    request: Request,
    *,
    admin: object,
    csrf_token: str,
    route_id: str,
    route: ModelRoute,
    form: dict[str, str],
    choices: dict[str, Any],
    error: str | None = None,
    status_code: int = 200,
) -> Response:
    settings = _settings(request)
    # Read-only DISPLAY projections always come from the freshly loaded
    # route, even on a refused-planning retry where the retained
    # (editable) submission form lacks them: a retry must not falsely
    # show "No notes." or every flag "disabled or absent". Editable
    # values keep the submission's retained state.
    defaults = _default_route_config_form(route)
    merged = dict(form)
    merged["notes_current"] = defaults["notes_current"]
    for _action_field, flag in _CHAT_FLAG_FIELDS:
        merged.setdefault(
            "chat_" + _flag_field(flag), defaults["chat_" + _flag_field(flag)]
        )
    for _action_field, flag in _RESPONSES_FLAG_FIELDS:
        merged.setdefault(
            "responses_" + _flag_field(flag),
            defaults["responses_" + _flag_field(flag)],
        )
    form = merged
    choice_labels = _choice_selected_labels(
        choices,
        (
            ("provider", form.get("provider")),
            ("requested_model", form.get("requested_model")),
            ("upstream_model", form.get("upstream_model")),
            ("endpoint", form.get("endpoint")),
            ("completion_profile", form.get("completion_profile")),
        ),
    )
    return templates.TemplateResponse(
        request,
        "routes/configuration_form.html",
        {
            "admin": admin,
            "csrf_token": csrf_token,
            "route_id": route_id,
            "route": route,
            "form": _admin_redact_key_form_values(form, settings),
            "choices": choices,
            "choice_labels": choice_labels,
            "error": error,
            "codex_leaf_fields": _CODEX_LEAF_FIELDS,
            "media_leaf_fields": _MEDIA_LEAF_FIELDS,
            "chat_flag_fields": _CHAT_FLAG_FIELDS,
            "responses_flag_fields": _RESPONSES_FLAG_FIELDS,
        },
        status_code=status_code,
    )


@router.get("/routes/{route_id}/configuration", response_class=HTMLResponse)
async def route_configuration_form(request: Request, route_id: str) -> Response:
    """GET: the guided partial / complete replacement form for ONE route."""
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found(request)

    try:
        parsed_route_id = uuid.UUID(route_id)
    except ValueError:
        return _admin_error_page(request, status_code=404, message="Model route not found.")

    page_context = await _admin_page_context(request)
    if isinstance(page_context, Response):
        return page_context
    context, csrf_token = page_context

    try:
        async with _admin_route_config_scope(request) as session:
            route = await _load_route_readonly(session, str(parsed_route_id))
    except RecordNotFoundError:
        return _admin_error_page(request, status_code=404, message="Model route not found.")

    form = _default_route_config_form(route)
    choices = await _route_config_form_choices(request, form)
    return _render_route_config_form(
        request,
        admin=context.admin_user,
        csrf_token=csrf_token,
        route_id=str(parsed_route_id),
        route=route,
        form=form,
        choices=choices,
    )




def _route_config_form_from_submission(raw: Any) -> dict[str, str]:
    """The complete fixed form vocabulary from one raw form submission."""
    form: dict[str, str] = {
        "capabilities_source": str(raw.get("capabilities_source") or _SOURCE_UNCHANGED),
        "requested_model": str(raw.get("requested_model") or ""),
        "requested_model_action": str(raw.get("requested_model_action") or "unchanged"),
        "match_type": str(raw.get("match_type") or "exact"),
        "match_type_action": str(raw.get("match_type_action") or "unchanged"),
        "endpoint": str(raw.get("endpoint") or CHAT_COMPLETIONS_ENDPOINT),
        "endpoint_action": str(raw.get("endpoint_action") or "unchanged"),
        "provider": str(raw.get("provider") or ""),
        "provider_action": str(raw.get("provider_action") or "unchanged"),
        "upstream_model": str(raw.get("upstream_model") or ""),
        "upstream_model_action": str(raw.get("upstream_model_action") or "unchanged"),
        "priority": str(raw.get("priority") or ""),
        "priority_action": str(raw.get("priority_action") or "unchanged"),
        "visible_in_models_action": str(raw.get("visible_in_models_action") or "unchanged"),
        "supports_streaming_action": str(raw.get("supports_streaming_action") or "unchanged"),
        "notes_intent": str(raw.get("notes_intent") or "preserve"),
        "notes": str(raw.get("notes") or ""),
        "codex_context_action": str(raw.get("codex_context_action") or "unchanged"),
        "codex_context_value": str(raw.get("codex_context_value") or ""),
        "codex_default_output_action": str(raw.get("codex_default_output_action") or "unchanged"),
        "codex_default_output_value": str(raw.get("codex_default_output_value") or ""),
        "codex_max_output_action": str(raw.get("codex_max_output_action") or "unchanged"),
        "codex_max_output_value": str(raw.get("codex_max_output_value") or ""),
        "media_image_action": str(raw.get("media_image_action") or "unchanged"),
        "media_image_value": str(raw.get("media_image_value") or ""),
        "media_video_tokens_action": str(raw.get("media_video_tokens_action") or "unchanged"),
        "media_video_tokens_value": str(raw.get("media_video_tokens_value") or ""),
        "media_video_frames_action": str(raw.get("media_video_frames_action") or "unchanged"),
        "media_video_frames_value": str(raw.get("media_video_frames_value") or ""),
        "completion_action": str(raw.get("completion_action") or "unchanged"),
        "completion_profile": str(raw.get("completion_profile") or ""),
        "capabilities_document": str(raw.get("capabilities_document") or ""),
    }
    for action_field, _flag in _CHAT_FLAG_FIELDS + _RESPONSES_FLAG_FIELDS:
        form[action_field] = str(raw.get(action_field) or "unchanged")
    return form


@router.post("/routes/{route_id}/configuration/plan", response_class=HTMLResponse)
async def route_configuration_plan(request: Request, route_id: str) -> Response:
    """POST: READ ONLY shared preview + purpose-bound signed review state.

    The preview mutates nothing and writes no audit row; every path ends
    with zero writes and zero audits (a no-write commit). Policy refusals
    reach the SHARED validators (fixed safe field messages), never a
    generic retry message. The complete replacement document is blanked
    before any refused-planning rerender (207/209 privacy law).
    """
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found(request)

    try:
        parsed_route_id = uuid.UUID(route_id)
    except ValueError:
        return _admin_error_page(request, status_code=404, message="Model route not found.")

    raw_form = await request.form()
    csrf_token = str(raw_form.get("csrf_token") or "")
    action_context = await _admin_action_context(request, csrf_token=csrf_token)
    if isinstance(action_context, Response):
        return action_context

    form = _route_config_form_from_submission(raw_form)

    async def _rerender(error: str, *, status_code: int = 400) -> Response:
        safe_form = dict(form)
        safe_form["capabilities_document"] = ""
        try:
            async with _admin_route_config_scope(request) as session:
                route = await _load_route_readonly(session, str(parsed_route_id))
        except RecordNotFoundError:
            return _admin_error_page(request, status_code=404, message="Model route not found.")
        choices = await _route_config_form_choices(request, safe_form)
        return _render_route_config_form(
            request,
            admin=action_context.admin_user,
            csrf_token=csrf_token,
            route_id=str(parsed_route_id),
            route=route,
            form=safe_form,
            choices=choices,
            error=error,
            status_code=status_code,
        )

    provider_choices = (
        await _route_config_form_choices(request, form)
    ).get("provider", [])
    try:
        parsed = _parse_route_config_form(
            form, provider_choices=provider_choices, settings=settings
        )
    except (ProviderRouteConfigError, ValueError) as exc:
        return await _rerender(_admin_redact_key_form_value(str(exc), settings))
    edits = parsed["edits"]

    # The SHARED service renders the reviewed plan (READ ONLY). The
    # explicit strict reparse + 128 KiB canonical bound runs BEFORE any
    # review rendering or signed-token construction.
    try:
        async with _admin_route_config_scope(request) as session:
            plan = await preview_route_update_for_route(
                session,
                str(parsed_route_id),
                external_tool_ceilings=settings.get_external_tool_operator_ceilings(),
                profile_dir=settings.COMPLETION_SERVICE_PROFILE_DIR,
                **edits,
            )
            plan_document = render_route_update_plan(plan)
            _strict_route_plan_document(plan_document, settings=settings)
            provider_row = await ProviderConfigsRepository(session).get_provider_config_by_provider(
                plan.provider
            )
    except RecordNotFoundError:
        return _admin_error_page(request, status_code=404, message="Model route not found.")
    except (ProviderRouteConfigError, ValueError) as exc:
        # The shared validators' fixed safe field messages (they name the
        # field, never echo a value) - the validator's own refusal, not a
        # generic retry.
        _log_admin_action_failure(
            request,
            exc=exc,
            admin_id=action_context.admin_user.id,
            owner_id=None,
            cohort_id=None,
            email_delivery_mode=None,
        )
        return await _rerender(_admin_redact_key_form_value(str(exc), settings))
    except Exception as exc:  # noqa: BLE001 - preview is read-only; safe fallback
        _log_admin_action_failure(
            request,
            exc=exc,
            admin_id=action_context.admin_user.id,
            owner_id=None,
            cohort_id=None,
            email_delivery_mode=None,
        )
        return await _rerender(
            "The route plan could not be prepared right now; try again."
        )

    try:
        token = build_route_review_token(
            admin_session_secret=settings.ADMIN_SESSION_SECRET,
            admin_user_id=action_context.admin_user.id,
            admin_session_id=action_context.admin_session.id,
            plan_document=plan_document,
            route_target=str(parsed_route_id),
            external_tool_ceilings=settings.get_external_tool_operator_ceilings(),
            profile_dir=settings.COMPLETION_SERVICE_PROFILE_DIR,
        )
    except (ProviderRouteConfigError, AdminReviewIntentError) as exc:
        _log_admin_action_failure(
            request,
            exc=exc,
            admin_id=action_context.admin_user.id,
            owner_id=None,
            cohort_id=None,
            email_delivery_mode=None,
        )
        message = exc.message if isinstance(exc, AdminReviewIntentError) else str(exc)
        return await _rerender(_admin_redact_key_form_value(message, settings))

    preview = plan_document.get("preview") or {}
    current = preview.get("current_configuration") or {}
    proposed = preview.get("proposed_configuration") or {}
    diff_rows = [
        {
            "field": field,
            "label": _CANONICAL_FIELD_LABELS.get(field, field),
            "before": _route_config_value_readable(field, current.get(field)),
            "after": _route_config_value_readable(field, proposed.get(field)),
        }
        for field in sorted(preview.get("changed_fields") or [])
        if field != "capabilities"
    ]
    if "capabilities" in (preview.get("changed_fields") or ()):
        capability_changes = _capabilities_diff(
            current.get("capabilities"),
            proposed.get("capabilities"),
            settings=settings,
        )
    else:
        capability_changes = []

    response = templates.TemplateResponse(
        request,
        "routes/configuration_review.html",
        {
            "admin": action_context.admin_user,
            "csrf_token": csrf_token,
            "route_id": str(parsed_route_id),
            "plan": plan_document,
            "plan_note": preview.get("note"),
            "diff_rows": diff_rows,
            "capability_changes": capability_changes,
            "proposed_configuration": proposed,
            "provider_context": (
                _provider_context_readable(provider_row, settings)
                if provider_row is not None
                else None
            ),
            "destination_provider": plan.provider,
            "route_config_review_intent": token,
            "error": None,
        },
    )
    _set_no_store_headers(response)
    return response


@router.post("/routes/{route_id}/configuration/apply", response_class=HTMLResponse)
async def route_configuration_apply(request: Request, route_id: str) -> Response:
    """POST: verify/rebind/strict-reparse, then execute the SAME plan.

    The signed token is reviewed data, never authority: the apply URL's
    route target must independently agree with the reviewed plan, and the
    plan is strict-reparsed (with the 128 KiB canonical bound) again
    BEFORE any mutation. A repeated effective route update is STALE (the
    core law); a fresh zero-diff plan is a no-write/no-audit no-op. The
    token is never retained on the result page.
    """
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found(request)

    try:
        parsed_route_id = uuid.UUID(route_id)
    except ValueError:
        return _admin_error_page(request, status_code=404, message="Model route not found.")

    raw_form = await request.form()
    csrf_token = str(raw_form.get("csrf_token") or "")
    review_intent = str(raw_form.get("route_config_review_intent") or "")
    confirm_apply = str(raw_form.get("confirm_apply") or "")
    reason = str(raw_form.get("reason") or "")

    action_context = await _admin_action_context(request, csrf_token=csrf_token)
    if isinstance(action_context, Response):
        return action_context

    def _safe_400(message: str) -> Response:
        return _admin_error_page(
            request,
            status_code=400,
            message=_admin_redact_key_form_value(message, settings),
        )

    # Everything below runs BEFORE any mutation.
    try:
        plan_document = verify_route_review_token(
            admin_session_secret=settings.ADMIN_SESSION_SECRET,
            token=review_intent,
            admin_user_id=action_context.admin_user.id,
            admin_session_id=action_context.admin_session.id,
            route_target=str(parsed_route_id),
            external_tool_ceilings=settings.get_external_tool_operator_ceilings(),
            profile_dir=settings.COMPLETION_SERVICE_PROFILE_DIR,
        )
        plan = _strict_route_plan_document(plan_document, settings=settings)
    except AdminReviewIntentError as exc:
        _log_admin_action_failure(
            request,
            exc=exc,
            admin_id=action_context.admin_user.id,
            owner_id=None,
            cohort_id=None,
            email_delivery_mode=None,
        )
        return _safe_400(exc.message)
    except (ProviderRouteConfigError, ValueError) as exc:
        _log_admin_action_failure(
            request,
            exc=exc,
            admin_id=action_context.admin_user.id,
            owner_id=None,
            cohort_id=None,
            email_delivery_mode=None,
        )
        return _safe_400(str(exc))

    try:
        if not _is_checked(confirm_apply):
            raise ValueError(
                "Confirm the reviewed route configuration plan before applying it."
            )
        cleaned_reason, reason_error = _admin_bounded_reason(reason)
        if reason_error is not None:
            raise ValueError(reason_error)
        if cleaned_reason is None:
            raise ValueError("Enter an audit reason before applying the route plan.")
        cleaned_reason = _admin_redact_key_form_value(cleaned_reason, settings)
    except ValueError as exc:
        _log_admin_action_failure(
            request,
            exc=exc,
            admin_id=action_context.admin_user.id,
            owner_id=None,
            cohort_id=None,
            email_delivery_mode=None,
        )
        return _safe_400(str(exc))

    # Execute the SAME reviewed plan in the caller-owned transaction.
    try:
        async with _admin_route_config_scope(request) as session:
            updated = await execute_route_update_plan(
                session,
                plan,
                reason=cleaned_reason,
                external_tool_ceilings=settings.get_external_tool_operator_ceilings(),
                profile_dir=settings.COMPLETION_SERVICE_PROFILE_DIR,
                actor_admin_id=action_context.admin_user.id,
            )
    except ProviderRouteStaleError as exc:
        _log_admin_action_failure(
            request,
            exc=exc,
            admin_id=action_context.admin_user.id,
            owner_id=None,
            cohort_id=None,
            email_delivery_mode=None,
        )
        return _safe_400(str(exc))
    except RecordNotFoundError:
        return _admin_error_page(request, status_code=404, message="Model route not found.")
    except (ProviderRouteConfigError, ValueError) as exc:
        _log_admin_action_failure(
            request,
            exc=exc,
            admin_id=action_context.admin_user.id,
            owner_id=None,
            cohort_id=None,
            email_delivery_mode=None,
        )
        return _safe_400(str(exc))

    # Outcome: an effective update moves the route off the reviewed
    # pre-state fingerprint; a zero-diff plan returns the row unchanged
    # (zero writes, zero audits).
    applied = (
        compute_route_configuration_fingerprint(
            str(updated.id),
            requested_model=updated.requested_model,
            match_type=updated.match_type,
            endpoint=updated.endpoint,
            provider=updated.provider,
            upstream_model=updated.upstream_model,
            priority=updated.priority,
            visible_in_models=updated.visible_in_models,
            supports_streaming=updated.supports_streaming,
            enabled=updated.enabled,
            capabilities=updated.capabilities,
            notes=updated.notes,
        )
        != plan.expected_configuration_fingerprint
    )

    response = templates.TemplateResponse(
        request,
        "routes/configuration_result.html",
        {
            "admin": action_context.admin_user,
            "route_id": str(parsed_route_id),
            "requested_model": updated.requested_model,
            "applied": applied,
            "reason": cleaned_reason,
            "expected_configuration_fingerprint": plan.expected_configuration_fingerprint,
            "plan": plan_document,
            "csrf_token": csrf_token,
        },
    )
    _set_no_store_headers(response)
    return response
