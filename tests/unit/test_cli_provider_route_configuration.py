"""Objective 199: providers/routes CLI surface (actual Typer, faked async helpers).

Proves the option wiring: provider disabled-by-default creation,
timeout/retries/actor passthrough, provider partial update plumbing and
conflict refusals (including nonblank reasons and known-shape secret
refusals, 199-b), safe read projections that redact recognized credential
shapes, capabilities-file preparation defaults for routes add, and the
two-step routes update command (mode mutex, mixed-mode refusal, bounded
plan file write/read, reviewed-plan route binding, fixed no-echo errors).
No database is used: the async session helpers are replaced with recording
fakes.
"""

from __future__ import annotations

import json
import stat
import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from typer.testing import CliRunner

from slaif_gateway.cli import providers as providers_cli
from slaif_gateway.cli import routes as routes_cli
from slaif_gateway.cli.main import app
from slaif_gateway.schemas.provider_route_configuration import (
    parse_route_update_plan_file,
)
from slaif_gateway.services.provider_route_configuration import preview_route_update

runner = CliRunner()

# 199-b R5: renderer-stable terminal + ANSI/whitespace-independent
# assertions (established project pattern: tests/unit/test_cli.py).
_ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
TERM_ENV = {"COLUMNS": "220", "NO_COLOR": "1"}


def _plain(text: str) -> str:
    return " ".join(_ANSI_RE.sub("", text).split())


def _invoke(*args: Any, **kwargs: Any) -> Any:
    """Renderer-stable invocation (fixed terminal width, no color)."""
    kwargs.setdefault("env", TERM_ENV)
    return runner.invoke(*args, **kwargs)


PROVIDER_ID = uuid.UUID("11111111-1111-4111-8111-111111111111")
ROUTE_ID = "22222222-3333-4444-8555-666666666666"
CHAT_BLOCK = {"chat_text": True, "chat_streaming": True, "chat_function_tools": False}
CODEX_BLOCK = {
    "context_window_tokens": 1050000,
    "default_max_output_tokens": 32768,
    "max_output_tokens": 128000,
}
SECOND_PROVIDER_ID = uuid.UUID("88888888-7777-4666-8555-444444444444")


@dataclass
class FakeProvider:
    id: uuid.UUID = PROVIDER_ID
    provider: str = "mod-a"
    display_name: str = "Mod A"
    # 199-c: a genuinely compatible provider — the pure module resolver
    # must be able to resolve the review destination.
    kind: str = "openai_compatible"
    base_url: str = "https://svc-a.example/api"
    api_key_env_var: str = "SVC_A_KEY"
    enabled: bool = False
    timeout_seconds: int = 30
    max_retries: int = 0
    notes: str | None = None
    created_at: datetime = datetime(2026, 1, 1, tzinfo=UTC)
    updated_at: datetime = datetime(2026, 1, 1, tzinfo=UTC)


@dataclass
class FakeRoute:
    id: str = ROUTE_ID
    requested_model: str = "zap-it-1"
    match_type: str = "exact"
    endpoint: str = "/v1/chat/completions"
    provider: str = "mod-a"
    upstream_model: str = "zap-it-1"
    priority: int = 100
    enabled: bool = True
    visible_in_models: bool = True
    supports_streaming: bool = True
    capabilities: dict[str, Any] = field(
        default_factory=lambda: {
            "chat_completions": dict(CHAT_BLOCK),
            "codex_limits": dict(CODEX_BLOCK),
        }
    )
    notes: str | None = "route notes"
    created_at: datetime = datetime(2026, 1, 1, tzinfo=UTC)
    updated_at: datetime = datetime(2026, 1, 1, tzinfo=UTC)


# --- providers ----------------------------------------------------------------


class TestProvidersAdd:
    def test_omitted_enabled_stays_disabled(self, monkeypatch) -> None:
        seen: dict[str, Any] = {}

        async def fake_add(**kwargs: Any) -> FakeProvider:
            seen.update(kwargs)
            return FakeProvider()

        monkeypatch.setattr(providers_cli, "_add_provider", fake_add)
        result = _invoke(
            app,
            [
                "providers", "add", "--provider", "mod-a",
                "--api-key-env-var", "SVC_A_KEY", "--kind", "module",
                "--base-url", "https://svc-a.example/api", "--json",
            ],
        )
        assert result.exit_code == 0
        assert seen["enabled"] is False
        assert seen["timeout_seconds"] == 300
        assert seen["max_retries"] == 2

    def test_explicit_enable_and_timeout_retries_passthrough(self, monkeypatch) -> None:
        seen: dict[str, Any] = {}

        async def fake_add(**kwargs: Any) -> FakeProvider:
            seen.update(kwargs)
            return FakeProvider()

        monkeypatch.setattr(providers_cli, "_add_provider", fake_add)
        result = _invoke(
            app,
            [
                "providers", "add", "--provider", "mod-a",
                "--api-key-env-var", "SVC_A_KEY", "--kind", "module",
                "--base-url", "https://svc-a.example/api",
                "--enabled", "--timeout-seconds", "30", "--max-retries", "0",
                "--actor-admin-id", str(PROVIDER_ID), "--json",
            ],
        )
        assert result.exit_code == 0
        assert seen["enabled"] is True
        assert seen["timeout_seconds"] == 30
        assert seen["max_retries"] == 0
        assert seen["actor_admin_id"] == PROVIDER_ID

    def test_actor_admin_id_must_be_uuid(self, monkeypatch) -> None:
        async def fake_add(**kwargs: Any) -> FakeProvider:
            raise AssertionError("must not be called")

        monkeypatch.setattr(providers_cli, "_add_provider", fake_add)
        result = _invoke(
            app,
            [
                "providers", "add", "--provider", "mod-a",
                "--api-key-env-var", "SVC_A_KEY",
                "--actor-admin-id", "not-a-uuid",
            ],
        )
        assert result.exit_code != 0
        assert "not-a-uuid" not in result.stdout

    # --- 199-c: creation-surface known-shape guards ----------------------------

    def test_notes_known_secret_shape_refused_on_create(self, monkeypatch) -> None:
        async def fake_add(**kwargs: Any) -> FakeProvider:
            raise AssertionError("must not be called")

        monkeypatch.setattr(providers_cli, "_add_provider", fake_add)
        canary = "sk-proj-abcdef1234567890abcdef1234567890"
        result = _invoke(
            app,
            [
                "providers", "add", "--provider", "mod-a",
                "--api-key-env-var", "SVC_A_KEY",
                "--notes", canary,
            ],
        )
        assert result.exit_code != 0
        assert "credential patterns" in _plain(result.stderr)
        assert canary not in result.stdout
        assert canary not in result.stderr

    def test_reason_known_secret_shape_refused_on_create(self, monkeypatch) -> None:
        async def fake_add(**kwargs: Any) -> FakeProvider:
            raise AssertionError("must not be called")

        monkeypatch.setattr(providers_cli, "_add_provider", fake_add)
        canary = "sk-proj-abcdef1234567890abcdef1234567890"
        result = _invoke(
            app,
            [
                "providers", "add", "--provider", "mod-a",
                "--api-key-env-var", "SVC_A_KEY",
                "--reason", canary,
            ],
        )
        assert result.exit_code != 0
        assert "credential patterns" in _plain(result.stderr)
        assert canary not in result.stdout
        assert canary not in result.stderr

    def test_display_name_and_base_url_secret_shapes_refused_on_create(
        self, monkeypatch
    ) -> None:
        async def fake_add(**kwargs: Any) -> FakeProvider:
            raise AssertionError("must not be called")

        monkeypatch.setattr(providers_cli, "_add_provider", fake_add)
        for flag, value in (
            ("--display-name", "Auth: Bearer abcdef1234567890"),
            ("--base-url", "https://sk-proj-abcdef1234567890abcdef1234567890"),
        ):
            result = _invoke(
                app,
                [
                    "providers", "add", "--provider", "mod-a",
                    "--api-key-env-var", "SVC_A_KEY",
                    flag, value,
                ],
            )
            assert result.exit_code != 0
            assert "credential patterns" in _plain(result.stderr)
            assert value not in result.stdout
            assert value not in result.stderr

    def test_ordinary_text_and_env_reference_accepted_on_create(self, monkeypatch) -> None:
        seen: dict[str, Any] = {}

        async def fake_add(**kwargs: Any) -> FakeProvider:
            seen.update(kwargs)
            return FakeProvider()

        monkeypatch.setattr(providers_cli, "_add_provider", fake_add)
        result = _invoke(
            app,
            [
                "providers", "add", "--provider", "mod-a",
                "--api-key-env-var", "SVC_A_KEY", "--kind", "module",
                "--display-name", "Svc A (reviewed)",
                "--base-url", "https://svc-a.example/api",
                "--notes", "uses SVC_A_KEY; reviewed note",
                "--reason", "fictional module preparation",
                "--json",
            ],
        )
        assert result.exit_code == 0
        # safe env-variable NAMES and ordinary text stay literal
        assert seen["display_name"] == "Svc A (reviewed)"
        assert seen["base_url"] == "https://svc-a.example/api"
        assert seen["notes"] == "uses SVC_A_KEY; reviewed note"
        assert seen["reason"] == "fictional module preparation"


class TestProvidersUpdate:
    def test_partial_update_plumbing(self, monkeypatch) -> None:
        seen: dict[str, Any] = {}

        async def fake_update(provider_or_id: str, **kwargs: Any) -> FakeProvider:
            seen["provider_or_id"] = provider_or_id
            seen.update(kwargs)
            return FakeProvider()

        monkeypatch.setattr(providers_cli, "_update_provider", fake_update)
        result = _invoke(
            app,
            [
                "providers", "update", "mod-a", "--reason", "tune timeout",
                "--timeout-seconds", "180", "--max-retries", "0", "--json",
            ],
        )
        assert result.exit_code == 0
        assert seen["provider_or_id"] == "mod-a"
        assert seen["timeout_seconds"] == 180
        assert seen["max_retries"] == 0
        assert seen["display_name"] is None  # omitted = preserve
        assert seen["clear_notes"] is False
        assert seen["reason"] == "tune timeout"
        payload = json.loads(result.stdout)
        assert payload["timeout_seconds"] == 30  # fake row value

    def test_reason_required(self, monkeypatch) -> None:
        async def fake_update(provider_or_id: str, **kwargs: Any) -> FakeProvider:
            raise AssertionError("must not be called")

        monkeypatch.setattr(providers_cli, "_update_provider", fake_update)
        result = _invoke(app, ["providers", "update", "mod-a"])
        assert result.exit_code != 0

    def test_notes_and_clear_conflict(self, monkeypatch) -> None:
        async def fake_update(provider_or_id: str, **kwargs: Any) -> FakeProvider:
            raise AssertionError("must not be called")

        monkeypatch.setattr(providers_cli, "_update_provider", fake_update)
        result = _invoke(
            app,
            [
                "providers", "update", "mod-a", "--reason", "r",
                "--notes", "x", "--clear-notes",
            ],
        )
        assert result.exit_code != 0
        assert "--notes or --clear-notes" in _plain(result.stderr)

    def test_blank_reason_refused(self, monkeypatch) -> None:
        # 199-b: the audit reason must be NONBLANK on provider updates.
        async def fake_update(provider_or_id: str, **kwargs: Any) -> FakeProvider:
            raise AssertionError("must not be called")

        monkeypatch.setattr(providers_cli, "_update_provider", fake_update)
        result = _invoke(
            app,
            ["providers", "update", "mod-a", "--reason", "   ", "--json"],
        )
        assert result.exit_code != 0
        assert "nonblank" in _plain(result.stderr)

    def test_notes_known_secret_shape_refused(self, monkeypatch) -> None:
        # 199-b: known credential shapes are refused BEFORE mutation and
        # never echoed.
        canary = "sk-proj-abcdef1234567890abcdef1234567890"
        async def fake_update(provider_or_id: str, **kwargs: Any) -> FakeProvider:
            raise AssertionError("must not be called")

        monkeypatch.setattr(providers_cli, "_update_provider", fake_update)
        result = _invoke(
            app,
            [
                "providers", "update", "mod-a", "--reason", "r",
                "--notes", canary,
            ],
        )
        assert result.exit_code != 0
        assert "credential patterns" in _plain(result.stderr)
        assert canary not in result.stderr
        assert canary not in result.stdout

    def test_safe_output_redacts_known_shapes(self, monkeypatch) -> None:
        # 199-b: existing free-form read values are safely projected on
        # add/update outcomes (known-shape protection, no echo).
        canary = "sk-proj-abcdef1234567890abcdef1234567890"
        row = FakeProvider(notes=f"legacy note {canary}")

        async def fake_update(provider_or_id: str, **kwargs: Any) -> FakeProvider:
            return row

        monkeypatch.setattr(providers_cli, "_update_provider", fake_update)
        result = _invoke(
            app,
            [
                "providers", "update", "mod-a", "--reason", "r",
                "--timeout-seconds", "45", "--json",
            ],
        )
        assert result.exit_code == 0
        assert canary not in result.stdout
        assert "***" in result.stdout
        payload = json.loads(result.stdout)
        # legitimate env-reference NAME is preserved, never masked
        assert payload["api_key_env_var"] == "SVC_A_KEY"


# --- routes add ----------------------------------------------------------------


class TestRoutesAdd:
    def test_flag_free_add_keeps_historical_enabled_default(self, monkeypatch) -> None:
        seen: dict[str, Any] = {}

        async def fake_add(**kwargs: Any) -> FakeRoute:
            seen.update(kwargs)
            return FakeRoute()

        monkeypatch.setattr(routes_cli, "_add_route", fake_add)
        result = _invoke(
            app,
            [
                "routes", "add", "--requested-model", "zap-it-1",
                "--match-type", "exact", "--provider", "mod-a", "--json",
            ],
        )
        assert result.exit_code == 0
        assert seen["enabled"] is True
        assert seen["capabilities"] is None
        assert seen["supports_streaming"] is True

    def test_capabilities_file_preparation_defaults_disabled(self, tmp_path, monkeypatch) -> None:
        caps = tmp_path / "caps.json"
        caps.write_text(
            json.dumps(
                {"schema_version": 1, "capabilities": {"chat_completions": dict(CHAT_BLOCK)}}
            ),
            encoding="utf-8",
        )
        seen: dict[str, Any] = {}

        async def fake_add(**kwargs: Any) -> FakeRoute:
            seen.update(kwargs)
            return FakeRoute()

        monkeypatch.setattr(routes_cli, "_add_route", fake_add)
        result = _invoke(
            app,
            [
                "routes", "add", "--requested-model", "zap-it-1",
                "--match-type", "exact", "--provider", "mod-a",
                "--capabilities-file", str(caps), "--json",
            ],
        )
        assert result.exit_code == 0
        assert seen["enabled"] is False
        assert seen["capabilities"] == {"chat_completions": dict(CHAT_BLOCK)}

    def test_capabilities_file_with_explicit_enable(self, tmp_path, monkeypatch) -> None:
        caps = tmp_path / "caps.json"
        caps.write_text(
            json.dumps(
                {"schema_version": 1, "capabilities": {"chat_completions": dict(CHAT_BLOCK)}}
            ),
            encoding="utf-8",
        )
        seen: dict[str, Any] = {}

        async def fake_add(**kwargs: Any) -> FakeRoute:
            seen.update(kwargs)
            return FakeRoute()

        monkeypatch.setattr(routes_cli, "_add_route", fake_add)
        result = _invoke(
            app,
            [
                "routes", "add", "--requested-model", "zap-it-1",
                "--match-type", "exact", "--provider", "mod-a",
                "--capabilities-file", str(caps), "--enabled", "--json",
            ],
        )
        assert result.exit_code == 0
        assert seen["enabled"] is True

    def test_notes_known_secret_shape_refused(self, monkeypatch) -> None:
        # 199-b R4: route creation notes are guarded before any DB access.
        canary = "sk-proj-abcdef1234567890abcdef1234567890"

        async def fake_add(**kwargs: Any) -> FakeRoute:
            raise AssertionError("must not be called")

        monkeypatch.setattr(routes_cli, "_add_route", fake_add)
        result = _invoke(
            app,
            [
                "routes", "add", "--requested-model", "zap-it-1",
                "--match-type", "exact", "--provider", "mod-a",
                "--notes", canary, "--json",
            ],
        )
        assert result.exit_code != 0
        assert "credential patterns" in _plain(result.stderr)
        assert canary not in result.stderr

    def test_invalid_capabilities_file_refused_before_db(self, tmp_path, monkeypatch) -> None:
        caps = tmp_path / "caps.json"
        caps.write_text('{"schema_version": 1, "capabilities": {"made_up": true}}', encoding="utf-8")

        async def fake_add(**kwargs: Any) -> FakeRoute:
            raise AssertionError("must not be called")

        monkeypatch.setattr(routes_cli, "_add_route", fake_add)
        result = _invoke(
            app,
            [
                "routes", "add", "--requested-model", "zap-it-1",
                "--match-type", "exact", "--provider", "mod-a",
                "--capabilities-file", str(caps), "--json",
            ],
        )
        assert result.exit_code != 0
        assert "unsupported groups" in result.stderr
        assert str(caps) not in result.stderr  # no path echo


# --- routes update ----------------------------------------------------------------


def _fake_preview_for(route: FakeRoute, monkeypatch) -> None:
    provider = FakeProvider()

    async def fake_preview(route_id: str, **edits: Any):
        return preview_route_update(route, provider, **edits)

    monkeypatch.setattr(routes_cli, "_preview_route_update_plan", fake_preview)


def _dry_run_args(route_id: str, plan_path: str, *extra: str) -> list[str]:
    return ["routes", "update", route_id, "--dry-run", plan_path, *extra]


class TestRoutesUpdateDryRun:
    def test_requires_a_mode(self) -> None:
        result = _invoke(app, ["routes", "update", ROUTE_ID])
        assert result.exit_code != 0
        assert "--dry-run PATH or --execute PATH" in _plain(result.stderr)

    def test_modes_are_mutex(self) -> None:
        result = _invoke(
            app, ["routes", "update", ROUTE_ID, "--dry-run", "/tmp/a", "--execute", "/tmp/b"]
        )
        assert result.exit_code != 0

    def test_partial_codex_plan_written_0600(self, tmp_path, monkeypatch) -> None:
        route = FakeRoute()
        _fake_preview_for(route, monkeypatch)
        plan_path = tmp_path / "plan.json"
        result = _invoke(
            app,
            _dry_run_args(ROUTE_ID, str(plan_path), "--codex-max-output-tokens", "400000", "--json"),
        )
        assert result.exit_code == 0, result.stderr
        assert plan_path.exists()
        mode = stat.S_IMODE(plan_path.stat().st_mode)
        assert mode == 0o600
        plan = parse_route_update_plan_file(plan_path.read_bytes())
        assert plan.capabilities_mode == "partial"
        assert plan.capability_patch.codex_limits == {"max_output_tokens": 400000}
        payload = json.loads(result.stdout)
        assert payload["capabilities_mode"] == "partial"
        assert payload["expected_configuration_fingerprint"] == (
            plan.expected_configuration_fingerprint
        )
        # strict round-trip: the written file re-parses under the same contract
        assert plan.route_id == ROUTE_ID

    def test_no_overwrite_refused(self, tmp_path, monkeypatch) -> None:
        route = FakeRoute()
        _fake_preview_for(route, monkeypatch)
        plan_path = tmp_path / "plan.json"
        first = _invoke(
            app, _dry_run_args(ROUTE_ID, str(plan_path), "--priority", "50")
        )
        assert first.exit_code == 0
        second = _invoke(
            app, _dry_run_args(ROUTE_ID, str(plan_path), "--priority", "51")
        )
        assert second.exit_code != 0
        assert "already exists" in second.stderr
        plan = parse_route_update_plan_file(plan_path.read_bytes())
        assert plan.priority == 50  # untouched

    def test_missing_route_safe_error(self, monkeypatch) -> None:
        async def fake_preview(route_id: str, **edits: Any):
            from slaif_gateway.services.record_errors import RecordNotFoundError

            raise RecordNotFoundError("Model route")

        monkeypatch.setattr(routes_cli, "_preview_route_update_plan", fake_preview)
        result = _invoke(app, _dry_run_args(ROUTE_ID, "/tmp/x"))
        assert result.exit_code != 0
        assert ROUTE_ID not in result.stderr

    def test_file_plus_partial_flags_refused(self, tmp_path, monkeypatch) -> None:
        route = FakeRoute()
        _fake_preview_for(route, monkeypatch)
        caps = tmp_path / "caps.json"
        caps.write_text(
            json.dumps({"schema_version": 1, "capabilities": {"chat_completions": dict(CHAT_BLOCK)}}),
            encoding="utf-8",
        )
        result = _invoke(
            app,
            _dry_run_args(ROUTE_ID, str(tmp_path / "p"), "--capabilities-file", str(caps),
                          "--codex-max-output-tokens", "400000"),
        )
        assert result.exit_code != 0
        assert "complete replacement" in result.stderr

    def test_chat_capability_flag_malformed(self, monkeypatch) -> None:
        route = FakeRoute()
        _fake_preview_for(route, monkeypatch)
        result = _invoke(
            app, _dry_run_args(ROUTE_ID, "/tmp/p", "--chat-capability", "chat_text")
        )
        assert result.exit_code != 0
        assert "NAME=true or NAME=false" in result.stderr

    def test_completion_profile_and_clear_conflict(self, monkeypatch) -> None:
        route = FakeRoute()
        _fake_preview_for(route, monkeypatch)
        result = _invoke(
            app,
            _dry_run_args(
                ROUTE_ID, "/tmp/p",
                "--completion-service-profile", "zap-it-v1", "--clear-completion-service",
            ),
        )
        assert result.exit_code != 0

    def test_invalid_candidate_refused_without_file(self, tmp_path, monkeypatch) -> None:
        route = FakeRoute()
        _fake_preview_for(route, monkeypatch)
        plan_path = tmp_path / "p"
        result = _invoke(
            app, _dry_run_args(ROUTE_ID, str(plan_path), "--codex-context-window-tokens", "10")
        )
        assert result.exit_code != 0
        assert not plan_path.exists()
        assert "codex_limits" in result.stderr


class TestRoutesUpdateExecute:
    def test_execute_requires_reason(self, tmp_path, monkeypatch) -> None:
        async def fake_execute(
            route_id: str, plan, *, reason: str, actor_admin_id: Any
        ) -> FakeRoute:
            raise AssertionError("must not be called")

        monkeypatch.setattr(routes_cli, "_execute_route_update_plan", fake_execute)
        result = _invoke(app, ["routes", "update", ROUTE_ID, "--execute", "/tmp/p"])
        assert result.exit_code != 0
        assert "--reason" in _plain(result.stderr)

    def test_mixed_mode_refused(self, tmp_path, monkeypatch) -> None:
        async def fake_execute(
            route_id: str, plan, *, reason: str, actor_admin_id: Any
        ) -> FakeRoute:
            raise AssertionError("must not be called")

        monkeypatch.setattr(routes_cli, "_execute_route_update_plan", fake_execute)
        result = _invoke(
            app,
            [
                "routes", "update", ROUTE_ID, "--execute", "/tmp/p",
                "--reason", "r", "--codex-max-output-tokens", "400000",
            ],
        )
        assert result.exit_code != 0
        assert "--dry-run only" in _plain(result.stderr)

    def test_happy_path_executes_reviewed_plan(self, tmp_path, monkeypatch) -> None:
        route = FakeRoute()
        _fake_preview_for(route, monkeypatch)
        plan_path = tmp_path / "plan.json"
        written = _invoke(
            app, _dry_run_args(ROUTE_ID, str(plan_path), "--priority", "50")
        )
        assert written.exit_code == 0

        executed: dict[str, Any] = {}

        async def fake_execute(
            route_id: str, plan, *, reason: str, actor_admin_id: Any
        ) -> FakeRoute:
            executed["route_id"] = route_id
            executed["plan"] = plan
            executed["reason"] = reason
            return FakeRoute(priority=50)

        monkeypatch.setattr(routes_cli, "_execute_route_update_plan", fake_execute)
        result = _invoke(
            app,
            [
                "routes", "update", ROUTE_ID, "--execute", str(plan_path),
                "--reason", "reviewed ceiling", "--json",
            ],
        )
        assert result.exit_code == 0, result.stderr
        assert executed["reason"] == "reviewed ceiling"
        assert executed["route_id"] == ROUTE_ID
        assert executed["plan"].priority == 50
        payload = json.loads(result.stdout)
        assert payload["priority"] == 50

    def test_tampered_plan_forwarded_and_detected_stale(self, tmp_path, monkeypatch) -> None:
        route = FakeRoute()
        _fake_preview_for(route, monkeypatch)
        plan_path = tmp_path / "plan.json"
        written = _invoke(app, _dry_run_args(ROUTE_ID, str(plan_path), "--priority", "50"))
        assert written.exit_code == 0
        document = json.loads(plan_path.read_text(encoding="utf-8"))
        document["priority"] = 999  # tamper outside the plan flow
        plan_path.write_text(json.dumps(document), encoding="utf-8")

        executed: dict[str, Any] = {}

        async def fake_execute(
            route_id: str, plan, *, reason: str, actor_admin_id: Any
        ) -> FakeRoute:
            executed["plan"] = plan
            return FakeRoute(priority=999)

        monkeypatch.setattr(routes_cli, "_execute_route_update_plan", fake_execute)
        result = _invoke(
            app,
            ["routes", "update", ROUTE_ID, "--execute", str(plan_path), "--reason", "r"],
        )
        # The tampered document still strict-parses and is forwarded to the
        # execute helper exactly as stored. The plan's expected fingerprint
        # was computed for priority=50, so the service/PG layer refuses the
        # mismatch as stale (proven in the service unit + PG tests).
        assert result.exit_code == 0, result.stderr
        assert executed["plan"].priority == 999
        original = parse_route_update_plan_file(
            json.dumps({**document, "priority": 50}).encode("utf-8")
        )
        assert executed["plan"].expected_configuration_fingerprint == (
            original.expected_configuration_fingerprint
        )

    def test_blank_reason_refused(self, tmp_path, monkeypatch) -> None:
        # 199-b: execute requires a NONBLANK reason (whitespace is refused).
        async def fake_execute(
            route_id: str, plan, *, reason: str, actor_admin_id: Any
        ) -> FakeRoute:
            raise AssertionError("must not be called")

        monkeypatch.setattr(routes_cli, "_execute_route_update_plan", fake_execute)
        result = _invoke(
            app,
            ["routes", "update", ROUTE_ID, "--execute", "/tmp/p", "--reason", "   "],
        )
        assert result.exit_code != 0
        assert "nonblank" in _plain(result.stderr)

    def test_route_argument_must_match_plan(self, tmp_path, monkeypatch) -> None:
        # 199-b: the CLI route argument BINDS to the reviewed plan; a plan
        # can never be applied to a different route.
        route = FakeRoute()
        _fake_preview_for(route, monkeypatch)
        plan_path = tmp_path / "plan.json"
        written = _invoke(app, _dry_run_args(ROUTE_ID, str(plan_path), "--priority", "50"))
        assert written.exit_code == 0

        async def fake_execute(
            route_id: str, plan, *, reason: str, actor_admin_id: Any
        ) -> FakeRoute:
            raise AssertionError("must not be called")

        monkeypatch.setattr(routes_cli, "_execute_route_update_plan", fake_execute)
        other = "99999999-0000-4000-8000-000000000000"
        result = _invoke(
            app,
            [
                "routes", "update", other, "--execute", str(plan_path),
                "--reason", "r",
            ],
        )
        assert result.exit_code != 0
        assert "match the reviewed plan" in _plain(result.stderr)
        assert other not in _plain(result.stderr)

    def test_invalid_plan_file_refused(self, tmp_path, monkeypatch) -> None:
        plan_path = tmp_path / "plan.json"
        plan_path.write_text('{"schema_version": 2}', encoding="utf-8")

        async def fake_execute(
            route_id: str, plan, *, reason: str, actor_admin_id: Any
        ) -> FakeRoute:
            raise AssertionError("must not be called")

        monkeypatch.setattr(routes_cli, "_execute_route_update_plan", fake_execute)
        result = _invoke(
            app,
            ["routes", "update", ROUTE_ID, "--execute", str(plan_path), "--reason", "r"],
        )
        assert result.exit_code != 0
        assert "schema_version" in result.stderr

    def test_stale_fingerprint_rejected_at_parse_level(self, tmp_path, monkeypatch) -> None:
        route = FakeRoute()
        _fake_preview_for(route, monkeypatch)
        plan_path = tmp_path / "plan.json"
        written = _invoke(app, _dry_run_args(ROUTE_ID, str(plan_path), "--priority", "50"))
        assert written.exit_code == 0
        document = json.loads(plan_path.read_text(encoding="utf-8"))
        document["expected_configuration_fingerprint"] = "z" * 64
        plan_path.write_text(json.dumps(document), encoding="utf-8")

        result = _invoke(
            app,
            ["routes", "update", ROUTE_ID, "--execute", str(plan_path), "--reason", "r"],
        )
        assert result.exit_code != 0
        assert "fingerprint" in result.stderr
