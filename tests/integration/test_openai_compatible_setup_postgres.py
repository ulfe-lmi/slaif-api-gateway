from __future__ import annotations

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import pytest
from sqlalchemy import func, select, text

from slaif_gateway.db.models import AuditLog, ModelRoute, PricingRule
from slaif_gateway.db.repositories.audit import AuditRepository
from slaif_gateway.db.repositories.pricing import PricingRulesRepository
from slaif_gateway.db.repositories.provider_configs import ProviderConfigsRepository
from slaif_gateway.db.repositories.routing import ModelRoutesRepository
from slaif_gateway.services.openai_compatible_discovery import DiscoveredModels
from slaif_gateway.services.openai_compatible_setup import (
    CHAT_AND_RESPONSES_VISION_INLINE_PRESET,
    CHAT_AND_RESPONSES_TEXT_PRESET,
    OpenAICompatibleSetupService,
    SetupError,
    SetupRequest,
)


class _FreshDiscovery:
    async def discover(self, provider_or_id: str) -> DiscoveredModels:
        return DiscoveredModels(provider=provider_or_id, models=("qwen/a", "qwen/b"))


class _FailOnSecondAudit:
    def __init__(self, delegate: AuditRepository) -> None:
        self._delegate = delegate
        self._calls = 0

    async def add_audit_log(self, **kwargs: object):
        self._calls += 1
        if self._calls == 2:
            raise RuntimeError("injected setup failure after route and pricing writes")
        return await self._delegate.add_audit_log(**kwargs)


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
            pricing_mode="local_zero",
            confirm_local_zero=True,
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
                pricing_mode="local_zero",
                confirm_local_zero=True,
                reason="conflict must roll back",
            )
        )
    route_count_after = await async_test_session.scalar(
        select(func.count()).select_from(ModelRoute).where(ModelRoute.provider == provider.provider)
    )
    assert route_count_after == 4


@pytest.mark.asyncio
async def test_vision_inline_setup_adds_only_chat_and_responses_image_capabilities(
    async_test_session,
) -> None:
    suffix = id(async_test_session)
    providers = ProviderConfigsRepository(async_test_session)
    provider = await providers.create_provider_config(
        provider=f"pg-vision-{suffix}",
        display_name="PostgreSQL vision preset",
        base_url="https://vision.example.test/v1",
        api_key_env_var="PG_VISION_KEY",
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
            selected_models=("qwen/a",),
            preset=CHAT_AND_RESPONSES_VISION_INLINE_PRESET,
            pricing_mode="local_zero",
            confirm_local_zero=True,
            reason="bounded vision preset test",
        )
    )

    chat = next(route for route in result.routes if route.endpoint == "/v1/chat/completions")
    responses = next(route for route in result.routes if route.endpoint == "/v1/responses")
    chat_capabilities = chat.capabilities["chat_completions"]
    responses_capabilities = responses.capabilities["responses"]
    assert chat_capabilities["chat_image_inputs"] is True
    assert chat_capabilities["chat_multimodal"] is True
    assert chat_capabilities["chat_audio_inputs"] is False
    assert chat_capabilities["chat_file_inputs"] is False
    assert responses_capabilities["image_input"] is True
    assert responses_capabilities["multimodal"] is True
    assert responses_capabilities["file_input"] is False
    assert responses_capabilities["storage"] is False
    assert responses_capabilities["codex_request_envelope"] is False


@pytest.mark.asyncio
async def test_generic_setup_mid_write_failure_rolls_back_all_rows(migrated_postgres_url) -> None:
    engine = create_async_engine(migrated_postgres_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    suffix = id(engine)
    async with session_factory() as session:
        async with session.begin():
            provider = await ProviderConfigsRepository(session).create_provider_config(
                provider=f"pg-generic-failure-{suffix}",
                display_name="PostgreSQL failure setup",
                base_url="https://provider.example.test/v1",
                api_key_env_var="PG_GENERIC_FAILURE_KEY",
                kind="openai_compatible",
                enabled=True,
                timeout_seconds=30,
                max_retries=0,
            )

    async with session_factory() as session:
        before_values = []
        for model in (ModelRoute, PricingRule, AuditLog):
            before_values.append(int(await session.scalar(select(func.count()).select_from(model))))
        before = tuple(before_values)
        await session.rollback()
        try:
            async with session.begin():
                await OpenAICompatibleSetupService(
                    session=session,
                    provider_configs_repository=ProviderConfigsRepository(session),
                    model_routes_repository=ModelRoutesRepository(session),
                    pricing_rules_repository=PricingRulesRepository(session),
                    audit_repository=_FailOnSecondAudit(AuditRepository(session)),
                    discovery_service=_FreshDiscovery(),
                ).execute(
                    SetupRequest(
                        provider=provider.provider,
                        selected_models=("qwen/a", "qwen/b"),
                        preset="chat_text_v1",
                        pricing_mode="local_zero",
                        confirm_local_zero=True,
                        reason="injected rollback proof",
                    )
                )
        except RuntimeError as exc:
            assert str(exc) == "injected setup failure after route and pricing writes"
        else:
            raise AssertionError("injected setup failure did not fire")

    async with session_factory() as session:
        after_values = []
        for model in (ModelRoute, PricingRule, AuditLog):
            after_values.append(int(await session.scalar(select(func.count()).select_from(model))))
        after = tuple(after_values)
    async with engine.begin() as connection:
        await connection.execute(
            text("DELETE FROM provider_configs WHERE provider = :provider"),
            {"provider": provider.provider},
        )
    await engine.dispose()
    assert after == before
