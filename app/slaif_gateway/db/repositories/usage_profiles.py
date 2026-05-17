"""Repository helpers for safe usage_profiles table operations."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from slaif_gateway.db.models import UsageProfile
from slaif_gateway.utils.sanitization import sanitize_metadata_mapping


class UsageProfilesRepository:
    """Encapsulates CRUD-style access for safe usage profile rows."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_usage_profile(
        self,
        *,
        usage_ledger_id: uuid.UUID,
        gateway_key_id: uuid.UUID,
        endpoint_path: str,
        provider: str,
        input_tokens: int,
        output_tokens: int,
        total_tokens: int,
        owner_id: uuid.UUID | None = None,
        institution_id: uuid.UUID | None = None,
        cohort_id: uuid.UUID | None = None,
        requested_model: str | None = None,
        resolved_upstream_model: str | None = None,
        provider_host: str | None = None,
        provider_endpoint_path: str | None = None,
        reasoning_tokens: int | None = None,
        cached_tokens: int | None = None,
        tool_call_counts: dict[str, object] | None = None,
        function_tool_names: list[str] | None = None,
        provider_reported_cost: Decimal | None = None,
        slaif_calculated_cost: Decimal | None = None,
        cost_currency: str | None = None,
        cost_source: str = "unknown",
        gateway_request_id: str | None = None,
        profile_metadata: dict[str, object] | None = None,
        created_at: datetime | None = None,
    ) -> UsageProfile:
        row = UsageProfile(
            usage_ledger_id=usage_ledger_id,
            gateway_key_id=gateway_key_id,
            owner_id=owner_id,
            institution_id=institution_id,
            cohort_id=cohort_id,
            endpoint_path=endpoint_path,
            provider=provider,
            requested_model=requested_model,
            resolved_upstream_model=resolved_upstream_model,
            provider_host=provider_host,
            provider_endpoint_path=provider_endpoint_path,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            reasoning_tokens=reasoning_tokens,
            cached_tokens=cached_tokens,
            tool_call_counts=sanitize_metadata_mapping(tool_call_counts, drop_content_keys=True),
            function_tool_names=list(function_tool_names or []),
            provider_reported_cost=provider_reported_cost,
            slaif_calculated_cost=slaif_calculated_cost,
            cost_currency=cost_currency,
            cost_source=cost_source,
            gateway_request_id=gateway_request_id,
            profile_metadata=sanitize_metadata_mapping(profile_metadata, drop_content_keys=True),
        )
        if created_at is not None:
            row.created_at = created_at
        self._session.add(row)
        await self._session.flush()
        return row

    async def get_by_usage_ledger_id(self, usage_ledger_id: uuid.UUID) -> UsageProfile | None:
        result = await self._session.execute(
            select(UsageProfile).where(UsageProfile.usage_ledger_id == usage_ledger_id)
        )
        return result.scalar_one_or_none()

    async def list_for_gateway_key(
        self,
        gateway_key_id: uuid.UUID,
        *,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
        limit: int = 100,
    ) -> list[UsageProfile]:
        statement: Select[tuple[UsageProfile]] = select(UsageProfile).where(
            UsageProfile.gateway_key_id == gateway_key_id
        )
        if start_at is not None:
            statement = statement.where(UsageProfile.created_at >= start_at)
        if end_at is not None:
            statement = statement.where(UsageProfile.created_at <= end_at)
        statement = statement.order_by(UsageProfile.created_at.desc()).limit(limit)
        result = await self._session.execute(statement)
        return list(result.scalars().all())
