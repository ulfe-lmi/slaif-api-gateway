"""Repository helpers for key template persistence."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from slaif_gateway.db.models import KeyTemplate, KeyTemplateRevision


class KeyTemplatesRepository:
    """Encapsulates key template and immutable revision persistence."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_template_record(
        self,
        *,
        name: str,
        description: str | None = None,
        created_by_admin_id: uuid.UUID | None = None,
        notes: str | None = None,
        status: str = "active",
    ) -> KeyTemplate:
        row = KeyTemplate(
            name=name,
            description=description,
            status=status,
            created_by_admin_id=created_by_admin_id,
            notes=notes,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def create_revision_record(
        self,
        *,
        template_id: uuid.UUID,
        revision_number: int,
        created_by_admin_id: uuid.UUID | None,
        source_type: str,
        source_calibration_gateway_key_id: uuid.UUID | None,
        source_time_window_start: datetime | None,
        source_time_window_end: datetime | None,
        source_multiplier: Decimal | None,
        allowed_endpoints: list[str],
        allowed_models: list[str],
        allowed_providers: list[str],
        allowed_hosted_capabilities: list[str],
        hosted_capabilities_requiring_review: list[str],
        request_limit_total: int,
        token_limit_total: int,
        input_token_limit_total: int | None = None,
        output_token_limit_total: int | None = None,
        reasoning_token_limit_total: int | None = None,
        cost_limit_eur: Decimal | None = None,
        max_input_tokens_per_request: int | None = None,
        max_output_tokens_per_request: int | None = None,
        max_total_tokens_per_request: int | None = None,
        max_single_request_cost_eur: Decimal | None = None,
        rate_limit_policy: dict[str, object] | None = None,
        validity_days_default: int | None = None,
        email_delivery_mode_default: str | None = None,
        template_snapshot: dict[str, object] | None = None,
        created_audit_log_id: uuid.UUID | None = None,
    ) -> KeyTemplateRevision:
        row = KeyTemplateRevision(
            template_id=template_id,
            revision_number=revision_number,
            created_by_admin_id=created_by_admin_id,
            source_type=source_type,
            source_calibration_gateway_key_id=source_calibration_gateway_key_id,
            source_time_window_start=source_time_window_start,
            source_time_window_end=source_time_window_end,
            source_multiplier=source_multiplier,
            allowed_endpoints=allowed_endpoints,
            allowed_models=allowed_models,
            allowed_providers=allowed_providers,
            allowed_hosted_capabilities=allowed_hosted_capabilities,
            hosted_capabilities_requiring_review=hosted_capabilities_requiring_review,
            request_limit_total=request_limit_total,
            token_limit_total=token_limit_total,
            input_token_limit_total=input_token_limit_total,
            output_token_limit_total=output_token_limit_total,
            reasoning_token_limit_total=reasoning_token_limit_total,
            cost_limit_eur=cost_limit_eur,
            max_input_tokens_per_request=max_input_tokens_per_request,
            max_output_tokens_per_request=max_output_tokens_per_request,
            max_total_tokens_per_request=max_total_tokens_per_request,
            max_single_request_cost_eur=max_single_request_cost_eur,
            rate_limit_policy=rate_limit_policy or {},
            validity_days_default=validity_days_default,
            email_delivery_mode_default=email_delivery_mode_default,
            template_snapshot=template_snapshot or {},
            created_audit_log_id=created_audit_log_id,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def set_current_revision(
        self,
        *,
        template_id: uuid.UUID,
        revision_id: uuid.UUID,
    ) -> KeyTemplate | None:
        row = await self._session.get(KeyTemplate, template_id)
        if row is None:
            return None
        row.current_revision_id = revision_id
        await self._session.flush()
        return row

    async def get_template_for_admin_detail(self, template_id: uuid.UUID) -> KeyTemplate | None:
        statement = (
            select(KeyTemplate)
            .options(selectinload(KeyTemplate.revisions))
            .where(KeyTemplate.id == template_id)
        )
        result = await self._session.execute(statement)
        return result.scalar_one_or_none()

    async def get_revision_for_admin_detail(
        self,
        revision_id: uuid.UUID,
    ) -> KeyTemplateRevision | None:
        statement = (
            select(KeyTemplateRevision)
            .options(selectinload(KeyTemplateRevision.template))
            .where(KeyTemplateRevision.id == revision_id)
        )
        result = await self._session.execute(statement)
        return result.scalar_one_or_none()

    async def list_templates_for_admin(
        self,
        *,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[KeyTemplate]:
        statement: Select[tuple[KeyTemplate]] = select(KeyTemplate).options(
            selectinload(KeyTemplate.revisions)
        )
        if status is not None:
            statement = statement.where(KeyTemplate.status == status)
        statement = statement.order_by(KeyTemplate.created_at.desc()).limit(limit).offset(offset)
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    async def list_revisions_for_template(self, template_id: uuid.UUID) -> list[KeyTemplateRevision]:
        statement = (
            select(KeyTemplateRevision)
            .where(KeyTemplateRevision.template_id == template_id)
            .order_by(KeyTemplateRevision.revision_number.desc())
        )
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    async def next_revision_number(self, template_id: uuid.UUID) -> int:
        statement = select(func.coalesce(func.max(KeyTemplateRevision.revision_number), 0)).where(
            KeyTemplateRevision.template_id == template_id
        )
        result = await self._session.execute(statement)
        return int(result.scalar_one()) + 1
