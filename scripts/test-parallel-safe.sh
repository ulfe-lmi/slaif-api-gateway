#!/usr/bin/env bash
set -euo pipefail

if [[ -n "${PYTHON:-}" ]]; then
  PY="$PYTHON"
elif [[ -x ".venv/bin/python" ]]; then
  PY=".venv/bin/python"
else
  PY="python"
fi

echo "Running unit tests in parallel, then shared-resource suites serially."
echo "This script does not create, mutate, or drop test databases."
echo "Set TEST_DATABASE_URL for integration/E2E/browser suites; skipped tests remain visible."

export PYTHON="$PY"
scripts/test-unit-parallel.sh "$@"

run_pytest() {
  echo "Command: $PY -m pytest $*"
  set -x
  "$PY" -m pytest "$@"
  { set +x; } 2>/dev/null
}

run_pytest tests/integration "$@"
run_pytest tests/e2e "$@"
run_pytest tests/browser -m playwright "$@"
