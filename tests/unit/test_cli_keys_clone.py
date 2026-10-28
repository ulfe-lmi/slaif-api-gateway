"""Actual-Typer unit tests for `keys clone` (objective 198).

The DB-touching helpers are faked; the real command wiring (flag
validation, plan-file IO, channel selection, output shapes) is exercised.
"""

from __future__ import annotations

import json
import os
import stat
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
import typer
from typer.testing import CliRunner

from slaif_gateway.cli import keys as keys_cli
from slaif_gateway.cli.common import CliSecretFileError
from slaif_gateway.cli.main import app
from slaif_gateway.schemas.key_clone import parse_clone_plan_file
from slaif_gateway.services.email_delivery_service import PendingKeyEmailResult

runner = CliRunner()

OPERATION_UUID = uuid.UUID("0f341c8a-1234-5678-9abc-def012345678")
SOURCE_KEY_ID = uuid.UUID("11111111-1111-4111-8111-111111111111")
TARGET_OWNER_ID = uuid.UUID("33333333-3333-4333-8333-333333333333")
TARGET_KEY_ID = uuid.UUID("66666666-6666-4666-8666-666666666666")
ONE_TIME_SECRET_ID = uuid.UUID("77777777-7777-4777-8777-777777777777")
EMAIL_DELIVERY_ID = uuid.UUID("88888888-8888-4888-8888-888888888888")
ADMIN_ID = uuid.UUID("55555555-5555-4555-8555-555555555555")

PLAINTEXT_KEY = "sk-slaif-clonepub.clone-once-only-secret-material"
FINGERPRINT = "ab" * 32


def _plan_document() -> dict[str, object]:
    return {
        "schema_version": 1,
        "operation_uuid": str(OPERATION_UUID),
        "source_gateway_key_id": str(SOURCE_KEY_ID),
        "source_public_key_id": "pub-source",
        "source_fingerprint": FINGERPRINT,
        "target_owner_id": str(TARGET_OWNER_ID),
        "target_cohort_id": None,
        "validity": {"mode": "duration-from-now", "duration_seconds": 3600},
        "policy": {
            "schema_version": 1,
            "allowed_models": ["gpt-test-mini"],
            "allow_all_models": False,
            "allowed_endpoints": ["/v1/chat/completions"],
            "allow_all_endpoints": False,
        },
        "requires_fenced_confirmation": False,
        "preview": {
            "valid_from": "2026-10-28T12:00:00+00:00",
            "valid_until": "2026-10-28T13:00:00+00:00",
            "note": "Preview only.",
        },
    }


def _created_result(**overrides) -> keys_cli.KeyCloneResult:
    kwargs = dict(
        status="created",
        operation_uuid=str(OPERATION_UUID),
        source_gateway_key_id=str(SOURCE_KEY_ID),
        source_fingerprint=FINGERPRINT,
        requires_fenced_confirmation=False,
        target_gateway_key_id=str(TARGET_KEY_ID),
        target_public_key_id="pub-target",
        one_time_secret_id=str(ONE_TIME_SECRET_ID),
        email_delivery_id=str(EMAIL_DELIVERY_ID),
        valid_from=datetime(2026, 10, 28, 12, 0, tzinfo=UTC),
        valid_until=datetime(2026, 10, 28, 13, 0, tzinfo=UTC),
        plaintext_key=PLAINTEXT_KEY,
    )
    kwargs.update(overrides)
    return keys_cli.KeyCloneResult(**kwargs)


def _delivery(status: str = "pending") -> PendingKeyEmailResult:
    return PendingKeyEmailResult(
        email_delivery_id=EMAIL_DELIVERY_ID,
        one_time_secret_id=ONE_TIME_SECRET_ID,
        gateway_key_id=TARGET_KEY_ID,
        owner_id=TARGET_OWNER_ID,
        recipient_email="owner@example.invalid",
        status=status,
    )


class _FakeBuild:
    def __init__(self, document=None):
        self.document = document if document is not None else _plan_document()
        self.calls: list[dict[str, object]] = []

    async def __call__(self, **kwargs):
        self.calls.append(kwargs)
        return self.document


class _FakeExecute:
    def __init__(self, result=None, error: Exception | None = None):
        self.result = result if result is not None else _created_result()
        self.error = error
        self.calls: list[dict[str, object]] = []

    async def __call__(self, plan, **kwargs):
        self.calls.append(dict(plan=plan, **kwargs))
        if self.error is not None:
            raise self.error
        return self.result


def _dry_run_args(plan_path: Path, *extra: str) -> list[str]:
    return [
        "keys",
        "clone",
        "--dry-run",
        str(plan_path),
        "--source-key-id",
        str(SOURCE_KEY_ID),
        "--target-owner-id",
        str(TARGET_OWNER_ID),
        "--validity-mode",
        "duration-from-now",
        "--validity-duration-seconds",
        "3600",
        *extra,
    ]


# --- flag / mode validation ----------------------------------------------------


def test_clone_requires_exactly_one_of_dry_run_or_execute(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "keys",
            "clone",
            "--source-key-id",
            str(SOURCE_KEY_ID),
            "--target-owner-id",
            str(TARGET_OWNER_ID),
            "--validity-mode",
            "duration-from-now",
        ],
    )
    assert result.exit_code == 1
    assert "exactly one of --dry-run PATH or --execute PATH" in result.stderr

    both = _dry_run_args(tmp_path / "a.json", "--execute", str(tmp_path / "b.json"))
    result = runner.invoke(app, both)
    assert result.exit_code == 1
    assert "exactly one of --dry-run PATH or --execute PATH" in result.stderr


def test_clone_dry_run_requires_source_owner_and_mode(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "keys",
            "clone",
            "--dry-run",
            str(tmp_path / "a.json"),
            "--target-owner-id",
            str(TARGET_OWNER_ID),
            "--validity-mode",
            "duration-from-now",
        ],
    )
    assert result.exit_code == 1
    assert "--source-key-id is required" in result.stderr

    result = runner.invoke(
        app,
        [
            "keys",
            "clone",
            "--dry-run",
            str(tmp_path / "a.json"),
            "--source-key-id",
            str(SOURCE_KEY_ID),
            "--target-owner-id",
            str(TARGET_OWNER_ID),
        ],
    )
    assert result.exit_code == 1
    assert "--validity-mode is required" in result.stderr


def test_clone_dry_run_mode_consistency(tmp_path: Path) -> None:
    base = _dry_run_args(tmp_path / "a.json")

    result = runner.invoke(
        app, base[:-2] + ["--validity-mode", "bogus"]
    )
    assert result.exit_code == 1
    assert "must be copy-source-expiry" in result.stderr

    result = runner.invoke(
        app,
        [
            "keys",
            "clone",
            "--dry-run",
            str(tmp_path / "a.json"),
            "--source-key-id",
            str(SOURCE_KEY_ID),
            "--target-owner-id",
            str(TARGET_OWNER_ID),
            "--validity-mode",
            "duration-from-now",
        ],
    )
    assert result.exit_code == 1
    assert "--validity-duration-seconds must be positive" in result.stderr

    result = runner.invoke(
        app,
        [
            "keys",
            "clone",
            "--dry-run",
            str(tmp_path / "a.json"),
            "--source-key-id",
            str(SOURCE_KEY_ID),
            "--target-owner-id",
            str(TARGET_OWNER_ID),
            "--validity-mode",
            "absolute",
            "--valid-until",
            "2026-12-01T00:00:00+00:00",
        ],
    )
    assert result.exit_code == 1
    assert "--valid-from and --valid-until are required" in result.stderr

    result = runner.invoke(
        app,
        [
            "keys",
            "clone",
            "--dry-run",
            str(tmp_path / "a.json"),
            "--source-key-id",
            str(SOURCE_KEY_ID),
            "--target-owner-id",
            str(TARGET_OWNER_ID),
            "--validity-mode",
            "copy-source-expiry",
            "--validity-duration-seconds",
            "60",
        ],
    )
    assert result.exit_code == 1
    assert "copy-source-expiry accepts no duration" in result.stderr


# --- dry-run --------------------------------------------------------------------


def test_clone_dry_run_writes_plan_file_and_json_matches_file(tmp_path: Path, monkeypatch) -> None:
    fake_build = _FakeBuild()
    monkeypatch.setattr(keys_cli, "_build_clone_plan_document", fake_build)
    plan_path = tmp_path / "plan.json"

    result = runner.invoke(app, _dry_run_args(plan_path, "--json"))
    assert result.exit_code == 0, result.stderr

    assert plan_path.exists()
    mode = stat.S_IMODE(os.stat(plan_path).st_mode)
    assert mode == 0o600
    file_bytes = plan_path.read_bytes()
    stdout_doc = json.loads(result.stdout)
    file_doc = json.loads(file_bytes)
    assert stdout_doc == file_doc
    # The emitted document re-parses with the same strict schema.
    assert parse_clone_plan_file(file_bytes).operation_uuid == str(OPERATION_UUID)
    assert PLAINTEXT_KEY not in result.stdout

    # UUIDs were parsed, not passed as strings, into the service.
    call = fake_build.calls[0]
    assert call["source_gateway_key_id"] == SOURCE_KEY_ID
    assert call["target_owner_id"] == TARGET_OWNER_ID
    assert call["validity_mode"] == "duration-from-now"
    assert call["validity_duration_seconds"] == 3600


def test_clone_dry_run_refuses_overwrite(tmp_path: Path, monkeypatch) -> None:
    fake_build = _FakeBuild()
    monkeypatch.setattr(keys_cli, "_build_clone_plan_document", fake_build)
    plan_path = tmp_path / "plan.json"

    result = runner.invoke(app, _dry_run_args(plan_path))
    assert result.exit_code == 0, result.stderr
    result = runner.invoke(app, _dry_run_args(plan_path))
    assert result.exit_code == 1
    assert "Clone plan file already exists" in result.stderr


def test_clone_dry_run_text_output_is_safe(tmp_path: Path, monkeypatch) -> None:
    fake_build = _FakeBuild()
    monkeypatch.setattr(keys_cli, "_build_clone_plan_document", fake_build)
    plan_path = tmp_path / "plan.json"

    result = runner.invoke(app, _dry_run_args(plan_path))
    assert result.exit_code == 0, result.stderr
    assert "planned" in result.stdout
    assert str(OPERATION_UUID) in result.stdout
    assert str(plan_path) in result.stdout
    # The full policy document stays in the file, not in the text summary.
    assert "gpt-test-mini" not in result.stdout
    assert PLAINTEXT_KEY not in result.stdout


def test_clone_dry_run_service_error_is_safe(tmp_path: Path, monkeypatch) -> None:
    from slaif_gateway.services.key_clone_service import KeyCloneTargetMissingError

    async def _raising(**kwargs):
        raise KeyCloneTargetMissingError(param="target_owner_id")

    monkeypatch.setattr(keys_cli, "_build_clone_plan_document", _raising)
    result = runner.invoke(app, _dry_run_args(tmp_path / "plan.json", "--json"))
    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["error"]["code"] == "key_clone_target_missing"
    assert str(TARGET_OWNER_ID) not in result.stdout


# --- execute: channel validation ------------------------------------------------


def _execute_args(plan_path: Path, *extra: str) -> list[str]:
    return [
        "keys",
        "clone",
        "--execute",
        str(plan_path),
        "--reason",
        "clone for unit test",
        *extra,
    ]


def _write_plan_file(tmp_path: Path, document: dict[str, object] | None = None) -> Path:
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(
        json.dumps(document if document is not None else _plan_document(), indent=2)
        + "\n",
        encoding="utf-8",
    )
    return plan_path


def test_clone_execute_requires_reason(tmp_path: Path, monkeypatch) -> None:
    fake_execute = _FakeExecute()
    monkeypatch.setattr(keys_cli, "_execute_clone_plan", fake_execute)
    plan_path = _write_plan_file(tmp_path)
    result = runner.invoke(app, ["keys", "clone", "--execute", str(plan_path)])
    assert result.exit_code == 1
    assert "--reason is required" in result.stderr
    assert fake_execute.calls == []


def test_clone_execute_requires_exactly_one_channel(tmp_path: Path, monkeypatch) -> None:
    fake_execute = _FakeExecute()
    monkeypatch.setattr(keys_cli, "_execute_clone_plan", fake_execute)
    plan_path = _write_plan_file(tmp_path)

    result = runner.invoke(app, _execute_args(plan_path))
    assert result.exit_code == 1
    assert "exactly one explicit one-time key channel" in result.stderr
    assert fake_execute.calls == []

    result = runner.invoke(
        app,
        _execute_args(plan_path, "--show-plaintext", "--secret-output-file", str(tmp_path / "s")),
    )
    assert result.exit_code == 1
    assert fake_execute.calls == []

    result = runner.invoke(
        app,
        _execute_args(plan_path, "--show-plaintext", "--email-delivery", "pending"),
    )
    assert result.exit_code == 1
    assert fake_execute.calls == []


# --- execute: output channels ----------------------------------------------------


def test_clone_execute_show_plaintext_json(tmp_path: Path, monkeypatch) -> None:
    fake_execute = _FakeExecute()
    monkeypatch.setattr(keys_cli, "_execute_clone_plan", fake_execute)
    plan_path = _write_plan_file(tmp_path)

    result = runner.invoke(app, _execute_args(plan_path, "--show-plaintext", "--json"))
    assert result.exit_code == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "created"
    assert payload["target_gateway_key_id"] == str(TARGET_KEY_ID)
    assert payload["plaintext_key"] == PLAINTEXT_KEY
    assert result.stdout.count(PLAINTEXT_KEY) == 1
    assert "Warning: plaintext key is shown once" in result.stderr

    call = fake_execute.calls[0]
    assert call["reason"] == "clone for unit test"
    assert call["confirm_external_tool_fenced"] is False
    assert call["email_delivery_mode"] is keys_cli.EmailDeliveryMode.none


def test_clone_execute_secret_output_file(tmp_path: Path, monkeypatch) -> None:
    fake_execute = _FakeExecute()
    monkeypatch.setattr(keys_cli, "_execute_clone_plan", fake_execute)
    plan_path = _write_plan_file(tmp_path)
    secret_path = tmp_path / "key.secret"

    result = runner.invoke(app, _execute_args(plan_path, "--secret-output-file", str(secret_path)))
    assert result.exit_code == 0, result.stderr
    assert secret_path.exists()
    assert stat.S_IMODE(os.stat(secret_path).st_mode) == 0o600
    assert secret_path.read_text(encoding="utf-8") == f"{PLAINTEXT_KEY}\n"
    assert PLAINTEXT_KEY not in result.stdout


def test_clone_execute_fresh_secret_output_file_existing_commits_then_recovers(
    tmp_path: Path, monkeypatch
) -> None:
    fake_execute = _FakeExecute()  # a FRESH operation (status "created")
    monkeypatch.setattr(keys_cli, "_execute_clone_plan", fake_execute)
    plan_path = _write_plan_file(tmp_path)
    secret_path = tmp_path / "key.secret"
    secret_path.write_text("existing", encoding="utf-8")

    result = runner.invoke(
        app, _execute_args(plan_path, "--secret-output-file", str(secret_path), "--json")
    )
    # A fresh operation committed (one key created); the exclusive 0600 write
    # then failed, so it exits nonzero with safe recovery and NEVER clobbers
    # the pre-existing file.
    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["status"] == "created"
    assert payload["target_gateway_key_id"] == str(TARGET_KEY_ID)
    assert "recovery" in payload
    assert payload["recovery"]["plaintext_recoverable"] is False
    assert "plaintext_key" not in payload
    assert secret_path.read_text(encoding="utf-8") == "existing"


def test_clone_execute_exact_repeat_reaches_dedup_with_existing_file(
    tmp_path: Path, monkeypatch
) -> None:
    fake_execute = _FakeExecute(
        result=_created_result(status="already-applied", plaintext_key=None)
    )
    monkeypatch.setattr(keys_cli, "_execute_clone_plan", fake_execute)
    plan_path = _write_plan_file(tmp_path)
    secret_path = tmp_path / "key.secret"
    secret_path.write_text("existing", encoding="utf-8")

    result = runner.invoke(
        app, _execute_args(plan_path, "--secret-output-file", str(secret_path), "--json")
    )
    # The exact repeat reaches dedup (already-applied), returns the safe
    # original IDs, and does NOT write/retrieve plaintext or clobber the file.
    assert result.exit_code == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "already-applied"
    assert payload["target_gateway_key_id"] == str(TARGET_KEY_ID)
    assert "plaintext_key" not in payload
    assert secret_path.read_text(encoding="utf-8") == "existing"


def test_clone_execute_email_pending_keeps_safe_output(tmp_path: Path, monkeypatch) -> None:
    fake_execute = _FakeExecute()
    monkeypatch.setattr(keys_cli, "_execute_clone_plan", fake_execute)
    plan_path = _write_plan_file(tmp_path)

    result = runner.invoke(app, _execute_args(plan_path, "--email-delivery", "pending", "--json"))
    assert result.exit_code == 0, result.stderr
    payload = json.loads(result.stdout)
    assert "plaintext_key" not in payload
    assert payload["email_delivery_id"] == str(EMAIL_DELIVERY_ID)
    assert "send-pending-key" in result.stderr
    assert fake_execute.calls[0]["email_delivery_mode"] is keys_cli.EmailDeliveryMode.pending


def test_clone_execute_email_send_now(tmp_path: Path, monkeypatch) -> None:
    fake_execute = _FakeExecute()
    monkeypatch.setattr(keys_cli, "_execute_clone_plan", fake_execute)

    seen: dict[str, object] = {}

    async def fake_send_now(**kwargs):
        seen.update(kwargs)
        return _delivery(status="sent")

    monkeypatch.setattr(keys_cli, "_send_pending_key_email_now", fake_send_now)
    plan_path = _write_plan_file(tmp_path)

    result = runner.invoke(app, _execute_args(plan_path, "--email-delivery", "send-now", "--json"))
    assert result.exit_code == 0, result.stderr
    payload = json.loads(result.stdout)
    assert "plaintext_key" not in payload
    assert payload["email_delivery_status"] == "sent"
    assert seen["one_time_secret_id"] == ONE_TIME_SECRET_ID
    assert seen["email_delivery_id"] == EMAIL_DELIVERY_ID


def test_clone_execute_email_enqueue_reports_task(tmp_path: Path, monkeypatch) -> None:
    fake_execute = _FakeExecute()
    monkeypatch.setattr(keys_cli, "_execute_clone_plan", fake_execute)

    def fake_enqueue(**kwargs):
        return "celery-task-123"

    monkeypatch.setattr(keys_cli, "_enqueue_pending_key_email", fake_enqueue)
    plan_path = _write_plan_file(tmp_path)

    result = runner.invoke(app, _execute_args(plan_path, "--email-delivery", "enqueue", "--json"))
    assert result.exit_code == 0, result.stderr
    payload = json.loads(result.stdout)
    assert "plaintext_key" not in payload
    assert payload["celery_task_id"] == "celery-task-123"
    assert payload["email_delivery_status"] == "queued"


def test_clone_execute_send_now_failure_exits_nonzero(tmp_path: Path, monkeypatch) -> None:
    fake_execute = _FakeExecute()
    monkeypatch.setattr(keys_cli, "_execute_clone_plan", fake_execute)

    async def fake_send_now(**kwargs):
        return _delivery(status="failed")

    monkeypatch.setattr(keys_cli, "_send_pending_key_email_now", fake_send_now)
    plan_path = _write_plan_file(tmp_path)

    result = runner.invoke(app, _execute_args(plan_path, "--email-delivery", "send-now", "--json"))
    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["status"] == "created"
    assert payload["email_delivery_status"] == "failed"
    assert "plaintext_key" not in payload


def test_clone_execute_already_applied_never_plaintext(tmp_path: Path, monkeypatch) -> None:
    applied = _created_result(
        status="already-applied",
        plaintext_key=None,
        valid_from=None,
        valid_until=None,
    )
    fake_execute = _FakeExecute(result=applied)
    monkeypatch.setattr(keys_cli, "_execute_clone_plan", fake_execute)
    plan_path = _write_plan_file(tmp_path)

    result = runner.invoke(app, _execute_args(plan_path, "--show-plaintext", "--json"))
    assert result.exit_code == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "already-applied"
    assert "plaintext_key" not in payload
    assert PLAINTEXT_KEY not in result.stdout
    assert "already completed" in result.stderr


def test_clone_execute_missing_plan_file(tmp_path: Path, monkeypatch) -> None:
    fake_execute = _FakeExecute()
    monkeypatch.setattr(keys_cli, "_execute_clone_plan", fake_execute)
    result = runner.invoke(
        app, _execute_args(tmp_path / "does-not-exist.json", "--show-plaintext")
    )
    assert result.exit_code == 1
    assert "Clone plan file is missing or unreadable" in result.stderr
    assert str(tmp_path / "does-not-exist.json") not in result.stderr
    assert fake_execute.calls == []


def test_clone_execute_tampered_plan_rejected_without_db(tmp_path: Path, monkeypatch) -> None:
    fake_execute = _FakeExecute()
    monkeypatch.setattr(keys_cli, "_execute_clone_plan", fake_execute)
    document = _plan_document()
    document["bogus_field"] = 1
    plan_path = _write_plan_file(tmp_path, document)

    result = runner.invoke(app, _execute_args(plan_path, "--show-plaintext", "--json"))
    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert "unsupported fields" in payload["error"]["message"]
    assert fake_execute.calls == []


def test_clone_execute_post_commit_output_failure_is_safe_and_nonzero(
    tmp_path: Path, monkeypatch
) -> None:
    fake_execute = _FakeExecute()
    monkeypatch.setattr(keys_cli, "_execute_clone_plan", fake_execute)

    def failing_write(path, secret):
        raise CliSecretFileError("Could not create secret output file: permission denied")

    monkeypatch.setattr(keys_cli, "write_secret_file", failing_write)
    plan_path = _write_plan_file(tmp_path)

    result = runner.invoke(
        app,
        _execute_args(plan_path, "--secret-output-file", str(tmp_path / "key.secret"), "--json"),
    )
    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["status"] == "created"
    assert payload["target_gateway_key_id"] == str(TARGET_KEY_ID)
    assert payload["one_time_secret_id"] == str(ONE_TIME_SECRET_ID)
    assert payload["recovery"]["plaintext_recoverable"] is False
    assert "send-pending-key" in payload["recovery"]["guidance"]
    assert PLAINTEXT_KEY not in result.stdout
    # Never silently cloned again.
    assert len(fake_execute.calls) == 1


def test_clone_execute_confirm_flag_passes_through(tmp_path: Path, monkeypatch) -> None:
    fake_execute = _FakeExecute()
    monkeypatch.setattr(keys_cli, "_execute_clone_plan", fake_execute)
    plan_path = _write_plan_file(tmp_path)

    result = runner.invoke(
        app,
        _execute_args(plan_path, "--show-plaintext", "--confirm-external-tool-fenced",
                      "--actor-admin-id", str(ADMIN_ID)),
    )
    assert result.exit_code == 0, result.stderr
    call = fake_execute.calls[0]
    assert call["confirm_external_tool_fenced"] is True
    assert call["actor_admin_id"] == ADMIN_ID


# --- 198-b: mixed modes, bounded input, safe errors, post-commit recovery ------


def test_clone_execute_refuses_dry_run_only_flags(tmp_path: Path, monkeypatch) -> None:
    fake_execute = _FakeExecute()
    monkeypatch.setattr(keys_cli, "_execute_clone_plan", fake_execute)
    plan_path = _write_plan_file(tmp_path)
    result = runner.invoke(
        app,
        _execute_args(
            plan_path, "--target-owner-id", str(TARGET_OWNER_ID), "--show-plaintext"
        ),
    )
    assert result.exit_code == 1
    assert "reads source/target/validity from the plan file" in result.stderr
    assert fake_execute.calls == []


def test_clone_dry_run_refuses_execute_only_options(tmp_path: Path, monkeypatch) -> None:
    fake_build = _FakeBuild()
    monkeypatch.setattr(keys_cli, "_build_clone_plan_document", fake_build)

    result = runner.invoke(app, _dry_run_args(tmp_path / "a.json", "--show-plaintext"))
    assert result.exit_code == 1
    assert "--show-plaintext is execute-only" in result.stderr
    assert fake_build.calls == []

    result = runner.invoke(
        app, _dry_run_args(tmp_path / "b.json", "--email-delivery", "pending")
    )
    assert result.exit_code == 1
    assert "--email-delivery is execute-only" in result.stderr
    assert fake_build.calls == []


def test_clone_bounded_plan_read_limits_bytes(tmp_path: Path) -> None:
    import io

    cap = 128 * 1024
    inner = io.BytesIO(b" " * (cap + 50))
    requested: list[int] = []

    class _CountingFile:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self, n: int = -1) -> bytes:
            requested.append(n)
            return inner.read(n)

    class _CountingPath:
        def open(self, *a, **k):
            return _CountingFile()

    with pytest.raises(typer.BadParameter) as excinfo:
        keys_cli._read_bounded_plan_file(_CountingPath())  # type: ignore[arg-type]
    # The oversized refusal is the EXPECTED fixed safe error (no path or
    # body echo), not a swallowed exception.
    assert "exceeds the bounded size" in str(excinfo.value)
    assert str(tmp_path) not in str(excinfo.value)
    # The read is bounded to cap+1 (never the whole file).
    assert requested == [cap + 1]


def test_clone_execute_refuses_oversized_plan_before_db(tmp_path: Path, monkeypatch) -> None:
    fake_execute = _FakeExecute()
    monkeypatch.setattr(keys_cli, "_execute_clone_plan", fake_execute)
    plan_path = tmp_path / "big.json"
    plan_path.write_bytes(b"{" + b" " * (140 * 1024) + b"}")
    result = runner.invoke(
        app, _execute_args(plan_path, "--show-plaintext")
    )
    assert result.exit_code == 1
    assert "exceeds the bounded size" in result.stderr
    assert fake_execute.calls == []


def test_clone_dry_run_overwrite_error_does_not_echo_path(
    tmp_path: Path, monkeypatch
) -> None:
    fake_build = _FakeBuild()
    monkeypatch.setattr(keys_cli, "_build_clone_plan_document", fake_build)
    plan_path = tmp_path / "plan.json"
    runner.invoke(app, _dry_run_args(plan_path))
    result = runner.invoke(app, _dry_run_args(plan_path))
    assert result.exit_code == 1
    assert "Clone plan file already exists" in result.stderr
    assert str(plan_path) not in result.stderr


def test_clone_execute_postcommit_mail_exception_is_safe_recovery(
    tmp_path: Path, monkeypatch
) -> None:
    fake_execute = _FakeExecute()
    monkeypatch.setattr(keys_cli, "_execute_clone_plan", fake_execute)

    async def failing_send(**kwargs):
        raise RuntimeError("synthetic transport exception")

    monkeypatch.setattr(keys_cli, "_send_pending_key_email_now", failing_send)
    plan_path = _write_plan_file(tmp_path)
    result = runner.invoke(
        app, _execute_args(plan_path, "--email-delivery", "send-now", "--json")
    )
    # The clone committed despite the raised post-commit mail exception; the
    # CLI exits nonzero with safe target/secret/delivery IDs and recovery, and
    # never echoes the exception detail.
    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["status"] == "created"
    assert payload["target_gateway_key_id"] == str(TARGET_KEY_ID)
    assert payload["one_time_secret_id"] == str(ONE_TIME_SECRET_ID)
    assert "recovery" in payload
    assert payload["recovery"]["plaintext_recoverable"] is False
    assert "synthetic transport exception" not in result.stdout
