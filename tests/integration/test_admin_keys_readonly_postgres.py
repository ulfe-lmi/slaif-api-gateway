import asyncio
import re
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from slaif_gateway.config import Settings
from slaif_gateway.db.models import GatewayKey
from slaif_gateway.db.repositories.admin_users import AdminUsersRepository
from slaif_gateway.db.repositories.cohorts import CohortsRepository
from slaif_gateway.db.repositories.institutions import InstitutionsRepository
from slaif_gateway.db.repositories.keys import GatewayKeysRepository
from slaif_gateway.db.repositories.owners import OwnersRepository
from slaif_gateway.main import create_app
from slaif_gateway.utils.passwords import hash_admin_password


def _csrf_from_html(html: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert match is not None
    return match.group(1)


async def _create_admin_and_keys(database_url: str) -> dict[str, object]:
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(UTC)
    async with session_factory() as session:
        async with session.begin():
            admin = await AdminUsersRepository(session).create_admin_user(
                email=f"admin-{uuid.uuid4()}@example.org",
                display_name="Integration Admin",
                password_hash=hash_admin_password("correct horse battery staple"),
                role="admin",
                is_active=True,
            )
            institution = await InstitutionsRepository(session).create_institution(
                name=f"SLAIF University {uuid.uuid4()}",
                country="SI",
            )
            cohort = await CohortsRepository(session).create_cohort(
                name=f"Workshop {uuid.uuid4()}",
                starts_at=now - timedelta(days=1),
                ends_at=now + timedelta(days=30),
            )
            owner = await OwnersRepository(session).create_owner(
                name="Ada",
                surname="Lovelace",
                email=f"owner-{uuid.uuid4()}@example.org",
                institution_id=institution.id,
            )
            active_key = await GatewayKeysRepository(session).create_gateway_key_record(
                public_key_id=f"public-{uuid.uuid4()}",
                token_hash="token_hash_must_not_render_" + uuid.uuid4().hex,
                owner_id=owner.id,
                cohort_id=cohort.id,
                valid_from=now - timedelta(days=1),
                valid_until=now + timedelta(days=30),
                key_hint="sk-slaif-public-hint",
                cost_limit_eur=Decimal("12.000000000"),
                token_limit_total=1200,
                request_limit_total=120,
                allowed_models=["gpt-test"],
                allowed_endpoints=["/v1/chat/completions"],
                rate_limit_requests_per_minute=30,
                rate_limit_tokens_per_minute=1000,
                max_concurrent_requests=2,
                metadata_json={"allowed_providers": ["openai"], "rate_limit_policy": {"window_seconds": 60}},
                created_by_admin_user_id=admin.id,
            )
            expired_key = await GatewayKeysRepository(session).create_gateway_key_record(
                public_key_id=f"expired-{uuid.uuid4()}",
                token_hash="expired_token_hash_must_not_render_" + uuid.uuid4().hex,
                owner_id=owner.id,
                valid_from=now - timedelta(days=30),
                valid_until=now - timedelta(days=1),
                key_hint="sk-slaif-expired-hint",
                allowed_models=["gpt-test"],
                allowed_endpoints=["/v1/chat/completions"],
            )
            payload = {
                "admin_email": admin.email,
                "admin_password": "correct horse battery staple",
                "active_key_id": active_key.id,
                "active_public_key_id": active_key.public_key_id,
                "active_token_hash": active_key.token_hash,
                "expired_public_key_id": expired_key.public_key_id,
                "owner_email": owner.email,
                "owner_name": f"{owner.name} {owner.surname}",
                "institution_name": institution.name,
                "cohort_name": cohort.name,
                "key_status": active_key.status,
                "key_updated_at": active_key.updated_at,
            }
    await engine.dispose()
    return payload


async def _get_key(database_url: str, gateway_key_id: uuid.UUID) -> GatewayKey:
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        key = await session.get(GatewayKey, gateway_key_id)
        assert key is not None
    await engine.dispose()
    return key


def test_admin_keys_readonly_pages(migrated_postgres_url: str) -> None:
    data = asyncio.run(_create_admin_and_keys(migrated_postgres_url))
    settings = Settings(
        APP_ENV="test",
        DATABASE_URL=migrated_postgres_url,
        ADMIN_SESSION_SECRET="s" * 40,
    )
    app = create_app(settings)

    with TestClient(app) as client:
        unauthenticated = client.get("/admin/keys", follow_redirects=False)
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

        list_page = client.get("/admin/keys")
        assert list_page.status_code == 200
        assert data["active_public_key_id"] in list_page.text
        assert data["expired_public_key_id"] in list_page.text
        assert data["owner_email"] in list_page.text
        assert data["owner_name"] in list_page.text
        assert data["institution_name"] in list_page.text
        assert data["cohort_name"] in list_page.text
        assert "token_hash" not in list_page.text
        assert data["active_token_hash"] not in list_page.text

        filtered = client.get(
            "/admin/keys",
            params={"public_key_id": data["active_public_key_id"], "owner_email": data["owner_email"]},
        )
        assert filtered.status_code == 200
        assert data["active_public_key_id"] in filtered.text
        assert data["expired_public_key_id"] not in filtered.text

        expired_filtered = client.get("/admin/keys", params={"expired": "true"})
        assert expired_filtered.status_code == 200
        assert data["expired_public_key_id"] in expired_filtered.text
        assert "expired" in expired_filtered.text

        detail = client.get(f"/admin/keys/{data['active_key_id']}")
        assert detail.status_code == 200
        assert data["active_public_key_id"] in detail.text
        assert "gpt-test" in detail.text
        assert "/v1/chat/completions" in detail.text
        assert "openai" in detail.text
        assert "Plaintext keys" in detail.text
        assert "token_hash" not in detail.text
        assert data["active_token_hash"] not in detail.text
        assert "encrypted_payload" not in detail.text
        assert "nonce" not in detail.text

        invalid = client.get("/admin/keys/not-a-uuid")
        missing = client.get(f"/admin/keys/{uuid.uuid4()}")
        assert invalid.status_code == 404
        assert missing.status_code == 404

    key_after_gets = asyncio.run(_get_key(migrated_postgres_url, data["active_key_id"]))
    assert key_after_gets.status == data["key_status"]
    assert key_after_gets.updated_at == data["key_updated_at"]
