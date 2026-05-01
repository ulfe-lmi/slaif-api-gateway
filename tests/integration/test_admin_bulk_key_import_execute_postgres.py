from __future__ import annotations

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


def _plaintext_keys_from_html(html: str) -> list[str]:
    return re.findall(r"sk-slaif-[A-Za-z0-9_-]{8,64}\.[A-Za-z0-9_-]{43,}", html)


def _settings(database_url: str) -> Settings:
    return Settings(
        APP_ENV="test",
        DATABASE_URL=database_url,
        ADMIN_SESSION_SECRET="s" * 40,
        TOKEN_HMAC_SECRET="hmac-secret-for-bulk-key-execution-tests",
        ONE_TIME_SECRET_ENCRYPTION_KEY=generate_secret_key(),
        OPENAI_UPSTREAM_API_KEY="sk-provider-secret-placeholder",
        OPENROUTER_API_KEY="sk-or-provider-secret-placeholder",
    )


async def _seed_records(database_url: str) -> dict[str, object]:
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(UTC)
    suffix = uuid.uuid4().hex
    try:
        async with session_factory() as session:
            async with session.begin():
                admin = await AdminUsersRepository(session).create_admin_user(
                    email=f"admin-bulk-exec-{suffix}@example.org",
                    display_name="Bulk Key Exec Admin",
                    password_hash=hash_admin_password("correct horse battery staple"),
                    role="admin",
                    is_active=True,
                )
                institution = await InstitutionsRepository(session).create_institution(
                    name=f"Bulk Exec University {suffix}",
                    country="SI",
                )
                cohort = await CohortsRepository(session).create_cohort(
                    name=f"Bulk Exec Cohort {suffix}",
                    starts_at=now - timedelta(days=1),
                    ends_at=now + timedelta(days=30),
                )
                owner = await OwnersRepository(session).create_owner(
                    name="Ada",
                    surname="Lovelace",
                    email=f"bulk-exec-owner-{suffix}@example.org",
                    institution_id=institution.id,
                )
                return {
                    "admin_id": admin.id,
                    "admin_email": admin.email,
                    "admin_password": "correct horse battery staple",
                    "owner_id": owner.id,
                    "owner_email": owner.email,
                    "institution_id": institution.id,
                    "cohort_id": cohort.id,
                }
    finally:
        await engine.dispose()


async def _counts(database_url: str) -> dict[str, int]:
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            return {
                "gateway_keys": int(await session.scalar(select(func.count()).select_from(GatewayKey)) or 0),
                "one_time_secrets": int(await session.scalar(select(func.count()).select_from(OneTimeSecret)) or 0),
                "email_deliveries": int(await session.scalar(select(func.count()).select_from(EmailDelivery)) or 0),
                "audit_logs": int(await session.scalar(select(func.count()).select_from(AuditLog)) or 0),
            }
    finally:
        await engine.dispose()


async def _created_keys(database_url: str) -> list[GatewayKey]:
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            result = await session.execute(select(GatewayKey).order_by(GatewayKey.created_at.asc()))
            return list(result.scalars().all())
    finally:
        await engine.dispose()


async def _all_secret_rows(database_url: str) -> tuple[list[OneTimeSecret], list[EmailDelivery], list[AuditLog], list[AdminSession]]:
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            secrets = list((await session.execute(select(OneTimeSecret))).scalars().all())
            deliveries = list((await session.execute(select(EmailDelivery))).scalars().all())
            audits = list((await session.execute(select(AuditLog))).scalars().all())
            sessions = list((await session.execute(select(AdminSession))).scalars().all())
            return secrets, deliveries, audits, sessions
    finally:
        await engine.dispose()


def _assert_plaintext_not_persisted(database_url: str, plaintext_keys: list[str]) -> None:
    keys = asyncio.run(_created_keys(database_url))
    secrets, deliveries, audits, sessions = asyncio.run(_all_secret_rows(database_url))
    serialized = json.dumps(
        {
            "keys": [
                {
                    "token_hash": key.token_hash,
                    "key_hint": key.key_hint,
                    "metadata_json": key.metadata_json,
                }
                for key in keys
            ],
            "secrets": [
                {
                    "encrypted_payload": secret.encrypted_payload,
                    "nonce": secret.nonce,
                }
                for secret in secrets
            ],
            "deliveries": [
                {
                    "recipient_email": delivery.recipient_email,
                    "subject": delivery.subject,
                    "template_name": delivery.template_name,
                    "status": delivery.status,
                }
                for delivery in deliveries
            ],
            "audits": [
                {
                    "action": audit.action,
                    "note": audit.note,
                    "old_values": audit.old_values,
                    "new_values": audit.new_values,
                }
                for audit in audits
            ],
            "sessions": [
                {
                    "session_token_hash": session.session_token_hash,
                    "csrf_token_hash": session.csrf_token_hash,
                }
                for session in sessions
            ],
        },
        default=str,
    )
    for plaintext_key in plaintext_keys:
        assert plaintext_key not in serialized
    assert "token_hash" not in json.dumps([audit.new_values for audit in audits], default=str)
    assert "encrypted_payload" not in json.dumps([audit.new_values for audit in audits], default=str)
    assert "nonce" not in json.dumps([audit.new_values for audit in audits], default=str)


def test_admin_bulk_key_import_execute_postgres(migrated_postgres_url: str) -> None:
    data = asyncio.run(_seed_records(migrated_postgres_url))
    owner_id = data["owner_id"]
    owner_email = data["owner_email"]
    cohort_id = data["cohort_id"]
    assert isinstance(owner_id, uuid.UUID)
    assert isinstance(cohort_id, uuid.UUID)
    settings = _settings(migrated_postgres_url)
    app = create_app(settings)

    with TestClient(app) as client:
        unauthenticated = client.post(
            "/admin/keys/bulk-import/execute",
            data={"import_format": "csv", "import_text": f"owner_email,valid_days\n{owner_email},30\n"},
            follow_redirects=False,
        )
        assert unauthenticated.status_code == 303
        assert unauthenticated.headers["location"] == "/admin/login"

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

        import_page = client.get("/admin/keys/bulk-import")
        csrf = _csrf_from_html(import_page.text)
        counts_after_login = asyncio.run(_counts(migrated_postgres_url))

        preview_csv = f"owner_email,valid_days,cost_limit_eur,email_delivery_mode\n{owner_email},30,10.00,none\n"
        preview = client.post(
            "/admin/keys/bulk-import/preview",
            data={"csrf_token": csrf, "import_format": "csv", "import_text": preview_csv},
        )
        assert preview.status_code == 200
        assert asyncio.run(_counts(migrated_postgres_url)) == counts_after_login

        without_csrf = client.post(
            "/admin/keys/bulk-import/execute",
            data={"import_format": "csv", "import_text": preview_csv, "confirm_import": "true", "reason": "bulk"},
        )
        assert without_csrf.status_code == 400
        assert "Invalid CSRF token." in without_csrf.text
        assert asyncio.run(_counts(migrated_postgres_url)) == counts_after_login

        missing_confirm = client.post(
            "/admin/keys/bulk-import/execute",
            data={
                "csrf_token": csrf,
                "import_format": "csv",
                "import_text": preview_csv,
                "confirm_plaintext_display": "true",
                "reason": "bulk key execution",
            },
        )
        assert missing_confirm.status_code == 400
        assert "Confirm bulk key import" in missing_confirm.text
        assert asyncio.run(_counts(migrated_postgres_url)) == counts_after_login

        missing_reason = client.post(
            "/admin/keys/bulk-import/execute",
            data={
                "csrf_token": csrf,
                "import_format": "csv",
                "import_text": preview_csv,
                "confirm_import": "true",
                "confirm_plaintext_display": "true",
            },
        )
        assert missing_reason.status_code == 400
        assert "audit reason" in missing_reason.text
        assert asyncio.run(_counts(migrated_postgres_url)) == counts_after_login

        created = client.post(
            "/admin/keys/bulk-import/execute",
            data={
                "csrf_token": csrf,
                "import_format": "csv",
                "import_text": (
                    "owner_email,cohort_id,valid_days,cost_limit_eur,token_limit_total,"
                    "request_limit_total,allowed_models,allowed_endpoints,"
                    "rate_limit_requests_per_minute,email_delivery_mode\n"
                    f"{owner_email},{cohort_id},30,10.00,100000,1000,"
                    "gpt-test,/v1/chat/completions,60,none\n"
                ),
                "confirm_import": "true",
                "confirm_plaintext_display": "true",
                "reason": "bulk key execution",
            },
        )
        assert created.status_code == 200
        assert created.headers["Cache-Control"] == "no-store, no-cache, must-revalidate"
        assert created.headers["Pragma"] == "no-cache"
        plaintext_keys = _plaintext_keys_from_html(created.text)
        assert len(plaintext_keys) == 1
        assert created.text.count(plaintext_keys[0]) == 1
        assert plaintext_keys[0] not in str(created.url)
        assert plaintext_keys[0] not in created.headers.get("set-cookie", "")
        assert "token_hash" not in created.text
        assert "encrypted_payload" not in created.text
        assert "nonce" not in created.text
        assert "password_hash" not in created.text
        assert settings.OPENAI_UPSTREAM_API_KEY not in created.text
        assert settings.OPENROUTER_API_KEY not in created.text

        after_created = asyncio.run(_counts(migrated_postgres_url))
        assert after_created["gateway_keys"] == counts_after_login["gateway_keys"] + 1
        assert after_created["one_time_secrets"] == counts_after_login["one_time_secrets"] + 1
        assert after_created["email_deliveries"] == counts_after_login["email_deliveries"]
        assert after_created["audit_logs"] == counts_after_login["audit_logs"] + 1
        key = asyncio.run(_created_keys(migrated_postgres_url))[0]
        assert key.cost_limit_eur == Decimal("10.00")
        assert key.allowed_models == ["gpt-test"]
        assert key.allowed_endpoints == ["/v1/chat/completions"]
        assert key.rate_limit_requests_per_minute == 60
        assert key.token_hash
        assert not key.token_hash.startswith("sk-")
        _assert_plaintext_not_persisted(migrated_postgres_url, plaintext_keys)

        pending_json = json.dumps(
            [
                {
                    "owner_id": str(owner_id),
                    "valid_days": "15",
                    "cost_limit_eur": "5.00",
                    "email_delivery_mode": "pending",
                }
            ]
        )
        pending = client.post(
            "/admin/keys/bulk-import/execute",
            data={
                "csrf_token": csrf,
                "import_format": "json",
                "import_text": pending_json,
                "confirm_import": "true",
                "confirm_plaintext_display": "true",
                "reason": "bulk pending key execution",
            },
        )
        assert pending.status_code == 200
        pending_plaintext = _plaintext_keys_from_html(pending.text)
        assert len(pending_plaintext) == 1
        assert pending.text.count(pending_plaintext[0]) == 1
        after_pending = asyncio.run(_counts(migrated_postgres_url))
        assert after_pending["gateway_keys"] == after_created["gateway_keys"] + 1
        assert after_pending["one_time_secrets"] == after_created["one_time_secrets"] + 1
        assert after_pending["email_deliveries"] == after_created["email_deliveries"] + 1
        assert after_pending["audit_logs"] == after_created["audit_logs"] + 2
        _assert_plaintext_not_persisted(migrated_postgres_url, plaintext_keys + pending_plaintext)

        invalid_csv = f"owner_email,valid_days,cost_limit_eur\nmissing@example.org,30,10.00\n{owner_email},30,8.00\n"
        invalid = client.post(
            "/admin/keys/bulk-import/execute",
            data={
                "csrf_token": csrf,
                "import_format": "csv",
                "import_text": invalid_csv,
                "confirm_import": "true",
                "confirm_plaintext_display": "true",
                "reason": "invalid bulk key execution",
            },
        )
        assert invalid.status_code == 400
        assert "All rows must validate" in invalid.text
        assert asyncio.run(_counts(migrated_postgres_url)) == after_pending

        unsupported_send = client.post(
            "/admin/keys/bulk-import/execute",
            data={
                "csrf_token": csrf,
                "import_format": "csv",
                "import_text": f"owner_email,valid_days,email_delivery_mode\n{owner_email},30,send-now\n",
                "confirm_import": "true",
                "confirm_plaintext_display": "true",
                "reason": "unsupported send",
            },
        )
        assert unsupported_send.status_code == 400
        assert "send-now" in unsupported_send.text
        assert asyncio.run(_counts(migrated_postgres_url)) == after_pending

        secret_input = client.post(
            "/admin/keys/bulk-import/execute",
            data={
                "csrf_token": csrf,
                "import_format": "csv",
                "import_text": f"owner_email,valid_days,note\n{owner_email},30,sk-provider-secret\n",
                "confirm_import": "true",
                "confirm_plaintext_display": "true",
                "reason": "secret input",
            },
        )
        assert secret_input.status_code == 400
        assert "note must not contain secret-looking values" in secret_input.text
        assert "sk-provider-secret" not in secret_input.text
        assert asyncio.run(_counts(migrated_postgres_url)) == after_pending

        provider_policy = client.post(
            "/admin/keys/bulk-import/execute",
            data={
                "csrf_token": csrf,
                "import_format": "csv",
                "import_text": f"owner_email,valid_days,allowed_providers\n{owner_email},30,openai\n",
                "confirm_import": "true",
                "confirm_plaintext_display": "true",
                "reason": "provider policy unsupported",
            },
        )
        assert provider_policy.status_code == 400
        assert "allowed_providers" in provider_policy.text
        assert asyncio.run(_counts(migrated_postgres_url)) == after_pending
