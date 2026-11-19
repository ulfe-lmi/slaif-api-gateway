"""Visible history never invents opaque authority or bypasses owned tool replay."""

from datetime import UTC, datetime
import uuid

import pytest
from sqlalchemy import func, select

from slaif_gateway.config import Settings
from slaif_gateway.db.models import CodexReplayReference
from slaif_gateway.db.repositories.codex_replay import CodexReplayReferencesRepository
from slaif_gateway.db.repositories.routing import ModelRoutesRepository
from slaif_gateway.db.repositories.usage import UsageLedgerRepository
from slaif_gateway.services.codex_replay_service import (
    CodexReplayReferenceError,
    CodexReplayService,
)
from slaif_gateway.services.responses_request_policy import (
    CodexReplayRequestCandidate,
    codex_replay_request_candidates,
)
from tests.integration.test_quota_reservation_postgres import _create_gateway_key


@pytest.mark.asyncio
@pytest.mark.parametrize("ciphertext_form", ["missing", "null", "empty"])
@pytest.mark.parametrize("positional", [False, True])
async def test_visible_reasoning_with_owned_tool_keeps_exact_ownership_checks(
    async_test_session, ciphertext_form, positional
):
    session = async_test_session
    key = await _create_gateway_key(session)
    other_key = await _create_gateway_key(session)
    route = await ModelRoutesRepository(session).create_model_route(
        requested_model="visible-replay-" + uuid.uuid4().hex,
        provider="openai",
        upstream_model="synthetic-model",
        endpoint="/v1/responses",
    )
    now = datetime.now(UTC)
    request_id = "visible-replay-" + uuid.uuid4().hex
    ledger = await UsageLedgerRepository(session).create_success_record(
        request_id=request_id,
        gateway_key_id=key.id,
        owner_id=key.owner_id,
        cohort_id=key.cohort_id,
        endpoint="/v1/responses",
        provider=route.provider,
        started_at=now,
        finished_at=now,
        requested_model=route.requested_model,
        resolved_model=route.upstream_model,
        streaming=True,
    )
    service = CodexReplayService(
        repository=CodexReplayReferencesRepository(session),
        settings=Settings(
            TOKEN_HMAC_SECRET="visible-replay-test-secret", ACTIVE_HMAC_KEY_VERSION="1"
        ),
    )
    tool = CodexReplayRequestCandidate(
        item_kind="function_call",
        item_id="fc_visible_test",
        call_id="call_visible_test",
        tool_namespace="functions",
        tool_name="wait",
    )
    assert (
        await service.persist_validated_references(
            candidates=(tool,),
            gateway_key_id=key.id,
            usage_ledger_id=ledger.id,
            source_request_id=request_id,
            provider=route.provider,
            route_id=route.id,
            upstream_model=route.upstream_model,
            now=now,
        )
        == 1
    )
    visible = {
        "type": "reasoning",
        "id": "rs_visible_test",
        "summary": [],
        "content": [{"type": "reasoning_text", "text": "Synthetic visible context"}],
    }
    if ciphertext_form != "missing":
        visible["encrypted_content"] = None if ciphertext_form == "null" else ""
    body = {
        "input": [
            visible,
            {
                "type": "function_call",
                "id": tool.item_id,
                "call_id": tool.call_id,
                "namespace": "functions",
                "name": "wait",
                "arguments": "{}",
            },
        ]
    }
    kwargs = dict(top_level_tool_taxonomy=frozenset({("functions", "wait", "function")}))
    if positional:
        kwargs["codex_tool_call_bindings"] = {tool.call_id: ("functions", "wait", "function")}
    candidates = codex_replay_request_candidates(body, require_call_completeness=True, **kwargs)
    assert len(candidates) == 1 and candidates[0].item_kind == "function_call"
    authorization = await service.verify_owned_replay(candidates=candidates, gateway_key_id=key.id)
    assert len(authorization.references) == 1
    service.verify_route_compatibility(
        authorization,
        provider=route.provider,
        route_id=route.id,
        upstream_model=route.upstream_model,
    )
    # Existing tool ownership, route binding and nonempty encrypted authority
    # remain mandatory; visible context cannot turn any of these into a bypass.
    with pytest.raises(CodexReplayReferenceError) as wrong_key:
        await service.verify_owned_replay(candidates=candidates, gateway_key_id=other_key.id)
    assert wrong_key.value.error_code == "responses_codex_replay_reference_not_found"
    with pytest.raises(CodexReplayReferenceError) as wrong_route:
        service.verify_route_compatibility(
            authorization,
            provider=route.provider,
            route_id=uuid.uuid4(),
            upstream_model=route.upstream_model,
        )
    assert wrong_route.value.error_code == "responses_codex_replay_route_mismatch"
    visible["encrypted_content"] = "synthetic-unowned-ciphertext"
    opaque = codex_replay_request_candidates(body, require_call_completeness=True, **kwargs)
    assert len(opaque) == 2 and opaque[0].item_kind == "reasoning"
    with pytest.raises(CodexReplayReferenceError) as unowned:
        await service.verify_owned_replay(candidates=opaque, gateway_key_id=key.id)
    assert unowned.value.error_code == "responses_codex_replay_reference_not_found"
    rows = (
        (
            await session.execute(
                select(CodexReplayReference).where(
                    CodexReplayReference.gateway_key_id == key.id,
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1 and rows[0].item_kind == "function_call"
    assert (
        await session.scalar(
            select(func.count())
            .select_from(CodexReplayReference)
            .where(
                CodexReplayReference.gateway_key_id == key.id,
                CodexReplayReference.item_kind == "reasoning",
            )
        )
        == 0
    )
