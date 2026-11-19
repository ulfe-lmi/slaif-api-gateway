"""Real pricing, reservation and settlement follow the normalized wire budget."""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from slaif_gateway.db.models import QuotaReservation, UsageLedger
from slaif_gateway.db.repositories.fx_rates import FxRatesRepository
from slaif_gateway.db.repositories.pricing import PricingRulesRepository
from slaif_gateway.schemas.providers import ProviderResponse, ProviderUsage
from slaif_gateway.services.accounting import AccountingService
from slaif_gateway.services.pricing import PricingService
from tests.integration.test_quota_reservation_postgres import (
    _authenticated_key,
    _create_gateway_key,
    _route,
    _service,
)
from tests.unit.test_output_token_budget_policy import KINDS, budget_case


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("requested", [None, 5, 1000000])
async def test_wire_limit_price_and_postgres_reservation_agree(async_test_session, kind, requested):
    session = async_test_session
    key = await _create_gateway_key(session)
    policy, forwarded, expected = budget_case(kind, requested)
    choices = 3 if kind == "chat_choices" else 1
    assert forwarded == expected
    aggregate = forwarded * choices
    key.token_limit_total = policy.estimated_input_tokens + aggregate
    await session.flush()
    endpoint = (
        "/v1/realtime/client_secrets"
        if kind == "realtime"
        else "/v1/chat/completions"
        if kind.startswith("chat")
        else "/v1/responses"
    )
    route = _route()
    now = datetime.now(UTC)
    pricing = PricingRulesRepository(session)
    await pricing.create_pricing_rule(
        provider=route.provider,
        upstream_model=route.resolved_model,
        endpoint=endpoint,
        valid_from=now - timedelta(seconds=10),
        currency="EUR",
        input_price_per_1m=Decimal(1),
        cached_input_price_per_1m=Decimal(1),
        output_price_per_1m=Decimal(2),
        reasoning_price_per_1m=Decimal(2),
        pricing_metadata={
            "codex_accounting": {
                "cache_write_input_price_per_1m": "1",
                "long_context_threshold_tokens": 10000,
                "long_context_input_multiplier": "1",
                "long_context_output_multiplier": "1",
            }
        },
    )
    estimator = PricingService(
        pricing_rules_repository=pricing, fx_rates_repository=FxRatesRepository(session)
    )
    method = (
        estimator.estimate_realtime_client_secret_cost
        if kind == "realtime"
        else estimator.estimate_chat_completion_cost
    )
    estimate = await method(route=route, policy=policy, endpoint=endpoint)
    assert estimate.estimated_output_tokens == aggregate
    expected_cost = (Decimal(policy.estimated_input_tokens) + Decimal(2 * aggregate)) / Decimal(
        1000000
    )
    assert estimate.estimated_total_cost_eur == expected_cost
    request_id = "budget-" + uuid.uuid4().hex
    quota = _service(session)
    reservation = await quota.reserve_for_chat_completion(
        authenticated_key=_authenticated_key(key),
        route=route,
        policy=policy,
        cost_estimate=estimate,
        request_id=request_id,
        endpoint=endpoint,
    )
    row = await session.get(QuotaReservation, reservation.reservation_id)
    await session.refresh(key)
    assert (
        row.reserved_tokens
        == key.tokens_reserved_total
        == policy.estimated_input_tokens + aggregate
    )
    assert row.reserved_cost_eur == key.cost_reserved_eur == expected_cost
    if kind == "realtime":
        # This endpoint meters admission only; do not claim actual-session usage.
        await quota.release_reservation(reservation.reservation_id)
    else:
        actual = ProviderResponse(
            provider=route.provider,
            upstream_model=route.resolved_model,
            status_code=200,
            json_body={"id": "synthetic-budget-response"},
            usage=ProviderUsage(prompt_tokens=3, completion_tokens=2, total_tokens=5),
        )
        await AccountingService(session).finalize_successful_response(
            reservation.reservation_id,
            _authenticated_key(key),
            route,
            policy,
            estimate,
            actual,
            request_id,
            endpoint=endpoint,
        )
        ledger = (
            await session.execute(select(UsageLedger).where(UsageLedger.request_id == request_id))
        ).scalar_one()
        assert ledger.success and ledger.accounting_status == "finalized"
        assert ledger.input_tokens == 3 and ledger.output_tokens == 2 and ledger.total_tokens == 5
        assert ledger.actual_cost_eur == Decimal("0.000007")
        await session.refresh(key)
        assert key.tokens_used_total == 5 and key.cost_used_eur == Decimal("0.000007")
    await session.refresh(key)
    assert key.tokens_reserved_total == 0 and key.cost_reserved_eur == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["compact", "codex_compact"])
async def test_compact_default_reservation_does_not_expand_to_route_maximum(
    async_test_session, kind
):
    session = async_test_session
    key = await _create_gateway_key(session)
    policy, forwarded, expected = budget_case(kind, None)
    assert forwarded is None and expected == 8
    # A reservation made from the route maximum (60) would fail this quota;
    # the configured compact default must fit and be the actual DB exposure.
    key.token_limit_total = policy.estimated_input_tokens + expected
    await session.flush()
    from tests.integration.test_quota_reservation_postgres import _estimate

    reservation = await _service(session).reserve_for_chat_completion(
        authenticated_key=_authenticated_key(key),
        route=_route(),
        policy=policy,
        cost_estimate=_estimate(
            cost=Decimal("0.01"), input_tokens=policy.estimated_input_tokens, output_tokens=expected
        ),
        request_id="compact-budget-" + uuid.uuid4().hex,
        endpoint="/v1/responses/compact",
    )
    row = await session.get(QuotaReservation, reservation.reservation_id)
    assert row.reserved_tokens == policy.estimated_input_tokens + expected
