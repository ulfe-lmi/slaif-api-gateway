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
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
import pytest
import respx
import uvicorn
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from tests.integration.db_test_utils import run_alembic_upgrade_head

TEST_MODEL = "gpt-test-mini"
PROMPT_TEXT = "Hello from SLAIF test"
COMPLETION_TEXT = "Hello from mocked upstream"
FAKE_OPENAI_UPSTREAM_KEY = "fake-openai-upstream-key"
FAKE_OPENROUTER_UPSTREAM_KEY = "fake-openrouter-upstream-key"
TEST_HMAC_SECRET = "test-hmac-secret-for-openai-client-e2e-123456"
TEST_ADMIN_SECRET = "test-admin-secret-for-openai-client-e2e-123456"
TEST_ONE_TIME_SECRET_KEY = "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY"
CHAT_COMPLETIONS_ENDPOINT = "/v1/chat/completions"


@dataclass(frozen=True, slots=True)
class CreatedE2EData:
    plaintext_gateway_key: str
    gateway_key_id: uuid.UUID
    public_key_id: str


@dataclass(frozen=True, slots=True)
class AccountingState:
    gateway_key: object
    reservation: object
    usage_ledger: object
    one_time_secret: object
    provider_config: object


def _test_database_url() -> str:
    database_url = os.getenv("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("TEST_DATABASE_URL is required for OpenAI Python client E2E test")
    return database_url


def _configure_runtime_environment(monkeypatch: pytest.MonkeyPatch, database_url: str) -> None:
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("GATEWAY_KEY_PREFIX", "sk-slaif-")
    monkeypatch.setenv("GATEWAY_KEY_ACCEPTED_PREFIXES", "sk-slaif-")
    monkeypatch.setenv("ACTIVE_HMAC_KEY_VERSION", "1")
    monkeypatch.setenv("TOKEN_HMAC_SECRET_V1", TEST_HMAC_SECRET)
    monkeypatch.setenv("ADMIN_SESSION_SECRET", TEST_ADMIN_SECRET)
    monkeypatch.setenv("ONE_TIME_SECRET_ENCRYPTION_KEY", TEST_ONE_TIME_SECRET_KEY)
    monkeypatch.setenv("OPENAI_UPSTREAM_API_KEY", FAKE_OPENAI_UPSTREAM_KEY)
    monkeypatch.setenv("OPENROUTER_API_KEY", FAKE_OPENROUTER_UPSTREAM_KEY)

    from slaif_gateway.config import get_settings

    get_settings.cache_clear()


async def _create_test_data(
    database_url: str,
    *,
    provider: str = "openai",
    model: str = TEST_MODEL,
    allowed_models: list[str] | None = None,
    allowed_endpoints: list[str] | None = None,
    base_url: str = "https://api.openai.com/v1",
    api_key_env_var: str = "OPENAI_UPSTREAM_API_KEY",
    owner_label: str = "OpenAI",
) -> CreatedE2EData:
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
    display_name = f"{owner_label} E2E"
    notes_prefix = f"{owner_label} Python client E2E test"

    try:
        async with session_factory() as session:
            await session.execute(
                delete(ModelRoute).where(
                    ModelRoute.requested_model == model,
                    ModelRoute.provider == provider,
                )
            )
            await session.execute(
                delete(PricingRule).where(
                    PricingRule.provider == provider,
                    PricingRule.upstream_model == model,
                    PricingRule.endpoint == CHAT_COMPLETIONS_ENDPOINT,
                )
            )

            institutions = InstitutionsRepository(session)
            owners = OwnersRepository(session)
            cohorts = CohortsRepository(session)
            providers = ProviderConfigsRepository(session)
            routes = ModelRoutesRepository(session)
            pricing = PricingRulesRepository(session)

            institution = await institutions.create_institution(
                name=f"SLAIF {owner_label} E2E Institute {unique_id}",
                country="SI",
                notes=f"{notes_prefix} data",
            )
            owner = await owners.create_owner(
                name=owner_label,
                surname="Client",
                email=f"{provider}-client-e2e-{unique_id}@example.org",
                institution_id=institution.id,
                notes=f"{notes_prefix} owner",
            )
            cohort = await cohorts.create_cohort(
                name=f"{provider}-client-e2e-{unique_id}",
                description=f"{notes_prefix} cohort",
                starts_at=now - timedelta(days=1),
                ends_at=now + timedelta(days=1),
            )

            provider_config = await providers.get_provider_config_by_provider(provider)
            if provider_config is None:
                await providers.create_provider_config(
                    provider=provider,
                    display_name=display_name,
                    base_url=base_url,
                    api_key_env_var=api_key_env_var,
                    notes="E2E test provider config without secrets",
                )
            else:
                await providers.update_provider_metadata(
                    provider_config.id,
                    display_name=display_name,
                    base_url=base_url,
                    api_key_env_var=api_key_env_var,
                    notes="E2E test provider config without secrets",
                )
                await providers.set_provider_enabled(provider_config.id, enabled=True)

            await routes.create_model_route(
                requested_model=model,
                provider=provider,
                upstream_model=model,
                match_type="exact",
                endpoint=CHAT_COMPLETIONS_ENDPOINT,
                priority=1,
                visible_in_models=True,
                supports_streaming=False,
                notes=f"{notes_prefix} route",
            )
            await pricing.create_pricing_rule(
                provider=provider,
                upstream_model=model,
                endpoint=CHAT_COMPLETIONS_ENDPOINT,
                valid_from=now - timedelta(days=1),
                currency="EUR",
                input_price_per_1m=Decimal("1.000000000"),
                output_price_per_1m=Decimal("1.000000000"),
                request_price=Decimal("0.000000000"),
                notes=f"{notes_prefix} pricing",
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
                    allowed_models=[model] if allowed_models is None else allowed_models,
                    allowed_endpoints=[CHAT_COMPLETIONS_ENDPOINT]
                    if allowed_endpoints is None
                    else allowed_endpoints,
                    note=f"{notes_prefix} key",
                )
            )
            await session.commit()
            return CreatedE2EData(
                plaintext_gateway_key=created_key.plaintext_key,
                gateway_key_id=created_key.gateway_key_id,
                public_key_id=created_key.public_key_id,
            )
    finally:
        await engine.dispose()


async def _load_accounting_state(
    database_url: str,
    gateway_key_id: uuid.UUID,
    *,
    provider: str = "openai",
) -> AccountingState:
    from slaif_gateway.db.models import (
        GatewayKey,
        OneTimeSecret,
        ProviderConfig,
        QuotaReservation,
        UsageLedger,
    )

    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with session_factory() as session:
            gateway_key = await session.get(GatewayKey, gateway_key_id)
            reservation = (
                await session.execute(
                    select(QuotaReservation)
                    .where(QuotaReservation.gateway_key_id == gateway_key_id)
                    .order_by(QuotaReservation.created_at.desc())
                    .limit(1)
                )
            ).scalar_one()
            usage_ledger = (
                await session.execute(
                    select(UsageLedger)
                    .where(UsageLedger.gateway_key_id == gateway_key_id)
                    .order_by(UsageLedger.created_at.desc())
                    .limit(1)
                )
            ).scalar_one()
            one_time_secret = (
                await session.execute(
                    select(OneTimeSecret)
                    .where(OneTimeSecret.gateway_key_id == gateway_key_id)
                    .order_by(OneTimeSecret.created_at.desc())
                    .limit(1)
                )
            ).scalar_one()
            provider_config = (
                await session.execute(
                    select(ProviderConfig).where(ProviderConfig.provider == provider)
                )
            ).scalar_one()
            return AccountingState(
                gateway_key=gateway_key,
                reservation=reservation,
                usage_ledger=usage_ledger,
                one_time_secret=one_time_secret,
                provider_config=provider_config,
            )
    finally:
        await engine.dispose()


async def _load_accounting_side_effect_counts(
    database_url: str,
    gateway_key_id: uuid.UUID,
) -> tuple[int, int]:
    from slaif_gateway.db.models import QuotaReservation, UsageLedger

    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with session_factory() as session:
            reservation_count = (
                await session.execute(
                    select(func.count())
                    .select_from(QuotaReservation)
                    .where(QuotaReservation.gateway_key_id == gateway_key_id)
                )
            ).scalar_one()
            usage_ledger_count = (
                await session.execute(
                    select(func.count())
                    .select_from(UsageLedger)
                    .where(UsageLedger.gateway_key_id == gateway_key_id)
                )
            ).scalar_one()
            return int(reservation_count), int(usage_ledger_count)
    finally:
        await engine.dispose()


def _free_port() -> int:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@contextmanager
def _run_uvicorn_server(app, port: int) -> Iterator[None]:
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

    try:
        deadline = time.monotonic() + 10
        while not server.started:
            if not thread.is_alive():
                raise RuntimeError("Uvicorn server thread exited before startup")
            if time.monotonic() > deadline:
                raise TimeoutError("Timed out waiting for Uvicorn server startup")
            time.sleep(0.05)
        yield
    finally:
        server.should_exit = True
        thread.join(timeout=10)


@pytest.mark.e2e
def test_openai_python_client_chat_completions_env_e2e(monkeypatch: pytest.MonkeyPatch) -> None:
    database_url = _test_database_url()
    run_alembic_upgrade_head(database_url)
    _configure_runtime_environment(monkeypatch, database_url)
    created = asyncio.run(_create_test_data(database_url))

    from openai import OpenAI
    from slaif_gateway.config import get_settings
    from slaif_gateway.main import create_app

    port = _free_port()
    monkeypatch.setenv("OPENAI_API_KEY", created.plaintext_gateway_key)
    monkeypatch.setenv("OPENAI_BASE_URL", f"http://127.0.0.1:{port}/v1")

    app = create_app(get_settings())
    upstream_payload = {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "created": 123,
        "model": TEST_MODEL,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": COMPLETION_TEXT},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 5, "completion_tokens": 6, "total_tokens": 11},
    }

    with _run_uvicorn_server(app, port):
        with respx.mock(assert_all_mocked=True, assert_all_called=True) as router:
            router.route(host="127.0.0.1").pass_through()
            upstream_route = router.post("https://api.openai.com/v1/chat/completions").mock(
                return_value=httpx.Response(
                    200,
                    json=upstream_payload,
                    headers={"x-request-id": "upstream-openai-e2e"},
                )
            )

            client = OpenAI()
            response = client.chat.completions.create(
                model=TEST_MODEL,
                messages=[{"role": "user", "content": PROMPT_TEXT}],
                temperature=0.2,
                top_p=0.9,
                stop=["STOP"],
                user="student-1",
                seed=123,
                tools=[{"type": "function", "function": {"name": "lookup"}}],
                tool_choice="auto",
                response_format={"type": "json_object"},
                extra_body={
                    "metadata": {"course": "week-1"},
                    "x_unknown_json_compatible": {"preserved": True},
                },
            )

    assert response.choices[0].message.content == COMPLETION_TEXT
    assert len(upstream_route.calls) == 1
    upstream_request = upstream_route.calls[0].request
    assert upstream_request.headers["authorization"] == f"Bearer {FAKE_OPENAI_UPSTREAM_KEY}"
    assert upstream_request.headers["authorization"] != f"Bearer {created.plaintext_gateway_key}"

    upstream_body = json.loads(upstream_request.content)
    assert upstream_body["model"] == TEST_MODEL
    assert upstream_body["max_completion_tokens"] == get_settings().DEFAULT_MAX_OUTPUT_TOKENS
    assert upstream_body["temperature"] == 0.2
    assert upstream_body["top_p"] == 0.9
    assert upstream_body["stop"] == ["STOP"]
    assert upstream_body["user"] == "student-1"
    assert upstream_body["seed"] == 123
    assert upstream_body["tools"][0]["function"]["name"] == "lookup"
    assert upstream_body["tool_choice"] == "auto"
    assert upstream_body["response_format"] == {"type": "json_object"}
    assert upstream_body["metadata"] == {"course": "week-1"}
    assert upstream_body["x_unknown_json_compatible"] == {"preserved": True}
    assert PROMPT_TEXT in json.dumps(upstream_body)

    state = asyncio.run(_load_accounting_state(database_url, created.gateway_key_id))

    assert state.reservation.status == "finalized"
    assert state.reservation.finalized_at is not None
    assert state.gateway_key.cost_reserved_eur == Decimal("0E-9")
    assert state.gateway_key.tokens_reserved_total == 0
    assert state.gateway_key.requests_reserved_total == 0
    assert state.gateway_key.tokens_used_total == 11
    assert state.gateway_key.requests_used_total == 1
    assert state.gateway_key.cost_used_eur >= Decimal("0")

    assert state.usage_ledger.provider == "openai"
    assert state.usage_ledger.requested_model == TEST_MODEL
    assert state.usage_ledger.resolved_model == TEST_MODEL
    assert state.usage_ledger.prompt_tokens == 5
    assert state.usage_ledger.completion_tokens == 6
    assert state.usage_ledger.total_tokens == 11
    assert state.usage_ledger.accounting_status == "finalized"
    assert state.usage_ledger.success is True
    assert state.usage_ledger.quota_reservation_id == state.reservation.id

    usage_payload = json.dumps(state.usage_ledger.usage_raw, sort_keys=True)
    metadata_payload = json.dumps(state.usage_ledger.response_metadata, sort_keys=True)
    assert PROMPT_TEXT not in usage_payload
    assert COMPLETION_TEXT not in usage_payload
    assert PROMPT_TEXT not in metadata_payload
    assert COMPLETION_TEXT not in metadata_payload

    assert state.gateway_key.public_key_id == created.public_key_id
    assert state.gateway_key.token_hash != created.plaintext_gateway_key
    assert created.plaintext_gateway_key not in state.gateway_key.token_hash
    assert created.plaintext_gateway_key not in (state.gateway_key.key_hint or "")
    assert created.plaintext_gateway_key not in state.one_time_secret.encrypted_payload
    assert created.plaintext_gateway_key not in state.one_time_secret.nonce

    provider_config_text = json.dumps(
        {
            "provider": state.provider_config.provider,
            "display_name": state.provider_config.display_name,
            "kind": state.provider_config.kind,
            "base_url": state.provider_config.base_url,
            "api_key_env_var": state.provider_config.api_key_env_var,
            "notes": state.provider_config.notes,
        },
        sort_keys=True,
    )
    assert FAKE_OPENAI_UPSTREAM_KEY not in provider_config_text
    assert state.provider_config.api_key_env_var == "OPENAI_UPSTREAM_API_KEY"


@pytest.mark.e2e
def test_openai_python_client_models_list_empty_for_no_allowed_models(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = _test_database_url()
    run_alembic_upgrade_head(database_url)
    _configure_runtime_environment(monkeypatch, database_url)
    created = asyncio.run(
        _create_test_data(database_url, allowed_models=[], allowed_endpoints=["/v1/models"])
    )

    from openai import OpenAI
    from slaif_gateway.config import get_settings
    from slaif_gateway.main import create_app

    port = _free_port()
    monkeypatch.setenv("OPENAI_API_KEY", created.plaintext_gateway_key)
    monkeypatch.setenv("OPENAI_BASE_URL", f"http://127.0.0.1:{port}/v1")

    app = create_app(get_settings())

    with _run_uvicorn_server(app, port):
        with respx.mock(assert_all_mocked=True, assert_all_called=False) as router:
            router.route(host="127.0.0.1").pass_through()

            client = OpenAI()
            models = client.models.list()

    assert models.object == "list"
    assert models.data == []


@pytest.mark.e2e
def test_openai_python_client_rejects_multi_choice_chat_before_upstream(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = _test_database_url()
    run_alembic_upgrade_head(database_url)
    _configure_runtime_environment(monkeypatch, database_url)
    created = asyncio.run(_create_test_data(database_url))

    from openai import BadRequestError, OpenAI
    from slaif_gateway.config import get_settings
    from slaif_gateway.main import create_app

    port = _free_port()
    monkeypatch.setenv("OPENAI_API_KEY", created.plaintext_gateway_key)
    monkeypatch.setenv("OPENAI_BASE_URL", f"http://127.0.0.1:{port}/v1")

    app = create_app(get_settings())

    with _run_uvicorn_server(app, port):
        with respx.mock(assert_all_mocked=True, assert_all_called=False) as router:
            router.route(host="127.0.0.1").pass_through()
            upstream_route = router.post("https://api.openai.com/v1/chat/completions").mock(
                return_value=httpx.Response(
                    500,
                    json={"error": {"message": "upstream should not be called"}},
                )
            )

            client = OpenAI()
            with pytest.raises(BadRequestError) as exc_info:
                client.chat.completions.create(
                    model=TEST_MODEL,
                    messages=[{"role": "user", "content": PROMPT_TEXT}],
                    n=2,
                )

    error = exc_info.value
    assert error.status_code == 400
    assert error.body is not None
    assert error.body["code"] == "invalid_choice_count"
    assert error.body["param"] == "n"
    assert "multi-choice quota accounting" in error.body["message"]
    assert len(upstream_route.calls) == 0

    reservation_count, usage_ledger_count = asyncio.run(
        _load_accounting_side_effect_counts(database_url, created.gateway_key_id)
    )
    assert reservation_count == 0
    assert usage_ledger_count == 0
