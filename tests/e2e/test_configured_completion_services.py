"""Official SDK -> real gateway/DB -> mocked service, for both JSON profiles."""

import asyncio
import json
from decimal import Decimal

import httpx
import pytest
import respx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from tests.e2e.test_openai_python_client_chat import (
    _configure_runtime_environment,
    _create_test_data,
    _free_port,
    _load_accounting_state,
    _run_uvicorn_server,
    _test_database_url,
)
from tests.integration.db_test_utils import run_alembic_upgrade_head


async def configure_module(database_url, provider, model, profile_id):
    from slaif_gateway.db.models import ModelRoute, PricingRule, ProviderConfig
    from slaif_gateway.services.chat_completion_route_capabilities import (
        completion_service_chat_completion_capabilities,
    )

    engine = create_async_engine(database_url)
    try:
        async with async_sessionmaker(engine)() as session:
            p = await session.scalar(
                select(ProviderConfig).where(ProviderConfig.provider == provider)
            )
            p.kind = "module"
            p.max_retries = 0
            p.timeout_seconds = 30
            route = await session.scalar(
                select(ModelRoute).where(
                    ModelRoute.provider == provider,
                    ModelRoute.requested_model == model,
                )
            )
            route.capabilities = {
                "chat_completions": completion_service_chat_completion_capabilities(),
                "completion_service": {"version": 1, "profile": profile_id},
            }
            price = await session.scalar(
                select(PricingRule).where(
                    PricingRule.provider == provider,
                    PricingRule.upstream_model == model,
                )
            )
            price.currency = "EUR"
            price.request_price = price.input_price_per_1m = price.output_price_per_1m = Decimal(
                "0"
            )
            await session.commit()
    finally:
        await engine.dispose()


@pytest.mark.e2e
@pytest.mark.parametrize("profile_id", ["facial-scoring-v1", "zap-it-v1"])
def test_sdk_completion_profiles_with_real_admission_and_accounting(monkeypatch, profile_id):
    from openai import OpenAI
    from slaif_gateway.config import get_settings
    from slaif_gateway.main import create_app
    from slaif_gateway.modules.servers.completion_service.profiles import load_profile

    db = _test_database_url()
    run_alembic_upgrade_head(db)
    _configure_runtime_environment(monkeypatch, db)
    profile = load_profile(profile_id)
    provider = "facial_scoring" if profile_id == "facial-scoring-v1" else "zap_it"
    monkeypatch.setenv(profile.api_key_env_var, "synthetic-native-secret")
    created = asyncio.run(
        _create_test_data(
            db,
            provider=provider,
            model=profile.public_model,
            base_url="https://completion-native.example",
            api_key_env_var=profile.api_key_env_var,
            supports_streaming=False,
            image_inputs=True,
        )
    )
    asyncio.run(configure_module(db, provider, profile.public_model, profile_id))
    port = _free_port()
    monkeypatch.setenv("OPENAI_API_KEY", created.plaintext_gateway_key)
    monkeypatch.setenv("OPENAI_BASE_URL", f"http://127.0.0.1:{port}/v1")
    native = {"status": "scored", "score": 0.25}
    content = [{"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}}]
    if profile_id == "zap-it-v1":
        content.append({"type": "text", "text": "pipeline: sam2\n"})
        native = {
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [
                        {
                            "type": "output_text",
                            "text": '{"schema_version":"zap-it.public.v1","objects":[]}',
                        },
                    ],
                }
            ],
        }
    with _run_uvicorn_server(create_app(get_settings()), port):
        with respx.mock(assert_all_mocked=True, assert_all_called=False) as router:
            router.route(host="127.0.0.1").pass_through()
            upstream = router.post(
                "https://completion-native.example" + profile.upstream_path
            ).mock(
                return_value=httpx.Response(200, json=native),
            )
            with OpenAI() as client:
                result = client.chat.completions.create(
                    model=profile.public_model,
                    messages=[{"role": "user", "content": content}],
                )
            assert upstream.call_count == 1
            sent = upstream.calls[0].request
            assert (
                sent.headers[profile.auth_header] == profile.auth_prefix + "synthetic-native-secret"
            )
            assert created.plaintext_gateway_key.encode() not in sent.content
            assert created.plaintext_gateway_key not in str(sent.headers)
    assert result.model == profile.public_model
    assert result.usage.total_tokens == 0
    if profile_id == "zap-it-v1":
        assert json.loads(result.choices[0].message.content)["schema_version"] == "zap-it.public.v1"
    else:
        assert result.choices[0].message.content == "Score: 0.2500 (type: uncalibrated_model_score)"
    state = asyncio.run(_load_accounting_state(db, created.gateway_key_id, provider=provider))
    assert state.gateway_key.requests_used_total == 1
    assert state.gateway_key.tokens_used_total == 0
    assert state.gateway_key.requests_reserved_total == 0
    assert state.reservation.status == "finalized"
    assert state.usage_ledger.actual_cost_eur == 0
    assert state.usage_ledger.total_tokens == 0
    assert state.usage_ledger.usage_raw == {}
