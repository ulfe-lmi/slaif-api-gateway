"""CLI behavior for catalog-refresh review / verify / export-baseline."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

import test_catalog_refresh_source_evidence as _evidence_tests

from slaif_gateway.cli.main import app

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "catalog_refresh"
runner = CliRunner()


def _review(args: list[str], tmp_path: Path):
    return runner.invoke(
        app,
        ["catalog-refresh", "review", *args,
         "--run-root", str(tmp_path / "runs"),
         "--seal-key", str(tmp_path / "seal.key")],
    )


def test_review_first_install_is_ready(tmp_path: Path) -> None:
    result = _review([str(FIXTURES / "bundle-first-install.json"), "--first-install"], tmp_path)
    assert result.exit_code == 0, result.output
    lines = result.stdout.splitlines()
    assert lines[0] == "state: READY"
    assert "reason:" in lines[1]
    assert lines[3].startswith("report: file://")
    assert lines[4].startswith("run_dir: file://")
    assert "changed: 0" in lines
    assert "warnings: 0" in lines
    assert "blockers: 0" in lines
    assert any(line.startswith("stage: offline review:") for line in lines)
    assert "review these ten files" not in result.stdout
    report = tmp_path / "runs" / "fixture-first-install-001" / "REVIEW.html"
    assert report.is_file()
    assert (tmp_path / "runs" / "fixture-first-install-001" / "receipt.json").is_file()


def test_review_refresh_with_changes_is_blocked(tmp_path: Path) -> None:
    """The fixture's changed row is an update: no apply operation exists in
    this version, so the run is BLOCKED even though it is sealed/verifiable."""
    result = _review(
        [str(FIXTURES / "bundle-refresh-ready.json"),
         "--baseline-file", str(FIXTURES / "baseline-synthetic.json")],
        tmp_path,
    )
    assert result.exit_code == 20, result.output
    assert result.stdout.splitlines()[0] == "state: BLOCKED"
    assert "changed: 1" in result.stdout
    verify = runner.invoke(
        app,
        ["catalog-refresh", "verify",
         "--run-dir", str(tmp_path / "runs" / "fixture-refresh-ready-001"),
         "--seal-key", str(tmp_path / "seal.key")],
    )
    assert verify.exit_code == 0, verify.output  # verify checks seal integrity
    assert "valid: yes" in verify.stdout
    assert "state: BLOCKED" in verify.stdout  # the review state is BLOCKED


def test_review_ready_with_warnings_exit_10(tmp_path: Path) -> None:
    """Aged sources (25h) are REVIEW; with no mutations the state is
    READY_WITH_WARNINGS, not BLOCKED."""
    from datetime import UTC, datetime, timedelta

    payload = json.loads((FIXTURES / "bundle-refresh-ready.json").read_text())
    payload["run_id"] = "test-cli-warnings-001"
    for item in payload["pricing"]:
        if item["model"] == "synthetic/updated-v1":
            for dimension in item["dimensions"]:
                if dimension["name"] == "input":
                    dimension["value"] = "1"  # identical to baseline
    # The evidence must carry the proposed price (the fixture snapshot pins
    # 1.2/4 EUR for updated-v1; the baseline carries 1/4).
    _evidence_tests.set_openrouter_evidence(
        payload, {**_evidence_tests.DEFAULT_PRICES, "synthetic/updated-v1": ("1", "4")}
    )
    for route in payload["routes"]:
        if route["requested_model"] == "synthetic/updated-v1":
            route["priority"] = 100  # identical to baseline
    retrieved = (datetime(2026, 9, 21, 12, 0, 0, tzinfo=UTC) - timedelta(hours=25)).isoformat()
    for source in payload["sources"]:
        source["retrieved_at"] = retrieved
    bundle_path = tmp_path / "bundle-warnings.json"
    bundle_path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    result = _review([str(bundle_path), "--baseline-file", str(FIXTURES / "baseline-synthetic.json")], tmp_path)
    assert result.exit_code == 10, result.output
    assert result.stdout.splitlines()[0] == "state: READY_WITH_WARNINGS"


def test_review_blocked_exit_20(tmp_path: Path) -> None:
    result = _review(
        [str(FIXTURES / "bundle-blocked.json"),
         "--baseline-file", str(FIXTURES / "baseline-synthetic.json")],
        tmp_path,
    )
    assert result.exit_code == 20, result.output
    assert result.stdout.splitlines()[0] == "state: BLOCKED"
    assert "currency_inconsistency" in result.stdout
    # The blocked run is still sealed and verifiable.
    verify = runner.invoke(
        app,
        ["catalog-refresh", "verify",
         "--run-dir", str(tmp_path / "runs" / "fixture-refresh-blocked-001"),
         "--seal-key", str(tmp_path / "seal.key")],
    )
    assert verify.exit_code == 0, verify.output
    assert "state: BLOCKED" in verify.stdout


def test_review_truncated_source_is_not_disappeared(tmp_path: Path) -> None:
    result = _review(
        [str(FIXTURES / "bundle-truncated.json"),
         "--baseline-file", str(FIXTURES / "baseline-synthetic.json")],
        tmp_path,
    )
    assert result.exit_code == 20, result.output
    validation = json.loads(
        (tmp_path / "runs" / "fixture-truncated-001" / "validation.json").read_text()
    )
    dispositions = {d["model"]: d["disposition"] for d in validation["dispositions"]}
    assert dispositions["synthetic/gone-v1"] == "BLOCKED"
    assert "DISAPPEARED" not in dispositions.values()
    codes = {w["code"] for w in validation["warnings"]}
    assert "explicitly_selected_not_refetched" in codes


def test_review_invalid_bundle_publics_minimal_blocked_run(tmp_path: Path) -> None:
    result = _review(
        [str(FIXTURES / "bundle-duplicate-key.json"),
         "--baseline-file", str(FIXTURES / "baseline-synthetic.json")],
        tmp_path,
    )
    assert result.exit_code == 65, result.output
    assert "state: BLOCKED" in result.stdout
    assert "bundle invalid: bundle_invalid_json" in result.stdout
    run_dirs = sorted(p.name for p in (tmp_path / "runs").iterdir())
    assert len(run_dirs) == 1
    assert run_dirs[0].startswith("blocked-invalid-")
    run_dir = tmp_path / "runs" / run_dirs[0]
    html = (run_dir / "REVIEW.html").read_text()
    assert "not sealed" in html
    assert not (run_dir / "receipt.json").exists()
    # The raw bundle text must not be echoed into the report.
    assert "fixture-dup-key-2" not in html


def test_review_missing_bundle_file_is_data_error(tmp_path: Path) -> None:
    result = _review([str(tmp_path / "nope.json"), "--first-install"], tmp_path)
    assert result.exit_code == 65
    assert "not readable" in result.stderr


def test_review_missing_baseline_file_is_data_error(tmp_path: Path) -> None:
    result = _review(
        [str(FIXTURES / "bundle-refresh-ready.json"), "--baseline-file", str(tmp_path / "absent.json")],
        tmp_path,
    )
    assert result.exit_code == 65
    assert "not readable" in result.stderr


def test_review_invalid_baseline_file_is_data_error(tmp_path: Path) -> None:
    bad = tmp_path / "bad-baseline.json"
    bad.write_bytes(b"not json at all")
    result = _review(
        [str(FIXTURES / "bundle-refresh-ready.json"), "--baseline-file", str(bad)],
        tmp_path,
    )
    assert result.exit_code == 65
    assert "baseline file invalid" in result.stderr


def test_refresh_bundle_requires_declared_mode_sources(tmp_path: Path) -> None:
    # exported_file bundle with a live DB source requested
    result = _review(
        [str(FIXTURES / "bundle-refresh-ready.json"), "--db-url", "postgresql+asyncpg://u:p@127.0.0.1:59999/x"],
        tmp_path,
    )
    assert result.exit_code == 2  # usage error: mode mismatch
    # first-install bundle with a baseline file requested
    result = _review(
        [str(FIXTURES / "bundle-first-install.json"), "--baseline-file", str(FIXTURES / "baseline-synthetic.json")],
        tmp_path,
    )
    assert result.exit_code == 2
    # contradictory flags
    result = _review(
        [str(FIXTURES / "bundle-first-install.json"), "--first-install",
         "--baseline-file", str(FIXTURES / "baseline-synthetic.json")],
        tmp_path,
    )
    assert result.exit_code == 2


def test_baseline_identity_mismatch_blocks(tmp_path: Path) -> None:
    payload = json.loads((FIXTURES / "bundle-refresh-ready.json").read_text())
    payload["baseline"]["content_sha256"] = "f" * 64  # wrong digest
    bundle_path = tmp_path / "bundle-wrong-digest.json"
    bundle_path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    result = _review([str(bundle_path), "--baseline-file", str(FIXTURES / "baseline-synthetic.json")], tmp_path)
    assert result.exit_code == 20, result.output
    assert "baseline_identity_mismatch" in result.stdout
    run_dirs = sorted(p.name for p in (tmp_path / "runs").iterdir())
    assert any(name.startswith("blocked-baseline_identity_mismatch-") for name in run_dirs)

    payload = json.loads((FIXTURES / "bundle-refresh-ready.json").read_text())
    payload["baseline"]["target_database"] = "some-other-database"
    bundle_path = tmp_path / "bundle-wrong-target.json"
    bundle_path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    result = _review([str(bundle_path), "--baseline-file", str(FIXTURES / "baseline-synthetic.json")], tmp_path)
    assert result.exit_code == 20, result.output
    assert "baseline_target_mismatch" in result.stdout


def test_stale_baseline_with_same_shape_is_rejected(tmp_path: Path) -> None:
    """A baseline whose rows changed but digest was not recomputed is rejected."""
    baseline = json.loads((FIXTURES / "baseline-synthetic.json").read_text())
    baseline["pricing"][0]["input_price_per_1m"] = "99.9"  # rows changed, digest stale
    stale = tmp_path / "stale-baseline.json"
    stale.write_text(json.dumps(baseline, sort_keys=True), encoding="utf-8")
    result = _review(
        [str(FIXTURES / "bundle-refresh-ready.json"), "--baseline-file", str(stale)],
        tmp_path,
    )
    assert result.exit_code == 65, result.output
    assert "baseline file invalid: baseline_digest_mismatch" in result.stderr
    assert not (tmp_path / "runs").exists()  # no run is published for unreadable input


def test_run_directory_is_never_overwritten(tmp_path: Path) -> None:
    args = [str(FIXTURES / "bundle-first-install.json"), "--first-install"]
    first = _review(args, tmp_path)
    assert first.exit_code == 0
    second = _review(args, tmp_path)
    assert second.exit_code == 65
    assert "already exists" in second.stderr


def test_seal_key_must_be_outside_run_tree(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        ["catalog-refresh", "review", str(FIXTURES / "bundle-first-install.json"),
         "--first-install",
         "--run-root", str(tmp_path / "runs"),
         "--seal-key", str(tmp_path / "runs" / "embedded.key")],
    )
    assert result.exit_code == 2


def test_review_json_summary(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        ["catalog-refresh", "review", str(FIXTURES / "bundle-first-install.json"),
         "--first-install",
         "--run-root", str(tmp_path / "runs"),
         "--seal-key", str(tmp_path / "seal.key"),
         "--json"],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["state"] == "READY"
    assert payload["run_id"] == "fixture-first-install-001"
    assert payload["report"].startswith("file://")
    assert payload["changed"] == 0
    assert "apply" in payload["stage"]


def test_verify_valid_run(tmp_path: Path) -> None:
    assert _review([str(FIXTURES / "bundle-first-install.json"), "--first-install"], tmp_path).exit_code == 0
    result = runner.invoke(
        app,
        ["catalog-refresh", "verify",
         "--run-dir", str(tmp_path / "runs" / "fixture-first-install-001"),
         "--seal-key", str(tmp_path / "seal.key")],
    )
    assert result.exit_code == 0, result.output
    assert "valid: yes" in result.stdout
    for check in ("digests: ok", "hmac: ok", "artifacts: ok", "validation: ok", "report: ok", "correspondence: ok"):
        assert check in result.stdout


def test_verify_tampered_run_exit_30(tmp_path: Path) -> None:
    assert _review([str(FIXTURES / "bundle-first-install.json"), "--first-install"], tmp_path).exit_code == 0
    victim = tmp_path / "runs" / "fixture-first-install-001" / "REVIEW.html"
    victim.write_bytes(victim.read_bytes() + b"tampered")
    result = runner.invoke(
        app,
        ["catalog-refresh", "verify",
         "--run-dir", str(tmp_path / "runs" / "fixture-first-install-001"),
         "--seal-key", str(tmp_path / "seal.key")],
    )
    assert result.exit_code == 30
    assert "valid: no" in result.stdout


def test_verify_missing_key_is_data_error(tmp_path: Path) -> None:
    assert _review([str(FIXTURES / "bundle-first-install.json"), "--first-install"], tmp_path).exit_code == 0
    result = runner.invoke(
        app,
        ["catalog-refresh", "verify",
         "--run-dir", str(tmp_path / "runs" / "fixture-first-install-001"),
         "--seal-key", str(tmp_path / "absent.key")],
    )
    assert result.exit_code == 65
    assert "does not exist" in result.stderr
    assert not (tmp_path / "absent.key").exists()  # verify never creates keys


def test_verify_missing_run_dir_exit_30(tmp_path: Path) -> None:
    assert _review([str(FIXTURES / "bundle-first-install.json"), "--first-install"], tmp_path).exit_code == 0
    result = runner.invoke(
        app,
        ["catalog-refresh", "verify",
         "--run-dir", str(tmp_path / "runs" / "no-such-run"),
         "--seal-key", str(tmp_path / "seal.key")],
    )
    assert result.exit_code == 30
    assert "valid: no" in result.stdout


def test_verify_wrong_key_exit_30(tmp_path: Path) -> None:
    assert _review([str(FIXTURES / "bundle-first-install.json"), "--first-install"], tmp_path).exit_code == 0
    other_key = tmp_path / "other.key"
    # Create a second, different key via the CLI review in a separate root.
    assert runner.invoke(
        app,
        ["catalog-refresh", "review", str(FIXTURES / "bundle-first-install.json"),
         "--first-install",
         "--run-root", str(tmp_path / "other-runs"),
         "--seal-key", str(other_key)],
    ).exit_code == 0
    result = runner.invoke(
        app,
        ["catalog-refresh", "verify",
         "--run-dir", str(tmp_path / "runs" / "fixture-first-install-001"),
         "--seal-key", str(other_key)],
    )
    assert result.exit_code == 30
    assert "hmac: authentication failed" in result.stdout


def test_export_baseline_without_database_is_data_error(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    out = tmp_path / "baseline.json"
    result = runner.invoke(app, ["catalog-refresh", "export-baseline", "--out", str(out)])
    assert result.exit_code == 65
    assert not out.exists()


def test_export_baseline_refuses_existing_output(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    out = tmp_path / "baseline.json"
    out.write_bytes(b"{}")
    result = runner.invoke(app, ["catalog-refresh", "export-baseline", "--out", str(out)])
    assert result.exit_code == 65
    assert out.read_bytes() == b"{}"

def test_review_failure_leaves_no_partial_run_at_final_path(tmp_path: Path, monkeypatch) -> None:
    """A publish failure must not leave an unsealed, complete-looking run."""
    import slaif_gateway.cli.catalog_refresh as cr
    from slaif_gateway.services.catalog_refresh.errors import CatalogRefreshSealError

    def boom(_run_dir, _key):
        raise CatalogRefreshSealError("simulated seal failure")

    monkeypatch.setattr(cr, "seal_run", boom)
    result = _review(
        [str(FIXTURES / "bundle-first-install.json"), "--first-install"], tmp_path
    )
    assert result.exit_code == 65, result.output
    run_root = tmp_path / "runs"
    assert not (run_root / "fixture-first-install-001").exists()
    leftovers = sorted(p.name for p in run_root.iterdir()) if run_root.exists() else []
    assert leftovers == [], f"staging leftovers: {leftovers}"


# --- 180-e E5: truthful SQL evidence (capture paths) -------------------------

FIRST_INSTALL_SQL_NOTE = (
    "Explicit first install: no database was read and no baseline document "
    "exists; no SQL was executed during this review."
)
DOCUMENT_SQL_NOTE = (
    "Baseline consumed from a supplied document: SQL was executed historically "
    "at that document's export time (declared capture metadata, not re-attested "
    "by this review); no SQL was executed during this review."
)
LIVE_EXPORT_SQL_NOTE = (
    "SQL was executed during this review: this review command performed the "
    "live read-only baseline export."
)


def _run_validation_json(tmp_path: Path, run_id: str) -> dict:
    return json.loads((tmp_path / "runs" / run_id / "validation.json").read_text(encoding="utf-8"))


def test_sql_capture_first_install_run(tmp_path: Path) -> None:
    result = _review([str(FIXTURES / "bundle-first-install.json"), "--first-install"], tmp_path)
    assert result.exit_code == 0, result.output
    validation = _run_validation_json(tmp_path, "fixture-first-install-001")
    sql_checks = validation["sql_checks"]
    assert sql_checks["capture"] == "first_install"
    assert sql_checks["sql_executed_during_review"] is False
    assert sql_checks["checked"] is False
    assert sql_checks["note"] == FIRST_INSTALL_SQL_NOTE
    html = (tmp_path / "runs" / "fixture-first-install-001" / "REVIEW.html").read_text(encoding="utf-8")
    assert "Capture path (this execution)" in html
    assert "first_install" in html
    # the first-install report must never claim a live export
    assert "live read-only baseline export" not in html


def test_sql_capture_document_run(tmp_path: Path) -> None:
    result = _review(
        [str(FIXTURES / "bundle-refresh-ready.json"),
         "--baseline-file", str(FIXTURES / "baseline-synthetic.json")],
        tmp_path,
    )
    assert result.exit_code == 20, result.output  # changed row: BLOCKED, but sealed
    validation = _run_validation_json(tmp_path, "fixture-refresh-ready-001")
    sql_checks = validation["sql_checks"]
    assert sql_checks["capture"] == "document"
    assert sql_checks["sql_executed_during_review"] is False
    assert sql_checks["checked"] is True
    assert sql_checks["note"] == DOCUMENT_SQL_NOTE
    html = (tmp_path / "runs" / "fixture-refresh-ready-001" / "REVIEW.html").read_text(encoding="utf-8")
    assert "Capture path (this execution)" in html
    assert "live read-only baseline export" not in html


def test_falsified_sql_capture_claims_are_blocked(tmp_path: Path) -> None:
    """A caller cannot claim live SQL for a document path, cannot pass an
    unknown capture, and cannot skip the baseline on a refresh mode."""
    import pytest

    from slaif_gateway.schemas.catalog_refresh import BaselineDocument
    from slaif_gateway.services.catalog_refresh.baseline import load_baseline
    from slaif_gateway.services.catalog_refresh.bundle import load_bundle
    from slaif_gateway.services.catalog_refresh.errors import CatalogRefreshBlockedError
    from slaif_gateway.services.catalog_refresh.policy import policy_from_document
    from slaif_gateway.services.catalog_refresh.validation import (
        sql_capture_for_mode,
        validate_against_baseline_document,
    )

    bundle = load_bundle((FIXTURES / "bundle-refresh-ready.json").read_bytes())
    baseline: BaselineDocument = load_baseline(
        (FIXTURES / "baseline-synthetic.json").read_bytes()
    )
    policy = policy_from_document(bundle.policy)
    assert sql_capture_for_mode(bundle.baseline.mode) == "document"

    # (a) claiming a live export for a supplied document
    with pytest.raises(CatalogRefreshBlockedError) as excinfo:
        validate_against_baseline_document(bundle, baseline, policy, sql_capture="live_export")
    assert excinfo.value.code == "sql_capture_mismatch"
    # (b) an unknown capture
    with pytest.raises(CatalogRefreshBlockedError) as excinfo:
        validate_against_baseline_document(bundle, baseline, policy, sql_capture="live-export")
    assert excinfo.value.code == "sql_capture_invalid"
    # (c) a refresh mode without any baseline document
    with pytest.raises(CatalogRefreshBlockedError) as excinfo:
        validate_against_baseline_document(bundle, None, policy, sql_capture="document")
    assert excinfo.value.code == "baseline_mode_mismatch"
    # (d) the consistent path works
    report, _artifacts = validate_against_baseline_document(
        bundle, baseline, policy, sql_capture="document"
    )
    assert report.sql_checks["capture"] == "document"


def test_verify_replay_records_no_sql_executed(tmp_path: Path) -> None:
    result = _review([str(FIXTURES / "bundle-first-install.json"), "--first-install"], tmp_path)
    assert result.exit_code == 0, result.output
    verify = runner.invoke(
        app,
        ["catalog-refresh", "verify",
         "--run-dir", str(tmp_path / "runs" / "fixture-first-install-001"),
         "--seal-key", str(tmp_path / "seal.key")],
    )
    assert verify.exit_code == 0, verify.output
    assert "valid: yes" in verify.stdout
    assert "sql_evidence: replayed from sealed bytes (no SQL executed during verification)" in verify.stdout


def test_db_snapshot_outage_publishes_minimal_blocked_run(tmp_path: Path) -> None:
    """E5: a db_snapshot bundle whose live export fails publishes a minimal
    BLOCKED run (exit 20) — it must never fall back to an empty first
    install or claim live SQL it did not perform."""
    payload = json.loads((FIXTURES / "bundle-refresh-ready.json").read_text())
    payload["run_id"] = "test-cli-db-outage-001"
    payload["baseline"]["mode"] = "db_snapshot"
    bundle_path = tmp_path / "bundle.json"
    bundle_path.write_text(json.dumps(payload, sort_keys=True, indent=1) + "\n", encoding="utf-8")

    result = runner.invoke(
        app,
        ["catalog-refresh", "review", str(bundle_path),
         "--db-url", "postgresql+asyncpg://ubuntu@127.0.0.1:59999/unreachable",
         "--run-root", str(tmp_path / "runs"),
         "--seal-key", str(tmp_path / "seal.key")],
    )
    assert result.exit_code == 20, result.output
    assert result.stdout.splitlines()[0] == "state: BLOCKED"
    run_dirs = sorted(p.name for p in (tmp_path / "runs").iterdir())
    assert len(run_dirs) == 1
    assert run_dirs[0].startswith("blocked-baseline_export_failed-")
    validation = json.loads(
        (tmp_path / "runs" / run_dirs[0] / "validation.json").read_text(encoding="utf-8")
    )
    assert validation["state"] == "BLOCKED"
    assert validation["code"] == "baseline_export_failed"
    # the minimal run is a real blocked review, not an empty bootstrap
    assert "first_install" not in json.dumps(validation)
    assert "receipt.json" not in (tmp_path / "runs" / run_dirs[0]).joinpath("nope").name
    assert not (tmp_path / "runs" / run_dirs[0] / "receipt.json").exists()
