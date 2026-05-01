from __future__ import annotations

import asyncio
import json
import re
import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from slaif_gateway.config import Settings
from slaif_gateway.db.models import AuditLog, EmailDelivery, GatewayKey, OneTimeSecret
from slaif_gateway.db.repositories.admin_users import AdminUsersRepository
from slaif_gateway.db.repositories.cohorts import CohortsRepository
from slaif_gateway.db.repositories.institutions import InstitutionsRepository
from slaif_gateway.db.repositories.owners import OwnersRepository
from slaif_gateway.main import create_app
from slaif_gateway.utils.passwords import hash_admin_password


def _csrf_from_html(html: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert match is not None
    return match.group(1)


async def _create_admin_owner_and_cohort(database_url: str) -> dict[str, object]:
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(UTC)
    suffix = uuid.uuid4().hex
    async with session_factory() as session:
        async with session.begin():
            admin = await AdminUsersRepository(session).create_admin_user(
                email=f"admin-bulk-key-{suffix}@example.org",
                display_name="Bulk Key Admin",
                password_hash=hash_admin_password("correct horse battery staple"),
                role="admin",
                is_active=True,
            )
            institution = await InstitutionsRepository(session).create_institution(
                name=f"Bulk Key University {suffix}",
                country="SI",
            )
            cohort = await CohortsRepository(session).create_cohort(
                name=f"Bulk Key Cohort {suffix}",
                starts_at=now - timedelta(days=1),
                ends_at=now + timedelta(days=30),
            )
            owner = await OwnersRepository(session).create_owner(
                name="Ada",
                surname="Lovelace",
                email=f"bulk-key-owner-{suffix}@example.org",
                institution_id=institution.id,
            )
            payload = {
                "admin_email": admin.email,
                "admin_password": "correct horse battery staple",
                "owner_id": owner.id,
                "owner_email": owner.email,
                "institution_id": institution.id,
                "cohort_id": cohort.id,
            }
    await engine.dispose()
    return payload


async def _mutation_counts(database_url: str) -> dict[str, int]:
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        payload = {
            "gateway_keys": int(await session.scalar(select(func.count()).select_from(GatewayKey)) or 0),
            "one_time_secrets": int(await session.scalar(select(func.count()).select_from(OneTimeSecret)) or 0),
            "email_deliveries": int(await session.scalar(select(func.count()).select_from(EmailDelivery)) or 0),
            "audit_logs": int(await session.scalar(select(func.count()).select_from(AuditLog)) or 0),
        }
    await engine.dispose()
    return payload


def _assert_no_key_mutation(database_url: str, expected: dict[str, int]) -> None:
    assert asyncio.run(_mutation_counts(database_url)) == expected


def _safe_settings(database_url: str) -> Settings:
    return Settings(
        APP_ENV="test",
        DATABASE_URL=database_url,
        ADMIN_SESSION_SECRET="s" * 40,
        TOKEN_HMAC_SECRET="hmac-secret-not-used-by-preview",
        OPENAI_UPSTREAM_API_KEY="sk-provider-secret-placeholder",
        OPENROUTER_API_KEY="sk-or-provider-secret-placeholder",
    )


def test_admin_bulk_key_import_preview_postgres(migrated_postgres_url: str) -> None:
    data = asyncio.run(_create_admin_owner_and_cohort(migrated_postgres_url))
    owner_id = data["owner_id"]
    owner_email = data["owner_email"]
    cohort_id = data["cohort_id"]
    institution_id = data["institution_id"]
    assert isinstance(owner_id, uuid.UUID)
    assert isinstance(cohort_id, uuid.UUID)
    assert isinstance(institution_id, uuid.UUID)
    settings = _safe_settings(migrated_postgres_url)
    app = create_app(settings)

    with TestClient(app) as client:
        unauthenticated = client.post(
            "/admin/keys/bulk-import/preview",
            data={"owner_email": str(owner_email), "valid_days": "30"},
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

        counts_after_login = asyncio.run(_mutation_counts(migrated_postgres_url))

        import_page = client.get("/admin/keys/bulk-import")
        assert import_page.status_code == 200
        assert 'name="csrf_token"' in import_page.text
        assert "Dry-run only" in import_page.text
        csrf = _csrf_from_html(import_page.text)

        without_csrf = client.post(
            "/admin/keys/bulk-import/preview",
            data={"import_format": "csv", "import_text": f"owner_email,valid_days\n{owner_email},30\n"},
        )
        assert without_csrf.status_code == 400
        assert "Invalid CSRF token." in without_csrf.text
        _assert_no_key_mutation(migrated_postgres_url, counts_after_login)

        csv_text = (
            "owner_id,owner_email,institution_id,cohort_id,valid_days,cost_limit_eur,"
            "token_limit_total,request_limit_total,allowed_models,allowed_endpoints,"
            "allowed_providers,rate_limit_requests_per_minute,email_delivery_mode,note\n"
            f"{owner_id},{owner_email},{institution_id},{cohort_id},30,10.00,100000,1000,"
            "gpt-test,/v1/chat/completions,openai,60,none,safe note\n"
        )
        valid_csv = client.post(
            "/admin/keys/bulk-import/preview",
            data={"csrf_token": csrf, "import_format": "csv", "import_text": csv_text},
        )
        assert valid_csv.status_code == 200
        assert "Bulk Key Import Preview Result" in valid_csv.text
        assert "Ada Lovelace" in valid_csv.text
        assert "gpt-test" in valid_csv.text
        assert "No plaintext gateway keys were generated" in valid_csv.text
        _assert_no_key_mutation(migrated_postgres_url, counts_after_login)

        json_preview = client.post(
            "/admin/keys/bulk-import/preview",
            data={
                "csrf_token": csrf,
                "import_format": "json",
                "import_text": json.dumps(
                    [
                        {
                            "owner_email": str(owner_email),
                            "cohort_id": str(cohort_id),
                            "valid_days": "15",
                            "cost_limit_eur": "5.00",
                            "email_delivery_mode": "none",
                        }
                    ]
                ),
            },
        )
        assert json_preview.status_code == 200
        assert "Valid rows" in json_preview.text
        _assert_no_key_mutation(migrated_postgres_url, counts_after_login)

        invalid_owner = client.post(
            "/admin/keys/bulk-import/preview",
            data={
                "csrf_token": csrf,
                "import_format": "csv",
                "import_text": "owner_email,valid_days\nmissing@example.org,30\n",
            },
        )
        assert invalid_owner.status_code == 200
        assert "owner_email must reference an existing owner" in invalid_owner.text
        _assert_no_key_mutation(migrated_postgres_url, counts_after_login)

        secret_note = client.post(
            "/admin/keys/bulk-import/preview",
            data={
                "csrf_token": csrf,
                "import_format": "csv",
                "import_text": f"owner_email,valid_days,note\n{owner_email},30,sk-provider-secret\n",
            },
        )
        assert secret_note.status_code == 200
        assert "note must not contain secret-looking values" in secret_note.text
        assert "sk-provider-secret" not in secret_note.text
        _assert_no_key_mutation(migrated_postgres_url, counts_after_login)

        plaintext_key_input = client.post(
            "/admin/keys/bulk-import/preview",
            data={
                "csrf_token": csrf,
                "import_format": "csv",
                "import_text": f"owner_email,valid_days,label\n{owner_email},30,sk-slaif-public.secret-value\n",
            },
        )
        assert plaintext_key_input.status_code == 200
        assert "label must not contain secret-looking values" in plaintext_key_input.text
        assert "sk-slaif-public.secret-value" not in plaintext_key_input.text
        _assert_no_key_mutation(migrated_postgres_url, counts_after_login)

        for html in (
            import_page.text,
            valid_csv.text,
            json_preview.text,
            invalid_owner.text,
            secret_note.text,
            plaintext_key_input.text,
        ):
            assert settings.OPENAI_UPSTREAM_API_KEY not in html
            assert settings.OPENROUTER_API_KEY not in html
            assert "token_hash" not in html
            assert "encrypted_payload" not in html
            assert "nonce" not in html
            assert "password_hash" not in html
            assert "session-token" not in html
            assert "sk-slaif-public.secret-value" not in html
