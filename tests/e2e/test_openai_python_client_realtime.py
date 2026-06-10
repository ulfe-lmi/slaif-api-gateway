from __future__ import annotations

import asyncio
import json
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
import pytest
import respx
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from tests.e2e.test_openai_python_client_chat import (
    FAKE_OPENAI_UPSTREAM_KEY,
    _configure_runtime_environment,
    _free_port,
    _run_uvicorn_server,
    _test_database_url,
)
from tests.integration.db_test_utils import run_alembic_upgrade_head

REALTIME_CLIENT_SECRETS_ENDPOINT = "/v1/realtime/client_secrets"


async def _create_realtime_test_data(database_url: str):
    from slaif_gateway.config import Settings
    from slaif_gateway.db.models import ModelRoute, PricingRule
    from slaif_gateway.db.repositories.audit import AuditRepository
    from slaif_gateway.db.repositories.cohorts import CohortsRepository
    from slaif_gateway.db.repositories.institutions import InstitutionsRepository
    from slaif_gateway.db.repositories.keys import GatewayKeysRepository
    from slaif_gateway.db.repositories.one_time_secrets import OneTimeSecretsRepository
    from slaif_gateway.db.repositories.owners import OwnersRepository
    from slaif_gateway.db.repositories.pricing import PricingRulesRepository
    from slaif_gateway.db.repositories.provider_configs import ProviderConfigsRepository
    from slaif_gateway.db.repositories.routing import ModelRoutesRepository
    from slaif_gateway.schemas.keys import CreateGatewayKeyInput
    from slaif_gateway.services.key_service import KeyService

    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    unique_id = uuid.uuid4().hex
    now = datetime.now(UTC)

    try:
        async with session_factory() as session:
            await session.execute(
                delete(ModelRoute).where(
                    ModelRoute.requested_model == "classroom-realtime",
                    ModelRoute.provider == "openai",
                    ModelRoute.endpoint == REALTIME_CLIENT_SECRETS_ENDPOINT,
                )
            )
            await session.execute(
                delete(PricingRule).where(
                    PricingRule.provider == "openai",
                    PricingRule.upstream_model == "gpt-realtime-mini",
                    PricingRule.endpoint == REALTIME_CLIENT_SECRETS_ENDPOINT,
                )
            )

            institutions = InstitutionsRepository(session)
            owners = OwnersRepository(session)
            cohorts = CohortsRepository(session)
            providers = ProviderConfigsRepository(session)
            routes = ModelRoutesRepository(session)
            pricing = PricingRulesRepository(session)

            institution = await institutions.create_institution(
                name=f"SLAIF Realtime E2E Institute {unique_id}",
                country="SI",
                notes="Realtime E2E test data",
            )
            owner = await owners.create_owner(
                name="Realtime",
                surname="Client",
                email=f"realtime-client-e2e-{unique_id}@example.org",
                institution_id=institution.id,
                notes="Realtime E2E owner",
            )
            cohort = await cohorts.create_cohort(
                name=f"realtime-client-e2e-{unique_id}",
                description="Realtime E2E cohort",
                starts_at=now - timedelta(days=1),
                ends_at=now + timedelta(days=1),
            )

            provider_config = await providers.get_provider_config_by_provider("openai")
            if provider_config is None:
                await providers.create_provider_config(
                    provider="openai",
                    display_name="OpenAI Realtime E2E",
                    base_url="https://api.openai.com/v1",
                    api_key_env_var="OPENAI_UPSTREAM_API_KEY",
                    notes="Realtime E2E provider config without secrets",
                )
            else:
                await providers.update_provider_metadata(
                    provider_config.id,
                    display_name="OpenAI Realtime E2E",
                    base_url="https://api.openai.com/v1",
                    api_key_env_var="OPENAI_UPSTREAM_API_KEY",
                    notes="Realtime E2E provider config without secrets",
                )
                await providers.set_provider_enabled(provider_config.id, enabled=True)

            await routes.create_model_route(
                requested_model="classroom-realtime",
                provider="openai",
                upstream_model="gpt-realtime-mini",
                match_type="exact",
                endpoint=REALTIME_CLIENT_SECRETS_ENDPOINT,
                priority=1,
                visible_in_models=False,
                supports_streaming=False,
                capabilities={
                    "realtime": {
                        "audio": True,
                        "webrtc_client_secrets": True,
                        "transcription": False,
                    }
                },
                notes="Realtime E2E route",
            )
            await pricing.create_pricing_rule(
                provider="openai",
                upstream_model="gpt-realtime-mini",
                endpoint=REALTIME_CLIENT_SECRETS_ENDPOINT,
                valid_from=now - timedelta(days=1),
                currency="EUR",
                input_price_per_1m=Decimal("0.500000000"),
                output_price_per_1m=Decimal("1.000000000"),
                request_price=Decimal("0.010000000"),
                notes="Realtime E2E pricing",
            )

            key_service = KeyService(
                settings=Settings(),
                gateway_keys_repository=GatewayKeysRepository(session),
                one_time_secrets_repository=OneTimeSecretsRepository(session),
                audit_repository=AuditRepository(session),
            )
            created_key = await key_service.create_gateway_key(
                CreateGatewayKeyInput(
                    owner_id=owner.id,
                    cohort_id=cohort.id,
                    valid_from=now - timedelta(minutes=5),
                    valid_until=now + timedelta(days=1),
                    cost_limit_eur=Decimal("10.000000000"),
                    token_limit_total=100_000,
                    request_limit_total=100,
                    allowed_models=["classroom-realtime"],
                    allowed_endpoints=[REALTIME_CLIENT_SECRETS_ENDPOINT],
                    note="Realtime E2E key",
                )
            )
            await session.commit()
            return created_key
    finally:
        await engine.dispose()


@pytest.mark.e2e
def test_openai_python_client_realtime_client_secret_e2e(monkeypatch: pytest.MonkeyPatch) -> None:
    database_url = _test_database_url()
    run_alembic_upgrade_head(database_url)
    _configure_runtime_environment(monkeypatch, database_url)
    created = asyncio.run(_create_realtime_test_data(database_url))

    from openai import OpenAI
    from slaif_gateway.config import get_settings
    from slaif_gateway.main import create_app

    port = _free_port()
    monkeypatch.setenv("OPENAI_API_KEY", created.plaintext_key)
    monkeypatch.setenv("OPENAI_BASE_URL", f"http://127.0.0.1:{port}/v1")

    app = create_app(get_settings())

    with _run_uvicorn_server(app, port):
        with respx.mock(assert_all_mocked=True, assert_all_called=True) as router:
            router.route(host="127.0.0.1").pass_through()
            upstream_route = router.post("https://api.openai.com/v1/realtime/client_secrets").mock(
                return_value=httpx.Response(
                    200,
                    json={
                        "value": "rtcs_123",
                        "expires_at": 1893456000,
                        "session": {
                            "id": "sess_123",
                            "object": "realtime.session",
                            "type": "realtime",
                            "model": "gpt-realtime-mini",
                            "output_modalities": ["audio"],
                            "audio": {
                                "output": {
                                    "voice": "cedar",
                                    "format": {"type": "audio/pcmu"},
                                }
                            },
                        },
                    },
                    headers={
                        "content-type": "application/json",
                        "openai-request-id": "upstream-realtime",
                    },
                )
            )

            client = OpenAI()
            response = client.realtime.client_secrets.create(
                expires_after={"anchor": "created_at", "seconds": 600},
                session={
                    "type": "realtime",
                    "model": "classroom-realtime",
                    "output_modalities": ["audio"],
                    "audio": {
                        "input": {"format": {"type": "audio/pcm", "rate": 24000}},
                        "output": {"format": {"type": "audio/pcmu"}, "voice": "cedar"},
                    },
                    "instructions": "Keep answers short.",
                    "max_output_tokens": 256,
                },
            )

    assert response.value == "rtcs_123"
    assert response.session.id == "sess_123"
    assert response.session.model == "gpt-realtime-mini"
    assert len(upstream_route.calls) == 1

    upstream_request = upstream_route.calls[0].request
    assert upstream_request.headers["authorization"] == f"Bearer {FAKE_OPENAI_UPSTREAM_KEY}"
    assert upstream_request.headers["authorization"] != f"Bearer {created.plaintext_key}"
    upstream_body = json.loads(upstream_request.content)
    assert upstream_body["session"]["model"] == "gpt-realtime-mini"
    assert upstream_body["session"]["audio"]["output"]["voice"] == "cedar"
