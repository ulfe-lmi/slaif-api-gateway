#!/usr/bin/env bash
set -euo pipefail

# Run the strict, disposable production-appliance qualification journey.
exec python scripts/production-qualification/run.py "$@"
