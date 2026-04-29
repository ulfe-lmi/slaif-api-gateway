import asyncio
import re
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from slaif_gateway.config import Settings
from slaif_gateway.db.models import AuditLog, ModelRoute, ProviderConfig
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
                display_name="Route Admin",
                password_hash=hash_admin_password("correct horse battery staple"),
                role="admin",
                is_active=True,
            )
            provider = await ProviderConfigsRepository(session).create_provider_config(
                provider=f"route-provider-{suffix}",
                display_name="Route Provider",
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


async def _route_count(database_url: str, requested_model: str) -> int:
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        count = await session.scalar(
            select(func.count()).select_from(ModelRoute).where(ModelRoute.requested_model == requested_model)
        )
    await engine.dispose()
    return int(count or 0)


async def _route_by_requested_model(database_url: str, requested_model: str) -> ModelRoute:
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        row = await session.scalar(select(ModelRoute).where(ModelRoute.requested_model == requested_model))
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


async def _database_safety_text(database_url: str, route_id: uuid.UUID) -> str:
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        routes = list((await session.execute(select(ModelRoute))).scalars().all())
        providers = list((await session.execute(select(ProviderConfig))).scalars().all())
        audits = list(
            (
                await session.execute(
                    select(AuditLog).where(
                        AuditLog.entity_type == "model_route",
                        AuditLog.entity_id == route_id,
                    )
                )
            )
            .scalars()
            .all()
        )
        payload = []
        for route in routes:
            payload.append(
                " ".join(
                    str(value)
                    for value in (
                        route.requested_model,
                        route.match_type,
                        route.endpoint,
                        route.provider,
                        route.upstream_model,
                        route.capabilities,
                        route.notes,
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


def _valid_form(provider: str, requested_model: str, **overrides) -> dict[str, str]:
    values = {
        "requested_model": requested_model,
        "match_type": "exact",
        "endpoint": "/v1/chat/completions",
        "provider": provider,
        "upstream_model": f"{requested_model}-upstream",
        "priority": "10",
        "enabled": "true",
        "visible_in_models": "true",
        "supports_streaming": "true",
        "capabilities": '{"vision": false}',
        "notes": "safe route metadata",
        "reason": "integration route setup",
    }
    values.update(overrides)
    return values


def test_admin_route_actions_postgres(migrated_postgres_url: str) -> None:
    data = asyncio.run(_create_admin_and_provider(migrated_postgres_url))
    suffix = uuid.uuid4().hex
    requested_model = f"dashboard-route-{suffix}"
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
            "/admin/routes/new",
            data=_valid_form(str(data["provider"]), requested_model),
            follow_redirects=False,
        )
        assert unauthenticated.status_code == 303
        assert unauthenticated.headers["location"] == "/admin/login"
        assert asyncio.run(_route_count(migrated_postgres_url, requested_model)) == 0

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

        create_page = client.get("/admin/routes/new")
        assert create_page.status_code == 200
        assert str(data["api_key_env_var"]) in create_page.text
        assert provider_secret_value not in create_page.text

        without_csrf = client.post(
            "/admin/routes/new",
            data=_valid_form(str(data["provider"]), requested_model),
        )
        assert without_csrf.status_code == 400
        assert asyncio.run(_route_count(migrated_postgres_url, requested_model)) == 0

        create_page = client.get("/admin/routes/new")
        invalid = client.post(
            "/admin/routes/new",
            data={
                **_valid_form(str(data["provider"]), requested_model, match_type="regex"),
                "csrf_token": _csrf_from_html(create_page.text),
            },
        )
        assert invalid.status_code == 400
        assert asyncio.run(_route_count(migrated_postgres_url, requested_model)) == 0

        create_page = client.get("/admin/routes/new")
        created = client.post(
            "/admin/routes/new",
            data={
                **_valid_form(str(data["provider"]), requested_model),
                "csrf_token": _csrf_from_html(create_page.text),
            },
            follow_redirects=False,
        )
        assert created.status_code == 303
        route = asyncio.run(_route_by_requested_model(migrated_postgres_url, requested_model))
        assert created.headers["location"] == f"/admin/routes/{route.id}?message=model_route_created"
        assert route.provider == data["provider"]
        assert route.capabilities == {"vision": False}
        audit_rows = asyncio.run(_audit_rows(migrated_postgres_url, route.id))
        assert "model_route_created" in {row.action for row in audit_rows}

        detail = client.get(f"/admin/routes/{route.id}")
        edit = client.get(f"/admin/routes/{route.id}/edit")
        assert detail.status_code == 200
        assert edit.status_code == 200
        assert route.upstream_model in detail.text
        assert str(data["api_key_env_var"]) in detail.text
        assert provider_secret_value not in detail.text
        assert provider_secret_value not in edit.text

        edited_model = f"{requested_model}-edited"
        edited = client.post(
            f"/admin/routes/{route.id}/edit",
            data={
                **_valid_form(
                    str(data["provider"]),
                    edited_model,
                    upstream_model=f"{edited_model}-upstream",
                    priority="20",
                    visible_in_models="",
                    supports_streaming="",
                    capabilities='{"json": true}',
                    notes="edited safe route metadata",
                    reason="integration route edit",
                ),
                "csrf_token": _csrf_from_html(edit.text),
            },
            follow_redirects=False,
        )
        assert edited.status_code == 303
        route = asyncio.run(_route_by_requested_model(migrated_postgres_url, edited_model))
        assert route.upstream_model == f"{edited_model}-upstream"
        assert route.priority == 20
        assert route.visible_in_models is False
        assert route.supports_streaming is False
        assert route.capabilities == {"json": True}

        edit = client.get(f"/admin/routes/{route.id}/edit")
        bad_secret_edit = client.post(
            f"/admin/routes/{route.id}/edit",
            data={
                **_valid_form(
                    str(data["provider"]),
                    edited_model,
                    capabilities='{"api_key": "sk-real-looking-secret"}',
                ),
                "csrf_token": _csrf_from_html(edit.text),
            },
        )
        assert bad_secret_edit.status_code == 400
        unchanged = asyncio.run(_route_by_requested_model(migrated_postgres_url, edited_model))
        assert unchanged.capabilities == {"json": True}

        detail = client.get(f"/admin/routes/{route.id}")
        disable_without_confirmation = client.post(
            f"/admin/routes/{route.id}/disable",
            data={
                "csrf_token": _csrf_from_html(detail.text),
                "reason": "maintenance",
            },
            follow_redirects=False,
        )
        assert disable_without_confirmation.status_code == 303
        assert asyncio.run(_route_by_requested_model(migrated_postgres_url, edited_model)).enabled is True

        detail = client.get(f"/admin/routes/{route.id}")
        disabled = client.post(
            f"/admin/routes/{route.id}/disable",
            data={
                "csrf_token": _csrf_from_html(detail.text),
                "confirm_disable": "true",
                "reason": "maintenance",
            },
            follow_redirects=False,
        )
        assert disabled.status_code == 303
        assert asyncio.run(_route_by_requested_model(migrated_postgres_url, edited_model)).enabled is False

        detail = client.get(f"/admin/routes/{route.id}")
        enabled = client.post(
            f"/admin/routes/{route.id}/enable",
            data={
                "csrf_token": _csrf_from_html(detail.text),
                "reason": "back online",
            },
            follow_redirects=False,
        )
        assert enabled.status_code == 303
        assert asyncio.run(_route_by_requested_model(migrated_postgres_url, edited_model)).enabled is True

        combined_html = "\n".join(
            [
                client.get("/admin/routes").text,
                client.get("/admin/routes/new").text,
                client.get(f"/admin/routes/{route.id}").text,
                client.get(f"/admin/routes/{route.id}/edit").text,
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

    audit_rows = asyncio.run(_audit_rows(migrated_postgres_url, route.id))
    actions = {row.action for row in audit_rows}
    assert "model_route_updated" in actions
    assert "model_route_disabled" in actions
    assert "model_route_enabled" in actions

    database_text = asyncio.run(_database_safety_text(migrated_postgres_url, route.id))
    assert provider_secret_value not in database_text
    assert "sk-or-provider-secret-placeholder" not in database_text
    assert "sk-real-looking-secret" not in database_text
    assert "api_key_value" not in database_text
    assert "token_hash" not in database_text
    assert "encrypted_payload" not in database_text
    assert "nonce" not in database_text
