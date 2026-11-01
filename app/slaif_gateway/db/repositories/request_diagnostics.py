"""Repository helpers for the bounded request_diagnostics table.

All operations run inside a caller-owned short transaction.  The capacity
enforcement sequence (advisory lock, expiry prune, bounded eviction, insert)
is a small nonblocking transactional lock plus bounded eviction — no general
storage-slot or job framework.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from slaif_gateway.db.models import RequestDiagnostic
from slaif_gateway.schemas.request_diagnostics import (
    DiagnosticsNamespace,
    RequestDiagnosticRecord,
)

# Fixed transactional advisory-lock key for capacity enforcement.
_CAPACITY_LOCK_KEY = 201026
# Per-write eviction bound so one writer can never issue an unbounded sweep.
_MAX_EVICTION_PER_WRITE = 1000
# Per-operation prune bound: bounded expiry pruning on writes and via the
# explicit cleanup command (no unbounded sweep, no background daemon).
_MAX_PRUNE_PER_OPERATION = 1000


class RequestDiagnosticsRepository:
    """Encapsulates bounded CRUD-style access for RequestDiagnostic rows."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def try_acquire_capacity_lock(self) -> bool:
        """Bounded, nonblocking transactional capacity lock (no wait)."""
        result = await self._session.execute(
            text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": _CAPACITY_LOCK_KEY}
        )
        return bool(result.scalar_one())

    async def delete_expired(self, *, not_before: datetime) -> int:
        """Physically prune at most one bounded batch of expired rows."""
        ids = (
            select(RequestDiagnostic.id)
            .where(RequestDiagnostic.occurred_at < not_before)
            .order_by(RequestDiagnostic.occurred_at.asc(), RequestDiagnostic.id.asc())
            .limit(_MAX_PRUNE_PER_OPERATION)
        ).scalar_subquery()
        result = await self._session.execute(
            delete(RequestDiagnostic).where(RequestDiagnostic.id.in_(ids))
        )
        return result.rowcount or 0

    async def count_rows(self) -> int:
        result = await self._session.execute(select(func.count(RequestDiagnostic.id)))
        return int(result.scalar_one())

    async def gateway_id_exists(self, *, gateway_request_id: str) -> bool:
        """Bounded point lookup on the unique stable gateway diagnostic ID."""
        result = await self._session.execute(
            select(RequestDiagnostic.id)
            .where(RequestDiagnostic.gateway_request_id == gateway_request_id)
            .limit(1)
        )
        return result.first() is not None

    async def evict_oldest(self, *, count: int) -> int:
        """Physically remove at most ``count`` oldest rows (bounded)."""
        if count <= 0:
            return 0
        count = min(count, _MAX_EVICTION_PER_WRITE)
        rows = (
            (
                select(RequestDiagnostic.id)
                .order_by(RequestDiagnostic.occurred_at.asc(), RequestDiagnostic.id.asc())
                .limit(count)
            )
            .scalar_subquery()
        )
        result = await self._session.execute(
            delete(RequestDiagnostic).where(RequestDiagnostic.id.in_(rows))
        )
        return result.rowcount or 0

    async def insert_row(self, record: RequestDiagnosticRecord) -> None:
        row = RequestDiagnostic(
            id=record.id,
            gateway_request_id=record.gateway_request_id,
            client_request_id=record.client_request_id,
            client_id_unavailable_reason=record.client_id_unavailable_reason,
            method=record.method,
            endpoint_template=record.endpoint_template,
            occurred_at=record.occurred_at,
            http_status=record.http_status,
            stream_outcome=record.stream_outcome,
            source=record.source,
            reason_code=record.reason_code,
            error_code=record.error_code,
            error_param=record.error_param,
            positions=record.positions,
            counts=record.counts,
            limits=record.limits,
            gateway_key_id=record.gateway_key_id,
            route_id=record.route_id,
            route_pattern=record.route_pattern,
            deployment_revision=record.deployment_revision,
            estimated_input_tokens=record.estimated_input_tokens,
            output_allowance_tokens=record.output_allowance_tokens,
            context_window_tokens=record.context_window_tokens,
            replay_error_code=record.replay_error_code,
            recorded_at=record.recorded_at,
        )
        self._session.add(row)
        await self._session.flush()

    async def lookup_retained(
        self,
        *,
        lookup_id: str,
        namespace: DiagnosticsNamespace,
        not_before: datetime,
        limit: int,
    ) -> tuple[tuple[RequestDiagnosticRecord, ...], int]:
        """Bounded retained-row fetch plus an exact retained match count.

        One single-snapshot statement: at most ``limit`` rows are loaded
        (the service passes one row past the 100-candidate bound) together
        with a ``COUNT(*) OVER ()`` computed over the same retained
        predicate, so the row set and the count cannot disagree between
        separate statements and ambiguity/overflow is reported honestly
        without loading an unbounded result set.
        """
        if namespace is DiagnosticsNamespace.GATEWAY:
            conditions = [RequestDiagnostic.gateway_request_id == lookup_id]
        elif namespace is DiagnosticsNamespace.CLIENT:
            conditions = [RequestDiagnostic.client_request_id == lookup_id]
        else:
            conditions = [
                (RequestDiagnostic.gateway_request_id == lookup_id)
                | (RequestDiagnostic.client_request_id == lookup_id)
            ]
        retained = *conditions, RequestDiagnostic.occurred_at >= not_before
        total_column = func.count(RequestDiagnostic.id).over().label("retained_total")
        result = await self._session.execute(
            select(RequestDiagnostic, total_column)
            .where(*retained)
            .order_by(RequestDiagnostic.occurred_at.asc(), RequestDiagnostic.id.asc())
            .limit(max(1, int(limit)))
        )
        rows: list[RequestDiagnostic] = []
        total = 0
        for row, row_total in result.all():
            total = int(row_total)
            rows.append(row)
        return tuple(_row_to_record(row) for row in rows), total

    async def retained_summary(
        self, *, not_before: datetime
    ) -> tuple[int, datetime | None, datetime | None]:
        result = await self._session.execute(
            select(
                func.count(RequestDiagnostic.id),
                func.min(RequestDiagnostic.occurred_at),
                func.max(RequestDiagnostic.occurred_at),
            ).where(RequestDiagnostic.occurred_at >= not_before)
        )
        count, oldest, newest = result.one()
        return int(count), oldest, newest

    async def recent_retained_ids(
        self,
        *,
        namespace: DiagnosticsNamespace,
        not_before: datetime,
        query: str | None = None,
        limit: int,
    ) -> tuple[tuple[str, str, datetime], ...]:
        """Bounded newest-first retained ID choices (211-a GUI picker).

        The choice set follows the requested namespace: gateway-only,
        client-only (non-null client IDs), or both tagged by namespace
        for ``any``. An optional substring query is applied with escaped
        LIKE wildcards so a pasted value is data, not a pattern.
        DISTINCT IDs are grouped BEFORE the limit (newest ``recorded_at``
        per ID), so repeated client IDs cannot consume the candidate
        batch and hide older distinct choices; at most ``limit``
        distinct IDs per namespace are loaded, newest first.
        For ``any``, the merged gateway/client rows are de-duplicated by
        submitted ID (newest write time wins) BEFORE the final cap, so a
        value retained in both namespaces never hides an older distinct
        choice.
        """
        limit = max(1, int(limit))
        out: list[tuple[str, str, datetime]] = []
        for column, tag in _namespace_choice_columns(namespace):
            conditions = [RequestDiagnostic.occurred_at >= not_before]
            if column is RequestDiagnostic.client_request_id:
                conditions.append(RequestDiagnostic.client_request_id.is_not(None))
            if query:
                conditions.append(_escaped_ilike(column, query))
            newest = func.max(RequestDiagnostic.recorded_at)
            result = await self._session.execute(
                select(column.label("value"), newest.label("recorded"))
                .where(*conditions)
                .group_by(column)
                .order_by(newest.desc(), column.asc())
                .limit(limit)
            )
            out.extend((str(value), tag, when) for value, when in result.all())
        out.sort(key=lambda item: (item[2], item[1], item[0]), reverse=True)
        deduped: list[tuple[str, str, datetime]] = []
        seen: set[str] = set()
        for value, tag, when in out:
            if value in seen:
                continue
            seen.add(value)
            deduped.append((value, tag, when))
        return tuple(deduped[:limit])

    async def retained_choice_for(
        self,
        *,
        lookup_id: str,
        namespace: DiagnosticsNamespace,
        not_before: datetime,
    ) -> tuple[str, datetime] | None:
        """Bounded point read for one retained ID (picker hydration).

        Returns ``(namespace_tag, recorded_at)`` from ONE read so the
        namespace and its real write time travel together; ``None`` when
        no retained row matches under the requested namespace law (a
        vanished row is omitted, never re-timestamped).
        """
        for column, tag in _namespace_choice_columns(namespace):
            conditions = [
                column == lookup_id,
                RequestDiagnostic.occurred_at >= not_before,
            ]
            if column is RequestDiagnostic.client_request_id:
                conditions.append(RequestDiagnostic.client_request_id.is_not(None))
            result = await self._session.execute(
                select(column, RequestDiagnostic.recorded_at)
                .where(*conditions)
                .order_by(RequestDiagnostic.recorded_at.desc())
                .limit(1)
            )
            row = result.first()
            if row is not None:
                return tag, row[1]
        return None


def _namespace_choice_columns(
    namespace: DiagnosticsNamespace,
) -> tuple[tuple[object, str], ...]:
    if namespace is DiagnosticsNamespace.GATEWAY:
        return ((RequestDiagnostic.gateway_request_id, "gateway"),)
    if namespace is DiagnosticsNamespace.CLIENT:
        return ((RequestDiagnostic.client_request_id, "client"),)
    return (
        (RequestDiagnostic.gateway_request_id, "gateway"),
        (RequestDiagnostic.client_request_id, "client"),
    )


def _escaped_ilike(column: object, query: str) -> object:
    escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return column.ilike(f"%{escaped}%", escape="\\")


def _row_to_record(row: RequestDiagnostic) -> RequestDiagnosticRecord:
    positions: dict[str, int] | None = None
    if isinstance(row.positions, dict):
        positions = {
            str(key): int(value)
            for key, value in row.positions.items()
            if isinstance(value, int) and not isinstance(value, bool)
        }
        if not positions:
            positions = None
    counts: dict[str, int] | None = None
    if row.counts is not None:
        counts = {
            str(key): int(value)
            for key, value in row.counts.items()
            if isinstance(value, int) and not isinstance(value, bool)
        }
    limits: dict[str, int] | None = None
    if row.limits is not None:
        limits = {
            str(key): int(value)
            for key, value in row.limits.items()
            if isinstance(value, int) and not isinstance(value, bool)
        }
    return RequestDiagnosticRecord(
        id=row.id,
        gateway_request_id=row.gateway_request_id,
        client_request_id=row.client_request_id,
        client_id_unavailable_reason=row.client_id_unavailable_reason,
        method=row.method,
        endpoint_template=row.endpoint_template,
        occurred_at=row.occurred_at,
        http_status=row.http_status,
        stream_outcome=row.stream_outcome,
        source=row.source,
        reason_code=row.reason_code,
        error_code=row.error_code,
        error_param=row.error_param,
        positions=positions,
        counts=counts,
        limits=limits,
        gateway_key_id=row.gateway_key_id,
        route_id=row.route_id,
        route_pattern=row.route_pattern,
        deployment_revision=row.deployment_revision,
        estimated_input_tokens=row.estimated_input_tokens,
        output_allowance_tokens=row.output_allowance_tokens,
        context_window_tokens=row.context_window_tokens,
        replay_error_code=row.replay_error_code,
        recorded_at=row.recorded_at,
    )
