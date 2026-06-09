"""Repository helpers for provider-stored Conversation references."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from slaif_gateway.db.models import ConversationReference
from slaif_gateway.utils.sanitization import sanitize_metadata_mapping


class ConversationReferencesRepository:
    """Encapsulates ownership-safe access to conversation reference rows."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_conversation_reference(
        self,
        *,
        provider_conversation_id: str,
        gateway_key_id: uuid.UUID,
        provider: str,
        endpoint: str,
        owner_id: uuid.UUID | None = None,
        institution_id: uuid.UUID | None = None,
        cohort_id: uuid.UUID | None = None,
        route_id: uuid.UUID | None = None,
        provider_request_id: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> ConversationReference:
        row = ConversationReference(
            provider_conversation_id=provider_conversation_id,
            gateway_key_id=gateway_key_id,
            owner_id=owner_id,
            institution_id=institution_id,
            cohort_id=cohort_id,
            provider=provider,
            endpoint=endpoint,
            route_id=route_id,
            provider_request_id=provider_request_id,
            reference_metadata=sanitize_metadata_mapping(metadata, drop_content_keys=True),
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def get_active_reference_for_key(
        self,
        *,
        provider_conversation_id: str,
        gateway_key_id: uuid.UUID,
    ) -> ConversationReference | None:
        result = await self._session.execute(
            select(ConversationReference).where(
                ConversationReference.provider_conversation_id == provider_conversation_id,
                ConversationReference.gateway_key_id == gateway_key_id,
                ConversationReference.status == "active",
            ).limit(2)
        )
        rows = list(result.scalars())
        if len(rows) != 1:
            return None
        return rows[0]

    async def mark_deleted(
        self,
        reference: ConversationReference,
        *,
        deleted_at: datetime,
    ) -> ConversationReference:
        reference.status = "deleted"
        reference.deleted_at = deleted_at
        await self._session.flush()
        return reference
