# OAP Work Order — 139-a

PR mode: `CREATE_NEW_PR`
Branch: `oap/139-production-compose-boot-closure`
Base: main @ 1d357c497c56358c3c5e72e955ea4915d7221563

## Objective and reason

Fix `docker-compose.production.yml` so that a clean Linux host following
`docs/deployment-production.md` can actually boot a functioning SLAIF gateway.
Currently the API container fails closed at startup due to missing required
secrets, Nginx fails due to missing TLS certificate mount, no migrations run,
and no provider credentials are provisioned. This makes the documented
deployment path non-functional.

## Root cause evidence (from MVP-CLOSURE-AUDIT.md)

1. API container receives only `database_url` secret. Missing:
   `TOKEN_HMAC_SECRET_V1`, `ADMIN_SESSION_SECRET`, `ONE_TIME_SECRET_ENCRYPTION_KEY`.
   In `APP_ENV=production`, config validation raises on all three.
2. No volume mount for `/etc/nginx/certs/` referenced by `nginx/production.conf`.
3. No `OPENROUTER_API_KEY` or `OPENAI_UPSTREAM_API_KEY` provisioning.
4. No Alembic migration execution.
5. No health check defined for the API service.

## Exact requirements

1. Add Docker secrets for: `token_hmac_secret_v1`, `admin_session_secret`,
   `one_time_secret_encryption_key`.
2. Wire those secrets into the API container environment using `_FILE` pattern
   or direct env injection consistent with existing `DATABASE_URL_FILE` approach.
3. Add TLS certificate volume mount to nginx service (host path or named volume).
4. Add optional provider credential secrets (`openrouter_api_key`,
   `openai_upstream_api_key`) wired into API environment.
5. Add a one-shot migration service that runs `alembic upgrade head` after
   postgres is healthy and before API starts.
6. Add healthcheck to API service hitting `/healthz`.
7. Update `scripts/preflight.sh` to verify all new secret files exist.
8. Update `docs/deployment-production.md` with complete step-by-step including
   secret generation commands.
9. Do NOT add worker/scheduler to production profile in this round.

## What does NOT count as completion

- `docker compose config --quiet` passing alone.
- Documentation changes without compose file fixes.
- Adding secrets to `.env.example` without wiring them into the compose file.

## Allowed paths

```
docker-compose.production.yml
scripts/preflight.sh
docs/deployment-production.md
oap/orders/139-a-production-compose-boot-closure.md
oap/reports/139-a-production-compose-boot-closure.md
oap/active
```

## Verification

```bash
bash scripts/preflight.sh  # must pass with all secrets present
docker compose -f docker-compose.production.yml config --quiet
# Manual boot test documented in report with output
```

## Acceptance

Preflight passes; compose config valid; deployment docs updated; all CI green;
report-only SELF commit pushed; never merge.
