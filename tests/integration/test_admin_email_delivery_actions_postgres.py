import asyncio
import json
import re
import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from slaif_gateway.config import Settings
from slaif_gateway.db.models import AuditLog, EmailDelivery, GatewayKey, OneTimeSecret
from slaif_gateway.db.repositories.admin_users import AdminUsersRepository
from slaif_gateway.db.repositories.audit import AuditRepository
from slaif_gateway.db.repositories.email import EmailDeliveriesRepository
from slaif_gateway.db.repositories.keys import GatewayKeysRepository
from slaif_gateway.db.repositories.one_time_secrets import OneTimeSecretsRepository
from slaif_gateway.db.repositories.owners import OwnersRepository
from slaif_gateway.main import create_app
from slaif_gateway.schemas.keys import CreateGatewayKeyInput
from slaif_gateway.services.email_delivery_service import EmailDeliveryService
from slaif_gateway.services.email_service import EmailSendResult
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
        TOKEN_HMAC_SECRET="hmac-secret-for-admin-email-delivery-actions",
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
    id = "fake-existing-delivery-task-id"


class _FakeTask:
    def __init__(self) -> None:
        self.calls: list[tuple[object, ...]] = []

    def delay(self, *args):
        self.calls.append(args)
        return _FakeAsyncResult()


async def _create_admin(database_url: str) -> dict[str, object]:
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
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
                return {
                    "admin_email": admin.email,
                    "admin_password": "correct horse battery staple",
                    "admin_id": admin.id,
                }
    finally:
        await engine.dispose()


async def _create_pending_delivery(
    database_url: str,
    settings: Settings,
    *,
    label: str,
) -> dict[str, object]:
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            async with session.begin():
                owner = await OwnersRepository(session).create_owner(
                    name="Ada",
                    surname=label,
                    email=f"owner-{label}-{uuid.uuid4()}@example.org",
                )
                created = await KeyService(
                    settings=settings,
                    gateway_keys_repository=GatewayKeysRepository(session),
                    one_time_secrets_repository=OneTimeSecretsRepository(session),
                    audit_repository=AuditRepository(session),
                ).create_gateway_key(
                    CreateGatewayKeyInput(
                        owner_id=owner.id,
                        valid_from=datetime(2026, 1, 1, tzinfo=UTC),
                        valid_until=datetime(2026, 2, 1, tzinfo=UTC),
                        note=f"create {label}",
                    )
                )
                pending = await EmailDeliveryService(
                    settings=settings,
                    one_time_secrets_repository=OneTimeSecretsRepository(session),
                    email_deliveries_repository=EmailDeliveriesRepository(session),
                    gateway_keys_repository=GatewayKeysRepository(session),
                    owners_repository=OwnersRepository(session),
                    audit_repository=AuditRepository(session),
                    email_service=_FakeEmailService(),
                ).create_pending_key_email_delivery(
                    gateway_key_id=created.gateway_key_id,
                    one_time_secret_id=created.one_time_secret_id,
                    owner_id=owner.id,
                    reason=f"pending {label}",
                )
                return {
                    "plaintext_key": created.plaintext_key,
                    "gateway_key_id": created.gateway_key_id,
                    "one_time_secret_id": created.one_time_secret_id,
                    "email_delivery_id": pending.email_delivery_id,
                }
    finally:
        await engine.dispose()


async def _delivery_state(database_url: str, email_delivery_id: uuid.UUID) -> tuple[EmailDelivery, OneTimeSecret]:
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            delivery = await session.get(EmailDelivery, email_delivery_id)
            assert delivery is not None
            secret = await session.get(OneTimeSecret, delivery.one_time_secret_id)
            assert secret is not None
            return delivery, secret
    finally:
        await engine.dispose()


async def _mutate_secret(
    database_url: str,
    one_time_secret_id: uuid.UUID,
    *,
    status: str,
    consumed: bool = False,
    expired: bool = False,
) -> None:
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            async with session.begin():
                secret = await session.get(OneTimeSecret, one_time_secret_id)
                assert secret is not None
                secret.status = status
                if consumed:
                    secret.consumed_at = datetime.now(UTC)
                if expired:
                    secret.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    finally:
        await engine.dispose()


async def _mutate_delivery_status(
    database_url: str,
    email_delivery_id: uuid.UUID,
    *,
    status: str,
) -> None:
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            async with session.begin():
                delivery = await session.get(EmailDelivery, email_delivery_id)
                assert delivery is not None
                delivery.status = status
    finally:
        await engine.dispose()


async def _database_safety_text(database_url: str) -> str:
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            audits = (await session.execute(select(AuditLog))).scalars().all()
            deliveries = (await session.execute(select(EmailDelivery))).scalars().all()
            keys = (await session.execute(select(GatewayKey))).scalars().all()
            secrets = (await session.execute(select(OneTimeSecret))).scalars().all()
            return json.dumps(
                {
                    "audits": [
                        {
                            "action": row.action,
                            "old_values": row.old_values,
                            "new_values": row.new_values,
                            "note": row.note,
                        }
                        for row in audits
                    ],
                    "deliveries": [
                        {
                            "recipient_email": row.recipient_email,
                            "subject": row.subject,
                            "template_name": row.template_name,
                            "status": row.status,
                            "provider_message_id": row.provider_message_id,
                            "error_message": row.error_message,
                        }
                        for row in deliveries
                    ],
                    "keys": [{"token_hash": row.token_hash} for row in keys],
                    "secrets": [
                        {
                            "encrypted_payload": row.encrypted_payload,
                            "nonce": row.nonce,
                        }
                        for row in secrets
                    ],
                },
                default=str,
            )
    finally:
        await engine.dispose()


def _assert_html_safe(html: str, settings: Settings, plaintext_values: list[str]) -> None:
    assert "token_hash" not in html
    assert "encrypted_payload" not in html
    assert "nonce" not in html
    assert settings.OPENAI_UPSTREAM_API_KEY not in html
    assert settings.OPENROUTER_API_KEY not in html
    assert "password_hash" not in html
    assert "session-token" not in html
    for plaintext in plaintext_values:
        assert plaintext not in html


def test_admin_email_delivery_actions_postgres(monkeypatch, migrated_postgres_url: str) -> None:
    settings = _settings(migrated_postgres_url)
    admin = asyncio.run(_create_admin(migrated_postgres_url))
    send_delivery = asyncio.run(_create_pending_delivery(migrated_postgres_url, settings, label="send"))
    enqueue_delivery = asyncio.run(_create_pending_delivery(migrated_postgres_url, settings, label="enqueue"))
    consumed_delivery = asyncio.run(_create_pending_delivery(migrated_postgres_url, settings, label="consumed"))
    expired_delivery = asyncio.run(_create_pending_delivery(migrated_postgres_url, settings, label="expired"))
    ambiguous_delivery = asyncio.run(_create_pending_delivery(migrated_postgres_url, settings, label="ambiguous"))
    asyncio.run(
        _mutate_secret(
            migrated_postgres_url,
            consumed_delivery["one_time_secret_id"],
            status="consumed",
            consumed=True,
        )
    )
    asyncio.run(
        _mutate_secret(
            migrated_postgres_url,
            expired_delivery["one_time_secret_id"],
            status="pending",
            expired=True,
        )
    )
    asyncio.run(
        _mutate_delivery_status(
            migrated_postgres_url,
            ambiguous_delivery["email_delivery_id"],
            status="ambiguous",
        )
    )
    plaintext_values = [
        str(send_delivery["plaintext_key"]),
        str(enqueue_delivery["plaintext_key"]),
        str(consumed_delivery["plaintext_key"]),
        str(expired_delivery["plaintext_key"]),
        str(ambiguous_delivery["plaintext_key"]),
    ]
    fake_task = _FakeTask()
    _FakeEmailService.sent_bodies = []
    monkeypatch.setattr("slaif_gateway.api.admin.EmailService", _FakeEmailService)
    monkeypatch.setattr("slaif_gateway.api.admin.send_pending_key_email_task", fake_task)
    app = create_app(settings)

    with TestClient(app) as client:
        unauthenticated = client.post(
            f"/admin/email-deliveries/{send_delivery['email_delivery_id']}/send-now",
            data={"csrf_token": "csrf", "confirm_send": "true"},
            follow_redirects=False,
        )
        assert unauthenticated.status_code == 303
        assert unauthenticated.headers["location"] == "/admin/login"

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

        detail = client.get(f"/admin/email-deliveries/{send_delivery['email_delivery_id']}")
        assert detail.status_code == 200
        assert "confirm_send" in detail.text
        assert "confirm_enqueue" in detail.text
        _assert_html_safe(detail.text, settings, plaintext_values)
        csrf = _csrf_from_html(detail.text)

        no_csrf = client.post(
            f"/admin/email-deliveries/{send_delivery['email_delivery_id']}/send-now",
            data={"confirm_send": "true"},
        )
        assert no_csrf.status_code == 400
        delivery, secret = asyncio.run(_delivery_state(migrated_postgres_url, send_delivery["email_delivery_id"]))
        assert delivery.status == "pending"
        assert secret.status == "pending"

        send_now = client.post(
            f"/admin/email-deliveries/{send_delivery['email_delivery_id']}/send-now",
            data={
                "csrf_token": csrf,
                "confirm_send": "true",
                "reason": "manual dashboard send",
                "plaintext_key": "sk-slaif-public.secret",
            },
        )
        assert send_now.status_code == 200
        assert _FakeEmailService.sent_bodies
        assert send_delivery["plaintext_key"] in _FakeEmailService.sent_bodies[-1]
        _assert_html_safe(send_now.text, settings, plaintext_values)
        delivery, secret = asyncio.run(_delivery_state(migrated_postgres_url, send_delivery["email_delivery_id"]))
        assert delivery.status == "sent"
        assert secret.status == "consumed"
        assert secret.consumed_at is not None

        enqueue_detail = client.get(f"/admin/email-deliveries/{enqueue_delivery['email_delivery_id']}")
        enqueue = client.post(
            f"/admin/email-deliveries/{enqueue_delivery['email_delivery_id']}/enqueue",
            data={
                "csrf_token": _csrf_from_html(enqueue_detail.text),
                "confirm_enqueue": "true",
                "plaintext_key": "sk-slaif-public.secret",
            },
        )
        assert enqueue.status_code == 200
        _assert_html_safe(enqueue.text, settings, plaintext_values)
        assert fake_task.calls == [
            (
                str(enqueue_delivery["one_time_secret_id"]),
                str(enqueue_delivery["email_delivery_id"]),
                str(admin["admin_id"]),
            )
        ]
        assert "sk-slaif-" not in repr(fake_task.calls)
        delivery, secret = asyncio.run(_delivery_state(migrated_postgres_url, enqueue_delivery["email_delivery_id"]))
        assert delivery.status == "pending"
        assert secret.status == "pending"

        consumed_detail = client.get(f"/admin/email-deliveries/{consumed_delivery['email_delivery_id']}")
        consumed = client.post(
            f"/admin/email-deliveries/{consumed_delivery['email_delivery_id']}/send-now",
            data={"csrf_token": _csrf_from_html(consumed_detail.text), "confirm_send": "true"},
        )
        assert consumed.status_code == 200
        assert "cannot be sent" in consumed.text
        _assert_html_safe(consumed.text, settings, plaintext_values)
        delivery, secret = asyncio.run(_delivery_state(migrated_postgres_url, consumed_delivery["email_delivery_id"]))
        assert delivery.status == "pending"
        assert secret.status == "consumed"

        expired_detail = client.get(f"/admin/email-deliveries/{expired_delivery['email_delivery_id']}")
        expired = client.post(
            f"/admin/email-deliveries/{expired_delivery['email_delivery_id']}/enqueue",
            data={"csrf_token": _csrf_from_html(expired_detail.text), "confirm_enqueue": "true"},
        )
        assert expired.status_code == 200
        _assert_html_safe(expired.text, settings, plaintext_values)
        assert len(fake_task.calls) == 1
        delivery, secret = asyncio.run(_delivery_state(migrated_postgres_url, expired_delivery["email_delivery_id"]))
        assert delivery.status == "pending"
        assert secret.status == "pending"

        ambiguous_detail = client.get(f"/admin/email-deliveries/{ambiguous_delivery['email_delivery_id']}")
        assert "Do not retry" in ambiguous_detail.text
        ambiguous = client.post(
            f"/admin/email-deliveries/{ambiguous_delivery['email_delivery_id']}/send-now",
            data={"csrf_token": _csrf_from_html(ambiguous_detail.text), "confirm_send": "true"},
        )
        assert ambiguous.status_code == 200
        assert "cannot be sent" in ambiguous.text
        _assert_html_safe(ambiguous.text, settings, plaintext_values)
        assert len(_FakeEmailService.sent_bodies) == 1
        delivery, secret = asyncio.run(
            _delivery_state(migrated_postgres_url, ambiguous_delivery["email_delivery_id"])
        )
        assert delivery.status == "ambiguous"
        assert secret.status == "pending"

    database_text = asyncio.run(_database_safety_text(migrated_postgres_url))
    for plaintext in plaintext_values:
        assert plaintext not in database_text
