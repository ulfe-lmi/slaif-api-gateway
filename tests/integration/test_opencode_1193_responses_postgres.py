"""PostgreSQL side-effect proof for the OpenCode 1.19.3 Responses client module.

Every case below is rejected by the pinned client module (or by module
resolution) before any database write or provider call. The module is
streaming-only: ``stream`` must be exactly ``true`` in the captured wire
shape, so no non-streaming settlement case exists for this profile. The
streaming tool-loop PostgreSQL cases remain pending the root streaming
ruling and are deliberately not written here.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from slaif_gateway.api.errors import OpenAICompatibleError
from slaif_gateway.db.models import QuotaReservation, UsageLedger
from slaif_gateway.modules.clients.opencode_1193_responses import (
    OPENCODE_1193_RESPONSES_CLIENT_MODULE_ID,
    OPENCODE_1193_RESPONSES_CLIENT_MODULE_VERSION,
    OPENCODE_1193_RESPONSES_PROFILE_FIXTURE_SHA256,
)
from slaif_gateway.services.responses_gateway import handle_response_create

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
