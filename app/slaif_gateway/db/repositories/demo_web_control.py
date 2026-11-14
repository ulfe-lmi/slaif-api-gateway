"""Repository helpers for the demo-control request/session tables.

Objective 224-a foundation. All access targets the dedicated
``demo_control`` PostgreSQL schema (``demo_snapshot_requests`` and
``demo_web_sessions``) - never ``admin_users``/``admin_sessions`` or any
business table.

Locking law (verified against the PostgreSQL 16 privilege docs,
https://www.postgresql.org/docs/16/ddl-priv.html, and a live PG16 probe):

- Row-locking reads (``FOR UPDATE``/``FOR NO KEY UPDATE``/``FOR SHARE``/
  ``FOR KEY SHARE``) require UPDATE privilege on at least ONE column of
  each locked table. The web role holds no UPDATE on
  ``demo_snapshot_requests`` at all and neither role holds any UPDATE on
  ``fake_admin_accounts`` (column-SELECT only), so those roles can take
  NO row lock on those tables: their reads are plain MVCC SELECTs. The
  worker role holds column-level UPDATE on
  ``demo_snapshot_requests`` and may take ``FOR SHARE`` there (never FOR
  UPDATE - it lacks UPDATE on the remaining request columns).
- Every state transition is an ATOMIC GUARDED UPDATE (compare-and-set):
  ``UPDATE ... WHERE id = :id AND state IN (:from_states)``. Exactly one
  concurrent transition can match; the loser affects 0 rows and refuses.
  A guarded UPDATE needs only the column-level UPDATE grants the role
  already holds, so the same code executes under the restricted web
  (session revocation) and worker (request transitions) roles.
- Because account facts cannot be row-locked by either role, the
  credential fence is enforced STATEMENT-TIME inside the guarded worker
  transitions (``account_gate``): the live account row must still be
  enabled with the request's recorded generation, evaluated in the same
  atomic statement, so a concurrent reset/disable makes the CAS match 0
  rows and a stale worker result can never transition the copy. Session
  issuance/validation recheck the live account on every use.
"""

from __future__ import annotations

import uuid

from sqlalchemy import Select, and_, exists, insert, or_, select, update
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession

from slaif_gateway.db.models import (
    DemoSnapshotRequest,
    DemoWebSession,
    FakeAdminAccount,
)


def _account_live_fence():
    """Statement-time credential fence for guarded worker transitions.

    True only while the LIVE account row bound to the request is still
    enabled and its ``credential_generation`` still equals the
    request's recorded fence. References ONLY the worker-granted account
    columns (id, is_enabled, credential_generation), so the guarded
    UPDATE executes under the worker role's column-level grants.
    """
    account = FakeAdminAccount
    return exists(
        select(account.id)
        .where(account.id == DemoSnapshotRequest.account_id)
        .where(account.is_enabled.is_(True))
        .where(account.credential_generation == DemoSnapshotRequest.credential_generation)
    )


class DemoWebControlRepository:
    """Encapsulates access for the demo-control request/session tables."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # --- demo_snapshot_requests ------------------------------------------------

    async def get_request(
        self, request_id: uuid.UUID, *, read_lock: bool = False
    ) -> DemoSnapshotRequest | None:
        """Fetch one request by exact UUID.

        ``read_lock=True`` takes ``SELECT ... FOR SHARE`` - legal only
        for a role holding UPDATE on at least one column of this table
        (the worker role; the row-locking privilege law). No service
        transition path uses it (a FOR SHARE pre-read plus the guarded
        UPDATE on the same row would deadlock under concurrency); it
        remains available for inspection-style reads.
        ``populate_existing`` is always applied: atomic guarded UPDATEs
        bypass the ORM session, so a later re-read must refresh, never
        return, a stale instance.
        """
        statement = select(DemoSnapshotRequest).where(DemoSnapshotRequest.id == request_id)
        if read_lock:
            statement = statement.with_for_update(read=True)
        statement = statement.execution_options(populate_existing=True)
        result = await self._session.execute(statement)
        return result.scalar_one_or_none()

    async def create_request(
        self,
        *,
        account_id: uuid.UUID,
        credential_generation: int,
        created_at: object,
        deadline_at: object,
        expires_at: object,
    ) -> DemoSnapshotRequest:
        """Insert one pending request under the web role's column law.

        Core INSERT naming ONLY the web-granted columns (id, account_id,
        credential_generation, created_at, deadline_at, expires_at). An
        ORM ``session.add`` is NOT used: the ORM would also name the
        never-set worker-owned columns as explicit NULLs, which the
        column-limited INSERT grant refuses. ``state`` is omitted so
        the DB server_default 'pending' applies (the web role cannot
        name that column); the row is then re-read with the granted
        SELECT to return the authoritative stored state.
        """
        request_id = uuid.uuid4()
        statement = insert(DemoSnapshotRequest).values(
            id=request_id,
            account_id=account_id,
            credential_generation=credential_generation,
            created_at=created_at,
            deadline_at=deadline_at,
            expires_at=expires_at,
        )
        await self._session.execute(statement)
        created = await self.get_request(request_id, read_lock=False)
        assert created is not None, "just-inserted request missing on re-read"
        return created

    async def count_requests(
        self, account_id: uuid.UUID, *, state: str | None = None
    ) -> int:
        """Database-side bounded count (one integer returned)."""
        statement = select(func.count(DemoSnapshotRequest.id)).where(
            DemoSnapshotRequest.account_id == account_id
        )
        if state is not None:
            statement = statement.where(DemoSnapshotRequest.state == state)
        result = await self._session.execute(statement)
        return int(result.scalar_one())

    async def cas_transition(
        self,
        request_id: uuid.UUID,
        *,
        to_state: str,
        from_states: tuple[str, ...],
        failure_code: str | None = None,
        claimed_at: object = None,
        verified_at: object = None,
        worker_job_id: str | None = None,
        worker_target_db: str | None = None,
        account_gate: bool = False,
    ) -> bool:
        """Atomic guarded state transition (compare-and-set).

        ``UPDATE demo_snapshot_requests SET state=... [ + worker-owned
        fields] WHERE id=:id AND state IN (:from_states) [AND the live
        account fence holds]``. Returns True only when EXACTLY this
        caller's transition matched (rowcount 1); concurrent transitions
        serialize on the row lock and the loser observes 0 rows. Only
        the granted worker columns are ever set.

        ``account_gate=True`` additionally requires, IN THE SAME atomic
        statement, that the live bound account is still enabled with the
        request's recorded credential generation - the statement-time
        form of the credential fence (row locks on the account table are
        impossible under the column-SELECT-only grants).
        """
        values: dict[str, object] = {"state": to_state}
        if failure_code is not None:
            values["failure_code"] = failure_code
        if claimed_at is not None:
            values["claimed_at"] = claimed_at
        if verified_at is not None:
            values["verified_at"] = verified_at
        if worker_job_id is not None:
            values["worker_job_id"] = worker_job_id
        if worker_target_db is not None:
            values["worker_target_db"] = worker_target_db
        statement = (
            update(DemoSnapshotRequest)
            .where(DemoSnapshotRequest.id == request_id)
            .where(DemoSnapshotRequest.state.in_(from_states))
            .values(**values)
        )
        if account_gate:
            statement = statement.where(_account_live_fence())
        result = await self._session.execute(statement)
        return result.rowcount == 1

    async def list_expired_for_reap(self, *, limit: int) -> list[DemoSnapshotRequest]:
        """Bounded recovery scan: rows that may have expired in place.

        Plain (lock-free) scan of pending rows past their claim deadline
        and claimed rows past their full lifetime, oldest first, at most
        ``limit`` rows. No row lock: the caller rechecks the state law
        and fails each row with an ATOMIC GUARDED transition, which is
        the single serialization point (a FOR SHARE scan followed by
        guarded UPDATEs on the same rows would deadlock under concurrent
        reaps).
        """
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        statement = (
            select(DemoSnapshotRequest)
            .where(
                or_(
                    and_(
                        DemoSnapshotRequest.state == "pending",
                        DemoSnapshotRequest.deadline_at <= now,
                    ),
                    and_(
                        DemoSnapshotRequest.state == "claimed",
                        DemoSnapshotRequest.expires_at <= now,
                    ),
                )
            )
            .order_by(DemoSnapshotRequest.created_at.asc())
            .limit(limit)
            .execution_options(populate_existing=True)
        )
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    # --- demo_web_sessions -------------------------------------------------------

    async def get_session_by_token_hash(
        self, token_hash: str, *, read_lock: bool = False
    ) -> DemoWebSession | None:
        """Look up one session by exact token hash.

        ``read_lock=True`` takes ``FOR SHARE`` (SELECT privilege only).
        ``populate_existing`` always refreshes stale instances, as with
        the request reads.
        """
        statement = select(DemoWebSession).where(DemoWebSession.token_hash == token_hash)
        if read_lock:
            statement = statement.with_for_update(read=True)
        statement = statement.execution_options(populate_existing=True)
        result = await self._session.execute(statement)
        return result.scalar_one_or_none()

    async def count_active_sessions_for_request(self, request_id: uuid.UUID) -> int:
        """Count of live (non-revoked) sessions bound to one request."""
        result = await self._session.execute(
            select(func.count(DemoWebSession.id))
            .where(DemoWebSession.request_id == request_id)
            .where(DemoWebSession.revoked_at.is_(None))
        )
        return int(result.scalar_one())

    async def create_session(
        self,
        *,
        token_hash: str,
        account_id: uuid.UUID,
        credential_generation: int,
        request_id: uuid.UUID,
        created_at: object,
        expires_at: object,
    ) -> DemoWebSession:
        """Insert one live session bound to exactly one verified request.

        Core INSERT naming ONLY the web-granted columns (id, token_hash,
        account_id, credential_generation, request_id, created_at,
        expires_at). An ORM ``session.add`` is NOT used: the ORM would
        also name the never-set ``revoked_at`` as an explicit NULL,
        which the column-limited INSERT grant refuses. ``revoked_at``
        stays NULL by database default; only the web role's later
        UPDATE(revoked_at) may write it.
        """
        session_id = uuid.uuid4()
        statement = insert(DemoWebSession).values(
            id=session_id,
            token_hash=token_hash,
            account_id=account_id,
            credential_generation=credential_generation,
            request_id=request_id,
            created_at=created_at,
            expires_at=expires_at,
        )
        await self._session.execute(statement)
        row = await self.get_session_by_token_hash(token_hash, read_lock=False)
        assert row is not None, "just-inserted session missing on re-read"
        return row

    async def cas_revoke_session(self, session_id: uuid.UUID, revoked_at: object) -> bool:
        """Atomic guarded revocation (compare-and-set on revoked_at NULL).

        Needs only the web role's column-level UPDATE(revoked_at) grant.
        Returns True only when this caller performed the revocation.
        """
        statement = (
            update(DemoWebSession)
            .where(DemoWebSession.id == session_id)
            .where(DemoWebSession.revoked_at.is_(None))
            .values(revoked_at=revoked_at)
        )
        result = await self._session.execute(statement)
        return result.rowcount == 1

    async def list_requests(
        self, account_id: uuid.UUID, *, limit: int, offset: int = 0
    ) -> list[DemoSnapshotRequest]:
        """Deterministic bounded newest-first listing for one account."""
        statement: Select[tuple[DemoSnapshotRequest]] = (
            select(DemoSnapshotRequest)
            .where(DemoSnapshotRequest.account_id == account_id)
            .order_by(DemoSnapshotRequest.created_at.desc(), DemoSnapshotRequest.id.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    async def flush(self) -> None:
        """Flush pending ORM inserts inside the caller's transaction."""
        await self._session.flush()
