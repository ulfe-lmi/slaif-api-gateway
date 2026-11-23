"""Unit coverage for the owned ciphertext-derived id-less reasoning replay path.

The OpenCode Responses wire replays encrypted reasoning output items without
item IDs or status fields. The gateway therefore needs a bounded, domain-
separated HMAC reference derived from the ciphertext itself: immediate
memory only, no fabricated protocol ID, no raw-content storage, persisted
only after successful finalized accounting, and bound to the same key and
route/provider/model. All stored digest material is opaque HMAC output; the
ciphertext never appears in stored rows.
"""

from __future__ import annotations

import re
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
    _item_digest,
)
from slaif_gateway.utils.crypto import hmac_sha256_token

_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_SECRET = "unit-replay-secret"
_CIPHER = "enc_" + "ab" * 31  # 64 bounded synthetic ciphertext bytes
_OTHER_CIPHER = "enc_" + "cd" * 31


@dataclass(frozen=True, slots=True, repr=False)
class Candidate:
    item_kind: str
    item_id: str | None
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
        TOKEN_HMAC_SECRET=_SECRET,
        ACTIVE_HMAC_KEY_VERSION="1",
    )


def _idless_reasoning(*, cipher: str = _CIPHER) -> Candidate:
    return Candidate(item_kind="reasoning", item_id=None, encrypted_content=cipher)


def _expected_v3_digest(cipher: str) -> str:
    return hmac_sha256_token(
        token=f"slaif-codex-replay:v3:reasoning:{len(cipher.encode('utf-8'))}:{cipher}",
        secret=_SECRET,
    )


async def _persist_idless_reasoning(
    service: CodexReplayService, *, key_id: uuid.UUID, route_id: uuid.UUID, now: datetime
) -> None:
    await service.persist_validated_references(
        candidates=(_idless_reasoning(),),
        gateway_key_id=key_id,
        usage_ledger_id=uuid.uuid4(),
        source_request_id="req_idless_reasoning",
        provider="openai",
        route_id=route_id,
        upstream_model="gpt-test",
        now=now,
        allow_idless_encrypted_reasoning=True,
    )


@pytest.mark.asyncio
async def test_idless_reasoning_is_rejected_when_flag_is_off() -> None:
    """Legacy behavior: id-less reasoning never passed the immediate step."""

    service = CodexReplayService(repository=FakeRepository(), settings=_settings())
    with pytest.raises(CodexReplayReferenceError) as verify_error:
        await service.verify_owned_replay(
            candidates=(_idless_reasoning(),),
            gateway_key_id=uuid.uuid4(),
        )
    assert verify_error.value.error_code == "responses_codex_replay_reference_not_found"

    repository = FakeRepository()
    service = CodexReplayService(repository=repository, settings=_settings())
    with pytest.raises(CodexReplayReferenceError) as persist_error:
        await service.persist_validated_references(
            candidates=(_idless_reasoning(),),
            gateway_key_id=uuid.uuid4(),
            usage_ledger_id=uuid.uuid4(),
            source_request_id="req_flag_off",
            provider="openai",
            route_id=uuid.uuid4(),
            upstream_model="gpt-test",
        )
    assert persist_error.value.error_code == "responses_codex_replay_reference_not_found"
    assert repository.rows == []


@pytest.mark.asyncio
async def test_idless_reasoning_rejects_missing_empty_or_oversized_cipher() -> None:
    service = CodexReplayService(repository=FakeRepository(), settings=_settings())
    key_id = uuid.uuid4()
    for candidate in (
        Candidate(item_kind="reasoning", item_id=None, encrypted_content=None),
        Candidate(item_kind="reasoning", item_id=None, encrypted_content=""),
        Candidate(
            item_kind="reasoning",
            item_id=None,
            encrypted_content="x" * 1_048_577,
        ),
    ):
        with pytest.raises(CodexReplayReferenceError) as exc_info:
            await service.verify_owned_replay(
                candidates=(candidate,),
                gateway_key_id=key_id,
                allow_idless_encrypted_reasoning=True,
            )
        assert exc_info.value.error_code == "responses_codex_replay_reference_not_found"


@pytest.mark.asyncio
async def test_idless_reasoning_rejects_duplicate_identical_cipher() -> None:
    service = CodexReplayService(repository=FakeRepository(), settings=_settings())
    key_id = uuid.uuid4()
    with pytest.raises(CodexReplayReferenceError) as exc_info:
        await service.verify_owned_replay(
            candidates=(_idless_reasoning(), _idless_reasoning()),
            gateway_key_id=key_id,
            allow_idless_encrypted_reasoning=True,
        )
    assert exc_info.value.error_code == "responses_codex_replay_reference_not_found"


@pytest.mark.asyncio
async def test_idpresent_reasoning_with_cipher_is_rejected_defensively() -> None:
    """ID-bound reasoning rows exist; a cipher plus ID must be denied, flag on or off."""

    service = CodexReplayService(repository=FakeRepository(), settings=_settings())
    key_id = uuid.uuid4()
    for flag in (False, True):
        with pytest.raises(CodexReplayReferenceError) as exc_info:
            await service.verify_owned_replay(
                candidates=(
                    Candidate(
                        item_kind="reasoning",
                        item_id="rs_reasoning_1",
                        encrypted_content=_CIPHER,
                    ),
                ),
                gateway_key_id=key_id,
                allow_idless_encrypted_reasoning=flag,
            )
        assert exc_info.value.error_code == "responses_codex_replay_reference_not_found"


@pytest.mark.asyncio
async def test_idpresent_reasoning_with_invalid_id_is_rejected() -> None:
    service = CodexReplayService(repository=FakeRepository(), settings=_settings())
    key_id = uuid.uuid4()
    for item_id in ("bad id", " lead", "toolong" * 40):
        with pytest.raises(CodexReplayReferenceError):
            await service.verify_owned_replay(
                candidates=(Candidate(item_kind="reasoning", item_id=item_id),),
                gateway_key_id=key_id,
                allow_idless_encrypted_reasoning=True,
            )


@pytest.mark.asyncio
async def test_persist_verify_same_key_route_immediate_continuation() -> None:
    repository = FakeRepository()
    service = CodexReplayService(repository=repository, settings=_settings())
    key_id = uuid.uuid4()
    route_id = uuid.uuid4()
    now = datetime(2026, 11, 23, 9, 0, tzinfo=UTC)
    await _persist_idless_reasoning(
        service, key_id=key_id, route_id=route_id, now=now
    )

    (row,) = repository.rows
    assert row.item_kind == "reasoning"
    assert row.call_id_hmac is None
    assert row.tool_namespace is None
    assert row.tool_name is None
    assert row.provider == "openai"
    assert row.route_id == route_id
    assert row.upstream_model == "gpt-test"
    assert _HEX64.fullmatch(row.item_id_hmac) is not None
    assert row.item_id_hmac == _expected_v3_digest(_CIPHER)
    assert _CIPHER not in row.item_id_hmac
    assert row.expires_at == now + CODEX_REPLAY_REFERENCE_TTL

    authorization = await service.verify_owned_replay(
        candidates=(_idless_reasoning(),),
        gateway_key_id=key_id,
        now=now + timedelta(minutes=1),
        allow_idless_encrypted_reasoning=True,
    )
    (reference,) = authorization.references
    assert reference.item_kind == "reasoning"
    assert reference.provider == "openai"
    assert reference.route_id == route_id
    assert reference.upstream_model == "gpt-test"
    assert reference.expires_at == row.expires_at
    service.verify_route_compatibility(
        authorization,
        provider="openai",
        route_id=route_id,
        upstream_model="gpt-test",
    )


@pytest.mark.asyncio
async def test_altered_cipher_is_denied() -> None:
    """Same length, different bytes: the HMAC reference must not match."""

    repository = FakeRepository()
    service = CodexReplayService(repository=repository, settings=_settings())
    key_id = uuid.uuid4()
    now = datetime(2026, 11, 23, 9, 0, tzinfo=UTC)
    await _persist_idless_reasoning(
        service, key_id=key_id, route_id=uuid.uuid4(), now=now
    )
    with pytest.raises(CodexReplayReferenceError) as exc_info:
        await service.verify_owned_replay(
            candidates=(_idless_reasoning(cipher=_OTHER_CIPHER),),
            gateway_key_id=key_id,
            now=now + timedelta(minutes=1),
            allow_idless_encrypted_reasoning=True,
        )
    assert exc_info.value.error_code == "responses_codex_replay_reference_not_found"


@pytest.mark.asyncio
async def test_foreign_key_is_denied() -> None:
    repository = FakeRepository()
    service = CodexReplayService(repository=repository, settings=_settings())
    key_id = uuid.uuid4()
    now = datetime(2026, 11, 23, 9, 0, tzinfo=UTC)
    await _persist_idless_reasoning(
        service, key_id=key_id, route_id=uuid.uuid4(), now=now
    )
    with pytest.raises(CodexReplayReferenceError) as exc_info:
        await service.verify_owned_replay(
            candidates=(_idless_reasoning(),),
            gateway_key_id=uuid.uuid4(),
            now=now + timedelta(minutes=1),
            allow_idless_encrypted_reasoning=True,
        )
    assert exc_info.value.error_code == "responses_codex_replay_reference_not_found"


@pytest.mark.asyncio
async def test_stale_reference_is_denied() -> None:
    repository = FakeRepository()
    service = CodexReplayService(repository=repository, settings=_settings())
    key_id = uuid.uuid4()
    now = datetime(2026, 11, 23, 9, 0, tzinfo=UTC)
    await _persist_idless_reasoning(
        service, key_id=key_id, route_id=uuid.uuid4(), now=now
    )
    with pytest.raises(CodexReplayReferenceError) as exc_info:
        await service.verify_owned_replay(
            candidates=(_idless_reasoning(),),
            gateway_key_id=key_id,
            now=now + CODEX_REPLAY_REFERENCE_TTL,
            allow_idless_encrypted_reasoning=True,
        )
    assert exc_info.value.error_code == "responses_codex_replay_reference_not_found"


@pytest.mark.asyncio
async def test_route_provider_and_model_mismatch_are_denied() -> None:
    repository = FakeRepository()
    service = CodexReplayService(repository=repository, settings=_settings())
    key_id = uuid.uuid4()
    route_id = uuid.uuid4()
    now = datetime(2026, 11, 23, 9, 0, tzinfo=UTC)
    await _persist_idless_reasoning(
        service, key_id=key_id, route_id=route_id, now=now
    )
    authorization = await service.verify_owned_replay(
        candidates=(_idless_reasoning(),),
        gateway_key_id=key_id,
        now=now + timedelta(minutes=1),
        allow_idless_encrypted_reasoning=True,
    )
    for provider, route, model in (
        ("openrouter", route_id, "gpt-test"),
        ("openai", uuid.uuid4(), "gpt-test"),
        ("openai", route_id, "other-model"),
    ):
        with pytest.raises(CodexReplayReferenceError) as exc_info:
            service.verify_route_compatibility(
                authorization,
                provider=provider,
                route_id=route,
                upstream_model=model,
            )
        assert exc_info.value.error_code == "responses_codex_replay_route_mismatch"


@pytest.mark.asyncio
async def test_present_wrong_id_is_denied_not_folded_into_idless_path() -> None:
    """A present-but-unowned ID must fail instead of falling through to v3."""

    repository = FakeRepository()
    service = CodexReplayService(repository=repository, settings=_settings())
    key_id = uuid.uuid4()
    now = datetime(2026, 11, 23, 9, 0, tzinfo=UTC)
    await _persist_idless_reasoning(
        service, key_id=key_id, route_id=uuid.uuid4(), now=now
    )
    with pytest.raises(CodexReplayReferenceError) as exc_info:
        await service.verify_owned_replay(
            candidates=(Candidate(item_kind="reasoning", item_id="rs_unissued"),),
            gateway_key_id=key_id,
            now=now + timedelta(minutes=1),
            allow_idless_encrypted_reasoning=True,
        )
    assert exc_info.value.error_code == "responses_codex_replay_reference_not_found"


@pytest.mark.asyncio
async def test_mixed_idpresent_and_idless_reasoning_each_match_exactly_once() -> None:
    repository = FakeRepository()
    service = CodexReplayService(repository=repository, settings=_settings())
    key_id = uuid.uuid4()
    route_id = uuid.uuid4()
    now = datetime(2026, 11, 23, 9, 0, tzinfo=UTC)
    await service.persist_validated_references(
        candidates=(
            Candidate(item_kind="reasoning", item_id="rs_owned_1"),
            _idless_reasoning(),
        ),
        gateway_key_id=key_id,
        usage_ledger_id=uuid.uuid4(),
        source_request_id="req_mixed",
        provider="openai",
        route_id=route_id,
        upstream_model="gpt-test",
        now=now,
        allow_idless_encrypted_reasoning=True,
    )
    assert len(repository.rows) == 2
    legacy_row = next(
        row for row in repository.rows if row.item_id_hmac != _expected_v3_digest(_CIPHER)
    )
    assert _HEX64.fullmatch(legacy_row.item_id_hmac) is not None
    assert legacy_row.item_id_hmac == hmac_sha256_token(
        token="slaif-codex-replay:v1:item:reasoning:rs_owned_1", secret=_SECRET
    )

    authorization = await service.verify_owned_replay(
        candidates=(
            Candidate(item_kind="reasoning", item_id="rs_owned_1"),
            _idless_reasoning(),
        ),
        gateway_key_id=key_id,
        now=now + timedelta(minutes=1),
        allow_idless_encrypted_reasoning=True,
    )
    assert [reference.item_kind for reference in authorization.references] == [
        "reasoning",
        "reasoning",
    ]

    # Presenting the owned ID twice must still be rejected as a duplicate.
    with pytest.raises(CodexReplayReferenceError):
        await service.verify_owned_replay(
            candidates=(
                Candidate(item_kind="reasoning", item_id="rs_owned_1"),
                Candidate(item_kind="reasoning", item_id="rs_owned_1"),
            ),
            gateway_key_id=key_id,
            now=now + timedelta(minutes=1),
            allow_idless_encrypted_reasoning=True,
        )


@pytest.mark.asyncio
async def test_legacy_idpresent_reasoning_digest_is_byte_unchanged() -> None:
    """Flag-off persistence keeps the exact v1 item digest for owned IDs."""

    repository = FakeRepository()
    service = CodexReplayService(repository=repository, settings=_settings())
    key_id = uuid.uuid4()
    now = datetime(2026, 11, 23, 9, 0, tzinfo=UTC)
    candidate = Candidate(item_kind="reasoning", item_id="rs_legacy_1")
    await service.persist_validated_references(
        candidates=(candidate,),
        gateway_key_id=key_id,
        usage_ledger_id=uuid.uuid4(),
        source_request_id="req_legacy",
        provider="openai",
        route_id=uuid.uuid4(),
        upstream_model="gpt-test",
        now=now,
    )
    (row,) = repository.rows
    assert row.item_id_hmac == hmac_sha256_token(
        token="slaif-codex-replay:v1:item:reasoning:rs_legacy_1", secret=_SECRET
    )
    assert row.item_id_hmac == _item_digest(candidate, secret=_SECRET)


@pytest.mark.asyncio
async def test_idless_tool_calls_still_use_call_digest_path() -> None:
    """The id-less tool path is untouched: rows match through call_id_hmac."""

    repository = FakeRepository()
    service = CodexReplayService(repository=repository, settings=_settings())
    key_id = uuid.uuid4()
    route_id = uuid.uuid4()
    now = datetime(2026, 11, 23, 9, 0, tzinfo=UTC)
    stored = Candidate(
        item_kind="function_call",
        item_id="fc_prefixed_1",
        call_id="call_1",
        tool_namespace="functions",
        tool_name="exec",
    )
    await service.persist_validated_references(
        candidates=(stored,),
        gateway_key_id=key_id,
        usage_ledger_id=uuid.uuid4(),
        source_request_id="req_tool",
        provider="local-coding",
        route_id=route_id,
        upstream_model="qwen-test",
        now=now,
    )
    reasoning_route = uuid.uuid4()
    await service.persist_validated_references(
        candidates=(_idless_reasoning(),),
        gateway_key_id=key_id,
        usage_ledger_id=uuid.uuid4(),
        source_request_id="req_tool_reasoning",
        provider="openai",
        route_id=reasoning_route,
        upstream_model="gpt-test",
        now=now,
        allow_idless_encrypted_reasoning=True,
    )
    idless_tool = Candidate(
        item_kind="function_call",
        item_id=None,
        call_id="call_1",
        tool_namespace="functions",
        tool_name="exec",
    )
    authorization = await service.verify_owned_replay(
        candidates=(idless_tool, _idless_reasoning()),
        gateway_key_id=key_id,
        now=now + timedelta(minutes=1),
        allow_idless_tool_call_replay=True,
        allow_idless_encrypted_reasoning=True,
    )
    assert [reference.item_kind for reference in authorization.references] == [
        "function_call",
        "reasoning",
    ]
    assert authorization.references[1].route_id == reasoning_route
    # The id-less tool row keeps its prefixed item digest, not a v3 digest.
    (tool_row,) = (
        row for row in repository.rows if row.item_kind == "function_call"
    )
    assert tool_row.item_id_hmac == hmac_sha256_token(
        token="slaif-codex-replay:v1:item:function_call:fc_prefixed_1",
        secret=_SECRET,
    )
    assert tool_row.call_id_hmac == hmac_sha256_token(
        token="slaif-codex-replay:v1:call:function_call:call_1", secret=_SECRET
    )
    # The reasoning row is the v3 ciphertext digest, opaque and 64-hex.
    (reasoning_row,) = (row for row in repository.rows if row.item_kind == "reasoning")
    assert reasoning_row.item_id_hmac == _expected_v3_digest(_CIPHER)
    assert reasoning_row.call_id_hmac is None


@pytest.mark.asyncio
async def test_v3_digest_is_domain_separated_from_v1() -> None:
    """Identical bytes must not collide across digest protocol versions."""

    candidate = _idless_reasoning()
    v3 = _item_digest(candidate, secret=_SECRET)
    v1_like = hmac_sha256_token(
        token=f"slaif-codex-replay:v1:item:reasoning:{_CIPHER}", secret=_SECRET
    )
    assert v3 != v1_like
    assert _HEX64.fullmatch(v3) is not None
