from __future__ import annotations

import asyncio
import json
from decimal import Decimal

import httpx
import pytest
import respx

from tests.e2e.test_openai_python_client_chat import (
    CHAT_COMPLETIONS_ENDPOINT,
    FAKE_OPENROUTER_UPSTREAM_KEY,
    _configure_runtime_environment,
    _create_test_data,
    _free_port,
    _load_accounting_state,
    _run_uvicorn_server,
    _test_database_url,
)
from tests.integration.db_test_utils import run_alembic_upgrade_head

TEST_MODEL = "anthropic/claude-test"
PROMPT_TEXT = "Hello from SLAIF OpenRouter test"
COMPLETION_TEXT = "Hello from mocked OpenRouter"


@pytest.mark.e2e
def test_openai_python_client_chat_completions_openrouter_env_e2e(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = _test_database_url()
    run_alembic_upgrade_head(database_url)
    _configure_runtime_environment(monkeypatch, database_url)
    created = asyncio.run(
        _create_test_data(
            database_url,
            provider="openrouter",
            model=TEST_MODEL,
            base_url="https://openrouter.ai/api/v1",
            api_key_env_var="OPENROUTER_API_KEY",
            owner_label="OpenRouter",
        )
    )

    from openai import OpenAI
    from slaif_gateway.config import get_settings
    from slaif_gateway.main import create_app

    port = _free_port()
    monkeypatch.setenv("OPENAI_API_KEY", created.plaintext_gateway_key)
    monkeypatch.setenv("OPENAI_BASE_URL", f"http://127.0.0.1:{port}/v1")

    app = create_app(get_settings())
    upstream_payload = {
        "id": "chatcmpl-openrouter-test",
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
        "usage": {"prompt_tokens": 7, "completion_tokens": 8, "total_tokens": 15},
    }

    with _run_uvicorn_server(app, port):
        with respx.mock(assert_all_mocked=True, assert_all_called=True) as router:
            router.route(host="127.0.0.1").pass_through()
            upstream_route = router.post(
                "https://openrouter.ai/api/v1/chat/completions"
            ).mock(
                return_value=httpx.Response(
                    200,
                    json=upstream_payload,
                    headers={"x-openrouter-request-id": "upstream-openrouter-e2e"},
                )
            )

            client = OpenAI()
            response = client.chat.completions.create(
                model=TEST_MODEL,
                messages=[{"role": "user", "content": PROMPT_TEXT}],
            )

    assert response.choices[0].message.content == COMPLETION_TEXT
    assert len(upstream_route.calls) == 1
    upstream_request = upstream_route.calls[0].request
    assert upstream_request.headers["authorization"] == f"Bearer {FAKE_OPENROUTER_UPSTREAM_KEY}"
    assert upstream_request.headers["authorization"] != f"Bearer {created.plaintext_gateway_key}"

    upstream_body = json.loads(upstream_request.content)
    assert upstream_body["model"] == TEST_MODEL
    assert upstream_body["max_completion_tokens"] == get_settings().DEFAULT_MAX_OUTPUT_TOKENS
    assert PROMPT_TEXT in json.dumps(upstream_body)

    state = asyncio.run(
        _load_accounting_state(
            database_url,
            created.gateway_key_id,
            provider="openrouter",
        )
    )

    assert state.reservation.status == "finalized"
    assert state.reservation.finalized_at is not None
    assert state.gateway_key.cost_reserved_eur == Decimal("0E-9")
    assert state.gateway_key.tokens_reserved_total == 0
    assert state.gateway_key.requests_reserved_total == 0
    assert state.gateway_key.tokens_used_total == 15
    assert state.gateway_key.requests_used_total == 1
    assert state.gateway_key.cost_used_eur >= Decimal("0")

    assert state.usage_ledger.provider == "openrouter"
    assert state.usage_ledger.requested_model == TEST_MODEL
    assert state.usage_ledger.resolved_model == TEST_MODEL
    assert state.usage_ledger.prompt_tokens == 7
    assert state.usage_ledger.completion_tokens == 8
    assert state.usage_ledger.total_tokens == 15
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
    assert FAKE_OPENROUTER_UPSTREAM_KEY not in provider_config_text
    assert state.provider_config.api_key_env_var == "OPENROUTER_API_KEY"
    assert CHAT_COMPLETIONS_ENDPOINT == state.usage_ledger.endpoint
