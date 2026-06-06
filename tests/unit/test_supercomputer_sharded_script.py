from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts/test-supercomputer-sharded.sh"
AGENTS = REPO_ROOT / "AGENTS.md"
TESTING_DOC = REPO_ROOT / "docs/testing-parallelism.md"


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

    extra = subprocess.run(
        [str(SCRIPT), "1", "2"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert extra.returncode != 0
    assert "Usage:" in extra.stderr


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
    assert "SLAIF_SUPERCOMPUTER_PARALLEL_E2E" in content
    assert "TEST_DATABASE_URL" in content
    assert "DB-backed shard subprocesses received isolated TEST_DATABASE_URL values" in content
    assert "DATABASE_URL was not used for destructive setup" in content
    assert "PostgreSQL availability required a generated create/drop database probe" in content
    assert 'local probe_db="${DB_PREFIX}_probe"' in content
    assert 'createdb "$probe_db"' in content
    assert 'dropdb --if-exists "$probe_db"' in content
    assert "trap cleanup EXIT INT TERM" in content
    assert "run_db_file_job" in content
    assert "find tests/integration" not in content
    assert "RUN_UPSTREAM_TESTS=0" in content
    assert "ENABLE_EMAIL_DELIVERY=false" in content
    assert "git ls-files | grep -E '(^|/)\\.codex($|/)'" in content
    assert 'run_db_suite "integration" "tests/integration" "$WORKERS"' in content
    assert 'run_db_suite "e2e" "tests/e2e" "$E2E_CONCURRENCY"' in content
    assert "E2E_CONCURRENCY=1" in content
    assert 'E2E_CONCURRENCY="$WORKERS"' in content
    assert "run_browser_suite" in content
    assert "tests/browser -m playwright" in content

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

    codex_invocation_patterns = [
        "\ncodex",
        "\tcodex",
        " codex ",
        "exec codex",
        "command -v codex",
        "$(codex",
        "`codex",
    ]
    for pattern in codex_invocation_patterns:
        assert pattern not in content


def test_supercomputer_docs_describe_inside_codex_verification_workflow() -> None:
    docs = AGENTS.read_text() + "\n" + TESTING_DOC.read_text()
    normalized_docs = " ".join(docs.split())

    assert "starts Codex" in normalized_docs
    assert "inside the repository" in normalized_docs
    assert "stays inside Codex" in normalized_docs
    assert "Codex is the caller" in docs
    assert "uses its shell tool" in docs
    assert "Repository scripts must never invoke" in docs
    assert "The repository harness itself never invokes" in docs
    assert (
        "bash -lc 'set -euo pipefail; pwd; command -v bash; command -v git; "
        "command -v python; git rev-parse --show-toplevel'"
    ) in docs
    assert "RESULT=CODEX_COMMAND_RUNNER_BROKEN" in docs
    assert "bwrap: execvp ... codex: No such file or directory" in docs
    assert "not a SLAIF test failure" in docs
    assert "Codex command-runner preflight failure" in docs
    assert "Do not edit files." in docs
    assert "Do not ask me to run commands." in docs
    assert "Do not create a branch." in docs
    assert "Do not commit." in docs
    assert "Do not open a PR." in docs
    assert "Do not run /review." in docs
    assert "Do not fix failures." in docs
    assert "In no case modify repository code." in docs
    assert "No repository commands were executed." in docs
    assert "No code was modified." in docs
    assert "scripts/test-supercomputer-sharded.sh 128" in docs
    assert "SUMMARY_PATH=" in docs
    assert "first useful bounded error excerpt from each failing shard log" in docs


def test_supercomputer_summary_includes_bounded_failure_diagnostics() -> None:
    content = SCRIPT.read_text()

    assert "ERROR_EXCERPT_PATTERN" in content
    assert "print_bounded_log_excerpt" in content
    assert "head -80" in content
    assert "tail -120" in content
    assert "failing_shard_status_entries:" in content
    assert "failing_shard_log_paths:" in content
    assert "failure_log_excerpts:" in content
    assert "postgresql_status: $POSTGRES_STATUS" in content
    assert "db_isolation: generated per-shard TEST_DATABASE_URL values only" in content
    assert "e2e_mode: $E2E_MODE" in content
    assert "browser_status: $BROWSER_STATUS" in content
    assert "PostgreSQL availability required a generated create/drop database probe" in content
    assert "E2E_MODE=\"default serial (max concurrency 1)\"" in content
    assert "BROWSER_STATUS=\"not run\"" in content
    assert "Browser tests were serial or skipped" in content


def test_supercomputer_db_suite_status_counting_tolerates_zero_matches() -> None:
    content = SCRIPT.read_text()

    assert "count_shard_status_matches()" in content
    assert 'passed="$(count_shard_status_matches "$suite" "PASS")"' in content
    assert 'failed_files="$(count_shard_status_matches "$suite" "FAIL")"' in content
    assert "grep -q \"$status_marker\"" in content
    assert "grep -l $'\\tPASS\\t'" not in content
    assert "grep -l $'\\tFAIL\\t'" not in content
