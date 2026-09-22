"""Unit tests for the 181 authoritative catalog collector (collection.py).

The whole official world (OpenRouter catalog, OpenAI pricing docs, model
pages, models index, ECB reference XML) is served by ``httpx.MockTransport``
with an injected public-DNS resolver: no test performs a real network
request. The tests drive the REAL collector end to end (``collect_bundle``)
and the REAL validator (``validate_bundle``), pinning: bootstrap READY,
explicit selection, ineligible-selection blocking, :batch/alias handling,
tier/long-band exclusion, page price-conflict and 404 handling, retrieval
failure as BLOCKED (never disappearance), ECB failure blocking FX binding,
refresh preservation of baseline route attributes including explicit
denials, baseline contract/currency exclusions, inventory re-verification
(fabricated entries block), source-without-retrieval blocking, and the
supplied-bundle offline replay scope.
"""

from __future__ import annotations

import json
import socket
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256

import httpx
import pytest

from slaif_gateway.schemas.catalog_refresh import (
    BaselineCounts,
    BaselineDocument,
    BaselinePricingRow,
    BaselineProviderRow,
    BaselineRouteRow,
    BaselineTarget,
)
from slaif_gateway.services.catalog_refresh import collection as coll
from slaif_gateway.services.catalog_refresh import sources as src
from slaif_gateway.services.catalog_refresh.errors import CatalogRefreshBlockedError
from slaif_gateway.services.catalog_refresh.policy import policy_from_document
from slaif_gateway.services.catalog_refresh.validation import validate_bundle

NOW = datetime(2026, 9, 21, 12, 0, 0, tzinfo=UTC)

OR_URL = "https://openrouter.ai/api/v1/models"
PRICING_URL = "https://developers.openai.com/api/docs/pricing.md"
MODELS_MD_URL = "https://developers.openai.com/api/docs/models.md"
ECB_URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"
PAGE_PREFIX = "https://developers.openai.com/api/docs/models/"


def _resolve_public(host, port, proto=None):
    return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("93.184.216.34", 443))]


def _per_token_usd(eur_per_1m: str) -> str:
    """Per-million EUR -> per-token USD at the exact 1.08 quote (180 shape)."""
    return str(Decimal(eur_per_1m) * Decimal("1.08") / Decimal(10**6))


def _or_row(model: str, *, inp: str = "0.5", out: str = "2.0", **kw) -> dict:
    row = {
        "id": model,
        "context_length": kw.get("context", 128000),
        "architecture": {
            "input_modalities": kw.get("in_mod", ["text"]),
            "output_modalities": kw.get("out_mod", ["text"]),
        },
        "top_provider": {"max_completion_tokens": kw.get("maxtok", 8192)},
        "deprecation": {"is_deprecated": kw.get("deprecated", False)},
        "pricing": {
            "prompt": kw.get("prompt", _per_token_usd(inp)),
            "completion": kw.get("completion", _per_token_usd(out)),
            "input_cache_read": kw.get(
                "cache_read", _per_token_usd(Decimal(inp) / Decimal(10))
            ),
        },
    }
    if kw.get("no_context"):
        del row["context_length"]
    if kw.get("no_completion"):
        del row["pricing"]["completion"]
    return row


def _or_payload(rows: list[dict]) -> bytes:
    return (json.dumps({"data": rows}, sort_keys=True) + "\n").encode("utf-8")


def _pricing_md(rows: list[tuple]) -> bytes:
    """v2 tiered pricing table rows: (model, si, sc, so, li, lo), '-' = absent."""

    def cell(v: str | None) -> str:
        return "-" if v is None else f"${v}"

    lines = [
        "# Pricing",
        "",
        "### Standard pricing data",
        "",
        "| Model | Short context input | Short context cached input | Short context output | Long context input | Long context output |",
        "|---|---|---|---|---|---|",
    ]
    for m, si, sc, so, li, lo in rows:
        lines.append(f"| {m} | {cell(si)} | {cell(sc)} | {cell(so)} | {cell(li)} | {cell(lo)} |")
    lines.append("")
    return ("\n".join(lines)).encode("utf-8")


def _page(
    model: str,
    *,
    inp: str = "0.54",
    cached: str | None = "0.054",
    out: str = "2.16",
    context: int = 128000,
    maxtok: int = 8192,
    chat: str = "Supported",
    text: bool = True,
) -> bytes:
    modality = "text" if text else "image"
    lines = [
        f"# {model}",
        "",
        f"Model ID: `{model}`",
        "",
        f"- Input modalities: {modality}",
        f"- Output modalities: {modality}",
        f"- {context:,} context window",
        f"- {maxtok:,} max output tokens",
        "",
        "## Endpoints",
        "",
        "| Endpoint | Route | Support |",
        "|---|---|---|",
        f"| Chat Completions | `v1/chat/completions` | {chat} |",
        "",
        "## Text tokens",
        "",
        "| Metric | Price | Unit |",
        "|---|---|---|",
        f"| Input | ${inp} | 1M tokens |",
    ]
    if cached is not None:
        lines.append(f"| Cached input | ${cached} | 1M tokens |")
    lines.append(f"| Output | ${out} | 1M tokens |")
    lines.append("")
    return ("\n".join(lines)).encode("utf-8")


def _ecb_xml(rate: str = "1.08", date_s: str = "2026-09-21") -> bytes:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<gesmes:Envelope xmlns:gesmes="http://www.gesmes.org/xml/2002-08-01" '
        'xmlns="http://www.ecb.int/vocabulary/2002-08-01/eurofxref">\n'
        "  <gesmes:subject>Reference rates</gesmes:subject>\n"
        "  <gesmes:Sender>\n"
        "    <gesmes:Name>ECB</gesmes:Name>\n"
        "  </gesmes:Sender>\n"
        "  <Cube>\n"
        f'    <Cube time="{date_s}">\n'
        f'      <Cube currency="USD" rate="{rate}"/>\n'
        "    </Cube>\n"
        "  </Cube>\n"
        "</gesmes:Envelope>\n"
    ).encode("utf-8")


@dataclass
class World:
    """One deterministic mock of the official source registry."""

    or_rows: list[dict] = field(
        default_factory=lambda: [
            _or_row("synth/alpha"),
            _or_row("synth/beta", inp="0.1", out="0.4"),
            _or_row("synth/alpha:batch"),
            _or_row("synth/deprecated", deprecated=True),
            _or_row("synth/nolimits", no_context=True),
            _or_row("synth/sentinel", prompt="-1"),
            _or_row("synth/image", in_mod=["image"], out_mod=["image"]),
            _or_row("synth/halfprice", no_completion=True),
        ]
    )
    pricing_rows: list[tuple] = field(
        default_factory=lambda: [
            ("gpt-syn-1", "0.54", "0.054", "2.16", "1.08", "4.32"),
            ("gpt-syn-2", "1.08", "0.108", "4.32", None, None),
            ("gpt-syn-long", None, None, None, "1.08", "4.32"),
        ]
    )
    pages: dict[str, bytes] = field(
        default_factory=lambda: {
            "gpt-syn-1": _page("gpt-syn-1"),
            "gpt-syn-2": _page("gpt-syn-2", inp="1.08", cached="0.108", out="4.32"),
        }
    )
    models_md: bytes = b"# Models index\n"
    ecb: bytes = _ecb_xml()
    statuses: dict[str, int] = field(default_factory=dict)

    def handler(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url in self.statuses:
            return httpx.Response(self.statuses[url])
        if url == OR_URL:
            return httpx.Response(200, content=_or_payload(self.or_rows))
        if url == PRICING_URL:
            return httpx.Response(200, content=_pricing_md(self.pricing_rows))
        if url == MODELS_MD_URL:
            return httpx.Response(200, content=self.models_md)
        if url == ECB_URL:
            return httpx.Response(200, content=self.ecb)
        if url.startswith(PAGE_PREFIX):
            slug = url[len(PAGE_PREFIX) :].removesuffix(".md")
            page = self.pages.get(slug)
            if page is None:
                return httpx.Response(404)
            return httpx.Response(200, content=page)
        return httpx.Response(500)

    def client(self) -> httpx.Client:
        return httpx.Client(
            transport=httpx.MockTransport(self.handler), follow_redirects=False
        )


def _collect(world: World, *, providers=("openai", "openrouter"), model_include=(),
             baseline=None, baseline_mode="first_install", now=None, **kw):
    # ``now`` is left at the real clock by default: mock-transport retrievals
    # stamp real times, so a frozen ``now`` earlier than those times would
    # itself trip the future-timestamp gate.
    return coll.collect_bundle(
        providers=tuple(providers),
        model_include=tuple(model_include),
        baseline_mode=baseline_mode,
        baseline=baseline,
        client=world.client(),
        resolve=_resolve_public,
        now=now,
        **kw,
    )


def _baseline_doc(
    routes: dict[str, dict] | None = None,
    pricing: dict[str, dict] | None = None,
) -> BaselineDocument:
    routes = routes or {}
    pricing = pricing or {}
    now_s = "2026-09-01T00:00:00+00:00"
    return BaselineDocument(
        schema_version="1",
        exported_at="2026-09-21T10:00:00+00:00",
        target=BaselineTarget(
            server_host="127.0.0.1",
            server_port=5433,
            database="slaif-collect-test",
            postgres_version="16.4",
        ),
        sql_checked=True,
        counts=BaselineCounts(
            providers=1,
            routes=len(routes),
            pricing_rules=len(pricing),
            fx_rates=0,
        ),
        content_sha256="0" * 64,
        providers=(
            BaselineProviderRow(
                id="11111111-1111-4111-8111-111111111111",
                provider="openrouter",
                display_name="OpenRouter (synthetic)",
                kind="openai_compatible",
                base_url="https://openrouter.ai/api/v1",
                api_key_env_var="OPENROUTER_API_KEY",
                enabled=True,
                timeout_seconds=300,
                max_retries=2,
                created_at=now_s,
                updated_at=now_s,
            ),
        ),
        routes=tuple(
            BaselineRouteRow(
                id=f"22222222-0000-4000-8000-{index:012d}",
                requested_model=model,
                match_type="exact",
                endpoint="/v1/chat/completions",
                provider="openrouter",
                upstream_model=model,
                priority=spec.get("priority", 100),
                enabled=spec.get("enabled", True),
                visible_in_models=spec.get("visible", True),
                supports_streaming=spec.get("streaming", True),
                capabilities=spec.get(
                    "caps", {"chat_completions": {"chat_text": True, "chat_streaming": True}}
                ),
                capabilities_unrepresented=spec.get("unrep", False),
                capabilities_fingerprint=sha256(
                    json.dumps(
                        spec.get(
                            "caps",
                            {"chat_completions": {"chat_text": True, "chat_streaming": True}},
                        ),
                        sort_keys=True,
                    ).encode()
                ).hexdigest(),
                created_at=now_s,
                updated_at=now_s,
            )
            for index, (model, spec) in enumerate(sorted(routes.items()))
        ),
        pricing=tuple(
            BaselinePricingRow(
                id=f"33333333-0000-4000-8000-{index:012d}",
                provider="openrouter",
                upstream_model=model,
                endpoint="/v1/chat/completions",
                currency=spec.get("currency", "USD"),
                input_price_per_1m=spec["input"],
                output_price_per_1m=spec["output"],
                cached_input_price_per_1m=spec.get("cached"),
                valid_from="2026-09-01T00:00:00+00:00",
                enabled=True,
                created_at=now_s,
                updated_at=now_s,
            )
            for index, (model, spec) in enumerate(sorted(pricing.items()))
        ),
        fx=(),
    )


def _validate(bundle, baseline):
    report, artifacts = validate_bundle(
        bundle,
        baseline,
        policy_from_document(bundle.policy),
        sql_capture="first_install" if bundle.baseline.mode == "first_install" else "document",
    )
    return report, artifacts


def _proposed_models(bundle) -> set[str]:
    return {f"{m.provider}/{m.model}" for m in bundle.models}


def _inventory(bundle) -> dict[tuple[str, str], tuple[str, str]]:
    return {
        (e.provider, e.model): (e.disposition, e.reason_code)
        for e in (bundle.collection.inventory if bundle.collection else ())
    }


def _codes(report) -> set[str]:
    return {w.code for w in report.warnings}


# --- bootstrap ---------------------------------------------------------------


def test_bootstrap_collection_both_providers_ready() -> None:
    bundle = _collect(World())
    assert bundle.collection is not None
    assert bundle.collection.providers == ("openai", "openrouter")
    assert bundle.run_id.startswith("collect-")
    assert bundle.research.status == "NOT_RUN"

    assert _proposed_models(bundle) == {
        "openrouter/synth/alpha",
        "openrouter/synth/beta",
        "openai/gpt-syn-1",
        "openai/gpt-syn-2",
    }
    inv = _inventory(bundle)
    assert inv[("openrouter", "synth/alpha:batch")] == ("excluded_subset", "service_variant")
    assert inv[("openrouter", "synth/deprecated")] == ("deprecated", "deprecated_model")
    assert inv[("openrouter", "synth/nolimits")] == ("incomplete", "missing_limits")
    assert inv[("openrouter", "synth/sentinel")] == ("incomplete", "negative_router_sentinel")
    assert inv[("openrouter", "synth/image")] == ("unsupported", "non_text_modality")
    assert inv[("openrouter", "synth/halfprice")] == ("incomplete", "missing_core_prices")
    assert inv[("openai", "gpt-syn-long")] == ("incomplete", "no_standard_short_prices")
    # every observed model reconciled exactly once
    observed = {
        ("openrouter", r["id"]) for r in World().or_rows
    } | {("openai", row[0]) for row in World().pricing_rows}
    assert set(inv) | {
        (m.provider, m.model) for m in bundle.models
    } == observed

    # retrieval records: one per unique URL fetched (4 phase-1 + 2 pages + 1 ecb)
    urls = {r.requested_url for r in bundle.collection.retrievals}
    assert OR_URL in urls and PRICING_URL in urls and MODELS_MD_URL in urls
    assert f"{PAGE_PREFIX}gpt-syn-1.md" in urls and f"{PAGE_PREFIX}gpt-syn-2.md" in urls
    assert ECB_URL in urls
    assert all(r.outcome == "ok" for r in bundle.collection.retrievals)

    report, artifacts = _validate(bundle, None)
    assert report.state == "READY", (report.state, sorted(_codes(report)))
    assert report.to_dict()["source_evidence"]["scope"] == "live_collection"

    # standard-v1 proposes short-context core pricing only (never long band)
    gpt1 = next(p for p in bundle.pricing if p.model == "gpt-syn-1")
    dims = {d.name: d.value for d in gpt1.dimensions}
    assert dims == {"input": "0.54", "cached_input": "0.054", "output": "2.16"}
    # FX fact is the published ECB quote AS PUBLISHED (EUR-USD 1.08); the
    # native -> EUR rate is derived by the tested FX gate and marked
    # derived_reciprocal with the original pair recorded.
    assert len(bundle.fx) == 1
    fx = bundle.fx[0]
    assert fx.base_currency == "EUR" and fx.quote_currency == "USD"
    assert fx.rate == "1.08"
    assert fx.provenance.sources == ("ecb|EUR-USD|ecb_reference_xml",)
    fx_cmp = report.to_dict()["fx_comparisons"][0]
    assert fx_cmp["pair"] == "USD→EUR"
    assert fx_cmp["derived"] is True
    assert fx_cmp["source_pair"] == "EUR-USD"
    assert fx_cmp["proposed_rate"] == str((Decimal(1) / Decimal("1.08")).quantize(Decimal("0.000000001")))


def test_single_model_selection_limits_pages_and_proposals() -> None:
    bundle = _collect(
        World(), providers=("openai",), model_include=("gpt-syn-1",)
    )
    assert _proposed_models(bundle) == {"openai/gpt-syn-1"}
    inv = _inventory(bundle)
    assert inv[("openai", "gpt-syn-2")] == (
        "excluded_subset",
        "explicit_selection_excluded",
    )
    assert inv[("openai", "gpt-syn-long")] == ("incomplete", "no_standard_short_prices")
    # only the selected model's page was fetched
    page_urls = [u for u in {r.requested_url for r in bundle.collection.retrievals} if u.startswith(PAGE_PREFIX)]
    assert page_urls == [f"{PAGE_PREFIX}gpt-syn-1.md"]
    report, _ = _validate(bundle, None)
    assert report.state == "READY", (report.state, sorted(_codes(report)))


def test_explicit_selection_of_ineligible_model_blocks() -> None:
    bundle = _collect(
        World(), providers=("openrouter",), model_include=("synth/sentinel",)
    )
    assert _proposed_models(bundle) == set()
    assert _inventory(bundle)[("openrouter", "synth/sentinel")] == (
        "incomplete",
        "negative_router_sentinel",
    )
    report, _ = _validate(bundle, None)
    assert report.state == "BLOCKED"
    assert "missing_required_selection" in _codes(report)


# --- alias / batch / tier handling -------------------------------------------


def test_alias_rows_proposed_under_exact_id_and_batch_excluded() -> None:
    world = World()
    world.or_rows.append(_or_row("~synth/alias", inp="0.3", out="0.9"))
    bundle = _collect(world, providers=("openrouter",))
    proposed = _proposed_models(bundle)
    assert "openrouter/~synth/alias" in proposed
    assert "openrouter/synth/alias" not in proposed
    assert _inventory(bundle)[("openrouter", "synth/alpha:batch")] == (
        "excluded_subset",
        "service_variant",
    )
    report, _ = _validate(bundle, None)
    assert report.state == "READY", (report.state, sorted(_codes(report)))


def test_long_band_prices_never_proposed() -> None:
    bundle = _collect(World(), providers=("openai",))
    gpt2 = next(p for p in bundle.pricing if p.model == "gpt-syn-2")
    dims = {d.name: d.value for d in gpt2.dimensions}
    # short row only; the world's long values must not leak into the proposal
    assert dims == {"input": "1.08", "cached_input": "0.108", "output": "4.32"}
    assert not any("long" in d.name for d in gpt2.dimensions)


def test_page_price_conflict_is_not_proposed() -> None:
    world = World()
    # page says input 0.99, table says 0.54 -> authoritative conflict
    world.pages["gpt-syn-1"] = _page("gpt-syn-1", inp="0.99")
    bundle = _collect(world, providers=("openai",))
    assert "openai/gpt-syn-1" not in _proposed_models(bundle)
    assert _inventory(bundle)[("openai", "gpt-syn-1")] == (
        "incomplete",
        "page_price_conflict",
    )
    report, _ = _validate(bundle, None)
    assert report.state == "READY", sorted(_codes(report))


def test_page_with_conflicting_tables_parse_fails_closed() -> None:
    world = World()
    double_table = (
        _page("gpt-syn-1")
        + b"\n## Text tokens\n\n| Metric | Price | Unit |\n|---|---|---|\n"
        b"| Input | $0.99 | 1M tokens |\n| Output | $2.16 | 1M tokens |\n"
    )
    world.pages["gpt-syn-1"] = double_table
    bundle = _collect(world, providers=("openai",))
    assert "openai/gpt-syn-1" not in _proposed_models(bundle)
    assert _inventory(bundle)[("openai", "gpt-syn-1")] == (
        "incomplete",
        "page_parse_failed",
    )


def test_page_404_records_failed_retrieval_and_incomplete() -> None:
    world = World()
    del world.pages["gpt-syn-1"]
    bundle = _collect(world, providers=("openai",))
    assert "openai/gpt-syn-1" not in _proposed_models(bundle)
    assert _inventory(bundle)[("openai", "gpt-syn-1")] == ("incomplete", "page_unavailable")
    failed = [r for r in bundle.collection.retrievals if r.outcome == "failed"]
    assert len(failed) == 1
    assert failed[0].status == 404
    assert failed[0].failure_code == "http_404"
    assert failed[0].content_sha256 is None
    report, _ = _validate(bundle, None)
    # an optional page 404 is an observed incompleteness, not a disappearance
    assert report.state == "READY", sorted(_codes(report))


# --- retrieval failures -------------------------------------------------------


def test_catalog_retrieval_failure_blocks_never_disappearance() -> None:
    world = World()
    world.statuses[OR_URL] = 503
    bundle = _collect(world)
    report, _ = _validate(bundle, None)
    assert report.state == "BLOCKED"
    codes = _codes(report)
    assert "collection_retrieval_failed" in codes
    # and the models must NOT be reported as disappeared
    assert "disappearance" not in report.state_reason.lower()


def test_ecb_failure_blocks_fx_binding() -> None:
    world = World()
    world.statuses[ECB_URL] = 503
    bundle = _collect(world, providers=("openrouter",))
    assert bundle.fx == ()
    failed = [r for r in bundle.collection.retrievals if r.outcome == "failed"]
    assert any(r.requested_url == ECB_URL for r in failed)
    report, _ = _validate(bundle, None)
    assert report.state == "BLOCKED"
    assert any(c.startswith("fx") for c in _codes(report)), sorted(_codes(report))


# --- refresh preservation ------------------------------------------------------


def test_refresh_preserves_baseline_route_attributes_and_denials() -> None:
    world = World()
    baseline = _baseline_doc(
        routes={
            "synth/alpha": {
                "priority": 200,
                "enabled": False,
                "visible": False,
                "streaming": False,
                "caps": {"chat_completions": {"chat_text": True, "chat_streaming": False}},
            }
        },
        pricing={
            "synth/alpha": {"input": "0.54", "output": "2.16", "cached": "0.054"}
        },
    )
    bundle = _collect(
        world,
        providers=("openrouter",),
        baseline=baseline,
        baseline_mode="exported_file",
    )
    route = next(r for r in bundle.routes if r.requested_model == "synth/alpha")
    assert route.priority == 200
    assert route.enabled is False
    assert route.visible_in_models is False
    assert route.supports_streaming is False
    # explicit denial preserved: text kept, streaming denied, nothing granted
    assert route.capabilities == {"text": True, "streaming": False}
    assert "function_tools" not in route.capabilities
    report, _ = _validate(bundle, baseline)
    assert report.state == "READY", (report.state, sorted(_codes(report)))


def test_baseline_contract_not_flat_is_retained_not_proposed() -> None:
    world = World()
    baseline = _baseline_doc(
        routes={"synth/alpha": {"unrep": True}},
        pricing={"synth/alpha": {"input": "0.54", "output": "2.16", "cached": "0.054"}},
    )
    bundle = _collect(
        world,
        providers=("openrouter",),
        baseline=baseline,
        baseline_mode="exported_file",
    )
    assert "openrouter/synth/alpha" not in _proposed_models(bundle)
    assert _inventory(bundle)[("openrouter", "synth/alpha")] == (
        "excluded_subset",
        "baseline_contract_not_flat",
    )
    report, _ = _validate(bundle, baseline)
    assert report.state == "READY", sorted(_codes(report))


def test_baseline_currency_mismatch_is_retained_not_proposed() -> None:
    world = World()
    baseline = _baseline_doc(
        routes={"synth/alpha": {}},
        pricing={"synth/alpha": {"input": "0.5", "output": "2", "cached": "0.05", "currency": "EUR"}},
    )
    bundle = _collect(
        world,
        providers=("openrouter",),
        baseline=baseline,
        baseline_mode="exported_file",
    )
    assert "openrouter/synth/alpha" not in _proposed_models(bundle)
    assert _inventory(bundle)[("openrouter", "synth/alpha")] == (
        "excluded_subset",
        "baseline_currency_mismatch",
    )


# --- collection identity integrity gates ---------------------------------------


def _roundtrip_bundle(bundle):
    """Re-load the canonical bundle bytes (schema round-trip)."""
    from slaif_gateway.services.catalog_refresh.bundle import canonical_bundle_bytes, load_bundle

    return load_bundle(canonical_bundle_bytes(bundle))


def test_fabricated_inventory_entry_blocks() -> None:
    bundle = _roundtrip_bundle(_collect(World(), providers=("openrouter",)))
    from slaif_gateway.schemas.catalog_refresh import CollectionIdentity

    data = bundle.collection.model_dump(mode="json")
    data["inventory"] = list(data["inventory"]) + [
        {
            "provider": "openrouter",
            "model": "synth/fabricated",
            "disposition": "unsupported",
            "reason_code": "non_text_modality",
            "detail": "fabricated in test",
        }
    ]
    bundle = bundle.model_copy(update={"collection": CollectionIdentity.model_validate(data)})
    report, _ = _validate(bundle, None)
    assert report.state == "BLOCKED"
    assert "collection_inventory_unsupported" in _codes(report)


def test_source_without_matching_retrieval_blocks() -> None:
    bundle = _roundtrip_bundle(_collect(World(), providers=("openrouter",)))
    from slaif_gateway.schemas.catalog_refresh import CollectionIdentity

    # drop the catalog retrieval record: the source digest is now unbacked
    data = bundle.collection.model_dump(mode="json")
    data["retrievals"] = [r for r in data["retrievals"] if r["requested_url"] != OR_URL]
    bundle = bundle.model_copy(update={"collection": CollectionIdentity.model_validate(data)})
    report, _ = _validate(bundle, None)
    assert report.state == "BLOCKED"
    assert "collection_source_unbacked" in _codes(report)


def test_supplied_bundle_replay_is_offline_scope() -> None:
    collected = _collect(World(), providers=("openrouter",))
    # a bundle reviewed without its collection identity is an offline replay
    supplied = collected.model_copy(update={"collection": None})
    report, _ = _validate(supplied, None)
    assert report.to_dict()["source_evidence"]["scope"] == "offline_replay"
    live_report, _ = _validate(collected, None)
    assert live_report.to_dict()["source_evidence"]["scope"] == "live_collection"


# --- collector input contract ---------------------------------------------------


def test_collect_bundle_baseline_mode_contract() -> None:
    world = World()
    with pytest.raises(CatalogRefreshBlockedError) as exc:
        coll.collect_bundle(
            providers=("openrouter",),
            baseline_mode="first_install",
            baseline=_baseline_doc(),
            client=world.client(),
            resolve=_resolve_public,
            now=NOW,
        )
    assert exc.value.code == "collection_baseline_mismatch"
    with pytest.raises(CatalogRefreshBlockedError) as exc:
        coll.collect_bundle(
            providers=("openrouter",),
            baseline_mode="exported_file",
            baseline=None,
            client=world.client(),
            resolve=_resolve_public,
            now=NOW,
        )
    assert exc.value.code == "collection_baseline_missing"
    with pytest.raises(CatalogRefreshBlockedError) as exc:
        coll.collect_bundle(
            providers=("anthropic",),
            baseline_mode="first_install",
            baseline=None,
            client=world.client(),
            resolve=_resolve_public,
            now=NOW,
        )
    assert exc.value.code == "collection_providers_invalid"


# --- CLI end-to-end (mocked world, real pipeline) -------------------------------


def test_cli_collect_bootstrap_publishes_sealed_run(tmp_path, monkeypatch) -> None:
    from typer.testing import CliRunner

    from slaif_gateway.cli.main import app

    world = World()
    monkeypatch.setattr(
        src, "new_client", lambda: world.client()
    )
    run_root = tmp_path / "runs"
    key = tmp_path / "seal.key"
    result = CliRunner().invoke(
        app,
        [
            "catalog-refresh",
            "collect",
            "--bootstrap",
            "--providers",
            "openrouter",
            "--run-root",
            str(run_root),
            "--seal-key",
            str(key),
        ],
    )
    assert result.exit_code in (0, 10), result.output
    run_dirs = sorted(p for p in run_root.iterdir() if p.is_dir())
    assert len(run_dirs) == 1
    run_dir = run_dirs[0]
    assert (run_dir / "REVIEW.html").is_file()
    assert (run_dir / "validation.json").is_file()
    assert (run_dir / "receipt.json").is_file()
    html = (run_dir / "REVIEW.html").read_text(encoding="utf-8")
    assert "#collection-details" in html
    assert "live-collection scope" in html

    verify = CliRunner().invoke(
        app,
        [
            "catalog-refresh",
            "verify",
            "--run-dir",
            str(run_dir),
            "--seal-key",
            str(key),
        ],
    )
    assert verify.exit_code == 0, verify.output
    assert "valid: yes" in verify.output


def test_cli_collect_blocked_world_publishes_blocked_run(tmp_path, monkeypatch) -> None:
    from typer.testing import CliRunner

    from slaif_gateway.cli.main import app

    world = World()
    world.statuses[OR_URL] = 503
    monkeypatch.setattr(src, "new_client", lambda: world.client())
    run_root = tmp_path / "runs"
    key = tmp_path / "seal.key"
    result = CliRunner().invoke(
        app,
        [
            "catalog-refresh",
            "collect",
            "--bootstrap",
            "--providers",
            "openrouter",
            "--run-root",
            str(run_root),
            "--seal-key",
            str(key),
        ],
    )
    assert result.exit_code == 20, result.output
    run_dirs = sorted(p for p in run_root.iterdir() if p.is_dir())
    assert len(run_dirs) == 1
    validation = json.loads((run_dirs[0] / "validation.json").read_text())
    assert validation["state"] == "BLOCKED"
    assert "collection_retrieval_failed" in validation["state_reason"]
