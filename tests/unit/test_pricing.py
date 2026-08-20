from decimal import Decimal

import pytest

from slaif_gateway.services.pricing import parse_external_tool_pricing
from slaif_gateway.services.pricing_errors import InvalidPricingDataError
from slaif_gateway.schemas.pricing import ExternalToolPricing


def _metadata(price: object = "0.010000000", source: str = "openai_published_per_call") -> dict[str, object]:
    return {
        "external_tool_pricing": {
            "openai_web_search_call_price_native": price,
            "source": source,
        }
    }


def test_exact_external_tool_pricing_inherits_currency() -> None:
    result = parse_external_tool_pricing(_metadata(), currency="USD")

    assert result is not None
    assert result.currency == "USD"
    assert result.unit_price_native == Decimal("0.010000000")
    assert result.source == "openai_published_per_call"


@pytest.mark.parametrize(
    "metadata",
    [
        _metadata(price="-0.01"),
        _metadata(price="NaN"),
        _metadata(source="unverified"),
        {"external_tool_pricing": {"source": "openai_published_per_call"}},
        {"external_tool_pricing": {"openai_web_search_call_price_native": "0.01", "source": "openai_published_per_call", "extra": 1}},
    ],
)
def test_malformed_selected_external_tool_pricing_fails_closed(metadata: dict[str, object]) -> None:
    with pytest.raises(InvalidPricingDataError):
        parse_external_tool_pricing(metadata, currency="EUR")


def test_missing_external_tool_pricing_is_not_an_ordinary_pricing_error() -> None:
    assert parse_external_tool_pricing({}, currency="EUR") is None
    assert parse_external_tool_pricing(None, currency="EUR") is None


@pytest.mark.parametrize("currency", ["", "US", "usd", "US$"])
def test_direct_external_tool_pricing_rejects_invalid_currency(currency: str) -> None:
    with pytest.raises(ValueError):
        ExternalToolPricing(currency, Decimal("0.01"), "openai_published_per_call")
