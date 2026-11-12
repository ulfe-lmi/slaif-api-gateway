"""Unit tests for the bounded private demo snapshot worker (objective 221).

These tests exercise the custody, fence, limits, redaction and manifest
logic with fake PostgreSQL client tools (scripts on PATH) and fake target
ops. No database, network or provider is involved; the real tooling is
covered by tests/integration/test_demo_snapshot_postgres.py.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from slaif_gateway.config import Settings
from slaif_gateway.services import demo_snapshot as ds
from slaif_gateway.services.demo_snapshot import (
    CODE_CLEANUP_FAILED,
    CODE_CUSTODY_UNSAFE,
    CODE_DISABLED,
    CODE_FENCE_HELD,
    CODE_MISCONFIGURED,
    CODE_SOURCE_DUMP_CAP_BYTES,
    CODE_SOURCE_DUMP_CAP_ELAPSED,
    CODE_SOURCE_DUMP_CANCELLED,
    CODE_SOURCE_DUMP_FAILED,
    STATE_CLEANED,
    STATE_CLEANUP_FAILED,
    STATE_FAILED,
    STATE_RAW_UNVERIFIED,
    STATE_RUNNING,
    TargetOps,
)


def _settings(**overrides) -> Settings:
    base: dict[str, object] = {
        "DEMO_SNAPSHOT_ENABLED": True,
        "DEMO_SNAPSHOT_SOURCE_HOST": "127.0.0.1",
        "DEMO_SNAPSHOT_SOURCE_PORT": 5555,
        "DEMO_SNAPSHOT_SOURCE_DATABASE": "slaif_src",
        "DEMO_SNAPSHOT_SOURCE_USER": "snap_reader",
        "DEMO_SNAPSHOT_TARGET_HOST": "127.0.0.1",
        "DEMO_SNAPSHOT_TARGET_PORT": 5556,
        "DEMO_SNAPSHOT_TARGET_USER": "snap_target",
        "DEMO_SNAPSHOT_PGPASSFILE": str(Path("/tmp/never") / "pgpass"),
        "DEMO_SNAPSHOT_CUSTODY_DIR": str(Path("/tmp/never") / "custody"),
    }
    base.update(overrides)
    return Settings(**base)


def _custody(tmp_path: Path) -> Path:
    custody = tmp_path / "custody"
    custody.mkdir(mode=0o700)
    return custody


def _passfile(tmp_path: Path) -> Path:
    passfile = tmp_path / "pgpass"
    passfile.write_text(
        "127.0.0.1:5555:slaif_src:snap_reader:canary-source-pw\n"
        "127.0.0.1:5556:*:snap_target:canary-target-pw\n",
        encoding="utf-8",
    )
    os.chmod(passfile, 0o600)
    return passfile


def _config(tmp_path: Path, **overrides) -> ds.DemoSnapshotConfig:
    custody = overrides.pop("custody", None) or _custody(tmp_path)
    passfile = overrides.pop("pgpassfile", None) or _passfile(tmp_path)
    settings = _settings(
        DEMO_SNAPSHOT_PGPASSFILE=str(passfile),
        DEMO_SNAPSHOT_CUSTODY_DIR=str(custody),
        **overrides,
    )
    return ds.config_from_settings(settings)


def _fake_ops(calls: list[str]) -> TargetOps:
    def create_database(name: str, deadline: float) -> None:
        calls.append(f"create:{name}")

    def drop_database(name: str) -> bool:
        calls.append(f"drop:{name}")
        return True

    def restore(archive: Path, name: str, deadline: float) -> None:
        calls.append(f"restore:{name}")

    def database_exists(name: str) -> bool | None:
        # Fake world: the database is assumed present, so the drop path is
        # exercised exactly as before.
        return True

    return TargetOps(
        create_database=create_database,
        drop_database=drop_database,
        restore=restore,
        database_exists=database_exists,
    )


def _fake_tool(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, name: str, body: str) -> None:
    """Install a fake client tool; repeated calls accumulate (not replace)."""
    script = tmp_path / name
    script.write_text(f"#!/bin/bash\n{body}\n", encoding="utf-8")
    os.chmod(script, 0o755)
    current = ds.shutil.which

    def which(tool: str, _current=current, _script=str(script), _name=name) -> str | None:
        if tool == _name:
            return _script
        return _current(tool)

    monkeypatch.setattr(ds.shutil, "which", which)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


def test_disabled_by_default_raises_safe_disabled_code() -> None:
    settings = Settings(DATABASE_URL="postgresql+asyncpg://u:p@127.0.0.1:5432/db")
    with pytest.raises(ds.DemoSnapshotError) as excinfo:
        ds.config_from_settings(settings)
    assert excinfo.value.code == CODE_DISABLED


def test_missing_fields_raise_misconfigured() -> None:
    settings = _settings(DEMO_SNAPSHOT_TARGET_HOST="")
    with pytest.raises(ds.DemoSnapshotError) as excinfo:
        ds.config_from_settings(settings)
    assert excinfo.value.code == CODE_MISCONFIGURED
    assert "127.0.0.1" not in excinfo.value.safe_message


def test_relative_custody_or_passfile_refused() -> None:
    settings = _settings(DEMO_SNAPSHOT_CUSTODY_DIR="relative/custody")
    with pytest.raises(ds.DemoSnapshotError) as excinfo:
        ds.config_from_settings(settings)
    assert excinfo.value.code == CODE_MISCONFIGURED
    settings = _settings(DEMO_SNAPSHOT_PGPASSFILE="relative/pgpass")
    with pytest.raises(ds.DemoSnapshotError) as excinfo:
        ds.config_from_settings(settings)
    assert excinfo.value.code == CODE_MISCONFIGURED


def test_non_positive_limits_refused() -> None:
    for field in (
        "DEMO_SNAPSHOT_MAX_EXPORT_BYTES",
        "DEMO_SNAPSHOT_MAX_ELAPSED_SECONDS",
        "DEMO_SNAPSHOT_RETENTION_SECONDS",
        "DEMO_SNAPSHOT_MAX_COPIES",
    ):
        settings = _settings(**{field: 0})
        with pytest.raises(ds.DemoSnapshotError) as excinfo:
            ds.config_from_settings(settings)
        assert excinfo.value.code == CODE_MISCONFIGURED


# ---------------------------------------------------------------------------
# Target-user SQL identifier validation
# ---------------------------------------------------------------------------


def test_target_user_must_be_sql_identifier() -> None:
    # Quotes or SQL metacharacters in the interpolated GRANT target are
    # refused at configuration time, never echoed back.
    for bad in ('bad"user', "snap; DROP", "has space", "UPPERCASE"):
        settings = _settings(DEMO_SNAPSHOT_TARGET_USER=bad)
        with pytest.raises(ds.DemoSnapshotError) as excinfo:
            ds.config_from_settings(settings)
        assert excinfo.value.code == CODE_MISCONFIGURED
        assert bad not in excinfo.value.safe_message


def test_source_database_must_be_sql_identifier() -> None:
    # The source database name is interpolated into the separation
    # catalog query; quotes or SQL metacharacters are refused at
    # configuration time, never echoed back.
    for bad in ('bad"db', "src; DROP", "has space", "UPPERDB"):
        settings = _settings(DEMO_SNAPSHOT_SOURCE_DATABASE=bad)
        with pytest.raises(ds.DemoSnapshotError) as excinfo:
            ds.config_from_settings(settings)
        assert excinfo.value.code == CODE_MISCONFIGURED
        assert bad not in excinfo.value.safe_message


# ---------------------------------------------------------------------------
# Separation guard and existence parser: exact boolean only (fail closed)
# ---------------------------------------------------------------------------


def _target_ops_with_psql(
    config: ds.DemoSnapshotConfig,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    psql_body: str,
) -> TargetOps:
    _fake_tool(monkeypatch, tmp_path, "psql", psql_body)
    return ds._target_ops(config, workdir=config.custody_dir, secrets=[])


def test_separation_guard_requires_exact_false_proof(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The catalog query is the only psql call containing "datname"; any
    # other call means the guard already let a create step run.
    config = _config(tmp_path)
    sentinel = tmp_path / "create_called"
    for body, proceed in (
        ("printf %s f", True),
        ("printf %s t", False),
        ("exit 0", False),  # rc 0 but EMPTY output: not a proof
        ("printf %s tf", False),  # malformed, would pass endswith("f")
        ("printf %s true", False),
        ("printf %s 'f x'", False),
        ("exit 3", False),  # nonzero rc
    ):
        if sentinel.exists():
            sentinel.unlink()
        ops = _target_ops_with_psql(
            config,
            monkeypatch,
            tmp_path,
            f'if [[ "$*" == *datname* ]]; then {body}; else touch "{sentinel}"; exit 0; fi',
        )
        raised: ds.DemoSnapshotError | None = None
        try:
            ops.create_database("demo_snap_unitprobe", time.monotonic() + 60)
        except ds.DemoSnapshotError as exc:
            raised = exc
        if proceed:
            assert raised is None, "exact 'f' must allow the create sequence"
            assert sentinel.exists(), "create steps must run after exact 'f'"
        else:
            assert raised is not None, "rejected proof must not create"
            assert raised.code == ds.CODE_TARGET_NOT_SEPARATE
            assert not sentinel.exists(), "no create step may run on rejected proof"


def test_database_exists_accepts_only_exact_boolean(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _config(tmp_path)
    for body, expected in (
        ("printf %s t", True),
        ("printf %s f", False),
        ("exit 0", None),  # empty output: unknown, never a guess
        ("printf %s tf", None),  # would pass endswith("f")
        ("printf %s true", None),
        ("printf %s 't f'", None),
        ("exit 3", None),  # nonzero rc
    ):
        ops = _target_ops_with_psql(config, monkeypatch, tmp_path, body)
        assert ops.database_exists("demo_snap_unitprobe") is expected


# ---------------------------------------------------------------------------
# Custody directory safety
# ---------------------------------------------------------------------------


def test_custody_symlink_refused(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir(mode=0o700)
    link = tmp_path / "link"
    os.symlink(real, link)
    config = _config(tmp_path, custody=link)
    with pytest.raises(ds.DemoSnapshotError) as excinfo:
        ds._validate_custody_dir(config.custody_dir)
    assert excinfo.value.code == CODE_CUSTODY_UNSAFE


def test_custody_symlinked_parent_refused(tmp_path: Path) -> None:
    # The no-symlink boundary covers every configured path component,
    # not only the final root: a symlinked parent would move the whole
    # custody tree (and its 0700 boundary) to an unreviewed location.
    real_parent = tmp_path / "real_parent"
    real_parent.mkdir(mode=0o700)
    inner = real_parent / "custody"
    inner.mkdir(mode=0o700)
    link_parent = tmp_path / "link_parent"
    os.symlink(real_parent, link_parent)
    with pytest.raises(ds.DemoSnapshotError) as excinfo:
        ds._validate_custody_dir(link_parent / "custody")
    assert excinfo.value.code == CODE_CUSTODY_UNSAFE


def test_custody_unreadable_ancestor_refused_safely(tmp_path: Path) -> None:
    # A permission-denied ancestor must fail closed with the fixed
    # custody-unsafe code and a safe message — never a raw OSError that
    # could expose the private custody path in a CLI traceback.
    locked = tmp_path / "locked_parent"
    locked.mkdir(mode=0o700)
    inner = locked / "custody"
    inner.mkdir(mode=0o700)
    os.chmod(locked, 0o000)
    try:
        with pytest.raises(ds.DemoSnapshotError) as excinfo:
            ds._validate_custody_dir(inner)
    finally:
        os.chmod(locked, 0o700)
    assert excinfo.value.code == CODE_CUSTODY_UNSAFE
    assert str(inner) not in excinfo.value.safe_message
    assert str(locked) not in excinfo.value.safe_message


def test_custody_world_accessible_refused(tmp_path: Path) -> None:
    custody = tmp_path / "custody"
    custody.mkdir(mode=0o755)
    with pytest.raises(ds.DemoSnapshotError) as excinfo:
        ds._validate_custody_dir(custody)
    assert excinfo.value.code == CODE_CUSTODY_UNSAFE


def test_custody_other_execute_bit_refused(tmp_path: Path) -> None:
    # 0701 grants "other" execute (traversal) and is NOT owner-only.
    custody = tmp_path / "custody"
    custody.mkdir(mode=0o701)
    with pytest.raises(ds.DemoSnapshotError) as excinfo:
        ds._validate_custody_dir(custody)
    assert excinfo.value.code == CODE_CUSTODY_UNSAFE


def test_custody_missing_refused(tmp_path: Path) -> None:
    with pytest.raises(ds.DemoSnapshotError) as excinfo:
        ds._validate_custody_dir(tmp_path / "absent")
    assert excinfo.value.code == CODE_CUSTODY_UNSAFE


# ---------------------------------------------------------------------------
# Single-worker fence (kernel flock)
# ---------------------------------------------------------------------------


def test_fence_refuses_live_holder(tmp_path: Path) -> None:
    custody = _custody(tmp_path)
    holder = ds._acquire_fence(custody)
    try:
        with pytest.raises(ds.DemoSnapshotError) as excinfo:
            ds._acquire_fence(custody)
        assert excinfo.value.code == CODE_FENCE_HELD
    finally:
        ds._release_fence(holder)


def test_symlinked_fence_refused(tmp_path: Path) -> None:
    # A planted symlink fence must not redirect the kernel lock to an
    # arbitrary file: O_NOFOLLOW makes acquisition fail closed.
    custody = _custody(tmp_path)
    target = tmp_path / "fence_target"
    target.write_text("", encoding="utf-8")
    os.chmod(target, 0o600)
    os.symlink(target, custody / ds._FENCE_NAME)
    with pytest.raises(ds.DemoSnapshotError) as excinfo:
        ds._acquire_fence(custody)
    assert excinfo.value.code == CODE_FENCE_HELD


def test_fence_is_released_when_holder_dies(tmp_path: Path) -> None:
    custody = _custody(tmp_path)
    fence = custody / ds._FENCE_NAME
    script = (
        "import fcntl, os, time\n"
        f"fd = os.open({str(fence)!r}, os.O_RDWR | os.O_CREAT, 0o600)\n"
        "fcntl.flock(fd, fcntl.LOCK_EX)\n"
        "print('held', flush=True)\n"
        "time.sleep(30)\n"
    )
    proc = subprocess.Popen(
        [sys.executable, "-c", script], stdout=subprocess.PIPE, text=True
    )
    try:
        assert proc.stdout.readline().strip() == "held"
        proc.kill()  # crash the holder: no explicit release
        proc.wait(timeout=10)
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=10)
    # The kernel released the dead holder's lock: acquisition succeeds now.
    fd = ds._acquire_fence(custody)
    ds._release_fence(fd)
    # Released fd: a second acquisition succeeds without interference.
    probe = ds._acquire_fence(custody)
    ds._release_fence(probe)


# ---------------------------------------------------------------------------
# Redaction and manifest
# ---------------------------------------------------------------------------


def test_redact_replaces_every_secret() -> None:
    message = "connect to demo_snap_abc via postgresql://u:secret@h:5432/db failed"
    out = ds._redact(message, ["secret", "demo_snap_abc", "postgresql://u:secret@h:5432/db"])
    assert "secret" not in out
    assert "demo_snap_abc" not in out
    assert "[redacted]" in out


def test_passfile_passwords_collected_including_wildcards(tmp_path: Path) -> None:
    config = _config(tmp_path)
    passwords = ds._read_passfile_passwords(config.pgpassfile, config)
    assert "canary-source-pw" in passwords
    assert "canary-target-pw" in passwords


def test_manifest_roundtrip_and_permissions(tmp_path: Path) -> None:
    job_dir = tmp_path / ("snap-" + "0" * 32)
    job_dir.mkdir(mode=0o700)
    manifest = ds.SnapshotManifest(
        job_id=job_dir.name,
        state=STATE_RUNNING,
        created_at=1000.0,
        target_db="demo_snap_x",
        export_bytes=42,
    )
    ds._write_manifest(job_dir, manifest)
    loaded = ds._read_manifest(job_dir)
    assert loaded is not None
    assert loaded.state == STATE_RUNNING
    assert loaded.target_db == "demo_snap_x"
    assert loaded.export_bytes == 42
    mode = (job_dir / ds._MANIFEST_NAME).stat().st_mode & 0o777
    assert mode == 0o600


def test_manifest_rejects_corrupt_or_unknown_schema(tmp_path: Path) -> None:
    job_dir = tmp_path / ("snap-" + "1" * 32)
    job_dir.mkdir(mode=0o700)
    (job_dir / ds._MANIFEST_NAME).write_text("{not json", encoding="utf-8")
    assert ds._read_manifest(job_dir) is None
    (job_dir / ds._MANIFEST_NAME).write_text('{"schema_version": 999}', encoding="utf-8")
    assert ds._read_manifest(job_dir) is None


# ---------------------------------------------------------------------------
# Orchestration with fake tools and fake target ops
# ---------------------------------------------------------------------------


def test_successful_job_marks_raw_unverified_with_exact_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = "dump-bytes-0123456789"
    _fake_tool(monkeypatch, tmp_path, "pg_dump", f'printf %s "{payload}"')
    _fake_tool(monkeypatch, tmp_path, "psql", "exit 0")
    _fake_tool(monkeypatch, tmp_path, "pg_restore", "exit 0")
    calls: list[str] = []
    config = _config(tmp_path)
    result = ds.run_snapshot_job(config, ops=_fake_ops(calls))
    assert result.state == STATE_RAW_UNVERIFIED
    assert result.failure_code is None
    assert result.export_bytes == len(payload.encode("utf-8"))
    assert calls == [f"create:{result.target_db}", f"restore:{result.target_db}"]

    job_dirs = [p for p in config.custody_dir.iterdir() if p.is_dir()]
    assert len(job_dirs) == 1
    manifest = ds._read_manifest(job_dirs[0])
    assert manifest is not None
    assert manifest.state == STATE_RAW_UNVERIFIED
    assert manifest.export_bytes == len(payload)
    assert manifest.capture_started_at is not None
    assert manifest.capture_finished_at is not None
    assert manifest.capture_finished_at >= manifest.capture_started_at
    # Custody mode and no fence left behind.
    assert job_dirs[0].stat().st_mode & 0o777 == 0o700
    # The fence file may exist, but the job's lock must be released.
    probe = ds._acquire_fence(config.custody_dir)
    ds._release_fence(probe)
    assert ds.count_raw_copies(config) == 1


def test_byte_cap_kills_dump_before_complete_claim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fake_tool(
        monkeypatch, tmp_path, "pg_dump",
        "for i in $(seq 1 200); do printf 'x%.0s' $(seq 1 1000); done",
    )
    _fake_tool(monkeypatch, tmp_path, "psql", "exit 0")
    _fake_tool(monkeypatch, tmp_path, "pg_restore", "exit 0")
    calls: list[str] = []
    config = _config(tmp_path, DEMO_SNAPSHOT_MAX_EXPORT_BYTES=10_000)
    result = ds.run_snapshot_job(config, ops=_fake_ops(calls))
    assert result.state == STATE_FAILED
    assert result.failure_code == CODE_SOURCE_DUMP_CAP_BYTES
    assert any(c.startswith("create:") for c in calls)
    assert not any(c.startswith("restore:") for c in calls)
    # No partial archive survives and no complete claim was made.
    leftover = [p for p in config.custody_dir.glob("snap-*/demo.dump")]
    assert leftover == []
    manifest = ds._read_manifest(next(p for p in config.custody_dir.iterdir() if p.is_dir()))
    assert manifest is not None
    assert manifest.state == STATE_FAILED
    assert manifest.export_bytes == 0


def test_elapsed_cap_kills_hung_dump(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fake_tool(monkeypatch, tmp_path, "pg_dump", "sleep 30")
    _fake_tool(monkeypatch, tmp_path, "psql", "exit 0")
    calls: list[str] = []
    config = _config(tmp_path, DEMO_SNAPSHOT_MAX_ELAPSED_SECONDS=1)
    started = time.monotonic()
    result = ds.run_snapshot_job(config, ops=_fake_ops(calls))
    assert time.monotonic() - started < 25
    assert result.state == STATE_FAILED
    assert result.failure_code == CODE_SOURCE_DUMP_CAP_ELAPSED


def test_cancel_event_stops_in_flight_dump(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fake_tool(monkeypatch, tmp_path, "pg_dump", "sleep 30")
    _fake_tool(monkeypatch, tmp_path, "psql", "exit 0")
    calls: list[str] = []
    config = _config(tmp_path, DEMO_SNAPSHOT_MAX_ELAPSED_SECONDS=30)
    cancel = threading.Event()
    cancel.set()
    result = ds.run_snapshot_job(config, cancel_event=cancel, ops=_fake_ops(calls))
    assert result.state == STATE_FAILED
    assert result.failure_code == CODE_SOURCE_DUMP_CANCELLED


def test_single_absolute_deadline_shared_by_create_dump_restore(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A slow create consumes the ONE job deadline; the dump then refuses
    to start instead of spending a second full budget."""
    _fake_tool(monkeypatch, tmp_path, "pg_dump", "sleep 30")
    _fake_tool(monkeypatch, tmp_path, "psql", "exit 0")
    _fake_tool(monkeypatch, tmp_path, "pg_restore", "exit 0")
    config = _config(tmp_path, DEMO_SNAPSHOT_MAX_ELAPSED_SECONDS=2)
    captured: dict[str, float] = {}

    def create_database(name: str, deadline: float) -> None:
        captured["create"] = deadline
        time.sleep(2.2)  # consume the entire job budget in create

    def restore(archive: Path, name: str, deadline: float) -> None:
        captured["restore"] = deadline

    ops = TargetOps(
        create_database=create_database,
        drop_database=lambda n: True,
        restore=restore,
        database_exists=lambda n: True,
    )
    started = time.monotonic()
    result = ds.run_snapshot_job(config, ops=ops)
    elapsed = time.monotonic() - started
    # The dump hit the (already expired) shared deadline immediately:
    # total elapsed is close to the create sleep, NOT sleep + full budget.
    assert elapsed < 4.0
    assert result.state == STATE_FAILED
    assert result.failure_code == CODE_SOURCE_DUMP_CAP_ELAPSED
    assert "restore" not in captured
    # The create deadline is anchored to JOB start (absolute), not to the
    # moment create itself began.
    assert abs(captured["create"] - (started + 2)) < 0.5


def test_dump_failure_cleans_target_and_keeps_safe_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fake_tool(monkeypatch, tmp_path, "pg_dump", "echo bad >&2; exit 2")
    _fake_tool(monkeypatch, tmp_path, "psql", "exit 0")
    calls: list[str] = []
    config = _config(tmp_path)
    result = ds.run_snapshot_job(config, ops=_fake_ops(calls))
    assert result.state == STATE_FAILED
    assert result.failure_code == CODE_SOURCE_DUMP_FAILED
    assert calls == [f"create:{result.target_db}", f"drop:{result.target_db}"]


def test_cleanup_failure_preserves_inspectable_state_and_retries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fake_tool(monkeypatch, tmp_path, "pg_dump", "echo bad >&2; exit 2")
    _fake_tool(monkeypatch, tmp_path, "psql", "exit 0")
    dropped: list[str] = []
    drop_ok = threading.Event()

    def drop_database(name: str) -> bool:
        dropped.append(name)
        return drop_ok.is_set()

    ops = TargetOps(
        create_database=lambda n, d: None,
        drop_database=drop_database,
        restore=lambda a, n, d: None,
        database_exists=lambda n: True,
    )
    config = _config(tmp_path)
    result = ds.run_snapshot_job(config, ops=ops)
    assert result.state == STATE_CLEANUP_FAILED
    assert result.failure_code == CODE_CLEANUP_FAILED
    manifest = ds._read_manifest(next(p for p in config.custody_dir.iterdir() if p.is_dir()))
    assert manifest is not None
    assert manifest.state == STATE_CLEANUP_FAILED

    # Idempotent retry: once the drop succeeds, recovery converges.
    drop_ok.set()
    recovered = ds.recover_interrupted_jobs(config, ops=ops)
    assert recovered == 1
    manifest = ds._read_manifest(next(p for p in config.custody_dir.iterdir() if p.is_dir()))
    assert manifest is not None
    assert manifest.state == STATE_CLEANED
    assert manifest.failure_code is None


# ---------------------------------------------------------------------------
# Stream fault injection: select/read errors fail closed and kill the group
# ---------------------------------------------------------------------------


def _assert_pid_dead(pid: int) -> None:
    """The pid must be dead (or at most an unreaped zombie), never running."""
    out = subprocess.run(
        ["ps", "-o", "state=", "-p", str(pid)], capture_output=True, text=True
    )
    state = out.stdout.strip()
    assert out.returncode != 0 or state.startswith("Z"), (
        f"child {pid} still alive with state {state!r}; the process group "
        "must be killed and reaped on stream failure"
    )


def test_select_error_fails_closed_no_complete_claim_kills_group(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A failed select() is a stream failure, never EOF: the job must end
    # FAILED with the dump-failure code (no RAW_UNVERIFIED claim, no
    # export bytes), and the tool's descendant child must be killed with
    # the process group.
    pidfile = tmp_path / "pg_dump_child.pid"
    _fake_tool(
        monkeypatch,
        tmp_path,
        "pg_dump",
        f"sleep 300 &\necho $! > {pidfile}\nwait",
    )
    _fake_tool(monkeypatch, tmp_path, "psql", "exit 0")
    real_select = ds.select.select
    calls = {"n": 0}

    def flaky_select(r, w, x, timeout=None):
        calls["n"] += 1
        if calls["n"] == 6:  # let the child start, then break the stream
            raise OSError(5, "injected select failure")
        return real_select(r, w, x, timeout)

    monkeypatch.setattr(ds.select, "select", flaky_select)
    calls_log: list[str] = []
    config = _config(tmp_path)
    result = ds.run_snapshot_job(config, ops=_fake_ops(calls_log))

    assert result.state == STATE_FAILED
    assert result.failure_code == CODE_SOURCE_DUMP_FAILED
    assert result.export_bytes == 0
    for job_dir in ds._list_job_dirs(config.custody_dir):
        manifest = ds._read_manifest(job_dir)
        assert manifest is not None
        assert manifest.state == STATE_FAILED, "no RAW_UNVERIFIED claim may stand"
        assert manifest.failure_code == CODE_SOURCE_DUMP_FAILED
    time.sleep(0.2)  # let the killed group fully exit
    _assert_pid_dead(int(pidfile.read_text().strip()))


def test_read_error_fails_closed_and_kills_group(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A failed os.read() likewise fails closed inside _run_tool with a
    # safe code (never a bare OSError) and kills the process group.
    # Only the service module's os namespace is swapped (a delegating
    # proxy whose read alone raises), so subprocess.Popen and the rest
    # of the interpreter keep the real os module.
    pidfile = tmp_path / "pg_dump_child.pid"
    _fake_tool(
        monkeypatch,
        tmp_path,
        "pg_dump",
        f"sleep 300 &\necho $! > {pidfile}\nprintf x\nwait",
    )
    config = _config(tmp_path)
    tool = ds.shutil.which("pg_dump")
    assert tool is not None

    class _ReadFailingOs:
        def read(self, fd, size):
            raise OSError(5, "injected read failure")

        def __getattr__(self, name):
            return getattr(os, name)

    monkeypatch.setattr(ds, "os", _ReadFailingOs())
    raised: ds.DemoSnapshotError | None = None
    try:
        ds._run_tool(
            [tool],
            env=ds._pg_env(config.pgpassfile),
            workdir=config.custody_dir,
            deadline=time.monotonic() + 30,
            cancel_event=None,
            secrets=[],
            # Select the stdout PIPE path so the pump (and os.read) run.
            on_chunk=lambda _chunk: None,
        )
    except ds.DemoSnapshotError as exc:
        raised = exc
    finally:
        monkeypatch.undo()  # restore ds.os before any further subprocess use

    assert raised is not None, "read error must raise a safe DemoSnapshotError"
    assert raised.code == ds.CODE_SOURCE_DUMP_FAILED
    assert raised.safe_message
    time.sleep(0.2)
    _assert_pid_dead(int(pidfile.read_text().strip()))


def test_recover_cleans_stale_running_job_idempotently(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fake_tool(monkeypatch, tmp_path, "psql", "exit 0")
    config = _config(tmp_path)
    calls: list[str] = []
    ops = _fake_ops(calls)

    job_id = "snap-" + "ab" * 16
    job_dir = config.custody_dir / job_id
    job_dir.mkdir(mode=0o700)
    manifest = ds.SnapshotManifest(
        job_id=job_id, state=STATE_RUNNING, created_at=time.time(), target_db="demo_snap_stale"
    )
    ds._write_manifest(job_dir, manifest)
    (job_dir / ds._DUMP_NAME).write_bytes(b"partial")

    assert ds.recover_interrupted_jobs(config, ops=ops) == 1
    manifest = ds._read_manifest(job_dir)
    assert manifest is not None
    assert manifest.state == STATE_CLEANED
    assert "drop:demo_snap_stale" in calls
    assert not (job_dir / ds._DUMP_NAME).exists()
    # Second run is a no-op (idempotent).
    assert ds.recover_interrupted_jobs(config, ops=ops) == 0


def test_expiry_removes_old_copies_and_enforces_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fake_tool(monkeypatch, tmp_path, "psql", "exit 0")
    config = _config(tmp_path, DEMO_SNAPSHOT_RETENTION_SECONDS=100, DEMO_SNAPSHOT_MAX_COPIES=2)
    calls: list[str] = []
    ops = _fake_ops(calls)

    def make_job(suffix: str, age_seconds: float) -> None:
        job_id = f"snap-{suffix}"
        job_dir = config.custody_dir / job_id
        job_dir.mkdir(mode=0o700)
        manifest = ds.SnapshotManifest(
            job_id=job_id,
            state=STATE_RAW_UNVERIFIED,
            created_at=time.time() - age_seconds,
            target_db=f"demo_snap_{suffix}",
        )
        ds._write_manifest(job_dir, manifest)

    hex32 = lambda n: format(n, "032x")  # noqa: E731
    make_job(hex32(1), 10_000)  # expired by retention
    make_job(hex32(2), 50)  # within retention, but over budget
    make_job(hex32(3), 10)  # within retention and budget
    make_job(hex32(4), 5)  # within retention and budget

    removed = ds.expire_copies(config, ops=ops)
    assert removed == 2  # one expired + one over budget (oldest first)
    assert f"drop:demo_snap_{hex32(1)}" in calls
    assert f"drop:demo_snap_{hex32(2)}" in calls
    assert ds.count_raw_copies(config) == 2


def test_secrets_never_rendered_in_job_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fake_tool(monkeypatch, tmp_path, "pg_dump", "printf x")
    _fake_tool(monkeypatch, tmp_path, "psql", "exit 0")
    _fake_tool(monkeypatch, tmp_path, "pg_restore", "exit 0")
    config = _config(tmp_path)
    result = ds.run_snapshot_job(config, ops=_fake_ops([]))
    assert result.state == STATE_RAW_UNVERIFIED
    rendered = json.dumps(
        {
            "state": result.state,
            "failure_code": result.failure_code,
            "export_bytes": result.export_bytes,
            "elapsed_ms": result.elapsed_ms,
        }
    )
    for forbidden in ("canary-source-pw", "canary-target-pw", "postgresql://", result.target_db):
        assert forbidden not in rendered
