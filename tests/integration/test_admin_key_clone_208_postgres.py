"""208-a GUI reviewed key cloning — owned PostgreSQL integration tests.

Real-app, real-PostgreSQL coverage for the GUI clone workflow (G04):
guided form, review-intent round trip, apply, and read-only receipt
recovery. Every assertion is on PERSISTED state (key rows, policy
columns, metadata JSON, one-time-secret and email-delivery rows, audit
rows) or the rendered operator page — the core clone service's own
concurrency/rollback/replay proofs are component evidence from the
qualified core/CLI rounds and are not re-run here.

The seed coexists with other integration modules on one session
database: provider configs and model routes are get-or-create (the
provider slug is DB-unique), while owners/institutions/cohorts use
run-unique names.
"""

import asyncio
import re
import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from slaif_gateway.config import Settings
from slaif_gateway.db.models import (
    AuditLog,
    EmailDelivery,
    GatewayKey,
    OneTimeSecret,
)
from slaif_gateway.db.repositories.admin_users import AdminUsersRepository
from slaif_gateway.db.repositories.cohorts import CohortsRepository
from slaif_gateway.db.repositories.institutions import InstitutionsRepository
from slaif_gateway.db.repositories.owners import OwnersRepository
from slaif_gateway.db.repositories.provider_configs import ProviderConfigsRepository
from slaif_gateway.db.repositories.routing import ModelRoutesRepository
from slaif_gateway.main import create_app
from slaif_gateway.services.email_delivery_service import EmailDeliveryService
from slaif_gateway.services.email_errors import EmailError
from slaif_gateway.utils.passwords import hash_admin_password
from slaif_gateway.utils.secrets import generate_secret_key

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')
TOKEN_RE = re.compile(r'name="clone_review_intent" value="([^"]+)"')
OPERATION_RE = re.compile(
    r"clone/receipts\?operation=([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}"
    r"-[0-9a-f]{4}-[0-9a-f]{12})"
)
SECRET_DISPLAY_RE = re.compile(
    r'class="secret-display".*?<code>([^<]+)</code>', re.DOTALL
)

ADMIN_PASSWORD = "correct horse battery staple"
DURATION_SECONDS = 3601  # deliberately non-minute


def _settings(database_url: str, **overrides) -> Settings:
    base = dict(
        APP_ENV="test",
        DATABASE_URL=database_url,
        ADMIN_SESSION_SECRET="s" * 40,
        TOKEN_HMAC_SECRET="hmac-secret-for-208-tests",
        ONE_TIME_SECRET_ENCRYPTION_KEY=generate_secret_key(),
        OPENAI_UPSTREAM_API_KEY="sk-provider-secret-placeholder",
        OPENROUTER_API_KEY="sk-or-provider-secret-placeholder",
    )
    base.update(overrides)
    return Settings(**base)


def _csrf_from_html(html: str) -> str:
    match = CSRF_RE.search(html)
    assert match is not None
    return match.group(1)


def asyncio_run(coro):
    return asyncio.run(coro)


def _engine(database_url: str):
    return create_async_engine(database_url, future=True)


def _session_factory(database_url: str):
    return async_sessionmaker(_engine(database_url), expire_on_commit=False)


async def _seed(database_url: str) -> dict[str, object]:
    engine = _engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(UTC)
    try:
        async with factory() as session:
            async with session.begin():
                admin = await AdminUsersRepository(session).create_admin_user(
                    email=f"admin-{uuid.uuid4()}@example.org",
                    display_name="208 Integration Admin",
                    password_hash=hash_admin_password(ADMIN_PASSWORD),
                    role="admin",
                    is_active=True,
                )
                institution = await InstitutionsRepository(session).create_institution(
                    name=f"208 Institute {uuid.uuid4()}",
                    country="SI",
                )
                cohort = await CohortsRepository(session).create_cohort(
                    name=f"208 Workshop {uuid.uuid4()}",
                    starts_at=now - timedelta(days=1),
                    ends_at=now + timedelta(days=30),
                )
                owner = await OwnersRepository(session).create_owner(
                    name="Grace",
                    surname="Hopper",
                    email=f"owner-{uuid.uuid4()}@example.org",
                    institution_id=institution.id,
                )
                # Alternate clone TARGET owner (distinct from the source
                # owner) so ignored target controls would be detected.
                target_owner = await OwnersRepository(session).create_owner(
                    name="Ada",
                    surname="Lovelace",
                    email=f"target-owner-{uuid.uuid4()}@example.org",
                    institution_id=institution.id,
                )
                # Provider slugs are DB-unique across the session database:
                # get-or-create so this module coexists with other PG tests.
                providers = ProviderConfigsRepository(session)
                if await providers.get_provider_config_by_provider("openai") is None:
                    await providers.create_provider_config(
                        provider="openai",
                        display_name="OpenAI (208)",
                        base_url="https://api.openai.test/v1",
                        api_key_env_var="OPENAI_UPSTREAM_API_KEY",
                    )
                if (
                    await providers.get_provider_config_by_provider("openrouter")
                    is None
                ):
                    await providers.create_provider_config(
                        provider="openrouter",
                        display_name="OpenRouter (208)",
                        base_url="https://openrouter.test/v1",
                        api_key_env_var="OPENROUTER_API_KEY",
                    )
                routes = ModelRoutesRepository(session)
                for provider, requested, upstream in (
                    ("openai", "gpt-test", "gpt-test"),
                    ("openrouter", "gpt-other", "gpt-other"),
                ):
                    existing = {
                        r.requested_model
                        for r in await routes.list_model_routes(provider=provider)
                    }
                    if requested not in existing:
                        await routes.create_model_route(
                            requested_model=requested,
                            provider=provider,
                            upstream_model=upstream,
                            endpoint="/v1/chat/completions",
                        )
                return {
                    "admin_email": admin.email,
                    "admin_id": admin.id,
                    "owner_id": owner.id,
                    "target_owner_id": target_owner.id,
                    "cohort_id": cohort.id,
                }
    finally:
        await engine.dispose()


_SEED_CACHE: dict[str, dict[str, object]] = {}


def _seed_sync(database_url: str) -> dict[str, object]:
    """One shared seed per database (provider slugs are DB-unique)."""
    if database_url not in _SEED_CACHE:
        _SEED_CACHE[database_url] = asyncio_run(_seed(database_url))
    return _SEED_CACHE[database_url]


def _login(client: TestClient, data: dict[str, object]) -> None:
    login_page = client.get("/admin/login")
    csrf = _csrf_from_html(login_page.text)
    response = client.post(
        "/admin/login",
        data={
            "email": data["admin_email"],
            "password": ADMIN_PASSWORD,
            "csrf_token": csrf,
        },
        follow_redirects=False,
    )
    assert response.status_code == 303


def _create_key(
    client: TestClient,
    *,
    owner_id: uuid.UUID,
    extra: dict[str, str] | None = None,
) -> None:
    page = client.get("/admin/keys/create")
    assert page.status_code == 200
    csrf = _csrf_from_html(page.text)
    payload: dict[str, str] = {
        "csrf_token": csrf,
        "owner_id": str(owner_id),
        "valid_days": "30",
        "email_delivery_mode": "none",
        "allow_all_models": "true",
        "allow_all_endpoints": "true",
    }
    if extra:
        payload.update(extra)
    response = client.post("/admin/keys/create", data=payload, follow_redirects=False)
    assert response.status_code == 200, response.text[:800]


async def _owner_keys(database_url: str, owner_id: uuid.UUID) -> list[GatewayKey]:
    engine = _engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            result = await session.execute(
                select(GatewayKey)
                .where(GatewayKey.owner_id == owner_id)
                .order_by(GatewayKey.created_at.asc(), GatewayKey.id.asc())
            )
            keys = list(result.scalars().all())
            for key in keys:
                await session.refresh(key)
            return keys
    finally:
        await engine.dispose()


def _policy_row(key: GatewayKey) -> dict[str, object]:
    """Non-secret policy/usage fields used for fidelity and isolation."""
    metadata = key.metadata_json if isinstance(key.metadata_json, dict) else {}
    return {
        "status": key.status,
        "key_purpose": key.key_purpose,
        "capability_policy_mode": key.capability_policy_mode,
        "owner_id": key.owner_id,
        "cohort_id": key.cohort_id,
        "allow_all_models": key.allow_all_models,
        "allowed_models": key.allowed_models,
        "allow_all_endpoints": key.allow_all_endpoints,
        "allowed_endpoints": key.allowed_endpoints,
        "cost_limit_eur": key.cost_limit_eur,
        "token_limit_total": key.token_limit_total,
        "request_limit_total": key.request_limit_total,
        "rate_limit_requests_per_minute": key.rate_limit_requests_per_minute,
        "rate_limit_tokens_per_minute": key.rate_limit_tokens_per_minute,
        "max_concurrent_requests": key.max_concurrent_requests,
        "cost_used_eur": key.cost_used_eur,
        "tokens_used_total": key.tokens_used_total,
        "requests_used_total": key.requests_used_total,
        "cost_reserved_eur": key.cost_reserved_eur,
        "tokens_reserved_total": key.tokens_reserved_total,
        "requests_reserved_total": key.requests_reserved_total,
        "allowed_providers": metadata.get("allowed_providers"),
        "rate_limit_policy": metadata.get("rate_limit_policy"),
        "lazy_throttling_policy": metadata.get("lazy_throttling_policy"),
    }


async def _secret_row(database_url: str, key_id: uuid.UUID):
    engine = _engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            secret = (
                await session.execute(
                    select(OneTimeSecret).where(OneTimeSecret.gateway_key_id == key_id)
                )
            ).scalar_one_or_none()
            if secret is None:
                return None
            await session.refresh(secret)
            return (secret.id, secret.status, secret.consumed_at, secret.created_at)
    finally:
        await engine.dispose()


async def _clone_audit_count(database_url: str) -> int:
    engine = _engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            result = await session.execute(
                select(func.count())
                .select_from(AuditLog)
                .where(AuditLog.action == "gateway_key_cloned")
            )
            return int(result.scalar_one())
    finally:
        await engine.dispose()


async def _set_source_valid_until(
    database_url: str, key_id: uuid.UUID, valid_until: datetime
) -> None:
    engine = _engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            async with session.begin():
                key = await session.get(GatewayKey, key_id)
                assert key is not None
                key.valid_until = valid_until
    finally:
        await engine.dispose()


def _review(
    client: TestClient,
    source_id: uuid.UUID,
    *,
    validity_mode: str = "duration-from-now",
    duration_value: str = str(DURATION_SECONDS),
    duration_unit: str = "seconds",
    delivery_mode: str = "none",
    target_owner_id: str = "",
    target_cohort_id: str = "",
):
    page = client.get(f"/admin/keys/{source_id}/clone")
    assert page.status_code == 200
    csrf = _csrf_from_html(page.text)
    return client.post(
        f"/admin/keys/{source_id}/clone/review",
        data={
            "csrf_token": csrf,
            "target_owner_id": target_owner_id,
            "target_cohort_id": target_cohort_id,
            "validity_mode": validity_mode,
            "duration_value": duration_value,
            "duration_unit": duration_unit,
            "email_delivery_mode": delivery_mode,
        },
        follow_redirects=False,
    )


def _apply(client: TestClient, source_id: uuid.UUID, token: str, reason: str):
    detail = client.get(f"/admin/keys/{source_id}")
    assert detail.status_code == 200
    csrf = _csrf_from_html(detail.text)
    return client.post(
        f"/admin/keys/{source_id}/clone/apply",
        data={
            "csrf_token": csrf,
            "clone_review_intent": token,
            "confirm_apply": "true",
            "reason": reason,
        },
        follow_redirects=False,
    )


# ---------------------------------------------------------------------------
# Faithful canonical clone + source/unrelated isolation + exact-repeat + recovery
# ---------------------------------------------------------------------------


def test_clone_guided_flow_persists_faithful_canonical_clone(
    migrated_postgres_url: str,
) -> None:
    data = _seed_sync(migrated_postgres_url)
    owner_id = data["owner_id"]
    target_owner_id = data["target_owner_id"]
    cohort_id = data["cohort_id"]
    assert isinstance(owner_id, uuid.UUID)
    assert isinstance(target_owner_id, uuid.UUID)
    assert isinstance(cohort_id, uuid.UUID)
    app = create_app(_settings(migrated_postgres_url))
    with TestClient(app) as client:
        _login(client, data)

        _create_key(
            client,
            owner_id=owner_id,
            extra={
                "allowed_providers": "openai",
                "cost_limit_eur": "12.345678901",
                "token_limit_total": "9000",
                "request_limit_total": "300",
                "rate_limit_requests_per_minute": "30",
                "rate_limit_tokens_per_minute": "10000",
                "rate_limit_concurrent_requests": "2",
                "rate_limit_window_seconds": "10",
                "lazy_throttling_mode": "wait",
                "lazy_throttling_max_wait_seconds": "30",
                "lazy_throttling_max_waiting_requests": "2",
                "reason": "208 clone source key",
            },
        )
        # Unrelated key under the TARGET owner: an isolated snapshot that
        # must not move when the source owner's key is cloned.
        _create_key(
            client,
            owner_id=target_owner_id,
            extra={"allowed_providers": "openrouter", "reason": "208 unrelated key"},
        )
        source_keys = asyncio_run(_owner_keys(migrated_postgres_url, owner_id))
        unrelated_keys = asyncio_run(_owner_keys(migrated_postgres_url, target_owner_id))
        assert len(source_keys) == 1
        assert len(unrelated_keys) == 1
        source = source_keys[0]
        unrelated = unrelated_keys[0]
        source_before = _policy_row(source)
        unrelated_before = _policy_row(unrelated)
        source_secret_before = asyncio_run(_secret_row(migrated_postgres_url, source.id))
        unrelated_secret_before = asyncio_run(
            _secret_row(migrated_postgres_url, unrelated.id)
        )
        audits_before = asyncio_run(_clone_audit_count(migrated_postgres_url))
        created_before = datetime.now(UTC)

        # 1. Guided form: source identity + core eligibility + form controls.
        form = client.get(f"/admin/keys/{source.id}/clone")
        assert form.status_code == 200
        assert source.public_key_id in form.text
        assert "not eligible for cloning" not in form.text
        assert "Eligibility: " in form.text
        assert "copy-source-expiry" in form.text
        assert "duration-from-now" in form.text

        # 2. Review: readable canonical policy, signed intent, no secrets.
        # The target is the ALTERNATE owner and cohort (an ordinary
        # non-default selection that must reach the persisted target).
        review = _review(
            client,
            source.id,
            target_owner_id=str(target_owner_id),
            target_cohort_id=str(cohort_id),
            delivery_mode="none",
        )
        assert review.status_code == 200, review.text[:800]
        assert "Allow-list: openai" in review.text
        assert "Wait for capacity: max wait 30s" in review.text
        token_match = TOKEN_RE.search(review.text)
        assert token_match is not None
        token = token_match.group(1)
        operation_match = OPERATION_RE.search(review.text)
        assert operation_match is not None, "review page must show the operation"
        reviewed_operation = operation_match.group(1)
        review_has_key_material = "sk-slaif-" in review.text
        assert not review_has_key_material, "review page must not show a key"

        # 3. Apply: one-time plaintext result, no-store, persisted target.
        result = _apply(client, source.id, token, "208 guided clone")
        assert result.status_code == 200, result.text[:800]
        assert "Plaintext Gateway Key (one-time display)" in result.text
        secret_match = SECRET_DISPLAY_RE.search(result.text)
        assert secret_match is not None, "plaintext key not displayed exactly once"
        displayed = secret_match.group(1)
        prefix_ok = displayed.startswith("sk-slaif-")
        count_ok = result.text.count(displayed) == 1
        assert prefix_ok and count_ok, "displayed key shape/count wrong"
        cache_headers = [
            v for k, v in result.headers.items() if k.lower() == "cache-control"
        ]
        assert any("no-store" in v for v in cache_headers)

        # 4. Persisted target: faithful canonical policy, independent identity,
        #    under the alternate owner and cohort.
        target_keys = asyncio_run(_owner_keys(migrated_postgres_url, target_owner_id))
        assert len(target_keys) == 2, "clone must create exactly one new key"
        target = next(k for k in target_keys if k.id != unrelated.id)
        target_policy = _policy_row(target)
        for field in (
            "status",
            "key_purpose",
            "capability_policy_mode",
            "cohort_id",
            "allow_all_models",
            "allowed_models",
            "allow_all_endpoints",
            "allowed_endpoints",
            "cost_limit_eur",
            "token_limit_total",
            "request_limit_total",
            "rate_limit_requests_per_minute",
            "rate_limit_tokens_per_minute",
            "max_concurrent_requests",
            "allowed_providers",
            "rate_limit_policy",
            "lazy_throttling_policy",
        ):
            expected = source_before[field]
            if field == "cohort_id":
                expected = cohort_id
            assert target_policy[field] == expected, field
        target_owner_ok = target_policy["owner_id"] == target_owner_id
        assert target_owner_ok, "target owner control was ignored"
        for field in (
            "cost_used_eur",
            "tokens_used_total",
            "requests_used_total",
            "cost_reserved_eur",
            "tokens_reserved_total",
            "requests_reserved_total",
        ):
            assert target_policy[field] == 0, field
        independent_hash = target.token_hash != source.token_hash
        assert independent_hash, "target must have independent key material"
        assert target.public_key_id != source.public_key_id
        assert str(target.id) in result.text, "result must link the persisted target"
        # Exact 3601s window from execution time (non-minute, exact).
        window = target.valid_until - target.valid_from
        assert window == timedelta(seconds=DURATION_SECONDS), "window not exact"
        assert target.valid_until > created_before

        # Receipt + one-time secret + audit.
        receipt = target.metadata_json.get("clone_receipt")
        assert isinstance(receipt, dict) and receipt.get("status") == "created"
        assert receipt.get("source_gateway_key_id") == str(source.id)
        assert receipt.get("target_gateway_key_id") == str(target.id)
        assert receipt.get("target_owner_id") == str(target_owner_id)
        assert receipt.get("target_cohort_id") == str(cohort_id)
        assert receipt.get("operation_uuid") == reviewed_operation
        assert isinstance(receipt.get("source_fingerprint"), str)
        target_secret = asyncio_run(_secret_row(migrated_postgres_url, target.id))
        assert target_secret is not None, "target must have a one-time secret row"
        audits_after = asyncio_run(_clone_audit_count(migrated_postgres_url))
        assert audits_after == audits_before + 1

        # 5. Source and unrelated rows unchanged.
        source_final = asyncio_run(_owner_keys(migrated_postgres_url, owner_id))[0]
        unrelated_final = next(
            k for k in asyncio_run(_owner_keys(migrated_postgres_url, target_owner_id))
            if k.id == unrelated.id
        )
        same_source = _policy_row(source_final) == source_before
        same_unrelated = _policy_row(unrelated_final) == unrelated_before
        assert same_source and same_unrelated, "source/unrelated rows changed"
        source_secret_after = asyncio_run(_secret_row(migrated_postgres_url, source.id))
        unrelated_secret_after = asyncio_run(
            _secret_row(migrated_postgres_url, unrelated.id)
        )
        assert source_secret_after == source_secret_before
        assert unrelated_secret_after == unrelated_secret_before

        # 6. Exact-repeat: same operation -> already-applied, no second key.
        repeat = _apply(client, source.id, token, "208 exact repeat")
        assert repeat.status_code == 200, repeat.text[:800]
        assert "Already Applied" in repeat.text
        no_redisplay = SECRET_DISPLAY_RE.search(repeat.text) is None
        assert no_redisplay, "already-applied must not redisplay plaintext"
        repeat_keys = asyncio_run(_owner_keys(migrated_postgres_url, target_owner_id))
        assert len(repeat_keys) == 2
        repeat_target = next(k for k in repeat_keys if k.id == target.id)
        assert _policy_row(repeat_target) == target_policy
        assert asyncio_run(_clone_audit_count(migrated_postgres_url)) == audits_after

        # 7. Recovery: created projection + not-found, read-only.
        recovered = client.get(
            f"/admin/keys/{source.id}/clone/receipts?operation={reviewed_operation}"
        )
        assert recovered.status_code == 200
        assert "completed and created exactly one target key" in recovered.text
        assert str(target.id) in recovered.text
        missing = client.get(
            f"/admin/keys/{source.id}/clone/receipts?operation={uuid.uuid4()}"
        )
        assert missing.status_code == 200
        assert "No clone receipt matches" in missing.text
        recovery_keys = asyncio_run(_owner_keys(migrated_postgres_url, target_owner_id))
        assert len(recovery_keys) == 2, "recovery must never create keys"


# ---------------------------------------------------------------------------
# Stale / tampered review refused before any write
# ---------------------------------------------------------------------------


def test_clone_stale_and_tampered_reviews_refused_before_writes(
    migrated_postgres_url: str,
) -> None:
    data = _seed_sync(migrated_postgres_url)
    owner_id = data["owner_id"]
    target_owner_id = data["target_owner_id"]
    app = create_app(_settings(migrated_postgres_url))
    with TestClient(app) as client:
        _login(client, data)
        _create_key(
            client,
            owner_id=owner_id,
            extra={
                "allowed_providers": "openai",
                "request_limit_total": "50",
                "reason": "208 stale probe source",
            },
        )
        source = next(
            k
            for k in asyncio_run(_owner_keys(migrated_postgres_url, owner_id))
            if k.request_limit_total == 50
        )
        audits_before = asyncio_run(_clone_audit_count(migrated_postgres_url))

        # Stale: the source validity changes AFTER the review is built.
        review = _review(client, source.id, target_owner_id=str(target_owner_id))
        assert review.status_code == 200, review.text[:800]
        stale_token = TOKEN_RE.search(review.text).group(1)
        asyncio_run(
            _set_source_valid_until(
                migrated_postgres_url,
                source.id,
                datetime.now(UTC) + timedelta(days=1),
            )
        )
        # Snapshot AFTER the intentional change: the refusal must not move
        # this state (or the audit log) at all.
        after_change = asyncio_run(_owner_keys(migrated_postgres_url, owner_id))
        baseline_ids = [k.id for k in after_change]
        baseline_rows = {k.id: _policy_row(k) for k in after_change}
        stale = _apply(client, source.id, stale_token, "208 stale apply")
        assert stale.status_code == 400
        assert "stale" in stale.text
        assert [k.id for k in asyncio_run(_owner_keys(migrated_postgres_url, owner_id))] == (
            baseline_ids
        )
        final_rows = {
            k.id: _policy_row(k)
            for k in asyncio_run(_owner_keys(migrated_postgres_url, owner_id))
        }
        assert final_rows == baseline_rows, "stale refusal wrote state"
        assert asyncio_run(_clone_audit_count(migrated_postgres_url)) == audits_before

        # Tamper: a corrupted intent token is refused before any mutation.
        review2 = _review(client, source.id, target_owner_id=str(target_owner_id))
        assert review2.status_code == 200, review2.text[:800]
        token2 = TOKEN_RE.search(review2.text).group(1)
        flipped = "0" if token2[-1] in "abcdefgh" else "a"
        tampered = token2[:-1] + flipped
        assert tampered != token2
        pre_tamper_rows = {
            k.id: _policy_row(k)
            for k in asyncio_run(_owner_keys(migrated_postgres_url, owner_id))
        }
        tamper = _apply(client, source.id, tampered, "208 tampered apply")
        assert tamper.status_code == 400
        final_tamper_rows = {
            k.id: _policy_row(k)
            for k in asyncio_run(_owner_keys(migrated_postgres_url, owner_id))
        }
        assert final_tamper_rows == pre_tamper_rows, "tamper refusal wrote state"
        assert asyncio_run(_clone_audit_count(migrated_postgres_url)) == audits_before


# ---------------------------------------------------------------------------
# Committed clone + post-commit dispatch failure -> recovery outcome
# ---------------------------------------------------------------------------


def test_clone_send_now_post_commit_failure_recovers(
    migrated_postgres_url: str, monkeypatch
) -> None:
    data = _seed_sync(migrated_postgres_url)
    owner_id = data["owner_id"]
    target_owner_id = data["target_owner_id"]
    settings = _settings(
        migrated_postgres_url,
        ENABLE_EMAIL_DELIVERY=True,
        SMTP_HOST="smtp.test.invalid",
        SMTP_FROM="admin@example.org",
    )
    app = create_app(settings)

    async def _boom(
        self,
        *,
        one_time_secret_id,
        email_delivery_id=None,
        actor_admin_id=None,
        reason=None,
    ):
        raise EmailError("smtp down (synthetic)")

    monkeypatch.setattr(EmailDeliveryService, "send_pending_key_email", _boom)
    with TestClient(app) as client:
        _login(client, data)
        _create_key(
            client,
            owner_id=owner_id,
            extra={
                "allowed_providers": "openai",
                "request_limit_total": "60",
                "reason": "208 delivery-failure source",
            },
        )
        source = next(
            k
            for k in asyncio_run(_owner_keys(migrated_postgres_url, owner_id))
            if k.request_limit_total == 60
        )
        keys_before = asyncio_run(_owner_keys(migrated_postgres_url, target_owner_id))
        audits_before = asyncio_run(_clone_audit_count(migrated_postgres_url))

        review = _review(
            client,
            source.id,
            target_owner_id=str(target_owner_id),
            delivery_mode="send-now",
        )
        assert review.status_code == 200, review.text[:800]
        token = TOKEN_RE.search(review.text).group(1)
        reviewed_operation = OPERATION_RE.search(review.text).group(1)
        result = _apply(client, source.id, token, "208 delivery failure")
        assert result.status_code == 200, result.text[:800]
        assert "Created With Delivery Failure" in result.text
        assert "A second clone is NOT needed" in result.text
        no_plaintext = SECRET_DISPLAY_RE.search(result.text) is None
        assert no_plaintext, "send-now outcome must not display plaintext"
        assert str(source.id) in result.text

        keys_after = asyncio_run(_owner_keys(migrated_postgres_url, target_owner_id))
        assert len(keys_after) == len(keys_before) + 1
        target = next(k for k in keys_after if k.id not in {b.id for b in keys_before})
        receipt = target.metadata_json.get("clone_receipt")
        assert isinstance(receipt, dict) and receipt.get("status") == "created"
        assert receipt.get("operation_uuid") == reviewed_operation
        assert asyncio_run(_clone_audit_count(migrated_postgres_url)) == (
            audits_before + 1
        )

        # The pending delivery is persisted and recoverable.
        async def _pending_delivery() -> tuple[int, object | None]:
            engine = _engine(migrated_postgres_url)
            factory = async_sessionmaker(engine, expire_on_commit=False)
            try:
                async with factory() as session:
                    rows = (
                        await session.execute(
                            select(EmailDelivery).where(
                                EmailDelivery.gateway_key_id == target.id
                            )
                        )
                    ).scalars().all()
                    statuses = sorted(r.status for r in rows)
                    return len(rows), (statuses or [None])[0]
            finally:
                await engine.dispose()

        delivery_rows, delivery_status = asyncio_run(_pending_delivery())
        assert delivery_rows == 1
        assert delivery_status in {"pending", "sending", "failed"}, delivery_status

        recovered = client.get(
            f"/admin/keys/{source.id}/clone/receipts"
            f"?operation={receipt['operation_uuid']}"
        )
        assert recovered.status_code == 200
        assert "completed and created exactly one target key" in recovered.text
        assert str(target.id) in recovered.text


# ---------------------------------------------------------------------------
# Unsupported source + delivery preconditions
# ---------------------------------------------------------------------------


def test_clone_unsupported_source_and_delivery_preconditions(
    migrated_postgres_url: str,
) -> None:
    data = _seed_sync(migrated_postgres_url)
    owner_id = data["owner_id"]
    target_owner_id = data["target_owner_id"]
    app = create_app(_settings(migrated_postgres_url))
    with TestClient(app) as client:
        _login(client, data)
        _create_key(
            client,
            owner_id=owner_id,
            extra={
                "allowed_providers": "openai",
                "request_limit_total": "70",
                "reason": "208 suspend probe source",
            },
        )
        source = next(
            k
            for k in asyncio_run(_owner_keys(migrated_postgres_url, owner_id))
            if k.request_limit_total == 70
        )
        baseline = [k.id for k in asyncio_run(_owner_keys(migrated_postgres_url, owner_id))]
        audits_before = asyncio_run(_clone_audit_count(migrated_postgres_url))

        # Suspend the source through the existing admin action.
        detail = client.get(f"/admin/keys/{source.id}")
        csrf = _csrf_from_html(detail.text)
        suspend = client.post(
            f"/admin/keys/{source.id}/suspend",
            data={"csrf_token": csrf, "reason": "208 suspend probe"},
            follow_redirects=False,
        )
        assert suspend.status_code == 303
        keys_suspended = asyncio_run(_owner_keys(migrated_postgres_url, owner_id))
        suspended = next(k for k in keys_suspended if k.id == source.id)
        assert suspended.status == "suspended"

        # Form shows the controlled unsupported state (no crash, no 500).
        form = client.get(f"/admin/keys/{source.id}/clone")
        assert form.status_code == 200
        assert "not eligible for cloning" in form.text
        assert "active status" in form.text

        # Review is refused with the fixed core message and builds no token.
        review = _review(client, source.id, target_owner_id=str(target_owner_id))
        assert review.status_code == 400
        assert "not eligible for cloning" in review.text
        no_token = TOKEN_RE.search(review.text) is None
        assert no_token, "ineligible review must not issue an intent token"
        assert [
            k.id for k in asyncio_run(_owner_keys(migrated_postgres_url, owner_id))
        ] == baseline
        assert asyncio_run(_clone_audit_count(migrated_postgres_url)) == audits_before

        # Send-now is refused before any service work when delivery is disabled.
        _create_key(
            client,
            owner_id=owner_id,
            extra={
                "allowed_providers": "openai",
                "request_limit_total": "80",
                "reason": "208 precondition source",
            },
        )
        active = next(
            k
            for k in asyncio_run(_owner_keys(migrated_postgres_url, owner_id))
            if k.request_limit_total == 80
        )
        precondition = _review(
            client, active.id, target_owner_id=str(target_owner_id), delivery_mode="send-now"
        )
        assert precondition.status_code == 400
        assert "Email delivery must be enabled" in precondition.text
        no_token2 = TOKEN_RE.search(precondition.text) is None
        assert no_token2
