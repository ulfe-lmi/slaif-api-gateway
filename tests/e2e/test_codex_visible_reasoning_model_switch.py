"""SDK -> gateway -> two adapters -> PostgreSQL, with mocked provider SSE."""

import asyncio
import copy
import json
import uuid
from pathlib import Path

import httpx
import pytest
import respx
from openai import NotFoundError, OpenAI
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from slaif_gateway.db.models import CodexReplayReference, GatewayKey, ModelRoute, UsageLedger
from tests.e2e.test_codex_0162_local_tools import _local_coding_environment, _local_coding_test_data_kwargs
from tests.e2e.test_openai_python_client_chat import _configure_runtime_environment, _free_port, _run_uvicorn_server
from tests.e2e.test_openai_python_client_responses import (
    _codex_standard_stream, _codex_vllm_usage, _create_responses_test_data, _sse,
)
from tests.integration.db_test_utils import run_alembic_upgrade_head
from tests.integration.test_lazy_throttling_postgres_redis import owned_pg_url  # noqa: F401
from tests.unit.test_codex_reasoning_representation_switch import _events, _item
from tests.unit.test_upstream_llm_adapter import capabilities


@pytest.fixture
def scoped_profile_bootstrap(monkeypatch):
    """Restore registry state without weakening immutable production bootstrap."""
    from slaif_gateway.modules.clients import registry
    from slaif_gateway.modules.clients.codex_0162 import CODEX_0162_CLIENT_MODULE_ID

    monkeypatch.setitem(
        registry._CLIENT_MODULE_REGISTRY_ENTRIES, CODEX_0162_CLIENT_MODULE_ID,
        registry._CLIENT_MODULE_REGISTRY_ENTRIES[CODEX_0162_CLIENT_MODULE_ID],
    )
    monkeypatch.setattr(registry, "CODEX_0162_CLIENT_MODULE_INSTANCE", registry.CODEX_0162_CLIENT_MODULE_INSTANCE)
    monkeypatch.setattr(registry, "_CODEX_0162_BOOTSTRAP_BOUND", False)


def _wire_stream(form, turn, model):
    rid = f"resp_switch_{turn}"
    reasoning = _item(form, done=True, item_id=f"rs_switch_{turn}")
    events = _events(form, response_id=rid, item_id=reasoning["id"])
    message = {
        "type": "message", "id": "stream_message_1", "status": "completed",
        "role": "assistant", "phase": None, "summary": [],
        "content": [{"type": "output_text", "text": "answer", "annotations": [], "logprobs": None}],
    }
    response = {
        "id": rid, "object": "response", "created_at": 123, "model": model,
        "status": "completed", "output": [reasoning, message], "usage": _codex_vllm_usage(10, 4),
    }
    # The existing message fixture follows the reasoning lifecycle unchanged.
    for line in _codex_standard_stream(response).splitlines():
        if not line.startswith("data: "):
            continue
        event = json.loads(line[6:])
        if event["type"] == "response.created":
            continue
        if "output_index" in event:
            event["output_index"] = 1
        events.append(event)
    for sequence, event in enumerate(events):
        event["sequence_number"] = sequence
    return "".join(_sse(event) for event in events)


@pytest.mark.e2e
@pytest.mark.parametrize("first_native", [False, True])
def test_visible_reasoning_survives_bidirectional_model_switch(
    monkeypatch, owned_pg_url: str, first_native: bool, scoped_profile_bootstrap,  # noqa: F811
):
    """Retain each turn's reasoning, switch adapters A->B->A, then deny opaque forgery."""
    db = owned_pg_url
    run_alembic_upgrade_head(db)
    _configure_runtime_environment(monkeypatch, db)
    _local_coding_environment(monkeypatch)
    profile_path = Path(__file__).resolve().parents[2] / "app/slaif_gateway/modules/clients/profiles/codex-0.167.1.json"
    monkeypatch.setenv("CODEX_COMPATIBILITY_PROFILE_FILE", str(profile_path))
    monkeypatch.setenv("UPSTREAM_LLM_PROFILES_FILE", "")
    from slaif_gateway.config import get_settings
    from slaif_gateway.main import create_app

    get_settings.cache_clear()
    app = create_app(get_settings())
    module = app.state.codex_0162_profile
    pin = {"id": module.module_id, "version": module.revision, "fixture_sha256": module.digest}
    suffix = uuid.uuid4().hex
    models = [f"switch-visible-{suffix}-preserve", f"switch-visible-{suffix}-native"]
    providers = [f"switch-preserve-{suffix}", f"switch-native-{suffix}"]
    bases = [f"http://127.0.0.1:{_free_port()}/v1" for _ in models]
    created = []
    try:
        for model, provider, base in zip(models, providers, bases, strict=True):
            kwargs = _local_coding_test_data_kwargs(pin)
            kwargs.update(provider=provider, upstream_model=model + "-upstream")
            created.append(asyncio.run(_create_responses_test_data(db, model=model, base_url=base, **kwargs)))

        async def configure():
            engine = create_async_engine(db)
            try:
                async with async_sessionmaker(engine)() as session:
                    key = await session.get(GatewayKey, created[0].gateway_key_id)
                    key.allowed_models = models
                    key.allowed_providers = providers
                    for model, profile in zip(models, ["responses-passthrough-v1", "native-vllm-v1"], strict=True):
                        route = (await session.execute(select(ModelRoute).where(ModelRoute.requested_model == model))).scalar_one()
                        route.capabilities = {**route.capabilities, **capabilities(profile)}
                    await session.commit()
            finally:
                await engine.dispose()

        asyncio.run(configure())
        order = [1, 0, 1] if first_native else [0, 1, 0]
        observed = []

        def upstream(request):
            body = json.loads(request.content)
            route_index = order[len(observed)]
            assert body["model"] == models[route_index] + "-upstream"
            assert request.headers["authorization"] == "Bearer synthetic-local-coding-service-bearer"
            retained = [i for i in body["input"] if i.get("type") == "reasoning"]
            assert len(retained) == len(observed)
            for prior, item in enumerate(retained):
                assert item["encrypted_content"] == (None if order[prior] else "")
                assert item["content"][0]["text"] == "synthetic reasoning"
            observed.append(body)
            return httpx.Response(200, text=_wire_stream("null" if route_index else "empty", len(observed), body["model"]), headers={"content-type": "text/event-stream"})

        port = _free_port()
        monkeypatch.setenv("OPENAI_API_KEY", created[0].plaintext_key)
        monkeypatch.setenv("OPENAI_BASE_URL", f"http://127.0.0.1:{port}/v1")
        history = [{"type": "additional_tools", "role": "developer", "tools": [{"type": "namespace", "name": "functions", "tools": [{"type": "function", "name": "read", "parameters": {"type": "object", "properties": {}}}]}]}, {"role": "user", "content": "Synthetic switching check"}]
        with _run_uvicorn_server(app, port), respx.mock(assert_all_mocked=True, assert_all_called=False) as router:
            for base in bases:
                router.post(base + "/responses").mock(side_effect=upstream)
            router.route(host="127.0.0.1", port=port).pass_through()
            client = OpenAI(max_retries=0)
            for index in order:
                events = list(client.responses.create(model=models[index], input=history, stream=True, max_output_tokens=64))
                assert not any(e.type in {"error", "response.failed"} for e in events)
                completed = next(e.response for e in events if e.type == "response.completed")
                assert completed.output_text == "answer"
                reasoning = completed.output[0].model_dump(mode="json", exclude_none=False)
                # Rust ResponseItem serialization omits provider-only status.
                reasoning = {k: reasoning[k] for k in ("type", "id", "summary", "content", "encrypted_content")}
                history.extend([reasoning, {"role": "user", "content": "Continue on the other model"}])
            forged = copy.deepcopy(history)
            forged[2] = {"type": "reasoning", "id": "rs_unowned_opaque", "summary": [], "encrypted_content": "opaque-foreign-ciphertext"}
            with pytest.raises(NotFoundError) as error:
                list(client.responses.create(model=models[order[-1]], input=forged, stream=True, max_output_tokens=64))
            assert error.value.code == "responses_codex_replay_reference_not_found"
            client.close()
        assert len(observed) == 3

        async def accounting():
            engine = create_async_engine(db)
            try:
                async with async_sessionmaker(engine)() as session:
                    rows = (await session.execute(select(UsageLedger).where(UsageLedger.gateway_key_id == created[0].gateway_key_id))).scalars().all()
                    assert len(rows) == 3
                    assert all(r.success and r.accounting_status == "finalized" for r in rows)
                    assert sum(r.total_tokens for r in rows) == 42
                    refs = await session.scalar(select(func.count()).select_from(CodexReplayReference).where(CodexReplayReference.gateway_key_id == created[0].gateway_key_id))
                    assert refs == 0  # Visible IDs never acquire opaque ownership.
            finally:
                await engine.dispose()
        asyncio.run(accounting())
    finally:
        get_settings.cache_clear()
