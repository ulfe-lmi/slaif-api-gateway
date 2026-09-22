"""Bounded offline source-evidence parsing, observations, and reconciliation.

Objective-180 continuation 180-c: a matching hash of arbitrary bytes and an
official URL are not evidence of a model's price, units, limits or
capabilities. Proposed facts must be bound to the *parsed meaning* of the
supplied snapshot bytes.

This module is pure and strictly offline:

- it parses bounded evidence bytes with deterministic, reviewed parsers
  (reusing the provider-catalog pure helpers through a bounded adapter);
- it derives typed observations carrying exact row/field locators, values,
  units, currencies and parser identity;
- it reconciles observations against proposed facts with exact Decimal
  semantics (canonical comparison currency EUR, import-contract 9-dp
  quantization).

It never performs network I/O, never invokes the live proposal generator or
its fetchers, never resolves XML external entities, and never treats a
supplied boolean or label as retrieval attestation. Offline replay proves
extraction consistency against supplied snapshots; it does not authenticate a
live retrieval that never occurred.

Versioning decision (C1): the catalog-refresh subsystem is unmerged, so the
typed bundle contract (schema v1) deliberately evolves in this focused round.
The evolution is additive on the validation side (the validator derives
observations from the supplied evidence bytes; no new top-level bundle fields
are introduced) and the schema stays at version ``1``. Incompatible inputs
(unknown provider/source-kind combinations, malformed snapshots, digests that
contradict the bytes) are rejected clearly at load time or classified
BLOCKED/REVIEW at validation time, never silently accepted.
"""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Mapping

# Bounded provider-catalog pure helpers (reused, not duplicated).
from slaif_gateway.services.provider_catalog_proposal import (
    _decimal_to_string,
    _doc_price_cell,
    _extract_tabular_blocks,
    _parse_openai_models_docs,
    _parse_openai_pricing_docs,
    _safe_openai_model_id,
)

# --- bounds (enforced before expensive decoding/parsing) --------------------

MAX_SNAPSHOT_BYTES = 4 * 1024 * 1024
MAX_XML_BYTES = 1 * 1024 * 1024
MAX_JSON_ITEMS = 500          # rows in an OpenRouter/OpenAI models payload
MAX_TABLE_ROWS = 5000         # rows across all OpenAI docs tables
MAX_MODELS_PER_SNAPSHOT = 500
MAX_QUOTE_CURRENCIES = 64     # FX quotes per ECB snapshot

# Import-contract money precision: PostgreSQL Numeric(18,9).
MONEY_QUANTUM = Decimal("0.000000001")
PER_TOKEN_TO_PER_1M = Decimal("1000000")

_EUR = "EUR"

# Capability keys that are provider-observed facts (backed by snapshot
# modalities). Every other capability key, plus route-local choices (alias,
# priority, visibility, enabled, match_type, supports_streaming), is operator
# / gateway-local policy and is never claimed to come from provider pages.
PROVIDER_OBSERVED_CAPABILITIES: frozenset[str] = frozenset({"text"})

# FX rate binding tolerance: identical to the FX gate's direct-vs-reciprocal
# consistency tolerance, so evidence binding and the FX gate can never
# disagree about whether two decimal rates "agree".
FX_BINDING_TOLERANCE = Decimal("0.00000001")


class SnapshotFormatError(Exception):
    """Safe, code-only snapshot format failure. Never carries raw content."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class ParsedModel:
    """Deterministic model-level facts parsed from one snapshot row."""

    provider: str
    model: str
    context_length: int | None = None
    max_output_tokens: int | None = None
    prices: Mapping[str, Decimal] = field(default_factory=dict)  # dim -> per-1m
    price_currency: str | None = None
    text_modality: bool | None = None  # None = not reported by this source
    deprecated: bool | None = None     # None = not reported by this source
    locators: Mapping[str, str] = field(default_factory=dict)
    parser: str = ""
    identity_only: bool = False
    # Objective 181: contextual billing/endpoint facts. ``billing_tier``
    # ("standard"/"batch"/"flex"/"fast") and ``context_band`` ("short"/
    # "long") are None when the source does not distinguish them (OpenRouter
    # and the legacy single-table OpenAI format). ``prices`` carries the
    # short-band representable dims of the row's tier, ``prices_long`` the
    # long-band dims, and ``extra_pricing`` observed dims outside the
    # standard-v1 proposal contract (exact canonical values).
    # ``non_representable_prices`` records recognized non-representable
    # values (dim -> safe reason code): the row keeps its identity and the
    # value is never converted to zero or a guessed related-model price.
    billing_tier: str | None = None
    context_band: str | None = None
    prices_long: Mapping[str, Decimal] = field(default_factory=dict)
    extra_pricing: Mapping[str, str] = field(default_factory=dict)
    non_representable_prices: Mapping[str, str] = field(default_factory=dict)
    chat_supported: bool | None = None
    # 181: the OpenRouter "overrides" key publishes contextual (long-context
    # min_prompt_tokens / time-of-day) price tiers as a stringified list.
    # Contextual tiers are not representable by the standard-v1 flat
    # proposal contract; the observed block count is recorded so they are
    # accounted for, never silently ignored and never proposed.
    pricing_overrides: int | None = None
    # 181-b: the OpenRouter "request" key publishes a per-REQUEST charge
    # (USD per request, NOT per-1M). None = not published; a source -1
    # sentinel on this key is recorded on non_representable_prices.
    request_price: Decimal | None = None
    # 181-b: published pricing keys outside the recognized billable/observed
    # set, recorded (never silently dropped) and fail-closed at eligibility.
    unknown_pricing_keys: tuple[str, ...] = ()


@dataclass(frozen=True)
class ParsedFxQuote:
    """One reference-rate quote parsed from an FX snapshot."""

    base_currency: str
    quote_currency: str
    rate: Decimal
    published_date: date
    locator: str
    parser: str


@dataclass(frozen=True)
class SnapshotParse:
    provider: str
    source_kind: str
    ok: bool
    error: str | None  # safe code only
    models: tuple[ParsedModel, ...] = ()
    fx_quotes: tuple[ParsedFxQuote, ...] = ()
    parser: str = ""


@dataclass(frozen=True)
class Observation:
    """One typed, locatable observation derived from parsed snapshot bytes.

    An observation is a property of the parsed bytes (source key, row/field
    locator, canonical value, unit, currency, parser identity). It is never
    manufactured by copying a proposed value to its provenance sources.
    """

    source_key: str
    provider: str
    model: str
    field: str          # pricing:<dim> | model:context_length | ... | fx:rate
    locator: str
    value: str          # canonical exact string (Decimal text / true / false)
    unit: str           # per_1m_tokens | none | currency_pair
    currency: str | None
    parser: str


@dataclass(frozen=True)
class ReconciliationFinding:
    severity: str  # "BLOCKER" | "REVIEW"
    code: str
    detail: str
    provider: str | None = None
    model: str | None = None


@dataclass(frozen=True)
class BackedFact:
    """One proposed fact bound to deterministic parsed observations.

    ``observations`` carries the actual derived observation records that
    bound the fact (observed value, unit, currency, exact locator,
    normalization) so the one report can show the evidence inline. There
    is no semantic backing: a label or copied value never verifies a fact.
    """

    field: str
    proposed: str
    proposed_normalized: str | None  # canonical normalized proposal (EUR for pricing)
    backed_by: tuple[str, ...]       # declared source keys with a matching observation
    independent_sources: int         # distinct official URLs among the matchers
    observations: tuple[dict[str, Any], ...] = ()


# --- deterministic parsers ---------------------------------------------------

def _decode_bounded(evidence: bytes, *, kind: str, max_bytes: int) -> str:
    if len(evidence) > max_bytes:
        raise SnapshotFormatError(f"{kind}:snapshot_too_large")
    try:
        return evidence.decode("utf-8")
    except UnicodeDecodeError:
        raise SnapshotFormatError(f"{kind}:not_utf8") from None


def _reject_duplicate_key(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    seen: set[str] = set()
    for key, _value in pairs:
        if key in seen:
            raise SnapshotFormatError("duplicate_key")
        seen.add(key)
    return dict(pairs)


def _reject_non_finite_constant(token: str) -> Any:
    raise SnapshotFormatError("non_finite_constant")


def _json_loads_bounded(evidence: bytes, *, kind: str) -> Any:
    """Decode and parse bounded snapshot JSON strictly.

    Duplicate object keys and non-finite constants are rejected at every
    nesting level, not merely in the outer bundle: a second conflicting
    ``prompt`` cell inside the decoded snapshot is malformed official
    content, never a last-wins surprise. Errors are code-only; no input
    fragments are echoed.
    """
    text = _decode_bounded(evidence, kind=kind, max_bytes=MAX_SNAPSHOT_BYTES)
    try:
        return json.loads(
            text,
            object_pairs_hook=_reject_duplicate_key,
            parse_constant=_reject_non_finite_constant,
        )
    except SnapshotFormatError as exc:
        raise SnapshotFormatError(f"{kind}:{exc.code}") from None
    except json.JSONDecodeError:
        raise SnapshotFormatError(f"{kind}:malformed_json") from None


# Price cell syntax: plain or exponent-form decimals (both shapes appear
# in published payloads and in supplied fixture evidence). The exponent is
# bounded to three digits so hostile exponents cannot escape the Decimal
# context; the real bounds are value-level and spelling-independent,
# enforced on the parsed Decimal so legitimate cells spelled with many
# fractional places (e.g. 16 significant digits in 22 places) pass while
# hostiles (too many significant digits, huge magnitude, negatives other
# than the documented -1 sentinel, non-finite values) stay fail-closed.
# The per-1M magnitude cap keeps every converted value inside the
# Numeric(18,9) import contract enforced downstream.
_OPENROUTER_PRICE_SYNTAX = re.compile(r"^[+-]?(?:\d+(?:\.\d+)?|\.\d+)(?:[eE][+-]?\d{1,3})?$")
_OPENROUTER_PER_1M_MAGNITUDE_CAP = Decimal("1000000000")
# The import contract is Numeric(18,9): a nonzero per-1M value below the
# 9-decimal quantum would quantize to zero, which would turn a real price
# into a free one. Exact zero remains a legitimate (review-flagged) price.
_OPENROUTER_PRICE_QUANTUM = Decimal("0.000000001")


def _openrouter_price_decimal(cell: str) -> Decimal:
    """Exact per-token -> per-1M conversion with value-level bounds."""
    if not _OPENROUTER_PRICE_SYNTAX.fullmatch(cell):
        raise ValueError("syntax")
    try:
        value = Decimal(cell)
        per_1m = value * Decimal("1000000")
    except InvalidOperation:
        raise ValueError("bound") from None
    if (
        not value.is_finite()
        or value < 0
        or len(value.as_tuple().digits) > 18
        or per_1m >= _OPENROUTER_PER_1M_MAGNITUDE_CAP
        or (0 < per_1m < _OPENROUTER_PRICE_QUANTUM)
    ):
        raise ValueError("bound")
    return per_1m


def _openrouter_validated_rows(payload: Any, *, kind: str) -> list[Mapping[str, object]]:
    """Raw structural validation of an OpenRouter-style payload.

    The raw structure is validated with original row indices preserved
    before any reused helper is invoked: the proposal helper filters
    non-mapping rows before enumeration, which would shift locators and
    let malformed rows disappear silently. Any malformed row or invalid
    model id is a format error (code-only, never echoed).
    """
    if not isinstance(payload, Mapping):
        raise SnapshotFormatError(f"{kind}:not_an_object")
    data = payload.get("data")
    if not isinstance(data, list):
        raise SnapshotFormatError(f"{kind}:missing_data_array")
    if len(data) > MAX_JSON_ITEMS:
        raise SnapshotFormatError(f"{kind}:too_many_rows")
    for _index, row in enumerate(data):
        if not isinstance(row, Mapping):
            raise SnapshotFormatError(f"{kind}:malformed_row")
        raw_id = row.get("id")
        if not isinstance(raw_id, str) or not raw_id or raw_id != raw_id.strip() or len(raw_id) > 200:
            raise SnapshotFormatError(f"{kind}:invalid_model_id")
    return list(data)


# 181-b: the complete set of recognized OpenRouter top-level pricing keys.
# Anything else published is an unknown billing dimension (recorded and
# fail-closed at eligibility), never silently accepted as harmless.
_OPENROUTER_PRICING_KEYS = frozenset(
    {
        "prompt",
        "input_cache_read",
        "completion",
        "internal_reasoning",
        "input_cache_write",
        "input_cache_write_1h",
        "web_search",
        "request",
        "overrides",
    }
)

_OPENROUTER_OVERRIDE_BLOCK = re.compile(r"\{[^{}]*\}")
# Key set grounded in the live 2026-09-22 /models payload (observed blocks
# also carry 1-hour cache-write, audio and audio-cache price dims). Values
# are never parsed into facts; only the block count is recorded, so the
# allowlist gates shape recognition only. Unknown keys stay fail-closed.
_OPENROUTER_OVERRIDE_KEYS = frozenset(
    {
        "min_prompt_tokens",
        "utc_days",
        "utc_start",
        "utc_end",
        "prompt",
        "completion",
        "input_cache_read",
        "input_cache_write",
        "input_cache_write_1h",
        "internal_reasoning",
        "audio",
        "input_audio_cache",
    }
)
_OPENROUTER_OVERRIDE_PRICE_KEYS = frozenset(
    {
        "prompt",
        "completion",
        "input_cache_read",
        "input_cache_write",
        "input_cache_write_1h",
        "internal_reasoning",
        "audio",
        "input_audio_cache",
    }
)


def _safe_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, str):
        try:
            parsed = int(value.strip())
        except ValueError:
            return None
        return parsed if parsed >= 0 else None
    return None


def _string_list(value: Any) -> tuple[str, ...] | None:
    if not isinstance(value, list):
        return None
    out: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item or len(item) > 64:
            return None
        out.append(item)
    return tuple(out)


def parse_openrouter_models_snapshot(evidence: bytes) -> tuple[ParsedModel, ...]:
    """Parse a cached OpenRouter /models payload (official API shape).

    The raw structure is validated with original row indices preserved
    (a malformed row or invalid id is a format error, never a silent
    skip), then bounded decimal cells are converted to per-million USD
    with exact Decimal arithmetic and value-level bounds.
    Pricing cells are per-token USD strings in the official shape; they
    are normalized to per-million USD with exact Decimal arithmetic (the
    SLAIF import-contract unit). A payload without ``data[]`` is
    malformed.
    """
    payload = _json_loads_bounded(evidence, kind="openrouter_models_api")
    rows = _openrouter_validated_rows(payload, kind="openrouter_models_api")
    models: list[ParsedModel] = []
    for index, row in enumerate(rows):
        model_id = str(row.get("id"))
        prefix = f"data[{index}]"
        locators: dict[str, str] = {}

        context_length = _safe_int(row.get("context_length"))
        if context_length is not None:
            locators["model:context_length"] = f"{prefix}.context_length"

        top_provider = row.get("top_provider")
        max_output_tokens: int | None = None
        if isinstance(top_provider, Mapping):
            max_output_tokens = _safe_int(top_provider.get("max_completion_tokens"))
            if max_output_tokens is not None:
                locators["model:max_output_tokens"] = f"{prefix}.top_provider.max_completion_tokens"

        architecture = row.get("architecture")
        input_modalities = (
            _string_list(architecture.get("input_modalities"))
            if isinstance(architecture, Mapping)
            else None
        )
        output_modalities = (
            _string_list(architecture.get("output_modalities"))
            if isinstance(architecture, Mapping)
            else None
        )
        text_modality: bool | None = None
        if input_modalities is not None and output_modalities is not None:
            text_modality = "text" in input_modalities and "text" in output_modalities
            locators["model:capability:text"] = f"{prefix}.architecture.input_modalities + output_modalities"

        deprecated: bool | None = None
        deprecation = row.get("deprecation")
        if isinstance(deprecation, Mapping) and isinstance(deprecation.get("is_deprecated"), bool):
            deprecated = deprecation["is_deprecated"]
            locators["model:deprecated"] = f"{prefix}.deprecation.is_deprecated"

        pricing = row.get("pricing") if isinstance(row.get("pricing"), Mapping) else {}
        prices: dict[str, Decimal] = {}
        extra_pricing: dict[str, str] = {}
        non_representable: dict[str, str] = {}
        dim_keys = {
            "input": "prompt",
            "cached_input": "input_cache_read",
            "output": "completion",
            "reasoning": "internal_reasoning",
        }
        for dim, key in dim_keys.items():
            if key in pricing:
                raw_cell = pricing.get(key)
                if not isinstance(raw_cell, str) or not _OPENROUTER_PRICE_SYNTAX.fullmatch(raw_cell.strip()):
                    raise SnapshotFormatError("openrouter_models_api:invalid_price")
                cell = raw_cell.strip()
                # 181: OpenRouter's documented -1 sentinel marks dynamic or
                # non-representable pricing. The row keeps its identity and
                # carries an explicit incomplete reason; the value is never
                # converted to zero or a guessed price, and the sentinel
                # does not poison complete supported siblings in the same
                # snapshot. Any other malformed value stays fail-closed.
                if cell == "-1":
                    non_representable[dim] = "negative_router_sentinel"
                    locators[f"pricing:{dim}:non_representable"] = f"{prefix}.pricing.{key}"
                    continue
                try:
                    prices[dim] = _openrouter_price_decimal(cell)
                except ValueError:
                    raise SnapshotFormatError("openrouter_models_api:invalid_price") from None
                locators[f"pricing:{dim}"] = f"{prefix}.pricing.{key}"
        # 181: observed billing dims outside the standard-v1 proposal
        # contract are recorded with their exact values and units and
        # explained in the report, never silently dropped. cache writes are
        # published per-token (converted to per-1m like the other dims);
        # web_search is published per call and kept as-is.
        for extra_dim, key in (
            ("cache_write", "input_cache_write"),
            ("cache_write_1h", "input_cache_write_1h"),
            ("web_search", "web_search"),
        ):
            if key in pricing:
                raw_cell = pricing.get(key)
                if not isinstance(raw_cell, str) or not _OPENROUTER_PRICE_SYNTAX.fullmatch(raw_cell.strip()):
                    raise SnapshotFormatError("openrouter_models_api:invalid_price")
                cell = raw_cell.strip()
                if cell == "-1":
                    non_representable[extra_dim] = "negative_router_sentinel"
                    locators[f"pricing:{extra_dim}:non_representable"] = f"{prefix}.pricing.{key}"
                    continue
                if extra_dim == "web_search":
                    # Per-call price: keep the published value as-is with
                    # value-level bounds (no per-1M conversion).
                    try:
                        amount = Decimal(cell)
                    except InvalidOperation:
                        raise SnapshotFormatError("openrouter_models_api:invalid_price") from None
                    if (
                        not amount.is_finite()
                        or amount < 0
                        or len(amount.as_tuple().digits) > 18
                        or amount >= _OPENROUTER_PER_1M_MAGNITUDE_CAP
                    ):
                        raise SnapshotFormatError("openrouter_models_api:invalid_price") from None
                    extra_pricing[extra_dim] = _decimal_to_string(amount)
                else:
                    try:
                        converted = _openrouter_price_decimal(cell)
                    except ValueError:
                        raise SnapshotFormatError("openrouter_models_api:invalid_price") from None
                    extra_pricing[extra_dim] = _decimal_to_string(converted)
                locators[f"pricing:{extra_dim}"] = f"{prefix}.pricing.{key}"
        # 181-b: the "request" key publishes a per-REQUEST charge (USD per
        # request). It is strictly parsed with the same value-level bounds
        # as the per-call dims (no per-1M conversion); a -1 sentinel is a
        # non-representable billable value (fail-closed), never zero.
        request_price: Decimal | None = None
        if "request" in pricing:
            raw_cell = pricing.get("request")
            if not isinstance(raw_cell, str) or not _OPENROUTER_PRICE_SYNTAX.fullmatch(raw_cell.strip()):
                raise SnapshotFormatError("openrouter_models_api:invalid_price")
            cell = raw_cell.strip()
            if cell == "-1":
                non_representable["request"] = "negative_router_sentinel"
                locators["pricing:request:non_representable"] = f"{prefix}.pricing.request"
            else:
                try:
                    amount = Decimal(cell)
                except InvalidOperation:
                    raise SnapshotFormatError("openrouter_models_api:invalid_price") from None
                if (
                    not amount.is_finite()
                    or amount < 0
                    or len(amount.as_tuple().digits) > 18
                    or amount >= _OPENROUTER_PER_1M_MAGNITUDE_CAP
                ):
                    raise SnapshotFormatError("openrouter_models_api:invalid_price") from None
                request_price = amount
                locators["pricing:request"] = f"{prefix}.pricing.request"
        # 181-b: published pricing keys outside the recognized set are
        # recorded on the row (never silently dropped) and fail closed at
        # eligibility; they are NOT a snapshot format error, so the row's
        # identity and the other dims remain observable and explainable.
        unknown_pricing_keys = tuple(sorted(set(pricing) - _OPENROUTER_PRICING_KEYS))
        # 181: the "overrides" key publishes contextual (long-context /
        # time-of-day) price tiers as a stringified list. The current
        # published shape is a string; any other shape is a format error
        # (fail-closed on format drift). The block count is recorded so
        # contextual billing is accounted for, never silently ignored and
        # never proposed (it cannot be represented flatly).
        pricing_overrides: int | None = None
        if "overrides" in pricing:
            raw_overrides = pricing.get("overrides")
            if isinstance(raw_overrides, list):
                # current published shape: a JSON array of override objects
                if (
                    not raw_overrides
                    or len(raw_overrides) > 16
                    or any(not isinstance(item, Mapping) for item in raw_overrides)
                    or any(
                        not (set(item) <= _OPENROUTER_OVERRIDE_KEYS)
                        or not any(key in item for key in _OPENROUTER_OVERRIDE_PRICE_KEYS)
                        for item in raw_overrides
                    )
                ):
                    raise SnapshotFormatError("openrouter_models_api:malformed_overrides")
                pricing_overrides = len(raw_overrides)
            elif isinstance(raw_overrides, str):
                # observed alternate shape: the same array as a stringified
                # list; bounded, and the block count is derived from the
                # bracket structure (never evaluated).
                if not (
                    len(raw_overrides) <= 4096
                    and raw_overrides.startswith("[")
                    and raw_overrides.endswith("]")
                ):
                    raise SnapshotFormatError("openrouter_models_api:malformed_overrides")
                pricing_overrides = len(_OPENROUTER_OVERRIDE_BLOCK.findall(raw_overrides))
            else:
                raise SnapshotFormatError("openrouter_models_api:malformed_overrides")
            if pricing_overrides is not None:
                locators["pricing:overrides"] = f"{prefix}.pricing.overrides"

        models.append(
            ParsedModel(
                provider="openrouter",
                model=model_id,
                context_length=context_length,
                max_output_tokens=max_output_tokens,
                prices=prices,
                price_currency="USD" if prices else None,
                text_modality=text_modality,
                deprecated=deprecated,
                locators=locators,
                parser="openrouter_models_api/v1",
                extra_pricing=extra_pricing,
                non_representable_prices=non_representable,
                pricing_overrides=pricing_overrides,
                request_price=request_price,
                unknown_pricing_keys=unknown_pricing_keys,
            )
        )
    if len(models) > MAX_MODELS_PER_SNAPSHOT:
        raise SnapshotFormatError("openrouter_models_api:too_many_models")
    return tuple(models)


def parse_openai_models_api_snapshot(evidence: bytes) -> tuple[ParsedModel, ...]:
    """Parse a cached OpenAI /v1/models payload: identity only.

    Rows are validated on the raw structure and duplicate ids are
    preserved: the set-based helper would erase duplicates before they
    could be checked, and a malformed row must never disappear through
    filtering. The Models API identity alone cannot prove a price, unit,
    or context limit; those fields stay None and only the model's
    presence is observable.
    """
    payload = _json_loads_bounded(evidence, kind="openai_models_api")
    if not isinstance(payload, Mapping):
        raise SnapshotFormatError("openai_models_api:not_an_object")
    data = payload.get("data")
    if not isinstance(data, list):
        raise SnapshotFormatError("openai_models_api:missing_data_array")
    if len(data) > MAX_JSON_ITEMS:
        raise SnapshotFormatError("openai_models_api:too_many_rows")
    models: list[ParsedModel] = []
    for index, row in enumerate(data):
        if not isinstance(row, Mapping):
            raise SnapshotFormatError("openai_models_api:malformed_row")
        model_id = _safe_openai_model_id(row.get("id"))
        if model_id is None:
            raise SnapshotFormatError("openai_models_api:invalid_model_id")
        models.append(
            ParsedModel(
                provider="openai",
                model=model_id,
                parser="openai_models_api/v1",
                identity_only=True,
                locators={"model:identity": f"data[{index}].id"},
            )
        )
    if len(models) > MAX_MODELS_PER_SNAPSHOT:
        raise SnapshotFormatError("openai_models_api:too_many_models")
    return tuple(models)


# --- 181: current official OpenAI pricing Markdown (tiered sections) --------
#
# The current official pricing page is Markdown with one table per billing
# tier ("### Standard pricing data", "### Batch pricing data", "### Flex
# pricing data", "### Fast pricing data"). Each table row is one model with
# Short-context and Long-context columns for input, cached input, cache
# writes and output. Tiers and context bands are BILLING CONTEXT, not
# alternative facts for the same price: a Standard short-context price and a
# Batch short-context price are different prices of the same model and must
# never be flattened, averaged, or let one override the other. Only the
# Standard tier short-context dims are representable by the standard-v1
# flat proposal contract; every other observed price keeps its exact
# tier/band context (qualified observation fields) or an explicit
# observed-not-proposed record.

_OPENAI_TIER_NAMES = ("standard", "batch", "flex", "fast")
_OPENAI_PRICE_HEADER_MAP = {
    "short context input": ("short", "input"),
    "short context cached input": ("short", "cached_input"),
    "short context cache writes": ("short", "cache_write"),
    "short context output": ("short", "output"),
    "long context input": ("long", "input"),
    "long context cached input": ("long", "cached_input"),
    "long context cache writes": ("long", "cache_write"),
    "long context output": ("long", "output"),
}
_OPENAI_TIER_HEADING = re.compile(
    r"^###\s+(" + "|".join(name.capitalize() for name in _OPENAI_TIER_NAMES) + r")\s+pricing\s+data\s*$",
    re.IGNORECASE,
)
# Anchor-less-per-line detection of the v2 format within a whole document
# (^/$ are line-anchored for this marker only).
_OPENAI_V2_FORMAT_MARKER = re.compile(
    r"^###\s+(?:Standard|Batch|Flex|Fast)\s+pricing\s+data\s*$",
    re.IGNORECASE | re.MULTILINE,
)
_OPENAI_MODEL_CELL_ANNOTATION = re.compile(r"^(?P<id>.+?)\s*\((?P<note>[^()]+)\)$")
# Context labels that may annotate a model cell in the current official
# pricing tables. They are BILLING/STATUS CONTEXT, not identity, and are
# preserved verbatim in the locator. Unknown labels are a format error
# (fail-closed on format drift), never a guess.
_OPENAI_CONTEXT_NOTE = re.compile(
    # The context-length label is published without a closing angle bracket
    # ("<272K context length") in the current official tables; match it exactly.
    r"^(?:<[0-9]+[KkMm]\s+context\s+length|data\s+sharing|legacy)$", re.IGNORECASE
)
_OPENAI_PRICE_VALUE = re.compile(r"^\$\s*(?P<amount>[0-9]+(?:\.[0-9]+)?)$")


# Syntactic model-identity validation for the v2 pricing tables:
# lowercase alphanumerics plus ".", "_" and "-", bounded, no leading or
# trailing separator. Deliberately NOT the legacy family allowlist
# (``_safe_openai_model_id``): that allowlist predates current published
# identities (it rejects the official "davinci-002"/"babbage-002" rows)
# and a name family is not an identity rule. Whether a model supports
# ordinary Chat is established by its official model-page endpoint
# contract, never by its name.
_OPENAI_V2_MODEL_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{0,199}$")


def _openai_v2_model_cell(cell: str) -> tuple[str, str | None]:
    """Canonical model id from a v2 pricing-table model cell.

    Current rows may carry a context-length annotation
    ("gpt-5.5 (<272K context length)"); the annotation is context, not
    identity, and is returned for the locator. Unknown cell shapes are a
    format error, never a guess.
    """
    text = cell.strip()
    match = _OPENAI_MODEL_CELL_ANNOTATION.fullmatch(text)
    if match is not None:
        note = match.group("note").strip()
        if not _OPENAI_CONTEXT_NOTE.fullmatch(note):
            raise SnapshotFormatError("openai_pricing_docs:unrecognized_model_annotation")
        candidate = match.group("id").strip()
    else:
        candidate = text
    if not _OPENAI_V2_MODEL_ID.fullmatch(candidate):
        raise SnapshotFormatError("openai_pricing_docs:invalid_model_id")
    return candidate, (match.group("note").strip() if match is not None else None)


def _openai_v2_price_cell(cell: str) -> Decimal | None:
    """Per-1m USD cell ("$10.00") or an explicit missing marker ("-")."""
    text = cell.strip()
    if text in ("-", ""):
        return None
    match = _OPENAI_PRICE_VALUE.fullmatch(text)
    if match is None:
        raise SnapshotFormatError("openai_pricing_docs:unrecognized_price_cell")
    return Decimal(match.group("amount"))


def _parse_openai_pricing_md_v2(text: str) -> tuple[ParsedModel, ...]:
    """Parse the current tiered Markdown pricing page (official shape)."""
    lines = text.splitlines()
    tier_rows: dict[str, dict[str, dict[str, Any]]] = {tier: {} for tier in _OPENAI_TIER_NAMES}
    table_count = 0
    total_data_rows = 0
    current_tier: str | None = None
    in_tier_table = False
    current_columns: list[tuple[str, str]] | None = None  # (band, dim) per cell
    row_in_table = 0
    for line in lines:
        stripped = line.strip()
        heading = _OPENAI_TIER_HEADING.match(stripped)
        if heading is not None:
            in_tier_table = True
            current_tier = heading.group(1).lower()
            current_columns = None
            row_in_table = 0
            continue
        if in_tier_table and not stripped.startswith("|"):
            # any non-table line ends the current tier table
            if stripped.startswith("#") or (stripped and not stripped.startswith(">")):
                in_tier_table = False
                current_columns = None
            continue
        if not in_tier_table or current_tier is None:
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if _is_separator_row(cells):
            continue
        if cells and cells[0].lower() == "model":
            table_count += 1
            if len(cells) < 2:
                raise SnapshotFormatError("openai_pricing_docs:empty_tier_table")
            columns: list[tuple[str, str]] = []
            for column in cells[1:]:
                key = column.lower()
                if key not in _OPENAI_PRICE_HEADER_MAP:
                    raise SnapshotFormatError("openai_pricing_docs:unrecognized_header")
                columns.append(_OPENAI_PRICE_HEADER_MAP[key])
            current_columns = columns
            continue
        if current_columns is None or len(cells) != len(current_columns) + 1:
            raise SnapshotFormatError("openai_pricing_docs:malformed_table_row")
        model_id, note = _openai_v2_model_cell(cells[0])
        row_in_table += 1
        total_data_rows += 1
        if total_data_rows > MAX_TABLE_ROWS:
            raise SnapshotFormatError("openai_pricing_docs:too_many_rows")
        row = tier_rows[current_tier].setdefault(
            model_id,
            {"prices": {}, "prices_long": {}, "extra": {}, "locators": {}, "note": None},
        )
        if row["note"] is None:
            row["note"] = note
        for cell, (band, dim) in zip(cells[1:], current_columns):
            value = _openai_v2_price_cell(cell)
            if value is None:
                continue
            locator = f"tier[{current_tier}].row[{row_in_table}].{dim}_{band}"
            if band == "short":
                if dim == "cache_write":
                    row["extra"]["cache_write"] = _decimal_to_string(value)
                else:
                    row["prices"][dim] = value
                row["locators"][f"pricing:{dim}"] = locator
            else:
                if dim == "cache_write":
                    row["extra"]["cache_write_long"] = _decimal_to_string(value)
                    row["locators"]["pricing:cache_write_long"] = locator
                else:
                    row["prices_long"][dim] = value
                    row["locators"][f"pricing_long:{dim}"] = locator
        if model_id in tier_rows[current_tier] and (
            len(tier_rows[current_tier][model_id]["prices"])
            + len(tier_rows[current_tier][model_id]["prices_long"])
            + len(tier_rows[current_tier][model_id]["extra"])
            == 0
        ):
            raise SnapshotFormatError("openai_pricing_docs:empty_model_row")
    models: list[ParsedModel] = []
    for tier in _OPENAI_TIER_NAMES:
        for model_id in sorted(tier_rows[tier]):
            row = tier_rows[tier][model_id]
            if not (row["prices"] or row["prices_long"] or row["extra"]):
                continue
            locators = dict(row["locators"])
            if row["note"] is not None:
                locators["model:context_annotation"] = f"tier[{tier}].row: {row['note']!r}"
            models.append(
                ParsedModel(
                    provider="openai",
                    model=model_id,
                    prices=dict(row["prices"]),
                    prices_long=dict(row["prices_long"]),
                    extra_pricing=dict(row["extra"]),
                    price_currency="USD"
                    if (row["prices"] or row["prices_long"])
                    else None,
                    billing_tier=tier,
                    context_band="short",
                    locators=locators,
                    parser="openai_pricing_docs/v2",
                )
            )
    if len(models) > MAX_MODELS_PER_SNAPSHOT * len(_OPENAI_TIER_NAMES):
        raise SnapshotFormatError("openai_pricing_docs:too_many_models")
    return tuple(models)


def parse_openai_pricing_docs_snapshot(evidence: bytes) -> tuple[ParsedModel, ...]:
    """Parse cached OpenAI pricing-docs tables (official docs shape).

    Two official formats are recognized deterministically:

    - v2 (current): Markdown with per-tier "### <Tier> pricing data"
      tables carrying Short/Long context columns. Every observed price
      keeps its tier and context band; only Standard short-context dims
      are emitted on the flat ``prices`` map that standard-v1 proposals
      bind to, long-band and cache-write prices are emitted on their own
      contextual fields, and non-Standard tiers are recorded as observed
      billing context, never flattened into Standard.
    - v1 (legacy): the previous single-table HTML shape, parsed by the
      reused ``_parse_openai_pricing_docs`` path (unchanged behavior).

    Values are per-1m USD as published; unknown cells are left missing,
    never invented; unrecognized headers or price cells are format
    errors (fail-closed), never guessed.
    """
    text = _decode_bounded(evidence, kind="openai_pricing_docs", max_bytes=MAX_SNAPSHOT_BYTES)
    if _OPENAI_V2_FORMAT_MARKER.search(text):
        return _parse_openai_pricing_md_v2(text)
    tables = _extract_tabular_blocks(text)
    total_rows = sum(max(0, len(table) - 1) for table in tables)
    if total_rows > MAX_TABLE_ROWS:
        raise SnapshotFormatError("openai_pricing_docs:too_many_rows")
    records = _parse_openai_pricing_docs(
        text=text, source_url="offline-replay", source_retrieved_at=""
    )
    models: list[ParsedModel] = []
    for record in records:
        locator = _locate_openai_pricing_row(
            tables, record.model_id, record.input_price_per_1m, record.output_price_per_1m
        )
        locators: dict[str, str] = {}
        prices: dict[str, Decimal] = {}
        for dim, value in (
            ("input", record.input_price_per_1m),
            ("cached_input", record.cached_input_price_per_1m),
            ("output", record.output_price_per_1m),
        ):
            if value is not None:
                prices[dim] = Decimal(value)
                locators[f"pricing:{dim}"] = locator
        text_modality: bool | None = None
        if record.modality is not None:
            text_modality = record.modality.strip().lower() == "text"
            locators["model:capability:text"] = locator
        models.append(
            ParsedModel(
                provider="openai",
                model=record.model_id,
                prices=prices,
                price_currency="USD" if prices else None,
                text_modality=text_modality,
                locators=locators,
                parser="openai_pricing_docs/v1",
            )
        )
    if len(models) > MAX_MODELS_PER_SNAPSHOT:
        raise SnapshotFormatError("openai_pricing_docs:too_many_models")
    return tuple(models)


_SEPARATOR_CELL = re.compile(r"^[-: ]+$")


def _is_separator_row(row: list[str]) -> bool:
    cells = [cell for cell in row if cell.strip()]
    return bool(cells) and all(_SEPARATOR_CELL.fullmatch(cell.strip()) for cell in cells)


def _locate_openai_pricing_row(
    tables: list[list[list[str]]], model_id: str, input_value: str | None, output_value: str | None
) -> str:
    """Align a parsed pricing record to its table/row using the same pure
    cell helpers the parser uses. Returns a structural locator string in
    which data rows are numbered from 1 after the header (separator rows
    excluded)."""
    for table_index, table in enumerate(tables):
        if not table:
            continue
        header = [cell.strip().lower() for cell in table[0]]
        if "model" not in header or "input" not in header:
            continue
        model_index = header.index("model")
        input_index = header.index("input")
        output_index = next(
            (idx for idx, value in enumerate(header) if value.startswith("output")), None
        )
        row_index = 0
        for row in table[1:]:
            if _is_separator_row(row):
                continue
            row_index += 1
            if len(row) <= model_index:
                continue
            if _safe_openai_model_id(row[model_index]) != model_id:
                continue
            row_input = _doc_price_cell(row[input_index] if input_index < len(row) else None)
            row_output = (
                _doc_price_cell(row[output_index] if output_index is not None and output_index < len(row) else None)
                if output_index is not None
                else None
            )
            if row_input == input_value and row_output == output_value:
                return f"table[{table_index}].row[{row_index}]"
    return "unresolved"


_OPENAI_INDEX_BULLET = re.compile(
    r"^- \[(?P<text>[^\]]+)\]\((?P<path>[^()\s]+)\)(?::\s*(?P<desc>.*?))?\s*$"
)
_OPENAI_INDEX_MODEL_PAGE = re.compile(r"^/api/docs/models/(?P<id>[^/]+)\.md$")
_OPENAI_INDEX_INLINE_MODEL_ID = re.compile(r"Model ID:\s*`(?P<id>[^`]+)`")


def _openai_index_ids(text: str) -> tuple[tuple[str, str], ...] | None:
    """Bounded identity extraction from the current linked-index format.

    The current official models index lists models as Markdown bullets
    whose link is the model page (``/api/docs/models/<id>.md``); the ID is
    the page path, NEVER the display name (display names include aliases
    that differ from API IDs). One documented exception links elsewhere
    (specialized models) and declares ``Model ID: `<id>``` inline in its
    description: exactly one such ID is accepted, zero or more than one
    deterministically skip the bullet (no guessing). Duplicates across
    sections deduplicate to the first occurrence. Returns None when the
    document is not in the linked-index format (legacy block handling).
    """
    found: list[tuple[str, str]] = []
    seen: set[str] = set()
    is_index_format = False
    for index, line in enumerate(text.splitlines()):
        match = _OPENAI_INDEX_BULLET.match(line.strip())
        if match is None:
            continue
        model_id: str | None = None
        page = _OPENAI_INDEX_MODEL_PAGE.fullmatch(match.group("path"))
        if page is not None:
            model_id = page.group("id")
        else:
            inline = _OPENAI_INDEX_INLINE_MODEL_ID.findall(match.group("desc") or "")
            if len(inline) == 1:
                model_id = inline[0]
        if model_id is None:
            continue
        if not _OPENAI_V2_MODEL_ID.fullmatch(model_id):
            raise SnapshotFormatError("openai_models_docs:invalid_model_id")
        is_index_format = True
        if model_id not in seen:
            seen.add(model_id)
            found.append((model_id, f"line[{index}]"))
    if not is_index_format:
        return None
    return tuple(found)


def parse_openai_models_docs_snapshot(evidence: bytes) -> tuple[ParsedModel, ...]:
    """Parse the official OpenAI models index (current linked-index format
    or the legacy block format): identity/limits, no prices.

    - current linked index (2026-09): ``- [Display](/api/docs/models/<id>.md)``
      bullets; identity-only rows (the per-model pages and the pricing
      document carry limits and prices), duplicates across the Featured
      and catalog sections deduplicated explicitly;
    - legacy block format (180/181-a fixtures): unchanged behavior.
    """
    text = _decode_bounded(evidence, kind="openai_models_docs", max_bytes=MAX_SNAPSHOT_BYTES)
    index_ids = _openai_index_ids(text)
    if index_ids is not None:
        if len(index_ids) > MAX_MODELS_PER_SNAPSHOT:
            raise SnapshotFormatError("openai_models_docs:too_many_models")
        return tuple(
            ParsedModel(
                provider="openai",
                model=model_id,
                identity_only=True,
                locators={"model:identity": locator},
                parser="openai_models_docs/v2",
            )
            for model_id, locator in index_ids
        )
    records = _parse_openai_models_docs(text=text, source_url="offline-replay")
    if len(records) > MAX_MODELS_PER_SNAPSHOT:
        raise SnapshotFormatError("openai_models_docs:too_many_models")
    out: list[ParsedModel] = []
    for index, record in enumerate(sorted(records.values(), key=lambda r: r.model_id)):
        locators: dict[str, str] = {}
        if record.context_length is not None:
            locators["model:context_length"] = f"model_block[{index}].context_length"
        if record.max_output_tokens is not None:
            locators["model:max_output_tokens"] = f"model_block[{index}].max_output_tokens"
        out.append(
            ParsedModel(
                provider="openai",
                model=record.model_id,
                context_length=record.context_length,
                max_output_tokens=record.max_output_tokens,
                locators=locators,
                parser="openai_models_docs/v1",
            )
        )
    return tuple(out)


_DOCTYPE_PATTERN = re.compile(r"<!DOCTYPE", re.IGNORECASE)


_OPENAI_DOC_MODEL_ID = re.compile(r"^Model ID:\s*`([^`]+)`\s*$")
_OPENAI_DOC_MODALITIES = re.compile(r"^-[ \t]*Input modalities:\s*(.+)$")
_OPENAI_DOC_OUTPUT_MODALITIES = re.compile(r"^-[ \t]*Output modalities:\s*(.+)$")
_OPENAI_DOC_CONTEXT = re.compile(r"^-[ \t]*([0-9][0-9,]*)\s*context window$")
_OPENAI_DOC_MAX_OUTPUT = re.compile(r"^-[ \t]*([0-9][0-9,]*)\s*max output tokens$")
_OPENAI_DOC_PRICE_ROW = re.compile(
    r"^\|\s*(?P<metric>Input|Cached input|Output|Cache writes)\s*\|\s*\$\s*"
    r"(?P<amount>[0-9]+(?:\.[0-9]+)?)\s*\|\s*1M tokens\s*\|\s*$",
    re.IGNORECASE,
)
_OPENAI_DOC_ENDPOINT_ROW = re.compile(
    r"^\|\s*(?P<endpoint>[^|]+?)\s*\|\s*`(?P<route>[^`]+)`\s*\|\s*(?P<support>Supported|Not supported)\s*\|\s*$"
)


def parse_openai_model_doc_snapshot(evidence: bytes) -> tuple[ParsedModel, ...]:
    """Parse ONE official OpenAI model doc page (Markdown, per model).

    The page is the model's official API contract: it declares the exact
    ``Model ID`` (identity binding), input/output modalities, context
    window, max output tokens, the endpoint support table (Chat
    Completions supported or not — the ordinary-Chat contract evidence,
    never inferred from the name or from text modality alone), and the
    per-model text-token prices (a second, model-scoped source for the
    Standard short-context prices). A page without a declared Model ID
    is malformed; an unexpected endpoint/support cell shape is a format
    error (fail-closed). No prices are invented for missing cells.
    """
    text = _decode_bounded(evidence, kind="openai_model_doc", max_bytes=MAX_SNAPSHOT_BYTES)
    lines = text.splitlines()
    model_id: str | None = None
    model_id_line: int | None = None
    input_modalities: tuple[str, ...] | None = None
    output_modalities: tuple[str, ...] | None = None
    context_length: int | None = None
    max_output_tokens: int | None = None
    locators: dict[str, str] = {}
    for index, line in enumerate(lines):
        stripped = line.strip()
        if model_id is None:
            match = _OPENAI_DOC_MODEL_ID.match(stripped)
            if match is not None:
                candidate = match.group(1).strip()
                if not _OPENAI_V2_MODEL_ID.fullmatch(candidate):
                    raise SnapshotFormatError("openai_model_doc:invalid_model_id")
                model_id = candidate
                model_id_line = index
                locators["model:identity"] = f"line[{index}]"
                continue
        modalities = _OPENAI_DOC_MODALITIES.match(stripped)
        if modalities is not None:
            if input_modalities is not None:
                raise SnapshotFormatError("openai_model_doc:ambiguous_details")
            input_modalities = tuple(
                item.strip().lower() for item in modalities.group(1).split(",") if item.strip()
            )
            locators["model:capability:text"] = f"line[{index}]"
            continue
        output = _OPENAI_DOC_OUTPUT_MODALITIES.match(stripped)
        if output is not None:
            if output_modalities is not None:
                raise SnapshotFormatError("openai_model_doc:ambiguous_details")
            output_modalities = tuple(
                item.strip().lower() for item in output.group(1).split(",") if item.strip()
            )
            continue
        context = _OPENAI_DOC_CONTEXT.match(stripped)
        if context is not None:
            value = int(context.group(1).replace(",", ""))
            if context_length is not None and context_length != value:
                raise SnapshotFormatError("openai_model_doc:ambiguous_details")
            context_length = value
            locators["model:context_length"] = f"line[{index}]"
            continue
        max_output = _OPENAI_DOC_MAX_OUTPUT.match(stripped)
        if max_output is not None:
            value = int(max_output.group(1).replace(",", ""))
            if max_output_tokens is not None and max_output_tokens != value:
                raise SnapshotFormatError("openai_model_doc:ambiguous_details")
            max_output_tokens = value
            locators["model:max_output_tokens"] = f"line[{index}]"
            continue
    if model_id is None or model_id_line is None:
        raise SnapshotFormatError("openai_model_doc:missing_model_id")
    text_modality: bool | None = None
    if input_modalities is not None and output_modalities is not None:
        text_modality = "text" in input_modalities and "text" in output_modalities
    chat_supported: bool | None = None
    prices: dict[str, Decimal] = {}
    extra_pricing: dict[str, str] = {}
    in_endpoints_table = False
    in_text_tokens_table = False
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("#"):
            heading = stripped.lstrip("#").strip().lower()
            in_endpoints_table = heading == "endpoints"
            in_text_tokens_table = heading in ("text tokens", "text-token pricing")
            continue
        if not in_endpoints_table and not in_text_tokens_table:
            continue
        if not stripped.startswith("|"):
            if stripped:
                in_endpoints_table = False
                in_text_tokens_table = False
            continue
        if in_endpoints_table:
            match = _OPENAI_DOC_ENDPOINT_ROW.match(stripped)
            if match is None:
                if stripped.lower().startswith("| endpoint") or _is_separator_row(
                    [cell.strip() for cell in stripped.strip("|").split("|")]
                ):
                    continue
                raise SnapshotFormatError("openai_model_doc:malformed_endpoint_row")
            if match.group("route").strip() == "v1/chat/completions":
                if chat_supported is not None:
                    raise SnapshotFormatError("openai_model_doc:ambiguous_endpoint_support")
                chat_supported = match.group("support").lower() == "supported"
                locators["endpoint:chat_completions"] = f"line[{index}]"
        elif in_text_tokens_table:
            match = _OPENAI_DOC_PRICE_ROW.match(stripped)
            if match is None:
                if stripped.lower().startswith("| metric") or _is_separator_row(
                    [cell.strip() for cell in stripped.strip("|").split("|")]
                ):
                    continue
                raise SnapshotFormatError("openai_model_doc:malformed_price_row")
            metric = match.group("metric").strip().lower()
            value = Decimal(match.group("amount"))
            if metric == "cache writes":
                # Observed extra billing dimension: recorded exactly like
                # the pricing document's cache-write column, never
                # proposed by standard-v1, never conflated with input.
                dim = "cache_write"
                if dim in extra_pricing and extra_pricing[dim] != _decimal_to_string(value):
                    raise SnapshotFormatError("openai_model_doc:conflicting_price_row")
                extra_pricing[dim] = _decimal_to_string(value)
                locators[f"pricing:{dim}"] = f"line[{index}]"
                continue
            dim = "cached_input" if metric == "cached input" else metric
            if dim in prices and prices[dim] != value:
                raise SnapshotFormatError("openai_model_doc:conflicting_price_row")
            prices[dim] = value
            locators[f"pricing:{dim}"] = f"line[{index}]"
    return (
        ParsedModel(
            provider="openai",
            model=model_id,
            context_length=context_length,
            max_output_tokens=max_output_tokens,
            prices=prices,
            extra_pricing=extra_pricing,
            price_currency="USD" if (prices or extra_pricing) else None,
            text_modality=text_modality,
            chat_supported=chat_supported,
            locators=locators,
            parser="openai_model_doc/v1",
        ),
    )


def parse_ecb_reference_xml_snapshot(evidence: bytes) -> tuple[ParsedFxQuote, ...]:
    """Parse supplied ECB reference-rate XML (pure offline, stdlib only).

    EUR is the implicit base: ``1 EUR = <rate> <currency>``. DOCTYPE
    declarations are rejected outright (entity expansion / XXE surface);
    malformed XML, missing dates, non-positive or non-decimal rates are
    format errors. No external entities are fetched or resolved.
    """
    text = _decode_bounded(evidence, kind="ecb_reference_xml", max_bytes=MAX_XML_BYTES)
    if _DOCTYPE_PATTERN.search(text):
        raise SnapshotFormatError("ecb_reference_xml:doctype_forbidden")
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        raise SnapshotFormatError("ecb_reference_xml:malformed_xml") from None

    cubes: list[ET.Element] = []

    def _walk(element: ET.Element) -> None:
        if element.tag.rsplit("}", 1)[-1] == "Cube":
            cubes.append(element)
        for child in element:
            _walk(child)

    _walk(root)
    quotes: list[ParsedFxQuote] = []
    for cube in cubes:
        time_attr = cube.get("time")
        # Only date-carrying Cubes without their own currency attribute are
        # quote containers; quoted Cubes carry currency+rate and are read as
        # children.
        if not time_attr or cube.get("currency") is not None:
            continue
        try:
            published = date.fromisoformat(time_attr.strip())
        except ValueError:
            raise SnapshotFormatError("ecb_reference_xml:bad_date") from None
        child_quotes = 0
        for child in cube:
            if child.tag.rsplit("}", 1)[-1] != "Cube":
                continue
            currency = child.get("currency")
            rate_text = child.get("rate")
            if not currency or not rate_text:
                raise SnapshotFormatError("ecb_reference_xml:malformed_quote")
            if not re.fullmatch(r"[A-Z]{3}", currency):
                raise SnapshotFormatError("ecb_reference_xml:bad_currency")
            try:
                rate = Decimal(rate_text.strip())
            except InvalidOperation:
                raise SnapshotFormatError("ecb_reference_xml:bad_rate") from None
            if not rate.is_finite() or rate <= 0:
                raise SnapshotFormatError("ecb_reference_xml:non_positive_rate")
            quotes.append(
                ParsedFxQuote(
                    base_currency="EUR",
                    quote_currency=currency,
                    rate=rate,
                    published_date=published,
                    locator=f"Cube@time={time_attr}/Cube@currency={currency}",
                    parser="ecb_reference_xml/v1",
                )
            )
            child_quotes += 1
        if child_quotes == 0:
            raise SnapshotFormatError("ecb_reference_xml:no_quotes")
    if len(quotes) > MAX_QUOTE_CURRENCIES:
        raise SnapshotFormatError("ecb_reference_xml:too_many_quotes")
    if not quotes:
        raise SnapshotFormatError("ecb_reference_xml:no_quotes")
    return tuple(quotes)


# --- registry -----------------------------------------------------------------

# (provider, source_kind) -> reviewed parser identity. The registry, not a
# caller-supplied extractor string, decides what is deterministic.
PARSER_IDS: dict[tuple[str, str], str] = {
    ("openrouter", "openrouter_models_api"): "openrouter_models_api/v1",
    ("openai", "openai_models_api"): "openai_models_api/v1",
    ("openai", "openai_pricing_docs"): "openai_pricing_docs/v1",
    ("openai", "openai_models_docs"): "openai_models_docs/v1",
    # 181: one official per-model doc page (endpoint contract + limits +
    # model-scoped text prices). "docs_page" is a generic approved kind;
    # the (openai, docs_page) pair is the only registered docs_page parser.
    ("openai", "docs_page"): "openai_model_doc/v1",
    ("ecb", "ecb_reference_xml"): "ecb_reference_xml/v1",
}


def has_deterministic_parser(provider: str, source_kind: str) -> bool:
    return (provider, source_kind) in PARSER_IDS


def parse_snapshot(
    provider: str, source_kind: str, evidence: bytes
) -> SnapshotParse:
    """Dispatch bounded parsing for one evidence blob. Safe code-only errors."""
    parser_id = PARSER_IDS.get((provider, source_kind), "")
    try:
        if (provider, source_kind) == ("openrouter", "openrouter_models_api"):
            models = parse_openrouter_models_snapshot(evidence)
            return SnapshotParse(provider, source_kind, True, None, models, (), parser_id)
        if (provider, source_kind) == ("openai", "openai_models_api"):
            models = parse_openai_models_api_snapshot(evidence)
            return SnapshotParse(provider, source_kind, True, None, models, (), parser_id)
        if (provider, source_kind) == ("openai", "openai_pricing_docs"):
            models = parse_openai_pricing_docs_snapshot(evidence)
            return SnapshotParse(provider, source_kind, True, None, models, (), parser_id)
        if (provider, source_kind) == ("openai", "openai_models_docs"):
            models = parse_openai_models_docs_snapshot(evidence)
            return SnapshotParse(provider, source_kind, True, None, models, (), parser_id)
        if (provider, source_kind) == ("openai", "docs_page"):
            models = parse_openai_model_doc_snapshot(evidence)
            return SnapshotParse(provider, source_kind, True, None, models, (), parser_id)
        if (provider, source_kind) == ("ecb", "ecb_reference_xml"):
            quotes = parse_ecb_reference_xml_snapshot(evidence)
            return SnapshotParse(provider, source_kind, True, None, (), quotes, parser_id)
        return SnapshotParse(provider, source_kind, False, "no_registered_parser", (), (), "")
    except SnapshotFormatError as exc:
        return SnapshotParse(provider, source_kind, False, exc.code, (), (), parser_id)


# --- observation derivation ----------------------------------------------------

def _parsed_model_signature(model: ParsedModel) -> tuple:
    """Full observed row identity, including 181 billing context.

    Two rows for one model ID with different tier/band context (e.g. the
    Standard and Batch tables of the official OpenAI pricing document)
    are distinct observed rows, not a self-contradiction: the signature
    therefore covers every observed field. Rows with the same context but
    different values still conflict and block.
    """
    return (
        model.billing_tier,
        model.context_band,
        tuple(sorted((dim, str(value)) for dim, value in model.prices.items())),
        tuple(sorted((dim, str(value)) for dim, value in model.prices_long.items())),
        tuple(sorted((dim, value) for dim, value in model.extra_pricing.items())),
        tuple(sorted((dim, value) for dim, value in model.non_representable_prices.items())),
        model.pricing_overrides,
        model.request_price,
        model.unknown_pricing_keys,
        model.chat_supported,
        model.context_length,
        model.max_output_tokens,
        model.text_modality,
        model.deprecated,
    )


def dedupe_parsed_models(parsed: SnapshotParse) -> tuple[list[ParsedModel], dict[str, tuple[str, int]]]:
    """Deduplicate rows of one parsed snapshot with explicit dispositions.

    Rows for one model ID are grouped by their FULL observed signature
    (181: including tier/band context, so one model legitimately appears
    once per billing table, e.g. Standard and Batch):

    - identical rows (same signature) deduplicate to one, reported as
      ``("identical", count)``;
    - distinct signatures are kept as distinct observed rows. Rows that
      share the same billing context but differ in values are a
      self-contradiction of one snapshot: they are reported as
      ``("conflict", count)`` and still surface as blocking
      ``source_observations_contradict`` findings through the
      observation-level contradiction check, never silently skipped.

    Returns ``(kept_models, {model_id: (kind, count)})``.
    """
    by_id: dict[str, list[ParsedModel]] = {}
    for model in parsed.models:
        by_id.setdefault(model.model, []).append(model)
    kept: list[ParsedModel] = []
    duplicates: dict[str, tuple[str, int]] = {}
    for model_id in sorted(by_id):
        rows = by_id[model_id]
        if len(rows) == 1:
            kept.append(rows[0])
            continue
        by_signature: dict[tuple, list[ParsedModel]] = {}
        for row in rows:
            by_signature.setdefault(_parsed_model_signature(row), []).append(row)
        if len(by_signature) == 1:
            kept.append(rows[0])
            duplicates[model_id] = ("identical", len(rows))
            continue
        # Distinct billing contexts are distinct observed rows (kept).
        for signature_rows in by_signature.values():
            kept.append(signature_rows[0])
            if len(signature_rows) > 1:
                # cannot happen: same signature rows dedup above; guard
                # keeps the accounting exact.
                duplicates[model_id] = ("identical", len(signature_rows))
        # Same-context contradictions: rows that agree on every context
        # dimension but disagree on values share no signature; detect them
        # by comparing context-only projections.
        def context_of(m: ParsedModel) -> tuple:
            return (
                m.billing_tier,
                m.context_band,
                tuple(sorted(m.extra_pricing)),
                tuple(sorted(m.non_representable_prices)),
                m.pricing_overrides,
                m.chat_supported,
                m.context_length,
                m.max_output_tokens,
                m.text_modality,
                m.deprecated,
            )
        by_context: dict[tuple, list[ParsedModel]] = {}
        for row in rows:
            by_context.setdefault(context_of(row), []).append(row)
        conflict_rows = [
            rows_for_context
            for rows_for_context in by_context.values()
            if len({ _parsed_model_signature(m) for m in rows_for_context }) > 1
        ]
        if conflict_rows:
            count = sum(len(rows_for_context) for rows_for_context in conflict_rows)
            duplicates[model_id] = ("conflict", count)
    kept.sort(key=lambda m: (m.model, m.billing_tier or "", m.context_band or ""))
    return kept, duplicates


# Observed-but-not-proposed billing dims carry their published unit;
# everything else observed on a price row is per-1M tokens.
EXTRA_DIM_UNITS: dict[str, str] = {
    "cache_write": "per_1m_tokens",
    "cache_write_long": "per_1m_tokens",
    "web_search": "per_request",
}


# --- 181-b: shared standard-v1 flat billing eligibility -----------------------
#
# One deterministic policy decides, from ALL authoritative observations of a
# model (every billing tier, every context band, every published pricing key),
# whether the standard-v1 flat proposal may carry it. The SAME function runs
# in the collector (exclusion with a machine reason before proposal) and in
# the validator (recomputation over the parsed official evidence, so a
# supplied/tampered bundle cannot bypass eligibility by dropping dimensions).
#
# Representable by the flat standard short-context contract: the core text
# dims (input / cached_input / output, per-1M) plus, when published as a
# positive charge, the reasoning dim (per-1M) and the per-request dim
# (per_request). Excluded (fail-closed, exact machine reason): published
# long-context standard prices, contextual override tiers, positive
# cache-write charges, unknown billing keys, source sentinels on billable
# dims, and conflicting billable observations. A legitimate zero is a
# no-charge, never a missing fact; an out-of-scope dimension is ignored ONLY
# under the explicit tested policy below, with the acceptance evidence
# surfaced, never silently.

REASON_LONG_CONTEXT_PRICES = "long_context_prices_unrepresentable"
REASON_CONTEXTUAL_OVERRIDES = "contextual_overrides_unrepresentable"
REASON_CACHE_WRITE_CHARGES = "cache_write_charges_unrepresentable"
REASON_UNKNOWN_BILLING_DIMENSION = "unknown_billing_dimension"
REASON_CONFLICTING_BILLING = "conflicting_billing_observation"
REASON_BILLING_SENTINEL = "negative_router_sentinel"

#: inventory reason codes that the billing decision itself verifies
BILLING_EXCLUSION_REASONS = frozenset(
    {
        REASON_LONG_CONTEXT_PRICES,
        REASON_CONTEXTUAL_OVERRIDES,
        REASON_CACHE_WRITE_CHARGES,
        REASON_UNKNOWN_BILLING_DIMENSION,
        REASON_CONFLICTING_BILLING,
        REASON_BILLING_SENTINEL,
    }
)


@dataclass(frozen=True)
class BillingDecision:
    """One model's standard-v1 flat billing eligibility (pure, deterministic).

    ``carried`` is (dimension, exact decimal string, unit) for every
    positive charge the flat proposal MUST carry; ``accepted_unreachable``
    carries the visible evidence for deliberately ignored out-of-scope
    charges (an explicit tested policy, never a silent drop).
    """

    eligible: bool
    reason_code: str | None = None
    detail: str | None = None
    carried: tuple[tuple[str, str, str], ...] = ()
    accepted_unreachable: tuple[str, ...] = ()


def _billing_positive(value: str) -> bool:
    try:
        decimal = Decimal(value)
    except InvalidOperation:
        return False
    return decimal.is_finite() and decimal > 0


def _router_billing_decision(rows: Sequence[ParsedModel]) -> BillingDecision:
    unknown = sorted({key for row in rows for key in row.unknown_pricing_keys})
    if unknown:
        return BillingDecision(
            False,
            REASON_UNKNOWN_BILLING_DIMENSION,
            "unknown billing dimension(s) in official pricing: " + ",".join(unknown[:4]),
        )
    for row in rows:
        if row.pricing_overrides:
            return BillingDecision(
                False,
                REASON_CONTEXTUAL_OVERRIDES,
                f"{row.pricing_overrides} contextual override block(s) publish prices the flat standard contract cannot represent",
            )
        for extra in ("cache_write", "cache_write_1h"):
            value = row.extra_pricing.get(extra)
            if value is not None and _billing_positive(value):
                return BillingDecision(
                    False,
                    REASON_CACHE_WRITE_CHARGES,
                    f"published {extra.replace('_', ' ')} charge {value} per 1M tokens is not billable in the flat standard-v1 contract",
                )
        for dim in (
            "input",
            "output",
            "cached_input",
            "reasoning",
            "request",
            "cache_write",
            "cache_write_1h",
            "web_search",
        ):
            if dim in row.non_representable_prices:
                return BillingDecision(
                    False,
                    REASON_BILLING_SENTINEL,
                    f"source -1 sentinel on billable {dim} pricing; the charge cannot be verified, fail-closed",
                )
    carried: dict[str, tuple[Decimal, str]] = {}
    unreachable: list[str] = []
    for row in rows:
        reasoning = row.prices.get("reasoning")
        if reasoning is not None and reasoning > 0:
            existing = carried.get("reasoning")
            if existing is not None and existing != (reasoning, "per_1m_tokens"):
                return BillingDecision(
                    False, REASON_CONFLICTING_BILLING, "conflicting reasoning charge observations"
                )
            carried["reasoning"] = (reasoning, "per_1m_tokens")
        request = row.request_price
        if request is not None and request > 0:
            existing = carried.get("request")
            if existing is not None and existing != (request, "per_request"):
                return BillingDecision(
                    False, REASON_CONFLICTING_BILLING, "conflicting request charge observations"
                )
            carried["request"] = (request, "per_request")
        web_search = row.extra_pricing.get("web_search")
        if web_search is not None and _billing_positive(web_search):
            unreachable.append(
                f"web_search per-call charge {web_search} accepted unreachable: hosted web search is "
                "a denied hosted operation in the standard-v1 profile"
            )
    return BillingDecision(
        True,
        None,
        None,
        tuple((dim, str(value), unit) for dim, (value, unit) in sorted(carried.items())),
        tuple(dict.fromkeys(unreachable)),
    )


def _openai_billing_decision(rows: Sequence[ParsedModel]) -> BillingDecision:
    # Non-standard tiers (batch/flex/fast) are distinct service variants of
    # the same model, not context bands of the standard contract: the
    # standard-v1 flat proposal bills the standard tier only, mirroring the
    # OpenRouter :batch service-variant handling. A model with ONLY
    # non-standard rows is handled by no_standard_short_prices, not here.
    for row in rows:
        if row.billing_tier not in (None, "standard"):
            continue
        if row.prices_long:
            dims = ",".join(sorted(row.prices_long)[:4])
            return BillingDecision(
                False,
                REASON_LONG_CONTEXT_PRICES,
                f"standard tier publishes long-context prices ({dims}); the flat standard proposal bills the short band only",
            )
        for extra in ("cache_write", "cache_write_long"):
            value = row.extra_pricing.get(extra)
            if value is not None and _billing_positive(value):
                return BillingDecision(
                    False,
                    REASON_CACHE_WRITE_CHARGES,
                    f"published {extra.replace('_', ' ')} charge {value} per 1M tokens is not billable in the flat standard-v1 contract",
                )
    return BillingDecision(True)


def standard_v1_billing_decision(
    provider: str, rows: Sequence[ParsedModel]
) -> BillingDecision:
    """Deterministic standard-v1 flat billing eligibility for one model.

    Considers EVERY observed row of the model (all billing tiers, all
    context bands, every published pricing key). Missing, negative
    sentinel, malformed, non-finite, conflicting and ambiguous billable
    values are fail-closed exclusions with an exact machine reason; a
    legitimate zero stays a documented no-charge; the accepted
    out-of-scope dimensions carry their tested-policy evidence.
    """
    if provider == "openrouter":
        return _router_billing_decision(rows)
    if provider == "openai":
        return _openai_billing_decision(rows)
    return BillingDecision(False, REASON_UNKNOWN_BILLING_DIMENSION, f"unsupported provider {provider!r}")


def _pricing_field_name(model: ParsedModel, dim: str, *, band: str | None = None, extra: bool = False) -> str:
    """181: observation field name with full billing context.

    Bare ``pricing:<dim>`` names are reserved for the proposal-representable
    context: sources without tier/band distinctions (OpenRouter, legacy
    single-table OpenAI) and the Standard tier short band. Every other
    observed price (other tiers, long band, extra dims) keeps its exact
    context in a qualified field, so it is fully accounted for in the
    report without ever binding to, or contradicting, a proposed
    standard short-context price.
    """
    effective_band = band if band is not None else (model.context_band or "short")
    if not extra and model.billing_tier in (None, "standard") and effective_band == "short":
        return f"pricing:{dim}"
    tier = model.billing_tier or "plain"
    return f"pricing:{dim}:{tier}:{effective_band}"


def derive_observations(source_key: str, parsed: SnapshotParse) -> tuple[Observation, ...]:
    """Derive typed observations from one successfully parsed snapshot.

    Observations are properties of the parsed bytes, never copies of proposed
    values. Independence accounting (duplicate URLs / aliases to identical
    bytes / repeated references are one observation, not two) happens in
    :func:`independent_digests` via the per-source content digests.

    181: prices carry their exact tier/band context (see
    :func:`_pricing_field_name`); extra observed dims and the model-page
    endpoint contract derive their own observations. Non-representable
    values (e.g. the OpenRouter -1 sentinel) derive no price observation
    at all — there is no value to bind — and are accounted for by the
    collection inventory instead.
    """
    if not parsed.ok:
        return ()
    observations: list[Observation] = []
    for model in parsed.models:
        for dim in sorted(model.prices):
            observations.append(
                Observation(
                    source_key=source_key,
                    provider=model.provider,
                    model=model.model,
                    field=_pricing_field_name(model, dim),
                    locator=model.locators.get(f"pricing:{dim}", "unresolved"),
                    value=str(model.prices[dim]),
                    unit="per_1m_tokens",
                    currency=model.price_currency,
                    parser=model.parser,
                )
            )
        for dim in sorted(model.prices_long):
            observations.append(
                Observation(
                    source_key=source_key,
                    provider=model.provider,
                    model=model.model,
                    field=_pricing_field_name(model, dim, band="long"),
                    locator=model.locators.get(f"pricing_long:{dim}", "unresolved"),
                    value=str(model.prices_long[dim]),
                    unit="per_1m_tokens",
                    currency=model.price_currency,
                    parser=model.parser,
                )
            )
        for dim in sorted(model.extra_pricing):
            band = "long" if dim.endswith("_long") else "short"
            observations.append(
                Observation(
                    source_key=source_key,
                    provider=model.provider,
                    model=model.model,
                    field=_pricing_field_name(model, dim, band=band, extra=True),
                    locator=model.locators.get(f"pricing:{dim}", "unresolved"),
                    value=model.extra_pricing[dim],
                    unit=EXTRA_DIM_UNITS.get(dim, "per_1m_tokens"),
                    currency=model.price_currency,
                    parser=model.parser,
                )
            )
        if model.request_price is not None:
            # 181-b: the per-request charge is a proposal-representable
            # billable dimension; publish its observation under the standard
            # short-context field name (the only context OpenRouter rows
            # carry) so a carried "request" dim can bind to it.
            effective_band = model.context_band or "short"
            request_field = (
                "pricing:request"
                if model.billing_tier in (None, "standard")
                and effective_band == "short"
                else f"pricing:request:{model.billing_tier or 'plain'}:{effective_band}"
            )
            observations.append(
                Observation(
                    source_key=source_key,
                    provider=model.provider,
                    model=model.model,
                    field=request_field,
                    locator=model.locators.get("pricing:request", "unresolved"),
                    value=str(model.request_price),
                    unit="per_request",
                    currency=model.price_currency,
                    parser=model.parser,
                )
            )
        if model.context_length is not None:
            observations.append(
                Observation(
                    source_key=source_key,
                    provider=model.provider,
                    model=model.model,
                    field="model:context_length",
                    locator=model.locators.get("model:context_length", "unresolved"),
                    value=str(model.context_length),
                    unit="none",
                    currency=None,
                    parser=model.parser,
                )
            )
        if model.max_output_tokens is not None:
            observations.append(
                Observation(
                    source_key=source_key,
                    provider=model.provider,
                    model=model.model,
                    field="model:max_output_tokens",
                    locator=model.locators.get("model:max_output_tokens", "unresolved"),
                    value=str(model.max_output_tokens),
                    unit="none",
                    currency=None,
                    parser=model.parser,
                )
            )
        if model.text_modality is not None:
            observations.append(
                Observation(
                    source_key=source_key,
                    provider=model.provider,
                    model=model.model,
                    field="model:capability:text",
                    locator=model.locators.get("model:capability:text", "unresolved"),
                    value="true" if model.text_modality else "false",
                    unit="none",
                    currency=None,
                    parser=model.parser,
                )
            )
        if model.deprecated is not None:
            observations.append(
                Observation(
                    source_key=source_key,
                    provider=model.provider,
                    model=model.model,
                    field="model:deprecated",
                    locator=model.locators.get("model:deprecated", "unresolved"),
                    value="true" if model.deprecated else "false",
                    unit="none",
                    currency=None,
                    parser=model.parser,
                )
            )
        if model.chat_supported is not None:
            observations.append(
                Observation(
                    source_key=source_key,
                    provider=model.provider,
                    model=model.model,
                    field="model:chat_supported",
                    locator=model.locators.get("endpoint:chat_completions", "unresolved"),
                    value="true" if model.chat_supported else "false",
                    unit="none",
                    currency=None,
                    parser=model.parser,
                )
            )
        if model.pricing_overrides is not None:
            observations.append(
                Observation(
                    source_key=source_key,
                    provider=model.provider,
                    model=model.model,
                    field="model:pricing_overrides",
                    locator=model.locators.get("pricing:overrides", "unresolved"),
                    value=str(model.pricing_overrides),
                    unit="none",
                    currency=None,
                    parser=model.parser,
                )
            )
    for quote in parsed.fx_quotes:
        observations.append(
            Observation(
                source_key=source_key,
                provider="ecb",
                model=f"{quote.base_currency}-{quote.quote_currency}",
                field="fx:rate",
                locator=quote.locator,
                value=str(quote.rate),
                unit="currency_pair",
                currency=quote.quote_currency,
                parser=quote.parser,
            )
        )
    return tuple(observations)


# --- normalization and canonical comparison -----------------------------------

def quantize_money(value: Decimal) -> Decimal:
    """Import-contract precision: Numeric(18,9), ROUND_HALF_UP."""
    return value.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def to_eur(value_per_1m: Decimal, currency: str | None, fx_to_eur: Mapping[str, Decimal]) -> Decimal:
    """Exact Decimal conversion to EUR per-1m using canonical native->EUR
    rates, then import-contract quantization. EUR values pass through.

    Raises ``KeyError`` when the currency has no verified native->EUR rate
    (the caller must then report the fact as unbound, never convert with an
    invented rate).
    """
    if currency is None or currency == _EUR:
        return quantize_money(value_per_1m)
    rate = fx_to_eur.get(currency)
    if rate is None:
        raise KeyError(currency)
    return quantize_money(value_per_1m * rate)


def observations_for(
    observations: tuple[Observation, ...],
    *,
    field_name: str,
    model_names: frozenset[str],
    provider: str,
) -> tuple[Observation, ...]:
    return tuple(
        observation
        for observation in observations
        if observation.field == field_name
        and observation.provider == provider
        and observation.model in model_names
    )


def independent_source_urls(observations: tuple[Observation, ...], urls: Mapping[str, str]) -> int:
    """Count of distinct official source URLs behind these observations.

    Repeated retrievals or aliases of the same official URL are one source,
    not independent corroboration - even when the content hashes of the
    repeated retrievals differ. Only distinct URLs count.
    """
    seen: set[str] = set()
    for observation in observations:
        seen.add(urls.get(observation.source_key, observation.source_key))
    return len(seen)


def contradicting_values(
    observations: tuple[Observation, ...],
    urls: Mapping[str, str],
    digests: Mapping[str, str],
    fx_to_eur: Mapping[str, Decimal],
) -> tuple[str, ...] | None:
    """Canonical values across distinct (URL, digest) snapshots for one field.

    Returns the distinct raw values when different supplied snapshots
    disagree, else None (agreement or a single snapshot). Comparison is
    canonical, not raw string spelling: money compares after exact EUR
    normalization (1 == 1.0); a value whose unit/currency is missing or
    whose FX rate is unbound cannot be assigned a currency by assertion -
    it is its own distinct marker, so unverifiable currencies never
    silently agree. Observations grouped by the same (URL, digest) pair
    (repeated references to identical bytes) never contradict themselves.
    """
    if not observations:
        return None
    pricing = observations[0].field.startswith("pricing:")
    by_group: dict[tuple[str, str], set[Decimal | str]] = {}
    raw_by_norm: dict[Decimal | str, str] = {}
    for observation in observations:
        url = urls.get(observation.source_key, observation.source_key)
        digest = digests.get(observation.source_key, observation.source_key)
        if pricing:
            try:
                normalized: Decimal | str = to_eur(Decimal(observation.value), observation.currency, fx_to_eur)
            except (InvalidOperation, KeyError):
                normalized = f"unresolvable:{observation.currency or 'unknown'}"
        else:
            normalized = observation.value
        by_group.setdefault((url, digest), set()).add(normalized)
        raw_by_norm.setdefault(normalized, observation.value)
    if len(by_group) <= 1:
        return None
    union: set[Decimal | str] = set()
    for values in by_group.values():
        union.update(values)
    if len(union) <= 1:
        return None
    return tuple(sorted(raw_by_norm.get(value, str(value)) for value in union))


# --- reconciliation -------------------------------------------------------------

def _observation_record(
    observation: Observation,
    urls: Mapping[str, str],
    digests: Mapping[str, str],
    source_times: Mapping[str, str],
    fx_info: Mapping[str, Mapping[str, Any]],
    fx_to_eur: Mapping[str, Decimal],
) -> dict[str, Any]:
    """Serializable record of one actual derived observation (D5)."""
    normalized: str | None = None
    conversion: str | None = None
    if observation.field.startswith("pricing:") and observation.unit == "per_1m_tokens":
        try:
            normalized = str(to_eur(Decimal(observation.value), observation.currency, fx_to_eur))
            if observation.currency is None:
                conversion = "none"
            elif observation.currency == _EUR:
                conversion = "identity (EUR)"
            else:
                info = fx_info.get(observation.currency, {})
                direction = "reciprocal of verified quote" if info.get("derived_reciprocal") else "verified quote"
                conversion = (
                    f"{observation.currency} to EUR at {fx_to_eur.get(observation.currency)} "
                    f"({info.get('pair', 'verified FX binding')}, {direction}, quote date {info.get('quote_date', 'n/a')})"
                )
        except (InvalidOperation, KeyError):
            normalized = None
            conversion = "UNRESOLVED (no verified FX binding for this currency)"
    return {
        "source": observation.source_key,
        "url": urls.get(observation.source_key, ""),
        "digest": digests.get(observation.source_key, ""),
        "retrieved_at": source_times.get(observation.source_key, ""),
        "parser": observation.parser,
        "locator": observation.locator,
        "observed_value": observation.value,
        "unit": observation.unit,
        "currency": observation.currency,
        "normalized_eur": normalized,
        "conversion": conversion,
    }


def reconcile_model_facts(
    *,
    provider: str,
    binding_model: str,
    proposed: Mapping[str, Any],
    observations: tuple[Observation, ...],
    official_source_keys: frozenset[str],
    declared_sources: Mapping[str, frozenset[str]],
    fx_to_eur: Mapping[str, Decimal],
    urls: Mapping[str, str],
    digests: Mapping[str, str],
    source_times: Mapping[str, str],
    fx_info: Mapping[str, Mapping[str, Any]],
    required_price_dims: tuple[str, ...] = ("input", "output"),
) -> tuple[list[ReconciliationFinding], dict[str, BackedFact], set[str], set[str]]:
    """Reconcile proposed financial/capability/limit facts against parsed
    observations for one (provider, binding model).

    ``binding_model`` is the route's effective upstream model: provider
    facts bind to provider + actual upstream model, and a public alias is
    local routing policy, not a model whose price can be borrowed.

    ``proposed`` maps field names to specs:
      pricing:<dim> -> {"value": str|None, "currency": str, "required": bool}
      model:<field> -> int | bool (only fields that are actually proposed)

    Each field is validated against the sources its own fact declares
    (``declared_sources``): referenced-but-wrong field/model/provider
    evidence blocks, and a match that exists only in an undeclared source
    is a reference mismatch, never a silent repair. Authoritative
    conflicts are detected across ALL official observations for the
    (provider, binding model, field) context, so selective citation cannot
    hide a conflicting supplied observation.

    Matching uses canonical semantics: money compares in EUR after exact
    Decimal conversion with import-contract quantization (1 == 1.0).
    Observations with a missing currency or an unbound FX rate cannot be
    assigned a currency by assertion and never verify a fact. Only
    OFFICIAL-classified observations (approved publisher/kind/parser/host,
    digest-verified bytes, successful deterministic parse) can verify a
    fact; operator/semantic provenance never does.

    Returns (findings, backed, unresolved_required_fields, missing_fx_currencies).
    """
    findings: list[ReconciliationFinding] = []
    backed: dict[str, BackedFact] = {}
    unresolved: set[str] = set()
    missing_fx: set[str] = set()

    model_names = frozenset({binding_model})

    def _fx_convert(value: str, currency: str | None) -> Decimal | None:
        try:
            return to_eur(Decimal(value), currency, fx_to_eur)
        except (InvalidOperation, KeyError):
            if isinstance(currency, str) and currency not in (_EUR, ""):
                missing_fx.add(currency)
            return None

    def _field_observations(field_name: str) -> tuple[tuple[Observation, ...], tuple[Observation, ...]]:
        all_obs = observations_for(
            observations, field_name=field_name, model_names=model_names, provider=provider
        )
        official_all = tuple(o for o in all_obs if o.source_key in official_source_keys)
        declared = declared_sources.get(field_name, frozenset())
        official_declared = tuple(o for o in official_all if o.source_key in declared)
        return official_all, official_declared

    def _record(observation: Observation) -> dict[str, Any]:
        return _observation_record(observation, urls, digests, source_times, fx_info, fx_to_eur)

    for field_name in sorted(proposed):
        spec = proposed[field_name]
        if spec is None:
            continue
        if field_name.startswith("pricing:"):
            if not isinstance(spec, Mapping):
                continue
            value = spec.get("value")
            currency = spec.get("currency")
            dim = field_name.split(":", 1)[1]
            required = bool(spec.get("required")) or dim in required_price_dims
            if value is None:
                continue  # proposed null dimension: nothing to bind
            official_all, official_declared = _field_observations(field_name)
            contradict = contradicting_values(official_all, urls, digests, fx_to_eur)
            if contradict is not None:
                findings.append(
                    ReconciliationFinding(
                        "BLOCKER",
                        "source_observations_contradict",
                        f"supplied official snapshots disagree on {field_name} for {provider}/{binding_model}: "
                        + ", ".join(contradict[:4])
                        + ("" if len(contradict) <= 4 else f" (+{len(contradict) - 4} more)"),
                        provider,
                        binding_model,
                    )
                )
                unresolved.add(field_name)
                continue
            proposed_eur = _fx_convert(value, currency)
            matching: list[Observation] = []
            if proposed_eur is not None:
                for observation in official_declared:
                    observed_eur = _fx_convert(observation.value, observation.currency)
                    if observed_eur is not None and observed_eur == proposed_eur:
                        matching.append(observation)
            if matching:
                backed[field_name] = BackedFact(
                    field=field_name,
                    proposed=value,
                    proposed_normalized=str(proposed_eur) if proposed_eur is not None else None,
                    backed_by=tuple(obs.source_key for obs in matching),
                    independent_sources=independent_source_urls(tuple(matching), urls),
                    observations=tuple(_record(obs) for obs in matching[:8]),
                )
                continue
            if proposed_eur is None:
                if required:
                    # missing_fx already carries the currency; the model is
                    # blocked via fx_evidence_unbound, never converted with
                    # an invented rate.
                    unresolved.add(field_name)
                else:
                    findings.append(
                        ReconciliationFinding(
                            "REVIEW",
                            "source_evidence_unsupported",
                            f"optional {field_name} for {provider}/{binding_model} proposed in {currency or 'unknown currency'} "
                            "has no verified FX rate and cannot be bound",
                            provider,
                            binding_model,
                        )
                    )
                    unresolved.add(field_name)
                continue
            undeclared_match = any(
                (obs_eur := _fx_convert(observation.value, observation.currency)) is not None
                and obs_eur == proposed_eur
                for observation in official_all
                if observation.source_key not in declared_sources.get(field_name, frozenset())
            )
            if undeclared_match:
                findings.append(
                    ReconciliationFinding(
                        "BLOCKER",
                        "source_evidence_reference_mismatch",
                        f"proposed {field_name} matches an official snapshot observation that is not among the "
                        f"fact's declared sources for {provider}/{binding_model}; per-field references must bind "
                        "the supporting evidence",
                        provider,
                        binding_model,
                    )
                )
                unresolved.add(field_name)
                continue
            unresolvable_declared = any(
                _fx_convert(observation.value, observation.currency) is None for observation in official_declared
            )
            if official_declared and not unresolvable_declared:
                findings.append(
                    ReconciliationFinding(
                        "BLOCKER",
                        "source_evidence_value_mismatch",
                        f"proposed {field_name}={value} {currency or ''} does not match any parsed observation "
                        f"from its declared sources for {provider}/{binding_model}",
                        provider,
                        binding_model,
                    )
                )
            else:
                findings.append(
                    ReconciliationFinding(
                        "BLOCKER" if required else "REVIEW",
                        "source_evidence_unsupported",
                        f"{'required ' if required else 'optional '}{field_name} for {provider}/{binding_model} has no "
                        "verified snapshot observation from its declared sources (a matching digest of arbitrary "
                        "bytes, a semantic label, or another model's observations is not evidence)",
                        provider,
                        binding_model,
                    )
                )
            unresolved.add(field_name)
            continue
        # --- non-pricing model/capability fields ---------------------------
        value = spec if not isinstance(spec, Mapping) else spec.get("value")
        if value is None:
            continue
        official_all, official_declared = _field_observations(field_name)
        contradict = contradicting_values(official_all, urls, digests, fx_to_eur)
        if contradict is not None:
            findings.append(
                ReconciliationFinding(
                    "BLOCKER",
                    "source_observations_contradict",
                    f"supplied official snapshots disagree on {field_name} for {provider}/{binding_model}: "
                    + ", ".join(contradict[:4]),
                    provider,
                    binding_model,
                )
            )
            unresolved.add(field_name)
            continue
        canonical = "true" if value is True else ("false" if value is False else str(value))
        matching = [observation for observation in official_declared if observation.value == canonical]
        if matching:
            backed[field_name] = BackedFact(
                field=field_name,
                proposed=canonical,
                proposed_normalized=canonical,
                backed_by=tuple(obs.source_key for obs in matching),
                independent_sources=independent_source_urls(tuple(matching), urls),
                observations=tuple(_record(obs) for obs in matching[:8]),
            )
            continue
        undeclared_match = any(
            observation.value == canonical
            for observation in official_all
            if observation.source_key not in declared_sources.get(field_name, frozenset())
        )
        if undeclared_match:
            findings.append(
                ReconciliationFinding(
                    "BLOCKER",
                    "source_evidence_reference_mismatch",
                    f"proposed {field_name}={canonical} matches an official snapshot observation that is not "
                    f"among the fact's declared sources for {provider}/{binding_model}",
                    provider,
                    binding_model,
                )
            )
            unresolved.add(field_name)
            continue
        if official_declared:
            findings.append(
                ReconciliationFinding(
                    "BLOCKER",
                    "source_evidence_value_mismatch",
                    f"proposed {field_name}={canonical} does not match parsed observations from its declared "
                    f"sources for {provider}/{binding_model}",
                    provider,
                    binding_model,
                )
            )
        else:
            findings.append(
                ReconciliationFinding(
                    "BLOCKER",
                    "source_evidence_unsupported",
                    f"proposed {field_name}={canonical} for {provider}/{binding_model} has no verified snapshot "
                    "observation from its declared sources (a semantic label is not evidence)",
                    provider,
                    binding_model,
                )
            )
        unresolved.add(field_name)
    return findings, backed, unresolved, missing_fx
