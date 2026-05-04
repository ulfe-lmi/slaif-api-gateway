from __future__ import annotations

import json
import os
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from slaif_gateway.config import Settings
from slaif_gateway.db.models import GatewayKey, QuotaReservation, UsageLedger
from slaif_gateway.db.repositories.audit import AuditRepository
from slaif_gateway.db.repositories.cohorts import CohortsRepository
from slaif_gateway.db.repositories.institutions import InstitutionsRepository
from slaif_gateway.db.repositories.keys import GatewayKeysRepository
from slaif_gateway.db.repositories.one_time_secrets import OneTimeSecretsRepository
from slaif_gateway.db.repositories.owners import OwnersRepository
from slaif_gateway.db.repositories.pricing import PricingRulesRepository
from slaif_gateway.db.repositories.provider_configs import ProviderConfigsRepository
from slaif_gateway.db.repositories.routing import ModelRoutesRepository
from slaif_gateway.main import create_app
from slaif_gateway.schemas.keys import CreateGatewayKeyInput
from slaif_gateway.services.input_token_estimation import estimate_chat_completion_input_tokens
from slaif_gateway.services.key_service import KeyService

pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL is not set; skipping PostgreSQL non-message estimation tests.",
)

TEST_MODEL = "gpt-non-message-estimation-test"
FAKE_OPENAI_UPSTREAM_KEY = "fake-openai-upstream-key"
TEST_HMAC_SECRET = "test-hmac-secret-for-non-message-estimation-123456"
TEST_ADMIN_SECRET = "test-admin-secret-for-non-message-estimation-123456"
TEST_ONE_TIME_SECRET_KEY = "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY"
CHAT_COMPLETIONS_ENDPOINT = "/v1/chat/completions"


async def _create_test_key(database_url: str) -> tuple[str, uuid.UUID]:
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    unique_id = uuid.uuid4().hex
    now = datetime.now(UTC)

    try:
        async with session_factory() as session:
            institutions = InstitutionsRepository(session)
            owners = OwnersRepository(session)
            cohorts = CohortsRepository(session)
            providers = ProviderConfigsRepository(session)
            routes = ModelRoutesRepository(session)
            pricing = PricingRulesRepository(session)

            institution = await institutions.create_institution(
                name=f"SLAIF non-message estimation {unique_id}",
                country="SI",
                notes="Integration test institution",
            )
            owner = await owners.create_owner(
                name="NonMessage",
                surname="Tester",
                email=f"non-message-{unique_id}@example.test",
                institution_id=institution.id,
                notes="Integration test owner",
            )
            cohort = await cohorts.create_cohort(
                name=f"non-message-estimation-{unique_id}",
                description="Integration test cohort",
                starts_at=now - timedelta(days=1),
                ends_at=now + timedelta(days=1),
            )

            provider_config = await providers.get_provider_config_by_provider("openai")
            if provider_config is None:
                await providers.create_provider_config(
                    provider="openai",
                    display_name="OpenAI integration test",
                    base_url="https://api.openai.com/v1",
                    api_key_env_var="OPENAI_UPSTREAM_API_KEY",
                    notes="Integration test provider config without secrets",
                )
            else:
                await providers.update_provider_metadata(
                    provider_config.id,
                    display_name="OpenAI integration test",
                    base_url="https://api.openai.com/v1",
                    api_key_env_var="OPENAI_UPSTREAM_API_KEY",
                    notes="Integration test provider config without secrets",
                )
                await providers.set_provider_enabled(provider_config.id, enabled=True)

            await routes.create_model_route(
                requested_model=TEST_MODEL,
                provider="openai",
                upstream_model=TEST_MODEL,
                match_type="exact",
                endpoint=CHAT_COMPLETIONS_ENDPOINT,
                priority=1,
                visible_in_models=True,
                supports_streaming=False,
                notes="Integration test route",
            )
            await pricing.create_pricing_rule(
                provider="openai",
                upstream_model=TEST_MODEL,
                endpoint=CHAT_COMPLETIONS_ENDPOINT,
                valid_from=now - timedelta(days=1),
                currency="EUR",
                input_price_per_1m=Decimal("1.000000000"),
                output_price_per_1m=Decimal("1.000000000"),
                request_price=Decimal("0.000000000"),
                notes="Integration test pricing",
            )

            key_service = KeyService(
                settings=Settings(
                    TOKEN_HMAC_SECRET_V1=TEST_HMAC_SECRET,
                    ADMIN_SESSION_SECRET=TEST_ADMIN_SECRET,
                    ONE_TIME_SECRET_ENCRYPTION_KEY=TEST_ONE_TIME_SECRET_KEY,
                ),
                gateway_keys_repository=GatewayKeysRepository(session),
                one_time_secrets_repository=OneTimeSecretsRepository(session),
                audit_repository=AuditRepository(session),
            )
            created_key = await key_service.create_gateway_key(
                CreateGatewayKeyInput(
                    owner_id=owner.id,
                    cohort_id=cohort.id,
                    valid_from=now - timedelta(minutes=5),
                    valid_until=now + timedelta(days=1),
                    cost_limit_eur=Decimal("10.000000000"),
                    token_limit_total=100_000,
                    request_limit_total=100,
                    allowed_models=[TEST_MODEL],
                    allowed_endpoints=[CHAT_COMPLETIONS_ENDPOINT],
                    note="Integration test key",
                )
            )
            await session.commit()
            return created_key.plaintext_key, created_key.gateway_key_id
    finally:
        await engine.dispose()


async def _side_effect_counts(database_url: str, gateway_key_id: uuid.UUID) -> tuple[int, int]:
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            reservations = (
                await session.execute(
                    select(func.count())
                    .select_from(QuotaReservation)
                    .where(QuotaReservation.gateway_key_id == gateway_key_id)
                )
            ).scalar_one()
            ledger_rows = (
                await session.execute(
                    select(func.count())
                    .select_from(UsageLedger)
                    .where(UsageLedger.gateway_key_id == gateway_key_id)
                )
            ).scalar_one()
            return int(reservations), int(ledger_rows)
    finally:
        await engine.dispose()


async def _latest_state(database_url: str, gateway_key_id: uuid.UUID):
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            gateway_key = await session.get(GatewayKey, gateway_key_id)
            reservation = (
                await session.execute(
                    select(QuotaReservation)
                    .where(QuotaReservation.gateway_key_id == gateway_key_id)
                    .order_by(QuotaReservation.created_at.desc())
                    .limit(1)
                )
            ).scalar_one()
            ledger = (
                await session.execute(
                    select(UsageLedger)
                    .where(UsageLedger.gateway_key_id == gateway_key_id)
                    .order_by(UsageLedger.created_at.desc())
                    .limit(1)
                )
            ).scalar_one()
            return gateway_key, reservation, ledger
    finally:
        await engine.dispose()


def _settings(database_url: str, *, hard_max_input_tokens: int) -> Settings:
    return Settings(
        APP_ENV="test",
        DATABASE_URL=database_url,
        TOKEN_HMAC_SECRET_V1=TEST_HMAC_SECRET,
        ADMIN_SESSION_SECRET=TEST_ADMIN_SECRET,
        ONE_TIME_SECRET_ENCRYPTION_KEY=TEST_ONE_TIME_SECRET_KEY,
        OPENAI_UPSTREAM_API_KEY=FAKE_OPENAI_UPSTREAM_KEY,
        HARD_MAX_INPUT_TOKENS=hard_max_input_tokens,
        DEFAULT_MAX_OUTPUT_TOKENS=20,
    )


@pytest.mark.asyncio
async def test_large_response_format_rejects_before_provider_or_db_side_effects(
    migrated_postgres_url: str,
    respx_mock,
) -> None:
    plaintext_key, gateway_key_id = await _create_test_key(migrated_postgres_url)
    app = create_app(_settings(migrated_postgres_url, hard_max_input_tokens=100))
    route = respx_mock.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(500, json={"error": {"message": "should not be called"}})
    )

    with TestClient(app) as client:
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {plaintext_key}"},
            json={
                "model": TEST_MODEL,
                "messages": [{"role": "user", "content": "tiny prompt"}],
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "answer",
                        "schema": {
                            "type": "object",
                            "properties": {
                                "answer": {
                                    "type": "string",
                                    "description": "RAW_SCHEMA_REJECT_MARKER" + ("x" * 300),
                                }
                            },
                        },
                    },
                },
            },
        )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "input_token_limit_exceeded"
    assert "RAW_SCHEMA_REJECT_MARKER" not in response.json()["error"]["message"]
    assert route.calls == []
    assert await _side_effect_counts(migrated_postgres_url, gateway_key_id) == (0, 0)


@pytest.mark.asyncio
async def test_small_tools_and_response_format_forward_and_reserve_total_estimate(
    migrated_postgres_url: str,
    respx_mock,
) -> None:
    plaintext_key, gateway_key_id = await _create_test_key(migrated_postgres_url)
    app = create_app(_settings(migrated_postgres_url, hard_max_input_tokens=5000))
    raw_schema_marker = "RAW_SCHEMA_ACCEPTED_MARKER"
    request_body = {
        "model": TEST_MODEL,
        "messages": [{"role": "user", "content": "tiny prompt"}],
        "max_tokens": 10,
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "lookup",
                    "parameters": {"type": "object", "properties": {"query": {"type": "string"}}},
                },
            }
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "answer",
                "schema": {
                    "type": "object",
                    "properties": {"answer": {"type": "string", "description": raw_schema_marker}},
                },
            },
        },
    }
    input_estimate = estimate_chat_completion_input_tokens(
        request_body,
        messages=request_body["messages"],
    )
    route = respx_mock.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "chatcmpl_non_message",
                "object": "chat.completion",
                "model": TEST_MODEL,
                "choices": [],
                "usage": {"prompt_tokens": 5, "completion_tokens": 6, "total_tokens": 11},
            },
            headers={"x-request-id": "upstream-non-message"},
        )
    )

    with TestClient(app) as client:
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {plaintext_key}"},
            json=request_body,
        )

    assert response.status_code == 200
    upstream_body = json.loads(route.calls[0].request.content)
    assert upstream_body["tools"] == request_body["tools"]
    assert upstream_body["response_format"] == request_body["response_format"]

    gateway_key, reservation, ledger = await _latest_state(migrated_postgres_url, gateway_key_id)
    assert reservation.status == "finalized"
    assert reservation.reserved_tokens == input_estimate.total_input_tokens_estimate + 10
    assert gateway_key.tokens_reserved_total == 0
    assert gateway_key.requests_reserved_total == 0
    assert gateway_key.tokens_used_total == 11
    assert ledger.accounting_status == "finalized"
    assert ledger.prompt_tokens == 5
    assert ledger.completion_tokens == 6
    assert ledger.total_tokens == 11

    db_payload = json.dumps(
        {
            "gateway_key": {
                "public_key_id": gateway_key.public_key_id,
                "key_hint": gateway_key.key_hint,
                "token_hash": gateway_key.token_hash,
                "metadata": gateway_key.metadata_json,
            },
            "reservation": {
                "request_id": reservation.request_id,
                "requested_model": reservation.requested_model,
            },
            "ledger": {
                "usage_raw": ledger.usage_raw,
                "response_metadata": ledger.response_metadata,
                "error_message": ledger.error_message,
            },
        },
        sort_keys=True,
        default=str,
    )
    assert raw_schema_marker not in db_payload
    assert FAKE_OPENAI_UPSTREAM_KEY not in db_payload
    assert plaintext_key not in db_payload
