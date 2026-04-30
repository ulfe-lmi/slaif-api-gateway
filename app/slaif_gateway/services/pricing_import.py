"""Dry-run parsing and validation for pricing import previews."""

from __future__ import annotations

import csv
import json
import uuid
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from io import StringIO
from urllib.parse import urlparse

from slaif_gateway.services.model_route_service import normalize_endpoint
from slaif_gateway.services.pricing_rule_service import PricingRuleService
from slaif_gateway.utils.redaction import is_sensitive_key, redact_text

PRICING_IMPORT_ALLOWED_FIELDS = {
    "provider",
    "model",
    "upstream_model",
    "endpoint",
    "currency",
    "input_price_per_1m",
    "cached_input_price_per_1m",
    "output_price_per_1m",
    "reasoning_price_per_1m",
    "request_price",
    "pricing_metadata",
    "valid_from",
    "valid_until",
    "source_url",
    "notes",
    "enabled",
}


@dataclass(frozen=True, slots=True)
class PricingImportRowPreview:
    """Safe row-level result for a pricing import dry-run."""

    row_number: int
    status: str
    classification: str
    provider: str | None = None
    model: str | None = None
    endpoint: str | None = None
    currency: str | None = None
    input_price_per_1m: str | None = None
    cached_input_price_per_1m: str | None = None
    output_price_per_1m: str | None = None
    reasoning_price_per_1m: str | None = None
    request_price: str | None = None
    pricing_metadata: dict[str, object] | None = None
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    source_url: str | None = None
    notes: str | None = None
    enabled: bool | None = None
    errors: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class PricingImportPreview:
    """Safe aggregate preview for a pricing import dry-run."""

    total_rows: int
    valid_count: int
    invalid_count: int
    rows: tuple[PricingImportRowPreview, ...]


@dataclass(frozen=True, slots=True)
class PricingImportExecutionRow:
    """Safe row-level result for a pricing import execution."""

    row_number: int
    action: str
    status: str
    pricing_rule_id: uuid.UUID | None = None
    provider: str | None = None
    model: str | None = None
    endpoint: str | None = None
    currency: str | None = None
    input_price_per_1m: str | None = None
    cached_input_price_per_1m: str | None = None
    output_price_per_1m: str | None = None
    reasoning_price_per_1m: str | None = None
    request_price: str | None = None
    pricing_metadata: dict[str, object] | None = None
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    source_url: str | None = None
    notes: str | None = None
    enabled: bool | None = None
    errors: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class PricingImportExecutionPlan:
    """All-or-nothing execution plan for validated pricing import rows."""

    total_rows: int
    executable_count: int
    blocked_count: int
    rows: tuple[PricingImportExecutionRow, ...]

    @property
    def executable(self) -> bool:
        return self.total_rows > 0 and self.blocked_count == 0


@dataclass(frozen=True, slots=True)
class PricingImportExecutionResult:
    """Safe aggregate result for a pricing import execution."""

    total_rows: int
    created_count: int
    updated_count: int
    skipped_count: int
    error_count: int
    rows: tuple[PricingImportExecutionRow, ...]
    audit_summary: str


def parse_pricing_import_csv(text: str) -> list[dict[str, object]]:
    """Parse pricing CSV text into raw row mappings."""
    try:
        reader = csv.DictReader(StringIO(text))
        if not reader.fieldnames:
            raise ValueError("Pricing CSV import must include a header row")
        return [dict(row) for row in reader]
    except csv.Error as exc:
        raise ValueError("Pricing import content is not valid CSV") from exc


def parse_pricing_import_json(text: str) -> list[dict[str, object]]:
    """Parse pricing JSON text into raw row mappings."""
    try:
        loaded = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("Pricing import content is not valid JSON") from exc
    if not isinstance(loaded, list):
        raise ValueError("Pricing JSON import must be a list of objects")
    if not all(isinstance(item, dict) for item in loaded):
        raise ValueError("Pricing JSON import must contain only objects")
    return list(loaded)


def detect_pricing_import_format(*, filename: str | None, requested_format: str, text: str) -> str:
    """Resolve csv/json/auto format selection."""
    normalized = requested_format.strip().lower()
    if normalized not in {"auto", "csv", "json"}:
        raise ValueError("Import format must be auto, csv, or json")
    if normalized in {"csv", "json"}:
        return normalized

    suffix = (filename or "").rsplit(".", 1)[-1].lower() if "." in (filename or "") else ""
    if suffix in {"csv", "json"}:
        return suffix
    stripped = text.lstrip()
    if stripped.startswith("["):
        return "json"
    return "csv"


def validate_pricing_import_rows(
    rows: Sequence[Mapping[str, object]],
    *,
    max_rows: int,
    now: datetime | None = None,
) -> PricingImportPreview:
    """Validate raw import rows and return a non-mutating preview."""
    if max_rows <= 0:
        raise ValueError("max_rows must be positive")
    if len(rows) > max_rows:
        raise ValueError(f"Pricing import may contain at most {max_rows} rows")

    timestamp = _aware_time(now or datetime.now(UTC))
    previews: list[PricingImportRowPreview] = []
    seen_keys: set[tuple[str, str, str, datetime, datetime | None]] = set()
    for index, row in enumerate(rows, start=1):
        try:
            preview = _validate_one_row(row, index=index, now=timestamp)
            key = (
                preview.provider or "",
                preview.model or "",
                preview.endpoint or "",
                preview.valid_from or timestamp,
                preview.valid_until,
            )
            if key in seen_keys:
                preview = replace(preview, classification="duplicate")
            else:
                seen_keys.add(key)
        except ValueError as exc:
            preview = PricingImportRowPreview(
                row_number=index,
                status="invalid",
                classification="invalid",
                errors=(str(exc),),
            )
        previews.append(preview)

    valid_count = sum(1 for row in previews if row.status == "valid")
    return PricingImportPreview(
        total_rows=len(previews),
        valid_count=valid_count,
        invalid_count=len(previews) - valid_count,
        rows=tuple(previews),
    )


def classify_pricing_import_preview(
    preview: PricingImportPreview,
    *,
    existing_rules_by_row: Mapping[int, Sequence[object]],
) -> PricingImportPreview:
    """Classify valid preview rows against existing pricing rules without mutation."""
    classified_rows: list[PricingImportRowPreview] = []
    for row in preview.rows:
        if row.status != "valid" or row.classification == "duplicate":
            classified_rows.append(row)
            continue
        classification = _classify_existing(row, existing_rules_by_row.get(row.row_number, ()))
        classified_rows.append(replace(row, classification=classification))
    return PricingImportPreview(
        total_rows=preview.total_rows,
        valid_count=preview.valid_count,
        invalid_count=preview.invalid_count,
        rows=tuple(classified_rows),
    )


def pricing_import_preview_to_dict(preview: PricingImportPreview) -> dict[str, object]:
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
                "provider": row.provider,
                "model": row.model,
                "endpoint": row.endpoint,
                "currency": row.currency,
                "input_price_per_1m": row.input_price_per_1m,
                "cached_input_price_per_1m": row.cached_input_price_per_1m,
                "output_price_per_1m": row.output_price_per_1m,
                "reasoning_price_per_1m": row.reasoning_price_per_1m,
                "request_price": row.request_price,
                "pricing_metadata": row.pricing_metadata,
                "valid_from": row.valid_from.isoformat() if row.valid_from else None,
                "valid_until": row.valid_until.isoformat() if row.valid_until else None,
                "source_url": row.source_url,
                "notes": row.notes,
                "enabled": row.enabled,
                "errors": list(row.errors),
            }
            for row in preview.rows
        ],
    }


def build_pricing_import_execution_plan(preview: PricingImportPreview) -> PricingImportExecutionPlan:
    """Build a create-only execution plan from a classified preview."""
    plan_rows: list[PricingImportExecutionRow] = []
    for row in preview.rows:
        if row.status != "valid":
            plan_rows.append(
                _execution_row_from_preview(
                    row,
                    action="invalid",
                    status="blocked",
                    errors=row.errors or ("row is invalid",),
                )
            )
            continue
        if row.classification != "create":
            plan_rows.append(
                _execution_row_from_preview(
                    row,
                    action="skipped",
                    status="blocked",
                    errors=(
                        "pricing import execution only creates new rows; "
                        f"{row.classification} rows are not supported in this workflow",
                    ),
                )
            )
            continue
        plan_rows.append(_execution_row_from_preview(row, action="create", status="ready"))

    blocked_count = sum(1 for row in plan_rows if row.status == "blocked")
    return PricingImportExecutionPlan(
        total_rows=len(plan_rows),
        executable_count=len(plan_rows) - blocked_count,
        blocked_count=blocked_count,
        rows=tuple(plan_rows),
    )


async def execute_pricing_import_plan(
    plan: PricingImportExecutionPlan,
    *,
    pricing_rule_service: PricingRuleService,
    actor_admin_id: uuid.UUID,
    reason: str,
) -> PricingImportExecutionResult:
    """Apply a validated create-only pricing import plan using the pricing service."""
    cleaned_reason = reason.strip()
    if not cleaned_reason:
        raise ValueError("audit reason is required")
    if not plan.executable:
        return PricingImportExecutionResult(
            total_rows=plan.total_rows,
            created_count=0,
            updated_count=0,
            skipped_count=sum(1 for row in plan.rows if row.status == "blocked"),
            error_count=plan.blocked_count,
            rows=plan.rows,
            audit_summary="No pricing rows were written.",
        )

    created_rows: list[PricingImportExecutionRow] = []
    for row in plan.rows:
        created = await pricing_rule_service.create_pricing_rule(
            provider=_required_plan_text(row.provider, field_name="provider", row_number=row.row_number),
            model=_required_plan_text(row.model, field_name="model", row_number=row.row_number),
            endpoint=_required_plan_text(row.endpoint, field_name="endpoint", row_number=row.row_number),
            currency=_required_plan_text(row.currency, field_name="currency", row_number=row.row_number),
            input_price_per_1m=_required_plan_decimal(
                row.input_price_per_1m,
                field_name="input_price_per_1m",
                row_number=row.row_number,
            ),
            cached_input_price_per_1m=_optional_plan_decimal(
                row.cached_input_price_per_1m,
                field_name="cached_input_price_per_1m",
                row_number=row.row_number,
            ),
            output_price_per_1m=_required_plan_decimal(
                row.output_price_per_1m,
                field_name="output_price_per_1m",
                row_number=row.row_number,
            ),
            reasoning_price_per_1m=_optional_plan_decimal(
                row.reasoning_price_per_1m,
                field_name="reasoning_price_per_1m",
                row_number=row.row_number,
            ),
            request_price=_optional_plan_decimal(
                row.request_price,
                field_name="request_price",
                row_number=row.row_number,
            ),
            pricing_metadata=row.pricing_metadata or {},
            valid_from=row.valid_from or datetime.now(UTC),
            valid_until=row.valid_until,
            source_url=row.source_url,
            notes=row.notes,
            enabled=True if row.enabled is None else row.enabled,
            actor_admin_id=actor_admin_id,
            reason=cleaned_reason,
        )
        created_rows.append(
            replace(
                row,
                action="created",
                status="created",
                pricing_rule_id=created.id,
                errors=(),
            )
        )

    return PricingImportExecutionResult(
        total_rows=plan.total_rows,
        created_count=len(created_rows),
        updated_count=0,
        skipped_count=0,
        error_count=0,
        rows=tuple(created_rows),
        audit_summary="Created pricing rules were audited individually.",
    )


def pricing_import_execution_result_to_dict(result: PricingImportExecutionResult) -> dict[str, object]:
    """Convert execution result DTOs to safe serializable values for tests or JSON-like rendering."""
    return {
        "total_rows": result.total_rows,
        "created_count": result.created_count,
        "updated_count": result.updated_count,
        "skipped_count": result.skipped_count,
        "error_count": result.error_count,
        "audit_summary": result.audit_summary,
        "rows": [
            {
                "row_number": row.row_number,
                "action": row.action,
                "status": row.status,
                "pricing_rule_id": str(row.pricing_rule_id) if row.pricing_rule_id else None,
                "provider": row.provider,
                "model": row.model,
                "endpoint": row.endpoint,
                "currency": row.currency,
                "input_price_per_1m": row.input_price_per_1m,
                "cached_input_price_per_1m": row.cached_input_price_per_1m,
                "output_price_per_1m": row.output_price_per_1m,
                "reasoning_price_per_1m": row.reasoning_price_per_1m,
                "request_price": row.request_price,
                "pricing_metadata": row.pricing_metadata,
                "valid_from": row.valid_from.isoformat() if row.valid_from else None,
                "valid_until": row.valid_until.isoformat() if row.valid_until else None,
                "source_url": row.source_url,
                "notes": row.notes,
                "enabled": row.enabled,
                "errors": list(row.errors),
            }
            for row in result.rows
        ],
    }


def _validate_one_row(row: Mapping[str, object], *, index: int, now: datetime) -> PricingImportRowPreview:
    unknown_fields = {str(field) for field in row if field not in PRICING_IMPORT_ALLOWED_FIELDS}
    if unknown_fields:
        raise ValueError(f"unknown fields: {', '.join(sorted(unknown_fields))}")

    model = row.get("model", row.get("upstream_model"))
    valid_from = _optional_import_datetime(row.get("valid_from"), field_name="valid_from") or now
    valid_until = _optional_import_datetime(row.get("valid_until"), field_name="valid_until")
    if valid_until is not None and valid_until <= valid_from:
        raise ValueError("valid_until must be after valid_from")

    pricing_metadata = _optional_import_metadata(row.get("pricing_metadata"))
    return PricingImportRowPreview(
        row_number=index,
        status="valid",
        classification="create",
        provider=_required_import_text(row.get("provider"), field_name="provider"),
        model=_required_import_text(model, field_name="model"),
        endpoint=normalize_endpoint(_optional_import_text(row.get("endpoint"), field_name="endpoint") or "chat.completions"),
        currency=_normalize_currency(_optional_import_text(row.get("currency"), field_name="currency") or "EUR"),
        input_price_per_1m=_required_import_decimal(row.get("input_price_per_1m"), field_name="input_price_per_1m"),
        cached_input_price_per_1m=_optional_import_decimal(
            row.get("cached_input_price_per_1m"),
            field_name="cached_input_price_per_1m",
        ),
        output_price_per_1m=_required_import_decimal(
            row.get("output_price_per_1m"),
            field_name="output_price_per_1m",
        ),
        reasoning_price_per_1m=_optional_import_decimal(
            row.get("reasoning_price_per_1m"),
            field_name="reasoning_price_per_1m",
        ),
        request_price=_optional_import_decimal(row.get("request_price"), field_name="request_price"),
        pricing_metadata=pricing_metadata,
        valid_from=valid_from,
        valid_until=valid_until,
        source_url=_optional_import_source_url(row.get("source_url")),
        notes=_optional_import_text(row.get("notes"), field_name="notes"),
        enabled=_optional_import_bool(row.get("enabled"), field_name="enabled", default=True),
    )


def _execution_row_from_preview(
    row: PricingImportRowPreview,
    *,
    action: str,
    status: str,
    errors: tuple[str, ...] = (),
) -> PricingImportExecutionRow:
    return PricingImportExecutionRow(
        row_number=row.row_number,
        action=action,
        status=status,
        provider=row.provider,
        model=row.model,
        endpoint=row.endpoint,
        currency=row.currency,
        input_price_per_1m=row.input_price_per_1m,
        cached_input_price_per_1m=row.cached_input_price_per_1m,
        output_price_per_1m=row.output_price_per_1m,
        reasoning_price_per_1m=row.reasoning_price_per_1m,
        request_price=row.request_price,
        pricing_metadata=row.pricing_metadata,
        valid_from=row.valid_from,
        valid_until=row.valid_until,
        source_url=row.source_url,
        notes=row.notes,
        enabled=row.enabled,
        errors=errors,
    )


def _required_plan_text(value: str | None, *, field_name: str, row_number: int) -> str:
    if value is None or not value.strip():
        raise ValueError(f"Pricing import row {row_number} is missing {field_name}")
    return value


def _required_plan_decimal(value: str | None, *, field_name: str, row_number: int) -> Decimal:
    parsed = _optional_plan_decimal(value, field_name=field_name, row_number=row_number)
    if parsed is None:
        raise ValueError(f"Pricing import row {row_number} is missing {field_name}")
    return parsed


def _optional_plan_decimal(value: str | None, *, field_name: str, row_number: int) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        parsed = Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"Pricing import row {row_number} field {field_name} must be a decimal string") from exc
    if not parsed.is_finite() or parsed < 0:
        raise ValueError(f"Pricing import row {row_number} field {field_name} must be non-negative")
    return parsed


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
    if not parsed.is_finite() or parsed < 0:
        raise ValueError(f"{field_name} must be non-negative")
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


def _optional_import_bool(value: object, *, field_name: str, default: bool) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off"}:
            return False
    raise ValueError(f"{field_name} must be boolean")


def _optional_import_source_url(value: object) -> str | None:
    source_url = _optional_import_text(value, field_name="source_url")
    if source_url is None:
        return None
    parsed = urlparse(source_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("source_url must be an absolute http or https URL")
    if parsed.username or parsed.password:
        raise ValueError("source_url must not contain credentials")
    return source_url


def _optional_import_metadata(value: object) -> dict[str, object]:
    if value is None or value == "":
        return {}
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError("pricing_metadata must be a JSON object") from exc
    else:
        parsed = value
    if not isinstance(parsed, dict):
        raise ValueError("pricing_metadata must be a JSON object")
    if _metadata_contains_secret(parsed):
        raise ValueError("pricing_metadata must not contain secret-looking values")
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
            if is_sensitive_key(key_text):
                return True
            if _metadata_contains_secret(item):
                return True
        return False
    if isinstance(value, list | tuple):
        return any(_metadata_contains_secret(item) for item in value)
    if isinstance(value, str):
        return _looks_like_secret(value)
    return False


def _classify_existing(row: PricingImportRowPreview, existing_rules: Iterable[object]) -> str:
    rules = list(existing_rules)
    if not rules:
        return "create"

    exact_matches = [
        rule
        for rule in rules
        if getattr(rule, "currency", None) == row.currency
        and _same_time(getattr(rule, "valid_from", None), row.valid_from)
        and _same_time(getattr(rule, "valid_until", None), row.valid_until)
    ]
    if exact_matches:
        return "duplicate" if any(bool(getattr(rule, "enabled", False)) for rule in exact_matches) else "disabled"

    if any(_windows_overlap(row.valid_from, row.valid_until, getattr(rule, "valid_from", None), getattr(rule, "valid_until", None)) for rule in rules):
        return "overlap"
    return "update"


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
