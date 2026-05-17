"""PostgreSQL checks for safe usage profile persistence."""

from __future__ import annotations

import json
import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from sqlalchemy import inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from slaif_gateway.db.models import UsageProfile
from slaif_gateway.db.repositories.keys import GatewayKeysRepository
from slaif_gateway.db.repositories.owners import OwnersRepository
from slaif_gateway.db.repositories.quota import QuotaReservationsRepository
from slaif_gateway.db.repositories.usage import UsageLedgerRepository
from slaif_gateway.db.repositories.usage_profiles import UsageProfilesRepository
from slaif_gateway.schemas.auth import AuthenticatedGatewayKey
from slaif_gateway.schemas.policy import ChatCompletionPolicyResult
from slaif_gateway.schemas.pricing import ChatCostEstimate
from slaif_gateway.schemas.providers import ProviderResponse, ProviderUsage
from slaif_gateway.schemas.routing import RouteResolutionResult
from slaif_gateway.services.accounting import AccountingService
from slaif_gateway.services.calibration_summary_service import CalibrationSummaryService
from slaif_gateway.services.quota_service import QuotaService
from slaif_gateway.services.usage_profile_service import UsageProfileService, build_chat_completion_tool_metadata
from tests.e2e.test_openai_python_client_chat import (
    COMPLETION_TEXT,
    FAKE_OPENAI_UPSTREAM_KEY,
    PROMPT_TEXT,
    TEST_MODEL,
    _configure_runtime_environment,
    _create_test_data,
    _load_accounting_state,
)


def _usage_profile_indexes(sync_connection) -> set[str]:
    return {index["name"] for index in inspect(sync_connection).get_indexes("usage_profiles")}


def _usage_profile_columns(sync_connection) -> set[str]:
    return {column["name"] for column in inspect(sync_connection).get_columns("usage_profiles")}


@pytest.mark.asyncio
async def test_migration_creates_usage_profiles_table_and_indexes(migrated_engine) -> None:
    async with migrated_engine.connect() as connection:
        columns = await connection.run_sync(_usage_profile_columns)
        indexes = await connection.run_sync(_usage_profile_indexes)

    assert "usage_ledger_id" in columns
    assert "profile_metadata" in columns
    assert "ix_usage_profiles_gateway_key_id_created_at" in indexes
    assert "ix_usage_profiles_owner_id_created_at" in indexes
    assert "ix_usage_profiles_institution_id_created_at" in indexes
    assert "ix_usage_profiles_cohort_id_created_at" in indexes
    assert "ix_usage_profiles_endpoint_provider_model_created_at" in indexes


@pytest.mark.asyncio
async def test_usage_profile_repository_insert_and_list(async_test_session: AsyncSession) -> None:
    gateway_key = await _create_gateway_key(async_test_session)
    ledger = await _finalized_ledger(async_test_session, gateway_key)
    service = UsageProfileService(
        usage_ledger_repository=UsageLedgerRepository(async_test_session),
        usage_profiles_repository=UsageProfilesRepository(async_test_session),
    )

    profile = await service.record_from_usage_ledger(
        ledger.id,
        route=_route(),
        tool_metadata=build_chat_completion_tool_metadata(
            {"tools": [{"type": "function", "function": {"name": "lookup"}}]}
        ),
    )
    rows = await UsageProfilesRepository(async_test_session).list_for_gateway_key(gateway_key.id)

    assert profile is not None
    assert rows == [profile]
    assert profile.usage_ledger_id == ledger.id
    assert profile.gateway_key_id == gateway_key.id
    assert profile.tool_call_counts == {"function": 1}
    assert profile.function_tool_names == ["lookup"]


@pytest.mark.asyncio
async def test_usage_profile_constraints_reject_negative_counts(async_test_session: AsyncSession) -> None:
    gateway_key = await _create_gateway_key(async_test_session)
    ledger = await _finalized_ledger(async_test_session, gateway_key)

    with pytest.raises(IntegrityError):
        async with async_test_session.begin_nested():
            async_test_session.add(
                UsageProfile(
                    usage_ledger_id=ledger.id,
                    gateway_key_id=gateway_key.id,
                    endpoint_path="/v1/chat/completions",
                    provider="openai",
                    input_tokens=-1,
                    output_tokens=0,
                    total_tokens=0,
                    cost_source="unknown",
                )
            )
            await async_test_session.flush()


@pytest.mark.asyncio
async def test_usage_profile_fk_requires_usage_ledger(async_test_session: AsyncSession) -> None:
    gateway_key = await _create_gateway_key(async_test_session)

    with pytest.raises(IntegrityError):
        async with async_test_session.begin_nested():
            async_test_session.add(
                UsageProfile(
                    usage_ledger_id=uuid.uuid4(),
                    gateway_key_id=gateway_key.id,
                    endpoint_path="/v1/chat/completions",
                    provider="openai",
                    input_tokens=1,
                    output_tokens=1,
                    total_tokens=2,
                    cost_source="unknown",
                )
            )
            await async_test_session.flush()


def test_chat_completions_e2e_creates_usage_profile_without_content(
    migrated_postgres_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_runtime_environment(monkeypatch, migrated_postgres_url)
    created = asyncio.run(_create_test_data(migrated_postgres_url))

    from slaif_gateway.config import get_settings
    from slaif_gateway.main import create_app

    app = create_app(get_settings())
    upstream_payload = {
        "id": "chatcmpl-profile",
        "object": "chat.completion",
        "created": 123,
        "model": TEST_MODEL,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": COMPLETION_TEXT},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 5,
            "completion_tokens": 6,
            "total_tokens": 11,
            "prompt_tokens_details": {"cached_tokens": 2},
            "completion_tokens_details": {"reasoning_tokens": 1},
        },
    }

    with respx.mock(assert_all_mocked=True, assert_all_called=True) as router:
        router.post("https://api.openai.com/v1/chat/completions").mock(
            return_value=httpx.Response(
                200,
                json=upstream_payload,
                headers={"x-request-id": "upstream-openai-profile"},
            )
        )
        with TestClient(app) as client:
            response = client.post(
                "/v1/chat/completions",
                json={
                    "model": TEST_MODEL,
                    "messages": [{"role": "user", "content": PROMPT_TEXT}],
                    "tools": [
                        {
                            "type": "function",
                            "function": {
                                "name": "lookup_profile",
                                "parameters": {"description": PROMPT_TEXT},
                            },
                        }
                    ],
                },
                headers={"Authorization": f"Bearer {created.plaintext_gateway_key}"},
            )

    assert response.status_code == 200, response.text
    state = asyncio.run(_load_accounting_state(migrated_postgres_url, created.gateway_key_id))
    profile = asyncio.run(_latest_profile(migrated_postgres_url, created.gateway_key_id))

    assert state.usage_ledger.accounting_status == "finalized"
    assert profile is not None
    assert profile.usage_ledger_id == state.usage_ledger.id
    assert profile.endpoint_path == "/v1/chat/completions"
    assert profile.provider == "openai"
    assert profile.requested_model == TEST_MODEL
    assert profile.resolved_upstream_model == TEST_MODEL
    assert profile.provider_host == "api.openai.com"
    assert profile.provider_endpoint_path == "/v1/chat/completions"
    assert profile.input_tokens == 5
    assert profile.output_tokens == 6
    assert profile.total_tokens == 11
    assert profile.cached_tokens == 2
    assert profile.reasoning_tokens == 1
    assert profile.tool_call_counts == {"function": 1}
    assert profile.function_tool_names == ["lookup_profile"]

    serialized = json.dumps(
        {
            "tool_call_counts": profile.tool_call_counts,
            "function_tool_names": profile.function_tool_names,
            "profile_metadata": profile.profile_metadata,
            "provider_host": profile.provider_host,
            "provider_endpoint_path": profile.provider_endpoint_path,
        },
        sort_keys=True,
    )
    assert PROMPT_TEXT not in serialized
    assert COMPLETION_TEXT not in serialized
    assert created.plaintext_gateway_key not in serialized
    assert FAKE_OPENAI_UPSTREAM_KEY not in serialized


def test_trusted_calibration_chat_completions_e2e_records_safe_profile_metadata(
    migrated_postgres_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = "gpt-5-search-api"
    _configure_runtime_environment(monkeypatch, migrated_postgres_url)
    created = asyncio.run(
        _create_test_data(
            migrated_postgres_url,
            model=model,
            trusted_calibration=True,
            owner_label="Trusted Calibration",
        )
    )

    from slaif_gateway.config import get_settings
    from slaif_gateway.main import create_app

    app = create_app(get_settings())
    upstream_payload = {
        "id": "chatcmpl-calibration-profile",
        "object": "chat.completion",
        "created": 123,
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": COMPLETION_TEXT},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 5, "completion_tokens": 6, "total_tokens": 11},
    }

    with respx.mock(assert_all_mocked=True, assert_all_called=True) as router:
        router.post("https://api.openai.com/v1/chat/completions").mock(
            return_value=httpx.Response(200, json=upstream_payload)
        )
        with TestClient(app) as client:
            response = client.post(
                "/v1/chat/completions",
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": PROMPT_TEXT}],
                    "web_search_options": {"search_context_size": "low"},
                    "tools": [{"type": "web_search_preview"}],
                },
                headers={"Authorization": f"Bearer {created.plaintext_gateway_key}"},
            )

    assert response.status_code == 200, response.text
    profile = asyncio.run(_latest_profile(migrated_postgres_url, created.gateway_key_id))

    assert profile is not None
    assert profile.profile_metadata["key_purpose"] == "trusted_calibration"
    assert (
        profile.profile_metadata["capability_policy_mode"]
        == "trusted_calibration_discovery"
    )
    assert "web_search_options" in profile.profile_metadata["observed_hosted_capability_types"]
    assert "web_search_preview" in profile.profile_metadata["observed_hosted_capability_types"]
    serialized = json.dumps(profile.profile_metadata, sort_keys=True)
    assert PROMPT_TEXT not in serialized
    assert COMPLETION_TEXT not in serialized
    assert created.plaintext_gateway_key not in serialized


def test_calibration_summary_service_reads_trusted_profiles_from_postgres(
    migrated_postgres_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = "gpt-5-search-api"
    _configure_runtime_environment(monkeypatch, migrated_postgres_url)
    created = asyncio.run(
        _create_test_data(
            migrated_postgres_url,
            model=model,
            trusted_calibration=True,
            owner_label="Trusted Calibration Summary",
        )
    )

    from slaif_gateway.config import get_settings
    from slaif_gateway.main import create_app

    app = create_app(get_settings())
    upstream_payload = {
        "id": "chatcmpl-calibration-summary",
        "object": "chat.completion",
        "created": 123,
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": COMPLETION_TEXT},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 8, "completion_tokens": 9, "total_tokens": 17},
    }

    with respx.mock(assert_all_mocked=True, assert_all_called=True) as router:
        router.post("https://api.openai.com/v1/chat/completions").mock(
            return_value=httpx.Response(200, json=upstream_payload)
        )
        with TestClient(app) as client:
            response = client.post(
                "/v1/chat/completions",
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": PROMPT_TEXT}],
                    "web_search_options": {"search_context_size": "low"},
                },
                headers={"Authorization": f"Bearer {created.plaintext_gateway_key}"},
            )

    assert response.status_code == 200, response.text
    result = asyncio.run(_summarize_calibration_profile(migrated_postgres_url, created.gateway_key_id))

    assert result.summary.observed_request_count == 1
    assert result.summary.observed_endpoints == ("/v1/chat/completions",)
    assert result.summary.observed_requested_models == (model,)
    assert "web_search_options" in result.summary.observed_hosted_capabilities
    assert result.proposal.proposed_allowed_endpoints == ("/v1/chat/completions",)
    assert result.proposal.proposed_allowed_models == (model,)
    assert result.proposal.proposed_request_limit_total == 3
    assert result.proposal.proposed_token_limit_total == 51
    assert result.proposal.proposed_allowed_hosted_capabilities == ()
    assert result.proposal.hosted_capabilities_requiring_review == (
        "search_specific_model",
        "web_search_options",
    )
    serialized = json.dumps(result, default=str, sort_keys=True)
    assert PROMPT_TEXT not in serialized
    assert COMPLETION_TEXT not in serialized
    assert created.plaintext_gateway_key not in serialized


async def _summarize_calibration_profile(database_url: str, gateway_key_id: uuid.UUID):
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            service = CalibrationSummaryService(
                gateway_keys_repository=GatewayKeysRepository(session),
                usage_profiles_repository=UsageProfilesRepository(session),
            )
            return await service.summarize_calibration_key_usage(
                gateway_key_id=gateway_key_id,
                multiplier=Decimal("3"),
            )
    finally:
        await engine.dispose()


async def _latest_profile(database_url: str, gateway_key_id: uuid.UUID) -> UsageProfile | None:
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            return (
                await session.execute(
                    select(UsageProfile)
                    .where(UsageProfile.gateway_key_id == gateway_key_id)
                    .order_by(UsageProfile.created_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
    finally:
        await engine.dispose()


async def _create_gateway_key(async_test_session: AsyncSession):
    owner = await OwnersRepository(async_test_session).create_owner(
        name="Usage",
        surname="Profiler",
        email=f"usage-profile-{uuid.uuid4()}@example.test",
    )
    now = datetime.now(UTC)
    return await GatewayKeysRepository(async_test_session).create_gateway_key_record(
        public_key_id=f"k_{uuid.uuid4().hex}",
        token_hash=f"hash-{uuid.uuid4().hex}",
        owner_id=owner.id,
        valid_from=now - timedelta(minutes=5),
        valid_until=now + timedelta(hours=1),
        cost_limit_eur=Decimal("1.000000000"),
        token_limit_total=1000,
        request_limit_total=5,
        allow_all_models=True,
        allow_all_endpoints=True,
    )


async def _finalized_ledger(async_test_session: AsyncSession, gateway_key):
    reservation = await QuotaService(
        gateway_keys_repository=GatewayKeysRepository(async_test_session),
        quota_reservations_repository=QuotaReservationsRepository(async_test_session),
    ).reserve_for_chat_completion(
        authenticated_key=_authenticated_key(gateway_key),
        route=_route(),
        policy=_policy(),
        cost_estimate=_estimate(),
        request_id=f"req-{uuid.uuid4()}",
    )

    result = await AccountingService(async_test_session).finalize_successful_response(
        reservation.reservation_id,
        _authenticated_key(gateway_key),
        _route(),
        _policy(),
        _estimate(),
        ProviderResponse(
            provider="openai",
            upstream_model="gpt-4.1-mini",
            status_code=200,
            json_body={},
            upstream_request_id="upstream-profile",
            usage=ProviderUsage(
                prompt_tokens=5,
                completion_tokens=6,
                total_tokens=11,
                cached_tokens=2,
                reasoning_tokens=1,
            ),
        ),
        request_id=reservation.request_id,
    )
    ledger = await UsageLedgerRepository(async_test_session).get_usage_record_by_id(result.usage_ledger_id)
    assert ledger is not None
    return ledger


def _authenticated_key(row) -> AuthenticatedGatewayKey:
    return AuthenticatedGatewayKey(
        gateway_key_id=row.id,
        owner_id=row.owner_id,
        cohort_id=row.cohort_id,
        public_key_id=row.public_key_id,
        status=row.status,
        valid_from=row.valid_from,
        valid_until=row.valid_until,
        allow_all_models=row.allow_all_models,
        allowed_models=tuple(row.allowed_models),
        allow_all_endpoints=row.allow_all_endpoints,
        allowed_endpoints=tuple(row.allowed_endpoints),
        allowed_providers=None,
        cost_limit_eur=row.cost_limit_eur,
        token_limit_total=row.token_limit_total,
        request_limit_total=row.request_limit_total,
        rate_limit_policy={},
    )


def _route() -> RouteResolutionResult:
    return RouteResolutionResult(
        requested_model="classroom-cheap",
        resolved_model="gpt-4.1-mini",
        provider="openai",
        route_id=uuid.uuid4(),
        route_match_type="exact",
        route_pattern="classroom-cheap",
        priority=100,
        provider_base_url="https://api.openai.com/v1?ignored=true",
    )


def _policy() -> ChatCompletionPolicyResult:
    return ChatCompletionPolicyResult(
        effective_body={"model": "classroom-cheap", "messages": [], "max_completion_tokens": 100},
        requested_output_tokens=100,
        effective_output_tokens=100,
        estimated_input_tokens=100,
        injected_default_output_tokens=False,
    )


def _estimate() -> ChatCostEstimate:
    return ChatCostEstimate(
        provider="openai",
        requested_model="classroom-cheap",
        resolved_model="gpt-4.1-mini",
        native_currency="EUR",
        estimated_input_tokens=100,
        estimated_output_tokens=100,
        estimated_input_cost_native=Decimal("0.100000000"),
        estimated_output_cost_native=Decimal("0.200000000"),
        estimated_total_cost_native=Decimal("0.300000000"),
        estimated_total_cost_eur=Decimal("0.300000000"),
        pricing_rule_id=None,
        fx_rate_id=None,
    )
