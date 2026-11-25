"""PostgreSQL settlement and replay-proof coverage for OpenCode 1.19.3.

The first group is rejected by the pinned client module (or module
resolution) before any database write or provider call. The second group
settles a real streaming tool loop (encrypted reasoning plus flat
function call) through ``handle_response_create`` against real PostgreSQL
quota, ledger, reservation, and replay-reference state, with the provider
mocked only at the gateway adapter boundary (no upstream HTTP wire).
A final group settles the same loop with the REAL provider factory and
adapter in place, intercepting only the upstream HTTP transport at
loopback.
The remaining cases pin the negative paths with no side effects.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
import json
from types import SimpleNamespace
import uuid

import httpx
import pytest
import respx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from slaif_gateway.api.errors import OpenAICompatibleError
from slaif_gateway.config import Settings
from slaif_gateway.db.models import CodexReplayReference, QuotaReservation, UsageLedger
from slaif_gateway.db.repositories.cohorts import CohortsRepository
from slaif_gateway.db.repositories.keys import GatewayKeysRepository
from slaif_gateway.db.repositories.owners import OwnersRepository
from slaif_gateway.db.repositories.pricing import PricingRulesRepository
from slaif_gateway.db.repositories.routing import ModelRoutesRepository
from slaif_gateway.modules.clients.opencode_1193_responses import (
    OPENCODE_1193_RESPONSES_CLIENT_MODULE_ID,
    OPENCODE_1193_RESPONSES_CLIENT_MODULE_VERSION,
    OPENCODE_1193_RESPONSES_PROFILE_FIXTURE_SHA256,
)
from slaif_gateway.schemas.providers import ProviderStreamChunk, ProviderUsage
from slaif_gateway.services import responses_gateway as gateway
from slaif_gateway.services.responses_gateway import handle_response_create
from slaif_gateway.utils.crypto import hmac_sha256_token
from tests.integration.test_codex_tool_history_postgres import (
    _auth_key,
    _gate_route_resolver,
)

_PIN = {
    "id": OPENCODE_1193_RESPONSES_CLIENT_MODULE_ID,
    "version": OPENCODE_1193_RESPONSES_CLIENT_MODULE_VERSION,
    "fixture_sha256": OPENCODE_1193_RESPONSES_PROFILE_FIXTURE_SHA256,
}

_TOOL_NAMES = (
    "bash",
    "edit",
    "glob",
    "grep",
    "read",
    "skill",
    "task",
    "todowrite",
    "write",
)


def _tool(name: str) -> dict:
    return {
        "type": "function",
        "name": name,
        "description": f"Tool {name}",
        "parameters": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
        "strict": True,
    }


def _full_body(stream: bool) -> dict:
    """The exact captured first-turn wire shape, with stream overridable."""
    return {
        "model": "synthetic-opencode-model",
        "stream": stream,
        "store": False,
        "tool_choice": "auto",
        "include": ["reasoning.encrypted_content"],
        "reasoning": {"effort": "xhigh"},
        "max_output_tokens": 32000,
        "input": [
            {"role": "developer", "content": "You are a bounded local tool harness."},
            {
                "role": "user",
                "content": [{"type": "input_text", "text": "Read the marker file exactly."}],
            },
        ],
        "tools": [_tool(name) for name in _TOOL_NAMES],
    }


def _payload(body: dict) -> SimpleNamespace:
    return SimpleNamespace(
        model_dump=lambda **_: body,
        model_fields_set=set(),
    )


def _key(client_module: object) -> SimpleNamespace:
    return SimpleNamespace(responses_policy={"client_module": client_module})


async def _counts(session: AsyncSession) -> tuple[int, int]:
    reservations = await session.scalar(select(func.count()).select_from(QuotaReservation))
    ledger = await session.scalar(select(func.count()).select_from(UsageLedger))
    return reservations, ledger


@pytest.mark.asyncio
async def test_opencode_unknown_client_module_rejection_has_no_postgres_side_effect(
    async_test_session: AsyncSession,
) -> None:
    before = await _counts(async_test_session)
    pin = dict(_PIN, id="opencode-9.9.9-responses-v1")
    with pytest.raises(OpenAICompatibleError) as exc_info:
        await handle_response_create(
            payload=_payload(_full_body(stream=True)),
            authenticated_key=_key(pin),
            settings=SimpleNamespace(),
        )
    assert exc_info.value.code == "unsupported_client_module"
    assert await _counts(async_test_session) == before


@pytest.mark.asyncio
@pytest.mark.parametrize("stale_version", ["0", "2"])
async def test_opencode_stale_version_rejection_has_no_postgres_side_effect(
    async_test_session: AsyncSession,
    stale_version: str,
) -> None:
    before = await _counts(async_test_session)
    pin = dict(_PIN, version=stale_version)
    with pytest.raises(OpenAICompatibleError) as exc_info:
        await handle_response_create(
            payload=_payload(_full_body(stream=True)),
            authenticated_key=_key(pin),
            settings=SimpleNamespace(),
        )
    assert exc_info.value.code == "client_module_fixture_mismatch"
    assert await _counts(async_test_session) == before


@pytest.mark.asyncio
async def test_opencode_wrong_digest_rejection_has_no_postgres_side_effect(
    async_test_session: AsyncSession,
) -> None:
    before = await _counts(async_test_session)
    pin = dict(_PIN, fixture_sha256="0" * 64)
    with pytest.raises(OpenAICompatibleError) as exc_info:
        await handle_response_create(
            payload=_payload(_full_body(stream=True)),
            authenticated_key=_key(pin),
            settings=SimpleNamespace(),
        )
    assert exc_info.value.code == "client_module_fixture_mismatch"
    assert await _counts(async_test_session) == before


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("client_module", "expected_code"),
    [
        ({}, "client_module_metadata_invalid"),
        (
            {"id": OPENCODE_1193_RESPONSES_CLIENT_MODULE_ID},
            "client_module_metadata_invalid",
        ),
        ({**_PIN, "extra": "metadata"}, "client_module_metadata_invalid"),
        (
            {
                "id": OPENCODE_1193_RESPONSES_CLIENT_MODULE_ID,
                "version": 1,
                "fixture_sha256": OPENCODE_1193_RESPONSES_PROFILE_FIXTURE_SHA256,
            },
            "client_module_metadata_invalid",
        ),
        (
            OPENCODE_1193_RESPONSES_CLIENT_MODULE_ID,
            "client_module_metadata_invalid",
        ),
        # A present-but-None digest survives the key-set and string checks
        # and is rejected as a digest mismatch instead.
        (
            {
                "id": OPENCODE_1193_RESPONSES_CLIENT_MODULE_ID,
                "version": OPENCODE_1193_RESPONSES_CLIENT_MODULE_VERSION,
                "fixture_sha256": None,
            },
            "client_module_fixture_mismatch",
        ),
    ],
    ids=[
        "empty",
        "missing-keys",
        "extra-key",
        "integer-version",
        "non-mapping",
        "null-digest",
    ],
)
async def test_opencode_metadata_shape_rejection_has_no_postgres_side_effect(
    async_test_session: AsyncSession,
    client_module: object,
    expected_code: str,
) -> None:
    before = await _counts(async_test_session)
    with pytest.raises(OpenAICompatibleError) as exc_info:
        await handle_response_create(
            payload=_payload(_full_body(stream=True)),
            authenticated_key=_key(client_module),
            settings=SimpleNamespace(),
        )
    assert exc_info.value.code == expected_code
    assert await _counts(async_test_session) == before


@pytest.mark.asyncio
async def test_opencode_stream_false_rejection_has_no_postgres_side_effect(
    async_test_session: AsyncSession,
) -> None:
    """The OpenCode profile is streaming-only: ``stream`` false is denied.

    This pins the captured wire fact at the gateway boundary: with a fully
    valid pin and otherwise exact first-turn shape, only the stream field
    differs, and the request fails closed before any PostgreSQL write or
    provider call.
    """
    before = await _counts(async_test_session)
    with pytest.raises(OpenAICompatibleError) as exc_info:
        await handle_response_create(
            payload=_payload(_full_body(stream=False)),
            authenticated_key=_key(dict(_PIN)),
            settings=SimpleNamespace(),
        )
    assert exc_info.value.code == "opencode_1193_field_shape"
    assert await _counts(async_test_session) == before


# --- Streaming tool-loop settlement and replay-proof coverage ------------

CIPHER = "c" * 64
_HMAC_SECRET = "oap228-opencode-qualification-replay-hmac-secret"
_OPENCODE_CAPS = (
    "codex_request_envelope",
    "codex_client_tools",
    "codex_streaming_tool_events",
    "codex_encrypted_reasoning_replay",
)
_PUBLIC_MODEL = "synthetic-opencode-model"
_PROVIDER = "synthetic-opencode"
_UPSTREAM = "synthetic-upstream"


def _digest(token: str) -> str:
    return hmac_sha256_token(token=token, secret=_HMAC_SECRET)


D_V1_RS = _digest("slaif-codex-replay:v1:item:reasoning:rs_228a_1")
D_V3_CIPHER = _digest(f"slaif-codex-replay:v3:reasoning:{len(CIPHER)}:{CIPHER}")
D_V1_FC = _digest("slaif-codex-replay:v1:item:function_call:fc_228a_1")
D_V1_CALL = _digest("slaif-codex-replay:v1:call:function_call:call_228a_op")


def _settings() -> Settings:
    return Settings(
        APP_ENV="development",
        TOKEN_HMAC_SECRET=_HMAC_SECRET,
        ACTIVE_HMAC_KEY_VERSION="1",
        CODEX_REPLAY_REFERENCE_TTL_SECONDS=86400,
        ENABLE_REDIS_RATE_LIMITS=False,
    )


def _route_caps(caps: tuple[str, ...]) -> dict:
    block = {
        "text": True,
        "stateless": True,
        "streaming": True,
        "tools": True,
        "function_tools": True,
    }
    block.update({c: True for c in caps})
    return {
        "responses": block,
        # Fully gated Codex routes carry strict numeric limits alongside the
        # capability block; parse_codex_route_limits demands exactly these
        # fields with default <= max < context.
        "codex_limits": {
            "context_window_tokens": 1_050_000,
            "default_max_output_tokens": 32_768,
            "max_output_tokens": 128_000,
        },
    }


def _probe(
    route_id: uuid.UUID,
    capabilities: dict,
    *,
    provider: str = _PROVIDER,
    provider_kind: str = "openai_compatible",
    base_url: str = "http://127.0.0.1:18031/v1",
    api_key_env_var: str = "UPSTREAM_SERVICE_TOKEN",
    public_model: str = _PUBLIC_MODEL,
    upstream_model: str = _UPSTREAM,
) -> SimpleNamespace:
    return SimpleNamespace(
        provider=provider,
        provider_kind=provider_kind,
        provider_base_url=base_url,
        provider_api_key_env_var=api_key_env_var,
        provider_timeout_seconds=10,
        provider_max_retries=0,
        route_id=route_id,
        resolved_model=upstream_model,
        requested_model=public_model,
        route_match_type="exact",
        route_pattern=public_model,
        priority=1,
        supports_streaming=True,
        capabilities=capabilities,
    )


async def _seed_opencode_world(
    session: AsyncSession,
    *,
    caps: tuple[str, ...],
    route: object = None,
    provider: str = _PROVIDER,
    public_model: str = _PUBLIC_MODEL,
    upstream_model: str = _UPSTREAM,
):
    now = datetime.now(UTC)
    unique = uuid.uuid4().hex
    owner = await OwnersRepository(session).create_owner(
        name="OpenCode",
        surname="Qualification",
        email=f"oc228-{unique}@example.org",
    )
    cohort = await CohortsRepository(session).create_cohort(name=f"oc228-{unique}")
    key = await GatewayKeysRepository(session).create_gateway_key_record(
        public_key_id=f"oc228_{unique}",
        token_hash=uuid.uuid4().hex,
        owner_id=owner.id,
        cohort_id=cohort.id,
        valid_from=now - timedelta(minutes=1),
        valid_until=now + timedelta(days=30),
        cost_limit_eur=Decimal("50.00"),
        token_limit_total=1_000_000,
        request_limit_total=10_000,
        rate_limit_requests_per_minute=60,
        rate_limit_tokens_per_minute=120_000,
        max_concurrent_requests=4,
        allow_all_models=False,
        allowed_models=[public_model],
        allow_all_endpoints=False,
        allowed_endpoints=["/v1/responses"],
        metadata_json={
            "responses_policy": {
                "version": 1,
                "allowed_capabilities": list(caps),
                "client_module": dict(_PIN),
            },
            "allowed_providers": [provider],
        },
    )
    # Pre-existing settled usage. This world seeds NO ledger rows, so tests
    # assert exact per-key deltas instead of matching seeded rows.
    key.cost_used_eur = Decimal("7.250000000")
    key.tokens_used_total = 12_345
    key.requests_used_total = 9
    if route is None:
        route = await ModelRoutesRepository(session).create_model_route(
            requested_model=public_model,
            provider=provider,
            upstream_model=upstream_model,
            endpoint="/v1/responses",
        )
        await PricingRulesRepository(session).create_pricing_rule(
            provider=provider,
            upstream_model=upstream_model,
            valid_from=now - timedelta(minutes=1),
            endpoint="/v1/responses",
            currency="EUR",
            input_price_per_1m=Decimal("2.00"),
            cached_input_price_per_1m=Decimal("2.00"),
            output_price_per_1m=Decimal("8.00"),
            reasoning_price_per_1m=Decimal("8.00"),
            pricing_metadata={
                "codex_accounting": {
                    "long_context_threshold_tokens": 1_050_000,
                    "long_context_input_multiplier": "1.0",
                    "long_context_output_multiplier": "1.0",
                    "cache_write_input_price_per_1m": "2.00",
                }
            },
        )
    await session.flush()
    return owner, cohort, key, route


def _turn1_events() -> list[dict]:
    return [
        {"type": "response.created", "response": {"id": "resp_228a_1"}},
        {
            "type": "response.output_item.added",
            "output_index": 0,
            "item": {"type": "reasoning", "id": "rs_228a_1", "encrypted_content": CIPHER},
        },
        {
            "type": "response.reasoning_summary_part.added",
            "item_id": "rs_228a_1",
            "output_index": 0,
            "summary_index": 0,
            "part": {"type": "summary_text", "text": ""},
        },
        {
            "type": "response.reasoning_summary_text.delta",
            "item_id": "rs_228a_1",
            "output_index": 0,
            "summary_index": 0,
            "delta": "part",
        },
        {
            "type": "response.reasoning_summary_part.done",
            "item_id": "rs_228a_1",
            "output_index": 0,
            "summary_index": 0,
            "part": {"type": "summary_text", "text": "part"},
        },
        {
            "type": "response.output_item.done",
            "output_index": 0,
            "item": {
                "type": "reasoning",
                "id": "rs_228a_1",
                "summary": [{"type": "summary_text", "text": "part"}],
                "encrypted_content": CIPHER,
            },
        },
        {
            "type": "response.output_item.added",
            "output_index": 1,
            "item": {
                "type": "function_call",
                "id": "fc_228a_1",
                "status": "in_progress",
                "name": "read",
                "call_id": "call_228a_op",
                "arguments": "",
            },
        },
        {
            "type": "response.function_call_arguments.delta",
            "item_id": "fc_228a_1",
            "output_index": 1,
            "delta": "{}",
        },
        {
            "type": "response.output_item.done",
            "output_index": 1,
            "item": {
                "type": "function_call",
                "id": "fc_228a_1",
                "status": "completed",
                "name": "read",
                "call_id": "call_228a_op",
                "arguments": "{}",
            },
        },
        {
            "type": "response.completed",
            "response": {
                "id": "resp_228a_1",
                "status": "completed",
                "usage": {"input_tokens": 5, "output_tokens": 2, "total_tokens": 7},
            },
        },
    ]


def _turn2_events() -> list[dict]:
    return [
        {"type": "response.created", "response": {"id": "resp_228a_2"}},
        {"type": "response.output_text.delta", "delta": "Done."},
        {
            "type": "response.completed",
            "response": {
                "id": "resp_228a_2",
                "status": "completed",
                "usage": {"input_tokens": 5, "output_tokens": 2, "total_tokens": 7},
            },
        },
    ]


def _turn2_input() -> list[dict]:
    return [
        {"role": "developer", "content": "You are a bounded local tool harness."},
        {
            "role": "user",
            "content": [{"type": "input_text", "text": "Read the marker file exactly."}],
        },
        # ID-less encrypted reasoning replay (the pinned OpenCode wire shape).
        {
            "type": "reasoning",
            "summary": [{"type": "summary_text", "text": "part"}],
            "encrypted_content": CIPHER,
        },
        # Flat function call/output (no namespace keys).
        {"type": "function_call", "call_id": "call_228a_op", "name": "read", "arguments": "{}"},
        {"type": "function_call_output", "call_id": "call_228a_op", "output": "MARKER"},
    ]


class _Adapter:
    def __init__(self, turns: list[list[dict]]) -> None:
        self._turns = list(turns)
        self.calls = 0

    async def stream_response(self, request):
        self.calls += 1
        for event in self._turns.pop(0):
            yield ProviderStreamChunk(
                provider=request.provider,
                upstream_model=request.upstream_model,
                data=json.dumps(event),
                json_body=event,
                raw_sse_event="data: " + json.dumps(event) + "\n\n",
                usage=(
                    ProviderUsage(prompt_tokens=5, completion_tokens=2, total_tokens=7)
                    if event["type"] == "response.completed"
                    else None
                ),
            )


def _patch_streaming(
    monkeypatch: pytest.MonkeyPatch,
    session: AsyncSession,
    route: object,
    adapter: _Adapter,
    caps: tuple[str, ...] = _OPENCODE_CAPS,
) -> None:
    async def db(request=None):
        yield session

    monkeypatch.setattr(gateway, "_get_db_session_after_auth_header_check", db)
    monkeypatch.setattr(
        gateway,
        "_resolve_responses_route",
        _gate_route_resolver(_probe(route.id, _route_caps(caps))),
    )
    monkeypatch.setattr(gateway, "get_provider_adapter", lambda *args: adapter)


async def _settle_turn1(
    session: AsyncSession,
    auth: object,
    settings: Settings,
    key: object,
    *,
    model: str = _PUBLIC_MODEL,
) -> None:
    """Issue turn 1 and pin its successful settlement (completed, not failed)."""
    body = _full_body(stream=True)
    body["model"] = model
    response = await handle_response_create(
        payload=_payload(body),
        authenticated_key=auth,
        settings=settings,
    )
    joined = "".join([s async for s in response.body_iterator])
    assert "response.completed" in joined
    assert "response.failed" not in joined
    await session.refresh(key)


async def _ref_rows(session: AsyncSession, key_id: object) -> list:
    stmt = select(CodexReplayReference).where(CodexReplayReference.gateway_key_id == key_id)
    return list((await session.execute(stmt)).scalars())


async def _ledger_rows(session: AsyncSession, key_id: object) -> list:
    stmt = (
        select(UsageLedger)
        .where(UsageLedger.gateway_key_id == key_id)
        .order_by(UsageLedger.started_at)
    )
    return list((await session.execute(stmt)).scalars())


async def _reservation_rows(session: AsyncSession, key_id: object) -> list:
    stmt = select(QuotaReservation).where(QuotaReservation.gateway_key_id == key_id)
    return list((await session.execute(stmt)).scalars())


@pytest.mark.asyncio
async def test_opencode_streaming_toolloop_settles_and_idless_replay_continues(
    async_test_session, monkeypatch
):
    session = async_test_session
    owner, cohort, key, route = await _seed_opencode_world(session, caps=_OPENCODE_CAPS)
    adapter = _Adapter([_turn1_events(), _turn2_events()])
    _patch_streaming(monkeypatch, session, route, adapter)
    auth = _auth_key(key)
    await _settle_turn1(session, auth, _settings(), key)

    assert key.requests_used_total == 10
    assert key.tokens_used_total == 12_352
    assert key.tokens_reserved_total == 0
    assert key.requests_reserved_total == 0

    refs = await _ref_rows(session, key.id)
    assert len(refs) == 3
    assert {r.item_id_hmac for r in refs} == {D_V1_RS, D_V3_CIPHER, D_V1_FC}
    assert {r.item_kind for r in refs} == {"reasoning", "function_call"}
    fc = next(r for r in refs if r.item_kind == "function_call")
    assert fc.call_id_hmac == D_V1_CALL
    assert fc.tool_namespace == "functions"
    assert fc.tool_name == "read"
    assert fc.route_id == route.id
    assert fc.provider == _PROVIDER
    assert fc.upstream_model == _UPSTREAM
    for reasoning in (r for r in refs if r.item_kind == "reasoning"):
        assert reasoning.call_id_hmac is None
        assert reasoning.tool_namespace is None
        assert reasoning.tool_name is None

    ledger = await _ledger_rows(session, key.id)
    assert len(ledger) == 1
    assert ledger[0].success is True
    assert ledger[0].accounting_status == "finalized"
    assert ledger[0].total_tokens == 7
    reservations = await _reservation_rows(session, key.id)
    assert len(reservations) == 1
    assert reservations[0].status == "finalized"

    body2 = _full_body(stream=True)
    body2["input"] = _turn2_input()
    response2 = await handle_response_create(
        payload=_payload(body2), authenticated_key=auth, settings=_settings()
    )
    joined2 = "".join([s async for s in response2.body_iterator])
    assert "response.completed" in joined2
    assert "response.failed" not in joined2
    await session.refresh(key)
    assert key.requests_used_total == 11
    assert key.tokens_used_total == 12_359
    assert key.tokens_reserved_total == 0
    assert key.requests_reserved_total == 0
    assert len(await _ref_rows(session, key.id)) == 3
    ledger2 = await _ledger_rows(session, key.id)
    assert len(ledger2) == 2
    assert all(row.success is True and row.accounting_status == "finalized" for row in ledger2)
    assert adapter.calls == 2


@pytest.mark.asyncio
async def test_opencode_streaming_toolloop_altered_cipher_replay_denied(
    async_test_session, monkeypatch
):
    session = async_test_session
    owner, cohort, key, route = await _seed_opencode_world(session, caps=_OPENCODE_CAPS)
    adapter = _Adapter([_turn1_events()])
    _patch_streaming(monkeypatch, session, route, adapter)
    auth = _auth_key(key)
    await _settle_turn1(session, auth, _settings(), key)

    before_requests = key.requests_used_total
    before_tokens = key.tokens_used_total
    replay_input = _turn2_input()
    replay_input[2]["encrypted_content"] = "d" * 64
    body = _full_body(stream=True)
    body["input"] = replay_input
    with pytest.raises(OpenAICompatibleError) as exc_info:
        await handle_response_create(
            payload=_payload(body), authenticated_key=auth, settings=_settings()
        )
    assert exc_info.value.code == "responses_codex_replay_reference_not_found"
    await session.refresh(key)
    assert key.requests_used_total == before_requests
    assert key.tokens_used_total == before_tokens
    assert len(await _ledger_rows(session, key.id)) == 1
    assert adapter.calls == 1


@pytest.mark.asyncio
async def test_opencode_streaming_toolloop_foreign_key_replay_denied(
    async_test_session, monkeypatch
):
    session = async_test_session
    owner_a, cohort_a, key_a, route = await _seed_opencode_world(session, caps=_OPENCODE_CAPS)
    # World B reuses the same route row (the resolver is fully patched;
    # only route.id matters) so the route/pricing unique constraints are
    # not re-hit.
    owner_b, cohort_b, key_b, _ = await _seed_opencode_world(
        session, caps=_OPENCODE_CAPS, route=route
    )
    adapter = _Adapter([_turn1_events()])
    _patch_streaming(monkeypatch, session, route, adapter)
    auth_a = _auth_key(key_a)
    await _settle_turn1(session, auth_a, _settings(), key_a)

    body = _full_body(stream=True)
    body["input"] = _turn2_input()
    with pytest.raises(OpenAICompatibleError) as exc_info:
        await handle_response_create(
            payload=_payload(body),
            authenticated_key=_auth_key(key_b),
            settings=_settings(),
        )
    assert exc_info.value.code == "responses_codex_replay_reference_not_found"

    assert len(await _ref_rows(session, key_a.id)) == 3
    await session.refresh(key_a)
    assert key_a.requests_used_total == 10
    await session.refresh(key_b)
    assert key_b.requests_used_total == 9
    assert key_b.tokens_used_total == 12_345
    assert len(await _ref_rows(session, key_b.id)) == 0
    assert adapter.calls == 1


@pytest.mark.asyncio
async def test_opencode_streaming_toolloop_unknown_model_denied_by_real_resolver(
    async_test_session, monkeypatch
):
    session = async_test_session
    owner, cohort, key, route = await _seed_opencode_world(session, caps=_OPENCODE_CAPS)

    async def db(request=None):
        yield session

    monkeypatch.setattr(gateway, "_get_db_session_after_auth_header_check", db)
    adapter = _Adapter([])
    monkeypatch.setattr(gateway, "get_provider_adapter", lambda *args: adapter)

    body = _full_body(stream=True)
    body["model"] = "other-model"
    with pytest.raises(OpenAICompatibleError) as exc_info:
        await handle_response_create(
            payload=_payload(body),
            authenticated_key=_auth_key(key),
            settings=_settings(),
        )
    assert exc_info.value.code == "model_not_allowed_for_key"
    await session.refresh(key)
    assert key.requests_used_total == 9
    assert key.tokens_used_total == 12_345
    assert len(await _ledger_rows(session, key.id)) == 0
    assert adapter.calls == 0


@pytest.mark.asyncio
async def test_opencode_streaming_toolloop_id_bearing_reasoning_replay_denied(
    async_test_session, monkeypatch
):
    session = async_test_session
    owner, cohort, key, route = await _seed_opencode_world(session, caps=_OPENCODE_CAPS)
    adapter = _Adapter([_turn1_events()])
    _patch_streaming(monkeypatch, session, route, adapter)
    auth = _auth_key(key)
    await _settle_turn1(session, auth, _settings(), key)

    # A present item id in the native OpenCode captured shape is rejected
    # by the selected module before any database write.
    replay_input = _turn2_input()
    replay_input[2] = {
        "type": "reasoning",
        "id": "rs_never_1",
        "summary": [{"type": "summary_text", "text": "part"}],
        "encrypted_content": CIPHER,
    }
    body = _full_body(stream=True)
    body["input"] = replay_input
    with pytest.raises(OpenAICompatibleError) as exc_info:
        await handle_response_create(
            payload=_payload(body), authenticated_key=auth, settings=_settings()
        )
    assert exc_info.value.code == "opencode_1193_input_item"
    await session.refresh(key)
    assert key.requests_used_total == 10
    assert key.tokens_used_total == 12_352
    assert len(await _ledger_rows(session, key.id)) == 1


@pytest.mark.asyncio
async def test_opencode_streaming_toolloop_failed_stream_settles_estimated_without_refs(
    async_test_session, monkeypatch
):
    session = async_test_session
    owner, cohort, key, route = await _seed_opencode_world(session, caps=_OPENCODE_CAPS)
    events = _turn1_events()
    # The done item must equal the accumulated arguments; mismatching it
    # forces the strict stream validator to fail the turn.
    events[8]["item"]["arguments"] = "WRONG"
    adapter = _Adapter([events])
    _patch_streaming(monkeypatch, session, route, adapter)
    auth = _auth_key(key)

    response = await handle_response_create(
        payload=_payload(_full_body(stream=True)),
        authenticated_key=auth,
        settings=_settings(),
    )
    joined = "".join([s async for s in response.body_iterator])
    assert "response.failed" in joined
    assert "response.completed" not in joined
    await session.refresh(key)
    # A failed streaming turn is admitted as one request. The reservation
    # is finalized at the estimate (513 input + 32_000 requested max
    # output = 32_513) and settles as an estimated ledger row of the
    # observed finalization split (513 input + 5 output = 518 tokens,
    # EUR 0.001066). It persists NO replay reference because the output
    # was never validated as completed.
    assert key.requests_used_total == 10
    assert key.tokens_used_total == 12_345 + 518
    assert key.tokens_reserved_total == 0
    assert key.requests_reserved_total == 0
    ledger = await _ledger_rows(session, key.id)
    assert len(ledger) == 1
    assert ledger[0].success is False
    assert ledger[0].accounting_status == "estimated"
    assert ledger[0].input_tokens == 513
    assert ledger[0].output_tokens == 5
    assert ledger[0].total_tokens == 518
    assert len(await _ref_rows(session, key.id)) == 0
    reservations = await _reservation_rows(session, key.id)
    assert len(reservations) == 1
    assert reservations[0].status == "finalized"
    assert reservations[0].reserved_tokens == 32_513
    assert reservations[0].finalized_at is not None


@pytest.mark.asyncio
async def test_opencode_streaming_toolloop_missing_replay_capability_denied(
    async_test_session, monkeypatch
):
    session = async_test_session
    # Key keeps the FULL grants so the key-level gate passes; only the ROUTE
    # metadata drops codex_encrypted_reasoning_replay (the gate under test -
    # a key-level denial would short-circuit before the route gate runs).
    owner, cohort, key, route = await _seed_opencode_world(session, caps=_OPENCODE_CAPS)
    adapter = _Adapter([])
    _patch_streaming(monkeypatch, session, route, adapter, caps=_OPENCODE_CAPS[:-1])

    with pytest.raises(OpenAICompatibleError) as exc_info:
        await handle_response_create(
            payload=_payload(_full_body(stream=True)),
            authenticated_key=_auth_key(key),
            settings=_settings(),
        )
    assert exc_info.value.code == "responses_route_capability_not_supported"
    await session.refresh(key)
    assert key.requests_used_total == 9
    assert key.tokens_used_total == 12_345
    assert len(await _ledger_rows(session, key.id)) == 0
    assert adapter.calls == 0


# --- HTTP-mock factory-adapter settlement (228-b focused item) --------------
#
# These cases leave ``gateway.get_provider_adapter`` UNPATCHED: the real
# provider factory resolves the route probe to the registered OpenAI or
# OpenAI-compatible server module, performs the static client/server pair
# check, reads the operator credential from the route-named environment
# variable, and the real adapter issues a real ``httpx`` call that ``respx``
# intercepts at loopback. Request body shape, public-to-upstream model
# substitution, Bearer substitution, and PostgreSQL settlement are therefore
# real gateway behavior; only the upstream HTTP transport is mocked. No
# live provider, LAN, or real credential is involved.


def _sse_body(events: list[dict]) -> bytes:
    return b"".join(b"data: " + json.dumps(event).encode() + b"\n\n" for event in events)


_MOCK_ADAPTER_CASES = [
    {
        "provider": "openai",
        "provider_kind": "openai",
        "base_url": "http://127.0.0.1:18099/v1",
        "api_key_env_var": "MOCK228B_OPENAI_UPSTREAM_KEY",
        "api_key_value": "mock228b-openai-upstream-secret",
        "public_model": "oc228b-openai-model",
        "upstream_model": "oc228b-openai-upstream",
    },
    {
        "provider": "mock228b-compat",
        "provider_kind": "openai_compatible",
        "base_url": "http://127.0.0.1:18100/v1",
        "api_key_env_var": "MOCK228B_COMPAT_UPSTREAM_KEY",
        "api_key_value": "mock228b-compat-upstream-secret",
        "public_model": "oc228b-compat-model",
        "upstream_model": "oc228b-compat-upstream",
    },
]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case", _MOCK_ADAPTER_CASES, ids=["openai-native", "openai-compatible"]
)
@pytest.mark.parametrize(
    "argument_closure", [False, True], ids=["baseline", "argument-closure"]
)
async def test_mock_http_factory_adapter_settles_both_turns(
    async_test_session, monkeypatch, case, argument_closure
):
    session = async_test_session
    owner, cohort, key, route = await _seed_opencode_world(
        session,
        caps=_OPENCODE_CAPS,
        provider=case["provider"],
        public_model=case["public_model"],
        upstream_model=case["upstream_model"],
    )
    monkeypatch.setenv(case["api_key_env_var"], case["api_key_value"])
    monkeypatch.delenv("OPENAI_UPSTREAM_API_KEY", raising=False)

    async def db(request=None):
        yield session

    monkeypatch.setattr(gateway, "_get_db_session_after_auth_header_check", db)
    monkeypatch.setattr(
        gateway,
        "_resolve_responses_route",
        _gate_route_resolver(
            _probe(
                route.id,
                _route_caps(_OPENCODE_CAPS),
                provider=case["provider"],
                provider_kind=case["provider_kind"],
                base_url=case["base_url"],
                api_key_env_var=case["api_key_env_var"],
                public_model=case["public_model"],
                upstream_model=case["upstream_model"],
            )
        ),
    )

    auth = _auth_key(key)
    # baseline: the native wire as captured; argument-closure: same wire
    # with the closed function-argument frame before the function done.
    turn1 = (
        _argument_closed_turn1_events() if argument_closure else _turn1_events()
    )
    with respx.mock(assert_all_called=False) as router:
        upstream = router.route(method="POST", url=f"{case['base_url']}/responses")
        upstream.mock(
            side_effect=[
                httpx.Response(
                    200,
                    content=_sse_body(turn1),
                    headers={"content-type": "text/event-stream"},
                ),
                httpx.Response(
                    200,
                    content=_sse_body(_turn2_events()),
                    headers={"content-type": "text/event-stream"},
                ),
            ]
        )

        await _settle_turn1(session, auth, _settings(), key, model=case["public_model"])

        body2 = _full_body(stream=True)
        body2["model"] = case["public_model"]
        body2["input"] = _turn2_input()
        response2 = await handle_response_create(
            payload=_payload(body2), authenticated_key=auth, settings=_settings()
        )
        joined2 = "".join([s async for s in response2.body_iterator])
        assert "response.completed" in joined2
        assert "response.failed" not in joined2

        # Wire facts: exactly one upstream POST per admitted turn, exact
        # public-to-upstream model substitution, stream true, and the
        # operator credential in the Bearer header only (never in the body).
        assert upstream.calls.call_count == 2
        for call in upstream.calls:
            request_body = json.loads(call.request.content)
            assert request_body["model"] == case["upstream_model"]
            assert request_body["stream"] is True
            assert (
                call.request.headers["authorization"] == f"Bearer {case['api_key_value']}"
            )
            content = call.request.content
            assert _HMAC_SECRET.encode() not in content
            assert key.token_hash.encode() not in content
            assert case["api_key_value"].encode() not in content

    await session.refresh(key)
    # Settlement mirrors the adapter-mocked main case exactly: two finalized
    # turns of 5 in / 2 out at the seeded 2.00/8.00 per-1M pricing.
    assert key.requests_used_total == 11
    assert key.tokens_used_total == 12_359
    assert key.tokens_reserved_total == 0
    assert key.requests_reserved_total == 0
    assert key.cost_used_eur == Decimal("7.250052")
    refs = await _ref_rows(session, key.id)
    assert len(refs) == 3
    assert {r.item_id_hmac for r in refs} == {D_V1_RS, D_V3_CIPHER, D_V1_FC}
    assert {r.item_kind for r in refs} == {"reasoning", "function_call"}
    fc = next(r for r in refs if r.item_kind == "function_call")
    assert fc.call_id_hmac == D_V1_CALL
    assert fc.tool_namespace == "functions"
    assert fc.tool_name == "read"
    assert fc.route_id == route.id
    assert fc.provider == case["provider"]
    assert fc.upstream_model == case["upstream_model"]
    for reasoning in (r for r in refs if r.item_kind == "reasoning"):
        assert reasoning.call_id_hmac is None
        assert reasoning.tool_namespace is None
        assert reasoning.tool_name is None
    ledger = await _ledger_rows(session, key.id)
    assert len(ledger) == 2
    assert all(row.success is True and row.accounting_status == "finalized" for row in ledger)
    reservations = await _reservation_rows(session, key.id)
    assert len(reservations) == 2
    assert all(reservation.status == "finalized" for reservation in reservations)
    reservations = await _reservation_rows(session, key.id)
    assert len(reservations) == 2
    assert all(reservation.status == "finalized" for reservation in reservations)


# --- Real-factory missing output_index repair (228-c focused item) -----------
#
# Demonstrated LAN defect: the first rejected native producer event was
# ``response.output_item.added`` with ``output_index`` ABSENT.  These cases
# exercise the scoped normalization through the UNPATCHED real provider
# factory and adapter (only the openai-compatible server-module pair gets
# the repair gate), with real PostgreSQL settlement; the upstream HTTP
# transport stays loopback-mocked.  No live provider, LAN, or real
# credential is involved.


def _missing_index_turn1_events() -> list[dict]:
    """Turn 1 with ``output_index`` removed from every output_item event.

    Only the FIRST added absence was observed natively (the demonstrated
    LAN defect); extending the absence to the remaining added/done
    events while the delta/part events keep supplied indexes is a
    synthetic extension of that observed shape.  The terminal response
    gains the registered ID -> index output ordering that the repair
    guard validates (reasoning done at 0, function_call done at 1).
    """
    events = _turn1_events()
    for event in events:
        if event["type"] in {"response.output_item.added", "response.output_item.done"}:
            del event["output_index"]
    terminal = events[-1]
    assert terminal["type"] == "response.completed"
    terminal["response"]["output"] = [
        events[5]["item"],  # reasoning done item (registered index 0)
        events[8]["item"],  # function_call done item (registered index 1)
    ]
    return events


def _contradictory_terminal_turn1_events() -> list[dict]:
    """Missing-index turn 1 whose terminal output order is REVERSED."""
    events = _missing_index_turn1_events()
    events[-1]["response"]["output"] = list(reversed(events[-1]["response"]["output"]))
    return events


def _argument_closed_turn1_events(*, missing_indices: bool = False) -> list[dict]:
    """Turn 1 extended with the closed function-argument wire.

    The ``response.function_call_arguments.done`` closure is inserted
    immediately BEFORE the registered function_call
    ``response.output_item.done`` (registered index 1, after reasoning
    at 0), reusing that done item's item_id/name/arguments so the
    closure can only settle when it equals the accumulated deltas.
    ``sequence_number`` is renumbered monotonically across the stream.
    With ``missing_indices`` the ``output_index`` is removed ONLY from
    the output-item and function-argument delta/done events; the
    terminal response carries the actual reasoning + function done
    items in registered order.
    """
    events = _turn1_events()
    done_index = next(
        i
        for i, event in enumerate(events)
        if event["type"] == "response.output_item.done"
        and event["item"]["type"] == "function_call"
    )
    done_item = events[done_index]["item"]
    events.insert(
        done_index,
        {
            "type": "response.function_call_arguments.done",
            "item_id": done_item["id"],
            "output_index": 1,
            "name": done_item["name"],
            "arguments": done_item["arguments"],
        },
    )
    indexed_types = {
        "response.output_item.added",
        "response.output_item.done",
        "response.reasoning_summary_part.added",
        "response.reasoning_summary_part.done",
        "response.reasoning_summary_text.delta",
        "response.function_call_arguments.delta",
        "response.function_call_arguments.done",
    }
    for sequence, event in enumerate(events):
        if event["type"] in indexed_types:
            event["sequence_number"] = sequence
    if missing_indices:
        for event in events:
            if event["type"] in {
                "response.output_item.added",
                "response.output_item.done",
                "response.function_call_arguments.delta",
                "response.function_call_arguments.done",
            }:
                del event["output_index"]
    terminal = events[-1]
    assert terminal["type"] == "response.completed"
    terminal["response"]["output"] = [
        event["item"] for event in events if event["type"] == "response.output_item.done"
    ]
    return events


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "argument_closure", [False, True], ids=["item-only", "argument-closure"]
)
async def test_mock_http_factory_adapter_settles_missing_index_wire(
    async_test_session, monkeypatch, argument_closure
) -> None:
    session = async_test_session
    case = _MOCK_ADAPTER_CASES[1]  # openai-compatible pair: repair gate active
    owner, cohort, key, route = await _seed_opencode_world(
        session,
        caps=_OPENCODE_CAPS,
        provider=case["provider"],
        public_model=case["public_model"],
        upstream_model=case["upstream_model"],
    )
    monkeypatch.setenv(case["api_key_env_var"], case["api_key_value"])
    monkeypatch.delenv("OPENAI_UPSTREAM_API_KEY", raising=False)

    async def db(request=None):
        yield session

    monkeypatch.setattr(gateway, "_get_db_session_after_auth_header_check", db)
    monkeypatch.setattr(
        gateway,
        "_resolve_responses_route",
        _gate_route_resolver(
            _probe(
                route.id,
                _route_caps(_OPENCODE_CAPS),
                provider=case["provider"],
                provider_kind=case["provider_kind"],
                base_url=case["base_url"],
                api_key_env_var=case["api_key_env_var"],
                public_model=case["public_model"],
                upstream_model=case["upstream_model"],
            )
        ),
    )

    auth = _auth_key(key)
    turn1 = (
        _argument_closed_turn1_events(missing_indices=True)
        if argument_closure
        else _missing_index_turn1_events()
    )
    # Repaired wire truth: compact re-encoding with the derived index
    # appended last.  The unmodified producer frame (default separators,
    # no index) must never be forwarded.
    repaired_frame = 'data: ' + json.dumps(
        {**turn1[1], "output_index": 0}, separators=(",", ":")
    ) + "\n\n"
    raw_missing_frame = "data: " + json.dumps(turn1[1]) + "\n\n"

    with respx.mock(assert_all_called=False) as router:
        upstream = router.route(method="POST", url=f"{case['base_url']}/responses")
        upstream.mock(
            side_effect=[
                httpx.Response(
                    200,
                    content=_sse_body(turn1),
                    headers={"content-type": "text/event-stream"},
                ),
                httpx.Response(
                    200,
                    content=_sse_body(_turn2_events()),
                    headers={"content-type": "text/event-stream"},
                ),
            ]
        )

        body = _full_body(stream=True)
        body["model"] = case["public_model"]
        response1 = await handle_response_create(
            payload=_payload(body), authenticated_key=auth, settings=_settings()
        )
        joined1 = "".join([s async for s in response1.body_iterator])
        assert "response.completed" in joined1
        assert "response.failed" not in joined1
        assert repaired_frame in joined1
        assert raw_missing_frame not in joined1

        if argument_closure:
            # The scoped normalization must also derive the registered
            # index 1 for the closed function-argument wire: compact
            # repaired frames with the index appended last reach the
            # client, and the unmodified producer frames (default
            # separators, no index) are never forwarded.
            for arg_type in (
                "response.function_call_arguments.delta",
                "response.function_call_arguments.done",
            ):
                arg_event = next(e for e in turn1 if e["type"] == arg_type)
                repaired_arg_frame = (
                    "data: "
                    + json.dumps(
                        {**arg_event, "output_index": 1}, separators=(",", ":")
                    )
                    + "\n\n"
                )
                assert repaired_arg_frame in joined1
                assert "data: " + json.dumps(arg_event) + "\n\n" not in joined1

        body2 = _full_body(stream=True)
        body2["model"] = case["public_model"]
        body2["input"] = _turn2_input()
        response2 = await handle_response_create(
            payload=_payload(body2), authenticated_key=auth, settings=_settings()
        )
        joined2 = "".join([s async for s in response2.body_iterator])
        assert "response.completed" in joined2
        assert "response.failed" not in joined2

        # Wire facts: exactly one upstream POST per admitted turn, exact
        # public-to-upstream model substitution, stream true, and the
        # operator credential in the Bearer header only (never in the body).
        assert upstream.calls.call_count == 2
        for call in upstream.calls:
            request_body = json.loads(call.request.content)
            assert request_body["model"] == case["upstream_model"]
            assert request_body["stream"] is True
            assert (
                call.request.headers["authorization"] == f"Bearer {case['api_key_value']}"
            )
            content = call.request.content
            assert _HMAC_SECRET.encode() not in content
            assert key.token_hash.encode() not in content
            assert case["api_key_value"].encode() not in content

    await session.refresh(key)
    # Settlement mirrors the two-turn factory case exactly: the repaired
    # wire changes nothing about accounting (5 in / 2 out per turn at the
    # seeded 2.00/8.00 per-1M pricing).
    assert key.requests_used_total == 11
    assert key.tokens_used_total == 12_359
    assert key.tokens_reserved_total == 0
    assert key.requests_reserved_total == 0
    assert key.cost_used_eur == Decimal("7.250052")
    refs = await _ref_rows(session, key.id)
    assert len(refs) == 3
    assert {r.item_id_hmac for r in refs} == {D_V1_RS, D_V3_CIPHER, D_V1_FC}
    ledger = await _ledger_rows(session, key.id)
    assert len(ledger) == 2
    assert all(row.success is True and row.accounting_status == "finalized" for row in ledger)


@pytest.mark.asyncio
async def test_mock_http_factory_adapter_rejects_contradictory_terminal_no_refs(
    async_test_session, monkeypatch
) -> None:
    session = async_test_session
    case = _MOCK_ADAPTER_CASES[1]
    owner, cohort, key, route = await _seed_opencode_world(
        session,
        caps=_OPENCODE_CAPS,
        provider=case["provider"],
        public_model=case["public_model"],
        upstream_model=case["upstream_model"],
    )
    monkeypatch.setenv(case["api_key_env_var"], case["api_key_value"])
    monkeypatch.delenv("OPENAI_UPSTREAM_API_KEY", raising=False)

    async def db(request=None):
        yield session

    monkeypatch.setattr(gateway, "_get_db_session_after_auth_header_check", db)
    monkeypatch.setattr(
        gateway,
        "_resolve_responses_route",
        _gate_route_resolver(
            _probe(
                route.id,
                _route_caps(_OPENCODE_CAPS),
                provider=case["provider"],
                provider_kind=case["provider_kind"],
                base_url=case["base_url"],
                api_key_env_var=case["api_key_env_var"],
                public_model=case["public_model"],
                upstream_model=case["upstream_model"],
            )
        ),
    )

    auth = _auth_key(key)
    with respx.mock(assert_all_called=False) as router:
        upstream = router.route(method="POST", url=f"{case['base_url']}/responses")
        upstream.mock(
            side_effect=[
                httpx.Response(
                    200,
                    content=_sse_body(_contradictory_terminal_turn1_events()),
                    headers={"content-type": "text/event-stream"},
                ),
            ]
        )

        body = _full_body(stream=True)
        body["model"] = case["public_model"]
        response = await handle_response_create(
            payload=_payload(body), authenticated_key=auth, settings=_settings()
        )
        joined = "".join([s async for s in response.body_iterator])
        assert "response.failed" in joined
        assert "response.completed" not in joined
        assert "responses_stream_event_not_supported" in joined
        assert upstream.calls.call_count == 1

    await session.refresh(key)
    # Mirrors the accepted failed-stream precedent: the failed turn is
    # admitted as one request, the reservation is finalized at the
    # admission estimate (513 input + 32_000 requested max output), and
    # NO replay reference is persisted because the terminal was rejected.
    assert key.requests_used_total == 10
    assert key.tokens_reserved_total == 0
    assert key.requests_reserved_total == 0
    ledger = await _ledger_rows(session, key.id)
    assert len(ledger) == 1
    assert ledger[0].success is False
    assert ledger[0].accounting_status == "estimated"
    assert ledger[0].input_tokens == 513
    assert ledger[0].input_tokens + ledger[0].output_tokens == ledger[0].total_tokens
    assert key.tokens_used_total == 12_345 + ledger[0].total_tokens
    assert len(await _ref_rows(session, key.id)) == 0
    reservations = await _reservation_rows(session, key.id)
    assert len(reservations) == 1
    assert reservations[0].status == "finalized"
    assert reservations[0].reserved_tokens == 32_513
    assert reservations[0].finalized_at is not None
