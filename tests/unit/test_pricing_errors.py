from __future__ import annotations

from slaif_gateway.api.pricing_errors import openai_error_from_pricing_error
from slaif_gateway.services.pricing_errors import (
    FxRateNotFoundError,
    InvalidFxRateError,
    InvalidPricingDataError,
    PricingRuleNotFoundError,
    UnsupportedCurrencyError,
)


def test_missing_pricing_maps_to_invalid_request_error() -> None:
    error = PricingRuleNotFoundError(param="model")

    mapped = openai_error_from_pricing_error(error)

    assert mapped.status_code == 400
    assert mapped.error_type == "invalid_request_error"
    assert mapped.code == "pricing_rule_not_found"
    assert mapped.param == "model"


def test_missing_fx_maps_to_invalid_request_error() -> None:
    error = FxRateNotFoundError(param="currency")

    mapped = openai_error_from_pricing_error(error)

    assert mapped.status_code == 400
    assert mapped.error_type == "invalid_request_error"
    assert mapped.code == "fx_rate_not_found"
    assert mapped.param == "currency"


def test_invalid_pricing_maps_to_server_error() -> None:
    mapped = openai_error_from_pricing_error(InvalidPricingDataError())

    assert mapped.status_code == 500
    assert mapped.error_type == "server_error"
    assert mapped.code == "invalid_pricing_data"


def test_invalid_fx_maps_to_server_error() -> None:
    mapped = openai_error_from_pricing_error(InvalidFxRateError())

    assert mapped.status_code == 500
    assert mapped.error_type == "server_error"
    assert mapped.code == "invalid_fx_rate"


def test_unsupported_currency_has_safe_metadata() -> None:
    error = UnsupportedCurrencyError(param="currency")

    assert error.status_code == 400
    assert error.error_type == "invalid_request_error"
    assert error.error_code == "unsupported_currency"
    assert error.param == "currency"
