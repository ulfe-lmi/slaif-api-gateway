import asyncio
import re
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from slaif_gateway.config import Settings
from slaif_gateway.db.models import AuditLog, GatewayKey
from slaif_gateway.db.repositories.admin_users import AdminUsersRepository
from slaif_gateway.db.repositories.audit import AuditRepository
from slaif_gateway.db.repositories.cohorts import CohortsRepository
from slaif_gateway.db.repositories.institutions import InstitutionsRepository
from slaif_gateway.db.repositories.keys import GatewayKeysRepository
from slaif_gateway.db.repositories.one_time_secrets import OneTimeSecretsRepository
from slaif_gateway.db.repositories.owners import OwnersRepository
from slaif_gateway.main import create_app
from slaif_gateway.schemas.keys import CreateGatewayKeyInput
from slaif_gateway.services.key_service import KeyService
from slaif_gateway.utils.passwords import hash_admin_password
from slaif_gateway.utils.secrets import generate_secret_key


def _csrf_from_html(html: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert match is not None
    return match.group(1)


def _settings(database_url: str, *, one_time_secret_key: str | None = None) -> Settings:
    return Settings(
        APP_ENV="test",
        DATABASE_URL=database_url,
        ADMIN_SESSION_SECRET="s" * 40,
        TOKEN_HMAC_SECRET="hmac-secret-for-admin-key-actions-tests",
        ONE_TIME_SECRET_ENCRYPTION_KEY=one_time_secret_key or generate_secret_key(),
        OPENAI_UPSTREAM_API_KEY="sk-provider-secret-placeholder",
        OPENROUTER_API_KEY="sk-or-provider-secret-placeholder",
    )


async def _create_admin_and_key(database_url: str) -> dict[str, object]:
    settings = _settings(database_url)
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(UTC)
    try:
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
                key_service = KeyService(
                    settings=settings,
                    gateway_keys_repository=GatewayKeysRepository(session),
                    one_time_secrets_repository=OneTimeSecretsRepository(session),
                    audit_repository=AuditRepository(session),
                )
                created = await key_service.create_gateway_key(
                    CreateGatewayKeyInput(
                        owner_id=owner.id,
                        cohort_id=cohort.id,
                        valid_from=now - timedelta(days=1),
                        valid_until=now + timedelta(days=30),
                        created_by_admin_id=admin.id,
                        cost_limit_eur=Decimal("12.000000000"),
                        token_limit_total=1200,
                        request_limit_total=120,
                        allowed_models=["gpt-test"],
                        allowed_endpoints=["/v1/chat/completions"],
                        note="integration setup",
                    )
                )
                key = await session.get(GatewayKey, created.gateway_key_id)
                assert key is not None
                return {
                    "admin_email": admin.email,
                    "admin_password": "correct horse battery staple",
                    "gateway_key_id": key.id,
                    "public_key_id": key.public_key_id,
                    "plaintext_key": created.plaintext_key,
                    "token_hash": key.token_hash,
                    "one_time_secret_key": settings.ONE_TIME_SECRET_ENCRYPTION_KEY,
                }
    finally:
        await engine.dispose()


async def _get_key(database_url: str, gateway_key_id: uuid.UUID) -> GatewayKey:
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        key = await session.get(GatewayKey, gateway_key_id)
        assert key is not None
    await engine.dispose()
    return key


async def _audit_actions(database_url: str, gateway_key_id: uuid.UUID) -> list[str]:
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        result = await session.execute(
            select(AuditLog.action)
            .where(AuditLog.entity_id == gateway_key_id)
            .order_by(AuditLog.created_at.asc())
        )
        actions = list(result.scalars().all())
    await engine.dispose()
    return actions


def _assert_safe_html(html: str, data: dict[str, object], settings: Settings) -> None:
    assert str(data["public_key_id"]) in html
    assert str(data["plaintext_key"]) not in html
    assert str(data["token_hash"]) not in html
    assert "token_hash" not in html
    assert "encrypted_payload" not in html
    assert "nonce" not in html
    assert settings.OPENAI_UPSTREAM_API_KEY not in html
    assert settings.OPENROUTER_API_KEY not in html
    assert "password_hash" not in html
    assert "session-token" not in html


def test_admin_key_lifecycle_actions_postgres(migrated_postgres_url: str) -> None:
    data = asyncio.run(_create_admin_and_key(migrated_postgres_url))
    key_id = data["gateway_key_id"]
    assert isinstance(key_id, uuid.UUID)
    settings = _settings(
        migrated_postgres_url,
        one_time_secret_key=str(data["one_time_secret_key"]),
    )
    app = create_app(settings)

    with TestClient(app) as client:
        unauthenticated = client.post(f"/admin/keys/{key_id}/suspend", follow_redirects=False)
        assert unauthenticated.status_code == 303
        assert unauthenticated.headers["location"] == "/admin/login"
        assert asyncio.run(_get_key(migrated_postgres_url, key_id)).status == "active"

        login_page = client.get("/admin/login")
        login_csrf = _csrf_from_html(login_page.text)
        login = client.post(
            "/admin/login",
            data={
                "email": data["admin_email"],
                "password": data["admin_password"],
                "csrf_token": login_csrf,
            },
            follow_redirects=False,
        )
        assert login.status_code == 303

        detail = client.get(f"/admin/keys/{key_id}")
        assert detail.status_code == 200
        _assert_safe_html(detail.text, data, settings)

        no_csrf = client.post(f"/admin/keys/{key_id}/suspend")
        assert no_csrf.status_code == 400
        assert "Invalid CSRF token." in no_csrf.text
        assert asyncio.run(_get_key(migrated_postgres_url, key_id)).status == "active"

        csrf = _csrf_from_html(detail.text)
        suspended = client.post(
            f"/admin/keys/{key_id}/suspend",
            data={"csrf_token": csrf, "reason": "pause access"},
            follow_redirects=False,
        )
        assert suspended.status_code == 303
        assert suspended.headers["location"] == f"/admin/keys/{key_id}?message=key_suspended"
        assert asyncio.run(_get_key(migrated_postgres_url, key_id)).status == "suspended"
        assert "suspend_key" in asyncio.run(_audit_actions(migrated_postgres_url, key_id))

        detail = client.get(f"/admin/keys/{key_id}")
        csrf = _csrf_from_html(detail.text)
        activated = client.post(
            f"/admin/keys/{key_id}/activate",
            data={"csrf_token": csrf, "reason": "resume access"},
            follow_redirects=False,
        )
        assert activated.status_code == 303
        assert activated.headers["location"] == f"/admin/keys/{key_id}?message=key_activated"
        assert asyncio.run(_get_key(migrated_postgres_url, key_id)).status == "active"
        assert "activate_key" in asyncio.run(_audit_actions(migrated_postgres_url, key_id))

        detail = client.get(f"/admin/keys/{key_id}")
        csrf = _csrf_from_html(detail.text)
        missing_confirmation = client.post(
            f"/admin/keys/{key_id}/revoke",
            data={"csrf_token": csrf, "reason": "course ended"},
            follow_redirects=False,
        )
        assert missing_confirmation.status_code == 303
        assert missing_confirmation.headers["location"] == (
            f"/admin/keys/{key_id}?message=revoke_confirmation_required"
        )
        assert asyncio.run(_get_key(migrated_postgres_url, key_id)).status == "active"

        detail = client.get(f"/admin/keys/{key_id}")
        csrf = _csrf_from_html(detail.text)
        revoked = client.post(
            f"/admin/keys/{key_id}/revoke",
            data={
                "csrf_token": csrf,
                "reason": "course ended",
                "confirm_revoke": "true",
            },
            follow_redirects=False,
        )
        assert revoked.status_code == 303
        assert revoked.headers["location"] == f"/admin/keys/{key_id}?message=key_revoked"
        revoked_key = asyncio.run(_get_key(migrated_postgres_url, key_id))
        assert revoked_key.status == "revoked"
        assert revoked_key.revoked_reason == "course ended"
        assert "revoke_key" in asyncio.run(_audit_actions(migrated_postgres_url, key_id))

        detail = client.get(f"/admin/keys/{key_id}")
        assert detail.status_code == 200
        _assert_safe_html(detail.text, data, settings)
        assert f"/admin/keys/{key_id}/activate" not in detail.text
        csrf = _csrf_from_html(detail.text)
        reactivate = client.post(
            f"/admin/keys/{key_id}/activate",
            data={"csrf_token": csrf, "reason": "should fail"},
            follow_redirects=False,
        )
        assert reactivate.status_code == 303
        assert reactivate.headers["location"] == (
            f"/admin/keys/{key_id}?message=gateway_key_already_revoked"
        )
        assert asyncio.run(_get_key(migrated_postgres_url, key_id)).status == "revoked"
