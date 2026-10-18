"""Full-gateway E2E for the operator-controlled request-capture facility.

Two regressions, both with the owned labelled loopback PostgreSQL fixture
(``owned_pg_url``) and fully synthetic data; no real model or provider is
ever involved, and neither test is actual Codex CLI or actual model
qualification:

* ``test_chat_capture_thread_gateway_respx_upstream`` runs the gateway in a
  thread inside the test process with the OpenAI upstream mocked by respx
  and exercises the facility through the OpenAI Python SDK over real loopback
  HTTP.  It is SDK/mocked-upstream coverage, not a fresh-process proof.
* ``test_responses_capture_fresh_process_loopback_backend`` spawns a FRESH
  gateway process (real uvicorn) against a real loopback mock Local-Coding
  backend over real HTTP, and proves the /v1/responses path: verified-key
  UUID filtering with bad-HMAC non-consumption, complete malformed-JSON
  capture, actual selected-module id/version/digest, the precise taxonomy
  tool rejection, successful admission with finalized accounting, and known
  secret canaries.

Both prove, end to end:

* capture is default-OFF and a disabled/unarmed window changes nothing
  (identical upstream bytes, identical public response, normal accounting);
* an armed finite window captures the FULL original request bytes (with the
  gateway key masked) and the precise local rejection facts for malformed
  input, correlated by the gateway diagnostic ID;
* the window exhausts exactly after its configured count and later requests
  are plain passthrough again;
* accounting is unchanged throughout (every accepted request finalizes).

The synthetic canaries are generated per run and must never appear outside
the captured body artifacts where the full-content consent applies.
"""

from __future__ import annotations

import asyncio
import base64
import copy
import hashlib
import http.server
import json
import os
import secrets
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

import httpx
import pytest
import respx
from openai import OpenAI
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from tests.e2e.test_openai_python_client_chat import (
    COMPLETION_TEXT,
    TEST_MODEL,
    _configure_runtime_environment,
    _create_test_data,
    _free_port,
    _run_uvicorn_server,
)
from tests.integration.db_test_utils import run_alembic_upgrade_head
from tests.integration.test_lazy_throttling_postgres_redis import (  # noqa: F401
    owned_pg_url,
)

CANARY_PROMPT = f"OAP191-E2E-CANARY-{secrets.token_hex(8)}"
ENDPOINT = "/v1/chat/completions"
_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _upstream_payload() -> dict[str, object]:
    return {
        "id": "chatcmpl-capture-e2e",
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
        "usage": {"prompt_tokens": 5, "completion_tokens": 6, "total_tokens": 11},
    }


def _usage_ledger_count(database_url: str, gateway_key_id: uuid.UUID) -> int:
    async def _count() -> int:
        from slaif_gateway.db.models import UsageLedger

        engine = create_async_engine(database_url, future=True)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with session_factory() as session:
                value = await session.execute(
                    select(func.count())
                    .select_from(UsageLedger)
                    .where(UsageLedger.gateway_key_id == gateway_key_id)
                )
                return int(value.scalar_one())
        finally:
            await engine.dispose()

    return asyncio.run(_count())


def _artifacts(capture_root: Path) -> dict[str, dict[str, dict[str, object]]]:
    """Map request_id -> {"capture": doc, "record": doc} across sessions."""
    docs: dict[str, dict[str, dict[str, object]]] = {}
    captures_dir = capture_root / "captures"
    if not captures_dir.is_dir():
        return docs
    for session_dir in sorted(captures_dir.iterdir()):
        if not session_dir.is_dir():
            continue
        for path in sorted(session_dir.glob("*.json")):
            doc = json.loads(path.read_bytes())
            kind = path.name.split(".")[1]
            docs.setdefault(str(doc.get("request_id")), {})[kind] = doc
    return docs


@pytest.mark.e2e
def test_chat_capture_thread_gateway_respx_upstream(
    monkeypatch: pytest.MonkeyPatch,
    owned_pg_url: str,  # noqa: F811 - fixture surfaces the owned DB
    tmp_path: Path,
) -> None:
    """Chat coverage: in-process thread gateway, respx-mocked OpenAI upstream.

    This is NOT a fresh-process or actual-loopback-backend proof; that
    coverage lives in the /v1/responses test below.
    """
    database_url = owned_pg_url
    run_alembic_upgrade_head(database_url)
    capture_root = tmp_path / "captures"
    monkeypatch.setenv("REQUEST_CAPTURE_ENABLED", "true")
    monkeypatch.setenv("REQUEST_CAPTURE_DIR", str(capture_root))
    _configure_runtime_environment(monkeypatch, database_url)
    created = asyncio.run(_create_test_data(database_url))

    from slaif_gateway.config import get_settings
    from slaif_gateway.main import create_app
    from slaif_gateway.services.request_capture import build_capture_facility

    settings = get_settings()
    store = build_capture_facility(settings)
    assert store is not None
    port = _free_port()
    monkeypatch.setenv("OPENAI_API_KEY", created.plaintext_gateway_key)
    monkeypatch.setenv("OPENAI_BASE_URL", f"http://127.0.0.1:{port}/v1")
    client = OpenAI()

    upstream_bodies: list[bytes] = []

    def _chat(payload: dict[str, object]) -> None:
        response = client.chat.completions.create(**payload)
        assert response.choices[0].message.content == COMPLETION_TEXT

    def _stream(payload: dict[str, object]) -> None:
        chunks = list(client.chat.completions.create(**payload, stream=True))
        assert "".join(
            (chunk.choices[0].delta.content or "") for chunk in chunks if chunk.choices
        )

    def _raw(path: str, raw_body: bytes) -> httpx.Response:
        with httpx.Client(base_url=f"http://127.0.0.1:{port}") as raw_client:
            return raw_client.post(
                path,
                content=raw_body,
                headers={
                    "Authorization": f"Bearer {created.plaintext_gateway_key}",
                    "Content-Type": "application/json",
                },
            )
    with _run_uvicorn_server(create_app(settings), port):
        with respx.mock(assert_all_mocked=True, assert_all_called=False) as router:
            router.route(host="127.0.0.1").pass_through()
            upstream_route = router.post("https://api.openai.com/v1/chat/completions")

            def _upstream(request: httpx.Request) -> httpx.Response:
                upstream_bodies.append(request.content)
                if request.headers.get("stream", "").lower() == "true" or b'"stream":true' in request.content:
                    body = (
                        b'data: {"id":"chatcmpl-capture-e2e","object":"chat.completion.chunk",'
                        b'"created":123,"model":' + json.dumps(TEST_MODEL).encode() + b','
                        b'"choices":[{"index":0,"delta":{"role":"assistant","content":'
                        + json.dumps(COMPLETION_TEXT).encode() + b'},'
                        b'"finish_reason":null}]}\n\n'
                        b'data: {"id":"chatcmpl-capture-e2e","object":"chat.completion.chunk",'
                        b'"created":123,"model":' + json.dumps(TEST_MODEL).encode() + b','
                        b'"choices":[{"index":0,"delta":{},'
                        b'"finish_reason":"stop"}]}\n\n'
                        b'data: {"id":"chatcmpl-capture-e2e","object":"chat.completion.chunk",'
                        b'"created":123,"model":' + json.dumps(TEST_MODEL).encode() + b','
                        b'"choices":[],"usage":{"prompt_tokens":5,'
                        b'"completion_tokens":6,"total_tokens":11}}\n\n'
                        b"data: [DONE]\n\n"
                    )
                    return httpx.Response(
                        200,
                        content=body,
                        headers={
                            "content-type": "text/event-stream",
                            "x-request-id": "upstream-openai-e2e-stream",
                        },
                    )
                return httpx.Response(
                    200,
                    json=_upstream_payload(),
                    headers={"x-request-id": "upstream-openai-e2e"},
                )

            upstream_route.mock(side_effect=_upstream)

            chat_payload = {
                "model": TEST_MODEL,
                "messages": [{"role": "user", "content": CANARY_PROMPT}],
            }

            # 1) Unarmed baseline: capture is default-OFF, nothing is stored.
            _chat(chat_payload)
            assert len(upstream_bodies) == 1
            baseline_body = upstream_bodies[0]
            assert _artifacts(capture_root) == {}

            # 2) Arm a finite window and capture three accepted requests.
            store.arm(endpoint=ENDPOINT, count=3, ttl_seconds=600)
            _chat(chat_payload)
            assert upstream_bodies[1] == baseline_body
            _stream(chat_payload)
            _chat(chat_payload)

            # 3) Exhausted window: the next request is plain passthrough.
            _chat(chat_payload)
            assert len(upstream_bodies) == 5
            assert upstream_bodies[-1] == baseline_body

            # 4) Re-arm for one malformed-JSON rejection.
            store.arm(endpoint=ENDPOINT, count=1, ttl_seconds=600)
            malformed = b'{"model": ' + b'"' + TEST_MODEL.encode() + b'": BROKEN'
            rejected = _raw(ENDPOINT, malformed)
            assert rejected.status_code == 422
            error_payload = rejected.json()
            assert error_payload["error"]["code"] == "validation_error"

    # -- artifact assertions -------------------------------------------------

    docs = _artifacts(capture_root)
    # 4 captured request_ids: 3 accepted + 1 rejected.
    assert len(docs) == 4, {k: sorted(v.keys()) for k, v in docs.items()}
    by_record = [
        (v["record"], v["capture"]) for v in docs.values() if "record" in v and "capture" in v
    ]
    assert len(by_record) == 4
    key_bytes = created.plaintext_gateway_key.encode()

    accepted_docs = [
        pair for pair in by_record if pair[0].get("status_code") == 200
    ]
    rejected_docs = [pair for pair in by_record if pair[0].get("status_code") == 422]
    assert len(accepted_docs) == 3 and len(rejected_docs) == 1

    for record, capture in accepted_docs:
        assert record["endpoint"] == ENDPOINT
        assert record["verified_key_uuid"] == str(created.gateway_key_id)
        assert record["verified_key_provenance"] == "normal_auth"
        assert record["status_code"] == 200
        assert capture["body_complete"] is True
        assert capture["body_omitted_for_secret_safety"] is False
        stored = base64.b64decode(capture["body"])
        assert key_bytes not in stored
        assert CANARY_PROMPT.encode() in stored
        # The full prompt bytes are retained (explicit auth substitutions only).
        assert CANARY_PROMPT.encode() in stored

    record, capture = rejected_docs[0]
    assert record["status_code"] == 422
    rejection = record.get("rejection")
    assert isinstance(rejection, dict)
    assert rejection.get("error_code") == "validation_error"
    assert rejection.get("error_message") == "Invalid request"
    assert rejection.get("status_code") == 422
    assert rejection.get("count", 0) >= 1
    assert isinstance(rejection.get("errors"), list)
    first = rejection["errors"][0]
    assert first.get("error_type") == "json_invalid"
    loc = first.get("loc")
    assert isinstance(loc, list) and loc and loc[0] == "body"
    # The actual JSON parser position: a nonnegative integer offset in the body.
    assert any(
        isinstance(part, int) and not isinstance(part, bool) and part >= 0
        for part in loc[1:]
    )
    assert first.get("json_error")
    stored = base64.b64decode(capture["body"])
    assert stored == malformed  # exact malformed bytes preserved
    assert key_bytes not in stored

    # The canary never appears in control files (manifest/lock), only in the
    # consented full-content body artifacts.
    manifest = (capture_root / "capture.manifest.json").read_bytes()
    assert CANARY_PROMPT.encode() not in manifest
    assert key_bytes not in manifest

    # -- accounting is unchanged through the whole window ---------------------
    # 5 accepted requests (baseline 1 + captured 3 + after-exhaustion 1); the
    # 422 consumes no reservation and creates no ledger row.
    assert _usage_ledger_count(database_url, created.gateway_key_id) == 5


@pytest.mark.e2e
def test_request_capture_disabled_is_fully_passthrough(
    monkeypatch: pytest.MonkeyPatch,
    owned_pg_url: str,  # noqa: F811 - fixture surfaces the owned DB
    tmp_path: Path,
) -> None:
    database_url = owned_pg_url
    run_alembic_upgrade_head(database_url)
    monkeypatch.delenv("REQUEST_CAPTURE_ENABLED", raising=False)
    _configure_runtime_environment(monkeypatch, database_url)
    created = asyncio.run(_create_test_data(database_url))

    from slaif_gateway.config import get_settings
    from slaif_gateway.main import create_app
    from slaif_gateway.services.request_capture import build_capture_facility

    settings = get_settings()
    assert build_capture_facility(settings) is None
    port = _free_port()
    monkeypatch.setenv("OPENAI_API_KEY", created.plaintext_gateway_key)
    monkeypatch.setenv("OPENAI_BASE_URL", f"http://127.0.0.1:{port}/v1")
    client = OpenAI()

    with _run_uvicorn_server(create_app(settings), port):
        with respx.mock(assert_all_mocked=True, assert_all_called=False) as router:
            router.route(host="127.0.0.1").pass_through()
            upstream_route = router.post("https://api.openai.com/v1/chat/completions").mock(
                return_value=httpx.Response(200, json=_upstream_payload())
            )
            response = client.chat.completions.create(
                model=TEST_MODEL,
                messages=[{"role": "user", "content": CANARY_PROMPT + "-disabled"}],
            )
            assert response.choices[0].message.content == COMPLETION_TEXT
            assert len(upstream_route.calls) == 1

    assert _usage_ledger_count(database_url, created.gateway_key_id) == 1
    assert not tmp_path.joinpath("captures").exists()


# -- fresh-process /v1/responses regression (acceptance A3) -----------------
#
# A FRESH gateway process (real uvicorn, real loopback HTTP) fronts an owned
# PG and forwards to a REAL loopback mock Local-Coding backend; the parent's
# respx cannot intercept the child's outbound traffic, so the mock backend is
# a genuine HTTP server.  Synthetic data only; this is not actual Codex CLI
# or actual model qualification.


@pytest.mark.e2e
def test_responses_capture_fresh_process_loopback_backend(
    monkeypatch: pytest.MonkeyPatch,
    owned_pg_url: str,  # noqa: F811 - fixture surfaces the owned DB
    tmp_path: Path,
) -> None:
    from tests.e2e import test_codex_0162_local_tools as h
    from slaif_gateway.modules.clients.registry import get_client_module
    from slaif_gateway.services.request_capture import (
        CaptureFacilityConfig,
        CaptureStore,
    )

    database_url = owned_pg_url
    run_alembic_upgrade_head(database_url)
    module = get_client_module("codex-0.162-responses-v1")
    module_meta = {
        "id": module.module_id,
        "version": module.module_version,
        "fixture_sha256": module.fixture_sha256,
    }
    capture_root = tmp_path / "captures"
    monkeypatch.setenv("REQUEST_CAPTURE_ENABLED", "true")
    monkeypatch.setenv("REQUEST_CAPTURE_DIR", str(capture_root))
    monkeypatch.setenv("REQUEST_CAPTURE_BODY_BUDGET_BYTES", str(10 * 1024 * 1024))
    monkeypatch.setenv("REQUEST_CAPTURE_TOTAL_STORAGE_BYTES", str(20 * 1024 * 1024))
    monkeypatch.setenv("REQUEST_CAPTURE_DEPLOYED_REVISION", "synthetic-e2e-revision")
    monkeypatch.setenv("REQUEST_CAPTURE_REVISION_PROVENANCE", "synthetic-e2e-test")
    h._configure_runtime_environment(monkeypatch, database_url)
    h._local_coding_environment(monkeypatch)

    observed: list[dict[str, str]] = []
    backend_errors: list[str] = []

    class BackendHandler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *_args: object) -> None:
            pass

        def do_POST(self) -> None:  # noqa: N802 - http.server API
            try:
                raw = self.rfile.read(int(self.headers["Content-Length"]))
                request = httpx.Request(
                    "POST",
                    f"http://127.0.0.1:{self.server.server_port}/v1/responses",
                    headers=dict(self.headers),
                    content=raw,
                )
                h._verify_local_coding_signature(request)
                assert self.headers["Authorization"] == (
                    "Bearer synthetic-local-coding-service-bearer"
                )
                assert self.headers.get("Cookie") is None
                assert self.headers.get("Proxy-Authorization") is None
                body = json.loads(raw)
                assert "client_metadata" not in body and "prompt_cache_key" not in body
                observed.append({"body_sha256": hashlib.sha256(raw).hexdigest()})
                payload = json.dumps(h._completed_response()).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
            except Exception as exc:  # noqa: BLE001 - safe class only, never content
                backend_errors.append(type(exc).__name__)
                self.send_error(500)

    backend = http.server.ThreadingHTTPServer(("127.0.0.1", 0), BackendHandler)
    backend_thread = threading.Thread(target=backend.serve_forever, daemon=True)
    backend_thread.start()

    model = "oap191-capture-e2e"
    created = asyncio.run(
        h._create_responses_test_data(
            database_url,
            model=model,
            base_url=f"http://127.0.0.1:{backend.server_port}/v1",
            **h._local_coding_test_data_kwargs(module_meta),
        )
    )

    # Whitelisted child environment only; never copy unknown secrets.
    known_env = [
        "DATABASE_URL",
        "APP_ENV",
        "GATEWAY_KEY_PREFIX",
        "GATEWAY_KEY_ACCEPTED_PREFIXES",
        "ACTIVE_HMAC_KEY_VERSION",
        "TOKEN_HMAC_SECRET_V1",
        "ADMIN_SESSION_SECRET",
        "ONE_TIME_SECRET_ENCRYPTION_KEY",
        "LOCAL_CODING_SERVICE_TOKEN",
        "LOCAL_CODING_SIGNING_SECRET_V1",
        "LOCAL_CODING_IDENTITY_DERIVATION_SECRET_V1",
    ]
    env = {name: os.environ[name] for name in known_env}
    env.update(
        {
            "PATH": "/usr/local/bin:/usr/bin:/bin",
            "PYTHONPATH": str(_REPOSITORY_ROOT / "app"),
            "REQUEST_CAPTURE_ENABLED": "true",
            "REQUEST_CAPTURE_DIR": str(capture_root),
            "REQUEST_CAPTURE_BODY_BUDGET_BYTES": str(10 * 1024 * 1024),
            "REQUEST_CAPTURE_TOTAL_STORAGE_BYTES": str(20 * 1024 * 1024),
            "REQUEST_CAPTURE_DEPLOYED_REVISION": "synthetic-e2e-revision",
            "REQUEST_CAPTURE_REVISION_PROVENANCE": "synthetic-e2e-test",
            "ENABLE_EMAIL_DELIVERY": "false",
            "PYTHONDONTWRITEBYTECODE": "1",
            "NO_COLOR": "1",
            "TERM": "dumb",
        }
    )
    gateway_port = h._free_port()
    log_path = tmp_path / "gateway.log"
    log_file = os.fdopen(os.open(log_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600), "wb")
    fail_marker = tmp_path / "fail-publish"
    child_program = (
        "import pathlib, sys, uvicorn\n"
        "from slaif_gateway.services.request_capture import CaptureStore\n"
        "original_publish = CaptureStore.write_artifact\n"
        "failure_marker = pathlib.Path(sys.argv[2])\n"
        "def controlled_publish(self, **kwargs):\n"
        "    if failure_marker.exists():\n"
        '        raise RuntimeError("synthetic-controlled-publish-failure")\n'
        "    return original_publish(self, **kwargs)\n"
        "CaptureStore.write_artifact = controlled_publish\n"
        'uvicorn.run("slaif_gateway.main:app", host="127.0.0.1", '
        "port=int(sys.argv[1]), log_level=\"warning\", access_log=False)\n"
    )
    process = subprocess.Popen(
        [sys.executable, "-c", child_program, str(gateway_port), str(fail_marker)],
        cwd=str(_REPOSITORY_ROOT),
        env=env,
        stdout=log_file,
        stderr=subprocess.STDOUT,
    )
    try:
        for _ in range(120):
            assert process.poll() is None, "gateway child exited before readiness"
            try:
                if (
                    httpx.get(
                        f"http://127.0.0.1:{gateway_port}/healthz", timeout=1, trust_env=False
                    ).status_code
                    == 200
                ):
                    break
            except httpx.HTTPError:
                pass
            time.sleep(0.1)
        else:
            raise AssertionError("gateway readiness timeout")

        store = CaptureStore(
            CaptureFacilityConfig(
                True,
                capture_root,
                10 * 1024 * 1024,
                20 * 1024 * 1024,
                100,
                3600,
                "synthetic-e2e-revision",
                "synthetic-e2e-test",
                "0.1.0",
            )
        )
        key = created.plaintext_key
        key_uuid = str(created.gateway_key_id)
        cookie = f"COOKIE_CANARY_191_{secrets.token_hex(4)}"
        proxy = f"PROXY_CANARY_191_{secrets.token_hex(4)}"
        basic = base64.b64encode(("synthetic-user:" + proxy).encode()).decode()
        headers = [
            ("Authorization", "Bearer " + key),
            ("Cookie", "session=" + cookie),
            ("Proxy-Authorization", "Basic " + basic),
            ("Content-Type", "application/json"),
        ]
        query = "?keep=PRESERVE_QUERY&api_key=" + "".join(
            "%{:02X}".format(b) for b in cookie.encode()
        )
        namespace = {
            "type": "namespace",
            "name": "mcp__codex_apps__github",
            "description": "PRESERVE_NAMESPACE_DESCRIPTION",
            "tools": [h._function_tool("_read_page")],
        }
        declaration = {
            "type": "additional_tools",
            "id": "at_oap191_e2e",
            "role": "developer",
            "tools": [namespace],
        }
        valid = {
            "model": model,
            "input": [
                declaration,
                {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": "PRESERVE_PRIVATE_PROMPT"}],
                },
            ],
            "stream": False,
            "store": False,
            "max_output_tokens": 8,
            "prompt_cache_key": h.SESSION,
            "client_metadata": h._metadata(),
        }
        invalid = copy.deepcopy(valid)
        invalid["input"][0]["tools"][0]["tools"][0]["name"] = "_INVALID"
        malformed = (
            '{"instructions":"PRESERVE_INSTRUCTIONS","copy":"'
            + key
            + '","cookie_copy":"'
            + cookie
            + '","password":"'
            + proxy
            + '","arguments":"PRESERVE_TOOL_ARGUMENTS","result":"PRESERVE_TOOL_RESULTS",'
            '"session_id":"PRESERVE_SESSION_ID","unfinished":'
        ).encode()
        valid_json = json.dumps(valid, separators=(",", ":")).encode()

        def matching_artifact(request_id: str) -> tuple[dict, dict]:
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                candidate = next(
                    (capture_root / "captures").glob(f"*/{request_id}.capture.json"), None
                )
                if candidate is not None:
                    record_path = candidate.with_name(request_id + ".record.json")
                    if record_path.is_file():
                        return json.loads(candidate.read_bytes()), json.loads(record_path.read_bytes())
                time.sleep(0.05)
            raise AssertionError(f"no artifact for {request_id}")

        def assert_recorded_public_error(record: dict, response: httpx.Response) -> None:
            rejection = record.get("rejection")
            assert isinstance(rejection, dict)
            public = response.json()["error"]
            assert rejection["error_code"] == public["code"]
            assert rejection["error_message"] == public["message"]
            assert rejection["error_param"] == public.get("param")
            assert rejection["status_code"] == response.status_code

        with httpx.Client(timeout=30, trust_env=False) as client:
            base = f"http://127.0.0.1:{gateway_port}/v1/responses"

            # Unarmed baseline: default-OFF, nothing stored, forwarding works.
            baseline = client.post(base + query, headers=headers, content=valid_json)
            assert baseline.status_code == 200
            assert len(observed) == 1
            assert _artifacts(capture_root) == {}

            # Filtered window: a bad-HMAC key with the same public ID gets 401
            # and must NOT consume the verified-key-filtered window.
            session = store.arm(
                endpoint="/v1/responses", key_uuid=key_uuid, count=1, ttl_seconds=120
            )
            wrong_key = key[:-1] + ("A" if key[-1] != "A" else "B")
            unauthorized = client.post(
                base,
                headers={
                    "Authorization": "Bearer " + wrong_key,
                    "Content-Type": "application/json",
                },
                content=json.dumps(valid).encode(),
            )
            assert unauthorized.status_code == 401
            remaining = next(
                s for s in store.status() if s.session_id == session.session_id
            ).remaining
            assert remaining == 1

            # Malformed JSON: full original bytes captured (masked), precise
            # decoder + public validation facts, actual verified UUID.
            rejected_body = client.post(base + query, headers=headers, content=malformed)
            assert rejected_body.status_code == 422
            capture, record = matching_artifact(
                rejected_body.headers.get("x-slaif-diagnostic-id", "")
            )
            stored = base64.b64decode(capture["body"])
            expected = (
                malformed.replace(key.encode(), record["recognized_hint"].encode())
                .replace(cookie.encode(), b"[REDACTED]")
                .replace(proxy.encode(), b"[REDACTED]")
            )
            assert stored == expected
            assert capture["body_complete"] is True
            assert record["verified_key_uuid"] == key_uuid
            # Malformed JSON is rejected BEFORE the normal-auth dependency runs,
            # so the verified UUID comes from the observer's read-only probe.
            assert record["verified_key_provenance"] == "read_only_capture_probe"
            assert_recorded_public_error(record, rejected_body)
            first = record["rejection"]["errors"][0]
            assert first["error_type"] == "json_invalid"
            loc = first["loc"]
            assert isinstance(loc, list) and loc and loc[0] == "body"
            # The actual JSON parser position: a nonnegative integer offset.
            assert any(
                isinstance(part, int) and not isinstance(part, bool) and part >= 0
                for part in loc[1:]
            )
            assert first["json_error"]
            material = json.dumps(record).encode() + json.dumps(capture).encode()
            assert cookie.encode() not in material
            assert proxy.encode() not in material
            assert key.encode() not in material
            assert next(
                s for s in store.status() if s.session_id == session.session_id
            ).remaining == 0

            # Invalid tool name: precise taxonomy facts + actual module
            # identity (id/version/digest) + full original body.
            session = store.arm(
                endpoint="/v1/responses", key_uuid=key_uuid, count=1, ttl_seconds=120
            )
            invalid_json = json.dumps(invalid, separators=(",", ":")).encode()
            invalid_body = client.post(base + query, headers=headers, content=invalid_json)
            assert invalid_body.status_code == 400
            capture, record = matching_artifact(
                invalid_body.headers.get("x-slaif-diagnostic-id", "")
            )
            stored = base64.b64decode(capture["body"])
            assert stored == invalid_json.replace(
                key.encode(), record["recognized_hint"].encode()
            ).replace(cookie.encode(), b"[REDACTED]").replace(proxy.encode(), b"[REDACTED]")
            assert_recorded_public_error(record, invalid_body)
            rejection = record["rejection"]
            assert rejection["reason_code"] == "tool_name_not_allowed"
            assert rejection["tool_index"] == 0
            assert rejection["namespace_index"] == 0
            assert record["module_id"] == module_meta["id"]
            assert record["module_version"] == module_meta["version"]
            assert record["module_fixture_sha256"] == module_meta["fixture_sha256"]

            # Successful admission: full artifact + finalized accounting.
            session = store.arm(
                endpoint="/v1/responses", key_uuid=key_uuid, count=1, ttl_seconds=120
            )
            accepted = client.post(base + query, headers=headers, content=valid_json)
            assert accepted.status_code == baseline.status_code == 200
            capture, record = matching_artifact(
                accepted.headers.get("x-slaif-diagnostic-id", "")
            )
            stored = base64.b64decode(capture["body"])
            assert stored == valid_json.replace(
                key.encode(), record["recognized_hint"].encode()
            ).replace(cookie.encode(), b"[REDACTED]").replace(proxy.encode(), b"[REDACTED]")
            assert capture["body_complete"] is True
            assert record["status_code"] == 200
            assert record["verified_key_uuid"] == key_uuid
            assert record["module_id"] == module_meta["id"]
            assert record["module_version"] == module_meta["version"]
            assert record["module_fixture_sha256"] == module_meta["fixture_sha256"]

            # Controlled publication failure: the app result is unchanged and
            # the claim is consumed (no endless capture).
            session = store.arm(
                endpoint="/v1/responses", key_uuid=key_uuid, count=1, ttl_seconds=120
            )
            fail_marker.write_text("synthetic controlled publication failure")
            try:
                failed = client.post(base + query, headers=headers, content=valid_json)
                assert failed.status_code == 200
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    state = next(
                        s for s in store.status() if s.session_id == session.session_id
                    )
                    if state.remaining == 0:
                        break
                    time.sleep(0.05)
                assert state.remaining == 0
            finally:
                fail_marker.unlink()

            # Forwarding parity: every provider request (including the failed
            # publish) carried the identical original provider payload.
            assert len(observed) == 3
            assert len({o["body_sha256"] for o in observed}) == 1
            assert not backend_errors

        counters = asyncio.run(h._load_gateway_key_counters(database_url, created.gateway_key_id))
        ledger = asyncio.run(h._load_ledger_rows(database_url, created.gateway_key_id))
        assert counters == (3, 15)
        assert ledger == [(5, "finalized")] * 3

        logs = log_path.read_bytes()
        for canary in (
            key.encode(),
            key.split(".", 1)[1].encode(),
            cookie.encode(),
            proxy.encode(),
            basic.encode(),
        ):
            assert canary not in logs
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        log_file.close()
        backend.shutdown()
        backend.server_close()
        backend_thread.join(timeout=5)
