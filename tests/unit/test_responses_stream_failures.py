"""HTTP/SSE failure boundaries, source-derived consumer shape, and cleanup."""

import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from slaif_gateway.main import create_app
from slaif_gateway.providers.errors import ProviderHTTPError, ProviderTimeoutError
from slaif_gateway.providers.streaming import format_responses_error_event
from slaif_gateway.utils.streaming_response import DeferredStartStreamingResponse
from tests.unit.test_v1_responses_quota import (
    _response_stream_chunk,
    _responses_request,
    _wire_auth_and_db,
    _wire_streaming_gateway,
    _wire_streaming_route,
    _wire_successful_route_pricing_quota,
)


def _setup(monkeypatch, chunks, error):
    app = create_app()
    _wire_auth_and_db(monkeypatch, app)
    _wire_successful_route_pricing_quota(monkeypatch)
    _wire_streaming_route(monkeypatch)
    state, _, reservation = _wire_streaming_gateway(
        monkeypatch, chunks=chunks, provider_error=error
    )
    return app, state, reservation


@pytest.mark.parametrize("status", [400, 401, 403, 404, 429, 500, 503])
def test_upstream_rejection_before_first_event_is_http_error_and_releases_once(monkeypatch, status):
    error = ProviderHTTPError(provider="synthetic", upstream_status_code=status)
    app, state, reservation = _setup(monkeypatch, [], error)
    response = TestClient(app).post("/v1/responses", json={**_responses_request(), "stream": True})
    assert response.status_code == status
    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["error"]["code"] == "provider_http_error"
    assert len(state["failure_calls"]) == 1
    assert state["failure_calls"][0]["status_code"] == status
    assert state["finalize_calls"] == []
    assert state["streaming_estimate_calls"] == []
    assert state["rate_release_calls"] == [(reservation, True)]


def test_early_timeout_is_http_504_not_empty_success_stream(monkeypatch):
    app, state, _ = _setup(monkeypatch, [], ProviderTimeoutError(provider="synthetic"))
    response = TestClient(app).post("/v1/responses", json={**_responses_request(), "stream": True})
    assert response.status_code == 504
    assert response.json()["error"]["code"] == "provider_timeout"
    assert len(state["failure_calls"]) == 1


@pytest.mark.parametrize("partial_text", [False, True])
def test_after_headers_failure_is_terminal_failed_event_with_real_identity(
    monkeypatch, partial_text
):
    chunks = [
        _response_stream_chunk(
            {"type": "response.created", "sequence_number": 7, "response": {"id": "resp_synthetic"}}
        )
    ]
    if partial_text:
        chunks.append(
            _response_stream_chunk(
                {"type": "response.output_text.delta", "sequence_number": 8, "delta": "visible"}
            )
        )
    app, state, reservation = _setup(
        monkeypatch, chunks, ProviderTimeoutError(provider="synthetic")
    )
    response = TestClient(app).post("/v1/responses", json={**_responses_request(), "stream": True})
    assert response.status_code == 200
    events = [
        json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")
    ]
    failed = events[-1]
    assert failed["type"] == "response.failed"
    assert failed["sequence_number"] == (9 if partial_text else 8)
    assert failed["response"]["id"] == "resp_synthetic"
    assert failed["response"]["status"] == "failed"
    assert failed["response"]["error"]["code"] == "provider_timeout"
    # Exact pinned Codex consumer reads response.failed.response.error rather
    # than treating ordinary type:error as a generic API failure.
    assert failed["response"]["error"]["message"] == "Provider request timed out"
    assert "response.completed" not in response.text and "[DONE]" not in response.text
    assert len(state["streaming_estimate_calls"]) == int(partial_text)
    assert len(state["failure_calls"]) == int(not partial_text)
    assert state["rate_release_calls"] == [(reservation, True)]


def test_formatter_never_invents_a_response_identity():
    event = json.loads(format_responses_error_event(message="Safe failure", code="synthetic")[6:])
    assert event["type"] == "error"
    assert "response" not in event


@pytest.mark.asyncio
async def test_response_does_not_commit_headers_while_waiting_for_first_event():
    ready = asyncio.Event()
    sent = []
    closed = []

    async def events():
        try:
            await ready.wait()
            yield "first"
            yield "second"
        finally:
            closed.append(True)

    async def send(event):
        sent.append(event)

    task = asyncio.create_task(DeferredStartStreamingResponse(events()).stream_response(send))
    await asyncio.sleep(0)
    assert sent == []
    ready.set()
    await task
    assert sent[0]["type"] == "http.response.start"
    assert [e["body"] for e in sent[1:]] == [b"first", b"second", b""]
    assert closed == [True]


@pytest.mark.asyncio
async def test_send_disconnect_closes_suspended_producer_immediately():
    closed = []

    async def events():
        try:
            yield "first"
            await asyncio.sleep(100)
        finally:
            closed.append(True)

    async def send(event):
        if event["type"] == "http.response.body":
            raise OSError("Synthetic closed peer")

    with pytest.raises(OSError):
        await DeferredStartStreamingResponse(events()).stream_response(send)
    assert closed == [True]


@pytest.mark.asyncio
async def test_disconnect_before_first_event_closes_producer_without_headers():
    entered = asyncio.Event()
    closed = []
    sent = []

    async def events():
        try:
            entered.set()
            await asyncio.sleep(100)
            yield "never"
        finally:
            closed.append(True)

    async def send(event):
        sent.append(event)

    task = asyncio.create_task(DeferredStartStreamingResponse(events()).stream_response(send))
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert closed == [True] and sent == []


def test_transport_send_failure_runs_stream_accounting_and_slot_cleanup(monkeypatch):
    import slaif_gateway.services.responses_gateway as gateway

    chunks = [
        _response_stream_chunk({"type": "response.created", "response": {"id": "resp_synthetic"}}),
        _response_stream_chunk({"type": "response.output_text.delta", "delta": "visible"}),
    ]
    app, state, reservation = _setup(monkeypatch, chunks, None)

    class ClosedPeerResponse(DeferredStartStreamingResponse):
        async def stream_response(self, send):
            async def closed_send(event):
                if event["type"] == "http.response.body" and b"visible" in event["body"]:
                    raise OSError("Synthetic transport disconnect")
                await send(event)

            await super().stream_response(closed_send)

    monkeypatch.setattr(gateway, "DeferredStartStreamingResponse", ClosedPeerResponse)
    response = TestClient(app, raise_server_exceptions=False).post(
        "/v1/responses", json={**_responses_request(), "stream": True}
    )
    assert response.status_code == 200
    assert len(state["streaming_estimate_calls"]) == 1
    assert state["streaming_estimate_calls"][0]["error_type"] == "client_disconnected"
    assert state["finalize_calls"] == []
    assert state["rate_release_calls"] == [(reservation, True)]
