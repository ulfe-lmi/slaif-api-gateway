# Deployment

This document describes the repository Docker Compose packaging and the
deployment boundaries operators must keep explicit. It is not a production
certification or a complete site reliability runbook.

For a beginner-friendly local walkthrough, start with
[`quickstart.md`](quickstart.md). For RC-beta scope and release checklist, see
[`rc-beta.md`](rc-beta.md) and [`beta-readiness.md`](beta-readiness.md). For
operator incident and maintenance procedures, see
[`runbooks/README.md`](runbooks/README.md).

## Overview

The Compose packaging defines these services:

- `api`: FastAPI application served by Gunicorn with Uvicorn workers.
- `worker`: Celery worker for background jobs such as key email delivery and
  optional reconciliation tasks.
- `scheduler`: Celery Beat scheduler. Scheduled reconciliation remains disabled
  unless explicitly enabled through environment variables.
- `postgres`: PostgreSQL 16, the source of truth for keys, quotas, accounting,
  audit logs, admin state, catalog metadata, and email delivery state.
- `redis`: Redis 7 for Celery broker state and optional operational rate limits.
- `mailpit`: local/development SMTP sink and web mailbox.
- `nginx`: optional reverse proxy profile using `deploy/nginx/slaif-api-gateway.conf`.

API, worker, and scheduler containers do not run migrations automatically.
Migrations are explicit operator actions.

## Local Docker Compose

Clone the repository and create a local environment file:

```bash
git clone https://github.com/ulfe-lmi/slaif-api-gateway.git
cd slaif-api-gateway
cp .env.example .env
```

Replace development placeholders in `.env` before using the stack for anything
outside local testing. For local Compose, `.env.example` already points
`DATABASE_URL`, `REDIS_URL`, `CELERY_BROKER_URL`, and `SMTP_HOST` at the Compose
service names. `.env` is clear-text local runtime configuration; do not commit
it, and on shared systems restrict it with:

```bash
chmod 600 .env
```

Generate local runtime secrets with `slaif-gateway secrets generate ... --write`
before starting services. Use either the host-local CLI workflow or the
Docker-only bind-mounted workflow in [`quickstart.md`](quickstart.md); do not
assume a plain `docker compose run api ... --env-file .env --write` updates the
host `.env` file unless the project directory is explicitly mounted. The
`--write` option intentionally writes generated runtime secrets to that
clear-text file for local/self-hosted bootstrap. It is a convenience, not a
complete production secret-management system.

Build the image and start infrastructure:

```bash
docker compose build
docker compose up -d postgres redis mailpit
```

Run migrations explicitly:

```bash
docker compose run --rm api slaif-gateway db upgrade
```

Then start the full local stack:

```bash
docker compose up
```

Create the first admin account:

```bash
printf '%s\n' 'replace-this-password' \
  | docker compose run --rm api slaif-gateway admin create \
      --email admin@example.org \
      --display-name "Admin User" \
      --password-stdin
```

Create local catalog metadata before sending traffic through `/v1`. For real
traffic, copy the example pricing CSV and replace its placeholder prices with
operator-reviewed local pricing assumptions before applying it:

```bash
cp docs/examples/openai-completions-pricing.example.csv local-openai-pricing.csv

docker compose run --rm api slaif-gateway bootstrap openai-completions-catalog \
  --pricing-file local-openai-pricing.csv \
  --apply

docker compose run --rm api slaif-gateway fx add \
  --base-currency USD \
  --quote-currency EUR \
  --rate 0.920000000
```

The bootstrap command creates local OpenAI Chat Completions metadata only. It
does not call OpenAI, fetch pricing, create gateway keys, or store provider key
values. Legacy `/v1/completions` is not implemented.

Create prerequisite owner records and issue a gateway key with endpoints
`/v1/models` and `/v1/chat/completions` plus the desired catalog model IDs.
Users then call the local gateway with normal OpenAI-compatible variables:

```bash
export OPENAI_API_KEY="sk-slaif-..."
export OPENAI_BASE_URL="http://localhost:8000/v1"
```

Mailpit is available at `http://localhost:8025` by default. Its SMTP endpoint is
`mailpit:1025` from containers and `localhost:1025` from the host. Compose host
ports are configurable with `API_HOST_PORT`, `POSTGRES_HOST_PORT`,
`REDIS_HOST_PORT`, `MAILPIT_SMTP_HOST_PORT`, `MAILPIT_WEB_HOST_PORT`, and
`NGINX_HOST_PORT`; the default Postgres and Redis host ports are `15432` and
`16379` to avoid common collisions with host-local services.

Stop the local stack:

```bash
docker compose down
```

Use `docker compose down -v` only when you intentionally want to delete local
PostgreSQL and Redis volumes.

For non-destructive local refreshes, use:

```bash
./scripts/docker-refresh.sh --env-only  # after .env changes
./scripts/docker-refresh.sh --pull      # after upstream code updates on main
./scripts/docker-refresh.sh             # after local code changes
```

The script builds API/worker/scheduler images, runs migrations unless skipped,
recreates runtime services, shows Compose status, and checks `/healthz` and
`/readyz`. It never removes Docker volumes or overwrites `.env`.

## Optional Browser Smoke Tests

The Playwright admin dashboard smoke tests are optional and are not part of the
normal unit, integration, or OpenAI-compatible E2E commands. They require an
explicit test database and an explicitly installed browser:

```bash
python -m playwright install chromium
TEST_DATABASE_URL="postgresql+asyncpg://..." python -m pytest tests/browser -m playwright
```

The suite starts the local FastAPI app, seeds safe dummy dashboard data, drives
admin login/navigation/logout in Chromium, checks representative CSRF-protected
forms are present, and verifies rendered normal dashboard pages do not expose
token hashes, encrypted one-time-secret material, provider keys, plaintext
gateway keys, prompts, completions, or session data. It does not call real
OpenAI/OpenRouter providers and does not send real email.

## GitHub CI Packaging Smoke

The public GitHub Actions CI includes a Docker Compose smoke job for the
repository packaging. It copies `.env.example` to `.env`, validates
`docker compose config`, builds the image, starts PostgreSQL, Redis, and
Mailpit, runs `slaif-gateway db upgrade` explicitly, starts API/worker/scheduler
services, checks `/healthz` and `/readyz`, validates the Nginx config with the
official `nginx:stable` image, and then runs `docker compose down -v` in
cleanup.

The CI smoke does not use real provider keys, does not call OpenAI/OpenRouter,
does not send real external email, and does not run migrations implicitly from
API/worker/scheduler startup.

## Production Notes

Docker Compose is local/development packaging and a clear service layout. It is
not full production hardening by itself.

Before production use:

- Replace every placeholder secret in `.env`.
- Use strong values for HMAC, admin session, one-time-secret encryption,
  provider, SMTP, and database secrets.
- Run migrations explicitly during controlled deploy steps.
- Use real PostgreSQL/Redis services or managed equivalents if appropriate.
- Put API traffic behind HTTPS, usually through Nginx or a managed ingress.
- Keep `/metrics` internal or allowlisted.
- Keep `/readyz` internal or allowlisted.
- Protect `/admin` with HTTPS, strong admin passwords, login rate limiting, and
  preferably an IP allowlist, VPN, or equivalent ingress control.
- Provide upstream provider secrets through environment variables, Docker
  secrets, or a deployment secret manager. Do not store provider key values in
  `provider_configs`; that table stores env var names only.
- Use a deployment secret manager or Docker secrets for production where
  appropriate. The `slaif-gateway secrets generate ...` CLI can produce strong
  initial values for local or self-hosted setup, but it is not a full
  secret-management system.
- Do not leave `LOG_LEVEL=DEBUG` running indefinitely in production except for a
  time-bounded incident diagnosis.
- Prefer `STRUCTURED_LOGS=true`, `GUNICORN_LOG_LEVEL=info`, and
  `CELERY_LOG_LEVEL=INFO` for production log aggregation.
- Monitor Redis rate-limit availability and choose fail-open/fail-closed
  behavior deliberately. PostgreSQL quotas and accounting remain authoritative.
- Replacing `TOKEN_HMAC_SECRET_V1` invalidates gateway keys signed with that
  secret unless the old secret remains configured.
- Replacing `ADMIN_SESSION_SECRET` invalidates active admin sessions.
- Replacing `ONE_TIME_SECRET_ENCRYPTION_KEY` can make existing encrypted
  one-time secrets undecryptable.

The server-side OpenAI upstream secret is `OPENAI_UPSTREAM_API_KEY`.
`OPENAI_API_KEY` is reserved for clients carrying gateway-issued keys.

## Diagnostic Logging

Production should normally stay at `LOG_LEVEL=INFO` with
`STRUCTURED_LOGS=true`, so API logs remain structured JSON and suitable for
operator log systems. Admin pages return generic browser-safe errors and a
server-generated reference such as `gw-...`; they do not render stack traces,
raw request bodies, cookies, CSRF tokens, session tokens, plaintext gateway
keys, provider keys, encrypted payloads, nonces, prompts, or completions.

For local diagnosis of an admin or worker issue, set:

```bash
LOG_LEVEL=DEBUG
STRUCTURED_LOGS=false
GUNICORN_LOG_LEVEL=debug
CELERY_LOG_LEVEL=DEBUG
```

Then inspect logs from the relevant services:

```bash
docker compose logs -f api
docker compose logs -f worker scheduler
docker compose logs api | rg '<diagnostic-id>'
```

Logs are redacted but can still contain sensitive operational metadata. Keep
them operator-side; this project intentionally does not expose a dashboard log
viewer.

## Streaming And Nginx

`deploy/nginx/slaif-api-gateway.conf` is a starting point. It proxies `/v1`,
`/admin`, and `/healthz` to the API service. `/readyz` is allowlisted to private
networks by default, and `/metrics` is denied by default.

Streaming routes require anti-buffering and long timeouts:

```nginx
proxy_http_version 1.1;
proxy_buffering off;
proxy_cache off;
proxy_read_timeout 3600s;
proxy_send_timeout 3600s;
```

TLS certificates, real domains, request-size limits, access logs, and network
allowlists are deployment-specific and must be reviewed by the operator.

## Worker And Scheduler

The `worker` service runs:

```bash
celery -A slaif_gateway.workers.celery_app:celery_app worker --loglevel=${CELERY_LOG_LEVEL:-INFO}
```

The `scheduler` service runs:

```bash
celery -A slaif_gateway.workers.celery_app:celery_app beat --loglevel=${CELERY_LOG_LEVEL:-INFO}
```

The worker handles explicit key email delivery tasks. Celery payloads carry IDs
only, never plaintext gateway keys or email bodies.

Scheduled reconciliation is disabled by default. Enabling
`ENABLE_SCHEDULED_RECONCILIATION=true` schedules safe backlog inspection only.
Automatic reconciliation mutation requires the matching
`RECONCILIATION_AUTO_EXECUTE_*` flag and `RECONCILIATION_DRY_RUN=false`.
Scheduled reconciliation tasks reuse existing service-layer logic, do not call
providers, and return safe summaries only.

Optional reconciliation alert webhooks are disabled by default. When
`ENABLE_RECONCILIATION_ALERTS=true` is configured with a generic webhook URL,
the scheduled backlog inspection task can send safe backlog counts to an
operator-managed alerting bridge. Alert webhooks do not mutate quota/accounting,
do not call providers, and do not send email. Payloads are counts-only by
default; `RECONCILIATION_ALERT_INCLUDE_IDS=true` adds only safe reservation and
usage-ledger IDs. Treat the webhook URL as a secret if it contains tokens.

Operational procedures for stale reservations and provider-completed recovery
are in [`runbooks/stale-reservation-reconciliation.md`](runbooks/stale-reservation-reconciliation.md)
and [`runbooks/provider-completed-reconciliation.md`](runbooks/provider-completed-reconciliation.md).

## Backups

Back up PostgreSQL. It is the source of truth for key metadata, HMAC digests,
quota counters, usage ledger rows, catalog metadata, audit logs, admin sessions,
and email delivery state.

Plaintext gateway keys are not stored, so they cannot be recovered from backups.
Protect these secrets separately from the database:

- `TOKEN_HMAC_SECRET_V*`
- `ADMIN_SESSION_SECRET`
- `ONE_TIME_SECRET_ENCRYPTION_KEY`
- upstream provider keys
- SMTP credentials

Losing an HMAC secret invalidates keys created with that HMAC version. Losing a
one-time-secret encryption key prevents recovery of pending encrypted delivery
secrets; rotate affected gateway keys instead of attempting to resend old
plaintext.

Backup/restore and secret-rotation procedures are documented in
[`runbooks/database-backup-restore.md`](runbooks/database-backup-restore.md),
[`runbooks/provider-key-rotation.md`](runbooks/provider-key-rotation.md),
[`runbooks/hmac-secret-rotation.md`](runbooks/hmac-secret-rotation.md), and
[`runbooks/one-time-secret-encryption-key.md`](runbooks/one-time-secret-encryption-key.md).

Docker and Nginx troubleshooting guidance is in
[`runbooks/docker-nginx-troubleshooting.md`](runbooks/docker-nginx-troubleshooting.md).

## Limitations

- This deployment packaging is not a formal production certification,
  compliance attestation, or penetration test.
- No CI/CD system is required or added by this repository packaging.
- Native Anthropic API, Responses hosted tools/stateful routes, embeddings,
  files, images, and audio endpoints remain unsupported unless separately
  implemented and documented. Current Responses support is stateless text-only
  `POST /v1/responses` with local function and custom tools only.
- Admin bulk/import/upload workflows are application features documented in
  README.md, `docs/security-model.md`, and `docs/compatibility-matrix.md`; the
  deployment packaging does not add separate asynchronous import/export job
  infrastructure beyond the implemented app and Celery services.
- Slack/PagerDuty-specific SDK integrations are not implemented; use the
  optional generic reconciliation webhook with an operator-managed bridge.
