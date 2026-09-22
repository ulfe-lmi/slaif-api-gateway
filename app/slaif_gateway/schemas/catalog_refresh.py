"""Typed contracts for catalog refresh proposal bundles and baselines.

Schema v1 is the canonical proposal semantics for the Objective-180 offline
review workflow. The bundle carries *facts and provenance only*: readiness
state, confidence scores, counters, and validator results are deliberately
absent because they are always recomputed by deterministic validation and
must never be trusted from caller-supplied JSON.

Versioning decision (180-c): the catalog-refresh subsystem is still unmerged,
so the typed bundle contract deliberately evolves within schema v1 instead of
branching a v2. The 180-c evolution is additive: sources may now cite the ECB
as the FX reference publisher (``ecb_reference_xml`` with a currency-pair
model), and the validator derives typed observations from the supplied
``evidence_b64`` bytes with registered deterministic parsers, binding
proposed facts to parsed snapshot values. No new top-level bundle fields are
introduced, no existing field changes meaning, and incompatible inputs
(unknown provider/source-kind combinations, malformed snapshots, digests that
contradict the bytes) are rejected clearly at load time or classified
BLOCKED/REVIEW at validation time — never silently accepted.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal, InvalidOperation
import re
from typing import Any, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, model_validator

from slaif_gateway.services.audio_route_capabilities import KNOWN_AUDIO_ENDPOINT_CAPABILITIES
from slaif_gateway.services.chat_completion_route_capabilities import (
    CHAT_CAPABILITY_CACHED_INPUT_USAGE,
    CHAT_CAPABILITY_FUNCTION_TOOLS,
    CHAT_CAPABILITY_JSON_MODE,
    CHAT_CAPABILITY_LEGACY_FUNCTIONS,
    CHAT_CAPABILITY_LOGPROBS,
    CHAT_CAPABILITY_REASONING_USAGE,
    CHAT_CAPABILITY_STREAMING,
    CHAT_CAPABILITY_STRUCTURED_OUTPUTS,
    CHAT_CAPABILITY_TEXT,
    CHAT_COMPLETIONS_CAPABILITIES_KEY,
    KNOWN_CHAT_COMPLETION_CAPABILITIES,
)
from slaif_gateway.services.embeddings_route_capabilities import KNOWN_EMBEDDINGS_CAPABILITIES
from slaif_gateway.services.external_tool_policy_contract import (
    DEFAULT_EXTERNAL_TOOL_OPERATOR_CEILINGS,
    parse_route_external_tool_policy,
)
from slaif_gateway.services.realtime_route_capabilities import KNOWN_REALTIME_CAPABILITIES
from slaif_gateway.services.responses_route_capabilities import (
    CODEX_COMPACTION_COMPATIBLE_ROUTE_IDS_KEY,
    CODEX_LIMITS_KEY,
    KNOWN_RESPONSES_CAPABILITIES,
    parse_codex_compaction_compatible_route_ids,
    parse_codex_route_limits,
)

SCHEMA_VERSION = "1"
RENDERER_VERSION = "181.1"
POLICY_VERSION = 1

_RUN_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
_HEX64_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_CURRENCY_PATTERN = re.compile(r"^[A-Z]{3}$")
_ENV_NAME_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")

KNOWN_PROVIDERS: frozenset[str] = frozenset({"openai", "openrouter"})
KNOWN_UNITS: frozenset[str] = frozenset({"per_1m_tokens", "per_request"})
PRICE_DIMENSION_NAMES: frozenset[str] = frozenset(
    {"input", "cached_input", "output", "reasoning", "request"}
)
SOURCE_KINDS: frozenset[str] = frozenset(
    {
        "openrouter_models_api",
        "openrouter_model_detail",
        "openai_models_api",
        "openai_pricing_docs",
        "openai_models_docs",
        "docs_page",
        "operator_input",
        "ecb_reference_xml",
    }
)
# FX reference sources use a currency-pair "model" part (e.g. "EUR-USD");
# the pair's direction is the publisher's native quote direction.
FX_PAIR_PATTERN = re.compile(r"^[A-Z]{3}-[A-Z]{3}$")
CAPABILITY_KEYS: frozenset[str] = frozenset(
    {
        "text",
        "streaming",
        "function_tools",
        "legacy_functions",
        "structured_outputs",
        "json_mode",
        "logprobs",
        "reasoning_usage",
        "cached_input_usage",
    }
)
MATCH_TYPES: frozenset[str] = frozenset({"exact", "prefix", "glob"})


# The import/database monetary contract is PostgreSQL Numeric(18,9): at most
# 18 significant digits with 9 after the decimal point. Hostile huge
# exponent/precision values (e.g. "1E+1000000") are bounded from the decimal's
# own digit/exponent tuple BEFORE any comparison or arithmetic, so magnitude
# checks can never overflow, and such values are never accepted into a bundle.
_MONEY_MAX_INTEGER_DIGITS = 9
_MONEY_MAX_FRACTION_DIGITS = 9
_FX_LABEL_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")


def parse_decimal_text(raw: Any, *, field: str, non_negative: bool = False) -> str:
    """Accept only exact decimal strings bounded to the Numeric(18,9) contract.

    Rejects floats, booleans, NaN/Infinity, values beyond the 9-integer/
    9-fractional digit bound, and values requiring more than 9 decimal places.
    The bound is a property of the value, not of its spelling: trailing zeros
    in the coefficient are stripped with pure tuple arithmetic (hostile
    exponents included) BEFORE any comparison or arithmetic, so numerically
    equivalent spellings such as "1.0000000000" or "0.0000000010" are
    accepted and preserved verbatim, while out-of-range values fail with a
    safe ValueError. The stripped input text is returned unchanged (never
    re-normalized through ``Decimal.__str__``, which would spell tiny values
    in scientific notation).
    """
    if isinstance(raw, bool) or not isinstance(raw, str):
        raise ValueError(f"{field} must be an exact decimal string (floats are rejected)")
    text = raw.strip()
    try:
        value = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"{field} is not a finite decimal: {field}") from exc
    if not value.is_finite():
        raise ValueError(f"{field} must be finite")
    _sign, digits, exponent = value.as_tuple()
    # The Numeric(18,9) bound is a property of the value, not its spelling:
    # strip trailing zeros from the coefficient (pure tuple arithmetic, no
    # intermediate value construction) so numerically equivalent spellings
    # ("1.0000000000", "0.0000000010") are judged by their value, and hostile
    # exponents still fail safely before any arithmetic.
    trailing = 0
    for digit in reversed(digits):
        if digit == 0:
            trailing += 1
        else:
            break
    if trailing:
        significant = digits[: len(digits) - trailing]
        bound_exponent = exponent + trailing
    else:
        significant = digits
        bound_exponent = exponent
    if not significant:
        # the value is exactly zero in any spelling
        integer_digits = 0
        fraction_digits = 0
    else:
        integer_digits = (
            len(significant) + bound_exponent
            if bound_exponent >= 0
            else max(0, len(significant) + bound_exponent)
        )
        fraction_digits = max(0, -bound_exponent)
    if integer_digits > _MONEY_MAX_INTEGER_DIGITS:
        raise ValueError(f"{field} exceeds the database Numeric(18,9) magnitude bound")
    if fraction_digits > _MONEY_MAX_FRACTION_DIGITS:
        raise ValueError(f"{field} exceeds 9 decimal places (database Numeric(18,9))")
    if non_negative and value < 0:
        raise ValueError(f"{field} must be non-negative")
    return text


def validate_safe_url(raw: str, *, field: str) -> str:
    text = raw.strip()
    if len(text) > 2048:
        raise ValueError(f"{field} exceeds the URL length bound")
    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError(f"{field} must use http or https")
    if not parsed.hostname:
        raise ValueError(f"{field} must include a host")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError(f"{field} must not embed credentials")
    return text


def validate_currency(raw: str, *, field: str) -> str:
    text = (raw or "").strip().upper()
    if not _CURRENCY_PATTERN.fullmatch(text):
        raise ValueError(f"{field} must be a three-letter ISO currency code")
    return text


def validate_capabilities(raw: dict[str, Any], *, field: str) -> dict[str, bool]:
    """Capabilities are a bounded boolean map; no nested or free-form values."""
    if len(raw) > 32:
        raise ValueError(f"{field} may contain at most 32 keys")
    result: dict[str, bool] = {}
    for key, value in raw.items():
        key_text = str(key)
        if len(key_text) > 64:
            raise ValueError(f"{field} keys are bounded to 64 characters")
        if not isinstance(value, bool):
            raise ValueError(f"{field}.{key_text} must be a boolean")
        result[key_text] = value
    return result


class CatalogRefreshModel(BaseModel):
    """Base model: unknown fields are always rejected."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class AwareDatetimeStr(CatalogRefreshModel):
    """Helper kept for clarity; pydantic datetime fields are validated below."""

    value: datetime


class RevisionIdentity(CatalogRefreshModel):
    schema_version: Literal[SCHEMA_VERSION]
    slaif_revision: str = Field(min_length=1, max_length=128)
    renderer_version: str = Field(default=RENDERER_VERSION, min_length=1, max_length=32)
    policy_version: int = Field(default=POLICY_VERSION, ge=1, le=1000)


class ResearchIdentity(CatalogRefreshModel):
    """Objective 180 is offline: live research is NOT_RUN, never fabricated."""

    status: Literal["NOT_RUN"]
    codex_version: Literal["N/A"] = "N/A"
    prompt_version: Literal["N/A"] = "N/A"
    extractor_version: str = Field(min_length=1, max_length=64)
    tool_version: str = Field(min_length=1, max_length=64)


class SourceRetrievalRecord(CatalogRefreshModel):
    """Objective 181: one measured HTTP retrieval outcome for one URL.

    Records what this invocation ACTUALLY fetched: requested and final
    URL, retrieval UTC time (retrieval time is never publication time),
    transport outcome, and content identity. Retrieval time is not
    publication time, and a model creation time is not a price
    publication time. Failed retrievals carry a safe code only — never
    raw response bodies or secret-bearing exception text.
    """

    requested_url: str
    final_url: str | None = None
    retrieved_at: datetime
    outcome: Literal["ok", "failed"]
    status: int | None = Field(default=None, ge=0, le=999)
    failure_code: str | None = Field(default=None, min_length=1, max_length=128)
    content_type: str | None = Field(default=None, max_length=256)
    content_bytes: int | None = Field(default=None, ge=0)
    content_sha256: str | None = None
    attempts: int = Field(default=1, ge=1, le=8)
    redirects: int = Field(default=0, ge=0, le=8)
    published_at: datetime | None = None

    @model_validator(mode="after")
    def _check(self) -> "SourceRetrievalRecord":
        validate_safe_url(self.requested_url, field="requested_url")
        if self.final_url is not None:
            validate_safe_url(self.final_url, field="final_url")
        if self.outcome == "ok":
            if self.status is None or not (200 <= self.status < 300):
                raise ValueError("a successful retrieval records its 2xx status")
            if self.content_bytes is None or not (
                _HEX64_PATTERN.fullmatch(self.content_sha256 or "")
            ):
                raise ValueError("a successful retrieval records content size and digest")
            if self.failure_code is not None:
                raise ValueError("a successful retrieval has no failure code")
        else:
            if self.failure_code is None:
                raise ValueError("a failed retrieval records its safe failure code")
            if self.content_bytes is not None or self.content_sha256 is not None:
                raise ValueError("a failed retrieval never records body content")
        if (
            self.published_at is not None
            and (
                self.published_at.tzinfo is None
                or self.published_at.utcoffset() is None
            )
        ):
            raise ValueError("published_at must be timezone-aware")
        return self


class CollectionInventoryEntry(CatalogRefreshModel):
    """Objective 181 (C3): one observed source model, one disposition.

    Every model the collected sources observed is reconciled exactly
    once. Proposed models live in the bundle's facts; every non-proposed
    observed model appears here exactly once with a compact machine
    reason code and a bounded human detail. Nothing silently disappears;
    the report groups the reasons and keeps the full detail inline.
    """

    provider: str
    model: str
    disposition: Literal[
        "excluded_subset",
        "unsupported",
        "incomplete",
        "deprecated",
        "retained_local",
        "unresolved",
    ]
    reason_code: str = Field(min_length=1, max_length=128)
    detail: str = Field(default="", max_length=240)

    @model_validator(mode="after")
    def _check(self) -> "CollectionInventoryEntry":
        if self.provider not in KNOWN_PROVIDERS:
            raise ValueError(f"unknown provider {self.provider!r}")
        if not (1 <= len(self.model) <= 200):
            raise ValueError("inventory model IDs are bounded to 1..200 characters")
        return self


class CollectionIdentity(CatalogRefreshModel):
    """Objective 181: measured identity of the collecting invocation.

    Present only when this bundle was built by the collect command from
    actual retrievals in this invocation. A supplied bundle reviewed
    offline carries no collection identity: offline review of a supplied
    bundle must not claim live retrieval occurred in that invocation.
    ResearchIdentity remains NOT_RUN for Codex in this objective; this
    identity records the deterministic collector and its real retrieval
    outcomes, never a researcher's SUCCESS label.
    """

    tool: str = Field(min_length=1, max_length=128)
    code_revision: str = Field(min_length=1, max_length=128)
    profile: Literal["standard-v1"]
    providers: tuple[str, ...] = Field(min_length=1)
    model_include: tuple[str, ...] = Field(default=())
    started_at: datetime
    finished_at: datetime
    retrievals: tuple[SourceRetrievalRecord, ...] = Field(default=(), max_length=512)
    inventory: tuple[CollectionInventoryEntry, ...] = Field(default=(), max_length=2048)
    deduplicated_fetches: bool = False
    # 181-b (B3): distinct observed SOURCE model identities per collected
    # provider (the catalog the sources actually listed). Deliberately
    # separate from local route/alias rows: a source model count is not a
    # route count, and the report must not conflate the two.
    source_model_counts: dict[str, int] = Field(default_factory=dict, max_length=8)

    @model_validator(mode="after")
    def _check(self) -> "CollectionIdentity":
        if len(set(self.providers)) != len(self.providers):
            raise ValueError("collection providers contain duplicates")
        for provider in self.providers:
            if provider not in KNOWN_PROVIDERS:
                raise ValueError(f"unknown provider {provider!r} in collection")
        if len(set(self.model_include)) != len(self.model_include):
            raise ValueError("collection model_include contains duplicates")
        if self.started_at.tzinfo is None or self.started_at.utcoffset() is None:
            raise ValueError("collection started_at must be timezone-aware")
        if self.finished_at.tzinfo is None or self.finished_at.utcoffset() is None:
            raise ValueError("collection finished_at must be timezone-aware")
        if self.finished_at < self.started_at:
            raise ValueError("collection finished_at precedes started_at")
        urls = [retrieval.requested_url for retrieval in self.retrievals]
        if len(set(urls)) != len(urls):
            raise ValueError("collection retrievals contain duplicate requested URLs")
        keys = [(entry.provider, entry.model) for entry in self.inventory]
        if len(set(keys)) != len(keys):
            raise ValueError(
                "inventory entries must reconcile each observed model exactly once"
            )
        for provider, count in self.source_model_counts.items():
            if provider not in KNOWN_PROVIDERS:
                raise ValueError(f"unknown provider {provider!r} in source model counts")
            if count < 0:
                raise ValueError("source model counts must be non-negative")
        return self


class ProfileContract(CatalogRefreshModel):
    """Standard v1 profile: ordinary text Chat Completions only."""

    name: Literal["standard-v1"]
    endpoint: Literal["/v1/chat/completions"]
    supports_streaming: bool = True
    local_models_visible: bool = True
    capability_allowlist: tuple[str, ...] = Field(default=())

    @model_validator(mode="after")
    def _check_allowlist(self) -> ProfileContract:
        for key in self.capability_allowlist:
            if key not in CAPABILITY_KEYS:
                raise ValueError(
                    f"capability {key!r} is outside the standard v1 allowlist"
                )
        if len(set(self.capability_allowlist)) != len(self.capability_allowlist):
            raise ValueError("capability allowlist contains duplicates")
        return self


class Selection(CatalogRefreshModel):
    providers: tuple[str, ...] = Field(min_length=1)
    model_include: tuple[str, ...] = Field(default=())

    @model_validator(mode="after")
    def _check(self) -> Selection:
        if len(set(self.providers)) != len(self.providers):
            raise ValueError("selection providers contain duplicates")
        for provider in self.providers:
            if provider not in KNOWN_PROVIDERS:
                raise ValueError(f"unknown provider {provider!r} in selection")
        if len(set(self.model_include)) != len(self.model_include):
            raise ValueError("selection model_include contains duplicates")
        for model in self.model_include:
            if not (1 <= len(model) <= 200):
                raise ValueError("selection model IDs are bounded to 1..200 characters")
        return self


class SourceRecord(CatalogRefreshModel):
    provider: str
    model: str
    source_kind: str
    url: str
    retrieved_at: datetime
    published_at: datetime | None = None
    content_sha256: str
    # Optional inline evidence bytes (base64). When present, the validator
    # (a) binds them to the declared content digest and (b) parses them with
    # the registered deterministic parser for (provider, source_kind),
    # deriving typed observations that proposed facts must be bound to. A
    # matching digest of arbitrary bytes is not content trust: empty,
    # unrelated, or contradictory bytes fail the evidence gate. When absent,
    # the digest is unprovable offline and the source classifies as REVIEW
    # ("not verifiable offline"), never VERIFIED. Bounded so a hostile bundle
    # cannot carry unbounded payloads (4 MiB of decoded bytes).
    evidence_b64: str | None = Field(default=None, max_length=6_000_000)
    extractor: str = Field(min_length=1, max_length=128)
    extraction: Literal["deterministic", "semantic"]
    required: bool = True
    truncated: bool = False
    warnings: tuple[str, ...] = Field(default=())

    @model_validator(mode="after")
    def _check(self) -> SourceRecord:
        validate_safe_url(self.url, field="url")
        if self.provider == "ecb":
            # ECB is the FX reference publisher, not a model provider: its
            # sources must carry the EUR-based reference-rate snapshot kind
            # and a currency-pair model part.
            if self.source_kind != "ecb_reference_xml":
                raise ValueError("ecb sources must use source kind ecb_reference_xml")
            if not FX_PAIR_PATTERN.fullmatch(self.model):
                raise ValueError("ecb sources must carry a currency-pair model (e.g. EUR-USD)")
        elif self.provider not in KNOWN_PROVIDERS:
            raise ValueError(f"unknown provider {self.provider!r}")
        if self.source_kind not in SOURCE_KINDS:
            raise ValueError(f"unknown source kind {self.source_kind!r}")
        if not _HEX64_PATTERN.fullmatch(self.content_sha256):
            raise ValueError("content_sha256 must be 64 lowercase hex characters")
        if self.evidence_b64 is not None and len(self.evidence_b64) % 4 != 0:
            raise ValueError("evidence_b64 must be base64 with padding")
        if self.retrieved_at.tzinfo is None or self.retrieved_at.utcoffset() is None:
            raise ValueError("retrieved_at must be timezone-aware")
        if self.published_at is not None and (
            self.published_at.tzinfo is None or self.published_at.utcoffset() is None
        ):
            raise ValueError("published_at must be timezone-aware")
        for warning in self.warnings:
            if not (1 <= len(warning) <= 400):
                raise ValueError("source warnings are bounded strings")
        if len(self.warnings) > 32:
            raise ValueError("source warnings are bounded to 32 entries")
        return self


class FieldProvenance(CatalogRefreshModel):
    """Provenance references only. Authority is never caller-supplied.

    The caller-declared "authoritative" boolean was removed in 180-b: trust
    is derived deterministically from (provider, source_kind) -> official-host
    rules and the supporting evidence, never declared by the bundle author.
    """

    sources: tuple[str, ...] = Field(min_length=1)
    extractor: str = Field(min_length=1, max_length=128)
    extraction: Literal["deterministic", "semantic"]

    @model_validator(mode="after")
    def _check(self) -> FieldProvenance:
        if len(set(self.sources)) != len(self.sources):
            raise ValueError("provenance sources contain duplicates")
        for source in self.sources:
            parts = source.split("|")
            if len(parts) != 3 or not all(parts):
                raise ValueError(
                    "provenance sources must be '<provider>|<model>|<source_kind>'"
                )
        return self


class PricingDimension(CatalogRefreshModel):
    name: str
    value: str | None = None
    unit: str
    currency: str

    @model_validator(mode="after")
    def _check(self) -> PricingDimension:
        if self.name not in PRICE_DIMENSION_NAMES:
            raise ValueError(f"unknown pricing dimension {self.name!r}")
        if self.unit not in KNOWN_UNITS:
            raise ValueError(f"unknown unit {self.unit!r}")
        validate_currency(self.currency, field="currency")
        if self.value is not None:
            parse_decimal_text(self.value, field=f"dimension.{self.name}", non_negative=True)
        if self.name == "request" and self.unit != "per_request":
            raise ValueError("request dimension requires unit per_request")
        if self.name != "request" and self.unit != "per_1m_tokens":
            raise ValueError(f"{self.name} dimension requires unit per_1m_tokens")
        return self


class ModelPricingFacts(CatalogRefreshModel):
    provider: str
    model: str
    endpoint: Literal["/v1/chat/completions"]
    currency: str
    dimensions: tuple[PricingDimension, ...] = Field(min_length=1)
    valid_from: datetime
    provenance: FieldProvenance
    warnings: tuple[str, ...] = Field(default=())

    @model_validator(mode="after")
    def _check(self) -> ModelPricingFacts:
        if self.provider not in KNOWN_PROVIDERS:
            raise ValueError(f"unknown provider {self.provider!r}")
        validate_currency(self.currency, field="currency")
        names = [dimension.name for dimension in self.dimensions]
        if len(set(names)) != len(names):
            raise ValueError("pricing dimensions must be unique per model")
        if self.valid_from.tzinfo is None or self.valid_from.utcoffset() is None:
            raise ValueError("valid_from must be timezone-aware")
        return self


class RouteFacts(CatalogRefreshModel):
    provider: str
    requested_model: str
    upstream_model: str
    match_type: str
    endpoint: Literal["/v1/chat/completions"]
    priority: int = Field(ge=1, le=100000)
    enabled: bool = True
    visible_in_models: bool = True
    supports_streaming: bool = True
    capabilities: dict[str, bool] = Field(default_factory=dict)
    provenance: FieldProvenance
    warnings: tuple[str, ...] = Field(default=())

    @model_validator(mode="after")
    def _check(self) -> RouteFacts:
        if self.provider not in KNOWN_PROVIDERS:
            raise ValueError(f"unknown provider {self.provider!r}")
        if self.match_type not in MATCH_TYPES:
            raise ValueError(f"unknown match type {self.match_type!r}")
        if len(self.requested_model) > 200 or len(self.upstream_model) > 200:
            raise ValueError("route model identifiers are bounded")
        validate_capabilities(self.capabilities, field="capabilities")
        for key in self.capabilities:
            if key not in CAPABILITY_KEYS:
                raise ValueError(f"capability {key!r} is outside the standard v1 allowlist")
        return self


class FxFacts(CatalogRefreshModel):
    base_currency: str
    quote_currency: str
    rate: str
    valid_from: datetime
    valid_until: datetime | None = None
    published_at: datetime | None = None
    source: str | None = Field(default=None, max_length=2048)
    provenance: FieldProvenance
    warnings: tuple[str, ...] = Field(default=())

    @model_validator(mode="after")
    def _check(self) -> FxFacts:
        validate_currency(self.base_currency, field="base_currency")
        validate_currency(self.quote_currency, field="quote_currency")
        if self.base_currency == self.quote_currency:
            raise ValueError("FX base and quote currencies must differ")
        parse_decimal_text(self.rate, field="rate")
        if Decimal(self.rate) <= 0:
            raise ValueError("FX rate must be positive")
        if self.valid_until is not None and self.valid_until <= self.valid_from:
            raise ValueError("valid_until must be after valid_from")
        if self.source is not None:
            validate_safe_url(self.source, field="source")
        return self


class ModelFacts(CatalogRefreshModel):
    provider: str
    model: str
    display_name: str | None = Field(default=None, max_length=200)
    context_length: int | None = Field(default=None, ge=1)
    max_output_tokens: int | None = Field(default=None, ge=1)
    supports_streaming: bool = True
    capabilities: dict[str, bool] = Field(default_factory=dict)
    deprecated: bool = False
    provenance: FieldProvenance
    warnings: tuple[str, ...] = Field(default=())

    @model_validator(mode="after")
    def _check(self) -> ModelFacts:
        if self.provider not in KNOWN_PROVIDERS:
            raise ValueError(f"unknown provider {self.provider!r}")
        if not (1 <= len(self.model) <= 200):
            raise ValueError("model IDs are bounded to 1..200 characters")
        validate_capabilities(self.capabilities, field="capabilities")
        for key in self.capabilities:
            if key not in CAPABILITY_KEYS:
                raise ValueError(f"capability {key!r} is outside the standard v1 allowlist")
        return self


class BaselineIdentity(CatalogRefreshModel):
    mode: Literal["first_install", "db_snapshot", "exported_file"]
    exported_at: datetime | None = None
    target_database: str | None = Field(default=None, max_length=256)
    # 181-b (B2): explicit host/port identity fields. 180-era bundles
    # predate them (None) and keep the database-name-only comparison;
    # the full target identity is additionally bound inside the hashed
    # baseline content digest in every mode.
    target_host: str | None = Field(default=None, max_length=256)
    target_port: int | None = Field(default=None, ge=1, le=65535)
    postgres_version: str | None = Field(default=None, max_length=32)
    sql_checked: bool = False
    row_counts: dict[str, int] = Field(default_factory=dict)
    content_sha256: str | None = None

    @model_validator(mode="after")
    def _check(self) -> BaselineIdentity:
        if self.mode == "first_install":
            if (
                self.exported_at is not None
                or self.target_database is not None
                or self.target_host is not None
                or self.target_port is not None
            ):
                raise ValueError("first_install baseline must be explicitly empty")
            if self.sql_checked or self.content_sha256 is not None:
                raise ValueError("first_install baseline carries no SQL evidence")
            if self.row_counts:
                raise ValueError("first_install baseline carries no row counts")
        else:
            if self.exported_at is None:
                raise ValueError("non-first-install baseline requires exported_at")
            if self.exported_at.tzinfo is None or self.exported_at.utcoffset() is None:
                raise ValueError("exported_at must be timezone-aware")
            if not self.sql_checked:
                raise ValueError("a non-first-install baseline must record sql_checked")
            if self.content_sha256 is not None and not _HEX64_PATTERN.fullmatch(
                self.content_sha256
            ):
                raise ValueError("content_sha256 must be 64 lowercase hex characters")
            if self.target_database is not None and (
                "@" in self.target_database or "://" in self.target_database
            ):
                raise ValueError("target_database must not carry credentials")
            if self.target_host is not None and (
                "@" in self.target_host or "://" in self.target_host
            ):
                raise ValueError("target_host must not carry credentials")
        for key, value in self.row_counts.items():
            if not (1 <= len(key) <= 64) or value < 0:
                raise ValueError("row_counts must map bounded names to non-negative ints")
        return self


class PolicyDocument(CatalogRefreshModel):
    """Versioned operator policy; every threshold is deterministic data."""

    version: int = Field(default=POLICY_VERSION, ge=1, le=1000)
    price_change_review: str = "0.25"
    fx_change_review: str = "0.03"
    source_stale_review_hours: int = Field(default=24, ge=1, le=8760)
    source_stale_blocked_hours: int = Field(default=72, ge=1, le=8760)
    fx_stale_review_days: int = Field(default=3, ge=0, le=3660)
    fx_stale_blocked_days: int = Field(default=7, ge=0, le=3660)

    @model_validator(mode="after")
    def _check(self) -> PolicyDocument:
        for field_name in ("price_change_review", "fx_change_review"):
            value = Decimal(getattr(self, field_name))
            if not value.is_finite() or value <= 0:
                raise ValueError(f"{field_name} must be a positive finite decimal")
        if self.source_stale_blocked_hours < self.source_stale_review_hours:
            raise ValueError("source_stale_blocked_hours must be >= review hours")
        if self.fx_stale_blocked_days < self.fx_stale_review_days:
            raise ValueError("fx_stale_blocked_days must be >= review days")
        if self.version != POLICY_VERSION:
            raise ValueError(f"unsupported policy version {self.version}")
        return self


class RefreshBundle(CatalogRefreshModel):
    """The canonical catalog-refresh.json proposal bundle (facts only)."""

    schema_version: Literal[SCHEMA_VERSION]
    run_id: str
    generated_at: datetime
    revision: RevisionIdentity
    research: ResearchIdentity
    # Objective 181: present only for bundles built by the collect command
    # from actual retrievals in this invocation. Optional (schema version
    # deliberately remains "1" so sealed 180-era bundles still replay and
    # verify unchanged); supplied bundles carry no collection identity.
    collection: CollectionIdentity | None = None
    policy: PolicyDocument
    profile: ProfileContract
    selection: Selection
    sources: tuple[SourceRecord, ...] = Field(default=())
    models: tuple[ModelFacts, ...] = Field(default=())
    pricing: tuple[ModelPricingFacts, ...] = Field(default=())
    routes: tuple[RouteFacts, ...] = Field(default=())
    fx: tuple[FxFacts, ...] = Field(default=())
    baseline: BaselineIdentity
    notes: str | None = Field(default=None, max_length=4000)

    @model_validator(mode="after")
    def _unique_identities(self) -> RefreshBundle:
        if not _RUN_ID_PATTERN.fullmatch(self.run_id):
            raise ValueError("run_id must match ^[a-z0-9][a-z0-9-]{0,63}$")
        if self.generated_at.tzinfo is None or self.generated_at.utcoffset() is None:
            raise ValueError("generated_at must be timezone-aware")

        source_keys = [
            (source.provider, source.model, source.source_kind) for source in self.sources
        ]
        if len(set(source_keys)) != len(source_keys):
            raise ValueError("duplicate source identities (provider|model|source_kind)")

        model_keys = [(item.provider, item.model) for item in self.models]
        if len(set(model_keys)) != len(model_keys):
            raise ValueError("duplicate model identities (provider|model)")

        pricing_keys = [
            (item.provider, item.model, item.endpoint, item.currency)
            for item in self.pricing
        ]
        if len(set(pricing_keys)) != len(pricing_keys):
            raise ValueError("duplicate pricing identities (provider|model|endpoint|currency)")

        route_keys = [
            (item.provider, item.requested_model, item.match_type, item.endpoint)
            for item in self.routes
        ]
        if len(set(route_keys)) != len(route_keys):
            raise ValueError("duplicate route identities (provider|requested_model|match_type|endpoint)")

        fx_keys = [(item.base_currency, item.quote_currency, item.valid_from) for item in self.fx]
        if len(set(fx_keys)) != len(fx_keys):
            raise ValueError("duplicate FX identities (base|quote|valid_from)")

        provenance_keys = {
            f"{provider}|{model}|{kind}" for provider, model, kind in source_keys
        }
        for facts in (*self.models, *self.pricing, *self.routes, *self.fx):
            for source in facts.provenance.sources:
                if source not in provenance_keys:
                    raise ValueError(f"provenance references unknown source {source!r}")
        return self


# --- Baseline document (read-only export) -----------------------------------


class BaselineTarget(CatalogRefreshModel):
    server_host: str = Field(min_length=1, max_length=256)
    server_port: int = Field(ge=1, le=65535)
    database: str = Field(min_length=1, max_length=256)
    postgres_version: str = Field(min_length=1, max_length=32)


class BaselineProviderRow(CatalogRefreshModel):
    id: str
    provider: str
    display_name: str
    kind: str
    base_url: str
    api_key_env_var: str | None = None
    enabled: bool
    timeout_seconds: int
    max_retries: int
    created_at: datetime
    updated_at: datetime


# --- Baseline route capability projection (180-e) ---------------------------
# Runtime model_routes.capabilities is a nested map of endpoint-family blocks
# (chat_completions/audio_endpoints/embeddings/realtime/responses boolean
# blocks, the typed codex_limits integer contract, the bounded Codex
# compaction route-ID allowlist, and the typed external_tools policy). The
# baseline export projects exactly the recognized runtime contract with
# bounded allowlists, preserving nested structure and effective meaning.
# Unrecognized keys/values are never carried into the public document; the
# row is flagged unrepresented (with a fingerprint of the raw map as a safe
# comparison identity) instead of being silently claimed unchanged.
_CAPABILITY_BOOL_BLOCKS: dict[str, frozenset[str]] = {
    "chat_completions": KNOWN_CHAT_COMPLETION_CAPABILITIES,
    "audio_endpoints": KNOWN_AUDIO_ENDPOINT_CAPABILITIES,
    "embeddings": KNOWN_EMBEDDINGS_CAPABILITIES,
    "realtime": KNOWN_REALTIME_CAPABILITIES,
    "responses": KNOWN_RESPONSES_CAPABILITIES,
}
_CAPABILITY_TOP_KEYS: frozenset[str] = frozenset(_CAPABILITY_BOOL_BLOCKS) | frozenset(
    {CODEX_LIMITS_KEY, CODEX_COMPACTION_COMPATIBLE_ROUTE_IDS_KEY, "external_tools"}
)

# 180-f (F2): the single deterministic mapping between proposal intent and
# the runtime chat_completions capability shape. EVERY consumer (emitted
# import bytes, evidence requirements, before/after comparison, rendered
# rows) uses this mapping; nothing else grants or compares capability
# meaning.
FLAT_CAPABILITY_TO_CHAT_FIELD: dict[str, str] = {
    "text": CHAT_CAPABILITY_TEXT,
    "streaming": CHAT_CAPABILITY_STREAMING,
    "function_tools": CHAT_CAPABILITY_FUNCTION_TOOLS,
    "legacy_functions": CHAT_CAPABILITY_LEGACY_FUNCTIONS,
    "structured_outputs": CHAT_CAPABILITY_STRUCTURED_OUTPUTS,
    "json_mode": CHAT_CAPABILITY_JSON_MODE,
    "logprobs": CHAT_CAPABILITY_LOGPROBS,
    "reasoning_usage": CHAT_CAPABILITY_REASONING_USAGE,
    "cached_input_usage": CHAT_CAPABILITY_CACHED_INPUT_USAGE,
}


def declared_capability_overlay(flat: Mapping[str, bool] | None) -> dict[str, bool]:
    """Explicitly declared standard keys, mapped onto chat_completions fields.

    Only keys actually present in the proposal intent are returned; omitted
    keys are NOT defaulted, so an overlay can never silently rewrite an
    approved stored field (including an explicit denial).
    """
    overlay: dict[str, bool] = {}
    for key, value in (flat or {}).items():
        if key in FLAT_CAPABILITY_TO_CHAT_FIELD and isinstance(value, bool):
            overlay[FLAT_CAPABILITY_TO_CHAT_FIELD[key]] = value
    return overlay


def derive_standard_create_capabilities(
    flat: Mapping[str, bool] | None, *, supports_streaming: bool
) -> dict[str, bool]:
    """Capability block for a NEW standard Chat Completions route.

    The documented standard scope is text plus the route's declared streaming
    intent, plus any other standard key the proposal EXPLICITLY declares.
    Nothing else is granted: undeclared function tools, structured outputs,
    logprobs or any other runtime default stay absent (runtime-denied) - the
    create never turns on permissions the proposal did not request.
    """
    declared = declared_capability_overlay(flat)
    block: dict[str, bool] = {
        CHAT_CAPABILITY_TEXT: declared.get(CHAT_CAPABILITY_TEXT, True),
        CHAT_CAPABILITY_STREAMING: declared.get(CHAT_CAPABILITY_STREAMING, supports_streaming),
    }
    for key, value in declared.items():
        if key not in block:
            block[key] = value
    return dict(sorted(block.items()))


def overlay_route_capabilities(
    stored_block: Mapping[str, bool] | None, flat: Mapping[str, bool] | None
) -> dict[str, bool]:
    """Effective block for an EXISTING row: the reviewed baseline block as the
    base, with ONLY the explicitly declared intent overlaid. Omitted approved
    fields - including explicit denials - are preserved verbatim."""
    effective = dict(stored_block) if isinstance(stored_block, Mapping) else {}
    effective.update(declared_capability_overlay(flat))
    return effective


def derived_route_capabilities(
    flat: Mapping[str, bool] | None, *, supports_streaming: bool
) -> dict[str, Any]:
    """Canonical capabilities map emitted for a NEW standard route row.

    Standard refresh proposals are Chat Completions routes only, so the map
    carries exactly the recognized nested runtime block (the conservative
    create contract) and no stray flat storage keys; the import path stores
    a declared nested block verbatim.
    """
    return {
        CHAT_COMPLETIONS_CAPABILITIES_KEY: derive_standard_create_capabilities(
            flat, supports_streaming=supports_streaming
        )
    }


def validate_route_capability_projection(raw: Any) -> None:
    """Strict canonical shape for a projected baseline capabilities map.

    Raises ValueError (naming the block, never the offending value or key) on
    any deviation, so a baseline file can never smuggle free-form data into
    the public document.
    """
    if not isinstance(raw, Mapping):
        raise ValueError("baseline capabilities must be an object")
    for key in raw:
        if not isinstance(key, str) or key not in _CAPABILITY_TOP_KEYS:
            raise ValueError("baseline capabilities carry an unknown block")
    for key in _CAPABILITY_BOOL_BLOCKS:
        if key not in raw:
            continue
        value = raw[key]
        if not isinstance(value, Mapping):
            raise ValueError(f"capability block {key} must be an object")
        for inner_key, inner in value.items():
            if not isinstance(inner_key, str) or inner_key not in _CAPABILITY_BOOL_BLOCKS[key]:
                raise ValueError(f"capability block {key} carries an unknown field")
            if not isinstance(inner, bool):
                raise ValueError(f"capability block {key} carries a non-boolean value")
    if CODEX_LIMITS_KEY in raw:
        try:
            parse_codex_route_limits({CODEX_LIMITS_KEY: raw[CODEX_LIMITS_KEY]})
        except Exception as exc:  # noqa: BLE001 - contract parser raises typed errors
            raise ValueError("capability block codex_limits is malformed") from exc
    if CODEX_COMPACTION_COMPATIBLE_ROUTE_IDS_KEY in raw:
        try:
            parse_codex_compaction_compatible_route_ids(
                {CODEX_COMPACTION_COMPATIBLE_ROUTE_IDS_KEY: raw[CODEX_COMPACTION_COMPATIBLE_ROUTE_IDS_KEY]}
            )
        except Exception as exc:  # noqa: BLE001
            raise ValueError("capability block codex_compaction_compatible_route_ids is malformed") from exc
    if "external_tools" in raw:
        result = parse_route_external_tool_policy(
            raw["external_tools"], ceilings=DEFAULT_EXTERNAL_TOOL_OPERATOR_CEILINGS
        )
        if not result.valid or result.policy is None:
            raise ValueError("capability block external_tools is malformed")


class BaselineRouteRow(CatalogRefreshModel):
    id: str
    requested_model: str
    match_type: str
    endpoint: str
    provider: str
    upstream_model: str
    priority: int
    enabled: bool
    visible_in_models: bool
    supports_streaming: bool
    # Projected nested runtime capability contract (180-e): recognized
    # endpoint-family blocks only, canonical shape, no free-form values.
    capabilities: dict[str, Any] = Field(default_factory=dict)
    # True when the raw map carried values outside the recognized contract;
    # the raw values are NOT carried into the document, and affected changes
    # are blocked by validation instead of being claimed unchanged.
    capabilities_unrepresented: bool = False
    # sha256 of the canonical JSON of the raw capabilities map: a safe opaque
    # comparison identity (an identity, not anonymization of guessable
    # secrets).
    capabilities_fingerprint: str = Field(min_length=64, max_length=64)
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def _check(self) -> BaselineRouteRow:
        validate_route_capability_projection(self.capabilities)
        if not _HEX64_PATTERN.fullmatch(self.capabilities_fingerprint):
            raise ValueError("capabilities_fingerprint must be 64 lowercase hex characters")
        return self


_PRICING_MONEY_FIELDS: tuple[str, ...] = (
    "input_price_per_1m",
    "cached_input_price_per_1m",
    "output_price_per_1m",
    "reasoning_price_per_1m",
    "request_price",
    "audio_output_price_per_1m",
    "cache_write_input_price_per_1m",
)
_PRICING_MULTIPLIER_FIELDS: tuple[str, ...] = (
    "cache_write_input_multiplier",
    "long_context_input_multiplier",
    "long_context_output_multiplier",
)


class BaselinePricingRow(CatalogRefreshModel):
    id: str
    provider: str
    upstream_model: str
    endpoint: str
    currency: str
    input_price_per_1m: str | None = None
    cached_input_price_per_1m: str | None = None
    output_price_per_1m: str | None = None
    reasoning_price_per_1m: str | None = None
    request_price: str | None = None
    valid_from: datetime
    valid_until: datetime | None = None
    enabled: bool
    source_url: str | None = None
    created_at: datetime
    updated_at: datetime
    # 180-e: typed allowlisted monetary metadata retained from the runtime
    # pricing_metadata (audio output pricing, Codex cache-write/long-context
    # accounting, selected hosted fee). Free-form metadata is never carried;
    # unrepresentable monetary metadata flags the row instead.
    audio_output_price_per_1m: str | None = None
    cache_write_input_price_per_1m: str | None = None
    cache_write_input_multiplier: str | None = None
    long_context_threshold_tokens: int | None = None
    long_context_input_multiplier: str | None = None
    long_context_output_multiplier: str | None = None
    external_tool_price_per_call: str | None = None
    external_tool_source: Literal["openai_published_per_call"] | None = None
    pricing_metadata_unrepresented: bool = False

    @model_validator(mode="after")
    def _check(self) -> BaselinePricingRow:
        validate_currency(self.currency, field="currency")
        for name in _PRICING_MONEY_FIELDS:
            value = getattr(self, name)
            if value is not None:
                parse_decimal_text(value, field=f"pricing.{name}", non_negative=True)
        for name in _PRICING_MULTIPLIER_FIELDS:
            value = getattr(self, name)
            if value is not None:
                parse_decimal_text(value, field=f"pricing.{name}", non_negative=True)
                if Decimal(value) <= 0:
                    raise ValueError(f"pricing.{name} must be positive")
        if self.long_context_threshold_tokens is not None and (
            isinstance(self.long_context_threshold_tokens, bool)
            or self.long_context_threshold_tokens <= 0
        ):
            raise ValueError("pricing.long_context_threshold_tokens must be a positive integer")
        codex_fields = (
            self.long_context_threshold_tokens,
            self.long_context_input_multiplier,
            self.long_context_output_multiplier,
        )
        cache_fields = (self.cache_write_input_price_per_1m, self.cache_write_input_multiplier)
        # Mirror the runtime codex accounting contract exactly: the
        # long-context fields are all-or-none and, whenever that set is
        # present, EXACTLY ONE cache-write field (price or multiplier) must
        # be present; a cache field without the set, or the set without a
        # cache field, is not a valid runtime row.
        if any(value is not None for value in codex_fields):
            if any(value is None for value in codex_fields):
                raise ValueError("codex accounting metadata must carry the full long-context field set")
            if sum(1 for value in cache_fields if value is not None) != 1:
                raise ValueError("codex accounting metadata requires exactly one cache-write field")
        elif any(value is not None for value in cache_fields):
            raise ValueError("codex accounting metadata requires the full long-context field set")
        if (self.external_tool_price_per_call is None) != (self.external_tool_source is None):
            raise ValueError("external tool pricing price and source must be set together")
        if self.external_tool_price_per_call is not None:
            parse_decimal_text(
                self.external_tool_price_per_call,
                field="pricing.external_tool_price_per_call",
                non_negative=True,
            )
        return self


class BaselineFxRow(CatalogRefreshModel):
    id: str
    base_currency: str
    quote_currency: str
    rate: str
    valid_from: datetime
    valid_until: datetime | None = None
    source: str | None = None
    # Legacy FX sources are not always URLs: safe normalized labels (e.g.
    # "manual", "ecb") are retained as typed labels. A row carries at most
    # one of source/source_label.
    source_label: str | None = Field(default=None, max_length=64)
    created_at: datetime

    @model_validator(mode="after")
    def _check(self) -> BaselineFxRow:
        validate_currency(self.base_currency, field="base_currency")
        validate_currency(self.quote_currency, field="quote_currency")
        parse_decimal_text(self.rate, field="fx.rate")
        if Decimal(self.rate) <= 0:
            raise ValueError("fx.rate must be positive")
        if self.source is not None:
            validate_safe_url(self.source, field="fx.source")
        if self.source is not None and self.source_label is not None:
            raise ValueError("fx row carries both a source URL and a source label")
        if self.source_label is not None and not _FX_LABEL_PATTERN.fullmatch(self.source_label):
            raise ValueError("fx.source_label must be a safe normalized label")
        return self


class BaselineCounts(CatalogRefreshModel):
    providers: int = Field(ge=0)
    routes: int = Field(ge=0)
    pricing_rules: int = Field(ge=0)
    fx_rates: int = Field(ge=0)


class BaselineDocument(CatalogRefreshModel):
    schema_version: Literal[SCHEMA_VERSION]
    exported_at: datetime
    target: BaselineTarget
    sql_checked: Literal[True]
    counts: BaselineCounts
    content_sha256: str
    providers: tuple[BaselineProviderRow, ...] = Field(default=())
    routes: tuple[BaselineRouteRow, ...] = Field(default=())
    pricing: tuple[BaselinePricingRow, ...] = Field(default=())
    fx: tuple[BaselineFxRow, ...] = Field(default=())

    @model_validator(mode="after")
    def _counts_match(self) -> BaselineDocument:
        if self.exported_at.tzinfo is None or self.exported_at.utcoffset() is None:
            raise ValueError("exported_at must be timezone-aware")
        if not _HEX64_PATTERN.fullmatch(self.content_sha256):
            raise ValueError("content_sha256 must be 64 lowercase hex characters")
        if (
            self.counts.providers != len(self.providers)
            or self.counts.routes != len(self.routes)
            or self.counts.pricing_rules != len(self.pricing)
            or self.counts.fx_rates != len(self.fx)
        ):
            raise ValueError("counts must match exported rows exactly")
        for row in self.providers:
            if row.api_key_env_var is not None and not _ENV_NAME_PATTERN.fullmatch(
                row.api_key_env_var
            ):
                raise ValueError("api_key_env_var must be an environment variable name")
        return self
