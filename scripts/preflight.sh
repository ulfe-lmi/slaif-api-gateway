#!/usr/bin/env bash
set -euo pipefail
fail() { echo "PREFLIGHT_FAILED $1" >&2; exit 1; }
[[ -f docker-compose.production.yml ]] || fail compose_file_missing
for secret in \
  secrets/postgres_password \
  secrets/database_url \
  secrets/token_hmac_secret_v1 \
  secrets/admin_session_secret \
  secrets/one_time_secret_encryption_key \
  secrets/openrouter_api_key \
  secrets/openai_upstream_api_key; do
  [[ -s "$secret" ]] || fail "secret_missing=$secret"
done
if [[ "$(stat -c '%a' secrets)" != "700" ]]; then fail secrets_permissions; fi
[[ -f secrets/tls/fullchain.pem ]] || fail tls_certificate_missing=fullchain.pem
[[ -f secrets/tls/privkey.pem ]] || fail tls_certificate_missing=privkey.pem
command -v docker >/dev/null || fail docker_missing
docker compose -f docker-compose.production.yml config --quiet || fail compose_invalid
echo PREFLIGHT_OK
