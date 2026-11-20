"""227-a Agent Chat client profiles — primary-owned PostgreSQL integration tests.

Real-app, real-PostgreSQL coverage for operator binding of the neutral Chat
client-module pin (``metadata_json["chat_client_module"]``) on PERSISTED
state. Pin identities are derived from the live registry through
``agent_chat_profile_metadata`` (never hardcoded tuples), so a documented
profile-data revision keeps these tests honest without editing them.

Round 1 (this file's first test): the binding round trip — create with a
pin, strict current-registry round trip through the service
authoring/update/export law, explicit null clear, repeat, and omission
preservation. Later rounds add projection/dry-run, stale/forged/malformed
export strictness, rotation preservation, secret-safe audit, runtime
dispatch denials, and usage accounting on the same seed helpers.
"""

from __future__ import annotations

import asyncio
import json
import os
import socket
import threading
import time
import uuid
from collections.abc import Iterator
from contextlib import closing, contextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
import pytest
import uvicorn
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from slaif_gateway.config import Settings
from slaif_gateway.db.models import GatewayKey, QuotaReservation, UsageLedger
from slaif_gateway.db.repositories.audit import AuditRepository
from slaif_gateway.db.repositories.cohorts import CohortsRepository
from slaif_gateway.db.repositories.institutions import InstitutionsRepository
from slaif_gateway.db.repositories.keys import GatewayKeysRepository
from slaif_gateway.db.repositories.one_time_secrets import OneTimeSecretsRepository
from slaif_gateway.db.repositories.owners import OwnersRepository
from slaif_gateway.db.repositories.pricing import PricingRulesRepository
from slaif_gateway.db.repositories.provider_configs import ProviderConfigsRepository
from slaif_gateway.db.repositories.routing import ModelRoutesRepository
from slaif_gateway.main import create_app
from slaif_gateway.modules.clients.agent_chat import (
    agent_chat_profile_metadata,
    bootstrap_agent_chat_client_modules,
    get_agent_chat_client_module,
)
from slaif_gateway.schemas.key_configuration import KeyConfiguration
from slaif_gateway.schemas.keys import (
    CreateGatewayKeyInput,
    RevokeGatewayKeyInput,
    RotateGatewayKeyInput,
    UpdateGatewayKeyConfigurationInput,
)
from slaif_gateway.services.key_service import KeyService
from slaif_gateway.services.key_policy_configuration import KeyConfigurationExportError

pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL is not set; skipping agent Chat profile PostgreSQL tests.",
)

HERMES_MODULE_ID = "hermes-0.22.5-chat-v1"
OPENCODE_MODULE_ID = "opencode-1.19.3-chat-v1"
CHAT_ENDPOINT = "/v1/chat/completions"
TEST_MODEL = "gpt-227-agent-chat-profile"

TEST_HMAC_SECRET = "test-hmac-secret-for-agent-chat-profile-1234567890"
TEST_ADMIN_SECRET = "test-admin-secret-for-agent-chat-profile-1234567890"
TEST_ONE_TIME_SECRET_KEY = "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY"

# Runtime dispatch (round 3) requires a provider of the existing
# "openai_compatible" kind: the seed "openai" provider is the NATIVE
# built-in slug and is intentionally NOT a qualified Chat pair. Never
# widen the pair registry or mock the gate away to make these pass.
RUNTIME_MODEL = "gpt-227-agent-chat-runtime"
HERMES227_SVC_KEY_ENV = "HERMES227_SVC_KEY"
FAKE_COMPATIBLE_UPSTREAM_KEY = "fake-227-hermes-compatible-upstream-key"
FAKE_NATIVE_OPENAI_UPSTREAM_KEY = "fake-227-native-openai-upstream-key"

_SEED_CACHE: dict[str, dict[str, uuid.UUID]] = {}


def _module_pin(module_id: str) -> dict[str, str]:
    """Current registry canonical tuple for one statically shipped Chat module."""
    bootstrap_agent_chat_client_modules()
    return dict(agent_chat_profile_metadata(get_agent_chat_client_module(module_id)))


def _service(session) -> KeyService:
    return KeyService(
        settings=Settings(
            TOKEN_HMAC_SECRET_V1=TEST_HMAC_SECRET,
            ADMIN_SESSION_SECRET=TEST_ADMIN_SECRET,
            ONE_TIME_SECRET_ENCRYPTION_KEY=TEST_ONE_TIME_SECRET_KEY,
        ),
        gateway_keys_repository=GatewayKeysRepository(session),
        one_time_secrets_repository=OneTimeSecretsRepository(session),
        audit_repository=AuditRepository(session),
    )


async def _seed(database_url: str) -> dict[str, uuid.UUID]:
    """Institution/owner/cohort plus provider/route/pricing for TEST_MODEL.

    Provider slugs are DB-unique across the session database, so the
    provider is get-or-created and its existing base_url is left alone;
    the requested model is unique to this module.
    """
    if database_url in _SEED_CACHE:
        return _SEED_CACHE[database_url]
    engine = create_async_engine(database_url, future=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(UTC)
    unique = uuid.uuid4().hex
    try:
        async with factory() as session:
            async with session.begin():
                institution = await InstitutionsRepository(session).create_institution(
                    name=f"227 Agent Chat Institute {unique}",
                    country="SI",
                    notes="227 agent Chat profile integration test institution",
                )
                owner = await OwnersRepository(session).create_owner(
                    name="Ada",
                    surname="Lovelace",
                    email=f"owner-227-{unique}@example.test",
                    institution_id=institution.id,
                    notes="227 agent Chat profile integration test owner",
                )
                cohort = await CohortsRepository(session).create_cohort(
                    name=f"agent-chat-profile-{unique}",
                    description="227 agent Chat profile integration test cohort",
                    starts_at=now - timedelta(days=1),
                    ends_at=now + timedelta(days=1),
                )
                providers = ProviderConfigsRepository(session)
                if await providers.get_provider_config_by_provider("openai") is None:
                    await providers.create_provider_config(
                        provider="openai",
                        display_name="OpenAI (227 agent Chat)",
                        base_url="https://api.openai.test/v1",
                        api_key_env_var="OPENAI_UPSTREAM_API_KEY",
                        notes="227 agent Chat profile integration test provider",
                    )
                routes = ModelRoutesRepository(session)
                existing = {
                    route.requested_model
                    for route in await routes.list_model_routes(provider="openai")
                }
                if TEST_MODEL not in existing:
                    await routes.create_model_route(
                        requested_model=TEST_MODEL,
                        provider="openai",
                        upstream_model=TEST_MODEL,
                        match_type="exact",
                        endpoint=CHAT_ENDPOINT,
                        priority=1,
                        visible_in_models=True,
                        supports_streaming=False,
                        notes="227 agent Chat profile integration test route",
                    )
                    await PricingRulesRepository(session).create_pricing_rule(
                        provider="openai",
                        upstream_model=TEST_MODEL,
                        endpoint=CHAT_ENDPOINT,
                        valid_from=now - timedelta(days=1),
                        currency="EUR",
                        input_price_per_1m=Decimal("1.000000000"),
                        output_price_per_1m=Decimal("1.000000000"),
                        request_price=Decimal("0.000000000"),
                        notes="227 agent Chat profile integration test pricing",
                    )
                seed = {
                    "owner_id": owner.id,
                    "cohort_id": cohort.id,
                }
    finally:
        await engine.dispose()
    _SEED_CACHE[database_url] = seed
    return seed


async def _stored_metadata(database_url: str, gateway_key_id: uuid.UUID) -> dict[str, object]:
    engine = create_async_engine(database_url, future=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            row = await session.get(GatewayKey, gateway_key_id)
            return dict(row.metadata_json or {})
    finally:
        await engine.dispose()


async def _key_audit_rows(session, gateway_key_id: uuid.UUID) -> list:
    """Audit rows for one key (entity-scoped filter; newest first)."""
    rows = await AuditRepository(session).list_audit_logs(
        entity_type="gateway_key", limit=500
    )
    return [row for row in rows if row.entity_id == gateway_key_id]


async def _inject_chat_pin(session, row: GatewayKey, pin_value: object) -> None:
    """Raw-DB fault injection of an arbitrary stored ``chat_client_module``.

    Simulates state that the current strict authoring law can no longer
    produce (pre-revision rows, out-of-band edits) so tests can verify the
    fail-closed export/preview/audit behavior against it.
    """
    await session.execute(
        text(
            "UPDATE gateway_keys "
            "SET metadata = jsonb_set("
            "metadata::jsonb, '{chat_client_module}', CAST(:pin AS jsonb)) "
            "WHERE id = :key_id"
        ),
        {"pin": json.dumps(pin_value), "key_id": row.id},
    )
    await session.commit()
    session.expire(row)


async def _create_pinned_key(
    service: KeyService,
    seed: dict[str, uuid.UUID],
    now: datetime,
    chat_client_module: dict[str, str] | None,
    token_limit_total: int = 100_000,
    note: str = "227 agent Chat profile round-2 key",
):
    return await service.create_gateway_key(
        CreateGatewayKeyInput(
            owner_id=seed["owner_id"],
            cohort_id=seed["cohort_id"],
            valid_from=now - timedelta(minutes=5),
            valid_until=now + timedelta(days=1),
            cost_limit_eur=Decimal("10.000000000"),
            token_limit_total=token_limit_total,
            request_limit_total=100,
            allowed_models=[TEST_MODEL],
            allowed_endpoints=[CHAT_ENDPOINT],
            note=note,
            chat_client_module=chat_client_module,
        )
    )


@pytest.mark.asyncio
async def test_chat_pin_binding_round_trip_on_persisted_state(
    migrated_postgres_url: str,
) -> None:
    """Create/set/clear/repeat/preserve Chat pin; assert persisted JSON + export."""
    seed = await _seed(migrated_postgres_url)
    hermes_pin = _module_pin(HERMES_MODULE_ID)
    opencode_pin = _module_pin(OPENCODE_MODULE_ID)
    assert hermes_pin["id"] == HERMES_MODULE_ID
    assert opencode_pin["id"] == OPENCODE_MODULE_ID

    now = datetime.now(UTC)
    engine = create_async_engine(migrated_postgres_url, future=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            service = _service(session)

            # 1) Create WITH a Hermes pin: stored verbatim as the canonical
            #    current-registry tuple, and the strict export echoes it.
            created = await service.create_gateway_key(
                CreateGatewayKeyInput(
                    owner_id=seed["owner_id"],
                    cohort_id=seed["cohort_id"],
                    valid_from=now - timedelta(minutes=5),
                    valid_until=now + timedelta(days=1),
                    cost_limit_eur=Decimal("10.000000000"),
                    token_limit_total=100_000,
                    request_limit_total=100,
                    allowed_models=[TEST_MODEL],
                    allowed_endpoints=[CHAT_ENDPOINT],
                    note="227 agent Chat profile binding round trip",
                    chat_client_module=hermes_pin,
                )
            )
            await session.commit()
            key_id = created.gateway_key_id
            row = await session.get(GatewayKey, key_id)
            assert row is not None
            assert (row.metadata_json or {}).get("chat_client_module") == hermes_pin
            assert (await service.export_gateway_key_configuration(key_id))[
                "chat_client_module"
            ] == hermes_pin

            # 2) Set the OpenCode pin: persisted and exported exactly.
            config = KeyConfiguration()
            config.chat_client_module = opencode_pin
            await service.update_gateway_key_configuration(
                UpdateGatewayKeyConfigurationInput(
                    gateway_key_id=key_id,
                    configuration=config,
                    reason="227 binding round trip: set OpenCode Chat pin",
                )
            )
            await session.commit()
            await session.refresh(row)
            assert (row.metadata_json or {}).get("chat_client_module") == opencode_pin
            assert (await service.export_gateway_key_configuration(key_id))[
                "chat_client_module"
            ] == opencode_pin

            # 3) Explicit null clears ONLY the Chat binding; export shows null.
            config = KeyConfiguration()
            config.chat_client_module = None
            await service.update_gateway_key_configuration(
                UpdateGatewayKeyConfigurationInput(
                    gateway_key_id=key_id,
                    configuration=config,
                    reason="227 binding round trip: clear Chat pin",
                )
            )
            await session.commit()
            await session.refresh(row)
            assert "chat_client_module" not in (row.metadata_json or {})
            assert (
                await service.export_gateway_key_configuration(key_id)
            ).get("chat_client_module") is None

            # 4) Repeat: re-set the Hermes pin on the same key.
            config = KeyConfiguration()
            config.chat_client_module = hermes_pin
            await service.update_gateway_key_configuration(
                UpdateGatewayKeyConfigurationInput(
                    gateway_key_id=key_id,
                    configuration=config,
                    reason="227 binding round trip: re-set Hermes Chat pin",
                )
            )
            await session.commit()
            await session.refresh(row)
            assert (row.metadata_json or {}).get("chat_client_module") == hermes_pin

            # 5) Omission preserves: an unrelated configuration change must
            #    not touch the stored Chat pin.
            config = KeyConfiguration()
            config.token_limit_total = 90_000
            await service.update_gateway_key_configuration(
                UpdateGatewayKeyConfigurationInput(
                    gateway_key_id=key_id,
                    configuration=config,
                    reason="227 binding round trip: unrelated limit update",
                )
            )
            await session.commit()
            await session.refresh(row)
            assert (row.metadata_json or {}).get("chat_client_module") == hermes_pin
            assert row.token_limit_total == 90_000
    finally:
        await engine.dispose()

    # 6) Re-read through a FRESH session/connection: the round trip is real
    #    persisted state, not session-local identity-map state.
    metadata = await _stored_metadata(migrated_postgres_url, key_id)
    assert metadata.get("chat_client_module") == hermes_pin


@pytest.mark.asyncio
async def test_chat_pin_projection_dry_run_makes_no_writes(
    migrated_postgres_url: str,
) -> None:
    """Projection of a valid pin update renders before/after, writes nothing."""
    seed = await _seed(migrated_postgres_url)
    hermes_pin = _module_pin(HERMES_MODULE_ID)
    opencode_pin = _module_pin(OPENCODE_MODULE_ID)
    now = datetime.now(UTC)
    engine = create_async_engine(migrated_postgres_url, future=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            service = _service(session)
            created = await _create_pinned_key(
                service, seed, now, hermes_pin, token_limit_total=100_000
            )
            await session.commit()
            key_id = created.gateway_key_id
            row = await session.get(GatewayKey, key_id)
            assert row is not None
            audits_before = await _key_audit_rows(session, key_id)

            config = KeyConfiguration()
            config.token_limit_total = 50_000
            config.chat_client_module = opencode_pin
            projected = await service.project_key_configuration_update(
                row, configuration=config, reason="227 projection dry run"
            )
            assert projected.gateway_key_id == key_id
            assert projected.before_document["chat_client_module"] == hermes_pin
            assert projected.after_document["chat_client_module"] == opencode_pin
            assert projected.before_document["token_limit_total"] == 100_000
            assert projected.after_document["token_limit_total"] == 50_000

            # Dry-run law: NO write, NO audit, NO state change of any kind.
            await session.refresh(row)
            assert (row.metadata_json or {}).get("chat_client_module") == hermes_pin
            assert row.token_limit_total == 100_000
            audits_after = await _key_audit_rows(session, key_id)
            assert [audit.id for audit in audits_after] == [
                audit.id for audit in audits_before
            ]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_chat_pin_stale_forged_malformed_export_denied_repair_still_possible(
    migrated_postgres_url: str,
) -> None:
    """Strict export/preview deny invalid stored pins; repair stays possible."""
    seed = await _seed(migrated_postgres_url)
    hermes_pin = _module_pin(HERMES_MODULE_ID)
    canary = "OPAQUE-CANARY-227-SECRET-DO-NOT-ECHO"
    now = datetime.now(UTC)
    engine = create_async_engine(migrated_postgres_url, future=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            service = _service(session)
            created = await _create_pinned_key(
                service, seed, now, None, note="227 strict export boundary key"
            )
            await session.commit()
            key_id = created.gateway_key_id
            row = await session.get(GatewayKey, key_id)
            assert row is not None

            # (a) STALE pin: current module id, outdated version.
            stale = dict(hermes_pin)
            stale["version"] = "0.21.0"
            await _inject_chat_pin(session, row, stale)
            with pytest.raises(KeyConfigurationExportError) as stale_exc:
                await service.export_gateway_key_configuration(key_id)
            assert stale_exc.value.error_code == "key_configuration_export_unavailable"
            # Export is a pure read: stored fail-closed state is untouched.
            await session.refresh(row)
            assert (row.metadata_json or {}).get("chat_client_module") == stale

            # An unrelated repair update remains possible while export fails.
            config = KeyConfiguration()
            config.token_limit_total = 80_000
            await service.update_gateway_key_configuration(
                UpdateGatewayKeyConfigurationInput(
                    gateway_key_id=key_id,
                    configuration=config,
                    reason="227 stale pin repair: limit update",
                )
            )
            await session.commit()
            await session.refresh(row)
            assert (row.metadata_json or {}).get("chat_client_module") == stale
            assert row.token_limit_total == 80_000

            # Explicit clear succeeds despite the failing strict export.
            config = KeyConfiguration()
            config.chat_client_module = None
            await service.update_gateway_key_configuration(
                UpdateGatewayKeyConfigurationInput(
                    gateway_key_id=key_id,
                    configuration=config,
                    reason="227 stale pin repair: explicit clear",
                )
            )
            await session.commit()
            await session.refresh(row)
            assert "chat_client_module" not in (row.metadata_json or {})
            assert (
                await service.export_gateway_key_configuration(key_id)
            )["chat_client_module"] is None

            # (b) FORGED pin: plausible but unregistered module id.
            forged = {
                "id": "rogue-9.9.9-chat-v1",
                "version": "9.9.9",
                "fixture_sha256": "0" * 64,
            }
            await _inject_chat_pin(session, row, forged)
            with pytest.raises(KeyConfigurationExportError):
                await service.export_gateway_key_configuration(key_id)
            await session.refresh(row)
            assert (row.metadata_json or {}).get("chat_client_module") == forged

            # (c) MALFORMED non-object pin holding an opaque canary.
            await _inject_chat_pin(session, row, canary)
            with pytest.raises(KeyConfigurationExportError):
                await service.export_gateway_key_configuration(key_id)
            # The no-write projection shares the same strict law: previewing
            # an invalid stored state fails closed, no partial document.
            config = KeyConfiguration()
            config.token_limit_total = 60_000
            with pytest.raises(KeyConfigurationExportError):
                await service.project_key_configuration_update(
                    row, configuration=config, reason="227 preview of invalid state"
                )
            await session.refresh(row)
            assert (row.metadata_json or {}).get("chat_client_module") == canary

            # An unrelated update succeeds and its audit projection is
            # secret-safe: fixed marker only, the canary is never echoed.
            config = KeyConfiguration()
            config.token_limit_total = 70_000
            await service.update_gateway_key_configuration(
                UpdateGatewayKeyConfigurationInput(
                    gateway_key_id=key_id,
                    configuration=config,
                    reason="227 malformed pin repair: limit update",
                )
            )
            await session.commit()
            repair_rows = [
                audit
                for audit in await _key_audit_rows(session, key_id)
                if audit.note == "227 malformed pin repair: limit update"
            ]
            assert len(repair_rows) == 1
            repair = repair_rows[0]
            assert repair.action == "update_key_configuration"
            assert repair.old_values["chat_client_module"] == "unsupported"
            assert repair.new_values["chat_client_module"] == "unsupported"
            repair_blob = json.dumps(
                {
                    **(repair.old_values or {}),
                    **(repair.new_values or {}),
                    "note": repair.note,
                }
            )
            assert canary not in repair_blob

            # Explicit clear restores a strict export again.
            config = KeyConfiguration()
            config.chat_client_module = None
            await service.update_gateway_key_configuration(
                UpdateGatewayKeyConfigurationInput(
                    gateway_key_id=key_id,
                    configuration=config,
                    reason="227 malformed pin repair: explicit clear",
                )
            )
            await session.commit()
            await session.refresh(row)
            assert "chat_client_module" not in (row.metadata_json or {})
            assert (
                await service.export_gateway_key_configuration(key_id)
            )["chat_client_module"] is None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_chat_pin_rotation_preserves_persisted_pin_and_existing_audits(
    migrated_postgres_url: str,
) -> None:
    """Rotation carries the stored pin; existing rotation audits stay secret-safe."""
    seed = await _seed(migrated_postgres_url)
    hermes_pin = _module_pin(HERMES_MODULE_ID)
    canary = "OPAQUE-CANARY-227-SECRET-DO-NOT-ECHO-2"
    now = datetime.now(UTC)
    engine = create_async_engine(migrated_postgres_url, future=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            service = _service(session)

            # (a) Valid current pin: the replacement key persists and
            #     exports the same canonical pin; old key is revoked.
            created = await _create_pinned_key(
                service, seed, now, hermes_pin, note="227 rotation valid pin key"
            )
            await session.commit()
            key_id = created.gateway_key_id
            result = await service.rotate_gateway_key(
                RotateGatewayKeyInput(
                    gateway_key_id=key_id,
                    reason="227 rotation preserves valid pin",
                    revoke_old_key=True,
                )
            )
            await session.commit()
            assert result.old_gateway_key_id == key_id
            assert result.new_plaintext_key.startswith("sk-slaif-")
            new_row = await session.get(GatewayKey, result.new_gateway_key_id)
            assert new_row is not None
            assert (new_row.metadata_json or {}).get("chat_client_module") == hermes_pin
            assert (
                await service.export_gateway_key_configuration(
                    result.new_gateway_key_id
                )
            )["chat_client_module"] == hermes_pin
            old_row = await session.get(GatewayKey, key_id)
            assert old_row.status == "revoked"

            # Existing rotation audit actions link both keys by entity id.
            # The durable audit sanitizer intentionally drops *_key_id and
            # public-key identity fields from new_values, so assert the
            # surviving entity scoping and safe revocation flag, not those.
            rotate_rows = [
                audit
                for audit in await _key_audit_rows(session, key_id)
                if audit.action == "rotate_key"
            ]
            assert len(rotate_rows) == 1
            assert rotate_rows[0].entity_type == "gateway_key"
            assert rotate_rows[0].entity_id == key_id
            assert rotate_rows[0].new_values["old_key_revoked"] is True
            created_rows = [
                audit
                for audit in await _key_audit_rows(session, result.new_gateway_key_id)
                if audit.action == "gateway_key_rotation_created"
            ]
            assert len(created_rows) == 1
            assert created_rows[0].entity_type == "gateway_key"
            assert created_rows[0].entity_id == result.new_gateway_key_id

            # (b) Malformed non-object pin: the raw fail-closed state is
            #     carried onto the replacement key unchanged, and the
            #     opaque canary never reaches any rotation audit row.
            created2 = await _create_pinned_key(
                service, seed, now, None, note="227 rotation malformed pin key"
            )
            await session.commit()
            key2_id = created2.gateway_key_id
            row2 = await session.get(GatewayKey, key2_id)
            assert row2 is not None
            await _inject_chat_pin(session, row2, canary)
            result2 = await service.rotate_gateway_key(
                RotateGatewayKeyInput(
                    gateway_key_id=key2_id,
                    reason="227 rotation carries malformed pin fail-closed",
                    revoke_old_key=True,
                )
            )
            await session.commit()
            new2_row = await session.get(GatewayKey, result2.new_gateway_key_id)
            assert new2_row is not None
            assert (new2_row.metadata_json or {}).get("chat_client_module") == canary
            all_rotation_audits = [
                *await _key_audit_rows(session, key2_id),
                *await _key_audit_rows(session, result2.new_gateway_key_id),
            ]
            assert all_rotation_audits
            for audit in all_rotation_audits:
                blob = json.dumps(
                    {
                        **(audit.old_values or {}),
                        **(audit.new_values or {}),
                        "note": audit.note,
                    }
                )
                assert canary not in blob
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# Round 3: runtime dispatch and PostgreSQL accounting over real HTTP
# ---------------------------------------------------------------------------


async def _seed_runtime_route(
    database_url: str, suffix: str, *, supports_streaming: bool = False
) -> tuple[str, str, str]:
    """Unique openai_compatible provider + explicit Chat route + pricing.

    Returns (provider_slug, base_url, model); the base_url is the respx
    target and model is the public requested model. The provider slug AND
    the public model are unique per invocation, so even when earlier runs
    left same-model routes for other providers in the shared test DB,
    model-to-provider resolution stays unambiguous. The upstream model
    stays the static RUNTIME_MODEL (pricing is per-provider).
    ``supports_streaming`` is passed through to the route for the
    streaming round-trip cases; it defaults to ``False``.
    """
    engine = create_async_engine(database_url, future=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(UTC)
    try:
        async with factory() as session:
            async with session.begin():
                providers = ProviderConfigsRepository(session)
                provider_slug = f"227compat-{suffix}"
                model = f"{RUNTIME_MODEL}-{suffix}"
                assert await providers.get_provider_config_by_provider(
                    provider_slug
                ) is None
                base_url = f"https://svc-227-{suffix}.example/v1"
                await providers.create_provider_config(
                    provider=provider_slug,
                    display_name=f"227 Hermes-compatible service {suffix}",
                    kind="openai_compatible",
                    base_url=base_url,
                    api_key_env_var=HERMES227_SVC_KEY_ENV,
                    enabled=True,
                    timeout_seconds=300,
                    max_retries=0,
                    notes="227 agent Chat profile runtime test provider",
                )
                await ModelRoutesRepository(session).create_model_route(
                    requested_model=model,
                    provider=provider_slug,
                    upstream_model=RUNTIME_MODEL,
                    match_type="exact",
                    endpoint=CHAT_ENDPOINT,
                    priority=1,
                    visible_in_models=True,
                    supports_streaming=supports_streaming,
                    notes="227 agent Chat profile runtime test route",
                )
                await PricingRulesRepository(session).create_pricing_rule(
                    provider=provider_slug,
                    upstream_model=RUNTIME_MODEL,
                    endpoint=CHAT_ENDPOINT,
                    valid_from=now - timedelta(days=1),
                    currency="EUR",
                    input_price_per_1m=Decimal("1.000000000"),
                    output_price_per_1m=Decimal("1.000000000"),
                    request_price=Decimal("0.000000000"),
                    notes="227 agent Chat profile runtime test pricing",
                )
    finally:
        await engine.dispose()
    return provider_slug, base_url, model


def _runtime_settings(database_url: str) -> Settings:
    return Settings(
        APP_ENV="test",
        DATABASE_URL=database_url,
        TOKEN_HMAC_SECRET_V1=TEST_HMAC_SECRET,
        ADMIN_SESSION_SECRET=TEST_ADMIN_SECRET,
        ONE_TIME_SECRET_ENCRYPTION_KEY=TEST_ONE_TIME_SECRET_KEY,
        HARD_MAX_INPUT_TOKENS=10_000,
        DEFAULT_MAX_OUTPUT_TOKENS=100,
    )


async def _runtime_state(database_url: str, gateway_key_id: uuid.UUID):
    """(GatewayKey, reservations desc, ledgers desc) through a fresh session."""
    engine = create_async_engine(database_url, future=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            reservations = (
                await session.execute(
                    select(QuotaReservation)
                    .where(QuotaReservation.gateway_key_id == gateway_key_id)
                    .order_by(QuotaReservation.created_at.desc())
                )
            ).scalars().all()
            ledgers = (
                await session.execute(
                    select(UsageLedger)
                    .where(UsageLedger.gateway_key_id == gateway_key_id)
                    .order_by(UsageLedger.created_at.desc())
                )
            ).scalars().all()
            gateway_key = await session.get(GatewayKey, gateway_key_id)
            return gateway_key, reservations, ledgers
    finally:
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("module_id", "tool_name"),
    [
        (HERMES_MODULE_ID, "read_file"),
        (OPENCODE_MODULE_ID, "read"),
    ],
)
async def test_chat_pin_runtime_success_finalizes_pg_usage(
    migrated_postgres_url: str,
    respx_mock,
    monkeypatch,
    module_id: str,
    tool_name: str,
) -> None:
    """Authenticated current Chat pin dispatches and finalizes on PG.

    Real TestClient HTTP + real PostgreSQL: the finite pair gate passes
    for the unique openai_compatible provider (never the native 'openai'
    seed), the profile decodes xhigh + the local tool declaration, the
    body reaches the mocked generic upstream with the substituted fake
    provider key, and PostgreSQL accounting ends with exactly one
    finalized reservation/ledger and zero pending counters.
    """
    seed = await _seed(migrated_postgres_url)
    suffix = uuid.uuid4().hex[:12]
    provider_slug, base_url, runtime_model = await _seed_runtime_route(
        migrated_postgres_url, suffix
    )
    assert provider_slug not in {"openai", "openrouter"}
    pin = _module_pin(module_id)
    now = datetime.now(UTC)

    engine = create_async_engine(migrated_postgres_url, future=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            service = _service(session)
            created = await service.create_gateway_key(
                CreateGatewayKeyInput(
                    owner_id=seed["owner_id"],
                    cohort_id=seed["cohort_id"],
                    valid_from=now - timedelta(minutes=5),
                    valid_until=now + timedelta(days=1),
                    cost_limit_eur=Decimal("10.000000000"),
                    token_limit_total=100_000,
                    request_limit_total=100,
                    allowed_models=[runtime_model],
                    allowed_endpoints=[CHAT_ENDPOINT],
                    note=f"227 agent Chat profile runtime success {module_id}",
                    chat_client_module=pin,
                )
            )
            await session.commit()
            plaintext_key = created.plaintext_key
            key_id = created.gateway_key_id
    finally:
        await engine.dispose()

    request_body = {
        "model": runtime_model,
        "messages": [{"role": "user", "content": "Read the log file."}],
        "reasoning_effort": "xhigh",
        "stream": False,
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": tool_name,
                    "parameters": {
                        "type": "object",
                        "properties": {"path": {"type": "string"}},
                        "required": ["path"],
                    },
                },
            }
        ],
    }

    monkeypatch.setenv(HERMES227_SVC_KEY_ENV, FAKE_COMPATIBLE_UPSTREAM_KEY)
    upstream = respx_mock.post(f"{base_url}/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "chatcmpl_227_runtime",
                "object": "chat.completion",
                "model": RUNTIME_MODEL,
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "Done."},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 5,
                    "completion_tokens": 6,
                    "total_tokens": 11,
                },
            },
            headers={"x-request-id": "upstream-227-hermes"},
        )
    )

    app = create_app(_runtime_settings(migrated_postgres_url))
    with TestClient(app) as client:
        response = client.post(
            CHAT_ENDPOINT,
            headers={"Authorization": f"Bearer {plaintext_key}"},
            json=request_body,
        )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["id"] == "chatcmpl_227_runtime"
    assert body["choices"][0]["message"]["content"] == "Done."
    assert body["usage"]["total_tokens"] == 11

    # Exact forwarding through the profile-decoded canonical body.
    assert len(upstream.calls) == 1
    upstream_body = json.loads(upstream.calls[0].request.content)
    # The per-invocation public model maps to the static upstream model.
    assert upstream_body["model"] == RUNTIME_MODEL
    assert upstream_body["messages"] == request_body["messages"]
    assert upstream_body["tools"] == request_body["tools"]
    assert upstream_body["reasoning_effort"] == "xhigh"
    upstream_headers = {
        name.lower(): value for name, value in upstream.calls[0].request.headers.items()
    }
    assert upstream_headers.get("authorization") == (
        f"Bearer {FAKE_COMPATIBLE_UPSTREAM_KEY}"
    )
    raw_upstream = upstream.calls[0].request.content.decode("utf-8", "replace")
    assert plaintext_key not in raw_upstream
    assert "sk-slaif-" not in raw_upstream

    # PostgreSQL accounting: exactly one terminal reservation + ledger row,
    # zero pending reservations, correct actual usage.
    gateway_key, reservations, ledgers = await _runtime_state(
        migrated_postgres_url, key_id
    )
    assert len(reservations) == 1
    assert len(ledgers) == 1
    reservation, ledger = reservations[0], ledgers[0]
    assert reservation.status == "finalized"
    assert reservation.reserved_tokens > 0
    assert gateway_key.tokens_reserved_total == 0
    assert gateway_key.requests_reserved_total == 0
    assert gateway_key.cost_reserved_eur == Decimal("0")
    assert gateway_key.tokens_used_total == 11
    assert gateway_key.requests_used_total == 1
    # 5 input + 6 output tokens at 1.00 EUR/1M each = 0.000011 EUR actual.
    assert gateway_key.cost_used_eur == Decimal("0.000011")
    assert ledger.accounting_status == "finalized"
    assert ledger.prompt_tokens == 5
    assert ledger.completion_tokens == 6
    assert ledger.total_tokens == 11

    # The persisted pin survives dispatch; no secrets in the persisted set.
    assert (gateway_key.metadata_json or {}).get("chat_client_module") == pin
    db_payload = json.dumps(
        {
            "gateway_key": {
                "public_key_id": gateway_key.public_key_id,
                "key_hint": gateway_key.key_hint,
                "token_hash": gateway_key.token_hash,
                "metadata": gateway_key.metadata_json,
            },
            "reservation": {
                "request_id": reservation.request_id,
                "requested_model": reservation.requested_model,
                "status": reservation.status,
            },
            "ledger": {
                "usage_raw": ledger.usage_raw,
                "response_metadata": ledger.response_metadata,
                "error_message": ledger.error_message,
            },
        },
        sort_keys=True,
        default=str,
    )
    assert FAKE_COMPATIBLE_UPSTREAM_KEY not in db_payload
    assert plaintext_key not in db_payload
    # Note: the persisted ``key_hint`` intentionally retains the public key
    # prefix, so the ``sk-slaif-`` prefix absence is NOT asserted on the
    # persisted set; exact full-key and provider-secret absence are.


# ---------------------------------------------------------------------------
# Round 3: pre-upstream denials (pair gate, pin validation, auth state)
# ---------------------------------------------------------------------------


async def _provider_forwarding(database_url: str, provider: str) -> tuple[str, str]:
    """(base_url, api_key_env_var) for a stored provider, read at runtime."""
    engine = create_async_engine(database_url, future=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            row = await ProviderConfigsRepository(session).get_provider_config_by_provider(
                provider
            )
            return row.base_url, row.api_key_env_var
    finally:
        await engine.dispose()


async def _create_chat_key(
    database_url: str,
    seed: dict[str, uuid.UUID],
    now: datetime,
    *,
    allowed_models: list[str],
    chat_client_module: dict[str, str] | None,
    note: str,
    request_limit_total: int = 100,
    allowed_endpoints: list[str] | None = None,
    allowed_providers: list[str] | None = None,
) -> tuple[str, uuid.UUID]:
    """Create a Chat-endpoint key; return (plaintext_key, gateway_key_id)."""
    engine = create_async_engine(database_url, future=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            created = await _service(session).create_gateway_key(
                CreateGatewayKeyInput(
                    owner_id=seed["owner_id"],
                    cohort_id=seed["cohort_id"],
                    valid_from=now - timedelta(minutes=5),
                    valid_until=now + timedelta(days=1),
                    cost_limit_eur=Decimal("10.000000000"),
                    token_limit_total=100_000,
                    request_limit_total=request_limit_total,
                    allowed_models=allowed_models,
                    allowed_endpoints=(
                        allowed_endpoints
                        if allowed_endpoints is not None
                        else [CHAT_ENDPOINT]
                    ),
                    note=note,
                    allowed_providers=allowed_providers,
                    chat_client_module=chat_client_module,
                )
            )
            await session.commit()
            return created.plaintext_key, created.gateway_key_id
    finally:
        await engine.dispose()


async def _inject_pin(database_url: str, key_id: uuid.UUID, pin_value: object) -> None:
    engine = create_async_engine(database_url, future=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            row = await session.get(GatewayKey, key_id)
            await _inject_chat_pin(session, row, pin_value)
    finally:
        await engine.dispose()


def _deny_response(response, expected_code: str) -> None:
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == expected_code, response.text


async def _assert_no_forwarding_no_accounting(
    database_url: str, key_id: uuid.UUID, upstream
) -> None:
    """Denials must fail closed before upstream, admission, and accounting."""
    assert len(upstream.calls) == 0
    _, reservations, ledgers = await _runtime_state(database_url, key_id)
    assert reservations == []
    assert ledgers == []


@pytest.mark.asyncio
@pytest.mark.parametrize("module_id", [HERMES_MODULE_ID, OPENCODE_MODULE_ID])
async def test_chat_pin_native_provider_pair_denied_before_admission(
    migrated_postgres_url: str, respx_mock, monkeypatch, module_id: str
) -> None:
    """A valid Chat pin never resolves to the native 'openai' slug.

    The TEST_MODEL seed route belongs to the native 'openai' provider; the
    finite pair gate must reject before admission and before the upstream,
    leaving no reservation or ledger row.
    """
    seed = await _seed(migrated_postgres_url)
    base_url, env_var = await _provider_forwarding(migrated_postgres_url, "openai")
    upstream = respx_mock.post(f"{base_url}/chat/completions").mock(
        return_value=httpx.Response(200, json={"id": "must-not-be-called"})
    )
    monkeypatch.setenv(env_var, FAKE_NATIVE_OPENAI_UPSTREAM_KEY)

    pin = _module_pin(module_id)
    plaintext_key, key_id = await _create_chat_key(
        migrated_postgres_url,
        seed,
        datetime.now(UTC),
        allowed_models=[TEST_MODEL],
        chat_client_module=pin,
        note=f"227 agent Chat profile native pair denial {module_id}",
    )

    app = create_app(_runtime_settings(migrated_postgres_url))
    with TestClient(app) as client:
        response = client.post(
            CHAT_ENDPOINT,
            headers={"Authorization": f"Bearer {plaintext_key}"},
            json={"model": TEST_MODEL, "messages": [{"role": "user", "content": "hi"}]},
        )

    _deny_response(response, "incompatible_client_server_pair")
    await _assert_no_forwarding_no_accounting(migrated_postgres_url, key_id, upstream)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "value"),
    [("version", "0.0.0"), ("fixture_sha256", "0" * 64)],
)
async def test_chat_pin_stale_fixture_denied_before_admission(
    migrated_postgres_url: str, respx_mock, monkeypatch, field: str, value: str
) -> None:
    """A stored pin whose fixture tuple no longer matches fails closed."""
    seed = await _seed(migrated_postgres_url)
    base_url, env_var = await _provider_forwarding(migrated_postgres_url, "openai")
    upstream = respx_mock.post(f"{base_url}/chat/completions").mock(
        return_value=httpx.Response(200, json={"id": "must-not-be-called"})
    )
    monkeypatch.setenv(env_var, FAKE_NATIVE_OPENAI_UPSTREAM_KEY)

    pin = _module_pin(HERMES_MODULE_ID)
    stale = dict(pin)
    stale[field] = value
    plaintext_key, key_id = await _create_chat_key(
        migrated_postgres_url,
        seed,
        datetime.now(UTC),
        allowed_models=[TEST_MODEL],
        chat_client_module=None,
        note=f"227 agent Chat profile stale fixture denial {field}",
    )
    await _inject_pin(migrated_postgres_url, key_id, stale)

    app = create_app(_runtime_settings(migrated_postgres_url))
    with TestClient(app) as client:
        response = client.post(
            CHAT_ENDPOINT,
            headers={"Authorization": f"Bearer {plaintext_key}"},
            json={"model": TEST_MODEL, "messages": [{"role": "user", "content": "hi"}]},
        )

    _deny_response(response, "chat_client_module_fixture_mismatch")
    await _assert_no_forwarding_no_accounting(migrated_postgres_url, key_id, upstream)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "module_id",
    ["not-a-registered-chat-module", "codex-0.149-responses-v1"],
)
async def test_chat_pin_unknown_module_denied_before_admission(
    migrated_postgres_url: str, respx_mock, monkeypatch, module_id: str
) -> None:
    """Unknown IDs, including Responses-only modules, are not Chat pins."""
    seed = await _seed(migrated_postgres_url)
    base_url, env_var = await _provider_forwarding(migrated_postgres_url, "openai")
    upstream = respx_mock.post(f"{base_url}/chat/completions").mock(
        return_value=httpx.Response(200, json={"id": "must-not-be-called"})
    )
    monkeypatch.setenv(env_var, FAKE_NATIVE_OPENAI_UPSTREAM_KEY)

    forged = {"id": module_id, "version": "1.0.0", "fixture_sha256": "f" * 64}
    plaintext_key, key_id = await _create_chat_key(
        migrated_postgres_url,
        seed,
        datetime.now(UTC),
        allowed_models=[TEST_MODEL],
        chat_client_module=None,
        note="227 agent Chat profile unknown module denial",
    )
    await _inject_pin(migrated_postgres_url, key_id, forged)

    app = create_app(_runtime_settings(migrated_postgres_url))
    with TestClient(app) as client:
        response = client.post(
            CHAT_ENDPOINT,
            headers={"Authorization": f"Bearer {plaintext_key}"},
            json={"model": TEST_MODEL, "messages": [{"role": "user", "content": "hi"}]},
        )

    _deny_response(response, "unsupported_client_module")
    await _assert_no_forwarding_no_accounting(migrated_postgres_url, key_id, upstream)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "pin_value",
    [
        {"id": HERMES_MODULE_ID},
        {**_module_pin(HERMES_MODULE_ID), "extra": "x"},
        {"id": 1, "version": "1", "fixture_sha256": "x"},
        HERMES_MODULE_ID,
    ],
    ids=["missing-keys", "extra-key", "non-string-values", "not-a-mapping"],
)
async def test_chat_pin_malformed_metadata_denied_before_admission(
    migrated_postgres_url: str, respx_mock, monkeypatch, pin_value: object
) -> None:
    """Only the exact {id, version, fixture_sha256} string tuple resolves."""
    seed = await _seed(migrated_postgres_url)
    base_url, env_var = await _provider_forwarding(migrated_postgres_url, "openai")
    upstream = respx_mock.post(f"{base_url}/chat/completions").mock(
        return_value=httpx.Response(200, json={"id": "must-not-be-called"})
    )
    monkeypatch.setenv(env_var, FAKE_NATIVE_OPENAI_UPSTREAM_KEY)

    plaintext_key, key_id = await _create_chat_key(
        migrated_postgres_url,
        seed,
        datetime.now(UTC),
        allowed_models=[TEST_MODEL],
        chat_client_module=None,
        note="227 agent Chat profile malformed pin denial",
    )
    await _inject_pin(migrated_postgres_url, key_id, pin_value)

    app = create_app(_runtime_settings(migrated_postgres_url))
    with TestClient(app) as client:
        response = client.post(
            CHAT_ENDPOINT,
            headers={"Authorization": f"Bearer {plaintext_key}"},
            json={"model": TEST_MODEL, "messages": [{"role": "user", "content": "hi"}]},
        )

    _deny_response(response, "chat_client_module_metadata_invalid")
    await _assert_no_forwarding_no_accounting(migrated_postgres_url, key_id, upstream)


@pytest.mark.asyncio
async def test_chat_absent_pin_default_behavior_unaffected(
    migrated_postgres_url: str, respx_mock, monkeypatch
) -> None:
    """Absent pin keeps the existing default Chat dialect end to end.

    The same native 'openai' seed that is denied to a Chat-pinned key still
    serves the pinless key through the default path with normal PG
    finalization.
    """
    seed = await _seed(migrated_postgres_url)
    base_url, env_var = await _provider_forwarding(migrated_postgres_url, "openai")
    monkeypatch.setenv(env_var, FAKE_NATIVE_OPENAI_UPSTREAM_KEY)
    upstream = respx_mock.post(f"{base_url}/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "chatcmpl_227_default",
                "object": "chat.completion",
                "model": TEST_MODEL,
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "ok"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 5,
                    "completion_tokens": 6,
                    "total_tokens": 11,
                },
            },
        )
    )

    plaintext_key, key_id = await _create_chat_key(
        migrated_postgres_url,
        seed,
        datetime.now(UTC),
        allowed_models=[TEST_MODEL],
        chat_client_module=None,
        note="227 agent Chat profile absent-pin default",
    )

    app = create_app(_runtime_settings(migrated_postgres_url))
    with TestClient(app) as client:
        response = client.post(
            CHAT_ENDPOINT,
            headers={"Authorization": f"Bearer {plaintext_key}"},
            json={"model": TEST_MODEL, "messages": [{"role": "user", "content": "hi"}]},
        )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["id"] == "chatcmpl_227_default"
    assert body["usage"]["total_tokens"] == 11

    assert len(upstream.calls) == 1
    headers = {
        name.lower(): value for name, value in upstream.calls[0].request.headers.items()
    }
    assert headers.get("authorization") == f"Bearer {FAKE_NATIVE_OPENAI_UPSTREAM_KEY}"
    assert plaintext_key not in upstream.calls[0].request.content.decode("utf-8", "replace")

    gateway_key, reservations, ledgers = await _runtime_state(
        migrated_postgres_url, key_id
    )
    assert len(reservations) == 1
    assert len(ledgers) == 1
    assert reservations[0].status == "finalized"
    assert gateway_key.tokens_reserved_total == 0
    assert gateway_key.requests_reserved_total == 0
    assert gateway_key.cost_reserved_eur == Decimal("0")
    assert gateway_key.tokens_used_total == 11
    assert gateway_key.requests_used_total == 1
    assert gateway_key.cost_used_eur == Decimal("0.000011")
    assert (gateway_key.metadata_json or {}).get("chat_client_module") is None


@pytest.mark.asyncio
async def test_tampered_gateway_key_denied_before_upstream(
    migrated_postgres_url: str, respx_mock, monkeypatch
) -> None:
    """A syntactically valid but digest-mismatched key is 401, pre-upstream."""
    seed = await _seed(migrated_postgres_url)
    base_url, env_var = await _provider_forwarding(migrated_postgres_url, "openai")
    upstream = respx_mock.post(f"{base_url}/chat/completions").mock(
        return_value=httpx.Response(200, json={"id": "must-not-be-called"})
    )
    monkeypatch.setenv(env_var, FAKE_NATIVE_OPENAI_UPSTREAM_KEY)

    plaintext_key, key_id = await _create_chat_key(
        migrated_postgres_url,
        seed,
        datetime.now(UTC),
        allowed_models=[TEST_MODEL],
        chat_client_module=None,
        note="227 agent Chat profile tampered key denial",
    )
    chars = list(plaintext_key)
    chars[-10] = "b" if chars[-10] != "b" else "a"
    tampered_key = "".join(chars)

    app = create_app(_runtime_settings(migrated_postgres_url))
    with TestClient(app) as client:
        response = client.post(
            CHAT_ENDPOINT,
            headers={"Authorization": f"Bearer {tampered_key}"},
            json={"model": TEST_MODEL, "messages": [{"role": "user", "content": "hi"}]},
        )

    assert response.status_code == 401, response.text
    assert response.json()["error"]["code"] == "gateway_key_invalid_digest", response.text
    await _assert_no_forwarding_no_accounting(migrated_postgres_url, key_id, upstream)


@pytest.mark.asyncio
async def test_revoked_gateway_key_denied_before_upstream(
    migrated_postgres_url: str, respx_mock, monkeypatch
) -> None:
    """A revoked key is 403 before admission, upstream, or accounting."""
    seed = await _seed(migrated_postgres_url)
    base_url, env_var = await _provider_forwarding(migrated_postgres_url, "openai")
    upstream = respx_mock.post(f"{base_url}/chat/completions").mock(
        return_value=httpx.Response(200, json={"id": "must-not-be-called"})
    )
    monkeypatch.setenv(env_var, FAKE_NATIVE_OPENAI_UPSTREAM_KEY)

    plaintext_key, key_id = await _create_chat_key(
        migrated_postgres_url,
        seed,
        datetime.now(UTC),
        allowed_models=[TEST_MODEL],
        chat_client_module=None,
        note="227 agent Chat profile revoked key denial",
    )
    engine = create_async_engine(migrated_postgres_url, future=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            await _service(session).revoke_gateway_key(
                RevokeGatewayKeyInput(
                    gateway_key_id=key_id, reason="227 test revocation"
                )
            )
            await session.commit()
    finally:
        await engine.dispose()

    app = create_app(_runtime_settings(migrated_postgres_url))
    with TestClient(app) as client:
        response = client.post(
            CHAT_ENDPOINT,
            headers={"Authorization": f"Bearer {plaintext_key}"},
            json={"model": TEST_MODEL, "messages": [{"role": "user", "content": "hi"}]},
        )

    assert response.status_code == 403, response.text
    assert response.json()["error"]["code"] == "gateway_key_revoked", response.text
    await _assert_no_forwarding_no_accounting(migrated_postgres_url, key_id, upstream)


# ---------------------------------------------------------------------------
# Round 4: streamed Chat success finalization over real HTTP + PostgreSQL
# ---------------------------------------------------------------------------


def _sse_event(data: str) -> str:
    return f"data: {data}\n\n"


def _stream_success_sse(upstream_model: str) -> str:
    """Canonical three-event Chat success stream: delta, usage, [DONE]."""
    chunk_id = "chatcmpl_227_stream"
    delta_event = {
        "id": chunk_id,
        "object": "chat.completion.chunk",
        "created": 123,
        "model": upstream_model,
        "choices": [
            {"index": 0, "delta": {"content": "Done."}, "finish_reason": "stop"}
        ],
    }
    usage_event = {
        "id": chunk_id,
        "object": "chat.completion.chunk",
        "created": 123,
        "model": upstream_model,
        "choices": [],
        "usage": {"prompt_tokens": 5, "completion_tokens": 6, "total_tokens": 11},
    }
    return (
        _sse_event(json.dumps(delta_event))
        + _sse_event(json.dumps(usage_event))
        + "data: [DONE]\n\n"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("module_id", "tool_name"),
    [
        (HERMES_MODULE_ID, "read_file"),
        (OPENCODE_MODULE_ID, "read"),
    ],
)
async def test_chat_pin_stream_success_finalizes_pg_usage(
    migrated_postgres_url: str,
    respx_mock,
    monkeypatch,
    module_id: str,
    tool_name: str,
) -> None:
    """A streamed Chat success finalizes PostgreSQL usage from the SSE chunk.

    Real TestClient HTTP + real PostgreSQL: the unique openai_compatible
    provider passes the finite pair gate, the profile forwards the stream
    request with the substituted provider key, the complete SSE body is
    consumed, and accounting ends with exactly one finalized
    reservation/ledger and zero pending counters.
    """
    seed = await _seed(migrated_postgres_url)
    suffix = uuid.uuid4().hex[:12]
    provider_slug, base_url, runtime_model = await _seed_runtime_route(
        migrated_postgres_url, suffix, supports_streaming=True
    )
    assert provider_slug not in {"openai", "openrouter"}
    pin = _module_pin(module_id)
    plaintext_key, key_id = await _create_chat_key(
        migrated_postgres_url,
        seed,
        datetime.now(UTC),
        allowed_models=[runtime_model],
        chat_client_module=pin,
        note=f"227 agent Chat profile stream success {module_id}",
    )

    request_body = {
        "model": runtime_model,
        "messages": [{"role": "user", "content": "Read the log file."}],
        "reasoning_effort": "xhigh",
        "stream": True,
        "stream_options": {"include_usage": True},
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": tool_name,
                    "parameters": {
                        "type": "object",
                        "properties": {"path": {"type": "string"}},
                        "required": ["path"],
                    },
                },
            }
        ],
    }
    monkeypatch.setenv(HERMES227_SVC_KEY_ENV, FAKE_COMPATIBLE_UPSTREAM_KEY)
    upstream = respx_mock.post(f"{base_url}/chat/completions").mock(
        return_value=httpx.Response(
            200,
            content=_stream_success_sse(RUNTIME_MODEL).encode(),
            headers={"content-type": "text/event-stream"},
        )
    )

    app = create_app(_runtime_settings(migrated_postgres_url))
    with TestClient(app) as client:
        with client.stream(
            "POST",
            CHAT_ENDPOINT,
            headers={"Authorization": f"Bearer {plaintext_key}"},
            json=request_body,
        ) as response:
            assert response.status_code == 200, response.read()
            streamed = "".join(response.iter_text())

    assert "Done." in streamed
    assert "data: [DONE]" in streamed

    # Exact forwarding through the profile-decoded canonical body, with the
    # substituted provider key and no gateway secret leakage.
    assert len(upstream.calls) == 1
    upstream_body = json.loads(upstream.calls[0].request.content)
    assert upstream_body["model"] == RUNTIME_MODEL
    assert upstream_body["stream"] is True
    assert upstream_body["reasoning_effort"] == "xhigh"
    upstream_headers = {
        name.lower(): value for name, value in upstream.calls[0].request.headers.items()
    }
    assert upstream_headers.get("authorization") == (
        f"Bearer {FAKE_COMPATIBLE_UPSTREAM_KEY}"
    )
    raw_upstream = upstream.calls[0].request.content.decode("utf-8", "replace")
    assert plaintext_key not in raw_upstream
    assert "sk-slaif-" not in raw_upstream

    # PostgreSQL accounting: exactly one terminal reservation + ledger row,
    # zero pending reservations, actual usage from the SSE usage chunk.
    gateway_key, reservations, ledgers = await _runtime_state(
        migrated_postgres_url, key_id
    )
    assert len(reservations) == 1
    assert len(ledgers) == 1
    reservation, ledger = reservations[0], ledgers[0]
    assert reservation.status == "finalized"
    assert ledger.streaming is True
    assert ledger.accounting_status == "finalized"
    assert ledger.prompt_tokens == 5
    assert ledger.completion_tokens == 6
    assert ledger.total_tokens == 11
    assert gateway_key.tokens_reserved_total == 0
    assert gateway_key.requests_reserved_total == 0
    assert gateway_key.cost_reserved_eur == Decimal("0")
    assert gateway_key.tokens_used_total == 11
    assert gateway_key.requests_used_total == 1
    # 5 input + 6 output tokens at 1.00 EUR/1M each = 0.000011 EUR actual.
    assert gateway_key.cost_used_eur == Decimal("0.000011")

    # The persisted pin survives dispatch; no secrets in the persisted set.
    assert (gateway_key.metadata_json or {}).get("chat_client_module") == pin
    db_payload = json.dumps(
        {
            "gateway_key": {
                "public_key_id": gateway_key.public_key_id,
                "key_hint": gateway_key.key_hint,
                "token_hash": gateway_key.token_hash,
                "metadata": gateway_key.metadata_json,
            },
            "reservation": {
                "request_id": reservation.request_id,
                "requested_model": reservation.requested_model,
                "status": reservation.status,
            },
            "ledger": {
                "usage_raw": ledger.usage_raw,
                "response_metadata": ledger.response_metadata,
                "error_message": ledger.error_message,
            },
        },
        sort_keys=True,
        default=str,
    )
    assert FAKE_COMPATIBLE_UPSTREAM_KEY not in db_payload
    assert plaintext_key not in db_payload


# ---------------------------------------------------------------------------
# Round 4: provider failures (non-stream 500, stream 500) release cleanly
# ---------------------------------------------------------------------------

_PROVIDER_ERROR_500_JSON = {
    "error": {"message": "upstream exploded", "type": "provider_error"}
}


async def _streaming_denial_setup(
    migrated_postgres_url: str, respx_mock, monkeypatch, module_id: str, streaming: bool
) -> tuple[str, str, str, dict, object]:
    """(runtime_model, base_url, plaintext_key, key_id, upstream) for a 500 case."""
    seed = await _seed(migrated_postgres_url)
    suffix = uuid.uuid4().hex[:12]
    provider_slug, base_url, runtime_model = await _seed_runtime_route(
        migrated_postgres_url, suffix, supports_streaming=streaming
    )
    assert provider_slug not in {"openai", "openrouter"}
    pin = _module_pin(module_id)
    plaintext_key, key_id = await _create_chat_key(
        migrated_postgres_url,
        seed,
        datetime.now(UTC),
        allowed_models=[runtime_model],
        chat_client_module=pin,
        note=f"227 agent Chat profile provider error {module_id}",
    )
    monkeypatch.setenv(HERMES227_SVC_KEY_ENV, FAKE_COMPATIBLE_UPSTREAM_KEY)
    upstream = respx_mock.post(f"{base_url}/chat/completions").mock(
        return_value=httpx.Response(500, json=_PROVIDER_ERROR_500_JSON)
    )
    return runtime_model, base_url, plaintext_key, key_id, upstream


@pytest.mark.asyncio
async def test_chat_pin_provider_http_error_releases_reservation(
    migrated_postgres_url: str, respx_mock, monkeypatch
) -> None:
    """A non-streamed provider 500 is gateway 500, reservation released.

    Admission happened (the reservation exists) but no output was produced,
    so the reservation is released and the ledger is a failed record with
    zero counters.
    """
    runtime_model, base_url, plaintext_key, key_id, upstream = (
        await _streaming_denial_setup(
            migrated_postgres_url, respx_mock, monkeypatch, HERMES_MODULE_ID, False
        )
    )

    request_body = {
        "model": runtime_model,
        "messages": [{"role": "user", "content": "Read the log file."}],
        "reasoning_effort": "xhigh",
        "stream": False,
    }
    app = create_app(_runtime_settings(migrated_postgres_url))
    with TestClient(app) as client:
        response = client.post(
            CHAT_ENDPOINT,
            headers={"Authorization": f"Bearer {plaintext_key}"},
            json=request_body,
        )

    assert response.status_code == 500, response.text
    assert response.json()["error"]["code"] == "provider_http_error", response.text
    assert len(upstream.calls) == 1

    gateway_key, reservations, ledgers = await _runtime_state(
        migrated_postgres_url, key_id
    )
    assert len(reservations) == 1
    assert len(ledgers) == 1
    reservation, ledger = reservations[0], ledgers[0]
    assert reservation.status == "released"
    assert ledger.streaming is False
    assert ledger.accounting_status == "failed"
    assert ledger.success is False
    assert ledger.error_type == "provider_http_error"
    assert gateway_key.tokens_reserved_total == 0
    assert gateway_key.requests_reserved_total == 0
    assert gateway_key.cost_reserved_eur == Decimal("0")
    assert gateway_key.tokens_used_total == 0
    assert gateway_key.requests_used_total == 0
    assert gateway_key.cost_used_eur == Decimal("0")


# ---------------------------------------------------------------------------
# Round 4: real client disconnect mid-stream (uvicorn + real TCP)
# ---------------------------------------------------------------------------


def _free_port() -> int:
    """A free loopback TCP port for a disposable uvicorn server."""
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@contextmanager
def _run_uvicorn_server(app, port: int) -> Iterator[None]:
    """Run the app on real TCP uvicorn in a daemon thread; exit on scope end."""
    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=port,
        log_level="error",
        lifespan="on",
        timeout_keep_alive=1,
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=lambda: asyncio.run(server.serve()), daemon=True)
    thread.start()
    deadline = time.monotonic() + 10.0
    while not server.started:
        if time.monotonic() > deadline:
            raise AssertionError("uvicorn server did not start in time")
        time.sleep(0.05)
    try:
        yield
    finally:
        server.should_exit = True
        thread.join(timeout=10)


async def _disconnect_stream_sse(upstream_model: str):
    """Partial delta, 2 s stall, then late delta + usage + [DONE].

    The client disconnects after the first delta; the late yields prove
    the upstream generator is interrupted rather than consumed.
    """
    chunk_id = "chatcmpl_227_disconnect"

    def _event(content: str, finish_reason: str | None, usage: dict | None) -> str:
        event: dict = {
            "id": chunk_id,
            "object": "chat.completion.chunk",
            "created": 123,
            "model": upstream_model,
            "choices": [
                {"index": 0, "delta": {"content": content}, "finish_reason": finish_reason}
            ],
        }
        if usage is not None:
            event["choices"] = []
            event["usage"] = usage
        return _sse_event(json.dumps(event))

    # httpx treats async-generator content items as raw bytes chunks.
    yield _event("Partial answer.", None, None).encode()
    await asyncio.sleep(2.0)
    yield _event(
        "", None, {"prompt_tokens": 5, "completion_tokens": 6, "total_tokens": 11}
    ).encode()
    yield b"data: [DONE]\n\n"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("module_id", "tool_name"),
    [
        (HERMES_MODULE_ID, "read_file"),
        (OPENCODE_MODULE_ID, "read"),
    ],
)
async def test_chat_pin_client_disconnect_proves_actual_cancellation(
    migrated_postgres_url: str,
    respx_mock,
    monkeypatch,
    module_id: str,
    tool_name: str,
) -> None:
    """A real TCP client disconnect mid-stream cancels the app and estimates.

    Real uvicorn over loopback + real PostgreSQL: the stream starts and the
    first delta is delivered, then the client drops the connection while
    the upstream generator is still producing. The gateway's shielded
    interruption finalization records an estimated (non-invoice-grade)
    ledger, finalizes the reservation, and burns exactly one request.
    """
    seed = await _seed(migrated_postgres_url)
    suffix = uuid.uuid4().hex[:12]
    provider_slug, base_url, runtime_model = await _seed_runtime_route(
        migrated_postgres_url, suffix, supports_streaming=True
    )
    assert provider_slug not in {"openai", "openrouter"}
    pin = _module_pin(module_id)
    plaintext_key, key_id = await _create_chat_key(
        migrated_postgres_url,
        seed,
        datetime.now(UTC),
        allowed_models=[runtime_model],
        chat_client_module=pin,
        note=f"227 agent Chat profile disconnect {module_id}",
    )

    request_body = {
        "model": runtime_model,
        "messages": [{"role": "user", "content": "Read the log file."}],
        "reasoning_effort": "xhigh",
        "stream": True,
        "stream_options": {"include_usage": True},
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": tool_name,
                    "parameters": {
                        "type": "object",
                        "properties": {"path": {"type": "string"}},
                        "required": ["path"],
                    },
                },
            }
        ],
    }
    monkeypatch.setenv(HERMES227_SVC_KEY_ENV, FAKE_COMPATIBLE_UPSTREAM_KEY)
    upstream = respx_mock.post(f"{base_url}/chat/completions").mock(
        return_value=httpx.Response(
            200,
            content=_disconnect_stream_sse(RUNTIME_MODEL),
            headers={"content-type": "text/event-stream"},
        )
    )

    app = create_app(_runtime_settings(migrated_postgres_url))
    port = _free_port()
    # respx intercepts every httpx client in the process; the test-side
    # loopback client must be a real TCP connection, so mark its URL
    # pass-through while the provider URL stays mocked.
    respx_mock.post(f"http://127.0.0.1:{port}{CHAT_ENDPOINT}").pass_through()
    with _run_uvicorn_server(app, port):
        http = httpx.Client(timeout=httpx.Timeout(30.0))
        try:
            with http.stream(
                "POST",
                f"http://127.0.0.1:{port}{CHAT_ENDPOINT}",
                headers={"Authorization": f"Bearer {plaintext_key}"},
                json=request_body,
            ) as response:
                assert response.status_code == 200, response.read()
                received = ""
                for chunk in response.iter_text():
                    received += chunk
                    if "Partial answer." in received:
                        break
                # Exiting the stream context closes the real TCP
                # connection mid-stream.
            assert "NEVER-ARRIVED." not in received
        finally:
            http.close()
        # Give the app's shielded interruption finalization time to commit
        # before the server is torn down.
        time.sleep(1.5)
    assert len(upstream.calls) == 1

    deadline = time.monotonic() + 15.0
    while time.monotonic() < deadline:
        gateway_key, reservations, ledgers = await _runtime_state(
            migrated_postgres_url, key_id
        )
        if ledgers:
            break
        await asyncio.sleep(0.25)

    assert ledgers, "no ledger row was written before the polling deadline"
    assert len(reservations) == 1
    assert len(ledgers) == 1
    reservation, ledger = reservations[0], ledgers[0]
    assert reservation.status == "finalized"
    assert ledger.streaming is True
    assert ledger.success is False
    assert ledger.accounting_status == "estimated"
    assert ledger.error_type == "client_disconnected"
    assert ledger.completion_tokens > 0
    metadata = ledger.response_metadata or {}
    assert metadata.get("stream_interruption_reason") == (
        "chat_streaming_client_disconnected_estimated"
    )
    assert metadata.get("accounting_estimate_reason") == (
        "chat_streaming_client_disconnected_estimated"
    )
    assert metadata.get("final_provider_usage_available") is False
    assert gateway_key.tokens_reserved_total == 0
    assert gateway_key.requests_reserved_total == 0
    assert gateway_key.cost_reserved_eur == Decimal("0")
    assert gateway_key.requests_used_total == 1
    assert gateway_key.tokens_used_total > 0
    # No cost_used_eur assertion: the disconnect finalizes the estimated
    # (non-zero) cost, not zero.

    # The persisted pin survives interruption; no secrets in the persisted set.
    assert (gateway_key.metadata_json or {}).get("chat_client_module") == pin
    db_payload = json.dumps(
        {
            "gateway_key": {
                "public_key_id": gateway_key.public_key_id,
                "key_hint": gateway_key.key_hint,
                "token_hash": gateway_key.token_hash,
                "metadata": gateway_key.metadata_json,
            },
            "reservation": {
                "request_id": reservation.request_id,
                "requested_model": reservation.requested_model,
                "status": reservation.status,
            },
            "ledger": {
                "usage_raw": ledger.usage_raw,
                "response_metadata": ledger.response_metadata,
                "error_message": ledger.error_message,
            },
        },
        sort_keys=True,
        default=str,
    )
    assert FAKE_COMPATIBLE_UPSTREAM_KEY not in db_payload
    assert plaintext_key not in db_payload


# ---------------------------------------------------------------------------
# Round 4: request quota exhaustion (429 before upstream)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chat_pin_request_quota_exhausted_denied_429_before_upstream(
    migrated_postgres_url: str,
    respx_mock,
    monkeypatch,
) -> None:
    """A key at its request limit gets 429 preflight before any forwarding.

    PG preflight only: the first request consumes the single allowed
    request and finalizes normally; the identical second request is denied
    by the PostgreSQL request-quota preflight with 429
    ``quota_limit_exceeded`` before the provider is contacted. Concurrent
    lazy-wait revalidation is Redis-gated and is not faked here.
    """
    seed = await _seed(migrated_postgres_url)
    suffix = uuid.uuid4().hex[:12]
    provider_slug, base_url, runtime_model = await _seed_runtime_route(
        migrated_postgres_url, suffix
    )
    assert provider_slug not in {"openai", "openrouter"}
    pin = _module_pin(HERMES_MODULE_ID)
    plaintext_key, key_id = await _create_chat_key(
        migrated_postgres_url,
        seed,
        datetime.now(UTC),
        allowed_models=[runtime_model],
        chat_client_module=pin,
        note="227 agent Chat profile request quota exhaustion",
        request_limit_total=1,
    )

    request_body = {
        "model": runtime_model,
        "messages": [{"role": "user", "content": "Read the log file."}],
        "reasoning_effort": "xhigh",
        "stream": False,
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "read_file",
                    "parameters": {
                        "type": "object",
                        "properties": {"path": {"type": "string"}},
                        "required": ["path"],
                    },
                },
            }
        ],
    }
    monkeypatch.setenv(HERMES227_SVC_KEY_ENV, FAKE_COMPATIBLE_UPSTREAM_KEY)
    upstream = respx_mock.post(f"{base_url}/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "chatcmpl_227_runtime",
                "object": "chat.completion",
                "model": RUNTIME_MODEL,
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "Done."},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 5,
                    "completion_tokens": 6,
                    "total_tokens": 11,
                },
            },
            headers={"x-request-id": "upstream-227-hermes"},
        )
    )

    app = create_app(_runtime_settings(migrated_postgres_url))
    with TestClient(app) as client:
        first = client.post(
            CHAT_ENDPOINT,
            headers={"Authorization": f"Bearer {plaintext_key}"},
            json=request_body,
        )
        assert first.status_code == 200, first.text
        assert first.json()["usage"]["total_tokens"] == 11

        second = client.post(
            CHAT_ENDPOINT,
            headers={"Authorization": f"Bearer {plaintext_key}"},
            json=request_body,
        )

    assert second.status_code == 429, second.text
    assert second.json()["error"]["code"] == "quota_limit_exceeded"
    # The denied request never reached the provider.
    assert len(upstream.calls) == 1

    gateway_key, reservations, ledgers = await _runtime_state(
        migrated_postgres_url, key_id
    )
    assert len(reservations) == 1
    assert len(ledgers) == 1
    assert reservations[0].status == "finalized"
    assert gateway_key.requests_used_total == 1
    assert gateway_key.tokens_reserved_total == 0
    assert gateway_key.requests_reserved_total == 0
    assert gateway_key.cost_reserved_eur == Decimal("0")


@pytest.mark.asyncio
async def test_chat_pin_stream_provider_error_after_admission_releases_reservation(
    migrated_postgres_url: str, respx_mock, monkeypatch
) -> None:
    """A provider 500 on a stream request is an SSE error event, released.

    Streaming opens the upstream inside the response generator, so the
    client receives a 200 SSE body containing the error event; with no
    output delivered the reservation is released and the ledger failed.
    """
    runtime_model, base_url, plaintext_key, key_id, upstream = (
        await _streaming_denial_setup(
            migrated_postgres_url, respx_mock, monkeypatch, HERMES_MODULE_ID, True
        )
    )

    request_body = {
        "model": runtime_model,
        "messages": [{"role": "user", "content": "Read the log file."}],
        "reasoning_effort": "xhigh",
        "stream": True,
    }
    app = create_app(_runtime_settings(migrated_postgres_url))
    with TestClient(app) as client:
        with client.stream(
            "POST",
            CHAT_ENDPOINT,
            headers={"Authorization": f"Bearer {plaintext_key}"},
            json=request_body,
        ) as response:
            assert response.status_code == 200, response.read()
            streamed = "".join(response.iter_text())

    assert "provider_http_error" in streamed
    assert "Done." not in streamed
    assert len(upstream.calls) == 1

    gateway_key, reservations, ledgers = await _runtime_state(
        migrated_postgres_url, key_id
    )
    assert len(reservations) == 1
    assert len(ledgers) == 1
    reservation, ledger = reservations[0], ledgers[0]
    assert reservation.status == "released"
    assert ledger.streaming is True
    assert ledger.accounting_status == "failed"
    assert ledger.success is False
    assert ledger.error_type == "provider_http_error"
    assert gateway_key.tokens_reserved_total == 0
    assert gateway_key.requests_reserved_total == 0
    assert gateway_key.cost_reserved_eur == Decimal("0")
    assert gateway_key.tokens_used_total == 0
    assert gateway_key.requests_used_total == 0
    assert gateway_key.cost_used_eur == Decimal("0")


# ---------------------------------------------------------------------------
# Round 5: key-policy and route-capability denials (model/endpoint/provider/stream)
# ---------------------------------------------------------------------------


async def _policy_denial_setup(
    migrated_postgres_url: str,
    respx_mock,
    monkeypatch,
    module_id: str,
    *,
    allowed_models: list[str] | None = None,
    allowed_endpoints: list[str] | None = None,
    allowed_providers: list[str] | None = None,
) -> tuple[str, str, uuid.UUID, object]:
    """(runtime_model, plaintext_key, key_id, upstream) for a policy denial.

    Seeds a unique openai_compatible runtime route, creates a valid-pinned
    Chat key with one failing key-policy dimension, and mocks the upstream
    endpoint that must never be called.
    """
    seed = await _seed(migrated_postgres_url)
    suffix = uuid.uuid4().hex[:12]
    provider_slug, base_url, runtime_model = await _seed_runtime_route(
        migrated_postgres_url, suffix
    )
    assert provider_slug not in {"openai", "openrouter"}
    pin = _module_pin(module_id)
    plaintext_key, key_id = await _create_chat_key(
        migrated_postgres_url,
        seed,
        datetime.now(UTC),
        allowed_models=allowed_models or [runtime_model],
        chat_client_module=pin,
        note=f"227 agent Chat profile policy denial {module_id}",
        allowed_endpoints=allowed_endpoints,
        allowed_providers=allowed_providers,
    )
    monkeypatch.setenv(HERMES227_SVC_KEY_ENV, FAKE_COMPATIBLE_UPSTREAM_KEY)
    upstream = respx_mock.post(f"{base_url}/chat/completions").mock(
        return_value=httpx.Response(200, json={"id": "must-not-be-called"})
    )
    return runtime_model, plaintext_key, key_id, upstream


def _policy_post(client, plaintext_key: str, body: dict) -> object:
    return client.post(
        CHAT_ENDPOINT,
        headers={"Authorization": f"Bearer {plaintext_key}"},
        json=body,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("module_id", [HERMES_MODULE_ID, OPENCODE_MODULE_ID])
async def test_chat_pin_model_not_allowed_denied_before_upstream(
    migrated_postgres_url: str, respx_mock, monkeypatch, module_id: str
) -> None:
    """A key whose allowed_models omits the requested model is denied 403."""
    runtime_model, plaintext_key, key_id, upstream = await _policy_denial_setup(
        migrated_postgres_url,
        respx_mock,
        monkeypatch,
        module_id,
        allowed_models=["227-unrelated-model"],
    )
    app = create_app(_runtime_settings(migrated_postgres_url))
    with TestClient(app) as client:
        response = _policy_post(
            client,
            plaintext_key,
            {"model": runtime_model, "messages": [{"role": "user", "content": "hi"}]},
        )
    assert response.status_code == 403, response.text
    assert (
        response.json()["error"]["code"] == "model_not_allowed_for_key"
    ), response.text
    await _assert_no_forwarding_no_accounting(migrated_postgres_url, key_id, upstream)


@pytest.mark.asyncio
@pytest.mark.parametrize("module_id", [HERMES_MODULE_ID, OPENCODE_MODULE_ID])
async def test_chat_pin_endpoint_not_allowed_denied_before_upstream(
    migrated_postgres_url: str, respx_mock, monkeypatch, module_id: str
) -> None:
    """A key that does not allow the Chat endpoint is denied 403 here."""
    runtime_model, plaintext_key, key_id, upstream = await _policy_denial_setup(
        migrated_postgres_url,
        respx_mock,
        monkeypatch,
        module_id,
        allowed_endpoints=["/v1/responses"],
    )
    app = create_app(_runtime_settings(migrated_postgres_url))
    with TestClient(app) as client:
        response = _policy_post(
            client,
            plaintext_key,
            {"model": runtime_model, "messages": [{"role": "user", "content": "hi"}]},
        )
    assert response.status_code == 403, response.text
    assert (
        response.json()["error"]["code"] == "endpoint_not_allowed"
    ), response.text
    await _assert_no_forwarding_no_accounting(migrated_postgres_url, key_id, upstream)


@pytest.mark.asyncio
@pytest.mark.parametrize("module_id", [HERMES_MODULE_ID, OPENCODE_MODULE_ID])
async def test_chat_pin_provider_not_allowed_denied_before_upstream(
    migrated_postgres_url: str, respx_mock, monkeypatch, module_id: str
) -> None:
    """A key restricted to the native 'openai' slug cannot use the compat route."""
    runtime_model, plaintext_key, key_id, upstream = await _policy_denial_setup(
        migrated_postgres_url,
        respx_mock,
        monkeypatch,
        module_id,
        allowed_providers=["openai"],
    )
    app = create_app(_runtime_settings(migrated_postgres_url))
    with TestClient(app) as client:
        response = _policy_post(
            client,
            plaintext_key,
            {"model": runtime_model, "messages": [{"role": "user", "content": "hi"}]},
        )
    assert response.status_code == 403, response.text
    assert (
        response.json()["error"]["code"] == "provider_not_allowed_for_key"
    ), response.text
    await _assert_no_forwarding_no_accounting(migrated_postgres_url, key_id, upstream)


@pytest.mark.asyncio
@pytest.mark.parametrize("module_id", [HERMES_MODULE_ID, OPENCODE_MODULE_ID])
async def test_chat_pin_streaming_disabled_route_denied_before_upstream(
    migrated_postgres_url: str, respx_mock, monkeypatch, module_id: str
) -> None:
    """stream=True on a non-streaming route is denied 400 with param=stream."""
    runtime_model, plaintext_key, key_id, upstream = await _policy_denial_setup(
        migrated_postgres_url, respx_mock, monkeypatch, module_id
    )
    app = create_app(_runtime_settings(migrated_postgres_url))
    with TestClient(app) as client:
        response = _policy_post(
            client,
            plaintext_key,
            {
                "model": runtime_model,
                "messages": [{"role": "user", "content": "hi"}],
                "stream": True,
            },
        )
    assert response.status_code == 400, response.text
    error = response.json()["error"]
    assert error["code"] == "chat_capability_not_supported", response.text
    assert error["param"] == "stream", response.text
    await _assert_no_forwarding_no_accounting(migrated_postgres_url, key_id, upstream)
