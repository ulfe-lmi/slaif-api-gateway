"""Objective 224-a: durable least-privilege demo control handoff.

Transactional state machine for ONE fresh, disposable, identity-masked
snapshot per successful demo login. PostgreSQL-authoritative control
metadata only (``demo_control.demo_snapshot_requests`` and
``demo_control.demo_web_sessions``); no in-memory-only session truth and
no ambient Redis dependence.

Role contracts (enforced by reviewed column/table grants applied in
224-b; the service enforces per-session ownership and the state law):

- **web control** role: may verify the fake-admin credential hash (a
  column-scoped SELECT on ``fake_admin_accounts``), create its OWN demo
  request rows (column-limited INSERT; the ``state`` column cannot be
  named - the DB default 'pending' applies) and read them, and
  create/revoke its own sessions (INSERT; UPDATE(revoked_at) only). It
  has NO UPDATE grant on ``demo_snapshot_requests`` at all: it can never
  move a request out of pending and can never mark a copy verified. It
  may NOT update fake-admin accounts/events, may NOT read source
  business tables, and may NOT acquire worker source/target credentials.
- **privileged snapshot worker** control role: may claim/complete demo
  requests (column-level UPDATE of the worker-owned columns only), read
  ONLY the necessary account/generation facts via a column-scoped
  SELECT (never username or password_hash), and observe session
  revocation facts (id, request_id, expires_at, revoked_at) via a
  column-limited SELECT (never token_hash/account/generation; it never
  writes session rows). Its source-export role remains a separate
  SELECT-only public-schema role.

Locking law (PostgreSQL 16 privilege docs, verified live on PG16):
every row-locking read (``FOR UPDATE``/``FOR NO KEY UPDATE``/``FOR
SHARE``/``FOR KEY SHARE``) requires UPDATE privilege on at least one
column of the locked table. Neither restricted role holds any UPDATE on
``fake_admin_accounts`` (column-SELECT only) and the web role holds no
UPDATE on the request table at all, so account facts are ALWAYS read
with plain MVCC SELECTs and the web role reads request rows plain as
well. The worker role (column UPDATE on the request table) CAN take
FOR SHARE on request rows, but the service takes NO row locks at all:
a FOR SHARE pre-read followed by the guarded UPDATE on the same row in
one transaction deadlocks under concurrent claimers. Every state
transition is therefore an ATOMIC GUARDED UPDATE (compare-and-set on
the current state), which is the single serialization point, so
concurrent transitions serialize on the row and exactly one wins -
this is what makes the claim exactly-once under the column-level
grants. The credential fence additionally rides STATEMENT-TIME inside
the guarded claim/handoff CAS (the live account must still be enabled
with the recorded generation in the same atomic statement), because
the account table cannot be row-locked by either role; session
issuance/validation recheck the live account on every use.

State law for a request (finite reviewed vocabulary):

    pending -> claimed -> verified_unpublished -> cleanup_pending
                                                         -> cleaned
    pending/claimed -> failed (safe finite failure code)
    verified_unpublished/failed -> cleanup_pending

A verified handoff is recorded only when the exact worker-held
manifest/copy binding (closed grammars, the exact verified 223 manifest
state), the LIVE account fence (enabled + recorded generation,
rechecked live and enforced statement-time in the atomic CAS), the copy
lifetime, and the database
copy-uniqueness invariants all agree. Late completions and
stale/duplicate/replayed claims are refused. A crash or restart leaves
an inspectable finite state and permits bounded recovery
(``reap_expired``); nothing is ever silently published.
"""

from __future__ import annotations

import hashlib
import re
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from slaif_gateway.db.models import DemoSnapshotRequest, DemoWebSession
from slaif_gateway.db.repositories.demo_web_control import DemoWebControlRepository
from slaif_gateway.db.repositories.fake_admin_accounts import (
    FakeAdminAccountFacts,
    FakeAdminAccountsRepository,
)

# --- finite reviewed vocabularies ------------------------------------------------

REQUEST_STATE_PENDING = "pending"
REQUEST_STATE_CLAIMED = "claimed"
REQUEST_STATE_VERIFIED_UNPUBLISHED = "verified_unpublished"
REQUEST_STATE_FAILED = "failed"
REQUEST_STATE_CLEANUP_PENDING = "cleanup_pending"
REQUEST_STATE_CLEANED = "cleaned"

REQUEST_STATES = (
    REQUEST_STATE_PENDING,
    REQUEST_STATE_CLAIMED,
    REQUEST_STATE_VERIFIED_UNPUBLISHED,
    REQUEST_STATE_FAILED,
    REQUEST_STATE_CLEANUP_PENDING,
    REQUEST_STATE_CLEANED,
)

FAILURE_CLAIM_EXPIRED = "claim_expired"
FAILURE_LATE_COMPLETION = "late_completion"
FAILURE_WORKER_FAILED = "worker_failed"
FAILURE_VERIFICATION_FAILED = "verification_failed"
FAILURE_COPY_MISMATCH = "copy_mismatch"
FAILURE_STATE_CONFLICT = "state_conflict"
FAILURE_INTERNAL_ERROR = "internal_error"

REQUEST_FAILURE_CODES = (
    FAILURE_CLAIM_EXPIRED,
    FAILURE_LATE_COMPLETION,
    FAILURE_WORKER_FAILED,
    FAILURE_VERIFICATION_FAILED,
    FAILURE_COPY_MISMATCH,
    FAILURE_STATE_CONFLICT,
    FAILURE_INTERNAL_ERROR,
)

# The worker-only failure codes the generic failure path may accept.
WORKER_FAILURE_CODES = (FAILURE_WORKER_FAILED, FAILURE_INTERNAL_ERROR)

# The ONLY accepted verified 223 manifest state for a handoff: the 222 DB
# state AND the 223 file-backed verification both passed (still
# unpublished). Any other state string is refused. The constant is
# imported LAZILY inside ``record_verified_handoff`` (the worker-only
# path) so that importing this control service - and therefore the 224-c
# demo web app, which never calls that method - does not pull the
# privileged 221/222/223 snapshot worker module chain into the web
# process (224-c web-path isolation).

# --- bounded lifetimes -------------------------------------------------------------

#: Bounded worker claim lease for a pending request.
CLAIM_LEASE = timedelta(minutes=15)
#: Full lifetime of one disposable snapshot (creation to expiry).
REQUEST_TTL = timedelta(minutes=60)

# --- closed identity grammars (221 manifest law) -----------------------------------

_WORKER_JOB_ID_RE = re.compile(r"snap-[0-9a-f]{32}")
_WORKER_TARGET_DB_RE = re.compile(r"demo_snap_[0-9a-f]{20}")

_TOKEN_BYTES = 32

# Closed PostgreSQL identifier law for the role names interpolated into
# the reviewed grant matrix (224-b applies these after the roles exist).
_ROLE_NAME_RE = re.compile(r"[a-z_][a-z0-9_]{0,62}")


class DemoWebControlError(Exception):
    """Safe fixed-vocabulary error for the demo web-control path.

    ``safe_message`` names only the failing FLAG/FIELD, never the
    supplied value (token, job id, target db, password, DSN).
    """

    def __init__(self, code: str, safe_message: str) -> None:
        super().__init__(safe_message)
        self.code = code
        self.safe_message = safe_message


# --- safe projections (no secrets, ever) --------------------------------------------


@dataclass(frozen=True, slots=True)
class DemoSnapshotRequestProjection:
    """Safe request fields for public-facing output.

    ``to_safe_dict`` NEVER emits the private copy locators
    (``worker_job_id`` / ``worker_target_db``): they are worker-owned
    custody references that the web role may not see. They remain on the
    internal dataclass only so the worker control path can bind them.
    """

    id: uuid.UUID
    account_id: uuid.UUID
    credential_generation: int
    state: str
    failure_code: str | None
    worker_job_id: str | None
    worker_target_db: str | None
    created_at: object
    deadline_at: object
    expires_at: object

    def to_safe_dict(self) -> dict[str, object]:
        return {
            "id": str(self.id),
            "account_id": str(self.account_id),
            "credential_generation": self.credential_generation,
            "state": self.state,
            "failure_code": self.failure_code,
            "created_at": self._iso(self.created_at),
            "deadline_at": self._iso(self.deadline_at),
            "expires_at": self._iso(self.expires_at),
        }

    @staticmethod
    def _iso(value: object) -> object:
        return value.isoformat() if hasattr(value, "isoformat") else value


@dataclass(frozen=True, slots=True)
class DemoWebSessionProjection:
    """Safe session fields; NEVER contains the raw token or its hash."""

    id: uuid.UUID
    account_id: uuid.UUID
    credential_generation: int
    request_id: uuid.UUID
    created_at: object
    expires_at: object
    revoked_at: object | None

    def to_safe_dict(self) -> dict[str, object]:
        return {
            "id": str(self.id),
            "account_id": str(self.account_id),
            "credential_generation": self.credential_generation,
            "request_id": str(self.request_id),
            "created_at": self.created_at.isoformat()
            if hasattr(self.created_at, "isoformat")
            else self.created_at,
            "expires_at": self.expires_at.isoformat()
            if hasattr(self.expires_at, "isoformat")
            else self.expires_at,
            "revoked_at": (
                self.revoked_at.isoformat()
                if hasattr(self.revoked_at, "isoformat")
                else self.revoked_at
            ),
        }


@dataclass(frozen=True, slots=True)
class DemoSessionIssuedResult:
    """A freshly issued session: the raw opaque token EXACTLY ONCE.

    The raw token is returned here and never persisted, logged, echoed,
    or repeated in any projection.
    """

    token: str
    session: DemoWebSessionProjection


@dataclass(frozen=True, slots=True)
class VerifiedCopyBinding:
    """The worker-held verified manifest/copy fields, passed by value.

    The privileged worker process parses these from its OWN verified
    private 221/223 custody (manifest + the 222/223 independent
    verifiers) and passes them here; the control plane cannot and does
    not read worker-private custody. The control plane's job is to bind
    them EXACTLY: closed grammar for both identities, the exact verified
    manifest state string, the live account fence rechecked under FOR
    SHARE, the copy lifetime, and the database copy-uniqueness
    invariants (two requests can never bind one job or one copy). A raw
    caller-supplied state string with no structured binding is never
    accepted.
    """

    worker_job_id: str
    worker_target_db: str
    manifest_state: str


# --- token law ------------------------------------------------------------------------


def generate_opaque_token() -> str:
    """Cryptographically random opaque browser token (256 bits, url-safe)."""
    return secrets.token_urlsafe(_TOKEN_BYTES)


def hash_opaque_token(token: str) -> str:
    """SHA-256 hex digest (64 lowercase hex) - the ONLY stored form."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _pg_constraint_name(exc: IntegrityError) -> str | None:
    """Constraint name for a driver IntegrityError (asyncpg adapter shape).

    The SQLAlchemy asyncpg dialect wraps the native asyncpg exception
    as ``__cause__`` of the adapter error (``exc.orig``); the
    ``constraint_name`` attribute lives on the NATIVE asyncpg error,
    not on the adapter error. Walk the cause chain (bounded) and return
    the first non-empty constraint name.
    """
    error: BaseException | None = exc.orig
    for _ in range(4):
        if error is None:
            return None
        name = getattr(error, "constraint_name", None)
        if isinstance(name, str) and name:
            return name
        error = error.__cause__
    return None


def _require_known_state(state: object) -> None:
    """Refuse a stored state outside the finite reviewed vocabulary."""
    if not isinstance(state, str) or state not in REQUEST_STATES:
        raise DemoWebControlError(
            "web_unknown_state",
            "The demo snapshot request is in an unrecognized state; it was "
            "left untouched for operator inspection.",
        )


def _validate_worker_job_id(worker_job_id: str) -> None:
    if not isinstance(worker_job_id, str) or _WORKER_JOB_ID_RE.fullmatch(worker_job_id) is None:
        raise DemoWebControlError(
            "web_invalid_job_identity",
            "The worker job identity does not match the closed snapshot "
            "job-id grammar.",
        )


def _validate_worker_target_db(worker_target_db: str) -> None:
    if (
        not isinstance(worker_target_db, str)
        or _WORKER_TARGET_DB_RE.fullmatch(worker_target_db) is None
    ):
        raise DemoWebControlError(
            "web_invalid_target_identity",
            "The copy locator does not match the closed target-database "
            "name grammar.",
        )


def _validate_role_name(role: object) -> None:
    """Refuse any role name outside the closed identifier law (no echo)."""
    if not isinstance(role, str) or _ROLE_NAME_RE.fullmatch(role) is None:
        raise DemoWebControlError(
            "web_role_name_invalid",
            "The role name does not match the closed PostgreSQL "
            "identifier law.",
        )


# --- reviewed role grant matrix (applied in 224-b after the roles exist) --------------


def web_role_grant_sql(role: str) -> tuple[str, ...]:
    """Exact reviewed grants for the future demo WEB control role.

    Web may read the fake-admin credential hash (login, 224-b) via a
    column-scoped SELECT, create its own request rows via a
    COLUMN-LIMITED INSERT (``state`` cannot be named - the DB default
    'pending' applies; the worker-owned columns are excluded), read
    requests, and create/revoke its own sessions (INSERT;
    UPDATE(revoked_at) only). It has NO UPDATE grant on
    ``demo_snapshot_requests`` at all, so it can never move a request
    out of pending and can never mark a copy verified. Copy cleanup
    after session revocation is performed by the worker role's bounded
    cleanup path (224-b), which observes the revoked sessions and
    request expiries. Web may never write fake-admin accounts/events
    and receives NO grant on any business table.
    """
    _validate_role_name(role)
    return (
        f"GRANT USAGE ON SCHEMA demo_control TO {role}",
        # Column-scoped: the web login (224-b) verifies the credential
        # hash by username; the control service itself uses only the
        # facts columns. Timestamps are not granted.
        "GRANT SELECT (id, username, password_hash, is_enabled, "
        f"credential_generation) ON demo_control.fake_admin_accounts TO {role}",
        f"GRANT SELECT ON demo_control.demo_snapshot_requests TO {role}",
        "GRANT INSERT (id, account_id, credential_generation, created_at, "
        f"deadline_at, expires_at) ON demo_control.demo_snapshot_requests TO {role}",
        f"GRANT SELECT ON demo_control.demo_web_sessions TO {role}",
        "GRANT INSERT (id, token_hash, account_id, credential_generation, "
        f"request_id, created_at, expires_at) ON demo_control.demo_web_sessions TO {role}",
        f"GRANT UPDATE (revoked_at) ON demo_control.demo_web_sessions TO {role}",
    )


def worker_role_grant_sql(role: str) -> tuple[str, ...]:
    """Exact reviewed grants for the future privileged snapshot WORKER control role.

    Worker may read ONLY the necessary account/generation facts via a
    column-scoped SELECT (never username or password_hash), move
    requests through the worker-owned states via column-level UPDATE
    (claim/verify/fail, exact copy identities, verified_at, and the
    cleanup tail cleanup_pending/cleaned after session revocation), and
    observe session revocation FACTS (id, request_id, expires_at,
    revoked_at) via a column-limited SELECT - it never sees
    ``token_hash``, ``account_id``, or ``credential_generation`` on
    session rows, and it never writes session rows. It may NOT create
    or insert request or session rows and receives NO grant on any
    business table. Its source-export role is a separate SELECT-only
    public-schema role (221 law, unchanged).
    """
    _validate_role_name(role)
    return (
        f"GRANT USAGE ON SCHEMA demo_control TO {role}",
        # Facts ONLY: the worker never sees username or password_hash -
        # the necessary account/generation facts are the only columns
        # granted, matching the order's worker role contract.
        "GRANT SELECT (id, is_enabled, credential_generation) "
        f"ON demo_control.fake_admin_accounts TO {role}",
        f"GRANT SELECT ON demo_control.demo_snapshot_requests TO {role}",
        "GRANT UPDATE (state, failure_code, claimed_at, worker_job_id, "
        f"worker_target_db, verified_at) ON demo_control.demo_snapshot_requests TO {role}",
        # Session revocation FACTS only: the cleanup path counts live
        # sessions per request (request_id + revoked_at). token_hash,
        # account_id and credential_generation are never granted to the
        # worker.
        "GRANT SELECT (id, request_id, expires_at, revoked_at) "
        f"ON demo_control.demo_web_sessions TO {role}",
    )


# --- service ------------------------------------------------------------------------


class DemoWebControlService:
    """One-transaction demo control state machine.

    The caller owns the transaction (each public method = one unit of
    work). ALL reads in this service are plain MVCC SELECTs - no row
    locks at all (row-locking reads require UPDATE on at least one
    column of the locked table, which the restricted roles cannot use
    for the account table at all, and a FOR SHARE pre-read plus guarded
    UPDATE on the same row would deadlock under concurrency). Every
    state transition is an atomic guarded UPDATE (compare-and-set), the
    single serialization point, so the same service executes under the
    restricted web role (session revocation, request/session creation)
    and the worker role (request transitions) - no FOR UPDATE anywhere,
    matching the column-level grants. A failed late write rolls back
    the whole unit of work.

    ``requests_repository`` / ``accounts_repository`` may be injected for
    database-independent unit tests; production passes the session-built
    repositories.
    """

    def __init__(
        self,
        session: AsyncSession,
        *,
        requests_repository: DemoWebControlRepository | None = None,
        accounts_repository: FakeAdminAccountsRepository | None = None,
    ) -> None:
        self._requests = requests_repository or DemoWebControlRepository(session)
        self._accounts = accounts_repository or FakeAdminAccountsRepository(session)

    # -- loads / projections -------------------------------------------------------

    @staticmethod
    def _project_request(request: DemoSnapshotRequest) -> DemoSnapshotRequestProjection:
        return DemoSnapshotRequestProjection(
            id=request.id,
            account_id=request.account_id,
            credential_generation=int(request.credential_generation),
            state=request.state,
            failure_code=request.failure_code,
            worker_job_id=request.worker_job_id,
            worker_target_db=request.worker_target_db,
            created_at=request.created_at,
            deadline_at=request.deadline_at,
            expires_at=request.expires_at,
        )

    @staticmethod
    def _project_session(session_row: DemoWebSession) -> DemoWebSessionProjection:
        return DemoWebSessionProjection(
            id=session_row.id,
            account_id=session_row.account_id,
            credential_generation=int(session_row.credential_generation),
            request_id=session_row.request_id,
            created_at=session_row.created_at,
            expires_at=session_row.expires_at,
            revoked_at=session_row.revoked_at,
        )

    async def _load_request(
        self, request_id: uuid.UUID, *, read_lock: bool = False
    ) -> DemoSnapshotRequest:
        """Request read + known-state gate.

        Plain MVCC SELECT by default. The service takes NO row locks on
        request rows: every transition pre-read is a fast path and the
        ATOMIC GUARDED UPDATE is the single serialization point. A
        ``FOR SHARE`` pre-read followed by the guarded UPDATE on the
        same row in one transaction would deadlock under concurrent
        claimers (verified live on PG16), and the web role cannot row-
        lock here at all (no UPDATE grant). ``read_lock=True`` remains
        available for the worker role (which legally may FOR SHARE this
        table) but no service path uses it.
        """
        request = await self._requests.get_request(request_id, read_lock=read_lock)
        if request is None:
            raise DemoWebControlError(
                "web_request_not_found",
                "No demo snapshot request exists for the supplied identity.",
            )
        _require_known_state(request.state)
        return request

    async def _load_account(self, account_id: uuid.UUID) -> FakeAdminAccountFacts:
        # Facts-only column-scoped read (id, is_enabled,
        # credential_generation): the ONLY account view the control
        # service uses, so it executes under both the web role's and the
        # worker role's narrow grants (the worker never sees username or
        # password_hash).
        #
        # Plain MVCC SELECT, no row lock: per the PostgreSQL 16
        # privilege law, every row-locking read (FOR UPDATE/FOR SHARE/
        # ...) requires UPDATE privilege on at least one column of the
        # locked table, which NEITHER demo role holds on
        # fake_admin_accounts (column-SELECT only). The credential fence
        # is therefore enforced (a) STATEMENT-TIME inside the guarded
        # worker transitions (account_gate) and (b) by the live
        # rechecks in create/validate session on every use, so a
        # concurrent operator reset/disable still prevents any usable
        # session.
        account = await self._accounts.get_account_facts(account_id, read_lock=False)
        if account is None:
            raise DemoWebControlError(
                "web_account_not_found",
                "No demo account exists for the supplied identity.",
            )
        return account

    async def _cas_or_conflict(
        self,
        request_id: uuid.UUID,
        *,
        error_code: str,
        safe_message: str,
        **cas_kwargs: object,
    ) -> DemoSnapshotRequest:
        """Run an atomic guarded transition; on 0 rows re-read and refuse."""
        ok = await self._requests.cas_transition(request_id, **cas_kwargs)  # type: ignore[arg-type]
        if not ok:
            # The committed state already moved (concurrent transition).
            # Re-read it (known-state gate) and refuse with the finite
            # safe code.
            await self._load_request(request_id, read_lock=False)
            raise DemoWebControlError(error_code, safe_message)
        return await self._load_request(request_id, read_lock=False)

    # -- web role operations -----------------------------------------------------

    async def create_request(
        self, *, account_id: uuid.UUID
    ) -> DemoSnapshotRequestProjection:
        """Create one fresh pending snapshot request for an enabled account.

        Gates (all in this transaction, on the live account facts read):
        account exists, account enabled, database-side active
        account count nonzero. Binds the LIVE credential generation. A
        new UUID and new bounded deadline/expiry per call: two logins
        always get distinct requests (and later distinct copies). The
        INSERT names only the web-granted columns; the state column is
        set by the DB default, never by this role.
        """
        account = await self._load_account(account_id)
        if not account.is_enabled:
            raise DemoWebControlError(
                "web_account_disabled",
                "The demo account is disabled.",
            )
        active = await self._accounts.count_active_accounts()
        if active <= 0:
            raise DemoWebControlError(
                "web_no_active_accounts",
                "No enabled demo account exists; demo login is unavailable.",
            )
        now = _utcnow()
        request = await self._requests.create_request(
            account_id=account_id,
            credential_generation=int(account.credential_generation),
            created_at=now,
            deadline_at=now + CLAIM_LEASE,
            expires_at=now + REQUEST_TTL,
        )
        return self._project_request(request)

    async def create_session(
        self, *, account_id: uuid.UUID, request_id: uuid.UUID
    ) -> DemoSessionIssuedResult:
        """Issue exactly one live session for an EXACT verified request.

        Gates: the request belongs to this account; its state is
        verified_unpublished; it has not expired; the account is still
        enabled with the matching generation; the database-side active
        account count is nonzero; and NO live session already binds this
        copy (a reused copy can never carry two concurrent sessions -
        also enforced by the partial unique index). The session expires
        exactly when the copy does. The raw token is returned ONCE.

        Residual race (documented, 224-b): the live-session count and
        the worker's cleanup ``count-actives-then-CAS`` are not
        serialized, so a session can be issued in the instant between
        the worker's count and its transition to ``cleanup_pending``.
        Such a session is INVALIDATED EARLY by design and is safe: its
        FIRST use is refused by ``validate_session`` because the bound
        request is no longer ``verified_unpublished`` (and a fresh
        ``create_session`` on a cleanup-pending/cleaned copy is refused
        with ``web_request_not_verified``), i.e. before any browser use
        can touch a copy that cleanup is about to remove. The token is
        opaque and only its hash is stored, so the invalidated session
        leaks nothing.
        """
        request = await self._load_request(request_id, read_lock=False)
        if request.account_id != account_id:
            raise DemoWebControlError(
                "web_request_not_owned",
                "This demo snapshot request does not belong to the "
                "supplied account.",
            )
        account = await self._load_account(account_id)
        if not account.is_enabled:
            raise DemoWebControlError(
                "web_account_disabled",
                "The demo account is disabled.",
            )
        if int(account.credential_generation) != int(request.credential_generation):
            raise DemoWebControlError(
                "web_account_generation_mismatch",
                "The demo account credential generation changed since this "
                "snapshot was requested; the request is invalid.",
            )
        active = await self._accounts.count_active_accounts()
        if active <= 0:
            raise DemoWebControlError(
                "web_no_active_accounts",
                "No enabled demo account exists; demo login is unavailable.",
            )
        now = _utcnow()
        if request.state != REQUEST_STATE_VERIFIED_UNPUBLISHED:
            raise DemoWebControlError(
                "web_request_not_verified",
                "A session can only be issued for a verified snapshot copy.",
            )
        if now >= request.expires_at:
            raise DemoWebControlError(
                "web_request_expired",
                "The snapshot copy has expired; a new request is required.",
            )
        if await self._requests.count_active_sessions_for_request(request_id) > 0:
            raise DemoWebControlError(
                "web_request_copy_reused",
                "This verified copy already has a live session; the copy "
                "cannot be reused concurrently.",
            )
        token = generate_opaque_token()
        try:
            session_row = await self._requests.create_session(
                token_hash=hash_opaque_token(token),
                account_id=account_id,
                credential_generation=int(account.credential_generation),
                request_id=request_id,
                created_at=now,
                expires_at=request.expires_at,
            )
        except IntegrityError as exc:
            # Lost the one-live-session-per-copy race (or a replayed
            # token hash): the aborted transaction commits nothing.
            if _pg_constraint_name(exc) in (
                "uq_demo_web_sessions_one_active_per_request",
                "ix_demo_web_sessions_token_hash",
            ):
                raise DemoWebControlError(
                    "web_request_copy_reused",
                    "This verified copy already has a live session; the "
                    "copy cannot be reused concurrently.",
                ) from exc
            raise
        return DemoSessionIssuedResult(
            token=token, session=self._project_session(session_row)
        )

    async def validate_session(
        self, *, account_id: uuid.UUID, token: str
    ) -> DemoWebSessionProjection:
        """Re-validate an active session on EVERY later use.

        Gates: the session exists and belongs to this account; it has
        not been revoked; it has not expired; its bound request is still
        verified_unpublished and unexpired; the account is still enabled
        with the SAME generation recorded on the session; and the
        database-side active account count is still nonzero. Any failure
        is a safe refusal - never a silent pass.
        """
        session_row = await self._requests.get_session_by_token_hash(
            hash_opaque_token(token)
        )
        if session_row is None or session_row.account_id != account_id:
            raise DemoWebControlError(
                "web_session_not_found",
                "No active demo session exists for the supplied identity.",
            )
        if session_row.revoked_at is not None:
            raise DemoWebControlError(
                "web_session_revoked",
                "This demo session has been revoked.",
            )
        now = _utcnow()
        if now >= session_row.expires_at:
            raise DemoWebControlError(
                "web_session_expired",
                "This demo session has expired.",
            )
        request = await self._load_request(session_row.request_id, read_lock=False)
        if request.state != REQUEST_STATE_VERIFIED_UNPUBLISHED:
            raise DemoWebControlError(
                "web_request_not_verified",
                "The bound snapshot copy is no longer verified-unpublished.",
            )
        if now >= request.expires_at:
            raise DemoWebControlError(
                "web_request_expired",
                "The bound snapshot copy has expired.",
            )
        account = await self._load_account(account_id)
        if not account.is_enabled:
            raise DemoWebControlError(
                "web_account_disabled",
                "The demo account is disabled.",
            )
        if int(account.credential_generation) != int(session_row.credential_generation):
            raise DemoWebControlError(
                "web_account_generation_mismatch",
                "The demo account credential generation changed; the "
                "session is invalid.",
            )
        active = await self._accounts.count_active_accounts()
        if active <= 0:
            raise DemoWebControlError(
                "web_no_active_accounts",
                "No enabled demo account exists; demo login is unavailable.",
            )
        return self._project_session(session_row)

    async def revoke_session(
        self, *, account_id: uuid.UUID, token: str
    ) -> DemoWebSessionProjection | None:
        """Revoke a session idempotently (web-owned, its own account only).

        If the session is live and belongs to this account: revoke it
        with ONE atomic guarded UPDATE (needs only the web role's
        column-level UPDATE(revoked_at) grant - no FOR UPDATE). The web
        role has NO write grant on the request rows, so it never
        mutates the request: the WORKER's bounded cleanup path (224-b)
        observes this revocation (plus request expiry) and performs the
        exact cleanup via ``mark_cleanup_pending`` / ``mark_cleaned``.
        Repeating the call is a defined no-op. Returns the session
        projection, or None when no such session exists for this
        account.
        """
        session_row = await self._requests.get_session_by_token_hash(
            hash_opaque_token(token)
        )
        if session_row is None or session_row.account_id != account_id:
            return None
        if session_row.revoked_at is None:
            await self._requests.cas_revoke_session(session_row.id, _utcnow())
        return self._project_session(
            await self._requests.get_session_by_token_hash(
                hash_opaque_token(token), read_lock=False
            )
            or session_row
        )

    async def request_facts(
        self, *, request_id: uuid.UUID
    ) -> DemoSnapshotRequestProjection | None:
        """Safe projection read of one request (224-c web wait poll).

        SELECT-only under the web role's grant on
        ``demo_snapshot_requests``; returns the safe projection
        (``to_safe_dict`` never emits the worker-owned copy locators)
        or ``None``. No mutation, no row lock, no state gate: the
        wait surface owns its own ownership/state/deadline checks on
        the returned projection.
        """
        request = await self._requests.get_request(request_id, read_lock=False)
        if request is None:
            return None
        return self._project_request(request)

    async def session_facts_by_token(
        self, *, token: str
    ) -> DemoWebSessionProjection | None:
        """Resolve the stored session for a raw token (224-c web role).

        The demo session cookie carries ONLY the raw opaque token, so
        the web app must recover the account binding from the stored
        hash before it can call ``validate_session``/``revoke_session``
        (both take ``account_id``). This is a SELECT-only read under the
        web role's ``SELECT`` grant on ``demo_web_sessions`` - no row
        lock, no mutation. It returns the safe projection (which
        includes ``account_id``) or ``None``. It performs NO validation
        gates: the caller MUST still run ``validate_session`` (or
        ``revoke_session``) with the resolved account so every gate is
        rechecked on every use. A blank/absent token resolves to
        ``None`` without touching the database.
        """
        if not token:
            return None
        session_row = await self._requests.get_session_by_token_hash(
            hash_opaque_token(token), read_lock=False
        )
        if session_row is None:
            return None
        return self._project_session(session_row)

    # -- worker role operations --------------------------------------------------

    async def claim_request(self, *, request_id: uuid.UUID) -> DemoSnapshotRequestProjection:
        """Claim exactly one pending request (atomic guarded transition).

        Refusals: unknown request; duplicate/replayed/stale claim (state
        no longer pending - the CAS matches 0 rows and the committed
        state is re-read); the claim lease deadline already passed (the
        row is marked failed/claim_expired); the account was disabled or
        its generation moved (row marked failed/state_conflict - a stale
        job must never proceed). Exactly one concurrent claim wins: the
        CAS serializes on the row under the column-level grants.
        """
        request = await self._load_request(request_id)
        if request.state != REQUEST_STATE_PENDING:
            raise DemoWebControlError(
                "web_request_not_pending",
                "This request was already claimed or otherwise left the "
                "pending state; the claim is refused.",
            )
        now = _utcnow()
        if now >= request.deadline_at:
            request = await self._cas_or_conflict(
                request_id,
                error_code="web_request_not_pending",
                safe_message="The claim lease already expired.",
                to_state=REQUEST_STATE_FAILED,
                from_states=(REQUEST_STATE_PENDING,),
                failure_code=FAILURE_CLAIM_EXPIRED,
            )
            return self._project_request(request)
        account = await self._load_account(request.account_id)
        if not account.is_enabled or int(account.credential_generation) != int(
            request.credential_generation
        ):
            request = await self._cas_or_conflict(
                request_id,
                error_code="web_request_not_pending",
                safe_message="The claim could not be completed; the request "
                "was left in a safe inspectable state.",
                to_state=REQUEST_STATE_FAILED,
                from_states=(REQUEST_STATE_PENDING,),
                failure_code=FAILURE_STATE_CONFLICT,
            )
            return self._project_request(request)
        request = await self._cas_or_conflict(
            request_id,
            error_code="web_request_not_pending",
            safe_message="This request was already claimed or otherwise "
            "left the pending state; the claim is refused.",
            to_state=REQUEST_STATE_CLAIMED,
            from_states=(REQUEST_STATE_PENDING,),
            claimed_at=now,
            # Statement-time credential fence: the live account must
            # still be enabled with the recorded generation IN THIS same
            # atomic statement (the pre-read above is only the fast
            # path); row locks on the account table are impossible under
            # the column-SELECT-only grants.
            account_gate=True,
        )
        return self._project_request(request)

    async def record_verified_handoff(
        self, *, request_id: uuid.UUID, binding: VerifiedCopyBinding
    ) -> DemoSnapshotRequestProjection:
        """Record the worker-only verified handoff (exact binding).

        Accepts ONLY when ALL of the following hold, each enforced in
        this transaction (live reads + atomic guarded transitions, with
        the account fence statement-time in the CAS itself):

        * the closed grammars hold for both copy identities;
        * the request is claimed (no handoff from pending/failed/...);
        * the LIVE account is still enabled and its credential
          generation still equals the request's recorded fence (a
          reset/disable mid-job invalidates the handoff and the row is
          marked failed/state_conflict; enforced STATEMENT-TIME in the
          atomic handoff CAS itself, so even a reset in the window
          between the pre-read and the CAS cannot transition the copy);
        * the copy has not expired (a late completion is refused and the
          row is marked failed/late_completion);
        * the worker-held manifest state is EXACTLY the verified 223
          combined state (any other value -> failed/verification_failed);
        * the database copy-uniqueness invariants hold (the exact job
          identity and copy locator are not already bound to another
          request; a violation is a safe refusal and the transaction is
          aborted, leaving the request claimed for explicit failure).

        The exact job identity and copy locator are published no earlier
        than this point.
        """
        _validate_worker_job_id(binding.worker_job_id)
        _validate_worker_target_db(binding.worker_target_db)
        request = await self._load_request(request_id)
        if request.state != REQUEST_STATE_CLAIMED:
            raise DemoWebControlError(
                "web_request_not_claimed",
                "A verified handoff is only recorded for a claimed request.",
            )
        account = await self._load_account(request.account_id)
        if not account.is_enabled:
            request = await self._cas_or_conflict(
                request_id,
                error_code="web_request_not_claimed",
                safe_message="The handoff could not be completed; the request "
                "was left in a safe inspectable state.",
                to_state=REQUEST_STATE_FAILED,
                from_states=(REQUEST_STATE_CLAIMED,),
                failure_code=FAILURE_STATE_CONFLICT,
            )
            return self._project_request(request)
        if int(account.credential_generation) != int(request.credential_generation):
            request = await self._cas_or_conflict(
                request_id,
                error_code="web_request_not_claimed",
                safe_message="The handoff could not be completed; the request "
                "was left in a safe inspectable state.",
                to_state=REQUEST_STATE_FAILED,
                from_states=(REQUEST_STATE_CLAIMED,),
                failure_code=FAILURE_STATE_CONFLICT,
            )
            return self._project_request(request)
        now = _utcnow()
        if now >= request.expires_at:
            request = await self._cas_or_conflict(
                request_id,
                error_code="web_request_not_claimed",
                safe_message="The handoff could not be completed; the request "
                "was left in a safe inspectable state.",
                to_state=REQUEST_STATE_FAILED,
                from_states=(REQUEST_STATE_CLAIMED,),
                failure_code=FAILURE_LATE_COMPLETION,
            )
            return self._project_request(request)
        # Worker-only lazy import: the web process never reaches this
        # method, so its snapshot-module chain stays unloaded there.
        from slaif_gateway.services.demo_snapshot import (
            STATE_DB_AND_FILES_VERIFIED_UNPUBLISHED,
        )

        if binding.manifest_state != STATE_DB_AND_FILES_VERIFIED_UNPUBLISHED:
            request = await self._cas_or_conflict(
                request_id,
                error_code="web_request_not_claimed",
                safe_message="The handoff could not be completed; the request "
                "was left in a safe inspectable state.",
                to_state=REQUEST_STATE_FAILED,
                from_states=(REQUEST_STATE_CLAIMED,),
                failure_code=FAILURE_VERIFICATION_FAILED,
            )
            return self._project_request(request)
        try:
            request = await self._cas_or_conflict(
                request_id,
                error_code="web_request_not_claimed",
                safe_message="The handoff could not be completed; the request "
                "was left in a safe inspectable state.",
                to_state=REQUEST_STATE_VERIFIED_UNPUBLISHED,
                from_states=(REQUEST_STATE_CLAIMED,),
                worker_job_id=binding.worker_job_id,
                worker_target_db=binding.worker_target_db,
                verified_at=now,
                # Statement-time credential fence (see _load_account):
                # a concurrent reset/disable makes this CAS match 0 rows,
                # so a stale worker result can never become
                # browser-authoritative.
                account_gate=True,
            )
        except IntegrityError as exc:
            # The copy (job identity or copy locator) is already bound
            # to another request: a replayed/forged or double-bound copy.
            # The aborted transaction commits nothing; the request stays
            # claimed for the worker to fail explicitly.
            constraint = _pg_constraint_name(exc)
            if constraint in (
                "uq_demo_snapshot_requests_worker_job_id",
                "uq_demo_snapshot_requests_worker_target_db",
            ):
                raise DemoWebControlError(
                    "web_request_copy_reused",
                    "The supplied copy identity is already bound to "
                    "another request; the handoff was refused.",
                ) from exc
            raise
        return self._project_request(request)

    async def record_worker_failure(
        self, *, request_id: uuid.UUID, code: str
    ) -> DemoSnapshotRequestProjection:
        """Safely fail a pending/claimed request with a finite code.

        Only the worker failure vocabulary is accepted here; verification
        and copy-mismatch failures arise from the specific handoff
        checks, not from this generic path.
        """
        if code not in WORKER_FAILURE_CODES:
            raise DemoWebControlError(
                "web_failure_code_invalid",
                "The supplied failure code is not in the reviewed worker "
                "vocabulary.",
            )
        request = await self._load_request(request_id)
        if request.state not in (REQUEST_STATE_PENDING, REQUEST_STATE_CLAIMED):
            raise DemoWebControlError(
                "web_state_conflict",
                "Only a pending or claimed request can be failed by the "
                "worker.",
            )
        request = await self._cas_or_conflict(
            request_id,
            error_code="web_state_conflict",
            safe_message="The request state already moved; the failure was "
            "not double-recorded.",
            to_state=REQUEST_STATE_FAILED,
            from_states=(REQUEST_STATE_PENDING, REQUEST_STATE_CLAIMED),
            failure_code=code,
        )
        return self._project_request(request)

    async def mark_cleanup_pending(
        self, *, request_id: uuid.UUID
    ) -> DemoSnapshotRequestProjection:
        """Worker: mark cleanup pending (idempotent).

        From verified_unpublished ONLY when no USABLE live session still
        binds the copy (or the copy has expired). A live session makes
        the copy usable ONLY while the bound account is still enabled
        with the recorded credential generation - the per-use recheck
        law of session validation. An account disable or credential
        reset therefore kills every session at its next use, and the
        copy may then enter cleanup IMMEDIATELY (physical cleanup may
        be asynchronous, but it is no longer gated on the 60-minute
        copy lifetime). A live session with an enabled, generation-
        matching account still refuses cleanup. From failed: always.
        This is the worker side of the revocation/cleanup contract: the
        web role revokes its sessions, the worker observes and cleans
        up.
        """
        request = await self._load_request(request_id)
        if request.state == REQUEST_STATE_CLEANUP_PENDING:
            return self._project_request(request)
        if request.state == REQUEST_STATE_FAILED:
            from_states = (REQUEST_STATE_FAILED,)
        elif request.state == REQUEST_STATE_VERIFIED_UNPUBLISHED:
            now = _utcnow()
            if now < request.expires_at:
                account = await self._load_account(request.account_id)
                account_usable = (
                    account.is_enabled
                    and int(account.credential_generation)
                    == int(request.credential_generation)
                )
                if account_usable and (
                    await self._requests.count_active_sessions_for_request(
                        request_id
                    )
                    > 0
                ):
                    raise DemoWebControlError(
                        "web_cleanup_refused_live_session",
                        "The verified copy still has a live session; cleanup "
                        "is refused.",
                    )
            from_states = (REQUEST_STATE_VERIFIED_UNPUBLISHED,)
        else:
            raise DemoWebControlError(
                "web_state_conflict",
                "This request cannot enter cleanup from its current "
                "state.",
            )
        request = await self._cas_or_conflict(
            request_id,
            error_code="web_state_conflict",
            safe_message="The request state already moved; cleanup was not "
            "double-recorded.",
            to_state=REQUEST_STATE_CLEANUP_PENDING,
            from_states=from_states,
        )
        return self._project_request(request)

    async def mark_cleaned(
        self, *, request_id: uuid.UUID
    ) -> DemoSnapshotRequestProjection:
        """Worker: mark cleaned (idempotent) - only from cleanup_pending."""
        request = await self._load_request(request_id)
        if request.state == REQUEST_STATE_CLEANED:
            return self._project_request(request)
        if request.state != REQUEST_STATE_CLEANUP_PENDING:
            raise DemoWebControlError(
                "web_state_conflict",
                "Only a cleanup-pending request can be marked cleaned.",
            )
        request = await self._cas_or_conflict(
            request_id,
            error_code="web_state_conflict",
            safe_message="The request state already moved; cleanup was not "
            "double-recorded.",
            to_state=REQUEST_STATE_CLEANED,
            from_states=(REQUEST_STATE_CLEANUP_PENDING,),
        )
        return self._project_request(request)

    # -- bounded recovery ----------------------------------------------------------

    async def reap_expired(self, *, limit: int = 100) -> int:
        """Bounded recovery after a crash/restart (worker/CLI operation).

        Fails, in inspectable finite states: pending requests whose claim
        lease deadline passed (claim_expired) and claimed requests whose
        full snapshot lifetime passed (late_completion). At most
        ``limit`` rows per call; never publishes anything.
        """
        if limit <= 0 or limit > 1000:
            raise DemoWebControlError(
                "web_reap_limit_invalid",
                "The recovery limit must be a positive bounded integer.",
            )
        now = _utcnow()
        requests = await self._requests.list_expired_for_reap(limit=limit)
        reaped = 0
        for request in requests:
            _require_known_state(request.state)
            if request.state == REQUEST_STATE_PENDING and now >= request.deadline_at:
                if await self._requests.cas_transition(
                    request.id,
                    to_state=REQUEST_STATE_FAILED,
                    from_states=(REQUEST_STATE_PENDING,),
                    failure_code=FAILURE_CLAIM_EXPIRED,
                ):
                    reaped += 1
            elif request.state == REQUEST_STATE_CLAIMED and now >= request.expires_at:
                if await self._requests.cas_transition(
                    request.id,
                    to_state=REQUEST_STATE_FAILED,
                    from_states=(REQUEST_STATE_CLAIMED,),
                    failure_code=FAILURE_LATE_COMPLETION,
                ):
                    reaped += 1
        return reaped


def __getattr__(name: str) -> object:
    """Lazy worker-only constant (PEP 562).

    ``VERIFIED_COPY_STATE`` is imported here on first attribute access
    (tests and the worker CLI path) instead of at module import time, so
    the web process - which imports this service but never reads the
    attribute - never loads the privileged snapshot module chain.
    """
    if name == "VERIFIED_COPY_STATE":
        from slaif_gateway.services.demo_snapshot import (
            STATE_DB_AND_FILES_VERIFIED_UNPUBLISHED,
        )

        return STATE_DB_AND_FILES_VERIFIED_UNPUBLISHED
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
