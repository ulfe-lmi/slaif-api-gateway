"""Strict versioned NON-secret plan file for reviewed key-configuration batches.

The reviewed plan binds the exact reviewed scope (one cohort or an exact
UUID list), the finite status filter, the strict version-1 key-configuration
PARTIAL policy document, the exact selected UUIDs with canonical before/after
documents, derived per-key field diffs, bounded source/post state
fingerprints, and honest safe counts. It never serializes key material,
HMAC digests, provider credentials, or usage/counter state. Parsing refuses
unknown fields, duplicate keys, wrong types, non-finite constants,
recognized secret shapes, tampered counts/diffs, and oversized files with
fixed safe vocabulary (no file bodies, IDs of refused values, or
operator-supplied content is echoed). A saved plan is an editable operator
review artifact: it is NOT a signature and it grants no authority.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from slaif_gateway.schemas.key_configuration import (
    _KNOWN_CONFIGURATION_FIELDS,
    KeyConfigurationError,
    parse_key_configuration,
)

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

KEY_BATCH_PLAN_SCHEMA_VERSION = 1
KEY_BATCH_PLAN_OPERATION = "apply"
KEY_BATCH_PLAN_MAX_BYTES = 8 * 1024 * 1024

# Bounded review/apply scope: both the requested and selected sets are
# limited to this many unique keys (overflow is refused, never truncated).
KEY_BATCH_MAX_KEYS = 1000

# Bounded audit reason for the apply operation (UTF-8 bytes).
KEY_BATCH_APPLY_REASON_MAX_BYTES = 512

# Finite persisted key-status vocabulary (validity derives separately).
KEY_BATCH_STATUSES: tuple[str, ...] = ("active", "suspended", "revoked")
KEY_BATCH_STATUS_VALUES: frozenset[str] = frozenset(KEY_BATCH_STATUSES)

KEY_BATCH_SELECTION_COHORT = "cohort"
KEY_BATCH_SELECTION_KEYS = "keys"

_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")

_MISSING = object()


class KeyBatchError(ValueError):
    """A safe, fixed-message key-batch error.

    Messages use fixed vocabulary only; they never echo file bodies,
    paths, field values, digests, or operator-supplied input.
    """

    def __init__(self, safe_message: str, *, error_code: str) -> None:
        self.safe_message = safe_message
        self.error_code = error_code
        super().__init__(safe_message)


class KeyBatchStaleError(KeyBatchError):
    """The reviewed pre-state (membership, status, or configuration) no
    longer matches the live rows; the whole batch is refused."""


def key_batch_state_fingerprint(
    *,
    config_document: dict[str, Any],
    owner_id: uuid.UUID | str,
    cohort_id: uuid.UUID | str | None,
    status: str,
    key_purpose: str,
    valid_from: datetime,
    valid_until: datetime,
) -> str:
    """Bounded fingerprint of the reviewed configured state.

    Covers the canonical version-1 configuration document plus the stable
    identity/lifecycle/scope/validity context. Usage/token/request/cost
    counters, generic ``updated_at``/``last_used_at``, transient
    rate/cache/broker state, and crypto material are deliberately excluded:
    usage-only changes must never invalidate configuration planning.
    """
    context = {
        "config_document": config_document,
        "owner_id": str(owner_id),
        "cohort_id": str(cohort_id) if cohort_id is not None else None,
        "status": status,
        "key_purpose": key_purpose,
        "valid_from": valid_from.isoformat(),
        "valid_until": valid_until.isoformat(),
    }
    payload = json.dumps(
        context, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def key_batch_document_changes(
    before: dict[str, Any], after: dict[str, Any]
) -> tuple[dict[str, Any], ...]:
    """Derived, deterministic per-key field diff (schema_version excluded)."""
    fields = sorted(set(before) | set(after) - {"schema_version"})
    changes: list[dict[str, Any]] = []
    for field in fields:
        if before.get(field, _MISSING) != after.get(field, _MISSING):
            changes.append(
                {"field": field, "before": before.get(field), "after": after.get(field)}
            )
    return tuple(changes)


@dataclass(frozen=True, slots=True)
class KeyBatchPlanKey:
    """One reviewed selected key with canonical before/after documents."""

    key_id: str
    source_fingerprint: str
    post_fingerprint: str
    before: dict[str, Any]
    after: dict[str, Any]
    changes: tuple[dict[str, Any], ...]


@dataclass(frozen=True, slots=True)
class KeyBatchPlan:
    """Strict reviewed plan for one bounded key-configuration batch."""

    schema_version: int
    operation: str
    selection_kind: str
    cohort_id: str | None
    key_ids: tuple[str, ...]
    statuses: tuple[str, ...]
    policy: dict[str, Any]
    keys: tuple[KeyBatchPlanKey, ...]
    selected_count: int
    changed_count: int
    unchanged_count: int
    excluded_by_status: tuple[tuple[str, str], ...]
    planned_at: str


def render_key_batch_plan(plan: KeyBatchPlan) -> dict[str, Any]:
    """Render the exact reviewed document (deterministic key order)."""
    return {
        "schema_version": plan.schema_version,
        "operation": plan.operation,
        "selection_kind": plan.selection_kind,
        "cohort_id": plan.cohort_id,
        "key_ids": list(plan.key_ids),
        "statuses": list(plan.statuses),
        "policy": dict(plan.policy),
        "keys": [
            {
                "key_id": key.key_id,
                "source_fingerprint": key.source_fingerprint,
                "post_fingerprint": key.post_fingerprint,
                "before": dict(key.before),
                "after": dict(key.after),
                "changes": [dict(change) for change in key.changes],
            }
            for key in plan.keys
        ],
        "selected_count": plan.selected_count,
        "changed_count": plan.changed_count,
        "unchanged_count": plan.unchanged_count,
        "excluded_by_status": [
            {"key_id": key_id, "status": status}
            for key_id, status in plan.excluded_by_status
        ],
        "planned_at": plan.planned_at,
    }


def _fail(field: str, message: str) -> None:
    raise KeyBatchError(f"{field}: {message}", error_code="key_batch_plan")


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


def _require_int(value: Any, field: str, *, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        _fail(field, "Value must be an integer.")
    if value < minimum or value > maximum:
        _fail(field, f"Value must be between {minimum} and {maximum}.")
    return value


def _require_uuid(value: Any, field: str) -> str:
    if not isinstance(value, str) or not _UUID_RE.fullmatch(value):
        _fail(field, "Value must be a UUID.")
    return str(uuid.UUID(value))


def _require_fingerprint(value: Any, field: str) -> str:
    if not isinstance(value, str) or not _HEX64_RE.fullmatch(value):
        _fail(field, "Value must be a 64 character lowercase digest.")
    return value


def _require_iso_datetime(value: Any, field: str) -> str:
    if not isinstance(value, str):
        _fail(field, "Value must be an ISO-8601 timestamp.")
    try:
        datetime.fromisoformat(value)
    except ValueError:
        _fail(field, "Value must be a valid ISO-8601 timestamp.")
    return value


def _require_status(value: Any, field: str) -> str:
    if not isinstance(value, str) or value not in KEY_BATCH_STATUS_VALUES:
        _fail(field, "Value must be a persisted key status.")
    return value


_PLAN_TOP_LEVEL_KEYS = frozenset(
    {
        "schema_version",
        "operation",
        "selection_kind",
        "cohort_id",
        "key_ids",
        "statuses",
        "policy",
        "keys",
        "selected_count",
        "changed_count",
        "unchanged_count",
        "excluded_by_status",
        "planned_at",
    }
)
_PLAN_KEY_KEYS = frozenset(
    {
        "key_id",
        "source_fingerprint",
        "post_fingerprint",
        "before",
        "after",
        "changes",
    }
)


def _require_exact_keys(
    document: Any, field: str, expected: frozenset[str]
) -> None:
    if not isinstance(document, dict) or not all(isinstance(k, str) for k in document):
        _fail(field, "Value must be a JSON object.")
    unknown = sorted(set(document) - expected)
    if unknown:
        _fail(field, "Document contains unsupported fields.")
    missing = sorted(expected - set(document))
    if missing:
        _fail(field, "Document is missing required fields.")


def _require_json_object(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict) or not all(isinstance(k, str) for k in value):
        _fail(field, "Value must be a JSON object.")
    return value


def parse_key_batch_plan(document: dict[str, Any]) -> KeyBatchPlan:
    """Strictly parse one reviewed plan document.

    The parse re-derives every derived value (deterministic diffs, counts,
    ordering, consistency between the selection list and the per-key
    entries) and refuses any document that does not round-trip to itself,
    so an edited count, diff, fingerprint, or target is refused.

    The parser guarantees STRUCTURAL integrity only: exact field
    vocabulary, types, bounds, ordering, derived diffs/counts, and
    strict version-1 before/after documents. It is NOT semantic
    target proof: the shared service re-derives the source/target
    state, fingerprints, and repeat/no-op decisions from the strict
    typed policy plus the live locked rows before any first-apply or
    repeat decision.
    """
    if not isinstance(document, dict) or not all(isinstance(k, str) for k in document):
        _fail("file", "Top level must be a JSON object.")
    _refuse_known_secret_shapes(document)
    _require_exact_keys(document, "file", _PLAN_TOP_LEVEL_KEYS)

    version = document["schema_version"]
    if (
        isinstance(version, bool)
        or not isinstance(version, int)
        or version != KEY_BATCH_PLAN_SCHEMA_VERSION
    ):
        _fail("schema_version", "Value must be exactly the current schema version.")
    if document["operation"] != KEY_BATCH_PLAN_OPERATION:
        _fail("operation", "Value must be exactly the batch operation.")

    selection_kind = document["selection_kind"]
    if selection_kind not in (KEY_BATCH_SELECTION_COHORT, KEY_BATCH_SELECTION_KEYS):
        _fail("selection_kind", "Value must be cohort or keys.")

    raw_cohort_id = document["cohort_id"]
    if selection_kind == KEY_BATCH_SELECTION_COHORT:
        cohort_id = _require_uuid(raw_cohort_id, "cohort_id")
    elif raw_cohort_id is not None:
        _fail("cohort_id", "Value must be absent for a key-list selection.")
    else:
        cohort_id = None

    raw_key_ids = document["key_ids"]
    if not isinstance(raw_key_ids, list) or len(raw_key_ids) > KEY_BATCH_MAX_KEYS:
        _fail("key_ids", f"Value must be a list of at most {KEY_BATCH_MAX_KEYS} UUIDs.")
    key_ids = tuple(_require_uuid(item, "key_ids") for item in raw_key_ids)
    if len(set(key_ids)) != len(key_ids):
        _fail("key_ids", "Value must not repeat a key.")
    if key_ids != tuple(sorted(key_ids)):
        _fail("key_ids", "Value must be sorted.")

    raw_statuses = document["statuses"]
    if not isinstance(raw_statuses, list) or not raw_statuses:
        _fail("statuses", "Value must be a non-empty list of statuses.")
    statuses = tuple(sorted({_require_status(item, "statuses") for item in raw_statuses}))
    if list(raw_statuses) != list(statuses):
        _fail("statuses", "Value must be sorted and unique.")

    policy_document = _require_json_object(document["policy"], "policy")
    try:
        policy = parse_key_configuration(policy_document)
    except KeyConfigurationError as exc:
        raise KeyBatchError(
            "policy: The reviewed policy is not a valid version-1 "
            "configuration document.",
            error_code="key_batch_plan",
        ) from exc
    if policy.is_empty():
        _fail("policy", "The reviewed policy must request at least one change.")

    raw_keys = document["keys"]
    if not isinstance(raw_keys, list) or len(raw_keys) != len(key_ids):
        _fail("keys", "Value must carry one entry per selected key.")
    plan_keys: list[KeyBatchPlanKey] = []
    for index, raw_key in enumerate(raw_keys):
        _require_exact_keys(raw_key, f"keys[{index}]", _PLAN_KEY_KEYS)
        before = _require_json_object(raw_key["before"], f"keys[{index}].before")
        after = _require_json_object(raw_key["after"], f"keys[{index}].after")
        # Strict version-1 configuration documents: unknown fields, wrong
        # types, and missing/invalid schema_version are refused (the
        # shared service renderer already gates rendered documents with
        # the SAME parser).
        try:
            parse_key_configuration(before)
        except KeyConfigurationError:
            _fail(
                f"keys[{index}].before",
                "Document is not a valid version-1 configuration document.",
            )
        try:
            parse_key_configuration(after)
        except KeyConfigurationError:
            _fail(
                f"keys[{index}].after",
                "Document is not a valid version-1 configuration document.",
            )
        raw_changes = raw_key["changes"]
        if not isinstance(raw_changes, list):
            _fail(f"keys[{index}].changes", "Value must be a list.")
        changes: tuple[dict[str, Any], ...] = ()
        for change_index, raw_change in enumerate(raw_changes):
            _require_exact_keys(
                raw_change,
                f"keys[{index}].changes[{change_index}]",
                frozenset({"field", "before", "after"}),
            )
            field = raw_change["field"]
            if not isinstance(field, str) or field not in _KNOWN_CONFIGURATION_FIELDS:
                _fail(
                    f"keys[{index}].changes[{change_index}].field",
                    "Value must be a known configuration field.",
                )
            changes = changes + (
                {
                    "field": field,
                    "before": raw_change["before"],
                    "after": raw_change["after"],
                },
            )
        expected_changes = key_batch_document_changes(before, after)
        if tuple(json.dumps(item, sort_keys=True) for item in changes) != tuple(
            json.dumps(item, sort_keys=True) for item in expected_changes
        ):
            _fail(f"keys[{index}].changes", "Value must equal the derived document diff.")
        plan_keys.append(
            KeyBatchPlanKey(
                key_id=_require_uuid(raw_key["key_id"], f"keys[{index}].key_id"),
                source_fingerprint=_require_fingerprint(
                    raw_key["source_fingerprint"], f"keys[{index}].source_fingerprint"
                ),
                post_fingerprint=_require_fingerprint(
                    raw_key["post_fingerprint"], f"keys[{index}].post_fingerprint"
                ),
                before=before,
                after=after,
                changes=changes,
            )
        )
    if tuple(key.key_id for key in plan_keys) != key_ids:
        _fail("keys", "Entries must match the selected key list exactly.")

    selected_count = _require_int(
        document["selected_count"], "selected_count", minimum=0, maximum=KEY_BATCH_MAX_KEYS
    )
    if selected_count != len(plan_keys):
        _fail("selected_count", "Value must equal the number of selected keys.")
    changed_count = _require_int(
        document["changed_count"], "changed_count", minimum=0, maximum=KEY_BATCH_MAX_KEYS
    )
    unchanged_count = _require_int(
        document["unchanged_count"], "unchanged_count", minimum=0, maximum=KEY_BATCH_MAX_KEYS
    )
    derived_changed = sum(1 for key in plan_keys if key.changes)
    if changed_count != derived_changed:
        _fail("changed_count", "Value must equal the number of changed keys.")
    if unchanged_count != selected_count - changed_count:
        _fail("unchanged_count", "Value must equal selected minus changed keys.")

    raw_excluded = document["excluded_by_status"]
    if not isinstance(raw_excluded, list):
        _fail("excluded_by_status", "Value must be a list.")
    excluded: list[tuple[str, str]] = []
    seen_excluded: set[str] = set()
    for index, raw_entry in enumerate(raw_excluded):
        _require_exact_keys(
            raw_entry, f"excluded_by_status[{index}]", frozenset({"key_id", "status"})
        )
        key_id = _require_uuid(raw_entry["key_id"], f"excluded_by_status[{index}].key_id")
        status = _require_status(raw_entry["status"], f"excluded_by_status[{index}].status")
        if key_id in set(key_ids) or key_id in seen_excluded:
            _fail("excluded_by_status", "Value must not repeat or select a key.")
        if status in statuses:
            _fail(
                f"excluded_by_status[{index}].status",
                "Value must be outside the selected status filter.",
            )
        seen_excluded.add(key_id)
        excluded.append((key_id, status))
    if selection_kind == KEY_BATCH_SELECTION_COHORT and excluded:
        _fail("excluded_by_status", "Value must be empty for a cohort selection.")
    if (
        selection_kind == KEY_BATCH_SELECTION_KEYS
        and len(key_ids) + len(excluded) > KEY_BATCH_MAX_KEYS
    ):
        _fail(
            "excluded_by_status",
            f"Value plus selected keys must not exceed {KEY_BATCH_MAX_KEYS}.",
        )
    excluded.sort()
    if [[entry["key_id"], entry["status"]] for entry in raw_excluded] != [
        list(entry) for entry in excluded
    ]:
        _fail("excluded_by_status", "Value must be sorted.")

    planned_at = _require_iso_datetime(document["planned_at"], "planned_at")

    plan = KeyBatchPlan(
        schema_version=version,
        operation=KEY_BATCH_PLAN_OPERATION,
        selection_kind=selection_kind,
        cohort_id=cohort_id,
        key_ids=key_ids,
        statuses=statuses,
        policy=dict(policy_document),
        keys=tuple(plan_keys),
        selected_count=selected_count,
        changed_count=changed_count,
        unchanged_count=unchanged_count,
        excluded_by_status=tuple(excluded),
        planned_at=planned_at,
    )
    # Strict round-trip gate: the parsed document must render back to the
    # EXACT reviewed document (an edited count, bound, or target is refused).
    if render_key_batch_plan(plan) != document:
        _fail("file", "Document does not round-trip to the reviewed plan.")
    return plan


def _refuse_known_secret_shapes(document: Any) -> None:
    """Refuse a recognized credential shape ANYWHERE in the plan document.

    Finite known-shape protection (gateway/provider key, Bearer header,
    sensitive assignment), not a content sanitizer: nested policy and
    snapshot values are checked too, so a recognized shape can never be
    produced or persisted through parse or the bounded writer (which
    re-validates through this same gate).
    """
    try:
        text = json.dumps(document, sort_keys=True, ensure_ascii=True)
    except (TypeError, ValueError):
        _fail("file", "Document is not a valid JSON document.")
    if any(pattern.search(text) for pattern in _SECRET_SHAPE_PATTERNS):
        _fail("file", "Document contains a recognized credential shape.")


def _load_strict_object(data: bytes, max_bytes: int) -> dict[str, Any]:
    if len(data) > max_bytes:
        _fail("file", f"File exceeds {max_bytes} bytes.")
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
    except KeyBatchError:
        raise
    except json.JSONDecodeError:
        _fail("file", "File is not valid JSON.")
    if not isinstance(value, dict):
        _fail("file", "Top level must be a JSON object.")
    return value


def parse_key_batch_plan_file(path: Path | str) -> KeyBatchPlan:
    """Read at most MAX+1 bytes and strictly parse one reviewed plan."""
    try:
        with Path(path).open("rb") as stream:
            data = stream.read(KEY_BATCH_PLAN_MAX_BYTES + 1)
    except OSError:
        raise KeyBatchError(
            "The batch plan file is not readable.", error_code="key_batch_plan"
        ) from None
    document = _load_strict_object(data, KEY_BATCH_PLAN_MAX_BYTES)
    if any(
        pattern.search(data.decode("utf-8", errors="replace"))
        for pattern in _SECRET_SHAPE_PATTERNS
    ):
        _fail("file", "File contains a recognized credential shape.")
    return parse_key_batch_plan(document)


def write_key_batch_plan_file(path: Path | str, plan: KeyBatchPlan) -> None:
    """Bounded exclusive 0600 write; never overwrite an existing file.

    The document is rendered, strictly re-validated, and size-bounded
    BEFORE any file descriptor is opened. If a write then fails, the fixed
    static error is raised and NO path is removed: a partial file may
    remain at the exact output path (the operator removes it and re-runs);
    existing and unrelated paths are never touched, and O_EXCL guarantees
    the path is never overwritten.
    """
    import os

    payload = (
        json.dumps(render_key_batch_plan(plan), indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    if len(payload) > KEY_BATCH_PLAN_MAX_BYTES:
        raise KeyBatchError(
            "The rendered batch plan exceeds the bounded size.",
            error_code="key_batch_plan",
        )
    # Strict re-validation of the exact document about to be written.
    parse_key_batch_plan(render_key_batch_plan(plan))
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except OSError:
        raise KeyBatchError(
            "The batch plan output must be a new writable file.",
            error_code="key_batch_plan",
        ) from None
    try:
        stream = os.fdopen(fd, "wb")
    except OSError:
        os.close(fd)
        raise KeyBatchError(
            "The batch plan file could not be written.", error_code="key_batch_plan"
        ) from None
    try:
        with stream:
            stream.write(payload)
    except OSError:
        raise KeyBatchError(
            "The batch plan file could not be written; a partial file "
            "may remain at the output path, which is never overwritten.",
            error_code="key_batch_plan",
        ) from None
