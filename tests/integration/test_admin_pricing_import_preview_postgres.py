from __future__ import annotations

import asyncio
import re
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from slaif_gateway.config import Settings
from slaif_gateway.db.models import AuditLog, PricingRule, ProviderConfig
from slaif_gateway.db.repositories.admin_users import AdminUsersRepository
from slaif_gateway.db.repositories.provider_configs import ProviderConfigsRepository
from slaif_gateway.main import create_app
from slaif_gateway.utils.passwords import hash_admin_password


def _csrf_from_html(html: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert match is not None
    return match.group(1)


async def _create_admin_and_provider(database_url: str) -> dict[str, object]:
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    suffix = uuid.uuid4().hex
    async with session_factory() as session:
        async with session.begin():
            admin = await AdminUsersRepository(session).create_admin_user(
                email=f"admin-pricing-import-{suffix}@example.org",
                display_name="Pricing Import Admin",
                password_hash=hash_admin_password("correct horse battery staple"),
                role="admin",
                is_active=True,
            )
            provider = await ProviderConfigsRepository(session).create_provider_config(
                provider=f"pricing-import-provider-{suffix}",
                display_name="Pricing Import Provider",
                kind="openai_compatible",
                base_url="https://provider.example.test/v1",
                api_key_env_var="OPENAI_UPSTREAM_API_KEY",
                enabled=True,
                timeout_seconds=120,
                max_retries=1,
                notes="safe provider metadata",
            )
    await engine.dispose()
    return {
        "admin_email": admin.email,
        "admin_password": "correct horse battery staple",
        "provider": provider.provider,
        "api_key_env_var": provider.api_key_env_var,
    }


async def _pricing_count(database_url: str) -> int:
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        count = await session.scalar(select(func.count()).select_from(PricingRule))
    await engine.dispose()
    return int(count or 0)


async def _audit_count(database_url: str) -> int:
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        count = await session.scalar(select(func.count()).select_from(AuditLog))
    await engine.dispose()
    return int(count or 0)


async def _database_safety_text(database_url: str) -> str:
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        pricing_rules = list((await session.execute(select(PricingRule))).scalars().all())
        providers = list((await session.execute(select(ProviderConfig))).scalars().all())
        audits = list((await session.execute(select(AuditLog))).scalars().all())
        payload: list[str] = []
        for pricing in pricing_rules:
            payload.append(
                " ".join(
                    str(value)
                    for value in (
                        pricing.provider,
                        pricing.upstream_model,
                        pricing.endpoint,
                        pricing.currency,
                        pricing.pricing_metadata,
                        pricing.source_url,
                        pricing.notes,
                    )
                )
            )
        for provider in providers:
            payload.append(
                " ".join(str(value) for value in (provider.provider, provider.api_key_env_var, provider.notes))
            )
        for audit in audits:
            payload.append(
                " ".join(
                    str(value)
                    for value in (
                        audit.action,
                        audit.entity_type,
                        audit.old_values,
                        audit.new_values,
                        audit.note,
                    )
                )
            )
    await engine.dispose()
    return "\n".join(payload)


def _valid_csv(provider: str, model: str) -> str:
    return (
        "provider,model,input_price_per_1m,output_price_per_1m,valid_from,source_url,notes\n"
        f"{provider},{model},0.100000000,0.200000000,2026-01-01T00:00:00+00:00,"
        "https://pricing.example.org/catalog,safe pricing note\n"
    )


def test_admin_pricing_import_preview_postgres(migrated_postgres_url: str) -> None:
    data = asyncio.run(_create_admin_and_provider(migrated_postgres_url))
    provider_secret_value = "sk-provider-secret-placeholder"
    model = f"pricing-import-{uuid.uuid4().hex}"
    settings = Settings(
        APP_ENV="test",
        DATABASE_URL=migrated_postgres_url,
        ADMIN_SESSION_SECRET="s" * 40,
        OPENAI_UPSTREAM_API_KEY=provider_secret_value,
        OPENROUTER_API_KEY="sk-or-provider-secret-placeholder",
    )
    app = create_app(settings)

    before_pricing = asyncio.run(_pricing_count(migrated_postgres_url))
    with TestClient(app) as client:
        unauthenticated = client.post(
            "/admin/pricing/import/preview",
            data={"import_format": "csv", "import_text": _valid_csv(str(data["provider"]), model)},
            follow_redirects=False,
        )
        assert unauthenticated.status_code == 303
        assert unauthenticated.headers["location"] == "/admin/login"
        assert asyncio.run(_pricing_count(migrated_postgres_url)) == before_pricing

        login_page = client.get("/admin/login")
        login = client.post(
            "/admin/login",
            data={
                "email": data["admin_email"],
                "password": data["admin_password"],
                "csrf_token": _csrf_from_html(login_page.text),
            },
            follow_redirects=False,
        )
        assert login.status_code == 303
        before_audit = asyncio.run(_audit_count(migrated_postgres_url))

        import_page = client.get("/admin/pricing/import")
        assert import_page.status_code == 200
        assert "Pricing Import Preview" in import_page.text
        assert 'name="csrf_token"' in import_page.text

        without_csrf = client.post(
            "/admin/pricing/import/preview",
            data={"import_format": "csv", "import_text": _valid_csv(str(data["provider"]), model)},
        )
        assert without_csrf.status_code == 400
        assert asyncio.run(_pricing_count(migrated_postgres_url)) == before_pricing

        valid = client.post(
            "/admin/pricing/import/preview",
            data={
                "csrf_token": _csrf_from_html(import_page.text),
                "import_format": "csv",
                "source_label": "manual-local-catalog",
                "import_text": _valid_csv(str(data["provider"]), model),
            },
        )
        assert valid.status_code == 200
        assert "Pricing Import Preview Result" in valid.text
        assert "Valid rows" in valid.text
        assert model in valid.text
        assert "Database writes" in valid.text
        assert provider_secret_value not in valid.text
        assert asyncio.run(_pricing_count(migrated_postgres_url)) == before_pricing

        import_page = client.get("/admin/pricing/import")
        json_preview = client.post(
            "/admin/pricing/import/preview",
            data={
                "csrf_token": _csrf_from_html(import_page.text),
                "import_format": "json",
                "import_text": (
                    f'[{{"provider":"{data["provider"]}","model":"{model}-json",'
                    '"input_price_per_1m":"0.100000000","output_price_per_1m":"0.200000000"}]'
                ),
            },
        )
        assert json_preview.status_code == 200, json_preview.text
        assert f"{model}-json" in json_preview.text
        assert asyncio.run(_pricing_count(migrated_postgres_url)) == before_pricing

        import_page = client.get("/admin/pricing/import")
        invalid = client.post(
            "/admin/pricing/import/preview",
            data={
                "csrf_token": _csrf_from_html(import_page.text),
                "import_format": "json",
                "import_text": (
                    f'[{{"provider":"{data["provider"]}","model":"{model}-bad",'
                    '"input_price_per_1m":"0.100000000","output_price_per_1m":"0.200000000",'
                    '"pricing_metadata":{"api_key":"sk-real-looking-secret"}}]'
                ),
            },
        )
        assert invalid.status_code == 200
        assert "Invalid rows" in invalid.text
        assert "pricing_metadata must not contain secret-looking values" in invalid.text
        assert "sk-real-looking-secret" not in invalid.text
        assert asyncio.run(_pricing_count(migrated_postgres_url)) == before_pricing

        combined_html = "\n".join([import_page.text, valid.text, json_preview.text, invalid.text])
        assert provider_secret_value not in combined_html
        assert "sk-or-provider-secret-placeholder" not in combined_html
        assert "token_hash" not in combined_html
        assert "encrypted_payload" not in combined_html
        assert "nonce" not in combined_html
        assert "password_hash" not in combined_html
        assert "slaif_admin_session" not in combined_html

    assert asyncio.run(_pricing_count(migrated_postgres_url)) == before_pricing
    assert asyncio.run(_audit_count(migrated_postgres_url)) == before_audit
    database_text = asyncio.run(_database_safety_text(migrated_postgres_url))
    assert provider_secret_value not in database_text
    assert "sk-or-provider-secret-placeholder" not in database_text
    assert "sk-real-looking-secret" not in database_text
