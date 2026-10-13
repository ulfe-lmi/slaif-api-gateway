"""Objective 183 (R1): bounded PARENT-GROUNDED verification of research
transcriptions against sealed official-source evidence bytes.

Trust model (parent-owned, re-derived at BOTH collection and verify time):

- the parent independently re-resolves the COMPLETE source row/section from
  the captured bytes (bounded identity-literal JSON parse for OpenRouter;
  strict line scan for OpenAI markdown);
- the researcher's transcription must cover EXACTLY the keys/cells the
  parent observes (an omitted fee/override/tier/sentinel/unknown key or a
  fabricated one rejects the whole model — absence in the model's JSON is
  not absence in the source);
- every quote must equal the exact raw source literal the parent re-derives;
- every normalized value is recomputed by the parent with the existing
  bounded Decimal/int grammar and unit conversion (the model's own
  normalization is never trusted);
- ParsedModel rows fed to the EXISTING eligibility/billing gates are
  constructed by the parent from the parent-resolved context only.

Sealed :class:`~slaif_gateway.schemas.catalog_refresh.ResearchGroundedFact`
records are the verbatim-quoted reading record; an offline verify re-grounds
them against the sealed evidence bytes, so trust is never declared.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Mapping

from slaif_gateway.schemas.catalog_refresh import RESEARCH_EXTRACTOR_ID
from slaif_gateway.services.catalog_refresh import source_evidence as se

__all__ = [
    "GroundingError",
    "OpenAiTierTranscription",
    "RouterTranscription",
    "ground_doc_page",
    "ground_openai_pricing_row",
    "ground_router_row",
    "ground_router_snapshot",
    "re_ground_fact",
    "resolve_router_row",
]

MAX_RESEARCH_MODELS = 64  # models per one task output
MAX_RESEARCH_PRICING_KEYS = 32  # pricing keys per row
MAX_RESEARCH_CELL = 512  # quote length bound
MAX_RESEARCH_LOCATOR = 256
_RESEARCH_INT_GRAMMAR = re.compile(r"^[0-9]{1,3}(?:,[0-9]{3})*$")
# Plain unformatted integers (JSON numerics) or US-grouped comma form;
# K/M suffixes apply to plain integers only.
_RESEARCH_LIMIT_GRAMMAR = re.compile(
    r"^([0-9]{1,3}(?:,[0-9]{3})*|[0-9]{1,12})([KkMm])?$"
)
# Documented research limit-line variants for OpenAI model doc pages
# (deterministic layouts are handled by the registered parser first).
_DOC_CONTEXT_LINE = re.compile(
    r"^[Cc]ontext\s+window\s*(?:\(\s*tokens\s*\))?\s*:\s*((?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]{1,12})(?:[KkMm])?)\s*$"
)
_DOC_MAXOUT_LINE = re.compile(
    r"^[Mm]ax(?:imum)?\s+output\s*(?:\(\s*tokens\s*\))?\s*:\s*((?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]{1,12})(?:[KkMm])?)\s*$"
)
_MAX_RESEARCH_INT = 10**12

ROUTER_DIM_KEYS = {
    "input": "prompt",
    "cached_input": "input_cache_read",
    "output": "completion",
    "reasoning": "internal_reasoning",
}
ROUTER_EXTRA_KEYS = {
    "cache_write": "input_cache_write",
    "cache_write_1h": "input_cache_write_1h",
    "web_search": "web_search",
}


class GroundingError(Exception):
    """Fail-closed grounding refusal (safe code only, no input echo)."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class RawCell:
    """One parent-resolved raw scalar (exact source spelling)."""

    literal: str  # string: unquoted text; number: exact literal; bool/null: literal
    kind: str  # "string" | "number" | "bool" | "null"


@dataclass
class RouterRowContext:
    """Parent-resolved complete OpenRouter row context (all billing inputs)."""

    index: int
    model: str
    pricing: dict[str, RawCell] = field(default_factory=dict)
    context_length: RawCell | None = None
    max_output_tokens: RawCell | None = None
    text_modality: bool | None = None
    deprecated: bool | None = None
    overrides: int | None = None  # parent-recomputed block count
    overrides_malformed: bool = False


@dataclass(frozen=True)
class GroundedCell:
    """One verified transcription cell (sealed as a ResearchGroundedFact)."""

    field: str
    locator: str
    quote: str
    value: str
    unit: str
    currency: str | None


# --- parent-resolved context -------------------------------------------------


def _raw_cell(value: Any) -> RawCell | None:
    """Map one identity-parsed JSON scalar to its exact source spelling."""
    if isinstance(value, str):
        return RawCell(literal=value, kind="string")
    if isinstance(value, se._RawNumber):
        return RawCell(literal=value.literal, kind="number")
    if isinstance(value, bool):
        return RawCell(literal="true" if value else "false", kind="bool")
    if value is None:
        return RawCell(literal="null", kind="null")
    return None  # arrays/objects are not scalar cells (parent-recomputed)


def _research_limit_value(literal: str) -> int:
    match = _RESEARCH_LIMIT_GRAMMAR.fullmatch(literal.strip())
    if match is None:
        raise GroundingError("value_grammar")
    digits = match.group(1)
    suffix = match.group(2)
    if "," in digits:
        if suffix is not None or not _RESEARCH_INT_GRAMMAR.fullmatch(digits):
            raise GroundingError("value_grammar")
    value = int(digits.replace(",", ""))
    if suffix is not None:
        value *= 1000 if suffix.upper() == "K" else 10**6
    if value < 1 or value > _MAX_RESEARCH_INT:
        raise GroundingError("value_bound")
    return value


def _check_locator(text: str, expected: str | None) -> None:
    if not (1 <= len(text) <= MAX_RESEARCH_LOCATOR):
        raise GroundingError("locator_length")
    if expected is not None and text != expected:
        raise GroundingError("locator_mismatch")


def resolve_router_row(evidence: bytes, model: str) -> RouterRowContext:
    """Parent-resolve ONE complete OpenRouter row from the snapshot bytes.

    The row is re-located by the parent from the exact ``id`` (the claimed
    index is checked, never trusted). Every pricing key, the limit fields,
    modalities, deprecation and the overrides block are resolved so the
    complete billing context is available regardless of what any model
    transcribed. Malformed structure is fail-closed (GroundingError).
    """
    payload = se.loads_raw_snapshot_json(evidence, kind="openrouter_models_api")
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise GroundingError("source_unstructured")
    rows = payload["data"]
    if len(rows) > se.OPENAI_MAX_MODELS_PER_SNAPSHOT * 8:
        raise GroundingError("source_unbounded")
    index = None
    row = None
    for i, candidate in enumerate(rows):
        if isinstance(candidate, dict) and candidate.get("id") == model:
            if index is not None:
                raise GroundingError("model_ambiguous")
            index = i
            row = candidate
    if row is None:
        raise GroundingError("model_not_found")
    context = RouterRowContext(index=index, model=model)
    pricing = row.get("pricing")
    if pricing is not None:
        if not isinstance(pricing, dict) or len(pricing) > MAX_RESEARCH_PRICING_KEYS:
            raise GroundingError("pricing_unbounded")
        for key, value in pricing.items():
            if not isinstance(key, str) or not (1 <= len(key) <= 64):
                raise GroundingError("pricing_key_invalid")
            cell = _raw_cell(value)
            if cell is None:
                raise GroundingError("pricing_cell_unrepresentable")
            context.pricing[key] = cell
    if "context_length" in row and row["context_length"] is not None:
        cell = _raw_cell(row["context_length"])
        if cell is None:
            raise GroundingError("limit_unrepresentable")
        context.context_length = cell
    top_provider = row.get("top_provider")
    if isinstance(top_provider, dict) and top_provider.get("max_completion_tokens") is not None:
        cell = _raw_cell(top_provider["max_completion_tokens"])
        if cell is None:
            raise GroundingError("limit_unrepresentable")
        context.max_output_tokens = cell
    architecture = row.get("architecture")
    if isinstance(architecture, dict):
        inputs = architecture.get("input_modalities")
        outputs = architecture.get("output_modalities")
        if isinstance(inputs, list) and isinstance(outputs, list) and all(
            isinstance(item, str) for item in (*inputs, *outputs)
        ):
            context.text_modality = "text" in inputs and "text" in outputs
    deprecation = row.get("deprecation")
    if isinstance(deprecation, dict) and isinstance(deprecation.get("is_deprecated"), bool):
        context.deprecated = deprecation["is_deprecated"]
    if "overrides" in context.pricing:
        cell = context.pricing["overrides"]
        count = _router_overrides_count(cell)
        if count is None:
            context.overrides_malformed = True
        else:
            context.overrides = count
    return context


def _router_overrides_count(cell: RawCell) -> int | None:
    """Parent-recomputed overrides block count (deterministic bounds)."""
    if cell.kind == "string":
        text = cell.literal
        if not (
            len(text) <= 4096
            and text.startswith("[")
            and text.endswith("]")
        ):
            return None
        return len(se.ROUTER_OVERRIDE_BLOCK_RE.findall(text))
    return None


def _normalized_router_pricing(key: str, cell: RawCell) -> tuple[str, str, str] | None:
    """Parent-normalize one pricing cell -> (value, unit, currency) or the
    sentinel marker. ValueError from the existing grammar -> ungroundable."""
    text = cell.literal.strip()
    if key in ROUTER_DIM_KEYS.values():
        if text == "-1":
            return ("non_representable", "per_1m_tokens", "USD")
        try:
            value = se.process_router_price_cell(text)
        except ValueError:
            raise GroundingError(f"cell_ungroundable:{key}") from None
        return (_decimal_str(value), "per_1m_tokens", "USD")
    if key in ("input_cache_write", "input_cache_write_1h"):
        if text == "-1":
            return ("non_representable", "per_1m_tokens", "USD")
        try:
            value = se.process_router_price_cell(text)
        except ValueError:
            raise GroundingError(f"cell_ungroundable:{key}") from None
        return (_decimal_str(value), "per_1m_tokens", "USD")
    if key == "web_search":
        if text == "-1":
            return ("non_representable", "per_call", "USD")
        try:
            value = se.process_router_price_cell(text)
            if not (value.is_finite() and value < 10**9):
                raise GroundingError(f"cell_ungroundable:{key}")
        except ValueError:
            raise GroundingError(f"cell_ungroundable:{key}") from None
        return (_decimal_str(value), "per_call", "USD")
    if key == "request":
        if text == "-1":
            return ("non_representable", "per_request", "USD")
        try:
            value = se.process_router_price_cell(text)
        except ValueError:
            raise GroundingError(f"cell_ungroundable:{key}") from None
        return (_decimal_str(value), "per_request", "USD")
    # unknown key: recorded, never normalized (the billing gate sees it raw)
    return ("unrecognized_key", "raw", None)


def _decimal_str(value: Decimal) -> str:
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _router_row_parsed(context: RouterRowContext) -> "se.ParsedModel":
    """Parent-built ParsedModel from the parent-resolved row context (the
    transcription's quotes are never the value source)."""
    prices: dict[str, Decimal] = {}
    non_representable: dict[str, str] = {}
    extra_pricing: dict[str, str] = {}
    request_price: Decimal | None = None
    for key, cell in sorted(context.pricing.items()):
        normalized = _normalized_router_pricing(key, cell)
        if key in ROUTER_DIM_KEYS.values():
            dim = next(d for d, k in ROUTER_DIM_KEYS.items() if k == key)
            if normalized[0] == "non_representable":
                non_representable[dim] = "negative_router_sentinel"
            else:
                prices[dim] = Decimal(normalized[0])
        elif key in ROUTER_EXTRA_KEYS.values():
            dim = next(d for d, k in ROUTER_EXTRA_KEYS.items() if k == key)
            if normalized[0] != "non_representable":
                extra_pricing[dim] = normalized[0]
        elif key == "request":
            if normalized[0] != "non_representable":
                request_price = Decimal(normalized[0])
            else:
                non_representable["request"] = "negative_router_sentinel"
        else:
            continue  # unknown keys flow through unknown_pricing_keys
    context_length: int | None = None
    if context.context_length is not None:
        context_length = _research_limit_value(context.context_length.literal)
    max_output: int | None = None
    if context.max_output_tokens is not None:
        max_output = _research_limit_value(context.max_output_tokens.literal)
    prefix = f"data[{context.index}]"
    locators: dict[str, str] = {}
    if context_length is not None:
        locators["model:context_length"] = f"{prefix}.context_length"
    if max_output is not None:
        locators["model:max_output_tokens"] = f"{prefix}.top_provider.max_completion_tokens"
    if context.text_modality is not None:
        locators["model:capability:text"] = f"{prefix}.architecture"
    if context.deprecated is not None:
        locators["model:deprecated"] = f"{prefix}.deprecation.is_deprecated"
    for key in sorted(context.pricing):
        locators[f"pricing:{key}"] = f"{prefix}.pricing.{key}"
    return se.ParsedModel(
        provider="openrouter",
        model=context.model,
        context_length=context_length,
        max_output_tokens=max_output,
        prices=prices,
        price_currency="USD" if prices else None,
        text_modality=context.text_modality,
        deprecated=context.deprecated,
        locators=locators,
        parser=RESEARCH_EXTRACTOR_ID,
        extra_pricing=extra_pricing,
        non_representable_prices=non_representable,
        pricing_overrides=context.overrides,
        request_price=request_price,
        unknown_pricing_keys=tuple(
            sorted(set(context.pricing) - set(se.ROUTER_RECOGNIZED_PRICING_KEYS))
        ),
    )

# --- OpenAI pricing tables (lenient parent scan) ------------------------------


@dataclass(frozen=True)
class OpenAiCell:
    text: str  # exact raw cell token
    line: int
    value: Decimal | None  # parent-parsed; None = explicit missing marker
    unparseable: bool = False


@dataclass
class OpenAiPricingContext:
    """Parent-resolved OpenAI v2 pricing tables: (tier, model) -> cells."""

    rows: dict[tuple[str, str], dict[str, OpenAiCell]]
    columns: dict[str, tuple[str, ...]]  # tier -> ordered lowercase headers
    unusable_tiers: frozenset[str]
    unusable_rows: int = 0
    # Models with two rows claiming the same (tier, model) scope in one
    # captured table: an ambiguous context, rejected fail-closed at
    # grounding (never silently pick the first row).
    conflicting_models: frozenset[str] = frozenset()


def resolve_openai_pricing_snapshot(evidence: bytes) -> OpenAiPricingContext:
    """Lenient-but-strict parent scan of the v2 pricing document.

    Unlike the deterministic parser (fail-closed on the first unrecognized
    cell), the scan keeps going: one unparseable cell marks that cell
    ungroundable, one malformed model cell skips that row only, and an
    unrecognized header makes that tier table unusable — no captured source
    ID is silently discarded.
    """
    text = evidence.decode("utf-8") if len(evidence) <= se.OPENAI_MAX_SNAPSHOT_BYTES else None
    if text is None:
        raise GroundingError("source_too_large")
    rows: dict[tuple[str, str], dict[str, OpenAiCell]] = {}
    columns: dict[str, tuple[str, ...]] = {}
    unusable_tiers: set[str] = set()
    unusable_rows = 0
    conflicting_models: set[str] = set()
    total_data_rows = 0
    current_tier: str | None = None
    current_columns: list[tuple[str, str]] | None = None
    in_tier_table = False
    for line_no, line in enumerate(text.splitlines()):
        stripped = line.strip()
        heading = se.OPENAI_V2_TIER_HEADING_RE.match(stripped)
        if heading is not None:
            in_tier_table = True
            current_tier = heading.group(1).lower()
            current_columns = None
            continue
        if in_tier_table and not stripped.startswith("|"):
            if stripped.startswith("#") or (stripped and not stripped.startswith(">")):
                in_tier_table = False
                current_columns = None
            continue
        if not in_tier_table or current_tier is None:
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if se.OPENAI_SEPARATOR_ROW_CHECK(cells):
            continue
        if cells and cells[0].lower() == "model":
            parsed_cols: list[tuple[str, str]] = []
            ok = len(cells) >= 2
            for column in cells[1:]:
                mapped = se.OPENAI_V2_PRICE_HEADER_MAP.get(column.lower())
                if mapped is None:
                    ok = False
                    break
                parsed_cols.append(mapped)
            if not ok:
                unusable_tiers.add(current_tier)
                current_columns = None
            else:
                columns[current_tier] = tuple(column.lower() for column in cells[1:])
                current_columns = parsed_cols
            continue
        if current_columns is None or len(cells) != len(current_columns) + 1:
            unusable_rows += 1
            continue
        total_data_rows += 1
        if total_data_rows > se.OPENAI_MAX_TABLE_ROWS:
            raise GroundingError("source_unbounded")
        try:
            model_id, _note = se.parse_openai_v2_model_cell_id(cells[0])
        except se.SnapshotFormatError:
            unusable_rows += 1
            continue
        row_cells: dict[str, OpenAiCell] = {}
        for header, cell_text in zip(columns[current_tier], cells[1:]):
            value: Decimal | None
            unparseable = False
            if cell_text in ("-", ""):
                value = None
            else:
                try:
                    value = se.parse_openai_v2_price_cell_value(cell_text)
                except se.SnapshotFormatError:
                    # Opaque cells - including parenthetical qualifiers such
                    # as "$0.50 (per request)", "(batch)" or "(starts at)" -
                    # are never interpreted: a non-numeric qualifier does not
                    # prove a harmless annotation, so the cell stays
                    # ungroundable and the model's context is rejected rather
                    # than silently stripped to a per-million amount.
                    value = None
                    unparseable = True
            row_cells[header] = OpenAiCell(text=cell_text, line=line_no, value=value, unparseable=unparseable)
        key = (current_tier, model_id)
        if key in rows:
            # Two rows in one captured table claim the same (tier, model)
            # scope: ambiguous context. Count it AND reject the affected
            # model fail-closed - never silently retain the first row.
            unusable_rows += 1
            conflicting_models.add(model_id)
        else:
            rows[key] = row_cells
    return OpenAiPricingContext(
        rows=rows,
        columns=columns,
        unusable_tiers=frozenset(unusable_tiers),
        unusable_rows=unusable_rows,
        conflicting_models=frozenset(conflicting_models),
    )


def openai_pricing_row_parsed(
    tier: str, model_id: str, cells: dict[str, OpenAiCell], context: OpenAiPricingContext
) -> "se.ParsedModel":
    """Parent-built ParsedModel row from the parent-resolved cells (exact
    mirror of the deterministic v2 row mapping)."""
    prices: dict[str, Decimal] = {}
    prices_long: dict[str, Decimal] = {}
    extra: dict[str, str] = {}
    locators: dict[str, str] = {}
    for header, (band, dim) in se.OPENAI_V2_PRICE_HEADER_MAP.items():
        if header not in cells:
            continue
        cell = cells[header]
        if cell.unparseable:
            raise GroundingError(f"cell_ungroundable:{header}")
        if cell.value is None:
            continue
        locator = f"line[{cell.line}]"
        if band == "short":
            if dim == "cache_write":
                extra["cache_write"] = _decimal_str(cell.value)
                locators["pricing:cache_write"] = locator
            else:
                prices[dim] = cell.value
                locators[f"pricing:{dim}"] = locator
        else:
            if dim == "cache_write":
                extra["cache_write_long"] = _decimal_str(cell.value)
                locators["pricing:cache_write_long"] = locator
            else:
                prices_long[dim] = cell.value
                locators[f"pricing_long:{dim}"] = locator
    return se.ParsedModel(
        provider="openai",
        model=model_id,
        prices=prices,
        prices_long=prices_long,
        extra_pricing=extra,
        price_currency="USD" if (prices or prices_long) else None,
        billing_tier=tier,
        context_band="short",
        locators=locators,
        parser=RESEARCH_EXTRACTOR_ID,
    )


def openai_pricing_field_name(tier: str, dim: str, band: str, extra: bool = False) -> str:
    model = se.ParsedModel(provider="openai", model="", billing_tier=tier, context_band="short")
    return se._pricing_field_name(model, dim, band=band, extra=extra)


# --- OpenAI model doc pages (parsed-but-incomplete limits) --------------------


@dataclass
class DocPageContext:
    """Parent-resolved model doc page: identity + research limit candidates."""

    model_id: str
    lines: list[str]
    context_candidates: list[tuple[int, int]]  # (line, value)
    maxout_candidates: list[tuple[int, int]]


def resolve_doc_page(evidence: bytes) -> DocPageContext:
    text = se._decode_bounded(evidence, kind="research:openai_model_doc", max_bytes=se.OPENAI_MAX_SNAPSHOT_BYTES)
    lines = text.splitlines()
    model_id = None
    for line in lines:
        match = se.OPENAI_DOC_MODEL_ID_RE.match(line.strip())
        if match is not None:
            candidate = match.group(1).strip()
            if not se._OPENAI_V2_MODEL_ID.fullmatch(candidate):
                raise GroundingError("model_id_invalid")
            model_id = candidate
            break
    if model_id is None:
        raise GroundingError("model_id_missing")
    context_candidates: list[tuple[int, int]] = []
    maxout_candidates: list[tuple[int, int]] = []
    for line_no, line in enumerate(lines):
        stripped = line.strip()
        match = _DOC_CONTEXT_LINE.match(stripped)
        if match is not None:
            try:
                context_candidates.append((line_no, _research_limit_value(match.group(1))))
            except GroundingError:
                continue
        match = _DOC_MAXOUT_LINE.match(stripped)
        if match is not None:
            try:
                maxout_candidates.append((line_no, _research_limit_value(match.group(1))))
            except GroundingError:
                continue
    return DocPageContext(
        model_id=model_id,
        lines=lines,
        context_candidates=context_candidates,
        maxout_candidates=maxout_candidates,
    )


def _unique_limit(candidates: list[tuple[int, int]]) -> tuple[int, int] | None:
    if not candidates:
        return None
    values = {value for _line, value in candidates}
    if len(values) != 1:
        raise GroundingError("value_ambiguous")
    return candidates[0]


# --- transcription verification (collection + verify time) --------------------


@dataclass(frozen=True)
class RouterTranscription:
    """Schema-conformant per-model researcher transcription (OpenRouter)."""

    model: str
    claimed_index: int
    pricing_cells: dict[str, tuple[str, str]]  # key -> (locator, quote)
    context_length: tuple[str, str] | None  # (locator, quote)
    max_output_tokens: tuple[str, str] | None


def ground_router_row(
    evidence: bytes, trans: RouterTranscription
) -> tuple["se.ParsedModel", list[GroundedCell]]:
    """Verify ONE transcription against the parent-resolved row and return
    the parent-built row + verified cells. Any refusal is fail-closed.

    The orchestrator calls this per model so one bad transcription rejects
    only its own model (never the task's other models)."""
    cells: list[GroundedCell] = []
    context = resolve_router_row(evidence, trans.model)
    if context.index != trans.claimed_index:
        raise GroundingError("locator_mismatch")
    # exact key-set equality: the transcription covers the FULL row
    if set(trans.pricing_cells) != set(context.pricing):
        missing = sorted(set(context.pricing) - set(trans.pricing_cells))
        extra = sorted(set(trans.pricing_cells) - set(context.pricing))
        if missing:
            raise GroundingError(f"context_omitted:{missing[0]}")
        raise GroundingError(f"context_fabricated:{extra[0]}")
    prefix = f"data[{context.index}]"
    for key, (locator, quote) in sorted(trans.pricing_cells.items()):
        expected = f"{prefix}.pricing.{key}"
        _check_locator(locator, expected)
        cell = context.pricing[key]
        if quote != cell.literal:
            raise GroundingError(f"quote_mismatch:{key}")
        _check_cell(quote)
        normalized = _normalized_router_pricing(key, cell)
        field_name = f"pricing:{key}"
        cells.append(
            GroundedCell(
                field=field_name,
                locator=locator,
                quote=quote,
                value=normalized[0],
                unit=normalized[1],
                currency=normalized[2],
            )
        )
    for field_name, trans_cell, context_cell, path in (
        ("model:context_length", trans.context_length, context.context_length, f"{prefix}.context_length"),
        ("model:max_output_tokens", trans.max_output_tokens, context.max_output_tokens, f"{prefix}.top_provider.max_completion_tokens"),
    ):
        if context_cell is None:
            if trans_cell is not None:
                raise GroundingError(f"context_fabricated:{field_name}")
            continue
        if trans_cell is None:
            raise GroundingError(f"context_omitted:{field_name}")
        locator, quote = trans_cell
        _check_locator(locator, path)
        if quote != context_cell.literal:
            raise GroundingError(f"quote_mismatch:{field_name}")
        _check_cell(quote)
        value = _research_limit_value(quote)
        cells.append(
            GroundedCell(field=field_name, locator=locator, quote=quote, value=str(value), unit="none", currency=None)
        )
    row = _router_row_parsed(context)
    if context.overrides_malformed:
        raise GroundingError("context_malformed_overrides")
    return row, cells


def ground_router_snapshot(
    evidence: bytes, transcriptions: list[RouterTranscription]
) -> tuple[list["se.ParsedModel"], list[GroundedCell]]:
    """Batch convenience: verify EVERY transcription (all-or-nothing)."""
    if len(transcriptions) > MAX_RESEARCH_MODELS:
        raise GroundingError("models_unbounded")
    seen: set[str] = set()
    rows: list[se.ParsedModel] = []
    cells: list[GroundedCell] = []
    for trans in transcriptions:
        if trans.model in seen:
            raise GroundingError("model_duplicate")
        seen.add(trans.model)
        row, row_cells = ground_router_row(evidence, trans)
        rows.append(row)
        cells.extend(row_cells)
    return rows, cells


def _check_cell(text: str) -> None:
    if not (1 <= len(text) <= MAX_RESEARCH_CELL):
        raise GroundingError("cell_length")


@dataclass(frozen=True)
class OpenAiTierTranscription:
    """One claimed tier row: the row's line and EVERY cell in that row
    (a flat cell map cannot cover multi-tier models, whose rows sit on
    different lines with different values)."""

    line: int
    cells: dict[str, tuple[str, str]]  # header -> (locator, quote)


def ground_openai_pricing_row(
    evidence: bytes, model: str, tier_trans: Mapping[str, OpenAiTierTranscription]
) -> tuple[list["se.ParsedModel"], list[GroundedCell]]:
    """Verify a model's complete transcription (ALL its rows in ALL usable
    tier tables, ALL columns, each at its own actual row) against the
    parent scan."""
    context = resolve_openai_pricing_snapshot(evidence)
    if model in context.conflicting_models:
        raise GroundingError("context_ambiguous")
    model_keys = sorted(key for key in context.rows if key[1] == model)
    if not model_keys:
        raise GroundingError("model_not_found")
    expected_tiers = {tier for tier, _model in model_keys}
    if set(tier_trans) != expected_tiers:
        missing = sorted(expected_tiers - set(tier_trans))
        if missing:
            raise GroundingError(f"context_omitted:{missing[0]}")
        raise GroundingError("context_fabricated")
    rows: list[se.ParsedModel] = []
    cells: list[GroundedCell] = []
    for tier in sorted(expected_tiers):
        if tier in context.unusable_tiers:
            raise GroundingError("tier_unusable")
        row_cells = context.rows[(tier, model)]
        trans = tier_trans[tier]
        if trans.line != next(iter(row_cells.values())).line:
            raise GroundingError("locator_mismatch")
        if set(trans.cells) != set(row_cells):
            missing = sorted(set(row_cells) - set(trans.cells))
            if missing:
                raise GroundingError(f"context_omitted:{missing[0]}")
            raise GroundingError("context_fabricated")
        for header, (locator, quote) in sorted(trans.cells.items()):
            expected = f"line[{row_cells[header].line}]"
            _check_locator(locator, expected)
            cell = row_cells[header]
            if quote != cell.text:
                raise GroundingError(f"quote_mismatch:{header}")
            _check_cell(quote)
            band_dim = se.OPENAI_V2_PRICE_HEADER_MAP[header]
            band, dim = band_dim
            extra = dim == "cache_write"
            if cell.unparseable:
                raise GroundingError(f"cell_ungroundable:{header}")
            value = "missing" if cell.value is None else _decimal_str(cell.value)
            field_name = openai_pricing_field_name(tier, dim, band, extra=extra)
            cells.append(
                GroundedCell(
                    field=field_name,
                    locator=locator,
                    quote=quote,
                    value=value,
                    unit="per_1m_tokens" if not extra or dim == "cache_write" else "raw",
                    currency="USD",
                )
            )
        rows.append(openai_pricing_row_parsed(tier, model, row_cells, context))
    return rows, cells


def ground_doc_page(
    evidence: bytes,
    model: str,
    context_trans: tuple[str, str] | None,
    maxout_trans: tuple[str, str] | None,
) -> tuple[dict[str, int], list[GroundedCell]]:
    """Verify docs_page limit supplements against the parent page scan.

    The page's model ID must match (deterministic identity binding); each
    claimed field must match the parent-resolved unique value on the
    claimed line; a value the parent resolves must be claimed (no omission);
    fields the parent cannot resolve must not be claimed.
    """
    context = resolve_doc_page(evidence)
    if context.model_id != model:
        raise GroundingError("model_mismatch")
    resolved: dict[str, int] = {}
    cells: list[GroundedCell] = []
    for field_name, trans, candidates in (
        ("model:context_length", context_trans, context.context_candidates),
        ("model:max_output_tokens", maxout_trans, context.maxout_candidates),
    ):
        unique = _unique_limit(candidates)
        if unique is None:
            if trans is not None:
                raise GroundingError(f"context_fabricated:{field_name}")
            continue
        if trans is None:
            raise GroundingError(f"context_omitted:{field_name}")
        line_no, value = unique
        locator, quote = trans
        _check_locator(locator, f"line[{line_no}]")
        if quote != context.lines[line_no].strip():
            raise GroundingError(f"quote_mismatch:{field_name}")
        _check_cell(quote)
        resolved[field_name] = value
        cells.append(
            GroundedCell(field=field_name, locator=locator, quote=quote, value=str(value), unit="none", currency=None)
        )
    return resolved, cells

# --- verify-time re-grounding (a sealed fact is re-derived, never declared) --


def re_ground_fact(
    *,
    evidence: bytes,
    source_kind: str,
    model: str,
    field: str,
    locator: str,
    quote: str,
    value: str,
    unit: str,
    currency: str | None,
) -> None:
    """Re-derive ONE sealed :class:`ResearchGroundedFact` from the sealed
    evidence bytes (verify time).

    The same parent-owned resolution and normalization the collection-time
    grounding used must reproduce the fact EXACTLY (locator, verbatim quote,
    normalized value, unit, currency). Any mismatch - a tampered fact, a
    re-worded quote, a value from another row/model/tier/unit - raises a
    fail-closed :class:`GroundingError` with a safe code (no input echo).
    """
    if source_kind == "openrouter_models_api":
        context = resolve_router_row(evidence, model)
        prefix = f"data[{context.index}]"
        if field == "model:context_length":
            cell = context.context_length
            path = f"{prefix}.context_length"
        elif field == "model:max_output_tokens":
            cell = context.max_output_tokens
            path = f"{prefix}.top_provider.max_completion_tokens"
        elif field.startswith("pricing:"):
            key = field.split(":", 1)[1]
            cell = context.pricing.get(key)
            path = f"{prefix}.pricing.{key}"
        else:
            raise GroundingError("fact_ungroundable")
        if cell is None:
            raise GroundingError("fact_ungroundable")
        if field.startswith("pricing:"):
            normalized = _normalized_router_pricing(key, cell)
            if normalized is None:
                raise GroundingError("fact_ungroundable")
            expected_value, expected_unit, expected_currency = normalized
        else:
            expected_value = str(_research_limit_value(cell.literal))
            expected_unit, expected_currency = "none", None
        if locator != path:
            raise GroundingError("fact_locator_mismatch")
        if quote != cell.literal:
            raise GroundingError("fact_quote_mismatch")
        if (value, unit, currency) != (expected_value, expected_unit, expected_currency):
            raise GroundingError("fact_value_mismatch")
        return
    if source_kind == "openai_pricing_docs":
        context = resolve_openai_pricing_snapshot(evidence)
        if model in context.conflicting_models:
            raise GroundingError("fact_ungroundable")
        found = None
        for (tier, row_model), row_cells in sorted(context.rows.items()):
            if row_model != model or tier in context.unusable_tiers:
                continue
            for header, cell in sorted(row_cells.items()):
                band, dim = se.OPENAI_V2_PRICE_HEADER_MAP[header]
                if openai_pricing_field_name(tier, dim, band, extra=dim == "cache_write") != field:
                    continue
                found = cell
                break
            if found is not None:
                break
        if found is None:
            raise GroundingError("fact_ungroundable")
        if found.unparseable or found.value is None:
            raise GroundingError("fact_ungroundable")
        if locator != f"line[{found.line}]":
            raise GroundingError("fact_locator_mismatch")
        if quote != found.text:
            raise GroundingError("fact_quote_mismatch")
        if (value, unit, currency) != (_decimal_str(found.value), "per_1m_tokens", "USD"):
            raise GroundingError("fact_value_mismatch")
        return
    if source_kind == "docs_page":
        context = resolve_doc_page(evidence)
        if context.model_id != model:
            raise GroundingError("fact_model_mismatch")
        if field == "model:context_length":
            candidates = context.context_candidates
        elif field == "model:max_output_tokens":
            candidates = context.maxout_candidates
        else:
            raise GroundingError("fact_ungroundable")
        unique = _unique_limit(candidates)
        if unique is None:
            raise GroundingError("fact_ungroundable")
        line_no, unique_value = unique
        if locator != f"line[{line_no}]":
            raise GroundingError("fact_locator_mismatch")
        if quote != context.lines[line_no].strip():
            raise GroundingError("fact_quote_mismatch")
        if (value, unit, currency) != (str(unique_value), "none", None):
            raise GroundingError("fact_value_mismatch")
        return
    raise GroundingError("fact_ungroundable")
