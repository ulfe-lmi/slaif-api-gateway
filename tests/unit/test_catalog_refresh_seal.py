"""HMAC sealing and verification: fail-closed tamper and path semantics."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
from pathlib import Path

import pytest
from typer.testing import CliRunner

from slaif_gateway.cli.main import app
from slaif_gateway.services.catalog_refresh.errors import CatalogRefreshSealError
from slaif_gateway.services.catalog_refresh import filesystem as fs
from slaif_gateway.services.catalog_refresh import sealing
from slaif_gateway.services.catalog_refresh.sealing import (
    CONTENT_FILES,
    ensure_seal_key,
    verify_run,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "catalog_refresh"
runner = CliRunner()


@pytest.fixture()
def sealed_run(tmp_path: Path) -> tuple[Path, Path]:
    """Run the CLI review once and return (run_dir, seal_key_path)."""
    run_root = tmp_path / "runs"
    seal_key = tmp_path / "seal.key"
    result = runner.invoke(
        app,
        [
            "catalog-refresh", "review",
            str(FIXTURES / "bundle-first-install.json"),
            "--first-install",
            "--run-root", str(run_root),
            "--seal-key", str(seal_key),
        ],
    )
    # 182: every first-install model is new exposure -> the run is
    # READY_WITH_WARNINGS (exit 10); the run is still sealed/verifiable.
    assert result.exit_code == 10, result.output
    return run_root / "fixture-first-install-001", seal_key


def _key(run: tuple[Path, Path]) -> bytes:
    return (run[1]).read_bytes()  # hex text


def _raw_key(path: Path) -> bytes:
    return bytes.fromhex(path.read_bytes().decode("ascii"))


def test_round_trip_verifies_cleanly(sealed_run: tuple[Path, Path]) -> None:
    run_dir, seal_key = sealed_run
    result = verify_run(run_dir, _raw_key(seal_key))
    assert result.valid
    # 182: first-install carries new-exposure warnings -> READY_WITH_WARNINGS
    assert result.state == "READY_WITH_WARNINGS"
    assert result.checks["digests"] == "ok"
    assert result.checks["hmac"] == "ok"
    assert result.checks["correspondence"] == "ok"


@pytest.mark.parametrize("content_file", list(CONTENT_FILES))
def test_tampering_each_content_file_fails(sealed_run: tuple[Path, Path], content_file: str) -> None:
    run_dir, seal_key = sealed_run
    target = run_dir / content_file
    data = target.read_bytes()
    target.write_bytes(data + b"tampered\n" if content_file != "catalog-refresh.json" else data.replace(b"fixture-first-install-001", b"fixture-first-install-999"))
    result = verify_run(run_dir, _raw_key(seal_key))
    assert not result.valid
    target.write_bytes(data)  # restore for other checks


def test_tampering_manifest_or_receipt_fails(sealed_run: tuple[Path, Path]) -> None:
    run_dir, seal_key = sealed_run
    for name in ("manifest.json", "receipt.json"):
        target = run_dir / name
        original = target.read_bytes()
        target.write_bytes(original + b"\n")
        assert not verify_run(run_dir, _raw_key(seal_key)).valid
        target.write_bytes(original)


def test_wrong_key_fails(sealed_run: tuple[Path, Path]) -> None:
    run_dir, seal_key = sealed_run
    wrong = Path(seal_key.parent / "other.key")
    ensure_seal_key(wrong)
    assert wrong.read_bytes() != seal_key.read_bytes()
    result = verify_run(run_dir, _raw_key(wrong))
    assert not result.valid
    assert "hmac" in result.checks or "digest" in result.checks


def test_coordinated_tamper_without_key_still_fails(sealed_run: tuple[Path, Path]) -> None:
    """Manipulating proposal + report + manifest together is not enough."""
    run_dir, seal_key = sealed_run
    bundle_path = run_dir / "catalog-refresh.json"
    original = bundle_path.read_bytes()
    mutated = original.replace(b"all-EUR pricing, create-only bootstrap.", b"all-EUR pricing, create-only bootstrap TAMPERED")
    bundle_path.write_bytes(mutated)
    # Recompute manifest + receipt digests as a tamperer with local knowledge would.
    files = {name: hashlib.sha256((run_dir / name).read_bytes()).hexdigest() for name in CONTENT_FILES}
    manifest = {"schema_version": "1", "files": [
        {"path": name, "sha256": files[name], "bytes": (run_dir / name).stat().st_size}
        for name in sorted(files)
    ]}
    manifest_bytes = (json.dumps(manifest, sort_keys=True, indent=1) + "\n").encode("utf-8")
    (run_dir / "manifest.json").write_bytes(manifest_bytes)
    receipt = json.loads((run_dir / "receipt.json").read_bytes())
    receipt["files"] = dict(sorted(files.items()))
    receipt["manifest_sha256"] = hashlib.sha256(manifest_bytes).hexdigest()
    # The semantic hash is local knowledge (not secret); a determined tamperer
    # refreshes it too. Only the HMAC requires the external key.
    from slaif_gateway.services.catalog_refresh.bundle import canonical_bundle_bytes, load_bundle

    receipt["semantic_bundle_sha256"] = hashlib.sha256(
        canonical_bundle_bytes(load_bundle((run_dir / "catalog-refresh.json").read_bytes()))
    ).hexdigest()
    (run_dir / "receipt.json").write_bytes((json.dumps(receipt, sort_keys=True, indent=1) + "\n").encode("utf-8"))
    result = verify_run(run_dir, _raw_key(seal_key))
    assert not result.valid
    # Ordinary digests and manifest consistency all pass; the external HMAC fails.
    assert result.checks.get("digests") == "ok"
    assert result.checks.get("hmac") == "authentication failed"


def test_missing_file_fails(sealed_run: tuple[Path, Path]) -> None:
    run_dir, seal_key = sealed_run
    victim = run_dir / "validation.json"
    data = victim.read_bytes()
    victim.unlink()
    try:
        assert not verify_run(run_dir, _raw_key(seal_key)).valid
    finally:
        victim.write_bytes(data)


def test_missing_run_dir_fails(tmp_path: Path, sealed_run: tuple[Path, Path]) -> None:
    _, seal_key = sealed_run
    result = verify_run(tmp_path / "does-not-exist", _raw_key(seal_key))
    assert not result.valid
    assert result.checks["run_dir"] == "missing"


def test_path_traversal_manifest_entry_is_refused(sealed_run: tuple[Path, Path], tmp_path: Path) -> None:
    run_dir, seal_key = sealed_run
    (run_dir.parent / "evil.txt").write_bytes(b"outside the run\n")
    manifest = json.loads((run_dir / "manifest.json").read_bytes())
    manifest["files"].append({"path": "../evil.txt", "sha256": "0" * 64, "bytes": 17})
    (run_dir / "manifest.json").write_bytes((json.dumps(manifest, sort_keys=True, indent=1) + "\n").encode("utf-8"))
    assert not verify_run(run_dir, _raw_key(seal_key)).valid


def test_symlink_content_file_is_refused(sealed_run: tuple[Path, Path]) -> None:
    run_dir, seal_key = sealed_run
    target = run_dir / "validation.json"
    data = target.read_bytes()
    outside = run_dir.parent / "outside-validation.json"
    outside.write_bytes(data)
    target.unlink()
    os.symlink(outside, target)
    try:
        assert not verify_run(run_dir, _raw_key(seal_key)).valid
    finally:
        target.unlink()
        target.write_bytes(data)


def test_file_size_bound_is_enforced(sealed_run: tuple[Path, Path]) -> None:
    """A single run file above the 32 MiB acceptance bound is refused."""
    run_dir, seal_key = sealed_run
    victim = run_dir / "REVIEW.html"
    data = victim.read_bytes()
    victim.write_bytes(data + b"x" * (33 * 1024 * 1024))
    try:
        assert not verify_run(run_dir, _raw_key(seal_key)).valid
    finally:
        victim.write_bytes(data)


def test_nested_depth_bound_is_enforced(sealed_run: tuple[Path, Path]) -> None:
    run_dir, seal_key = sealed_run
    deep = run_dir / "a" / "b" / "c" / "d" / "e" / "f"
    deep.mkdir(parents=True)
    (deep / "deep.txt").write_bytes(b"deep")
    manifest = json.loads((run_dir / "manifest.json").read_bytes())
    manifest["files"].append({"path": "a/b/c/d/e/f/deep.txt", "sha256": hashlib.sha256(b"deep").hexdigest(), "bytes": 4})
    (run_dir / "manifest.json").write_bytes((json.dumps(manifest, sort_keys=True, indent=1) + "\n").encode("utf-8"))
    try:
        assert not verify_run(run_dir, _raw_key(seal_key)).valid
    finally:
        shutil.rmtree(run_dir / "a")
        (run_dir / "manifest.json").write_bytes((json.dumps(manifest, sort_keys=True, indent=1) + "\n").encode("utf-8"))


def test_duplicate_json_key_in_bundle_fails_verification(sealed_run: tuple[Path, Path]) -> None:
    run_dir, seal_key = sealed_run
    bundle_path = run_dir / "catalog-refresh.json"
    original = bundle_path.read_bytes()
    duplicated = original.replace(b'"run_id":"fixture-first-install-001"', b'"run_id":"fixture-first-install-001","run_id":"x"', 1)
    assert duplicated != original
    bundle_path.write_bytes(duplicated)
    try:
        # A tamperer who refreshes every local digest still cannot hide that
        # the canonical bundle is unparseable (duplicate JSON key).
        files = {name: hashlib.sha256((run_dir / name).read_bytes()).hexdigest() for name in CONTENT_FILES}
        manifest = {"schema_version": "1", "files": [
            {"path": name, "sha256": files[name], "bytes": (run_dir / name).stat().st_size}
            for name in sorted(files)
        ]}
        manifest_bytes = (json.dumps(manifest, sort_keys=True, indent=1) + "\n").encode("utf-8")
        (run_dir / "manifest.json").write_bytes(manifest_bytes)
        receipt = json.loads((run_dir / "receipt.json").read_bytes())
        receipt["files"] = dict(sorted(files.items()))
        receipt["manifest_sha256"] = hashlib.sha256(manifest_bytes).hexdigest()
        # Semantic recompute will itself fail at parse; keep the original value
        # so verification reaches the bundle-parse layer.
        (run_dir / "receipt.json").write_bytes((json.dumps(receipt, sort_keys=True, indent=1) + "\n").encode("utf-8"))
        result = verify_run(run_dir, _raw_key(seal_key))
        assert not result.valid
        assert result.checks.get("bundle") == "bundle_invalid_json"
    finally:
        bundle_path.write_bytes(original)
        manifest_original = json.loads((run_dir / "manifest.json").read_bytes())
        (run_dir / "manifest.json").write_bytes((json.dumps(manifest_original, sort_keys=True, indent=1) + "\n").encode("utf-8"))


def test_verify_never_writes_or_resigns(sealed_run: tuple[Path, Path]) -> None:
    run_dir, seal_key = sealed_run

    def snapshot() -> dict[str, tuple[int, int]]:
        return {
            path.name: (path.stat().st_size, int(path.stat().st_mtime_ns))
            for path in sorted(run_dir.iterdir())
        }

    before = snapshot()
    result = verify_run(run_dir, _raw_key(seal_key))
    assert result.valid
    assert snapshot() == before  # no file added, grown, or re-signed


def test_seal_key_creation_mode_and_refusals(tmp_path: Path) -> None:
    key_path = tmp_path / "keys" / "seal.key"
    ensure_seal_key(key_path)
    assert stat.S_IMODE(key_path.stat().st_mode) == 0o600
    first = key_path.read_bytes()
    # Existing keys are loaded, never silently overwritten.
    assert ensure_seal_key(key_path) == bytes.fromhex(first.decode("ascii"))
    assert key_path.read_bytes() == first

    bad_mode = tmp_path / "badmode.key"
    ensure_seal_key(bad_mode)
    os.chmod(bad_mode, 0o644)
    with pytest.raises(CatalogRefreshSealError):
        ensure_seal_key(bad_mode)

    wrong_length = tmp_path / "short.key"
    wrong_length.write_bytes(b"ab" * 10)
    with pytest.raises(CatalogRefreshSealError):
        ensure_seal_key(wrong_length)

    symlinked = tmp_path / "link.key"
    os.symlink(key_path, symlinked)
    with pytest.raises(CatalogRefreshSealError):
        ensure_seal_key(symlinked)


def test_no_key_material_in_artifacts(sealed_run: tuple[Path, Path]) -> None:
    run_dir, seal_key = sealed_run
    secret_hex = seal_key.read_bytes().decode("ascii")
    for name in (*CONTENT_FILES, "manifest.json", "receipt.json"):
        data = (run_dir / name).read_bytes()
        assert secret_hex not in data.decode("utf-8", errors="replace")
        assert bytes.fromhex(secret_hex) not in data

# --- 180-b adversarial additions ---------------------------------------------


def test_parent_symlink_component_is_refused(sealed_run: tuple[Path, Path]) -> None:
    run_dir, seal_key = sealed_run
    outside = run_dir.parent / "outside-dir"
    outside.mkdir()
    (outside / "sneaky.json").write_bytes(b"{}")
    inner = run_dir / "sub"
    inner.mkdir()
    os.symlink(outside, inner / "link")
    try:
        manifest = json.loads((run_dir / "manifest.json").read_bytes())
        manifest["files"].append(
            {"path": "sub/link/sneaky.json", "sha256": hashlib.sha256(b"{}").hexdigest(), "bytes": 2}
        )
        (run_dir / "manifest.json").write_bytes((json.dumps(manifest, sort_keys=True, indent=1) + "\n").encode("utf-8"))
        assert not verify_run(run_dir, _raw_key(seal_key)).valid
    finally:
        (inner / "link").unlink()
        inner.rmdir()
        (outside / "sneaky.json").unlink()
        outside.rmdir()


def test_dangling_symlink_content_file_is_refused(sealed_run: tuple[Path, Path]) -> None:
    run_dir, seal_key = sealed_run
    target = run_dir / "validation.json"
    data = target.read_bytes()
    target.unlink()
    os.symlink(run_dir.parent / "nonexistent-target", target)
    try:
        assert not verify_run(run_dir, _raw_key(seal_key)).valid
    finally:
        target.unlink()
        target.write_bytes(data)


def test_concurrent_seal_key_initialization_single_winner(tmp_path: Path) -> None:
    """Race-safe O_EXCL key creation: one winner, the rest reuse its key."""
    import threading

    key_path = tmp_path / "concurrent.key"
    results: list[bytes] = []
    errors: list[Exception] = []

    def worker() -> None:
        try:
            results.append(ensure_seal_key(key_path))
        except Exception as exc:  # pragma: no cover - surfaced via errors
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert not errors
    assert len(results) == 8
    assert len({result.hex() for result in results}) == 1  # one key won
    assert stat.S_IMODE(key_path.stat().st_mode) == 0o600
    # A follow-up load returns the same bytes; the key was never replaced.
    assert ensure_seal_key(key_path) == results[0]


def test_concurrent_existing_invalid_key_is_never_replaced(tmp_path: Path) -> None:
    """A loser in the race must fail on an invalid winner key, not overwrite it."""
    key_path = tmp_path / "invalid.key"
    key_path.write_bytes(b"not-a-valid-key")
    with pytest.raises(CatalogRefreshSealError):
        ensure_seal_key(key_path)
    assert key_path.read_bytes() == b"not-a-valid-key"


def test_manifest_duplicate_path_is_refused(sealed_run: tuple[Path, Path]) -> None:
    run_dir, seal_key = sealed_run
    manifest = json.loads((run_dir / "manifest.json").read_bytes())
    first = dict(manifest["files"][0])
    manifest["files"].append(first)
    try:
        (run_dir / "manifest.json").write_bytes((json.dumps(manifest, sort_keys=True, indent=1) + "\n").encode("utf-8"))
        assert not verify_run(run_dir, _raw_key(seal_key)).valid
    finally:
        manifest["files"] = manifest["files"][: -1]
        (run_dir / "manifest.json").write_bytes((json.dumps(manifest, sort_keys=True, indent=1) + "\n").encode("utf-8"))


def test_malformed_manifest_shape_is_refused(sealed_run: tuple[Path, Path]) -> None:
    run_dir, seal_key = sealed_run
    original = (run_dir / "manifest.json").read_bytes()
    for payload in (b"[]", b'{"schema_version": "2", "files": []}', b'{"files": []}',
                    b'{"schema_version": "1", "files": [{"path": "a"}]}'):
        (run_dir / "manifest.json").write_bytes(payload)
        assert not verify_run(run_dir, _raw_key(seal_key)).valid
    (run_dir / "manifest.json").write_bytes(original)


def test_review_failure_leaves_no_partial_run(tmp_path: Path, monkeypatch) -> None:
    """A failure during staging/publish must leave nothing at the final path."""
    import slaif_gateway.cli.catalog_refresh as cr

    def boom(_run_dir, _key):
        raise CatalogRefreshSealError("simulated seal failure")

    monkeypatch.setattr(cr, "seal_run", boom)
    result = runner.invoke(
        app,
        [
            "catalog-refresh", "review",
            str(FIXTURES / "bundle-first-install.json"),
            "--first-install",
            "--run-root", str(tmp_path / "runs"),
            "--seal-key", str(tmp_path / "seal.key"),
        ],
    )
    assert result.exit_code == 65, result.output
    run_root = tmp_path / "runs"
    assert not (run_root / "fixture-first-install-001").exists()
    leftovers = [p.name for p in run_root.iterdir()] if run_root.exists() else []
    assert leftovers == [], f"staging leftovers: {leftovers}"


# --- 181-i (I2): authenticated execution context in the sealed run ------------


def _recompute_manifest(run_dir: Path) -> bytes:
    """Recompute the manifest digests the way a determined local actor with
    knowledge of the layout would (no HMAC involved)."""
    files = {name: hashlib.sha256((run_dir / name).read_bytes()).hexdigest() for name in CONTENT_FILES}
    manifest = {"schema_version": "1", "files": [
        {"path": name, "sha256": files[name], "bytes": (run_dir / name).stat().st_size}
        for name in sorted(files)
    ]}
    return (json.dumps(manifest, sort_keys=True, indent=1) + "\n").encode("utf-8")


def _reseal_with_key(run_dir: Path, seal_key: Path) -> None:
    """Recompute manifest + re-sign the run with the runner key (a local
    actor who holds the key CAN re-seal; verify must still refuse
    unsupported or legacy contexts)."""
    (run_dir / "manifest.json").write_bytes(_recompute_manifest(run_dir))
    run_fd, _chain = fs._open_anchored(run_dir)
    try:
        sealing.seal_run(run_fd, _raw_key(seal_key))
    finally:
        os.close(run_fd)


def test_new_sealed_run_binds_authenticated_execution_context(sealed_run: tuple[Path, Path]) -> None:
    run_dir, seal_key = sealed_run
    document = json.loads((run_dir / "validation.json").read_bytes())
    context = document["execution_context"]
    # the review runner is offline; the generator is the measured running code
    from slaif_gateway.services.catalog_refresh import execution_identity

    expected_tool, expected_revision = execution_identity.tool_identity()
    assert context["acquisition"] == "offline_supplied"
    assert context["generator"] == {
        "tool": expected_tool,
        "code_revision": expected_revision,
    }
    from slaif_gateway.schemas.catalog_refresh import RENDERER_VERSION

    assert context["generator_versions"] == {
        "schema_version": "1",
        "renderer_version": RENDERER_VERSION,
        "policy_version": 1,
        "extractor_version": "slaif-collector/181.1",
    }

    result = verify_run(run_dir, _raw_key(seal_key))
    assert result.valid
    assert (
        result.checks["acquisition"]
        == "replayed original mode \'offline_supplied\' (no HTTP/DNS/SQL executed during verification)"
    )
    # original (authenticated) vs current (measured now) identities: same
    # code here, but reported as distinct facts
    assert result.original_generator == {
        "tool": expected_tool,
        "code_revision": expected_revision,
    }
    assert result.current_generator is not None
    assert result.current_generator["tool"] == expected_tool
    assert "context" not in result.checks  # no refusal for a supported run


def test_context_flip_tamper_fails_hmac_authentication(sealed_run: tuple[Path, Path]) -> None:
    """Flipping the authenticated acquisition mode and re-signing digests
    WITHOUT the key must fail HMAC: the context is runner-bound, not
    locally re-derivable."""
    run_dir, seal_key = sealed_run
    victim = run_dir / "validation.json"
    original = victim.read_bytes()
    document = json.loads(original)
    document["execution_context"]["acquisition"] = (
        "live_collection"
        if document["execution_context"]["acquisition"] == "offline_supplied"
        else "offline_supplied"
    )
    victim.write_bytes((json.dumps(document, sort_keys=True, indent=1) + "\n").encode("utf-8"))
    (run_dir / "manifest.json").write_bytes(_recompute_manifest(run_dir))
    # refresh the receipt digests as a tamperer with local knowledge would
    receipt = json.loads((run_dir / "receipt.json").read_bytes())
    files = {name: hashlib.sha256((run_dir / name).read_bytes()).hexdigest() for name in CONTENT_FILES}
    manifest_bytes = (run_dir / "manifest.json").read_bytes()
    receipt["files"] = dict(sorted(files.items()))
    receipt["manifest_sha256"] = hashlib.sha256(manifest_bytes).hexdigest()
    (run_dir / "receipt.json").write_bytes(
        (json.dumps(receipt, sort_keys=True, indent=1) + "\n").encode("utf-8")
    )
    result = verify_run(run_dir, _raw_key(seal_key))
    assert not result.valid
    assert result.checks.get("digests") == "ok"
    assert result.checks.get("hmac") == "authentication failed"
    # restore
    victim.write_bytes(original)
    (run_dir / "manifest.json").write_bytes(_recompute_manifest(run_dir))
    _reseal_with_key(run_dir, seal_key)
    assert verify_run(run_dir, _raw_key(seal_key)).valid


@pytest.mark.parametrize("mutate", [
    lambda ctx: ctx.__setitem__("schema_version", "2"),
    lambda ctx: ctx["generator_versions"].__setitem__("extractor_version", "slaif-collector/999.9"),
    lambda ctx: ctx.__setitem__("bogus_field", "x"),
])
def test_resealed_unsupported_context_is_refused(
    sealed_run: tuple[Path, Path], mutate
) -> None:
    """A FORGED context with an unsupported version/shape - even fully
    re-signed with the runner key - is refused explicitly (no historical
    renderer fleet, no re-derivation)."""
    run_dir, seal_key = sealed_run
    victim = run_dir / "validation.json"
    original = victim.read_bytes()
    document = json.loads(original)
    mutate(document["execution_context"])
    victim.write_bytes((json.dumps(document, sort_keys=True, indent=1) + "\n").encode("utf-8"))
    _reseal_with_key(run_dir, seal_key)
    result = verify_run(run_dir, _raw_key(seal_key))
    assert not result.valid
    assert result.checks.get("digests") == "ok"
    assert result.checks.get("hmac") == "ok"  # authentication passed...
    assert result.checks.get("context") == "unsupported context shape or version"
    victim.write_bytes(original)
    _reseal_with_key(run_dir, seal_key)
    assert verify_run(run_dir, _raw_key(seal_key)).valid


@pytest.mark.parametrize("version", ["181.1", "999.9", "CANARY-SECRET-\x01\x02malicious"])
def test_resealed_unsupported_renderer_version_is_refused(
    sealed_run: tuple[Path, Path], version: str
) -> None:
    """A FORGED context of a renderer version this verifier cannot replay
    byte-stably is refused explicitly and distinguishably: 181.1 is the
    concrete pre-182 boundary (its sealed artifacts are not byte-stable
    under the 182 renderer); unknown future values are refused the same
    way. No historical renderer fleet, no re-derivation. The refusal
    message is fixed and never echoes the authenticated (untrusted) value
    (A1 safe-error surface)."""
    run_dir, seal_key = sealed_run
    victim = run_dir / "validation.json"
    original = victim.read_bytes()
    document = json.loads(original)
    document["execution_context"]["generator_versions"]["renderer_version"] = version
    victim.write_bytes((json.dumps(document, sort_keys=True, indent=1) + "\n").encode("utf-8"))
    _reseal_with_key(run_dir, seal_key)
    result = verify_run(run_dir, _raw_key(seal_key))
    assert not result.valid
    assert result.checks.get("digests") == "ok"
    assert result.checks.get("hmac") == "ok"  # authentication passed...
    assert result.checks.get("context") == (
        "unsupported renderer version in sealed context; "
        "re-run the review under the current CLI"
    )
    # negative canary: the forged value (including private text/control
    # characters) must not reach any error output
    if "CANARY" in version:
        assert "CANARY" not in json.dumps(result.checks, default=str)
    victim.write_bytes(original)
    _reseal_with_key(run_dir, seal_key)
    assert verify_run(run_dir, _raw_key(seal_key)).valid


def test_resealed_legacy_validation_without_context_is_refused(
    sealed_run: tuple[Path, Path]
) -> None:
    """A pre-181-i sealed run (validation.json WITHOUT the execution
    context) is refused explicitly and never re-sealed or rewritten:
    verify reports the missing legacy context and the current verifier
    identity, and the sealed bytes are left for the operator."""
    run_dir, seal_key = sealed_run
    victim = run_dir / "validation.json"
    original = victim.read_bytes()
    document = json.loads(original)
    del document["execution_context"]
    victim.write_bytes((json.dumps(document, sort_keys=True, indent=1) + "\n").encode("utf-8"))
    _reseal_with_key(run_dir, seal_key)
    result = verify_run(run_dir, _raw_key(seal_key))
    assert not result.valid
    assert result.checks.get("digests") == "ok"
    assert result.checks.get("hmac") == "ok"
    assert result.checks.get("context") == "missing (unsupported legacy validation context)"
    # the current verifier identity is still reported, the original is not
    assert result.original_generator is None
    assert result.current_generator is not None
    assert result.current_generator["tool"].startswith("slaif-gateway/")
    victim.write_bytes(original)
    _reseal_with_key(run_dir, seal_key)
    assert verify_run(run_dir, _raw_key(seal_key)).valid
