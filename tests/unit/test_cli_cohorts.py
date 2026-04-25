from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from typer.testing import CliRunner

from slaif_gateway.cli import cohorts as cohorts_cli
from slaif_gateway.cli.main import app

runner = CliRunner()
COHORT_ID = uuid.UUID("22222222-2222-4222-8222-222222222222")


@dataclass
class FakeCohort:
    id: uuid.UUID = COHORT_ID
    name: str = "SLAIF Spring"
    description: str | None = "training"
    starts_at: datetime | None = datetime(2026, 1, 1, tzinfo=UTC)
    ends_at: datetime | None = datetime(2026, 2, 1, tzinfo=UTC)
    created_at: datetime = datetime(2026, 1, 1, tzinfo=UTC)
    updated_at: datetime = datetime(2026, 1, 2, tzinfo=UTC)


def test_cohorts_help_registers_commands() -> None:
    result = runner.invoke(app, ["cohorts", "--help"])

    assert result.exit_code == 0
    for command in ("create", "list", "show"):
        assert command in result.stdout


def test_cohorts_create_passes_expected_values(monkeypatch) -> None:
    seen: dict[str, object] = {}

    async def fake_create_cohort(**kwargs: object) -> FakeCohort:
        seen.update(kwargs)
        return FakeCohort()

    monkeypatch.setattr(cohorts_cli, "_create_cohort", fake_create_cohort)

    result = runner.invoke(
        app,
        [
            "cohorts",
            "create",
            "--name",
            "SLAIF Spring",
            "--description",
            "training",
            "--starts-at",
            "2026-01-01T00:00:00Z",
            "--ends-at",
            "2026-02-01T00:00:00+00:00",
            "--json",
        ],
    )

    assert result.exit_code == 0
    assert seen["name"] == "SLAIF Spring"
    assert seen["description"] == "training"
    payload = json.loads(result.stdout)
    assert payload["id"] == str(COHORT_ID)


def test_cohorts_invalid_end_before_start_fails_before_database() -> None:
    result = runner.invoke(
        app,
        [
            "cohorts",
            "create",
            "--name",
            "SLAIF Spring",
            "--starts-at",
            "2026-02-01T00:00:00Z",
            "--ends-at",
            "2026-01-01T00:00:00Z",
            "--json",
        ],
    )

    assert result.exit_code != 0
    assert "ends_at must be after starts_at" in result.stdout


def test_cohorts_list_and_show_output_safe(monkeypatch) -> None:
    async def fake_list_cohorts(*, institution_id: str | None, limit: int) -> list[FakeCohort]:
        assert institution_id is None
        assert limit == 5
        return [FakeCohort()]

    async def fake_show_cohort(cohort_id: str) -> FakeCohort:
        assert cohort_id == str(COHORT_ID)
        return FakeCohort()

    monkeypatch.setattr(cohorts_cli, "_list_cohorts", fake_list_cohorts)
    monkeypatch.setattr(cohorts_cli, "_show_cohort", fake_show_cohort)

    list_result = runner.invoke(app, ["cohorts", "list", "--limit", "5", "--json"])
    show_result = runner.invoke(app, ["cohorts", "show", str(COHORT_ID), "--json"])

    assert list_result.exit_code == 0
    assert show_result.exit_code == 0
    assert json.loads(list_result.stdout)["cohorts"][0]["name"] == "SLAIF Spring"
    assert json.loads(show_result.stdout)["name"] == "SLAIF Spring"
    assert "password_hash" not in list_result.stdout
    assert "token_hash" not in show_result.stdout
