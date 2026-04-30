"""Dry-run parsing and validation for model route import previews."""

from __future__ import annotations

import csv
import json
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from io import StringIO
from urllib.parse import urlparse

from slaif_gateway.db.models import MATCH_TYPE_VALUES_MODEL_ROUTES
from slaif_gateway.services.model_route_service import ModelRouteService, normalize_endpoint
from slaif_gateway.utils.redaction import is_sensitive_key, redact_text

ROUTE_IMPORT_ALLOWED_FIELDS = {
    "requested_model",
    "model_pattern",
    "match_type",
    "endpoint",
    "provider",
    "provider_config_id",
    "upstream_model",
    "priority",
    "enabled",
    "visible_in_models",
    "visible",
    "supports_streaming",
    "streaming",
    "capabilities",
    "metadata",
    "notes",
}


@dataclass(frozen=True, slots=True)
class RouteImportProviderRef:
    """Safe provider config reference used for route import validation."""

    id: uuid.UUID
    provider: str


@dataclass(frozen=True, slots=True)
class RouteImportRowPreview:
    """Safe row-level result for a model route import dry-run."""

    row_number: int
    status: str
    classification: str
    requested_model: str | None = None
    match_type: str | None = None
    endpoint: str | None = None
    provider: str | None = None
    provider_config_id: uuid.UUID | None = None
    upstream_model: str | None = None
    priority: int | None = None
    enabled: bool | None = None
    visible_in_models: bool | None = None
    supports_streaming: bool | None = None
    capabilities: dict[str, object] | None = None
    notes: str | None = None
    errors: tuple[str, ...] = ()

    @property
    def capabilities_summary(self) -> str:
        if not self.capabilities:
            return "none"
        return ", ".join(sorted(str(key) for key in self.capabilities))


@dataclass(frozen=True, slots=True)
class RouteImportPreview:
    """Safe aggregate preview for a model route import dry-run."""

    total_rows: int
    valid_count: int
    invalid_count: int
    rows: tuple[RouteImportRowPreview, ...]


@dataclass(frozen=True, slots=True)
class RouteImportExecutionRow:
    """Safe row-level result for a model route import execution."""

    row_number: int
    action: str
    status: str
    route_id: uuid.UUID | None = None
    requested_model: str | None = None
    match_type: str | None = None
    endpoint: str | None = None
    provider: str | None = None
    provider_config_id: uuid.UUID | None = None
    upstream_model: str | None = None
    priority: int | None = None
    enabled: bool | None = None
    visible_in_models: bool | None = None
    supports_streaming: bool | None = None
    capabilities: dict[str, object] | None = None
    notes: str | None = None
    errors: tuple[str, ...] = ()

    @property
    def capabilities_summary(self) -> str:
        if not self.capabilities:
            return "none"
        return ", ".join(sorted(str(key) for key in self.capabilities))


@dataclass(frozen=True, slots=True)
class RouteImportExecutionPlan:
    """All-or-nothing execution plan for validated route import rows."""

    total_rows: int
    executable_count: int
    blocked_count: int
    rows: tuple[RouteImportExecutionRow, ...]

    @property
    def executable(self) -> bool:
        return self.total_rows > 0 and self.blocked_count == 0


@dataclass(frozen=True, slots=True)
class RouteImportExecutionResult:
    """Safe aggregate result for a model route import execution."""

    total_rows: int
    created_count: int
    updated_count: int
    skipped_count: int
    error_count: int
    rows: tuple[RouteImportExecutionRow, ...]
    audit_summary: str


def parse_route_import_csv(text: str) -> list[dict[str, object]]:
    """Parse route CSV text into raw row mappings."""
    try:
        reader = csv.DictReader(StringIO(text))
        if not reader.fieldnames:
            raise ValueError("Route CSV import must include a header row")
        return [dict(row) for row in reader]
    except csv.Error as exc:
        raise ValueError("Route import content is not valid CSV") from exc


def parse_route_import_json(text: str) -> list[dict[str, object]]:
    """Parse route JSON text into raw row mappings."""
    try:
        loaded = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("Route import content is not valid JSON") from exc
    if not isinstance(loaded, list):
        raise ValueError("Route JSON import must be a list of objects")
    if not all(isinstance(item, dict) for item in loaded):
        raise ValueError("Route JSON import must contain only objects")
    return list(loaded)


def detect_route_import_format(*, filename: str | None, requested_format: str, text: str) -> str:
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


def provider_refs_from_rows(provider_configs: Sequence[object]) -> tuple[RouteImportProviderRef, ...]:
    """Build safe provider references from provider config rows or DTOs."""
    refs: list[RouteImportProviderRef] = []
    for row in provider_configs:
        row_id = getattr(row, "id", None)
        provider = getattr(row, "provider", None)
        if isinstance(row_id, uuid.UUID) and isinstance(provider, str) and provider.strip():
            refs.append(RouteImportProviderRef(id=row_id, provider=provider.strip()))
    return tuple(refs)


def validate_route_import_rows(
    rows: Sequence[Mapping[str, object]],
    *,
    provider_configs: Sequence[RouteImportProviderRef],
    max_rows: int,
) -> RouteImportPreview:
    """Validate raw import rows and return a non-mutating preview."""
    if max_rows <= 0:
        raise ValueError("max_rows must be positive")
    if len(rows) > max_rows:
        raise ValueError(f"Route import may contain at most {max_rows} rows")

    provider_by_name = {provider.provider: provider for provider in provider_configs}
    provider_by_id = {provider.id: provider for provider in provider_configs}
    previews: list[RouteImportRowPreview] = []
    seen_keys: set[tuple[str, str, str]] = set()
    for index, row in enumerate(rows, start=1):
        try:
            preview = _validate_one_row(
                row,
                index=index,
                provider_by_name=provider_by_name,
                provider_by_id=provider_by_id,
            )
            key = (preview.requested_model or "", preview.match_type or "", preview.endpoint or "")
            if key in seen_keys:
                preview = replace(preview, classification="duplicate")
            else:
                seen_keys.add(key)
        except ValueError as exc:
            preview = RouteImportRowPreview(
                row_number=index,
                status="invalid",
                classification="invalid",
                errors=(str(exc),),
            )
        previews.append(preview)

    valid_count = sum(1 for row in previews if row.status == "valid")
    return RouteImportPreview(
        total_rows=len(previews),
        valid_count=valid_count,
        invalid_count=len(previews) - valid_count,
        rows=tuple(previews),
    )


def classify_route_import_preview(
    preview: RouteImportPreview,
    *,
    existing_routes_by_row: Mapping[int, Sequence[object]],
) -> RouteImportPreview:
    """Classify valid preview rows against existing model routes without mutation."""
    classified_rows: list[RouteImportRowPreview] = []
    for row in preview.rows:
        if row.status != "valid" or row.classification == "duplicate":
            classified_rows.append(row)
            continue
        classification = _classify_existing(row, existing_routes_by_row.get(row.row_number, ()))
        classified_rows.append(replace(row, classification=classification))
    return RouteImportPreview(
        total_rows=preview.total_rows,
        valid_count=preview.valid_count,
        invalid_count=preview.invalid_count,
        rows=tuple(classified_rows),
    )


def route_import_preview_to_dict(preview: RouteImportPreview) -> dict[str, object]:
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
                "requested_model": row.requested_model,
                "match_type": row.match_type,
                "endpoint": row.endpoint,
                "provider": row.provider,
                "provider_config_id": str(row.provider_config_id) if row.provider_config_id else None,
                "upstream_model": row.upstream_model,
                "priority": row.priority,
                "enabled": row.enabled,
                "visible_in_models": row.visible_in_models,
                "supports_streaming": row.supports_streaming,
                "capabilities": row.capabilities,
                "notes": row.notes,
                "errors": list(row.errors),
            }
            for row in preview.rows
        ],
    }


def build_route_import_execution_plan(preview: RouteImportPreview) -> RouteImportExecutionPlan:
    """Build a create-only execution plan from a classified route import preview."""
    plan_rows: list[RouteImportExecutionRow] = []
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
                        "route import execution only creates new rows; "
                        f"{row.classification} rows are not supported in this workflow",
                    ),
                )
            )
            continue
        plan_rows.append(_execution_row_from_preview(row, action="create", status="ready"))

    blocked_count = sum(1 for row in plan_rows if row.status == "blocked")
    return RouteImportExecutionPlan(
        total_rows=len(plan_rows),
        executable_count=len(plan_rows) - blocked_count,
        blocked_count=blocked_count,
        rows=tuple(plan_rows),
    )


async def execute_route_import_plan(
    plan: RouteImportExecutionPlan,
    *,
    model_route_service: ModelRouteService,
    actor_admin_id: uuid.UUID,
    reason: str,
) -> RouteImportExecutionResult:
    """Apply a validated create-only route import plan using the route service."""
    cleaned_reason = reason.strip()
    if not cleaned_reason:
        raise ValueError("audit reason is required")
    if not plan.executable:
        return RouteImportExecutionResult(
            total_rows=plan.total_rows,
            created_count=0,
            updated_count=0,
            skipped_count=sum(1 for row in plan.rows if row.status == "blocked"),
            error_count=plan.blocked_count,
            rows=plan.rows,
            audit_summary="No model route rows were written.",
        )

    created_rows: list[RouteImportExecutionRow] = []
    for row in plan.rows:
        created = await model_route_service.create_model_route(
            requested_model=_required_plan_text(row.requested_model, field_name="requested_model", row_number=row.row_number),
            match_type=_required_plan_text(row.match_type, field_name="match_type", row_number=row.row_number),
            endpoint=_required_plan_text(row.endpoint, field_name="endpoint", row_number=row.row_number),
            provider=_required_plan_text(row.provider, field_name="provider", row_number=row.row_number),
            upstream_model=_required_plan_text(row.upstream_model, field_name="upstream_model", row_number=row.row_number),
            priority=_required_plan_int(row.priority, field_name="priority", row_number=row.row_number),
            enabled=True if row.enabled is None else row.enabled,
            visible_in_models=True if row.visible_in_models is None else row.visible_in_models,
            supports_streaming=True if row.supports_streaming is None else row.supports_streaming,
            capabilities=row.capabilities or {},
            notes=row.notes,
            actor_admin_id=actor_admin_id,
            reason=cleaned_reason,
        )
        created_rows.append(
            replace(
                row,
                action="created",
                status="created",
                route_id=created.id,
                errors=(),
            )
        )

    return RouteImportExecutionResult(
        total_rows=plan.total_rows,
        created_count=len(created_rows),
        updated_count=0,
        skipped_count=0,
        error_count=0,
        rows=tuple(created_rows),
        audit_summary="Created model route rows were audited individually.",
    )


def route_import_execution_result_to_dict(result: RouteImportExecutionResult) -> dict[str, object]:
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
                "route_id": str(row.route_id) if row.route_id else None,
                "requested_model": row.requested_model,
                "match_type": row.match_type,
                "endpoint": row.endpoint,
                "provider": row.provider,
                "provider_config_id": str(row.provider_config_id) if row.provider_config_id else None,
                "upstream_model": row.upstream_model,
                "priority": row.priority,
                "enabled": row.enabled,
                "visible_in_models": row.visible_in_models,
                "supports_streaming": row.supports_streaming,
                "capabilities": row.capabilities,
                "notes": row.notes,
                "errors": list(row.errors),
            }
            for row in result.rows
        ],
    }


def _validate_one_row(
    row: Mapping[str, object],
    *,
    index: int,
    provider_by_name: Mapping[str, RouteImportProviderRef],
    provider_by_id: Mapping[uuid.UUID, RouteImportProviderRef],
) -> RouteImportRowPreview:
    unknown_fields = {str(field) for field in row if field not in ROUTE_IMPORT_ALLOWED_FIELDS}
    if unknown_fields:
        raise ValueError(f"unknown fields: {', '.join(sorted(unknown_fields))}")

    requested_model = _required_import_text(
        row.get("requested_model") or row.get("model_pattern"),
        field_name="requested_model",
        forbid_whitespace=True,
    )
    match_type = _optional_import_text(row.get("match_type"), field_name="match_type") or "exact"
    if match_type not in MATCH_TYPE_VALUES_MODEL_ROUTES:
        allowed = ", ".join(MATCH_TYPE_VALUES_MODEL_ROUTES)
        raise ValueError(f"match_type must be one of: {allowed}")
    endpoint = _parse_endpoint(row.get("endpoint"))
    provider_ref = _resolve_provider_ref(row, provider_by_name=provider_by_name, provider_by_id=provider_by_id)
    upstream_model = _required_import_text(
        row.get("upstream_model"),
        field_name="upstream_model",
        forbid_whitespace=True,
    )
    capabilities = _optional_import_metadata(row.get("capabilities") or row.get("metadata"))

    return RouteImportRowPreview(
        row_number=index,
        status="valid",
        classification="create",
        requested_model=requested_model,
        match_type=match_type,
        endpoint=endpoint,
        provider=provider_ref.provider,
        provider_config_id=provider_ref.id,
        upstream_model=upstream_model,
        priority=_optional_import_int(row.get("priority"), field_name="priority", default=100),
        enabled=_optional_import_bool(row.get("enabled"), field_name="enabled", default=True),
        visible_in_models=_optional_import_bool(
            row.get("visible_in_models", row.get("visible")),
            field_name="visible_in_models",
            default=True,
        ),
        supports_streaming=_optional_import_bool(
            row.get("supports_streaming", row.get("streaming")),
            field_name="supports_streaming",
            default=True,
        ),
        capabilities=capabilities,
        notes=_optional_import_text(row.get("notes"), field_name="notes"),
    )


def _resolve_provider_ref(
    row: Mapping[str, object],
    *,
    provider_by_name: Mapping[str, RouteImportProviderRef],
    provider_by_id: Mapping[uuid.UUID, RouteImportProviderRef],
) -> RouteImportProviderRef:
    provider_name = _optional_import_text(row.get("provider"), field_name="provider")
    provider_config_id = _optional_import_uuid(row.get("provider_config_id"), field_name="provider_config_id")

    provider_ref: RouteImportProviderRef | None = None
    if provider_config_id is not None:
        provider_ref = provider_by_id.get(provider_config_id)
        if provider_ref is None:
            raise ValueError("provider_config_id must reference an existing provider config")
    if provider_name is not None:
        named_ref = provider_by_name.get(provider_name)
        if named_ref is None:
            raise ValueError("provider must reference an existing provider config")
        if provider_ref is not None and named_ref.id != provider_ref.id:
            raise ValueError("provider and provider_config_id must reference the same provider config")
        provider_ref = named_ref
    if provider_ref is None:
        raise ValueError("provider or provider_config_id is required")
    return provider_ref


def _execution_row_from_preview(
    row: RouteImportRowPreview,
    *,
    action: str,
    status: str,
    errors: tuple[str, ...] = (),
) -> RouteImportExecutionRow:
    return RouteImportExecutionRow(
        row_number=row.row_number,
        action=action,
        status=status,
        requested_model=row.requested_model,
        match_type=row.match_type,
        endpoint=row.endpoint,
        provider=row.provider,
        provider_config_id=row.provider_config_id,
        upstream_model=row.upstream_model,
        priority=row.priority,
        enabled=row.enabled,
        visible_in_models=row.visible_in_models,
        supports_streaming=row.supports_streaming,
        capabilities=row.capabilities,
        notes=row.notes,
        errors=errors,
    )


def _required_plan_text(value: str | None, *, field_name: str, row_number: int) -> str:
    if value is None or not value.strip():
        raise ValueError(f"Route import row {row_number} is missing {field_name}")
    return value


def _required_plan_int(value: int | None, *, field_name: str, row_number: int) -> int:
    if value is None:
        raise ValueError(f"Route import row {row_number} is missing {field_name}")
    if value < 0:
        raise ValueError(f"Route import row {row_number} field {field_name} must be non-negative")
    return value


def _parse_endpoint(value: object) -> str:
    endpoint = _optional_import_text(value, field_name="endpoint", forbid_whitespace=True) or "chat.completions"
    normalized = normalize_endpoint(endpoint)
    if not normalized.startswith("/v1/"):
        raise ValueError("endpoint must be a /v1 path or chat.completions")
    parsed = urlparse(normalized)
    if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment:
        raise ValueError("endpoint must be a safe path without query parameters")
    return normalized


def _required_import_text(value: object, *, field_name: str, forbid_whitespace: bool = False) -> str:
    text = _optional_import_text(value, field_name=field_name, forbid_whitespace=forbid_whitespace)
    if text is None:
        raise ValueError(f"{field_name} is required")
    return text


def _optional_import_text(
    value: object,
    *,
    field_name: str,
    forbid_whitespace: bool = False,
) -> str | None:
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    cleaned = value.strip()
    if not cleaned:
        return None
    if forbid_whitespace and any(ch.isspace() for ch in cleaned):
        raise ValueError(f"{field_name} must not contain whitespace")
    if _looks_like_secret(cleaned):
        raise ValueError(f"{field_name} must not contain secret-looking values")
    return cleaned


def _optional_import_uuid(value: object, *, field_name: str) -> uuid.UUID | None:
    text = _optional_import_text(value, field_name=field_name)
    if text is None:
        return None
    try:
        return uuid.UUID(text)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be a UUID") from exc


def _optional_import_int(value: object, *, field_name: str, default: int) -> int:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a non-negative integer")
    if isinstance(value, int):
        parsed = value
    elif isinstance(value, str):
        normalized = value.strip()
        if not normalized:
            return default
        if not normalized.isdecimal():
            raise ValueError(f"{field_name} must be a non-negative integer")
        parsed = int(normalized)
    else:
        raise ValueError(f"{field_name} must be a non-negative integer")
    if parsed < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")
    return parsed


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


def _optional_import_metadata(value: object) -> dict[str, object]:
    if value is None or value == "":
        return {}
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError("capabilities must be a JSON object") from exc
    else:
        parsed = value
    if not isinstance(parsed, dict):
        raise ValueError("capabilities must be a JSON object")
    if _metadata_contains_secret(parsed):
        raise ValueError("capabilities must not contain secret-looking values")
    return dict(parsed)


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


def _classify_existing(row: RouteImportRowPreview, existing_routes: Sequence[object]) -> str:
    routes = [
        route
        for route in existing_routes
        if getattr(route, "requested_model", None) == row.requested_model
        and getattr(route, "match_type", None) == row.match_type
        and getattr(route, "endpoint", None) == row.endpoint
    ]
    if not routes:
        return "create"
    if any(_same_route(row, route) for route in routes):
        return "duplicate"
    if any(getattr(route, "provider", None) != row.provider for route in routes):
        return "conflict"
    return "update"


def _same_route(row: RouteImportRowPreview, route: object) -> bool:
    return (
        getattr(route, "requested_model", None) == row.requested_model
        and getattr(route, "match_type", None) == row.match_type
        and getattr(route, "endpoint", None) == row.endpoint
        and getattr(route, "provider", None) == row.provider
        and getattr(route, "upstream_model", None) == row.upstream_model
        and getattr(route, "priority", None) == row.priority
        and bool(getattr(route, "enabled", False)) == row.enabled
        and bool(getattr(route, "visible_in_models", False)) == row.visible_in_models
        and bool(getattr(route, "supports_streaming", False)) == row.supports_streaming
        and (getattr(route, "capabilities", None) or {}) == (row.capabilities or {})
        and (getattr(route, "notes", None) or None) == (row.notes or None)
    )
