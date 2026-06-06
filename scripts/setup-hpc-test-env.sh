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
  SLAIF_HPC_REDIS_PREFIX             User-local Redis install prefix
  SLAIF_HPC_REDIS_VERSION            Redis source-build version fallback
  SLAIF_HPC_DOCKER_COMPOSE_PREFIX    User-local Docker Compose wrapper prefix
  SLAIF_HPC_DOCKER_COMPOSE_VERSION   Standalone Docker Compose version fallback
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
USER_NAME="${USER:-$(id -un 2>/dev/null || echo user)}"
HPC_FAST_ROOT="/dev/shm/${USER_NAME}"
if [[ ! -d /dev/shm || ! -w /dev/shm ]]; then
  HPC_FAST_ROOT="${TMPDIR:-/tmp}/${USER_NAME}"
fi
POSTGRES_PREFIX="${SLAIF_HPC_POSTGRES_PREFIX:-${HPC_FAST_ROOT}/slaif-pg-tools}"
REDIS_PREFIX="${SLAIF_HPC_REDIS_PREFIX:-${HPC_FAST_ROOT}/slaif-redis-tools}"
REDIS_BUILD_ROOT="${SLAIF_HPC_REDIS_BUILD_ROOT:-${HPC_FAST_ROOT}/slaif-redis-build}"
REDIS_VERSION="${SLAIF_HPC_REDIS_VERSION:-7.2.5}"
DOCKER_COMPOSE_PREFIX="${SLAIF_HPC_DOCKER_COMPOSE_PREFIX:-${HPC_FAST_ROOT}/slaif-docker-compose}"
DOCKER_COMPOSE_VERSION="${SLAIF_HPC_DOCKER_COMPOSE_VERSION:-v2.27.1}"
BROWSER_LIB_PREFIX="${SLAIF_HPC_BROWSER_LIB_PREFIX:-${HPC_FAST_ROOT}/slaif-browser-libs}"
PLAYWRIGHT_BROWSERS_PATH="${SLAIF_HPC_PLAYWRIGHT_BROWSERS_PATH:-${HPC_FAST_ROOT}/ms-playwright}"
DOCKER_ENV_STATUS="not needed"

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

real_home() {
  getent passwd "${USER:-}" 2>/dev/null | cut -d: -f6 || true
}

find_user_tool() {
  local tool="$1"
  local candidate home_candidate
  if command -v "$tool" >/dev/null 2>&1; then
    command -v "$tool"
    return 0
  fi
  home_candidate="$(real_home)"
  for candidate in \
    "${HOME:-}/.local/bin/${tool}" \
    "${home_candidate}/.local/bin/${tool}" \
    "${home_candidate}/bin/${tool}"
  do
    if [[ -n "$candidate" && -x "$candidate" ]]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  return 1
}

PKG_MANAGER_BIN=""
PKG_MANAGER_KIND=""
for candidate_tool in micromamba mamba conda; do
  if PKG_MANAGER_BIN="$(find_user_tool "$candidate_tool")"; then
    PKG_MANAGER_KIND="$candidate_tool"
    break
  fi
done

conda_create_prefix() {
  local prefix="$1"
  shift
  [[ -n "$PKG_MANAGER_BIN" ]] || return 1
  case "$PKG_MANAGER_KIND" in
    micromamba|mamba)
      "$PKG_MANAGER_BIN" create -y -p "$prefix" -c conda-forge "$@"
      ;;
    conda)
      "$PKG_MANAGER_BIN" create -y -p "$prefix" -c conda-forge "$@"
      ;;
    *)
      return 1
      ;;
  esac
}

try_module_for_tools() {
  local module_name="$1"
  shift
  source_modules_init || return 1
  module load "$module_name" >/dev/null 2>&1 || return 1
  local tool
  for tool in "$@"; do
    command -v "$tool" >/dev/null 2>&1 || return 1
  done
  return 0
}

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
  [[ -n "$PKG_MANAGER_BIN" ]] || die "micromamba, mamba, or conda is required to install user-local PostgreSQL"
  log "Installing PostgreSQL 16 into ${POSTGRES_PREFIX}"
  conda_create_prefix "$POSTGRES_PREFIX" postgresql=16 >/dev/null
fi

export PATH="${POSTGRES_PREFIX}/bin:${PATH}"
if [[ -d "${POSTGRES_PREFIX}/lib" ]]; then
  export LD_LIBRARY_PATH="${POSTGRES_PREFIX}/lib${LD_LIBRARY_PATH+:${LD_LIBRARY_PATH}}"
fi

for tool in psql createdb dropdb initdb pg_ctl postgres; do
  command -v "$tool" >/dev/null 2>&1 || die "required PostgreSQL tool missing after setup: $tool"
done

need_redis=0
if ! command -v redis-server >/dev/null 2>&1 || ! command -v redis-cli >/dev/null 2>&1; then
  need_redis=1
fi

if [[ "$need_redis" -eq 1 ]] && try_module_for_tools redis redis-server redis-cli; then
  need_redis=0
  log "Using Redis tools from an HPC module"
fi

if [[ "$need_redis" -eq 1 && -x "${REDIS_PREFIX}/bin/redis-server" && -x "${REDIS_PREFIX}/bin/redis-cli" ]]; then
  need_redis=0
fi

if [[ "$need_redis" -eq 1 && -n "$PKG_MANAGER_BIN" ]]; then
  log "Installing Redis into ${REDIS_PREFIX}"
  if conda_create_prefix "$REDIS_PREFIX" redis-server >/dev/null 2>&1 || \
     conda_create_prefix "$REDIS_PREFIX" redis >/dev/null 2>&1; then
    need_redis=0
  else
    log "Conda Redis install failed; falling back to source build"
  fi
fi

if [[ "$need_redis" -eq 1 ]]; then
  log "Building Redis ${REDIS_VERSION} from source into ${REDIS_PREFIX}"
  mkdir -p "$REDIS_BUILD_ROOT" "$REDIS_PREFIX"
  redis_tar="${REDIS_BUILD_ROOT}/redis-${REDIS_VERSION}.tar.gz"
  redis_src="${REDIS_BUILD_ROOT}/redis-${REDIS_VERSION}"
  clean_env=(env -u LD_LIBRARY_PATH -u LIBRARY_PATH -u CPATH -u PKG_CONFIG_PATH -u PYTHONPATH)
  if [[ ! -f "$redis_tar" ]]; then
    if command -v curl >/dev/null 2>&1; then
      "${clean_env[@]}" curl -fsSL "https://download.redis.io/releases/redis-${REDIS_VERSION}.tar.gz" -o "$redis_tar"
    elif command -v wget >/dev/null 2>&1; then
      "${clean_env[@]}" wget -q "https://download.redis.io/releases/redis-${REDIS_VERSION}.tar.gz" -O "$redis_tar"
    else
      die "curl or wget is required for Redis source-build fallback"
    fi
  fi
  rm -rf "$redis_src"
  "${clean_env[@]}" tar -xzf "$redis_tar" -C "$REDIS_BUILD_ROOT"
  (
    cd "$redis_src"
    if [[ -x /usr/bin/gcc ]]; then
      "${clean_env[@]}" make MALLOC=libc CC=/usr/bin/gcc CFLAGS="-O2 -g0" REDIS_CFLAGS="" REDIS_LDFLAGS="" -j"$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo 4)"
    else
      "${clean_env[@]}" make MALLOC=libc CFLAGS="-O2 -g0" REDIS_CFLAGS="" REDIS_LDFLAGS="" -j"$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo 4)"
    fi
    "${clean_env[@]}" make PREFIX="$REDIS_PREFIX" install
  )
fi

export PATH="${REDIS_PREFIX}/bin:${PATH}"
redis-server --version >/dev/null 2>&1 || die "redis-server missing after setup"
redis-cli --version >/dev/null 2>&1 || die "redis-cli missing after setup"
log "Redis tools: $(command -v redis-server), $(command -v redis-cli)"

docker_compose_works() {
  command -v docker >/dev/null 2>&1 || return 1
  docker compose version >/dev/null 2>&1 || return 1
}

ensure_compose_env_file() {
  local env_file="${REPO_ROOT}/.env"
  if [[ -f "$env_file" ]]; then
    DOCKER_ENV_STATUS=".env already present"
    return 0
  fi
  if [[ -f "${REPO_ROOT}/.env.example" ]]; then
    cp "${REPO_ROOT}/.env.example" "$env_file"
    DOCKER_ENV_STATUS="created ignored .env from .env.example"
    if ! git -C "$REPO_ROOT" check-ignore -q .env; then
      die ".env is not ignored; refusing to leave a local Compose env file"
    fi
    return 0
  fi
  DOCKER_ENV_STATUS=".env.example missing"
  return 1
}

if ! docker_compose_works && try_module_for_tools docker docker; then
  log "Using Docker/Compose from an HPC module"
fi

if ! docker_compose_works; then
  mkdir -p "${DOCKER_COMPOSE_PREFIX}/bin"
  compose_bin="${DOCKER_COMPOSE_PREFIX}/bin/docker-compose"
  wrapper_bin="${DOCKER_COMPOSE_PREFIX}/bin/docker"
  if [[ ! -x "$compose_bin" ]]; then
    log "Installing standalone Docker Compose ${DOCKER_COMPOSE_VERSION} into ${DOCKER_COMPOSE_PREFIX}"
    uname_s="$(uname -s)"
    uname_m="$(uname -m)"
    case "$uname_m" in
      x86_64|amd64) compose_arch="x86_64" ;;
      aarch64|arm64) compose_arch="aarch64" ;;
      *) die "unsupported architecture for standalone Docker Compose: $uname_m" ;;
    esac
    compose_url="https://github.com/docker/compose/releases/download/${DOCKER_COMPOSE_VERSION}/docker-compose-${uname_s}-${compose_arch}"
    clean_env=(env -u LD_LIBRARY_PATH -u LIBRARY_PATH -u CPATH -u PKG_CONFIG_PATH -u PYTHONPATH)
    if command -v curl >/dev/null 2>&1; then
      "${clean_env[@]}" curl -fsSL "$compose_url" -o "$compose_bin"
    elif command -v wget >/dev/null 2>&1; then
      "${clean_env[@]}" wget -q "$compose_url" -O "$compose_bin"
    else
      die "curl or wget is required to install standalone Docker Compose"
    fi
    chmod +x "$compose_bin"
  fi
  cat > "$wrapper_bin" <<EOF
#!/usr/bin/env bash
set -euo pipefail
if [[ "\${1:-}" == "compose" ]]; then
  shift
  exec '${compose_bin}' "\$@"
fi
echo "This user-local wrapper only supports: docker compose ..." >&2
exit 64
EOF
  chmod +x "$wrapper_bin"
  export PATH="${DOCKER_COMPOSE_PREFIX}/bin:${PATH}"
fi

if docker_compose_works; then
  pushd "$REPO_ROOT" >/dev/null
  if ! docker compose config >/dev/null 2>&1; then
    ensure_compose_env_file || true
  else
    DOCKER_ENV_STATUS="${DOCKER_ENV_STATUS:-not needed}"
  fi
  docker compose version >/dev/null
  docker compose config >/dev/null || die "docker compose config failed after Compose setup"
  popd >/dev/null
  log "Docker Compose config tooling ready: $(command -v docker)"
else
  log "Docker Compose config tooling unavailable after setup"
fi

log "Ensuring Playwright Chromium is installed"
PLAYWRIGHT_BROWSERS_PATH="$PLAYWRIGHT_BROWSERS_PATH" \
  "${REPO_ROOT}/.venv/bin/python" -m playwright install chromium >/dev/null

browser_bin="$(find "$PLAYWRIGHT_BROWSERS_PATH" -type f \( -name chrome-headless-shell -o -name chrome \) | head -n 1 || true)"
if [[ -z "$browser_bin" ]]; then
  die "could not locate a Playwright Chromium binary under ${PLAYWRIGHT_BROWSERS_PATH}"
fi

missing_libs="$(ldd "$browser_bin" | awk '/not found/ {print $1}' || true)"
if printf '%s\n' "$missing_libs" | grep -q '^libgbm\.so\.1$'; then
  [[ -n "$PKG_MANAGER_BIN" ]] || die "micromamba, mamba, or conda is required to install missing browser runtime libraries"
  log "Installing browser runtime libraries into ${BROWSER_LIB_PREFIX}"
  conda_create_prefix "$BROWSER_LIB_PREFIX" libgbm libdrm >/dev/null
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
export SLAIF_HPC_REDIS_PREFIX='${REDIS_PREFIX}'
export SLAIF_HPC_DOCKER_COMPOSE_PREFIX='${DOCKER_COMPOSE_PREFIX}'
export SLAIF_HPC_DOCKER_ENV_STATUS='${DOCKER_ENV_STATUS}'
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
