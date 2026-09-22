"""Objective 180 integration tests: read-only PostgreSQL baseline export.

Covers AP-6 against a real migrated PostgreSQL instance (TEST_DATABASE_URL
or Testcontainers via tests/integration/conftest.py): complete, consistent,
read-only allowlisted export with ordinary private-content canaries (no
free-form notes/metadata at all), deterministic content digests, snapshot
consistency under concurrent writes, keyset pagination beyond one page,
outage safety (never an empty bootstrap), stale/wrong baseline rejection by
the CLI, and offline replay equivalence (live export -> CLI review twice ->
byte-identical artifacts -> verify).

All seeded data is synthetic; the provider string is ``openrouter`` because
the bundle schema enforces KNOWN_PROVIDERS, and the test database is a
disposable task-owned instance, so no real catalog state is touched.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import uuid
from urllib.parse import urlparse
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from typer.testing import CliRunner

from slaif_gateway.cli.catalog_refresh import _baseline_document_bytes
from slaif_gateway.cli.main import app
from slaif_gateway.db.repositories.fx_rates import FxRatesRepository
from slaif_gateway.db.repositories.pricing import PricingRulesRepository
from slaif_gateway.schemas.catalog_refresh import BaselineDocument
from slaif_gateway.schemas.pricing import FxConversionResult
from slaif_gateway.services.catalog_refresh.baseline import (
    canonical_baseline_content,
    export_baseline,
)
from slaif_gateway.services.catalog_refresh.errors import CatalogRefreshBlockedError

from slaif_gateway.services.catalog_refresh.validation import _reciprocal
from slaif_gateway.services.pricing import PricingService
from slaif_gateway.services.pricing_errors import FxRateNotFoundError

runner = CliRunner()

PROVIDER = "openrouter"
BASE_URL = "https://openrouter.example.invalid"
API_KEY_ENV_VAR = "OPENROUTER_API_KEY"
VALID_FROM = datetime(2026, 9, 1, tzinfo=UTC)
GENERATED_AT = "2026-09-22T12:00:00+00:00"
RETRIEVED_AT = "2026-09-22T11:00:00+00:00"

MODELS = ("synthetic/stable-v1", "synthetic/updated-v1", "synthetic/new-v1")
PRICES: dict[str, dict[str, str]] = {
    "synthetic/stable-v1": {"input": "0.5", "output": "2"},
    "synthetic/updated-v1": {"input": "1", "output": "4"},
    "synthetic/new-v1": {"input": "0.1", "output": "0.4"},
}

# Secret markers that must never survive into the exported baseline document.
PROVIDER_SECRET = "sk-or-syntheticproviderkey0001"
ROUTE_SECRET = "sk-route-secret-abc123456789"
METADATA_SECRET = "sk-meta-secret-abcdef123456"
FLOAT_METADATA = "0.97"
# Ordinary private content (not a secret pattern): regex secret redaction is
# not an allowlist for unrelated request/personal content, so the default
# export carries no free-form fields at all and this canary must not appear
# anywhere in the document.
PRIVATE_CANARY = "Synthetic private customer conversation content: sample only."


async def _seed_catalog(database_url: str) -> None:
    """Seed the four allowlisted tables with synthetic rows and fake secrets.

    Idempotent: clears only this task's synthetic rows so the test can be
    re-run against the same task-owned database.
    """
    engine = create_async_engine(database_url, future=True)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "DELETE FROM fx_rates WHERE source = :fx_source"
                ),
                {"fx_source": "https://synthetic.example.invalid/fx"},
            )
            await connection.execute(
                text(
                    "DELETE FROM pricing_rules WHERE provider = :provider"
                    " AND upstream_model = ANY(:models)"
                    " AND source_url = :source_url"
                ),
                {
                    "provider": PROVIDER,
                    "models": list(MODELS),
                    "source_url": f"{BASE_URL}/models",
                },
            )
            await connection.execute(
                text(
                    "DELETE FROM model_routes WHERE (provider = :provider"
                    " AND requested_model = ANY(:models))"
                    " OR (provider = 'openai' AND requested_model LIKE 'synthetic/pad-%')"
                ),
                {"provider": PROVIDER, "models": list(MODELS)},
            )
            await connection.execute(
                text(
                    "DELETE FROM provider_configs WHERE provider = :provider"
                    " AND display_name = :display_name"
                ),
                {"provider": PROVIDER, "display_name": "Synthetic OpenRouter (integration)"},
            )
            await connection.execute(
                text(
                    "INSERT INTO provider_configs (id, provider, display_name, kind, base_url,"
                    " api_key_env_var, enabled, timeout_seconds, max_retries, notes,"
                    " created_at, updated_at) VALUES"
                    " (:id, :provider, 'Synthetic OpenRouter (integration)', 'openai_compatible',"
                    " :base_url, :env_var, true, 300, 2, :notes, now(), now())"
                ),
                {
                    "id": str(uuid.uuid4()),
                    "provider": PROVIDER,
                    "base_url": BASE_URL,
                    "env_var": API_KEY_ENV_VAR,
                    "notes": f"upstream credential {PROVIDER_SECRET} managed by env var {API_KEY_ENV_VAR}; {PRIVATE_CANARY}",
                },
            )
            for model in MODELS:
                prices = PRICES[model]
                await connection.execute(
                    text(
                        "INSERT INTO model_routes (id, requested_model, match_type, endpoint, provider,"
                        " upstream_model, priority, enabled, visible_in_models, supports_streaming,"
                        " capabilities, notes, created_at, updated_at) VALUES"
                        " (:id, :model, 'exact', '/v1/chat/completions', :provider, :model, 100,"
                        " true, true, true, :capabilities, :notes, now(), now())"
                    ),
                    {
                        "id": str(uuid.uuid4()),
                        "model": model,
                        "provider": PROVIDER,
                        "capabilities": json.dumps({"text": True, "streaming": True}),
                        "notes": f"api_key={ROUTE_SECRET}; {PRIVATE_CANARY}",
                    },
                )
                await connection.execute(
                    text(
                        "INSERT INTO pricing_rules (id, provider, upstream_model, endpoint, currency,"
                        " input_price_per_1m, output_price_per_1m, pricing_metadata, valid_from,"
                        " enabled, source_url, created_at, updated_at) VALUES"
                        " (:id, :provider, :model, '/v1/chat/completions', 'EUR', :input_price,"
                        " :output_price, :metadata, :valid_from, true, :source_url, now(), now())"
                    ),
                    {
                        "id": str(uuid.uuid4()),
                        "provider": PROVIDER,
                        "model": model,
                        "input_price": prices["input"],
                        "output_price": prices["output"],
                        "metadata": json.dumps(
                            {
                                "api_key": METADATA_SECRET,
                                "confidence": 0.97,
                                "region": "eu-central",
                                "transcript": PRIVATE_CANARY,
                            }
                        ),
                        "valid_from": VALID_FROM,
                        "source_url": f"{BASE_URL}/models",
                    },
                )
            await connection.execute(
                text(
                    "INSERT INTO fx_rates (id, base_currency, quote_currency, rate, valid_from,"
                    " source, created_at) VALUES"
                    " (:id, 'EUR', 'USD', '1.08', :valid_from, 'https://synthetic.example.invalid/fx', now())"
                ),
                {"id": str(uuid.uuid4()), "valid_from": VALID_FROM},
            )
    finally:
        await engine.dispose()


async def _seed_pad_routes(database_url: str, count: int) -> list[str]:
    """Seed many routes for a second (unselected) provider to force pagination."""
    models = [f"synthetic/pad-{index:04d}" for index in range(count)]
    engine = create_async_engine(database_url, future=True)
    try:
        async with engine.begin() as connection:
            for model in models:
                await connection.execute(
                    text(
                        "INSERT INTO model_routes (id, requested_model, match_type, endpoint, provider,"
                        " upstream_model, priority, enabled, visible_in_models, supports_streaming,"
                        " capabilities, created_at, updated_at) VALUES"
                        " (:id, :model, 'exact', '/v1/chat/completions', 'openai', :model, 100,"
                        " true, true, true, :capabilities, now(), now())"
                    ),
                    {
                        "id": str(uuid.uuid4()),
                        "model": model,
                        "capabilities": json.dumps({"text": True}),
                    },
                )
    finally:
        await engine.dispose()
    return models


async def _counts(database_url: str) -> dict[str, int]:
    engine = create_async_engine(database_url, future=True)
    try:
        async with engine.connect() as connection:
            return {
                name: (
                    await connection.execute(text(f"SELECT COUNT(*) FROM {name}"))
                ).scalar_one()
                for name in (
                    "provider_configs",
                    "model_routes",
                    "pricing_rules",
                    "fx_rates",
                    "audit_log",
                )
            }
    finally:
        await engine.dispose()


def _build_replay_bundle(doc: BaselineDocument) -> dict:
    """Build a full-refresh bundle that mirrors every openrouter baseline row."""
    now_iso = GENERATED_AT
    provenance = {
        "extractor": "integration/1.0",
        "extraction": "deterministic",
    }
    models_payload = []
    routes_payload = []
    pricing_payload = []
    sources_payload = []
    for route in doc.routes:
        if route.provider != PROVIDER or route.requested_model not in MODELS:
            continue
        model = route.requested_model
        models_payload.append(
            {
                "provider": PROVIDER,
                "model": model,
                "display_name": f"Synthetic {model} (integration)",
                "supports_streaming": route.supports_streaming,
                "capabilities": dict(route.capabilities or {}),
                "deprecated": False,
                "provenance": dict(provenance, sources=[f"{PROVIDER}|{model}|openrouter_models_api"]),
                "warnings": [],
            }
        )
        routes_payload.append(
            {
                "provider": PROVIDER,
                "requested_model": route.requested_model,
                "upstream_model": route.upstream_model,
                "match_type": route.match_type,
                "endpoint": route.endpoint,
                "priority": route.priority,
                "enabled": route.enabled,
                "visible_in_models": route.visible_in_models,
                "supports_streaming": route.supports_streaming,
                "capabilities": dict(route.capabilities or {}),
                "provenance": dict(provenance, sources=[f"{PROVIDER}|{model}|openrouter_models_api"]),
                "warnings": [],
            }
        )
    for rule in doc.pricing:
        if rule.provider != PROVIDER or rule.upstream_model not in MODELS:
            continue
        model = rule.upstream_model
        dimensions = []
        for name, value in (
            ("input", rule.input_price_per_1m),
            ("cached_input", rule.cached_input_price_per_1m),
            ("output", rule.output_price_per_1m),
            ("reasoning", rule.reasoning_price_per_1m),
            ("request", rule.request_price),
        ):
            if value is None:
                continue
            dimensions.append(
                {
                    "name": name,
                    "value": str(value),
                    "unit": "per_request" if name == "request" else "per_1m_tokens",
                    "currency": rule.currency,
                }
            )
        pricing_payload.append(
            {
                "provider": PROVIDER,
                "model": model,
                "endpoint": rule.endpoint,
                "currency": rule.currency,
                "dimensions": dimensions,
                "valid_from": rule.valid_from.isoformat(),
                "provenance": dict(provenance, sources=[f"{PROVIDER}|{model}|openrouter_models_api"]),
                "warnings": [],
            }
        )
        # The bundle's source record points at the official models API host
        # and binds offline evidence bytes to the declared digest (the DB
        # base_url is provider configuration, not the bundle's source of
        # truth). Trust must classify as OFFICIAL/VERIFIED for a READY replay.
        evidence = f"integration-offline-evidence:{model}".encode("utf-8")
        sources_payload.append(
            {
                "provider": PROVIDER,
                "model": model,
                "source_kind": "openrouter_models_api",
                "url": "https://openrouter.ai/api/v1/models",
                "retrieved_at": RETRIEVED_AT,
                "published_at": None,
                "content_sha256": hashlib.sha256(evidence).hexdigest(),
                "evidence_b64": base64.b64encode(evidence).decode("ascii"),
                "extractor": "integration/1.0",
                "extraction": "deterministic",
                "required": True,
                "truncated": False,
                "warnings": [],
            }
        )
    return {
        "schema_version": "1",
        "run_id": "obj180-replay-001",
        "generated_at": now_iso,
        "revision": {
            "schema_version": "1",
            "slaif_revision": "obj180-integration-revision",
            "renderer_version": "180.0",
            "policy_version": 1,
        },
        "research": {
            "status": "NOT_RUN",
            "codex_version": "N/A",
            "prompt_version": "N/A",
            "extractor_version": "integration/1.0",
            "tool_version": "integration/1.0",
        },
        "profile": {
            "name": "standard-v1",
            "endpoint": "/v1/chat/completions",
            "supports_streaming": True,
            "local_models_visible": True,
            "capability_allowlist": [],
        },
        "policy": {
            "version": 1,
            "price_change_review": "0.25",
            "fx_change_review": "0.03",
            "source_stale_review_hours": 24,
            "source_stale_blocked_hours": 72,
            "fx_stale_review_days": 3,
            "fx_stale_blocked_days": 7,
        },
        "selection": {"providers": [PROVIDER], "model_include": []},
        "baseline": {
            "mode": "exported_file",
            "exported_at": doc.exported_at.isoformat(),
            "target_database": doc.target.database,
            "postgres_version": doc.target.postgres_version,
            "sql_checked": doc.sql_checked,
            "row_counts": {
                "providers": doc.counts.providers,
                "routes": doc.counts.routes,
                "pricing_rules": doc.counts.pricing_rules,
                "fx_rates": doc.counts.fx_rates,
            },
            "content_sha256": doc.content_sha256,
        },
        "models": models_payload,
        "routes": routes_payload,
        "pricing": pricing_payload,
        "fx": [],
        "sources": sources_payload,
        "notes": "Objective 180 integration replay: mirrors the live exported baseline exactly.",
    }


def test_export_baseline_complete_redacted_and_deterministic(migrated_postgres_url: str) -> None:
    asyncio.run(_seed_catalog(migrated_postgres_url))
    now_a = datetime(2026, 9, 22, 6, 0, tzinfo=UTC)
    now_b = datetime(2026, 9, 22, 7, 30, tzinfo=UTC)
    doc_a = asyncio.run(export_baseline(migrated_postgres_url, now=now_a))
    doc_b = asyncio.run(export_baseline(migrated_postgres_url, now=now_b))

    # Complete and correctly targeted (relative counts: the task database may
    # hold rows from other integration tests in a full session).
    assert doc_a.counts.providers >= 1
    assert doc_a.counts.routes >= len(MODELS)
    assert doc_a.counts.pricing_rules >= len(MODELS)
    assert doc_a.counts.fx_rates >= 1
    assert doc_a.counts.routes == len(doc_a.routes)
    assert doc_a.counts.pricing_rules == len(doc_a.pricing)
    assert doc_a.counts.fx_rates == len(doc_a.fx)
    assert doc_a.counts.providers == len(doc_a.providers)
    assert doc_a.sql_checked is True
    assert doc_a.target.database.endswith("test")
    expected_port = urlparse(migrated_postgres_url).port or 5432
    assert doc_a.target.server_port == expected_port
    assert doc_a.target.postgres_version.startswith("16")
    exported_models = {row.requested_model for row in doc_a.routes}
    assert set(MODELS) <= exported_models
    assert {row.upstream_model for row in doc_a.pricing} >= set(MODELS)
    assert any(row.base_currency == "EUR" and row.quote_currency == "USD" for row in doc_a.fx)
    assert doc_a.providers[0].provider == PROVIDER or any(
        row.provider == PROVIDER for row in doc_a.providers
    )

    # The provider secret ENV VARIABLE NAME is retained (names only)...
    our_provider = next(row for row in doc_a.providers if row.provider == PROVIDER)
    assert our_provider.api_key_env_var == API_KEY_ENV_VAR
    # ...and every seeded secret marker is gone from the whole document.
    document_text = json.dumps(doc_a.model_dump(mode="json"), sort_keys=True)
    for secret in (PROVIDER_SECRET, ROUTE_SECRET, METADATA_SECRET, FLOAT_METADATA):
        assert secret not in document_text

    # R4: no free-form fields exist in the export at all; ordinary private
    # content (not just secret patterns) cannot survive into the document.
    provider_dump = our_provider.model_dump()
    route_dumps = [row.model_dump() for row in doc_a.routes]
    pricing_dumps = [row.model_dump() for row in doc_a.pricing]
    assert "notes_redacted" not in provider_dump and "notes" not in provider_dump
    for dump in route_dumps:
        assert "notes_redacted" not in dump and "notes" not in dump
    for dump in pricing_dumps:
        assert "pricing_metadata" not in dump and "notes_redacted" not in dump
    for canary in (PRIVATE_CANARY, PROVIDER_SECRET, ROUTE_SECRET, METADATA_SECRET, FLOAT_METADATA):
        assert canary not in document_text
    # The exported target is compared against the parsed configured URL, not
    # a hardcoded suffix or port.
    parsed_target = urlparse(migrated_postgres_url)
    assert doc_a.target.server_host == (parsed_target.hostname or "localhost")
    assert doc_a.target.database == (parsed_target.path or "/").lstrip("/")

    # Deterministic content digest: exported_at never enters the digest.
    assert doc_a.exported_at != doc_b.exported_at
    assert doc_a.content_sha256 == doc_b.content_sha256
    assert canonical_baseline_content(doc_a) == canonical_baseline_content(doc_b)


def test_export_baseline_is_read_only(migrated_postgres_url: str) -> None:
    before = asyncio.run(_counts(migrated_postgres_url))
    asyncio.run(export_baseline(migrated_postgres_url, now=datetime.now(UTC)))
    after = asyncio.run(_counts(migrated_postgres_url))
    assert before == after
    assert before["audit_log"] == after["audit_log"]

def test_export_snapshot_is_consistent_under_concurrent_writer(migrated_postgres_url: str) -> None:
    """REPEATABLE READ: an uncommitted concurrent insert must not appear in
    the exported snapshot; after the writer commits, a second export sees it.
    The export itself never reads or writes anything but the four tables."""

    async def scenario() -> tuple[int, int]:
        writer = create_async_engine(migrated_postgres_url, future=True)
        reader_url = migrated_postgres_url
        try:
            async with writer.connect() as writer_conn:
                writer_txn = await writer_conn.begin()
                await writer_conn.execute(
                    text(
                        "INSERT INTO model_routes (id, requested_model, match_type, endpoint,"
                        " provider, upstream_model, priority, enabled, visible_in_models,"
                        " supports_streaming, capabilities, created_at, updated_at) VALUES"
                        " (:id, 'synthetic/concurrent-v1', 'exact', '/v1/chat/completions',"
                        " 'openai', 'synthetic/concurrent-v1', 100, true, true, true,"
                        " :capabilities, now(), now())"
                    ),
                    {"id": str(uuid.uuid4()), "capabilities": json.dumps({"text": True})},
                )
                # Snapshot while the writer's row is uncommitted.
                doc_snapshot = await export_baseline(reader_url, now=datetime.now(UTC))
                # A concurrent second export in the same window is identical
                # (same snapshot semantics, read-only, deterministic rows).
                doc_second = await export_baseline(reader_url, now=datetime.now(UTC))
                assert doc_snapshot.content_sha256 == doc_second.content_sha256
                # The uncommitted row must NOT be visible.
                assert not any(
                    row.requested_model == "synthetic/concurrent-v1" for row in doc_snapshot.routes
                )
                await writer_txn.commit()
            doc_after = await export_baseline(reader_url, now=datetime.now(UTC))
            assert any(
                row.requested_model == "synthetic/concurrent-v1" for row in doc_after.routes
            )
            return (
                sum(1 for row in doc_snapshot.routes if row.requested_model == "synthetic/concurrent-v1"),
                sum(1 for row in doc_after.routes if row.requested_model == "synthetic/concurrent-v1"),
            )
        finally:
            # Cleanup: remove the probe row so re-runs stay idempotent.
            cleanup = create_async_engine(migrated_postgres_url, future=True)
            try:
                async with cleanup.begin() as connection:
                    await connection.execute(
                        text(
                            "DELETE FROM model_routes WHERE provider = 'openai'"
                            " AND requested_model = 'synthetic/concurrent-v1'"
                        )
                    )
            finally:
                await cleanup.dispose()

    before, after = asyncio.run(scenario())
    assert before == 0
    assert after == 1


def test_export_baseline_paginates_beyond_one_page(migrated_postgres_url: str) -> None:
    before = asyncio.run(_counts(migrated_postgres_url))
    pad_models = asyncio.run(_seed_pad_routes(migrated_postgres_url, 600))
    expected_total = before["model_routes"] + 600
    # Default page_size is 500, so a correct export needs at least two pages
    # for model_routes; a silent truncation would trip the consistency check.
    doc = asyncio.run(export_baseline(migrated_postgres_url, now=datetime.now(UTC)))
    assert doc.counts.routes == expected_total
    assert len(doc.routes) == expected_total
    exported_models = {row.requested_model for row in doc.routes}
    assert set(pad_models) <= exported_models


def test_export_baseline_outage_never_bootstraps() -> None:
    with pytest.raises(CatalogRefreshBlockedError) as excinfo:
        asyncio.run(
            export_baseline(
                "postgresql+asyncpg://ubuntu@127.0.0.1:59999/unreachable",
                now=datetime.now(UTC),
            )
        )
    assert excinfo.value.code == "baseline_export_failed"


def test_stale_baseline_file_rejected_by_cli(migrated_postgres_url: str, tmp_path: Path) -> None:
    doc = asyncio.run(export_baseline(migrated_postgres_url, now=datetime.now(UTC)))
    bundle_path = tmp_path / "bundle.json"
    bundle_path.write_text(
        json.dumps(_build_replay_bundle(doc), sort_keys=True, indent=1) + "\n",
        encoding="utf-8",
    )
    # Tamper with one row but keep the original self-declared digest.
    payload = json.loads(_baseline_document_bytes(doc))
    payload["routes"][0]["priority"] = 999
    tampered = tmp_path / "baseline-tampered.json"
    tampered.write_text(json.dumps(payload, sort_keys=True, indent=1) + "\n", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "catalog-refresh",
            "review",
            str(bundle_path),
            "--baseline-file",
            str(tampered),
            "--run-root",
            str(tmp_path / "runs"),
            "--seal-key",
            str(tmp_path / "seal.key"),
        ],
    )
    assert result.exit_code == 65, result.output
    assert "baseline_digest_mismatch" in (result.output + result.stderr)
    assert not (tmp_path / "runs").exists()


def test_cli_export_baseline_round_trip(migrated_postgres_url: str, tmp_path: Path) -> None:
    direct = asyncio.run(export_baseline(migrated_postgres_url, now=datetime.now(UTC)))
    out = tmp_path / "baseline.json"
    result = runner.invoke(
        app,
        [
            "catalog-refresh",
            "export-baseline",
            "--db-url",
            migrated_postgres_url,
            "--out",
            str(out),
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    summary = json.loads(result.stdout)
    assert summary["content_sha256"] == direct.content_sha256
    assert summary["sql_checked"] is True
    assert summary["counts"]["routes"] == direct.counts.routes
    file_payload = json.loads(out.read_text(encoding="utf-8"))
    assert file_payload["content_sha256"] == direct.content_sha256
    # The export must never overwrite existing output.
    again = runner.invoke(
        app,
        [
            "catalog-refresh",
            "export-baseline",
            "--db-url",
            migrated_postgres_url,
            "--out",
            str(out),
        ],
    )
    assert again.exit_code == 65, again.output


def test_offline_replay_equivalence_and_verify(migrated_postgres_url: str, tmp_path: Path) -> None:
    doc = asyncio.run(export_baseline(migrated_postgres_url, now=datetime.now(UTC)))
    bundle_path = tmp_path / "bundle.json"
    bundle_path.write_text(
        json.dumps(_build_replay_bundle(doc), sort_keys=True, indent=1) + "\n",
        encoding="utf-8",
    )
    baseline_path = tmp_path / "baseline.json"
    export = runner.invoke(
        app,
        [
            "catalog-refresh",
            "export-baseline",
            "--db-url",
            migrated_postgres_url,
            "--out",
            str(baseline_path),
        ],
    )
    assert export.exit_code == 0, export.output
    export_payload = json.loads(baseline_path.read_text(encoding="utf-8"))
    assert export_payload["content_sha256"] == doc.content_sha256

    seal_key = tmp_path / "seal.key"
    run_dirs = []
    for index in (1, 2):
        run_root = tmp_path / f"runs-{index}"
        result = runner.invoke(
            app,
            [
                "catalog-refresh",
                "review",
                str(bundle_path),
                "--baseline-file",
                str(baseline_path),
                "--run-root",
                str(run_root),
                "--seal-key",
                str(seal_key),
            ],
        )
        assert result.exit_code == 0, result.output
        assert result.stdout.splitlines()[0] == "state: READY"
        run_dir = run_root / "obj180-replay-001"
        run_dirs.append(run_dir)
        assert (run_dir / "REVIEW.html").is_file()
        assert (run_dir / "receipt.json").is_file()
        # The published baseline is the live export's bytes, not a re-derivation.
        stored = json.loads((run_dir / "catalog-baseline.json").read_text(encoding="utf-8"))
        assert stored["content_sha256"] == doc.content_sha256

    # Two offline replays of the same live export are byte-identical.
    first, second = run_dirs
    for name in ("validation.json", "REVIEW.html", "catalog-refresh.json",
                 "catalog-baseline.json", "routes-proposal.tsv",
                 "pricing-proposal.tsv", "fx-proposal.json", "manifest.json"):
        assert (first / name).read_bytes() == (second / name).read_bytes(), name

    for run_dir in run_dirs:
        verify = runner.invoke(
            app,
            [
                "catalog-refresh",
                "verify",
                "--run-dir",
                str(run_dir),
                "--seal-key",
                str(seal_key),
            ],
        )
        assert verify.exit_code == 0, verify.output
        assert "valid: yes" in verify.stdout
        assert "state: READY" in verify.stdout


def test_fx_normalization_matches_runtime_pricing_lookup(migrated_postgres_url: str) -> None:
    """R2 FX proof: offline normalization must agree with the runtime path.

    Proves, with disposable fx_rates rows and the real
    PricingService.convert_to_eur lookup:
    (a) a USD-denominated price normalized to the canonical native-to-EUR
        pair (USD->EUR) converts at runtime to exactly the expected EUR
        cost;
    (b) the runtime never silently inverts an EUR->USD row, so a USD
        lookup with only the inverse pair present must raise; this is why
        the offline validator derives the reciprocal deterministically
        instead of relabeling a direction;
    (c) the validator reciprocal is deterministic at 9 decimal places
        (ROUND_HALF_UP) and stable under double inversion.
    """
    source = f"obj180b-fx-proof-{uuid.uuid4().hex[:12]}"
    at = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)

    async def _seed(pair: tuple[str, str], rate: str, source_: str) -> uuid.UUID:
        engine = create_async_engine(migrated_postgres_url, future=True)
        try:
            async with engine.begin() as connection:
                row_id = uuid.uuid4()
                await connection.execute(
                    text(
                        "INSERT INTO fx_rates (id, base_currency, quote_currency, rate,"
                        " valid_from, source, created_at) VALUES"
                        " (:id, :base, :quote, :rate, :valid_from, :source, now())"
                    ),
                    {
                        "id": str(row_id),
                        "base": pair[0],
                        "quote": pair[1],
                        "rate": rate,
                        "valid_from": datetime(2026, 1, 1, tzinfo=UTC),
                        "source": source_,
                    },
                )
                return row_id
        finally:
            await engine.dispose()

    async def _cleanup(source_: str) -> None:
        engine = create_async_engine(migrated_postgres_url, future=True)
        try:
            async with engine.begin() as connection:
                await connection.execute(
                    text("DELETE FROM fx_rates WHERE source = :source"),
                    {"source": source_},
                )
        finally:
            await engine.dispose()

    async def _convert_or_raise(
        amount: Decimal, currency: str
    ) -> tuple[Decimal, FxConversionResult]:
        engine = create_async_engine(migrated_postgres_url, future=True)
        try:
            async with engine.connect() as connection:
                transaction = await connection.begin()
                session_factory = async_sessionmaker(
                    bind=connection, class_=AsyncSession, expire_on_commit=False
                )
                try:
                    async with session_factory() as session:
                        service = PricingService(
                            pricing_rules_repository=PricingRulesRepository(session),
                            fx_rates_repository=FxRatesRepository(session),
                        )
                        return await service.convert_to_eur(amount, currency, at=at)
                finally:
                    await transaction.rollback()
        finally:
            await engine.dispose()

    # (a) Canonical native-to-EUR pair: USD->EUR. The emitted normalized
    #     rate must produce exactly the expected EUR cost at runtime.
    seeded = asyncio.run(_seed(("USD", "EUR"), "0.925925926", source))
    try:
        eur_cost, conversion = asyncio.run(_convert_or_raise(Decimal("1.00"), "USD"))
        assert eur_cost == Decimal("0.925925926")
        assert conversion.rate == Decimal("0.925925926")
        assert conversion.from_currency == "USD"
        assert conversion.to_currency == "EUR"
        assert conversion.fx_rate_id == seeded
    finally:
        asyncio.run(_cleanup(source))

    # (b) Only the inverse pair present: the runtime must not invert it.
    inverse_source = f"{source}-inverse"
    asyncio.run(_seed(("EUR", "USD"), "1.08", inverse_source))
    try:
        with pytest.raises(FxRateNotFoundError):
            asyncio.run(_convert_or_raise(Decimal("1.00"), "USD"))
    finally:
        asyncio.run(_cleanup(inverse_source))

    # (c) Deterministic reciprocal: 9dp ROUND_HALF_UP, double-inversion stable.
    assert _reciprocal(Decimal("1.08")) == Decimal("0.925925926")
    assert _reciprocal(_reciprocal(Decimal("1.08"))) == Decimal("1.080000000")
