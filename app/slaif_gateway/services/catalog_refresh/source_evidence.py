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
    _openrouter_models_from_payload,
    _parse_openai_models_api,
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
    """One proposed fact with its deterministic (or review-only) backing."""

    field: str
    proposed: str
    backed_by: tuple[str, ...]      # source keys with a matching observation
    independent_sources: int        # distinct snapshot digests among the matchers
    semantic_only: bool             # True: review-only backing, never verified


# --- deterministic parsers ---------------------------------------------------

def _decode_bounded(evidence: bytes, *, kind: str, max_bytes: int) -> str:
    if len(evidence) > max_bytes:
        raise SnapshotFormatError(f"{kind}:snapshot_too_large")
    try:
        return evidence.decode("utf-8")
    except UnicodeDecodeError:
        raise SnapshotFormatError(f"{kind}:not_utf8") from None


def _json_loads_bounded(evidence: bytes, *, kind: str) -> Any:
    text = _decode_bounded(evidence, kind=kind, max_bytes=MAX_SNAPSHOT_BYTES)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        raise SnapshotFormatError(f"{kind}:malformed_json") from None


def _openrouter_rows(payload: Any, *, kind: str) -> list[Mapping[str, object]]:
    """Row selection for an OpenRouter-style payload; a payload without
    ``data[]`` (e.g. ``{}``) is a format error, never a bare traceback."""
    if not isinstance(payload, Mapping):
        raise SnapshotFormatError(f"{kind}:not_an_object")
    try:
        return _openrouter_models_from_payload(payload)
    except ValueError:
        raise SnapshotFormatError(f"{kind}:missing_data_array") from None


def _openai_model_ids(payload: Any, *, kind: str) -> set[str]:
    if not isinstance(payload, Mapping):
        raise SnapshotFormatError(f"{kind}:not_an_object")
    try:
        return _parse_openai_models_api(payload)
    except ValueError:
        raise SnapshotFormatError(f"{kind}:missing_data_array") from None


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

    Reuses ``_openrouter_models_from_payload`` for row selection and
    ``_convert_openrouter_price`` for exact per-token -> per-million USD
    conversion. Pricing cells are per-token USD strings in the official
    shape; they are normalized to per-million USD with exact Decimal
    arithmetic (the SLAIF import-contract unit). Rows lacking a safe model
    id are skipped; a payload without ``data[]`` is malformed.
    """
    payload = _json_loads_bounded(evidence, kind="openrouter_models_api")
    rows = _openrouter_rows(payload, kind="openrouter_models_api")
    if len(rows) > MAX_JSON_ITEMS:
        raise SnapshotFormatError("openrouter_models_api:too_many_rows")
    models: list[ParsedModel] = []
    for index, row in enumerate(rows):
        raw_id = row.get("id")
        if not isinstance(raw_id, str) or not raw_id or len(raw_id) > 200:
            continue
        model_id = raw_id
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
                try:
                    per_1m = _convert_openrouter_price(pricing.get(key), allow_zero=True)
                except ValueError:
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

    The Models API identity alone cannot prove a price, unit, or context
    limit; those fields stay None and only the model's presence is observable.
    """
    payload = _json_loads_bounded(evidence, kind="openai_models_api")
    ids = _openai_model_ids(payload, kind="openai_models_api")
    if len(ids) > MAX_MODELS_PER_SNAPSHOT:
        raise SnapshotFormatError("openai_models_api:too_many_models")
    return tuple(
        ParsedModel(
            provider="openai",
            model=model_id,
            parser="openai_models_api/v1",
            identity_only=True,
        )
        for model_id in sorted(ids)
    )


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


def independent_digests(observations: tuple[Observation, ...], digests: Mapping[str, str]) -> int:
    """Count of distinct snapshot content digests behind these observations.

    Duplicate URLs, aliases to identical bytes, or repeated references to one
    snapshot are one digest, not independent corroboration.
    """
    seen: set[str] = set()
    for observation in observations:
        digest = digests.get(observation.source_key)
        if digest is not None:
            seen.add(digest)
    return len(seen)


def contradicting_values(
    observations: tuple[Observation, ...], digests: Mapping[str, str]
) -> tuple[str, ...] | None:
    """Canonical values across DISTINCT snapshots for one field.

    Returns the distinct values when different snapshots disagree, else None
    (agreement or a single snapshot). Comparison is canonical, not raw string
    spelling: money compares as Decimal (1 == 1.0); a single snapshot with
    multiple source records (repeated references) never contradicts itself.
    """
    if not observations:
        return None
    numeric_field = observations[0].field.startswith("pricing:")
    by_digest_value: dict[str, set[Decimal | str]] = {}
    for observation in observations:
        digest = digests.get(observation.source_key, observation.source_key)
        if numeric_field:
            try:
                value: Decimal | str = Decimal(observation.value)
            except InvalidOperation:
                value = observation.value
        else:
            value = observation.value
        by_digest_value.setdefault(digest, set()).add(value)
    if len(by_digest_value) <= 1:
        return None
    union: set[Decimal | str] = set()
    for values in by_digest_value.values():
        union.update(values)
    if len(union) <= 1:
        return None
    return tuple(sorted(str(value) for value in union))


# --- reconciliation -------------------------------------------------------------

def reconcile_model_facts(
    *,
    provider: str,
    model: str,
    upstream_model: str | None,
    proposed: Mapping[str, Any],
    observations: tuple[Observation, ...],
    official_source_keys: frozenset[str],
    semantic_provenance: bool,
    fx_to_eur: Mapping[str, Decimal],
    digests: Mapping[str, str],
    required_price_dims: tuple[str, ...] = ("input", "output"),
) -> tuple[list[ReconciliationFinding], dict[str, BackedFact], set[str], set[str]]:
    """Reconcile proposed financial/capability/limit facts against parsed
    observations for one (provider, model).

    ``proposed`` maps field names to specs:
      pricing:<dim> -> {"value": str|None, "currency": str, "required": bool}
      model:<field> -> int | bool (only fields that are actually proposed;
      None/False values are no claims and are not passed in)

    Matching uses canonical semantics: money is compared in EUR after exact
    Decimal conversion with import-contract quantization (1 == 1.0; a USD
    observation and a EUR proposal agree when the verified FX rate makes
    them equal). Only observations from OFFICIAL-classified sources
    (approved publisher/kind/parser/host, digest-verified bytes, successful
    deterministic parse) can verify a fact. Observations from
    operator/semantic sources never verify: they can at most keep a fact in
    REVIEW (the documented operator-input policy). Observations from any
    other unapproved source cannot establish trust.

    Returns (findings, backed, unresolved_required_fields, missing_fx_currencies).
    """
    findings: list[ReconciliationFinding] = []
    backed: dict[str, BackedFact] = {}
    unresolved: set[str] = set()
    missing_fx: set[str] = set()

    names = {model}
    if upstream_model and upstream_model != model:
        names.add(upstream_model)
    model_names = frozenset(names)

    def _fx_convert(value: str, currency: str | None) -> Decimal | None:
        try:
            return to_eur(Decimal(value), currency, fx_to_eur)
        except (InvalidOperation, KeyError):
            if isinstance(currency, str) and currency not in (_EUR, ""):
                missing_fx.add(currency)
            return None

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
            field_obs = observations_for(
                observations, field_name=field_name, model_names=model_names, provider=provider
            )
            official_obs = tuple(
                observation for observation in field_obs if observation.source_key in official_source_keys
            )
            if official_obs:
                contradict = contradicting_values(official_obs, digests)
                if contradict is not None:
                    findings.append(
                        ReconciliationFinding(
                            "BLOCKER",
                            "source_observations_contradict",
                            f"distinct snapshots disagree on {field_name}: {', '.join(contradict[:4])}",
                            provider,
                            model,
                        )
                    )
                    unresolved.add(field_name)
                    continue
                proposed_eur = _fx_convert(value, currency)
                if proposed_eur is None:
                    continue
                matching = []
                for observation in official_obs:
                    observed_eur = _fx_convert(observation.value, observation.currency)
                    if observed_eur is not None and observed_eur == proposed_eur:
                        matching.append(observation)
                if matching:
                    backed[field_name] = BackedFact(
                        field=field_name,
                        proposed=value,
                        backed_by=tuple(obs.source_key for obs in matching),
                        independent_sources=independent_digests(matching, digests),
                        semantic_only=False,
                    )
                else:
                    findings.append(
                        ReconciliationFinding(
                            "BLOCKER",
                            "source_evidence_value_mismatch",
                            f"proposed {field_name}={value} {currency or ''} does not match any parsed official snapshot value for {provider}/{model}",
                            provider,
                            model,
                        )
                    )
                    unresolved.add(field_name)
            else:
                non_official_match = False
                if field_obs:
                    proposed_eur = _fx_convert(value, currency)
                    if proposed_eur is not None:
                        non_official_match = any(
                            _fx_convert(observation.value, observation.currency) == proposed_eur
                            for observation in field_obs
                        )
                if semantic_provenance:
                    findings.append(
                        ReconciliationFinding(
                            "REVIEW",
                            "source_evidence_semantic_only",
                            f"{field_name} for {provider}/{model} has no verified deterministic observation; operator/semantic provenance is review-only"
                            + ("" if non_official_match else "; unapproved observation disagrees with the proposal"),
                            provider,
                            model,
                        )
                    )
                    if field_obs:
                        backed[field_name] = BackedFact(
                            field=field_name,
                            proposed=value,
                            backed_by=tuple(obs.source_key for obs in field_obs),
                            independent_sources=independent_digests(field_obs, digests),
                            semantic_only=True,
                        )
                    if required:
                        unresolved.add(field_name)
                elif required:
                    findings.append(
                        ReconciliationFinding(
                            "BLOCKER",
                            "source_evidence_unapproved" if field_obs else "source_evidence_unsupported",
                            (
                                f"required {field_name} for {provider}/{model} is backed only by unapproved source observations"
                                if field_obs
                                else f"required {field_name} for {provider}/{model} has no supporting snapshot observation"
                            ),
                            provider,
                            model,
                        )
                    )
                    unresolved.add(field_name)
                else:
                    findings.append(
                        ReconciliationFinding(
                            "REVIEW",
                            "source_evidence_unapproved" if field_obs else "source_evidence_unsupported",
                            (
                                f"{field_name} for {provider}/{model} is backed only by unapproved source observations"
                                if field_obs
                                else f"{field_name} for {provider}/{model} has no supporting snapshot observation (not required)"
                            ),
                            provider,
                            model,
                        )
                    )
        else:
            value = spec if not isinstance(spec, Mapping) else spec.get("value")
            if value is None:
                continue
            field_obs = observations_for(
                observations, field_name=field_name, model_names=model_names, provider=provider
            )
            official_obs = tuple(
                observation for observation in field_obs if observation.source_key in official_source_keys
            )
            canonical = "true" if value is True else ("false" if value is False else str(value))
            if official_obs:
                contradict = contradicting_values(official_obs, digests)
                if contradict is not None:
                    findings.append(
                        ReconciliationFinding(
                            "BLOCKER",
                            "source_observations_contradict",
                            f"distinct snapshots disagree on {field_name}: {', '.join(contradict[:4])}",
                            provider,
                            model,
                        )
                    )
                    unresolved.add(field_name)
                    continue
                matching = [observation for observation in official_obs if observation.value == canonical]
                if matching:
                    backed[field_name] = BackedFact(
                        field=field_name,
                        proposed=canonical,
                        backed_by=tuple(obs.source_key for obs in matching),
                        independent_sources=independent_digests(matching, digests),
                        semantic_only=False,
                    )
                else:
                    findings.append(
                        ReconciliationFinding(
                            "BLOCKER",
                            "source_evidence_value_mismatch",
                            f"proposed {field_name}={canonical} does not match parsed official snapshot values for {provider}/{model}",
                            provider,
                            model,
                        )
                    )
                    unresolved.add(field_name)
            elif field_obs:
                findings.append(
                    ReconciliationFinding(
                        "BLOCKER" if not semantic_provenance else "REVIEW",
                        "source_evidence_unapproved" if not semantic_provenance else "source_evidence_semantic_only",
                        (
                            f"proposed {field_name}={canonical} is backed only by unapproved source observations"
                            if not semantic_provenance
                            else f"{field_name} for {provider}/{model} has no verified deterministic observation; operator/semantic provenance is review-only"
                        ),
                        provider,
                        model,
                    )
                )
                if semantic_provenance:
                    backed[field_name] = BackedFact(
                        field=field_name,
                        proposed=canonical,
                        backed_by=tuple(obs.source_key for obs in field_obs),
                        independent_sources=independent_digests(field_obs, digests),
                        semantic_only=True,
                    )
                    unresolved.add(field_name)
            else:
                if semantic_provenance:
                    findings.append(
                        ReconciliationFinding(
                            "REVIEW",
                            "source_evidence_semantic_only",
                            f"{field_name} for {provider}/{model} has no supporting snapshot observation; operator/semantic provenance is review-only",
                            provider,
                            model,
                        )
                    )
                    unresolved.add(field_name)
                else:
                    findings.append(
                        ReconciliationFinding(
                            "BLOCKER",
                            "source_evidence_unsupported",
                            f"proposed {field_name}={canonical} for {provider}/{model} has no supporting snapshot observation",
                            provider,
                            model,
                        )
                    )
                    unresolved.add(field_name)
    return findings, backed, unresolved, missing_fx
