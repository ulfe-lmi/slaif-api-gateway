"""207-a GUI key policy administration — owned PostgreSQL integration tests.

Real-app, real-PostgreSQL coverage for G01 (provider tri-state + advanced
version-1 configuration import/export), G02 (existing-key rate editor),
and G03 (effective-policy inspection + explain model access). The database
is the session ``migrated_postgres_url`` (an owned loopback/tmpfs
PostgreSQL 16 under CI, or ``TEST_DATABASE_URL`` locally).

Every assertion is on PERSISTED state (columns, metadata JSON, audit
rows) or the rendered operator page — not on helper call counts.
"""

import json
import re
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from slaif_gateway.config import Settings
from slaif_gateway.db.models import (
    AdminSession,
    AuditLog,
    GatewayKey,
    OneTimeSecret,
    ProviderConfig,
)
from slaif_gateway.db.repositories.admin_users import AdminUsersRepository
from slaif_gateway.db.repositories.cohorts import CohortsRepository
from slaif_gateway.db.repositories.institutions import InstitutionsRepository
from slaif_gateway.db.repositories.owners import OwnersRepository
from slaif_gateway.db.repositories.provider_configs import ProviderConfigsRepository
from slaif_gateway.db.repositories.routing import ModelRoutesRepository
from slaif_gateway.main import create_app
from slaif_gateway.services.key_policy_inspection import build_key_policy_inspection
from slaif_gateway.utils.passwords import hash_admin_password
from slaif_gateway.utils.secrets import generate_secret_key

# A synthetic credential-shaped canary used ONLY as submitted input that a
# rejected document may contain; assertions are booleans over rendered
# output (the value itself is synthetic, not a live secret).
CONFIG_CANARY = "sk-slaif-canary-" + "9" * 40


def _settings(database_url: str) -> Settings:
    return Settings(
        APP_ENV="test",
        DATABASE_URL=database_url,
        ADMIN_SESSION_SECRET="s" * 40,
        TOKEN_HMAC_SECRET="hmac-secret-for-207-tests",
        ONE_TIME_SECRET_ENCRYPTION_KEY=generate_secret_key(),
        OPENAI_UPSTREAM_API_KEY="sk-provider-secret-placeholder",
        OPENROUTER_API_KEY="sk-or-provider-secret-placeholder",
    )


def _csrf_from_html(html: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert match is not None
    return match.group(1)


def asyncio_run(coro):
    import asyncio

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
                    display_name="207 Integration Admin",
                    password_hash=hash_admin_password("correct horse battery staple"),
                    role="admin",
                    is_active=True,
                )
                institution = await InstitutionsRepository(session).create_institution(
                    name=f"207 Institute {uuid.uuid4()}",
                    country="SI",
                )
                cohort = await CohortsRepository(session).create_cohort(
                    name=f"207 Workshop {uuid.uuid4()}",
                    starts_at=now - timedelta(days=1),
                    ends_at=now + timedelta(days=30),
                )
                owner = await OwnersRepository(session).create_owner(
                    name="Grace",
                    surname="Hopper",
                    email=f"owner-{uuid.uuid4()}@example.org",
                    institution_id=institution.id,
                )
                providers = ProviderConfigsRepository(session)
                await providers.create_provider_config(
                    provider="openai",
                    display_name="OpenAI (207)",
                    base_url="https://api.openai.test/v1",
                    api_key_env_var="OPENAI_UPSTREAM_API_KEY",
                )
                await providers.create_provider_config(
                    provider="openrouter",
                    display_name="OpenRouter (207)",
                    base_url="https://openrouter.test/v1",
                    api_key_env_var="OPENROUTER_API_KEY",
                )
                routes = ModelRoutesRepository(session)
                await routes.create_model_route(
                    requested_model="gpt-test",
                    provider="openai",
                    upstream_model="gpt-test",
                    endpoint="/v1/chat/completions",
                )
                await routes.create_model_route(
                    requested_model="gpt-other",
                    provider="openrouter",
                    upstream_model="gpt-other",
                    endpoint="/v1/chat/completions",
                )
                return {
                    "admin_email": admin.email,
                    "admin_password": "correct horse battery staple",
                    "admin_id": admin.id,
                    "owner_id": owner.id,
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
            "password": data["admin_password"],
            "csrf_token": csrf,
        },
        follow_redirects=False,
    )
    assert response.status_code == 303


def _create_key(
    client: TestClient,
    data: dict[str, object],
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
    }
    payload.update({str(k): str(v) for k, v in data.items()})
    if extra:
        payload.update(extra)
    response = client.post("/admin/keys/create", data=payload, follow_redirects=False)
    assert response.status_code == 200, response.text[:800]
    return None


async def _latest_key(database_url: str, owner_id: uuid.UUID) -> GatewayKey:
    engine = _engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            result = await session.execute(
                select(GatewayKey)
                .where(GatewayKey.owner_id == owner_id)
                .order_by(GatewayKey.created_at.desc(), GatewayKey.id.desc())
                .limit(1)
            )
            key = result.scalar_one()
            await session.refresh(key)
            return key
    finally:
        await engine.dispose()


async def _key_row_snapshot(database_url: str, key_id: uuid.UUID) -> dict[str, object]:
    engine = _engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            key = await session.get(GatewayKey, key_id)
            assert key is not None
            secret = (
                await session.execute(
                    select(OneTimeSecret).where(OneTimeSecret.gateway_key_id == key_id)
                )
            ).scalar_one_or_none()
            return {
                "valid_from": key.valid_from,
                "valid_until": key.valid_until,
                "cost_used_eur": key.cost_used_eur,
                "tokens_used_total": key.tokens_used_total,
                "requests_used_total": key.requests_used_total,
                "cost_reserved_eur": key.cost_reserved_eur,
                "tokens_reserved_total": key.tokens_reserved_total,
                "requests_reserved_total": key.requests_reserved_total,
                "token_hash": key.token_hash,
                "owner_id": key.owner_id,
                "cohort_id": key.cohort_id,
                "secret_present": secret is not None,
                "secret_immutable": (
                    (secret.encrypted_payload, secret.nonce, secret.consumed_at, secret.status)
                    if secret is not None
                    else None
                ),
            }
    finally:
        await engine.dispose()


async def _audit_count(database_url: str) -> int:
    engine = _engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            result = await session.execute(select(func.count()).select_from(AuditLog))
            return int(result.scalar_one())
    finally:
        await engine.dispose()


async def _last_audit(database_url: str, action: str) -> AuditLog | None:
    engine = _engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            result = await session.execute(
                select(AuditLog)
                .where(AuditLog.action == action)
                .order_by(AuditLog.created_at.desc())
                .limit(1)
            )
            return result.scalar_one_or_none()
    finally:
        await engine.dispose()


def _provider_state(database_url: str):
    """Return the openrouter provider config id (for enable/disable)."""

    async def _run():
        engine = _engine(database_url)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with factory() as session:
                result = await session.execute(
                    select(ProviderConfig).where(ProviderConfig.provider == "openrouter")
                )
                return result.scalar_one()
        finally:
            await engine.dispose()

    return asyncio_run(_run())


def _set_provider_enabled(database_url: str, provider: str, enabled: bool) -> None:
    async def _run():
        engine = _engine(database_url)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with factory() as session:
                async with session.begin():
                    result = await session.execute(
                        select(ProviderConfig).where(ProviderConfig.provider == provider)
                    )
                    config = result.scalar_one()
                    config.enabled = enabled
        finally:
            await engine.dispose()

    asyncio_run(_run())


# ---------------------------------------------------------------------------
# G01: provider tri-state
# ---------------------------------------------------------------------------


def test_provider_tri_state_persisted_and_rendered(migrated_postgres_url: str) -> None:
    data = _seed_sync(migrated_postgres_url)
    owner_id = data["owner_id"]
    assert isinstance(owner_id, uuid.UUID)
    app = create_app(_settings(migrated_postgres_url))
    with TestClient(app) as client:
        _login(client, data)

        # Unrestricted (stored NULL).
        _create_key(
            client,
            {
                "allow_all_providers": "true",
                "allow_all_models": "true",
                "allow_all_endpoints": "true",
                "reason": "207 unrestricted key",
            },
            owner_id=owner_id,
        )
        unrestricted = asyncio_run(_latest_key(migrated_postgres_url, owner_id))
        assert unrestricted.metadata_json.get("allowed_providers") in (None, [])
        page = client.get(f"/admin/keys/{unrestricted.id}")
        assert "Unrestricted (all enabled providers)" in page.text

        # Explicit allow-list.
        _create_key(
            client,
            {
                "allowed_providers": "openai",
                "allow_all_models": "true",
                "allow_all_endpoints": "true",
                "reason": "207 allow-list key",
            },
            owner_id=owner_id,
        )
        allow_list = asyncio_run(_latest_key(migrated_postgres_url, owner_id))
        assert allow_list.metadata_json.get("allowed_providers") == ["openai"]
        page = client.get(f"/admin/keys/{allow_list.id}")
        assert "Allow-list: openai" in page.text

        # Explicit deny-all (stored []).
        _create_key(
            client,
            {
                "provider_deny_all": "true",
                "allow_all_models": "true",
                "allow_all_endpoints": "true",
                "reason": "207 deny-all key",
            },
            owner_id=owner_id,
        )
        deny_all = asyncio_run(_latest_key(migrated_postgres_url, owner_id))
        assert deny_all.metadata_json.get("allowed_providers") == []
        page = client.get(f"/admin/keys/{deny_all.id}")
        assert "Deny all providers" in page.text
        # Tri-state prefill round-trips on the detail page.
        assert 'name="provider_deny_all" value="true" checked' in page.text


def test_policy_update_empty_selection_fails_closed(migrated_postgres_url: str) -> None:
    data = _seed_sync(migrated_postgres_url)
    owner_id = data["owner_id"]
    app = create_app(_settings(migrated_postgres_url))
    with TestClient(app) as client:
        _login(client, data)
        _create_key(
            client,
            {
                "allow_all_providers": "true",
                "allow_all_models": "true",
                "allow_all_endpoints": "true",
                "reason": "207 fail-closed key",
            },
            owner_id=owner_id,
        )
        key = asyncio_run(_latest_key(migrated_postgres_url, owner_id))
        page = client.get(f"/admin/keys/{key.id}")
        csrf = _csrf_from_html(page.text)
        response = client.post(
            f"/admin/keys/{key.id}/policy",
            data={
                "csrf_token": csrf,
                "allow_all_models": "true",
                "allow_all_endpoints": "true",
                "reason": "legacy empty submission",
            },
        )
        assert response.status_code == 400
        assert "an empty selection never grants unrestricted access" in response.text
        refreshed = asyncio_run(_latest_key(migrated_postgres_url, owner_id))
        assert refreshed.updated_at == key.updated_at


def test_disabled_provider_round_trip_preserved(migrated_postgres_url: str) -> None:
    data = _seed_sync(migrated_postgres_url)
    owner_id = data["owner_id"]
    app = create_app(_settings(migrated_postgres_url))
    with TestClient(app) as client:
        _login(client, data)
        _create_key(
            client,
            {
                "allowed_providers": "openrouter",
                "allow_all_models": "true",
                "allow_all_endpoints": "true",
                "reason": "207 preservation key",
            },
            owner_id=owner_id,
        )
        key = asyncio_run(_latest_key(migrated_postgres_url, owner_id))
        assert key.metadata_json.get("allowed_providers") == ["openrouter"]

        # Disable the provider AFTER the key stores it.
        _set_provider_enabled(migrated_postgres_url, "openrouter", False)

        page = client.get(f"/admin/keys/{key.id}")
        csrf = _csrf_from_html(page.text)
        response = client.post(
            f"/admin/keys/{key.id}/policy",
            data={
                "csrf_token": csrf,
                "allowed_providers": "openrouter",
                "allow_all_models": "true",
                "allow_all_endpoints": "true",
                "reason": "round-trip stored provider",
            },
            follow_redirects=False,
        )
        assert response.status_code == 303
        refreshed = asyncio_run(_latest_key(migrated_postgres_url, owner_id))
        assert refreshed.metadata_json.get("allowed_providers") == ["openrouter"]

        # An UNRELATED unknown slug is still refused (no broadening).
        page = client.get(f"/admin/keys/{key.id}")
        csrf = _csrf_from_html(page.text)
        response = client.post(
            f"/admin/keys/{key.id}/policy",
            data={
                "csrf_token": csrf,
                "allowed_providers": "ghost-provider",
                "allow_all_models": "true",
                "allow_all_endpoints": "true",
                "reason": "try unknown slug",
            },
        )
        assert response.status_code == 400
        assert "A selected provider is not available" in response.text
        refreshed = asyncio_run(_latest_key(migrated_postgres_url, owner_id))
        assert refreshed.metadata_json.get("allowed_providers") == ["openrouter"]
        _set_provider_enabled(migrated_postgres_url, "openrouter", True)


# ---------------------------------------------------------------------------
# G02: rate editor
# ---------------------------------------------------------------------------


def test_rate_editor_persets_clears_and_isolates_state(migrated_postgres_url: str) -> None:
    data = _seed_sync(migrated_postgres_url)
    owner_id = data["owner_id"]
    admin_id = data["admin_id"]
    app = create_app(_settings(migrated_postgres_url))
    with TestClient(app) as client:
        _login(client, data)
        _create_key(
            client,
            {
                "allow_all_providers": "true",
                "allow_all_models": "true",
                "allow_all_endpoints": "true",
                "cost_limit_eur": "12.345678901",
                "token_limit_total": "9000",
                "request_limit_total": "300",
                "reason": "207 rate editor key",
            },
            owner_id=owner_id,
        )
        key = asyncio_run(_latest_key(migrated_postgres_url, owner_id))
        before = asyncio_run(_key_row_snapshot(migrated_postgres_url, key.id))

        page = client.get(f"/admin/keys/{key.id}")
        csrf = _csrf_from_html(page.text)
        # 1 request per 10 seconds + concurrency 1.
        response = client.post(
            f"/admin/keys/{key.id}/rate-limits",
            data={
                "csrf_token": csrf,
                "rate_action_requests_per_window": "set",
                "rate_value_requests_per_window": "1",
                "rate_action_window": "set",
                "rate_value_window": "10",
                "rate_action_concurrency": "set",
                "rate_value_concurrency": "1",
                "reason": "one request per ten seconds",
            },
            follow_redirects=False,
        )
        assert response.status_code == 303
        after_set = asyncio_run(_latest_key(migrated_postgres_url, owner_id))
        assert after_set.rate_limit_requests_per_minute == 1
        assert after_set.max_concurrent_requests == 1
        assert after_set.metadata_json["rate_limit_policy"]["window_seconds"] == 10
        assert after_set.rate_limit_tokens_per_minute is None

        # Everything else is untouched.
        preserved = asyncio_run(_key_row_snapshot(migrated_postgres_url, key.id))
        for field in before:
            if field not in {"updated_at"}:
                assert preserved[field] == before[field], field

        audit = asyncio_run(_last_audit(migrated_postgres_url, "update_key_rate_limits"))
        assert audit is not None
        assert audit.admin_user_id == admin_id
        assert "one request per ten seconds" in (audit.note or "")

        # Detail prefill shows the configured values.
        page = client.get(f"/admin/keys/{key.id}")
        csrf = _csrf_from_html(page.text)
        assert 'name="rate_value_requests_per_window" value="1"' in page.text
        assert 'name="rate_value_window" value="10"' in page.text
        assert 'name="rate_value_concurrency" value="1"' in page.text

        # Zero is refused with a fixed message; state unchanged.
        response = client.post(
            f"/admin/keys/{key.id}/rate-limits",
            data={
                "csrf_token": csrf,
                "rate_action_requests_per_window": "set",
                "rate_value_requests_per_window": "0",
                "reason": "try zero",
            },
        )
        assert response.status_code == 400
        assert "Requests per window must be a positive whole number." in response.text
        unchanged = asyncio_run(_latest_key(migrated_postgres_url, owner_id))
        assert unchanged.rate_limit_requests_per_minute == 1

        # No-op is refused.
        response = client.post(
            f"/admin/keys/{key.id}/rate-limits",
            data={"csrf_token": csrf, "reason": "no change"},
        )
        assert response.status_code == 400
        assert "No rate-limit change requested." in response.text

        # Clear concurrency: inherit the deployment.
        response = client.post(
            f"/admin/keys/{key.id}/rate-limits",
            data={
                "csrf_token": csrf,
                "rate_action_concurrency": "clear",
                "reason": "inherit deployment concurrency",
            },
            follow_redirects=False,
        )
        assert response.status_code == 303
        after_clear = asyncio_run(_latest_key(migrated_postgres_url, owner_id))
        assert after_clear.max_concurrent_requests is None
        assert after_clear.rate_limit_requests_per_minute == 1


# ---------------------------------------------------------------------------
# G01: advanced configuration export / partial update
# ---------------------------------------------------------------------------


def test_configuration_export_exact_and_partial_update_preserves_siblings(
    migrated_postgres_url: str,
) -> None:
    data = _seed_sync(migrated_postgres_url)
    owner_id = data["owner_id"]
    app = create_app(_settings(migrated_postgres_url))
    with TestClient(app) as client:
        _login(client, data)
        _create_key(
            client,
            {
                "allow_all_providers": "true",
                "allow_all_models": "true",
                "allow_all_endpoints": "true",
                "cost_limit_eur": "7.250000000",
                "rate_limit_requests_per_minute": "120",
                "rate_limit_window_seconds": "15",
                "lazy_throttling_mode": "wait",
                "lazy_throttling_max_wait_seconds": "45",
                "lazy_throttling_max_waiting_requests": "3",
                "reason": "207 configuration key",
            },
            owner_id=owner_id,
        )
        key = asyncio_run(_latest_key(migrated_postgres_url, owner_id))

        # Export: exact decimals, allowlisted fields, private attachment.
        response = client.get(f"/admin/keys/{key.id}/configuration.json")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("application/json")
        assert (
            response.headers["content-disposition"]
            == f'attachment; filename="slaif-key-configuration-{key.public_key_id}.json"'
        )
        assert "no-store" in response.headers.get("cache-control", "")
        document = json.loads(response.text)
        assert document["schema_version"] == 1
        assert document["cost_limit_eur"] == "7.250000000"
        assert document["rate_limit_policy"] == {
            "requests_per_minute": 120,
            "window_seconds": 15,
        }
        assert document["lazy_throttling_policy"]["mode"] == "wait"
        # No secret material in the document.
        body = response.text
        assert "token_hash" not in body
        assert "encrypted_payload" not in body
        assert "nonce" not in body
        assert key.token_hash not in body

        # Partial update: change ONLY the cost limit.
        page = client.get(f"/admin/keys/{key.id}")
        csrf = _csrf_from_html(page.text)
        update_doc = json.dumps({"schema_version": 1, "cost_limit_eur": "9.500000000"})
        response = client.post(
            f"/admin/keys/{key.id}/configuration",
            data={
                "csrf_token": csrf,
                "configuration_json": update_doc,
                "confirm_configuration_update": "true",
                "reason": "raise cost limit",
            },
            follow_redirects=False,
        )
        assert response.status_code == 303
        refreshed = asyncio_run(_latest_key(migrated_postgres_url, owner_id))
        assert refreshed.cost_limit_eur == Decimal("9.500000000")
        # Siblings preserved by the presence-aware law.
        assert refreshed.rate_limit_requests_per_minute == 120
        assert refreshed.metadata_json["rate_limit_policy"]["window_seconds"] == 15
        lazy_meta = refreshed.metadata_json.get("lazy_throttling_policy") or {}
        assert lazy_meta.get("mode") == "wait"
        assert lazy_meta.get("max_wait_seconds") == 45

        audit = asyncio_run(_last_audit(migrated_postgres_url, "update_key_configuration"))
        assert audit is not None
        assert audit.admin_user_id == data["admin_id"]

        # A rejected document never echoes: canary absent from the 400 page.
        page = client.get(f"/admin/keys/{key.id}")
        csrf = _csrf_from_html(page.text)
        response = client.post(
            f"/admin/keys/{key.id}/configuration",
            data={
                "csrf_token": csrf,
                "configuration_json": '{"schema_version": 1, "note": "' + CONFIG_CANARY + '"}',
                "confirm_configuration_update": "true",
                "reason": "unknown field",
            },
        )
        assert response.status_code == 400
        assert "Document contains unsupported fields." in response.text
        assert CONFIG_CANARY not in response.text


# ---------------------------------------------------------------------------
# G03: explain model access (shared projection, read-only)
# ---------------------------------------------------------------------------


def test_explain_route_read_only_and_configuration_only(migrated_postgres_url: str) -> None:
    data = _seed_sync(migrated_postgres_url)
    owner_id = data["owner_id"]
    app = create_app(_settings(migrated_postgres_url))
    with TestClient(app) as client:
        _login(client, data)
        _create_key(
            client,
            {
                "allowed_providers": "openai",
                "allowed_models": "gpt-test",
                "allowed_endpoints": "/v1/chat/completions",
                "reason": "207 explain key",
            },
            owner_id=owner_id,
        )
        key = asyncio_run(_latest_key(migrated_postgres_url, owner_id))
        audit_before = asyncio_run(_audit_count(migrated_postgres_url))
        snapshot_before = asyncio_run(_key_row_snapshot(migrated_postgres_url, key.id))

        page = client.get(f"/admin/keys/{key.id}")
        csrf = _csrf_from_html(page.text)
        # Allowed model on the allowed endpoint: resolved.
        response = client.post(
            f"/admin/keys/{key.id}/explain-route",
            data={
                "csrf_token": csrf,
                "endpoint": "/v1/chat/completions",
                "model": "gpt-test",
            },
        )
        assert response.status_code == 200
        assert "data-explain-report" in response.text
        assert "Configuration-only view" in response.text
        assert "resolved" in response.text
        assert "gpt-test" in response.text
        # The explain action re-renders the detail page with a refreshed CSRF.
        csrf = _csrf_from_html(response.text)

        # Disallowed model: blocked by the model allow-list.
        response = client.post(
            f"/admin/keys/{key.id}/explain-route",
            data={
                "csrf_token": csrf,
                "endpoint": "/v1/chat/completions",
                "model": "gpt-other",
            },
        )
        assert response.status_code == 200
        assert "blocked" in response.text
        csrf = _csrf_from_html(response.text)

        # Unknown endpoint: not evaluated, never invented.
        response = client.post(
            f"/admin/keys/{key.id}/explain-route",
            data={
                "csrf_token": csrf,
                "endpoint": "/v1/nonexistent",
                "model": "gpt-test",
            },
        )
        assert response.status_code == 200
        assert "not-evaluated" in response.text or "blocked" in response.text
        csrf = _csrf_from_html(response.text)

        # Read-only: no audit rows and no key-row changes.
        assert asyncio_run(_audit_count(migrated_postgres_url)) == audit_before
        snapshot_after = asyncio_run(_key_row_snapshot(migrated_postgres_url, key.id))
        assert snapshot_after == snapshot_before

        # Suspended key state is disclosed in the explanation.
        response = client.post(
            f"/admin/keys/{key.id}/suspend",
            data={"csrf_token": csrf, "reason": "207 suspend for explain"},
            follow_redirects=False,
        )
        assert response.status_code == 303
        page = client.get(f"/admin/keys/{key.id}")
        csrf = _csrf_from_html(page.text)
        response = client.post(
            f"/admin/keys/{key.id}/explain-route",
            data={
                "csrf_token": csrf,
                "endpoint": "/v1/chat/completions",
                "model": "gpt-test",
            },
        )
        assert response.status_code == 200
        assert "suspended" in response.text.lower()


def test_detail_inspection_matches_shared_cli_projection(migrated_postgres_url: str) -> None:
    data = _seed_sync(migrated_postgres_url)
    owner_id = data["owner_id"]
    settings = _settings(migrated_postgres_url)
    app = create_app(settings)
    with TestClient(app) as client:
        _login(client, data)
        _create_key(
            client,
            {
                "allowed_providers": "openai",
                "allow_all_models": "true",
                "allow_all_endpoints": "true",
                "rate_limit_requests_per_minute": "77",
                "reason": "207 inspection key",
            },
            owner_id=owner_id,
        )
        key = asyncio_run(_latest_key(migrated_postgres_url, owner_id))
        page = client.get(f"/admin/keys/{key.id}")
        assert page.status_code == 200
        assert "key-effective-policy-heading" in page.text

        # The SAME shared projection the CLI renders.
        engine = _engine(migrated_postgres_url)
        factory = async_sessionmaker(engine, expire_on_commit=False)

        async def _inspect():
            try:
                async with factory() as session:
                    row = await session.get(GatewayKey, key.id)
                    return build_key_policy_inspection(gateway_key=row, settings=settings)
            finally:
                await engine.dispose()

        inspection = asyncio_run(_inspect())

        assert inspection["allowlists"]["state"] == "allow-list"
        assert inspection["allowlists"]["allowed_providers"] == ["openai"]
        requests_member = inspection["rate_limits"]["requests_per_window"]
        assert requests_member["configured"] == 77
        assert requests_member["source"] == "key"

        # The rendered section carries the shared facts.
        assert "Allow-list: openai" in page.text
        assert "requests_per_window" in page.text
        assert "77" in page.text


# ---------------------------------------------------------------------------
# 207-b: non-rotating download auth, reason bounds, canary non-persistence
# ---------------------------------------------------------------------------


async def _key_count_for_owner(database_url: str, owner_id: uuid.UUID) -> int:
    engine = _engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            result = await session.execute(
                select(func.count())
                .select_from(GatewayKey)
                .where(GatewayKey.owner_id == owner_id)
            )
            return int(result.scalar_one())
    finally:
        await engine.dispose()


async def _any_audit_note_contains(database_url: str, needle: str) -> bool:
    engine = _engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            result = await session.execute(
                select(AuditLog.note).where(AuditLog.note.like(f"%{needle}%"))
            )
            return result.first() is not None
    finally:
        await engine.dispose()


async def _expire_admin_sessions(database_url: str, admin_id: uuid.UUID) -> None:
    engine = _engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            async with session.begin():
                result = await session.execute(
                    select(AdminSession).where(AdminSession.admin_user_id == admin_id)
                )
                for row in result.scalars().all():
                    row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    finally:
        await engine.dispose()


def test_configuration_download_does_not_rotate_same_page_csrf(
    migrated_postgres_url: str,
) -> None:
    """REAL CSRF service: page renders rotate the stored token, the
    read-only attachment must not, so the still-displayed form token
    completes the same-page edit; expired sessions are refused on the
    attachment too."""
    data = _seed_sync(migrated_postgres_url)
    owner_id = data["owner_id"]
    app = create_app(_settings(migrated_postgres_url))
    with TestClient(app) as client:
        _login(client, data)
        _create_key(
            client,
            {
                "allow_all_providers": "true",
                "allow_all_models": "true",
                "allow_all_endpoints": "true",
                "reason": "207-b download csrf key",
            },
            owner_id=owner_id,
        )
        key = asyncio_run(_latest_key(migrated_postgres_url, owner_id))

        detail = client.get(f"/admin/keys/{key.id}")
        assert detail.status_code == 200
        displayed_csrf = _csrf_from_html(detail.text)

        download = client.get(f"/admin/keys/{key.id}/configuration.json")
        assert download.status_code == 200
        assert download.headers["content-type"].startswith("application/json")
        assert "no-store" in download.headers.get("cache-control", "")
        assert download.headers["content-disposition"].startswith("attachment")
        document = json.loads(download.text)
        assert document["schema_version"] == 1
        # The attachment carries the canonical allowlisted projection:
        # unrestricted providers export as null.
        assert document["allowed_providers"] is None

        # Same-page edit with THAT SAME still-displayed token: a rotated
        # (or invalidated) token would 400 Invalid CSRF here.
        edited = client.post(
            f"/admin/keys/{key.id}/rate-limits",
            data={
                "csrf_token": displayed_csrf,
                "rate_action_requests_per_window": "set",
                "rate_value_requests_per_window": "5",
                "rate_action_window": "set",
                "rate_value_window": "30",
                "reason": "same-page edit after download",
            },
            follow_redirects=False,
        )
        assert edited.status_code == 303
        after = asyncio_run(_latest_key(migrated_postgres_url, owner_id))
        assert after.rate_limit_requests_per_minute == 5
        assert after.metadata_json["rate_limit_policy"]["window_seconds"] == 30
        assert after.rate_limit_tokens_per_minute is None
        audit = asyncio_run(_last_audit(migrated_postgres_url, "update_key_rate_limits"))
        assert audit is not None
        assert audit.note == "same-page edit after download"

        # The real CSRF service still rotates on page renders: the token
        # displayed BEFORE this fresh render is now refused, proving the
        # success above came from non-rotation, not an always-accept
        # token check.
        client.get(f"/admin/keys/{key.id}")
        stale = client.post(
            f"/admin/keys/{key.id}/rate-limits",
            data={
                "csrf_token": displayed_csrf,
                "rate_action_requests_per_window": "set",
                "rate_value_requests_per_window": "6",
                "reason": "stale token control",
            },
        )
        assert stale.status_code == 400
        assert "Invalid CSRF token." in stale.text
        unchanged = asyncio_run(_latest_key(migrated_postgres_url, owner_id))
        assert unchanged.rate_limit_requests_per_minute == 5

        # Expired session: same refused-redirect law on the attachment.
        asyncio_run(_expire_admin_sessions(migrated_postgres_url, data["admin_id"]))
        expired = client.get(
            f"/admin/keys/{key.id}/configuration.json", follow_redirects=False
        )
        assert expired.status_code == 303
        assert expired.headers["location"] == "/admin/login"


def test_rate_reason_bounds_512_valid_513_refused_no_mutation(
    migrated_postgres_url: str,
) -> None:
    data = _seed_sync(migrated_postgres_url)
    owner_id = data["owner_id"]
    app = create_app(_settings(migrated_postgres_url))
    with TestClient(app) as client:
        _login(client, data)
        _create_key(
            client,
            {
                "allow_all_providers": "true",
                "allow_all_models": "true",
                "allow_all_endpoints": "true",
                "reason": "207-b reason bounds key",
            },
            owner_id=owner_id,
        )
        key = asyncio_run(_latest_key(migrated_postgres_url, owner_id))
        page = client.get(f"/admin/keys/{key.id}")
        csrf = _csrf_from_html(page.text)
        # The seed/owner is shared across this module, so prior
        # rate-edit audits exist: the refusal is proven by the audit
        # baseline, not by a global "no such audit ever" claim.
        audits_before = asyncio_run(_audit_count(migrated_postgres_url))

        reason_513 = "b" * 513
        too_long = client.post(
            f"/admin/keys/{key.id}/rate-limits",
            data={
                "csrf_token": csrf,
                "rate_action_requests_per_window": "set",
                "rate_value_requests_per_window": "42",
                "reason": reason_513,
            },
        )
        assert too_long.status_code == 400
        assert "Audit reason is too long." in too_long.text
        unchanged = asyncio_run(_latest_key(migrated_postgres_url, owner_id))
        assert unchanged.rate_limit_requests_per_minute is None
        assert asyncio_run(_audit_count(migrated_postgres_url)) == audits_before

        reason_512 = "b" * 512
        ok = client.post(
            f"/admin/keys/{key.id}/rate-limits",
            data={
                "csrf_token": csrf,
                "rate_action_requests_per_window": "set",
                "rate_value_requests_per_window": "42",
                "reason": reason_512,
            },
            follow_redirects=False,
        )
        assert ok.status_code == 303
        after = asyncio_run(_latest_key(migrated_postgres_url, owner_id))
        assert after.rate_limit_requests_per_minute == 42
        audit = asyncio_run(_last_audit(migrated_postgres_url, "update_key_rate_limits"))
        assert audit is not None
        assert audit.note == reason_512
        assert len(audit.note) == 512


def test_create_document_canary_model_refused_without_persistence(
    migrated_postgres_url: str,
) -> None:
    """The demonstrated (a) case end-to-end: a schema-valid document whose
    allowed_models carries a recognized credential shape is refused before
    the shared validators and the service; nothing persists, no audit note
    carries the canary, and the 400 HTML echoes nothing."""
    data = _seed_sync(migrated_postgres_url)
    owner_id = data["owner_id"]
    app = create_app(_settings(migrated_postgres_url))
    with TestClient(app) as client:
        _login(client, data)
        create_page = client.get("/admin/keys/create")
        csrf = _csrf_from_html(create_page.text)
        keys_before = asyncio_run(_key_count_for_owner(migrated_postgres_url, owner_id))
        audits_before = asyncio_run(_audit_count(migrated_postgres_url))

        document = json.dumps(
            {
                "schema_version": 1,
                "allowed_models": [CONFIG_CANARY],
                "allow_all_endpoints": True,
                "allowed_providers": ["openai"],
            }
        )
        response = client.post(
            "/admin/keys/create",
            data={
                "csrf_token": csrf,
                "owner_id": str(owner_id),
                "valid_days": "30",
                "email_delivery_mode": "none",
                "reason": "207-b canary model refusal",
                "policy_source": "configuration",
                "configuration_json": document,
            },
            follow_redirects=False,
        )
        assert response.status_code == 400
        assert "Allowed models must be route model identifiers" in response.text
        assert CONFIG_CANARY not in response.text

        assert (
            asyncio_run(_key_count_for_owner(migrated_postgres_url, owner_id))
            == keys_before
        )
        assert asyncio_run(_audit_count(migrated_postgres_url)) == audits_before
        assert (
            asyncio_run(_any_audit_note_contains(migrated_postgres_url, CONFIG_CANARY))
            is False
        )
