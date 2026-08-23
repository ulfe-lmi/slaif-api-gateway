#!/usr/bin/env bash
set -euo pipefail
fail() { echo "PREFLIGHT_FAILED $1" >&2; exit 1; }
[[ -f docker-compose.production.yml ]] || fail compose_file_missing
for secret in secrets/postgres_password secrets/database_url; do
  [[ -s "$secret" ]] || fail "secret_missing=$secret"
done
if [[ "$(stat -c '%a' secrets)" != "700" ]]; then fail secrets_permissions; fi
command -v docker >/dev/null || fail docker_missing
docker compose -f docker-compose.production.yml config --quiet || fail compose_invalid
echo PREFLIGHT_OK
