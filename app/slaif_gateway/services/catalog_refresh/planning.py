"""Deterministic apply-plan derivation for catalog refresh (objective 182,
A2/A3).

The apply plan is a CANONICAL TYPED projection of the authenticated sealed
bytes only (bundle + baseline document + the validation state of this
recomputation). It carries no effective T, no wall clock, and no live
database state, so the plan identity (``plan_sha256``) is stable for the
same sealed run. The symbolic value :data:`EFFECTIVE_T_SYMBOL` marks the
instant at which every NEW row is inserted: the one effective T chosen by
the successful apply transaction itself (A3). The plan never carries a
timestamp for that instant.

Representability (bounded 182 scope):
- genuinely NEW route/pricing rows -> create operations (plus the missing
  provider metadata for their providers);
- CHANGED price against a single valid active baseline row ->
  ``supersede_pricing`` (close the reviewed active window at T, insert the
  new row at T; never an in-place reprice);
- FX pairs with a differing active baseline rate -> ``supersede_fx``;
  required pairs with NO active baseline row (including closed-history-only
  pairs) -> ``create_fx`` bound to the comparison state NEW.
Route capability/identity mutations are NOT representable in 182 and never
appear in a plan; those runs stay BLOCKED by the route gate.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from slaif_gateway.schemas.catalog_refresh import (
    APPLY_PLAN_SCHEMA_VERSION,
    BaselineFxRow,
    BaselinePricingRow,
    ModelPricingFacts,
    RefreshBundle,
    RouteFacts,
    derived_route_capabilities,
)
from slaif_gateway.services.catalog_refresh.bundle import _first_provenance_url

# Symbol for the one effective T of the successful apply transaction.
EFFECTIVE_T_SYMBOL = "effective_t"

# Canonical insertion order for the sorted operation list (determinism).
_TYPE_ORDER: dict[str, int] = {
    "create_provider": 0,
    "create_route": 1,
    "create_pricing": 2,
    "supersede_pricing": 3,
    "create_fx": 4,
    "supersede_fx": 5,
}

# Canonical provider metadata for the KNOWN providers when the baseline does
# not carry a provider config row. The values mirror the provider-config
# service defaults (display_name falls back to the slug, built-in base URL,
# standard kind/timeouts), so the plan names exactly the row apply inserts.
_PROVIDER_DEFAULTS: dict[str, dict[str, Any]] = {
    "openai": {
        "display_name": "openai",
        "base_url": "https://api.openai.com/v1",
        "api_key_env_var": "OPENAI_UPSTREAM_API_KEY",
    },
    "openrouter": {
        "display_name": "openrouter",
        "base_url": "https://openrouter.ai/api/v1",
        "api_key_env_var": "OPENROUTER_API_KEY",
    },
}


def _iso(value: datetime | None) -> str | None:
    return None if value is None else value.astimezone(UTC).isoformat()


def create_provider_op(provider: str) -> dict[str, Any]:
    defaults = _PROVIDER_DEFAULTS[provider]
    return {
        "type": "create_provider",
        "provider": provider,
        "display_name": defaults["display_name"],
        "base_url": defaults["base_url"],
        "api_key_env_var": defaults["api_key_env_var"],
        "kind": "openai_compatible",
        "enabled": True,
        "timeout_seconds": 300,
        "max_retries": 2,
    }


def create_route_op(route: RouteFacts) -> dict[str, Any]:
    """Create operation for one genuinely NEW route row.

    ``capabilities`` carries the ACTUAL runtime capability contract (the
    same deterministic derived shape the executable TSV artifact emits), so
    the applied row is byte-consistent with the reviewed artifact.
    """
    return {
        "type": "create_route",
        "provider": route.provider,
        "requested_model": route.requested_model,
        "upstream_model": route.upstream_model,
        "match_type": route.match_type,
        "priority": route.priority,
        "enabled": route.enabled,
        "visible_in_models": route.visible_in_models,
        "supports_streaming": route.supports_streaming,
        "endpoint": route.endpoint,
        "capabilities": derived_route_capabilities(
            route.capabilities, supports_streaming=route.supports_streaming
        ),
    }


def _pricing_dimensions(pricing: ModelPricingFacts) -> dict[str, str | None]:
    return {dimension.name: dimension.value for dimension in pricing.dimensions}


def create_pricing_op(
    bundle: RefreshBundle,
    pricing: ModelPricingFacts,
    *,
    upstream: str,
) -> dict[str, Any]:
    """Create operation for one genuinely NEW pricing row.

    ``model`` is the route's UPSTREAM identity (public aliases are local
    routing state; the executable pricing row carries the upstream model),
    exactly as the executable TSV artifact maps it.
    """
    return {
        "type": "create_pricing",
        "provider": pricing.provider,
        "model": upstream,
        "endpoint": pricing.endpoint,
        "currency": pricing.currency,
        "dimensions": _pricing_dimensions(pricing),
        "source_url": _first_provenance_url(bundle, pricing) or None,
        "new_valid_from": EFFECTIVE_T_SYMBOL,
    }


def supersede_pricing_op(
    bundle: RefreshBundle,
    old: BaselinePricingRow,
    pricing: ModelPricingFacts,
) -> dict[str, Any]:
    """Supersession operation for a CHANGED price on a single valid active
    baseline row. ``old`` records the reviewed baseline facts the apply
    close-guard must re-verify at T (row identity, exact values, the
    reviewed closing instant); the new row is inserted at the effective T.
    """
    return {
        "type": "supersede_pricing",
        "provider": old.provider,
        "model": old.upstream_model,
        "endpoint": old.endpoint,
        "old": {
            "row_id": old.id,
            "currency": old.currency,
            "dimensions": {
                "input": old.input_price_per_1m,
                "cached_input": old.cached_input_price_per_1m,
                "output": old.output_price_per_1m,
                "reasoning": old.reasoning_price_per_1m,
                "request": old.request_price,
            },
            "valid_from": _iso(old.valid_from),
            "valid_until": _iso(old.valid_until),
            "enabled": old.enabled,
        },
        "new": {
            "currency": pricing.currency,
            "dimensions": _pricing_dimensions(pricing),
            "source_url": _first_provenance_url(bundle, pricing) or None,
            "new_valid_from": EFFECTIVE_T_SYMBOL,
        },
    }


def create_fx_op(
    pair: tuple[str, str],
    *,
    rate: str,
    source: str | None,
    published_at: datetime | None,
    derived: bool,
    source_pair: str | None,
) -> dict[str, Any]:
    """Create operation for a required native->EUR pair with NO active
    baseline row (comparison state NEW, including closed-history-only
    pairs). The row is inserted at the effective T."""
    base_currency, quote_currency = pair
    return {
        "type": "create_fx",
        "base_currency": base_currency,
        "quote_currency": quote_currency,
        "rate": rate,
        "source": source,
        "published_at": _iso(published_at),
        "derived_reciprocal": derived,
        "source_pair": source_pair,
        "new_valid_from": EFFECTIVE_T_SYMBOL,
    }


def supersede_fx_op(
    old: BaselineFxRow,
    *,
    rate: str,
    source: str | None,
    published_at: datetime | None,
    derived: bool,
    source_pair: str | None,
) -> dict[str, Any]:
    """Supersession operation for a required native->EUR pair whose single
    valid active baseline row carries a different rate. ``old`` records the
    reviewed baseline facts the apply close-guard re-verifies at T."""
    return {
        "type": "supersede_fx",
        "base_currency": old.base_currency,
        "quote_currency": old.quote_currency,
        "old": {
            "row_id": old.id,
            "rate": old.rate,
            "valid_from": _iso(old.valid_from),
            "valid_until": _iso(old.valid_until),
            "source": old.source,
        },
        "new": {
            "rate": rate,
            "source": source,
            "published_at": _iso(published_at),
            "derived_reciprocal": derived,
            "source_pair": source_pair,
            "new_valid_from": EFFECTIVE_T_SYMBOL,
        },
    }


def op_sort_key(op: dict[str, Any]) -> tuple[Any, ...]:
    """Canonical, total sort key for operations (deterministic plan bytes)."""
    op_type = op["type"]
    primary = op.get("provider") or ""
    secondary = ""
    tertiary = ""
    if op_type == "create_route":
        secondary = op.get("requested_model") or ""
        tertiary = op.get("match_type") or ""
    elif op_type == "create_pricing":
        secondary = op.get("model") or ""
        tertiary = op.get("endpoint") or ""
    elif op_type == "supersede_pricing":
        secondary = op.get("model") or ""
        tertiary = op.get("endpoint") or ""
    elif op_type in ("create_fx", "supersede_fx"):
        primary = op.get("base_currency") or ""
        secondary = op.get("quote_currency") or ""
    return (_TYPE_ORDER[op_type], primary, secondary, tertiary)


def plan_sha256(operations: list[dict[str, Any]]) -> str:
    """SHA-256 of the canonical encoding of the sorted operation list."""
    canonical = json.dumps(operations, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_apply_plan(operations: list[dict[str, Any]]) -> dict[str, Any]:
    """The canonical apply-plan object (attached to the report only when
    non-empty, so no-change runs keep byte-stable validation.json)."""
    ops = sorted(operations, key=op_sort_key)
    return {
        "schema_version": APPLY_PLAN_SCHEMA_VERSION,
        "plan_sha256": plan_sha256(ops),
        "operations": ops,
    }
