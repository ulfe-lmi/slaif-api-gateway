# Deployment

This document describes the repository Docker Compose packaging and the
deployment boundaries operators must keep explicit. It is not a production
certification or a complete site reliability runbook.

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
service names.

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

Create local catalog metadata before sending traffic through `/v1`:

```bash
docker compose run --rm api slaif-gateway providers add \
  --provider openai \
  --api-key-env-var OPENAI_UPSTREAM_API_KEY

docker compose run --rm api slaif-gateway routes add \
  --requested-model gpt-test-mini \
  --match-type exact \
  --provider openai \
  --upstream-model gpt-test-mini

docker compose run --rm api slaif-gateway pricing add \
  --provider openai \
  --model gpt-test-mini \
  --endpoint chat.completions \
  --currency EUR \
  --input-price-per-1m 0.10 \
  --output-price-per-1m 0.20

docker compose run --rm api slaif-gateway fx add \
  --base-currency USD \
  --quote-currency EUR \
  --rate 0.920000000
```

Create prerequisite owner records and issue a gateway key with the existing CLI
commands documented in the README. Users then call the local gateway with normal
OpenAI-compatible variables:

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

The server-side OpenAI upstream secret is `OPENAI_UPSTREAM_API_KEY`.
`OPENAI_API_KEY` is reserved for clients carrying gateway-issued keys.

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
celery -A slaif_gateway.workers.celery_app:celery_app worker --loglevel=INFO
```

The `scheduler` service runs:

```bash
celery -A slaif_gateway.workers.celery_app:celery_app beat --loglevel=INFO
```

The worker handles explicit key email delivery tasks. Celery payloads carry IDs
only, never plaintext gateway keys or email bodies.

Scheduled reconciliation is disabled by default. Enabling
`ENABLE_SCHEDULED_RECONCILIATION=true` schedules safe backlog inspection only.
Automatic reconciliation mutation requires the matching
`RECONCILIATION_AUTO_EXECUTE_*` flag and `RECONCILIATION_DRY_RUN=false`.
Scheduled reconciliation tasks reuse existing service-layer logic, do not call
providers, and return safe summaries only.

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

## Limitations

- This deployment packaging is not a formal production certification,
  compliance attestation, or penetration test.
- No CI/CD system is required or added by this repository packaging.
- Native Anthropic API, Responses API, embeddings, files, images, and audio
  endpoints remain unsupported unless separately implemented and documented.
- Bulk import/upload workflows and external alert sinks are not implemented by
  this deployment slice.
