"""Strict versioned NON-secret plan file for reviewed replay maintenance.

The extend plan binds the exact reviewed scope, time filters, selected
lifetime, include-expired choice, safe aggregate counts, and one public
optimistic source-set/configuration fingerprint. It never serializes raw
HMAC digests, provider identifiers, replay-row UUID lists, credentials,
or conversation content. Parsing refuses unknown fields, duplicate keys,
wrong types, non-finite constants, recognized secret shapes, and
oversized files with fixed safe vocabulary (no file bodies or values are
echoed). These are public optimistic guards, not authentication or
replay authority.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

# Fixed safe vocabulary shared with the shared maintenance service.
EXCLUSION_REASON_KEY_NOT_ACTIVE_OR_VALID = "key_not_active_or_valid"
EXCLUSION_REASON_LEDGER_NOT_FINALIZED = "ledger_not_finalized"
EXCLUSION_REASON_UNSUPPORTED_KIND = "unsupported_kind"
EXCLUSION_REASON_HMAC_VERSION_UNAVAILABLE = "hmac_version_unavailable"
EXCLUSION_REASON_OUTSIDE_LIFETIME = "outside_lifetime"
EXCLUSION_REASON_EXPIRED_NOT_INCLUDED = "expired_not_included"

EXCLUSION_REASON_CODES = frozenset(
    {
        EXCLUSION_REASON_KEY_NOT_ACTIVE_OR_VALID,
        EXCLUSION_REASON_LEDGER_NOT_FINALIZED,
        EXCLUSION_REASON_UNSUPPORTED_KIND,
        EXCLUSION_REASON_HMAC_VERSION_UNAVAILABLE,
        EXCLUSION_REASON_OUTSIDE_LIFETIME,
        EXCLUSION_REASON_EXPIRED_NOT_INCLUDED,
    }
)

REPLAY_MAINTENANCE_PLAN_SCHEMA_VERSION = 1
REPLAY_PLAN_OPERATION = "extend"
REPLAY_PLAN_MAX_BYTES = 32 * 1024

# Known secret shapes reused from the existing redaction contract (finite,
# recognized authentication/provider patterns - not a content sanitizer).
from slaif_gateway.utils.redaction import (  # noqa: E402
    _BEARER_PATTERN,
    _GATEWAY_KEY_TEXT_PATTERN,
    _PROVIDER_KEY_PATTERN,
    _SENSITIVE_ASSIGNMENT_PATTERN,
)

_SECRET_SHAPE_PATTERNS = (
    _GATEWAY_KEY_TEXT_PATTERN,
    _BEARER_PATTERN,
    _PROVIDER_KEY_PATTERN,
    _SENSITIVE_ASSIGNMENT_PATTERN,
)

_UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")


class ReplayMaintenanceError(ValueError):
    """A safe, fixed-message replay maintenance error.

    Messages use fixed vocabulary only; they never echo file bodies,
    paths, field values, digests, or operator-supplied input.
    """

    def __init__(self, safe_message: str, *, error_code: str) -> None:
        self.safe_message = safe_message
        self.error_code = error_code
        super().__init__(safe_message)


class ReplayMaintenanceStaleError(ReplayMaintenanceError):
    """The reviewed expected pre-state no longer matches the live rows."""


@dataclass(frozen=True, slots=True)
class ReplayScope:
    """Exactly one explicit maintenance scope (never implicit all-rows)."""

    key_id: uuid.UUID | None = None
    cohort_id: uuid.UUID | None = None
    all_active: bool = False

    @property
    def scope_text(self) -> str:
        if self.key_id is not None:
            return f"key:{self.key_id}"
        if self.cohort_id is not None:
            return f"cohort:{self.cohort_id}"
        return "all-active"


def parse_replay_scope(
    *,
    key_id: str | None = None,
    cohort_id: str | None = None,
    all_active: bool = False,
) -> ReplayScope:
    """Validate exactly one explicit scope selection."""
    provided = sum(part is not None for part in (key_id, cohort_id)) + (1 if all_active else 0)
    if provided != 1:
        raise ReplayMaintenanceError(
            "Exactly one scope is required: --key-id, --cohort-id, or --all-active.",
            error_code="replay_maintenance_scope",
        )
    scope = ReplayScope(
        key_id=parse_scope_uuid(key_id, field="--key-id") if key_id is not None else None,
        cohort_id=parse_scope_uuid(cohort_id, field="--cohort-id")
        if cohort_id is not None
        else None,
        all_active=all_active,
    )
    return scope


def parse_scope_uuid(value: str, *, field: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError:
        raise ReplayMaintenanceError(
            f"{field} must be a valid UUID.", error_code="replay_maintenance_scope"
        ) from None


def parse_utc_datetime(value: str | None, *, field: str) -> datetime | None:
    """Parse an explicit UTC creation-time bound (fixed safe errors)."""
    if value is None:
        return None
    text = value.strip()
    if not text:
        raise ReplayMaintenanceError(
            f"{field} must be an ISO 8601 UTC timestamp.",
            error_code="replay_maintenance_time_bound",
        )
    candidate = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        raise ReplayMaintenanceError(
            f"{field} must be an ISO 8601 UTC timestamp.",
            error_code="replay_maintenance_time_bound",
        ) from None
    if parsed.tzinfo is None or parsed.utcoffset() != UTC.utcoffset(None):
        raise ReplayMaintenanceError(
            f"{field} must be an explicit UTC timestamp.",
            error_code="replay_maintenance_time_bound",
        )
    return parsed.astimezone(UTC)


def validate_utc_bounds(
    created_from: datetime | None, created_until: datetime | None
) -> None:
    if (
        created_from is not None
        and created_until is not None
        and created_from > created_until
    ):
        raise ReplayMaintenanceError(
            "Creation bounds must satisfy --created-from <= --created-until.",
            error_code="replay_maintenance_time_bound",
        )


def _fail(field: str, message: str) -> None:
    raise ReplayMaintenanceError(f"{field}: {message}", error_code="replay_maintenance_plan")


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
    except ReplayMaintenanceError:
        raise
    except json.JSONDecodeError:
        _fail("file", f"{label} is not valid JSON.")
    if not isinstance(value, dict):
        _fail("file", "Top level must be a JSON object.")
    return value


def _contains_known_secret_shape(value: Any) -> bool:
    if isinstance(value, str):
        return any(pattern.search(value) for pattern in _SECRET_SHAPE_PATTERNS)
    if isinstance(value, dict):
        return any(_contains_known_secret_shape(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_contains_known_secret_shape(item) for item in value)
    return False


def _require_int(raw: Any, field: str, *, minimum: int, maximum: int) -> int:
    if type(raw) is not int:
        _fail(field, "Value must be an integer.")
    if raw < minimum or raw > maximum:
        _fail(field, "Value is outside the supported range.")
    return raw


def _require_bool(raw: Any, field: str) -> bool:
    if type(raw) is not bool:
        _fail(field, "Value must be a boolean.")
    return raw


def _require_iso_datetime(raw: Any, field: str) -> datetime:
    if not isinstance(raw, str) or not raw:
        _fail(field, "Value must be an ISO 8601 UTC timestamp.")
    try:
        parsed = datetime.fromisoformat(raw[:-1] + "+00:00" if raw.endswith("Z") else raw)
    except ValueError:
        _fail(field, "Value must be an ISO 8601 UTC timestamp.")
    if parsed.tzinfo is None or parsed.utcoffset() != UTC.utcoffset(None):
        _fail(field, "Value must be an explicit UTC timestamp.")
    return parsed.astimezone(UTC)


@dataclass(frozen=True, slots=True)
class ReplayExtendPlan:
    """One reviewed, bounded, monotonic replay expiry extension."""

    schema_version: int
    operation: str
    scope: ReplayScope
    created_from: datetime | None
    created_until: datetime | None
    ttl_seconds: int
    configured_ttl_seconds: int
    include_expired: bool
    previewed_at: datetime
    selected_keys: int
    eligible_references: int
    exclusion_counts: dict[str, int]
    old_expiry_min: datetime | None
    old_expiry_max: datetime | None
    new_expiry_min: datetime | None
    new_expiry_max: datetime | None
    expected_source_fingerprint: str
    expected_source_state_fingerprint: str
    expected_post_state_fingerprint: str


def render_replay_extend_plan(plan: ReplayExtendPlan) -> dict[str, Any]:
    scope: dict[str, Any] = {}
    if plan.scope.key_id is not None:
        scope["key_id"] = str(plan.scope.key_id)
    elif plan.scope.cohort_id is not None:
        scope["cohort_id"] = str(plan.scope.cohort_id)
    else:
        scope["all_active"] = True
    return {
        "schema_version": plan.schema_version,
        "operation": plan.operation,
        "scope": scope,
        "created_from": plan.created_from.isoformat().replace("+00:00", "Z")
        if plan.created_from is not None
        else None,
        "created_until": plan.created_until.isoformat().replace("+00:00", "Z")
        if plan.created_until is not None
        else None,
        "ttl_seconds": plan.ttl_seconds,
        "configured_ttl_seconds": plan.configured_ttl_seconds,
        "include_expired": plan.include_expired,
        "previewed_at": plan.previewed_at.isoformat().replace("+00:00", "Z"),
        "selected_keys": plan.selected_keys,
        "eligible_references": plan.eligible_references,
        "exclusion_counts": {
            code: plan.exclusion_counts.get(code, 0) for code in sorted(EXCLUSION_REASON_CODES)
        },
        "old_expiry_min": plan.old_expiry_min.isoformat().replace("+00:00", "Z")
        if plan.old_expiry_min is not None
        else None,
        "old_expiry_max": plan.old_expiry_max.isoformat().replace("+00:00", "Z")
        if plan.old_expiry_max is not None
        else None,
        "new_expiry_min": plan.new_expiry_min.isoformat().replace("+00:00", "Z")
        if plan.new_expiry_min is not None
        else None,
        "new_expiry_max": plan.new_expiry_max.isoformat().replace("+00:00", "Z")
        if plan.new_expiry_max is not None
        else None,
        "expected_source_fingerprint": plan.expected_source_fingerprint,
        "expected_source_state_fingerprint": plan.expected_source_state_fingerprint,
        "expected_post_state_fingerprint": plan.expected_post_state_fingerprint,
    }


_KNOWN_PLAN_FIELDS = frozenset(
    {
        "schema_version",
        "operation",
        "scope",
        "created_from",
        "created_until",
        "ttl_seconds",
        "configured_ttl_seconds",
        "include_expired",
        "previewed_at",
        "selected_keys",
        "eligible_references",
        "exclusion_counts",
        "old_expiry_min",
        "old_expiry_max",
        "new_expiry_min",
        "new_expiry_max",
        "expected_source_fingerprint",
        "expected_source_state_fingerprint",
        "expected_post_state_fingerprint",
    }
)
_KNOWN_SCOPE_FIELDS = frozenset({"key_id", "cohort_id", "all_active"})


def parse_replay_extend_plan_document(document: dict[str, Any]) -> ReplayExtendPlan:
    for field in document:
        if field not in _KNOWN_PLAN_FIELDS:
            _fail("file", "Unknown top-level field.")
    for field in _KNOWN_PLAN_FIELDS:
        if field not in document:
            _fail("file", "Missing required field.")
    if _contains_known_secret_shape(document):
        _fail("file", "Value carries a recognized secret shape.")
    version = document["schema_version"]
    if type(version) is not int or version != REPLAY_MAINTENANCE_PLAN_SCHEMA_VERSION:
        _fail("schema_version", "Unsupported plan schema version.")
    if document["operation"] != REPLAY_PLAN_OPERATION:
        _fail("operation", "Unsupported plan operation.")
    raw_scope = document["scope"]
    if not isinstance(raw_scope, dict):
        _fail("scope", "Value must be a JSON object.")
    for field in raw_scope:
        if field not in _KNOWN_SCOPE_FIELDS:
            _fail("scope", "Unknown scope field.")
    scope = ReplayScope(
        key_id=(
            uuid.UUID(raw_scope["key_id"])
            if "key_id" in raw_scope
            else None
        ),
        cohort_id=(
            uuid.UUID(raw_scope["cohort_id"])
            if "cohort_id" in raw_scope
            else None
        ),
        all_active=raw_scope.get("all_active") is True,
    )
    provided = sum(part is not None for part in (scope.key_id, scope.cohort_id)) + (
        1 if scope.all_active else 0
    )
    if provided != 1:
        _fail("scope", "Exactly one scope selection is required.")
    if "key_id" in raw_scope and not _UUID_RE.fullmatch(str(raw_scope["key_id"])):
        _fail("scope", "key_id must be a canonical UUID string.")
    if "cohort_id" in raw_scope and not _UUID_RE.fullmatch(str(raw_scope["cohort_id"])):
        _fail("scope", "cohort_id must be a canonical UUID string.")
    created_from = _parse_optional_bound(document["created_from"], "created_from")
    created_until = _parse_optional_bound(document["created_until"], "created_until")
    validate_utc_bounds(created_from, created_until)
    ttl_seconds = _require_int(
        document["ttl_seconds"], "ttl_seconds", minimum=1, maximum=31_536_000
    )
    configured_ttl_seconds = _require_int(
        document["configured_ttl_seconds"],
        "configured_ttl_seconds",
        minimum=1,
        maximum=31_536_000,
    )
    include_expired = _require_bool(document["include_expired"], "include_expired")
    previewed_at = _require_iso_datetime(document["previewed_at"], "previewed_at")
    selected_keys = _require_int(
        document["selected_keys"], "selected_keys", minimum=0, maximum=1_000
    )
    eligible_references = _require_int(
        document["eligible_references"],
        "eligible_references",
        minimum=0,
        maximum=50_000,
    )
    raw_counts = document["exclusion_counts"]
    if not isinstance(raw_counts, dict) or not raw_counts:
        _fail("exclusion_counts", "Value must be a JSON object of reason counts.")
    exclusion_counts: dict[str, int] = {}
    for code, raw_count in raw_counts.items():
        if code not in EXCLUSION_REASON_CODES:
            _fail("exclusion_counts", "Unknown exclusion reason code.")
        exclusion_counts[code] = _require_int(raw_count, code, minimum=0, maximum=50_000)
    old_expiry_min = _parse_optional_bound(document["old_expiry_min"], "old_expiry_min")
    old_expiry_max = _parse_optional_bound(document["old_expiry_max"], "old_expiry_max")
    new_expiry_min = _parse_optional_bound(document["new_expiry_min"], "new_expiry_min")
    new_expiry_max = _parse_optional_bound(document["new_expiry_max"], "new_expiry_max")
    fingerprint = document["expected_source_fingerprint"]
    if not isinstance(fingerprint, str) or not _HEX64_RE.fullmatch(fingerprint):
        _fail("expected_source_fingerprint", "Value must be a 64 character lowercase digest.")
    state_fingerprint = document["expected_source_state_fingerprint"]
    if (
        not isinstance(state_fingerprint, str)
        or not _HEX64_RE.fullmatch(state_fingerprint)
    ):
        _fail(
            "expected_source_state_fingerprint",
            "Value must be a 64 character lowercase digest.",
        )
    post_fingerprint = document["expected_post_state_fingerprint"]
    if (
        not isinstance(post_fingerprint, str)
        or not _HEX64_RE.fullmatch(post_fingerprint)
    ):
        _fail(
            "expected_post_state_fingerprint",
            "Value must be a 64 character lowercase digest.",
        )
    plan = ReplayExtendPlan(
        schema_version=version,
        operation=REPLAY_PLAN_OPERATION,
        scope=scope,
        created_from=created_from,
        created_until=created_until,
        ttl_seconds=ttl_seconds,
        configured_ttl_seconds=configured_ttl_seconds,
        include_expired=include_expired,
        previewed_at=previewed_at,
        selected_keys=selected_keys,
        eligible_references=eligible_references,
        exclusion_counts=exclusion_counts,
        old_expiry_min=old_expiry_min,
        old_expiry_max=old_expiry_max,
        new_expiry_min=new_expiry_min,
        new_expiry_max=new_expiry_max,
        expected_source_fingerprint=fingerprint,
        expected_source_state_fingerprint=state_fingerprint,
        expected_post_state_fingerprint=post_fingerprint,
    )
    # Strict round-trip gate: the parsed document must render back to the
    # EXACT reviewed document (an edited count or bound is refused).
    if render_replay_extend_plan(plan) != document:
        _fail("file", "Document does not round-trip to the reviewed plan.")
    return plan


def _parse_optional_bound(raw: Any, field: str) -> datetime | None:
    if raw is None:
        return None
    return _require_iso_datetime(raw, field)


def parse_replay_extend_plan_file(path: Path) -> ReplayExtendPlan:
    try:
        data = path.read_bytes()
    except OSError:
        raise ReplayMaintenanceError(
            "The extend plan file is not readable.",
            error_code="replay_maintenance_plan",
        ) from None
    document = _load_strict_object(data, REPLAY_PLAN_MAX_BYTES, "Extend plan")
    return parse_replay_extend_plan_document(document)


def write_replay_extend_plan_file(path: Path, plan: ReplayExtendPlan) -> None:
    """Bounded exclusive 0600 write; never overwrite an existing file."""
    import os

    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except OSError:
        raise ReplayMaintenanceError(
            "The extend plan output must be a new writable file.",
            error_code="replay_maintenance_plan",
        ) from None
    payload = (
        json.dumps(render_replay_extend_plan(plan), indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    if len(payload) > REPLAY_PLAN_MAX_BYTES:
        raise ReplayMaintenanceError(
            "The rendered extend plan exceeds the bounded size.",
            error_code="replay_maintenance_plan",
        )
    with os.fdopen(fd, "wb") as stream:
        stream.write(payload)
