"""Repository helpers for pricing_rules table operations."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from slaif_gateway.db.models import PricingRule


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
