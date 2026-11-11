"""Deterministic provider catalog proposal tooling.

This module fetches official provider docs and metadata, compares multiple
source methods, and generates proposal artifacts that plug into SLAIF's
existing route/pricing import preview workflows.
"""

from __future__ import annotations

import asyncio
import csv
import fnmatch
import hashlib
import json
import os
import re
import uuid
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from contextvars import ContextVar
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation, localcontext
from html.parser import HTMLParser
from io import StringIO
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

import httpx

from slaif_gateway.services.pricing_import import parse_pricing_import_tsv, validate_pricing_import_rows
from slaif_gateway.schemas.catalog_refresh import parse_decimal_text
from slaif_gateway.services.route_import import (
    RouteImportProviderRef,
    parse_route_import_tsv,
    validate_route_import_rows,
)
from slaif_gateway.services.chat_completion_route_capabilities import (
    CHAT_CAPABILITY_AUDIO,
    CHAT_CAPABILITY_AUDIO_INPUTS,
    CHAT_CAPABILITY_AUDIO_OUTPUTS,
    CHAT_CAPABILITY_CACHED_INPUT_USAGE,
    CHAT_CAPABILITY_CUSTOM_TOOLS,
    CHAT_CAPABILITY_EXTERNAL_MCP_CONNECTORS,
    CHAT_CAPABILITY_FILE_INPUTS,
    CHAT_CAPABILITY_FUNCTION_TOOLS,
    CHAT_CAPABILITY_HOSTED_CODE_INTERPRETER,
    CHAT_CAPABILITY_HOSTED_COMPUTER_USE,
    CHAT_CAPABILITY_HOSTED_FILE_SEARCH,
    CHAT_CAPABILITY_HOSTED_IMAGE_GENERATION,
    CHAT_CAPABILITY_HOSTED_TOOL_SEARCH,
    CHAT_CAPABILITY_HOSTED_WEB_SEARCH,
    CHAT_CAPABILITY_IMAGE_INPUTS,
    CHAT_CAPABILITY_JSON_MODE,
    CHAT_CAPABILITY_LEGACY_FUNCTIONS,
    CHAT_CAPABILITY_LOGPROBS,
    CHAT_CAPABILITY_MULTIMODAL,
    CHAT_CAPABILITY_MULTIPLE_CHOICES,
    CHAT_CAPABILITY_REASONING_USAGE,
    CHAT_CAPABILITY_SERVICE_TIER_NON_DEFAULT,
    CHAT_CAPABILITY_STREAMING,
    CHAT_CAPABILITY_STRUCTURED_OUTPUTS,
    CHAT_CAPABILITY_TEXT,
    CHAT_COMPLETIONS_CAPABILITIES_KEY,
)
from slaif_gateway.services.hosted_tool_policy import is_search_specific_chat_completion_model
from slaif_gateway.services.key_policy_validation import (
    IMPLEMENTED_CLIENT_ENDPOINTS,
    RESPONSES_ENDPOINT,
)
from slaif_gateway.services.model_route_service import CHAT_COMPLETIONS_ENDPOINT, normalize_endpoint
from slaif_gateway.services.openai_assisted_catalog import (
    OPENAI_ADMIN_DISCOVERY_API_KEY_ENV_VAR,
    OFFICIAL_OPENAI_SOURCE_DOMAINS,
    generate_openai_pricing_proposal_text,
    generate_openai_route_proposal_text,
)
from slaif_gateway.utils.redaction import redact_mapping, redact_text

ProviderName = Literal["openai", "openrouter"]
ProposalSourceMethod = Literal["docs", "api", "assisted"]
EndpointScope = Literal["chat_completions", "responses"]
Confidence = Literal["high", "medium", "low"]

OPENROUTER_PROVIDER = "openrouter"
OPENAI_PROVIDER = "openai"
OPENROUTER_MODELS_API_URL = "https://openrouter.ai/api/v1/models"
OPENROUTER_MODELS_DOCS_URL = "https://openrouter.ai/docs/guides/overview/models"
OPENROUTER_MODELS_DOCS_MARKDOWN_URL = "https://openrouter.ai/docs/guides/overview/models.md"
OPENROUTER_OPENAPI_REFERENCE_URL = "https://openrouter.ai/docs/api/reference/overview"
OPENAI_MODELS_API_URL = "https://api.openai.com/v1/models"
OPENAI_MODELS_DOCS_URL = "https://developers.openai.com/api/docs/models"
OPENAI_PRICING_DOCS_URL = "https://developers.openai.com/api/docs/pricing"

OFFICIAL_OPENROUTER_SOURCE_DOMAINS = ("openrouter.ai",)
OFFICIAL_SOURCE_DOMAINS = {
    OPENAI_PROVIDER: OFFICIAL_OPENAI_SOURCE_DOMAINS,
    OPENROUTER_PROVIDER: OFFICIAL_OPENROUTER_SOURCE_DOMAINS,
}

DEFAULT_ENDPOINT_SCOPES: tuple[EndpointScope, ...] = ("chat_completions",)
SUPPORTED_ENDPOINT_SCOPES = frozenset({"chat_completions", "responses"})
SUPPORTED_SOURCE_METHODS = frozenset({"docs", "api", "assisted"})
SUPPORTED_OUTPUT_FILES = (
    "source-manifest.json",
    "provider-catalog-normalized.json",
    "routes-proposal.tsv",
    "pricing-proposal.tsv",
    "provider-catalog-report.md",
    "warnings.json",
)
PACKAGE_INDEX_FILENAME = "packages/package-index.json"
PACKAGE_INDEX_MARKDOWN_FILENAME = "packages/package-index.md"
PROPOSAL_TSV_VALIDATION_ERROR_CODE = "proposal_tsv_validation_failed"
PROPOSAL_OUTPUT_SIZE_EXCEEDED_CODE = "proposal_output_size_exceeded"
SUPPORTED_CHAT_PARAMETERS = {
    "tools",
    "tool_choice",
    "max_tokens",
    "max_completion_tokens",
    "temperature",
    "top_p",
    "structured_outputs",
    "response_format",
    "stop",
    "frequency_penalty",
    "presence_penalty",
    "seed",
    "reasoning",
    "include_reasoning",
    "logprobs",
}
UNSUPPORTED_HOSTED_PARAMETERS = {
    "web_search",
    "web_search_options",
    "file_search",
    "code_interpreter",
    "computer",
    "computer_use",
    "image_generation",
    "tool_search",
}
OPENAI_ASSISTED_ACKNOWLEDGEMENT = (
    "OpenAI assisted catalog cross-checks are proposal-only and require operator review."
)

_PRICE_CELL_PATTERN = re.compile(r"^\$?(?P<amount>-?[0-9]+(?:\.[0-9]+)?)$")
_LABEL_PATTERN = re.compile(r"^(?P<label>[A-Za-z][A-Za-z0-9 /_-]+):\s*(?P<value>.+)$")
_MODEL_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{1,127}$")
_OPENAI_MODEL_IDENTIFIER_PATTERN = re.compile(
    r"^(?:"
    r"gpt(?:-[a-z0-9][a-z0-9.-]*)"
    r"|o[0-9](?:[a-z0-9.-]*)"
    r"|chatgpt-[a-z0-9][a-z0-9.-]*"
    r"|text-embedding-[a-z0-9][a-z0-9.-]*"
    r"|whisper-[a-z0-9][a-z0-9.-]*"
    r"|tts-[a-z0-9][a-z0-9.-]*"
    r"|omni-moderation-[a-z0-9][a-z0-9.-]*"
    r")$"
)
_NUMERIC_PATTERN = re.compile(r"^[0-9][0-9,]*$")
_WHITESPACE_PATTERN = re.compile(r"\s+")
_ROUTE_CONTEXT_PATTERN = re.compile(r"(?:^|[| ])context=(?P<value>[0-9]+)")
_ROUTE_MAX_OUTPUT_PATTERN = re.compile(r"(?:^|[| ])max_output_tokens=(?P<value>[0-9]+)")

OPENROUTER_CHAT_TEXT_PACKAGE = "openrouter-chat-text"
OPENROUTER_CHAT_IMAGE_PACKAGE = "openrouter-chat-image"
OPENROUTER_CHAT_AUDIO_PACKAGE = "openrouter-chat-audio"
OPENROUTER_CHAT_MULTIMODAL_PACKAGE = "openrouter-chat-multimodal"
OPENROUTER_RESPONSES_TEXT_PACKAGE = "openrouter-responses-text"

OPENROUTER_PACKAGE_ORDER = (
    OPENROUTER_CHAT_TEXT_PACKAGE,
    OPENROUTER_CHAT_IMAGE_PACKAGE,
    OPENROUTER_CHAT_AUDIO_PACKAGE,
    OPENROUTER_CHAT_MULTIMODAL_PACKAGE,
    OPENROUTER_RESPONSES_TEXT_PACKAGE,
)
OPENROUTER_PACKAGE_ALIASES = {
    "all": OPENROUTER_CHAT_MULTIMODAL_PACKAGE,
    "chat-text": OPENROUTER_CHAT_TEXT_PACKAGE,
    "chat-image": OPENROUTER_CHAT_IMAGE_PACKAGE,
    "chat-audio": OPENROUTER_CHAT_AUDIO_PACKAGE,
    "chat-multimodal": OPENROUTER_CHAT_MULTIMODAL_PACKAGE,
    "responses-text": OPENROUTER_RESPONSES_TEXT_PACKAGE,
}
PACKAGE_EXCLUDED_WARNING_CODES = (
    "missing_pricing",
    "zero_price_requires_review",
    "negative_or_invalid_price",
    "unsupported_modality",
    "search_specific_model",
    "hosted_tool_only",
    "deprecated_or_expiring",
    "ambiguous_capability",
)


@dataclass(frozen=True, slots=True)
class ProviderCatalogSource:
    provider: ProviderName
    source_type: str
    url: str
    retrieved_at: str
    content_hash: str
    content_type: str | None
    warnings: tuple[str, ...] = ()
    snapshot_path: str | None = None


@dataclass(frozen=True, slots=True)
class ProviderCatalogWarning:
    code: str
    message: str
    provider: ProviderName
    model_id: str | None = None
    endpoint: str | None = None
    sources: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ProviderCatalogModelCandidate:
    provider: ProviderName
    model_id: str
    canonical_model_id: str | None
    display_name: str | None
    description: str | None
    endpoints: tuple[str, ...]
    input_modalities: tuple[str, ...]
    output_modalities: tuple[str, ...]
    context_length: int | None
    max_output_tokens: int | None
    knowledge_cutoff: str | None
    supports_streaming: bool | None
    supported_parameters: tuple[str, ...]
    capabilities: dict[str, object]
    confidence: Confidence
    source_evidence: tuple[str, ...]
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ProviderCatalogPricingCandidate:
    provider: ProviderName
    model_id: str
    endpoint: str
    currency: str
    input_price_per_1m: str | None
    cached_input_price_per_1m: str | None
    output_price_per_1m: str | None
    reasoning_price_per_1m: str | None
    request_price: str | None
    source_url: str
    source_retrieved_at: str
    pricing_metadata: dict[str, object]
    notes: str
    confidence: Confidence
    ready_for_import: bool
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ProviderCatalogRouteCandidate:
    requested_model: str
    match_type: str
    endpoint: str
    provider: ProviderName
    upstream_model: str
    priority: int
    enabled: bool
    visible_in_models: bool
    supports_streaming: bool
    capabilities: dict[str, object]
    notes: str
    confidence: Confidence
    ready_for_import: bool
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ProposalFxCapture:
    """Immutable USD->target FX fact captured ONCE for one proposal run.

    Every field is a safe string projection (no raw Decimal/UUID/datetime
    objects), so the capture can be embedded in report/metadata/manifest
    projections without echoing secrets or environment values. Official
    source amounts stay native USD through parsing and cross-checking; a
    non-USD proposal is generated with the capture whose target_currency
    matches the requested output currency. USD output is the identity
    conversion and needs no capture (and no database).
    """

    base_currency: str
    target_currency: str
    fx_rate_id: str
    rate: str
    valid_from: str
    valid_until: str | None
    captured_at: str


def make_proposal_fx_capture(
    *,
    target_currency: str,
    fx_rate_id: str | uuid.UUID,
    rate: Decimal,
    valid_from: datetime,
    valid_until: datetime | None,
    captured_at: datetime,
) -> ProposalFxCapture:
    """Build one immutable capture from ONE configured USD->target row.

    Pure and fail-closed: the source currency is always native USD, the
    rate must be a positive finite Decimal, timestamps must be aware,
    and captured_at must lie inside the row's validity window (the
    repository already filters by at_time; this re-checks the pure seam
    so a stale row can never be captured into an output).
    """
    target = target_currency.strip().upper()
    if len(target) != 3 or not target.isalpha():
        raise ValueError("currency must be a 3-letter ISO code")
    if not isinstance(rate, Decimal) or not rate.is_finite() or rate <= 0:
        raise ValueError("fx rate must be a positive finite Decimal")
    if valid_from.tzinfo is None:
        raise ValueError("fx rate valid_from must be timezone-aware")
    if valid_until is not None and valid_until.tzinfo is None:
        raise ValueError("fx rate valid_until must be timezone-aware")
    if valid_until is not None and valid_until <= valid_from:
        raise ValueError("fx rate validity window is empty")
    if captured_at.tzinfo is None:
        raise ValueError("fx capture time must be timezone-aware")
    if captured_at < valid_from:
        raise ValueError("fx rate is not yet valid at the capture time")
    if valid_until is not None and captured_at >= valid_until:
        raise ValueError("fx rate is expired at the capture time")
    # The source rate id is a canonical UUID fact (the configured row's
    # identity), not free text: normalize through UUID, refuse otherwise.
    if not isinstance(fx_rate_id, uuid.UUID):
        try:
            fx_rate_id = uuid.UUID(str(fx_rate_id))
        except ValueError as exc:
            raise ValueError("fx rate id must be a canonical UUID") from exc
    return ProposalFxCapture(
        base_currency="USD",
        target_currency=target,
        fx_rate_id=str(fx_rate_id),
        rate=_decimal_to_string(rate),
        valid_from=_utc_z(valid_from),
        valid_until=_utc_z(valid_until) if valid_until is not None else None,
        captured_at=_utc_z(captured_at),
    )


def _utc_z(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


_PROPOSAL_FX_QUANTUM = Decimal("0.000000001")
_PROPOSAL_FX_MAX = Decimal("999999999.999999999")


def _convert_proposal_price_text(text: str | None, rate: Decimal) -> str | None:
    """Apply ONE captured USD->target rate to one canonical price text.

    Follows the established price contract (Numeric(18,9)): quantize to
    1e-9 with ROUND_HALF_UP under a sufficient local precision, preserve
    missing (None) and exact zero, and refuse positive-to-zero underflow
    and values above the 9-integer/9-fraction import bound. Never
    silently underflows a positive price to a free one.
    """
    if text is None:
        return None
    if not isinstance(text, str):
        raise ValueError("proposal price must be an exact decimal string")
    # Reuse the EXISTING Numeric(18,9) validation (finite, non-negative,
    # within the 9-integer/9-fraction bound) BEFORE any arithmetic rather
    # than trusting the candidate text.
    try:
        checked = parse_decimal_text(text, field="proposal price", non_negative=True)
    except ValueError as exc:
        raise ValueError("proposal price is outside the Numeric(18,9) contract") from exc
    value = Decimal(checked)
    if value == 0:
        return "0"
    with localcontext() as ctx:
        ctx.prec = 50
        converted = (value * rate).quantize(_PROPOSAL_FX_QUANTUM, rounding=ROUND_HALF_UP)
    if converted == 0:
        raise ValueError("fx conversion underflow: a positive price became zero")
    if converted > _PROPOSAL_FX_MAX:
        raise ValueError("fx conversion overflow: price exceeds the import bound")
    return _decimal_to_string(converted)


def apply_proposal_fx(
    candidates: Sequence[ProviderCatalogPricingCandidate],
    capture: ProposalFxCapture | None,
) -> list[ProviderCatalogPricingCandidate]:
    """Convert every pricing candidate into the capture's target currency.

    Pure and applied ONCE per run, before any writer: USD (or no capture)
    returns the candidates unchanged (byte-identical, no FX metadata).
    A non-USD capture applies one Decimal conversion to EVERY monetary
    dimension (per-1M token prices and the per-request price), updates
    the row currency, and preserves the original source-currency amounts
    plus the applied FX pair/rate id/rate/validity/capture time in the
    candidate's pricing_metadata. Raises ValueError on underflow/
    overflow so the caller refuses before writing any output.
    """
    if capture is None or capture.target_currency == capture.base_currency:
        return list(candidates)
    rate = Decimal(capture.rate)
    converted: list[ProviderCatalogPricingCandidate] = []
    for candidate in candidates:
        # The shared composition always hands this converter native-USD
        # source candidates: any other label means the candidate was
        # already converted (or forged) and a second multiplication must
        # be impossible, not silent.
        if candidate.currency != capture.base_currency:
            raise ValueError(
                "proposal fx double application: candidate currency is not "
                "the capture base currency"
            )
        source_prices = {
            "input_price_per_1m": candidate.input_price_per_1m,
            "cached_input_price_per_1m": candidate.cached_input_price_per_1m,
            "output_price_per_1m": candidate.output_price_per_1m,
            "reasoning_price_per_1m": candidate.reasoning_price_per_1m,
            "request_price": candidate.request_price,
        }
        metadata = dict(candidate.pricing_metadata)
        metadata["source_currency"] = candidate.currency
        metadata["source_prices"] = source_prices
        metadata["fx"] = {
            "base_currency": capture.base_currency,
            "target_currency": capture.target_currency,
            "fx_rate_id": capture.fx_rate_id,
            "rate": capture.rate,
            "valid_from": capture.valid_from,
            "valid_until": capture.valid_until,
            "captured_at": capture.captured_at,
        }
        # The original source pricing_unit (e.g. "usd_per_token") is the
        # OFFICIAL SOURCE unit and stays untouched: the row currency plus
        # the fx metadata state the applied conversion; the source unit is
        # never relabeled.
        converted.append(
            replace(
                candidate,
                currency=capture.target_currency,
                input_price_per_1m=_convert_proposal_price_text(candidate.input_price_per_1m, rate),
                cached_input_price_per_1m=_convert_proposal_price_text(
                    candidate.cached_input_price_per_1m, rate
                ),
                output_price_per_1m=_convert_proposal_price_text(candidate.output_price_per_1m, rate),
                reasoning_price_per_1m=_convert_proposal_price_text(
                    candidate.reasoning_price_per_1m, rate
                ),
                request_price=_convert_proposal_price_text(candidate.request_price, rate),
                pricing_metadata=metadata,
            )
        )
    return converted


@dataclass(frozen=True, slots=True)
class ProviderCatalogModelStatus:
    provider: ProviderName
    model_id: str
    pricing_status: str
    route_status: str
    sources_seen: tuple[str, ...]
    confidence: Confidence
    warnings: tuple[str, ...]
    ready_for_route_import: bool
    ready_for_pricing_import: bool


@dataclass(frozen=True, slots=True)
class ProviderCatalogProposalBundle:
    providers: tuple[ProviderName, ...]
    sources: tuple[ProviderCatalogSource, ...]
    models: tuple[ProviderCatalogModelCandidate, ...]
    pricing_candidates: tuple[ProviderCatalogPricingCandidate, ...]
    route_candidates: tuple[ProviderCatalogRouteCandidate, ...]
    comparison_rows: tuple[ProviderCatalogModelStatus, ...]
    warnings: tuple[ProviderCatalogWarning, ...]


@dataclass(frozen=True, slots=True)
class ProviderCatalogProposalResult:
    output_dir: Path
    routes_proposal_path: Path
    pricing_proposal_path: Path
    normalized_path: Path
    report_path: Path
    warnings_path: Path
    manifest_path: Path
    route_rows_ready: int
    pricing_rows_ready: int
    warnings_count: int
    high_confidence: int
    medium_confidence: int
    low_confidence: int
    paired_ready_only: bool = False
    ordinary_chat_only: bool = True
    package_index_path: Path | None = None
    package_index_markdown_path: Path | None = None
    package_names: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ProviderCatalogPackageResult:
    package_name: str
    package_dir: Path
    endpoint_family: str
    endpoint: str
    route_rows: int
    pricing_rows: int
    superset_of: tuple[str, ...]
    includes_packages: tuple[str, ...]
    recommendation: str
    warning_counts: Mapping[str, int]
    excluded_counts: Mapping[str, int]


class ProviderCatalogProposalValidationError(ValueError):
    """Raised when generated proposal TSV artifacts fail local validation."""

    def __init__(self, message: str) -> None:
        super().__init__(f"{PROPOSAL_TSV_VALIDATION_ERROR_CODE}: {message}")


class ProviderCatalogProposalSizeError(ValueError):
    """Raised when generated proposal artifacts exceed the ENFORCED byte
    ceiling bound to the custody admission reservation. The generator
    stops mid-generation (before further growth) so the reservation is a
    real enforced ceiling, not an estimate; the caller retracts the
    partial output so no over-ceiling artifact is ever left behind."""

    def __init__(self, message: str) -> None:
        super().__init__(f"{PROPOSAL_OUTPUT_SIZE_EXCEEDED_CODE}: {message}")


@dataclass(frozen=True, slots=True)
class _FetchedSource:
    provider: ProviderName
    source_type: str
    url: str
    retrieved_at: str
    content_hash: str
    content_type: str | None
    raw_text: str | None = None
    raw_json: Mapping[str, object] | None = None
    snapshot_path: str | None = None
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class _OpenAIPricingRecord:
    model_id: str
    input_price_per_1m: str | None
    cached_input_price_per_1m: str | None
    output_price_per_1m: str | None
    reasoning_price_per_1m: str | None
    request_price: str | None
    category: str | None
    modality: str | None
    source_url: str
    source_retrieved_at: str
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class _OpenAIModelRecord:
    model_id: str
    display_name: str | None
    description: str | None
    endpoints: tuple[str, ...]
    features: tuple[str, ...]
    context_length: int | None
    max_output_tokens: int | None
    knowledge_cutoff: str | None
    warnings: tuple[str, ...] = ()


class _ProposalOutputBudget:
    """Small BEFORE-GROWTH write-admission budget for ONE proposal
    generation. ``cap`` is the enforced ceiling (the custody admission
    reservation). ``committed`` is a CONSERVATIVE per-generation
    admission counter: each payload's FULL size is charged BEFORE its
    file is written, and is NEVER refunded on a partial/failed/overwrite
    attempt (a source-details helper may catch a write error and continue,
    so successful-write-only charging would under-count). Admission is
    O(1) per write (no full-tree rescan): a payload is admitted only if
    committed + size <= cap, so an over-ceiling payload is refused and
    never written. The ACTUAL at-rest bytes are measured separately by
    the custody gate (``account_proposal_output``); this budget only
    bounds growth before it happens."""

    def __init__(self, cap: int) -> None:
        self.cap = int(cap)
        self.committed = 0

    def admit(self, size: int) -> None:
        if self.committed + int(size) > self.cap:
            raise ProviderCatalogProposalSizeError(
                f"provider catalog proposal write of {size} bytes would "
                f"exceed its enforced byte ceiling (committed {self.committed} "
                f"+ {size} > {self.cap} bytes)"
            )
        self.committed += int(size)  # charge BEFORE the write; no refund


# Default-optional injected generation budget (ContextVar, so every write
# in the current generation task routes through the same O(1) admission
# without threading the object through every fetch/write signature). The
# default None leaves CLI behavior unchanged (the CLI composes this
# directly and reserves no custody bytes).
_PROPOSAL_OUTPUT_BUDGET: ContextVar[_ProposalOutputBudget | None] = ContextVar(
    "slaif_proposal_output_budget", default=None
)


def _emit(path: Path, data: bytes) -> None:
    """Admit-then-write the encoded payload for the active generation
    budget, THEN write. ``admit`` runs BEFORE any open/truncate/write and
    charges the full size with NO refund, so an over-ceiling payload is
    refused and never written, and a caught/partial/failed write still
    conservatively consumes the budget. A None budget (CLI) writes
    freely."""
    budget = _PROPOSAL_OUTPUT_BUDGET.get()
    if budget is not None:
        budget.admit(len(data))
    path.write_bytes(data)


async def generate_provider_catalog_proposal(
    *,
    provider_scope: ProviderName | Literal["all"],
    output_dir: Path,
    endpoint_scopes: Sequence[EndpointScope] = DEFAULT_ENDPOINT_SCOPES,
    include_models: Sequence[str] = (),
    exclude_models: Sequence[str] = (),
    currency: str = "USD",
    source_methods: Sequence[ProposalSourceMethod] | None = None,
    max_models: int = 500,
    fetch_details_limit: int = 50,
    include_api_models: bool = False,
    max_web_calls: int = 3,
    save_source_snapshots: bool = False,
    acknowledge_assisted_proposal_risk: bool = False,
    allow_zero_prices: bool = False,
    paired_ready_only: bool = False,
    ordinary_chat_only: bool = True,
    package_names: Sequence[str] = (),
    all_packages: bool = False,
    include_deprecated: bool = False,
    include_ambiguous_capabilities: bool = False,
    http_client: httpx.AsyncClient | None = None,
    now: datetime | None = None,
    max_output_bytes: int | None = None,
    fx_capture: ProposalFxCapture | None = None,
) -> ProviderCatalogProposalResult:
    """Generate proposal artifacts without mutating local metadata."""

    providers = _normalize_provider_scope(provider_scope)
    endpoint_scope_values = _normalize_endpoint_scopes(endpoint_scopes)
    source_method_values = _normalize_source_methods(
        provider_scope=provider_scope,
        source_methods=source_methods,
        include_api_models=include_api_models,
    )
    normalized_currency = _normalize_currency(currency)
    if fx_capture is None and normalized_currency != "USD":
        # Fail closed BEFORE any directory/network work: a non-USD output
        # currency always carries one captured configured FX rate; there
        # is no silent relabeling path. USD remains offline-capable.
        raise ValueError(
            "a non-USD output currency requires an fx capture (one "
            "configured direct USD->target FX rate); USD is the only "
            "offline-capable output currency"
        )
    if fx_capture is not None:
        if fx_capture.base_currency != "USD":
            raise ValueError("fx capture base currency must be USD (native source currency)")
        if fx_capture.target_currency != normalized_currency:
            raise ValueError("fx capture target does not match the requested output currency")
    normalized_package_names = _normalize_openrouter_package_names(
        provider_scope=provider_scope,
        package_names=package_names,
        all_packages=all_packages,
    )
    _require_positive(max_models, label="max_models")
    _require_non_negative(fetch_details_limit, label="fetch_details_limit")
    _require_positive(max_web_calls, label="max_web_calls")
    if "assisted" in source_method_values and not acknowledge_assisted_proposal_risk:
        raise ValueError("--acknowledge-assisted-proposal-risk is required when using source=assisted")
    output_dir.mkdir(parents=True, exist_ok=True)
    source_dir = output_dir / "sources"
    if save_source_snapshots:
        source_dir.mkdir(parents=True, exist_ok=True)

    owns_client = http_client is None
    client = http_client or httpx.AsyncClient(timeout=60.0, follow_redirects=True)
    bundle_warnings: list[ProviderCatalogWarning] = []
    sources: list[ProviderCatalogSource] = []
    models: list[ProviderCatalogModelCandidate] = []
    pricing_candidates: list[ProviderCatalogPricingCandidate] = []
    route_candidates: list[ProviderCatalogRouteCandidate] = []
    comparison_rows: list[ProviderCatalogModelStatus] = []

    budget = (
        _ProposalOutputBudget(max_output_bytes)
        if max_output_bytes is not None
        else None
    )
    budget_token = _PROPOSAL_OUTPUT_BUDGET.set(budget)
    try:
        for provider in providers:
            # The provider proposers always receive the NATIVE source
            # currency (USD): official source amounts stay native USD
            # through parsing and cross-checking (assisted outputs
            # included). The requested output currency is applied exactly
            # once by apply_proposal_fx, below, before any writer.
            if provider == OPENROUTER_PROVIDER:
                provider_bundle = await _propose_openrouter(
                    client=client,
                    endpoint_scopes=endpoint_scope_values,
                    include_models=include_models,
                    exclude_models=exclude_models,
                    currency="USD",
                    source_methods=source_method_values,
                    max_models=max_models,
                    fetch_details_limit=fetch_details_limit,
                    save_source_snapshots=save_source_snapshots,
                    source_dir=source_dir,
                    allow_zero_prices=allow_zero_prices,
                    ordinary_chat_only=ordinary_chat_only,
                    now=now,
                )
            else:
                provider_bundle = await _propose_openai(
                    client=client,
                    endpoint_scopes=endpoint_scope_values,
                    include_models=include_models,
                    exclude_models=exclude_models,
                    currency="USD",
                    source_methods=source_method_values,
                    include_api_models=include_api_models,
                    max_web_calls=max_web_calls,
                    max_models=max_models,
                    save_source_snapshots=save_source_snapshots,
                    source_dir=source_dir,
                    acknowledge_assisted_proposal_risk=acknowledge_assisted_proposal_risk,
                    allow_zero_prices=allow_zero_prices,
                    ordinary_chat_only=ordinary_chat_only,
                    now=now,
                )
            sources.extend(provider_bundle.sources)
            models.extend(provider_bundle.models)
            # ONE conversion, applied before ANY writer (root JSON/TSV/
            # report and the package outputs all share these candidates):
            # native USD candidates are converted to the requested output
            # currency with the single captured rate, or left
            # byte-identical for USD.
            pricing_candidates.extend(
                apply_proposal_fx(provider_bundle.pricing_candidates, fx_capture)
            )
            route_candidates.extend(provider_bundle.route_candidates)
            comparison_rows.extend(provider_bundle.comparison_rows)
            bundle_warnings.extend(provider_bundle.warnings)

        normalized_path = output_dir / "provider-catalog-normalized.json"
        report_path = output_dir / "provider-catalog-report.md"
        warnings_path = output_dir / "warnings.json"
        manifest_path = output_dir / "source-manifest.json"
        routes_path = output_dir / "routes-proposal.tsv"
        pricing_path = output_dir / "pricing-proposal.tsv"
        package_index_path: Path | None = None
        package_index_markdown_path: Path | None = None

        exported_route_candidates, exported_pricing_candidates = _select_export_candidates(
            route_candidates,
            pricing_candidates,
            paired_ready_only=paired_ready_only,
        )

        _write_json(
            normalized_path,
            {
                "providers": list(providers),
                "fx": _fx_projection(fx_capture),
                "export_filters": {
                    "paired_ready_only": paired_ready_only,
                    "ordinary_chat_only": ordinary_chat_only,
                },
                "export_row_counts": {
                    "routes": len(exported_route_candidates),
                    "pricing": len(exported_pricing_candidates),
                },
                "models": [_jsonify_dataclass(item) for item in models],
                "pricing_candidates": [_jsonify_dataclass(item) for item in pricing_candidates],
                "route_candidates": [_jsonify_dataclass(item) for item in route_candidates],
                "comparison_rows": [_jsonify_dataclass(item) for item in comparison_rows],
            },
        )
        _write_json(
            warnings_path,
            {"warnings": [_jsonify_dataclass(item) for item in bundle_warnings]},
        )
        _write_json(
            manifest_path,
            {
                "sources": [_jsonify_dataclass(item) for item in sources],
                "output_files": list(SUPPORTED_OUTPUT_FILES),
                "fx": _fx_projection(fx_capture),
                "generated_at": _timestamp(now),
                "extractor_version": "provider_catalog_proposal_v1",
            },
        )
        _write_route_tsv(routes_path, exported_route_candidates, ordinary_chat_only=ordinary_chat_only)
        _write_pricing_tsv(pricing_path, exported_pricing_candidates)
        _emit(
            report_path,
            _render_report(
                providers=providers,
                fx_capture=fx_capture,
                comparison_rows=comparison_rows,
                warnings=bundle_warnings,
                route_candidates=route_candidates,
                pricing_candidates=pricing_candidates,
                exported_route_candidates=exported_route_candidates,
                exported_pricing_candidates=exported_pricing_candidates,
                paired_ready_only=paired_ready_only,
                ordinary_chat_only=ordinary_chat_only,
            ).encode("utf-8"),
        )
        _validate_generated_route_tsv(routes_path, exported_route_candidates)
        _validate_generated_pricing_tsv(pricing_path, exported_pricing_candidates)

        if normalized_package_names:
            package_results = await _generate_openrouter_package_outputs(
                client=client,
                output_dir=output_dir,
                package_names=normalized_package_names,
                include_models=include_models,
                exclude_models=exclude_models,
                source_methods=source_method_values,
                max_models=max_models,
                fetch_details_limit=fetch_details_limit,
                save_source_snapshots=save_source_snapshots,
                source_dir=source_dir,
                allow_zero_prices=allow_zero_prices,
                include_deprecated=include_deprecated,
                include_ambiguous_capabilities=include_ambiguous_capabilities,
                now=now,
                source_manifest_path=manifest_path,
                fx_capture=fx_capture,
            )
            package_index_path = output_dir / PACKAGE_INDEX_FILENAME
            package_index_markdown_path = output_dir / PACKAGE_INDEX_MARKDOWN_FILENAME
            _write_package_indexes(
                package_index_path=package_index_path,
                package_index_markdown_path=package_index_markdown_path,
                package_results=package_results,
            )

        confidence_counts = _count_confidence(models)
        return ProviderCatalogProposalResult(
            output_dir=output_dir,
            routes_proposal_path=routes_path,
            pricing_proposal_path=pricing_path,
            normalized_path=normalized_path,
            report_path=report_path,
            warnings_path=warnings_path,
            manifest_path=manifest_path,
            route_rows_ready=len(exported_route_candidates),
            pricing_rows_ready=len(exported_pricing_candidates),
            warnings_count=len(bundle_warnings),
            high_confidence=confidence_counts["high"],
            medium_confidence=confidence_counts["medium"],
            low_confidence=confidence_counts["low"],
            paired_ready_only=paired_ready_only,
            ordinary_chat_only=ordinary_chat_only,
            package_index_path=package_index_path,
            package_index_markdown_path=package_index_markdown_path,
            package_names=normalized_package_names,
        )
    finally:
        _PROPOSAL_OUTPUT_BUDGET.reset(budget_token)
        if owns_client:
            await client.aclose()


async def _propose_openrouter(
    *,
    client: httpx.AsyncClient,
    endpoint_scopes: tuple[EndpointScope, ...],
    include_models: Sequence[str],
    exclude_models: Sequence[str],
    currency: str,
    source_methods: tuple[ProposalSourceMethod, ...],
    max_models: int,
    fetch_details_limit: int,
    save_source_snapshots: bool,
    source_dir: Path,
    allow_zero_prices: bool,
    ordinary_chat_only: bool,
    now: datetime | None,
) -> ProviderCatalogProposalBundle:
    if "assisted" in source_methods:
        raise ValueError("OpenRouter assisted proposal source is not implemented")
    warnings: list[ProviderCatalogWarning] = []
    fetched_sources: list[_FetchedSource] = []
    models_source = await _fetch_text_source(
        client=client,
        provider=OPENROUTER_PROVIDER,
        source_type="docs",
        url=OPENROUTER_MODELS_DOCS_MARKDOWN_URL,
        save_snapshot=save_source_snapshots,
        source_dir=source_dir,
        now=now,
    )
    fetched_sources.append(models_source)
    unit_confirmed = _confirm_openrouter_pricing_unit(models_source.raw_text or "")
    if not unit_confirmed:
        warnings.append(
            ProviderCatalogWarning(
                code="unit_unconfirmed",
                message="OpenRouter pricing unit could not be confirmed from official docs.",
                provider=OPENROUTER_PROVIDER,
                sources=(models_source.url,),
            )
        )
    api_source = await _fetch_json_source(
        client=client,
        provider=OPENROUTER_PROVIDER,
        source_type="api",
        url=OPENROUTER_MODELS_API_URL,
        save_snapshot=save_source_snapshots,
        source_dir=source_dir,
        now=now,
    )
    fetched_sources.append(api_source)

    details_by_model = {}
    for detail in await _fetch_openrouter_detail_sources(
        client=client,
        models_payload=api_source.raw_json or {},
        fetch_details_limit=fetch_details_limit,
        save_source_snapshots=save_source_snapshots,
        source_dir=source_dir,
        now=now,
    ):
        fetched_sources.append(detail)
        model_id = _model_id_from_detail_url(detail.url)
        if model_id:
            details_by_model[model_id] = detail.raw_json or {}

    raw_models = _openrouter_models_from_payload(api_source.raw_json or {})
    selected_rows = [
        row
        for row in raw_models
        if _model_allowed(row.get("id"), include_models=include_models, exclude_models=exclude_models)
    ][:max_models]
    model_candidates: list[ProviderCatalogModelCandidate] = []
    pricing_candidates: list[ProviderCatalogPricingCandidate] = []
    route_candidates: list[ProviderCatalogRouteCandidate] = []
    comparison_rows: list[ProviderCatalogModelStatus] = []

    for row in selected_rows:
        model_id = _safe_model_id(row.get("id"))
        if model_id is None:
            warnings.append(
                ProviderCatalogWarning(
                    code="invalid_model_id",
                    message="OpenRouter model row had no safe model id.",
                    provider=OPENROUTER_PROVIDER,
                    sources=(api_source.url,),
                )
            )
            continue
        supported_parameters = _string_tuple(row.get("supported_parameters"))
        input_modalities = _string_tuple(((row.get("architecture") or {}) if isinstance(row.get("architecture"), Mapping) else {}).get("input_modalities"))
        output_modalities = _string_tuple(((row.get("architecture") or {}) if isinstance(row.get("architecture"), Mapping) else {}).get("output_modalities"))
        pricing = row.get("pricing") if isinstance(row.get("pricing"), Mapping) else {}
        top_provider = row.get("top_provider") if isinstance(row.get("top_provider"), Mapping) else {}
        detail_json = details_by_model.get(model_id, {})
        model_warnings = _openrouter_model_warnings(
            model_id=model_id,
            supported_parameters=supported_parameters,
            input_modalities=input_modalities,
            output_modalities=output_modalities,
            expiration_date=_safe_text(row.get("expiration_date")),
            ordinary_chat_only=ordinary_chat_only,
        )
        confidence: Confidence = "high" if unit_confirmed else "medium"
        model_candidates.append(
            ProviderCatalogModelCandidate(
                provider=OPENROUTER_PROVIDER,
                model_id=model_id,
                canonical_model_id=_safe_text(row.get("canonical_slug")),
                display_name=_safe_text(row.get("name")),
                description=_safe_text(row.get("description")),
                endpoints=(CHAT_COMPLETIONS_ENDPOINT,),
                input_modalities=input_modalities,
                output_modalities=output_modalities,
                context_length=_safe_int(row.get("context_length")),
                max_output_tokens=_safe_int(top_provider.get("max_completion_tokens"))
                or _safe_int(_detail_lookup(detail_json, "max_completion_tokens")),
                knowledge_cutoff=_safe_text(row.get("knowledge_cutoff")),
                supports_streaming="text" in output_modalities,
                supported_parameters=supported_parameters,
                capabilities=_build_chat_capabilities(
                    supported_parameters=supported_parameters,
                    input_modalities=input_modalities,
                    output_modalities=output_modalities,
                    supports_streaming="text" in output_modalities,
                    provider=OPENROUTER_PROVIDER,
                    supports_cached_input_usage="input_cache_read" in pricing,
                ),
                confidence=confidence,
                source_evidence=tuple(filter(None, (api_source.url, models_source.url))),
                warnings=model_warnings,
            )
        )
        route_status = "report-only"
        route_ready = False
        if "chat_completions" in endpoint_scopes and _openrouter_route_ready(
            model_id=model_id,
            output_modalities=output_modalities,
            warnings=model_warnings,
        ):
            route_ready = True
            route_status = "ready"
            route_candidates.append(
                ProviderCatalogRouteCandidate(
                    requested_model=model_id,
                    match_type="exact",
                    endpoint=CHAT_COMPLETIONS_ENDPOINT,
                    provider=OPENROUTER_PROVIDER,
                    upstream_model=model_id,
                    priority=100,
                    enabled=True,
                    visible_in_models="deprecated_or_expiring" not in model_warnings
                    and "hidden_from_models" not in model_warnings,
                    supports_streaming="text" in output_modalities,
                    capabilities=_build_chat_capabilities(
                        supported_parameters=supported_parameters,
                        input_modalities=input_modalities,
                        output_modalities=output_modalities,
                        supports_streaming="text" in output_modalities,
                        provider=OPENROUTER_PROVIDER,
                        supports_cached_input_usage="input_cache_read" in pricing,
                    ),
                    notes=_route_notes(
                        provider=OPENROUTER_PROVIDER,
                        model_id=model_id,
                        confidence=confidence,
                        context_length=_safe_int(row.get("context_length")),
                        max_output_tokens=_safe_int(top_provider.get("max_completion_tokens")),
                        source_urls=(api_source.url, models_source.url),
                        warnings=model_warnings,
                    ),
                    confidence=confidence,
                    ready_for_import=True,
                    warnings=model_warnings,
                )
            )
        elif "responses" in endpoint_scopes:
            warnings.append(
                ProviderCatalogWarning(
                    code="future_endpoint",
                    message=(
                        "OpenRouter responses route proposals are report-only in this workflow; "
                        "chat.completions remains the ready import target."
                    ),
                    provider=OPENROUTER_PROVIDER,
                    model_id=model_id,
                    endpoint=RESPONSES_ENDPOINT,
                    sources=(api_source.url,),
                )
            )

        pricing_row, pricing_warning_codes = _openrouter_pricing_candidate(
            model_id=model_id,
            pricing=pricing,
            currency=currency,
            source_url=api_source.url,
            source_retrieved_at=api_source.retrieved_at,
            unit_confirmed=unit_confirmed,
            confidence=confidence,
            model_warnings=model_warnings,
            allow_zero_prices=allow_zero_prices,
        )
        pricing_status = "missing"
        pricing_ready = False
        if pricing_row is not None and "chat_completions" in endpoint_scopes:
            pricing_ready = pricing_row.ready_for_import
            pricing_status = "ready" if pricing_ready else "report-only"
            pricing_candidates.append(pricing_row)
        elif pricing_warning_codes:
            pricing_status = "report-only"
        comparison_rows.append(
            ProviderCatalogModelStatus(
                provider=OPENROUTER_PROVIDER,
                model_id=model_id,
                pricing_status=pricing_status,
                route_status=route_status,
                sources_seen=("api", "docs"),
                confidence=confidence,
                warnings=tuple(sorted(set(model_warnings + pricing_warning_codes))),
                ready_for_route_import=route_ready,
                ready_for_pricing_import=pricing_ready,
            )
        )
        for warning_code in pricing_warning_codes:
            warnings.append(
                ProviderCatalogWarning(
                    code=warning_code,
                    message=_warning_message(warning_code, model_id),
                    provider=OPENROUTER_PROVIDER,
                    model_id=model_id,
                    endpoint=CHAT_COMPLETIONS_ENDPOINT,
                    sources=(api_source.url, models_source.url),
                )
            )
        for warning_code in model_warnings:
            warnings.append(
                ProviderCatalogWarning(
                    code=warning_code,
                    message=_warning_message(warning_code, model_id),
                    provider=OPENROUTER_PROVIDER,
                    model_id=model_id,
                    endpoint=CHAT_COMPLETIONS_ENDPOINT,
                    sources=(api_source.url, models_source.url),
                )
            )

    return ProviderCatalogProposalBundle(
        providers=(OPENROUTER_PROVIDER,),
        sources=tuple(_source_to_manifest_entry(item) for item in fetched_sources),
        models=tuple(model_candidates),
        pricing_candidates=tuple(pricing_candidates),
        route_candidates=tuple(route_candidates),
        comparison_rows=tuple(comparison_rows),
        warnings=tuple(_dedupe_warning_objects(warnings)),
    )



async def _openai_markdown_documents(
    *, client: httpx.AsyncClient, fetched_sources: list[_FetchedSource],
    warnings: list[ProviderCatalogWarning], include_models: Sequence[str],
    exclude_models: Sequence[str], max_models: int, ordinary_chat_only: bool,
    save_source_snapshots: bool, source_dir: Path, now: datetime | None,
) -> tuple[_FetchedSource, tuple[_OpenAIPricingRecord, ...], dict[str, _OpenAIModelRecord], dict[str, str]]:
    """Bounded official page-backed fallback; API identity never grants endpoints.

    Reuse the existing strict per-model snapshot parser. Fetch only models
    with flat Standard pricing and a literal official-index identity, at
    most 64 pages / four concurrent requests. No aliases or prices are guessed.
    """
    from slaif_gateway.services.catalog_refresh.source_evidence import (
        SnapshotFormatError, parse_openai_model_doc_snapshot,
        parse_openai_models_docs_snapshot,
    )

    async def fetch(url: str, kind: str) -> _FetchedSource:
        source = await _fetch_text_source(
            client=client, provider=OPENAI_PROVIDER, source_type=kind,
            url=url, save_snapshot=save_source_snapshots,
            source_dir=source_dir, now=now,
        )
        fetched_sources.append(source)
        return source

    pricing = await fetch(OPENAI_PRICING_DOCS_URL + ".md", "docs_pricing_markdown")
    index = await fetch(OPENAI_MODELS_DOCS_URL + ".md", "docs_models_markdown")
    prices = _parse_openai_pricing_docs(
        text=pricing.raw_text or "", source_url=pricing.url,
        source_retrieved_at=pricing.retrieved_at,
    )
    # Do not flatten the newer cache-write/context-tier table into token
    # prices. This flat TSV family cannot represent those dimensions.
    if re.search(r"\|[^\n]*Short context input", pricing.raw_text or "", re.IGNORECASE):
        warnings.append(ProviderCatalogWarning(
            code="contextual_pricing_report_only", provider=OPENAI_PROVIDER,
            message="Context-dependent/cache-write price tables are outside this flat-price proposal format; only explicit flat Standard rows are eligible.",
        ))
    identities = {row.model for row in parse_openai_models_docs_snapshot(
        (index.raw_text or "").encode("utf-8")
    )}
    candidates = sorted({row.model_id for row in prices} & identities)
    candidates = [m for m in candidates if _model_allowed(
        m, include_models=include_models, exclude_models=exclude_models
    )]
    cap = min(max_models, 64)
    if len(candidates) > cap:
        warnings.append(ProviderCatalogWarning(
            code="model_page_cap_applied", provider=OPENAI_PROVIDER,
            message=f"Official model-page cap {cap} omitted {len(candidates)-cap} candidates.",
        ))
    semaphore = asyncio.Semaphore(4)

    async def page(model_id: str) -> tuple[str, _OpenAIModelRecord | None, str | None]:
        async with semaphore:
            try:
                source = await fetch(
                    OPENAI_MODELS_DOCS_URL + "/" + model_id + ".md",
                    "docs_model_" + model_id,
                )
                parsed = parse_openai_model_doc_snapshot((source.raw_text or "").encode("utf-8"))[0]
            except (httpx.HTTPError, SnapshotFormatError):
                return model_id, None, None
            if parsed.model != model_id or parsed.text_modality is not True:
                return model_id, None, None
            # A text-only projection of a vision-capable model does not grant
            # image or hosted-tool authority. Explicit multimodal proposals
            # retain image input behind the existing route capability gates.
            text = source.raw_text or ""
            section = ""
            flags = set()
            for line in text.splitlines():
                stripped = line.strip()
                if stripped.startswith("#"):
                    section = stripped.lstrip("#").strip().lower()
                elif section == "supported features" and stripped.startswith("- "):
                    feature = stripped[2:].strip()
                    translated = {"streaming":"streaming", "function_calling":"function calling",
                                  "structured_outputs":"structured outputs", "logprobs":"logprobs",
                                  "reasoning":"reasoning"}.get(feature)
                    if translated:
                        flags.add(translated)
                if not ordinary_chat_only and stripped.startswith("- Input modalities:"):
                    if "image" in {m.strip() for m in stripped.partition(":")[2].split(",")}:
                        flags.add("image input")
            endpoint_set = set()
            section = ""
            for line in text.splitlines():
                stripped = line.strip()
                if stripped.startswith("#"):
                    section = stripped.lstrip("#").strip().lower()
                if section != "endpoints" or not stripped.startswith("|"):
                    continue
                cells = [c.strip().strip("`") for c in stripped.strip("|").split("|")]
                if len(cells) == 3 and cells[2] == "Supported":
                    endpoint = "/" + cells[1].lstrip("/")
                    if endpoint in (CHAT_COMPLETIONS_ENDPOINT, RESPONSES_ENDPOINT):
                        endpoint_set.add(endpoint)
            if not endpoint_set:
                return model_id, None, None
            row_warnings = ("deprecated_or_expiring",) if re.search(
                r"^Status: Deprecated\s*$", text, flags=re.MULTILINE
            ) else ()
            record = _OpenAIModelRecord(
                model_id=model_id, display_name=model_id, description=None,
                endpoints=tuple(sorted(endpoint_set)), features=tuple(sorted(flags)),
                context_length=parsed.context_length, max_output_tokens=parsed.max_output_tokens,
                knowledge_cutoff=None, warnings=row_warnings,
            )
            return model_id, record, source.url

    results = await asyncio.gather(*(page(m) for m in candidates[:cap]))
    records = {}
    urls = {}
    for model_id, record, url in results:
        if record is not None:
            records[model_id] = record
            urls[model_id] = url
        else:
            warnings.append(ProviderCatalogWarning(
                code="model_page_unusable", provider=OPENAI_PROVIDER, model_id=model_id,
                message="Official model page failed retrieval, identity, format, or text-contract checks.",
            ))
    return pricing, prices, records, urls


async def _propose_openai(
    *,
    client: httpx.AsyncClient,
    endpoint_scopes: tuple[EndpointScope, ...],
    include_models: Sequence[str],
    exclude_models: Sequence[str],
    currency: str,
    source_methods: tuple[ProposalSourceMethod, ...],
    include_api_models: bool,
    max_web_calls: int,
    max_models: int,
    save_source_snapshots: bool,
    source_dir: Path,
    acknowledge_assisted_proposal_risk: bool,
    allow_zero_prices: bool,
    ordinary_chat_only: bool,
    now: datetime | None,
) -> ProviderCatalogProposalBundle:
    warnings: list[ProviderCatalogWarning] = []
    fetched_sources: list[_FetchedSource] = []

    pricing_source = await _fetch_text_source(
        client=client,
        provider=OPENAI_PROVIDER,
        source_type="docs",
        url=OPENAI_PRICING_DOCS_URL,
        save_snapshot=save_source_snapshots,
        source_dir=source_dir,
        now=now,
    )
    models_source = await _fetch_text_source(
        client=client,
        provider=OPENAI_PROVIDER,
        source_type="docs",
        url=OPENAI_MODELS_DOCS_URL,
        save_snapshot=save_source_snapshots,
        source_dir=source_dir,
        now=now,
    )
    fetched_sources.extend((pricing_source, models_source))

    pricing_records = _parse_openai_pricing_docs(
        text=_text_from_source(pricing_source),
        source_url=pricing_source.url,
        source_retrieved_at=pricing_source.retrieved_at,
    )
    model_records = _parse_openai_models_docs(
        text=_text_from_source(models_source),
        source_url=models_source.url,
    )
    model_source_urls: dict[str, str] = {}
    # The current index is navigation, not an endpoint contract. Its
    # HTML rendering no longer contains the legacy inline model blocks.
    if not model_records and "<html" in (models_source.raw_text or "").lower():
        pricing_source, pricing_records, model_records, model_source_urls = (
            await _openai_markdown_documents(
                client=client, fetched_sources=fetched_sources, warnings=warnings,
                include_models=include_models, exclude_models=exclude_models,
                max_models=max_models, ordinary_chat_only=ordinary_chat_only,
                save_source_snapshots=save_source_snapshots, source_dir=source_dir, now=now,
            )
        )

    api_model_ids: set[str] = set()
    if include_api_models or "api" in source_methods:
        api_source = await _fetch_openai_models_api(
            client=client,
            save_source_snapshots=save_source_snapshots,
            source_dir=source_dir,
            now=now,
        )
        fetched_sources.append(api_source)
        api_model_ids = _parse_openai_models_api(api_source.raw_json or {})

    assisted_pricing_rows: dict[tuple[str, str], dict[str, str]] = {}
    assisted_route_rows: dict[tuple[str, str], dict[str, str]] = {}
    if "assisted" in source_methods:
        if not acknowledge_assisted_proposal_risk:
            raise ValueError("--acknowledge-assisted-proposal-risk is required for source=assisted")
        assisted_pricing_text = await generate_openai_pricing_proposal_text(
            source_url=OPENAI_PRICING_DOCS_URL,
            models_source_url=OPENAI_MODELS_DOCS_URL,
            api_key_env_var=OPENAI_ADMIN_DISCOVERY_API_KEY_ENV_VAR,
            proposal_model=os.getenv("OPENAI_ASSISTED_CATALOG_MODEL", "gpt-5.5"),
            currency=currency,
            endpoint=CHAT_COMPLETIONS_ENDPOINT,
            include_models=include_models,
            exclude_models=exclude_models,
            max_web_calls=max_web_calls,
            http_client=client,
            now=now,
        )
        assisted_route_text = await generate_openai_route_proposal_text(
            source_url=OPENAI_MODELS_DOCS_URL,
            api_key_env_var=OPENAI_ADMIN_DISCOVERY_API_KEY_ENV_VAR,
            proposal_model=os.getenv("OPENAI_ASSISTED_CATALOG_MODEL", "gpt-5.5"),
            include_models=include_models,
            exclude_models=exclude_models,
            implemented_endpoints_only=True,
            http_client=client,
        )
        fetched_sources.extend(
            (
                _pseudo_source_from_assisted(
                    proposal_type="assisted_pricing",
                    source_urls=(OPENAI_PRICING_DOCS_URL, OPENAI_MODELS_DOCS_URL),
                    tsv_text=assisted_pricing_text.tsv_text,
                    now=now,
                ),
                _pseudo_source_from_assisted(
                    proposal_type="assisted_routes",
                    source_urls=(OPENAI_MODELS_DOCS_URL,),
                    tsv_text=assisted_route_text.tsv_text,
                    now=now,
                ),
            )
        )
        assisted_pricing_rows = _parse_assisted_pricing_tsv(assisted_pricing_text.tsv_text)
        assisted_route_rows = _parse_assisted_route_tsv(assisted_route_text.tsv_text)

    all_model_ids = {
        record.model_id
        for record in pricing_records
        if _model_allowed(record.model_id, include_models=include_models, exclude_models=exclude_models)
    } | {
        record.model_id
        for record in model_records.values()
        if _model_allowed(record.model_id, include_models=include_models, exclude_models=exclude_models)
    }
    if include_api_models or "api" in source_methods:
        all_model_ids |= {
            model_id
            for model_id in api_model_ids
            if _model_allowed(model_id, include_models=include_models, exclude_models=exclude_models)
        }
    # Honor the SAME public max_models cap OpenRouter uses: after the
    # include/exclude filtering, take the first ``max_models`` of the
    # sorted eligible ids (deterministic). The cap is the operator's
    # explicit finite choice; the omitted scope is reported honestly in
    # the warnings (count + which ids were dropped), never silently.
    eligible_model_ids = sorted(all_model_ids)
    omitted_model_ids = eligible_model_ids[max_models:]
    eligible_model_ids = eligible_model_ids[:max_models]
    if omitted_model_ids:
        warnings.append(
            ProviderCatalogWarning(
                code="model_cap_applied",
                message=(
                    f"max_models={max_models} kept {len(eligible_model_ids)} "
                    f"eligible model(s) and omitted {len(omitted_model_ids)} "
                    f"more (e.g. {', '.join(omitted_model_ids[:5])}"
                    f"{'...' if len(omitted_model_ids) > 5 else ''})"
                ),
                provider=OPENAI_PROVIDER,
            )
        )
    pricing_by_model = _group_openai_pricing_records(pricing_records)
    model_candidates: list[ProviderCatalogModelCandidate] = []
    pricing_candidates: list[ProviderCatalogPricingCandidate] = []
    route_candidates: list[ProviderCatalogRouteCandidate] = []
    comparison_rows: list[ProviderCatalogModelStatus] = []

    for model_id in eligible_model_ids:
        docs_model = model_records.get(model_id)
        model_source_url = model_source_urls.get(model_id, models_source.url)
        doc_prices = pricing_by_model.get(model_id, ())
        selected_doc_pricing = _select_openai_text_pricing_record(doc_prices)
        row_warnings = _openai_model_comparison_warnings(
            model_id=model_id,
            docs_model=docs_model,
            has_pricing=bool(doc_prices),
            api_model_ids=api_model_ids if (include_api_models or "api" in source_methods) else None,
            ordinary_chat_only=ordinary_chat_only,
        )
        if "chat_completions" in endpoint_scopes and not _is_openai_chat_completions_model_id(model_id):
            row_warnings = tuple(sorted(set(row_warnings + ("unsupported_modality",))))
        if is_search_specific_chat_completion_model(model_id):
            row_warnings = tuple(sorted(set(row_warnings + ("search_specific_model",))))
        if docs_model is not None:
            confidence = "high" if model_id in api_model_ids and api_model_ids else "medium"
            endpoints = docs_model.endpoints or (CHAT_COMPLETIONS_ENDPOINT,)
            model_candidates.append(
                ProviderCatalogModelCandidate(
                    provider=OPENAI_PROVIDER,
                    model_id=model_id,
                    canonical_model_id=model_id,
                    display_name=docs_model.display_name,
                    description=docs_model.description,
                    endpoints=endpoints,
                    input_modalities=_feature_modalities(docs_model.features, kind="input"),
                    output_modalities=_feature_modalities(docs_model.features, kind="output"),
                    context_length=docs_model.context_length,
                    max_output_tokens=docs_model.max_output_tokens,
                    knowledge_cutoff=docs_model.knowledge_cutoff,
                    supports_streaming="streaming" in docs_model.features,
                    supported_parameters=_features_to_parameters(docs_model.features),
                    capabilities=_build_chat_capabilities_from_features(
                        features=docs_model.features,
                        supports_streaming="streaming" in docs_model.features,
                        provider=OPENAI_PROVIDER,
                        supports_cached_input_usage=selected_doc_pricing is not None
                        and selected_doc_pricing.cached_input_price_per_1m is not None,
                    ),
                    confidence=confidence,
                    source_evidence=tuple(
                        value
                        for value in (
                            model_source_url,
                            OPENAI_MODELS_API_URL if model_id in api_model_ids else None,
                        )
                        if value is not None
                    ),
                    warnings=row_warnings,
                )
            )

        route_ready = False
        route_status = "missing"
        if docs_model is not None and "chat_completions" in endpoint_scopes:
            route_status = "report-only"
            if (
                CHAT_COMPLETIONS_ENDPOINT in docs_model.endpoints
                and _is_openai_chat_completions_model_id(model_id)
                and "search_specific_model" not in row_warnings
                and "hosted_tool_only" not in row_warnings
            ):
                route_confidence: Confidence = (
                    "high" if (model_id in api_model_ids and api_model_ids) else "medium"
                )
                route_rows_match = assisted_route_rows.get((model_id, CHAT_COMPLETIONS_ENDPOINT))
                route_row_warnings = list(row_warnings)
                if "assisted" in source_methods and route_rows_match is None:
                    route_row_warnings.append("model_missing_from_assisted")
                route_ready = (
                    "search_specific_model" not in route_row_warnings
                    and "unsupported_modality" not in route_row_warnings
                    and "hosted_tool_only" not in route_row_warnings
                    and "deprecated_or_expiring" not in route_row_warnings
                )
                route_status = "ready" if route_ready else "report-only"
                route_candidates.append(
                    ProviderCatalogRouteCandidate(
                        requested_model=model_id,
                        match_type="exact",
                        endpoint=CHAT_COMPLETIONS_ENDPOINT,
                        provider=OPENAI_PROVIDER,
                        upstream_model=model_id,
                        priority=100,
                        enabled=True,
                        visible_in_models="deprecated_or_expiring" not in route_row_warnings,
                        supports_streaming="streaming" in docs_model.features,
                        capabilities=_build_chat_capabilities_from_features(
                            features=docs_model.features,
                            supports_streaming="streaming" in docs_model.features,
                            provider=OPENAI_PROVIDER,
                            supports_cached_input_usage=selected_doc_pricing is not None
                            and selected_doc_pricing.cached_input_price_per_1m is not None,
                        ),
                        notes=_route_notes(
                            provider=OPENAI_PROVIDER,
                            model_id=model_id,
                            confidence=route_confidence,
                            context_length=docs_model.context_length,
                            max_output_tokens=docs_model.max_output_tokens,
                            source_urls=tuple(
                                value
                                for value in (
                                    model_source_url,
                                    OPENAI_MODELS_API_URL if model_id in api_model_ids else None,
                                )
                                if value is not None
                            ),
                            warnings=tuple(route_row_warnings),
                        ),
                        confidence=route_confidence,
                        ready_for_import=route_ready,
                        warnings=tuple(route_row_warnings),
                    )
                )
            if "responses" in endpoint_scopes and RESPONSES_ENDPOINT in IMPLEMENTED_CLIENT_ENDPOINTS:
                warnings.append(
                    ProviderCatalogWarning(
                        code="future_endpoint",
                        message=(
                            "OpenAI responses route proposals remain report-only in this workflow; "
                            "chat.completions stays the ready import target."
                        ),
                        provider=OPENAI_PROVIDER,
                        model_id=model_id,
                        endpoint=RESPONSES_ENDPOINT,
                        sources=(model_source_url,),
                    )
                )

        pricing_ready = False
        pricing_status = "missing"
        openai_pricing_candidates, pricing_warning_codes = _openai_pricing_candidates(
            model_id=model_id,
            pricing_records=doc_prices,
            currency=currency,
            endpoint_scopes=endpoint_scopes,
            model_record=docs_model,
            assisted_pricing_rows=assisted_pricing_rows,
            sources=(pricing_source.url, model_source_url),
            allow_zero_prices=allow_zero_prices,
        )
        if openai_pricing_candidates:
            pricing_ready = any(candidate.ready_for_import for candidate in openai_pricing_candidates)
            pricing_status = "ready" if pricing_ready else "report-only"
            pricing_candidates.extend(openai_pricing_candidates)
        comparison_rows.append(
            ProviderCatalogModelStatus(
                provider=OPENAI_PROVIDER,
                model_id=model_id,
                pricing_status=pricing_status,
                route_status=route_status,
                sources_seen=_openai_sources_seen(
                    model_id=model_id,
                    docs_model=docs_model,
                    has_pricing=bool(doc_prices),
                    api_model_ids=api_model_ids if (include_api_models or "api" in source_methods) else None,
                    assisted_pricing_rows=assisted_pricing_rows if "assisted" in source_methods else None,
                    assisted_route_rows=assisted_route_rows if "assisted" in source_methods else None,
                ),
                confidence=_confidence_from_openai_sources(
                    model_id=model_id,
                    docs_model=docs_model,
                    api_model_ids=api_model_ids if (include_api_models or "api" in source_methods) else None,
                    has_assisted="assisted" in source_methods,
                ),
                warnings=tuple(sorted(set(tuple(row_warnings) + tuple(pricing_warning_codes)))),
                ready_for_route_import=route_ready,
                ready_for_pricing_import=pricing_ready,
            )
        )
        for warning_code in sorted(set(tuple(row_warnings) + tuple(pricing_warning_codes))):
            warnings.append(
                ProviderCatalogWarning(
                    code=warning_code,
                    message=_warning_message(warning_code, model_id),
                    provider=OPENAI_PROVIDER,
                    model_id=model_id,
                    endpoint=CHAT_COMPLETIONS_ENDPOINT,
                    sources=tuple(
                        value
                        for value in (
                            pricing_source.url if doc_prices else None,
                            model_source_url if docs_model else None,
                            OPENAI_MODELS_API_URL if model_id in api_model_ids else None,
                        )
                        if value is not None
                    ),
                )
            )

    return ProviderCatalogProposalBundle(
        providers=(OPENAI_PROVIDER,),
        sources=tuple(_source_to_manifest_entry(item) for item in fetched_sources),
        models=tuple(model_candidates),
        pricing_candidates=tuple(pricing_candidates),
        route_candidates=tuple(route_candidates),
        comparison_rows=tuple(comparison_rows),
        warnings=tuple(_dedupe_warning_objects(warnings)),
    )


def _normalize_provider_scope(provider_scope: ProviderName | Literal["all"]) -> tuple[ProviderName, ...]:
    if provider_scope == "all":
        return (OPENAI_PROVIDER, OPENROUTER_PROVIDER)
    if provider_scope not in {OPENAI_PROVIDER, OPENROUTER_PROVIDER}:
        raise ValueError("provider scope must be openai, openrouter, or all")
    return (provider_scope,)


def _normalize_endpoint_scopes(endpoint_scopes: Sequence[EndpointScope]) -> tuple[EndpointScope, ...]:
    scopes = tuple(dict.fromkeys(scope.strip() for scope in endpoint_scopes if scope.strip()))
    if not scopes:
        return DEFAULT_ENDPOINT_SCOPES
    for scope in scopes:
        if scope not in SUPPORTED_ENDPOINT_SCOPES:
            allowed = ", ".join(sorted(SUPPORTED_ENDPOINT_SCOPES))
            raise ValueError(f"endpoint scope must be one of: {allowed}")
    return scopes  # type: ignore[return-value]


def _normalize_source_methods(
    *,
    provider_scope: ProviderName | Literal["all"],
    source_methods: Sequence[ProposalSourceMethod] | None,
    include_api_models: bool,
) -> tuple[ProposalSourceMethod, ...]:
    if source_methods:
        normalized = tuple(dict.fromkeys(value.strip() for value in source_methods if value.strip()))
    else:
        normalized = ("docs", "api") if provider_scope == OPENROUTER_PROVIDER else ("docs",)
    if include_api_models and "api" not in normalized:
        normalized = normalized + ("api",)
    for value in normalized:
        if value not in SUPPORTED_SOURCE_METHODS:
            allowed = ", ".join(sorted(SUPPORTED_SOURCE_METHODS))
            raise ValueError(f"source method must be one of: {allowed}")
    return normalized  # type: ignore[return-value]


def _normalize_currency(currency: str) -> str:
    normalized = currency.strip().upper()
    if not re.fullmatch(r"[A-Z]{3}", normalized):
        raise ValueError("currency must be a 3-letter ISO code")
    return normalized


def _normalize_openrouter_package_names(
    *,
    provider_scope: ProviderName | Literal["all"],
    package_names: Sequence[str],
    all_packages: bool,
) -> tuple[str, ...]:
    requested = [value.strip().lower() for value in package_names if value.strip()]
    if all_packages or "all" in requested:
        requested = list(OPENROUTER_PACKAGE_ORDER)
    if not requested:
        return ()
    if provider_scope != OPENROUTER_PROVIDER:
        raise ValueError("provider catalog package presets are implemented only for openrouter")
    normalized: list[str] = []
    for value in requested:
        canonical = OPENROUTER_PACKAGE_ALIASES.get(value, value)
        if canonical not in OPENROUTER_PACKAGE_ORDER:
            allowed = ", ".join(OPENROUTER_PACKAGE_ORDER)
            raise ValueError(f"unknown package name {value!r}; allowed values: {allowed}")
        if canonical not in normalized:
            normalized.append(canonical)
    return tuple(normalized)


def _require_positive(value: int, *, label: str) -> None:
    if value <= 0:
        raise ValueError(f"{label} must be positive")


def _require_non_negative(value: int, *, label: str) -> None:
    if value < 0:
        raise ValueError(f"{label} must be non-negative")


async def _fetch_text_source(
    *,
    client: httpx.AsyncClient,
    provider: ProviderName,
    source_type: str,
    url: str,
    save_snapshot: bool,
    source_dir: Path,
    now: datetime | None,
) -> _FetchedSource:
    _validate_official_source_url(url, provider=provider)
    response = await client.get(url)
    response.raise_for_status()
    content = response.text
    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
    snapshot_path = None
    if save_snapshot:
        snapshot_path = _save_source_snapshot(
            source_dir=source_dir,
            provider=provider,
            source_type=source_type,
            extension="txt",
            content=content,
        )
    return _FetchedSource(
        provider=provider,
        source_type=source_type,
        url=str(response.url),
        retrieved_at=_timestamp(now),
        content_hash=content_hash,
        content_type=response.headers.get("content-type"),
        raw_text=content,
        snapshot_path=snapshot_path,
    )


async def _fetch_json_source(
    *,
    client: httpx.AsyncClient,
    provider: ProviderName,
    source_type: str,
    url: str,
    save_snapshot: bool,
    source_dir: Path,
    now: datetime | None,
) -> _FetchedSource:
    _validate_official_source_url(url, provider=provider)
    response = await client.get(url)
    response.raise_for_status()
    payload = response.json()
    serialized = json.dumps(payload, sort_keys=True)
    snapshot_path = None
    if save_snapshot:
        snapshot_path = _save_source_snapshot(
            source_dir=source_dir,
            provider=provider,
            source_type=source_type,
            extension="json",
            content=json.dumps(_sanitize_snapshot_payload(payload), indent=2, sort_keys=True),
        )
    return _FetchedSource(
        provider=provider,
        source_type=source_type,
        url=str(response.url),
        retrieved_at=_timestamp(now),
        content_hash=hashlib.sha256(serialized.encode("utf-8")).hexdigest(),
        content_type=response.headers.get("content-type"),
        raw_json=payload if isinstance(payload, Mapping) else {"data": payload},
        snapshot_path=snapshot_path,
    )


async def _fetch_openrouter_detail_sources(
    *,
    client: httpx.AsyncClient,
    models_payload: Mapping[str, object],
    fetch_details_limit: int,
    save_source_snapshots: bool,
    source_dir: Path,
    now: datetime | None,
) -> tuple[_FetchedSource, ...]:
    rows = _openrouter_models_from_payload(models_payload)
    results: list[_FetchedSource] = []
    for row in rows[:fetch_details_limit]:
        links = row.get("links")
        if not isinstance(links, Mapping):
            continue
        details = links.get("details")
        if not isinstance(details, str) or not details.strip():
            continue
        if details.startswith("/"):
            url = f"https://openrouter.ai{details}"
        else:
            url = details
        try:
            results.append(
                await _fetch_json_source(
                    client=client,
                    provider=OPENROUTER_PROVIDER,
                    source_type="details",
                    url=url,
                    save_snapshot=save_source_snapshots,
                    source_dir=source_dir,
                    now=now,
                )
            )
        except Exception:
            continue
    return tuple(results)


async def _fetch_openai_models_api(
    *,
    client: httpx.AsyncClient,
    save_source_snapshots: bool,
    source_dir: Path,
    now: datetime | None,
) -> _FetchedSource:
    api_key = os.getenv(OPENAI_ADMIN_DISCOVERY_API_KEY_ENV_VAR)
    if not api_key or not api_key.strip():
        raise ValueError(
            f"{OPENAI_ADMIN_DISCOVERY_API_KEY_ENV_VAR} is required for OpenAI API model listing"
        )
    response = await client.get(
        OPENAI_MODELS_API_URL,
        headers={"Authorization": f"Bearer {api_key.strip()}"},
    )
    response.raise_for_status()
    payload = response.json()
    serialized = json.dumps(payload, sort_keys=True)
    snapshot_path = None
    if save_source_snapshots:
        snapshot_path = _save_source_snapshot(
            source_dir=source_dir,
            provider=OPENAI_PROVIDER,
            source_type="api",
            extension="json",
            content=json.dumps(_sanitize_snapshot_payload(payload), indent=2, sort_keys=True),
        )
    return _FetchedSource(
        provider=OPENAI_PROVIDER,
        source_type="api",
        url=str(response.url),
        retrieved_at=_timestamp(now),
        content_hash=hashlib.sha256(serialized.encode("utf-8")).hexdigest(),
        content_type=response.headers.get("content-type"),
        raw_json=payload if isinstance(payload, Mapping) else {"data": payload},
        snapshot_path=snapshot_path,
    )


def _pseudo_source_from_assisted(
    *,
    proposal_type: str,
    source_urls: Sequence[str],
    tsv_text: str,
    now: datetime | None,
) -> _FetchedSource:
    serialized = redact_text(tsv_text)
    return _FetchedSource(
        provider=OPENAI_PROVIDER,
        source_type=proposal_type,
        url=",".join(source_urls),
        retrieved_at=_timestamp(now),
        content_hash=hashlib.sha256(serialized.encode("utf-8")).hexdigest(),
        content_type="text/tab-separated-values",
        raw_text=serialized,
    )


def _validate_official_source_url(url: str, *, provider: ProviderName) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"https"}:
        raise ValueError("source URL must use https")
    host = (parsed.hostname or "").lower()
    if not host:
        raise ValueError("source URL must include a hostname")
    allowed = OFFICIAL_SOURCE_DOMAINS[provider]
    if not any(host == domain or host.endswith(f".{domain}") for domain in allowed):
        raise ValueError("source URL must use an official provider domain")


def _save_source_snapshot(
    *,
    source_dir: Path,
    provider: ProviderName,
    source_type: str,
    extension: str,
    content: str,
) -> str:
    filename = f"{provider}-{source_type}.{extension}"
    path = source_dir / filename
    _emit(path, content.encode("utf-8"))
    return str(path)


def _sanitize_snapshot_payload(payload: object) -> object:
    if isinstance(payload, Mapping):
        return redact_mapping(payload)
    if isinstance(payload, list):
        return [_sanitize_snapshot_payload(item) for item in payload]
    if isinstance(payload, str):
        return redact_text(payload)
    return payload


def _text_from_source(source: _FetchedSource) -> str:
    text = source.raw_text or ""
    if "<html" in text.lower():
        return _HTMLTableExtractor().extract(text)
    return text


class _HTMLTableExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []
        self._cell_open = False

    def handle_starttag(self, tag: str, attrs) -> None:  # noqa: ANN001
        if tag in {"tr"}:
            self._parts.append("\n")
        elif tag in {"td", "th"}:
            if self._cell_open:
                self._parts.append("\t")
            self._cell_open = True
        elif tag in {"br", "p", "div", "section", "article", "li", "h1", "h2", "h3", "h4", "h5", "h6"}:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"}:
            self._parts.append("\t")
        elif tag in {"tr", "table"}:
            self._parts.append("\n")
            self._cell_open = False
        elif tag in {"p", "div", "section", "article", "li", "h1", "h2", "h3", "h4", "h5", "h6"}:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        cleaned = _WHITESPACE_PATTERN.sub(" ", data)
        if cleaned.strip():
            self._parts.append(cleaned.strip())

    def extract(self, text: str) -> str:
        self.feed(text)
        extracted = "".join(self._parts)
        lines = [line.rstrip() for line in extracted.splitlines()]
        return "\n".join(line for line in lines if line.strip())


def _confirm_openrouter_pricing_unit(text: str) -> bool:
    normalized = text.lower()
    return "all pricing values are in usd per token/request/unit" in normalized


def _openrouter_models_from_payload(payload: Mapping[str, object]) -> list[Mapping[str, object]]:
    data = payload.get("data")
    if not isinstance(data, list):
        raise ValueError("OpenRouter models API payload must contain data[]")
    return [row for row in data if isinstance(row, Mapping)]


def _openrouter_model_warnings(
    *,
    model_id: str,
    supported_parameters: Sequence[str],
    input_modalities: Sequence[str],
    output_modalities: Sequence[str],
    expiration_date: str | None,
    ordinary_chat_only: bool,
) -> tuple[str, ...]:
    warnings: set[str] = set()
    if is_search_specific_chat_completion_model(model_id) or "search" in model_id.lower():
        warnings.add("search_specific_model")
    if expiration_date:
        warnings.add("deprecated_or_expiring")
    if any(parameter in UNSUPPORTED_HOSTED_PARAMETERS for parameter in supported_parameters):
        warnings.add("hosted_tool_only")
    if "text" not in output_modalities:
        warnings.add("unsupported_modality")
    if "file" in supported_parameters or "file" in input_modalities or "file" in output_modalities:
        warnings.add("ambiguous_capability")
    if (
        "audio" in supported_parameters
        or "audio" in input_modalities
        or "audio" in output_modalities
        or "audio" in model_id.lower()
    ):
        warnings.add("ambiguous_capability")
    if ordinary_chat_only and _ordinary_chat_candidate_requires_review(
        model_id=model_id,
        input_modalities=input_modalities,
        output_modalities=output_modalities,
    ):
        warnings.add("unsupported_modality")
    return tuple(sorted(warnings))


def _openrouter_route_ready(
    *,
    model_id: str,
    output_modalities: Sequence[str],
    warnings: Sequence[str],
) -> bool:
    return (
        "text" in output_modalities
        and "search_specific_model" not in warnings
        and "unsupported_modality" not in warnings
        and not is_search_specific_chat_completion_model(model_id)
    )


def _openrouter_pricing_candidate(
    *,
    model_id: str,
    pricing: Mapping[str, object],
    currency: str,
    source_url: str,
    source_retrieved_at: str,
    unit_confirmed: bool,
    confidence: Confidence,
    model_warnings: Sequence[str],
    allow_zero_prices: bool,
) -> tuple[ProviderCatalogPricingCandidate | None, tuple[str, ...]]:
    warning_codes: set[str] = set(model_warnings)
    if not unit_confirmed:
        warning_codes.add("unit_unconfirmed")
        return None, tuple(sorted(warning_codes))
    try:
        input_price = _convert_openrouter_price(pricing.get("prompt"), allow_zero=True)
        cached_input = _convert_openrouter_price(pricing.get("input_cache_read"), allow_zero=True)
        output_price = _convert_openrouter_price(pricing.get("completion"), allow_zero=True)
        reasoning_price = _convert_openrouter_price(pricing.get("internal_reasoning"), allow_zero=True)
        request_price = _decimal_text(pricing.get("request"))
    except ValueError as exc:
        code = "negative_or_invalid_price" if "negative" in str(exc) or "decimal" in str(exc) else "missing_pricing"
        warning_codes.add(code)
        return None, tuple(sorted(warning_codes))
    if input_price is None and output_price is None:
        warning_codes.add("missing_pricing")
    zero_price_detected = input_price == "0" or output_price == "0"
    if zero_price_detected:
        warning_codes.add("zero_price_requires_review")
    ready = not {
        "missing_pricing",
        "unit_unconfirmed",
        "search_specific_model",
        "unsupported_modality",
        "hosted_tool_only",
    } & warning_codes
    if zero_price_detected and not allow_zero_prices:
        ready = False
    pricing_metadata = {
        "source_type": "openrouter_models_api",
        "operator_review_required": True,
        "zero_price_requires_review": zero_price_detected,
        "pricing_unit": "usd_per_token",
        "conversion_factor": "1000000",
        "confidence": confidence,
        "warnings": sorted(warning_codes),
    }
    return (
        ProviderCatalogPricingCandidate(
            provider=OPENROUTER_PROVIDER,
            model_id=model_id,
            endpoint=CHAT_COMPLETIONS_ENDPOINT,
            currency=currency,
            input_price_per_1m=input_price,
            cached_input_price_per_1m=cached_input,
            output_price_per_1m=output_price,
            reasoning_price_per_1m=reasoning_price,
            request_price=request_price,
            source_url=source_url,
            source_retrieved_at=source_retrieved_at,
            pricing_metadata=pricing_metadata,
            notes=(
                "OpenRouter public models API proposal; pricing remains a reviewed local "
                "accounting assumption until imported."
            ),
            confidence=confidence,
            ready_for_import=ready,
            warnings=tuple(sorted(warning_codes)),
        ),
        tuple(sorted(warning_codes)),
    )


def _convert_openrouter_price(value: object, *, allow_zero: bool) -> str | None:
    decimal_value = _decimal_text(value)
    if decimal_value is None:
        return None
    parsed = Decimal(decimal_value)
    if parsed < 0:
        raise ValueError("price must be non-negative")
    if parsed == 0 and not allow_zero:
        return "0"
    converted = parsed * Decimal("1000000")
    return _decimal_to_string(converted)


def _detail_lookup(payload: Mapping[str, object], key: str) -> object | None:
    if key in payload:
        return payload.get(key)
    data = payload.get("data")
    if isinstance(data, Mapping):
        return data.get(key)
    return None


def _model_id_from_detail_url(url: str) -> str | None:
    parsed = urlparse(url)
    parts = [part for part in parsed.path.split("/") if part]
    if "models" not in parts or "endpoints" not in parts:
        return None
    try:
        model_index = parts.index("models") + 1
        endpoint_index = parts.index("endpoints")
    except ValueError:
        return None
    if model_index >= endpoint_index:
        return None
    model_id = "/".join(parts[model_index:endpoint_index])
    return model_id or None


def _parse_openai_pricing_docs(
    *,
    text: str,
    source_url: str,
    source_retrieved_at: str,
) -> tuple[_OpenAIPricingRecord, ...]:
    standard = re.search(
        r"^### Standard pricing data[ \t]*$\n(.*?)(?=^### (?:Batch|Flex|Fast) pricing data|\Z)",
        text, flags=re.MULTILINE | re.DOTALL | re.IGNORECASE,
    )
    if standard is not None:
        text = standard.group(1)
    tables = _extract_tabular_blocks(text)
    records: list[_OpenAIPricingRecord] = []
    for table in tables:
        header = [cell.strip().lower() for cell in table[0]]
        output_index = next(
            (idx for idx, value in enumerate(header) if value.startswith("output")),
            None,
        )
        if "model" not in header or "input" not in header or output_index is None:
            continue
        model_index = header.index("model")
        modality_index = header.index("modality") if "modality" in header else None
        cached_index = header.index("cached input") if "cached input" in header else None
        input_index = header.index("input")
        category = None
        for row in table[1:]:
            if len(row) <= model_index:
                continue
            model_id = _safe_openai_model_id(row[model_index])
            if model_id is None:
                first = row[0].lower() if row else ""
                if first in {"category", "standard", "batch", "priority"}:
                    category = row[0]
                continue
            modality = row[modality_index] if modality_index is not None and modality_index < len(row) else None
            input_price = _doc_price_cell(row[input_index] if input_index < len(row) else None)
            cached_price = _doc_price_cell(row[cached_index] if cached_index is not None and cached_index < len(row) else None)
            output_price = _doc_price_cell(row[output_index] if output_index is not None and output_index < len(row) else None)
            warnings: list[str] = []
            if modality and modality.lower() != "text":
                warnings.append("unsupported_modality")
            if input_price is None or output_price is None:
                warnings.append("missing_pricing")
            records.append(
                _OpenAIPricingRecord(
                    model_id=model_id,
                    input_price_per_1m=input_price,
                    cached_input_price_per_1m=cached_price,
                    output_price_per_1m=output_price,
                    reasoning_price_per_1m=None,
                    request_price=None,
                    category=category,
                    modality=modality,
                    source_url=source_url,
                    source_retrieved_at=source_retrieved_at,
                    warnings=tuple(warnings),
                )
            )
    return tuple(records)


def _parse_openai_models_docs(*, text: str, source_url: str) -> dict[str, _OpenAIModelRecord]:
    blocks = _split_model_blocks(text)
    records: dict[str, _OpenAIModelRecord] = {}
    for block in blocks:
        model_id = _safe_openai_model_id(block.get("model_id"))
        if model_id is None:
            continue
        endpoints = tuple(
            endpoint
            for endpoint in (
                _normalize_doc_endpoint(value)
                for value in _csvish_values(block.get("endpoints", ""))
            )
            if endpoint is not None
        )
        features = tuple(sorted(set(_csvish_values(block.get("features", "")))))
        if not _openai_model_block_is_trusted(block):
            continue
        warnings: list[str] = []
        if "web_search" in features or "search" in features or is_search_specific_chat_completion_model(model_id):
            warnings.append("search_specific_model")
        if "hosted_tools" in features:
            warnings.append("hosted_tool_only")
        records[model_id] = _OpenAIModelRecord(
            model_id=model_id,
            display_name=_safe_text(block.get("display_name")) or model_id,
            description=_safe_text(block.get("description")),
            endpoints=endpoints or (CHAT_COMPLETIONS_ENDPOINT,),
            features=features,
            context_length=_safe_int(block.get("context_length")),
            max_output_tokens=_safe_int(block.get("max_output_tokens")),
            knowledge_cutoff=_safe_text(block.get("knowledge_cutoff")),
            warnings=tuple(warnings),
        )
    return records


def _parse_openai_models_api(payload: Mapping[str, object]) -> set[str]:
    data = payload.get("data")
    if not isinstance(data, list):
        raise ValueError("OpenAI /v1/models payload must include data[]")
    result: set[str] = set()
    for row in data:
        if not isinstance(row, Mapping):
            continue
        model_id = _safe_openai_model_id(row.get("id"))
        if model_id:
            result.add(model_id)
    return result


def _group_openai_pricing_records(
    records: Sequence[_OpenAIPricingRecord],
) -> dict[str, tuple[_OpenAIPricingRecord, ...]]:
    grouped: dict[str, list[_OpenAIPricingRecord]] = defaultdict(list)
    for record in records:
        grouped[record.model_id].append(record)
    return {key: tuple(value) for key, value in grouped.items()}


def _openai_model_comparison_warnings(
    *,
    model_id: str,
    docs_model: _OpenAIModelRecord | None,
    has_pricing: bool,
    api_model_ids: set[str] | None,
    ordinary_chat_only: bool,
) -> tuple[str, ...]:
    warnings: set[str] = set()
    if docs_model is None:
        warnings.add("model_missing_from_docs")
    if not has_pricing:
        warnings.add("missing_pricing")
    if api_model_ids is not None and model_id not in api_model_ids:
        warnings.add("model_missing_from_api")
    if docs_model is not None:
        warnings.update(docs_model.warnings)
        if ordinary_chat_only and _ordinary_chat_candidate_requires_review(
            model_id=model_id,
            input_modalities=_feature_modalities(docs_model.features, kind="input"),
            output_modalities=_feature_modalities(docs_model.features, kind="output"),
        ):
            warnings.add("unsupported_modality")
    return tuple(sorted(warnings))


def _ordinary_chat_candidate_requires_review(
    *,
    model_id: str,
    input_modalities: Sequence[str],
    output_modalities: Sequence[str],
) -> bool:
    lowered_model = model_id.lower()
    blocked_tokens = (
        "image",
        "audio",
        "speech",
        "tts",
        "whisper",
        "realtime",
        "video",
        "lyria",
        "music",
        "vl-",
        "-vl",
    )
    if any(token in lowered_model for token in blocked_tokens):
        return True
    input_set = {value.lower() for value in input_modalities}
    output_set = {value.lower() for value in output_modalities}
    if "text" not in input_set or "text" not in output_set:
        return True
    if any(value != "text" for value in input_set | output_set):
        return True
    return False


def _openai_pricing_candidates(
    *,
    model_id: str,
    pricing_records: Sequence[_OpenAIPricingRecord],
    currency: str,
    endpoint_scopes: Sequence[EndpointScope],
    model_record: _OpenAIModelRecord | None,
    assisted_pricing_rows: Mapping[tuple[str, str], dict[str, str]],
    sources: Sequence[str],
    allow_zero_prices: bool,
) -> tuple[list[ProviderCatalogPricingCandidate], list[str]]:
    warning_codes: set[str] = set()
    candidates: list[ProviderCatalogPricingCandidate] = []
    if not pricing_records:
        warning_codes.add("missing_pricing")
        return candidates, sorted(warning_codes)
    selected = _select_openai_text_pricing_record(pricing_records)
    if selected is None:
        warning_codes.add("missing_pricing")
        return candidates, sorted(warning_codes)
    warning_codes.update(selected.warnings)
    if model_record is None:
        warning_codes.add("model_missing_from_docs")
    elif model_record.warnings:
        warning_codes.update(model_record.warnings)
    if is_search_specific_chat_completion_model(model_id):
        warning_codes.add("search_specific_model")
    if not _is_openai_chat_completions_model_id(model_id):
        warning_codes.add("unsupported_modality")
    for endpoint_scope in endpoint_scopes:
        if endpoint_scope == "responses":
            warning_codes.add("future_endpoint")
            continue
        endpoint = CHAT_COMPLETIONS_ENDPOINT
        assisted = assisted_pricing_rows.get((model_id, endpoint))
        if assisted is not None and _pricing_record_disagrees(selected, assisted):
            warning_codes.add("pricing_disagreement")
        if assisted is None and assisted_pricing_rows:
            warning_codes.add("model_missing_from_assisted")
        zero_price_detected = (
            selected.input_price_per_1m == "0"
            or selected.output_price_per_1m == "0"
        )
        if zero_price_detected:
            warning_codes.add("zero_price_requires_review")
        ready = not {
            "missing_pricing",
            "model_missing_from_docs",
            "pricing_disagreement",
            "search_specific_model",
            "unsupported_modality",
            "unsupported_endpoint",
            "hosted_tool_only",
            "deprecated_or_expiring",
        } & warning_codes
        if zero_price_detected and not allow_zero_prices:
            ready = False
        confidence: Confidence = "high" if assisted is not None and "pricing_disagreement" not in warning_codes else "medium"
        metadata = {
            "source_type": "openai_pricing_docs",
            "operator_review_required": True,
            "zero_price_requires_review": zero_price_detected,
            "source_evidence": list(sources),
            "confidence": confidence,
            "warnings": sorted(warning_codes),
        }
        candidates.append(
            ProviderCatalogPricingCandidate(
                provider=OPENAI_PROVIDER,
                model_id=model_id,
                endpoint=endpoint,
                currency=currency,
                input_price_per_1m=selected.input_price_per_1m,
                cached_input_price_per_1m=selected.cached_input_price_per_1m,
                output_price_per_1m=selected.output_price_per_1m,
                reasoning_price_per_1m=selected.reasoning_price_per_1m,
                request_price=selected.request_price,
                source_url=selected.source_url,
                source_retrieved_at=selected.source_retrieved_at,
                pricing_metadata=metadata,
                notes=(
                    "Official OpenAI pricing docs proposal; review before import. "
                    "Imported rows become local accounting assumptions."
                ),
                confidence=confidence,
                ready_for_import=ready,
                warnings=tuple(sorted(warning_codes)),
            )
        )
    return candidates, sorted(warning_codes)


def _select_openai_text_pricing_record(
    records: Sequence[_OpenAIPricingRecord],
) -> _OpenAIPricingRecord | None:
    for record in records:
        modality = (record.modality or "").lower()
        if not modality or modality == "text":
            return record
    return records[0] if records else None


def _pricing_record_disagrees(
    record: _OpenAIPricingRecord,
    assisted: Mapping[str, str],
) -> bool:
    expected = {
        "input_price_per_1m": record.input_price_per_1m or "",
        "cached_input_price_per_1m": record.cached_input_price_per_1m or "",
        "output_price_per_1m": record.output_price_per_1m or "",
    }
    return any((assisted.get(key) or "") != value for key, value in expected.items())


def _parse_assisted_pricing_tsv(text: str) -> dict[tuple[str, str], dict[str, str]]:
    rows = list(csv.DictReader(StringIO(text), delimiter="\t"))
    result: dict[tuple[str, str], dict[str, str]] = {}
    for row in rows:
        model = _safe_model_id(row.get("model"))
        endpoint = normalize_endpoint(row.get("endpoint", ""))
        if model is None:
            continue
        result[(model, endpoint)] = {str(key): str(value or "") for key, value in row.items()}
    return result


def _parse_assisted_route_tsv(text: str) -> dict[tuple[str, str], dict[str, str]]:
    rows = list(csv.DictReader(StringIO(text), delimiter="\t"))
    result: dict[tuple[str, str], dict[str, str]] = {}
    for row in rows:
        model = _safe_model_id(row.get("requested_model"))
        endpoint = normalize_endpoint(row.get("endpoint", ""))
        if model is None:
            continue
        result[(model, endpoint)] = {str(key): str(value or "") for key, value in row.items()}
    return result


def _build_chat_capabilities(
    *,
    supported_parameters: Sequence[str],
    input_modalities: Sequence[str],
    output_modalities: Sequence[str],
    supports_streaming: bool,
    provider: ProviderName,
    supports_cached_input_usage: bool,
) -> dict[str, object]:
    parameter_set = {parameter.lower() for parameter in supported_parameters}
    input_modality_set = {modality.lower() for modality in input_modalities}
    output_modality_set = {modality.lower() for modality in output_modalities}
    image_inputs = "image" in input_modality_set
    file_inputs = "file" in input_modality_set and "file" in parameter_set
    audio_inputs = "audio" in input_modality_set and "audio" in parameter_set
    audio_outputs = "audio" in output_modality_set and "audio" in parameter_set
    chat = {
        CHAT_CAPABILITY_TEXT: "text" in output_modality_set or not output_modality_set,
        CHAT_CAPABILITY_STREAMING: supports_streaming,
        CHAT_CAPABILITY_FUNCTION_TOOLS: "tools" in parameter_set,
        CHAT_CAPABILITY_CUSTOM_TOOLS: False,
        CHAT_CAPABILITY_LEGACY_FUNCTIONS: "tools" in parameter_set,
        CHAT_CAPABILITY_STRUCTURED_OUTPUTS: "structured_outputs" in parameter_set,
        CHAT_CAPABILITY_JSON_MODE: (
            "response_format" in parameter_set or "structured_outputs" in parameter_set
        ),
        CHAT_CAPABILITY_LOGPROBS: "logprobs" in parameter_set,
        CHAT_CAPABILITY_REASONING_USAGE: (
            "reasoning" in parameter_set or "include_reasoning" in parameter_set
        ),
        CHAT_CAPABILITY_CACHED_INPUT_USAGE: supports_cached_input_usage,
        CHAT_CAPABILITY_HOSTED_WEB_SEARCH: False,
        CHAT_CAPABILITY_HOSTED_FILE_SEARCH: False,
        CHAT_CAPABILITY_HOSTED_CODE_INTERPRETER: False,
        CHAT_CAPABILITY_HOSTED_COMPUTER_USE: False,
        CHAT_CAPABILITY_HOSTED_IMAGE_GENERATION: False,
        CHAT_CAPABILITY_HOSTED_TOOL_SEARCH: False,
        CHAT_CAPABILITY_EXTERNAL_MCP_CONNECTORS: False,
        CHAT_CAPABILITY_IMAGE_INPUTS: image_inputs,
        CHAT_CAPABILITY_MULTIMODAL: any(
            modality != "text" for modality in input_modality_set | output_modality_set
        ),
        CHAT_CAPABILITY_AUDIO: audio_inputs or audio_outputs,
        CHAT_CAPABILITY_FILE_INPUTS: file_inputs,
        CHAT_CAPABILITY_AUDIO_INPUTS: audio_inputs,
        CHAT_CAPABILITY_AUDIO_OUTPUTS: audio_outputs,
        CHAT_CAPABILITY_SERVICE_TIER_NON_DEFAULT: False,
        CHAT_CAPABILITY_MULTIPLE_CHOICES: False,
    }
    return {
        CHAT_COMPLETIONS_CAPABILITIES_KEY: chat,
        "provider_catalog_source": provider,
    }


def _build_chat_capabilities_from_features(
    *,
    features: Sequence[str],
    supports_streaming: bool,
    provider: ProviderName,
    supports_cached_input_usage: bool,
) -> dict[str, object]:
    feature_set = {feature.lower() for feature in features}
    return _build_chat_capabilities(
        supported_parameters=_features_to_parameters(feature_set),
        input_modalities=_feature_modalities(feature_set, kind="input"),
        output_modalities=_feature_modalities(feature_set, kind="output"),
        supports_streaming=supports_streaming,
        provider=provider,
        supports_cached_input_usage=supports_cached_input_usage,
    )


def _features_to_parameters(features: Iterable[str]) -> tuple[str, ...]:
    feature_set = {feature.lower() for feature in features}
    parameters: set[str] = set()
    if "function calling" in feature_set or "tools" in feature_set:
        parameters.add("tools")
    if "structured outputs" in feature_set:
        parameters.add("structured_outputs")
        parameters.add("response_format")
    if "json mode" in feature_set:
        parameters.add("response_format")
    if "logprobs" in feature_set:
        parameters.add("logprobs")
    if "reasoning" in feature_set:
        parameters.add("reasoning")
    return tuple(sorted(parameters))


def _feature_modalities(features: Iterable[str], *, kind: Literal["input", "output"]) -> tuple[str, ...]:
    feature_set = {feature.lower() for feature in features}
    values = {"text"}
    if kind == "input":
        if "image input" in feature_set or "vision" in feature_set:
            values.add("image")
        if "file input" in feature_set:
            values.add("file")
        if "audio input" in feature_set:
            values.add("audio")
    else:
        if "audio output" in feature_set:
            values.add("audio")
    return tuple(sorted(values))


def _extract_tabular_blocks(text: str) -> list[list[list[str]]]:
    blocks: list[list[list[str]]] = []
    current: list[list[str]] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            if current:
                blocks.append(current)
                current = []
            continue
        if "\t" in line:
            cells = [cell.strip() for cell in line.split("\t") if cell.strip()]
            if cells:
                current.append(cells)
            continue
        if "|" in line and line.count("|") >= 2:
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            if any(cells):
                current.append(cells)
            continue
        if current:
            blocks.append(current)
            current = []
    if current:
        blocks.append(current)
    return blocks


def _split_model_blocks(text: str) -> list[dict[str, str]]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    blocks: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    for line in lines:
        candidate_model = _heading_model_id(line)
        if candidate_model:
            if current is not None:
                blocks.append(current)
            current = {"model_id": candidate_model, "display_name": candidate_model}
            continue
        if current is None:
            continue
        label_match = _LABEL_PATTERN.match(line)
        if label_match:
            label = label_match.group("label").strip().lower().replace(" ", "_")
            current[label] = label_match.group("value").strip()
        elif "description" not in current and len(line.split()) > 3:
            current["description"] = line
    if current is not None:
        blocks.append(current)
    return blocks


def _heading_model_id(line: str) -> str | None:
    stripped = line.lstrip("# ").strip()
    return _safe_openai_model_id(stripped)


def _openai_model_block_is_trusted(block: Mapping[str, str]) -> bool:
    trusted_fields = {
        "endpoints",
        "features",
        "context_length",
        "max_output_tokens",
        "knowledge_cutoff",
    }
    return any(block.get(field) for field in trusted_fields)


def _csvish_values(value: str) -> tuple[str, ...]:
    if not value:
        return ()
    result = []
    for piece in re.split(r",|\u2022|;|\|", value):
        normalized = piece.strip().lower()
        if normalized:
            result.append(normalized)
    return tuple(result)


def _normalize_doc_endpoint(value: str) -> str | None:
    normalized = value.strip().lower()
    mapping = {
        "/v1/chat/completions": CHAT_COMPLETIONS_ENDPOINT,
        "chat.completions": CHAT_COMPLETIONS_ENDPOINT,
        "chat completions": CHAT_COMPLETIONS_ENDPOINT,
        "/v1/responses": RESPONSES_ENDPOINT,
        "responses": RESPONSES_ENDPOINT,
    }
    return mapping.get(normalized)


def _doc_price_cell(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.replace(",", "").strip()
    if not normalized or normalized == "-":
        return None
    if "/ minute" in normalized.lower():
        return None
    match = _PRICE_CELL_PATTERN.match(normalized)
    if match is None:
        return None
    return _decimal_to_string(Decimal(match.group("amount")))


def _string_tuple(value: object) -> tuple[str, ...]:
    if isinstance(value, list):
        return tuple(str(item).strip().lower() for item in value if str(item).strip())
    return ()


def _decimal_text(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return _decimal_to_string(value)
    if isinstance(value, str):
        normalized = value.strip()
        if not normalized:
            return None
        try:
            return _decimal_to_string(Decimal(normalized))
        except InvalidOperation as exc:
            raise ValueError("value must be a decimal string") from exc
    raise ValueError("value must be a decimal string")


def _decimal_to_string(value: Decimal) -> str:
    normalized = value.normalize()
    rendered = format(normalized, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".") or "0"
    return rendered


def _safe_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    if not normalized:
        return None
    redacted = redact_text(normalized)
    return redacted if redacted == normalized else None


def _safe_model_id(value: object) -> str | None:
    text = _safe_text(value)
    if text is None or not _MODEL_IDENTIFIER_PATTERN.match(text):
        return None
    return text


def _safe_openai_model_id(value: object) -> str | None:
    text = _safe_text(value)
    if text is None:
        return None
    normalized = text.strip()
    if normalized != normalized.lower():
        return None
    if not _OPENAI_MODEL_IDENTIFIER_PATTERN.match(normalized):
        return None
    return normalized


def _is_openai_chat_completions_model_id(model_id: str) -> bool:
    return (
        model_id.startswith("gpt-")
        or model_id.startswith("chatgpt-")
        or bool(re.match(r"^o[0-9](?:[a-z0-9.-]*)$", model_id))
    )


def _safe_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        normalized = value.replace(",", "").strip()
        if _NUMERIC_PATTERN.match(normalized):
            return int(normalized)
    return None


def _timestamp(now: datetime | None = None) -> str:
    effective = now or datetime.now(UTC)
    return effective.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _warning_message(code: str, model_id: str | None) -> str:
    label = f" for {model_id}" if model_id else ""
    messages = {
        "missing_pricing": f"Missing pricing{label}.",
        "unit_unconfirmed": f"Pricing unit could not be confirmed{label}.",
        "pricing_disagreement": f"Pricing sources disagree{label}.",
        "model_missing_from_api": f"Model missing from API source{label}.",
        "model_missing_from_docs": f"Model missing from docs source{label}.",
        "unsupported_endpoint": f"Endpoint support is ambiguous or unsupported{label}.",
        "hosted_tool_only": f"Hosted/provider-side tool support remains unsupported{label}.",
        "search_specific_model": f"Search-specific model omitted from ordinary chat routes{label}.",
        "future_endpoint": f"Future endpoint remained report-only{label}.",
        "unsupported_modality": f"Unsupported modality requires review{label}.",
        "deprecated_or_expiring": f"Deprecated or expiring model requires review{label}.",
        "ambiguous_capability": f"Capability mapping is ambiguous{label}.",
        "duplicate_model": f"Duplicate model proposal requires review{label}.",
        "negative_or_invalid_price": f"Negative or invalid price value{label}.",
        "zero_price_requires_review": f"Zero price requires operator review{label}.",
        "model_missing_from_assisted": f"Model missing from assisted cross-check{label}.",
        "invalid_model_id": "Source row had no safe model id.",
    }
    return messages.get(code, f"{code}{label}")


def _route_notes(
    *,
    provider: ProviderName,
    model_id: str,
    confidence: Confidence,
    context_length: int | None,
    max_output_tokens: int | None,
    source_urls: Sequence[str],
    warnings: Sequence[str],
) -> str:
    parts = [
        f"provider={provider}",
        f"confidence={confidence}",
        f"model={model_id}",
    ]
    if context_length is not None:
        parts.append(f"context={context_length}")
    if max_output_tokens is not None:
        parts.append(f"max_output_tokens={max_output_tokens}")
    if warnings:
        parts.append("warnings=" + ",".join(sorted(set(warnings))))
    if source_urls:
        parts.append("sources=" + ",".join(source_urls))
    return " | ".join(parts)


def _openai_sources_seen(
    *,
    model_id: str,
    docs_model: _OpenAIModelRecord | None,
    has_pricing: bool,
    api_model_ids: set[str] | None,
    assisted_pricing_rows: Mapping[tuple[str, str], dict[str, str]] | None,
    assisted_route_rows: Mapping[tuple[str, str], dict[str, str]] | None,
) -> tuple[str, ...]:
    seen = []
    if docs_model is not None or has_pricing:
        seen.append("docs")
    if api_model_ids is not None and model_id in api_model_ids:
        seen.append("api")
    if assisted_pricing_rows is not None or assisted_route_rows is not None:
        if (assisted_pricing_rows and (model_id, CHAT_COMPLETIONS_ENDPOINT) in assisted_pricing_rows) or (
            assisted_route_rows and (model_id, CHAT_COMPLETIONS_ENDPOINT) in assisted_route_rows
        ):
            seen.append("assisted")
    return tuple(seen)


def _confidence_from_openai_sources(
    *,
    model_id: str,
    docs_model: _OpenAIModelRecord | None,
    api_model_ids: set[str] | None,
    has_assisted: bool,
) -> Confidence:
    if docs_model is not None and api_model_ids is not None and model_id in api_model_ids:
        return "high"
    if docs_model is not None:
        return "medium"
    if has_assisted:
        return "low"
    return "low"


def _count_confidence(models: Sequence[ProviderCatalogModelCandidate]) -> dict[str, int]:
    counts = {"high": 0, "medium": 0, "low": 0}
    for row in models:
        counts[row.confidence] += 1
    return counts


def _source_to_manifest_entry(source: _FetchedSource) -> ProviderCatalogSource:
    return ProviderCatalogSource(
        provider=source.provider,
        source_type=source.source_type,
        url=source.url,
        retrieved_at=source.retrieved_at,
        content_hash=source.content_hash,
        content_type=source.content_type,
        warnings=source.warnings,
        snapshot_path=source.snapshot_path,
    )


def _dedupe_warning_objects(
    warnings: Sequence[ProviderCatalogWarning],
) -> tuple[ProviderCatalogWarning, ...]:
    seen = set()
    result = []
    for warning in warnings:
        key = (warning.code, warning.provider, warning.model_id, warning.endpoint, warning.message)
        if key in seen:
            continue
        seen.add(key)
        result.append(warning)
    return tuple(result)


def _select_export_candidates(
    route_candidates: Sequence[ProviderCatalogRouteCandidate],
    pricing_candidates: Sequence[ProviderCatalogPricingCandidate],
    *,
    paired_ready_only: bool,
) -> tuple[tuple[ProviderCatalogRouteCandidate, ...], tuple[ProviderCatalogPricingCandidate, ...]]:
    ready_routes = [row for row in route_candidates if row.ready_for_import]
    ready_pricing = [row for row in pricing_candidates if row.ready_for_import]
    if not paired_ready_only:
        return tuple(ready_routes), tuple(ready_pricing)

    route_keys = {(row.provider, row.upstream_model, row.endpoint) for row in ready_routes}
    pricing_keys = {(row.provider, row.model_id, row.endpoint) for row in ready_pricing}
    paired_keys = route_keys & pricing_keys
    filtered_routes = [row for row in ready_routes if (row.provider, row.upstream_model, row.endpoint) in paired_keys]
    filtered_pricing = [row for row in ready_pricing if (row.provider, row.model_id, row.endpoint) in paired_keys]
    return tuple(filtered_routes), tuple(filtered_pricing)


async def _generate_openrouter_package_outputs(
    *,
    client: httpx.AsyncClient,
    output_dir: Path,
    package_names: Sequence[str],
    include_models: Sequence[str],
    exclude_models: Sequence[str],
    source_methods: Sequence[ProposalSourceMethod],
    max_models: int,
    fetch_details_limit: int,
    save_source_snapshots: bool,
    source_dir: Path,
    allow_zero_prices: bool,
    include_deprecated: bool,
    include_ambiguous_capabilities: bool,
    now: datetime | None,
    source_manifest_path: Path,
    fx_capture: ProposalFxCapture | None = None,
) -> tuple[ProviderCatalogPackageResult, ...]:
    package_bundle = await _propose_openrouter(
        client=client,
        endpoint_scopes=("chat_completions", "responses"),
        include_models=include_models,
        exclude_models=exclude_models,
        currency="USD",
        source_methods=source_methods,
        max_models=max_models,
        fetch_details_limit=fetch_details_limit,
        save_source_snapshots=save_source_snapshots,
        source_dir=source_dir,
        allow_zero_prices=allow_zero_prices,
        ordinary_chat_only=False,
        now=now,
    )
    # SAME single captured rate as the root output (the package re-proposes
    # natively in USD; conversion happens here, before selection/writers).
    package_pricing_candidates = apply_proposal_fx(
        package_bundle.pricing_candidates, fx_capture
    )
    model_by_id = {row.model_id: row for row in package_bundle.models}
    paired_routes, paired_pricing = _select_export_candidates(
        package_bundle.route_candidates,
        package_pricing_candidates,
        paired_ready_only=True,
    )
    routes_by_key = {
        (row.provider, row.upstream_model, row.endpoint): row
        for row in paired_routes
    }
    pricing_by_key = {
        (row.provider, row.model_id, row.endpoint): row
        for row in paired_pricing
    }
    base_keys = sorted(routes_by_key.keys() & pricing_by_key.keys())
    comparison_by_model = {
        row.model_id: row
        for row in package_bundle.comparison_rows
        if row.provider == OPENROUTER_PROVIDER
    }

    package_results: list[ProviderCatalogPackageResult] = []
    packages_dir = output_dir / "packages"
    packages_dir.mkdir(parents=True, exist_ok=True)

    package_keys: dict[str, set[tuple[str, str, str]]] = {}
    for package_name in OPENROUTER_PACKAGE_ORDER:
        selected_keys = _select_package_keys(
            package_name=package_name,
            base_keys=base_keys,
            package_keys=package_keys,
            routes_by_key=routes_by_key,
            pricing_by_key=pricing_by_key,
            model_by_id=model_by_id,
            include_deprecated=include_deprecated,
            include_ambiguous_capabilities=include_ambiguous_capabilities,
        )
        package_keys[package_name] = selected_keys
        if package_name not in package_names:
            continue
        package_result = _write_openrouter_package(
            output_dir=packages_dir / package_name,
            package_name=package_name,
            selected_keys=selected_keys,
            routes_by_key=routes_by_key,
            pricing_by_key=pricing_by_key,
            model_by_id=model_by_id,
            comparison_by_model=comparison_by_model,
            include_deprecated=include_deprecated,
            include_ambiguous_capabilities=include_ambiguous_capabilities,
            source_manifest_path=source_manifest_path,
            generated_at=_timestamp(now),
        )
        package_results.append(package_result)
    return tuple(package_results)


def _select_package_keys(
    *,
    package_name: str,
    base_keys: Sequence[tuple[str, str, str]],
    package_keys: Mapping[str, set[tuple[str, str, str]]],
    routes_by_key: Mapping[tuple[str, str, str], ProviderCatalogRouteCandidate],
    pricing_by_key: Mapping[tuple[str, str, str], ProviderCatalogPricingCandidate],
    model_by_id: Mapping[str, ProviderCatalogModelCandidate],
    include_deprecated: bool,
    include_ambiguous_capabilities: bool,
) -> set[tuple[str, str, str]]:
    if package_name == OPENROUTER_RESPONSES_TEXT_PACKAGE:
        return set()

    selected: set[tuple[str, str, str]] = set()
    for key in base_keys:
        route = routes_by_key[key]
        pricing = pricing_by_key[key]
        model = model_by_id.get(route.upstream_model)
        if model is None:
            continue
        if not _package_common_route_allowed(
            route=route,
            pricing=pricing,
            model=model,
            include_deprecated=include_deprecated,
        ):
            continue
        if package_name == OPENROUTER_CHAT_TEXT_PACKAGE and _qualifies_chat_text(model=model):
            selected.add(key)
        elif package_name == OPENROUTER_CHAT_IMAGE_PACKAGE:
            if key in package_keys.get(OPENROUTER_CHAT_TEXT_PACKAGE, set()) or _qualifies_chat_image(
                model=model,
                route=route,
                include_ambiguous_capabilities=include_ambiguous_capabilities,
            ):
                selected.add(key)
        elif package_name == OPENROUTER_CHAT_AUDIO_PACKAGE:
            if key in package_keys.get(OPENROUTER_CHAT_IMAGE_PACKAGE, set()) or _qualifies_chat_audio(
                model=model,
                route=route,
                include_ambiguous_capabilities=include_ambiguous_capabilities,
            ):
                selected.add(key)
        elif package_name == OPENROUTER_CHAT_MULTIMODAL_PACKAGE:
            if key in package_keys.get(OPENROUTER_CHAT_AUDIO_PACKAGE, set()) or _qualifies_chat_multimodal(
                model=model,
                route=route,
                include_ambiguous_capabilities=include_ambiguous_capabilities,
            ):
                selected.add(key)
    return selected


def _package_common_route_allowed(
    *,
    route: ProviderCatalogRouteCandidate,
    pricing: ProviderCatalogPricingCandidate,
    model: ProviderCatalogModelCandidate,
    include_deprecated: bool,
) -> bool:
    if route.endpoint != CHAT_COMPLETIONS_ENDPOINT or pricing.endpoint != CHAT_COMPLETIONS_ENDPOINT:
        return False
    if "search_specific_model" in route.warnings or "hosted_tool_only" in route.warnings:
        return False
    if _looks_like_globally_excluded_package_family(model.model_id):
        return False
    if not include_deprecated and "deprecated_or_expiring" in model.warnings:
        return False
    return True


def _qualifies_chat_text(*, model: ProviderCatalogModelCandidate) -> bool:
    return not _ordinary_chat_candidate_requires_review(
        model_id=model.model_id,
        input_modalities=model.input_modalities,
        output_modalities=model.output_modalities,
    )


def _qualifies_chat_image(
    *,
    model: ProviderCatalogModelCandidate,
    route: ProviderCatalogRouteCandidate,
    include_ambiguous_capabilities: bool,
) -> bool:
    chat = _chat_capabilities_map(route.capabilities)
    if not (chat.get(CHAT_CAPABILITY_IMAGE_INPUTS) and chat.get(CHAT_CAPABILITY_TEXT)):
        return False
    if chat.get(CHAT_CAPABILITY_AUDIO_OUTPUTS):
        return False
    if _looks_like_generation_only_or_excluded(model.model_id):
        return False
    if "ambiguous_capability" in model.warnings and not include_ambiguous_capabilities:
        return False
    return True


def _qualifies_chat_audio(
    *,
    model: ProviderCatalogModelCandidate,
    route: ProviderCatalogRouteCandidate,
    include_ambiguous_capabilities: bool,
) -> bool:
    chat = _chat_capabilities_map(route.capabilities)
    if not chat.get(CHAT_CAPABILITY_TEXT):
        return False
    if not chat.get(CHAT_CAPABILITY_AUDIO_INPUTS):
        return False
    if chat.get(CHAT_CAPABILITY_AUDIO_OUTPUTS):
        return False
    if _looks_like_audio_excluded_family(model.model_id):
        return False
    if "ambiguous_capability" in model.warnings and not include_ambiguous_capabilities:
        return False
    return True


def _qualifies_chat_multimodal(
    *,
    model: ProviderCatalogModelCandidate,
    route: ProviderCatalogRouteCandidate,
    include_ambiguous_capabilities: bool,
) -> bool:
    chat = _chat_capabilities_map(route.capabilities)
    if not chat.get(CHAT_CAPABILITY_TEXT):
        return False
    if not (
        chat.get(CHAT_CAPABILITY_IMAGE_INPUTS)
        or chat.get(CHAT_CAPABILITY_AUDIO_INPUTS)
        or chat.get(CHAT_CAPABILITY_FILE_INPUTS)
    ):
        return False
    if chat.get(CHAT_CAPABILITY_AUDIO_OUTPUTS):
        return False
    if _looks_like_generation_only_or_excluded(model.model_id):
        return False
    if "ambiguous_capability" in model.warnings and not include_ambiguous_capabilities:
        return False
    return True


def _looks_like_excluded_ordinary_chat_family(model_id: str) -> bool:
    lowered = model_id.lower()
    blocked = (
        "image",
        "audio",
        "speech",
        "tts",
        "whisper",
        "realtime",
        "video",
        "lyria",
        "music",
        "vl-",
        "-vl",
        "deep-research",
        "sonar-pro-search",
    )
    return any(token in lowered for token in blocked)


def _looks_like_globally_excluded_package_family(model_id: str) -> bool:
    lowered = model_id.lower()
    blocked = (
        "realtime",
        "video",
        "lyria",
        "music",
        "deep-research",
        "sonar-pro-search",
    )
    return any(token in lowered for token in blocked)


def _looks_like_generation_only_or_excluded(model_id: str) -> bool:
    lowered = model_id.lower()
    blocked = (
        "realtime",
        "video",
        "lyria",
        "music",
        "deep-research",
        "sonar-pro-search",
    )
    return any(token in lowered for token in blocked)


def _looks_like_audio_excluded_family(model_id: str) -> bool:
    lowered = model_id.lower()
    blocked = (
        "realtime",
        "tts",
        "whisper",
        "speech",
        "lyria",
        "music",
        "stt",
    )
    return any(token in lowered for token in blocked)


def _chat_capabilities_map(capabilities: Mapping[str, object]) -> Mapping[str, object]:
    chat = capabilities.get(CHAT_COMPLETIONS_CAPABILITIES_KEY)
    return chat if isinstance(chat, Mapping) else {}


def _write_openrouter_package(
    *,
    output_dir: Path,
    package_name: str,
    selected_keys: set[tuple[str, str, str]],
    routes_by_key: Mapping[tuple[str, str, str], ProviderCatalogRouteCandidate],
    pricing_by_key: Mapping[tuple[str, str, str], ProviderCatalogPricingCandidate],
    model_by_id: Mapping[str, ProviderCatalogModelCandidate],
    comparison_by_model: Mapping[str, ProviderCatalogModelStatus],
    include_deprecated: bool,
    include_ambiguous_capabilities: bool,
    source_manifest_path: Path,
    generated_at: str,
) -> ProviderCatalogPackageResult:
    output_dir.mkdir(parents=True, exist_ok=True)
    routes = tuple(routes_by_key[key] for key in sorted(selected_keys))
    pricing = tuple(pricing_by_key[key] for key in sorted(selected_keys))
    route_path = output_dir / "routes-proposal.tsv"
    pricing_path = output_dir / "pricing-proposal.tsv"
    report_path = output_dir / "package-report.md"
    review_path = output_dir / "model-review.md"
    manifest_path = output_dir / "package-manifest.json"

    _write_route_tsv(route_path, routes, ordinary_chat_only=False)
    _write_pricing_tsv(pricing_path, pricing)
    _validate_generated_route_tsv(route_path, routes)
    _validate_generated_pricing_tsv(pricing_path, pricing)

    endpoint_family, endpoint, superset_of, includes_packages, recommendation, safety_mode = _package_metadata(
        package_name
    )
    warning_counts = _count_warning_codes_for_models(
        comparison_by_model.get(route.upstream_model)
        for route in routes
    )
    excluded_counts = _count_package_excluded_warnings(
        comparison_by_model=comparison_by_model,
        included_model_ids={route.upstream_model for route in routes},
    )
    manifest = {
        "package_name": package_name,
        "provider": OPENROUTER_PROVIDER,
        "endpoint_family": endpoint_family,
        "endpoint": endpoint,
        "superset_of": list(superset_of),
        "includes_packages": list(includes_packages),
        "mode": "paired-ready",
        "ordinary_chat_only": package_name == OPENROUTER_CHAT_TEXT_PACKAGE,
        "route_rows": len(routes),
        "pricing_rows": len(pricing),
        "warnings": warning_counts,
        "excluded_counts": excluded_counts,
        "generated_at": generated_at,
        "source_manifest": os.path.relpath(source_manifest_path, output_dir),
        "include_deprecated": include_deprecated,
        "include_ambiguous_capabilities": include_ambiguous_capabilities,
        "recommendation": recommendation,
        "safety_mode": safety_mode,
        "audio_input_rows": _count_capability(routes, CHAT_CAPABILITY_AUDIO_INPUTS),
        "audio_output_rows": _count_capability(routes, CHAT_CAPABILITY_AUDIO_OUTPUTS),
        "image_input_rows": _count_capability(routes, CHAT_CAPABILITY_IMAGE_INPUTS),
        "file_input_rows": _count_capability(routes, CHAT_CAPABILITY_FILE_INPUTS),
    }
    _write_json(manifest_path, manifest)
    _emit(
        review_path,
        _render_package_model_review(
            package_name=package_name,
            endpoint=endpoint,
            routes=routes,
            pricing=pricing,
            model_by_id=model_by_id,
            recommendation=recommendation,
            safety_mode=safety_mode,
        ).encode("utf-8"),
    )
    _emit(
        report_path,
        _render_package_report(
            package_name=package_name,
            endpoint=endpoint,
            superset_of=superset_of,
            includes_packages=includes_packages,
            route_rows=len(routes),
            pricing_rows=len(pricing),
            warning_counts=warning_counts,
            excluded_counts=excluded_counts,
            recommendation=recommendation,
            safety_mode=safety_mode,
        ).encode("utf-8"),
    )
    return ProviderCatalogPackageResult(
        package_name=package_name,
        package_dir=output_dir,
        endpoint_family=endpoint_family,
        endpoint=endpoint,
        route_rows=len(routes),
        pricing_rows=len(pricing),
        superset_of=superset_of,
        includes_packages=includes_packages,
        recommendation=recommendation,
        warning_counts=warning_counts,
        excluded_counts=excluded_counts,
    )


def _package_metadata(
    package_name: str,
) -> tuple[str, str, tuple[str, ...], tuple[str, ...], str, str]:
    if package_name == OPENROUTER_CHAT_TEXT_PACKAGE:
        return (
            "chat_completions",
            CHAT_COMPLETIONS_ENDPOINT,
            (),
            (),
            "production",
            "default safe import candidate",
        )
    if package_name == OPENROUTER_CHAT_IMAGE_PACKAGE:
        return (
            "chat_completions",
            CHAT_COMPLETIONS_ENDPOINT,
            (OPENROUTER_CHAT_TEXT_PACKAGE,),
            (OPENROUTER_CHAT_TEXT_PACKAGE,),
            "reviewed staging",
            "superset of text chat adding image-input to text-output rows",
        )
    if package_name == OPENROUTER_CHAT_AUDIO_PACKAGE:
        return (
            "chat_completions",
            CHAT_COMPLETIONS_ENDPOINT,
            (OPENROUTER_CHAT_IMAGE_PACKAGE,),
            (OPENROUTER_CHAT_TEXT_PACKAGE, OPENROUTER_CHAT_IMAGE_PACKAGE),
            "reviewed staging",
            "superset of image chat adding safe audio-input chat rows only",
        )
    if package_name == OPENROUTER_CHAT_MULTIMODAL_PACKAGE:
        return (
            "chat_completions",
            CHAT_COMPLETIONS_ENDPOINT,
            (OPENROUTER_CHAT_AUDIO_PACKAGE,),
            (
                OPENROUTER_CHAT_TEXT_PACKAGE,
                OPENROUTER_CHAT_IMAGE_PACKAGE,
                OPENROUTER_CHAT_AUDIO_PACKAGE,
            ),
            "staging",
            "broader safe multimodal chat review surface",
        )
    return (
        "responses",
        RESPONSES_ENDPOINT,
        (),
        (),
        "report-only",
        "separate responses family; zero-row unless current evidence supports import-ready text rows",
    )


def _count_warning_codes_for_models(
    rows: Iterable[ProviderCatalogModelStatus | None],
) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for row in rows:
        if row is None:
            continue
        for warning in row.warnings:
            counts[warning] += 1
    return dict(sorted(counts.items()))


def _count_package_excluded_warnings(
    *,
    comparison_by_model: Mapping[str, ProviderCatalogModelStatus],
    included_model_ids: set[str],
) -> dict[str, int]:
    counts: dict[str, int] = {code: 0 for code in PACKAGE_EXCLUDED_WARNING_CODES}
    for model_id, row in comparison_by_model.items():
        if model_id in included_model_ids:
            continue
        for warning in row.warnings:
            if warning in counts:
                counts[warning] += 1
    return counts


def _count_capability(
    routes: Sequence[ProviderCatalogRouteCandidate],
    capability_key: str,
) -> int:
    total = 0
    for route in routes:
        chat = _chat_capabilities_map(route.capabilities)
        if bool(chat.get(capability_key)):
            total += 1
    return total


def _render_package_model_review(
    *,
    package_name: str,
    endpoint: str,
    routes: Sequence[ProviderCatalogRouteCandidate],
    pricing: Sequence[ProviderCatalogPricingCandidate],
    model_by_id: Mapping[str, ProviderCatalogModelCandidate],
    recommendation: str,
    safety_mode: str,
) -> str:
    pricing_by_key = {
        (row.provider, row.model_id, row.endpoint): row
        for row in pricing
    }
    # Display currency is derived from the ACTUAL rows: this run has a
    # single output currency (the converted candidate currency, or the
    # native USD default when no rows survived). The USD SOURCE-evidence
    # metadata on each row is untouched; only this label follows the
    # values it describes.
    display_currency = pricing[0].currency if pricing else "USD"
    lines = [
        f"# {package_name} review",
        "",
        f"Endpoint: `{endpoint}`",
        f"Recommendation: {recommendation}",
        f"Package status: {safety_mode}",
        f"Rows: {len(routes)}",
        "",
        "<table>",
        "  <thead>",
        f"    <tr><th>model</th><th>endpoint</th><th>input {display_currency} per 1M</th><th>cached input {display_currency} per 1M</th><th>output {display_currency} per 1M</th><th>reasoning {display_currency} per 1M</th><th>context</th><th>max output</th><th>capability badges</th><th>package status</th></tr>",
        "  </thead>",
        "  <tbody>",
    ]
    for route in routes:
        pricing_row = pricing_by_key[(route.provider, route.upstream_model, route.endpoint)]
        model = model_by_id.get(route.upstream_model)
        context = _display_or_dash(model.context_length if model is not None else _parse_route_context(route.notes))
        max_output = _display_or_dash(
            model.max_output_tokens if model is not None else _parse_route_max_output(route.notes)
        )
        lines.append(
            "    <tr>"
            f"<td><code>{_html_escape(route.upstream_model)}</code></td>"
            f"<td><code>{_html_escape(route.endpoint)}</code></td>"
            f"<td>{_html_escape(_display_or_dash(pricing_row.input_price_per_1m))}</td>"
            f"<td>{_html_escape(_display_or_dash(pricing_row.cached_input_price_per_1m))}</td>"
            f"<td>{_html_escape(_display_or_dash(pricing_row.output_price_per_1m))}</td>"
            f"<td>{_html_escape(_display_or_dash(pricing_row.reasoning_price_per_1m))}</td>"
            f"<td>{_html_escape(context)}</td>"
            f"<td>{_html_escape(max_output)}</td>"
            f"<td>{_html_escape(', '.join(_package_capability_badges(route)) or '—')}</td>"
            "<td>import-ready</td>"
            "</tr>"
        )
    if not routes:
        lines.append(
            "    <tr><td colspan=\"10\">— no import-ready rows in this package; review package-report.md for why this surface remained report-only.</td></tr>"
        )
    lines.extend(
        [
            "  </tbody>",
            "</table>",
            "",
            f"Reasoning-capable and separately priced reasoning are distinct. `reasoning {display_currency} per 1M` stays `—` when no separate reasoning price is exposed.",
            "",
        ]
    )
    return "\n".join(lines)


def _render_package_report(
    *,
    package_name: str,
    endpoint: str,
    superset_of: Sequence[str],
    includes_packages: Sequence[str],
    route_rows: int,
    pricing_rows: int,
    warning_counts: Mapping[str, int],
    excluded_counts: Mapping[str, int],
    recommendation: str,
    safety_mode: str,
) -> str:
    lines = [
        f"# {package_name}",
        "",
        f"Endpoint: `{endpoint}`",
        f"Recommendation: {recommendation}",
        f"Package status: {safety_mode}",
        f"Route rows: {route_rows}",
        f"Pricing rows: {pricing_rows}",
        f"Superset of: {', '.join(superset_of) if superset_of else 'none'}",
        f"Includes packages: {', '.join(includes_packages) if includes_packages else 'none'}",
        "",
        "## Included warning counts",
        "",
    ]
    if warning_counts:
        for code, count in warning_counts.items():
            lines.append(f"- `{code}`: {count}")
    else:
        lines.append("- none")
    lines.extend(("", "## Excluded counts", ""))
    for code, count in excluded_counts.items():
        lines.append(f"- `{code}`: {count}")
    lines.extend(
        [
            "",
            "## Review and preview sequence",
            "",
            "1. Review `model-review.md` and this package report.",
            "2. Run pricing dry-run.",
            "3. Run routes dry-run.",
            "4. Execute pricing import only after explicit review.",
            "5. Execute route import only after explicit review.",
            "",
            "```bash",
            "slaif-gateway pricing import \\",
            "  --format tsv \\",
            f"  --file packages/{package_name}/pricing-proposal.tsv \\",
            "  --dry-run \\",
            "  --json",
            "",
            "slaif-gateway routes import \\",
            "  --format tsv \\",
            f"  --file packages/{package_name}/routes-proposal.tsv \\",
            "  --dry-run \\",
            "  --json",
            "```",
            "",
            "Execution remains a separate operator action after review only:",
            "",
            "```bash",
            "slaif-gateway pricing import \\",
            "  --format tsv \\",
            f"  --file packages/{package_name}/pricing-proposal.tsv \\",
            "  --execute \\",
            "  --confirm-import \\",
            f"  --reason \"reviewed {package_name} pricing import\" \\",
            "  --json",
            "",
            "slaif-gateway routes import \\",
            "  --format tsv \\",
            f"  --file packages/{package_name}/routes-proposal.tsv \\",
            "  --execute \\",
            "  --confirm-import \\",
            f"  --reason \"reviewed {package_name} route import\" \\",
            "  --json",
            "```",
            "",
            "Safety notes:",
            "",
            "- proposal/package generation only",
            "- paired-ready TSVs only",
            "- no provider calls happen during import preview or execution",
            "- no production import should be executed blindly from an unreviewed package",
            "",
        ]
    )
    return "\n".join(lines)


def _write_package_indexes(
    *,
    package_index_path: Path,
    package_index_markdown_path: Path,
    package_results: Sequence[ProviderCatalogPackageResult],
) -> None:
    payload = {
        "packages": [
            {
                "package_name": item.package_name,
                "package_dir": os.path.relpath(item.package_dir, package_index_path.parent.parent),
                "endpoint_family": item.endpoint_family,
                "endpoint": item.endpoint,
                "route_rows": item.route_rows,
                "pricing_rows": item.pricing_rows,
                "superset_of": list(item.superset_of),
                "includes_packages": list(item.includes_packages),
                "recommendation": item.recommendation,
                "warnings": dict(item.warning_counts),
                "excluded_counts": dict(item.excluded_counts),
            }
            for item in package_results
        ]
    }
    _write_json(package_index_path, payload)
    lines = [
        "# OpenRouter package index",
        "",
        "## Package relationships",
        "",
        "- `openrouter-chat-text`: base package",
        "- `openrouter-chat-image`: superset of `openrouter-chat-text`",
        "- `openrouter-chat-audio`: superset of `openrouter-chat-image`",
        "- `openrouter-chat-multimodal`: superset of `openrouter-chat-audio`",
        "- `openrouter-responses-text`: separate endpoint family, not a Chat superset",
        "",
        "## Recommended sequence",
        "",
        "1. Review the package report and model review table.",
        "2. Run pricing dry-run.",
        "3. Run routes dry-run.",
        "4. Execute pricing import only with `--execute --confirm-import --reason` after review.",
        "5. Execute route import only with `--execute --confirm-import --reason` after review.",
        "",
        "## Packages",
        "",
    ]
    for item in package_results:
        lines.extend(
            [
                f"### {item.package_name}",
                "",
                f"- endpoint family: `{item.endpoint_family}`",
                f"- endpoint: `{item.endpoint}`",
                f"- route rows: {item.route_rows}",
                f"- pricing rows: {item.pricing_rows}",
                f"- recommendation: {item.recommendation}",
                f"- superset of: {', '.join(item.superset_of) if item.superset_of else 'none'}",
                "",
            ]
        )
    _emit(package_index_markdown_path, "\n".join(lines).encode("utf-8"))


def _package_capability_badges(route: ProviderCatalogRouteCandidate) -> list[str]:
    chat = _chat_capabilities_map(route.capabilities)
    badges = ["text"]
    if chat.get(CHAT_CAPABILITY_STREAMING):
        badges.append("streaming")
    if chat.get(CHAT_CAPABILITY_IMAGE_INPUTS):
        badges.append("image-input")
    if chat.get(CHAT_CAPABILITY_FILE_INPUTS):
        badges.append("file-input")
    if chat.get(CHAT_CAPABILITY_AUDIO_INPUTS):
        badges.append("audio-input")
    if chat.get(CHAT_CAPABILITY_AUDIO_OUTPUTS):
        badges.append("audio-output")
    if chat.get(CHAT_CAPABILITY_REASONING_USAGE):
        badges.append("reasoning-capable")
    if chat.get(CHAT_CAPABILITY_FUNCTION_TOOLS):
        badges.append("function-tools")
    if chat.get(CHAT_CAPABILITY_STRUCTURED_OUTPUTS):
        badges.append("structured")
    return badges


def _parse_route_context(notes: str | None) -> int | None:
    if not notes:
        return None
    match = _ROUTE_CONTEXT_PATTERN.search(notes)
    return int(match.group("value")) if match else None


def _parse_route_max_output(notes: str | None) -> int | None:
    if not notes:
        return None
    match = _ROUTE_MAX_OUTPUT_PATTERN.search(notes)
    return int(match.group("value")) if match else None


def _display_or_dash(value: object) -> str:
    if value is None or value == "":
        return "—"
    return str(value)


def _html_escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _write_route_tsv(
    path: Path,
    rows: Sequence[ProviderCatalogRouteCandidate],
    *,
    ordinary_chat_only: bool,
) -> None:
    fieldnames = [
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
    with StringIO() as buffer:
        writer = csv.DictWriter(buffer, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        for row in rows:
            if not row.ready_for_import:
                continue
            writer.writerow(
                {
                    "requested_model": row.requested_model,
                    "match_type": row.match_type,
                    "endpoint": row.endpoint,
                    "provider": row.provider,
                    "upstream_model": row.upstream_model,
                    "priority": row.priority,
                    "enabled": str(row.enabled).lower(),
                    "visible_in_models": str(row.visible_in_models).lower(),
                    "supports_streaming": str(row.supports_streaming).lower(),
                    "capabilities": json.dumps(
                        _export_route_capabilities(row.capabilities, ordinary_chat_only=ordinary_chat_only),
                        separators=(",", ":"),
                        sort_keys=True,
                    ),
                    "notes": row.notes,
                }
            )
        data = buffer.getvalue().encode("utf-8")
    _emit(path, data)


def _write_pricing_tsv(path: Path, rows: Sequence[ProviderCatalogPricingCandidate]) -> None:
    fieldnames = [
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
    with StringIO() as buffer:
        writer = csv.DictWriter(buffer, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        for row in rows:
            if not row.ready_for_import:
                continue
            writer.writerow(
                {
                    "provider": row.provider,
                    "model": row.model_id,
                    "endpoint": row.endpoint,
                    "currency": row.currency,
                    "input_price_per_1m": row.input_price_per_1m or "",
                    "cached_input_price_per_1m": row.cached_input_price_per_1m or "",
                    "output_price_per_1m": row.output_price_per_1m or "",
                    "reasoning_price_per_1m": row.reasoning_price_per_1m or "",
                    "request_price": row.request_price or "",
                    "valid_from": row.source_retrieved_at,
                    "source_url": row.source_url,
                    "source_retrieved_at": row.source_retrieved_at,
                    "pricing_metadata": json.dumps(row.pricing_metadata, separators=(",", ":"), sort_keys=True),
                    "notes": row.notes,
                }
            )
        data = buffer.getvalue().encode("utf-8")
    _emit(path, data)


def _validate_generated_route_tsv(
    path: Path,
    rows: Sequence[ProviderCatalogRouteCandidate],
) -> None:
    expected_fields = [
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
    _validate_tsv_row_shapes(path, expected_fields=expected_fields)
    route_rows = parse_route_import_tsv(path.read_text(encoding="utf-8"))
    provider_refs = tuple(
        RouteImportProviderRef(
            id=uuid.uuid5(uuid.NAMESPACE_URL, f"provider-catalog:{provider}"),
            provider=provider,
        )
        for provider in sorted({row.provider for row in rows if row.ready_for_import})
    )
    preview = validate_route_import_rows(
        route_rows,
        provider_configs=provider_refs,
        max_rows=max(len(route_rows), 1),
    )
    invalid = [row for row in preview.rows if row.status != "valid"]
    if invalid:
        raise ProviderCatalogProposalValidationError(
            f"routes-proposal.tsv failed route import validation: {invalid[0].errors[0]}"
        )


def _export_route_capabilities(
    capabilities: Mapping[str, object],
    *,
    ordinary_chat_only: bool,
) -> dict[str, object]:
    exported = dict(capabilities)
    if not ordinary_chat_only:
        return exported
    chat = exported.get(CHAT_COMPLETIONS_CAPABILITIES_KEY)
    if not isinstance(chat, Mapping):
        return exported
    allowed_chat_keys = {
        CHAT_CAPABILITY_TEXT,
        CHAT_CAPABILITY_STREAMING,
        CHAT_CAPABILITY_FUNCTION_TOOLS,
        CHAT_CAPABILITY_LEGACY_FUNCTIONS,
        CHAT_CAPABILITY_STRUCTURED_OUTPUTS,
        CHAT_CAPABILITY_JSON_MODE,
        CHAT_CAPABILITY_LOGPROBS,
        CHAT_CAPABILITY_REASONING_USAGE,
        CHAT_CAPABILITY_CACHED_INPUT_USAGE,
    }
    compact_chat = {
        key: value
        for key, value in chat.items()
        if key in allowed_chat_keys and bool(value)
    }
    compact_chat.setdefault(CHAT_CAPABILITY_TEXT, True)
    exported[CHAT_COMPLETIONS_CAPABILITIES_KEY] = compact_chat
    return exported


def _validate_generated_pricing_tsv(path: Path, rows: Sequence[ProviderCatalogPricingCandidate]) -> None:
    expected_fields = [
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
    _validate_tsv_row_shapes(path, expected_fields=expected_fields)
    pricing_rows = parse_pricing_import_tsv(path.read_text(encoding="utf-8"))
    preview = validate_pricing_import_rows(
        pricing_rows,
        max_rows=max(len(pricing_rows), 1),
    )
    invalid = [row for row in preview.rows if row.status != "valid"]
    if invalid:
        raise ProviderCatalogProposalValidationError(
            f"pricing-proposal.tsv failed pricing import validation: {invalid[0].errors[0]}"
        )


def _validate_tsv_row_shapes(path: Path, *, expected_fields: Sequence[str]) -> None:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle, delimiter="\t")
        rows = list(reader)
    if not rows:
        raise ProviderCatalogProposalValidationError(f"{path.name} is empty")
    header = rows[0]
    if header != list(expected_fields):
        raise ProviderCatalogProposalValidationError(
            f"{path.name} header mismatch: expected {list(expected_fields)!r}, got {header!r}"
        )
    for index, row in enumerate(rows[1:], start=2):
        if len(row) != len(header):
            raise ProviderCatalogProposalValidationError(
                f"{path.name} row {index} has {len(row)} columns; expected {len(header)}"
            )
        for field_name, value in zip(header, row, strict=True):
            _validate_tsv_cell(
                path_name=path.name,
                row_number=index,
                field_name=field_name,
                value=value,
            )


def _validate_tsv_cell(*, path_name: str, row_number: int, field_name: str, value: str) -> None:
    if "\n" in value or "\r" in value:
        raise ProviderCatalogProposalValidationError(
            f"{path_name} row {row_number} field {field_name} contains raw multiline content"
        )
    if redact_text(value) != value:
        raise ProviderCatalogProposalValidationError(
            f"{path_name} row {row_number} field {field_name} contains secret-looking content"
        )
    if field_name in {"capabilities", "pricing_metadata"} and value:
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ProviderCatalogProposalValidationError(
                f"{path_name} row {row_number} field {field_name} is not valid JSON"
            ) from exc
        if not isinstance(parsed, dict):
            raise ProviderCatalogProposalValidationError(
                f"{path_name} row {row_number} field {field_name} must be a JSON object"
            )
        if redact_mapping(parsed) != parsed:
            raise ProviderCatalogProposalValidationError(
                f"{path_name} row {row_number} field {field_name} contains secret-looking JSON content"
            )
    if field_name in {
        "input_price_per_1m",
        "cached_input_price_per_1m",
        "output_price_per_1m",
        "reasoning_price_per_1m",
        "request_price",
    } and value:
        try:
            Decimal(value)
        except InvalidOperation as exc:
            raise ProviderCatalogProposalValidationError(
                f"{path_name} row {row_number} field {field_name} is not a decimal string"
            ) from exc
    if field_name in {"enabled", "visible_in_models", "supports_streaming"} and value not in {"true", "false"}:
        raise ProviderCatalogProposalValidationError(
            f"{path_name} row {row_number} field {field_name} must be true or false"
        )
    if field_name == "source_url" and value:
        if any(char.isspace() for char in value):
            raise ProviderCatalogProposalValidationError(
                f"{path_name} row {row_number} field source_url must not contain whitespace"
            )
        parsed = urlparse(value)
        if not parsed.scheme or not parsed.netloc:
            raise ProviderCatalogProposalValidationError(
                f"{path_name} row {row_number} field source_url must be a valid absolute URL"
            )
    if field_name in {"source_retrieved_at", "valid_from"} and value:
        try:
            datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ProviderCatalogProposalValidationError(
                f"{path_name} row {row_number} field {field_name} must be an ISO-8601 timestamp"
            ) from exc


def _render_report(
    *,
    providers: Sequence[str],
    fx_capture: ProposalFxCapture | None = None,
    comparison_rows: Sequence[ProviderCatalogModelStatus],
    warnings: Sequence[ProviderCatalogWarning],
    route_candidates: Sequence[ProviderCatalogRouteCandidate],
    pricing_candidates: Sequence[ProviderCatalogPricingCandidate],
    exported_route_candidates: Sequence[ProviderCatalogRouteCandidate],
    exported_pricing_candidates: Sequence[ProviderCatalogPricingCandidate],
    paired_ready_only: bool,
    ordinary_chat_only: bool,
) -> str:
    lines = [
        "# Provider Catalog Proposal Report",
        "",
        f"Providers: {', '.join(providers)}",
        "",
    ]
    if fx_capture is not None and fx_capture.target_currency != fx_capture.base_currency:
        # Truthful, safe, bounded operator-visible fact (string projections
        # only - never a raw row, DSN, or environment value): the source
        # amounts stayed native USD and were converted with ONE captured
        # configured direct rate, frozen until the proposal is re-run.
        lines.extend(
            [
                f"Output currency: {fx_capture.target_currency} (native source "
                f"{fx_capture.base_currency}; one captured direct "
                f"USD->{fx_capture.target_currency} rate {fx_capture.rate}, "
                f"rate id {fx_capture.fx_rate_id}, valid from "
                f"{fx_capture.valid_from}, valid until "
                f"{fx_capture.valid_until or 'open'}, captured "
                f"{fx_capture.captured_at}; frozen until re-run)",
                "",
            ]
        )
    lines.extend(
        [
        f"Route rows ready: {len(exported_route_candidates)}",
        f"Pricing rows ready: {len(exported_pricing_candidates)}",
        f"Warnings: {len(warnings)}",
        f"Paired ready only: {'yes' if paired_ready_only else 'no'}",
        f"Ordinary chat only: {'yes' if ordinary_chat_only else 'no'}",
        f"Raw ready route rows: {sum(1 for row in route_candidates if row.ready_for_import)}",
        f"Raw ready pricing rows: {sum(1 for row in pricing_candidates if row.ready_for_import)}",
        "",
        "| model | provider | pricing_status | route_status | sources_seen | confidence | warnings | ready_for_route_import | ready_for_pricing_import |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for row in comparison_rows:
        lines.append(
            "| "
            + " | ".join(
                [
                    row.model_id,
                    row.provider,
                    row.pricing_status,
                    row.route_status,
                    ",".join(row.sources_seen),
                    row.confidence,
                    ",".join(row.warnings),
                    "yes" if row.ready_for_route_import else "no",
                    "yes" if row.ready_for_pricing_import else "no",
                ]
            )
            + " |"
        )
    if warnings:
        lines.extend(("", "## Warnings", ""))
        for warning in warnings:
            label = warning.model_id or warning.endpoint or warning.provider
            lines.append(f"- `{warning.code}` {label}: {warning.message}")
    return "\n".join(lines) + "\n"


def _fx_projection(fx_capture: ProposalFxCapture | None) -> dict[str, object] | None:
    """Safe known projection of one captured FX fact (or None for USD).

    USD output is the identity conversion and carries no FX metadata;
    non-USD emits only the frozen string projections of the capture so
    root JSON/manifest/report stay consistent without echoing secrets,
    raw rows, or environment content.
    """
    if fx_capture is None or fx_capture.target_currency == fx_capture.base_currency:
        return None
    return {
        "base_currency": fx_capture.base_currency,
        "target_currency": fx_capture.target_currency,
        "fx_rate_id": fx_capture.fx_rate_id,
        "rate": fx_capture.rate,
        "valid_from": fx_capture.valid_from,
        "valid_until": fx_capture.valid_until,
        "captured_at": fx_capture.captured_at,
    }


def _write_json(path: Path, payload: Mapping[str, object]) -> None:
    data = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
    _emit(path, data)


def _jsonify_dataclass(value: object) -> object:
    if not hasattr(value, "__dataclass_fields__"):
        return value
    return _jsonify_mapping(asdict(value))


def _jsonify_mapping(value: object) -> object:
    if isinstance(value, Decimal):
        return _decimal_to_string(value)
    if isinstance(value, Mapping):
        return {str(key): _jsonify_mapping(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_jsonify_mapping(item) for item in value]
    return value


def _model_allowed(
    model_id: object,
    *,
    include_models: Sequence[str],
    exclude_models: Sequence[str],
) -> bool:
    if not isinstance(model_id, str) or not model_id.strip():
        return False
    if include_models and not any(fnmatch.fnmatch(model_id, pattern) for pattern in include_models):
        return False
    if exclude_models and any(fnmatch.fnmatch(model_id, pattern) for pattern in exclude_models):
        return False
    return True
