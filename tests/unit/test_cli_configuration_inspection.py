"""Finite process-configuration inspection (204-b).

Covers the exact reviewed allowlist, honest configured/default source
reporting, the fixed safe unavailable boundary at the ACTUAL root
callback path (real Typer app), no-echo of an invalid Settings
environment, and actual COLD subprocess entrypoint coverage (import
under an invalid numeric Settings environment, and real
``config show`` invocations under valid/invalid environments).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from typer.testing import CliRunner

import slaif_gateway.cli.configuration as configuration_cli
import slaif_gateway.cli.main as main_cli
from slaif_gateway.config import Settings
from slaif_gateway.services.configuration_inspection import (
    CONFIG_INSPECTION_ALLOWLIST,
    INSPECTION_LIMITATIONS,
    PROCESS_RESTART_SCOPE,
    inspect_process_configuration,
    render_process_configuration_text,
)

# One consistent module-import style for the CLI entry point: the module
# alias serves the callback monkeypatches, and the SAME app object serves
# every invocation below.
app = main_cli.app

# Recognized provider-key shape used as a SYNTHETIC invalid numeric
# Settings value (never a real credential).
CANARY = "sk-proj-canary204b0000000000000"
_runner = CliRunner()
_REPO_ROOT = Path(__file__).resolve().parents[2]


# --- allowlist discipline ---------------------------------------------------


def test_allowlist_is_exactly_the_reviewed_finite_set() -> None:
    assert len(CONFIG_INSPECTION_ALLOWLIST) == 45
    assert len(set(CONFIG_INSPECTION_ALLOWLIST)) == 45
    model_fields = Settings.model_fields
    for name in CONFIG_INSPECTION_ALLOWLIST:
        assert name in model_fields, f"unknown setting {name}"
    # No wildcard enumeration: the allowlist must be a literal tuple.
    assert isinstance(CONFIG_INSPECTION_ALLOWLIST, tuple)


def test_allowlist_names_are_secret_free() -> None:
    forbidden = (
        "password", "secret", "hmac", "api_key", "smtp", "database",
        "redis", "session", "upstream", "token_hash",
    )
    for name in CONFIG_INSPECTION_ALLOWLIST:
        lowered = name.lower()
        for term in forbidden:
            assert term not in lowered, (name, term)


# --- pure projection ---------------------------------------------------------


def test_inspection_reports_values_and_honest_sources() -> None:
    settings = Settings(APP_ENV="test")
    payload = inspect_process_configuration(settings)
    config = payload["config"]
    assert config["snapshot_scope"] == "current CLI process cached Settings"
    assert config["limitations"] == list(INSPECTION_LIMITATIONS)
    settings_map = config["settings"]
    assert set(settings_map) == set(CONFIG_INSPECTION_ALLOWLIST)

    replay = settings_map["CODEX_REPLAY_REFERENCE_TTL_SECONDS"]
    assert replay["value"] == settings.CODEX_REPLAY_REFERENCE_TTL_SECONDS
    assert replay["source"] == "default"
    assert replay["restart_scope"] == PROCESS_RESTART_SCOPE

    # A value explicitly supplied at construction is "configured"; every
    # other allowlisted name stays "default" (no validator-derived noise
    # for these names was observed).
    overridden = Settings(
        APP_ENV="test", CODEX_REPLAY_REFERENCE_TTL_SECONDS=1234
    )
    overridden_payload = inspect_process_configuration(overridden)
    overridden_map = overridden_payload["config"]["settings"]
    assert overridden_map["CODEX_REPLAY_REFERENCE_TTL_SECONDS"]["value"] == 1234
    assert (
        overridden_map["CODEX_REPLAY_REFERENCE_TTL_SECONDS"]["source"]
        == "configured"
    )
    assert (
        overridden_map["HARD_MAX_INPUT_TOKENS"]["source"] == "default"
    )

    # Nullable defaults are reported as None, not as missing entries.
    assert settings_map["DEFAULT_RATE_LIMIT_REQUESTS_PER_MINUTE"]["value"] is None


def test_text_render_is_compact_and_limited() -> None:
    payload = inspect_process_configuration(Settings(APP_ENV="test"))
    text = render_process_configuration_text(payload)
    assert "not live API/worker state" in text
    # One shared restart/recreate line (not repeated per setting).
    assert "restart scope for every listed setting" in text
    assert "recreating the affected containers" in text
    assert "CODEX_REPLAY_REFERENCE_TTL_SECONDS =" in text
    assert "source: default" in text
    assert "Limitations:" in text
    assert "reverse-proxy" in text


# --- CLI show through the REAL root callback ---------------------------------


def test_config_show_json_and_text_valid_environment(monkeypatch) -> None:
    settings = Settings(
        APP_ENV="test", HARD_MAX_OUTPUT_TOKENS=9999
    )
    monkeypatch.setattr(configuration_cli, "get_settings", lambda: settings)
    result = _runner.invoke(app, ["config", "show", "--json"], env={"NO_COLOR": "1"})
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    settings_map = payload["config"]["settings"]
    assert len(settings_map) == 45
    assert settings_map["HARD_MAX_OUTPUT_TOKENS"] == {
        "value": 9999,
        "source": "configured",
        "restart_scope": PROCESS_RESTART_SCOPE,
    }

    result = _runner.invoke(app, ["config", "show"], env={"NO_COLOR": "1"})
    assert result.exit_code == 0, result.output
    assert "HARD_MAX_OUTPUT_TOKENS = 9999 (source: configured)" in result.stdout


def test_config_show_unavailable_maps_settings_fault_without_echo(monkeypatch) -> None:
    calls = {"main": 0}

    def _main_settings_must_not_run():
        calls["main"] += 1
        raise AssertionError("root callback must not build Settings for config")

    def _broken_settings():
        raise RuntimeError(
            f"synthetic Settings failure: {CANARY} invalid value"
        )

    monkeypatch.setattr(main_cli, "get_settings", _main_settings_must_not_run)
    monkeypatch.setattr(configuration_cli, "get_settings", _broken_settings)

    result = _runner.invoke(
        app, ["config", "show", "--json"], env={"NO_COLOR": "1"}
    )
    assert result.exit_code == 1
    assert calls["main"] == 0
    payload = json.loads(result.stdout)
    assert payload == {
        "error": {
            "code": "configuration_unavailable",
            "message": (
                "Process configuration could not be loaded. Check the "
                "deployment environment and try again."
            ),
        }
    }
    assert CANARY not in result.stdout
    assert CANARY not in (result.stderr or "")

    result = _runner.invoke(app, ["config", "show"], env={"NO_COLOR": "1"})
    assert result.exit_code == 1
    assert "configuration_unavailable" not in result.stdout
    assert "Process configuration could not be loaded" in (result.stderr or "")
    assert CANARY not in (result.stderr or "")


def test_non_config_commands_still_build_settings_in_root_callback(monkeypatch) -> None:
    calls = {"main": 0}
    real_settings = Settings(APP_ENV="test")

    def _spied_settings():
        calls["main"] += 1
        return real_settings

    monkeypatch.setattr(main_cli, "get_settings", _spied_settings)
    result = _runner.invoke(app, ["version"], env={"NO_COLOR": "1"})
    assert result.exit_code == 0, result.output
    assert calls["main"] == 1


# --- COLD actual-subprocess entrypoint coverage -------------------------------


def _subprocess_env(**overrides) -> dict[str, str]:
    env = dict(os.environ)
    env.pop("DATABASE_URL", None)
    env.pop("TEST_DATABASE_URL", None)
    env.update(
        {
            "PYTHONPATH": str(_REPO_ROOT / "app"),
            "APP_ENV": "test",
            "NO_COLOR": "1",
            "COLUMNS": "220",
        }
    )
    env.update(overrides)
    return env


_COLD_IMPORT_CODE = (
    "import sys, json\n"
    "import slaif_gateway.cli.main\n"
    "print(json.dumps({"
    "'worker_task_loaded': 'slaif_gateway.workers.tasks_email' in sys.modules, "
    "'celery_app_loaded': 'slaif_gateway.workers.celery_app' in sys.modules"
    "}))"
)

_CONFIG_SHOW_CODE = (
    "import sys\n"
    'sys.argv = ["slaif-gateway", "config", "show", "--json"]\n'
    "from slaif_gateway.cli.main import app\n"
    "app()\n"
)


def test_cold_import_invalid_numeric_settings_environment() -> None:
    proc = subprocess.run(
        [sys.executable, "-c", _COLD_IMPORT_CODE],
        cwd=_REPO_ROOT,
        env=_subprocess_env(HARD_MAX_INPUT_TOKENS=CANARY),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    facts = json.loads(proc.stdout)
    assert facts == {"worker_task_loaded": False, "celery_app_loaded": False}
    assert CANARY not in proc.stdout
    assert CANARY not in proc.stderr
    assert "Traceback" not in proc.stderr


def test_cold_import_valid_settings_environment() -> None:
    proc = subprocess.run(
        [sys.executable, "-c", _COLD_IMPORT_CODE],
        cwd=_REPO_ROOT,
        env=_subprocess_env(HARD_MAX_INPUT_TOKENS="128000"),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    facts = json.loads(proc.stdout)
    assert facts["worker_task_loaded"] is False


def test_real_config_show_valid_environment_subprocess() -> None:
    proc = subprocess.run(
        [sys.executable, "-c", _CONFIG_SHOW_CODE],
        cwd=_REPO_ROOT,
        env=_subprocess_env(HARD_MAX_INPUT_TOKENS="128000"),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    settings_map = payload["config"]["settings"]
    assert len(settings_map) == 45
    assert settings_map["HARD_MAX_INPUT_TOKENS"]["value"] == 128000
    assert settings_map["HARD_MAX_INPUT_TOKENS"]["source"] == "configured"
    assert settings_map["CODEX_REPLAY_REFERENCE_TTL_SECONDS"]["source"] == "default"


def test_real_config_show_invalid_environment_subprocess_no_echo() -> None:
    proc = subprocess.run(
        [sys.executable, "-c", _CONFIG_SHOW_CODE],
        cwd=_REPO_ROOT,
        env=_subprocess_env(HARD_MAX_INPUT_TOKENS=CANARY),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 1
    payload = json.loads(proc.stdout)
    assert payload["error"]["code"] == "configuration_unavailable"
    assert CANARY not in proc.stdout
    assert CANARY not in proc.stderr
    assert "Traceback" not in proc.stderr
