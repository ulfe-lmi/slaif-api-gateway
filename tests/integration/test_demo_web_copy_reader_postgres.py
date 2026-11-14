"""Real owned-PostgreSQL-16 evidence for the objective 224-d verified
copy reader.

Runs on the same owned fixture pair as the 222/224-b/224-c evidence
(``san_env`` + function-scoped ``custody``) and reuses the 224-b
module's owned web/worker ROLES (``_wenv_base``) and the 224-c
module's known-credential account (``webenv``). This module adds ONE
function-scoped STATIC reader role on the target service (LOGIN, no
privilege bits, no memberships) with exact run-owned teardown.

Proves, against real PostgreSQL 16 with the REAL reader role:

- pre-grant denial: the reader CANNOT CONNECT to a raw (unverified)
  221 copy, so no unverified/DB-only/failed copy is ever readable;
- exact verified grant: after the real 221+222+223 chain the reader
  can SELECT on the bound copy, while INSERT/UPDATE/DELETE/CREATE and
  any source-cluster access are refused by the database;
- per-session copy isolation: two sessions read their OWN distinct
  copies (a marker row in one copy is invisible to the other);
- wrong-copy binding fails closed (a control row pointing at an
  ungranted copy renders the one safe note, never a connection);
- a grant failure (missing reader role) publishes NOTHING and the
  exact request-associated cleanup drops the bound target with no
  survivor;
- canary hygiene: no target name, DSN, credential or custody path in
  worker CLI output, preview HTML or control rows rendered to the
  browser; the source business data is byte-for-byte unchanged
  (counts) and no mail/provider effect occurs.

No provider HTTP, no Redis, no email. Synthetic data only; the demo
remains unusable from a browser beyond the entry surface plus the
read-only preview (full copy-backed GUI is a later suffix).
"""

from __future__ import annotations

import asyncio
import json
import re
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import asyncpg
import pytest
from httpx import ASGITransport, AsyncClient

from slaif_gateway.demo_web import (
    COPY_PREVIEW_TABLES,
    DemoWebConfig,
    PgDemoWebFacade,
    create_demo_app,
)
from tests.integration.test_demo_snapshot_sanitize_postgres import (
    _Env,
    _settings_for,
)
from tests.integration.test_demo_web_control_postgres import (
    _scalar_many,
)
from tests.integration.test_demo_web_postgres import (
    _parse_pending,
    _request_row,
    _run_worker_cli,
    _target_db_exists,
)

# Owned-PostgreSQL fixtures and the run-tagged web/worker roles by
# plugin registration (requested BY NAME; F811 avoidance). The known-
# credential account fixture (``webenv``) is likewise a plugin fixture.
pytest_plugins = (
    "tests.integration.test_demo_web_worker_postgres",
    "tests.integration.test_demo_web_postgres",
)


# --- function-scoped STATIC reader role on the target service -------------------


@pytest.fixture()
def readerenv(san_env: _Env) -> Iterator[dict[str, Any]]:
    """ONE static SELECT-only reader role (own password), run-owned.

    Teardown drops exactly the copy databases this test registered,
    then the role - nothing else on the owned target service.
    """
    target = san_env.target
    role = f"slaif224d_reader_{uuid.uuid4().hex[:8]}"
    pw = f"reader-pw-{uuid.uuid4().hex}"
    created: list[str] = []

    async def setup() -> None:
        s = await asyncpg.connect(
            host=str(target["host"]), port=int(target["port"]),
            user=str(target["user"]), password=str(target["password"]),
            database=str(target["database"]),
        )
        try:
            await s.execute(
                f"CREATE ROLE {role} LOGIN PASSWORD '{pw}' "
                "NOCREATEDB NOCREATEROLE"
            )
        finally:
            await s.close()

    asyncio.run(setup())
    try:
        yield {"role": role, "pw": pw, "created": created}
    finally:
        async def teardown() -> None:
            s = await asyncpg.connect(
                host=str(target["host"]), port=int(target["port"]),
                user=str(target["user"]), password=str(target["password"]),
                database=str(target["database"]),
            )
            try:
                for db in created:
                    await s.execute(
                        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                        "WHERE datname = $1 AND pid <> pg_backend_pid()", db
                    )
                    await s.execute(f'DROP DATABASE IF EXISTS "{db}"')
                await s.execute(f"DROP ROLE IF EXISTS {role}")
            finally:
                await s.close()

        asyncio.run(teardown())


def _reader_conn_kwargs(san: _Env, env: dict[str, Any], database: str) -> dict:
    return {
        "host": str(san.target["host"]),
        "port": int(san.target["port"]),
        "user": str(env["role"]),
        "password": str(env["pw"]),
        "database": database,
        "timeout": 10.0,
    }


def _web_config_d(env: dict[str, Any], reader: dict[str, Any],
                  san: _Env) -> DemoWebConfig:
    parsed = urlparse(str(env["source_url"]))
    return DemoWebConfig(
        enabled=True,
        control_host=parsed.hostname,
        control_port=parsed.port or 5432,
        control_database=parsed.path.lstrip("/"),
        control_user=str(env["web_role"]),
        control_password=str(env["web_pw"]),
        cookie_secret=f"pg-e2e-d-cookie-secret-{uuid.uuid4().hex}",
        copy_host=str(san.target["host"]),
        copy_port=int(san.target["port"]),
        copy_user=str(reader["role"]),
        copy_password=str(reader["pw"]),
    )


def _worker_cli_env_d(san: _Env, env: dict[str, Any], custody: Path,
                      reader: dict[str, Any]) -> dict[str, str]:
    values = _settings_for(san, custody)
    values.update(
        {
            "DEMO_WEB_WORKER_CONTROL_HOST": san.source["host"],
            "DEMO_WEB_WORKER_CONTROL_PORT": int(san.source["port"]),
            "DEMO_WEB_WORKER_CONTROL_DATABASE": san.source["database"],
            "DEMO_WEB_WORKER_CONTROL_USER": env["worker_role"],
            "DEMO_WEB_WORKER_CONTROL_PASSWORD": env["worker_pw"],
            "COMPLETION_SERVICE_PROFILE_DIR": str(env["profile_dir"]),
            "DEMO_SNAPSHOT_TARGET_READER_ROLE": reader["role"],
        }
    )
    return {str(k): str(v) for k, v in values.items()}


def _raw_copy_name(custody: Path) -> str:
    """The target name of the newest custody job manifest (test-owned)."""
    from slaif_gateway.services import demo_snapshot as ds

    best = None
    for job_dir in sorted(custody.iterdir()):
        if not job_dir.is_dir():
            continue
        manifest = ds.read_manifest(job_dir)
        if manifest is None:
            continue
        if best is None or manifest.created_at > best[0]:
            best = (manifest.created_at, manifest.target_db)
    assert best is not None, "no custody job manifest found"
    return best[1]


def _owners_count(html: str) -> int:
    m = re.search(r"<td>owners</td>\s*<td>(\d+)</td>", html)
    assert m is not None, f"owners count not rendered: {html[:400]}"
    return int(m.group(1))


async def _http_phase(cfg: DemoWebConfig, action, *args):
    """One web phase with its own facade (per-loop engine law)."""
    facade = PgDemoWebFacade(cfg)
    try:
        app = create_demo_app(cfg, facade=facade)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="https://demo.test"
        ) as client:
            return await action(client, *args)
    finally:
        await facade.close()


def _source_counts(san: _Env) -> dict[str, int]:
    async def run() -> dict[str, int]:
        out: dict[str, int] = {}
        for table in ("owners", "gateway_keys", "usage_ledger",
                      "email_deliveries", "audit_log", "provider_configs",
                      "model_routes", "pricing_rules"):
            rows = await _scalar_many(
                str(san.source["url"]), f"SELECT count(*) FROM {table}"
            )
            out[table] = int(rows[0]._mapping["count"])
        return out

    return asyncio.run(run())


def _canary_free(text_blob: str, env: dict[str, Any],
                 reader: dict[str, Any], names: list[str]) -> None:
    for value in (
        env["web_pw"], env["worker_pw"], reader["pw"],
        str(env["source_url"]), "postgresql+asyncpg",
    ):
        assert value not in text_blob, "credential/DSN leaked"
    for name in names:
        assert name not in text_blob, "copy name leaked"


# --- 1. full cycle: grant law, isolation, wrong copy, cleanup -------------------


def test_copy_reader_full_cycle(
    san_env: _Env, webenv: dict[str, Any], readerenv: dict[str, Any],
    custody: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    env, reader = webenv, readerenv
    san = san_env
    cfg = _web_config_d(env, reader, san)
    cli_env = _worker_cli_env_d(san, env, custody, reader)
    copy_names: list[str] = []
    base = _source_counts(san)

    # Step 1: pre-grant denial - the reader cannot CONNECT to a RAW
    # (unverified) copy, so nothing unverified is ever readable.
    output = _run_worker_cli(["run", "--json"], _settings_for(san, custody)
                             | {str(k): str(v) for k, v in cli_env.items()
                                if k.startswith("DEMO_WEB_WORKER")
                                or k == "COMPLETION_SERVICE_PROFILE_DIR"
                                or k == "DEMO_SNAPSHOT_TARGET_READER_ROLE"},
                             monkeypatch)
    assert "RAW_UNVERIFIED" in output
    raw_db = _raw_copy_name(custody)
    try:
        with pytest.raises(asyncpg.PostgresError) as denied:
            asyncio.run(
                _connect_close(_reader_conn_kwargs(san, reader, raw_db))
            )
        assert denied.value.sqlstate in ("42501", "28000", "28P01")
    finally:
        # The raw copy is NOT granted to the reader: drop it directly
        # (test-owned) and remove its custody dir.
        asyncio.run(_drop_copy(san, raw_db))
        import shutil

        for job_dir in custody.iterdir():
            if (
                job_dir.is_dir()
                and _manifest_target(job_dir) == raw_db
            ):
                shutil.rmtree(job_dir, ignore_errors=True)

    # Step 2: session 1 - real chain -> verified + granted -> preview.
    rid1, pending1 = asyncio.run(_login_phase(cfg, env))
    output1 = _run_worker_cli(["process-request", str(rid1), "--json"],
                              cli_env, monkeypatch)
    assert "verified_unpublished" in output1
    _canary_free(output1, env, reader, copy_names)
    target1 = _request_row(env, rid1)["worker_target_db"]
    assert isinstance(target1, str) and target1.startswith("demo_snap_")
    copy_names.append(target1)
    reader["created"].append(target1)
    assert _target_db_exists(san, target1)

    token1 = asyncio.run(_wait_phase(cfg, pending1))

    # Reader privileges on the bound copy: SELECT yes, DML/DDL no.
    async def privilege_law() -> None:
        s = await asyncpg.connect(**_reader_conn_kwargs(san, reader, target1))
        try:
            n = await s.fetchval("SELECT count(*) FROM owners")
            assert isinstance(n, int)
            for stmt in (
                "INSERT INTO owners (id, name, surname, email, is_active, "
                "created_at, updated_at) VALUES (gen_random_uuid(), 'x', 'y', "
                "'perm-probe@canary.invalid', true, now(), now())",
                "UPDATE owners SET name = name",
                "DELETE FROM owners WHERE id = (SELECT id FROM owners LIMIT 1)",
                "CREATE TABLE reader_probe (x int)",
            ):
                with pytest.raises(asyncpg.PostgresError) as denied:
                    await s.execute(stmt)
                assert denied.value.sqlstate == "42501"
        finally:
            await s.close()

    asyncio.run(privilege_law())
    # Reader has NO source-cluster access (control/business/provider
    # data unreachable).
    try:
        with pytest.raises(asyncpg.PostgresError) as denied:
            asyncio.run(
                _connect_close(
                    {
                        "host": str(san.source["host"]),
                        "port": int(san.source["port"]),
                        "user": reader["role"],
                        "password": reader["pw"],
                        "database": str(san.source["database"]),
                        "timeout": 10.0,
                    }
                )
            )
        assert denied.value.sqlstate in ("42501", "28000", "28P01")
    except AssertionError:
        raise

    async def preview1_first() -> str:
        async def action(client: AsyncClient) -> str:
            client.cookies.set("slaif_demo_session", token1, path="/")
            r = await client.get("/fakeadmin/copy-preview")
            assert r.status_code == 200
            assert r.headers.get("cache-control") == "no-store"
            for table in COPY_PREVIEW_TABLES:
                assert f"<td>{table}</td>" in r.text
            assert "not available right now" not in r.text
            _canary_free(r.text, env, reader, [target1])
            assert "postgresql" not in r.text.lower()
            return r.text

        return await _http_phase(cfg, action)

    html1 = asyncio.run(preview1_first())
    owners_before_marker = _owners_count(html1)

    # Step 3: session 2 - second distinct copy.
    rid2, pending2 = asyncio.run(_login_phase(cfg, env))
    assert rid2 != rid1
    output2 = _run_worker_cli(["process-request", str(rid2), "--json"],
                              cli_env, monkeypatch)
    assert "verified_unpublished" in output2
    _canary_free(output2, env, reader, copy_names + [target1])
    target2 = _request_row(env, rid2)["worker_target_db"]
    assert target2 != target1
    copy_names.append(target2)
    reader["created"].append(target2)
    token2 = asyncio.run(_wait_phase(cfg, pending2))

    # Per-copy marker: a row inserted into copy ONE (as target admin)
    # is visible to session one and NOT to session two.
    marker_email = f"224d-marker-{uuid.uuid4().hex}@canary.invalid"

    async def plant_marker() -> None:
        s = await asyncpg.connect(
            host=str(san.target["host"]), port=int(san.target["port"]),
            user=str(san.target["user"]), password=str(san.target["password"]),
            database=target1,
        )
        try:
            await s.execute(
                "INSERT INTO owners (id, name, surname, email, is_active, "
                "created_at, updated_at) VALUES (gen_random_uuid(), '224d', "
                f"'Marker', '{marker_email}', true, now(), now())"
            )
        finally:
            await s.close()

    asyncio.run(plant_marker())

    async def preview(client_session: str) -> str:
        async def action(client: AsyncClient) -> str:
            client.cookies.set("slaif_demo_session", client_session, path="/")
            r = await client.get("/fakeadmin/copy-preview")
            assert r.status_code == 200
            assert "not available right now" not in r.text
            return r.text

        return await _http_phase(cfg, action)

    html1b = asyncio.run(preview(token1))
    html2 = asyncio.run(preview(token2))
    assert _owners_count(html1b) == owners_before_marker + 1
    assert _owners_count(html2) == owners_before_marker  # distinct copy
    _canary_free(html1b + html2, env, reader, [target1, target2])

    # The web-role PROJECTION (the only control-row view browser-
    # facing code can consume) NEVER carries the private copy
    # locators, and its serialized form carries no canary.
    async def safe_projection_law() -> None:
        facade = PgDemoWebFacade(cfg)
        try:
            for rid in (rid1, rid2):
                safe = (await facade.get_request(rid)).to_safe_dict()
                assert "worker_job_id" not in safe
                assert "worker_target_db" not in safe
                _canary_free(
                    json.dumps(safe, sort_keys=True), env, reader, copy_names
                )
        finally:
            await facade.close()

    asyncio.run(safe_projection_law())

    # Step 4: wrong-copy binding fails closed.
    asyncio.run(
        _exec_point(
            str(env["source_url"]),
            "UPDATE demo_control.demo_snapshot_requests "
            "SET worker_target_db = :db WHERE id = :id",
            {"db": raw_db, "id": str(rid1)},
        )
    )

    async def preview_wrong() -> str:
        async def action(client: AsyncClient) -> str:
            client.cookies.set("slaif_demo_session", token1, path="/")
            r = await client.get("/fakeadmin/copy-preview")
            assert r.status_code == 200
            assert "not available right now" in r.text
            assert raw_db not in r.text
            return r.text

        return await _http_phase(cfg, action)

    asyncio.run(preview_wrong())
    asyncio.run(
        _exec_point(
            str(env["source_url"]),
            "UPDATE demo_control.demo_snapshot_requests "
            "SET worker_target_db = :db WHERE id = :id",
            {"db": target1, "id": str(rid1)},
        )
    )

    # Step 5: logout revokes; the preview bounces on the next use.
    async def logout1() -> None:
        async def action(client: AsyncClient) -> None:
            client.cookies.set("slaif_demo_session", token1, path="/")
            r = await client.get("/fakeadmin/ready")
            csrf = r.cookies["slaif_demo_csrf"]
            r = await client.post("/fakeadmin/logout", data={"csrf": csrf})
            assert r.status_code == 303

        await _http_phase(cfg, action)

        async def action2(client: AsyncClient) -> None:
            client.cookies.set("slaif_demo_session", token1, path="/")
            r = await client.get("/fakeadmin/copy-preview")
            assert r.status_code == 303
            assert r.headers["location"] == "/fakeadmin/login"

        await _http_phase(cfg, action2)

    asyncio.run(logout1())

    # Session 2 must be revoked too: the 224-a cleanup gate retains a
    # copy bound to a live, unexpired, still-usable session, so an
    # unlogged-out token2 would be a CORRECT refusal, not a failure.
    async def logout2() -> None:
        async def action(client: AsyncClient) -> None:
            client.cookies.set("slaif_demo_session", token2, path="/")
            r = await client.get("/fakeadmin/ready")
            csrf = r.cookies["slaif_demo_csrf"]
            r = await client.post("/fakeadmin/logout", data={"csrf": csrf})
            assert r.status_code == 303

        await _http_phase(cfg, action)

        async def action2(client: AsyncClient) -> None:
            client.cookies.set("slaif_demo_session", token2, path="/")
            r = await client.get("/fakeadmin/copy-preview")
            assert r.status_code == 303
            assert r.headers["location"] == "/fakeadmin/login"

        await _http_phase(cfg, action2)

    asyncio.run(logout2())

    # Step 6: exact cleanup drops BOTH bound copies; no survivor.
    out_clean = _run_worker_cli(["cleanup", "--json"], cli_env, monkeypatch)
    _canary_free(out_clean, env, reader, copy_names)
    for rid, target in ((rid1, target1), (rid2, target2)):
        assert _request_row(env, rid)["state"] == "cleaned"
        assert not _target_db_exists(san, target)
    # The reader can no longer connect to a dropped copy.
    with pytest.raises(asyncpg.PostgresError) as denied:
        asyncio.run(_connect_close(_reader_conn_kwargs(san, reader, target1)))
    assert denied.value.sqlstate in ("3D000", "42501")

    # Step 7: source invariance - no business row, mail or provider
    # effect from the whole chain.
    after = _source_counts(san)
    for table in base:
        # The seeded fake-admin account lives in demo_control (a
        # separate schema), so every counted source table must be
        # EXACTLY invariant, not merely non-decreasing.
        assert after[table] == base[table], table


# --- 2. grant failure: nothing published, exact cleanup, no survivor ------------


def test_grant_failure_no_publication_exact_cleanup(
    san_env: _Env, webenv: dict[str, Any], readerenv: dict[str, Any],
    custody: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    env, reader = webenv, readerenv
    san = san_env
    cfg = _web_config_d(env, reader, san)
    # The worker is pointed at a role that does NOT exist: the role
    # law precheck fails closed before any grant.
    cli_env = _worker_cli_env_d(san, env, custody, reader)
    cli_env["DEMO_SNAPSHOT_TARGET_READER_ROLE"] = (
        f"slaif224d_missing_{uuid.uuid4().hex[:8]}"
    )

    rid, pending = asyncio.run(_login_phase(cfg, env))
    output = _run_worker_cli(["process-request", str(rid), "--json"],
                             cli_env, monkeypatch)
    assert "WEB_READER_GRANT_FAILED" in output
    assert "verified_unpublished" not in output

    row = _request_row(env, rid)
    assert row["state"] == "failed"
    # The copy was created (221) but NEVER bound/published: no session
    # exists, and the wait surface reports the terminal failed state.
    sessions = asyncio.run(
        _scalar_many(
            str(env["source_url"]),
            "SELECT count(*) FROM demo_control.demo_web_sessions "
            "WHERE request_id = :id",
            {"id": str(rid)},
        )
    )
    assert int(sessions[0]._mapping["count"]) == 0

    # The granted-lookalike copy: find it in the private custody
    # (test-owned) and prove the reader CANNOT connect (no grant was
    # ever applied), then the exact cleanup drops it.
    target = _raw_copy_name(custody)
    reader["created"].append(target)
    try:
        with pytest.raises(asyncpg.PostgresError) as denied:
            asyncio.run(_connect_close(_reader_conn_kwargs(san, reader, target)))
        assert denied.value.sqlstate in ("42501", "28000", "28P01")
    finally:
        pass

    out_clean = _run_worker_cli(["cleanup", "--json"], cli_env, monkeypatch)
    assert target not in out_clean
    row = _request_row(env, rid)
    assert row["state"] == "cleaned"
    assert not _target_db_exists(san, target)


# --- 3. schema-grant failure rolls back the whole grant transaction ---------------


def test_schema_grant_failure_rolls_back_connect(
    san_env: _Env, webenv: dict[str, Any], readerenv: dict[str, Any],
    custody: Path,
) -> None:
    """The role law PASSES but a later schema grant fails: the whole
    transaction (including the already-issued CONNECT) must roll back,
    so no partial grant can ever make a malformed copy readable.

    Built on the REAL grant step against an exact disposable database
    whose ``public`` schema was removed: ``GRANT CONNECT`` succeeds,
    the next ``GRANT USAGE ON SCHEMA public`` fails, ON_ERROR_STOP
    aborts the statement list and the open transaction rolls back.
    """
    env, reader = webenv, readerenv
    san = san_env

    # Exact worker copy-name grammar, as the 221 stage would create it.
    db = f"demo_snap_{uuid.uuid4().hex[:20]}"
    reader["created"].append(db)
    admin = {
        "host": str(san.target["host"]), "port": int(san.target["port"]),
        "user": str(san.target["user"]), "password": str(san.target["password"]),
        "database": str(san.target["database"]),
    }
    try:
        async def prepare() -> None:
            s = await asyncpg.connect(**admin)
            try:
                # Mirror the 221 copy-creation ACL law exactly: PUBLIC
                # loses CONNECT, only the target admin may connect.
                await s.execute(f'CREATE DATABASE "{db}"')
                await s.execute(
                    f'REVOKE CONNECT ON DATABASE "{db}" FROM PUBLIC'
                )
            finally:
                await s.close()
            s2 = await asyncpg.connect(**{**admin, "database": db})
            try:
                await s2.execute("DROP SCHEMA public")
            finally:
                await s2.close()

        asyncio.run(prepare())

        from slaif_gateway.config import Settings
        from slaif_gateway.services import demo_web_worker as dww

        settings = Settings(**_worker_cli_env_d(san, env, custody, reader))
        config = dww.web_worker_config_from_settings(settings)
        with pytest.raises(dww.DemoWebWorkerError) as exc:
            dww._grant_target_reader(config, db)
        assert exc.value.code == dww.CODE_READER_GRANT_FAILED

        # No partial CONNECT survived: zero shared-catalog grant
        # entries for (this reader role, this exact database).
        async def check_rolled_back() -> None:
            s = await asyncpg.connect(**admin)
            try:
                n = await s.fetchval(
                    "SELECT count(*) FROM pg_shdepend sh "
                    "JOIN pg_database d ON d.oid = sh.objid "
                    "WHERE sh.classid = 'pg_database'::regclass "
                    "AND sh.refclassid = 'pg_authid'::regclass "
                    "AND sh.refobjid = (SELECT oid FROM pg_roles "
                    "WHERE rolname = $1) AND d.datname = $2",
                    str(reader["role"]),
                    db,
                )
                assert n == 0, "partial CONNECT grant survived the rollback"
            finally:
                await s.close()

        asyncio.run(check_rolled_back())

        # Behavioral proof: the reader cannot connect AT ALL.
        with pytest.raises(asyncpg.PostgresError) as denied:
            asyncio.run(_connect_close(_reader_conn_kwargs(san, reader, db)))
        assert denied.value.sqlstate in ("42501", "3D000")
    finally:
        asyncio.run(_drop_copy(san, db))


# --- small async helpers ----------------------------------------------------------


async def _connect_close(kwargs: dict) -> None:
    s = await asyncpg.connect(**kwargs)
    await s.close()


async def _drop_copy(san: _Env, db: str) -> None:
    s = await asyncpg.connect(
        host=str(san.target["host"]), port=int(san.target["port"]),
        user=str(san.target["user"]), password=str(san.target["password"]),
        database=str(san.target["database"]),
    )
    try:
        await s.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE datname = $1 AND pid <> pg_backend_pid()", db
        )
        await s.execute(f'DROP DATABASE IF EXISTS "{db}"')
    finally:
        await s.close()


def _manifest_target(job_dir: Path) -> str | None:
    from slaif_gateway.services import demo_snapshot as ds

    manifest = ds.read_manifest(job_dir)
    return manifest.target_db if manifest is not None else None


async def _exec_point(url: str, sql: str, params: dict[str, Any]) -> None:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(url, future=True)
    try:
        async with engine.begin() as conn:
            await conn.execute(text(sql), params)
    finally:
        await engine.dispose()


async def _login_phase(cfg: DemoWebConfig, env: dict[str, Any]):
    async def action(client: AsyncClient):
        r = await client.get("/fakeadmin/login")
        csrf = r.cookies["slaif_demo_csrf"]
        r = await client.post(
            "/fakeadmin/login",
            data={
                "username": env["username"],
                "password": env["password"],
                "csrf": csrf,
            },
        )
        assert r.status_code == 303, r.text
        return _parse_pending(cfg.cookie_secret, r.cookies["slaif_demo_pending"]), r.cookies["slaif_demo_pending"]

    return await _http_phase(cfg, action)


async def _wait_phase(cfg: DemoWebConfig, pending: str) -> str:
    async def action(client: AsyncClient) -> str:
        client.cookies.set(
            "slaif_demo_pending", pending, domain="demo.test", path="/fakeadmin"
        )
        r = await client.get("/fakeadmin/wait/status")
        assert r.json() == {"state": "ready"}
        r = await client.get("/fakeadmin/wait")
        assert r.status_code == 303
        token = client.cookies.get("slaif_demo_session")
        assert token
        return token

    return await _http_phase(cfg, action)
