import asyncio
import re
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from slaif_gateway.config import Settings
from slaif_gateway.db.models import AuditLog, ProviderConfig
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
                display_name="Provider Admin",
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


async def _provider_count(database_url: str, provider: str) -> int:
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        count = await session.scalar(
            select(func.count()).select_from(ProviderConfig).where(ProviderConfig.provider == provider)
        )
    await engine.dispose()
    return int(count or 0)


async def _provider_by_name(database_url: str, provider: str) -> ProviderConfig:
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        row = await session.scalar(select(ProviderConfig).where(ProviderConfig.provider == provider))
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


async def _database_safety_text(database_url: str, provider_id: uuid.UUID) -> str:
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        providers = list((await session.execute(select(ProviderConfig))).scalars().all())
        audits = list(
            (
                await session.execute(
                    select(AuditLog).where(
                        AuditLog.entity_type == "provider_config",
                        AuditLog.entity_id == provider_id,
                    )
                )
            )
            .scalars()
            .all()
        )
        payload = []
        for provider in providers:
            payload.append(
                " ".join(
                    str(value)
                    for value in (
                        provider.provider,
                        provider.display_name,
                        provider.kind,
                        provider.base_url,
                        provider.api_key_env_var,
                        provider.notes,
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


def _valid_form(provider: str, **overrides) -> dict[str, str]:
    values = {
        "provider": provider,
        "display_name": "Integration Provider",
        "kind": "openai_compatible",
        "base_url": "https://provider.example.test/v1",
        "api_key_env_var": "OPENAI_UPSTREAM_API_KEY",
        "enabled": "true",
        "timeout_seconds": "120",
        "max_retries": "1",
        "notes": "safe provider metadata",
        "reason": "integration provider setup",
    }
    values.update(overrides)
    return values


def test_admin_provider_config_actions_postgres(migrated_postgres_url: str) -> None:
    admin = asyncio.run(_create_admin(migrated_postgres_url))
    suffix = uuid.uuid4().hex
    provider_name = f"dashboard-provider-{suffix}"
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
            "/admin/providers/new",
            data=_valid_form(provider_name),
            follow_redirects=False,
        )
        assert unauthenticated.status_code == 303
        assert unauthenticated.headers["location"] == "/admin/login"
        assert asyncio.run(_provider_count(migrated_postgres_url, provider_name)) == 0

        login_page = client.get("/admin/login")
        login = client.post(
            "/admin/login",
            data={
                "email": admin["admin_email"],
                "password": admin["admin_password"],
                "csrf_token": _csrf_from_html(login_page.text),
            },
            follow_redirects=False,
        )
        assert login.status_code == 303

        create_page = client.get("/admin/providers/new")
        assert create_page.status_code == 200
        assert "api_key_env_var" in create_page.text
        assert provider_secret_value not in create_page.text

        without_csrf = client.post(
            "/admin/providers/new",
            data=_valid_form(provider_name),
        )
        assert without_csrf.status_code == 400
        assert asyncio.run(_provider_count(migrated_postgres_url, provider_name)) == 0

        create_page = client.get("/admin/providers/new")
        invalid = client.post(
            "/admin/providers/new",
            data={
                **_valid_form(provider_name, timeout_seconds="-1"),
                "csrf_token": _csrf_from_html(create_page.text),
            },
        )
        assert invalid.status_code == 400
        assert asyncio.run(_provider_count(migrated_postgres_url, provider_name)) == 0

        create_page = client.get("/admin/providers/new")
        created = client.post(
            "/admin/providers/new",
            data={
                **_valid_form(provider_name),
                "csrf_token": _csrf_from_html(create_page.text),
            },
            follow_redirects=False,
        )
        assert created.status_code == 303
        provider = asyncio.run(_provider_by_name(migrated_postgres_url, provider_name))
        assert created.headers["location"] == f"/admin/providers/{provider.id}?message=provider_config_created"
        assert provider.api_key_env_var == "OPENAI_UPSTREAM_API_KEY"
        assert provider_secret_value not in provider.api_key_env_var
        audit_rows = asyncio.run(_audit_rows(migrated_postgres_url, provider.id))
        assert "provider_config_created" in {row.action for row in audit_rows}

        detail = client.get(f"/admin/providers/{provider.id}")
        edit = client.get(f"/admin/providers/{provider.id}/edit")
        assert detail.status_code == 200
        assert edit.status_code == 200
        assert provider.api_key_env_var in detail.text
        assert provider_secret_value not in detail.text
        assert provider_secret_value not in edit.text

        edited = client.post(
            f"/admin/providers/{provider.id}/edit",
            data={
                **_valid_form(
                    provider_name,
                    display_name="Edited Provider",
                    api_key_env_var="OPENROUTER_API_KEY",
                    timeout_seconds="90",
                    max_retries="0",
                    notes="edited safe metadata",
                    reason="integration provider edit",
                ),
                "csrf_token": _csrf_from_html(edit.text),
            },
            follow_redirects=False,
        )
        assert edited.status_code == 303
        provider = asyncio.run(_provider_by_name(migrated_postgres_url, provider_name))
        assert provider.display_name == "Edited Provider"
        assert provider.api_key_env_var == "OPENROUTER_API_KEY"
        assert provider.timeout_seconds == 90
        assert provider.max_retries == 0

        edit = client.get(f"/admin/providers/{provider.id}/edit")
        bad_secret_edit = client.post(
            f"/admin/providers/{provider.id}/edit",
            data={
                **_valid_form(provider_name, api_key_env_var="sk-real-looking-secret"),
                "csrf_token": _csrf_from_html(edit.text),
            },
        )
        assert bad_secret_edit.status_code == 400
        unchanged = asyncio.run(_provider_by_name(migrated_postgres_url, provider_name))
        assert unchanged.api_key_env_var == "OPENROUTER_API_KEY"

        detail = client.get(f"/admin/providers/{provider.id}")
        disable_without_confirmation = client.post(
            f"/admin/providers/{provider.id}/disable",
            data={
                "csrf_token": _csrf_from_html(detail.text),
                "reason": "maintenance",
            },
            follow_redirects=False,
        )
        assert disable_without_confirmation.status_code == 303
        assert asyncio.run(_provider_by_name(migrated_postgres_url, provider_name)).enabled is True

        detail = client.get(f"/admin/providers/{provider.id}")
        disabled = client.post(
            f"/admin/providers/{provider.id}/disable",
            data={
                "csrf_token": _csrf_from_html(detail.text),
                "confirm_disable": "true",
                "reason": "maintenance",
            },
            follow_redirects=False,
        )
        assert disabled.status_code == 303
        assert asyncio.run(_provider_by_name(migrated_postgres_url, provider_name)).enabled is False

        detail = client.get(f"/admin/providers/{provider.id}")
        enabled = client.post(
            f"/admin/providers/{provider.id}/enable",
            data={
                "csrf_token": _csrf_from_html(detail.text),
                "reason": "back online",
            },
            follow_redirects=False,
        )
        assert enabled.status_code == 303
        assert asyncio.run(_provider_by_name(migrated_postgres_url, provider_name)).enabled is True

        combined_html = "\n".join(
            [
                client.get("/admin/providers").text,
                client.get(f"/admin/providers/{provider.id}").text,
                client.get(f"/admin/providers/{provider.id}/edit").text,
            ]
        )
        assert provider_name in combined_html
        assert "OPENROUTER_API_KEY" in combined_html
        assert provider_secret_value not in combined_html
        assert "sk-or-provider-secret-placeholder" not in combined_html
        assert "token_hash" not in combined_html
        assert "encrypted_payload" not in combined_html
        assert "nonce" not in combined_html
        assert "password_hash" not in combined_html
        assert "slaif_admin_session" not in combined_html

    audit_rows = asyncio.run(_audit_rows(migrated_postgres_url, provider.id))
    actions = {row.action for row in audit_rows}
    assert "provider_config_updated" in actions
    assert "provider_config_disabled" in actions
    assert "provider_config_enabled" in actions

    database_text = asyncio.run(_database_safety_text(migrated_postgres_url, provider.id))
    assert provider_secret_value not in database_text
    assert "sk-or-provider-secret-placeholder" not in database_text
    assert "sk-real-looking-secret" not in database_text
    assert "api_key_value" not in database_text
    assert "token_hash" not in database_text
    assert "encrypted_payload" not in database_text
    assert "nonce" not in database_text
