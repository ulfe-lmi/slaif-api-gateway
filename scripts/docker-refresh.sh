#!/usr/bin/env bash
set -Eeuo pipefail

usage() {
  cat <<'EOF'
Usage: ./scripts/docker-refresh.sh [options]

Safely refresh the local Docker Compose API, worker, and scheduler services.
This script never deletes Docker volumes, overwrites .env, or resets git state.

Options:
  --pull              Fetch origin and fast-forward main before refreshing.
  --env-only          Recreate api/worker/scheduler after .env changes; skip git, build, and migrations.
  --skip-build        Skip docker compose build.
  --skip-migrations   Skip slaif-gateway db upgrade.
  --no-health-check   Skip /healthz and /readyz checks.
  --help              Show this help text.

Examples:
  ./scripts/docker-refresh.sh --env-only
  ./scripts/docker-refresh.sh --pull
  ./scripts/docker-refresh.sh
EOF
}

run() {
  printf '+'
  printf ' %q' "$@"
  printf '\n'
  "$@"
}

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

if [[ ! -f "docker-compose.yml" || ! -d "app/slaif_gateway" ]]; then
  echo "error: could not locate slaif-api-gateway repo root" >&2
  exit 1
fi

pull=false
env_only=false
skip_build=false
skip_migrations=false
health_check=true

while [[ $# -gt 0 ]]; do
  case "$1" in
    --pull)
      pull=true
      ;;
    --env-only)
      env_only=true
      ;;
    --skip-build)
      skip_build=true
      ;;
    --skip-migrations)
      skip_migrations=true
      ;;
    --no-health-check)
      health_check=false
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "error: unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
  shift
done

compose=(docker compose)
services=(api worker scheduler)

api_host_port() {
  local value=""
  if [[ -f ".env" ]]; then
    value="$(
      sed -n 's/^[[:space:]]*API_HOST_PORT[[:space:]]*=[[:space:]]*//p' .env \
        | sed 's/[[:space:]]*#.*$//' \
        | sed 's/^["'\'']//; s/["'\'']$//' \
        | tail -n 1
    )"
  fi
  if [[ -z "$value" ]]; then
    value="8000"
  fi
  printf '%s\n' "$value"
}

tracked_changes() {
  [[ -n "$(git status --porcelain --untracked-files=no)" ]]
}

echo "Repository: $repo_root"
run git status --short

if [[ "$pull" == true ]]; then
  if tracked_changes; then
    echo "error: refusing --pull because tracked worktree changes are present" >&2
    exit 1
  fi
  branch="$(git branch --show-current)"
  if [[ "$branch" != "main" ]]; then
    echo "error: --pull is intended for local main; current branch is '$branch'" >&2
    exit 1
  fi
  run git fetch origin
  run git checkout main
  run git pull --ff-only origin main
fi

if [[ "$env_only" != true && "$skip_build" != true ]]; then
  run "${compose[@]}" build "${services[@]}"
fi

if [[ "$env_only" != true && "$skip_migrations" != true ]]; then
  run "${compose[@]}" run --rm api slaif-gateway db upgrade
fi

run "${compose[@]}" up -d --force-recreate "${services[@]}"
run "${compose[@]}" ps

if [[ "$health_check" == true ]]; then
  port="$(api_host_port)"
  run curl -fsS "http://localhost:${port}/healthz"
  printf '\n'
  run curl -fsS "http://localhost:${port}/readyz"
  printf '\n'
fi
