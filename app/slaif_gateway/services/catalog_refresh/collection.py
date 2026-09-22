"""Objective 181 (C1-C5): authoritative collection orchestrator.

Builds ONE canonical RefreshBundle from ACTUAL bounded retrievals of the
official OpenRouter models API, the official OpenAI pricing/model
documents, and the ECB daily reference XML. The orchestrator:

- plans only registry sources (``sources.py``), fetches them with the
  enforced transport bounds, and records every retrieval outcome
  (successes and failures) in the bundle's CollectionIdentity;
- parses every fetched snapshot with the registered deterministic
  parsers (no new parser logic lives here);
- normalizes eligible models into the standard-v1 proposal facts
  (exact upstream identities, published prices in native currency,
  9-decimal import-contract values) and reconciles EVERY observed model
  exactly once (proposed, or one inventory entry with a machine reason
  backed by the parsed bytes);
- records the required FX pairs as the published ECB quotes (EUR is the
  implicit base of the reference XML; only pairs a proposed non-EUR price
  actually needs). The native -> EUR rate the runtime uses is derived by
  the tested 180 FX gate as an exact Decimal reciprocal and is marked
  derived in every comparison and artifact row;
- preserves existing local route identity/priority/visibility and
  approved capability denials on refresh.

Nothing here is an import/apply path: the output is the same canonical
bundle the 180 review pipeline validates, seals, and reports. Codex
research is NOT_RUN in this objective (182 owns that boundary).
"""

from __future__ import annotations

import base64
import hashlib
import socket
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, ROUND_HALF_UP
from importlib.metadata import version as _package_version
from typing import Callable, Mapping

import httpx

from slaif_gateway.schemas.catalog_refresh import (
    FLAT_CAPABILITY_TO_CHAT_FIELD,
    POLICY_VERSION,
    RENDERER_VERSION,
    SCHEMA_VERSION,
    BaselineDocument,
    BaselineIdentity,
    CollectionIdentity,
    CollectionInventoryEntry,
    FieldProvenance,
    FxFacts,
    ModelFacts,
    ModelPricingFacts,
    PolicyDocument,
    PricingDimension,
    ProfileContract,
    RefreshBundle,
    ResearchIdentity,
    RevisionIdentity,
    RouteFacts,
    Selection,
    SourceRecord,
    SourceRetrievalRecord,
)
from slaif_gateway.services.catalog_refresh import source_evidence as se
from slaif_gateway.services.catalog_refresh import sources
from slaif_gateway.services.catalog_refresh.errors import CatalogRefreshBlockedError
from slaif_gateway.services.catalog_refresh.sources import (
    RetrievalResult,
    fetch_sources,
)

EXTRACTOR_ID = "slaif-collector/181.1"
MONEY_QUANTUM = Decimal("0.000000001")
MAX_OPENAI_MODEL_PAGES = 64
EUR = "EUR"
CHAT_ENDPOINT = "/v1/chat/completions"
CATALOG_MODEL = "catalog"

# Inventory reason codes (compact machine codes; bounded detail text).
REASON_SERVICE_VARIANT = "service_variant"
REASON_PROVIDER_ALIAS = "provider_alias_row"
REASON_NEGATIVE_SENTINEL = "negative_router_sentinel"
REASON_MISSING_LIMITS = "missing_limits"
REASON_NON_TEXT = "non_text_modality"
REASON_DEPRECATED = "deprecated_model"
REASON_NO_STANDARD_SHORT = "no_standard_short_prices"
REASON_PAGE_UNAVAILABLE = "page_unavailable"
REASON_PAGE_PARSE_FAILED = "page_parse_failed"
REASON_PAGE_MODEL_MISMATCH = "page_model_mismatch"
REASON_PAGE_NO_CHAT = "page_no_chat"
REASON_PAGE_NO_TEXT = "page_no_text"
REASON_PAGE_PRICE_CONFLICT = "page_price_conflict"
REASON_BASELINE_CONTRACT_NOT_FLAT = "baseline_contract_not_flat"
REASON_BASELINE_CURRENCY_MISMATCH = "baseline_currency_mismatch"
REASON_EXPLICIT_SELECTION_EXCLUDED = "explicit_selection_excluded"
REASON_PRICE_BELOW_QUANTUM = "price_below_quantum"


def package_version() -> str:
    try:
        return _package_version("slaif-api-gateway")
    except Exception:  # noqa: BLE001 - uninstalled dev checkouts
        return "0.0.0+local"


def _money_string(value: Decimal) -> str | None:
    """Quantize to the Numeric(18,9) import contract (9 dp, HALF_UP).

    Returns None when a positive value quantizes to zero (it could not be
    stored without becoming a free price; the model is excluded with an
    explicit reason instead of a guessed/zero value).
    """
    quantized = value.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)
    if quantized == 0 and value > 0:
        return None
    text = f"{quantized:f}"
    return text.rstrip("0").rstrip(".") or "0"


def _baseline_route_flat_capable(baseline_row: object) -> bool:
    """Can a flat standard proposal preserve this baseline route contract?

    Only when the projected contract is exactly one chat_completions block
    with boolean values AND the projection lost nothing
    (``capabilities_unrepresented`` false). Anything else (extra endpoint
    blocks, codex limits, external tools, unrecognized raw values) cannot
    be proposed without claiming a contract the import would not carry, so
    the model is retained locally with an explicit inventory reason.
    """
    if getattr(baseline_row, "capabilities_unrepresented", False):
        return False
    return (
        _flat_from_baseline_chat_block(
            getattr(baseline_row, "capabilities", {})
        )
        is not None
    )


def _flat_from_baseline_chat_block(block: Mapping[str, object]) -> dict[str, bool] | None:
    """Project a baseline chat_completions block onto flat standard keys.

    Only blocks that are exactly the standard create contract (a single
    ``chat_completions`` block) are flat-representable; anything else
    (extra endpoint blocks, codex limits, external tools) cannot be
    preserved by a flat proposal, so the model is retained locally
    instead of being proposed.
    """
    if set(block) != {"chat_completions"}:
        return None
    inner = block["chat_completions"]
    if not isinstance(inner, Mapping):
        return None
    flat: dict[str, bool] = {}
    for flat_key, chat_field in FLAT_CAPABILITY_TO_CHAT_FIELD.items():
        if chat_field in inner:
            value = inner[chat_field]
            if not isinstance(value, bool):
                return None
            flat[flat_key] = value
    return flat


@dataclass(frozen=True)
class _Proposal:
    route: RouteFacts
    model: ModelFacts
    pricing: ModelPricingFacts


def collect_bundle(
    *,
    providers: tuple[str, ...],
    model_include: tuple[str, ...] = (),
    baseline_mode: str,
    baseline: BaselineDocument | None,
    client: httpx.Client,
    now: datetime | None = None,
    fetch: Callable[..., list[RetrievalResult]] = fetch_sources,
    resolve: Callable[..., list[tuple]] = socket.getaddrinfo,
) -> RefreshBundle:
    """Run the full collection and return the canonical bundle.

    Raises CatalogRefreshBlockedError (safe code + detail) for
    collection-level failures that cannot be represented in a bundle
    (budget caps, unknown providers); retrieval and parse failures ARE
    represented (retrieval records / source evidence) and surface as
    deterministic validation blockers instead.
    """
    if baseline_mode not in ("first_install", "db_snapshot", "exported_file"):
        raise CatalogRefreshBlockedError(
            "collection_baseline_mode_invalid", f"unsupported baseline mode {baseline_mode!r}"
        )
    if baseline_mode == "first_install" and baseline is not None:
        raise CatalogRefreshBlockedError(
            "collection_baseline_mismatch", "first_install carries no baseline document"
        )
    if baseline_mode != "first_install" and baseline is None:
        raise CatalogRefreshBlockedError(
            "collection_baseline_missing", f"{baseline_mode} requires a baseline document"
        )
    providers = tuple(sorted(set(providers)))
    if not providers or any(p not in ("openai", "openrouter") for p in providers):
        raise CatalogRefreshBlockedError(
            "collection_providers_invalid", "providers must be a non-empty subset of openai/openrouter"
        )
    model_include = tuple(sorted(set(model_include)))

    started_at = now or datetime.now(UTC)
    retrievals: list[RetrievalResult] = []

    # --- phase 1: whole-catalog snapshots (+ OpenAI model-docs index) ------
    phase1_specs = tuple(sources.plan_catalog_specs(providers))
    phase1 = fetch(phase1_specs, client=client, resolve=resolve)
    retrievals.extend(phase1)

    openrouter_rows: list[se.ParsedModel] = []
    openai_pricing_rows: list[se.ParsedModel] = []
    for result in phase1:
        if not result.ok or result.content is None:
            continue
        parsed = se.parse_snapshot(
            result.spec.provider, result.spec.source_kind, result.content
        )
        if not parsed.ok:
            continue  # recorded via the source record + validation
        if result.spec.provider == "openrouter":
            kept, _duplicates = se.dedupe_parsed_models(parsed)
            openrouter_rows.extend(kept)
        elif result.spec.provider == "openai" and result.spec.source_kind == "openai_pricing_docs":
            kept, _duplicates = se.dedupe_parsed_models(parsed)
            openai_pricing_rows.extend(kept)

    # --- baseline indexes (refresh preservation) ---------------------------
    baseline_route_attrs: dict[tuple[str, str], object] = {}
    baseline_pricing_currencies: dict[tuple[str, str], set[str]] = {}
    if baseline is not None:
        for row in baseline.routes:
            if row.match_type == "exact" and row.endpoint == CHAT_ENDPOINT:
                baseline_route_attrs.setdefault((row.provider, row.requested_model), row)
        for row in baseline.pricing:
            if row.endpoint == CHAT_ENDPOINT:
                baseline_pricing_currencies.setdefault((row.provider, row.upstream_model), set()).add(row.currency)

    include_set = set(model_include)
    inventory: list[CollectionInventoryEntry] = []
    proposals: dict[tuple[str, str], _Proposal] = {}
    page_results: list[RetrievalResult] = []

    # --- OpenRouter eligibility ---------------------------------------------
    for row in sorted(openrouter_rows, key=lambda m: m.model):
        model_id = row.model
        if model_id.endswith(":batch"):
            inventory.append(
                CollectionInventoryEntry(
                    provider="openrouter",
                    model=model_id,
                    disposition="excluded_subset",
                    reason_code=REASON_SERVICE_VARIANT,
                    detail="batch service variant; standard-v1 proposes the canonical chat row",
                )
            )
            continue
        # Provider-alias rows (``~`` prefix) are proposed under their EXACT
        # observed identity when otherwise eligible: the prefix is part of
        # the published model ID, no alias mapping is asserted, and the
        # canonical non-alias identity is frequently absent from the
        # payload entirely (excluding these rows would silently drop fully
        # priced, documented chat models from the default package).
        if row.deprecated is True:
            inventory.append(
                CollectionInventoryEntry(
                    provider="openrouter", model=model_id, disposition="deprecated",
                    reason_code=REASON_DEPRECATED, detail="source deprecation flag is set",
                )
            )
            continue
        missing = [
            dim for dim in ("input", "output")
            if dim in row.non_representable_prices
        ]
        if missing:
            inventory.append(
                CollectionInventoryEntry(
                    provider="openrouter", model=model_id, disposition="incomplete",
                    reason_code=REASON_NEGATIVE_SENTINEL,
                    detail="router -1 sentinel on " + ",".join(sorted(missing)) + " pricing",
                )
            )
            continue
        if row.context_length is None or row.max_output_tokens is None:
            inventory.append(
                CollectionInventoryEntry(
                    provider="openrouter", model=model_id, disposition="incomplete",
                    reason_code=REASON_MISSING_LIMITS,
                    detail="context length and/or max output tokens not published",
                )
            )
            continue
        if row.text_modality is not True:
            inventory.append(
                CollectionInventoryEntry(
                    provider="openrouter", model=model_id, disposition="unsupported",
                    reason_code=REASON_NON_TEXT,
                    detail="text is not an input and output modality",
                )
            )
            continue
        if not {"input", "output"} <= set(row.prices):
            inventory.append(
                CollectionInventoryEntry(
                    provider="openrouter", model=model_id, disposition="incomplete",
                    reason_code="missing_core_prices",
                    detail="input and/or output price not representable in source",
                )
            )
            continue
        if include_set and model_id not in include_set:
            inventory.append(
                CollectionInventoryEntry(
                    provider="openrouter", model=model_id, disposition="excluded_subset",
                    reason_code=REASON_EXPLICIT_SELECTION_EXCLUDED,
                    detail="not in the explicit --models selection",
                )
            )
            continue
        key = ("openrouter", model_id)
        if key in baseline_pricing_currencies and baseline_pricing_currencies[key] != {"USD"}:
            inventory.append(
                CollectionInventoryEntry(
                    provider="openrouter", model=model_id, disposition="excluded_subset",
                    reason_code=REASON_BASELINE_CURRENCY_MISMATCH,
                    detail="baseline pricing currency differs from the published native currency",
                )
            )
            continue
        baseline_row = baseline_route_attrs.get(key)
        if baseline_row is not None and not _baseline_route_flat_capable(baseline_row):
            inventory.append(
                CollectionInventoryEntry(
                    provider="openrouter", model=model_id, disposition="excluded_subset",
                    reason_code=REASON_BASELINE_CONTRACT_NOT_FLAT,
                    detail="baseline route capability contract is not flat-representable; retained locally",
                )
            )
            continue
        proposals[key] = _router_proposal(row, baseline_row, started_at)

    # --- OpenAI candidates and model pages ----------------------------------
    if "openai" in providers:
        standard_rows: dict[str, se.ParsedModel] = {}
        observed: dict[str, list[se.ParsedModel]] = {}
        for row in openai_pricing_rows:
            observed.setdefault(row.model, []).append(row)
            if (
                row.billing_tier == "standard"
                and row.context_band in (None, "short")
                and {"input", "output"} <= set(row.prices)
                and row.model not in standard_rows
            ):
                standard_rows[row.model] = row
        candidates = sorted(standard_rows)
        if include_set:
            candidates = [m for m in candidates if m in include_set]
        if len(candidates) > MAX_OPENAI_MODEL_PAGES:
            raise CatalogRefreshBlockedError(
                "collection_page_cap_exceeded",
                f"{len(candidates)} OpenAI model pages exceed the {MAX_OPENAI_MODEL_PAGES} page bound",
            )
        if candidates:
            page_specs = tuple(sources.model_page_spec("openai", m) for m in candidates)
            page_results = fetch(page_specs, client=client, resolve=resolve)
            retrievals.extend(page_results)

        pages: dict[str, se.ParsedModel | None] = {}
        page_failed: dict[str, str] = {}
        for result in page_results:
            model_id = result.spec.model
            if not result.ok or result.content is None:
                page_failed[model_id] = result.failure_code or "transport_error"
                continue
            parsed = se.parse_snapshot("openai", "docs_page", result.content)
            if not parsed.ok:
                page_failed[model_id] = parsed.error or "page_parse_failed"
                continue
            if not parsed.models:
                page_failed[model_id] = "page_parse_failed"
                continue
            page = parsed.models[0]
            if page.model != model_id:
                page_failed[model_id] = "page_model_mismatch"
                continue
            pages[model_id] = page

        for model_id in sorted(observed):
            row = standard_rows.get(model_id)
            if row is None:
                inventory.append(
                    CollectionInventoryEntry(
                        provider="openai", model=model_id, disposition="incomplete",
                        reason_code=REASON_NO_STANDARD_SHORT,
                        detail="no standard short-context input+output prices published",
                    )
                )
                continue
            if include_set and model_id not in include_set:
                inventory.append(
                    CollectionInventoryEntry(
                        provider="openai", model=model_id, disposition="excluded_subset",
                        reason_code=REASON_EXPLICIT_SELECTION_EXCLUDED,
                        detail="not in the explicit --models selection",
                    )
                )
                continue
            key = ("openai", model_id)
            if key in baseline_pricing_currencies and baseline_pricing_currencies[key] != {"USD"}:
                inventory.append(
                    CollectionInventoryEntry(
                        provider="openai", model=model_id, disposition="excluded_subset",
                        reason_code=REASON_BASELINE_CURRENCY_MISMATCH,
                        detail="baseline pricing currency differs from the published native currency",
                    )
                )
                continue
            baseline_row = baseline_route_attrs.get(key)
            if baseline_row is not None and not _baseline_route_flat_capable(baseline_row):
                inventory.append(
                    CollectionInventoryEntry(
                        provider="openai", model=model_id, disposition="excluded_subset",
                        reason_code=REASON_BASELINE_CONTRACT_NOT_FLAT,
                        detail="baseline route capability contract is not flat-representable; retained locally",
                    )
                )
                continue
            failure = page_failed.get(model_id)
            if failure is not None:
                if failure == "page_model_mismatch":
                    reason = REASON_PAGE_MODEL_MISMATCH
                elif failure.startswith("openai_model_doc"):
                    reason = REASON_PAGE_PARSE_FAILED
                else:
                    reason = REASON_PAGE_UNAVAILABLE
                inventory.append(
                    CollectionInventoryEntry(
                        provider="openai", model=model_id, disposition="incomplete",
                        reason_code=reason, detail=f"model page: {failure}",
                    )
                )
                continue
            page = pages[model_id]
            if page.chat_supported is not True:
                inventory.append(
                    CollectionInventoryEntry(
                        provider="openai", model=model_id, disposition="incomplete",
                        reason_code=REASON_PAGE_NO_CHAT,
                        detail="official model page does not list Chat Completions as supported",
                    )
                )
                continue
            if page.text_modality is not True:
                inventory.append(
                    CollectionInventoryEntry(
                        provider="openai", model=model_id, disposition="unsupported",
                        reason_code=REASON_PAGE_NO_TEXT,
                        detail="official model page reports no text output modality",
                    )
                )
                continue
            if page.context_length is None:
                inventory.append(
                    CollectionInventoryEntry(
                        provider="openai", model=model_id, disposition="incomplete",
                        reason_code=REASON_MISSING_LIMITS,
                        detail="official model page does not publish a context window",
                    )
                )
                continue
            # Page prices must exactly match the pricing table's standard
            # short row (a conflicting authoritative page never proposes).
            for dim in ("input", "output", "cached_input"):
                page_value = page.prices.get(dim)
                table_value = row.prices.get(dim)
                if page_value is not None and table_value is not None and page_value != table_value:
                    inventory.append(
                        CollectionInventoryEntry(
                            provider="openai", model=model_id, disposition="incomplete",
                            reason_code=REASON_PAGE_PRICE_CONFLICT,
                            detail=f"model page {dim} price conflicts with the pricing table",
                        )
                    )
                    break
            else:
                proposals[key] = _openai_proposal(row, page, baseline_row, started_at)

    # --- FX: only pairs a proposed non-EUR price actually needs -------------
    # The bundle records each needed quote EXACTLY AS PUBLISHED (EUR is the
    # implicit base currency of the ECB reference XML). The native -> EUR
    # rate the runtime looks up is derived by the tested 180 FX gate (exact
    # Decimal reciprocal, 9 dp HALF_UP) and is marked derived_reciprocal /
    # source_pair in every comparison and artifact row, so the published
    # direction is never relabeled at collection time.
    needed_currencies = {
        item.pricing.currency for item in proposals.values() if item.pricing.currency != EUR
    }
    fx_facts: list[FxFacts] = []
    ecb_published_at: datetime | None = None
    ecb_sources: list[SourceRecord] = []
    if needed_currencies:
        ecb_spec = sources.ecb_spec()
        ecb_result = fetch((ecb_spec,), client=client, resolve=resolve)[0]
        retrievals.append(ecb_result)
        if ecb_result.ok and ecb_result.content is not None:
            parsed_ecb = se.parse_snapshot("ecb", "ecb_reference_xml", ecb_result.content)
            if parsed_ecb.ok:
                ecb_published_at = (
                    datetime(
                        max(q.published_date for q in parsed_ecb.fx_quotes).year,
                        max(q.published_date for q in parsed_ecb.fx_quotes).month,
                        max(q.published_date for q in parsed_ecb.fx_quotes).day,
                        tzinfo=UTC,
                    )
                )
                for currency in sorted(needed_currencies):
                    quotes = [
                        q for q in parsed_ecb.fx_quotes
                        if {q.base_currency, q.quote_currency} == {EUR, currency}
                    ]
                    if not quotes:
                        continue  # validation reports the unbound currency
                    latest = max(quotes, key=lambda q: q.published_date)
                    pair_ref = f"{latest.base_currency}-{latest.quote_currency}"
                    ecb_sources.append(
                        SourceRecord(
                            provider="ecb",
                            model=pair_ref,
                            source_kind="ecb_reference_xml",
                            url=ecb_result.spec.url,
                            retrieved_at=ecb_result.retrieved_at,
                            published_at=ecb_published_at,
                            content_sha256=ecb_result.content_sha256(),
                            evidence_b64=base64.b64encode(ecb_result.content).decode("ascii"),
                            extractor=EXTRACTOR_ID,
                            extraction="deterministic",
                            required=True,
                            truncated=False,
                        )
                    )
                    fx_facts.append(
                        FxFacts(
                            base_currency=latest.base_currency,
                            quote_currency=latest.quote_currency,
                            rate=str(latest.rate),
                            valid_from=started_at,
                            valid_until=None,
                            published_at=datetime(latest.published_date.year, latest.published_date.month, latest.published_date.day, tzinfo=UTC),
                            source=ecb_result.spec.url,
                            provenance=FieldProvenance(
                                sources=(f"ecb|{pair_ref}|ecb_reference_xml",),
                                extractor=EXTRACTOR_ID,
                                extraction="deterministic",
                            ),
                        )
                    )

    # --- source records for every successfully fetched, included snapshot ---
    source_records: list[SourceRecord] = []
    for result in phase1 + page_results:
        if not result.ok or result.content is None:
            continue
        spec = result.spec
        published_at = None
        if spec.provider == "ecb":
            published_at = ecb_published_at
        source_records.append(
            SourceRecord(
                provider=spec.provider,
                model=spec.model,
                source_kind=spec.source_kind,
                url=spec.url,
                retrieved_at=result.retrieved_at,
                published_at=published_at,
                content_sha256=result.content_sha256(),
                evidence_b64=base64.b64encode(result.content).decode("ascii"),
                extractor=EXTRACTOR_ID,
                extraction="deterministic",
                required=spec.required,
                truncated=False,
            )
        )
    source_records.extend(ecb_sources)
    source_records.sort(
        key=lambda s: (s.provider, s.model, s.source_kind, s.url)
    )

    # --- assemble facts ------------------------------------------------------
    routes = [p.route for p in (proposals[k] for k in sorted(proposals))]
    models = [p.model for p in (proposals[k] for k in sorted(proposals))]
    pricing = [p.pricing for p in (proposals[k] for k in sorted(proposals))]

    finished_at = datetime.now(UTC) if now is None else now
    retrievals.sort(key=lambda r: (r.spec.provider, r.spec.url, r.retrieved_at))
    retrieval_records = tuple(_retrieval_record(r, ecb_published_at) for r in retrievals)
    inventory.sort(key=lambda e: (e.provider, e.model, e.reason_code))

    content_digest = hashlib.sha256(
        "|".join(
            sorted(r.content_sha256() or "" for r in retrievals if r.ok)
            + [",".join(providers), ",".join(model_include), baseline_mode]
        ).encode("utf-8")
    ).hexdigest()[:12]
    run_id = f"collect-{started_at:%Y%m%d}-{started_at:%H%M%S}-{content_digest}"

    baseline_identity = (
        BaselineIdentity(mode="first_install")
        if baseline_mode == "first_install"
        else BaselineIdentity(
            mode=baseline_mode,
            exported_at=baseline.exported_at,
            target_database=(
                f"{baseline.target.server_host}:{baseline.target.server_port}/"
                f"{baseline.target.database}"
            ),
            postgres_version=baseline.target.postgres_version,
            sql_checked=baseline.sql_checked,
            row_counts={
                "providers": baseline.counts.providers,
                "routes": baseline.counts.routes,
                "pricing_rules": baseline.counts.pricing_rules,
                "fx_rates": baseline.counts.fx_rates,
            },
            content_sha256=baseline.content_sha256,
        )
    )

    version = package_version()
    return RefreshBundle(
        schema_version=SCHEMA_VERSION,
        run_id=run_id,
        generated_at=finished_at,
        revision=RevisionIdentity(
            schema_version=SCHEMA_VERSION,
            slaif_revision=version,
            renderer_version=RENDERER_VERSION,
            policy_version=POLICY_VERSION,
        ),
        research=ResearchIdentity(
            status="NOT_RUN",
            extractor_version=EXTRACTOR_ID,
            tool_version=version,
        ),
        collection=CollectionIdentity(
            tool=f"slaif-gateway/{version}",
            code_revision=f"slaif-api-gateway=={version}",
            profile="standard-v1",
            providers=providers,
            model_include=model_include,
            started_at=started_at,
            finished_at=finished_at,
            retrievals=retrieval_records,
            inventory=tuple(inventory),
            deduplicated_fetches=True,
        ),
        policy=PolicyDocument(),
        profile=ProfileContract(
            name="standard-v1",
            endpoint=CHAT_ENDPOINT,
            supports_streaming=True,
            local_models_visible=True,
            capability_allowlist=(),
        ),
        selection=Selection(providers=providers, model_include=model_include),
        sources=tuple(source_records),
        models=tuple(models),
        pricing=tuple(pricing),
        routes=tuple(routes),
        fx=tuple(fx_facts),
        baseline=baseline_identity,
        notes=(
            f"standard-v1 collection: {len(proposals)} proposed model(s), "
            f"{len(inventory)} reconciled exclusion(s); Codex research NOT_RUN; "
            "no import/apply performed"
        ),
    )


def _router_proposal(
    row: se.ParsedModel, baseline_row: object | None, valid_from: datetime
) -> _Proposal:
    provider, model_id = "openrouter", row.model
    provenance = FieldProvenance(
        sources=(f"openrouter|{CATALOG_MODEL}|openrouter_models_api",),
        extractor=EXTRACTOR_ID,
        extraction="deterministic",
    )
    supports_streaming = True
    flat_capabilities = {"text": True, "streaming": True}
    priority = 100
    enabled = True
    visible = True
    if baseline_row is not None:
        priority = baseline_row.priority
        enabled = baseline_row.enabled
        visible = baseline_row.visible_in_models
        supports_streaming = baseline_row.supports_streaming
        flat = _flat_from_baseline_chat_block(baseline_row.capabilities)
        if flat is not None:
            flat_capabilities = flat
    dims: list[PricingDimension] = []
    for dim in ("input", "output", "cached_input"):
        value = row.prices.get(dim)
        if value is None:
            continue
        text = _money_string(value)
        if text is None:
            continue
        dims.append(
            PricingDimension(name=dim, value=text, unit="per_1m_tokens", currency="USD")
        )
    route = RouteFacts(
        provider=provider,
        requested_model=model_id,
        upstream_model=model_id,
        match_type="exact",
        endpoint=CHAT_ENDPOINT,
        priority=priority,
        enabled=enabled,
        visible_in_models=visible,
        supports_streaming=supports_streaming,
        capabilities=flat_capabilities,
        provenance=provenance,
    )
    model = ModelFacts(
        provider=provider,
        model=model_id,
        display_name=model_id,
        context_length=row.context_length,
        max_output_tokens=row.max_output_tokens,
        supports_streaming=supports_streaming,
        capabilities={"text": True, "streaming": supports_streaming},
        deprecated=False,
        provenance=provenance,
    )
    pricing = ModelPricingFacts(
        provider=provider,
        model=model_id,
        endpoint=CHAT_ENDPOINT,
        currency="USD",
        dimensions=tuple(dims),
        valid_from=valid_from,
        provenance=provenance,
    )
    return _Proposal(route=route, model=model, pricing=pricing)


def _openai_proposal(
    row: se.ParsedModel,
    page: se.ParsedModel,
    baseline_row: object | None,
    valid_from: datetime,
) -> _Proposal:
    provider, model_id = "openai", row.model
    price_sources = (f"openai|{CATALOG_MODEL}|openai_pricing_docs", f"openai|{model_id}|docs_page")
    page_provenance = FieldProvenance(
        sources=(f"openai|{model_id}|docs_page",),
        extractor=EXTRACTOR_ID,
        extraction="deterministic",
    )
    price_provenance = FieldProvenance(
        sources=price_sources,
        extractor=EXTRACTOR_ID,
        extraction="deterministic",
    )
    supports_streaming = True
    flat_capabilities = {"text": True, "streaming": True}
    priority = 100
    enabled = True
    visible = True
    if baseline_row is not None:
        priority = baseline_row.priority
        enabled = baseline_row.enabled
        visible = baseline_row.visible_in_models
        supports_streaming = baseline_row.supports_streaming
        flat = _flat_from_baseline_chat_block(baseline_row.capabilities)
        if flat is not None:
            flat_capabilities = flat
    dims: list[PricingDimension] = []
    for dim in ("input", "output", "cached_input"):
        value = row.prices.get(dim)
        if value is None:
            continue
        text = _money_string(value)
        if text is None:
            continue
        dims.append(
            PricingDimension(name=dim, value=text, unit="per_1m_tokens", currency="USD")
        )
    route = RouteFacts(
        provider=provider,
        requested_model=model_id,
        upstream_model=model_id,
        match_type="exact",
        endpoint=CHAT_ENDPOINT,
        priority=priority,
        enabled=enabled,
        visible_in_models=visible,
        supports_streaming=supports_streaming,
        capabilities=flat_capabilities,
        provenance=page_provenance,
    )
    model = ModelFacts(
        provider=provider,
        model=model_id,
        display_name=model_id,
        context_length=page.context_length,
        max_output_tokens=page.max_output_tokens,
        supports_streaming=supports_streaming,
        capabilities={"text": True, "streaming": supports_streaming},
        deprecated=False,
        provenance=page_provenance,
    )
    pricing = ModelPricingFacts(
        provider=provider,
        model=model_id,
        endpoint=CHAT_ENDPOINT,
        currency="USD",
        dimensions=tuple(dims),
        valid_from=valid_from,
        provenance=price_provenance,
    )
    return _Proposal(route=route, model=model, pricing=pricing)


def _retrieval_record(result: RetrievalResult, ecb_published_at: datetime | None) -> SourceRetrievalRecord:
    published_at = None
    if result.spec.provider == "ecb" and ecb_published_at is not None:
        published_at = ecb_published_at
    return SourceRetrievalRecord(
        requested_url=result.spec.url,
        final_url=result.final_url,
        retrieved_at=result.retrieved_at,
        outcome="ok" if result.ok else "failed",
        status=result.status,
        failure_code=result.failure_code,
        content_type=result.content_type,
        content_bytes=len(result.content) if result.content is not None else None,
        content_sha256=result.content_sha256(),
        attempts=result.attempts,
        redirects=result.redirects,
        published_at=published_at,
    )
