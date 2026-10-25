"""Repository helpers for pricing_rules table operations."""

from __future__ import annotations

import types
import uuid
from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal
from sqlalchemy import Select, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from slaif_gateway.db.models import PricingRule
from slaif_gateway.utils.admin_list_filters import as_value_tuple, or_equals

# Column keys of the pricing_rules row returned by _COHERENT_PAIR_SQL. The
# attribute set matches what services.pricing._pricing_lookup_result reads
# off a pricing row, so a SimpleNamespace built from these keys can be
# passed through the same lookup-result construction.
_PRICE_ROW_KEYS = (
    "id",
    "provider",
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
    "enabled",
)

# Single-statement coherent pair capture. One snapshot (one statement under
# READ COMMITTED) selects BOTH the active enabled pricing rule and the
# native->EUR FX row, so a concurrent price+FX supersession can only be
# observed as the complete old pair or the complete new pair, never mixed.
#
# Price side mirrors PricingRulesRepository.find_active_pricing_rule exactly:
# enabled, valid_from <= at_time, valid_until IS NULL OR > at_time, most
# recent valid_from first. FX side mirrors FxRatesRepository.find_latest_rate
# for (base_currency=<price currency>, quote_currency='EUR'): same validity
# window, most recent valid_from first, created_at tie-break. The LEFT JOIN
# LATERAL leaves the fx columns NULL when the price currency is EUR (the
# read-free conversion) or no active rate exists; the caller decides the
# fail-closed behavior.
_COHERENT_PAIR_SQL = text(
    "SELECT p.id, p.provider, p.upstream_model, p.endpoint, p.currency, "
    "p.input_price_per_1m, p.cached_input_price_per_1m, "
    "p.output_price_per_1m, p.reasoning_price_per_1m, p.request_price, "
    "p.pricing_metadata, p.valid_from, p.valid_until, p.enabled, "
    "f.id AS fx_id, f.base_currency AS fx_base_currency, "
    "f.quote_currency AS fx_quote_currency, f.rate AS fx_rate, "
    "f.valid_from AS fx_valid_from, f.valid_until AS fx_valid_until, "
    "f.source AS fx_source, f.created_at AS fx_created_at "
    "FROM ("
    "  SELECT * FROM pricing_rules "
    "  WHERE provider = :provider "
    "    AND upstream_model = :upstream_model "
    "    AND endpoint = :endpoint "
    "    AND enabled = TRUE "
    "    AND valid_from <= :at_time "
    "    AND (valid_until IS NULL OR valid_until > :at_time) "
    "  ORDER BY valid_from DESC "
    "  LIMIT 1"
    ") AS p "
    "LEFT JOIN LATERAL ("
    "  SELECT * FROM fx_rates "
    "  WHERE base_currency = p.currency "
    "    AND quote_currency = 'EUR' "
    "    AND p.currency <> 'EUR' "
    "    AND valid_from <= :at_time "
    "    AND (valid_until IS NULL OR valid_until > :at_time) "
    "  ORDER BY valid_from DESC, created_at DESC "
    "  LIMIT 1"
    ") AS f ON TRUE"
)


class PricingRulesRepository:
    """Encapsulates CRUD-style access for PricingRule rows."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_pricing_rule(
        self,
        *,
        provider: str,
        upstream_model: str,
        valid_from: datetime,
        endpoint: str = "/v1/chat/completions",
        currency: str = "USD",
        input_price_per_1m: Decimal | None = None,
        cached_input_price_per_1m: Decimal | None = None,
        output_price_per_1m: Decimal | None = None,
        reasoning_price_per_1m: Decimal | None = None,
        request_price: Decimal | None = None,
        pricing_metadata: dict[str, object] | None = None,
        valid_until: datetime | None = None,
        enabled: bool = True,
        source_url: str | None = None,
        notes: str | None = None,
    ) -> PricingRule:
        row = PricingRule(
            provider=provider,
            upstream_model=upstream_model,
            endpoint=endpoint,
            currency=currency,
            input_price_per_1m=input_price_per_1m,
            cached_input_price_per_1m=cached_input_price_per_1m,
            output_price_per_1m=output_price_per_1m,
            reasoning_price_per_1m=reasoning_price_per_1m,
            request_price=request_price,
            pricing_metadata=pricing_metadata or {},
            valid_from=valid_from,
            valid_until=valid_until,
            enabled=enabled,
            source_url=source_url,
            notes=notes,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def get_pricing_rule_by_id(self, pricing_rule_id: uuid.UUID) -> PricingRule | None:
        return await self._session.get(PricingRule, pricing_rule_id)

    async def list_pricing_rules(
        self,
        *,
        provider: str | None = None,
        upstream_model: str | None = None,
        endpoint: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[PricingRule]:
        statement: Select[tuple[PricingRule]] = select(PricingRule)
        if provider is not None:
            statement = statement.where(PricingRule.provider == provider)
        if upstream_model is not None:
            statement = statement.where(PricingRule.upstream_model == upstream_model)
        if endpoint is not None:
            statement = statement.where(PricingRule.endpoint == endpoint)

        statement = (
            statement.order_by(PricingRule.valid_from.desc(), PricingRule.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    async def list_pricing_rules_for_admin(
        self,
        *,
        provider: str | Sequence[str] | None = None,
        model: str | Sequence[str] | None = None,
        endpoint: str | Sequence[str] | None = None,
        currency: str | Sequence[str] | None = None,
        enabled: bool | None = None,
        active: bool | None = None,
        now: datetime | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[PricingRule]:
        providers = as_value_tuple(provider)
        models = as_value_tuple(model)
        endpoints = as_value_tuple(endpoint)
        currencies = as_value_tuple(currency)
        # 195-a: OR WITHIN a field, AND ACROSS fields; the pre-195
        # per-member normalization is preserved exactly (exact provider/
        # endpoint/currency equality, case-insensitive substring for the
        # upstream model).
        statement: Select[tuple[PricingRule]] = select(PricingRule)
        if providers is not None:
            statement = statement.where(or_equals(PricingRule.provider, providers))
        if models is not None:
            statement = statement.where(
                or_(
                    *[
                        PricingRule.upstream_model.ilike(f"%{value}%")
                        for value in models
                    ]
                )
            )
        if endpoints is not None:
            statement = statement.where(or_equals(PricingRule.endpoint, endpoints))
        if currencies is not None:
            statement = statement.where(or_equals(PricingRule.currency, currencies))
        if enabled is not None:
            statement = statement.where(PricingRule.enabled == enabled)
        if active is not None and now is not None:
            active_condition = (
                (PricingRule.valid_from <= now)
                & ((PricingRule.valid_until.is_(None)) | (PricingRule.valid_until >= now))
            )
            statement = statement.where(active_condition if active else ~active_condition)

        statement = (
            statement.order_by(PricingRule.valid_from.desc(), PricingRule.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    async def get_pricing_rule_for_admin_detail(self, pricing_rule_id: uuid.UUID) -> PricingRule | None:
        return await self._session.get(PricingRule, pricing_rule_id)

    async def list_enabled_pricing_rules(
        self,
        *,
        provider: str | None = None,
        endpoint: str | None = None,
    ) -> list[PricingRule]:
        statement: Select[tuple[PricingRule]] = select(PricingRule).where(PricingRule.enabled.is_(True))
        if provider is not None:
            statement = statement.where(PricingRule.provider == provider)
        if endpoint is not None:
            statement = statement.where(PricingRule.endpoint == endpoint)

        statement = statement.order_by(PricingRule.valid_from.desc(), PricingRule.created_at.desc())
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    async def list_pricing_rules_for_provider_model(
        self,
        *,
        provider: str,
        upstream_model: str,
        endpoint: str | None = None,
    ) -> list[PricingRule]:
        statement: Select[tuple[PricingRule]] = select(PricingRule).where(
            PricingRule.provider == provider,
            PricingRule.upstream_model == upstream_model,
        )
        if endpoint is not None:
            statement = statement.where(PricingRule.endpoint == endpoint)

        statement = statement.order_by(PricingRule.valid_from.desc(), PricingRule.created_at.desc())
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    async def set_pricing_rule_enabled(self, pricing_rule_id: uuid.UUID, *, enabled: bool) -> bool:
        row = await self.get_pricing_rule_by_id(pricing_rule_id)
        if row is None:
            return False

        row.enabled = enabled
        await self._session.flush()
        return True

    async def update_pricing_rule_metadata(
        self,
        pricing_rule_id: uuid.UUID,
        *,
        provider: str,
        upstream_model: str,
        endpoint: str,
        currency: str,
        input_price_per_1m: Decimal,
        cached_input_price_per_1m: Decimal | None,
        output_price_per_1m: Decimal,
        reasoning_price_per_1m: Decimal | None,
        request_price: Decimal | None,
        pricing_metadata: dict[str, object],
        valid_from: datetime,
        valid_until: datetime | None,
        enabled: bool,
        source_url: str | None,
        notes: str | None,
    ) -> bool:
        row = await self.get_pricing_rule_by_id(pricing_rule_id)
        if row is None:
            return False

        row.provider = provider
        row.upstream_model = upstream_model
        row.endpoint = endpoint
        row.currency = currency
        row.input_price_per_1m = input_price_per_1m
        row.cached_input_price_per_1m = cached_input_price_per_1m
        row.output_price_per_1m = output_price_per_1m
        row.reasoning_price_per_1m = reasoning_price_per_1m
        row.request_price = request_price
        row.pricing_metadata = pricing_metadata
        row.valid_from = valid_from
        row.valid_until = valid_until
        row.enabled = enabled
        row.source_url = source_url
        row.notes = notes
        await self._session.flush()
        return True

    async def find_active_pricing_rule(
        self,
        *,
        provider: str,
        upstream_model: str,
        endpoint: str,
        at_time: datetime,
    ) -> PricingRule | None:
        statement: Select[tuple[PricingRule]] = (
            select(PricingRule)
            .where(
                PricingRule.provider == provider,
                PricingRule.upstream_model == upstream_model,
                PricingRule.endpoint == endpoint,
                PricingRule.enabled.is_(True),
                PricingRule.valid_from <= at_time,
                (PricingRule.valid_until.is_(None)) | (PricingRule.valid_until > at_time),
            )
            .order_by(PricingRule.valid_from.desc())
            .limit(1)
        )
        result = await self._session.execute(statement)
        return result.scalar_one_or_none()

    async def find_active_pricing_rule_with_fx(
        self,
        *,
        provider: str,
        upstream_model: str,
        endpoint: str,
        at_time: datetime,
    ) -> tuple[types.SimpleNamespace | None, types.SimpleNamespace | None]:
        """Coherent admission capture: price row AND native->EUR FX row from
        ONE statement (one snapshot), or (None, None) when no active enabled
        pricing rule matches. The FX row is None when the currency is EUR or
        no active rate exists (the caller decides the fail-closed behavior).
        """
        result = await self._session.execute(
            _COHERENT_PAIR_SQL,
            {
                "provider": provider,
                "upstream_model": upstream_model,
                "endpoint": endpoint,
                "at_time": at_time,
            },
        )
        row = result.mappings().first()
        if row is None:
            return None, None
        price = types.SimpleNamespace(**{key: row[key] for key in _PRICE_ROW_KEYS})
        if row["fx_id"] is None:
            return price, None
        fx = types.SimpleNamespace(
            id=row["fx_id"],
            base_currency=row["fx_base_currency"],
            quote_currency=row["fx_quote_currency"],
            rate=row["fx_rate"],
            valid_from=row["fx_valid_from"],
            valid_until=row["fx_valid_until"],
            source=row["fx_source"],
            created_at=row["fx_created_at"],
        )
        return price, fx

    async def close_active_pricing_rule(
        self,
        *,
        pricing_rule_id: uuid.UUID,
        provider: str,
        upstream_model: str,
        endpoint: str,
        currency: str,
        valid_from: datetime,
        expected_valid_until: datetime | None,
        effective_at: datetime,
    ) -> bool:
        """Supersession close: end the active validity window of EXACTLY the
        row the reviewed plan identified, at the one effective T.

        Guarded on the baseline facts recorded in the plan (row identity,
        currency, opening instant, the REVIEWED closing instant, still
        active at T, still enabled). The reviewed closing instant is
        compared with exact NULL-safe equality (IS NOT DISTINCT FROM): a
        reviewed NULL end must still be NULL at apply time (a NULL ->
        finite drift is rejected, never wildcarded), and a reviewed finite
        future end — ordinary refresh state — must still be exactly that
        end and still in the future at T. Any drift or expiry means the row
        is not the reviewed active row and NOTHING is mutated. The window
        is then safely ended at the one effective T while the amount,
        currency, metadata and row identity stay untouched; the new row is
        inserted at the same instant by the caller (history is preserved,
        never repriced in place).
        """
        result = await self._session.execute(
            text(
                "UPDATE pricing_rules SET valid_until = :effective_at "
                "WHERE id = :id "
                "AND provider = :provider "
                "AND upstream_model = :upstream_model "
                "AND endpoint = :endpoint "
                "AND currency = :currency "
                "AND valid_from = :valid_from "
                "AND enabled = TRUE "
                "AND valid_until IS NOT DISTINCT FROM :expected_valid_until "
                "AND (valid_until IS NULL OR valid_until > :effective_at)"
            ),
            {
                "id": pricing_rule_id,
                "provider": provider,
                "upstream_model": upstream_model,
                "endpoint": endpoint,
                "currency": currency,
                "valid_from": valid_from,
                "expected_valid_until": expected_valid_until,
                "effective_at": effective_at,
            },
        )
        return result.rowcount == 1
