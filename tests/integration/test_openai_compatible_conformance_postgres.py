"""Focused PostgreSQL accounting/privacy evidence for generic backends."""

from __future__ import annotations

import os
import uuid
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
import httpx
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy import func, inspect, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from slaif_gateway.db.models import AuditLog, GatewayKey, QuotaReservation, UsageLedger
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
    zero_model = "generic-chat-local-zero"
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
    await routes.create_model_route(
        requested_model=zero_model, provider=provider, upstream_model="qwen/zero",
        endpoint="/v1/chat/completions", capabilities={"chat_completions": {
            "chat_text": True, "chat_streaming": False, "chat_image_inputs": True,
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
    async_test_session.add(PricingRule(
        provider=provider, upstream_model="qwen/zero", endpoint="/v1/chat/completions",
        valid_from=now - timedelta(days=1), currency="EUR",
        input_price_per_1m=Decimal("0.000000000"), output_price_per_1m=Decimal("0.000000000"),
        request_price=Decimal("0.000000000"),
        pricing_metadata={"pricing_basis": "operator_confirmed_local_zero"},
        notes="generic gateway local zero matrix",
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
            upstream_model = "qwen/zero" if request.upstream_model == "qwen/zero" else "qwen/chat"
            return ProviderResponse(
                provider=provider, upstream_model=upstream_model, status_code=200,
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
            if failure_mode["value"] == "missing":
                for payload in (
                    {"type": "response.created", "sequence_number": 0, "response": {
                        "id": "missing-usage", "object": "response", "created_at": 123,
                        "status": "in_progress", "model": "qwen/responses",
                    }},
                    {"type": "response.output_text.delta", "sequence_number": 1,
                     "item_id": "missing-item", "output_index": 0, "content_index": 0,
                     "delta": "MISSING_USAGE_CANARY"},
                    {"type": "response.completed", "sequence_number": 2, "response": {
                        "id": "missing-usage", "object": "response", "created_at": 123,
                        "status": "completed", "model": "qwen/responses", "output": [],
                    }},
                ):
                    yield ProviderStreamChunk(
                        provider=provider, upstream_model="qwen/responses", data="event",
                        raw_sse_event=f"data: {json.dumps(payload)}\n\n", json_body=payload,
                        usage=None,
                    )
                return
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
        zero_response = await client.post("/v1/chat/completions", headers={"Authorization": "Bearer gateway-test"}, json={
            "model": zero_model, "messages": [{"role": "user", "content": "LOCAL_ZERO_CANARY"}],
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
        failure_mode["value"] = "missing"
        missing_usage_response = await client.post("/v1/responses", headers={"Authorization": "Bearer gateway-test"}, json={
            "model": responses_model, "input": "MISSING_USAGE_CANARY", "store": False, "stream": True,
        })
    assert chat_response.status_code == 200, chat_response.text
    assert responses_response.status_code == 200, responses_response.text
    assert zero_response.status_code == 200, zero_response.text
    assert remote_response.status_code == 400
    assert exhausted_response.status_code == 429
    assert provider_failure_response.status_code >= 400
    assert missing_usage_response.status_code == 200
    assert "responses_stream_usage_missing" in missing_usage_response.text
    assert "response.completed" not in missing_usage_response.text
    assert calls == ["chat.completions", "responses", "chat.completions", "chat.completions"]
    async_test_session.expire_all()
    rows = (await async_test_session.execute(select(UsageLedger).where(UsageLedger.gateway_key_id == key_id))).scalars().all()
    assert len(rows) == 5
    assert sum(row.accounting_status == "finalized" for row in rows) == 3
    assert sum(row.accounting_status != "finalized" for row in rows) == 2
    assert {row.provider for row in rows} == {provider}
    assert {row.accounting_status for row in rows} >= {"finalized", "failed"}
    missing_row = next(row for row in rows if row.requested_model == responses_model and row.streaming)
    assert missing_row.accounting_status != "finalized"
    assert missing_row.actual_cost_eur is not None
    zero_ledger = next(row for row in rows if row.resolved_model == "qwen/zero")
    assert zero_ledger.actual_cost_native == Decimal("0E-9")
    assert zero_ledger.actual_cost_eur == Decimal("0E-9")
    pricing_row = (await async_test_session.execute(select(PricingRule).where(
        PricingRule.provider == provider, PricingRule.upstream_model == "qwen/zero"
    ))).scalar_one()
    assert pricing_row.pricing_metadata["pricing_basis"] == "operator_confirmed_local_zero"
    refreshed_key = await async_test_session.get(GatewayKey, key_id)
    assert refreshed_key is not None
    assert refreshed_key.cost_reserved_eur == Decimal("0E-9")
    assert refreshed_key.tokens_reserved_total == 0
    assert refreshed_key.requests_reserved_total == 0

    charged_rows = [
        row for row in rows if row.accounting_status in {"finalized", "interrupted", "interrupted_estimated", "estimated"}
    ]
    ledger_cost_eur = sum(
        (row.actual_cost_eur if row.actual_cost_eur is not None else row.estimated_cost_eur or Decimal("0"))
        for row in charged_rows
    )
    assert refreshed_key.cost_used_eur == ledger_cost_eur
    assert refreshed_key.tokens_used_total == sum(row.total_tokens for row in charged_rows)
    assert refreshed_key.requests_used_total == len(charged_rows)
    assert zero_ledger.actual_cost_eur == Decimal("0E-9")

    canaries = (
        "CHAT_CANARY", "RESPONSES_CANARY", "LOCAL_ZERO_CANARY", "https://remote.test/canary",
        "QUOTA_CANARY", "PROVIDER_FAILURE_CANARY", "MISSING_USAGE_CANARY", "MISSING_USAGE_CANARY",
        "data:image/png;base64", "BASE64_CANARY", "tool-schema-canary", "tool-arguments-canary",
        "tool-results-canary", "gateway-test", "GENERIC_UPSTREAM_KEY", "Authorization",
        "cookie", "x-slaif-internal", "raw_request", "raw_response",
    )
    safe_ledger_rows = [
        {
            "request_id": row.request_id,
            "endpoint": row.endpoint,
            "provider": row.provider,
            "requested_model": row.requested_model,
            "resolved_model": row.resolved_model,
            "streaming": row.streaming,
            "success": row.success,
            "accounting_status": row.accounting_status,
            "http_status": row.http_status,
            "error_type": row.error_type,
            "error_message": row.error_message,
            "prompt_tokens": row.prompt_tokens,
            "completion_tokens": row.completion_tokens,
            "total_tokens": row.total_tokens,
            "estimated_cost_eur": row.estimated_cost_eur,
            "actual_cost_eur": row.actual_cost_eur,
            "actual_cost_native": row.actual_cost_native,
            "native_currency": row.native_currency,
            "usage_raw": row.usage_raw,
            "response_metadata": row.response_metadata,
        }
        for row in rows
    ]
    audit_rows = (
        await async_test_session.execute(
            select(AuditLog).where(AuditLog.request_id.in_([row.request_id for row in rows]))
        )
    ).scalars().all()
    safe_audit_rows = [
        {
            "action": row.action,
            "entity_type": row.entity_type,
            "entity_id": row.entity_id,
            "old_values": row.old_values,
            "new_values": row.new_values,
            "request_id": row.request_id,
            "note": row.note,
        }
        for row in audit_rows
    ]
    durable_projection = json.dumps([safe_ledger_rows, safe_audit_rows], default=str, sort_keys=True)
    assert all(canary not in durable_projection for canary in canaries)
    assert len([row for row in rows if row.streaming and row.requested_model == responses_model]) == 1
    assert missing_row.accounting_status in {"interrupted", "interrupted_estimated", "estimated"}
    assert missing_row.actual_cost_eur is not None or missing_row.estimated_cost_eur is not None
    assert missing_row.success is not True
    assert "completed" not in json.dumps(missing_row.response_metadata, sort_keys=True).lower()
    assert await async_test_session.scalar(select(func.count()).select_from(QuotaReservation).where(
        QuotaReservation.gateway_key_id == key_id, QuotaReservation.status == "pending")) == 0
