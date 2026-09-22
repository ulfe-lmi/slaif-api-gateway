"""180-g (G1-G4): descriptor-anchored filesystem boundary and sealing tests.

Exercises the ACTUAL open/publish/read/mutate seams with explicit barriers
(no timing-only sleeps), synthetic fake keys only, and pytest tmp_path
resources. Coverage: anchored-walk refusals (symlinked ancestors/parents/
leaves, traversal, depth), FIFO/special-file promptness, sparse-oversize
pre-read refusal, short/growing reads, strict JSON (canary non-echo),
descriptor ownership (no leaks, no reused-fd kills, rejection cleanup),
exact 0600 key contract on the opened FD, winner/loser at the rename
seam, atomic NEW-ONLY publication (pre-existing targets, sequential and
concurrent publishers, replaced-staging refusal), identity-checked
cleanup, mutation-namespace permission enforcement, lifecycle binding
(cross-phase directory swaps), capture-once accounting, first-install
marker byte-equality, and CLI failure-output privacy.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import shutil

import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest
from typer.testing import CliRunner, Result

from slaif_gateway.cli.main import app
from slaif_gateway.services.catalog_refresh import filesystem as fs
from slaif_gateway.services.catalog_refresh.baseline import load_baseline
from slaif_gateway.services.catalog_refresh.bundle import (
    canonical_bundle_bytes,
    load_bundle,
)
from slaif_gateway.services.catalog_refresh.errors import (
    CatalogRefreshBlockedError,
    CatalogRefreshSealError,
)
from slaif_gateway.services.catalog_refresh.sealing import (
    CONTENT_FILES,
    _hmac_payload,
    content_hashes,
    verify_run,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "catalog_refresh"
REPO_ROOT = Path(__file__).resolve().parents[2]
runner = CliRunner()


def _raw_key(path: Path) -> bytes:
    return bytes.fromhex(path.read_bytes().decode("ascii"))


def _fd_count() -> int:
    return len(os.listdir("/proc/self/fd"))


def _invoke_review(tmp_path: Path, run_root: Path, seal_key: Path) -> Result:
    return runner.invoke(
        app,
        [
            "catalog-refresh", "review",
            str(FIXTURES / "bundle-first-install.json"),
            "--first-install",
            "--run-root", str(run_root),
            "--seal-key", str(seal_key),
        ],
    )


@pytest.fixture()
def sealed_run_like(tmp_path: Path) -> tuple[Path, Path]:
    """Sealed first-install run: (run_dir, seal_key_path), like
    test_catalog_refresh_seal.sealed_run."""
    run_root = tmp_path / "runs"
    seal_key = tmp_path / "seal.key"
    result = _invoke_review(tmp_path, run_root, seal_key)
    assert result.exit_code == 0, result.output
    return run_root / "fixture-first-install-001", seal_key

# --- anchored walks and bounded reads -----------------------------------------


def test_symlinked_ancestor_parent_leaf_refused(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "sneaky.json").write_bytes(b"outside bytes")
    real = tmp_path / "real"
    real.mkdir()
    (real / "data.txt").write_bytes(b"real bytes")
    # symlinked leaf
    os.symlink(outside / "sneaky.json", real / "link.txt")
    with pytest.raises(CatalogRefreshSealError):
        fs.anchored_read(real, "link.txt", 1024)
    # symlinked intermediate parent
    sub = real / "sub"
    sub.mkdir()
    os.symlink(outside, sub / "link")
    with pytest.raises(CatalogRefreshSealError):
        fs.anchored_read(real, "sub/link/sneaky.json", 1024)
    # symlinked ancestor
    os.symlink(real, tmp_path / "alias")
    with pytest.raises(CatalogRefreshSealError):
        fs.anchored_read(tmp_path / "alias", "data.txt", 1024)


def test_run_name_traversal_and_shape_refused(tmp_path: Path) -> None:
    d = tmp_path / "d"
    d.mkdir()
    (d / "x.txt").write_bytes(b"x")
    for bad in ("../x.txt", "a/../b.txt", "", ".", "..", "/abs.txt", "a/b/c/d/e.txt"):
        with pytest.raises(CatalogRefreshSealError):
            fs.anchored_read(d, bad, 1024)


def test_fifo_leaf_refused_promptly(tmp_path: Path) -> None:
    fifo = tmp_path / "f.fifo"
    os.mkfifo(fifo)
    t0 = time.monotonic()
    with pytest.raises(CatalogRefreshSealError) as excinfo:
        fs.read_user_file(fifo, 1024)
    assert time.monotonic() - t0 < 2.0
    assert "not a regular file" in str(excinfo.value)


def test_sparse_oversize_refused_before_any_read(tmp_path: Path, monkeypatch) -> None:
    f = tmp_path / "sparse.bin"
    with open(f, "wb") as fh:
        fh.truncate(9 * 1024 * 1024)  # sparse: no backing bytes

    def no_read(*_a, **_kw):
        raise AssertionError("no read may happen for oversize input")

    monkeypatch.setattr(fs, "os_read", no_read)
    with pytest.raises(CatalogRefreshSealError) as excinfo:
        fs.read_user_file(f, 8 * 1024 * 1024)
    assert "exceeds the size bound" in str(excinfo.value)


def test_short_read_refused(tmp_path: Path, monkeypatch) -> None:
    f = tmp_path / "f.bin"
    f.write_bytes(b"0123456789" * 100)

    def short(_fd, _n):
        return b""

    monkeypatch.setattr(fs, "os_read", short)
    with pytest.raises(CatalogRefreshSealError) as excinfo:
        fs.read_user_file(f, 1024 * 1024)
    assert "short or growing read" in str(excinfo.value)


def test_file_growing_after_snapshot_refused(tmp_path: Path, monkeypatch) -> None:
    f = tmp_path / "f.bin"
    f.write_bytes(b"01234")
    real = fs.os_read

    def growing(fd, n):
        if n == 1:  # the EOF probe sees a byte: the file grew
            return b"X"
        return real(fd, n)

    monkeypatch.setattr(fs, "os_read", growing)
    with pytest.raises(CatalogRefreshSealError) as excinfo:
        fs.read_user_file(f, 1024)
    assert "grew after the size snapshot" in str(excinfo.value)


def test_strict_json_deep_input_refused_safely() -> None:
    with pytest.raises(CatalogRefreshSealError) as excinfo:
        fs.strict_json_bytes(b"[" * 50000 + b"]" * 50000, "x")
    assert "not strictly valid JSON" in str(excinfo.value)


def test_duplicate_key_error_never_echoes_input() -> None:
    canary = "canary-dup-key-0123456789"
    raw = f'{{"{canary}": 1, "{canary}": 2}}'.encode()
    with pytest.raises(CatalogRefreshSealError) as excinfo:
        fs.strict_json_bytes(raw, "bundle")
    assert canary not in str(excinfo.value)
    for load in (load_bundle, load_baseline):
        with pytest.raises(CatalogRefreshBlockedError) as excinfo:
            load(raw)
        assert canary not in str(excinfo.value)
        assert "duplicate JSON key" in excinfo.value.detail


def test_schema_error_never_echoes_unknown_field() -> None:
    canary = "SYNTHETIC_PRIVATE_FIELD_CANARY_180G"
    bundle_raw = (FIXTURES / "bundle-first-install.json").read_text()
    mutated = bundle_raw.rstrip().removesuffix("}") + f', "{canary}": "secret-value"\n}}'
    with pytest.raises(CatalogRefreshBlockedError) as excinfo:
        load_bundle(mutated.encode())
    assert excinfo.value.code == "bundle_schema_invalid"
    assert canary not in str(excinfo.value)
    assert "secret-value" not in str(excinfo.value)
    baseline_raw = (FIXTURES / "baseline-synthetic.json").read_text()
    mutb = baseline_raw.rstrip().removesuffix("}") + f', "{canary}": "secret-value"\n}}'
    with pytest.raises(CatalogRefreshBlockedError) as excinfo:
        load_baseline(mutb.encode())
    assert excinfo.value.code == "baseline_schema_invalid"
    assert canary not in str(excinfo.value)
    assert "secret-value" not in str(excinfo.value)


def test_cli_failure_output_never_echoes_unknown_field(tmp_path: Path) -> None:
    canary = "SYNTHETIC_PRIVATE_FIELD_CANARY_180G"
    bundle_raw = (FIXTURES / "bundle-first-install.json").read_text()
    mutated = bundle_raw.rstrip().removesuffix("}") + f', "{canary}": "secret-value"\n}}'
    bundle_path = tmp_path / "bundle.json"
    bundle_path.write_text(mutated, encoding="utf-8")
    run_root = tmp_path / "runs"
    result = runner.invoke(
        app,
        [
            "catalog-refresh", "review", str(bundle_path),
            "--first-install",
            "--run-root", str(run_root),
            "--seal-key", str(tmp_path / "seal.key"),
        ],
    )
    assert result.exit_code == 65, result.output
    assert canary not in result.output
    assert "secret-value" not in result.output
    # the minimal blocked run artifacts must be clean too
    blocked_dirs = [p for p in run_root.iterdir() if p.name.startswith("blocked-")] if run_root.exists() else []
    assert blocked_dirs, "a minimal blocked run must be published"
    for blocked in blocked_dirs:
        for entry in blocked.iterdir():
            data = entry.read_bytes()
            assert canary.encode() not in data
            assert b"secret-value" not in data


def test_create_missing_parents_are_private(tmp_path: Path) -> None:
    d = tmp_path / "x" / "y" / "z"
    handle = fs.open_anchored_handle(d, create_missing=True)
    try:
        assert d.is_dir()
        for p in (tmp_path / "x", tmp_path / "x" / "y", d):
            assert p.stat().st_mode & 0o777 == 0o700
    finally:
        handle.close()


# --- descriptor ownership -------------------------------------------------------


def test_open_anchored_directory_no_fd_leak(tmp_path: Path) -> None:
    before = _fd_count()
    for _ in range(12):
        fd, _chain = fs.open_anchored_directory(tmp_path)
        os.close(fd)
    assert _fd_count() - before == 0


def test_anchored_dir_close_never_kills_reused_fd(tmp_path: Path) -> None:
    d = tmp_path / "a" / "b"
    d.mkdir(parents=True)
    handle = fs.open_anchored_handle(d)
    victim_fd = handle.component_fds[0]
    os.close(victim_fd)  # explicit barrier close (simulated early close)
    probe = tmp_path / "probe.txt"
    probe.write_bytes(b"unrelated")
    reused = os.open(probe, os.O_RDONLY)  # grabs the freed number
    assert reused == victim_fd  # deterministic on this system
    handle.close()
    # the unrelated fd that reused the number must still be usable
    assert os.read(reused, 16) == b"unrelated"
    os.close(reused)


def test_anchored_dir_double_close_harmless(tmp_path: Path) -> None:
    d = tmp_path / "c" / "e"
    d.mkdir(parents=True)
    handle = fs.open_anchored_handle(d)
    handle.close()
    handle.close()


def test_namespace_rejection_no_fd_leak(tmp_path: Path) -> None:
    w = tmp_path / "w777"
    w.mkdir()
    os.chmod(w, 0o777)
    before = _fd_count()
    for _ in range(5):
        with pytest.raises(CatalogRefreshSealError):
            fs.ensure_seal_key(w / "seal.key")
        with pytest.raises(CatalogRefreshSealError):
            fs.publish_new_only_file(w, "out.json", b"{}", 0o644)
    assert _fd_count() - before == 0
    assert not (w / "seal.key").exists()
    assert not (w / "out.json").exists()
    os.chmod(w, 0o755)
    fs.publish_new_only_file(w, "out.json", b"{}", 0o644)
    assert (w / "out.json").read_bytes() == b"{}"


# --- seal key contract ------------------------------------------------------------


def test_key_exact_mode_owner_hex_enforced(tmp_path: Path) -> None:
    key_path = tmp_path / "keys" / "seal.key"
    key = fs.ensure_seal_key(key_path)
    assert key == _raw_key(key_path)
    assert key_path.stat().st_mode & 0o777 == 0o600
    assert (tmp_path / "keys").stat().st_mode & 0o777 == 0o700
    assert fs.ensure_seal_key(key_path) == key  # reuse, never replaced
    bad = tmp_path / "bad.key"
    fs.ensure_seal_key(bad)
    for mode in (0o644, 0o700, 0o400, 0o640, 0o604):
        os.chmod(bad, mode)
        with pytest.raises(CatalogRefreshSealError):
            fs.ensure_seal_key(bad)
    # trailing newline: 65 bytes
    (tmp_path / "nl.key").write_bytes(bad.read_bytes() + b"\n")
    os.chmod(tmp_path / "nl.key", 0o600)
    with pytest.raises(CatalogRefreshSealError):
        fs.ensure_seal_key(tmp_path / "nl.key")
    # uppercase hex
    (tmp_path / "upper.key").write_bytes(bad.read_bytes().upper())
    os.chmod(tmp_path / "upper.key", 0o600)
    with pytest.raises(CatalogRefreshSealError):
        fs.ensure_seal_key(tmp_path / "upper.key")
    # symlink key
    os.symlink(bad, tmp_path / "link.key")
    os.chmod(bad, 0o600)
    with pytest.raises(CatalogRefreshSealError):
        fs.ensure_seal_key(tmp_path / "link.key")
    # verify never creates
    missing = tmp_path / "no.key"
    with pytest.raises(CatalogRefreshSealError) as excinfo:
        fs.load_seal_key_bytes(missing)
    assert "does not exist" in str(excinfo.value)
    assert not missing.exists()


def test_key_growing_during_read_refused(tmp_path: Path, monkeypatch) -> None:
    key_path = tmp_path / "grow.key"
    fs.ensure_seal_key(key_path)
    real = fs.os_read

    def growing(fd, n):
        if n == 1:  # EOF probe sees a byte: grew after the snapshot
            return b"5"
        return real(fd, n)

    monkeypatch.setattr(fs, "os_read", growing)
    with pytest.raises(CatalogRefreshSealError) as excinfo:
        fs.ensure_seal_key(key_path)
    assert "grew after the size snapshot" in str(excinfo.value)


def test_key_race_loser_reuses_winner_at_rename_seam(tmp_path: Path, monkeypatch) -> None:
    key_path = tmp_path / "race.key"
    winner_bytes = (b"a1" * 32)  # 64 lowercase hex
    real_rename = fs._renameat2_noreplace
    state = {"called": False}

    def seam(src_dirfd, src_name, dst_dirfd, dst_name):
        if not state["called"]:
            state["called"] = True
            # a peer publishes the winner at the final name right now
            wfd = os.open(dst_name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=dst_dirfd)
            os.write(wfd, winner_bytes)
            os.fchmod(wfd, 0o600)
            os.fsync(wfd)
            os.close(wfd)
            raise fs.PublicationConflictError("destination already exists; refusing to overwrite")
        return real_rename(src_dirfd, src_name, dst_dirfd, dst_name)

    monkeypatch.setattr(fs, "_renameat2_noreplace", seam)
    key = fs.ensure_seal_key(key_path)
    assert key == bytes.fromhex(winner_bytes.decode())
    assert key_path.read_bytes() == winner_bytes
    assert not [p for p in tmp_path.iterdir() if p.name.startswith(".seal-key-")]


# --- atomic NEW-ONLY publication ---------------------------------------------------


def test_mutation_parent_permissions_enforced(tmp_path: Path) -> None:
    p = tmp_path / "writable"
    p.mkdir()
    os.chmod(p, 0o777)
    pfd, _chain = fs.open_anchored_directory(p)
    try:
        with pytest.raises(CatalogRefreshSealError) as excinfo:
            fs.mkdir_private_child(pfd, ".stg-")
        assert "must not be writable by group or other" in str(excinfo.value)
        with pytest.raises(CatalogRefreshSealError):
            fs.publish_new_only_directory(pfd, "nope", "out", (0, 0))
    finally:
        os.close(pfd)
    os.chmod(p, 0o755)  # owner-writable only: accepted
    pfd, _chain = fs.open_anchored_directory(p)
    try:
        name, sfd, _ident = fs.mkdir_private_child(pfd, ".stg-")
        os.close(sfd)
        os.rmdir(p / name)
        fs.publish_new_only_file(p, "out.json", b"{}", 0o644)
        assert (p / "out.json").read_bytes() == b"{}"
    finally:
        os.close(pfd)


def test_publish_refuses_replaced_staging(tmp_path: Path) -> None:
    pfd, _chain = fs.open_anchored_directory(tmp_path)
    try:
        name, sfd, ident = fs.mkdir_private_child(pfd, ".stg-")
        os.close(sfd)
        # rename-based replacement of the (empty) staging dir: foreign
        # directory with a different inode, no inode reuse involved.
        foreign = tmp_path / "foreign"
        foreign.mkdir()
        (foreign / "evil.txt").write_bytes(b"foreign content")
        os.rename(foreign, tmp_path / name)
        assert (tmp_path / name / "evil.txt").exists()
        with pytest.raises(CatalogRefreshSealError) as excinfo:
            fs.publish_new_only_directory(pfd, name, "out", ident)
        assert "replaced" in str(excinfo.value)
        # the foreign directory stays untouched and nothing is published
        assert (tmp_path / name / "evil.txt").read_bytes() == b"foreign content"
        assert not (tmp_path / "out").exists()
    finally:
        os.close(pfd)


def test_sequential_double_publish_conflict(tmp_path: Path) -> None:
    pfd, _chain = fs.open_anchored_directory(tmp_path)
    try:
        name, sfd, ident = fs.mkdir_private_child(pfd, ".stg-")
        os.close(sfd)
        fs.publish_new_only_directory(pfd, name, "out", ident)
        identity_before = (tmp_path / "out").stat()
        name2, sfd2, ident2 = fs.mkdir_private_child(pfd, ".stg2-")
        os.close(sfd2)
        with pytest.raises(fs.PublicationConflictError):
            fs.publish_new_only_directory(pfd, name2, "out", ident2)
        after = (tmp_path / "out").stat()
        assert (identity_before.st_dev, identity_before.st_ino) == (after.st_dev, after.st_ino)
        assert not (tmp_path / "out").exists() or (tmp_path / "out").is_dir()
    finally:
        os.close(pfd)


def test_concurrent_publishers_single_winner(tmp_path: Path, monkeypatch) -> None:
    pfd, _chain = fs.open_anchored_directory(tmp_path)
    try:
        name_a, sfd_a, ident_a = fs.mkdir_private_child(pfd, ".stgA-")
        fs.write_staged_file(sfd_a, "marker.txt", b"A", 0o644)
        os.close(sfd_a)
        name_b, sfd_b, ident_b = fs.mkdir_private_child(pfd, ".stgB-")
        fs.write_staged_file(sfd_b, "marker.txt", b"B", 0o644)
        os.close(sfd_b)
        barrier = threading.Barrier(2)
        real = fs._renameat2_noreplace

        def seam(src_dirfd, src_name, dst_dirfd, dst_name):
            barrier.wait(timeout=10)  # both publishers at the real syscall seam
            return real(src_dirfd, src_name, dst_dirfd, dst_name)

        monkeypatch.setattr(fs, "_renameat2_noreplace", seam)
        results: dict[str, str] = {}

        def worker(tag: str, name: str, ident: tuple[int, int]) -> None:
            try:
                fs.publish_new_only_directory(pfd, name, "published", ident)
                results[tag] = "ok"
            except fs.PublicationConflictError:
                results[tag] = "conflict"
            except Exception as exc:  # pragma: no cover - surfaced via results
                results[tag] = f"error:{exc!r}"

        threads = [
            threading.Thread(target=worker, args=("a", name_a, ident_a)),
            threading.Thread(target=worker, args=("b", name_b, ident_b)),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15)
        assert sorted(results.values()) == ["conflict", "ok"], results
        assert (tmp_path / "published" / "marker.txt").read_bytes() in (b"A", b"B")
    finally:
        os.close(pfd)


def test_cleanup_refuses_replaced_staging(tmp_path: Path) -> None:
    pfd, _chain = fs.open_anchored_directory(tmp_path)
    try:
        name, sfd, ident = fs.mkdir_private_child(pfd, ".stg-")
        os.close(sfd)
        foreign = tmp_path / "foreign"
        foreign.mkdir()
        (foreign / "keep.txt").write_bytes(b"keep")
        os.rename(foreign, tmp_path / name)
        fs.cleanup_staged_directory(pfd, name, ident, [])
        assert (tmp_path / name / "keep.txt").read_bytes() == b"keep"
    finally:
        os.close(pfd)


def test_preexisting_run_target_types_never_overwritten(tmp_path: Path) -> None:
    run_root = tmp_path / "runs"
    run_root.mkdir()
    os.chmod(run_root, 0o700)
    target = run_root / "fixture-first-install-001"
    # 1) empty directory
    target.mkdir()
    result = _invoke_review(tmp_path, run_root, tmp_path / "seal.key")
    assert result.exit_code == 65, result.output
    assert "already exists" in result.stderr
    assert target.is_dir() and not target.is_symlink() and not any(target.iterdir())
    target.rmdir()
    # 2) non-empty directory
    target.mkdir()
    (target / "keep.txt").write_bytes(b"keep")
    result = _invoke_review(tmp_path, run_root, tmp_path / "seal.key")
    assert result.exit_code == 65, result.output
    assert (target / "keep.txt").read_bytes() == b"keep"
    shutil.rmtree(target)
    # 3) regular file
    target.write_bytes(b"sentinel")
    inode_before = target.stat()
    result = _invoke_review(tmp_path, run_root, tmp_path / "seal.key")
    assert result.exit_code == 65, result.output
    after = target.stat()
    assert (inode_before.st_dev, inode_before.st_ino) == (after.st_dev, after.st_ino)
    assert target.read_bytes() == b"sentinel"
    target.unlink()
    # 4) symlink to a directory
    realdir = tmp_path / "realdir"
    realdir.mkdir()
    os.symlink(realdir, target)
    result = _invoke_review(tmp_path, run_root, tmp_path / "seal.key")
    assert result.exit_code == 65, result.output
    assert target.is_symlink()
    assert not (realdir / "fixture-first-install-001").exists()


# --- lifecycle binding -----------------------------------------------------------


def test_anchored_dir_binding_holds_and_detects_swap(tmp_path: Path) -> None:
    d = tmp_path / "a" / "b"
    d.mkdir(parents=True)
    handle = fs.open_anchored_handle(d)
    try:
        handle.assert_name_binding()  # holds
        other = tmp_path / "other"
        other.mkdir()
        os.rename(d, tmp_path / "moved")
        os.rename(other, d)  # swap at the final component (no inode reuse)
        with pytest.raises(CatalogRefreshSealError) as excinfo:
            handle.assert_name_binding()
        assert "binding changed" in str(excinfo.value)
    finally:
        handle.close()


def test_anchored_dir_binding_detects_ancestor_swap(tmp_path: Path) -> None:
    base = tmp_path / "anc"
    inner = base / "runs"
    inner.mkdir(parents=True)
    handle = fs.open_anchored_handle(inner)
    try:
        handle.assert_name_binding()
        outside = tmp_path / "outside"
        (outside / "runs").mkdir(parents=True)
        os.rename(base, tmp_path / "base-moved")
        os.symlink(outside, base)  # swap at an ancestor level
        with pytest.raises(CatalogRefreshSealError):
            handle.assert_name_binding()
    finally:
        handle.close()
        os.unlink(base)  # remove the symlink (leave base-moved for tmp cleanup)


# --- CLI integration ----------------------------------------------------------------


def test_cross_phase_directory_swap_voids_run(tmp_path: Path, monkeypatch) -> None:
    """Strategic reproducer: after the containment check, the run-root and
    key-tree names are swapped (real directories, no symlink, no inode
    reuse). The checked binding changes, so no run may be published and no
    READY may be announced for the stale display pathname."""
    import slaif_gateway.cli.catalog_refresh as cr

    run_root = tmp_path / "runs"
    keys = tmp_path / "keys"
    run_root.mkdir()
    keys.mkdir()
    os.chmod(run_root, 0o700)
    os.chmod(keys, 0o700)
    real_ensure = cr.ensure_seal_key

    def swap_ensure(path, key_parent_fd=None):
        key = real_ensure(path, key_parent_fd=key_parent_fd)
        os.rename(run_root, tmp_path / "original-runs")
        os.rename(keys, run_root)
        return key

    monkeypatch.setattr(cr, "ensure_seal_key", swap_ensure)
    result = runner.invoke(
        app,
        [
            "catalog-refresh", "review",
            str(FIXTURES / "bundle-first-install.json"),
            "--first-install",
            "--run-root", str(run_root),
            "--seal-key", str(keys / "seal.key"),
        ],
    )
    assert result.exit_code == 65, result.output
    assert "binding changed" in result.output
    assert "READY" not in result.output
    # no run under the swapped name; the key stays where the name points;
    # the original run tree is left empty (staging cleaned, nothing published)
    assert not (run_root / "fixture-first-install-001").exists()
    assert (run_root / "seal.key").exists()
    assert [p.name for p in (tmp_path / "original-runs").iterdir()] == []


def test_swap_between_check_and_key_gate_voids_run(tmp_path: Path, monkeypatch) -> None:
    """A swap that lands between the containment check and the key-load
    gate is caught at the key gate: no key is created and nothing is
    published."""
    import slaif_gateway.cli.catalog_refresh as cr

    run_root = tmp_path / "runs"
    keys = tmp_path / "keys"
    run_root.mkdir()
    keys.mkdir()
    os.chmod(run_root, 0o700)
    os.chmod(keys, 0o700)
    real_read = cr.read_user_file
    state = {"swapped": False}

    def swap_read(path, cap):
        data = real_read(path, cap)
        if not state["swapped"]:
            state["swapped"] = True
            os.rename(run_root, tmp_path / "original-runs")
            os.rename(keys, run_root)
        return data

    monkeypatch.setattr(cr, "read_user_file", swap_read)
    result = runner.invoke(
        app,
        [
            "catalog-refresh", "review",
            str(FIXTURES / "bundle-first-install.json"),
            "--first-install",
            "--run-root", str(run_root),
            "--seal-key", str(keys / "seal.key"),
        ],
    )
    assert result.exit_code == 65, result.output
    assert "binding changed" in result.output
    assert not (run_root / "fixture-first-install-001").exists()
    assert not (run_root / "seal.key").exists()  # key never created
    assert [p.name for p in (tmp_path / "original-runs").iterdir()] == []


def test_peer_writable_run_root_refused(tmp_path: Path) -> None:
    run_root = tmp_path / "runs"
    run_root.mkdir()
    os.chmod(run_root, 0o777)
    result = _invoke_review(tmp_path, run_root, tmp_path / "seal.key")
    assert result.exit_code == 65, result.output
    assert "must not be writable by group or other" in result.output
    assert not (run_root / "fixture-first-install-001").exists()
    assert not any(run_root.iterdir())
    assert run_root.stat().st_mode & 0o777 == 0o777  # never chmod'ed


def test_peer_writable_key_parent_refused(tmp_path: Path) -> None:
    keys = tmp_path / "keys"
    keys.mkdir()
    os.chmod(keys, 0o777)
    result = _invoke_review(tmp_path, tmp_path / "runs", keys / "seal.key")
    assert result.exit_code == 65, result.output
    assert "must not be writable by group or other" in result.output
    assert not (keys / "seal.key").exists()
    assert keys.stat().st_mode & 0o777 == 0o777  # never chmod'ed


def test_verify_after_parent_swap_uses_held_bytes(tmp_path: Path, monkeypatch, sealed_run_like: tuple[Path, Path]) -> None:
    """AP-G1: at the actual open seam, the run dir is swapped for a symlink
    to an outside tree AFTER the anchored walk held the real directory.
    Verification must authenticate the ORIGINAL held bytes (or safely
    reject) — never the outside bytes."""
    run_dir, seal_key = sealed_run_like
    outside = run_dir.parent / "outside"
    outside.mkdir()
    (outside / "catalog-refresh.json").write_bytes(b"FORGED OUTSIDE BUNDLE")
    real_open = fs._open_anchored
    state = {"swapped": False}

    def swap_open(path):
        fd, chain = real_open(path)
        if not state["swapped"] and Path(path) == run_dir:
            state["swapped"] = True
            os.rename(run_dir, run_dir.with_name("original-run"))
            os.symlink(outside, run_dir)
        return fd, chain

    monkeypatch.setattr(fs, "_open_anchored", swap_open)
    try:
        result = verify_run(run_dir, _raw_key(seal_key))
    finally:
        if run_dir.is_symlink():
            run_dir.unlink()
        if (run_dir.parent / "original-run").exists():
            os.rename(run_dir.parent / "original-run", run_dir)
    assert state["swapped"]
    if result.valid:
        # valid only if the ORIGINAL descriptor-anchored bytes authenticated
        assert result.checks["digests"] == "ok"
        assert result.checks["hmac"] == "ok"


def test_ancestor_symlink_run_dir_safe_rejects(tmp_path: Path) -> None:
    base = tmp_path / "anc"
    run_root = base / "runs"
    run_root.mkdir(parents=True)
    os.chmod(base, 0o700)
    os.chmod(run_root, 0o700)
    seal_key = tmp_path / "anc.key"
    result = _invoke_review(tmp_path, run_root, seal_key)
    assert result.exit_code == 0, result.output
    run_dir = run_root / "fixture-first-install-001"
    outside = tmp_path / "outside-anc"
    (outside / "runs" / "fixture-first-install-001").mkdir(parents=True)
    (outside / "runs" / "fixture-first-install-001" / "receipt.json").write_bytes(b"FORGED")
    os.rename(base, tmp_path / "base-moved")
    os.symlink(outside, base)
    try:
        verified = verify_run(run_dir, _raw_key(seal_key))
    finally:
        os.unlink(base)
    assert not verified.valid
    assert verified.checks["run_dir"] == "missing"


def test_cli_refuses_fifo_bundle_promptly(tmp_path: Path) -> None:
    fifo = tmp_path / "bundle.fifo"
    os.mkfifo(fifo)
    code = (
        "import sys; sys.path.insert(0, 'app');\n"
        "from typer.testing import CliRunner, Result;\n"
        "from slaif_gateway.cli.main import app;\n"
        f"r = CliRunner().invoke(app, ['catalog-refresh', 'review', {str(fifo)!r}, "
        f"'--first-install', '--run-root', {str(tmp_path / 'runs')!r}, "
        f"'--seal-key', {str(tmp_path / 'k.key')!r}]);\n"
        "sys.exit(r.exit_code)\n"
    )
    try:
        proc = subprocess.run(
            [sys.executable, "-c", code],
            cwd=REPO_ROOT,
            timeout=15,
            capture_output=True,
            text=True,
        )
    except subprocess.TimeoutExpired as exc:
        pytest.fail(f"FIFO bundle input blocked the CLI past the hard timeout: {exc}")
    assert proc.returncode == 65, proc.stdout + proc.stderr


def test_cli_refuses_sparse_oversize_bundle(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle.json"
    with open(bundle, "wb") as fh:
        fh.truncate(9 * 1024 * 1024)
    result = runner.invoke(
        app,
        [
            "catalog-refresh", "review", str(bundle),
            "--first-install",
            "--run-root", str(tmp_path / "runs"),
            "--seal-key", str(tmp_path / "seal.key"),
        ],
    )
    assert result.exit_code == 65, result.output
    assert "bundle file is not readable" in result.stderr


def test_seal_capture_once_per_file(tmp_path: Path, monkeypatch) -> None:
    """AP-G5: each run content file and the manifest are captured exactly
    once through the held descriptor; the receipt is never read back."""
    counts: dict[str, int] = {}
    real = fs.anchored_read_fd

    def counting(dir_fd, name, cap):
        counts[name] = counts.get(name, 0) + 1
        return real(dir_fd, name, cap)

    monkeypatch.setattr(fs, "anchored_read_fd", counting)
    result = _invoke_review(tmp_path, tmp_path / "runs", tmp_path / "seal.key")
    assert result.exit_code == 0, result.output
    for name in CONTENT_FILES:
        assert counts.get(name) == 1, counts
    assert counts.get("manifest.json") == 1
    assert counts.get("receipt.json", 0) == 0


def test_first_install_forged_marker_fails(tmp_path: Path, monkeypatch, sealed_run_like: tuple[Path, Path]) -> None:
    """Even a forger holding the key cannot pass: first-install
    verification requires the EXACT canonical empty marker bytes, not any
    object carrying the expected schema_version."""
    run_dir, seal_key = sealed_run_like
    key = _raw_key(seal_key)
    base_path = run_dir / "catalog-baseline.json"
    doc = json.loads(base_path.read_bytes())
    doc["note"] = doc["note"] + " (forged)"
    base_path.write_bytes((json.dumps(doc, sort_keys=True, indent=1) + "\n").encode())
    # the forger (WITH the key) recomputes every local value
    content = {name: (run_dir / name).read_bytes() for name in CONTENT_FILES}
    manifest = {
        "schema_version": "1",
        "files": [
            {"path": name, "sha256": hashlib.sha256(content[name]).hexdigest(), "bytes": len(content[name])}
            for name in sorted(content)
        ],
    }
    manifest_bytes = (json.dumps(manifest, sort_keys=True, indent=1) + "\n").encode()
    (run_dir / "manifest.json").write_bytes(manifest_bytes)
    bundle_raw = content["catalog-refresh.json"]
    bundle = load_bundle(bundle_raw)
    semantic = hashlib.sha256(canonical_bundle_bytes(bundle)).hexdigest()
    identity = json.loads(bundle_raw)
    manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
    payload = _hmac_payload(
        identity["run_id"],
        identity["generated_at"],
        manifest_sha256,
        content_hashes(content),
        semantic,
    )
    receipt = {
        "schema_version": "1",
        "files": dict(sorted(content_hashes(content).items())),
        "manifest_sha256": manifest_sha256,
        "semantic_bundle_sha256": semantic,
        "hmac_sha256": hmac.new(key, payload, hashlib.sha256).hexdigest(),
    }
    (run_dir / "receipt.json").write_bytes((json.dumps(receipt, sort_keys=True, indent=1) + "\n").encode())
    result = verify_run(run_dir, key)
    assert not result.valid
    assert "first_install" in result.checks


def test_manifest_declared_bounds_checked_before_reading(tmp_path: Path, sealed_run_like: tuple[Path, Path]) -> None:
    """Bounds are reconciled against the DECLARED manifest before any
    content is read: count, per-file caps (bundle 8 MiB) and aggregate
    128 MiB including manifest/receipt overhead."""
    run_dir, seal_key = sealed_run_like
    key = _raw_key(seal_key)
    # 65 declared entries (files absent)
    manifest = {
        "schema_version": "1",
        "files": [
            {"path": f"f{i}.json", "sha256": "0" * 64, "bytes": 1} for i in range(65)
        ],
    }
    (run_dir / "manifest.json").write_bytes(
        (json.dumps(manifest, sort_keys=True, indent=1) + "\n").encode()
    )
    result = verify_run(run_dir, key)
    assert not result.valid
    assert "bounds" in result.checks
    # aggregate: 6 x 21 MiB + 7 MiB bundle = 133 MiB > 128 MiB
    manifest = {
        "schema_version": "1",
        "files": [
            {
                "path": name,
                "sha256": "0" * 64,
                "bytes": 7 * 1024 * 1024 if name == "catalog-refresh.json" else 21 * 1024 * 1024,
            }
            for name in CONTENT_FILES
        ],
    }
    (run_dir / "manifest.json").write_bytes(
        (json.dumps(manifest, sort_keys=True, indent=1) + "\n").encode()
    )
    result = verify_run(run_dir, key)
    assert not result.valid
    assert "bounds" in result.checks
    # bundle per-file cap: 9 MiB declared for the bundle > 8 MiB
    manifest = {
        "schema_version": "1",
        "files": [
            {
                "path": name,
                "sha256": "0" * 64,
                "bytes": 9 * 1024 * 1024 if name == "catalog-refresh.json" else 1,
            }
            for name in CONTENT_FILES
        ],
    }
    (run_dir / "manifest.json").write_bytes(
        (json.dumps(manifest, sort_keys=True, indent=1) + "\n").encode()
    )
    result = verify_run(run_dir, key)
    assert not result.valid
    assert "bounds" in result.checks


def test_export_baseline_atomic_new_only(tmp_path: Path, monkeypatch) -> None:
    import slaif_gateway.cli.catalog_refresh as cr

    raw = (FIXTURES / "baseline-synthetic.json").read_bytes()

    async def fake_export(database_url, *, now, page_size=500):
        return load_baseline(raw)

    monkeypatch.setattr(cr, "export_baseline", fake_export)
    out = tmp_path / "baseline.json"
    result = runner.invoke(
        app,
        [
            "catalog-refresh", "export-baseline",
            "--out", str(out),
            "--db-url", "postgresql+asyncpg://u@localhost/db",
        ],
    )
    assert result.exit_code == 0, result.output
    assert out.read_bytes() == cr._baseline_document_bytes(load_baseline(raw))
    out2 = tmp_path / "out2.json"
    realdir = tmp_path / "targetdir"
    realdir.mkdir()
    # pre-existing file
    out2.write_bytes(b"{}")
    before = out2.stat()
    result = runner.invoke(
        app,
        [
            "catalog-refresh", "export-baseline",
            "--out", str(out2),
            "--db-url", "postgresql+asyncpg://u@localhost/db",
        ],
    )
    assert result.exit_code == 65, result.output
    assert "refusing to overwrite existing output" in result.stderr
    after = out2.stat()
    assert (before.st_dev, before.st_ino) == (after.st_dev, after.st_ino)
    assert out2.read_bytes() == b"{}"
    out2.unlink()
    # pre-existing empty directory
    out2.mkdir()
    result = runner.invoke(
        app,
        [
            "catalog-refresh", "export-baseline",
            "--out", str(out2),
            "--db-url", "postgresql+asyncpg://u@localhost/db",
        ],
    )
    assert result.exit_code == 65, result.output
    assert out2.is_dir() and not any(out2.iterdir())
    out2.rmdir()
    # pre-existing symlink
    os.symlink(realdir, out2)
    result = runner.invoke(
        app,
        [
            "catalog-refresh", "export-baseline",
            "--out", str(out2),
            "--db-url", "postgresql+asyncpg://u@localhost/db",
        ],
    )
    assert result.exit_code == 65, result.output
    assert out2.is_symlink()
    assert not any(realdir.iterdir())
