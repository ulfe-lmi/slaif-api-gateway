"""Unit tests for the 223 demo file-backed snapshot worker (stage 223).

No database, network or provider is involved: the typed per-kind display
sanitizers, the anchored capture boundary, the owned ``files/`` write
phase, the independent read-only verifier and the bounded job runner are
exercised against temporary file trees and in-memory documents. The real
PostgreSQL 16 source+target chain (221 snapshot -> 222 sanitize -> 223
files) is covered by
tests/integration/test_demo_snapshot_files_postgres.py.
"""

from __future__ import annotations

import json
import os
import re
import time
import uuid
from pathlib import Path

import pytest

from slaif_gateway.config import Settings
from slaif_gateway.services import demo_snapshot as ds
from slaif_gateway.services import demo_snapshot_files as dsf
from slaif_gateway.services.catalog_refresh import filesystem as catfs
from slaif_gateway.schemas.catalog_refresh import (
    EXTRACTOR_ID as _EXEC_EXTRACTOR_ID,
    POLICY_VERSION as _EXEC_POLICY_VERSION,
    RENDERER_VERSION as _EXEC_RENDERER_VERSION,
    SCHEMA_VERSION as _EXEC_SCHEMA_VERSION,
)

CANARY = "CANARY223a"


def _settings(**overrides) -> Settings:
    base = dict(
        DEMO_SNAPSHOT_ENABLED=True,
        DEMO_SNAPSHOT_SOURCE_HOST="127.0.0.1",
        DEMO_SNAPSHOT_SOURCE_PORT=5555,
        DEMO_SNAPSHOT_SOURCE_DATABASE="slaif_src",
        DEMO_SNAPSHOT_SOURCE_USER="snap_reader",
        DEMO_SNAPSHOT_TARGET_HOST="127.0.0.1",
        DEMO_SNAPSHOT_TARGET_PORT=5556,
        DEMO_SNAPSHOT_TARGET_USER="snap_target",
        DEMO_SNAPSHOT_PGPASSFILE=str(Path("/tmp/never") / "pgpass"),
        DEMO_SNAPSHOT_CUSTODY_DIR=str(Path("/tmp/never") / "custody"),
        DEMO_SNAPSHOT_MAX_EXPORT_BYTES=64 * 1024 * 1024,
        DEMO_SNAPSHOT_MAX_ELAPSED_SECONDS=300,
        DEMO_SNAPSHOT_RETENTION_SECONDS=86400,
        DEMO_SNAPSHOT_MAX_COPIES=4,
    )
    base.update(overrides)
    return Settings(**base)


@pytest.fixture()
def umask_022(monkeypatch):
    previous = os.umask(0o022)
    yield
    os.umask(previous)


def _config(
    tmp_path: Path,
    *,
    custody: Path | None = None,
    catalog_root: Path | None = None,
    catalog_seal_key: Path | None = None,
    branding_dir: Path | None = None,
    completion_profile_dir: Path | None = None,
    upstream_llm_profiles_file: Path | None = None,
    max_file_bytes: int = 32 * 1024 * 1024,
    max_total_bytes: int = 128 * 1024 * 1024,
    max_elapsed_seconds: float = 300.0,
) -> dsf.FileSnapshotConfig:
    custody = custody if custody is not None else tmp_path / "custody"
    custody.mkdir(mode=0o700, exist_ok=True)
    return dsf.FileSnapshotConfig(
        custody_dir=custody,
        catalog_root=catalog_root,
        catalog_seal_key=catalog_seal_key,
        branding_dir=branding_dir,
        completion_profile_dir=completion_profile_dir,
        upstream_llm_profiles_file=upstream_llm_profiles_file,
        public_base_url_configured=False,
        max_file_bytes=max_file_bytes,
        max_total_bytes=max_total_bytes,
        max_elapsed_seconds=max_elapsed_seconds,
    )


def _seeded_job(
    tmp_path: Path,
    config: dsf.FileSnapshotConfig,
    *,
    state: str = ds.STATE_DB_SANITIZED_UNPUBLISHED,
) -> tuple[Path, ds.SnapshotManifest]:
    job_id = "snap-" + uuid.uuid4().hex
    job_dir = config.custody_dir / job_id
    job_dir.mkdir(mode=0o700)
    manifest = ds.SnapshotManifest(
        job_id=job_id,
        state=state,
        created_at=time.time(),
        target_db="demo_snap_" + uuid.uuid4().hex[:20],
    )
    ds.write_manifest(job_dir, manifest)
    return job_dir, manifest


def _capture(
    config: dsf.FileSnapshotConfig, seed: bytes = b"seed-1"
) -> dsf._Capture:
    return dsf.capture_all(config, _settings(), seed)


def _bare_config(**overrides) -> dsf.FileSnapshotConfig:
    """A config object with a custody dir that is never touched on disk
    (capture/budget unit tests need no real directory)."""
    base = dict(
        custody_dir=Path("/nonexistent-custody"),
        catalog_root=None,
        catalog_seal_key=None,
        branding_dir=None,
        completion_profile_dir=None,
        upstream_llm_profiles_file=None,
        public_base_url_configured=False,
        max_file_bytes=32 * 1024 * 1024,
        max_total_bytes=128 * 1024 * 1024,
        max_elapsed_seconds=300.0,
    )
    base.update(overrides)
    return dsf.FileSnapshotConfig(**base)


# ---------------------------------------------------------------------------
# Feature-local configuration
# ---------------------------------------------------------------------------


def test_files_config_defaults_are_valid(tmp_path) -> None:
    settings = _settings(DEMO_SNAPSHOT_CUSTODY_DIR=str(tmp_path / "custody"))
    config = dsf.files_config_from_settings(settings)
    assert config.max_file_bytes == 32 * 1024 * 1024
    assert config.max_total_bytes == 128 * 1024 * 1024
    assert config.max_elapsed_seconds == 300.0


def test_files_config_rejects_out_of_range_bounds(tmp_path) -> None:
    custody = str(tmp_path / "custody")
    for override in (
        {"DEMO_SNAPSHOT_FILES_MAX_FILE_BYTES": 1024},
        {"DEMO_SNAPSHOT_FILES_MAX_FILE_BYTES": 256 * 1024 * 1024},
        {"DEMO_SNAPSHOT_FILES_MAX_TOTAL_BYTES": 32 * 1024 * 1024},
        {"DEMO_SNAPSHOT_FILES_MAX_ELAPSED_SECONDS": 5},
        {"DEMO_SNAPSHOT_FILES_MAX_ELAPSED_SECONDS": 7200},
        {
            "DEMO_SNAPSHOT_FILES_MAX_FILE_BYTES": 128 * 1024 * 1024,
            "DEMO_SNAPSHOT_FILES_MAX_TOTAL_BYTES": 64 * 1024 * 1024,
        },
    ):
        settings = _settings(
            DEMO_SNAPSHOT_CUSTODY_DIR=custody,
            DEMO_SNAPSHOT_PGPASSFILE=str(tmp_path / "pgpass"),
            **override,
        )
        with pytest.raises(ds.DemoSnapshotError) as exc:
            dsf.files_config_from_settings(settings)
        assert exc.value.code == ds.CODE_MISCONFIGURED


def test_malformed_demo_file_settings_do_not_break_disabled_gateway(tmp_path) -> None:
    # The feature-local validator lives in files_config_from_settings, so
    # ordinary gateway startup (worker disabled) never sees these values.
    settings = Settings(
        DEMO_SNAPSHOT_ENABLED=False,
        DEMO_SNAPSHOT_FILES_MAX_FILE_BYTES=1024,
        DEMO_SNAPSHOT_FILES_MAX_TOTAL_BYTES=1024,
    )
    # ordinary startup never calls the feature-local validator
    assert settings.DEMO_SNAPSHOT_ENABLED is False
    # The worker entrypoint refuses disabled demo workers before the
    # feature-local file-cap checks are reached.
    with pytest.raises(ds.DemoSnapshotError) as exc:
        dsf.files_config_from_settings(settings)
    assert exc.value.code == ds.CODE_DISABLED


def test_enabled_worker_rejects_out_of_range_file_caps(tmp_path) -> None:
    settings = _settings(
        DEMO_SNAPSHOT_CUSTODY_DIR=str(tmp_path / "custody"),
        DEMO_SNAPSHOT_PGPASSFILE=str(tmp_path / "pgpass"),
        DEMO_SNAPSHOT_FILES_MAX_FILE_BYTES=1024,
    )
    with pytest.raises(ds.DemoSnapshotError) as exc:
        dsf.files_config_from_settings(settings)
    assert exc.value.code == ds.CODE_MISCONFIGURED


def test_catalog_root_and_seal_key_must_be_both_or_neither(tmp_path) -> None:
    root = tmp_path / "catalog"
    root.mkdir()
    config = _config(tmp_path, catalog_root=root)
    with pytest.raises(ds.DemoSnapshotError) as exc:
        _capture(config)
    assert exc.value.code == dsf.CODE_FILES_SOURCE_UNSAFE


# ---------------------------------------------------------------------------
# Typed display sanitizers: per-family canaries
# ---------------------------------------------------------------------------


def test_route_tsv_canaries_neutralized() -> None:
    import csv
    import io

    header = [
        "requested_model",
        "match_type",
        "endpoint",
        "provider",
        "upstream_model",
        "priority",
        "enabled",
        "visible_in_models",
        "supports_streaming",
        "capabilities",
        "notes",
    ]
    row = [
        "gpt-4o",
        "exact",
        "/v1/chat/completions",
        "openai",
        "gpt-4o",
        "10",
        "true",
        "true",
        "true",
        # The sealed route TSV carries the derived RUNTIME capability
        # projection (chat_completions block), not flat catalog keys.
        json.dumps({"chat_completions": {"chat_text": True, "chat_streaming": True}}),
        f"operator note {CANARY}",
    ]
    # Producer dialect: csv.writer with tab delimiter -> CRLF rows and
    # the JSON cell quoted with doubled quotes.
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter="\t")
    writer.writerow(header)
    writer.writerow(row)
    raw = buffer.getvalue().encode("utf-8")
    out = dsf._san_route_tsv(raw, b"seed")
    text = out.decode()
    assert CANARY not in text
    assert "operator note" not in text
    assert "\t" + dsf.DEMO_NOTES + "\n" in text or text.rstrip().endswith(dsf.DEMO_NOTES)


def test_route_tsv_unknown_capability_key_refused() -> None:
    header = [
        "requested_model",
        "match_type",
        "endpoint",
        "provider",
        "upstream_model",
        "priority",
        "enabled",
        "visible_in_models",
        "supports_streaming",
        "capabilities",
        "notes",
    ]
    row = [
        "gpt-4o",
        "exact",
        "/v1/chat/completions",
        "openai",
        "gpt-4o",
        "10",
        "true",
        "true",
        "true",
        json.dumps({f"{CANARY}_capability": True}),
        "",
    ]
    raw = ("\n".join(["\t".join(header), "\t".join(row)]) + "\n").encode()
    with pytest.raises(ds.DemoSnapshotError) as exc:
        dsf._san_route_tsv(raw, b"seed")
    assert exc.value.code == dsf.CODE_FILES_SOURCE_UNSUPPORTED


def test_pricing_tsv_source_fields_neutralized() -> None:
    header = [
        "provider",
        "model",
        "endpoint",
        "currency",
        "input_price_per_1m",
        "cached_input_price_per_1m",
        "output_price_per_1m",
        "reasoning_price_per_1m",
        "request_price",
        "valid_from",
        "source_url",
        "source_retrieved_at",
        "pricing_metadata",
        "notes",
    ]
    row = [
        "openai",
        "gpt-4o",
        "/v1/chat/completions",
        "USD",
        "2.5",
        "",
        "10",
        "",
        "",
        "2026-11-12T00:00:00Z",
        f"https://internal.example/?token={CANARY}",
        "2026-11-12T00:00:00Z",
        json.dumps({"note": CANARY}),
        CANARY,
    ]
    raw = ("\n".join(["\t".join(header), "\t".join(row)]) + "\n").encode()
    out = dsf._san_pricing_tsv(raw, b"seed")
    assert CANARY not in out.decode()
    assert "internal.example" not in out.decode()


def test_unknown_kind_has_no_sanitizer() -> None:
    with pytest.raises(ds.DemoSnapshotError) as exc:
        dsf._sanitize_by_kind("nope", b"x", seed=b"seed")
    assert exc.value.code == dsf.CODE_FILES_SOURCE_UNSUPPORTED


def test_branding_sanitizer_returns_packaged_fallback() -> None:
    from slaif_gateway.web import branding as web_branding

    logo, _ct = web_branding.fallback_asset("logo")
    assert dsf._san_branding(b"<svg>" + CANARY.encode(), b"seed", "logo") == logo
    assert dsf._san_branding(b"@import url(evil)", b"seed", "style.css") == b""
    with pytest.raises(ds.DemoSnapshotError):
        dsf._san_branding(b"x", b"seed", "not-a-slot")


# ---------------------------------------------------------------------------
# Typed display sanitizers: full-document canaries
# ---------------------------------------------------------------------------

BUNDLE_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "catalog_refresh" / "bundle-refresh-ready.json"


def test_refresh_bundle_canaries_neutralized() -> None:
    payload = json.loads(BUNDLE_FIXTURE.read_text())
    # The canary here is a SOURCE-valid slug (the source schema would
    # accept it); the demo projection must still replace it.
    payload["run_id"] = f"run-{CANARY.lower()}"
    payload["notes"] = f"operator notes {CANARY}"
    payload["revision"]["slaif_revision"] = f"rev-{CANARY}"
    payload["sources"][0]["url"] = f"https://internal.example/{CANARY}"
    payload["baseline"]["target_database"] = f"db-{CANARY}"
    raw = json.dumps(payload).encode()
    out = dsf._san_refresh_bundle(raw, b"seed")
    text = out.decode()
    assert CANARY not in text and CANARY.lower() not in text
    assert "internal.example" not in text
    doc = json.loads(text)
    assert doc["revision"]["slaif_revision"] == dsf.DEMO_CODE_REVISION
    assert doc["run_id"].startswith("demo-run-")
    # Source retrieval records (URLs/times) are never displayed; only
    # the finite count of the closed source list remains.
    assert doc["sources"] == {"count": len(payload["sources"])}
    assert set(doc["baseline"]) == {
        "mode",
        "postgres_version",
        "sql_checked",
        "row_counts",
    }


def test_baseline_row_counts_closed_keys() -> None:
    payload = json.loads(BUNDLE_FIXTURE.read_text())
    # A SOURCE-valid table-name slug outside the reviewed closed set:
    # the row-count law (not the schema) must refuse it.
    payload["baseline"]["row_counts"] = {"providers": 1, f"{CANARY.lower()}_table": 2}
    with pytest.raises(ds.DemoSnapshotError):
        dsf._closed_row_counts(payload["baseline"]["row_counts"])
    with pytest.raises(ds.DemoSnapshotError) as exc:
        dsf._san_refresh_bundle(json.dumps(payload).encode(), b"seed")
    assert exc.value.code == dsf.CODE_FILES_SOURCE_UNSUPPORTED
    # first_install emits an empty row-count map: that is allowed.
    assert dsf._closed_row_counts({}) == {}
    payload["baseline"] = {}  # first_install: explicitly empty baseline
    payload["baseline"]["mode"] = "first_install"
    out = dsf._san_refresh_bundle(json.dumps(payload).encode(), b"seed")
    assert json.loads(out.decode())["baseline"]["row_counts"] == {}


_VALIDATION_DOC = {
    "state": "ready",
    "state_reason": f"reason {CANARY}",
    "run_id": f"run-{CANARY}",
    "generated_at": "2026-11-12T00:00:00+00:00",
    "policy_version": 7,
    "counts": {f"{CANARY}_name": 3, "routes": 5},
    "per_provider": {"openrouter": {"input": 1, f"{CANARY}_metric": 2}},
    "dispositions": [
        {"provider": "openrouter", "model": "synthetic/stable-v1", "disposition": "included"}
    ],
    "price_comparisons": [
        {
            "provider": "openrouter",
            "model": "synthetic/stable-v1",
            "dimension": "input",
            "old": "1.5",
            "new": "2.5",
            "currency_old": "EUR",
            "currency_new": "EUR",
            "percent_change": "66.67",
            "state": "within_bounds",
        }
    ],
    "warnings": [
        {"severity": "info", "code": "ok", "provider": "openrouter", "model": f"leak-{CANARY}"}
    ],
    "import_gates": [
        {
            "kind": "routes",
            "schema_valid": True,
            "total_rows": 2,
            "valid_rows": 2,
            "invalid_rows": 0,
            "classifications": {f"{CANARY}_cls": 2},
            "plan_ready_rows": 2,
            "plan_blocked_rows": 0,
            "excluded_mutations": 1,
        }
    ],
    "baseline_metadata": [
        {
            "provider": "openrouter",
            "model": "synthetic/stable-v1",
            "upstream_model": "synthetic/stable-v1-up",
            "fields": {f"f1 {CANARY}": "x", "f2": "y"},
        }
    ],
    "sources": [
        {
            "provider": "openrouter",
            "model": "synthetic/stable-v1",
            "source_kind": "openrouter_models_api",
        }
    ],
    "baseline": {"rows": 5, CANARY: "deep"},
    "research": {"a": 1},
    "artifacts": {"b": 2},
    "sql_checks": {"c": 3},
    "fx_comparisons": [{"x": 1}],
    "execution_context": {
        "schema_version": "1",
        "acquisition": "offline_supplied",
        # tool/code_revision carry the canary: they must be DROPPED.
        "generator": {"tool": f"tool-{CANARY}", "code_revision": f"rev-{CANARY}"},
        "generator_versions": {
            "schema_version": _EXEC_SCHEMA_VERSION,
            "renderer_version": _EXEC_RENDERER_VERSION,
            "policy_version": _EXEC_POLICY_VERSION,
            "extractor_version": _EXEC_EXTRACTOR_ID,
        },
    },
}


def test_validation_json_canaries_neutralized() -> None:
    out = dsf._san_validation_json(json.dumps(_VALIDATION_DOC).encode(), b"seed")
    text = out.decode()
    assert CANARY not in text
    doc = json.loads(text)
    assert doc["state_reason"] == dsf.DEMO_NOTES
    assert doc["run_id"].startswith("demo-run-")
    assert doc["counts"] == {"entries": 2}
    # per_provider keeps only the closed provider key; inner metric
    # names are map positions, reduced to their TOTAL (1 + 2 = 3).
    assert doc["per_provider"] == {"openrouter": {"total": 3}}
    assert doc["baseline"] == {"count": 2}
    assert doc["source_evidence"] == {}
    assert doc["import_gates"][0]["classifications"] == {"total": 2}
    assert doc["import_gates"][0]["excluded_mutations"] == 1
    assert doc["baseline_metadata"][0]["fields"] == {"count": 2}
    # model detail is a free-text position in warnings: dropped.
    assert "model" not in doc["warnings"][0]
    # execution context: app versions pinned to the current product
    # constants; tool/code_revision identity dropped.
    assert doc["execution_context"] == {
        "schema_version": "1",
        "acquisition": "offline_supplied",
        "generator_versions": {
            "schema_version": _EXEC_SCHEMA_VERSION,
            "renderer_version": _EXEC_RENDERER_VERSION,
            "policy_version": _EXEC_POLICY_VERSION,
            "extractor_version": _EXEC_EXTRACTOR_ID,
        },
    }


def test_validation_json_unknown_shape_refused() -> None:
    broken = dict(_VALIDATION_DOC)
    broken["unexpected_key"] = "x"
    with pytest.raises(ds.DemoSnapshotError) as exc:
        dsf._san_validation_json(json.dumps(broken).encode(), b"seed")
    assert exc.value.code == dsf.CODE_FILES_SOURCE_UNSUPPORTED
    broken = dict(_VALIDATION_DOC)
    broken["per_provider"] = {"not-a-provider": {"total": 1}}
    with pytest.raises(ds.DemoSnapshotError):
        dsf._san_validation_json(json.dumps(broken).encode(), b"seed")
    # An upstream model detail outside the model-id grammar is refused:
    # the model field is a typed position, not free text.
    broken = json.loads(json.dumps(_VALIDATION_DOC))
    broken["baseline_metadata"][0]["upstream_model"] = f"up {CANARY}"
    with pytest.raises(ds.DemoSnapshotError):
        dsf._san_validation_json(json.dumps(broken).encode(), b"seed")
    # A sealed run generated by ANOTHER renderer version is refused:
    # the display projection only re-proves the current product law.
    broken = json.loads(json.dumps(_VALIDATION_DOC))
    broken["execution_context"]["generator_versions"]["renderer_version"] = "0.0-old"
    with pytest.raises(ds.DemoSnapshotError) as exc:
        dsf._san_validation_json(json.dumps(broken).encode(), b"seed")
    assert exc.value.code == dsf.CODE_FILES_SOURCE_UNSUPPORTED


# ---------------------------------------------------------------------------
# Capture boundary: branding and completion-profile source laws
# ---------------------------------------------------------------------------

_CANARY_SVG = (
    f'<svg xmlns="http://www.w3.org/2000/svg"><title>{CANARY}</title></svg>'
).encode("utf-8")


def test_branding_valid_svg_resolved_and_substituted(tmp_path) -> None:
    from slaif_gateway.web import branding as web_branding

    brand = tmp_path / "brand"
    brand.mkdir()
    (brand / "logo.svg").write_bytes(_CANARY_SVG)
    config = _config(tmp_path, branding_dir=brand)
    capture = dsf.capture_all(config, _settings(), b"seed")
    slots = capture.source_records["branding"]["slots"]
    assert slots["logo"] == {
        "resolved": True,
        "file_name": "logo.svg",
        "content_type": "image/svg+xml",
        "substituted": False,
    }
    leaves = {leaf.logical_name: leaf for leaf in capture.leaves}
    logo_leaf = leaves["branding/logo"]
    fallback, _ct = web_branding.fallback_asset("logo")
    # The operator's own SVG (canary included) is never copied: the
    # display leaf is exactly the packaged neutral substitute.
    assert logo_leaf.data == fallback
    assert CANARY.encode() not in logo_leaf.data
    # Unconfigured optional slots still get their neutral fallbacks.
    assert slots["favicon"]["substituted"] is True
    assert leaves["branding/favicon"].data == web_branding.fallback_asset("favicon")[0]


def test_branding_symlink_candidate_fails_unsupported(tmp_path) -> None:
    brand = tmp_path / "brand"
    brand.mkdir()
    target = tmp_path / "real.svg"
    target.write_bytes(_CANARY_SVG)
    (brand / "logo.svg").symlink_to(target)
    config = _config(tmp_path, branding_dir=brand)
    with pytest.raises(ds.DemoSnapshotError) as exc:
        dsf.capture_all(config, _settings(), b"seed")
    assert exc.value.code == dsf.CODE_FILES_SOURCE_UNSUPPORTED


def test_branding_dual_candidate_fails_unsupported(tmp_path) -> None:
    brand = tmp_path / "brand"
    brand.mkdir()
    (brand / "logo.svg").write_bytes(_CANARY_SVG)
    (brand / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 32)
    config = _config(tmp_path, branding_dir=brand)
    with pytest.raises(ds.DemoSnapshotError) as exc:
        dsf.capture_all(config, _settings(), b"seed")
    assert exc.value.code == dsf.CODE_FILES_SOURCE_UNSUPPORTED


def test_completion_profiles_fictionalized_and_bodies_never_copied(tmp_path, umask_022) -> None:
    prof = tmp_path / "profiles"
    prof.mkdir()
    for stem in ("alpha-profile", "beta-profile"):
        (prof / f"{stem}.json").write_text(json.dumps({"org": CANARY, "id": stem}))
    (prof / "bindings.json").write_text(json.dumps({CANARY: "bindings"}))
    (prof / "not-a-profile.txt").write_text(CANARY)
    config = _config(tmp_path, completion_profile_dir=prof)
    capture = dsf.capture_all(config, _settings(), b"seed-1")
    leaf = capture.leaves[0]
    assert leaf.logical_name == "profiles/completion-choices.json"
    doc = json.loads(leaf.data)
    profiles = doc["profiles"]
    assert len(profiles) == 2
    for item in profiles:
        assert re.fullmatch(r"demo-profile-[0-9a-f]{24}", item)
    # The operator stems and the profile BODIES are never displayed.
    text = leaf.data.decode()
    assert CANARY not in text
    assert "alpha-profile" not in text and "beta-profile" not in text
    # The private per-copy id map is custody state, not display data.
    id_map = capture.source_records["completion_profiles"]["id_map"]
    assert set(id_map) == set(profiles)
    assert set(id_map.values()) == {"alpha-profile", "beta-profile"}
    # A second copy (different job seed) gets a DIFFERENT fictional
    # mapping: no cross-copy reuse of the first copy's IDs.
    capture2 = dsf.capture_all(config, _settings(), b"seed-2")
    profiles2 = json.loads(capture2.leaves[0].data)["profiles"]
    assert set(profiles2).isdisjoint(set(profiles))
    # bindings.json is excluded by the admin loader law.
    assert "bindings" not in capture.source_records["completion_profiles"]["id_map"].values()


# ---------------------------------------------------------------------------
# Capture boundary: configured catalog custody (worker-read-only)
# ---------------------------------------------------------------------------


def _catalog_tree(
    tmp_path: Path,
    *,
    mode: int = 0o700,
    subdirs=("runs", "uploads", "proposals", "jobs"),
) -> tuple[Path, Path]:
    """A minimal configured catalog custody: required subdirs + seal key."""
    root = tmp_path / "catalog"
    root.mkdir()
    for sub in subdirs:
        (root / sub).mkdir()
    root.chmod(mode)
    key_parent = tmp_path / "sealkey"
    key_parent.mkdir()
    key_parent.chmod(0o700)
    key = key_parent / "seal.key"
    catfs.ensure_seal_key(key)
    return root, key


def test_capture_missing_catalog_subdir_fails_closed(tmp_path, umask_022) -> None:
    root, key = _catalog_tree(
        tmp_path, subdirs=("runs", "uploads", "proposals")  # jobs missing
    )
    config = _config(tmp_path, catalog_root=root, catalog_seal_key=key)
    with pytest.raises(ds.DemoSnapshotError) as exc:
        dsf.capture_all(config, _settings(), b"seed")
    assert exc.value.code == dsf.CODE_FILES_SOURCE_MISSING


def test_capture_accepts_0755_owner_owned_catalog_root(tmp_path, umask_022) -> None:
    # The read-only SOURCE acceptance law matches the admin custody
    # service: owner-owned and not group/world WRITABLE (0755 is usable).
    root, key = _catalog_tree(tmp_path, mode=0o755)
    config = _config(tmp_path, catalog_root=root, catalog_seal_key=key)
    capture = dsf.capture_all(config, _settings(), b"seed")
    record = capture.source_records["catalog"]
    assert record["configured"] is True
    assert record["runs"] == [] and record["jobs"] == []


def test_capture_rejects_group_writable_catalog_root(tmp_path, umask_022) -> None:
    root, key = _catalog_tree(tmp_path, mode=0o702)
    config = _config(tmp_path, catalog_root=root, catalog_seal_key=key)
    with pytest.raises(ds.DemoSnapshotError) as exc:
        dsf.capture_all(config, _settings(), b"seed")
    assert exc.value.code == dsf.CODE_FILES_SOURCE_UNSAFE


def test_capture_run_directory_swap_fails_changed(tmp_path, umask_022, monkeypatch) -> None:
    # A run directory swapped (new inode) at the SAME path between
    # enumeration and open must be detected as a changed source.
    root, key = _catalog_tree(tmp_path)
    run_id = "run-swap-test"
    run_dir = root / "runs" / run_id
    run_dir.mkdir()
    config = _config(tmp_path, catalog_root=root, catalog_seal_key=key)
    real_open = catfs.open_anchored_handle
    swapped = {"done": False}

    def swap_then_open(path, **kwargs):
        if not swapped["done"] and str(path) == str(run_dir):
            swapped["done"] = True
            os.rename(run_dir, run_dir.parent / (run_id + ".bak"))
            run_dir.mkdir()
        return real_open(path, **kwargs)

    monkeypatch.setattr(catfs, "open_anchored_handle", swap_then_open)
    with pytest.raises(ds.DemoSnapshotError) as exc:
        dsf.capture_all(config, _settings(), b"seed")
    assert exc.value.code == dsf.CODE_FILES_SOURCE_CHANGED
    assert swapped["done"] is True


# ---------------------------------------------------------------------------
# Independent verifier: tamper refusal (any drift is FILES_VERIFY_FAILED)
# ---------------------------------------------------------------------------


def _written_job(
    tmp_path,
    *,
    max_file_bytes: int = 32 * 1024 * 1024,
    max_total_bytes: int = 128 * 1024 * 1024,
) -> tuple[Path, ds.SnapshotManifest, dsf.FileSnapshotConfig]:
    """One job with a fully written + verified display tree."""
    config = _config(
        tmp_path,
        max_file_bytes=max_file_bytes,
        max_total_bytes=max_total_bytes,
    )
    job_dir, manifest = _seeded_job(tmp_path, config)
    capture = dsf._Capture(config, _settings())
    capture.add_display(
        kind=dsf.KIND_WARNINGS_JSON,
        source="t",
        source_ref="t:warnings",
        logical_name="t/warnings.json",
        raw=b'{"warnings": []}',
        seed=b"s1",
    )
    capture.add_display(
        kind=dsf.KIND_REVIEW_HTML,
        source="t",
        source_ref="t:report",
        logical_name="t/report.html",
        raw=b"<html>secret-operator-report</html>",
        seed=b"s1",
    )
    dsf._write_files(job_dir, capture)
    dsf.verify_files(job_dir, manifest, config, time.monotonic() + 60)
    return job_dir, manifest, config


def _manifest_path(job_dir: Path) -> Path:
    return job_dir / dsf.FILES_DIR_NAME / dsf.FILES_MANIFEST_NAME


def _mutate_files_manifest(job_dir: Path, mutate) -> None:
    doc = json.loads(_manifest_path(job_dir).read_text())
    mutate(doc)
    _manifest_path(job_dir).write_text(json.dumps(doc, sort_keys=True))


def _first_leaf_name(job_dir: Path) -> str:
    doc = json.loads(_manifest_path(job_dir).read_text())
    return doc["files"][0]["leaf"]


def test_verify_refuses_tampered_leaf_content(tmp_path) -> None:
    job_dir, manifest, config = _written_job(tmp_path)
    leaf = job_dir / dsf.FILES_DIR_NAME / _first_leaf_name(job_dir)
    data = bytearray(leaf.read_bytes())
    data[-2] = data[-2] ^ 1  # same size, different bytes
    leaf.write_bytes(bytes(data))
    with pytest.raises(ds.DemoSnapshotError) as exc:
        dsf.verify_files(job_dir, manifest, config, time.monotonic() + 60)
    assert exc.value.code == dsf.CODE_FILES_VERIFY_FAILED


def test_verify_refuses_leaf_mode_drift(tmp_path) -> None:
    job_dir, manifest, config = _written_job(tmp_path)
    (job_dir / dsf.FILES_DIR_NAME / _first_leaf_name(job_dir)).chmod(0o644)
    with pytest.raises(ds.DemoSnapshotError) as exc:
        dsf.verify_files(job_dir, manifest, config, time.monotonic() + 60)
    assert exc.value.code == dsf.CODE_FILES_VERIFY_FAILED


def test_verify_refuses_leaf_inode_drift(tmp_path) -> None:
    job_dir, manifest, config = _written_job(tmp_path)
    leaf = job_dir / dsf.FILES_DIR_NAME / _first_leaf_name(job_dir)
    content = leaf.read_bytes()
    leaf.unlink()
    leaf.write_bytes(content)  # same bytes, NEW inode
    with pytest.raises(ds.DemoSnapshotError) as exc:
        dsf.verify_files(job_dir, manifest, config, time.monotonic() + 60)
    assert exc.value.code == dsf.CODE_FILES_VERIFY_FAILED


def test_verify_refuses_foreign_entry_in_files(tmp_path) -> None:
    job_dir, manifest, config = _written_job(tmp_path)
    (job_dir / dsf.FILES_DIR_NAME / "foreign.txt").write_bytes(b"not ours")
    with pytest.raises(ds.DemoSnapshotError) as exc:
        dsf.verify_files(job_dir, manifest, config, time.monotonic() + 60)
    assert exc.value.code == dsf.CODE_FILES_VERIFY_FAILED


def test_verify_refuses_missing_leaf(tmp_path) -> None:
    job_dir, manifest, config = _written_job(tmp_path)
    (job_dir / dsf.FILES_DIR_NAME / _first_leaf_name(job_dir)).unlink()
    with pytest.raises(ds.DemoSnapshotError) as exc:
        dsf.verify_files(job_dir, manifest, config, time.monotonic() + 60)
    assert exc.value.code == dsf.CODE_FILES_VERIFY_FAILED


def test_verify_refuses_files_dir_mode_drift(tmp_path) -> None:
    job_dir, manifest, config = _written_job(tmp_path)
    (job_dir / dsf.FILES_DIR_NAME).chmod(0o755)
    with pytest.raises(ds.DemoSnapshotError) as exc:
        dsf.verify_files(job_dir, manifest, config, time.monotonic() + 60)
    assert exc.value.code == dsf.CODE_FILES_VERIFY_FAILED


def test_verify_refuses_bool_manifest_size(tmp_path) -> None:
    job_dir, manifest, config = _written_job(tmp_path)

    def flip(doc):
        doc["files"][0]["bytes"] = True

    _mutate_files_manifest(job_dir, flip)
    with pytest.raises(ds.DemoSnapshotError) as exc:
        dsf.verify_files(job_dir, manifest, config, time.monotonic() + 60)
    assert exc.value.code == dsf.CODE_FILES_VERIFY_FAILED


def test_verify_refuses_oversized_manifest_size(tmp_path) -> None:
    job_dir, manifest, config = _written_job(tmp_path)

    def inflate(doc):
        # The untrusted manifest count can never raise the read cap.
        doc["files"][0]["bytes"] = config.max_file_bytes + 1

    _mutate_files_manifest(job_dir, inflate)
    with pytest.raises(ds.DemoSnapshotError) as exc:
        dsf.verify_files(job_dir, manifest, config, time.monotonic() + 60)
    assert exc.value.code == dsf.CODE_FILES_VERIFY_FAILED


def test_verify_refuses_json_leaf_extra_key(tmp_path) -> None:
    job_dir, manifest, config = _written_job(tmp_path)
    leaf = job_dir / dsf.FILES_DIR_NAME / _first_leaf_name(job_dir)
    doc = json.loads(leaf.read_bytes())
    doc["injected"] = CANARY
    leaf.write_text(json.dumps(doc) + "\n")
    with pytest.raises(ds.DemoSnapshotError) as exc:
        dsf.verify_files(job_dir, manifest, config, time.monotonic() + 60)
    assert exc.value.code == dsf.CODE_FILES_VERIFY_FAILED


def test_verify_refuses_unknown_leaf_kind(tmp_path) -> None:
    job_dir, manifest, config = _written_job(tmp_path)

    def rekind(doc):
        doc["files"][0]["kind"] = "nope"

    _mutate_files_manifest(job_dir, rekind)
    with pytest.raises(ds.DemoSnapshotError) as exc:
        dsf.verify_files(job_dir, manifest, config, time.monotonic() + 60)
    assert exc.value.code == dsf.CODE_FILES_VERIFY_FAILED


def test_verify_refuses_expired_deadline(tmp_path, monkeypatch) -> None:
    job_dir, manifest, config = _written_job(tmp_path)
    real_monotonic = time.monotonic
    base = real_monotonic()
    monkeypatch.setattr(dsf.time, "monotonic", lambda: base + 10_000)
    with pytest.raises(ds.DemoSnapshotError) as exc:
        dsf.verify_files(job_dir, manifest, config, base + 60)
    assert exc.value.code == dsf.CODE_FILES_BUDGET_EXCEEDED


# ---------------------------------------------------------------------------
# Job runner: interrupted write, safe cleanup and refusal
# ---------------------------------------------------------------------------


def test_interrupted_pre_manifest_write_fails_cleanup_and_retains(tmp_path) -> None:
    """A torn write that left leaves but NO files manifest must fail the
    retry closed: cleanup refuses (no exact-leaf record), the copy keeps
    its 222 state with a safe finite code, and the artifacts are RETAINED
    for operator inspection."""
    config = _config(tmp_path)
    job_dir, manifest = _seeded_job(tmp_path, config)
    manifest.files_state = dsf.FILES_STATE_PENDING
    ds.write_manifest(job_dir, manifest)
    files = job_dir / dsf.FILES_DIR_NAME
    files.mkdir(mode=0o700)
    partial = "f0000-" + "0" * 12
    (files / partial).write_bytes(b"partial-leaf")
    result = dsf.run_files_job(config, _settings())
    assert result.state == "FAILED"
    assert result.copies_failed == 1 and result.copies_files_verified == 0
    # The aggregate safe code matches the per-copy manifest code.
    assert result.failure_code == dsf.CODE_FILES_CLEANUP_FAILED
    after = ds.read_manifest(job_dir)
    assert after.state == ds.STATE_DB_SANITIZED_UNPUBLISHED
    assert after.files_state == dsf.FILES_STATE_FAILED
    assert after.files_failure_code == dsf.CODE_FILES_CLEANUP_FAILED
    # Artifacts retained: no exact-leaf record means no exact cleanup.
    assert files.exists()
    assert (files / partial).exists()


def test_cleanup_refuses_rebound_files_directory(tmp_path) -> None:
    """The held files/ identity must equal the manifest-recorded identity:
    a directory swapped for a fresh one (new inode) with a copied manifest
    is a REBIND - cleanup refuses and retains everything for the operator."""
    job_dir, manifest, _config = _written_job(tmp_path)
    manifest.files_state = dsf.FILES_STATE_FAILED
    manifest.files_failure_code = dsf.CODE_FILES_BUDGET_EXCEEDED
    ds.write_manifest(job_dir, manifest)
    files = job_dir / dsf.FILES_DIR_NAME
    manifest_bytes = (files / dsf.FILES_MANIFEST_NAME).read_bytes()
    backup = job_dir / "files-orig-backup"
    os.rename(files, backup)  # original tree retained untouched
    files.mkdir(mode=0o700)  # NEW inode at the original path
    (files / dsf.FILES_MANIFEST_NAME).write_bytes(manifest_bytes)
    assert ds._clean_job_files(job_dir) is False
    assert files.exists()
    assert (files / dsf.FILES_MANIFEST_NAME).exists()
    # The original verified tree (leaves included) is untouched by the
    # refused cleanup.
    assert backup.exists()
    assert dsf.FILES_MANIFEST_NAME in os.listdir(backup)
    assert any(name.startswith("f00") for name in os.listdir(backup))


def test_cleanup_refuses_foreign_entry_in_files(tmp_path) -> None:
    """A valid exact-leaf set plus ONE foreign entry: the exact-leaf
    removal cannot rmdir the directory, so cleanup fails and retains the
    tree (the foreign file is never deleted by name)."""
    job_dir, manifest, _config = _written_job(tmp_path)
    manifest.files_state = dsf.FILES_STATE_FAILED
    manifest.files_failure_code = dsf.CODE_FILES_BUDGET_EXCEEDED
    ds.write_manifest(job_dir, manifest)
    files = job_dir / dsf.FILES_DIR_NAME
    (files / "foreign-entry").write_bytes(b"not ours")
    assert ds._clean_job_files(job_dir) is False
    assert (files / "foreign-entry").exists()
    assert files.exists()


def _fake_copy_profiles_for(
    job_dirs: tuple[Path, ...], stems: tuple[str, ...]
):
    """Unit stub for the gate's read-only copy-DB fetch.

    The fake copied database references exactly the fictional profiles
    derived under EACH copy's own job seed (the same shared derivation
    the 222 route transform and the 223 choices projection use).
    """
    async def _fetch(base, target_db: str, timeout: float):
        for job_dir in job_dirs:
            manifest = ds.read_manifest(job_dir)
            if manifest.target_db == target_db:
                return [
                    dsf.demo_profile_id(manifest.job_id.encode(), stem)
                    for stem in stems
                ]
        raise AssertionError("unknown copy database")

    return _fetch


def test_completion_link_violations_law() -> None:
    # No copied route references a profile: always consistent.
    assert dsf._completion_link_violations([], None) == 0
    assert dsf._completion_link_violations([], frozenset({"p1"})) == 0
    # Route references a profile but no choices were captured: missing
    # link for every reference.
    assert dsf._completion_link_violations(["p1", "p2"], None) == 2
    # Exact fictional choice link: consistent, even with extra choices.
    assert dsf._completion_link_violations(["p1"], frozenset({"p1", "p2"})) == 0
    # One inconsistent reference: exactly one violation.
    assert dsf._completion_link_violations(["p1", "p3"], frozenset({"p1", "p2"})) == 1


def test_runner_two_copies_get_disjoint_mappings(tmp_path, umask_022, monkeypatch) -> None:
    prof = tmp_path / "profiles"
    prof.mkdir()
    for stem in ("alpha-profile", "beta-profile"):
        (prof / f"{stem}.json").write_text("{}")
    config = _config(tmp_path, completion_profile_dir=prof)
    job_a, _ma = _seeded_job(tmp_path, config)
    job_b, _mb = _seeded_job(tmp_path, config)
    # Gate stub: each fake copy DB links to its own copy's fictional
    # choices (positive link proof for the combined gate).
    monkeypatch.setattr(
        dsf,
        "_copy_completion_profile_ids",
        _fake_copy_profiles_for((job_a, job_b), ("alpha-profile", "beta-profile")),
    )
    result = dsf.run_files_job(config, _settings())
    assert result.state == "FILES_VERIFIED"
    assert result.copies_files_verified == 2 and result.copies_failed == 0
    for job_dir in (job_a, job_b):
        assert ds.read_manifest(job_dir).state == ds.STATE_DB_AND_FILES_VERIFIED_UNPUBLISHED

    def choice_profiles(job_dir: Path) -> list[str]:
        doc = json.loads(_manifest_path(job_dir).read_text())
        for entry in doc["files"]:
            if entry["logical_name"] == "profiles/completion-choices.json":
                leaf = job_dir / dsf.FILES_DIR_NAME / entry["leaf"]
                return json.loads(leaf.read_bytes())["profiles"]
        raise AssertionError("completion choices leaf missing")

    profiles_a = choice_profiles(job_a)
    profiles_b = choice_profiles(job_b)
    assert len(profiles_a) == 2 and len(profiles_b) == 2
    # Each copy (seeded by its own job id) gets a DIFFERENT fictional
    # mapping: no cross-copy reuse.
    assert set(profiles_a).isdisjoint(set(profiles_b))
    # The second run is idempotent: already-verified copies are skipped.
    # Promoted copies are not re-counted as newly verified: zero new
    # copies with zero failures is the safe idempotent result.
    again = dsf.run_files_job(config, _settings())
    assert again.state == "FILES_VERIFIED"
    assert again.copies_files_verified == 0 and again.copies_failed == 0


def test_runner_completion_link_mismatch_fails_before_publication(
    tmp_path, umask_022, monkeypatch
) -> None:
    """A copied route referencing a profile that does NOT link to the
    captured fictional choices must fail the combined job BEFORE
    publication: finite code, cleanup, no promotion."""
    prof = tmp_path / "profiles"
    prof.mkdir()
    (prof / "alpha-profile.json").write_text("{}")
    config = _config(tmp_path, completion_profile_dir=prof)
    job_dir, _manifest = _seeded_job(tmp_path, config)
    # The fake copy DB still carries the RAW operator profile id (a
    # tampered/inconsistent copy): it links to nothing captured.
    async def _raw_profiles(base, target_db, timeout: float):
        return ["alpha-profile"]

    monkeypatch.setattr(dsf, "_copy_completion_profile_ids", _raw_profiles)
    result = dsf.run_files_job(config, _settings())
    assert result.state == "FAILED"
    assert result.copies_failed == 1 and result.copies_files_verified == 0
    assert result.failure_code == dsf.CODE_FILES_VERIFY_FAILED
    after = ds.read_manifest(job_dir)
    assert after.state == ds.STATE_DB_SANITIZED_UNPUBLISHED
    assert after.files_state == dsf.FILES_STATE_FAILED
    assert after.files_failure_code == dsf.CODE_FILES_VERIFY_FAILED
    assert not (job_dir / dsf.FILES_DIR_NAME).exists()  # cleaned, unpublished


def test_runner_completion_link_missing_choices_fails_closed(
    tmp_path, umask_022, monkeypatch
) -> None:
    """A copied route referencing a completion profile while the profile
    source is UNCONFIGURED (no choices to link to) fails closed."""
    config = _config(tmp_path)  # no completion_profile_dir
    job_dir, _manifest = _seeded_job(tmp_path, config)

    async def _raw_profiles(base, target_db, timeout: float):
        return ["some-profile"]

    monkeypatch.setattr(dsf, "_copy_completion_profile_ids", _raw_profiles)
    result = dsf.run_files_job(config, _settings())
    assert result.state == "FAILED"
    assert result.failure_code == dsf.CODE_FILES_VERIFY_FAILED
    after = ds.read_manifest(job_dir)
    assert after.state == ds.STATE_DB_SANITIZED_UNPUBLISHED
    assert after.files_failure_code == dsf.CODE_FILES_VERIFY_FAILED


class _FakeClock:
    def __init__(self, start: float) -> None:
        self.t = start

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


def test_runner_deadline_lapse_before_promotion_never_publishes(
    tmp_path, monkeypatch
) -> None:
    """If the copy budget lapses AFTER verification but BEFORE the
    promotion write, the copy is cleaned and refused - never published."""
    config = _config(tmp_path)
    job_dir, _manifest = _seeded_job(tmp_path, config)
    clock = _FakeClock(1000.0)
    monkeypatch.setattr(dsf.time, "monotonic", clock)
    real_verify = dsf.verify_files

    def verify_then_lapse(job_dir, manifest, cfg, deadline):
        real_verify(job_dir, manifest, cfg, deadline)
        clock.advance(config.max_elapsed_seconds + 5)

    monkeypatch.setattr(dsf, "verify_files", verify_then_lapse)
    result = dsf.run_files_job(config, _settings())
    assert result.state == "FAILED"
    assert result.copies_failed == 1 and result.copies_files_verified == 0
    assert result.failure_code == dsf.CODE_FILES_BUDGET_EXCEEDED
    after = ds.read_manifest(job_dir)
    assert after.state == ds.STATE_DB_SANITIZED_UNPUBLISHED
    assert after.files_state == dsf.FILES_STATE_FAILED
    assert after.files_failure_code == dsf.CODE_FILES_BUDGET_EXCEEDED
    assert not (job_dir / dsf.FILES_DIR_NAME).exists()  # cleaned, unpublished


def test_runner_config_validation_failure_does_not_leak_fence(
    tmp_path, umask_022, monkeypatch
) -> None:
    """If the 221 base-config validation raises, the custody fence must not
    leak: the base config is validated BEFORE the fence is acquired."""
    config = _config(tmp_path)

    def boom(_s):
        raise RuntimeError("config validation failed")

    monkeypatch.setattr(dsf.ds, "config_from_settings", boom)
    with pytest.raises(RuntimeError, match="config validation failed"):
        dsf.run_files_job(config, _settings())
    # The fence was never held: a fresh acquire succeeds. Close the
    # acquired descriptor explicitly and exactly once (even if the
    # assertion below fails) so the test itself cannot leak it.
    fd = ds.acquire_fence(config.custody_dir)
    try:
        assert isinstance(fd, int) and fd >= 0
    finally:
        ds.release_fence(fd)


def test_leaf_index_uses_four_digit_boundary() -> None:
    config = _bare_config()
    capture = dsf._Capture(config, _settings())
    for _ in range(1001):
        capture.add_display(
            kind=dsf.KIND_REVIEW_HTML,
            source="t",
            source_ref="t:h",
            logical_name="t/h",
            raw=b"x",
            seed=b"s",
        )
    leaf = capture.leaves[1000]
    assert leaf.leaf.startswith("f1000-")
    assert dsf._LEAF_NAME_RE.fullmatch(leaf.leaf)


def test_add_display_admits_raw_before_parsing() -> None:
    """The aggregate RAW budget is checked BEFORE the typed sanitizer
    parses: an oversized invalid raw file is TOO_LARGE, not UNSUPPORTED."""
    config = _bare_config(max_file_bytes=64)
    capture = dsf._Capture(config, _settings())
    with pytest.raises(ds.DemoSnapshotError) as exc:
        capture.add_display(
            kind=dsf.KIND_WARNINGS_JSON,
            source="t",
            source_ref="t:r",
            logical_name="t/r",
            raw=b"{" * 128,
            seed=b"s",
        )
    assert exc.value.code == dsf.CODE_FILES_SOURCE_TOO_LARGE


def test_raw_bytes_not_retained_after_add_display() -> None:
    import sys

    config = _bare_config()
    capture = dsf._Capture(config, _settings())
    raw = b"raw-operator-bytes-" * 100
    # No NEW reference to the raw source object may survive the call:
    # the capture retains the sanitized display bytes only.
    before = sys.getrefcount(raw)
    leaf = capture.add_display(
        kind=dsf.KIND_REVIEW_HTML,
        source="t",
        source_ref="t:r",
        logical_name="t/r",
        raw=raw,
        seed=b"s",
    )
    assert leaf.data == dsf.NEUTRAL_REVIEW_HTML
    assert sys.getrefcount(raw) == before


def test_write_refuses_existing_files_directory(tmp_path) -> None:
    config = _config(tmp_path)
    job_dir, _manifest = _seeded_job(tmp_path, config)
    (job_dir / dsf.FILES_DIR_NAME).mkdir()
    capture = dsf._Capture(config, _settings())
    capture.add_display(
        kind=dsf.KIND_REVIEW_HTML,
        source="t",
        source_ref="t:h",
        logical_name="t/h",
        raw=b"x",
        seed=b"s",
    )
    with pytest.raises(ds.DemoSnapshotError) as exc:
        dsf._write_files(job_dir, capture)
    assert exc.value.code == dsf.CODE_FILES_WRITE_FAILED


# ---------------------------------------------------------------------------
# Per-kind source-valid canary cases (chunk 1: fx, warnings, neutral)
# ---------------------------------------------------------------------------


def _fx_fact(source: str | None = "https://example.invalid/" + CANARY) -> dict:
    return {
        "base_currency": "EUR",
        "quote_currency": "USD",
        "rate": "1.0800",
        "valid_from": "2026-11-01T00:00:00+00:00",
        "valid_until": "2026-12-01T00:00:00+00:00",
        "published_at": "2026-11-01T06:00:00+00:00",
        "source": source,
        "provenance": {
            "sources": [f"openrouter|gpt-4o-mini|{CANARY}"],
            "extractor": CANARY,
            "extraction": "deterministic",
        },
        "warnings": [f"{CANARY}-note"],
    }


def test_fx_json_projects_closed_fields_and_drops_canary() -> None:
    raw = json.dumps([_fx_fact()]).encode()
    out = json.loads(dsf._san_fx_json(raw, b"seed-1"))
    assert CANARY not in json.dumps(out)
    assert out["schema"] == dsf.DEMO_SCHEMA_VERSION
    assert out["kind"] == dsf.KIND_FX_JSON
    assert out["fx"] == [
        {
            "base_currency": "EUR",
            "quote_currency": "USD",
            "rate": "1.0800",
            "valid_from": "2026-11-01T00:00:00+00:00",
            "valid_until": "2026-12-01T00:00:00+00:00",
        }
    ]


def test_fx_json_refuses_unrecognized_fact_schema() -> None:
    facts = [_fx_fact()]
    facts[0]["unknown_field"] = CANARY
    with pytest.raises(ds.DemoSnapshotError) as exc:
        dsf._san_fx_json(json.dumps(facts).encode(), b"seed-1")
    assert exc.value.code == dsf.CODE_FILES_SOURCE_UNSUPPORTED


def test_fx_json_refuses_non_list_top_level() -> None:
    with pytest.raises(ds.DemoSnapshotError) as exc:
        dsf._san_fx_json(b'{"fx": []}', b"seed-1")
    assert exc.value.code == dsf.CODE_FILES_SOURCE_UNSUPPORTED


def _warnings_raw(row_extra: dict | None = None) -> bytes:
    row = {
        "code": "fx.manual_source",
        "provider": "openrouter",
        "model_id": "gpt-4o-mini",
        "endpoint": "chat/completions",
    }
    if row_extra:
        row.update(row_extra)
    return json.dumps({"warnings": [row]}).encode()


def test_warnings_json_projects_closed_fields_and_drops_unknown_row_fields() -> None:
    out = json.loads(dsf._san_warnings_json(_warnings_raw({"note": CANARY}), b"seed-1"))
    assert CANARY not in json.dumps(out)
    assert out["schema"] == dsf.DEMO_SCHEMA_VERSION
    assert out["kind"] == dsf.KIND_WARNINGS_JSON
    assert out["warnings"] == [
        {
            "code": "fx.manual_source",
            "provider": "openrouter",
            "model_id": "gpt-4o-mini",
            "endpoint": "chat/completions",
        }
    ]


def test_warnings_json_refuses_unknown_top_level_key() -> None:
    with pytest.raises(ds.DemoSnapshotError) as exc:
        dsf._san_warnings_json(
            json.dumps({"warnings": [], "extra": CANARY}).encode(), b"seed-1"
        )
    assert exc.value.code == dsf.CODE_FILES_SOURCE_UNSUPPORTED


def test_warnings_json_refuses_unknown_provider() -> None:
    with pytest.raises(ds.DemoSnapshotError) as exc:
        dsf._san_warnings_json(_warnings_raw({"provider": CANARY}), b"seed-1")
    assert exc.value.code == dsf.CODE_FILES_SOURCE_UNSUPPORTED


def test_review_html_and_markdown_emit_exact_neutral_output() -> None:
    raw = ("<html>secret " + CANARY + "</html>").encode()
    assert (
        dsf._sanitize_by_kind(dsf.KIND_REVIEW_HTML, raw, seed=b"seed-1")
        == dsf.NEUTRAL_REVIEW_HTML
    )
    assert (
        dsf._sanitize_by_kind(
            dsf.KIND_MARKDOWN, ("# report " + CANARY).encode(), seed=b"seed-1"
        )
        == dsf.NEUTRAL_MARKDOWN
    )


def test_verify_refuses_malformed_warning_model_id_type() -> None:
    # A tampered stored leaf with a non-string model_id must fail with a
    # finite code, never a raw TypeError escaping the verifier.
    doc = {
        "schema": dsf.DEMO_SCHEMA_VERSION,
        "kind": dsf.KIND_WARNINGS_JSON,
        "warnings": [
            {
                "code": "fx.manual_source",
                "provider": None,
                "model_id": 123,
                "endpoint": None,
            }
        ],
    }
    with pytest.raises(ds.DemoSnapshotError) as exc:
        dsf._verify_json_policy(
            dsf.KIND_WARNINGS_JSON, json.dumps(doc).encode()
        )
    assert exc.value.code == dsf.CODE_FILES_VERIFY_FAILED


# ---------------------------------------------------------------------------
# Per-kind source-valid canary cases (chunk 2: baseline, normalized,
# source manifest, package manifest, llm profiles, job record)
# ---------------------------------------------------------------------------


def _baseline_raw() -> tuple[bytes, str]:
    from slaif_gateway.schemas.catalog_refresh import BaselineDocument

    provider_id = str(uuid.uuid4())
    doc = BaselineDocument.model_validate(
        {
            "schema_version": _EXEC_SCHEMA_VERSION,
            "exported_at": "2026-11-01T00:00:00+00:00",
            "target": {
                "server_host": "db",
                "server_port": 5432,
                "database": "slaif",
                "postgres_version": "16.15",
            },
            "sql_checked": True,
            "counts": {
                "providers": 1,
                "routes": 0,
                "pricing_rules": 0,
                "fx_rates": 0,
            },
            "content_sha256": "ab" * 32,
            "providers": [
                {
                    "id": provider_id,
                    "provider": "openrouter",
                    "display_name": "OpenRouter " + CANARY,
                    "kind": "openai_compatible",
                    "base_url": "https://openrouter.ai/api/v1/" + CANARY,
                    "api_key_env_var": "OPENROUTER_API_KEY",
                    "enabled": True,
                    "timeout_seconds": 120,
                    "max_retries": 2,
                    "created_at": "2026-11-01T00:00:00+00:00",
                    "updated_at": "2026-11-01T00:00:00+00:00",
                }
            ],
            "routes": [],
            "pricing": [],
            "fx": [],
        }
    )
    return json.dumps(doc.model_dump(mode="json")).encode(), provider_id


def test_baseline_document_remaps_ids_and_drops_free_text() -> None:
    raw, provider_id = _baseline_raw()
    out = dsf._san_baseline_document(raw, b"seed-1")
    text = out.decode()
    assert CANARY not in text
    assert provider_id not in text
    doc = json.loads(out)
    assert doc["schema"] == dsf.DEMO_SCHEMA_VERSION
    assert doc["kind"] == dsf.KIND_BASELINE_DOC
    assert doc["target"] == {"postgres_version": "16.15"}
    assert doc["counts"] == {
        "providers": 1,
        "routes": 0,
        "pricing_rules": 0,
        "fx_rates": 0,
    }
    row = doc["providers"][0]
    assert row["provider"] == "openrouter"
    assert row["id"] != provider_id
    dsf._verify_json_policy(dsf.KIND_BASELINE_DOC, out)


def test_baseline_document_refuses_unknown_field() -> None:
    raw, _provider_id = _baseline_raw()
    doc = json.loads(raw)
    doc["extra"] = CANARY
    with pytest.raises(ds.DemoSnapshotError) as exc:
        dsf._san_baseline_document(json.dumps(doc).encode(), b"seed-1")
    assert exc.value.code == dsf.CODE_FILES_SOURCE_UNSUPPORTED


def _normalized_raw() -> bytes:
    return json.dumps(
        {
            "providers": ["openrouter"],
            "fx": None,
            "export_filters": {
                "paired_ready_only": True,
                "ordinary_chat_only": True,
            },
            "export_row_counts": {"routes": 1, "pricing": 1},
            "models": [
                {
                    "provider": "openrouter",
                    "model_id": "gpt-4o-mini",
                    "canonical_model_id": None,
                    "display_name": "GPT-4o mini " + CANARY,
                    "description": CANARY,
                    "endpoints": ["chat/completions"],
                    "input_modalities": ["text"],
                    "output_modalities": ["text"],
                    "context_length": 128000,
                    "max_output_tokens": 16384,
                    "knowledge_cutoff": None,
                    "supports_streaming": True,
                    "supported_parameters": ["temperature"],
                    "capabilities": {"text": True, "streaming": True},
                    "confidence": "high",
                }
            ],
            "pricing_candidates": [
                {
                    "provider": "openrouter",
                    "model_id": "gpt-4o-mini",
                    "endpoint": "chat/completions",
                    "currency": "USD",
                    "input_price_per_1m": "0.15",
                    "cached_input_price_per_1m": None,
                    "output_price_per_1m": "0.60",
                    "reasoning_price_per_1m": None,
                    "request_price": None,
                    "source_url": "https://openrouter.ai/" + CANARY,
                    "source_retrieved_at": None,
                    "pricing_metadata": {"note": CANARY},
                    "notes": CANARY,
                    "ready_for_import": True,
                    "confidence": "high",
                }
            ],
            "route_candidates": [
                {
                    "requested_model": "gpt-4o-mini",
                    "match_type": "exact",
                    "endpoint": "chat/completions",
                    "provider": "openrouter",
                    "upstream_model": "openai/gpt-4o-mini",
                    "priority": 10,
                    "enabled": True,
                    "visible_in_models": True,
                    "supports_streaming": True,
                    "capabilities": {"text": True},
                    "ready_for_import": True,
                    "confidence": "high",
                }
            ],
            "comparison_rows": [{"status": CANARY}],
        }
    ).encode()


def test_normalized_catalog_projects_closed_fields_and_drops_canary() -> None:
    out = dsf._san_normalized_json(_normalized_raw(), b"seed-1")
    assert CANARY not in out.decode()
    doc = json.loads(out)
    assert doc["schema"] == dsf.DEMO_SCHEMA_VERSION
    assert doc["kind"] == dsf.KIND_NORMALIZED_JSON
    assert doc["fx"] is None
    assert doc["comparison_rows"] == {"count": 1}
    assert doc["models"][0]["capabilities"] == {"text": True, "streaming": True}
    assert doc["pricing_candidates"][0]["input_price_per_1m"] == "0.15"
    dsf._verify_json_policy(dsf.KIND_NORMALIZED_JSON, out)


def test_normalized_catalog_refuses_unknown_top_level_key() -> None:
    doc = json.loads(_normalized_raw())
    doc["extra"] = CANARY
    with pytest.raises(ds.DemoSnapshotError) as exc:
        dsf._san_normalized_json(json.dumps(doc).encode(), b"seed-1")
    assert exc.value.code == dsf.CODE_FILES_SOURCE_UNSUPPORTED


def _source_manifest_raw() -> bytes:
    from slaif_gateway.services.provider_catalog_proposal import (
        SUPPORTED_OUTPUT_FILES,
    )

    return json.dumps(
        {
            "sources": [
                {
                    "provider": "openrouter",
                    "source_type": CANARY,
                    "content_hash": "cd" * 32,
                    "retrieved_at": "2026-11-01T00:00:00+00:00",
                    "url": "https://openrouter.ai/" + CANARY,
                    "warnings": [CANARY],
                }
            ],
            "output_files": list(SUPPORTED_OUTPUT_FILES),
            "fx": None,
            "generated_at": "2026-11-01T00:00:00+00:00",
            "extractor_version": "provider_catalog_proposal_v1",
        }
    ).encode()


def test_source_manifest_neutralizes_source_type_and_drops_paths() -> None:
    out = dsf._san_source_manifest(_source_manifest_raw(), b"seed-1")
    assert CANARY not in out.decode()
    doc = json.loads(out)
    assert doc["schema"] == dsf.DEMO_SCHEMA_VERSION
    assert doc["kind"] == dsf.KIND_SOURCE_MANIFEST
    assert doc["sources"][0]["source_type"] == "known"
    assert doc["sources"][0]["content_hash"] == "cd" * 32
    dsf._verify_json_policy(dsf.KIND_SOURCE_MANIFEST, out)


def test_source_manifest_refuses_unknown_extractor_version() -> None:
    doc = json.loads(_source_manifest_raw())
    doc["extractor_version"] = CANARY
    with pytest.raises(ds.DemoSnapshotError) as exc:
        dsf._san_source_manifest(json.dumps(doc).encode(), b"seed-1")
    assert exc.value.code == dsf.CODE_FILES_SOURCE_UNSUPPORTED


def _package_manifest_raw() -> bytes:
    return json.dumps(
        {
            "package_name": "openrouter-chat-text",
            "provider": "openrouter",
            "endpoint_family": "chat",
            "endpoint": "chat/completions",
            "superset_of": ["openrouter-chat-text-base"],
            "includes_packages": ["openrouter-audio"],
            "mode": "proposal",
            "ordinary_chat_only": True,
            "route_rows": 132,
            "pricing_rows": 132,
            "warnings": {CANARY: 2},
            "excluded_counts": {"ambiguous_capability": 1},
            "generated_at": "2026-11-01T00:00:00+00:00",
            "source_manifest": "/tmp/never/" + CANARY,
            "include_deprecated": False,
            "include_ambiguous_capabilities": False,
            "recommendation": CANARY,
            "safety_mode": "strict",
            "audio_input_rows": 0,
            "audio_output_rows": 0,
            "image_input_rows": 0,
            "file_input_rows": 0,
        }
    ).encode()


def test_package_manifest_neutralizes_code_keys_and_drops_paths() -> None:
    out = dsf._san_package_manifest(_package_manifest_raw(), b"seed-1")
    assert CANARY not in out.decode()
    doc = json.loads(out)
    assert doc["schema"] == dsf.DEMO_SCHEMA_VERSION
    assert doc["kind"] == dsf.KIND_PACKAGE_MANIFEST
    assert doc["warnings"] == {"total": 2}
    assert doc["excluded_counts"] == {"total": 1}
    assert doc["route_rows"] == 132
    dsf._verify_json_policy(dsf.KIND_PACKAGE_MANIFEST, out)


def test_package_manifest_refuses_unknown_key() -> None:
    doc = json.loads(_package_manifest_raw())
    doc["extra"] = CANARY
    with pytest.raises(ds.DemoSnapshotError) as exc:
        dsf._san_package_manifest(json.dumps(doc).encode(), b"seed-1")
    assert exc.value.code == dsf.CODE_FILES_SOURCE_UNSUPPORTED


def _llm_profiles_raw() -> bytes:
    return json.dumps(
        {
            "schema_version": 1,
            "profiles": [
                {
                    "profile_id": "operator-" + CANARY.lower(),
                    "revision": 3,
                    "instruction_placement": "preserve",
                    "tool_encoding": "preserve",
                },
                {
                    "profile_id": "acme-codex-profile",
                    "revision": 1,
                    "instruction_placement": "leading_system_developer",
                    "tool_encoding": "native_vllm",
                },
            ],
        }
    ).encode()


def test_llm_profiles_fictionalize_operator_ids() -> None:
    out = dsf._san_llm_profiles(_llm_profiles_raw(), b"seed-1")
    text = out.decode()
    assert CANARY not in text
    assert "acme-codex-profile" not in text
    doc = json.loads(out)
    assert doc["schema"] == dsf.DEMO_SCHEMA_VERSION
    assert doc["kind"] == dsf.KIND_LLM_PROFILES
    assert [p["profile_id"] for p in doc["profiles"]] == [
        "demo-llm-profile-01",
        "demo-llm-profile-02",
    ]
    assert all(
        re.fullmatch(r"[0-9a-f]{64}", p["sha256"]) for p in doc["profiles"]
    )
    dsf._verify_json_policy(dsf.KIND_LLM_PROFILES, out)


def test_llm_profiles_refuses_wrong_schema_version() -> None:
    doc = json.loads(_llm_profiles_raw())
    doc["schema_version"] = 2
    with pytest.raises(ds.DemoSnapshotError) as exc:
        dsf._san_llm_profiles(json.dumps(doc).encode(), b"seed-1")
    assert exc.value.code == dsf.CODE_FILES_SOURCE_UNSUPPORTED


def _job_record_raw() -> dict:
    return {
        "job_id": "ab" * 16,
        "family": "proposal",
        "status": "ready",
        "progress": "import nearly done " + CANARY,
        "dispatch": "confirmed",
        "run_id": "run-2026-11-01-aabbcc",
        "artifact_name": "bundle-" + "cd" * 16,
        "cancel_requested": False,
        "created_at": "2026-11-01T00:00:00+00:00",
        "updated_at": "2026-11-01T06:00:00+00:00",
        "params": {"secret": CANARY},
    }


def test_job_record_neutralizes_progress_and_remaps_ids() -> None:
    out = dsf._sanitize_job_record(json.dumps(_job_record_raw()).encode(), b"seed-1")
    text = out.decode()
    assert CANARY not in text
    assert "ab" * 16 not in text
    doc = json.loads(out)
    assert doc["kind"] == "catalog_job_record"
    assert re.fullmatch(r"[0-9a-f]{32}", doc["job_id"])
    assert doc["job_id"] != "ab" * 16
    assert doc["progress"] == dsf.DEMO_NOTES
    assert doc["error_code"] is None
    assert re.fullmatch(r"demo-run-[0-9a-f]{24}", doc["run_id"])
    assert re.fullmatch(r"bundle-[0-9a-f]{32}", doc["artifact_name"])
    dsf._verify_json_policy(dsf.KIND_JOB_RECORD, out)


def test_job_record_refuses_unknown_status() -> None:
    record = _job_record_raw()
    record["status"] = CANARY
    with pytest.raises(ds.DemoSnapshotError) as exc:
        dsf._sanitize_job_record(json.dumps(record).encode(), b"seed-1")
    assert exc.value.code == dsf.CODE_FILES_SOURCE_UNSUPPORTED


# ---------------------------------------------------------------------------
# Positive configured sealed catalog run: read-only capture, neutral
# display, and the display tree is not an applicable sealed capture.
# ---------------------------------------------------------------------------


def test_capture_sealed_catalog_run_read_only_and_display_not_applicable(
    tmp_path, umask_022
) -> None:
    from typer.testing import CliRunner

    from slaif_gateway.cli.main import app
    from slaif_gateway.services.catalog_refresh import sealing
    from slaif_gateway.services.catalog_refresh.errors import (
        CatalogRefreshSealError,
    )

    fixtures = Path(__file__).resolve().parents[1] / "fixtures" / "catalog_refresh"
    catalog_root = tmp_path / "catalog"
    for sub in ("runs", "uploads", "proposals", "jobs"):
        (catalog_root / sub).mkdir(parents=True)
    catalog_root.chmod(0o700)
    # The seal key is private and lives OUTSIDE the catalog root.
    seal_key = tmp_path / "seal.key"
    result = CliRunner().invoke(
        app,
        [
            "catalog-refresh",
            "review",
            str(fixtures / "bundle-first-install.json"),
            "--first-install",
            "--run-root",
            str(catalog_root / "runs"),
            "--seal-key",
            str(seal_key),
        ],
    )
    # First-install runs are READY_WITH_WARNINGS (exit 10) but fully sealed.
    assert result.exit_code == 10, result.output
    run_dir = catalog_root / "runs" / "fixture-first-install-001"
    assert run_dir.is_dir()

    before = {name: (run_dir / name).read_bytes() for name in sealing.CONTENT_FILES}
    before_meta = {
        name: (run_dir / name).read_bytes() for name in ("manifest.json", "receipt.json")
    }

    config = _config(tmp_path, catalog_root=catalog_root, catalog_seal_key=seal_key)
    seed = b"seed-sealed-run"
    capture = dsf.capture_all(config, _settings(), seed)
    assert "catalog" not in capture.not_configured
    assert len(capture.leaves) == len(sealing.CONTENT_FILES)

    # The source custody is byte-for-byte untouched (worker is read-only).
    for name, data in before.items():
        assert (run_dir / name).read_bytes() == data
    for name, data in before_meta.items():
        assert (run_dir / name).read_bytes() == data

    # Every leaf is a sanitized display copy under the demo run id; the
    # original run id and the sealed report never appear in a display leaf.
    by_name = {leaf.logical_name.rsplit("/", 1)[1]: leaf for leaf in capture.leaves}
    assert set(by_name) == set(sealing.CONTENT_FILES)
    demo_run_id = dsf._demo_run_id(seed, "fixture-first-install-001")
    for name, leaf in by_name.items():
        assert leaf.logical_name == f"catalog/runs/{demo_run_id}/{name}"
        assert "fixture-first-install-001" not in leaf.data.decode("utf-8", "replace")
    assert by_name["REVIEW.html"].data == dsf.NEUTRAL_REVIEW_HTML

    # Write the owned display tree and prove the ORIGINAL seal authority
    # does not authenticate it: the display copy carries no HMAC/apply
    # validity.
    job_dir, _manifest = _seeded_job(tmp_path, config)
    dsf._write_files(job_dir, capture)
    files_dir = job_dir / dsf.FILES_DIR_NAME
    raw_key = catfs.load_seal_key_bytes(seal_key)
    with pytest.raises(CatalogRefreshSealError):
        sealing.load_verified_capture(files_dir, raw_key)

    # Sanity: the same key DOES authenticate the untouched source run.
    captured = sealing.load_verified_capture(run_dir, raw_key)
    assert set(captured.content) == set(sealing.CONTENT_FILES)

    # The private files manifest carries ONLY per-copy (demo) identities:
    # no original run id in any source_ref or leaf binding.
    manifest_bytes = (files_dir / dsf.FILES_MANIFEST_NAME).read_bytes()
    assert b"fixture-first-install-001" not in manifest_bytes


def test_upload_artifact_names_never_reach_private_manifest(tmp_path, umask_022) -> None:
    fixtures = Path(__file__).resolve().parents[1] / "fixtures" / "catalog_refresh"
    catalog_root = tmp_path / "catalog"
    for sub in ("runs", "uploads", "proposals", "jobs"):
        (catalog_root / sub).mkdir(parents=True)
    catalog_root.chmod(0o700)
    seal_key = tmp_path / "seal.key"
    catfs.ensure_seal_key(seal_key)

    original_job = "ab" * 16
    original_artifact = "bundle-" + "cd" * 16
    src_job_dir = catalog_root / "uploads" / original_job
    src_job_dir.mkdir(mode=0o700)
    bundle_bytes = (fixtures / "bundle-refresh-ready.json").read_bytes()
    (src_job_dir / original_artifact).write_bytes(bundle_bytes)
    (src_job_dir / original_artifact).chmod(0o600)

    config = _config(tmp_path, catalog_root=catalog_root, catalog_seal_key=seal_key)
    seed = b"seed-uploads"
    capture = dsf.capture_all(config, _settings(), seed)
    assert "catalog" not in capture.not_configured
    assert len(capture.leaves) == 1

    job_dir, _manifest = _seeded_job(tmp_path, config)
    dsf._write_files(job_dir, capture)
    manifest_bytes = (
        job_dir / dsf.FILES_DIR_NAME / dsf.FILES_MANIFEST_NAME
    ).read_bytes()
    assert original_job.encode() not in manifest_bytes
    assert original_artifact.encode() not in manifest_bytes
    # The source artifact is byte-for-byte untouched (read-only capture).
    assert (src_job_dir / original_artifact).read_bytes() == bundle_bytes

