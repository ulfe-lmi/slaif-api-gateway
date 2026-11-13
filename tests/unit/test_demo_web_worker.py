"""Objective 224-b unit evidence: exact per-request worker handoff + cleanup.

Database-independent: the control plane is driven through a fake
connection/service that simulates the 224-a reviewed law (atomic claim,
handoff refusal, cleanup tail), and the 221/222/223 pipeline stages are
monkeypatched where the custody manifest is the unit under test. Real
role/grant/lock and full-chain evidence lives in
tests/integration/test_demo_web_worker_postgres.py.

Covers: feature-local config validation (no value echo, ordinary
startup unaffected), safe result projections, claim refusal, the
exact-job pipeline (no global-scan promotion), the worker-held
re-read + digest proof, handoff refusals, the structural verified-
copy eviction and fail-closed admission laws (also in
test_demo_snapshot.py), the exact 222/223 selectors, and the bounded
session-aware cleanup law.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import uuid
from pathlib import Path

import pytest

from slaif_gateway.config import Settings
from slaif_gateway.services import demo_snapshot as ds
from slaif_gateway.services import demo_snapshot_files as dsf
from slaif_gateway.services import demo_snapshot_sanitize as dss
from slaif_gateway.services.catalog_refresh import filesystem as catfs
from slaif_gateway.services import demo_web_worker as dww
from slaif_gateway.services.demo_web_control import (
    DemoSnapshotRequestProjection,
    DemoWebControlError,
    VERIFIED_COPY_STATE,
)

REQUEST_ID = uuid.uuid4()
ACCOUNT_ID = uuid.uuid4()
CANARY = "canary-web-worker-9f8e7d6c5b4a"


# --- settings/config harness --------------------------------------------------------


def _settings_dict(custody: Path, passfile: Path, **overrides) -> dict[str, object]:
    base: dict[str, object] = {
        "DEMO_SNAPSHOT_ENABLED": True,
        "DEMO_SNAPSHOT_SOURCE_HOST": "127.0.0.1",
        "DEMO_SNAPSHOT_SOURCE_PORT": 5555,
        "DEMO_SNAPSHOT_SOURCE_DATABASE": "slaif_src",
        "DEMO_SNAPSHOT_SOURCE_USER": "snap_reader",
        "DEMO_SNAPSHOT_TARGET_HOST": "127.0.0.1",
        "DEMO_SNAPSHOT_TARGET_PORT": 5556,
        "DEMO_SNAPSHOT_TARGET_USER": "snap_target",
        "DEMO_SNAPSHOT_TARGET_READER_ROLE": "snap_reader_role",
        "DEMO_SNAPSHOT_PGPASSFILE": str(passfile),
        "DEMO_SNAPSHOT_CUSTODY_DIR": str(custody),
        "DEMO_WEB_WORKER_CONTROL_HOST": "127.0.0.1",
        "DEMO_WEB_WORKER_CONTROL_PORT": 5555,
        "DEMO_WEB_WORKER_CONTROL_DATABASE": "slaif_src",
        "DEMO_WEB_WORKER_CONTROL_USER": "snap_worker",
        "DEMO_WEB_WORKER_CONTROL_PASSWORD": CANARY,
    }
    base.update(overrides)
    return base


def _custody_passfile(tmp_path: Path) -> tuple[Path, Path]:
    custody = tmp_path / "custody"
    custody.mkdir(mode=0o700)
    passfile = tmp_path / "pgpass"
    passfile.write_text(
        "127.0.0.1:5555:slaif_src:snap_reader:canary-src\n"
        "127.0.0.1:5556:*:snap_target:canary-tgt\n",
        encoding="utf-8",
    )
    os.chmod(passfile, 0o600)
    return custody, passfile


def _worker_config(tmp_path: Path, **overrides):
    custody, passfile = _custody_passfile(tmp_path)
    settings = Settings(**_settings_dict(custody, passfile, **overrides))
    return dww.web_worker_config_from_settings(settings), settings, custody, passfile


def _projection(state: str, failure_code: str | None = None) -> DemoSnapshotRequestProjection:
    return DemoSnapshotRequestProjection(
        id=REQUEST_ID,
        account_id=ACCOUNT_ID,
        credential_generation=1,
        state=state,
        failure_code=failure_code,
        worker_job_id=None,
        worker_target_db=None,
        created_at=None,
        deadline_at=None,
        expires_at=None,
    )


# --- fake control plane ---------------------------------------------------------------


class FakeControl:
    """Mimics dww._ControlConnection for unit evidence."""

    def __init__(
        self,
        config,
        *,
        claim_state: str = "claimed",
        handoff_state: str = "verified_unpublished",
        handoff_code: str | None = None,
        handoff_error: str | None = None,
        cleanup_refused: tuple[uuid.UUID, ...] = (),
        candidates: list[dict[str, object]] | None = None,
    ) -> None:
        self.claims: list[uuid.UUID] = []
        self.handoffs: list[tuple[uuid.UUID, object]] = []
        self.failures: list[tuple[uuid.UUID, str]] = []
        self.reaped = 0
        self.cleanup_pending_calls: list[uuid.UUID] = []
        self.cleaned_calls: list[uuid.UUID] = []
        self.claim_state = claim_state
        self.handoff_state = handoff_state
        self.handoff_code = handoff_code
        self.handoff_error = handoff_error
        self.cleanup_refused = set(cleanup_refused)
        self.candidates = candidates if candidates is not None else []
        self.closed = False
        self.sessions = self

    # sessions.begin() and sessions() both yield the fake control as the
    # "session" (the patched service factory ignores it).
    def begin(self) -> "FakeControl":
        return self

    def __call__(self) -> "FakeControl":
        return self

    async def __aenter__(self) -> "FakeControl":
        return self

    async def __aexit__(self, *exc) -> bool:
        return False

    async def close(self) -> None:
        self.closed = True


def _install_fake_control(
    monkeypatch: pytest.MonkeyPatch, control: FakeControl
) -> None:
    monkeypatch.setattr(dww, "_ControlConnection", lambda _config: control)

    async def _candidate_rows(_control, _limit):
        return [dict(row) for row in control.candidates]

    monkeypatch.setattr(dww, "_candidate_rows", _candidate_rows)

    class FakeService:
        def __init__(self, _session):
            pass

        async def claim_request(self, *, request_id):
            control.claims.append(request_id)
            if control.claim_state == "claimed":
                return _projection("claimed")
            return _projection(control.claim_state, control.handoff_code)

        async def record_verified_handoff(self, *, request_id, binding):
            if control.handoff_error is not None:
                raise DemoWebControlError(
                    control.handoff_error, "refused for test evidence."
                )
            control.handoffs.append((request_id, binding))
            return _projection(control.handoff_state, control.handoff_code)

        async def record_worker_failure(self, *, request_id, code):
            control.failures.append((request_id, code))
            return _projection("failed", code)

        async def mark_cleanup_pending(self, *, request_id):
            if request_id in control.cleanup_refused:
                raise DemoWebControlError(
                    "web_cleanup_refused_live_session", "live session (fake)."
                )
            control.cleanup_pending_calls.append(request_id)
            return _projection("cleanup_pending")

        async def mark_cleaned(self, *, request_id):
            control.cleaned_calls.append(request_id)
            return _projection("cleaned")

        async def reap_expired(self, *, limit):
            control.reaped = 3
            return 3

    monkeypatch.setattr(dww, "DemoWebControlService", FakeService)


def _job_id(n: int) -> str:
    return "snap-" + format(n, "032x")


def _target_db(n: int) -> str:
    return "demo_snap_" + format(n, "020x")


def _make_verified_copies(
    custody: Path,
    job: str,
    target: str,
    *,
    corrupt_leaf: bool = False,
    request_id: uuid.UUID = REQUEST_ID,
    extra_leaf: bool = False,
    duplicate_entry: bool = False,
) -> None:
    """Write a custody job in the exact combined verified state, with a
    real 223-conformant files/ tree (flat leaf grammar, 0600,
    files-dir identity, per-leaf inode identity, policy-neutral
    content) and the matching private files manifest."""
    job_dir = custody / job
    job_dir.mkdir(mode=0o700)
    ds.write_manifest(
        job_dir,
        ds.SnapshotManifest(
            job_id=job,
            state=ds.STATE_DB_AND_FILES_VERIFIED_UNPUBLISHED,
            created_at=1000.0,
            target_db=target,
            files_state=dsf.FILES_STATE_VERIFIED,
            files_verified_at=2000.0,
            request_id=str(request_id),
            files_count=1,
            files_bytes=len(dsf.NEUTRAL_MARKDOWN),
        ),
    )
    files_dir = job_dir / dsf.FILES_DIR_NAME
    files_dir.mkdir(mode=0o700)
    payload = dsf.NEUTRAL_MARKDOWN
    leaf_name = "f0001-" + "ab" * 6
    leaf_path = files_dir / leaf_name
    leaf_path.write_bytes(b"tampered" if corrupt_leaf else payload)
    os.chmod(leaf_path, 0o600)
    dir_st = os.stat(files_dir, follow_symlinks=False)
    leaf_st = os.stat(leaf_path, follow_symlinks=False)
    entry = {
        "leaf": leaf_name,
        "logical_name": f"catalog/proposals/{'ab' * 16}/provider-catalog-report.md",
        "kind": dsf.KIND_MARKDOWN,
        "sha256": hashlib.sha256(payload).hexdigest(),
        "bytes": len(payload),
        "inode_identity": [leaf_st.st_dev, leaf_st.st_ino],
        "source": "test",
        "source_ref": "fixed-label",
        "captured_at": 1500.0,
        "source_sha256": hashlib.sha256(b"src").hexdigest(),
    }
    manifest_doc = {
        "schema_version": 1,
        "state": dsf.FILES_STATE_VERIFIED,
        "files": [dict(entry), dict(entry)] if duplicate_entry else [dict(entry)],
        "files_dir_identity": [dir_st.st_dev, dir_st.st_ino],
        "not_configured": [],
        "source_records": {},
    }
    (files_dir / dsf.FILES_MANIFEST_NAME).write_text(
        __import__("json").dumps(manifest_doc, sort_keys=True) + "\n", encoding="utf-8"
    )
    if extra_leaf:
        extra = files_dir / ("f0002-" + "cd" * 6)
        extra.write_bytes(dsf.NEUTRAL_MARKDOWN)
        os.chmod(extra, 0o600)


def _pipeline_success(
    monkeypatch: pytest.MonkeyPatch, job: str, target: str
) -> dict[str, list]:
    calls: dict[str, list] = {"snapshot": [], "sanitize": [], "files": []}

    def fake_snapshot(config, **kwargs):
        calls["snapshot"].append((config, kwargs))
        return ds.DemoSnapshotJobResult(
            state=ds.STATE_RAW_UNVERIFIED,
            failure_code=None,
            export_bytes=10,
            elapsed_ms=1,
            job_id=job,
            target_db=target,
        )

    monkeypatch.setattr(ds, "run_snapshot_job", fake_snapshot)

    def fake_sanitize(config, *, job_id=None):
        calls["sanitize"].append(job_id)
        return dss.SanitizeCopiesResult(
            dss.SANITIZE_STATE_SANITIZED, None, 1, 0, 1
        )

    monkeypatch.setattr(dss, "sanitize_copies", fake_sanitize)

    def fake_files(config, settings, *, job_id=None):
        calls["files"].append(job_id)
        return dsf.FilesJobResult(
            state="FILES_VERIFIED",
            copies_files_verified=1,
            copies_failed=0,
            elapsed_ms=1,
        )

    monkeypatch.setattr(dsf, "run_files_job", fake_files)

    def fake_ingest(config, job_id, request_id, target_db):
        # 224-g: the target-only demo_display ingest is database-side
        # evidence; unit tests substitute the recorded no-op seam.
        calls["ingest"].append((job_id, request_id, target_db))

    calls["ingest"] = []
    monkeypatch.setattr(dww, "_ingest_verified_display", fake_ingest)
    return calls


# --- config ------------------------------------------------------------------------


def test_config_missing_fields_raise_safe_misconfigured(tmp_path: Path) -> None:
    custody, passfile = _custody_passfile(tmp_path)
    for missing in (
        "DEMO_WEB_WORKER_CONTROL_HOST",
        "DEMO_WEB_WORKER_CONTROL_DATABASE",
        "DEMO_WEB_WORKER_CONTROL_USER",
        "DEMO_WEB_WORKER_CONTROL_PASSWORD",
    ):
        d = _settings_dict(custody, passfile)
        d[missing] = ""
        with pytest.raises(dww.DemoWebWorkerError) as exc:
            dww.web_worker_config_from_settings(Settings(**d))
        assert exc.value.code == dww.CODE_WORKER_MISCONFIGURED
        assert CANARY not in exc.value.safe_message


def test_config_bad_identifier_or_port_refused(tmp_path: Path) -> None:
    custody, passfile = _custody_passfile(tmp_path)
    d = _settings_dict(custody, passfile, DEMO_WEB_WORKER_CONTROL_USER="Bad-User")
    with pytest.raises(dww.DemoWebWorkerError) as exc:
        dww.web_worker_config_from_settings(Settings(**d))
    assert exc.value.code == dww.CODE_WORKER_MISCONFIGURED
    assert "Bad-User" not in exc.value.safe_message
    d = _settings_dict(custody, passfile, DEMO_WEB_WORKER_CONTROL_PORT=99999)
    with pytest.raises(dww.DemoWebWorkerError):
        dww.web_worker_config_from_settings(Settings(**d))


def test_config_wraps_demo_off_and_password_never_in_repr(tmp_path: Path) -> None:
    custody, passfile = _custody_passfile(tmp_path)
    d = _settings_dict(custody, passfile, DEMO_SNAPSHOT_ENABLED=False)
    with pytest.raises(dww.DemoWebWorkerError) as exc:
        dww.web_worker_config_from_settings(Settings(**d))
    assert exc.value.code == dww.CODE_WORKER_MISCONFIGURED
    config = dww.web_worker_config_from_settings(
        Settings(**_settings_dict(custody, passfile))
    )
    assert CANARY not in repr(config)


def test_ordinary_gateway_startup_unaffected_by_demo_settings() -> None:
    # Feature-local validation: a plain Settings() with no demo
    # configuration at all must construct (no model-validator coupling).
    settings = Settings()
    assert settings.DEMO_SNAPSHOT_ENABLED is False
    assert settings.DEMO_WEB_WORKER_CONTROL_HOST == ""


# --- process_request -----------------------------------------------------------------


def test_process_request_claim_refused_runs_no_pipeline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, settings, custody, _ = _worker_config(tmp_path)
    control = FakeControl(config, claim_state="failed", handoff_code="worker_failed")
    _install_fake_control(monkeypatch, control)
    calls = _pipeline_success(monkeypatch, _job_id(1), _target_db(1))
    result = asyncio.run(
        dww.process_request(config, settings, request_id=REQUEST_ID)
    )
    assert result.state == "claim_refused"
    assert result.failure_code == "worker_failed"
    assert calls == {"snapshot": [], "sanitize": [], "files": [], "ingest": []}
    assert control.handoffs == [] and control.failures == []
    assert "job" not in result.to_safe_dict()
    assert control.closed


def test_process_request_happy_path_publishes_exact_binding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, settings, custody, _ = _worker_config(tmp_path)
    job, target = _job_id(7), _target_db(7)
    _make_verified_copies(custody, job, target)
    control = FakeControl(config)
    _install_fake_control(monkeypatch, control)
    calls = _pipeline_success(monkeypatch, job, target)
    grants: list[str] = []
    monkeypatch.setattr(dww, "_grant_target_reader",
                        lambda cfg, db: grants.append(db))
    result = asyncio.run(
        dww.process_request(config, settings, request_id=REQUEST_ID)
    )
    assert result.state == "verified_unpublished"
    assert result.failure_code is None
    # 224-d: the exact verified copy was published to the reader role
    # exactly once (and the proof preceded it: the grant ran only
    # because the pipeline succeeded).
    assert grants == [target]
    # The exact job was selected everywhere; the worker passes no
    # protected set (the 221 structural law protects verified copies
    # itself - the redundant 224-b set was removed in 224-c).
    assert calls["sanitize"] == [job] and calls["files"] == [job]
    assert "protected_job_ids" not in calls["snapshot"][0][1]
    (rid, binding) = control.handoffs[0]
    assert rid == REQUEST_ID
    assert binding.worker_job_id == job
    assert binding.worker_target_db == target
    assert binding.manifest_state == VERIFIED_COPY_STATE
    assert control.failures == []
    safe = result.to_safe_dict()
    assert job not in str(safe) and target not in str(safe)


def test_process_request_221_failure_records_and_stops(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, settings, custody, _ = _worker_config(tmp_path)
    control = FakeControl(config)
    _install_fake_control(monkeypatch, control)
    calls = _pipeline_success(monkeypatch, _job_id(1), _target_db(1))

    def failing_snapshot(cfg, **kwargs):
        calls["snapshot"].append(kwargs)
        return ds.DemoSnapshotJobResult(
            state=ds.STATE_FAILED,
            failure_code=ds.CODE_TARGET_RESTORE_FAILED,
            export_bytes=0,
            elapsed_ms=1,
            job_id="",
        )

    monkeypatch.setattr(ds, "run_snapshot_job", failing_snapshot)
    result = asyncio.run(
        dww.process_request(config, settings, request_id=REQUEST_ID)
    )
    assert result.state == "failed"
    assert result.failure_code == ds.CODE_TARGET_RESTORE_FAILED
    assert control.failures == [(REQUEST_ID, "worker_failed")]
    assert control.handoffs == []
    assert calls["sanitize"] == [] and calls["files"] == []


def test_process_request_223_failure_records_and_stops(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, settings, custody, _ = _worker_config(tmp_path)
    job, target = _job_id(2), _target_db(2)
    _make_verified_copies(custody, job, target)
    control = FakeControl(config)
    _install_fake_control(monkeypatch, control)
    _pipeline_success(monkeypatch, job, target)

    def failing_files(config_, settings_, *, job_id=None):
        return dsf.FilesJobResult(
            state="FAILED",
            copies_files_verified=0,
            copies_failed=1,
            elapsed_ms=1,
            failure_code="FILES_VERIFY_FAILED",
        )

    monkeypatch.setattr(dsf, "run_files_job", failing_files)
    result = asyncio.run(
        dww.process_request(config, settings, request_id=REQUEST_ID)
    )
    assert result.state == "failed"
    assert result.failure_code == "FILES_VERIFY_FAILED"
    assert control.handoffs == []
    assert control.failures == [(REQUEST_ID, "worker_failed")]


def test_process_request_digest_mismatch_refuses_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, settings, custody, _ = _worker_config(tmp_path)
    job, target = _job_id(3), _target_db(3)
    _make_verified_copies(custody, job, target, corrupt_leaf=True)
    control = FakeControl(config)
    _install_fake_control(monkeypatch, control)
    _pipeline_success(monkeypatch, job, target)
    result = asyncio.run(
        dww.process_request(config, settings, request_id=REQUEST_ID)
    )
    assert result.state == "failed"
    assert result.failure_code == "worker_failed"
    assert control.handoffs == []


def test_process_request_foreign_leaf_in_tree_refuses_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """224-b proof law: a foreign entry in the held files/ tree (not in
    the manifest) breaks the exact-leaf-set law - no publication."""
    config, settings, custody, _ = _worker_config(tmp_path)
    job, target = _job_id(30), _target_db(30)
    _make_verified_copies(custody, job, target, extra_leaf=True)
    control = FakeControl(config)
    _install_fake_control(monkeypatch, control)
    _pipeline_success(monkeypatch, job, target)
    result = asyncio.run(
        dww.process_request(config, settings, request_id=REQUEST_ID)
    )
    assert result.state == "failed"
    assert result.failure_code == "worker_failed"
    assert control.handoffs == []


def test_process_request_duplicate_manifest_entry_refuses_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """224-b proof law: a duplicated leaf name in the private files
    manifest breaks the name-uniqueness law - no publication."""
    config, settings, custody, _ = _worker_config(tmp_path)
    job, target = _job_id(31), _target_db(31)
    _make_verified_copies(custody, job, target, duplicate_entry=True)
    control = FakeControl(config)
    _install_fake_control(monkeypatch, control)
    _pipeline_success(monkeypatch, job, target)
    result = asyncio.run(
        dww.process_request(config, settings, request_id=REQUEST_ID)
    )
    assert result.state == "failed"
    assert result.failure_code == "worker_failed"
    assert control.handoffs == []


def test_process_request_leaf_inode_drift_refuses_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """224-b proof law: a leaf REWRITTEN with identical bytes (digest
    still matches) but a new inode breaks the per-leaf inode-identity
    law - the digest alone cannot prove placement - no publication."""
    config, settings, custody, _ = _worker_config(tmp_path)
    job, target = _job_id(32), _target_db(32)
    _make_verified_copies(custody, job, target)
    leaf = custody / job / dsf.FILES_DIR_NAME / ("f0001-" + "ab" * 6)
    payload = leaf.read_bytes()
    # Hold the old leaf open so its inode stays ALLOCATED during the
    # replacement: the rewritten file then deterministically gets a
    # DIFFERENT inode (an unlink/rewrite can reuse a freed inode on
    # some CI filesystems, which would silently flip this negative).
    old_fd = os.open(leaf, os.O_RDONLY)
    try:
        leaf.unlink()  # new inode, identical content
        leaf.write_bytes(payload)
        os.chmod(leaf, 0o600)
        control = FakeControl(config)
        _install_fake_control(monkeypatch, control)
        _pipeline_success(monkeypatch, job, target)
        result = asyncio.run(
            dww.process_request(config, settings, request_id=REQUEST_ID)
        )
        assert result.state == "failed"
        assert result.failure_code == "worker_failed"
        assert control.handoffs == []
    finally:
        os.close(old_fd)


def test_process_request_job_directory_rebind_refuses_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """224-b proof law: the job directory swapped for a symlink between
    the pipeline and the proof cannot redirect the anchored read - the
    no-follow boundary refuses and nothing is published."""
    config, settings, custody, _ = _worker_config(tmp_path)
    job, target = _job_id(33), _target_db(33)
    _make_verified_copies(custody, job, target)
    job_dir = custody / job
    real = custody / (job + "-real")
    job_dir.rename(real)
    os.symlink(real, job_dir)
    control = FakeControl(config)
    _install_fake_control(monkeypatch, control)
    _pipeline_success(monkeypatch, job, target)
    result = asyncio.run(
        dww.process_request(config, settings, request_id=REQUEST_ID)
    )
    assert result.state == "failed"
    assert result.failure_code == "worker_failed"
    assert control.handoffs == []


def test_process_request_job_identity_drift_between_reads_refuses_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """224-b binding law: a job directory swapped AFTER the main-manifest
    read but BEFORE the files re-proof opens its own handle cannot pair
    manifest A with files tree B - the exact job-directory identity
    captured by the first held handle is required by the second."""
    config, settings, custody, _ = _worker_config(tmp_path)
    job, target = _job_id(34), _target_db(34)
    _make_verified_copies(custody, job, target)
    job_dir = custody / job

    real_read = catfs.anchored_read_fd
    state = {"swapped": False}

    def swapping_read(dir_fd, name, cap):
        data = real_read(dir_fd, name, cap)
        if not state["swapped"]:
            state["swapped"] = True
            # Swap the job directory right after the main-manifest read
            # (open + name binding already saw the original directory):
            # a later fresh open resolves a DIFFERENT directory.
            job_dir.rename(job_dir.parent / (job + "-real"))
            job_dir.mkdir(mode=0o700)
        return data

    monkeypatch.setattr(catfs, "anchored_read_fd", swapping_read)
    control = FakeControl(config)
    _install_fake_control(monkeypatch, control)
    _pipeline_success(monkeypatch, job, target)
    result = asyncio.run(
        dww.process_request(config, settings, request_id=REQUEST_ID)
    )
    assert result.state == "failed"
    assert result.failure_code == "worker_failed"
    assert control.handoffs == []


def test_process_request_files_totals_mismatch_refuses_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """224-b binding law: the main manifest's recorded files totals must
    equal the re-proven totals; a tampered count is a refusal even
    though every leaf digest and identity still agrees."""
    config, settings, custody, _ = _worker_config(tmp_path)
    job, target = _job_id(35), _target_db(35)
    _make_verified_copies(custody, job, target)
    manifest = ds.read_manifest(custody / job)
    assert manifest is not None
    manifest.files_count = manifest.files_count + 1
    ds.write_manifest(custody / job, manifest)
    control = FakeControl(config)
    _install_fake_control(monkeypatch, control)
    _pipeline_success(monkeypatch, job, target)
    result = asyncio.run(
        dww.process_request(config, settings, request_id=REQUEST_ID)
    )
    assert result.state == "failed"
    assert result.failure_code == "worker_failed"
    assert control.handoffs == []


def test_process_request_manifest_state_mismatch_refuses_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, settings, custody, _ = _worker_config(tmp_path)
    job, target = _job_id(4), _target_db(4)
    _make_verified_copies(custody, job, target)
    # Demote the manifest: the pipeline claimed success but the
    # worker-held custody disagrees -> no publication.
    job_dir = custody / job
    manifest = ds.read_manifest(job_dir)
    assert manifest is not None
    manifest.state = ds.STATE_DB_SANITIZED_UNPUBLISHED
    ds.write_manifest(job_dir, manifest)
    control = FakeControl(config)
    _install_fake_control(monkeypatch, control)
    _pipeline_success(monkeypatch, job, target)
    result = asyncio.run(
        dww.process_request(config, settings, request_id=REQUEST_ID)
    )
    assert result.state == "failed"
    assert control.handoffs == []


def test_process_request_handoff_refusal_reports_finite_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, settings, custody, _ = _worker_config(tmp_path)
    job, target = _job_id(5), _target_db(5)
    _make_verified_copies(custody, job, target)
    control = FakeControl(
        config, handoff_state="failed", handoff_code="state_conflict"
    )
    _install_fake_control(monkeypatch, control)
    _pipeline_success(monkeypatch, job, target)

    def grant_guard(cfg, db):
        # 224-d ordering law: the publication grant happens BEFORE any
        # handoff attempt (the copy is made readable only now, and the
        # handoff may not precede it).
        assert db == target
        assert control.handoffs == []

    monkeypatch.setattr(dww, "_grant_target_reader", grant_guard)
    result = asyncio.run(
        dww.process_request(config, settings, request_id=REQUEST_ID)
    )
    assert result.state == "failed"
    assert result.failure_code == "state_conflict"
    # The handoff WAS attempted exactly once (the refusal came back),
    # AFTER the guard-proven grant (asserted in-flight above); the
    # refusal marks the request failed promptly (224-d: the granted
    # copy must not wait on the claim lease reap for cleanup).
    assert len(control.handoffs) == 1
    assert control.failures == [(REQUEST_ID, "worker_failed")]


def test_process_request_control_error_maps_to_safe_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, settings, custody, _ = _worker_config(tmp_path)
    job, target = _job_id(6), _target_db(6)
    _make_verified_copies(custody, job, target)
    control = FakeControl(config, handoff_error="web_request_not_claimed")
    _install_fake_control(monkeypatch, control)
    _pipeline_success(monkeypatch, job, target)
    monkeypatch.setattr(dww, "_grant_target_reader", lambda cfg, db: None)
    result = asyncio.run(
        dww.process_request(config, settings, request_id=REQUEST_ID)
    )
    assert result.state == "failed"
    assert result.failure_code == "web_request_not_claimed"
    # Prompt guarded failure mark (no-op in production if the row
    # already moved; the fake accepts it).
    assert control.failures == [(REQUEST_ID, "worker_failed")]


def test_process_request_unexpected_exception_safe_internal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, settings, custody, _ = _worker_config(tmp_path)
    control = FakeControl(config)
    _install_fake_control(monkeypatch, control)

    def boom(cfg, **kwargs):
        raise RuntimeError("internal")

    monkeypatch.setattr(ds, "run_snapshot_job", boom)
    result = asyncio.run(
        dww.process_request(config, settings, request_id=REQUEST_ID)
    )
    assert result.state == "failed"
    assert result.failure_code == dww.CODE_WORKER_INTERNAL
    assert control.failures == [(REQUEST_ID, "worker_failed")]
    assert control.closed


# --- exact 222/223 selectors ----------------------------------------------------------


def _make_raw_copy(custody: Path, n: int) -> str:
    job = _job_id(n)
    job_dir = custody / job
    job_dir.mkdir(mode=0o700)
    ds.write_manifest(
        job_dir,
        ds.SnapshotManifest(
            job_id=job,
            state=ds.STATE_RAW_UNVERIFIED,
            created_at=1000.0,
            target_db=_target_db(n),
        ),
    )
    return job


def _fake_sanitizer(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    seen: list[str] = []

    async def fake(config, job_dir, manifest, deadline):
        seen.append(manifest.job_id)
        manifest.state = ds.STATE_DB_SANITIZED_UNPUBLISHED
        manifest.failure_code = None
        ds.write_manifest(job_dir, manifest)
        return dss.SanitizeCopyResult(
            dss.SANITIZE_STATE_PROMOTED, None, manifest.job_id
        )

    monkeypatch.setattr(dss, "_sanitize_copy_async", fake)
    return seen


def test_sanitize_exact_job_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    custody, passfile = _custody_passfile(tmp_path)
    settings = Settings(**_settings_dict(custody, passfile))
    config = ds.config_from_settings(settings)
    a, b = _make_raw_copy(custody, 21), _make_raw_copy(custody, 22)
    seen = _fake_sanitizer(monkeypatch)

    result = dss.sanitize_copies(config, job_id=a)
    assert result.state == dss.SANITIZE_STATE_SANITIZED
    assert (result.copies_sanitized, result.copies_failed) == (1, 0)
    assert seen == [a]
    # The unrelated pre-existing copy is untouched (still RAW).
    mb = ds.read_manifest(custody / b)
    assert mb is not None and mb.state == ds.STATE_RAW_UNVERIFIED

    # Global scan (unchanged contract) still processes every RAW copy.
    seen.clear()
    result = dss.sanitize_copies(config)
    assert result.state == dss.SANITIZE_STATE_SANITIZED
    assert result.copies_sanitized == 1  # only b remains RAW (a already done)
    assert seen == [b]


def test_sanitize_exact_job_missing_or_inconsistent(tmp_path: Path) -> None:
    custody, passfile = _custody_passfile(tmp_path)
    settings = Settings(**_settings_dict(custody, passfile))
    config = ds.config_from_settings(settings)
    for bad in ("snap-" + "0" * 32, "not-a-job", "snap-Z" * 11):
        result = dss.sanitize_copies(config, job_id=bad)
        assert result.state == dss.SANITIZE_STATE_FAILED
        assert result.failure_code == ds.CODE_EXACT_COPY_UNAVAILABLE
        assert (result.copies_sanitized, result.copies_failed) == (0, 1)
    # Directory exists but the manifest names a DIFFERENT job id.
    job_dir = custody / (_job_id(31))
    job_dir.mkdir(mode=0o700)
    ds.write_manifest(
        job_dir,
        ds.SnapshotManifest(
            job_id=_job_id(32),
            state=ds.STATE_RAW_UNVERIFIED,
            created_at=1.0,
            target_db=_target_db(31),
        ),
    )
    result = dss.sanitize_copies(config, job_id=_job_id(31))
    assert result.failure_code == ds.CODE_EXACT_COPY_UNAVAILABLE


def test_sanitize_exact_job_already_sanitized_is_noop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    custody, passfile = _custody_passfile(tmp_path)
    settings = Settings(**_settings_dict(custody, passfile))
    config = ds.config_from_settings(settings)
    job = _make_raw_copy(custody, 41)
    job_dir = custody / job
    manifest = ds.read_manifest(job_dir)
    assert manifest is not None
    manifest.state = ds.STATE_DB_SANITIZED_UNPUBLISHED
    ds.write_manifest(job_dir, manifest)
    seen = _fake_sanitizer(monkeypatch)
    result = dss.sanitize_copies(config, job_id=job)
    assert result.state == dss.SANITIZE_STATE_SANITIZED
    assert (result.copies_sanitized, result.copies_failed) == (0, 0)
    assert seen == []


def _files_config(custody: Path) -> dsf.FileSnapshotConfig:
    return dsf.FileSnapshotConfig(
        custody_dir=custody,
        catalog_root=None,
        catalog_seal_key=None,
        branding_dir=None,
        completion_profile_dir=None,
        upstream_llm_profiles_file=None,
        public_base_url_configured=False,
        max_file_bytes=32 * 1024 * 1024,
        max_total_bytes=128 * 1024 * 1024,
        max_elapsed_seconds=300,
    )


def test_files_exact_already_verified_is_noop(tmp_path: Path) -> None:
    custody, passfile = _custody_passfile(tmp_path)
    settings = Settings(**_settings_dict(custody, passfile))
    job, target = _job_id(51), _target_db(51)
    _make_verified_copies(custody, job, target)
    result = dsf.run_files_job(_files_config(custody), settings, job_id=job)
    assert result.state == "FILES_VERIFIED"
    assert (result.copies_files_verified, result.copies_failed) == (0, 0)
    assert result.failure_code is None


def test_files_exact_missing_refused(tmp_path: Path) -> None:
    custody, passfile = _custody_passfile(tmp_path)
    settings = Settings(**_settings_dict(custody, passfile))
    result = dsf.run_files_job(
        _files_config(custody), settings, job_id=_job_id(52)
    )
    assert result.state == "FAILED"
    assert result.failure_code == ds.CODE_EXACT_COPY_UNAVAILABLE
    assert (result.copies_files_verified, result.copies_failed) == (0, 1)


def test_files_exact_sanitized_job_runs_only_that_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    custody, passfile = _custody_passfile(tmp_path)
    settings = Settings(**_settings_dict(custody, passfile))
    job = _make_raw_copy(custody, 61)
    job_dir = custody / job
    manifest = ds.read_manifest(job_dir)
    assert manifest is not None
    manifest.state = ds.STATE_DB_SANITIZED_UNPUBLISHED
    ds.write_manifest(job_dir, manifest)
    # A foreign pre-existing verified copy that must NOT be touched.
    foreign = _job_id(62)
    _make_verified_copies(custody, foreign, _target_db(62))

    monkeypatch.setattr(
        dsf, "capture_all", lambda config, settings_, seed: object()
    )
    monkeypatch.setattr(dsf, "_write_files", lambda job_dir_, capture: {})
    monkeypatch.setattr(
        dsf, "verify_files", lambda job_dir_, manifest_, config_, deadline: None
    )
    monkeypatch.setattr(
        dsf, "_completion_link_gate", lambda job_dir_, base, db, deadline: None
    )
    result = dsf.run_files_job(_files_config(custody), settings, job_id=job)
    assert result.state == "FILES_VERIFIED"
    assert (result.copies_files_verified, result.copies_failed) == (1, 0)
    done = ds.read_manifest(job_dir)
    assert done is not None
    assert done.state == ds.STATE_DB_AND_FILES_VERIFIED_UNPUBLISHED
    assert done.files_state == dsf.FILES_STATE_VERIFIED
    foreign_m = ds.read_manifest(custody / foreign)
    assert foreign_m is not None
    assert foreign_m.state == ds.STATE_DB_AND_FILES_VERIFIED_UNPUBLISHED
    assert foreign_m.job_id == foreign


# --- bounded recovery/cleanup ---------------------------------------------------------


def test_recover_and_cleanup_matrix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, _, custody, _ = _worker_config(tmp_path)
    # One bound copy with a real custody job (cleanup will "drop" it).
    bound_job = _job_id(71)
    bound_db = _target_db(71)
    job_dir = custody / bound_job
    job_dir.mkdir(mode=0o700)
    ds.write_manifest(
        job_dir,
        ds.SnapshotManifest(
            job_id=bound_job,
            state=ds.STATE_DB_AND_FILES_VERIFIED_UNPUBLISHED,
            created_at=1.0,
            target_db=bound_db,
        ),
    )
    # A mismatched copy: manifest says a DIFFERENT target db.
    mismatch_job = _job_id(72)
    job_dir2 = custody / mismatch_job
    job_dir2.mkdir(mode=0o700)
    ds.write_manifest(
        job_dir2,
        ds.SnapshotManifest(
            job_id=mismatch_job,
            state=ds.STATE_DB_AND_FILES_VERIFIED_UNPUBLISHED,
            created_at=1.0,
            target_db="demo_snap_" + "1" * 20,
        ),
    )

    ok_id = uuid.uuid4()
    mismatch_id = uuid.uuid4()
    refused_id = uuid.uuid4()
    bare_failed_id = uuid.uuid4()
    control = FakeControl(
        config,
        candidates=[
            {"id": bare_failed_id, "state": "failed", "worker_job_id": None, "worker_target_db": None},
            {"id": refused_id, "state": "verified_unpublished", "worker_job_id": None, "worker_target_db": None},
            {"id": ok_id, "state": "cleanup_pending", "worker_job_id": bound_job, "worker_target_db": bound_db},
            {"id": mismatch_id, "state": "cleanup_pending", "worker_job_id": mismatch_job, "worker_target_db": "demo_snap_ffffffffffffffffffff"},
        ],
        cleanup_refused=(refused_id,),
    )
    _install_fake_control(monkeypatch, control)

    drops: list[str] = []
    db_state = {"exists": True}

    class _FakeOps(ds.TargetOps):
        def __init__(self):
            super().__init__(
                create_database=lambda name, deadline: None,
                restore=lambda archive, name, deadline: None,
                drop_database=lambda name: (
                    drops.append(name), db_state.update(exists=False), True
                )[2],
                database_exists=lambda name: db_state["exists"],
            )

    monkeypatch.setattr(ds, "_target_ops", lambda config_, **kw: _FakeOps())

    result = asyncio.run(dww.recover_and_cleanup(config))
    assert result.reaped == 3
    # failed (no binding) -> cleaned directly; refused stays untouched;
    # bound copy -> artifacts removed then cleaned; mismatch retained.
    assert ok_id in control.cleaned_calls
    assert bare_failed_id in control.cleaned_calls
    assert mismatch_id not in control.cleaned_calls
    assert refused_id not in control.cleaned_calls
    assert result.cleaned == 2
    assert result.retained == 2
    assert drops == [bound_db]  # ONLY the bound database
    # Manifest of the cleaned copy follows the 221 law.
    cleaned_m = ds.read_manifest(job_dir)
    assert cleaned_m is not None and cleaned_m.state == ds.STATE_CLEANED
    # The mismatched copy is retained exactly as found (inspectable).
    mm = ds.read_manifest(job_dir2)
    assert mm is not None
    assert mm.state == ds.STATE_DB_AND_FILES_VERIFIED_UNPUBLISHED
    assert control.closed


def test_recover_and_cleanup_failure_retains_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, _, custody, _ = _worker_config(tmp_path)
    job = _job_id(81)
    db = _target_db(81)
    job_dir = custody / job
    job_dir.mkdir(mode=0o700)
    ds.write_manifest(
        job_dir,
        ds.SnapshotManifest(
            job_id=job,
            state=ds.STATE_DB_AND_FILES_VERIFIED_UNPUBLISHED,
            created_at=1.0,
            target_db=db,
        ),
    )
    rid = uuid.uuid4()
    control = FakeControl(
        config,
        candidates=[
            {"id": rid, "state": "cleanup_pending", "worker_job_id": job, "worker_target_db": db},
        ],
    )
    _install_fake_control(monkeypatch, control)
    monkeypatch.setattr(
        ds, "_target_ops",
        lambda config_, **kw: ds.TargetOps(
            create_database=lambda name, deadline: None,
            drop_database=lambda name: True,
            restore=lambda archive, name, deadline: None,
            database_exists=lambda name: True,
        ),
    )
    monkeypatch.setattr(ds, "_cleanup_artifacts", lambda ops, job_dir_, db_: False)
    result = asyncio.run(dww.recover_and_cleanup(config))
    assert result.cleaned == 0
    assert result.retained == 1
    assert result.failure_code == ds.CODE_CLEANUP_FAILED
    assert rid not in control.cleaned_calls
    # The manifest records the inspectable cleanup failure.
    m = ds.read_manifest(job_dir)
    assert m is not None and m.state == ds.STATE_CLEANUP_FAILED
    assert m.failure_code == ds.CODE_CLEANUP_FAILED


def test_recover_and_cleanup_limit_validation(tmp_path: Path) -> None:
    config, _, _, _ = _worker_config(tmp_path)

    async def run(limit: int):
        return await dww.recover_and_cleanup(config, limit=limit)

    for limit in (0, 101):
        with pytest.raises(dww.DemoWebWorkerError) as exc:
            asyncio.run(run(limit))
        assert exc.value.code == dww.CODE_WORKER_MISCONFIGURED


# --- CLI safe output -------------------------------------------------------------------


def test_cli_misconfig_emits_safe_code_no_canary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    custody, passfile = _custody_passfile(tmp_path)
    for key, value in _settings_dict(custody, passfile).items():
        monkeypatch.setenv(str(key), str(value))
    monkeypatch.setenv("DEMO_WEB_WORKER_CONTROL_HOST", "")  # gap
    from typer.testing import CliRunner

    from slaif_gateway.cli.demo_snapshot_worker import app

    runner = CliRunner()
    result = runner.invoke(app, ["process-request", str(REQUEST_ID), "--json"])
    assert result.exit_code == 1
    assert "WEB_WORKER_MISCONFIGURED" in result.output
    assert CANARY not in result.output
    result = runner.invoke(app, ["cleanup", "--json"])
    assert result.exit_code == 1
    assert "WEB_WORKER_MISCONFIGURED" in result.output
    assert CANARY not in result.output


# --- request ownership association (224-b review) ------------------------------------


def test_process_request_binds_request_id_into_private_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, settings, custody, _ = _worker_config(tmp_path)
    job, target = _job_id(91), _target_db(91)
    # The pipeline fake leaves the verified manifest (with the durable
    # request association written by the 221 stage) in place.
    _make_verified_copies(custody, job, target, request_id=REQUEST_ID)
    control = FakeControl(config)
    _install_fake_control(monkeypatch, control)
    calls = _pipeline_success(monkeypatch, job, target)
    monkeypatch.setattr(dww, "_grant_target_reader", lambda cfg, db: None)
    result = asyncio.run(
        dww.process_request(config, settings, request_id=REQUEST_ID)
    )
    assert result.state == "verified_unpublished"
    job_dir = custody / job
    manifest = ds.read_manifest(job_dir)
    assert manifest is not None
    assert manifest.request_id == str(REQUEST_ID)
    # The 221 stage was invoked with the durable request binding and
    # NO protected set: the structural verified-copy law in
    # _expire_copies protects published copies by state (224-c: the
    # redundant worker-derived set was removed).
    snapshot_kwargs = calls["snapshot"][0][1]
    assert snapshot_kwargs["request_id"] == str(REQUEST_ID)
    assert "protected_job_ids" not in snapshot_kwargs
    # And the worker's proof required exactly that association.
    (rid, binding) = control.handoffs[0]
    assert rid == REQUEST_ID and binding.worker_job_id == job


def test_process_request_foreign_request_binding_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A manifest bound to ANOTHER request can never pass the worker's
    proof, even if every digest and state agrees."""
    config, settings, custody, _ = _worker_config(tmp_path)
    job, target = _job_id(92), _target_db(92)
    other_request = uuid.uuid4()
    _make_verified_copies(custody, job, target)
    job_dir = custody / job
    manifest = ds.read_manifest(job_dir)
    assert manifest is not None
    manifest.request_id = str(other_request)
    ds.write_manifest(job_dir, manifest)
    control = FakeControl(config)
    _install_fake_control(monkeypatch, control)
    _pipeline_success(monkeypatch, job, target)
    result = asyncio.run(
        dww.process_request(config, settings, request_id=REQUEST_ID)
    )
    assert result.state == "failed"
    assert result.failure_code == "worker_failed"
    assert control.handoffs == []


def _bound_failed_job(custody: Path, n: int, request_id: uuid.UUID) -> tuple[str, str]:
    job = _job_id(n)
    job_dir = custody / job
    job_dir.mkdir(mode=0o700)
    ds.write_manifest(
        job_dir,
        ds.SnapshotManifest(
            job_id=job,
            state=ds.STATE_DB_AND_FILES_VERIFIED_UNPUBLISHED,
            created_at=1.0,
            target_db=_target_db(n),
            request_id=str(request_id),
        ),
    )
    return job, _target_db(n)


def test_recover_and_cleanup_finds_unbound_owned_job(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """224-b review: a failed request with NO published control binding
    still has its exact owned job found through the private custody
    association and removed; foreign jobs are never touched."""
    config, _, custody, _ = _worker_config(tmp_path)
    rid_owned = uuid.uuid4()
    rid_ghost = uuid.uuid4()  # its request row is NOT in this scan
    rid_none = uuid.uuid4()
    job, db = _bound_failed_job(custody, 93, rid_owned)
    foreign_job, foreign_db = _bound_failed_job(custody, 94, rid_ghost)

    control = FakeControl(
        config,
        candidates=[
            {"id": rid_owned, "state": "failed", "worker_job_id": None, "worker_target_db": None},
            {"id": rid_none, "state": "failed", "worker_job_id": None, "worker_target_db": None},
        ],
    )
    _install_fake_control(monkeypatch, control)
    drops: list[str] = []
    db_state = {"exists": True}

    class _FakeOps(ds.TargetOps):
        def __init__(self):
            super().__init__(
                create_database=lambda name, deadline: None,
                drop_database=lambda name: (
                    drops.append(name), db_state.update(exists=False), True
                )[2],
                restore=lambda archive, name, deadline: None,
                database_exists=lambda name: db_state["exists"],
            )

    monkeypatch.setattr(ds, "_target_ops", lambda config_, **kw: _FakeOps())

    result = asyncio.run(dww.recover_and_cleanup(config))
    # The owned job is found via its private association and removed;
    # the foreign job (bound to a request outside this scan) is
    # untouched; the binding-less request with no job is cleaned
    # directly.
    assert drops == [db]
    assert foreign_db not in drops
    assert rid_owned in control.cleaned_calls
    assert rid_none in control.cleaned_calls
    assert result.cleaned == 2
    assert result.retained == 0
    m = ds.read_manifest(custody / job)
    assert m is not None and m.state == ds.STATE_CLEANED
    fm = ds.read_manifest(custody / foreign_job)
    assert fm is not None
    assert fm.state == ds.STATE_DB_AND_FILES_VERIFIED_UNPUBLISHED


class _RecordingOps(ds.TargetOps):
    """Fake target ops recording every drop (224-b recovery tests)."""

    def __init__(self, drops: list[str], db_state: dict[str, bool]) -> None:
        super().__init__(
            create_database=lambda name, deadline: None,
            drop_database=lambda name: (
                drops.append(name),
                db_state.update(exists=False),
                True,
            )[2],
            restore=lambda archive, name, deadline: None,
            database_exists=lambda name: db_state["exists"],
        )


def test_recover_and_cleanup_double_bound_request_retained(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """224-b fail-closed: TWO custody manifests binding the SAME request
    is an ownership-invariant violation - the row is retained with a
    finite failure code and NO artifact is removed."""
    config, _, custody, _ = _worker_config(tmp_path)
    rid_dup = uuid.uuid4()
    job_a, db_a = _bound_failed_job(custody, 95, rid_dup)
    job_b, db_b = _bound_failed_job(custody, 96, rid_dup)
    control = FakeControl(
        config,
        candidates=[
            {
                "id": rid_dup,
                "state": "failed",
                "worker_job_id": None,
                "worker_target_db": None,
            },
        ],
    )
    _install_fake_control(monkeypatch, control)
    drops: list[str] = []
    db_state = {"exists": True}
    monkeypatch.setattr(
        ds,
        "_target_ops",
        lambda config_, **kw: _RecordingOps(drops, db_state),
    )

    result = asyncio.run(dww.recover_and_cleanup(config))
    assert drops == []
    assert db_a not in drops and db_b not in drops
    assert rid_dup not in control.cleaned_calls
    assert result.cleaned == 0
    assert result.retained == 1
    assert result.failure_code == ds.CODE_CLEANUP_FAILED
    for job in (job_a, job_b):
        m = ds.read_manifest(custody / job)
        assert m is not None
        assert m.state == ds.STATE_DB_AND_FILES_VERIFIED_UNPUBLISHED


def test_recover_and_cleanup_unreadable_manifest_retained(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """224-b fail-closed: an unreadable/malformed custody manifest cannot
    have its owner positively excluded - the request is retained as
    ambiguous and nothing is removed or marked cleaned."""
    config, _, custody, _ = _worker_config(tmp_path)
    rid_bad = uuid.uuid4()
    job, db = _bound_failed_job(custody, 97, rid_bad)
    (custody / job / ds._MANIFEST_NAME).write_text(
        "{corrupt manifest", encoding="utf-8"
    )
    control = FakeControl(
        config,
        candidates=[
            {
                "id": rid_bad,
                "state": "failed",
                "worker_job_id": None,
                "worker_target_db": None,
            },
        ],
    )
    _install_fake_control(monkeypatch, control)
    drops: list[str] = []
    db_state = {"exists": True}
    monkeypatch.setattr(
        ds,
        "_target_ops",
        lambda config_, **kw: _RecordingOps(drops, db_state),
    )

    result = asyncio.run(dww.recover_and_cleanup(config))
    assert drops == []
    assert rid_bad not in control.cleaned_calls
    assert result.cleaned == 0
    assert result.retained == 1
    assert result.failure_code == ds.CODE_CLEANUP_FAILED
    # The corrupt manifest is left byte-identical for operator
    # inspection.
    assert (custody / job / ds._MANIFEST_NAME).read_text(encoding="utf-8") == (
        "{corrupt manifest"
    )


# --- 224-d: exact verified-copy reader publication grant ----------------------

READER_ROLE = "snap_reader_role"  # the fixture's configured reader role


def _fake_psql(monkeypatch: pytest.MonkeyPatch, outputs=None):
    """Capture every bounded psql call; scripted per-call (out, rc).

    ``outputs`` is a list of ``(stdout_tail, returncode)`` pairs; when
    omitted every call succeeds with stdout ``"1"``.
    """
    calls: list[tuple[str, str]] = []

    def fake_psql(config, database, sql, **kwargs):
        calls.append((database, sql))
        if outputs is None:
            out, rc = "1", 0
        else:
            out, rc = outputs[len(calls) - 1]
        return ds._CappedRunResult(
            returncode=rc, stderr_tail="", stdout_tail=out
        )

    monkeypatch.setattr(ds, "_psql_target_admin", fake_psql)
    return calls


def test_grant_success_single_transaction_exact_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, _settings, _custody, _pf = _worker_config(tmp_path)
    target = _target_db(41)
    calls = _fake_psql(monkeypatch, outputs=[("1", 0), ("", 0)])
    dww._grant_target_reader(config, target)
    assert len(calls) == 2
    # 1) role-law precheck on the maintenance database.
    pre_db, pre_sql = calls[0]
    assert pre_db == "postgres"
    assert "pg_roles" in pre_sql and "pg_auth_members" in pre_sql
    assert "rolcanlogin" in pre_sql and "rolsuper" in pre_sql
    # 2) ONE explicit transaction ON the exact target database:
    # CONNECT + USAGE + SELECT, atomic (BEGIN ... COMMIT).
    grant_db, grant_sql = calls[1]
    assert grant_db == target
    assert grant_sql.startswith("BEGIN; ")
    assert grant_sql.endswith("COMMIT;")
    assert f'GRANT CONNECT ON DATABASE "{target}" TO "{READER_ROLE}"' in grant_sql
    assert f'GRANT USAGE ON SCHEMA public TO "{READER_ROLE}"' in grant_sql
    assert f'GRANT SELECT ON ALL TABLES IN SCHEMA public TO "{READER_ROLE}"' in grant_sql
    # 224-g: the target-only display schema grant rides the SAME
    # atomic transaction.
    assert f'GRANT USAGE ON SCHEMA demo_display TO "{READER_ROLE}"' in grant_sql
    assert f'GRANT SELECT ON demo_display.leaves TO "{READER_ROLE}"' in grant_sql
    # No statement may name the source cluster or any DML/DDL.
    full = pre_sql + " " + grant_sql
    for forbidden in ("DELETE", "UPDATE ", "INSERT", "CREATE", "ALTER", "DROP "):
        assert forbidden not in full


def test_grant_missing_role_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config, _settings, _custody, _pf = _worker_config(tmp_path)
    calls = _fake_psql(monkeypatch, outputs=[("", 0)])  # role absent
    with pytest.raises(dww.DemoWebWorkerError) as ei:
        dww._grant_target_reader(config, _target_db(42))
    assert ei.value.code == dww.CODE_READER_GRANT_FAILED
    assert len(calls) == 1  # no grant statement ran


def test_grant_privileged_or_member_role_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, _settings, _custody, _pf = _worker_config(tmp_path)
    calls = _fake_psql(monkeypatch, outputs=[("0", 0)])  # law violated
    with pytest.raises(dww.DemoWebWorkerError) as ei:
        dww._grant_target_reader(config, _target_db(43))
    assert ei.value.code == dww.CODE_READER_GRANT_FAILED
    assert len(calls) == 1


def test_grant_target_admin_reused_refused_before_any_psql(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, _settings, _custody, _pf = _worker_config(
        tmp_path, DEMO_SNAPSHOT_TARGET_READER_ROLE="snap_target"
    )
    calls = _fake_psql(monkeypatch)
    with pytest.raises(dww.DemoWebWorkerError) as ei:
        dww._grant_target_reader(config, _target_db(44))
    assert ei.value.code == dww.CODE_READER_GRANT_FAILED
    assert calls == []


def test_grant_transaction_failure_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, _settings, _custody, _pf = _worker_config(tmp_path)
    calls = _fake_psql(monkeypatch, outputs=[("1", 0), ("", 1)])
    with pytest.raises(dww.DemoWebWorkerError) as ei:
        dww._grant_target_reader(config, _target_db(45))
    assert ei.value.code == dww.CODE_READER_GRANT_FAILED
    assert len(calls) == 2  # precheck ok, grant transaction failed


def test_grant_malformed_target_name_refused_before_any_psql(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, _settings, _custody, _pf = _worker_config(tmp_path)
    calls = _fake_psql(monkeypatch)
    with pytest.raises(dww.DemoWebWorkerError) as ei:
        dww._grant_target_reader(config, "evil_db")
    assert ei.value.code == dww.CODE_READER_GRANT_FAILED
    assert calls == []


def test_process_request_grant_failure_fails_without_publishing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, settings, custody, _ = _worker_config(tmp_path)
    job, target = _job_id(47), _target_db(47)
    _make_verified_copies(custody, job, target)
    control = FakeControl(config)
    _install_fake_control(monkeypatch, control)
    _pipeline_success(monkeypatch, job, target)

    def grant_boom(cfg, db):
        assert db == target
        raise dww.DemoWebWorkerError(
            dww.CODE_READER_GRANT_FAILED, "The demo copy reader grant "
            "transaction could not be applied."
        )

    monkeypatch.setattr(dww, "_grant_target_reader", grant_boom)
    result = asyncio.run(
        dww.process_request(config, settings, request_id=REQUEST_ID)
    )
    assert result.state == "failed"
    assert result.failure_code == dww.CODE_READER_GRANT_FAILED
    # NEVER published: no handoff attempt, failure recorded.
    assert control.handoffs == []
    assert control.failures == [(REQUEST_ID, "worker_failed")]


# --- 224-g target-only display ingest ------------------------------------------------


class _FakeDisplayTxn:
    def __init__(self, conn: "_FakeDisplayConn") -> None:
        self._conn = conn

    async def __aenter__(self) -> "_FakeDisplayTxn":
        return self

    async def __aexit__(self, exc_type, _exc, _tb) -> bool:
        if exc_type is not None:
            self._conn.rolled_back = True
        return False


class _FakeDisplayConn:
    """Records every statement + parameter tuple of the ingest
    transaction; never touches a real database."""

    def __init__(self) -> None:
        self.executes: list[tuple[str, tuple[object, ...]]] = []
        self.rolled_back = False
        self.closed = False

    def transaction(self) -> _FakeDisplayTxn:
        return _FakeDisplayTxn(self)

    async def execute(self, sql: str, *args: object) -> None:
        self.executes.append((sql, args))

    async def close(self) -> None:
        self.closed = True


def _fake_display_conn(monkeypatch: pytest.MonkeyPatch) -> _FakeDisplayConn:
    conn = _FakeDisplayConn()

    async def fake_connect_copy(config, target_db, **kwargs):
        fake_connect_copy.target_db = target_db
        fake_connect_copy.kwargs = kwargs
        return conn

    monkeypatch.setattr(dss, "_connect_copy", fake_connect_copy)
    return conn


def _ingest_one_leaf(custody: Path, job: str, target: str, **entry_overrides):
    """Run the sync ingest entry against ONE-leaf verified custody."""
    _make_verified_copies(custody, job, target)
    if entry_overrides:
        files_dir = custody / job / dsf.FILES_DIR_NAME
        import json as _json

        doc = _json.loads((files_dir / dsf.FILES_MANIFEST_NAME).read_text())
        for key, value in entry_overrides.items():
            doc["files"][0][key] = value
        (files_dir / dsf.FILES_MANIFEST_NAME).write_text(
            _json.dumps(doc, sort_keys=True) + "\n"
        )
    return dww._ingest_verified_display(
        _worker_config_for(custody), job, REQUEST_ID, target
    )


def _worker_config_for(custody: Path) -> dww.DemoWebWorkerConfig:
    import tempfile

    tmp = Path(tempfile.mkdtemp(prefix="224g-cfg-"))
    passfile = tmp / "pgpass"
    passfile.write_text(
        "127.0.0.1:5555:slaif_src:snap_reader:canary-src\n"
        "127.0.0.1:5556:*:snap_target:canary-tgt\n",
        encoding="utf-8",
    )
    os.chmod(passfile, 0o600)
    settings = Settings(**_settings_dict(custody, passfile))
    return dww.web_worker_config_from_settings(settings)


LEGIT_REPORT_NAME = f"catalog/proposals/{'ab' * 16}/provider-catalog-report.md"


def test_ingest_happy_path_projects_only_closed_safe_fields(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    custody, _pf = _custody_passfile(tmp_path)
    job, target = _job_id(71), _target_db(71)
    conn = _fake_display_conn(monkeypatch)
    _ingest_one_leaf(custody, job, target)
    assert not conn.rolled_back and conn.closed
    sqls = [sql for sql, _args in conn.executes]
    assert sqls[0] == dww._DISPLAY_LEAVES_DDL
    assert "CREATE SCHEMA demo_display" in sqls[0]
    assert "CREATE TABLE demo_display.leaves" in sqls[0]
    assert len(conn.executes) == 2  # DDL + the single INSERT
    _sql, args = conn.executes[1]
    assert "INSERT INTO demo_display.leaves" in _sql
    name, kind, sha, count, captured, body = args
    assert name == LEGIT_REPORT_NAME
    assert kind == dsf.KIND_MARKDOWN
    assert sha == hashlib.sha256(dsf.NEUTRAL_MARKDOWN).hexdigest()
    assert count == len(dsf.NEUTRAL_MARKDOWN)
    assert captured == 1500.0
    assert body == dsf.NEUTRAL_MARKDOWN
    # No private manifest field (source, source_ref, source_sha256,
    # inode identity, on-disk leaf name) may be projected into SQL.
    rendered = repr(conn.executes)
    for forbidden in (
        "fixed-label",  # source_ref
        hashlib.sha256(b"src").hexdigest(),  # source_sha256
        "f0001-",  # on-disk leaf name
        "inode",
    ):
        assert forbidden not in rendered


def test_ingest_rejects_illegal_logical_name_and_rolls_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    custody, _pf = _custody_passfile(tmp_path)
    job, target = _job_id(72), _target_db(72)
    conn = _fake_display_conn(monkeypatch)
    with pytest.raises(dww.DemoWebWorkerError) as ei:
        _ingest_one_leaf(
            custody, job, target, logical_name="branding/evil.svg"
        )
    assert ei.value.code == dww.CODE_DISPLAY_INGEST_FAILED
    assert conn.rolled_back
    assert len(conn.executes) == 1  # DDL only; no INSERT survived


def test_ingest_rejects_duplicate_logical_names(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    custody, _pf = _custody_passfile(tmp_path)
    job, target = _job_id(73), _target_db(73)
    _make_verified_copies(custody, job, target)
    files_dir = custody / job / dsf.FILES_DIR_NAME
    import json as _json

    # A second physical leaf with the SAME closed logical name.
    leaf2 = files_dir / ("f0002-" + "cd" * 6)
    leaf2.write_bytes(dsf.NEUTRAL_MARKDOWN)
    os.chmod(leaf2, 0o600)
    leaf_st = os.stat(leaf2, follow_symlinks=False)
    doc = _json.loads((files_dir / dsf.FILES_MANIFEST_NAME).read_text())
    doc["files"].append(
        {
            "leaf": leaf2.name,
            "logical_name": LEGIT_REPORT_NAME,
            "kind": dsf.KIND_MARKDOWN,
            "sha256": hashlib.sha256(dsf.NEUTRAL_MARKDOWN).hexdigest(),
            "bytes": len(dsf.NEUTRAL_MARKDOWN),
            "inode_identity": [leaf_st.st_dev, leaf_st.st_ino],
            "source": "test",
            "source_ref": "fixed-label",
            "captured_at": 1500.0,
            "source_sha256": hashlib.sha256(b"src").hexdigest(),
        }
    )
    (files_dir / dsf.FILES_MANIFEST_NAME).write_text(
        _json.dumps(doc, sort_keys=True) + "\n"
    )
    conn = _fake_display_conn(monkeypatch)
    with pytest.raises(dww.DemoWebWorkerError) as ei:
        dww._ingest_verified_display(
            _worker_config_for(custody), job, REQUEST_ID, target
        )
    assert ei.value.code == dww.CODE_DISPLAY_INGEST_FAILED
    assert conn.rolled_back
    # DDL + the FIRST (legit) leaf INSERT ran; the duplicate refused
    # before its INSERT and the whole transaction rolled back.
    assert len(conn.executes) == 2
    assert all("INSERT" not in sql or i == 1 for i, (sql, _a) in enumerate(conn.executes))


def test_ingest_rejects_unknown_kind_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    custody, _pf = _custody_passfile(tmp_path)
    job, target = _job_id(74), _target_db(74)
    conn = _fake_display_conn(monkeypatch)
    with pytest.raises(dww.DemoWebWorkerError) as ei:
        _ingest_one_leaf(custody, job, target, kind="not-a-kind")
    assert ei.value.code == dww.CODE_DISPLAY_INGEST_FAILED
    assert conn.rolled_back
    assert len(conn.executes) == 1


def test_ingest_rejects_leaf_changed_after_verification(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    custody, _pf = _custody_passfile(tmp_path)
    job, target = _job_id(75), _target_db(75)
    conn = _fake_display_conn(monkeypatch)
    _make_verified_copies(custody, job, target, corrupt_leaf=True)
    with pytest.raises(dww.DemoWebWorkerError) as ei:
        dww._ingest_verified_display(
            _worker_config_for(custody), job, REQUEST_ID, target
        )
    assert ei.value.code == dww.CODE_DISPLAY_INGEST_FAILED
    assert conn.rolled_back
    # DDL ran first, then the re-proof refusal rolled the transaction
    # back: no INSERT ever reached the copy.
    assert len(conn.executes) == 1


def test_ingest_rejects_main_manifest_leaf_count_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    custody, _pf = _custody_passfile(tmp_path)
    job, target = _job_id(76), _target_db(76)
    _make_verified_copies(custody, job, target)
    job_dir = custody / job
    manifest = ds.read_manifest(job_dir)
    assert manifest is not None
    manifest.files_count = 5  # custody lies about the re-proven set
    ds.write_manifest(job_dir, manifest)
    conn = _fake_display_conn(monkeypatch)
    with pytest.raises(dww.DemoWebWorkerError) as ei:
        dww._ingest_verified_display(
            _worker_config_for(custody), job, REQUEST_ID, target
        )
    assert ei.value.code == dww.CODE_DISPLAY_INGEST_FAILED
    assert conn.rolled_back
    assert len(conn.executes) == 2  # DDL ran, zero INSERTs survived


def test_ingest_rejects_invalid_capture_time(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    custody, _pf = _custody_passfile(tmp_path)
    job, target = _job_id(77), _target_db(77)
    conn = _fake_display_conn(monkeypatch)
    with pytest.raises(dww.DemoWebWorkerError) as ei:
        _ingest_one_leaf(custody, job, target, captured_at=True)
    assert ei.value.code == dww.CODE_DISPLAY_INGEST_FAILED
    assert conn.rolled_back


def test_ingest_deadline_already_elapsed_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    custody, _pf = _custody_passfile(tmp_path)
    job, target = _job_id(78), _target_db(78)
    _make_verified_copies(custody, job, target)
    _fake_display_conn(monkeypatch)

    async def run_past_deadline() -> None:
        config = _worker_config_for(custody)
        proof = dww._anchored_main_manifest(config, job, REQUEST_ID)
        assert proof is not None
        manifest, job_identity = proof
        await dww._display_ingest_transaction(
            config,
            target,
            custody / job,
            manifest,
            job_identity,
            deadline=0.0,  # already elapsed
        )

    with pytest.raises(dww.DemoWebWorkerError) as ei:
        asyncio.run(run_past_deadline())
    assert ei.value.code == dww.CODE_DISPLAY_INGEST_FAILED


def test_ingest_refuses_foreign_job_or_request_before_any_db_work(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    custody, _pf = _custody_passfile(tmp_path)
    job, target = _job_id(79), _target_db(79)
    _make_verified_copies(custody, job, target)
    conn = _fake_display_conn(monkeypatch)
    config = _worker_config_for(custody)
    # Foreign request: the anchored manifest ownership check refuses.
    with pytest.raises(dww.DemoWebWorkerError) as ei:
        dww._ingest_verified_display(
            config, job, uuid.uuid4(), target
        )
    assert ei.value.code == dww.CODE_DISPLAY_INGEST_FAILED
    # Malformed target name: refused before any DB work at all.
    with pytest.raises(dww.DemoWebWorkerError) as ei2:
        dww._ingest_verified_display(config, job, REQUEST_ID, "evil_db")
    assert ei2.value.code == dww.CODE_DISPLAY_INGEST_FAILED
    assert conn.executes == []


def test_ingest_logical_name_law_closed_per_kind() -> None:
    K = dsf
    run = "demo-run-" + "a" * 24
    job32 = "b" * 32
    presets = (
        "openrouter-chat-text",
        "openrouter-chat-image",
        "openrouter-chat-audio",
        "openrouter-chat-multimodal",
        "openrouter-responses-text",
    )
    law = dww._display_name_law
    assert law(K.KIND_REFRESH_BUNDLE, f"catalog/runs/{run}/catalog-refresh.json")
    assert law(K.KIND_REFRESH_BUNDLE, f"catalog/uploads/{job32}/bundle-{'c' * 32}")
    assert law(K.KIND_BASELINE_DOC, f"catalog/runs/{run}/catalog-baseline.json")
    assert law(K.KIND_BASELINE_DOC, f"catalog/uploads/{job32}/baseline-export-{'d' * 32}")
    assert law(K.KIND_ROUTE_TSV, f"catalog/runs/{run}/routes-proposal.tsv")
    assert law(K.KIND_ROUTE_TSV, f"catalog/proposals/{job32}/routes-proposal.tsv")
    assert law(K.KIND_ROUTE_TSV, f"catalog/proposals/{job32}/packages/{presets[0]}/routes-proposal.tsv")
    assert law(K.KIND_PRICING_TSV, f"catalog/proposals/{job32}/packages/{presets[4]}/pricing-proposal.tsv")
    assert law(K.KIND_FX_JSON, f"catalog/runs/{run}/fx-proposal.json")
    assert law(K.KIND_VALIDATION_JSON, f"catalog/runs/{run}/validation.json")
    assert law(K.KIND_REVIEW_HTML, f"catalog/runs/{run}/REVIEW.html")
    assert law(K.KIND_SOURCE_MANIFEST, f"catalog/proposals/{job32}/source-manifest.json")
    assert law(K.KIND_NORMALIZED_JSON, f"catalog/proposals/{job32}/provider-catalog-normalized.json")
    assert law(K.KIND_WARNINGS_JSON, f"catalog/proposals/{job32}/warnings.json")
    assert law(K.KIND_MARKDOWN, f"catalog/proposals/{job32}/provider-catalog-report.md")
    assert law(K.KIND_MARKDOWN, f"catalog/proposals/{job32}/packages/{presets[1]}/package-report.md")
    assert law(K.KIND_MARKDOWN, f"catalog/proposals/{job32}/packages/{presets[2]}/model-review.md")
    assert law(K.KIND_PACKAGE_MANIFEST, f"catalog/proposals/{job32}/packages/{presets[3]}/package-manifest.json")
    assert law(K.KIND_JOB_RECORD, f"catalog/jobs/{job32}.json")
    for slot in ("style.css", "logo", "logo-compact", "favicon", "hero"):
        assert law(K.KIND_BRANDING, f"branding/{slot}")
    assert law(K.KIND_LLM_PROFILES, "profiles/upstream-llm.json")
    assert law(K.KIND_COMPLETION_CHOICES, "profiles/completion-choices.json")
    # Closed law: foreign shapes, traversal, unknown kinds, wrong
    # kind/name pairs, and over-length names all refuse.
    assert not law(K.KIND_BRANDING, "branding/evil.svg")
    assert not law(K.KIND_BRANDING, "branding/../etc/passwd")
    assert not law(K.KIND_ROUTE_TSV, f"catalog/runs/{run}/routes-proposal.tsvx")
    assert not law(K.KIND_MARKDOWN, f"catalog/proposals/{job32}/packages/evil-pkg/report.md")
    assert not law("unknown_kind", "profiles/upstream-llm.json")
    assert not law(K.KIND_BRANDING, f"catalog/jobs/{job32}.json")
    assert not law(K.KIND_LLM_PROFILES, "x" * 201)
    assert not law(K.KIND_LLM_PROFILES, "")
    assert not law(123, "profiles/upstream-llm.json")


def test_process_request_ingest_failure_fails_without_publishing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, settings, custody, _ = _worker_config(tmp_path)
    job, target = _job_id(80), _target_db(80)
    _make_verified_copies(custody, job, target)
    control = FakeControl(config)
    _install_fake_control(monkeypatch, control)
    calls = _pipeline_success(monkeypatch, job, target)

    def ingest_boom(cfg, job_id, request_id, target_db):
        assert (job_id, request_id, target_db) == (job, REQUEST_ID, target)
        raise dww.DemoWebWorkerError(
            dww.CODE_DISPLAY_INGEST_FAILED,
            "The verified display could not be ingested into the demo copy.",
        )

    monkeypatch.setattr(dww, "_ingest_verified_display", ingest_boom)
    grants: list[str] = []
    monkeypatch.setattr(
        dww, "_grant_target_reader", lambda cfg, db: grants.append(db)
    )
    result = asyncio.run(
        dww.process_request(config, settings, request_id=REQUEST_ID)
    )
    assert result.state == "failed"
    assert result.failure_code == dww.CODE_DISPLAY_INGEST_FAILED
    # NEVER published: no grant, no handoff, failure recorded, and the
    # 221/222/223 pipeline ran exactly once.
    assert grants == []
    assert control.handoffs == []
    assert control.failures == [(REQUEST_ID, "worker_failed")]
    assert len(calls["snapshot"]) == 1 and calls["ingest"] == []
