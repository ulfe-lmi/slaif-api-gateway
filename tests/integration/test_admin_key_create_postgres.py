import asyncio
import json
import re
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from slaif_gateway.config import Settings
from slaif_gateway.db.models import AdminSession, AuditLog, EmailDelivery, GatewayKey, OneTimeSecret
from slaif_gateway.db.repositories.admin_users import AdminUsersRepository
from slaif_gateway.db.repositories.cohorts import CohortsRepository
from slaif_gateway.db.repositories.institutions import InstitutionsRepository
from slaif_gateway.db.repositories.owners import OwnersRepository
from slaif_gateway.main import create_app
from slaif_gateway.utils.passwords import hash_admin_password
from slaif_gateway.utils.secrets import generate_secret_key


def _csrf_from_html(html: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert match is not None
    return match.group(1)


def _plaintext_key_from_html(html: str) -> str:
    match = re.search(r"sk-slaif-[A-Za-z0-9_-]{8,64}\.[A-Za-z0-9_-]{43,}", html)
    assert match is not None
    return match.group(0)


def _settings(database_url: str, *, one_time_secret_key: str | None = None) -> Settings:
    return Settings(
        APP_ENV="test",
        DATABASE_URL=database_url,
        ADMIN_SESSION_SECRET="s" * 40,
        TOKEN_HMAC_SECRET="hmac-secret-for-admin-key-create-tests",
        ONE_TIME_SECRET_ENCRYPTION_KEY=one_time_secret_key or generate_secret_key(),
        OPENAI_UPSTREAM_API_KEY="sk-provider-secret-placeholder",
        OPENROUTER_API_KEY="sk-or-provider-secret-placeholder",
    )


async def _create_admin_owner_and_cohort(database_url: str) -> dict[str, object]:
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
                return {
                    "admin_email": admin.email,
                    "admin_password": "correct horse battery staple",
                    "admin_id": admin.id,
                    "owner_id": owner.id,
                    "owner_email": owner.email,
                    "cohort_id": cohort.id,
                    "cohort_name": cohort.name,
                }
    finally:
        await engine.dispose()


async def _gateway_key_count_for_owner(database_url: str, owner_id: uuid.UUID) -> int:
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            result = await session.execute(
                select(func.count()).select_from(GatewayKey).where(GatewayKey.owner_id == owner_id)
            )
            return int(result.scalar_one())
    finally:
        await engine.dispose()


async def _email_delivery_count(database_url: str) -> int:
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            result = await session.execute(select(func.count()).select_from(EmailDelivery))
            return int(result.scalar_one())
    finally:
        await engine.dispose()


async def _created_key_by_owner(database_url: str, owner_id: uuid.UUID) -> GatewayKey:
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            result = await session.execute(select(GatewayKey).where(GatewayKey.owner_id == owner_id))
            return result.scalar_one()
    finally:
        await engine.dispose()


async def _one_time_secret_for_key(database_url: str, gateway_key_id: uuid.UUID) -> OneTimeSecret:
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            result = await session.execute(
                select(OneTimeSecret).where(OneTimeSecret.gateway_key_id == gateway_key_id)
            )
            return result.scalar_one()
    finally:
        await engine.dispose()


async def _audit_rows_for_key(database_url: str, gateway_key_id: uuid.UUID) -> list[AuditLog]:
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            result = await session.execute(
                select(AuditLog)
                .where(AuditLog.entity_id == gateway_key_id)
                .order_by(AuditLog.created_at.asc())
            )
            return list(result.scalars().all())
    finally:
        await engine.dispose()


async def _admin_sessions(database_url: str, admin_id: uuid.UUID) -> list[AdminSession]:
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            result = await session.execute(select(AdminSession).where(AdminSession.admin_user_id == admin_id))
            return list(result.scalars().all())
    finally:
        await engine.dispose()


def _assert_safe_dashboard_html(html: str, *, plaintext_key: str, key: GatewayKey, settings: Settings) -> None:
    assert plaintext_key not in html
    assert key.token_hash not in html
    assert "token_hash" not in html
    assert "encrypted_payload" not in html
    assert "nonce" not in html
    assert settings.OPENAI_UPSTREAM_API_KEY not in html
    assert settings.OPENROUTER_API_KEY not in html
    assert "password_hash" not in html
    assert "session-token" not in html


def test_admin_key_create_form_postgres(migrated_postgres_url: str) -> None:
    data = asyncio.run(_create_admin_owner_and_cohort(migrated_postgres_url))
    owner_id = data["owner_id"]
    cohort_id = data["cohort_id"]
    admin_id = data["admin_id"]
    assert isinstance(owner_id, uuid.UUID)
    assert isinstance(cohort_id, uuid.UUID)
    assert isinstance(admin_id, uuid.UUID)
    settings = _settings(migrated_postgres_url)
    app = create_app(settings)
    email_delivery_count_before = asyncio.run(_email_delivery_count(migrated_postgres_url))

    with TestClient(app) as client:
        unauthenticated = client.post(
            "/admin/keys/create",
            data={
                "owner_id": str(owner_id),
                "valid_days": "30",
                "reason": "should not mutate",
            },
            follow_redirects=False,
        )
        assert unauthenticated.status_code == 303
        assert unauthenticated.headers["location"] == "/admin/login"
        assert asyncio.run(_gateway_key_count_for_owner(migrated_postgres_url, owner_id)) == 0

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

        create_page = client.get("/admin/keys/create")
        assert create_page.status_code == 200
        assert str(owner_id) in create_page.text
        assert str(cohort_id) in create_page.text
        assert "token_hash" not in create_page.text
        assert "encrypted_payload" not in create_page.text
        assert "nonce" not in create_page.text
        csrf = _csrf_from_html(create_page.text)

        without_csrf = client.post(
            "/admin/keys/create",
            data={
                "owner_id": str(owner_id),
                "valid_days": "30",
                "reason": "missing csrf",
            },
        )
        assert without_csrf.status_code == 400
        assert "Invalid CSRF token." in without_csrf.text
        assert asyncio.run(_gateway_key_count_for_owner(migrated_postgres_url, owner_id)) == 0

        invalid_data = client.post(
            "/admin/keys/create",
            data={
                "csrf_token": csrf,
                "owner_id": str(owner_id),
                "valid_days": "30",
                "cost_limit_eur": "-1",
                "reason": "invalid cost",
            },
        )
        assert invalid_data.status_code == 400
        assert "Enter valid positive quota and rate-limit values." in invalid_data.text
        assert asyncio.run(_gateway_key_count_for_owner(migrated_postgres_url, owner_id)) == 0

        created = client.post(
            "/admin/keys/create",
            data={
                "csrf_token": csrf,
                "owner_id": str(owner_id),
                "cohort_id": str(cohort_id),
                "valid_days": "45",
                "cost_limit_eur": "19.000000000",
                "token_limit_total": "1900",
                "request_limit_total": "190",
                "allowed_models": "gpt-test\nopenrouter/test",
                "allowed_endpoints": "/v1/chat/completions, /v1/models",
                "rate_limit_requests_per_minute": "60",
                "rate_limit_tokens_per_minute": "12000",
                "rate_limit_concurrent_requests": "4",
                "rate_limit_window_seconds": "30",
                "reason": "dashboard create integration",
            },
        )
        assert created.status_code == 200
        assert created.headers["Cache-Control"] == "no-store, no-cache, must-revalidate"
        assert created.headers["Pragma"] == "no-cache"
        plaintext_key = _plaintext_key_from_html(created.text)
        assert created.text.count(plaintext_key) == 1
        assert plaintext_key not in str(created.url)
        assert plaintext_key not in created.headers.get("set-cookie", "")
        assert "No email delivery row was created" in created.text
        assert "no Celery task was queued" in created.text
        assert "token_hash" not in created.text
        assert "encrypted_payload" not in created.text
        assert "nonce" not in created.text

        assert asyncio.run(_gateway_key_count_for_owner(migrated_postgres_url, owner_id)) == 1
        key = asyncio.run(_created_key_by_owner(migrated_postgres_url, owner_id))
        assert key.status == "active"
        assert key.owner_id == owner_id
        assert key.cohort_id == cohort_id
        assert key.cost_limit_eur == Decimal("19.000000000")
        assert key.token_limit_total == 1900
        assert key.request_limit_total == 190
        assert key.allowed_models == ["gpt-test", "openrouter/test"]
        assert key.allowed_endpoints == ["/v1/chat/completions", "/v1/models"]
        assert key.rate_limit_requests_per_minute == 60
        assert key.rate_limit_tokens_per_minute == 12000
        assert key.max_concurrent_requests == 4
        assert key.metadata_json == {"rate_limit_policy": {"window_seconds": 30}}
        assert key.token_hash
        assert not key.token_hash.startswith("sk-")
        assert plaintext_key not in key.token_hash
        assert plaintext_key not in (key.key_hint or "")

        one_time_secret = asyncio.run(_one_time_secret_for_key(migrated_postgres_url, key.id))
        assert one_time_secret.purpose == "gateway_key_email"
        assert plaintext_key not in one_time_secret.encrypted_payload
        assert plaintext_key not in one_time_secret.nonce

        audit_rows = asyncio.run(_audit_rows_for_key(migrated_postgres_url, key.id))
        assert [row.action for row in audit_rows] == ["gateway_key_created"]
        serialized_audit = json.dumps(
            [
                {
                    "action": row.action,
                    "old_values": row.old_values,
                    "new_values": row.new_values,
                    "note": row.note,
                }
                for row in audit_rows
            ],
            default=str,
        )
        assert "dashboard create integration" in serialized_audit
        assert plaintext_key not in serialized_audit
        assert key.token_hash not in serialized_audit
        assert one_time_secret.encrypted_payload not in serialized_audit
        assert one_time_secret.nonce not in serialized_audit
        assert "token_hash" not in serialized_audit
        assert "encrypted_payload" not in serialized_audit
        assert "nonce" not in serialized_audit

        for admin_session in asyncio.run(_admin_sessions(migrated_postgres_url, admin_id)):
            assert plaintext_key not in admin_session.session_token_hash
            assert plaintext_key not in admin_session.csrf_token_hash

        assert asyncio.run(_email_delivery_count(migrated_postgres_url)) == email_delivery_count_before

        detail = client.get(f"/admin/keys/{key.id}")
        assert detail.status_code == 200
        _assert_safe_dashboard_html(detail.text, plaintext_key=plaintext_key, key=key, settings=settings)
        assert key.public_key_id in detail.text
