"""Repository helpers for provider-stored Responses references."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from slaif_gateway.db.models import ResponseReference
from slaif_gateway.utils.sanitization import sanitize_metadata_mapping


class ResponseReferencesRepository:
    """Encapsulates ownership-safe access to response reference rows."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_response_reference(
        self,
        *,
        provider_response_id: str,
        gateway_key_id: uuid.UUID,
        provider: str,
        endpoint: str,
        owner_id: uuid.UUID | None = None,
        institution_id: uuid.UUID | None = None,
        cohort_id: uuid.UUID | None = None,
        requested_model: str | None = None,
        upstream_model: str | None = None,
        route_id: uuid.UUID | None = None,
        provider_request_id: str | None = None,
        expires_at: datetime | None = None,
        metadata: dict[str, object] | None = None,
    ) -> ResponseReference:
        row = ResponseReference(
            provider_response_id=provider_response_id,
            gateway_key_id=gateway_key_id,
            owner_id=owner_id,
            institution_id=institution_id,
            cohort_id=cohort_id,
            provider=provider,
            requested_model=requested_model,
            upstream_model=upstream_model,
            endpoint=endpoint,
            route_id=route_id,
            provider_request_id=provider_request_id,
            expires_at=expires_at,
            reference_metadata=sanitize_metadata_mapping(metadata, drop_content_keys=True),
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def get_active_reference_for_key(
        self,
        *,
        provider_response_id: str,
        gateway_key_id: uuid.UUID,
    ) -> ResponseReference | None:
        result = await self._session.execute(
            select(ResponseReference).where(
                ResponseReference.provider_response_id == provider_response_id,
                ResponseReference.gateway_key_id == gateway_key_id,
                ResponseReference.status == "active",
            ).limit(2)
        )
        rows = list(result.scalars())
        if len(rows) != 1:
            return None
        return rows[0]

    async def mark_deleted(
        self,
        reference: ResponseReference,
        *,
        deleted_at: datetime,
    ) -> ResponseReference:
        reference.status = "deleted"
        reference.deleted_at = deleted_at
        await self._session.flush()
        return reference
