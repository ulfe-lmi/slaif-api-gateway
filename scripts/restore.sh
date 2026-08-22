#!/usr/bin/env bash
set -euo pipefail
: "${RESTORE_DATABASE_URL:?Set RESTORE_DATABASE_URL to a clean disposable/test PostgreSQL URL}"
: "${BACKUP_INPUT:?Set BACKUP_INPUT to a pg_dump custom-format file}"
case "$(realpath "${BACKUP_INPUT}")" in *.log) echo "Refusing log input" >&2; exit 2;; esac
command -v pg_restore >/dev/null || { echo "pg_restore not found" >&2; exit 2; }
pg_restore --clean --if-exists --dbname="$RESTORE_DATABASE_URL" "$BACKUP_INPUT"
printf 'RESTORE_COMPLETED=%s\n' "$BACKUP_INPUT"
