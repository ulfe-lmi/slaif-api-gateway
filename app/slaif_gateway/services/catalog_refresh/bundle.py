"""Canonical bundle loading, normalization, and artifact generation.

The bundle is the single source of proposal semantics. Everything downstream
(import TSVs/JSON, validation, report, seal) is derived from its normalized
bytes so that re-running the pipeline on the same input is byte-stable.

Artifact rules (180-b): executable import artifacts carry *only* the
permitted intended operations — create rows. Duplicates (no-op rows),
updates, and excluded rows never leak into the TSV/JSON deltas; the full
catalog facts, including excluded rows, remain in the canonical bundle and
the review report.
"""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Sequence

from pydantic import ValidationError

from slaif_gateway.schemas.catalog_refresh import (
    RefreshBundle,
    RouteFacts,
    SourceRecord,
    derived_route_capabilities,
)
from slaif_gateway.services.catalog_refresh.errors import (
    CatalogRefreshBlockedError,
    safe_schema_error_text,
)

MAX_BUNDLE_BYTES = 8 * 1024 * 1024

ROUTE_TSV_FIELDS = [
    "requested_model",
    "match_type",
    "endpoint",
    "provider",
    "upstream_model",
    "priority",
    "enabled",
    "visible_in_models",
    "supports_streaming",
    "capabilities",
    "notes",
]
PRICING_TSV_FIELDS = [
    "provider",
    "model",
    "endpoint",
    "currency",
    "input_price_per_1m",
    "cached_input_price_per_1m",
    "output_price_per_1m",
    "reasoning_price_per_1m",
    "request_price",
    "valid_from",
    "source_url",
    "source_retrieved_at",
    "pricing_metadata",
    "notes",
]


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    seen: set[str] = set()
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in seen:
            # Constant message: the (untrusted) key name is never echoed.
            raise ValueError("duplicate JSON key")
        seen.add(key)
        result[key] = value
    return result


def _reject_non_finite(_token: str) -> Any:
    raise ValueError("non-finite JSON value")


def load_bundle(raw: bytes) -> RefreshBundle:
    """Parse and validate the canonical bundle, rejecting unsafe JSON."""
    if len(raw) > MAX_BUNDLE_BYTES:
        raise CatalogRefreshBlockedError(
            "bundle_too_large", "bundle exceeds the 8 MiB bound"
        )
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CatalogRefreshBlockedError(
            "bundle_not_utf8", "bundle is not valid UTF-8"
        ) from exc
    try:
        payload = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_non_finite,
        )
    except (json.JSONDecodeError, ValueError, RecursionError) as exc:
        raise CatalogRefreshBlockedError("bundle_invalid_json", str(exc)) from exc
    try:
        return RefreshBundle.model_validate(payload)
    except ValidationError as exc:
        # Pydantic locations/messages may carry untrusted input;
        # render a bounded, safe form (see safe_schema_error_text).
        raise CatalogRefreshBlockedError(
            "bundle_schema_invalid", safe_schema_error_text(exc)
        ) from exc


def canonical_bundle_bytes(bundle: RefreshBundle) -> bytes:
    """Stable canonical encoding: sorted keys, exact decimal strings, no clock."""
    payload = bundle.model_dump(mode="json")
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _utc():
    from datetime import UTC

    return UTC


def generate_route_tsv(bundle: RefreshBundle, routes: Sequence[RouteFacts]) -> bytes:
    """Deterministic routes-proposal.tsv for exactly the permitted create rows.

    The caller (validation) decides which routes are executable creates;
    this function only serializes them. Duplicates/updates/excluded rows are
    never passed in and therefore never leak into the executable artifact.
    """
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=ROUTE_TSV_FIELDS, delimiter="\t")
    writer.writeheader()
    for route in sorted(routes, key=lambda r: (r.provider, r.requested_model, r.match_type, r.endpoint)):
        writer.writerow(
            {
                "requested_model": route.requested_model,
                "match_type": route.match_type,
                "endpoint": route.endpoint,
                "provider": route.provider,
                "upstream_model": route.upstream_model,
                "priority": str(route.priority),
                "enabled": str(route.enabled).lower(),
                "visible_in_models": str(route.visible_in_models).lower(),
                "supports_streaming": str(route.supports_streaming).lower(),
                # 180-f (F2): emit the ACTUAL runtime capability shape (the
                # single deterministic derived contract), not stray flat
                # storage keys, so created rows survive export -> refresh
                # without an unrepresented-capability blocker.
                "capabilities": json.dumps(
                    derived_route_capabilities(
                        route.capabilities, supports_streaming=route.supports_streaming
                    ),
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                "notes": "",
            }
        )
    return buffer.getvalue().encode("utf-8")


def generate_pricing_tsv(
    bundle: RefreshBundle,
    rows: Sequence[Any],
    upstream_by_key: dict[tuple[str, str], str],
) -> bytes:
    """Deterministic pricing-proposal.tsv for exactly the permitted create rows.

    The ``model`` column carries the *upstream* model ID that the paired
    route forwards to (public aliases need not equal upstream IDs); the
    caller resolves the mapping through ``upstream_by_key``.
    """
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=PRICING_TSV_FIELDS, delimiter="\t")
    writer.writeheader()

    def _dim(pricing, name: str) -> str:
        for dimension in pricing.dimensions:
            if dimension.name == name:
                return dimension.value or ""
        return ""

    for pricing in sorted(rows, key=lambda p: (p.provider, p.model, p.currency)):
        upstream = upstream_by_key.get((pricing.provider, pricing.model), pricing.model)
        writer.writerow(
            {
                "provider": pricing.provider,
                "model": upstream,
                "endpoint": pricing.endpoint,
                "currency": pricing.currency,
                "input_price_per_1m": _dim(pricing, "input"),
                "cached_input_price_per_1m": _dim(pricing, "cached_input"),
                "output_price_per_1m": _dim(pricing, "output"),
                "reasoning_price_per_1m": _dim(pricing, "reasoning"),
                "request_price": _dim(pricing, "request"),
                "valid_from": pricing.valid_from.astimezone(_utc()).isoformat(),
                "source_url": _first_provenance_url(bundle, pricing),
                # 180-f (F2): generated rows must carry only metadata the
                # runtime pricing_metadata contract can represent. The
                # proposal's dimension data already lives in the typed
                # price columns and source provenance lives in the sealed
                # bundle's source records; injecting either into row
                # metadata would make the imported row unrepresentable on
                # the next baseline export and block the very round trip
                # this artifact is meant to feed.
                "source_retrieved_at": "",
                "pricing_metadata": "",
                "notes": "",
            }
        )
    return buffer.getvalue().encode("utf-8")


@dataclass(frozen=True, slots=True)
class NormalizedFxRow:
    """One executable FX create row in the canonical runtime direction.

    The runtime converts costs with
    ``find_latest_rate(base_currency=native, quote_currency=EUR)``, so the
    import-ready pair is always native -> EUR. Rows derived as the reciprocal
    of a supplied EUR -> native quotation keep the original pair recorded so
    the direction is never silently relabeled.
    """

    base_currency: str
    quote_currency: str
    rate: str
    source: str | None
    valid_from: Any
    valid_until: Any | None
    published_at: Any | None
    derived_reciprocal: bool
    source_pair: str | None = None


def generate_fx_json(rows: Sequence[NormalizedFxRow]) -> bytes:
    """Deterministic fx-proposal.json for exactly the permitted create rows.

    Every row is in the canonical native -> EUR direction the runtime uses;
    derived reciprocals are recorded (never relabeled) in the row metadata.
    """
    payload_rows = [
        {
            "base_currency": row.base_currency,
            "quote_currency": row.quote_currency,
            "rate": str(Decimal(row.rate)),
            "source": row.source,
            "valid_from": row.valid_from.astimezone(_utc()).isoformat(),
            "valid_until": row.valid_until.astimezone(_utc()).isoformat() if row.valid_until else None,
            "metadata": {
                "published_at": row.published_at.astimezone(_utc()).isoformat() if row.published_at else None,
                "derived_reciprocal": row.derived_reciprocal,
                "source_pair": row.source_pair,
            },
            "notes": "",
        }
        for row in sorted(rows, key=lambda r: (r.base_currency, r.quote_currency, str(r.valid_from)))
    ]
    return (json.dumps(payload_rows, sort_keys=True, indent=1) + "\n").encode("utf-8")


def _first_provenance_url(bundle: RefreshBundle, pricing: Any) -> str:
    for source_key in pricing.provenance.sources:
        for source in bundle.sources:
            if f"{source.provider}|{source.model}|{source.source_kind}" == source_key:
                return source.url
    return ""


def selected_model_keys(bundle: RefreshBundle) -> set[tuple[str, str]]:
    """(provider, public model) keys selected by the bundle selection filters.

    Pricing facts keyed by an upstream model ID that a selected route of the
    same provider forwards to are normalized onto that route's public name,
    so alias cases do not create phantom selected models.
    """
    providers = set(bundle.selection.providers)
    included = set(bundle.selection.model_include)

    public_by_upstream: dict[tuple[str, str], set[str]] = {}
    public_names: set[tuple[str, str]] = set()
    for route in bundle.routes:
        if route.provider not in providers:
            continue
        public_by_upstream.setdefault((route.provider, route.upstream_model), set()).add(route.requested_model)
        public_names.add((route.provider, route.requested_model))

    keys: set[tuple[str, str]] = set()
    for provider, model in {
        (item.provider, getattr(item, "model", None) or item.requested_model)
        for item in (*bundle.models, *bundle.pricing, *bundle.routes)
    }:
        if provider not in providers:
            continue
        # A fact key that is already a public route name stays as-is; a key
        # that is not a public name is resolved through the route(s) of this
        # provider that forward to that upstream model.
        if (provider, model) in public_names:
            resolved = {model}
        else:
            resolved = public_by_upstream.get((provider, model)) or {model}
        for candidate in sorted(resolved):
            if included and candidate not in included:
                continue
            keys.add((provider, candidate))
    return keys


def source_for(bundle: RefreshBundle, provider: str, model: str) -> list[SourceRecord]:
    return [
        source
        for source in bundle.sources
        if source.provider == provider and source.model == model
    ]
