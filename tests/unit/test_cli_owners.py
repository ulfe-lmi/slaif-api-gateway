from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from typer.testing import CliRunner

from slaif_gateway.cli import owners as owners_cli
from slaif_gateway.cli.main import app
from slaif_gateway.services.record_errors import DuplicateRecordError

runner = CliRunner()
OWNER_ID = uuid.UUID("33333333-3333-4333-8333-333333333333")
INSTITUTION_ID = uuid.UUID("11111111-1111-4111-8111-111111111111")


@dataclass
class FakeOwner:
    id: uuid.UUID = OWNER_ID
    name: str = "Ada"
    surname: str = "Lovelace"
    email: str = "ada@example.org"
    institution_id: uuid.UUID | None = INSTITUTION_ID
    notes: str | None = "safe notes"
    is_active: bool = True
    created_at: datetime = datetime(2026, 1, 1, tzinfo=UTC)
    updated_at: datetime = datetime(2026, 1, 2, tzinfo=UTC)


def test_owners_help_registers_commands() -> None:
    result = runner.invoke(app, ["owners", "--help"])

    assert result.exit_code == 0
    for command in ("create", "list", "show"):
        assert command in result.stdout


def test_owners_create_passes_expected_values(monkeypatch) -> None:
    seen: dict[str, object] = {}

    async def fake_create_owner(**kwargs: object) -> FakeOwner:
        seen.update(kwargs)
        return FakeOwner()

    monkeypatch.setattr(owners_cli, "_create_owner", fake_create_owner)

    result = runner.invoke(
        app,
        [
            "owners",
            "create",
            "--name",
            "Ada",
            "--surname",
            "Lovelace",
            "--email",
            "ADA@EXAMPLE.ORG",
            "--institution-id",
            str(INSTITUTION_ID),
            "--notes",
            "safe notes",
            "--json",
        ],
    )

    assert result.exit_code == 0
    assert seen["email"] == "ADA@EXAMPLE.ORG"
    assert seen["institution_id"] == str(INSTITUTION_ID)
    payload = json.loads(result.stdout)
    assert payload["id"] == str(OWNER_ID)
    assert "password" not in result.stdout
    assert "token_hash" not in result.stdout


def test_owners_list_and_show_output_safe(monkeypatch) -> None:
    async def fake_list_owners(
        *,
        institution_id: str | None,
        email: str | None,
        limit: int,
    ) -> list[FakeOwner]:
        assert institution_id == str(INSTITUTION_ID)
        assert email == "ada@example.org"
        assert limit == 5
        return [FakeOwner()]

    async def fake_show_owner(owner_id_or_email: str) -> FakeOwner:
        assert owner_id_or_email == "ada@example.org"
        return FakeOwner()

    monkeypatch.setattr(owners_cli, "_list_owners", fake_list_owners)
    monkeypatch.setattr(owners_cli, "_show_owner", fake_show_owner)

    list_result = runner.invoke(
        app,
        [
            "owners",
            "list",
            "--institution-id",
            str(INSTITUTION_ID),
            "--email",
            "ada@example.org",
            "--limit",
            "5",
            "--json",
        ],
    )
    show_result = runner.invoke(app, ["owners", "show", "ada@example.org", "--json"])

    assert list_result.exit_code == 0
    assert show_result.exit_code == 0
    assert json.loads(list_result.stdout)["owners"][0]["email"] == "ada@example.org"
    assert json.loads(show_result.stdout)["email"] == "ada@example.org"
    assert "password_hash" not in list_result.stdout
    assert "token_hash" not in show_result.stdout


def test_owners_duplicate_error_output_is_safe(monkeypatch) -> None:
    async def fake_create_owner(**kwargs: object) -> FakeOwner:
        raise DuplicateRecordError("Owner", "email")

    monkeypatch.setattr(owners_cli, "_create_owner", fake_create_owner)

    result = runner.invoke(
        app,
        [
            "owners",
            "create",
            "--name",
            "Ada",
            "--surname",
            "Lovelace",
            "--email",
            "ada@example.org",
            "--json",
        ],
    )

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["error"]["code"] == "duplicate_record"
    assert "password_hash" not in result.stdout
    assert "token_hash" not in result.stdout
