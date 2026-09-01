from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from slaif_gateway.config import Settings
from slaif_gateway.services.codex_replay_service import (
    CODEX_REPLAY_REFERENCE_TTL,
    CodexReplayReferenceError,
    CodexReplayService,
)


@dataclass(frozen=True, slots=True, repr=False)
class Candidate:
    item_kind: str
    item_id: str
    call_id: str | None = None
    tool_namespace: str | None = None
    tool_name: str | None = None
    encrypted_content: str | None = None


class FakeRepository:
    def __init__(self) -> None:
        self.rows: list[SimpleNamespace] = []
        self.upsert_calls = 0
        self.ledger_finalized = True

    async def usage_ledger_is_finalized_for_key(self, **kwargs):
        return self.ledger_finalized

    async def list_active_hmac_versions_for_key(self, *, gateway_key_id, item_kinds, now):
        return sorted(
            {
                row.hmac_key_version
                for row in self.rows
                if row.gateway_key_id == gateway_key_id
                and row.item_kind in item_kinds
                and row.expires_at > now
            }
        )

    async def list_active_by_item_digests(self, *, gateway_key_id, item_digests, now):
        allowed = set(item_digests)
        return [
            row
            for row in self.rows
            if row.gateway_key_id == gateway_key_id
            and (row.item_kind, row.item_id_hmac) in allowed
            and row.expires_at > now
        ]

    async def list_active_by_call_digests(self, *, gateway_key_id, call_digests, now):
        allowed = set(call_digests)
        return [
            row
            for row in self.rows
            if row.gateway_key_id == gateway_key_id
            and (row.item_kind, row.call_id_hmac) in allowed
            and row.expires_at > now
        ]

    async def upsert_many(self, records):
        self.upsert_calls += 1
        for record in records:
            existing = next(
                (
                    row
                    for row in self.rows
                    if row.gateway_key_id == record.gateway_key_id
                    and row.item_kind == record.item_kind
                    and row.item_id_hmac == record.item_id_hmac
                ),
                None,
            )
            row = (
                SimpleNamespace(**record.__dict__)
                if hasattr(record, "__dict__")
                else SimpleNamespace(**{name: getattr(record, name) for name in record.__slots__})
            )
            if existing is None:
                self.rows.append(row)
            else:
                self.rows[self.rows.index(existing)] = row


def _settings() -> Settings:
    return Settings(
        APP_ENV="development",
        TOKEN_HMAC_SECRET="unit-replay-secret",
        ACTIVE_HMAC_KEY_VERSION="1",
    )


def _reasoning() -> Candidate:
    return Candidate(item_kind="reasoning", item_id="rs_reasoning_1")


def _tool() -> Candidate:
    return Candidate(
        item_kind="custom_tool_call",
        item_id="ctc_1",
        call_id="call_1",
        tool_namespace="functions",
        tool_name="exec",
    )


def _function_tool() -> Candidate:
    return Candidate(
        item_kind="function_call",
        item_id="fc_1",
        call_id="call_1",
        tool_namespace="functions",
        tool_name="wait",
    )


def _compaction(*, content: str = "opaque-value") -> Candidate:
    return Candidate(
        item_kind="compaction",
        item_id="cmp_safe_1",
        encrypted_content=content,
    )


@pytest.mark.asyncio
async def test_compaction_digest_binds_id_and_ciphertext_after_finalized_accounting() -> None:
    repository = FakeRepository()
    service = CodexReplayService(repository=repository, settings=_settings())
    key_id = uuid.uuid4()
    route_id = uuid.uuid4()
    now = datetime(2026, 8, 18, 10, 0, tzinfo=UTC)
    await service.persist_validated_references(
        candidates=(_compaction(),),
        gateway_key_id=key_id,
        usage_ledger_id=uuid.uuid4(),
        source_request_id="req_compact_safe",
        provider="openai",
        route_id=route_id,
        upstream_model="gpt-test",
        now=now,
    )
    row = repository.rows[0]
    assert row.item_kind == "compaction"
    assert row.call_id_hmac is None
    assert "opaque-value" not in row.item_id_hmac
    assert "cmp_safe_1" not in row.item_id_hmac

    for altered in (
        _compaction(content="altered"),
        Candidate(
            item_kind="compaction",
            item_id="cmp_safe_2",
            encrypted_content="opaque-value",
        ),
    ):
        with pytest.raises(CodexReplayReferenceError):
            await service.verify_owned_replay(
                candidates=(altered,), gateway_key_id=key_id, now=now + timedelta(minutes=1)
            )

    authorization = await service.verify_owned_replay(
        candidates=(_compaction(),),
        gateway_key_id=key_id,
        now=now + timedelta(minutes=1),
    )
    compatible_route = uuid.uuid4()
    service.verify_route_compatibility(
        authorization,
        provider="openai",
        route_id=compatible_route,
        upstream_model="gpt-test",
        compatible_route_ids=frozenset({route_id}),
    )
    with pytest.raises(CodexReplayReferenceError):
        service.verify_route_compatibility(
            authorization,
            provider="openai",
            route_id=compatible_route,
            upstream_model="other-model",
            compatible_route_ids=frozenset({route_id}),
        )


@pytest.mark.asyncio
async def test_persist_and_verify_are_hmac_only_idempotent_and_route_bound() -> None:
    repository = FakeRepository()
    service = CodexReplayService(repository=repository, settings=_settings())
    key_id = uuid.uuid4()
    ledger_id = uuid.uuid4()
    route_id = uuid.uuid4()
    now = datetime(2026, 8, 18, 10, 0, tzinfo=UTC)
    candidates = (_reasoning(), _tool())

    count = await service.persist_validated_references(
        candidates=candidates,
        gateway_key_id=key_id,
        usage_ledger_id=ledger_id,
        source_request_id="req_safe_1",
        provider="openai",
        route_id=route_id,
        upstream_model="gpt-test",
        now=now,
    )
    await service.persist_validated_references(
        candidates=candidates,
        gateway_key_id=key_id,
        usage_ledger_id=ledger_id,
        source_request_id="req_safe_1",
        provider="openai",
        route_id=route_id,
        upstream_model="gpt-test",
        now=now,
    )

    assert count == 2
    assert repository.upsert_calls == 2
    assert len(repository.rows) == 2
    assert all(
        row.expires_at - row.created_at == CODEX_REPLAY_REFERENCE_TTL for row in repository.rows
    )
    assert all(len(row.item_id_hmac) == 64 for row in repository.rows)
    assert all(
        candidate.item_id not in row.item_id_hmac
        for candidate, row in zip(candidates, repository.rows, strict=True)
    )
    tool_row = next(row for row in repository.rows if row.item_kind == "custom_tool_call")
    assert tool_row.call_id_hmac is not None and len(tool_row.call_id_hmac) == 64
    assert _tool().call_id not in tool_row.call_id_hmac

    authorization = await service.verify_owned_replay(
        candidates=candidates,
        gateway_key_id=key_id,
        now=now + timedelta(minutes=1),
    )
    service.verify_route_compatibility(
        authorization,
        provider="openai",
        route_id=route_id,
        upstream_model="gpt-test",
    )
    assert [reference.item_kind for reference in authorization.references] == [
        "reasoning",
        "custom_tool_call",
    ]


@pytest.mark.asyncio
async def test_standalone_function_output_uses_active_call_hmac_and_exact_taxonomy() -> None:
    repository = FakeRepository()
    service = CodexReplayService(repository=repository, settings=_settings())
    key_id = uuid.uuid4()
    now = datetime(2026, 8, 18, 10, 0, tzinfo=UTC)
    await service.persist_validated_references(
        candidates=(_function_tool(),),
        gateway_key_id=key_id,
        usage_ledger_id=uuid.uuid4(),
        source_request_id="req_function_call",
        provider="openai",
        route_id=uuid.uuid4(),
        upstream_model="gpt-test",
        session_scope="session-a",
        now=now,
    )

    authorization = await service.verify_owned_function_output_calls(
        call_ids=("call_1",),
        gateway_key_id=key_id,
        tool_taxonomy=frozenset(
            {
                ("functions", "wait", "function"),
                ("functions", "exec", "custom"),
            }
        ),
        session_scope="session-a",
        now=now + timedelta(minutes=1),
    )
    assert [reference.item_kind for reference in authorization.references] == ["function_call"]
    assert repository.rows[0].call_id_hmac is not None

    with pytest.raises(CodexReplayReferenceError):
        await service.verify_owned_function_output_calls(
            call_ids=("call_1",),
            gateway_key_id=key_id,
            tool_taxonomy=frozenset({("functions", "wait", "function")}),
            session_scope="session-b",
            now=now + timedelta(minutes=1),
        )

    duplicate = SimpleNamespace(**vars(repository.rows[0]))
    duplicate.item_id_hmac = "0" * 64
    repository.rows.append(duplicate)
    with pytest.raises(CodexReplayReferenceError):
        await service.verify_owned_function_output_calls(
            call_ids=("call_1",),
            gateway_key_id=key_id,
            tool_taxonomy=frozenset({("functions", "wait", "function")}),
            session_scope="session-a",
            now=now + timedelta(minutes=1),
        )
    repository.rows.pop()

    for kwargs in (
        {"gateway_key_id": uuid.uuid4()},
        {"gateway_key_id": key_id, "tool_name": "other"},
        {"gateway_key_id": key_id, "tool_namespace": "collaboration"},
    ):
        with pytest.raises(CodexReplayReferenceError) as exc_info:
            await service.verify_owned_function_output_calls(
                call_ids=("call_1",),
                gateway_key_id=kwargs.get("gateway_key_id", key_id),
                tool_taxonomy=frozenset(
                    {
                        (
                            kwargs.get("tool_namespace", "functions"),
                            kwargs.get("tool_name", "wait"),
                            "function",
                        )
                    }
                ),
                now=now + timedelta(minutes=1),
                session_scope="session-a",
            )
        assert exc_info.value.error_code == "responses_codex_replay_reference_not_found"

    with pytest.raises(CodexReplayReferenceError):
        await service.verify_owned_function_output_calls(
            call_ids=("call_1", "call_2"),
            gateway_key_id=key_id,
            tool_taxonomy=frozenset({("functions", "wait", "function")}),
            session_scope="session-a",
            now=now + timedelta(minutes=1),
        )


@pytest.mark.asyncio
async def test_cross_key_expiry_name_and_route_mismatches_fail_closed() -> None:
    repository = FakeRepository()
    service = CodexReplayService(repository=repository, settings=_settings())
    key_id = uuid.uuid4()
    route_id = uuid.uuid4()
    now = datetime(2026, 8, 18, 10, 0, tzinfo=UTC)
    await service.persist_validated_references(
        candidates=(_tool(),),
        gateway_key_id=key_id,
        usage_ledger_id=uuid.uuid4(),
        source_request_id="req_safe_2",
        provider="openai",
        route_id=route_id,
        upstream_model="gpt-test",
        now=now,
    )

    for candidate, owner, checked_now in (
        (_tool(), uuid.uuid4(), now + timedelta(minutes=1)),
        (_tool(), key_id, now + CODEX_REPLAY_REFERENCE_TTL),
        (
            Candidate(
                item_kind="custom_tool_call",
                item_id="ctc_1",
                call_id="call_1",
                tool_namespace="functions",
                tool_name="wait",
            ),
            key_id,
            now + timedelta(minutes=1),
        ),
    ):
        with pytest.raises(CodexReplayReferenceError) as exc_info:
            await service.verify_owned_replay(
                candidates=(candidate,),
                gateway_key_id=owner,
                now=checked_now,
            )
        assert exc_info.value.error_code == "responses_codex_replay_reference_not_found"

    authorization = await service.verify_owned_replay(
        candidates=(_tool(),),
        gateway_key_id=key_id,
        now=now + timedelta(minutes=1),
    )
    with pytest.raises(CodexReplayReferenceError) as exc_info:
        service.verify_route_compatibility(
            authorization,
            provider="openrouter",
            route_id=route_id,
            upstream_model="gpt-test",
        )
    assert exc_info.value.error_code == "responses_codex_replay_route_mismatch"


@pytest.mark.asyncio
async def test_unavailable_stored_hmac_version_is_refused() -> None:
    repository = FakeRepository()
    repository.rows.append(
        SimpleNamespace(
            gateway_key_id=uuid.uuid4(),
            item_kind="reasoning",
            item_id_hmac="0" * 64,
            call_id_hmac=None,
            hmac_key_version=2,
            tool_namespace=None,
            tool_name=None,
            provider="openai",
            route_id=uuid.uuid4(),
            upstream_model="gpt-test",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
    )
    service = CodexReplayService(repository=repository, settings=_settings())

    with pytest.raises(CodexReplayReferenceError) as exc_info:
        await service.verify_owned_replay(
            candidates=(_reasoning(),),
            gateway_key_id=repository.rows[0].gateway_key_id,
        )
    assert exc_info.value.error_code == "responses_codex_replay_hmac_unavailable"


@pytest.mark.asyncio
async def test_reference_persistence_requires_finalized_same_key_ledger() -> None:
    repository = FakeRepository()
    repository.ledger_finalized = False
    service = CodexReplayService(repository=repository, settings=_settings())
    with pytest.raises(CodexReplayReferenceError) as exc_info:
        await service.persist_validated_references(
            candidates=(_reasoning(),),
            gateway_key_id=uuid.uuid4(),
            usage_ledger_id=uuid.uuid4(),
            source_request_id="req_not_finalized",
            provider="openai",
            route_id=uuid.uuid4(),
            upstream_model="gpt-test",
        )
    assert exc_info.value.error_code == "responses_codex_replay_persistence_failed"
    assert repository.upsert_calls == 0


@pytest.mark.asyncio
async def test_digest_lookup_failure_has_no_private_exception_chain() -> None:
    private_canary = "private-item-or-digest-canary"

    class FailingRepository(FakeRepository):
        async def list_active_hmac_versions_for_key(self, **kwargs):
            return [1]

        async def list_active_by_item_digests(self, **kwargs):
            raise RuntimeError(private_canary)

    service = CodexReplayService(repository=FailingRepository(), settings=_settings())
    with pytest.raises(CodexReplayReferenceError) as exc_info:
        await service.verify_owned_replay(
            candidates=(Candidate(item_kind="reasoning", item_id=private_canary),),
            gateway_key_id=uuid.uuid4(),
        )
    assert exc_info.value.error_code == "responses_codex_replay_reference_not_found"
    assert exc_info.value.__cause__ is None
    assert private_canary not in repr(exc_info.value)
