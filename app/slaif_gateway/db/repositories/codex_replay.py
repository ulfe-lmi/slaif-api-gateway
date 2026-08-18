"""Repository operations for HMAC-only Codex replay references."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Sequence

from sqlalchemy import distinct, select, tuple_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from slaif_gateway.db.models import CodexReplayReference, UsageLedger


@dataclass(frozen=True, slots=True, repr=False)
class CodexReplayReferenceInsert:
    """Persistence-only safe metadata; digest values must never be logged."""

    id: uuid.UUID
    gateway_key_id: uuid.UUID
    usage_ledger_id: uuid.UUID
    source_request_id: str
    provider: str
    route_id: uuid.UUID
    upstream_model: str
    item_kind: str
    item_id_hmac: str
    call_id_hmac: str | None
    hmac_key_version: int
    tool_namespace: str | None
    tool_name: str | None
    created_at: datetime
    expires_at: datetime


class CodexReplayReferencesRepository:
    """Batch ownership lookup and idempotent persistence for replay metadata."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def usage_ledger_is_finalized_for_key(
        self,
        *,
        usage_ledger_id: uuid.UUID,
        gateway_key_id: uuid.UUID,
        source_request_id: str,
    ) -> bool:
        result = await self._session.execute(
            select(UsageLedger.id).where(
                UsageLedger.id == usage_ledger_id,
                UsageLedger.gateway_key_id == gateway_key_id,
                UsageLedger.request_id == source_request_id,
                UsageLedger.success.is_(True),
                UsageLedger.accounting_status == "finalized",
            )
        )
        return result.scalar_one_or_none() is not None

    async def list_active_hmac_versions_for_key(
        self,
        *,
        gateway_key_id: uuid.UUID,
        item_kinds: frozenset[str],
        now: datetime,
    ) -> list[int]:
        result = await self._session.execute(
            select(distinct(CodexReplayReference.hmac_key_version))
            .where(
                CodexReplayReference.gateway_key_id == gateway_key_id,
                CodexReplayReference.item_kind.in_(item_kinds),
                CodexReplayReference.expires_at > now,
            )
            .order_by(CodexReplayReference.hmac_key_version)
        )
        return [int(value) for value in result.scalars().all()]

    async def list_active_by_item_digests(
        self,
        *,
        gateway_key_id: uuid.UUID,
        item_digests: Sequence[tuple[str, str]],
        now: datetime,
    ) -> list[CodexReplayReference]:
        if not item_digests:
            return []
        result = await self._session.execute(
            select(CodexReplayReference).where(
                CodexReplayReference.gateway_key_id == gateway_key_id,
                CodexReplayReference.expires_at > now,
                tuple_(
                    CodexReplayReference.item_kind,
                    CodexReplayReference.item_id_hmac,
                ).in_(list(item_digests)),
            )
        )
        return list(result.scalars().all())

    async def upsert_many(
        self,
        records: Sequence[CodexReplayReferenceInsert],
    ) -> None:
        if not records:
            return
        values = [
            {
                "id": record.id,
                "gateway_key_id": record.gateway_key_id,
                "usage_ledger_id": record.usage_ledger_id,
                "source_request_id": record.source_request_id,
                "provider": record.provider,
                "route_id": record.route_id,
                "upstream_model": record.upstream_model,
                "item_kind": record.item_kind,
                "item_id_hmac": record.item_id_hmac,
                "call_id_hmac": record.call_id_hmac,
                "hmac_key_version": record.hmac_key_version,
                "tool_namespace": record.tool_namespace,
                "tool_name": record.tool_name,
                "created_at": record.created_at,
                "expires_at": record.expires_at,
            }
            for record in records
        ]
        statement = insert(CodexReplayReference).values(values)
        statement = statement.on_conflict_do_update(
            index_elements=[
                CodexReplayReference.gateway_key_id,
                CodexReplayReference.item_kind,
                CodexReplayReference.item_id_hmac,
            ],
            set_={
                "usage_ledger_id": statement.excluded.usage_ledger_id,
                "source_request_id": statement.excluded.source_request_id,
                "provider": statement.excluded.provider,
                "route_id": statement.excluded.route_id,
                "upstream_model": statement.excluded.upstream_model,
                "call_id_hmac": statement.excluded.call_id_hmac,
                "hmac_key_version": statement.excluded.hmac_key_version,
                "tool_namespace": statement.excluded.tool_namespace,
                "tool_name": statement.excluded.tool_name,
                "created_at": statement.excluded.created_at,
                "expires_at": statement.excluded.expires_at,
            },
        )
        await self._session.execute(statement)
