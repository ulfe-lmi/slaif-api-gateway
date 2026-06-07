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
RESPONSES_INPUT_TOKENS_ENDPOINT = "/v1/responses/input_tokens"
INPUT_TEXT = "Hello from SLAIF Responses test"
OUTPUT_TEXT = "Hello from mocked Responses upstream"


def _sse(payload: dict[str, object]) -> str:
    return f"data: {json.dumps(payload, separators=(',', ':'))}\n\n"


async def _create_responses_test_data(
    database_url: str,
    *,
    streaming: bool = False,
    structured_outputs: bool = False,
    json_mode: bool = False,
    function_tools: bool = False,
    custom_tools: bool = False,
    image_input: bool = False,
    file_input: bool = False,
    input_token_count: bool = False,
    stored_responses: bool = False,
    previous_response_id: bool = False,
    list_input_items: bool = False,
    endpoint: str = RESPONSES_ENDPOINT,
    allowed_endpoints: list[str] | None = None,
):
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
                    PricingRule.endpoint == endpoint,
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
            capabilities["structured_outputs"] = structured_outputs
            capabilities["json_mode"] = json_mode
            capabilities["function_tools"] = function_tools
            capabilities["custom_tools"] = custom_tools
            capabilities["image_input"] = image_input
            capabilities["file_input"] = file_input
            capabilities["input_token_count"] = input_token_count
            capabilities["stored_responses"] = stored_responses
            capabilities["previous_response_id"] = previous_response_id
            capabilities["list_input_items"] = list_input_items

            await routes.create_model_route(
                requested_model=TEST_RESPONSES_MODEL,
                provider="openai",
                upstream_model=TEST_RESPONSES_MODEL,
                match_type="exact",
                endpoint=endpoint,
                priority=1,
                visible_in_models=True,
                supports_streaming=streaming,
                capabilities={"responses": capabilities},
                notes="Responses E2E route",
            )
            await pricing.create_pricing_rule(
                provider="openai",
                upstream_model=TEST_RESPONSES_MODEL,
                endpoint=endpoint,
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
                    allowed_endpoints=allowed_endpoints or [endpoint],
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
def test_openai_python_client_responses_store_retrieve_delete_e2e(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = _test_database_url()
    run_alembic_upgrade_head(database_url)
    _configure_runtime_environment(monkeypatch, database_url)
    created = asyncio.run(
        _create_responses_test_data(
            database_url,
            stored_responses=True,
            allowed_endpoints=[
                RESPONSES_ENDPOINT,
                "GET /v1/responses/{response_id}",
                "DELETE /v1/responses/{response_id}",
            ],
        )
    )

    from openai import OpenAI
    from slaif_gateway.config import get_settings
    from slaif_gateway.main import create_app

    port = _free_port()
    monkeypatch.setenv("OPENAI_API_KEY", created.plaintext_key)
    monkeypatch.setenv("OPENAI_BASE_URL", f"http://127.0.0.1:{port}/v1")

    app = create_app(get_settings())
    create_payload = {
        "id": "resp_stored_e2e",
        "object": "response",
        "created_at": 123,
        "status": "completed",
        "model": TEST_RESPONSES_MODEL,
        "output": [
            {
                "id": "msg_stored_e2e",
                "type": "message",
                "status": "completed",
                "role": "assistant",
                "content": [{"type": "output_text", "text": OUTPUT_TEXT, "annotations": []}],
            }
        ],
        "usage": {"input_tokens": 7, "output_tokens": 11, "total_tokens": 18},
        "store": True,
    }
    retrieve_payload = {
        "id": "resp_stored_e2e",
        "object": "response",
        "status": "completed",
        "model": TEST_RESPONSES_MODEL,
        "output": create_payload["output"],
        "usage": {"input_tokens": 7, "output_tokens": 11, "total_tokens": 18},
    }
    delete_payload = {"id": "resp_stored_e2e", "object": "response.deleted", "deleted": True}

    with _run_uvicorn_server(app, port):
        with respx.mock(assert_all_mocked=True, assert_all_called=True) as router:
            router.route(host="127.0.0.1").pass_through()
            create_route = router.post("https://api.openai.com/v1/responses").mock(
                return_value=httpx.Response(
                    200,
                    json=create_payload,
                    headers={"x-request-id": "upstream-openai-responses-store-e2e"},
                )
            )
            retrieve_route = router.get("https://api.openai.com/v1/responses/resp_stored_e2e").mock(
                return_value=httpx.Response(
                    200,
                    json=retrieve_payload,
                    headers={"x-request-id": "upstream-openai-responses-retrieve-e2e"},
                )
            )
            delete_route = router.delete("https://api.openai.com/v1/responses/resp_stored_e2e").mock(
                return_value=httpx.Response(
                    200,
                    json=delete_payload,
                    headers={"x-request-id": "upstream-openai-responses-delete-e2e"},
                )
            )

            client = OpenAI()
            created_response = client.responses.create(
                model=TEST_RESPONSES_MODEL,
                input=INPUT_TEXT,
                max_output_tokens=32,
                store=True,
            )
            retrieved_response = client.responses.retrieve("resp_stored_e2e")
            deleted_response = client.responses.delete("resp_stored_e2e")

    assert created_response.id == "resp_stored_e2e"
    assert retrieved_response.id == "resp_stored_e2e"
    if deleted_response is not None:
        assert deleted_response.id == "resp_stored_e2e"
        assert getattr(deleted_response, "deleted") is True
    assert create_route.called
    assert retrieve_route.called
    assert delete_route.called
    create_request = create_route.calls[0].request
    retrieve_request = retrieve_route.calls[0].request
    delete_request = delete_route.calls[0].request
    assert create_request.headers["authorization"] == f"Bearer {FAKE_OPENAI_UPSTREAM_KEY}"
    assert retrieve_request.headers["authorization"] == f"Bearer {FAKE_OPENAI_UPSTREAM_KEY}"
    assert delete_request.headers["authorization"] == f"Bearer {FAKE_OPENAI_UPSTREAM_KEY}"
    assert created.plaintext_key not in retrieve_request.headers["authorization"]
    assert json.loads(create_request.content)["store"] is True

    state = asyncio.run(_load_accounting_state(database_url, created.gateway_key_id))
    assert state.gateway_key.requests_used_total == 1
    assert state.gateway_key.tokens_used_total == 18
    assert state.usage_ledger.endpoint == RESPONSES_ENDPOINT


@pytest.mark.e2e
def test_openai_python_client_responses_previous_response_id_e2e(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = _test_database_url()
    run_alembic_upgrade_head(database_url)
    _configure_runtime_environment(monkeypatch, database_url)
    created = asyncio.run(
        _create_responses_test_data(
            database_url,
            stored_responses=True,
            previous_response_id=True,
        )
    )

    from openai import OpenAI
    from slaif_gateway.config import get_settings
    from slaif_gateway.main import create_app

    port = _free_port()
    monkeypatch.setenv("OPENAI_API_KEY", created.plaintext_key)
    monkeypatch.setenv("OPENAI_BASE_URL", f"http://127.0.0.1:{port}/v1")

    app = create_app(get_settings())
    previous_payload = {
        "id": "resp_previous_e2e",
        "object": "response",
        "created_at": 123,
        "status": "completed",
        "model": TEST_RESPONSES_MODEL,
        "output": [
            {
                "id": "msg_previous_e2e",
                "type": "message",
                "status": "completed",
                "role": "assistant",
                "content": [{"type": "output_text", "text": OUTPUT_TEXT, "annotations": []}],
            }
        ],
        "usage": {"input_tokens": 7, "output_tokens": 11, "total_tokens": 18},
        "store": True,
    }
    next_payload = {
        "id": "resp_next_e2e",
        "object": "response",
        "created_at": 124,
        "status": "completed",
        "model": TEST_RESPONSES_MODEL,
        "output": [
            {
                "id": "msg_next_e2e",
                "type": "message",
                "status": "completed",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "continued", "annotations": []}],
            }
        ],
        "usage": {"input_tokens": 5, "output_tokens": 6, "total_tokens": 11},
        "store": False,
    }

    with _run_uvicorn_server(app, port):
        with respx.mock(assert_all_mocked=True, assert_all_called=True) as router:
            router.route(host="127.0.0.1").pass_through()
            upstream_route = router.post("https://api.openai.com/v1/responses").mock(
                side_effect=[
                    httpx.Response(
                        200,
                        json=previous_payload,
                        headers={"x-request-id": "upstream-openai-responses-previous-seed"},
                    ),
                    httpx.Response(
                        200,
                        json=next_payload,
                        headers={"x-request-id": "upstream-openai-responses-previous-next"},
                    ),
                ]
            )

            client = OpenAI()
            previous_response = client.responses.create(
                model=TEST_RESPONSES_MODEL,
                input=INPUT_TEXT,
                max_output_tokens=32,
                store=True,
            )
            next_response = client.responses.create(
                model=TEST_RESPONSES_MODEL,
                input="Continue.",
                max_output_tokens=16,
                previous_response_id="resp_previous_e2e",
            )

    assert previous_response.id == "resp_previous_e2e"
    assert next_response.id == "resp_next_e2e"
    assert upstream_route.called
    assert len(upstream_route.calls) == 2
    first_body = json.loads(upstream_route.calls[0].request.content)
    second_body = json.loads(upstream_route.calls[1].request.content)
    assert first_body["store"] is True
    assert second_body == {
        "model": TEST_RESPONSES_MODEL,
        "input": "Continue.",
        "max_output_tokens": 16,
        "previous_response_id": "resp_previous_e2e",
        "store": False,
    }
    assert upstream_route.calls[1].request.headers["authorization"] == (
        f"Bearer {FAKE_OPENAI_UPSTREAM_KEY}"
    )
    assert created.plaintext_key not in upstream_route.calls[1].request.headers["authorization"]


@pytest.mark.e2e
def test_openai_python_client_responses_input_items_list_e2e(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = _test_database_url()
    run_alembic_upgrade_head(database_url)
    _configure_runtime_environment(monkeypatch, database_url)
    created = asyncio.run(
        _create_responses_test_data(
            database_url,
            stored_responses=True,
            list_input_items=True,
            allowed_endpoints=[
                RESPONSES_ENDPOINT,
                "GET /v1/responses/{response_id}/input_items",
            ],
        )
    )

    from openai import OpenAI
    from slaif_gateway.config import get_settings
    from slaif_gateway.main import create_app

    port = _free_port()
    monkeypatch.setenv("OPENAI_API_KEY", created.plaintext_key)
    monkeypatch.setenv("OPENAI_BASE_URL", f"http://127.0.0.1:{port}/v1")

    app = create_app(get_settings())
    create_payload = {
        "id": "resp_input_items_e2e",
        "object": "response",
        "created_at": 123,
        "status": "completed",
        "model": TEST_RESPONSES_MODEL,
        "output": [
            {
                "id": "msg_input_items_e2e",
                "type": "message",
                "status": "completed",
                "role": "assistant",
                "content": [{"type": "output_text", "text": OUTPUT_TEXT, "annotations": []}],
            }
        ],
        "usage": {"input_tokens": 7, "output_tokens": 11, "total_tokens": 18},
        "store": True,
    }
    input_items_payload = {
        "object": "list",
        "data": [
            {
                "id": "msg_input_item_1",
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": INPUT_TEXT}],
            }
        ],
        "first_id": "msg_input_item_1",
        "last_id": "msg_input_item_1",
        "has_more": False,
    }

    with _run_uvicorn_server(app, port):
        with respx.mock(assert_all_mocked=True, assert_all_called=True) as router:
            router.route(host="127.0.0.1").pass_through()
            create_route = router.post("https://api.openai.com/v1/responses").mock(
                return_value=httpx.Response(
                    200,
                    json=create_payload,
                    headers={"x-request-id": "upstream-openai-responses-input-items-create"},
                )
            )
            input_items_route = router.get(
                "https://api.openai.com/v1/responses/resp_input_items_e2e/input_items"
            ).mock(
                return_value=httpx.Response(
                    200,
                    json=input_items_payload,
                    headers={"x-request-id": "upstream-openai-responses-input-items-list"},
                )
            )

            client = OpenAI()
            created_response = client.responses.create(
                model=TEST_RESPONSES_MODEL,
                input=INPUT_TEXT,
                max_output_tokens=32,
                store=True,
            )
            input_items = client.responses.input_items.list(
                "resp_input_items_e2e",
                include=["message.input_image.image_url"],
                limit=25,
                order="asc",
            )

    assert created_response.id == "resp_input_items_e2e"
    assert input_items.object == "list"
    assert input_items.data[0].id == "msg_input_item_1"
    assert create_route.called
    assert input_items_route.called
    list_request = input_items_route.calls[0].request
    assert list_request.headers["authorization"] == f"Bearer {FAKE_OPENAI_UPSTREAM_KEY}"
    assert created.plaintext_key not in list_request.headers["authorization"]
    assert list_request.url.params.get("include") == "message.input_image.image_url"
    assert list_request.url.params.get("limit") == "25"
    assert list_request.url.params.get("order") == "asc"


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
def test_openai_python_client_responses_input_items_structured_e2e(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = _test_database_url()
    run_alembic_upgrade_head(database_url)
    _configure_runtime_environment(monkeypatch, database_url)
    created = asyncio.run(
        _create_responses_test_data(database_url, structured_outputs=True)
    )

    from openai import OpenAI
    from slaif_gateway.config import get_settings
    from slaif_gateway.main import create_app

    port = _free_port()
    monkeypatch.setenv("OPENAI_API_KEY", created.plaintext_key)
    monkeypatch.setenv("OPENAI_BASE_URL", f"http://127.0.0.1:{port}/v1")

    app = create_app(get_settings())
    output_text = '{"answer":"items"}'
    input_items = [
        {"role": "system", "content": "System guidance for the response."},
        {
            "role": "user",
            "content": [{"type": "input_text", "text": INPUT_TEXT}],
            "type": "message",
        },
    ]
    schema = {
        "type": "object",
        "properties": {"answer": {"type": "string"}},
        "required": ["answer"],
        "additionalProperties": False,
    }
    upstream_payload = {
        "id": "resp_items_structured_test",
        "object": "response",
        "created_at": 123,
        "status": "completed",
        "model": TEST_RESPONSES_MODEL,
        "output": [
            {
                "id": "msg_items_structured_test",
                "type": "message",
                "status": "completed",
                "role": "assistant",
                "content": [
                    {
                        "type": "output_text",
                        "text": output_text,
                        "annotations": [],
                    }
                ],
            }
        ],
        "usage": {"input_tokens": 10, "output_tokens": 12, "total_tokens": 22},
        "store": False,
    }

    with _run_uvicorn_server(app, port):
        with respx.mock(assert_all_mocked=True, assert_all_called=True) as router:
            router.route(host="127.0.0.1").pass_through()
            upstream_route = router.post("https://api.openai.com/v1/responses").mock(
                return_value=httpx.Response(
                    200,
                    json=upstream_payload,
                    headers={"x-request-id": "upstream-openai-responses-items-e2e"},
                )
            )

            client = OpenAI()
            response = client.responses.create(
                model=TEST_RESPONSES_MODEL,
                input=input_items,
                max_output_tokens=32,
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "answer_schema",
                        "schema": schema,
                        "strict": True,
                    }
                },
            )

    assert response.id == "resp_items_structured_test"
    assert response.output_text == output_text
    upstream_request = upstream_route.calls[0].request
    assert upstream_request.headers["authorization"] == f"Bearer {FAKE_OPENAI_UPSTREAM_KEY}"
    assert upstream_request.headers["authorization"] != f"Bearer {created.plaintext_key}"
    assert json.loads(upstream_request.content) == {
        "model": TEST_RESPONSES_MODEL,
        "input": input_items,
        "max_output_tokens": 32,
        "store": False,
        "text": {
            "format": {
                "type": "json_schema",
                "name": "answer_schema",
                "schema": schema,
                "strict": True,
            }
        },
    }

    state = asyncio.run(_load_accounting_state(database_url, created.gateway_key_id))
    assert state.reservation.status == "finalized"
    assert state.gateway_key.tokens_reserved_total == 0
    assert state.gateway_key.requests_used_total == 1
    assert state.gateway_key.tokens_used_total == 22
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
        output_text,
        "answer_schema",
        created.plaintext_key,
        FAKE_OPENAI_UPSTREAM_KEY,
    ):
        assert forbidden not in ledger_text


@pytest.mark.e2e
def test_openai_python_client_responses_streaming_input_items_e2e(
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
    input_items = [{"role": "user", "content": INPUT_TEXT}]
    completed_response = {
        "id": "resp_stream_items_test",
        "object": "response",
        "created_at": 123,
        "status": "completed",
        "model": TEST_RESPONSES_MODEL,
        "output": [
            {
                "id": "msg_stream_items_test",
                "type": "message",
                "status": "completed",
                "role": "assistant",
                "content": [{"type": "output_text", "text": OUTPUT_TEXT, "annotations": []}],
            }
        ],
        "usage": {"input_tokens": 7, "output_tokens": 11, "total_tokens": 18},
        "store": False,
    }
    sse = (
        _sse(
            {
                "type": "response.created",
                "sequence_number": 0,
                "response": {
                    "id": "resp_stream_items_test",
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
                "item_id": "msg_stream_items_test",
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
                        "x-request-id": "upstream-openai-responses-stream-items-e2e",
                    },
                )
            )

            client = OpenAI()
            events = list(
                client.responses.create(
                    model=TEST_RESPONSES_MODEL,
                    input=input_items,
                    max_output_tokens=32,
                    stream=True,
                )
            )

    assert [event.type for event in events] == [
        "response.created",
        "response.output_text.delta",
        "response.completed",
    ]
    assert any(getattr(event, "delta", None) == OUTPUT_TEXT for event in events)
    upstream_request = upstream_route.calls[0].request
    assert upstream_request.headers["authorization"] == f"Bearer {FAKE_OPENAI_UPSTREAM_KEY}"
    assert upstream_request.headers["authorization"] != f"Bearer {created.plaintext_key}"
    assert json.loads(upstream_request.content) == {
        "model": TEST_RESPONSES_MODEL,
        "input": input_items,
        "max_output_tokens": 32,
        "stream": True,
        "store": False,
    }

    state = asyncio.run(_load_accounting_state(database_url, created.gateway_key_id))
    assert state.reservation.status == "finalized"
    assert state.gateway_key.tokens_reserved_total == 0
    assert state.gateway_key.requests_used_total == 1
    assert state.gateway_key.tokens_used_total == 18
    assert state.usage_ledger.streaming is True


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
            assert store_exc.value.code == "responses_stored_response_capability_not_supported"
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


@pytest.mark.e2e
def test_openai_python_client_responses_structured_text_e2e(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = _test_database_url()
    run_alembic_upgrade_head(database_url)
    _configure_runtime_environment(monkeypatch, database_url)
    created = asyncio.run(
        _create_responses_test_data(database_url, structured_outputs=True)
    )

    from openai import OpenAI
    from slaif_gateway.config import get_settings
    from slaif_gateway.main import create_app

    port = _free_port()
    monkeypatch.setenv("OPENAI_API_KEY", created.plaintext_key)
    monkeypatch.setenv("OPENAI_BASE_URL", f"http://127.0.0.1:{port}/v1")

    app = create_app(get_settings())
    output_text = '{"answer":"structured"}'
    upstream_payload = {
        "id": "resp_structured_test",
        "object": "response",
        "created_at": 123,
        "status": "completed",
        "model": TEST_RESPONSES_MODEL,
        "output": [
            {
                "id": "msg_structured_test",
                "type": "message",
                "status": "completed",
                "role": "assistant",
                "content": [
                    {
                        "type": "output_text",
                        "text": output_text,
                        "annotations": [],
                    }
                ],
            }
        ],
        "usage": {
            "input_tokens": 9,
            "output_tokens": 13,
            "total_tokens": 22,
        },
        "store": False,
    }
    schema = {
        "type": "object",
        "properties": {"answer": {"type": "string"}},
        "required": ["answer"],
        "additionalProperties": False,
    }

    with _run_uvicorn_server(app, port):
        with respx.mock(assert_all_mocked=True, assert_all_called=True) as router:
            router.route(host="127.0.0.1").pass_through()
            upstream_route = router.post("https://api.openai.com/v1/responses").mock(
                return_value=httpx.Response(
                    200,
                    json=upstream_payload,
                    headers={"x-request-id": "upstream-openai-responses-structured-e2e"},
                )
            )

            client = OpenAI()
            response = client.responses.create(
                model=TEST_RESPONSES_MODEL,
                input=INPUT_TEXT,
                max_output_tokens=32,
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "answer_schema",
                        "schema": schema,
                        "strict": True,
                    }
                },
            )

    assert response.id == "resp_structured_test"
    assert response.output_text == output_text
    assert len(upstream_route.calls) == 1
    upstream_request = upstream_route.calls[0].request
    assert upstream_request.headers["authorization"] == f"Bearer {FAKE_OPENAI_UPSTREAM_KEY}"
    assert upstream_request.headers["authorization"] != f"Bearer {created.plaintext_key}"

    upstream_body = json.loads(upstream_request.content)
    assert upstream_body == {
        "model": TEST_RESPONSES_MODEL,
        "input": INPUT_TEXT,
        "max_output_tokens": 32,
        "store": False,
        "text": {
            "format": {
                "type": "json_schema",
                "name": "answer_schema",
                "schema": schema,
                "strict": True,
            }
        },
    }

    state = asyncio.run(_load_accounting_state(database_url, created.gateway_key_id))
    assert state.reservation.status == "finalized"
    assert state.gateway_key.tokens_reserved_total == 0
    assert state.gateway_key.requests_used_total == 1
    assert state.gateway_key.tokens_used_total == 22
    assert state.usage_ledger.endpoint == RESPONSES_ENDPOINT
    assert state.usage_ledger.prompt_tokens == 9
    assert state.usage_ledger.completion_tokens == 13
    assert state.usage_ledger.total_tokens == 22

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
        output_text,
        "answer_schema",
        created.plaintext_key,
        FAKE_OPENAI_UPSTREAM_KEY,
    ):
        assert forbidden not in ledger_text


@pytest.mark.e2e
def test_openai_python_client_responses_function_tool_e2e(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = _test_database_url()
    run_alembic_upgrade_head(database_url)
    _configure_runtime_environment(monkeypatch, database_url)
    created = asyncio.run(
        _create_responses_test_data(database_url, function_tools=True)
    )

    from openai import OpenAI
    from slaif_gateway.config import get_settings
    from slaif_gateway.main import create_app

    port = _free_port()
    monkeypatch.setenv("OPENAI_API_KEY", created.plaintext_key)
    monkeypatch.setenv("OPENAI_BASE_URL", f"http://127.0.0.1:{port}/v1")

    app = create_app(get_settings())
    upstream_payload = {
        "id": "resp_function_tool_test",
        "object": "response",
        "created_at": 123,
        "status": "completed",
        "model": TEST_RESPONSES_MODEL,
        "output": [
            {
                "id": "fc_function_tool_test",
                "type": "function_call",
                "call_id": "call_function_tool_test",
                "name": "lookup",
                "arguments": '{"query":"safe"}',
                "status": "completed",
            }
        ],
        "usage": {
            "input_tokens": 17,
            "output_tokens": 19,
            "total_tokens": 36,
        },
        "store": False,
    }
    tools = [
        {
            "type": "function",
            "name": "lookup",
            "description": "Local lookup intent.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
                "additionalProperties": False,
            },
            "strict": True,
        }
    ]

    with _run_uvicorn_server(app, port):
        with respx.mock(assert_all_mocked=True, assert_all_called=True) as router:
            router.route(host="127.0.0.1").pass_through()
            upstream_route = router.post("https://api.openai.com/v1/responses").mock(
                return_value=httpx.Response(
                    200,
                    json=upstream_payload,
                    headers={"x-request-id": "upstream-openai-responses-function-e2e"},
                )
            )

            client = OpenAI()
            response = client.responses.create(
                model=TEST_RESPONSES_MODEL,
                input=INPUT_TEXT,
                max_output_tokens=32,
                tools=tools,
                tool_choice={"type": "function", "name": "lookup"},
            )

    assert response.id == "resp_function_tool_test"
    assert response.output[0].type == "function_call"
    assert len(upstream_route.calls) == 1
    upstream_request = upstream_route.calls[0].request
    assert upstream_request.headers["authorization"] == f"Bearer {FAKE_OPENAI_UPSTREAM_KEY}"
    assert upstream_request.headers["authorization"] != f"Bearer {created.plaintext_key}"

    upstream_body = json.loads(upstream_request.content)
    assert upstream_body == {
        "model": TEST_RESPONSES_MODEL,
        "input": INPUT_TEXT,
        "max_output_tokens": 32,
        "store": False,
        "tools": tools,
        "tool_choice": {"type": "function", "name": "lookup"},
    }

    state = asyncio.run(_load_accounting_state(database_url, created.gateway_key_id))
    assert state.reservation.status == "finalized"
    assert state.gateway_key.tokens_reserved_total == 0
    assert state.gateway_key.requests_used_total == 1
    assert state.gateway_key.tokens_used_total == 36
    assert state.usage_ledger.endpoint == RESPONSES_ENDPOINT
    assert state.usage_ledger.prompt_tokens == 17
    assert state.usage_ledger.completion_tokens == 19
    assert state.usage_ledger.total_tokens == 36

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
        "Local lookup intent.",
        '{"query":"safe"}',
        created.plaintext_key,
        FAKE_OPENAI_UPSTREAM_KEY,
    ):
        assert forbidden not in ledger_text


@pytest.mark.e2e
def test_openai_python_client_responses_custom_tool_e2e(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = _test_database_url()
    run_alembic_upgrade_head(database_url)
    _configure_runtime_environment(monkeypatch, database_url)
    created = asyncio.run(_create_responses_test_data(database_url, custom_tools=True))

    from openai import OpenAI
    from slaif_gateway.config import get_settings
    from slaif_gateway.main import create_app

    port = _free_port()
    monkeypatch.setenv("OPENAI_API_KEY", created.plaintext_key)
    monkeypatch.setenv("OPENAI_BASE_URL", f"http://127.0.0.1:{port}/v1")

    app = create_app(get_settings())
    upstream_payload = {
        "id": "resp_custom_tool_test",
        "object": "response",
        "created_at": 123,
        "status": "completed",
        "model": TEST_RESPONSES_MODEL,
        "output": [
            {
                "id": "ct_custom_tool_test",
                "type": "custom_tool_call",
                "call_id": "call_custom_tool_test",
                "name": "draft_email",
                "input": "subject: safe",
            }
        ],
        "usage": {"input_tokens": 23, "output_tokens": 29, "total_tokens": 52},
        "store": False,
    }
    tools = [
        {
            "type": "custom",
            "name": "draft_email",
            "description": "Local drafting intent.",
            "format": {
                "type": "grammar",
                "syntax": "regex",
                "definition": r"subject: .+",
            },
        }
    ]

    with _run_uvicorn_server(app, port):
        with respx.mock(assert_all_mocked=True, assert_all_called=True) as router:
            router.route(host="127.0.0.1").pass_through()
            upstream_route = router.post("https://api.openai.com/v1/responses").mock(
                return_value=httpx.Response(
                    200,
                    json=upstream_payload,
                    headers={"x-request-id": "upstream-openai-responses-custom-e2e"},
                )
            )

            client = OpenAI()
            response = client.responses.create(
                model=TEST_RESPONSES_MODEL,
                input=INPUT_TEXT,
                max_output_tokens=32,
                tools=tools,
                tool_choice={"type": "custom", "name": "draft_email"},
            )

    assert response.id == "resp_custom_tool_test"
    assert response.output[0].type == "custom_tool_call"
    assert response.output[0].name == "draft_email"
    assert response.output[0].input == "subject: safe"
    assert len(upstream_route.calls) == 1
    upstream_request = upstream_route.calls[0].request
    assert upstream_request.headers["authorization"] == f"Bearer {FAKE_OPENAI_UPSTREAM_KEY}"
    assert upstream_request.headers["authorization"] != f"Bearer {created.plaintext_key}"
    assert json.loads(upstream_request.content) == {
        "model": TEST_RESPONSES_MODEL,
        "input": INPUT_TEXT,
        "max_output_tokens": 32,
        "store": False,
        "tools": tools,
        "tool_choice": {"type": "custom", "name": "draft_email"},
    }

    state = asyncio.run(_load_accounting_state(database_url, created.gateway_key_id))
    assert state.reservation.status == "finalized"
    assert state.gateway_key.tokens_reserved_total == 0
    assert state.gateway_key.requests_used_total == 1
    assert state.gateway_key.tokens_used_total == 52
    assert state.usage_ledger.endpoint == RESPONSES_ENDPOINT
    assert state.usage_ledger.prompt_tokens == 23
    assert state.usage_ledger.completion_tokens == 29
    assert state.usage_ledger.total_tokens == 52

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
        "Local drafting intent.",
        "subject: safe",
        created.plaintext_key,
        FAKE_OPENAI_UPSTREAM_KEY,
    ):
        assert forbidden not in ledger_text


@pytest.mark.e2e
def test_openai_python_client_responses_image_input_e2e(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = _test_database_url()
    run_alembic_upgrade_head(database_url)
    _configure_runtime_environment(monkeypatch, database_url)
    created = asyncio.run(_create_responses_test_data(database_url, image_input=True))

    from openai import OpenAI
    from slaif_gateway.config import get_settings
    from slaif_gateway.main import create_app

    port = _free_port()
    monkeypatch.setenv("OPENAI_API_KEY", created.plaintext_key)
    monkeypatch.setenv("OPENAI_BASE_URL", f"http://127.0.0.1:{port}/v1")

    app = create_app(get_settings())
    image_url = "https://example.org/slaif-e2e-image.png"
    input_items = [
        {
            "role": "user",
            "content": [
                {"type": "input_text", "text": "Describe the image."},
                {"type": "input_image", "image_url": image_url, "detail": "low"},
            ],
        }
    ]
    upstream_payload = {
        "id": "resp_image_input_test",
        "object": "response",
        "created_at": 123,
        "status": "completed",
        "model": TEST_RESPONSES_MODEL,
        "output": [
            {
                "id": "msg_image_input_test",
                "type": "message",
                "status": "completed",
                "role": "assistant",
                "content": [{"type": "output_text", "text": OUTPUT_TEXT, "annotations": []}],
            }
        ],
        "usage": {"input_tokens": 31, "output_tokens": 7, "total_tokens": 38},
        "store": False,
    }

    with _run_uvicorn_server(app, port):
        with respx.mock(assert_all_mocked=True, assert_all_called=True) as router:
            router.route(host="127.0.0.1").pass_through()
            upstream_route = router.post("https://api.openai.com/v1/responses").mock(
                return_value=httpx.Response(
                    200,
                    json=upstream_payload,
                    headers={"x-request-id": "upstream-openai-responses-image-e2e"},
                )
            )

            client = OpenAI()
            response = client.responses.create(
                model=TEST_RESPONSES_MODEL,
                input=input_items,
                max_output_tokens=32,
            )

    assert response.id == "resp_image_input_test"
    assert response.output_text == OUTPUT_TEXT
    assert len(upstream_route.calls) == 1
    upstream_request = upstream_route.calls[0].request
    assert upstream_request.headers["authorization"] == f"Bearer {FAKE_OPENAI_UPSTREAM_KEY}"
    assert upstream_request.headers["authorization"] != f"Bearer {created.plaintext_key}"
    assert json.loads(upstream_request.content) == {
        "model": TEST_RESPONSES_MODEL,
        "input": input_items,
        "max_output_tokens": 32,
        "store": False,
    }

    state = asyncio.run(_load_accounting_state(database_url, created.gateway_key_id))
    assert state.reservation.status == "finalized"
    assert state.gateway_key.requests_used_total == 1
    assert state.gateway_key.tokens_used_total == 38
    ledger_text = json.dumps(
        {
            "response_metadata": state.usage_ledger.response_metadata,
            "usage_raw": state.usage_ledger.usage_raw,
            "error_message": state.usage_ledger.error_message,
        },
        default=str,
    )
    for forbidden in (
        image_url,
        OUTPUT_TEXT,
        created.plaintext_key,
        FAKE_OPENAI_UPSTREAM_KEY,
    ):
        assert forbidden not in ledger_text


@pytest.mark.e2e
def test_openai_python_client_responses_file_input_e2e(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = _test_database_url()
    run_alembic_upgrade_head(database_url)
    _configure_runtime_environment(monkeypatch, database_url)
    created = asyncio.run(_create_responses_test_data(database_url, file_input=True))

    from openai import OpenAI
    from slaif_gateway.config import get_settings
    from slaif_gateway.main import create_app

    port = _free_port()
    monkeypatch.setenv("OPENAI_API_KEY", created.plaintext_key)
    monkeypatch.setenv("OPENAI_BASE_URL", f"http://127.0.0.1:{port}/v1")

    app = create_app(get_settings())
    file_url = "https://example.org/slaif-e2e-document.pdf"
    input_items = [
        {
            "role": "user",
            "content": [
                {"type": "input_text", "text": "Summarize the file."},
                {"type": "input_file", "file_url": file_url},
            ],
        }
    ]
    upstream_payload = {
        "id": "resp_file_input_test",
        "object": "response",
        "created_at": 123,
        "status": "completed",
        "model": TEST_RESPONSES_MODEL,
        "output": [
            {
                "id": "msg_file_input_test",
                "type": "message",
                "status": "completed",
                "role": "assistant",
                "content": [{"type": "output_text", "text": OUTPUT_TEXT, "annotations": []}],
            }
        ],
        "usage": {"input_tokens": 43, "output_tokens": 9, "total_tokens": 52},
        "store": False,
    }

    with _run_uvicorn_server(app, port):
        with respx.mock(assert_all_mocked=True, assert_all_called=True) as router:
            router.route(host="127.0.0.1").pass_through()
            upstream_route = router.post("https://api.openai.com/v1/responses").mock(
                return_value=httpx.Response(
                    200,
                    json=upstream_payload,
                    headers={"x-request-id": "upstream-openai-responses-file-e2e"},
                )
            )

            client = OpenAI()
            response = client.responses.create(
                model=TEST_RESPONSES_MODEL,
                input=input_items,
                max_output_tokens=32,
            )

    assert response.id == "resp_file_input_test"
    assert response.output_text == OUTPUT_TEXT
    assert len(upstream_route.calls) == 1
    upstream_request = upstream_route.calls[0].request
    assert upstream_request.headers["authorization"] == f"Bearer {FAKE_OPENAI_UPSTREAM_KEY}"
    assert upstream_request.headers["authorization"] != f"Bearer {created.plaintext_key}"
    assert json.loads(upstream_request.content) == {
        "model": TEST_RESPONSES_MODEL,
        "input": input_items,
        "max_output_tokens": 32,
        "store": False,
    }

    state = asyncio.run(_load_accounting_state(database_url, created.gateway_key_id))
    assert state.reservation.status == "finalized"
    assert state.gateway_key.requests_used_total == 1
    assert state.gateway_key.tokens_used_total == 52
    ledger_text = json.dumps(
        {
            "response_metadata": state.usage_ledger.response_metadata,
            "usage_raw": state.usage_ledger.usage_raw,
            "error_message": state.usage_ledger.error_message,
        },
        default=str,
    )
    for forbidden in (
        file_url,
        OUTPUT_TEXT,
        created.plaintext_key,
        FAKE_OPENAI_UPSTREAM_KEY,
    ):
        assert forbidden not in ledger_text


@pytest.mark.e2e
def test_openai_python_client_responses_input_token_count_e2e(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = _test_database_url()
    run_alembic_upgrade_head(database_url)
    _configure_runtime_environment(monkeypatch, database_url)
    created = asyncio.run(
        _create_responses_test_data(
            database_url,
            input_token_count=True,
            image_input=True,
            file_input=True,
            endpoint=RESPONSES_INPUT_TOKENS_ENDPOINT,
        )
    )

    from openai import OpenAI
    from slaif_gateway.config import get_settings
    from slaif_gateway.main import create_app

    port = _free_port()
    monkeypatch.setenv("OPENAI_API_KEY", created.plaintext_key)
    monkeypatch.setenv("OPENAI_BASE_URL", f"http://127.0.0.1:{port}/v1")

    app = create_app(get_settings())
    input_items = [
        {
            "role": "user",
            "content": [
                {"type": "input_text", "text": INPUT_TEXT},
                {"type": "input_image", "image_url": "https://example.org/count-image.png"},
                {"type": "input_file", "file_url": "https://example.org/count-file.pdf"},
            ],
        }
    ]
    with respx.mock(assert_all_mocked=True, assert_all_called=True) as router:
        router.route(host="127.0.0.1").pass_through()
        upstream_route = router.post("https://api.openai.com/v1/responses/input_tokens").mock(
            return_value=httpx.Response(
                200,
                json={"object": "response.input_tokens", "input_tokens": 321},
                headers={"OpenAI-Request-ID": "req-responses-count-e2e"},
            )
        )
        with _run_uvicorn_server(app, port):
            client = OpenAI()
            response = client.responses.input_tokens.count(
                model=TEST_RESPONSES_MODEL,
                input=input_items,
                truncation="disabled",
            )

    assert response.input_tokens == 321
    assert upstream_route.called
    upstream_request = upstream_route.calls[0].request
    assert upstream_request.headers["authorization"] == f"Bearer {FAKE_OPENAI_UPSTREAM_KEY}"
    assert upstream_request.headers["authorization"] != f"Bearer {created.plaintext_key}"
    assert json.loads(upstream_request.content) == {
        "model": TEST_RESPONSES_MODEL,
        "input": input_items,
        "truncation": "disabled",
    }
