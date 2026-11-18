"""Failed first-turn/retry/replay with real PostgreSQL quota and HMAC state."""

import copy
import json
import uuid

import pytest
from sqlalchemy import delete, func, select

from slaif_gateway.db.models import CodexReplayReference, QuotaReservation, UsageLedger
from slaif_gateway.db.repositories.codex_replay import CodexReplayReferencesRepository
from slaif_gateway.providers.errors import ProviderResponseParseError
from slaif_gateway.schemas.openai import ResponsesCreateRequest
from slaif_gateway.schemas.providers import ProviderStreamChunk, ProviderUsage
from slaif_gateway.services import responses_gateway as gateway
from slaif_gateway.services.codex_replay_service import CodexReplayReferenceError, CodexReplayService
from slaif_gateway.services.responses_request_policy import CodexReplayRequestCandidate
from tests.integration.test_codex_tool_history_postgres import (
    _ALL_CODEX_CAPS, _CODEX_RESPONSES_CAPS, _SUCCESS_KINDS, VLLM_CAPS,
    _auth_key, _gate_route_resolver, _group_b_settings, _route_probe,
    _seed_owned_history_world, rev16_client_module, upstream_route_capabilities,  # noqa: F401 - pytest fixture
)
from tests.unit.test_codex_tool_history_replay_wiring import base_model, decl, fn, ns, out, user
from tests.unit.test_responses_codex_streaming_tools import _added_tool, _done_tool


def _stream(tool=True):
    identity = dict(item_id="fc_delivery", call_id="call_delivery", namespace="functions",
                    name="read", custom=False)
    events = [{"type": "response.created", "response": {"id": "resp_delivery"}}]
    if tool:
        events += [
            _added_tool(**identity),
            {"type": "response.function_call_arguments.delta", "item_id": "fc_delivery",
             "output_index": 0, "delta": "{}"},
            _done_tool(**identity, text="{}"),
        ]
    else:
        events.append({"type": "response.output_text.delta", "delta": "Retry succeeded."})
    events.append({"type": "response.completed", "response": {
        "id": "resp_delivery", "status": "completed",
        "usage": {"input_tokens": 5, "output_tokens": 2, "total_tokens": 7},
    }})
    return events


@pytest.mark.asyncio
@pytest.mark.usefixtures("rev16_client_module")
@pytest.mark.parametrize("kind", ["vllm", "llama-preserve"])
@pytest.mark.parametrize("fault", ["provider_error", "missing_terminal", "invalid_event"])
async def test_fresh_failure_then_retry_then_owned_replay_settles_without_404(
    async_test_session, monkeypatch, fault, kind,
):
    session = async_test_session
    settings = _group_b_settings()
    spec = _SUCCESS_KINDS[kind]
    key, route = await _seed_owned_history_world(
        session, settings=settings, provider=spec.provider, allowed_capabilities=_ALL_CODEX_CAPS,
    )
    # The fixture contains pre-existing usage; this conversation starts with
    # genuinely empty replay state and no historical input items.
    await session.execute(delete(CodexReplayReference).where(CodexReplayReference.gateway_key_id == key.id))
    auth = _auth_key(key)
    caps = VLLM_CAPS if kind == "vllm" else upstream_route_capabilities(spec.profile_id)
    probe = _route_probe(route.id, spec.provider, {**caps, "responses": _CODEX_RESPONSES_CAPS})

    async def db(request=None):
        yield session

    monkeypatch.setattr(gateway, "_get_db_session_after_auth_header_check", db)
    monkeypatch.setattr(gateway, "_resolve_responses_route", _gate_route_resolver(probe))
    control = {"phase": 0, "calls": 0}

    class Adapter:
        async def stream_response(self, request):
            control["calls"] += 1
            events = _stream(tool=control["phase"] != 2)
            if control["phase"] == 0:
                events = events[:-1]
                if fault == "invalid_event":
                    events.append({"type": "unapproved.event"})
            for event in events:
                yield ProviderStreamChunk(
                    provider=request.provider, upstream_model=request.upstream_model,
                    data=json.dumps(event), json_body=event,
                    raw_sse_event="data: " + json.dumps(event) + "\n\n",
                    usage=(ProviderUsage(prompt_tokens=5, completion_tokens=2, total_tokens=7)
                           if event["type"] == "response.completed" else None),
                )
            if control["phase"] == 0 and fault == "provider_error":
                raise ProviderResponseParseError(provider=spec.provider,
                    error_code="vllm_tool_protocol_invalid", safe_message="Synthetic protocol failure")

    monkeypatch.setattr(gateway, "get_provider_adapter", lambda *args: Adapter())
    body = base_model()
    body.update(model="synthetic-codex-model", stream=True, store=False)
    body["input"] = [decl(ns("functions", fn("read"))), user("Read the test fixture.")]
    repository = CodexReplayReferencesRepository(session)
    replay = CodexReplayService(repository=repository, settings=settings)
    candidate = CodexReplayRequestCandidate(item_kind="function_call", item_id="fc_delivery",
        call_id="call_delivery", tool_namespace="functions", tool_name="read")

    async def invoke(payload):
        return await gateway.handle_response_create(
            payload=ResponsesCreateRequest.model_validate(payload), authenticated_key=auth,
            settings=settings,
        )

    before = key.requests_used_total
    response = await invoke(body)
    failed_events = [s async for s in response.body_iterator]
    assert "response.failed" in "".join(failed_events)
    assert "fc_delivery" not in "".join(failed_events)
    assert await session.scalar(select(func.count()).select_from(CodexReplayReference)
        .where(CodexReplayReference.gateway_key_id == key.id)) == 0
    with pytest.raises(CodexReplayReferenceError):
        await replay.verify_owned_replay(candidates=(candidate,), gateway_key_id=key.id)

    # Retrying the unchanged, fresh request now succeeds. At the instant its
    # first tool event is delivered, real accounting and HMAC ownership exist.
    control["phase"] = 1
    response = await invoke(body)
    successful = []
    async for event in response.body_iterator:
        if "fc_delivery" in event:
            authorization = await replay.verify_owned_replay(candidates=(candidate,), gateway_key_id=key.id)
            replay.verify_route_compatibility(authorization, provider=spec.provider,
                route_id=route.id, upstream_model=route.upstream_model)
        successful.append(event)
    assert "response.completed" in "".join(successful)
    with pytest.raises(CodexReplayReferenceError):
        await replay.verify_owned_replay(candidates=(candidate,), gateway_key_id=uuid.uuid4())

    # The next request contains only tool items the gateway actually delivered.
    control["phase"] = 2
    continuation = copy.deepcopy(body)
    tool = _stream()[3]["item"]
    continuation["input"].extend([tool, out("call_delivery"), user("Continue.")])
    response = await invoke(continuation)
    continued = "".join([s async for s in response.body_iterator])
    assert "response.completed" in continued and "response.failed" not in continued
    await session.refresh(key)
    assert key.requests_used_total == before + 3
    rows = list((await session.execute(select(UsageLedger).where(UsageLedger.gateway_key_id == key.id)
        .order_by(UsageLedger.started_at))).scalars())
    assert len(rows) == 4  # fixture usage + failed turn + successful retry + continuation
    assert rows[-1].success and rows[-1].accounting_status == "finalized"
    assert rows[-2].success and rows[-2].accounting_status == "finalized"
    assert rows[-1].total_tokens == rows[-2].total_tokens == 7
    assert not rows[-3].success and rows[-3].accounting_status == "estimated"
    reservations = list((await session.execute(select(QuotaReservation)
        .where(QuotaReservation.gateway_key_id == key.id))).scalars())
    assert len(reservations) == 3 and all(r.status == "finalized" for r in reservations)
    assert control["calls"] == 3
    assert key.tokens_reserved_total == 0 and key.requests_reserved_total == 0
