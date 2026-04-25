"""Service-layer pricing lookup and FX conversion for cost estimates."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Final

from slaif_gateway.db.models import FxRate, PricingRule
from slaif_gateway.db.repositories.fx_rates import FxRatesRepository
from slaif_gateway.db.repositories.pricing import PricingRulesRepository
from slaif_gateway.schemas.policy import ChatCompletionPolicyResult
from slaif_gateway.schemas.pricing import (
    ChatCostEstimate,
    FxConversionResult,
    PricingLookupResult,
)
from slaif_gateway.schemas.routing import RouteResolutionResult
from slaif_gateway.services.pricing_errors import (
    FxRateNotFoundError,
    InvalidFxRateError,
    InvalidPricingDataError,
    PricingRuleNotFoundError,
    UnsupportedCurrencyError,
)

_ONE_MILLION: Final[Decimal] = Decimal("1000000")
_EUR: Final[str] = "EUR"


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
        policy: ChatCompletionPolicyResult,
        endpoint: str = "chat.completions",
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
        input_cost_native = (
            Decimal(input_tokens) / _ONE_MILLION * pricing.input_price_per_1m
        )
        output_cost_native = (
            Decimal(output_tokens) / _ONE_MILLION * pricing.output_price_per_1m
        )
        total_native = input_cost_native + output_cost_native
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

    return PricingLookupResult(
        provider=row.provider,
        model=row.upstream_model,
        endpoint=row.endpoint,
        currency=currency,
        input_price_per_1m=input_price,
        cached_input_price_per_1m=cached_input_price,
        output_price_per_1m=output_price,
        reasoning_price_per_1m=reasoning_price,
        pricing_rule_id=row.id,
        valid_from=row.valid_from,
        valid_until=row.valid_until,
    )


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


def _required_positive_decimal(value: Decimal, *, field_name: str) -> Decimal:
    if not isinstance(value, Decimal):
        raise InvalidFxRateError(f"Configured FX field '{field_name}' must be Decimal.")
    if value <= 0:
        raise InvalidFxRateError(f"Configured FX field '{field_name}' must be positive.")
    return value
