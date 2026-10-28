"""Owned-PostgreSQL evidence for the typed CLI key-policy configuration (196-a).

Real owned PostgreSQL 16 (unique, labeled, loopback-bound, tmpfs container
created and removed by the imported ``owned_pg_url`` fixture) plus the real
installed Typer entry path. Proves:

- file-only create with providers + rate + Responses policy;
- safe export with explicit nulls;
- provider-only updates that preserve models/endpoints/responses/quota/usage;
- distinct persisted ``None`` (unrestricted) vs ``[]`` (deny-all) providers;
- the stored provider policy reaching the REAL auth + model-catalog
  consumer over owned rows (no provider HTTP);
- forced LATE audit failures (after the write phase flushed) rolling back
  the whole caller-owned transaction for both create and update;
- the migration law failing atomically on a bound key (no state, no audit);
- bulk-import provider parity through real execution.

No real provider inference, no real email, no ambient DATABASE_URL. The
configured gateway key prefix is deliberately custom, so key parsing and
auth expectations are derived from Settings, not the production default.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from typer.testing import CliRunner

from slaif_gateway.cli.main import app
from slaif_gateway.config import get_settings
from slaif_gateway.db.models import AuditLog, EmailDelivery, GatewayKey, OneTimeSecret
from slaif_gateway.db.repositories.cohorts import CohortsRepository
from slaif_gateway.db.repositories.institutions import InstitutionsRepository
from slaif_gateway.db.repositories.owners import OwnersRepository
from slaif_gateway.db.repositories.routing import ModelRoutesRepository
from slaif_gateway.db.session import get_sessionmaker
from slaif_gateway.modules.clients.codex_0149 import CODEX_0149_CLIENT_MODULE_ID
from slaif_gateway.modules.clients.codex_0162 import CODEX_0162_CLIENT_MODULE_ID
from slaif_gateway.modules.clients.registry import client_module_metadata, get_client_module
from slaif_gateway.services.key_import import (
    KeyImportOwnerRef,
    KeyImportReadOnlyContext,
    build_key_import_execution_plan,
    execute_key_import_plan,
    validate_key_import_rows,
)
from slaif_gateway.utils.secrets import generate_secret_key

# Fixture re-export: the owned PostgreSQL 16 container is created and
# removed by the imported qualified fixture (exact created ID only).
from tests.integration.test_lazy_throttling_postgres_redis import (  # noqa: F401,F811
    owned_pg_url,
)

TEST_HMAC_SECRET = "test-hmac-secret-for-cli-key-policy-integration-196"
TEST_ADMIN_SECRET = "test-admin-secret-for-cli-key-policy-integration-196"
# Deliberately distinct from the production default: key parsing/display and
# the real auth consumer must derive expectations from configured Settings.
TEST_GATEWAY_KEY_PREFIX = "sk-slaif196test-"

PIN_0162 = client_module_metadata(get_client_module(CODEX_0162_CLIENT_MODULE_ID))
PIN_0149 = client_module_metadata(get_client_module(CODEX_0149_CLIENT_MODULE_ID))


@dataclass(frozen=True)
class Context:
    owner_id: uuid.UUID
    cohort_id: uuid.UUID


@pytest.fixture
def env_for_owned_pg(
    monkeypatch: pytest.MonkeyPatch, owned_pg_url: str,  # noqa: F811
) -> str:
    monkeypatch.setenv("DATABASE_URL", owned_pg_url)
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.delenv("CODEX_COMPATIBILITY_PROFILE_FILE", raising=False)
    monkeypatch.setenv("GATEWAY_KEY_PREFIX", TEST_GATEWAY_KEY_PREFIX)
    monkeypatch.setenv("GATEWAY_KEY_ACCEPTED_PREFIXES", TEST_GATEWAY_KEY_PREFIX)
    monkeypatch.setenv("ACTIVE_HMAC_KEY_VERSION", "1")
    monkeypatch.setenv("TOKEN_HMAC_SECRET_V1", TEST_HMAC_SECRET)
    monkeypatch.setenv("ADMIN_SESSION_SECRET", TEST_ADMIN_SECRET)
    monkeypatch.setenv("ONE_TIME_SECRET_ENCRYPTION_KEY", generate_secret_key())
    monkeypatch.setenv("ENABLE_EMAIL_DELIVERY", "false")
    get_settings.cache_clear()
    return owned_pg_url


def _run(coro):
    import asyncio

    return asyncio.run(coro)


def _session_factory(database_url: str):
    engine = create_async_engine(database_url, future=True)
    return engine, async_sessionmaker(engine, expire_on_commit=False)


def _unique_label(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex}"


async def _create_context(database_url: str, *, with_responses_route: bool) -> Context:
    engine, session_factory = _session_factory(database_url)
    unique = _unique_label("slaif196")
    now = datetime.now(UTC)
    try:
        async with session_factory() as session:
            institutions = InstitutionsRepository(session)
            cohorts = CohortsRepository(session)
            owners = OwnersRepository(session)
            routes = ModelRoutesRepository(session)
            institution = await institutions.create_institution(
                name=f"SLAIF 196 {unique}",
                country="SI",
                notes="typed key-policy integration owner",
            )
            cohort = await cohorts.create_cohort(
                name=unique,
                description="typed key-policy integration cohort",
                starts_at=now - timedelta(days=1),
                ends_at=now + timedelta(days=30),
            )
            owner = await owners.create_owner(
                name="Policy",
                surname="Integration",
                email=f"{unique}@example.org",
                institution_id=institution.id,
                notes="typed key-policy integration owner",
            )
            await routes.create_model_route(
                requested_model="gpt-test-mini",
                provider="openai",
                upstream_model="gpt-test-mini",
                endpoint="/v1/chat/completions",
            )
            if with_responses_route:
                await routes.create_model_route(
                    requested_model="gpt-test-mini",
                    provider="openai",
                    upstream_model="gpt-test-mini",
                    endpoint="/v1/responses",
                )
            await session.commit()
            return Context(owner_id=owner.id, cohort_id=cohort.id)
    finally:
        await engine.dispose()


async def _fetch_key_row(database_url: str, gateway_key_id: uuid.UUID) -> GatewayKey:
    engine, session_factory = _session_factory(database_url)
    try:
        async with session_factory() as session:
            row = await session.get(GatewayKey, gateway_key_id)
            assert row is not None
            return row
    finally:
        await engine.dispose()


async def _audit_count(
    database_url: str, gateway_key_id: uuid.UUID, action: str
) -> int:
    engine, session_factory = _session_factory(database_url)
    try:
        async with session_factory() as session:
            result = await session.execute(
                select(AuditLog).where(
                    AuditLog.entity_type == "gateway_key",
                    AuditLog.entity_id == gateway_key_id,
                    AuditLog.action == action,
                )
            )
            return len(result.scalars().all())
    finally:
        await engine.dispose()


async def _key_count(database_url: str, owner_id: uuid.UUID) -> int:
    engine, session_factory = _session_factory(database_url)
    try:
        async with session_factory() as session:
            result = await session.execute(
                select(GatewayKey).where(GatewayKey.owner_id == owner_id)
            )
            return len(result.scalars().all())
    finally:
        await engine.dispose()


def _policy_file(tmp_path, document: dict[str, object], name: str = "policy.json") -> str:
    path = tmp_path / name
    path.write_text(json.dumps(document))
    return str(path)


runner = CliRunner()


def test_file_only_create_export_and_preserving_update(
    tmp_path, env_for_owned_pg: str
) -> None:
    context = _run(_create_context(env_for_owned_pg, with_responses_route=False))
    policy = _policy_file(
        tmp_path,
        {
            "schema_version": 1,
            "allowed_models": ["gpt-test-mini"],
            "allowed_endpoints": ["/v1/chat/completions"],
            "allowed_providers": ["openai", "openrouter"],
            "cost_limit_eur": "99999999.123456789",
            "rate_limit_policy": {"requests_per_minute": 11, "window_seconds": 33},
        },
    )
    result = runner.invoke(
        app,
        [
            "keys",
            "create",
            "--owner-id",
            str(context.owner_id),
            "--cohort-id",
            str(context.cohort_id),
            "--valid-days",
            "30",
            "--policy-file",
            policy,
            "--reason",
            "196 file create",
            "--show-plaintext",
        ],
    )
    assert result.exit_code == 0, result.output
    gateway_key_id = uuid.UUID(
        json.loads(result.output)["gateway_key_id"]
        if "--json" in result.output
        else _kv_value(result.output, "gateway_key_id")
    )

    row = _run(_fetch_key_row(env_for_owned_pg, gateway_key_id))
    assert row.metadata_json.get("allowed_providers") == ["openai", "openrouter"]
    assert row.allowed_models == ["gpt-test-mini"]
    assert row.allowed_endpoints == ["/v1/chat/completions"]
    assert row.cost_limit_eur is not None and str(row.cost_limit_eur).startswith("99999999.123456789")
    assert row.rate_limit_requests_per_minute == 11
    token_hash_before = row.token_hash
    usage_before = (row.cost_used_eur, row.tokens_used_total, row.requests_used_total)
    validity_before = (row.valid_from, row.valid_until)

    # Safe export: explicit nulls for absent groups, exact values otherwise.
    export_result = runner.invoke(app, ["keys", "policy", "export", str(gateway_key_id)])
    assert export_result.exit_code == 0, export_result.output
    document = json.loads(export_result.output)
    assert document["schema_version"] == 1
    assert document["allowed_providers"] == ["openai", "openrouter"]
    assert document["responses_policy"] is None
    assert document["lazy_throttling_policy"] is None
    assert "confirm_external_tool_fenced" not in document
    assert document["rate_limit_policy"]["requests_per_minute"] == 11
    assert document["rate_limit_policy"]["window_seconds"] == 33
    assert str(document["cost_limit_eur"]) == "99999999.123456789"

    # Provider-only update: everything else is preserved.
    update_result = runner.invoke(
        app,
        [
            "keys",
            "policy",
            "update",
            str(gateway_key_id),
            "--provider-none",
            "--reason",
            "196 deny all providers",
        ],
    )
    assert update_result.exit_code == 0, update_result.output
    row = _run(_fetch_key_row(env_for_owned_pg, gateway_key_id))
    assert row.metadata_json.get("allowed_providers") == []
    assert row.allowed_models == ["gpt-test-mini"]
    assert row.allowed_endpoints == ["/v1/chat/completions"]
    assert row.rate_limit_requests_per_minute == 11
    assert row.cost_limit_eur is not None
    assert str(row.cost_limit_eur).startswith("99999999.123456789")
    assert (row.cost_used_eur, row.tokens_used_total, row.requests_used_total) == usage_before
    assert (row.valid_from, row.valid_until) == validity_before
    assert row.token_hash == token_hash_before
    assert _run(_audit_count(env_for_owned_pg, gateway_key_id, "update_key_configuration")) == 1

    # Explicit provider-all: the stored allow-list is removed (unrestricted).
    all_result = runner.invoke(
        app,
        [
            "keys",
            "policy",
            "update",
            str(gateway_key_id),
            "--provider-all",
            "--reason",
            "196 unrestricted providers",
        ],
    )
    assert all_result.exit_code == 0, all_result.output
    row = _run(_fetch_key_row(env_for_owned_pg, gateway_key_id))
    assert "allowed_providers" not in row.metadata_json
    assert _run(_audit_count(env_for_owned_pg, gateway_key_id, "update_key_configuration")) == 2


def _kv_value(output: str, key: str) -> str:
    for line in output.splitlines():
        if line.startswith(f"{key}: "):
            return line.split(": ", 1)[1]
    raise AssertionError(f"{key} not found in CLI output")


def test_none_vs_empty_providers_persist_distinctly(tmp_path, env_for_owned_pg: str) -> None:
    context = _run(_create_context(env_for_owned_pg, with_responses_route=False))
    base = [
        "keys",
        "create",
        "--owner-id",
        str(context.owner_id),
        "--cohort-id",
        str(context.cohort_id),
        "--valid-days",
        "30",
        "--allowed-model",
        "gpt-test-mini",
        "--allowed-endpoint",
        "/v1/chat/completions",
        "--reason",
        "196 provider semantics",
        "--show-plaintext",
    ]
    # Omitted providers: unrestricted (absent from stored metadata).
    result_unrestricted = runner.invoke(app, base)
    assert result_unrestricted.exit_code == 0, result_unrestricted.output
    id_unrestricted = uuid.UUID(_kv_value(result_unrestricted.output, "gateway_key_id"))
    row_unrestricted = _run(_fetch_key_row(env_for_owned_pg, id_unrestricted))
    assert "allowed_providers" not in row_unrestricted.metadata_json

    # Explicit deny-all: persisted as an empty list, never collapsed to None.
    result_deny = runner.invoke(app, base + ["--provider-none"])
    assert result_deny.exit_code == 0, result_deny.output
    id_deny = uuid.UUID(_kv_value(result_deny.output, "gateway_key_id"))
    row_deny = _run(_fetch_key_row(env_for_owned_pg, id_deny))
    assert row_deny.metadata_json.get("allowed_providers") == []


def test_bound_key_repin_fails_atomically_in_pg(tmp_path, env_for_owned_pg: str) -> None:
    context = _run(_create_context(env_for_owned_pg, with_responses_route=True))
    policy = _policy_file(
        tmp_path,
        {
            "schema_version": 1,
            "allowed_models": ["gpt-test-mini"],
            "allowed_endpoints": ["/v1/responses"],
            "allowed_providers": [],
            "responses_policy": {
                "version": 1,
                "allowed_capabilities": ["codex_request_envelope"],
                "client_module": dict(PIN_0162),
            },
        },
    )
    result = runner.invoke(
        app,
        [
            "keys",
            "create",
            "--owner-id",
            str(context.owner_id),
            "--cohort-id",
            str(context.cohort_id),
            "--valid-days",
            "30",
            "--policy-file",
            policy,
            "--reason",
            "196 codex pin create",
            "--show-plaintext",
        ],
    )
    assert result.exit_code == 0, result.output
    gateway_key_id = uuid.UUID(_kv_value(result.output, "gateway_key_id"))
    row = _run(_fetch_key_row(env_for_owned_pg, gateway_key_id))
    assert row.metadata_json["responses_policy"]["client_module"] == PIN_0162

    keys_before = _run(_key_count(env_for_owned_pg, context.owner_id))
    repin_policy = _policy_file(
        tmp_path,
        {
            "schema_version": 1,
            "responses_policy": {
                "version": 1,
                "allowed_capabilities": ["codex_request_envelope"],
                "client_module": dict(PIN_0149),
            },
        },
        name="repin.json",
    )
    repin = runner.invoke(
        app,
        [
            "keys",
            "policy",
            "update",
            str(gateway_key_id),
            "--policy-file",
            repin_policy,
            "--reason",
            "196 repin attempt",
        ],
    )
    assert repin.exit_code != 0
    assert "client-module migration" in repin.output
    row = _run(_fetch_key_row(env_for_owned_pg, gateway_key_id))
    assert row.metadata_json["responses_policy"]["client_module"] == PIN_0162
    assert _run(_audit_count(env_for_owned_pg, gateway_key_id, "update_key_configuration")) == 0
    assert _run(_key_count(env_for_owned_pg, context.owner_id)) == keys_before


def test_bulk_import_provider_parity_executes(tmp_path, env_for_owned_pg: str) -> None:
    context = _run(_create_context(env_for_owned_pg, with_responses_route=False))

    async def load_owner_and_admin() -> tuple[KeyImportOwnerRef, str, uuid.UUID]:
        engine, session_factory = _session_factory(env_for_owned_pg)
        try:
            async with session_factory() as session:
                from sqlalchemy import select as _select

                from slaif_gateway.db.models import Institution, Owner
                from slaif_gateway.db.repositories.admin_users import AdminUsersRepository
                from slaif_gateway.utils.passwords import hash_admin_password

                owner_row = await session.execute(
                    _select(Owner).where(Owner.id == context.owner_id)
                )
                owner = owner_row.scalar_one()
                institution = await session.get(Institution, owner.institution_id)
                ref = KeyImportOwnerRef(
                    id=owner.id,
                    email=owner.email,
                    display_name=f"{owner.name} {owner.surname}",
                    institution_id=owner.institution_id,
                    institution_name=institution.name if institution else None,
                )
                admin = await AdminUsersRepository(session).create_admin_user(
                    email=f"admin-196-{uuid.uuid4().hex}@example.org",
                    display_name="SLAIF 196 Integration Admin",
                    password_hash=hash_admin_password("correct horse battery staple"),
                    role="admin",
                )
                await session.commit()
                return ref, owner.email, admin.id
        finally:
            await engine.dispose()

    owner_ref, owner_email, admin_id = _run(load_owner_and_admin())
    now = datetime.now(UTC)
    base_row = {
        "owner_email": owner_email,
        "valid_days": "30",
        "allowed_models": "gpt-test-mini",
        "allowed_endpoints": "/v1/chat/completions",
        "email_delivery_mode": "none",
    }
    rows = [
        dict(base_row),  # omitted providers -> unrestricted
        dict(base_row, allowed_providers="openai"),  # explicit list
        dict(base_row, allowed_providers="[]"),  # explicit deny-all
        dict(base_row, allow_all_providers="true"),  # explicit unrestricted
    ]
    context_obj = KeyImportReadOnlyContext(
        owners_by_id={owner_ref.id: owner_ref},
        owners_by_email={owner_ref.email: owner_ref},
        cohorts_by_id={},
    )
    preview = validate_key_import_rows(rows, context=context_obj, max_rows=10, now=now)
    assert preview.invalid_count == 0, [r.errors for r in preview.rows]
    assert preview.rows[0].allowed_providers is None
    assert preview.rows[1].allowed_providers == ("openai",)
    assert preview.rows[2].allowed_providers == ()
    assert preview.rows[3].allowed_providers is None

    plan = build_key_import_execution_plan(
        preview,
        actor_admin_id=admin_id,
        reason="196 bulk import provider parity",
        confirm_import=True,
        confirm_plaintext_display=True,
    )

    async def execute() -> list[uuid.UUID]:
        settings = get_settings()
        session_factory = get_sessionmaker(settings)
        from slaif_gateway.db.repositories.audit import AuditRepository
        from slaif_gateway.db.repositories.keys import GatewayKeysRepository
        from slaif_gateway.db.repositories.one_time_secrets import OneTimeSecretsRepository
        from slaif_gateway.db.repositories.routing import ModelRoutesRepository as _MR
        from slaif_gateway.services.key_service import KeyService

        async with session_factory() as session:
            async with session.begin():
                service = KeyService(
                    settings=settings,
                    gateway_keys_repository=GatewayKeysRepository(session),
                    one_time_secrets_repository=OneTimeSecretsRepository(session),
                    audit_repository=AuditRepository(session),
                    model_routes_repository=_MR(session),
                )
                result = await execute_key_import_plan(
                    plan, key_service=service, email_delivery_service=None
                )
                return [row.gateway_key_id for row in result.rows]

    created_ids = _run(execute())
    assert len(created_ids) == 4
    rows_db = [_run(_fetch_key_row(env_for_owned_pg, key_id)) for key_id in created_ids]
    # Distinct persisted provider states, never collapsed.
    assert "allowed_providers" not in rows_db[0].metadata_json
    assert rows_db[1].metadata_json.get("allowed_providers") == ["openai"]
    assert rows_db[2].metadata_json.get("allowed_providers") == []
    assert "allowed_providers" not in rows_db[3].metadata_json


def test_bulk_import_rejects_external_tool_metadata_columns(env_for_owned_pg: str) -> None:
    context = _run(_create_context(env_for_owned_pg, with_responses_route=False))

    async def load_owner_email() -> tuple[KeyImportOwnerRef, str]:
        engine, session_factory = _session_factory(env_for_owned_pg)
        try:
            async with session_factory() as session:
                from sqlalchemy import select as _select

                from slaif_gateway.db.models import Owner

                owner_row = await session.execute(
                    _select(Owner).where(Owner.id == context.owner_id)
                )
                owner = owner_row.scalar_one()
                ref = KeyImportOwnerRef(
                    id=owner.id,
                    email=owner.email,
                    display_name=f"{owner.name} {owner.surname}",
                )
                return ref, owner.email
        finally:
            await engine.dispose()

    owner_ref, owner_email = _run(load_owner_email())
    context_obj = KeyImportReadOnlyContext(
        owners_by_id={owner_ref.id: owner_ref},
        owners_by_email={owner_ref.email: owner_ref},
        cohorts_by_id={},
    )
    row = {
        "owner_email": owner_email,
        "valid_days": "30",
        "allowed_models": "gpt-test-mini",
        "allowed_endpoints": "/v1/chat/completions",
        "email_delivery_mode": "none",
        "metadata": json.dumps({"external_tool_policy": {"mode": "external_tool_fenced"}}),
    }
    preview = validate_key_import_rows([row], context=context_obj, max_rows=10, now=datetime.now(UTC))
    assert preview.invalid_count == 1
    assert preview.rows[0].status == "invalid"


# --------------------------------------------------------------------------
# Stored provider policy reaches the REAL auth + model-catalog consumer
# --------------------------------------------------------------------------


async def _create_provider_config(database_url: str) -> None:
    engine, session_factory = _session_factory(database_url)
    try:
        async with session_factory() as session:
            from slaif_gateway.db.repositories.provider_configs import (
                ProviderConfigsRepository,
            )

            await ProviderConfigsRepository(session).create_provider_config(
                provider="openai",
                display_name="OpenAI Integration Test",
                base_url="https://provider.test.invalid/v1",
                api_key_env_var="OPENAI_UPSTREAM_API_KEY",
            )
            await session.commit()
    finally:
        await engine.dispose()


def test_stored_provider_policy_reaches_real_auth_consumer(
    tmp_path, env_for_owned_pg: str
) -> None:
    """Stored ``None`` vs ``[]`` providers reach the actual consumers.

    Both keys are created through the real CLI with a test-owned
    --secret-output-file channel. The one-time key material is only read
    back from that file (never printed or committed), authenticated with
    the real GatewayAuthService against the owned rows, and consumed by
    the real ModelCatalogService. No provider HTTP, no inference.
    """
    context = _run(_create_context(env_for_owned_pg, with_responses_route=False))
    _run(_create_provider_config(env_for_owned_pg))

    base = [
        "keys",
        "create",
        "--owner-id",
        str(context.owner_id),
        "--cohort-id",
        str(context.cohort_id),
        "--valid-days",
        "30",
        "--allowed-model",
        "gpt-test-mini",
        "--allowed-endpoint",
        "/v1/chat/completions",
        "--reason",
        "196 provider consumer proof",
    ]
    secret_unrestricted = tmp_path / "secret-unrestricted.txt"
    secret_deny = tmp_path / "secret-deny-all.txt"
    result_unrestricted = runner.invoke(
        app, base + ["--secret-output-file", str(secret_unrestricted)]
    )
    assert result_unrestricted.exit_code == 0, result_unrestricted.output
    result_deny = runner.invoke(
        app, base + ["--provider-none", "--secret-output-file", str(secret_deny)]
    )
    assert result_deny.exit_code == 0, result_deny.output

    # Key material is read only from the test-owned files; the prefix is
    # derived from the configured Settings (custom test prefix).
    settings = get_settings()
    token_unrestricted = secret_unrestricted.read_text().strip()
    token_deny = secret_deny.read_text().strip()
    for token in (token_unrestricted, token_deny):
        assert token.startswith(settings.GATEWAY_KEY_PREFIX)

    async def consume(token: str) -> tuple[tuple[str, ...] | None, list[str]]:
        engine, session_factory = _session_factory(env_for_owned_pg)
        try:
            async with session_factory() as session:
                from slaif_gateway.db.repositories.keys import GatewayKeysRepository
                from slaif_gateway.db.repositories.provider_configs import (
                    ProviderConfigsRepository,
                )
                from slaif_gateway.db.repositories.routing import ModelRoutesRepository
                from slaif_gateway.services.auth_service import GatewayAuthService
                from slaif_gateway.services.model_catalog import ModelCatalogService

                auth_service = GatewayAuthService(
                    settings=settings,
                    gateway_keys_repository=GatewayKeysRepository(session),
                )
                authenticated = await auth_service.authenticate_authorization_header(
                    f"Bearer {token}"
                )
                catalog = ModelCatalogService(
                    model_routes_repository=ModelRoutesRepository(session),
                    provider_configs_repository=ProviderConfigsRepository(session),
                )
                models = [
                    model.id
                    for model in await catalog.list_visible_models(authenticated)
                ]
                return authenticated.allowed_providers, models
        finally:
            await engine.dispose()

    providers_unrestricted, models_unrestricted = _run(consume(token_unrestricted))
    assert providers_unrestricted is None
    assert models_unrestricted == ["gpt-test-mini"]

    providers_deny, models_deny = _run(consume(token_deny))
    assert providers_deny == ()
    assert models_deny == []


# --------------------------------------------------------------------------
# Forced LATE audit failure: the caller-owned transaction rolls back
# --------------------------------------------------------------------------


def _install_late_audit_failure(
    monkeypatch: pytest.MonkeyPatch,
    fail_actions: frozenset[str],
    observe: object = None,
) -> list[dict[str, object]]:
    """Fail ONLY the terminal audit call of the named configuration action.

    Repository write-phase calls (limits/request-policy/rate/metadata
    updates) run and flush first; only the final ``add_audit_log`` call
    raises, so the CLI's caller-owned ``session.begin()`` transaction must
    roll the entire operation back. The transaction manager itself is
    never patched, and no state is manually restored in assertions.

    The optional async ``observe(session, record)`` callable runs INSIDE
    the same open transaction immediately BEFORE the raise, so the test
    can record that the write phase was actually visible (and correct) at
    the moment of failure. Every forced invocation is recorded and the
    record list is returned.
    """
    from slaif_gateway.db.repositories.audit import AuditRepository

    original_audit = AuditRepository.add_audit_log
    records: list[dict[str, object]] = []

    async def failing_audit(self, *, action: str, **kwargs):  # type: ignore[no-untyped-def]
        if action in fail_actions:
            record: dict[str, object] = {"action": action}
            if observe is not None:
                await observe(self._session, record)  # type: ignore[misc]
            records.append(record)
            raise RuntimeError("FORCED_LATE_AUDIT_FAILURE_196")
        return await original_audit(self, action=action, **kwargs)

    monkeypatch.setattr(AuditRepository, "add_audit_log", failing_audit)
    return records


async def _count_for_owner(database_url: str, model: type, owner_id: uuid.UUID) -> int:
    engine, session_factory = _session_factory(database_url)
    try:
        async with session_factory() as session:
            result = await session.execute(select(model).where(model.owner_id == owner_id))
            return len(result.scalars().all())
    finally:
        await engine.dispose()


async def _total_audit_count(database_url: str) -> int:
    engine, session_factory = _session_factory(database_url)
    try:
        async with session_factory() as session:
            result = await session.execute(select(AuditLog))
            return len(result.scalars().all())
    finally:
        await engine.dispose()


def _snapshot_key_row(row: GatewayKey) -> dict[str, object]:
    return {
        "public_key_id": row.public_key_id,
        "token_hash": row.token_hash,
        "hmac_key_version": row.hmac_key_version,
        "status": row.status,
        "valid_from": row.valid_from,
        "valid_until": row.valid_until,
        "cost_limit_eur": row.cost_limit_eur,
        "token_limit_total": row.token_limit_total,
        "request_limit_total": row.request_limit_total,
        "allowed_models": row.allowed_models,
        "allowed_endpoints": row.allowed_endpoints,
        "allow_all_models": row.allow_all_models,
        "allow_all_endpoints": row.allow_all_endpoints,
        "rate_limit_requests_per_minute": row.rate_limit_requests_per_minute,
        "rate_limit_tokens_per_minute": row.rate_limit_tokens_per_minute,
        "max_concurrent_requests": row.max_concurrent_requests,
        "cost_used_eur": row.cost_used_eur,
        "tokens_used_total": row.tokens_used_total,
        "requests_used_total": row.requests_used_total,
        "cost_reserved_eur": row.cost_reserved_eur,
        "tokens_reserved_total": row.tokens_reserved_total,
        "requests_reserved_total": row.requests_reserved_total,
        "metadata_json": row.metadata_json,
        "quota_reset_count": row.quota_reset_count,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def test_forced_late_create_audit_failure_rolls_back_creation(
    tmp_path, env_for_owned_pg: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failed terminal create audit persists no key/secret/audit at all."""
    context = _run(_create_context(env_for_owned_pg, with_responses_route=False))
    policy = _policy_file(
        tmp_path,
        {
            "schema_version": 1,
            "allowed_models": ["gpt-test-mini"],
            "allowed_endpoints": ["/v1/chat/completions"],
            "allowed_providers": ["openai"],
        },
    )

    async def observe_create(session, record: dict[str, object]) -> None:
        key_rows = (
            (
                await session.execute(
                    select(GatewayKey).where(GatewayKey.owner_id == context.owner_id)
                )
            )
            .scalars()
            .all()
        )
        secret_rows = (
            (
                await session.execute(
                    select(OneTimeSecret).where(OneTimeSecret.owner_id == context.owner_id)
                )
            )
            .scalars()
            .all()
        )
        record["same_txn_key_rows"] = len(key_rows)
        record["same_txn_secret_rows"] = len(secret_rows)
        record["same_txn_providers"] = (
            (key_rows[0].metadata_json or {}).get("allowed_providers")
            if key_rows
            else None
        )

    create_records = _install_late_audit_failure(
        monkeypatch, frozenset({"gateway_key_created"}), observe=observe_create
    )
    secret_file = tmp_path / "must-not-exist.txt"
    audits_before = _run(_total_audit_count(env_for_owned_pg))
    result = runner.invoke(
        app,
        [
            "keys",
            "create",
            "--owner-id",
            str(context.owner_id),
            "--cohort-id",
            str(context.cohort_id),
            "--valid-days",
            "30",
            "--policy-file",
            policy,
            "--reason",
            "196 forced late create audit failure",
            "--secret-output-file",
            str(secret_file),
        ],
    )
    assert result.exit_code == 1
    # No secret-output-file or email side effect of a failed creation.
    assert not secret_file.exists()
    # The forced terminal audit was ACTUALLY reached, and only after the
    # write phase: the new key row and its one-time secret were visible
    # (with the typed provider policy) in the SAME open transaction.
    assert [record["action"] for record in create_records] == ["gateway_key_created"]
    assert create_records[0]["same_txn_key_rows"] == 1
    assert create_records[0]["same_txn_secret_rows"] == 1
    assert create_records[0]["same_txn_providers"] == ["openai"]
    # Fresh session: nothing of the rolled-back creation was persisted,
    # including any partial audit record.
    assert _run(_count_for_owner(env_for_owned_pg, GatewayKey, context.owner_id)) == 0
    assert _run(_count_for_owner(env_for_owned_pg, OneTimeSecret, context.owner_id)) == 0
    assert _run(_count_for_owner(env_for_owned_pg, EmailDelivery, context.owner_id)) == 0
    assert _run(_total_audit_count(env_for_owned_pg)) == audits_before


def test_forced_late_update_audit_failure_rolls_back_update(
    tmp_path, env_for_owned_pg: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failed terminal update audit leaves the key completely unchanged."""
    context = _run(_create_context(env_for_owned_pg, with_responses_route=False))
    policy = _policy_file(
        tmp_path,
        {
            "schema_version": 1,
            "allowed_models": ["gpt-test-mini"],
            "allowed_endpoints": ["/v1/chat/completions"],
            "allowed_providers": ["openai"],
            "cost_limit_eur": "42.5",
        },
    )
    secret_file = tmp_path / "update-proof-secret.txt"
    result = runner.invoke(
        app,
        [
            "keys",
            "create",
            "--owner-id",
            str(context.owner_id),
            "--cohort-id",
            str(context.cohort_id),
            "--valid-days",
            "30",
            "--policy-file",
            policy,
            "--reason",
            "196 rollback baseline",
            "--secret-output-file",
            str(secret_file),
        ],
    )
    assert result.exit_code == 0, result.output
    gateway_key_id = uuid.UUID(_kv_value(result.output, "gateway_key_id"))
    baseline = _snapshot_key_row(_run(_fetch_key_row(env_for_owned_pg, gateway_key_id)))
    assert (
        _run(_audit_count(env_for_owned_pg, gateway_key_id, "update_key_configuration"))
        == 0
    )
    audits_before = _run(_total_audit_count(env_for_owned_pg))

    async def observe_update(session, record: dict[str, object]) -> None:
        row = await session.get(GatewayKey, gateway_key_id)
        record["same_txn_providers"] = (
            (row.metadata_json or {}).get("allowed_providers") if row else None
        )
        record["same_txn_token_hash"] = row.token_hash if row else None

    update_records = _install_late_audit_failure(
        monkeypatch, frozenset({"update_key_configuration"}), observe=observe_update
    )
    update_result = runner.invoke(
        app,
        [
            "keys",
            "policy",
            "update",
            str(gateway_key_id),
            "--provider-none",
            "--reason",
            "196 forced late update audit failure",
        ],
    )
    assert update_result.exit_code == 1

    # The forced terminal audit was ACTUALLY reached, and only after the
    # metadata write phase: the CHANGED deny-all provider list was visible
    # in the SAME open transaction while the key material stayed intact.
    assert [record["action"] for record in update_records] == ["update_key_configuration"]
    assert update_records[0]["same_txn_providers"] == []
    assert update_records[0]["same_txn_token_hash"] == baseline["token_hash"]

    # Fresh session: the ENTIRE row is byte-for-byte the pre-update state
    # and no audit record of the failed update exists.
    fresh = _snapshot_key_row(_run(_fetch_key_row(env_for_owned_pg, gateway_key_id)))
    assert fresh == baseline
    assert (
        _run(_audit_count(env_for_owned_pg, gateway_key_id, "update_key_configuration"))
        == 0
    )
    assert _run(_total_audit_count(env_for_owned_pg)) == audits_before
