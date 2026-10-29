"""CLI boundary unit evidence for 203-a (typed parsing, safe no-echo
errors, JSON/text formatting, runtime wiring) using a stubbed batch
runtime. Real Typer + real SQL evidence lives in
tests/integration/test_cli_key_batch_postgres.py.
"""

from __future__ import annotations

import json
import dataclasses
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from typer.testing import CliRunner

from slaif_gateway.cli.main import app as cli_app
from slaif_gateway.cli import key_batch as kb
from slaif_gateway.schemas.key_batch import (
    KeyBatchPlan,
    KeyBatchPlanKey,
    key_batch_document_changes,
    key_batch_state_fingerprint,
    parse_key_batch_plan_file,
)
from slaif_gateway.schemas.key_configuration import key_configuration_export
from slaif_gateway.services.key_batch_service import (
    APPLY_STATUS_APPLIED,
    KeyBatchApplyResult,
    _validate_apply_reason,
)

CANARY = "sk-slaif-canary203a00000000000"
# Recognized provider-key shape that the finite redaction patterns match in
# ANY surrounding context (used for the plan-artifact pathname guard).
PATH_CANARY = "sk-proj-canary203a0000000000000"
KID = str(uuid.UUID("33333333-3333-4333-8333-333333333333"))
OWNER = str(uuid.UUID("44444444-4444-4444-8444-444444444444"))

_runner = CliRunner()


def _plan() -> KeyBatchPlan:
    before = {"schema_version": 1, "request_limit_total": 100}
    after = {"schema_version": 1, "request_limit_total": 2000}
    context = dict(
        config_document=before,
        owner_id=uuid.UUID(OWNER),
        cohort_id=None,
        status="active",
        key_purpose="standard",
        valid_from=__import__("datetime").datetime(2026, 10, 29, tzinfo=__import__("datetime").UTC),
        valid_until=__import__("datetime").datetime(2026, 11, 28, tzinfo=__import__("datetime").UTC),
    )
    return KeyBatchPlan(
        schema_version=1,
        operation="apply",
        selection_kind="keys",
        cohort_id=None,
        key_ids=(KID,),
        statuses=("active",),
        policy={"schema_version": 1, "request_limit_total": 2000},
        keys=(
            KeyBatchPlanKey(
                key_id=KID,
                source_fingerprint=key_batch_state_fingerprint(**context),
                post_fingerprint=key_batch_state_fingerprint(
                    **{**context, "config_document": after}
                ),
                before=before,
                after=after,
                changes=key_batch_document_changes(before, after),
            ),
        ),
        selected_count=1,
        changed_count=1,
        unchanged_count=0,
        excluded_by_status=(),
        planned_at="2026-10-29T07:00:00+00:00",
    )


class _StubBatchService:
    def __init__(self) -> None:
        self.plan_calls: list[dict[str, object]] = []
        self.apply_calls: list[dict[str, object]] = []

    async def plan(self, *, cohort_id, key_ids, statuses, policy):
        self.plan_calls.append(
            {"cohort_id": cohort_id, "key_ids": key_ids, "statuses": statuses}
        )
        # Carry the ACTUAL parsed policy document into the returned plan
        # so the real writer gate (known-shape refusal) sees it exactly
        # as the shared service would project it.
        return dataclasses.replace(_plan(), policy=key_configuration_export(policy))

    async def apply(
        self,
        *,
        plan,
        reason,
        actor_admin_id=None,
        confirm_external_tool_fenced=False,
    ):
        # Apply the REAL shared reason law before recording the call,
        # exactly where the shared service enforces it (pre-effect).
        _validate_apply_reason(reason)
        self.apply_calls.append(
            {
                "plan": plan,
                "reason": reason,
                "actor": actor_admin_id,
                "confirm": bool(confirm_external_tool_fenced),
            }
        )
        return KeyBatchApplyResult(
            status=APPLY_STATUS_APPLIED,
            selected_count=1,
            changed_count=1,
            unchanged_count=0,
            key_ids=(KID,),
        )


@pytest.fixture()
def stub_runtime(monkeypatch: pytest.MonkeyPatch):
    stub = _StubBatchService()

    @asynccontextmanager
    async def _runtime():
        yield None, stub

    monkeypatch.setattr(kb, "_batch_runtime", _runtime)
    return stub


def _policy_file(tmp_path: Path) -> Path:
    p = tmp_path / "policy.json"
    p.write_text(json.dumps({"schema_version": 1, "request_limit_total": 2000}))
    return p


def test_commands_registered() -> None:
    res = _runner.invoke(cli_app, ["keys", "batch", "--help"])
    assert res.exit_code == 0
    assert "plan" in res.output and "apply" in res.output


def test_plan_selection_and_input_errors_no_echo(tmp_path: Path) -> None:
    policy = _policy_file(tmp_path)
    cases = [
        # both selection sources
        ["--cohort-id", OWNER, "--key-id", KID],
        # no selection source
        [],
        # malformed uuid
        ["--key-id", "not-a-uuid"],
        # duplicate key id
        ["--key-id", KID, "--key-id", KID],
        # invalid status (never echoed)
        ["--key-id", KID, "--status", "expired"],
        # missing policy file
        ["--key-id", KID],
        # missing plan file
        ["--key-id", KID, "--policy-file", str(policy)],
    ]
    for args in cases:
        res = _runner.invoke(
            cli_app,
            ["keys", "batch", "plan", *args, "--plan-file", str(tmp_path / "p.json"), "--json"],
        )
        assert res.exit_code == 1, (args, res.output)
        payload = json.loads(res.output)
        assert "error" in payload
        assert CANARY not in res.output


def test_plan_over_cap_refused_safely(tmp_path: Path) -> None:
    policy = _policy_file(tmp_path)
    args = []
    for i in range(1001):
        args += ["--key-id", str(uuid.uuid4())]
    res = _runner.invoke(
        cli_app,
        ["keys", "batch", "plan", *args, "--policy-file", str(policy),
         "--plan-file", str(tmp_path / "p.json"), "--json"],
    )
    assert res.exit_code == 1
    assert "1000" in res.output


def test_plan_credential_canary_never_echoed(tmp_path: Path, stub_runtime) -> None:
    policy = tmp_path / "canary.json"
    policy.write_text(json.dumps({"schema_version": 1, "allowed_models": [CANARY]}))
    res = _runner.invoke(
        cli_app,
        ["keys", "batch", "plan", "--cohort-id", OWNER,
         "--policy-file", str(policy), "--plan-file", str(tmp_path / "p.json"), "--json"],
    )
    assert res.exit_code == 1
    assert CANARY not in res.output
    assert CANARY not in (res.output if res.output else "")


def test_plan_happy_path_json_and_file(tmp_path: Path, stub_runtime) -> None:
    policy = _policy_file(tmp_path)
    plan_file = tmp_path / "plan.json"
    res = _runner.invoke(
        cli_app,
        ["keys", "batch", "plan", "--key-id", KID,
         "--policy-file", str(policy), "--plan-file", str(plan_file), "--json"],
    )
    assert res.exit_code == 0, res.output
    payload = json.loads(res.output)
    assert payload["plan_file"] == str(plan_file)
    assert payload["plan"]["key_ids"] == [KID]
    assert payload["plan"]["selected_count"] == 1
    assert plan_file.exists()
    # The written file is a parseable strict plan at 0600.
    written = parse_key_batch_plan_file(plan_file)
    assert written.key_ids == (KID,)
    assert stub_runtime.plan_calls[0]["key_ids"] == (uuid.UUID(KID),)
    assert stub_runtime.plan_calls[0]["statuses"] == ("active",)


def test_plan_text_summary_bounded(tmp_path: Path, stub_runtime) -> None:
    policy = _policy_file(tmp_path)
    res = _runner.invoke(
        cli_app,
        ["keys", "batch", "plan", "--key-id", KID,
         "--policy-file", str(policy), "--plan-file", str(tmp_path / "p.json")],
    )
    assert res.exit_code == 0, res.output
    assert "selected: 1" in res.output
    assert "changed: 1" in res.output
    assert "request_limit_total" in res.output
    assert "token_hash" not in res.output


def test_apply_reason_actor_and_json(tmp_path: Path, stub_runtime) -> None:
    plan_file = tmp_path / "plan.json"
    from slaif_gateway.schemas.key_batch import write_key_batch_plan_file

    write_key_batch_plan_file(plan_file, _plan())
    actor = str(uuid.uuid4())
    res = _runner.invoke(
        cli_app,
        ["keys", "batch", "apply", "--plan-file", str(plan_file),
         "--reason", "batch window", "--actor-admin-id", actor, "--json"],
    )
    assert res.exit_code == 0, res.output
    payload = json.loads(res.output)
    assert payload["status"] == "applied"
    assert payload["key_ids"] == [KID]
    call = stub_runtime.apply_calls[0]
    assert call["reason"] == "batch window"
    assert call["actor"] == uuid.UUID(actor)


def test_apply_missing_inputs_and_bad_actor(tmp_path: Path, stub_runtime) -> None:
    plan_file = tmp_path / "plan.json"
    from slaif_gateway.schemas.key_batch import write_key_batch_plan_file

    write_key_batch_plan_file(plan_file, _plan())
    res = _runner.invoke(
        cli_app, ["keys", "batch", "apply", "--plan-file", str(plan_file), "--json"]
    )
    assert res.exit_code == 1
    assert "--reason" in res.output
    res = _runner.invoke(
        cli_app,
        ["keys", "batch", "apply", "--plan-file", str(plan_file),
         "--reason", "r", "--actor-admin-id", "nope", "--json"],
    )
    assert res.exit_code == 1
    payload = json.loads(res.output)
    assert payload["error"]["code"] == "invalid_parameter"


def test_apply_credential_reason_refused_no_echo(tmp_path: Path, stub_runtime) -> None:
    plan_file = tmp_path / "plan.json"
    from slaif_gateway.schemas.key_batch import write_key_batch_plan_file

    write_key_batch_plan_file(plan_file, _plan())
    res = _runner.invoke(
        cli_app,
        ["keys", "batch", "apply", "--plan-file", str(plan_file),
         "--reason", f"rotate {CANARY} now", "--json"],
    )
    assert res.exit_code == 1
    assert CANARY not in res.output
    assert stub_runtime.apply_calls == []


def test_database_not_configured(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    policy = _policy_file(tmp_path)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    from slaif_gateway.config import get_settings

    get_settings.cache_clear()
    try:
        res = _runner.invoke(
            cli_app,
            ["keys", "batch", "plan", "--cohort-id", OWNER,
             "--policy-file", str(policy),
             "--plan-file", str(tmp_path / "plan.json"), "--json"],
        )
        assert res.exit_code == 1
        payload = json.loads(res.output)
        assert payload["error"]["code"] == "database_not_configured"
    finally:
        get_settings.cache_clear()


def test_apply_fresh_fenced_confirmation_flag_passthrough(
    tmp_path: Path, stub_runtime
) -> None:
    plan_file = tmp_path / "plan.json"
    from slaif_gateway.schemas.key_batch import write_key_batch_plan_file

    write_key_batch_plan_file(plan_file, _plan())
    # No fresh flag: the service receives the explicit False default.
    res = _runner.invoke(
        cli_app,
        ["keys", "batch", "apply", "--plan-file", str(plan_file),
         "--reason", "fenced batch", "--json"],
    )
    assert res.exit_code == 0, res.output
    assert stub_runtime.apply_calls[0]["confirm"] is False
    # Fresh explicit flag: the service receives True.
    res = _runner.invoke(
        cli_app,
        ["keys", "batch", "apply", "--plan-file", str(plan_file),
         "--reason", "fenced batch", "--confirm-external-tool-fenced", "--json"],
    )
    assert res.exit_code == 0, res.output
    assert stub_runtime.apply_calls[1]["confirm"] is True
    help_res = _runner.invoke(cli_app, ["keys", "batch", "apply", "--help"])
    assert help_res.exit_code == 0
    assert "--confirm-external-tool-fenced" in help_res.output


def test_plan_path_credential_shape_refused_no_echo(
    tmp_path: Path, stub_runtime
) -> None:
    policy = _policy_file(tmp_path)
    bad_name = f"{PATH_CANARY}.json"
    for extra in ([], ["--json"]):
        res = _runner.invoke(
            cli_app,
            ["keys", "batch", "plan", "--key-id", KID,
             "--policy-file", str(policy),
             "--plan-file", str(tmp_path / bad_name), *extra],
        )
        assert res.exit_code == 1, (res.output, res.stderr)
        # The matched shape is never echoed in stdout OR stderr.
        assert PATH_CANARY not in res.output
        assert PATH_CANARY not in res.stderr
        assert PATH_CANARY not in (res.stderr or "")
        if extra:
            payload = json.loads(res.output)
            assert payload["error"]["code"] == "invalid_parameter"
        # No artifact is created at the refused pathname.
        assert not (tmp_path / bad_name).exists()
