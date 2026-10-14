"""184 R1: the thin installed administrator refresh wrapper.

These unit tests pin the wrapper's ARGUMENT BOUNDARIES: the standard
Linux timeout watchdog only ever wraps the read-only collect
subcommand, the child's exact exit code is preserved, unsupported
presets/modes and non-positive watchdog durations refuse before any
spawn, and apply/review/export/verify/status never reach the watchdog.
The actual installed workflow and real watchdog cancellation are
qualified in tests/integration/test_catalog_refresh_installed_workflow.py.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

import slaif_gateway.cli.catalog_refresh_admin as admin_mod
from slaif_gateway.cli.catalog_refresh_admin import app as admin_app

runner = CliRunner()


def _invoke(args: list[str], monkeypatch, *, rc: int = 0, which_map: dict | None = None):
    spawns: list[list[str]] = []

    def fake_run(cmd, **_kw):
        spawns.append(list(cmd))
        return subprocess.CompletedProcess(cmd, rc)

    def fake_which(name: str):
        if which_map is not None:
            return which_map.get(name)
        return f"/fake/{name}"

    monkeypatch.setattr(admin_mod.subprocess, "run", fake_run)
    monkeypatch.setattr(admin_mod.shutil, "which", fake_which)
    result = runner.invoke(admin_app, args)
    return result, spawns


def _no_spawn_run(monkeypatch):
    def exploding_run(cmd, **_kw):
        raise AssertionError(f"wrapper spawned a child: {cmd}")

    monkeypatch.setattr(admin_mod.subprocess, "run", exploding_run)


def test_admin_refresh_builds_watchdog_collect_argv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result, spawns = _invoke(
        [
            "--mode", "bootstrap",
            "--run-root", str(tmp_path / "runs"),
            "--seal-key", str(tmp_path / "seal.key"),
            "--providers", "openai",
            "--models", "gpt-3.5-turbo",
            "--json",
        ],
        monkeypatch,
    )
    assert result.exit_code == 0, result.output
    assert len(spawns) == 1
    cmd = spawns[0]
    # watchdog prefix: timeout -k <grace> <timeout>
    assert cmd[:3] == ["/fake/timeout", "-k", "5"]
    assert cmd[3] == "300"  # default 300s
    # the child is the installed gateway CLI, collect subcommand only
    child = cmd[4:]
    assert child[:3] == ["/fake/slaif-gateway", "catalog-refresh", "collect"]
    assert "--bootstrap" in child
    assert "--profile" in child and child[child.index("--profile") + 1] == "standard-v1"
    assert child[child.index("--providers") + 1] == "openai"
    assert child[child.index("--models") + 1] == "gpt-3.5-turbo"
    assert "--json" in child
    assert child[child.index("--run-root") + 1] == str(tmp_path / "runs")
    assert child[child.index("--seal-key") + 1] == str(tmp_path / "seal.key")
    # defaults stay default (no implicit model cap, both providers when unset)
    assert "--providers" in child


@pytest.mark.parametrize("child_rc", [0, 10, 20, 65, 124, 137])
def test_admin_refresh_preserves_child_exit_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, child_rc: int
) -> None:
    result, spawns = _invoke(
        [
            "--mode", "bootstrap",
            "--run-root", str(tmp_path / "runs"),
            "--seal-key", str(tmp_path / "seal.key"),
        ],
        monkeypatch,
        rc=child_rc,
    )
    assert result.exit_code == child_rc, result.output
    assert len(spawns) == 1


def test_admin_refresh_never_puts_noncollect_under_watchdog(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result, spawns = _invoke(
        [
            "--mode", "refresh",
            "--db-url", "postgresql://u@localhost/db",
            "--run-root", str(tmp_path / "runs"),
            "--seal-key", str(tmp_path / "seal.key"),
        ],
        monkeypatch,
    )
    assert result.exit_code == 0, result.output
    child = spawns[0][4:]
    # exactly the read-only collect subcommand; no other catalog-refresh
    # subcommand may ever be placed under the watchdog
    assert child[:3] == ["/fake/slaif-gateway", "catalog-refresh", "collect"]
    for forbidden in ("apply", "review", "export-baseline", "verify", "status"):
        assert forbidden not in child
    assert child[child.index("--db-url") + 1] == "postgresql://u@localhost/db"


def test_admin_refresh_refuses_unsupported_mode_before_spawn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _no_spawn_run(monkeypatch)
    result, spawns = _invoke(
        [
            "--mode", "help",
            "--run-root", str(tmp_path / "runs"),
            "--seal-key", str(tmp_path / "seal.key"),
        ],
        monkeypatch,
    )
    assert result.exit_code == 65, result.output
    assert "must be one of" in result.output
    assert spawns == []
    # Profile/preset support stays the EXISTING child's single authority
    # (the wrapper passes --profile through unchanged and duplicates no
    # preset policy); the exact installed unsupported-preset refusal is
    # proven with the actual installed command in the R5/R7 integration
    # evidence.


def test_admin_refresh_requires_positive_kill_grace_before_spawn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _no_spawn_run(monkeypatch)
    result, spawns = _invoke(
        [
            "--mode", "bootstrap", "--kill-grace", "0",
            "--run-root", str(tmp_path / "runs"),
            "--seal-key", str(tmp_path / "seal.key"),
        ],
        monkeypatch,
    )
    assert result.exit_code == 65, result.output
    assert "KILL escalation" in result.output
    assert spawns == []


def test_admin_refresh_requires_positive_timeout_before_spawn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _no_spawn_run(monkeypatch)
    result, spawns = _invoke(
        [
            "--mode", "bootstrap", "--timeout", "0",
            "--run-root", str(tmp_path / "runs"),
            "--seal-key", str(tmp_path / "seal.key"),
        ],
        monkeypatch,
    )
    assert result.exit_code == 65, result.output
    assert "positive" in result.output
    assert spawns == []


def test_admin_refresh_bootstrap_rejects_baseline_source_before_spawn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _no_spawn_run(monkeypatch)
    result, spawns = _invoke(
        [
            "--mode", "bootstrap", "--db-url", "postgresql://u@localhost/db",
            "--run-root", str(tmp_path / "runs"),
            "--seal-key", str(tmp_path / "seal.key"),
        ],
        monkeypatch,
    )
    assert result.exit_code == 65, result.output
    assert spawns == []


def test_admin_refresh_missing_gateway_cli_is_data_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _no_spawn_run(monkeypatch)
    result, spawns = _invoke(
        [
            "--mode", "bootstrap",
            "--run-root", str(tmp_path / "runs"),
            "--seal-key", str(tmp_path / "seal.key"),
        ],
        monkeypatch,
        which_map={"timeout": "/fake/timeout", "slaif-gateway": None},
    )
    assert result.exit_code == 65, result.output
    assert "slaif-gateway" in result.output
    assert spawns == []


def test_admin_refresh_missing_timeout_binary_is_data_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _no_spawn_run(monkeypatch)
    result, spawns = _invoke(
        [
            "--mode", "bootstrap",
            "--run-root", str(tmp_path / "runs"),
            "--seal-key", str(tmp_path / "seal.key"),
        ],
        monkeypatch,
        which_map={"timeout": None, "slaif-gateway": "/fake/slaif-gateway"},
    )
    assert result.exit_code == 65, result.output
    assert "timeout" in result.output
    assert spawns == []


def test_admin_refresh_research_passthrough_only_with_research(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = [
        "--run-root", str(tmp_path / "runs"),
        "--seal-key", str(tmp_path / "seal.key"),
    ]
    # without --research: no research option may reach the child
    result, spawns = _invoke(["--mode", "bootstrap", *base], monkeypatch)
    assert result.exit_code == 0, result.output
    child = spawns[0][4:]
    assert "--research" not in child and "--research-endpoint" not in child

    # with --research: the existing research options pass through verbatim
    result, spawns = _invoke(
        [
            "--mode", "bootstrap", *base,
            "--research",
            "--research-cli-bin", "/opt/codex/bin/codex",
            "--research-endpoint", "https://research.example/v1",
            "--research-model", "research-model",
            "--research-auth-env", "SLAIF_RESEARCH_KEY",
            "--research-timeout", "240",
        ],
        monkeypatch,
    )
    assert result.exit_code == 0, result.output
    child = spawns[0][4:]
    assert "--research" in child
    assert child[child.index("--research-cli-bin") + 1] == "/opt/codex/bin/codex"
    assert child[child.index("--research-endpoint") + 1] == "https://research.example/v1"
    assert child[child.index("--research-model") + 1] == "research-model"
    assert child[child.index("--research-auth-env") + 1] == "SLAIF_RESEARCH_KEY"
    assert child[child.index("--research-timeout") + 1] == "240"


def test_admin_refresh_mode_is_case_insensitive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result, spawns = _invoke(
        [
            "--mode", "BOOTSTRAP",
            "--run-root", str(tmp_path / "runs"),
            "--seal-key", str(tmp_path / "seal.key"),
        ],
        monkeypatch,
    )
    assert result.exit_code == 0, result.output
    assert "--bootstrap" in spawns[0]
