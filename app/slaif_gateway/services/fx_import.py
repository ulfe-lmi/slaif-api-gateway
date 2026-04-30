"""Dry-run parsing and validation for FX rate import previews."""

from __future__ import annotations

import csv
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from io import StringIO

from slaif_gateway.utils.redaction import is_sensitive_key, redact_text

FX_IMPORT_ALLOWED_FIELDS = {
    "base_currency",
    "quote_currency",
    "rate",
    "source",
    "valid_from",
    "valid_until",
    "metadata",
    "note",
    "notes",
}


@dataclass(frozen=True, slots=True)
class FxImportRowPreview:
    """Safe row-level result for an FX import dry-run."""

    row_number: int
    status: str
    classification: str
    base_currency: str | None = None
    quote_currency: str | None = None
    rate: str | None = None
    source: str | None = None
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    metadata: dict[str, object] | None = None
    notes: str | None = None
    errors: tuple[str, ...] = ()

    @property
    def metadata_summary(self) -> str:
        if not self.metadata:
            return "none"
        return ", ".join(sorted(str(key) for key in self.metadata))


@dataclass(frozen=True, slots=True)
class FxImportPreview:
    """Safe aggregate preview for an FX import dry-run."""

    total_rows: int
    valid_count: int
    invalid_count: int
    rows: tuple[FxImportRowPreview, ...]


def parse_fx_import_csv(text: str) -> list[dict[str, object]]:
    """Parse FX CSV text into raw row mappings."""
    try:
        reader = csv.DictReader(StringIO(text))
        if not reader.fieldnames:
            raise ValueError("FX CSV import must include a header row")
        return [dict(row) for row in reader]
    except csv.Error as exc:
        raise ValueError("FX import content is not valid CSV") from exc


def parse_fx_import_json(text: str) -> list[dict[str, object]]:
    """Parse FX JSON text into raw row mappings."""
    try:
        loaded = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("FX import content is not valid JSON") from exc
    if not isinstance(loaded, list):
        raise ValueError("FX JSON import must be a list of objects")
    if not all(isinstance(item, dict) for item in loaded):
        raise ValueError("FX JSON import must contain only objects")
    return list(loaded)


def detect_fx_import_format(*, filename: str | None, requested_format: str, text: str) -> str:
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


def validate_fx_import_rows(
    rows: Sequence[Mapping[str, object]],
    *,
    max_rows: int,
    now: datetime | None = None,
) -> FxImportPreview:
    """Validate raw import rows and return a non-mutating preview."""
    if max_rows <= 0:
        raise ValueError("max_rows must be positive")
    if len(rows) > max_rows:
        raise ValueError(f"FX import may contain at most {max_rows} rows")

    timestamp = _aware_time(now or datetime.now(UTC))
    previews: list[FxImportRowPreview] = []
    seen_keys: set[tuple[str, str, datetime, datetime | None]] = set()
    for index, row in enumerate(rows, start=1):
        try:
            preview = _validate_one_row(row, index=index, now=timestamp)
            key = (
                preview.base_currency or "",
                preview.quote_currency or "",
                preview.valid_from or timestamp,
                preview.valid_until,
            )
            if key in seen_keys:
                preview = replace(preview, classification="duplicate")
            else:
                seen_keys.add(key)
        except ValueError as exc:
            preview = FxImportRowPreview(
                row_number=index,
                status="invalid",
                classification="invalid",
                errors=(str(exc),),
            )
        previews.append(preview)

    valid_count = sum(1 for row in previews if row.status == "valid")
    return FxImportPreview(
        total_rows=len(previews),
        valid_count=valid_count,
        invalid_count=len(previews) - valid_count,
        rows=tuple(previews),
    )


def classify_fx_import_preview(
    preview: FxImportPreview,
    *,
    existing_rates_by_row: Mapping[int, Sequence[object]],
) -> FxImportPreview:
    """Classify valid preview rows against existing FX rows without mutation."""
    classified_rows: list[FxImportRowPreview] = []
    for row in preview.rows:
        if row.status != "valid" or row.classification == "duplicate":
            classified_rows.append(row)
            continue
        classification = _classify_existing(row, existing_rates_by_row.get(row.row_number, ()))
        classified_rows.append(replace(row, classification=classification))
    return FxImportPreview(
        total_rows=preview.total_rows,
        valid_count=preview.valid_count,
        invalid_count=preview.invalid_count,
        rows=tuple(classified_rows),
    )


def fx_import_preview_to_dict(preview: FxImportPreview) -> dict[str, object]:
    """Convert preview DTOs to safe serializable values for tests or JSON-like rendering."""
    return {
        "total_rows": preview.total_rows,
        "valid_count": preview.valid_count,
        "invalid_count": preview.invalid_count,
        "rows": [
            {
                "row_number": row.row_number,
                "status": row.status,
                "classification": row.classification,
                "base_currency": row.base_currency,
                "quote_currency": row.quote_currency,
                "rate": row.rate,
                "source": row.source,
                "valid_from": row.valid_from.isoformat() if row.valid_from else None,
                "valid_until": row.valid_until.isoformat() if row.valid_until else None,
                "metadata": row.metadata,
                "notes": row.notes,
                "errors": list(row.errors),
            }
            for row in preview.rows
        ],
    }


def _validate_one_row(row: Mapping[str, object], *, index: int, now: datetime) -> FxImportRowPreview:
    unknown_fields = {str(field) for field in row if field not in FX_IMPORT_ALLOWED_FIELDS}
    if unknown_fields:
        raise ValueError(f"unknown fields: {', '.join(sorted(unknown_fields))}")

    base_currency = _normalize_currency(_required_import_text(row.get("base_currency"), field_name="base_currency"))
    quote_currency = _normalize_currency(
        _optional_import_text(row.get("quote_currency"), field_name="quote_currency") or "EUR"
    )
    if base_currency == quote_currency:
        raise ValueError("base_currency and quote_currency must differ")

    valid_from = _optional_import_datetime(row.get("valid_from"), field_name="valid_from") or now
    valid_until = _optional_import_datetime(row.get("valid_until"), field_name="valid_until")
    if valid_until is not None and valid_until <= valid_from:
        raise ValueError("valid_until must be after valid_from")

    metadata = _optional_import_metadata(row.get("metadata"))
    notes = _optional_import_text(row.get("notes", row.get("note")), field_name="notes")
    return FxImportRowPreview(
        row_number=index,
        status="valid",
        classification="create",
        base_currency=base_currency,
        quote_currency=quote_currency,
        rate=_required_import_decimal(row.get("rate"), field_name="rate"),
        source=_optional_import_text(row.get("source"), field_name="source"),
        valid_from=valid_from,
        valid_until=valid_until,
        metadata=metadata,
        notes=notes,
    )


def _required_import_text(value: object, *, field_name: str) -> str:
    text = _optional_import_text(value, field_name=field_name)
    if text is None:
        raise ValueError(f"{field_name} is required")
    return text


def _optional_import_text(value: object, *, field_name: str) -> str | None:
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    cleaned = value.strip()
    if not cleaned:
        return None
    if _looks_like_secret(cleaned):
        raise ValueError(f"{field_name} must not contain secret-looking values")
    return cleaned


def _required_import_decimal(value: object, *, field_name: str) -> str:
    parsed = _optional_import_decimal(value, field_name=field_name)
    if parsed is None:
        raise ValueError(f"{field_name} is required")
    return parsed


def _optional_import_decimal(value: object, *, field_name: str) -> str | None:
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a decimal string")
    normalized = value.strip()
    if not normalized:
        return None
    try:
        parsed = Decimal(normalized)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field_name} must be a decimal string") from exc
    if not parsed.is_finite() or parsed <= 0:
        raise ValueError(f"{field_name} must be positive")
    return str(parsed)


def _optional_import_datetime(value: object, *, field_name: str) -> datetime | None:
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be an ISO datetime string")
    normalized = value.strip()
    if not normalized:
        return None
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    try:
        return _aware_time(datetime.fromisoformat(normalized))
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an ISO datetime string") from exc


def _optional_import_metadata(value: object) -> dict[str, object]:
    if value is None or value == "":
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
    if _metadata_contains_secret(parsed):
        raise ValueError("metadata must not contain secret-looking values")
    return dict(parsed)


def _normalize_currency(value: str) -> str:
    normalized = value.strip().upper()
    if len(normalized) != 3 or not normalized.isalpha():
        raise ValueError("currency must be a 3-letter code")
    return normalized


def _aware_time(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _looks_like_secret(value: str) -> bool:
    stripped = value.strip()
    lowered = stripped.lower()
    if lowered.startswith(("bearer ", "sk-", "sk_", "sk-or-")):
        return True
    return redact_text(stripped) != stripped


def _metadata_contains_secret(value: object) -> bool:
    if isinstance(value, Mapping):
        for key, item in value.items():
            key_text = str(key)
            if is_sensitive_key(key_text) or "secret" in key_text.lower():
                return True
            if _metadata_contains_secret(item):
                return True
        return False
    if isinstance(value, list | tuple):
        return any(_metadata_contains_secret(item) for item in value)
    if isinstance(value, str):
        return _looks_like_secret(value)
    return False


def _classify_existing(row: FxImportRowPreview, existing_rates: Iterable[object]) -> str:
    rates = list(existing_rates)
    if not rates:
        return "create"

    exact_matches = [
        rate
        for rate in rates
        if _same_time(getattr(rate, "valid_from", None), row.valid_from)
        and _same_time(getattr(rate, "valid_until", None), row.valid_until)
    ]
    if exact_matches:
        return "duplicate" if any(_same_rate(row, rate) for rate in exact_matches) else "update"

    if any(
        _windows_overlap(row.valid_from, row.valid_until, getattr(rate, "valid_from", None), getattr(rate, "valid_until", None))
        for rate in rates
    ):
        return "conflict"
    return "create"


def _same_rate(row: FxImportRowPreview, rate: object) -> bool:
    try:
        existing_rate = Decimal(str(getattr(rate, "rate")))
        imported_rate = Decimal(row.rate or "")
    except (InvalidOperation, ValueError):
        return False
    return (
        getattr(rate, "base_currency", None) == row.base_currency
        and getattr(rate, "quote_currency", None) == row.quote_currency
        and existing_rate == imported_rate
        and (getattr(rate, "source", None) or None) == (row.source or None)
    )


def _same_time(left: object, right: datetime | None) -> bool:
    if not isinstance(left, datetime) or right is None:
        return left is None and right is None
    return _aware_time(left) == _aware_time(right)


def _windows_overlap(
    left_start: datetime | None,
    left_end: datetime | None,
    right_start: object,
    right_end: object,
) -> bool:
    if left_start is None or not isinstance(right_start, datetime):
        return False
    start_a = _aware_time(left_start)
    end_a = _aware_time(left_end) if isinstance(left_end, datetime) else None
    start_b = _aware_time(right_start)
    end_b = _aware_time(right_end) if isinstance(right_end, datetime) else None
    return start_a < (end_b or datetime.max.replace(tzinfo=UTC)) and start_b < (
        end_a or datetime.max.replace(tzinfo=UTC)
    )
