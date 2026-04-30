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
                email=f"route-import-execute-admin-{suffix}@example.org",
                display_name="Route Import Execute Admin",
                password_hash=hash_admin_password("correct horse battery staple"),
                role="admin",
                is_active=True,
            )
            provider = await ProviderConfigsRepository(session).create_provider_config(
                provider=f"route-import-execute-provider-{suffix}",
                display_name="Route Import Execute Provider",
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


async def _routes_for(database_url: str, requested_model: str) -> list[ModelRoute]:
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        result = await session.execute(select(ModelRoute).where(ModelRoute.requested_model == requested_model))
        rows = list(result.scalars().all())
    await engine.dispose()
    return rows


async def _route_count(database_url: str, requested_model: str) -> int:
    return len(await _routes_for(database_url, requested_model))


async def _provider_count(database_url: str, provider: str) -> int:
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        count = await session.scalar(
            select(func.count()).select_from(ProviderConfig).where(ProviderConfig.provider == provider)
        )
    await engine.dispose()
    return int(count or 0)


async def _audit_rows(database_url: str, requested_model: str) -> list[AuditLog]:
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        result = await session.execute(
            select(AuditLog).where(
                AuditLog.action == "model_route_created",
                AuditLog.entity_type == "model_route",
                AuditLog.new_values["requested_model"].as_string() == requested_model,
            )
        )
        rows = list(result.scalars().all())
    await engine.dispose()
    return rows


def _valid_csv(provider: str, requested_model: str, **overrides: str) -> str:
    row = {
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
        "notes": "safe route note",
    }
    row.update(overrides)
    headers = list(row)
    return ",".join(headers) + "\n" + ",".join(row[name] for name in headers) + "\n"


def test_admin_route_import_execute_postgres(migrated_postgres_url: str) -> None:
    data = asyncio.run(_create_admin_and_provider(migrated_postgres_url))
    suffix = uuid.uuid4().hex
    requested_model = f"route-import-execute-{suffix}"
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
            "/admin/routes/import/execute",
            data={
                "import_format": "csv",
                "import_text": _valid_csv(str(data["provider"]), requested_model),
                "confirm_import": "true",
                "reason": "route import",
            },
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

        preview_page = client.get("/admin/routes/import")
        preview = client.post(
            "/admin/routes/import/preview",
            data={
                "csrf_token": _csrf_from_html(preview_page.text),
                "import_format": "csv",
                "import_text": _valid_csv(str(data["provider"]), requested_model),
            },
        )
        assert preview.status_code == 200
        assert asyncio.run(_route_count(migrated_postgres_url, requested_model)) == 0

        without_csrf = client.post(
            "/admin/routes/import/execute",
            data={
                "import_format": "csv",
                "import_text": _valid_csv(str(data["provider"]), requested_model),
                "confirm_import": "true",
                "reason": "route import",
            },
        )
        assert without_csrf.status_code == 400
        assert asyncio.run(_route_count(migrated_postgres_url, requested_model)) == 0

        without_confirmation_page = client.get("/admin/routes/import")
        without_confirmation = client.post(
            "/admin/routes/import/execute",
            data={
                "csrf_token": _csrf_from_html(without_confirmation_page.text),
                "import_format": "csv",
                "import_text": _valid_csv(str(data["provider"]), requested_model),
                "reason": "route import",
            },
        )
        assert without_confirmation.status_code == 400
        assert "Confirm route import execution" in without_confirmation.text
        assert asyncio.run(_route_count(migrated_postgres_url, requested_model)) == 0

        without_reason_page = client.get("/admin/routes/import")
        without_reason = client.post(
            "/admin/routes/import/execute",
            data={
                "csrf_token": _csrf_from_html(without_reason_page.text),
                "import_format": "csv",
                "import_text": _valid_csv(str(data["provider"]), requested_model),
                "confirm_import": "true",
            },
        )
        assert without_reason.status_code == 400
        assert "Enter an audit reason" in without_reason.text
        assert asyncio.run(_route_count(migrated_postgres_url, requested_model)) == 0

        execute_page = client.get("/admin/routes/import")
        valid_execute = client.post(
            "/admin/routes/import/execute",
            data={
                "csrf_token": _csrf_from_html(execute_page.text),
                "import_format": "csv",
                "import_text": _valid_csv(str(data["provider"]), requested_model),
                "confirm_import": "true",
                "reason": "route import",
            },
        )
        assert valid_execute.status_code == 200
        assert "Route Import Result" in valid_execute.text
        assert "Created rows" in valid_execute.text
        assert provider_secret_value not in valid_execute.text
        assert "token_hash" not in valid_execute.text
        assert "encrypted_payload" not in valid_execute.text
        assert "nonce" not in valid_execute.text
        assert "password_hash" not in valid_execute.text
        assert "slaif_admin_session" not in valid_execute.text
        routes = asyncio.run(_routes_for(migrated_postgres_url, requested_model))
        assert len(routes) == 1
        assert routes[0].provider == data["provider"]
        assert routes[0].upstream_model == f"{requested_model}-upstream"
        assert routes[0].priority == 10
        audit_rows = asyncio.run(_audit_rows(migrated_postgres_url, requested_model))
        assert len(audit_rows) == 1
        assert "requested_model,match_type" not in str(audit_rows[0].new_values)

        invalid_model = f"{requested_model}-invalid"
        invalid_page = client.get("/admin/routes/import")
        invalid = client.post(
            "/admin/routes/import/execute",
            data={
                "csrf_token": _csrf_from_html(invalid_page.text),
                "import_format": "csv",
                "import_text": _valid_csv(str(data["provider"]), invalid_model, match_type="regex"),
                "confirm_import": "true",
                "reason": "route import",
            },
        )
        assert invalid.status_code == 400
        assert "match_type must be one of" in invalid.text
        assert asyncio.run(_route_count(migrated_postgres_url, invalid_model)) == 0

        bad_provider_model = f"{requested_model}-bad-provider"
        bad_provider_page = client.get("/admin/routes/import")
        bad_provider = client.post(
            "/admin/routes/import/execute",
            data={
                "csrf_token": _csrf_from_html(bad_provider_page.text),
                "import_format": "csv",
                "import_text": _valid_csv("missing-provider", bad_provider_model),
                "confirm_import": "true",
                "reason": "route import",
            },
        )
        assert bad_provider.status_code == 400
        assert "provider must reference an existing provider config" in bad_provider.text
        assert asyncio.run(_route_count(migrated_postgres_url, bad_provider_model)) == 0

        unknown_field_model = f"{requested_model}-unknown-field"
        unknown_field_page = client.get("/admin/routes/import")
        unknown_field = client.post(
            "/admin/routes/import/execute",
            data={
                "csrf_token": _csrf_from_html(unknown_field_page.text),
                "import_format": "csv",
                "import_text": _valid_csv(str(data["provider"]), unknown_field_model, unexpected="value"),
                "confirm_import": "true",
                "reason": "route import",
            },
        )
        assert unknown_field.status_code == 400
        assert "unknown fields" in unknown_field.text
        assert asyncio.run(_route_count(migrated_postgres_url, unknown_field_model)) == 0

        secret_value = "sk-provider-secret-in-upload"
        secret_model = f"{requested_model}-secret"
        secret_page = client.get("/admin/routes/import")
        secret_metadata = client.post(
            "/admin/routes/import/execute",
            data={
                "csrf_token": _csrf_from_html(secret_page.text),
                "import_format": "csv",
                "import_text": _valid_csv(
                    str(data["provider"]),
                    secret_model,
                    capabilities='{"api_key":"' + secret_value + '"}',
                ),
                "confirm_import": "true",
                "reason": "route import",
            },
        )
        assert secret_metadata.status_code == 400
        assert "capabilities must not contain secret-looking values" in secret_metadata.text
        assert secret_value not in secret_metadata.text
        assert asyncio.run(_route_count(migrated_postgres_url, secret_model)) == 0

        json_model = f"{requested_model}-json"
        json_page = client.get("/admin/routes/import")
        json_execute = client.post(
            "/admin/routes/import/execute",
            data={
                "csrf_token": _csrf_from_html(json_page.text),
                "import_format": "json",
                "import_text": (
                    '[{"requested_model":"'
                    + json_model
                    + '","match_type":"exact","provider":"'
                    + str(data["provider"])
                    + '","upstream_model":"'
                    + json_model
                    + '-upstream","priority":11}]'
                ),
                "confirm_import": "true",
                "reason": "route import",
            },
        )
        assert json_execute.status_code == 200
        json_routes = asyncio.run(_routes_for(migrated_postgres_url, json_model))
        assert len(json_routes) == 1
        assert json_routes[0].provider == data["provider"]

        duplicate_model = f"{requested_model}-duplicate"
        duplicate_page = client.get("/admin/routes/import")
        duplicate = client.post(
            "/admin/routes/import/execute",
            data={
                "csrf_token": _csrf_from_html(duplicate_page.text),
                "import_format": "csv",
                "import_text": _valid_csv(str(data["provider"]), duplicate_model)
                + _valid_csv(str(data["provider"]), duplicate_model).split("\n", 1)[1],
                "confirm_import": "true",
                "reason": "route import",
            },
        )
        assert duplicate.status_code == 400
        assert "duplicate rows are not supported" in duplicate.text
        assert asyncio.run(_route_count(migrated_postgres_url, duplicate_model)) == 0

        assert asyncio.run(_provider_count(migrated_postgres_url, str(data["provider"]))) == 1
