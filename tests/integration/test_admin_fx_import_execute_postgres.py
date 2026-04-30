from __future__ import annotations

import asyncio
import re
import string
import uuid
from decimal import Decimal

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
                email=f"admin-fx-execute-{suffix}@example.org",
                display_name="FX Execute Admin",
                password_hash=hash_admin_password("correct horse battery staple"),
                role="admin",
                is_active=True,
            )
    await engine.dispose()
    return {
        "admin_email": admin.email,
        "admin_password": "correct horse battery staple",
    }


async def _fx_rows(database_url: str) -> list[FxRate]:
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        rows = list((await session.execute(select(FxRate).order_by(FxRate.created_at))).scalars().all())
    await engine.dispose()
    return rows


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


def _currency() -> str:
    alphabet = string.ascii_uppercase
    number = uuid.uuid4().int
    return "".join(alphabet[(number >> shift) % len(alphabet)] for shift in (0, 8, 16))


def test_admin_fx_import_execute_postgres(migrated_postgres_url: str) -> None:
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
    preview_base = _currency()
    execute_base = _currency()
    json_base = _currency()

    before_fx = asyncio.run(_fx_count(migrated_postgres_url))
    with TestClient(app) as client:
        unauthenticated = client.post(
            "/admin/fx/import/execute",
            data={
                "import_format": "csv",
                "import_text": _valid_csv(),
                "confirm_import": "true",
                "reason": "safe audit reason",
            },
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
        preview = client.post(
            "/admin/fx/import/preview",
            data={
                "csrf_token": _csrf_from_html(import_page.text),
                "import_format": "csv",
                "import_text": _valid_csv(preview_base),
            },
        )
        assert preview.status_code == 200
        assert asyncio.run(_fx_count(migrated_postgres_url)) == before_fx

        without_csrf = client.post(
            "/admin/fx/import/execute",
            data={
                "import_format": "csv",
                "import_text": _valid_csv(),
                "confirm_import": "true",
                "reason": "safe audit reason",
            },
        )
        assert without_csrf.status_code == 400
        assert asyncio.run(_fx_count(migrated_postgres_url)) == before_fx

        no_confirmation = client.post(
            "/admin/fx/import/execute",
            data={
                "csrf_token": _csrf_from_html(import_page.text),
                "import_format": "csv",
                "import_text": _valid_csv(),
                "reason": "safe audit reason",
            },
        )
        assert no_confirmation.status_code == 400
        assert asyncio.run(_fx_count(migrated_postgres_url)) == before_fx

        no_reason = client.post(
            "/admin/fx/import/execute",
            data={
                "csrf_token": _csrf_from_html(import_page.text),
                "import_format": "csv",
                "import_text": _valid_csv(),
                "confirm_import": "true",
            },
        )
        assert no_reason.status_code == 400
        assert asyncio.run(_fx_count(migrated_postgres_url)) == before_fx

        execute = client.post(
            "/admin/fx/import/execute",
            data={
                "csrf_token": _csrf_from_html(import_page.text),
                "import_format": "csv",
                "source_label": "manual-local-fx",
                "import_text": _valid_csv(execute_base),
                "confirm_import": "true",
                "reason": "safe audit reason",
            },
        )
        assert execute.status_code == 200, execute.text
        assert "FX Import Result" in execute.text
        assert "FX import completed" in execute.text
        assert "Created rows" in execute.text
        assert provider_secret_value not in execute.text

        rows = asyncio.run(_fx_rows(migrated_postgres_url))
        assert len(rows) == before_fx + 1
        created = rows[-1]
        assert created.base_currency == execute_base
        assert created.quote_currency == "EUR"
        assert created.rate == Decimal("0.920000000")
        assert created.source == "manual-local-fx"
        assert asyncio.run(_audit_count(migrated_postgres_url)) == before_audit + 1

        import_page = client.get("/admin/fx/import")
        json_execute = client.post(
            "/admin/fx/import/execute",
            data={
                "csrf_token": _csrf_from_html(import_page.text),
                "import_format": "json",
                "import_text": (
                    f'[{{"base_currency":"{json_base}","quote_currency":"EUR","rate":"1.160000000",'
                    '"valid_from":"2026-01-01T00:00:00+00:00","source":"manual-local-fx"}]'
                ),
                "confirm_import": "true",
                "reason": "safe JSON import reason",
            },
        )
        assert json_execute.status_code == 200, json_execute.text
        assert f"{json_base} / EUR" in json_execute.text
        assert asyncio.run(_fx_count(migrated_postgres_url)) == before_fx + 2

        invalid_payloads = [
            _valid_csv(base_currency="AUD", rate="not-decimal"),
            _valid_csv(base_currency="USDX"),
            _valid_csv(base_currency="EUR", quote_currency="EUR"),
            _valid_csv(base_currency="CAD", unknown="value"),
            _valid_csv(base_currency="CHF", metadata='{"api_key":"sk-provider-secret-in-upload"}'),
        ]
        for payload in invalid_payloads:
            import_page = client.get("/admin/fx/import")
            invalid = client.post(
                "/admin/fx/import/execute",
                data={
                    "csrf_token": _csrf_from_html(import_page.text),
                    "import_format": "csv",
                    "import_text": payload,
                    "confirm_import": "true",
                    "reason": "safe audit reason",
                },
            )
            assert invalid.status_code == 400
            assert "Import blocked" in invalid.text or "unknown fields" in invalid.text
            assert asyncio.run(_fx_count(migrated_postgres_url)) == before_fx + 2
            assert "sk-provider-secret-in-upload" not in invalid.text

        import_page = client.get("/admin/fx/import")
        numeric_json = client.post(
            "/admin/fx/import/execute",
            data={
                "csrf_token": _csrf_from_html(import_page.text),
                "import_format": "json",
                "import_text": '[{"base_currency":"JPY","quote_currency":"EUR","rate":0.0062}]',
                "confirm_import": "true",
                "reason": "safe audit reason",
            },
        )
        assert numeric_json.status_code == 400
        assert "rate must be a decimal string" in numeric_json.text
        assert asyncio.run(_fx_count(migrated_postgres_url)) == before_fx + 2

        combined_html = "\n".join([preview.text, execute.text, json_execute.text, numeric_json.text])
        assert provider_secret_value not in combined_html
        assert "sk-or-provider-secret-placeholder" not in combined_html
        assert "token_hash" not in combined_html
        assert "encrypted_payload" not in combined_html
        assert "nonce" not in combined_html
        assert "password_hash" not in combined_html
        assert "slaif_admin_session" not in combined_html

    database_text = asyncio.run(_database_safety_text(migrated_postgres_url))
    assert provider_secret_value not in database_text
    assert "sk-or-provider-secret-placeholder" not in database_text
    assert "sk-provider-secret-in-upload" not in database_text
    assert "base_currency,quote_currency,rate" not in database_text
    assert "safe fx note" not in database_text
