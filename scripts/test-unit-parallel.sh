#!/usr/bin/env bash
set -euo pipefail

if [[ -n "${PYTHON:-}" ]]; then
  PY="$PYTHON"
elif [[ -x ".venv/bin/python" ]]; then
  PY=".venv/bin/python"
else
  PY="python"
fi

VISIBLE_CORES="$("$PY" - <<'PY'
import os

print(os.cpu_count() or 1)
PY
)"

DEFAULT_WORKERS="$("$PY" - <<'PY'
import os

cores = os.cpu_count() or 1
print(max(1, min(20, cores)))
PY
)"

WORKERS="${PYTEST_XDIST_WORKERS:-$DEFAULT_WORKERS}"
XDIST_ARGS="${PYTEST_XDIST_ARGS:---dist loadscope}"

echo "Python: $PY"
echo "Visible CPU cores: $VISIBLE_CORES"
echo "pytest-xdist workers: $WORKERS"
echo "pytest-xdist args: $XDIST_ARGS"
echo "Command: $PY -m pytest tests/unit -n $WORKERS $XDIST_ARGS $*"

set -x
"$PY" -m pytest tests/unit -n "$WORKERS" $XDIST_ARGS "$@"
