from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

from typer.testing import CliRunner

from slaif_gateway.cli import keys as keys_cli
from slaif_gateway.cli.main import app
from slaif_gateway.schemas.keys import RotateGatewayKeyInput, RotatedGatewayKeyResult

runner = CliRunner()

OLD_GATEWAY_KEY_ID = uuid.UUID("44444444-4444-4444-8444-444444444444")
NEW_GATEWAY_KEY_ID = uuid.UUID("66666666-6666-4666-8666-666666666666")
ONE_TIME_SECRET_ID = uuid.UUID("55555555-5555-4555-8555-555555555555")
ADMIN_ID = uuid.UUID("33333333-3333-4333-8333-333333333333")
NEW_PLAINTEXT_KEY = "sk-slaif-new-public.once-only-rotation-secret"


def _rotation_result() -> RotatedGatewayKeyResult:
    return RotatedGatewayKeyResult(
        old_gateway_key_id=OLD_GATEWAY_KEY_ID,
        new_gateway_key_id=NEW_GATEWAY_KEY_ID,
        new_plaintext_key=NEW_PLAINTEXT_KEY,
        new_public_key_id="new-public",
        one_time_secret_id=ONE_TIME_SECRET_ID,
        old_status="revoked",
        new_status="active",
        valid_from=datetime(2026, 1, 1, tzinfo=UTC),
        valid_until=datetime(2026, 3, 1, tzinfo=UTC),
    )


def test_rotate_prints_replacement_plaintext_once(monkeypatch) -> None:
    seen: dict[str, RotateGatewayKeyInput] = {}

    async def fake_rotate(payload: RotateGatewayKeyInput) -> RotatedGatewayKeyResult:
        seen["payload"] = payload
        return _rotation_result()

    monkeypatch.setattr(keys_cli, "_rotate_gateway_key", fake_rotate)

    result = runner.invoke(
        app,
        [
            "keys",
            "rotate",
            str(OLD_GATEWAY_KEY_ID),
            "--actor-admin-id",
            str(ADMIN_ID),
            "--reason",
            "lost key",
            "--valid-until",
            "2026-03-01T00:00:00+00:00",
        ],
    )

    assert result.exit_code == 0
    assert result.stdout.count(NEW_PLAINTEXT_KEY) == 1
    assert "shown once" in result.stdout
    assert "token_hash" not in result.stdout
    assert "encrypted_payload" not in result.stdout
    assert "nonce" not in result.stdout

    payload = seen["payload"]
    assert payload.gateway_key_id == OLD_GATEWAY_KEY_ID
    assert payload.actor_admin_id == ADMIN_ID
    assert payload.reason == "lost key"
    assert payload.revoke_old_key is True
    assert payload.new_valid_until == datetime(2026, 3, 1, tzinfo=UTC)


def test_rotate_json_includes_new_plaintext_key_only_for_rotation(monkeypatch) -> None:
    async def fake_rotate(payload: RotateGatewayKeyInput) -> RotatedGatewayKeyResult:
        return _rotation_result()

    monkeypatch.setattr(keys_cli, "_rotate_gateway_key", fake_rotate)

    result = runner.invoke(app, ["keys", "rotate", str(OLD_GATEWAY_KEY_ID), "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["new_plaintext_key"] == NEW_PLAINTEXT_KEY
    assert result.stdout.count(NEW_PLAINTEXT_KEY) == 1
    assert "token_hash" not in result.stdout
    assert "encrypted_payload" not in result.stdout
    assert "nonce" not in result.stdout


def test_rotate_keep_old_active_maps_to_revoke_old_false(monkeypatch) -> None:
    seen: dict[str, RotateGatewayKeyInput] = {}

    async def fake_rotate(payload: RotateGatewayKeyInput) -> RotatedGatewayKeyResult:
        seen["payload"] = payload
        return _rotation_result()

    monkeypatch.setattr(keys_cli, "_rotate_gateway_key", fake_rotate)

    result = runner.invoke(
        app,
        ["keys", "rotate", str(OLD_GATEWAY_KEY_ID), "--keep-old-active", "--json"],
    )

    assert result.exit_code == 0
    assert seen["payload"].revoke_old_key is False
