from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from typer.testing import CliRunner

from slaif_gateway.cli import institutions as institutions_cli
from slaif_gateway.cli.main import app

runner = CliRunner()
INSTITUTION_ID = uuid.UUID("11111111-1111-4111-8111-111111111111")


@dataclass
class FakeInstitution:
    id: uuid.UUID = INSTITUTION_ID
    name: str = "SLAIF Test Institute"
    country: str | None = "SI"
    notes: str | None = "safe notes"
    created_at: datetime = datetime(2026, 1, 1, tzinfo=UTC)
    updated_at: datetime = datetime(2026, 1, 2, tzinfo=UTC)


def test_institutions_help_registers_commands() -> None:
    result = runner.invoke(app, ["institutions", "--help"])

    assert result.exit_code == 0
    for command in ("create", "list", "show"):
        assert command in result.stdout


def test_institutions_create_passes_expected_values(monkeypatch) -> None:
    seen: dict[str, object] = {}

    async def fake_create_institution(**kwargs: object) -> FakeInstitution:
        seen.update(kwargs)
        return FakeInstitution()

    monkeypatch.setattr(institutions_cli, "_create_institution", fake_create_institution)

    result = runner.invoke(
        app,
        [
            "institutions",
            "create",
            "--name",
            "SLAIF Test Institute",
            "--country",
            "SI",
            "--notes",
            "safe notes",
            "--json",
        ],
    )

    assert result.exit_code == 0
    assert seen == {"name": "SLAIF Test Institute", "country": "SI", "notes": "safe notes"}
    payload = json.loads(result.stdout)
    assert payload["id"] == str(INSTITUTION_ID)
    assert "password" not in result.stdout
    assert "token_hash" not in result.stdout


def test_institutions_list_and_show_output_safe(monkeypatch) -> None:
    async def fake_list_institutions(*, limit: int) -> list[FakeInstitution]:
        assert limit == 5
        return [FakeInstitution()]

    async def fake_show_institution(institution_id_or_name: str) -> FakeInstitution:
        assert institution_id_or_name == str(INSTITUTION_ID)
        return FakeInstitution()

    monkeypatch.setattr(institutions_cli, "_list_institutions", fake_list_institutions)
    monkeypatch.setattr(institutions_cli, "_show_institution", fake_show_institution)

    list_result = runner.invoke(app, ["institutions", "list", "--limit", "5", "--json"])
    show_result = runner.invoke(app, ["institutions", "show", str(INSTITUTION_ID), "--json"])

    assert list_result.exit_code == 0
    assert show_result.exit_code == 0
    assert json.loads(list_result.stdout)["institutions"][0]["name"] == "SLAIF Test Institute"
    assert json.loads(show_result.stdout)["name"] == "SLAIF Test Institute"
    assert "password_hash" not in list_result.stdout
    assert "token_hash" not in show_result.stdout
