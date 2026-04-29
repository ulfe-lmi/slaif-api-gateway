<div style="text-align: center;">
  <a href="https://www.slaif.si">
    <img src="https://slaif.si/img/logos/SLAIF_logo_ANG_barve.svg" width="400" height="400">
  </a>
</div>

# SLAIF API Gateway

SLAIF API Gateway is an open-source, OpenAI-compatible API gateway for educational and institutional LLM access. It lets users run ordinary OpenAI SDK examples by setting `OPENAI_API_KEY` and `OPENAI_BASE_URL`, while operators keep control over issued gateway keys, quotas, model access, provider routing, pricing, usage accounting, and audit logs.

The gateway is intended for workshops, courses, training events, and AI-factory environments where users need practical LLM API access but organizers must protect upstream provider credentials and spending.

For exact reviewer-facing behavior, see:

- [`docs/openai-compatibility.md`](docs/openai-compatibility.md) for supported OpenAI-compatible endpoints, request field policy, streaming behavior, and unsupported APIs.
- [`docs/provider-forwarding-contract.md`](docs/provider-forwarding-contract.md) for provider body/header mutation rules, accounting boundaries, and OpenAI/OpenRouter forwarding details.
- [`docs/compatibility-matrix.md`](docs/compatibility-matrix.md) for the current support and test coverage matrix.
- [`SECURITY.md`](SECURITY.md) for vulnerability reporting and review/audit scope.
- [`.env.example`](.env.example) and [`docs/configuration.md`](docs/configuration.md) for safe configuration templates and environment variable reference.
- [`docs/security-model.md`](docs/security-model.md) for gateway key lifecycle, provider isolation, quota/accounting, Redis, email/Celery, and logging security boundaries.

## Current Status

Implemented:

- `GET /healthz` and `GET /readyz`.
- Authenticated `GET /v1/models` backed by local provider and route metadata, filtered by the gateway key's effective model allow-list.
- Non-streaming and SSE streaming `POST /v1/chat/completions` with request policy checks, route resolution, pricing/FX lookup, PostgreSQL quota reservation, provider forwarding through OpenAI/OpenRouter adapters, and accounting finalization.
- Gateway key generation/authentication with HMAC-only storage and configurable key prefixes.
- Typer CLI commands for admin bootstrap, institutions, cohorts, owners, key management, provider config, model routes, pricing, FX rates, usage summaries/exports, and DB migration helpers.
- PostgreSQL-backed quota/accounting, usage ledger metadata, model catalog, route resolution, and pricing/FX services.
- Production provider-secret validation that requires enabled built-in providers to have non-placeholder upstream secrets, keeps `OPENAI_API_KEY` reserved for client gateway keys, and checks enabled DB provider config env vars in `/readyz`.
- Manual stale quota-reservation reconciliation for operator repair of expired pending reservations after crashes.
- Redis-backed operational rate limiting for `/v1/chat/completions` when enabled, covering request, estimated-token, and concurrency limits.
- Observability foundation with request IDs, structured log redaction, sanitized provider diagnostics, finalized EUR cost metrics, and controlled `/metrics` exposure.
- Admin web authentication foundation with `/admin/login`, `/admin/logout`, a placeholder `/admin` dashboard, key list/detail pages with CSRF-protected create, suspend/activate/revoke, validity-window, PostgreSQL hard quota limit, usage-counter reset, rotation, and create/rotate email-delivery mode actions, read-only owner/institution/cohort pages, provider config pages with CSRF-protected create/edit/enable/disable metadata actions, model route pages with CSRF-protected create/edit/enable/disable metadata actions, pricing pages with CSRF-protected create/edit/enable/disable metadata actions, FX pages with CSRF-protected create/edit metadata actions, usage/audit activity pages, and email delivery pages with CSRF-protected send-now/enqueue actions for valid pending key deliveries, secure cookie settings, server-side session rows, and CSRF-protected forms.
- Explicit CLI/dashboard-controlled email delivery for gateway keys using encrypted one-time secrets, SMTP via `aiosmtplib`, and Celery task payloads that carry IDs only.
- Admin role semantics are explicit for the current implementation: every active admin account is a full operator, and `superadmin` is metadata/future-proofing rather than an enforced RBAC boundary.
- Mocked OpenAI/OpenRouter E2E coverage using the official OpenAI Python client, including `stream=True` chat completions.

Not implemented yet:

- Bulk key creation forms, arbitrary/old-key dashboard email resend actions, pricing import/upload forms, FX import/upload/external-refresh forms, and state-changing management pages for owners, institutions, cohorts, usage, and audit.
- Automatic key-email sending by default.
- OpenTelemetry tracing and full deployment docs.

## OpenAI-Compatible Usage

Users configure the standard OpenAI client environment variables only:

```bash
export OPENAI_API_KEY="sk-slaif-..."
export OPENAI_BASE_URL="http://localhost:8000/v1"
```

Then ordinary OpenAI Python client code works:

```python
from openai import OpenAI

client = OpenAI()
response = client.chat.completions.create(
    model="gpt-test-mini",
    messages=[{"role": "user", "content": "Hello"}],
)
print(response.choices[0].message.content)
```

Streaming chat completions use OpenAI-compatible Server-Sent Events and work with the official client:

```python
stream = client.chat.completions.create(
    model="gpt-test-mini",
    messages=[{"role": "user", "content": "Hello"}],
    stream=True,
)
for chunk in stream:
    if chunk.choices:
        print(chunk.choices[0].delta.content or "", end="")
```

Common Chat Completions parameters such as `temperature`, `top_p`, `tools`,
`tool_choice`, `response_format`, `seed`, `user`, `logprobs`, `metadata`, and
service-tier options are passed through to the selected upstream provider unless
the gateway explicitly rejects them. For streaming requests, the gateway forwards
`stream_options.include_usage=true` so final provider usage can be captured for
accounting.

Chat Completions `n` is preserved when omitted or exactly `1`. `n > 1` is
intentionally rejected until multi-choice quota reservation and cost accounting
are implemented; it is not silently clamped or dropped.

`sk-slaif-` is the default generated gateway key prefix. New key generation uses `GATEWAY_KEY_PREFIX`, and authentication accepts only prefixes configured in `GATEWAY_KEY_ACCEPTED_PREFIXES`, which must include the active generation prefix.

## Quick Local Setup

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Unit tests do not require PostgreSQL, Redis, Docker, or real upstream provider keys:

```bash
python -m pytest tests/unit
```

For DB-backed operation, configure PostgreSQL and run migrations explicitly:

```bash
export DATABASE_URL="postgresql+asyncpg://slaif:slaif@localhost:5432/slaif_gateway"
alembic upgrade head
uvicorn --app-dir app slaif_gateway.main:app --reload
```

The FastAPI app creates one async SQLAlchemy engine/sessionmaker during lifespan and disposes the engine on shutdown. Database pool and timeout behavior is configurable:

```bash
export DATABASE_POOL_SIZE=5
export DATABASE_MAX_OVERFLOW=10
export DATABASE_POOL_TIMEOUT_SECONDS=30
export DATABASE_POOL_RECYCLE_SECONDS=1800
export DATABASE_POOL_PRE_PING=true
export DATABASE_CONNECT_TIMEOUT_SECONDS=10
export DATABASE_STATEMENT_TIMEOUT_MS=30000
```

`DATABASE_POOL_PRE_PING` is enabled by default so stale pooled connections are checked before use. `DATABASE_CONNECT_TIMEOUT_SECONDS` is passed to asyncpg connection setup. `DATABASE_STATEMENT_TIMEOUT_MS` is optional; when set, PostgreSQL receives a per-connection `statement_timeout` server setting.

`/readyz` checks database configuration, reachability, and whether the database's `alembic_version` revision is current with the committed Alembic head. Redis is not required for readiness unless `ENABLE_REDIS_RATE_LIMITS=true`; when enabled, the app creates one Redis client during lifespan and `/readyz` requires a successful Redis ping. In production, `/readyz` also checks enabled `provider_configs.api_key_env_var` references and reports only missing environment variable names when details are enabled, never secret values. `/readyz` never runs migrations or performs destructive actions.

In development/test, `/readyz` includes detailed Alembic current/head revision fields by default. In production, exact revision details are hidden by default and only coarse `database`, `schema`, and `redis` statuses are returned unless `READYZ_INCLUDE_DETAILS=true`. Keep `/readyz` internal or reverse-proxy allowlisted in production; when Nginx or Docker deployment files are added, they should deny public access to `/readyz` by default.

When `APP_ENV=production`, startup logs warn if `READYZ_INCLUDE_DETAILS=true` because detailed readiness output is more informative than the safe production default. The warning is an operator visibility guardrail, not a substitute for network or reverse-proxy controls.

Redis rate limiting is optional and controls temporary operational throttles only:

```bash
export ENABLE_REDIS_RATE_LIMITS=true
export REDIS_URL="redis://localhost:6379/0"
export DEFAULT_RATE_LIMIT_REQUESTS_PER_MINUTE=60
export DEFAULT_RATE_LIMIT_TOKENS_PER_MINUTE=120000
export DEFAULT_RATE_LIMIT_CONCURRENT_REQUESTS=5
export RATE_LIMIT_CONCURRENCY_TTL_SECONDS=300
export RATE_LIMIT_CONCURRENCY_HEARTBEAT_SECONDS=30
```

When enabled, `/v1/chat/completions` checks Redis after request policy token estimation and before route resolution, pricing, PostgreSQL hard quota reservation, and provider forwarding. Rate-limit failures return OpenAI-shaped errors. PostgreSQL remains authoritative for durable hard quota and accounting.

Request and estimated-token limits are per-window operational throttles. Concurrency limits track active request IDs separately from that window: streaming responses refresh their Redis active slot while open, release removes the specific request ID, and the concurrency TTL is a conservative crash-cleanup fallback rather than the normal lifetime of a long stream.

Global defaults apply when a key does not define an override. Operators can set per-key Redis rate-limit policy at creation or later:

```bash
slaif-gateway keys create --owner-id <owner-id> --valid-days 30 \
  --rate-limit-requests-per-minute 60 \
  --rate-limit-tokens-per-minute 100000 \
  --rate-limit-concurrent-requests 3

slaif-gateway keys set-rate-limits <key-id> \
  --requests-per-minute 60 \
  --tokens-per-minute 100000 \
  --concurrent-requests 3

slaif-gateway keys set-rate-limits <key-id> --clear-all
```

Per-key Redis limits are stored with key metadata and are operational throttles only. Clearing a per-key field lets the configured global default apply; clearing all per-key Redis limits does not change PostgreSQL hard quota limits or usage counters. Redis rate limiting is enforced only when `ENABLE_REDIS_RATE_LIMITS=true`.

## Observability

Every HTTP response includes an `X-Request-ID` header. A safe incoming `X-Request-ID` is preserved; otherwise the gateway generates one and binds it to structured logs.

Structured logs redact Authorization headers, gateway/provider keys, cookies, passwords, CSRF/session tokens, token hashes, encrypted payloads, and nonces. Redaction recognizes configured gateway key prefixes as well as generic gateway-key-shaped values, and never preserves secret characters from the key secret component. Accounting and audit metadata sanitization handles nested sensitive fields across camelCase, snake_case, and kebab-case keys. Prompts and completions are not logged or stored by default.

`GET /metrics` exposes Prometheus text metrics in development/test when `ENABLE_METRICS=true`. In production, metrics access is restricted by default through `METRICS_REQUIRE_AUTH`; because admin auth for metrics is not implemented yet, production access is denied unless an explicit `METRICS_ALLOWED_IPS` allowlist permits the client IP. `METRICS_PUBLIC_IN_PRODUCTION=true` intentionally makes metrics public and should not be used for internet-facing deployments. Protect `/metrics` with an internal network, reverse-proxy allowlist, or an admin/auth layer when one is available; future Nginx/deployment docs should keep `/metrics` internal or allowlisted by default. Redis is not required for metrics, and OpenTelemetry is not implemented yet.

When `APP_ENV=production`, startup logs warn if metrics are explicitly made public or metrics auth is disabled. These warnings make risky overrides visible but do not replace internal networking, reverse-proxy allowlists, or an admin/auth layer.

## Admin Web Foundation

The server-rendered admin foundation exposes `GET /admin/login`, `POST /admin/login`, `GET /admin`, `POST /admin/logout`, key pages under `/admin/keys`, read-only owner/institution/cohort pages, provider config pages under `/admin/providers`, model route pages under `/admin/routes`, pricing pages under `/admin/pricing`, FX pages under `/admin/fx`, activity pages under `/admin/usage` and `/admin/audit`, and email delivery pages under `/admin/email-deliveries`. Key dashboard pages show safe metadata such as public key ID, key hint, owner, status, validity, quota counters, allowed model/endpoint/provider summaries, and rate-limit policy. The dashboard includes a CSRF-protected key creation form for existing owners and cohorts; key creation and key rotation support explicit email-delivery modes: `none`, `pending`, `send-now`, and `enqueue`. `none` preserves the no-cache one-time browser plaintext result. `pending` creates an email delivery record linked to the encrypted one-time secret and still shows the plaintext once. `send-now` delivers through SMTP and suppresses browser plaintext display. `enqueue` queues Celery delivery with IDs only and suppresses browser plaintext display. Existing pending/failed key email deliveries can also be sent now or enqueued from the email delivery detail page when they are backed by a valid unconsumed one-time secret; those actions require CSRF and explicit confirmation, never accept plaintext key input, and never show plaintext keys in the browser. Key detail pages also provide CSRF-protected POST actions to suspend, activate, permanently revoke, update validity windows, update PostgreSQL hard quota limits, reset usage counters, and rotate keys through the existing key service and audit behavior. Reserved-counter reset requires an additional repair confirmation, usage reset does not delete usage ledger rows, and Redis operational rate-limit counters are not reset by this action. Old plaintext keys are never resent. Lost keys cannot be resent; rotate them instead. Hard quota limits are PostgreSQL-backed and distinct from Redis operational rate limits. Owner, institution, and cohort pages show safe record metadata plus key count summaries. Provider config pages support CSRF-protected create, edit, enable, and disable actions for safe metadata only. They store `api_key_env_var` names because those are configuration references, but they never accept, store, or display provider key values. Model route pages support CSRF-protected create, edit, enable, and disable actions for local routing metadata only; route forms reference provider config rows and env var names, never provider key values, and do not change pricing, FX, or provider adapter behavior. Pricing pages support CSRF-protected create, edit, enable, and disable actions for local pricing metadata only. Pricing changes affect future quota reservation and accounting through the existing pricing service; the dashboard does not change pricing calculation semantics and does not implement pricing import/upload. FX pages support CSRF-protected create and edit actions for local FX metadata only. FX changes affect future EUR conversion, quota reservation, and accounting through the existing FX lookup path; the dashboard does not change FX runtime semantics and does not implement imports, uploads, external FX API calls, or scheduled refresh. The current FX schema has no enabled state, so active status is controlled by validity windows. Usage, audit, and email delivery pages show safe local metadata only; they do not render prompt/completion content, raw request/response bodies, email bodies, plaintext key material, token hashes, encrypted one-time-secret payloads, nonces, provider key values, password hashes, or session tokens. Plaintext gateway keys are never shown after creation/rotation except for explicit one-time creation/rotation result output in `none` and `pending` modes.

Arbitrary old-key dashboard email resend actions, bulk key creation forms, pricing import/upload forms, FX import/upload/external-refresh forms, and owner, institution, cohort, usage, and audit mutation pages are not implemented yet.

Admin passwords are verified with the existing Argon2id utilities. Login has DB/audit-backed failed-attempt rate limiting by normalized email and client IP; failed attempts and temporary lockout events are audited, messages remain generic, and Redis is not required. Login creates a server-side `admin_sessions` row and stores only HMAC-hashed session and CSRF tokens in PostgreSQL. The browser receives a session cookie named by `ADMIN_SESSION_COOKIE_NAME`; it is `HttpOnly`, `SameSite=Lax` by default, and `Secure` by default in production. State-changing admin forms use CSRF tokens. This foundation uses local Jinja2 templates and static CSS only; it does not use CDN Tailwind or CDN HTMX.

All active admin users are currently full operators. The `role` field and the
CLI `--superadmin` flag are preserved as metadata/future-proofing for later
RBAC work, but the current dashboard and admin CLI do not enforce per-role
permissions or superadmin-only actions. Inactive admin accounts cannot log in,
and revoked or expired admin sessions cannot access admin routes. Protect every
active admin account as highly privileged; MFA and role-gated permissions remain
future hardening options.

Provider HTTP and streaming errors can attach bounded, sanitized diagnostics to
failure ledger metadata for operator troubleshooting. Raw provider response
bodies are not returned to clients or stored. Diagnostic metadata redacts
provider keys, gateway keys, token hashes, Authorization headers, cookies, and
session data, and drops prompt/completion/request/response body fields. Successful
accounting finalization records finalized EUR cost in Prometheus metrics.

## CLI Quickstart

Create prerequisite records and a gateway key:

```bash
slaif-gateway admin create --email admin@example.org --display-name "Admin User" --password-stdin
slaif-gateway institutions create --name "SLAIF Test Institute" --country SI
slaif-gateway cohorts create --name "SLAIF Workshop 2026"
slaif-gateway owners create --name Ada --surname Lovelace --email ada@example.org --institution-id <institution-id>
slaif-gateway keys create --owner-id <owner-id> --valid-days 30
slaif-gateway keys set-rate-limits <key-id> --requests-per-minute 60 --tokens-per-minute 100000 --concurrent-requests 3
```

Text-mode `keys create` and `keys rotate` show the plaintext gateway key once for the operator workflow. JSON mode is secret-safe by default: use `--show-plaintext` only when intentionally capturing the one-time key in JSON, or use `--secret-output-file PATH` to write it to a new `0600` file without printing it to stdout. Lost keys cannot be resent; rotate them. Reserved-counter repair requires `keys reset-usage --reset-reserved --confirm-reset-reserved`.

Email delivery is explicit and operator-controlled; key creation and rotation never send email by default. Configure local SMTP/Mailpit-style settings before using it:

```bash
export ENABLE_EMAIL_DELIVERY=true
export SMTP_HOST=localhost
export SMTP_PORT=1025
export SMTP_FROM=noreply@example.org
export CELERY_BROKER_URL="${REDIS_URL:-redis://localhost:6379/0}"
```

`slaif-gateway keys create --email-delivery pending` and `slaif-gateway keys rotate --email-delivery pending` create a pending `email_deliveries` row linked to the new one-time secret. Use `--email-delivery send-now` to send immediately, or `--email-delivery enqueue` to queue the Celery task. Send-now and enqueue modes treat email as the secret delivery channel and do not print the plaintext key to stdout; they reject `--show-plaintext` and `--secret-output-file` to avoid multiple secret destinations.

`slaif-gateway email test --to ada@example.org` sends a safe test email with no gateway key material. `slaif-gateway email send-pending-key --one-time-secret-id <id> --send-now` retries/sends a key from an existing encrypted `one_time_secrets` row, and `--enqueue` queues the Celery task instead. The task payload contains only IDs such as `one_time_secret_id` and `email_delivery_id`; plaintext gateway keys are decrypted only inside the delivery process and are never placed in Redis/Celery payloads, audit rows, or `email_deliveries`. Lost keys cannot be resent from old plaintext; rotate the key and send the replacement one-time secret.

Configure local provider, route, pricing, and FX metadata:

```bash
slaif-gateway providers add --provider openai --api-key-env-var OPENAI_UPSTREAM_API_KEY
slaif-gateway routes add --requested-model gpt-test-mini --match-type exact --provider openai --upstream-model gpt-test-mini
slaif-gateway pricing add --provider openai --model gpt-test-mini --endpoint chat.completions --currency EUR --input-price-per-1m 0.10 --output-price-per-1m 0.20
slaif-gateway fx add --base-currency USD --quote-currency EUR --rate 0.920000000
```

Inspect usage ledger metadata:

```bash
slaif-gateway usage summarize --group-by provider_model
slaif-gateway usage export --format csv --output usage.csv
```

Inspect and repair expired pending quota reservations:

```bash
slaif-gateway quota list-expired-reservations
slaif-gateway quota reconcile-expired-reservations --dry-run
slaif-gateway quota reconcile-expired-reservations --execute --reason "crash recovery"
```

Inspect and repair streaming provider-completed rows whose accounting finalization failed:

```bash
slaif-gateway quota list-provider-completed-recovery
slaif-gateway quota reconcile-provider-completed --dry-run
slaif-gateway quota reconcile-provider-completed --execute --reason "finalization repair"
```

Provider, route, pricing, FX, and usage CLI commands operate on local metadata only. They do not call upstream providers, fetch live pricing, or fetch live FX rates.
Quota reconciliation is manual/operator tooling for expired pending reservations and provider-completed finalization failures; it defaults to dry-run and does not implement background or Celery cleanup. Provider-completed repair uses the stored usage/cost metadata, does not call providers, and does not treat a provider-completed success as a zero-cost failure.

## Testing

Run the normal local checks:

```bash
python -m pytest tests/unit
python -m ruff check app tests
alembic heads
```

Integration tests use `TEST_DATABASE_URL` when set, may use Testcontainers when Docker is available, and otherwise skip cleanly:

```bash
TEST_DATABASE_URL="postgresql+asyncpg://..." python -m pytest tests/integration
```

The OpenAI/OpenRouter E2E tests use the official `openai` Python package with `OpenAI()` reading `OPENAI_API_KEY` and `OPENAI_BASE_URL`, but upstream HTTP is mocked with RESPX. Normal tests require no real OpenAI or OpenRouter keys and make no real upstream calls.
Streaming E2E tests also use mocked upstream SSE responses for OpenAI and OpenRouter. Successful streaming finalization requires provider final usage metadata. If a stream completes without final usage, the gateway releases the reservation, records a failed/incomplete ledger event with zero actual cost, emits a safe SSE error event, and does not emit a normal successful `[DONE]`. If a provider stream completes with usage but accounting finalization fails after content was delivered, the gateway keeps a durable provider-completed usage record marked for reconciliation instead of treating it as a zero-cost provider failure. Prompt and completion content are not stored. Client-disconnect cleanup is covered by a real ASGI server test that closes a stream early and verifies reservation/Redis concurrency cleanup.

Redis rate-limit integration tests use `TEST_REDIS_URL` when set. If it is not set and `redis-server` is available locally, tests start a temporary user-owned Redis instance on a free localhost port.

## External Reviews And Remediation

The project has undergone external quality/security-oriented mid-development reviews. Review artifacts and remediation status are tracked in:

- [`docs/security/reviews/`](docs/security/reviews/)
- [`docs/security/reviews/remediation-matrix.md`](docs/security/reviews/remediation-matrix.md)

These reviews are not formal certifications or penetration tests. They document major architecture, security, accounting, compatibility, and production-readiness findings and the PRs/checks that addressed them.

## Security Notes

- Plaintext gateway keys are shown only once at creation or rotation.
- PostgreSQL stores gateway key HMAC digests, not plaintext gateway keys.
- Provider configs store provider API key environment variable names, not provider secret values.
- Server-side upstream provider secrets use `OPENAI_UPSTREAM_API_KEY` and `OPENROUTER_API_KEY`; `OPENAI_API_KEY` remains reserved for OpenAI-compatible clients carrying gateway-issued keys.
- Usage summaries and exports include metadata, token counts, and costs. They do not include prompts, completions, request bodies, response bodies, token hashes, provider keys, or other secrets.
- Usage ledger rows do not store prompts or completions by default.
- Unknown pricing or required FX conversion data fails closed for cost-limited requests.
- Hard quota reservation uses PostgreSQL row locking and reserved counters, not Redis.
- Redis rate limiting is temporary operational throttling only; PostgreSQL remains the hard quota source of truth.

## Schema And Migrations

`docs/database-schema.md` is the authoritative schema source. Schema changes must update that document, SQLAlchemy models, Alembic migrations, and tests together.

Migrations are explicit operator actions and are not run during application startup or `/readyz`. Fresh `alembic upgrade head` runs create the project schema and version table from the committed migration chain.

## Roadmap

Near-term remaining work includes owner/institution/cohort mutation pages, bulk key creation, pricing/FX import workflows, OpenTelemetry tracing, and fuller public deployment documentation.

For production streaming behind Nginx, disable proxy buffering and use long read/send timeouts so SSE chunks reach clients promptly.

## Maintainer

Janez Perš  
Faculty of Electrical Engineering, University of Ljubljana  
Laboratory for Machine Intelligence (LMI)  
Email: janez.pers@fe.uni-lj.si  

- Profile: https://lmi.fe.uni-lj.si/en/janez-pers-2/
- Laboratory: https://lmi.fe.uni-lj.si/en

## Security Contact

For responsible disclosure of vulnerabilities, please contact:  
janez.pers@fe.uni-lj.si

## Acknowledgement

We acknowledge the support of the EC/EuroHPC JU and the Slovenian Ministry of HESI via the project SLAIF (grant number 101254461).

Project website: https://www.slaif.si
