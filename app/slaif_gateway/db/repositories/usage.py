"""Repository helpers for usage_ledger table operations."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from slaif_gateway.db.models import UsageLedger


class UsageLedgerRepository:
    """Encapsulates CRUD-style access for UsageLedger rows."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_usage_record(
        self,
        *,
        request_id: str,
        gateway_key_id: uuid.UUID,
        endpoint: str,
        provider: str,
        started_at: datetime,
        quota_reservation_id: uuid.UUID | None = None,
        client_request_id: str | None = None,
        idempotency_key: str | None = None,
        owner_id: uuid.UUID | None = None,
        institution_id: uuid.UUID | None = None,
        cohort_id: uuid.UUID | None = None,
        owner_email_snapshot: str | None = None,
        owner_name_snapshot: str | None = None,
        owner_surname_snapshot: str | None = None,
        institution_name_snapshot: str | None = None,
        cohort_name_snapshot: str | None = None,
        http_method: str = "POST",
        requested_model: str | None = None,
        resolved_model: str | None = None,
        upstream_request_id: str | None = None,
        streaming: bool = False,
        success: bool | None = None,
        accounting_status: str = "pending",
        http_status: int | None = None,
        error_type: str | None = None,
        error_message: str | None = None,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cached_tokens: int = 0,
        reasoning_tokens: int = 0,
        total_tokens: int = 0,
        estimated_cost_eur: Decimal | None = None,
        actual_cost_eur: Decimal | None = None,
        actual_cost_native: Decimal | None = None,
        native_currency: str | None = None,
        usage_raw: dict[str, object] | None = None,
        response_metadata: dict[str, object] | None = None,
        finished_at: datetime | None = None,
        latency_ms: int | None = None,
    ) -> UsageLedger:
        row = UsageLedger(
            request_id=request_id,
            client_request_id=client_request_id,
            idempotency_key=idempotency_key,
            quota_reservation_id=quota_reservation_id,
            gateway_key_id=gateway_key_id,
            owner_id=owner_id,
            institution_id=institution_id,
            cohort_id=cohort_id,
            owner_email_snapshot=owner_email_snapshot,
            owner_name_snapshot=owner_name_snapshot,
            owner_surname_snapshot=owner_surname_snapshot,
            institution_name_snapshot=institution_name_snapshot,
            cohort_name_snapshot=cohort_name_snapshot,
            endpoint=endpoint,
            http_method=http_method,
            provider=provider,
            requested_model=requested_model,
            resolved_model=resolved_model,
            upstream_request_id=upstream_request_id,
            streaming=streaming,
            success=success,
            accounting_status=accounting_status,
            http_status=http_status,
            error_type=error_type,
            error_message=error_message,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_tokens=cached_tokens,
            reasoning_tokens=reasoning_tokens,
            total_tokens=total_tokens,
            estimated_cost_eur=estimated_cost_eur,
            actual_cost_eur=actual_cost_eur,
            actual_cost_native=actual_cost_native,
            native_currency=native_currency,
            usage_raw=usage_raw or {},
            response_metadata=response_metadata or {},
            started_at=started_at,
            finished_at=finished_at,
            latency_ms=latency_ms,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def create_success_record(self, **kwargs: object) -> UsageLedger:
        """Create a finalized successful usage ledger row."""
        return await self.create_usage_record(
            success=True,
            accounting_status="finalized",
            **kwargs,
        )

    async def create_failure_record(self, **kwargs: object) -> UsageLedger:
        """Create a failure usage ledger row without prompt or response content."""
        return await self.create_usage_record(
            success=False,
            accounting_status="failed",
            **kwargs,
        )

    async def get_usage_record_by_id(self, usage_id: uuid.UUID) -> UsageLedger | None:
        return await self._session.get(UsageLedger, usage_id)

    async def get_usage_record_by_request_id(self, request_id: str) -> UsageLedger | None:
        result = await self._session.execute(select(UsageLedger).where(UsageLedger.request_id == request_id))
        return result.scalar_one_or_none()

    async def list_usage_for_key(
        self,
        gateway_key_id: uuid.UUID,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[UsageLedger]:
        statement: Select[tuple[UsageLedger]] = (
            select(UsageLedger)
            .where(UsageLedger.gateway_key_id == gateway_key_id)
            .order_by(UsageLedger.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    async def list_usage_for_owner(
        self,
        owner_id: uuid.UUID,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[UsageLedger]:
        statement: Select[tuple[UsageLedger]] = (
            select(UsageLedger)
            .where(UsageLedger.owner_id == owner_id)
            .order_by(UsageLedger.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    async def list_usage_for_cohort(
        self,
        cohort_id: uuid.UUID,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[UsageLedger]:
        statement: Select[tuple[UsageLedger]] = (
            select(UsageLedger)
            .where(UsageLedger.cohort_id == cohort_id)
            .order_by(UsageLedger.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    async def list_usage_by_provider_model(
        self,
        *,
        provider: str | None = None,
        resolved_model: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[UsageLedger]:
        statement: Select[tuple[UsageLedger]] = select(UsageLedger)
        if provider is not None:
            statement = statement.where(UsageLedger.provider == provider)
        if resolved_model is not None:
            statement = statement.where(UsageLedger.resolved_model == resolved_model)

        statement = statement.order_by(UsageLedger.created_at.desc()).limit(limit).offset(offset)
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    async def summarize_usage_for_key(self, gateway_key_id: uuid.UUID) -> dict[str, int | Decimal]:
        statement = select(
            func.coalesce(func.sum(UsageLedger.total_tokens), 0).label("total_tokens"),
            func.coalesce(func.sum(UsageLedger.prompt_tokens), 0).label("prompt_tokens"),
            func.coalesce(func.sum(UsageLedger.completion_tokens), 0).label("completion_tokens"),
            func.coalesce(func.sum(UsageLedger.input_tokens), 0).label("input_tokens"),
            func.coalesce(func.sum(UsageLedger.output_tokens), 0).label("output_tokens"),
            func.coalesce(func.sum(UsageLedger.actual_cost_eur), Decimal("0")).label("actual_cost_eur"),
        ).where(UsageLedger.gateway_key_id == gateway_key_id)
        result = await self._session.execute(statement)
        row = result.one()
        return {
            "total_tokens": int(row.total_tokens),
            "prompt_tokens": int(row.prompt_tokens),
            "completion_tokens": int(row.completion_tokens),
            "input_tokens": int(row.input_tokens),
            "output_tokens": int(row.output_tokens),
            "actual_cost_eur": Decimal(row.actual_cost_eur),
        }
