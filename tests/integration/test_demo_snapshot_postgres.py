"""PostgreSQL integration tests for the bounded private demo snapshot worker.

Requires TWO owned, loopback-only PostgreSQL 16 services (source business
database + separate target service), configured via:

    DEMO_SNAP_TEST_SOURCE_URL=postgresql+asyncpg://user:pw@127.0.0.1:PORT/slaif_gateway_test
    DEMO_SNAP_TEST_TARGET_URL=postgresql+asyncpg://user:pw@127.0.0.1:PORT2/postgres

Both URLs must be 127.0.0.1 loopback with the exact allowlisted database
names; anything else skips. Synthetic canary credentials only; no ambient
DATABASE_URL, production data, provider or mail access is used.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import re
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import asyncpg
import pytest

from slaif_gateway.config import Settings
from slaif_gateway.services import demo_snapshot as ds
from slaif_gateway.services.demo_snapshot import (
    CODE_SOURCE_DUMP_CAP_BYTES,
    CODE_SOURCE_DUMP_CAP_ELAPSED,
    CODE_SOURCE_DUMP_CANCELLED,
    CODE_TARGET_NOT_SEPARATE,
    CODE_TARGET_CREATE_FAILED,
    STATE_CLEANED,
    STATE_FAILED,
    STATE_RAW_UNVERIFIED,
    STATE_RUNNING,
)
from tests.integration.db_test_utils import run_alembic_upgrade_head

_ALLOWED_SOURCE_DB = "slaif_gateway_test"
_ALLOWED_TARGET_DB = "postgres"
_ALLOWED_HOST = "127.0.0.1"

_CANARY_SOURCE_PW = "canary-src-pw-221-9f3ab1"
_CANARY_WEB_PW = "canary-web-pw-221-b44f02"
_CANARY_NOCREATE_PW = "canary-nocreate-pw-221-51aa07"

# Run-owned role names: this test process generates them and drops exactly
# these on teardown. No fixed shared names, no global drops of roles this
# run did not create.
_RUN_TAG = uuid.uuid4().hex[:8]
READER_ROLE = f"demo_snap_reader_{_RUN_TAG}"
WEB_ROLE = f"demo_snap_web_{_RUN_TAG}"
NOCREATE_ROLE = f"demo_snap_nocreate_{_RUN_TAG}"

# Tables the concurrent writer does NOT touch: they must be byte-identical
# before and after a live export. (institutions is the written table and
# is therefore not part of the non-mutation fingerprint.)
_FINGERPRINT_TABLES = (
    "owners",
    "gateway_keys",
    "usage_ledger",
    "quota_reservations",
)


# Conservative identifier check before any teardown interpolation.
_TEARDOWN_IDENT_RE = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")


def _recorded_target_dbs(custody_root: Path) -> set[str]:
    """Exact target_db names recorded in THIS fixture's custody manifests.

    Teardown may drop only these names: they were created by this run's
    jobs, so this is run ownership, not a prefix or owner match.
    """
    names: set[str] = set()
    for case_dir in sorted(custody_root.iterdir()):
        if case_dir.is_symlink() or not case_dir.is_dir():
            continue
        for job_dir in ds._list_job_dirs(case_dir):
            manifest = ds._read_manifest(job_dir)
            if manifest is not None and manifest.target_db:
                names.add(manifest.target_db)
    return names


async def _target_db_names(t: asyncpg.Connection) -> set[str]:
    return {row["datname"] for row in await t.fetch("SELECT datname FROM pg_database")}


def _parse_test_url(name: str, allowed_db: str) -> dict[str, object] | None:
    raw = os.getenv(name, "")
    if not raw:
        return None
    parsed = urlparse(raw)
    db_name = (parsed.path or "").lstrip("/").lower()
    if parsed.scheme != "postgresql+asyncpg" or parsed.hostname != _ALLOWED_HOST:
        return None
    if db_name != allowed_db:
        return None
    return {
        "host": parsed.hostname,
        "port": parsed.port,
        "user": parsed.username,
        "password": parsed.password,
        "database": db_name,
        "url": raw,
    }


def _require_pg_tools() -> None:
    for tool in ("pg_dump", "pg_restore", "psql"):
        if shutil.which(tool) is None:
            pytest.skip(f"PostgreSQL client tooling ({tool}) is unavailable in this environment")


@dataclass(slots=True)
class _Env:
    source: dict[str, object]
    target: dict[str, object]
    custody: Path
    passfile: Path

    @property
    def canaries(self) -> list[str]:
        return [
            _CANARY_SOURCE_PW,
            str(self.target["password"]),
            _CANARY_WEB_PW,
            _CANARY_NOCREATE_PW,
        ]


def _settings_for(env: _Env, custody: Path, **overrides) -> Settings:
    base: dict[str, object] = {
        "DEMO_SNAPSHOT_ENABLED": True,
        "DEMO_SNAPSHOT_SOURCE_HOST": env.source["host"],
        "DEMO_SNAPSHOT_SOURCE_PORT": env.source["port"],
        "DEMO_SNAPSHOT_SOURCE_DATABASE": env.source["database"],
        "DEMO_SNAPSHOT_SOURCE_USER": READER_ROLE,
        "DEMO_SNAPSHOT_TARGET_HOST": env.target["host"],
        "DEMO_SNAPSHOT_TARGET_PORT": env.target["port"],
        "DEMO_SNAPSHOT_TARGET_USER": env.target["user"],
        "DEMO_SNAPSHOT_PGPASSFILE": str(env.passfile),
        "DEMO_SNAPSHOT_CUSTODY_DIR": str(custody),
        "DEMO_SNAPSHOT_MAX_EXPORT_BYTES": 512 * 1024 * 1024,
        "DEMO_SNAPSHOT_MAX_ELAPSED_SECONDS": 120,
        "DEMO_SNAPSHOT_RETENTION_SECONDS": 3600,
        "DEMO_SNAPSHOT_MAX_COPIES": 8,
    }
    base.update(overrides)
    return Settings(**base)


def _config_for(env: _Env, custody: Path, **overrides) -> ds.DemoSnapshotConfig:
    return ds.config_from_settings(_settings_for(env, custody, **overrides))


async def _connect(url: dict[str, object]) -> asyncpg.Connection:
    return await asyncpg.connect(
        host=str(url["host"]),
        port=int(url["port"]),
        user=str(url["user"]),
        password=str(url["password"]),
        database=str(url["database"]),
    )


async def _table_fingerprint(conn: asyncpg.Connection, table: str) -> str:
    row = await conn.fetchrow(
        f"SELECT count(*) AS n, md5(coalesce(string_agg(t, '|' ORDER BY t), '')) AS h "
        f"FROM (SELECT row_to_json(x)::text AS t FROM {table} x) z"
    )
    return f"{row['n']}:{row['h']}"


async def _source_fingerprints(source: dict[str, object]) -> dict[str, str]:
    conn = await asyncpg.connect(
        host=str(source["host"]),
        port=int(source["port"]),
        user=str(source["user"]),
        password=str(source["password"]),
        database=str(source["database"]),
    )
    try:
        return {table: await _table_fingerprint(conn, table) for table in _FINGERPRINT_TABLES}
    finally:
        await conn.close()


def _new_custody(tmp_path: Path, name: str) -> Path:
    custody = tmp_path / name
    custody.mkdir(mode=0o700)
    return custody


def _raw_jobs(config: ds.DemoSnapshotConfig) -> list[ds.SnapshotManifest]:
    result = []
    for job_dir in ds._list_job_dirs(config.custody_dir):
        manifest = ds._read_manifest(job_dir)
        if manifest is not None and manifest.state == STATE_RAW_UNVERIFIED:
            result.append(manifest)
    return result


@pytest.fixture(scope="module")
def snap_env(tmp_path_factory: pytest.TempPathFactory) -> _Env:
    source = _parse_test_url("DEMO_SNAP_TEST_SOURCE_URL", _ALLOWED_SOURCE_DB)
    target = _parse_test_url("DEMO_SNAP_TEST_TARGET_URL", _ALLOWED_TARGET_DB)
    if source is None or target is None:
        pytest.skip(
            "DEMO_SNAP_TEST_SOURCE_URL / DEMO_SNAP_TEST_TARGET_URL must be owned "
            "127.0.0.1 PostgreSQL 16 test URLs with the allowlisted database names"
        )
    _require_pg_tools()

    tmp_root = tmp_path_factory.mktemp("demo_snapshot")
    custody_root = tmp_root / "custody"
    custody_root.mkdir(mode=0o700)

    passfile = tmp_root / "pgpass"
    passfile.write_text(
        f"{source['host']}:{source['port']}:{source['database']}:{READER_ROLE}:{_CANARY_SOURCE_PW}\n"
        f"{target['host']}:{target['port']}:*:{target['user']}:{target['password']}\n"
        f"{target['host']}:{target['port']}:*:{NOCREATE_ROLE}:{_CANARY_NOCREATE_PW}\n",
        encoding="utf-8",
    )
    os.chmod(passfile, 0o600)

    async def setup() -> None:
        s = await _connect(source)
        try:
            # Run-owned unique names: the IF EXISTS guard only ever matches
            # a name THIS run generated (same-process rerun), never an
            # unrelated role.
            for role in (READER_ROLE, WEB_ROLE, NOCREATE_ROLE):
                await s.execute(f'DROP ROLE IF EXISTS "{role}"')
            await s.execute(f'CREATE ROLE "{READER_ROLE}" LOGIN PASSWORD \'{_CANARY_SOURCE_PW}\'')
            await s.execute(f'CREATE ROLE "{WEB_ROLE}" LOGIN PASSWORD \'{_CANARY_WEB_PW}\'')
            await s.execute(
                f'CREATE ROLE "{NOCREATE_ROLE}" LOGIN PASSWORD \'{_CANARY_NOCREATE_PW}\' NOCREATEDB'
            )
            await s.execute(f'GRANT USAGE ON SCHEMA public TO "{READER_ROLE}"')
            await s.execute(f'GRANT SELECT ON ALL TABLES IN SCHEMA public TO "{READER_ROLE}"')
            # Hermetic for THIS run only: remove rows from a same-process
            # rerun carrying this exact run tag. No broad prefix is ever
            # deleted, so unrelated fixture or operator rows are untouched.
            await s.execute(
                "DELETE FROM institutions WHERE name LIKE $1",
                f"snapseq-{_RUN_TAG}-%",
            )
        finally:
            await s.close()

        # Target must be a dedicated separate service.
        t = await _connect(target)
        try:
            rows = await t.fetch("SELECT datname FROM pg_database")
            datnames = {row["datname"] for row in rows}
            allowed = {"postgres", "template0", "template1"}
            # Fail closed: the target service must be DEDICATED and contain
            # no non-system database before this run. This run never drops
            # a database it did not create and record itself.
            foreign = datnames - allowed
            assert not foreign, (
                "target service must be dedicated and contain no "
                "non-system databases before the test run"
            )
            tables = await t.fetch(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
            )
            assert not tables, "target postgres db must be a dedicated service without business tables"
            # Run-owned target roles: the web role must exist on the
            # target so CONNECT denials are genuine privilege denials
            # (not authentication failures), and the NOCREATEDB role must
            # exist so CREATE DATABASE failures test the privilege, not
            # role absence. Both are dropped by the target teardown path.
            for role in (WEB_ROLE, NOCREATE_ROLE):
                await t.execute(f'DROP ROLE IF EXISTS "{role}"')
            await t.execute(
                f'CREATE ROLE "{WEB_ROLE}" LOGIN PASSWORD \'{_CANARY_WEB_PW}\' NOCREATEDB'
            )
            await t.execute(
                f'CREATE ROLE "{NOCREATE_ROLE}" LOGIN PASSWORD \'{_CANARY_NOCREATE_PW}\' NOCREATEDB'
            )
        finally:
            await t.close()

    # Source: migrate to head (sync Alembic; must run OUTSIDE any loop).
    run_alembic_upgrade_head(str(source["url"]))
    # Role grants (inside setup) depend on the migrated business tables.
    asyncio.run(setup())

    env = _Env(
        source=source,
        target=target,
        custody=custody_root,
        passfile=passfile,
    )
    yield env

    # Teardown: exact run-ownership cleanup in INDEPENDENT paths, so a
    # failure in one (e.g. a role-privilege dependency) cannot skip the
    # others. Only exact manifest-recorded database names are dropped.
    # Cleanup failures are surfaced in the test evidence, never swallowed.
    def teardown() -> None:
        failures: list[str] = []

        async def drop_recorded_dbs() -> None:
            t = await _connect(target)
            try:
                for name in sorted(_recorded_target_dbs(custody_root)):
                    if not _TEARDOWN_IDENT_RE.fullmatch(name):
                        continue
                    await t.execute(
                        f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'
                    )
            finally:
                await t.close()

        async def drop_roles_and_rows() -> None:
            s = await _connect(source)
            try:
                for role in (READER_ROLE, WEB_ROLE, NOCREATE_ROLE):
                    # Privilege grants are DROP ROLE dependencies: revoke
                    # first, then drop exactly the run-owned roles.
                    await s.execute(
                        f'REVOKE ALL ON ALL TABLES IN SCHEMA public FROM "{role}"'
                    )
                    await s.execute(
                        f'REVOKE USAGE ON SCHEMA public FROM "{role}"'
                    )
                    await s.execute(f'DROP ROLE IF EXISTS "{role}"')
                await s.execute(
                    "DELETE FROM institutions WHERE name LIKE $1",
                    f"snapseq-{_RUN_TAG}-%",
                )
            finally:
                await s.close()

        async def drop_target_roles() -> None:
            t = await _connect(target)
            try:
                for role in (WEB_ROLE, NOCREATE_ROLE):
                    await t.execute(f'DROP ROLE IF EXISTS "{role}"')
            finally:
                await t.close()

        try:
            asyncio.run(drop_recorded_dbs())
        except Exception as exc:
            failures.append(f"target-database cleanup: {exc!r}")
        try:
            asyncio.run(drop_target_roles())
        except Exception as exc:
            failures.append(f"target role cleanup: {exc!r}")
        try:
            asyncio.run(drop_roles_and_rows())
        except Exception as exc:
            failures.append(f"source role/row cleanup: {exc!r}")
        if failures:
            pytest.fail(
                "221 fixture cleanup incomplete: " + "; ".join(failures)
            )

    teardown()


@pytest.fixture()
def custody(snap_env: _Env, tmp_path: Path) -> Path:
    return _new_custody(snap_env.custody, f"case-{uuid.uuid4().hex[:12]}")


def _writer_loop(
    source: dict[str, object],
    stop: threading.Event,
    counter: dict[str, int],
    committed: list[float],
) -> None:
    """Insert a new fictional institution row on a tight loop until stopped.

    ``committed`` collects the wall-clock commit time of every insert so
    a test can prove writes landed strictly inside the capture window.
    """

    def run() -> None:
        async def pump() -> None:
            conn = await _connect(source)
            try:
                while not stop.is_set():
                    row_id = uuid.uuid4()
                    counter["n"] += 1
                    await conn.execute(
                        "INSERT INTO institutions "
                        "(id, name, country, notes, created_at, updated_at) "
                        "VALUES ($1, $2, 'SI', '221 synthetic fixture', NOW(), NOW())",
                        row_id,
                        f"snapseq-{_RUN_TAG}-{counter['n']}",
                    )
                    committed.append(time.time())
                    await asyncio.sleep(0.005)
            finally:
                await conn.close()

        asyncio.run(pump())

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return thread


async def _target_rows(snap_env: _Env, target_db: str) -> list[dict[str, object]]:
    conn = await asyncpg.connect(
        host=str(snap_env.target["host"]),
        port=int(snap_env.target["port"]),
        user=str(snap_env.target["user"]),
        password=str(snap_env.target["password"]),
        database=target_db,
    )
    try:
        rows = await conn.fetch(
            "SELECT id, name FROM institutions ORDER BY name"
        )
        return [dict(row) for row in rows]
    finally:
        await conn.close()


async def _db_exists(snap_env: _Env, target_db: str) -> bool:
    conn = await _connect(snap_env.target)
    try:
        row = await conn.fetchrow("SELECT 1 FROM pg_database WHERE datname = $1", target_db)
        return row is not None
    finally:
        await conn.close()


# ---------------------------------------------------------------------------
# Happy path: one consistent export under concurrent writes
# ---------------------------------------------------------------------------


def test_full_snapshot_consistent_under_concurrent_writes(snap_env: _Env, custody: Path) -> None:
    config = _config_for(snap_env, custody)
    stop = threading.Event()
    counter: dict[str, int] = {"n": 0}
    committed: list[float] = []
    writer = _writer_loop(snap_env.source, stop, counter, committed)
    time.sleep(1.0)  # let a handful of rows land

    # The writer KEEPS COMMITTING while the dump runs: this is a real
    # concurrent snapshot, not a quiesced one.
    before = asyncio.run(_source_fingerprints(snap_env.source))
    result = ds.run_snapshot_job(config)
    after = asyncio.run(_source_fingerprints(snap_env.source))

    assert result.state == STATE_RAW_UNVERIFIED, result.failure_code
    assert result.export_bytes > 0
    assert asyncio.run(_db_exists(snap_env, result.target_db)) is True

    # The export must not have modified the source in any way.
    assert before == after

    # Prove the concurrency precisely: at least one writer commit landed
    # strictly INSIDE the recorded capture window (not merely during the
    # later restore phase).
    job_dir = next(p for p in custody.iterdir() if p.is_dir())
    manifest = ds._read_manifest(job_dir)
    assert manifest is not None
    assert manifest.capture_started_at is not None
    assert manifest.capture_finished_at is not None
    in_window = [
        t for t in committed
        if manifest.capture_started_at < t < manifest.capture_finished_at
    ]
    assert in_window, "writer must commit strictly within the capture window"

    stop.set()
    writer.join(timeout=10)
    assert not writer.is_alive()

    rows = asyncio.run(_target_rows(snap_env, result.target_db))
    seqs = sorted(
        int(str(row["name"]).rsplit("-", 1)[1])
        for row in rows
        if str(row["name"]).startswith(f"snapseq-{_RUN_TAG}-")
    )
    assert seqs, "writer rows must be present in the copy"
    # One consistent snapshot: a gapless prefix of the writer sequence.
    assert seqs == list(range(1, max(seqs) + 1)), "copy must be a gapless consistent prefix"


def test_demo_control_excluded_and_unreadable(snap_env: _Env, custody: Path) -> None:
    config = _config_for(snap_env, custody)
    result = ds.run_snapshot_job(config)
    assert result.state == STATE_RAW_UNVERIFIED, result.failure_code

    async def checks() -> tuple[bool, bool, bool, set[str]]:
        conn = await asyncpg.connect(
            host=str(snap_env.target["host"]),
            port=int(snap_env.target["port"]),
            user=str(snap_env.target["user"]),
            password=str(snap_env.target["password"]),
            database=result.target_db,
        )
        demo_present = await conn.fetchval(
            "SELECT to_regclass('demo_control.fake_admin_accounts') IS NOT NULL"
        )
        exts = {
            row["extname"]
            for row in await conn.fetch("SELECT extname FROM pg_extension")
        }
        await conn.close()

        reader = await asyncpg.connect(
            host=str(snap_env.source["host"]),
            port=int(snap_env.source["port"]),
            user=READER_ROLE,
            password=_CANARY_SOURCE_PW,
            database=str(snap_env.source["database"]),
        )
        try:
            try:
                await reader.fetch(
                    "SELECT count(*) AS n FROM demo_control.fake_admin_accounts"
                )
                demo_read = True
            except asyncpg.exceptions.InsufficientPrivilegeError:
                demo_read = False
            business_ok = bool(
                await reader.fetchval("SELECT count(*) >= 0 FROM institutions")
            )
        finally:
            await reader.close()
        return bool(demo_present), demo_read, bool(business_ok), exts

    demo_present, demo_read, business_ok, exts = asyncio.run(checks())
    assert demo_present is False, "demo_control must be excluded from the raw copy"
    assert demo_read is False, "the SELECT-only source role must not read demo accounts"
    assert business_ok is True, "the SELECT-only source role must read business tables"
    # The fixed approved extension set (migration 0001) travels inside the
    # archive and must be restored into the raw copy.
    assert {"citext", "pgcrypto"} <= exts, "approved extensions must be restored"


def test_reader_role_cannot_dml(snap_env: _Env) -> None:
    async def checks() -> tuple[bool, bool, bool]:
        reader = await asyncpg.connect(
            host=str(snap_env.source["host"]),
            port=int(snap_env.source["port"]),
            user=READER_ROLE,
            password=_CANARY_SOURCE_PW,
            database=str(snap_env.source["database"]),
        )
        try:
            outcomes = []
            for sql in (
                "INSERT INTO institutions (id, name) VALUES (gen_random_uuid(), 'dml-probe')",
                "UPDATE institutions SET notes = 'dml-probe' WHERE false",
                "DELETE FROM institutions WHERE false",
            ):
                try:
                    await reader.execute(sql)
                    outcomes.append(False)
                except asyncpg.exceptions.InsufficientPrivilegeError:
                    outcomes.append(True)
            return tuple(outcomes)  # type: ignore[return-value]
        finally:
            await reader.close()

    denied_insert, denied_update, denied_delete = asyncio.run(checks())
    assert (denied_insert, denied_update, denied_delete) == (True, True, True)


def test_web_role_cannot_connect_or_read_raw_target(snap_env: _Env, custody: Path) -> None:
    config = _config_for(snap_env, custody)
    result = ds.run_snapshot_job(config)
    assert result.state == STATE_RAW_UNVERIFIED, result.failure_code

    async def checks() -> tuple[bool, str]:
        t = await _connect(snap_env.target)
        try:
            can_connect = await t.fetchval(
                "SELECT has_database_privilege($1, $2, 'CONNECT')",
                WEB_ROLE,
                result.target_db,
            )
        finally:
            await t.close()
        # Auth proof: the web role CAN authenticate and connect to the
        # target service's postgres database with its fixture password,
        # so a raw-copy denial below is a genuine privilege denial.
        probe = await asyncpg.connect(
            host=str(snap_env.target["host"]),
            port=int(snap_env.target["port"]),
            user=WEB_ROLE,
            password=_CANARY_WEB_PW,
            database="postgres",
            timeout=10,
        )
        await probe.close()
        # The raw-copy connection must fail specifically for the CONNECT
        # privilege (SQLSTATE 42501), not auth failure or any other error.
        try:
            conn = await asyncpg.connect(
                host=str(snap_env.target["host"]),
                port=int(snap_env.target["port"]),
                user=WEB_ROLE,
                password=_CANARY_WEB_PW,
                database=result.target_db,
                timeout=10,
            )
            await conn.close()
            return bool(can_connect), "connected"
        except asyncpg.InsufficientPrivilegeError as exc:
            return bool(can_connect), str(exc.sqlstate)
        except (asyncpg.PostgresError, OSError) as exc:
            return bool(can_connect), f"unexpected: {type(exc).__name__}"

    can_connect, denial = asyncio.run(checks())
    assert can_connect is False, "raw copy must revoke CONNECT from PUBLIC (web role)"
    assert denial == "42501", (
        "web role must be denied by CONNECT privilege (SQLSTATE 42501), "
        "not by authentication or any other error"
    )


def test_create_gate_denies_connect_while_closed_and_after(snap_env: _Env) -> None:
    """Mirror the worker's exact raw-database gate and prove the window.

    The fresh database is created CLOSED (ALLOW_CONNECTIONS = false);
    while closed even the configured target user cannot connect. The ACL
    restriction (REVOKE PUBLIC / GRANT target user) is applied while still
    closed, and the database is opened only afterwards. The synthetic web
    role is denied in the closed window AND after the gate. (The trusted
    extensions required by migration 0001 are not bootstrapped here; they
    travel inside the dump archive and are asserted on the raw copy in
    test_demo_control_excluded_and_unreadable.)
    """
    target_db = f"demo_snap_gate_{uuid.uuid4().hex[:16]}"

    async def attempt_connect(user: str, password: str) -> bool:
        try:
            conn = await asyncpg.connect(
                host=str(snap_env.target["host"]),
                port=int(snap_env.target["port"]),
                user=user,
                password=password,
                database=target_db,
                timeout=10,
            )
            await conn.close()
            return True
        except (asyncpg.PostgresError, OSError):
            return False

    async def gate() -> None:
        admin = await _connect(snap_env.target)
        try:
            await admin.execute(
                f'CREATE DATABASE "{target_db}" WITH ALLOW_CONNECTIONS = false'
            )
            # Closed window: even the target user cannot connect.
            assert (
                await attempt_connect(
                    str(snap_env.target["user"]), str(snap_env.target["password"])
                )
                is False
            )
            # Synthetic web role denied while closed.
            assert await attempt_connect(WEB_ROLE, _CANARY_WEB_PW) is False
            # Restrict while still closed.
            await admin.execute(
                f'REVOKE CONNECT ON DATABASE "{target_db}" FROM PUBLIC; '
                f'GRANT CONNECT ON DATABASE "{target_db}" TO "{snap_env.target["user"]}"'
            )
            # Open only after the restriction is in place.
            await admin.execute(
                f'ALTER DATABASE "{target_db}" WITH ALLOW_CONNECTIONS = true'
            )
            # After the gate: web role still denied, target user connects.
            assert await attempt_connect(WEB_ROLE, _CANARY_WEB_PW) is False
            owner = await asyncpg.connect(
                host=str(snap_env.target["host"]),
                port=int(snap_env.target["port"]),
                user=str(snap_env.target["user"]),
                password=str(snap_env.target["password"]),
                database=target_db,
                timeout=10,
            )
            try:
                await owner.fetchval("SELECT 1")
            finally:
                await owner.close()
        finally:
            await admin.close()
            cleanup = await _connect(snap_env.target)
            try:
                await cleanup.execute(
                    f'DROP DATABASE IF EXISTS "{target_db}" WITH (FORCE)'
                )
            finally:
                await cleanup.close()

    asyncio.run(gate())


def test_two_invocations_produce_distinct_fresh_copies(snap_env: _Env, custody: Path) -> None:
    config = _config_for(snap_env, custody)
    first = ds.run_snapshot_job(config)
    assert first.state == STATE_RAW_UNVERIFIED, first.failure_code

    async def seed_row() -> None:
        s = await _connect(snap_env.source)
        try:
            await s.execute(
                "INSERT INTO institutions "
                "(id, name, country, notes, created_at, updated_at) "
                "VALUES ($1, $2, 'SI', '221 synthetic fixture', NOW(), NOW())",
                uuid.uuid4(),
                f"snapseq-{_RUN_TAG}-second-run",
            )
        finally:
            await s.close()

    asyncio.run(seed_row())
    second = ds.run_snapshot_job(config)
    assert second.state == STATE_RAW_UNVERIFIED, second.failure_code
    assert second.target_db != first.target_db

    async def names(target_db: str) -> set[str]:
        conn = await asyncpg.connect(
            host=str(snap_env.target["host"]),
            port=int(snap_env.target["port"]),
            user=str(snap_env.target["user"]),
            password=str(snap_env.target["password"]),
            database=target_db,
        )
        try:
            rows = await conn.fetch("SELECT name FROM institutions")
            return {row["name"] for row in rows}
        finally:
            await conn.close()

    first_names, second_names = asyncio.run(names(first.target_db)), asyncio.run(names(second.target_db))
    tagged_second = f"snapseq-{_RUN_TAG}-second-run"
    assert tagged_second not in first_names
    assert tagged_second in second_names
    assert len(_raw_jobs(config)) == 2


# ---------------------------------------------------------------------------
# Limits, failures, and custody
# ---------------------------------------------------------------------------


def test_byte_cap_aborts_before_complete_claim(snap_env: _Env, custody: Path) -> None:
    config = _config_for(snap_env, custody, DEMO_SNAPSHOT_MAX_EXPORT_BYTES=1024)
    result = ds.run_snapshot_job(config)
    assert result.state == STATE_FAILED
    assert result.failure_code == CODE_SOURCE_DUMP_CAP_BYTES
    assert result.export_bytes == 0
    assert _raw_jobs(config) == []
    leftover = [p for p in config.custody_dir.glob("snap-*/demo.dump")]
    assert leftover == []
    asyncio.run(_assert_no_target_dbs(snap_env, custody, config))


def test_elapsed_cap_aborts_hung_dump(snap_env: _Env, custody: Path) -> None:
    config = _config_for(snap_env, custody, DEMO_SNAPSHOT_MAX_ELAPSED_SECONDS=2)

    async def hold_lock(done: threading.Event) -> None:
        s = await _connect(snap_env.source)
        try:
            async with s.transaction():
                await s.execute("LOCK TABLE institutions IN ACCESS EXCLUSIVE MODE")
                while not done.is_set():
                    await asyncio.sleep(0.05)
        finally:
            await s.close()

    done = threading.Event()
    holder = threading.Thread(target=lambda: asyncio.run(hold_lock(done)), daemon=True)
    holder.start()
    time.sleep(0.5)  # let the lock settle

    try:
        started = time.monotonic()
        result = ds.run_snapshot_job(config)
        elapsed = time.monotonic() - started
    finally:
        done.set()
        holder.join(timeout=10)

    assert result.state == STATE_FAILED
    assert result.failure_code == CODE_SOURCE_DUMP_CAP_ELAPSED
    assert elapsed < 20
    asyncio.run(_assert_no_target_dbs(snap_env, custody, config))


def test_blocked_catalog_guard_fails_closed_bounded(snap_env: _Env, custody: Path) -> None:
    """The separation preflight shares the job's ONE absolute deadline.

    A pg_database catalog lock held by THIS run blocks the bounded
    separation check before any CREATE DATABASE: the job must fail with
    the exact TARGET_NOT_SEPARATE code (separation could not be
    verified), create no database, and stay bounded by the job budget
    plus cleanup slack. The independent create/dump/restore deadline
    sharing is covered by the unit suite. The fixture releases its own
    catalog lock on an independent 4s timer — after the 3s job cap has
    fired — so the worker's bounded post-failure existence check is not
    blocked by this fixture's own lock holder.
    """
    config = _config_for(snap_env, custody, DEMO_SNAPSHOT_MAX_ELAPSED_SECONDS=3)

    async def hold_pg_database_lock(done: threading.Event) -> None:
        s = await _connect(snap_env.target)
        try:
            async with s.transaction():
                await s.execute(
                    "LOCK TABLE pg_database IN ACCESS EXCLUSIVE MODE"
                )
                while not done.is_set():
                    await asyncio.sleep(0.05)
        finally:
            await s.close()

    done = threading.Event()
    holder = threading.Thread(
        target=lambda: asyncio.run(hold_pg_database_lock(done)), daemon=True
    )
    holder.start()
    time.sleep(0.5)  # let the catalog lock settle

    def release_later() -> None:
        time.sleep(4.0)
        done.set()

    releaser = threading.Thread(target=release_later, daemon=True)
    releaser.start()

    try:
        started = time.monotonic()
        result = ds.run_snapshot_job(config)
        elapsed = time.monotonic() - started
    finally:
        done.set()
        holder.join(timeout=10)
    releaser.join(timeout=10)

    assert result.state == STATE_FAILED
    assert result.failure_code == CODE_TARGET_NOT_SEPARATE
    # Bounded by the ONE job budget plus cleanup slack.
    assert elapsed < 15
    asyncio.run(_assert_no_target_dbs(snap_env, custody, config))


def test_cancel_stops_in_flight_job(snap_env: _Env, custody: Path) -> None:
    config = _config_for(snap_env, custody)
    cancel = threading.Event()
    cancel.set()
    result = ds.run_snapshot_job(config, cancel_event=cancel)
    assert result.state == STATE_FAILED
    assert result.failure_code == CODE_SOURCE_DUMP_CANCELLED
    asyncio.run(_assert_no_target_dbs(snap_env, custody, config))


def test_restore_create_failure_leaves_nothing(snap_env: _Env, custody: Path) -> None:
    # A NOCREATEDB target user cannot create the raw copy: after a proven
    # authentication, the CREATE DATABASE denial must be a genuine
    # privilege failure (SQLSTATE 42501), and the job must report FAILED
    # with TARGET_CREATE_FAILED because the denied create leaves no
    # database to clean (authoritative existence check).
    settings = _settings_for(snap_env, custody, DEMO_SNAPSHOT_TARGET_USER=NOCREATE_ROLE)
    nocreate_config = ds.config_from_settings(settings)

    async def privilege_check() -> tuple[str, bool]:
        probe = await asyncpg.connect(
            host=str(snap_env.target["host"]),
            port=int(snap_env.target["port"]),
            user=NOCREATE_ROLE,
            password=_CANARY_NOCREATE_PW,
            database="postgres",
            timeout=10,
        )
        try:
            try:
                await probe.execute(f"CREATE DATABASE demo_snap_{uuid.uuid4().hex[:20]}")
                return "created", True  # must not happen: NOCREATEDB role
            except asyncpg.InsufficientPrivilegeError as exc:
                return str(exc.sqlstate), False
            except (asyncpg.PostgresError, OSError) as exc:
                return f"unexpected: {type(exc).__name__}", False
        finally:
            await probe.close()

    sqlstate, probe_db_made = asyncio.run(privilege_check())
    assert sqlstate == "42501", (
        "NOCREATEDB denial must be SQLSTATE 42501, not auth or other errors"
    )
    assert probe_db_made is False, "NOCREATEDB role must not create any database"

    result = ds.run_snapshot_job(nocreate_config)
    assert result.state == STATE_FAILED
    assert result.failure_code == CODE_TARGET_CREATE_FAILED
    assert _raw_jobs(nocreate_config) == []
    asyncio.run(_assert_no_target_dbs(snap_env, custody, nocreate_config))


def test_same_cluster_target_refused_before_any_create(
    snap_env: _Env, custody: Path, tmp_path: Path
) -> None:
    # Misconfiguration: the target host/port resolve to the SOURCE
    # cluster and the target user is the source admin (which can create
    # databases). The bounded separation guard must reject before any
    # CREATE, so the source catalog must be unchanged. The same
    # host+port guard fires before any psql call; a test-local passfile
    # entry for the source admin lets the post-failure existence check
    # authenticate, so the outcome is FAILED (not a cleanup artifact).
    test_passfile = tmp_path / "pgpass"
    with open(snap_env.passfile, encoding="utf-8") as fh:
        base_lines = fh.read().splitlines()
    test_passfile.write_text(
        "\n".join(
            [
                *base_lines,
                f"{snap_env.source['host']}:{snap_env.source['port']}:*"
                f":{snap_env.source['user']}:{snap_env.source['password']}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    os.chmod(test_passfile, 0o600)

    settings = _settings_for(
        snap_env,
        custody,
        DEMO_SNAPSHOT_TARGET_HOST=snap_env.source["host"],
        DEMO_SNAPSHOT_TARGET_PORT=snap_env.source["port"],
        DEMO_SNAPSHOT_TARGET_USER=snap_env.source["user"],
        DEMO_SNAPSHOT_PGPASSFILE=str(test_passfile),
    )
    config = ds.config_from_settings(settings)

    async def source_db_names() -> set[str]:
        c = await _connect(snap_env.source)
        try:
            return await _target_db_names(c)
        finally:
            await c.close()

    before = asyncio.run(source_db_names())
    result = ds.run_snapshot_job(config)
    after = asyncio.run(source_db_names())

    assert result.state == STATE_FAILED
    assert result.failure_code == CODE_TARGET_NOT_SEPARATE
    assert after == before, "guard must refuse before any CREATE DATABASE"
    assert not any(
        name.startswith("demo_snap_") for name in after
    ), "no raw copy may appear on the source cluster"
    assert _raw_jobs(config) == []


async def _assert_no_target_dbs(snap_env: _Env, custody: Path, config: ds.DemoSnapshotConfig) -> None:
    """No raw database may remain for any job recorded in this custody dir."""
    for job_dir in ds._list_job_dirs(custody):
        manifest = ds._read_manifest(job_dir)
        if manifest is None:
            continue
        exists = await _db_exists(snap_env, manifest.target_db)
        assert exists is False, "partial target database must be cleaned up"


def test_recover_interrupted_job_idempotent(snap_env: _Env, custody: Path) -> None:
    config = _config_for(snap_env, custody)

    async def make_partial() -> str:
        t = await _connect(snap_env.target)
        try:
            target_db = f"demo_snap_{uuid.uuid4().hex[:20]}"
            await t.execute(f'CREATE DATABASE "{target_db}"')
            await t.execute(f'REVOKE CONNECT ON DATABASE "{target_db}" FROM PUBLIC')
            return target_db
        finally:
            await t.close()

    target_db = asyncio.run(make_partial())
    job_id = f"snap-{uuid.uuid4().hex}"
    job_dir = custody / job_id
    job_dir.mkdir(mode=0o700)
    manifest = ds.SnapshotManifest(
        job_id=job_id,
        state=STATE_RUNNING,
        created_at=time.time(),
        target_db=target_db,
    )
    ds._write_manifest(job_dir, manifest)
    (job_dir / ds._DUMP_NAME).write_bytes(b"partial-bytes")

    assert ds.recover_interrupted_jobs(config) == 1
    assert asyncio.run(_db_exists(snap_env, target_db)) is False
    assert not (job_dir / ds._DUMP_NAME).exists()
    recovered = ds._read_manifest(job_dir)
    assert recovered is not None
    assert recovered.state == STATE_CLEANED
    # Idempotent second pass.
    assert ds.recover_interrupted_jobs(config) == 0


def test_expiry_and_copy_budget_drop_real_copies(snap_env: _Env, custody: Path) -> None:
    config = _config_for(snap_env, custody, DEMO_SNAPSHOT_MAX_COPIES=1)

    async def make_copy() -> str:
        t = await _connect(snap_env.target)
        try:
            target_db = f"demo_snap_{uuid.uuid4().hex[:20]}"
            await t.execute(f'CREATE DATABASE "{target_db}"')
            return target_db
        finally:
            await t.close()

    def record(target_db: str, age_seconds: float) -> None:
        job_id = f"snap-{uuid.uuid4().hex}"
        job_dir = custody / job_id
        job_dir.mkdir(mode=0o700)
        manifest = ds.SnapshotManifest(
            job_id=job_id,
            state=STATE_RAW_UNVERIFIED,
            created_at=time.time() - age_seconds,
            target_db=target_db,
        )
        ds._write_manifest(job_dir, manifest)

    old_db = asyncio.run(make_copy())
    mid_db = asyncio.run(make_copy())
    new_db = asyncio.run(make_copy())
    record(old_db, 10_000)  # beyond the default 3600s retention
    record(mid_db, 100)  # within retention
    record(new_db, 0.0)  # within retention

    removed = ds.expire_copies(config)
    assert removed == 2  # old by retention, mid by budget (oldest first)
    assert asyncio.run(_db_exists(snap_env, old_db)) is False
    assert asyncio.run(_db_exists(snap_env, mid_db)) is False
    assert asyncio.run(_db_exists(snap_env, new_db)) is True
    assert len(_raw_jobs(config)) == 1


def test_force_cleanup_terminates_active_connection(snap_env: _Env, custody: Path) -> None:
    """Cleanup uses DROP ... WITH (FORCE): an active connection to the
    interrupted copy is terminated and the copy is removed. The probe runs
    on the SAME event loop that owns the held connection (an asyncpg
    connection cannot be used across asyncio.run loops)."""
    config = _config_for(snap_env, custody)

    async def scenario() -> None:
        t = await _connect(snap_env.target)
        try:
            target_db = f"demo_snap_{uuid.uuid4().hex[:20]}"
            await t.execute(f'CREATE DATABASE "{target_db}"')
            await t.execute(f'REVOKE CONNECT ON DATABASE "{target_db}" FROM PUBLIC')
        finally:
            await t.close()
        held = await asyncpg.connect(
            host=str(snap_env.target["host"]),
            port=int(snap_env.target["port"]),
            user=str(snap_env.target["user"]),
            password=str(snap_env.target["password"]),
            database=target_db,
        )
        job_id = f"snap-{uuid.uuid4().hex}"
        job_dir = custody / job_id
        job_dir.mkdir(mode=0o700)
        manifest = ds.SnapshotManifest(
            job_id=job_id,
            state=STATE_RUNNING,
            created_at=time.time(),
            target_db=target_db,
        )
        ds._write_manifest(job_dir, manifest)
        (job_dir / ds._DUMP_NAME).write_bytes(b"partial-bytes")

        # The real worker cleanup (psql subprocess) runs while this loop
        # is idle; the FORCE drop must terminate the active session.
        assert ds.recover_interrupted_jobs(config) == 1
        check = await _connect(snap_env.target)
        try:
            exists = await check.fetchrow(
                "SELECT 1 FROM pg_database WHERE datname = $1", target_db
            )
        finally:
            await check.close()
        assert exists is None
        # The next I/O on the terminated connection must fail with a
        # connection-level (not SQL) error.
        with pytest.raises(
            (asyncpg.InterfaceError, asyncpg.PostgresError, OSError)
        ):
            await held.fetchval("SELECT 1")
        try:
            await held.close()
        except Exception:
            pass

    asyncio.run(scenario())


def test_cli_output_and_manifest_contain_no_secrets(
    snap_env: _Env, custody: Path
) -> None:
    config = _config_for(snap_env, custody)
    settings = _settings_for(snap_env, custody)
    result = ds.run_snapshot_job(config)
    assert result.state == STATE_RAW_UNVERIFIED, result.failure_code

    env = dict(os.environ)
    env.update(
        {
            "DEMO_SNAPSHOT_ENABLED": "true",
            "DEMO_SNAPSHOT_SOURCE_HOST": str(settings.DEMO_SNAPSHOT_SOURCE_HOST),
            "DEMO_SNAPSHOT_SOURCE_PORT": str(settings.DEMO_SNAPSHOT_SOURCE_PORT),
            "DEMO_SNAPSHOT_SOURCE_DATABASE": str(settings.DEMO_SNAPSHOT_SOURCE_DATABASE),
            "DEMO_SNAPSHOT_SOURCE_USER": READER_ROLE,
            "DEMO_SNAPSHOT_TARGET_HOST": str(settings.DEMO_SNAPSHOT_TARGET_HOST),
            "DEMO_SNAPSHOT_TARGET_PORT": str(settings.DEMO_SNAPSHOT_TARGET_PORT),
            "DEMO_SNAPSHOT_TARGET_USER": str(settings.DEMO_SNAPSHOT_TARGET_USER),
            "DEMO_SNAPSHOT_PGPASSFILE": str(settings.DEMO_SNAPSHOT_PGPASSFILE),
            "DEMO_SNAPSHOT_CUSTODY_DIR": str(settings.DEMO_SNAPSHOT_CUSTODY_DIR),
            "DEMO_SNAPSHOT_MAX_EXPORT_BYTES": str(settings.DEMO_SNAPSHOT_MAX_EXPORT_BYTES),
            "DEMO_SNAPSHOT_MAX_ELAPSED_SECONDS": str(settings.DEMO_SNAPSHOT_MAX_ELAPSED_SECONDS),
            "DEMO_SNAPSHOT_RETENTION_SECONDS": str(settings.DEMO_SNAPSHOT_RETENTION_SECONDS),
            "DEMO_SNAPSHOT_MAX_COPIES": str(settings.DEMO_SNAPSHOT_MAX_COPIES),
        }
    )
    import subprocess as _subprocess
    import sys as _sys

    cli = Path(_sys.executable).parent / "slaif-gateway"
    proc = _subprocess.run(
        [str(cli), "demo-snapshot-worker", "run", "--json"],
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert proc.returncode == 0, proc.stderr
    output = proc.stdout + proc.stderr
    for secret in snap_env.canaries:
        assert secret not in output
    assert result.target_db not in output
    assert "RAW_UNVERIFIED" in output

    # The private custody manifest must not contain any credential either.
    for job_dir in ds._list_job_dirs(config.custody_dir):
        manifest_bytes = (job_dir / ds._MANIFEST_NAME).read_bytes()
        for secret in snap_env.canaries:
            assert secret.encode() not in manifest_bytes
