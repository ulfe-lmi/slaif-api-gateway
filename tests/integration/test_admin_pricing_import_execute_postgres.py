from __future__ import annotations

import asyncio
import re
import uuid
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from slaif_gateway.config import Settings
from slaif_gateway.db.models import AuditLog, PricingRule
from slaif_gateway.main import create_app
from tests.integration.test_admin_pricing_import_preview_postgres import _create_admin_and_provider


def _csrf_from_html(html: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert match is not None
    return match.group(1)


async def _pricing_count(database_url: str) -> int:
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        count = await session.scalar(select(func.count()).select_from(PricingRule))
    await engine.dispose()
    return int(count or 0)


async def _pricing_rows_for_model(database_url: str, model: str) -> list[PricingRule]:
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        rows = list(
            (
                await session.execute(
                    select(PricingRule).where(PricingRule.upstream_model == model).order_by(PricingRule.created_at)
                )
            )
            .scalars()
            .all()
        )
    await engine.dispose()
    return rows


async def _audit_rows(database_url: str) -> list[AuditLog]:
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        rows = list((await session.execute(select(AuditLog))).scalars().all())
    await engine.dispose()
    return rows


async def _database_safety_text(database_url: str) -> str:
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        pricing_rules = list((await session.execute(select(PricingRule))).scalars().all())
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
        "provider,model,input_price_per_1m,cached_input_price_per_1m,output_price_per_1m,"
        "request_price,valid_from,source_url,notes\n"
        f"{provider},{model},0.100000000,0.050000000,0.200000000,0.010000000,"
        "2026-01-01T00:00:00+00:00,https://pricing.example.org/catalog,safe pricing note\n"
    )


def _settings(database_url: str) -> Settings:
    return Settings(
        APP_ENV="test",
        DATABASE_URL=database_url,
        ADMIN_SESSION_SECRET="s" * 40,
        OPENAI_UPSTREAM_API_KEY="",
        OPENROUTER_API_KEY="",
    )


def _login(client: TestClient, *, email: str, password: str) -> None:
    login_page = client.get("/admin/login")
    login = client.post(
        "/admin/login",
        data={
            "email": email,
            "password": password,
            "csrf_token": _csrf_from_html(login_page.text),
        },
        follow_redirects=False,
    )
    assert login.status_code == 303


def test_admin_pricing_import_execute_postgres(migrated_postgres_url: str) -> None:
    data = asyncio.run(_create_admin_and_provider(migrated_postgres_url))
    provider_secret_value = "sk-provider-secret-placeholder"
    model = f"pricing-execute-{uuid.uuid4().hex}"
    app = create_app(_settings(migrated_postgres_url))
    before_pricing = asyncio.run(_pricing_count(migrated_postgres_url))

    with TestClient(app) as client:
        unauthenticated = client.post(
            "/admin/pricing/import/execute",
            data={
                "import_format": "csv",
                "import_text": _valid_csv(str(data["provider"]), model),
                "confirm_import": "true",
                "reason": "pricing import",
            },
            follow_redirects=False,
        )
        assert unauthenticated.status_code == 303
        assert asyncio.run(_pricing_count(migrated_postgres_url)) == before_pricing

        _login(client, email=str(data["admin_email"]), password=str(data["admin_password"]))

        import_page = client.get("/admin/pricing/import")
        preview = client.post(
            "/admin/pricing/import/preview",
            data={
                "csrf_token": _csrf_from_html(import_page.text),
                "import_format": "csv",
                "import_text": _valid_csv(str(data["provider"]), model),
            },
        )
        assert preview.status_code == 200
        assert asyncio.run(_pricing_count(migrated_postgres_url)) == before_pricing

        import_page = client.get("/admin/pricing/import")
        no_csrf = client.post(
            "/admin/pricing/import/execute",
            data={
                "import_format": "csv",
                "import_text": _valid_csv(str(data["provider"]), model),
                "confirm_import": "true",
                "reason": "pricing import",
            },
        )
        assert no_csrf.status_code == 400
        assert asyncio.run(_pricing_count(migrated_postgres_url)) == before_pricing

        missing_confirmation = client.post(
            "/admin/pricing/import/execute",
            data={
                "csrf_token": _csrf_from_html(import_page.text),
                "import_format": "csv",
                "import_text": _valid_csv(str(data["provider"]), model),
                "reason": "pricing import",
            },
        )
        assert missing_confirmation.status_code == 400
        assert asyncio.run(_pricing_count(migrated_postgres_url)) == before_pricing

        import_page = client.get("/admin/pricing/import")
        missing_reason = client.post(
            "/admin/pricing/import/execute",
            data={
                "csrf_token": _csrf_from_html(import_page.text),
                "import_format": "csv",
                "import_text": _valid_csv(str(data["provider"]), model),
                "confirm_import": "true",
            },
        )
        assert missing_reason.status_code == 400
        assert asyncio.run(_pricing_count(migrated_postgres_url)) == before_pricing

        import_page = client.get("/admin/pricing/import")
        invalid = client.post(
            "/admin/pricing/import/execute",
            data={
                "csrf_token": _csrf_from_html(import_page.text),
                "import_format": "json",
                "import_text": (
                    f'[{{"provider":"{data["provider"]}","model":"{model}-bad",'
                    '"input_price_per_1m":0.100000000,"output_price_per_1m":"0.200000000",'
                    '"unexpected":"nope"}}]'
                ),
                "confirm_import": "true",
                "reason": "pricing import",
            },
        )
        assert invalid.status_code == 400
        assert "unknown fields" in invalid.text or "decimal string" in invalid.text
        assert asyncio.run(_pricing_count(migrated_postgres_url)) == before_pricing

        import_page = client.get("/admin/pricing/import")
        secret_metadata = client.post(
            "/admin/pricing/import/execute",
            data={
                "csrf_token": _csrf_from_html(import_page.text),
                "import_format": "json",
                "import_text": (
                    f'[{{"provider":"{data["provider"]}","model":"{model}-secret",'
                    '"input_price_per_1m":"0.100000000","output_price_per_1m":"0.200000000",'
                    '"pricing_metadata":{"api_key":"sk-real-looking-secret"}}]'
                ),
                "confirm_import": "true",
                "reason": "pricing import",
            },
        )
        assert secret_metadata.status_code == 400
        assert "pricing_metadata must not contain secret-looking values" in secret_metadata.text
        assert "sk-real-looking-secret" not in secret_metadata.text
        assert asyncio.run(_pricing_count(migrated_postgres_url)) == before_pricing

        import_page = client.get("/admin/pricing/import")
        execute = client.post(
            "/admin/pricing/import/execute",
            data={
                "csrf_token": _csrf_from_html(import_page.text),
                "import_format": "csv",
                "source_label": "manual-local-catalog",
                "import_text": _valid_csv(str(data["provider"]), model),
                "confirm_import": "true",
                "reason": "pricing import",
            },
        )
        assert execute.status_code == 200, execute.text
        assert "Pricing Import Result" in execute.text
        assert "Created rows" in execute.text
        assert model in execute.text
        assert provider_secret_value not in execute.text

        rows = asyncio.run(_pricing_rows_for_model(migrated_postgres_url, model))
        assert len(rows) == 1
        assert rows[0].input_price_per_1m == Decimal("0.100000000")
        assert rows[0].cached_input_price_per_1m == Decimal("0.050000000")
        assert rows[0].output_price_per_1m == Decimal("0.200000000")
        assert rows[0].request_price == Decimal("0.010000000")

        import_page = client.get("/admin/pricing/import")
        duplicate = client.post(
            "/admin/pricing/import/execute",
            data={
                "csrf_token": _csrf_from_html(import_page.text),
                "import_format": "csv",
                "import_text": _valid_csv(str(data["provider"]), model),
                "confirm_import": "true",
                "reason": "pricing import",
            },
        )
        assert duplicate.status_code == 400
        assert "duplicate rows are not supported" in duplicate.text
        assert len(asyncio.run(_pricing_rows_for_model(migrated_postgres_url, model))) == 1

        import_page = client.get("/admin/pricing/import")
        json_model = f"{model}-json"
        json_execute = client.post(
            "/admin/pricing/import/execute",
            data={
                "csrf_token": _csrf_from_html(import_page.text),
                "import_format": "json",
                "import_text": (
                    f'[{{"provider":"{data["provider"]}","model":"{json_model}",'
                    '"input_price_per_1m":"0.300000000","output_price_per_1m":"0.400000000"}]'
                ),
                "confirm_import": "true",
                "reason": "pricing import",
            },
        )
        assert json_execute.status_code == 200, json_execute.text
        assert len(asyncio.run(_pricing_rows_for_model(migrated_postgres_url, json_model))) == 1

        combined_html = "\n".join(
            [
                import_page.text,
                preview.text,
                invalid.text,
                secret_metadata.text,
                execute.text,
                duplicate.text,
                json_execute.text,
            ]
        )
        assert provider_secret_value not in combined_html
        assert "sk-real-looking-secret" not in combined_html
        assert "token_hash" not in combined_html
        assert "encrypted_payload" not in combined_html
        assert "nonce" not in combined_html
        assert "password_hash" not in combined_html
        assert "slaif_admin_session" not in combined_html

    audit_rows = asyncio.run(_audit_rows(migrated_postgres_url))
    assert any(row.action == "pricing_rule_created" and row.note == "pricing import" for row in audit_rows)
    database_text = asyncio.run(_database_safety_text(migrated_postgres_url))
    assert provider_secret_value not in database_text
    assert "sk-real-looking-secret" not in database_text
    assert "provider,model,input_price_per_1m" not in database_text
