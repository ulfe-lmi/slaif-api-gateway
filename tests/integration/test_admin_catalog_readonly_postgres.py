import asyncio
import re
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from slaif_gateway.config import Settings
from slaif_gateway.db.models import FxRate, ModelRoute, PricingRule, ProviderConfig
from slaif_gateway.db.repositories.admin_users import AdminUsersRepository
from slaif_gateway.db.repositories.fx_rates import FxRatesRepository
from slaif_gateway.db.repositories.pricing import PricingRulesRepository
from slaif_gateway.db.repositories.provider_configs import ProviderConfigsRepository
from slaif_gateway.db.repositories.routing import ModelRoutesRepository
from slaif_gateway.main import create_app
from slaif_gateway.utils.passwords import hash_admin_password


def _csrf_from_html(html: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert match is not None
    return match.group(1)


async def _create_admin_catalog(database_url: str) -> dict[str, object]:
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(UTC)
    suffix = uuid.uuid4().hex
    async with session_factory() as session:
        async with session.begin():
            admin = await AdminUsersRepository(session).create_admin_user(
                email=f"admin-{uuid.uuid4()}@example.org",
                display_name="Integration Admin",
                password_hash=hash_admin_password("correct horse battery staple"),
                role="admin",
                is_active=True,
            )
            provider = await ProviderConfigsRepository(session).create_provider_config(
                provider=f"catalog-openai-{suffix}",
                display_name="Catalog OpenAI",
                kind="openai_compatible",
                base_url="https://api.openai.example/v1",
                api_key_env_var="OPENAI_UPSTREAM_API_KEY",
                enabled=True,
                timeout_seconds=120,
                max_retries=1,
                notes="safe provider note",
            )
            route = await ModelRoutesRepository(session).create_model_route(
                requested_model=f"catalog-gpt-{suffix}",
                match_type="exact",
                endpoint="/v1/chat/completions",
                provider=provider.provider,
                upstream_model=f"upstream-gpt-{suffix}",
                priority=10,
                enabled=True,
                visible_in_models=True,
                supports_streaming=True,
                capabilities={"vision": False},
                notes="safe route note",
            )
            pricing = await PricingRulesRepository(session).create_pricing_rule(
                provider=provider.provider,
                upstream_model=route.upstream_model,
                endpoint=route.endpoint,
                currency="EUR",
                input_price_per_1m=Decimal("0.100000000"),
                cached_input_price_per_1m=Decimal("0.050000000"),
                output_price_per_1m=Decimal("0.200000000"),
                reasoning_price_per_1m=None,
                request_price=None,
                pricing_metadata={"source": "manual"},
                valid_from=now - timedelta(days=1),
                valid_until=None,
                enabled=True,
                source_url="https://pricing.example.org/catalog",
                notes="safe pricing note",
            )
            fx = await FxRatesRepository(session).create_fx_rate(
                base_currency="USD",
                quote_currency="EUR",
                rate=Decimal("0.920000000"),
                valid_from=now - timedelta(days=1),
                valid_until=None,
                source=f"manual-catalog-{suffix}",
            )
            payload = {
                "admin_email": admin.email,
                "admin_password": "correct horse battery staple",
                "provider_id": provider.id,
                "provider": provider.provider,
                "provider_updated_at": provider.updated_at,
                "api_key_env_var": provider.api_key_env_var,
                "route_id": route.id,
                "requested_model": route.requested_model,
                "upstream_model": route.upstream_model,
                "route_updated_at": route.updated_at,
                "pricing_id": pricing.id,
                "pricing_updated_at": pricing.updated_at,
                "fx_id": fx.id,
                "fx_created_at": fx.created_at,
                "fx_source": fx.source,
            }
    await engine.dispose()
    return payload


async def _get_catalog_rows(
    database_url: str,
    provider_id: uuid.UUID,
    route_id: uuid.UUID,
    pricing_id: uuid.UUID,
    fx_id: uuid.UUID,
) -> dict[str, object]:
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        provider = await session.get(ProviderConfig, provider_id)
        route = await session.get(ModelRoute, route_id)
        pricing = await session.get(PricingRule, pricing_id)
        fx = await session.get(FxRate, fx_id)
        assert provider is not None
        assert route is not None
        assert pricing is not None
        assert fx is not None
        payload = {
            "provider_updated_at": provider.updated_at,
            "route_updated_at": route.updated_at,
            "pricing_updated_at": pricing.updated_at,
            "fx_created_at": fx.created_at,
        }
    await engine.dispose()
    return payload


def test_admin_catalog_readonly_pages(migrated_postgres_url: str) -> None:
    data = asyncio.run(_create_admin_catalog(migrated_postgres_url))
    settings = Settings(
        APP_ENV="test",
        DATABASE_URL=migrated_postgres_url,
        ADMIN_SESSION_SECRET="s" * 40,
        OPENAI_UPSTREAM_API_KEY="sk-provider-secret-placeholder",
        OPENROUTER_API_KEY="sk-or-provider-secret-placeholder",
    )
    app = create_app(settings)

    with TestClient(app) as client:
        for path in ("/admin/providers", "/admin/routes", "/admin/pricing", "/admin/fx"):
            unauthenticated = client.get(path, follow_redirects=False)
            assert unauthenticated.status_code == 303
            assert unauthenticated.headers["location"] == "/admin/login"

        login_page = client.get("/admin/login")
        csrf = _csrf_from_html(login_page.text)
        login = client.post(
            "/admin/login",
            data={
                "email": data["admin_email"],
                "password": data["admin_password"],
                "csrf_token": csrf,
            },
            follow_redirects=False,
        )
        assert login.status_code == 303

        providers = client.get("/admin/providers")
        assert providers.status_code == 200
        assert data["provider"] in providers.text
        assert data["api_key_env_var"] in providers.text

        provider_filtered = client.get(
            "/admin/providers",
            params={"provider": data["provider"], "enabled": "true"},
        )
        assert provider_filtered.status_code == 200
        assert data["provider"] in provider_filtered.text

        provider_detail = client.get(f"/admin/providers/{data['provider_id']}")
        assert provider_detail.status_code == 200
        assert data["upstream_model"] in provider_detail.text

        routes = client.get("/admin/routes")
        assert routes.status_code == 200
        assert data["requested_model"] in routes.text

        route_filtered = client.get(
            "/admin/routes",
            params={
                "provider": data["provider"],
                "requested_model": "catalog-gpt",
                "match_type": "exact",
                "enabled": "true",
                "visible": "true",
            },
        )
        assert route_filtered.status_code == 200
        assert data["requested_model"] in route_filtered.text

        route_detail = client.get(f"/admin/routes/{data['route_id']}")
        assert route_detail.status_code == 200
        assert data["upstream_model"] in route_detail.text
        assert data["api_key_env_var"] in route_detail.text

        pricing = client.get("/admin/pricing")
        assert pricing.status_code == 200
        assert data["upstream_model"] in pricing.text

        pricing_filtered = client.get(
            "/admin/pricing",
            params={
                "provider": data["provider"],
                "model": "upstream-gpt",
                "endpoint": "/v1/chat/completions",
                "currency": "EUR",
                "enabled": "true",
                "active": "true",
            },
        )
        assert pricing_filtered.status_code == 200
        assert data["upstream_model"] in pricing_filtered.text

        pricing_detail = client.get(f"/admin/pricing/{data['pricing_id']}")
        assert pricing_detail.status_code == 200
        assert "0.100000000" in pricing_detail.text

        fx = client.get("/admin/fx")
        assert fx.status_code == 200
        assert data["fx_source"] in fx.text

        fx_filtered = client.get(
            "/admin/fx",
            params={
                "base_currency": "USD",
                "quote_currency": "EUR",
                "source": data["fx_source"],
                "active": "true",
            },
        )
        assert fx_filtered.status_code == 200
        assert data["fx_source"] in fx_filtered.text

        fx_detail = client.get(f"/admin/fx/{data['fx_id']}")
        assert fx_detail.status_code == 200
        assert "0.920000000" in fx_detail.text

        combined = "\n".join(
            [
                providers.text,
                provider_detail.text,
                routes.text,
                route_detail.text,
                pricing.text,
                pricing_detail.text,
                fx.text,
                fx_detail.text,
            ]
        )
        assert settings.OPENAI_UPSTREAM_API_KEY not in combined
        assert settings.OPENROUTER_API_KEY not in combined
        assert "token_hash" not in combined
        assert "encrypted_payload" not in combined
        assert "nonce" not in combined
        assert "password_hash" not in combined
        assert "slaif_admin_session" not in combined
        assert "prompt text must not render" not in combined
        assert "completion text must not render" not in combined

        assert client.get("/admin/providers/not-a-uuid").status_code == 404
        assert client.get(f"/admin/providers/{uuid.uuid4()}").status_code == 404
        assert client.get("/admin/routes/not-a-uuid").status_code == 404
        assert client.get(f"/admin/routes/{uuid.uuid4()}").status_code == 404
        assert client.get("/admin/pricing/not-a-uuid").status_code == 404
        assert client.get(f"/admin/pricing/{uuid.uuid4()}").status_code == 404
        assert client.get("/admin/fx/not-a-uuid").status_code == 404
        assert client.get(f"/admin/fx/{uuid.uuid4()}").status_code == 404

    after = asyncio.run(
        _get_catalog_rows(
            migrated_postgres_url,
            data["provider_id"],
            data["route_id"],
            data["pricing_id"],
            data["fx_id"],
        )
    )
    assert after["provider_updated_at"] == data["provider_updated_at"]
    assert after["route_updated_at"] == data["route_updated_at"]
    assert after["pricing_updated_at"] == data["pricing_updated_at"]
    assert after["fx_created_at"] == data["fx_created_at"]
