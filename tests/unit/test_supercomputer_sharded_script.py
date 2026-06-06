from __future__ import annotations

import os
import stat
import subprocess
import sys
import textwrap
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts/test-supercomputer-sharded.sh"
SETUP_SCRIPT = REPO_ROOT / "scripts/setup-hpc-test-env.sh"
RUN_SCRIPT = REPO_ROOT / "scripts/run-hpc-supercomputer-verify.sh"
AGENTS = REPO_ROOT / "AGENTS.md"
TESTING_DOC = REPO_ROOT / "docs/testing-parallelism.md"
HPC_DOC = REPO_ROOT / "docs/testing-hpc.md"
HPC_SKILL = REPO_ROOT / "agents/skills/hpc-supercomputer-verify/SKILL.md"


def test_supercomputer_script_exists_executable_and_syntax_valid() -> None:
    assert SCRIPT.exists()
    assert SCRIPT.stat().st_mode & stat.S_IXUSR
    subprocess.run(["bash", "-n", str(SCRIPT)], cwd=REPO_ROOT, check=True)
    subprocess.run(["bash", "-n", str(SETUP_SCRIPT)], cwd=REPO_ROOT, check=True)
    subprocess.run(["bash", "-n", str(RUN_SCRIPT)], cwd=REPO_ROOT, check=True)


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

    for repo_script in (SCRIPT, SETUP_SCRIPT, RUN_SCRIPT):
        script_text = repo_script.read_text()
        assert ".codex/packages" not in script_text
        assert "command -v codex" not in script_text

    for repo_script in (SCRIPT, RUN_SCRIPT):
        script_text = repo_script.read_text()
        assert "RUN_UPSTREAM_TESTS=0" in script_text or "unset RUN_UPSTREAM_TESTS" in script_text
        assert "ENABLE_EMAIL_DELIVERY=false" in script_text or 'ENABLE_EMAIL_DELIVERY="false"' in script_text


def test_supercomputer_docs_describe_inside_codex_verification_workflow() -> None:
    docs = AGENTS.read_text() + "\n" + TESTING_DOC.read_text() + "\n" + HPC_DOC.read_text()
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


def test_hpc_skill_and_docs_cover_vega_environment_preparation() -> None:
    assert HPC_SKILL.exists()
    assert not (REPO_ROOT / ".codex/skills/hpc-supercomputer-verify/SKILL.md").exists()

    docs = "\n".join(
        [
            HPC_SKILL.read_text(),
            HPC_DOC.read_text(),
            TESTING_DOC.read_text(),
            AGENTS.read_text(),
        ]
    )
    normalized_docs = " ".join(docs.split())

    assert "user stays inside Codex" in normalized_docs
    assert "Codex runs the shell commands" in normalized_docs
    assert "Repo scripts never invoke `codex`" in docs or "Repository scripts must never invoke" in docs
    assert "Redis" in docs
    assert "redis-server" in docs
    assert "Redis-backed integration tests do not skip" in docs or "Redis-dependent pytest tests skip" in docs
    assert "Docker Compose" in docs
    assert "standalone Docker Compose" in docs
    assert "thin `docker compose" in docs or "thin `docker` wrapper" in docs
    assert "Docker daemon" in docs
    assert "Do not install or require a Docker daemon" in docs or "does not need a Docker daemon" in docs
    assert ".env.example" in docs
    assert "ignored local `.env`" in docs
    assert "Validation phases" in docs
    assert "Test suites" in docs
    assert "Validation phases are not pytest tests" in docs or "non-pytest checks" in docs


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
    assert "Validation phases" in content
    assert "Test suites" in content
    assert "| phase | status | duration_s | log | note |" in content
    assert "| suite | status | duration_s | tests | passed | failed | skipped | log / log_dir | note |" in content
    assert "total skipped" in content
    assert "RESULT=OK_FULL" in content
    assert "RESULT=FAIL_REAL_TEST" in content
    assert "RESULT=ENVIRONMENT_BLOCKED" in content
    assert "RESULT=HARNESS_BUG" in content
    assert "parse_pytest_logs" in content


def test_pytest_count_reader_prints_counts_without_caller_scope_mutation() -> None:
    content = SCRIPT.read_text()

    assert "read_pytest_counts() {" in content
    assert "printf -v" not in content
    assert "__tests_var" not in content
    assert "count_tests" in content
    assert "count_passed" in content
    assert "count_failed" in content
    assert "count_skipped" in content
    assert 'IFS=$\'\\t\' read -r tests passed failed skipped parse_note < <(read_pytest_counts "$log_path")' in content
    assert (
        'IFS=$\'\\t\' read -r tests passed failed_tests skipped parse_note < '
        '<(read_pytest_counts "${log_paths[@]}")'
    ) in content
    assert "record_suite_result \"$suite\" \"PASS\" \"$duration\" \"$tests\"" in content


def test_pytest_count_reader_handles_expected_summary_shapes_under_set_u(tmp_path: Path) -> None:
    content = SCRIPT.read_text()
    function_block = content[
        content.index("parse_pytest_logs() {") : content.index("\nDB_PREFIX_RAW=")
    ]
    probe = tmp_path / "probe.sh"
    probe.write_text(
        textwrap.dedent(
            f"""\
            #!/usr/bin/env bash
            set -Eeuo pipefail
            PY="{sys.executable}"
            {function_block}
            for log_path in "$@"; do
              IFS=$'\\t' read -r tests passed failed skipped note < <(read_pytest_counts "$log_path")
              printf '%s|%s|%s|%s|%s\\n' "$tests" "$passed" "$failed" "$skipped" "$note"
            done
            """
        )
    )
    probe.chmod(0o755)

    cases = {
        "all-pass.log": ("=================== 1848 passed in 30.96s ===================\n", "1848|1848|0|0|"),
        "pass-fail.log": ("========= 127 passed, 1 failed in 11.00s =========\n", "128|127|1|0|"),
        "pass-fail-skip.log": (
            "===== 117 passed, 1 failed, 10 skipped in 11.00s =====\n",
            "128|117|1|10|",
        ),
        "browser.log": ("==================== 1 passed in 7.00s ====================\n", "1|1|0|0|"),
        "no-summary.log": ("no pytest summary here\n", "0|0|0|0|"),
    }
    log_paths = []
    for filename, (body, _expected) in cases.items():
        log_path = tmp_path / filename
        log_path.write_text(body)
        log_paths.append(log_path)

    result = subprocess.run(
        ["bash", str(probe), *(str(path) for path in log_paths)],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    lines = result.stdout.splitlines()

    for line, (_filename, (_body, expected_prefix)) in zip(lines, cases.items(), strict=True):
        assert line.startswith(expected_prefix)
    assert "no-summary.log: no pytest summary" in lines[-1]


def test_summary_reporting_is_written_after_passing_unit_counts() -> None:
    content = SCRIPT.read_text()

    unit_call = content.index('run_pytest_suite_logged "unit"')
    integration_call = content.index('run_db_suite "integration"')
    e2e_call = content.index('run_db_suite "e2e"')
    browser_call = content.index("\nrun_browser_suite\n", e2e_call)
    summary_call = content.index("\nwrite_summary\n", browser_call)
    assert unit_call < integration_call < e2e_call < browser_call < summary_call

    assert 'echo "Summary path: $SUMMARY_FILE"' in content
    assert "write_summary" in content
    assert "| phase | status | duration_s | log | note |" in content
    assert "| phase | status | duration_s | tests" not in content
    assert "| suite | status | duration_s | tests | passed | failed | skipped | log / log_dir | note |" in content


def test_supercomputer_db_suite_status_counting_tolerates_zero_matches() -> None:
    content = SCRIPT.read_text()

    assert "count_shard_status_matches()" in content
    assert 'passed_files="$(count_shard_status_matches "$suite" "PASS")"' in content
    assert 'failed_files="$(count_shard_status_matches "$suite" "FAIL")"' in content
    assert "grep -q \"$status_marker\"" in content
    assert "grep -l $'\\tPASS\\t'" not in content
    assert "grep -l $'\\tFAIL\\t'" not in content


def test_hpc_setup_provisions_redis_and_compose_without_daemon() -> None:
    setup = SETUP_SCRIPT.read_text()
    runner = RUN_SCRIPT.read_text()

    assert "SLAIF_HPC_REDIS_PREFIX" in setup
    assert "SLAIF_HPC_REDIS_VERSION" in setup
    assert "redis-server --version" in setup
    assert "redis-cli --version" in setup
    assert "https://download.redis.io/releases/redis-${REDIS_VERSION}.tar.gz" in setup
    assert "env -u LD_LIBRARY_PATH -u LIBRARY_PATH -u CPATH -u PKG_CONFIG_PATH -u PYTHONPATH" in setup
    assert "make MALLOC=libc" in setup
    assert "CC=/usr/bin/gcc" in setup
    assert "SLAIF_HPC_DOCKER_COMPOSE_PREFIX" in setup
    assert "SLAIF_HPC_DOCKER_COMPOSE_VERSION" in setup
    assert "docker compose version" in setup
    assert "docker compose config" in setup
    assert "This user-local wrapper only supports: docker compose ..." in setup
    assert ".env.example" in setup
    assert "git -C \"$REPO_ROOT\" check-ignore -q .env" in setup
    assert "docker daemon" not in setup.lower()

    assert "SLAIF_HPC_REDIS_PREFIX" in runner
    assert "SLAIF_HPC_DOCKER_COMPOSE_PREFIX" in runner
    assert "Redis prefix" in runner
    assert "Docker Compose wrapper prefix" in runner
    assert "Compose .env status" in runner
    assert "unset DATABASE_URL" in runner
    assert "unset RUN_UPSTREAM_TESTS" in runner
    assert "unset OPENAI_API_KEY" in runner
    assert "ENABLE_EMAIL_DELIVERY=\"false\"" in runner
    assert "SLAIF_HPC_REDIS_PREFIX}/bin" in runner
    assert "SLAIF_HPC_DOCKER_COMPOSE_PREFIX}/bin" in runner


def test_hpc_reporting_keeps_validation_counts_out_of_validation_table() -> None:
    content = SCRIPT.read_text()

    validation_header = "| phase | status | duration_s | log | note |"
    suite_header = "| suite | status | duration_s | tests | passed | failed | skipped | log / log_dir | note |"
    assert validation_header in content
    assert suite_header in content
    assert "| phase | status | duration_s | tests" not in content
    assert "record_validation_result" in content
    assert "record_suite_result" in content
    assert "pytest_skipped_tests: $total_skipped" in content
    assert "total_skipped" in content


def test_no_committed_local_env_or_codex_state() -> None:
    tracked = subprocess.run(
        ["git", "ls-files"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=True,
    ).stdout.splitlines()
    assert ".env" not in tracked
    assert not any(path.startswith(".codex/") or "/.codex/" in path for path in tracked)


def test_no_hpc_report_specific_user_or_job_paths_are_committed() -> None:
    checked_paths = [
        AGENTS,
        TESTING_DOC,
        HPC_DOC,
        HPC_SKILL,
        SCRIPT,
        SETUP_SCRIPT,
        RUN_SCRIPT,
    ]
    combined = "\n".join(path.read_text() for path in checked_paths)
    user_marker = "jp" + "ers"
    account_marker = "cn" + "0393"
    job_marker = "348" + "15129"
    path_marker = f"/dev/shm/{user_marker}"
    for marker in (user_marker, account_marker, path_marker, job_marker):
        assert marker not in combined
