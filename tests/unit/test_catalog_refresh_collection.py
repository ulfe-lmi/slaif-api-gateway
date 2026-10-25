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
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from hashlib import sha256

import httpx
import pytest

import catalog_report_script_audit as _script_audit

from slaif_gateway.cli import catalog_refresh as cli_catalog_refresh
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
from slaif_gateway.services.catalog_refresh.validation import (
    ACQUISITION_LIVE,
    ACQUISITION_OFFLINE,
    validate_bundle,
)

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


def _validate(bundle, baseline, *, acquisition=None):
    """Validate a bundle with the RUNNER-SELECTED execution context (181-i).

    ``acquisition`` names the execution path of the simulated invocation.
    When omitted it simulates the PRODUCING runner: the collect path
    selected the live context (the bundle carries this invocation's own
    collection identity); every other path is offline. The I1 scope
    regressions below pass it explicitly, because the context is a
    runner decision, never a property of the bundle bytes.
    """
    if acquisition is None:
        acquisition = (
            ACQUISITION_LIVE if bundle.collection is not None else ACQUISITION_OFFLINE
        )
    report, artifacts = validate_bundle(
        bundle,
        baseline,
        policy_from_document(bundle.policy),
        sql_capture="first_install" if bundle.baseline.mode == "first_install" else "document",
        acquisition=acquisition,
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


# --- 181-d (T1/D3): live-I/O guard, coherent clocks, injection helper --------


def _refuse_live_dns(*args, **kwargs):
    raise AssertionError("focused test reached a default DNS resolver (live network escape)")


def _refuse_live_connect(*args, **kwargs):
    raise AssertionError("focused test attempted a real socket connection (live network escape)")


@pytest.fixture(autouse=True)
def _no_live_io_guard(monkeypatch):
    """181-d (T1/D3): fail-on-live-I/O guard over the WHOLE focused
    collection/CLI surface in this module.

    The only permitted I/O seams are the ``httpx.MockTransport`` client and
    the explicitly injected resolver (``resolve=_resolve_public`` directly,
    or through the ``_cli_collect`` seam). This guard is the negative half
    of the isolation proof: it refuses any dynamic default-DNS lookup and
    any real socket connection, AND re-points the import-time DEFAULT
    resolver bindings (Python binds function defaults at ``def`` time, so
    patching ``socket.getaddrinfo`` alone would not cover them) to a
    refusing tripwire. An un-injected call therefore fails loudly instead
    of performing a public DNS lookup. The guard itself installs no
    synthetic resolver: the explicit ``resolve`` injection is the isolation
    fix, and this fixture only proves nothing leaks past it.
    """
    monkeypatch.setattr(socket, "getaddrinfo", _refuse_live_dns)
    monkeypatch.setattr(socket.socket, "connect", _refuse_live_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", _refuse_live_connect)
    for fn in (
        src.fetch_source,
        src.fetch_sources,
        src.guard_public_destination,
        coll.collect_bundle,
        src.new_client,
    ):
        kwdefaults = dict(getattr(fn, "__kwdefaults__", None) or {})
        if "resolve" in kwdefaults:
            kwdefaults["resolve"] = _refuse_live_dns
            monkeypatch.setattr(fn, "__kwdefaults__", kwdefaults)
    yield


# 181-d (T2/D3): one coherent frozen pipeline clock. The FX freshness
# boundary is a CALENDAR-DAY property (UTC publication date vs UTC review
# date), so the fixture date and the pipeline clock must come from the SAME
# instant. Pre-fix, the fixture was created at one real date and the
# pipeline ran at a later real time: a real UTC midnight crossing between
# the two aged the quote by a day with no code change (the flake). Freezing
# every pipeline wall-clock read to one shared instant proves the boundary
# is midnight-independent.
FROZEN_MIDNIGHT_EDGE = datetime(2026, 10, 11, 23, 59, 59, tzinfo=UTC)
FROZEN_POST_MIDNIGHT_EDGE = datetime(2026, 10, 12, 0, 0, 1, tzinfo=UTC)


def _freeze_pipeline_clock(monkeypatch, frozen: datetime) -> None:
    """Freeze fixture, collection, retrieval and CLI clocks to ONE instant.

    Validation derives its clock from ``bundle.generated_at`` (the frozen
    collection finish), so it stays coherent automatically.
    """

    class _FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return frozen

    monkeypatch.setattr(sys.modules[__name__], "datetime", _FrozenDatetime)
    monkeypatch.setattr(src, "datetime", _FrozenDatetime)
    monkeypatch.setattr(coll, "datetime", _FrozenDatetime)
    monkeypatch.setattr(cli_catalog_refresh, "datetime", _FrozenDatetime)


def _inject_proposal_facts(bundle, model: str, valid_from: datetime):
    """Build fully grounded proposal facts (route + model + pricing) for a
    model ID, mirroring the collected provenance: valid source references,
    normal TSV dimensions, and the exact published default-row prices
    (0.54 / 0.054 / 2.16 USD per 1M). The strongest supplied-bundle
    injection shape - only the policy itself may refuse it."""
    from slaif_gateway.schemas.catalog_refresh import (
        FieldProvenance,
        ModelFacts,
        ModelPricingFacts,
        PricingDimension,
        RouteFacts,
    )

    prov = FieldProvenance(
        sources=("openrouter|catalog|openrouter_models_api",),
        extractor=coll.EXTRACTOR_ID,
        extraction="deterministic",
    )
    route = RouteFacts(
        provider="openrouter",
        requested_model=model,
        upstream_model=model,
        match_type="exact",
        endpoint="/v1/chat/completions",
        priority=100,
        enabled=True,
        visible_in_models=True,
        supports_streaming=True,
        capabilities={"text": True, "streaming": True},
        provenance=prov,
    )
    model_facts = ModelFacts(
        provider="openrouter",
        model=model,
        display_name=model,
        context_length=128000,
        max_output_tokens=8192,
        supports_streaming=True,
        capabilities={"text": True, "streaming": True},
        deprecated=False,
        provenance=prov,
    )
    pricing = ModelPricingFacts(
        provider="openrouter",
        model=model,
        endpoint="/v1/chat/completions",
        currency="USD",
        dimensions=(
            PricingDimension(name="input", value="0.54", unit="per_1m_tokens", currency="USD"),
            PricingDimension(name="cached_input", value="0.054", unit="per_1m_tokens", currency="USD"),
            PricingDimension(name="output", value="2.16", unit="per_1m_tokens", currency="USD"),
        ),
        valid_from=valid_from,
        provenance=prov,
    )
    return route, model_facts, pricing


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
    # 182: the created model's public exposure warning is the only finding
    assert report.state == "READY_WITH_WARNINGS"
    assert sorted(_codes(report)) == ["new_model_exposure"]
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
    # 182: the created model's public exposure warning is the only finding
    assert report.state == "READY_WITH_WARNINGS"
    assert sorted(_codes(report)) == ["new_model_exposure"]


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
    # 182: the created model's public exposure warning is the only finding
    assert report.state == "READY_WITH_WARNINGS"
    assert sorted(_codes(report)) == ["new_model_exposure"]


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
    # 182: the created model's public exposure warning is the only finding
    assert report.state == "READY_WITH_WARNINGS"
    assert sorted(_codes(report)) == ["new_model_exposure"]


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
    # 182: the created model's public exposure warning is the only finding
    assert report.state == "READY_WITH_WARNINGS"
    assert sorted(_codes(report)) == ["new_model_exposure"]


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
    # 182: the created model's public exposure warning is the only finding
    assert report.state == "READY_WITH_WARNINGS"
    assert sorted(_codes(report)) == ["new_model_exposure"]


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
    # 182: the created model's public exposure warning is the only finding
    assert report.state == "READY_WITH_WARNINGS"
    assert sorted(_codes(report)) == ["new_model_exposure"]


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


# --- 181-i (I1): runner-selected acquisition scope ----------------------------


def test_intact_collected_bundle_reviewed_offline_is_supplied_collection() -> None:
    """A supplied INTACT bundle keeps its collection identity as historical
    provenance: the reviewing invocation is offline, the scope is
    supplied_collection, and the provenance (dates/retrievals/inventory/
    digests) is preserved and labeled, never renewed or re-dated."""
    collected = _collect(World(), providers=("openrouter",))
    original_identity = collected.collection.model_dump()

    report, _ = _validate(collected, None, acquisition=ACQUISITION_OFFLINE)
    evidence = report.to_dict()["source_evidence"]
    assert evidence["scope"] == "supplied_collection"
    # this invocation performed no live retrieval
    assert "no live retrieval" in evidence["note"] or "reviewed the supplied bytes offline" in evidence["note"]
    # provenance preserved byte-for-byte
    supplied_collection = evidence["collection"]
    assert supplied_collection["tool"] == original_identity["tool"]
    assert supplied_collection["code_revision"] == original_identity["code_revision"]
    assert supplied_collection["retrievals_total"] == len(collected.collection.retrievals)
    assert supplied_collection["retrievals_ok"] == sum(
        1 for r in collected.collection.retrievals if r.outcome == "ok"
    )
    # the context records the offline mode, not a live claim
    context = report.to_dict()["execution_context"]
    assert context["acquisition"] == "offline_supplied"


def test_fabricated_collection_identity_never_promotes_offline_review() -> None:
    """A supplied bundle carrying a FABRICATED collection identity (even an
    intact-shaped one) must not be promoted to live and must not lend its
    untrusted tool/code_revision to the current generator identity: the
    generator of the offline review is measured from the running code."""
    collected = _collect(World(), providers=("openrouter",))
    forged = collected.collection.model_copy(
        update={
            "tool": "attacker-tool/9.9.9",
            "code_revision": "forged-revision-000",
        }
    )
    forged_bundle = collected.model_copy(update={"collection": forged})

    # offline review (the default for any non-collect invocation)
    report, _ = _validate(forged_bundle, None, acquisition=ACQUISITION_OFFLINE)
    assert report.to_dict()["source_evidence"]["scope"] == "supplied_collection"
    generator = report.to_dict()["execution_context"]["generator"]
    assert generator["tool"] != "attacker-tool/9.9.9"
    assert generator["code_revision"] != "forged-revision-000"
    from slaif_gateway.services.catalog_refresh import execution_identity

    expected_tool, expected_revision = execution_identity.tool_identity()
    assert generator["tool"] == expected_tool
    assert generator["code_revision"] == expected_revision

    # the explicit live context also cannot be claimed by label alone: the
    # generator is still the runner's own measurement (the collect path's),
    # and a live context without ANY collection identity blocks the run
    live_report, _ = _validate(forged_bundle, None, acquisition=ACQUISITION_LIVE)
    live_generator = live_report.to_dict()["execution_context"]["generator"]
    assert live_generator["tool"] == "attacker-tool/9.9.9"
    assert live_generator["code_revision"] == "forged-revision-000"
    assert live_report.to_dict()["source_evidence"]["scope"] == "live_collection"

    no_collection = forged_bundle.model_copy(update={"collection": None})
    with pytest.raises(CatalogRefreshBlockedError) as excinfo:
        _validate(no_collection, None, acquisition=ACQUISITION_LIVE)
    assert excinfo.value.code == "acquisition_context_mismatch"


def test_public_validator_default_is_offline_with_current_measured_generator() -> None:
    """181-i (I1/I2) on the PUBLIC pure-validator contract: calling
    ``validate_bundle`` directly with NO acquisition argument must treat an
    intact OR forged collection as supplied historical provenance (offline
    scope) and measure the current generator from the running code. The
    helper-based tests above simulate the producing runner, so this pins
    the library default itself."""
    from slaif_gateway.services.catalog_refresh import execution_identity

    collected = _collect(World(), providers=("openrouter",))
    policy = policy_from_document(collected.policy)

    # intact collection, no acquisition argument -> offline, measured generator
    report, _ = validate_bundle(
        collected, None, policy, sql_capture="first_install"
    )
    evidence = report.to_dict()["source_evidence"]
    assert evidence["scope"] == "supplied_collection"
    expected_tool, expected_revision = execution_identity.tool_identity()
    generator = report.to_dict()["execution_context"]["generator"]
    assert generator == {"tool": expected_tool, "code_revision": expected_revision}
    assert report.to_dict()["execution_context"]["acquisition"] == "offline_supplied"

    # forged collection, no acquisition argument -> still offline, and the
    # forged identity never becomes the current generator
    forged = collected.model_copy(
        update={
            "collection": collected.collection.model_copy(
                update={
                    "tool": "attacker-tool/9.9.9",
                    "code_revision": "forged-revision-000",
                }
            )
        }
    )
    forged_report, _ = validate_bundle(
        forged, None, policy, sql_capture="first_install"
    )
    assert forged_report.to_dict()["source_evidence"]["scope"] == "supplied_collection"
    forged_generator = forged_report.to_dict()["execution_context"]["generator"]
    assert forged_generator == {"tool": expected_tool, "code_revision": expected_revision}
    assert forged_generator["tool"] != "attacker-tool/9.9.9"
    assert forged_generator["code_revision"] != "forged-revision-000"


def test_offline_review_generator_versions_are_the_running_code() -> None:
    """The execution context's generator_versions are the ACTUAL versions
    of the generating code (runner-owned constants), never the supplied
    bundle revision/research declarations."""
    collected = _collect(World(), providers=("openrouter",))
    report, _ = _validate(collected, None, acquisition=ACQUISITION_OFFLINE)
    versions = report.to_dict()["execution_context"]["generator_versions"]
    from slaif_gateway.schemas.catalog_refresh import (
        EXTRACTOR_ID,
        POLICY_VERSION,
        RENDERER_VERSION,
        SCHEMA_VERSION,
    )

    assert versions == {
        "schema_version": SCHEMA_VERSION,
        "renderer_version": RENDERER_VERSION,
        "policy_version": POLICY_VERSION,
        "extractor_version": EXTRACTOR_ID,
    }


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
    # 182: the created model's public exposure warning is the only finding
    assert report.state == "READY_WITH_WARNINGS"
    assert sorted(_codes(report)) == ["new_model_exposure"]


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
    # 182: the created model's public exposure warning is the only finding
    assert report.state == "READY_WITH_WARNINGS"
    assert sorted(_codes(report)) == ["new_model_exposure"]


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
    # 182: the created model's public exposure warning is the only finding
    assert report.state == "READY_WITH_WARNINGS"
    assert sorted(_codes(report)) == ["new_model_exposure"]


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
    """181-c (C2) / 181-d (D1): a :online-style ID with a positive hosted
    charge is excluded identically to an ordinary flat ID with the same
    charge; 181-d tightens the variant case to the INTRINSIC IDENTITY
    reason (the documented :online contract enables hosted web search
    regardless of the fee); the flat sibling stays proposed."""
    online = _or_row("synth/alpha:online")
    online["pricing"]["web_search"] = "0.01"
    world = World()
    world.or_rows = [online, _or_row("synth/beta", inp="0.1", out="0.4")]
    bundle = _collect(world, providers=("openrouter",))
    assert _proposed_models(bundle) == {"openrouter/synth/beta"}
    assert _inventory(bundle)[("openrouter", "synth/alpha:online")] == (
        "excluded_subset",
        "intrinsic_hosted_variant_unrepresentable",
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


def test_router_online_variant_excluded_by_intrinsic_identity_not_fee() -> None:
    """181-d (D1): the documented OpenRouter ':online' variant is a known
    intrinsic hosted identity (official model-variants contract: the suffix
    enables real-time web search for any model, exactly equivalent to the
    web plugin, and is deprecated in favor of the openrouter:web_search
    server tool). It is excluded by IDENTITY - positive, zero, and missing
    web_search fees all yield the exact intrinsic reason (zero cost cannot
    qualify tool authority; absent fees cannot establish absence of
    search) - while the flat sibling stays proposed."""
    for fee in ("0.01", "0", None):
        online = _or_row("synth/alpha:online")
        if fee is not None:
            online["pricing"]["web_search"] = fee
        world = World()
        world.or_rows = [online, _or_row("synth/beta", inp="0.1", out="0.4")]
        bundle = _collect(world, providers=("openrouter",))
        assert _proposed_models(bundle) == {"openrouter/synth/beta"}, fee
        assert _inventory(bundle)[("openrouter", "synth/alpha:online")] == (
            "excluded_subset",
            "intrinsic_hosted_variant_unrepresentable",
        ), fee


def test_router_online_variant_explicit_selection_blocks() -> None:
    """181-d (D1): explicitly selecting the intrinsic hosted identity does
    not launder it: with a published ZERO fee and complete flat facts the
    selection still BLOCKs exactly like any other excluded model
    (missing_required_selection), never READY."""
    online = _or_row("synth/alpha:online")
    online["pricing"]["web_search"] = "0"
    world = World()
    world.or_rows = [online, _or_row("synth/beta", inp="0.1", out="0.4")]
    bundle = _collect(
        world, providers=("openrouter",), model_include=("synth/alpha:online",)
    )
    assert _proposed_models(bundle) == set()
    assert _inventory(bundle)[("openrouter", "synth/alpha:online")] == (
        "excluded_subset",
        "intrinsic_hosted_variant_unrepresentable",
    )
    assert _inventory(bundle)[("openrouter", "synth/beta")] == (
        "excluded_subset",
        "explicit_selection_excluded",
    )
    report, _ = _validate(bundle, None)
    assert report.state == "BLOCKED", sorted(_codes(report))
    assert "missing_required_selection" in _codes(report)


def test_supplied_bundle_online_variant_proposal_blocks_regardless_of_fee() -> None:
    """181-d (D1) independent supplied-bundle negative: a ready proposal for
    the intrinsic ':online' identity with fully valid source provenance,
    normal TSV dimensions, and the exact published prices still BLOCKS -
    the shared policy is recomputed from the parsed official rows, so
    caller-supplied inventory, warnings, or labels cannot launder the
    identity. Positive, zero, and missing fee states all block."""
    for fee in ("0.01", "0", None):
        online = _or_row("synth/alpha:online")
        if fee is not None:
            online["pricing"]["web_search"] = fee
        world = World()
        world.or_rows = [online, _or_row("synth/beta", inp="0.1", out="0.4")]
        collected = _collect(world, providers=("openrouter",))
        bundle = _roundtrip_bundle(collected)
        route, model_facts, pricing = _inject_proposal_facts(
            bundle, "synth/alpha:online", collected.generated_at
        )
        bundle = bundle.model_copy(
            update={
                "routes": bundle.routes + (route,),
                "models": bundle.models + (model_facts,),
                "pricing": bundle.pricing + (pricing,),
            }
        )
        report, _ = _validate(bundle, None)
        assert report.state == "BLOCKED", (fee, sorted(_codes(report)))
        assert "proposed_row_billing_ineligible" in _codes(report), fee
        ineligible = next(
            w for w in report.warnings if w.code == "proposed_row_billing_ineligible"
        )
        assert "intrinsic_hosted_variant_unrepresentable" in ineligible.detail, fee


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
    # 182: the created model's public exposure warning is the only finding
    assert report.state == "READY_WITH_WARNINGS"
    assert sorted(_codes(report)) == ["new_model_exposure"]


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
    # 182: the created model's public exposure warning is the only finding
    assert report.state == "READY_WITH_WARNINGS"
    assert sorted(_codes(report)) == ["new_model_exposure"]


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
    # 182: the created model's public exposure warning is the only finding
    assert report.state == "READY_WITH_WARNINGS"
    assert sorted(_codes(report)) == ["new_model_exposure"]


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
    # 182: the created model's public exposure warning is the only finding
    assert report.state == "READY_WITH_WARNINGS"
    assert sorted(_codes(report)) == ["new_model_exposure"]
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


def _mixed_baseline(match_type: str, pattern: str) -> BaselineDocument:
    """181-d (D2): one flat exact public alias plus one GOVERNING fixed
    upstream prefix/glob for the same provider/upstream - the MIXED local
    authority set, with the denied wildcard alternative preserved
    (disabled/hidden/non-streaming row kept, priorities and destinations
    intact)."""
    baseline = _baseline_doc(
        routes={
            "public-alias": {},
            pattern: {
                "enabled": False,
                "visible": False,
                "streaming": False,
            },
        },
        pricing={
            "synth/alpha": {"input": "0.54", "output": "2.16", "cached": "0.054"}
        },
    )
    return baseline.model_copy(
        update={
            "routes": tuple(
                r.model_copy(
                    update={
                        "upstream_model": "synth/alpha",
                        "match_type": (
                            match_type if r.requested_model == pattern else "exact"
                        ),
                    }
                )
                for r in baseline.routes
            )
        }
    )


@pytest.mark.parametrize(
    "match_type,pattern",
    [("prefix", "public/"), ("glob", "public/*")],
)
def test_refresh_mixed_exact_and_wildcard_baseline_retained_coherent(
    match_type: str, pattern: str
) -> None:
    """181-d (D2) strategic reproducer: a flat exact public alias AND a
    governing fixed-upstream prefix/glob for the same provider/upstream
    form a MIXED authority set. The collector evaluates the WHOLE set
    before choosing any flat row and retains every alternative locally
    with an explained disposition - no exact route/pricing candidate is
    invented - and the validator confirms the claim: a coherent
    non-blocked plan, denied alternative preserved, nothing
    disappeared."""
    world = World()
    world.or_rows = [_or_row("synth/alpha")]
    baseline = _mixed_baseline(match_type, pattern)
    bundle = _collect(
        world,
        providers=("openrouter",),
        baseline=baseline,
        baseline_mode="exported_file",
    )
    assert bundle.routes == ()
    assert bundle.pricing == ()
    assert bundle.models == ()
    assert _inventory(bundle)[("openrouter", "synth/alpha")] == (
        "excluded_subset",
        "baseline_contract_not_flat",
    )
    detail = next(
        e.detail for e in bundle.collection.inventory if e.model == "synth/alpha"
    )
    assert "public-alias" in detail and pattern in detail
    report, artifacts = _validate(bundle, baseline)
    assert report.state == "READY", (report.state, sorted(_codes(report)))
    assert "wildcard_route_authority_bypassed" not in _codes(report)
    assert "model_disappeared" not in _codes(report)
    # artifact plan: no parallel exact route or pricing row invented
    assert "synth/alpha" not in artifacts["routes-proposal.tsv"].decode()
    assert "synth/alpha" not in artifacts["pricing-proposal.tsv"].decode()
    # both retained alternatives and the governed upstream keep explicit
    # deterministic NOT_FETCHED dispositions
    dispositions = {
        d.model: d.disposition
        for d in report.dispositions
        if d.model in ("public-alias", pattern, "synth/alpha")
    }
    assert dispositions == {
        "public-alias": "NOT_FETCHED",
        pattern: "NOT_FETCHED",
        "synth/alpha": "NOT_FETCHED",
    }


def test_supplied_bundle_parallel_route_on_mixed_baseline_blocks() -> None:
    """181-d (D2) independent supplied-bundle negative: even on a MIXED
    exact + governing-wildcard baseline, a supplied bundle that re-inserts
    the parallel exact route for the governed upstream (fully grounded,
    valid provenance, normal TSV dimensions, exact published prices)
    BLOCKS - the wildcard retains local authority and no parallel route
    bypasses it."""
    world = World()
    world.or_rows = [_or_row("synth/alpha")]
    baseline = _mixed_baseline("prefix", "public/")
    collected = _collect(
        world,
        providers=("openrouter",),
        baseline=baseline,
        baseline_mode="exported_file",
    )
    assert collected.routes == ()  # the collector retains, never invents
    bundle = _roundtrip_bundle(collected)
    route, model_facts, pricing = _inject_proposal_facts(
        bundle, "synth/alpha", collected.generated_at
    )
    bundle = bundle.model_copy(
        update={
            "routes": bundle.routes + (route,),
            "models": bundle.models + (model_facts,),
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

    # 181-d (D3): the collect stage runs through the ``_cli_collect`` seam,
    # which injects the explicit public-DNS resolver (``resolve=``); the
    # module-wide live-I/O guard proves no default resolver call and no
    # real socket connection can escape this CLI test (the pre-fix version
    # performed public DNS lookups for openrouter.ai and www.ecb.europa.eu
    # through the production default resolver).
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

    # ``verify`` re-reads the published run directory only (no retrieval);
    # the module-wide guard covers this direct invocation as well.
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
    # 181-d (D3): resolver-injected through the ``_cli_collect`` seam: the
    # 503 retry loop (three attempts) performs zero default resolver calls
    # and zero real connections; the guard makes any escape fail loudly.
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


def test_cli_collect_bootstrap_exposure_warning_exit_10(tmp_path, monkeypatch) -> None:
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
    # 182: the created models' exposure warnings make this run exit 10
    assert result.exit_code == 10, result.output
    summary = _cli_json(result)
    assert summary["state"] == "READY_WITH_WARNINGS"
    assert summary["warnings"] == 2
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


def test_cli_collect_refresh_baseline_file_exposure_warning_exit_10(tmp_path, monkeypatch) -> None:
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
    # 182: the created model's exposure warning makes this run exit 10
    assert result.exit_code == 10, result.output
    summary = _cli_json(result)
    assert summary["state"] == "READY_WITH_WARNINGS"
    assert summary["warnings"] == 1
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
    # 181-d (D3): one coherent frozen clock at the PRE-midnight edge
    # (2026-10-11T23:59:59Z). The fixture quote date and every pipeline
    # wall-clock read (fixture, collection, retrieval, CLI, validation)
    # share that one instant, so the calendar age is exactly four days by
    # construction: the four-calendar-day review boundary is proven
    # independent of the real UTC date the test happens to run on.
    _freeze_pipeline_clock(monkeypatch, FROZEN_MIDNIGHT_EDGE)
    world = World()
    world.ecb = _ecb_xml(
        date_s=(FROZEN_MIDNIGHT_EDGE.date() - timedelta(days=4)).isoformat()
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


@pytest.mark.parametrize(
    "frozen",
    [FROZEN_MIDNIGHT_EDGE, FROZEN_POST_MIDNIGHT_EDGE],
    ids=["pre-midnight-23-59-59", "post-midnight-00-00-01"],
)
def test_cli_collect_fx_fresh_boundary_exposure_warning_exit_10(tmp_path, monkeypatch, frozen) -> None:
    # 181-d (D3): calendar age exactly at the fresh boundary (3 days)
    # stays ready (the created model's exposure warning is the only
    # finding) - proven at BOTH the pre-midnight edge (23:59:59Z) and
    # the post-midnight edge (00:00:01Z) with one coherent frozen clock:
    # the fixture quote date is derived from the SAME instant the pipeline
    # uses, so a real UTC midnight crossing between fixture creation and
    # collection can no longer age the quote (midnight independence; the
    # real three-calendar-day fresh rule is unchanged).
    _freeze_pipeline_clock(monkeypatch, frozen)
    world = World()
    world.ecb = _ecb_xml(
        date_s=(frozen.date() - timedelta(days=3)).isoformat()
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
    # 182: the created model's exposure warning makes this run exit 10
    assert result.exit_code == 10, result.output
    summary = _cli_json(result)
    assert summary["state"] == "READY_WITH_WARNINGS"
    assert summary["warnings"] == 2


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


# --- 181-f (F1): one whole-invocation context across the real collector -----


def test_second_fetch_phase_cannot_reset_context_budgets() -> None:
    # Phase 1 (openai + openrouter = 3 specs) consumes all 3 attempts of
    # the shared context; the model-page phase must NOT reset the budget:
    # it fails closed before any later HTTP activity.
    world = World()
    context = src.new_acquisition_context(
        deadline_seconds=120,
        max_attempts=3,
        max_bytes=src.MAX_COLLECTION_BYTES,
    )
    with pytest.raises(src.SourceFetchError) as exc:
        _collect(world, providers=("openai", "openrouter"), acquisition=context)
    assert exc.value.code == "collection_budget_exhausted"


def test_byte_budget_exhaustion_across_phases_blocks_run() -> None:
    world = World()
    # 4 KiB covers the two small phase-1 docs but not the page cap.
    context = src.new_acquisition_context(
        deadline_seconds=120,
        max_attempts=src.MAX_COLLECTION_REQUESTS,
        max_bytes=4 * 1024,
    )
    with pytest.raises(src.SourceFetchError) as exc:
        _collect(world, providers=("openai", "openrouter"), acquisition=context)
    assert exc.value.code == "collection_budget_exhausted"


def test_expired_context_blocks_before_any_fetch() -> None:
    world = World()
    context = src.new_acquisition_context(deadline_seconds=0)
    with pytest.raises(src.SourceFetchError) as exc:
        _collect(world, providers=("openrouter",), acquisition=context)
    assert exc.value.code == "acquisition_deadline_exceeded"
    # the collection-level failure aborts the run: no bundle is produced


def test_cli_collect_deadline_exhaustion_publishes_blocked_run(tmp_path, monkeypatch) -> None:
    # The CLI's default context path: an exhausted deadline surfaces as a
    # BLOCKED run (safe code + detail), exit 20, at the collect stage.
    real_new_context = coll.new_acquisition_context

    def exhausted(**kw):
        return real_new_context(deadline_seconds=0)

    monkeypatch.setattr(coll, "new_acquisition_context", exhausted)
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
    assert result.exit_code == 20, result.output
    summary = _cli_json(result)
    assert summary["state"] == "BLOCKED"
    assert "acquisition_deadline_exceeded" in summary["reason"]
    run_dirs = sorted(p for p in run_root.iterdir() if p.is_dir())
    assert len(run_dirs) == 1
    validation = json.loads((run_dirs[0] / "validation.json").read_text())
    assert validation["state"] == "BLOCKED"
    assert "acquisition_deadline_exceeded" in validation["state_reason"]


# --- 181-g: G1-G6 regressions (strategic negative probes) -------------------


def test_cli_collect_rejected_redirect_secrets_absent_from_sealed_output(
    tmp_path, monkeypatch
) -> None:
    # G4 (sealed level, exact probe case): a 302 to the approved host
    # carrying credentials AND a query is refused safely, and the
    # synthetic markers must be ABSENT from EVERY file of the sealed run
    # directory (collector JSON, rendered review, validation, receipt,
    # manifest) - not just the exception type.
    world = World()
    unsafe = (
        "https://synthetic-user:synthetic-password@openrouter.ai"
        "/api/v1/models?token=synthetic-token"
    )
    original_handler = world.handler

    def redirecting(request: httpx.Request) -> httpx.Response:
        if str(request.url) == OR_URL:
            return httpx.Response(302, headers={"location": unsafe})
        return original_handler(request)

    world.handler = redirecting  # instance attribute shadows the method
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
    run_dirs = sorted(p for p in run_root.iterdir() if p.is_dir())
    assert len(run_dirs) == 1
    bundle = json.loads((run_dirs[0] / "catalog-refresh.json").read_text())
    failures = [
        r.get("failure_code") for r in bundle["collection"]["retrievals"]
    ]
    assert "url_credentials" in failures, (
        "the safe code is recorded in the retrieval record"
    )
    # The rendered review carries the safe code too - and NOTHING else
    # from the rejected target.
    html = (run_dirs[0] / "REVIEW.html").read_text()
    assert "url_credentials" in html
    markers = (
        b"synthetic-user",
        b"synthetic-password",
        b"synthetic-token",
        unsafe.encode("utf-8"),
    )
    scanned: list[str] = []
    for path in sorted(run_dirs[0].rglob("*")):
        if path.is_file():
            data = path.read_bytes()
            scanned.append(path.name)
            for marker in markers:
                assert marker not in data, f"rejected target leaked into {path.name}"
    for expected in ("catalog-refresh.json", "REVIEW.html", "validation.json", "receipt.json"):
        assert expected in scanned, f"expected sealed artifact {expected}"


def test_cli_collect_malformed_port_redirect_blocks_safely(tmp_path, monkeypatch) -> None:
    # G6 (CLI level, exact probe case): a 302 to a malformed-port target
    # fails deterministically with the safe code url_nondefault_port -
    # no ValueError escape, no traceback, a proper BLOCKED run. (The
    # out-of-range NUMERIC port is the variant httpx itself can parse in
    # its redirect bookkeeping, so our re-validation is the decision
    # point; the non-numeric variant is refused even earlier by httpx
    # and still surfaces as the safe transport_error - see the sources
    # tests.)
    world = World()
    unsafe = "https://developers.openai.com:99999/api/docs/pricing.md"
    original_handler = world.handler

    def redirecting(request: httpx.Request) -> httpx.Response:
        if str(request.url) == PRICING_URL:
            return httpx.Response(302, headers={"location": unsafe})
        return original_handler(request)

    world.handler = redirecting
    run_root = tmp_path / "runs"
    key = tmp_path / "seal.key"
    result = _cli_collect(
        monkeypatch,
        world,
        "catalog-refresh",
        "collect",
        "--bootstrap",
        "--providers",
        "openai",
        "--run-root",
        str(run_root),
        "--seal-key",
        str(key),
        "--json",
    )
    assert result.exit_code == 20, result.output
    assert "Traceback" not in result.output
    assert "ValueError" not in result.output
    assert "not-a-port" not in result.output
    assert "99999" not in result.output
    summary = _cli_json(result)
    assert summary["state"] == "BLOCKED"
    run_dirs = sorted(p for p in run_root.iterdir() if p.is_dir())
    assert len(run_dirs) == 1
    validation = json.loads((run_dirs[0] / "validation.json").read_text())
    assert validation["state"] == "BLOCKED"
    bundle = json.loads((run_dirs[0] / "catalog-refresh.json").read_text())
    failures = [
        r.get("failure_code") for r in bundle["collection"]["retrievals"]
    ]
    assert "url_nondefault_port" in failures, (
        "the exact safe code is recorded in the retrieval record"
    )
    html = (run_dirs[0] / "REVIEW.html").read_text()
    assert "url_nondefault_port" in html
    # The unsafe port must not leak into the report's VISIBLE data. The
    # one verified fixed sorting script is excluded from this data-level
    # check (its precision comments contain 99999-digit literals).
    auditor = _script_audit.audit_fixed_report_script(html)
    assert "99999" not in auditor.visible_text


# --- 184: observed-model truthful refusal (selected BLOCK, retention) ------
#
# A collection inventory entry proves the ID was OBSERVED in this collection
# (excluded or incomplete). Such an ID is never "absent from complete source
# retrieval": an explicitly required selection that cannot be safely proposed
# is BLOCKED with the exact reason, and any other observed-but-unproposed ID
# is a documented retain-local. Genuine absence keeps the established
# disappearance semantics.


def test_refresh_selected_unrepresentable_billing_blocks_truthfully() -> None:
    """184: an explicitly selected in-baseline model whose observed billing
    cannot be safely proposed is BLOCKED with the exact machine reason -
    never reported as absent from the source set, never an actionable plan."""
    world = World()
    world.or_rows = [_or_row("synth/alpha"), _or_row("synth/billing")]
    world.or_rows[1]["pricing"]["request"] = "0.001"
    baseline = _baseline_doc(
        routes={"synth/billing": {}},
        pricing={"synth/billing": {"input": "0.5", "output": "2.0"}},
    )
    bundle = _collect(
        world,
        providers=("openrouter",),
        baseline=baseline,
        baseline_mode="exported_file",
        model_include=("synth/billing",),
    )
    assert _proposed_models(bundle) == set()
    assert _inventory(bundle)[("openrouter", "synth/billing")] == (
        "excluded_subset",
        "request_charges_unrepresentable",
    )
    report, _ = _validate(bundle, baseline)
    assert report.state == "BLOCKED", (report.state, sorted(_codes(report)))
    assert "explicitly_selected_not_proposable" in _codes(report)
    assert "model_disappeared" not in _codes(report)
    disp = {d.model: d for d in report.dispositions if d.provider == "openrouter"}
    assert disp["synth/billing"].disposition == "BLOCKED"
    assert "request_charges_unrepresentable" in disp["synth/billing"].detail
    assert report.apply_plan is None


def test_refresh_unselected_observed_excluded_retained_not_disappeared() -> None:
    """184: an in-baseline model observed but excluded in an all-eligible
    refresh is a documented retain-local - never disappearance, and no plan
    operation may touch it."""
    world = World()
    world.or_rows = [_or_row("synth/alpha"), _or_row("synth/billing")]
    world.or_rows[1]["pricing"]["request"] = "0.001"
    baseline = _baseline_doc(
        routes={"synth/billing": {}},
        pricing={"synth/billing": {"input": "0.5", "output": "2.0"}},
    )
    bundle = _collect(
        world,
        providers=("openrouter",),
        baseline=baseline,
        baseline_mode="exported_file",
    )
    assert _inventory(bundle)[("openrouter", "synth/billing")] == (
        "excluded_subset",
        "request_charges_unrepresentable",
    )
    report, _ = _validate(bundle, baseline)
    assert report.state in ("READY", "READY_WITH_WARNINGS"), (
        report.state,
        sorted(_codes(report)),
    )
    assert "model_disappeared" not in _codes(report)
    disp = {d.model: d for d in report.dispositions if d.provider == "openrouter"}
    assert disp["synth/billing"].disposition == "NOT_FETCHED"
    assert "request_charges_unrepresentable" in disp["synth/billing"].detail
    for op in (report.apply_plan or {}).get("operations") or ():
        assert op.get("model") != "synth/billing"
        assert op.get("requested_model") != "synth/billing"
        assert op.get("upstream_model") != "synth/billing"


def test_refresh_selected_unparseable_page_blocks_truthfully() -> None:
    """184: an explicitly selected in-baseline model whose required page is
    delivered but fails to parse is BLOCKED with the exact parser reason -
    observed facts are retained, never absence."""
    world = World()
    world.or_rows = []
    world.pricing_rows = [("gpt-syn-1", "0.54", "0.054", "2.16", None, None)]
    page = _page("gpt-syn-1")
    # truncate mid-cell of the Output price row: the bytes are delivered,
    # the parser refuses them (malformed price row)
    idx = page.find(b"| Output | $2.16 |")
    world.pages = {"gpt-syn-1": page[: idx + len(b"| Output | $2.1")]}
    baseline = _baseline_doc(
        pricing={"gpt-syn-1": {"input": "0.54", "output": "2.16"}}
    )
    baseline = baseline.model_copy(
        update={
            "pricing": tuple(
                r.model_copy(update={"provider": "openai"})
                for r in baseline.pricing
            )
        }
    )
    bundle = _collect(
        world,
        providers=("openai",),
        baseline=baseline,
        baseline_mode="exported_file",
        model_include=("gpt-syn-1",),
    )
    assert _proposed_models(bundle) == set()
    assert _inventory(bundle)[("openai", "gpt-syn-1")] == (
        "incomplete",
        "page_parse_failed",
    )
    report, _ = _validate(bundle, baseline)
    assert report.state == "BLOCKED", (report.state, sorted(_codes(report)))
    assert "explicitly_selected_not_proposable" in _codes(report)
    assert "source_evidence_parse_failed" in _codes(report)
    assert "model_disappeared" not in _codes(report)
    disp = {d.model: d for d in report.dispositions if d.provider == "openai"}
    assert disp["gpt-syn-1"].disposition == "BLOCKED"
    assert "page_parse_failed" in disp["gpt-syn-1"].detail
    assert report.apply_plan is None


def test_refresh_true_absence_still_disappears() -> None:
    """184: a baseline model with NO observation recorded (genuinely absent
    from the complete sources) keeps the established disappearance and
    retain-local semantics."""
    world = World()
    world.or_rows = [_or_row("synth/alpha")]
    baseline = _baseline_doc(
        routes={"synth/gone": {}},
        pricing={"synth/gone": {"input": "0.5", "output": "2.0"}},
    )
    bundle = _collect(
        world,
        providers=("openrouter",),
        baseline=baseline,
        baseline_mode="exported_file",
    )
    assert _inventory(bundle) == {}
    report, _ = _validate(bundle, baseline)
    assert report.state == "READY_WITH_WARNINGS"
    assert "model_disappeared" in _codes(report)
    disp = {d.model: d for d in report.dispositions if d.provider == "openrouter"}
    assert disp["synth/gone"].disposition == "DISAPPEARED"


def test_refresh_alias_of_observed_excluded_upstream_retained() -> None:
    """184: a public alias whose observed upstream is excluded for an
    observed reason is retained locally through the alias identity - never
    disappearance."""
    world = World()
    world.or_rows = [_or_row("synth/alpha")]
    world.or_rows[0]["pricing"]["request"] = "0.001"
    baseline = _alias_baseline()
    bundle = _collect(
        world,
        providers=("openrouter",),
        baseline=baseline,
        baseline_mode="exported_file",
    )
    assert _inventory(bundle)[("openrouter", "synth/alpha")] == (
        "excluded_subset",
        "request_charges_unrepresentable",
    )
    report, _ = _validate(bundle, baseline)
    assert report.state == "READY", (report.state, sorted(_codes(report)))
    assert "model_disappeared" not in _codes(report)
    disp = {d.model: d for d in report.dispositions if d.provider == "openrouter"}
    assert disp["public-alias"].disposition == "NOT_FETCHED"
    assert "request_charges_unrepresentable" in disp["public-alias"].detail


def test_refresh_selected_genuinely_absent_baseline_blocks() -> None:
    """184: an explicitly selected in-baseline model that is GENUINELY
    absent from the complete sources (no observation recorded) still
    BLOCKS: the required selection carries no facts to review. The
    disposition states the truthful absence (retain-local, no delete);
    the ordinary all-eligible disappearance REVIEW stays as-is (see the
    previous test)."""
    world = World()
    world.or_rows = [_or_row("synth/alpha")]
    baseline = _baseline_doc(
        routes={"synth/gone": {}},
        pricing={"synth/gone": {"input": "0.5", "output": "2.0"}},
    )
    bundle = _collect(
        world,
        providers=("openrouter",),
        baseline=baseline,
        baseline_mode="exported_file",
        model_include=("synth/gone",),
    )
    assert _proposed_models(bundle) == set()
    # no observation of the selected model: it is genuinely absent
    assert ("openrouter", "synth/gone") not in _inventory(bundle)
    report, _ = _validate(bundle, baseline)
    assert report.state == "BLOCKED", (report.state, sorted(_codes(report)))
    assert "missing_required_selection" in _codes(report)
    assert "model_disappeared" not in _codes(report)
    disp = {d.model: d for d in report.dispositions if d.provider == "openrouter"}
    assert disp["synth/gone"].disposition == "BLOCKED"
    assert "absent from complete sources" in disp["synth/gone"].detail
    assert "no delete" in disp["synth/gone"].detail
    assert report.apply_plan is None
