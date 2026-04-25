from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from typer.testing import CliRunner

from slaif_gateway.cli import admin as admin_cli
from slaif_gateway.cli.main import app
from slaif_gateway.utils.passwords import verify_admin_password

runner = CliRunner()
ADMIN_ID = uuid.UUID("11111111-1111-4111-8111-111111111111")
PLAINTEXT_PASSWORD = "admin password 123"


@dataclass
class FakeAdminUser:
    id: uuid.UUID = ADMIN_ID
    email: str = "admin@example.org"
    display_name: str = "Test Admin"
    role: str = "admin"
    is_active: bool = True
    created_at: datetime = datetime(2026, 1, 1, tzinfo=UTC)
    updated_at: datetime = datetime(2026, 1, 2, tzinfo=UTC)
    last_login_at: datetime | None = None


def test_admin_help_registers_commands() -> None:
    result = runner.invoke(app, ["admin", "--help"])

    assert result.exit_code == 0
    for command in ("create", "reset-password", "list"):
        assert command in result.stdout


def test_admin_create_hashes_password_and_does_not_print_secret(monkeypatch) -> None:
    seen: dict[str, object] = {}

    async def fake_create_admin(**kwargs: object) -> FakeAdminUser:
        seen.update(kwargs)
        return FakeAdminUser(role="superadmin")

    monkeypatch.setattr(admin_cli, "_create_admin", fake_create_admin)

    result = runner.invoke(
        app,
        [
            "admin",
            "create",
            "--email",
            "Admin@Example.ORG",
            "--display-name",
            "Test Admin",
            "--password",
            PLAINTEXT_PASSWORD,
            "--superadmin",
            "--json",
        ],
    )

    assert result.exit_code == 0
    password_hash = seen["password_hash"]
    assert isinstance(password_hash, str)
    assert password_hash != PLAINTEXT_PASSWORD
    assert password_hash.startswith("$argon2id$")
    assert verify_admin_password(PLAINTEXT_PASSWORD, password_hash)
    assert PLAINTEXT_PASSWORD not in result.stdout
    assert password_hash not in result.stdout
    assert "password_hash" not in result.stdout

    payload = json.loads(result.stdout)
    assert payload["email"] == "admin@example.org"
    assert payload["is_superadmin"] is True


def test_admin_create_password_stdin(monkeypatch) -> None:
    seen: dict[str, object] = {}

    async def fake_create_admin(**kwargs: object) -> FakeAdminUser:
        seen.update(kwargs)
        return FakeAdminUser()

    monkeypatch.setattr(admin_cli, "_create_admin", fake_create_admin)

    result = runner.invoke(
        app,
        [
            "admin",
            "create",
            "--email",
            "admin@example.org",
            "--display-name",
            "Test Admin",
            "--password-stdin",
        ],
        input=f"{PLAINTEXT_PASSWORD}\n",
    )

    assert result.exit_code == 0
    assert verify_admin_password(PLAINTEXT_PASSWORD, seen["password_hash"])
    assert PLAINTEXT_PASSWORD not in result.stdout
    assert seen["password_hash"] not in result.stdout


def test_admin_reset_password_hashes_and_does_not_print_secret(monkeypatch) -> None:
    seen: dict[str, object] = {}

    async def fake_reset_password(admin_user_id_or_email: str, password_hash: str) -> FakeAdminUser:
        seen["identifier"] = admin_user_id_or_email
        seen["password_hash"] = password_hash
        return FakeAdminUser()

    monkeypatch.setattr(admin_cli, "_reset_password", fake_reset_password)

    result = runner.invoke(
        app,
        [
            "admin",
            "reset-password",
            "admin@example.org",
            "--password",
            PLAINTEXT_PASSWORD,
            "--json",
        ],
    )

    assert result.exit_code == 0
    assert seen["identifier"] == "admin@example.org"
    assert verify_admin_password(PLAINTEXT_PASSWORD, seen["password_hash"])
    assert PLAINTEXT_PASSWORD not in result.stdout
    assert seen["password_hash"] not in result.stdout
    assert "password_hash" not in result.stdout

    payload = json.loads(result.stdout)
    assert payload["password_changed"] is True


def test_admin_list_never_prints_password_hash(monkeypatch) -> None:
    async def fake_list_admins(*, limit: int) -> list[FakeAdminUser]:
        assert limit == 10
        return [FakeAdminUser()]

    monkeypatch.setattr(admin_cli, "_list_admins", fake_list_admins)

    result = runner.invoke(app, ["admin", "list", "--limit", "10", "--json"])

    assert result.exit_code == 0
    assert "password_hash" not in result.stdout
    payload = json.loads(result.stdout)
    assert payload["admin_users"][0]["email"] == "admin@example.org"
