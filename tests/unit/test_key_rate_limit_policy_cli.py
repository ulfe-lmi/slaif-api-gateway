from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal

from typer.testing import CliRunner

from slaif_gateway.cli import keys as keys_cli
from slaif_gateway.cli.main import app
from slaif_gateway.schemas.keys import (
    CreateGatewayKeyInput,
    CreatedGatewayKey,
    GatewayKeyManagementResult,
)

runner = CliRunner()

OWNER_ID = uuid.UUID("11111111-1111-4111-8111-111111111111")
GATEWAY_KEY_ID = uuid.UUID("44444444-4444-4444-8444-444444444444")
ADMIN_ID = uuid.UUID("33333333-3333-4333-8333-333333333333")
ONE_TIME_SECRET_ID = uuid.UUID("55555555-5555-4555-8555-555555555555")
PLAINTEXT_KEY = "sk-slaif-public.once-only-secret"


def _created_result() -> CreatedGatewayKey:
    return CreatedGatewayKey(
        gateway_key_id=GATEWAY_KEY_ID,
        owner_id=OWNER_ID,
        public_key_id="public",
        display_prefix="sk-slaif-public",
        plaintext_key=PLAINTEXT_KEY,
        one_time_secret_id=ONE_TIME_SECRET_ID,
        valid_from=datetime(2026, 1, 1, tzinfo=UTC),
        valid_until=datetime(2026, 2, 1, tzinfo=UTC),
        rate_limit_policy={
            "requests_per_minute": 60,
            "tokens_per_minute": 100_000,
            "max_concurrent_requests": 3,
            "window_seconds": 60,
        },
    )


def _management_result(policy: dict[str, int] | None) -> GatewayKeyManagementResult:
    return GatewayKeyManagementResult(
        gateway_key_id=GATEWAY_KEY_ID,
        public_key_id="public",
        status="active",
        updated_at=datetime(2026, 1, 2, tzinfo=UTC),
        valid_from=datetime(2026, 1, 1, tzinfo=UTC),
        valid_until=datetime(2026, 2, 1, tzinfo=UTC),
        cost_limit_eur=Decimal("12.34"),
        token_limit_total=500,
        request_limit_total=20,
        cost_used_eur=Decimal("0"),
        tokens_used_total=0,
        requests_used_total=0,
        cost_reserved_eur=Decimal("0"),
        tokens_reserved_total=0,
        requests_reserved_total=0,
        rate_limit_policy=policy,
    )


def test_keys_create_accepts_rate_limit_flags(monkeypatch) -> None:
    seen: dict[str, CreateGatewayKeyInput] = {}

    async def fake_create(payload: CreateGatewayKeyInput) -> CreatedGatewayKey:
        seen["payload"] = payload
        return _created_result()

    monkeypatch.setattr(keys_cli, "_create_gateway_key", fake_create)

    result = runner.invoke(
        app,
        [
            "keys",
            "create",
            "--owner-id",
            str(OWNER_ID),
            "--valid-until",
            "2026-02-01T00:00:00+00:00",
            "--rate-limit-requests-per-minute",
            "60",
            "--rate-limit-tokens-per-minute",
            "100000",
            "--rate-limit-concurrent-requests",
            "3",
            "--rate-limit-window-seconds",
            "60",
            "--json",
        ],
    )

    assert result.exit_code == 0
    assert seen["payload"].rate_limit_policy == {
        "requests_per_minute": 60,
        "tokens_per_minute": 100_000,
        "max_concurrent_requests": 3,
        "window_seconds": 60,
    }
    payload = json.loads(result.stdout)
    assert payload["rate_limit_policy"]["requests_per_minute"] == 60
    assert "token_hash" not in result.stdout
    assert "encrypted_payload" not in result.stdout
    assert "nonce" not in result.stdout


def test_keys_create_without_rate_limit_flags_preserves_current_behavior(monkeypatch) -> None:
    seen: dict[str, CreateGatewayKeyInput] = {}

    async def fake_create(payload: CreateGatewayKeyInput) -> CreatedGatewayKey:
        seen["payload"] = payload
        return _created_result()

    monkeypatch.setattr(keys_cli, "_create_gateway_key", fake_create)

    result = runner.invoke(
        app,
        [
            "keys",
            "create",
            "--owner-id",
            str(OWNER_ID),
            "--valid-until",
            "2026-02-01T00:00:00+00:00",
        ],
    )

    assert result.exit_code == 0
    assert seen["payload"].rate_limit_policy is None


def test_keys_create_rejects_invalid_rate_limit_values() -> None:
    result = runner.invoke(
        app,
        [
            "keys",
            "create",
            "--owner-id",
            str(OWNER_ID),
            "--valid-until",
            "2026-02-01T00:00:00+00:00",
            "--rate-limit-requests-per-minute",
            "0",
        ],
    )

    assert result.exit_code != 0


def test_keys_set_rate_limits_updates_policy(monkeypatch) -> None:
    seen: dict[str, object] = {}

    async def fake_update_rate_limits(**kwargs: object) -> GatewayKeyManagementResult:
        seen.update(kwargs)
        return _management_result(
            {
                "requests_per_minute": 60,
                "tokens_per_minute": 100_000,
                "max_concurrent_requests": 3,
                "window_seconds": 60,
            }
        )

    monkeypatch.setattr(keys_cli, "_update_rate_limits", fake_update_rate_limits)

    result = runner.invoke(
        app,
        [
            "keys",
            "set-rate-limits",
            str(GATEWAY_KEY_ID),
            "--requests-per-minute",
            "60",
            "--tokens-per-minute",
            "100000",
            "--concurrent-requests",
            "3",
            "--window-seconds",
            "60",
            "--actor-admin-id",
            str(ADMIN_ID),
            "--reason",
            "operator throttle",
            "--json",
        ],
    )

    assert result.exit_code == 0
    assert seen["gateway_key_id"] == GATEWAY_KEY_ID
    assert seen["requests_per_minute"] == 60
    assert seen["tokens_per_minute"] == 100_000
    assert seen["concurrent_requests"] == 3
    assert seen["window_seconds"] == 60
    assert seen["actor_admin_id"] == ADMIN_ID
    assert seen["reason"] == "operator throttle"
    payload = json.loads(result.stdout)
    assert payload["rate_limit_policy"]["max_concurrent_requests"] == 3
    assert "token_hash" not in result.stdout


def test_keys_set_rate_limits_clear_options(monkeypatch) -> None:
    seen: dict[str, object] = {}

    async def fake_update_rate_limits(**kwargs: object) -> GatewayKeyManagementResult:
        seen.update(kwargs)
        return _management_result(None)

    monkeypatch.setattr(keys_cli, "_update_rate_limits", fake_update_rate_limits)

    result = runner.invoke(
        app,
        [
            "keys",
            "set-rate-limits",
            str(GATEWAY_KEY_ID),
            "--clear-all",
            "--json",
        ],
    )

    assert result.exit_code == 0
    assert seen["clear_all"] is True
    payload = json.loads(result.stdout)
    assert payload["rate_limit_policy"] is None


def test_keys_set_rate_limits_rejects_invalid_or_conflicting_values() -> None:
    invalid = runner.invoke(
        app,
        ["keys", "set-rate-limits", str(GATEWAY_KEY_ID), "--tokens-per-minute", "-1"],
    )
    assert invalid.exit_code != 0

    conflict = runner.invoke(
        app,
        [
            "keys",
            "set-rate-limits",
            str(GATEWAY_KEY_ID),
            "--requests-per-minute",
            "10",
            "--clear-requests",
        ],
    )
    assert conflict.exit_code != 0
