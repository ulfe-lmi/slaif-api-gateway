# Configuration

This gateway is configured with environment variables. Secrets should come from
environment variables, a deployment secret manager, or Docker secrets when those
deployment files exist. The root `.env.example` file is a safe template only; it
must not contain real credentials.

Migrations are explicit operator actions. The application and `/readyz` do not
run migrations on startup.

## Required Production Secrets

Production requires strong, non-placeholder values for:

- `TOKEN_HMAC_SECRET_V1`, or the version matching `ACTIVE_HMAC_KEY_VERSION`
- `ADMIN_SESSION_SECRET`
- `ONE_TIME_SECRET_ENCRYPTION_KEY`
- `OPENAI_UPSTREAM_API_KEY` and/or `OPENROUTER_API_KEY` when those providers are enabled
- `SMTP_PASSWORD` when the configured SMTP server requires authentication

`ONE_TIME_SECRET_ENCRYPTION_KEY` must be base64url-encoded 32-byte key material.
Rotate any provider or SMTP secret that is accidentally committed, logged, or
shared.

## Client Vs Upstream Provider Keys

Training users configure the standard OpenAI client variables:

```bash
export OPENAI_API_KEY="sk-slaif-..."
export OPENAI_BASE_URL="https://api.ulfe.slaif.si/v1"
```

`OPENAI_API_KEY` is a gateway-issued key from this service. It is not the real
OpenAI provider secret.

The server uses `OPENAI_UPSTREAM_API_KEY` for the actual OpenAI provider key.
Do not set the gateway's upstream provider secret as `OPENAI_API_KEY` in the
server environment. OpenRouter uses `OPENROUTER_API_KEY`.

## App And Gateway Keys

- `APP_ENV` controls environment-sensitive defaults such as production readiness
  details and metrics protection.
- `APP_BASE_URL` is the local app base URL.
- `PUBLIC_BASE_URL` is the user-facing OpenAI-compatible base URL and should
  usually include `/v1`.
- `GATEWAY_KEY_PREFIX` controls newly generated gateway key prefixes.
- `GATEWAY_KEY_ACCEPTED_PREFIXES` controls accepted prefixes and must include the
  active generation prefix.
- `ACTIVE_HMAC_KEY_VERSION` selects which versioned HMAC secret new keys use.
- `TOKEN_HMAC_SECRET_V1` stores the server-side HMAC pepper for version 1.
- `TOKEN_HMAC_SECRET` is a legacy/non-production fallback for version 1 only.

## Database Configuration

- `DATABASE_URL` is the SQLAlchemy async PostgreSQL URL.
- `DATABASE_POOL_SIZE`, `DATABASE_MAX_OVERFLOW`,
  `DATABASE_POOL_TIMEOUT_SECONDS`, and `DATABASE_POOL_RECYCLE_SECONDS` configure
  SQLAlchemy async engine pooling.
- `DATABASE_POOL_PRE_PING` is enabled by default so stale pooled connections are
  checked before use.
- `DATABASE_CONNECT_TIMEOUT_SECONDS` is passed to asyncpg connection setup.
- `DATABASE_STATEMENT_TIMEOUT_MS` is optional; when set, each asyncpg connection
  receives a PostgreSQL `statement_timeout` server setting.

CLI DB commands and service workflows create explicit settings/sessionmaker
instances. Engines are not created at import time.

## Redis And Rate Limiting

Redis is used for operational throttling and Celery broker state. PostgreSQL
remains the hard quota and accounting source of truth.

- `REDIS_URL` configures Redis access.
- `ENABLE_REDIS_RATE_LIMITS` enables request, estimated-token, and concurrency
  throttles for supported `/v1` traffic.
- `REDIS_CONNECT_TIMEOUT_SECONDS` and `REDIS_SOCKET_TIMEOUT_SECONDS` bound Redis
  operations.
- `DEFAULT_RATE_LIMIT_REQUESTS_PER_MINUTE`,
  `DEFAULT_RATE_LIMIT_TOKENS_PER_MINUTE`, and
  `DEFAULT_RATE_LIMIT_CONCURRENT_REQUESTS` provide global defaults when key
  metadata does not override them.
- `RATE_LIMIT_FAIL_CLOSED` controls Redis failure behavior. When unset,
  production fails closed and development/test fails open.
- `RATE_LIMIT_CONCURRENCY_TTL_SECONDS`,
  `RATE_LIMIT_CONCURRENCY_HEARTBEAT_SECONDS`, and
  `RATE_LIMIT_CONCURRENCY_TTL_GRACE_SECONDS` control active concurrency slot
  cleanup and stream heartbeats.

## Provider Configuration

- `OPENAI_UPSTREAM_API_KEY` supplies the OpenAI provider key.
- `OPENROUTER_API_KEY` supplies the OpenRouter provider key.
- `ENABLE_OPENAI_PROVIDER` and `ENABLE_OPENROUTER_PROVIDER` toggle provider
  availability at configuration level.

The `provider_configs` table stores provider metadata and environment variable
names such as `OPENAI_UPSTREAM_API_KEY`; it does not store provider secret
values. Model routes, pricing, and FX rates are configured through CLI/database
metadata.

## Request Caps

- `DEFAULT_MAX_OUTPUT_TOKENS` is injected when a supported request omits output
  token controls.
- `HARD_MAX_OUTPUT_TOKENS` rejects requests above the configured maximum output.
- `HARD_MAX_INPUT_TOKENS` rejects requests whose estimated input is too large.

These caps protect hard quota reservation by bounding worst-case usage before
upstream forwarding.

## Metrics, Readiness, And Logging

- `/healthz` is process liveness and can be public-ish.
- `/readyz` checks database/schema readiness and Redis readiness only when
  Redis-backed features are enabled. Keep it internal or allowlisted in
  production.
- `/metrics` exposes Prometheus metrics. Keep it internal or allowlisted in
  production.
- `ENABLE_METRICS=false` disables metrics.
- `METRICS_REQUIRE_AUTH`, `METRICS_PUBLIC_IN_PRODUCTION`, and
  `METRICS_ALLOWED_IPS` control production metrics exposure.
- `READYZ_INCLUDE_DETAILS` controls whether exact readiness details such as
  Alembic revisions are included.
- `REQUEST_ID_HEADER`, `LOG_LEVEL`, and `STRUCTURED_LOGS` control request IDs
  and logging output.

Production startup logs warn when risky explicit overrides make `/metrics`
public or `/readyz` more detailed than the safe default. These warnings are not a
substitute for internal networking, reverse proxy allowlists, or an admin/auth
layer.

Structured logs redact gateway keys, provider keys, passwords, cookies, session
tokens, token hashes, encrypted payloads, nonces, and other sensitive fields.

## Email, Celery, And SMTP

- `ENABLE_EMAIL_DELIVERY` enables SMTP key delivery workflows.
- `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM`,
  `SMTP_USE_TLS`, `SMTP_STARTTLS`, and `SMTP_TIMEOUT_SECONDS` configure SMTP.
- `EMAIL_KEY_SECRET_MAX_AGE_SECONDS` controls encrypted one-time key delivery
  secret lifetime.
- `CELERY_BROKER_URL` configures the Celery broker; when unset, Celery can use
  `REDIS_URL`.
- `CELERY_RESULT_BACKEND` is optional and can remain empty.

Use Mailpit or another fake/local SMTP service for development and tests. Celery
task payloads contain IDs only, never plaintext gateway keys. Lost keys cannot
be resent; rotate and send a replacement key.

## Production Notes

- Never commit `.env`.
- Never commit real provider keys, gateway keys, SMTP passwords, HMAC secrets,
  session secrets, or one-time-secret encryption keys.
- Rotate provider keys immediately if leaked.
- Rotate HMAC secrets carefully; removing an old version invalidates keys that
  were created with that version.
- Use HTTPS and a reverse proxy in production. When deployment/Nginx files are
  added, keep `/readyz` and `/metrics` internal or allowlisted and configure SSE
  streaming without proxy buffering.
