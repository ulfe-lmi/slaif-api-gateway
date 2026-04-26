"""Service helpers for FX rate metadata."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from slaif_gateway.db.models import FxRate
from slaif_gateway.db.repositories.audit import AuditRepository
from slaif_gateway.db.repositories.fx_rates import FxRatesRepository
from slaif_gateway.services.record_errors import RecordNotFoundError


class FxRateService:
    """Small service layer for FX rate CLI operations."""

    def __init__(
        self,
        *,
        fx_rates_repository: FxRatesRepository,
        audit_repository: AuditRepository,
    ) -> None:
        self._fx_rates = fx_rates_repository
        self._audit = audit_repository

    async def create_fx_rate(
        self,
        *,
        base_currency: str,
        quote_currency: str,
        rate: Decimal,
        valid_from: datetime,
        valid_until: datetime | None,
        source: str | None,
    ) -> FxRate:
        if rate <= 0:
            raise ValueError("rate must be positive")
        valid_from = _aware_time(valid_from)
        valid_until = _aware_time(valid_until) if valid_until is not None else None
        if valid_until is not None and valid_until <= valid_from:
            raise ValueError("valid_until must be after valid_from")

        row = await self._fx_rates.create_fx_rate(
            base_currency=_normalize_currency(base_currency),
            quote_currency=_normalize_currency(quote_currency),
            rate=rate,
            valid_from=valid_from,
            valid_until=valid_until,
            source=_clean_optional(source),
        )
        await self._audit.add_audit_log(
            action="fx_rate_created",
            entity_type="fx_rate",
            entity_id=row.id,
            new_values=_safe_audit_values(row),
        )
        return row

    async def list_fx_rates(
        self,
        *,
        base_currency: str | None,
        quote_currency: str | None,
        limit: int,
    ) -> list[FxRate]:
        return await self._fx_rates.list_fx_rates(
            base_currency=_normalize_currency(base_currency) if base_currency else None,
            quote_currency=_normalize_currency(quote_currency) if quote_currency else None,
            limit=limit,
        )

    async def latest_fx_rate(
        self,
        *,
        base_currency: str,
        quote_currency: str,
    ) -> FxRate:
        row = await self._fx_rates.find_latest_rate(
            base_currency=_normalize_currency(base_currency),
            quote_currency=_normalize_currency(quote_currency),
            at_time=datetime.now(UTC),
        )
        if row is None:
            raise RecordNotFoundError("FX rate")
        return row


def _normalize_currency(value: str) -> str:
    normalized = value.strip().upper()
    if len(normalized) != 3 or not normalized.isalpha():
        raise ValueError("Currency must be a 3-letter code")
    return normalized


def _aware_time(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value


def _clean_optional(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _safe_audit_values(row: FxRate) -> dict[str, object]:
    return {
        "base_currency": row.base_currency,
        "quote_currency": row.quote_currency,
        "rate": str(row.rate),
        "valid_from": row.valid_from.isoformat(),
        "valid_until": row.valid_until.isoformat() if row.valid_until is not None else None,
        "source": row.source,
    }
