"""CLI behavior for catalog-refresh review / verify / export-baseline."""

from __future__ import annotations

import json
import shutil
import signal
import subprocess
import sys
import time
from hashlib import sha256
from pathlib import Path

import pytest
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
    # the first-install bundle creates models, so the A2 new-model
    # exposure review warning makes this READY_WITH_WARNINGS (exit 10)
    assert result.exit_code == 10, result.output
    lines = result.stdout.splitlines()
    assert lines[0] == "state: READY_WITH_WARNINGS"
    assert "reason:" in lines[1]
    assert lines[3].startswith("report: file://")
    assert lines[4].startswith("run_dir: file://")
    assert "changed: 0" in lines
    assert "warnings: 1" in lines
    assert "blockers: 0" in lines
    assert any(line.startswith("stage: offline review:") for line in lines)
    assert "review these ten files" not in result.stdout
    report = tmp_path / "runs" / "fixture-first-install-001" / "REVIEW.html"
    assert report.is_file()
    assert (tmp_path / "runs" / "fixture-first-install-001" / "receipt.json").is_file()


def test_review_refresh_with_changes_is_blocked(tmp_path: Path) -> None:
    """The fixture's changed row is an update of an existing row: the
    import gate blocks the route change, so the run is BLOCKED even
    though it is sealed/verifiable."""
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
    assert first.exit_code == 10  # RWW: new-model exposure warning
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
    assert result.exit_code == 10, result.output
    payload = json.loads(result.stdout)
    assert payload["state"] == "READY_WITH_WARNINGS"
    assert payload["run_id"] == "fixture-first-install-001"
    assert payload["report"].startswith("file://")
    assert payload["changed"] == 0
    assert "apply" in payload["stage"]


def test_verify_valid_run(tmp_path: Path) -> None:
    assert _review([str(FIXTURES / "bundle-first-install.json"), "--first-install"], tmp_path).exit_code == 10
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
    assert _review([str(FIXTURES / "bundle-first-install.json"), "--first-install"], tmp_path).exit_code == 10
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
    assert _review([str(FIXTURES / "bundle-first-install.json"), "--first-install"], tmp_path).exit_code == 10
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
    assert _review([str(FIXTURES / "bundle-first-install.json"), "--first-install"], tmp_path).exit_code == 10
    result = runner.invoke(
        app,
        ["catalog-refresh", "verify",
         "--run-dir", str(tmp_path / "runs" / "no-such-run"),
         "--seal-key", str(tmp_path / "seal.key")],
    )
    assert result.exit_code == 30
    assert "valid: no" in result.stdout


def test_verify_wrong_key_exit_30(tmp_path: Path) -> None:
    assert _review([str(FIXTURES / "bundle-first-install.json"), "--first-install"], tmp_path).exit_code == 10
    other_key = tmp_path / "other.key"
    # Create a second, different key via the CLI review in a separate root.
    assert runner.invoke(
        app,
        ["catalog-refresh", "review", str(FIXTURES / "bundle-first-install.json"),
         "--first-install",
         "--run-root", str(tmp_path / "other-runs"),
         "--seal-key", str(other_key)],
    ).exit_code == 10
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
    "Baseline consumed from a supplied document: the document DECLARES a "
    "historical SQL export at its export time; consuming the file does not "
    "verify that historical SQL execution occurred, and this review does not "
    "attest it; no SQL was executed during this review."
)
LIVE_EXPORT_SQL_NOTE = (
    "SQL was executed during this review: this review command performed the "
    "live read-only baseline export."
)


def _run_validation_json(tmp_path: Path, run_id: str) -> dict:
    return json.loads((tmp_path / "runs" / run_id / "validation.json").read_text(encoding="utf-8"))


def test_sql_capture_first_install_run(tmp_path: Path) -> None:
    result = _review([str(FIXTURES / "bundle-first-install.json"), "--first-install"], tmp_path)
    assert result.exit_code == 10, result.output  # RWW: new-model exposure warning
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
    assert result.exit_code == 10, result.output  # RWW: new-model exposure warning
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


def test_collect_preacquisition_baseline_failure_labels_path_and_publishes(
    tmp_path: Path,
) -> None:
    """181-i (I1): a collect whose baseline resolution fails BEFORE any
    acquisition must be labeled by the path actually reached. The JSON
    stage says the collection never started (no retrieval performed), the
    published minimal REVIEW.html footer agrees, acquisition seams are
    never touched, and the run is a single unsealed BLOCKED run (exit 20)."""
    import socket

    import slaif_gateway.cli.catalog_refresh as cli_mod
    import slaif_gateway.services.catalog_refresh.sources as sources_mod
    from slaif_gateway.services.catalog_refresh.errors import (
        CatalogRefreshBlockedError,
    )

    events: list[str] = []

    async def baseline_fail(*args: object, **kwargs: object) -> object:
        events.append("baseline failure before collection")
        raise CatalogRefreshBlockedError(
            "baseline_export_failed", "synthetic pre-acquisition failure"
        )

    def forbidden(*args: object, **kwargs: object) -> None:
        events.append("prohibited acquisition seam")
        raise AssertionError("acquisition was not supposed to be reached")

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(cli_mod, "export_baseline", baseline_fail)
    monkeypatch.setattr(sources_mod, "new_client", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    try:
        result = runner.invoke(
            app,
            ["catalog-refresh", "collect", "--refresh",
             "--db-url", "postgresql+asyncpg://synthetic@127.0.0.1:1/proof",
             "--providers", "openrouter",
             "--run-root", str(tmp_path / "runs"),
             "--seal-key", str(tmp_path / "seal.key"),
             "--json"],
        )
    finally:
        monkeypatch.undo()
    assert result.exit_code == 20, result.output
    summary = json.loads(result.stdout)
    assert events == ["baseline failure before collection"], events
    assert summary["state"] == "BLOCKED"
    assert summary["reason"].startswith("baseline_export_failed")
    # JSON stage: accurate not-started label, never a live-collection claim.
    assert summary["stage"].startswith("collection not started")
    assert "retrieval performed by this command" not in summary["stage"]
    assert summary["stage"] == cli_mod.STAGE_LINE_COLLECT_NOT_STARTED
    assert summary["stage"] != cli_mod.STAGE_LINE_COLLECT
    # Exactly one BLOCKED run, named for the reached failure.
    run_dirs = sorted(p.name for p in (tmp_path / "runs").iterdir())
    assert len(run_dirs) == 1
    assert run_dirs[0].startswith("blocked-baseline_export_failed-")
    run_dir = tmp_path / "runs" / run_dirs[0]
    assert not (run_dir / "receipt.json").exists()
    # JSON + HTML agreement: the published minimal report footer carries
    # the SAME reached-path stage (not the generic review scope).
    html = (run_dir / "REVIEW.html").read_text(encoding="utf-8")
    assert "not sealed" in html
    assert f"Scope: {summary['stage']}." in html
    assert "offline review: this invocation reviewed supplied bytes" not in html
    assert "retrieval performed by this command" not in html


def test_collect_failed_attempt_labels_attempted_and_publishes(tmp_path: Path) -> None:
    """181-i (I1): a collect whose retrieval ATTEMPT fails is labeled
    attempted-and-incomplete (not live, not not-started); the JSON stage
    and the published minimal footer agree, and the acquisition seam WAS
    reached (unlike the pre-acquisition case)."""
    import socket
    import types

    import slaif_gateway.cli.catalog_refresh as cli_mod
    from slaif_gateway.services.catalog_refresh.sources import SourceFetchError

    events: list[str] = []

    def fake_collect_bundle(**kwargs: object) -> object:
        events.append("collection attempt reached")
        raise SourceFetchError("collection_fetch_failed")

    def forbidden(*args: object, **kwargs: object) -> None:
        events.append("prohibited physical seam")
        raise AssertionError("no physical network in this test")

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(cli_mod.catalog_collection, "collect_bundle", fake_collect_bundle)
    monkeypatch.setattr(
        cli_mod.catalog_sources,
        "new_client",
        lambda: types.SimpleNamespace(close=lambda: None),
    )
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    try:
        result = runner.invoke(
            app,
            ["catalog-refresh", "collect", "--bootstrap",
             "--providers", "openrouter",
             "--run-root", str(tmp_path / "runs"),
             "--seal-key", str(tmp_path / "seal.key"),
             "--json"],
        )
    finally:
        monkeypatch.undo()
    assert result.exit_code == 20, result.output
    summary = json.loads(result.stdout)
    assert events == ["collection attempt reached"], events
    assert summary["reason"].startswith("collection failed: collection_fetch_failed")
    assert summary["stage"] == cli_mod.STAGE_LINE_COLLECT_INCOMPLETE
    assert summary["stage"] != cli_mod.STAGE_LINE_COLLECT
    assert "retrieval performed by this command" not in summary["stage"]
    run_dirs = sorted(p.name for p in (tmp_path / "runs").iterdir())
    assert len(run_dirs) == 1
    assert run_dirs[0].startswith("blocked-collection_fetch_failed-")
    run_dir = tmp_path / "runs" / run_dirs[0]
    assert not (run_dir / "catalog-refresh.json").exists()
    html = (run_dir / "REVIEW.html").read_text(encoding="utf-8")
    assert "not sealed" in html
    assert f"Scope: {summary['stage']}." in html
    assert "offline review: this invocation reviewed supplied bytes" not in html


def test_collect_postcollection_block_keeps_live_stage_and_publishes(
    tmp_path: Path,
) -> None:
    """181-i (I1): a COMPLETED collect that then blocks in the shared
    review tail (baseline identity mismatch) keeps the live-collection
    stage: the retrieval really was performed by this command, and the
    published blocked report footer must agree with the JSON stage."""
    import hashlib
    import types

    import slaif_gateway.cli.catalog_refresh as cli_mod
    from slaif_gateway.schemas.catalog_refresh import BaselineDocument
    from slaif_gateway.services.catalog_refresh.baseline import (
        canonical_baseline_content,
    )
    from slaif_gateway.services.catalog_refresh.bundle import load_bundle

    # A VALID baseline document whose canonical digest differs from the
    # fixture bundle's declared baseline identity.
    doc_payload = json.loads(
        (FIXTURES / "baseline-synthetic.json").read_text(encoding="utf-8")
    )
    doc_payload["fx"][0]["rate"] = "1.09"
    doc = BaselineDocument.model_validate(doc_payload)
    doc_payload["content_sha256"] = hashlib.sha256(
        canonical_baseline_content(doc)
    ).hexdigest()
    doc = BaselineDocument.model_validate(doc_payload)
    baseline_path = tmp_path / "baseline-different.json"
    baseline_path.write_text(
        json.dumps(doc.model_dump(mode="json"), sort_keys=True, indent=1) + "\n",
        encoding="utf-8",
    )

    fixture_bundle = load_bundle(
        (FIXTURES / "bundle-refresh-ready.json").read_bytes()
    )
    seen: dict[str, bool] = {}

    def fake_collect_bundle(**kwargs: object) -> object:
        seen["reached"] = True
        return fixture_bundle

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(cli_mod.catalog_collection, "collect_bundle", fake_collect_bundle)
    monkeypatch.setattr(
        cli_mod.catalog_sources,
        "new_client",
        lambda: types.SimpleNamespace(close=lambda: None),
    )
    try:
        result = runner.invoke(
            app,
            ["catalog-refresh", "collect", "--refresh",
             "--baseline-file", str(baseline_path),
             "--providers", "openrouter",
             "--run-root", str(tmp_path / "runs"),
             "--seal-key", str(tmp_path / "seal.key"),
             "--json"],
        )
    finally:
        monkeypatch.undo()
    assert result.exit_code == 20, result.output
    assert seen.get("reached") is True
    summary = json.loads(result.stdout)
    assert summary["reason"].startswith("baseline_identity_mismatch")
    assert summary["stage"] == cli_mod.STAGE_LINE_COLLECT
    run_dirs = sorted(p.name for p in (tmp_path / "runs").iterdir())
    assert len(run_dirs) == 1
    assert run_dirs[0].startswith("blocked-baseline_identity_mismatch-")
    run_dir = tmp_path / "runs" / run_dirs[0]
    # the collected canonical bytes ARE published with the blocked run
    assert (run_dir / "catalog-refresh.json").is_file()
    assert not (run_dir / "receipt.json").exists()
    html = (run_dir / "REVIEW.html").read_text(encoding="utf-8")
    assert f"Scope: {summary['stage']}." in html
    assert "live collection" in html
    assert "offline review: this invocation reviewed supplied bytes" not in html


# --- 181-h H3: standard operator watchdog over the read-only collect --------

TESTS_UNIT_DIR = Path(__file__).resolve().parent
REPO_ROOT = Path(__file__).resolve().parents[2]

# Finite test durations (NOT the documented 300 s operator default): the
# driver must survive a slow, parallel-CI startup BEFORE the watchdog
# fires, so the duration is an adequate finite startup allowance. The
# stall itself is 300 s, so a bounded return is still proven against it.
WATCHDOG_DURATION_SECONDS = 10
WATCHDOG_KILL_GRACE_SECONDS = 1
WATCHDOG_WALL_BUDGET_SECONDS = (
    WATCHDOG_DURATION_SECONDS + WATCHDOG_KILL_GRACE_SECONDS + 15
)

_WATCHDOG_DRIVER_TEMPLATE = """
import signal
import sys
import time
from pathlib import Path

sys.path.insert(0, {app_root!r})
sys.path.insert(0, {tests_unit!r})

import pytest

import test_catalog_refresh_collection as tc

if {ignore_term!r}:
    signal.signal(signal.SIGTERM, signal.SIG_IGN)

world = tc.World()
original = world.handler


def stalled(request):
    # Owned marker: proves the REAL collect reached the intended
    # acquisition stall (not a timeout during startup).
    Path(sys.argv[3]).write_text("stall reached", encoding="utf-8")
    time.sleep(300.0)
    return original(request)


world.handler = stalled

monkey = pytest.MonkeyPatch()
tc._cli_collect(
    monkey,
    world,
    "catalog-refresh",
    "collect",
    "--bootstrap",
    "--providers",
    "openrouter",
    "--run-root",
    sys.argv[1],
    "--seal-key",
    sys.argv[2],
)
"""


def _run_watchdog_case(tmp_path: Path, *, ignore_term: bool) -> tuple[int, float, Path]:
    """Drive the REAL collect (mocked HTTP/DNS, stalled first request)
    under the standard OS watchdog with adequate finite test durations
    (startup allowance; the stall is 300 s, so a bounded return is still
    proven against it). The standard process-group watchdog semantics are
    kept: no --foreground, no bespoke supervisor."""
    timeout_bin = shutil.which("timeout")
    assert timeout_bin is not None, "the standard OS timeout utility is required"
    driver = tmp_path / "watchdog_driver.py"
    driver.write_text(
        _WATCHDOG_DRIVER_TEMPLATE.format(
            app_root=str(REPO_ROOT / "app"),
            tests_unit=str(TESTS_UNIT_DIR),
            ignore_term=ignore_term,
        ),
        encoding="utf-8",
    )
    run_root = tmp_path / "runs"
    key = tmp_path / "seal.key"
    marker = tmp_path / "stall-reached"
    started = time.monotonic()
    proc = subprocess.run(
        [
            timeout_bin,
            f"--kill-after={WATCHDOG_KILL_GRACE_SECONDS}",
            str(WATCHDOG_DURATION_SECONDS),
            sys.executable,
            str(driver),
            str(run_root),
            str(key),
            str(marker),
        ],
        capture_output=True,
        timeout=WATCHDOG_WALL_BUDGET_SECONDS + 30,
    )
    wall = time.monotonic() - started
    return proc.returncode, wall, marker


def test_watchdog_terminates_stalled_collect_before_any_publication(
    tmp_path: Path,
) -> None:
    # 181-h H3 (watchdog proof): the documented watchdog prefix (standard
    # OS ``timeout --kill-after=<grace> <duration>``) around the REAL
    # collect command - mocked HTTP/DNS through the existing World
    # fixture, first request stalled - returns bounded and NON-SUCCESS
    # (genuine timeout representations: 124/137, or the raw -SIGTERM/
    # -SIGKILL where a standard process-group ``timeout`` signals its own
    # group on the runner), publishes NO new run (the collect writes
    # nothing during the fetch phase; publication is one atomic rename at
    # finalization only), and leaves an EARLIER published run in the same
    # run root byte-identical. The owned marker (written by the stalled
    # handler) proves the stall was REACHED - not a startup timeout. No
    # private service; adequate finite test duration only.
    import test_catalog_refresh_collection as tc

    world = tc.World()
    run_root = tmp_path / "runs"
    key = tmp_path / "seal.key"

    # Pre-publish a normal READY run in the SAME run root (in-process).
    mp = pytest.MonkeyPatch()
    try:
        base = tc._cli_collect(
            mp,
            world,
            "catalog-refresh",
            "collect",
            "--bootstrap",
            "--providers",
            "openrouter",
            "--run-root",
            str(run_root),
            "--seal-key",
            str(key),
            "--json",
        )
    finally:
        mp.undo()
    assert base.exit_code == 10, base.output  # RWW: new-model exposure warning
    before_dirs = sorted(p.name for p in run_root.iterdir())
    assert len(before_dirs) == 1
    before_bytes = {
        p.relative_to(run_root).as_posix(): sha256(p.read_bytes()).hexdigest()
        for p in sorted(run_root.rglob("*"))
        if p.is_file()
    }

    rc, wall, marker = _run_watchdog_case(tmp_path, ignore_term=False)
    assert rc in (124, 137, -signal.SIGTERM, -signal.SIGKILL), (
        f"watchdog status must be a genuine non-success timeout "
        f"representation, got {rc}"
    )
    assert wall < WATCHDOG_WALL_BUDGET_SECONDS, (
        f"watchdog return unbounded: {wall}"
    )
    assert marker.is_file(), (
        "the collect must have reached the intended acquisition stall "
        "(owned marker written by the mocked stalled handler)"
    )

    after_dirs = sorted(p.name for p in run_root.iterdir())
    assert after_dirs == before_dirs, (
        "interrupted collect must not publish a new run"
    )
    after_bytes = {
        p.relative_to(run_root).as_posix(): sha256(p.read_bytes()).hexdigest()
        for p in sorted(run_root.rglob("*"))
        if p.is_file()
    }
    assert after_bytes == before_bytes, (
        "the earlier published run must be byte-identical"
    )


def test_watchdog_kill_after_terminates_term_ignoring_collect(
    tmp_path: Path,
) -> None:
    # 181-h H3 (TERM-ignoring owned negative): a collect that ignores
    # SIGTERM must be KILLed after the KILL grace and still exit
    # non-success - the genuine SIGKILL representation is 137 (the shell
    # convention) or the raw -signal.SIGKILL where a standard
    # process-group ``timeout`` surfaces the signal itself - publishing
    # nothing: no fresh READY, no staged or partial artifact, no
    # overwrite of an older review. The marker proves the stall was
    # reached before the KILL.
    rc, wall, marker = _run_watchdog_case(tmp_path, ignore_term=True)
    assert rc in (137, -signal.SIGKILL), (
        f"TERM-ignoring collect must be KILLed after the grace: {rc}"
    )
    assert wall < WATCHDOG_WALL_BUDGET_SECONDS, (
        f"watchdog return unbounded: {wall}"
    )
    assert marker.is_file(), (
        "the collect must have reached the intended acquisition stall "
        "(owned marker written by the mocked stalled handler)"
    )
    run_root = tmp_path / "runs"
    leftovers = (
        sorted(p.name for p in run_root.iterdir()) if run_root.exists() else []
    )
    assert leftovers == [], (
        "an interrupted collect publishes nothing: "
        f"leftovers={leftovers}"
    )


# --- 181-i (I1/I2/I3): runner-selected context through the real CLI -----------


def test_cli_review_of_intact_collected_bundle_is_offline_with_measured_generator(
    tmp_path: Path, monkeypatch
) -> None:
    """Mirror of the strategic probe: an INTACT mocked-collected bundle is
    reviewed through the actual CLI with every network escape refused.
    The reviewing invocation is OFFLINE: the scope is supplied_collection
    (the recorded identity is historical provenance, preserved), the
    generating generator is MEASURED from the running code (never the
    bundle's declared identity), and verify replays the authenticated
    context, reporting original vs current generator identity."""
    import socket as _socket

    import test_catalog_refresh_collection as _collect_tests

    def _refuse_dns(*args, **kwargs):
        raise AssertionError("CLI review reached a default DNS resolver (live network escape)")

    def _refuse_connect(*args, **kwargs):
        raise AssertionError("CLI review attempted a real socket connection (live network escape)")

    def _refuse_new_client(*args, **kwargs):
        raise AssertionError("CLI review constructed a live source client")

    monkeypatch.setattr(_socket, "getaddrinfo", _refuse_dns)
    monkeypatch.setattr(_socket.socket, "connect", _refuse_connect)
    monkeypatch.setattr(_socket.socket, "connect_ex", _refuse_connect)
    from slaif_gateway.services.catalog_refresh import sources as _sources

    monkeypatch.setattr(_sources, "new_client", _refuse_new_client)

    # 1) actual (mocked-transport) collection, then the canonical bundle bytes
    collected = _collect_tests._collect(_collect_tests.World(), providers=("openrouter",))
    assert collected.collection is not None
    from slaif_gateway.services.catalog_refresh.bundle import canonical_bundle_bytes

    bundle_path = tmp_path / "collected.json"
    bundle_path.write_bytes(canonical_bundle_bytes(collected))

    # 2) real CLI review (offline by the runner's path selection)
    result = runner.invoke(
        app,
        [
            "catalog-refresh", "review",
            str(bundle_path),
            "--first-install",
            "--run-root", str(tmp_path / "runs"),
            "--seal-key", str(tmp_path / "seal.key"),
        ],
    )
    assert result.exit_code == 10, result.output  # RWW: new-model exposure warning
    assert result.stdout.splitlines()[0] == "state: READY_WITH_WARNINGS"
    assert any(line.startswith("stage: offline review:") for line in result.stdout.splitlines())
    assert "performed no live retrieval" in result.stdout

    run_dir = tmp_path / "runs" / collected.run_id
    validation = json.loads((run_dir / "validation.json").read_bytes())
    evidence = validation["source_evidence"]
    assert evidence["scope"] == "supplied_collection"
    # provenance preserved (dates/retrievals/inventory/digests), never erased
    assert evidence["collection"]["tool"] == collected.collection.tool
    assert evidence["collection"]["code_revision"] == collected.collection.code_revision
    assert evidence["collection"]["retrievals_total"] == len(collected.collection.retrievals)
    assert evidence["collection"]["started_at"] == collected.collection.started_at.isoformat()

    # the generating generator is the MEASURED running code, not the
    # bundle's declared (historical) collection identity
    from slaif_gateway.services.catalog_refresh import execution_identity as _ei

    expected_tool, expected_revision = _ei.tool_identity()
    context = validation["execution_context"]
    assert context["acquisition"] == "offline_supplied"
    assert context["generator"] == {"tool": expected_tool, "code_revision": expected_revision}
    assert context["generator"]["tool"] != collected.collection.tool or (
        expected_tool == collected.collection.tool
    )
    assert context["generator_versions"] == _ei.generator_versions()

    # 3) verify replays the authenticated context and reports both identities
    verify = runner.invoke(
        app,
        [
            "catalog-refresh", "verify",
            "--run-dir", str(run_dir),
            "--seal-key", str(tmp_path / "seal.key"),
        ],
    )
    assert verify.exit_code == 0, verify.output
    assert "valid: yes" in verify.stdout
    assert (
        "acquisition: replayed original mode 'offline_supplied' "
        "(no HTTP/DNS/SQL executed during verification)"
    ) in verify.stdout
    assert (
        f"original generator: tool {expected_tool} · code_revision "
        f"{expected_revision} (authenticated in the sealed validation.json)"
    ) in verify.stdout
    assert "current generator: tool" in verify.stdout
    assert "(measured at verification time)" in verify.stdout

    verify_json = runner.invoke(
        app,
        [
            "catalog-refresh", "verify",
            "--run-dir", str(run_dir),
            "--seal-key", str(tmp_path / "seal.key"),
            "--json",
        ],
    )
    assert verify_json.exit_code == 0, verify_json.output
    payload = json.loads(verify_json.stdout)
    assert payload["valid"] is True
    assert payload["original_generator"] == {
        "tool": expected_tool,
        "code_revision": expected_revision,
    }
    assert payload["current_generator"]["tool"] == expected_tool
    assert payload["checks"]["acquisition"].startswith("replayed original mode")
