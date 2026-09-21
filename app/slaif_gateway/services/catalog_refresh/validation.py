"""Deterministic readiness, completeness, and validator recomputation.

Everything reported as state, count, or evidence is recomputed here from the
normalized bundle, the baseline rows, and the exact generated artifact bytes.
No caller-supplied readiness, confidence, or counters are ever trusted.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from slaif_gateway.schemas.catalog_refresh import (
    CAPABILITY_KEYS,
    BaselineDocument,
    RefreshBundle,
)
from slaif_gateway.services.catalog_refresh.bundle import (
    generate_fx_json,
    generate_pricing_tsv,
    generate_route_tsv,
    selected_model_keys,
)
from slaif_gateway.services.catalog_refresh.errors import CatalogRefreshBlockedError
from slaif_gateway.services.catalog_refresh.policy import RefreshPolicy
from slaif_gateway.services.fx_import import (
    build_fx_import_execution_plan,
    classify_fx_import_preview,
    parse_fx_import_json,
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

    def to_dict(self) -> dict[str, Any]:
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
                for gate in sorted(self.gates, key=lambda g: g.name)
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
                }
                for gate in sorted(self.import_gates, key=lambda g: g.kind)
            ],
            "baseline": dict(sorted(self.baseline.items())),
            "research": dict(sorted(self.research.items())),
            "artifacts": dict(sorted(self.artifacts.items())),
            "sql_checks": dict(sorted(self.sql_checks.items())),
        }


def validation_json_bytes(report: ValidationReport) -> bytes:
    """Exact canonical encoding shared by the CLI writer and the verifier."""
    import json

    return (json.dumps(report.to_dict(), sort_keys=True, indent=1, default=str) + "\n").encode("utf-8")


def _utc(value: datetime) -> datetime:
    return value.astimezone(UTC)


def _pct(old: Decimal, new: Decimal) -> str:
    delta = abs(new - old) / old
    return str(delta.quantize(Decimal("0.000001")))


def _latest_active(rows, now: datetime):
    active = [row for row in rows if _utc(row.valid_from) <= now and (row.valid_until is None or _utc(row.valid_until) > now)]
    pool = active or list(rows)
    if not pool:
        return None
    return max(pool, key=lambda row: _utc(row.valid_from))


def validate_bundle(
    bundle: RefreshBundle,
    baseline: BaselineDocument | None,
    policy: RefreshPolicy,
) -> tuple[ValidationReport, dict[str, bytes]]:
    """Recompute the full review result. Pure and deterministic."""
    warnings: list[Warning] = []
    blockers: list[str] = []
    now = _utc(bundle.generated_at)
    selected = selected_model_keys(bundle)

    def add(severity: str, code: str, detail: str, provider: str | None = None, model: str | None = None) -> None:
        warnings.append(Warning(severity, code, provider, model, detail))
        if severity == SEVERITY_BLOCKER:
            blockers.append(code)

    # --- baseline indexes -------------------------------------------------
    baseline_routes_by_model: dict[tuple[str, str], list[Any]] = {}
    baseline_pricing_by_key: dict[tuple[str, str, str], list[Any]] = {}
    baseline_fx_by_pair: dict[tuple[str, str], list[Any]] = {}
    baseline_provider_names: set[str] = set()
    if baseline is not None:
        for row in baseline.routes:
            baseline_routes_by_model.setdefault((row.provider, row.requested_model), []).append(row)
        for row in baseline.pricing:
            baseline_pricing_by_key.setdefault((row.provider, row.upstream_model, row.endpoint), []).append(row)
        for row in baseline.fx:
            baseline_fx_by_pair.setdefault((row.base_currency, row.quote_currency), []).append(row)
        baseline_provider_names = {row.provider for row in baseline.providers}

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

    models_by_key = {(item.provider, item.model): item for item in bundle.models}
    pricing_by_key: dict[tuple[str, str], Any] = {}
    for item in bundle.pricing:
        pricing_by_key[(item.provider, item.model)] = item
    routes_by_key: dict[tuple[str, str], Any] = {}
    for item in bundle.routes:
        routes_by_key[(item.provider, item.requested_model)] = item
    sources_by_key: dict[tuple[str, str], list[Any]] = {}
    for source in bundle.sources:
        sources_by_key.setdefault((source.provider, source.model), []).append(source)

    # --- out-of-scope facts are counted explicitly, never silently dropped
    out_of_scope = sum(
        1
        for item in (*bundle.models, *bundle.pricing, *bundle.routes)
        if (getattr(item, "provider"), getattr(item, "model", None) or getattr(item, "requested_model")) not in selected
    )

    # --- per-selected-model dispositions ----------------------------------
    dispositions: list[Disposition] = []
    price_comparisons: list[PriceComparison] = []
    per_provider: dict[str, dict[str, int]] = {}
    unsupported_excluded: list[str] = []
    missing_required_dimensions: list[str] = []

    def bump(provider: str, key: str) -> None:
        per_provider.setdefault(provider, {})
        per_provider[provider][key] = per_provider[provider].get(key, 0) + 1

    for provider, model in sorted(selected):
        facts = models_by_key.get((provider, model))
        route = routes_by_key.get((provider, model))
        pricing = pricing_by_key.get((provider, model))
        model_sources = sources_by_key.get((provider, model), [])
        truncated_required = any(source.truncated for source in model_sources if source.required)
        truncated_optional = any(source.truncated for source in model_sources if not source.required)
        in_baseline = (provider, model) in baseline_routes_by_model or any(
            p == provider and m == model for (p, m, _endpoint) in baseline_pricing_by_key
        )

        # source completeness for this model
        source_failed = truncated_required or (bool(in_baseline) and not model_sources)
        if truncated_optional:
            add(SEVERITY_REVIEW, "source_truncated_optional", "an optional source for this model was truncated", provider, model)
        for source in model_sources:
            age = now - _utc(source.retrieved_at)
            if age < timedelta(0):
                add(SEVERITY_BLOCKER, "future_source_timestamp", "retrieved_at is after generated_at", provider, model)
            else:
                state = policy.source_age_state(age)
                if state == "review":
                    add(SEVERITY_REVIEW, "source_stale_review", f"source age {age} exceeds review threshold", provider, model)
                elif state == "blocked":
                    add(SEVERITY_BLOCKER, "source_stale_blocked", f"source age {age} exceeds blocked threshold", provider, model)
            for warning in source.warnings:
                add(SEVERITY_REVIEW, "source_warning", warning, provider, model)

        if facts is None and route is None and pricing is None:
            explicitly_selected = model in bundle.selection.model_include
            if in_baseline:
                if source_failed:
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
                    dispositions.append(Disposition(provider, model, DISPOSITION_DISAPPEARED, "in baseline but absent from complete sources; retain-local, no delete semantics in 180"))
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
            add(
                SEVERITY_BLOCKER,
                "source_truncated_blocked",
                "a required source for this model is truncated; its required import plan is blocked",
                provider,
                model,
            )
            dispositions.append(Disposition(provider, model, DISPOSITION_BLOCKED, "required source truncated; import plan blocked"))
            bump(provider, "blocked")
            continue

        if facts is not None and facts.deprecated:
            dispositions.append(Disposition(provider, model, DISPOSITION_DEPRECATED, "source marks model deprecated; retain-local, no delete semantics in 180"))
            bump(provider, "deprecated")
            add(SEVERITY_REVIEW, "model_deprecated", "model marked deprecated by source", provider, model)
            continue

        # capability widening rejection (standard v1 profile)
        capabilities = (facts.capabilities if facts is not None else {})
        if route is not None:
            capabilities = {**capabilities, **route.capabilities}
        unsupported = [key for key in capabilities if key not in CAPABILITY_KEYS]
        if unsupported:
            unsupported_excluded.append(f"{provider}/{model}:{','.join(sorted(unsupported))}")
            add(SEVERITY_REVIEW, "unsupported_capability_excluded", f"capability outside standard v1 profile: {','.join(sorted(unsupported))}", provider, model)
            dispositions.append(Disposition(provider, model, DISPOSITION_EXCLUDED, f"unsupported capability: {','.join(sorted(unsupported))}"))
            bump(provider, "excluded")
            continue

        # route facts required for any priced or fact-bearing model
        if route is None:
            add(SEVERITY_BLOCKER, "missing_route", "selected model has facts or pricing but no route proposal", provider, model)
            dispositions.append(Disposition(provider, model, DISPOSITION_BLOCKED, "no route proposal"))
            bump(provider, "blocked")
            continue

        # pricing required for selected chat text models
        if pricing is None:
            add(SEVERITY_BLOCKER, "missing_pricing", "selected model has a route but no pricing proposal", provider, model)
            dispositions.append(Disposition(provider, model, DISPOSITION_BLOCKED, "no pricing proposal"))
            bump(provider, "blocked")
            continue

        old_rules = baseline_pricing_by_key.get((provider, route.upstream_model, route.endpoint), [])
        old_pricing = _latest_active(
            [r for r in old_rules if r.currency == pricing.currency],
            now,
        )
        old_pricing_any = _latest_active(list(old_rules), now)
        currency_conflict = (
            old_pricing_any is not None and old_pricing_any.currency != pricing.currency
        )
        if currency_conflict:
            add(
                SEVERITY_BLOCKER,
                "currency_inconsistency",
                f"baseline {old_pricing_any.currency} vs proposed {pricing.currency}",
                provider,
                model,
            )
        old_route = None
        for candidate in baseline_routes_by_model.get((provider, route.requested_model), []):
            if candidate.match_type == route.match_type and candidate.endpoint == route.endpoint and candidate.provider == route.provider:
                old_route = candidate
                break

        changed_fields: list[str] = []
        if old_route is None:
            if old_pricing is None:
                disposition = DISPOSITION_NEW
            else:
                disposition = DISPOSITION_NEW
                changed_fields.append("route")
        else:
            for attr in ("upstream_model", "priority", "enabled", "visible_in_models", "supports_streaming", "match_type"):
                new_value = getattr(route, attr)
                old_value = getattr(old_route, attr)
                if attr == "capabilities":
                    new_value = route.capabilities or {}
                    old_value = old_route.capabilities or {}
                elif isinstance(new_value, bool):
                    old_value = bool(old_value)
                if new_value != old_value:
                    changed_fields.append(attr)

        # pricing dimension comparison
        old_dims: dict[str, tuple[Decimal, str]] = {}
        old_currency: str | None = None
        if old_pricing is not None:
            old_currency = old_pricing.currency
            old_dims = {
                name: (Decimal(value), old_pricing.currency)
                for name, value in (
                    ("input", old_pricing.input_price_per_1m),
                    ("cached_input", old_pricing.cached_input_price_per_1m),
                    ("output", old_pricing.output_price_per_1m),
                    ("reasoning", old_pricing.reasoning_price_per_1m),
                    ("request", old_pricing.request_price),
                )
                if value is not None
            }
        if currency_conflict:
            changed_fields.append("pricing.currency")
        _DIMENSION_ATTRIBUTE = {
            "input": "input_price_per_1m",
            "cached_input": "cached_input_price_per_1m",
            "output": "output_price_per_1m",
            "reasoning": "reasoning_price_per_1m",
            "request": "request_price",
        }
        for dimension in pricing.dimensions:
            new_value = None if dimension.value is None else Decimal(dimension.value)
            if dimension.value is not None and not Decimal(dimension.value).is_finite():
                add(SEVERITY_BLOCKER, "non_finite_price", f"dimension {dimension.name} is non-finite", provider, model)
            if dimension.name not in {"input", "output", "cached_input", "reasoning", "request"}:
                add(SEVERITY_BLOCKER, "unknown_unit", f"unknown unit {dimension.unit}", provider, model)
            if currency_conflict:
                old_any_value = None
                if old_pricing_any is not None:
                    raw = getattr(old_pricing_any, _DIMENSION_ATTRIBUTE[dimension.name])
                    old_any_value = None if raw is None else str(raw)
                price_comparisons.append(
                    PriceComparison(
                        provider=provider,
                        model=model,
                        dimension=dimension.name,
                        old=old_any_value,
                        new=None if new_value is None else str(new_value),
                        currency_old=old_pricing_any.currency if old_pricing_any is not None else None,
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
                old_value, _currency = old_entry
                if old_value == 0 and new_value > 0 or old_value > 0 and new_value == 0:
                    comparison_state = "ZERO_TRANSITION"
                    add(SEVERITY_REVIEW, "price_zero_transition", f"{dimension.name} crossed zero (old={old_value}, new={new_value})", provider, model)
                elif old_value != 0:
                    percent = _pct(old_value, new_value)
                    if Decimal(percent) > policy.price_change_review:
                        comparison_state = "CHANGED_REVIEW"
                        add(SEVERITY_REVIEW, "price_moved_review", f"{dimension.name} moved {percent} (> policy {policy.price_change_review})", provider, model)
                    else:
                        comparison_state = "CHANGED" if old_value != new_value else "UNCHANGED"
                if comparison_state in ("CHANGED", "CHANGED_REVIEW", "ZERO_TRANSITION", "NEW", "REMOVED"):
                    changed_fields.append(f"pricing.{dimension.name}")
            price_comparisons.append(
                PriceComparison(
                    provider=provider,
                    model=model,
                    dimension=dimension.name,
                    old=None if old_entry is None else str(old_entry[0]),
                    new=None if new_value is None else str(new_value),
                    currency_old=old_currency if old_entry is not None else None,
                    currency_new=dimension.currency,
                    percent_change=percent,
                    state=comparison_state,
                )
            )
        dimension_blocked = False
        for required in ("input", "output"):
            if all(dimension.value is None for dimension in pricing.dimensions if dimension.name == required):
                dimension_blocked = True
                missing_required_dimensions.append(f"{provider}/{model}:{required}")
                add(SEVERITY_BLOCKER, "missing_required_dimension", f"required {required} price is missing", provider, model)

        if dimension_blocked:
            disposition = DISPOSITION_BLOCKED
            disposition_detail = "missing required pricing dimension(s); import plan blocked"
        elif not old_route and old_pricing is None and not changed_fields:
            disposition = DISPOSITION_NEW
            disposition_detail = "no baseline row for this model"
        elif changed_fields:
            disposition = DISPOSITION_CHANGED
            disposition_detail = "; ".join(sorted(set(changed_fields)))
        else:
            disposition = DISPOSITION_UNCHANGED
            disposition_detail = "all compared fields identical"
        bump(provider, disposition.lower())
        dispositions.append(
            Disposition(provider, model, disposition, disposition_detail)
        )

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

    # --- counts (recomputed, identity-enforced) ---------------------------
    disposition_counts: dict[str, int] = {}
    for item in dispositions:
        disposition_counts[item.disposition] = disposition_counts.get(item.disposition, 0) + 1
    new_count = disposition_counts.get(DISPOSITION_NEW, 0)
    changed_count = disposition_counts.get(DISPOSITION_CHANGED, 0)
    unchanged_count = disposition_counts.get(DISPOSITION_UNCHANGED, 0)
    excluded_count = disposition_counts.get(DISPOSITION_EXCLUDED, 0)
    blocked_count = disposition_counts.get(DISPOSITION_BLOCKED, 0)
    ready_count = new_count + changed_count + unchanged_count
    considered_count = ready_count + excluded_count + blocked_count + disposition_counts.get(DISPOSITION_NOT_FETCHED, 0)
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
    if considered_count != counts["ready"] + excluded_count + blocked_count + counts["not_fetched"]:
        raise CatalogRefreshBlockedError("count_identity_violation", "considered != ready + excluded + blocked + not_fetched")

    # --- authoritative contradiction: two authoritative sources disagree --
    for provider, model in sorted(selected):
        field_values: dict[str, dict[str, str]] = {}
        for source in sources_by_key.get((provider, model), []):
            key = f"{provider}|{model}|{source.source_kind}"
            for item in (*bundle.models, *bundle.pricing, *bundle.routes):
                item_model = getattr(item, "model", None) or getattr(item, "requested_model")
                if getattr(item, "provider") != provider or item_model != model:
                    continue
                for source_ref in item.provenance.sources:
                    if source_ref == key:
                        for value_name, value in (
                            ("context_length", str(getattr(item, "context_length", None) or "")),
                        ):
                            field_values.setdefault(value_name, {})[key] = value
        for value_name, values in field_values.items():
            distinct = set(values.values()) - {""}
            if len(distinct) > 1:
                add(SEVERITY_BLOCKER, "authoritative_contradiction", f"sources disagree on {value_name}", provider, model)

    # --- artifacts via the real import parsers ----------------------------
    route_tsv = generate_route_tsv(bundle, selected)
    pricing_tsv = generate_pricing_tsv(bundle, selected)
    fx_json = generate_fx_json(bundle)

    route_gate = _run_route_gate(bundle, baseline, route_tsv, now, baseline_provider_names)
    pricing_gate = _run_pricing_gate(baseline, pricing_tsv, now)
    fx_required_currencies = {
        item.currency for item in bundle.pricing if (item.provider, item.model) in selected
    } - {"EUR"}
    fx_gate = _run_fx_gate(baseline, bundle, fx_json, now, fx_required_currencies, policy, add)

    # pairing gate
    priced_keys = {(item.provider, item.model) for item in bundle.pricing if (item.provider, item.model) in selected}
    routed_keys = {(item.provider, item.requested_model) for item in bundle.routes if (item.provider, item.requested_model) in selected}
    unpaired_pricing = sorted(priced_keys - routed_keys)
    if unpaired_pricing:
        for provider, model in unpaired_pricing:
            add(SEVERITY_BLOCKER, "unpaired_pricing", "pricing proposal without a matching route proposal", provider, model)
    pairing_detail = "every priced selected model has a matching route identity" if not unpaired_pricing else f"{len(unpaired_pricing)} unpaired pricing rows"

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

    gates: list[Gate] = []
    if unpaired_pricing:
        gates.append(Gate("pairing", EVIDENCE_BLOCKED, pairing_detail))
    else:
        gates.append(Gate("pairing", EVIDENCE_VERIFIED, pairing_detail))
    gates.append(Gate("unsupported", unsupported_evidence, unsupported_detail))
    if counts["blocked"]:
        gates.append(Gate("completeness", EVIDENCE_BLOCKED, f"{counts['blocked']} selected models blocked"))
    elif counts["excluded"]:
        gates.append(Gate("completeness", EVIDENCE_REVIEW, f"{counts['excluded']} selected models excluded"))
    else:
        gates.append(Gate("completeness", EVIDENCE_VERIFIED, "all selected models accounted"))
    gates.extend(route_gate.gates)
    gates.extend(pricing_gate.gates)
    gates.extend(fx_gate.gates)
    import_gates = [route_gate.import_gate, pricing_gate.import_gate, fx_gate.import_gate]

    # --- overall state ------------------------------------------------------
    gate_blocked = [gate for gate in gates if gate.evidence == EVIDENCE_BLOCKED]
    review_warnings = [warning for warning in warnings if warning.severity != SEVERITY_INFO]
    if gate_blocked or blockers:
        state = OVERALL_BLOCKED
        state_reason = "blocked by: " + ", ".join(sorted({gate.name for gate in gate_blocked} | set(blockers)))
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
            "note": "baseline SQL checked via read-only consistent export" if baseline is not None and baseline.sql_checked else "no SQL checked (first-install or offline export file without DB access)",
        },
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


def _provider_refs(bundle: RefreshBundle, baseline: BaselineDocument | None, baseline_provider_names: set[str]) -> list[RouteImportProviderRef]:
    refs: dict[str, RouteImportProviderRef] = {}
    if baseline is not None:
        for row in baseline.providers:
            if row.provider in baseline_provider_names:
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


def _run_route_gate(bundle, baseline, tsv_bytes: bytes, now: datetime, baseline_provider_names: set[str]) -> _GateBundle:
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
        result.import_gate = ImportGate("routes", False, 0, 0, 0, {}, 0, 0, schema_error)
        return result
    refs = _provider_refs(bundle, baseline, baseline_provider_names)
    preview = validate_route_import_rows(rows, provider_configs=refs, max_rows=max(len(rows), 1))
    existing_by_row: dict[int, list[Any]] = {}
    if baseline is not None:
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
    detail_parts = [f"{len(rows)} rows, {len(invalid)} invalid, {len(non_create)} non-create (apply NOT_SUPPORTED until 182)"]
    if invalid:
        result.gates.append(Gate(ROUTE_GATE, EVIDENCE_BLOCKED, f"{len(invalid)} route rows invalid: {invalid[0].errors[0][:200]}"))
    elif non_create:
        result.gates.append(Gate(ROUTE_GATE, EVIDENCE_REVIEW, f"{len(non_create)} existing-row changes represented; apply plan blocked until 182"))
    elif plan.executable:
        result.gates.append(Gate(ROUTE_GATE, EVIDENCE_VERIFIED, "route TSV valid; create-only plan executable"))
    elif rows:
        result.gates.append(Gate(ROUTE_GATE, EVIDENCE_REVIEW, "route TSV valid; plan not executable"))
    else:
        result.gates.append(Gate(ROUTE_GATE, EVIDENCE_VERIFIED, "no route rows proposed (NO CHANGES)"))
    result.import_gate = ImportGate(
        "routes",
        schema_valid,
        len(rows),
        classified.valid_count,
        classified.invalid_count,
        _classification_counts(classified),
        plan.executable_count,
        plan.blocked_count,
        "; ".join(detail_parts),
    )
    return result


def _run_pricing_gate(baseline, tsv_bytes: bytes, now: datetime) -> _GateBundle:
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
        result.import_gate = ImportGate("pricing", False, 0, 0, 0, {}, 0, 0, schema_error)
        return result
    preview = validate_pricing_import_rows(rows, max_rows=max(len(rows), 1))
    existing_by_row: dict[int, list[Any]] = {}
    if baseline is not None:
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
        result.gates.append(Gate(PRICING_GATE, EVIDENCE_REVIEW, f"{len(non_create)} existing-window changes represented; apply plan blocked until 182"))
    elif plan.executable:
        result.gates.append(Gate(PRICING_GATE, EVIDENCE_VERIFIED, "pricing TSV valid; create-only plan executable"))
    elif rows:
        result.gates.append(Gate(PRICING_GATE, EVIDENCE_REVIEW, "pricing TSV valid; plan not executable"))
    else:
        result.gates.append(Gate(PRICING_GATE, EVIDENCE_VERIFIED, "no pricing rows proposed (NO CHANGES)"))
    result.import_gate = ImportGate(
        "pricing",
        schema_valid,
        len(rows),
        classified.valid_count,
        classified.invalid_count,
        _classification_counts(classified),
        plan.executable_count,
        plan.blocked_count,
        f"{len(rows)} rows, {len(invalid)} invalid, {len(non_create)} non-create",
    )
    return result


def _run_fx_gate(baseline, bundle, fx_bytes: bytes, now: datetime, required_currencies: set[str], policy: RefreshPolicy, add) -> _GateBundle:
    result = _GateBundle()
    if not required_currencies and not bundle.fx:
        result.gates.append(Gate(FX_GATE, EVIDENCE_NA, "all selected prices are EUR; FX is N/A"))
        result.import_gate = ImportGate("fx", True, 0, 0, 0, {}, 0, 0, "N/A: every selected price is EUR")
        return result
    text_payload = fx_bytes.decode("utf-8")
    try:
        rows = parse_fx_import_json(text_payload)
        schema_valid = True
        schema_error = ""
    except ValueError as exc:
        rows = []
        schema_valid = False
        schema_error = str(exc)
    if not schema_valid:
        result.gates.append(Gate(FX_GATE, EVIDENCE_BLOCKED, f"FX JSON failed to parse: {schema_error}"))
        result.import_gate = ImportGate("fx", False, 0, 0, 0, {}, 0, 0, schema_error)
        return result
    preview = validate_fx_import_rows(rows, max_rows=max(len(rows), 1), now=now)
    existing_by_row: dict[int, list[Any]] = {}
    if baseline is not None:
        for row in preview.rows:
            if row.status != "valid":
                continue
            existing_by_row[row.row_number] = [
                baseline_rate
                for baseline_rate in baseline.fx
                if baseline_rate.base_currency == row.base_currency and baseline_rate.quote_currency == row.quote_currency
            ]
    classified = classify_fx_import_preview(preview, existing_rates_by_row=existing_by_row)
    plan = build_fx_import_execution_plan(classified)
    invalid = [row for row in classified.rows if row.status != "valid"]

    for currency in sorted(required_currencies):
        if not any(row.base_currency == "EUR" and row.quote_currency == currency for row in preview.rows if row.status == "valid"):
            add(SEVERITY_BLOCKER, "fx_missing_required_pair", f"no EUR→{currency} FX fact for a selected pricing currency", None, None)
    for row in preview.rows:
        if row.status != "valid":
            continue
        old = _latest_active(
            [
                baseline_rate
                for baseline_rate in (baseline.fx if baseline else [])
                if baseline_rate.base_currency == row.base_currency and baseline_rate.quote_currency == row.quote_currency
            ],
            now,
        )
        if old is not None and old.rate:
            old_rate = Decimal(old.rate)
            new_rate = Decimal(row.rate)
            if old_rate > 0:
                percent = _pct(old_rate, new_rate)
                if Decimal(percent) > policy.fx_change_review:
                    add(SEVERITY_REVIEW, "fx_moved_review", f"{row.base_currency}→{row.quote_currency} moved {percent} (> policy {policy.fx_change_review})", None, None)
    for facts in bundle.fx:
        if facts.published_at is None:
            add(SEVERITY_REVIEW, "fx_no_publication_date", f"{facts.base_currency}→{facts.quote_currency} has no publication date", None, None)
            continue
        age = now - _utc(facts.published_at)
        if age < timedelta(0):
            add(SEVERITY_BLOCKER, "fx_future_publication", "FX publication date is in the future", None, None)
            continue
        state = policy.fx_age_state(age)
        if state == "review":
            add(SEVERITY_REVIEW, "fx_stale_review", f"FX publication age {age} exceeds review threshold", None, None)
        elif state == "blocked":
            add(SEVERITY_BLOCKER, "fx_stale_blocked", f"FX publication age {age} exceeds blocked threshold", None, None)
    if invalid:
        result.gates.append(Gate(FX_GATE, EVIDENCE_BLOCKED, f"{len(invalid)} FX rows invalid: {invalid[0].errors[0][:200]}"))
    elif plan.blocked_count:
        result.gates.append(Gate(FX_GATE, EVIDENCE_REVIEW, f"{plan.blocked_count} FX rows blocked in apply plan (182)"))
    elif rows:
        result.gates.append(Gate(FX_GATE, EVIDENCE_VERIFIED, "FX JSON valid; plan executable"))
    elif required_currencies:
        result.gates.append(
            Gate(
                FX_GATE,
                EVIDENCE_BLOCKED,
                "required FX pairs missing for: " + ", ".join(sorted(required_currencies)),
            )
        )
    else:
        result.gates.append(Gate(FX_GATE, EVIDENCE_NA, "no FX rows required"))
    result.import_gate = ImportGate(
        "fx",
        schema_valid,
        len(rows),
        classified.valid_count,
        classified.invalid_count,
        _classification_counts(classified),
        plan.executable_count,
        plan.blocked_count,
        f"{len(rows)} rows, {len(invalid)} invalid",
    )
    return result


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

