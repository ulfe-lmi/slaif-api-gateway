import asyncio
import re
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
    async with session_factory() as session:
        async with session.begin():
            admin = await AdminUsersRepository(session).create_admin_user(
                email=f"admin-{uuid.uuid4()}@example.org",
                display_name="FX Admin",
                password_hash=hash_admin_password("correct horse battery staple"),
                role="admin",
                is_active=True,
            )
            payload = {
                "admin_email": admin.email,
                "admin_password": "correct horse battery staple",
            }
    await engine.dispose()
    return payload


async def _fx_count(database_url: str, source: str) -> int:
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        count = await session.scalar(select(func.count()).select_from(FxRate).where(FxRate.source == source))
    await engine.dispose()
    return int(count or 0)


async def _fx_by_source(database_url: str, source: str) -> FxRate:
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        row = await session.scalar(select(FxRate).where(FxRate.source == source))
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


async def _database_safety_text(database_url: str, fx_rate_id: uuid.UUID) -> str:
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        fx_rates = list((await session.execute(select(FxRate))).scalars().all())
        audits = list(
            (
                await session.execute(
                    select(AuditLog).where(AuditLog.entity_type == "fx_rate", AuditLog.entity_id == fx_rate_id)
                )
            )
            .scalars()
            .all()
        )
        payload = []
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


def _valid_form(source: str, **overrides) -> dict[str, str]:
    values = {
        "base_currency": "USD",
        "quote_currency": "EUR",
        "rate": "0.920000000",
        "valid_from": "2026-01-01T00:00:00+00:00",
        "valid_until": "",
        "source": source,
        "reason": "integration fx setup",
    }
    values.update(overrides)
    return values


def test_admin_fx_actions_postgres(migrated_postgres_url: str) -> None:
    data = asyncio.run(_create_admin(migrated_postgres_url))
    suffix = uuid.uuid4().hex
    source = f"dashboard-fx-{suffix}"
    valid_from = f"2026-01-01T00:00:00.{int(suffix[:6], 16) % 1_000_000:06d}+00:00"
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
            "/admin/fx/new",
            data=_valid_form(source, valid_from=valid_from),
            follow_redirects=False,
        )
        assert unauthenticated.status_code == 303
        assert unauthenticated.headers["location"] == "/admin/login"
        assert asyncio.run(_fx_count(migrated_postgres_url, source)) == 0

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

        create_page = client.get("/admin/fx/new")
        assert create_page.status_code == 200
        assert provider_secret_value not in create_page.text

        without_csrf = client.post("/admin/fx/new", data=_valid_form(source, valid_from=valid_from))
        assert without_csrf.status_code == 400
        assert asyncio.run(_fx_count(migrated_postgres_url, source)) == 0

        create_page = client.get("/admin/fx/new")
        invalid = client.post(
            "/admin/fx/new",
            data={
                **_valid_form(source, rate="not-decimal", valid_from=valid_from),
                "csrf_token": _csrf_from_html(create_page.text),
            },
        )
        assert invalid.status_code == 400
        assert asyncio.run(_fx_count(migrated_postgres_url, source)) == 0

        create_page = client.get("/admin/fx/new")
        created = client.post(
            "/admin/fx/new",
            data={**_valid_form(source, valid_from=valid_from), "csrf_token": _csrf_from_html(create_page.text)},
            follow_redirects=False,
        )
        assert created.status_code == 303
        fx_rate = asyncio.run(_fx_by_source(migrated_postgres_url, source))
        assert created.headers["location"] == f"/admin/fx/{fx_rate.id}?message=fx_rate_created"
        assert fx_rate.base_currency == "USD"
        assert fx_rate.quote_currency == "EUR"
        assert fx_rate.rate == Decimal("0.920000000")
        audit_rows = asyncio.run(_audit_rows(migrated_postgres_url, fx_rate.id))
        assert "fx_rate_created" in {row.action for row in audit_rows}

        detail = client.get(f"/admin/fx/{fx_rate.id}")
        edit = client.get(f"/admin/fx/{fx_rate.id}/edit")
        assert detail.status_code == 200
        assert edit.status_code == 200
        assert source in detail.text
        assert provider_secret_value not in detail.text
        assert provider_secret_value not in edit.text
        assert f"/admin/fx/{fx_rate.id}/enable" not in detail.text
        assert f"/admin/fx/{fx_rate.id}/disable" not in detail.text

        edited_source = f"{source}-edited"
        edited = client.post(
            f"/admin/fx/{fx_rate.id}/edit",
            data={
                **_valid_form(
                    edited_source,
                    base_currency="GBP",
                    rate="1.160000000",
                    valid_from=valid_from,
                    reason="integration fx edit",
                ),
                "csrf_token": _csrf_from_html(edit.text),
            },
            follow_redirects=False,
        )
        assert edited.status_code == 303
        fx_rate = asyncio.run(_fx_by_source(migrated_postgres_url, edited_source))
        assert fx_rate.base_currency == "GBP"
        assert fx_rate.quote_currency == "EUR"
        assert fx_rate.rate == Decimal("1.160000000")

        edit = client.get(f"/admin/fx/{fx_rate.id}/edit")
        invalid_currency = client.post(
            f"/admin/fx/{fx_rate.id}/edit",
            data={
                **_valid_form(edited_source, base_currency="USDX", valid_from=valid_from),
                "csrf_token": _csrf_from_html(edit.text),
            },
        )
        assert invalid_currency.status_code == 400
        unchanged = asyncio.run(_fx_by_source(migrated_postgres_url, edited_source))
        assert unchanged.base_currency == "GBP"

        edit = client.get(f"/admin/fx/{fx_rate.id}/edit")
        same_pair = client.post(
            f"/admin/fx/{fx_rate.id}/edit",
            data={
                **_valid_form(edited_source, base_currency="EUR", quote_currency="EUR", valid_from=valid_from),
                "csrf_token": _csrf_from_html(edit.text),
            },
        )
        assert same_pair.status_code == 400
        unchanged = asyncio.run(_fx_by_source(migrated_postgres_url, edited_source))
        assert unchanged.base_currency == "GBP"

        edit = client.get(f"/admin/fx/{fx_rate.id}/edit")
        secret_source = client.post(
            f"/admin/fx/{fx_rate.id}/edit",
            data={
                **_valid_form("sk-real-looking-secret", valid_from=valid_from),
                "csrf_token": _csrf_from_html(edit.text),
            },
        )
        assert secret_source.status_code == 400
        unchanged = asyncio.run(_fx_by_source(migrated_postgres_url, edited_source))
        assert unchanged.source == edited_source

        combined_html = "\n".join(
            [
                client.get("/admin/fx").text,
                client.get("/admin/fx/new").text,
                client.get(f"/admin/fx/{fx_rate.id}").text,
                client.get(f"/admin/fx/{fx_rate.id}/edit").text,
            ]
        )
        assert edited_source in combined_html
        assert provider_secret_value not in combined_html
        assert "sk-or-provider-secret-placeholder" not in combined_html
        assert "token_hash" not in combined_html
        assert "encrypted_payload" not in combined_html
        assert "nonce" not in combined_html
        assert "password_hash" not in combined_html
        assert "slaif_admin_session" not in combined_html

    audit_rows = asyncio.run(_audit_rows(migrated_postgres_url, fx_rate.id))
    assert "fx_rate_updated" in {row.action for row in audit_rows}

    database_text = asyncio.run(_database_safety_text(migrated_postgres_url, fx_rate.id))
    assert provider_secret_value not in database_text
    assert "sk-or-provider-secret-placeholder" not in database_text
    assert "sk-real-looking-secret" not in database_text
    assert "api_key_value" not in database_text
    assert "token_hash" not in database_text
    assert "encrypted_payload" not in database_text
    assert "nonce" not in database_text
