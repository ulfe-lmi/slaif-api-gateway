"""Integration tests for deterministic test-data seeding."""

from __future__ import annotations

import os

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from scripts.seed_test_data import async_main
from slaif_gateway.config import Settings
from slaif_gateway.db.models import (
    FxRate,
    GatewayKey,
    Institution,
    ModelRoute,
    OneTimeSecret,
    Owner,
    PricingRule,
    ProviderConfig,
)


pytestmark = pytest.mark.asyncio

async def test_seed_script_populates_safe_dummy_data(
    migrated_postgres_url: str,
    async_test_session: AsyncSession,
    monkeypatch,
) -> None:
    monkeypatch.setenv("TEST_DATABASE_URL", migrated_postgres_url)
    monkeypatch.setenv("APP_ENV", "development")

    await async_main()

    institution = await async_test_session.scalar(
        select(Institution).where(Institution.name == "SLAIF Test Institute")
    )
    owner = await async_test_session.scalar(
        select(Owner).where(Owner.email == "student.one@example.org")
    )
    openai_provider = await async_test_session.scalar(
        select(ProviderConfig).where(ProviderConfig.provider == "openai")
    )
    route = await async_test_session.scalar(
        select(ModelRoute).where(ModelRoute.requested_model == "gpt-4.1-mini")
    )
    price = await async_test_session.scalar(
        select(PricingRule).where(PricingRule.upstream_model == "gpt-4.1-mini")
    )
    fx_rate = await async_test_session.scalar(
        select(FxRate).where(FxRate.base_currency == "USD", FxRate.quote_currency == "EUR")
    )

    assert institution is not None
    assert owner is not None
    assert openai_provider is not None
    assert route is not None
    assert price is not None
    assert fx_rate is not None

    assert openai_provider.api_key_env_var == "OPENAI_UPSTREAM_API_KEY"
    assert "sk-" not in openai_provider.api_key_env_var

    gateway_keys = (await async_test_session.scalars(select(GatewayKey))).all()
    settings = Settings()
    expected_prefix = settings.get_gateway_key_prefix().rstrip("-")
    for key_row in gateway_keys:
        assert key_row.token_hash
        assert "sk-" not in key_row.token_hash
        assert key_row.key_prefix == expected_prefix

    one_time_secrets = (await async_test_session.scalars(select(OneTimeSecret))).all()
    for secret in one_time_secrets:
        assert "sk-" not in secret.encrypted_payload
        assert "secret" not in secret.encrypted_payload.lower() or len(secret.encrypted_payload) > 20

    assert os.getenv("DATABASE_URL") is None or os.getenv("DATABASE_URL") != migrated_postgres_url
