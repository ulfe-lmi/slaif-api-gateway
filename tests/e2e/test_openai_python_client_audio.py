from __future__ import annotations

import asyncio
import json
import tempfile
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

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

SPEECH_ENDPOINT = "/v1/audio/speech"
TRANSCRIPTIONS_ENDPOINT = "/v1/audio/transcriptions"
TRANSLATIONS_ENDPOINT = "/v1/audio/translations"


async def _create_audio_test_data(
    database_url: str,
    *,
    endpoint: str,
    requested_model: str,
    resolved_model: str,
    capability_key: str,
    request_price: Decimal,
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

    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    unique_id = uuid.uuid4().hex
    now = datetime.now(UTC)

    try:
        async with session_factory() as session:
            await session.execute(
                delete(ModelRoute).where(
                    ModelRoute.requested_model == requested_model,
                    ModelRoute.provider == "openai",
                    ModelRoute.endpoint == endpoint,
                )
            )
            await session.execute(
                delete(PricingRule).where(
                    PricingRule.provider == "openai",
                    PricingRule.upstream_model == resolved_model,
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
                name=f"SLAIF Audio E2E Institute {unique_id}",
                country="SI",
                notes="Audio E2E test data",
            )
            owner = await owners.create_owner(
                name="Audio",
                surname="Client",
                email=f"audio-client-e2e-{unique_id}@example.org",
                institution_id=institution.id,
                notes="Audio E2E owner",
            )
            cohort = await cohorts.create_cohort(
                name=f"audio-client-e2e-{unique_id}",
                description="Audio E2E cohort",
                starts_at=now - timedelta(days=1),
                ends_at=now + timedelta(days=1),
            )

            provider_config = await providers.get_provider_config_by_provider("openai")
            if provider_config is None:
                await providers.create_provider_config(
                    provider="openai",
                    display_name="OpenAI Audio E2E",
                    base_url="https://api.openai.com/v1",
                    api_key_env_var="OPENAI_UPSTREAM_API_KEY",
                    notes="Audio E2E test provider config without secrets",
                )
            else:
                await providers.update_provider_metadata(
                    provider_config.id,
                    display_name="OpenAI Audio E2E",
                    base_url="https://api.openai.com/v1",
                    api_key_env_var="OPENAI_UPSTREAM_API_KEY",
                    notes="Audio E2E test provider config without secrets",
                )
                await providers.set_provider_enabled(provider_config.id, enabled=True)

            await routes.create_model_route(
                requested_model=requested_model,
                provider="openai",
                upstream_model=resolved_model,
                match_type="exact",
                endpoint=endpoint,
                priority=1,
                visible_in_models=False,
                supports_streaming=False,
                capabilities={"audio_endpoints": {capability_key: True}},
                notes="Audio E2E route",
            )
            await pricing.create_pricing_rule(
                provider="openai",
                upstream_model=resolved_model,
                endpoint=endpoint,
                valid_from=now - timedelta(days=1),
                currency="EUR",
                input_price_per_1m=Decimal("1.000000000"),
                output_price_per_1m=Decimal("0.000000000"),
                request_price=request_price,
                notes="Audio E2E pricing",
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
                    allowed_models=[requested_model],
                    allowed_endpoints=[endpoint],
                    note="Audio E2E key",
                )
            )
            await session.commit()
            return created_key
    finally:
        await engine.dispose()


@pytest.mark.e2e
def test_openai_python_client_audio_speech_e2e(monkeypatch: pytest.MonkeyPatch) -> None:
    database_url = _test_database_url()
    run_alembic_upgrade_head(database_url)
    _configure_runtime_environment(monkeypatch, database_url)
    created = asyncio.run(
        _create_audio_test_data(
            database_url,
            endpoint=SPEECH_ENDPOINT,
            requested_model="classroom-audio-speech",
            resolved_model="gpt-4o-mini-tts",
            capability_key="audio_speech",
            request_price=Decimal("0.004000000"),
        )
    )

    from openai import OpenAI
    from slaif_gateway.config import get_settings
    from slaif_gateway.main import create_app

    port = _free_port()
    monkeypatch.setenv("OPENAI_API_KEY", created.plaintext_key)
    monkeypatch.setenv("OPENAI_BASE_URL", f"http://127.0.0.1:{port}/v1")

    app = create_app(get_settings())
    speech_text = "Please read this aloud."

    with _run_uvicorn_server(app, port):
        with respx.mock(assert_all_mocked=True, assert_all_called=True) as router:
            router.route(host="127.0.0.1").pass_through()
            upstream_route = router.post("https://api.openai.com/v1/audio/speech").mock(
                return_value=httpx.Response(
                    200,
                    content=b"speech-audio",
                    headers={
                        "content-type": "audio/aac",
                        "content-length": "12",
                        "x-request-id": "upstream-audio-speech",
                    },
                )
            )

            client = OpenAI()
            response = client.audio.speech.create(
                model="classroom-audio-speech",
                voice="alloy",
                input=speech_text,
                response_format="aac",
                instructions="Calm narration",
                speed=1.1,
            )

    assert response.content == b"speech-audio"
    assert len(upstream_route.calls) == 1
    upstream_request = upstream_route.calls[0].request
    assert upstream_request.headers["authorization"] == f"Bearer {FAKE_OPENAI_UPSTREAM_KEY}"
    assert upstream_request.headers["authorization"] != f"Bearer {created.plaintext_key}"
    upstream_body = json.loads(upstream_request.content)
    assert upstream_body == {
        "model": "gpt-4o-mini-tts",
        "input": speech_text,
        "voice": "alloy",
        "response_format": "aac",
        "instructions": "Calm narration",
        "speed": 1.1,
    }

    state = asyncio.run(_load_accounting_state(database_url, created.gateway_key_id))
    assert state.reservation.status == "finalized"
    assert state.gateway_key.requests_used_total == 1
    assert state.gateway_key.cost_used_eur > Decimal("0")
    usage_payload = json.dumps(state.usage_ledger.usage_raw, sort_keys=True)
    metadata_payload = json.dumps(state.usage_ledger.response_metadata, sort_keys=True)
    for forbidden in (speech_text, "Calm narration", created.plaintext_key):
        assert forbidden not in usage_payload
        assert forbidden not in metadata_payload


@pytest.mark.e2e
def test_openai_python_client_audio_transcription_e2e(monkeypatch: pytest.MonkeyPatch) -> None:
    database_url = _test_database_url()
    run_alembic_upgrade_head(database_url)
    _configure_runtime_environment(monkeypatch, database_url)
    created = asyncio.run(
        _create_audio_test_data(
            database_url,
            endpoint=TRANSCRIPTIONS_ENDPOINT,
            requested_model="classroom-audio-transcription",
            resolved_model="gpt-4o-transcribe",
            capability_key="audio_transcriptions",
            request_price=Decimal("0.006000000"),
        )
    )

    from openai import OpenAI
    from slaif_gateway.config import get_settings
    from slaif_gateway.main import create_app

    port = _free_port()
    monkeypatch.setenv("OPENAI_API_KEY", created.plaintext_key)
    monkeypatch.setenv("OPENAI_BASE_URL", f"http://127.0.0.1:{port}/v1")

    app = create_app(get_settings())
    prompt_text = "Short safe hint"

    with tempfile.NamedTemporaryFile(suffix=".wav") as tmp:
        tmp.write(b"RIFFfake-audio")
        tmp.flush()

        with _run_uvicorn_server(app, port):
            with respx.mock(assert_all_mocked=True, assert_all_called=True) as router:
                router.route(host="127.0.0.1").pass_through()
                upstream_route = router.post("https://api.openai.com/v1/audio/transcriptions").mock(
                    return_value=httpx.Response(
                        200,
                        text="hello transcript",
                        headers={"content-type": "text/plain; charset=utf-8"},
                    )
                )

                client = OpenAI()
                response = client.audio.transcriptions.create(
                    model="classroom-audio-transcription",
                    file=Path(tmp.name),
                    prompt=prompt_text,
                    response_format="text",
                    temperature=0.2,
                )

    assert response == "hello transcript"
    assert len(upstream_route.calls) == 1
    upstream_request = upstream_route.calls[0].request
    assert upstream_request.headers["authorization"] == f"Bearer {FAKE_OPENAI_UPSTREAM_KEY}"
    assert upstream_request.headers["authorization"] != f"Bearer {created.plaintext_key}"
    multipart_text = upstream_request.content.decode("utf-8", errors="ignore")
    assert 'name="model"' in multipart_text
    assert "gpt-4o-transcribe" in multipart_text
    assert 'name="prompt"' in multipart_text
    assert prompt_text in multipart_text

    state = asyncio.run(_load_accounting_state(database_url, created.gateway_key_id))
    assert state.reservation.status == "finalized"
    assert state.gateway_key.requests_used_total == 1
    assert state.gateway_key.cost_used_eur > Decimal("0")
    usage_payload = json.dumps(state.usage_ledger.usage_raw, sort_keys=True)
    metadata_payload = json.dumps(state.usage_ledger.response_metadata, sort_keys=True)
    for forbidden in (prompt_text, "hello transcript", Path(tmp.name).name, created.plaintext_key):
        assert forbidden not in usage_payload
        assert forbidden not in metadata_payload


@pytest.mark.e2e
def test_openai_python_client_audio_translation_e2e(monkeypatch: pytest.MonkeyPatch) -> None:
    database_url = _test_database_url()
    run_alembic_upgrade_head(database_url)
    _configure_runtime_environment(monkeypatch, database_url)
    created = asyncio.run(
        _create_audio_test_data(
            database_url,
            endpoint=TRANSLATIONS_ENDPOINT,
            requested_model="classroom-audio-translation",
            resolved_model="whisper-1",
            capability_key="audio_translations",
            request_price=Decimal("0.006000000"),
        )
    )

    from openai import OpenAI
    from slaif_gateway.config import get_settings
    from slaif_gateway.main import create_app

    port = _free_port()
    monkeypatch.setenv("OPENAI_API_KEY", created.plaintext_key)
    monkeypatch.setenv("OPENAI_BASE_URL", f"http://127.0.0.1:{port}/v1")

    app = create_app(get_settings())
    prompt_text = "Keep names intact"

    with tempfile.NamedTemporaryFile(suffix=".mp3") as tmp:
        tmp.write(b"ID3fake-audio")
        tmp.flush()

        with _run_uvicorn_server(app, port):
            with respx.mock(assert_all_mocked=True, assert_all_called=True) as router:
                router.route(host="127.0.0.1").pass_through()
                upstream_route = router.post("https://api.openai.com/v1/audio/translations").mock(
                    return_value=httpx.Response(
                        200,
                        json={"text": "Hello world"},
                        headers={"content-type": "application/json"},
                    )
                )

                client = OpenAI()
                response = client.audio.translations.create(
                    model="classroom-audio-translation",
                    file=Path(tmp.name),
                    prompt=prompt_text,
                    response_format="json",
                    temperature=0.1,
                )

    assert response.text == "Hello world"
    assert len(upstream_route.calls) == 1
    upstream_request = upstream_route.calls[0].request
    assert upstream_request.headers["authorization"] == f"Bearer {FAKE_OPENAI_UPSTREAM_KEY}"
    assert upstream_request.headers["authorization"] != f"Bearer {created.plaintext_key}"
    multipart_text = upstream_request.content.decode("utf-8", errors="ignore")
    assert 'name="model"' in multipart_text
    assert "whisper-1" in multipart_text
    assert 'name="prompt"' in multipart_text
    assert prompt_text in multipart_text

    state = asyncio.run(_load_accounting_state(database_url, created.gateway_key_id))
    assert state.reservation.status == "finalized"
    assert state.gateway_key.requests_used_total == 1
    assert state.gateway_key.cost_used_eur > Decimal("0")
    usage_payload = json.dumps(state.usage_ledger.usage_raw, sort_keys=True)
    metadata_payload = json.dumps(state.usage_ledger.response_metadata, sort_keys=True)
    for forbidden in (prompt_text, "Hello world", Path(tmp.name).name, created.plaintext_key):
        assert forbidden not in usage_payload
        assert forbidden not in metadata_payload
