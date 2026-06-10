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
    _load_accounting_state,
    _run_uvicorn_server,
    _test_database_url,
)
from tests.integration.db_test_utils import run_alembic_upgrade_head

EMBEDDINGS_ENDPOINT = "/v1/embeddings"


async def _create_embeddings_test_data(database_url: str):
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
                    ModelRoute.requested_model == "classroom-embedding",
                    ModelRoute.provider == "openai",
                    ModelRoute.endpoint == EMBEDDINGS_ENDPOINT,
                )
            )
            await session.execute(
                delete(PricingRule).where(
                    PricingRule.provider == "openai",
                    PricingRule.upstream_model == "text-embedding-3-small",
                    PricingRule.endpoint == EMBEDDINGS_ENDPOINT,
                )
            )

            institutions = InstitutionsRepository(session)
            owners = OwnersRepository(session)
            cohorts = CohortsRepository(session)
            providers = ProviderConfigsRepository(session)
            routes = ModelRoutesRepository(session)
            pricing = PricingRulesRepository(session)

            institution = await institutions.create_institution(
                name=f"SLAIF Embeddings E2E Institute {unique_id}",
                country="SI",
                notes="Embeddings E2E test data",
            )
            owner = await owners.create_owner(
                name="Embeddings",
                surname="Client",
                email=f"embeddings-client-e2e-{unique_id}@example.org",
                institution_id=institution.id,
                notes="Embeddings E2E owner",
            )
            cohort = await cohorts.create_cohort(
                name=f"embeddings-client-e2e-{unique_id}",
                description="Embeddings E2E cohort",
                starts_at=now - timedelta(days=1),
                ends_at=now + timedelta(days=1),
            )

            provider_config = await providers.get_provider_config_by_provider("openai")
            if provider_config is None:
                await providers.create_provider_config(
                    provider="openai",
                    display_name="OpenAI Embeddings E2E",
                    base_url="https://api.openai.com/v1",
                    api_key_env_var="OPENAI_UPSTREAM_API_KEY",
                    notes="Embeddings E2E test provider config without secrets",
                )
            else:
                await providers.update_provider_metadata(
                    provider_config.id,
                    display_name="OpenAI Embeddings E2E",
                    base_url="https://api.openai.com/v1",
                    api_key_env_var="OPENAI_UPSTREAM_API_KEY",
                    notes="Embeddings E2E test provider config without secrets",
                )
                await providers.set_provider_enabled(provider_config.id, enabled=True)

            await routes.create_model_route(
                requested_model="classroom-embedding",
                provider="openai",
                upstream_model="text-embedding-3-small",
                match_type="exact",
                endpoint=EMBEDDINGS_ENDPOINT,
                priority=1,
                visible_in_models=False,
                supports_streaming=False,
                capabilities={"embeddings": {"embeddings": True, "embeddings_dimensions": True}},
                notes="Embeddings E2E route",
            )
            await pricing.create_pricing_rule(
                provider="openai",
                upstream_model="text-embedding-3-small",
                endpoint=EMBEDDINGS_ENDPOINT,
                valid_from=now - timedelta(days=1),
                currency="EUR",
                input_price_per_1m=Decimal("0.100000000"),
                output_price_per_1m=Decimal("0.000000000"),
                notes="Embeddings E2E pricing",
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
                    allowed_models=["classroom-embedding"],
                    allowed_endpoints=[EMBEDDINGS_ENDPOINT],
                    note="Embeddings E2E key",
                )
            )
            await session.commit()
            return created_key
    finally:
        await engine.dispose()


@pytest.mark.e2e
def test_openai_python_client_embeddings_e2e(monkeypatch: pytest.MonkeyPatch) -> None:
    database_url = _test_database_url()
    run_alembic_upgrade_head(database_url)
    _configure_runtime_environment(monkeypatch, database_url)
    created = asyncio.run(_create_embeddings_test_data(database_url))

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
            upstream_route = router.post("https://api.openai.com/v1/embeddings").mock(
                return_value=httpx.Response(
                    200,
                    json={
                        "object": "list",
                        "data": [
                            {"object": "embedding", "embedding": [0.1, 0.2], "index": 0},
                            {"object": "embedding", "embedding": [0.3, 0.4], "index": 1},
                        ],
                        "model": "text-embedding-3-small",
                        "usage": {"prompt_tokens": 4, "total_tokens": 4},
                    },
                    headers={
                        "content-type": "application/json",
                        "x-request-id": "upstream-embeddings",
                    },
                )
            )

            client = OpenAI()
            response = client.embeddings.create(
                model="classroom-embedding",
                input=["hello", "world"],
                encoding_format="float",
                dimensions=8,
                user="learner-1",
            )

    assert response.object == "list"
    assert len(response.data) == 2
    assert response.model == "text-embedding-3-small"
    assert len(upstream_route.calls) == 1

    upstream_request = upstream_route.calls[0].request
    assert upstream_request.headers["authorization"] == f"Bearer {FAKE_OPENAI_UPSTREAM_KEY}"
    assert upstream_request.headers["authorization"] != f"Bearer {created.plaintext_key}"
    upstream_body = json.loads(upstream_request.content)
    assert upstream_body == {
        "model": "text-embedding-3-small",
        "input": ["hello", "world"],
        "encoding_format": "float",
        "dimensions": 8,
        "user": "learner-1",
    }

    state = asyncio.run(_load_accounting_state(database_url, created.gateway_key_id))
    assert state.reservation.status == "finalized"
    assert state.gateway_key.requests_used_total == 1
    assert state.gateway_key.cost_used_eur > Decimal("0")
    usage_payload = json.dumps(state.usage_ledger.usage_raw, sort_keys=True)
    metadata_payload = json.dumps(state.usage_ledger.response_metadata, sort_keys=True)
    vectors_payload = json.dumps(response.model_dump(), sort_keys=True)
    for forbidden in ("hello", "world", created.plaintext_key):
        assert forbidden not in usage_payload
        assert forbidden not in metadata_payload
    assert "[0.1, 0.2]" not in usage_payload
    assert "[0.1, 0.2]" not in metadata_payload
    assert "[0.1, 0.2]" in vectors_payload
