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
from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from typer.testing import CliRunner

from slaif_gateway.cli.catalog_refresh import _baseline_document_bytes
from slaif_gateway.cli.main import app
from slaif_gateway.config import get_settings
from slaif_gateway.db.repositories.fx_rates import FxRatesRepository
from slaif_gateway.db.repositories.pricing import PricingRulesRepository
from slaif_gateway.schemas.catalog_refresh import BaselineDocument
from slaif_gateway.schemas.pricing import FxConversionResult
from slaif_gateway.services.catalog_refresh.baseline import (
    canonical_baseline_content,
    capabilities_fingerprint,
    export_baseline,
)
from slaif_gateway.services.catalog_refresh.errors import CatalogRefreshBlockedError

from slaif_gateway.services.catalog_refresh.validation import _reciprocal
from slaif_gateway.schemas.catalog_refresh import CAPABILITY_KEYS
from slaif_gateway.services.chat_completion_route_capabilities import (
    ensure_default_chat_completion_capabilities,
)

from tests.unit.test_catalog_refresh_source_evidence import (
    ECB_URL,
    ecb_source_dict,
    openrouter_snapshot_bytes,
)
from slaif_gateway.services.pricing import PricingService
from slaif_gateway.services.pricing_errors import FxRateNotFoundError

runner = CliRunner()

PROVIDER = "openrouter"
BASE_URL = "https://openrouter.example.invalid"
API_KEY_ENV_VAR = "OPENROUTER_API_KEY"
VALID_FROM = datetime(2026, 9, 1, tzinfo=UTC)
GENERATED_AT = "2026-09-22T12:00:00+00:00"
RETRIEVED_AT = "2026-09-22T11:00:00+00:00"
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "catalog_refresh"

MODELS = ("synthetic/stable-v1", "synthetic/updated-v1", "synthetic/new-v1")
# Allowlisted monetary metadata per model (180-e E2): the runtime contract
# fields the baseline must preserve verbatim.
METADATA_BY_MODEL: dict[str, dict] = {
    "synthetic/stable-v1": {
        # a valid RUNTIME codex row: the contract requires EXACTLY ONE
        # cache-write field alongside the full long-context set
        "codex_accounting": {
            "long_context_threshold_tokens": 272000,
            "long_context_input_multiplier": "2.00",
            "long_context_output_multiplier": "3.00",
            "cache_write_input_price_per_1m": "7.50",
        }
    },
    "synthetic/updated-v1": {
        "external_tool_pricing": {
            "openai_web_search_call_price_native": "0.01",
            "source": "openai_published_per_call",
        }
    },
    "synthetic/new-v1": {"audio_output_price_per_1m": "15"},
}
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
                    " OR (provider = 'openai' AND upstream_model = 'synthetic/canary-v1')"
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
                    " OR (provider = 'openai' AND requested_model = 'synthetic/unknown-cap-v1')"
                ),
                {"provider": PROVIDER, "models": list(MODELS)},
            )
            # provider_configs.provider is UNIQUE: converge on the provider
            # identity this seed owns, not only on its display name (another
            # test file may have left a differently-labelled row for the same
            # provider; the seed replaces it, and the file's cleanup removes
            # it by provider identity afterwards).
            await connection.execute(
                text("DELETE FROM provider_configs WHERE provider = :provider"),
                {"provider": PROVIDER},
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
                        # the real runtime nested projection (180-e E1): the
                        # full chat_completions contract block, not a flat map
                        "capabilities": json.dumps(
                            ensure_default_chat_completion_capabilities({}, supports_streaming=True)
                        ),
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
                        # 180-e E2: the allowlisted monetary metadata the
                        # runtime consumes must survive the export verbatim
                        "metadata": json.dumps(METADATA_BY_MODEL[model]),
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
            # A fourth, unselected (openai) pricing row whose metadata is all
            # free-form canary content: the export must flag the row
            # unrepresentable and drop every canary.
            await connection.execute(
                text(
                    "INSERT INTO pricing_rules (id, provider, upstream_model, endpoint, currency,"
                    " input_price_per_1m, output_price_per_1m, pricing_metadata, valid_from,"
                    " enabled, source_url, created_at, updated_at) VALUES"
                    " (:id, 'openai', 'synthetic/canary-v1', '/v1/chat/completions', 'EUR', '0.1',"
                    " '0.4', :metadata, :valid_from, true, :source_url, now(), now())"
                ),
                {
                    "id": str(uuid.uuid4()),
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
            # An unselected (openai) route whose capabilities carry a key
            # outside the recognized contract: exported as unrepresented with
            # an opaque fingerprint, never with the raw value.
            await connection.execute(
                text(
                    "INSERT INTO model_routes (id, requested_model, match_type, endpoint, provider,"
                    " upstream_model, priority, enabled, visible_in_models, supports_streaming,"
                    " capabilities, created_at, updated_at) VALUES"
                    " (:id, 'synthetic/unknown-cap-v1', 'exact', '/v1/chat/completions', 'openai',"
                    " 'synthetic/unknown-cap-v1', 100, true, true, true, :capabilities, now(), now())"
                ),
                {
                    "id": str(uuid.uuid4()),
                    "capabilities": json.dumps(
                        {
                            "chat_completions": {"chat_text": True},
                            "mystery_block": {"free_form_canary": PRIVATE_CANARY},
                        }
                    ),
                },
            )
    finally:
        await engine.dispose()


async def _seed_provider_only(database_url: str) -> None:
    """Seed only the provider identity row (180-f F2 round-trip proof).

    Idempotent: converges the task-owned provider row so the test can be
    re-run against the same task-owned database. The file's autouse cleanup
    removes the provider row and every synthetic route/pricing row again.
    """
    engine = create_async_engine(database_url, future=True)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text("DELETE FROM provider_configs WHERE provider = :provider"),
                {"provider": PROVIDER},
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
    finally:
        await engine.dispose()


async def _fetch_route_capabilities(database_url: str, model: str) -> dict:
    """The ACTUAL stored capabilities JSON of one task-owned route row."""
    engine = create_async_engine(database_url, future=True)
    try:
        async with engine.connect() as connection:
            rows = (
                await connection.execute(
                    text(
                        "SELECT capabilities FROM model_routes"
                        " WHERE provider = :provider AND requested_model = :model"
                    ),
                    {"provider": PROVIDER, "model": model},
                )
            ).mappings().all()
    finally:
        await engine.dispose()
    assert len(rows) == 1, f"expected exactly one route row for {model}, got {len(rows)}"
    value = rows[0]["capabilities"]
    return json.loads(value) if isinstance(value, str) else dict(value)


async def _count_task_rows(database_url: str, table: str, column: str, model: str) -> int:
    engine = create_async_engine(database_url, future=True)
    try:
        async with engine.connect() as connection:
            return (
                await connection.execute(
                    text(
                        f"SELECT COUNT(*) FROM {table}"
                        f" WHERE provider = :provider AND {column} = :model"
                    ),
                    {"provider": PROVIDER, "model": model},
                )
            ).scalar_one()
    finally:
        await engine.dispose()


async def _seed_pad_routes(database_url: str, count: int) -> list[str]:
    """Seed many routes for a second (unselected) provider to force pagination."""
    models = [f"synthetic/pad-{index:04d}" for index in range(count)]
    engine = create_async_engine(database_url, future=True)
    try:
        async with engine.begin() as connection:
            for start in range(0, len(models), 500):
                batch = models[start : start + 500]
                params: dict[str, object] = {}
                value_clauses = []
                for offset, model in enumerate(batch):
                    params[f"id_{offset}"] = str(uuid.uuid4())
                    params[f"model_{offset}"] = model
                    params[f"capabilities_{offset}"] = json.dumps({"text": True})
                    value_clauses.append(
                        f"(:id_{offset}, :model_{offset}, 'exact', '/v1/chat/completions',"
                        f" 'openai', :model_{offset}, 100, true, true, true,"
                        f" :capabilities_{offset}, now(), now())"
                    )
                await connection.execute(
                    text(
                        "INSERT INTO model_routes (id, requested_model, match_type, endpoint,"
                        " provider, upstream_model, priority, enabled, visible_in_models,"
                        " supports_streaming, capabilities, created_at, updated_at) VALUES "
                        + ", ".join(value_clauses)
                    ),
                    params,
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


async def _delete_all_synthetic_rows(database_url: str) -> None:
    """Delete every row this file's seeds can leave behind.

    The CI integration database is session-scoped across test FILES, so no
    synthetic seed row may outlive a test in this file: a later file's
    ``routes list --limit 1000`` scans (and exact-model disable passes)
    assume a small pre-existing route set.
    """
    engine = create_async_engine(database_url, future=True)
    try:
        async with engine.begin() as connection:
            # 180-f (F2): the round-trip proof imports synthetic/chat-v1 in
            # addition to MODELS; every synthetic row of a task-owned
            # provider must be cleaned up by this file's autouse hook.
            await connection.execute(
                text(
                    "DELETE FROM model_routes WHERE (provider = 'openrouter'"
                    " AND requested_model LIKE 'synthetic/%')"
                    " OR (provider = 'openai' AND requested_model LIKE 'synthetic/%')"
                ),
            )
            await connection.execute(
                text(
                    "DELETE FROM pricing_rules WHERE (provider = 'openrouter'"
                    " AND upstream_model LIKE 'synthetic/%')"
                    " OR (provider = 'openai' AND upstream_model LIKE 'synthetic/%')"
                ),
            )
            await connection.execute(
                text(
                    "DELETE FROM fx_rates WHERE source IN"
                    " ('https://synthetic.example.invalid/fx', 'obj180e-barrier-fx')"
                )
            )
            await connection.execute(
                text(
                    "DELETE FROM provider_configs WHERE provider = 'openrouter'"
                )
            )
    finally:
        await engine.dispose()


@pytest.fixture(autouse=True)
def _no_synthetic_rows_left_behind(migrated_postgres_url: str) -> Iterator[None]:
    """The shared CI integration database is session-scoped across files:
    after every test in this file, no synthetic seed row may remain."""
    yield
    asyncio.run(_delete_all_synthetic_rows(migrated_postgres_url))


def _flat_standard_capabilities(nested: dict | None) -> dict:
    """The flat standard-v1 capability keys a proposal may declare, taken
    from the baseline's nested chat_completions projection."""
    block = (nested or {}).get("chat_completions") or {}
    flat: dict[str, bool] = {}
    for key, value in block.items():
        if not isinstance(value, bool) or not key.startswith("chat_"):
            continue
        standard = key.removeprefix("chat_")
        if standard in CAPABILITY_KEYS:
            flat[standard] = value
    return flat


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
    model_prices: dict[str, tuple[str, str]] = {}
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
                "capabilities": _flat_standard_capabilities(route.capabilities),
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
                "capabilities": _flat_standard_capabilities(route.capabilities),
                "provenance": dict(provenance, sources=[f"{PROVIDER}|{model}|openrouter_models_api"]),
                "warnings": [],
            }
        )
    for rule in doc.pricing:
        if rule.provider != PROVIDER or rule.upstream_model not in MODELS:
            continue
        model = rule.upstream_model
        if rule.input_price_per_1m is not None and rule.output_price_per_1m is not None:
            model_prices[model] = (rule.input_price_per_1m, rule.output_price_per_1m)
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
    # One real OpenRouter /models snapshot (official shape, per-token USD
    # at the 1.08 reference quote) carries every priced model. Each bundle
    # source record points at the official models API host and binds the
    # same offline evidence bytes to the declared digest (the DB base_url is
    # provider configuration, not the bundle's source of truth). Repeated
    # references to identical bytes are one observation, not corroboration;
    # trust must classify as OFFICIAL/VERIFIED for a READY replay.
    snapshot = openrouter_snapshot_bytes(model_prices)
    snapshot_digest = hashlib.sha256(snapshot).hexdigest()
    snapshot_b64 = base64.b64encode(snapshot).decode("ascii")
    for model in sorted(model_prices):
        sources_payload.append(
            {
                "provider": PROVIDER,
                "model": model,
                "source_kind": "openrouter_models_api",
                "url": "https://openrouter.ai/api/v1/models",
                "retrieved_at": RETRIEVED_AT,
                "published_at": None,
                "content_sha256": snapshot_digest,
                "evidence_b64": snapshot_b64,
                "extractor": "integration/1.0",
                "extraction": "deterministic",
                "required": True,
                "truncated": False,
                "warnings": [],
            }
        )
    # EUR pricing is normalized through the supplied ECB reference quote
    # (own publisher identity, ecb_reference_xml kind, EUR-based snapshot).
    sources_payload.append(
        ecb_source_dict(
            date_s="2026-09-22",
            rate="1.08",
            retrieved_at=RETRIEVED_AT,
            published_at="2026-09-22T00:00:00+00:00",
        )
    )
    return {
        "schema_version": "1",
        "run_id": "obj180-replay-001",
        "generated_at": now_iso,
        "revision": {
            "schema_version": "1",
            "slaif_revision": "obj180-integration-revision",
            "renderer_version": "180.4",
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
        "fx": [
            {
                "base_currency": "EUR",
                "quote_currency": "USD",
                "rate": "1.08",
                "valid_from": "2026-09-22T00:00:00+00:00",
                "valid_until": None,
                "published_at": "2026-09-22T00:00:00+00:00",
                "source": ECB_URL,
                "provenance": {
                    "extractor": "integration/1.0",
                    "extraction": "deterministic",
                    "sources": ["ecb|EUR-USD|ecb_reference_xml"],
                },
                "warnings": [],
            }
        ],
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
    # Seed one route so the test is self-contained on a clean database;
    # the session-scoped CI database may have no model_routes before this file.
    asyncio.run(_seed_pad_routes(migrated_postgres_url, 1))
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


# --- 180-e E1: nested capability projection against a real database ----------

def test_export_preserves_nested_capabilities_and_flags_unknown_keys(migrated_postgres_url: str) -> None:
    asyncio.run(_seed_catalog(migrated_postgres_url))
    doc = asyncio.run(export_baseline(migrated_postgres_url, now=datetime.now(UTC)))
    document_text = json.dumps(doc.model_dump(mode="json"), sort_keys=True)
    expected_block = ensure_default_chat_completion_capabilities({}, supports_streaming=True)

    for row in doc.routes:
        if row.provider == PROVIDER and row.requested_model in MODELS:
            # the real runtime nested projection is preserved verbatim
            assert row.capabilities == expected_block
            assert row.capabilities_unrepresented is False
            assert row.capabilities_fingerprint == capabilities_fingerprint(expected_block)

    unknown = next(r for r in doc.routes if r.requested_model == "synthetic/unknown-cap-v1")
    assert unknown.capabilities_unrepresented is True
    # the recognized sibling block still projects; the unknown block is dropped
    assert unknown.capabilities == {"chat_completions": {"chat_text": True}}
    assert len(unknown.capabilities_fingerprint) == 64
    assert "mystery_block" not in document_text
    assert PRIVATE_CANARY not in document_text

    canary = next(p for p in doc.pricing if p.upstream_model == "synthetic/canary-v1")
    assert canary.pricing_metadata_unrepresented is True
    assert METADATA_SECRET not in document_text
    assert FLOAT_METADATA not in document_text


def test_export_preserves_allowlisted_monetary_metadata(migrated_postgres_url: str) -> None:
    """E2: the typed monetary metadata the runtime consumes survives the
    export verbatim (audio output price, codex long-context/cache fields,
    selected hosted fee)."""
    asyncio.run(_seed_catalog(migrated_postgres_url))
    doc = asyncio.run(export_baseline(migrated_postgres_url, now=datetime.now(UTC)))
    by_model = {row.upstream_model: row for row in doc.pricing}

    stable = by_model["synthetic/stable-v1"]
    assert stable.pricing_metadata_unrepresented is False
    assert stable.long_context_threshold_tokens == 272000
    assert stable.long_context_input_multiplier == "2.00"
    assert stable.long_context_output_multiplier == "3.00"
    assert stable.cache_write_input_price_per_1m == "7.50"
    assert stable.audio_output_price_per_1m is None

    updated = by_model["synthetic/updated-v1"]
    assert updated.external_tool_price_per_call == "0.01"
    assert updated.external_tool_source == "openai_published_per_call"

    new = by_model["synthetic/new-v1"]
    assert new.audio_output_price_per_1m == "15"


def test_export_metadata_only_difference_changes_the_digest(migrated_postgres_url: str) -> None:
    """E2: a change in an allowlisted monetary metadata field is a change in
    the baseline content (the digest is over the rows, not just prices)."""
    asyncio.run(_seed_catalog(migrated_postgres_url))
    doc_a = asyncio.run(export_baseline(migrated_postgres_url, now=datetime.now(UTC)))

    def set_multiplier(value: str) -> None:
        async def _update() -> None:
            engine = create_async_engine(migrated_postgres_url, future=True)
            try:
                async with engine.begin() as connection:
                    await connection.execute(
                        text(
                            "UPDATE pricing_rules SET pricing_metadata = :metadata"
                            " WHERE provider = :provider AND upstream_model = :model"
                        ),
                        {
                            "metadata": json.dumps(
                                {"codex_accounting": {"long_context_threshold_tokens": 272000,
                                                      "long_context_input_multiplier": value,
                                                      "long_context_output_multiplier": "3.00",
                                                      "cache_write_input_price_per_1m": "7.50"}}
                            ),
                            "provider": PROVIDER,
                            "model": "synthetic/stable-v1",
                        },
                    )
            finally:
                await engine.dispose()

        asyncio.run(_update())

    try:
        set_multiplier("2.10")
        doc_b = asyncio.run(export_baseline(migrated_postgres_url, now=datetime.now(UTC)))
        assert doc_b.content_sha256 != doc_a.content_sha256
        stable_b = next(r for r in doc_b.pricing if r.upstream_model == "synthetic/stable-v1")
        assert stable_b.long_context_input_multiplier == "2.10"
    finally:
        set_multiplier("2.00")


def test_export_fx_label_source_and_free_form_block(migrated_postgres_url: str) -> None:
    """E1: legacy FX sources keep their safe typed label (manual/ecb); a
    free-form source value blocks the export (row identity named, value not)."""
    asyncio.run(_seed_catalog(migrated_postgres_url))

    def add_fx(label: str, quote: str, rate: str) -> uuid.UUID:
        row_id = uuid.uuid4()

        async def _insert() -> None:
            engine = create_async_engine(migrated_postgres_url, future=True)
            try:
                async with engine.begin() as connection:
                    await connection.execute(
                        text(
                            "INSERT INTO fx_rates (id, base_currency, quote_currency, rate, valid_from,"
                            " source, created_at) VALUES (:id, :quote, 'EUR', :rate, :valid_from, :source, now())"
                        ),
                        {"id": row_id, "quote": quote, "rate": rate,
                         "valid_from": VALID_FROM, "source": label},
                    )
            finally:
                await engine.dispose()

        asyncio.run(_insert())
        return row_id

    def drop(row_id: uuid.UUID) -> None:
        async def _delete() -> None:
            engine = create_async_engine(migrated_postgres_url, future=True)
            try:
                async with engine.begin() as connection:
                    await connection.execute(
                        text("DELETE FROM fx_rates WHERE id = :id"), {"id": row_id}
                    )
            finally:
                await engine.dispose()

        asyncio.run(_delete())

    label_id = add_fx("manual", "GBP", "0.85")
    try:
        doc = asyncio.run(export_baseline(migrated_postgres_url, now=datetime.now(UTC)))
        row = next(r for r in doc.fx if r.base_currency == "GBP" and r.quote_currency == "EUR")
        assert row.source is None
        assert row.source_label == "manual"
    finally:
        drop(label_id)

    # free-form: the whole export blocks, naming the row id, never the value
    bad_id = add_fx("see internal memo page 3", "CHF", "1.05")
    try:
        with pytest.raises(CatalogRefreshBlockedError) as excinfo:
            asyncio.run(export_baseline(migrated_postgres_url, now=datetime.now(UTC)))
        assert excinfo.value.code == "baseline_fx_source_unsafe"
        assert "see internal memo" not in excinfo.value.detail
        assert str(bad_id) in excinfo.value.detail
    finally:
        drop(bad_id)


# --- 180-e E2: unrepresented metadata blocks the review ----------------------

def test_unrepresented_baseline_metadata_blocks_cli_review(migrated_postgres_url: str, tmp_path: Path) -> None:
    asyncio.run(_seed_catalog(migrated_postgres_url))
    doc = asyncio.run(export_baseline(migrated_postgres_url, now=datetime.now(UTC)))
    baseline_path = tmp_path / "baseline.json"
    runner.invoke(
        app, ["catalog-refresh", "export-baseline", "--db-url", migrated_postgres_url,
              "--out", str(baseline_path)]
    )
    # flip the selected model's metadata to the unrepresentable flag and
    # re-attest the content digest of the tampered payload (the loader must
    # still accept the document bytes)
    payload = json.loads(baseline_path.read_text(encoding="utf-8"))
    for row in payload["pricing"]:
        if row["upstream_model"] == "synthetic/stable-v1" and row["provider"] == PROVIDER:
            row["pricing_metadata_unrepresented"] = True
    tampered = BaselineDocument.model_validate({**payload, "content_sha256": "0" * 64})
    new_digest = hashlib.sha256(canonical_baseline_content(tampered)).hexdigest()
    payload["content_sha256"] = new_digest
    baseline_path.write_text(json.dumps(payload, sort_keys=True, indent=1) + "\n", encoding="utf-8")

    # the bundle is built against exactly this (tampered) document, so its
    # declared baseline identity carries the tampered content digest
    bundle = _build_replay_bundle(doc)
    bundle["baseline"]["content_sha256"] = new_digest
    bundle_path = tmp_path / "bundle.json"
    bundle_path.write_text(json.dumps(bundle, sort_keys=True, indent=1) + "\n", encoding="utf-8")
    result = runner.invoke(
        app,
        ["catalog-refresh", "review", str(bundle_path),
         "--baseline-file", str(baseline_path),
         "--run-root", str(tmp_path / "runs"),
         "--seal-key", str(tmp_path / "seal.key")],
    )
    assert result.exit_code == 20, result.output
    run_dir = tmp_path / "runs" / "obj180-replay-001"
    validation = json.loads((run_dir / "validation.json").read_text(encoding="utf-8"))
    codes = {w["code"] for w in validation["warnings"]}
    assert "baseline_unrepresented_metadata" in codes
    assert validation["state"] == "BLOCKED"


# --- 180-e E3: observed source facts cannot be bypassed via the CLI ----------

def _replay_bundle_with_snapshot_mutation(doc: BaselineDocument, mutate) -> dict:
    bundle = _build_replay_bundle(doc)
    # rebuild the shared openrouter snapshot with the mutation, re-binding
    # the evidence bytes to every openrouter source record
    model_prices = {
        p.upstream_model: (p.input_price_per_1m, p.output_price_per_1m)
        for p in doc.pricing
        if p.provider == PROVIDER and p.upstream_model in MODELS
    }
    data = json.loads(openrouter_snapshot_bytes(model_prices))
    mutate(data)
    snapshot = (json.dumps(data, sort_keys=True) + "\n").encode("utf-8")
    for source in bundle["sources"]:
        if source["provider"] == PROVIDER:
            source["content_sha256"] = hashlib.sha256(snapshot).hexdigest()
            source["evidence_b64"] = base64.b64encode(snapshot).decode("ascii")
    return bundle


def test_e3_deprecation_reproducer_blocks_cli_review(migrated_postgres_url: str, tmp_path: Path) -> None:
    """Reproducer 1: snapshot deprecation.is_deprecated=true while the
    proposal carries deprecated=false -> BLOCKED (retain-local)."""
    asyncio.run(_seed_catalog(migrated_postgres_url))
    doc = asyncio.run(export_baseline(migrated_postgres_url, now=datetime.now(UTC)))
    baseline_path = tmp_path / "baseline.json"
    runner.invoke(
        app, ["catalog-refresh", "export-baseline", "--db-url", migrated_postgres_url,
              "--out", str(baseline_path)]
    )

    def mutate(data: dict) -> None:
        for row in data["data"]:
            if row["id"] == "synthetic/stable-v1":
                row["deprecation"] = {"is_deprecated": True}

    bundle = _replay_bundle_with_snapshot_mutation(doc, mutate)
    bundle["run_id"] = "obj180e-e3-deprecation"
    bundle_path = tmp_path / "bundle.json"
    bundle_path.write_text(json.dumps(bundle, sort_keys=True, indent=1) + "\n", encoding="utf-8")
    result = runner.invoke(
        app,
        ["catalog-refresh", "review", str(bundle_path),
         "--baseline-file", str(baseline_path),
         "--run-root", str(tmp_path / "runs"),
         "--seal-key", str(tmp_path / "seal.key")],
    )
    assert result.exit_code == 20, result.output
    validation = json.loads(
        (tmp_path / "runs" / "obj180e-e3-deprecation" / "validation.json").read_text(encoding="utf-8")
    )
    codes = {w["code"] for w in validation["warnings"]}
    assert "source_evidence_value_mismatch" in codes
    detail = next(w["detail"] for w in validation["warnings"] if w["code"] == "source_evidence_value_mismatch")
    assert "deprecated" in detail
    assert "retain the local row" in detail
    disp = {d["model"]: d["disposition"] for d in validation["dispositions"]}
    assert disp["synthetic/stable-v1"] == "BLOCKED"


def test_e3_audio_only_reproducer_blocks_cli_review(migrated_postgres_url: str, tmp_path: Path) -> None:
    """Reproducer 2: audio-only modalities (observed text=false) while the
    route claims text -> BLOCKED; effective eligibility cannot bypass the
    observed fact."""
    asyncio.run(_seed_catalog(migrated_postgres_url))
    doc = asyncio.run(export_baseline(migrated_postgres_url, now=datetime.now(UTC)))
    baseline_path = tmp_path / "baseline.json"
    runner.invoke(
        app, ["catalog-refresh", "export-baseline", "--db-url", migrated_postgres_url,
              "--out", str(baseline_path)]
    )

    def mutate(data: dict) -> None:
        for row in data["data"]:
            if row["id"] == "synthetic/stable-v1":
                row["architecture"] = {
                    "input_modalities": ["audio"],
                    "output_modalities": ["audio"],
                }

    bundle = _replay_bundle_with_snapshot_mutation(doc, mutate)
    bundle["run_id"] = "obj180e-e3-audio-only"
    bundle_path = tmp_path / "bundle.json"
    bundle_path.write_text(json.dumps(bundle, sort_keys=True, indent=1) + "\n", encoding="utf-8")
    result = runner.invoke(
        app,
        ["catalog-refresh", "review", str(bundle_path),
         "--baseline-file", str(baseline_path),
         "--run-root", str(tmp_path / "runs"),
         "--seal-key", str(tmp_path / "seal.key")],
    )
    assert result.exit_code == 20, result.output
    validation = json.loads(
        (tmp_path / "runs" / "obj180e-e3-audio-only" / "validation.json").read_text(encoding="utf-8")
    )
    codes = {w["code"] for w in validation["warnings"]}
    assert "source_evidence_value_mismatch" in codes
    detail = next(w["detail"] for w in validation["warnings"] if w["code"] == "source_evidence_value_mismatch")
    assert "model:capability:text" in detail
    disp = {d["model"]: d["disposition"] for d in validation["dispositions"]}
    assert disp["synthetic/stable-v1"] == "BLOCKED"


def test_e3_text_disabled_declaration_on_existing_route_is_visible_change(
    migrated_postgres_url: str, tmp_path: Path
) -> None:
    """180-f (F2) x E3: an audio-only source with BOTH the model and the
    route facts declaring text=false matches the observed fact, so no
    invented value mismatch appears; but on an EXISTING row the explicit
    text denial is a VISIBLE capability change. The refresh shows
    route.capabilities.chat_text as a CHANGED (excluded update) field and
    the create-only import gate blocks the run because no apply operation
    exists - no silent no-op, no silent default expansion."""
    asyncio.run(_seed_catalog(migrated_postgres_url))
    doc = asyncio.run(export_baseline(migrated_postgres_url, now=datetime.now(UTC)))
    baseline_path = tmp_path / "baseline.json"
    runner.invoke(
        app, ["catalog-refresh", "export-baseline", "--db-url", migrated_postgres_url,
              "--out", str(baseline_path)]
    )

    def mutate(data: dict) -> None:
        for row in data["data"]:
            if row["id"] == "synthetic/stable-v1":
                row["architecture"] = {
                    "input_modalities": ["audio"],
                    "output_modalities": ["audio"],
                }

    bundle = _replay_bundle_with_snapshot_mutation(doc, mutate)
    for item in bundle["models"]:
        if item["model"] == "synthetic/stable-v1":
            item["capabilities"] = {"streaming": True, "text": False}
    for item in bundle["routes"]:
        if item["requested_model"] == "synthetic/stable-v1":
            item["capabilities"] = {"streaming": True, "text": False}
    bundle["run_id"] = "obj180f-e3-text-disabled"
    bundle_path = tmp_path / "bundle.json"
    bundle_path.write_text(json.dumps(bundle, sort_keys=True, indent=1) + "\n", encoding="utf-8")
    result = runner.invoke(
        app,
        ["catalog-refresh", "review", str(bundle_path),
         "--baseline-file", str(baseline_path),
         "--run-root", str(tmp_path / "runs"),
         "--seal-key", str(tmp_path / "seal.key")],
    )
    assert result.exit_code == 20, result.output
    validation = json.loads(
        (tmp_path / "runs" / "obj180f-e3-text-disabled" / "validation.json").read_text(encoding="utf-8")
    )
    codes = {w["code"] for w in validation["warnings"]}
    # The declared text=false claim matches the observed audio-only fact:
    # no fabricated value mismatch.
    assert "source_evidence_value_mismatch" not in codes
    # The create-only artifact excludes the update; the gate says so.
    assert "gate:import.routes" in codes
    disp = {d["model"]: d for d in validation["dispositions"]}
    entry = disp["synthetic/stable-v1"]
    assert entry["disposition"] == "CHANGED"
    assert "route.capabilities.chat_text" in entry["detail"]


# --- 180-f F2: create -> import -> export -> refresh round trip -------------

def test_f2_generated_routes_survive_create_export_refresh(
    migrated_postgres_url: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """180-f (F2): the complete local round trip in a fresh task-owned
    database. Generate the valid first-install fixture (READY), dry-run and
    explicitly confirm the deterministic route/pricing imports with an audit
    reason, assert the ACTUAL persisted capabilities (the conservative
    create contract - no permission widening), export the real rows, and
    review the same synthetic source facts again: an honest UNCHANGED no-op
    with header-only artifacts, no unrepresented-capability blocker and no
    duplicate rows. This uses ONLY existing import commands with synthetic
    data in a task-owned test database."""
    import csv as csv_module

    asyncio.run(_seed_provider_only(migrated_postgres_url))
    bundle_path = tmp_path / "bundle.json"
    bundle_path.write_bytes((FIXTURES / "bundle-first-install.json").read_bytes())
    seal_key = tmp_path / "seal.key"
    run_root = tmp_path / "runs"

    # 1) first-install review of the committed fixture: READY.
    result = runner.invoke(
        app,
        ["catalog-refresh", "review", str(bundle_path), "--first-install",
         "--run-root", str(run_root), "--seal-key", str(seal_key)],
    )
    assert result.exit_code == 0, result.output
    run_dir = run_root / "fixture-first-install-001"
    routes_tsv = run_dir / "routes-proposal.tsv"
    pricing_tsv = run_dir / "pricing-proposal.tsv"
    with routes_tsv.open(encoding="utf-8") as fh:
        emitted = next(csv_module.DictReader(fh, delimiter="\t"))
    # The emitted capabilities are the nested runtime shape - the single
    # derived contract - with no stray flat storage keys.
    assert json.loads(emitted["capabilities"]) == {
        "chat_completions": {"chat_streaming": True, "chat_text": True}
    }

    # The import commands resolve the task-owned database from
    # DATABASE_URL; get_settings is lru_cached, so refresh it after the
    # env switch (the established cli_env fixture pattern in this suite).
    monkeypatch.setenv("DATABASE_URL", migrated_postgres_url)
    get_settings.cache_clear()

    # 2) dry-run both imports.
    result = runner.invoke(
        app, ["routes", "import", "--file", str(routes_tsv), "--dry-run", "--json"]
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["valid_count"] == 1 and payload["invalid_count"] == 0
    result = runner.invoke(
        app, ["pricing", "import", "--file", str(pricing_tsv), "--dry-run", "--json"]
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["validated_count"] == 1 and payload["invalid_count"] == 0

    # 3) explicitly confirmed imports with audit reasons.
    result = runner.invoke(
        app,
        ["routes", "import", "--file", str(routes_tsv), "--execute",
         "--confirm-import", "--reason",
         "180-f F2 round-trip proof: confirmed create of synthetic/chat-v1",
         "--json"],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["created_count"] == 1
    result = runner.invoke(
        app,
        ["pricing", "import", "--file", str(pricing_tsv), "--execute",
         "--confirm-import", "--reason",
         "180-f F2 round-trip proof: confirmed pricing for synthetic/chat-v1",
         "--json"],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["created_count"] == 1

    # 4) the ACTUAL persisted capabilities: exactly the conservative create
    # contract - the importer must not have widened permissions.
    stored = asyncio.run(_fetch_route_capabilities(migrated_postgres_url, "synthetic/chat-v1"))
    assert stored == {"chat_completions": {"chat_streaming": True, "chat_text": True}}

    # 5) export the real rows.
    baseline_path = tmp_path / "baseline.json"
    result = runner.invoke(
        app, ["catalog-refresh", "export-baseline", "--db-url", migrated_postgres_url,
              "--out", str(baseline_path)],
    )
    assert result.exit_code == 0, result.output
    baseline_doc = BaselineDocument.model_validate_json(baseline_path.read_bytes())

    # 6) review the same synthetic source facts against the exported rows.
    bundle = json.loads(bundle_path.read_bytes())
    bundle["run_id"] = "fixture-refresh-002"
    bundle["baseline"] = {
        "mode": "exported_file",
        "exported_at": baseline_doc.exported_at.isoformat(),
        "target_database": baseline_doc.target.database,
        "postgres_version": baseline_doc.target.postgres_version,
        "sql_checked": baseline_doc.sql_checked,
        "row_counts": {
            "providers": baseline_doc.counts.providers,
            "routes": baseline_doc.counts.routes,
            "pricing_rules": baseline_doc.counts.pricing_rules,
            "fx_rates": baseline_doc.counts.fx_rates,
        },
        "content_sha256": baseline_doc.content_sha256,
    }
    bundle_path2 = tmp_path / "bundle-refresh.json"
    bundle_path2.write_text(json.dumps(bundle, sort_keys=True, indent=1) + "\n", encoding="utf-8")
    result = runner.invoke(
        app,
        ["catalog-refresh", "review", str(bundle_path2),
         "--baseline-file", str(baseline_path),
         "--run-root", str(run_root), "--seal-key", str(seal_key)],
    )
    # On a fresh CI database this is READY (exit 0). Against a shared
    # session database carrying other files' openrouter rows, the
    # model_disappeared REVIEW findings for those rows make it
    # READY_WITH_WARNINGS (exit 10). Neither may be BLOCKED: the round
    # trip itself must produce no blockers.
    assert result.exit_code in (0, 10), result.output
    validation = json.loads(
        (run_root / "fixture-refresh-002" / "validation.json").read_text(encoding="utf-8")
    )
    assert not any(w["severity"] == "BLOCKER" for w in validation["warnings"])
    codes = {w["code"] for w in validation["warnings"]}
    assert "baseline_unrepresented_capabilities" not in codes
    assert "baseline_unrepresented_metadata" not in codes
    assert "source_observations_contradict" not in codes
    disp = {d["model"]: d for d in validation["dispositions"]}
    assert disp["synthetic/chat-v1"]["disposition"] == "UNCHANGED"
    assert validation["counts"]["changed"] == 0
    # Zero executable rows: header-only route/pricing artifacts.
    for name in ("routes-proposal.tsv", "pricing-proposal.tsv"):
        with (run_root / "fixture-refresh-002" / name).open(encoding="utf-8") as fh:
            row_lines = [line for line in fh.read().splitlines() if line.strip()]
        assert len(row_lines) == 1, f"{name} must be header-only, got {len(row_lines)} line(s)"
    # No duplicate rows: still exactly one route and one pricing row.
    assert asyncio.run(_count_task_rows(migrated_postgres_url, "model_routes", "requested_model", "synthetic/chat-v1")) == 1
    assert asyncio.run(_count_task_rows(migrated_postgres_url, "pricing_rules", "upstream_model", "synthetic/chat-v1")) == 1






# --- 180-e E5: live db_snapshot review + verify replay -----------------------

def test_live_db_snapshot_run_records_live_capture_and_verify_replay(migrated_postgres_url: str, tmp_path: Path) -> None:
    """A db_snapshot review performs the live read-only export itself: the
    published record claims live SQL, and the offline verify replay states
    explicitly that it executed none."""
    asyncio.run(_seed_catalog(migrated_postgres_url))
    doc = asyncio.run(export_baseline(migrated_postgres_url, now=datetime.now(UTC)))
    bundle = _build_replay_bundle(doc)
    bundle["run_id"] = "obj180e-live-001"
    bundle["baseline"]["mode"] = "db_snapshot"
    bundle_path = tmp_path / "bundle.json"
    bundle_path.write_text(json.dumps(bundle, sort_keys=True, indent=1) + "\n", encoding="utf-8")

    result = runner.invoke(
        app,
        ["catalog-refresh", "review", str(bundle_path),
         "--db-url", migrated_postgres_url,
         "--run-root", str(tmp_path / "runs"),
         "--seal-key", str(tmp_path / "seal.key")],
    )
    assert result.exit_code == 0, result.output
    assert result.stdout.splitlines()[0] == "state: READY"
    run_dir = tmp_path / "runs" / "obj180e-live-001"
    validation = json.loads((run_dir / "validation.json").read_text(encoding="utf-8"))
    sql_checks = validation["sql_checks"]
    assert sql_checks["capture"] == "live_export"
    assert sql_checks["sql_executed_during_review"] is True
    assert "live read-only baseline export" in sql_checks["note"]
    html = (run_dir / "REVIEW.html").read_text(encoding="utf-8")
    assert "Capture path (this execution)" in html

    verify = runner.invoke(
        app,
        ["catalog-refresh", "verify", "--run-dir", str(run_dir),
         "--seal-key", str(tmp_path / "seal.key")],
    )
    assert verify.exit_code == 0, verify.output
    assert "valid: yes" in verify.stdout
    assert "state: READY" in verify.stdout
    assert "sql_evidence: replayed from sealed bytes (no SQL executed during verification)" in verify.stdout


# --- 180-e E4: real REPEATABLE READ proof under a committing writer ---------

# Explicit test-only barrier at the exporter's real query/page seam (the
# mandated 180-e design): the wrapper pauses the export at its FIRST
# _page_rows call, which occurs after SET TRANSACTION, the version probe,
# and all four COUNT reads, i.e. after the REPEATABLE READ snapshot is fully
# established. The independent writer commits in the meantime, and the test
# awaits the commit completion before releasing the real reads. No product
# code is changed for the seam; no pg_stat_activity polling, no advisory
# locks, no padding beyond one page-size of headroom.
_BARRIER_PAD_COUNT = 3000


def _barrier_cleanup(database_url: str) -> None:
    async def cleanup() -> None:
        engine = create_async_engine(database_url, future=True)
        try:
            async with engine.begin() as connection:
                await connection.execute(
                    text(
                        "DELETE FROM model_routes WHERE provider = 'openai'"
                        " AND requested_model = 'synthetic/barrier-v1'"
                    )
                )
                await connection.execute(
                    text(
                        "DELETE FROM pricing_rules WHERE provider = 'openai'"
                        " AND upstream_model = 'synthetic/barrier-v1'"
                    )
                )
                await connection.execute(
                    text("DELETE FROM fx_rates WHERE source = 'obj180e-barrier-fx'")
                )
                await connection.execute(
                    text(
                        "DELETE FROM pricing_rules WHERE provider = 'openai'"
                        " AND upstream_model = 'synthetic/canary-v1'"
                    )
                )
        finally:
            await engine.dispose()

    asyncio.run(cleanup())


def _install_export_seam():
    """Test-only barrier at the exporter's real query/page boundary.

    Wraps ``baseline._page_rows`` and delegates every call to the original
    implementation. The first page call happens after the transaction, the
    version probe, and the four count reads, so at that seam the REPEATABLE
    READ snapshot is fully established. The wrapper pauses there until the
    test has committed the independent writer, then releases the real read.
    """
    import slaif_gateway.services.catalog_refresh.baseline as baseline_module

    original = baseline_module._page_rows
    fired = asyncio.Event()
    release = asyncio.Event()
    state = {"fired": False}

    async def seam(connection, table, id_column, columns, expected_count, page_size):
        if not state["fired"]:
            state["fired"] = True
            fired.set()
            await release.wait()
        return await original(connection, table, id_column, columns, expected_count, page_size)

    baseline_module._page_rows = seam

    def restore() -> None:
        baseline_module._page_rows = original

    return fired, release, restore


def _install_isolation_override(isolation: str):
    """Test-only engine injection so the SAME exporter runs another
    isolation level (the negative control). Product isolation is untouched
    and the exporter's query sequence is never reimplemented here."""
    import slaif_gateway.services.catalog_refresh.baseline as baseline_module

    original = baseline_module.create_async_engine

    def overriding(url, **kwargs):
        kwargs["isolation_level"] = isolation
        return original(url, **kwargs)

    baseline_module.create_async_engine = overriding

    def restore() -> None:
        baseline_module.create_async_engine = original

    return restore


async def _commit_barrier_writer(database_url: str) -> None:
    """Independent writer: cross-table writes committed in one transaction.

    The context-manager exit awaits the commit, so when this function
    returns the writes are durable on the server side.
    """
    engine = create_async_engine(database_url, future=True)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO model_routes (id, requested_model, match_type, endpoint,"
                    " provider, upstream_model, priority, enabled, visible_in_models,"
                    " supports_streaming, capabilities, created_at, updated_at) VALUES"
                    " (:id, 'synthetic/barrier-v1', 'exact', '/v1/chat/completions',"
                    " 'openai', 'synthetic/barrier-v1', 100, true, true, true,"
                    " :capabilities, now(), now())"
                ),
                {"id": str(uuid.uuid4()), "capabilities": json.dumps({"text": True})},
            )
            await connection.execute(
                text(
                    "INSERT INTO pricing_rules (id, provider, upstream_model, endpoint,"
                    " currency, input_price_per_1m, output_price_per_1m, valid_from,"
                    " enabled, source_url, created_at, updated_at) VALUES"
                    " (:id, 'openai', 'synthetic/barrier-v1', '/v1/chat/completions',"
                    " 'EUR', '0.1', '0.4', :valid_from, true,'https://synthetic.example.invalid/barrier', now(), now())"
                ),
                {"id": str(uuid.uuid4()), "valid_from": VALID_FROM},
            )
            await connection.execute(
                text(
                    "INSERT INTO fx_rates (id, base_currency, quote_currency, rate,"
                    " valid_from, source, created_at) VALUES"
                    " (:id, 'JPY', 'EUR', '0.0067', :valid_from, 'obj180e-barrier-fx', now())"
                ),
                {"id": str(uuid.uuid4()), "valid_from": VALID_FROM},
            )
            await connection.execute(
                text(
                    "UPDATE pricing_rules SET output_price_per_1m = '0.99'"
                    " WHERE provider = 'openai' AND upstream_model = 'synthetic/canary-v1'"
                )
            )
    finally:
        await engine.dispose()


def test_export_snapshot_is_coherent_when_writer_commits_mid_export(migrated_postgres_url: str) -> None:
    """E4 positive proof: at the exporter's real page seam the independent
    writer commits BETWEEN the snapshot-establishing count reads and the
    first page read. REPEATABLE READ yields one coherent OLD snapshot -
    counts and pages agree per table, the writer's committed rows and the
    updated canary value are absent, and the export wrote nothing - while
    the next export sees the coherent NEW state."""
    asyncio.run(_seed_catalog(migrated_postgres_url))
    asyncio.run(_seed_pad_routes(migrated_postgres_url, _BARRIER_PAD_COUNT))
    before = asyncio.run(_counts(migrated_postgres_url))
    fired, release, restore_seam = _install_export_seam()
    try:
        async def scenario() -> BaselineDocument:
            export_task = asyncio.create_task(
                export_baseline(migrated_postgres_url, now=datetime.now(UTC))
            )
            # the export reached its first real page read: SET TRANSACTION,
            # the version probe, and all four COUNT reads are done, so the
            # REPEATABLE READ snapshot is fully established
            await asyncio.wait_for(fired.wait(), timeout=60)
            # commit the independent writer and AWAIT commit completion
            # before releasing the real reads
            writer_task = asyncio.create_task(_commit_barrier_writer(migrated_postgres_url))
            await asyncio.wait_for(writer_task, timeout=30)
            release.set()
            return await asyncio.wait_for(export_task, timeout=60)

        doc = asyncio.run(scenario())
        # coherent OLD state: the writer's committed writes are absent
        assert doc.counts.providers == before["provider_configs"]
        assert doc.counts.routes == before["model_routes"]
        assert doc.counts.pricing_rules == before["pricing_rules"]
        assert doc.counts.fx_rates == before["fx_rates"]
        # the export's own cross-check (counts == pages) holds per table
        assert len(doc.routes) == doc.counts.routes
        assert len(doc.pricing) == doc.counts.pricing_rules
        assert len(doc.fx) == doc.counts.fx_rates
        assert not any(r.requested_model == "synthetic/barrier-v1" for r in doc.routes)
        assert not any(p.upstream_model == "synthetic/barrier-v1" for p in doc.pricing)
        canary = next(p for p in doc.pricing if p.upstream_model == "synthetic/canary-v1")
        # the writer's UPDATE is unseen (compare values: the column's
        # NUMERIC(18,9) scale padding is not a semantic difference)
        assert Decimal(canary.output_price_per_1m) == Decimal("0.4")
        # the export itself wrote nothing: no audit entries were created
        after = asyncio.run(_counts(migrated_postgres_url))
        assert after["audit_log"] == before["audit_log"]
        # the next export sees the coherent NEW state
        doc2 = asyncio.run(export_baseline(migrated_postgres_url, now=datetime.now(UTC)))
        assert doc2.counts.routes == before["model_routes"] + 1
        assert doc2.counts.pricing_rules == before["pricing_rules"] + 1
        assert doc2.counts.fx_rates == before["fx_rates"] + 1
        assert any(r.requested_model == "synthetic/barrier-v1" for r in doc2.routes)
        assert any(p.upstream_model == "synthetic/barrier-v1" for p in doc2.pricing)
        canary2 = next(p for p in doc2.pricing if p.upstream_model == "synthetic/canary-v1")
        assert Decimal(canary2.output_price_per_1m) == Decimal("0.99")
    finally:
        restore_seam()
        _barrier_cleanup(migrated_postgres_url)


def test_export_snapshot_negative_control_read_committed_mismatches(migrated_postgres_url: str) -> None:
    """E4 negative control: the SAME exporter, forced to READ COMMITTED by
    a test-only engine/isolation injection (no product change, no
    reimplementation of its query sequence), with the independent writer
    committed at the same seam. READ COMMITTED takes a fresh snapshot per
    statement, so the model_routes pages see the committed row while the
    pre-commit COUNT does not, and the exporter's count/page cross-check
    must refuse. This proves the seam-based test exposes a
    non-repeatable implementation."""
    asyncio.run(_seed_catalog(migrated_postgres_url))
    asyncio.run(_seed_pad_routes(migrated_postgres_url, _BARRIER_PAD_COUNT))
    fired, release, restore_seam = _install_export_seam()
    restore_isolation = _install_isolation_override("READ COMMITTED")
    try:
        async def scenario() -> None:
            export_task = asyncio.create_task(
                export_baseline(migrated_postgres_url, now=datetime.now(UTC))
            )
            await asyncio.wait_for(fired.wait(), timeout=60)
            writer_task = asyncio.create_task(_commit_barrier_writer(migrated_postgres_url))
            await asyncio.wait_for(writer_task, timeout=30)
            release.set()
            with pytest.raises(CatalogRefreshBlockedError) as excinfo:
                await asyncio.wait_for(export_task, timeout=60)
            assert excinfo.value.code == "baseline_consistency_mismatch"

        asyncio.run(scenario())
    finally:
        restore_isolation()
        restore_seam()
        _barrier_cleanup(migrated_postgres_url)
