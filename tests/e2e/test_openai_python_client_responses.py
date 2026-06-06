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

TEST_RESPONSES_MODEL = "gpt-responses-text-test"
RESPONSES_ENDPOINT = "/v1/responses"
INPUT_TEXT = "Hello from SLAIF Responses test"
OUTPUT_TEXT = "Hello from mocked Responses upstream"


def _sse(payload: dict[str, object]) -> str:
    return f"data: {json.dumps(payload, separators=(',', ':'))}\n\n"


async def _create_responses_test_data(database_url: str, *, streaming: bool = False):
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
    from slaif_gateway.services.responses_route_capabilities import default_responses_capabilities

    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    unique_id = uuid.uuid4().hex
    now = datetime.now(UTC)

    try:
        async with session_factory() as session:
            await session.execute(
                delete(ModelRoute).where(
                    ModelRoute.requested_model == TEST_RESPONSES_MODEL,
                    ModelRoute.provider == "openai",
                )
            )
            await session.execute(
                delete(PricingRule).where(
                    PricingRule.provider == "openai",
                    PricingRule.upstream_model == TEST_RESPONSES_MODEL,
                    PricingRule.endpoint == RESPONSES_ENDPOINT,
                )
            )

            institutions = InstitutionsRepository(session)
            owners = OwnersRepository(session)
            cohorts = CohortsRepository(session)
            providers = ProviderConfigsRepository(session)
            routes = ModelRoutesRepository(session)
            pricing = PricingRulesRepository(session)

            institution = await institutions.create_institution(
                name=f"SLAIF Responses E2E Institute {unique_id}",
                country="SI",
                notes="Responses E2E test data",
            )
            owner = await owners.create_owner(
                name="Responses",
                surname="Client",
                email=f"responses-client-e2e-{unique_id}@example.org",
                institution_id=institution.id,
                notes="Responses E2E owner",
            )
            cohort = await cohorts.create_cohort(
                name=f"responses-client-e2e-{unique_id}",
                description="Responses E2E cohort",
                starts_at=now - timedelta(days=1),
                ends_at=now + timedelta(days=1),
            )

            provider_config = await providers.get_provider_config_by_provider("openai")
            if provider_config is None:
                await providers.create_provider_config(
                    provider="openai",
                    display_name="OpenAI Responses E2E",
                    base_url="https://api.openai.com/v1",
                    api_key_env_var="OPENAI_UPSTREAM_API_KEY",
                    notes="E2E test provider config without secrets",
                )
            else:
                await providers.update_provider_metadata(
                    provider_config.id,
                    display_name="OpenAI Responses E2E",
                    base_url="https://api.openai.com/v1",
                    api_key_env_var="OPENAI_UPSTREAM_API_KEY",
                    notes="E2E test provider config without secrets",
                )
                await providers.set_provider_enabled(provider_config.id, enabled=True)

            capabilities = default_responses_capabilities()
            capabilities["streaming"] = streaming

            await routes.create_model_route(
                requested_model=TEST_RESPONSES_MODEL,
                provider="openai",
                upstream_model=TEST_RESPONSES_MODEL,
                match_type="exact",
                endpoint=RESPONSES_ENDPOINT,
                priority=1,
                visible_in_models=True,
                supports_streaming=streaming,
                capabilities={"responses": capabilities},
                notes="Responses E2E route",
            )
            await pricing.create_pricing_rule(
                provider="openai",
                upstream_model=TEST_RESPONSES_MODEL,
                endpoint=RESPONSES_ENDPOINT,
                valid_from=now - timedelta(days=1),
                currency="EUR",
                input_price_per_1m=Decimal("1.000000000"),
                output_price_per_1m=Decimal("1.000000000"),
                request_price=Decimal("0.000000000"),
                notes="Responses E2E pricing",
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
                    allowed_models=[TEST_RESPONSES_MODEL],
                    allowed_endpoints=[RESPONSES_ENDPOINT],
                    note="Responses E2E key",
                )
            )
            await session.commit()
            return created_key
    finally:
        await engine.dispose()


@pytest.mark.e2e
def test_openai_python_client_responses_text_e2e(monkeypatch: pytest.MonkeyPatch) -> None:
    database_url = _test_database_url()
    run_alembic_upgrade_head(database_url)
    _configure_runtime_environment(monkeypatch, database_url)
    created = asyncio.run(_create_responses_test_data(database_url))

    from openai import OpenAI
    from slaif_gateway.config import get_settings
    from slaif_gateway.main import create_app

    port = _free_port()
    monkeypatch.setenv("OPENAI_API_KEY", created.plaintext_key)
    monkeypatch.setenv("OPENAI_BASE_URL", f"http://127.0.0.1:{port}/v1")

    app = create_app(get_settings())
    upstream_payload = {
        "id": "resp_text_test",
        "object": "response",
        "created_at": 123,
        "status": "completed",
        "model": TEST_RESPONSES_MODEL,
        "output": [
            {
                "id": "msg_text_test",
                "type": "message",
                "status": "completed",
                "role": "assistant",
                "content": [
                    {
                        "type": "output_text",
                        "text": OUTPUT_TEXT,
                        "annotations": [],
                    }
                ],
            }
        ],
        "usage": {
            "input_tokens": 7,
            "output_tokens": 11,
            "total_tokens": 18,
            "input_tokens_details": {"cached_tokens": 2},
            "output_tokens_details": {"reasoning_tokens": 3},
        },
        "store": False,
    }

    with _run_uvicorn_server(app, port):
        with respx.mock(assert_all_mocked=True, assert_all_called=True) as router:
            router.route(host="127.0.0.1").pass_through()
            upstream_route = router.post("https://api.openai.com/v1/responses").mock(
                return_value=httpx.Response(
                    200,
                    json=upstream_payload,
                    headers={"x-request-id": "upstream-openai-responses-e2e"},
                )
            )

            client = OpenAI()
            response = client.responses.create(
                model=TEST_RESPONSES_MODEL,
                input=INPUT_TEXT,
                instructions="Answer briefly.",
                max_output_tokens=32,
                temperature=0.2,
                top_p=0.9,
                metadata={"course": "week-1"},
            )

    assert response.id == "resp_text_test"
    assert response.output_text == OUTPUT_TEXT
    assert len(upstream_route.calls) == 1
    upstream_request = upstream_route.calls[0].request
    assert upstream_request.headers["authorization"] == f"Bearer {FAKE_OPENAI_UPSTREAM_KEY}"
    assert upstream_request.headers["authorization"] != f"Bearer {created.plaintext_key}"

    upstream_body = json.loads(upstream_request.content)
    assert upstream_body["model"] == TEST_RESPONSES_MODEL
    assert upstream_body["input"] == INPUT_TEXT
    assert upstream_body["instructions"] == "Answer briefly."
    assert upstream_body["max_output_tokens"] == 32
    assert upstream_body["temperature"] == 0.2
    assert upstream_body["top_p"] == 0.9
    assert upstream_body["metadata"] == {"course": "week-1"}
    assert upstream_body["store"] is False

    state = asyncio.run(_load_accounting_state(database_url, created.gateway_key_id))
    assert state.reservation.status == "finalized"
    assert state.gateway_key.tokens_reserved_total == 0
    assert state.gateway_key.requests_used_total == 1
    assert state.gateway_key.tokens_used_total == 18
    assert state.usage_ledger.endpoint == RESPONSES_ENDPOINT
    assert state.usage_ledger.provider == "openai"
    assert state.usage_ledger.requested_model == TEST_RESPONSES_MODEL
    assert state.usage_ledger.resolved_model == TEST_RESPONSES_MODEL
    assert state.usage_ledger.prompt_tokens == 7
    assert state.usage_ledger.completion_tokens == 11
    assert state.usage_ledger.total_tokens == 18

    ledger_text = json.dumps(
        {
            "response_metadata": state.usage_ledger.response_metadata,
            "usage_raw": state.usage_ledger.usage_raw,
            "error_message": state.usage_ledger.error_message,
        },
        default=str,
    )
    for forbidden in (
        INPUT_TEXT,
        OUTPUT_TEXT,
        created.plaintext_key,
        FAKE_OPENAI_UPSTREAM_KEY,
    ):
        assert forbidden not in ledger_text


@pytest.mark.e2e
def test_openai_python_client_responses_streaming_text_e2e(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = _test_database_url()
    run_alembic_upgrade_head(database_url)
    _configure_runtime_environment(monkeypatch, database_url)
    created = asyncio.run(_create_responses_test_data(database_url, streaming=True))

    from openai import OpenAI
    from slaif_gateway.config import get_settings
    from slaif_gateway.main import create_app

    port = _free_port()
    monkeypatch.setenv("OPENAI_API_KEY", created.plaintext_key)
    monkeypatch.setenv("OPENAI_BASE_URL", f"http://127.0.0.1:{port}/v1")

    app = create_app(get_settings())
    completed_response = {
        "id": "resp_stream_test",
        "object": "response",
        "created_at": 123,
        "status": "completed",
        "model": TEST_RESPONSES_MODEL,
        "output": [
            {
                "id": "msg_stream_test",
                "type": "message",
                "status": "completed",
                "role": "assistant",
                "content": [
                    {
                        "type": "output_text",
                        "text": OUTPUT_TEXT,
                        "annotations": [],
                    }
                ],
            }
        ],
        "usage": {
            "input_tokens": 7,
            "output_tokens": 11,
            "total_tokens": 18,
            "input_tokens_details": {"cached_tokens": 2},
            "output_tokens_details": {"reasoning_tokens": 3},
        },
        "store": False,
    }
    sse = (
        _sse(
            {
                "type": "response.created",
                "sequence_number": 0,
                "response": {
                    "id": "resp_stream_test",
                    "object": "response",
                    "created_at": 123,
                    "status": "in_progress",
                    "model": TEST_RESPONSES_MODEL,
                },
            }
        )
        + _sse(
            {
                "type": "response.output_text.delta",
                "sequence_number": 1,
                "item_id": "msg_stream_test",
                "output_index": 0,
                "content_index": 0,
                "delta": OUTPUT_TEXT,
            }
        )
        + _sse(
            {
                "type": "response.completed",
                "sequence_number": 2,
                "response": completed_response,
            }
        )
    )

    with _run_uvicorn_server(app, port):
        with respx.mock(assert_all_mocked=True, assert_all_called=True) as router:
            router.route(host="127.0.0.1").pass_through()
            upstream_route = router.post("https://api.openai.com/v1/responses").mock(
                return_value=httpx.Response(
                    200,
                    content=sse.encode(),
                    headers={
                        "content-type": "text/event-stream",
                        "x-request-id": "upstream-openai-responses-stream-e2e",
                    },
                )
            )

            client = OpenAI()
            stream = client.responses.create(
                model=TEST_RESPONSES_MODEL,
                input=INPUT_TEXT,
                max_output_tokens=32,
                stream=True,
            )
            events = list(stream)

    event_types = [event.type for event in events]
    assert event_types == [
        "response.created",
        "response.output_text.delta",
        "response.completed",
    ]
    deltas = [getattr(event, "delta", None) for event in events]
    assert OUTPUT_TEXT in deltas

    completed_events = [event for event in events if event.type == "response.completed"]
    assert completed_events
    assert completed_events[0].response.id == "resp_stream_test"
    assert completed_events[0].response.usage.total_tokens == 18

    assert len(upstream_route.calls) == 1
    upstream_request = upstream_route.calls[0].request
    assert upstream_request.headers["authorization"] == f"Bearer {FAKE_OPENAI_UPSTREAM_KEY}"
    assert upstream_request.headers["authorization"] != f"Bearer {created.plaintext_key}"
    upstream_body = json.loads(upstream_request.content)
    assert upstream_body == {
        "model": TEST_RESPONSES_MODEL,
        "input": INPUT_TEXT,
        "max_output_tokens": 32,
        "stream": True,
        "store": False,
    }

    state = asyncio.run(_load_accounting_state(database_url, created.gateway_key_id))
    assert state.reservation.status == "finalized"
    assert state.gateway_key.tokens_reserved_total == 0
    assert state.gateway_key.requests_used_total == 1
    assert state.gateway_key.tokens_used_total == 18
    assert state.usage_ledger.endpoint == RESPONSES_ENDPOINT
    assert state.usage_ledger.streaming is True
    assert state.usage_ledger.provider == "openai"
    assert state.usage_ledger.prompt_tokens == 7
    assert state.usage_ledger.completion_tokens == 11
    assert state.usage_ledger.total_tokens == 18

    ledger_text = json.dumps(
        {
            "response_metadata": state.usage_ledger.response_metadata,
            "usage_raw": state.usage_ledger.usage_raw,
            "error_message": state.usage_ledger.error_message,
        },
        default=str,
    )
    for forbidden in (
        INPUT_TEXT,
        OUTPUT_TEXT,
        created.plaintext_key,
        FAKE_OPENAI_UPSTREAM_KEY,
    ):
        assert forbidden not in ledger_text


@pytest.mark.e2e
def test_openai_python_client_responses_rejects_store_and_stream_without_upstream(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = _test_database_url()
    run_alembic_upgrade_head(database_url)
    _configure_runtime_environment(monkeypatch, database_url)
    created = asyncio.run(_create_responses_test_data(database_url))

    from openai import BadRequestError, OpenAI
    from slaif_gateway.config import get_settings
    from slaif_gateway.main import create_app

    port = _free_port()
    monkeypatch.setenv("OPENAI_API_KEY", created.plaintext_key)
    monkeypatch.setenv("OPENAI_BASE_URL", f"http://127.0.0.1:{port}/v1")

    app = create_app(get_settings())

    with _run_uvicorn_server(app, port):
        with respx.mock(assert_all_mocked=False, assert_all_called=False) as router:
            router.route(host="127.0.0.1").pass_through()
            upstream_route = router.post("https://api.openai.com/v1/responses").mock(
                return_value=httpx.Response(500, json={"error": {"message": "should not be called"}})
            )
            client = OpenAI()

            with pytest.raises(BadRequestError) as store_exc:
                client.responses.create(
                    model=TEST_RESPONSES_MODEL,
                    input=INPUT_TEXT,
                    store=True,
                )
            assert store_exc.value.code == "responses_store_not_supported"
            assert INPUT_TEXT not in str(store_exc.value)

            with pytest.raises(BadRequestError) as stream_exc:
                client.responses.create(
                    model=TEST_RESPONSES_MODEL,
                    input=INPUT_TEXT,
                    stream=True,
                )
            assert stream_exc.value.code == "responses_route_capability_not_supported"
            assert INPUT_TEXT not in str(stream_exc.value)

    assert upstream_route.calls == []
