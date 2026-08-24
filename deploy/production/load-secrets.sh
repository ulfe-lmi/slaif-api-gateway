#!/usr/bin/env bash
set -euo pipefail

fail() {
  printf 'production secret loading failed: %s\n' "$1" >&2
  exit 78
}

if [[ "${APP_ENV:-development}" == "production" ]]; then
  [[ "$#" -gt 0 ]] || fail "no command supplied"
fi

load_secret() {
  local environment_name="$1"
  local file_environment_name="$2"
  local secret_path
  local secret_value

  if [[ "${!environment_name+x}" == x ]]; then
    if [[ "${!file_environment_name+x}" == x ]]; then
      fail "ambiguous configuration for ${environment_name}"
    fi
    if [[ "${APP_ENV:-development}" == "production" ]]; then
      fail "direct configuration is not permitted for ${environment_name}"
    fi
    return 0
  fi

  if [[ "${!file_environment_name+x}" != x ]]; then
    [[ "${APP_ENV:-development}" == "production" ]] || return 0
    fail "missing file variable ${file_environment_name}"
  fi

  secret_path="${!file_environment_name}"
  [[ -n "$secret_path" ]] || fail "empty file variable ${file_environment_name}"
  [[ -f "$secret_path" ]] || fail "secret file is missing: ${file_environment_name}"
  [[ -r "$secret_path" ]] || fail "secret file is unreadable: ${file_environment_name}"
  [[ ! -L "$secret_path" ]] || fail "secret file must not be a symlink: ${file_environment_name}"

  # Bash read with a NUL delimiter preserves all bytes up to EOF, including
  # trailing newlines. Environment variables cannot contain NUL, so reject
  # that case rather than silently trimming or rewriting secret material.
  IFS= read -r -d '' secret_value < "$secret_path" || true
  [[ -n "$secret_value" ]] || fail "secret file is empty: ${file_environment_name}"
  if od -An -v -t x1 "$secret_path" | grep -q '00'; then
    fail "secret file contains NUL: ${file_environment_name}"
  fi
  export "${environment_name}=${secret_value}"
}

load_secret DATABASE_URL DATABASE_URL_FILE
load_secret TOKEN_HMAC_SECRET_V1 TOKEN_HMAC_SECRET_V1_FILE
load_secret ADMIN_SESSION_SECRET ADMIN_SESSION_SECRET_FILE
load_secret ONE_TIME_SECRET_ENCRYPTION_KEY ONE_TIME_SECRET_ENCRYPTION_KEY_FILE
load_secret OPENAI_UPSTREAM_API_KEY OPENAI_UPSTREAM_API_KEY_FILE
load_secret OPENROUTER_API_KEY OPENROUTER_API_KEY_FILE
load_secret REDIS_URL REDIS_URL_FILE

if [[ "$(id -u)" == "0" ]] && id slaif >/dev/null 2>&1; then
  exec su --preserve-environment --shell /bin/sh slaif -c 'exec "$0" "$@"' -- "$@"
fi

exec "$@"
