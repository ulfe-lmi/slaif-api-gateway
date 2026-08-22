"""Atomic hierarchical recurring budget reservation service."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from slaif_gateway.db.models import BudgetPeriod, GatewayKey
from slaif_gateway.services.quota_errors import QuotaLimitExceededError


class BudgetService:
    """Reserve against all applicable budget periods in the caller's transaction.

    Rows are locked with ``SELECT ... FOR UPDATE`` before projection. Atomicity
    comes from the caller's PostgreSQL transaction; no Redis-only state exists.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def reserve(
        self,
        *,
        gateway_key: GatewayKey,
        reserved_cost_eur: Decimal,
        reserved_tokens: int,
        reserved_requests: int,
        now: datetime | None = None,
    ) -> list[BudgetPeriod]:
        check_now = _aware_now(now)
        owner_id = gateway_key.owner_id
        service_owner_id = getattr(gateway_key, "service_owner_id", None)
        applicable = await self._applicable_budgets(owner_id=owner_id, now=check_now)
        if service_owner_id is not None and service_owner_id != owner_id:
            applicable.extend(await self._applicable_budgets(owner_id=service_owner_id, now=check_now))

        locked_rows: list[BudgetPeriod] = []
        seen: set[uuid.UUID] = set()
        for row in applicable:
            if row.id in seen:
                continue
            locked = await self._session.get(BudgetPeriod, row.id, with_for_update=True)
            if locked is not None:
                seen.add(locked.id)
                locked_rows.append(locked)

        for budget in locked_rows:
            if budget.cost_limit_eur is not None:
                projected = (
                    Decimal(budget.cost_used_eur)
                    + Decimal(budget.cost_reserved_eur)
                    + reserved_cost_eur
                )
                if projected > Decimal(str(budget.cost_limit_eur)):
                    raise QuotaLimitExceededError("Budget cost limit exceeded", param="budget_cost")
            if budget.token_limit_total is not None:
                projected_tokens = (
                    int(budget.tokens_used_total) + int(budget.tokens_reserved_total) + reserved_tokens
                )
                if projected_tokens > int(budget.token_limit_total):
                    raise QuotaLimitExceededError("Budget token limit exceeded", param="budget_tokens")
            if budget.request_limit_total is not None:
                projected_requests = (
                    int(budget.requests_used_total)
                    + int(budget.requests_reserved_total)
                    + reserved_requests
                )
                if projected_requests > int(budget.request_limit_total):
                    raise QuotaLimitExceededError("Budget request limit exceeded", param="budget_requests")

        for budget in locked_rows:
            budget.cost_reserved_eur = Decimal(budget.cost_reserved_eur) + reserved_cost_eur
            budget.tokens_reserved_total += reserved_tokens
            budget.requests_reserved_total += reserved_requests
            budget.updated_at = check_now
        await self._session.flush()
        return locked_rows

    async def release(self, rows: list[BudgetPeriod], *, cost: Decimal, tokens: int, requests: int) -> None:
        for budget in rows:
            await awaitable_refresh(self._session, budget.id)
            budget.cost_reserved_eur = max(Decimal("0"), Decimal(budget.cost_reserved_eur) - cost)
            budget.tokens_reserved_total = max(0, int(budget.tokens_reserved_total) - tokens)
            budget.requests_reserved_total = max(0, int(budget.requests_reserved_total) - requests)
        await self._session.flush()

    async def finalize(self, rows: list[BudgetPeriod], *, cost: Decimal, tokens: int, requests: int) -> None:
        for budget in rows:
            await awaitable_refresh(self._session, budget.id)
            budget.cost_reserved_eur = max(Decimal("0"), Decimal(budget.cost_reserved_eur) - cost)
            budget.tokens_reserved_total = max(0, int(budget.tokens_reserved_total) - tokens)
            budget.requests_reserved_total = max(0, int(budget.requests_reserved_total) - requests)
            budget.cost_used_eur = Decimal(budget.cost_used_eur) + cost
            budget.tokens_used_total += tokens
            budget.requests_used_total += requests
        await self._session.flush()

    async def _applicable_budgets(self, *, owner_id: uuid.UUID, now: datetime) -> list[BudgetPeriod]:
        result = await self._session.execute(select(BudgetPeriod).where(BudgetPeriod.owner_id == owner_id))
        return [row for row in result.scalars().all() if row.period_start <= now < row.period_end]


async def awaitable_refresh(session: AsyncSession, object_id: uuid.UUID) -> BudgetPeriod | None:
    return await session.get(BudgetPeriod, object_id, with_for_update=True)


def _aware_now(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value
