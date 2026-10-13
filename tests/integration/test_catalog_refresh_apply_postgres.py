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
from slaif_gateway.db.models import ProviderConfig, ModelRoute, PricingRule
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
    assert db_actor == "slaif_synth"  # the ACTUAL database user, not the operator text
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
            "SELECT run_id, bundle_sha256, receipt_hmac_sha256, effective_at "
            "FROM catalog_refresh_applications",
        ))[0]
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO catalog_refresh_applications (id, run_id, "
                    "bundle_sha256, receipt_hmac_sha256, plan_sha256, mode, "
                    "operator_actor, db_actor, reason, effective_at, outcome, "
                    "created_at) VALUES (:id, :run_id, :bundle, :hmac, :plan, "
                    "'bootstrap', 'ops@itg', 'slaif_synth', 'anomaly', "
                    ":eff, 'committed', :now)"
                ),
                {
                    "id": uuid.uuid4(),
                    "run_id": record[0],
                    "bundle": record[1],
                    "hmac": record[2],
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
