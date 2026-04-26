from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from typer.testing import CliRunner

from slaif_gateway.cli import routes as routes_cli
from slaif_gateway.cli.main import app
from slaif_gateway.services.model_route_service import ModelRouteService

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
    for command in ("add", "list", "show", "enable", "disable"):
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
