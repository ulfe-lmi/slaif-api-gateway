#!/usr/bin/env bash
set -euo pipefail
fail() { echo "PREFLIGHT_FAILED $1" >&2; exit 1; }
[[ -f docker-compose.production.yml ]] || fail compose_file_missing
secret_file() {
  local variable_name="$1"
  local default_path="$2"
  printf '%s\n' "${!variable_name:-$default_path}"
}

if [[ -z "${SLAIF_POSTGRES_PASSWORD_FILE:-}" && -d "secrets" ]]; then
  secrets_mode="$(stat -c '%a' secrets)"
  [[ "$secrets_mode" == "700" ]] || fail "secrets directory must have mode 700 (found $secrets_mode)"
fi

for pair in \
  "SLAIF_POSTGRES_PASSWORD_FILE secrets/postgres_password" \
  "SLAIF_DATABASE_URL_FILE secrets/database_url" \
  "SLAIF_TOKEN_HMAC_SECRET_V1_FILE secrets/token_hmac_secret_v1" \
  "SLAIF_ADMIN_SESSION_SECRET_FILE secrets/admin_session_secret" \
  "SLAIF_ONE_TIME_SECRET_ENCRYPTION_KEY_FILE secrets/one_time_secret_encryption_key" \
  "SLAIF_OPENROUTER_API_KEY_FILE secrets/openrouter_api_key" \
  "SLAIF_OPENAI_UPSTREAM_API_KEY_FILE secrets/openai_upstream_api_key" \
  "SLAIF_REDIS_PASSWORD_FILE secrets/redis_password" \
  "SLAIF_REDIS_URL_FILE secrets/redis_url"; do
  read -r variable default_path <<<"$pair"
  path="$(secret_file "$variable" "$default_path")"
  [[ -f "$path" ]] || fail "secret_missing=$variable"
  [[ -r "$path" ]] || fail "secret_unreadable=$variable"
  [[ -s "$path" ]] || fail "secret_empty=$variable"
  [[ ! -L "$path" ]] || fail "secret_symlink=$variable"
done

tls_dir="${SLAIF_TLS_DIR:-./secrets/tls}"
[[ -d "$tls_dir" ]] || fail tls_directory_missing
[[ -f "$tls_dir/fullchain.pem" ]] || fail tls_certificate_missing=fullchain.pem
[[ -f "$tls_dir/privkey.pem" ]] || fail tls_certificate_missing=privkey.pem
[[ -s "$tls_dir/fullchain.pem" ]] || fail tls_certificate_empty=fullchain.pem
[[ -s "$tls_dir/privkey.pem" ]] || fail tls_certificate_empty=privkey.pem
command -v docker >/dev/null || fail docker_missing
docker compose -f docker-compose.production.yml config --quiet || fail compose_invalid
echo PREFLIGHT_OK
