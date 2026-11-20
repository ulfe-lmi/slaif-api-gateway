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

import os
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
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
    UpdateGatewayKeyConfigurationInput,
)
from slaif_gateway.services.key_service import KeyService

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
