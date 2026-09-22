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
from datetime import UTC, datetime, timedelta
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
from slaif_gateway.services.catalog_refresh import source_evidence as se
from slaif_gateway.services.catalog_refresh import sources as src
from slaif_gateway.services.catalog_refresh.baseline import canonical_baseline_content
from slaif_gateway.services.catalog_refresh.bundle import canonical_bundle_bytes
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
    # Current official linked-index format (bounded synthetic fixture):
    # model-page bullets (ID from the path, never the display name), a
    # duplicate across sections, and the documented specialized-models
    # bullet that declares its Model ID inline.
    models_md: bytes = field(
        default_factory=lambda: (
            "# Models\n\n"
            "## Featured models\n\n"
            "- [Synth One](/api/docs/models/gpt-syn-1.md): Start here.\n"
            "- [Synth Two](/api/docs/models/gpt-syn-2.md): Balanced.\n\n"
            "## Browse our full catalog of models\n\n"
            "- [gpt-syn-1](/api/docs/models/gpt-syn-1.md): Replacement for gpt-syn-0\n"
            "- [gpt-syn-2](/api/docs/models/gpt-syn-2.md): Balanced model\n"
            "- [gpt-syn-long](/api/docs/models/gpt-syn-long.md): Long context only\n"
            "- [Synth Special](/api/docs/pricing#specialized-models): "
            "Specialized. Model ID: `gpt-syn-special`.\n"
        ).encode("utf-8")
    )
    # Dynamic ECB publication date (current UTC date): the freshness gate
    # compares quote date against the review clock, so a static fixture
    # date is calendar-sensitive and would start blocking without any
    # code change. The CLI freshness-boundary tests pass explicit dates.
    ecb: bytes = field(
        default_factory=lambda: _ecb_xml(date_s=datetime.now(UTC).date().isoformat())
    )
    # Optional full replacement of the pricing document (tiered tables
    # beyond the standard six-column shape, e.g. Batch tier or cache-write
    # columns).
    pricing_md: bytes | None = None
    statuses: dict[str, int] = field(default_factory=dict)

    def handler(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url in self.statuses:
            return httpx.Response(self.statuses[url])
        if url == OR_URL:
            return httpx.Response(200, content=_or_payload(self.or_rows))
        if url == PRICING_URL:
            content = (
                self.pricing_md
                if self.pricing_md is not None
                else _pricing_md(self.pricing_rows)
            )
            return httpx.Response(200, content=content)
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

    # 181-b (B1): gpt-syn-1 publishes long-context standard prices, so the
    # flat standard proposal cannot bill it faithfully: it is excluded with
    # the exact policy reason (its page is never even fetched), while the
    # flat, complete siblings stay usable.
    assert _proposed_models(bundle) == {
        "openrouter/synth/alpha",
        "openrouter/synth/beta",
        "openai/gpt-syn-2",
    }
    inv = _inventory(bundle)
    assert inv[("openrouter", "synth/alpha:batch")] == ("excluded_subset", "service_variant")
    assert inv[("openrouter", "synth/deprecated")] == ("deprecated", "deprecated_model")
    assert inv[("openrouter", "synth/nolimits")] == ("incomplete", "missing_limits")
    assert inv[("openrouter", "synth/sentinel")] == ("incomplete", "negative_router_sentinel")
    assert inv[("openrouter", "synth/image")] == ("unsupported", "non_text_modality")
    assert inv[("openrouter", "synth/halfprice")] == ("incomplete", "missing_core_prices")
    assert inv[("openai", "gpt-syn-1")] == (
        "excluded_subset",
        "long_context_prices_unrepresentable",
    )
    assert inv[("openai", "gpt-syn-long")] == ("incomplete", "no_standard_short_prices")
    # 181-b (B3): the fetched models index is model evidence; the
    # index-only ID (no standard pricing rows at all) is reconciled with
    # exactly one explained disposition.
    assert inv[("openai", "gpt-syn-special")] == (
        "incomplete",
        "index_only_no_standard_prices",
    )
    # every observed model reconciled exactly once (pricing rows AND the
    # index identities, source counts distinct from route/alias rows)
    index_ids = {"gpt-syn-1", "gpt-syn-2", "gpt-syn-long", "gpt-syn-special"}
    observed = {
        ("openrouter", r["id"]) for r in World().or_rows
    } | {("openai", row[0]) for row in World().pricing_rows} | {("openai", m) for m in index_ids}
    assert set(inv) | {
        (m.provider, m.model) for m in bundle.models
    } == observed
    # source model counts: distinct observed source identities per provider
    assert bundle.collection.source_model_counts == {"openai": 4, "openrouter": 8}

    # retrieval records: one per unique URL fetched (4 phase-1 + 1 page + 1 ecb);
    # gpt-syn-1's page is never fetched (excluded before retrieval)
    urls = {r.requested_url for r in bundle.collection.retrievals}
    assert OR_URL in urls and PRICING_URL in urls and MODELS_MD_URL in urls
    assert f"{PAGE_PREFIX}gpt-syn-2.md" in urls
    assert f"{PAGE_PREFIX}gpt-syn-1.md" not in urls
    assert ECB_URL in urls
    assert all(r.outcome == "ok" for r in bundle.collection.retrievals)

    report, artifacts = _validate(bundle, None)
    assert report.state == "READY", (report.state, sorted(_codes(report)))
    assert report.to_dict()["source_evidence"]["scope"] == "live_collection"
    assert report.to_dict()["source_evidence"]["collection"]["source_model_counts"] == {
        "openai": 4,
        "openrouter": 8,
    }

    # standard-v1 proposes short-context core pricing only (never long band)
    gpt2 = next(p for p in bundle.pricing if p.model == "gpt-syn-2")
    dims = {d.name: d.value for d in gpt2.dimensions}
    assert dims == {"input": "1.08", "cached_input": "0.108", "output": "4.32"}
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
        World(), providers=("openai",), model_include=("gpt-syn-2",)
    )
    assert _proposed_models(bundle) == {"openai/gpt-syn-2"}
    inv = _inventory(bundle)
    # the ineligible sibling carries its exact billing reason (checked
    # before selection), not a selection reason
    assert inv[("openai", "gpt-syn-1")] == (
        "excluded_subset",
        "long_context_prices_unrepresentable",
    )
    assert inv[("openai", "gpt-syn-long")] == ("incomplete", "no_standard_short_prices")
    # only the selected model's page was fetched
    page_urls = [u for u in {r.requested_url for r in bundle.collection.retrievals} if u.startswith(PAGE_PREFIX)]
    assert page_urls == [f"{PAGE_PREFIX}gpt-syn-2.md"]
    report, _ = _validate(bundle, None)
    assert report.state == "READY", (report.state, sorted(_codes(report)))


def test_explicit_selection_of_billing_ineligible_model_blocks() -> None:
    """181-b (B1) strategic reproducer: an OpenAI model with published
    long-context standard prices is explicitly selected. The collector
    must not flatten the long tier into the short band: the model is
    excluded with the exact policy reason and the explicit selection
    BLOCKS (missing_required_selection), never READY."""
    world = World()
    world.pages["gpt-syn-1"] = _page("gpt-syn-1", context=1000000)
    bundle = _collect(world, providers=("openai",), model_include=("gpt-syn-1",))
    assert _proposed_models(bundle) == set()
    assert _inventory(bundle)[("openai", "gpt-syn-1")] == (
        "excluded_subset",
        "long_context_prices_unrepresentable",
    )
    report, _ = _validate(bundle, None)
    assert report.state == "BLOCKED", sorted(_codes(report))
    assert "missing_required_selection" in _codes(report)
    # no proposal leaked long-band values at short-band identity
    assert bundle.pricing == ()


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
    # page says input 0.99, table says 1.08 -> authoritative conflict
    world.pages["gpt-syn-2"] = _page("gpt-syn-2", inp="0.99", cached="0.108", out="4.32")
    bundle = _collect(world)
    assert "openai/gpt-syn-2" not in _proposed_models(bundle)
    assert _inventory(bundle)[("openai", "gpt-syn-2")] == (
        "incomplete",
        "page_price_conflict",
    )
    # flat, complete siblings stay usable in default discovery
    assert _proposed_models(bundle) == {
        "openrouter/synth/alpha",
        "openrouter/synth/beta",
    }
    report, _ = _validate(bundle, None)
    assert report.state == "READY", sorted(_codes(report))


def test_page_with_conflicting_tables_parse_fails_closed() -> None:
    world = World()
    double_table = (
        _page("gpt-syn-2", inp="1.08", cached="0.108", out="4.32")
        + b"\n## Text tokens\n\n| Metric | Price | Unit |\n|---|---|---|\n"
        b"| Input | $0.99 | 1M tokens |\n| Output | $4.32 | 1M tokens |\n"
    )
    world.pages["gpt-syn-2"] = double_table
    bundle = _collect(world, providers=("openai",))
    assert "openai/gpt-syn-2" not in _proposed_models(bundle)
    assert _inventory(bundle)[("openai", "gpt-syn-2")] == (
        "incomplete",
        "page_parse_failed",
    )


def test_page_404_records_failed_retrieval_and_incomplete() -> None:
    world = World()
    del world.pages["gpt-syn-2"]
    bundle = _collect(world)
    assert "openai/gpt-syn-2" not in _proposed_models(bundle)
    assert _inventory(bundle)[("openai", "gpt-syn-2")] == ("incomplete", "page_unavailable")
    failed = [r for r in bundle.collection.retrievals if r.outcome == "failed"]
    assert len(failed) == 1
    assert failed[0].status == 404
    assert failed[0].failure_code == "http_404"
    assert failed[0].content_sha256 is None
    # siblings stay usable; the 404 is an observed incompleteness, not a
    # disappearance and not a provider-wide failure
    assert _proposed_models(bundle) == {
        "openrouter/synth/alpha",
        "openrouter/synth/beta",
    }
    report, _ = _validate(bundle, None)
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


# --- 181-b (B1): shared flat billing eligibility ---------------------------------


def _router_world_with_pricing_field(field_name: str, value: str) -> World:
    """Single OpenRouter world carrying one extra published pricing key."""
    row = _or_row("synth/alpha")
    row["pricing"][field_name] = value
    world = World()
    world.or_rows = [row]
    return world


def _rebuild_frozen(model, **updates):
    """Rebuild a frozen fact model with field updates (schema round-trip)."""
    return type(model).model_validate({**model.model_dump(mode="json"), **updates})


def test_router_cache_write_charge_excluded_and_selection_blocks() -> None:
    """181-b (B1) strategic reproducer: a positive cache-write charge must
    never be silently dropped from the proposal. The row is excluded with
    the exact policy reason, and explicitly requesting that row BLOCKs."""
    world = _router_world_with_pricing_field("input_cache_write", "0.000009")
    bundle = _collect(world, providers=("openrouter",))
    assert _proposed_models(bundle) == set()
    assert _inventory(bundle)[("openrouter", "synth/alpha")] == (
        "excluded_subset",
        "cache_write_charges_unrepresentable",
    )
    selected = _collect(
        world, providers=("openrouter",), model_include=("synth/alpha",)
    )
    report, _ = _validate(selected, None)
    assert report.state == "BLOCKED", sorted(_codes(report))
    assert "missing_required_selection" in _codes(report)


def test_router_1h_cache_write_charge_excluded() -> None:
    world = _router_world_with_pricing_field("input_cache_write_1h", "0.000009")
    bundle = _collect(world, providers=("openrouter",))
    assert _proposed_models(bundle) == set()
    assert _inventory(bundle)[("openrouter", "synth/alpha")] == (
        "excluded_subset",
        "cache_write_charges_unrepresentable",
    )


def test_router_zero_cache_write_is_no_charge_not_missing() -> None:
    world = _router_world_with_pricing_field("input_cache_write", "0")
    bundle = _collect(world, providers=("openrouter",))
    assert _proposed_models(bundle) == {"openrouter/synth/alpha"}
    pricing = next(item for item in bundle.pricing if item.model == "synth/alpha")
    assert {d.name for d in pricing.dimensions} == {"input", "cached_input", "output"}
    report, _ = _validate(bundle, None)
    assert report.state == "READY", sorted(_codes(report))


def test_router_reasoning_charge_excluded_under_standard_v1() -> None:
    """181-c (C1) strategic reproducer: a positive separately billed
    reasoning charge must not produce a ready standard-v1 row - ordinary
    Chat admission reserves at the output price and no qualified reasoning
    billing contract is authorized. Default discovery retains the flat
    siblings; an explicitly selected excluded model BLOCKs."""
    charged = _or_row("synth/alpha")
    charged["pricing"]["internal_reasoning"] = "0.000009"
    world = World()
    world.or_rows = [charged, _or_row("synth/beta", inp="0.1", out="0.4")]
    bundle = _collect(world, providers=("openrouter",))
    assert _proposed_models(bundle) == {"openrouter/synth/beta"}
    assert _inventory(bundle)[("openrouter", "synth/alpha")] == (
        "excluded_subset",
        "reasoning_charges_unrepresentable",
    )
    selected = _collect(
        world, providers=("openrouter",), model_include=("synth/alpha",)
    )
    report, _ = _validate(selected, None)
    assert report.state == "BLOCKED", sorted(_codes(report))
    assert "missing_required_selection" in _codes(report)


def test_router_zero_reasoning_charge_carried_as_no_charge() -> None:
    """181-c (C1): a published ZERO reasoning price is an explicit
    no-charge, never a missing fact: the proposal carries it exactly,
    because a missing price would make finalization bill reasoning tokens
    at the output price (a change of actual local billing)."""
    world = _router_world_with_pricing_field("internal_reasoning", "0")
    bundle = _collect(world, providers=("openrouter",))
    assert _proposed_models(bundle) == {"openrouter/synth/alpha"}
    pricing = next(item for item in bundle.pricing if item.model == "synth/alpha")
    dims = {d.name: (d.value, d.unit) for d in pricing.dimensions}
    assert dims["reasoning"] == ("0", "per_1m_tokens")
    assert dims["input"] == ("0.54", "per_1m_tokens")
    assert dims["output"] == ("2.16", "per_1m_tokens")
    report, _ = _validate(bundle, None)
    assert report.state == "READY", sorted(_codes(report))


def test_router_request_charge_excluded_under_standard_v1() -> None:
    """181-c (C1) strategic reproducer: a positive per-request fee must not
    produce a ready standard-v1 row - ordinary Chat admission and
    finalization do not bill an additive per-request fee (the column serves
    native-module contracts). Flat siblings stay; explicit selection BLOCKs."""
    charged = _or_row("synth/alpha")
    charged["pricing"]["request"] = "0.1"
    world = World()
    world.or_rows = [charged, _or_row("synth/beta", inp="0.1", out="0.4")]
    bundle = _collect(world, providers=("openrouter",))
    assert _proposed_models(bundle) == {"openrouter/synth/beta"}
    assert _inventory(bundle)[("openrouter", "synth/alpha")] == (
        "excluded_subset",
        "request_charges_unrepresentable",
    )
    selected = _collect(
        world, providers=("openrouter",), model_include=("synth/alpha",)
    )
    report, _ = _validate(selected, None)
    assert report.state == "BLOCKED", sorted(_codes(report))
    assert "missing_required_selection" in _codes(report)


def test_router_zero_request_charge_is_no_charge_not_missing() -> None:
    """181-c (C1) zero semantics: a published zero per-request fee is a
    documented no-charge - ordinary Chat bills no per-request fee at all,
    so carrying nothing changes no local billing."""
    world = _router_world_with_pricing_field("request", "0")
    bundle = _collect(world, providers=("openrouter",))
    assert _proposed_models(bundle) == {"openrouter/synth/alpha"}
    pricing = next(item for item in bundle.pricing if item.model == "synth/alpha")
    assert {d.name for d in pricing.dimensions} == {"input", "cached_input", "output"}
    report, _ = _validate(bundle, None)
    assert report.state == "READY", sorted(_codes(report))


def test_router_tiny_positive_request_charge_excluded() -> None:
    # 181-c (C1): ANY positive per-request fee excludes the row - the
    # executable-billing gate fires before the import-quantum gate, so a
    # below-quantum fee is excluded with the exact billing reason and never
    # stored as a free price.
    world = _router_world_with_pricing_field("request", "0.0000000001")
    bundle = _collect(world, providers=("openrouter",))
    assert _proposed_models(bundle) == set()
    assert _inventory(bundle)[("openrouter", "synth/alpha")] == (
        "excluded_subset",
        "request_charges_unrepresentable",
    )


def test_router_contextual_overrides_excluded() -> None:
    world = _router_world_with_pricing_field(
        "overrides",
        [{"prompt": "0.000009", "completion": "0.000018", "min_prompt_tokens": 200000}],
    )
    bundle = _collect(world, providers=("openrouter",))
    assert _proposed_models(bundle) == set()
    assert _inventory(bundle)[("openrouter", "synth/alpha")] == (
        "excluded_subset",
        "contextual_overrides_unrepresentable",
    )


def test_router_stringified_overrides_excluded() -> None:
    world = _router_world_with_pricing_field(
        "overrides",
        "[{'prompt': '0.000009', 'completion': '0.000018', 'min_prompt_tokens': 200000}]",
    )
    bundle = _collect(world, providers=("openrouter",))
    assert _proposed_models(bundle) == set()
    assert _inventory(bundle)[("openrouter", "synth/alpha")] == (
        "excluded_subset",
        "contextual_overrides_unrepresentable",
    )


def test_router_unknown_pricing_key_excluded_fail_closed() -> None:
    world = _router_world_with_pricing_field("per_image", "0.000000001")
    bundle = _collect(world, providers=("openrouter",))
    assert _proposed_models(bundle) == set()
    assert _inventory(bundle)[("openrouter", "synth/alpha")] == (
        "excluded_subset",
        "unknown_billing_dimension",
    )


def test_router_sentinel_on_billable_extra_excluded() -> None:
    # A -1 sentinel on a billable extra dimension is an unverifiable
    # charge: fail-closed exclusion, never a silent no-charge.
    world = _router_world_with_pricing_field("input_cache_write", "-1")
    bundle = _collect(world, providers=("openrouter",))
    assert _proposed_models(bundle) == set()
    assert _inventory(bundle)[("openrouter", "synth/alpha")] == (
        "excluded_subset",
        "negative_router_sentinel",
    )


def test_router_web_search_charge_excluded() -> None:
    """181-c (C2) strategic reproducer: a positive hosted-operation charge
    is EXCLUDED with the exact machine reason - no blanket 'accepted
    unreachable' assertion (hosted operations are denied in the profile and
    no reviewed per-model executable contract proves the charge cannot be
    incurred)."""
    world = _router_world_with_pricing_field("web_search", "0.01")
    bundle = _collect(world, providers=("openrouter",))
    assert _proposed_models(bundle) == set()
    assert _inventory(bundle)[("openrouter", "synth/alpha")] == (
        "excluded_subset",
        "hosted_operation_charges_unrepresentable",
    )
    report, _ = _validate(bundle, None)
    assert all("accepted unreachable" not in w.detail for w in report.warnings)
    # the only observed model is excluded => the usable bootstrap is empty
    assert report.state == "BLOCKED", sorted(_codes(report))
    assert "collection_empty_bootstrap" in _codes(report)


def test_router_online_variant_hosted_charge_excluded_and_sibling_kept() -> None:
    """181-c (C2): model variants or intrinsic hosted-style identities are
    never declared safe by analogy with optional tools - a :online-style ID
    with a positive hosted charge is excluded on the price (identity is not
    laundering), identically to an ordinary flat ID; the flat sibling stays
    proposed."""
    online = _or_row("synth/alpha:online")
    online["pricing"]["web_search"] = "0.01"
    world = World()
    world.or_rows = [online, _or_row("synth/beta", inp="0.1", out="0.4")]
    bundle = _collect(world, providers=("openrouter",))
    assert _proposed_models(bundle) == {"openrouter/synth/beta"}
    assert _inventory(bundle)[("openrouter", "synth/alpha:online")] == (
        "excluded_subset",
        "hosted_operation_charges_unrepresentable",
    )
    plain = _or_row("synth/alpha")
    plain["pricing"]["web_search"] = "0.01"
    world2 = World()
    world2.or_rows = [plain]
    bundle2 = _collect(world2, providers=("openrouter",))
    assert _inventory(bundle2)[("openrouter", "synth/alpha")] == (
        "excluded_subset",
        "hosted_operation_charges_unrepresentable",
    )


def test_router_zero_web_search_is_no_charge_not_missing() -> None:
    """181-c (C2) zero semantics: a published zero web-search charge is a
    no-charge (the standard chat contract has no web-search billing
    dimension and a zero publishes no provider-side cost): the row stays
    proposed with core dims only."""
    world = _router_world_with_pricing_field("web_search", "0")
    bundle = _collect(world, providers=("openrouter",))
    assert _proposed_models(bundle) == {"openrouter/synth/alpha"}
    pricing = next(item for item in bundle.pricing if item.model == "synth/alpha")
    assert {d.name for d in pricing.dimensions} == {"input", "cached_input", "output"}
    report, _ = _validate(bundle, None)
    assert report.state == "READY", sorted(_codes(report))


def test_empty_usable_bootstrap_blocks() -> None:
    """181-b (B1): every observed model excluded => the usable bootstrap is
    empty and BLOCKs instead of publishing an empty proposal as READY."""
    world = World()
    world.or_rows = [_or_row("synth/sentinel", prompt="-1")]
    world.pricing_rows = [("gpt-syn-1", "0.54", "0.054", "2.16", "1.08", "4.32")]
    world.pages = {}
    bundle = _collect(world)
    assert _proposed_models(bundle) == set()
    report, _ = _validate(bundle, None)
    assert report.state == "BLOCKED", sorted(_codes(report))
    assert "collection_empty_bootstrap" in _codes(report)


# --- 181-b (B1): bypass negatives through supplied-bundle validation ----------


def test_supplied_bundle_dropping_carried_charge_blocks() -> None:
    """181-c (C1): removing the published ZERO reasoning no-charge from a
    collected bundle must block: the omission would change actual local
    billing (finalization would fall back to the output price)."""
    world = _router_world_with_pricing_field("internal_reasoning", "0")
    collected = _collect(world, providers=("openrouter",))
    bundle = _roundtrip_bundle(collected)
    pricing = next(item for item in bundle.pricing if item.model == "synth/alpha")
    stripped = _rebuild_frozen(
        pricing,
        dimensions=[d for d in pricing.dimensions if d.name != "reasoning"],
    )
    bundle = bundle.model_copy(update={"pricing": (stripped,)})
    report, _ = _validate(bundle, None)
    assert report.state == "BLOCKED", sorted(_codes(report))
    assert "proposed_row_billing_dim_missing" in _codes(report)


def test_supplied_bundle_altering_carried_charge_blocks() -> None:
    """181-c (C1): altering the carried zero reasoning no-charge to a
    positive value must block (it would publish an unbilled charge)."""
    world = _router_world_with_pricing_field("internal_reasoning", "0")
    collected = _collect(world, providers=("openrouter",))
    bundle = _roundtrip_bundle(collected)
    pricing = next(item for item in bundle.pricing if item.model == "synth/alpha")
    tampered = _rebuild_frozen(
        pricing,
        dimensions=[
            d
            if d.name != "reasoning"
            else _rebuild_frozen(d, value="8")
            for d in pricing.dimensions
        ],
    )
    bundle = bundle.model_copy(update={"pricing": (tampered,)})
    report, _ = _validate(bundle, None)
    assert report.state == "BLOCKED", sorted(_codes(report))
    assert "proposed_row_billing_dim_mismatch" in _codes(report)


def test_supplied_bundle_ineligible_proposal_blocks() -> None:
    """Injecting a ready proposal for a model whose official observations
    are not flat-billable must block with the exact policy reason."""
    from slaif_gateway.schemas.catalog_refresh import (
        FieldProvenance,
        ModelFacts,
        ModelPricingFacts,
        PricingDimension,
        RouteFacts,
    )

    world = _router_world_with_pricing_field("input_cache_write", "0.000009")
    collected = _collect(world, providers=("openrouter",))
    bundle = _roundtrip_bundle(collected)
    prov = FieldProvenance(
        sources=("openrouter|catalog|openrouter_models_api",),
        extractor=coll.EXTRACTOR_ID,
        extraction="deterministic",
    )
    route = RouteFacts(
        provider="openrouter",
        requested_model="synth/alpha",
        upstream_model="synth/alpha",
        match_type="exact",
        endpoint="/v1/chat/completions",
        priority=100,
        enabled=True,
        visible_in_models=True,
        supports_streaming=True,
        capabilities={"text": True, "streaming": True},
        provenance=prov,
    )
    model = ModelFacts(
        provider="openrouter",
        model="synth/alpha",
        display_name="synth/alpha",
        context_length=128000,
        max_output_tokens=8192,
        supports_streaming=True,
        capabilities={"text": True, "streaming": True},
        deprecated=False,
        provenance=prov,
    )
    pricing = ModelPricingFacts(
        provider="openrouter",
        model="synth/alpha",
        endpoint="/v1/chat/completions",
        currency="USD",
        dimensions=(
            PricingDimension(name="input", value="0.54", unit="per_1m_tokens", currency="USD"),
            PricingDimension(name="cached_input", value="0.054", unit="per_1m_tokens", currency="USD"),
            PricingDimension(name="output", value="2.16", unit="per_1m_tokens", currency="USD"),
        ),
        valid_from=collected.generated_at,
        provenance=prov,
    )
    bundle = bundle.model_copy(
        update={
            "routes": bundle.routes + (route,),
            "models": bundle.models + (model,),
            "pricing": bundle.pricing + (pricing,),
        }
    )
    report, _ = _validate(bundle, None)
    assert report.state == "BLOCKED", sorted(_codes(report))
    assert "proposed_row_billing_ineligible" in _codes(report)
    ineligible = next(
        w for w in report.warnings if w.code == "proposed_row_billing_ineligible"
    )
    assert "cache_write_charges_unrepresentable" in ineligible.detail


# --- 181-b (B1): OpenAI tier, band, and extra-dimension cases ------------------


def test_openai_long_zero_price_still_excluded() -> None:
    # A published $0 long-context standard price is still a contextual
    # price: the flat short-band proposal cannot bill the model faithfully.
    world = World()
    world.pricing_rows = [
        ("gpt-syn-2", "1.08", "0.108", "4.32", "0", "0"),
        ("gpt-syn-3", "0.54", "0.054", "2.16", None, None),
    ]
    world.pages = {
        "gpt-syn-2": _page("gpt-syn-2", inp="1.08", cached="0.108", out="4.32"),
        "gpt-syn-3": _page("gpt-syn-3"),
    }
    bundle = _collect(world, providers=("openai",))
    assert _proposed_models(bundle) == {"openai/gpt-syn-3"}
    assert _inventory(bundle)[("openai", "gpt-syn-2")] == (
        "excluded_subset",
        "long_context_prices_unrepresentable",
    )
    # eligibility is decided before page retrieval: no wasted fetch
    page_urls = [
        u
        for u in {r.requested_url for r in bundle.collection.retrievals}
        if u.startswith(PAGE_PREFIX)
    ]
    assert page_urls == [f"{PAGE_PREFIX}gpt-syn-3.md"]
    report, _ = _validate(bundle, None)
    assert report.state == "READY", sorted(_codes(report))


def test_openai_batch_tier_is_service_variant_not_context_band() -> None:
    # Batch is a distinct service variant of the same model (mirroring the
    # OpenRouter :batch handling): it never blocks the standard tier.
    world = World()
    world.pricing_rows = []
    world.pricing_md = (
        "# Pricing\n\n"
        "### Standard pricing data\n\n"
        "| Model | Short context input | Short context output |\n"
        "|---|---|---|\n"
        "| gpt-syn-batch | $0.54 | $2.16 |\n\n"
        "### Batch pricing data\n\n"
        "| Model | Short context input | Short context output |\n"
        "|---|---|---|\n"
        "| gpt-syn-batch | $0.10 | $0.40 |\n"
    ).encode("utf-8")
    world.pages = {"gpt-syn-batch": _page("gpt-syn-batch")}
    bundle = _collect(world, providers=("openai",))
    assert _proposed_models(bundle) == {"openai/gpt-syn-batch"}
    assert ("openai", "gpt-syn-batch") not in _inventory(bundle)
    report, _ = _validate(bundle, None)
    assert report.state == "READY", sorted(_codes(report))


def test_openai_cache_write_charge_excluded() -> None:
    world = World()
    world.pricing_rows = []
    world.pricing_md = (
        "# Pricing\n\n"
        "### Standard pricing data\n\n"
        "| Model | Short context input | Short context cache writes | Short context output |\n"
        "|---|---|---|---|\n"
        "| gpt-syn-cw | $0.54 | $0.054 | $2.16 |\n"
    ).encode("utf-8")
    bundle = _collect(world, providers=("openai",))
    assert _proposed_models(bundle) == set()
    assert _inventory(bundle)[("openai", "gpt-syn-cw")] == (
        "excluded_subset",
        "cache_write_charges_unrepresentable",
    )


# --- 181-b (B2): local route authority preservation ----------------------------


def _alias_baseline(**route_spec) -> BaselineDocument:
    """Baseline holding ONE genuine public alias (name != upstream)."""
    baseline = _baseline_doc(routes={"public-alias": route_spec})
    return baseline.model_copy(
        update={
            "routes": tuple(
                r.model_copy(update={"upstream_model": "synth/alpha"})
                for r in baseline.routes
            )
        }
    )


def test_refresh_alias_preserves_local_route_identity_and_denials() -> None:
    """181-b (B2) strategic reproducer: a disabled/invisible/nonstreaming
    public alias with priority 77 and an explicit streaming denial must be
    preserved exactly - no new enabled upstream-named route, no false
    disappearance."""
    world = World()
    world.or_rows = [_or_row("synth/alpha")]
    baseline = _alias_baseline(
        enabled=False,
        visible=False,
        streaming=False,
        priority=77,
        caps={"chat_completions": {"chat_text": True, "chat_streaming": False}},
    )
    bundle = _collect(
        world,
        providers=("openrouter",),
        baseline=baseline,
        baseline_mode="exported_file",
    )
    assert [r.requested_model for r in bundle.routes] == ["public-alias"]
    (route,) = bundle.routes
    assert route.upstream_model == "synth/alpha"
    assert route.match_type == "exact"
    assert route.priority == 77
    assert route.enabled is False
    assert route.visible_in_models is False
    assert route.supports_streaming is False
    # explicit denial preserved: text kept, streaming denied, nothing granted
    assert route.capabilities == {"text": True, "streaming": False}
    assert "function_tools" not in route.capabilities
    report, _ = _validate(bundle, baseline)
    assert report.state == "READY", (report.state, sorted(_codes(report)))
    assert "model_disappeared" not in _codes(report)
    assert "alias_route_replaced" not in _codes(report)


def test_refresh_two_aliases_are_never_reduced() -> None:
    world = World()
    world.or_rows = [_or_row("synth/alpha")]
    baseline = _baseline_doc(
        routes={
            "alias-one": {
                "enabled": False,
                "visible": False,
                "streaming": False,
                "priority": 77,
                "caps": {"chat_completions": {"chat_text": True, "chat_streaming": False}},
            },
            "alias-two": {"priority": 33},
        }
    )
    baseline = baseline.model_copy(
        update={
            "routes": tuple(
                r.model_copy(update={"upstream_model": "synth/alpha"})
                for r in baseline.routes
            )
        }
    )
    bundle = _collect(
        world,
        providers=("openrouter",),
        baseline=baseline,
        baseline_mode="exported_file",
    )
    assert bundle.routes == ()
    assert _inventory(bundle)[("openrouter", "synth/alpha")] == (
        "excluded_subset",
        "baseline_multiple_routes",
    )
    report, _ = _validate(bundle, baseline)
    assert report.state == "READY", (report.state, sorted(_codes(report)))
    assert "model_disappeared" not in _codes(report)
    dispositions = {
        d.model: d.disposition for d in report.dispositions if d.model in ("alias-one", "alias-two")
    }
    assert dispositions == {"alias-one": "NOT_FETCHED", "alias-two": "NOT_FETCHED"}


def test_refresh_prefix_baseline_covers_upstream_retained() -> None:
    """181-c (C3): a PASSTHROUGH prefix (no fixed upstream) governs the
    upstreams whose identity matches the public pattern: retained locally
    with an explicit reason, never a parallel exact route, never a
    disappearance."""
    world = World()
    world.or_rows = [_or_row("synth/alpha")]
    baseline = _baseline_doc(routes={"synth/": {"priority": 50}})
    baseline = baseline.model_copy(
        update={
            "routes": tuple(
                r.model_copy(update={"match_type": "prefix", "upstream_model": ""})
                for r in baseline.routes
            )
        }
    )
    bundle = _collect(
        world,
        providers=("openrouter",),
        baseline=baseline,
        baseline_mode="exported_file",
    )
    assert bundle.routes == ()
    assert _inventory(bundle)[("openrouter", "synth/alpha")] == (
        "excluded_subset",
        "baseline_contract_not_flat",
    )
    report, _ = _validate(bundle, baseline)
    assert report.state == "READY", (report.state, sorted(_codes(report)))
    assert "model_disappeared" not in _codes(report)
    # the routing pattern is local state, retained with an explicit
    # deterministic disposition - never a source disappearance
    dispositions = {d.model: d.disposition for d in report.dispositions if d.model == "synth/"}
    assert dispositions == {"synth/": "NOT_FETCHED"}


def test_refresh_fixed_upstream_prefix_baseline_retained() -> None:
    """181-c (C3) strategic reproducer: a prefix route with a FIXED
    upstream_model governs that upstream even though the public pattern
    differs from the upstream ID (the resolver's destination rule, not
    public string similarity). The row is retained locally, NO parallel
    exact route is invented, and neither side is a source disappearance."""
    world = World()
    world.or_rows = [_or_row("synth/alpha")]
    baseline = _baseline_doc(
        routes={
            "public/": {
                "enabled": False,
                "visible": False,
                "streaming": False,
                "priority": 77,
                "caps": {"chat_completions": {"chat_text": True, "chat_streaming": False}},
            }
        }
    )
    baseline = baseline.model_copy(
        update={
            "routes": tuple(
                r.model_copy(update={"match_type": "prefix", "upstream_model": "synth/alpha"})
                for r in baseline.routes
            )
        }
    )
    bundle = _collect(
        world,
        providers=("openrouter",),
        baseline=baseline,
        baseline_mode="exported_file",
    )
    assert bundle.routes == ()
    assert _inventory(bundle)[("openrouter", "synth/alpha")] == (
        "excluded_subset",
        "baseline_contract_not_flat",
    )
    detail = next(
        e.detail for e in bundle.collection.inventory if e.model == "synth/alpha"
    )
    assert "public/" in detail and "synth/alpha" in detail
    report, artifacts = _validate(bundle, baseline)
    assert report.state == "READY", (report.state, sorted(_codes(report)))
    assert "model_disappeared" not in _codes(report)
    assert "wildcard_route_authority_bypassed" not in _codes(report)
    # artifact plan: the governed upstream is absent from the import artifacts
    # (no invented parallel route, no parallel pricing row)
    assert "synth/alpha" not in artifacts["routes-proposal.tsv"].decode()
    assert "synth/alpha" not in artifacts["pricing-proposal.tsv"].decode()
    dispositions = {
        d.model: d.disposition for d in report.dispositions if d.model == "public/"
    }
    assert dispositions == {"public/": "NOT_FETCHED"}


def test_refresh_glob_baseline_covers_upstream_retained() -> None:
    """181-c (C3): passthrough glob coverage, same retain-local semantics."""
    world = World()
    world.or_rows = [_or_row("synth/alpha")]
    baseline = _baseline_doc(routes={"synth/*": {"priority": 50}})
    baseline = baseline.model_copy(
        update={
            "routes": tuple(
                r.model_copy(update={"match_type": "glob", "upstream_model": ""})
                for r in baseline.routes
            )
        }
    )
    bundle = _collect(
        world,
        providers=("openrouter",),
        baseline=baseline,
        baseline_mode="exported_file",
    )
    assert bundle.routes == ()
    assert _inventory(bundle)[("openrouter", "synth/alpha")] == (
        "excluded_subset",
        "baseline_contract_not_flat",
    )
    report, _ = _validate(bundle, baseline)
    assert report.state == "READY", (report.state, sorted(_codes(report)))
    assert "model_disappeared" not in _codes(report)


def test_refresh_multiple_wildcard_alternatives_not_reduced() -> None:
    """181-c (C3): multiple governing wildcard rows are all recorded in the
    retention reason - alternatives are never reduced to one row."""
    world = World()
    world.or_rows = [_or_row("synth/alpha")]
    baseline = _baseline_doc(routes={"public/": {"priority": 77}, "alt/": {"priority": 42}})
    baseline = baseline.model_copy(
        update={
            "routes": tuple(
                r.model_copy(update={"match_type": "prefix", "upstream_model": "synth/alpha"})
                for r in baseline.routes
            )
        }
    )
    bundle = _collect(
        world,
        providers=("openrouter",),
        baseline=baseline,
        baseline_mode="exported_file",
    )
    assert bundle.routes == ()
    assert _inventory(bundle)[("openrouter", "synth/alpha")] == (
        "excluded_subset",
        "baseline_contract_not_flat",
    )
    detail = next(
        e.detail for e in bundle.collection.inventory if e.model == "synth/alpha"
    )
    assert "public/" in detail and "alt/" in detail
    report, _ = _validate(bundle, baseline)
    assert report.state == "READY", (report.state, sorted(_codes(report)))
    assert "model_disappeared" not in _codes(report)


def test_refresh_fixed_prefix_to_other_upstream_not_covered() -> None:
    """181-c (C3): a public prefix whose FIXED destination is another
    upstream does NOT govern this model - no broadening of public-prefix
    rules to every unconfigured model: the normal exact proposal proceeds."""
    world = World()
    world.or_rows = [_or_row("synth/alpha")]
    baseline = _baseline_doc(routes={"public/": {"priority": 77}})
    baseline = baseline.model_copy(
        update={
            "routes": tuple(
                r.model_copy(update={"match_type": "prefix", "upstream_model": "other/x"})
                for r in baseline.routes
            )
        }
    )
    bundle = _collect(
        world,
        providers=("openrouter",),
        baseline=baseline,
        baseline_mode="exported_file",
    )
    (route,) = bundle.routes
    assert route.requested_model == "synth/alpha"
    assert route.match_type == "exact"
    assert route.upstream_model == "synth/alpha"
    report, _ = _validate(bundle, baseline)
    assert report.state == "READY", (report.state, sorted(_codes(report)))
    assert "wildcard_route_authority_bypassed" not in _codes(report)


def test_supplied_bundle_replacing_alias_with_upstream_route_blocks() -> None:
    world = World()
    world.or_rows = [_or_row("synth/alpha")]
    baseline = _alias_baseline(
        enabled=False,
        visible=False,
        streaming=False,
        priority=77,
        caps={"chat_completions": {"chat_text": True, "chat_streaming": False}},
    )
    collected = _collect(
        world,
        providers=("openrouter",),
        baseline=baseline,
        baseline_mode="exported_file",
    )
    bundle = _roundtrip_bundle(collected)
    (alias_route,) = bundle.routes
    renamed = _rebuild_frozen(alias_route, requested_model="synth/alpha")
    bundle = bundle.model_copy(update={"routes": (renamed,)})
    report, _ = _validate(bundle, baseline)
    assert report.state == "BLOCKED", sorted(_codes(report))
    assert "alias_route_replaced" in _codes(report)


def test_supplied_bundle_parallel_upstream_route_blocks() -> None:
    world = World()
    world.or_rows = [_or_row("synth/alpha")]
    baseline = _alias_baseline(
        enabled=False,
        visible=False,
        streaming=False,
        priority=77,
        caps={"chat_completions": {"chat_text": True, "chat_streaming": False}},
    )
    collected = _collect(
        world,
        providers=("openrouter",),
        baseline=baseline,
        baseline_mode="exported_file",
    )
    bundle = _roundtrip_bundle(collected)
    (alias_route,) = bundle.routes
    parallel = _rebuild_frozen(alias_route, requested_model="synth/alpha")
    bundle = bundle.model_copy(update={"routes": bundle.routes + (parallel,)})
    report, _ = _validate(bundle, baseline)
    assert report.state == "BLOCKED", sorted(_codes(report))
    assert "alias_route_replaced" in _codes(report)


def test_supplied_bundle_parallel_wildcard_route_blocks() -> None:
    """181-c (C3): a supplied bundle that re-inserts a parallel exact route
    for an upstream governed by a baseline wildcard (fixed destination)
    must BLOCK, even though the row is otherwise flat and fully priced:
    the wildcard retains local authority over that upstream."""
    from slaif_gateway.schemas.catalog_refresh import (
        FieldProvenance,
        ModelFacts,
        ModelPricingFacts,
        PricingDimension,
        RouteFacts,
    )

    world = World()
    world.or_rows = [_or_row("synth/alpha")]
    baseline = _baseline_doc(
        routes={
            "public/": {
                "enabled": False,
                "visible": False,
                "streaming": False,
                "priority": 77,
                "caps": {"chat_completions": {"chat_text": True, "chat_streaming": False}},
            }
        }
    )
    baseline = baseline.model_copy(
        update={
            "routes": tuple(
                r.model_copy(update={"match_type": "prefix", "upstream_model": "synth/alpha"})
                for r in baseline.routes
            )
        }
    )
    collected = _collect(
        world,
        providers=("openrouter",),
        baseline=baseline,
        baseline_mode="exported_file",
    )
    assert collected.routes == ()  # the collector retains, never invents
    bundle = _roundtrip_bundle(collected)
    prov = FieldProvenance(
        sources=("openrouter|catalog|openrouter_models_api",),
        extractor=coll.EXTRACTOR_ID,
        extraction="deterministic",
    )
    route = RouteFacts(
        provider="openrouter",
        requested_model="synth/alpha",
        upstream_model="synth/alpha",
        match_type="exact",
        endpoint="/v1/chat/completions",
        priority=100,
        enabled=True,
        visible_in_models=True,
        supports_streaming=True,
        capabilities={"text": True, "streaming": True},
        provenance=prov,
    )
    model = ModelFacts(
        provider="openrouter",
        model="synth/alpha",
        display_name="synth/alpha",
        context_length=128000,
        max_output_tokens=8192,
        supports_streaming=True,
        capabilities={"text": True, "streaming": True},
        deprecated=False,
        provenance=prov,
    )
    pricing = ModelPricingFacts(
        provider="openrouter",
        model="synth/alpha",
        endpoint="/v1/chat/completions",
        currency="USD",
        dimensions=(
            PricingDimension(name="input", value="0.54", unit="per_1m_tokens", currency="USD"),
            PricingDimension(name="cached_input", value="0.054", unit="per_1m_tokens", currency="USD"),
            PricingDimension(name="output", value="2.16", unit="per_1m_tokens", currency="USD"),
        ),
        valid_from=collected.generated_at,
        provenance=prov,
    )
    bundle = bundle.model_copy(
        update={
            "routes": bundle.routes + (route,),
            "models": bundle.models + (model,),
            "pricing": bundle.pricing + (pricing,),
        }
    )
    report, _ = _validate(bundle, baseline)
    assert report.state == "BLOCKED", sorted(_codes(report))
    assert "wildcard_route_authority_bypassed" in _codes(report)


# --- 181-b (B3): models-index inventory ----------------------------------------


def test_index_only_model_explicit_selection_blocks() -> None:
    world = World()
    bundle = _collect(world, providers=("openai",), model_include=("gpt-syn-special",))
    assert _proposed_models(bundle) == set()
    assert _inventory(bundle)[("openai", "gpt-syn-special")] == (
        "incomplete",
        "index_only_no_standard_prices",
    )
    report, _ = _validate(bundle, None)
    assert report.state == "BLOCKED", sorted(_codes(report))
    assert "missing_required_selection" in _codes(report)


def test_legacy_models_docs_format_still_parses() -> None:
    parsed = se.parse_snapshot(
        "openai",
        "openai_models_docs",
        (
            b"# Models\n\n## gpt-legacy\nContext length: 128000\n"
            b"Max output tokens: 8192\nEndpoints: /v1/chat/completions\n"
        ),
    )
    assert parsed.ok, parsed.error
    (model,) = parsed.models
    assert model.model == "gpt-legacy"
    assert model.context_length == 128000
    assert model.max_output_tokens == 8192
    assert model.parser == "openai_models_docs/v1"
    assert model.identity_only is False
    # a non-index document keeps legacy behavior end to end: no
    # index-only inventory entry, counts reflect pricing rows only
    world = World()
    world.models_md = b"# Models index\n"
    bundle = _collect(world, providers=("openai",))
    assert ("openai", "gpt-syn-special") not in _inventory(bundle)
    assert bundle.collection.source_model_counts == {"openai": 3}

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

# --- 181-b (AP-B2/AP-B4): CLI exit status and stage pinning --------------------


def _cli_collect(monkeypatch, world: World, *args: str):
    """Invoke the real collect command against a fully mocked world.

    The CLI's real ``collect_bundle`` defaults to ``socket.getaddrinfo`` for
    its destination check; a fully mocked public resolver is injected so no
    unit test performs a live DNS lookup (AP-B4). The JSON summary lands on
    stdout; httpx logging lands on stderr.
    """
    from typer.testing import CliRunner

    from slaif_gateway.cli.main import app

    real_collect = coll.collect_bundle

    def collect_with_resolver(**kw):
        kw["resolve"] = _resolve_public
        return real_collect(**kw)

    monkeypatch.setattr(src, "new_client", lambda: world.client())
    monkeypatch.setattr(coll, "collect_bundle", collect_with_resolver)
    return CliRunner().invoke(app, list(args))


def _cli_json(result) -> dict:
    return json.loads(result.stdout)


def test_cli_collect_bootstrap_ready_exit_0(tmp_path, monkeypatch) -> None:
    world = World()
    run_root = tmp_path / "runs"
    key = tmp_path / "seal.key"
    result = _cli_collect(
        monkeypatch,
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
    assert result.exit_code == 0, result.output
    summary = _cli_json(result)
    assert summary["state"] == "READY"
    assert summary["stage"].startswith("live collection")
    from typer.testing import CliRunner

    from slaif_gateway.cli.main import app

    run_dirs = sorted(p for p in run_root.iterdir() if p.is_dir())
    assert len(run_dirs) == 1
    verify = CliRunner().invoke(
        app,
        [
            "catalog-refresh",
            "verify",
            "--run-dir",
            str(run_dirs[0]),
            "--seal-key",
            str(key),
        ],
    )
    assert verify.exit_code == 0, verify.output


def test_cli_collect_refresh_baseline_file_ready_exit_0(tmp_path, monkeypatch) -> None:
    """181-b (B2) strategic reproducer: a real collect --refresh
    --baseline-file against a valid canonical-digest baseline now succeeds
    (it returned 20/baseline_target_mismatch before the target
    representation fix)."""
    world = World()
    baseline = _baseline_doc(
        routes={"synth/alpha": {}},
        pricing={"synth/alpha": {"input": "0.54", "output": "2.16", "cached": "0.054"}},
    )
    baseline = baseline.model_copy(
        update={
            "content_sha256": sha256(canonical_baseline_content(baseline)).hexdigest()
        }
    )
    baseline_path = tmp_path / "baseline.json"
    baseline_path.write_text(baseline.model_dump_json(), encoding="utf-8")
    run_root = tmp_path / "runs"
    key = tmp_path / "seal.key"
    result = _cli_collect(
        monkeypatch,
        world,
        "catalog-refresh",
        "collect",
        "--refresh",
        "--providers",
        "openrouter",
        "--baseline-file",
        str(baseline_path),
        "--run-root",
        str(run_root),
        "--seal-key",
        str(key),
        "--json",
    )
    assert result.exit_code == 0, result.output
    summary = _cli_json(result)
    assert summary["state"] == "READY"
    assert summary["stage"].startswith("live collection")


def test_cli_review_substituted_baseline_digest_rejected(tmp_path, monkeypatch) -> None:
    world = World()
    baseline_a = _baseline_doc(routes={"synth/alpha": {}})
    collected = _collect(
        world,
        providers=("openrouter",),
        baseline=baseline_a,
        baseline_mode="exported_file",
    )
    bundle_path = tmp_path / "bundle.json"
    bundle_path.write_bytes(canonical_bundle_bytes(collected))
    # a different document (same row counts, different content): the
    # declared digest can no longer bind it
    baseline_b = baseline_a.model_copy(
        update={
            "routes": tuple(
                r.model_copy(update={"priority": r.priority + 1})
                for r in baseline_a.routes
            )
        }
    )
    baseline_b = baseline_b.model_copy(
        update={
            "content_sha256": sha256(canonical_baseline_content(baseline_b)).hexdigest()
        }
    )
    baseline_path = tmp_path / "baseline.json"
    baseline_path.write_text(baseline_b.model_dump_json(), encoding="utf-8")
    run_root = tmp_path / "runs"
    key = tmp_path / "seal.key"
    from typer.testing import CliRunner

    from slaif_gateway.cli.main import app

    result = CliRunner().invoke(
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
            str(key),
            "--json",
        ],
    )
    assert result.exit_code == 20, result.output
    summary = _cli_json(result)
    assert summary["state"] == "BLOCKED"
    assert "baseline_identity_mismatch" in summary["reason"]


def test_cli_review_target_mismatch_rejected(tmp_path, monkeypatch) -> None:
    world = World()
    baseline = _baseline_doc(routes={"synth/alpha": {}})
    baseline = baseline.model_copy(
        update={
            "content_sha256": sha256(canonical_baseline_content(baseline)).hexdigest()
        }
    )
    collected = _collect(
        world,
        providers=("openrouter",),
        baseline=baseline,
        baseline_mode="exported_file",
    )
    bundle_path = tmp_path / "bundle.json"
    baseline_path = tmp_path / "baseline.json"
    baseline_path.write_text(baseline.model_dump_json(), encoding="utf-8")
    run_root = tmp_path / "runs"
    key = tmp_path / "seal.key"
    from typer.testing import CliRunner

    from slaif_gateway.cli.main import app

    for tamper in (
        {"target_database": "other-db"},
        {"target_host": "10.0.0.9"},
    ):
        tampered = collected.model_copy(
            update={"baseline": collected.baseline.model_copy(update=tamper)}
        )
        bundle_path.write_bytes(canonical_bundle_bytes(tampered))
        result = CliRunner().invoke(
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
                str(key),
                "--json",
            ],
        )
        assert result.exit_code == 20, (tamper, result.output)
        summary = _cli_json(result)
        assert summary["state"] == "BLOCKED"
        assert "baseline_target_mismatch" in summary["reason"]


def test_cli_collect_stale_fx_review_exit_10(tmp_path, monkeypatch) -> None:
    world = World()
    world.ecb = _ecb_xml(
        date_s=(datetime.now(UTC).date() - timedelta(days=4)).isoformat()
    )
    run_root = tmp_path / "runs"
    key = tmp_path / "seal.key"
    result = _cli_collect(
        monkeypatch,
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
    assert result.exit_code == 10, result.output
    summary = _cli_json(result)
    assert summary["state"] == "READY_WITH_WARNINGS"
    run_dirs = sorted(p for p in run_root.iterdir() if p.is_dir())
    validation = json.loads((run_dirs[0] / "validation.json").read_text())
    assert any(
        w["code"] == "fx_stale_review" for w in validation["warnings"]
    )


def test_cli_collect_fx_fresh_boundary_exit_0(tmp_path, monkeypatch) -> None:
    # calendar age exactly at the fresh boundary (3 days) stays READY
    world = World()
    world.ecb = _ecb_xml(
        date_s=(datetime.now(UTC).date() - timedelta(days=3)).isoformat()
    )
    run_root = tmp_path / "runs"
    key = tmp_path / "seal.key"
    result = _cli_collect(
        monkeypatch,
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
    assert result.exit_code == 0, result.output
    assert _cli_json(result)["state"] == "READY"


def test_cli_collect_blocked_exit_20_collect_stage(tmp_path, monkeypatch) -> None:
    """A semantically blocked collect publishes a BLOCKED run and exits 20
    with the live-collection stage wording (65 is reserved for unpublished
    data errors)."""
    world = World()
    world.statuses[OR_URL] = 503
    run_root = tmp_path / "runs"
    key = tmp_path / "seal.key"
    result = _cli_collect(
        monkeypatch,
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
    assert result.exit_code == 20, result.output
    summary = _cli_json(result)
    assert summary["state"] == "BLOCKED"
    assert summary["stage"].startswith("live collection")
    run_dirs = sorted(p for p in run_root.iterdir() if p.is_dir())
    validation = json.loads((run_dirs[0] / "validation.json").read_text())
    assert validation["state"] == "BLOCKED"
    assert "collection_retrieval_failed" in validation["state_reason"]
