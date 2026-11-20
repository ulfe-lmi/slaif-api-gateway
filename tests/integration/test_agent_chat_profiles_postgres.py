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

import json
import os
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from slaif_gateway.config import Settings
from slaif_gateway.db.models import GatewayKey
from slaif_gateway.db.repositories.audit import AuditRepository
from slaif_gateway.db.repositories.cohorts import CohortsRepository
from slaif_gateway.db.repositories.institutions import InstitutionsRepository
from slaif_gateway.db.repositories.keys import GatewayKeysRepository
from slaif_gateway.db.repositories.one_time_secrets import OneTimeSecretsRepository
from slaif_gateway.db.repositories.owners import OwnersRepository
from slaif_gateway.db.repositories.pricing import PricingRulesRepository
from slaif_gateway.db.repositories.provider_configs import ProviderConfigsRepository
from slaif_gateway.db.repositories.routing import ModelRoutesRepository
from slaif_gateway.modules.clients.agent_chat import (
    agent_chat_profile_metadata,
    bootstrap_agent_chat_client_modules,
    get_agent_chat_client_module,
)
from slaif_gateway.schemas.key_configuration import KeyConfiguration
from slaif_gateway.schemas.keys import (
    CreateGatewayKeyInput,
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
