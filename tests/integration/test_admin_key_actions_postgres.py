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
from slaif_gateway.db.models import AuditLog, GatewayKey, OneTimeSecret, UsageLedger
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


async def _get_key_by_public_id(database_url: str, public_key_id: str) -> GatewayKey:
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        result = await session.execute(select(GatewayKey).where(GatewayKey.public_key_id == public_key_id))
        key = result.scalar_one()
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


async def _audit_rows(database_url: str, gateway_key_id: uuid.UUID) -> list[AuditLog]:
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        result = await session.execute(
            select(AuditLog)
            .where(AuditLog.entity_id == gateway_key_id)
            .order_by(AuditLog.created_at.asc())
        )
        rows = list(result.scalars().all())
    await engine.dispose()
    return rows


async def _gateway_key_count(database_url: str) -> int:
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        result = await session.execute(select(func.count()).select_from(GatewayKey))
        count = int(result.scalar_one())
    await engine.dispose()
    return count


async def _one_time_secret_for_key(database_url: str, gateway_key_id: uuid.UUID) -> OneTimeSecret:
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        result = await session.execute(
            select(OneTimeSecret).where(OneTimeSecret.gateway_key_id == gateway_key_id)
        )
        one_time_secret = result.scalar_one()
    await engine.dispose()
    return one_time_secret


async def _seed_usage_counters_and_ledger(database_url: str, gateway_key_id: uuid.UUID) -> None:
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(UTC)
    async with session_factory() as session:
        async with session.begin():
            key = await session.get(GatewayKey, gateway_key_id)
            assert key is not None
            key.cost_used_eur = Decimal("3.000000000")
            key.tokens_used_total = 30
            key.requests_used_total = 3
            key.cost_reserved_eur = Decimal("4.000000000")
            key.tokens_reserved_total = 40
            key.requests_reserved_total = 4
            key.last_used_at = now
            session.add(
                UsageLedger(
                    request_id=f"admin-reset-test-{uuid.uuid4()}",
                    gateway_key_id=key.id,
                    owner_id=key.owner_id,
                    cohort_id=key.cohort_id,
                    endpoint="/v1/chat/completions",
                    provider="openai",
                    requested_model="gpt-test",
                    resolved_model="gpt-test",
                    success=True,
                    accounting_status="finalized",
                    http_status=200,
                    prompt_tokens=10,
                    completion_tokens=20,
                    input_tokens=10,
                    output_tokens=20,
                    total_tokens=30,
                    actual_cost_eur=Decimal("3.000000000"),
                    usage_raw={"total_tokens": 30},
                    response_metadata={"source": "admin reset integration test"},
                    started_at=now,
                    finished_at=now,
                )
            )
    await engine.dispose()


async def _usage_ledger_count(database_url: str, gateway_key_id: uuid.UUID) -> int:
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        result = await session.execute(
            select(func.count()).select_from(UsageLedger).where(UsageLedger.gateway_key_id == gateway_key_id)
        )
        count = int(result.scalar_one())
    await engine.dispose()
    return count


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


def _replacement_key_from_html(html: str) -> str:
    match = re.search(r"sk-slaif-[A-Za-z0-9_-]{8,64}\.[A-Za-z0-9_-]{43,}", html)
    assert match is not None
    return match.group(0)


def _assert_safe_rotation_result_html(
    html: str,
    *,
    old_plaintext_key: str,
    replacement_key: str,
    settings: Settings,
) -> None:
    assert html.count(replacement_key) == 1
    assert old_plaintext_key not in html
    assert "token_hash" not in html
    assert "encrypted_payload" not in html
    assert "nonce" not in html
    assert settings.OPENAI_UPSTREAM_API_KEY not in html
    assert settings.OPENROUTER_API_KEY not in html
    assert "password_hash" not in html
    assert "session-token" not in html


def _hard_quota_snapshot(key: GatewayKey) -> dict[str, object]:
    return {
        "cost_used_eur": key.cost_used_eur,
        "tokens_used_total": key.tokens_used_total,
        "requests_used_total": key.requests_used_total,
        "cost_reserved_eur": key.cost_reserved_eur,
        "tokens_reserved_total": key.tokens_reserved_total,
        "requests_reserved_total": key.requests_reserved_total,
        "rate_limit_requests_per_minute": key.rate_limit_requests_per_minute,
        "rate_limit_tokens_per_minute": key.rate_limit_tokens_per_minute,
        "max_concurrent_requests": key.max_concurrent_requests,
        "metadata_json": key.metadata_json,
    }


def test_admin_key_lifecycle_actions_postgres(migrated_postgres_url: str) -> None:
    data = asyncio.run(_create_admin_and_key(migrated_postgres_url))
    key_id = data["gateway_key_id"]
    assert isinstance(key_id, uuid.UUID)
    rotation_data = asyncio.run(_create_admin_and_key(migrated_postgres_url))
    rotation_key_id = rotation_data["gateway_key_id"]
    assert isinstance(rotation_key_id, uuid.UUID)
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

        unauthenticated_validity = client.post(
            f"/admin/keys/{key_id}/validity",
            data={"valid_until": "2026-06-01T00:00:00+00:00", "reason": "should not mutate"},
            follow_redirects=False,
        )
        assert unauthenticated_validity.status_code == 303
        assert unauthenticated_validity.headers["location"] == "/admin/login"

        unauthenticated_limits = client.post(
            f"/admin/keys/{key_id}/limits",
            data={"cost_limit_eur": "99.000000000", "reason": "should not mutate"},
            follow_redirects=False,
        )
        assert unauthenticated_limits.status_code == 303
        assert unauthenticated_limits.headers["location"] == "/admin/login"
        original_key = asyncio.run(_get_key(migrated_postgres_url, key_id))
        assert original_key.cost_limit_eur == Decimal("12.000000000")

        unauthenticated_rotate = client.post(
            f"/admin/keys/{rotation_key_id}/rotate",
            data={"confirm_rotate": "true", "reason": "should not mutate"},
            follow_redirects=False,
        )
        assert unauthenticated_rotate.status_code == 303
        assert unauthenticated_rotate.headers["location"] == "/admin/login"
        assert asyncio.run(_get_key(migrated_postgres_url, rotation_key_id)).status == "active"

        asyncio.run(_seed_usage_counters_and_ledger(migrated_postgres_url, key_id))
        ledger_count_before_reset = asyncio.run(_usage_ledger_count(migrated_postgres_url, key_id))
        unauthenticated_reset = client.post(
            f"/admin/keys/{key_id}/reset-usage",
            data={"confirm_reset_usage": "true", "reason": "should not mutate"},
            follow_redirects=False,
        )
        assert unauthenticated_reset.status_code == 303
        assert unauthenticated_reset.headers["location"] == "/admin/login"
        after_unauthenticated_reset = asyncio.run(_get_key(migrated_postgres_url, key_id))
        assert after_unauthenticated_reset.cost_used_eur == Decimal("3.000000000")
        assert after_unauthenticated_reset.cost_reserved_eur == Decimal("4.000000000")
        assert asyncio.run(_usage_ledger_count(migrated_postgres_url, key_id)) == ledger_count_before_reset

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
        no_csrf_validity = client.post(
            f"/admin/keys/{key_id}/validity",
            data={"valid_until": "2026-06-01T00:00:00+00:00", "reason": "missing csrf"},
        )
        assert no_csrf_validity.status_code == 400
        assert "Invalid CSRF token." in no_csrf_validity.text

        no_csrf_reset = client.post(
            f"/admin/keys/{key_id}/reset-usage",
            data={"confirm_reset_usage": "true", "reason": "missing csrf"},
        )
        assert no_csrf_reset.status_code == 400
        assert "Invalid CSRF token." in no_csrf_reset.text
        after_no_csrf_reset = asyncio.run(_get_key(migrated_postgres_url, key_id))
        assert after_no_csrf_reset.cost_used_eur == Decimal("3.000000000")
        assert after_no_csrf_reset.cost_reserved_eur == Decimal("4.000000000")

        rotate_detail = client.get(f"/admin/keys/{rotation_key_id}")
        assert rotate_detail.status_code == 200
        _assert_safe_html(rotate_detail.text, rotation_data, settings)
        rotate_csrf = _csrf_from_html(rotate_detail.text)
        before_rotation_count = asyncio.run(_gateway_key_count(migrated_postgres_url))

        rotate_without_csrf = client.post(
            f"/admin/keys/{rotation_key_id}/rotate",
            data={"confirm_rotate": "true", "reason": "missing csrf"},
        )
        assert rotate_without_csrf.status_code == 400
        assert "Invalid CSRF token." in rotate_without_csrf.text
        assert asyncio.run(_get_key(migrated_postgres_url, rotation_key_id)).status == "active"
        assert asyncio.run(_gateway_key_count(migrated_postgres_url)) == before_rotation_count

        rotate_without_confirm = client.post(
            f"/admin/keys/{rotation_key_id}/rotate",
            data={"csrf_token": rotate_csrf, "reason": "missing confirmation"},
            follow_redirects=False,
        )
        assert rotate_without_confirm.status_code == 303
        assert rotate_without_confirm.headers["location"] == (
            f"/admin/keys/{rotation_key_id}?message=rotation_confirmation_required"
        )
        assert asyncio.run(_get_key(migrated_postgres_url, rotation_key_id)).status == "active"
        assert asyncio.run(_gateway_key_count(migrated_postgres_url)) == before_rotation_count

        rotate_without_reason = client.post(
            f"/admin/keys/{rotation_key_id}/rotate",
            data={"csrf_token": rotate_csrf, "confirm_rotate": "true"},
            follow_redirects=False,
        )
        assert rotate_without_reason.status_code == 303
        assert rotate_without_reason.headers["location"] == (
            f"/admin/keys/{rotation_key_id}?message=rotation_reason_required"
        )
        assert asyncio.run(_get_key(migrated_postgres_url, rotation_key_id)).status == "active"
        assert asyncio.run(_gateway_key_count(migrated_postgres_url)) == before_rotation_count

        rotated = client.post(
            f"/admin/keys/{rotation_key_id}/rotate",
            data={
                "csrf_token": rotate_csrf,
                "confirm_rotate": "true",
                "reason": "dashboard rotation integration",
            },
        )
        assert rotated.status_code == 200
        assert rotated.headers["Cache-Control"] == "no-store, no-cache, must-revalidate"
        assert rotated.headers["Pragma"] == "no-cache"
        replacement_key = _replacement_key_from_html(rotated.text)
        _assert_safe_rotation_result_html(
            rotated.text,
            old_plaintext_key=str(rotation_data["plaintext_key"]),
            replacement_key=replacement_key,
            settings=settings,
        )
        assert asyncio.run(_gateway_key_count(migrated_postgres_url)) == before_rotation_count + 1
        old_rotated_key = asyncio.run(_get_key(migrated_postgres_url, rotation_key_id))
        assert old_rotated_key.status == "revoked"
        assert old_rotated_key.revoked_reason == "dashboard rotation integration"
        new_public_key_id = replacement_key.removeprefix("sk-slaif-").split(".", 1)[0]
        new_key = asyncio.run(_get_key_by_public_id(migrated_postgres_url, new_public_key_id))
        new_key_id = new_key.id
        assert new_key.status == "active"
        assert new_key.public_key_id == new_public_key_id
        assert new_key.token_hash
        assert not new_key.token_hash.startswith("sk-")
        assert replacement_key not in new_key.token_hash
        assert replacement_key not in (new_key.key_hint or "")
        one_time_secret = asyncio.run(_one_time_secret_for_key(migrated_postgres_url, new_key_id))
        assert one_time_secret.purpose == "gateway_key_rotation_email"
        assert replacement_key not in one_time_secret.encrypted_payload
        assert replacement_key not in one_time_secret.nonce
        assert "rotate_key" in asyncio.run(_audit_actions(migrated_postgres_url, rotation_key_id))
        assert "gateway_key_rotation_created" in asyncio.run(_audit_actions(migrated_postgres_url, new_key_id))
        serialized_audit = json.dumps(
            [
                {
                    "action": row.action,
                    "old_values": row.old_values,
                    "new_values": row.new_values,
                    "note": row.note,
                }
                for row in (
                    asyncio.run(_audit_rows(migrated_postgres_url, rotation_key_id))
                    + asyncio.run(_audit_rows(migrated_postgres_url, new_key_id))
                )
            ],
            default=str,
        )
        assert replacement_key not in serialized_audit
        assert new_key.token_hash not in serialized_audit
        assert one_time_secret.encrypted_payload not in serialized_audit
        assert one_time_secret.nonce not in serialized_audit

        detail = client.get(f"/admin/keys/{key_id}")
        assert detail.status_code == 200
        csrf = _csrf_from_html(detail.text)
        before_policy_update = asyncio.run(_get_key(migrated_postgres_url, key_id))
        before_quota_snapshot = _hard_quota_snapshot(before_policy_update)

        invalid_datetime = client.post(
            f"/admin/keys/{key_id}/validity",
            data={
                "csrf_token": csrf,
                "valid_until": "not-a-date",
                "reason": "bad datetime",
            },
            follow_redirects=False,
        )
        assert invalid_datetime.status_code == 303
        assert invalid_datetime.headers["location"] == (
            f"/admin/keys/{key_id}?message=invalid_gateway_key_validity"
        )
        unchanged_after_bad_datetime = asyncio.run(_get_key(migrated_postgres_url, key_id))
        assert unchanged_after_bad_datetime.valid_from == before_policy_update.valid_from
        assert unchanged_after_bad_datetime.valid_until == before_policy_update.valid_until

        new_valid_from = datetime.now(UTC) - timedelta(hours=1)
        new_valid_until = datetime.now(UTC) + timedelta(days=45)
        validity_update = client.post(
            f"/admin/keys/{key_id}/validity",
            data={
                "csrf_token": csrf,
                "valid_from": new_valid_from.isoformat(),
                "valid_until": new_valid_until.isoformat(),
                "reason": "extend workshop window",
            },
            follow_redirects=False,
        )
        assert validity_update.status_code == 303
        assert validity_update.headers["location"] == f"/admin/keys/{key_id}?message=key_validity_updated"
        updated_validity = asyncio.run(_get_key(migrated_postgres_url, key_id))
        assert updated_validity.valid_from.replace(microsecond=0) == new_valid_from.replace(microsecond=0)
        assert updated_validity.valid_until.replace(microsecond=0) == new_valid_until.replace(microsecond=0)
        assert "extend_key" in asyncio.run(_audit_actions(migrated_postgres_url, key_id))

        invalid_limit = client.post(
            f"/admin/keys/{key_id}/limits",
            data={
                "csrf_token": csrf,
                "cost_limit_eur": "-1",
                "reason": "bad limit",
            },
            follow_redirects=False,
        )
        assert invalid_limit.status_code == 303
        assert invalid_limit.headers["location"] == (
            f"/admin/keys/{key_id}?message=invalid_gateway_key_limits"
        )
        unchanged_after_bad_limit = asyncio.run(_get_key(migrated_postgres_url, key_id))
        assert unchanged_after_bad_limit.cost_limit_eur == Decimal("12.000000000")
        assert unchanged_after_bad_limit.token_limit_total == 1200
        assert unchanged_after_bad_limit.request_limit_total == 120

        limit_update = client.post(
            f"/admin/keys/{key_id}/limits",
            data={
                "csrf_token": csrf,
                "cost_limit_eur": "24.000000000",
                "token_limit": "2400",
                "request_limit": "240",
                "reason": "raise hard quota",
            },
            follow_redirects=False,
        )
        assert limit_update.status_code == 303
        assert limit_update.headers["location"] == f"/admin/keys/{key_id}?message=key_limits_updated"
        updated_limits = asyncio.run(_get_key(migrated_postgres_url, key_id))
        assert updated_limits.cost_limit_eur == Decimal("24.000000000")
        assert updated_limits.token_limit_total == 2400
        assert updated_limits.request_limit_total == 240
        after_quota_snapshot = _hard_quota_snapshot(updated_limits)
        for field in (
            "cost_used_eur",
            "tokens_used_total",
            "requests_used_total",
            "cost_reserved_eur",
            "tokens_reserved_total",
            "requests_reserved_total",
            "rate_limit_requests_per_minute",
            "rate_limit_tokens_per_minute",
            "max_concurrent_requests",
            "metadata_json",
        ):
            assert after_quota_snapshot[field] == before_quota_snapshot[field]
        assert "update_key_limits" in asyncio.run(_audit_actions(migrated_postgres_url, key_id))

        detail = client.get(f"/admin/keys/{key_id}")
        assert detail.status_code == 200
        _assert_safe_html(detail.text, data, settings)
        csrf = _csrf_from_html(detail.text)
        used_reset = client.post(
            f"/admin/keys/{key_id}/reset-usage",
            data={
                "csrf_token": csrf,
                "confirm_reset_usage": "true",
                "reason": "reset workshop usage counters",
            },
            follow_redirects=False,
        )
        assert used_reset.status_code == 303
        assert used_reset.headers["location"] == f"/admin/keys/{key_id}?message=key_usage_reset"
        after_used_reset = asyncio.run(_get_key(migrated_postgres_url, key_id))
        assert after_used_reset.cost_used_eur == Decimal("0E-9")
        assert after_used_reset.tokens_used_total == 0
        assert after_used_reset.requests_used_total == 0
        assert after_used_reset.cost_reserved_eur == Decimal("4.000000000")
        assert after_used_reset.tokens_reserved_total == 40
        assert after_used_reset.requests_reserved_total == 4
        assert asyncio.run(_usage_ledger_count(migrated_postgres_url, key_id)) == ledger_count_before_reset
        assert "reset_quota" in asyncio.run(_audit_actions(migrated_postgres_url, key_id))

        detail = client.get(f"/admin/keys/{key_id}")
        csrf = _csrf_from_html(detail.text)
        missing_reserved_confirmation = client.post(
            f"/admin/keys/{key_id}/reset-usage",
            data={
                "csrf_token": csrf,
                "confirm_reset_usage": "true",
                "reset_reserved": "true",
                "reason": "repair stale reserved counters",
            },
            follow_redirects=False,
        )
        assert missing_reserved_confirmation.status_code == 303
        assert missing_reserved_confirmation.headers["location"] == (
            f"/admin/keys/{key_id}?message=reserved_reset_confirmation_required"
        )
        after_missing_reserved_confirmation = asyncio.run(_get_key(migrated_postgres_url, key_id))
        assert after_missing_reserved_confirmation.cost_reserved_eur == Decimal("4.000000000")
        assert after_missing_reserved_confirmation.tokens_reserved_total == 40
        assert after_missing_reserved_confirmation.requests_reserved_total == 4

        detail = client.get(f"/admin/keys/{key_id}")
        csrf = _csrf_from_html(detail.text)
        reserved_reset = client.post(
            f"/admin/keys/{key_id}/reset-usage",
            data={
                "csrf_token": csrf,
                "confirm_reset_usage": "true",
                "reset_reserved": "true",
                "confirm_reset_reserved": "true",
                "reason": "repair stale reserved counters",
            },
            follow_redirects=False,
        )
        assert reserved_reset.status_code == 303
        assert reserved_reset.headers["location"] == f"/admin/keys/{key_id}?message=key_usage_reset"
        after_reserved_reset = asyncio.run(_get_key(migrated_postgres_url, key_id))
        assert after_reserved_reset.cost_reserved_eur == Decimal("0E-9")
        assert after_reserved_reset.tokens_reserved_total == 0
        assert after_reserved_reset.requests_reserved_total == 0
        assert asyncio.run(_usage_ledger_count(migrated_postgres_url, key_id)) == ledger_count_before_reset

        detail = client.get(f"/admin/keys/{key_id}")
        assert detail.status_code == 200
        _assert_safe_html(detail.text, data, settings)
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
