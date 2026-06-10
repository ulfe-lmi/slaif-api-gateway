from __future__ import annotations

import inspect
import uuid
from copy import deepcopy
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from slaif_gateway.schemas.audio import AudioPolicyResult
from slaif_gateway.schemas.embeddings import EmbeddingsPolicyResult
from slaif_gateway.schemas.policy import ChatCompletionPolicyResult
from slaif_gateway.schemas.realtime import RealtimePolicyResult
from slaif_gateway.schemas.routing import RouteResolutionResult
from slaif_gateway.services.pricing import PricingService
from slaif_gateway.services.pricing_errors import (
    AudioOutputPricingNotSupportedError,
    AudioRequestPricingNotSupportedError,
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
    request_price: Decimal | None = None,
    pricing_metadata: dict[str, object] | None = None,
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
        request_price=request_price,
        pricing_metadata=pricing_metadata or {},
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
    assert estimate.input_price_per_1m == Decimal("0.150000000")
    assert estimate.cached_input_price_per_1m == Decimal("0.010000000")
    assert estimate.output_price_per_1m == Decimal("0.600000000")
    assert estimate.fx_rate == Decimal("0.920000000")


@pytest.mark.asyncio
async def test_cost_estimate_uses_total_policy_input_tokens_with_non_message_fields() -> None:
    service = _service(
        pricing_rows=[
            _pricing_rule(
                upstream_model="gpt-4.1-mini",
                currency="EUR",
                input_price_per_1m=Decimal("1.000000000"),
                output_price_per_1m=Decimal("0.000000000"),
            )
        ],
    )
    policy = ChatCompletionPolicyResult(
        effective_body={
            "model": "classroom-cheap",
            "messages": [{"role": "user", "content": "hi"}],
            "response_format": {"type": "json_schema", "json_schema": {"schema": {}}},
        },
        requested_output_tokens=10,
        effective_output_tokens=10,
        estimated_input_tokens=1500,
        estimated_message_input_tokens=25,
        estimated_non_message_input_tokens=1475,
        estimated_non_message_input_bytes=1475,
        estimated_non_message_input_fields=("response_format",),
        injected_default_output_tokens=False,
    )

    estimate = await service.estimate_chat_completion_cost(
        route=_route(requested_model="classroom-cheap", resolved_model="gpt-4.1-mini"),
        policy=policy,
        at=datetime(2026, 4, 25, tzinfo=UTC),
    )

    assert estimate.estimated_input_tokens == 1500
    assert estimate.estimated_input_cost_native == Decimal("0.001500000000")


@pytest.mark.asyncio
async def test_cost_estimate_uses_choice_aware_output_tokens_without_multiplying_input() -> None:
    service = _service(
        pricing_rows=[
            _pricing_rule(
                upstream_model="gpt-4.1-mini",
                currency="EUR",
                input_price_per_1m=Decimal("1.000000000"),
                output_price_per_1m=Decimal("2.000000000"),
            )
        ],
    )
    policy = ChatCompletionPolicyResult(
        effective_body={
            "model": "classroom-cheap",
            "messages": [{"role": "user", "content": "hi"}],
            "max_completion_tokens": 10,
            "n": 3,
        },
        requested_output_tokens=10,
        effective_output_tokens=30,
        effective_output_tokens_per_choice=10,
        effective_choice_count=3,
        estimated_input_tokens=100,
        injected_default_output_tokens=False,
    )

    estimate = await service.estimate_chat_completion_cost(
        route=_route(requested_model="classroom-cheap", resolved_model="gpt-4.1-mini"),
        policy=policy,
        at=datetime(2026, 4, 25, tzinfo=UTC),
    )

    assert estimate.estimated_input_tokens == 100
    assert estimate.estimated_output_tokens == 30
    assert estimate.estimated_input_cost_native == Decimal("0.000100000000")
    assert estimate.estimated_output_cost_native == Decimal("0.000060000000")


@pytest.mark.asyncio
async def test_audio_output_estimate_requires_explicit_audio_output_pricing_metadata() -> None:
    service = _service(pricing_rows=[_pricing_rule(currency="EUR")])
    policy = ChatCompletionPolicyResult(
        effective_body={
            "model": "classroom-cheap",
            "messages": [{"role": "user", "content": "say hi"}],
            "modalities": ["text", "audio"],
            "audio": {"format": "wav", "voice": "alloy"},
        },
        requested_output_tokens=20,
        effective_output_tokens=20,
        estimated_input_tokens=100,
        injected_default_output_tokens=False,
    )

    with pytest.raises(AudioOutputPricingNotSupportedError) as exc_info:
        await service.estimate_chat_completion_cost(
            route=_route(requested_model="classroom-cheap", resolved_model="gpt-4.1-mini"),
            policy=policy,
            at=datetime(2026, 4, 25, tzinfo=UTC),
        )

    assert exc_info.value.error_code == "chat_audio_output_pricing_not_supported"
    assert exc_info.value.param == "audio"


@pytest.mark.asyncio
async def test_audio_output_estimate_uses_explicit_audio_output_price_for_reservation() -> None:
    service = _service(
        pricing_rows=[
            _pricing_rule(
                currency="EUR",
                input_price_per_1m=Decimal("1.000000000"),
                output_price_per_1m=Decimal("2.000000000"),
                pricing_metadata={"audio_output_price_per_1m": "64.000000000"},
            )
        ],
    )
    policy = ChatCompletionPolicyResult(
        effective_body={
            "model": "classroom-cheap",
            "messages": [{"role": "user", "content": "say hi"}],
            "modalities": ["text", "audio"],
            "audio": {"format": "wav", "voice": "alloy"},
        },
        requested_output_tokens=20,
        effective_output_tokens=20,
        estimated_input_tokens=100,
        injected_default_output_tokens=False,
    )

    estimate = await service.estimate_chat_completion_cost(
        route=_route(requested_model="classroom-cheap", resolved_model="gpt-4.1-mini"),
        policy=policy,
        at=datetime(2026, 4, 25, tzinfo=UTC),
    )

    assert estimate.audio_output_price_per_1m == Decimal("64.000000000")
    assert estimate.estimated_input_cost_native == Decimal("0.000100000000")
    assert estimate.estimated_output_cost_native == Decimal("0.001280000000")


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


@pytest.mark.asyncio
async def test_audio_speech_estimate_uses_request_price_when_configured() -> None:
    service = _service(
        pricing_rows=[
            _pricing_rule(
                upstream_model="tts-1",
                endpoint="/v1/audio/speech",
                input_price_per_1m=Decimal("1.000000000"),
                output_price_per_1m=Decimal("0.000000000"),
                request_price=Decimal("0.020000000"),
            )
        ],
        fx_rows=[_fx_rate()],
    )

    estimate = await service.estimate_audio_operation_cost(
        route=_route(requested_model="classroom-audio", resolved_model="tts-1"),
        policy=AudioPolicyResult(
            effective_body={"model": "classroom-audio", "input": "hello", "voice": "alloy"},
            estimated_input_tokens=12,
        ),
        endpoint="/v1/audio/speech",
        at=datetime(2026, 4, 25, tzinfo=UTC),
    )

    assert estimate.request_price == Decimal("0.020000000")
    assert estimate.estimated_total_cost_native == Decimal("0.020000000")


@pytest.mark.asyncio
async def test_audio_transcription_requires_request_pricing_without_usage_model() -> None:
    service = _service(
        pricing_rows=[
            _pricing_rule(
                upstream_model="whisper-1",
                endpoint="/v1/audio/transcriptions",
                input_price_per_1m=Decimal("1.000000000"),
                output_price_per_1m=Decimal("0.000000000"),
                request_price=None,
            )
        ],
        fx_rows=[_fx_rate()],
    )

    with pytest.raises(AudioRequestPricingNotSupportedError):
        await service.estimate_audio_operation_cost(
            route=_route(requested_model="classroom-audio", resolved_model="whisper-1"),
            policy=AudioPolicyResult(
                effective_body={"model": "classroom-audio"},
                estimated_input_tokens=120,
                uploaded_file_bytes=1024,
            ),
            endpoint="/v1/audio/transcriptions",
            at=datetime(2026, 4, 25, tzinfo=UTC),
        )


@pytest.mark.asyncio
async def test_audio_speech_can_fallback_to_input_pricing_without_request_price() -> None:
    service = _service(
        pricing_rows=[
            _pricing_rule(
                upstream_model="tts-1",
                endpoint="/v1/audio/speech",
                input_price_per_1m=Decimal("2.000000000"),
                output_price_per_1m=Decimal("0.000000000"),
            )
        ],
        fx_rows=[_fx_rate()],
    )

    estimate = await service.estimate_audio_operation_cost(
        route=_route(requested_model="classroom-audio", resolved_model="tts-1"),
        policy=AudioPolicyResult(
            effective_body={"model": "classroom-audio", "input": "hello", "voice": "alloy"},
            estimated_input_tokens=10,
        ),
        endpoint="/v1/audio/speech",
        at=datetime(2026, 4, 25, tzinfo=UTC),
    )

    assert estimate.request_price is None
    assert estimate.estimated_input_cost_native == Decimal("0.000020000000")


@pytest.mark.asyncio
async def test_embeddings_estimate_uses_input_pricing_only() -> None:
    service = _service(
        pricing_rows=[
            _pricing_rule(
                upstream_model="text-embedding-3-small",
                endpoint="/v1/embeddings",
                input_price_per_1m=Decimal("0.100000000"),
                cached_input_price_per_1m=Decimal("0.050000000"),
                output_price_per_1m=Decimal("0.000000000"),
            )
        ],
        fx_rows=[_fx_rate()],
    )

    estimate = await service.estimate_embeddings_cost(
        route=_route(
            requested_model="classroom-embedding",
            resolved_model="text-embedding-3-small",
        ),
        policy=EmbeddingsPolicyResult(
            effective_body={"model": "classroom-embedding", "input": ["hello", "world"]},
            estimated_input_tokens=12,
        ),
        endpoint="/v1/embeddings",
        at=datetime(2026, 4, 25, tzinfo=UTC),
    )

    assert estimate.request_price is None
    assert estimate.estimated_input_tokens == 12
    assert estimate.estimated_output_tokens == 0
    assert estimate.estimated_input_cost_native == Decimal("0.000001200000")
    assert estimate.estimated_total_cost_native == Decimal("0.000001200000")


@pytest.mark.asyncio
async def test_embeddings_estimate_requires_pricing_rule() -> None:
    service = _service(fx_rows=[_fx_rate()])

    with pytest.raises(PricingRuleNotFoundError):
        await service.estimate_embeddings_cost(
            route=_route(
                requested_model="classroom-embedding",
                resolved_model="text-embedding-3-small",
            ),
            policy=EmbeddingsPolicyResult(
                effective_body={"model": "classroom-embedding", "input": "hello"},
                estimated_input_tokens=4,
            ),
            endpoint="/v1/embeddings",
            at=datetime(2026, 4, 25, tzinfo=UTC),
        )


@pytest.mark.asyncio
async def test_embeddings_estimate_requires_fx_rate_for_non_eur_pricing() -> None:
    service = _service(
        pricing_rows=[
            _pricing_rule(
                upstream_model="text-embedding-3-small",
                endpoint="/v1/embeddings",
                currency="USD",
                input_price_per_1m=Decimal("0.100000000"),
                output_price_per_1m=Decimal("0.000000000"),
            )
        ],
        fx_rows=[],
    )

    with pytest.raises(FxRateNotFoundError):
        await service.estimate_embeddings_cost(
            route=_route(
                requested_model="classroom-embedding",
                resolved_model="text-embedding-3-small",
            ),
            policy=EmbeddingsPolicyResult(
                effective_body={"model": "classroom-embedding", "input": "hello"},
                estimated_input_tokens=4,
            ),
            endpoint="/v1/embeddings",
            at=datetime(2026, 4, 25, tzinfo=UTC),
        )


@pytest.mark.asyncio
async def test_realtime_client_secret_estimate_uses_higher_of_token_and_request_pricing() -> None:
    service = _service(
        pricing_rows=[
            _pricing_rule(
                upstream_model="gpt-realtime-mini",
                endpoint="/v1/realtime/client_secrets",
                currency="EUR",
                input_price_per_1m=Decimal("1.000000000"),
                output_price_per_1m=Decimal("2.000000000"),
                request_price=Decimal("0.005000000"),
            )
        ]
    )

    estimate = await service.estimate_realtime_client_secret_cost(
        route=_route(
            requested_model="classroom-realtime",
            resolved_model="gpt-realtime-mini",
        ),
        policy=RealtimePolicyResult(
            effective_body={"session": {"model": "classroom-realtime", "type": "realtime"}},
            estimated_input_tokens=100,
            effective_output_tokens=200,
        ),
        endpoint="/v1/realtime/client_secrets",
        at=datetime(2026, 4, 25, tzinfo=UTC),
    )

    assert estimate.request_price == Decimal("0.005000000")
    assert estimate.estimated_total_cost_native == Decimal("0.005000000")
    assert estimate.estimated_output_tokens == 200


@pytest.mark.asyncio
async def test_realtime_client_secret_estimate_requires_fx_rate_for_non_eur_pricing() -> None:
    service = _service(
        pricing_rows=[
            _pricing_rule(
                upstream_model="gpt-realtime-mini",
                endpoint="/v1/realtime/client_secrets",
                currency="USD",
                input_price_per_1m=Decimal("1.000000000"),
                output_price_per_1m=Decimal("2.000000000"),
                request_price=Decimal("0.005000000"),
            )
        ],
        fx_rows=[],
    )

    with pytest.raises(FxRateNotFoundError):
        await service.estimate_realtime_client_secret_cost(
            route=_route(
                requested_model="classroom-realtime",
                resolved_model="gpt-realtime-mini",
            ),
            policy=RealtimePolicyResult(
                effective_body={"session": {"model": "classroom-realtime", "type": "realtime"}},
                estimated_input_tokens=100,
                effective_output_tokens=200,
            ),
            endpoint="/v1/realtime/client_secrets",
            at=datetime(2026, 4, 25, tzinfo=UTC),
        )
