"""Objective 224-b: exact per-request demo worker handoff and cleanup.

One purpose-built private orchestration path for a specific
``demo_snapshot_requests.id``:

    claim (224-a atomic guarded transition, worker control role)
      -> ONE fresh 221 source export
      -> 222 database sanitation of THAT copy (exact job)
      -> 223 file capture/verification of THAT copy (exact job)
      -> re-read the WORKER-HELD private custody manifest and the
         verified file manifest (identity, target DB, combined verified
         state, every stored leaf digest)
      -> record_verified_handoff (statement-time account fence, copy
         lifetime, database copy-uniqueness invariants)

The worker - never the web role - owns the private custody path and the
seal key. A string supplied by a caller is not verification: publication
happens only when the worker's own re-read of its private custody agrees
on every identity, state and digest immediately before the handoff.

The control connection uses a SEPARATE explicit worker-role credential
(never the owner ``DATABASE_URL``); the operator creates the role and
applies the reviewed 224-a grant matrix before this path can run.
Nothing here creates roles or grants implicitly.

Recovery/cleanup is a bounded, schedulable worker invocation: stuck
pending/claimed rows are reaped (224-a law), failed rows and
session-released verified rows enter ``cleanup_pending``, and each
``cleanup_pending`` row has ONLY its bound disposable target database
dropped and ONLY its owned file/dump custody leaves removed (under the
custody fence) before ``cleaned`` is claimed. A missing, mismatched or
partially surviving bound artifact retains the row in
``cleanup_pending`` for a safe retry; it is never marked ``cleaned``
while a bound artifact remains. A live, unexpired, still-usable
session's verified copy never enters cleanup (224-a service gate).

No HTTP, Celery/Redis, provider forwarding or inference is wired here;
this is a CLI-invoked, worker-only path with safe fixed-vocabulary
output (no job id, target database name, DSN, password or row content
is ever rendered).
"""

from __future__ import annotations

import asyncio
import re
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import quote

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from slaif_gateway.config import Settings
from slaif_gateway.services.catalog_refresh import filesystem as catfs
from slaif_gateway.services import demo_snapshot as ds
from slaif_gateway.services import demo_snapshot_files as dsf
from slaif_gateway.services import demo_snapshot_sanitize as dss
from slaif_gateway.services.demo_web_control import (
    FAILURE_WORKER_FAILED,
    REQUEST_STATE_CLEANUP_PENDING,
    REQUEST_STATE_CLAIMED,
    REQUEST_STATE_FAILED,
    REQUEST_STATE_VERIFIED_UNPUBLISHED,
    DemoWebControlError,
    DemoWebControlService,
    VerifiedCopyBinding,
    _WORKER_JOB_ID_RE,
    _WORKER_TARGET_DB_RE,
)

# --- finite safe worker vocabulary (no value echo, ever) -----------------------

CODE_WORKER_MISCONFIGURED = "WEB_WORKER_MISCONFIGURED"
CODE_WORKER_INTERNAL = "WEB_WORKER_INTERNAL"

_IDENT_RE = re.compile(r"[a-z_][a-z0-9_]{0,62}")

# Bounded recovery/cleanup scan limit (per invocation).
_MAX_CANDIDATES = 100


class DemoWebWorkerError(Exception):
    """Safe fixed-vocabulary error for the demo web worker path.

    ``safe_message`` names only the failing FLAG/FIELD, never a value
    (password, DSN, job id, target database, row content).
    """

    def __init__(self, code: str, safe_message: str) -> None:
        super().__init__(safe_message)
        self.code = code
        self.safe_message = safe_message


# --- configuration (feature-local; default OFF) ---------------------------------


@dataclass(frozen=True, slots=True)
class DemoWebWorkerConfig:
    """Explicitly configured, worker-only exact-handoff inputs.

    The control connection is built from ``control_*`` fields ONLY -
    never from the owner ``DATABASE_URL``. ``control_password`` is
    ``repr=False`` and never rendered; the rendered safe output
    vocabulary contains no connection details.
    """

    control_host: str
    control_port: int
    control_database: str
    control_user: str
    snapshot: ds.DemoSnapshotConfig
    files: dsf.FileSnapshotConfig
    control_password: str = field(repr=False, default="")

    def _control_engine_url(self) -> str:
        return (
            "postgresql+asyncpg://"
            f"{quote(self.control_user, safe='')}:"
            f"{quote(self.control_password, safe='')}"
            f"@{self.control_host}:{self.control_port}/"
            f"{quote(self.control_database, safe='')}"
        )


def web_worker_config_from_settings(settings: Settings) -> DemoWebWorkerConfig:
    """Build the worker config; fail closed with safe finite codes.

    Feature-local validation (223-a precedent): the 221/223 demo
    configuration and the five control-connection fields are validated
    HERE, so an ordinary demo-disabled gateway never fails to start
    because of an optional demo setting. The control user/database must
    match the closed PostgreSQL identifier law (no interpolation
    escape); the password must be non-empty but is never named.
    """
    try:
        snapshot = ds.config_from_settings(settings)
    except ds.DemoSnapshotError as exc:
        raise DemoWebWorkerError(
            CODE_WORKER_MISCONFIGURED, exc.safe_message
        ) from None
    try:
        files = dsf.files_config_from_settings(settings)
    except ds.DemoSnapshotError as exc:
        raise DemoWebWorkerError(
            CODE_WORKER_MISCONFIGURED, exc.safe_message
        ) from None

    def _required(name: str, value: str) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise DemoWebWorkerError(
                CODE_WORKER_MISCONFIGURED,
                f"The demo web worker is missing the {name} configuration.",
            )
        return normalized

    host = _required(
        "DEMO_WEB_WORKER_CONTROL_HOST", settings.DEMO_WEB_WORKER_CONTROL_HOST
    )
    database = _required(
        "DEMO_WEB_WORKER_CONTROL_DATABASE",
        settings.DEMO_WEB_WORKER_CONTROL_DATABASE,
    )
    user = _required(
        "DEMO_WEB_WORKER_CONTROL_USER", settings.DEMO_WEB_WORKER_CONTROL_USER
    )
    _required(
        "DEMO_WEB_WORKER_CONTROL_PASSWORD",
        settings.DEMO_WEB_WORKER_CONTROL_PASSWORD,
    )
    port = int(settings.DEMO_WEB_WORKER_CONTROL_PORT)
    if not 1 <= port <= 65535:
        raise DemoWebWorkerError(
            CODE_WORKER_MISCONFIGURED,
            "The demo web worker control port is outside its finite bound.",
        )
    if not _IDENT_RE.fullmatch(database):
        raise DemoWebWorkerError(
            CODE_WORKER_MISCONFIGURED,
            "The demo web worker control database is not a valid "
            "PostgreSQL identifier.",
        )
    if not _IDENT_RE.fullmatch(user):
        raise DemoWebWorkerError(
            CODE_WORKER_MISCONFIGURED,
            "The demo web worker control user is not a valid "
            "PostgreSQL identifier.",
        )
    return DemoWebWorkerConfig(
        control_host=host,
        control_port=port,
        control_database=database,
        control_user=user,
        control_password=settings.DEMO_WEB_WORKER_CONTROL_PASSWORD.strip(),
        snapshot=snapshot,
        files=files,
    )


# --- bounded control connection --------------------------------------------------


class _ControlConnection:
    """ONE bounded control-connection factory for one worker invocation.

    A single-connection pool (``pool_size=1, max_overflow=0``) keeps the
    invocation finite; ``close()`` disposes the engine. The DSN is built
    from the explicit worker-role fields only.
    """

    def __init__(self, config: DemoWebWorkerConfig) -> None:
        # Explicit no-TLS stage boundary (mirrors the 222 target
        # connection's ``ssl=False``): no TLS is ever negotiated, so
        # the control endpoint must stay on a trusted private
        # loopback/Compose network. This stage does not support
        # verified remote DB TLS.
        self._engine: AsyncEngine = create_async_engine(
            config._control_engine_url(),
            connect_args={"ssl": False},
            pool_pre_ping=True,
            pool_size=1,
            max_overflow=0,
            pool_timeout=10,
        )
        self.sessions: async_sessionmaker[AsyncSession] = async_sessionmaker(
            self._engine, expire_on_commit=False
        )

    async def close(self) -> None:
        await self._engine.dispose()


# --- safe results (no private copy locators, ever) --------------------------------


@dataclass(frozen=True, slots=True)
class ProcessRequestResult:
    """Safe fixed-vocabulary outcome of one exact worker invocation.

    ``state`` is one of ``verified_unpublished`` (success), ``failed``
    (the request row is in a finite failed state or the handoff was
    refused) or ``claim_refused`` (the request already left pending or
    the claim lease/state fence refused this worker). The result NEVER
    contains a job id, target database name or other private copy
    locator; those live only in the worker-private custody and the
    control row (worker role).
    """

    state: str
    failure_code: str | None = None
    elapsed_ms: int = 0

    def to_safe_dict(self) -> dict[str, object]:
        out: dict[str, object] = {"state": self.state, "elapsed_ms": self.elapsed_ms}
        if self.failure_code is not None:
            out["code"] = self.failure_code
        return out


@dataclass(frozen=True, slots=True)
class CleanupResult:
    """Safe fixed-vocabulary outcome of one bounded recovery/cleanup."""

    reaped: int = 0
    cleanup_marked: int = 0
    cleaned: int = 0
    retained: int = 0
    failure_code: str | None = None
    elapsed_ms: int = 0

    def to_safe_dict(self) -> dict[str, object]:
        out: dict[str, object] = {
            "reaped": self.reaped,
            "cleanup_marked": self.cleanup_marked,
            "cleaned": self.cleaned,
            "retained": self.retained,
            "elapsed_ms": self.elapsed_ms,
        }
        if self.failure_code is not None:
            out["code"] = self.failure_code
        return out


def _elapsed_ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)


# --- worker-held proof (re-read, never trust a string) ---------------------------


# Trusted read cap for the private main custody manifest (fixed small
# field set; a larger file is an invariant violation, not a read).
_WORKER_MAIN_MANIFEST_MAX_BYTES = 64 * 1024


def _verify_worker_held(
    config: DemoWebWorkerConfig,
    job_id: str,
    request_id: uuid.UUID,
) -> VerifiedCopyBinding | None:
    """Re-read the WORKER-HELD private custody and prove the exact
    combined verified state immediately before publication.

    Proves, from the worker's own files (never from any caller string):

    * the main manifest read through the ANCHORED held job handle
      (no pathname read: a swapped job directory cannot redirect the
      proof);
    * the manifest identity (stored job id == exact job id);
    * the EXACT request ownership (the manifest's private ``request_id``
      association - written before target creation - equals the request
      being handed off; a foreign or forged manifest can never pass);
    * the exact target database name (closed grammar);
    * the combined 222+223 verified manifest state;
    * the files state is verified;
    * the complete 223 display-tree law, re-proven through the shared
      read-only ``_reprove_files_tree`` (anchored no-follow reads):
      files-directory identity, the EXACT leaf set (no foreign entry,
      no duplicate or invalid name), per-leaf regular type / 0600
      mode / byte count / inode identity, digests and display policy.
      A promoted tree is re-proven exactly as hard as a fresh one.
    * the SAME job-directory identity binds both reads: the
      ``(st_dev, st_ino)`` captured by the main-manifest handle is
      required by the files re-proof, so a directory swapped between
      the two held handles cannot pair manifest A with files tree B;
    * the re-proven leaf count and total bytes equal the main
      manifest's recorded ``files_count`` / ``files_bytes``.

    Returns the binding only when everything agrees; ``None`` otherwise
    (the caller fails the request and never publishes).
    """
    if not _WORKER_JOB_ID_RE.fullmatch(job_id):
        return None
    job_dir = config.snapshot.custody_dir / job_id
    try:
        handle = catfs.open_anchored_handle(job_dir)
    except catfs.CatalogRefreshSealError:
        return None
    try:
        handle.assert_name_binding(str(job_dir))
        # Bind the files re-proof to THIS exact job directory.
        job_identity = handle.identity
        try:
            raw = catfs.anchored_read_fd(
                handle.dir_fd,
                ds._MANIFEST_NAME,
                _WORKER_MAIN_MANIFEST_MAX_BYTES,
            )
        except (OSError, catfs.CatalogRefreshSealError):
            return None
    finally:
        handle.close()
    manifest = ds._manifest_from_bytes(raw)
    if (
        manifest is None
        or manifest.job_id != job_id
        or manifest.request_id != str(request_id)
        or manifest.state != ds.STATE_DB_AND_FILES_VERIFIED_UNPUBLISHED
        or manifest.files_state != dsf.FILES_STATE_VERIFIED
        or not _WORKER_TARGET_DB_RE.fullmatch(manifest.target_db)
    ):
        return None
    deadline = time.monotonic() + config.files.max_elapsed_seconds
    try:
        total_bytes, leaf_count = dsf._reprove_files_tree(
            job_dir,
            config.files,
            deadline,
            expected_job_identity=job_identity,
        )
    except ds.DemoSnapshotError:
        return None
    if (
        manifest.files_count != leaf_count
        or manifest.files_bytes != total_bytes
    ):
        return None
    return VerifiedCopyBinding(
        worker_job_id=manifest.job_id,
        worker_target_db=manifest.target_db,
        manifest_state=manifest.state,
    )


# --- protected-copy law (221 eviction/admission boundary) ------------------------


_PROTECTED_JOB_IDS_SQL = text(
    """
    SELECT DISTINCT r.worker_job_id
    FROM demo_control.demo_snapshot_requests AS r
    WHERE r.state = 'verified_unpublished'
      AND r.worker_job_id IS NOT NULL
      AND r.expires_at > now()
    """
)


async def _protected_job_ids(control: _ControlConnection) -> frozenset[str]:
    """Job ids of published verified copies that must survive the 221
    expiry/budget pass of this run: every ``verified_unpublished``
    request that has not expired (a second login may still issue a
    session on that copy, so it is protected regardless of whether a
    session row is currently live).
    """
    async with control.sessions() as session:
        result = await session.execute(_PROTECTED_JOB_IDS_SQL)
        return frozenset(str(v) for v in result.scalars().all())


async def _safe_record_failure(
    control: _ControlConnection, request_id: uuid.UUID
) -> None:
    """Record the generic worker failure; keep the row inspectable.

    A control-side refusal (state already moved) or a control outage is
    swallowed: the request remains in its current finite state and the
    bounded recovery invocation reaps it later.
    """
    try:
        async with control.sessions.begin() as session:
            await DemoWebControlService(session).record_worker_failure(
                request_id=request_id, code=FAILURE_WORKER_FAILED
            )
    except Exception:
        pass


# --- exact per-request worker invocation -------------------------------------------


async def process_request(
    config: DemoWebWorkerConfig,
    settings: Settings,
    *,
    request_id: uuid.UUID,
    _control: _ControlConnection | None = None,
) -> ProcessRequestResult:
    """Process ONE specific request: claim -> 221 -> 222 -> 223 -> proof
    -> verified handoff. Bounded, worker-only, exact-copy.

    * The claim is the 224-a atomic guarded transition: exactly one
      concurrent worker can win; a lost, replayed or stale claim is a
      safe ``claim_refused`` result and no pipeline runs.
    * ONE fresh 221 copy is created; the run's expiry/budget pass and
      admission never evict a protected published copy (fail-closed).
    * 222 and 223 run on THAT job only (exact-job selectors); unrelated
      pre-existing copies are never touched or promoted.
    * Before publication the worker re-reads its OWN private custody
      (manifest + verified file manifest + every leaf digest); a
      mismatch fails the request instead of publishing.
    * The handoff CAS rechecks the statement-time account fence, the
      copy lifetime, and the database copy-uniqueness invariants.

    Every failure leaves the request in an inspectable finite state;
    nothing is ever silently published.
    """
    started = time.monotonic()
    control = _control or _ControlConnection(config)
    try:
        # 1) Claim exactly this pending request.
        try:
            async with control.sessions.begin() as session:
                projection = await DemoWebControlService(session).claim_request(
                    request_id=request_id
                )
        except DemoWebControlError as exc:
            return ProcessRequestResult(
                "claim_refused", exc.code, _elapsed_ms(started)
            )
        if projection.state != REQUEST_STATE_CLAIMED:
            return ProcessRequestResult(
                "claim_refused",
                projection.failure_code or "state_conflict",
                _elapsed_ms(started),
            )

        # 2) ONE fresh 221 copy (never evicting a protected copy). The
        # request identity is durably bound into the private custody
        # manifest BEFORE the target database is created. The 221/222/
        # 223 entry points are SYNCHRONOUS and 222/223 spawn their own
        # ``asyncio.run`` internally, so every stage runs OFF the
        # control loop (worker-only single-task invocation; a stage on
        # the loop would raise and fail the request).
        protected = await _protected_job_ids(control)
        job = await asyncio.to_thread(
            ds.run_snapshot_job,
            config.snapshot,
            protected_job_ids=protected,
            request_id=str(request_id),
        )
        if job.state != ds.STATE_RAW_UNVERIFIED or not _WORKER_JOB_ID_RE.fullmatch(
            job.job_id
        ):
            await _safe_record_failure(control, request_id)
            return ProcessRequestResult(
                "failed",
                job.failure_code or CODE_WORKER_INTERNAL,
                _elapsed_ms(started),
            )

        # 3) 222 sanitation of THAT job only.
        san = await asyncio.to_thread(
            dss.sanitize_copies, config.snapshot, job_id=job.job_id
        )
        if (
            san.state != dss.SANITIZE_STATE_SANITIZED
            or san.copies_sanitized != 1
            or san.copies_failed
        ):
            await _safe_record_failure(control, request_id)
            return ProcessRequestResult(
                "failed",
                san.failure_code or CODE_WORKER_INTERNAL,
                _elapsed_ms(started),
            )

        # 4) 223 file capture/verification of THAT job only.
        files = await asyncio.to_thread(
            dsf.run_files_job, config.files, settings, job_id=job.job_id
        )
        if files.state != "FILES_VERIFIED" or files.copies_failed:
            await _safe_record_failure(control, request_id)
            return ProcessRequestResult(
                "failed",
                files.failure_code or CODE_WORKER_INTERNAL,
                _elapsed_ms(started),
            )

        # 5) Worker-held proof (re-read + digest + exact request
        # ownership), then 6) handoff.
        binding = _verify_worker_held(config, job.job_id, request_id)
        if binding is None:
            await _safe_record_failure(control, request_id)
            return ProcessRequestResult(
                "failed", FAILURE_WORKER_FAILED, _elapsed_ms(started)
            )
        try:
            async with control.sessions.begin() as session:
                projection = await DemoWebControlService(session).record_verified_handoff(
                    request_id=request_id, binding=binding
                )
        except DemoWebControlError as exc:
            return ProcessRequestResult(
                "failed", exc.code, _elapsed_ms(started)
            )
        if projection.state != REQUEST_STATE_VERIFIED_UNPUBLISHED:
            return ProcessRequestResult(
                "failed",
                projection.failure_code or "state_conflict",
                _elapsed_ms(started),
            )
        return ProcessRequestResult(
            REQUEST_STATE_VERIFIED_UNPUBLISHED, None, _elapsed_ms(started)
        )
    except DemoWebWorkerError:
        raise
    except Exception:
        await _safe_record_failure(control, request_id)
        return ProcessRequestResult(
            "failed", CODE_WORKER_INTERNAL, _elapsed_ms(started)
        )
    finally:
        if _control is None:
            await control.close()


# --- bounded recovery/cleanup invocation -------------------------------------------


_CANDIDATE_SQL = text(
    """
    SELECT r.id, r.state, r.worker_job_id, r.worker_target_db
    FROM demo_control.demo_snapshot_requests AS r
    WHERE r.state IN ('failed', 'cleanup_pending', 'verified_unpublished')
    ORDER BY r.created_at ASC, r.id ASC
    LIMIT :limit
    """
)


async def _candidate_rows(
    control: _ControlConnection, limit: int
) -> list[dict[str, Any]]:
    """Bounded oldest-first scan of worker-side cleanup candidates.

    Reads only the worker-granted columns (id, state, worker_job_id,
    worker_target_db); at most ``limit`` rows per invocation.
    """
    async with control.sessions() as session:
        result = await session.execute(_CANDIDATE_SQL, {"limit": limit})
        return [dict(row._mapping) for row in result.fetchall()]


# Ownership findings (224-b fail-closed law): ZERO means the scan
# positively confirmed that no job is bound (and every manifest was
# readable); ONE means exactly one binding; AMBIGUOUS means either
# more than one job binds the request OR at least one custody manifest
# could not be read/validated (its owner cannot be positively excluded).
_OWNERSHIP_ZERO = "zero"
_OWNERSHIP_ONE = "one"
_OWNERSHIP_AMBIGUOUS = "ambiguous"


def _find_job_for_request(
    config: DemoWebWorkerConfig, request_id: str
) -> tuple[str, Path | None]:
    """Find the EXACT custody job durably bound to one request.

    The association lives in the private custody manifest's
    ``request_id`` field (written before the target database is
    created). A bounded scan of the validated custody root returns
    ``(status, job_dir)``: ``ZERO`` with ``None`` when no non-cleaned
    manifest names this request AND every manifest was readable;
    ``ONE`` with the single job directory; ``AMBIGUOUS`` with ``None``
    when more than one job binds the request, or any manifest is
    unreadable/malformed (its owner cannot be positively excluded).
    Ambiguity is an ownership-invariant violation: the caller MUST
    retain the request and every artifact for operator inspection -
    never mark cleaned. Nothing is ever inferred from directory order
    or timestamps.
    """
    matches: list[Path] = []
    unreadable = False
    for job_dir in ds._list_job_dirs(config.snapshot.custody_dir):
        manifest = ds._read_manifest(job_dir)
        if manifest is None:
            unreadable = True
            continue
        if manifest.request_id == request_id and manifest.state != ds.STATE_CLEANED:
            matches.append(job_dir)
    if len(matches) > 1 or unreadable:
        return _OWNERSHIP_AMBIGUOUS, None
    if len(matches) == 1:
        return _OWNERSHIP_ONE, matches[0]
    return _OWNERSHIP_ZERO, None


def _cleanup_bound_artifacts(
    config: DemoWebWorkerConfig,
    row: dict[str, Any],
    expected_request_id: str | None = None,
) -> bool:
    """Drop ONLY the bound target DB + remove ONLY the owned custody
    leaves for ONE ``cleanup_pending`` row; prove absence.

    Under the custody fence:

    * the control-row binding must match the closed grammars;
    * when the worker-private manifest exists, its recorded target
      database must AGREE with the control row (a mismatch is an
      operator-inspection condition and never a drop);
    * the manifest's job identity must match the job directory it was
      read from, and - when ``expected_request_id`` is given (the
      unbound recovery path) - the manifest's request association must
      match it too. These are re-read UNDER the fence immediately
      before the drop: a manifest swapped between the caller's scan
      and the drop cannot redirect the removal.
    * ``_cleanup_artifacts`` removes the dump, drops the exact target
      database, then the exact 223 display leaves (DB first, files
      second - the 223 ordering law);
    * the target database must then be verifiably absent.

    ``True`` only when every step completed and absence is proven; the
    manifest (when present) is updated to the 221 law
    (``CLEANED`` / ``CLEANUP_FAILED``). A failed step retains the row in
    ``cleanup_pending`` for a safe retry.
    """
    job_id = row["worker_job_id"]
    target_db = row["worker_target_db"]
    if (
        not isinstance(job_id, str)
        or not isinstance(target_db, str)
        or not _WORKER_JOB_ID_RE.fullmatch(job_id)
        or not _WORKER_TARGET_DB_RE.fullmatch(target_db)
    ):
        return False
    try:
        ds._validate_custody_dir(config.snapshot.custody_dir)
    except ds.DemoSnapshotError:
        return False
    fence_fd = ds._acquire_fence(config.snapshot.custody_dir)
    try:
        workdir = config.snapshot.custody_dir
        secrets = list(
            ds._read_passfile_passwords(
                config.snapshot.pgpassfile, config.snapshot
            )
        )
        ops = ds._target_ops(config.snapshot, workdir=workdir, secrets=secrets)
        job_dir = config.snapshot.custody_dir / job_id
        manifest = ds._read_manifest(job_dir)
        if manifest is not None and (
            manifest.job_id != job_id
            or manifest.target_db != target_db
            or (
                expected_request_id is not None
                and manifest.request_id != expected_request_id
            )
        ):
            return False
        clean = ds._cleanup_artifacts(ops, job_dir, target_db)
        if not clean:
            if manifest is not None:
                manifest.state = ds.STATE_CLEANUP_FAILED
                manifest.failure_code = ds.CODE_CLEANUP_FAILED
                try:
                    ds._write_manifest(job_dir, manifest)
                except OSError:
                    pass
            return False
        if manifest is not None:
            manifest.state = ds.STATE_CLEANED
            manifest.failure_code = None
            try:
                ds._write_manifest(job_dir, manifest)
            except OSError:
                return False
        return ops.database_exists(target_db) is False
    finally:
        ds._release_fence(fence_fd)


async def recover_and_cleanup(
    config: DemoWebWorkerConfig,
    *,
    limit: int = _MAX_CANDIDATES,
    _control: _ControlConnection | None = None,
) -> CleanupResult:
    """Bounded recovery/cleanup invocation (worker-only; schedulable).

    1. Reap stuck pending/claimed rows (224-a bounded recovery law:
       claim lease / full lifetime, finite codes, at most ``limit``).
    2. For a bounded oldest-first set of candidates: mark ``failed``
       rows and session-released ``verified_unpublished`` rows
       ``cleanup_pending`` (the 224-a service enforces the live
       usable-session gate; a refused row is counted retained and left
       untouched).
    3. Every ``cleanup_pending`` row: drop ONLY the bound target
       database and remove ONLY its owned custody leaves (under the
       custody fence), prove absence, then mark ``cleaned``. A row
       without a published control binding still has its exact owned
       job found through the durable private custody association
       (``manifest.request_id``, written before target creation) and
       cleaned ONLY when exactly one such job exists; a row for which
       the scan positively confirms nothing is bound (and every
       manifest is readable) is marked cleaned directly. An AMBIGUOUS
       finding - double-bound request or unreadable manifest - retains
       the row and every artifact. Nothing is ever inferred from
       directory order or timestamps. A missing, mismatched,
       double-bound or partially surviving owned artifact retains the
       row in ``cleanup_pending`` (inspectable, retry-safe) and is
       never marked ``cleaned``.

    No bound copy of a live, unexpired, still-usable session is ever
    touched (224-a service gate + the 221 protected-copy law).
    """
    if not 1 <= limit <= _MAX_CANDIDATES:
        raise DemoWebWorkerError(
            CODE_WORKER_MISCONFIGURED,
            "The recovery limit must be a positive bounded integer.",
        )
    started = time.monotonic()
    control = _control or _ControlConnection(config)
    reaped = 0
    marked = 0
    cleaned = 0
    retained = 0
    first_code: str | None = None
    try:
        try:
            async with control.sessions.begin() as session:
                reaped = await DemoWebControlService(session).reap_expired(
                    limit=limit
                )
        except DemoWebControlError:
            pass
        rows = await _candidate_rows(control, limit)
        for row in rows:
            row_id = row["id"]
            state = row["state"]
            if state in (REQUEST_STATE_FAILED, REQUEST_STATE_VERIFIED_UNPUBLISHED):
                try:
                    async with control.sessions.begin() as session:
                        await DemoWebControlService(session).mark_cleanup_pending(
                            request_id=row_id
                        )
                    marked += 1
                except DemoWebControlError:
                    # Live usable session (or state moved): retained,
                    # untouched, retried on a later invocation.
                    retained += 1
                    continue
                state = REQUEST_STATE_CLEANUP_PENDING
            if state != REQUEST_STATE_CLEANUP_PENDING:
                retained += 1
                continue
            if row["worker_job_id"] is None or row["worker_target_db"] is None:
                # No published control binding: find the exact owned job
                # through the DURATION-bounded private custody
                # association (written before target creation). Never
                # inferred by order/time; never a blind "nothing owned".
                status, job_dir = _find_job_for_request(config, str(row_id))
                if status == _OWNERSHIP_AMBIGUOUS:
                    # Ownership-invariant violation: more than one job
                    # binds this request, or a custody manifest is
                    # unreadable (its owner cannot be excluded). Retain
                    # the row and EVERY artifact for operator
                    # inspection; never mark cleaned.
                    retained += 1
                    first_code = first_code or ds.CODE_CLEANUP_FAILED
                    continue
                if job_dir is not None:
                    manifest = ds._read_manifest(job_dir)
                    if (
                        manifest is None
                        or not _WORKER_JOB_ID_RE.fullmatch(manifest.job_id)
                        or not _WORKER_TARGET_DB_RE.fullmatch(manifest.target_db)
                    ):
                        retained += 1
                        first_code = first_code or ds.CODE_CLEANUP_FAILED
                        continue
                    bound_row = {
                        "worker_job_id": manifest.job_id,
                        "worker_target_db": manifest.target_db,
                    }
                    if _cleanup_bound_artifacts(
                        config, bound_row, expected_request_id=str(row_id)
                    ):
                        try:
                            async with control.sessions.begin() as session:
                                await DemoWebControlService(session).mark_cleaned(
                                    request_id=row_id
                                )
                            cleaned += 1
                        except DemoWebControlError:
                            retained += 1
                    else:
                        retained += 1
                        first_code = first_code or ds.CODE_CLEANUP_FAILED
                    continue
                # Status ZERO: the scan positively confirmed nothing is
                # bound and every manifest was readable (the claim
                # failed before any 221 job, or the owned job was
                # already cleaned): safe to claim cleaned.
                try:
                    async with control.sessions.begin() as session:
                        await DemoWebControlService(session).mark_cleaned(
                            request_id=row_id
                        )
                    cleaned += 1
                except DemoWebControlError:
                    retained += 1
                continue
            if _cleanup_bound_artifacts(config, row):
                try:
                    async with control.sessions.begin() as session:
                        await DemoWebControlService(session).mark_cleaned(
                            request_id=row_id
                        )
                    cleaned += 1
                except DemoWebControlError:
                    retained += 1
            else:
                retained += 1
                first_code = first_code or ds.CODE_CLEANUP_FAILED
    finally:
        if _control is None:
            await control.close()
    return CleanupResult(
        reaped=reaped,
        cleanup_marked=marked,
        cleaned=cleaned,
        retained=retained,
        failure_code=first_code,
        elapsed_ms=_elapsed_ms(started),
    )
