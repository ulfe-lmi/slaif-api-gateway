import asyncio
import re
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from slaif_gateway.config import Settings
from slaif_gateway.db.models import ModelRoute, ProviderConfig
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
                email=f"route-import-admin-{suffix}@example.org",
                display_name="Route Import Admin",
                password_hash=hash_admin_password("correct horse battery staple"),
                role="admin",
                is_active=True,
            )
            provider = await ProviderConfigsRepository(session).create_provider_config(
                provider=f"route-import-provider-{suffix}",
                display_name="Route Import Provider",
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


async def _provider_count(database_url: str, provider: str) -> int:
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        count = await session.scalar(
            select(func.count()).select_from(ProviderConfig).where(ProviderConfig.provider == provider)
        )
    await engine.dispose()
    return int(count or 0)


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


def test_admin_route_import_preview_postgres(migrated_postgres_url: str) -> None:
    data = asyncio.run(_create_admin_and_provider(migrated_postgres_url))
    suffix = uuid.uuid4().hex
    requested_model = f"route-import-{suffix}"
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
            "/admin/routes/import/preview",
            data={
                "import_format": "csv",
                "import_text": _valid_csv(str(data["provider"]), requested_model),
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

        import_page = client.get("/admin/routes/import")
        assert import_page.status_code == 200
        assert str(data["api_key_env_var"]) not in import_page.text
        assert provider_secret_value not in import_page.text

        without_csrf = client.post(
            "/admin/routes/import/preview",
            data={
                "import_format": "csv",
                "import_text": _valid_csv(str(data["provider"]), requested_model),
            },
        )
        assert without_csrf.status_code == 400
        assert asyncio.run(_route_count(migrated_postgres_url, requested_model)) == 0

        preview_page = client.get("/admin/routes/import")
        valid = client.post(
            "/admin/routes/import/preview",
            data={
                "csrf_token": _csrf_from_html(preview_page.text),
                "import_format": "csv",
                "import_text": _valid_csv(str(data["provider"]), requested_model),
            },
        )
        assert valid.status_code == 200
        assert "Route Import Preview Result" in valid.text
        assert requested_model in valid.text
        assert "create" in valid.text
        assert provider_secret_value not in valid.text
        assert "token_hash" not in valid.text
        assert "encrypted_payload" not in valid.text
        assert "nonce" not in valid.text
        assert "password_hash" not in valid.text
        assert "slaif_admin_session" not in valid.text
        assert asyncio.run(_route_count(migrated_postgres_url, requested_model)) == 0

        json_model = f"{requested_model}-json"
        preview_page = client.get("/admin/routes/import")
        json_preview = client.post(
            "/admin/routes/import/preview",
            data={
                "csrf_token": _csrf_from_html(preview_page.text),
                "import_format": "json",
                "import_text": (
                    '[{"requested_model":"'
                    + json_model
                    + '","match_type":"exact","provider":"'
                    + str(data["provider"])
                    + '","upstream_model":"'
                    + json_model
                    + '-upstream","priority":10}]'
                ),
            },
        )
        assert json_preview.status_code == 200
        assert json_model in json_preview.text
        assert asyncio.run(_route_count(migrated_postgres_url, json_model)) == 0

        bad_provider_model = f"{requested_model}-bad-provider"
        preview_page = client.get("/admin/routes/import")
        bad_provider = client.post(
            "/admin/routes/import/preview",
            data={
                "csrf_token": _csrf_from_html(preview_page.text),
                "import_format": "csv",
                "import_text": _valid_csv("missing-provider", bad_provider_model),
            },
        )
        assert bad_provider.status_code == 200
        assert "provider must reference an existing provider config" in bad_provider.text
        assert asyncio.run(_route_count(migrated_postgres_url, bad_provider_model)) == 0

        secret_value = "sk-provider-secret-in-upload"
        secret_model = f"{requested_model}-secret"
        preview_page = client.get("/admin/routes/import")
        secret_metadata = client.post(
            "/admin/routes/import/preview",
            data={
                "csrf_token": _csrf_from_html(preview_page.text),
                "import_format": "csv",
                "import_text": _valid_csv(
                    str(data["provider"]),
                    secret_model,
                    capabilities='{"api_key":"' + secret_value + '"}',
                ),
            },
        )
        assert secret_metadata.status_code == 200
        assert "capabilities must not contain secret-looking values" in secret_metadata.text
        assert secret_value not in secret_metadata.text
        assert asyncio.run(_route_count(migrated_postgres_url, secret_model)) == 0

        assert asyncio.run(_provider_count(migrated_postgres_url, str(data["provider"]))) == 1
