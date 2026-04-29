import asyncio
import re
import uuid
from decimal import Decimal

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
                email=f"admin-{uuid.uuid4()}@example.org",
                display_name="Pricing Admin",
                password_hash=hash_admin_password("correct horse battery staple"),
                role="admin",
                is_active=True,
            )
            provider = await ProviderConfigsRepository(session).create_provider_config(
                provider=f"pricing-provider-{suffix}",
                display_name="Pricing Provider",
                kind="openai_compatible",
                base_url="https://provider.example.test/v1",
                api_key_env_var="OPENAI_UPSTREAM_API_KEY",
                enabled=True,
                timeout_seconds=120,
                max_retries=1,
                notes="safe provider metadata",
            )
            payload = {
                "admin_email": admin.email,
                "admin_password": "correct horse battery staple",
                "provider": provider.provider,
                "provider_id": provider.id,
                "api_key_env_var": provider.api_key_env_var,
            }
    await engine.dispose()
    return payload


async def _pricing_count(database_url: str, model: str) -> int:
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        count = await session.scalar(
            select(func.count()).select_from(PricingRule).where(PricingRule.upstream_model == model)
        )
    await engine.dispose()
    return int(count or 0)


async def _pricing_by_model(database_url: str, model: str) -> PricingRule:
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        row = await session.scalar(select(PricingRule).where(PricingRule.upstream_model == model))
        assert row is not None
        session.expunge(row)
    await engine.dispose()
    return row


async def _audit_rows(database_url: str, entity_id: uuid.UUID) -> list[AuditLog]:
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        result = await session.execute(select(AuditLog).where(AuditLog.entity_id == entity_id))
        rows = list(result.scalars().all())
        for row in rows:
            session.expunge(row)
    await engine.dispose()
    return rows


async def _database_safety_text(database_url: str, pricing_rule_id: uuid.UUID) -> str:
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        pricing_rules = list((await session.execute(select(PricingRule))).scalars().all())
        providers = list((await session.execute(select(ProviderConfig))).scalars().all())
        audits = list(
            (
                await session.execute(
                    select(AuditLog).where(
                        AuditLog.entity_type == "pricing_rule",
                        AuditLog.entity_id == pricing_rule_id,
                    )
                )
            )
            .scalars()
            .all()
        )
        payload = []
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


def _valid_form(provider: str, model: str, **overrides) -> dict[str, str]:
    values = {
        "provider": provider,
        "upstream_model": model,
        "endpoint": "/v1/chat/completions",
        "currency": "EUR",
        "input_price_per_1m": "0.100000000",
        "cached_input_price_per_1m": "0.050000000",
        "output_price_per_1m": "0.200000000",
        "reasoning_price_per_1m": "",
        "request_price": "0",
        "pricing_metadata": '{"source": "manual"}',
        "valid_from": "2026-01-01T00:00:00+00:00",
        "valid_until": "",
        "enabled": "true",
        "source_url": "https://pricing.example.org/catalog",
        "notes": "safe pricing metadata",
        "reason": "integration pricing setup",
    }
    values.update(overrides)
    return values


def test_admin_pricing_actions_postgres(migrated_postgres_url: str) -> None:
    data = asyncio.run(_create_admin_and_provider(migrated_postgres_url))
    suffix = uuid.uuid4().hex
    model = f"dashboard-pricing-{suffix}"
    provider_secret_value = "sk-provider-secret-placeholder"
    settings = Settings(
        APP_ENV="test",
        DATABASE_URL=migrated_postgres_url,
        ADMIN_SESSION_SECRET="s" * 40,
        OPENAI_UPSTREAM_API_KEY=provider_secret_value,
        OPENROUTER_API_KEY="sk-or-provider-secret-placeholder",
    )
    app = create_app(settings)

    with TestClient(app) as client:
        unauthenticated = client.post(
            "/admin/pricing/new",
            data=_valid_form(str(data["provider"]), model),
            follow_redirects=False,
        )
        assert unauthenticated.status_code == 303
        assert unauthenticated.headers["location"] == "/admin/login"
        assert asyncio.run(_pricing_count(migrated_postgres_url, model)) == 0

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

        create_page = client.get("/admin/pricing/new")
        assert create_page.status_code == 200
        assert str(data["api_key_env_var"]) in create_page.text
        assert provider_secret_value not in create_page.text

        without_csrf = client.post(
            "/admin/pricing/new",
            data=_valid_form(str(data["provider"]), model),
        )
        assert without_csrf.status_code == 400
        assert asyncio.run(_pricing_count(migrated_postgres_url, model)) == 0

        create_page = client.get("/admin/pricing/new")
        invalid = client.post(
            "/admin/pricing/new",
            data={
                **_valid_form(str(data["provider"]), model, input_price_per_1m="not-decimal"),
                "csrf_token": _csrf_from_html(create_page.text),
            },
        )
        assert invalid.status_code == 400
        assert asyncio.run(_pricing_count(migrated_postgres_url, model)) == 0

        create_page = client.get("/admin/pricing/new")
        created = client.post(
            "/admin/pricing/new",
            data={
                **_valid_form(str(data["provider"]), model),
                "csrf_token": _csrf_from_html(create_page.text),
            },
            follow_redirects=False,
        )
        assert created.status_code == 303
        pricing = asyncio.run(_pricing_by_model(migrated_postgres_url, model))
        assert created.headers["location"] == f"/admin/pricing/{pricing.id}?message=pricing_rule_created"
        assert pricing.provider == data["provider"]
        assert pricing.input_price_per_1m == Decimal("0.100000000")
        assert pricing.output_price_per_1m == Decimal("0.200000000")
        assert pricing.request_price == Decimal("0E-9")
        assert pricing.pricing_metadata == {"source": "manual"}
        audit_rows = asyncio.run(_audit_rows(migrated_postgres_url, pricing.id))
        assert "pricing_rule_created" in {row.action for row in audit_rows}

        detail = client.get(f"/admin/pricing/{pricing.id}")
        edit = client.get(f"/admin/pricing/{pricing.id}/edit")
        assert detail.status_code == 200
        assert edit.status_code == 200
        assert pricing.upstream_model in detail.text
        assert str(data["api_key_env_var"]) in detail.text
        assert provider_secret_value not in detail.text
        assert provider_secret_value not in edit.text

        edited_model = f"{model}-edited"
        edited = client.post(
            f"/admin/pricing/{pricing.id}/edit",
            data={
                **_valid_form(
                    str(data["provider"]),
                    edited_model,
                    input_price_per_1m="0.300000000",
                    output_price_per_1m="0.400000000",
                    request_price="0.010000000",
                    currency="USD",
                    pricing_metadata='{"source": "updated"}',
                    notes="edited safe pricing metadata",
                    reason="integration pricing edit",
                ),
                "csrf_token": _csrf_from_html(edit.text),
            },
            follow_redirects=False,
        )
        assert edited.status_code == 303
        pricing = asyncio.run(_pricing_by_model(migrated_postgres_url, edited_model))
        assert pricing.currency == "USD"
        assert pricing.input_price_per_1m == Decimal("0.300000000")
        assert pricing.output_price_per_1m == Decimal("0.400000000")
        assert pricing.request_price == Decimal("0.010000000")
        assert pricing.pricing_metadata == {"source": "updated"}

        edit = client.get(f"/admin/pricing/{pricing.id}/edit")
        invalid_edit = client.post(
            f"/admin/pricing/{pricing.id}/edit",
            data={
                **_valid_form(
                    str(data["provider"]),
                    edited_model,
                    currency="EURO",
                ),
                "csrf_token": _csrf_from_html(edit.text),
            },
        )
        assert invalid_edit.status_code == 400
        unchanged = asyncio.run(_pricing_by_model(migrated_postgres_url, edited_model))
        assert unchanged.currency == "USD"

        edit = client.get(f"/admin/pricing/{pricing.id}/edit")
        bad_secret_edit = client.post(
            f"/admin/pricing/{pricing.id}/edit",
            data={
                **_valid_form(
                    str(data["provider"]),
                    edited_model,
                    pricing_metadata='{"api_key": "sk-real-looking-secret"}',
                ),
                "csrf_token": _csrf_from_html(edit.text),
            },
        )
        assert bad_secret_edit.status_code == 400
        unchanged = asyncio.run(_pricing_by_model(migrated_postgres_url, edited_model))
        assert unchanged.pricing_metadata == {"source": "updated"}

        detail = client.get(f"/admin/pricing/{pricing.id}")
        disable_without_confirmation = client.post(
            f"/admin/pricing/{pricing.id}/disable",
            data={
                "csrf_token": _csrf_from_html(detail.text),
                "reason": "maintenance",
            },
            follow_redirects=False,
        )
        assert disable_without_confirmation.status_code == 303
        assert asyncio.run(_pricing_by_model(migrated_postgres_url, edited_model)).enabled is True

        detail = client.get(f"/admin/pricing/{pricing.id}")
        disabled = client.post(
            f"/admin/pricing/{pricing.id}/disable",
            data={
                "csrf_token": _csrf_from_html(detail.text),
                "confirm_disable": "true",
                "reason": "maintenance",
            },
            follow_redirects=False,
        )
        assert disabled.status_code == 303
        assert asyncio.run(_pricing_by_model(migrated_postgres_url, edited_model)).enabled is False

        detail = client.get(f"/admin/pricing/{pricing.id}")
        enabled = client.post(
            f"/admin/pricing/{pricing.id}/enable",
            data={
                "csrf_token": _csrf_from_html(detail.text),
                "reason": "back online",
            },
            follow_redirects=False,
        )
        assert enabled.status_code == 303
        assert asyncio.run(_pricing_by_model(migrated_postgres_url, edited_model)).enabled is True

        combined_html = "\n".join(
            [
                client.get("/admin/pricing").text,
                client.get("/admin/pricing/new").text,
                client.get(f"/admin/pricing/{pricing.id}").text,
                client.get(f"/admin/pricing/{pricing.id}/edit").text,
            ]
        )
        assert edited_model in combined_html
        assert str(data["api_key_env_var"]) in combined_html
        assert provider_secret_value not in combined_html
        assert "sk-or-provider-secret-placeholder" not in combined_html
        assert "token_hash" not in combined_html
        assert "encrypted_payload" not in combined_html
        assert "nonce" not in combined_html
        assert "password_hash" not in combined_html
        assert "slaif_admin_session" not in combined_html

    audit_rows = asyncio.run(_audit_rows(migrated_postgres_url, pricing.id))
    actions = {row.action for row in audit_rows}
    assert "pricing_rule_updated" in actions
    assert "pricing_rule_disabled" in actions
    assert "pricing_rule_enabled" in actions

    database_text = asyncio.run(_database_safety_text(migrated_postgres_url, pricing.id))
    assert provider_secret_value not in database_text
    assert "sk-or-provider-secret-placeholder" not in database_text
    assert "sk-real-looking-secret" not in database_text
    assert "api_key_value" not in database_text
    assert "token_hash" not in database_text
    assert "encrypted_payload" not in database_text
    assert "nonce" not in database_text
