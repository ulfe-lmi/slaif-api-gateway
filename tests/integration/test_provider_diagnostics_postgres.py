from __future__ import annotations

import asyncio
import json
from decimal import Decimal

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from tests.e2e.test_openai_python_client_chat import (
    COMPLETION_TEXT,
    FAKE_OPENROUTER_UPSTREAM_KEY,
    PROMPT_TEXT,
    _configure_runtime_environment,
    _create_test_data,
    _load_accounting_state,
)
from tests.e2e.test_openrouter_python_client_chat import TEST_MODEL
from tests.integration.db_test_utils import run_alembic_upgrade_head


def _chat_body(*, stream: bool = False) -> dict[str, object]:
    body: dict[str, object] = {
        "model": TEST_MODEL,
        "messages": [{"role": "user", "content": PROMPT_TEXT}],
    }
    if stream:
        body["stream"] = True
    return body


def test_non_streaming_provider_error_persists_sanitized_diagnostic(
    migrated_postgres_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_alembic_upgrade_head(migrated_postgres_url)
    _configure_runtime_environment(monkeypatch, migrated_postgres_url)
    created = asyncio.run(
        _create_test_data(
            migrated_postgres_url,
            provider="openrouter",
            model=TEST_MODEL,
            base_url="https://openrouter.ai/api/v1",
            api_key_env_var="OPENROUTER_API_KEY",
            owner_label="OpenRouter Diagnostics",
        )
    )

    from slaif_gateway.config import get_settings
    from slaif_gateway.main import create_app

    app = create_app(get_settings())
    upstream_error = {
        "error": {
            "message": "rate limited for sk-or-secret",
            "code": "rate_limited",
            "metadata": {
                "request_body": PROMPT_TEXT,
                "response_body": COMPLETION_TEXT,
                "authorization": f"Bearer {created.plaintext_gateway_key}",
                "apiKey": FAKE_OPENROUTER_UPSTREAM_KEY,
                "token_hash": "hash-secret",
            },
        }
    }
    with respx.mock(assert_all_mocked=True, assert_all_called=True) as router:
        upstream_route = router.post("https://openrouter.ai/api/v1/chat/completions").mock(
            return_value=httpx.Response(
                429,
                json=upstream_error,
                headers={"x-openrouter-request-id": "or-diagnostic-error"},
            )
        )
        with TestClient(app) as client:
            response = client.post(
                "/v1/chat/completions",
                json=_chat_body(),
                headers={"Authorization": f"Bearer {created.plaintext_gateway_key}"},
            )

    assert response.status_code == 429
    assert response.json()["error"]["code"] == "provider_http_error"
    assert "rate limited for" not in response.text
    assert len(upstream_route.calls) == 1
    upstream_request = upstream_route.calls[0].request
    assert upstream_request.headers["authorization"] == f"Bearer {FAKE_OPENROUTER_UPSTREAM_KEY}"
    assert upstream_request.headers["authorization"] != f"Bearer {created.plaintext_gateway_key}"

    state = asyncio.run(
        _load_accounting_state(
            migrated_postgres_url,
            created.gateway_key_id,
            provider="openrouter",
        )
    )
    assert state.reservation.status == "released"
    assert state.gateway_key.cost_reserved_eur == Decimal("0E-9")
    assert state.gateway_key.tokens_reserved_total == 0
    assert state.usage_ledger.accounting_status == "failed"
    assert state.usage_ledger.error_type == "provider_http_error"

    metadata = state.usage_ledger.response_metadata
    diagnostic = metadata["provider_diagnostic"]
    assert diagnostic["provider"] == "openrouter"
    assert diagnostic["upstream_status_code"] == 429
    assert diagnostic["upstream_error_code"] == "rate_limited"
    assert diagnostic["upstream_request_id"] == "or-diagnostic-error"

    metadata_text = json.dumps(metadata, sort_keys=True)
    assert "provider_diagnostic" in metadata_text
    assert "raw provider" not in metadata_text
    assert PROMPT_TEXT not in metadata_text
    assert COMPLETION_TEXT not in metadata_text
    assert FAKE_OPENROUTER_UPSTREAM_KEY not in metadata_text
    assert created.plaintext_gateway_key not in metadata_text
    assert "hash-secret" not in metadata_text
    assert "authorization" not in metadata_text.lower()


def test_streaming_provider_error_event_persists_sanitized_diagnostic(
    migrated_postgres_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_alembic_upgrade_head(migrated_postgres_url)
    _configure_runtime_environment(monkeypatch, migrated_postgres_url)
    created = asyncio.run(
        _create_test_data(
            migrated_postgres_url,
            provider="openrouter",
            model=TEST_MODEL,
            base_url="https://openrouter.ai/api/v1",
            api_key_env_var="OPENROUTER_API_KEY",
            owner_label="OpenRouter Streaming Diagnostics",
        )
    )

    from slaif_gateway.config import get_settings
    from slaif_gateway.main import create_app

    app = create_app(get_settings())
    sse = (
        'data: {"error":{"message":"provider rejected sk-or-secret",'
        '"code":"bad_request","metadata":{"prompt":"'
        + PROMPT_TEXT
        + '","response_body":"'
        + COMPLETION_TEXT
        + '","apiKey":"'
        + FAKE_OPENROUTER_UPSTREAM_KEY
        + '"}}}\n\n'
    )
    with respx.mock(assert_all_mocked=True, assert_all_called=True) as router:
        upstream_route = router.post("https://openrouter.ai/api/v1/chat/completions").mock(
            return_value=httpx.Response(
                200,
                content=sse.encode(),
                headers={"x-openrouter-request-id": "or-stream-diagnostic-error"},
            )
        )
        with TestClient(app) as client:
            with client.stream(
                "POST",
                "/v1/chat/completions",
                json=_chat_body(stream=True),
                headers={"Authorization": f"Bearer {created.plaintext_gateway_key}"},
            ) as response:
                streamed = "".join(response.iter_text())

    assert response.status_code == 200
    assert "provider_http_error" in streamed
    assert "provider rejected" not in streamed
    assert len(upstream_route.calls) == 1

    state = asyncio.run(
        _load_accounting_state(
            migrated_postgres_url,
            created.gateway_key_id,
            provider="openrouter",
        )
    )
    assert state.reservation.status == "released"
    assert state.usage_ledger.streaming is True
    assert state.usage_ledger.accounting_status == "failed"
    assert state.usage_ledger.error_type == "provider_http_error"

    metadata = state.usage_ledger.response_metadata
    diagnostic = metadata["provider_diagnostic"]
    assert diagnostic["provider"] == "openrouter"
    assert diagnostic["upstream_status_code"] == 200
    assert diagnostic["upstream_error_code"] == "bad_request"
    assert diagnostic["upstream_request_id"] == "or-stream-diagnostic-error"

    metadata_text = json.dumps(metadata, sort_keys=True)
    assert PROMPT_TEXT not in metadata_text
    assert COMPLETION_TEXT not in metadata_text
    assert FAKE_OPENROUTER_UPSTREAM_KEY not in metadata_text
    assert created.plaintext_gateway_key not in metadata_text
    assert "apiKey" not in metadata_text
