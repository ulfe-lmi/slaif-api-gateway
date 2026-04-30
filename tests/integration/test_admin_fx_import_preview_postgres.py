from __future__ import annotations

import asyncio
import re
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from slaif_gateway.config import Settings
from slaif_gateway.db.models import AuditLog, FxRate
from slaif_gateway.db.repositories.admin_users import AdminUsersRepository
from slaif_gateway.main import create_app
from slaif_gateway.utils.passwords import hash_admin_password


def _csrf_from_html(html: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert match is not None
    return match.group(1)


async def _create_admin(database_url: str) -> dict[str, object]:
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    suffix = uuid.uuid4().hex
    async with session_factory() as session:
        async with session.begin():
            admin = await AdminUsersRepository(session).create_admin_user(
                email=f"admin-fx-import-{suffix}@example.org",
                display_name="FX Import Admin",
                password_hash=hash_admin_password("correct horse battery staple"),
                role="admin",
                is_active=True,
            )
    await engine.dispose()
    return {
        "admin_email": admin.email,
        "admin_password": "correct horse battery staple",
    }


async def _fx_count(database_url: str) -> int:
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        count = await session.scalar(select(func.count()).select_from(FxRate))
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
        fx_rates = list((await session.execute(select(FxRate))).scalars().all())
        audits = list((await session.execute(select(AuditLog))).scalars().all())
        payload: list[str] = []
        for fx_rate in fx_rates:
            payload.append(
                " ".join(
                    str(value)
                    for value in (
                        fx_rate.base_currency,
                        fx_rate.quote_currency,
                        fx_rate.rate,
                        fx_rate.source,
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


def _valid_csv(base_currency: str = "USD", **overrides: str) -> str:
    row = {
        "base_currency": base_currency,
        "quote_currency": "EUR",
        "rate": "0.920000000",
        "valid_from": "2026-01-01T00:00:00+00:00",
        "source": "manual-local-fx",
        "notes": "safe fx note",
    }
    row.update(overrides)
    headers = list(row)
    return ",".join(headers) + "\n" + ",".join(row[name] for name in headers) + "\n"


def test_admin_fx_import_preview_postgres(migrated_postgres_url: str) -> None:
    data = asyncio.run(_create_admin(migrated_postgres_url))
    provider_secret_value = "sk-provider-secret-placeholder"
    settings = Settings(
        APP_ENV="test",
        DATABASE_URL=migrated_postgres_url,
        ADMIN_SESSION_SECRET="s" * 40,
        OPENAI_UPSTREAM_API_KEY=provider_secret_value,
        OPENROUTER_API_KEY="sk-or-provider-secret-placeholder",
    )
    app = create_app(settings)

    before_fx = asyncio.run(_fx_count(migrated_postgres_url))
    with TestClient(app) as client:
        unauthenticated = client.post(
            "/admin/fx/import/preview",
            data={"import_format": "csv", "import_text": _valid_csv()},
            follow_redirects=False,
        )
        assert unauthenticated.status_code == 303
        assert unauthenticated.headers["location"] == "/admin/login"
        assert asyncio.run(_fx_count(migrated_postgres_url)) == before_fx

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

        import_page = client.get("/admin/fx/import")
        assert import_page.status_code == 200
        assert "FX Import Preview" in import_page.text
        assert 'name="csrf_token"' in import_page.text

        without_csrf = client.post(
            "/admin/fx/import/preview",
            data={"import_format": "csv", "import_text": _valid_csv()},
        )
        assert without_csrf.status_code == 400
        assert asyncio.run(_fx_count(migrated_postgres_url)) == before_fx

        valid = client.post(
            "/admin/fx/import/preview",
            data={
                "csrf_token": _csrf_from_html(import_page.text),
                "import_format": "csv",
                "source_label": "manual-local-fx",
                "import_text": _valid_csv(),
            },
        )
        assert valid.status_code == 200
        assert "FX Import Preview Result" in valid.text
        assert "Valid rows" in valid.text
        assert "USD / EUR" in valid.text
        assert "Database writes" in valid.text
        assert provider_secret_value not in valid.text
        assert asyncio.run(_fx_count(migrated_postgres_url)) == before_fx

        import_page = client.get("/admin/fx/import")
        json_preview = client.post(
            "/admin/fx/import/preview",
            data={
                "csrf_token": _csrf_from_html(import_page.text),
                "import_format": "json",
                "import_text": (
                    '[{"base_currency":"GBP","quote_currency":"EUR","rate":"1.160000000",'
                    '"valid_from":"2026-01-01T00:00:00+00:00","source":"manual-local-fx"}]'
                ),
            },
        )
        assert json_preview.status_code == 200, json_preview.text
        assert "GBP / EUR" in json_preview.text
        assert asyncio.run(_fx_count(migrated_postgres_url)) == before_fx

        import_page = client.get("/admin/fx/import")
        invalid_currency = client.post(
            "/admin/fx/import/preview",
            data={
                "csrf_token": _csrf_from_html(import_page.text),
                "import_format": "csv",
                "import_text": _valid_csv(base_currency="USDX"),
            },
        )
        assert invalid_currency.status_code == 200
        assert "currency must be a 3-letter code" in invalid_currency.text
        assert asyncio.run(_fx_count(migrated_postgres_url)) == before_fx

        import_page = client.get("/admin/fx/import")
        same_currency = client.post(
            "/admin/fx/import/preview",
            data={
                "csrf_token": _csrf_from_html(import_page.text),
                "import_format": "csv",
                "import_text": _valid_csv(base_currency="EUR", quote_currency="EUR"),
            },
        )
        assert same_currency.status_code == 200
        assert "base_currency and quote_currency must differ" in same_currency.text
        assert asyncio.run(_fx_count(migrated_postgres_url)) == before_fx

        secret_value = "sk-provider-secret-in-upload"
        import_page = client.get("/admin/fx/import")
        secret_metadata = client.post(
            "/admin/fx/import/preview",
            data={
                "csrf_token": _csrf_from_html(import_page.text),
                "import_format": "csv",
                "import_text": _valid_csv(metadata='{"api_key":"' + secret_value + '"}'),
            },
        )
        assert secret_metadata.status_code == 200
        assert "metadata must not contain secret-looking values" in secret_metadata.text
        assert secret_value not in secret_metadata.text
        assert asyncio.run(_fx_count(migrated_postgres_url)) == before_fx

        combined_html = "\n".join([import_page.text, valid.text, json_preview.text, secret_metadata.text])
        assert provider_secret_value not in combined_html
        assert "sk-or-provider-secret-placeholder" not in combined_html
        assert "token_hash" not in combined_html
        assert "encrypted_payload" not in combined_html
        assert "nonce" not in combined_html
        assert "password_hash" not in combined_html
        assert "slaif_admin_session" not in combined_html

    assert asyncio.run(_fx_count(migrated_postgres_url)) == before_fx
    assert asyncio.run(_audit_count(migrated_postgres_url)) == before_audit
    database_text = asyncio.run(_database_safety_text(migrated_postgres_url))
    assert provider_secret_value not in database_text
    assert "sk-or-provider-secret-placeholder" not in database_text
    assert "sk-provider-secret-in-upload" not in database_text
