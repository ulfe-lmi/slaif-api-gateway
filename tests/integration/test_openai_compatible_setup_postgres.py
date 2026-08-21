from __future__ import annotations

import pytest
from sqlalchemy import func, select

from slaif_gateway.db.models import AuditLog, ModelRoute, PricingRule
from slaif_gateway.db.repositories.audit import AuditRepository
from slaif_gateway.db.repositories.pricing import PricingRulesRepository
from slaif_gateway.db.repositories.provider_configs import ProviderConfigsRepository
from slaif_gateway.db.repositories.routing import ModelRoutesRepository
from slaif_gateway.services.openai_compatible_discovery import DiscoveredModels
from slaif_gateway.services.openai_compatible_setup import (
    CHAT_AND_RESPONSES_TEXT_PRESET,
    OpenAICompatibleSetupService,
    SetupError,
    SetupRequest,
)


class _FreshDiscovery:
    async def discover(self, provider_or_id: str) -> DiscoveredModels:
        return DiscoveredModels(provider=provider_or_id, models=("qwen/a", "qwen/b"))


@pytest.mark.asyncio
async def test_generic_setup_creates_exact_routes_pricing_and_audits_atomically(async_test_session) -> None:
    suffix = id(async_test_session)
    providers = ProviderConfigsRepository(async_test_session)
    provider = await providers.create_provider_config(
        provider=f"pg-generic-{suffix}",
        display_name="PostgreSQL generic setup",
        base_url="https://provider.example.test/v1",
        api_key_env_var="PG_GENERIC_KEY",
        kind="openai_compatible",
        enabled=True,
        timeout_seconds=30,
        max_retries=0,
    )
    service = OpenAICompatibleSetupService(
        session=async_test_session,
        provider_configs_repository=providers,
        model_routes_repository=ModelRoutesRepository(async_test_session),
        pricing_rules_repository=PricingRulesRepository(async_test_session),
        audit_repository=AuditRepository(async_test_session),
        discovery_service=_FreshDiscovery(),
    )

    result = await service.execute(
        SetupRequest(
            provider=provider.provider,
            selected_models=("qwen/a", "qwen/b"),
            preset=CHAT_AND_RESPONSES_TEXT_PRESET,
            reason="bounded PostgreSQL setup test",
        )
    )

    assert len(result.routes) == 4
    assert len(result.pricing_rules) == 4
    assert all(not row.enabled for row in result.routes)
    assert all(row.currency == "EUR" for row in result.pricing_rules)
    assert all(row.pricing_metadata["pricing_basis"] == "operator_confirmed_local_zero" for row in result.pricing_rules)
    route_count = await async_test_session.scalar(
        select(func.count()).select_from(ModelRoute).where(ModelRoute.provider == provider.provider)
    )
    pricing_count = await async_test_session.scalar(
        select(func.count()).select_from(PricingRule).where(PricingRule.provider == provider.provider)
    )
    audit_count = await async_test_session.scalar(
        select(func.count()).select_from(AuditLog).where(AuditLog.entity_id == provider.id)
    )
    assert (route_count, pricing_count) == (4, 4)
    assert audit_count == 1

    with pytest.raises(SetupError, match="conflicts"):
        await service.execute(
            SetupRequest(
                provider=provider.provider,
                selected_models=("qwen/a",),
                preset="chat_text_v1",
                reason="conflict must roll back",
            )
        )
    route_count_after = await async_test_session.scalar(
        select(func.count()).select_from(ModelRoute).where(ModelRoute.provider == provider.provider)
    )
    assert route_count_after == 4
