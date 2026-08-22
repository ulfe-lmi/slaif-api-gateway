#!/usr/bin/env bash
set -euo pipefail
: "${BACKUP_DATABASE_URL:?Set BACKUP_DATABASE_URL to a safe disposable/test PostgreSQL URL}"
: "${BACKUP_OUTPUT:?Set BACKUP_OUTPUT to a local file path}"
case "$BACKUP_OUTPUT" in .local-provider-catalog/*|*.log|/tmp/*) echo "Refusing unsafe backup output path" >&2; exit 2;; esac
command -v pg_dump >/dev/null || { echo "pg_dump not found" >&2; exit 2; }
pg_dump --format=custom --file="$BACKUP_OUTPUT" "$BACKUP_DATABASE_URL"
printf 'BACKUP_WRITTEN=%s\n' "$BACKUP_OUTPUT"
