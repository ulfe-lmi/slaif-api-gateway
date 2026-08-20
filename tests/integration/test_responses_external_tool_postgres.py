"""PostgreSQL evidence for bounded Responses web-search accounting."""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from slaif_gateway.db.models import ModelRoute, UsageLedger
from slaif_gateway.db.repositories.audit import AuditRepository
from slaif_gateway.db.repositories.keys import GatewayKeysRepository
from slaif_gateway.db.repositories.owners import OwnersRepository
from slaif_gateway.db.repositories.quota import QuotaReservationsRepository
from slaif_gateway.db.repositories.usage import UsageLedgerRepository
from slaif_gateway.schemas.external_tool_fence import (
    ExternalToolFenceAcquireInput,
    ExternalToolFenceRouteFacts,
)
from slaif_gateway.schemas.auth import AuthenticatedGatewayKey
from slaif_gateway.schemas.pricing import ExternalToolPricing, FxConversionResult
from slaif_gateway.schemas.providers import ProviderResponse, ProviderStreamChunk, ProviderUsage
from slaif_gateway.providers.errors import ProviderError
from slaif_gateway.schemas.routing import RouteResolutionResult
from slaif_gateway.services.responses_gateway import _RateLimitReservation
from slaif_gateway.main import create_app
from slaif_gateway.schemas.external_tool_hold import (
    ExternalToolAccountingHoldInput,
    ExternalToolHoldEvidenceQuality,
    ExternalToolHoldReasonCode,
)
from slaif_gateway.services.external_tool_fence import ExternalToolFenceService
from slaif_gateway.services.external_tool_hold import ExternalToolAccountingHoldService
from slaif_gateway.services.external_tool_policy_contract import ExternalToolAdmissionDecision

pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL is not set; skipping Responses external-tool PostgreSQL tests.",
)


def _decision() -> ExternalToolAdmissionDecision:
    return ExternalToolAdmissionDecision(
        allowed=True,
        quota_mode="external_tool_fenced",
        effective_tool_call_cap=2,
        reason_code="external_tool_fenced_allowed",
        exclusive_key_fence_required=True,
        single_request_overrun_accepted=True,
        hold_on_missing_or_ambiguous_final_cost=True,
        following_requests_block_after_exhaustion=True,
    )


async def _create_key(session: AsyncSession):
    owner = await OwnersRepository(session).create_owner(
        name="Responses",
        surname="Web Search",
        email=f"responses-web-search-{uuid.uuid4().hex}@example.test",
    )
    policy = {
        "version": 1,
        "mode": "external_tool_fenced",
        "allowed_capabilities": ["provider_web_search"],
        "allowed_destination_ids": [],
        "max_provider_tool_calls_per_request": 2,
        "single_request_overrun_acknowledged": True,
    }
    return await GatewayKeysRepository(session).create_gateway_key_record(
        public_key_id=f"responses_{uuid.uuid4().hex}",
        token_hash=f"hash-{uuid.uuid4().hex}",
        owner_id=owner.id,
        valid_from=datetime.now(UTC) - timedelta(minutes=1),
        valid_until=datetime.now(UTC) + timedelta(hours=1),
        cost_limit_eur=Decimal("5.000000000"),
        token_limit_total=1000,
        request_limit_total=3,
        allow_all_models=True,
        allow_all_endpoints=True,
        metadata_json={"external_tool_policy": policy},
    )


def _authenticated_key(key) -> AuthenticatedGatewayKey:
    return AuthenticatedGatewayKey(
        gateway_key_id=key.id,
        owner_id=key.owner_id,
        cohort_id=None,
        public_key_id=key.public_key_id,
        status=key.status,
        valid_from=key.valid_from,
        valid_until=key.valid_until,
        allow_all_models=True,
        allowed_models=(),
        allow_all_endpoints=True,
        allowed_endpoints=(),
        allowed_providers=None,
        cost_limit_eur=key.cost_limit_eur,
        token_limit_total=key.token_limit_total,
        request_limit_total=key.request_limit_total,
        rate_limit_policy={},
        responses_policy={},
        key_purpose="standard",
        capability_policy_mode="standard",
        external_tool_policy=key.metadata_json["external_tool_policy"],
    )


def _route(route_row: ModelRoute) -> RouteResolutionResult:
    return RouteResolutionResult(
        requested_model=route_row.requested_model,
        resolved_model=route_row.upstream_model,
        provider=route_row.provider,
        route_id=route_row.id,
        route_match_type="exact",
        route_pattern=route_row.requested_model,
        priority=route_row.priority,
        capabilities={
            "external_tools": {
                "version": 1,
                "supported_capabilities": ["provider_web_search"],
                "approved_destination_ids": [],
                "max_provider_tool_calls_per_request": 2,
                "call_limit_enforced": True,
                "final_usage_required": True,
                "final_cost_required": True,
            },
            "responses": {
                "text": True,
                "stateless": True,
                "streaming": True,
                "tools": True,
            },
        },
    )


def _provider_response(*, usage: bool = True, malformed: bool = False) -> ProviderResponse:
    output = [] if malformed else [
        {
            "type": "web_search_call",
            "id": "call-canary-id",
            "status": "completed",
            "action": {"type": "search", "query": "query-canary"},
        }
    ]
    return ProviderResponse(
        provider="openai",
        upstream_model="gpt-4.1-mini",
        status_code=200,
        json_body={
            "id": "resp-canary-id",
            "object": "response",
            "status": "completed",
            "output": output,
            "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
        },
        usage=(ProviderUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15) if usage else None),
    )


def _stream_chunk(payload: dict[str, object], *, usage: ProviderUsage | None = None) -> ProviderStreamChunk:
    return ProviderStreamChunk(
        provider="openai",
        upstream_model="gpt-4.1-mini",
        data="event",
        raw_sse_event=f"data: {payload}\n\n",
        json_body=payload,
        usage=usage,
        upstream_request_id="upstream-stream-canary",
    )


async def _gateway_client(
    monkeypatch,
    async_test_session,
    key,
    route_row,
    *,
    provider_response,
    model_price: Decimal = Decimal("1000"),
):
    import slaif_gateway.api.dependencies as dependencies
    import slaif_gateway.services.responses_gateway as gateway
    import slaif_gateway.services.pricing as pricing_module

    app = create_app()
    authenticated = _authenticated_key(key)
    app.dependency_overrides[dependencies.get_authenticated_gateway_key] = (
        lambda: authenticated
    )

    async def session_iterator(*_args, **_kwargs):
        yield async_test_session

    monkeypatch.setattr(gateway, "_get_db_session_after_auth_header_check", session_iterator)
    monkeypatch.setattr(dependencies, "_get_db_session_after_auth_header_check", session_iterator)
    async def resolve_model(self, requested_model, authenticated_key, endpoint="/v1/chat/completions"):
        _ = (self, requested_model, authenticated_key, endpoint)
        return _route(route_row)

    monkeypatch.setattr(gateway.RouteResolutionService, "resolve_model", resolve_model)
    external_pricing = ExternalToolPricing(
        currency="EUR", unit_price_native=Decimal("0.01"), source="openai_published_per_call"
    )
    pricing_row = SimpleNamespace(
        currency="EUR",
        input_price_per_1m=model_price,
        output_price_per_1m=model_price,
        cached_input_price_per_1m=None,
        reasoning_price_per_1m=None,
        audio_output_price_per_1m=None,
        request_price=None,
        cache_write_input_price_per_1m=None,
        cache_write_input_multiplier=None,
        long_context_threshold_tokens=None,
        long_context_input_multiplier=None,
        long_context_output_multiplier=None,
        pricing_rule_id=None,
        external_tool_pricing=external_pricing,
    )
    async def find_active(self, **_kwargs):
        return pricing_row

    async def convert_to_eur(self, amount, native_currency, at=None):
        _ = (amount, native_currency, at)
        return amount, FxConversionResult("EUR", "EUR", Decimal("1"), None)

    monkeypatch.setattr(pricing_module.PricingService, "find_active_pricing_rule", find_active)
    monkeypatch.setattr(pricing_module.PricingService, "convert_to_eur", convert_to_eur)

    class Adapter:
        async def forward_response(self, request):
            assert request.body["tools"] == [{"type": "web_search"}]
            assert request.body["max_tool_calls"] == 1
            assert "query-canary" not in str(request.body)
            if isinstance(provider_response, Exception):
                raise provider_response
            return provider_response

        async def stream_response(self, request):
            _ = request
            for chunk in getattr(provider_response, "stream_chunks", ()):
                yield chunk

    monkeypatch.setattr(gateway, "get_provider_adapter", lambda route, settings: Adapter())
    released = []
    redis_requests = []

    async def reserve_redis(**kwargs):
        redis_requests.append(kwargs["request_id"])
        return _RateLimitReservation(
            service=SimpleNamespace(),
            policy=SimpleNamespace(),
            gateway_key_id=key.id,
            request_id=kwargs["request_id"],
            concurrency_reserved=False,
        )

    async def release_redis(reservation, *, suppress):
        _ = suppress
        released.append(reservation.request_id)

    monkeypatch.setattr(gateway, "_reserve_redis_rate_limit", reserve_redis)
    monkeypatch.setattr(gateway, "_release_rate_limit_concurrency", release_redis)
    return app, httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test"), released


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["provider", "missing_usage", "malformed_output"])
async def test_gateway_post_start_failures_create_one_full_hold(
    async_test_session: AsyncSession,
    monkeypatch,
    failure: str,
) -> None:
    key = await _create_key(async_test_session)
    route_row = ModelRoute(
        requested_model=f"gpt-responses-web-search-hold-{failure}",
        match_type="exact",
        endpoint="/v1/responses",
        provider="openai",
        upstream_model="gpt-4.1-mini",
    )
    async_test_session.add(route_row)
    await async_test_session.flush()
    if failure == "provider":
        response_value = ProviderError(
            "Provider failure canary", provider="openai", error_code="provider_request_error"
        )
    elif failure == "missing_usage":
        response_value = _provider_response(usage=False)
    else:
        response_value = _provider_response(malformed=True)
    app, client, released = await _gateway_client(
        monkeypatch, async_test_session, key, route_row, provider_response=response_value
    )
    async with client:
        response = await client.post(
            "/v1/responses",
            json={
                "model": route_row.requested_model,
                "input": "hello",
                "store": False,
                "tools": [{"type": "web_search"}],
                "tool_choice": "auto",
                "max_tool_calls": 1,
            },
        )
    assert response.status_code >= 400
    assert "canary" not in response.text.lower()
    await async_test_session.refresh(key)
    assert key.external_tool_fence_state == "held"
    assert key.cost_reserved_eur == Decimal("5.000000000")
    assert key.tokens_reserved_total == 1000
    ledgers = await UsageLedgerRepository(async_test_session).get_usage_records_by_reservation_id(
        key.external_tool_fence_reservation_id
    )
    assert len(ledgers) == 1
    assert ledgers[0].streaming is False
    assert "canary" not in repr(ledgers[0].response_metadata).lower()
    assert len(released) == 1


@pytest.mark.asyncio
async def test_gateway_overrun_then_ordinary_and_hosted_admission_fail(
    async_test_session: AsyncSession,
    monkeypatch,
) -> None:
    key = await _create_key(async_test_session)
    route_row = ModelRoute(
        requested_model="gpt-responses-web-search-overrun",
        match_type="exact",
        endpoint="/v1/responses",
        provider="openai",
        upstream_model="gpt-4.1-mini",
    )
    async_test_session.add(route_row)
    await async_test_session.flush()
    app, client, released = await _gateway_client(
        monkeypatch,
        async_test_session,
        key,
        route_row,
        provider_response=_provider_response(),
        model_price=Decimal("500000"),
    )
    body = {
        "model": route_row.requested_model,
        "input": "hello",
        "store": False,
        "tools": [{"type": "web_search"}],
        "tool_choice": "auto",
        "max_tool_calls": 1,
    }
    async with client:
        first = await client.post("/v1/responses", json=body)
        ordinary = await client.post(
            "/v1/responses",
            json={"model": route_row.requested_model, "input": "ordinary", "store": False},
        )
        hosted_again = await client.post("/v1/responses", json=body)
    assert first.status_code == 200, first.text
    assert ordinary.status_code in {400, 409, 429}
    assert hosted_again.status_code in {400, 409, 429}
    assert len(released) == 3
    await async_test_session.refresh(key)
    assert key.external_tool_fence_state == "none"
    assert key.cost_used_eur > key.cost_limit_eur
    ledgers = list(
        (
            await async_test_session.execute(
                select(UsageLedger).where(UsageLedger.gateway_key_id == key.id)
            )
        ).scalars()
    )
    assert len(ledgers) == 1


@pytest.mark.asyncio
async def test_gateway_hosted_stream_withholds_terminal_and_finalizes_content_free(
    async_test_session: AsyncSession,
    monkeypatch,
) -> None:
    key = await _create_key(async_test_session)
    route_row = ModelRoute(
        requested_model="gpt-responses-web-search-stream",
        match_type="exact",
        endpoint="/v1/responses",
        provider="openai",
        upstream_model="gpt-4.1-mini",
    )
    async_test_session.add(route_row)
    await async_test_session.flush()
    usage = ProviderUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15)
    chunks = (
        _stream_chunk({"type": "response.created", "sequence_number": 0}),
        _stream_chunk({"type": "response.output_text.delta", "delta": "safe text"}),
        _stream_chunk(
            {
                "type": "response.web_search_call.completed",
                "item_id": "call-stream-canary",
                "output_index": 0,
                "sequence_number": 1,
            }
        ),
        _stream_chunk(
            {
                "type": "response.output_item.done",
                "output_index": 0,
                "sequence_number": 2,
                "item": {
                    "type": "web_search_call",
                    "id": "call-stream-canary",
                    "status": "completed",
                    "action": {"type": "search", "query": "stream-query-canary"},
                },
            }
        ),
        _stream_chunk(
            {
                "type": "response.completed",
                "sequence_number": 3,
                "response": {
                    "status": "completed",
                    "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
                },
            },
            usage=usage,
        ),
        ProviderStreamChunk(
            provider="openai",
            upstream_model="gpt-4.1-mini",
            data="[DONE]",
            raw_sse_event="data: [DONE]\n\n",
            is_done=True,
            upstream_request_id="upstream-stream-canary",
        ),
    )
    app, client, released = await _gateway_client(
        monkeypatch,
        async_test_session,
        key,
        route_row,
        provider_response=SimpleNamespace(stream_chunks=chunks),
    )
    async with client:
        response = await client.post(
            "/v1/responses",
            json={
                "model": route_row.requested_model,
                "input": "hello",
                "store": False,
                "stream": True,
                "tools": [{"type": "web_search"}],
                "tool_choice": "auto",
                "max_tool_calls": 1,
            },
        )
    assert response.status_code == 200, response.text
    assert "stream-query-canary" in response.text
    await async_test_session.refresh(key)
    assert key.external_tool_fence_state == "none"
    all_ledgers = list(
        (
            await async_test_session.execute(
                select(UsageLedger).where(UsageLedger.gateway_key_id == key.id)
            )
        ).scalars()
    )
    assert len(all_ledgers) == 1
    assert all_ledgers[0].streaming is True
    assert "stream-query-canary" not in repr(all_ledgers[0].response_metadata)
    assert released


@pytest.mark.asyncio
async def test_gateway_malformed_hosted_stream_creates_streaming_hold(
    async_test_session: AsyncSession,
    monkeypatch,
) -> None:
    key = await _create_key(async_test_session)
    route_row = ModelRoute(
        requested_model="gpt-responses-web-search-stream-malformed",
        match_type="exact",
        endpoint="/v1/responses",
        provider="openai",
        upstream_model="gpt-4.1-mini",
    )
    async_test_session.add(route_row)
    await async_test_session.flush()
    chunks = (
        _stream_chunk({"type": "response.web_search_call.completed", "item_id": "stream-id", "output_index": 0, "sequence_number": 1}),
        _stream_chunk(
            {
                "type": "response.output_item.done",
                "output_index": 0,
                "sequence_number": 2,
                "item": {
                    "type": "web_search_call",
                    "id": "stream-id",
                    "status": "completed",
                    "action": {"type": "forbidden-action", "query": "bad-canary"},
                },
            }
        ),
    )
    app, client, released = await _gateway_client(
        monkeypatch,
        async_test_session,
        key,
        route_row,
        provider_response=SimpleNamespace(stream_chunks=chunks),
    )
    async with client:
        response = await client.post(
            "/v1/responses",
            json={
                "model": route_row.requested_model,
                "input": "hello",
                "store": False,
                "stream": True,
                "tools": [{"type": "web_search"}],
                "tool_choice": "auto",
                "max_tool_calls": 1,
            },
        )
    assert response.status_code == 200
    assert "[DONE]" not in response.text
    assert "bad-canary" not in response.text
    await async_test_session.refresh(key)
    assert key.external_tool_fence_state == "held"
    ledgers = await UsageLedgerRepository(async_test_session).get_usage_records_by_reservation_id(
        key.external_tool_fence_reservation_id
    )
    assert len(ledgers) == 1
    assert ledgers[0].streaming is True
    assert released


@pytest.mark.asyncio
async def test_gateway_same_key_fence_blocks_without_provider_work(
    async_test_session: AsyncSession,
    monkeypatch,
) -> None:
    key = await _create_key(async_test_session)
    route_row = ModelRoute(
        requested_model="gpt-responses-web-search-concurrent",
        match_type="exact",
        endpoint="/v1/responses",
        provider="openai",
        upstream_model="gpt-4.1-mini",
    )
    async_test_session.add(route_row)
    await async_test_session.flush()
    fence = ExternalToolFenceService(
        gateway_keys_repository=GatewayKeysRepository(async_test_session),
        quota_reservations_repository=QuotaReservationsRepository(async_test_session),
        usage_ledger_repository=UsageLedgerRepository(async_test_session),
        audit_repository=AuditRepository(async_test_session),
    )
    await fence.acquire(
        ExternalToolFenceAcquireInput(
            gateway_key_id=key.id,
            request_id="blocking-request",
            route=ExternalToolFenceRouteFacts(
                endpoint="/v1/responses",
                requested_model=route_row.requested_model,
                provider="openai",
                route_id=route_row.id,
            ),
            capabilities=("provider_web_search",),
            destination_ids=(),
            decision=_decision(),
            now=datetime.now(UTC),
        )
    )
    app, client, released = await _gateway_client(
        monkeypatch, async_test_session, key, route_row, provider_response=_provider_response()
    )
    async with client:
        response = await client.post(
            "/v1/responses",
            json={
                "model": route_row.requested_model,
                "input": "hello",
                "store": False,
                "tools": [{"type": "web_search"}],
                "tool_choice": "auto",
                "max_tool_calls": 1,
            },
        )
    assert response.status_code == 409
    assert "blocking-request" not in response.text
    assert len(released) == 1


@pytest.mark.asyncio
async def test_gateway_allowed_success_is_atomic_and_content_free(
    async_test_session: AsyncSession,
    monkeypatch,
) -> None:
    key = await _create_key(async_test_session)
    route_row = ModelRoute(
        requested_model="gpt-responses-web-search-gateway",
        match_type="exact",
        endpoint="/v1/responses",
        provider="openai",
        upstream_model="gpt-4.1-mini",
    )
    async_test_session.add(route_row)
    await async_test_session.flush()
    app, client, released = await _gateway_client(
        monkeypatch,
        async_test_session,
        key,
        route_row,
        provider_response=_provider_response(),
    )
    async with client:
        response = await client.post(
            "/v1/responses",
            json={
                "model": route_row.requested_model,
                "input": "hello",
                "store": False,
                "tools": [{"type": "web_search"}],
                "tool_choice": "auto",
                "max_tool_calls": 1,
            },
        )
    assert response.status_code == 200, response.text
    await async_test_session.refresh(key)
    assert key.external_tool_fence_state == "none"
    assert key.cost_reserved_eur == Decimal("0")
    assert key.tokens_reserved_total == 0
    assert key.requests_reserved_total == 0
    ledgers = list(
        (
            await async_test_session.execute(
                select(UsageLedger).where(UsageLedger.gateway_key_id == key.id)
            )
        ).scalars()
    )
    assert len(ledgers) == 1
    assert ledgers[0].response_metadata["external_tool_completed_call_count"] == 1
    assert "query-canary" not in repr(ledgers[0].response_metadata)
    audits = await AuditRepository(async_test_session).list_audit_logs_for_admin(
        target_id=key.id, limit=20
    )
    assert audits
    assert all("canary" not in repr(audit.__dict__).lower() for audit in audits)
    assert released == [ledgers[0].request_id]


@pytest.mark.asyncio
async def test_web_search_fence_and_hold_are_content_free(
    async_test_session: AsyncSession,
) -> None:
    key = await _create_key(async_test_session)
    route_row = ModelRoute(
        requested_model="gpt-responses-web-search-test",
        match_type="exact",
        endpoint="/v1/responses",
        provider="openai",
        upstream_model="gpt-4.1-mini",
    )
    async_test_session.add(route_row)
    await async_test_session.flush()
    fence = ExternalToolFenceService(
        gateway_keys_repository=GatewayKeysRepository(async_test_session),
        quota_reservations_repository=QuotaReservationsRepository(async_test_session),
        usage_ledger_repository=UsageLedgerRepository(async_test_session),
        audit_repository=AuditRepository(async_test_session),
    )
    acquired = await fence.acquire(
        ExternalToolFenceAcquireInput(
            gateway_key_id=key.id,
            request_id=f"responses-web-search-{uuid.uuid4().hex}",
            route=ExternalToolFenceRouteFacts(
                endpoint="/v1/responses",
                requested_model="gpt-responses-web-search-test",
                provider="openai",
                route_id=route_row.id,
            ),
            capabilities=("provider_web_search",),
            destination_ids=(),
            decision=_decision(),
            now=datetime.now(UTC),
        )
    )
    assert acquired.fence_state == "active"
    assert acquired.reserved_cost_eur == Decimal("5.000000000")
    assert acquired.reserved_tokens == 1000
    assert acquired.reserved_requests == 1

    await async_test_session.refresh(key)
    assert key.external_tool_fence_state == "active"
    assert key.cost_reserved_eur == Decimal("5.000000000")
    assert key.tokens_reserved_total == 1000
    assert key.requests_reserved_total == 1

    hold = await ExternalToolAccountingHoldService(
        gateway_keys_repository=GatewayKeysRepository(async_test_session),
        quota_reservations_repository=QuotaReservationsRepository(async_test_session),
        usage_ledger_repository=UsageLedgerRepository(async_test_session),
        audit_repository=AuditRepository(async_test_session),
    ).place(
        ExternalToolAccountingHoldInput(
            gateway_key_id=key.id,
            reservation_id=acquired.reservation_id,
            request_id=acquired.request_id,
            reason_code=ExternalToolHoldReasonCode.MISSING_FINAL_USAGE,
            evidence_quality=ExternalToolHoldEvidenceQuality.MISSING,
            streaming=True,
            now=datetime.now(UTC),
        )
    )
    assert hold.fence_state == "held"
    ledgers = await UsageLedgerRepository(async_test_session).get_usage_records_by_reservation_id(
        acquired.reservation_id
    )
    assert len(ledgers) == 1
    assert ledgers[0].usage_raw == {}
    assert "external_tool_accounting_hold" in ledgers[0].response_metadata
    assert "content" not in ledgers[0].response_metadata
    assert "arguments" not in ledgers[0].response_metadata
    assert "results" not in ledgers[0].response_metadata
