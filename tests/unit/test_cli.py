import json
import re

import structlog
from typer.testing import CliRunner

from slaif_gateway.cli import keys as keys_cli
from slaif_gateway.cli import main as cli_main
from slaif_gateway.config import get_settings

app = cli_main.app

runner = CliRunner()

_ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


def _plain_stderr(stderr: str) -> str:
    return " ".join(_ANSI_RE.sub("", stderr).split())


def setup_function() -> None:
    get_settings.cache_clear()
    structlog.reset_defaults()


def teardown_function() -> None:
    # Typer's CliRunner provides an isolated stderr stream. CLI logging tests
    # intentionally bind structlog to that stream, so reset it before later
    # tests in the same xdist worker can inherit a closed capture object.
    structlog.reset_defaults()


def test_cli_version() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "slaif-api-gateway 0.1.0" in result.stdout


def test_cli_verbose_version_enables_debug_logs_on_stderr() -> None:
    result = runner.invoke(app, ["--verbose", "version"])

    assert result.exit_code == 0
    assert "slaif-api-gateway 0.1.0" in result.stdout
    assert "cli.command.start" in result.stderr
    assert '"level": "debug"' in result.stderr


def test_cli_short_verbose_version_enables_debug_logs_on_stderr() -> None:
    result = runner.invoke(app, ["-v", "version"])

    assert result.exit_code == 0
    assert "slaif-api-gateway 0.1.0" in result.stdout
    assert "cli.command.start" in result.stderr


def test_cli_log_level_debug_version_enables_debug_logs_on_stderr() -> None:
    result = runner.invoke(app, ["--log-level", "debug", "version"])

    assert result.exit_code == 0
    assert "slaif-api-gateway 0.1.0" in result.stdout
    assert "cli.command.start" in result.stderr
    assert '"level": "debug"' in result.stderr


def test_cli_rejects_invalid_log_level() -> None:
    result = runner.invoke(app, ["--log-level", "trace", "version"])

    assert result.exit_code == 2
    plain_stderr = _plain_stderr(result.stderr)
    assert "--log-level must be one of" in plain_stderr
    assert "DEBUG, INFO, WARNING, ERROR" in plain_stderr
    assert "CRITICAL" in plain_stderr


def test_cli_rejects_verbose_and_log_level_together() -> None:
    result = runner.invoke(app, ["--verbose", "--log-level", "DEBUG", "version"])

    assert result.exit_code == 2
    plain_stderr = _plain_stderr(result.stderr)
    assert "Use either --verbose or --log-level, not both" in plain_stderr


def test_cli_verbose_logs_redact_fake_secrets(monkeypatch) -> None:
    real_configure_logging = cli_main.configure_logging

    def configure_and_emit_secret_log(*args: object, **kwargs: object) -> None:
        real_configure_logging(*args, **kwargs)
        structlog.get_logger("tests.cli").debug(
            "cli.secret.redaction.test",
            plaintext_key="sk-slaif-public.secretsecret",
            provider_key="sk-or-providersecret123",
            Authorization="Bearer authorization-secret",
            csrf_token="csrf-secret",
            session_token="session-secret",
            encrypted_payload="encrypted-secret",
            nonce="nonce-secret",
        )

    monkeypatch.setattr(cli_main, "configure_logging", configure_and_emit_secret_log)

    result = runner.invoke(app, ["--verbose", "version"])

    assert result.exit_code == 0
    assert "cli.secret.redaction.test" in result.stderr
    for forbidden in (
        "secretsecret",
        "providersecret",
        "authorization-secret",
        "csrf-secret",
        "session-secret",
        "encrypted-secret",
        "nonce-secret",
    ):
        assert forbidden not in result.stdout
        assert forbidden not in result.stderr


def test_cli_verbose_keeps_json_stdout_machine_readable(monkeypatch) -> None:
    async def fake_list_gateway_keys(**kwargs: object) -> list[object]:
        return []

    monkeypatch.setattr(keys_cli, "_list_gateway_keys", fake_list_gateway_keys)

    result = runner.invoke(app, ["--verbose", "keys", "list", "--json"])

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {"keys": []}
    assert "cli.command.start" in result.stderr
