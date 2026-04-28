"""Repository helpers for usage_ledger table operations."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Select, or_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from slaif_gateway.db.models import UsageLedger
from slaif_gateway.utils.sanitization import sanitize_metadata_mapping


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
            usage_raw=sanitize_metadata_mapping(usage_raw, drop_content_keys=True),
            response_metadata=sanitize_metadata_mapping(response_metadata, drop_content_keys=True),
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

    async def create_provider_completed_record(self, **kwargs: object) -> UsageLedger:
        """Create a durable provider-completed row before final counter mutation."""
        return await self.create_usage_record(
            success=None,
            accounting_status="pending",
            **kwargs,
        )

    async def mark_provider_completed_record_finalized(
        self,
        usage_ledger_id: uuid.UUID,
        *,
        http_status: int,
        response_metadata: dict[str, object],
        finished_at: datetime,
        latency_ms: int | None,
    ) -> UsageLedger:
        """Mark a provider-completed recovery row finalized after quota finalization."""
        row = await self.get_usage_record_by_id(usage_ledger_id)
        if row is None:
            raise LookupError("Usage ledger row was not found")

        row.success = True
        row.accounting_status = "finalized"
        row.http_status = http_status
        row.error_type = None
        row.error_message = None
        row.response_metadata = sanitize_metadata_mapping(response_metadata, drop_content_keys=True)
        row.finished_at = finished_at
        row.latency_ms = latency_ms
        await self._session.flush()
        return row

    async def mark_provider_completed_record_finalization_failed(
        self,
        usage_ledger_id: uuid.UUID,
        *,
        error_type: str,
        error_message: str,
        response_metadata: dict[str, object],
        finished_at: datetime,
        latency_ms: int | None,
    ) -> UsageLedger:
        """Mark a provider-completed row as requiring accounting reconciliation."""
        row = await self.get_usage_record_by_id(usage_ledger_id)
        if row is None:
            raise LookupError("Usage ledger row was not found")

        row.success = None
        row.accounting_status = "failed"
        row.error_type = error_type
        row.error_message = error_message
        row.response_metadata = sanitize_metadata_mapping(response_metadata, drop_content_keys=True)
        row.finished_at = finished_at
        row.latency_ms = latency_ms
        await self._session.flush()
        return row

    async def list_provider_completed_recovery_records(
        self,
        *,
        limit: int = 100,
        gateway_key_id: uuid.UUID | None = None,
        provider: str | None = None,
        model: str | None = None,
        older_than: datetime | None = None,
    ) -> list[UsageLedger]:
        statement: Select[tuple[UsageLedger]] = _provider_completed_recovery_statement()
        if gateway_key_id is not None:
            statement = statement.where(UsageLedger.gateway_key_id == gateway_key_id)
        if provider is not None:
            statement = statement.where(UsageLedger.provider == provider)
        if model is not None:
            statement = statement.where(
                or_(
                    UsageLedger.requested_model == model,
                    UsageLedger.resolved_model == model,
                )
            )
        if older_than is not None:
            statement = statement.where(UsageLedger.created_at <= older_than)
        statement = statement.order_by(UsageLedger.created_at.asc()).limit(limit)
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    async def get_provider_completed_recovery_record_for_update(
        self,
        *,
        usage_ledger_id: uuid.UUID | None = None,
        reservation_id: uuid.UUID | None = None,
    ) -> UsageLedger | None:
        statement: Select[tuple[UsageLedger]] = _provider_completed_recovery_statement().with_for_update()
        if usage_ledger_id is not None:
            statement = statement.where(UsageLedger.id == usage_ledger_id)
        if reservation_id is not None:
            statement = statement.where(UsageLedger.quota_reservation_id == reservation_id)
        result = await self._session.execute(statement)
        return result.scalar_one_or_none()

    async def mark_provider_completed_reconciled(
        self,
        usage_ledger_id: uuid.UUID,
        *,
        response_metadata: dict[str, object],
        finished_at: datetime,
    ) -> UsageLedger:
        """Mark an existing provider-completed recovery row finalized by repair."""
        row = await self.get_usage_record_by_id(usage_ledger_id)
        if row is None:
            raise LookupError("Usage ledger row was not found")

        row.success = True
        row.accounting_status = "finalized"
        row.error_type = None
        row.error_message = None
        row.response_metadata = sanitize_metadata_mapping(response_metadata, drop_content_keys=True)
        row.finished_at = finished_at
        await self._session.flush()
        return row

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

    async def list_usage_records(
        self,
        *,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
        provider: str | None = None,
        model: str | None = None,
        owner_id: uuid.UUID | None = None,
        cohort_id: uuid.UUID | None = None,
        gateway_key_id: uuid.UUID | None = None,
        limit: int | None = None,
        ascending: bool = False,
    ) -> list[UsageLedger]:
        """List safe usage ledger records for reporting/export.

        This helper returns ORM rows but never commits or creates sessions. The
        schema has no prompt/completion body columns, so callers can project
        safe reporting fields without exposing request content.
        """
        statement: Select[tuple[UsageLedger]] = select(UsageLedger)
        if start_at is not None:
            statement = statement.where(UsageLedger.created_at >= start_at)
        if end_at is not None:
            statement = statement.where(UsageLedger.created_at <= end_at)
        if provider is not None:
            statement = statement.where(UsageLedger.provider == provider)
        if model is not None:
            statement = statement.where(
                or_(
                    UsageLedger.requested_model == model,
                    UsageLedger.resolved_model == model,
                )
            )
        if owner_id is not None:
            statement = statement.where(UsageLedger.owner_id == owner_id)
        if cohort_id is not None:
            statement = statement.where(UsageLedger.cohort_id == cohort_id)
        if gateway_key_id is not None:
            statement = statement.where(UsageLedger.gateway_key_id == gateway_key_id)

        ordering = UsageLedger.created_at.asc() if ascending else UsageLedger.created_at.desc()
        statement = statement.order_by(ordering)
        if limit is not None:
            statement = statement.limit(limit)

        result = await self._session.execute(statement)
        return list(result.scalars().all())

    async def list_usage_for_admin(
        self,
        *,
        provider: str | None = None,
        model: str | None = None,
        endpoint: str | None = None,
        status: str | None = None,
        gateway_key_id: uuid.UUID | None = None,
        owner_id: uuid.UUID | None = None,
        institution_id: uuid.UUID | None = None,
        cohort_id: uuid.UUID | None = None,
        request_id: str | None = None,
        streaming: bool | None = None,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[UsageLedger]:
        """Return usage rows with safe dashboard relationships loaded."""
        statement = _usage_admin_statement()
        statement = _apply_usage_admin_filters(
            statement,
            provider=provider,
            model=model,
            endpoint=endpoint,
            status=status,
            gateway_key_id=gateway_key_id,
            owner_id=owner_id,
            institution_id=institution_id,
            cohort_id=cohort_id,
            request_id=request_id,
            streaming=streaming,
            start_at=start_at,
            end_at=end_at,
        )
        statement = statement.order_by(UsageLedger.created_at.desc()).limit(limit).offset(offset)
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    async def get_usage_for_admin_detail(self, usage_ledger_id: uuid.UUID) -> UsageLedger | None:
        """Return one usage row with safe dashboard relationships loaded."""
        statement = _usage_admin_statement().where(UsageLedger.id == usage_ledger_id)
        result = await self._session.execute(statement)
        return result.scalar_one_or_none()

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


def _provider_completed_recovery_statement() -> Select[tuple[UsageLedger]]:
    return select(UsageLedger).where(
        UsageLedger.accounting_status == "failed",
        UsageLedger.response_metadata["needs_reconciliation"].as_boolean().is_(True),
        UsageLedger.response_metadata["recovery_state"].as_string()
        == "provider_completed_finalization_failed",
    )


def _usage_admin_statement() -> Select[tuple[UsageLedger]]:
    return select(UsageLedger).options(
        selectinload(UsageLedger.gateway_key),
        selectinload(UsageLedger.owner),
        selectinload(UsageLedger.institution),
        selectinload(UsageLedger.cohort),
    )


def _apply_usage_admin_filters(
    statement: Select[tuple[UsageLedger]],
    *,
    provider: str | None,
    model: str | None,
    endpoint: str | None,
    status: str | None,
    gateway_key_id: uuid.UUID | None,
    owner_id: uuid.UUID | None,
    institution_id: uuid.UUID | None,
    cohort_id: uuid.UUID | None,
    request_id: str | None,
    streaming: bool | None,
    start_at: datetime | None,
    end_at: datetime | None,
) -> Select[tuple[UsageLedger]]:
    if provider is not None:
        statement = statement.where(func.lower(UsageLedger.provider).like(f"%{provider.lower()}%"))
    if model is not None:
        normalized_model = f"%{model.lower()}%"
        statement = statement.where(
            or_(
                func.lower(UsageLedger.requested_model).like(normalized_model),
                func.lower(UsageLedger.resolved_model).like(normalized_model),
            )
        )
    if endpoint is not None:
        statement = statement.where(func.lower(UsageLedger.endpoint).like(f"%{endpoint.lower()}%"))
    if status is not None:
        statement = statement.where(UsageLedger.accounting_status == status)
    if gateway_key_id is not None:
        statement = statement.where(UsageLedger.gateway_key_id == gateway_key_id)
    if owner_id is not None:
        statement = statement.where(UsageLedger.owner_id == owner_id)
    if institution_id is not None:
        statement = statement.where(UsageLedger.institution_id == institution_id)
    if cohort_id is not None:
        statement = statement.where(UsageLedger.cohort_id == cohort_id)
    if request_id is not None:
        statement = statement.where(func.lower(UsageLedger.request_id).like(f"%{request_id.lower()}%"))
    if streaming is not None:
        statement = statement.where(UsageLedger.streaming.is_(streaming))
    if start_at is not None:
        statement = statement.where(UsageLedger.created_at >= start_at)
    if end_at is not None:
        statement = statement.where(UsageLedger.created_at <= end_at)
    return statement
