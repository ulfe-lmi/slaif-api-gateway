"""PostgreSQL proof for the facial-scoring module and route metadata boundary."""

from __future__ import annotations

import os

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from slaif_gateway.config import Settings
from slaif_gateway.db.repositories.provider_configs import ProviderConfigsRepository
from slaif_gateway.db.repositories.routing import ModelRoutesRepository
from slaif_gateway.modules.facial_scoring import FacialScoringAdapter
from slaif_gateway.providers.factory import get_provider_adapter
from slaif_gateway.services.chat_completion_route_capabilities import (
    facial_scoring_chat_completion_capabilities,
    is_fixed_request_module_billing,
)

pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL is not set; skipping optional PostgreSQL facial scoring tests.",
)


@pytest.mark.asyncio
async def test_postgres_facial_scoring_metadata_builds_static_adapter(
    async_test_session: AsyncSession,
    monkeypatch,
) -> None:
    monkeypatch.setenv("FACIAL_SCORING_API_KEY", "facial-native-test-key")
    capabilities = {"chat_completions": facial_scoring_chat_completion_capabilities()}

    provider = await ProviderConfigsRepository(async_test_session).create_provider_config(
        provider="facial_scoring",
        display_name="Facial scoring test module",
        kind="module",
        base_url="https://facial-native.example",
        api_key_env_var="FACIAL_SCORING_API_KEY",
        timeout_seconds=11,
        max_retries=0,
        notes="test-only reviewed metadata",
    )
    route = await ModelRoutesRepository(async_test_session).create_model_route(
        requested_model="facial-manipulation-scoring",
        provider=provider.provider,
        upstream_model="facial-manipulation-scoring",
        endpoint="/v1/chat/completions",
        supports_streaming=False,
        capabilities=capabilities,
        notes="bounded test route",
    )

    adapter = get_provider_adapter(provider, Settings())

    assert isinstance(adapter, FacialScoringAdapter)
    assert provider.kind == "module"
    assert provider.api_key_env_var == "FACIAL_SCORING_API_KEY"
    assert route.supports_streaming is False
    assert route.capabilities == capabilities
    assert is_fixed_request_module_billing(provider.kind, route.endpoint) is True
    assert adapter._api_key == "facial-native-test-key"
