"""Unit tests for the content-free diagnostics ASGI observer middleware.

Layers:

* Real FastAPI app + TestClient with the actual ``RequestIdMiddleware`` and
  ``DiagnosticsObserverMiddleware``; the shared service ``record_failure`` is
  monkeypatched to capture the projected facts (no database, no provider, no
  normal auth).
* Pure-ASGI direct middleware calls for outcomes TestClient cannot express
  (cancellation, pre-response exceptions).
* Log-binding canaries: the request-ID log binding must never carry an opaque
  credential value aliased into the request-ID header (cookie, known
  credential header, proxy Bearer), while the wire ``X-Request-ID`` response
  header and the HTTP result are preserved exactly.
"""

from __future__ import annotations

import asyncio
import contextlib
import io
from typing import Any
from types import SimpleNamespace

import pytest
import structlog
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient

from slaif_gateway.api.errors import (
    OpenAICompatibleError,
    openai_compatible_error_handler,
)
from slaif_gateway.api.middleware import RequestIdMiddleware
from slaif_gateway.api.request_diagnostics import (
    DiagnosticsObserverMiddleware,
    install_request_diagnostics,
)
from slaif_gateway.config import Settings
from slaif_gateway.schemas.request_diagnostics import DiagnosticsWriteOutcome
from slaif_gateway.services.request_capture import (
    record_scope_capture_provenance,
    record_scope_capture_rejection,
)
from slaif_gateway.services.request_diagnostics import (
    RequestDiagnosticsService,
    record_scope_diagnostics,
)

CANARY = "opaque_alias_canary_123"


@pytest.fixture()
def settings() -> Settings:
    return Settings(_env_file=None, APP_ENV="test", DATABASE_URL=None)


@pytest.fixture()
def enabled_settings() -> Settings:
    return Settings(
        _env_file=None, APP_ENV="test", DATABASE_URL=None, REQUEST_DIAGNOSTICS_ENABLED=True
    )


@pytest.fixture()
def recorded(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Capture the facts the observer hands to the shared service."""
    captured: list[dict[str, Any]] = []

    async def fake_record_failure(
        self: Any,
        facts: Any,
        *,
        client_id_masker: Any = None,
        client_id_mask_complete: bool = True,
    ) -> DiagnosticsWriteOutcome:
        captured.append(dict(facts))
        return DiagnosticsWriteOutcome.STORED

    monkeypatch.setattr(RequestDiagnosticsService, "record_failure", fake_record_failure)
    return captured


def _make_app(settings: Settings, *, with_db: bool = True) -> FastAPI:
    app = FastAPI()
    if with_db:
        app.state.db_sessionmaker = object()
    # Starlette: the LAST added middleware is outermost, so RequestId is
    # outside the observer (same relative order as create_app).
    app.add_middleware(
        DiagnosticsObserverMiddleware,
        settings=settings,
        accepted_prefixes=("sk-slaif-",),
    )
    app.add_middleware(RequestIdMiddleware, settings=settings)
    return app


# -- terminal outcome observation ---------------------------------------------


def test_http_rejection_is_recorded_with_wire_status(
    enabled_settings: Settings, recorded: list[dict[str, Any]]
) -> None:
    app = _make_app(enabled_settings)

    @app.post("/v1/chat/completions")
    async def denied() -> Any:
        from fastapi.responses import JSONResponse

        return JSONResponse({"error": "denied"}, status_code=400)

    client = TestClient(app, raise_server_exceptions=False)
    response = client.post("/v1/chat/completions")
    assert response.status_code == 400
    assert len(recorded) == 1
    facts = recorded[0]
    assert facts["stream_outcome"] == "http_rejection"
    assert facts["http_status"] == 400
    assert facts["method"] == "POST"
    assert facts["endpoint_template"] == "/v1/chat/completions"
    assert str(facts["gateway_request_id"]).startswith("gw-")
    # client request ID state correlation preserved
    assert isinstance(facts["client_request_id"], str)


def test_successful_request_never_recorded(
    enabled_settings: Settings, recorded: list[dict[str, Any]]
) -> None:
    app = _make_app(enabled_settings)

    @app.get("/v1/models")
    async def models() -> dict[str, Any]:
        return {"data": []}

    response = TestClient(app).get("/v1/models")
    assert response.status_code == 200
    assert recorded == []


def test_admin_surface_is_not_observed(
    enabled_settings: Settings, recorded: list[dict[str, Any]]
) -> None:
    app = _make_app(enabled_settings)

    @app.get("/admin/keys")
    async def admin() -> None:
        raise RuntimeError("admin failure")

    response = TestClient(app, raise_server_exceptions=False).get("/admin/keys")
    assert response.status_code == 500
    assert recorded == []


def test_hook_stream_failure_after_200_is_recorded(
    enabled_settings: Settings, recorded: list[dict[str, Any]]
) -> None:
    app = _make_app(enabled_settings)

    @app.get("/v1/responses")
    async def streamed(request: Request) -> StreamingResponse:
        async def gen() -> Any:
            yield b"event: output_item.done\n\n"
            record_scope_diagnostics(
                request.scope,
                stream_outcome="stream_failure",
                source="responses_stream_failure",
                error_code="stream_event_invalid",
            )

        return StreamingResponse(gen(), media_type="text/event-stream")

    response = TestClient(app).get("/v1/responses")
    assert response.status_code == 200
    assert len(recorded) == 1
    facts = recorded[0]
    assert facts["stream_outcome"] == "stream_failure"
    # the actual wire status (headers already sent) is preserved
    assert facts["http_status"] == 200
    assert facts["source"] == "responses_stream_failure"
    assert facts["error_code"] == "stream_event_invalid"


def test_clean_stream_is_not_recorded(
    enabled_settings: Settings, recorded: list[dict[str, Any]]
) -> None:
    app = _make_app(enabled_settings)

    @app.get("/v1/responses")
    async def streamed() -> StreamingResponse:
        async def gen() -> Any:
            yield b"event: done\n\n"

        return StreamingResponse(gen(), media_type="text/event-stream")

    response = TestClient(app).get("/v1/responses")
    assert response.status_code == 200
    assert recorded == []


def test_mid_stream_exception_reraised_and_recorded(
    enabled_settings: Settings, recorded: list[dict[str, Any]]
) -> None:
    app = _make_app(enabled_settings)

    class StreamBreak(Exception):
        code = "synthetic_stream_break"

    @app.get("/v1/responses")
    async def streamed() -> StreamingResponse:
        async def gen() -> Any:
            yield b"event: partial\n\n"
            raise StreamBreak()

        return StreamingResponse(gen(), media_type="text/event-stream")

    with pytest.raises(Exception):
        TestClient(app).get("/v1/responses")
    assert len(recorded) == 1
    facts = recorded[0]
    assert facts["stream_outcome"] == "stream_failure"
    assert facts["http_status"] == 200
    assert facts["error_code"] == "synthetic_stream_break"


def test_pre_response_exception_recorded_as_rejection(
    enabled_settings: Settings, recorded: list[dict[str, Any]]
) -> None:
    app = _make_app(enabled_settings)

    class PreResponse(Exception):
        code = "synthetic_preflight"

    @app.get("/v1/models")
    async def models() -> None:
        raise PreResponse()

    TestClient(app, raise_server_exceptions=False).get("/v1/models")
    assert len(recorded) == 1
    facts = recorded[0]
    assert facts["stream_outcome"] == "http_rejection"
    # no response was ever sent: no wire status is projected
    assert facts.get("http_status") is None
    assert facts["error_code"] == "synthetic_preflight"


def test_no_diagnostic_id_never_recorded(
    enabled_settings: Settings, recorded: list[dict[str, Any]]
) -> None:
    """Without the RequestId middleware there is no server diagnostic ID."""
    app = FastAPI()
    app.state.db_sessionmaker = object()
    app.add_middleware(
        DiagnosticsObserverMiddleware,
        settings=enabled_settings,
        accepted_prefixes=("sk-slaif-",),
    )

    @app.get("/v1/models")
    async def models() -> None:
        raise RuntimeError("boom")

    TestClient(app, raise_server_exceptions=False).get("/v1/models")
    assert recorded == []


def test_missing_session_factory_never_recorded(
    enabled_settings: Settings, recorded: list[dict[str, Any]]
) -> None:
    app = _make_app(enabled_settings, with_db=False)

    @app.get("/v1/models")
    async def models() -> None:
        raise RuntimeError("boom")

    TestClient(app, raise_server_exceptions=False).get("/v1/models")
    assert recorded == []


def test_recording_failure_never_changes_response(
    enabled_settings: Settings, recorded: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    async def failing(
        self: Any, facts: Any, **kwargs: Any
    ) -> DiagnosticsWriteOutcome:
        raise RuntimeError("writer exploded")

    monkeypatch.setattr(RequestDiagnosticsService, "record_failure", failing)
    app = _make_app(enabled_settings)

    @app.get("/v1/models")
    async def models() -> None:
        raise RuntimeError("boom")

    response = TestClient(app, raise_server_exceptions=False).get("/v1/models")
    assert response.status_code == 500
    assert recorded == []  # nothing captured: the fake raised before storing


def test_install_is_noop_when_disabled(settings: Settings) -> None:
    app = FastAPI()
    install_request_diagnostics(app, settings)
    assert all(
        middleware.cls is not DiagnosticsObserverMiddleware
        for middleware in app.user_middleware
    )


def test_install_adds_observer_when_enabled(enabled_settings: Settings) -> None:
    app = FastAPI()
    install_request_diagnostics(app, enabled_settings)
    assert any(
        middleware.cls is DiagnosticsObserverMiddleware
        for middleware in app.user_middleware
    )


# -- pure-ASGI outcomes TestClient cannot express ------------------------------


def _direct_scope() -> dict[str, Any]:
    return {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "https",
        "path": "/v1/responses",
        "raw_path": b"/v1/responses",
        "query_string": b"",
        "root_path": "",
        "headers": [],
        "client": ("127.0.0.1", 12345),
        "server": ("test", 443),
        "state": {
            "gateway_request_id": "gw-11111111-1111-4111-8111-111111111111",
            "request_id": "req-direct",
        },
        "app": SimpleNamespace(state=SimpleNamespace(db_sessionmaker=object())),
    }


def test_cancellation_reraised_and_recorded(
    enabled_settings: Settings, recorded: list[dict[str, Any]]
) -> None:
    async def inner(scope: Any, receive: Any, send: Any) -> None:
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})
        raise asyncio.CancelledError()

    middleware = DiagnosticsObserverMiddleware(
        inner, settings=enabled_settings, accepted_prefixes=("sk-slaif-",)
    )

    async def send(message: Any) -> None:
        return None

    scope = _direct_scope()
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(middleware(scope, None, send))
    assert len(recorded) == 1
    assert recorded[0]["stream_outcome"] == "cancelled"


def test_pre_response_app_exception_recorded(
    enabled_settings: Settings, recorded: list[dict[str, Any]]
) -> None:
    class PreResponse(Exception):
        code = "synthetic_preflight"

    async def inner(scope: Any, receive: Any, send: Any) -> None:
        raise PreResponse()

    middleware = DiagnosticsObserverMiddleware(
        inner, settings=enabled_settings, accepted_prefixes=("sk-slaif-",)
    )
    with pytest.raises(PreResponse):
        asyncio.run(middleware(_direct_scope(), None, None))
    assert recorded[0]["stream_outcome"] == "http_rejection"
    assert recorded[0]["error_code"] == "synthetic_preflight"


def test_non_http_scope_passes_through(enabled_settings: Settings) -> None:
    seen: list[str] = []

    async def inner(scope: Any, receive: Any, send: Any) -> None:
        seen.append(scope["type"])

    middleware = DiagnosticsObserverMiddleware(
        inner, settings=enabled_settings, accepted_prefixes=("sk-slaif-",)
    )
    asyncio.run(middleware({"type": "websocket"}, None, None))
    assert seen == ["websocket"]


# -- projection boundary: counts and wire-status priority ----------------------


def test_taxonomy_observed_count_preserved(
    enabled_settings: Settings, recorded: list[dict[str, Any]]
) -> None:
    app = _make_app(enabled_settings)

    @app.post("/v1/responses")
    async def denied(request: Request) -> None:
        record_scope_capture_rejection(
            request.scope,
            {
                "source": "codex_additional_tools_taxonomy",
                "reason_code": "additional_tools_count_exceeded",
                "param": "input.tools",
                "field": "a free-form field value that must never be stored",
                "observed": 197,
                "limit": 128,
            },
        )
        from fastapi.responses import JSONResponse

        return JSONResponse(
            {"error": "taxonomy"}, status_code=400
        )

    response = TestClient(app).post("/v1/responses")
    assert response.status_code == 400
    assert len(recorded) == 1
    facts = recorded[0]
    # the genuine integer observed count survives under its finite key
    assert facts["counts"] == {"observed": 197, "limit": 128}
    assert facts["source"] == "codex_additional_tools_taxonomy"
    # free-form field text is never projected
    assert "field" not in facts
    assert "free-form" not in repr(facts)


def test_observed_wire_status_beats_classifier_hint(
    enabled_settings: Settings, recorded: list[dict[str, Any]]
) -> None:
    """Synthetic direct observer injection: a classifier ``status_code`` hint
    that conflicts with the actual ASGI wire status must lose.  This is a
    projection-boundary guard, not a reproduced real HTTP failure (real
    classifiers record the status they actually raised)."""
    app = _make_app(enabled_settings)

    @app.post("/v1/responses")
    async def denied(request: Request) -> Any:
        record_scope_capture_rejection(
            request.scope,
            {
                "source": "local_error",
                "reason_code": "local_rejection",
                "status_code": 500,  # conflicting classifier hint
            },
        )
        from fastapi.responses import JSONResponse

        return JSONResponse({"error": "conflict"}, status_code=403)

    response = TestClient(app).post("/v1/responses")
    assert response.status_code == 403
    assert len(recorded) == 1
    # the actual observed wire status wins
    assert recorded[0]["http_status"] == 403


# -- provenance attribution -----------------------------------------------------


def test_normal_auth_provenance_supplies_key_id(
    enabled_settings: Settings, recorded: list[dict[str, Any]]
) -> None:
    app = _make_app(enabled_settings)

    @app.get("/v1/models")
    async def models(request: Request) -> None:
        record_scope_capture_provenance(
            request.scope,
            auth_provenance="normal_auth",
            verified_key_uuid="11112222-3333-4444-5555-666677778888",
        )
        raise RuntimeError("boom")

    TestClient(app, raise_server_exceptions=False).get("/v1/models")
    assert len(recorded) == 1
    assert (
        recorded[0]["gateway_key_id"]
        == "11112222-3333-4444-5555-666677778888"
    )


def test_capture_probe_provenance_never_supplies_key_id(
    enabled_settings: Settings, recorded: list[dict[str, Any]]
) -> None:
    app = _make_app(enabled_settings)

    @app.get("/v1/models")
    async def models(request: Request) -> None:
        record_scope_capture_provenance(
            request.scope,
            auth_provenance="read_only_capture_probe",
            verified_key_uuid="11112222-3333-4444-5555-666677778888",
        )
        raise RuntimeError("boom")

    TestClient(app, raise_server_exceptions=False).get("/v1/models")
    assert len(recorded) == 1
    assert recorded[0].get("gateway_key_id") is None


# -- request-ID log binding: credential-alias canaries --------------------------


def _log_app(settings: Settings) -> FastAPI:
    app = FastAPI()
    app.add_exception_handler(OpenAICompatibleError, openai_compatible_error_handler)
    app.add_middleware(RequestIdMiddleware, settings=settings)

    @app.get("/v1/log-fail")
    async def fail() -> None:
        structlog.get_logger("probe").info("probe.failure")
        raise OpenAICompatibleError(
            "Synthetic boundary rejection.",
            code="endpoint_not_allowed",
            status_code=403,
        )

    return app


@pytest.mark.parametrize(
    ("header", "value", "alias"),
    [
        ("Cookie", f"session={CANARY}", CANARY),
        ("X-API-Key", CANARY, CANARY),
        ("Proxy-Authorization", f"Bearer {CANARY}", CANARY),
    ],
    ids=["cookie", "known_header", "proxy"],
)
def test_credential_alias_never_reaches_log_binding(
    settings: Settings, header: str, value: str, alias: str
) -> None:
    app = _log_app(settings)
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        response = TestClient(app).get(
            "/v1/log-fail", headers={"X-Request-ID": alias, header: value}
        )
    assert response.status_code == 403
    # wire correlation is preserved exactly
    assert response.headers.get("X-Request-ID") == alias
    log_output = buffer.getvalue()
    assert alias not in log_output
    assert "[REDACTED]" in log_output or "request_id" not in log_output


def test_plain_request_id_still_bound_for_logs(settings: Settings) -> None:
    """Positive control: without any credential alias the ordinary client
    request ID keeps reaching the log binding (no over-masking)."""
    app = _log_app(settings)
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        response = TestClient(app).get(
            "/v1/log-fail",
            headers={
                "X-Request-ID": "plain-legit-id-42",
                "Cookie": "session=unrelated-session-value",
            },
        )
    assert response.status_code == 403
    assert response.headers.get("X-Request-ID") == "plain-legit-id-42"
    assert "plain-legit-id-42" in buffer.getvalue()


def test_masker_fault_omits_binding_and_preserves_request(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A fault INSIDE the masker callback must omit the log binding, never
    turn an ordinary 200 request into a 500, and never skip the endpoint."""
    import slaif_gateway.api.middleware as mw

    def broken_masker(scope: Any, *, accepted_prefixes: Any) -> Any:
        def boom(data: Any) -> Any:
            raise RuntimeError("synthetic masker fault")

        return boom, True

    monkeypatch.setattr(mw, "build_client_id_masker", broken_masker)
    app = FastAPI()
    app.add_middleware(RequestIdMiddleware, settings=settings)
    calls: list[int] = []

    @app.get("/v1/ok")
    async def ok() -> dict[str, bool]:
        calls.append(1)
        return {"fine": True}

    response = TestClient(app).get("/v1/ok", headers={"X-Request-ID": "legit-wire-id"})
    assert response.status_code == 200
    assert response.json() == {"fine": True}
    assert response.headers.get("X-Request-ID") == "legit-wire-id"
    assert calls == [1]
