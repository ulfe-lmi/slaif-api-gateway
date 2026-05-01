"""Dry-run parsing and validation for bulk gateway key import previews."""

from __future__ import annotations

import csv
import json
import re
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from io import StringIO

from slaif_gateway.utils.redaction import is_sensitive_key, redact_text

KEY_IMPORT_ALLOWED_FIELDS = {
    "owner_id",
    "owner_email",
    "institution_id",
    "cohort_id",
    "valid_from",
    "valid_until",
    "valid_days",
    "cost_limit_eur",
    "token_limit",
    "token_limit_total",
    "request_limit",
    "request_limit_total",
    "allowed_models",
    "allowed_endpoints",
    "allowed_providers",
    "allow_all_models",
    "allow_all_endpoints",
    "allow_all_providers",
    "rate_limit_requests_per_minute",
    "rate_limit_tokens_per_minute",
    "rate_limit_concurrent_requests",
    "rate_limit_window_seconds",
    "email_delivery_mode",
    "note",
    "admin_note",
    "label",
    "metadata",
}

KEY_IMPORT_EMAIL_MODES = {"none", "pending", "send-now", "enqueue"}
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@dataclass(frozen=True, slots=True)
class KeyImportOwnerRef:
    """Safe owner metadata used for bulk key import validation."""

    id: uuid.UUID
    email: str
    display_name: str
    institution_id: uuid.UUID | None = None
    institution_name: str | None = None


@dataclass(frozen=True, slots=True)
class KeyImportCohortRef:
    """Safe cohort metadata used for bulk key import validation."""

    id: uuid.UUID
    name: str


@dataclass(frozen=True, slots=True)
class KeyImportReadOnlyContext:
    """Read-only lookup data for import validation."""

    owners_by_id: Mapping[uuid.UUID, KeyImportOwnerRef]
    owners_by_email: Mapping[str, KeyImportOwnerRef]
    cohorts_by_id: Mapping[uuid.UUID, KeyImportCohortRef]
    email_delivery_enabled: bool = False
    smtp_configured: bool = False
    celery_configured: bool = False


@dataclass(frozen=True, slots=True)
class KeyImportRowPreview:
    """Safe row-level preview for a bulk gateway key import dry-run."""

    row_number: int
    status: str
    classification: str
    owner_id: uuid.UUID | None = None
    owner_email: str | None = None
    owner_name: str | None = None
    institution_id: uuid.UUID | None = None
    institution_name: str | None = None
    cohort_id: uuid.UUID | None = None
    cohort_name: str | None = None
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    cost_limit_eur: str | None = None
    token_limit: int | None = None
    request_limit: int | None = None
    allowed_models: tuple[str, ...] = ()
    allowed_endpoints: tuple[str, ...] = ()
    allowed_providers: tuple[str, ...] = ()
    allow_all_models: bool = False
    allow_all_endpoints: bool = False
    allow_all_providers: bool = False
    rate_limit_policy: dict[str, int] | None = None
    email_delivery_mode: str = "none"
    label: str | None = None
    note: str | None = None
    metadata_summary: str = "none"
    errors: tuple[str, ...] = ()

    @property
    def allowed_models_summary(self) -> str:
        return _policy_summary(self.allowed_models, allow_all=self.allow_all_models)

    @property
    def allowed_endpoints_summary(self) -> str:
        return _policy_summary(self.allowed_endpoints, allow_all=self.allow_all_endpoints)

    @property
    def allowed_providers_summary(self) -> str:
        return _policy_summary(self.allowed_providers, allow_all=self.allow_all_providers)

    @property
    def rate_limit_summary(self) -> str:
        if not self.rate_limit_policy:
            return "none"
        parts = []
        if "requests_per_minute" in self.rate_limit_policy:
            parts.append(f"{self.rate_limit_policy['requests_per_minute']} req/min")
        if "tokens_per_minute" in self.rate_limit_policy:
            parts.append(f"{self.rate_limit_policy['tokens_per_minute']} tokens/min")
        if "max_concurrent_requests" in self.rate_limit_policy:
            parts.append(f"{self.rate_limit_policy['max_concurrent_requests']} concurrent")
        if "window_seconds" in self.rate_limit_policy:
            parts.append(f"{self.rate_limit_policy['window_seconds']}s window")
        return ", ".join(parts) if parts else "none"


@dataclass(frozen=True, slots=True)
class KeyImportPreview:
    """Safe aggregate preview for a bulk gateway key import dry-run."""

    total_rows: int
    valid_count: int
    invalid_count: int
    rows: tuple[KeyImportRowPreview, ...]
    duplicate_owner_count: int = 0


def parse_key_import_csv(text: str) -> list[dict[str, object]]:
    """Parse key import CSV text into raw row mappings."""
    try:
        reader = csv.DictReader(StringIO(text))
        if not reader.fieldnames:
            raise ValueError("Key import CSV must include a header row")
        return [dict(row) for row in reader]
    except csv.Error as exc:
        raise ValueError("Key import content is not valid CSV") from exc


def parse_key_import_json(text: str) -> list[dict[str, object]]:
    """Parse key import JSON text into raw row mappings."""
    try:
        loaded = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("Key import content is not valid JSON") from exc
    if not isinstance(loaded, list):
        raise ValueError("Key JSON import must be a list of objects")
    if not all(isinstance(item, dict) for item in loaded):
        raise ValueError("Key JSON import must contain only objects")
    return list(loaded)


def detect_key_import_format(*, filename: str | None, requested_format: str, text: str) -> str:
    """Resolve csv/json/auto format selection."""
    normalized = requested_format.strip().lower()
    if normalized not in {"auto", "csv", "json"}:
        raise ValueError("Import format must be auto, csv, or json")
    if normalized in {"csv", "json"}:
        return normalized

    suffix = (filename or "").rsplit(".", 1)[-1].lower() if "." in (filename or "") else ""
    if suffix in {"csv", "json"}:
        return suffix
    if text.lstrip().startswith("["):
        return "json"
    return "csv"


def validate_key_import_rows(
    rows: Sequence[Mapping[str, object]],
    *,
    context: KeyImportReadOnlyContext,
    max_rows: int,
    now: datetime | None = None,
) -> KeyImportPreview:
    """Validate raw key import rows and return a non-mutating preview."""
    if max_rows <= 0:
        raise ValueError("max_rows must be positive")
    if len(rows) > max_rows:
        raise ValueError(f"Key import may contain at most {max_rows} rows")

    timestamp = _aware_time(now or datetime.now(UTC))
    previews: list[KeyImportRowPreview] = []
    owner_counts: dict[uuid.UUID, int] = {}
    for index, row in enumerate(rows, start=1):
        try:
            preview = _validate_one_row(row, index=index, context=context, now=timestamp)
            if preview.owner_id is not None:
                owner_counts[preview.owner_id] = owner_counts.get(preview.owner_id, 0) + 1
        except ValueError as exc:
            preview = KeyImportRowPreview(
                row_number=index,
                status="invalid",
                classification="invalid",
                errors=(str(exc),),
            )
        previews.append(preview)

    duplicate_owner_ids = {owner_id for owner_id, count in owner_counts.items() if count > 1}
    classified = tuple(
        _with_classification(row, "duplicate") if row.owner_id in duplicate_owner_ids else row
        for row in previews
    )
    valid_count = sum(1 for row in classified if row.status == "valid")
    return KeyImportPreview(
        total_rows=len(classified),
        valid_count=valid_count,
        invalid_count=len(classified) - valid_count,
        rows=classified,
        duplicate_owner_count=sum(1 for row in classified if row.status == "valid" and row.classification == "duplicate"),
    )


def key_import_preview_to_dict(preview: KeyImportPreview) -> dict[str, object]:
    """Convert preview DTOs to safe serializable values for tests or JSON-like rendering."""
    return {
        "total_rows": preview.total_rows,
        "valid_count": preview.valid_count,
        "invalid_count": preview.invalid_count,
        "duplicate_owner_count": preview.duplicate_owner_count,
        "rows": [
            {
                "row_number": row.row_number,
                "status": row.status,
                "classification": row.classification,
                "owner_id": str(row.owner_id) if row.owner_id else None,
                "owner_email": row.owner_email,
                "owner_name": row.owner_name,
                "institution_id": str(row.institution_id) if row.institution_id else None,
                "institution_name": row.institution_name,
                "cohort_id": str(row.cohort_id) if row.cohort_id else None,
                "cohort_name": row.cohort_name,
                "valid_from": row.valid_from.isoformat() if row.valid_from else None,
                "valid_until": row.valid_until.isoformat() if row.valid_until else None,
                "cost_limit_eur": row.cost_limit_eur,
                "token_limit": row.token_limit,
                "request_limit": row.request_limit,
                "allowed_models": list(row.allowed_models),
                "allowed_endpoints": list(row.allowed_endpoints),
                "allowed_providers": list(row.allowed_providers),
                "allow_all_models": row.allow_all_models,
                "allow_all_endpoints": row.allow_all_endpoints,
                "allow_all_providers": row.allow_all_providers,
                "rate_limit_policy": row.rate_limit_policy,
                "email_delivery_mode": row.email_delivery_mode,
                "label": row.label,
                "note": row.note,
                "metadata_summary": row.metadata_summary,
                "errors": list(row.errors),
            }
            for row in preview.rows
        ],
    }


def _validate_one_row(
    row: Mapping[str, object],
    *,
    index: int,
    context: KeyImportReadOnlyContext,
    now: datetime,
) -> KeyImportRowPreview:
    unknown_fields = {str(field) for field in row if field not in KEY_IMPORT_ALLOWED_FIELDS}
    if unknown_fields:
        raise ValueError(f"unknown fields: {', '.join(sorted(unknown_fields))}")

    owner = _resolve_owner(row, context=context)
    institution_id = _optional_import_uuid(row.get("institution_id"), field_name="institution_id")
    if institution_id is not None and owner.institution_id != institution_id:
        raise ValueError("institution_id must match the resolved owner institution")
    cohort = _resolve_cohort(row, context=context)

    valid_from = _optional_import_datetime(row.get("valid_from"), field_name="valid_from") or now
    valid_until = _parse_valid_until(
        valid_from=valid_from,
        valid_until=row.get("valid_until"),
        valid_days=row.get("valid_days"),
    )

    cost_limit = _optional_import_decimal(row.get("cost_limit_eur"), field_name="cost_limit_eur")
    token_limit = _optional_positive_int(
        row.get("token_limit_total", row.get("token_limit")),
        field_name="token_limit",
    )
    request_limit = _optional_positive_int(
        row.get("request_limit_total", row.get("request_limit")),
        field_name="request_limit",
    )
    allowed_models = _optional_import_list(row.get("allowed_models"), field_name="allowed_models")
    allowed_endpoints = _optional_import_list(row.get("allowed_endpoints"), field_name="allowed_endpoints")
    allowed_providers = _optional_import_list(row.get("allowed_providers"), field_name="allowed_providers")
    allow_all_models = _optional_bool(row.get("allow_all_models"), field_name="allow_all_models")
    allow_all_endpoints = _optional_bool(row.get("allow_all_endpoints"), field_name="allow_all_endpoints")
    allow_all_providers = _optional_bool(row.get("allow_all_providers"), field_name="allow_all_providers")
    rate_limit_policy = _rate_limit_policy(row)
    email_delivery_mode = _email_delivery_mode(row.get("email_delivery_mode"), context=context, owner=owner)
    metadata = _optional_import_metadata(row.get("metadata"))

    return KeyImportRowPreview(
        row_number=index,
        status="valid",
        classification="create",
        owner_id=owner.id,
        owner_email=owner.email,
        owner_name=owner.display_name,
        institution_id=owner.institution_id,
        institution_name=owner.institution_name,
        cohort_id=cohort.id if cohort else None,
        cohort_name=cohort.name if cohort else None,
        valid_from=valid_from,
        valid_until=valid_until,
        cost_limit_eur=cost_limit,
        token_limit=token_limit,
        request_limit=request_limit,
        allowed_models=tuple(allowed_models),
        allowed_endpoints=tuple(allowed_endpoints),
        allowed_providers=tuple(allowed_providers),
        allow_all_models=allow_all_models,
        allow_all_endpoints=allow_all_endpoints,
        allow_all_providers=allow_all_providers,
        rate_limit_policy=rate_limit_policy,
        email_delivery_mode=email_delivery_mode,
        label=_optional_import_text(row.get("label"), field_name="label"),
        note=_optional_import_text(row.get("note", row.get("admin_note")), field_name="note"),
        metadata_summary=", ".join(sorted(str(key) for key in metadata)) if metadata else "none",
    )


def _resolve_owner(row: Mapping[str, object], *, context: KeyImportReadOnlyContext) -> KeyImportOwnerRef:
    owner_id = _optional_import_uuid(row.get("owner_id"), field_name="owner_id")
    owner_email = _optional_email(row.get("owner_email"))
    if owner_id is None and owner_email is None:
        raise ValueError("owner_id or owner_email is required")
    if owner_id is not None:
        owner = context.owners_by_id.get(owner_id)
        if owner is None:
            raise ValueError("owner_id must reference an existing owner")
        if owner_email is not None and owner.email.lower() != owner_email.lower():
            raise ValueError("owner_email must match owner_id when both are supplied")
        return owner
    assert owner_email is not None
    owner = context.owners_by_email.get(owner_email.lower())
    if owner is None:
        raise ValueError("owner_email must reference an existing owner")
    return owner


def _resolve_cohort(row: Mapping[str, object], *, context: KeyImportReadOnlyContext) -> KeyImportCohortRef | None:
    cohort_id = _optional_import_uuid(row.get("cohort_id"), field_name="cohort_id")
    if cohort_id is None:
        return None
    cohort = context.cohorts_by_id.get(cohort_id)
    if cohort is None:
        raise ValueError("cohort_id must reference an existing cohort")
    return cohort


def _parse_valid_until(*, valid_from: datetime, valid_until: object, valid_days: object) -> datetime:
    has_valid_until = not _is_blank(valid_until)
    has_valid_days = not _is_blank(valid_days)
    if has_valid_until and has_valid_days:
        raise ValueError("Use either valid_until or valid_days, not both")
    if has_valid_until:
        parsed = _optional_import_datetime(valid_until, field_name="valid_until")
        if parsed is None:
            raise ValueError("valid_until is required")
    elif has_valid_days:
        days = _required_positive_int(valid_days, field_name="valid_days")
        parsed = valid_from + timedelta(days=days)
    else:
        raise ValueError("valid_until or valid_days is required")
    if parsed <= valid_from:
        raise ValueError("valid_until must be after valid_from")
    return parsed


def _rate_limit_policy(row: Mapping[str, object]) -> dict[str, int] | None:
    fields = (
        ("rate_limit_requests_per_minute", "requests_per_minute"),
        ("rate_limit_tokens_per_minute", "tokens_per_minute"),
        ("rate_limit_concurrent_requests", "max_concurrent_requests"),
        ("rate_limit_window_seconds", "window_seconds"),
    )
    policy: dict[str, int] = {}
    for input_name, policy_name in fields:
        value = _optional_positive_int(row.get(input_name), field_name=input_name)
        if value is not None:
            policy[policy_name] = value
    return policy or None


def _email_delivery_mode(
    value: object,
    *,
    context: KeyImportReadOnlyContext,
    owner: KeyImportOwnerRef,
) -> str:
    mode = _optional_import_text(value, field_name="email_delivery_mode") or "none"
    normalized = mode.strip().lower()
    if normalized not in KEY_IMPORT_EMAIL_MODES:
        raise ValueError("email_delivery_mode must be none, pending, send-now, or enqueue")
    if normalized in {"pending", "send-now", "enqueue"} and not owner.email:
        raise ValueError("email_delivery_mode requires the owner to have an email address")
    if normalized in {"send-now", "enqueue"} and not context.email_delivery_enabled:
        raise ValueError("email delivery must be enabled before send-now or enqueue can be executed")
    if normalized == "send-now" and not context.smtp_configured:
        raise ValueError("SMTP settings must be configured before send-now can be executed")
    if normalized == "enqueue" and not context.celery_configured:
        raise ValueError("Celery broker settings must be configured before enqueue can be executed")
    return normalized


def _optional_import_text(value: object, *, field_name: str) -> str | None:
    if _is_blank(value):
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    cleaned = value.strip()
    if _looks_like_secret(cleaned):
        raise ValueError(f"{field_name} must not contain secret-looking values")
    return cleaned


def _optional_email(value: object) -> str | None:
    email = _optional_import_text(value, field_name="owner_email")
    if email is None:
        return None
    normalized = email.strip().lower()
    if not _EMAIL_RE.match(normalized):
        raise ValueError("owner_email must be a valid email address")
    return normalized


def _optional_import_uuid(value: object, *, field_name: str) -> uuid.UUID | None:
    text = _optional_import_text(value, field_name=field_name)
    if text is None:
        return None
    try:
        return uuid.UUID(text)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be a UUID") from exc


def _optional_import_datetime(value: object, *, field_name: str) -> datetime | None:
    text = _optional_import_text(value, field_name=field_name)
    if text is None:
        return None
    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        return _aware_time(datetime.fromisoformat(normalized))
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an ISO datetime string") from exc


def _optional_import_decimal(value: object, *, field_name: str) -> str | None:
    text = _optional_import_text(value, field_name=field_name)
    if text is None:
        return None
    try:
        parsed = Decimal(text)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field_name} must be a decimal string") from exc
    if not parsed.is_finite() or parsed <= 0:
        raise ValueError(f"{field_name} must be positive")
    return str(parsed)


def _optional_positive_int(value: object, *, field_name: str) -> int | None:
    if _is_blank(value):
        return None
    return _required_positive_int(value, field_name=field_name)


def _required_positive_int(value: object, *, field_name: str) -> int:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a positive integer string")
    text = value.strip()
    if not text.isdigit():
        raise ValueError(f"{field_name} must be a positive integer")
    parsed = int(text, 10)
    if parsed <= 0:
        raise ValueError(f"{field_name} must be positive")
    return parsed


def _optional_bool(value: object, *, field_name: str) -> bool:
    if _is_blank(value):
        return False
    if isinstance(value, bool):
        return value
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a boolean string")
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{field_name} must be true or false")


def _optional_import_list(value: object, *, field_name: str) -> list[str]:
    if _is_blank(value):
        return []
    if isinstance(value, str):
        text = value.strip()
        if text.startswith("["):
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{field_name} must be a JSON list or comma/newline-separated string") from exc
            return _list_from_sequence(parsed, field_name=field_name)
        normalized = text.replace(",", "\n")
        items = [item.strip() for item in normalized.splitlines() if item.strip()]
    elif isinstance(value, list | tuple):
        items = _list_from_sequence(value, field_name=field_name)
    else:
        raise ValueError(f"{field_name} must be a list or string")
    for item in items:
        if _looks_like_secret(item):
            raise ValueError(f"{field_name} must not contain secret-looking values")
    return items


def _list_from_sequence(value: object, *, field_name: str) -> list[str]:
    if not isinstance(value, list | tuple):
        raise ValueError(f"{field_name} must be a list of strings")
    items: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise ValueError(f"{field_name} must contain only strings")
        cleaned = item.strip()
        if cleaned:
            items.append(cleaned)
    return items


def _optional_import_metadata(value: object) -> dict[str, object]:
    if _is_blank(value):
        return {}
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError("metadata must be a JSON object") from exc
    else:
        parsed = value
    if not isinstance(parsed, dict):
        raise ValueError("metadata must be a JSON object")
    if _mapping_contains_secret(parsed):
        raise ValueError("metadata must not contain secret-looking values")
    return dict(parsed)


def _with_classification(row: KeyImportRowPreview, classification: str) -> KeyImportRowPreview:
    return KeyImportRowPreview(
        row_number=row.row_number,
        status=row.status,
        classification=classification,
        owner_id=row.owner_id,
        owner_email=row.owner_email,
        owner_name=row.owner_name,
        institution_id=row.institution_id,
        institution_name=row.institution_name,
        cohort_id=row.cohort_id,
        cohort_name=row.cohort_name,
        valid_from=row.valid_from,
        valid_until=row.valid_until,
        cost_limit_eur=row.cost_limit_eur,
        token_limit=row.token_limit,
        request_limit=row.request_limit,
        allowed_models=row.allowed_models,
        allowed_endpoints=row.allowed_endpoints,
        allowed_providers=row.allowed_providers,
        allow_all_models=row.allow_all_models,
        allow_all_endpoints=row.allow_all_endpoints,
        allow_all_providers=row.allow_all_providers,
        rate_limit_policy=row.rate_limit_policy,
        email_delivery_mode=row.email_delivery_mode,
        label=row.label,
        note=row.note,
        metadata_summary=row.metadata_summary,
        errors=row.errors,
    )


def _policy_summary(values: tuple[str, ...], *, allow_all: bool) -> str:
    if allow_all:
        return "all"
    if not values:
        return "default"
    return ", ".join(values)


def _aware_time(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _is_blank(value: object) -> bool:
    return value is None or value == "" or (isinstance(value, str) and not value.strip())


def _looks_like_secret(value: str) -> bool:
    stripped = value.strip()
    lowered = stripped.lower()
    if lowered.startswith(("bearer ", "sk-", "sk_", "sk-or-")):
        return True
    return redact_text(stripped) != stripped


def _mapping_contains_secret(value: object) -> bool:
    if isinstance(value, Mapping):
        for key, item in value.items():
            key_text = str(key)
            if is_sensitive_key(key_text) or "secret" in key_text.lower() or "password" in key_text.lower():
                return True
            if _mapping_contains_secret(item):
                return True
        return False
    if isinstance(value, list | tuple):
        return any(_mapping_contains_secret(item) for item in value)
    if isinstance(value, str):
        return _looks_like_secret(value)
    return False
