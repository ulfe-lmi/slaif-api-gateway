import asyncio
import re
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from slaif_gateway.config import Settings
from slaif_gateway.db.models import AuditLog, EmailDelivery, OneTimeSecret, UsageLedger
from slaif_gateway.db.repositories.admin_users import AdminUsersRepository
from slaif_gateway.db.repositories.audit import AuditRepository
from slaif_gateway.db.repositories.cohorts import CohortsRepository
from slaif_gateway.db.repositories.email import EmailDeliveriesRepository
from slaif_gateway.db.repositories.institutions import InstitutionsRepository
from slaif_gateway.db.repositories.keys import GatewayKeysRepository
from slaif_gateway.db.repositories.owners import OwnersRepository
from slaif_gateway.db.repositories.usage import UsageLedgerRepository
from slaif_gateway.main import create_app
from slaif_gateway.utils.passwords import hash_admin_password


def _csrf_from_html(html: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert match is not None
    return match.group(1)


async def _create_admin_activity(database_url: str) -> dict[str, object]:
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
            institution = await InstitutionsRepository(session).create_institution(
                name=f"Activity Institution {suffix}",
                country="SI",
            )
            cohort = await CohortsRepository(session).create_cohort(
                name=f"Activity Cohort {suffix}",
                starts_at=now - timedelta(days=1),
                ends_at=now + timedelta(days=1),
            )
            owner = await OwnersRepository(session).create_owner(
                name="Ada",
                surname="Lovelace",
                email=f"ada-{suffix}@example.org",
                institution_id=institution.id,
            )
            key = await GatewayKeysRepository(session).create_gateway_key_record(
                public_key_id=f"pub_activity_{suffix[:12]}",
                token_hash=f"hmac-secret-not-rendered-{suffix}",
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
                request_id=f"req_activity_{suffix}",
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
                requested_model=f"activity-model-{suffix}",
                resolved_model=f"activity-model-{suffix}",
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
                    "prompt_tokens": 3,
                    "prompt": "prompt text that must not render",
                    "api_key": "sk-provider-secret-danger",
                },
                response_metadata={
                    "safe": "metadata-ok",
                    "response_body": "completion text that must not render",
                    "authorization": "Bearer secret",
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
                old_values={"token_hash": "secret", "safe_old": "old-ok"},
                new_values={
                    "safe_new": "new-ok",
                    "provider_api_key": "sk-provider-secret-danger",
                    "messages": "prompt text that must not render",
                },
                ip_address="127.0.0.1",
                user_agent="pytest",
                request_id=f"req_audit_{suffix}",
                note="Authorization=Bearer secret and safe audit note",
            )
            secret = OneTimeSecret(
                purpose="gateway_key_email",
                owner_id=owner.id,
                gateway_key_id=key.id,
                encrypted_payload="encrypted-payload-not-rendered",
                nonce="nonce-not-rendered",
                encryption_key_version=1,
                expires_at=now + timedelta(hours=1),
                status="pending",
            )
            session.add(secret)
            await session.flush()
            email = await EmailDeliveriesRepository(session).create_email_delivery(
                recipient_email=owner.email,
                subject="Gateway key delivery",
                template_name="gateway_key_email",
                owner_id=owner.id,
                gateway_key_id=key.id,
                one_time_secret_id=secret.id,
                status="pending",
            )
            payload = {
                "admin_email": admin.email,
                "admin_password": "correct horse battery staple",
                "owner_email": owner.email,
                "gateway_key_id": key.id,
                "public_key_id": key.public_key_id,
                "usage_id": usage.id,
                "request_id": usage.request_id,
                "audit_id": audit.id,
                "audit_request_id": audit.request_id,
                "email_id": email.id,
                "one_time_secret_id": secret.id,
                "model": usage.resolved_model,
            }
    await engine.dispose()
    return payload


async def _activity_counts(database_url: str) -> tuple[int, int, int]:
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        usage_count = await session.scalar(select(func.count()).select_from(UsageLedger))
        audit_count = await session.scalar(select(func.count()).select_from(AuditLog))
        email_count = await session.scalar(select(func.count()).select_from(EmailDelivery))
    await engine.dispose()
    return int(usage_count or 0), int(audit_count or 0), int(email_count or 0)


def test_admin_activity_readonly_pages(migrated_postgres_url: str) -> None:
    data = asyncio.run(_create_admin_activity(migrated_postgres_url))
    settings = Settings(
        APP_ENV="test",
        DATABASE_URL=migrated_postgres_url,
        ADMIN_SESSION_SECRET="s" * 40,
        OPENAI_UPSTREAM_API_KEY="sk-provider-secret-placeholder",
        OPENROUTER_API_KEY="sk-or-provider-secret-placeholder",
    )
    app = create_app(settings)

    with TestClient(app) as client:
        for path in ("/admin/usage", "/admin/audit", "/admin/email-deliveries"):
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
        before_counts = asyncio.run(_activity_counts(migrated_postgres_url))

        usage = client.get("/admin/usage")
        assert usage.status_code == 200
        assert data["request_id"] in usage.text
        assert data["public_key_id"] in usage.text

        usage_filtered = client.get(
            "/admin/usage",
            params={
                "provider": "openai",
                "model": data["model"],
                "endpoint": "/v1/chat/completions",
                "status": "finalized",
                "gateway_key_id": str(data["gateway_key_id"]),
                "request_id": data["request_id"],
                "streaming": "false",
            },
        )
        assert usage_filtered.status_code == 200
        assert data["request_id"] in usage_filtered.text

        usage_detail = client.get(f"/admin/usage/{data['usage_id']}")
        assert usage_detail.status_code == 200
        assert "metadata-ok" in usage_detail.text
        assert "prompt text that must not render" not in usage_detail.text
        assert "completion text that must not render" not in usage_detail.text

        audit = client.get("/admin/audit")
        assert audit.status_code == 200
        assert "key.created" in audit.text

        audit_filtered = client.get(
            "/admin/audit",
            params={
                "action": "key",
                "target_type": "gateway_key",
                "target_id": str(data["gateway_key_id"]),
                "request_id": data["audit_request_id"],
            },
        )
        assert audit_filtered.status_code == 200
        assert "key.created" in audit_filtered.text

        audit_detail = client.get(f"/admin/audit/{data['audit_id']}")
        assert audit_detail.status_code == 200
        assert "new-ok" in audit_detail.text
        assert "token_hash" not in audit_detail.text
        assert "provider_api_key" not in audit_detail.text

        email = client.get("/admin/email-deliveries")
        assert email.status_code == 200
        assert data["owner_email"] in email.text
        assert data["public_key_id"] in email.text

        email_filtered = client.get(
            "/admin/email-deliveries",
            params={
                "status": "pending",
                "owner_email": data["owner_email"],
                "gateway_key_id": str(data["gateway_key_id"]),
                "one_time_secret_id": str(data["one_time_secret_id"]),
            },
        )
        assert email_filtered.status_code == 200
        assert "Gateway key delivery" in email_filtered.text

        email_detail = client.get(f"/admin/email-deliveries/{data['email_id']}")
        assert email_detail.status_code == 200
        assert "Gateway key delivery" in email_detail.text
        assert "encrypted-payload-not-rendered" not in email_detail.text
        assert "nonce-not-rendered" not in email_detail.text

        html = "\n".join(
            [
                usage.text,
                usage_detail.text,
                audit.text,
                audit_detail.text,
                email.text,
                email_detail.text,
            ]
        )
        for forbidden in (
            "sk-provider-secret-placeholder",
            "sk-or-provider-secret-placeholder",
            "sk-provider-secret-danger",
            "hmac-secret-not-rendered",
            "encrypted-payload-not-rendered",
            "nonce-not-rendered",
            "password_hash",
            "session_token",
            "raw request body",
            "raw response body",
        ):
            assert forbidden not in html

    after_counts = asyncio.run(_activity_counts(migrated_postgres_url))
    assert after_counts == before_counts
