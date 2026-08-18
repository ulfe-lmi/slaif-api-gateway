from __future__ import annotations

import uuid

import pytest

from slaif_gateway.schemas.keys import (
    UpdateGatewayKeyChatStreamingLiveBurnInput,
    UpdateGatewayKeyExternalToolPolicyInput,
    UpdateGatewayKeyPolicyInput,
)
from slaif_gateway.services.key_errors import InvalidGatewayKeyPolicyError

from tests.unit.key_management_fakes import FakeGatewayKeyRow, make_key_service


def _fenced_policy() -> dict[str, object]:
    return {
        "version": 1,
        "mode": "external_tool_fenced",
        "allowed_capabilities": ["provider_web_search"],
        "allowed_destination_ids": [],
        "max_provider_tool_calls_per_request": 2,
        "single_request_overrun_acknowledged": True,
    }


@pytest.mark.asyncio
async def test_update_gateway_key_policy_updates_only_policy_and_audits() -> None:
    row = FakeGatewayKeyRow(
        allowed_models=["old-model"],
        allowed_endpoints=["/v1/models"],
        allow_all_models=False,
        allow_all_endpoints=False,
    )
    service, keys_repo, _, audit_repo, _ = make_key_service(row)
    actor_id = uuid.uuid4()

    result = await service.update_gateway_key_policy(
        UpdateGatewayKeyPolicyInput(
            gateway_key_id=row.id,
            allowed_models=["gpt-5.2", "gpt-5.2", "gpt-5.1"],
            allowed_endpoints=["/v1/models", "/v1/chat/completions"],
            actor_admin_id=actor_id,
            reason="fix request policy",
        )
    )

    assert keys_repo.policy_calls == [
        {
            "gateway_key_id": row.id,
            "allowed_models": ["gpt-5.2", "gpt-5.1"],
            "allowed_endpoints": ["/v1/models", "/v1/chat/completions"],
            "allow_all_models": False,
            "allow_all_endpoints": False,
        }
    ]
    assert row.allowed_models == ["gpt-5.2", "gpt-5.1"]
    assert row.allowed_endpoints == ["/v1/models", "/v1/chat/completions"]
    assert row.cost_limit_eur is not None
    assert row.token_hash == "a" * 64
    assert result.allowed_models == ["gpt-5.2", "gpt-5.1"]

    audit = audit_repo.calls[-1]
    assert audit["action"] == "update_key_policy"
    assert audit["entity_id"] == row.id
    assert audit["admin_user_id"] == actor_id
    assert audit["note"] == "fix request policy"
    assert audit["old_values"]["allowed_models"] == ["old-model"]
    assert audit["new_values"]["allowed_models"] == ["gpt-5.2", "gpt-5.1"]
    assert "token_hash" not in str(audit)


@pytest.mark.asyncio
async def test_update_gateway_key_policy_requires_reason() -> None:
    row = FakeGatewayKeyRow()
    service, keys_repo, _, audit_repo, _ = make_key_service(row)

    with pytest.raises(InvalidGatewayKeyPolicyError, match="audit reason"):
        await service.update_gateway_key_policy(
            UpdateGatewayKeyPolicyInput(
                gateway_key_id=row.id,
                allowed_models=["gpt-5.2"],
                allowed_endpoints=["/v1/chat/completions"],
                reason="",
            )
        )

    assert keys_repo.policy_calls == []
    assert audit_repo.calls == []


@pytest.mark.asyncio
async def test_update_gateway_key_policy_can_update_allowed_providers_without_mutating_quotas() -> (
    None
):
    row = FakeGatewayKeyRow(
        metadata_json={
            "allowed_providers": ["openai"],
            "rate_limit_policy": {"window_seconds": 30},
        },
        cost_limit_eur=None,
    )
    old_tokens_used = row.tokens_used_total
    service, keys_repo, _, audit_repo, _ = make_key_service(row)

    result = await service.update_gateway_key_policy(
        UpdateGatewayKeyPolicyInput(
            gateway_key_id=row.id,
            allowed_providers=["openrouter"],
            update_allowed_providers=True,
            allowed_models=["gpt-5.2"],
            allowed_endpoints=["/v1/chat/completions"],
            reason="switch provider allow-list",
        )
    )

    assert keys_repo.policy_calls == [
        {
            "gateway_key_id": row.id,
            "allowed_models": ["gpt-5.2"],
            "allowed_endpoints": ["/v1/chat/completions"],
            "allow_all_models": False,
            "allow_all_endpoints": False,
        }
    ]
    assert keys_repo.metadata_calls == [
        {
            "gateway_key_id": row.id,
            "metadata_json": {
                "allowed_providers": ["openrouter"],
                "rate_limit_policy": {"window_seconds": 30},
            },
        }
    ]
    assert row.tokens_used_total == old_tokens_used
    assert row.metadata_json == {
        "allowed_providers": ["openrouter"],
        "rate_limit_policy": {"window_seconds": 30},
    }
    assert result.allowed_models == ["gpt-5.2"]

    audit = audit_repo.calls[-1]
    assert audit["old_values"]["allowed_providers"] == ["openai"]
    assert audit["new_values"]["allowed_providers"] == ["openrouter"]
    assert "token_hash" not in str(audit)


@pytest.mark.asyncio
async def test_update_chat_streaming_live_burn_policy_updates_metadata_only_and_audits() -> None:
    row = FakeGatewayKeyRow(
        metadata_json={
            "allowed_providers": ["openai"],
            "chat_streaming_live_burn": {
                "version": 1,
                "enabled": True,
                "cost_margin_eur": "0.000000000",
                "token_margin": 0,
            },
        }
    )
    old_cost_limit = row.cost_limit_eur
    old_tokens_used = row.tokens_used_total
    service, keys_repo, _, audit_repo, _ = make_key_service(row)
    actor_id = uuid.uuid4()

    result = await service.update_gateway_key_chat_streaming_live_burn(
        UpdateGatewayKeyChatStreamingLiveBurnInput(
            gateway_key_id=row.id,
            chat_streaming_live_burn_policy={
                "version": 1,
                "enabled": False,
                "cost_margin_eur": "-0.250000000",
                "token_margin": -250,
            },
            actor_admin_id=actor_id,
            reason="adjust stream brake",
        )
    )

    assert keys_repo.metadata_calls == [
        {
            "gateway_key_id": row.id,
            "metadata_json": {
                "allowed_providers": ["openai"],
                "chat_streaming_live_burn": {
                    "version": 1,
                    "enabled": False,
                    "cost_margin_eur": "-0.250000000",
                    "token_margin": -250,
                },
            },
        }
    ]
    assert row.cost_limit_eur == old_cost_limit
    assert row.tokens_used_total == old_tokens_used
    assert result.chat_streaming_live_burn_policy == {
        "version": 1,
        "enabled": False,
        "cost_margin_eur": "-0.250000000",
        "token_margin": -250,
    }

    audit = audit_repo.calls[-1]
    assert audit["action"] == "update_chat_streaming_live_burn_policy"
    assert audit["admin_user_id"] == actor_id
    assert audit["old_values"]["chat_streaming_live_burn_policy"]["enabled"] is True
    assert audit["new_values"]["chat_streaming_live_burn_policy"]["enabled"] is False
    assert "token_hash" not in str(audit)


@pytest.mark.asyncio
async def test_update_chat_streaming_live_burn_policy_requires_reason() -> None:
    row = FakeGatewayKeyRow()
    service, keys_repo, _, audit_repo, _ = make_key_service(row)

    with pytest.raises(InvalidGatewayKeyPolicyError, match="audit reason"):
        await service.update_gateway_key_chat_streaming_live_burn(
            UpdateGatewayKeyChatStreamingLiveBurnInput(
                gateway_key_id=row.id,
                chat_streaming_live_burn_policy={
                    "version": 1,
                    "enabled": True,
                    "cost_margin_eur": "0",
                    "token_margin": 0,
                },
                reason="",
            )
        )

    assert keys_repo.metadata_calls == []
    assert audit_repo.calls == []


@pytest.mark.asyncio
async def test_update_external_tool_policy_is_canonical_preserves_metadata_and_audits_once() -> (
    None
):
    row = FakeGatewayKeyRow(metadata_json={"allowed_providers": ["openai"]})
    service, keys_repo, _, audit_repo, _ = make_key_service(row)

    result = await service.update_gateway_key_external_tool_policy(
        UpdateGatewayKeyExternalToolPolicyInput(
            gateway_key_id=row.id,
            external_tool_policy=_fenced_policy(),
            confirm_external_tool_fenced=True,
            actor_admin_id=uuid.uuid4(),
            reason="reviewed future search fence",
        )
    )

    assert keys_repo.metadata_calls[0]["metadata_json"]["allowed_providers"] == ["openai"]
    assert keys_repo.metadata_calls[0]["metadata_json"]["external_tool_policy"] == _fenced_policy()
    assert result.external_tool_policy == _fenced_policy()
    assert [row["action"] for row in audit_repo.calls] == ["update_external_tool_policy"]
    assert "provider_web_search" in str(audit_repo.calls[0]["new_values"])
    assert "http" not in str(audit_repo.calls[0]["new_values"])


@pytest.mark.asyncio
async def test_update_external_tool_policy_rejects_without_reason_or_confirmation_before_mutation() -> (
    None
):
    row = FakeGatewayKeyRow()
    service, keys_repo, _, audit_repo, _ = make_key_service(row)

    for reason, confirmed in (("", True), ("reviewed", False)):
        with pytest.raises(InvalidGatewayKeyPolicyError):
            await service.update_gateway_key_external_tool_policy(
                UpdateGatewayKeyExternalToolPolicyInput(
                    gateway_key_id=row.id,
                    external_tool_policy=_fenced_policy(),
                    confirm_external_tool_fenced=confirmed,
                    reason=reason,
                )
            )

    assert keys_repo.metadata_calls == []
    assert audit_repo.calls == []
