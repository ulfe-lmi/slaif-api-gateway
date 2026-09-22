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
from dataclasses import dataclass, field, replace
from fnmatch import fnmatchcase
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlparse

from slaif_gateway.schemas.catalog_refresh import (
    CAPABILITY_KEYS,
    FX_PAIR_PATTERN,
    BaselineDocument,
    RefreshBundle,
    RouteFacts,
    derive_standard_create_capabilities,
    overlay_route_capabilities,
)
from slaif_gateway.services.chat_completion_route_capabilities import (
    CHAT_CAPABILITY_TEXT,
    CHAT_COMPLETIONS_CAPABILITIES_KEY,
)
from slaif_gateway.services.catalog_refresh import source_evidence as se
from slaif_gateway.services.catalog_refresh import sources as _source_registry
from slaif_gateway.services.catalog_refresh.collection import (
    CHAT_ENDPOINT,
    _baseline_route_flat_capable,
)
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
    ("openai", "openai_models_docs"): frozenset({"openai.com"}),
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

# 180-e (E5): SQL evidence is a property of the actual execution path that
# produced or supplied the baseline, never of a caller-supplied mode label.
# The four capture paths are: explicit first install (no database read), a
# supplied baseline document (SQL was executed historically at that document's
# export time), a live read-only export performed by this review command, and
# the offline seal replay (recomputes from sealed bytes, executes no SQL).
SQL_CAPTURE_FIRST_INSTALL = "first_install"
SQL_CAPTURE_DOCUMENT = "document"
SQL_CAPTURE_LIVE_EXPORT = "live_export"
_SQL_CAPTURES: frozenset[str] = frozenset(
    {SQL_CAPTURE_FIRST_INSTALL, SQL_CAPTURE_DOCUMENT, SQL_CAPTURE_LIVE_EXPORT}
)

_SQL_CAPTURE_NOTES: dict[str, str] = {
    SQL_CAPTURE_FIRST_INSTALL: (
        "Explicit first install: no database was read and no baseline document "
        "exists; no SQL was executed during this review."
    ),
    SQL_CAPTURE_DOCUMENT: (
        "Baseline consumed from a supplied document: the document DECLARES a "
        "historical SQL export at its export time; consuming the file does not "
        "verify that historical SQL execution occurred, and this review does not "
        "attest it; no SQL was executed during this review."
    ),
    SQL_CAPTURE_LIVE_EXPORT: (
        "SQL was executed during this review: this review command performed the "
        "live read-only baseline export."
    ),
}


def sql_capture_for_mode(mode: str) -> str:
    """The only capture a bundle with this declared baseline mode may carry."""
    if mode == "first_install":
        return SQL_CAPTURE_FIRST_INSTALL
    if mode == "db_snapshot":
        return SQL_CAPTURE_LIVE_EXPORT
    if mode == "exported_file":
        return SQL_CAPTURE_DOCUMENT
    raise CatalogRefreshBlockedError("sql_capture_invalid", f"unknown baseline mode {mode!r}")

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
    baseline_metadata: list[dict[str, Any]] = field(default_factory=list)
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
            "baseline_metadata": [
                {
                    "provider": row["provider"],
                    "model": row["model"],
                    "upstream_model": row.get("upstream_model"),
                    "fields": dict(sorted(row["fields"].items())),
                }
                for row in sorted(
                    self.baseline_metadata,
                    key=lambda r: (r["provider"], r["model"], r.get("upstream_model") or ""),
                )
            ],
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


# 180-e (E1): proposal-side flat capability keys map onto the baseline's
# nested chat_completions block with a "chat_" prefix (standard v1 profile).
_PROPOSAL_CAPABILITY_TO_BASELINE: dict[str, str] = {key: f"chat_{key}" for key in CAPABILITY_KEYS}

# 180-e (E2): the allowlisted monetary metadata fields preserved from the
# baseline for review display (never silently dropped from the record).
_BASELINE_METADATA_FIELDS: tuple[str, ...] = (
    "audio_output_price_per_1m",
    "cache_write_input_price_per_1m",
    "cache_write_input_multiplier",
    "long_context_threshold_tokens",
    "long_context_input_multiplier",
    "long_context_output_multiplier",
    "external_tool_price_per_call",
    "external_tool_source",
)


def _effective_chat_text_capability(route: RouteFacts) -> bool:
    """chat_text of the contract the emitted import path would actually store.

    180-f (F2): proposals emit the conservative create contract (the
    documented standard text/streaming scope plus explicitly declared
    standard keys), and the import path stores a declared nested block
    verbatim. An explicit text denial therefore narrows the executable
    surface; a text omission stays inside the documented standard scope
    (chat_text enabled for a standard text route). Computed with the same
    single mapping used for the emitted import bytes and the
    before/after comparison.
    """
    block = derive_standard_create_capabilities(
        route.capabilities, supports_streaming=route.supports_streaming
    )
    return bool(block.get(CHAT_CAPABILITY_TEXT, False))


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
    *,
    sql_capture: str,
) -> tuple[ValidationReport, dict[str, bytes]]:
    """Recompute the full review result. Pure and deterministic.

    ``sql_capture`` names the actual execution path that produced or supplied
    the baseline for this review (180-e). It is never inferred from the
    bundle's mode label alone: a capture inconsistent with the declared mode
    blocks the run instead of letting a label claim SQL evidence the path did
    not produce.
    """
    if sql_capture not in _SQL_CAPTURES:
        raise CatalogRefreshBlockedError(
            "sql_capture_invalid",
            f"sql_capture must be one of {sorted(_SQL_CAPTURES)}, got {sql_capture!r}",
        )
    expected_capture = sql_capture_for_mode(bundle.baseline.mode)
    if sql_capture != expected_capture:
        raise CatalogRefreshBlockedError(
            "sql_capture_mismatch",
            f"this review path captured SQL evidence as {sql_capture!r} but the bundle "
            f"declares baseline mode {bundle.baseline.mode!r} (capture {expected_capture!r}); "
            "a mode label cannot claim SQL evidence its path did not produce",
        )
    if (baseline is None) != (bundle.baseline.mode == "first_install"):
        raise CatalogRefreshBlockedError(
            "baseline_mode_mismatch",
            "a first_install review reads no database and a refresh review requires a baseline document",
        )
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
    baseline_model_keys: set[tuple[str, str]] = (
        {identity[:2] for identity in baseline_routes_by_identity}
        | {(p, m) for (p, m, _e) in baseline_pricing_by_key}
    )

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
    deduped_models: dict[str, list[se.ParsedModel]] = {}
    fx_quotes: list[tuple[str, se.ParsedFxQuote]] = []
    all_observations: list[se.Observation] = []
    source_digests: dict[str, str] = {}
    source_urls: dict[str, str] = {}
    source_times: dict[str, str] = {}
    official_source_keys: set[str] = set()
    # 181: models whose one snapshot carries same-context conflicting rows
    # are blocked per model (the global dedupe finding alone would let a
    # row matching one conflicting value still reach the import artifacts).
    conflicting_model_ids: set[tuple[str, str]] = set()
    for source, assessment in zip(bundle.sources, source_assessments):
        key = f"{source.provider}|{source.model}|{source.source_kind}"
        assessment_by_key[key] = assessment
        assessment["parser"] = se.PARSER_IDS.get((source.provider, source.source_kind), "")
        source_urls[key] = source.url
        source_times[key] = source.retrieved_at.isoformat()
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
            # 180-d: conflicting rows within ONE snapshot block (a single
            # digest disagreeing with itself is a contradiction, not a
            # skip); identical duplicate rows deduplicate under an explicit
            # safe policy with an honest finding and reconciled counts.
            kept, duplicates = se.dedupe_parsed_models(parsed)
            deduped_models[key] = kept
            for duplicate_id, (kind, count) in sorted(duplicates.items()):
                if kind == "identical":
                    add(
                        SEVERITY_REVIEW,
                        "source_duplicate_rows_deduplicated",
                        f"source {key} repeats {count} identical rows for model {duplicate_id}; deduplicated with an explicit count, not silently",
                        source.provider,
                        duplicate_id,
                    )
                else:
                    conflicting_model_ids.add((source.provider, duplicate_id))
                    add(
                        SEVERITY_BLOCKER,
                        "source_observations_contradict",
                        f"source {key} contains {count} conflicting rows for model {duplicate_id} within one snapshot; conflicting values block",
                        source.provider,
                        duplicate_id,
                    )
            if kept:
                deduped = replace(parsed, models=tuple(kept))
                all_observations.extend(se.derive_observations(key, deduped))
            for quote in parsed.fx_quotes:
                fx_quotes.append((key, quote))
            if assessment["classification"] == SOURCE_OFFICIAL:
                official_source_keys.add(key)
        elif se.has_deterministic_parser(source.provider, source.source_kind):
            # 180-d: a required source with a registered parser whose
            # digest-verified bytes fail deterministic parsing is blocked
            # regardless of the extraction label: a semantic label is not
            # evidence, and a matching hash of unparseable bytes is not
            # content trust.
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

    # --- 181-b: every observed official row, keyed for eligibility ----
    # The shared standard-v1 billing policy recomputes from these parsed
    # rows (never from the proposal's own claims), so a supplied or
    # tampered bundle cannot bypass eligibility by dropping dimensions.
    official_rows: dict[str, dict[str, list[se.ParsedModel]]] = {}
    page_ok_models: set[str] = set()
    page_rows: dict[str, se.ParsedModel] = {}
    for key, parsed in parse_results.items():
        if not parsed.ok or key not in official_source_keys:
            continue
        source_kind = key.split("|", 2)[2]
        for parsed_model in deduped_models.get(key, []):
            if parsed_model.provider not in selection_providers:
                continue
            official_rows.setdefault(parsed_model.provider, {}).setdefault(
                parsed_model.model, []
            ).append(parsed_model)
            if source_kind == "docs_page":
                page_ok_models.add(parsed_model.model)
                page_rows.setdefault(parsed_model.model, parsed_model)
    evidence_ids_by_provider: dict[str, dict[str, se.ParsedModel]] = {
        provider: {model_id: rows[-1] for model_id, rows in by_model.items()}
        for provider, by_model in official_rows.items()
    }

    # --- 181-b (B1): shared billing eligibility, recomputed for EVERY
    # bundle (live collection AND offline supplied-bundle replay). A
    # proposed model whose official parsed observations are not billable
    # under the flat standard-v1 contract is a blocker, with the exact
    # policy reason; a positive published charge that the proposal drops
    # or alters is a blocker, not an exclusion.
    proposed_pricing_rows: dict[tuple[str, str], list[Any]] = {}
    for item in bundle.pricing:
        proposed_pricing_rows.setdefault((item.provider, item.model), []).append(item)
    proposed_fact_keys = (
        {(item.provider, item.model) for item in bundle.models}
        | set(proposed_pricing_rows)
    )
    for provider, model in sorted(proposed_fact_keys):
        if provider not in selection_providers:
            continue
        rows = official_rows.get(provider, {}).get(model)
        if not rows:
            continue  # no official parsed rows: the evidence gates own it
        decision = se.standard_v1_billing_decision(provider, rows)
        if not decision.eligible:
            add(
                SEVERITY_BLOCKER,
                "proposed_row_billing_ineligible",
                f"proposed model is not billable under the flat standard-v1 contract: "
                f"{decision.reason_code} - {decision.detail}",
                provider,
                model,
            )
            continue
        for dim, value_text, unit in decision.carried:
            try:
                observed_value = Decimal(value_text)
            except InvalidOperation:
                continue
            pricing_rows = proposed_pricing_rows.get((provider, model), [])
            if not pricing_rows:
                continue
            missing = True
            mismatch = False
            for pricing in pricing_rows:
                match = next(
                    (d for d in pricing.dimensions if d.name == dim), None
                )
                if match is None:
                    missing = True
                    break
                try:
                    proposed_value = (
                        Decimal(match.value) if match.value is not None else None
                    )
                except InvalidOperation:
                    proposed_value = None
                if match.unit != unit or proposed_value is None or proposed_value != observed_value:
                    missing = False
                    mismatch = True
                    break
                missing = False
            if missing:
                add(
                    SEVERITY_BLOCKER,
                    "proposed_row_billing_dim_missing",
                    f"official source publishes a positive {dim} charge but the proposal omits it; "
                    "removing a billable dimension is not an exclusion",
                    provider,
                    model,
                )
            elif mismatch:
                add(
                    SEVERITY_BLOCKER,
                    "proposed_row_billing_dim_mismatch",
                    f"proposed {dim} charge does not equal the published {value_text} "
                    f"(unit {unit})",
                    provider,
                    model,
                )

    # --- 181-b (B2): local route authority is never overridden ---------
    # A baseline public route for an upstream that still exists must not be
    # replaced by proposed route name(s) under the same upstream (no alias
    # clobbering, no parallel upstream-named route), in live collection and
    # supplied-bundle review alike.
    if baseline is not None:
        proposed_names_by_upstream: dict[tuple[str, str], set[str]] = {}
        for route in bundle.routes:
            if route.match_type == "exact" and route.endpoint == CHAT_ENDPOINT:
                proposed_names_by_upstream.setdefault(
                    (route.provider, route.upstream_model), set()
                ).add(route.requested_model)
        seen_replacements: set[tuple[str, str, str]] = set()
        baseline_names_by_upstream: dict[tuple[str, str], set[str]] = {}
        for row in baseline.routes:
            if row.match_type == "exact" and row.endpoint == CHAT_ENDPOINT:
                baseline_names_by_upstream.setdefault(
                    (row.provider, row.upstream_model), set()
                ).add(row.requested_model)
        for row in baseline.routes:
            if row.match_type != "exact" or row.endpoint != CHAT_ENDPOINT:
                continue
            proposed = proposed_names_by_upstream.get(
                (row.provider, row.upstream_model)
            )
            if not proposed:
                continue
            # A baseline route whose public name IS the upstream identity is
            # not a public alias: renaming its public name follows the
            # established 180 create/mutation semantics, not alias
            # preservation. A GENUINE alias (public name != upstream) must
            # be preserved exactly, and a parallel upstream-named route for
            # that upstream must never be proposed (no alias clobbering, no
            # bypass route).
            if row.requested_model == row.upstream_model:
                continue
            if row.requested_model not in proposed:
                identity = (row.provider, row.requested_model, row.upstream_model)
                if identity in seen_replacements:
                    continue
                seen_replacements.add(identity)
                add(
                    SEVERITY_BLOCKER,
                    "alias_route_replaced",
                    f"baseline public alias {row.requested_model!r} for upstream "
                    f"{row.upstream_model!r} is replaced by proposed route name(s) "
                    f"{', '.join(sorted(proposed))!s}; local route authority is preserved "
                    "and no parallel route bypasses the alias",
                    row.provider,
                    row.requested_model,
                )
            elif (
                row.upstream_model in proposed
                and row.upstream_model
                not in baseline_names_by_upstream.get(
                    (row.provider, row.upstream_model), set()
                )
            ):
                identity = (
                    row.provider,
                    f"parallel:{row.upstream_model}",
                    row.upstream_model,
                )
                if identity in seen_replacements:
                    continue
                seen_replacements.add(identity)
                add(
                    SEVERITY_BLOCKER,
                    "alias_route_replaced",
                    f"proposed route {row.upstream_model!r} is a parallel upstream-named "
                    f"route for an upstream already held by baseline alias "
                    f"{row.requested_model!r}; no parallel route bypasses the alias",
                    row.provider,
                    row.requested_model,
                )

    # --- 180-d: FX facts must bind to parsed authoritative quotes BEFORE any
    # currency normalization. A candidate rate merely labelled verified
    # before its check is not verified: fx_to_eur is built exclusively from
    # quotes that passed full binding (rate within tolerance in the direct or
    # exact-reciprocal direction, finite positive fact rate, publication date
    # equal to the quote date, quote source declared in the fact's
    # provenance). No semantic/manual escape hatch for guessed FX. ---------
    fx_backed: list[dict[str, Any]] = []
    bound_fx: list[Any] = []
    fx_to_eur: dict[str, Decimal] = {}
    fx_rate_provenance: dict[str, dict[str, Any]] = {}
    for facts in bundle.fx:
        pair = (facts.base_currency, facts.quote_currency)
        pair_names = {f"{pair[0]}-{pair[1]}", f"{pair[1]}-{pair[0]}"}
        field_quotes = [
            (source_key, quote)
            for source_key, quote in fx_quotes
            if f"{quote.base_currency}-{quote.quote_currency}" in pair_names
        ]
        official_quotes = [item for item in field_quotes if item[0] in official_source_keys]
        if not official_quotes:
            if field_quotes:
                add(
                    SEVERITY_BLOCKER,
                    "source_evidence_unapproved",
                    f"FX fact {pair[0]} to {pair[1]} is backed only by unapproved source quotes",
                    None,
                    None,
                )
            else:
                add(
                    SEVERITY_BLOCKER,
                    "fx_evidence_unbound",
                    f"FX fact {pair[0]} to {pair[1]} has no verified reference quote; semantic/manual rates are not evidence",
                    None,
                    None,
                )
            continue
        try:
            fact_rate = Decimal(facts.rate)
        except InvalidOperation:
            fact_rate = None
        if fact_rate is None or not fact_rate.is_finite() or fact_rate <= 0:
            add(
                SEVERITY_BLOCKER,
                "fx_rate_not_finite_positive",
                f"FX fact {pair[0]} to {pair[1]} rate is not a finite positive decimal",
                None,
                None,
            )
            continue
        # 180-f (F3): compare exact Decimal values in the FACT PAIR's
        # direction, grouped by (publication date, direction) context.
        # Equivalent spellings (1.08 == 1.080) must not fabricate a
        # financial conflict; genuine same-context disagreements still
        # block. Cross-direction quotes on the same date must agree within
        # the bounded reciprocal tolerance, never by unstable invert-back
        # equality.
        direct_by_date: dict[Any, set[Decimal]] = {}
        reciprocal_by_date: dict[Any, set[Decimal]] = {}
        for _key, quote in official_quotes:
            if (quote.base_currency, quote.quote_currency) == pair:
                direct_by_date.setdefault(quote.published_date, set()).add(quote.rate)
            else:
                reciprocal_by_date.setdefault(quote.published_date, set()).add(_reciprocal(quote.rate))
        fx_conflicts: list[str] = []
        for pub_date in sorted(set(direct_by_date) | set(reciprocal_by_date)):
            direct_values = direct_by_date.get(pub_date, set())
            reciprocal_values = reciprocal_by_date.get(pub_date, set())
            if len(direct_values) > 1:
                fx_conflicts.extend(str(value) for value in sorted(direct_values))
            if len(reciprocal_values) > 1 and max(reciprocal_values) - min(reciprocal_values) > 2 * se.FX_BINDING_TOLERANCE:
                fx_conflicts.extend(str(value) for value in sorted(reciprocal_values))
            for value in direct_values:
                if reciprocal_values and not any(
                    abs(value - reciprocal_value) <= se.FX_BINDING_TOLERANCE
                    for reciprocal_value in reciprocal_values
                ):
                    fx_conflicts.append(str(value))
        if fx_conflicts:
            add(
                SEVERITY_BLOCKER,
                "source_observations_contradict",
                f"distinct FX snapshots disagree on {pair[0]}-{pair[1]}: {', '.join(sorted(set(fx_conflicts))[:4])}",
                None,
                None,
            )
            continue
        # 180-f (F3): the supporting quote is selected from the fact's OWN
        # declared, approved, parsed sources - a rate match at an undeclared
        # source is not backing, and an earlier uncited match must never
        # shadow a later correctly cited quote. The independent
        # same-context contradiction check above still covers ALL
        # authoritative evidence for the pair.
        declared_quotes = [
            (source_key, quote)
            for source_key, quote in official_quotes
            if source_key in facts.provenance.sources
        ]
        if not declared_quotes:
            add(
                SEVERITY_BLOCKER,
                "source_evidence_reference_mismatch",
                f"FX fact {pair[0]} to {pair[1]} is not declared to be supported by any verified quote source for this pair",
                None,
                None,
            )
            continue
        matched: tuple[str, se.ParsedFxQuote, bool] | None = None
        value_matched: tuple[str, se.ParsedFxQuote, bool] | None = None
        for source_key, quote in declared_quotes:
            same_direction = (quote.base_currency, quote.quote_currency) == pair
            # Reciprocal quotes are validated in the proposed pair's
            # direction (quote normalized to the fact's direction), with
            # the explicit bounded tolerance - no invert-back of the fact
            # rate.
            quote_in_pair_direction = quote.rate if same_direction else _reciprocal(quote.rate)
            if abs(quote_in_pair_direction - fact_rate) > se.FX_BINDING_TOLERANCE:
                continue
            candidate = (source_key, quote, same_direction)
            if (
                matched is None
                and facts.published_at is not None
                and quote.published_date == facts.published_at.date()
            ):
                matched = candidate
                break
            if value_matched is None:
                value_matched = candidate
        if matched is None and value_matched is None:
            add(
                SEVERITY_BLOCKER,
                "source_evidence_value_mismatch",
                f"FX rate {facts.rate} does not match any verified {pair[0]}/{pair[1]} reference quote or its reciprocal declared by this fact",
                None,
                None,
            )
            continue
        source_key, quote, same_direction = matched if matched is not None else value_matched
        if facts.published_at is None:
            add(
                SEVERITY_BLOCKER,
                "fx_evidence_date_mismatch",
                f"FX fact {pair[0]} to {pair[1]} carries no publication date; the verified quote is dated {quote.published_date.isoformat()}",
                None,
                None,
            )
            continue
        if matched is None:
            add(
                SEVERITY_BLOCKER,
                "fx_evidence_date_mismatch",
                f"FX fact publication date {facts.published_at.date().isoformat()} does not match the verified quote date {quote.published_date.isoformat()}",
                None,
                None,
            )
            continue
        bound_fx.append(facts)
        fx_backed.append(
            {
                "pair": f"{pair[0]} to {pair[1]}",
                "rate": facts.rate,
                "backed_by": source_key,
                "observed_quote": str(quote.rate),
                "derived_reciprocal": not same_direction,
                "quote_date": quote.published_date.isoformat(),
                "quote_locator": quote.locator,
                "quote_url": source_urls.get(source_key, ""),
                "quote_digest": source_digests.get(source_key, ""),
                "quote_retrieved_at": source_times.get(source_key, ""),
                "quote_parser": quote.parser,
                "fact_published_at": facts.published_at.isoformat(),
            }
        )
        # Register the verified native -> EUR rate from the QUOTE (not the
        # fact's string), using the exact reciprocal rule the FX gate uses.
        if quote.quote_currency == "EUR":
            currency_to_register = quote.base_currency
            rate_to_register = quote.rate
        elif quote.base_currency == "EUR":
            currency_to_register = quote.quote_currency
            rate_to_register = _reciprocal(quote.rate)
        else:
            continue
        existing = fx_to_eur.get(currency_to_register)
        if existing is not None:
            # 180-f (F3): same-direction quotes must be exactly equal; quotes
            # reaching the same currency from opposite directions are rounded
            # reciprocals of each other and must agree within the bounded
            # reciprocal tolerance (an invert-back equality would be unstable).
            existing_derived = bool(
                fx_rate_provenance.get(currency_to_register, {}).get("derived_reciprocal")
            )
            this_derived = quote.base_currency == "EUR"
            agreement = (
                existing == rate_to_register
                if existing_derived == this_derived
                else abs(existing - rate_to_register) <= se.FX_BINDING_TOLERANCE
            )
            if not agreement:
                add(
                    SEVERITY_BLOCKER,
                    "source_observations_contradict",
                    f"verified FX quotes give conflicting {currency_to_register} to EUR rates: {existing} vs {rate_to_register}",
                    None,
                    None,
                )
                continue
        fx_to_eur[currency_to_register] = rate_to_register
        fx_rate_provenance[currency_to_register] = {
            "pair": f"{quote.base_currency}-{quote.quote_currency}",
            "rate": str(quote.rate),
            "derived_reciprocal": quote.base_currency == "EUR",
            "quote_date": quote.published_date.isoformat(),
            "source": source_key,
        }

    # --- per-selected-model dispositions ----------------------------------
    dispositions: list[Disposition] = []
    price_comparisons: list[PriceComparison] = []
    baseline_metadata_rows: list[dict[str, Any]] = []
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
        # 181-b (B2): pairing by the route's UPSTREAM identity. A preserved
        # public alias is local routing state: the route row keeps both
        # names, and the model/pricing facts of the upstream it forwards to
        # pair through the route's upstream_model (the established 180-f
        # pairing authority). A local name never misses a pairing merely
        # because its fact sits under the upstream identity, and a fact
        # under an upstream identity is served by the retained alias route.
        if facts is None and routes:
            for upstream in sorted({r.upstream_model for r in routes}):
                if upstream == model:
                    continue
                candidate = models_by_key.get((provider, upstream))
                if candidate is not None:
                    facts = candidate
                    break
        if not pricing_facts_list and routes:
            for upstream in sorted({r.upstream_model for r in routes}):
                if upstream == model:
                    continue
                candidate = pricing_by_key.get((provider, upstream), [])
                if candidate:
                    pricing_facts_list = candidate
                    break
        if not routes and (facts is not None or pricing_facts_list):
            routes = [
                r
                for r in bundle.routes
                if r.provider == provider
                and r.upstream_model == model
                and r.match_type == "exact"
                and r.endpoint == CHAT_ENDPOINT
            ]
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
                    # 181-b (B2): a baseline name carried ONLY by wildcard
                    # (prefix/glob) route rows is a local routing pattern,
                    # not a source model: it was never part of the source
                    # catalog, so it cannot "disappear" from it. The local
                    # row is retained with an explicit deterministic
                    # disposition (no delete semantics in this version).
                    if (
                        not any(
                            identity[:2] == (provider, model)
                            and identity[2] == "exact"
                            for identity in baseline_routes_by_identity
                        )
                        and not any(
                            p2 == provider and m2 == model
                            for (p2, m2, _endpoint2) in baseline_pricing_by_key
                        )
                        and any(
                            row.provider == provider
                            and row.requested_model == model
                            and row.match_type != "exact"
                            and row.endpoint == CHAT_ENDPOINT
                            for row in (baseline.routes if baseline is not None else ())
                        )
                    ):
                        dispositions.append(
                            Disposition(
                                provider,
                                model,
                                DISPOSITION_NOT_FETCHED,
                                "local wildcard route retained (routing pattern is local "
                                "state, not a source model); no delete semantics in this version",
                            )
                        )
                        bump(provider, "not_fetched")
                        continue
                    # 181: a collection inventory entry with a baseline-
                    # retention reason documents WHY this observed baseline
                    # model was not proposed (its stored contract cannot be
                    # proposed flat). That is a documented retain-local, not
                    # an absence from the source set; the full inventory
                    # verification still re-checks the claim against the
                    # baseline and blocks on any unsupported entry.
                    _collection = bundle.collection
                    _entry = next(
                        (
                            e
                            for e in (_collection.inventory if _collection is not None else ())
                            if e.provider == provider and e.model == model
                        ),
                        None,
                    )
                    if _entry is None:
                        # 181-b (B2): a baseline model may be a PUBLIC ALIAS
                        # whose retention entry is keyed by the upstream
                        # identity; resolve through the baseline route rows
                        # (the alias remaining mapped to a present upstream
                        # is retention, never disappearance).
                        _inventory = (
                            _collection.inventory if _collection is not None else ()
                        )
                        for _row in (baseline.routes if baseline is not None else ()):
                            if (
                                _row.provider != provider
                                or _row.requested_model != model
                                or _row.endpoint != CHAT_ENDPOINT
                            ):
                                continue
                            _entry = next(
                                (
                                    e
                                    for e in _inventory
                                    if e.provider == provider
                                    and e.model == _row.upstream_model
                                ),
                                None,
                            )
                            if _entry is not None:
                                break
                    if (
                        _entry is not None
                        and _entry.reason_code
                        in (
                            "baseline_contract_not_flat",
                            "baseline_currency_mismatch",
                            "baseline_multiple_routes",
                        )
                        and (provider, model) in baseline_model_keys
                    ):
                        dispositions.append(
                            Disposition(
                                provider,
                                model,
                                DISPOSITION_NOT_FETCHED,
                                f"retained locally per collection inventory ({_entry.reason_code}); observed in sources, not proposed",
                            )
                        )
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

        # --- 180-d: bind proposed facts to parsed snapshot observations ---
        # Provider facts bind to provider + the route's ACTUAL upstream
        # model (a public alias is local routing policy, not a model whose
        # price can be borrowed). Each field is validated against the
        # sources its own fact declares; conflicts are detected across all
        # official observations for the context, so selective citation
        # cannot hide a conflicting supplied observation. Only
        # OFFICIAL-classified observations (approved publisher/kind/parser/
        # host, digest-verified bytes, successful deterministic parse) can
        # verify a fact; operator/semantic provenance never does.
        # 180-e (E3): effective text eligibility is what the imported route
        # would actually be able to execute: the model-level claim OR the
        # ACTUAL runtime contract of any proposed route, computed with the
        # importer's defaults. Proposals carry flat standard keys only; the
        # import path adds the default chat_completions block (which enables
        # chat_text) whenever no nested block is declared, so a flat text
        # omission/false cannot narrow the executable surface.
        effective_text = bool(facts.capabilities.get("text")) if facts is not None else False
        if not effective_text:
            effective_text = any(_effective_chat_text_capability(route) for route in routes)
        fact_sources = frozenset(facts.provenance.sources) if facts is not None else frozenset()
        declared: dict[str, frozenset[str]] = {
            f"pricing:{dimension.name}": frozenset(pricing_facts.provenance.sources)
            for dimension in pricing_facts.dimensions
        }
        if facts is not None:
            if facts.context_length is not None:
                declared["model:context_length"] = fact_sources
            if facts.max_output_tokens is not None:
                declared["model:max_output_tokens"] = fact_sources
            if facts.deprecated:
                declared["model:deprecated"] = fact_sources
        if effective_text:
            text_sources = set(fact_sources)
            for route in routes:
                text_sources.update(route.provenance.sources)
            declared["model:capability:text"] = frozenset(text_sources)
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
        if effective_text:
            proposed["model:capability:text"] = True
        evidence_findings, backed_facts, _unresolved_fields, missing_fx = se.reconcile_model_facts(
            provider=provider,
            binding_model=upstream,
            proposed=proposed,
            observations=tuple(all_observations),
            official_source_keys=frozenset(official_source_keys),
            declared_sources=declared,
            fx_to_eur=fx_to_eur,
            urls=source_urls,
            digests=source_digests,
            source_times=source_times,
            fx_info=fx_rate_provenance,
        )
        # 180-e (E3): an observed official deprecation fact can never be
        # bypassed by omitting the proposal field. If an official snapshot
        # reports the binding model as deprecated, the proposal must carry it
        # (handled above as DEPRECATED); otherwise the affected proposal is
        # blocked. No auto-delete and no auto-disable: the local row is
        # retained and a human decides.
        deprecated_conflict = False
        deprecated_observations = se.observations_for(
            all_observations,
            field_name="model:deprecated",
            model_names=frozenset({upstream}),
            provider=provider,
        )
        if any(
            observation.source_key in official_source_keys and observation.value == "true"
            for observation in deprecated_observations
        ) and not (facts is not None and facts.deprecated):
            deprecated_conflict = True
            add(
                SEVERITY_BLOCKER,
                "source_evidence_value_mismatch",
                "source reports the binding model as deprecated but the proposal is not; the affected proposal is blocked (retain the local row; no auto-delete or auto-disable)",
                provider,
                model,
            )
        for finding in evidence_findings:
            add(finding.severity, finding.code, finding.detail, finding.provider, finding.model)
        for backed_field in sorted(backed_facts):
            backed_fact = backed_facts[backed_field]
            evidence_backed_facts.append(
                {
                    "provider": provider,
                    "model": model,
                    "upstream_model": upstream,
                    "field": backed_fact.field,
                    "proposed": backed_fact.proposed,
                    "proposed_normalized": backed_fact.proposed_normalized,
                    "backed_by": list(backed_fact.backed_by),
                    "independent_sources": backed_fact.independent_sources,
                    "observations": list(backed_fact.observations),
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
        declared_all = {key for keys in declared.values() for key in keys}
        complete_keys = [
            key
            for key in declared_all
            if parse_results.get(key) is not None and parse_results[key].ok
        ]
        model_missing = bool(
            complete_keys
            and not any(
                parsed_model.model == upstream
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
        snapshot_conflict = (provider, upstream) in conflicting_model_ids
        if (
            any(finding.severity == SEVERITY_BLOCKER for finding in evidence_findings)
            or missing_fx
            or model_missing
            or deprecated_conflict
            or snapshot_conflict
        ):
            blocked_codes = sorted(
                {finding.code for finding in evidence_findings if finding.severity == SEVERITY_BLOCKER}
                | ({"fx_evidence_unbound"} if missing_fx else set())
                | ({"source_evidence_model_missing"} if model_missing else set())
                | ({"source_observations_contradict"} if snapshot_conflict else set())
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
        # 180-e (E2): monetary metadata outside the allowlist flags the row
        # instead of being silently dropped from the before/after record.
        baseline_metadata_unrepresented = bool(
            old_pricing is not None and getattr(old_pricing, "pricing_metadata_unrepresented", False)
        )
        if baseline_metadata_unrepresented:
            add(
                SEVERITY_BLOCKER,
                "baseline_unrepresented_metadata",
                "baseline pricing metadata carries values outside the current allowlist; the row is blocked rather than claimed safe-update or no-change",
                provider,
                model,
            )
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
        if old_pricing is not None:
            preserved_metadata = {
                name: getattr(old_pricing, name)
                for name in _BASELINE_METADATA_FIELDS
                if getattr(old_pricing, name, None) is not None
            }
            if preserved_metadata:
                baseline_metadata_rows.append(
                    {
                        "provider": provider,
                        "model": model,
                        "upstream_model": upstream,
                        "fields": dict(sorted(preserved_metadata.items())),
                    }
                )
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
        route_unrepresented = False
        streaming_conflict = False
        text_disabled_create = False
        for route, old_route in zip(routes, old_route_rows):
            # 180-f (F2): a proposal declaring the streaming capability
            # with a different supports_streaming column is
            # self-contradictory; reject explicitly instead of a silent
            # precedence accident.
            flat_streaming = (route.capabilities or {}).get("streaming")
            if isinstance(flat_streaming, bool) and flat_streaming is not route.supports_streaming:
                streaming_conflict = True
                add(
                    SEVERITY_BLOCKER,
                    "streaming_intent_conflict",
                    f"route declares streaming capability {flat_streaming} but supports_streaming={route.supports_streaming}; contradictory streaming intent is rejected explicitly",
                    provider,
                    model,
                )
            if old_route is None:
                # 180-f (F2): new rows get the conservative create
                # contract (same single mapping as the emitted import
                # bytes). A text-disabled route is not a usable standard
                # text candidate; block the create with a clear reason
                # rather than silently enabling text or claiming a text
                # bootstrap.
                create_block = derive_standard_create_capabilities(
                    route.capabilities, supports_streaming=route.supports_streaming
                )
                if not create_block.get(CHAT_CAPABILITY_TEXT, False):
                    text_disabled_create = True
                    add(
                        SEVERITY_BLOCKER,
                        "text_disabled_route",
                        "route declares text disabled; not a usable standard text candidate; no text bootstrap is claimed",
                        provider,
                        model,
                    )
                continue
            for attr in ("upstream_model", "priority", "enabled", "visible_in_models", "supports_streaming", "match_type"):
                new_value = getattr(route, attr)
                old_value = getattr(old_route, attr)
                if isinstance(new_value, bool):
                    old_value = bool(old_value)
                if new_value != old_value:
                    route_changed = True
                    changed_fields.append(f"route.{attr}")
            if getattr(old_route, "capabilities_unrepresented", False):
                route_unrepresented = True
            # 180-f (F2): partial-intent preservation. The reviewed
            # baseline block is the base; ONLY the explicitly declared
            # intent is overlaid. Omitted approved fields - including
            # explicit denials - are preserved, so a partial proposal
            # never rewrites stored capability metadata it did not
            # request; an explicitly requested capability change is
            # shown as a change (create-only behavior preserved).
            old_capabilities = getattr(old_route, "capabilities", None) or {}
            old_block = old_capabilities.get(CHAT_COMPLETIONS_CAPABILITIES_KEY)
            old_block = dict(old_block) if isinstance(old_block, Mapping) else {}
            effective_block = overlay_route_capabilities(old_block, route.capabilities)
            if effective_block != old_block:
                route_changed = True
                for field in sorted(set(effective_block) | set(old_block)):
                    if effective_block.get(field) != old_block.get(field):
                        changed_fields.append(f"route.capabilities.{field}")
        if route_unrepresented:
            add(
                SEVERITY_BLOCKER,
                "baseline_unrepresented_capabilities",
                "baseline route capabilities are not fully representable by the current allowlist; the row is blocked rather than claimed unchanged",
                provider,
                model,
            )

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
                    # 180-f (F4): the threshold decision compares the exact
                    # ratio BEFORE display quantization (cross-multiplied,
                    # so rounding can never move an above-threshold value
                    # back onto the threshold); _pct is display-only.
                    if abs(new_value - old_entry) > policy.price_change_review * abs(old_entry):
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

        if dimension_blocked or currency_conflict or pricing_ambiguous or route_unrepresented or baseline_metadata_unrepresented or streaming_conflict or text_disabled_create:
            disposition = DISPOSITION_BLOCKED
            disposition_detail = "blocked: " + "; ".join(sorted(set(changed_fields + ["required pricing dimension(s) missing" if dimension_blocked else ""] + ["currency inconsistency" if currency_conflict else ""] + ["ambiguous baseline rows" if pricing_ambiguous else ""] + ["unrepresentable baseline capabilities" if route_unrepresented else ""] + ["unrepresentable baseline metadata" if baseline_metadata_unrepresented else ""] + ["streaming intent conflict" if streaming_conflict else ""] + ["text disabled route" if text_disabled_create else ""])))
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
    # FX facts that failed evidence binding above are not executable: the
    # FX gate sees only bound facts, so an unbound required pair surfaces as
    # a missing-pair blocker instead of an executable row with a guessed
    # rate.
    bundle_for_fx = bundle if len(bound_fx) == len(bundle.fx) else bundle.model_copy(update={"fx": tuple(bound_fx)})
    fx_rows, fx_gate, fx_comparisons = _run_fx_gate(
        baseline, bundle_for_fx, now, fx_required_currencies, policy, add
    )
    fx_json = generate_fx_json(fx_rows)

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

    # --- 180-d: selection reconciliation ----------------------------------
    # Inventory derived independently from the official parsed snapshots,
    # then every parsed raw identifier is reconciled into an explicit
    # disposition: selected/proposed, retained from baseline (historical
    # local state), explicitly excluded by a subset, unsupported (text
    # capability not observed), or an unexplained omission under an
    # all-eligible selection - which blocks. No silent row disappearance.
    # --- 181: collection identity gates (live collection evidence) ---------
    # A bundle carrying a CollectionIdentity claims this invocation actually
    # fetched its sources. Those claims are re-checked against the bundle's
    # own source records and the parsed official evidence: a
    # caller-supplied success label never backs a source, never covers a
    # failed transport/parse, and never reconciles an observed model the
    # parsed bytes do not support. Supplied bundles (no collection identity)
    # keep the 180 offline-replay semantics exactly.
    collection = bundle.collection
    collection_inventory_verified: dict[tuple[str, str], str] = {}
    collection_report: dict[str, Any] = {}
    if collection is not None:
        retrieval_by_url: dict[str, Any] = {}
        failed_retrieval_urls: set[str] = set()
        for record in collection.retrievals:
            if record.outcome == "ok":
                retrieval_by_url[record.requested_url] = record
            else:
                failed_retrieval_urls.add(record.requested_url)
        for source in bundle.sources:
            record = retrieval_by_url.get(source.url)
            if record is None or record.content_sha256 != source.content_sha256:
                add(
                    SEVERITY_BLOCKER,
                    "collection_source_unbacked",
                    f"source {source.provider}|{source.model}|{source.source_kind} has no successful "
                    "retrieval record with a matching content digest in the collection identity",
                    source.provider,
                    source.model,
                )
        _catalog_url_by_provider = {
            "openrouter": _source_registry.OPENROUTER_MODELS_URL,
            "openai": _source_registry.OPENAI_PRICING_MD_URL,
        }
        for provider in collection.providers:
            catalog_url = _catalog_url_by_provider.get(provider)
            if catalog_url is not None and catalog_url not in retrieval_by_url:
                state = "failed" if catalog_url in failed_retrieval_urls else "absent"
                add(
                    SEVERITY_BLOCKER,
                    "collection_retrieval_failed",
                    f"provider catalog retrieval for {provider} is {state}; a source outage is a "
                    "retrieval failure, not model disappearance, and an empty bootstrap is never READY",
                    provider,
                    None,
                )
        # 181-b (B1): a live collection that fetched its sources but
        # produced NO usable proposal is not a ready bootstrap: every
        # observed model was excluded, and publishing an empty proposal as
        # READY would let an all-ineligible catalog masquerade as a
        # successful collection. (A refresh against an existing baseline
        # may legitimately propose nothing while retaining every baseline
        # model; that no-op is accounted per model above.)
        if (
            baseline is None
            and not bundle.routes
            and not bundle.pricing
            and not bundle.models
        ):
            add(
                SEVERITY_BLOCKER,
                "collection_empty_bootstrap",
                "collection fetched official sources but proposed no model, route, or "
                "pricing; an empty usable bootstrap is never READY",
                None,
                None,
            )
        # Evidence rows per provider: the shared official_rows built above
        # (all kept rows, for claim verification).
        evidence_rows = official_rows
        baseline_model_keys_all = set(baseline_model_keys)
        # 181-b (B2): upstream-keyed baseline indexes for retention claim
        # verification (the collector keys retention entries by upstream
        # identity; public aliases resolve through these rows).
        baseline_chat_rows_by_upstream: dict[tuple[str, str], list[Any]] = {}
        baseline_wildcard_route_rows: list[Any] = []
        baseline_pricing_rows_by_upstream: dict[tuple[str, str], list[Any]] = {}
        if baseline is not None:
            for row in baseline.routes:
                if row.endpoint != CHAT_ENDPOINT:
                    continue
                if row.match_type == "exact":
                    baseline_chat_rows_by_upstream.setdefault(
                        (row.provider, row.upstream_model), []
                    ).append(row)
                else:
                    baseline_wildcard_route_rows.append(row)
            for row in baseline.pricing:
                if row.endpoint == CHAT_ENDPOINT:
                    baseline_pricing_rows_by_upstream.setdefault(
                        (row.provider, row.upstream_model), []
                    ).append(row)
        unverified_inventory: list[str] = []
        for entry in collection.inventory:
            provider, model_id = entry.provider, entry.model
            rows = evidence_rows.get(provider, {}).get(model_id, [])
            em = rows[-1] if rows else None
            verified = False
            if entry.disposition == "retained_local":
                verified = (provider, model_id) in baseline_model_keys_all
            elif entry.disposition == "deprecated":
                verified = em is not None and em.deprecated is True
            elif entry.disposition == "unsupported":
                verified = em is not None and em.text_modality is not True
            elif entry.disposition == "excluded_subset":
                if entry.reason_code == "explicit_selection_excluded":
                    verified = (
                        bool(bundle.selection.model_include)
                        and model_id not in set(bundle.selection.model_include)
                    )
                elif entry.reason_code == "service_variant":
                    verified = model_id.endswith(":batch")
                elif entry.reason_code in se.BILLING_EXCLUSION_REASONS:
                    # 181-b (B1): billing-exclusion claims are recomputed
                    # with the SAME shared policy over the parsed rows.
                    decision = (
                        se.standard_v1_billing_decision(provider, rows) if rows else None
                    )
                    verified = (
                        decision is not None
                        and not decision.eligible
                        and decision.reason_code == entry.reason_code
                    )
                elif entry.reason_code == "price_below_quantum":
                    decision = (
                        se.standard_v1_billing_decision(provider, rows) if rows else None
                    )
                    verified = decision is not None and decision.eligible and any(
                        Decimal(value).quantize(
                            Decimal("0.000000001"), rounding=ROUND_HALF_UP
                        )
                        == 0
                        for _dim, value, _unit in decision.carried
                    )
                elif entry.reason_code == "baseline_contract_not_flat":
                    # 181-b (B2): upstream-keyed - exactly one non-flat
                    # exact row, or a covering prefix/glob baseline route.
                    exact_here = baseline_chat_rows_by_upstream.get(
                        (provider, model_id), []
                    )
                    if len(exact_here) == 1:
                        verified = not _baseline_route_flat_capable(exact_here[0])
                    else:
                        verified = any(
                            row.provider == provider
                            and (
                                (
                                    row.match_type == "prefix"
                                    and model_id.startswith(row.requested_model)
                                )
                                or (
                                    row.match_type == "glob"
                                    and fnmatchcase(model_id, row.requested_model)
                                )
                            )
                            for row in baseline_wildcard_route_rows
                        )
                elif entry.reason_code == "baseline_multiple_routes":
                    verified = len(
                        baseline_chat_rows_by_upstream.get((provider, model_id), [])
                    ) >= 2
                elif entry.reason_code == "baseline_currency_mismatch":
                    currencies = {
                        row.currency
                        for row in baseline_pricing_rows_by_upstream.get(
                            (provider, model_id), []
                        )
                    }
                    verified = bool(currencies) and currencies != {"USD"}
                else:
                    verified = False
            elif entry.disposition == "incomplete":
                if em is None:
                    verified = False
                elif entry.reason_code == "negative_router_sentinel":
                    verified = bool({"input", "output"} & set(em.non_representable_prices))
                elif entry.reason_code == "missing_limits":
                    verified = em.context_length is None or em.max_output_tokens is None
                elif entry.reason_code == "missing_core_prices":
                    verified = not {"input", "output"} <= set(em.prices)
                elif entry.reason_code == "no_standard_short_prices":
                    verified = not any(
                        row.billing_tier in (None, "standard")
                        and row.context_band in (None, "short")
                        and {"input", "output"} <= set(row.prices)
                        for row in rows
                    )
                elif entry.reason_code == "index_only_no_standard_prices":
                    # 181-b (B3): the ID is listed by the official models
                    # index (identity-only observation) and carries no
                    # standard short-context pricing rows.
                    verified = any(row.identity_only for row in rows) and not any(
                        row.billing_tier in (None, "standard")
                        and row.context_band in (None, "short")
                        and {"input", "output"} <= set(row.prices)
                        for row in rows
                    )
                elif entry.reason_code in (
                    "page_unavailable",
                    "page_parse_failed",
                    "page_model_mismatch",
                ):
                    verified = model_id not in page_ok_models
                elif entry.reason_code == "page_no_chat":
                    page = page_rows.get(model_id)
                    verified = page is not None and page.chat_supported is not True
                elif entry.reason_code == "page_no_text":
                    page = page_rows.get(model_id)
                    verified = page is not None and page.text_modality is not True
                elif entry.reason_code == "page_price_conflict":
                    page = page_rows.get(model_id)
                    verified = False
                    if page is not None:
                        for row in rows:
                            if row.billing_tier in (None, "standard") and row.context_band in (None, "short"):
                                for dim in ("input", "output", "cached_input"):
                                    page_value = page.prices.get(dim)
                                    row_value = row.prices.get(dim)
                                    if (
                                        page_value is not None
                                        and row_value is not None
                                        and page_value != row_value
                                    ):
                                        verified = True
                                        break
                            if verified:
                                break
                else:
                    verified = False
            else:  # unresolved: reconciled only when the model was not observed
                verified = em is None
            if verified:
                collection_inventory_verified[(provider, model_id)] = entry.disposition
            else:
                unverified_inventory.append(f"{provider}/{model_id} ({entry.reason_code})")
        if unverified_inventory:
            add(
                SEVERITY_BLOCKER,
                "collection_inventory_unsupported",
                f"{len(unverified_inventory)} collection inventory entr(ies) are not supported by the "
                "parsed official evidence or the baseline: "
                + ", ".join(sorted(unverified_inventory)[:8])
                + ("" if len(unverified_inventory) <= 8 else f" (+{len(unverified_inventory) - 8} more)"),
                None,
                None,
            )
        collection_report = {
            "tool": collection.tool,
            "code_revision": collection.code_revision,
            "profile": collection.profile,
            "providers": list(collection.providers),
            "model_include": list(collection.model_include),
            "started_at": collection.started_at.isoformat(),
            "finished_at": collection.finished_at.isoformat(),
            "retrievals_total": len(collection.retrievals),
            "retrievals_ok": sum(1 for r in collection.retrievals if r.outcome == "ok"),
            "retrievals_failed": sum(1 for r in collection.retrievals if r.outcome == "failed"),
            "failed_retrievals": sorted(failed_retrieval_urls),
            "deduplicated_fetches": collection.deduplicated_fetches,
            "inventory_entries": len(collection.inventory),
            "inventory_by_reason": {
                reason: sum(1 for e in collection.inventory if e.reason_code == reason)
                for reason in sorted({e.reason_code for e in collection.inventory})
            },
            "inventory_unverified": len(unverified_inventory),
            "source_model_counts": {
                provider: count
                for provider, count in sorted(collection.source_model_counts.items())
            },
        }

    selected_by_provider: dict[str, set[str]] = {}
    for provider, model in selected:
        selected_by_provider.setdefault(provider, set()).add(model)
    # 181-b (B2): an evidence ID proposed under a public alias is covered
    # by that route's upstream identity (the alias IS the local identity).
    proposed_upstreams_by_provider: dict[str, set[str]] = {}
    for route in bundle.routes:
        if route.match_type == "exact" and route.endpoint == CHAT_ENDPOINT:
            proposed_upstreams_by_provider.setdefault(route.provider, set()).add(
                route.upstream_model
            )

    def _covered_by_proposal(provider: str, model_id: str) -> bool:
        return model_id in proposed_upstreams_by_provider.get(provider, set())

    explicit_subset = bool(bundle.selection.model_include)
    inventory: dict[str, dict[str, Any]] = {}
    unexplained_omissions: list[str] = []
    for provider in sorted(selection_providers & (set(evidence_ids_by_provider) | set(selected_by_provider))):
        ids = evidence_ids_by_provider.get(provider, {})
        sel = selected_by_provider.get(provider, set())
        prov_counts = {
            "evidence_models": len(ids),
            "selected_models": sum(
                1 for mid in ids if mid in sel or _covered_by_proposal(provider, mid)
            ),
            "retained_local_models": 0,
            "explicitly_excluded_models": 0,
            "unsupported_excluded_models": 0,
            "unexplained_omissions": 0,
        }
        retained_ids: list[str] = []
        excluded_ids: list[str] = []
        for mid in sorted(ids):
            if mid in sel or _covered_by_proposal(provider, mid):
                continue
            if (provider, mid) in baseline_model_keys:
                prov_counts["retained_local_models"] += 1
                retained_ids.append(mid)
            elif (provider, mid) in collection_inventory_verified:
                # 181: an evidence-verified collection inventory entry
                # reconciles the observed model (its claim was re-checked
                # against the parsed bytes above, never trusted raw).
                disposition = collection_inventory_verified[(provider, mid)]
                if disposition == "excluded_subset":
                    prov_counts["explicitly_excluded_models"] += 1
                else:
                    prov_counts["unsupported_excluded_models"] += 1
                excluded_ids.append(mid)
            elif explicit_subset:
                prov_counts["explicitly_excluded_models"] += 1
                excluded_ids.append(mid)
            elif ids[mid].text_modality is not True:
                prov_counts["unsupported_excluded_models"] += 1
                excluded_ids.append(mid)
            else:
                prov_counts["unexplained_omissions"] += 1
                unexplained_omissions.append(f"{provider}/{mid}")
        inventory[provider] = {
            **prov_counts,
            "selection_mode": "explicit_subset" if explicit_subset else "all_eligible",
            "retained_local_ids": retained_ids[:16],
            "excluded_ids": excluded_ids[:16],
        }
    if unexplained_omissions:
        add(
            SEVERITY_BLOCKER,
            "selection_unexplained_omission",
            f"{len(unexplained_omissions)} eligible model(s) present in official snapshots are neither proposed, "
            "explicitly excluded by a subset, nor retained from baseline: "
            + ", ".join(sorted(unexplained_omissions)[:8])
            + ("" if len(unexplained_omissions) <= 8 else f" (+{len(unexplained_omissions) - 8} more)"),
            None,
            None,
        )
    live_collection = bundle.collection is not None
    source_evidence_report: dict[str, Any] = {
        "scope": "live_collection" if live_collection else "offline_replay",
        "note": (
            "live collection performed by this invocation: sources were fetched "
            "with bounded official retrieval and parsed with registered "
            "deterministic parsers; retrieval outcomes are recorded in the "
            "collection identity"
            if live_collection
            else "supplied/cached snapshot bytes were parsed offline with registered "
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
    if live_collection:
        source_evidence_report["collection"] = collection_report

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
            "capture": sql_capture,
            "sql_executed_during_review": sql_capture == SQL_CAPTURE_LIVE_EXPORT,
            "note": _SQL_CAPTURE_NOTES[sql_capture],
        },
        baseline_metadata=baseline_metadata_rows,
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
        # 180-f (F4): calendar-day basis (UTC publication date vs UTC
        # review reference date); the time-of-day never changes the state.
        calendar_age_days = (_utc(now).date() - _utc(facts.published_at).date()).days
        state = policy.fx_age_state(calendar_age_days)
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
        # 180-e (E2): the runtime looks up native -> EUR directly; only a
        # direct active baseline row is the current rate. An inverse-only
        # baseline is reported as such (REVIEW), never silently reciprocated
        # into a before/after comparison.
        current_rate = Decimal(base_direct.rate) if base_direct is not None else None
        if current_rate is None and inverse is not None:
            fx_add(
                SEVERITY_REVIEW,
                "fx_baseline_inverse_only",
                f"baseline holds only the inverse EUR\u2192{currency} pair; the runtime looks up "
                f"{currency}\u2192EUR directly, so the proposed rate compares as NEW, not as a change",
            )
        if base_direct_ambiguous or inverse_ambiguous:
            fx_add(SEVERITY_BLOCKER, "fx_baseline_ambiguous", f"ambiguous active baseline FX rows around {currency}/EUR")
        delta_pct = None
        state = "NEW"
        if current_rate is not None and current_rate > 0:
            delta_pct = str(((normalized_rate - current_rate) / current_rate).quantize(Decimal("0.000000001")))
            # 180-f (F4): exact pre-rounding comparison (cross-multiplied);
            # the quantized delta_pct is display formatting only.
            if abs(normalized_rate - current_rate) > policy.fx_change_review * current_rate:
                fx_add(SEVERITY_REVIEW, "fx_moved_review", f"{currency}→EUR moved {delta_pct} (policy {policy.fx_change_review})")
                state = "CHANGED_REVIEW"
            elif normalized_rate != current_rate:
                state = "CHANGED"
            else:
                state = "UNCHANGED"
        comparison = {
            "pair": f"{currency}→EUR",
            "current_rate": None if current_rate is None else str(current_rate),
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
    *,
    sql_capture: str,
) -> tuple[ValidationReport, dict[str, bytes]]:
    """Public entry: mode-consistent validation (first install must have no baseline).

    ``sql_capture`` must name the actual path that produced or supplied the
    baseline for this review; consistency with the declared mode is enforced
    inside :func:`validate_bundle` (180-e).
    """
    return validate_bundle(bundle, baseline, policy, sql_capture=sql_capture)
