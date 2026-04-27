from __future__ import annotations

import asyncio
import json
from decimal import Decimal

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from slaif_gateway.services.accounting_errors import ReservationFinalizationError
from tests.e2e.test_openai_python_client_chat import (
    COMPLETION_TEXT,
    FAKE_OPENAI_UPSTREAM_KEY,
    PROMPT_TEXT,
    TEST_MODEL,
    _configure_runtime_environment,
    _create_test_data,
    _load_accounting_state,
)
from tests.integration.db_test_utils import run_alembic_upgrade_head


def _streaming_body() -> dict[str, object]:
    return {
        "model": TEST_MODEL,
        "messages": [{"role": "user", "content": PROMPT_TEXT}],
        "stream": True,
    }


def _successful_sse() -> str:
    return (
        'data: {"id":"chatcmpl-stream","object":"chat.completion.chunk","created":123,'
        f'"model":"{TEST_MODEL}","choices":[{{"index":0,"delta":{{"content":"{COMPLETION_TEXT}"}},'
        '"finish_reason":"stop"}]}\n\n'
        'data: {"id":"chatcmpl-stream","object":"chat.completion.chunk","created":123,'
        f'"model":"{TEST_MODEL}","choices":[],"usage":'
        '{"prompt_tokens":5,"completion_tokens":6,"total_tokens":11}}\n\n'
        "data: [DONE]\n\n"
    )


def test_streaming_provider_completed_finalization_failure_leaves_recovery_record(
    migrated_postgres_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_alembic_upgrade_head(migrated_postgres_url)
    _configure_runtime_environment(monkeypatch, migrated_postgres_url)
    created = asyncio.run(_create_test_data(migrated_postgres_url))

    from slaif_gateway.config import get_settings
    from slaif_gateway.main import create_app
    from slaif_gateway.services.accounting import AccountingService

    async def _fail_finalization(self, *args, **kwargs):
        _ = (self, args, kwargs)
        raise ReservationFinalizationError()

    monkeypatch.setattr(AccountingService, "finalize_successful_response", _fail_finalization)

    app = create_app(get_settings())
    with respx.mock(assert_all_mocked=True, assert_all_called=True) as router:
        upstream_route = router.post("https://api.openai.com/v1/chat/completions").mock(
            return_value=httpx.Response(
                200,
                content=_successful_sse().encode(),
                headers={"x-request-id": "upstream-openai-stream-recovery"},
            )
        )
        with TestClient(app) as client:
            with client.stream(
                "POST",
                "/v1/chat/completions",
                json=_streaming_body(),
                headers={"Authorization": f"Bearer {created.plaintext_gateway_key}"},
            ) as response:
                streamed = "".join(response.iter_text())

    assert response.status_code == 200
    assert COMPLETION_TEXT in streamed
    assert "reservation_finalization_error" in streamed
    assert "data: [DONE]" not in streamed
    assert len(upstream_route.calls) == 1
    upstream_request = upstream_route.calls[0].request
    assert upstream_request.headers["authorization"] == f"Bearer {FAKE_OPENAI_UPSTREAM_KEY}"
    assert upstream_request.headers["authorization"] != f"Bearer {created.plaintext_gateway_key}"

    state = asyncio.run(_load_accounting_state(migrated_postgres_url, created.gateway_key_id))
    assert state.reservation.status == "pending"
    assert state.gateway_key.tokens_used_total == 0
    assert state.gateway_key.cost_used_eur == Decimal("0E-9")
    assert state.gateway_key.tokens_reserved_total > 0
    assert state.gateway_key.requests_reserved_total == 1
    assert state.usage_ledger.streaming is True
    assert state.usage_ledger.success is None
    assert state.usage_ledger.accounting_status == "failed"
    assert state.usage_ledger.error_type == "accounting_finalization_failed"
    assert state.usage_ledger.prompt_tokens == 5
    assert state.usage_ledger.completion_tokens == 6
    assert state.usage_ledger.total_tokens == 11
    assert state.usage_ledger.actual_cost_eur is not None
    assert state.usage_ledger.actual_cost_eur > Decimal("0")
    assert state.usage_ledger.response_metadata["needs_reconciliation"] is True
    assert (
        state.usage_ledger.response_metadata["recovery_state"]
        == "provider_completed_finalization_failed"
    )

    usage_payload = json.dumps(state.usage_ledger.usage_raw, sort_keys=True)
    metadata_payload = json.dumps(state.usage_ledger.response_metadata, sort_keys=True)
    assert PROMPT_TEXT not in usage_payload
    assert COMPLETION_TEXT not in usage_payload
    assert PROMPT_TEXT not in metadata_payload
    assert COMPLETION_TEXT not in metadata_payload
