"""181-i (I3): bounded measured code identity for catalog refresh.

The identity is a deterministic SHA-256 over a FIXED small set of owned
catalog-refresh files (logical name + content). These tests pin the
honesty contract:

- deterministic for the same bytes;
- changed bytes DO change it, even under an unchanged package version;
- relocation (tree moved, same bytes) does NOT change it;
- missing / non-regular / unreadable input yields the explicit
  ``unavailable`` marker — never a fabricated "known current" identity;
- bounds (file count, per-file size, aggregate size) fail closed;
- the measurement depends on neither the CWD nor any Git state;
- the package version stays separately in the tool metadata, and the
  generator version set is the running code's own constants.
"""

from __future__ import annotations

import os
import shutil
import stat
from pathlib import Path

import pytest

from slaif_gateway.services.catalog_refresh import execution_identity as ei


def _write_tree(root: Path) -> None:
    """Materialize the fixed identity file set with known contents."""
    for name in ei.IDENTITY_FILES:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(f"content-of-{name}\n".encode("utf-8"))


def test_identity_is_deterministic_and_prefixed() -> None:
    _write_tree_root = Path("/tmp/ei-test-deterministic")
    if _write_tree_root.exists():
        shutil.rmtree(_write_tree_root)
    root = _write_tree_root
    root.mkdir(parents=True)
    _write_tree(root)
    first = ei.measure_code_identity(root=root)
    second = ei.measure_code_identity(root=root)
    assert first == second
    assert first.startswith("catalog-ccid/v1:sha256:")
    assert len(first) == len("catalog-ccid/v1:sha256:") + 64
    shutil.rmtree(root)


def test_changed_bytes_change_the_identity() -> None:
    root = Path("/tmp/ei-test-changed")
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    _write_tree(root)
    baseline = ei.measure_code_identity(root=root)
    # same "package version", different bytes: the identity MUST differ
    victim = root / "services/catalog_refresh/validation.py"
    victim.write_bytes(victim.read_bytes() + b"# changed\n")
    changed = ei.measure_code_identity(root=root)
    assert changed != baseline
    shutil.rmtree(root)


def test_relocation_keeps_the_identity() -> None:
    source = Path("/tmp/ei-test-relocate-a")
    target = Path("/tmp/ei-test-relocate-b")
    for p in (source, target):
        if p.exists():
            shutil.rmtree(p)
    source.mkdir(parents=True)
    _write_tree(source)
    original = ei.measure_code_identity(root=source)
    shutil.copytree(source, target)
    assert ei.measure_code_identity(root=target) == original
    shutil.rmtree(source)
    shutil.rmtree(target)


def test_missing_file_is_unavailable() -> None:
    root = Path("/tmp/ei-test-missing")
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    _write_tree(root)
    (root / "services/catalog_refresh/rendering.py").unlink()
    assert ei.measure_code_identity(root=root) == ei.CODE_IDENTITY_UNAVAILABLE
    shutil.rmtree(root)


def test_symlinked_file_is_unavailable() -> None:
    root = Path("/tmp/ei-test-symlink")
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    _write_tree(root)
    victim = root / "cli/catalog_refresh.py"
    victim.unlink()
    os.symlink(root / "services/catalog_refresh/bundle.py", victim)
    assert ei.measure_code_identity(root=root) == ei.CODE_IDENTITY_UNAVAILABLE
    shutil.rmtree(root)


def test_unreadable_file_is_unavailable() -> None:
    if os.geteuid() == 0:
        pytest.skip("root ignores file permissions; the fail-closed path is "
                    "still exercised by the missing/non-regular cases")
    root = Path("/tmp/ei-test-unreadable")
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    _write_tree(root)
    victim = root / "schemas/catalog_refresh.py"
    victim.chmod(0o000)
    try:
        assert ei.measure_code_identity(root=root) == ei.CODE_IDENTITY_UNAVAILABLE
    finally:
        victim.chmod(0o644)
        shutil.rmtree(root)


def test_growing_file_between_stat_and_read_is_unavailable(monkeypatch) -> None:
    """The one-byte EOF probe: growth after the stat is detected, not
    silently digested as a prefix."""
    root = Path("/tmp/ei-test-growth")
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    _write_tree(root)

    real_read_bounded = ei._read_bounded

    def growing_read(path, expected_size):
        # simulate a concurrent writer appending after the stat
        with open(path, "ab") as handle:
            handle.write(b"# concurrent append\n")
        return real_read_bounded(path, expected_size)

    monkeypatch.setattr(ei, "_read_bounded", growing_read)
    assert ei.measure_code_identity(root=root) == ei.CODE_IDENTITY_UNAVAILABLE
    monkeypatch.undo()
    shutil.rmtree(root)


def test_shrinking_file_is_unavailable(monkeypatch) -> None:
    root = Path("/tmp/ei-test-shrink")
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    _write_tree(root)

    real_read_bounded = ei._read_bounded

    def shrinking_read(path, expected_size):
        with open(path, "wb") as handle:  # truncate below the stat size
            handle.write(b"short\n")
        return real_read_bounded(path, expected_size)

    monkeypatch.setattr(ei, "_read_bounded", shrinking_read)
    assert ei.measure_code_identity(root=root) == ei.CODE_IDENTITY_UNAVAILABLE
    monkeypatch.undo()
    shutil.rmtree(root)


def test_file_count_bound_is_enforced() -> None:
    root = Path("/tmp/ei-test-count-bound")
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    _write_tree(root)
    original = ei.MAX_IDENTITY_FILES
    monkeypatch = pytest.MonkeyPatch()
    try:
        monkeypatch.setattr(ei, "MAX_IDENTITY_FILES", len(ei.IDENTITY_FILES) - 1)
        assert ei.measure_code_identity(root=root) == ei.CODE_IDENTITY_UNAVAILABLE
    finally:
        monkeypatch.undo()
    assert ei.MAX_IDENTITY_FILES == original


def test_per_file_and_aggregate_bounds_are_enforced(monkeypatch) -> None:
    root = Path("/tmp/ei-test-size-bound")
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    _write_tree(root)
    big = root / "cli/catalog_refresh.py"
    big.write_bytes(b"x" * (ei.MAX_IDENTITY_FILE_BYTES + 1))
    assert ei.measure_code_identity(root=root) == ei.CODE_IDENTITY_UNAVAILABLE
    big.write_bytes(b"ok\n")
    # aggregate bound: shrink the budget until the (small) set exceeds it
    monkeypatch.setattr(ei, "MAX_IDENTITY_TOTAL_BYTES", 1)
    try:
        assert ei.measure_code_identity(root=root) == ei.CODE_IDENTITY_UNAVAILABLE
    finally:
        monkeypatch.undo()
    shutil.rmtree(root)


def test_measurement_does_not_depend_on_cwd(tmp_path: Path) -> None:
    root = Path("/tmp/ei-test-cwd")
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    _write_tree(root)
    original_cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        from_cwd_a = ei.measure_code_identity(root=root)
        os.chdir(original_cwd)
        from_cwd_b = ei.measure_code_identity(root=root)
    finally:
        os.chdir(original_cwd)
        shutil.rmtree(root)
    assert from_cwd_a == from_cwd_b


def test_package_root_measurement_is_real_and_stable() -> None:
    """The installed package root measurement is deterministic and covers
    the fixed set (relocation of the WHOLE tree would keep it)."""
    first = ei.measure_code_identity()
    second = ei.measure_code_identity()
    assert first == second
    assert first != ei.CODE_IDENTITY_UNAVAILABLE
    assert first.startswith("catalog-ccid/v1:sha256:")
    # the fixed set includes the helper itself: the identity is over a
    # non-empty, bounded set of owned files
    assert len(ei.IDENTITY_FILES) <= ei.MAX_IDENTITY_FILES
    root = ei._package_root()
    for name in ei.IDENTITY_FILES:
        assert (root / name).is_file(), name


def test_tool_identity_combines_version_and_measured_revision() -> None:
    tool, revision = ei.tool_identity()
    assert tool == f"slaif-gateway/{ei.package_version()}"
    assert revision == ei.measure_code_identity() or revision == ei.CODE_IDENTITY_UNAVAILABLE
    # the package version alone is NOT the code identity: a different
    # byte set (the /tmp fixture tree) must measure differently
    root = Path("/tmp/ei-test-tool")
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    _write_tree(root)
    assert ei.measure_code_identity(root=root) != revision
    shutil.rmtree(root)


def test_generator_versions_are_the_running_codes_constants() -> None:
    from slaif_gateway.schemas.catalog_refresh import (
        EXTRACTOR_ID,
        POLICY_VERSION,
        RENDERER_VERSION,
        SCHEMA_VERSION,
    )

    assert ei.generator_versions() == {
        "schema_version": SCHEMA_VERSION,
        "renderer_version": RENDERER_VERSION,
        "policy_version": POLICY_VERSION,
        "extractor_version": EXTRACTOR_ID,
    }


def test_uninstalled_package_version_is_honest() -> None:
    """An unresolvable distribution name must yield the honest local
    marker, not a fabricated version."""
    real = ei._package_version

    def missing(name):
        raise Exception("uninstalled")

    monkeypatch = pytest.MonkeyPatch()
    try:
        monkeypatch.setattr(ei, "_package_version", missing)
        assert ei.package_version() == "0.0.0+local"
    finally:
        monkeypatch.undo()
    assert ei._package_version is real


def test_regular_file_check_uses_lstat_semantics() -> None:
    """A directory where a file is expected is non-regular: unavailable."""
    root = Path("/tmp/ei-test-dir-as-file")
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    (root / "cli").mkdir(parents=True)
    (root / "cli/catalog_refresh.py").mkdir()
    for name in ei.IDENTITY_FILES:
        if name == "cli/catalog_refresh.py":
            continue
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x\n")
    try:
        assert ei.measure_code_identity(root=root) == ei.CODE_IDENTITY_UNAVAILABLE
        _ = stat.S_ISREG  # lstat-based type check is what the helper applies
    finally:
        shutil.rmtree(root)
