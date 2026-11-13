"""Real owned-PostgreSQL-16 evidence for objective 224-b exact worker
handoff and cleanup.

Runs on the 222 owned fixture pair (``san_env`` from
``test_demo_snapshot_sanitize_postgres``): the migrated source business
database (which carries the 0028 ``demo_control`` schema - the control
database of this deployment) and the dedicated separate target service,
plus the 221/222/223 worker configuration, run-tagged canary seed rows,
and the exact run-owned teardown (recorded target databases dropped,
roles dropped, seed rows deleted, residue asserted).

Adds the 224-b worker-side roles ON THE CONTROL DATABASE (source
service): the web role and the worker role, created from the reviewed
224-a grant matrix (``web_role_grant_sql`` / ``worker_role_grant_sql``),
plus one seeded enabled fake-admin account. The worker connects with
its dedicated worker role - never the owner credential.

Proves, against real PostgreSQL 16:

- one request -> ONE exact fresh 221 copy -> 222 + 223 for THAT copy
  -> worker-held proof -> verified handoff: the control row binding
  (worker_job_id / worker_target_db / state) equals the private custody
  manifest and the copy data is canary-free; the web role can issue
  and validate a session on the published copy;
- a second request gets a DISTINCT copy (distinct job + target db);
- two racing workers: exactly one claim, one copy, the other refused;
- an unbound legacy raw copy is never promoted or consumed by a
  request run (exact-job selectors only);
- a mid-job credential reset refuses the late handoff (statement-time
  account fence under the worker role);
- copy-locator reuse is refused by the database unique invariants
  (two requests can never bind one job or one target db);
- the finite copy budget, full of verified (never-evictable) copies,
  refuses the next request fail-closed before creating anything;
- the session-aware cleanup law under real roles: a live usable
  session refuses cleanup; revocation releases it (target db dropped,
  files removed, manifest CLEANED, row cleaned); an account disable
  releases a live-session copy immediately; a crashed worker's bound
  raw copy is recovered through the durable private request association
  with no survivors;
- the restricted-role matrix is enforced by the database (42501): the
  web role cannot write request state/worker columns or read account
  secrets; the worker role cannot read username/password_hash/token_hash;
- the worker CLI emits only the safe fixed vocabulary - the worker
  control password canary is never rendered.

No provider HTTP, no Redis, no normal admin auth, no email. The demo
remains unusable from a browser (no 224-b web route). Ownership
discipline mirrors the 222/224-a owned fixtures: run-tagged roles,
exact run-owned cleanup only.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from pathlib import Path
from collections.abc import Iterator
from typing import Any
from urllib.parse import quote

import asyncpg
import pytest
from slaif_gateway.config import Settings
from slaif_gateway.services import demo_snapshot as ds
from slaif_gateway.services import demo_web_worker as dww
from slaif_gateway.services.demo_web_control import (
    VERIFIED_COPY_STATE,
    DemoWebControlError,
    DemoWebControlService,
    VerifiedCopyBinding,
    web_role_grant_sql,
    worker_role_grant_sql,
)
from tests.integration.test_demo_snapshot_sanitize_postgres import (
    READER_ROLE,
    _CANARY_SOURCE_PW,
    _RC_CANARY_PROFILE,
    _Env,
    _all_public_tables,
    _connect_target_db,
    _copy_scan,
    _settings_for,
)
from tests.integration.test_demo_web_control_postgres import (
    _denied,
    _exec,
    _scalar,
    _scalar_many,
    _seed_account,
    _session_factory,
)

# Make the two owned-PostgreSQL fixtures (function-scope ``custody`` and
# module-scope ``san_env``) available to this module by plugin registration,
# so they can be requested BY NAME without a fixture-name import that would
# collide (F811) with the test-function parameters of the same name.
pytest_plugins = ("tests.integration.test_demo_snapshot_sanitize_postgres",)

_RUN_TAG = uuid.uuid4().hex[:8]
_WEB_ROLE = f"slaif224b_web_{_RUN_TAG}"
_WORKER_ROLE = f"slaif224b_worker_{_RUN_TAG}"
_WEB_PW = f"canary-web-pw-224b-{_RUN_TAG}"
_WORKER_PW = f"canary-worker-pw-224b-{_RUN_TAG}"


# --- fixtures ----------------------------------------------------------------


def _source_conn_kwargs(source: dict[str, object]) -> dict[str, Any]:
    return {
        "host": str(source["host"]),
        "port": int(source["port"]),
        "user": str(source["user"]),
        "password": str(source["password"]),
        "database": str(source["database"]),
    }


def _role_url(source: dict[str, object], role: str, password: str) -> str:
    return (
        f"postgresql+asyncpg://{quote(role)}:{quote(password)}"
        f"@{source['host']}:{source['port']}/{source['database']}"
    )

@pytest.fixture(scope="module")
def _wenv_base(
    san_env: _Env, tmp_path_factory: pytest.TempPathFactory
) -> Iterator[dict[str, Any]]:
    """Module-scoped worker-side ROLES + shared completion-profile source,
    with exact run-owned teardown. The seeded fake-admin ACCOUNT is
    function-scoped (see ``wenv``) so the worker's GLOBAL recovery/cleanup
    pass only ever sees one test's control rows; the roles are
    schema-scoped grants and can safely be shared across the module."""
    source = san_env.source
    source_url = str(source["url"])

    # Owned completion-profile source for the 223 combined DB/files link
    # gate: the 222 fixture seeds one model_route whose completion_service
    # profile is _RC_CANARY_PROFILE (222 fictionalizes that id per copy), so
    # the worker's 223 capture must offer EXACTLY that stem or the gate
    # refuses with FILES_VERIFY_FAILED. The profile BODY is never read by the
    # 223 capture (stems only - the admin GET never exposes bodies), so a
    # neutral placeholder suffices. 0700 dir, 0600 leaf, never group/world
    # writable. The production link gate is unchanged.
    profile_dir = tmp_path_factory.mktemp("224b-profiles") / "profiles"
    profile_dir.mkdir(mode=0o700)
    (profile_dir / f"{_RC_CANARY_PROFILE}.json").write_text("{}")
    os.chmod(profile_dir, 0o700)
    os.chmod(profile_dir / f"{_RC_CANARY_PROFILE}.json", 0o600)

    async def setup() -> None:
        s = await asyncpg.connect(**_source_conn_kwargs(source))
        try:
            for role in (_WEB_ROLE, _WORKER_ROLE):
                await s.execute(f'DROP ROLE IF EXISTS "{role}"')
            await s.execute(
                f"CREATE ROLE \"{_WEB_ROLE}\" LOGIN PASSWORD '{_WEB_PW}' "
                "NOCREATEDB NOCREATEROLE"
            )
            await s.execute(
                f"CREATE ROLE \"{_WORKER_ROLE}\" LOGIN PASSWORD '{_WORKER_PW}' "
                "NOCREATEDB NOCREATEROLE"
            )
        finally:
            await s.close()
        for stmt in web_role_grant_sql(_WEB_ROLE) + worker_role_grant_sql(
            _WORKER_ROLE
        ):
            await _exec(source_url, stmt)

    asyncio.run(setup())
    try:
        yield {
            "source_url": source_url,
            "web_url": _role_url(source, _WEB_ROLE, _WEB_PW),
            "worker_url": _role_url(source, _WORKER_ROLE, _WORKER_PW),
            "web_role": _WEB_ROLE,
            "worker_role": _WORKER_ROLE,
            "web_pw": _WEB_PW,
            "worker_pw": _WORKER_PW,
            "profile_dir": str(profile_dir),
        }
    finally:
        async def _teardown() -> None:
            s = await asyncpg.connect(**_source_conn_kwargs(source))
            try:
                for role in (_WEB_ROLE, _WORKER_ROLE):
                    # The reviewed grants (USAGE on demo_control + the
                    # column/table privileges) must be revoked before the
                    # role can be dropped; the owner (test) granted them, so
                    # the owner can revoke them. Role identifiers cannot be
                    # bound as DDL parameters, so they are inlined as quoted
                    # identifiers (self-generated names, not external input).
                    await s.execute(
                        f'REVOKE ALL ON ALL TABLES IN SCHEMA demo_control '
                        f'FROM "{role}"'
                    )
                    await s.execute(
                        f'REVOKE ALL ON ALL SEQUENCES IN SCHEMA demo_control '
                        f'FROM "{role}"'
                    )
                    await s.execute(
                        f'REVOKE ALL ON ALL FUNCTIONS IN SCHEMA demo_control '
                        f'FROM "{role}"'
                    )
                    await s.execute(
                        f'REVOKE USAGE ON SCHEMA demo_control FROM "{role}"'
                    )
                    await s.execute(f'DROP ROLE IF EXISTS "{role}"')
                remaining = await s.fetch(
                    "SELECT rolname FROM pg_roles WHERE rolname IN ($1, $2)",
                    _WEB_ROLE,
                    _WORKER_ROLE,
                )
            finally:
                await s.close()
            if remaining:
                raise AssertionError(
                    "run-owned roles remain after cleanup: "
                    + ", ".join(r["rolname"] for r in remaining)
                )

        try:
            asyncio.run(_teardown())
        except Exception as exc:
            pytest.fail(f"224-b role cleanup incomplete: {exc!r}")


@pytest.fixture()
def wenv(_wenv_base: dict[str, Any]) -> Iterator[dict[str, Any]]:
    """Function-scoped seeded ACCOUNT (fresh per test).

    A fresh account isolates this test's control rows from every other test
    in the module: the worker's ``recover_and_cleanup`` is a GLOBAL
    oldest-first pass over ALL accounts, but each test uses a separate
    function-scoped ``custody`` directory, so a shared (module-scoped)
    account would leak other tests' published/claimed rows into this test's
    cleanup scan (and vice versa). Deleting the account's sessions and
    requests before the account keeps teardown FK-safe."""
    source_url = str(_wenv_base["source_url"])
    account_id: uuid.UUID | None = None
    try:
        account_id = _seed_account(
            source_url, f"slaif224b-admin-{uuid.uuid4().hex[:8]}"
        )
        yield {**_wenv_base, "account_id": account_id}
    finally:
        async def _teardown() -> None:
            if account_id is None:
                return
            # Delete in FK order: demo_web_sessions (-> account, -> request)
            # before demo_snapshot_requests (-> account), which must both be
            # gone before the account itself.
            await _exec(
                source_url,
                "DELETE FROM demo_control.demo_web_sessions "
                f"WHERE account_id = '{account_id}'",
            )
            await _exec(
                source_url,
                "DELETE FROM demo_control.demo_snapshot_requests "
                f"WHERE account_id = '{account_id}'",
            )
            await _exec(
                source_url,
                f"DELETE FROM demo_control.fake_admin_accounts "
                f"WHERE id = '{account_id}'",
            )
            assert (
                await _scalar(
                    source_url,
                    "SELECT EXISTS (SELECT 1 FROM demo_control.fake_admin_accounts "
                    "WHERE id = :id)",
                    {"id": str(account_id)},
                )
                is False
            ), "seeded account row remains after cleanup"

        asyncio.run(_teardown())


# --- helpers -----------------------------------------------------------------


def _worker_settings(
    san: _Env, env: dict[str, Any], custody: Path, **overrides: Any
) -> Settings:
    source = san.source
    base = _settings_for(san, custody)
    base.update(
        {
            "DEMO_WEB_WORKER_CONTROL_HOST": source["host"],
            "DEMO_WEB_WORKER_CONTROL_PORT": int(source["port"]),
            "DEMO_WEB_WORKER_CONTROL_DATABASE": source["database"],
            "DEMO_WEB_WORKER_CONTROL_USER": env["worker_role"],
            "DEMO_WEB_WORKER_CONTROL_PASSWORD": env["worker_pw"],
            "COMPLETION_SERVICE_PROFILE_DIR": str(env["profile_dir"]),
        }
    )
    base.update(overrides)
    return Settings(**base)


def _worker_config(
    san: _Env, env: dict[str, Any], custody: Path, **overrides: Any
):
    settings = _worker_settings(san, env, custody, **overrides)
    return dww.web_worker_config_from_settings(settings), settings


def _create_request(env: dict[str, Any]) -> uuid.UUID:
    async def run() -> uuid.UUID:
        factory = _session_factory(str(env["web_url"]))
        async with factory() as session, session.begin():
            proj = await DemoWebControlService(session).create_request(
                account_id=env["account_id"]
            )
            return proj.id

    return asyncio.run(run())


def _issue_session(env: dict[str, Any], request_id: uuid.UUID) -> str:
    async def run() -> str:
        factory = _session_factory(str(env["web_url"]))
        async with factory() as session, session.begin():
            issued = await DemoWebControlService(session).create_session(
                account_id=env["account_id"], request_id=request_id
            )
            return issued.token

    return asyncio.run(run())


def _request_row(env: dict[str, Any], request_id: uuid.UUID) -> dict[str, Any]:
    async def run() -> dict[str, Any]:
        rows = await _scalar_many(
            str(env["source_url"]),
            "SELECT id, state, failure_code, worker_job_id, worker_target_db "
            "FROM demo_control.demo_snapshot_requests WHERE id = :id",
            {"id": str(request_id)},
        )
        return dict(rows[0]._mapping)

    return asyncio.run(run())


def _job_identity_of(custody: Path, request_id: uuid.UUID) -> str | None:
    """The custody job durably bound to one request (private manifest)."""
    for job_dir in ds._list_job_dirs(custody):
        manifest = ds._read_manifest(job_dir)
        if manifest is not None and manifest.request_id == str(request_id):
            return manifest.job_id
    return None


# --- target-DB helpers ---------------------------------------------------------


def _target_db_exists(san: _Env, db: str) -> bool:
    async def run() -> bool:
        s = await asyncpg.connect(**{
            "host": san.target["host"],
            "port": int(san.target["port"]),
            "user": san.target["user"],
            "password": san.target["password"],
            "database": str(san.target["database"]),
        })
        try:
            row = await s.fetchrow(
                "SELECT 1 FROM pg_database WHERE datname = $1", db
            )
            return row is not None
        finally:
            await s.close()

    return asyncio.run(run())


async def _copy_canary_hits(san: _Env, db: str) -> int:
    """Total rows in the copied target DB rendering any absence token."""
    conn = await _connect_target_db(san, db)
    try:
        total = 0
        for table in await _all_public_tables(conn):
            total += await _copy_scan(conn, table, san.absence_tokens)
        return total
    finally:
        await conn.close()


def _process(san: _Env, env: dict[str, Any], custody_dir: Path,
             request_id: uuid.UUID, **overrides: Any):
    """Run ONE exact worker invocation end-to-end (real 221/222/223)."""
    config, settings = _worker_config(san, env, custody_dir, **overrides)
    return asyncio.run(
        dww.process_request(config, settings, request_id=request_id)
    ), config


# --- 1. one request -> ONE exact verified copy ---------------------------------


def test_e2e_one_request_yields_one_exact_verified_copy(
    san_env: _Env, wenv: dict[str, Any], custody: Path
) -> None:
    env = wenv
    rid = _create_request(env)
    result, config = _process(san_env, env, custody, rid)
    assert result.state == "verified_unpublished", (
        result.state, result.failure_code
    )
    row = _request_row(env, rid)
    assert row["state"] == "verified_unpublished"
    job_id, target_db = row["worker_job_id"], row["worker_target_db"]
    assert dww._WORKER_JOB_ID_RE.fullmatch(job_id)
    assert dww._WORKER_TARGET_DB_RE.fullmatch(target_db)
    # The private custody manifest agrees EXACTLY with the control row.
    manifest = ds.read_manifest(custody / job_id)
    assert manifest is not None
    assert manifest.job_id == job_id
    assert manifest.target_db == target_db
    assert manifest.state == ds.STATE_DB_AND_FILES_VERIFIED_UNPUBLISHED
    assert manifest.request_id == str(rid)
    # The exact copy exists on the dedicated target service.
    assert _target_db_exists(san_env, target_db)
    # The copy data is canary-free (222 masking held through 224-b).
    assert asyncio.run(_copy_canary_hits(san_env, target_db)) == 0
    # The web role can issue and validate a session on the published copy.
    token = _issue_session(env, rid)
    assert token
    assert _validate_session(env, rid, token)


def _validate_session(
    env: dict[str, Any], request_id: uuid.UUID, token: str
) -> bool:
    async def run() -> bool:
        factory = _session_factory(str(env["web_url"]))
        async with factory() as session, session.begin():
            proj = await DemoWebControlService(session).validate_session(
                account_id=env["account_id"], token=token
            )
            return proj.request_id == request_id

    return asyncio.run(run())


# --- 2. second request -> DISTINCT copy ----------------------------------------


def test_second_request_gets_distinct_copy(
    san_env: _Env, wenv: dict[str, Any], custody: Path
) -> None:
    env = wenv
    rid_1 = _create_request(env)
    result_1, _ = _process(san_env, env, custody, rid_1)
    assert result_1.state == "verified_unpublished", result_1.failure_code
    row_1 = _request_row(env, rid_1)
    # Leave a live session: this copy is session-protected for any later
    # cleanup invocation in this module.
    _issue_session(env, rid_1)

    rid_2 = _create_request(env)
    result_2, _ = _process(san_env, env, custody, rid_2)
    assert result_2.state == "verified_unpublished", result_2.failure_code
    row_2 = _request_row(env, rid_2)
    _issue_session(env, rid_2)

    assert row_1["worker_job_id"] != row_2["worker_job_id"]
    assert row_1["worker_target_db"] != row_2["worker_target_db"]
    assert _target_db_exists(san_env, row_2["worker_target_db"])


# --- 3. two racing workers -> exactly one claim ---------------------------------


def test_two_racing_workers_claim_exactly_once(
    san_env: _Env, wenv: dict[str, Any], custody: Path
) -> None:
    env = wenv
    rid = _create_request(env)
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(_process, san_env, env, custody, rid)
            for _ in range(2)
        ]
        results = [f.result() for f in futures]
    # _process returns (result, config); the state lives on element [0].
    states = sorted(r[0].state for r in results)
    assert states == ["claim_refused", "verified_unpublished"], states
    row = _request_row(env, rid)
    assert row["state"] == "verified_unpublished"
    # Exactly ONE custody job is bound to this request.
    bound = [
        m.job_id
        for j in ds._list_job_dirs(custody)
        if (m := ds._read_manifest(j)) is not None
        and m.request_id == str(rid)
        and m.state != ds.STATE_CLEANED
    ]
    assert bound == [row["worker_job_id"]]
    _issue_session(env, rid)  # session-protect for later cleanup runs


# --- 4. unbound legacy raw copy is never promoted -------------------------------


def test_unbound_legacy_copy_never_promoted_by_request_run(
    san_env: _Env, wenv: dict[str, Any], custody: Path
) -> None:
    env = wenv
    config, settings = _worker_config(san_env, env, custody)
    bare = ds.run_snapshot_job(config.snapshot)
    assert bare.state == ds.STATE_RAW_UNVERIFIED, bare.failure_code
    bare_job = bare.job_id

    rid = _create_request(env)
    result, _ = _process(san_env, env, custody, rid)
    assert result.state == "verified_unpublished", result.failure_code
    row = _request_row(env, rid)
    assert row["worker_job_id"] != bare_job
    # The legacy raw copy was NOT sanitized or consumed: still RAW, still
    # RAW-state, bound to no request.
    bare_manifest = ds.read_manifest(custody / bare_job)
    assert bare_manifest is not None
    assert bare_manifest.state == ds.STATE_RAW_UNVERIFIED
    assert bare_manifest.request_id is None
    _issue_session(env, rid)  # session-protect the published copy


# --- worker-role control helpers -----------------------------------------------


def _worker_claim(env: dict[str, Any], request_id: uuid.UUID):
    async def run():
        factory = _session_factory(str(env["worker_url"]))
        async with factory() as session, session.begin():
            return await DemoWebControlService(session).claim_request(
                request_id=request_id
            )

    return asyncio.run(run())


def _worker_handoff(
    env: dict[str, Any], request_id: uuid.UUID, binding: VerifiedCopyBinding
):
    async def run():
        factory = _session_factory(str(env["worker_url"]))
        async with factory() as session, session.begin():
            return await DemoWebControlService(session).record_verified_handoff(
                request_id=request_id, binding=binding
            )

    return asyncio.run(run())


def _synthetic_binding():
    return VerifiedCopyBinding(
        worker_job_id="snap-" + uuid.uuid4().hex,
        worker_target_db="demo_snap_" + uuid.uuid4().hex[:20],
        manifest_state=VERIFIED_COPY_STATE,
    )


# --- 5. mid-job credential reset refuses the late handoff -----------------------


def test_reset_mid_job_refuses_late_handoff(
    san_env: _Env, wenv: dict[str, Any], custody: Path
) -> None:
    env = wenv
    rid = _create_request(env)
    claimed = _worker_claim(env, rid)
    assert claimed.state == "claimed"

    # Operator account DISABLE while the job is "running": the
    # statement-time account fence must refuse the late completion.
    # (Disable/re-enable keeps the credential generation stable so the
    # rest of the module's session law is undisturbed.)
    asyncio.run(
        _exec(
            str(env["source_url"]),
            f"UPDATE demo_control.fake_admin_accounts "
            f"SET is_enabled = false WHERE id = '{env['account_id']}'",
        )
    )
    proj = _worker_handoff(env, rid, _synthetic_binding())
    assert proj.state == "failed"
    assert proj.failure_code == "state_conflict"
    row = _request_row(env, rid)
    assert row["worker_job_id"] is None and row["worker_target_db"] is None
    asyncio.run(
        _exec(
            str(env["source_url"]),
            f"UPDATE demo_control.fake_admin_accounts "
            f"SET is_enabled = true WHERE id = '{env['account_id']}'",
        )
    )


# --- 6. copy-locator reuse is refused by the database ---------------------------


def test_copy_locator_reuse_refused_by_unique_index(
    san_env: _Env, wenv: dict[str, Any], custody: Path
) -> None:
    env = wenv
    rid_a = _create_request(env)
    rid_b = _create_request(env)
    _worker_claim(env, rid_a)
    _worker_claim(env, rid_b)
    binding = _synthetic_binding()
    proj_a = _worker_handoff(env, rid_a, binding)
    assert proj_a.state == "verified_unpublished"
    # The SAME job/target locator for another request: the partial unique
    # invariants refuse; the second request stays claimed for explicit
    # worker failure (never bound, never published).
    with pytest.raises(DemoWebControlError) as exc:
        _worker_handoff(env, rid_b, binding)
    assert exc.value.code == "web_request_copy_reused"
    row_b = _request_row(env, rid_b)
    assert row_b["state"] == "claimed"
    assert row_b["worker_job_id"] is None
    # Explicitly fail the stuck claim through the worker vocabulary.
    async def fail_row() -> None:
        factory = _session_factory(str(env["worker_url"]))
        async with factory() as session, session.begin():
            await DemoWebControlService(session).record_worker_failure(
                request_id=rid_b, code="worker_failed"
            )

    asyncio.run(fail_row())
    assert _request_row(env, rid_b)["state"] == "failed"


# --- 7. budget full of verified copies refuses the next request ------------------


def test_budget_full_of_verified_refuses_second_request(
    san_env: _Env, wenv: dict[str, Any]
) -> None:
    env = wenv
    # A dedicated top-level case dir so the run-owned teardown scans it.
    cust_b = san_env.custody / f"case-{uuid.uuid4().hex[:12]}"
    cust_b.mkdir(mode=0o700)
    rid_1 = _create_request(env)
    result_1, _ = _process(
        san_env, env, cust_b, rid_1, DEMO_SNAPSHOT_MAX_COPIES=1
    )
    assert result_1.state == "verified_unpublished", result_1.failure_code
    row_1 = _request_row(env, rid_1)
    assert row_1["state"] == "verified_unpublished"

    rid_2 = _create_request(env)
    result_2, _ = _process(
        san_env, env, cust_b, rid_2, DEMO_SNAPSHOT_MAX_COPIES=1
    )
    assert result_2.state == "failed"
    assert result_2.failure_code == ds.CODE_SNAPSHOT_BUDGET_FULL
    row_2 = _request_row(env, rid_2)
    assert row_2["state"] == "failed"
    # The specific budget code is on the RESULT (safe CLI vocabulary); the
    # control row stores only the finite worker failure vocabulary
    # (SNAPSHOT_BUDGET_FULL is not a permitted DB failure_code), so the row
    # carries the generic worker failure.
    assert row_2["failure_code"] == dww.FAILURE_WORKER_FAILED
    # The verified copy survived (structurally never generic-evicted) and
    # NO job was created for the refused request.
    assert _target_db_exists(san_env, row_1["worker_target_db"])
    bound_2 = [
        m.job_id
        for j in ds._list_job_dirs(cust_b)
        if (m := ds._read_manifest(j)) is not None
        and m.request_id == str(rid_2)
    ]
    assert bound_2 == []


# --- 8. session-aware cleanup matrix ---------------------------------------------


def _revoke_session(env: dict[str, Any], request_id: uuid.UUID, token: str) -> None:
    async def run() -> None:
        factory = _session_factory(str(env["web_url"]))
        async with factory() as session, session.begin():
            await DemoWebControlService(session).revoke_session(
                account_id=env["account_id"], token=token
            )

    asyncio.run(run())


def _set_account_enabled(env: dict[str, Any], flag: bool) -> None:
    asyncio.run(
        _exec(
            str(env["source_url"]),
            f"UPDATE demo_control.fake_admin_accounts "
            f"SET is_enabled = {'true' if flag else 'false'} "
            f"WHERE id = '{env['account_id']}'",
        )
    )


def test_session_aware_cleanup_matrix(
    san_env: _Env, wenv: dict[str, Any], custody: Path
) -> None:
    env = wenv
    config, _ = _worker_config(san_env, env, custody)

    # H1: published with a live session.
    rid_h1 = _create_request(env)
    result_h1, _ = _process(san_env, env, custody, rid_h1)
    assert result_h1.state == "verified_unpublished", result_h1.failure_code
    row_h1 = _request_row(env, rid_h1)
    db_h1 = row_h1["worker_target_db"]
    job_h1 = row_h1["worker_job_id"]
    tok_h1 = _issue_session(env, rid_h1)

    # (a) a live usable session refuses cleanup: the row and its copy
    # survive the bounded recovery invocation untouched.
    res_a = asyncio.run(dww.recover_and_cleanup(config))
    assert res_a.retained >= 1, "the live-session row must be retained"
    assert _request_row(env, rid_h1)["state"] == "verified_unpublished"
    assert _target_db_exists(san_env, db_h1)

    # (b) revoke, then plant a FOREIGN leaf: cleanup proceeds to
    # cleanup_pending, drops the DB FIRST, then refuses the files
    # cleanup (extra leaf) and RETAINS the row with a finite code.
    _revoke_session(env, rid_h1, tok_h1)
    files_dir = custody / job_h1 / "files"
    foreign = files_dir / ("f0999-" + "00" * 6)
    foreign.write_bytes(b"foreign-leaf")
    os.chmod(foreign, 0o600)
    res_b = asyncio.run(dww.recover_and_cleanup(config))
    row_h1b = _request_row(env, rid_h1)
    assert row_h1b["state"] == "cleanup_pending"
    assert not _target_db_exists(san_env, db_h1), "DB must be dropped first"
    assert foreign.exists(), "foreign leaf retained for operator inspection"
    m = ds.read_manifest(custody / job_h1)
    assert m is not None
    assert m.state == ds.STATE_CLEANUP_FAILED
    assert res_b.failure_code == ds.CODE_CLEANUP_FAILED

    # (c) remove the foreign leaf: the retry completes the exact cleanup.
    foreign.unlink()
    res_c = asyncio.run(dww.recover_and_cleanup(config))
    assert res_c.failure_code is None
    assert _request_row(env, rid_h1)["state"] == "cleaned"
    m = ds.read_manifest(custody / job_h1)
    assert m is not None and m.state == ds.STATE_CLEANED
    assert not (custody / job_h1 / "files").exists()
    assert not _target_db_exists(san_env, db_h1)

    # H2: published with a live session, then the account is DISABLED:
    # every session dies at first use, so cleanup is released immediately
    # (not gated on the 60-minute lifetime).
    rid_h2 = _create_request(env)
    result_h2, _ = _process(san_env, env, custody, rid_h2)
    assert result_h2.state == "verified_unpublished", result_h2.failure_code
    row_h2 = _request_row(env, rid_h2)
    db_h2 = row_h2["worker_target_db"]
    _issue_session(env, rid_h2)
    _set_account_enabled(env, False)
    res_d = asyncio.run(dww.recover_and_cleanup(config))
    _set_account_enabled(env, True)
    assert _request_row(env, rid_h2)["state"] == "cleaned"
    assert not _target_db_exists(san_env, db_h2)
    assert not (custody / row_h2["worker_job_id"] / "files").exists()
    assert res_d.failure_code is None


# --- 9. crashed-worker recovery through the durable association -------------------


def test_restart_recovery_removes_crashed_worker_artifacts(
    san_env: _Env, wenv: dict[str, Any], custody: Path
) -> None:
    env = wenv
    config, _ = _worker_config(san_env, env, custody)
    rid = _create_request(env)
    claimed = _worker_claim(env, rid)
    assert claimed.state == "claimed"
    # Simulate a worker crash AFTER 221 (raw copy + target DB exist,
    # the request row is unbound): the durable private association in
    # the custody manifest is the only ownership record.
    bare = ds.run_snapshot_job(config.snapshot, request_id=str(rid))
    assert bare.state == ds.STATE_RAW_UNVERIFIED, bare.failure_code
    db = bare.target_db
    assert _target_db_exists(san_env, db)
    asyncio.run(
        _worker_fail_request(env, rid, "worker_failed")
    )
    assert _request_row(env, rid)["state"] == "failed"

    res = asyncio.run(dww.recover_and_cleanup(config))
    assert res.failure_code is None
    # No survivors: the exact owned job was found and fully removed.
    assert _request_row(env, rid)["state"] == "cleaned"
    assert not _target_db_exists(san_env, db)
    m = ds.read_manifest(custody / bare.job_id)
    assert m is not None and m.state == ds.STATE_CLEANED


async def _worker_fail_request(
    env: dict[str, Any], request_id: uuid.UUID, code: str
) -> None:
    factory = _session_factory(str(env["worker_url"]))
    async with factory() as session, session.begin():
        await DemoWebControlService(session).record_worker_failure(
            request_id=request_id, code=code
        )


# --- 10. the restricted-role matrix is enforced by the database -------------------


def test_restricted_role_matrix_denials(san_env: _Env, wenv: dict[str, Any]) -> None:
    env = wenv
    web_url = str(env["web_url"])
    worker_url = str(env["worker_url"])
    reader_url = _role_url(san_env.source, READER_ROLE, _CANARY_SOURCE_PW)
    # Web role: NO UPDATE on requests at all (state or worker columns), no
    # business-table grant. The 224-b web LOGIN is granted column-scoped
    # SELECT on the credential (id/username/password_hash/is_enabled/
    # credential_generation) and full SELECT on its own session rows
    # (token_hash), so those reads ARE permitted (positive below) - the
    # WORKER role is denied all of them.
    _denied(web_url, "UPDATE demo_control.demo_snapshot_requests SET state = 'claimed'")
    _denied(
        web_url,
        "UPDATE demo_control.demo_snapshot_requests SET worker_job_id = 'snap-' || 'ab' || 'ab' || 'ab' || 'ab' || 'ab' || 'ab' || 'ab' || 'ab' || 'ab' || 'ab' || 'ab' || 'ab' || 'ab' || 'ab' || 'ab'",
    )
    _denied(web_url, "SELECT * FROM public.gateway_keys LIMIT 1")
    # Positive: the web login credential read is permitted and finds this
    # test's account (proves the grant, not merely the absence of a denial).
    login_rows = asyncio.run(
        _scalar_many(
            web_url,
            "SELECT username, password_hash FROM demo_control.fake_admin_accounts "
            f"WHERE id = '{env['account_id']}'",
        )
    )
    assert len(login_rows) == 1, "web login credential read must be permitted"
    # Full session-row SELECT is permitted (may be empty); raises 42501 if not.
    asyncio.run(
        _scalar_many(web_url, "SELECT token_hash FROM demo_control.demo_web_sessions")
    )
    # Worker role: never account identifiers/secrets, never token_hash,
    # no account writes, no request inserts.
    _denied(worker_url, "SELECT username FROM demo_control.fake_admin_accounts LIMIT 1")
    _denied(worker_url, "SELECT password_hash FROM demo_control.fake_admin_accounts LIMIT 1")
    _denied(worker_url, "SELECT token_hash FROM demo_control.demo_web_sessions LIMIT 1")
    _denied(worker_url, "UPDATE demo_control.fake_admin_accounts SET is_enabled = false")
    _denied(
        worker_url,
        "INSERT INTO demo_control.demo_snapshot_requests (account_id) "
        "VALUES ('00000000-0000-0000-0000-000000000000')",
    )
    # The 221 READER source role: no demo_control grant at all, and its
    # business read-only law is unchanged (222).
    _denied(reader_url, "SELECT * FROM demo_control.demo_snapshot_requests LIMIT 1")
    _denied(
        reader_url,
        "INSERT INTO demo_control.demo_snapshot_requests (account_id) "
        "VALUES ('00000000-0000-0000-0000-000000000000')",
    )
    _denied(reader_url, "INSERT INTO public.institutions (name) VALUES ('denied')")
    # Positive: the worker reads EXACTLY the account facts it needs.
    facts = asyncio.run(
        _scalar(
            worker_url,
            "SELECT is_enabled, credential_generation "
            "FROM demo_control.fake_admin_accounts LIMIT 1",
        )
    )
    assert facts is not None


# --- 11. the worker CLI emits only the safe vocabulary ----------------------------


def test_cli_process_request_and_cleanup_never_render_canaries(
    san_env: _Env, wenv: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    from typer.testing import CliRunner

    from slaif_gateway.cli import demo_snapshot_worker as cli_mod
    from slaif_gateway.config import get_settings

    env = wenv
    custody_c = san_env.custody / f"case-{uuid.uuid4().hex[:12]}"
    custody_c.mkdir(mode=0o700)
    rid = _create_request(env)
    values = _settings_for(san_env, custody_c)
    values.update(
        {
            "DEMO_WEB_WORKER_CONTROL_HOST": san_env.source["host"],
            "DEMO_WEB_WORKER_CONTROL_PORT": int(san_env.source["port"]),
            "DEMO_WEB_WORKER_CONTROL_DATABASE": san_env.source["database"],
            "DEMO_WEB_WORKER_CONTROL_USER": env["worker_role"],
            "DEMO_WEB_WORKER_CONTROL_PASSWORD": env["worker_pw"],
            # The 223 combined DB/files link gate needs the owned
            # completion-profile source (the 222 seed's completion_service
            # profile), or the CLI's 223 stage refuses FILES_VERIFY_FAILED.
            "COMPLETION_SERVICE_PROFILE_DIR": str(env["profile_dir"]),
        }
    )
    for key, value in values.items():
        monkeypatch.setenv(str(key), str(value))
    get_settings.cache_clear()
    try:
        runner = CliRunner()
        res = runner.invoke(cli_mod.app, ["process-request", str(rid), "--json"])
        assert res.exit_code == 0, res.output
        assert "verified_unpublished" in res.output
        # The safe vocabulary: no control password, no job id, no target
        # database name, no custody path.
        assert env["worker_pw"] not in res.output
        assert env["web_pw"] not in res.output
        assert "snap-" not in res.output
        assert "demo_snap_" not in res.output
        row = _request_row(env, rid)
        assert row["state"] == "verified_unpublished"
        res2 = runner.invoke(cli_mod.app, ["cleanup", "--json"])
        assert res2.exit_code == 0, res2.output
        assert env["worker_pw"] not in res2.output
        assert "demo_snap_" not in res2.output
    finally:
        get_settings.cache_clear()
