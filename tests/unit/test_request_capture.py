"""Unit tests for the operator-controlled request-capture observer (191-a).

Covers the pure-ASGI capture middleware against a synthetic application:
complete-body retention, safe no-prefix handling of incomplete captures,
secret masking in request-derived metadata, provenance channels, claim
exhaustion, and the guarantee that capture never alters the application
call, its incoming messages, or its outgoing messages.  No database and no
real gateway auth are involved; the verified-key probe is either absent
(no ``scope["app"]`` state) or explicitly faked.
"""

from __future__ import annotations

import asyncio
import base64
import json
import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import pytest

from slaif_gateway.api.request_capture import RequestCaptureMiddleware, install_request_capture
from slaif_gateway.services.request_capture import (
    CAPTURES_DIR_NAME,
    CaptureFacilityConfig,
    CaptureStore,
    record_scope_capture_provenance,
)

_PREFIXES = ("sk-slaif-",)
_REQUEST_ID = "gw-" + "a" * 32


def _config(root: Path, *, body_budget_bytes: int = 65536) -> CaptureFacilityConfig:
    return CaptureFacilityConfig(
        enabled=True,
        root=root,
        body_budget_bytes=body_budget_bytes,
        total_storage_bytes=max(4 * 1024 * 1024, body_budget_bytes * 2),
        max_count=100,
        max_ttl_seconds=3600,
        deployed_revision="synthetic-revision",
        revision_provenance="synthetic-test",
        app_version="0.1.0",
    )


class _SyntheticApp:
    """Minimal ASGI app with configurable body consumption and behavior."""

    def __init__(
        self,
        *,
        consume_body: bool = True,
        raise_error: BaseException | None = None,
        status: int = 200,
    ) -> None:
        self.consume_body = consume_body
        self.raise_error = raise_error
        self.status = status
        self.calls = 0
        self.consumed: list[dict[str, Any]] = []
        self.sent: list[dict[str, Any]] = []

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: Callable[[], Awaitable[dict[str, Any]]],
        send: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        self.calls += 1
        if self.consume_body:
            while True:
                message = await receive()
                self.consumed.append(message)
                if message.get("type") != "http.request" or not message.get("more_body", False):
                    break
        if self.raise_error is not None:
            raise self.raise_error
        produced = [
            {"type": "http.response.start", "status": self.status, "headers": []},
            {"type": "http.response.body", "body": b'{"ok":true}', "more_body": False},
        ]
        for message in produced:
            self.sent.append(message)
            await send(message)


def _scope(
    *,
    raw_body: bytes,
    path: str = "/v1/responses",
    raw_path: bytes | None = None,
    method: str = "POST",
    headers: list[tuple[bytes, bytes]] | None = None,
    app: Any = None,
) -> dict[str, Any]:
    if headers is None:
        headers = [(b"content-length", str(len(raw_body)).encode())]
    return {
        "type": "http",
        "method": method,
        "path": path,
        "raw_path": raw_path if raw_path is not None else path.encode(),
        "query_string": b"",
        "headers": headers,
        "state": {"gateway_request_id": _REQUEST_ID},
        "app": app,
    }


def _run_middleware(
    scope: dict[str, Any],
    raw_body: bytes,
    app: _SyntheticApp,
    store: CaptureStore,
    *,
    body_budget_bytes: int = 65536,
    disconnect: bool = False,
) -> None:
    middleware = RequestCaptureMiddleware(
        app, store=store, body_budget_bytes=body_budget_bytes, accepted_prefixes=_PREFIXES
    )
    messages: list[dict[str, Any]] = []
    if disconnect:
        messages.append({"type": "http.request", "body": raw_body[:1], "more_body": True})
    elif len(raw_body) > 5:
        messages.append({"type": "http.request", "body": raw_body[:5], "more_body": True})
        messages.append({"type": "http.request", "body": raw_body[5:], "more_body": False})
    else:
        messages.append({"type": "http.request", "body": raw_body, "more_body": False})
    index = 0

    async def receive() -> dict[str, Any]:
        nonlocal index
        if index >= len(messages):
            return {"type": "http.disconnect"}
        message = messages[index]
        index += 1
        return message

    sent: list[dict[str, Any]] = []

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)
        # The app records its own produced messages; identity check below.

    asyncio.run(middleware(scope, receive, send))
    assert sent == app.sent, "outgoing messages must be forwarded unchanged"


def _artifacts(store: CaptureStore, session_id: str) -> dict[str, dict[str, Any]]:
    directory = store.root / CAPTURES_DIR_NAME / session_id
    docs: dict[str, dict[str, Any]] = {}
    if directory.is_dir():
        for path in directory.glob("*.json"):
            kind = path.name.split(".")[1]
            docs[kind] = json.loads(path.read_bytes())
    return docs


def _artifact_bytes(store: CaptureStore, session_id: str) -> bytes:
    directory = store.root / CAPTURES_DIR_NAME / session_id
    return b"\n".join(p.read_bytes() for p in sorted(directory.glob("*.json")))


@pytest.fixture
def store(tmp_path: Path) -> CaptureStore:
    return CaptureStore(_config(tmp_path / "captures"))


def test_no_active_session_is_passthrough(store: CaptureStore) -> None:
    app = _SyntheticApp()
    scope = _scope(raw_body=b'{"input":"hello"}')
    _run_middleware(scope, b'{"input":"hello"}', app, store)
    assert app.calls == 1
    assert store.status() == []
    assert len(list((store.root / CAPTURES_DIR_NAME).glob("*"))) == 0


def test_complete_body_retained_exactly(store: CaptureStore) -> None:
    raw = b'{"input":"PRESERVE_COMPLETE_BODY","session_id":"PRESERVE_SESSION"}'
    session = store.arm(endpoint="/v1/responses")
    app = _SyntheticApp()
    scope = _scope(raw_body=raw)
    _run_middleware(scope, raw, app, store)
    docs = _artifacts(store, session.session_id)
    capture, record = docs["capture"], docs["record"]
    assert capture["body_complete"] is True
    assert base64.b64decode(capture["body"]) == raw
    assert base64.b64decode(capture["path"]) == scope["raw_path"]
    assert capture["body_bytes_observed"] == len(raw)
    assert capture["request_id"] == _REQUEST_ID == record["request_id"]
    assert record["status_code"] == 200
    assert record["endpoint"] == "/v1/responses"
    assert record["module_id"] is None and record["module_fixture_sha256"] is None


def test_complete_body_masks_bearer_with_hint(store: CaptureStore) -> None:
    key = "sk-slaif-" + "P" * 22 + "." + "S" * 43
    raw = b'{"prompt":"hello","copy":"' + key.encode() + b'","session":"keep-1"}'
    session = store.arm(endpoint="/v1/responses")
    app = _SyntheticApp()
    headers = [(b"authorization", ("Bearer " + key).encode())]
    scope = _scope(raw_body=raw, headers=headers)
    _run_middleware(scope, raw, app, store)
    docs = _artifacts(store, session.session_id)
    capture, record = docs["capture"], docs["record"]
    stored = base64.b64decode(capture["body"])
    assert key.encode() not in stored
    assert b'"session":"keep-1"' in stored
    hint = record["recognized_hint"].encode()
    assert stored == raw.replace(key.encode(), hint)
    assert capture["body_complete"] is True
    assert key.encode() not in _artifact_bytes(store, session.session_id)


def test_incomplete_not_consumed_stores_no_body(store: CaptureStore) -> None:
    raw = b'synthetic-body-bytes'
    session = store.arm(endpoint="/v1/responses")
    app = _SyntheticApp(consume_body=False)
    scope = _scope(raw_body=raw)
    _run_middleware(scope, raw, app, store)
    docs = _artifacts(store, session.session_id)
    capture, record = docs["capture"], docs["record"]
    assert capture["body_complete"] is False
    assert capture["body_omitted_for_secret_safety"] is True
    assert capture["incomplete_reason"] == "not_consumed"
    assert base64.b64decode(capture["body"]) == b""
    assert capture["body_bytes_stored"] == 0
    # The observer only counts bytes the application actually pulled.
    assert capture["body_bytes_observed"] == 0
    assert record["body_complete"] is False
    assert record["incomplete_reason"] == "not_consumed"


def test_truncated_body_over_budget_stores_no_body(store: CaptureStore) -> None:
    raw = b"ABCDE"
    session = store.arm(endpoint="/v1/responses")
    app = _SyntheticApp()
    scope = _scope(raw_body=raw)
    _run_middleware(scope, raw, app, store, body_budget_bytes=3)
    docs = _artifacts(store, session.session_id)
    capture = docs["capture"]
    assert capture["body_complete"] is False
    assert capture["body_truncated"] is True
    assert capture["incomplete_reason"] == "body_limit"
    assert base64.b64decode(capture["body"]) == b""
    assert capture["body_bytes_observed"] == len(raw)
    assert capture["body_bytes_buffered"] == 3


def test_client_disconnect_stores_no_body(store: CaptureStore) -> None:
    raw = b"abcdef"
    session = store.arm(endpoint="/v1/responses")
    # The app pulls the partial chunk, then the client disconnects mid-body.
    app = _SyntheticApp(consume_body=True)
    scope = _scope(raw_body=raw)
    _run_middleware(scope, raw, app, store, disconnect=True)
    docs = _artifacts(store, session.session_id)
    capture = docs["capture"]
    assert capture["body_complete"] is False
    assert capture["body_disconnected"] is True
    assert capture["incomplete_reason"] == "client_disconnected"
    assert capture["body_bytes_observed"] == len(raw[:1])
    assert base64.b64decode(capture["body"]) == b""


def test_method_and_rejection_diagnostic_are_masked(store: CaptureStore) -> None:
    key = "sk-slaif-" + "P" * 22 + "." + "S" * 43
    session = store.arm(endpoint="/v1/responses")
    app = _SyntheticApp()

    from slaif_gateway.services.request_capture import record_scope_capture_rejection

    async def rejecting_app(
        scope: dict[str, Any],
        receive: Callable[[], Awaitable[dict[str, Any]]],
        send: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        app.calls += 1
        while True:
            message = await receive()
            if message.get("type") != "http.request" or not message.get("more_body", False):
                break
        record_scope_capture_rejection(
            scope,
            {
                "reason_code": "synthetic_rejection",
                "param": key + chr(0xD800),
                "counts": {"tools": 197},
            },
        )
        for message in (
            {"type": "http.response.start", "status": 400, "headers": []},
            {"type": "http.response.body", "body": b"{}", "more_body": False},
        ):
            app.sent.append(message)
            await send(message)

    middleware = RequestCaptureMiddleware(
        rejecting_app, store=store, body_budget_bytes=65536, accepted_prefixes=_PREFIXES
    )
    messages = [{"type": "http.request", "body": b"synthetic", "more_body": False}]
    index = 0

    async def receive() -> dict[str, Any]:
        nonlocal index
        if index >= len(messages):
            return {"type": "http.disconnect"}
        message = messages[index]
        index += 1
        return message

    async def send(message: dict[str, Any]) -> None:
        pass

    scope = _scope(
        raw_body=b"synthetic",
        method=key,
        headers=[(b"authorization", ("Bearer " + key).encode())],
    )
    asyncio.run(middleware(scope, receive, send))
    blob = _artifact_bytes(store, session.session_id)
    assert key.encode() not in blob
    assert b"S" * 20 not in blob


def test_app_exception_is_preserved_and_finalized(store: CaptureStore) -> None:
    session = store.arm(endpoint="/v1/responses")
    failure = RuntimeError("synthetic-app-exception-private-marker")
    app = _SyntheticApp(raise_error=failure)
    scope = _scope(raw_body=b"synthetic")
    with pytest.raises(RuntimeError) as exc_info:
        _run_middleware(scope, b"synthetic", app, store)
    assert exc_info.value is failure
    docs = _artifacts(store, session.session_id)
    record = docs["record"]
    assert record["app_raised"] is True
    assert record["exception_class"] == "RuntimeError"
    assert "synthetic-app-exception-private-marker" not in json.dumps(record)
    assert record["status_code"] is None


def test_capture_write_failure_is_passthrough(store: CaptureStore) -> None:
    session = store.arm(endpoint="/v1/responses")

    def fail(**_kwargs: Any) -> None:
        raise RuntimeError("synthetic-write-failure-private-marker")

    store.write_artifact = fail  # type: ignore[method-assign]
    app = _SyntheticApp()
    scope = _scope(raw_body=b"synthetic")
    _run_middleware(scope, b"synthetic", app, store)
    assert app.calls == 1
    assert store.status()[0].remaining == 0  # the claim is consumed
    assert not (store.root / CAPTURES_DIR_NAME / session.session_id).exists()


def test_claim_exhaustion_stops_capture(store: CaptureStore) -> None:
    session = store.arm(endpoint="/v1/responses", count=1)
    raw = b'{"input":"one"}'
    app = _SyntheticApp()
    scope = _scope(raw_body=raw)
    _run_middleware(scope, raw, app, store)
    assert len(_artifacts(store, session.session_id)) == 2
    app2 = _SyntheticApp()
    _run_middleware(scope, raw, app2, store)
    assert app2.calls == 1
    assert len(_artifacts(store, session.session_id)) == 2


def test_normal_auth_provenance_prefers_normal_key(store: CaptureStore) -> None:
    session = store.arm(endpoint="/v1/responses")
    key_uuid = str(uuid.uuid4())
    app = _SyntheticApp()
    scope = _scope(raw_body=b'{"input":"x"}')
    record_scope_capture_provenance(
        scope, verified_key_uuid=key_uuid, auth_provenance="normal_auth"
    )
    _run_middleware(scope, b'{"input":"x"}', app, store)
    record = _artifacts(store, session.session_id)["record"]
    assert record["verified_key_uuid"] == key_uuid
    assert record["verified_key_provenance"] == "normal_auth"


def test_probe_provenance_fallback_and_module_identity(store: CaptureStore) -> None:
    session = store.arm(endpoint="/v1/responses")
    probe_uuid = str(uuid.uuid4())
    app = _SyntheticApp()
    scope = _scope(
        raw_body=b'{"input":"x"}',
        headers=[(b"authorization", b"Bearer sk-slaif-" + b"P" * 22 + b"." + b"S" * 43)],
    )
    record_scope_capture_provenance(
        scope,
        module_id="codex-0162",
        module_version="3",
        module_fixture_sha256="ab" * 32,
    )
    middleware = RequestCaptureMiddleware(
        app, store=store, body_budget_bytes=65536, accepted_prefixes=_PREFIXES
    )
    middleware._probe_verified_key = (  # type: ignore[method-assign]
        lambda scope, headers: asyncio.sleep(0, result=probe_uuid)
    )
    messages = [{"type": "http.request", "body": b'{"input":"x"}', "more_body": False}]
    index = 0

    async def receive() -> dict[str, Any]:
        nonlocal index
        if index >= len(messages):
            return {"type": "http.disconnect"}
        message = messages[index]
        index += 1
        return message

    async def send(_message: dict[str, Any]) -> None:
        pass

    asyncio.run(middleware(scope, receive, send))
    record = _artifacts(store, session.session_id)["record"]
    assert record["verified_key_uuid"] == probe_uuid
    assert record["verified_key_provenance"] == "read_only_capture_probe"
    assert record["module_id"] == "codex-0162"
    assert record["module_version"] == "3"
    assert record["module_fixture_sha256"] == "ab" * 32


def test_install_request_capture_disabled_returns_none(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from fastapi import FastAPI

    from slaif_gateway.config import get_settings

    monkeypatch.delenv("REQUEST_CAPTURE_ENABLED", raising=False)
    get_settings.cache_clear()
    try:
        app = FastAPI()
        assert install_request_capture(app, get_settings()) is None
        assert not hasattr(app.state, "capture_store")
    finally:
        get_settings.cache_clear()


def test_install_request_capture_enabled_builds_store(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from fastapi import FastAPI

    from slaif_gateway.config import get_settings

    monkeypatch.setenv("REQUEST_CAPTURE_ENABLED", "true")
    monkeypatch.setenv("REQUEST_CAPTURE_DIR", str(tmp_path / "captures"))
    get_settings.cache_clear()
    try:
        app = FastAPI()
        store = install_request_capture(app, get_settings())
        assert store is not None
        assert store.root == tmp_path / "captures"
        assert app.state.capture_store is store
    finally:
        get_settings.cache_clear()


def test_malformed_body_within_budget_is_retained(store: CaptureStore) -> None:
    raw = b'{"input": BROKEN-JSON \xff\xfe NOT UTF8'
    session = store.arm(endpoint="/v1/responses")
    app = _SyntheticApp()
    scope = _scope(raw_body=raw)
    _run_middleware(scope, raw, app, store)
    capture = _artifacts(store, session.session_id)["capture"]
    assert capture["body_complete"] is True
    assert base64.b64decode(capture["body"]) == raw
