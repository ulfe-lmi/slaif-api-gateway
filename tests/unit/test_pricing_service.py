from __future__ import annotations

import inspect
import uuid
from copy import deepcopy
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from slaif_gateway.schemas.policy import ChatCompletionPolicyResult
from slaif_gateway.schemas.routing import RouteResolutionResult
from slaif_gateway.services.pricing import PricingService
from slaif_gateway.services.pricing_errors import (
    FxRateNotFoundError,
    InvalidFxRateError,
    InvalidPricingDataError,
    PricingRuleNotFoundError,
)


class FakePricingRulesRepository:
    def __init__(self, rows: list[SimpleNamespace]) -> None:
        self._rows = rows

    async def find_active_pricing_rule(
        self,
        *,
        provider: str,
        upstream_model: str,
        endpoint: str,
        at_time: datetime,
    ) -> SimpleNamespace | None:
        matches = [
            row
            for row in self._rows
            if row.provider == provider
            and row.upstream_model == upstream_model
            and row.endpoint == endpoint
            and row.enabled is True
            and row.valid_from <= at_time
            and (row.valid_until is None or row.valid_until > at_time)
        ]
        matches.sort(key=lambda row: row.valid_from, reverse=True)
        return matches[0] if matches else None


class FakeFxRatesRepository:
    def __init__(self, rows: list[SimpleNamespace]) -> None:
        self._rows = rows

    async def find_latest_rate(
        self,
        *,
        base_currency: str,
        quote_currency: str,
        at_time: datetime | None = None,
    ) -> SimpleNamespace | None:
        rows = [
            row
            for row in self._rows
            if row.base_currency == base_currency and row.quote_currency == quote_currency
        ]
        if at_time is not None:
            rows = [
                row
                for row in rows
                if row.valid_from <= at_time and (row.valid_until is None or row.valid_until > at_time)
            ]
        rows.sort(key=lambda row: row.valid_from, reverse=True)
        return rows[0] if rows else None


def _pricing_rule(
    *,
    provider: str = "openai",
    upstream_model: str = "gpt-4.1-mini",
    endpoint: str = "/v1/chat/completions",
    currency: str = "USD",
    input_price_per_1m: Decimal | None = Decimal("0.150000000"),
    cached_input_price_per_1m: Decimal | None = Decimal("0.075000000"),
    output_price_per_1m: Decimal | None = Decimal("0.600000000"),
    reasoning_price_per_1m: Decimal | None = None,
    valid_from: datetime | None = None,
    valid_until: datetime | None = None,
    enabled: bool = True,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        provider=provider,
        upstream_model=upstream_model,
        endpoint=endpoint,
        currency=currency,
        input_price_per_1m=input_price_per_1m,
        cached_input_price_per_1m=cached_input_price_per_1m,
        output_price_per_1m=output_price_per_1m,
        reasoning_price_per_1m=reasoning_price_per_1m,
        valid_from=valid_from or datetime(2026, 1, 1, tzinfo=UTC),
        valid_until=valid_until,
        enabled=enabled,
    )


def _fx_rate(
    *,
    base_currency: str = "USD",
    quote_currency: str = "EUR",
    rate: Decimal = Decimal("0.920000000"),
    valid_from: datetime | None = None,
    valid_until: datetime | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        base_currency=base_currency,
        quote_currency=quote_currency,
        rate=rate,
        valid_from=valid_from or datetime(2026, 1, 1, tzinfo=UTC),
        valid_until=valid_until,
    )


def _service(
    *,
    pricing_rows: list[SimpleNamespace] | None = None,
    fx_rows: list[SimpleNamespace] | None = None,
) -> PricingService:
    return PricingService(
        pricing_rules_repository=FakePricingRulesRepository(pricing_rows or []),
        fx_rates_repository=FakeFxRatesRepository(fx_rows or []),
    )


def _route(*, requested_model: str = "classroom-cheap", resolved_model: str = "gpt-4.1-mini"):
    return RouteResolutionResult(
        requested_model=requested_model,
        resolved_model=resolved_model,
        provider="openai",
        route_id=uuid.uuid4(),
        route_match_type="exact",
        route_pattern=requested_model,
        priority=100,
    )


def _policy() -> ChatCompletionPolicyResult:
    return ChatCompletionPolicyResult(
        effective_body={"model": "classroom-cheap", "messages": [{"role": "user", "content": "hi"}]},
        requested_output_tokens=2000,
        effective_output_tokens=2000,
        estimated_input_tokens=1000,
        injected_default_output_tokens=False,
    )


@pytest.mark.asyncio
async def test_pricing_lookup_finds_enabled_active_rule() -> None:
    at = datetime(2026, 4, 25, tzinfo=UTC)
    service = _service(pricing_rows=[_pricing_rule()])

    result = await service.find_active_pricing_rule(
        provider="openai",
        model="gpt-4.1-mini",
        endpoint="/v1/chat/completions",
        at=at,
    )

    assert result.provider == "openai"
    assert result.model == "gpt-4.1-mini"
    assert result.currency == "USD"
    assert isinstance(result.input_price_per_1m, Decimal)
    assert isinstance(result.output_price_per_1m, Decimal)


@pytest.mark.asyncio
async def test_pricing_lookup_ignores_disabled_rules() -> None:
    service = _service(pricing_rows=[_pricing_rule(enabled=False)])

    with pytest.raises(PricingRuleNotFoundError):
        await service.find_active_pricing_rule(
            provider="openai",
            model="gpt-4.1-mini",
            endpoint="/v1/chat/completions",
            at=datetime(2026, 4, 25, tzinfo=UTC),
        )


@pytest.mark.asyncio
async def test_pricing_lookup_respects_validity_window() -> None:
    service = _service(
        pricing_rows=[
            _pricing_rule(
                valid_from=datetime(2026, 1, 1, tzinfo=UTC),
                valid_until=datetime(2026, 2, 1, tzinfo=UTC),
            )
        ]
    )

    with pytest.raises(PricingRuleNotFoundError):
        await service.find_active_pricing_rule(
            provider="openai",
            model="gpt-4.1-mini",
            endpoint="/v1/chat/completions",
            at=datetime(2026, 4, 25, tzinfo=UTC),
        )


@pytest.mark.asyncio
async def test_pricing_lookup_raises_when_missing() -> None:
    service = _service()

    with pytest.raises(PricingRuleNotFoundError):
        await service.find_active_pricing_rule(
            provider="openai",
            model="gpt-4.1-mini",
            endpoint="/v1/chat/completions",
            at=datetime(2026, 4, 25, tzinfo=UTC),
        )


@pytest.mark.asyncio
async def test_invalid_missing_pricing_data_fails() -> None:
    service = _service(pricing_rows=[_pricing_rule(input_price_per_1m=None)])

    with pytest.raises(InvalidPricingDataError):
        await service.find_active_pricing_rule(
            provider="openai",
            model="gpt-4.1-mini",
            endpoint="/v1/chat/completions",
            at=datetime(2026, 4, 25, tzinfo=UTC),
        )


@pytest.mark.asyncio
async def test_invalid_negative_pricing_data_fails() -> None:
    service = _service(pricing_rows=[_pricing_rule(output_price_per_1m=Decimal("-0.1"))])

    with pytest.raises(InvalidPricingDataError):
        await service.find_active_pricing_rule(
            provider="openai",
            model="gpt-4.1-mini",
            endpoint="/v1/chat/completions",
            at=datetime(2026, 4, 25, tzinfo=UTC),
        )


@pytest.mark.asyncio
async def test_eur_amount_returns_unchanged_without_rate_row() -> None:
    service = _service()
    amount = Decimal("1.230000001")

    converted, fx = await service.convert_to_eur(amount, "EUR")

    assert converted == amount
    assert fx.rate == Decimal("1")
    assert fx.fx_rate_id is None


@pytest.mark.asyncio
async def test_native_currency_converts_using_fx_rate() -> None:
    service = _service(fx_rows=[_fx_rate(rate=Decimal("0.920000000"))])

    converted, fx = await service.convert_to_eur(
        Decimal("2.500000000"),
        "USD",
        at=datetime(2026, 4, 25, tzinfo=UTC),
    )

    assert converted == Decimal("2.300000000000000000")
    assert fx.from_currency == "USD"
    assert fx.to_currency == "EUR"


@pytest.mark.asyncio
async def test_missing_fx_rate_raises() -> None:
    service = _service()

    with pytest.raises(FxRateNotFoundError):
        await service.convert_to_eur(Decimal("1"), "USD")


@pytest.mark.asyncio
@pytest.mark.parametrize("rate", [Decimal("0"), Decimal("-0.920000000")])
async def test_invalid_zero_or_negative_fx_rate_fails(rate: Decimal) -> None:
    service = _service(fx_rows=[_fx_rate(rate=rate)])

    with pytest.raises(InvalidFxRateError):
        await service.convert_to_eur(
            Decimal("1"),
            "USD",
            at=datetime(2026, 4, 25, tzinfo=UTC),
        )


@pytest.mark.asyncio
async def test_cost_estimate_calculates_native_and_eur_totals() -> None:
    service = _service(
        pricing_rows=[
            _pricing_rule(
                upstream_model="gpt-4.1-mini",
                input_price_per_1m=Decimal("0.150000000"),
                cached_input_price_per_1m=Decimal("0.010000000"),
                output_price_per_1m=Decimal("0.600000000"),
            )
        ],
        fx_rows=[_fx_rate(rate=Decimal("0.920000000"))],
    )

    estimate = await service.estimate_chat_completion_cost(
        route=_route(requested_model="classroom-cheap", resolved_model="gpt-4.1-mini"),
        policy=_policy(),
        at=datetime(2026, 4, 25, tzinfo=UTC),
    )

    assert estimate.requested_model == "classroom-cheap"
    assert estimate.resolved_model == "gpt-4.1-mini"
    assert estimate.estimated_input_tokens == 1000
    assert estimate.estimated_output_tokens == 2000
    assert estimate.estimated_input_cost_native == Decimal("0.000150000000")
    assert estimate.estimated_output_cost_native == Decimal("0.001200000000")
    assert estimate.estimated_total_cost_native == Decimal("0.001350000000")
    assert estimate.estimated_total_cost_eur == Decimal("0.001242000000000000000")


@pytest.mark.asyncio
async def test_cost_estimate_default_endpoint_uses_chat_completions_pricing_row() -> None:
    service = _service(pricing_rows=[_pricing_rule(currency="EUR")])

    estimate = await service.estimate_chat_completion_cost(
        route=_route(),
        policy=_policy(),
        at=datetime(2026, 4, 25, tzinfo=UTC),
    )

    assert estimate.pricing_rule_id is not None


@pytest.mark.asyncio
async def test_cost_estimate_assumes_uncached_input_for_max_cost() -> None:
    service = _service(
        pricing_rows=[
            _pricing_rule(
                input_price_per_1m=Decimal("2.000000000"),
                cached_input_price_per_1m=Decimal("0.010000000"),
                output_price_per_1m=Decimal("0.000000000"),
            )
        ],
        fx_rows=[_fx_rate()],
    )

    estimate = await service.estimate_chat_completion_cost(
        route=_route(),
        policy=_policy(),
        at=datetime(2026, 4, 25, tzinfo=UTC),
    )

    assert estimate.native_currency == "USD"
    assert estimate.estimated_input_cost_native == Decimal("0.002000000000")


@pytest.mark.asyncio
async def test_cost_estimate_uses_resolved_model_for_pricing_lookup() -> None:
    service = _service(
        pricing_rows=[
            _pricing_rule(upstream_model="gpt-4.1-mini"),
            _pricing_rule(upstream_model="classroom-cheap", input_price_per_1m=Decimal("9")),
        ],
        fx_rows=[_fx_rate()],
    )

    estimate = await service.estimate_chat_completion_cost(
        route=_route(requested_model="classroom-cheap", resolved_model="gpt-4.1-mini"),
        policy=_policy(),
        at=datetime(2026, 4, 25, tzinfo=UTC),
    )

    assert estimate.resolved_model == "gpt-4.1-mini"
    assert estimate.estimated_input_cost_native == Decimal("0.000150000000")


@pytest.mark.asyncio
async def test_cost_estimate_does_not_mutate_policy_or_route_objects() -> None:
    service = _service(pricing_rows=[_pricing_rule()], fx_rows=[_fx_rate()])
    route = _route()
    policy = _policy()
    route_before = deepcopy(route)
    policy_before = policy.model_copy(deep=True)

    await service.estimate_chat_completion_cost(
        route=route,
        policy=policy,
        at=datetime(2026, 4, 25, tzinfo=UTC),
    )

    assert route == route_before
    assert policy == policy_before


def test_pricing_service_safety_constraints() -> None:
    import slaif_gateway.services.pricing as module

    source = inspect.getsource(module)
    import_lines = [
        line.strip().lower()
        for line in source.splitlines()
        if line.strip().startswith(("import ", "from "))
    ]

    for disallowed in (
        "openai",
        "openrouter",
        "httpx",
        "aiosmtplib",
        "celery",
        "fastapi",
        "usage_ledger",
        "accounting",
        "create_async_engine",
        "get_sessionmaker",
    ):
        assert not any(disallowed in line for line in import_lines)

    assert ".commit(" not in source
    assert "reserve" not in source.lower()
