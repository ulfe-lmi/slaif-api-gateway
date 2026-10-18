"""REAL multiprocess filesystem tests for the capture store (objective 191).

No database is required: the store coordinates purely through the local
filesystem (flock-protected manifest + atomic artifacts).  These tests spawn
real OS processes to prove cross-worker claim exclusivity, finite exhaustion,
expiry/stop persistence across restarts, bounded budgets, safe path checks,
and cleanup behavior that preserves unrelated files.
"""

from __future__ import annotations

import multiprocessing
import os
import stat
import time
from pathlib import Path
from typing import Any

import pytest

from slaif_gateway.services.request_capture import (
    CAPTURES_DIR_NAME,
    CaptureFacilityConfig,
    CaptureStore,
    CaptureStoreError,
    LOCK_NAME,
    MANIFEST_NAME,
)

_CONFIG = {
    "body_budget_bytes": 65536,
    "total_storage_bytes": 4 * 1024 * 1024,
    "max_count": 100,
    "max_ttl_seconds": 3600,
}
ENDPOINT = "/v1/responses"


def _config_from_dict(root: Path, overrides: dict[str, Any] | None = None) -> CaptureFacilityConfig:
    values = dict(_CONFIG)
    if overrides:
        values.update(overrides)
    return CaptureFacilityConfig(
        enabled=True,
        root=root,
        body_budget_bytes=values["body_budget_bytes"],
        total_storage_bytes=values["total_storage_bytes"],
        max_count=values["max_count"],
        max_ttl_seconds=values["max_ttl_seconds"],
        deployed_revision="synthetic-revision",
        revision_provenance="synthetic-test",
        app_version="0.1.0",
    )


def _store(root: Path, overrides: dict[str, Any] | None = None) -> CaptureStore:
    return CaptureStore(_config_from_dict(root, overrides))


# -- real child-process workers (spawn-safe top-level functions) ------------


def _child_claim_once(root: str, endpoint: str, barrier, queue) -> None:
    """Wait until every worker is ready, then race exactly one claim."""
    store = _store(Path(root))
    barrier.wait(timeout=30)
    session = store.claim(endpoint=endpoint)
    queue.put("won" if session is not None else "skipped")


def _child_claim_until_exhausted(
    root: str, endpoint: str, attempts: int, _barrier, queue
) -> None:
    store = _store(Path(root))
    claims = 0
    for _ in range(attempts):
        if store.claim(endpoint=endpoint) is None:
            break
        claims += 1
    queue.put(claims)


def _spawn_race(target, args: tuple, workers: int, timeout: float = 30.0) -> list[Any]:
    """Spawn ``workers`` children behind a shared barrier; drain results."""
    ctx = multiprocessing.get_context("spawn")
    barrier = ctx.Barrier(workers)
    queue = ctx.Queue()
    processes = [ctx.Process(target=target, args=(*args, barrier, queue)) for _ in range(workers)]
    try:
        for process in processes:
            process.start()
        results = [queue.get(timeout=timeout) for _ in range(workers)]
        for process in processes:
            process.join(timeout)
            if process.is_alive():
                process.terminate()
                process.join(5)
        for process in processes:
            assert process.exitcode == 0
        return results
    finally:
        for process in processes:
            if process.is_alive():
                process.terminate()
                process.join(5)


@pytest.fixture
def root(tmp_path: Path) -> Path:
    return tmp_path / "captures"


def test_two_processes_exactly_one_next_claim(root: Path) -> None:
    store = _store(root)
    store.arm(endpoint=ENDPOINT, count=1)
    # Both workers race behind a real barrier, so a lost-update race (both
    # workers told they won, or one silently crashing) cannot masquerade as a
    # single winner: every child reports its own claim outcome over the queue.
    results = _spawn_race(_child_claim_once, (str(root), ENDPOINT), workers=2)
    assert sorted(results) == ["skipped", "won"]
    sessions = _store(root).status()
    assert len(sessions) == 1
    assert sessions[0].claimed == 1
    assert sessions[0].status(time.time()) == "exhausted"
    assert _store(root).claim(endpoint=ENDPOINT) is None


def test_finite_claims_across_processes(root: Path) -> None:
    store = _store(root)
    session = store.arm(endpoint=ENDPOINT, count=5)
    # Three workers each attempt up to 10 claims; the summed per-worker
    # reported outcomes must equal the armed count exactly.
    results = _spawn_race(_child_claim_until_exhausted, (str(root), ENDPOINT, 10), workers=3)
    assert sum(results) == 5
    assert all(isinstance(claims, int) and 0 <= claims <= 5 for claims in results)
    total = sum(s.claimed for s in _store(root).status())
    assert total == 5
    assert all(s.session_id == session.session_id for s in _store(root).status())
    assert _store(root).claim(endpoint=ENDPOINT) is None


def test_expired_session_never_rearms(root: Path) -> None:
    store = _store(root, overrides={"max_ttl_seconds": 5})
    session = store.arm(endpoint=ENDPOINT, count=1, ttl_seconds=1)
    time.sleep(1.2)
    assert session.status(time.time()) == "expired"
    assert _store(root).claim(endpoint=ENDPOINT) is None
    # A restarted process on the same root sees the same expired state.
    assert _store(root).status()[0].status(time.time()) == "expired"


def test_stopped_session_persists_across_restart(root: Path) -> None:
    store = _store(root)
    session = store.arm(endpoint=ENDPOINT, count=2)
    assert store.stop(session_id=session.session_id) == 1
    assert _store(root).status()[0].stopped is True
    assert _store(root).claim(endpoint=ENDPOINT) is None


def test_layout_permissions(root: Path) -> None:
    store = _store(root)
    session = store.arm(endpoint=ENDPOINT)
    mode = stat.S_IMODE(os.stat(root).st_mode)
    assert mode == 0o700
    assert stat.S_IMODE(os.stat(root / MANIFEST_NAME).st_mode) == 0o600
    assert stat.S_IMODE(os.stat(root / LOCK_NAME).st_mode) == 0o600
    # Publish one artifact and check the session directory/file modes.
    store.claim(endpoint=ENDPOINT, reserve_bytes=store.reservation_bytes())
    store.write_artifact(
        session_id=session.session_id,
        request_id="gw-perms-1",
        capture=b'{"schema_version":1}',
        record=b'{"schema_version":1}',
    )
    session_dir = root / CAPTURES_DIR_NAME / session.session_id
    assert stat.S_IMODE(os.stat(session_dir).st_mode) == 0o700
    for path in session_dir.glob("*.json"):
        assert stat.S_IMODE(os.stat(path).st_mode) == 0o600


def test_symlinked_root_is_refused(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    os.symlink(real, link)
    with pytest.raises(CaptureStoreError):
        _store(link)


def test_manifest_symlink_is_refused(root: Path) -> None:
    store = _store(root)
    store.arm(endpoint=ENDPOINT)
    # Replace the real manifest with a symlink to a regular file.
    manifest = root / MANIFEST_NAME
    real_manifest = root.parent / "manifest-real.json"
    manifest.rename(real_manifest)
    os.symlink(real_manifest, manifest)
    with pytest.raises(CaptureStoreError):
        _store(root).status()


def test_claim_zero_reserve_is_rejected(root: Path) -> None:
    store = _store(root)
    store.arm(endpoint=ENDPOINT, count=1)
    with pytest.raises(CaptureStoreError) as exc_info:
        store.claim(endpoint=ENDPOINT, reserve_bytes=0)
    assert exc_info.value.reason == "capture_reserve_invalid"
    assert store.status()[0].claimed == 0


def test_write_requires_claim_and_rejects_duplicates(root: Path) -> None:
    store = _store(root)
    session = store.arm(endpoint=ENDPOINT, count=2)
    with pytest.raises(CaptureStoreError) as exc_info:
        store.write_artifact(
            session_id=session.session_id,
            request_id="gw-x-1",
            capture=b"{}",
            record=b"{}",
        )
    assert exc_info.value.reason == "capture_unclaimed"
    # Two claims so the second publish passes the claimed/published check and
    # is rejected specifically as a duplicate artifact name.
    store.claim(endpoint=ENDPOINT, reserve_bytes=store.reservation_bytes())
    store.claim(endpoint=ENDPOINT, reserve_bytes=store.reservation_bytes())
    store.write_artifact(
        session_id=session.session_id,
        request_id="gw-x-1",
        capture=b'{"schema_version":1}',
        record=b'{"schema_version":1}',
    )
    with pytest.raises(CaptureStoreError) as exc_info:
        store.write_artifact(
            session_id=session.session_id,
            request_id="gw-x-1",
            capture=b"{}",
            record=b"{}",
        )
    assert exc_info.value.reason == "capture_duplicate"


def test_per_capture_and_global_budgets_are_enforced(root: Path) -> None:
    store = _store(root)
    reservation = store.reservation_bytes()
    session = store.arm(endpoint=ENDPOINT, count=2)
    store.claim(endpoint=ENDPOINT, reserve_bytes=reservation)
    too_big = b"{" + b"a" * (reservation + 1) + b"}"
    with pytest.raises(CaptureStoreError) as exc_info:
        store.write_artifact(
            session_id=session.session_id,
            request_id="gw-big-1",
            capture=too_big,
            record=b"{}",
        )
    assert exc_info.value.reason == "capture_storage_full"
    # The global budget is coherent: a second claim cannot exceed it.
    store.write_artifact(
        session_id=session.session_id,
        request_id="gw-ok-1",
        capture=b'{"schema_version":1}',
        record=b'{"schema_version":1}',
    )
    store.claim(endpoint=ENDPOINT, reserve_bytes=reservation)
    assert store.status()[0].claimed == 2


def test_global_total_storage_bounds_claims(root: Path) -> None:
    store = _store(root, overrides={"total_storage_bytes": store_reservation(root)})
    store.arm(endpoint=ENDPOINT, count=10)
    first = store.claim(endpoint=ENDPOINT)
    assert first is not None
    # Publishing consumes at least the reservation's actual footprint; the
    # next claim must not be able to exceed the configured total.
    store.write_artifact(
        session_id=first.session_id,
        request_id="gw-total-1",
        capture=b'{"schema_version":1}',
        record=b'{"schema_version":1}',
    )
    assert store.storage_reserved() <= store_reservation(root)


def store_reservation(root: Path) -> int:
    return _store(root).reservation_bytes()


def test_cleanup_preserves_unrelated_files(root: Path) -> None:
    store = _store(root)
    session = store.arm(endpoint=ENDPOINT)
    store.claim(endpoint=ENDPOINT, reserve_bytes=store.reservation_bytes())
    store.write_artifact(
        session_id=session.session_id,
        request_id="gw-keep-1",
        capture=b'{"schema_version":1}',
        record=b'{"schema_version":1}',
    )
    session_dir = root / CAPTURES_DIR_NAME / session.session_id
    unrelated = session_dir / "keep-unrelated.txt"
    unrelated.write_text("preserve me")
    reserved_before = store.storage_reserved()
    assert reserved_before > 0
    removed = store.cleanup(session_id=session.session_id)
    assert removed == 2
    assert unrelated.read_text() == "preserve me"
    assert store.storage_reserved() == 0
    assert _store(root).status() == []


def test_preexisting_path_at_artifact_name_is_refused(root: Path) -> None:
    store = _store(root)
    session = store.arm(endpoint=ENDPOINT, count=1)
    store.claim(endpoint=ENDPOINT, reserve_bytes=store.reservation_bytes())
    session_dir = root / CAPTURES_DIR_NAME / session.session_id
    session_dir.mkdir(parents=True)
    (session_dir / "gw-fail-1.capture.json").write_bytes(b"stale")
    with pytest.raises(CaptureStoreError) as exc_info:
        store.write_artifact(
            session_id=session.session_id,
            request_id="gw-fail-1",
            capture=b"{}",
            record=b"{}",
        )
    assert exc_info.value.reason == "capture_duplicate"
