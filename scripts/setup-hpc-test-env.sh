#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat >&2 <<'EOF'
Usage: scripts/setup-hpc-test-env.sh [--write-env-file PATH]

Prepare a user-local HPC test environment for the SLAIF supercomputer harness.

Optional environment variables:
  SLAIF_HPC_PYROOT                   Explicit Python installation root
  SLAIF_HPC_PYTHON_MODULE            HPC module name that provides python3 >= 3.11
  SLAIF_HPC_POSTGRES_PREFIX          User-local PostgreSQL install prefix
  SLAIF_HPC_BROWSER_LIB_PREFIX       User-local browser library prefix
  SLAIF_HPC_PLAYWRIGHT_BROWSERS_PATH User-local Playwright browser path
EOF
}

log() {
  printf '[setup-hpc-test-env] %s\n' "$*" >&2
}

die() {
  log "ERROR: $*"
  exit 1
}

if [[ "${APP_ENV:-}" == "production" ]]; then
  die "refusing to prepare HPC test environment when APP_ENV=production"
fi

WRITE_ENV_FILE=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --write-env-file)
      [[ $# -ge 2 ]] || die "--write-env-file requires a path"
      WRITE_ENV_FILE="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      usage
      die "unknown argument: $1"
      ;;
  esac
done

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
POSTGRES_PREFIX="${SLAIF_HPC_POSTGRES_PREFIX:-/dev/shm/${USER:-user}/slaif-pg-tools}"
BROWSER_LIB_PREFIX="${SLAIF_HPC_BROWSER_LIB_PREFIX:-/dev/shm/${USER:-user}/slaif-browser-libs}"
PLAYWRIGHT_BROWSERS_PATH="${SLAIF_HPC_PLAYWRIGHT_BROWSERS_PATH:-/dev/shm/${USER:-user}/ms-playwright}"

MODULE_INIT=""
source_modules_init() {
  local candidate
  for candidate in \
    /etc/profile.d/modules.sh \
    /usr/share/Modules/init/bash \
    /usr/share/modules/init/bash \
    /usr/local/Modules/init/bash \
    /usr/share/lmod/lmod/init/bash \
    /opt/apps/lmod/lmod/init/bash
  do
    if [[ -r "$candidate" ]]; then
      # shellcheck disable=SC1090
      . "$candidate"
      MODULE_INIT="$candidate"
      return 0
    fi
  done
  return 1
}

python_is_modern() {
  local python_bin="$1"
  local pyroot="${2:-}"
  if [[ -n "$pyroot" && -d "${pyroot}/lib" ]]; then
    LD_LIBRARY_PATH="${pyroot}/lib${LD_LIBRARY_PATH+:${LD_LIBRARY_PATH}}" "$python_bin" - <<'PY' >/dev/null 2>&1
import sys
raise SystemExit(0 if sys.version_info >= (3, 11) else 1)
PY
    return $?
  fi
  "$python_bin" - <<'PY' >/dev/null 2>&1
import sys
raise SystemExit(0 if sys.version_info >= (3, 11) else 1)
PY
}

choose_python() {
  local python_bin=""
  local pyroot=""
  local venv_home=""
  local auto_module=""

  if [[ -n "${SLAIF_HPC_PYROOT:-}" ]]; then
    python_bin="${SLAIF_HPC_PYROOT}/bin/python3"
    [[ -x "$python_bin" ]] || die "SLAIF_HPC_PYROOT does not provide bin/python3"
    python_is_modern "$python_bin" "$SLAIF_HPC_PYROOT" || die "SLAIF_HPC_PYROOT python3 is older than 3.11"
    pyroot="$SLAIF_HPC_PYROOT"
  elif [[ -f "${REPO_ROOT}/.venv/pyvenv.cfg" ]]; then
    venv_home="$(awk -F ' = ' '$1 == "home" {print $2}' "${REPO_ROOT}/.venv/pyvenv.cfg" | tail -1)"
    if [[ -n "$venv_home" && -x "${venv_home}/python3" ]] && python_is_modern "${venv_home}/python3" "$(cd "${venv_home}/.." && pwd)"; then
      python_bin="${venv_home}/python3"
      pyroot="$(cd "${venv_home}/.." && pwd)"
    fi
  elif command -v python3 >/dev/null 2>&1 && python_is_modern "$(command -v python3)"; then
    python_bin="$(command -v python3)"
    pyroot="$(cd "$(dirname "$python_bin")/.." && pwd)"
  elif [[ -n "${SLAIF_HPC_PYTHON_MODULE:-}" ]]; then
    source_modules_init || die "could not source module init while SLAIF_HPC_PYTHON_MODULE is set"
    module load "$SLAIF_HPC_PYTHON_MODULE"
    command -v python3 >/dev/null 2>&1 || die "module $SLAIF_HPC_PYTHON_MODULE did not provide python3"
    python_bin="$(command -v python3)"
    python_is_modern "$python_bin" || die "module $SLAIF_HPC_PYTHON_MODULE provides python3 older than 3.11"
    pyroot="$(cd "$(dirname "$python_bin")/.." && pwd)"
  else
    if source_modules_init; then
      auto_module="$(module -t spider Python 2>&1 | sed -n 's/^[[:space:]]*\(Python\/[^[:space:]]*\)$/\1/p' | sort -V | tail -1)"
      if [[ -n "$auto_module" ]]; then
        module load "$auto_module"
        command -v python3 >/dev/null 2>&1 || die "auto-discovered module $auto_module did not provide python3"
        python_bin="$(command -v python3)"
        python_is_modern "$python_bin" || die "auto-discovered module $auto_module provides python3 older than 3.11"
        pyroot="$(cd "$(dirname "$python_bin")/.." && pwd)"
      fi
    fi
    [[ -n "$python_bin" ]] || die "no Python 3.11+ found; set SLAIF_HPC_PYROOT or SLAIF_HPC_PYTHON_MODULE"
  fi

  printf '%s\n%s\n' "$python_bin" "$pyroot"
}

MICROMAMBA_BIN="$(command -v micromamba || true)"
if [[ -z "$MICROMAMBA_BIN" && -x "${HOME}/.local/bin/micromamba" ]]; then
  MICROMAMBA_BIN="${HOME}/.local/bin/micromamba"
fi

PYTHON_SELECTION="$(choose_python)"
PYTHON_BIN="$(printf '%s\n' "$PYTHON_SELECTION" | sed -n '1p')"
PYROOT="$(printf '%s\n' "$PYTHON_SELECTION" | sed -n '2p')"
[[ -n "$PYTHON_BIN" && -n "$PYROOT" ]] || die "failed to resolve Python runtime"

if source_modules_init; then
  inferred_python_module="Python/$(basename "$PYROOT")"
  if module -t spider "$inferred_python_module" >/dev/null 2>&1; then
    module load "$inferred_python_module"
    PYTHON_BIN="$(command -v python3 || printf '%s' "$PYTHON_BIN")"
    PYROOT="$(cd "$(dirname "$PYTHON_BIN")/.." && pwd)"
  fi
fi

export PATH="${PYROOT}/bin:${PATH}"
if [[ -d "${PYROOT}/lib" ]]; then
  export LD_LIBRARY_PATH="${PYROOT}/lib${LD_LIBRARY_PATH+:${LD_LIBRARY_PATH}}"
fi

log "Using Python: $PYTHON_BIN"
if [[ -n "$MODULE_INIT" ]]; then
  log "Sourced module init: $MODULE_INIT"
fi

if [[ ! -x "${REPO_ROOT}/.venv/bin/python" ]]; then
  log "Creating .venv"
  "$PYTHON_BIN" -m venv "${REPO_ROOT}/.venv"
fi

log "Installing dev dependencies into .venv"
(
  cd "$REPO_ROOT"
  "${REPO_ROOT}/.venv/bin/python" -m pip install --upgrade pip setuptools wheel
  "${REPO_ROOT}/.venv/bin/python" -m pip install -e ".[dev]"
)

need_postgres=0
for tool in psql createdb dropdb initdb pg_ctl postgres; do
  if [[ ! -x "${POSTGRES_PREFIX}/bin/${tool}" ]] && ! command -v "$tool" >/dev/null 2>&1; then
    need_postgres=1
    break
  fi
done

if [[ "$need_postgres" -eq 1 ]]; then
  [[ -n "$MICROMAMBA_BIN" ]] || die "micromamba is required to install user-local PostgreSQL"
  log "Installing PostgreSQL 16 into ${POSTGRES_PREFIX}"
  "$MICROMAMBA_BIN" create -y -p "$POSTGRES_PREFIX" -c conda-forge postgresql=16 >/dev/null
fi

export PATH="${POSTGRES_PREFIX}/bin:${PATH}"
if [[ -d "${POSTGRES_PREFIX}/lib" ]]; then
  export LD_LIBRARY_PATH="${POSTGRES_PREFIX}/lib${LD_LIBRARY_PATH+:${LD_LIBRARY_PATH}}"
fi

for tool in psql createdb dropdb initdb pg_ctl postgres; do
  command -v "$tool" >/dev/null 2>&1 || die "required PostgreSQL tool missing after setup: $tool"
done

log "Ensuring Playwright Chromium is installed"
PLAYWRIGHT_BROWSERS_PATH="$PLAYWRIGHT_BROWSERS_PATH" \
  "${REPO_ROOT}/.venv/bin/python" -m playwright install chromium >/dev/null

browser_bin="$(find "$PLAYWRIGHT_BROWSERS_PATH" -type f \( -name chrome-headless-shell -o -name chrome \) | head -n 1 || true)"
if [[ -z "$browser_bin" ]]; then
  die "could not locate a Playwright Chromium binary under ${PLAYWRIGHT_BROWSERS_PATH}"
fi

missing_libs="$(ldd "$browser_bin" | awk '/not found/ {print $1}' || true)"
if printf '%s\n' "$missing_libs" | grep -q '^libgbm\.so\.1$'; then
  [[ -n "$MICROMAMBA_BIN" ]] || die "micromamba is required to install missing browser runtime libraries"
  log "Installing browser runtime libraries into ${BROWSER_LIB_PREFIX}"
  "$MICROMAMBA_BIN" create -y -p "$BROWSER_LIB_PREFIX" -c conda-forge libgbm libdrm >/dev/null
fi

if [[ -d "${BROWSER_LIB_PREFIX}/lib" ]]; then
  export LD_LIBRARY_PATH="${BROWSER_LIB_PREFIX}/lib${LD_LIBRARY_PATH+:${LD_LIBRARY_PATH}}"
fi

missing_libs="$(ldd "$browser_bin" | awk '/not found/ {print $1}' || true)"
if [[ -n "$missing_libs" ]]; then
  log "Remaining unresolved browser libraries:"
  printf '%s\n' "$missing_libs" >&2
else
  log "Chromium shared libraries resolved"
fi

emit_exports() {
  cat <<EOF
export SLAIF_HPC_PYTHON_BIN='${PYTHON_BIN}'
export SLAIF_HPC_PYROOT='${PYROOT}'
export SLAIF_HPC_POSTGRES_PREFIX='${POSTGRES_PREFIX}'
export SLAIF_HPC_BROWSER_LIB_PREFIX='${BROWSER_LIB_PREFIX}'
export SLAIF_HPC_PLAYWRIGHT_BROWSERS_PATH='${PLAYWRIGHT_BROWSERS_PATH}'
export PLAYWRIGHT_BROWSERS_PATH='${PLAYWRIGHT_BROWSERS_PATH}'
export PATH='${PATH}'
export LD_LIBRARY_PATH='${LD_LIBRARY_PATH:-}'
EOF
}

if [[ -n "$WRITE_ENV_FILE" ]]; then
  emit_exports > "$WRITE_ENV_FILE"
  log "Wrote environment exports to ${WRITE_ENV_FILE}"
else
  emit_exports
fi
