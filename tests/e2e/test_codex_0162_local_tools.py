"""Full-gateway E2E for the registered 0.162 additional-tools profile.

Real gateway (auth, module resolution, request policy, admission, Local
Coding signed transport) forwarding to an owned loopback mock backend with no
real model or provider.  The synthetic 197-tool declaration keeps exactly the
operator-supplied namespace counts (11 + 5 + 181).  For this approved pair the
validated initial declaration is lowered to the existing top-level tools
namespace array before final provider serialization and HMAC signing: the
provider body carries the exact validated namespace/tool definitions with the
declaration item and its ID omitted, while the signed opaque identity, the
prompt_cache_key privacy omission, and the conservative accounting of the
original declaration material all remain in force.  The positive test uses
the fully gated four-grant key, which derives extended limits and therefore
requires the existing route prerequisites: the fourth route capability
(codex_encrypted_reasoning_replay) plus a valid codex_limits numeric
contract; a dedicated negative proves a route missing the fourth grant
fails closed before admission.
  The database is the owned,
labelled, loopback PostgreSQL fixture from the lazy-throttling integration
module; it is surfaced to the existing E2E harness through TEST_DATABASE_URL.
"""

from __future__ import annotations

import asyncio
import json
import uuid

import httpx
import pytest
import respx
from openai import OpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from tests.e2e.test_openai_python_client_chat import (
    _configure_runtime_environment,
    _free_port,
    _load_accounting_side_effect_counts,
    _load_accounting_state,
    _run_uvicorn_server,
)
from tests.e2e.test_openai_python_client_responses import (
    _codex_standard_stream,
    _codex_vllm_usage,
    _create_responses_test_data,
)
from tests.integration.db_test_utils import run_alembic_upgrade_head
from tests.integration.test_lazy_throttling_postgres_redis import (  # noqa: F401
    owned_pg_url,
)
from slaif_gateway.modules.clients.codex_0149 import (
    CODEX_0149_CLIENT_MODULE_VERSION,
    CODEX_0149_FIXTURE_SHA256,
)
from slaif_gateway.modules.clients.codex_0162 import (
    CODEX_0162_CLIENT_MODULE_ID,
    CODEX_0162_CLIENT_MODULE_VERSION,
    CODEX_0162_FIXTURE_SHA256,
)
from slaif_gateway.modules.servers.local_coding.identity import (
    LocalCodingRequestIdentity,
    canonical_identity_bytes,
    expected_signature,
)

AT_UUID = "at_123e4567-e89b-12d3-a456-426614174000"
SESSION = "123e4567-e89b-12d3-a456-426614174000"
LOCAL_CODING_SIGNING_SECRET = "local-coding-signing-secret-012345678901"
MCP_NAMESPACE_COUNTS = {
    "mcp__codex_apps__chatgpt_space": 40,
    "mcp__codex_apps__codex_document_control": 3,
    "mcp__codex_apps__github": 89,
    "mcp__codex_apps__hotline": 1,
    "mcp__codex_apps__pets": 11,
    "mcp__codex_apps__plugin_management": 6,
    "mcp__codex_apps__safety_settings": 5,
    "mcp__codex_apps__search_service": 1,
    "mcp__codex_apps__sites": 25,
}


def _function_tool(name: str) -> dict[str, object]:
    return {
        "type": "function",
        "name": name,
        "description": f"synthetic bounded description for {name}",
        "parameters": {
            "type": "object",
            "properties": {"value": {"type": "string"}},
            "required": ["value"],
            "additionalProperties": False,
        },
        "strict": True,
    }


def _synthetic_197_additional_tools_item() -> dict[str, object]:
    namespaces: list[dict[str, object]] = [
        {
            "type": "namespace",
            "name": "functions",
            "description": "bounded local function namespace",
            "tools": [
                _function_tool(name)
                for name in (
                    "exec_command",
                    "write_stdin",
                    "request_user_input",
                    "view_image",
                    "get_goal",
                    "create_goal",
                    "update_goal",
                    "plan_step",
                    "read_file",
                    "list_files",
                    "apply_diff",
                )
            ],
        },
        {
            "type": "namespace",
            "name": "multi_agent_v1",
            "description": "bounded local multi-agent namespace",
            "tools": [
                _function_tool(name)
                for name in (
                    "close_agent",
                    "resume_agent",
                    "send_input",
                    "spawn_agent",
                    "wait_agent",
                )
            ],
        },
    ]
    for namespace, count in MCP_NAMESPACE_COUNTS.items():
        prefix = namespace.split("__")[-1][:6]
        namespaces.append(
            {
                "type": "namespace",
                "name": namespace,
                "description": "synthetic plugin namespace (not an installed plugin)",
                "tools": [_function_tool(f"{prefix}_tool_{i:03d}") for i in range(count)],
            }
        )
    return {
        "type": "additional_tools",
        "id": AT_UUID,
        "role": "developer",
        "tools": namespaces,
    }


def _metadata() -> dict[str, str]:
    return {
        "session_id": SESSION,
        "thread_id": SESSION,
        "turn_id": "00000000-0000-4000-8000-000000000001",
        "x-codex-installation-id": "00000000-0000-4000-8000-000000000002",
        "x-codex-window-id": "00000000-0000-4000-8000-000000000003",
    }


def _completed_response() -> dict[str, object]:
    return {
        "id": "codex-0162-e2e-response",
        "object": "response",
        "created_at": 123,
        "status": "completed",
        "model": "qwen3.8-27b",
        "output": [
            {
                "type": "message",
                "id": "parser_message_1",
                "status": "completed",
                "role": "assistant",
                "content": [
                    {
                        "type": "output_text",
                        "text": "answer",
                        "annotations": [],
                        "logprobs": None,
                    }
                ],
                "phase": None,
            }
        ],
        "usage": _codex_vllm_usage(3, 2),
    }


def _assert_forwarded_197_lowered(
    body: dict[str, object], *, message_text: str, max_output_tokens: int | None
) -> None:
    tools = body["tools"]
    assert isinstance(tools, list)
    assert len(tools) == 11
    counts = {
        str(namespace["name"]): len(namespace["tools"]) for namespace in tools
    }
    assert counts["functions"] == 11
    assert counts["multi_agent_v1"] == 5
    for namespace, count in MCP_NAMESPACE_COUNTS.items():
        assert counts[namespace] == count
    assert sum(counts.values()) == 197
    for namespace in tools:
        assert namespace["type"] == "namespace"
        assert namespace["name"] in counts
        for tool in namespace["tools"]:
            assert tool["type"] == "function"
            assert tool["description"] == (
                f"synthetic bounded description for {tool['name']}"
            )
            assert tool["parameters"] == {
                "type": "object",
                "properties": {"value": {"type": "string"}},
                "required": ["value"],
                "additionalProperties": False,
            }
            assert tool["strict"] is True
    by_name = {str(namespace["name"]): namespace for namespace in tools}
    assert by_name["functions"]["description"] == "bounded local function namespace"
    assert by_name["multi_agent_v1"]["description"] == (
        "bounded local multi-agent namespace"
    )
    assert [str(namespace["name"]) for namespace in tools] == [
        "functions",
        "multi_agent_v1",
        *MCP_NAMESPACE_COUNTS,
    ]
    # The declaration item and its ID are omitted; the remaining input is
    # preserved in order.
    assert body["input"] == [
        {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": message_text}],
        }
    ]
    serialized = json.dumps(body)
    assert AT_UUID not in serialized
    assert SESSION not in serialized
    assert "client_metadata" not in body
    assert "prompt_cache_key" not in body
    # Fully gated requests finalize the route numeric contract; the applied
    # default output is forwarded, never a client-chosen value.
    if max_output_tokens is not None:
        assert body["max_output_tokens"] == max_output_tokens


def _verify_local_coding_signature(request: httpx.Request) -> None:
    headers = request.headers
    identity = LocalCodingRequestIdentity(
        principal=headers["x-slaif-principal"],
        session=headers["x-slaif-session"],
        repository=headers["x-slaif-repository"],
        route=headers["x-slaif-route"],
        identity_mode="signed_identity_v1",
    )
    canonical = canonical_identity_bytes(
        method="POST",
        path="/v1/responses",
        raw_query=b"",
        body=request.content,
        identity=identity,
        timestamp=headers["x-slaif-timestamp"],
        nonce=headers["x-slaif-nonce"],
    )
    assert headers["x-slaif-signature"] == expected_signature(
        secret=LOCAL_CODING_SIGNING_SECRET.encode("utf-8"), canonical=canonical
    )
    # Opaque identity: the raw session affinity never appears in the signed
    # headers or the provider body.
    assert headers["x-slaif-route"] == "vision"
    assert headers["x-slaif-principal"].startswith("h")
    assert SESSION not in headers["x-slaif-session"]
    assert SESSION not in request.content.decode("utf-8")


async def _load_ledger_rows(
    database_url: str, gateway_key_id: uuid.UUID
) -> list[tuple[int, str]]:
    from slaif_gateway.db.models import UsageLedger

    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            rows = (
                await session.execute(
                    select(UsageLedger)
                    .where(UsageLedger.gateway_key_id == gateway_key_id)
                    .order_by(UsageLedger.created_at.asc())
                )
            ).scalars()
            return [(int(row.total_tokens), row.accounting_status) for row in rows.all()]
    finally:
        await engine.dispose()


async def _load_gateway_key_counters(
    database_url: str, gateway_key_id: uuid.UUID
) -> tuple[int, int]:
    from slaif_gateway.db.models import GatewayKey

    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            key = await session.get(GatewayKey, gateway_key_id)
            return int(key.requests_used_total), int(key.tokens_used_total)
    finally:
        await engine.dispose()


def _local_coding_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOCAL_CODING_SERVICE_TOKEN", "synthetic-local-coding-service-bearer")
    monkeypatch.setenv("LOCAL_CODING_SIGNING_SECRET_V1", LOCAL_CODING_SIGNING_SECRET)
    monkeypatch.setenv(
        "LOCAL_CODING_IDENTITY_DERIVATION_SECRET_V1", "local-coding-derivation-secret-0123456789"
    )


# Fully gated key grant set: with all four Codex key grants,
# responses_codex_extended_limits_allowed derives true, and the route must
# additionally carry codex_encrypted_reasoning_replay plus a valid
# codex_limits numeric contract (an existing deployment prerequisite of the
# route gate, not a property of the 0.162 profile).
ALL_FOUR_CODEX_GRANTS = [
    "codex_request_envelope",
    "codex_client_tools",
    "codex_streaming_tool_events",
    "codex_encrypted_reasoning_replay",
]
CODEX_ROUTE_LIMITS = {
    "context_window_tokens": 131072,
    "default_max_output_tokens": 32768,
    "max_output_tokens": 128000,
}


def _local_coding_test_data_kwargs(
    client_module: dict[str, object], *, four_grants: bool = True
) -> dict[str, object]:
    return {
        "provider": "local-coding",
        "upstream_model": "qwen3.8-27b",
        "api_key_env_var": "LOCAL_CODING_SERVICE_TOKEN",
        "streaming": True,
        "local_coding_contract": {
            "contract_version": "local-coding-v1",
            "route_name": "vision",
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
            "allowed_capabilities": (
                ALL_FOUR_CODEX_GRANTS if four_grants else ALL_FOUR_CODEX_GRANTS[:3]
            ),
            "client_module": client_module,
        },
        "codex_request_envelope": True,
        "codex_client_tools": True,
        "codex_streaming_tool_events": True,
        "codex_encrypted_reasoning_replay": four_grants,
        "codex_route_limits": CODEX_ROUTE_LIMITS if four_grants else None,
    }


@pytest.mark.e2e
def test_codex_0162_197_tool_profile_full_gateway(
    monkeypatch: pytest.MonkeyPatch,
    owned_pg_url: str,  # noqa: F811
) -> None:
    database_url = owned_pg_url
    run_alembic_upgrade_head(database_url)
    _configure_runtime_environment(monkeypatch, database_url)
    _local_coding_environment(monkeypatch)
    local_model = "codex-0162-local-tools-test"
    local_port = _free_port()
    created = asyncio.run(
        _create_responses_test_data(
            database_url,
            model=local_model,
            base_url=f"http://127.0.0.1:{local_port}/v1",
            **_local_coding_test_data_kwargs(
                {
                    "id": CODEX_0162_CLIENT_MODULE_ID,
                    "version": CODEX_0162_CLIENT_MODULE_VERSION,
                    "fixture_sha256": CODEX_0162_FIXTURE_SHA256,
                }
            ),
        )
    )

    from slaif_gateway.config import get_settings
    from slaif_gateway.main import create_app

    get_settings.cache_clear()
    gateway_port = _free_port()
    monkeypatch.setenv("OPENAI_API_KEY", created.plaintext_key)
    monkeypatch.setenv("OPENAI_BASE_URL", f"http://127.0.0.1:{gateway_port}/v1")
    app = create_app(get_settings())
    completed = _completed_response()
    sse = _codex_standard_stream(completed)

    with _run_uvicorn_server(app, gateway_port):
        with respx.mock(assert_all_mocked=True, assert_all_called=False) as router:
            local_route = router.post(f"http://127.0.0.1:{local_port}/v1/responses").mock(
                side_effect=lambda request: httpx.Response(
                    200,
                    content=sse.encode()
                    if json.loads(request.content).get("stream")
                    else json.dumps(completed).encode(),
                    headers={
                        "content-type": "text/event-stream"
                        if json.loads(request.content).get("stream")
                        else "application/json"
                    },
                )
            )
            router.route(host="127.0.0.1").pass_through()
            client = OpenAI()
            non_streaming = client.responses.create(
                model=local_model,
                input=[
                    _synthetic_197_additional_tools_item(),
                    {
                        "type": "message",
                        "role": "user",
                        "content": [{"type": "input_text", "text": "bounded 0162 request"}],
                    },
                ],
                prompt_cache_key=SESSION,
                extra_body={"client_metadata": _metadata()},
            )
            streaming = client.responses.create(
                model=local_model,
                input=[
                    _synthetic_197_additional_tools_item(),
                    {
                        "type": "message",
                        "role": "user",
                        "content": [{"type": "input_text", "text": "bounded 0162 stream"}],
                    },
                ],
                stream=True,
                prompt_cache_key=SESSION,
                extra_body={"client_metadata": _metadata()},
            )
            events = list(streaming)

    assert non_streaming.id == "codex-0162-e2e-response"
    assert [event.type for event in events] == [
        "response.created",
        "response.output_item.added",
        "response.content_part.added",
        "response.output_text.delta",
        "response.output_text.done",
        "response.content_part.done",
        "response.output_item.done",
        "response.completed",
    ]
    assert len(local_route.calls) == 2
    for request in (call.request for call in local_route.calls):
        body = json.loads(request.content)
        _assert_forwarded_197_lowered(
            body,
            message_text=str(body["input"][0]["content"][0]["text"]),
            max_output_tokens=CODEX_ROUTE_LIMITS["default_max_output_tokens"],
        )
        _verify_local_coding_signature(request)
    assert "stream" not in json.loads(local_route.calls[0].request.content)
    assert json.loads(local_route.calls[1].request.content)["stream"] is True

    state = asyncio.run(
        _load_accounting_state(database_url, created.gateway_key_id, provider="local-coding")
    )
    assert state.gateway_key.requests_used_total == 2
    assert state.gateway_key.tokens_used_total == 10
    # Each request finalizes its own ledger row of 5 tokens; the key
    # aggregate is 10.
    assert state.usage_ledger.total_tokens == 5
    assert state.usage_ledger.accounting_status == "finalized"
    assert asyncio.run(_load_ledger_rows(database_url, created.gateway_key_id)) == [
        (5, "finalized"),
        (5, "finalized"),
    ]
    assert asyncio.run(
        _load_accounting_side_effect_counts(database_url, created.gateway_key_id)
    ) == (2, 2)


@pytest.mark.e2e
def test_codex_0162_four_key_grants_require_the_fourth_route_grant(
    monkeypatch: pytest.MonkeyPatch,
    owned_pg_url: str,  # noqa: F811
) -> None:
    """Existing route gate: all-four key grants derive extended limits.

    The key carries all four Codex grants while the route carries only the
    first three Codex flags and no codex_limits object; the request must
    fail closed before admission, with no backend call or accounting.
    """
    database_url = owned_pg_url
    run_alembic_upgrade_head(database_url)
    _configure_runtime_environment(monkeypatch, database_url)
    _local_coding_environment(monkeypatch)
    local_model = "codex-0162-missing-route-grant-test"
    local_port = _free_port()
    route_kwargs = _local_coding_test_data_kwargs(
        {
            "id": CODEX_0162_CLIENT_MODULE_ID,
            "version": CODEX_0162_CLIENT_MODULE_VERSION,
            "fixture_sha256": CODEX_0162_FIXTURE_SHA256,
        },
        four_grants=False,
    )
    # Four key grants on purpose: this is what derives extended limits and
    # therefore the fourth route capability plus codex_limits requirement.
    key_policy = dict(route_kwargs["responses_policy"])
    key_policy["allowed_capabilities"] = list(ALL_FOUR_CODEX_GRANTS)
    route_kwargs["responses_policy"] = key_policy
    created = asyncio.run(
        _create_responses_test_data(
            database_url,
            model=local_model,
            base_url=f"http://127.0.0.1:{local_port}/v1",
            **route_kwargs,
        )
    )

    from openai import BadRequestError
    from slaif_gateway.config import get_settings
    from slaif_gateway.main import create_app

    get_settings.cache_clear()
    gateway_port = _free_port()
    monkeypatch.setenv("OPENAI_API_KEY", created.plaintext_key)
    monkeypatch.setenv("OPENAI_BASE_URL", f"http://127.0.0.1:{gateway_port}/v1")
    app = create_app(get_settings())

    with _run_uvicorn_server(app, gateway_port):
        with respx.mock(assert_all_mocked=True, assert_all_called=False) as router:
            local_route = router.post(f"http://127.0.0.1:{local_port}/v1/responses").mock(
                return_value=httpx.Response(200, json=_completed_response())
            )
            router.route(host="127.0.0.1").pass_through()
            client = OpenAI()
            with pytest.raises(BadRequestError) as exc_info:
                client.responses.create(
                    model=local_model,
                    input=[
                        _synthetic_197_additional_tools_item(),
                        {
                            "type": "message",
                            "role": "user",
                            "content": [{"type": "input_text", "text": "missing grant"}],
                        },
                    ],
                    extra_body={"client_metadata": _metadata()},
                )
            assert exc_info.value.status_code == 400
            assert exc_info.value.code == "responses_route_capability_not_supported"
            assert AT_UUID not in str(exc_info.value)
            assert local_route.call_count == 0

    assert asyncio.run(
        _load_gateway_key_counters(database_url, created.gateway_key_id)
    ) == (0, 0)
    assert asyncio.run(
        _load_accounting_side_effect_counts(database_url, created.gateway_key_id)
    ) == (0, 0)


@pytest.mark.e2e
def test_codex_0149_v5_key_rejects_the_197_profile_without_accounting(
    monkeypatch: pytest.MonkeyPatch,
    owned_pg_url: str,  # noqa: F811
) -> None:
    database_url = owned_pg_url
    run_alembic_upgrade_head(database_url)
    _configure_runtime_environment(monkeypatch, database_url)
    _local_coding_environment(monkeypatch)
    local_model = "codex-0149v5-197-reject-test"
    local_port = _free_port()
    created = asyncio.run(
        _create_responses_test_data(
            database_url,
            model=local_model,
            base_url=f"http://127.0.0.1:{local_port}/v1",
            **_local_coding_test_data_kwargs(
                {
                    "id": "codex-0.149-responses-v1",
                    "version": CODEX_0149_CLIENT_MODULE_VERSION,
                    "fixture_sha256": CODEX_0149_FIXTURE_SHA256,
                },
                four_grants=False,
            ),
        )
    )

    from openai import BadRequestError
    from slaif_gateway.config import get_settings
    from slaif_gateway.main import create_app

    get_settings.cache_clear()
    gateway_port = _free_port()
    app = create_app(get_settings())

    with _run_uvicorn_server(app, gateway_port):
        with respx.mock(assert_all_mocked=True, assert_all_called=False) as router:
            local_route = router.post(f"http://127.0.0.1:{local_port}/v1/responses").mock(
                return_value=httpx.Response(200, json=_completed_response())
            )
            router.route(host="127.0.0.1").pass_through()
            client = OpenAI(
                api_key=created.plaintext_key,
                base_url=f"http://127.0.0.1:{gateway_port}/v1",
            )
            with pytest.raises(BadRequestError) as exc_info:
                client.responses.create(
                    model=local_model,
                    input=[
                        _synthetic_197_additional_tools_item(),
                        {
                            "type": "message",
                            "role": "user",
                            "content": [{"type": "input_text", "text": "rejected profile"}],
                        },
                    ],
                    prompt_cache_key=SESSION,
                    extra_body={"client_metadata": _metadata()},
                )
            assert exc_info.value.status_code == 400
            assert exc_info.value.code == "responses_codex_client_tools_invalid"
            assert exc_info.value.param == "input[0].tools"
            # The safe error never echoes declaration material.
            assert AT_UUID not in str(exc_info.value)
            assert local_route.call_count == 0

    # A rejected request creates no reservation, ledger row, or key usage.
    assert asyncio.run(
        _load_gateway_key_counters(database_url, created.gateway_key_id)
    ) == (0, 0)
    assert asyncio.run(
        _load_accounting_side_effect_counts(database_url, created.gateway_key_id)
    ) == (0, 0)
