from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

from fastapi.testclient import TestClient

from slaif_gateway.api.dependencies import get_authenticated_gateway_key
from slaif_gateway.config import Settings
from slaif_gateway.main import create_app
from slaif_gateway.providers.errors import ProviderTimeoutError
from slaif_gateway.services.accounting_errors import ReservationFinalizationError
from slaif_gateway.schemas.auth import AuthenticatedGatewayKey
from slaif_gateway.schemas.providers import ProviderStreamChunk, ProviderUsage
from slaif_gateway.schemas.quota import QuotaReservationResult
from slaif_gateway.schemas.routing import RouteResolutionResult


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


def _route() -> RouteResolutionResult:
    return RouteResolutionResult(
        requested_model="classroom-cheap",
        resolved_model="gpt-4.1-mini",
        provider="openai",
        route_id=uuid.uuid4(),
        route_match_type="exact",
        route_pattern="classroom-cheap",
        priority=100,
    )


def _chat_request() -> dict[str, object]:
    return {
        "model": "classroom-cheap",
        "messages": [{"role": "user", "content": "hello"}],
        "stream": True,
        "stream_options": {"include_usage": False, "other": "preserved"},
        "max_tokens": 20,
    }


def _wire_streaming_pipeline(monkeypatch, app, *, chunks=None, provider_error=None):
    from slaif_gateway.api import dependencies as dependencies_module
    import slaif_gateway.services.chat_completion_gateway as gateway_module

    state = {
        "route_calls": [],
        "pricing_calls": [],
        "reserve_calls": [],
        "stream_calls": [],
        "provider_completed_calls": [],
        "finalize_calls": [],
        "recovery_failure_calls": [],
        "failure_calls": [],
    }
    auth = _auth()

    class _Session:
        async def commit(self) -> None:
            return None

    async def _fake_auth_dependency() -> AuthenticatedGatewayKey:
        return auth

    async def _dummy_db_session():
        yield _Session()

    async def _fake_resolve_model(self, requested_model, authenticated_key):
        _ = (self, authenticated_key)
        state["route_calls"].append(requested_model)
        return _route()

    async def _fake_estimate(self, *, route, policy, endpoint="chat.completions", at=None):
        _ = (self, route, policy, endpoint, at)
        state["pricing_calls"].append("priced")
        return object()

    async def _fake_reserve(self, *, authenticated_key, route, policy, cost_estimate, request_id, now=None):
        _ = (self, authenticated_key, route, policy, cost_estimate, now)
        state["reserve_calls"].append(request_id)
        return QuotaReservationResult(
            reservation_id=uuid.uuid4(),
            gateway_key_id=auth.gateway_key_id,
            request_id=request_id,
            reserved_cost_eur=Decimal("0.003"),
            reserved_tokens=70,
            status="pending",
            expires_at=datetime.now(UTC) + timedelta(minutes=15),
        )

    async def _fake_provider_completed(self, *args, **kwargs):
        _ = (self, args)
        usage_ledger_id = uuid.uuid4()
        state["provider_completed_calls"].append({"usage_ledger_id": usage_ledger_id, **kwargs})
        return SimpleNamespace(usage_ledger_id=usage_ledger_id)

    async def _fake_finalize(self, *args, **kwargs):
        _ = (self, args)
        if state.get("finalize_error") is not None:
            raise state["finalize_error"]
        state["finalize_calls"].append(kwargs)
        return object()

    async def _fake_mark_finalization_failed(self, *args, **kwargs):
        _ = (self, args)
        state["recovery_failure_calls"].append(
            {
                "usage_ledger_id": args[0],
                "reservation_id": args[1],
                **kwargs,
            }
        )
        return object()

    async def _fake_failure(self, *args, **kwargs):
        _ = (self, args)
        state["failure_calls"].append(kwargs)
        return object()

    class _FakeAdapter:
        async def stream_chat_completion(self, request):
            state["stream_calls"].append(request)
            if provider_error is not None:
                raise provider_error
            for chunk in chunks or []:
                yield chunk

    app.dependency_overrides[get_authenticated_gateway_key] = _fake_auth_dependency
    monkeypatch.setattr(dependencies_module, "_get_db_session_after_auth_header_check", _dummy_db_session)
    monkeypatch.setattr(gateway_module, "_get_db_session_after_auth_header_check", _dummy_db_session)
    monkeypatch.setattr(gateway_module.RouteResolutionService, "resolve_model", _fake_resolve_model)
    monkeypatch.setattr(gateway_module.PricingService, "estimate_chat_completion_cost", _fake_estimate)
    monkeypatch.setattr(gateway_module.QuotaService, "reserve_for_chat_completion", _fake_reserve)
    monkeypatch.setattr(
        gateway_module.AccountingService,
        "record_provider_completed_before_finalization",
        _fake_provider_completed,
    )
    monkeypatch.setattr(gateway_module.AccountingService, "finalize_successful_response", _fake_finalize)
    monkeypatch.setattr(
        gateway_module.AccountingService,
        "mark_provider_completed_finalization_failed",
        _fake_mark_finalization_failed,
    )
    monkeypatch.setattr(gateway_module.AccountingService, "record_provider_failure_and_release", _fake_failure)
    monkeypatch.setattr(gateway_module, "get_provider_adapter", lambda route, settings: _FakeAdapter())
    return state


def test_streaming_chat_completion_forwards_chunks_and_finalizes_after_usage(monkeypatch) -> None:
    chunks = [
        ProviderStreamChunk(
            provider="openai",
            upstream_model="gpt-4.1-mini",
            data='{"id":"chunk-1","choices":[{"delta":{"content":"Hel"}}]}',
            raw_sse_event='data: {"id":"chunk-1","choices":[{"delta":{"content":"Hel"}}]}\n\n',
        ),
        ProviderStreamChunk(
            provider="openai",
            upstream_model="gpt-4.1-mini",
            data='{"id":"chunk-2","choices":[],"usage":{"prompt_tokens":5,"completion_tokens":6,"total_tokens":11}}',
            raw_sse_event=(
                'data: {"id":"chunk-2","choices":[],"usage":'
                '{"prompt_tokens":5,"completion_tokens":6,"total_tokens":11}}\n\n'
            ),
            json_body={
                "id": "chunk-2",
                "choices": [],
                "usage": {"prompt_tokens": 5, "completion_tokens": 6, "total_tokens": 11},
            },
            usage=ProviderUsage(prompt_tokens=5, completion_tokens=6, total_tokens=11),
            upstream_request_id="upstream-stream",
        ),
        ProviderStreamChunk(
            provider="openai",
            upstream_model="gpt-4.1-mini",
            data="[DONE]",
            raw_sse_event="data: [DONE]\n\n",
            is_done=True,
        ),
    ]
    app = create_app(Settings(OPENAI_UPSTREAM_API_KEY="unused"))
    state = _wire_streaming_pipeline(monkeypatch, app, chunks=chunks)

    with TestClient(app).stream("POST", "/v1/chat/completions", json=_chat_request()) as response:
        body = "".join(response.iter_text())

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "data: [DONE]" in body
    assert state["route_calls"] == ["classroom-cheap"]
    assert state["pricing_calls"] == ["priced"]
    assert state["reserve_calls"]
    assert state["stream_calls"]
    assert state["stream_calls"][0].body["stream_options"] == {
        "include_usage": True,
        "other": "preserved",
    }
    assert state["provider_completed_calls"]
    assert state["finalize_calls"]
    assert state["finalize_calls"][0]["streaming"] is True
    assert state["finalize_calls"][0]["provider_completed_usage_ledger_id"] == (
        state["provider_completed_calls"][0]["usage_ledger_id"]
    )
    assert state["recovery_failure_calls"] == []
    assert state["failure_calls"] == []


def test_streaming_provider_failure_records_failure_and_returns_error_event(monkeypatch) -> None:
    app = create_app(Settings(OPENAI_UPSTREAM_API_KEY="unused"))
    state = _wire_streaming_pipeline(
        monkeypatch,
        app,
        provider_error=ProviderTimeoutError(provider="openai"),
    )

    with TestClient(app).stream("POST", "/v1/chat/completions", json=_chat_request()) as response:
        body = "".join(response.iter_text())

    assert response.status_code == 200
    assert "provider_timeout" in body
    assert state["reserve_calls"]
    assert state["failure_calls"]
    assert state["failure_calls"][0]["streaming"] is True
    assert state["finalize_calls"] == []


def test_streaming_missing_final_usage_records_failure(monkeypatch) -> None:
    chunks = [
        ProviderStreamChunk(
            provider="openai",
            upstream_model="gpt-4.1-mini",
            data="[DONE]",
            raw_sse_event="data: [DONE]\n\n",
            is_done=True,
        )
    ]
    app = create_app(Settings(OPENAI_UPSTREAM_API_KEY="unused"))
    state = _wire_streaming_pipeline(monkeypatch, app, chunks=chunks)

    with TestClient(app).stream("POST", "/v1/chat/completions", json=_chat_request()) as response:
        body = "".join(response.iter_text())

    assert response.status_code == 200
    assert "stream_usage_missing" in body
    assert "final usage metadata" in body
    assert "data: [DONE]" not in body
    assert state["failure_calls"]
    assert state["failure_calls"][0]["error_code"] == "stream_usage_missing"
    assert state["finalize_calls"] == []


def test_streaming_missing_final_usage_error_event_is_safe(monkeypatch) -> None:
    secret_text = "sk-slaif-public1234abcd.supersecret"
    chunks = [
        ProviderStreamChunk(
            provider="openai",
            upstream_model="gpt-4.1-mini",
            data=f'{{"id":"chunk","choices":[{{"delta":{{"content":"{secret_text}"}}}}]}}',
            raw_sse_event=(
                'data: {"id":"chunk","choices":[{"delta":{"content":"partial content"}}]}\n\n'
            ),
        ),
        ProviderStreamChunk(
            provider="openai",
            upstream_model="gpt-4.1-mini",
            data="[DONE]",
            raw_sse_event="data: [DONE]\n\n",
            is_done=True,
        ),
    ]
    app = create_app(Settings(OPENAI_UPSTREAM_API_KEY="unused"))
    _wire_streaming_pipeline(monkeypatch, app, chunks=chunks)

    with TestClient(app).stream("POST", "/v1/chat/completions", json=_chat_request()) as response:
        body = "".join(response.iter_text())

    assert response.status_code == 200
    assert "stream_usage_missing" in body
    assert "partial content" in body
    assert "data: [DONE]" not in body
    error_event = body.rsplit("data: ", 1)[-1]
    assert "partial content" not in error_event
    assert secret_text not in error_event


def test_streaming_finalization_failure_marks_recovery_and_suppresses_done(monkeypatch) -> None:
    chunks = [
        ProviderStreamChunk(
            provider="openai",
            upstream_model="gpt-4.1-mini",
            data='{"id":"chunk-1","choices":[{"delta":{"content":"Hel"}}]}',
            raw_sse_event='data: {"id":"chunk-1","choices":[{"delta":{"content":"Hel"}}]}\n\n',
        ),
        ProviderStreamChunk(
            provider="openai",
            upstream_model="gpt-4.1-mini",
            data='{"id":"chunk-2","choices":[],"usage":{"prompt_tokens":5,"completion_tokens":6,"total_tokens":11}}',
            raw_sse_event=(
                'data: {"id":"chunk-2","choices":[],"usage":'
                '{"prompt_tokens":5,"completion_tokens":6,"total_tokens":11}}\n\n'
            ),
            json_body={
                "id": "chunk-2",
                "choices": [],
                "usage": {"prompt_tokens": 5, "completion_tokens": 6, "total_tokens": 11},
            },
            usage=ProviderUsage(prompt_tokens=5, completion_tokens=6, total_tokens=11),
            upstream_request_id="upstream-stream",
        ),
        ProviderStreamChunk(
            provider="openai",
            upstream_model="gpt-4.1-mini",
            data="[DONE]",
            raw_sse_event="data: [DONE]\n\n",
            is_done=True,
        ),
    ]
    app = create_app(Settings(OPENAI_UPSTREAM_API_KEY="unused"))
    state = _wire_streaming_pipeline(monkeypatch, app, chunks=chunks)
    state["finalize_error"] = ReservationFinalizationError()

    with TestClient(app).stream("POST", "/v1/chat/completions", json=_chat_request()) as response:
        body = "".join(response.iter_text())

    assert response.status_code == 200
    assert "chunk-1" in body
    assert "reservation_finalization_error" in body
    assert "data: [DONE]" not in body
    assert state["provider_completed_calls"]
    assert state["recovery_failure_calls"]
    assert state["recovery_failure_calls"][0]["usage_ledger_id"] == (
        state["provider_completed_calls"][0]["usage_ledger_id"]
    )
    assert state["failure_calls"] == []
