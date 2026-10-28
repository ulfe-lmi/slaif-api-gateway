"""Repository operations for HMAC-only Codex replay references."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Sequence

from sqlalchemy import (
    case,
    distinct,
    exists,
    func,
    select,
    tuple_,
    update,
)
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from slaif_gateway.db.models import CodexReplayReference, GatewayKey, ModelRoute, UsageLedger


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

    async def list_active_by_call_digests(
        self,
        *,
        gateway_key_id: uuid.UUID,
        call_digests: Sequence[tuple[str, str]],
        now: datetime,
    ) -> list[CodexReplayReference]:
        if not call_digests:
            return []
        result = await self._session.execute(
            select(CodexReplayReference).where(
                CodexReplayReference.gateway_key_id == gateway_key_id,
                CodexReplayReference.expires_at > now,
                tuple_(
                    CodexReplayReference.item_kind,
                    CodexReplayReference.call_id_hmac,
                ).in_(list(call_digests)),
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

    # --- additive administrative maintenance operations (objective 200) -----
    #
    # The runtime lookup/persistence methods above are unchanged; these
    # administrative queries are used only by the shared maintenance
    # service. Digests and row IDs are internal to selection and
    # fingerprints and are never returned as an export feature.

    @staticmethod
    def _scope_conditions(
        *,
        key_id: uuid.UUID | None,
        cohort_id: uuid.UUID | None,
        all_active: bool,
    ) -> list:
        conditions = []
        if key_id is not None:
            conditions.append(GatewayKey.id == key_id)
        elif cohort_id is not None:
            conditions.append(GatewayKey.cohort_id == cohort_id)
        elif all_active:
            conditions.append(GatewayKey.status == "active")
        return conditions

    @staticmethod
    def _time_conditions(
        created_from: datetime | None,
        created_until: datetime | None,
    ) -> list:
        conditions = []
        if created_from is not None:
            conditions.append(CodexReplayReference.created_at >= created_from)
        if created_until is not None:
            conditions.append(CodexReplayReference.created_at < created_until)
        return conditions

    async def list_maintenance_key_states(
        self,
        *,
        key_id: uuid.UUID | None = None,
        cohort_id: uuid.UUID | None = None,
        all_active: bool = False,
        limit: int,
    ) -> list[ReplayMaintenanceKeyState]:
        conditions = self._scope_conditions(
            key_id=key_id, cohort_id=cohort_id, all_active=all_active
        )
        statement = (
            select(
                GatewayKey.id,
                GatewayKey.status,
                GatewayKey.valid_from,
                GatewayKey.valid_until,
            )
            .where(*conditions)
            .order_by(GatewayKey.id)
            .limit(limit)
        )
        result = await self._session.execute(statement)
        return [ReplayMaintenanceKeyState(*row) for row in result.all()]

    async def lock_maintenance_keys(
        self, *, key_ids: list[uuid.UUID]
    ) -> list[ReplayMaintenanceKeyState]:
        if not key_ids:
            return []
        statement = (
            select(
                GatewayKey.id,
                GatewayKey.status,
                GatewayKey.valid_from,
                GatewayKey.valid_until,
            )
            .where(GatewayKey.id.in_(key_ids))
            .order_by(GatewayKey.id)
            .with_for_update()
        )
        result = await self._session.execute(statement)
        return [ReplayMaintenanceKeyState(*row) for row in result.all()]

    async def list_maintenance_rows(
        self,
        *,
        key_ids: list[uuid.UUID],
        created_from: datetime | None = None,
        created_until: datetime | None = None,
        limit: int | None = None,
        for_update: bool = False,
    ) -> list[ReplayMaintenanceRow]:
        if not key_ids:
            return []
        ledger_finalized = exists(
            select(UsageLedger.id)
            .where(
                UsageLedger.id == CodexReplayReference.usage_ledger_id,
                UsageLedger.gateway_key_id == CodexReplayReference.gateway_key_id,
                UsageLedger.request_id == CodexReplayReference.source_request_id,
                UsageLedger.success.is_(True),
                UsageLedger.accounting_status == "finalized",
            )
        ).label("ledger_finalized")
        statement = (
            select(
                CodexReplayReference.id,
                CodexReplayReference.gateway_key_id,
                CodexReplayReference.item_kind,
                CodexReplayReference.item_id_hmac,
                CodexReplayReference.usage_ledger_id,
                CodexReplayReference.hmac_key_version,
                CodexReplayReference.created_at,
                CodexReplayReference.expires_at,
                ledger_finalized,
            )
            .where(CodexReplayReference.gateway_key_id.in_(key_ids))
            .where(*self._time_conditions(created_from, created_until))
            .order_by(
                CodexReplayReference.gateway_key_id,
                CodexReplayReference.item_kind,
                CodexReplayReference.item_id_hmac,
            )
        )
        if limit is not None:
            statement = statement.limit(limit)
        if for_update:
            statement = statement.with_for_update()
        result = await self._session.execute(statement)
        return [ReplayMaintenanceRow(*row) for row in result.all()]

    async def list_maintenance_hmac_versions(
        self, *, key_ids: list[uuid.UUID]
    ) -> list[int]:
        if not key_ids:
            return []
        statement = (
            select(distinct(CodexReplayReference.hmac_key_version))
            .where(CodexReplayReference.gateway_key_id.in_(key_ids))
            .order_by(CodexReplayReference.hmac_key_version)
        )
        result = await self._session.execute(statement)
        return [int(value) for value in result.scalars().all()]

    async def inspect_reference_aggregates(
        self,
        *,
        key_ids: list[uuid.UUID],
        created_from: datetime | None,
        created_until: datetime | None,
        now: datetime,
    ) -> ReplayReferenceTotals:
        if not key_ids:
            return ReplayReferenceTotals(0, 0, None, None, None, None)
        conditions = self._time_conditions(created_from, created_until)
        active = case(
            (CodexReplayReference.expires_at > now, 1), else_=0
        )
        statement = (
            select(
                func.count(CodexReplayReference.id),
                func.sum(active),
                func.min(CodexReplayReference.created_at),
                func.max(CodexReplayReference.created_at),
                func.min(CodexReplayReference.expires_at),
                func.max(CodexReplayReference.expires_at),
            )
            .where(CodexReplayReference.gateway_key_id.in_(key_ids))
            .where(*conditions)
        )
        result = await self._session.execute(statement)
        row = result.one()
        return ReplayReferenceTotals(
            references=int(row[0] or 0),
            active_references=int(row[1] or 0),
            created_min=row[2],
            created_max=row[3],
            expiry_min=row[4],
            expiry_max=row[5],
        )

    async def inspect_reference_per_key(
        self,
        *,
        key_ids: list[uuid.UUID],
        created_from: datetime | None,
        created_until: datetime | None,
        now: datetime,
    ) -> list[tuple[uuid.UUID, int, int, datetime | None, datetime | None, datetime | None, datetime | None]]:
        if not key_ids:
            return []
        conditions = self._time_conditions(created_from, created_until)
        active = case((CodexReplayReference.expires_at > now, 1), else_=0)
        statement = (
            select(
                CodexReplayReference.gateway_key_id,
                func.count(CodexReplayReference.id),
                func.sum(active),
                func.min(CodexReplayReference.created_at),
                func.max(CodexReplayReference.created_at),
                func.min(CodexReplayReference.expires_at),
                func.max(CodexReplayReference.expires_at),
            )
            .where(CodexReplayReference.gateway_key_id.in_(key_ids))
            .where(*conditions)
            .group_by(CodexReplayReference.gateway_key_id)
            .order_by(CodexReplayReference.gateway_key_id)
        )
        result = await self._session.execute(statement)
        return [
            (
                row[0],
                int(row[1] or 0),
                int(row[2] or 0),
                row[3],
                row[4],
                row[5],
                row[6],
            )
            for row in result.all()
        ]

    async def inspect_reference_route_groups(
        self,
        *,
        key_ids: list[uuid.UUID],
        created_from: datetime | None,
        created_until: datetime | None,
        limit: int,
    ) -> tuple[
        list[tuple[uuid.UUID, str | None, int]], int
    ]:
        if not key_ids:
            return [], 0
        conditions = self._time_conditions(created_from, created_until)
        count = func.count(CodexReplayReference.id)
        statement = (
            select(
                ModelRoute.id,
                ModelRoute.requested_model,
                count,
            )
            .select_from(CodexReplayReference)
            .join(ModelRoute, ModelRoute.id == CodexReplayReference.route_id)
            .where(CodexReplayReference.gateway_key_id.in_(key_ids))
            .where(*conditions)
            .group_by(ModelRoute.id, ModelRoute.requested_model)
            .order_by(count.desc(), ModelRoute.id)
            .limit(limit)
        )
        result = await self._session.execute(statement)
        groups = [
            (row[0], row[1], int(row[2] or 0)) for row in result.all()
        ]
        total_statement = (
            select(func.count(distinct(CodexReplayReference.route_id)))
            .where(CodexReplayReference.gateway_key_id.in_(key_ids))
            .where(*conditions)
        )
        total = (await self._session.execute(total_statement)).scalar_one()
        return groups, int(total or 0)

    async def extend_reference_expiries(
        self, *, updates: list[tuple[uuid.UUID, datetime]]
    ) -> int:
        """Monotonic expiry extension ONLY (created_at untouched).

        The SQL guard refuses any shortening even though the caller has
        already verified the fresh locked state.
        """
        if not updates:
            return 0
        ordered = sorted(updates, key=lambda pair: (pair[0], pair[1]))
        updated = 0
        for start in range(0, len(ordered), _MAX_UPDATE_CHUNK):
            chunk = ordered[start : start + _MAX_UPDATE_CHUNK]
            mapping = {item_id: new_expiry for item_id, new_expiry in chunk}
            target = case(mapping, value=CodexReplayReference.id)
            statement = (
                update(CodexReplayReference)
                .where(CodexReplayReference.id.in_(list(mapping)))
                .where(CodexReplayReference.expires_at < target)
                .values(expires_at=target)
            )
            result = await self._session.execute(statement)
            updated += result.rowcount or 0
        return updated



@dataclass(frozen=True, slots=True)
class ReplayMaintenanceKeyState:
    """Safe key administration state for bounded maintenance selection."""

    id: uuid.UUID
    status: str
    valid_from: datetime
    valid_until: datetime


@dataclass(frozen=True, slots=True)
class ReplayMaintenanceRow:
    """Retained reference row state for maintenance (digests stay internal)."""

    id: uuid.UUID
    gateway_key_id: uuid.UUID
    item_kind: str
    item_id_hmac: str
    usage_ledger_id: uuid.UUID
    hmac_key_version: int
    created_at: datetime
    expires_at: datetime
    ledger_finalized: bool


@dataclass(frozen=True, slots=True)
class ReplayReferenceTotals:
    references: int
    active_references: int
    created_min: datetime | None
    created_max: datetime | None
    expiry_min: datetime | None
    expiry_max: datetime | None


# Bounded UPDATE chunk: id IN-list plus two CASE expansions (WHERE and SET)
# stay under the PostgreSQL 65,535 protocol parameter limit.
_MAX_UPDATE_CHUNK = 10_000
