from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from typer.testing import CliRunner

from slaif_gateway.cli import keys as keys_cli
from slaif_gateway.cli.main import app
from slaif_gateway.schemas.keys import (
    GatewayKeyManagementResult,
    ResetGatewayKeyUsageInput,
    UpdateGatewayKeyValidityInput,
)

runner = CliRunner()

GATEWAY_KEY_ID = uuid.UUID("44444444-4444-4444-8444-444444444444")
ADMIN_ID = uuid.UUID("33333333-3333-4333-8333-333333333333")


def _management_result() -> GatewayKeyManagementResult:
    return GatewayKeyManagementResult(
        gateway_key_id=GATEWAY_KEY_ID,
        public_key_id="public",
        status="active",
        updated_at=datetime(2026, 1, 2, tzinfo=UTC),
        valid_from=datetime(2026, 1, 1, tzinfo=UTC),
        valid_until=datetime(2026, 2, 1, tzinfo=UTC),
        cost_limit_eur=Decimal("12.34"),
        token_limit_total=500,
        request_limit_total=None,
        cost_used_eur=Decimal("0"),
        tokens_used_total=0,
        requests_used_total=0,
        cost_reserved_eur=Decimal("0"),
        tokens_reserved_total=0,
        requests_reserved_total=0,
        last_quota_reset_at=datetime(2026, 1, 2, tzinfo=UTC),
        quota_reset_count=1,
    )


def test_extend_parses_validity_options(monkeypatch) -> None:
    seen: dict[str, UpdateGatewayKeyValidityInput] = {}

    async def fake_update(payload: UpdateGatewayKeyValidityInput) -> GatewayKeyManagementResult:
        seen["payload"] = payload
        return _management_result()

    monkeypatch.setattr(keys_cli, "_update_validity", fake_update)

    result = runner.invoke(
        app,
        [
            "keys",
            "extend",
            str(GATEWAY_KEY_ID),
            "--valid-until",
            "2026-03-01T00:00:00+00:00",
            "--actor-admin-id",
            str(ADMIN_ID),
            "--reason",
            "workshop extension",
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = seen["payload"]
    assert payload.gateway_key_id == GATEWAY_KEY_ID
    assert payload.valid_until == datetime(2026, 3, 1, tzinfo=UTC)
    assert payload.actor_admin_id == ADMIN_ID
    assert payload.reason == "workshop extension"
    assert "token_hash" not in result.stdout


def test_set_limits_parses_decimal_integers_and_clear_flags(monkeypatch) -> None:
    seen: dict[str, object] = {}

    async def fake_update_limits(**kwargs: object) -> GatewayKeyManagementResult:
        seen.update(kwargs)
        return _management_result()

    monkeypatch.setattr(keys_cli, "_update_limits", fake_update_limits)

    result = runner.invoke(
        app,
        [
            "keys",
            "set-limits",
            str(GATEWAY_KEY_ID),
            "--cost-limit-eur",
            "12.34",
            "--token-limit-total",
            "500",
            "--clear-request-limit",
            "--actor-admin-id",
            str(ADMIN_ID),
            "--reason",
            "updated limits",
            "--json",
        ],
    )

    assert result.exit_code == 0
    assert seen["gateway_key_id"] == GATEWAY_KEY_ID
    assert seen["cost_limit_eur"] == Decimal("12.34")
    assert seen["token_limit_total"] == 500
    assert seen["request_limit_total"] is None
    assert seen["clear_request_limit"] is True
    assert seen["actor_admin_id"] == ADMIN_ID
    assert seen["reason"] == "updated limits"
    assert "token_hash" not in result.stdout


def test_set_limits_rejects_negative_values() -> None:
    result = runner.invoke(
        app,
        ["keys", "set-limits", str(GATEWAY_KEY_ID), "--token-limit-total", "-1"],
    )

    assert result.exit_code != 0


def test_reset_usage_warns_for_reserved_admin_repair(monkeypatch) -> None:
    seen: dict[str, ResetGatewayKeyUsageInput] = {}

    async def fake_reset(payload: ResetGatewayKeyUsageInput) -> GatewayKeyManagementResult:
        seen["payload"] = payload
        return _management_result()

    monkeypatch.setattr(keys_cli, "_reset_usage", fake_reset)

    result = runner.invoke(
        app,
        [
            "keys",
            "reset-usage",
            str(GATEWAY_KEY_ID),
            "--reset-reserved",
            "--actor-admin-id",
            str(ADMIN_ID),
            "--reason",
            "repair",
        ],
    )

    assert result.exit_code == 0
    assert "admin repair action" in result.stdout
    payload = seen["payload"]
    assert payload.reset_used_counters is True
    assert payload.reset_reserved_counters is True
    assert payload.actor_admin_id == ADMIN_ID
    assert payload.reason == "repair"
    assert "usage_ledger" not in result.stdout
    assert "token_hash" not in result.stdout
