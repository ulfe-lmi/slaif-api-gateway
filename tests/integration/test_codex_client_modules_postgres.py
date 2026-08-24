"""PostgreSQL side-effect proof for versioned Responses client selection."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from slaif_gateway.api.errors import OpenAICompatibleError
from slaif_gateway.db.models import QuotaReservation, UsageLedger
from slaif_gateway.modules.clients.codex_0149 import (
    CODEX_0149_CLIENT_MODULE_ID,
    CODEX_0149_FIXTURE_SHA256,
)
from slaif_gateway.services.responses_gateway import handle_response_create


@pytest.mark.asyncio
async def test_codex_0149_pair_denial_has_no_postgres_reservation_or_ledger_side_effect(
    async_test_session: AsyncSession,
) -> None:
    before_reservations = await async_test_session.scalar(
        select(func.count()).select_from(QuotaReservation)
    )
    before_ledger = await async_test_session.scalar(
        select(func.count()).select_from(UsageLedger)
    )
    payload = SimpleNamespace(
        model_dump=lambda **_: {
            "model": f"codex-0149-{uuid.uuid4().hex}",
            "input": "synthetic",
            "tools": [{"type": "web_search"}],
            "tool_choice": "auto",
        },
        model_fields_set=set(),
    )
    key = SimpleNamespace(
        responses_policy={
            "client_module": {
                "id": CODEX_0149_CLIENT_MODULE_ID,
                "version": "1",
                "fixture_sha256": CODEX_0149_FIXTURE_SHA256,
            }
        }
    )

    with pytest.raises(OpenAICompatibleError) as exc_info:
        await handle_response_create(
            payload=payload,
            authenticated_key=key,
            settings=SimpleNamespace(),
        )

    assert exc_info.value.code == "incompatible_client_server_pair"
    after_reservations = await async_test_session.scalar(
        select(func.count()).select_from(QuotaReservation)
    )
    after_ledger = await async_test_session.scalar(
        select(func.count()).select_from(UsageLedger)
    )
    assert after_reservations == before_reservations
    assert after_ledger == before_ledger
