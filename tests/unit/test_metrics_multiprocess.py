"""Cross-worker (multiprocess) metrics aggregation tests.

Simulates the shipped two-worker gunicorn topology: worker processes share
one ``PROMETHEUS_MULTIPROC_DIR`` (here a ``tmp_path`` directory), and a
single scrape must expose the aggregated samples of every *live* worker
under the original metric names. Subprocesses import the working-tree
metrics module with the environment variable set, so the real F1 wiring
(unregistered metric objects plus the single ``MultiProcessCollector``)
is what is exercised.

Worker processes stay alive (sleeping) until the test signals them,
mirroring gunicorn workers that keep serving while a scrape happens. A
worker that exits after calling ``metrics.on_worker_exit()`` simulates the
gunicorn ``worker_exit`` hook on graceful shutdown; a worker killed with
SIGKILL simulates a crash, where no cleanup hook can run and the
per-process files persist until explicitly reaped.
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

FAMILIES = (
    "gateway_http_requests_total",
    "gateway_provider_requests_total",
    "gateway_tokens_total",
    "gateway_cost_eur_total",
)

APP_DIR = Path(__file__).resolve().parents[2] / "app"
REPO_ROOT = APP_DIR.parent

WORKER_SCRIPT = textwrap.dedent(
    """
    import os
    import sys
    import time

    from decimal import Decimal

    from slaif_gateway import metrics

    for _ in range(2):
        metrics.observe_http_request(
            method="POST",
            endpoint="/v1/chat/completions",
            status_code=200,
            duration_seconds=0.001,
        )
    metrics.record_provider_call_result(
        provider="p",
        endpoint="chat.completions",
        status="success",
        duration_seconds=0.001,
    )
    metrics.add_tokens(provider="p", model="m", token_type="input", count=12)
    metrics.add_cost_eur(provider="p", model="m", cost_eur=Decimal("0.0001"))
    if len(sys.argv) > 2 and sys.argv[2] == "clean":
        # Simulate the gunicorn worker_exit hook firing on graceful exit.
        metrics.on_worker_exit()
        sys.exit(0)
    print("WORKER_READY", flush=True)
    time.sleep(600)
    """
)

REAPER_SCRIPT = textwrap.dedent(
    """
    import sys

    from slaif_gateway import metrics

    metrics._remove_multiproc_files_for_pid(int(sys.argv[2]))
    """
)

SCRAPE_SCRIPT = textwrap.dedent(
    """
    import re

    from slaif_gateway import metrics

    families = {
        "gateway_http_requests_total",
        "gateway_provider_requests_total",
        "gateway_tokens_total",
        "gateway_cost_eur_total",
    }
    sample = re.compile(r"^(?P<name>[a-zA-Z_:][a-zA-Z0-9_:]*)\\{[^\\n]*\\}\\s+(?P<value>[+-]?[0-9.eE+]+)$")
    counts = {family: 0 for family in families}
    body = metrics.prometheus_response_body().decode()
    for line in body.splitlines():
        match = sample.match(line)
        if not match:
            continue
        name = match.group("name")
        if name in families and float(match.group("value")) > 0:
            counts[name] += 1
    for family in sorted(families):
        print(f"POSITIVE {family} {counts[family]}")
    for line in body.splitlines():
        if line.startswith(
            'gateway_tokens_total{model="m",provider="p",token_type="input"}'
        ) or line.startswith('gateway_cost_eur_total{model="m",provider="p"}'):
            print(f"LINE {line}")
    """
)


def _subprocess_env(mpm_dir: Path) -> dict[str, str]:
    env = dict(os.environ)
    env["PROMETHEUS_MULTIPROC_DIR"] = str(mpm_dir)
    env["PYTHONPATH"] = str(APP_DIR)
    return env


def _start_live_worker(mpm_dir: Path) -> subprocess.Popen[str]:
    proc = subprocess.Popen(
        [sys.executable, "-c", WORKER_SCRIPT, str(mpm_dir)],
        cwd=str(REPO_ROOT),
        env=_subprocess_env(mpm_dir),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    line = proc.stdout.readline()
    assert line.strip() == "WORKER_READY", (line, proc.stderr.read())
    return proc


def _stop_worker(proc: subprocess.Popen[str], sigkill: bool = True) -> None:
    if sigkill:
        proc.kill()
    else:
        proc.terminate()
    proc.wait(timeout=10)


def _run_worker_clean_exit(mpm_dir: Path) -> None:
    proc = subprocess.run(
        [sys.executable, "-c", WORKER_SCRIPT, str(mpm_dir), "clean"],
        cwd=str(REPO_ROOT),
        env=_subprocess_env(mpm_dir),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, (proc.stdout, proc.stderr)


def _scrape(mpm_dir: Path) -> dict[str, object]:
    proc = subprocess.run(
        [sys.executable, "-c", SCRAPE_SCRIPT],
        cwd=str(REPO_ROOT),
        env=_subprocess_env(mpm_dir),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, (proc.stdout, proc.stderr)
    counts: dict[str, int] = {}
    lines: dict[str, str] = {}
    for line in proc.stdout.splitlines():
        if line.startswith("POSITIVE "):
            _, family, value = line.split()
            counts[family] = int(value)
        elif line.startswith("LINE "):
            payload = line[len("LINE ") :]
            lines[payload.split()[0].split("{")[0]] = payload
    return {"counts": counts, "lines": lines}


def test_single_scrape_aggregates_two_live_workers(tmp_path) -> None:
    worker_a = _start_live_worker(tmp_path)
    worker_b = _start_live_worker(tmp_path)
    try:
        result = _scrape(tmp_path)
        counts = result["counts"]

        # Every exercised family is positive on one scrape of the aggregate.
        assert all(counts[family] >= 1 for family in FAMILIES), counts
        # Both live workers contributed: per-worker increments summed exactly
        # under the original (unprefixed) metric names.
        assert result["lines"]["gateway_tokens_total"] == (
            'gateway_tokens_total{model="m",provider="p",token_type="input"} 24.0'
        ), result["lines"]
        assert result["lines"]["gateway_cost_eur_total"] == (
            'gateway_cost_eur_total{model="m",provider="p"} 0.0002'
        ), result["lines"]
    finally:
        _stop_worker(worker_a)
        _stop_worker(worker_b)


def test_worker_exit_hook_removes_worker_files(tmp_path) -> None:
    # A worker whose gunicorn worker_exit hook fired on graceful exit must
    # not leave its per-process files behind; the aggregate is empty.
    _run_worker_clean_exit(tmp_path)

    result = _scrape(tmp_path)
    assert all(result["counts"][family] == 0 for family in FAMILIES), result["counts"]


def test_lifespan_shutdown_removes_multiproc_files(tmp_path, monkeypatch) -> None:
    # The shipped UvicornWorker topology cleans up through the application
    # lifespan shutdown (atexit and the gunicorn worker-exit hook do not
    # run there); verify the create_app wiring at the ASGI lifecycle level.
    # The app is imported before PROMETHEUS_MULTIPROC_DIR is set so this
    # process's metric objects stay in single-process mode and never parse
    # the stale file below; the cleanup under test reads the env at call
    # time.
    from fastapi.testclient import TestClient

    from slaif_gateway.config import Settings
    from slaif_gateway.main import create_app

    app = create_app(Settings(APP_ENV="test"))

    fake = tmp_path / f"counter_{os.getpid()}.db"
    fake.write_text("stale multiprocess file")
    monkeypatch.setenv("PROMETHEUS_MULTIPROC_DIR", str(tmp_path))

    with TestClient(app):
        assert fake.exists()
    assert not fake.exists()


def test_dead_worker_files_remain_until_reaped(tmp_path) -> None:
    crashed = _start_live_worker(tmp_path)
    try:
        before = _scrape(tmp_path)
        assert all(before["counts"][family] >= 1 for family in FAMILIES), before["counts"]
    finally:
        # SIGKILL: no cleanup hook can run, so the files persist.
        _stop_worker(crashed, sigkill=True)

    # The dead worker's files still contribute until explicitly reaped with
    # the same code path the worker_exit hook uses.
    subprocess.run(
        [sys.executable, "-c", REAPER_SCRIPT, str(tmp_path), str(crashed.pid)],
        cwd=str(REPO_ROOT),
        env=_subprocess_env(tmp_path),
        capture_output=True,
        text=True,
        check=True,
    )
    after = _scrape(tmp_path)
    assert all(after["counts"][family] == 0 for family in FAMILIES), after["counts"]
