"""Service helpers for pricing rule metadata."""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

from slaif_gateway.db.models import PricingRule
from slaif_gateway.db.repositories.audit import AuditRepository
from slaif_gateway.db.repositories.pricing import PricingRulesRepository
from slaif_gateway.services.model_route_service import normalize_endpoint
from slaif_gateway.services.record_errors import RecordNotFoundError


_ALLOWED_IMPORT_FIELDS = {
    "provider",
    "model",
    "upstream_model",
    "endpoint",
    "currency",
    "input_price_per_1m",
    "output_price_per_1m",
    "cached_input_price_per_1m",
    "reasoning_price_per_1m",
    "valid_from",
    "valid_until",
    "source_url",
    "notes",
    "enabled",
}


@dataclass(frozen=True, slots=True)
class PricingImportResult:
    """Result for a pricing import operation."""

    imported_count: int
    dry_run: bool
    rows: tuple[PricingRule | dict[str, object], ...]


class PricingRuleService:
    """Small service layer for pricing rule CLI operations."""

    def __init__(
        self,
        *,
        pricing_rules_repository: PricingRulesRepository,
        audit_repository: AuditRepository,
    ) -> None:
        self._pricing = pricing_rules_repository
        self._audit = audit_repository

    async def create_pricing_rule(
        self,
        *,
        provider: str,
        model: str,
        endpoint: str,
        currency: str,
        input_price_per_1m: Decimal,
        output_price_per_1m: Decimal,
        cached_input_price_per_1m: Decimal | None,
        reasoning_price_per_1m: Decimal | None,
        valid_from: datetime,
        valid_until: datetime | None,
        source_url: str | None,
        notes: str | None,
        enabled: bool,
    ) -> PricingRule:
        _validate_non_negative(input_price_per_1m, "input_price_per_1m")
        _validate_non_negative(output_price_per_1m, "output_price_per_1m")
        _validate_optional_non_negative(cached_input_price_per_1m, "cached_input_price_per_1m")
        _validate_optional_non_negative(reasoning_price_per_1m, "reasoning_price_per_1m")
        valid_from = _aware_time(valid_from)
        valid_until = _optional_aware_time(valid_until)
        _validate_validity(valid_from, valid_until)

        row = await self._pricing.create_pricing_rule(
            provider=_required_text(provider, "Provider"),
            upstream_model=_required_text(model, "Model"),
            endpoint=normalize_endpoint(endpoint),
            currency=_normalize_currency(currency),
            input_price_per_1m=input_price_per_1m,
            cached_input_price_per_1m=cached_input_price_per_1m,
            output_price_per_1m=output_price_per_1m,
            reasoning_price_per_1m=reasoning_price_per_1m,
            valid_from=valid_from,
            valid_until=valid_until,
            enabled=enabled,
            source_url=_clean_optional(source_url),
            notes=_clean_optional(notes),
        )
        await self._audit.add_audit_log(
            action="pricing_rule_created",
            entity_type="pricing_rule",
            entity_id=row.id,
            new_values=_safe_audit_values(row),
        )
        return row

    async def list_pricing_rules(
        self,
        *,
        provider: str | None,
        model: str | None,
        endpoint: str | None,
        enabled_only: bool,
        limit: int,
    ) -> list[PricingRule]:
        rows = await self._pricing.list_pricing_rules(
            provider=_clean_optional(provider),
            upstream_model=_clean_optional(model),
            endpoint=normalize_endpoint(endpoint) if endpoint else None,
            limit=limit,
        )
        if enabled_only:
            rows = [row for row in rows if row.enabled]
        return rows

    async def get_pricing_rule(self, pricing_rule_id: uuid.UUID) -> PricingRule:
        row = await self._pricing.get_pricing_rule_by_id(pricing_rule_id)
        if row is None:
            raise RecordNotFoundError("Pricing rule")
        return row

    async def disable_model(
        self,
        *,
        provider: str,
        model: str,
        endpoint: str | None,
    ) -> list[PricingRule]:
        rows = await self._pricing.list_pricing_rules_for_provider_model(
            provider=_required_text(provider, "Provider"),
            upstream_model=_required_text(model, "Model"),
            endpoint=normalize_endpoint(endpoint) if endpoint else None,
        )
        disabled: list[PricingRule] = []
        for row in rows:
            if not row.enabled:
                continue
            old_enabled = row.enabled
            updated = await self._pricing.set_pricing_rule_enabled(row.id, enabled=False)
            if updated:
                row.enabled = False
                disabled.append(row)
                await self._audit.add_audit_log(
                    action="pricing_rule_disabled",
                    entity_type="pricing_rule",
                    entity_id=row.id,
                    old_values={"enabled": old_enabled},
                    new_values={"enabled": False},
                )
        return disabled

    async def import_pricing_rules(
        self,
        rows: Sequence[Mapping[str, object]],
        *,
        dry_run: bool,
    ) -> PricingImportResult:
        prepared = [_prepare_import_row(row, index=index) for index, row in enumerate(rows, start=1)]
        if dry_run:
            return PricingImportResult(imported_count=0, dry_run=True, rows=tuple(prepared))

        created: list[PricingRule] = []
        for row in prepared:
            created.append(await self.create_pricing_rule(**row))

        await self._audit.add_audit_log(
            action="pricing_rules_imported",
            entity_type="pricing_rule",
            new_values={"imported_count": len(created)},
        )
        return PricingImportResult(imported_count=len(created), dry_run=False, rows=tuple(created))


def _prepare_import_row(row: Mapping[str, object], *, index: int) -> dict[str, object]:
    unknown_fields = set(row) - _ALLOWED_IMPORT_FIELDS
    if unknown_fields:
        fields = ", ".join(sorted(unknown_fields))
        raise ValueError(f"Pricing import row {index} has unknown fields: {fields}")

    model = row.get("model", row.get("upstream_model"))
    return {
        "provider": _required_import_text(row.get("provider"), index=index, field_name="provider"),
        "model": _required_import_text(model, index=index, field_name="model"),
        "endpoint": str(row.get("endpoint") or "chat.completions"),
        "currency": str(row.get("currency") or "EUR"),
        "input_price_per_1m": _required_import_decimal(
            row.get("input_price_per_1m"),
            index=index,
            field_name="input_price_per_1m",
        ),
        "output_price_per_1m": _required_import_decimal(
            row.get("output_price_per_1m"),
            index=index,
            field_name="output_price_per_1m",
        ),
        "cached_input_price_per_1m": _optional_import_decimal(
            row.get("cached_input_price_per_1m"),
            index=index,
            field_name="cached_input_price_per_1m",
        ),
        "reasoning_price_per_1m": _optional_import_decimal(
            row.get("reasoning_price_per_1m"),
            index=index,
            field_name="reasoning_price_per_1m",
        ),
        "valid_from": _optional_import_datetime(row.get("valid_from"), index=index, field_name="valid_from")
        or datetime.now(UTC),
        "valid_until": _optional_import_datetime(
            row.get("valid_until"),
            index=index,
            field_name="valid_until",
        ),
        "source_url": _optional_import_text(row.get("source_url"), index=index, field_name="source_url"),
        "notes": _optional_import_text(row.get("notes"), index=index, field_name="notes"),
        "enabled": _optional_import_bool(row.get("enabled"), index=index, field_name="enabled", default=True),
    }


def _required_text(value: str, label: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{label} cannot be empty")
    return normalized


def _clean_optional(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _normalize_currency(value: str) -> str:
    normalized = _required_text(value, "Currency").upper()
    if len(normalized) != 3 or not normalized.isalpha():
        raise ValueError("Currency must be a 3-letter code")
    return normalized


def _aware_time(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value


def _optional_aware_time(value: datetime | None) -> datetime | None:
    return _aware_time(value) if value is not None else None


def _validate_validity(valid_from: datetime, valid_until: datetime | None) -> None:
    if valid_until is not None and valid_until <= valid_from:
        raise ValueError("valid_until must be after valid_from")


def _validate_non_negative(value: Decimal, field_name: str) -> None:
    if value < 0:
        raise ValueError(f"{field_name} must be non-negative")


def _validate_optional_non_negative(value: Decimal | None, field_name: str) -> None:
    if value is not None:
        _validate_non_negative(value, field_name)


def _required_import_text(value: object, *, index: int, field_name: str) -> str:
    if value is None:
        raise ValueError(f"Pricing import row {index} is missing {field_name}")
    return _required_text(str(value), field_name)


def _optional_import_text(value: object, *, index: int, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"Pricing import row {index} field {field_name} must be a string")
    return _clean_optional(value)


def _required_import_decimal(value: object, *, index: int, field_name: str) -> Decimal:
    parsed = _optional_import_decimal(value, index=index, field_name=field_name)
    if parsed is None:
        raise ValueError(f"Pricing import row {index} is missing {field_name}")
    return parsed


def _optional_import_decimal(value: object, *, index: int, field_name: str) -> Decimal | None:
    if value is None or value == "":
        return None
    if isinstance(value, float):
        raise ValueError(f"Pricing import row {index} field {field_name} must be a decimal string")
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(
            f"Pricing import row {index} field {field_name} must be a decimal value"
        ) from exc
    _validate_non_negative(parsed, field_name)
    return parsed


def _optional_import_datetime(value: object, *, index: int, field_name: str) -> datetime | None:
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise ValueError(f"Pricing import row {index} field {field_name} must be an ISO datetime")
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(
            f"Pricing import row {index} field {field_name} must be an ISO datetime"
        ) from exc
    return _aware_time(parsed)


def _optional_import_bool(
    value: object,
    *,
    index: int,
    field_name: str,
    default: bool,
) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes"}:
            return True
        if normalized in {"false", "0", "no"}:
            return False
    raise ValueError(f"Pricing import row {index} field {field_name} must be boolean")


def _safe_audit_values(row: PricingRule) -> dict[str, object]:
    return {
        "provider": row.provider,
        "upstream_model": row.upstream_model,
        "endpoint": row.endpoint,
        "currency": row.currency,
        "input_price_per_1m": str(row.input_price_per_1m) if row.input_price_per_1m is not None else None,
        "cached_input_price_per_1m": (
            str(row.cached_input_price_per_1m)
            if row.cached_input_price_per_1m is not None
            else None
        ),
        "output_price_per_1m": str(row.output_price_per_1m) if row.output_price_per_1m is not None else None,
        "reasoning_price_per_1m": (
            str(row.reasoning_price_per_1m) if row.reasoning_price_per_1m is not None else None
        ),
        "valid_from": row.valid_from.isoformat(),
        "valid_until": row.valid_until.isoformat() if row.valid_until is not None else None,
        "enabled": row.enabled,
        "source_url": row.source_url,
        "notes": row.notes,
    }
