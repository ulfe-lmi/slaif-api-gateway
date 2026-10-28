"""Strict, versioned, NON-secret key-clone plan schema (objective 198).

A clone plan is reviewed data, not authority. It records a stable
``operation_uuid``, the source key identity and a canonical configuration
fingerprint, the target owner/cohort, an explicit validity mode, the
canonical version-1 policy document (for operator review), and the
confirmation requirements for execution.

The plan NEVER contains source credentials, provider environment names or
base URLs, token hashes/HMACs, encrypted secrets, raw metadata, usage,
replay rows, or any plaintext key material. It is re-parsed strictly on
execute; unknown or duplicate JSON fields, oversized files, and bad types
are rejected with fixed safe messages that never echo file bodies, paths,
or operator-supplied values.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from slaif_gateway.schemas.key_configuration import (
    KeyConfigurationError,
    key_configuration_export,
    parse_key_configuration,
)

CLONE_PLAN_SCHEMA_VERSION = 1

# The plan wraps a 64 KiB configuration document plus identity/validity
# metadata; a modest, documented envelope bound keeps the file bounded.
MAX_CLONE_PLAN_FILE_BYTES = 128 * 1024
# Bounded maximum for duration-from-now validity: it keeps the derived window
# representable (no timedelta overflow) with a documented, safe ceiling.
MAX_VALIDITY_DURATION_SECONDS = 60 * 60 * 24 * 365 * 1000

# Namespaced receipt key stored on the NEW target key's metadata (objective
# 198 retry safety). It is bounded safe UUIDs/fingerprints/public state only.
CLONE_RECEIPT_METADATA_KEY = "clone_receipt"

VALIDITY_COPY_SOURCE_EXPIRY = "copy-source-expiry"
VALIDITY_DURATION_FROM_NOW = "duration-from-now"
VALIDITY_ABSOLUTE = "absolute"
_VALIDITY_MODES = (
    VALIDITY_COPY_SOURCE_EXPIRY,
    VALIDITY_DURATION_FROM_NOW,
    VALIDITY_ABSOLUTE,
)

_UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
_HEX64_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_PREVIEW_FIELDS = ("valid_from", "valid_until", "note")


class KeyClonePlanError(ValueError):
    """A safe, fixed-message clone-plan or clone-operation error.

    Messages use fixed vocabulary only; they never echo file bodies, paths,
    field values, or operator-supplied input.
    """


def _fail(field: str, message: str) -> None:
    raise KeyClonePlanError(f"{field}: {message}")


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
    _fail("file", f"JSON constant {name} is not allowed.")


def _load_strict_object(data: bytes) -> dict[str, Any]:
    if len(data) > MAX_CLONE_PLAN_FILE_BYTES:
        _fail("file", f"File exceeds {MAX_CLONE_PLAN_FILE_BYTES} bytes.")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        _fail("file", "File must be valid UTF-8 JSON.")
    try:
        value = json.loads(
            text,
            object_pairs_hook=_strict_pairs_hook,
            parse_constant=_strict_constant,
            parse_float=Decimal,
        )
    except KeyClonePlanError:
        raise
    except json.JSONDecodeError:
        _fail("file", "File is not valid JSON.")
    if not isinstance(value, dict):
        _fail("file", "Top level must be a JSON object.")
    return value


def _require_str(document: dict[str, Any], name: str) -> str:
    value = document.get(name, _ABSENT)
    if value is _ABSENT:
        _fail(name, "Field is required.")
    if not isinstance(value, str) or not value.strip():
        _fail(name, "Value must be a non-empty string.")
    return value


def _require_uuid_str(document: dict[str, Any], name: str) -> str:
    value = _require_str(document, name)
    if not _UUID_RE.match(value):
        _fail(name, "Value must be a UUID string.")
    return value


def _optional_uuid_str(document: dict[str, Any], name: str) -> str | None:
    value = document.get(name)
    if value is None:
        return None
    if not isinstance(value, str) or not _UUID_RE.match(value):
        _fail(name, "Value must be null or a UUID string.")
    return value


_ABSENT = object()


def _iso_string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail(name, "Value must be an ISO datetime string.")
    try:
        datetime.fromisoformat(value)
    except ValueError:
        _fail(name, "Value must be a valid ISO datetime string.")
    return value


def _aware_datetime(value: Any, name: str) -> datetime:
    """Parse an ISO datetime, treating a naive value as UTC.

    Naive-to-UTC normalization lets a mixed aware/naive absolute validity
    window be compared predictably (and rejected) instead of raising an
    uncaught parser TypeError.
    """
    if not isinstance(value, str) or not value.strip():
        _fail(name, "Value must be an ISO datetime string.")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        _fail(name, "Value must be a valid ISO datetime string.")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def _parse_validity(document: dict[str, Any]) -> dict[str, Any]:
    raw = document.get("validity", _ABSENT)
    if raw is _ABSENT:
        _fail("validity", "Field is required.")
    if not isinstance(raw, dict):
        _fail("validity", "Value must be a JSON object.")

    mode = raw.get("mode", _ABSENT)
    if mode is _ABSENT:
        _fail("validity.mode", "Field is required.")
    if not isinstance(mode, str) or mode not in _VALIDITY_MODES:
        _fail("validity.mode", "Value must be a supported validity mode.")

    mode_fields = {
        VALIDITY_COPY_SOURCE_EXPIRY: {"source_valid_until"},
        VALIDITY_DURATION_FROM_NOW: {"duration_seconds"},
        VALIDITY_ABSOLUTE: {"valid_from", "valid_until"},
    }
    allowed = {"mode", *mode_fields[mode]}
    extra = sorted(set(raw) - allowed)
    if extra:
        _fail("validity", "Object contains unsupported fields.")

    out: dict[str, Any] = {"mode": mode}
    if mode == VALIDITY_COPY_SOURCE_EXPIRY:
        out["source_valid_until_preview"] = _iso_string(
            raw.get("source_valid_until", _ABSENT), "validity.source_valid_until"
        )
    elif mode == VALIDITY_DURATION_FROM_NOW:
        dur = raw.get("duration_seconds", _ABSENT)
        if dur is _ABSENT:
            _fail("validity.duration_seconds", "Field is required.")
        if isinstance(dur, bool) or not isinstance(dur, int) or dur <= 0:
            _fail("validity.duration_seconds", "Value must be a positive integer.")
        if dur > MAX_VALIDITY_DURATION_SECONDS:
            _fail("validity.duration_seconds", "Value exceeds the bounded maximum.")
        out["duration_seconds"] = dur
    else:  # absolute
        out["valid_from"] = _iso_string(raw.get("valid_from", _ABSENT), "validity.valid_from")
        out["valid_until"] = _iso_string(raw.get("valid_until", _ABSENT), "validity.valid_until")
        if _aware_datetime(out["valid_from"], "validity.valid_from") >= _aware_datetime(
            out["valid_until"], "validity.valid_until"
        ):
            _fail("validity", "valid_until must be after valid_from.")
    return out


def _parse_preview(document: dict[str, Any]) -> dict[str, str | None] | None:
    """Parse the optional non-authoritative review preview block.

    The preview shows the validity window that dry-run previewed; execution
    always re-derives the window from EXECUTION time and the fresh source, so
    the preview is display data only and is ignored by execution.
    """
    raw = document.get("preview")
    if raw is None:
        return None
    if not isinstance(raw, dict):
        _fail("preview", "Value must be a JSON object.")
    extra = sorted(set(raw) - set(_PREVIEW_FIELDS))
    if extra:
        _fail("preview", "Object contains unsupported fields.")
    out: dict[str, str | None] = {}
    for name, value in raw.items():
        if value is not None and (not isinstance(value, str) or not value.strip()):
            _fail(f"preview.{name}", "Value must be null or a non-empty string.")
        out[name] = value
    return out


@dataclass(slots=True)
class KeyClonePlan:
    """A typed, non-secret clone plan (reviewed data, not authority)."""

    operation_uuid: str
    source_gateway_key_id: str
    source_public_key_id: str
    source_fingerprint: str
    target_owner_id: str
    target_cohort_id: str | None
    validity_mode: str
    validity_duration_seconds: int | None
    validity_from: str | None
    validity_until: str | None
    source_valid_until_preview: str | None
    policy: dict[str, Any]
    requires_fenced_confirmation: bool
    preview: dict[str, str | None] | None = None


def parse_clone_plan_document(document: dict[str, Any]) -> KeyClonePlan:
    """Strictly parse one clone-plan document into a typed plan."""
    raw_version = document.get("schema_version", _ABSENT)
    if raw_version is _ABSENT:
        _fail("schema_version", "Field is required.")
    if (
        not isinstance(raw_version, int)
        or isinstance(raw_version, bool)
        or raw_version != CLONE_PLAN_SCHEMA_VERSION
    ):
        _fail("schema_version", "Value must be exactly the current schema version.")

    known = {
        "schema_version",
        "operation_uuid",
        "source_gateway_key_id",
        "source_public_key_id",
        "source_fingerprint",
        "target_owner_id",
        "target_cohort_id",
        "validity",
        "policy",
        "requires_fenced_confirmation",
        "preview",
    }
    extra = sorted(str(k) for k in set(document) - known)
    if extra:
        _fail("schema", "Document contains unsupported fields.")

    operation_uuid = _require_uuid_str(document, "operation_uuid")
    source_id = _require_uuid_str(document, "source_gateway_key_id")
    source_public = _require_str(document, "source_public_key_id")
    fingerprint = _require_str(document, "source_fingerprint")
    if not _HEX64_RE.match(fingerprint):
        _fail("source_fingerprint", "Value must be a 64-character hex digest.")
    target_owner = _require_uuid_str(document, "target_owner_id")
    target_cohort = _optional_uuid_str(document, "target_cohort_id")
    validity = _parse_validity(document)

    raw_policy = document.get("policy", _ABSENT)
    if raw_policy is _ABSENT:
        _fail("policy", "Field is required.")
    if not isinstance(raw_policy, dict):
        _fail("policy", "Value must be a JSON object.")
    try:
        # parse_key_configuration enforces schema_version exactly 1 and all
        # field rules; re-render to the canonical export document so the plan
        # stores exactly what the shared export produces (allowlisted fields,
        # decimal strings).
        parsed_config = parse_key_configuration(raw_policy)
    except KeyConfigurationError as exc:
        raise KeyClonePlanError(str(exc)) from exc
    policy_document = key_configuration_export(parsed_config)

    requires_fenced = document.get("requires_fenced_confirmation", _ABSENT)
    if requires_fenced is _ABSENT:
        _fail("requires_fenced_confirmation", "Field is required.")
    if not isinstance(requires_fenced, bool):
        _fail("requires_fenced_confirmation", "Value must be a boolean.")

    preview = _parse_preview(document)

    return KeyClonePlan(
        operation_uuid=operation_uuid,
        source_gateway_key_id=source_id,
        source_public_key_id=source_public,
        source_fingerprint=fingerprint,
        target_owner_id=target_owner,
        target_cohort_id=target_cohort,
        validity_mode=validity["mode"],
        validity_duration_seconds=validity.get("duration_seconds"),
        validity_from=validity.get("valid_from"),
        validity_until=validity.get("valid_until"),
        source_valid_until_preview=validity.get("source_valid_until_preview"),
        policy=policy_document,
        requires_fenced_confirmation=requires_fenced,
        preview=preview,
    )


def parse_clone_plan_file(data: bytes) -> KeyClonePlan:
    """Read and strictly parse one clone-plan file payload."""
    document = _load_strict_object(data)
    return parse_clone_plan_document(document)


def render_clone_plan(plan: KeyClonePlan) -> dict[str, Any]:
    """Render a typed plan to its strict version-1 document form."""
    validity: dict[str, Any] = {"mode": plan.validity_mode}
    if plan.validity_mode == VALIDITY_COPY_SOURCE_EXPIRY:
        validity["source_valid_until"] = plan.source_valid_until_preview
    elif plan.validity_mode == VALIDITY_DURATION_FROM_NOW:
        validity["duration_seconds"] = plan.validity_duration_seconds
    else:
        validity["valid_from"] = plan.validity_from
        validity["valid_until"] = plan.validity_until
    document = {
        "schema_version": CLONE_PLAN_SCHEMA_VERSION,
        "operation_uuid": plan.operation_uuid,
        "source_gateway_key_id": plan.source_gateway_key_id,
        "source_public_key_id": plan.source_public_key_id,
        "source_fingerprint": plan.source_fingerprint,
        "target_owner_id": plan.target_owner_id,
        "target_cohort_id": plan.target_cohort_id,
        "validity": validity,
        "policy": plan.policy,
        "requires_fenced_confirmation": plan.requires_fenced_confirmation,
    }
    if plan.preview is not None:
        document["preview"] = dict(plan.preview)
    return document


def compute_source_fingerprint(
    *,
    public_key_id: str,
    status: str,
    valid_from: datetime,
    valid_until: datetime,
    key_purpose: str,
    capability_policy_mode: str,
    policy_document: dict[str, Any],
) -> str:
    """Canonical SHA-256 over the source's configuration-affecting state.

    Includes configured policy, status, validity, and purpose/mode identity.
    Deliberately EXCLUDES traffic usage/reservation counters, ``last_used``,
    and ``updated_at`` changes caused solely by usage, so a live source that
    only accrued traffic keeps a stable fingerprint.
    """
    payload = {
        "public_key_id": public_key_id,
        "status": status,
        "valid_from": valid_from.isoformat(),
        "valid_until": valid_until.isoformat(),
        "key_purpose": key_purpose,
        "capability_policy_mode": capability_policy_mode,
        "policy": policy_document,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def compute_policy_fingerprint(policy_document: dict[str, Any]) -> str:
    """Canonical SHA-256 over the reviewed canonical policy document.

    Binds the reviewed policy into the clone-receipt identity so an exact
    repeat is compared against the SAME policy, and lets first execution
    verify the reviewed policy still matches the fresh source. It is dedup
    data, never authentication/replay authority.
    """
    canonical = json.dumps(policy_document, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
