"""Repository helpers for the demo-control fake-admin account tables.

Objective 220 foundation. All access targets the dedicated
``demo_control`` PostgreSQL schema (``fake_admin_accounts`` and
``fake_admin_account_events``) — never ``admin_users``/``admin_sessions``
or any business table. Every mutation is written inside the caller's
existing transaction: the account state change and its one safe
append-only event commit or roll back together, so a failed late event
write rolls back the account change as well.
"""

from __future__ import annotations

import uuid

from dataclasses import dataclass

from sqlalchemy import Select, select
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession

from slaif_gateway.db.models import FakeAdminAccount, FakeAdminAccountEvent

EVENT_ACTION_CREATED = "created"
EVENT_ACTION_ENABLED = "enabled"
EVENT_ACTION_DISABLED = "disabled"
EVENT_ACTION_PASSWORD_RESET = "password_reset"


@dataclass(frozen=True, slots=True)
class FakeAdminAccountFacts:
    """Worker-safe account projection: id + generation facts ONLY.

    Never contains username, password_hash, or timestamps. This is the
    only account view the demo web-control service and the worker role
    may use; credential-hash verification is a separate 224-b web-app
    concern under the web role's own column-scoped SELECT.
    """

    id: uuid.UUID
    is_enabled: bool
    credential_generation: int


@dataclass(frozen=True, slots=True)
class FakeAdminLoginCredential:
    """Column-scoped LOGIN projection for the 224-c demo web role.

    Exactly the columns of the web role's reviewed grant (id, username,
    password_hash, is_enabled, credential_generation). The login lookup
    NEVER loads the full ORM row: ``created_at``/``updated_at`` are not
    granted to the web role, so a row-level SELECT would 42501.
    """

    id: uuid.UUID
    username: str
    password_hash: str
    is_enabled: bool
    credential_generation: int


class FakeAdminAccountsRepository:
    """Encapsulates access for the demo-control fake-admin tables."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_account_facts(
        self, account_id: uuid.UUID, *, read_lock: bool = True
    ) -> FakeAdminAccountFacts | None:
        """Column-scoped read of the necessary account/generation facts.

        The SELECT names only (id, is_enabled, credential_generation), so
        it executes under BOTH the worker role's narrow column-level
        SELECT (which excludes username/password_hash) and the web role's
        grant.

        ``read_lock`` takes ``FOR SHARE`` ONLY when the caller's role
        holds UPDATE on at least one column of this table - the
        PostgreSQL 16 row-locking-privilege law. The demo web/worker
        roles hold column-SELECT ONLY here, so the demo control service
        always passes ``read_lock=False`` (plain MVCC SELECT); its
        credential fence is enforced statement-time inside the guarded
        worker transitions plus live rechecks on every session use. Only
        trusted full-privilege callers (the operator CLI path) may use
        the lock.
        """
        statement = select(
            FakeAdminAccount.id,
            FakeAdminAccount.is_enabled,
            FakeAdminAccount.credential_generation,
        ).where(FakeAdminAccount.id == account_id)
        if read_lock:
            statement = statement.with_for_update(read=True)
        result = await self._session.execute(statement)
        row = result.first()
        if row is None:
            return None
        return FakeAdminAccountFacts(
            id=row.id,
            is_enabled=row.is_enabled,
            credential_generation=row.credential_generation,
        )

    async def get_account_by_username(
        self, username: str, *, for_update: bool = False
    ) -> FakeAdminAccount | None:
        """Look up one account by exact (case-insensitive) username.

        ``for_update=True`` takes the row lock (``SELECT ... FOR UPDATE``)
        and refreshes already-loaded ORM instances, so concurrent CLI
        mutations serialize on the row.
        """
        statement = select(FakeAdminAccount).where(FakeAdminAccount.username == username)
        if for_update:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        result = await self._session.execute(statement)
        return result.scalar_one_or_none()

    async def get_login_credential(
        self, username: str
    ) -> FakeAdminLoginCredential | None:
        """Column-scoped login lookup for the demo web role (224-c).

        The SELECT names EXACTLY the web-granted columns (id, username,
        password_hash, is_enabled, credential_generation); it never
        loads the full ORM row (timestamps are not granted to the web
        role, and a full-row read would 42501 under it). Plain MVCC
        SELECT - no row lock: the web role cannot row-lock this table
        (column-SELECT only; the PostgreSQL 16 row-locking law).
        """
        statement = select(
            FakeAdminAccount.id,
            FakeAdminAccount.username,
            FakeAdminAccount.password_hash,
            FakeAdminAccount.is_enabled,
            FakeAdminAccount.credential_generation,
        ).where(FakeAdminAccount.username == username)
        result = await self._session.execute(statement)
        row = result.first()
        if row is None:
            return None
        return FakeAdminLoginCredential(
            id=row.id,
            username=row.username,
            password_hash=row.password_hash,
            is_enabled=row.is_enabled,
            credential_generation=row.credential_generation,
        )

    async def get_account_by_id(
        self, account_id: uuid.UUID, *, for_update: bool = False
    ) -> FakeAdminAccount | None:
        if for_update:
            statement = (
                select(FakeAdminAccount)
                .where(FakeAdminAccount.id == account_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            result = await self._session.execute(statement)
            return result.scalar_one_or_none()
        return await self._session.get(FakeAdminAccount, account_id)

    async def list_accounts(self, *, limit: int, offset: int = 0) -> list[FakeAdminAccount]:
        """Deterministic bounded listing (created_at, username order)."""
        statement: Select[tuple[FakeAdminAccount]] = (
            select(FakeAdminAccount)
            .order_by(FakeAdminAccount.created_at.desc(), FakeAdminAccount.username.asc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    async def count_active_accounts(self) -> int:
        """Count of currently enabled demo accounts.

        Disabling the last active account makes this return zero in the
        SAME transaction commit; the later demo login layer uses exactly
        this fact to 404.
        """
        # Database-side COUNT(*) scalar: exactly one integer is returned
        # to the caller regardless of account count (no unbounded result
        # materialization), with exact zero-after-last-disable semantics.
        result = await self._session.execute(
            select(func.count(FakeAdminAccount.id)).where(FakeAdminAccount.is_enabled.is_(True))
        )
        return int(result.scalar_one())

    async def _append_event(
        self,
        *,
        account_id: uuid.UUID,
        action: str,
        reason: str | None,
        credential_generation: int,
    ) -> FakeAdminAccountEvent:
        event = FakeAdminAccountEvent(
            account_id=account_id,
            action=action,
            reason=reason,
            credential_generation=credential_generation,
        )
        self._session.add(event)
        await self._session.flush()
        return event

    async def create_account(
        self, *, username: str, password_hash: str, reason: str | None
    ) -> FakeAdminAccount:
        """Insert one enabled account (generation 0) plus its 'created' event."""
        account = FakeAdminAccount(
            username=username,
            password_hash=password_hash,
            is_enabled=True,
            credential_generation=0,
        )
        self._session.add(account)
        await self._session.flush()
        await self._append_event(
            account_id=account.id,
            action=EVENT_ACTION_CREATED,
            reason=reason,
            credential_generation=0,
        )
        return account

    async def set_enabled(
        self, account: FakeAdminAccount, *, enabled: bool, reason: str | None
    ) -> bool:
        """Enable/disable the already-locked account.

        Returns True only when the state actually changed (event written,
        generation bumped). Repeating the same state is a defined
        idempotent no-op: no event, no generation change, no fake success
        audit.
        """
        if account.is_enabled == enabled:
            return False
        account.is_enabled = enabled
        account.credential_generation += 1
        await self._session.flush()
        await self._append_event(
            account_id=account.id,
            action=EVENT_ACTION_ENABLED if enabled else EVENT_ACTION_DISABLED,
            reason=reason,
            credential_generation=account.credential_generation,
        )
        return True

    async def reset_password(
        self, account: FakeAdminAccount, *, password_hash: str, reason: str | None
    ) -> None:
        """Replace the salted hash and bump the generation.

        NEVER changes ``is_enabled``: resetting a disabled account's
        password does not reenable it.
        """
        account.password_hash = password_hash
        account.credential_generation += 1
        await self._session.flush()
        await self._append_event(
            account_id=account.id,
            action=EVENT_ACTION_PASSWORD_RESET,
            reason=reason,
            credential_generation=account.credential_generation,
        )

    async def list_events(
        self, account_id: uuid.UUID, *, limit: int, offset: int = 0
    ) -> list[FakeAdminAccountEvent]:
        """Bounded newest-first event listing for one account."""
        statement: Select[tuple[FakeAdminAccountEvent]] = (
            select(FakeAdminAccountEvent)
            .where(FakeAdminAccountEvent.account_id == account_id)
            .order_by(FakeAdminAccountEvent.created_at.desc(), FakeAdminAccountEvent.id.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(statement)
        return list(result.scalars().all())
