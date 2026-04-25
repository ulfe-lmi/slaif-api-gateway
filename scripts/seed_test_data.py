#!/usr/bin/env python3
"""Deterministically seed safe dummy data into TEST_DATABASE_URL."""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from slaif_gateway.db.models import (
    Cohort,
    FxRate,
    GatewayKey,
    Institution,
    ModelRoute,
    PricingRule,
)
from slaif_gateway.db.repositories.admin_users import AdminUsersRepository
from slaif_gateway.db.repositories.cohorts import CohortsRepository
from slaif_gateway.db.repositories.fx_rates import FxRatesRepository
from slaif_gateway.db.repositories.institutions import InstitutionsRepository
from slaif_gateway.db.repositories.keys import GatewayKeysRepository
from slaif_gateway.db.repositories.owners import OwnersRepository
from slaif_gateway.db.repositories.pricing import PricingRulesRepository
from slaif_gateway.db.repositories.provider_configs import ProviderConfigsRepository
from slaif_gateway.db.repositories.routing import ModelRoutesRepository


@dataclass(slots=True)
class SeedResult:
    institutions: int
    cohorts: int
    owners: int
    admin_users: int
    provider_configs: int
    model_routes: int
    pricing_rules: int
    fx_rates: int
    gateway_keys: int


def _validate_environment() -> str:
    if os.getenv("APP_ENV", "").lower() == "production":
        raise RuntimeError("Refusing to seed test data when APP_ENV=production")

    test_database_url = os.getenv("TEST_DATABASE_URL")
    if not test_database_url:
        raise RuntimeError("TEST_DATABASE_URL is required for seed script")

    parsed = urlparse(test_database_url)
    db_name = (parsed.path or "").lstrip("/").lower()
    if parsed.scheme not in {"postgresql+asyncpg", "postgresql", "postgres"}:
        raise RuntimeError("TEST_DATABASE_URL must use a PostgreSQL scheme")
    if not any(marker in db_name for marker in ("test", "dev", "local")):
        raise RuntimeError(
            "Refusing to seed database that does not look like test/dev/local by name"
        )

    return test_database_url


async def _get_or_create_institution(repo: InstitutionsRepository) -> tuple[Institution, bool]:
    existing = await repo.get_institution_by_name("SLAIF Test Institute")
    if existing:
        return existing, False
    row = await repo.create_institution(
        name="SLAIF Test Institute",
        country="SI",
        notes="Deterministic integration seed institution",
    )
    return row, True


async def _seed(session: AsyncSession) -> SeedResult:
    counts = SeedResult(0, 0, 0, 0, 0, 0, 0, 0, 0)

    institutions = InstitutionsRepository(session)
    cohorts = CohortsRepository(session)
    owners = OwnersRepository(session)
    admins = AdminUsersRepository(session)
    providers = ProviderConfigsRepository(session)
    routes = ModelRoutesRepository(session)
    pricing = PricingRulesRepository(session)
    fx_repo = FxRatesRepository(session)
    keys = GatewayKeysRepository(session)

    institution, created = await _get_or_create_institution(institutions)
    counts.institutions += int(created)

    cohort = await session.scalar(select(Cohort).where(Cohort.name == "test-cohort-2026"))
    if cohort is None:
        cohort = await cohorts.create_cohort(
            name="test-cohort-2026",
            description="Deterministic cohort for integration tests",
            starts_at=datetime(2026, 1, 1, tzinfo=UTC),
            ends_at=datetime(2026, 12, 31, tzinfo=UTC),
        )
        counts.cohorts += 1

    owner = await owners.get_owner_by_email("student.one@example.org")
    if owner is None:
        owner = await owners.create_owner(
            name="Demo",
            surname="Student",
            email="student.one@example.org",
            institution_id=institution.id,
            external_id="demo-owner-001",
            notes="Safe deterministic dummy owner",
        )
        counts.owners += 1

    admin = await admins.get_admin_user_by_email("admin.seed@example.org")
    if admin is None:
        admin = await admins.create_admin_user(
            email="admin.seed@example.org",
            display_name="Seed Admin",
            password_hash="$argon2id$v=19$m=65536,t=3,p=4$seed$placeholder-not-real",
            role="admin",
            is_active=True,
        )
        counts.admin_users += 1

    if await providers.get_provider_config_by_provider("openai") is None:
        await providers.create_provider_config(
            provider="openai",
            display_name="OpenAI (test)",
            base_url="https://api.openai.com/v1",
            api_key_env_var="OPENAI_UPSTREAM_API_KEY",
            notes="Test seed provider config without secrets",
        )
        counts.provider_configs += 1

    if await providers.get_provider_config_by_provider("openrouter") is None:
        await providers.create_provider_config(
            provider="openrouter",
            display_name="OpenRouter (test)",
            base_url="https://openrouter.ai/api/v1",
            api_key_env_var="OPENROUTER_API_KEY",
            notes="Test seed provider config without secrets",
        )
        counts.provider_configs += 1

    existing_openai_route = await session.scalar(
        select(ModelRoute).where(ModelRoute.requested_model == "gpt-4.1-mini", ModelRoute.provider == "openai")
    )
    if existing_openai_route is None:
        await routes.create_model_route(
            requested_model="gpt-4.1-mini",
            provider="openai",
            upstream_model="gpt-4.1-mini",
            match_type="exact",
            endpoint="/v1/chat/completions",
            priority=10,
            notes="Seed route: OpenAI native model",
        )
        counts.model_routes += 1

    existing_or_route = await session.scalar(
        select(ModelRoute).where(
            ModelRoute.requested_model == "anthropic/*",
            ModelRoute.provider == "openrouter",
            ModelRoute.match_type == "glob",
        )
    )
    if existing_or_route is None:
        await routes.create_model_route(
            requested_model="anthropic/*",
            provider="openrouter",
            upstream_model="anthropic/claude-3.5-sonnet",
            match_type="glob",
            endpoint="/v1/chat/completions",
            priority=20,
            notes="Seed route: Anthropic-family via OpenRouter",
        )
        counts.model_routes += 1

    valid_from = datetime(2026, 1, 1, tzinfo=UTC)
    if await session.scalar(
        select(PricingRule).where(
            PricingRule.provider == "openai",
            PricingRule.upstream_model == "gpt-4.1-mini",
            PricingRule.valid_from == valid_from,
        )
    ) is None:
        await pricing.create_pricing_rule(
            provider="openai",
            upstream_model="gpt-4.1-mini",
            endpoint="/v1/chat/completions",
            valid_from=valid_from,
            currency="USD",
            input_price_per_1m=Decimal("0.120000000"),
            output_price_per_1m=Decimal("0.480000000"),
            request_price=Decimal("0.000000000"),
            notes="Dummy non-production price",
        )
        counts.pricing_rules += 1

    if await session.scalar(
        select(PricingRule).where(
            PricingRule.provider == "openrouter",
            PricingRule.upstream_model == "anthropic/claude-3.5-sonnet",
            PricingRule.valid_from == valid_from,
        )
    ) is None:
        await pricing.create_pricing_rule(
            provider="openrouter",
            upstream_model="anthropic/claude-3.5-sonnet",
            endpoint="/v1/chat/completions",
            valid_from=valid_from,
            currency="USD",
            input_price_per_1m=Decimal("0.300000000"),
            output_price_per_1m=Decimal("0.900000000"),
            notes="Dummy non-production price",
        )
        counts.pricing_rules += 1

    if await session.scalar(
        select(FxRate).where(
            FxRate.base_currency == "USD",
            FxRate.quote_currency == "EUR",
            FxRate.valid_from == valid_from,
        )
    ) is None:
        await fx_repo.create_fx_rate(
            base_currency="USD",
            quote_currency="EUR",
            rate=Decimal("0.920000000"),
            valid_from=valid_from,
            source="seed-test-data",
        )
        counts.fx_rates += 1

    if await session.scalar(select(GatewayKey).where(GatewayKey.public_key_id == "k_demo_non_usable")) is None:
        now = datetime.now(UTC)
        await keys.create_gateway_key_record(
            public_key_id="k_demo_non_usable",
            token_hash="hmac-sha256:demo-non-usable-token-digest",
            owner_id=owner.id,
            cohort_id=cohort.id,
            valid_from=now,
            valid_until=now + timedelta(days=7),
            status="suspended",
            key_prefix="sk-slaif",
            key_hint="...demo",
            created_by_admin_user_id=admin.id,
        )
        counts.gateway_keys += 1

    await session.commit()
    return counts


async def async_main() -> SeedResult:
    database_url = _validate_environment()
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with session_factory() as session:
            return await _seed(session)
    finally:
        await engine.dispose()


def main() -> None:
    result = asyncio.run(async_main())
    print(
        "Seed complete:",
        {
            "institutions": result.institutions,
            "cohorts": result.cohorts,
            "owners": result.owners,
            "admin_users": result.admin_users,
            "provider_configs": result.provider_configs,
            "model_routes": result.model_routes,
            "pricing_rules": result.pricing_rules,
            "fx_rates": result.fx_rates,
            "gateway_keys": result.gateway_keys,
        },
    )


if __name__ == "__main__":
    main()
