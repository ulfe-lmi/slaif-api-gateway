"""Service-layer pricing lookup and FX conversion for cost estimates."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Final

from slaif_gateway.db.models import FxRate, PricingRule
from slaif_gateway.db.repositories.fx_rates import FxRatesRepository
from slaif_gateway.db.repositories.pricing import PricingRulesRepository
from slaif_gateway.schemas.audio import AudioPolicyResult
from slaif_gateway.schemas.embeddings import EmbeddingsPolicyResult
from slaif_gateway.schemas.policy import ChatCompletionPolicyResult, ResponsesPolicyResult
from slaif_gateway.schemas.pricing import (
    ChatCostEstimate,
    ExternalToolPricing,
    FxConversionResult,
    PricingLookupResult,
)
from slaif_gateway.schemas.realtime import RealtimePolicyResult
from slaif_gateway.schemas.routing import RouteResolutionResult
from slaif_gateway.services.pricing_errors import (
    AudioOutputPricingNotSupportedError,
    AudioRequestPricingNotSupportedError,
    FxRateNotFoundError,
    InvalidFxRateError,
    InvalidPricingDataError,
    PricingRuleNotFoundError,
    RealtimeClientSecretPricingNotSupportedError,
    UnsupportedCurrencyError,
)
from slaif_gateway.services.chat_completion_route_capabilities import (
    is_fixed_request_module_billing,
)

_ONE_MILLION: Final[Decimal] = Decimal("1000000")
_EUR: Final[str] = "EUR"
_CODEX_ACCOUNTING_METADATA_KEY: Final[str] = "codex_accounting"
_CODEX_ACCOUNTING_REQUIRED_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "long_context_threshold_tokens",
        "long_context_input_multiplier",
        "long_context_output_multiplier",
    }
)
_CODEX_ACCOUNTING_CACHE_FIELDS: Final[frozenset[str]] = frozenset(
    {"cache_write_input_price_per_1m", "cache_write_input_multiplier"}
)
_EXTERNAL_TOOL_PRICING_KEY: Final[str] = "external_tool_pricing"
_EXTERNAL_TOOL_PRICE_KEY: Final[str] = "openai_web_search_call_price_native"
_EXTERNAL_TOOL_SOURCE: Final[str] = "openai_published_per_call"


class PricingService:
    """Estimate maximum chat-completions cost using configured pricing and FX rows."""

    def __init__(
        self,
        *,
        pricing_rules_repository: PricingRulesRepository,
        fx_rates_repository: FxRatesRepository,
    ) -> None:
        self._pricing_rules_repository = pricing_rules_repository
        self._fx_rates_repository = fx_rates_repository

    async def find_active_pricing_rule(
        self,
        *,
        provider: str,
        model: str,
        endpoint: str,
        at: datetime | None = None,
    ) -> PricingLookupResult:
        at_time = _aware_time(at)
        normalized_endpoint = _normalize_endpoint(endpoint)
        row = await self._pricing_rules_repository.find_active_pricing_rule(
            provider=provider,
            upstream_model=model,
            endpoint=normalized_endpoint,
            at_time=at_time,
        )
        if row is None:
            raise PricingRuleNotFoundError(param="model")

        return _pricing_lookup_result(row)

    async def convert_to_eur(
        self,
        amount: Decimal,
        native_currency: str,
        at: datetime | None = None,
    ) -> tuple[Decimal, FxConversionResult]:
        currency = _normalize_currency(native_currency)
        if currency == _EUR:
            conversion = FxConversionResult(
                from_currency=_EUR,
                to_currency=_EUR,
                rate=Decimal("1"),
                fx_rate_id=None,
            )
            return amount, conversion

        at_time = _aware_time(at)
        row = await self._fx_rates_repository.find_latest_rate(
            base_currency=currency,
            quote_currency=_EUR,
            at_time=at_time,
        )
        if row is None:
            raise FxRateNotFoundError(param="currency")

        conversion = _fx_conversion_result(row)
        return amount * conversion.rate, conversion

    async def estimate_chat_completion_cost(
        self,
        *,
        route: RouteResolutionResult,
        policy: ChatCompletionPolicyResult | ResponsesPolicyResult,
        endpoint: str = "chat.completions",
        at: datetime | None = None,
        pricing: PricingLookupResult | None = None,
        fx: FxConversionResult | None = None,
    ) -> ChatCostEstimate:
        if pricing is None:
            pricing = await self.find_active_pricing_rule(
                provider=route.provider,
                model=route.resolved_model,
                endpoint=endpoint,
                at=at,
            )

        if is_fixed_request_module_billing(route.provider_kind, endpoint):
            if pricing.request_price is None:
                raise InvalidPricingDataError(
                    "Native module Chat Completions pricing requires a request price."
                )
            request_price = _required_non_negative_decimal(
                pricing.request_price,
                field_name="request_price",
            )
            total_eur, fx = await self.convert_to_eur(request_price, pricing.currency, at=at)
            return ChatCostEstimate(
                provider=route.provider,
                requested_model=route.requested_model,
                resolved_model=route.resolved_model,
                native_currency=pricing.currency,
                estimated_input_tokens=0,
                estimated_output_tokens=0,
                estimated_input_cost_native=Decimal("0"),
                estimated_output_cost_native=Decimal("0"),
                estimated_total_cost_native=request_price,
                estimated_total_cost_eur=total_eur,
                pricing_rule_id=pricing.pricing_rule_id,
                fx_rate_id=fx.fx_rate_id,
                input_price_per_1m=pricing.input_price_per_1m,
                cached_input_price_per_1m=pricing.cached_input_price_per_1m,
                output_price_per_1m=pricing.output_price_per_1m,
                reasoning_price_per_1m=pricing.reasoning_price_per_1m,
                audio_output_price_per_1m=pricing.audio_output_price_per_1m,
                request_price=request_price,
                fx_rate=fx.rate,
            )

        input_tokens = policy.estimated_input_tokens
        output_tokens = policy.effective_output_tokens
        audio_output_requested = _uses_audio_output(policy.effective_body)
        if audio_output_requested and pricing.audio_output_price_per_1m is None:
            raise AudioOutputPricingNotSupportedError(param="audio")

        codex_accounting = bool(getattr(policy, "codex_limits_applied", False))
        input_price = pricing.input_price_per_1m
        output_price = pricing.output_price_per_1m
        if codex_accounting:
            if (
                pricing.cache_write_input_price_per_1m is None
                or pricing.long_context_threshold_tokens is None
                or pricing.long_context_input_multiplier is None
                or pricing.long_context_output_multiplier is None
                or pricing.reasoning_price_per_1m is None
                or pricing.cached_input_price_per_1m is None
            ):
                raise InvalidPricingDataError(
                    "Complete Codex cache, reasoning, and long-context pricing is required."
                )
            input_price = max(
                pricing.input_price_per_1m,
                pricing.cache_write_input_price_per_1m,
            ) * max(Decimal("1"), pricing.long_context_input_multiplier)
            output_price = max(
                pricing.output_price_per_1m,
                pricing.reasoning_price_per_1m,
            ) * max(Decimal("1"), pricing.long_context_output_multiplier)

        input_cost_native = Decimal(input_tokens) / _ONE_MILLION * input_price
        if audio_output_requested and pricing.audio_output_price_per_1m is not None:
            output_price = max(output_price, pricing.audio_output_price_per_1m)
        output_cost_native = Decimal(output_tokens) / _ONE_MILLION * output_price
        total_native = input_cost_native + output_cost_native
        if fx is None:
            total_eur, fx = await self.convert_to_eur(total_native, pricing.currency, at=at)
        else:
            total_eur = total_native * fx.rate

        return ChatCostEstimate(
            provider=route.provider,
            requested_model=route.requested_model,
            resolved_model=route.resolved_model,
            native_currency=pricing.currency,
            estimated_input_tokens=input_tokens,
            estimated_output_tokens=output_tokens,
            estimated_input_cost_native=input_cost_native,
            estimated_output_cost_native=output_cost_native,
            estimated_total_cost_native=total_native,
            estimated_total_cost_eur=total_eur,
            pricing_rule_id=pricing.pricing_rule_id,
            fx_rate_id=fx.fx_rate_id,
            input_price_per_1m=pricing.input_price_per_1m,
            cached_input_price_per_1m=pricing.cached_input_price_per_1m,
            output_price_per_1m=pricing.output_price_per_1m,
            reasoning_price_per_1m=pricing.reasoning_price_per_1m,
            audio_output_price_per_1m=pricing.audio_output_price_per_1m,
            request_price=pricing.request_price,
            fx_rate=fx.rate,
            cache_write_input_price_per_1m=pricing.cache_write_input_price_per_1m,
            cache_write_input_multiplier=pricing.cache_write_input_multiplier,
            long_context_threshold_tokens=pricing.long_context_threshold_tokens,
            long_context_input_multiplier=pricing.long_context_input_multiplier,
            long_context_output_multiplier=pricing.long_context_output_multiplier,
            codex_accounting=codex_accounting,
        )

    async def estimate_audio_operation_cost(
        self,
        *,
        route: RouteResolutionResult,
        policy: AudioPolicyResult,
        endpoint: str,
        at: datetime | None = None,
    ) -> ChatCostEstimate:
        pricing = await self.find_active_pricing_rule(
            provider=route.provider,
            model=route.resolved_model,
            endpoint=endpoint,
            at=at,
        )

        input_tokens = policy.estimated_input_tokens
        output_tokens = 0

        input_cost_native = Decimal(input_tokens) / _ONE_MILLION * pricing.input_price_per_1m
        total_native = input_cost_native
        if pricing.request_price is not None:
            total_native = pricing.request_price
            input_cost_native = pricing.request_price
        elif endpoint in {"/v1/audio/transcriptions", "/v1/audio/translations"}:
            raise AudioRequestPricingNotSupportedError(param="model")

        total_eur, fx = await self.convert_to_eur(total_native, pricing.currency, at=at)

        return ChatCostEstimate(
            provider=route.provider,
            requested_model=route.requested_model,
            resolved_model=route.resolved_model,
            native_currency=pricing.currency,
            estimated_input_tokens=input_tokens,
            estimated_output_tokens=output_tokens,
            estimated_input_cost_native=input_cost_native,
            estimated_output_cost_native=Decimal("0"),
            estimated_total_cost_native=total_native,
            estimated_total_cost_eur=total_eur,
            pricing_rule_id=pricing.pricing_rule_id,
            fx_rate_id=fx.fx_rate_id,
            input_price_per_1m=pricing.input_price_per_1m,
            cached_input_price_per_1m=pricing.cached_input_price_per_1m,
            output_price_per_1m=pricing.output_price_per_1m,
            reasoning_price_per_1m=pricing.reasoning_price_per_1m,
            audio_output_price_per_1m=None,
            request_price=pricing.request_price,
            fx_rate=fx.rate,
        )

    async def estimate_embeddings_cost(
        self,
        *,
        route: RouteResolutionResult,
        policy: EmbeddingsPolicyResult,
        endpoint: str = "/v1/embeddings",
        at: datetime | None = None,
    ) -> ChatCostEstimate:
        pricing = await self.find_active_pricing_rule(
            provider=route.provider,
            model=route.resolved_model,
            endpoint=endpoint,
            at=at,
        )

        input_tokens = policy.estimated_input_tokens
        input_cost_native = Decimal(input_tokens) / _ONE_MILLION * pricing.input_price_per_1m
        total_eur, fx = await self.convert_to_eur(input_cost_native, pricing.currency, at=at)

        return ChatCostEstimate(
            provider=route.provider,
            requested_model=route.requested_model,
            resolved_model=route.resolved_model,
            native_currency=pricing.currency,
            estimated_input_tokens=input_tokens,
            estimated_output_tokens=0,
            estimated_input_cost_native=input_cost_native,
            estimated_output_cost_native=Decimal("0"),
            estimated_total_cost_native=input_cost_native,
            estimated_total_cost_eur=total_eur,
            pricing_rule_id=pricing.pricing_rule_id,
            fx_rate_id=fx.fx_rate_id,
            input_price_per_1m=pricing.input_price_per_1m,
            cached_input_price_per_1m=pricing.cached_input_price_per_1m,
            output_price_per_1m=pricing.output_price_per_1m,
            reasoning_price_per_1m=pricing.reasoning_price_per_1m,
            audio_output_price_per_1m=None,
            request_price=None,
            fx_rate=fx.rate,
        )

    async def estimate_realtime_client_secret_cost(
        self,
        *,
        route: RouteResolutionResult,
        policy: RealtimePolicyResult,
        endpoint: str = "/v1/realtime/client_secrets",
        admission_pricing_only: bool = False,
        at: datetime | None = None,
    ) -> ChatCostEstimate:
        pricing = await self.find_active_pricing_rule(
            provider=route.provider,
            model=route.resolved_model,
            endpoint=endpoint,
            at=at,
        )

        input_tokens = policy.estimated_input_tokens
        output_tokens = policy.effective_output_tokens
        if admission_pricing_only:
            if pricing.request_price is None:
                raise RealtimeClientSecretPricingNotSupportedError(param="model")
            input_cost_native = Decimal("0")
            output_cost_native = Decimal("0")
            total_native = pricing.request_price
        else:
            input_cost_native = Decimal(input_tokens) / _ONE_MILLION * pricing.input_price_per_1m
            output_cost_native = Decimal(output_tokens) / _ONE_MILLION * pricing.output_price_per_1m
            total_native = input_cost_native + output_cost_native
            if pricing.request_price is not None:
                total_native = max(total_native, pricing.request_price)
        total_eur, fx = await self.convert_to_eur(total_native, pricing.currency, at=at)

        return ChatCostEstimate(
            provider=route.provider,
            requested_model=route.requested_model,
            resolved_model=route.resolved_model,
            native_currency=pricing.currency,
            estimated_input_tokens=input_tokens,
            estimated_output_tokens=output_tokens,
            estimated_input_cost_native=input_cost_native,
            estimated_output_cost_native=output_cost_native,
            estimated_total_cost_native=total_native,
            estimated_total_cost_eur=total_eur,
            pricing_rule_id=pricing.pricing_rule_id,
            fx_rate_id=fx.fx_rate_id,
            input_price_per_1m=pricing.input_price_per_1m,
            cached_input_price_per_1m=pricing.cached_input_price_per_1m,
            output_price_per_1m=pricing.output_price_per_1m,
            reasoning_price_per_1m=pricing.reasoning_price_per_1m,
            audio_output_price_per_1m=None,
            request_price=pricing.request_price,
            fx_rate=fx.rate,
        )


def _aware_time(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value


def _normalize_currency(value: str) -> str:
    currency = value.strip().upper()
    if not currency:
        raise UnsupportedCurrencyError(param="currency")
    return currency


def _normalize_endpoint(value: str) -> str:
    endpoint = value.strip()
    if endpoint == "chat.completions":
        return "/v1/chat/completions"
    if endpoint == "audio.speech":
        return "/v1/audio/speech"
    if endpoint == "audio.transcriptions":
        return "/v1/audio/transcriptions"
    if endpoint == "audio.translations":
        return "/v1/audio/translations"
    if endpoint == "embeddings":
        return "/v1/embeddings"
    if endpoint == "realtime.client_secrets":
        return "/v1/realtime/client_secrets"
    if endpoint == "responses":
        return "/v1/responses"
    return endpoint


def _pricing_lookup_result(row: PricingRule) -> PricingLookupResult:
    currency = _normalize_currency(row.currency)
    input_price = _required_non_negative_decimal(
        row.input_price_per_1m,
        field_name="input_price_per_1m",
    )
    output_price = _required_non_negative_decimal(
        row.output_price_per_1m,
        field_name="output_price_per_1m",
    )
    cached_input_price = _optional_non_negative_decimal(
        row.cached_input_price_per_1m,
        field_name="cached_input_price_per_1m",
    )
    reasoning_price = _optional_non_negative_decimal(
        row.reasoning_price_per_1m,
        field_name="reasoning_price_per_1m",
    )
    audio_output_price = _optional_metadata_price_per_1m(
        row.pricing_metadata,
        field_name="audio_output_price_per_1m",
    )
    (
        cache_write_input_price,
        cache_write_input_multiplier,
        long_context_threshold,
        long_context_input_multiplier,
        long_context_output_multiplier,
    ) = _codex_accounting_metadata(
        row.pricing_metadata,
        input_price_per_1m=input_price,
    )

    return PricingLookupResult(
        provider=row.provider,
        model=row.upstream_model,
        endpoint=row.endpoint,
        currency=currency,
        input_price_per_1m=input_price,
        cached_input_price_per_1m=cached_input_price,
        output_price_per_1m=output_price,
        reasoning_price_per_1m=reasoning_price,
        audio_output_price_per_1m=audio_output_price,
        request_price=_optional_non_negative_decimal(
            row.request_price,
            field_name="request_price",
        ),
        cache_write_input_price_per_1m=cache_write_input_price,
        cache_write_input_multiplier=cache_write_input_multiplier,
        long_context_threshold_tokens=long_context_threshold,
        long_context_input_multiplier=long_context_input_multiplier,
        long_context_output_multiplier=long_context_output_multiplier,
        pricing_rule_id=row.id,
        valid_from=row.valid_from,
        valid_until=row.valid_until,
        external_tool_pricing=_optional_external_tool_pricing(
            row.pricing_metadata,
            currency=currency,
        ),
    )


def parse_external_tool_pricing(
    metadata: Mapping[str, Any] | None,
    *,
    currency: str,
) -> ExternalToolPricing | None:
    """Parse the exact selected hosted-tool metadata, failing closed when present."""
    if not isinstance(metadata, Mapping) or _EXTERNAL_TOOL_PRICING_KEY not in metadata:
        return None
    raw = metadata.get(_EXTERNAL_TOOL_PRICING_KEY)
    if not isinstance(raw, Mapping) or set(raw) != {_EXTERNAL_TOOL_PRICE_KEY, "source"}:
        raise InvalidPricingDataError("External-tool pricing metadata is malformed.")
    source = raw.get("source")
    price = raw.get(_EXTERNAL_TOOL_PRICE_KEY)
    if source != _EXTERNAL_TOOL_SOURCE:
        raise InvalidPricingDataError("External-tool pricing source is not approved.")
    try:
        amount = Decimal(str(price))
    except Exception as exc:
        raise InvalidPricingDataError("External-tool pricing amount is invalid.") from exc
    if not amount.is_finite() or amount < 0:
        raise InvalidPricingDataError("External-tool pricing amount is invalid.")
    return ExternalToolPricing(currency=currency, unit_price_native=amount, source=source)


def _optional_external_tool_pricing(
    metadata: Mapping[str, Any] | None,
    *,
    currency: str,
) -> ExternalToolPricing | None:
    """Keep ordinary pricing lookup compatible; selected contracts parse strictly."""
    if not isinstance(metadata, Mapping) or _EXTERNAL_TOOL_PRICING_KEY not in metadata:
        return None
    raw = metadata.get(_EXTERNAL_TOOL_PRICING_KEY)
    if not isinstance(raw, Mapping) or set(raw) != {_EXTERNAL_TOOL_PRICE_KEY, "source"}:
        return None
    if raw.get("source") != _EXTERNAL_TOOL_SOURCE:
        return None
    try:
        amount = Decimal(str(raw.get(_EXTERNAL_TOOL_PRICE_KEY)))
    except Exception:
        return None
    if not amount.is_finite() or amount < 0:
        return None
    return ExternalToolPricing(currency=currency, unit_price_native=amount, source=_EXTERNAL_TOOL_SOURCE)


def _codex_accounting_metadata(
    metadata: Mapping[str, Any] | None,
    *,
    input_price_per_1m: Decimal,
) -> tuple[Decimal | None, Decimal | None, int | None, Decimal | None, Decimal | None]:
    if not isinstance(metadata, Mapping) or _CODEX_ACCOUNTING_METADATA_KEY not in metadata:
        return None, None, None, None, None
    raw = metadata.get(_CODEX_ACCOUNTING_METADATA_KEY)
    if not isinstance(raw, Mapping):
        raise InvalidPricingDataError("Configured Codex accounting metadata must be an object.")
    fields = {str(key) for key in raw}
    cache_fields = fields.intersection(_CODEX_ACCOUNTING_CACHE_FIELDS)
    expected = _CODEX_ACCOUNTING_REQUIRED_FIELDS.union(cache_fields)
    if len(cache_fields) != 1 or fields != expected:
        raise InvalidPricingDataError(
            "Configured Codex accounting metadata is partial or contains unknown fields."
        )

    threshold = raw.get("long_context_threshold_tokens")
    if isinstance(threshold, bool) or not isinstance(threshold, int) or threshold <= 0:
        raise InvalidPricingDataError(
            "Configured Codex long-context threshold must be a positive integer."
        )
    long_input = _strict_positive_decimal_string(
        raw.get("long_context_input_multiplier"),
        field_name="long_context_input_multiplier",
    )
    long_output = _strict_positive_decimal_string(
        raw.get("long_context_output_multiplier"),
        field_name="long_context_output_multiplier",
    )
    cache_price: Decimal | None = None
    cache_multiplier: Decimal | None = None
    if "cache_write_input_price_per_1m" in raw:
        cache_price = _strict_non_negative_decimal_string(
            raw.get("cache_write_input_price_per_1m"),
            field_name="cache_write_input_price_per_1m",
        )
    else:
        cache_multiplier = _strict_positive_decimal_string(
            raw.get("cache_write_input_multiplier"),
            field_name="cache_write_input_multiplier",
        )
        cache_price = input_price_per_1m * cache_multiplier
    return cache_price, cache_multiplier, threshold, long_input, long_output


def _strict_non_negative_decimal_string(value: object, *, field_name: str) -> Decimal:
    if not isinstance(value, str) or not value.strip():
        raise InvalidPricingDataError(
            f"Configured Codex pricing field '{field_name}' must be a decimal string."
        )
    try:
        parsed = Decimal(value)
    except Exception as exc:
        raise InvalidPricingDataError(
            f"Configured Codex pricing field '{field_name}' must be a decimal string."
        ) from exc
    if not parsed.is_finite() or parsed < 0:
        raise InvalidPricingDataError(
            f"Configured Codex pricing field '{field_name}' must be non-negative."
        )
    return parsed


def _strict_positive_decimal_string(value: object, *, field_name: str) -> Decimal:
    parsed = _strict_non_negative_decimal_string(value, field_name=field_name)
    if parsed <= 0:
        raise InvalidPricingDataError(
            f"Configured Codex pricing field '{field_name}' must be positive."
        )
    return parsed


def _fx_conversion_result(row: FxRate) -> FxConversionResult:
    rate = _required_positive_decimal(row.rate, field_name="rate")
    return FxConversionResult(
        from_currency=_normalize_currency(row.base_currency),
        to_currency=_normalize_currency(row.quote_currency),
        rate=rate,
        fx_rate_id=row.id,
    )


def _required_non_negative_decimal(value: Decimal | None, *, field_name: str) -> Decimal:
    if value is None:
        raise InvalidPricingDataError(
            f"Configured pricing field '{field_name}' is required for chat cost estimates."
        )
    return _optional_non_negative_decimal(value, field_name=field_name)


def _optional_non_negative_decimal(value: Decimal | None, *, field_name: str) -> Decimal | None:
    if value is None:
        return None
    if not isinstance(value, Decimal):
        raise InvalidPricingDataError(f"Configured pricing field '{field_name}' must be Decimal.")
    if value < 0:
        raise InvalidPricingDataError(
            f"Configured pricing field '{field_name}' must be non-negative."
        )
    return value


def _optional_metadata_price_per_1m(
    metadata: Mapping[str, Any] | None,
    *,
    field_name: str,
) -> Decimal | None:
    if not isinstance(metadata, Mapping):
        return None
    value = metadata.get(field_name)
    if value is None:
        return None
    if isinstance(value, bool):
        raise InvalidPricingDataError(
            f"Configured pricing metadata field '{field_name}' must be numeric."
        )
    if isinstance(value, Decimal):
        return _optional_non_negative_decimal(value, field_name=field_name)
    if isinstance(value, int | float | str):
        try:
            parsed = Decimal(str(value))
        except Exception as exc:
            raise InvalidPricingDataError(
                f"Configured pricing metadata field '{field_name}' must be numeric."
            ) from exc
        return _optional_non_negative_decimal(parsed, field_name=field_name)
    raise InvalidPricingDataError(
        f"Configured pricing metadata field '{field_name}' must be numeric."
    )


def _uses_audio_output(payload: Mapping[str, Any]) -> bool:
    modalities = payload.get("modalities")
    return isinstance(modalities, list) and any(item == "audio" for item in modalities)


def _required_positive_decimal(value: Decimal, *, field_name: str) -> Decimal:
    if not isinstance(value, Decimal):
        raise InvalidFxRateError(f"Configured FX field '{field_name}' must be Decimal.")
    if value <= 0:
        raise InvalidFxRateError(f"Configured FX field '{field_name}' must be positive.")
    return value
