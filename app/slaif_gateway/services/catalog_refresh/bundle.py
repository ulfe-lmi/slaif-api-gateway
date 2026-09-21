"""Canonical bundle loading, normalization, and artifact generation.

The bundle is the single source of proposal semantics. Everything downstream
(import TSVs/JSON, validation, report, seal) is derived from its normalized
bytes so that re-running the pipeline on the same input is byte-stable.
"""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from pydantic import ValidationError

from slaif_gateway.schemas.catalog_refresh import (
    RefreshBundle,
    SourceRecord,
)
from slaif_gateway.services.catalog_refresh.errors import CatalogRefreshBlockedError

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
            raise ValueError(f"duplicate JSON key {key!r}")
        seen.add(key)
        result[key] = value
    return result


def _reject_non_finite(token: str) -> Any:
    raise ValueError(f"non-finite JSON value {token!r}")


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
    except (json.JSONDecodeError, ValueError) as exc:
        raise CatalogRefreshBlockedError("bundle_invalid_json", str(exc)) from exc
    try:
        return RefreshBundle.model_validate(payload)
    except ValidationError as exc:
        # Pydantic errors include input fragments; emit a bounded, safe form.
        errors = "; ".join(
            f"{'.'.join(str(loc) for loc in error.get('loc', ()))}: {error.get('msg', 'invalid')}"
            for error in exc.errors()[:8]
        )
        raise CatalogRefreshBlockedError(
            "bundle_schema_invalid", errors[:4000]
        ) from exc


def canonical_bundle_bytes(bundle: RefreshBundle) -> bytes:
    """Stable canonical encoding: sorted keys, exact decimal strings, no clock."""
    payload = bundle.model_dump(mode="json")
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _source_retrieved_at(bundle: RefreshBundle, source_key: str) -> str:
    for source in bundle.sources:
        if f"{source.provider}|{source.model}|{source.source_kind}" == source_key:
            return source.retrieved_at.astimezone(_utc()).isoformat()
    return bundle.generated_at.astimezone(_utc()).isoformat()


def _utc():
    from datetime import UTC

    return UTC


def generate_route_tsv(bundle: RefreshBundle, selected: set[tuple[str, str]]) -> bytes:
    """Deterministic routes-proposal.tsv for the selected routable rows."""
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=ROUTE_TSV_FIELDS, delimiter="\t")
    writer.writeheader()
    rows = [
        route
        for route in bundle.routes
        if (route.provider, route.requested_model) in selected
    ]
    for route in sorted(rows, key=lambda r: (r.provider, r.requested_model, r.match_type, r.endpoint)):
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
                "capabilities": json.dumps(route.capabilities, sort_keys=True, separators=(",", ":")),
                "notes": "",
            }
        )
    return buffer.getvalue().encode("utf-8")


def generate_pricing_tsv(bundle: RefreshBundle, selected: set[tuple[str, str]]) -> bytes:
    """Deterministic pricing-proposal.tsv for the selected priced rows."""
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=PRICING_TSV_FIELDS, delimiter="\t")
    writer.writeheader()
    rows = [
        pricing
        for pricing in bundle.pricing
        if (pricing.provider, pricing.model) in selected
    ]

    def _dim(pricing, name: str) -> str:
        for dimension in pricing.dimensions:
            if dimension.name == name:
                return dimension.value or ""
        return ""

    for pricing in sorted(rows, key=lambda p: (p.provider, p.model, p.currency)):
        first_source = pricing.provenance.sources[0]
        writer.writerow(
            {
                "provider": pricing.provider,
                "model": pricing.model,
                "endpoint": pricing.endpoint,
                "currency": pricing.currency,
                "input_price_per_1m": _dim(pricing, "input"),
                "cached_input_price_per_1m": _dim(pricing, "cached_input"),
                "output_price_per_1m": _dim(pricing, "output"),
                "reasoning_price_per_1m": _dim(pricing, "reasoning"),
                "request_price": _dim(pricing, "request"),
                "valid_from": pricing.valid_from.astimezone(_utc()).isoformat(),
                "source_url": _first_authoritative_url(bundle, pricing),
                "source_retrieved_at": _source_retrieved_at(bundle, first_source),
                "pricing_metadata": json.dumps(
                    {"dimensions": {d.name: {"value": d.value, "unit": d.unit} for d in pricing.dimensions}},
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                "notes": "",
            }
        )
    return buffer.getvalue().encode("utf-8")


def generate_fx_json(bundle: RefreshBundle) -> bytes:
    """Deterministic fx-proposal.json (FX import supports JSON, not TSV)."""
    rows = [
        {
            "base_currency": fx.base_currency,
            "quote_currency": fx.quote_currency,
            "rate": str(Decimal(fx.rate)),
            "source": fx.source,
            "valid_from": fx.valid_from.astimezone(_utc()).isoformat(),
            "valid_until": fx.valid_until.astimezone(_utc()).isoformat() if fx.valid_until else None,
            "metadata": {"published_at": fx.published_at.astimezone(_utc()).isoformat() if fx.published_at else None},
            "notes": "",
        }
        for fx in sorted(bundle.fx, key=lambda f: (f.base_currency, f.quote_currency, f.valid_from))
    ]
    return (json.dumps(rows, sort_keys=True, indent=1) + "\n").encode("utf-8")


def _first_authoritative_url(bundle: RefreshBundle, pricing) -> str:
    for source_key in pricing.provenance.sources:
        for source in bundle.sources:
            if f"{source.provider}|{source.model}|{source.source_kind}" == source_key:
                return source.url
    return ""


@dataclass(frozen=True, slots=True)
class BaselineRowProxy:
    """Attribute proxy so baseline rows feed the existing import classifiers."""

    requested_model: str | None = None
    match_type: str | None = None
    endpoint: str | None = None
    provider: str | None = None
    upstream_model: str | None = None
    priority: int | None = None
    enabled: bool = False
    visible_in_models: bool = False
    supports_streaming: bool = False
    capabilities: dict[str, object] | None = None
    notes: str | None = None
    currency: str | None = None
    valid_from: object | None = None
    valid_until: object | None = None
    base_currency: str | None = None
    quote_currency: str | None = None
    rate: str | None = None
    source: str | None = None


def route_proxy(row: Any) -> BaselineRowProxy:
    return BaselineRowProxy(
        requested_model=row.requested_model,
        match_type=row.match_type,
        endpoint=row.endpoint,
        provider=row.provider,
        upstream_model=row.upstream_model,
        priority=row.priority,
        enabled=row.enabled,
        visible_in_models=row.visible_in_models,
        supports_streaming=row.supports_streaming,
        capabilities=dict(row.capabilities or {}),
        notes=None,
    )


def pricing_proxy(row: Any) -> BaselineRowProxy:
    return BaselineRowProxy(
        provider=row.provider,
        upstream_model=row.upstream_model,
        endpoint=row.endpoint,
        currency=row.currency,
        enabled=row.enabled,
        valid_from=row.valid_from,
        valid_until=row.valid_until,
    )


def fx_proxy(row: Any) -> BaselineRowProxy:
    return BaselineRowProxy(
        base_currency=row.base_currency,
        quote_currency=row.quote_currency,
        rate=row.rate,
        source=row.source,
        enabled=True,
        valid_from=row.valid_from,
        valid_until=row.valid_until,
    )


def selected_model_keys(bundle: RefreshBundle) -> set[tuple[str, str]]:
    """(provider, model) keys selected by the bundle selection filters."""
    providers = set(bundle.selection.providers)
    included = set(bundle.selection.model_include)
    keys: set[tuple[str, str]] = set()
    for provider, model in {
        (item.provider, getattr(item, "model", None) or item.requested_model)
        for item in (*bundle.models, *bundle.pricing, *bundle.routes)
    }:
        if provider not in providers:
            continue
        if included and model not in included:
            continue
        keys.add((provider, model))
    return keys


def source_for(bundle: RefreshBundle, provider: str, model: str) -> list[SourceRecord]:
    return [
        source
        for source in bundle.sources
        if source.provider == provider and source.model == model
    ]
