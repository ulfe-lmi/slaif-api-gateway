"""PostgreSQL proof for HMAC-only Codex replay ownership and idempotency."""

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
class Candidate:
    item_kind: str
    item_id: str
    call_id: str | None = None
    tool_namespace: str | None = None
    tool_name: str | None = None


@pytest.mark.asyncio
async def test_codex_replay_postgres_hmac_only_same_key_and_expiry(
    async_test_session: AsyncSession,
) -> None:
    now = datetime.now(UTC)
    owners = OwnersRepository(async_test_session)
    cohorts = CohortsRepository(async_test_session)
    keys = GatewayKeysRepository(async_test_session)
    routes = ModelRoutesRepository(async_test_session)
    usage = UsageLedgerRepository(async_test_session)
    owner = await owners.create_owner(
        name="Codex",
        surname="Replay",
        email=f"codex-replay-{uuid.uuid4().hex}@example.org",
    )
    cohort = await cohorts.create_cohort(name=f"codex-replay-{uuid.uuid4().hex}")
    key = await keys.create_gateway_key_record(
        public_key_id=f"codex_replay_{uuid.uuid4().hex}",
        token_hash=uuid.uuid4().hex,
        owner_id=owner.id,
        cohort_id=cohort.id,
        valid_from=now - timedelta(minutes=1),
        valid_until=now + timedelta(days=1),
    )
    other_key = await keys.create_gateway_key_record(
        public_key_id=f"codex_replay_other_{uuid.uuid4().hex}",
        token_hash=uuid.uuid4().hex,
        owner_id=owner.id,
        cohort_id=cohort.id,
        valid_from=now - timedelta(minutes=1),
        valid_until=now + timedelta(days=1),
    )
    route = await routes.create_model_route(
        requested_model=f"classroom-codex-{uuid.uuid4().hex}",
        provider="openai",
        upstream_model="gpt-test",
        endpoint="/v1/responses",
    )
    request_id = f"req_codex_replay_{uuid.uuid4().hex}"
    ledger = await usage.create_success_record(
        request_id=request_id,
        gateway_key_id=key.id,
        owner_id=owner.id,
        cohort_id=cohort.id,
        endpoint="/v1/responses",
        provider="openai",
        started_at=now,
        finished_at=now,
        requested_model=route.requested_model,
        resolved_model=route.upstream_model,
        streaming=True,
    )
    candidates = (
        Candidate(item_kind="reasoning", item_id="rs_private_raw_id"),
        Candidate(
            item_kind="custom_tool_call",
            item_id="ctc_private_raw_id",
            call_id="call_private_raw_id",
            tool_namespace="functions",
            tool_name="exec",
        ),
    )
    settings = Settings(
        APP_ENV="development",
        TOKEN_HMAC_SECRET="postgres-replay-test-secret",
        ACTIVE_HMAC_KEY_VERSION="1",
    )
    service = CodexReplayService(
        repository=CodexReplayReferencesRepository(async_test_session),
        settings=settings,
    )

    for _ in range(2):
        assert (
            await service.persist_validated_references(
                candidates=candidates,
                gateway_key_id=key.id,
                usage_ledger_id=ledger.id,
                source_request_id=request_id,
                provider="openai",
                route_id=route.id,
                upstream_model=route.upstream_model,
                now=now,
            )
            == 2
        )
    rows = list(
        (
            await async_test_session.execute(
                select(CodexReplayReference).where(CodexReplayReference.gateway_key_id == key.id)
            )
        ).scalars()
    )
    assert len(rows) == 2
    serialized_safe_rows = " ".join(
        f"{row.item_kind} {row.item_id_hmac} {row.call_id_hmac or ''}" for row in rows
    )
    for forbidden in (
        "rs_private_raw_id",
        "ctc_private_raw_id",
        "call_private_raw_id",
    ):
        assert forbidden not in serialized_safe_rows

    authorization = await service.verify_owned_replay(
        candidates=candidates,
        gateway_key_id=key.id,
        now=now + timedelta(minutes=1),
    )
    service.verify_route_compatibility(
        authorization,
        provider="openai",
        route_id=route.id,
        upstream_model=route.upstream_model,
    )
    for gateway_key_id, checked_now in (
        (other_key.id, now + timedelta(minutes=1)),
        (key.id, now + timedelta(hours=24)),
    ):
        with pytest.raises(CodexReplayReferenceError) as exc_info:
            await service.verify_owned_replay(
                candidates=candidates,
                gateway_key_id=gateway_key_id,
                now=checked_now,
            )
        assert exc_info.value.error_code == "responses_codex_replay_reference_not_found"
