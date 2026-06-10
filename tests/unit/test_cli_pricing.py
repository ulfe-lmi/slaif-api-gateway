from __future__ import annotations

import json
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from typer.testing import CliRunner

from slaif_gateway.cli import pricing as pricing_cli
from slaif_gateway.cli.main import app
from slaif_gateway.services.pricing_rule_service import PricingRuleService

runner = CliRunner()
PRICING_ID = uuid.UUID("33333333-3333-4333-8333-333333333333")


@dataclass
class FakePricingRule:
    id: uuid.UUID = PRICING_ID
    provider: str = "openai"
    upstream_model: str = "gpt-test-mini"
    endpoint: str = "/v1/chat/completions"
    currency: str = "EUR"
    input_price_per_1m: Decimal = Decimal("0.10")
    cached_input_price_per_1m: Decimal | None = None
    output_price_per_1m: Decimal = Decimal("0.20")
    reasoning_price_per_1m: Decimal | None = None
    request_price: Decimal | None = None
    pricing_metadata: dict[str, object] = field(default_factory=dict)
    valid_from: datetime = datetime(2026, 1, 1, tzinfo=UTC)
    valid_until: datetime | None = None
    enabled: bool = True
    source_url: str | None = "https://example.test/pricing"
    notes: str | None = "safe"
    created_at: datetime = datetime(2026, 1, 1, tzinfo=UTC)
    updated_at: datetime = datetime(2026, 1, 2, tzinfo=UTC)


def test_pricing_help_registers_commands() -> None:
    result = runner.invoke(app, ["pricing", "--help"])

    assert result.exit_code == 0
    for command in ("add", "list", "show", "disable-model", "import"):
        assert command in result.stdout


def test_pricing_add_parses_decimal_prices(monkeypatch) -> None:
    seen: dict[str, object] = {}

    @asynccontextmanager
    async def fake_session():
        yield None, object()

    class FakeService:
        async def create_pricing_rule(self, **kwargs: object) -> FakePricingRule:
            seen.update(kwargs)
            return FakePricingRule(
                input_price_per_1m=kwargs["input_price_per_1m"],
                output_price_per_1m=kwargs["output_price_per_1m"],
            )

    monkeypatch.setattr(pricing_cli, "cli_db_session", fake_session)
    monkeypatch.setattr(pricing_cli, "_service", lambda session: FakeService())

    row = pricing_cli.run_async(
        pricing_cli._add_pricing_rule(
            provider="openai",
            model="gpt-test-mini",
            endpoint="chat.completions",
            currency="EUR",
            input_price_per_1m="0.10",
            output_price_per_1m="0.20",
            cached_input_price_per_1m=None,
            reasoning_price_per_1m=None,
            valid_from="2026-01-01T00:00:00Z",
            valid_until=None,
            source_url=None,
            notes=None,
            enabled=True,
        )
    )

    assert row.input_price_per_1m == Decimal("0.10")
    assert seen["input_price_per_1m"] == Decimal("0.10")
    assert seen["output_price_per_1m"] == Decimal("0.20")


@pytest.mark.parametrize("field_value", ["-0.01", "-1"])
def test_pricing_add_negative_prices_fail(field_value: str) -> None:
    service = PricingRuleService(pricing_rules_repository=object(), audit_repository=object())

    async def run_invalid() -> None:
        await service.create_pricing_rule(
            provider="openai",
            model="gpt-test-mini",
            endpoint="chat.completions",
            currency="EUR",
            input_price_per_1m=Decimal(field_value),
            output_price_per_1m=Decimal("0.20"),
            cached_input_price_per_1m=None,
            reasoning_price_per_1m=None,
            valid_from=datetime(2026, 1, 1, tzinfo=UTC),
            valid_until=None,
            source_url=None,
            notes=None,
            enabled=True,
        )

    with pytest.raises(ValueError, match="non-negative"):
        pricing_cli.run_async(run_invalid())


def test_pricing_add_valid_until_must_be_after_valid_from() -> None:
    service = PricingRuleService(pricing_rules_repository=object(), audit_repository=object())

    async def run_invalid() -> None:
        await service.create_pricing_rule(
            provider="openai",
            model="gpt-test-mini",
            endpoint="chat.completions",
            currency="EUR",
            input_price_per_1m=Decimal("0.10"),
            output_price_per_1m=Decimal("0.20"),
            cached_input_price_per_1m=None,
            reasoning_price_per_1m=None,
            valid_from=datetime(2026, 1, 2, tzinfo=UTC),
            valid_until=datetime(2026, 1, 1, tzinfo=UTC),
            source_url=None,
            notes=None,
            enabled=True,
        )

    with pytest.raises(ValueError, match="valid_until"):
        pricing_cli.run_async(run_invalid())


def test_pricing_list_show_disable_and_decimal_json(monkeypatch) -> None:
    async def fake_list_pricing_rules(**kwargs: object) -> list[FakePricingRule]:
        assert kwargs["provider"] == "openai"
        assert kwargs["model"] == "gpt-test-mini"
        assert kwargs["enabled_only"] is True
        return [FakePricingRule()]

    async def fake_show_pricing_rule(pricing_rule_id: str) -> FakePricingRule:
        assert pricing_rule_id == str(PRICING_ID)
        return FakePricingRule()

    async def fake_disable_model(**kwargs: object) -> list[FakePricingRule]:
        assert kwargs["provider"] == "openai"
        assert kwargs["model"] == "gpt-test-mini"
        return [FakePricingRule(enabled=False)]

    monkeypatch.setattr(pricing_cli, "_list_pricing_rules", fake_list_pricing_rules)
    monkeypatch.setattr(pricing_cli, "_show_pricing_rule", fake_show_pricing_rule)
    monkeypatch.setattr(pricing_cli, "_disable_model", fake_disable_model)

    list_result = runner.invoke(
        app,
        [
            "pricing",
            "list",
            "--provider",
            "openai",
            "--model",
            "gpt-test-mini",
            "--enabled-only",
            "--json",
        ],
    )
    show_result = runner.invoke(app, ["pricing", "show", str(PRICING_ID), "--json"])
    disable_result = runner.invoke(
        app,
        [
            "pricing",
            "disable-model",
            "--provider",
            "openai",
            "--model",
            "gpt-test-mini",
            "--json",
        ],
    )

    assert list_result.exit_code == 0
    assert show_result.exit_code == 0
    assert disable_result.exit_code == 0
    assert json.loads(list_result.stdout)["pricing_rules"][0]["input_price_per_1m"] == "0.10"
    assert json.loads(show_result.stdout)["output_price_per_1m"] == "0.20"
    assert json.loads(disable_result.stdout)["disabled_count"] == 1


def test_pricing_import_supports_json_and_dry_run(tmp_path, monkeypatch) -> None:
    import_path = tmp_path / "pricing.json"
    import_path.write_text(
        json.dumps(
            [
                {
                    "provider": "openai",
                    "model": "gpt-test-mini",
                    "endpoint": "chat.completions",
                    "currency": "EUR",
                    "input_price_per_1m": "0.10",
                    "output_price_per_1m": "0.20",
                    "valid_from": "2026-01-01T00:00:00Z",
                    "enabled": True,
                }
            ]
        ),
        encoding="utf-8",
    )
    seen: dict[str, object] = {}

    async def fake_preview_pricing_import(*, rows: list[dict[str, object]]) -> dict[str, object]:
        seen["rows"] = rows
        return {
            "total_rows": 1,
            "valid_count": 1,
            "invalid_count": 0,
            "rows": [],
        }

    monkeypatch.setattr(pricing_cli, "_preview_pricing_import", fake_preview_pricing_import)

    result = runner.invoke(
        app,
        ["pricing", "import", "--file", str(import_path), "--dry-run", "--json"],
    )

    assert result.exit_code == 0
    assert len(seen["rows"]) == 1
    payload = json.loads(result.stdout)
    assert payload["dry_run"] is True
    assert payload["imported_count"] == 0
    assert payload["validated_count"] == 1
    assert payload["invalid_count"] == 0


def test_pricing_import_supports_tsv_and_dry_run(tmp_path, monkeypatch) -> None:
    import_path = tmp_path / "pricing.tsv"
    import_path.write_text(
        "provider\tmodel\tendpoint\tcurrency\tinput_price_per_1m\toutput_price_per_1m\n"
        "openai\tgpt-test-mini\tchat.completions\tEUR\t0.10\t0.20\n",
        encoding="utf-8",
    )
    seen: dict[str, object] = {}

    async def fake_preview_pricing_import(*, rows: list[dict[str, object]]) -> dict[str, object]:
        seen["rows"] = rows
        return {
            "total_rows": 1,
            "valid_count": 1,
            "invalid_count": 0,
            "rows": [],
        }

    monkeypatch.setattr(pricing_cli, "_preview_pricing_import", fake_preview_pricing_import)

    result = runner.invoke(
        app,
        ["pricing", "import", "--file", str(import_path), "--dry-run", "--json"],
    )

    assert result.exit_code == 0
    assert seen["rows"] == [
        {
            "provider": "openai",
            "model": "gpt-test-mini",
            "endpoint": "chat.completions",
            "currency": "EUR",
            "input_price_per_1m": "0.10",
            "output_price_per_1m": "0.20",
        }
    ]


def test_pricing_import_accepts_provider_catalog_tsv_fields(tmp_path, monkeypatch) -> None:
    import_path = tmp_path / "pricing.tsv"
    import_path.write_text(
        "provider\tmodel\tendpoint\tcurrency\tinput_price_per_1m\tcached_input_price_per_1m\t"
        "output_price_per_1m\treasoning_price_per_1m\trequest_price\tvalid_from\tsource_url\t"
        "source_retrieved_at\tpricing_metadata\tnotes\n"
        'openrouter\topenai/gpt-test-mini\t/v1/chat/completions\tUSD\t2\t1\t8\t3\t0\t'
        '2026-01-01T00:00:00Z\thttps://openrouter.ai/api/v1/models\t2026-01-01T00:00:00Z\t'
        '{"operator_review_required":true}\treviewed local assumption\n',
        encoding="utf-8",
    )
    seen: dict[str, object] = {}

    async def fake_preview_pricing_import(*, rows: list[dict[str, object]]) -> dict[str, object]:
        seen["rows"] = rows
        return {
            "total_rows": 1,
            "valid_count": 1,
            "invalid_count": 0,
            "rows": [],
        }

    monkeypatch.setattr(pricing_cli, "_preview_pricing_import", fake_preview_pricing_import)

    result = runner.invoke(
        app,
        ["pricing", "import", "--file", str(import_path), "--format", "tsv", "--dry-run", "--json"],
    )

    assert result.exit_code == 0
    assert seen["rows"][0]["pricing_metadata"] == '{"operator_review_required":true}'
    assert seen["rows"][0]["request_price"] == "0"
    assert seen["rows"][0]["source_retrieved_at"] == "2026-01-01T00:00:00Z"


def test_pricing_import_invalid_file_fails_cleanly(tmp_path) -> None:
    import_path = tmp_path / "bad.json"
    import_path.write_text("{not-json", encoding="utf-8")

    result = runner.invoke(app, ["pricing", "import", "--file", str(import_path), "--dry-run"])

    assert result.exit_code != 0
    assert "Error:" in result.stderr
    assert "Traceback" not in result.output


def test_pricing_import_requires_explicit_mode(tmp_path) -> None:
    import_path = tmp_path / "pricing.tsv"
    import_path.write_text(
        "provider\tmodel\tendpoint\tcurrency\tinput_price_per_1m\toutput_price_per_1m\n"
        "openai\tgpt-test-mini\tchat.completions\tEUR\t0.10\t0.20\n",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["pricing", "import", "--file", str(import_path)])

    assert result.exit_code != 0
    assert "Pass --dry-run for preview or --execute --confirm-import --reason to write rows." in result.stderr


def test_pricing_import_execute_requires_confirm_and_reason(tmp_path) -> None:
    import_path = tmp_path / "pricing.tsv"
    import_path.write_text(
        "provider\tmodel\tendpoint\tcurrency\tinput_price_per_1m\toutput_price_per_1m\n"
        "openai\tgpt-test-mini\tchat.completions\tEUR\t0.10\t0.20\n",
        encoding="utf-8",
    )

    missing_confirm = runner.invoke(
        app,
        ["pricing", "import", "--file", str(import_path), "--execute", "--reason", "reviewed import"],
    )
    missing_reason = runner.invoke(
        app,
        ["pricing", "import", "--file", str(import_path), "--execute", "--confirm-import"],
    )
    confirm_without_execute = runner.invoke(
        app,
        ["pricing", "import", "--file", str(import_path), "--confirm-import"],
    )

    assert missing_confirm.exit_code != 0
    assert "--execute requires --confirm-import." in missing_confirm.stderr
    assert missing_reason.exit_code != 0
    assert "--reason is required with --execute." in missing_reason.stderr
    assert confirm_without_execute.exit_code != 0
    assert "--confirm-import requires --execute." in confirm_without_execute.stderr


def test_pricing_import_execute_calls_execution_helper(tmp_path, monkeypatch) -> None:
    import_path = tmp_path / "pricing.tsv"
    import_path.write_text(
        "provider\tmodel\tendpoint\tcurrency\tinput_price_per_1m\toutput_price_per_1m\n"
        "openai\tgpt-test-mini\tchat.completions\tEUR\t0.10\t0.20\n",
        encoding="utf-8",
    )
    seen: dict[str, object] = {}

    async def fake_execute_pricing_import(
        *,
        rows: list[dict[str, object]],
        actor_admin_id: str | None,
        reason: str,
    ) -> dict[str, object]:
        seen["rows"] = rows
        seen["actor_admin_id"] = actor_admin_id
        seen["reason"] = reason
        return {
            "dry_run": False,
            "validated_count": 1,
            "invalid_count": 0,
            "imported_count": 1,
            "created_count": 1,
            "updated_count": 0,
            "skipped_count": 0,
            "error_count": 0,
            "rows": [],
        }

    monkeypatch.setattr(pricing_cli, "_execute_pricing_import", fake_execute_pricing_import)

    result = runner.invoke(
        app,
        [
            "pricing",
            "import",
            "--file",
            str(import_path),
            "--execute",
            "--confirm-import",
            "--reason",
            "operator-reviewed pricing import",
            "--actor-admin-id",
            str(PRICING_ID),
            "--json",
        ],
    )

    assert result.exit_code == 0
    assert seen["actor_admin_id"] == str(PRICING_ID)
    assert seen["reason"] == "operator-reviewed pricing import"
    assert len(seen["rows"]) == 1
    payload = json.loads(result.stdout)
    assert payload["dry_run"] is False
    assert payload["imported_count"] == 1
    assert payload["created_count"] == 1
