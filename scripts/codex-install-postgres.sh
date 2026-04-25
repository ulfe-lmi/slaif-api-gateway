#!/usr/bin/env bash
set -euo pipefail

if [[ "${APP_ENV:-}" == "production" ]]; then
  echo "Refusing to install/setup test PostgreSQL when APP_ENV=production" >&2
  exit 1
fi

if ! command -v apt >/dev/null 2>&1; then
  echo "apt is unavailable. This script supports apt-based environments only." >&2
  exit 1
fi

if ! command -v sudo >/dev/null 2>&1; then
  echo "sudo is unavailable. Cannot install PostgreSQL packages." >&2
  exit 1
fi

sudo apt update
sudo apt install -y postgresql postgresql-contrib postgresql-client

echo "PostgreSQL packages installed."
