"""Focused PostgreSQL accounting/privacy evidence for generic backends."""

from __future__ import annotations

import os
import uuid
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
import httpx
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy import func, inspect, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from slaif_gateway.db.models import GatewayKey, QuotaReservation, UsageLedger
from slaif_gateway.db.models import PricingRule
from slaif_gateway.db.repositories.keys import GatewayKeysRepository
from slaif_gateway.db.repositories.owners import OwnersRepository
from slaif_gateway.db.repositories.quota import QuotaReservationsRepository
from slaif_gateway.db.repositories.usage import UsageLedgerRepository
from slaif_gateway.schemas.auth import AuthenticatedGatewayKey
from slaif_gateway.schemas.policy import ChatCompletionPolicyResult
from slaif_gateway.schemas.pricing import ChatCostEstimate
from slaif_gateway.schemas.providers import ProviderResponse, ProviderUsage
from slaif_gateway.schemas.routing import RouteResolutionResult
from slaif_gateway.services.accounting import AccountingService
from slaif_gateway.services.quota_service import QuotaService
from slaif_gateway.main import create_app

pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL is required for generic conformance PostgreSQL tests.",
)


async def _create_key(session: AsyncSession):
    owner = await OwnersRepository(session).create_owner(
        name="Generic",
        surname="Conformance",
        email=f"generic-conformance-{uuid.uuid4()}@example.test",
    )
    now = datetime.now(UTC)
    return await GatewayKeysRepository(session).create_gateway_key_record(
        public_key_id=f"generic-{uuid.uuid4().hex}",
        token_hash=f"hmac-{uuid.uuid4().hex}",
        owner_id=owner.id,
        valid_from=now - timedelta(minutes=5),
        valid_until=now + timedelta(hours=1),
        cost_limit_eur=Decimal("1.000000000"),
        token_limit_total=1000,
        request_limit_total=5,
        allow_all_models=True,
        allow_all_endpoints=True,
    )


def _auth(row) -> AuthenticatedGatewayKey:
    return AuthenticatedGatewayKey(
        gateway_key_id=row.id,
        owner_id=row.owner_id,
        cohort_id=row.cohort_id,
        public_key_id=row.public_key_id,
        status=row.status,
        valid_from=row.valid_from,
        valid_until=row.valid_until,
        allow_all_models=True,
        allowed_models=(),
        allow_all_endpoints=True,
        allowed_endpoints=(),
        allowed_providers=None,
        cost_limit_eur=row.cost_limit_eur,
        token_limit_total=row.token_limit_total,
        request_limit_total=row.request_limit_total,
        rate_limit_policy={},
    )


def _route() -> RouteResolutionResult:
    return RouteResolutionResult(
        requested_model="public-qwen",
        resolved_model="qwen/a",
        provider="lan-qwen",
        route_id=uuid.uuid4(),
        route_match_type="exact",
        route_pattern="public-qwen",
        priority=100,
        provider_kind="openai_compatible",
    )


def _policy() -> ChatCompletionPolicyResult:
    return ChatCompletionPolicyResult(
        effective_body={
            "model": "public-qwen",
            "messages": [{"role": "user", "content": "PROMPT_SECRET"}],
            "max_completion_tokens": 20,
        },
        requested_output_tokens=20,
        effective_output_tokens=20,
        estimated_input_tokens=5,
        injected_default_output_tokens=False,
    )


def _estimate() -> ChatCostEstimate:
    return ChatCostEstimate(
        provider="lan-qwen",
        requested_model="public-qwen",
        resolved_model="qwen/a",
        native_currency="EUR",
        estimated_input_tokens=5,
        estimated_output_tokens=20,
        estimated_input_cost_native=Decimal("0.001000000"),
        estimated_output_cost_native=Decimal("0.002000000"),
        estimated_total_cost_native=Decimal("0.003000000"),
        estimated_total_cost_eur=Decimal("0.003000000"),
        pricing_rule_id=None,
        fx_rate_id=None,
    )


@pytest.mark.asyncio
async def test_generic_accounting_finalizes_once_with_route_identity_and_no_content(
    async_test_session: AsyncSession,
) -> None:
    key = await _create_key(async_test_session)
    route = _route()
    policy = _policy()
    estimate = _estimate()
    request_id = f"generic-conformance-{uuid.uuid4()}"
    reservation = await QuotaService(
        gateway_keys_repository=GatewayKeysRepository(async_test_session),
        quota_reservations_repository=QuotaReservationsRepository(async_test_session),
    ).reserve_for_chat_completion(
        authenticated_key=_auth(key),
        route=route,
        policy=policy,
        cost_estimate=estimate,
        request_id=request_id,
    )

    result = await AccountingService(async_test_session).finalize_successful_response(
        reservation.reservation_id,
        _auth(key),
        route,
        policy,
        estimate,
        ProviderResponse(
            provider="lan-qwen",
            upstream_model="qwen/a",
            status_code=200,
            json_body={"completion": "COMPLETION_SECRET", "image": "BASE64_SECRET"},
            upstream_request_id="generic-upstream-request",
            usage=ProviderUsage(prompt_tokens=5, completion_tokens=7, total_tokens=12),
        ),
        request_id=request_id,
    )

    assert result.accounting_status == "finalized"
    ledger = await UsageLedgerRepository(async_test_session).get_usage_record_by_request_id(request_id)
    reservation_row = await QuotaReservationsRepository(async_test_session).get_reservation_by_id(
        reservation.reservation_id
    )
    assert ledger is not None
    assert reservation_row is not None
    assert reservation_row.status == "finalized"
    assert ledger.provider == "lan-qwen"
    assert ledger.requested_model == "public-qwen"
    assert ledger.resolved_model == "qwen/a"
    assert ledger.endpoint == "/v1/chat/completions"
    assert ledger.accounting_status == "finalized"
    assert ledger.total_tokens == 12
    assert await async_test_session.scalar(
        select(func.count()).select_from(UsageLedger).where(UsageLedger.request_id == request_id)
    ) == 1
    assert await async_test_session.scalar(
        select(func.count())
        .select_from(QuotaReservation)
        .where(
            QuotaReservation.request_id == request_id,
            QuotaReservation.status == "pending",
        )
    ) == 0
    persisted = str(ledger.__dict__)
    assert all(secret not in persisted for secret in ("PROMPT_SECRET", "COMPLETION_SECRET", "BASE64_SECRET"))

    columns = await (await async_test_session.connection()).run_sync(
        lambda connection: {column["name"] for column in inspect(connection).get_columns("usage_ledger")}
    )
    assert "prompt_content" not in columns
    assert "completion_content" not in columns
    assert "raw_request" not in columns
    assert "raw_response" not in columns


@pytest.mark.asyncio
async def test_generic_gateway_chat_and_responses_execute_with_postgres_accounting(
    async_test_session: AsyncSession,
    migrated_postgres_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exercise both generic gateway routes through ASGI and durable accounting."""
    from slaif_gateway.api import dependencies
    from slaif_gateway.config import get_settings
    from slaif_gateway.db.repositories.provider_configs import ProviderConfigsRepository
    from slaif_gateway.db.repositories.routing import ModelRoutesRepository
    from slaif_gateway.providers.errors import ProviderError
    from slaif_gateway.schemas.providers import ProviderStreamChunk
    from slaif_gateway.services import chat_completion_gateway, responses_gateway
    from slaif_gateway.services.responses_route_capabilities import default_responses_capabilities

    provider = "lan-qwen-gateway"
    chat_model = "generic-chat-gateway"
    responses_model = "generic-responses-gateway"
    now = datetime.now(UTC)
    await ProviderConfigsRepository(async_test_session).create_provider_config(
        provider=provider,
        display_name="Generic gateway test provider",
        base_url="https://lan-qwen-gateway.example.test/v1",
        api_key_env_var="GENERIC_UPSTREAM_KEY",
        kind="openai_compatible",
    )
    routes = ModelRoutesRepository(async_test_session)
    await routes.create_model_route(
        requested_model=chat_model, provider=provider, upstream_model="qwen/chat",
        endpoint="/v1/chat/completions", capabilities={"chat_completions": {
            "chat_text": True, "chat_streaming": True, "chat_image_inputs": True,
            "chat_multimodal": False, "chat_function_tools": True,
        }},
    )
    responses_capabilities = default_responses_capabilities()
    responses_capabilities.update({"streaming": True, "image_input": True, "function_tools": True})
    await routes.create_model_route(
        requested_model=responses_model, provider=provider, upstream_model="qwen/responses",
        endpoint="/v1/responses", capabilities={"responses": responses_capabilities},
    )
    for model, endpoint in ((chat_model, "/v1/chat/completions"), (responses_model, "/v1/responses")):
        async_test_session.add(PricingRule(
            provider=provider, upstream_model=("qwen/chat" if model == chat_model else "qwen/responses"),
            endpoint=endpoint, valid_from=now - timedelta(days=1), currency="EUR",
            input_price_per_1m=Decimal("1.000000000"), output_price_per_1m=Decimal("2.000000000"),
            request_price=Decimal("0.000000000"), pricing_metadata={}, notes="generic gateway matrix",
        ))
    key = await _create_key(async_test_session)
    key_id = key.id
    key.token_limit_total = 1_000_000
    key.request_limit_total = 10
    await async_test_session.flush()
    auth_holder = {"value": _auth(key)}

    connection = await async_test_session.connection()
    factory = async_sessionmaker(bind=connection, expire_on_commit=False)
    app = create_app(get_settings())
    app.state.oap_test_session_factory = factory
    app.dependency_overrides[dependencies.get_authenticated_gateway_key] = lambda: auth_holder["value"]

    async def session_iterator(request=None, *_args, **_kwargs):
        _ = request
        async with factory() as session:
            yield session

    monkeypatch.setattr(chat_completion_gateway, "_get_db_session_after_auth_header_check", session_iterator)
    monkeypatch.setattr(responses_gateway, "_get_db_session_after_auth_header_check", session_iterator)
    calls: list[str] = []
    failure_mode = {"value": "success"}

    class Adapter:
        async def forward_chat_completion(self, request):
            calls.append(request.endpoint)
            if failure_mode["value"] == "provider":
                raise ProviderError("provider failure canary", provider=provider, error_code="provider_request_error")
            return ProviderResponse(
                provider=provider, upstream_model="qwen/chat", status_code=200,
                json_body={"id": "chat-gateway", "object": "chat.completion", "model": "qwen/chat",
                           "choices": [{"index": 0, "message": {"role": "assistant", "content": "safe"}, "finish_reason": "stop"}],
                           "usage": {"prompt_tokens": 5, "completion_tokens": 7, "total_tokens": 12}},
                usage=ProviderUsage(prompt_tokens=5, completion_tokens=7, total_tokens=12),
            )

        async def forward_response(self, request):
            calls.append(request.endpoint)
            return ProviderResponse(
                provider=provider, upstream_model="qwen/responses", status_code=200,
                json_body={"id": "resp-gateway", "object": "response", "status": "completed", "output": [],
                           "usage": {"input_tokens": 6, "output_tokens": 8, "total_tokens": 14}, "store": False},
                usage=ProviderUsage(prompt_tokens=6, completion_tokens=8, total_tokens=14),
            )

        async def stream_response(self, request):
            _ = request
            yield ProviderStreamChunk(
                provider=provider, upstream_model="qwen/responses", data="event",
                raw_sse_event='data: {"type":"response.completed"}\n\n',
                json_body={"type": "response.completed", "response": {"id": "resp-stream", "status": "completed", "output": [],
                    "usage": {"input_tokens": 3, "output_tokens": 4, "total_tokens": 7}}},
                usage=ProviderUsage(prompt_tokens=3, completion_tokens=4, total_tokens=7),
            )

    adapter = Adapter()
    monkeypatch.setattr(chat_completion_gateway, "get_provider_adapter", lambda route, settings: adapter)
    monkeypatch.setattr(responses_gateway, "get_provider_adapter", lambda route, settings: adapter)

    async def reserve_redis(**kwargs):
        return chat_completion_gateway._RateLimitReservation(
            service=object(), policy=object(), gateway_key_id=key.id,
            request_id=kwargs["request_id"], concurrency_reserved=False,
        )

    async def release_redis(*args, **kwargs):
        _ = (args, kwargs)

    monkeypatch.setattr(chat_completion_gateway, "_reserve_redis_rate_limit", reserve_redis)
    monkeypatch.setattr(chat_completion_gateway, "_release_rate_limit_concurrency", release_redis)
    monkeypatch.setattr(responses_gateway, "_reserve_redis_rate_limit", reserve_redis)
    monkeypatch.setattr(responses_gateway, "_release_rate_limit_concurrency", release_redis)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        chat_response = await client.post("/v1/chat/completions", headers={"Authorization": "Bearer gateway-test"}, json={
            "model": chat_model, "messages": [{"role": "user", "content": "CHAT_CANARY"}],
        })
        responses_response = await client.post("/v1/responses", headers={"Authorization": "Bearer gateway-test"}, json={
            "model": responses_model, "input": "RESPONSES_CANARY", "store": False,
        })
        remote_response = await client.post("/v1/chat/completions", headers={"Authorization": "Bearer gateway-test"}, json={
            "model": chat_model, "messages": [{"role": "user", "content": [{"type": "image_url", "image_url": {"url": "https://remote.test/canary"}}]}],
        })
        await async_test_session.execute(
            update(GatewayKey).where(GatewayKey.id == key_id).values(request_limit_total=2)
        )
        await async_test_session.flush()
        auth_holder["value"] = replace(auth_holder["value"], request_limit_total=2)
        exhausted_response = await client.post("/v1/chat/completions", headers={"Authorization": "Bearer gateway-test"}, json={
            "model": chat_model, "messages": [{"role": "user", "content": "QUOTA_CANARY"}],
        })
        await async_test_session.execute(
            update(GatewayKey).where(GatewayKey.id == key_id).values(request_limit_total=10)
        )
        await async_test_session.flush()
        auth_holder["value"] = replace(auth_holder["value"], request_limit_total=10)
        failure_mode["value"] = "provider"
        provider_failure_response = await client.post("/v1/chat/completions", headers={"Authorization": "Bearer gateway-test"}, json={
            "model": chat_model, "messages": [{"role": "user", "content": "PROVIDER_FAILURE_CANARY"}],
        })
    assert chat_response.status_code == 200, chat_response.text
    assert responses_response.status_code == 200, responses_response.text
    assert remote_response.status_code == 400
    assert exhausted_response.status_code == 429
    assert provider_failure_response.status_code >= 400
    assert calls == ["chat.completions", "responses", "chat.completions"]
    async_test_session.expire_all()
    rows = (await async_test_session.execute(select(UsageLedger).where(UsageLedger.gateway_key_id == key_id))).scalars().all()
    assert len(rows) == 3
    assert sum(row.accounting_status == "finalized" for row in rows) == 2
    assert sum(row.accounting_status != "finalized" for row in rows) == 1
    assert {row.provider for row in rows} == {provider}
    assert {row.accounting_status for row in rows} == {"finalized", "failed"}
    assert await async_test_session.scalar(select(func.count()).select_from(QuotaReservation).where(
        QuotaReservation.gateway_key_id == key_id, QuotaReservation.status == "pending")) == 0
