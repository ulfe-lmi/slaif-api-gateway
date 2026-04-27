from __future__ import annotations

import inspect
import uuid
from datetime import UTC, datetime, timedelta

import pytest

import slaif_gateway.services.chat_completion_gateway as gateway_module
from slaif_gateway.api.errors import OpenAICompatibleError
from slaif_gateway.config import Settings
from slaif_gateway.schemas.auth import AuthenticatedGatewayKey
from slaif_gateway.schemas.openai import ChatCompletionRequest


def _auth() -> AuthenticatedGatewayKey:
    now = datetime.now(UTC)
    return AuthenticatedGatewayKey(
        gateway_key_id=uuid.uuid4(),
        owner_id=uuid.uuid4(),
        cohort_id=None,
        public_key_id="public1234abcd",
        status="active",
        valid_from=now - timedelta(minutes=5),
        valid_until=now + timedelta(minutes=30),
        allow_all_models=True,
        allowed_models=(),
        allow_all_endpoints=True,
        allowed_endpoints=(),
        allowed_providers=None,
        cost_limit_eur=None,
        token_limit_total=None,
        request_limit_total=None,
        rate_limit_policy={},
    )


def _payload() -> ChatCompletionRequest:
    return ChatCompletionRequest(
        model="gpt-test-mini",
        messages=[{"role": "user", "content": "hello"}],
        max_tokens=20,
    )


@pytest.mark.asyncio
async def test_db_session_unavailable_returns_database_error(monkeypatch) -> None:
    async def _empty_db_session(*args):
        _ = args
        if False:
            yield object()

    def _provider_must_not_be_called(*args, **kwargs):
        _ = (args, kwargs)
        raise AssertionError("provider must not be called without a DB session")

    monkeypatch.setattr(
        gateway_module,
        "_get_db_session_after_auth_header_check",
        _empty_db_session,
    )
    monkeypatch.setattr(gateway_module, "get_provider_adapter", _provider_must_not_be_called)

    with pytest.raises(OpenAICompatibleError) as exc_info:
        await gateway_module.handle_chat_completion(
            payload=_payload(),
            authenticated_key=_auth(),
            settings=Settings(OPENAI_UPSTREAM_API_KEY="unused"),
        )

    assert exc_info.value.status_code == 500
    assert exc_info.value.error_type == "server_error"
    assert exc_info.value.code == "database_session_unavailable"
    assert "Database session could not be created" in exc_info.value.message


def test_stale_provider_forwarding_placeholder_is_not_used_for_db_session_failures() -> None:
    source = inspect.getsource(gateway_module)

    assert "provider_forwarding_not_implemented" not in source
    assert "Provider forwarding is not implemented yet" not in source
    assert "database_session_unavailable" in source
