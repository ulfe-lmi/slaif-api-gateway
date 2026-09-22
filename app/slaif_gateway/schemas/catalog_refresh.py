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

from datetime import datetime
from decimal import Decimal, InvalidOperation
import re
from typing import Any, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, model_validator

SCHEMA_VERSION = "1"
RENDERER_VERSION = "180.2"
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
# exponent/precision values (e.g. Decimal("1E+100")) are rejected before any
# expensive formatting or arithmetic and never accepted into a bundle.
_MONEY_MAX = Decimal("999999999.999999999")
_MONEY_MAX_EXPONENT = -9


def parse_decimal_text(raw: Any, *, field: str, non_negative: bool = False) -> str:
    """Accept only exact decimal strings bounded to the Numeric(18,9) contract.

    Rejects floats, NaN/Infinity, values beyond the 9-integer/9-fractional
    digit bound, and values requiring more than 9 decimal places.
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
    if abs(value) > _MONEY_MAX:
        raise ValueError(f"{field} exceeds the database Numeric(18,9) magnitude bound")
    _sign, _digits, exponent = value.as_tuple()
    if exponent < _MONEY_MAX_EXPONENT:
        raise ValueError(f"{field} exceeds 9 decimal places (database Numeric(18,9))")
    if non_negative and value < 0:
        raise ValueError(f"{field} must be non-negative")
    return str(value)


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
    postgres_version: str | None = Field(default=None, max_length=32)
    sql_checked: bool = False
    row_counts: dict[str, int] = Field(default_factory=dict)
    content_sha256: str | None = None

    @model_validator(mode="after")
    def _check(self) -> BaselineIdentity:
        if self.mode == "first_install":
            if self.exported_at is not None or self.target_database is not None:
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


def validate_strict_capabilities(raw: dict[str, Any], *, field: str) -> dict[str, bool]:
    """Strict shape for route capabilities retained in a baseline export.

    Capabilities are the one semantically necessary free-form map kept in the
    default export. They are validated (boolean values, bounded keys) and a
    non-conforming value fails with a safe, explicit issue instead of being
    silently truncated.
    """
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
    capabilities: dict[str, bool] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def _check(self) -> BaselineRouteRow:
        validate_strict_capabilities(self.capabilities, field="capabilities")
        return self


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


class BaselineFxRow(CatalogRefreshModel):
    id: str
    base_currency: str
    quote_currency: str
    rate: str
    valid_from: datetime
    valid_until: datetime | None = None
    source: str | None = None
    created_at: datetime


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
