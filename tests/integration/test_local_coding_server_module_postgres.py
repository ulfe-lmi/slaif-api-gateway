"""PostgreSQL proof for Local Coding pre-reservation failure boundaries."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from slaif_gateway.api.errors import OpenAICompatibleError
from slaif_gateway.config import Settings
from slaif_gateway.db.models import QuotaReservation, UsageLedger
from slaif_gateway.db.repositories.routing import ModelRoutesRepository
from slaif_gateway.modules.servers.local_coding.adapter import LocalCodingAdapter
from slaif_gateway.modules.servers.local_coding.contract import (
    LOCAL_CODING_SERVER_MODULE_ID,
    LOCAL_CODING_SERVER_MODULE_VERSION,
    parse_local_coding_route_contract,
)
from slaif_gateway.modules.servers.registry import resolve_server_module
from slaif_gateway.providers.factory import get_provider_adapter
from slaif_gateway.schemas.openai import ResponsesCreateRequest
from slaif_gateway.services.responses_gateway import handle_response_create
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession


def _route() -> SimpleNamespace:
    return SimpleNamespace(
        provider="local-coding",
        provider_kind="openai_compatible",
        provider_base_url="http://127.0.0.1:18031/v1",
        provider_api_key_env_var="LOCAL_CODING_SERVICE_TOKEN",
        provider_timeout_seconds=10,
        provider_max_retries=0,
        route_id=uuid.uuid4(),
        resolved_model="qwen3.8-27b",
        requested_model="local-model",
        route_match_type="exact",
        route_pattern="local-model",
        priority=1,
        supports_streaming=True,
        capabilities={
            "responses": {
                "text": True,
                "stateless": True,
                "streaming": True,
            },
            "local_coding": {
                "contract_version": "local-coding-v1",
                "route_name": "vision",
                "tool_policy_version": "responses-tool-policy-v1",
                "identity_mode": "signed_identity_v1",
                "replay_mode": "process_local_inclusive_horizon_fail_closed",
                "deployment_mode": "single_worker",
                "clock_skew_seconds": 60,
                "replay_ttl_seconds": 60,
            },
        },
    )


@pytest.mark.asyncio
async def test_local_coding_identity_failure_creates_no_reservation_or_ledger(
    async_test_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    before_reservations = await async_test_session.scalar(
        select(func.count()).select_from(QuotaReservation)
    )
    before_ledger = await async_test_session.scalar(select(func.count()).select_from(UsageLedger))
    from slaif_gateway.services import responses_gateway

    async def resolve(**_kwargs):
        return _route()

    monkeypatch.setattr(responses_gateway, "_resolve_responses_route", resolve)
    key = SimpleNamespace(
        gateway_key_id=uuid.uuid4(),
        owner_id=uuid.uuid4(),
        responses_policy={
            "version": 1,
            "allowed_capabilities": ["text", "stateless"],
            "client_module": {
                "id": "openai-default",
                "version": "1",
                "fixture_sha256": None,
            },
        },
        allow_all_models=True,
        allow_all_endpoints=True,
        allowed_models=(),
        allowed_endpoints=(),
        allowed_providers=None,
        external_tool_policy=None,
        key_purpose="standard",
        capability_policy_mode="standard",
    )
    payload = ResponsesCreateRequest.model_validate(
        {"model": "local-model", "input": "synthetic", "store": False}
    )

    with pytest.raises(OpenAICompatibleError) as exc_info:
        await handle_response_create(
            payload=payload,
            authenticated_key=key,
            settings=Settings(),
        )

    assert exc_info.value.code == "local_coding_identity_unavailable"
    after_reservations = await async_test_session.scalar(
        select(func.count()).select_from(QuotaReservation)
    )
    after_ledger = await async_test_session.scalar(select(func.count()).select_from(UsageLedger))
    assert after_reservations == before_reservations
    assert after_ledger == before_ledger


@pytest.mark.asyncio
async def test_local_coding_route_row_roundtrips_new_mode_and_resolves_version_two(
    async_test_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capabilities = {
        "responses": {
            "text": True,
            "stateless": True,
            "streaming": True,
        },
        "local_coding": {
            "contract_version": "local-coding-v1",
            "route_name": "vision",
            "tool_policy_version": "responses-tool-policy-v1",
            "identity_mode": "signed_identity_v1",
            "replay_mode": "process_local_inclusive_horizon_fail_closed",
            "deployment_mode": "single_worker",
            "clock_skew_seconds": 60,
            "replay_ttl_seconds": 60,
        },
    }
    repository = ModelRoutesRepository(async_test_session)
    route = await repository.create_model_route(
        requested_model="local-coding-roundtrip",
        provider="local-coding",
        upstream_model="qwen3.8-27b",
        endpoint="/v1/responses",
        capabilities=capabilities,
    )
    route_id = route.id
    await async_test_session.commit()
    async_test_session.expire_all()

    reloaded = await repository.get_model_route_by_id(route_id)
    assert reloaded is not None
    stored = reloaded.capabilities["local_coding"]
    assert stored["replay_mode"] == "process_local_inclusive_horizon_fail_closed"
    assert stored["clock_skew_seconds"] == 60
    assert stored["replay_ttl_seconds"] == 60

    contract = parse_local_coding_route_contract(reloaded.capabilities)
    assert contract is not None
    assert contract.replay_mode == "process_local_inclusive_horizon_fail_closed"
    assert contract.clock_skew_seconds == 60
    assert contract.replay_ttl_seconds == 60

    resolved = resolve_server_module("local-coding", "openai_compatible", reloaded.capabilities)
    assert resolved.module_id == LOCAL_CODING_SERVER_MODULE_ID
    assert resolved.module_version == LOCAL_CODING_SERVER_MODULE_VERSION
    assert resolved.module_version == "2"

    monkeypatch.setenv(
        "LOCAL_CODING_ROUTE_ROUNDTRIP_TOKEN",
        "synthetic-local-coding-route-roundtrip-bearer-0123456789",
    )
    adapter = get_provider_adapter(
        SimpleNamespace(
            provider="local-coding",
            provider_kind="openai_compatible",
            provider_base_url="http://127.0.0.1:18031/v1",
            provider_api_key_env_var="LOCAL_CODING_ROUTE_ROUNDTRIP_TOKEN",
            provider_timeout_seconds=10,
            provider_max_retries=0,
            capabilities=reloaded.capabilities,
        ),
        Settings(
            LOCAL_CODING_SIGNING_SECRET_V1="local-coding-signing-secret-012345678901",
            LOCAL_CODING_IDENTITY_DERIVATION_SECRET_V1="local-coding-derivation-secret-0123456789",
        ),
    )
    assert isinstance(adapter, LocalCodingAdapter)
