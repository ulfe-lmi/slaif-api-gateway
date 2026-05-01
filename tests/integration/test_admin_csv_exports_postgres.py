from __future__ import annotations

import asyncio
import csv
import re
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from io import StringIO

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from slaif_gateway.config import Settings
from slaif_gateway.db.models import AuditLog, UsageLedger
from slaif_gateway.db.repositories.admin_users import AdminUsersRepository
from slaif_gateway.db.repositories.audit import AuditRepository
from slaif_gateway.db.repositories.cohorts import CohortsRepository
from slaif_gateway.db.repositories.institutions import InstitutionsRepository
from slaif_gateway.db.repositories.keys import GatewayKeysRepository
from slaif_gateway.db.repositories.owners import OwnersRepository
from slaif_gateway.db.repositories.usage import UsageLedgerRepository
from slaif_gateway.main import create_app
from slaif_gateway.utils.passwords import hash_admin_password


ADMIN_PASSWORD = "correct horse battery staple"
PROVIDER_SECRET = "sk-provider-secret-csv-export-must-not-render"
PROMPT_TEXT = "csv export prompt text must not render"
COMPLETION_TEXT = "csv export completion text must not render"
RAW_REQUEST_BODY = "raw request body must not export"
RAW_RESPONSE_BODY = "raw response body must not export"
TOKEN_HASH = "hmac-token-hash-must-not-render"
ENCRYPTED_PAYLOAD = "encrypted_payload_must_not_render"
NONCE = "nonce_must_not_render"
SESSION_TOKEN = "session-token-must-not-render"
PASSWORD_HASH = "password_hash_must_not_render"


def _csrf_from_html(html: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert match is not None
    return match.group(1)


async def _create_export_data(database_url: str) -> dict[str, object]:
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(UTC)
    suffix = uuid.uuid4().hex
    async with session_factory() as session:
        async with session.begin():
            admin = await AdminUsersRepository(session).create_admin_user(
                email=f"admin-export-{suffix}@example.org",
                display_name="Export Admin",
                password_hash=hash_admin_password(ADMIN_PASSWORD),
                role="admin",
                is_active=True,
            )
            institution = await InstitutionsRepository(session).create_institution(
                name=f"Export Institution {suffix}",
                country="SI",
            )
            cohort = await CohortsRepository(session).create_cohort(
                name=f"Export Cohort {suffix}",
                starts_at=now - timedelta(days=1),
                ends_at=now + timedelta(days=1),
            )
            owner = await OwnersRepository(session).create_owner(
                name="Export",
                surname="Owner",
                email=f"export-owner-{suffix}@example.org",
                institution_id=institution.id,
            )
            key = await GatewayKeysRepository(session).create_gateway_key_record(
                public_key_id=f"pub_export_{suffix[:12]}",
                token_hash=f"{TOKEN_HASH}-{suffix}",
                owner_id=owner.id,
                cohort_id=cohort.id,
                valid_from=now - timedelta(days=1),
                valid_until=now + timedelta(days=30),
                key_hint="hint",
                cost_limit_eur=Decimal("10.000000000"),
                token_limit_total=1000,
                request_limit_total=100,
                allow_all_models=True,
                allow_all_endpoints=True,
            )
            usage = await UsageLedgerRepository(session).create_success_record(
                request_id=f"=req_export_{suffix}",
                gateway_key_id=key.id,
                owner_id=owner.id,
                institution_id=institution.id,
                cohort_id=cohort.id,
                owner_email_snapshot=owner.email,
                owner_name_snapshot=owner.name,
                owner_surname_snapshot=owner.surname,
                institution_name_snapshot=institution.name,
                cohort_name_snapshot=cohort.name,
                endpoint="/v1/chat/completions",
                provider="openai",
                requested_model=f"export-model-{suffix}",
                resolved_model=f"export-model-{suffix}",
                upstream_request_id=f"upstream-{suffix}",
                streaming=False,
                http_status=200,
                prompt_tokens=3,
                completion_tokens=5,
                total_tokens=8,
                estimated_cost_eur=Decimal("0.010000000"),
                actual_cost_eur=Decimal("0.008000000"),
                native_currency="EUR",
                usage_raw={
                    "prompt": PROMPT_TEXT,
                    "request_body": RAW_REQUEST_BODY,
                    "token_hash": TOKEN_HASH,
                    "api_key": PROVIDER_SECRET,
                },
                response_metadata={
                    "completion": COMPLETION_TEXT,
                    "response_body": RAW_RESPONSE_BODY,
                    "encrypted_payload": ENCRYPTED_PAYLOAD,
                    "nonce": NONCE,
                    "authorization": "Authorization: Bearer secret",
                },
                started_at=now,
                finished_at=now + timedelta(milliseconds=100),
                latency_ms=100,
            )
            audit = await AuditRepository(session).add_audit_log(
                admin_user_id=admin.id,
                action="key.created",
                entity_type="gateway_key",
                entity_id=key.id,
                old_values={
                    "token_hash": TOKEN_HASH,
                    "encrypted_payload": ENCRYPTED_PAYLOAD,
                    "nonce": NONCE,
                    "safe_old": "=formula",
                },
                new_values={
                    "safe_new": "new-ok",
                    "provider_api_key": PROVIDER_SECRET,
                    "password_hash": PASSWORD_HASH,
                    "session_token": SESSION_TOKEN,
                    "messages": PROMPT_TEXT,
                    "response_body": RAW_RESPONSE_BODY,
                },
                ip_address="127.0.0.1",
                user_agent="pytest",
                request_id=f"req_audit_export_{suffix}",
                note=f"Authorization: Bearer {SESSION_TOKEN} and {PROMPT_TEXT}",
            )
            payload = {
                "admin_email": admin.email,
                "usage_id": usage.id,
                "request_id": usage.request_id,
                "gateway_key_id": key.id,
                "owner_id": owner.id,
                "institution_id": institution.id,
                "cohort_id": cohort.id,
                "owner_email": owner.email,
                "model": usage.resolved_model,
                "audit_id": audit.id,
                "audit_request_id": audit.request_id,
            }
    await engine.dispose()
    return payload


async def _counts(database_url: str) -> tuple[int, int]:
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        usage_count = await session.scalar(select(func.count()).select_from(UsageLedger))
        audit_count = await session.scalar(select(func.count()).select_from(AuditLog))
    await engine.dispose()
    return int(usage_count or 0), int(audit_count or 0)


async def _export_audit_count(database_url: str) -> int:
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        count = await session.scalar(
            select(func.count())
            .select_from(AuditLog)
            .where(AuditLog.action.in_(["admin_usage_export_csv", "admin_audit_export_csv"]))
        )
    await engine.dispose()
    return int(count or 0)


def _csv_rows(content: str) -> list[dict[str, str]]:
    return list(csv.DictReader(StringIO(content)))


def _assert_safe_csv(content: str) -> None:
    forbidden = (
        PROMPT_TEXT,
        COMPLETION_TEXT,
        RAW_REQUEST_BODY,
        RAW_RESPONSE_BODY,
        TOKEN_HASH,
        ENCRYPTED_PAYLOAD,
        NONCE,
        PROVIDER_SECRET,
        PASSWORD_HASH,
        SESSION_TOKEN,
        "Authorization: Bearer",
        "token_hash",
        "encrypted_payload",
        "password_hash",
        "session_token",
        "provider_api_key",
    )
    for value in forbidden:
        assert value not in content


def test_admin_usage_and_audit_csv_exports(migrated_postgres_url: str) -> None:
    data = asyncio.run(_create_export_data(migrated_postgres_url))
    settings = Settings(
        APP_ENV="test",
        DATABASE_URL=migrated_postgres_url,
        ADMIN_SESSION_SECRET="s" * 40,
        OPENAI_UPSTREAM_API_KEY="sk-provider-secret-placeholder",
        OPENROUTER_API_KEY="sk-or-provider-secret-placeholder",
        ADMIN_USAGE_EXPORT_MAX_ROWS=50,
        ADMIN_AUDIT_EXPORT_MAX_ROWS=50,
    )
    app = create_app(settings)

    with TestClient(app) as client:
        unauthenticated = client.post(
            "/admin/usage/export.csv",
            data={"confirm_export": "true", "reason": "review"},
            follow_redirects=False,
        )
        assert unauthenticated.status_code == 303
        before_unauth_counts = asyncio.run(_counts(migrated_postgres_url))
        before_export_audit_count = asyncio.run(_export_audit_count(migrated_postgres_url))

        login_page = client.get("/admin/login")
        csrf = _csrf_from_html(login_page.text)
        login = client.post(
            "/admin/login",
            data={
                "email": data["admin_email"],
                "password": ADMIN_PASSWORD,
                "csrf_token": csrf,
            },
            follow_redirects=False,
        )
        assert login.status_code == 303
        before_invalid_counts = asyncio.run(_counts(migrated_postgres_url))

        missing_csrf = client.post(
            "/admin/usage/export.csv",
            data={"confirm_export": "true", "reason": "review"},
        )
        assert missing_csrf.status_code == 400
        assert asyncio.run(_counts(migrated_postgres_url)) == before_invalid_counts

        usage_page = client.get("/admin/usage")
        dashboard_csrf = _csrf_from_html(usage_page.text)
        usage_export = client.post(
            "/admin/usage/export.csv",
            data={
                "csrf_token": dashboard_csrf,
                "confirm_export": "true",
                "reason": "operator review",
                "provider": "openai",
                "model": data["model"],
                "endpoint": "/v1/chat/completions",
                "status": "finalized",
                "gateway_key_id": str(data["gateway_key_id"]),
                "owner_id": str(data["owner_id"]),
                "institution_id": str(data["institution_id"]),
                "cohort_id": str(data["cohort_id"]),
                "request_id": data["request_id"],
                "streaming": "false",
                "limit": "10",
            },
        )
        assert usage_export.status_code == 200
        assert usage_export.headers["content-type"].startswith("text/csv")
        usage_rows = _csv_rows(usage_export.text)
        assert len(usage_rows) == 1
        assert usage_rows[0]["request_id"].startswith("'=req_export_")
        assert usage_rows[0]["owner_email"] == data["owner_email"]
        assert usage_rows[0]["actual_cost_eur"] == "0.008000000"
        _assert_safe_csv(usage_export.text)

        audit_page = client.get("/admin/audit")
        audit_csrf = _csrf_from_html(audit_page.text)
        audit_export = client.post(
            "/admin/audit/export.csv",
            data={
                "csrf_token": audit_csrf,
                "confirm_export": "true",
                "reason": "audit review",
                "action": "key",
                "target_type": "gateway_key",
                "target_id": str(data["gateway_key_id"]),
                "request_id": data["audit_request_id"],
                "limit": "10",
            },
        )
        assert audit_export.status_code == 200
        assert audit_export.headers["content-type"].startswith("text/csv")
        audit_rows = _csv_rows(audit_export.text)
        assert len(audit_rows) == 1
        assert audit_rows[0]["action"] == "key.created"
        assert "safe_new" in audit_rows[0]["new_values_sanitized"]
        _assert_safe_csv(audit_export.text)

    usage_count, audit_count = asyncio.run(_counts(migrated_postgres_url))
    assert usage_count == before_unauth_counts[0]
    assert audit_count == before_invalid_counts[1] + 2
    assert asyncio.run(_export_audit_count(migrated_postgres_url)) == before_export_audit_count + 2
