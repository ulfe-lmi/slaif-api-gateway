from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts/test-supercomputer-sharded.sh"


def test_supercomputer_script_exists_executable_and_syntax_valid() -> None:
    assert SCRIPT.exists()
    assert SCRIPT.stat().st_mode & stat.S_IXUSR
    subprocess.run(["bash", "-n", str(SCRIPT)], cwd=REPO_ROOT, check=True)


def test_supercomputer_script_requires_one_positive_integer_worker_argument() -> None:
    missing = subprocess.run(
        [str(SCRIPT)],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert missing.returncode != 0
    assert "Usage:" in missing.stderr

    invalid = subprocess.run(
        [str(SCRIPT), "not-an-int"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert invalid.returncode != 0
    assert "worker count must be a positive integer" in invalid.stderr


def test_supercomputer_script_refuses_production_and_upstream_smoke_mode() -> None:
    production_env = os.environ.copy()
    production_env["APP_ENV"] = "production"
    production = subprocess.run(
        [str(SCRIPT), "1"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        env=production_env,
        check=False,
    )
    assert production.returncode != 0
    assert "APP_ENV=production" in production.stderr

    upstream_env = os.environ.copy()
    upstream_env["RUN_UPSTREAM_TESTS"] = "1"
    upstream = subprocess.run(
        [str(SCRIPT), "1"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        env=upstream_env,
        check=False,
    )
    assert upstream.returncode != 0
    assert "RUN_UPSTREAM_TESTS=1" in upstream.stderr


def test_supercomputer_script_text_preserves_db_and_secret_safety_contract() -> None:
    content = SCRIPT.read_text()

    assert "SLAIF_SUPERCOMPUTER_RAMDISK" in content
    assert "SLAIF_SUPERCOMPUTER_KEEP_DBS" in content
    assert "SLAIF_SUPERCOMPUTER_SKIP_BROWSER" in content
    assert "SLAIF_SUPERCOMPUTER_SKIP_DOCKER" in content
    assert "TEST_DATABASE_URL" in content
    assert "DB-backed shard subprocesses received isolated TEST_DATABASE_URL values" in content
    assert "DATABASE_URL was not used for destructive setup" in content
    assert "trap cleanup EXIT INT TERM" in content
    assert "run_db_file_job" in content
    assert "find tests/integration" not in content
    assert "RUN_UPSTREAM_TESTS=0" in content
    assert "ENABLE_EMAIL_DELIVERY=false" in content

    dangerous_patterns = [
        "dropdb $DATABASE" + "_URL",
        "dropdb ${DATABASE" + "_URL",
        "createdb $DATABASE" + "_URL",
        "createdb ${DATABASE" + "_URL",
        "psql $DATABASE" + "_URL",
        "OPENAI" + "_API_KEY=",
        "OPENAI_UPSTREAM" + "_API_KEY=sk-",
        "OPENROUTER" + "_API_KEY=sk-",
    ]
    for pattern in dangerous_patterns:
        assert pattern not in content
