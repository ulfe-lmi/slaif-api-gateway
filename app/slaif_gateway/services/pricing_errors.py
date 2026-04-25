"""Domain errors for pricing lookup and FX conversion."""

from __future__ import annotations


class PricingError(Exception):
    """Base domain error for cost-estimation failures."""

    status_code: int = 400
    error_type: str = "invalid_request_error"
    error_code: str = "pricing_error"
    message: str = "Unable to estimate request cost"

    def __init__(self, safe_message: str | None = None, *, param: str | None = None) -> None:
        self.safe_message = safe_message or self.message
        self.param = param
        super().__init__(self.safe_message)


class PricingRuleNotFoundError(PricingError):
    error_code = "pricing_rule_not_found"
    message = "No enabled pricing rule is configured for the resolved model"


class PricingRuleDisabledError(PricingError):
    status_code = 403
    error_type = "permission_error"
    error_code = "pricing_rule_disabled"
    message = "Pricing for the resolved model is disabled"


class FxRateNotFoundError(PricingError):
    error_code = "fx_rate_not_found"
    message = "No FX rate is configured for converting the model currency to EUR"


class UnsupportedCurrencyError(PricingError):
    error_code = "unsupported_currency"
    message = "The pricing currency is not supported"


class InvalidPricingDataError(PricingError):
    status_code = 500
    error_type = "server_error"
    error_code = "invalid_pricing_data"
    message = "Configured pricing data is invalid"


class InvalidFxRateError(PricingError):
    status_code = 500
    error_type = "server_error"
    error_code = "invalid_fx_rate"
    message = "Configured FX rate is invalid"
