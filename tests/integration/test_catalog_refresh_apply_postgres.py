"""Objective 182 AP1/AP3: atomic apply proven on real PostgreSQL 16.

Run against a disposable owned instance via TEST_DATABASE_URL (the
integration conftest also offers Testcontainers). Proves, with committed
state and real transactions:

- AP1: one authenticated sealed run applies atomically (bootstrap creates
  and refresh supersession), the durable record + audit rows land in the
  SAME transaction, and the CLI surfaces exact exit codes.
- AP3: the SHARE ROW EXCLUSIVE catalog locks serialize (a) other applies
  and (b) ordinary catalog writers, while plain readers keep working;
  identical-bundle retries resolve the prior committed outcome FIRST
  (unchanged actor/effective_at) even after drift; conflicting plans from
  one baseline commit exactly once; injected mid-apply failure rolls every
  part back together; duplicate committed records are refused as ambiguous.

CLI commands run synchronously (they own their asyncio.run), so every
database phase below is a separate asyncio.run with its own engine; the
committed state between phases is the shared truth being proven.
All seeded data is synthetic; no real catalog state is touched.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Awaitable, Callable

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from typer.testing import CliRunner

from slaif_gateway.cli.main import app
from slaif_gateway.db.models import ProviderConfig, FxRate, ModelRoute, PricingRule
from slaif_gateway.services.catalog_refresh import apply as apply_mod
from slaif_gateway.services.catalog_refresh.errors import CatalogRefreshBlockedError

from tests.unit.test_catalog_refresh_source_evidence import (
    ECB_URL,
    ecb_xml_bytes,
    openrouter_snapshot_bytes,
)

pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL is not set; skipping optional PostgreSQL apply tests.",
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "catalog_refresh"
runner = CliRunner()

PROVIDER = "openrouter"
MODEL = "synthetic/itg-182"
UPSTREAM = MODEL
ENDPOINT = "/v1/chat/completions"
OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"
OLD_INPUT, OLD_OUTPUT = "0.25", "1"
NEW_INPUT_A, NEW_INPUT_B = "0.26", "0.27"  # both < 25% review threshold: READY


def _engine(url: str) -> AsyncEngine:
    return create_async_engine(url, pool_pre_ping=True)


def _phase(url: str, fn: Callable[[AsyncEngine], Awaitable[Any]]) -> Any:
    """One committed-state phase: fresh engine, run, dispose."""

    async def _run() -> Any:
        engine = _engine(url)
        try:
            return await fn(engine)
        finally:
            await engine.dispose()

    return asyncio.run(_run())


async def _cleanup(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        for table in (
            "catalog_refresh_applications",
            "audit_log",
            "pricing_rules",
            "model_routes",
            "provider_configs",
            "fx_rates",
            "admin_users",
        ):
            await conn.execute(text(f"DELETE FROM {table}"))


async def _scalar(engine: AsyncEngine, sql: str, *params: Any) -> Any:
    async with engine.connect() as conn:
        return (await conn.execute(text(sql), params)).scalar_one()


async def _rows(engine: AsyncEngine, sql: str, *params: Any) -> list[Any]:
    async with engine.connect() as conn:
        return list((await conn.execute(text(sql), params)).all())


def _iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _provenance() -> dict[str, Any]:
    return {
        "extraction": "deterministic",
        "extractor": "fixture-deterministic/1.0",
        "sources": [f"{PROVIDER}|{MODEL}|openrouter_models_api"],
    }


def _refresh_bundle_bytes(
    *, run_id: str, baseline_doc: dict[str, Any], input_price: str, now: datetime
) -> bytes:
    # the review reference is the bundle's own generated_at: fresh instants
    # sit AT it, and the ECB evidence is re-issued for that date (rate 1.08)
    generated = now - timedelta(hours=1)
    snapshot = openrouter_snapshot_bytes({MODEL: (input_price, OLD_OUTPUT)})
    xml = ecb_xml_bytes(generated.date().isoformat(), "1.08")
    counts = baseline_doc["counts"]
    doc = {
        "schema_version": "1",
        "run_id": run_id,
        "generated_at": _iso(generated),
        "revision": {
            "schema_version": "1",
            "slaif_revision": "itg-182",
            "renderer_version": "182.1",
            "policy_version": 1,
        },
        "research": {
            "status": "NOT_RUN",
            "codex_version": "N/A",
            "prompt_version": "N/A",
            "extractor_version": "fixture/1.0",
            "tool_version": "fixture/1.0",
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
        "profile": {
            "name": "standard-v1",
            "endpoint": ENDPOINT,
            "supports_streaming": True,
            "local_models_visible": True,
            "capability_allowlist": [],
        },
        "selection": {"providers": [PROVIDER], "model_include": [MODEL]},
        "sources": [
            {
                "provider": PROVIDER,
                "model": MODEL,
                "source_kind": "openrouter_models_api",
                "url": OPENROUTER_MODELS_URL,
                "retrieved_at": _iso(generated),
                "published_at": None,
                "content_sha256": hashlib.sha256(snapshot).hexdigest(),
                "evidence_b64": base64.b64encode(snapshot).decode("ascii"),
                "extractor": "fixture-deterministic/1.0",
                "extraction": "deterministic",
                "required": True,
                "truncated": False,
                "warnings": [],
            },
            {
                "provider": "ecb",
                "model": "EUR-USD",
                "source_kind": "ecb_reference_xml",
                "url": ECB_URL,
                "retrieved_at": _iso(generated),
                "published_at": _iso(generated),
                "content_sha256": hashlib.sha256(xml).hexdigest(),
                "evidence_b64": base64.b64encode(xml).decode("ascii"),
                "extractor": "fixture-deterministic/1.0",
                "extraction": "deterministic",
                "required": True,
                "truncated": False,
                "warnings": [],
            }
        ],
        "models": [
            {
                "provider": PROVIDER,
                "model": MODEL,
                "display_name": None,
                "context_length": 128000,
                "max_output_tokens": 8192,
                "supports_streaming": True,
                "capabilities": {"text": True, "streaming": True},
                "deprecated": False,
                "provenance": _provenance(),
                "warnings": [],
            }
        ],
        "pricing": [
            {
                "provider": PROVIDER,
                "model": MODEL,
                "endpoint": ENDPOINT,
                "currency": "EUR",
                "dimensions": [
                    {"currency": "EUR", "name": "input", "unit": "per_1m_tokens", "value": input_price},
                    {"currency": "EUR", "name": "output", "unit": "per_1m_tokens", "value": OLD_OUTPUT},
                ],
                "valid_from": _iso(now - timedelta(days=1)),
                "provenance": _provenance(),
                "warnings": [],
            }
        ],
        "routes": [
            {
                "provider": PROVIDER,
                "requested_model": MODEL,
                "upstream_model": UPSTREAM,
                "match_type": "exact",
                "endpoint": ENDPOINT,
                "priority": 100,
                "enabled": True,
                "visible_in_models": True,
                "supports_streaming": True,
                "capabilities": {"text": True, "streaming": True},
                "provenance": _provenance(),
                "warnings": [],
            }
        ],
        "fx": [
            {
                "base_currency": "EUR",
                "quote_currency": "USD",
                "rate": "1.08",
                "valid_from": _iso(generated),
                "valid_until": None,
                "published_at": _iso(generated),
                "source": ECB_URL,
                "provenance": {
                    "extraction": "deterministic",
                    "extractor": "fixture-deterministic/1.0",
                    "sources": ["ecb|EUR-USD|ecb_reference_xml"],
                },
                "warnings": [],
            }
        ],
        "baseline": {
            "mode": "exported_file",
            "exported_at": baseline_doc["exported_at"],
            "target_database": baseline_doc["target"]["database"],
            "target_host": baseline_doc["target"]["server_host"],
            "target_port": baseline_doc["target"]["server_port"],
            "postgres_version": baseline_doc["target"]["postgres_version"],
            "sql_checked": True,
            "row_counts": {
                "providers": counts["providers"],
                "routes": counts["routes"],
                "pricing_rules": counts["pricing_rules"],
                "fx_rates": counts["fx_rates"],
            },
            "content_sha256": baseline_doc["content_sha256"],
        },
        "notes": None,
    }
    return json.dumps(doc).encode("utf-8")


async def _seed_catalog(
    engine: AsyncEngine, *, input_price: str = OLD_INPUT, output_price: str = OLD_OUTPUT
) -> dict[str, str]:
    """Seed one provider + exact route + one active EUR pricing row."""
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as session:
        now = datetime.now(UTC)
        provider = ProviderConfig(
            provider=PROVIDER,
            display_name=PROVIDER,
            kind="openai_compatible",
            base_url="https://openrouter.example.invalid",
            api_key_env_var="OPENROUTER_API_KEY",
            enabled=True,
            timeout_seconds=300,
            max_retries=2,
            created_at=now,
            updated_at=now,
        )
        route = ModelRoute(
            requested_model=MODEL,
            match_type="exact",
            endpoint=ENDPOINT,
            provider=PROVIDER,
            upstream_model=UPSTREAM,
            priority=100,
            enabled=True,
            visible_in_models=True,
            supports_streaming=True,
            capabilities={
                "chat_completions": {"chat_text": True, "chat_streaming": True}
            },
            created_at=now,
            updated_at=now,
        )
        pricing = PricingRule(
            provider=PROVIDER,
            upstream_model=UPSTREAM,
            endpoint=ENDPOINT,
            currency="EUR",
            input_price_per_1m=Decimal(input_price),
            output_price_per_1m=Decimal(output_price),
            pricing_metadata={},
            valid_from=now - timedelta(days=1),
            enabled=True,
            created_at=now,
            updated_at=now,
        )
        session.add_all([provider, route, pricing])
        await session.commit()
        return {
            "provider": str(provider.id),
            "route": str(route.id),
            "pricing": str(pricing.id),
        }


def _review(args: list[str], tmp_path: Path, sub: str = ""):
    base = tmp_path / sub if sub else tmp_path
    return runner.invoke(
        app,
        ["catalog-refresh", "review", *args,
         "--run-root", str(base / "runs"),
         "--seal-key", str(base / "seal.key")],
    )


def _apply(run_dir: Path, tmp_path: Path, url: str, *, ack: tuple[str, ...] = ()) -> Any:
    return runner.invoke(
        app,
        ["catalog-refresh", "apply",
         "--run-dir", str(run_dir),
         "--db-url", url,
         "--seal-key", str(tmp_path / "seal.key"),
         "--confirm",
         "--actor", "ops@itg",
         "--reason", "itg: apply reviewed plan",
         *([] if not ack else ["--ack-warnings", ",".join(ack)]),
        ],
    )


def _status(run_dir: Path, tmp_path: Path, url: str) -> Any:
    return runner.invoke(
        app,
        ["catalog-refresh", "status",
         "--run-dir", str(run_dir),
         "--db-url", url,
         "--seal-key", str(tmp_path / "seal.key")],
    )


def _seal_key_bytes(tmp_path: Path) -> bytes:
    from slaif_gateway.services.catalog_refresh.filesystem import load_seal_key_bytes

    return load_seal_key_bytes(tmp_path / "seal.key")


def _summary_line(result: Any, prefix: str) -> str:
    for line in result.stdout.splitlines():
        if line.startswith(prefix):
            return line[len(prefix):].strip()
    raise AssertionError(f"missing line {prefix!r} in:\n{result.stdout}")


def _run_dir_for(run_id: str, tmp_path: Path, sub: str = "") -> Path:
    base = tmp_path / sub if sub else tmp_path
    return base / "runs" / run_id


def _fresh_first_install_bundle(tmp_path: Path, run_id: str) -> Path:
    """A first-install bundle with fresh source/FX publication times.

    The tracked fixture is a historical artifact; apply re-evaluates
    freshness against the apply-time wall clock, so the integration proof
    reviews a byte-identical copy whose only delta is fresh retrieval and
    publication instants (content digests and evidence untouched).
    """
    # the review reference instant is the bundle's own generated_at, so the
    # fresh retrieval/publication instants must sit AT it, not after it
    ref = datetime.now(UTC) - timedelta(hours=1)
    fresh = _iso(ref)
    doc = json.loads((FIXTURES / "bundle-first-install.json").read_text(encoding="utf-8"))
    doc["run_id"] = run_id
    doc["generated_at"] = fresh
    # the ECB evidence carries its own date: the XML must be re-issued for
    # the reference date so the published_at binding stays honest
    # (rate unchanged 1.08)
    xml = ecb_xml_bytes(ref.date().isoformat(), "1.08")
    for source in doc["sources"]:
        source["retrieved_at"] = fresh
        if source["provider"] == "ecb":
            source["published_at"] = fresh
            source["content_sha256"] = hashlib.sha256(xml).hexdigest()
            source["evidence_b64"] = base64.b64encode(xml).decode("ascii")
    for fx in doc["fx"]:
        fx["published_at"] = fresh
    path = tmp_path / f"{run_id}.bundle.json"
    path.write_bytes(json.dumps(doc).encode("utf-8"))
    return path


def _export_baseline(tmp_path: Path, url: str, name: str = "baseline.json") -> dict[str, Any]:
    out = tmp_path / name
    export = runner.invoke(
        app,
        ["catalog-refresh", "export-baseline", "--db-url", url, "--out", str(out)],
    )
    assert export.exit_code == 0, export.output
    return json.loads(out.read_text(encoding="utf-8"))


def test_bootstrap_apply_is_atomic_and_retry_is_idempotent(
    migrated_postgres_url: str, tmp_path: Path
) -> None:
    url = migrated_postgres_url
    _phase(url, _cleanup)
    assert _phase(url, lambda e: _scalar(e, "SELECT count(*) FROM provider_configs")) == 0

    bundle_path = _fresh_first_install_bundle(tmp_path, "itg-bootstrap-001")
    result = _review([str(bundle_path), "--first-install"], tmp_path)
    assert result.exit_code == 10, result.output  # RWW: new-model exposure
    run_dir = _run_dir_for("itg-bootstrap-001", tmp_path)
    sealed = json.loads((run_dir / "validation.json").read_text(encoding="utf-8"))
    sealed_plan = sealed["apply_plan"]
    receipt = json.loads((run_dir / "receipt.json").read_text(encoding="utf-8"))

    applied = _apply(run_dir, tmp_path, url, ack=("new_model_exposure",))
    assert applied.exit_code == 0, applied.output
    assert _summary_line(applied, "status:") == "committed"
    effective_at = _summary_line(applied, "effective_at:")

    async def _check(engine: AsyncEngine) -> dict[str, Any]:
        out: dict[str, Any] = {}
        out["providers"] = await _scalar(engine, "SELECT count(*) FROM provider_configs")
        out["routes"] = await _scalar(engine, "SELECT count(*) FROM model_routes")
        out["pricing"] = await _rows(
            engine,
            "SELECT input_price_per_1m, output_price_per_1m, currency, "
            "to_char(valid_from, 'YYYY-MM-DD\"T\"HH24:MI:SS.US\"Z\"') FROM pricing_rules",
        )
        out["fx"] = await _scalar(engine, "SELECT count(*) FROM fx_rates")
        out["records"] = await _rows(
            engine,
            "SELECT run_id, bundle_sha256, plan_sha256, mode, operator_actor, "
            "db_actor, reason, receipt_hmac_sha256, outcome, effective_at "
            "FROM catalog_refresh_applications",
        )
        out["audit_applied"] = await _scalar(
            engine, "SELECT count(*) FROM audit_log WHERE action = 'catalog_refresh_applied'"
        )
        out["current_user"] = await _scalar(engine, "SELECT current_user")
        return out

    state = _phase(url, _check)
    assert state["providers"] == 1
    assert state["routes"] == 1
    assert len(state["pricing"]) == 1
    (price_input, price_output, price_currency, price_valid_from) = state["pricing"][0]
    assert price_input == Decimal("0.25")
    assert price_output == Decimal("1")
    assert price_currency == "EUR"
    assert price_valid_from[:26] == effective_at[:26]  # created at the same T
    assert state["fx"] == 0
    assert len(state["records"]) == 1
    (run_id, bundle_sha, plan_sha, mode, actor, db_actor, reason, hmac, outcome, eff) = (
        state["records"][0]
    )
    assert run_id == "itg-bootstrap-001"
    assert bundle_sha == receipt["semantic_bundle_sha256"]
    assert plan_sha == sealed_plan["plan_sha256"]
    assert mode == "bootstrap"
    assert actor == "ops@itg"
    # the ACTUAL (environment-dependent) database user, not the operator text
    assert db_actor == state["current_user"]
    assert reason == "itg: apply reviewed plan"
    assert hmac == receipt["hmac_sha256"]
    assert outcome == "committed"
    assert eff.isoformat() == effective_at
    assert state["audit_applied"] == 1

    # retry of the SAME sealed run: already_committed, nothing new
    retried = _apply(run_dir, tmp_path, url, ack=("new_model_exposure",))
    assert retried.exit_code == 0, retried.output
    assert _summary_line(retried, "status:") == "already_committed"
    assert _summary_line(retried, "effective_at:") == effective_at

    async def _after_retry(engine: AsyncEngine) -> dict[str, Any]:
        return {
            "providers": await _scalar(engine, "SELECT count(*) FROM provider_configs"),
            "pricing": await _scalar(engine, "SELECT count(*) FROM pricing_rules"),
            "records": await _scalar(
                engine, "SELECT count(*) FROM catalog_refresh_applications"
            ),
            "audit_applied": await _scalar(
                engine, "SELECT count(*) FROM audit_log WHERE action = 'catalog_refresh_applied'"
            ),
        }

    after = _phase(url, _after_retry)
    assert after == {"providers": 1, "pricing": 1, "records": 1, "audit_applied": 1}

    # client-loss recovery: status reports the committed outcome
    st = _status(run_dir, tmp_path, url)
    assert st.exit_code == 0, st.output
    assert _summary_line(st, "committed:") == "true"
    assert _summary_line(st, "run_id:") == "itg-bootstrap-001"
    _phase(url, _cleanup)


def test_refresh_supersession_closes_then_creates_at_one_t(
    migrated_postgres_url: str, tmp_path: Path
) -> None:
    url = migrated_postgres_url
    _phase(url, _cleanup)
    seeded = _phase(url, lambda e: _seed_catalog(e))

    baseline_doc = _export_baseline(tmp_path, url, "baseline-refresh.json")
    now = datetime.now(UTC)
    bundle = _refresh_bundle_bytes(
        run_id="itg-refresh-001",
        baseline_doc=baseline_doc,
        input_price=NEW_INPUT_A,
        now=now,
    )
    bundle_path = tmp_path / "itg-refresh-001.bundle.json"
    bundle_path.write_bytes(bundle)
    reviewed = _review(
        [str(bundle_path), "--baseline-file", str(tmp_path / "baseline-refresh.json")],
        tmp_path,
    )
    assert reviewed.exit_code == 0, reviewed.output  # small move: READY
    run_dir = _run_dir_for("itg-refresh-001", tmp_path)
    sealed = json.loads((run_dir / "validation.json").read_text(encoding="utf-8"))
    sealed_plan = sealed["apply_plan"]
    assert [op["type"] for op in sealed_plan["operations"]] == ["supersede_pricing"]

    applied = _apply(run_dir, tmp_path, url)
    assert applied.exit_code == 0, applied.output
    assert _summary_line(applied, "status:") == "committed"
    effective_at = _summary_line(applied, "effective_at:")

    async def _check(engine: AsyncEngine) -> dict[str, Any]:
        out: dict[str, Any] = {}
        out["pricing_rows"] = await _rows(
            engine,
            "SELECT id::text, "
            "to_char(valid_from, 'YYYY-MM-DD\"T\"HH24:MI:SS.US\"Z\"'), "
            "to_char(valid_until, 'YYYY-MM-DD\"T\"HH24:MI:SS.US\"Z\"'), "
            "input_price_per_1m FROM pricing_rules "
            "ORDER BY valid_from, valid_until NULLS FIRST",
        )
        out["routes"] = await _scalar(engine, "SELECT count(*) FROM model_routes")
        out["providers"] = await _scalar(engine, "SELECT count(*) FROM provider_configs")
        out["fx"] = await _scalar(engine, "SELECT count(*) FROM fx_rates")
        out["record"] = await _rows(
            engine,
            "SELECT mode, superseded_pricing, created_pricing, "
            "applied_pricing_superseded_old_ids, applied_pricing_superseded_new_ids, "
            "effective_at FROM catalog_refresh_applications",
        )
        return out

    state = _phase(url, _check)
    assert state["routes"] == 1 and state["providers"] == 1 and state["fx"] == 0
    rows = state["pricing_rows"]
    assert len(rows) == 2
    old_row, new_row = rows
    assert old_row[0] == seeded["pricing"]
    assert old_row[2][:26] == effective_at[:26]  # closed exactly at T
    assert old_row[3] == Decimal(OLD_INPUT)
    assert new_row[0] != seeded["pricing"]
    assert new_row[1][:26] == effective_at[:26]  # opened exactly at T
    assert new_row[2] is None
    assert new_row[3] == Decimal(NEW_INPUT_A)

    (mode, sup, created, old_ids, new_ids, eff) = state["record"][0]
    assert mode == "refresh"
    assert sup == 1 and created == 0
    assert old_ids == [seeded["pricing"]]
    assert new_ids[0] != seeded["pricing"]
    assert eff.isoformat() == effective_at

    # retry: already committed, the prior T is unchanged
    retried = _apply(run_dir, tmp_path, url)
    assert retried.exit_code == 0, retried.output
    assert _summary_line(retried, "status:") == "already_committed"
    assert _summary_line(retried, "effective_at:") == effective_at
    assert (
        _phase(url, lambda e: _scalar(e, "SELECT count(*) FROM pricing_rules")) == 2
    )
    _phase(url, _cleanup)


def test_apply_refusals_mutate_nothing(migrated_postgres_url: str, tmp_path: Path) -> None:
    url = migrated_postgres_url

    # --- bootstrap into a NON-EMPTY catalog is refused -----------------
    _phase(url, _cleanup)
    _phase(url, lambda e: _seed_catalog(e))
    bundle_path = _fresh_first_install_bundle(tmp_path, "itg-bootstrap-nonempty")
    result = _review([str(bundle_path), "--first-install"], tmp_path)
    assert result.exit_code == 10, result.output
    run_dir = _run_dir_for("itg-bootstrap-nonempty", tmp_path)
    applied = _apply(run_dir, tmp_path, url, ack=("new_model_exposure",))
    assert applied.exit_code == 65, applied.output
    assert "apply_bootstrap_not_empty" in applied.stderr
    assert (
        _phase(url, lambda e: _scalar(e, "SELECT count(*) FROM catalog_refresh_applications"))
        == 0
    )

    # --- stale baseline is refused, drift preserved ---------------------
    _phase(url, _cleanup)
    seeded = _phase(url, lambda e: _seed_catalog(e))
    baseline_doc = _export_baseline(tmp_path, url, "baseline-stale.json")
    bundle = _refresh_bundle_bytes(
        run_id="itg-refresh-stale",
        baseline_doc=baseline_doc,
        input_price=NEW_INPUT_A,
        now=datetime.now(UTC),
    )
    bundle_path = tmp_path / "itg-refresh-stale.bundle.json"
    bundle_path.write_bytes(bundle)
    reviewed = _review(
        [str(bundle_path), "--baseline-file", str(tmp_path / "baseline-stale.json")],
        tmp_path,
    )
    assert reviewed.exit_code == 0, reviewed.output
    run_dir = _run_dir_for("itg-refresh-stale", tmp_path)

    async def _drift(engine: AsyncEngine) -> None:
        async with engine.begin() as conn:
            await conn.execute(
                text("UPDATE pricing_rules SET input_price_per_1m = 0.99 WHERE id = :id"),
                {"id": uuid.UUID(seeded["pricing"])},
            )

    _phase(url, _drift)
    applied = _apply(run_dir, tmp_path, url)
    assert applied.exit_code == 65, applied.output
    assert "apply_baseline_stale" in applied.stderr

    async def _after_stale(engine: AsyncEngine) -> dict[str, Any]:
        return {
            "records": await _scalar(
                engine, "SELECT count(*) FROM catalog_refresh_applications"
            ),
            "pricing": await _scalar(engine, "SELECT count(*) FROM pricing_rules"),
            "value": await _scalar(
                engine,
                "SELECT input_price_per_1m FROM pricing_rules WHERE id = :id",
                {"id": seeded["pricing"]},
            ),
        }

    after = _phase(url, _after_stale)
    assert after["records"] == 0
    assert after["pricing"] == 1
    assert after["value"] == Decimal("0.99")

    # --- unknown admin is refused in-transaction -------------------------
    _phase(url, _cleanup)
    r2 = tmp_path / "r2"
    r2.mkdir()
    r2.chmod(0o700)  # the seal-key boundary requires an owner-only parent
    bundle2 = _fresh_first_install_bundle(r2, "itg-bootstrap-admin")
    result = _review([str(bundle2), "--first-install"], tmp_path, "r2")
    assert result.exit_code == 10, result.output
    run_dir2 = _run_dir_for("itg-bootstrap-admin", tmp_path, "r2")
    applied = runner.invoke(
        app,
        ["catalog-refresh", "apply",
         "--run-dir", str(run_dir2),
         "--db-url", url,
         "--seal-key", str(r2 / "seal.key"),
         "--confirm", "--actor", "ops@itg", "--reason", "itg: admin check",
         "--ack-warnings", "new_model_exposure",
         "--admin-id", str(uuid.uuid4())],
    )
    assert applied.exit_code == 65, applied.output
    assert "apply_admin_unknown" in applied.stderr
    assert _phase(url, lambda e: _scalar(e, "SELECT count(*) FROM provider_configs")) == 0
    _phase(url, _cleanup)


def test_share_row_exclusive_blocks_ordinary_writers_not_readers(
    migrated_postgres_url: str,
) -> None:
    """Real PG16 matrix: while the apply lock mode is held, an ordinary
    catalog INSERT hits the bounded lock_timeout, a plain SELECT succeeds,
    and a second SRE requester is blocked too (serializes with itself)."""
    url = migrated_postgres_url
    _phase(url, _cleanup)

    async def _matrix(engine: AsyncEngine) -> dict[str, Any]:
        out: dict[str, Any] = {}
        async with engine.begin() as holder:
            await holder.execute(text("SET LOCAL lock_timeout = '2s'"))
            await holder.execute(text("SET LOCAL statement_timeout = '10s'"))
            await holder.execute(
                text("LOCK TABLE pricing_rules IN SHARE ROW EXCLUSIVE MODE")
            )
            # plain reader (ACCESS SHARE) is NOT blocked
            async with engine.connect() as reader:
                out["reader_ok"] = (
                    await reader.execute(text("SELECT count(*) FROM pricing_rules"))
                ).scalar_one() == 0
            # second SRE requester conflicts with itself
            async with engine.connect() as second:
                async with second.begin():
                    await second.execute(text("SET LOCAL lock_timeout = '1s'"))
                    with pytest.raises(DBAPIError):
                        await second.execute(
                            text("LOCK TABLE pricing_rules IN SHARE ROW EXCLUSIVE MODE")
                        )
            # ordinary writer (ROW EXCLUSIVE) is blocked within its bound
            now = datetime.now(UTC)
            insert_error: str | None = None
            async with engine.connect() as writer:
                try:
                    async with writer.begin():
                        await writer.execute(text("SET LOCAL lock_timeout = '1s'"))
                        await writer.execute(
                            text(
                                "INSERT INTO pricing_rules (id, provider, "
                                "upstream_model, endpoint, currency, "
                                "input_price_per_1m, output_price_per_1m, "
                                "pricing_metadata, valid_from, enabled, "
                                "created_at, updated_at) VALUES "
                                "(:id, :p, :m, :e, 'EUR', 1, 1, '{}'::jsonb, "
                                ":vf, true, :n, :n)"
                            ),
                            {
                                "id": uuid.uuid4(),
                                "p": PROVIDER,
                                "m": "synthetic/locktest",
                                "e": ENDPOINT,
                                "vf": now - timedelta(days=1),
                                "n": now,
                            },
                        )
                except DBAPIError as exc:
                    insert_error = str(exc).lower()
            out["insert_error"] = insert_error
            out["rows_after"] = await _scalar(engine, "SELECT count(*) FROM pricing_rules")
        return out

    out = _phase(url, _matrix)
    assert out["reader_ok"] is True
    assert out["insert_error"] is not None
    assert (
        "lock timeout" in out["insert_error"]
        or "55p03" in out["insert_error"]
        or "could not obtain lock" in out["insert_error"]
    ), out["insert_error"]
    assert out["rows_after"] == 0
    _phase(url, _cleanup)


def test_conflicting_plans_from_one_baseline_commit_exactly_once(
    migrated_postgres_url: str, tmp_path: Path
) -> None:
    url = migrated_postgres_url
    _phase(url, _cleanup)
    _phase(url, lambda e: _seed_catalog(e))
    baseline_doc = _export_baseline(tmp_path, url, "baseline-race.json")
    now = datetime.now(UTC)
    for run_id, new_input in (("itg-race-a", NEW_INPUT_A), ("itg-race-b", NEW_INPUT_B)):
        bundle = _refresh_bundle_bytes(
            run_id=run_id, baseline_doc=baseline_doc, input_price=new_input, now=now
        )
        path = tmp_path / f"{run_id}.bundle.json"
        path.write_bytes(bundle)
        reviewed = _review(
            [str(path), "--baseline-file", str(tmp_path / "baseline-race.json")],
            tmp_path,
        )
        assert reviewed.exit_code == 0, reviewed.output

    key = _seal_key_bytes(tmp_path)
    run_a = _run_dir_for("itg-race-a", tmp_path)
    run_b = _run_dir_for("itg-race-b", tmp_path)

    async def _apply_service(run_dir: Path) -> Any:
        return await apply_mod.apply_reviewed_run(
            run_dir=run_dir,
            seal_key=key,
            database_url=url,
            reason="itg: race",
            actor="ops@itg",
        )

    async def _race(engine: AsyncEngine) -> dict[str, Any]:
        outcomes = await asyncio.gather(
            _apply_service(run_a), _apply_service(run_b), return_exceptions=True
        )
        committed = [o for o in outcomes if isinstance(o, apply_mod.ApplyResult)
                     and o.status == "committed"]
        blocked = [o for o in outcomes if isinstance(o, CatalogRefreshBlockedError)]
        out: dict[str, Any] = {
            "committed": committed,
            "blocked": blocked,
            "other": [o for o in outcomes
                      if not isinstance(o, (apply_mod.ApplyResult, CatalogRefreshBlockedError))],
            "records": await _rows(
                engine,
                "SELECT run_id, operator_actor, effective_at FROM catalog_refresh_applications",
            ),
            "pricing_count": await _scalar(engine, "SELECT count(*) FROM pricing_rules"),
        }
        return out

    state = _phase(url, _race)
    assert len(state["committed"]) == 1, state["other"] or state["blocked"]
    assert len(state["blocked"]) == 1, state
    assert state["blocked"][0].code == "apply_baseline_stale", state["blocked"]
    assert not state["other"]
    winner = state["committed"][0]
    assert len(state["records"]) == 1
    assert state["records"][0][0] == winner.run_id
    assert state["records"][0][1] == "ops@itg"
    assert state["pricing_count"] == 2  # old closed + winner's new row

    # the LOSER bundle is a DIFFERENT reviewed plan: it must NOT be
    # resolved as idempotent, and re-running it stays refused
    loser_run = run_b if winner.run_id == "itg-race-a" else run_a
    winner_run = run_a if winner.run_id == "itg-race-a" else run_b

    async def _retries(engine: AsyncEngine) -> dict[str, Any]:
        loser_error: CatalogRefreshBlockedError | None = None
        try:
            await _apply_service(loser_run)
        except CatalogRefreshBlockedError as exc:
            loser_error = exc
        retry = await _apply_service(winner_run)
        return {
            "loser": loser_error,
            "retry": retry,
            "records": await _scalar(
                engine, "SELECT count(*) FROM catalog_refresh_applications"
            ),
        }

    after = _phase(url, _retries)
    assert after["loser"] is not None
    assert after["loser"].code == "apply_baseline_stale"
    retry = after["retry"]
    assert retry.status == "already_committed"
    assert retry.run_id == winner.run_id
    assert retry.effective_at == winner.effective_at
    assert retry.record["operator_actor"] == "ops@itg"
    assert retry.record["effective_at"] == winner.effective_at
    assert after["records"] == 1
    _phase(url, _cleanup)


def test_mid_apply_failure_rolls_back_everything(
    migrated_postgres_url: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    url = migrated_postgres_url
    _phase(url, _cleanup)
    bundle_path = _fresh_first_install_bundle(tmp_path, "itg-bootstrap-rollback")
    result = _review([str(bundle_path), "--first-install"], tmp_path)
    assert result.exit_code == 10, result.output
    run_dir = _run_dir_for("itg-bootstrap-rollback", tmp_path)
    key = _seal_key_bytes(tmp_path)

    async def _boom(self, *args: Any, **kwargs: Any) -> None:
        raise RuntimeError("injected mid-apply failure")

    monkeypatch.setattr(apply_mod.PricingRuleService, "create_pricing_rule", _boom)

    async def _run(engine: AsyncEngine) -> None:
        await apply_mod.apply_reviewed_run(
            run_dir=run_dir,
            seal_key=key,
            database_url=url,
            reason="itg: rollback proof",
            actor="ops@itg",
            ack_warnings=("new_model_exposure",),
        )

    with pytest.raises(CatalogRefreshBlockedError) as excinfo:
        _phase(url, _run)
    assert excinfo.value.code == "apply_database_error"
    # the provider and route ops ALREADY executed in-transaction before
    # the failure: every part must have rolled back together
    async def _check(engine: AsyncEngine) -> dict[str, Any]:
        return {
            "providers": await _scalar(engine, "SELECT count(*) FROM provider_configs"),
            "routes": await _scalar(engine, "SELECT count(*) FROM model_routes"),
            "pricing": await _scalar(engine, "SELECT count(*) FROM pricing_rules"),
            "records": await _scalar(
                engine, "SELECT count(*) FROM catalog_refresh_applications"
            ),
            "audit": await _scalar(engine, "SELECT count(*) FROM audit_log"),
        }

    assert _phase(url, _check) == {
        "providers": 0, "routes": 0, "pricing": 0, "records": 0, "audit": 0
    }
    _phase(url, _cleanup)


def test_duplicate_committed_records_are_refused_as_ambiguous(
    migrated_postgres_url: str, tmp_path: Path
) -> None:
    url = migrated_postgres_url
    _phase(url, _cleanup)
    bundle_path = _fresh_first_install_bundle(tmp_path, "itg-bootstrap-dup")
    result = _review([str(bundle_path), "--first-install"], tmp_path)
    assert result.exit_code == 10, result.output
    run_dir = _run_dir_for("itg-bootstrap-dup", tmp_path)
    applied = _apply(run_dir, tmp_path, url, ack=("new_model_exposure",))
    assert applied.exit_code == 0, applied.output
    effective_at = _summary_line(applied, "effective_at:")

    async def _inject_anomaly(engine: AsyncEngine) -> None:
        record = (await _rows(
            engine,
            "SELECT run_id, bundle_sha256, receipt_hmac_sha256, effective_at, "
            "db_actor FROM catalog_refresh_applications",
        ))[0]
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO catalog_refresh_applications (id, run_id, "
                    "bundle_sha256, receipt_hmac_sha256, plan_sha256, mode, "
                    "operator_actor, db_actor, reason, effective_at, outcome, "
                    "created_at) VALUES (:id, :run_id, :bundle, :hmac, :plan, "
                    "'bootstrap', 'ops@itg', :db_actor, 'anomaly', "
                    ":eff, 'committed', :now)"
                ),
                {
                    "id": uuid.uuid4(),
                    "run_id": record[0],
                    "bundle": record[1],
                    "hmac": record[2],
                    "db_actor": record[4],
                    "plan": "f" * 64,
                    "eff": record[3],
                    "now": datetime.now(UTC),
                },
            )

    _phase(url, _inject_anomaly)

    async def _retry(engine: AsyncEngine) -> None:
        await apply_mod.apply_reviewed_run(
            run_dir=run_dir,
            seal_key=key_bytes,
            database_url=url,
            reason="itg: duplicate guard",
            actor="ops@itg",
            ack_warnings=("new_model_exposure",),
        )

    key_bytes = _seal_key_bytes(tmp_path)
    with pytest.raises(CatalogRefreshBlockedError) as excinfo:
        _phase(url, _retry)
    assert excinfo.value.code == "apply_duplicate_record"
    assert _summary_line(applied, "effective_at:") == effective_at
    _phase(url, _cleanup)
# ---------------------------------------------------------------------------
# Objective 182-b: both-provider USD-native bootstrap with the required
# derived FX, simultaneous price+FX supersession over a reviewed finite
# future window, FX rollback, real-executor concurrency, and recoverable
# outcomes. Source fixtures are minimal internally consistent captured
# official-source bytes (OpenRouter /models JSON, OpenAI pricing-docs
# markdown, ECB reference XML); no real GET, provider key, or SQL beyond
# the owned disposable database.
# ---------------------------------------------------------------------------

OAI_PROVIDER = "openai"
OAI_MODEL = "gpt-5.2-itg-182b"  # v1 OpenAI doc rows bind the legacy ID allowlist
OPENAI_PRICING_URL = "https://developers.openai.com/api/docs/pricing.md"
OR_INPUT, OR_OUTPUT = "0.27", "1.08"        # USD per 1M (bootstrap)
OR_INPUT_B = "0.28"                          # USD per 1M (refresh; small move)
OAI_INPUT, OAI_OUTPUT = "0.54", "2.16"       # USD per 1M (unchanged by refresh)
RETAINED_MODEL = "synthetic/itg-retained"    # seeded but NOT selected
FX_OLD, FX_NEW = "1.08", "1.05"              # ECB EUR->USD reference rates
FX_OLD_EUR = Decimal("0.925925926")          # 1/1.08 at 9-decimal precision
FX_NEW_EUR = Decimal("0.952380952")          # 1/1.05 at 9-decimal precision


def _per_token_usd(per_1m_usd: str) -> str:
    """Per-million USD -> exact per-token USD fixed-point string."""
    return format(Decimal(per_1m_usd) / Decimal(10**6), "f")


def _openrouter_snapshot_bytes_usd(model_prices: dict[str, tuple[str, str]]) -> bytes:
    """OpenRouter /models payload with direct USD per-1M prices (the source
    evidence says exactly the proposed USD values)."""
    data = []
    for model in sorted(model_prices):
        input_usd, output_usd = model_prices[model]
        data.append(
            {
                "id": model,
                "context_length": 128000,
                "architecture": {"input_modalities": ["text"], "output_modalities": ["text"]},
                "top_provider": {"max_completion_tokens": 8192},
                "deprecation": {"is_deprecated": False},
                "pricing": {
                    "prompt": _per_token_usd(input_usd),
                    "completion": _per_token_usd(output_usd),
                    "input_cache_read": _per_token_usd(
                        format(Decimal(input_usd) / Decimal(10), "f")
                    ),
                },
            }
        )
    return (json.dumps({"data": data}, sort_keys=True) + "\n").encode("utf-8")


def _openai_pricing_docs_bytes(rows: dict[str, tuple[str, str]]) -> bytes:
    """Official OpenAI pricing-docs markdown table (USD per 1M, text
    modality; no cached-input column, so nothing is invented)."""
    lines = [
        "# Pricing",
        "",
        "| Model | Modality | Input | Cached input | Output |",
        "|---|---|---|---|---|",
    ]
    for model in sorted(rows):
        input_usd, output_usd = rows[model]
        lines.append(f"| {model} | text | ${input_usd} | - | ${output_usd} |")
    return ("\n".join(lines) + "\n").encode("utf-8")


def _usd_source_record(
    provider: str,
    model: str,
    source_kind: str,
    url: str,
    evidence: bytes,
    generated: datetime,
    *,
    published: datetime | None = None,
) -> dict[str, Any]:
    return {
        "provider": provider,
        "model": model,
        "source_kind": source_kind,
        "url": url,
        "retrieved_at": _iso(generated),
        "published_at": _iso(published) if published is not None else None,
        "content_sha256": hashlib.sha256(evidence).hexdigest(),
        "evidence_b64": base64.b64encode(evidence).decode("ascii"),
        "extractor": "fixture-deterministic/1.0",
        "extraction": "deterministic",
        "required": True,
        "truncated": False,
        "warnings": [],
    }


def _first_install_baseline_block() -> dict[str, Any]:
    return {
        "mode": "first_install",
        "exported_at": None,
        "target_database": None,
        "target_host": None,
        "target_port": None,
        "postgres_version": None,
        "sql_checked": False,
        "row_counts": {},
        "content_sha256": None,
    }


def _baseline_block_from_doc(baseline_doc: dict[str, Any]) -> dict[str, Any]:
    counts = baseline_doc["counts"]
    return {
        "mode": "exported_file",
        "exported_at": baseline_doc["exported_at"],
        "target_database": baseline_doc["target"]["database"],
        "target_host": baseline_doc["target"]["server_host"],
        "target_port": baseline_doc["target"]["server_port"],
        "postgres_version": baseline_doc["target"]["postgres_version"],
        "sql_checked": True,
        "row_counts": {
            "providers": counts["providers"],
            "routes": counts["routes"],
            "pricing_rules": counts["pricing_rules"],
            "fx_rates": counts["fx_rates"],
        },
        "content_sha256": baseline_doc["content_sha256"],
    }


def _usd_bundle_bytes(
    *,
    run_id: str,
    baseline_block: dict[str, Any],
    or_input: str,
    fx_rate: str,
    now: datetime,
) -> bytes:
    """One both-provider USD bundle: OpenRouter + OpenAI models with native
    USD prices and the ECB-derived USD->EUR FX fact (direct EUR->USD quote,
    reciprocal derived by the validator)."""
    generated = now - timedelta(hours=1)
    or_snapshot = _openrouter_snapshot_bytes_usd({MODEL: (or_input, OR_OUTPUT)})
    oai_docs = _openai_pricing_docs_bytes({OAI_MODEL: (OAI_INPUT, OAI_OUTPUT)})
    xml = ecb_xml_bytes(generated.date().isoformat(), fx_rate)
    doc = {
        "schema_version": "1",
        "run_id": run_id,
        "generated_at": _iso(generated),
        "revision": {
            "schema_version": "1",
            "slaif_revision": "itg-182b",
            "renderer_version": "182.1",
            "policy_version": 1,
        },
        "research": {
            "status": "NOT_RUN",
            "codex_version": "N/A",
            "prompt_version": "N/A",
            "extractor_version": "fixture/1.0",
            "tool_version": "fixture/1.0",
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
        "profile": {
            "name": "standard-v1",
            "endpoint": ENDPOINT,
            "supports_streaming": True,
            "local_models_visible": True,
            "capability_allowlist": [],
        },
        "selection": {
            "providers": [OAI_PROVIDER, PROVIDER],
            "model_include": [OAI_MODEL, MODEL],
        },
        "sources": [
            _usd_source_record(
                PROVIDER, MODEL, "openrouter_models_api", OPENROUTER_MODELS_URL,
                or_snapshot, generated,
            ),
            _usd_source_record(
                OAI_PROVIDER, OAI_MODEL, "openai_pricing_docs", OPENAI_PRICING_URL,
                oai_docs, generated, published=generated,
            ),
            _usd_source_record(
                "ecb", "EUR-USD", "ecb_reference_xml", ECB_URL,
                xml, generated, published=generated,
            ),
        ],
        "models": [
            {
                "provider": OAI_PROVIDER,
                "model": OAI_MODEL,
                "display_name": None,
                "context_length": None,
                "max_output_tokens": None,
                "supports_streaming": True,
                "capabilities": {"text": True},
                "deprecated": False,
                "provenance": {
                    "extraction": "deterministic",
                    "extractor": "fixture-deterministic/1.0",
                    "sources": [f"{OAI_PROVIDER}|{OAI_MODEL}|openai_pricing_docs"],
                },
                "warnings": [],
            },
            {
                "provider": PROVIDER,
                "model": MODEL,
                "display_name": None,
                "context_length": 128000,
                "max_output_tokens": 8192,
                "supports_streaming": True,
                "capabilities": {"text": True, "streaming": True},
                "deprecated": False,
                "provenance": {
                    "extraction": "deterministic",
                    "extractor": "fixture-deterministic/1.0",
                    "sources": [f"{PROVIDER}|{MODEL}|openrouter_models_api"],
                },
                "warnings": [],
            },
        ],
        "pricing": [
            {
                "provider": OAI_PROVIDER,
                "model": OAI_MODEL,
                "endpoint": ENDPOINT,
                "currency": "USD",
                "dimensions": [
                    {"currency": "USD", "name": "input", "unit": "per_1m_tokens", "value": OAI_INPUT},
                    {"currency": "USD", "name": "output", "unit": "per_1m_tokens", "value": OAI_OUTPUT},
                ],
                "valid_from": _iso(now - timedelta(days=1)),
                "provenance": {
                    "extraction": "deterministic",
                    "extractor": "fixture-deterministic/1.0",
                    "sources": [f"{OAI_PROVIDER}|{OAI_MODEL}|openai_pricing_docs"],
                },
                "warnings": [],
            },
            {
                "provider": PROVIDER,
                "model": MODEL,
                "endpoint": ENDPOINT,
                "currency": "USD",
                "dimensions": [
                    {"currency": "USD", "name": "input", "unit": "per_1m_tokens", "value": or_input},
                    {"currency": "USD", "name": "output", "unit": "per_1m_tokens", "value": OR_OUTPUT},
                ],
                "valid_from": _iso(now - timedelta(days=1)),
                "provenance": {
                    "extraction": "deterministic",
                    "extractor": "fixture-deterministic/1.0",
                    "sources": [f"{PROVIDER}|{MODEL}|openrouter_models_api"],
                },
                "warnings": [],
            },
        ],
        "routes": [
            {
                "provider": OAI_PROVIDER,
                "requested_model": OAI_MODEL,
                "upstream_model": OAI_MODEL,
                "match_type": "exact",
                "endpoint": ENDPOINT,
                "priority": 100,
                "enabled": True,
                "visible_in_models": True,
                "supports_streaming": True,
                "capabilities": {"text": True},
                "provenance": {
                    "extraction": "deterministic",
                    "extractor": "fixture-deterministic/1.0",
                    "sources": [f"{OAI_PROVIDER}|{OAI_MODEL}|openai_pricing_docs"],
                },
                "warnings": [],
            },
            {
                "provider": PROVIDER,
                "requested_model": MODEL,
                "upstream_model": UPSTREAM,
                "match_type": "exact",
                "endpoint": ENDPOINT,
                "priority": 100,
                "enabled": True,
                "visible_in_models": True,
                "supports_streaming": True,
                "capabilities": {"text": True, "streaming": True},
                "provenance": {
                    "extraction": "deterministic",
                    "extractor": "fixture-deterministic/1.0",
                    "sources": [f"{PROVIDER}|{MODEL}|openrouter_models_api"],
                },
                "warnings": [],
            },
        ],
        "fx": [
            {
                "base_currency": "EUR",
                "quote_currency": "USD",
                "rate": fx_rate,
                "valid_from": _iso(generated),
                "valid_until": None,
                "published_at": _iso(generated),
                "source": ECB_URL,
                "provenance": {
                    "extraction": "deterministic",
                    "extractor": "fixture-deterministic/1.0",
                    "sources": ["ecb|EUR-USD|ecb_reference_xml"],
                },
                "warnings": [],
            },
        ],
        "baseline": baseline_block,
        "notes": None,
    }
    return json.dumps(doc).encode("utf-8")


async def _seed_catalog_usd(engine: AsyncEngine) -> dict[str, str]:
    """Seed both providers, both selected models, one UNSELECTED retained
    model, and the USD->EUR FX row. The selected OpenRouter pricing row
    carries a reviewed finite FUTURE validity end."""
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as session:
        now = datetime.now(UTC)
        providers = [
            ProviderConfig(
                provider=p,
                display_name=p,
                kind="openai_compatible",
                base_url=f"https://{p}.example.invalid",
                api_key_env_var=f"{p.upper()}_UPSTREAM_API_KEY",
                enabled=True,
                timeout_seconds=300,
                max_retries=2,
                created_at=now,
                updated_at=now,
            )
            for p in (OAI_PROVIDER, PROVIDER)
        ]
        routes = [
            ModelRoute(
                requested_model=m,
                match_type="exact",
                endpoint=ENDPOINT,
                provider=p,
                upstream_model=m,
                priority=100,
                enabled=True,
                visible_in_models=True,
                supports_streaming=True,
                capabilities={
                    "chat_completions": {"chat_text": True, "chat_streaming": True}
                },
                created_at=now,
                updated_at=now,
            )
            for p, m in (
                (OAI_PROVIDER, OAI_MODEL),
                (PROVIDER, MODEL),
                (PROVIDER, RETAINED_MODEL),
            )
        ]
        pricing_rows = [
            PricingRule(
                provider=PROVIDER,
                upstream_model=MODEL,
                endpoint=ENDPOINT,
                currency="USD",
                input_price_per_1m=Decimal(OR_INPUT),
                output_price_per_1m=Decimal(OR_OUTPUT),
                pricing_metadata={},
                valid_from=now - timedelta(days=1),
                valid_until=now + timedelta(days=30),  # reviewed finite future end
                enabled=True,
                created_at=now,
                updated_at=now,
            ),
            PricingRule(
                provider=OAI_PROVIDER,
                upstream_model=OAI_MODEL,
                endpoint=ENDPOINT,
                currency="USD",
                input_price_per_1m=Decimal(OAI_INPUT),
                output_price_per_1m=Decimal(OAI_OUTPUT),
                pricing_metadata={},
                valid_from=now - timedelta(days=1),
                valid_until=None,
                enabled=True,
                created_at=now,
                updated_at=now,
            ),
            PricingRule(
                provider=PROVIDER,
                upstream_model=RETAINED_MODEL,
                endpoint=ENDPOINT,
                currency="USD",
                input_price_per_1m=Decimal("0.10"),
                output_price_per_1m=Decimal("0.40"),
                pricing_metadata={},
                valid_from=now - timedelta(days=1),
                valid_until=None,
                enabled=True,
                created_at=now,
                updated_at=now,
            ),
        ]
        session.add_all(providers + routes + pricing_rows)
        await session.flush()
        fx = FxRate(
            base_currency="USD",
            quote_currency="EUR",
            rate=FX_OLD_EUR,
            valid_from=now - timedelta(days=1),
            valid_until=None,
            source=ECB_URL,
        )
        session.add(fx)
        await session.commit()
        return {
            "provider_openai": str(providers[0].id),
            "provider_openrouter": str(providers[1].id),
            "route_oai": str(routes[0].id),
            "route_or": str(routes[1].id),
            "route_retained": str(routes[2].id),
            "pricing_model": str(pricing_rows[0].id),
            "pricing_oai": str(pricing_rows[1].id),
            "pricing_retained": str(pricing_rows[2].id),
            "pricing_model_until": pricing_rows[0].valid_until,
            "fx": str(fx.id),
        }


def _review_usd_refresh_run(
    tmp_path: Path, url: str, run_id: str, or_input: str, fx_rate: str
) -> Path:
    """Seed the USD catalog, export the baseline, review the price+FX
    refresh bundle. Returns the sealed run dir (exit 0 expected)."""
    _phase(url, _cleanup)
    _phase(url, lambda e: _seed_catalog_usd(e))
    baseline_doc = _export_baseline(tmp_path, url, f"baseline-{run_id}.json")
    bundle = _usd_bundle_bytes(
        run_id=run_id,
        baseline_block=_baseline_block_from_doc(baseline_doc),
        or_input=or_input,
        fx_rate=fx_rate,
        now=datetime.now(UTC),
    )
    path = tmp_path / f"{run_id}.bundle.json"
    path.write_bytes(bundle)
    reviewed = _review(
        [str(path), "--baseline-file", str(tmp_path / f"baseline-{run_id}.json")],
        tmp_path,
    )
    assert reviewed.exit_code == 0, reviewed.output
    return _run_dir_for(run_id, tmp_path)


def test_bootstrap_both_providers_usd_creates_required_fx(
    migrated_postgres_url: str, tmp_path: Path
) -> None:
    url = migrated_postgres_url
    _phase(url, _cleanup)
    now = datetime.now(UTC)
    bundle = _usd_bundle_bytes(
        run_id="itg182b-bootstrap",
        baseline_block=_first_install_baseline_block(),
        or_input=OR_INPUT,
        fx_rate=FX_OLD,
        now=now,
    )
    bundle_path = tmp_path / "itg182b-bootstrap.bundle.json"
    bundle_path.write_bytes(bundle)
    result = _review([str(bundle_path), "--first-install"], tmp_path)
    assert result.exit_code == 10, result.output  # new-model exposure warnings
    run_dir = _run_dir_for("itg182b-bootstrap", tmp_path)
    sealed = json.loads((run_dir / "validation.json").read_text(encoding="utf-8"))
    sealed_plan = sealed["apply_plan"]
    ops = sealed_plan["operations"]

    # exact sealed plan identities/operations (canonical order)
    assert [op["type"] for op in ops] == [
        "create_provider", "create_provider", "create_route", "create_route",
        "create_pricing", "create_pricing", "create_fx",
    ]
    assert [op["provider"] for op in ops[:2]] == [OAI_PROVIDER, PROVIDER]
    assert [(op["provider"], op["requested_model"], op["upstream_model"])
            for op in ops[2:4]] == [
        (OAI_PROVIDER, OAI_MODEL, OAI_MODEL), (PROVIDER, MODEL, UPSTREAM),
    ]
    assert [(op["provider"], op["model"], op["currency"], op["dimensions"])
            for op in ops[4:6]] == [
        (OAI_PROVIDER, OAI_MODEL, "USD", {"input": OAI_INPUT, "output": OAI_OUTPUT}),
        (PROVIDER, MODEL, "USD", {"input": OR_INPUT, "output": OR_OUTPUT}),
    ]
    (fx_op,) = ops[6:]
    assert fx_op == {
        "type": "create_fx",
        "base_currency": "USD",
        "quote_currency": "EUR",
        "rate": str(FX_OLD_EUR),
        "source": ECB_URL,
        "published_at": (now - timedelta(hours=1)).astimezone(UTC).isoformat(),
        "derived_reciprocal": True,
        "source_pair": "EUR-USD",
        "new_valid_from": "effective_t",
    }

    applied = _apply(run_dir, tmp_path, url, ack=("new_model_exposure",))
    assert applied.exit_code == 0, applied.output
    assert _summary_line(applied, "status:") == "committed"
    effective_at = _summary_line(applied, "effective_at:")

    async def _check(engine: AsyncEngine) -> dict[str, Any]:
        out: dict[str, Any] = {}
        out["providers"] = await _rows(
            engine, "SELECT provider, enabled FROM provider_configs ORDER BY provider"
        )
        out["routes"] = await _scalar(engine, "SELECT count(*) FROM model_routes")
        out["pricing"] = await _rows(
            engine,
            "SELECT id::text, provider, upstream_model, currency, input_price_per_1m, "
            "output_price_per_1m, source_url, "
            "to_char(valid_from, 'YYYY-MM-DD\"T\"HH24:MI:SS.US\"Z\"') "
            "FROM pricing_rules ORDER BY provider, upstream_model",
        )
        out["fx"] = await _rows(
            engine,
            "SELECT id::text, base_currency, quote_currency, rate, source, "
            "to_char(valid_from, 'YYYY-MM-DD\"T\"HH24:MI:SS.US\"Z\"'), valid_until "
            "FROM fx_rates",
        )
        out["record"] = await _rows(
            engine,
            "SELECT run_id, bundle_sha256, plan_sha256, mode, operator_actor, "
            "db_actor, receipt_hmac_sha256, outcome, effective_at, "
            "applied_provider_ids, applied_route_ids, applied_pricing_created_ids, "
            "applied_fx_created_ids, created_providers, created_routes, "
            "created_pricing, created_fx FROM catalog_refresh_applications",
        )
        out["audit_applied"] = await _scalar(
            engine, "SELECT count(*) FROM audit_log WHERE action = 'catalog_refresh_applied'"
        )
        out["current_user"] = await _scalar(engine, "SELECT current_user")
        return out

    state = _phase(url, _check)
    assert state["providers"] == [
        (OAI_PROVIDER, True), (PROVIDER, True),
    ]
    assert state["routes"] == 2
    assert len(state["pricing"]) == 2
    (oai_row, or_row) = state["pricing"]
    assert oai_row[1] == OAI_PROVIDER and oai_row[2] == OAI_MODEL
    assert oai_row[3] == "USD"
    assert (oai_row[4], oai_row[5]) == (Decimal(OAI_INPUT), Decimal(OAI_OUTPUT))
    assert oai_row[6] == OPENAI_PRICING_URL
    assert or_row[1] == PROVIDER and or_row[2] == MODEL
    assert or_row[3] == "USD"
    assert (or_row[4], or_row[5]) == (Decimal(OR_INPUT), Decimal(OR_OUTPUT))
    assert or_row[6] == OPENROUTER_MODELS_URL
    # one effective T for BOTH new pricing rows
    assert oai_row[7][:26] == effective_at[:26]
    assert or_row[7][:26] == effective_at[:26]
    # the bootstrap created the REQUIRED FX: USD->EUR, one T, exact rate
    assert len(state["fx"]) == 1
    (fx_id, fx_base, fx_quote, fx_rate, fx_source, fx_vf, fx_vu) = state["fx"][0]
    assert (fx_base, fx_quote) == ("USD", "EUR")
    assert fx_rate == FX_OLD_EUR
    assert fx_source == ECB_URL
    assert fx_vu is None
    assert fx_vf[:26] == effective_at[:26]

    (run_id, bundle_sha, plan_sha, mode, actor, db_actor, hmac, outcome, eff,
     prov_ids, route_ids, pricing_ids, fx_ids,
     c_prov, c_route, c_pricing, c_fx) = state["record"][0]
    assert run_id == "itg182b-bootstrap"
    receipt = json.loads((run_dir / "receipt.json").read_text(encoding="utf-8"))
    assert bundle_sha == receipt["semantic_bundle_sha256"]
    assert plan_sha == sealed_plan["plan_sha256"]
    assert hmac == receipt["hmac_sha256"]
    assert mode == "bootstrap"
    assert actor == "ops@itg"
    assert db_actor == state["current_user"]
    assert outcome == "committed"
    assert eff.isoformat() == effective_at
    assert (c_prov, c_route, c_pricing, c_fx) == (2, 2, 2, 1)
    # provider/route/pricing/FX durable IDs are the ACTUAL row IDs
    provider_ids = _phase(url, lambda e: _rows(e, "SELECT id::text FROM provider_configs"))
    route_ids_actual = _phase(url, lambda e: _rows(e, "SELECT id::text FROM model_routes"))
    assert sorted(prov_ids) == sorted(str(row[0]) for row in provider_ids)
    assert sorted(route_ids) == sorted(str(row[0]) for row in route_ids_actual)
    assert sorted(pricing_ids) == sorted([oai_row[0], or_row[0]])
    assert fx_ids == [fx_id]
    assert state["audit_applied"] == 1

    # retry of the SAME sealed run: already_committed, nothing new
    retried = _apply(run_dir, tmp_path, url, ack=("new_model_exposure",))
    assert retried.exit_code == 0, retried.output
    assert _summary_line(retried, "status:") == "already_committed"
    assert _summary_line(retried, "effective_at:") == effective_at
    after = _phase(url, _check)
    assert after["providers"] == state["providers"]
    assert after["pricing"] == state["pricing"]
    assert after["fx"] == state["fx"]
    assert len(after["record"]) == 1
    assert after["audit_applied"] == 1
    _phase(url, _cleanup)


def test_refresh_supersedes_price_and_fx_at_one_t(
    migrated_postgres_url: str, tmp_path: Path
) -> None:
    url = migrated_postgres_url
    run_dir = _review_usd_refresh_run(
        tmp_path, url, "itg182b-refresh", or_input=OR_INPUT_B, fx_rate=FX_NEW
    )
    # the reviewer helper seeded the catalog; read the row identities fresh
    ids = _phase(url, lambda e: _rows(
        e,
        "SELECT "
        "(SELECT id::text FROM pricing_rules WHERE upstream_model = :m1), "
        "(SELECT id::text FROM pricing_rules WHERE upstream_model = :m2), "
        "(SELECT id::text FROM pricing_rules WHERE upstream_model = :m3), "
        "(SELECT id::text FROM fx_rates WHERE base_currency = 'USD')",
        {"m1": MODEL, "m2": OAI_MODEL, "m3": RETAINED_MODEL},
    ))
    seeded_pricing_model, seeded_pricing_oai, seeded_pricing_retained, seeded_fx = ids[0]

    sealed = json.loads((run_dir / "validation.json").read_text(encoding="utf-8"))
    sealed_plan = sealed["apply_plan"]
    ops = sealed_plan["operations"]
    assert [op["type"] for op in ops] == ["supersede_pricing", "supersede_fx"]
    (sup_price, sup_fx) = ops
    assert sup_price["provider"] == PROVIDER
    assert sup_price["model"] == MODEL
    assert sup_price["endpoint"] == ENDPOINT
    assert sup_price["old"]["row_id"] == seeded_pricing_model
    assert sup_price["old"]["currency"] == "USD"
    # the reviewed old values are the exported 9-decimal baseline strings
    assert sup_price["old"]["dimensions"]["input"] == format(
        Decimal(OR_INPUT).quantize(Decimal("0.000000001")), "f"
    )
    assert sup_price["old"]["dimensions"]["output"] == format(
        Decimal(OR_OUTPUT).quantize(Decimal("0.000000001")), "f"
    )
    assert sup_price["old"]["enabled"] is True
    assert sup_price["old"]["valid_until"] is not None  # reviewed finite future end
    assert sup_price["new"]["currency"] == "USD"
    assert sup_price["new"]["dimensions"] == {"input": OR_INPUT_B, "output": OR_OUTPUT}
    assert sup_price["new"]["source_url"] == OPENROUTER_MODELS_URL
    assert sup_fx["base_currency"] == "USD"
    assert sup_fx["quote_currency"] == "EUR"
    assert sup_fx["old"]["row_id"] == seeded_fx
    assert sup_fx["old"]["rate"] == str(FX_OLD_EUR)
    assert sup_fx["old"]["valid_until"] is None
    assert sup_fx["old"]["source"] == ECB_URL
    assert sup_fx["new"]["rate"] == str(FX_NEW_EUR)
    assert sup_fx["new"]["derived_reciprocal"] is True
    assert sup_fx["new"]["source_pair"] == "EUR-USD"

    applied = _apply(run_dir, tmp_path, url)
    assert applied.exit_code == 0, applied.output
    assert _summary_line(applied, "status:") == "committed"
    effective_at = _summary_line(applied, "effective_at:")

    async def _check(engine: AsyncEngine) -> dict[str, Any]:
        out: dict[str, Any] = {}
        out["pricing"] = await _rows(
            engine,
            "SELECT id::text, upstream_model, currency, input_price_per_1m, "
            "output_price_per_1m, source_url, notes, "
            "to_char(valid_from, 'YYYY-MM-DD\"T\"HH24:MI:SS.US\"Z\"'), "
            "to_char(valid_until, 'YYYY-MM-DD\"T\"HH24:MI:SS.US\"Z\"') "
            "FROM pricing_rules ORDER BY upstream_model, valid_from",
        )
        out["fx"] = await _rows(
            engine,
            "SELECT id::text, base_currency, quote_currency, rate, source, "
            "to_char(valid_from, 'YYYY-MM-DD\"T\"HH24:MI:SS.US\"Z\"'), "
            "to_char(valid_until, 'YYYY-MM-DD\"T\"HH24:MI:SS.US\"Z\"') "
            "FROM fx_rates ORDER BY valid_from, valid_until NULLS FIRST",
        )
        out["routes"] = await _scalar(engine, "SELECT count(*) FROM model_routes")
        out["providers"] = await _scalar(engine, "SELECT count(*) FROM provider_configs")
        out["record"] = await _rows(
            engine,
            "SELECT mode, superseded_pricing, superseded_fx, created_pricing, "
            "created_fx, applied_pricing_superseded_old_ids, "
            "applied_pricing_superseded_new_ids, applied_fx_superseded_old_ids, "
            "applied_fx_superseded_new_ids, effective_at "
            "FROM catalog_refresh_applications",
        )
        out["audit_applied"] = await _scalar(
            engine, "SELECT count(*) FROM audit_log WHERE action = 'catalog_refresh_applied'"
        )
        return out

    state = _phase(url, _check)
    # provider/route counts unchanged; retained + OAI rows untouched
    assert state["routes"] == 3 and state["providers"] == 2
    rows = state["pricing"]
    assert len(rows) == 4  # OR old+new, OAI unchanged, retained unchanged
    by_model = {}
    for row in rows:
        by_model.setdefault(row[1], []).append(row)
    assert set(by_model) == {MODEL, OAI_MODEL, RETAINED_MODEL}
    or_old, or_new = sorted(by_model[MODEL], key=lambda r: r[7])
    (oai_row,) = by_model[OAI_MODEL]
    (retained_row,) = by_model[RETAINED_MODEL]
    assert or_old[0] == seeded_pricing_model
    assert (or_old[2], or_old[3], or_old[4]) == (
        "USD", Decimal(OR_INPUT), Decimal(OR_OUTPUT),
    )
    assert or_old[8][:26] == effective_at[:26]  # old window closed exactly at T
    assert or_new[0] != seeded_pricing_model
    assert or_new[7][:26] == effective_at[:26]  # new window opened exactly at T
    assert or_new[8] is None
    assert (or_new[2], or_new[3], or_new[4]) == (
        "USD", Decimal(OR_INPUT_B), Decimal(OR_OUTPUT),
    )
    assert or_new[5] == OPENROUTER_MODELS_URL
    assert oai_row[0] == seeded_pricing_oai
    assert (oai_row[2], oai_row[3], oai_row[4]) == (
        "USD", Decimal(OAI_INPUT), Decimal(OAI_OUTPUT),
    )
    assert oai_row[8] is None  # unchanged row: original window preserved
    assert retained_row[0] == seeded_pricing_retained
    assert (retained_row[2], retained_row[3], retained_row[4]) == (
        "USD", Decimal("0.10"), Decimal("0.40"),
    )
    # FX: old USD->EUR row closed at T, new row opened at the SAME T
    assert len(state["fx"]) == 2
    fx_old, fx_new = state["fx"]
    assert fx_old[0] == seeded_fx
    assert (fx_old[1], fx_old[2], fx_old[3]) == ("USD", "EUR", FX_OLD_EUR)
    assert fx_old[5][:26] != effective_at[:26]  # original open instant kept
    assert fx_old[6][:26] == effective_at[:26]  # closed exactly at T
    assert fx_new[0] != seeded_fx
    assert (fx_new[1], fx_new[2], fx_new[3]) == ("USD", "EUR", FX_NEW_EUR)
    assert fx_new[5][:26] == effective_at[:26]  # opened exactly at T
    assert fx_new[6] is None
    assert fx_new[4] == ECB_URL

    (mode, sup_p, sup_f, c_p, c_f, p_old, p_new, f_old, f_new, eff) = state["record"][0]
    assert mode == "refresh"
    assert (sup_p, sup_f, c_p, c_f) == (1, 1, 0, 0)
    assert p_old == [seeded_pricing_model]
    assert p_new[0] == or_new[0]
    assert f_old == [seeded_fx]
    assert f_new[0] == fx_new[0]
    assert eff.isoformat() == effective_at
    assert state["audit_applied"] == 1

    # retry: already committed, prior T unchanged, no new rows
    retried = _apply(run_dir, tmp_path, url)
    assert retried.exit_code == 0, retried.output
    assert _summary_line(retried, "status:") == "already_committed"
    assert _summary_line(retried, "effective_at:") == effective_at
    after = _phase(url, _check)
    assert after["pricing"] == state["pricing"]
    assert after["fx"] == state["fx"]
    assert len(after["record"]) == 1
    assert after["audit_applied"] == 1
    _phase(url, _cleanup)


def test_fx_supersession_failure_rolls_back_price_fx_and_records_together(
    migrated_postgres_url: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failure after the ACTUAL FX mutation (and the price mutations
    before it), before the application record/audit commit, must roll every
    affected window/amount and row set back together."""
    url = migrated_postgres_url
    run_dir = _review_usd_refresh_run(
        tmp_path, url, "itg182b-fxrollback", or_input=OR_INPUT_B, fx_rate=FX_NEW
    )
    seeded = _phase(url, lambda e: _rows(
        e,
        "SELECT "
        "(SELECT id::text FROM pricing_rules WHERE upstream_model = :m1), "
        "(SELECT id::text FROM fx_rates WHERE base_currency = 'USD')",
        {"m1": MODEL},
    ))
    seeded = {"pricing_model": seeded[0][0], "fx": seeded[0][1]}
    seeded["pricing_model_until"] = _phase(url, lambda e: _scalar(
        e,
        "SELECT valid_until FROM pricing_rules WHERE upstream_model = :m",
        {"m": MODEL},
    ))
    seeded_pricing_model, seeded_fx = seeded["pricing_model"], seeded["fx"]
    key = _seal_key_bytes(tmp_path)

    async def _boom_fx(self, *args: Any, **kwargs: Any) -> None:
        raise RuntimeError("injected fx supersession failure")

    monkeypatch.setattr(apply_mod.FxRateService, "create_fx_rate", _boom_fx)

    async def _run(engine: AsyncEngine) -> None:
        await apply_mod.apply_reviewed_run(
            run_dir=run_dir,
            seal_key=key,
            database_url=url,
            reason="itg: fx rollback proof",
            actor="ops@itg",
        )

    with pytest.raises(CatalogRefreshBlockedError) as excinfo:
        _phase(url, _run)
    assert excinfo.value.code == "apply_database_error"

    async def _check(engine: AsyncEngine) -> dict[str, Any]:
        return {
            "pricing_model_rows": await _rows(
                engine,
                "SELECT id::text, input_price_per_1m, output_price_per_1m, "
                "valid_until FROM pricing_rules WHERE upstream_model = :m "
                "ORDER BY valid_from",
                {"m": MODEL},
            ),
            "pricing_oai": await _rows(
                engine,
                "SELECT id::text, input_price_per_1m FROM pricing_rules "
                "WHERE upstream_model = :m",
                {"m": OAI_MODEL},
            ),
            "fx_rows": await _rows(
                engine,
                "SELECT id::text, base_currency, quote_currency, rate, valid_until "
                "FROM fx_rates ORDER BY valid_from",
            ),
            "records": await _scalar(
                engine, "SELECT count(*) FROM catalog_refresh_applications"
            ),
            "audit": await _scalar(engine, "SELECT count(*) FROM audit_log"),
        }

    state = _phase(url, _check)
    # the price supersession (old closed + new created) rolled back together
    seeded_until = seeded["pricing_model_until"]
    assert len(state["pricing_model_rows"]) == 1
    (row_id, inp, out, vu) = state["pricing_model_rows"][0]
    assert row_id == seeded_pricing_model
    assert (inp, out) == (Decimal(OR_INPUT), Decimal(OR_OUTPUT))
    # the close of the reviewed finite window rolled back to its original end
    assert vu is not None and vu.isoformat() == seeded_until.isoformat()
    # OAI untouched
    assert len(state["pricing_oai"]) == 1
    # the FX mutation (old window closed) rolled back too: still the old rate
    assert len(state["fx_rows"]) == 1
    (fx_id, fx_base, fx_quote, fx_rate, fx_vu) = state["fx_rows"][0]
    assert fx_id == seeded_fx
    assert (fx_base, fx_quote, fx_rate) == ("USD", "EUR", FX_OLD_EUR)
    assert fx_vu is None
    # no application record, no audit
    assert state["records"] == 0
    assert state["audit"] == 0
    _phase(url, _cleanup)


# --- 182-b B3: real executor concurrency and recoverable outcomes ---------


def test_identical_bundle_concurrent_apply_commits_exactly_once(
    migrated_postgres_url: str, tmp_path: Path
) -> None:
    url = migrated_postgres_url
    run_dir = _review_usd_refresh_run(
        tmp_path, url, "itg182b-race-same", or_input=OR_INPUT_B, fx_rate=FX_NEW
    )
    key = _seal_key_bytes(tmp_path)

    async def _apply_once() -> Any:
        return await apply_mod.apply_reviewed_run(
            run_dir=run_dir,
            seal_key=key,
            database_url=url,
            reason="itg: identical-bundle race",
            actor="ops@itg",
        )

    async def _race(engine: AsyncEngine) -> dict[str, Any]:
        outcomes = await asyncio.gather(_apply_once(), _apply_once(), return_exceptions=True)
        committed = [o for o in outcomes if isinstance(o, apply_mod.ApplyResult)
                     and o.status == "committed"]
        already = [o for o in outcomes if isinstance(o, apply_mod.ApplyResult)
                   and o.status == "already_committed"]
        other = [o for o in outcomes
                 if not isinstance(o, apply_mod.ApplyResult)]
        return {
            "committed": committed,
            "already": already,
            "other": other,
            "records": await _rows(
                engine,
                "SELECT run_id, operator_actor, effective_at "
                "FROM catalog_refresh_applications",
            ),
            "pricing": await _scalar(engine, "SELECT count(*) FROM pricing_rules"),
            "fx": await _scalar(engine, "SELECT count(*) FROM fx_rates"),
            "audit": await _scalar(
                engine, "SELECT count(*) FROM audit_log WHERE action = 'catalog_refresh_applied'"
            ),
        }

    state = _phase(url, _race)
    assert len(state["committed"]) == 1, state["other"] or state["already"]
    assert len(state["already"]) == 1, state
    assert not state["other"]
    winner, loser = state["committed"][0], state["already"][0]
    # identical prior record/T for the serialized caller
    assert loser.effective_at == winner.effective_at
    assert loser.record["effective_at"] == winner.record["effective_at"]
    assert loser.record["operator_actor"] == "ops@itg"
    assert len(state["records"]) == 1
    assert state["records"][0][0] == winner.run_id
    assert state["pricing"] == 4  # OR old+new, OAI, retained
    assert state["fx"] == 2
    assert state["audit"] == 1

    # a DISTINCT actor cannot overwrite the committed outcome
    async def _distinct_actor(engine: AsyncEngine) -> Any:
        return await apply_mod.apply_reviewed_run(
            run_dir=run_dir,
            seal_key=key,
            database_url=url,
            reason="itg: overwrite attempt",
            actor="other@itg",
        )

    retry = _phase(url, _distinct_actor)
    assert isinstance(retry, apply_mod.ApplyResult), retry
    assert retry.status == "already_committed"
    assert retry.effective_at == winner.effective_at
    assert retry.record["operator_actor"] == "ops@itg"
    after = _phase(url, lambda e: _rows(
        e, "SELECT operator_actor FROM catalog_refresh_applications"
    ))
    assert after == [("ops@itg",)]
    _phase(url, _cleanup)


def test_ordinary_writer_commit_before_apply_yields_stale_refusal(
    migrated_postgres_url: str, tmp_path: Path
) -> None:
    """An in-flight ordinary catalog edit that commits while the actual
    apply waits on the catalog locks makes the locked comparison see drift:
    the apply refuses stale, and the writer's committed fact is preserved."""
    url = migrated_postgres_url
    run_dir = _review_usd_refresh_run(
        tmp_path, url, "itg182b-interleave-w", or_input=OR_INPUT_B, fx_rate=FX_NEW
    )
    key = _seal_key_bytes(tmp_path)
    seeded_pricing_model = _phase(url, lambda e: _scalar(
        e, "SELECT id::text FROM pricing_rules WHERE upstream_model = :m", {"m": MODEL}
    ))
    seeded_end = _phase(url, lambda e: _scalar(
        e, "SELECT valid_until FROM pricing_rules WHERE upstream_model = :m", {"m": MODEL}
    ))

    async def _interleave(engine: AsyncEngine) -> CatalogRefreshBlockedError | None:
        error: CatalogRefreshBlockedError | None = None
        async with engine.connect() as wconn:
            await wconn.begin()
            # the ordinary edit is in flight: holds ROW EXCLUSIVE on the
            # catalog tables (the lock an ordinary INSERT/UPDATE takes)
            await wconn.execute(
                text(
                    "UPDATE pricing_rules SET output_price_per_1m = 0.42 "
                    "WHERE id = :id"
                ),
                {"id": uuid.UUID(seeded_pricing_model)},
            )

            async def _commit_writer() -> None:
                # let the apply reach its bounded lock wait first
                await asyncio.sleep(0.2)
                await wconn.commit()

            commit_task = asyncio.create_task(_commit_writer())
            try:
                await apply_mod.apply_reviewed_run(
                    run_dir=run_dir,
                    seal_key=key,
                    database_url=url,
                    reason="itg: interleave writer-first",
                    actor="ops@itg",
                )
            except CatalogRefreshBlockedError as exc:
                error = exc
            await commit_task
        return error

    error = _phase(url, _interleave)
    assert error is not None
    assert error.code == "apply_baseline_stale", error

    async def _check(engine: AsyncEngine) -> dict[str, Any]:
        return {
            "value": await _scalar(
                engine,
                "SELECT output_price_per_1m FROM pricing_rules WHERE id = :id",
                {"id": seeded_pricing_model},
            ),
            "end": await _scalar(
                engine,
                "SELECT valid_until FROM pricing_rules WHERE id = :id",
                {"id": seeded_pricing_model},
            ),
            "records": await _scalar(
                engine, "SELECT count(*) FROM catalog_refresh_applications"
            ),
            "pricing": await _scalar(engine, "SELECT count(*) FROM pricing_rules"),
        }

    state = _phase(url, _check)
    assert state["value"] == Decimal("0.42")  # the writer's fact is preserved
    # nothing was closed by the refused apply: the reviewed finite end is intact
    assert state["end"] is not None and state["end"].isoformat() == seeded_end.isoformat()
    assert state["records"] == 0
    assert state["pricing"] == 3
    _phase(url, _cleanup)


def test_ordinary_writer_waiting_on_apply_commits_after_without_loss(
    migrated_postgres_url: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The ordinary writer starts AFTER the actual apply holds the catalog
    locks: it waits for the apply commit, then commits on top of the
    committed facts. Committed apply facts are not silently lost."""
    url = migrated_postgres_url
    run_dir = _review_usd_refresh_run(
        tmp_path, url, "itg182b-interleave-a", or_input=OR_INPUT_B, fx_rate=FX_NEW
    )
    key = _seal_key_bytes(tmp_path)
    seeded_pricing_model = _phase(url, lambda e: _scalar(
        e, "SELECT id::text FROM pricing_rules WHERE upstream_model = :m", {"m": MODEL}
    ))

    lock_held = asyncio.Event()
    real_lock = apply_mod.lock_catalog_tables

    async def _signal_locks(connection: Any) -> None:
        await real_lock(connection)
        lock_held.set()

    monkeypatch.setattr(apply_mod, "lock_catalog_tables", _signal_locks)

    async def _interleave(engine: AsyncEngine) -> dict[str, Any]:
        async def _writer() -> None:
            # deterministic: the writer's write starts only after the apply
            # holds the catalog locks, so it must wait for the apply commit
            await lock_held.wait()
            async with engine.connect() as wconn:
                async with wconn.begin():
                    await wconn.execute(
                        text(
                            "UPDATE pricing_rules SET notes = 'writer-after-apply' "
                            "WHERE id = :id"
                        ),
                        {"id": uuid.UUID(seeded_pricing_model)},
                    )

        writer_task = asyncio.create_task(_writer())
        try:
            result = await apply_mod.apply_reviewed_run(
                run_dir=run_dir,
                seal_key=key,
                database_url=url,
                reason="itg: interleave apply-first",
                actor="ops@itg",
            )
        finally:
            await writer_task  # its commit happens after the apply commit
        return {
            "result": result,
            "pricing": await _rows(
                engine,
                "SELECT id::text, input_price_per_1m, notes, "
                "to_char(valid_from, 'YYYY-MM-DD\"T\"HH24:MI:SS.US\"Z\"'), "
                "to_char(valid_until, 'YYYY-MM-DD\"T\"HH24:MI:SS.US\"Z\"') "
                "FROM pricing_rules WHERE upstream_model = :m ORDER BY valid_from",
                {"m": MODEL},
            ),
            "records": await _scalar(
                engine, "SELECT count(*) FROM catalog_refresh_applications"
            ),
        }

    out = _phase(url, _interleave)
    result = out["result"]
    assert isinstance(result, apply_mod.ApplyResult), result
    assert result.status == "committed"
    t26 = result.effective_at[:26]
    rows = out["pricing"]
    assert len(rows) == 2
    old_row, new_row = rows
    assert old_row[0] == seeded_pricing_model
    assert old_row[2] == "writer-after-apply"  # writer's fact committed on top
    assert old_row[4][:26] == t26  # closed at T by the apply
    assert new_row[0] != seeded_pricing_model
    assert new_row[1] == Decimal(OR_INPUT_B)  # committed apply fact intact
    assert new_row[3][:26] == t26
    assert out["records"] == 1
    _phase(url, _cleanup)


def test_conflicting_catalog_lock_holder_gets_bounded_safe_refusal(
    migrated_postgres_url: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A conflicting catalog lock held across the ACTUAL apply makes the
    production bounded lock wait fail safely: a code+detail refusal with no
    partial writes/records/audit and complete transaction cleanup. Only the
    test-local lock wait is shortened; production settings are unchanged."""
    url = migrated_postgres_url
    run_dir = _review_usd_refresh_run(
        tmp_path, url, "itg182b-lockrefusal", or_input=OR_INPUT_B, fx_rate=FX_NEW
    )
    key = _seal_key_bytes(tmp_path)

    async def _short_prelude(connection: Any) -> None:
        await connection.execute(text("SET LOCAL lock_timeout = '1s'"))
        await connection.execute(text("SET LOCAL statement_timeout = '60s'"))
        await apply_mod.lock_catalog_tables(connection)

    monkeypatch.setattr(apply_mod, "apply_transaction_prelude", _short_prelude)

    async def _hold_and_apply(engine: AsyncEngine) -> CatalogRefreshBlockedError | None:
        error: CatalogRefreshBlockedError | None = None
        async with engine.connect() as holder:
            await holder.begin()
            await holder.execute(
                text("LOCK TABLE fx_rates IN SHARE ROW EXCLUSIVE MODE")
            )
            try:
                await apply_mod.apply_reviewed_run(
                    run_dir=run_dir,
                    seal_key=key,
                    database_url=url,
                    reason="itg: bounded lock refusal",
                    actor="ops@itg",
                )
            except CatalogRefreshBlockedError as exc:
                error = exc
            await holder.rollback()
        return error

    error = _phase(url, _hold_and_apply)
    assert error is not None
    assert error.code == "apply_database_error", error

    async def _check(engine: AsyncEngine) -> dict[str, Any]:
        return {
            "providers": await _scalar(engine, "SELECT count(*) FROM provider_configs"),
            "routes": await _scalar(engine, "SELECT count(*) FROM model_routes"),
            "pricing": await _scalar(engine, "SELECT count(*) FROM pricing_rules"),
            "fx": await _scalar(engine, "SELECT count(*) FROM fx_rates"),
            "records": await _scalar(
                engine, "SELECT count(*) FROM catalog_refresh_applications"
            ),
            "audit": await _scalar(engine, "SELECT count(*) FROM audit_log"),
        }

    assert _phase(url, _check) == {
        "providers": 2, "routes": 3, "pricing": 3, "fx": 1, "records": 0, "audit": 0,
    }
    _phase(url, _cleanup)


def test_post_commit_result_loss_recovers_via_status_and_retry(
    migrated_postgres_url: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Loss of the client result AFTER the database commit (injected at the
    CLI return seam): the first caller observes the loss; a separate
    authenticated status plus retry recovers the SAME committed outcome with
    no duplicate writes or audits."""
    from slaif_gateway.cli import catalog_refresh as cr_cli

    url = migrated_postgres_url
    run_dir = _review_usd_refresh_run(
        tmp_path, url, "itg182b-loss", or_input=OR_INPUT_B, fx_rate=FX_NEW
    )
    calls = {"n": 0}
    real_apply = cr_cli.apply_reviewed_run

    async def _losing_apply(**kwargs: Any) -> Any:
        result = await real_apply(**kwargs)
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("simulated client result loss after database commit")
        return result

    monkeypatch.setattr(cr_cli, "apply_reviewed_run", _losing_apply)

    first = _apply(run_dir, tmp_path, url)
    assert first.exit_code != 0
    assert isinstance(first.exception, RuntimeError)
    assert "simulated client result loss" in str(first.exception)

    # separate authenticated status sees the committed outcome
    st = _status(run_dir, tmp_path, url)
    assert st.exit_code == 0, st.output
    assert _summary_line(st, "committed:") == "true"
    status_record = json.loads(_summary_line(st, "record:"))
    effective_at = status_record["effective_at"]

    # retry (client result intact again) recovers the same outcome
    retry = _apply(run_dir, tmp_path, url)
    assert retry.exit_code == 0, retry.output
    assert _summary_line(retry, "status:") == "already_committed"
    assert _summary_line(retry, "effective_at:") == effective_at

    async def _check(engine: AsyncEngine) -> dict[str, Any]:
        return {
            "records": await _scalar(
                engine, "SELECT count(*) FROM catalog_refresh_applications"
            ),
            "audit": await _scalar(
                engine, "SELECT count(*) FROM audit_log WHERE action = 'catalog_refresh_applied'"
            ),
            "pricing": await _scalar(engine, "SELECT count(*) FROM pricing_rules"),
            "fx": await _scalar(engine, "SELECT count(*) FROM fx_rates"),
        }

    assert _phase(url, _check) == {
        "records": 1, "audit": 1, "pricing": 4, "fx": 2,
    }
    _phase(url, _cleanup)


def test_aged_retry_returns_original_outcome_and_refuses_new_stale_work(
    migrated_postgres_url: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """After the apply, the test clock advances past source freshness AND a
    reviewed finite validity end. The authenticated retry of the SAME bundle
    still returns the original actor/T/counts (known-committed lookup before
    the current gates); a DIFFERENT unapplied stale bundle is refused; no
    archived timestamp is refreshed or resealed and no freshness policy is
    relaxed."""
    url = migrated_postgres_url
    _phase(url, _cleanup)
    seeded = _phase(url, lambda e: _seed_catalog_usd(e))
    baseline_doc = _export_baseline(tmp_path, url, "baseline-aged.json")

    def _bundle(run_id: str, or_input: str) -> Path:
        bundle = _usd_bundle_bytes(
            run_id=run_id,
            baseline_block=_baseline_block_from_doc(baseline_doc),
            or_input=or_input,
            fx_rate=FX_NEW,
            now=datetime.now(UTC),
        )
        path = tmp_path / f"{run_id}.bundle.json"
        path.write_bytes(bundle)
        reviewed = _review(
            [str(path), "--baseline-file", str(tmp_path / "baseline-aged.json")],
            tmp_path,
        )
        assert reviewed.exit_code == 0, reviewed.output
        return _run_dir_for(run_id, tmp_path)

    run_a = _bundle("itg182b-aged-a", OR_INPUT_B)
    run_b = _bundle("itg182b-aged-b", "0.29")  # different unapplied work
    bundle_created_at = datetime.now(UTC)
    key = _seal_key_bytes(tmp_path)

    async def _apply_a(engine: AsyncEngine) -> Any:
        return await apply_mod.apply_reviewed_run(
            run_dir=run_a,
            seal_key=key,
            database_url=url,
            reason="itg: aged original",
            actor="ops@itg",
        )

    applied = _phase(url, _apply_a)
    assert isinstance(applied, apply_mod.ApplyResult), applied
    assert applied.status == "committed"
    t0 = applied.effective_at

    async def _snapshot(engine: AsyncEngine) -> dict[str, Any]:
        record = (await _rows(
            engine,
            "SELECT operator_actor, db_actor, effective_at, created_at, "
            "created_pricing, created_fx, superseded_pricing, superseded_fx "
            "FROM catalog_refresh_applications",
        ))[0]
        return {
            "record": record,
            "audit": await _scalar(
                engine, "SELECT count(*) FROM audit_log WHERE action = 'catalog_refresh_applied'"
            ),
        }

    before = _phase(url, _snapshot)
    validation_bytes = (run_a / "validation.json").read_bytes()

    class _FrozenDatetime(datetime):
        _frozen: datetime | None = None

        @classmethod
        def now(cls, tz=None) -> datetime:
            if cls._frozen is None:
                return super().now(tz)
            return cls._frozen

    # past the ACTUAL reviewed finite future end (seed: now + 30d) AND
    # past the source freshness block limit (72h from bundle generation)
    _FrozenDatetime._frozen = seeded["pricing_model_until"] + timedelta(days=1)
    assert _FrozenDatetime._frozen > seeded["pricing_model_until"]
    assert _FrozenDatetime._frozen > bundle_created_at + timedelta(hours=72)
    monkeypatch.setattr(apply_mod, "datetime", _FrozenDatetime)

    # 1) the authenticated retry of the SAME bundle: original actor/T/counts
    async def _retry_a(engine: AsyncEngine) -> Any:
        return await apply_mod.apply_reviewed_run(
            run_dir=run_a,
            seal_key=key,
            database_url=url,
            reason="itg: aged retry",
            actor="ops@itg",
        )

    retry = _phase(url, _retry_a)
    assert isinstance(retry, apply_mod.ApplyResult), retry
    assert retry.status == "already_committed"
    assert retry.effective_at == t0
    assert retry.record["operator_actor"] == "ops@itg"
    assert retry.counts == applied.counts

    # 2) a DIFFERENT unapplied bundle is still refused (freshness)
    async def _apply_b(engine: AsyncEngine) -> None:
        await apply_mod.apply_reviewed_run(
            run_dir=run_b,
            seal_key=key,
            database_url=url,
            reason="itg: stale other work",
            actor="ops@itg",
        )

    with pytest.raises(CatalogRefreshBlockedError) as excinfo:
        _phase(url, _apply_b)
    assert excinfo.value.code == "apply_freshness_blocked", excinfo.value.code

    # 3) no archived timestamp refreshed/resealed, no freshness relaxed
    after = _phase(url, _snapshot)
    assert after["record"] == before["record"]
    assert after["audit"] == before["audit"]
    assert (run_a / "validation.json").read_bytes() == validation_bytes
    _phase(url, _cleanup)
