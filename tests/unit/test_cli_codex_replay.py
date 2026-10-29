"""Actual-Typer evidence for the codex replay CLI surface (objective 200).

The async maintenance service is replaced with recording fakes (no
database, no backend contact). Proves: subcommand registration, the
exactly-one-scope law, mode mutex, TTL range and reason laws, dry-run 0600
plan file creation (new-file only), strict invalid-plan refusals without
echoing canaries, and safe bounded output.
"""

from __future__ import annotations

import json
import re
import stat
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

import pytest
from typer.testing import CliRunner

from slaif_gateway.cli import codex_replay as codex_replay_cli
from slaif_gateway.cli.main import app
from slaif_gateway.schemas.codex_replay_maintenance import (
    ReplayExtendPlan,
    ReplayScope,
    parse_replay_extend_plan_file,
    render_replay_extend_plan,
)
from slaif_gateway.services.codex_replay_maintenance import (
    ReplayExclusionReasons,
    ReplayInspectionSummary,
    ReplayKeySummary,
    ReplayRouteModelGroup,
)

runner = CliRunner()

_ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
TERM_ENV = {"COLUMNS": "220", "NO_COLOR": "1"}

KEY_A = uuid.UUID("11111111-1111-4111-8111-111111111111")
ROUTE_1 = uuid.UUID("99999999-0000-4000-8000-000000000001")
NOW = datetime(2026, 10, 28, 12, 0, 0, tzinfo=UTC)


def _plain(text: str) -> str:
    return " ".join(_ANSI_RE.sub("", text).split())


def _invoke(*args: Any, **kwargs: Any) -> Any:
    kwargs.setdefault("env", TERM_ENV)
    return runner.invoke(*args, **kwargs)


def _summary() -> ReplayInspectionSummary:
    key = ReplayKeySummary(
        key_id=KEY_A,
        key_status="active",
        references=2,
        active_references=1,
        expired_references=1,
        created_min=NOW,
        created_max=NOW,
        expiry_min=NOW,
        expiry_max=NOW,
    )
    return ReplayInspectionSummary(
        scope_text=f"key:{KEY_A}",
        now=NOW,
        configured_ttl_seconds=31_536_000,
        keys=1,
        keys_active_or_valid=1,
        references=2,
        active_references=1,
        expired_references=1,
        created_min=NOW,
        created_max=NOW,
        expiry_min=NOW,
        expiry_max=NOW,
        per_key=(key,),
        route_model_groups=(ReplayRouteModelGroup(ROUTE_1, "zap-it-1", 2),),
        route_model_groups_total=1,
        route_model_groups_truncated=False,
        reasons=ReplayExclusionReasons(0, 0, 0, 0, 0, 1),
        note="Expiry eligibility is maintenance state, not client or model readiness; replay use still requires the normal runtime authorization, route, and policy checks.",
    )


def _plan(**overrides: Any) -> ReplayExtendPlan:
    base: dict[str, Any] = dict(
        schema_version=1,
        operation="extend",
        scope=ReplayScope(key_id=KEY_A),
        created_from=None,
        created_until=None,
        ttl_seconds=31_536_000,
        configured_ttl_seconds=31_536_000,
        include_expired=False,
        previewed_at=NOW,
        selected_keys=1,
        eligible_references=2,
        exclusion_counts={
            "key_not_active_or_valid": 0,
            "ledger_not_finalized": 0,
            "unsupported_kind": 0,
            "hmac_version_unavailable": 0,
            "outside_lifetime": 0,
            "expired_not_included": 1,
        },
        old_expiry_min=NOW,
        old_expiry_max=NOW,
        new_expiry_min=NOW,
        new_expiry_max=NOW,
        expected_source_fingerprint="ab" * 32,
        expected_source_state_fingerprint="cd" * 32,
        expected_post_state_fingerprint="ef" * 32,
    )
    base.update(overrides)
    return ReplayExtendPlan(**base)


class FakeReplayService:
    def __init__(self) -> None:
        self.inspections: list[dict[str, Any]] = []
        self.previews: list[dict[str, Any]] = []
        self.applies: list[dict[str, Any]] = []
        self.summary = _summary()
        self.plan = _plan()
        self.error: Exception | None = None

    async def inspect_replay_references(self, *, scope, created_from, created_until, now=None):
        if self.error:
            raise self.error
        self.inspections.append(
            {"scope": scope, "created_from": created_from, "created_until": created_until}
        )
        return self.summary

    async def preview_replay_extend(
        self, *, scope, ttl_seconds, include_expired, created_from, created_until, now=None
    ):
        if self.error:
            raise self.error
        self.previews.append(
            {
                "scope": scope,
                "ttl_seconds": ttl_seconds,
                "include_expired": include_expired,
                "created_from": created_from,
                "created_until": created_until,
            }
        )
        import dataclasses

        return dataclasses.replace(
            self.plan,
            scope=scope,
            ttl_seconds=ttl_seconds if ttl_seconds is not None else self.plan.ttl_seconds,
            include_expired=include_expired,
            created_from=created_from,
            created_until=created_until,
        )

    async def apply_replay_extend(self, *, plan, reason, actor_admin_id, now=None):
        if self.error:
            raise self.error
        self.applies.append({"plan": plan, "reason": reason, "actor_admin_id": actor_admin_id})
        from slaif_gateway.services.codex_replay_maintenance import ReplayExtendResult

        return ReplayExtendResult(
            applied=True,
            already_applied=False,
            updated_references=plan.eligible_references,
            selected_keys=plan.selected_keys,
            eligible_references=plan.eligible_references,
            exclusion_counts=plan.exclusion_counts,
        )


@pytest.fixture()
def fake_service(monkeypatch) -> FakeReplayService:
    service = FakeReplayService()

    @asynccontextmanager
    async def _db() -> Any:
        yield "token", object()

    monkeypatch.setattr(codex_replay_cli, "cli_db_session", lambda: _db())
    monkeypatch.setattr(codex_replay_cli, "_service", lambda session: service)
    return service


class TestRegistration:
    def test_replay_subcommand_registers_inspect_and_extend(self) -> None:
        result = _invoke(app, ["codex", "replay", "--help"])
        assert result.exit_code == 0
        assert "inspect" in result.stdout
        assert "extend" in result.stdout


class TestInspect:
    def test_requires_exactly_one_scope(self, fake_service) -> None:
        result = _invoke(app, ["codex", "replay", "inspect"])
        assert result.exit_code == 2
        assert "Exactly one scope" in _plain(result.stderr)
        assert fake_service.inspections == []
        result = _invoke(
            app,
            ["codex", "replay", "inspect", "--key-id", str(KEY_A), "--all-active"],
        )
        assert result.exit_code == 2
        assert fake_service.inspections == []

    def test_scope_and_bounds_reach_service_and_json_is_safe(
        self, fake_service, tmp_path
    ) -> None:
        result = _invoke(
            app,
            [
                "codex", "replay", "inspect", "--key-id", str(KEY_A),
                "--created-from", "2026-01-01T00:00:00Z",
                "--created-until", "2026-10-01T00:00:00Z",
                "--json",
            ],
        )
        assert result.exit_code == 0, result.stderr
        assert len(fake_service.inspections) == 1
        call = fake_service.inspections[0]
        assert call["scope"].key_id == KEY_A
        assert call["created_from"] == datetime(2026, 1, 1, tzinfo=UTC)
        assert call["created_until"] == datetime(2026, 10, 1, tzinfo=UTC)
        payload = json.loads(result.stdout)
        assert payload["references"] == 2
        assert payload["active_references"] == 1
        assert payload["per_key"][0]["key_id"] == str(KEY_A)
        assert payload["route_model_groups"][0]["requested_model"] == "zap-it-1"
        assert payload["exclusion_reasons"]["expired_not_included"] == 1
        # No individual replay-row UUIDs, digests, or secrets.
        assert "deadbeef" not in result.stdout.lower()

    def test_non_utc_bound_refused(self, fake_service) -> None:
        result = _invoke(
            app,
            [
                "codex", "replay", "inspect", "--key-id", str(KEY_A),
                "--created-from", "2026-01-01T00:00:00",
            ],
        )
        assert result.exit_code == 2
        assert "UTC" in _plain(result.stderr)
        assert fake_service.inspections == []

    def test_text_output_is_bounded_and_safe(self, fake_service) -> None:
        result = _invoke(
            app,
            ["codex", "replay", "inspect", "--cohort-id", str(uuid.uuid4())],
        )
        assert result.exit_code == 0, result.stderr
        text = _plain(result.stdout)
        assert "References: 2 (1 active, 1 expired)" in text
        assert "Route" in text and "zap-it-1" in text
        assert "readiness" in text


class TestExtend:
    def test_mode_mutex(self, fake_service) -> None:
        result = _invoke(app, ["codex", "replay", "extend", "--key-id", str(KEY_A)])
        assert result.exit_code == 2
        assert "exactly one of" in _plain(result.stderr)
        result = _invoke(
            app,
            [
                "codex", "replay", "extend", "--key-id", str(KEY_A),
                "--output", "/tmp/x-plan.json", "--execute", "/tmp/x-plan.json",
            ],
        )
        assert result.exit_code == 2
        assert fake_service.previews == [] and fake_service.applies == []

    def test_ttl_range_refused(self, fake_service, tmp_path) -> None:
        for ttl in ("0", "31536001"):
            result = _invoke(
                app,
                [
                    "codex", "replay", "extend", "--key-id", str(KEY_A),
                    "--ttl-seconds", ttl, "--output", str(tmp_path / f"p{ttl}.json"),
                ],
            )
            assert result.exit_code == 2
            assert "1..31536000" in _plain(result.stderr)
        assert fake_service.previews == []

    def test_execute_requires_nonblank_reason(self, fake_service, tmp_path) -> None:
        plan_path = tmp_path / "p.json"
        plan_path.write_text(
            json.dumps(render_replay_extend_plan(_plan())), encoding="utf-8"
        )
        result = _invoke(
            app,
            ["codex", "replay", "extend", "--execute", str(plan_path)],
        )
        assert result.exit_code == 2
        assert "reason" in _plain(result.stderr)
        assert fake_service.applies == []

    def test_dry_run_writes_0600_plan_and_refuses_existing(
        self, fake_service, tmp_path
    ) -> None:
        plan_path = tmp_path / "plan.json"
        result = _invoke(
            app,
            [
                "codex", "replay", "extend", "--key-id", str(KEY_A),
                "--include-expired", "--output", str(plan_path), "--json",
            ],
        )
        assert result.exit_code == 0, result.stderr
        assert fake_service.previews[0]["include_expired"] is True
        mode = stat.S_IMODE(plan_path.stat().st_mode)
        assert mode == 0o600
        reparsed = parse_replay_extend_plan_file(plan_path)
        assert reparsed.scope.key_id == KEY_A
        assert reparsed.include_expired is True
        payload = json.loads(result.stdout)
        assert payload["mode"] == "dry-run"
        assert payload["ttl_is_configured_default"] is True
        # Reusing the same path must be refused (new file only).
        again = _invoke(
            app,
            [
                "codex", "replay", "extend", "--key-id", str(KEY_A),
                "--output", str(plan_path),
            ],
        )
        assert again.exit_code == 1
        assert "new writable file" in _plain(again.stderr)

    def test_explicit_ttl_shown_distinctly_from_configured(
        self, fake_service, tmp_path
    ) -> None:
        plan_path = tmp_path / "plan.json"
        result = _invoke(
            app,
            [
                "codex", "replay", "extend", "--key-id", str(KEY_A),
                "--ttl-seconds", "86400", "--output", str(plan_path), "--json",
            ],
        )
        assert result.exit_code == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["ttl_seconds"] == 86_400
        assert payload["configured_ttl_seconds"] == 31_536_000
        assert payload["ttl_is_configured_default"] is False

    def test_invalid_plan_files_refused_without_echo(self, fake_service, tmp_path) -> None:
        base = dict(render_replay_extend_plan(_plan()))
        canary = "sk-proj-abcdef1234567890abcdef1234567890"
        documents = {
            "unknown": json.dumps({**base, "surprise": 1}),
            "duplicate": json.dumps(base, sort_keys=False).replace(
                '"schema_version": 1,', '"schema_version": 1, "schema_version": 1,'
            ),
            "secret": json.dumps({**base, "scope": {"key_id": canary[:36]}}),
        }
        for name, document in documents.items():
            plan_path = tmp_path / f"{name}.json"
            plan_path.write_text(document, encoding="utf-8")
            result = _invoke(
                app,
                ["codex", "replay", "extend", "--execute", str(plan_path), "--reason", "r"],
            )
            assert result.exit_code == 2, (name, result.stderr)
            assert canary not in result.stdout
            assert canary not in result.stderr
            assert "sk-proj" not in _plain(result.stderr)
        # Oversize file (beyond the 32 KiB cap).
        big = tmp_path / "big.json"
        big.write_text("{\n" + '"pad": "x" * 0,\n' * 0 + '}' , encoding="utf-8")
        padded = json.dumps({**base, "pad": "x" * (33 * 1024)})
        big.write_text(padded, encoding="utf-8")
        result = _invoke(
            app,
            ["codex", "replay", "extend", "--execute", str(big), "--reason", "r"],
        )
        assert result.exit_code == 2
        assert fake_service.applies == []

    def test_execute_reaches_apply_with_reviewed_plan(
        self, fake_service, tmp_path
    ) -> None:
        plan_path = tmp_path / "plan.json"
        plan_path.write_text(
            json.dumps(render_replay_extend_plan(_plan())), encoding="utf-8"
        )
        result = _invoke(
            app,
            [
                "codex", "replay", "extend",
                "--execute", str(plan_path),
                "--reason", "resume long-running conversation",
                "--actor-admin-id", str(KEY_A),
                "--json",
            ],
        )
        assert result.exit_code == 0, result.stderr
        assert len(fake_service.applies) == 1
        call = fake_service.applies[0]
        assert call["plan"].scope.key_id == KEY_A
        assert call["reason"] == "resume long-running conversation"
        assert call["actor_admin_id"] == KEY_A
        payload = json.loads(result.stdout)
        assert payload["mode"] == "execute"
        assert payload["applied"] is True
        assert payload["updated_references"] == 2


class TestExecuteMixedModeRefusals:
    """200-c: --execute refuses every preview/edit flag BEFORE the plan
    is read or any database access (fixed no-echo message)."""

    @pytest.mark.parametrize(
        "flag_args",
        [
            ["--key-id", str(KEY_A)],
            ["--cohort-id", str(uuid.uuid4())],
            ["--all-active"],
            ["--ttl-seconds", "3600"],
            ["--include-expired"],
            ["--created-from", "2026-01-01T00:00:00Z"],
            ["--created-until", "2026-10-01T00:00:00Z"],
        ],
    )
    def test_execute_with_conflicting_flag_refused_before_plan_and_db(
        self, fake_service, tmp_path, flag_args
    ) -> None:
        missing = str(tmp_path / "absent-plan.json")
        result = _invoke(
            app,
            ["codex", "replay", "extend", "--execute", missing, "--reason", "x"]
            + flag_args,
        )
        assert result.exit_code == 2
        text = _plain(result.stderr)
        assert "reviewed plan file only" in text
        assert "absent-plan" not in text  # the plan path is never read
        assert fake_service.applies == []
        assert fake_service.previews == []

    def test_execute_mixed_refusal_does_not_echo_supplied_values(
        self, fake_service, tmp_path
    ) -> None:
        canary = "CanaryMixedMode200c"
        result = _invoke(
            app,
            [
                "codex", "replay", "extend", "--execute", str(tmp_path / "p.json"),
                "--reason", "r", "--created-from", canary,
            ],
        )
        assert result.exit_code == 2
        assert canary not in result.stdout
        assert canary not in result.stderr
        assert fake_service.applies == []


class TestExecuteRangeProvenance:
    """200-d: the execute JSON identifies the saved range/exclusion
    descriptors as reviewed-plan metadata, keeping them distinct from
    the operation-derived outcome fields."""

    def test_execute_json_labels_range_descriptors_as_reviewed_plan(
        self, fake_service, tmp_path
    ) -> None:
        plan_path = tmp_path / "plan.json"
        plan_path.write_text(
            json.dumps(render_replay_extend_plan(_plan())), encoding="utf-8"
        )
        result = _invoke(
            app,
            [
                "codex", "replay", "extend",
                "--execute", str(plan_path),
                "--reason", "resume long-running conversation",
                "--json",
            ],
        )
        assert result.exit_code == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["range_descriptors_source"] == "reviewed_plan"
        # The descriptors are the reviewed plan's own metadata...
        stamped = NOW.isoformat().replace("+00:00", "Z")
        assert payload["old_expiry_range"] == [stamped, stamped]
        assert payload["new_expiry_range"] == [stamped, stamped]
        assert payload["exclusion_counts"]["expired_not_included"] == 1
        # ...while the outcome fields stay operation-derived.
        assert payload["applied"] is True
        assert payload["already_applied"] is False
        assert payload["updated_references"] == 2
