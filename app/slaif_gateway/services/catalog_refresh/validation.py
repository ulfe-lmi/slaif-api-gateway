"""Deterministic readiness, completeness, and validator recomputation.

Everything reported as state, count, or evidence is recomputed here from the
normalized bundle, the baseline rows, and the exact generated artifact bytes.
No caller-supplied readiness, confidence, counters, or authority labels are
ever trusted (180-b).

State model (180-b):
- Genuinely unchanged rows are no-ops: they are excluded from the mutation
  plan and from the executable artifacts, and they carry no gate impact.
- Any actually-blocked proposed mutation (an existing-row update/supersession
  that no create-only executor can run) makes the overall state BLOCKED.
- Any REVIEW gate or review finding makes the state at least
  READY_WITH_WARNINGS. Gate failures are first-class findings: they appear in
  the warning list and the counts, so BLOCKED is never shown with zero
  blocking issues.
- Executable import artifacts contain only permitted create rows.

FX direction (180-b): the runtime converts costs with
``find_latest_rate(base_currency=native, quote_currency=EUR)``, so the
canonical import-ready pair is native -> EUR. A supplied EUR -> native
quotation may be reciprocated deterministically (Decimal, explicit
precision) and is then recorded as *derived* — never silently relabeled.

Source trust (180-b): authority is derived from (provider, source_kind) ->
official-host rules plus evidence binding; a declared content digest without
supplied matching evidence is REVIEW ("not verifiable offline"), and
disagreement in required facts across independently represented
observations is BLOCKED.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Any
from urllib.parse import urlparse

from slaif_gateway.schemas.catalog_refresh import (
    CAPABILITY_KEYS,
    FX_PAIR_PATTERN,
    BaselineDocument,
    RefreshBundle,
    RouteFacts,
)
from slaif_gateway.services.catalog_refresh import source_evidence as se
from slaif_gateway.services.catalog_refresh.bundle import (
    NormalizedFxRow,
    generate_fx_json,
    generate_pricing_tsv,
    generate_route_tsv,
    selected_model_keys,
)
from slaif_gateway.services.catalog_refresh.errors import CatalogRefreshBlockedError
from slaif_gateway.services.catalog_refresh.policy import RefreshPolicy
from slaif_gateway.services.fx_import import (
    classify_fx_import_preview,
    validate_fx_import_rows,
)
from slaif_gateway.services.pricing_import import (
    build_pricing_import_execution_plan,
    classify_pricing_import_preview,
    parse_pricing_import_tsv,
    validate_pricing_import_rows,
)
from slaif_gateway.services.route_import import (
    RouteImportProviderRef,
    build_route_import_execution_plan,
    classify_route_import_preview,
    parse_route_import_tsv,
    validate_route_import_rows,
)

OVERALL_READY = "READY"
OVERALL_READY_WITH_WARNINGS = "READY_WITH_WARNINGS"
OVERALL_BLOCKED = "BLOCKED"

SEVERITY_BLOCKER = "BLOCKER"
SEVERITY_REVIEW = "REVIEW"
SEVERITY_INFO = "INFO"

EVIDENCE_VERIFIED = "VERIFIED"
EVIDENCE_REVIEW = "REVIEW"
EVIDENCE_BLOCKED = "BLOCKED"
EVIDENCE_NA = "N/A"

SOURCE_OFFICIAL = "OFFICIAL"
SOURCE_REVIEW = "REVIEW"
SOURCE_BLOCKED = "BLOCKED"

EVIDENCE_OK = "verified"
EVIDENCE_NOT_SUPPLIED = "not_supplied"

DISPOSITION_NEW = "NEW"
DISPOSITION_CHANGED = "CHANGED"
DISPOSITION_UNCHANGED = "UNCHANGED"
DISPOSITION_EXCLUDED = "EXCLUDED"
DISPOSITION_BLOCKED = "BLOCKED"
DISPOSITION_DISAPPEARED = "DISAPPEARED"
DISPOSITION_DEPRECATED = "DEPRECATED"
DISPOSITION_NOT_FETCHED = "NOT_FETCHED"

ROUTE_GATE = "import.routes"
PRICING_GATE = "import.pricing"
FX_GATE = "import.fx"
GATE_SOURCES = "sources"
GATE_SCHEMA = "schema"
GATE_PRICING_COMPLETE = "pricing.complete"
GATE_PAIRING = "pairing"
GATE_UNSUPPORTED = "unsupported"
GATE_CHANGES = "changes"
GATE_COMPLETENESS = "completeness"

_GATE_ORDER = [
    GATE_SOURCES,
    GATE_SCHEMA,
    GATE_PRICING_COMPLETE,
    GATE_PAIRING,
    GATE_UNSUPPORTED,
    GATE_CHANGES,
    GATE_COMPLETENESS,
    ROUTE_GATE,
    PRICING_GATE,
    FX_GATE,
]

# (provider, source_kind) -> exact official hosts (suffix-matched).
# A safe URL is not an authoritative source: only these derivations may ever
# be classified OFFICIAL. Anything else is REVIEW at best, BLOCKED when the
# provider/source-kind combination itself is unsupported.
_OFFICIAL_HOST_RULES: dict[tuple[str, str], frozenset[str]] = {
    ("openrouter", "openrouter_models_api"): frozenset({"openrouter.ai"}),
    ("openrouter", "openrouter_model_detail"): frozenset({"openrouter.ai"}),
    ("openai", "openai_models_api"): frozenset({"api.openai.com"}),
    ("openai", "openai_pricing_docs"): frozenset({"openai.com"}),
    ("openai", "docs_page"): frozenset({"openai.com"}),
    ("openrouter", "docs_page"): frozenset({"openrouter.ai"}),
    # ECB is the FX reference publisher (its own identity, never a model
    # provider's source): only the EUR-based reference-rate snapshot kind.
    ("ecb", "ecb_reference_xml"): frozenset({"www.ecb.europa.eu", "data-api.ecb.europa.eu"}),
}
# FX sources are identified by a currency-pair "model" part (FX_PAIR_PATTERN
# from the schema) and may cite the official FX reference publisher in
# addition to the provider docs host.
_FX_DOCS_HOSTS: frozenset[str] = frozenset({"www.ecb.europa.eu", "data-api.ecb.europa.eu"})
# FX provenance references must use an FX-specific source kind (a model's
# OpenRouter reference may never be borrowed to satisfy an FX fact).
_FX_SOURCE_KINDS: frozenset[str] = frozenset({"operator_input", "docs_page", "ecb_reference_xml"})

EVIDENCE_MAX_BYTES = 4 * 1024 * 1024
_RECIPROCAL_QUANTUM = Decimal("0.000000001")
_FX_CONSISTENCY_TOLERANCE = Decimal("0.00000001")


@dataclass(frozen=True, slots=True)
class Gate:
    name: str
    evidence: str
    detail: str


@dataclass(frozen=True, slots=True)
class Warning:
    severity: str
    code: str
    provider: str | None
    model: str | None
    detail: str


@dataclass(frozen=True, slots=True)
class Disposition:
    provider: str
    model: str
    disposition: str
    detail: str


@dataclass(frozen=True, slots=True)
class PriceComparison:
    provider: str
    model: str
    dimension: str
    old: str | None
    new: str | None
    currency_old: str | None
    currency_new: str | None
    percent_change: str | None
    state: str


@dataclass(frozen=True, slots=True)
class ImportGate:
    kind: str
    schema_valid: bool
    total_rows: int
    valid_rows: int
    invalid_rows: int
    classifications: dict[str, int]
    plan_ready_rows: int
    plan_blocked_rows: int
    detail: str
    excluded_mutations: int = 0


@dataclass(slots=True)
class ValidationReport:
    state: str
    state_reason: str
    run_id: str
    generated_at: str
    policy_version: int
    counts: dict[str, int]
    per_provider: dict[str, dict[str, int]]
    dispositions: list[Disposition]
    price_comparisons: list[PriceComparison]
    warnings: list[Warning]
    gates: list[Gate]
    import_gates: list[ImportGate]
    baseline: dict[str, Any]
    research: dict[str, Any]
    artifacts: dict[str, Any]
    sql_checks: dict[str, Any] = field(default_factory=dict)
    sources: list[dict[str, Any]] = field(default_factory=list)
    fx_comparisons: list[dict[str, Any]] = field(default_factory=list)
    source_evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        order = {name: index for index, name in enumerate(_GATE_ORDER)}
        return {
            "state": self.state,
            "state_reason": self.state_reason,
            "run_id": self.run_id,
            "generated_at": self.generated_at,
            "policy_version": self.policy_version,
            "counts": dict(sorted(self.counts.items())),
            "per_provider": {
                provider: dict(sorted(values.items()))
                for provider, values in sorted(self.per_provider.items())
            },
            "dispositions": [
                {
                    "provider": item.provider,
                    "model": item.model,
                    "disposition": item.disposition,
                    "detail": item.detail,
                }
                for item in sorted(self.dispositions, key=lambda d: (d.provider, d.model))
            ],
            "price_comparisons": [
                {
                    "provider": item.provider,
                    "model": item.model,
                    "dimension": item.dimension,
                    "old": item.old,
                    "new": item.new,
                    "currency_old": item.currency_old,
                    "currency_new": item.currency_new,
                    "percent_change": item.percent_change,
                    "state": item.state,
                }
                for item in sorted(
                    self.price_comparisons, key=lambda p: (p.provider, p.model, p.dimension)
                )
            ],
            "warnings": [
                {
                    "severity": item.severity,
                    "code": item.code,
                    "provider": item.provider,
                    "model": item.model,
                    "detail": item.detail,
                }
                for item in sorted(
                    self.warnings, key=lambda w: (w.severity, w.code, w.provider or "", w.model or "")
                )
            ],
            "gates": [
                {"name": gate.name, "evidence": gate.evidence, "detail": gate.detail}
                for gate in sorted(self.gates, key=lambda g: (order.get(g.name, len(order)), g.name))
            ],
            "import_gates": [
                {
                    "kind": gate.kind,
                    "schema_valid": gate.schema_valid,
                    "total_rows": gate.total_rows,
                    "valid_rows": gate.valid_rows,
                    "invalid_rows": gate.invalid_rows,
                    "classifications": dict(sorted(gate.classifications.items())),
                    "plan_ready_rows": gate.plan_ready_rows,
                    "plan_blocked_rows": gate.plan_blocked_rows,
                    "detail": gate.detail,
                    "excluded_mutations": gate.excluded_mutations,
                }
                for gate in sorted(self.import_gates, key=lambda g: g.kind)
            ],
            "baseline": dict(sorted(self.baseline.items())),
            "research": dict(sorted(self.research.items())),
            "artifacts": dict(sorted(self.artifacts.items())),
            "sql_checks": dict(sorted(self.sql_checks.items())),
            "sources": [
                dict(sorted(item.items())) for item in sorted(
                    self.sources, key=lambda s: (s["provider"], s["model"], s["source_kind"])
                )
            ],
            "source_evidence": self.source_evidence,
            "fx_comparisons": [
                dict(sorted(item.items())) for item in sorted(
                    self.fx_comparisons, key=lambda f: str(f.get("pair", ""))
                )
            ],
        }


def validation_json_bytes(report: ValidationReport) -> bytes:
    """Exact canonical encoding shared by the CLI writer and the verifier."""
    return (json.dumps(report.to_dict(), sort_keys=True, indent=1, default=str) + "\n").encode("utf-8")


def _utc(value: datetime) -> datetime:
    return value.astimezone(UTC)


def _pct(old: Decimal, new: Decimal) -> str:
    """Signed relative change quantized to 1e-6 (never divides by zero)."""
    delta = (new - old) / old
    return str(delta.quantize(Decimal("0.000001")))


def _reciprocal(rate: Decimal) -> Decimal:
    """Deterministic reciprocal with explicit 9-decimal precision."""
    return (Decimal(1) / rate).quantize(_RECIPROCAL_QUANTUM, rounding=ROUND_HALF_UP)


def _select_active_pricing(rows, now: datetime) -> tuple[Any, bool]:
    """Select the baseline pricing row active at ``now``.

    Mirrors the runtime active lookup: disabled rows are excluded, the
    window is strict ``valid_from <= now < valid_until``, and there is NO
    fallback to expired or future rows. Overlapping active rows with
    different values are ambiguous (the caller blocks on that signal)
    instead of inventing a before-value.
    """
    active = [
        row
        for row in rows
        if row.enabled
        and _utc(row.valid_from) <= now
        and (row.valid_until is None or _utc(row.valid_until) > now)
    ]
    if not active:
        return None, False
    distinct = {
        (
            row.currency,
            row.input_price_per_1m,
            row.cached_input_price_per_1m,
            row.output_price_per_1m,
            row.reasoning_price_per_1m,
            row.request_price,
        )
        for row in active
    }
    if len(distinct) > 1:
        return None, True
    return max(active, key=lambda row: _utc(row.valid_from)), False


def _select_active_fx(rows, now: datetime) -> tuple[Any, bool]:
    """Strict-window FX selection (FX rows carry no enabled flag); no fallback."""
    active = [
        row
        for row in rows
        if _utc(row.valid_from) <= now and (row.valid_until is None or _utc(row.valid_until) > now)
    ]
    if not active:
        return None, False
    if len({row.rate for row in active}) > 1:
        return None, True
    return max(active, key=lambda row: _utc(row.valid_from)), False


def _host_allowed(hostname: str, hosts: frozenset[str]) -> bool:
    host = (hostname or "").lower()
    return any(host == official or host.endswith("." + official) for official in hosts)


def _classify_source(
    source,
    *,
    now: datetime,
    policy: RefreshPolicy,
    add,
) -> dict[str, Any]:
    """Derive the trust classification of one source record.

    OFFICIAL: exact official host for the (provider, source_kind) rule,
    deterministic extraction, and supplied evidence whose bytes match the
    declared content digest.
    REVIEW: safe but non-official host, operator-supplied or semantic
    extraction, or a declared digest with no supplied evidence ("not
    verifiable offline" — this run never fetches live sources).
    BLOCKED: unsupported provider/source-kind combination, lookalike or
    otherwise off-rule host, or supplied evidence that contradicts the
    declared digest.
    """
    provider = source.provider
    kind = source.source_kind
    model = source.model
    findings: list[tuple[str, str]] = []

    age = now - _utc(source.retrieved_at)
    if age < timedelta(0):
        add(SEVERITY_BLOCKER, "future_source_timestamp", "retrieved_at is after generated_at", provider, model)
        age_state = "blocked"
    else:
        age_state = policy.source_age_state(age)
        if age_state == "review":
            add(SEVERITY_REVIEW, "source_stale_review", f"source age {age} exceeds review threshold", provider, model)
        elif age_state == "blocked":
            add(SEVERITY_BLOCKER, "source_stale_blocked", f"source age {age} exceeds blocked threshold", provider, model)
    if source.truncated:
        if source.required:
            add(
                SEVERITY_BLOCKER,
                "source_truncated_blocked",
                "a required source for this model is truncated; its required import plan is blocked",
                provider,
                model,
            )
        else:
            add(SEVERITY_REVIEW, "source_truncated_optional", "an optional source for this model was truncated", provider, model)
    for warning in source.warnings:
        add(SEVERITY_REVIEW, "source_warning", warning, provider, model)

    # --- host / kind rules ------------------------------------------------
    pair_model = bool(FX_PAIR_PATTERN.fullmatch(model))
    hosts = _OFFICIAL_HOST_RULES.get((provider, kind))
    if hosts is None:
        if kind in (
            "openrouter_models_api",
            "openrouter_model_detail",
            "openai_models_api",
            "openai_pricing_docs",
            "ecb_reference_xml",
        ):
            findings.append(("mismatch", f"source kind {kind} does not match provider {provider}"))
            host_ok = False
        elif kind == "operator_input":
            host_ok = True  # operator-supplied: never OFFICIAL, never host-blocked
        else:
            findings.append(("unsupported", f"unsupported provider/source-kind combination {provider}/{kind}"))
            host_ok = False
    else:
        allowed = set(hosts)
        if pair_model:
            allowed |= _FX_DOCS_HOSTS
        parsed = urlparse(source.url)
        host_ok = _host_allowed(parsed.hostname or "", frozenset(allowed))
        if not host_ok:
            findings.append(("offhost", f"host is not the official host for {provider}/{kind}"))

    # --- evidence binding ---------------------------------------------------
    evidence_state = EVIDENCE_NOT_SUPPLIED
    if source.evidence_b64 is not None:
        try:
            evidence_bytes = base64.b64decode(source.evidence_b64, validate=True)
        except (binascii.Error, ValueError):
            add(SEVERITY_BLOCKER, "evidence_invalid_base64", "inline evidence is not valid base64", provider, model)
            evidence_state = "invalid"
            evidence_bytes = None
        else:
            if len(evidence_bytes) > EVIDENCE_MAX_BYTES:
                add(SEVERITY_BLOCKER, "evidence_too_large", f"inline evidence exceeds the {EVIDENCE_MAX_BYTES} byte bound", provider, model)
                evidence_state = "invalid"
            else:
                digest = hashlib.sha256(evidence_bytes).hexdigest()
                if digest != source.content_sha256:
                    add(
                        SEVERITY_BLOCKER,
                        "evidence_digest_mismatch",
                        "supplied evidence bytes do not match the declared content digest",
                        provider,
                        model,
                    )
                    evidence_state = "invalid"
                else:
                    evidence_state = EVIDENCE_OK

    if any(tag in ("mismatch", "unsupported") for tag, _ in findings) or evidence_state == "invalid":
        classification = SOURCE_BLOCKED
    elif kind == "operator_input" or source.extraction == "semantic" or not host_ok or evidence_state != EVIDENCE_OK:
        classification = SOURCE_REVIEW
    else:
        classification = SOURCE_OFFICIAL
        # A caller-declared "deterministic" label alone never establishes
        # trust: OFFICIAL additionally requires a reviewed registered parser
        # for (provider, source_kind). The parse itself is verified in the
        # evidence phase (a failed parse demotes or blocks the source).
        if not se.has_deterministic_parser(provider, kind):
            add(
                SEVERITY_REVIEW,
                "source_evidence_unapproved",
                "deterministic extraction claimed without a reviewed registered parser; source cannot be OFFICIAL",
                provider,
                model,
            )
            classification = SOURCE_REVIEW

    if classification == SOURCE_BLOCKED:
        add(SEVERITY_BLOCKER, "source_provenance_blocked", "; ".join(text for _, text in findings)[:400], provider, model)
    elif classification == SOURCE_REVIEW:
        reason = (
            "operator-supplied" if kind == "operator_input"
            else "semantic extraction" if source.extraction == "semantic"
            else "off-official-host" if not host_ok
            else "evidence not supplied (not verifiable offline)"
        )
        add(SEVERITY_REVIEW, "source_provenance_review", reason, provider, model)

    return {
        "provider": provider,
        "model": model,
        "source_kind": kind,
        "url": source.url,
        "content_sha256": source.content_sha256,
        "retrieved_at": source.retrieved_at.isoformat(),
        "published_at": source.published_at.isoformat() if source.published_at else None,
        "truncated": source.truncated,
        "age_state": age_state,
        "classification": classification,
        "evidence_state": evidence_state,
    }


def _fact_observations(model_facts, route_facts, pricing_facts) -> dict[str, list[tuple[str, str]]]:
    """Semantic field -> [(source_key, value)] across all facts of one model.

    Each fact attributes its values to every provenance source that backs it;
    two facts of the same model carrying different values for the same
    semantic field are contradictory observations, whatever their sources.
    """
    observations: dict[str, list[tuple[str, str]]] = {}

    def record(fact, prefix: str, values: dict[str, str | int | bool]) -> None:
        for source_key in fact.provenance.sources:
            for field_name, value in values.items():
                if value is None:
                    continue
                observations.setdefault(f"{prefix}:{field_name}", []).append((source_key, str(value)))

    if model_facts is not None:
        values = {
            "context_length": model_facts.context_length,
            "max_output_tokens": model_facts.max_output_tokens,
            "deprecated": model_facts.deprecated,
            "supports_streaming": model_facts.supports_streaming,
        }
        values.update({f"capability:{key}": value for key, value in model_facts.capabilities.items()})
        record(model_facts, "model", values)
    if route_facts is not None:
        values = {
            "upstream_model": route_facts.upstream_model,
            "priority": route_facts.priority,
            "match_type": route_facts.match_type,
            "supports_streaming": route_facts.supports_streaming,
        }
        values.update({f"capability:{key}": value for key, value in route_facts.capabilities.items()})
        record(route_facts, "route", values)
    if pricing_facts is not None:
        values = {"currency": pricing_facts.currency}
        values.update({f"dim:{d.name}": d.value for d in pricing_facts.dimensions if d.value is not None})
        record(pricing_facts, "pricing", values)
    return observations


def validate_bundle(
    bundle: RefreshBundle,
    baseline: BaselineDocument | None,
    policy: RefreshPolicy,
) -> tuple[ValidationReport, dict[str, bytes]]:
    """Recompute the full review result. Pure and deterministic."""
    warnings: list[Warning] = []
    now = _utc(bundle.generated_at)
    selected = selected_model_keys(bundle)

    def add(severity: str, code: str, detail: str, provider: str | None = None, model: str | None = None) -> None:
        warnings.append(Warning(severity, code, provider, model, detail))

    # --- baseline indexes -------------------------------------------------
    baseline_routes_by_identity: dict[tuple[str, str, str, str], list[Any]] = {}
    baseline_pricing_by_key: dict[tuple[str, str, str], list[Any]] = {}
    baseline_fx_by_pair: dict[tuple[str, str], list[Any]] = {}
    if baseline is not None:
        for row in baseline.routes:
            baseline_routes_by_identity.setdefault(
                (row.provider, row.requested_model, row.match_type, row.endpoint), []
            ).append(row)
        for row in baseline.pricing:
            baseline_pricing_by_key.setdefault((row.provider, row.upstream_model, row.endpoint), []).append(row)
        for row in baseline.fx:
            baseline_fx_by_pair.setdefault((row.base_currency, row.quote_currency), []).append(row)

    # Explicitly selected models and, for an unscoped selection, the full
    # baseline scope must be considered even when the bundle carries no facts
    # for them: a missing explicitly required selection is visible, never
    # hidden, and disappearance/outage semantics are decided per model.
    selection_providers = set(bundle.selection.providers)
    fact_keys = {
        (item.provider, getattr(item, "model", None) or item.requested_model)
        for item in (*bundle.models, *bundle.pricing, *bundle.routes)
    }
    if bundle.selection.model_include:
        for model in sorted(set(bundle.selection.model_include)):
            if any((provider, model) in fact_keys for provider in selection_providers):
                continue
            holders = _baseline_model_providers(baseline, model, selection_providers)
            if holders:
                selected.update((provider, model) for provider in holders)
            else:
                selected.update((provider, model) for provider in selection_providers)
    elif baseline is not None:
        for row in baseline.routes:
            if row.provider in selection_providers:
                selected.add((row.provider, row.requested_model))
        for row in baseline.pricing:
            if row.provider in selection_providers:
                selected.add((row.provider, row.upstream_model))

    evidence_backed_facts: list[dict[str, Any]] = []
    models_by_key = {(item.provider, item.model): item for item in bundle.models}
    pricing_by_key: dict[tuple[str, str], list[Any]] = {}
    for item in bundle.pricing:
        pricing_by_key.setdefault((item.provider, item.model), []).append(item)
    routes_by_key: dict[tuple[str, str], list[Any]] = {}
    for item in bundle.routes:
        routes_by_key.setdefault((item.provider, item.requested_model), []).append(item)
    sources_by_key: dict[tuple[str, str], list[Any]] = {}
    for source in bundle.sources:
        sources_by_key.setdefault((source.provider, source.model), []).append(source)

    # --- out-of-scope facts are counted explicitly, never silently dropped
    out_of_scope = sum(
        1
        for item in (*bundle.models, *bundle.pricing, *bundle.routes)
        if (getattr(item, "provider"), getattr(item, "model", None) or getattr(item, "requested_model")) not in selected
    )

    # --- source assessments (trust is derived, never declared) ------------
    source_assessments: list[dict[str, Any]] = []
    selected_source_keys: set[tuple[str, str, str]] = set()
    for source in bundle.sources:
        in_scope = (source.provider, source.model) in selected or bool(
            FX_PAIR_PATTERN.fullmatch(source.model)
        )
        assessment = _classify_source(source, now=now, policy=policy, add=add)
        source_assessments.append(assessment)
        if in_scope:
            selected_source_keys.add((source.provider, source.model, source.source_kind))

    # --- 180-c: bounded deterministic evidence parsing (trust is parsed,
    # never declared). Digest-verified bytes are parsed with the registered
    # parser; derived observations are the only things that may bind
    # proposed facts. A matching hash of arbitrary bytes is not content
    # trust: empty, unrelated, or contradictory bytes fail the gate. ------
    assessment_by_key: dict[str, dict[str, Any]] = {}
    parse_results: dict[str, se.SnapshotParse] = {}
    fx_quotes: list[tuple[str, se.ParsedFxQuote]] = []
    all_observations: list[se.Observation] = []
    source_digests: dict[str, str] = {}
    official_source_keys: set[str] = set()
    semantic_source_keys: set[str] = set()
    for source, assessment in zip(bundle.sources, source_assessments):
        key = f"{source.provider}|{source.model}|{source.source_kind}"
        assessment_by_key[key] = assessment
        assessment["parser"] = se.PARSER_IDS.get((source.provider, source.source_kind), "")
        if source.source_kind == "operator_input" or source.extraction == "semantic":
            semantic_source_keys.add(key)
        if source.truncated or source.evidence_b64 is None:
            assessment["parse_state"] = "truncated" if source.truncated else "no_evidence"
            assessment["parsed_models"] = 0
            assessment["parsed_fx_quotes"] = 0
            continue
        if assessment["evidence_state"] != EVIDENCE_OK:
            assessment["parse_state"] = "evidence_invalid"
            assessment["parsed_models"] = 0
            assessment["parsed_fx_quotes"] = 0
            continue
        evidence_bytes = base64.b64decode(source.evidence_b64, validate=True)
        parsed = se.parse_snapshot(source.provider, source.source_kind, evidence_bytes)
        parse_results[key] = parsed
        if parsed.ok:
            source_digests[key] = source.content_sha256
            all_observations.extend(se.derive_observations(key, parsed))
            for quote in parsed.fx_quotes:
                fx_quotes.append((key, quote))
            if assessment["classification"] == SOURCE_OFFICIAL:
                official_source_keys.add(key)
        elif source.extraction == "deterministic" and se.has_deterministic_parser(
            source.provider, source.source_kind
        ):
            # Registered deterministic parser, digest-verified bytes, and the
            # parse still failed: the bytes are not the claimed content.
            detail = f"required source failed deterministic parsing ({parsed.error})" if source.required else (
                "optional source failed deterministic parsing (" + str(parsed.error) + ")"
            )
            if source.required:
                add(SEVERITY_BLOCKER, "source_evidence_parse_failed", detail, source.provider, source.model)
                assessment["classification"] = SOURCE_BLOCKED
            else:
                add(SEVERITY_REVIEW, "source_evidence_parse_failed", detail, source.provider, source.model)
                assessment["classification"] = SOURCE_REVIEW
        assessment["parse_state"] = "ok" if parsed.ok else (parsed.error or "no_registered_parser")
        assessment["parsed_models"] = len(parsed.models)
        assessment["parsed_fx_quotes"] = len(parsed.fx_quotes)
        if parsed.ok:
            id_counts: dict[str, int] = {}
            for parsed_model in parsed.models:
                id_counts[parsed_model.model] = id_counts.get(parsed_model.model, 0) + 1
            for duplicate_id in sorted(model_id for model_id, count in id_counts.items() if count > 1):
                add(
                    SEVERITY_REVIEW,
                    "source_duplicate_model_id",
                    f"source {key} parses {id_counts[duplicate_id]} rows for model {duplicate_id}; duplicate IDs are not independent evidence",
                    source.provider,
                    duplicate_id,
                )

    # Verified native -> EUR rates from the bundle's own FX facts (the same
    # strict active selection the FX gate uses; a rate that cannot be
    # resolved deterministically is never invented).
    fx_to_eur_candidates: dict[str, set[Decimal]] = {}
    for facts in bundle.fx:
        active, ambiguous = _select_active_fx(
            [f for f in bundle.fx if f.base_currency == facts.base_currency and f.quote_currency == facts.quote_currency],
            now,
        )
        if ambiguous or active is None:
            continue
        rate = Decimal(active.rate)
        if active.quote_currency == "EUR":
            fx_to_eur_candidates.setdefault(active.base_currency, set()).add(rate)
        elif active.base_currency == "EUR" and rate > 0:
            derived = _reciprocal(rate)
            if derived > 0:
                fx_to_eur_candidates.setdefault(active.quote_currency, set()).add(derived)
    fx_to_eur: dict[str, Decimal] = {
        currency: next(iter(rates))
        for currency, rates in fx_to_eur_candidates.items()
        if len(rates) == 1
    }

    # --- per-selected-model dispositions ----------------------------------
    dispositions: list[Disposition] = []
    price_comparisons: list[PriceComparison] = []
    per_provider: dict[str, dict[str, int]] = {}
    unsupported_excluded: list[str] = []
    missing_required_dimensions: list[str] = []
    route_artifact_rows: list[RouteFacts] = []
    pricing_artifact_rows: list[Any] = []
    upstream_by_key: dict[tuple[str, str], str] = {}
    excluded_route_mutations = 0
    excluded_pricing_mutations = 0

    def bump(provider: str, key: str) -> None:
        per_provider.setdefault(provider, {})
        per_provider[provider][key] = per_provider[provider].get(key, 0) + 1

    _DIMENSION_ATTRIBUTE = {
        "input": "input_price_per_1m",
        "cached_input": "cached_input_price_per_1m",
        "output": "output_price_per_1m",
        "reasoning": "reasoning_price_per_1m",
        "request": "request_price",
    }

    for provider, model in sorted(selected):
        facts = models_by_key.get((provider, model))
        routes = routes_by_key.get((provider, model), [])
        pricing_facts_list = pricing_by_key.get((provider, model), [])
        model_sources = sources_by_key.get((provider, model), [])
        truncated_required = any(source.truncated for source in model_sources if source.required)
        in_baseline = any(
            identity[:2] == (provider, model) for identity in baseline_routes_by_identity
        ) or any(p == provider and m == model for (p, m, _endpoint) in baseline_pricing_by_key)

        # --- contradictions across independently represented observations
        if facts is not None or routes or pricing_facts_list:
            primary_route = sorted(routes, key=lambda r: (r.match_type, r.upstream_model))[0] if routes else None
            primary_pricing = sorted(pricing_facts_list, key=lambda p: p.currency)[0] if pricing_facts_list else None
            observations = _fact_observations(facts, primary_route, primary_pricing)
            for field_name in sorted(observations):
                distinct = {value for _, value in observations[field_name]}
                if len(distinct) > 1:
                    add(
                        SEVERITY_BLOCKER,
                        "source_contradiction",
                        f"sources disagree on {field_name}: " + ", ".join(sorted(distinct)[:4]),
                        provider,
                        model,
                    )
                    break

        if facts is None and not routes and not pricing_facts_list:
            explicitly_selected = model in bundle.selection.model_include
            if in_baseline:
                if truncated_required:
                    if explicitly_selected:
                        add(
                            SEVERITY_BLOCKER,
                            "explicitly_selected_not_refetched",
                            "explicitly selected baseline model was not re-fetched (source missing or truncated); baseline row retained, no delete",
                            provider,
                            model,
                        )
                        dispositions.append(Disposition(provider, model, DISPOSITION_BLOCKED, "explicitly selected baseline model not re-fetched; retain-local"))
                        bump(provider, "blocked")
                    else:
                        dispositions.append(Disposition(provider, model, DISPOSITION_NOT_FETCHED, "baseline model not re-fetched (source missing or truncated); not treated as disappeared"))
                        bump(provider, "not_fetched")
                else:
                    dispositions.append(Disposition(provider, model, DISPOSITION_DISAPPEARED, "in baseline but absent from complete sources; retain-local, no delete semantics in this version"))
                    bump(provider, "disappeared")
                    add(SEVERITY_REVIEW, "model_disappeared", "model present in baseline but absent from complete source retrieval; retained locally", provider, model)
            else:
                # explicitly selected but nothing proposed
                if explicitly_selected:
                    add(SEVERITY_BLOCKER, "missing_required_selection", "explicitly selected model has no facts, routes, or pricing", provider, model)
                    dispositions.append(Disposition(provider, model, DISPOSITION_BLOCKED, "explicitly selected model missing from bundle"))
                    bump(provider, "blocked")
                else:
                    dispositions.append(Disposition(provider, model, DISPOSITION_NOT_FETCHED, "no facts proposed for this selected model"))
                    bump(provider, "not_fetched")
            continue

        # A truncated required source blocks the affected required plan when
        # the model otherwise carries proposal facts.
        if truncated_required:
            dispositions.append(Disposition(provider, model, DISPOSITION_BLOCKED, "required source truncated; import plan blocked"))
            bump(provider, "blocked")
            continue

        if facts is not None and facts.deprecated:
            dispositions.append(Disposition(provider, model, DISPOSITION_DEPRECATED, "source marks model deprecated; retain-local, no delete semantics in this version"))
            bump(provider, "deprecated")
            add(SEVERITY_REVIEW, "model_deprecated", "model marked deprecated by source", provider, model)
            continue

        # capability widening rejection (standard v1 profile)
        capabilities = dict(facts.capabilities if facts is not None else {})
        for route in routes:
            capabilities.update(route.capabilities)
        unsupported = [key for key in capabilities if key not in CAPABILITY_KEYS]
        if unsupported:
            unsupported_excluded.append(f"{provider}/{model}:{','.join(sorted(unsupported))}")
            add(SEVERITY_REVIEW, "unsupported_capability_excluded", f"capability outside standard v1 profile: {','.join(sorted(unsupported))}", provider, model)
            dispositions.append(Disposition(provider, model, DISPOSITION_EXCLUDED, f"unsupported capability: {','.join(sorted(unsupported))}"))
            bump(provider, "excluded")
            continue

        # route facts required for any priced or fact-bearing model
        if not routes:
            add(SEVERITY_BLOCKER, "missing_route", "selected model has facts or pricing but no route proposal", provider, model)
            dispositions.append(Disposition(provider, model, DISPOSITION_BLOCKED, "no route proposal"))
            bump(provider, "blocked")
            continue

        # pricing required for selected chat text models
        if not pricing_facts_list:
            add(SEVERITY_BLOCKER, "missing_pricing", "selected model has a route but no pricing proposal", provider, model)
            dispositions.append(Disposition(provider, model, DISPOSITION_BLOCKED, "no pricing proposal"))
            bump(provider, "blocked")
            continue

        # --- pairing by provider + UPSTREAM model + endpoint ----------------
        # Public aliases need not equal upstream IDs: the pricing fact is
        # paired with the route it belongs to, and the executable pricing row
        # must carry the route's upstream model.
        primary_route = sorted(routes, key=lambda r: (r.match_type, r.upstream_model))[0]
        upstream = primary_route.upstream_model
        upstreams = {route.upstream_model for route in routes}
        pricing_key = (provider, model)
        if len(upstreams) > 1:
            add(SEVERITY_BLOCKER, "route_upstream_contradiction", f"routes for this model forward to conflicting upstream models: {', '.join(sorted(upstreams))}", provider, model)
            dispositions.append(Disposition(provider, model, DISPOSITION_BLOCKED, "conflicting upstream models across route forms"))
            bump(provider, "blocked")
            continue
        pricing_facts = sorted(pricing_facts_list, key=lambda p: p.currency)[0]
        if len(pricing_facts_list) > 1:
            add(
                SEVERITY_BLOCKER,
                "pricing_currency_contradiction",
                f"multiple pricing facts for this model in currencies: {', '.join(sorted(p.currency for p in pricing_facts_list))}",
                provider,
                model,
            )
            dispositions.append(Disposition(provider, model, DISPOSITION_BLOCKED, "conflicting pricing currencies"))
            bump(provider, "blocked")
            continue
        upstream_by_key[pricing_key] = upstream

        # --- 180-c: bind proposed facts to parsed snapshot observations ---
        # Only OFFICIAL-source observations (approved publisher/kind/parser/
        # host, digest-verified bytes, successful deterministic parse) can
        # verify a fact. Operator/semantic provenance keeps a fact in REVIEW
        # only; unapproved observations establish nothing.
        fact_sources = {
            source_ref
            for facts_ in (facts, primary_route, pricing_facts)
            if facts_ is not None
            for source_ref in facts_.provenance.sources
        }
        semantic_provenance = any(key in semantic_source_keys for key in fact_sources)
        proposed: dict[str, Any] = {}
        for dimension in pricing_facts.dimensions:
            proposed[f"pricing:{dimension.name}"] = {
                "value": dimension.value,
                "currency": dimension.currency,
                "required": dimension.name in ("input", "output"),
            }
        if facts is not None:
            if facts.context_length is not None:
                proposed["model:context_length"] = facts.context_length
            if facts.max_output_tokens is not None:
                proposed["model:max_output_tokens"] = facts.max_output_tokens
            if facts.deprecated:
                proposed["model:deprecated"] = True
            if facts.capabilities.get("text"):
                proposed["model:capability:text"] = True
        evidence_findings, backed_facts, _unresolved_fields, missing_fx = se.reconcile_model_facts(
            provider=provider,
            model=model,
            upstream_model=upstream,
            proposed=proposed,
            observations=tuple(all_observations),
            official_source_keys=frozenset(official_source_keys),
            semantic_provenance=semantic_provenance,
            fx_to_eur=fx_to_eur,
            digests=source_digests,
        )
        for finding in evidence_findings:
            add(finding.severity, finding.code, finding.detail, finding.provider, finding.model)
        for backed_field in sorted(backed_facts):
            backed_fact = backed_facts[backed_field]
            evidence_backed_facts.append(
                {
                    "provider": provider,
                    "model": model,
                    "field": backed_fact.field,
                    "proposed": backed_fact.proposed,
                    "backed_by": list(backed_fact.backed_by),
                    "independent_sources": backed_fact.independent_sources,
                    "semantic_only": backed_fact.semantic_only,
                }
            )
        if missing_fx:
            add(
                SEVERITY_BLOCKER,
                "fx_evidence_unbound",
                f"no verified {', '.join(sorted(missing_fx))} to EUR FX rate; price facts cannot be bound to snapshot evidence",
                provider,
                model,
            )
        model_names = {model, upstream}
        complete_keys = [
            key
            for key in fact_sources
            if parse_results.get(key) is not None and parse_results[key].ok
        ]
        model_missing = bool(
            complete_keys
            and not any(
                parsed_model.model in model_names
                for key in complete_keys
                for parsed_model in parse_results[key].models
            )
        )
        if model_missing:
            add(
                SEVERITY_BLOCKER,
                "source_evidence_model_missing",
                f"selected model is absent from the complete parsed snapshots of its {len(complete_keys)} source(s)",
                provider,
                model,
            )
        if any(finding.severity == SEVERITY_BLOCKER for finding in evidence_findings) or missing_fx or model_missing:
            blocked_codes = sorted(
                {finding.code for finding in evidence_findings if finding.severity == SEVERITY_BLOCKER}
                | ({"fx_evidence_unbound"} if missing_fx else set())
                | ({"source_evidence_model_missing"} if model_missing else set())
            )
            dispositions.append(
                Disposition(provider, model, DISPOSITION_BLOCKED, "source evidence: " + ", ".join(blocked_codes))
            )
            bump(provider, "blocked")
            continue

        # --- baseline comparison (strict active selection, no fallback) ----
        old_rows = baseline_pricing_by_key.get((provider, upstream, primary_route.endpoint), []) if baseline else []
        old_pricing, pricing_ambiguous = _select_active_pricing(old_rows, now)
        if pricing_ambiguous:
            add(SEVERITY_BLOCKER, "baseline_ambiguous_rows", "overlapping active baseline pricing rows with different values; no before-value is invented", provider, model)
        old_route_rows = [
            baseline_routes_by_identity.get((provider, model, route.match_type, route.endpoint), [None])[0]
            for route in routes
        ]

        # --- price dimension comparisons (currency compared first) ---------
        old_currency: str | None = None
        old_dims: dict[str, Decimal] = {}
        if old_pricing is not None:
            old_currency = old_pricing.currency
            old_dims = {
                name: Decimal(value)
                for name, value in (
                    ("input", old_pricing.input_price_per_1m),
                    ("cached_input", old_pricing.cached_input_price_per_1m),
                    ("output", old_pricing.output_price_per_1m),
                    ("reasoning", old_pricing.reasoning_price_per_1m),
                    ("request", old_pricing.request_price),
                )
                if value is not None
            }
        currency_conflict = old_pricing is not None and old_currency != pricing_facts.currency
        if currency_conflict:
            add(
                SEVERITY_BLOCKER,
                "currency_inconsistency",
                f"baseline {old_currency} vs proposed {pricing_facts.currency}",
                provider,
                model,
            )

        changed_fields: list[str] = []
        # route identity comparisons
        route_changed = False
        for route, old_route in zip(routes, old_route_rows):
            if old_route is None:
                continue
            for attr in ("upstream_model", "priority", "enabled", "visible_in_models", "supports_streaming", "match_type"):
                new_value = getattr(route, attr)
                old_value = getattr(old_route, attr)
                if isinstance(new_value, bool):
                    old_value = bool(old_value)
                if new_value != old_value:
                    route_changed = True
                    changed_fields.append(f"route.{attr}")
            if (route.capabilities or {}) != (old_route.capabilities or {}):
                route_changed = True
                changed_fields.append("route.capabilities")

        price_changed = False
        dimension_states: dict[str, str] = {}
        for dimension in pricing_facts.dimensions:
            new_value = None if dimension.value is None else Decimal(dimension.value)
            if currency_conflict:
                old_any_value = None
                if old_pricing is not None:
                    raw = getattr(old_pricing, _DIMENSION_ATTRIBUTE[dimension.name])
                    old_any_value = None if raw is None else str(raw)
                price_comparisons.append(
                    PriceComparison(
                        provider=provider,
                        model=model,
                        dimension=dimension.name,
                        old=old_any_value,
                        new=None if new_value is None else str(new_value),
                        currency_old=old_currency,
                        currency_new=dimension.currency,
                        percent_change=None,
                        state="CURRENCY_MISMATCH",
                    )
                )
                continue
            old_entry = old_dims.get(dimension.name)
            comparison_state = "UNCHANGED"
            percent = None
            if old_entry is None:
                if new_value is not None:
                    comparison_state = "NEW"
            elif new_value is None:
                comparison_state = "REMOVED"
            else:
                if old_entry == 0 and new_value > 0 or old_entry > 0 and new_value == 0:
                    comparison_state = "ZERO_TRANSITION"
                    add(SEVERITY_REVIEW, "price_zero_transition", f"{dimension.name} crossed zero (old={old_entry}, new={new_value})", provider, model)
                elif old_entry != 0:
                    percent = _pct(old_entry, new_value)
                    if abs(Decimal(percent)) > policy.price_change_review:
                        comparison_state = "CHANGED_REVIEW"
                        add(SEVERITY_REVIEW, "price_moved_review", f"{dimension.name} moved {percent} (policy {policy.price_change_review})", provider, model)
                    else:
                        comparison_state = "CHANGED" if old_entry != new_value else "UNCHANGED"
                if comparison_state in ("CHANGED", "CHANGED_REVIEW", "ZERO_TRANSITION", "NEW", "REMOVED"):
                    changed_fields.append(f"pricing.{dimension.name}")
            dimension_states[dimension.name] = comparison_state
            price_comparisons.append(
                PriceComparison(
                    provider=provider,
                    model=model,
                    dimension=dimension.name,
                    old=None if old_entry is None else str(old_entry),
                    new=None if new_value is None else str(new_value),
                    currency_old=old_currency if old_entry is not None else None,
                    currency_new=dimension.currency,
                    percent_change=percent,
                    state=comparison_state,
                )
            )
        if currency_conflict:
            price_changed = True
        # NEW/REMOVED dimensions are mutations only against an existing
        # baseline row; on a genuine create (no baseline row) there is no
        # before-value to mutate, so the create stays NEW, not CHANGED.
        elif old_rows and any(
            state in ("CHANGED", "CHANGED_REVIEW", "ZERO_TRANSITION", "NEW", "REMOVED")
            for state in dimension_states.values()
        ):
            price_changed = True

        dimension_blocked = False
        for required in ("input", "output"):
            if all(dimension.value is None for dimension in pricing_facts.dimensions if dimension.name == required):
                dimension_blocked = True
                missing_required_dimensions.append(f"{provider}/{model}:{required}")
                add(SEVERITY_BLOCKER, "missing_required_dimension", f"required {required} price is missing", provider, model)

        # --- route / pricing state vs baseline (create | no-op | mutation) --
        route_new = all(old is None for old in old_route_rows)
        pricing_no_baseline = not old_rows

        if dimension_blocked or currency_conflict or pricing_ambiguous:
            disposition = DISPOSITION_BLOCKED
            disposition_detail = "blocked: " + "; ".join(sorted(set(changed_fields + ["required pricing dimension(s) missing" if dimension_blocked else ""] + ["currency inconsistency" if currency_conflict else ""] + ["ambiguous baseline rows" if pricing_ambiguous else ""])))
        elif route_changed or price_changed:
            disposition = DISPOSITION_CHANGED
            disposition_detail = "; ".join(sorted(set(changed_fields)))
            excluded_route_mutations += 1 if route_changed else 0
            excluded_pricing_mutations += 1 if price_changed else 0
        elif route_new or pricing_no_baseline:
            disposition = DISPOSITION_NEW
            parts = []
            if route_new:
                parts.append("new route")
            if pricing_no_baseline:
                parts.append("new pricing")
            disposition_detail = " + ".join(parts) + " (create-only)"
            # executable artifacts: only the genuinely new rows
            if route_new:
                route_artifact_rows.extend(
                    route for route, old in zip(routes, old_route_rows) if old is None
                )
            if pricing_no_baseline and not dimension_blocked:
                pricing_artifact_rows.append(pricing_facts)
        else:
            disposition = DISPOSITION_UNCHANGED
            disposition_detail = "all compared fields identical to the active baseline (no-op)"
        bump(provider, disposition.lower())
        if disposition == DISPOSITION_CHANGED:
            per_provider.setdefault(provider, {})["mutations"] = per_provider.get(provider, {}).get("mutations", 0) + 1
        dispositions.append(Disposition(provider, model, disposition, disposition_detail))

    # disappeared/deprecated models tracked separately from fetched records
    considered_keys = {
        (item.provider, getattr(item, "model", None) or item.requested_model)
        for item in (*bundle.models, *bundle.pricing, *bundle.routes)
        if (item.provider, getattr(item, "model", None) or item.requested_model) in selected
    }
    for provider, model in sorted(selected):
        if (provider, model) not in considered_keys and (provider, model) not in {
            (d.provider, d.model) for d in dispositions if d.disposition in (DISPOSITION_DISAPPEARED, DISPOSITION_DEPRECATED, DISPOSITION_NOT_FETCHED, DISPOSITION_BLOCKED)
        }:
            dispositions.append(Disposition(provider, model, DISPOSITION_NOT_FETCHED, "no bundle facts and no baseline presence"))
            per_provider.setdefault(provider, {})
            per_provider[provider]["not_fetched"] = per_provider[provider].get("not_fetched", 0) + 1

    # --- counts (recomputed; considered is independent of the sum) ---------
    disposition_counts: dict[str, int] = {}
    for item in dispositions:
        disposition_counts[item.disposition] = disposition_counts.get(item.disposition, 0) + 1
    new_count = disposition_counts.get(DISPOSITION_NEW, 0)
    changed_count = disposition_counts.get(DISPOSITION_CHANGED, 0)
    unchanged_count = disposition_counts.get(DISPOSITION_UNCHANGED, 0)
    excluded_count = disposition_counts.get(DISPOSITION_EXCLUDED, 0)
    blocked_count = disposition_counts.get(DISPOSITION_BLOCKED, 0)
    ready_count = new_count + unchanged_count  # changed rows are NOT ready: they need unsupported updates
    considered_count = len(selected)
    counted = (
        ready_count
        + changed_count
        + excluded_count
        + blocked_count
        + disposition_counts.get(DISPOSITION_DISAPPEARED, 0)
        + disposition_counts.get(DISPOSITION_DEPRECATED, 0)
        + disposition_counts.get(DISPOSITION_NOT_FETCHED, 0)
    )
    if counted != considered_count:
        raise CatalogRefreshBlockedError(
            "count_identity_violation",
            f"dispositions ({counted}) do not cover every selected model ({considered_count})",
        )
    counts = {
        "selected": len(selected),
        "out_of_scope_facts": out_of_scope,
        "considered": considered_count,
        "ready": ready_count,
        "new": new_count,
        "changed": changed_count,
        "unchanged": unchanged_count,
        "excluded": excluded_count,
        "blocked": blocked_count,
        "disappeared": disposition_counts.get(DISPOSITION_DISAPPEARED, 0),
        "deprecated": disposition_counts.get(DISPOSITION_DEPRECATED, 0),
        "not_fetched": disposition_counts.get(DISPOSITION_NOT_FETCHED, 0),
    }

    # --- artifacts via the real import parsers ----------------------------
    route_tsv = generate_route_tsv(bundle, route_artifact_rows)
    pricing_tsv = generate_pricing_tsv(bundle, pricing_artifact_rows, upstream_by_key)

    # --- FX (canonical native -> EUR direction) ----------------------------
    fx_required_currencies = {
        item.currency for item in bundle.pricing if (item.provider, item.model) in selected
    } - {"EUR"}
    fx_rows, fx_gate, fx_comparisons = _run_fx_gate(
        baseline, bundle, now, fx_required_currencies, policy, add
    )
    fx_json = generate_fx_json(fx_rows)

    # --- 180-c: bind FX facts to parsed ECB reference quotes ---------------
    # An FX fact is verified only when a verified quote from the ECB
    # publisher (own identity, ecb_reference_xml kind) carries the same pair
    # (or its native inverse, reciprocated with the exact Decimal rule the
    # FX gate uses) and the fact's publication date equals the quote date.
    fx_backed: list[dict[str, Any]] = []
    for facts in bundle.fx:
        pair = (facts.base_currency, facts.quote_currency)
        pair_names = {f"{pair[0]}-{pair[1]}", f"{pair[1]}-{pair[0]}"}
        field_quotes = [
            (source_key, quote)
            for source_key, quote in fx_quotes
            if f"{quote.base_currency}-{quote.quote_currency}" in pair_names
        ]
        official_quotes = [
            item for item in field_quotes if item[0] in official_source_keys
        ]
        fact_semantic = any(key in semantic_source_keys for key in facts.provenance.sources)
        if not official_quotes:
            if field_quotes:
                add(
                    SEVERITY_BLOCKER,
                    "source_evidence_unapproved",
                    f"FX fact {pair[0]} to {pair[1]} is backed only by unapproved source quotes",
                    None,
                    None,
                )
            elif fact_semantic:
                add(
                    SEVERITY_REVIEW,
                    "fx_evidence_semantic_only",
                    f"FX fact {pair[0]} to {pair[1]} is operator/semantic input without a verified reference quote",
                    None,
                    None,
                )
            else:
                add(
                    SEVERITY_BLOCKER,
                    "fx_evidence_unbound",
                    f"FX fact {pair[0]} to {pair[1]} has no verified reference quote",
                    None,
                    None,
                )
            continue
        rates = {str(quote.rate) for _key, quote in official_quotes}
        if len(rates) > 1:
            add(
                SEVERITY_BLOCKER,
                "source_observations_contradict",
                f"distinct FX snapshots disagree on {pair[0]}-{pair[1]}: {', '.join(sorted(rates)[:4])}",
                None,
                None,
            )
            continue
        fact_rate = Decimal(facts.rate)
        matched: tuple[str, se.ParsedFxQuote, bool] | None = None
        for source_key, quote in official_quotes:
            same_direction = (
                quote.base_currency,
                quote.quote_currency,
            ) == pair
            if same_direction:
                agrees = abs(quote.rate - fact_rate) <= se.FX_BINDING_TOLERANCE
            else:
                agrees = abs(quote.rate - _reciprocal(fact_rate)) <= se.FX_BINDING_TOLERANCE
            if agrees:
                matched = (source_key, quote, same_direction)
                break
        if matched is None:
            add(
                SEVERITY_BLOCKER,
                "source_evidence_value_mismatch",
                f"FX rate {facts.rate} does not match any verified {pair[0]}/{pair[1]} reference quote or its reciprocal",
                None,
                None,
            )
            continue
        source_key, quote, same_direction = matched
        if facts.published_at is None:
            add(
                SEVERITY_BLOCKER,
                "fx_evidence_date_mismatch",
                f"FX fact {pair[0]} to {pair[1]} carries no publication date; the verified quote is dated {quote.published_date.isoformat()}",
                None,
                None,
            )
            continue
        if facts.published_at.date() != quote.published_date:
            add(
                SEVERITY_BLOCKER,
                "fx_evidence_date_mismatch",
                f"FX fact publication date {facts.published_at.date().isoformat()} does not match the verified quote date {quote.published_date.isoformat()}",
                None,
                None,
            )
            continue
        fx_backed.append(
            {
                "pair": f"{pair[0]} to {pair[1]}",
                "rate": facts.rate,
                "backed_by": source_key,
                "observed_quote": str(quote.rate),
                "derived_reciprocal": not same_direction,
                "quote_date": quote.published_date.isoformat(),
            }
        )

    route_gate = _run_route_gate(bundle, baseline, route_tsv, excluded_route_mutations, baseline is not None)
    pricing_gate = _run_pricing_gate(baseline, pricing_tsv, excluded_pricing_mutations, baseline is not None)

    # pairing gate: a pricing identity that matches neither the route public
    # name nor its upstream model is selected under its own (provider, model)
    # key and fails closed there as missing route (phantom pricing identity)
    # plus missing pricing for the real route, so pairing evidence reflects
    # those first-class blockers.
    pairing_findings = [w for w in warnings if w.code in ("missing_route", "missing_pricing")]
    if pairing_findings:
        pairing_evidence = EVIDENCE_BLOCKED
        pairing_detail = (f"{len(pairing_findings)} route/pricing pairing blocker(s): "
                          + ", ".join(sorted({w.code for w in pairing_findings})))
    else:
        pairing_evidence = EVIDENCE_VERIFIED
        pairing_detail = "every priced selected model is paired to its route by provider + upstream model + endpoint"

    # unsupported aggregated gate
    if unsupported_excluded:
        unsupported_detail = "; ".join(unsupported_excluded[:16])
        if any(d.disposition == DISPOSITION_BLOCKED for d in dispositions):
            unsupported_evidence = EVIDENCE_BLOCKED
        else:
            unsupported_evidence = EVIDENCE_REVIEW
    else:
        unsupported_detail = "no unsupported rows"
        unsupported_evidence = EVIDENCE_VERIFIED

    # inventory: derived independently from the parsed snapshots, then
    # reconciled against the selection (considered is len(selected); the
    # inventory is a separate projection, never a re-derivation of it).
    evidence_models_by_provider: dict[str, set[str]] = {}
    for key, parsed in parse_results.items():
        if not parsed.ok:
            continue
        for parsed_model in parsed.models:
            evidence_models_by_provider.setdefault(parsed_model.provider, set()).add(parsed_model.model)
    selected_by_provider: dict[str, set[str]] = {}
    for provider, model in selected:
        selected_by_provider.setdefault(provider, set()).add(model)
    upstream_by_provider: dict[str, set[str]] = {}
    for route in bundle.routes:
        if (route.provider, route.requested_model) in selected:
            upstream_by_provider.setdefault(route.provider, set()).add(route.upstream_model)
    inventory: dict[str, dict[str, int]] = {}
    for provider in sorted(set(evidence_models_by_provider) | set(selected_by_provider)):
        evidence = evidence_models_by_provider.get(provider, set())
        accounted = selected_by_provider.get(provider, set()) | upstream_by_provider.get(provider, set())
        inventory[provider] = {
            "evidence_models": len(evidence),
            "selected_models": len(selected_by_provider.get(provider, set())),
            "unproposed_candidates": len(evidence - accounted),
        }
    source_evidence_report: dict[str, Any] = {
        "scope": "offline_replay",
        "note": (
            "supplied/cached snapshot bytes were parsed offline with registered "
            "deterministic parsers; this proves extraction consistency against "
            "the supplied bytes, not a live retrieval that never occurred"
        ),
        "backed_facts": sorted(
            evidence_backed_facts,
            key=lambda item: (item["provider"], item["model"], item["field"]),
        ),
        "fx_backed": sorted(fx_backed, key=lambda item: item["pair"]),
        "inventory": {
            provider: dict(sorted(values.items()))
            for provider, values in sorted(inventory.items())
        },
    }

    # sources gate
    if any(a["classification"] == SOURCE_BLOCKED for a in source_assessments):
        sources_evidence = EVIDENCE_BLOCKED
        sources_detail = f"{sum(1 for a in source_assessments if a['classification'] == SOURCE_BLOCKED)} source(s) failed provenance or deterministic parsing rules"
    elif any(a["classification"] == SOURCE_REVIEW or a["age_state"] != "fresh" for a in source_assessments):
        sources_evidence = EVIDENCE_REVIEW
        sources_detail = "all required sources present; some sources are REVIEW-classified, aged, or not deterministically parseable"
    else:
        sources_evidence = EVIDENCE_VERIFIED
        sources_detail = (
            "all sources fresh, official-host, evidence-verified, and deterministically "
            "parsed; proposed required facts are bound to parsed snapshot observations"
        )

    # pricing completeness gate
    if missing_required_dimensions:
        pricing_complete_evidence = EVIDENCE_BLOCKED
        pricing_complete_detail = "missing required dimensions: " + "; ".join(missing_required_dimensions[:8])
    else:
        pricing_complete_evidence = EVIDENCE_VERIFIED
        pricing_complete_detail = "every selected priced model carries required input and output dimensions"

    # unusual-change gate
    change_findings = [w for w in warnings if w.code in ("price_moved_review", "fx_moved_review", "price_zero_transition")]
    if change_findings:
        changes_evidence = EVIDENCE_REVIEW
        changes_detail = f"{len(change_findings)} unusual change finding(s) above policy thresholds"
    else:
        changes_evidence = EVIDENCE_VERIFIED
        changes_detail = "no price/FX movement above policy thresholds"

    gates: list[Gate] = [
        Gate(GATE_SOURCES, sources_evidence, sources_detail),
        Gate(
            GATE_SCHEMA,
            EVIDENCE_VERIFIED,
            "bundle schema v1 parsed strictly; baseline document digest-verified"
            if baseline is not None
            else "bundle schema v1 parsed strictly; explicit first-install baseline",
        ),
        Gate(GATE_PRICING_COMPLETE, pricing_complete_evidence, pricing_complete_detail),
        Gate(GATE_PAIRING, pairing_evidence, pairing_detail),
        Gate(GATE_UNSUPPORTED, unsupported_evidence, unsupported_detail),
        Gate(GATE_CHANGES, changes_evidence, changes_detail),
    ]
    if counts["blocked"]:
        gates.append(Gate(GATE_COMPLETENESS, EVIDENCE_BLOCKED, f"{counts['blocked']} selected models blocked"))
    elif counts["excluded"]:
        gates.append(Gate(GATE_COMPLETENESS, EVIDENCE_REVIEW, f"{counts['excluded']} selected models excluded"))
    else:
        gates.append(Gate(GATE_COMPLETENESS, EVIDENCE_VERIFIED, "all selected models accounted"))
    gates.extend(route_gate.gates)
    gates.extend(pricing_gate.gates)
    gates.extend(fx_gate.gates)
    import_gates = [route_gate.import_gate, pricing_gate.import_gate, fx_gate.import_gate]

    # --- gate failures become first-class findings -------------------------
    for gate in list(gates):
        if gate.evidence == EVIDENCE_BLOCKED:
            warnings.append(Warning(SEVERITY_BLOCKER, f"gate:{gate.name}", None, None, gate.detail))
        elif gate.evidence == EVIDENCE_REVIEW:
            warnings.append(Warning(SEVERITY_REVIEW, f"gate:{gate.name}", None, None, gate.detail))

    # --- overall state ------------------------------------------------------
    blocker_warnings = [warning for warning in warnings if warning.severity == SEVERITY_BLOCKER]
    review_warnings = [warning for warning in warnings if warning.severity == SEVERITY_REVIEW]
    if blocker_warnings:
        state = OVERALL_BLOCKED
        state_reason = "blocked by: " + ", ".join(sorted({warning.code for warning in blocker_warnings}))
    elif review_warnings:
        state = OVERALL_READY_WITH_WARNINGS
        state_reason = f"{len(review_warnings)} review-level finding(s); no blockers"
    else:
        state = OVERALL_READY
        state_reason = "all recomputed gates verified; no review findings"

    baseline_info: dict[str, Any] = {
        "mode": bundle.baseline.mode,
        "exported_at": bundle.baseline.exported_at.isoformat() if bundle.baseline.exported_at else None,
        "sql_checked": bundle.baseline.sql_checked,
        "target": bundle.baseline.target_database,
        "postgres_version": bundle.baseline.postgres_version,
        "age": None,
    }
    if baseline is not None:
        baseline_info["documented_exported_at"] = baseline.exported_at.isoformat()
        baseline_info["age"] = (now - _utc(baseline.exported_at)).total_seconds()

    report = ValidationReport(
        state=state,
        state_reason=state_reason,
        run_id=bundle.run_id,
        generated_at=bundle.generated_at.isoformat(),
        policy_version=policy.version,
        counts=counts,
        per_provider={provider: dict(sorted(values.items())) for provider, values in sorted(per_provider.items())},
        dispositions=dispositions,
        price_comparisons=price_comparisons,
        warnings=warnings,
        gates=gates,
        import_gates=import_gates,
        baseline=baseline_info,
        research={
            "status": bundle.research.status,
            "extractor_version": bundle.research.extractor_version,
            "tool_version": bundle.research.tool_version,
        },
        artifacts={
            "routes_tsv_sha256": hashlib.sha256(route_tsv).hexdigest(),
            "pricing_tsv_sha256": hashlib.sha256(pricing_tsv).hexdigest(),
            "fx_json_sha256": hashlib.sha256(fx_json).hexdigest(),
            "route_rows": route_gate.import_gate.total_rows,
            "pricing_rows": pricing_gate.import_gate.total_rows,
            "fx_rows": fx_gate.import_gate.total_rows,
        },
        sql_checks={
            "checked": bool(baseline is not None and baseline.sql_checked),
            "sql_executed_during_review": bundle.baseline.mode == "db_snapshot",
            "note": (
                "SQL was executed during this review (live read-only db_snapshot export)"
                if bundle.baseline.mode == "db_snapshot"
                else "baseline consumed from a document; SQL was executed historically at that document's export time, not during this review"
            ),
        },
        sources=source_assessments,
        fx_comparisons=fx_comparisons,
        source_evidence=source_evidence_report,
    )
    artifacts = {"routes-proposal.tsv": route_tsv, "pricing-proposal.tsv": pricing_tsv, "fx-proposal.json": fx_json}
    return report, artifacts


class _GateBundle:
    def __init__(self) -> None:
        self.gates: list[Gate] = []
        self.import_gate: ImportGate | None = None


def _baseline_model_providers(baseline: BaselineDocument | None, model: str, providers: set[str]) -> set[str]:
    """Selected providers whose baseline carries the model (route or pricing)."""
    holders: set[str] = set()
    if baseline is None:
        return holders
    for row in baseline.routes:
        if row.requested_model == model and row.provider in providers:
            holders.add(row.provider)
    for row in baseline.pricing:
        if row.upstream_model == model and row.provider in providers:
            holders.add(row.provider)
    return holders


def _provider_refs(bundle: RefreshBundle, baseline: BaselineDocument | None) -> list[RouteImportProviderRef]:
    refs: dict[str, RouteImportProviderRef] = {}
    if baseline is not None:
        for row in baseline.providers:
            refs[row.provider] = RouteImportProviderRef(id=uuid.UUID(row.id), provider=row.provider)
    for provider in sorted({item.provider for item in bundle.routes}):
        if provider not in refs:
            refs[provider] = RouteImportProviderRef(id=uuid.uuid5(uuid.NAMESPACE_URL, f"catalog-refresh:{provider}"), provider=provider)
    return list(refs.values())


def _classification_counts(preview) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in preview.rows:
        counts[row.classification] = counts.get(row.classification, 0) + 1
    return counts


def _run_route_gate(bundle, baseline, tsv_bytes: bytes, excluded_mutations: int, have_baseline: bool) -> _GateBundle:
    """Gate the routes artifact through the real import parser/classifier.

    The artifact carries only create candidates; the classifier's own
    verdict is the truth. Any non-create verdict on an artifact row is an
    internal inconsistency (artifact leak) and blocks the gate.
    """
    result = _GateBundle()
    text_payload = tsv_bytes.decode("utf-8")
    try:
        rows = parse_route_import_tsv(text_payload)
        schema_valid = True
        schema_error = ""
    except ValueError as exc:
        rows = []
        schema_valid = False
        schema_error = str(exc)
    if not schema_valid:
        result.gates.append(Gate(ROUTE_GATE, EVIDENCE_BLOCKED, f"route TSV failed to parse: {schema_error}"))
        result.import_gate = ImportGate("routes", False, 0, 0, 0, {}, 0, 0, schema_error, excluded_mutations)
        return result
    refs = _provider_refs(bundle, baseline)
    preview = validate_route_import_rows(rows, provider_configs=refs, max_rows=max(len(rows), 1))
    existing_by_row: dict[int, list[Any]] = {}
    if have_baseline:
        for row in preview.rows:
            if row.status != "valid":
                continue
            existing_by_row[row.row_number] = [
                baseline_route
                for baseline_route in baseline.routes
                if baseline_route.provider == row.provider and baseline_route.requested_model == row.requested_model
            ]
    classified = classify_route_import_preview(preview, existing_routes_by_row=existing_by_row)
    plan = build_route_import_execution_plan(classified)
    invalid = [row for row in classified.rows if row.status != "valid"]
    non_create = [row for row in classified.rows if row.status == "valid" and row.classification != "create"]
    if invalid:
        result.gates.append(Gate(ROUTE_GATE, EVIDENCE_BLOCKED, f"{len(invalid)} route rows invalid: {invalid[0].errors[0][:200]}"))
    elif non_create:
        result.gates.append(Gate(ROUTE_GATE, EVIDENCE_BLOCKED, f"executable artifact leaked {len(non_create)} non-create row(s): {non_create[0].classification}"))
    elif excluded_mutations:
        result.gates.append(Gate(ROUTE_GATE, EVIDENCE_BLOCKED, f"{excluded_mutations} proposed route update(s) excluded — no apply operation exists in this version"))
    elif rows:
        result.gates.append(Gate(ROUTE_GATE, EVIDENCE_VERIFIED, f"create-only plan executable ({len(rows)} new route row(s))"))
    else:
        result.gates.append(Gate(ROUTE_GATE, EVIDENCE_NA, "no route rows proposed (NO CHANGES)"))
    result.import_gate = ImportGate(
        "routes",
        schema_valid,
        len(rows),
        classified.valid_count,
        classified.invalid_count,
        _classification_counts(classified),
        plan.executable_count,
        plan.blocked_count,
        f"{len(rows)} rows, {len(invalid)} invalid, {len(non_create)} non-create, {excluded_mutations} update(s) excluded",
        excluded_mutations,
    )
    return result


def _run_pricing_gate(baseline, tsv_bytes: bytes, excluded_mutations: int, have_baseline: bool) -> _GateBundle:
    result = _GateBundle()
    text_payload = tsv_bytes.decode("utf-8")
    try:
        rows = parse_pricing_import_tsv(text_payload)
        schema_valid = True
        schema_error = ""
    except ValueError as exc:
        rows = []
        schema_valid = False
        schema_error = str(exc)
    if not schema_valid:
        result.gates.append(Gate(PRICING_GATE, EVIDENCE_BLOCKED, f"pricing TSV failed to parse: {schema_error}"))
        result.import_gate = ImportGate("pricing", False, 0, 0, 0, {}, 0, 0, schema_error, excluded_mutations)
        return result
    preview = validate_pricing_import_rows(rows, max_rows=max(len(rows), 1))
    existing_by_row: dict[int, list[Any]] = {}
    if have_baseline:
        for row in preview.rows:
            if row.status != "valid":
                continue
            existing_by_row[row.row_number] = [
                baseline_rule
                for baseline_rule in baseline.pricing
                if baseline_rule.provider == row.provider
                and baseline_rule.upstream_model == row.model
                and baseline_rule.endpoint == row.endpoint
            ]
    classified = classify_pricing_import_preview(preview, existing_rules_by_row=existing_by_row)
    plan = build_pricing_import_execution_plan(classified)
    invalid = [row for row in classified.rows if row.status != "valid"]
    non_create = [row for row in classified.rows if row.status == "valid" and row.classification != "create"]
    if invalid:
        result.gates.append(Gate(PRICING_GATE, EVIDENCE_BLOCKED, f"{len(invalid)} pricing rows invalid: {invalid[0].errors[0][:200]}"))
    elif non_create:
        result.gates.append(Gate(PRICING_GATE, EVIDENCE_BLOCKED, f"executable artifact leaked {len(non_create)} non-create row(s): {non_create[0].classification}"))
    elif excluded_mutations:
        result.gates.append(Gate(PRICING_GATE, EVIDENCE_BLOCKED, f"{excluded_mutations} proposed pricing update(s) excluded — no apply operation exists in this version"))
    elif rows:
        result.gates.append(Gate(PRICING_GATE, EVIDENCE_VERIFIED, f"create-only plan executable ({len(rows)} new pricing row(s))"))
    else:
        result.gates.append(Gate(PRICING_GATE, EVIDENCE_NA, "no pricing rows proposed (NO CHANGES)"))
    result.import_gate = ImportGate(
        "pricing",
        schema_valid,
        len(rows),
        classified.valid_count,
        classified.invalid_count,
        _classification_counts(classified),
        plan.executable_count,
        plan.blocked_count,
        f"{len(rows)} rows, {len(invalid)} invalid, {len(non_create)} non-create, {excluded_mutations} update(s) excluded",
        excluded_mutations,
    )
    return result


def _run_fx_gate(baseline, bundle, now, required_currencies, policy, add):
    """Canonical native -> EUR FX gate.

    - Required pair per non-EUR pricing currency C is C -> EUR (the exact
      pair the runtime's convert_to_eur looks up).
    - A supplied EUR -> C quotation is reciprocated deterministically
      (Decimal, 9-decimal precision) and recorded as derived — never
      silently relabeled. Direct and reciprocal facts for the same pair
      must agree within the 1e-8 tolerance or the run blocks.
    - Only executable create rows (per the real FX import classifier) are
      emitted; existing-window conflicts are excluded mutations.
    Returns (artifact_rows, gate_bundle, comparisons).
    """
    result = _GateBundle()
    comparisons: list[dict[str, Any]] = []
    if not required_currencies and not bundle.fx:
        result.gates.append(Gate(FX_GATE, EVIDENCE_NA, "all selected prices are EUR; FX is N/A"))
        result.import_gate = ImportGate("fx", True, 0, 0, 0, {}, 0, 0, "N/A: every selected price is EUR")
        return [], result, comparisons

    # FX provenance references must be FX-specific (currency-pair model part,
    # operator_input/docs_page kind) — a model's source reference may never
    # be borrowed to satisfy an FX fact.
    fx_blocker_codes: set[str] = set()

    def fx_add(severity: str, code: str, detail: str) -> None:
        add(severity, code, detail, None, None)
        if severity == SEVERITY_BLOCKER:
            fx_blocker_codes.add(code)

    for facts in bundle.fx:
        for source_ref in facts.provenance.sources:
            provider, model_part, kind = source_ref.split("|")
            allowed_pairs = {f"{facts.base_currency}-{facts.quote_currency}", f"{facts.quote_currency}-{facts.base_currency}"}
            if kind == "ecb_reference_xml" and provider != "ecb":
                fx_add(SEVERITY_BLOCKER, "fx_provenance_invalid_reference", f"FX provenance reference {source_ref} uses the ECB reference kind but is not an ecb publisher source")
                continue
            if model_part not in allowed_pairs or kind not in _FX_SOURCE_KINDS:
                fx_add(SEVERITY_BLOCKER, "fx_provenance_invalid_reference", f"FX provenance reference {provider}|{model_part}|{kind} is not a currency-pair source of an FX-specific kind")

    # Select the effective fact per required currency.
    effective: dict[str, tuple[Any, bool, str | None]] = {}  # C -> (fact, derived, source_pair)
    for currency in sorted(required_currencies):
        direct_candidates = [f for f in bundle.fx if f.base_currency == currency and f.quote_currency == "EUR"]
        reciprocal_candidates = [f for f in bundle.fx if f.base_currency == "EUR" and f.quote_currency == currency]
        direct, direct_ambiguous = _select_active_fx(direct_candidates, now)
        reciprocal, reciprocal_ambiguous = _select_active_fx(reciprocal_candidates, now)
        if direct_ambiguous or reciprocal_ambiguous:
            fx_add(SEVERITY_BLOCKER, f"fx_ambiguous_{currency}", f"ambiguous overlapping active FX rows for {currency}")
            continue
        if direct is None and reciprocal is None:
            fx_add(SEVERITY_BLOCKER, "fx_missing_required_pair", f"no {currency}→EUR FX fact (direct or derivable from EUR→{currency}) for a selected pricing currency")
            continue
        if direct is not None and reciprocal is not None:
            tolerance_ok = abs(Decimal(direct.rate) - _reciprocal(Decimal(reciprocal.rate))) <= _FX_CONSISTENCY_TOLERANCE
            if not tolerance_ok:
                fx_add(SEVERITY_BLOCKER, "fx_contradictory_rates", f"{currency}→EUR direct rate contradicts the reciprocal of EUR→{currency}")
                continue
            effective[currency] = (direct, False, None)
        elif direct is not None:
            effective[currency] = (direct, False, None)
        else:
            derived = _reciprocal(Decimal(reciprocal.rate))
            if derived <= 0:
                fx_add(SEVERITY_BLOCKER, "fx_invalid_reciprocal", f"reciprocal of EUR→{currency} is not positive")
                continue
            effective[currency] = (reciprocal, True, f"EUR-{currency}")

    # Per-fact publication age checks (unchanged semantics).
    for facts in bundle.fx:
        if facts.published_at is None:
            fx_add(SEVERITY_REVIEW, "fx_no_publication_date", f"{facts.base_currency}→{facts.quote_currency} has no publication date")
            continue
        age = now - _utc(facts.published_at)
        if age < timedelta(0):
            fx_add(SEVERITY_BLOCKER, "fx_future_publication", "FX publication date is in the future")
            continue
        state = policy.fx_age_state(age)
        if state == "review":
            fx_add(SEVERITY_REVIEW, "fx_stale_review", f"FX publication age {age} exceeds review threshold")
        elif state == "blocked":
            fx_add(SEVERITY_BLOCKER, "fx_stale_blocked", f"FX publication age {age} exceeds blocked threshold")

    # Baseline comparisons (current vs proposed) + executable-create decision.
    artifact_rows: list[NormalizedFxRow] = []
    excluded_mutations = 0
    no_op_rows = 0
    for currency in sorted(required_currencies):
        entry = effective.get(currency)
        if entry is None:
            continue
        fact, derived, source_pair = entry
        normalized_rate = _reciprocal(Decimal(fact.rate)) if derived else Decimal(fact.rate)
        # current baseline rate for the normalized pair (or its inverse)
        base_rows = baseline_fx_by_pair_ref(baseline, (currency, "EUR"))
        base_direct, base_direct_ambiguous = _select_active_fx(base_rows, now)
        inverse_rows = baseline_fx_by_pair_ref(baseline, ("EUR", currency))
        inverse, inverse_ambiguous = _select_active_fx(inverse_rows, now)
        current_rate = None
        current_derived = False
        if base_direct is not None:
            current_rate = Decimal(base_direct.rate)
        elif inverse is not None:
            current_rate = _reciprocal(Decimal(inverse.rate))
            current_derived = True
        if base_direct_ambiguous or inverse_ambiguous:
            fx_add(SEVERITY_BLOCKER, "fx_baseline_ambiguous", f"ambiguous active baseline FX rows around {currency}/EUR")
        delta_pct = None
        state = "NEW"
        if current_rate is not None and current_rate > 0:
            delta_pct = str(((normalized_rate - current_rate) / current_rate).quantize(Decimal("0.000000001")))
            if abs(Decimal(delta_pct)) > policy.fx_change_review:
                fx_add(SEVERITY_REVIEW, "fx_moved_review", f"{currency}→EUR moved {delta_pct} (policy {policy.fx_change_review})")
                state = "CHANGED_REVIEW"
            elif normalized_rate != current_rate:
                state = "CHANGED"
            else:
                state = "UNCHANGED"
        comparison = {
            "pair": f"{currency}→EUR",
            "current_rate": None if current_rate is None else str(current_rate),
            "current_derived": current_derived,
            "proposed_rate": str(normalized_rate),
            "derived": derived,
            "source_pair": source_pair,
            "delta_pct": delta_pct,
            "state": state,
            "source": fact.source,
            "published_at": fact.published_at.isoformat() if fact.published_at else None,
        }
        comparisons.append(comparison)

        # Executable-create decision via the real FX import classifier.
        row_dict = {
            "base_currency": currency,
            "quote_currency": "EUR",
            "rate": str(normalized_rate),
            "source": fact.source,
            "valid_from": fact.valid_from.astimezone(UTC).isoformat(),
            "valid_until": fact.valid_until.astimezone(UTC).isoformat() if fact.valid_until else None,
            "metadata": {"published_at": fact.published_at.astimezone(UTC).isoformat() if fact.published_at else None},
            "notes": "",
        }
        preview = validate_fx_import_rows([row_dict], max_rows=1, now=now)
        existing_for_row = base_rows  # same pair (currency, EUR); inverse pair does not overlap the classifier's identity
        classified = classify_fx_import_preview(preview, existing_rates_by_row={1: existing_for_row} if existing_for_row else {})
        if classified.rows[0].status != "valid":
            fx_add(SEVERITY_BLOCKER, "fx_row_invalid", f"FX row for {currency}→EUR invalid: {classified.rows[0].errors[0][:200]}")
            continue
        classification = classified.rows[0].classification
        if classification == "create":
            artifact_rows.append(
                NormalizedFxRow(
                    base_currency=currency,
                    quote_currency="EUR",
                    rate=str(normalized_rate),
                    source=fact.source,
                    valid_from=fact.valid_from,
                    valid_until=fact.valid_until,
                    published_at=fact.published_at,
                    derived_reciprocal=derived,
                    source_pair=source_pair,
                )
            )
        elif classification == "duplicate":
            no_op_rows += 1
        else:
            excluded_mutations += 1

    # Gate verdict
    if excluded_mutations:
        result.gates.append(Gate(FX_GATE, EVIDENCE_BLOCKED, f"{excluded_mutations} existing FX row(s) require an update — no apply operation exists in this version"))
    elif fx_blocker_codes:
        result.gates.append(Gate(FX_GATE, EVIDENCE_BLOCKED, "FX requirements not met: " + ", ".join(sorted(fx_blocker_codes))))
    elif artifact_rows:
        result.gates.append(Gate(FX_GATE, EVIDENCE_VERIFIED, f"create-only FX plan executable ({len(artifact_rows)} new native→EUR rate(s))"))
    elif no_op_rows:
        result.gates.append(Gate(FX_GATE, EVIDENCE_VERIFIED, f"required FX pairs already present in baseline ({no_op_rows} duplicate no-op(s)); nothing to create"))
    elif required_currencies:
        result.gates.append(Gate(FX_GATE, EVIDENCE_BLOCKED, "required FX pairs missing for: " + ", ".join(sorted(required_currencies))))
    else:
        result.gates.append(Gate(FX_GATE, EVIDENCE_NA, "all selected prices are EUR; no FX rows required"))
    result.import_gate = ImportGate(
        "fx",
        True,
        len(artifact_rows),
        len(artifact_rows),
        0,
        {"create": len(artifact_rows)},
        len(artifact_rows),
        0,
        f"{len(artifact_rows)} rows to create, {no_op_rows} duplicate no-op(s), {excluded_mutations} update(s) excluded",
        excluded_mutations,
    )
    return artifact_rows, result, comparisons


def baseline_fx_by_pair_ref(baseline, pair):
    if baseline is None:
        return []
    return [row for row in baseline.fx if (row.base_currency, row.quote_currency) == pair]


def validate_against_baseline_document(
    bundle: RefreshBundle,
    baseline: BaselineDocument | None,
    policy: RefreshPolicy,
) -> tuple[ValidationReport, dict[str, bytes]]:
    """Public entry: mode-consistent validation (first install must have no baseline)."""
    if bundle.baseline.mode == "first_install" and baseline is not None:
        raise CatalogRefreshBlockedError(
            "baseline_mode_mismatch", "first_install bundle cannot use a non-empty baseline"
        )
    if bundle.baseline.mode != "first_install" and baseline is None:
        raise CatalogRefreshBlockedError(
            "baseline_required", "refresh requires a valid baseline (db snapshot or exported file)"
        )
    return validate_bundle(bundle, baseline, policy)
