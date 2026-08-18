"""PostgreSQL proof for finalized-accounting-gated opaque compaction HMAC replay."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from slaif_gateway.config import Settings
from slaif_gateway.db.models import CodexReplayReference
from slaif_gateway.db.repositories.codex_replay import CodexReplayReferencesRepository
from slaif_gateway.db.repositories.cohorts import CohortsRepository
from slaif_gateway.db.repositories.keys import GatewayKeysRepository
from slaif_gateway.db.repositories.owners import OwnersRepository
from slaif_gateway.db.repositories.routing import ModelRoutesRepository
from slaif_gateway.db.repositories.usage import UsageLedgerRepository
from slaif_gateway.services.codex_replay_service import (
    CodexReplayReferenceError,
    CodexReplayService,
)


@dataclass(frozen=True, slots=True, repr=False)
class CompactionCandidate:
    item_kind: str
    item_id: str
    encrypted_content: str
    call_id: str | None = None
    tool_namespace: str | None = None
    tool_name: str | None = None


@pytest.mark.asyncio
async def test_compaction_postgres_persists_only_composite_hmac_after_finalized_ledger(
    async_test_session: AsyncSession,
) -> None:
    now = datetime.now(UTC)
    owner = await OwnersRepository(async_test_session).create_owner(
        name="Codex",
        surname="Compaction",
        email=f"codex-compaction-{uuid.uuid4().hex}@example.org",
    )
    cohort = await CohortsRepository(async_test_session).create_cohort(
        name=f"codex-compaction-{uuid.uuid4().hex}"
    )
    key_repository = GatewayKeysRepository(async_test_session)
    key = await key_repository.create_gateway_key_record(
        public_key_id=f"codex_compaction_{uuid.uuid4().hex}",
        token_hash=uuid.uuid4().hex,
        owner_id=owner.id,
        cohort_id=cohort.id,
        valid_from=now - timedelta(minutes=1),
        valid_until=now + timedelta(days=1),
    )
    other_key = await key_repository.create_gateway_key_record(
        public_key_id=f"codex_compaction_other_{uuid.uuid4().hex}",
        token_hash=uuid.uuid4().hex,
        owner_id=owner.id,
        cohort_id=cohort.id,
        valid_from=now - timedelta(minutes=1),
        valid_until=now + timedelta(days=1),
    )
    route = await ModelRoutesRepository(async_test_session).create_model_route(
        requested_model=f"classroom-codex-compact-{uuid.uuid4().hex}",
        provider="openai",
        upstream_model="gpt-test",
        endpoint="/v1/responses/compact",
    )
    request_id = f"req_codex_compaction_{uuid.uuid4().hex}"
    ledger = await UsageLedgerRepository(async_test_session).create_success_record(
        request_id=request_id,
        gateway_key_id=key.id,
        owner_id=owner.id,
        cohort_id=cohort.id,
        endpoint="/v1/responses/compact",
        provider="openai",
        started_at=now,
        finished_at=now,
        requested_model=route.requested_model,
        resolved_model=route.upstream_model,
        streaming=False,
    )
    candidate = CompactionCandidate(
        item_kind="compaction",
        item_id="cmp_private_provider_id",
        encrypted_content="opaque-private-ciphertext",
    )
    service = CodexReplayService(
        repository=CodexReplayReferencesRepository(async_test_session),
        settings=Settings(
            APP_ENV="development",
            TOKEN_HMAC_SECRET="postgres-compaction-test-secret",
            ACTIVE_HMAC_KEY_VERSION="1",
        ),
    )
    assert (
        await service.persist_validated_references(
            candidates=(candidate,),
            gateway_key_id=key.id,
            usage_ledger_id=ledger.id,
            source_request_id=request_id,
            provider="openai",
            route_id=route.id,
            upstream_model=route.upstream_model,
            now=now,
        )
        == 1
    )
    row = (
        await async_test_session.execute(
            select(CodexReplayReference).where(
                CodexReplayReference.gateway_key_id == key.id,
                CodexReplayReference.item_kind == "compaction",
            )
        )
    ).scalar_one()
    assert row.call_id_hmac is None
    assert len(row.item_id_hmac) == 64
    assert candidate.item_id not in row.item_id_hmac
    assert candidate.encrypted_content not in row.item_id_hmac

    authorization = await service.verify_owned_replay(
        candidates=(candidate,),
        gateway_key_id=key.id,
        now=now + timedelta(minutes=1),
    )
    service.verify_route_compatibility(
        authorization,
        provider="openai",
        route_id=route.id,
        upstream_model=route.upstream_model,
    )
    for altered, owner_id in (
        (
            CompactionCandidate(
                item_kind="compaction",
                item_id=candidate.item_id,
                encrypted_content="altered-ciphertext",
            ),
            key.id,
        ),
        (candidate, other_key.id),
    ):
        with pytest.raises(CodexReplayReferenceError):
            await service.verify_owned_replay(
                candidates=(altered,),
                gateway_key_id=owner_id,
                now=now + timedelta(minutes=1),
            )
