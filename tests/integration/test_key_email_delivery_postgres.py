from __future__ import annotations

import asyncio
import json
import os
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from typer.testing import CliRunner

from slaif_gateway.cli import keys as keys_cli
from slaif_gateway.cli.main import app
from slaif_gateway.db.models import AuditLog, EmailDelivery, GatewayKey, OneTimeSecret
from slaif_gateway.db.repositories.owners import OwnersRepository
from slaif_gateway.services.email_service import EmailSendResult
from slaif_gateway.utils.secrets import generate_secret_key

pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL is required for key email delivery PostgreSQL integration tests",
)

TEST_HMAC_SECRET = "test-hmac-secret-for-key-email-delivery-123456"
TEST_ADMIN_SECRET = "test-admin-secret-for-key-email-delivery-123456"


class _FakeEmailService:
    sent_bodies: list[str] = []

    def __init__(self, *args, **kwargs) -> None:
        pass

    async def send_email(self, *, to: str, subject: str, text_body: str, html_body=None):
        self.sent_bodies.append(text_body)
        return EmailSendResult(
            message_id="<fake-message@example.org>",
            accepted_recipients=(to,),
            provider_status="250 queued",
        )


class _FakeAsyncResult:
    id = "fake-task-id"


class _FakeTask:
    def __init__(self) -> None:
        self.calls: list[tuple[object, ...]] = []

    def delay(self, *args):
        self.calls.append(args)
        return _FakeAsyncResult()


@pytest.fixture(scope="session")
def key_email_postgres_url() -> str:
    database_url = os.environ["TEST_DATABASE_URL"]
    from tests.integration.db_test_utils import run_alembic_upgrade_head

    run_alembic_upgrade_head(database_url)
    return database_url


@pytest.fixture
def key_email_env(monkeypatch: pytest.MonkeyPatch, key_email_postgres_url: str) -> str:
    monkeypatch.setenv("DATABASE_URL", key_email_postgres_url)
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("GATEWAY_KEY_PREFIX", "sk-slaif-")
    monkeypatch.setenv("GATEWAY_KEY_ACCEPTED_PREFIXES", "sk-slaif-")
    monkeypatch.setenv("ACTIVE_HMAC_KEY_VERSION", "1")
    monkeypatch.setenv("TOKEN_HMAC_SECRET_V1", TEST_HMAC_SECRET)
    monkeypatch.setenv("ADMIN_SESSION_SECRET", TEST_ADMIN_SECRET)
    monkeypatch.setenv("ONE_TIME_SECRET_ENCRYPTION_KEY", generate_secret_key())
    monkeypatch.setenv("ENABLE_EMAIL_DELIVERY", "true")
    monkeypatch.setenv("SMTP_HOST", "localhost")
    monkeypatch.setenv("SMTP_FROM", "noreply@example.org")
    monkeypatch.setenv("CELERY_BROKER_URL", "redis://localhost:6379/15")
    monkeypatch.setenv("OPENAI_UPSTREAM_API_KEY", "fake-openai-upstream-key")
    monkeypatch.setenv("OPENROUTER_API_KEY", "fake-openrouter-upstream-key")

    from slaif_gateway.config import get_settings

    get_settings.cache_clear()
    _FakeEmailService.sent_bodies = []
    return key_email_postgres_url


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def _run(coro):
    return asyncio.run(coro)


async def _create_owner(database_url: str) -> uuid.UUID:
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            owner = await OwnersRepository(session).create_owner(
                name="Email",
                surname="Delivery",
                email=f"email-delivery-{uuid.uuid4().hex}@example.org",
            )
            await session.commit()
            return owner.id
    finally:
        await engine.dispose()


async def _get_email_rows(database_url: str, gateway_key_id: uuid.UUID) -> list[EmailDelivery]:
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            rows = (
                await session.execute(
                    select(EmailDelivery).where(EmailDelivery.gateway_key_id == gateway_key_id)
                )
            ).scalars()
            return list(rows)
    finally:
        await engine.dispose()


async def _get_secret(database_url: str, one_time_secret_id: uuid.UUID) -> OneTimeSecret:
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            secret = await session.get(OneTimeSecret, one_time_secret_id)
            assert secret is not None
            return secret
    finally:
        await engine.dispose()


async def _get_key(database_url: str, gateway_key_id: uuid.UUID) -> GatewayKey:
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            key = await session.get(GatewayKey, gateway_key_id)
            assert key is not None
            return key
    finally:
        await engine.dispose()


async def _audit_values(database_url: str) -> str:
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            rows = (await session.execute(select(AuditLog))).scalars()
            return json.dumps([row.new_values for row in rows], default=str)
    finally:
        await engine.dispose()


def _create_args(owner_id: uuid.UUID, *extra: str) -> list[str]:
    return [
        "keys",
        "create",
        "--owner-id",
        str(owner_id),
        "--valid-from",
        "2026-01-01T00:00:00+00:00",
        "--valid-until",
        "2026-02-01T00:00:00+00:00",
        "--reason",
        "integration key email",
        *extra,
    ]


def test_create_email_delivery_pending_creates_safe_db_rows(
    runner: CliRunner,
    key_email_env: str,
) -> None:
    owner_id = _run(_create_owner(key_email_env))

    result = runner.invoke(
        app,
        _create_args(owner_id, "--email-delivery", "pending", "--json", "--show-plaintext"),
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    plaintext_key = payload["plaintext_key"]
    gateway_key_id = uuid.UUID(payload["gateway_key_id"])
    one_time_secret_id = uuid.UUID(payload["one_time_secret_id"])
    email_delivery_id = uuid.UUID(payload["email_delivery_id"])
    rows = _run(_get_email_rows(key_email_env, gateway_key_id))
    secret = _run(_get_secret(key_email_env, one_time_secret_id))
    key = _run(_get_key(key_email_env, gateway_key_id))
    audits = _run(_audit_values(key_email_env))

    assert rows and rows[0].id == email_delivery_id
    assert rows[0].status == "pending"
    assert secret.status == "pending"
    assert secret.consumed_at is None
    assert key.token_hash != plaintext_key
    assert plaintext_key not in rows[0].subject
    assert plaintext_key not in (rows[0].error_message or "")
    assert plaintext_key not in audits
    assert secret.encrypted_payload not in audits
    assert secret.nonce not in audits


def test_create_email_delivery_send_now_sends_and_hides_stdout_key(
    monkeypatch: pytest.MonkeyPatch,
    runner: CliRunner,
    key_email_env: str,
) -> None:
    monkeypatch.setattr(keys_cli, "EmailService", _FakeEmailService)
    owner_id = _run(_create_owner(key_email_env))

    result = runner.invoke(
        app,
        _create_args(owner_id, "--email-delivery", "send-now", "--json"),
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    gateway_key_id = uuid.UUID(payload["gateway_key_id"])
    one_time_secret_id = uuid.UUID(payload["one_time_secret_id"])
    rows = _run(_get_email_rows(key_email_env, gateway_key_id))
    secret = _run(_get_secret(key_email_env, one_time_secret_id))
    key = _run(_get_key(key_email_env, gateway_key_id))
    sent_body = _FakeEmailService.sent_bodies[0]

    assert rows[0].status == "sent"
    assert secret.status == "consumed"
    assert secret.consumed_at is not None
    assert payload["public_key_id"] in sent_body
    assert "sk-slaif-" in sent_body
    assert "plaintext_key" not in payload
    assert sent_body not in result.stdout
    assert "OPENAI_API_KEY" not in result.stdout
    assert key.token_hash not in sent_body


def test_create_email_delivery_enqueue_payload_ids_only(
    monkeypatch: pytest.MonkeyPatch,
    runner: CliRunner,
    key_email_env: str,
) -> None:
    fake_task = _FakeTask()
    monkeypatch.setattr(keys_cli, "send_pending_key_email_task", fake_task)
    owner_id = _run(_create_owner(key_email_env))

    result = runner.invoke(
        app,
        _create_args(owner_id, "--email-delivery", "enqueue", "--json"),
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["celery_task_id"] == "fake-task-id"
    assert "plaintext_key" not in payload
    assert "OPENAI_API_KEY" not in result.stdout
    assert fake_task.calls == [
        (
            payload["one_time_secret_id"],
            payload["email_delivery_id"],
            None,
        )
    ]
    assert "sk-slaif-" not in repr(fake_task.calls)
    rows = _run(_get_email_rows(key_email_env, uuid.UUID(payload["gateway_key_id"])))
    assert rows[0].status == "pending"


def test_rotate_email_delivery_send_now_delivers_replacement_only(
    monkeypatch: pytest.MonkeyPatch,
    runner: CliRunner,
    key_email_env: str,
) -> None:
    monkeypatch.setattr(keys_cli, "EmailService", _FakeEmailService)
    owner_id = _run(_create_owner(key_email_env))
    created = runner.invoke(
        app,
        _create_args(owner_id, "--json", "--show-plaintext"),
    )
    assert created.exit_code == 0, created.output
    created_payload = json.loads(created.stdout)
    old_plaintext = created_payload["plaintext_key"]

    rotated = runner.invoke(
        app,
        [
            "keys",
            "rotate",
            created_payload["gateway_key_id"],
            "--email-delivery",
            "send-now",
            "--json",
        ],
    )

    assert rotated.exit_code == 0, rotated.output
    payload = json.loads(rotated.stdout)
    sent_body = _FakeEmailService.sent_bodies[0]
    secret = _run(_get_secret(key_email_env, uuid.UUID(payload["one_time_secret_id"])))
    old_key = _run(_get_key(key_email_env, uuid.UUID(payload["old_gateway_key_id"])))
    new_key = _run(_get_key(key_email_env, uuid.UUID(payload["new_gateway_key_id"])))

    assert "new_plaintext_key" not in payload
    assert old_plaintext not in sent_body
    assert old_plaintext not in rotated.stdout
    assert payload["new_public_key_id"] in sent_body
    assert secret.status == "consumed"
    assert old_key.status == "revoked"
    assert new_key.status == "active"
