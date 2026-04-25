#!/usr/bin/env bash
set -euo pipefail

if [[ "${APP_ENV:-}" == "production" ]]; then
  echo "Refusing to start test PostgreSQL when APP_ENV=production" >&2
  exit 1
fi

if ! command -v sudo >/dev/null 2>&1; then
  echo "sudo is unavailable. Cannot start PostgreSQL." >&2
  exit 1
fi

started=0
if sudo service postgresql start >/dev/null 2>&1; then
  started=1
  echo "Started PostgreSQL via service postgresql start"
else
  echo "service start failed; trying pg_ctlcluster"
  if ! command -v pg_lsclusters >/dev/null 2>&1; then
    echo "pg_lsclusters is unavailable; cannot detect cluster for pg_ctlcluster." >&2
    exit 1
  fi

  cluster_version="$(pg_lsclusters -h | awk 'NR==1 {print $1}')"
  if [[ -z "${cluster_version}" ]]; then
    echo "No PostgreSQL cluster detected by pg_lsclusters." >&2
    exit 1
  fi

  sudo pg_ctlcluster "${cluster_version}" main start
  started=1
  echo "Started PostgreSQL via pg_ctlcluster ${cluster_version} main start"
fi

if [[ "${started}" -ne 1 ]]; then
  echo "Failed to start PostgreSQL." >&2
  exit 1
fi

if command -v pg_isready >/dev/null 2>&1; then
  pg_isready -h localhost -p 5432 || {
    echo "PostgreSQL process started but pg_isready reports not ready." >&2
    exit 1
  }
fi

echo "PostgreSQL is ready on localhost:5432"
