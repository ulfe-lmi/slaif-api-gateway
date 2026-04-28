import asyncio
import json
import re
import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from slaif_gateway.config import Settings
from slaif_gateway.db.models import AdminSession, AuditLog, EmailDelivery, GatewayKey, OneTimeSecret
from slaif_gateway.db.repositories.admin_users import AdminUsersRepository
from slaif_gateway.db.repositories.cohorts import CohortsRepository
from slaif_gateway.db.repositories.institutions import InstitutionsRepository
from slaif_gateway.db.repositories.owners import OwnersRepository
from slaif_gateway.main import create_app
from slaif_gateway.services.email_service import EmailSendResult
from slaif_gateway.utils.passwords import hash_admin_password
from slaif_gateway.utils.secrets import generate_secret_key


def _csrf_from_html(html: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert match is not None
    return match.group(1)


def _plaintext_key_from_text(text: str) -> str:
    match = re.search(r"sk-slaif-[A-Za-z0-9_-]{8,64}\.[A-Za-z0-9_-]{43,}", text)
    assert match is not None
    return match.group(0)


def _settings(database_url: str, *, one_time_secret_key: str | None = None) -> Settings:
    return Settings(
        APP_ENV="test",
        DATABASE_URL=database_url,
        ADMIN_SESSION_SECRET="s" * 40,
        TOKEN_HMAC_SECRET="hmac-secret-for-admin-key-email-dashboard-tests",
        ONE_TIME_SECRET_ENCRYPTION_KEY=one_time_secret_key or generate_secret_key(),
        ENABLE_EMAIL_DELIVERY=True,
        SMTP_HOST="localhost",
        SMTP_FROM="noreply@example.org",
        CELERY_BROKER_URL="redis://localhost:6379/15",
        OPENAI_UPSTREAM_API_KEY="sk-provider-secret-placeholder",
        OPENROUTER_API_KEY="sk-or-provider-secret-placeholder",
    )


class _FakeEmailService:
    sent_bodies: list[str] = []

    def __init__(self, *args, **kwargs) -> None:
        pass

    async def send_email(self, *, to: str, subject: str, text_body: str, html_body=None):
        self.sent_bodies.append(text_body)
        return EmailSendResult(
            message_id=f"<fake-{uuid.uuid4()}@example.org>",
            accepted_recipients=(to,),
            provider_status="250 queued",
        )


class _FakeAsyncResult:
    id = "fake-dashboard-task-id"


class _FakeTask:
    def __init__(self) -> None:
        self.calls: list[tuple[object, ...]] = []

    def delay(self, *args):
        self.calls.append(args)
        return _FakeAsyncResult()


async def _create_admin_owners_and_cohort(database_url: str) -> dict[str, object]:
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
                owners = []
                for label in ("none", "pending", "send-now", "enqueue", "rotate"):
                    owner = await OwnersRepository(session).create_owner(
                        name="Ada",
                        surname=label,
                        email=f"owner-{label}-{uuid.uuid4()}@example.org",
                        institution_id=institution.id,
                    )
                    owners.append(owner.id)
                return {
                    "admin_email": admin.email,
                    "admin_password": "correct horse battery staple",
                    "admin_id": admin.id,
                    "cohort_id": cohort.id,
                    "owner_ids": owners,
                }
    finally:
        await engine.dispose()


async def _key_by_public_id(database_url: str, public_key_id: str) -> GatewayKey:
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            result = await session.execute(select(GatewayKey).where(GatewayKey.public_key_id == public_key_id))
            return result.scalar_one()
    finally:
        await engine.dispose()


async def _email_rows_for_key(database_url: str, gateway_key_id: uuid.UUID) -> list[EmailDelivery]:
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            result = await session.execute(
                select(EmailDelivery).where(EmailDelivery.gateway_key_id == gateway_key_id)
            )
            return list(result.scalars().all())
    finally:
        await engine.dispose()


async def _email_row(database_url: str, email_delivery_id: uuid.UUID) -> EmailDelivery:
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            row = await session.get(EmailDelivery, email_delivery_id)
            assert row is not None
            return row
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


async def _audit_text(database_url: str) -> str:
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            rows = (await session.execute(select(AuditLog))).scalars().all()
            return json.dumps(
                [
                    {
                        "action": row.action,
                        "old_values": row.old_values,
                        "new_values": row.new_values,
                        "note": row.note,
                    }
                    for row in rows
                ],
                default=str,
            )
    finally:
        await engine.dispose()


async def _admin_session_text(database_url: str, admin_id: uuid.UUID) -> str:
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            rows = (
                await session.execute(select(AdminSession).where(AdminSession.admin_user_id == admin_id))
            ).scalars()
            return json.dumps(
                [
                    {
                        "session_token_hash": row.session_token_hash,
                        "csrf_token_hash": row.csrf_token_hash,
                    }
                    for row in rows
                ],
                default=str,
            )
    finally:
        await engine.dispose()


def _create_payload(owner_id: uuid.UUID, cohort_id: uuid.UUID, mode: str) -> dict[str, str]:
    return {
        "owner_id": str(owner_id),
        "cohort_id": str(cohort_id),
        "valid_days": "30",
        "reason": f"dashboard email mode {mode}",
        "email_delivery_mode": mode,
    }


def _assert_html_safe(html: str, settings: Settings) -> None:
    assert "token_hash" not in html
    assert "encrypted_payload" not in html
    assert "nonce" not in html
    assert settings.OPENAI_UPSTREAM_API_KEY not in html
    assert settings.OPENROUTER_API_KEY not in html
    assert "password_hash" not in html
    assert "session-token" not in html


def test_admin_key_email_delivery_modes_postgres(monkeypatch, migrated_postgres_url: str) -> None:
    data = asyncio.run(_create_admin_owners_and_cohort(migrated_postgres_url))
    owner_ids = data["owner_ids"]
    assert isinstance(owner_ids, list)
    cohort_id = data["cohort_id"]
    admin_id = data["admin_id"]
    assert isinstance(cohort_id, uuid.UUID)
    assert isinstance(admin_id, uuid.UUID)
    settings = _settings(migrated_postgres_url)
    fake_task = _FakeTask()
    _FakeEmailService.sent_bodies = []
    monkeypatch.setattr("slaif_gateway.api.admin.EmailService", _FakeEmailService)
    monkeypatch.setattr("slaif_gateway.api.admin.send_pending_key_email_task", fake_task)
    app = create_app(settings)

    with TestClient(app) as client:
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

        create_page = client.get("/admin/keys/create")
        csrf = _csrf_from_html(create_page.text)

        none_response = client.post(
            "/admin/keys/create",
            data={**_create_payload(owner_ids[0], cohort_id, "none"), "csrf_token": csrf},
        )
        assert none_response.status_code == 200
        none_plaintext = _plaintext_key_from_text(none_response.text)
        assert none_response.text.count(none_plaintext) == 1
        none_key = asyncio.run(_key_by_public_id(migrated_postgres_url, none_plaintext.split(".")[0].removeprefix("sk-slaif-")))
        none_secret = asyncio.run(_one_time_secret_for_key(migrated_postgres_url, none_key.id))
        assert asyncio.run(_email_rows_for_key(migrated_postgres_url, none_key.id)) == []

        pending_response = client.post(
            "/admin/keys/create",
            data={**_create_payload(owner_ids[1], cohort_id, "pending"), "csrf_token": csrf},
        )
        assert pending_response.status_code == 200
        pending_plaintext = _plaintext_key_from_text(pending_response.text)
        assert pending_response.text.count(pending_plaintext) == 1
        pending_key = asyncio.run(
            _key_by_public_id(migrated_postgres_url, pending_plaintext.split(".")[0].removeprefix("sk-slaif-"))
        )
        pending_rows = asyncio.run(_email_rows_for_key(migrated_postgres_url, pending_key.id))
        pending_secret = asyncio.run(_one_time_secret_for_key(migrated_postgres_url, pending_key.id))
        assert len(pending_rows) == 1
        assert pending_rows[0].status == "pending"
        assert pending_secret.status == "pending"
        assert pending_secret.consumed_at is None

        send_now_response = client.post(
            "/admin/keys/create",
            data={**_create_payload(owner_ids[2], cohort_id, "send-now"), "csrf_token": csrf},
        )
        assert send_now_response.status_code == 200
        send_now_plaintext = _plaintext_key_from_text(_FakeEmailService.sent_bodies[-1])
        assert send_now_plaintext not in send_now_response.text
        assert send_now_plaintext not in str(send_now_response.url)
        assert send_now_plaintext not in send_now_response.headers.get("set-cookie", "")
        send_key = asyncio.run(
            _key_by_public_id(migrated_postgres_url, send_now_plaintext.split(".")[0].removeprefix("sk-slaif-"))
        )
        send_rows = asyncio.run(_email_rows_for_key(migrated_postgres_url, send_key.id))
        send_secret = asyncio.run(_one_time_secret_for_key(migrated_postgres_url, send_key.id))
        assert send_rows[0].status == "sent"
        assert send_secret.status == "consumed"
        assert send_secret.consumed_at is not None

        enqueue_response = client.post(
            "/admin/keys/create",
            data={**_create_payload(owner_ids[3], cohort_id, "enqueue"), "csrf_token": csrf},
        )
        assert enqueue_response.status_code == 200
        assert "fake-dashboard-task-id" in enqueue_response.text
        assert "queued" in enqueue_response.text
        assert fake_task.calls
        assert len(fake_task.calls[-1]) == 3
        assert "sk-slaif-" not in repr(fake_task.calls)
        assert "plaintext" not in repr(fake_task.calls).lower()
        enqueue_delivery_id = uuid.UUID(str(fake_task.calls[-1][1]))
        enqueue_row = asyncio.run(_email_row(migrated_postgres_url, enqueue_delivery_id))
        assert enqueue_row.status == "pending"

        rotate_create = client.post(
            "/admin/keys/create",
            data={**_create_payload(owner_ids[4], cohort_id, "none"), "csrf_token": csrf},
        )
        old_plaintext = _plaintext_key_from_text(rotate_create.text)
        old_public_id = old_plaintext.split(".")[0].removeprefix("sk-slaif-")
        old_key = asyncio.run(_key_by_public_id(migrated_postgres_url, old_public_id))
        old_secret = asyncio.run(_one_time_secret_for_key(migrated_postgres_url, old_key.id))
        detail = client.get(f"/admin/keys/{old_key.id}")
        rotate_csrf = _csrf_from_html(detail.text)
        rotate_send = client.post(
            f"/admin/keys/{old_key.id}/rotate",
            data={
                "csrf_token": rotate_csrf,
                "confirm_rotate": "true",
                "reason": "deliver replacement by email",
                "email_delivery_mode": "send-now",
            },
        )
        assert rotate_send.status_code == 200
        replacement_plaintext = _plaintext_key_from_text(_FakeEmailService.sent_bodies[-1])
        assert replacement_plaintext not in rotate_send.text
        assert old_plaintext not in rotate_send.text
        assert old_plaintext not in _FakeEmailService.sent_bodies[-1]
        replacement_key = asyncio.run(
            _key_by_public_id(migrated_postgres_url, replacement_plaintext.split(".")[0].removeprefix("sk-slaif-"))
        )
        replacement_secret = asyncio.run(_one_time_secret_for_key(migrated_postgres_url, replacement_key.id))
        replacement_rows = asyncio.run(_email_rows_for_key(migrated_postgres_url, replacement_key.id))
        assert replacement_rows[0].status == "sent"
        assert replacement_secret.status == "consumed"

        for response in (
            none_response,
            pending_response,
            send_now_response,
            enqueue_response,
            rotate_send,
        ):
            assert response.headers["Cache-Control"] == "no-store, no-cache, must-revalidate"
            assert response.headers["Pragma"] == "no-cache"
            _assert_html_safe(response.text, settings)

    plaintext_values = [none_plaintext, pending_plaintext, send_now_plaintext, old_plaintext, replacement_plaintext]
    audit_text = asyncio.run(_audit_text(migrated_postgres_url))
    session_text = asyncio.run(_admin_session_text(migrated_postgres_url, admin_id))
    for plaintext in plaintext_values:
        assert plaintext not in audit_text
        assert plaintext not in session_text
    for key in (none_key, pending_key, send_key, old_key, replacement_key):
        assert key.token_hash
        assert not key.token_hash.startswith("sk-")
        assert all(plaintext not in key.token_hash for plaintext in plaintext_values)
    for secret in (none_secret, pending_secret, send_secret, old_secret, replacement_secret):
        assert all(plaintext not in secret.encrypted_payload for plaintext in plaintext_values)
        assert all(plaintext not in secret.nonce for plaintext in plaintext_values)
    for row in pending_rows + send_rows + [enqueue_row] + replacement_rows:
        serialized_email = json.dumps(
            {
                "recipient_email": row.recipient_email,
                "subject": row.subject,
                "template_name": row.template_name,
                "status": row.status,
                "provider_message_id": row.provider_message_id,
                "error_message": row.error_message,
            },
            default=str,
        )
        for plaintext in plaintext_values:
            assert plaintext not in serialized_email
