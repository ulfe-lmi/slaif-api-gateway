from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from typer.testing import CliRunner

from slaif_gateway.cli import routes as routes_cli
from slaif_gateway.cli.main import app
from slaif_gateway.services.model_route_service import ModelRouteService
from slaif_gateway.services.route_import import RouteImportProviderRef, validate_route_import_rows

runner = CliRunner()
ROUTE_ID = uuid.UUID("22222222-2222-4222-8222-222222222222")


@dataclass
class FakeRoute:
    id: uuid.UUID = ROUTE_ID
    requested_model: str = "gpt-test-mini"
    match_type: str = "exact"
    endpoint: str = "/v1/chat/completions"
    provider: str = "openai"
    upstream_model: str = "gpt-test-mini"
    priority: int = 100
    enabled: bool = True
    visible_in_models: bool = True
    supports_streaming: bool = True
    capabilities: dict[str, object] = field(default_factory=dict)
    notes: str | None = "safe"
    created_at: datetime = datetime(2026, 1, 1, tzinfo=UTC)
    updated_at: datetime = datetime(2026, 1, 2, tzinfo=UTC)


def test_routes_help_registers_commands() -> None:
    result = runner.invoke(app, ["routes", "--help"])

    assert result.exit_code == 0
    for command in ("add", "list", "show", "enable", "disable", "import"):
        assert command in result.stdout


def test_routes_add_validates_match_type() -> None:
    service = ModelRouteService(
        model_routes_repository=object(),
        audit_repository=object(),
    )

    async def run_invalid() -> None:
        await service.create_model_route(
            requested_model="gpt-test-mini",
            match_type="alias",
            provider="openai",
            upstream_model=None,
            priority=100,
            visible_in_models=True,
            enabled=True,
            notes=None,
        )

    try:
        routes_cli.run_async(run_invalid())
    except ValueError as exc:
        assert "match_type" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("invalid match_type should fail")


def test_routes_add_passes_provider_upstream_priority_and_visibility(monkeypatch) -> None:
    seen: dict[str, object] = {}

    async def fake_add_route(**kwargs: object) -> FakeRoute:
        seen.update(kwargs)
        return FakeRoute(
            requested_model=str(kwargs["requested_model"]),
            match_type=str(kwargs["match_type"]),
            provider=str(kwargs["provider"]),
            upstream_model=str(kwargs["upstream_model"]),
            priority=int(kwargs["priority"]),
            visible_in_models=bool(kwargs["visible_in_models"]),
        )

    monkeypatch.setattr(routes_cli, "_add_route", fake_add_route)

    result = runner.invoke(
        app,
        [
            "routes",
            "add",
            "--requested-model",
            "classroom-cheap",
            "--match-type",
            "exact",
            "--provider",
            "openrouter",
            "--upstream-model",
            "openai/gpt-test-mini",
            "--priority",
            "12",
            "--hidden",
            "--json",
        ],
    )

    assert result.exit_code == 0
    assert seen["provider"] == "openrouter"
    assert seen["upstream_model"] == "openai/gpt-test-mini"
    assert seen["priority"] == 12
    assert seen["visible_in_models"] is False
    payload = json.loads(result.stdout)
    assert payload["priority"] == 12
    assert payload["visible_in_models"] is False


def test_routes_list_show_and_toggle_output_safe(monkeypatch) -> None:
    async def fake_list_routes(
        *,
        provider: str | None,
        enabled_only: bool,
        visible_only: bool,
        limit: int,
    ) -> list[FakeRoute]:
        assert provider == "openai"
        assert enabled_only is True
        assert visible_only is True
        assert limit == 5
        return [FakeRoute()]

    async def fake_show_route(route_id: str) -> FakeRoute:
        assert route_id == str(ROUTE_ID)
        return FakeRoute()

    async def fake_set_route_enabled(route_id: str, *, enabled: bool) -> FakeRoute:
        assert route_id == str(ROUTE_ID)
        return FakeRoute(enabled=enabled)

    monkeypatch.setattr(routes_cli, "_list_routes", fake_list_routes)
    monkeypatch.setattr(routes_cli, "_show_route", fake_show_route)
    monkeypatch.setattr(routes_cli, "_set_route_enabled", fake_set_route_enabled)

    list_result = runner.invoke(
        app,
        ["routes", "list", "--provider", "openai", "--enabled-only", "--visible-only", "--limit", "5", "--json"],
    )
    show_result = runner.invoke(app, ["routes", "show", str(ROUTE_ID), "--json"])
    disable_result = runner.invoke(app, ["routes", "disable", str(ROUTE_ID), "--json"])
    enable_result = runner.invoke(app, ["routes", "enable", str(ROUTE_ID), "--json"])

    assert list_result.exit_code == 0
    assert show_result.exit_code == 0
    assert disable_result.exit_code == 0
    assert enable_result.exit_code == 0
    assert json.loads(list_result.stdout)["routes"][0]["requested_model"] == "gpt-test-mini"
    assert json.loads(show_result.stdout)["id"] == str(ROUTE_ID)
    assert json.loads(disable_result.stdout)["enabled"] is False
    assert json.loads(enable_result.stdout)["enabled"] is True
    assert "token_hash" not in list_result.stdout


def test_routes_import_supports_tsv_and_dry_run(tmp_path, monkeypatch) -> None:
    import_path = tmp_path / "routes.tsv"
    import_path.write_text(
        "requested_model\tmatch_type\tendpoint\tprovider\tupstream_model\tpriority\t"
        "enabled\tvisible_in_models\tsupports_streaming\tcapabilities\tnotes\n"
        'gpt-test-mini\texact\tchat.completions\topenrouter\topenai/gpt-test-mini\t100\t'
        'true\ttrue\ttrue\t{"chat_completions":{"chat_text":true}}\tsafe\n',
        encoding="utf-8",
    )
    seen: dict[str, object] = {}

    async def fake_preview_route_import(*, rows: list[dict[str, object]]):
        seen["rows"] = rows
        return validate_route_import_rows(
            rows,
            provider_configs=(RouteImportProviderRef(id=uuid.uuid4(), provider="openrouter"),),
            max_rows=10,
        )

    monkeypatch.setattr(routes_cli, "_preview_route_import", fake_preview_route_import)

    result = runner.invoke(
        app,
        ["routes", "import", "--file", str(import_path), "--format", "tsv", "--dry-run", "--json"],
    )

    assert result.exit_code == 0
    assert seen["rows"] == [
        {
            "requested_model": "gpt-test-mini",
            "match_type": "exact",
            "endpoint": "chat.completions",
            "provider": "openrouter",
            "upstream_model": "openai/gpt-test-mini",
            "priority": "100",
            "enabled": "true",
            "visible_in_models": "true",
            "supports_streaming": "true",
            "capabilities": '{"chat_completions":{"chat_text":true}}',
            "notes": "safe",
        }
    ]
    payload = json.loads(result.stdout)
    assert payload["dry_run"] is True
    assert payload["valid_count"] == 1
    assert payload["invalid_count"] == 0


def test_routes_import_requires_dry_run(tmp_path) -> None:
    import_path = tmp_path / "routes.tsv"
    import_path.write_text(
        "requested_model\tmatch_type\tprovider\tupstream_model\n"
        "gpt-test-mini\texact\topenrouter\topenai/gpt-test-mini\n",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["routes", "import", "--file", str(import_path)])

    assert result.exit_code != 0
    assert "Pass --dry-run for preview or --execute --confirm-import --reason to write rows." in result.stderr


def test_routes_import_execute_requires_confirm_and_reason(tmp_path) -> None:
    import_path = tmp_path / "routes.tsv"
    import_path.write_text(
        "requested_model\tmatch_type\tprovider\tupstream_model\n"
        "gpt-test-mini\texact\topenrouter\topenai/gpt-test-mini\n",
        encoding="utf-8",
    )

    missing_confirm = runner.invoke(
        app,
        ["routes", "import", "--file", str(import_path), "--execute", "--reason", "reviewed import"],
    )
    missing_reason = runner.invoke(
        app,
        ["routes", "import", "--file", str(import_path), "--execute", "--confirm-import"],
    )
    confirm_without_execute = runner.invoke(
        app,
        ["routes", "import", "--file", str(import_path), "--confirm-import"],
    )

    assert missing_confirm.exit_code != 0
    assert "--execute requires --confirm-import." in missing_confirm.stderr
    assert missing_reason.exit_code != 0
    assert "--reason is required with --execute." in missing_reason.stderr
    assert confirm_without_execute.exit_code != 0
    assert "--confirm-import requires --execute." in confirm_without_execute.stderr


def test_routes_import_execute_calls_execution_helper(tmp_path, monkeypatch) -> None:
    import_path = tmp_path / "routes.tsv"
    import_path.write_text(
        "requested_model\tmatch_type\tprovider\tupstream_model\n"
        "gpt-test-mini\texact\topenrouter\topenai/gpt-test-mini\n",
        encoding="utf-8",
    )
    seen: dict[str, object] = {}

    async def fake_execute_route_import(
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
            "total_rows": 1,
            "valid_count": 1,
            "invalid_count": 0,
            "created_count": 1,
            "updated_count": 0,
            "skipped_count": 0,
            "error_count": 0,
            "rows": [],
        }

    monkeypatch.setattr(routes_cli, "_execute_route_import", fake_execute_route_import)

    result = runner.invoke(
        app,
        [
            "routes",
            "import",
            "--file",
            str(import_path),
            "--execute",
            "--confirm-import",
            "--reason",
            "operator-reviewed route import",
            "--actor-admin-id",
            str(ROUTE_ID),
            "--json",
        ],
    )

    assert result.exit_code == 0
    assert seen["actor_admin_id"] == str(ROUTE_ID)
    assert seen["reason"] == "operator-reviewed route import"
    assert len(seen["rows"]) == 1
    payload = json.loads(result.stdout)
    assert payload["dry_run"] is False
    assert payload["created_count"] == 1
