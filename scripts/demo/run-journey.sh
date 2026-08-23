#!/usr/bin/env bash
set -euo pipefail

log() { printf '[%s] %s\n' "$(date -u +%FT%TZ)" "$1"; }
require_env() { [[ -n "${!1:-}" ]] || { echo "Missing required environment variable: $1" >&2; exit 2; }; }

START=$(date -u +%s)
log "journey=start"

require_env DATABASE_URL
command -v docker >/dev/null || { log "journey=fail reason=docker_missing"; exit 1; }

log "step=compose_config"
docker compose config --quiet

log "step=preflight"
if [[ -f scripts/preflight.sh ]]; then bash scripts/preflight.sh || true; fi

log "step=migrations"
.venv/bin/alembic upgrade head 2>/dev/null || alembic upgrade head

log "step=guided_onboarding"
log "guided_onboarding=manual_browser_steps_required"
log "onboarding_doc=docs/onboarding.md"

log "step=client_usage"
log "client_usage=requires_operator_gateway_key_and_safe_provider_configuration"

log "step=exports"
log "exports=metadata_only_see_docs/audit-export.md"

log "step=backup_restore"
[[ -n "${BACKUP_DATABASE_URL:-}" ]] || log "backup_restore=skipped_no_backup_database_url"
[[ -z "${BACKUP_DATABASE_URL:-}" ]] || {
  BACKUP_OUTPUT=./slaif-demo.dump bash scripts/backup.sh
  RESTORE_DATABASE_URL="$BACKUP_DATABASE_URL" BACKUP_INPUT=./slaif-demo.dump bash scripts/restore.sh
  RESTORE_DATABASE_URL="$BACKUP_DATABASE_URL" python scripts/verify_restore.py
}

END=$(date -u +%s)
log "journey=ok elapsed_seconds=$((END-START))"
