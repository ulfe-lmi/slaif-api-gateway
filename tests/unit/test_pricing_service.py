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
from slaif_gateway.schemas.policy import (
    ChatCompletionPolicyResult,
    ResponsesPolicyResult,
)
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
    RealtimeClientSecretPricingNotSupportedError,
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


def _route(
    *,
    requested_model: str = "classroom-cheap",
    resolved_model: str = "gpt-4.1-mini",
    provider: str = "openai",
    provider_kind: str | None = None,
):
    return RouteResolutionResult(
        requested_model=requested_model,
        resolved_model=resolved_model,
        provider=provider,
        route_id=uuid.uuid4(),
        route_match_type="exact",
        route_pattern=requested_model,
        priority=100,
        provider_kind=provider_kind,
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
async def test_realtime_client_secret_admission_pricing_requires_request_price() -> None:
    service = _service(
        pricing_rows=[
            _pricing_rule(
                upstream_model="gpt-realtime-mini",
                endpoint="/v1/realtime/client_secrets",
                currency="EUR",
                input_price_per_1m=Decimal("1.000000000"),
                output_price_per_1m=Decimal("2.000000000"),
                request_price=None,
            )
        ]
    )

    with pytest.raises(RealtimeClientSecretPricingNotSupportedError):
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
            admission_pricing_only=True,
            at=datetime(2026, 4, 25, tzinfo=UTC),
        )


@pytest.mark.asyncio
async def test_realtime_client_secret_admission_pricing_uses_request_price_only() -> None:
    service = _service(
        pricing_rows=[
            _pricing_rule(
                upstream_model="gpt-realtime-mini",
                endpoint="/v1/realtime/client_secrets",
                currency="EUR",
                input_price_per_1m=Decimal("10.000000000"),
                output_price_per_1m=Decimal("20.000000000"),
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
        admission_pricing_only=True,
        at=datetime(2026, 4, 25, tzinfo=UTC),
    )

    assert estimate.request_price == Decimal("0.005000000")
    assert estimate.estimated_total_cost_native == Decimal("0.005000000")
    assert estimate.estimated_input_cost_native == Decimal("0")
    assert estimate.estimated_output_cost_native == Decimal("0")


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


@pytest.mark.asyncio
async def test_module_chat_fixed_request_pricing_is_zero_token_and_exact_zero_cost() -> None:
    service = _service(
        pricing_rows=[
            _pricing_rule(
                provider="test-module",
                upstream_model="module-score-v1",
                currency="EUR",
                request_price=Decimal("0"),
                input_price_per_1m=Decimal("99"),
                output_price_per_1m=Decimal("99"),
            )
        ]
    )

    estimate = await service.estimate_chat_completion_cost(
        route=_route(
            requested_model="module-score",
            resolved_model="module-score-v1",
            provider="test-module",
            provider_kind="module",
        ),
        policy=ChatCompletionPolicyResult(
            effective_body={
                "model": "module-score",
                "messages": [{"role": "user", "content": "bounded input"}],
                "max_completion_tokens": 4096,
            },
            requested_output_tokens=4096,
            effective_output_tokens=4096,
            estimated_input_tokens=128,
            injected_default_output_tokens=False,
        ),
        endpoint="chat.completions",
        at=datetime(2026, 4, 25, tzinfo=UTC),
    )

    assert estimate.estimated_input_tokens == 0
    assert estimate.estimated_output_tokens == 0
    assert estimate.estimated_total_cost_native == Decimal("0")
    assert estimate.estimated_total_cost_eur == Decimal("0")


@pytest.mark.asyncio
async def test_module_chat_fixed_request_pricing_requires_request_price() -> None:
    service = _service(
        pricing_rows=[
            _pricing_rule(
                provider="test-module",
                upstream_model="module-score-v1",
                currency="EUR",
                request_price=None,
            )
        ]
    )

    with pytest.raises(InvalidPricingDataError, match="request price"):
        await service.estimate_chat_completion_cost(
            route=_route(
                requested_model="module-score",
                resolved_model="module-score-v1",
                provider="test-module",
                provider_kind="module",
            ),
            policy=_policy(),
            endpoint="chat.completions",
            at=datetime(2026, 4, 25, tzinfo=UTC),
        )

# ---------------------------------------------------------------------------
# Objective 182-b B2: compact capture/estimate matrix over the real shared
# pricing seam (capture_pricing_and_fx + family estimates) with USD FX and
# EUR identity: Chat, strict Responses/Codex, Audio, Embeddings, Realtime,
# fixed-request module billing, missing-rate fail-closed, and hosted
# Responses pre-fence facts/reuse.
# ---------------------------------------------------------------------------

B2_AT = datetime(2026, 5, 1, tzinfo=UTC)
B2_USD_INPUT = Decimal("0.270000000")
B2_USD_OUTPUT = Decimal("1.080000000")
B2_USD_FX = Decimal("0.925925926")
B2_EUR_INPUT = Decimal("0.250000000")
B2_EUR_OUTPUT = Decimal("1.000000000")


class B2PricingRulesRepository(FakePricingRulesRepository):
    """Pair-capture fake mirroring the real one-statement repository
    semantics, counting capture versus single-row lookups."""

    def __init__(
        self, rows: list[SimpleNamespace], fx_rows: list[SimpleNamespace]
    ) -> None:
        super().__init__(rows)
        self._fx_rows = list(fx_rows)
        self.pair_calls = 0
        self.single_calls = 0

    async def find_active_pricing_rule(self, **kwargs: object) -> SimpleNamespace | None:
        self.single_calls += 1
        return await super().find_active_pricing_rule(**kwargs)  # type: ignore[arg-type]

    async def find_active_pricing_rule_with_fx(
        self,
        *,
        provider: str,
        upstream_model: str,
        endpoint: str,
        at_time: datetime,
    ) -> tuple[SimpleNamespace | None, SimpleNamespace | None]:
        self.pair_calls += 1
        row = await super().find_active_pricing_rule(
            provider=provider,
            upstream_model=upstream_model,
            endpoint=endpoint,
            at_time=at_time,
        )
        if row is None:
            return None, None
        if row.currency == "EUR":
            return row, None
        fx_rows = [
            fx
            for fx in self._fx_rows
            if fx.base_currency == row.currency
            and fx.quote_currency == "EUR"
            and fx.valid_from <= at_time
            and (fx.valid_until is None or fx.valid_until > at_time)
        ]
        fx_rows.sort(key=lambda fx: fx.valid_from, reverse=True)
        return row, (fx_rows[0] if fx_rows else None)


def _b2_service(repo: B2PricingRulesRepository) -> PricingService:
    return PricingService(
        pricing_rules_repository=repo,
        fx_rates_repository=FakeFxRatesRepository(repo._fx_rows),
    )


@pytest.mark.asyncio
async def test_b2_capture_estimate_chat_carries_usd_fx_pair_ids() -> None:
    row = _pricing_rule(
        currency="USD",
        input_price_per_1m=B2_USD_INPUT,
        output_price_per_1m=B2_USD_OUTPUT,
    )
    fx = _fx_rate(base_currency="USD", quote_currency="EUR", rate=B2_USD_FX)
    repo = B2PricingRulesRepository([row], [fx])
    service = _b2_service(repo)

    capture = await service.capture_pricing_and_fx(
        provider="openai", model="gpt-4.1-mini", endpoint="/v1/chat/completions"
    )
    estimate = await service.estimate_chat_completion_cost(
        route=_route(),
        policy=_policy(),
        endpoint="/v1/chat/completions",
        pricing=capture.pricing,
        fx=capture.fx,
    )

    assert repo.pair_calls == 1
    assert repo.single_calls == 0  # no extra price/FX lookup for the estimate
    assert capture.pricing.pricing_rule_id == row.id
    assert capture.fx.fx_rate_id == fx.id
    assert estimate.pricing_rule_id == row.id
    assert estimate.fx_rate_id == fx.id
    assert estimate.native_currency == "USD"
    assert estimate.fx_rate == B2_USD_FX
    expected_native = (
        B2_USD_INPUT * Decimal(1000) + B2_USD_OUTPUT * Decimal(2000)
    ) / Decimal(10**6)
    assert estimate.estimated_total_cost_native == expected_native
    assert estimate.estimated_total_cost_eur == expected_native * B2_USD_FX


@pytest.mark.asyncio
async def test_b2_capture_estimate_chat_eur_identity_needs_no_fx_row() -> None:
    row = _pricing_rule(
        currency="EUR",
        input_price_per_1m=B2_EUR_INPUT,
        output_price_per_1m=B2_EUR_OUTPUT,
    )
    repo = B2PricingRulesRepository([row], [])
    service = _b2_service(repo)

    capture = await service.capture_pricing_and_fx(
        provider="openai", model="gpt-4.1-mini", endpoint="/v1/chat/completions"
    )
    estimate = await service.estimate_chat_completion_cost(
        route=_route(),
        policy=_policy(),
        endpoint="/v1/chat/completions",
        pricing=capture.pricing,
        fx=capture.fx,
    )

    assert capture.fx.fx_rate_id is None
    assert capture.fx.rate == Decimal("1")
    assert estimate.fx_rate_id is None
    assert estimate.pricing_rule_id == row.id
    assert estimate.estimated_total_cost_eur == estimate.estimated_total_cost_native
    assert repo.pair_calls == 1
    assert repo.single_calls == 0


@pytest.mark.asyncio
async def test_b2_capture_usd_without_fx_rate_fails_closed() -> None:
    row = _pricing_rule(
        currency="USD",
        input_price_per_1m=B2_USD_INPUT,
        output_price_per_1m=B2_USD_OUTPUT,
    )
    repo = B2PricingRulesRepository([row], [])
    service = _b2_service(repo)

    with pytest.raises(FxRateNotFoundError):
        await service.capture_pricing_and_fx(
            provider="openai", model="gpt-4.1-mini", endpoint="/v1/chat/completions"
        )
    assert repo.pair_calls == 1


@pytest.mark.asyncio
async def test_b2_capture_estimate_responses_codex_strict_complete_metadata() -> None:
    codex_row = _pricing_rule(
        currency="USD",
        input_price_per_1m=B2_USD_INPUT,
        output_price_per_1m=B2_USD_OUTPUT,
        cached_input_price_per_1m=Decimal("0.027000000"),
        reasoning_price_per_1m=Decimal("0.216000000"),
        pricing_metadata={
            "codex_accounting": {
                "long_context_threshold_tokens": 1050000,
                "long_context_input_multiplier": "1.75",
                "long_context_output_multiplier": "2.0",
                "cache_write_input_price_per_1m": "0.0000003375",
            }
        },
    )
    fx = _fx_rate(base_currency="USD", quote_currency="EUR", rate=B2_USD_FX)
    repo = B2PricingRulesRepository([codex_row], [fx])
    service = _b2_service(repo)
    codex_policy = ResponsesPolicyResult(
        effective_body={"model": "classroom-responses", "input": "hi"},
        requested_output_tokens=2000,
        effective_output_tokens=2000,
        injected_default_output_tokens=False,
        estimated_input_tokens=1000,
        codex_limits_applied=True,
    )

    capture = await service.capture_pricing_and_fx(
        provider="openai", model="gpt-4.1-mini", endpoint="/v1/chat/completions"
    )
    estimate = await service.estimate_chat_completion_cost(
        route=_route(),
        policy=codex_policy,
        endpoint="/v1/chat/completions",
        pricing=capture.pricing,
        fx=capture.fx,
    )

    assert estimate.codex_accounting is True
    assert estimate.pricing_rule_id == codex_row.id
    assert estimate.fx_rate_id == fx.id
    input_price = max(B2_USD_INPUT, Decimal("0.0000003375")) * Decimal("1.75")
    output_price = max(B2_USD_OUTPUT, Decimal("0.216000000")) * Decimal("2.0")
    expected_native = (
        Decimal(1000) * input_price + Decimal(2000) * output_price
    ) / Decimal(10**6)
    assert estimate.estimated_total_cost_native == expected_native
    assert estimate.estimated_total_cost_eur == expected_native * B2_USD_FX

    # strict: the same codex policy against a row WITHOUT complete metadata
    # fails closed instead of inventing cache/long-context prices
    bare_row = _pricing_rule(
        currency="USD",
        input_price_per_1m=B2_USD_INPUT,
        output_price_per_1m=B2_USD_OUTPUT,
    )
    bare_repo = B2PricingRulesRepository([bare_row], [fx])
    bare_service = _b2_service(bare_repo)
    bare_capture = await bare_service.capture_pricing_and_fx(
        provider="openai", model="gpt-4.1-mini", endpoint="/v1/chat/completions"
    )
    with pytest.raises(InvalidPricingDataError):
        await bare_service.estimate_chat_completion_cost(
            route=_route(),
            policy=codex_policy,
            endpoint="/v1/chat/completions",
            pricing=bare_capture.pricing,
            fx=bare_capture.fx,
        )


@pytest.mark.asyncio
async def test_b2_capture_estimate_audio_speech_carries_pair_ids() -> None:
    row = _pricing_rule(
        provider="openai",
        upstream_model="tts-1",
        endpoint="/v1/audio/speech",
        currency="USD",
        input_price_per_1m=B2_USD_INPUT,
        output_price_per_1m=B2_USD_OUTPUT,
        request_price=Decimal("0.004000000"),
    )
    fx = _fx_rate(base_currency="USD", quote_currency="EUR", rate=B2_USD_FX)
    repo = B2PricingRulesRepository([row], [fx])
    service = _b2_service(repo)

    capture = await service.capture_pricing_and_fx(
        provider="openai", model="tts-1", endpoint="/v1/audio/speech"
    )
    estimate = await service.estimate_audio_operation_cost(
        route=_route(requested_model="classroom-audio", resolved_model="tts-1"),
        policy=AudioPolicyResult(
            effective_body={"model": "classroom-audio", "input": "hi", "voice": "alloy"},
            estimated_input_tokens=100,
        ),
        endpoint="/v1/audio/speech",
        pricing=capture.pricing,
        fx=capture.fx,
    )

    assert estimate.pricing_rule_id == row.id
    assert estimate.fx_rate_id == fx.id
    assert estimate.native_currency == "USD"
    # fixed request price dominates token-based pricing
    assert estimate.estimated_total_cost_native == Decimal("0.004000000")
    assert estimate.estimated_total_cost_eur == Decimal("0.004000000") * B2_USD_FX
    assert repo.pair_calls == 1
    assert repo.single_calls == 0


@pytest.mark.asyncio
async def test_b2_capture_estimate_embeddings_carries_pair_ids() -> None:
    row = _pricing_rule(
        provider="openai",
        upstream_model="text-embedding-3-small",
        endpoint="/v1/embeddings",
        currency="USD",
        input_price_per_1m=Decimal("0.020000000"),
        output_price_per_1m=Decimal("0"),
    )
    fx = _fx_rate(base_currency="USD", quote_currency="EUR", rate=B2_USD_FX)
    repo = B2PricingRulesRepository([row], [fx])
    service = _b2_service(repo)

    capture = await service.capture_pricing_and_fx(
        provider="openai",
        model="text-embedding-3-small",
        endpoint="/v1/embeddings",
    )
    estimate = await service.estimate_embeddings_cost(
        route=_route(
            requested_model="classroom-embedding",
            resolved_model="text-embedding-3-small",
        ),
        policy=EmbeddingsPolicyResult(
            effective_body={"model": "classroom-embedding", "input": ["a", "b"]},
            estimated_input_tokens=8,
        ),
        endpoint="/v1/embeddings",
        pricing=capture.pricing,
        fx=capture.fx,
    )

    assert estimate.pricing_rule_id == row.id
    assert estimate.fx_rate_id == fx.id
    expected_native = Decimal(8) * Decimal("0.020000000") / Decimal(10**6)
    assert estimate.estimated_total_cost_native == expected_native
    assert estimate.estimated_total_cost_eur == expected_native * B2_USD_FX
    assert repo.pair_calls == 1
    assert repo.single_calls == 0


@pytest.mark.asyncio
async def test_b2_capture_estimate_realtime_carries_pair_ids() -> None:
    row = _pricing_rule(
        provider="openai",
        upstream_model="gpt-realtime-mini",
        endpoint="/v1/realtime/client_secrets",
        currency="USD",
        input_price_per_1m=Decimal("0.060000000"),
        output_price_per_1m=Decimal("0.240000000"),
        request_price=Decimal("0.001000000"),
    )
    fx = _fx_rate(base_currency="USD", quote_currency="EUR", rate=B2_USD_FX)
    repo = B2PricingRulesRepository([row], [fx])
    service = _b2_service(repo)

    capture = await service.capture_pricing_and_fx(
        provider="openai",
        model="gpt-realtime-mini",
        endpoint="/v1/realtime/client_secrets",
    )
    estimate = await service.estimate_realtime_client_secret_cost(
        route=_route(requested_model="classroom-realtime", resolved_model="gpt-realtime-mini"),
        policy=RealtimePolicyResult(
            effective_body={"model": "classroom-realtime"},
            estimated_input_tokens=1000,
            effective_output_tokens=2000,
        ),
        endpoint="/v1/realtime/client_secrets",
        pricing=capture.pricing,
        fx=capture.fx,
    )

    assert estimate.pricing_rule_id == row.id
    assert estimate.fx_rate_id == fx.id
    token_native = (
        Decimal(1000) * Decimal("0.060000000") + Decimal(2000) * Decimal("0.240000000")
    ) / Decimal(10**6)
    assert token_native < Decimal("0.001000000")
    assert estimate.estimated_total_cost_native == Decimal("0.001000000")
    assert estimate.estimated_total_cost_eur == Decimal("0.001000000") * B2_USD_FX
    assert repo.pair_calls == 1
    assert repo.single_calls == 0


@pytest.mark.asyncio
async def test_b2_capture_estimate_fixed_request_module_billing() -> None:
    row = _pricing_rule(
        provider="openai",
        upstream_model="module-model",
        endpoint="/v1/chat/completions",
        currency="USD",
        input_price_per_1m=Decimal("0"),
        output_price_per_1m=Decimal("0"),
        request_price=Decimal("0.002500000"),
    )
    fx = _fx_rate(base_currency="USD", quote_currency="EUR", rate=B2_USD_FX)
    repo = B2PricingRulesRepository([row], [fx])
    service = _b2_service(repo)

    capture = await service.capture_pricing_and_fx(
        provider="openai", model="module-model", endpoint="/v1/chat/completions"
    )
    estimate = await service.estimate_chat_completion_cost(
        route=_route(requested_model="facial", resolved_model="module-model", provider_kind="module"),
        policy=_policy(),
        endpoint="/v1/chat/completions",
        pricing=capture.pricing,
        fx=capture.fx,
    )

    assert estimate.estimated_input_tokens == 0
    assert estimate.estimated_output_tokens == 0
    assert estimate.estimated_total_cost_native == Decimal("0.002500000")
    assert estimate.estimated_total_cost_eur == Decimal("0.002500000") * B2_USD_FX
    assert estimate.pricing_rule_id == row.id
    assert estimate.fx_rate_id == fx.id
    assert repo.pair_calls == 1
    assert repo.single_calls == 0


@pytest.mark.asyncio
async def test_b2_capture_hosted_responses_external_tool_pricing_facts_reused() -> None:
    row = _pricing_rule(
        endpoint="/v1/responses",
        currency="USD",
        input_price_per_1m=B2_USD_INPUT,
        output_price_per_1m=B2_USD_OUTPUT,
        pricing_metadata={
            "external_tool_pricing": {
                "openai_web_search_call_price_native": "0.01",
                "source": "openai_published_per_call",
            }
        },
    )
    fx = _fx_rate(base_currency="USD", quote_currency="EUR", rate=B2_USD_FX)
    repo = B2PricingRulesRepository([row], [fx])
    service = _b2_service(repo)

    # the pre-fence capture parses the hosted-tool facts AND carries the
    # complete price/FX identity in one PricingCapture
    capture = await service.capture_pricing_and_fx(
        provider="openai", model="gpt-4.1-mini", endpoint="/v1/responses"
    )
    hosted = capture.pricing.external_tool_pricing
    assert hosted is not None
    assert hosted.currency == "USD"
    assert hosted.unit_price_native == Decimal("0.01")
    assert hosted.source == "openai_published_per_call"
    assert capture.pricing.pricing_rule_id == row.id
    assert capture.fx.fx_rate_id == fx.id

    # the estimate reuses the supplied capture: no further lookups, same IDs
    estimate = await service.estimate_chat_completion_cost(
        route=_route(requested_model="classroom-responses"),
        policy=ResponsesPolicyResult(
            effective_body={"model": "classroom-responses", "input": "hi"},
            requested_output_tokens=2000,
            effective_output_tokens=2000,
            injected_default_output_tokens=False,
            estimated_input_tokens=1000,
        ),
        endpoint="/v1/responses",
        pricing=capture.pricing,
        fx=capture.fx,
    )
    assert estimate.pricing_rule_id == row.id
    assert estimate.fx_rate_id == fx.id
    assert repo.pair_calls == 1
    assert repo.single_calls == 0
