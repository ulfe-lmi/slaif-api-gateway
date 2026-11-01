"""Reviewed key-configuration batch GUI (objective 209-a).

Server-rendered "Change existing keys" workflow:

- ``GET  /admin/key-batch``        guided/advanced batch form
- ``POST /admin/key-batch/plan``   READ ONLY core plan + signed review state
- ``POST /admin/key-batch/apply``  verify/rebind/strict-reparse, then atomic apply

The GUI parses and renders only. Selection, membership, staleness,
atomicity, audit, and quota law all live in the shared
:class:`~slaif_gateway.services.key_batch_service.KeyBatchService` and the
strict ``key_batch`` / ``key_configuration`` schemas. The review token is
the purpose-bound 209-a batch extension of the 208 review-intent state:
reviewed data, never authority, never persisted, and never echoed.

Routing note: the admin router already registers the dynamic
``GET /keys/{gateway_key_id}``. This module therefore lives under the
unambiguous longer ``/key-batch`` prefix (not ``/keys/batch``), so the
form, the existing key detail pages, and the 208 clone routes all keep
working with plain registration order.
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from decimal import Decimal, InvalidOperation
from typing import Any, AsyncIterator

from fastapi import APIRouter, Form, Request, Response
from fastapi.responses import HTMLResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.formparsers import MultiPartException

from slaif_gateway.api.admin import (
    _ADMIN_MODEL_CREDENTIAL_SHAPE_MESSAGE,
    _admin_action_context,
    _admin_bounded_reason,
    _admin_diagnostic_id,
    _admin_error_page,
    _admin_not_found,
    _admin_page_context,
    _admin_redact_key_form_value,
    _admin_redact_key_form_values,
    _admin_value_contains_credential_shape,
    _choice_selected_labels,
    _is_checked,
    _load_admin_record_choices_safe,
    _log_admin_action_failure,
    _parse_admin_text_list,
    _parse_required_admin_uuid,
    _set_no_store_headers,
    _settings,
    templates,
)
from slaif_gateway.api.admin_review_intent import (
    AdminReviewIntentError,
    MAX_REVIEW_INTENT_BATCH_TOKEN_CHARS,
    build_batch_review_token,
    verify_batch_review_token,
)
from slaif_gateway.config import Settings
from slaif_gateway.db.repositories.audit import AuditRepository
from slaif_gateway.db.repositories.cohorts import CohortsRepository
from slaif_gateway.db.repositories.keys import GatewayKeysRepository
from slaif_gateway.db.repositories.one_time_secrets import OneTimeSecretsRepository
from slaif_gateway.db.repositories.routing import ModelRoutesRepository
from slaif_gateway.db.session import get_sessionmaker_from_app
from slaif_gateway.schemas.key_batch import (
    KEY_BATCH_MAX_KEYS,
    KEY_BATCH_STATUSES,
    KeyBatchError,
    parse_key_batch_plan,
    render_key_batch_plan,
)
from slaif_gateway.schemas.key_configuration import (
    KeyConfiguration,
    KeyConfigurationError,
    parse_key_configuration_file,
)
from slaif_gateway.services.external_tool_policy_contract import (
    EXTERNAL_TOOL_FENCED,
)
from slaif_gateway.services.key_batch_service import KeyBatchService
from slaif_gateway.services.key_errors import KeyManagementError
from slaif_gateway.services.key_service import KeyService
from slaif_gateway.services.streaming_live_burn_surface import (
    CHAT_STREAMING_LIVE_BURN_SURFACE,
    parse_streaming_live_burn_surface_form_policy,
)
from slaif_gateway.web.formatting import (
    format_number,
    format_raw_decimal,
    format_tokens_m,
)

router = APIRouter(prefix="/admin", include_in_schema=False)

# ---------------------------------------------------------------------------
# Fixed form vocabulary (guided controls; the server law is authoritative)
# ---------------------------------------------------------------------------

_BATCH_INPUT_GUIDED = "guided"
_BATCH_INPUT_ADVANCED = "advanced"

_BATCH_QUOTA_FIELDS: tuple[tuple[str, str, str, str], ...] = (
    # (action_field, value_field, config_attribute, label)
    ("cost_action", "cost_value", "cost_limit_eur", "cost limit"),
    ("token_action", "token_value", "token_limit_total", "token limit"),
    ("request_action", "request_value", "request_limit_total", "request limit"),
)

_BATCH_RATE_FIELDS: tuple[tuple[str, str, str], ...] = (
    # (action_field, value_field, canonical rate member)
    ("rate_action_requests", "rate_value_requests", "requests_per_minute"),
    ("rate_action_tokens", "rate_value_tokens", "tokens_per_minute"),
    ("rate_action_concurrency", "rate_value_concurrency", "max_concurrent_requests"),
    ("rate_action_window", "rate_value_window", "window_seconds"),
)

_BATCH_LIST_FIELDS: tuple[tuple[str, str, str], ...] = (
    # (mode_field, value_field, label)
    ("providers_mode", "providers_value", "provider"),
    ("models_mode", "models_value", "model"),
    ("endpoints_mode", "endpoints_value", "endpoint"),
)

# Bounded transport caps for the batch APPLY form ONLY. The signed review
# token is a single urlencoded field of up to
# MAX_REVIEW_INTENT_BATCH_TOKEN_CHARS (the 8 MiB canonical plan,
# base64url-expanded: 11,184,812 chars, plus digest and separator).
# Starlette's default per-field cap (1 MiB) is far below that, so the
# apply route parses the form ITSELF with envelope-sized headroom BEFORE
# FastAPI's default auto-form parsing; no files are accepted and every
# other route keeps the framework defaults.
_BATCH_FORM_MAX_PART_BYTES = (
    MAX_REVIEW_INTENT_BATCH_TOKEN_CHARS + len("batch_review_intent") + 64 * 1024
)
_BATCH_FORM_MAX_FIELDS = 64
_BATCH_FORM_TOO_LARGE_MESSAGE = (
    "The submitted review state exceeds the bounded transport size. "
    "Review the batch plan again."
)
# Guided policy controls that must sit at their defaults while the
# advanced configuration document is the single input source.
_BATCH_GUIDED_POLICY_DEFAULTS: dict[str, str] = {
    "cost_action": "unchanged",
    "token_action": "unchanged",
    "request_action": "unchanged",
    "rate_action_requests": "unchanged",
    "rate_action_tokens": "unchanged",
    "rate_action_concurrency": "unchanged",
    "rate_action_window": "unchanged",
    "providers_mode": "unchanged",
    "models_mode": "unchanged",
    "endpoints_mode": "unchanged",
    "lazy_mode": "unchanged",
    "live_burn_mode": "unchanged",
}

# Readable labels for per-key configuration fields in the review diff.
_BATCH_FIELD_LABELS: dict[str, str] = {
    "cost_limit_eur": "Cost limit (EUR)",
    "token_limit_total": "Token limit",
    "request_limit_total": "Request limit",
    "allowed_models": "Allowed models",
    "allow_all_models": "Allow all models",
    "allowed_endpoints": "Allowed endpoints",
    "allow_all_endpoints": "Allow all endpoints",
    "allowed_providers": "Allowed providers",
    "responses_policy": "Responses policy",
    "rate_limit_policy": "Rate limit policy",
    "lazy_throttling_policy": "Lazy throttling",
    "chat_streaming_live_burn_policy": "Chat streaming live-burn",
    "external_tool_policy": "External tool policy",
}


def _default_batch_form() -> dict[str, str]:
    return {
        "input_mode": _BATCH_INPUT_GUIDED,
        "selection_kind": "cohort",
        "cohort_id": "",
        "key_ids": "",
        "status_active": "true",
        "status_suspended": "",
        "status_revoked": "",
        "cost_action": "unchanged",
        "cost_value": "",
        "token_action": "unchanged",
        "token_value": "",
        "request_action": "unchanged",
        "request_value": "",
        "rate_action_requests": "unchanged",
        "rate_value_requests": "",
        "rate_action_tokens": "unchanged",
        "rate_value_tokens": "",
        "rate_action_concurrency": "unchanged",
        "rate_value_concurrency": "",
        "rate_action_window": "unchanged",
        "rate_value_window": "",
        "providers_mode": "unchanged",
        "providers_value": "",
        "models_mode": "unchanged",
        "models_value": "",
        "endpoints_mode": "unchanged",
        "endpoints_value": "",
        "lazy_mode": "unchanged",
        "lazy_wait_seconds": "",
        "lazy_waiting": "",
        "live_burn_mode": "unchanged",
        "live_burn_cost_margin": "",
        "live_burn_token_margin": "",
        "configuration_json": "",
    }


# ---------------------------------------------------------------------------
# Guided form parsing (fixed safe errors; submitted values are never echoed)
# ---------------------------------------------------------------------------


def _parse_batch_statuses(form: dict[str, str]) -> tuple[str, ...]:
    statuses = [
        status
        for flag, status in (
            ("status_active", "active"),
            ("status_suspended", "suspended"),
            ("status_revoked", "revoked"),
        )
        if _is_checked(form.get(flag))
    ]
    if not statuses:
        raise ValueError("Select at least one persisted status to include.")
    if set(statuses) - set(KEY_BATCH_STATUSES):
        raise ValueError("Select only the supported persisted statuses.")
    return tuple(statuses)


def _parse_batch_selection(form: dict[str, str]) -> dict[str, Any]:
    """Exactly one selection source; bounded explicit key UUID set.

    The submitted identifiers are internal gateway key UUIDs (record
    choice kind ``key``), the same exact-set the CLI ``--key-id`` takes.
    Duplicates, malformed values, and overflow are refused with fixed
    messages that never echo the submitted values.
    """
    kind = (form.get("selection_kind") or "").strip().lower()
    if kind not in {"cohort", "keys"}:
        raise ValueError("Select the batch target: one cohort or explicit keys.")
    cohort_raw = (form.get("cohort_id") or "").strip()
    keys_raw = (form.get("key_ids") or "").strip()

    if kind == "cohort":
        if not cohort_raw:
            raise ValueError("Select the target cohort.")
        if keys_raw:
            raise ValueError(
                "Cohort selection uses only the cohort field; clear the key list."
            )
        return {
            "kind": "cohort",
            "cohort_id": _parse_required_admin_uuid(cohort_raw, field_name="cohort_id"),
            "key_ids": (),
        }

    if cohort_raw:
        raise ValueError("Key selection uses only the key list; clear the cohort field.")
    if not keys_raw:
        raise ValueError("Enter at least one gateway key UUID.")
    key_ids: list[uuid.UUID] = []
    seen: set[uuid.UUID] = set()
    for value in _parse_admin_text_list(keys_raw):
        try:
            key_id = uuid.UUID(value)
        except (ValueError, TypeError, AttributeError):
            raise ValueError(
                "Key selection contains an invalid key identifier."
            ) from None
        if key_id in seen:
            raise ValueError("Key selection contains duplicate key IDs.")
        seen.add(key_id)
        key_ids.append(key_id)
    if len(key_ids) > KEY_BATCH_MAX_KEYS:
        raise ValueError(
            f"Key selection exceeds the bounded key count ({KEY_BATCH_MAX_KEYS})."
        )
    return {"kind": "keys", "cohort_id": None, "key_ids": tuple(key_ids)}


def _parse_quota_value(raw: str, *, label: str) -> Decimal | int:
    try:
        value = Decimal(raw)
    except (InvalidOperation, ValueError):
        raise ValueError(f"Enter a valid number for the {label}.") from None
    if not value.is_finite() or value < 0:
        raise ValueError(f"The {label} must be a finite number of zero or more.")
    if label == "cost limit":
        return value
    if value != value.to_integral_value():
        raise ValueError(f"The {label} must be a whole number.")
    return int(value)


def _parse_batch_guided_policy(
    form: dict[str, str], settings: Settings
) -> KeyConfiguration:
    """Compose the guided controls into one strict KeyConfiguration.

    Omission law per member: an ``unchanged`` action omits the field
    (preserved), ``clear`` sends explicit null (unlimited/inherit), and
    ``set`` sends a positive value. A value with a non-``set`` action is
    a contradictory active control and is refused.
    """
    config = KeyConfiguration()

    for action_field, value_field, attribute, label in _BATCH_QUOTA_FIELDS:
        action = (form.get(action_field) or "").strip().lower()
        raw = (form.get(value_field) or "").strip()
        if action == "unchanged":
            if raw:
                raise ValueError(
                    f"The {label} is unchanged; leave its value blank."
                )
        elif action == "set":
            if not raw:
                raise ValueError(f"Enter a value for the {label} or choose another action.")
            setattr(config, attribute, _parse_quota_value(raw, label=label))
        elif action == "clear":
            if raw:
                raise ValueError(f"The {label} is cleared; leave its value blank.")
            setattr(config, attribute, None)
        else:
            raise ValueError(f"Select a valid action for the {label}.")

    rate_members: dict[str, int | None] = {}
    for action_field, value_field, member in _BATCH_RATE_FIELDS:
        action = (form.get(action_field) or "").strip().lower()
        raw = (form.get(value_field) or "").strip()
        if action == "unchanged":
            if raw:
                raise ValueError(
                    "That rate member is unchanged; leave its value blank."
                )
        elif action == "set":
            try:
                value = int(raw, 10)
            except (ValueError, TypeError):
                raise ValueError(
                    "Rate-limit values must be positive whole numbers."
                ) from None
            if value <= 0:
                raise ValueError(
                    "Rate-limit values must be positive whole numbers."
                )
            rate_members[member] = value
        elif action == "clear":
            if raw:
                raise ValueError(
                    "That rate member is cleared; leave its value blank."
                )
            rate_members[member] = None
        else:
            raise ValueError("Select a valid action for each rate member.")
    if rate_members:
        if len(rate_members) == len(_BATCH_RATE_FIELDS) and all(
            value is None for value in rate_members.values()
        ):
            # Every member explicitly cleared: clear the whole block.
            config.rate_limit_policy = None
        else:
            config.rate_limit_policy = dict(rate_members)

    list_vocab: dict[str, tuple[str, ...]] = {
        "providers_mode": ("unrestricted", "deny_all", "allow_list"),
        "models_mode": ("all", "deny_all", "allow_list"),
        "endpoints_mode": ("all", "deny_all", "allow_list"),
    }
    for mode_field, value_field, label in _BATCH_LIST_FIELDS:
        mode = (form.get(mode_field) or "").strip().lower()
        raw = (form.get(value_field) or "").strip()
        if mode == "unchanged":
            if raw:
                raise ValueError(f"The {label} list is unchanged; leave it blank.")
            continue
        if mode not in list_vocab[mode_field]:
            raise ValueError(f"Select a valid {label} mode.")
        items: list[str] = []
        if mode == "allow_list":
            items = _parse_admin_text_list(raw)
            if not items:
                raise ValueError(f"Enter at least one {label} for the allow list.")
            for item in items:
                if _admin_value_contains_credential_shape(item, settings):
                    raise ValueError(_ADMIN_MODEL_CREDENTIAL_SHAPE_MESSAGE)
        elif raw:
            raise ValueError(f"The {label} mode needs no list; leave it blank.")

        if mode_field == "providers_mode":
            config.allowed_providers = (
                None if mode == "unrestricted" else [] if mode == "deny_all" else items
            )
        elif mode_field == "models_mode":
            config.allow_all_models = mode == "all"
            config.allowed_models = items
        else:  # endpoints_mode
            config.allow_all_endpoints = mode == "all"
            config.allowed_endpoints = items

    lazy_mode = (form.get("lazy_mode") or "").strip().lower()
    lazy_wait_raw = (form.get("lazy_wait_seconds") or "").strip()
    lazy_waiting_raw = (form.get("lazy_waiting") or "").strip()
    if lazy_mode == "unchanged":
        if lazy_wait_raw or lazy_waiting_raw:
            raise ValueError("Lazy throttling is unchanged; leave its values blank.")
    elif lazy_mode == "remove":
        if lazy_wait_raw or lazy_waiting_raw:
            raise ValueError("Lazy throttling is removed; leave its values blank.")
        config.lazy_throttling_policy = None
    elif lazy_mode == "reject":
        if lazy_wait_raw or lazy_waiting_raw:
            raise ValueError("Reject mode needs no wait values; leave them blank.")
        config.lazy_throttling_policy = {"mode": "reject"}
    elif lazy_mode == "wait":
        if not lazy_wait_raw or not lazy_waiting_raw:
            raise ValueError("Wait mode needs both a max wait and a max waiting count.")
        try:
            wait_seconds = int(lazy_wait_raw, 10)
            waiting = int(lazy_waiting_raw, 10)
        except (ValueError, TypeError):
            raise ValueError(
                "Lazy wait values must be positive whole numbers."
            ) from None
        if wait_seconds <= 0 or waiting <= 0:
            raise ValueError("Lazy wait values must be positive whole numbers.")
        config.lazy_throttling_policy = {
            "mode": "wait",
            "max_wait_seconds": wait_seconds,
            "max_waiting_requests": waiting,
        }
    else:
        raise ValueError("Select a valid lazy throttling mode.")

    live_burn_mode = (form.get("live_burn_mode") or "").strip().lower()
    cost_margin_raw = (form.get("live_burn_cost_margin") or "").strip()
    token_margin_raw = (form.get("live_burn_token_margin") or "").strip()
    if live_burn_mode == "unchanged":
        if cost_margin_raw or token_margin_raw:
            raise ValueError(
                "Chat streaming live-burn is unchanged; leave its margins blank."
            )
    elif live_burn_mode in {"enable", "disable"}:
        policy = parse_streaming_live_burn_surface_form_policy(
            CHAT_STREAMING_LIVE_BURN_SURFACE,
            enabled=live_burn_mode == "enable",
            cost_margin_eur=cost_margin_raw,
            token_margin=token_margin_raw,
            existing_policy=None,
            max_abs_cost_margin_eur=settings.CHAT_STREAMING_LIVE_BURN_MAX_ABS_COST_MARGIN_EUR,
            max_abs_token_margin=settings.CHAT_STREAMING_LIVE_BURN_MAX_ABS_TOKEN_MARGIN,
        )
        config.chat_streaming_live_burn_policy = policy.to_metadata()
    else:
        raise ValueError("Select a valid chat streaming live-burn mode.")

    return config


def _parse_batch_input_source(
    form: dict[str, str], settings: Settings
) -> KeyConfiguration:
    """One input source: guided controls OR the advanced document."""
    mode = (form.get("input_mode") or "").strip().lower()
    if mode not in {_BATCH_INPUT_GUIDED, _BATCH_INPUT_ADVANCED}:
        raise ValueError("Select a supported input mode: guided or advanced.")
    document_raw = (form.get("configuration_json") or "").strip()

    if mode == _BATCH_INPUT_ADVANCED:
        if not document_raw:
            raise ValueError(
                "Advanced mode uses the configuration document; enter it."
            )
        for field, expected in _BATCH_GUIDED_POLICY_DEFAULTS.items():
            if (form.get(field) or "").strip().lower() != expected:
                raise ValueError(
                    "Advanced mode uses the configuration document; leave the "
                    "guided policy controls at their defaults."
                )
        for _action_field, value_field, _attribute, _label in _BATCH_QUOTA_FIELDS:
            if (form.get(value_field) or "").strip():
                raise ValueError(
                    "Advanced mode uses the configuration document; leave the "
                    "guided policy values blank."
                )
        for _action_field, value_field, _member in _BATCH_RATE_FIELDS:
            if (form.get(value_field) or "").strip():
                raise ValueError(
                    "Advanced mode uses the configuration document; leave the "
                    "guided policy values blank."
                )
        for _mode_field, value_field, _label in _BATCH_LIST_FIELDS:
            if (form.get(value_field) or "").strip():
                raise ValueError(
                    "Advanced mode uses the configuration document; leave the "
                    "guided policy lists blank."
                )
        if (
            (form.get("lazy_wait_seconds") or "").strip()
            or (form.get("lazy_waiting") or "").strip()
            or (form.get("live_burn_cost_margin") or "").strip()
            or (form.get("live_burn_token_margin") or "").strip()
        ):
            raise ValueError(
                "Advanced mode uses the configuration document; leave the "
                "guided policy values blank."
            )
        config = parse_key_configuration_file(document_raw.encode("utf-8"))
        if config.is_empty():
            raise ValueError(
                "The configuration document requests no key configuration change."
            )
        return config

    if document_raw:
        raise ValueError(
            "Guided mode uses the form controls; leave the configuration "
            "document blank."
        )
    config = _parse_batch_guided_policy(form, settings)
    if config.is_empty():
        raise ValueError(
            "Choose at least one policy change or use the advanced document."
        )
    return config


def _batch_requires_fenced_confirmation(plan_document: dict[str, Any]) -> bool:
    """Fresh fenced confirmation gate (rendering-side prediction of the law).

    The shared fenced law requires the FRESH apply-time confirmation exactly
    when the submitted configuration explicitly carries
    ``external_tool_policy`` (the service's ``config.has`` check): an
    explicitly set/replaced fenced block requires the checkbox, including an
    ``already_at_target`` repeat of the same reviewed operation. A RETAINED
    fenced policy on a key that is otherwise only quota/rate edited does NOT
    require it - the gate therefore inspects the reviewed INPUT policy only,
    never the retained after-targets.
    """
    policy = plan_document.get("policy")
    if not isinstance(policy, dict):
        return False
    external = policy.get("external_tool_policy")
    return isinstance(external, dict) and external.get("mode") == EXTERNAL_TOOL_FENCED


# ---------------------------------------------------------------------------
# Runtime scope (caller-owned transaction; the service is flush-only)
# ---------------------------------------------------------------------------


@asynccontextmanager
async def _admin_key_batch_runtime_scope(
    request: Request,
) -> AsyncIterator[tuple[Settings, KeyBatchService]]:
    session_factory = get_sessionmaker_from_app(request)
    async with session_factory() as session:
        async with session.begin():
            settings = _settings(request)
            keys_repository = GatewayKeysRepository(session)
            one_time_secrets_repository = OneTimeSecretsRepository(session)
            audit_repository = AuditRepository(session)
            key_service = KeyService(
                settings=settings,
                gateway_keys_repository=keys_repository,
                one_time_secrets_repository=one_time_secrets_repository,
                audit_repository=audit_repository,
                model_routes_repository=ModelRoutesRepository(session),
            )
            batch_service = KeyBatchService(
                gateway_keys_repository=keys_repository,
                cohorts_repository=CohortsRepository(session),
                key_service=key_service,
            )
            yield settings, batch_service, keys_repository


async def _load_batch_key_labels(
    request: Request, key_ids: tuple[str, ...]
) -> dict[str, str]:
    """Read-only public labels for the reviewed key set (bounded)."""
    if not key_ids:
        return {}
    try:
        session_factory = get_sessionmaker_from_app(request)
        async with session_factory() as session:
            async with session.begin():
                rows = await GatewayKeysRepository(session).get_gateway_keys_by_ids(
                    key_ids=[uuid.UUID(value) for value in key_ids]
                )
        return {
            str(row.id): f"{row.key_prefix or ''}{row.public_key_id or ''}"
            for row in rows
        }
    except (AttributeError, RuntimeError, ValueError):
        return {}


# ---------------------------------------------------------------------------
# Readable review helpers (rendering only; no policy logic)
# ---------------------------------------------------------------------------


# Field-specific null labels (the document semantics differ per field).
_BATCH_NULL_LABELS: dict[str, str] = {
    "cost_limit_eur": "Unlimited (null)",
    "token_limit_total": "Unlimited (null)",
    "request_limit_total": "Unlimited (null)",
    "allowed_providers": "Unrestricted (null)",
    "responses_policy": "Cleared (null)",
    "rate_limit_policy": "Cleared (null)",
    "lazy_throttling_policy": "Removed (null) - deployment default applies",
    "chat_streaming_live_burn_policy": "n/a (object only; use the CLI to disable)",
    "external_tool_policy": "Removed (null)",
}

_BATCH_TOKEN_QUANTITY_FIELDS: frozenset[str] = frozenset(
    {"token_limit_total", "tokens_per_minute"}
)

# Canonical configuration documents carry money as STRINGS (Decimal is
# exported via str(), so quantized snapshots can read "0E-9"); these
# fields render through the common numeric formatter, and identifier-like
# strings (which valid documents do not carry in these fields) would
# pass through the formatter unchanged anyway.
_BATCH_MONEY_FIELDS: frozenset[str] = frozenset({"cost_limit_eur"})


def _batch_finite_decimal(value: Any) -> Decimal | None:
    try:
        number = Decimal(str(value).strip())
    except (InvalidOperation, ValueError, TypeError):
        return None
    return number if number.is_finite() else None

_RATE_MEMBER_LABELS: dict[str, str] = {
    "requests_per_minute": "requests per window",
    "tokens_per_minute": "tokens per window",
    "max_concurrent_requests": "concurrent requests",
    "window_seconds": "window (seconds)",
}


def _batch_rate_policy_readable(value: Any) -> str:
    if not isinstance(value, dict) or not value:
        return str(value)
    parts: list[str] = []
    for member in sorted(value):
        raw = value[member]
        if raw is None:
            text = "inherit (null)"
        elif member == "tokens_per_minute":
            # Token quantities render through the shared M-token display
            # with the exact count beside it (the request/window members
            # keep plain grouped formatting; raw JSON stays exact).
            number = _batch_finite_decimal(raw)
            if number is not None and number == 0:
                text = "0 (zero)"
            elif number is not None:
                text = (
                    f"{format_tokens_m(number)}M tokens "
                    f"({format_number(number)} exact)"
                )
            else:
                text = format_number(raw) or str(raw)
        else:
            text = format_number(raw) or str(raw)
        parts.append(f"{_RATE_MEMBER_LABELS.get(member, member)}: {text}")
    return ", ".join(parts)


def _batch_config_value_readable(field: str, value: Any) -> str:
    """Readable diff/summary rendering (display only; raw JSON unchanged).

    Common comma grouping for counts/money, M-token display for token
    quantities (exact value retained beside it), actual zero rendered
    ``0``, and field-specific null labels. The exact raw plan JSON stays
    available in the review disclosure.
    """
    if value is None:
        return _BATCH_NULL_LABELS.get(field, "null")
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, (int, Decimal)) or (
        isinstance(value, float) and not isinstance(value, bool)
    ):
        if field in _BATCH_TOKEN_QUANTITY_FIELDS:
            return f"{format_tokens_m(value)}M tokens ({format_number(value)} exact)"
        if value == 0:
            return "0 (zero)"
        return format_number(value) or str(value)
    if isinstance(value, str):
        number = _batch_finite_decimal(value)
        if number is not None:
            if number == 0:
                return "0 (zero)"
            if field in _BATCH_TOKEN_QUANTITY_FIELDS:
                return (
                    f"{format_tokens_m(number)}M tokens "
                    f"({format_number(number)} exact)"
                )
            return format_number(number)
        return value
    if isinstance(value, list):
        if not value:
            if field in {"allowed_models", "allowed_endpoints"}:
                return "Deny all (empty list)"
            if field == "allowed_providers":
                return "Deny all (empty list)"
            return "[] (empty list)"
        if len(value) <= 12 and all(isinstance(item, str) for item in value):
            preview = ", ".join(value[:12])
            suffix = "" if len(value) <= 12 else f", … +{len(value) - 12} more"
            return f"{len(value)}: {preview}{suffix}"
        return f"{len(value)} item(s)"
    if isinstance(value, dict):
        if field == "rate_limit_policy":
            return _batch_rate_policy_readable(value)
        import json as _json

        return _json.dumps(value, sort_keys=True, separators=(",", ":"))
    return str(value)


def _batch_document_field_readable(
    document: Any, field: str, value: Any
) -> str:
    """Complete-state-aware rendering of one document field.

    An empty model/endpoint allow list does NOT deny on its own when the
    document's separate allow-all flag is true, and it cannot be read as
    deny when the flag is ABSENT from a (possibly partial) change document
    - the key's existing flag is preserved then. Both states render with
    neutral wording; deny-all is derived only from an explicit complete
    state (flag present and false). Providers keep their deny-all meaning
    (no flag).
    """
    if (
        field in {"allowed_models", "allowed_endpoints"}
        and value == []
        and isinstance(document, dict)
    ):
        flag_field = (
            "allow_all_models"
            if field == "allowed_models"
            else "allow_all_endpoints"
        )
        flag = document.get(flag_field)
        if flag is True:
            return "empty list (the allow-all flag grants access)"
        if flag is None:
            # Absent from this (possibly partial) change document: the
            # key's existing flag is preserved, so deny cannot be derived.
            return "empty list (the allow-all flag is not set by this change)"
    return _batch_config_value_readable(field, value)


def _batch_policy_summary(policy: dict[str, Any]) -> dict[str, str]:
    summary: dict[str, str] = {}
    for field in sorted(policy):
        if field == "schema_version":
            continue
        summary[field] = _batch_document_field_readable(policy, field, policy[field])
    return summary


def _batch_quota_column(
    document: dict[str, Any], field: str
) -> tuple[str, str]:
    """(readable text, raw sort key) for one quota field of a key document.

    Missing field = key document does not administer it (rendered as a
    plain dash, sorting as missing); explicit null = the field-specific
    unlimited/unrestricted/inherit meaning. The raw sort key is the
    canonical UNGROUPED exact decimal (format_raw_decimal): comma-grouped
    or M-scaled text would fall back to the sorter's bounded Number()
    path and misorder large adjacent 64-bit counts; grouping/M scaling is
    display-only.
    """
    if field not in document:
        return ("—", "")
    value = document[field]
    if value is None:
        return (_BATCH_NULL_LABELS.get(field, "null"), "")
    raw = format_raw_decimal(value) or str(value)
    if value == 0:
        # Actual zero renders 0 (never a scaled 0M).
        return ("0 (zero)", "0")
    if field in _BATCH_TOKEN_QUANTITY_FIELDS:
        return (
            f"{format_tokens_m(value)}M tokens ({format_number(value)} exact)",
            raw,
        )
    return (format_number(value) or str(value), raw)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


async def _batch_form_choices(
    request: Request, form: dict[str, str]
) -> dict[str, Any]:
    """Bounded initial option lists for the batch form's record controls.

    Allow-list catalogs reuse the shared policy catalog kinds (latest 100
    plus older server search); direct entry remains available, and the
    submitted values are never bounded by the display batch.
    """
    return await _load_admin_record_choices_safe(
        request,
        (
            ("cohort_id", "cohort", (form.get("cohort_id") or "").strip() or None),
            ("key_ids", "key", ((form.get("key_ids") or "").strip() or None)),
            (
                "providers_value",
                "policy_provider",
                (form.get("providers_value") or "").strip() or None,
            ),
            (
                "models_value",
                "policy_model",
                (form.get("models_value") or "").strip() or None,
            ),
            (
                "endpoints_value",
                "endpoint",
                (form.get("endpoints_value") or "").strip() or None,
            ),
        ),
    )


@router.get("/key-batch", response_class=HTMLResponse)
async def batch_key_form(request: Request) -> Response:
    """Discoverable, clearly separate "Change existing keys" entry."""
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found(request)
    page_context = await _admin_page_context(request)
    if isinstance(page_context, Response):
        return page_context
    admin, csrf_token = page_context
    form = _default_batch_form()
    choices = await _batch_form_choices(request, form)
    return templates.TemplateResponse(
        request,
        "keys/batch_form.html",
        {
            "admin": admin,
            "csrf_token": csrf_token,
            "form": _admin_redact_key_form_values(form, settings),
            "choices": choices,
            "choice_labels": {},
            "max_keys": KEY_BATCH_MAX_KEYS,
            "error": None,
            "diagnostic_id": None,
        },
    )


@router.post("/key-batch/plan", response_class=HTMLResponse)
async def batch_key_plan(
    request: Request,
    csrf_token: str = Form(""),
    input_mode: str = Form(_BATCH_INPUT_GUIDED),
    selection_kind: str = Form("cohort"),
    cohort_id: str = Form(""),
    key_ids: str = Form(""),
    # POST defaults are EMPTY: an unchecked HTML checkbox submits nothing,
    # and the active default applies to the GET form state only (an
    # unchecked box must not silently re-include active).
    status_active: str = Form(""),
    status_suspended: str = Form(""),
    status_revoked: str = Form(""),
    cost_action: str = Form("unchanged"),
    cost_value: str = Form(""),
    token_action: str = Form("unchanged"),
    token_value: str = Form(""),
    request_action: str = Form("unchanged"),
    request_value: str = Form(""),
    rate_action_requests: str = Form("unchanged"),
    rate_value_requests: str = Form(""),
    rate_action_tokens: str = Form("unchanged"),
    rate_value_tokens: str = Form(""),
    rate_action_concurrency: str = Form("unchanged"),
    rate_value_concurrency: str = Form(""),
    rate_action_window: str = Form("unchanged"),
    rate_value_window: str = Form(""),
    providers_mode: str = Form("unchanged"),
    providers_value: str = Form(""),
    models_mode: str = Form("unchanged"),
    models_value: str = Form(""),
    endpoints_mode: str = Form("unchanged"),
    endpoints_value: str = Form(""),
    lazy_mode: str = Form("unchanged"),
    lazy_wait_seconds: str = Form(""),
    lazy_waiting: str = Form(""),
    live_burn_mode: str = Form("unchanged"),
    live_burn_cost_margin: str = Form(""),
    live_burn_token_margin: str = Form(""),
    configuration_json: str = Form(""),
) -> Response:
    """READ ONLY core plan + purpose-bound signed review state.

    The core plan mutates nothing and writes no audit row; the caller's
    read-only transaction exits normally (a no-write commit).
    """
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found(request)

    action_context = await _admin_action_context(request, csrf_token=csrf_token)
    if isinstance(action_context, Response):
        return action_context

    form = {
        "input_mode": input_mode,
        "selection_kind": selection_kind,
        "cohort_id": cohort_id,
        "key_ids": key_ids,
        "status_active": status_active,
        "status_suspended": status_suspended,
        "status_revoked": status_revoked,
        "cost_action": cost_action,
        "cost_value": cost_value,
        "token_action": token_action,
        "token_value": token_value,
        "request_action": request_action,
        "request_value": request_value,
        "rate_action_requests": rate_action_requests,
        "rate_value_requests": rate_value_requests,
        "rate_action_tokens": rate_action_tokens,
        "rate_value_tokens": rate_value_tokens,
        "rate_action_concurrency": rate_action_concurrency,
        "rate_value_concurrency": rate_value_concurrency,
        "rate_action_window": rate_action_window,
        "rate_value_window": rate_value_window,
        "providers_mode": providers_mode,
        "providers_value": providers_value,
        "models_mode": models_mode,
        "models_value": models_value,
        "endpoints_mode": endpoints_mode,
        "endpoints_value": endpoints_value,
        "lazy_mode": lazy_mode,
        "lazy_wait_seconds": lazy_wait_seconds,
        "lazy_waiting": lazy_waiting,
        "live_burn_mode": live_burn_mode,
        "live_burn_cost_margin": live_burn_cost_margin,
        "live_burn_token_margin": live_burn_token_margin,
        "configuration_json": configuration_json,
    }

    async def _rerender(error: str, *, status_code: int = 400) -> Response:
        # Privacy law (207 advanced editor, reused): on a REFUSED planning
        # attempt the advanced configuration document is not redisplayed.
        # Generic free-text redaction cannot mask arbitrary JSON credential
        # values, so the document field is blanked before any rerender;
        # the selection/status scope and safe choices are retained.
        safe_form = dict(form)
        safe_form["configuration_json"] = ""
        choices = await _batch_form_choices(request, safe_form)
        return templates.TemplateResponse(
            request,
            "keys/batch_form.html",
            {
                "admin": action_context.admin_user,
                "csrf_token": csrf_token,
                "form": _admin_redact_key_form_values(safe_form, settings),
                "choices": choices,
                "choice_labels": _choice_selected_labels(
                    choices,
                    (
                        ("cohort_id", (safe_form.get("cohort_id") or "").strip() or None),
                        ("key_ids", (safe_form.get("key_ids") or "").strip() or None),
                    ),
                ),
                "max_keys": KEY_BATCH_MAX_KEYS,
                "error": error,
                "diagnostic_id": _admin_diagnostic_id(request),
            },
            status_code=status_code,
        )

    # Fixed safe input validation BEFORE any service call.
    try:
        statuses = _parse_batch_statuses(form)
        selection = _parse_batch_selection(form)
        policy = _parse_batch_input_source(form, settings)
    except (KeyManagementError, KeyConfigurationError, ValueError) as exc:
        message = exc.safe_message if isinstance(exc, KeyManagementError) else str(exc)
        return await _rerender(_admin_redact_key_form_value(message, settings))

    # The CORE builds the strict non-secret plan (no mutation, no audit).
    # Rendering the reviewed document and binding the purpose-bound token
    # run in the SAME controlled block: an oversize generated plan is a
    # fixed safe refusal, never a 500.
    try:
        async with _admin_key_batch_runtime_scope(request) as (
            _settings_obj,
            batch_service,
            _keys_repository,
        ):
            plan = await batch_service.plan(
                cohort_id=selection["cohort_id"],
                key_ids=selection["key_ids"],
                statuses=statuses,
                policy=policy,
            )
            plan_document = render_key_batch_plan(plan)
    except KeyBatchError as exc:
        _log_admin_action_failure(
            request,
            exc=exc,
            admin_id=action_context.admin_user.id,
            owner_id=None,
            cohort_id=selection["cohort_id"],
            email_delivery_mode=None,
        )
        return await _rerender(exc.safe_message)
    except AdminReviewIntentError as exc:
        _log_admin_action_failure(
            request,
            exc=exc,
            admin_id=action_context.admin_user.id,
            owner_id=None,
            cohort_id=selection["cohort_id"],
            email_delivery_mode=None,
        )
        return await _rerender(exc.message)
    except KeyManagementError as exc:
        _log_admin_action_failure(
            request,
            exc=exc,
            admin_id=action_context.admin_user.id,
            owner_id=None,
            cohort_id=selection["cohort_id"],
            email_delivery_mode=None,
        )
        return await _rerender(exc.safe_message)
    except Exception as exc:  # noqa: BLE001 - plan is read-only; safe fallback
        _log_admin_action_failure(
            request,
            exc=exc,
            admin_id=action_context.admin_user.id,
            owner_id=None,
            cohort_id=selection["cohort_id"],
            email_delivery_mode=None,
        )
        return await _rerender(
            "The batch plan could not be prepared right now; try again."
        )

    try:
        token = build_batch_review_token(
            admin_session_secret=settings.ADMIN_SESSION_SECRET,
            admin_user_id=action_context.admin_user.id,
            admin_session_id=action_context.admin_session.id,
            plan_document=plan_document,
        )
    except KeyBatchError as exc:
        # The strict re-parse inside the builder refuses a non-conformant
        # document (defensive: the service contract renders conformant
        # documents; a violation is a fixed safe refusal, never a 500).
        _log_admin_action_failure(
            request,
            exc=exc,
            admin_id=action_context.admin_user.id,
            owner_id=None,
            cohort_id=selection["cohort_id"],
            email_delivery_mode=None,
        )
        return await _rerender(exc.safe_message)
    except AdminReviewIntentError as exc:
        _log_admin_action_failure(
            request,
            exc=exc,
            admin_id=action_context.admin_user.id,
            owner_id=None,
            cohort_id=selection["cohort_id"],
            email_delivery_mode=None,
        )
        return await _rerender(exc.message)

    key_labels = await _load_batch_key_labels(request, plan.key_ids)
    cohort_label = None
    if plan.cohort_id:
        choices = await _batch_form_choices(
            request, {"cohort_id": plan.cohort_id, "key_ids": ""}
        )
        for option in choices.get("cohort_id", ()):
            if option.id == plan.cohort_id:
                cohort_label = option.label
                break

    plan_rows = []
    for entry in plan.keys:
        other_changes = [
            (
                _BATCH_FIELD_LABELS.get(change["field"], change["field"]),
                _batch_document_field_readable(
                    entry.before, change["field"], change["before"]
                ),
                _batch_document_field_readable(
                    entry.after, change["field"], change["after"]
                ),
            )
            for change in entry.changes
            if change["field"] not in {"request_limit_total", "token_limit_total"}
        ]
        plan_rows.append(
            {
                "key_id": entry.key_id,
                "label": key_labels.get(entry.key_id, ""),
                "request_before": _batch_quota_column(
                    entry.before, "request_limit_total"
                ),
                "request_after": _batch_quota_column(
                    entry.after, "request_limit_total"
                ),
                "token_before": _batch_quota_column(
                    entry.before, "token_limit_total"
                ),
                "token_after": _batch_quota_column(
                    entry.after, "token_limit_total"
                ),
                "other_changes": other_changes,
            }
        )

    response = templates.TemplateResponse(
        request,
        "keys/batch_review.html",
        {
            "admin": action_context.admin_user,
            "csrf_token": csrf_token,
            "plan": plan_document,
            "plan_rows": plan_rows,
            "key_labels": key_labels,
            "cohort_label": cohort_label or plan.cohort_id,
            "policy": plan_document["policy"],
            "policy_summary": _batch_policy_summary(plan_document["policy"]),
            "field_labels": _BATCH_FIELD_LABELS,
            "requires_fenced_confirmation": _batch_requires_fenced_confirmation(
                plan_document
            ),
            "batch_review_intent": token,
            "error": None,
        },
    )
    _set_no_store_headers(response)
    return response


@router.post("/key-batch/apply", response_class=HTMLResponse)
async def batch_key_apply(request: Request) -> Response:
    """Verify/rebind/strict-reparse the review state, then execute it.

    The signed review token is never retained on the result page. A
    repeat of the SAME valid reviewed plan is an ordinary repeat: the
    core decides it as the ``already_at_target`` outcome (zero writes,
    zero new audits) when the selected keys CURRENTLY equal the target -
    a present-state equality decision, not a historical receipt lookup.

    The signed review token is the largest single form field (up to
    ~10.67 MiB), far above Starlette's default 1 MiB per-field cap, so this
    route parses the form itself with the bounded envelope headroom
    (no files) instead of the default auto-form dependency parsing.
    """
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found(request)

    try:
        raw_form = await request.form(
            max_part_size=_BATCH_FORM_MAX_PART_BYTES,
            max_fields=_BATCH_FORM_MAX_FIELDS,
            max_files=0,
        )
    except (MultiPartException, StarletteHTTPException):
        # Starlette re-raises the bounded-parse MultiPartException as a
        # framework HTTPException inside an ASGI app; both map to the same
        # fixed safe refusal (no size/field detail redisplayed).
        return _admin_error_page(
            request, status_code=400, message=_BATCH_FORM_TOO_LARGE_MESSAGE
        )
    csrf_token = str(raw_form.get("csrf_token") or "")
    batch_review_intent = str(raw_form.get("batch_review_intent") or "")
    confirm_apply = str(raw_form.get("confirm_apply") or "")
    confirm_external_tool_fenced = str(
        raw_form.get("confirm_external_tool_fenced") or ""
    )
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
        plan_document = verify_batch_review_token(
            admin_session_secret=settings.ADMIN_SESSION_SECRET,
            token=batch_review_intent,
            admin_user_id=action_context.admin_user.id,
            admin_session_id=action_context.admin_session.id,
        )
        plan = parse_key_batch_plan(plan_document)
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
    except (KeyBatchError, ValueError) as exc:
        _log_admin_action_failure(
            request,
            exc=exc,
            admin_id=action_context.admin_user.id,
            owner_id=None,
            cohort_id=None,
            email_delivery_mode=None,
        )
        return _safe_400(exc.safe_message if isinstance(exc, KeyBatchError) else str(exc))

    verified_cohort_id = (
        uuid.UUID(plan_document["cohort_id"])
        if plan_document.get("cohort_id")
        else None
    )
    try:
        if not _is_checked(confirm_apply):
            raise ValueError("Confirm the reviewed key batch plan before applying it.")
        cleaned_reason, reason_error = _admin_bounded_reason(reason)
        if reason_error is not None:
            raise ValueError(reason_error)
        if cleaned_reason is None:
            raise ValueError("Enter an audit reason before applying the batch.")
        cleaned_reason = _admin_redact_key_form_value(cleaned_reason, settings)
        confirm_fenced = _is_checked(confirm_external_tool_fenced)
        if _batch_requires_fenced_confirmation(plan_document) and not confirm_fenced:
            raise ValueError(
                "Provide the fresh fenced external-tool confirmation before applying."
            )
    except (KeyBatchError, ValueError) as exc:
        _log_admin_action_failure(
            request,
            exc=exc,
            admin_id=action_context.admin_user.id,
            owner_id=None,
            cohort_id=verified_cohort_id,
            email_delivery_mode=None,
        )
        return _safe_400(exc.safe_message if isinstance(exc, KeyBatchError) else str(exc))

    # Execute the SAME reviewed plan in the caller-owned transaction.
    try:
        async with _admin_key_batch_runtime_scope(request) as (
            _settings_obj,
            batch_service,
            _keys_repository,
        ):
            result = await batch_service.apply(
                plan=plan,
                reason=cleaned_reason,
                actor_admin_id=action_context.admin_user.id,
                confirm_external_tool_fenced=confirm_fenced,
            )
    except KeyBatchError as exc:
        _log_admin_action_failure(
            request,
            exc=exc,
            admin_id=action_context.admin_user.id,
            owner_id=None,
            cohort_id=verified_cohort_id,
            email_delivery_mode=None,
        )
        return _safe_400(exc.safe_message)
    except (KeyManagementError, KeyConfigurationError, ValueError) as exc:
        _log_admin_action_failure(
            request,
            exc=exc,
            admin_id=action_context.admin_user.id,
            owner_id=None,
            cohort_id=verified_cohort_id,
            email_delivery_mode=None,
        )
        message = exc.safe_message if isinstance(exc, KeyManagementError) else str(exc)
        return _safe_400(message)

    key_labels = await _load_batch_key_labels(request, result.key_ids)
    response = templates.TemplateResponse(
        request,
        "keys/batch_result.html",
        {
            "admin": action_context.admin_user,
            "result": result,
            "plan": plan_document,
            "key_labels": key_labels,
            "reason": cleaned_reason,
            "status_labels": {
                "applied": (
                    "The reviewed batch was applied atomically with per-key audits."
                ),
                "already_at_target": (
                    "Every selected key already equals the reviewed target: no "
                    "writes and no new audit rows were made."
                ),
                "no_change": (
                    "No eligible keys remained for this reviewed selection."
                ),
            },
        },
    )
    _set_no_store_headers(response)
    return response
