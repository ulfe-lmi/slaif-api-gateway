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
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Mapping

# Bounded provider-catalog pure helpers (reused, not duplicated).
from slaif_gateway.services.provider_catalog_proposal import (
    _convert_openrouter_price,
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


# Bounded raw decimal cell: official per-token price cells are short
# decimal strings. Digits and exponents are bounded before the reused
# conversion helper so hostile exponents cannot trigger huge allocations
# or uncaught Decimal errors during normalization.
_BOUNDED_PRICE_CELL = re.compile(r"^[+-]?(?:\d{1,18}(?:\.\d{1,15})?|\.\d{1,15})(?:[eE][+-]?\d{1,3})?$")


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
    skip), then ``_convert_openrouter_price`` is reused for exact
    per-token -> per-million USD conversion of bounded decimal cells.
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
        dim_keys = {
            "input": "prompt",
            "cached_input": "input_cache_read",
            "output": "completion",
            "reasoning": "internal_reasoning",
        }
        for dim, key in dim_keys.items():
            if key in pricing:
                raw_cell = pricing.get(key)
                if not isinstance(raw_cell, str) or not _BOUNDED_PRICE_CELL.fullmatch(raw_cell.strip()):
                    raise SnapshotFormatError("openrouter_models_api:invalid_price")
                try:
                    per_1m = _convert_openrouter_price(raw_cell.strip(), allow_zero=True)
                except (ValueError, InvalidOperation, OverflowError):
                    raise SnapshotFormatError("openrouter_models_api:invalid_price") from None
                if per_1m is not None:
                    prices[dim] = Decimal(per_1m)
                    locators[f"pricing:{dim}"] = f"{prefix}.pricing.{key}"

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


def parse_openai_pricing_docs_snapshot(evidence: bytes) -> tuple[ParsedModel, ...]:
    """Parse cached OpenAI pricing-docs tables (official docs shape).

    Reuses ``_parse_openai_pricing_docs`` for record extraction and
    ``_extract_tabular_blocks`` + ``_doc_price_cell`` +
    ``_safe_openai_model_id`` for deterministic row/field locators. Values
    are per-1m USD as published; unknown cells are left missing, never
    invented.
    """
    text = _decode_bounded(evidence, kind="openai_pricing_docs", max_bytes=MAX_SNAPSHOT_BYTES)
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


def parse_openai_models_docs_snapshot(evidence: bytes) -> tuple[ParsedModel, ...]:
    """Parse cached OpenAI model docs blocks: limits/identity, no prices."""
    text = _decode_bounded(evidence, kind="openai_models_docs", max_bytes=MAX_SNAPSHOT_BYTES)
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
        if (provider, source_kind) == ("ecb", "ecb_reference_xml"):
            quotes = parse_ecb_reference_xml_snapshot(evidence)
            return SnapshotParse(provider, source_kind, True, None, (), quotes, parser_id)
        return SnapshotParse(provider, source_kind, False, "no_registered_parser", (), (), "")
    except SnapshotFormatError as exc:
        return SnapshotParse(provider, source_kind, False, exc.code, (), (), parser_id)


# --- observation derivation ----------------------------------------------------

def _parsed_model_signature(model: ParsedModel) -> tuple:
    return (
        tuple(sorted((dim, str(value)) for dim, value in model.prices.items())),
        model.context_length,
        model.max_output_tokens,
        model.text_modality,
        model.deprecated,
    )


def dedupe_parsed_models(parsed: SnapshotParse) -> tuple[list[ParsedModel], dict[str, tuple[str, int]]]:
    """Deduplicate rows of one parsed snapshot with explicit dispositions.

    Identical duplicate rows (same observed values) are deduplicated and
    reported as ``("identical", count)``; rows for the same model id with
    conflicting values are dropped from observations and reported as
    ``("conflict", count)`` - a single snapshot contradicting itself must
    block, not skip. Returns ``(kept_models, {model_id: (kind, count)})``.
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
        if len({_parsed_model_signature(m) for m in rows}) == 1:
            kept.append(rows[0])
            duplicates[model_id] = ("identical", len(rows))
        else:
            duplicates[model_id] = ("conflict", len(rows))
    kept.sort(key=lambda m: m.model)
    return kept, duplicates


def derive_observations(source_key: str, parsed: SnapshotParse) -> tuple[Observation, ...]:
    """Derive typed observations from one successfully parsed snapshot.

    Observations are properties of the parsed bytes, never copies of proposed
    values. Independence accounting (duplicate URLs / aliases to identical
    bytes / repeated references are one observation, not two) happens in
    :func:`independent_digests` via the per-source content digests.
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
                    field=f"pricing:{dim}",
                    locator=model.locators.get(f"pricing:{dim}", "unresolved"),
                    value=str(model.prices[dim]),
                    unit="per_1m_tokens",
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
