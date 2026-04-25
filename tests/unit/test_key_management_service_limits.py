from __future__ import annotations

import json
from decimal import Decimal

import pytest

from slaif_gateway.schemas.keys import ResetGatewayKeyUsageInput, UpdateGatewayKeyLimitsInput
from slaif_gateway.services.key_errors import (
    InvalidGatewayKeyLimitsError,
    InvalidGatewayKeyUsageResetError,
)
from tests.unit.key_management_fakes import FakeGatewayKeyRow, make_key_service


pytestmark = pytest.mark.asyncio


async def test_cost_token_and_request_limits_can_be_updated() -> None:
    row = FakeGatewayKeyRow(
        cost_used_eur=Decimal("10.000000000"),
        cost_reserved_eur=Decimal("2.000000000"),
        tokens_used_total=500,
        tokens_reserved_total=100,
        requests_used_total=10,
        requests_reserved_total=2,
    )
    service, keys_repo, _, audit_repo, _ = make_key_service(row)

    result = await service.update_gateway_key_limits(
        UpdateGatewayKeyLimitsInput(
            gateway_key_id=row.id,
            cost_limit_eur=Decimal("1.000000000"),
            token_limit_total=100,
            request_limit_total=1,
            reason="lower for next run",
        )
    )

    assert result.cost_limit_eur == Decimal("1.000000000")
    assert result.token_limit_total == 100
    assert result.request_limit_total == 1
    assert keys_repo.limit_calls[0]["cost_limit_eur"] == Decimal("1.000000000")
    assert audit_repo.calls[0]["action"] == "update_key_limits"
    assert audit_repo.calls[0]["old_values"]["cost_limit_eur"] == "25.000000000"
    assert audit_repo.calls[0]["new_values"]["cost_limit_eur"] == "1.000000000"


async def test_negative_or_zero_limits_fail() -> None:
    row = FakeGatewayKeyRow()
    service, _, _, _, _ = make_key_service(row)

    with pytest.raises(InvalidGatewayKeyLimitsError):
        await service.update_gateway_key_limits(
            UpdateGatewayKeyLimitsInput(gateway_key_id=row.id, cost_limit_eur=Decimal("0"))
        )
    with pytest.raises(InvalidGatewayKeyLimitsError):
        await service.update_gateway_key_limits(
            UpdateGatewayKeyLimitsInput(gateway_key_id=row.id, token_limit_total=-1)
        )
    with pytest.raises(InvalidGatewayKeyLimitsError):
        await service.update_gateway_key_limits(
            UpdateGatewayKeyLimitsInput(gateway_key_id=row.id, request_limit_total=0)
        )


async def test_limits_may_be_cleared_to_none() -> None:
    row = FakeGatewayKeyRow()
    service, _, _, _, _ = make_key_service(row)

    result = await service.update_gateway_key_limits(
        UpdateGatewayKeyLimitsInput(
            gateway_key_id=row.id,
            cost_limit_eur=None,
            token_limit_total=None,
            request_limit_total=None,
        )
    )

    assert result.cost_limit_eur is None
    assert result.token_limit_total is None
    assert result.request_limit_total is None


async def test_reset_usage_resets_used_counters_but_not_reserved_by_default() -> None:
    row = FakeGatewayKeyRow(
        cost_used_eur=Decimal("3.000000000"),
        tokens_used_total=30,
        requests_used_total=3,
        cost_reserved_eur=Decimal("4.000000000"),
        tokens_reserved_total=40,
        requests_reserved_total=4,
    )
    service, _, _, audit_repo, _ = make_key_service(row)

    result = await service.reset_gateway_key_usage(ResetGatewayKeyUsageInput(gateway_key_id=row.id))

    assert result.cost_used_eur == Decimal("0")
    assert result.tokens_used_total == 0
    assert result.requests_used_total == 0
    assert result.cost_reserved_eur == Decimal("4.000000000")
    assert result.tokens_reserved_total == 40
    assert result.requests_reserved_total == 4
    assert result.last_quota_reset_at is not None
    assert result.quota_reset_count == 1
    assert audit_repo.calls[0]["action"] == "reset_quota"
    assert audit_repo.calls[0]["new_values"]["reset_reserved_counters"] is False


async def test_reset_usage_can_reset_reserved_counters_as_explicit_admin_repair() -> None:
    row = FakeGatewayKeyRow(
        cost_reserved_eur=Decimal("4.000000000"),
        tokens_reserved_total=40,
        requests_reserved_total=4,
    )
    service, _, _, audit_repo, _ = make_key_service(row)

    result = await service.reset_gateway_key_usage(
        ResetGatewayKeyUsageInput(
            gateway_key_id=row.id,
            reset_used_counters=True,
            reset_reserved_counters=True,
            reason="repair stale reservation",
        )
    )

    assert result.cost_reserved_eur == Decimal("0")
    assert result.tokens_reserved_total == 0
    assert result.requests_reserved_total == 0
    assert audit_repo.calls[0]["new_values"]["reset_reserved_counters"] is True


async def test_reset_usage_rejects_noop_and_does_not_reference_ledger_deletion() -> None:
    row = FakeGatewayKeyRow()
    service, _, _, audit_repo, _ = make_key_service(row)

    with pytest.raises(InvalidGatewayKeyUsageResetError):
        await service.reset_gateway_key_usage(
            ResetGatewayKeyUsageInput(
                gateway_key_id=row.id,
                reset_used_counters=False,
                reset_reserved_counters=False,
            )
        )

    assert audit_repo.calls == []


async def test_limit_and_reset_audit_logs_contain_safe_values_only() -> None:
    row = FakeGatewayKeyRow(token_hash="f" * 64)
    service, _, _, audit_repo, _ = make_key_service(row)

    await service.update_gateway_key_limits(
        UpdateGatewayKeyLimitsInput(gateway_key_id=row.id, cost_limit_eur=Decimal("9"))
    )
    await service.reset_gateway_key_usage(ResetGatewayKeyUsageInput(gateway_key_id=row.id))

    serialized = json.dumps(audit_repo.calls, default=str)
    assert row.token_hash not in serialized
    assert "encrypted_payload" not in serialized
    assert "nonce" not in serialized
    assert "sk-slaif-" not in serialized
