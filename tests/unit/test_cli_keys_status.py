from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

from typer.testing import CliRunner

from slaif_gateway.cli import keys as keys_cli
from slaif_gateway.cli.main import app
from slaif_gateway.schemas.keys import (
    ActivateGatewayKeyInput,
    GatewayKeyManagementResult,
    RevokeGatewayKeyInput,
    SuspendGatewayKeyInput,
)
from slaif_gateway.services.key_errors import GatewayKeyAlreadyRevokedError

runner = CliRunner()

GATEWAY_KEY_ID = uuid.UUID("44444444-4444-4444-8444-444444444444")
OWNER_ID = uuid.UUID("11111111-1111-4111-8111-111111111111")
COHORT_ID = uuid.UUID("22222222-2222-4222-8222-222222222222")
ADMIN_ID = uuid.UUID("33333333-3333-4333-8333-333333333333")


def _management_result(status: str = "suspended") -> GatewayKeyManagementResult:
    return GatewayKeyManagementResult(
        gateway_key_id=GATEWAY_KEY_ID,
        public_key_id="public",
        status=status,
        updated_at=datetime(2026, 1, 2, tzinfo=UTC),
        valid_from=datetime(2026, 1, 1, tzinfo=UTC),
        valid_until=datetime(2026, 2, 1, tzinfo=UTC),
        cost_limit_eur=Decimal("10"),
        token_limit_total=100,
        request_limit_total=10,
        cost_used_eur=Decimal("1"),
        tokens_used_total=2,
        requests_used_total=3,
        cost_reserved_eur=Decimal("0"),
        tokens_reserved_total=0,
        requests_reserved_total=0,
    )


def _gateway_key_row() -> SimpleNamespace:
    return SimpleNamespace(
        id=GATEWAY_KEY_ID,
        public_key_id="public",
        key_prefix="sk-slaif-",
        key_hint="sk-slaif-public",
        owner_id=OWNER_ID,
        cohort_id=COHORT_ID,
        status="active",
        valid_from=datetime(2026, 1, 1, tzinfo=UTC),
        valid_until=datetime(2026, 2, 1, tzinfo=UTC),
        cost_limit_eur=Decimal("10"),
        token_limit_total=100,
        request_limit_total=10,
        cost_used_eur=Decimal("1"),
        tokens_used_total=2,
        requests_used_total=3,
        cost_reserved_eur=Decimal("0"),
        tokens_reserved_total=0,
        requests_reserved_total=0,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        updated_at=datetime(2026, 1, 2, tzinfo=UTC),
        revoked_at=None,
        revoked_reason=None,
        token_hash="must-not-print",
        encrypted_payload="must-not-print",
        nonce="must-not-print",
    )


def test_keys_list_and_show_output_safe_metadata(monkeypatch) -> None:
    async def fake_list(**kwargs: object) -> list[SimpleNamespace]:
        assert kwargs["owner_id"] == OWNER_ID
        assert kwargs["cohort_id"] == COHORT_ID
        assert kwargs["status"] == "active"
        assert kwargs["limit"] == 5
        return [_gateway_key_row()]

    async def fake_show(gateway_key_id: uuid.UUID) -> SimpleNamespace:
        assert gateway_key_id == GATEWAY_KEY_ID
        return _gateway_key_row()

    monkeypatch.setattr(keys_cli, "_list_gateway_keys", fake_list)
    monkeypatch.setattr(keys_cli, "_show_gateway_key", fake_show)

    list_result = runner.invoke(
        app,
        [
            "keys",
            "list",
            "--owner-id",
            str(OWNER_ID),
            "--cohort-id",
            str(COHORT_ID),
            "--status",
            "active",
            "--limit",
            "5",
        ],
    )
    show_result = runner.invoke(app, ["keys", "show", str(GATEWAY_KEY_ID), "--json"])

    assert list_result.exit_code == 0
    assert show_result.exit_code == 0
    for output in (list_result.stdout, show_result.stdout):
        assert "public" in output
        assert "token_hash" not in output
        assert "must-not-print" not in output
        assert "plaintext" not in output
        assert "encrypted_payload" not in output
        assert "nonce" not in output
    assert json.loads(show_result.stdout)["id"] == str(GATEWAY_KEY_ID)


def test_status_commands_call_service_with_actor_and_reason(monkeypatch) -> None:
    seen: dict[str, object] = {}

    async def fake_suspend(payload: SuspendGatewayKeyInput) -> GatewayKeyManagementResult:
        seen["suspend"] = payload
        return _management_result("suspended")

    async def fake_activate(payload: ActivateGatewayKeyInput) -> GatewayKeyManagementResult:
        seen["activate"] = payload
        return _management_result("active")

    async def fake_revoke(payload: RevokeGatewayKeyInput) -> GatewayKeyManagementResult:
        seen["revoke"] = payload
        return _management_result("revoked")

    monkeypatch.setattr(keys_cli, "_suspend_gateway_key", fake_suspend)
    monkeypatch.setattr(keys_cli, "_activate_gateway_key", fake_activate)
    monkeypatch.setattr(keys_cli, "_revoke_gateway_key", fake_revoke)

    for command in ("suspend", "activate", "revoke"):
        result = runner.invoke(
            app,
            [
                "keys",
                command,
                str(GATEWAY_KEY_ID),
                "--actor-admin-id",
                str(ADMIN_ID),
                "--reason",
                f"{command} reason",
                "--json",
            ],
        )
        assert result.exit_code == 0
        assert "token_hash" not in result.stdout
        payload = seen[command]
        assert payload.gateway_key_id == GATEWAY_KEY_ID
        assert payload.actor_admin_id == ADMIN_ID
        assert payload.reason == f"{command} reason"


def test_status_service_error_returns_nonzero(monkeypatch) -> None:
    async def fake_suspend(payload: SuspendGatewayKeyInput) -> GatewayKeyManagementResult:
        raise GatewayKeyAlreadyRevokedError()

    monkeypatch.setattr(keys_cli, "_suspend_gateway_key", fake_suspend)

    result = runner.invoke(app, ["keys", "suspend", str(GATEWAY_KEY_ID)])

    assert result.exit_code == 1
    assert "already revoked" in result.stderr
    assert "token_hash" not in result.stderr
