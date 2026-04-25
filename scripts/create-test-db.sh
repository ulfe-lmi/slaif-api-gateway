#!/usr/bin/env bash
set -euo pipefail

if [[ "${APP_ENV:-}" == "production" ]]; then
  echo "Refusing to create test database when APP_ENV=production" >&2
  exit 1
fi

TEST_DB_USER="${TEST_DB_USER:-slaif}"
TEST_DB_PASSWORD="${TEST_DB_PASSWORD:-slaif}"
TEST_DB_NAME="${TEST_DB_NAME:-slaif_gateway_test}"

if [[ "${TEST_DB_NAME}" != *test* && "${TEST_DB_NAME}" != *dev* && "${TEST_DB_NAME}" != *local* ]]; then
  echo "Refusing to use TEST_DB_NAME=${TEST_DB_NAME}; must include test/dev/local." >&2
  exit 1
fi

if [[ -n "${DATABASE_URL:-}" ]]; then
  echo "Info: DATABASE_URL is set but ignored by this script for safety."
fi

if ! command -v sudo >/dev/null 2>&1; then
  echo "sudo is unavailable. Cannot create test role/database." >&2
  exit 1
fi

sudo -u postgres psql -v ON_ERROR_STOP=1 <<SQL
DO
\$do\$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '${TEST_DB_USER}') THEN
    EXECUTE format('CREATE ROLE %I LOGIN PASSWORD %L', '${TEST_DB_USER}', '${TEST_DB_PASSWORD}');
  END IF;
END
\$do\$;
SQL

DB_EXISTS="$(sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='${TEST_DB_NAME}'")"
if [[ "${DB_EXISTS}" != "1" ]]; then
  sudo -u postgres createdb --owner="${TEST_DB_USER}" "${TEST_DB_NAME}"
fi

echo "TEST_DATABASE_URL=postgresql+asyncpg://${TEST_DB_USER}:${TEST_DB_PASSWORD}@localhost:5432/${TEST_DB_NAME}"
