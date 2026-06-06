#!/usr/bin/env bash
set -Eeuo pipefail

# Opt-in high-core verification harness for a single-node interactive machine.
#
# Interface:
#   scripts/test-supercomputer-sharded.sh <workers>
#
# Optional environment variables:
#   SLAIF_SUPERCOMPUTER_RAMDISK=/dev/shm
#   SLAIF_SUPERCOMPUTER_KEEP_DBS=1
#   SLAIF_SUPERCOMPUTER_KEEP_WORKDIR=1
#   SLAIF_SUPERCOMPUTER_SKIP_BROWSER=1
#   SLAIF_SUPERCOMPUTER_SKIP_DOCKER=1
#   SLAIF_SUPERCOMPUTER_PARALLEL_E2E=1
#   SLAIF_SUPERCOMPUTER_PGHOST=/var/run/postgresql
#   SLAIF_SUPERCOMPUTER_PGPORT=5432
#   SLAIF_SUPERCOMPUTER_PGUSER=postgres
#   SLAIF_SUPERCOMPUTER_DB_PREFIX=slaif_hpc_test_custom
#   SLAIF_SUPERCOMPUTER_START_POSTGRES=1  # reserved future hook; not implemented here
#
# Safety contract:
#   - never uses DATABASE_URL for destructive setup
#   - gives every DB-backed shard its own TEST_DATABASE_URL
#   - refuses APP_ENV=production and RUN_UPSTREAM_TESTS=1
#   - does not require provider keys or real email

usage() {
  cat >&2 <<'EOF'
Usage: scripts/test-supercomputer-sharded.sh <workers>

<workers> must be a positive integer. Example:
  scripts/test-supercomputer-sharded.sh 128

Optional behavior is controlled by SLAIF_SUPERCOMPUTER_* environment variables;
see the script header and docs/testing-parallelism.md.
EOF
}

die() {
  echo "ERROR: $*" >&2
  exit 1
}

if [[ $# -ne 1 ]]; then
  usage
  exit 2
fi

WORKERS="$1"
if [[ ! "$WORKERS" =~ ^[1-9][0-9]*$ ]]; then
  usage
  die "worker count must be a positive integer"
fi

if [[ "${APP_ENV:-}" == "production" ]]; then
  die "refusing to run when APP_ENV=production"
fi

if [[ "${RUN_UPSTREAM_TESTS:-}" == "1" ]]; then
  die "refusing to run with RUN_UPSTREAM_TESTS=1; normal tests must not call upstream providers"
fi

if [[ "${SLAIF_SUPERCOMPUTER_START_POSTGRES:-}" == "1" ]]; then
  die "SLAIF_SUPERCOMPUTER_START_POSTGRES=1 is reserved for a future user-owned temp cluster hook"
fi

if [[ -n "${PYTHON:-}" ]]; then
  PY="$PYTHON"
elif [[ -x ".venv/bin/python" ]]; then
  PY=".venv/bin/python"
else
  PY="python"
fi

command -v "$PY" >/dev/null 2>&1 || die "Python not found. Run python -m pip install -e \".[dev]\" first."

CPU_COUNT="$("$PY" - <<'PY'
import os
print(os.cpu_count() or 1)
PY
)"
if (( WORKERS > CPU_COUNT )); then
  echo "Warning: requested workers ($WORKERS) exceed visible CPU cores ($CPU_COUNT); continuing." >&2
fi

BRANCH="$(git branch --show-current 2>/dev/null || echo unknown)"
COMMIT="$(git rev-parse HEAD 2>/dev/null || echo unknown)"
SHORT_SHA="$(git rev-parse --short=12 HEAD 2>/dev/null || echo unknown)"
RUN_STAMP="$(date -u +%Y%m%d-%H%M%S)"
USER_NAME="${USER:-$(id -un 2>/dev/null || echo user)}"

choose_run_root() {
  local preferred="${SLAIF_SUPERCOMPUTER_RAMDISK:-}"
  if [[ -n "$preferred" && -d "$preferred" && -w "$preferred" ]]; then
    echo "$preferred"
    return
  fi
  if [[ -d /dev/shm && -w /dev/shm ]]; then
    echo /dev/shm
    return
  fi
  echo "${TMPDIR:-/tmp}"
}

RUN_BASE="$(choose_run_root)"
RUN_DIR="${RUN_BASE%/}/slaif-gateway-tests-${USER_NAME}-${RUN_STAMP}-$$"
LOG_DIR="$RUN_DIR/logs"
JUNIT_DIR="$RUN_DIR/junit"
TMP_ROOT="$RUN_DIR/tmp"
SUMMARY_FILE="$RUN_DIR/SUMMARY.md"
SUMMARY_TSV="$RUN_DIR/summary.tsv"
DB_LIST_FILE="$RUN_DIR/created-dbs.txt"
SHARD_STATUS_DIR="$RUN_DIR/shard-status"
mkdir -p "$LOG_DIR" "$JUNIT_DIR" "$TMP_ROOT" "$SHARD_STATUS_DIR"
: > "$SUMMARY_TSV"
: > "$DB_LIST_FILE"

export TMPDIR="$TMP_ROOT"

if [[ -n "${DATABASE_URL:-}" ]]; then
  echo "Info: DATABASE_URL is set but will be ignored for destructive test setup." >&2
fi

log() {
  printf '[%s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"
}

seconds_now() {
  date +%s
}

record_result() {
  local phase="$1"
  local status="$2"
  local duration="$3"
  local log_path="$4"
  local note="$5"
  printf '%s\t%s\t%s\t%s\t%s\n' "$phase" "$status" "$duration" "$log_path" "$note" >> "$SUMMARY_TSV"
}

ERROR_EXCERPT_PATTERN='FAILED|ERROR|Traceback|AssertionError|OperationalError|Timeout|Exception|FATAL|could not|refused|permission denied|database .* does not exist|connection'

print_bounded_log_excerpt() {
  local log_path="$1"
  if [[ -z "$log_path" || ! -f "$log_path" ]]; then
    echo "(log unavailable)"
    return 0
  fi
  local matches
  matches="$(grep -Ein "$ERROR_EXCERPT_PATTERN" "$log_path" 2>/dev/null | head -80 || true)"
  if [[ -n "$matches" ]]; then
    printf '%s\n' "$matches"
    return 0
  fi
  echo "(no error pattern match; last 120 log lines)"
  tail -120 "$log_path" 2>/dev/null || true
}

run_logged() {
  local phase="$1"
  local log_path="$2"
  shift 2
  local start end duration status
  start="$(seconds_now)"
  log "Starting $phase"
  set +e
  {
    echo "Phase: $phase"
    echo "Started: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "Command: $*"
    "$@"
  } >"$log_path" 2>&1
  status=$?
  set -e
  end="$(seconds_now)"
  duration=$((end - start))
  if [[ "$status" -eq 0 ]]; then
    record_result "$phase" "PASS" "$duration" "$log_path" ""
    log "Finished $phase: PASS (${duration}s)"
  else
    record_result "$phase" "FAIL" "$duration" "$log_path" "exit=$status"
    OVERALL_FAIL=1
    log "Finished $phase: FAIL (${duration}s; log: $log_path)"
  fi
  return 0
}

DB_PREFIX_RAW="${SLAIF_SUPERCOMPUTER_DB_PREFIX:-slaif_hpc_test_${SHORT_SHA}_$$}"
DB_PREFIX="$(printf '%s' "$DB_PREFIX_RAW" | tr '[:upper:]-' '[:lower:]_' | tr -cd 'a-z0-9_')"
[[ -n "$DB_PREFIX" ]] || die "empty database prefix after sanitization"
[[ "$DB_PREFIX" == *test* || "$DB_PREFIX" == *hpc* || "$DB_PREFIX" == slaif_hpc* ]] || {
  die "database prefix must include test/hpc marker"
}

setup_pg_env() {
  if [[ -n "${SLAIF_SUPERCOMPUTER_PGHOST:-}" ]]; then
    export PGHOST="$SLAIF_SUPERCOMPUTER_PGHOST"
  fi
  if [[ -n "${SLAIF_SUPERCOMPUTER_PGPORT:-}" ]]; then
    export PGPORT="$SLAIF_SUPERCOMPUTER_PGPORT"
  fi
  if [[ -n "${SLAIF_SUPERCOMPUTER_PGUSER:-}" ]]; then
    export PGUSER="$SLAIF_SUPERCOMPUTER_PGUSER"
  fi
}

db_url() {
  local db_name="$1"
  "$PY" - "$db_name" <<'PY'
import os
import sys
from urllib.parse import quote, urlencode

db = sys.argv[1]
host = os.getenv("PGHOST", "")
port = os.getenv("PGPORT", "")
user = os.getenv("PGUSER", "")
password = os.getenv("PGPASSWORD", "")

auth = ""
if user:
    auth = quote(user, safe="")
    if password:
        auth += ":" + quote(password, safe="")
    auth += "@"

if host and host.startswith("/"):
    query = {"host": host}
    if port:
        query["port"] = port
    print(f"postgresql+asyncpg://{auth}/{quote(db, safe='')}?{urlencode(query)}")
elif host:
    port_part = f":{port}" if port else ""
    print(f"postgresql+asyncpg://{auth}{host}{port_part}/{quote(db, safe='')}")
else:
    print(f"postgresql+asyncpg://{auth}/{quote(db, safe='')}")
PY
}

safe_db_name() {
  local db_name="$1"
  [[ "$db_name" == "$DB_PREFIX"_* ]] || return 1
  [[ "$db_name" == *test* || "$db_name" == *hpc* ]] || return 1
  [[ "$db_name" =~ ^[a-z0-9_]+$ ]] || return 1
}

create_db() {
  local db_name="$1"
  safe_db_name "$db_name" || die "refusing to create unsafe database name: $db_name"
  createdb "$db_name"
  printf '%s\n' "$db_name" >> "$DB_LIST_FILE"
}

drop_db() {
  local db_name="$1"
  safe_db_name "$db_name" || die "refusing to drop unsafe database name: $db_name"
  dropdb --if-exists "$db_name" >/dev/null 2>&1 || true
}

cleanup() {
  local exit_code=$?
  if [[ "${SLAIF_SUPERCOMPUTER_KEEP_DBS:-0}" != "1" && -f "$DB_LIST_FILE" ]]; then
    tac "$DB_LIST_FILE" 2>/dev/null | while IFS= read -r db_name; do
      [[ -n "$db_name" ]] || continue
      drop_db "$db_name"
    done
  fi
  if [[ "${SLAIF_SUPERCOMPUTER_KEEP_WORKDIR:-0}" == "1" ]]; then
    echo "Keeping run directory: $RUN_DIR" >&2
  fi
  exit "$exit_code"
}
trap cleanup EXIT INT TERM

check_python_dependency() {
  local module="$1"
  "$PY" - <<PY >/dev/null 2>&1
import $module
PY
}

postgres_available() {
  setup_pg_env
  command -v psql >/dev/null 2>&1 || return 1
  command -v createdb >/dev/null 2>&1 || return 1
  command -v dropdb >/dev/null 2>&1 || return 1
  psql -d postgres -Atc "select 1" >/dev/null 2>&1 || return 1
  local probe_db="${DB_PREFIX}_probe"
  safe_db_name "$probe_db" || return 1
  createdb "$probe_db" >/dev/null 2>&1 || return 1
  printf '%s\n' "$probe_db" >> "$DB_LIST_FILE"
  dropdb --if-exists "$probe_db" >/dev/null 2>&1 || return 1
  return 0
}

hidden_unicode_scan() {
  "$PY" - <<'PY'
from pathlib import Path
import subprocess
import unicodedata

suffixes = {".md", ".py", ".sh", ".toml", ".yml", ".yaml", ".txt", ".example"}
result = subprocess.run(["git", "ls-files"], check=True, text=True, capture_output=True)
bad = []
for line in result.stdout.splitlines():
    path = Path(line)
    if not path.is_file() or path.suffix not in suffixes:
        continue
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        continue
    for line_no, value in enumerate(text.splitlines(), start=1):
        for col_no, ch in enumerate(value, start=1):
            if unicodedata.category(ch) == "Cf":
                bad.append((str(path), line_no, col_no, unicodedata.name(ch, "UNKNOWN")))
if bad:
    for item in bad:
        print(item)
    raise SystemExit(1)
print("No hidden Unicode format-control characters found in tracked text files.")
PY
}

safety_scan() {
  local script="scripts/test-supercomputer-sharded.sh"
  git ls-files | grep -E '(^|/)\.codex($|/)' && return 1
  local forbidden_db_pattern
  forbidden_db_pattern="dropdb.*DATABASE""_URL|createdb.*DATABASE""_URL|psql.*DATABASE""_URL"
  if grep -E "$forbidden_db_pattern" "$script"; then
    echo "Found destructive DATABASE_URL pattern in $script" >&2
    return 1
  fi
  local forbidden_key_pattern
  forbidden_key_pattern="OPENAI""_API_KEY=|OPENAI_UPSTREAM""_API_KEY=sk-|OPENROUTER""_API_KEY=sk-"
  if grep -E "$forbidden_key_pattern" "$script"; then
    echo "Found forbidden upstream-key or upstream-test pattern in $script" >&2
    return 1
  fi
  echo "Safety scan passed."
}

find_test_files() {
  local dir="$1"
  if [[ -d "$dir" ]]; then
    find "$dir" -type f -name 'test_*.py' | sort
  fi
}

run_db_file_job() {
  local suite="$1"
  local index="$2"
  local file="$3"
  local status_file="$SHARD_STATUS_DIR/${suite}-${index}.status"
  local safe_file
  safe_file="$(printf '%s' "$file" | tr '/.' '__' | tr -cd 'A-Za-z0-9_')"
  local db_name="${DB_PREFIX}_${suite}_${index}"
  local log_path="$LOG_DIR/${suite}-${index}-${safe_file}.log"
  local junit_path="$JUNIT_DIR/${suite}-${index}-${safe_file}.xml"
  local start end duration status url
  start="$(seconds_now)"
  set +e
  {
    echo "Suite: $suite"
    echo "File: $file"
    echo "Database: $db_name"
    create_db "$db_name"
    url="$(db_url "$db_name")"
    mkdir -p "$TMP_ROOT/${suite}-${index}"
    env \
      -u DATABASE_URL \
      -u TEST_REDIS_URL \
      APP_ENV=test \
      RUN_UPSTREAM_TESTS=0 \
      ENABLE_EMAIL_DELIVERY=false \
      DATABASE_POOL_SIZE=1 \
      DATABASE_MAX_OVERFLOW=0 \
      DATABASE_POOL_TIMEOUT_SECONDS=30 \
      TMPDIR="$TMP_ROOT/${suite}-${index}" \
      TEST_DATABASE_URL="$url" \
      "$PY" -m pytest "$file" -rs --junitxml="$junit_path"
  } >"$log_path" 2>&1
  status=$?
  set -e
  end="$(seconds_now)"
  duration=$((end - start))
  if [[ "$status" -eq 0 ]]; then
    printf '%s\tPASS\t%s\t%s\t%s\n' "$suite" "$duration" "$log_path" "$file" > "$status_file"
  else
    printf '%s\tFAIL\t%s\t%s\t%s\n' "$suite" "$duration" "$log_path" "$file" > "$status_file"
  fi
  if [[ "${SLAIF_SUPERCOMPUTER_KEEP_DBS:-0}" != "1" ]]; then
    drop_db "$db_name"
  fi
  exit "$status"
}

throttle_jobs() {
  local limit="$1"
  while (( $(jobs -pr | wc -l) >= limit )); do
    sleep 0.2
  done
}

run_db_suite() {
  local suite="$1"
  local dir="$2"
  local max_concurrency="$3"
  local files_file="$RUN_DIR/${suite}-files.txt"
  [[ "$max_concurrency" =~ ^[1-9][0-9]*$ ]] || die "invalid $suite concurrency: $max_concurrency"
  find_test_files "$dir" > "$files_file"
  local count
  count="$(wc -l < "$files_file" | tr -d ' ')"
  if [[ "$count" == "0" ]]; then
    record_result "$suite" "SKIP" "0" "" "no test files found"
    return 0
  fi
  if [[ "$POSTGRES_STATUS" != "available" ]]; then
    record_result "$suite" "SKIP" "0" "" "$POSTGRES_STATUS"
    return 0
  fi

  log "Starting $suite sharded run with $count files and max concurrency $max_concurrency"
  local suite_start index file
  suite_start="$(seconds_now)"
  index=0
  while IFS= read -r file; do
    [[ -n "$file" ]] || continue
    index=$((index + 1))
    throttle_jobs "$max_concurrency"
    run_db_file_job "$suite" "$index" "$file" &
  done < "$files_file"

  local failed=0
  local pid
  for pid in $(jobs -p); do
    if ! wait "$pid"; then
      failed=$((failed + 1))
    fi
  done

  local duration passed failed_files
  duration=$(($(seconds_now) - suite_start))
  passed="$(grep -l $'\tPASS\t' "$SHARD_STATUS_DIR"/${suite}-*.status 2>/dev/null | wc -l | tr -d ' ')"
  failed_files="$(grep -l $'\tFAIL\t' "$SHARD_STATUS_DIR"/${suite}-*.status 2>/dev/null | wc -l | tr -d ' ')"
  if [[ "$failed" -eq 0 && "$failed_files" -eq 0 ]]; then
    record_result "$suite" "PASS" "$duration" "$SHARD_STATUS_DIR" "files=$count passed=$passed failed=0 max_concurrency=$max_concurrency"
    log "Finished $suite: PASS (${duration}s; files=$count)"
  else
    record_result "$suite" "FAIL" "$duration" "$SHARD_STATUS_DIR" "files=$count passed=$passed failed=$failed_files max_concurrency=$max_concurrency"
    OVERALL_FAIL=1
    log "Finished $suite: FAIL (${duration}s; failed files=$failed_files)"
  fi
}

run_browser_suite() {
  local suite="browser"
  if [[ "${SLAIF_SUPERCOMPUTER_SKIP_BROWSER:-0}" == "1" ]]; then
    BROWSER_STATUS="skipped: SLAIF_SUPERCOMPUTER_SKIP_BROWSER=1"
    record_result "$suite" "SKIP" "0" "" "SLAIF_SUPERCOMPUTER_SKIP_BROWSER=1"
    return 0
  fi
  if ! check_python_dependency "playwright"; then
    BROWSER_STATUS="skipped: playwright Python package unavailable"
    record_result "$suite" "SKIP" "0" "" "playwright Python package unavailable"
    return 0
  fi
  if [[ "$POSTGRES_STATUS" != "available" ]]; then
    BROWSER_STATUS="skipped: $POSTGRES_STATUS"
    record_result "$suite" "SKIP" "0" "" "$POSTGRES_STATUS"
    return 0
  fi
  local db_name="${DB_PREFIX}_browser_1"
  local log_path="$LOG_DIR/browser.log"
  local junit_path="$JUNIT_DIR/browser.xml"
  local start end duration status url
  start="$(seconds_now)"
  set +e
  {
    echo "Suite: browser"
    echo "Database: $db_name"
    create_db "$db_name"
    url="$(db_url "$db_name")"
    env \
      -u DATABASE_URL \
      -u TEST_REDIS_URL \
      APP_ENV=test \
      RUN_UPSTREAM_TESTS=0 \
      ENABLE_EMAIL_DELIVERY=false \
      DATABASE_POOL_SIZE=1 \
      DATABASE_MAX_OVERFLOW=0 \
      DATABASE_POOL_TIMEOUT_SECONDS=30 \
      TEST_DATABASE_URL="$url" \
      "$PY" -m pytest tests/browser -m playwright -vv -rs --junitxml="$junit_path"
  } >"$log_path" 2>&1
  status=$?
  set -e
  end="$(seconds_now)"
  duration=$((end - start))
  if [[ "${SLAIF_SUPERCOMPUTER_KEEP_DBS:-0}" != "1" ]]; then
    drop_db "$db_name"
  fi
  if [[ "$status" -eq 0 ]]; then
    BROWSER_STATUS="ran serial: PASS"
    record_result "$suite" "PASS" "$duration" "$log_path" "serial isolated DB"
  else
    BROWSER_STATUS="ran serial: FAIL ($log_path)"
    record_result "$suite" "FAIL" "$duration" "$log_path" "exit=$status"
    OVERALL_FAIL=1
  fi
}

write_summary() {
  local total_duration
  total_duration=$(($(seconds_now) - START_TIME))
  {
    echo "SUPERCOMPUTER TEST SUMMARY"
    echo
    echo "commit: $COMMIT"
    echo "branch: $BRANCH"
    echo "workers: $WORKERS"
    echo "run_dir: $RUN_DIR"
    echo "hostname: $(hostname)"
    echo "cpu_count: $CPU_COUNT"
    echo "total_duration_seconds: $total_duration"
    echo "postgresql_status: $POSTGRES_STATUS"
    echo "db_isolation: generated per-shard TEST_DATABASE_URL values only; DATABASE_URL ignored for destructive setup"
    echo "e2e_mode: $E2E_MODE"
    echo "browser_status: $BROWSER_STATUS"
    echo
    echo "| phase | status | duration_s | log | note |"
    echo "| --- | --- | ---: | --- | --- |"
    while IFS=$'\t' read -r phase status duration log_path note; do
      echo "| $phase | $status | $duration | $log_path | $note |"
    done < "$SUMMARY_TSV"
    echo
    echo "failures:"
    if grep -q $'\tFAIL\t' "$SUMMARY_TSV"; then
      grep $'\tFAIL\t' "$SUMMARY_TSV" || true
    else
      echo "none"
    fi
    echo
    echo "failing_shard_status_entries:"
    local shard_status_matches
    shard_status_matches="$(find "$SHARD_STATUS_DIR" -name '*.status' -print0 | xargs -r -0 grep -H $'\tFAIL\t' 2>/dev/null || true)"
    if [[ -n "$shard_status_matches" ]]; then
      printf '%s\n' "$shard_status_matches"
    else
      echo "none"
    fi
    echo
    echo "failing_shard_log_paths:"
    local shard_failures=0
    while IFS=$'\t' read -r suite status duration log_path file; do
      if [[ "$status" == "FAIL" ]]; then
        shard_failures=1
        echo "- $suite $file: $log_path"
      fi
    done < <(find "$SHARD_STATUS_DIR" -name '*.status' -print0 | xargs -r -0 cat 2>/dev/null)
    if [[ "$shard_failures" -eq 0 ]]; then
      echo "none"
    fi
    echo
    echo "skips:"
    if grep -q $'\tSKIP\t' "$SUMMARY_TSV"; then
      grep $'\tSKIP\t' "$SUMMARY_TSV" || true
    else
      echo "none"
    fi
    echo
    echo "slowest_shards:"
    find "$SHARD_STATUS_DIR" -name '*.status' -print0 \
      | xargs -r -0 cat 2>/dev/null \
      | sort -t $'\t' -k3,3nr \
      | head -20 || true
    echo
    echo "failure_log_excerpts:"
    local excerpts=0
    while IFS=$'\t' read -r phase status duration log_path note; do
      if [[ "$status" == "FAIL" && -n "$log_path" && -f "$log_path" ]]; then
        excerpts=1
        echo "### $phase"
        echo "log: $log_path"
        print_bounded_log_excerpt "$log_path"
        echo
      fi
    done < "$SUMMARY_TSV"
    while IFS=$'\t' read -r suite status duration log_path file; do
      if [[ "$status" == "FAIL" ]]; then
        excerpts=1
        echo "### $suite: $file"
        echo "log: $log_path"
        print_bounded_log_excerpt "$log_path"
        echo
      fi
    done < <(find "$SHARD_STATUS_DIR" -name '*.status' -print0 | xargs -r -0 cat 2>/dev/null)
    if [[ "$excerpts" -eq 0 ]]; then
      echo "none"
    fi
    echo
    echo "safety_confirmations:"
    echo "- RUN_UPSTREAM_TESTS=1 refused; normal run did not request real upstream calls."
    echo "- DATABASE_URL was not used for destructive setup."
    echo "- PostgreSQL availability required a generated create/drop database probe."
    echo "- DB-backed shard subprocesses received isolated TEST_DATABASE_URL values."
    echo "- Integration DB files used max concurrency $WORKERS."
    echo "- E2E DB files used max concurrency $E2E_CONCURRENCY."
    echo "- Browser tests were serial or skipped."
    echo "- Real email delivery was disabled in shard subprocess environments."
  } > "$SUMMARY_FILE"
  cat "$SUMMARY_FILE"
}

START_TIME="$(seconds_now)"
OVERALL_FAIL=0
BROWSER_STATUS="not run"

log "Run directory: $RUN_DIR"
{
  echo "branch: $BRANCH"
  echo "commit: $COMMIT"
  echo "git_status:"
  git status --short || true
  echo "hostname: $(hostname)"
  echo "date_utc: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "cpu_count: $CPU_COUNT"
  echo "workers_requested: $WORKERS"
  echo "memory:"
  free -h 2>/dev/null || true
  echo "disk:"
  df -h "$RUN_BASE" 2>/dev/null || true
  echo "python:"
  "$PY" --version
  "$PY" -m pytest --version 2>/dev/null || true
  psql --version 2>/dev/null || true
  redis-server --version 2>/dev/null || true
  docker --version 2>/dev/null || true
} > "$LOG_DIR/environment.log" 2>&1
record_result "environment" "PASS" "0" "$LOG_DIR/environment.log" "dirty tree recorded if present"

if ! check_python_dependency "pytest"; then
  die "pytest is unavailable. Run $PY -m pip install -e \".[dev]\" first."
fi
if ! check_python_dependency "xdist"; then
  die "pytest-xdist is unavailable. Run $PY -m pip install -e \".[dev]\" first."
fi
if ! check_python_dependency "ruff"; then
  die "ruff is unavailable. Run $PY -m pip install -e \".[dev]\" first."
fi
if ! check_python_dependency "alembic"; then
  die "alembic is unavailable. Run $PY -m pip install -e \".[dev]\" first."
fi
record_result "dependency_sanity" "PASS" "0" "" "pytest, xdist, ruff, alembic available"

if postgres_available; then
  POSTGRES_STATUS="available"
else
  POSTGRES_STATUS="SKIP: PostgreSQL psql/createdb/dropdb unavailable, connection failed, or generated create/drop probe failed"
fi

E2E_CONCURRENCY=1
E2E_MODE="default serial (max concurrency 1)"
if [[ "${SLAIF_SUPERCOMPUTER_PARALLEL_E2E:-0}" == "1" ]]; then
  E2E_CONCURRENCY="$WORKERS"
  E2E_MODE="explicit parallel via SLAIF_SUPERCOMPUTER_PARALLEL_E2E=1 (max concurrency $WORKERS)"
fi

run_logged "ruff" "$LOG_DIR/ruff.log" "$PY" -m ruff check .
run_logged "alembic_heads" "$LOG_DIR/alembic-heads.log" "$PY" -m alembic heads
run_logged "git_diff_check" "$LOG_DIR/git-diff-check.log" git diff --check
run_logged "hidden_unicode" "$LOG_DIR/hidden-unicode.log" hidden_unicode_scan
run_logged "safety_scan" "$LOG_DIR/safety-scan.log" safety_scan

if [[ "${SLAIF_SUPERCOMPUTER_SKIP_DOCKER:-0}" == "1" ]]; then
  record_result "docker_compose_config" "SKIP" "0" "" "SLAIF_SUPERCOMPUTER_SKIP_DOCKER=1"
elif command -v docker >/dev/null 2>&1; then
  run_logged "docker_compose_config" "$LOG_DIR/docker-compose-config.log" docker compose config
else
  record_result "docker_compose_config" "SKIP" "0" "" "docker unavailable"
fi

run_logged "unit" "$LOG_DIR/unit.log" env \
  -u DATABASE_URL \
  -u TEST_DATABASE_URL \
  -u TEST_REDIS_URL \
  APP_ENV=test \
  RUN_UPSTREAM_TESTS=0 \
  PYTEST_XDIST_WORKERS="$WORKERS" \
  PATH="$PWD/.venv/bin:$PATH" \
  scripts/test-unit-parallel.sh

run_db_suite "integration" "tests/integration" "$WORKERS"
run_db_suite "e2e" "tests/e2e" "$E2E_CONCURRENCY"
run_browser_suite

write_summary
echo "Summary path: $SUMMARY_FILE"

if [[ "$OVERALL_FAIL" -ne 0 ]]; then
  exit 1
fi
