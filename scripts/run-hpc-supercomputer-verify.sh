#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat >&2 <<'EOF'
Usage: scripts/run-hpc-supercomputer-verify.sh [workers]

Prepare a user-local HPC test environment and run the supercomputer harness.

Optional environment variables:
  SLAIF_HPC_GIT_PULL=1        Run cleaned git fetch/switch/pull before tests
  SLAIF_HPC_PGPORT=55432      TCP port for the temporary PostgreSQL cluster
  SLAIF_HPC_RUN_LOG=...       Harness tee log path
EOF
}

log() {
  printf '[run-hpc-supercomputer-verify] %s\n' "$*" >&2
}

die() {
  log "ERROR: $*"
  exit 1
}

if [[ "${APP_ENV:-}" == "production" ]]; then
  die "refusing to run HPC verification when APP_ENV=production"
fi

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

WORKERS="${1:-128}"
[[ "$WORKERS" =~ ^[1-9][0-9]*$ ]] || die "worker count must be a positive integer"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SETUP_SCRIPT="${REPO_ROOT}/scripts/setup-hpc-test-env.sh"
ENV_FILE="$(mktemp "${TMPDIR:-/tmp}/slaif-hpc-env.XXXXXX")"
RUN_LOG="${SLAIF_HPC_RUN_LOG:-/tmp/slaif-supercomputer-run.log}"
RUNROOT_BASE="${SLAIF_HPC_RUNROOT_BASE:-/dev/shm/${USER:-user}/slaif-hpc-pg}"
PGROOT="${RUNROOT_BASE}/cluster"
PGDATA="${PGROOT}/data"
PGSOCK="${PGROOT}/socket"
PGLOG="${PGROOT}/postgres.log"
WRAPBIN="${RUNROOT_BASE}/bin"
PGPORT="${SLAIF_HPC_PGPORT:-55432}"

cleanup() {
  local rc=$?
  if [[ -x "${WRAPBIN}/pg_ctl" && -s "${PGDATA}/PG_VERSION" ]]; then
    "${WRAPBIN}/pg_ctl" -D "${PGDATA}" -m fast stop > "${RUNROOT_BASE}/pg_stop.log" 2>&1 || true
  fi
  rm -f "$ENV_FILE"
  exit "$rc"
}
trap cleanup EXIT INT TERM

clean_git() {
  env -u LD_LIBRARY_PATH -u LIBRARY_PATH -u CPATH -u PKG_CONFIG_PATH -u PYTHONPATH git "$@"
}

"$SETUP_SCRIPT" --write-env-file "$ENV_FILE"
# shellcheck disable=SC1090
. "$ENV_FILE"

if [[ "${SLAIF_HPC_GIT_PULL:-0}" == "1" ]]; then
  log "Running cleaned git fetch/switch/pull"
  (
    cd "$REPO_ROOT"
    clean_git fetch origin
    clean_git switch main
    clean_git pull --ff-only origin main
  )
fi

mkdir -p "$PGROOT" "$PGSOCK" "$WRAPBIN"

RUNTIME_LD_LIBRARY_PATH="${LD_LIBRARY_PATH:-}"
for tool in psql createdb dropdb initdb pg_ctl postgres; do
  cat > "${WRAPBIN}/${tool}" <<EOF
#!/usr/bin/env bash
export LD_LIBRARY_PATH='${RUNTIME_LD_LIBRARY_PATH}'
exec '${SLAIF_HPC_POSTGRES_PREFIX}/bin/${tool}' "\$@"
EOF
  chmod +x "${WRAPBIN}/${tool}"
done

if [[ ! -s "${PGDATA}/PG_VERSION" ]]; then
  log "Initializing temporary PostgreSQL cluster at ${PGDATA}"
  rm -rf "$PGDATA"
  "${WRAPBIN}/initdb" -D "$PGDATA" -A trust --username "${USER:-user}" --no-locale > "${RUNROOT_BASE}/initdb.log" 2>&1
fi

log "Starting temporary PostgreSQL cluster on 127.0.0.1:${PGPORT}"
"${WRAPBIN}/pg_ctl" -D "$PGDATA" -l "$PGLOG" -o "-k ${PGSOCK} -h 127.0.0.1 -p ${PGPORT}" start > "${RUNROOT_BASE}/pg_start.log" 2>&1

export PGHOST="127.0.0.1"
export PGPORT="${PGPORT}"
export PGUSER="${USER:-user}"
export SLAIF_SUPERCOMPUTER_PGHOST="127.0.0.1"
export SLAIF_SUPERCOMPUTER_PGPORT="${PGPORT}"
export SLAIF_SUPERCOMPUTER_PGUSER="${USER:-user}"
export ENABLE_EMAIL_DELIVERY="false"
export PYTHON="${REPO_ROOT}/.venv/bin/python"
export PATH="${WRAPBIN}:${REPO_ROOT}/.venv/bin:${PATH}"

unset DATABASE_URL || true
unset TEST_DATABASE_URL || true
unset RUN_UPSTREAM_TESTS || true
unset OPENAI_API_KEY || true
unset OPENAI_UPSTREAM_API_KEY || true
unset OPENROUTER_API_KEY || true

log "Probing PostgreSQL create/drop access"
psql -d postgres -Atc "select version()"
probe_db="slaif_hpc_probe_${USER:-user}_$$"
createdb "$probe_db"
dropdb --if-exists "$probe_db"

(
  cd "$REPO_ROOT"
  log "Current HEAD: $(clean_git rev-parse HEAD)"
  clean_git status --short || true
  scripts/test-supercomputer-sharded.sh "$WORKERS" 2>&1 | tee "$RUN_LOG"
  harness_rc="${PIPESTATUS[0]}"
  summary_path="$(grep -E '^Summary path: ' "$RUN_LOG" | tail -1 | sed 's/^Summary path: //')"
  echo "SUMMARY_PATH=${summary_path}"
  if [[ -n "$summary_path" && -f "$summary_path" ]]; then
    cat "$summary_path"
  else
    tail -200 "$RUN_LOG" || true
  fi
  exit "$harness_rc"
)

