"""Fresh-process HTTP Gateway E2E for file-backed Codex 0.162 profile DATA.

A real uvicorn subprocess boots the genuine ``slaif_gateway.main:app`` with
``CODEX_COMPATIBILITY_PROFILE_FILE`` pointing at an external revision-4
profile (the same installed engine and code; only the trusted DATA file
differs from the packaged default).  The mock Local Coding backend runs in
the test process; no real model, provider, or plugin is involved.  The
synthetic declaration is labeled not-a-capture.

Proved:

- the external revision-4 file is accepted by the fresh process and its
  DATA-only rule (two bounded leading underscores) enables
  ``__future_tool`` where the packaged revision-3 default rejects it;
- a key still pinned to the stale revision-3 tuple is denied before
  side effects (no backend call, no accounting);
- ``slaif-gateway codex show-profile`` in a matching CLI process reports
  the same active identity as the HTTP snapshot;
- editing the profile file after the process loaded it cannot mutate the
  in-flight policy;
- a configured profile file that is invalid refuses startup (no silent
  fallback).
"""

from __future__ import annotations

import asyncio
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time

import httpx
import pytest

from tests.e2e.test_openai_python_client_chat import (
    FAKE_GENERIC_UPSTREAM_KEY,
    FAKE_OPENAI_UPSTREAM_KEY,
    FAKE_OPENROUTER_UPSTREAM_KEY,
    TEST_ADMIN_SECRET,
    TEST_HMAC_SECRET,
    TEST_ONE_TIME_SECRET_KEY,
    _configure_runtime_environment,
    _free_port,
    _load_accounting_side_effect_counts,
    _load_accounting_state,
    _run_uvicorn_server,
)
from tests.e2e.test_openai_python_client_responses import _create_responses_test_data
from tests.integration.db_test_utils import run_alembic_upgrade_head
from tests.integration.test_lazy_throttling_postgres_redis import (  # noqa: F401
    owned_pg_url,
)
from tests.e2e.test_codex_0162_local_tools import (
    ALL_FOUR_CODEX_GRANTS,
    CODEX_ROUTE_LIMITS,
    LOCAL_CODING_SIGNING_SECRET,
    SESSION,
    _completed_response,
    _function_tool,
    _local_coding_environment,
    _load_gateway_key_counters,
    _load_ledger_rows,
    _metadata,
    _verify_local_coding_signature,
)
from slaif_gateway.modules.clients.codex_0162 import (
    CODEX_0162_CLIENT_MODULE_ID,
    CODEX_0162_CLIENT_MODULE_VERSION,
    CODEX_0162_FIXTURE_SHA256,
)
from slaif_gateway.modules.codex_profile_data import load_codex_profile_file

LOCAL_CODING_ROUTE_NAME = "vision"


def _revision4_profile_document() -> dict[str, object]:
    """The packaged default with the DATA-only revision-4 rule applied."""
    document = {
        "schema_version": 1,
        "module_id": CODEX_0162_CLIENT_MODULE_ID,
        "revision": "4",
        "provenance": {
            "cli_version": "0.162.1",
            "source_tag": "rust-v0.162.1",
            "source_commit": "092d3acd6bec3e3a14bdc7e7a2810ab628ab759d",
        },
        "namespace_rules": {
            "builtin_names": ["functions", "multi_agent_v1"],
            "connector_prefixes": ["mcp__codex_apps__"],
            "suffix_initial": "lowercase_ascii",
            "suffix_tail": "lowercase_ascii_digits_underscore_dot_hyphen",
            "max_suffix_characters": 64,
        },
        "tool_name_rules": {
            "builtin": {
                "initial": "lowercase_ascii",
                "tail": "lowercase_ascii_digits_underscore_dot_hyphen",
                "max_characters": 64,
                "max_leading_underscores": 0,
            },
            "connector": {
                "initial": "lowercase_ascii",
                "tail": "lowercase_ascii_digits_underscore_dot_hyphen",
                "max_characters": 64,
                "max_leading_underscores": 2,
            },
        },
        "limits": {
            "max_namespaces": 16,
            "max_total_tools": 256,
            "max_tools_per_namespace": 256,
            "max_schema_depth": 16,
            "max_schema_properties": 4096,
            "max_tool_description_bytes": 20000,
            "max_total_description_bytes": 262144,
            "max_declaration_bytes": 589824,
        },
    }
    return document


def _future_tools_item() -> dict[str, object]:
    return {
        "type": "additional_tools",
        "role": "developer",
        "tools": [
            {
                "type": "namespace",
                "name": "mcp__codex_apps__future",
                "description": "synthetic future connector namespace (not a capture)",
                "tools": [_function_tool("__future_tool")],
            }
        ],
    }


BackendCall = tuple[dict[str, object], dict[str, str], bytes]


def _mock_backend_asgi(requests: list[BackendCall]):
    async def app(scope, receive, send) -> None:
        if scope["type"] == "lifespan":
            while True:
                message = await receive()
                if message["type"] == "lifespan.startup":
                    await send({"type": "lifespan.startup.complete"})
                elif message["type"] == "lifespan.shutdown":
                    await send({"type": "lifespan.shutdown.complete"})
                    return
            return
        assert scope["type"] == "http"
        headers = {k.decode("latin-1"): v.decode("latin-1") for k, v in scope["headers"]}
        body = b""
        while True:
            message = await receive()
            body += message.get("body", b"")
            if not message.get("more_body"):
                break
        payload = json.loads(body)
        requests.append((payload, headers, body))
        content = json.dumps(_completed_response()).encode("utf-8")
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"content-type", b"application/json")],
            }
        )
        await send({"type": "http.response.body", "body": content})

    return app


def _gateway_env(database_url: str, profile_file: str) -> dict[str, str]:
    """Whitelisted subprocess environment for the fresh gateway process.

    Only explicit fixture-synthetic settings, the owned test database URL,
    the app import path, and the profile path are passed; the parent
    environment is never copied wholesale, so no ambient or unknown
    secret-version values can reach the subprocess.
    """
    return {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONPATH": str(pathlib.Path(__file__).resolve().parents[2] / "app"),
        "DATABASE_URL": database_url,
        "APP_ENV": "test",
        "GATEWAY_KEY_PREFIX": "sk-slaif-",
        "GATEWAY_KEY_ACCEPTED_PREFIXES": "sk-slaif-",
        "ACTIVE_HMAC_KEY_VERSION": "1",
        "TOKEN_HMAC_SECRET_V1": TEST_HMAC_SECRET,
        "ADMIN_SESSION_SECRET": TEST_ADMIN_SECRET,
        "ONE_TIME_SECRET_ENCRYPTION_KEY": TEST_ONE_TIME_SECRET_KEY,
        "OPENAI_UPSTREAM_API_KEY": FAKE_OPENAI_UPSTREAM_KEY,
        "OPENROUTER_API_KEY": FAKE_OPENROUTER_UPSTREAM_KEY,
        "GENERIC_UPSTREAM_KEY": FAKE_GENERIC_UPSTREAM_KEY,
        "LOCAL_CODING_SERVICE_TOKEN": "synthetic-local-coding-service-bearer",
        "LOCAL_CODING_SIGNING_SECRET_V1": LOCAL_CODING_SIGNING_SECRET,
        "LOCAL_CODING_IDENTITY_DERIVATION_SECRET_V1": "local-coding-derivation-secret-0123456789",
        "CODEX_COMPATIBILITY_PROFILE_FILE": profile_file,
    }


def _start_gateway(port: int, env: dict[str, str]) -> subprocess.Popen:
    return subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "slaif_gateway.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )


def _wait_for_gateway(process: subprocess.Popen, port: int, timeout: float = 90.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            output = process.stdout.read().decode("utf-8", "replace")
            raise AssertionError(f"gateway process exited early: {output[-2000:]}")
        try:
            if httpx.get(f"http://127.0.0.1:{port}/healthz", timeout=2).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.2)
    process.terminate()
    raise TimeoutError("gateway never became ready")


def _stop_gateway(process: subprocess.Popen) -> None:
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()


def _post_responses(
    port: int,
    api_key: str,
    model: str,
    text: str,
) -> httpx.Response:
    with httpx.Client(base_url=f"http://127.0.0.1:{port}/v1", timeout=30) as client:
        return client.post(
            "/responses",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model,
                "input": [
                    _future_tools_item(),
                    {
                        "type": "message",
                        "role": "user",
                        "content": [{"type": "input_text", "text": text}],
                    },
                ],
                "client_metadata": _metadata(),
                "prompt_cache_key": SESSION,
            },
        )


def _local_coding_kwargs(client_module: dict[str, object]) -> dict[str, object]:
    return {
        "provider": "local-coding",
        "upstream_model": "qwen3.8-27b",
        "api_key_env_var": "LOCAL_CODING_SERVICE_TOKEN",
        "streaming": True,
        "local_coding_contract": {
            "contract_version": "local-coding-v1",
            "route_name": LOCAL_CODING_ROUTE_NAME,
            "tool_policy_version": "responses-tool-policy-v1",
            "identity_mode": "signed_identity_v1",
            "replay_mode": "process_local_inclusive_horizon_fail_closed",
            "deployment_mode": "single_worker",
            "clock_skew_seconds": 60,
            "replay_ttl_seconds": 60,
        },
        "responses_policy": {
            "version": 1,
            "local_coding_repository_scope": "signed-thread-repository",
            "allowed_capabilities": list(ALL_FOUR_CODEX_GRANTS),
            "client_module": client_module,
        },
        "codex_request_envelope": True,
        "codex_client_tools": True,
        "codex_streaming_tool_events": True,
        "codex_encrypted_reasoning_replay": True,
        "codex_route_limits": CODEX_ROUTE_LIMITS,
    }


@pytest.mark.e2e
def test_codex_profile_data_fresh_process_http_gateway(
    monkeypatch: pytest.MonkeyPatch,
    owned_pg_url: str,  # noqa: F811
) -> None:
    database_url = owned_pg_url
    run_alembic_upgrade_head(database_url)
    _configure_runtime_environment(monkeypatch, database_url)
    _local_coding_environment(monkeypatch)

    workdir = pathlib.Path(tempfile.mkdtemp(prefix="slaif-190b-profiledata-"))
    try:
        # The external revision-4 DATA file; the same installed engine
        # loads it.
        profile_path = workdir / "codex_0162_rev4.json"
        profile_path.write_text(
            json.dumps(_revision4_profile_document(), indent=2), encoding="utf-8"
        )
        active_profile = load_codex_profile_file(str(profile_path))
        active_facts = active_profile.to_facts()
        assert active_facts["revision"] == "4"
        assert active_facts["digest"] != CODEX_0162_FIXTURE_SHA256

        _run_fresh_process_profile_data_flow(database_url, workdir, profile_path, active_facts)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def _run_fresh_process_profile_data_flow(
    database_url: str,
    workdir: pathlib.Path,
    profile_path: pathlib.Path,
    active_facts: dict[str, object],
) -> None:

    # Both routes forward to the one in-test mock backend.
    local_port = _free_port()
    active_key = asyncio.run(
        _create_responses_test_data(
            database_url,
            model="codex-0162-profiledata-active",
            base_url=f"http://127.0.0.1:{local_port}/v1",
            **_local_coding_kwargs(
                {
                    "id": CODEX_0162_CLIENT_MODULE_ID,
                    "version": str(active_facts["revision"]),
                    "fixture_sha256": str(active_facts["digest"]),
                }
            ),
        )
    )
    stale_key = asyncio.run(
        _create_responses_test_data(
            database_url,
            model="codex-0162-profiledata-stale",
            base_url=f"http://127.0.0.1:{local_port}/v1",
            **_local_coding_kwargs(
                {
                    "id": CODEX_0162_CLIENT_MODULE_ID,
                    "version": CODEX_0162_CLIENT_MODULE_VERSION,
                    "fixture_sha256": CODEX_0162_FIXTURE_SHA256,
                }
            ),
        )
    )

    backend_requests: list[BackendCall] = []
    gateway_port = _free_port()

    with _run_uvicorn_server(_mock_backend_asgi(backend_requests), local_port):
        env = _gateway_env(database_url, str(profile_path))
        gateway = _start_gateway(gateway_port, env)
        try:
            _wait_for_gateway(gateway, gateway_port)

            # 1) Active revision-4 pin: the DATA-only rule accepts
            #    __future_tool end to end through the fresh HTTP process.
            ok = _post_responses(
                gateway_port,
                active_key.plaintext_key,
                "codex-0162-profiledata-active",
                "profile data revision four",
            )
            assert ok.status_code == 200, ok.text
            assert len(backend_requests) == 1
            _assert_forwarded_call(backend_requests[0])

            # 2) Stale revision-3 pin: denied before side effects.
            stale = _post_responses(
                gateway_port,
                stale_key.plaintext_key,
                "codex-0162-profiledata-stale",
                "stale pin rejected",
            )
            assert 400 <= stale.status_code < 500
            error_body = stale.json()
            assert "error" in error_body
            assert len(backend_requests) == 1  # no new backend call
            assert asyncio.run(
                _load_gateway_key_counters(database_url, stale_key.gateway_key_id)
            ) == (0, 0)
            assert asyncio.run(
                _load_accounting_side_effect_counts(database_url, stale_key.gateway_key_id)
            ) == (0, 0)

            # 3) CLI show-profile matches the HTTP snapshot.
            cli = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    (
                        "import sys; sys.argv = ["
                        "'slaif-gateway', 'codex', 'show-profile', '--json'];"
                        " from slaif_gateway.cli.main import app; app()"
                    ),
                ],
                env=env,
                capture_output=True,
                text=True,
                timeout=120,
            )
            assert cli.returncode == 0, cli.stderr
            shown = json.loads(cli.stdout)
            assert shown["revision"] == str(active_facts["revision"])
            assert shown["digest"] == str(active_facts["digest"])
            assert shown["client_module_id"] == CODEX_0162_CLIENT_MODULE_ID

            # 4) Editing the file after load cannot mutate in-flight policy:
            #    the running gateway keeps its revision-4 snapshot.
            default_bytes = (
                pathlib.Path(__file__).resolve().parents[2]
                / "app"
                / "slaif_gateway"
                / "modules"
                / "clients"
                / "profiles"
                / "codex_0162.json"
            ).read_bytes()
            profile_path.write_bytes(default_bytes)
            still_ok = _post_responses(
                gateway_port,
                active_key.plaintext_key,
                "codex-0162-profiledata-active",
                "in-flight snapshot unchanged",
            )
            assert still_ok.status_code == 200, still_ok.text
            assert len(backend_requests) == 2
            _assert_forwarded_call(backend_requests[1])
        finally:
            _stop_gateway(gateway)

    # 5) The fresh process finalized accounting for the accepted request only.
    state = asyncio.run(
        _load_accounting_state(database_url, active_key.gateway_key_id, provider="local-coding")
    )
    assert state.gateway_key.requests_used_total == 2
    assert asyncio.run(_load_ledger_rows(database_url, active_key.gateway_key_id)) == [
        (5, "finalized"),
        (5, "finalized"),
    ]


@pytest.mark.e2e
def _assert_forwarded_call(call: BackendCall) -> None:
    """Verify the signed Local Coding provider leg of one forwarded call."""
    payload, headers, body = call
    request = httpx.Request(
        "POST",
        "http://127.0.0.1:0/v1/responses",
        headers=headers,
        content=body,
    )
    # Final HMAC over the exact canonical identity, opaque session, and the
    # prompt_cache_key/metadata omission are proven by the shared helper.
    _verify_local_coding_signature(request)
    assert headers["authorization"] == "Bearer synthetic-local-coding-service-bearer"
    tools = payload["tools"]
    assert [namespace["name"] for namespace in tools] == ["mcp__codex_apps__future"]
    assert [tool["name"] for tool in tools[0]["tools"]] == ["__future_tool"]


@pytest.mark.e2e
def test_codex_profile_data_invalid_configured_file_refuses_startup() -> None:
    with tempfile.TemporaryDirectory(prefix="slaif-190b-badprofile-") as directory:
        bad = pathlib.Path(directory) / "bad-profile.json"
        bad.write_text("{not json", encoding="utf-8")
        port = _free_port()
        env = _gateway_env("postgresql+asyncpg://test:test@127.0.0.1:1/unused", str(bad))
        gateway = _start_gateway(port, env)
        try:
            deadline = time.monotonic() + 30
            refused = False
            while time.monotonic() < deadline:
                if gateway.poll() is not None:
                    refused = gateway.returncode != 0
                    break
                try:
                    if httpx.get(f"http://127.0.0.1:{port}/healthz", timeout=1).status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(0.2)
            assert refused, (
                "gateway with an invalid configured profile file must refuse "
                "startup, never fall back to the packaged default"
            )
        finally:
            _stop_gateway(gateway)
