# AGENTS.md — SLAIF API Gateway

This file is the implementation brief for Codex or any other coding agent working on this repository.

The project is an open-source, production-grade, OpenAI-compatible API gateway for SLAIF training and education. It issues its own API keys, enforces hard per-key quotas, accounts for tokens and cost, forwards permitted requests to upstream providers such as OpenAI and OpenRouter, and exposes an admin dashboard plus CLI for key management.

The project must be designed so normal users can use the standard OpenAI Python client with no code changes beyond environment variables.

---

## 1. Final project decisions

### 1.1 Project identity

- Repository name: `slaif-api-gateway`
- Python package/import name: `slaif_gateway`
- Python package location: `app/slaif_gateway/`
- CLI command: `slaif-gateway`
- Docker image name: `slaif-api-gateway`
- Preferred license: Apache License 2.0
- Public production-style base URL: `https://api.ulfe.slaif.si/v1`
- Default gateway API key prefix: `sk-slaif-`, configurable through `GATEWAY_KEY_PREFIX`; accepted prefixes are configured through `GATEWAY_KEY_ACCEPTED_PREFIXES`

### 1.2 Distribution model

This project is intended to be open source.

Source distribution is by `git clone`:

```bash
git clone https://github.com/<org>/slaif-api-gateway.git
cd slaif-api-gateway
```

Runtime/deployment is by Docker/Docker Compose:

```bash
cp .env.example .env
docker compose up --build
```

Do not design around private deployment assumptions. Do not require CI/CD. Local build and Docker Compose deployment must be fully supported.

### 1.3 Client compatibility requirement

User-facing examples and documentation MUST use standard OpenAI-compatible environment variables only:

```bash
export OPENAI_API_KEY="sk-slaif-..."
export OPENAI_BASE_URL="https://api.ulfe.slaif.si/v1"
```

Then ordinary code must work:

```python
from openai import OpenAI

client = OpenAI()
```

Do NOT introduce `SLAIF_API_KEY`, `SLAIF_BASE_URL`, or other custom client environment variables in user-facing examples. The point is OpenAI-compatible client usage.

The gateway-issued key is supplied by the user as the standard Bearer token in the `Authorization` header. Internally, the gateway validates that key, applies policy and quota, then substitutes the real upstream provider key before forwarding the request.

### 1.4 Compatibility goal

The implementation goal is a 100% OpenAI-compatible client experience for the supported endpoint set.

That means:

- OpenAI SDKs should work against this gateway by setting `OPENAI_API_KEY` and `OPENAI_BASE_URL`.
- Endpoint paths must preserve the `/v1/...` structure.
- Request and response bodies must be OpenAI-shaped.
- Streaming must be Server-Sent Events compatible.
- Errors from `/v1` routes must be OpenAI-shaped JSON errors.
- Unsupported endpoints must return OpenAI-shaped errors, not custom gateway errors.
- A compatibility matrix must document the exact endpoint support level.
  Current compatibility documentation lives in `docs/compatibility-matrix.md`.

Do not expose a custom API to training users unless explicitly requested later.

### 1.5 Provider compatibility boundary

Initial upstream providers:

- OpenAI through a native OpenAI adapter.
- OpenRouter through an OpenRouter adapter.

Anthropic-family models are supported only through OpenRouter's OpenAI-compatible interface unless a separate native Anthropic adapter is explicitly implemented later with request/response translation and tests.

Do not claim native Anthropic API compatibility in v1.

---

## 2. Locked technology stack

Use this stack unless the maintainer explicitly changes it.

### 2.1 Runtime and language

- Python 3.12+
- Async-first implementation
- `pyproject.toml` based packaging
- Prefer `uv` for dependency locking if used by the project; otherwise use standard pinned dependencies

### 2.2 Database

- Production source of truth: PostgreSQL 16+
- ORM: SQLAlchemy 2.x async
- PostgreSQL async driver: asyncpg
- Migrations: Alembic

Purpose:

- PostgreSQL stores durable truth: keys, owners, institutions, cohorts, quotas, reservations, usage ledger, audit logs, pricing, routing rules, provider metadata, admin users, sessions, and email delivery records.
- SQLAlchemy is the Python-to-SQL layer.
- asyncpg is the async PostgreSQL driver underneath SQLAlchemy.
- Alembic provides reproducible schema migrations.

### 2.3 Cache, rate limits, and jobs

- Redis 7+
- Celery
- Celery Beat for scheduled jobs

Purpose:

- Redis stores fast temporary operational state: rate-limit counters, short-lived locks, Celery broker messages, optional cached key lookups, and transient coordination data.
- Celery performs slow/background work outside the live API request path: sending emails, CSV exports, cleanup jobs, provider health checks, and bulk imports.
- Celery Beat runs scheduled jobs.

Important: PostgreSQL remains the source of truth. Redis must not be the only place where hard quota accounting is stored.

### 2.4 API framework

- FastAPI
- Starlette `StreamingResponse` for streaming/SSE
- Uvicorn for local development
- Gunicorn with Uvicorn workers for production app serving

Purpose:

- FastAPI defines HTTP routes, dependency injection, request handling, auth, and admin routes.
- Starlette provides low-level async streaming primitives.
- Uvicorn is the ASGI server.
- Gunicorn manages multiple Uvicorn worker processes in production.

### 2.5 Provider forwarding

- `httpx.AsyncClient`

Purpose:

- Forward requests asynchronously to OpenAI, OpenRouter, and future provider adapters.
- Support both non-streaming and streaming responses.
- Preserve response semantics carefully.

### 2.6 Admin dashboard

- FastAPI routes under `/admin`
- Jinja2 templates
- HTMX for lightweight interactivity
- Locally compiled Tailwind CSS

Purpose:

- Server-rendered admin dashboard without a React/Vue SPA.
- Admins can create/revoke/suspend/activate/extend/rotate keys, view owners, institutions, cohorts, usage, pricing, routing, audit logs, and email delivery state.
- HTMX can update page fragments without a heavy frontend stack.
- Tailwind must be compiled locally for production; do not use CDN Tailwind in production.
- HTMX must be vendored or installed locally for production pages; do not depend on a public CDN in production.

### 2.7 CLI

- Typer

Purpose:

- Provide terminal administration commands using the same service-layer functions as the dashboard.
- Must support first admin creation, key creation, bulk import, revoke/suspend/activate, limit updates, usage reset, usage export, pricing import, routing changes, email tests, and DB maintenance.

### 2.8 Email

- SMTP via `aiosmtplib`
- Email sending initiated through Celery worker tasks
- Mailpit for local development/testing

Purpose:

- Send newly generated or rotated keys to users.
- Do not block admin HTTP requests while sending email.
- In development, use Mailpit so real email is not sent accidentally.

Implementation note:

- Celery tasks are synchronous by default. If using `aiosmtplib` inside Celery, wrap async email calls safely with `asyncio.run(...)` or a clearly defined async task helper. Do not leave un-awaited coroutines in Celery tasks.

### 2.9 Security

- Gateway key storage: HMAC-SHA-256 with server pepper/key versioning
- Temporary recoverable secrets: encrypted with AES-256-GCM or equivalent authenticated encryption
- Admin passwords: Argon2id
- CSRF protection for admin state-changing forms
- Immutable/effectively append-only audit log
- No plaintext gateway keys stored after creation/rotation flow
- No secrets in logs
- Upstream provider keys supplied through environment variables or Docker secrets by default

Purpose:

- If the database leaks, issued gateway keys should not be usable.
- If logs leak, keys and provider secrets should not appear.
- Admin actions must be accountable and protected from browser-based cross-site request forgery.

### 2.10 Observability

- Structured logs: structlog
- Metrics: Prometheus metrics endpoint
- Tracing: OpenTelemetry optional / phase 2

Purpose:

- Every proxied request should have a gateway request ID.
- Logs should be structured and redact secrets.
- Metrics should track request volume, errors, quota rejections, provider latency, token use, and cost.
- OpenTelemetry is useful but may be implemented after the core gateway is stable.

### 2.11 Tests

- pytest
- pytest-asyncio
- respx for mocking outgoing `httpx` calls
- testcontainers for real PostgreSQL/Redis integration tests
- Hypothesis optional but recommended for quota/accounting property tests
- Playwright optional but recommended for admin dashboard browser tests

Do not require real OpenAI/OpenRouter keys for the normal test suite.

Real upstream smoke tests are allowed only under a clearly disabled-by-default test group, for example:

```bash
RUN_UPSTREAM_TESTS=1 OPENAI_UPSTREAM_API_KEY=sk-... OPENROUTER_API_KEY=sk-or-... pytest tests/upstream_optional/
```
Database integration tests have these allowed modes:

1. `TEST_DATABASE_URL`, when the maintainer or local environment provides an existing test database.
2. A safe disposable local PostgreSQL database created through the narrow postgres sudo commands, when available.
3. A user-owned temporary PostgreSQL instance for local/Codex verification, when it can be started without destructive setup against `DATABASE_URL`.
4. Testcontainers, when Docker is available and appropriate.
5. The explicit apt/sudo Codex PostgreSQL install harness, only when the prompt specifically requests package installation and sudo works non-interactively for the required package/service commands.

Unit tests must remain independent of all database integration modes.

### 2.12 Deployment

- Dockerfile
- Docker Compose
- Services: API, worker, scheduler, Postgres, Redis
- Preferred reverse proxy: Nginx
- Caddy may be documented only as an optional alternative

Use Nginx as the preferred reverse proxy for public HTTPS deployment.

Nginx is not primarily a capacity requirement; it is for HTTPS, port 443, request limits, clean `/v1` and `/admin` exposure, access logs, and correct streaming proxy behavior.

For streaming, Nginx config must include anti-buffering/timeouts, such as:

```nginx
proxy_buffering off;
proxy_cache off;
proxy_read_timeout 3600s;
proxy_send_timeout 3600s;
```

---

## 3. High-level architecture

```text
OpenAI SDK / curl / compatible client
        ↓
https://api.ulfe.slaif.si/v1
        ↓
Nginx, optional in dev but preferred in public production
        ↓
FastAPI gateway
        ↓
Authentication + policy + quota reservation
        ↓
Provider router
        ↓
OpenAI adapter / OpenRouter adapter / future adapters
        ↓
Provider response streamed or returned
        ↓
Usage ledger + cost accounting + audit/metrics
```

### 3.1 Main runtime services

```text
api        FastAPI/Gunicorn/Uvicorn app serving /v1 and /admin
worker     Celery worker for background tasks
scheduler  Celery Beat for scheduled jobs
postgres   PostgreSQL source of truth
redis      Redis for rate limits, Celery broker, locks/cache
mailpit    development-only fake SMTP/mailbox service
nginx      optional container or host-level reverse proxy for production HTTPS
```

---

## 4. Core system components

### 4.1 OpenAI-compatible ingress

Expose OpenAI-compatible endpoints under `/v1`.

Minimum initial endpoints:

- `GET /v1/models`
- `POST /v1/chat/completions`
- `POST /v1/embeddings` if enabled in routing/pricing
- `POST /v1/responses` may be implemented later, but document support level carefully

Rules:

- Preserve OpenAI-style request/response structure.
- Preserve streaming behavior for supported streaming endpoints.
- Return OpenAI-shaped errors.
- Do not require custom headers from clients.
- Do not require custom environment variables from clients.
- The client-provided `Authorization: Bearer ...` token is a gateway-issued token, not the upstream provider token.
- Unsupported large file/image/audio endpoints are out of scope unless explicitly implemented, priced, routed, and tested.

### 4.2 Gateway key service

Generate OpenAI-looking gateway keys for compatibility.

Recommended/default key format:

```text
<GATEWAY_KEY_PREFIX><public_key_id>.<secret>
```

Default:

```
sk-slaif-<public_key_id>.<secret>
```

Configuration:

```
GATEWAY_KEY_PREFIX=sk-slaif-
GATEWAY_KEY_ACCEPTED_PREFIXES=sk-slaif-
```

Rules:

*   `GATEWAY_KEY_PREFIX` controls the prefix used for newly generated keys.
*   `GATEWAY_KEY_ACCEPTED_PREFIXES` controls prefixes accepted during parsing/authentication.
*   `GATEWAY_KEY_ACCEPTED_PREFIXES` must include `GATEWAY_KEY_PREFIX`.
*   Prefixes should start with `sk-` for OpenAI-tool compatibility.
*   Prefixes must end with `-`.
*   Prefixes must not contain `.`, whitespace, `/`, `\`, quotes, or control characters.
*   Prefixes should use lowercase ASCII letters, digits, and hyphens only.
*   Parsing must use the configured accepted prefixes, not a hardcoded `sk-slaif-`.
*   If an old deployment used `sk-ulfe-`, it may be accepted by setting:  
    `GATEWAY_KEY_ACCEPTED_PREFIXES=sk-slaif-,sk-ulfe-`.

Where:

- `sk-` prefix improves compatibility with tools that expect OpenAI-like keys.
- `slaif` identifies the gateway issuer.
- `public_key_id` is non-secret and can be stored for fast lookup.
- `secret` is high-entropy random material generated from a CSPRNG.

Generation rules:

- Use at least 32 bytes of random entropy for the secret component.
- Show/email the plaintext key only at creation or rotation time.
- Never store the plaintext key in PostgreSQL.
- Never log the plaintext key.
- Never display the full key in the dashboard after creation/rotation.
- If a key is lost, rotate it; do not resend an old key.

Storage rules:

```text
stored_hash = HMAC_SHA256(TOKEN_HMAC_SECRET_V<version>, full_plaintext_gateway_key)
```

- `TOKEN_HMAC_SECRET_V<version>` is the server pepper and must be stored outside the database.
- `ACTIVE_HMAC_KEY_VERSION` identifies which secret version is used for newly generated keys.
- The gateway-key database record must store the HMAC secret version as defined in docs/database-schema.md.
- Compare hashes using constant-time comparison.
- Store only safe display material such as public ID, prefix, and a short hint if needed.

HMAC secret rotation policy:

- v1 must support at least one active HMAC secret version.
- If multiple versions are configured, validation must use the version recorded on the key row.
- New keys use `ACTIVE_HMAC_KEY_VERSION`.
- If the operator removes an old HMAC secret version, keys created with that version become invalid. This must be documented.

Key status behavior:

- Store only the non-expiration lifecycle states defined in docs/database-schema.md.
- Do not store `expired` as a key status.
- Expiration is derived from the validity window.
- The dashboard may show a computed display state of `expired`.

Required key owner/profile behavior:

- Keys must be associated with enough owner, institution, and optional cohort
  metadata to support administration, reporting, and auditability.
- Key validity, lifecycle status, quota limits, usage counters, endpoint/model
  policies, and audit metadata must follow `docs/database-schema.md`.
- AGENTS.md must not define alternate key columns or table names.

Required key management operations:

- create key
- bulk-create keys
- email newly created key to owner
- revoke key permanently
- suspend key temporarily
- activate key
- extend validity
- shorten validity
- set/update cost limit
- set/update token limit
- reset usage counters manually
- rotate key and email replacement
- list keys
- filter by institution/cohort/status
- export key metadata without plaintext secrets

### 4.3 Authentication and policy layer

For every `/v1` request:

1. Extract `Authorization: Bearer <gateway_key>`.
2. Parse public key ID if present.
3. Look up candidate key row.
4. Compute HMAC using the key's `hmac_key_version`.
5. Compare stored hash using constant-time comparison.
6. Verify stored status is `active`.
7. Verify current time is within validity window.
8. Verify requested endpoint is allowed.
9. Verify requested model is allowed.
10. Resolve route/provider.
11. Verify provider is allowed.
12. Verify rate limit.
13. Apply gateway token/output/input caps.
14. Estimate maximum possible token/cost consumption.
15. Atomically reserve quota before forwarding.
16. Forward request to selected provider with upstream provider secret.
17. Finalize accounting after response or mark reservation released/expired on error.

Failure must return an OpenAI-style error.

### 4.4 Gateway token and output caps

Hard quotas require a bounded maximum output size.

The gateway must enforce global defaults in configuration and may later support persisted per-key/per-route overrides if `docs/database-schema.md` is updated first.

Required v1 configuration:

```env
DEFAULT_MAX_OUTPUT_TOKENS=1024
HARD_MAX_OUTPUT_TOKENS=4096
HARD_MAX_INPUT_TOKENS=128000
```

Rules:

- If the client omits output-token controls (`max_tokens`, `max_completion_tokens`, or `max_output_tokens`, depending on endpoint), the gateway must inject a safe configured default before forwarding.
- If the client requests more than the configured hard limit, reject with an OpenAI-shaped error. Do not silently clamp unless explicitly documented later.
- If the request body exceeds the configured input-token limit, reject before forwarding.
- Quota reservation must be based on the effective request after gateway policy is applied.
- Endpoint-specific names must be handled carefully: Chat Completions may use `max_tokens` or `max_completion_tokens`; Responses may use `max_output_tokens`.

### 4.5 Provider router

The router decides which upstream provider receives a request.

Routing must be data-driven using the routing schema defined in docs/database-schema.md, not hardcoded only in Python.

Initial route seed examples:

```text
gpt-*                 -> OpenAI
text-embedding-*      -> OpenAI
o1-*                  -> OpenAI, if enabled and priced
o3-*                  -> OpenAI, if enabled and priced
o4-*                  -> OpenAI, if enabled and priced
openai/*              -> OpenRouter
anthropic/*           -> OpenRouter
google/*              -> OpenRouter
meta-llama/*          -> OpenRouter
mistralai/*           -> OpenRouter
qwen/*                -> OpenRouter
admin aliases         -> explicit route table entries
```

Do not use a broad `o* -> OpenAI` rule. It is too broad and may match unintended provider/model names.

Provider namespace routes such as `anthropic/*`, `openai/*`, `google/*`, and `meta-llama/*` must be evaluated before broad prefixes like `gpt-*`.

Examples:

```text
model="gpt-4.1-mini"                 -> OpenAI adapter
model="openai/gpt-4.1-mini"          -> OpenRouter adapter
model="anthropic/claude-..."         -> OpenRouter adapter
model="classroom-cheap"              -> alias resolved by routing table
```

The gateway must support:

- exact model routes
- prefix routes
- glob routes
- aliases
- priority ordering
- provider enable/disable flags
- per-key or per-cohort allowed model policies
- `/v1/models` returning only models visible to the caller

### 4.6 Provider adapters

Implement provider-specific forwarding behind a common interface.

Required adapters:

- OpenAI adapter
- OpenRouter adapter

Adapter responsibilities:

- know upstream base URL
- know required provider API key environment variable
- inject provider authentication
- use an explicit outbound header allowlist
- forward request body after gateway policy modifications
- preserve streaming response format
- parse usage
- parse provider request IDs where available
- normalize errors only when needed to preserve OpenAI-style client behavior

Header rules:

- Never forward the client `Authorization` header upstream.
- Never forward `Cookie`, `Set-Cookie`, CSRF headers, admin session headers, or internal gateway headers upstream.
- The adapter must replace authentication with the provider API key.
- Use provider-specific outbound header allowlists. Safe examples may include `Content-Type`, selected tracing/request ID headers, and provider-supported metadata headers.
- OpenRouter-specific headers, if used, must be configured intentionally and must not leak secrets.

Provider secrets:

```env
OPENAI_UPSTREAM_API_KEY=sk-...
OPENROUTER_API_KEY=sk-or-...
```

Do not name the upstream OpenAI key `OPENAI_API_KEY` in the server environment, because that name is semantically used by clients. Prefer `OPENAI_UPSTREAM_API_KEY` for the gateway's real provider key.

### 4.7 Pricing and model catalog

Use an explicit local pricing/model catalog backed by the pricing schema defined in docs/database-schema.md.

Required concepts:

- provider
- model name
- endpoint type
- native/source currency
- input token price
- cached input token price
- output token price
- reasoning token price if applicable
- image/audio/file/tool pricing if supported
- effective date
- status enabled/disabled
- pricing source/note
- created/updated by admin

Rules:

- Unknown model pricing must fail closed unless an admin explicitly marks the model as allowed with pricing policy and documents the exception.
- OpenAI-routed request cost is calculated locally from provider usage and pricing table.
- OpenRouter-routed request cost may use provider-returned cost when available, but still record token usage and model metadata.
- If OpenRouter provides cost and the local catalog also has cost, record both if useful: provider-reported cost and gateway-calculated cost.
- User-facing cost limits are in EUR.
- If upstream pricing or provider-returned cost is in USD or another currency, convert to EUR using configured FX data before reservation and finalization.
- Unknown FX conversion must fail closed for cost-limited keys.

### 4.8 Token and cost accounting

Per-key accounting is mandatory.

Token accounting is based on provider-returned usage fields whenever possible:

- prompt/input tokens
- completion/output tokens
- total tokens
- cached input tokens
- reasoning tokens, if present
- audio/image/tool/file tokens, if present

Cost accounting modes:

1. OpenRouter requests: prefer provider-returned cost if available; also store detailed token usage.
2. OpenAI requests: compute cost from local pricing table and provider usage.

Hard quota enforcement must use a reserve-then-finalize model.

Before request:

```text
apply gateway token/output/input caps
estimate maximum possible tokens/cost
atomically reserve estimated amount
reject if reservation would exceed key limits
```

After successful response:

```text
read actual usage
calculate/accept actual cost
replace reservation with final charge
append/finalize usage ledger row
update key counters
```

After failed request:

```text
release or adjust reservation according to whether provider charged usage
record failure in usage ledger if useful
```

Concurrency requirements:

- Use PostgreSQL transactions and row-level locking or atomic conditional updates for authoritative quota updates.
- Do not allow two simultaneous requests to overspend the same key.
- Redis can assist with rate limiting and short-lived locks, but PostgreSQL must remain the source of truth for quota state and ledger records.

Streaming requirements:

- For streaming requests, attempt to obtain final usage from the provider's final stream event/chunk.
- If a stream is interrupted before final usage arrives, record an incomplete/interrupted accounting event and handle according to policy.
- The gateway may inject provider-specific options needed to request streaming usage, if that does not break client compatibility.
- Never silently ignore usage failures for cost-bearing requests. Mark them clearly in the ledger.

Quota period semantics for v1:

- In v1, key limits are lifetime limits over the key validity period.
- Admins may manually reset usage counters with an audited action.
- Automatic monthly/rolling quota periods are out of scope unless `docs/database-schema.md` is updated to define period fields and reset behavior.

### 4.9 Usage ledger

The usage ledger should be append-oriented and auditable.

The exact usage-ledger schema is defined only in docs/database-schema.md. Do not
duplicate its column list in AGENTS.md.

Behavioral requirements:

- Record one accounting event per proxied request or attempted proxied request,
  according to docs/database-schema.md.
- Preserve enough metadata for reporting by key, owner, institution, cohort,
  endpoint, provider, model, status, tokens, cost, and accounting state.
- Preserve historical reporting even if owner/institution/cohort metadata changes later.
- Record failed, interrupted, estimated, and finalized accounting states clearly.
- Do not silently ignore usage/accounting failures for cost-bearing requests.
- Do not store full prompts, completions, uploaded files, or tool payloads by default.
- If content logging is added later, it must be explicit, opt-in, time-limited,
  access-controlled, and documented.

### 4.10 Admin dashboard

Expose dashboard routes under `/admin`.

Required pages/features:

- login/logout
- dashboard summary
- keys list with filters
- key detail page
- create key form
- bulk key creation/import
- rotate key
- revoke/suspend/activate key
- extend validity
- update limits
- reset usage limits manually
- email newly generated key
- email replacement key after rotation
- institutions/cohorts/workshops management
- usage explorer
- usage by key/user/institution/cohort/model/provider
- pricing table management
- routing table management
- provider health/status page
- email delivery history
- audit log
- CSV export controls

Security requirements:

- Secure admin session cookies
- CSRF token on every state-changing form/action
- Argon2id password hashes
- Rate limit admin login attempts
- Never display full plaintext gateway keys after initial creation/rotation screen
- Never display upstream provider keys
- Redact secrets in templates and logs
- For production, protect `/admin` with strong passwords, HTTPS, login rate limiting, and preferably IP allowlisting, VPN, or Nginx access control. MFA is recommended for a future version.

### 4.11 CLI

Implement Typer CLI as `slaif-gateway`.

Required commands should include at least:

```bash
slaif-gateway admin create
slaif-gateway admin reset-password

slaif-gateway keys create
slaif-gateway keys bulk-create
slaif-gateway keys list
slaif-gateway keys revoke
slaif-gateway keys suspend
slaif-gateway keys activate
slaif-gateway keys extend
slaif-gateway keys set-limits
slaif-gateway keys reset-usage
slaif-gateway keys rotate
slaif-gateway keys rotate-and-email

slaif-gateway usage export
slaif-gateway usage summarize

slaif-gateway pricing import
slaif-gateway pricing list
slaif-gateway pricing disable-model

slaif-gateway routes add
slaif-gateway routes list
slaif-gateway routes disable

slaif-gateway email test
slaif-gateway email send-pending-key

slaif-gateway db upgrade
slaif-gateway db current
slaif-gateway db check
```

Important email command rule:

- Do not implement a command that resends an old plaintext key.
- `email send-pending-key` may only send a newly generated/rotated key through a valid unconsumed `one_time_secrets` row.
- If the user lost an existing key, rotate it and send the replacement.

The CLI and dashboard must call the same service-layer functions. Do not duplicate business logic in route handlers and CLI command handlers.

### 4.12 Email delivery

Use SMTP through `aiosmtplib`, called from Celery tasks.

Email contents for user keys must include:

- user's name
- institution/cohort/workshop if relevant
- validity period
- token/cost limits
- API key shown once
- base URL
- standard OpenAI-compatible environment variable instructions

Example user instructions in email:

```bash
export OPENAI_API_KEY="sk-slaif-..."
export OPENAI_BASE_URL="https://api.ulfe.slaif.si/v1"
```

And:

```python
from openai import OpenAI

client = OpenAI()
```

Rules:

- Plaintext gateway key may exist only transiently at creation/rotation time.
- Celery jobs must not carry plaintext gateway keys in Redis payloads.
- Asynchronous email delivery must use `one_time_secrets`.
- `one_time_secrets` must store encrypted temporary secret material, not plaintext.
- Use AES-256-GCM or equivalent authenticated encryption.
- The master encryption key must be supplied outside PostgreSQL, for example through `ONE_TIME_SECRET_ENCRYPTION_KEY` as an environment variable or Docker secret.
- Rows must have short expiry and single-use semantics.
- After successful email delivery, mark the secret consumed and delete it or render it unusable after a retention window.
- Store email delivery metadata but not the full key.
- If delivery fails after the secret expires or is consumed, admin must rotate and send a replacement key.

### 4.13 Audit logging

Every sensitive action must create an audit log row.

Examples:

- admin login success/failure
- admin password change
- key created
- key emailed
- key revoked/suspended/activated
- key validity changed
- limits changed
- usage reset
- pricing changed
- routing changed
- provider config changed
- export generated

Audit row fields should include:

- actor admin ID
- action
- target type
- target ID
- timestamp
- old values, redacted
- new values, redacted
- reason/note if provided
- request ID
- IP/user-agent if privacy policy permits

Audit logs should be append-only from the application perspective.

### 4.14 Observability

Structured logs:

- Use structlog.
- Every request must have a request ID.
- Include provider, model, route, status, latency, quota status.
- Redact `Authorization`, API keys, provider keys, cookies, passwords, CSRF tokens, session tokens, and email passwords.

Prometheus metrics:

- request count by endpoint/provider/model/status
- request latency
- upstream latency
- streaming request count
- quota rejection count
- auth failure count
- token usage totals
- cost totals
- active keys
- Celery job success/failure counts
- email delivery success/failure counts

Health endpoints:

- `/healthz`: process is alive
- `/readyz`: database configuration/reachability and schema readiness; Redis should not be required until Redis-backed behavior is implemented
- `/metrics`: Prometheus metrics

Production rule:

- `/metrics` must not be publicly exposed in production. Restrict it by Nginx allowlist, internal network, or admin authentication.

### 4.15 Reverse proxy

Nginx is the preferred reverse proxy.

Responsibilities:

- HTTPS termination
- serve public `api.ulfe.slaif.si`
- route `/v1` and `/admin` to FastAPI
- enforce request size limits
- set sensible timeouts
- preserve streaming by disabling proxy buffering
- provide access logs

Do not require Nginx for local development. Local development can run directly with Uvicorn/Gunicorn and Docker Compose.

---

## 5. Database schema source of truth

The only authoritative database schema for this project is documented in:

docs/database-schema.md

Codex must implement SQLAlchemy models, Alembic migrations, repository methods,
and schema-dependent tests from docs/database-schema.md.

AGENTS.md must not define a competing inline schema.

Do not add table lists, column lists, index definitions, CHECK constraint values,
enum/check-value lists, migration contents, or alternative table names to this
file. Those belong in docs/database-schema.md.

If AGENTS.md and docs/database-schema.md conflict on any database-specific detail,
Codex must follow docs/database-schema.md and report the conflict.

Allowed in AGENTS.md:

- architecture requirements
- security requirements
- testing requirements
- operational requirements
- high-level behavior, such as "do not store plaintext gateway keys"
- references to docs/database-schema.md

Not allowed in AGENTS.md:

- duplicate schema definitions
- duplicate required table lists
- duplicate column definitions
- duplicate index/constraint definitions
- old/alternative table names
- schema shortcuts that simplify accounting, quota, audit, or secret handling

Schema change rule:

- Any schema change must first update docs/database-schema.md.
- SQLAlchemy models and Alembic migrations must then be implemented from that file.
- Tests must verify that the implementation matches docs/database-schema.md.
- Codex must not invent schema fields or remove schema fields without updating docs/database-schema.md and explaining the reason.

Important database policy requirements:

- PostgreSQL is the production source of truth.
- Redis is only for fast temporary state, locks, rate-limit counters, Celery broker data, and similar operational state.
- Gateway-issued API keys must never be stored in plaintext.
- One-time delivery secrets must never be stored in plaintext.
- Provider API keys must not be stored in PostgreSQL by default.
- Prompt, completion, uploaded-file, and tool payload contents must not be stored by default.
- Hard quota enforcement must use authoritative PostgreSQL state, not Redis-only state.
- Unknown model pricing and unknown FX conversion must fail closed for cost-limited keys.
- Anthropic-family models are supported only through OpenRouter's OpenAI-compatible interface unless a separate native Anthropic adapter is explicitly implemented with tests.

Implementation files:

- app/slaif_gateway/db/models.py
- app/slaif_gateway/db/session.py
- app/slaif_gateway/db/repositories/
- migrations/versions/

All schema changes require Alembic migrations and tests.

Enum/check strategy:

- Prefer text fields with CHECK constraints for status/match-type fields.
- Avoid PostgreSQL ENUM types unless the maintainer explicitly chooses them, because enum migrations are more cumbersome.

Migration strategy:

- Do not run Alembic migrations automatically inside every API/worker startup.
- Provide an explicit one-shot migration command/container, for example:

  docker compose run --rm api slaif-gateway db upgrade

- API and worker readiness should fail if the database schema is not current.
- Local development may run migrations as part of explicit setup scripts, but this must be visible and documented.

### 5.1 Documentation contract and implementation drift rules

The following files are implementation contracts. Codex must treat them as
current truth for the behavior they describe and keep them synchronized with
code changes:

- `docs/database-schema.md`
- `docs/openai-compatibility.md`
- `docs/provider-forwarding-contract.md`
- `docs/compatibility-matrix.md`
- `docs/accounting.md`, if present
- `docs/provider-routing.md`, if present
- `README.md`, for top-level current status, quickstart, and operator-facing
  truth

Documentation must be checked and updated in the same PR as the code change
whenever that change affects the documented behavior below. If Codex finds
that a required document is absent, it must either create it when that is in
scope or report the missing document and update the closest existing contract
document.

OpenAI-compatible API behavior changes require checking and, when needed,
updating `docs/openai-compatibility.md`, `docs/compatibility-matrix.md`, and
`README.md` if user-facing status changes. Examples include:

- adding, removing, or changing `/v1` endpoints
- changing request fields that are accepted, preserved, mutated, or rejected
- changing response shapes
- changing OpenAI-shaped error behavior
- changing streaming/SSE behavior
- changing unsupported endpoint behavior

Provider forwarding behavior changes require checking and, when needed,
updating `docs/provider-forwarding-contract.md`,
`docs/compatibility-matrix.md`, `docs/provider-routing.md` if present, and
`README.md` if user-facing behavior changes. Examples include:

- changing provider adapters
- changing upstream endpoint paths
- changing provider base URL behavior
- changing provider `api_key_env_var` behavior
- changing outbound header allowlists or blocklists
- changing client `Authorization` forwarding behavior
- changing upstream body mutation
- changing model substitution behavior
- changing OpenAI- or OpenRouter-specific behavior

Streaming and accounting behavior changes require checking and, when needed,
updating `docs/provider-forwarding-contract.md`,
`docs/openai-compatibility.md`, `docs/accounting.md` if present,
`docs/compatibility-matrix.md`, and `README.md` if user-facing behavior
changes. Examples include:

- changing `stream_options.include_usage` behavior
- changing missing-usage behavior
- changing provider-completed finalization-failure behavior
- changing client-disconnect behavior
- changing quota reservation, finalization, or release behavior
- changing reconciliation behavior
- changing usage-ledger semantics
- changing prompt/completion storage policy

Redis rate-limit behavior changes require checking and, when needed, updating
`docs/accounting.md` if present, `docs/provider-forwarding-contract.md` if
request-flow behavior changes, `docs/compatibility-matrix.md`, and `README.md`
if operator-facing behavior changes. Examples include:

- changing request, token, or concurrency limit semantics
- changing active-concurrency TTL, heartbeat, or release policy
- changing fail-open or fail-closed behavior
- changing readiness behavior when Redis is enabled
- changing whether Redis rate limiting is wired into endpoints

CLI secret-output and operator-behavior changes require checking and, when
needed, updating `README.md`, `docs/security-model.md` if present, and
`docs/compatibility-matrix.md` if it tracks the affected CLI/operator support.
Examples include:

- changing key create/rotate plaintext output behavior
- changing `--json` secret behavior
- changing `--secret-output-file` behavior
- changing repair or destructive confirmation requirements
- changing usage export content
- changing whether prompts, completions, or secrets appear in output

Schema changes remain governed by the `docs/database-schema.md` rule above:
the schema document must be updated first or in the same PR, models and
migrations must follow it, and AGENTS.md must not duplicate competing schema
detail.

Every Codex final report must include a documentation impact line for the PR:

- `Documentation updated: <files>`
- `Documentation checked, no update needed because <specific reason>`
- `Documentation intentionally deferred: <reason and follow-up task>`

For tasks that change public API, provider, accounting, Redis, security, or
operator behavior, "no update needed" must be justified specifically. It must
not be omitted or treated as implicit.

---

## 6. Repository structure

Use this structure unless there is a strong reason to adjust it.

```text
slaif-api-gateway/
├── AGENTS.md
├── README.md
├── LICENSE
├── SECURITY.md
├── CONTRIBUTING.md
├── CODE_OF_CONDUCT.md
├── CHANGELOG.md
├── pyproject.toml
├── uv.lock                         # if using uv; otherwise omit
├── .python-version
├── .gitignore
├── .dockerignore
├── .env.example
├── docker-compose.yml
├── docker-compose.dev.yml
├── Dockerfile
├── Makefile
├── alembic.ini
├── package.json                    # local Tailwind/HTMX asset tooling
├── tailwind.config.js
├── postcss.config.js
│
├── app/
│   └── slaif_gateway/
│       ├── __init__.py
│       ├── main.py                 # FastAPI app factory / entrypoint
│       ├── config.py               # environment/settings handling
│       ├── logging.py              # structlog setup
│       │
│       ├── api/
│       │   ├── __init__.py
│       │   ├── openai_compat.py    # /v1/chat/completions, /v1/models, etc.
│       │   ├── health.py           # /healthz, /readyz
│       │   ├── dependencies.py     # FastAPI auth/session dependencies
│       │   └── errors.py           # OpenAI-style error responses
│       │
│       ├── auth/
│       │   ├── __init__.py
│       │   └── ...                 # future auth-specific helpers as needed
│       │
│       ├── db/
│       │   ├── __init__.py
│       │   ├── base.py
│       │   ├── session.py
│       │   ├── models.py
│       │   └── repositories/
│       │       ├── __init__.py
│       │       ├── keys.py
│       │       ├── owners.py
│       │       ├── institutions.py
│       │       ├── cohorts.py
│       │       ├── usage.py
│       │       ├── quota.py
│       │       ├── provider_configs.py
│       │       ├── pricing.py
│       │       ├── routing.py
│       │       ├── fx_rates.py
│       │       ├── one_time_secrets.py
│       │       ├── email.py
│       │       └── audit.py
│       │
│       ├── services/
│       │   ├── __init__.py
│       │   ├── key_service.py      # create/revoke/extend/rotate/reset keys
│       │   ├── owner_service.py
│       │   ├── quota_service.py    # reserve/finalize quota
│       │   ├── accounting.py       # token/cost accounting
│       │   ├── pricing.py          # pricing lookup and cost calculation
│       │   ├── route_resolution.py # model -> provider decision
│       │   ├── model_catalog.py    # /v1/models metadata
│       │   ├── chat_completion_gateway.py
│       │   ├── provider_config_service.py
│       │   ├── model_route_service.py
│       │   ├── pricing_rule_service.py
│       │   ├── fx_rate_service.py
│       │   └── usage_report_service.py
│       │
│       ├── providers/
│       │   ├── __init__.py
│       │   ├── base.py             # provider adapter interface
│       │   ├── factory.py          # provider config -> adapter construction
│       │   ├── headers.py          # safe outbound header allowlists
│       │   ├── openai.py           # OpenAI upstream adapter
│       │   └── openrouter.py       # OpenRouter upstream adapter
│       │
│       ├── schemas/
│       │   ├── __init__.py
│       │   ├── openai.py           # request/response compatibility models
│       │   ├── admin.py
│       │   ├── keys.py
│       │   ├── owners.py
│       │   ├── usage.py
│       │   └── errors.py
│       │
│       ├── cli/
│       │   ├── __init__.py
│       │   ├── main.py             # Typer root
│       │   ├── admin.py
│       │   ├── cohorts.py
│       │   ├── common.py
│       │   ├── db.py
│       │   ├── fx.py
│       │   ├── institutions.py
│       │   ├── keys.py
│       │   ├── owners.py
│       │   ├── pricing.py
│       │   ├── providers.py
│       │   ├── routes.py
│       │   └── usage.py
│       │
│       ├── workers/
│       │   └── __init__.py         # Celery workers are future work
│       │
│       ├── web/
│       │   ├── templates/
│       │   │   └── .gitkeep        # dashboard templates are future work
│       │   └── static/
│       │       ├── css/.gitkeep
│       │       ├── img/.gitkeep
│       │       └── js/.gitkeep
│       │
│       └── utils/
│           ├── __init__.py
│           ├── crypto.py           # HMAC, random token generation, AES-GCM helpers
│           ├── time.py
│           ├── ids.py
│           └── redaction.py        # prevent secret leakage in logs
│
├── migrations/
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
│
├── tests/
│   ├── conftest.py
│   ├── unit/
│   │   ├── test_auth_service.py
│   │   ├── test_quota_service.py
│   │   ├── test_pricing_service.py
│   │   ├── test_route_resolution_service.py
│   │   ├── test_v1_chat_completions_forwarding.py
│   │   └── test_v1_error_shape.py
│   ├── integration/
│   │   ├── test_migrations_postgres.py
│   │   ├── test_repositories_foundation_postgres.py
│   │   ├── test_quota_reservation_postgres.py
│   │   ├── test_quota_reservation_concurrency_postgres.py
│   │   ├── test_cli_routing_pricing_postgres.py
│   │   ├── test_cli_usage_postgres.py
│   │   └── test_readyz_postgres.py
│   ├── e2e/
│   │   ├── test_openai_python_client_chat.py
│   │   └── test_openrouter_python_client_chat.py
│   └── upstream_optional/
│       ├── test_real_openai_smoke.py
│       └── test_real_openrouter_smoke.py
│
├── docs/
│   ├── architecture.md
│   ├── database-schema.md          # authoritative schema source
│   ├── deployment.md
│   ├── configuration.md
│   ├── security-model.md
│   ├── openai-compatibility.md
│   ├── provider-routing.md
│   ├── accounting.md
│   ├── admin-guide.md
│   ├── cli-reference.md
│   ├── development.md
│   └── compatibility-matrix.md
│
├── scripts/
│   ├── dev-reset.sh
│   ├── backup-postgres.sh
│   ├── restore-postgres.sh
│   ├── compile-tailwind.sh
│   ├── wait-for-services.sh
│   ├── codex-install-postgres.sh     # explicit Codex/local test harness only
│   ├── codex-start-postgres.sh       # explicit Codex/local test harness only
│   ├── create-test-db.sh             # creates isolated TEST_DATABASE_URL database
│   └── seed_test_data.py             # deterministic dummy data; no plaintext secrets
│
├── deploy/
│   ├── nginx/
│   │   └── slaif-api-gateway.conf
│   ├── systemd/
│   │   └── slaif-api-gateway.service
│   └── examples/
│       ├── docker-compose.production.yml
│       └── env.production.example
│
└── examples/
    ├── openai-python-client/
    │   ├── chat_completion.py
    │   ├── streaming_chat.py
    │   └── list_models.py
    ├── curl/
    │   ├── chat_completion.sh
    │   └── streaming_chat.sh
    └── workshop/
        ├── 01_basic_chat.py
        ├── 02_streaming.py
        └── 03_cost_awareness.py
```

### 6.1 Package layout and local execution

The Python package lives under `app/slaif_gateway/`.

Development may use either editable install:

```bash
pip install -e .
uvicorn slaif_gateway.main:app --reload
```

or app-dir invocation:

```bash
uvicorn --app-dir app slaif_gateway.main:app --reload
```

Docker builds must install the package or set the import path explicitly so `slaif_gateway` imports consistently.

---

## 7. Configuration

Use environment variables for configuration.

`.env.example` must include safe placeholders only.

Required configuration examples:

```env
APP_ENV=development
APP_BASE_URL=http://localhost:8000
PUBLIC_BASE_URL=http://localhost:8000/v1

DATABASE_URL=postgresql+asyncpg://slaif:slaif@postgres:5432/slaif_gateway
REDIS_URL=redis://redis:6379/0

ACTIVE_HMAC_KEY_VERSION=1
TOKEN_HMAC_SECRET_V1=change-me-generate-a-long-random-secret
ADMIN_SESSION_SECRET=change-me-generate-a-long-random-secret
ONE_TIME_SECRET_ENCRYPTION_KEY=change-me-32-byte-base64-key

OPENAI_UPSTREAM_API_KEY=
OPENROUTER_API_KEY=

SMTP_HOST=mailpit
SMTP_PORT=1025
SMTP_USERNAME=
SMTP_PASSWORD=
SMTP_FROM=no-reply@example.org

DEFAULT_KEY_COST_LIMIT_EUR=5.00
DEFAULT_KEY_TOKEN_LIMIT=1000000
DEFAULT_KEY_VALID_DAYS=30

DEFAULT_MAX_OUTPUT_TOKENS=1024
HARD_MAX_OUTPUT_TOKENS=4096
HARD_MAX_INPUT_TOKENS=128000

ENABLE_OPENAI_PROVIDER=true
ENABLE_OPENROUTER_PROVIDER=true
ENABLE_ADMIN_DASHBOARD=true
ENABLE_METRICS=true

GATEWAY_KEY_PREFIX=sk-slaif-
GATEWAY_KEY_ACCEPTED_PREFIXES=sk-slaif-
```

Rules:

- Never commit real secrets.
- Never store real provider keys in source code.
- Prefer Docker secrets or environment variables for production provider keys.
- If runtime-editable provider keys are later required, store them encrypted with AES-256-GCM using a master encryption key supplied outside PostgreSQL.
- If `APP_ENV=production`, application startup must fail if required secrets are missing or still equal to known placeholder/default values.
- If `APP_ENV=production`, application startup must fail if `OPENAI_API_KEY` is used as the upstream OpenAI provider secret. Use `OPENAI_UPSTREAM_API_KEY` instead.

---

## 8. Open-source documentation requirements

The repository must include:

- `README.md`
- `LICENSE`
- `SECURITY.md`
- `CONTRIBUTING.md`
- `CODE_OF_CONDUCT.md`, optional but recommended
- `.env.example`
- `docs/database-schema.md`
- `docs/deployment.md`
- `docs/configuration.md`
- `docs/security-model.md`
- `docs/openai-compatibility.md`
- `docs/accounting.md`
- `docs/provider-routing.md`
- `docs/compatibility-matrix.md`

README first page should explain:

- what the gateway does
- OpenAI-compatible usage
- quick start with Docker Compose
- how to run migrations
- how to create first admin
- how to issue first gateway key
- how to call it with the OpenAI Python client
- development and test basics

Example README client snippet:

```bash
export OPENAI_API_KEY="sk-slaif-..."
export OPENAI_BASE_URL="http://localhost:8000/v1"
```

```python
from openai import OpenAI

client = OpenAI()
response = client.chat.completions.create(
    model="gpt-4.1-mini",
    messages=[{"role": "user", "content": "Hello"}],
)
print(response.choices[0].message.content)
```

---

## 9. Testing strategy

Normal tests must not use real upstream APIs.

### 9.1 Unit tests

Use for:

- key generation
- HMAC hashing and versioning
- constant-time validation behavior
- AES-GCM one-time secret encryption/decryption
- pricing calculations
- FX conversion
- route matching and priority ordering
- quota estimation
- gateway output-token cap policy
- OpenAI error formatting
- redaction

### 9.2 Integration tests

Default integration-test strategy:

- Unit tests must not require PostgreSQL, Redis, Docker, or real upstream provider keys.
- Normal integration tests may use `TEST_DATABASE_URL` when explicitly provided.
- Local/Codex verification may create a safe disposable PostgreSQL database through narrow postgres sudo commands when available.
- Local/Codex verification may use a user-owned temporary PostgreSQL instance when available.
- Normal integration tests may use Testcontainers when Docker is available and appropriate.
- If no allowed PostgreSQL setup mode is available, database integration tests must skip cleanly.
- Integration tests must never use DATABASE_URL for destructive setup by default.
- Destructive test setup, migration resets, and seed scripts must target `TEST_DATABASE_URL` only.
- Do not stop merely because `sudo -n true` fails; test the specific allowed postgres commands and the non-sudo allowed modes before reporting a PostgreSQL blocker.

### 9.2.1 PostgreSQL-backed integration verification requirement

Codex must run relevant PostgreSQL-backed integration tests before opening a PR
when either condition is true:

- the task adds or modifies PostgreSQL integration-test coverage
- the prompt explicitly requests database verification

Codex must not report PostgreSQL-backed tests as "passed" when they skipped
because `TEST_DATABASE_URL` was missing or PostgreSQL was unavailable. If DB
tests skip, Codex must report them as "skipped" and explain the exact reason.

Skipping PostgreSQL-backed tests is acceptable only when:

- the prompt did not request DB verification and the task does not add or modify
  integration tests; or
- Codex made explicit, documented attempts to obtain a safe `TEST_DATABASE_URL`
  through every allowed setup method below and all methods failed.

When PostgreSQL-backed verification is needed, Codex must try setup methods in
this order:

1. If `TEST_DATABASE_URL` is already set, use it.
2. Else, if a safe disposable local PostgreSQL database can be created with the
   narrow sudo-enabled postgres commands, create one and export
   `TEST_DATABASE_URL`.
3. Else, if user-owned PostgreSQL binaries are available, start a user-owned
   temporary PostgreSQL instance and export `TEST_DATABASE_URL`.
4. Else, if Docker/Testcontainers is available and appropriate for the tests,
   use Testcontainers.
5. Else, skip cleanly and report the exact blockers.

The narrow sudo-enabled local PostgreSQL path is not the apt/sudo installation
harness. It uses only explicitly allowed postgres commands. Codex must not use
`sudo -n true` as a hard prerequisite, because sudoers may allow only specific
commands. Prefer checking the actual commands needed, for example:

```bash
sudo -n -u postgres /usr/bin/psql -d postgres -Atc "select current_user"
sudo -n -u postgres /usr/bin/createuser --help >/dev/null
sudo -n -u postgres /usr/bin/createdb --help >/dev/null
sudo -n -u postgres /usr/bin/dropdb --help >/dev/null
```

For disposable local database verification, use `TEST_DATABASE_URL` only:

```bash
sudo -n -u postgres /usr/bin/createuser ubuntu --createdb || true
sudo -n -u postgres /usr/bin/dropdb --if-exists slaif_gateway_test_codex
sudo -n -u postgres /usr/bin/createdb -O ubuntu slaif_gateway_test_codex
export TEST_DATABASE_URL="postgresql+asyncpg:///slaif_gateway_test_codex?host=/var/run/postgresql"
```

After the requested tests finish, remove the disposable database:

```bash
sudo -n -u postgres /usr/bin/dropdb --if-exists slaif_gateway_test_codex
```

Codex must never use `DATABASE_URL` for destructive test setup, schema reset,
seed data, or disposable integration testing.

Integration tests should cover:

- Alembic migrations
- repositories
- quota reservation transactions
- concurrent quota reservation races
- Redis rate limiting once Redis/rate-limit behavior is implemented
- Celery task integration once Celery workers are implemented
- one-time secret lifecycle
- seeded demo/test data workflows

### 9.2.2 Explicit Codex container PostgreSQL test harness

This is not the default test strategy.

Codex may install and start PostgreSQL inside its task container only when the
maintainer prompt explicitly requests this level of testing.

Trigger phrases include:

```text
Use the Codex container PostgreSQL test harness.
Run the local PostgreSQL install test harness.
Install PostgreSQL in the Codex container and run DB integration tests.
```

If the prompt does not explicitly request this, Codex must not run apt-based  
PostgreSQL installation.

This apt/sudo harness is separate from the narrow sudo-enabled local PostgreSQL
path and from the user-owned local PostgreSQL fallback.
Failure of `sudo -n true` is not by itself a reason to skip PostgreSQL coverage
when `TEST_DATABASE_URL`, the narrow sudo-enabled postgres commands,
Testcontainers, or an already-running local PostgreSQL instance is available.

When explicitly requested, Codex may:

```
sudo apt update
sudo apt install -y postgresql postgresql-contrib postgresql-client
```

Because Codex runs in a container, systemd may not be available. The harness  
must start PostgreSQL without assuming systemd. Acceptable approaches include:

```
sudo service postgresql start
```

or, if service startup is unavailable:

```
pg_lsclusters
sudo pg_ctlcluster <detected-version> main start
```

The harness must then create an isolated test role and database, for example:

```
sudo -u postgres psql -c "CREATE USER slaif WITH PASSWORD 'slaif';" || true
sudo -u postgres psql -c "ALTER USER slaif CREATEDB;"
sudo -u postgres createdb -O slaif slaif_gateway_test || true
```

The harness must use TEST\_DATABASE\_URL, not DATABASE\_URL:

```
export TEST_DATABASE_URL="postgresql+asyncpg://slaif:slaif@localhost:5432/slaif_gateway_test"
```

Then it should run:

```
alembic upgrade head
python scripts/seed_test_data.py
python -m pytest tests/integration
```

Safety rules for the Codex PostgreSQL harness:

*   It is for Codex/local development testing only.
*   It is not required for normal unit tests.
*   It is not required for open-source users by default.
*   It must never target production databases.
*   It must never run destructive setup against DATABASE\_URL.
*   It must use TEST\_DATABASE\_URL only.
*   It must refuse to run if APP\_ENV=production.
*   It must refuse to seed real provider API keys.
*   It must not store plaintext gateway keys.
*   It must not store plaintext one-time secrets.
*   Seeded gateway keys must either:
    *   be generated through the same safe service path and printed once for developer use, or
    *   use fake non-usable HMAC digests clearly marked as test/demo data.

### 9.2.3 Seed data script requirements

The repository must include a deterministic seed script:

```text
scripts/seed_test_data.py
```

Purpose:

*   populate a migrated test database with safe dummy data
*   support integration testing
*   support local/Codex development
*   avoid hand-written ad hoc SQL in prompts

The seed script must use TEST\_DATABASE\_URL, not DATABASE\_URL.

The seed script must refuse to run if:

*   TEST\_DATABASE\_URL is missing
*   APP\_ENV=production
*   the target database name does not look like a test/development database

Seed data should include representative dummy rows for:

*   institutions
*   cohorts
*   owners
*   admin users
*   gateway-key metadata
*   provider metadata
*   model routes
*   pricing rules
*   FX rates
*   quota/accounting examples where useful
*   email delivery examples where useful

Seed data must not include:

*   real provider API keys
*   plaintext gateway keys stored in the database
*   plaintext one-time secrets stored in the database
*   real personal data
*   real emails, except reserved/example domains such as example.org

If the seed script creates usable gateway keys for testing, it must use the same  
safe key-generation path as the application and print the plaintext key once to  
stdout. The database must still store only the HMAC digest and safe metadata.

If the seed script creates non-usable demo key rows, they must be clearly marked  
as non-usable and must not be represented as real issued credentials.

### 9.3 Provider mock tests

Use respx to intercept `httpx.AsyncClient` calls.

Test:

- OpenAI non-streaming forwarding
- OpenRouter non-streaming forwarding
- provider errors
- outbound header allowlist behavior
- usage parsing
- cost accounting

Streaming provider tests should be added only when streaming support is implemented.

### 9.4 E2E tests

Use the official OpenAI Python client against the local gateway.

The e2e test must configure only:

```bash
OPENAI_API_KEY=<gateway-issued-test-key>
OPENAI_BASE_URL=http://localhost:8000/v1
```

And then use:

```python
from openai import OpenAI
client = OpenAI()
```

### 9.5 Optional upstream tests

Real provider tests must be disabled by default and clearly marked.

They may be enabled manually only with explicit environment variables.

---

## 10. Development and deployment workflows

### 10.1 Local development

```bash
git clone https://github.com/<org>/slaif-api-gateway.git
cd slaif-api-gateway
cp .env.example .env
docker compose up --build
```

Run migrations explicitly:

```bash
docker compose run --rm api slaif-gateway db upgrade
```

### 10.2 Local server without reverse proxy

For development, it is acceptable to run:

```bash
uvicorn --app-dir app slaif_gateway.main:app --reload
```

or:

```bash
pip install -e .
uvicorn slaif_gateway.main:app --reload
```

or through Docker Compose.

### 10.3 Production-style local/server deployment

Use Docker Compose with services:

- api
- worker
- scheduler
- postgres
- redis
- optional nginx

For public HTTPS, use Nginx in front of the API.

Migrations should be run as a one-shot command before starting or restarting the application stack.

### 10.4 Building locally and distributing

If not using a registry, a built image can be distributed as a tarball:

```bash
docker build -t slaif-api-gateway:1.0.0 .
docker save slaif-api-gateway:1.0.0 | gzip > slaif-api-gateway-1.0.0.tar.gz
scp slaif-api-gateway-1.0.0.tar.gz server:/opt/slaif-api-gateway/
```

On the server:

```bash
gunzip -c slaif-api-gateway-1.0.0.tar.gz | docker load
docker compose up -d
```

Open-source users may simply clone and build locally.

Do not add CI/CD-specific requirements unless requested later.

## 10.5 Codex CLI Git and pull-request workflow

This project uses pull requests only. Codex CLI work must always happen on a
feature branch.

Rules:

- Codex must never commit directly to `main` or `master`.
- Codex must never push directly to `main` or `master`.
- Codex must never merge pull requests.
- The maintainer merges PRs manually in the GitHub web UI.
- After the maintainer merges a PR, the next task starts by updating local
  `main` from `origin/main`.
- After updating `main`, Codex creates a new task branch with
  `git switch -c feature/<short-task-name>`.
- Codex implements the task, runs tests, commits, pushes the feature branch, and
  creates a PR with `gh`.
- Each task should normally produce exactly one focused branch and one focused
  PR.
- Codex must not mix unrelated tasks in the same branch or PR.
- Codex must not continue working on an old feature branch after its PR has
  been merged.
- If the current branch is already a feature branch with unrelated changes,
  Codex must stop and report instead of mixing work.
- If `gh` authentication fails, Codex must report the exact failure and must not
  fake PR creation.
- If `gh` reports an invalid `GH_TOKEN` or `GITHUB_TOKEN`, Codex should try:

  ```bash
  env -u GH_TOKEN -u GITHUB_TOKEN gh auth status
  ```

  If that succeeds, Codex should use the env-unset form for `gh` commands.
- Codex must not commit local Codex state such as `.codex`.
- At the end of every task, Codex must report the branch name, commit hash,
  pushed status, PR URL, tests run, and any failures or skips.
- At the end of every task, Codex must also report documentation impact using
  one of the forms required by the documentation contract section.

Required start-of-task update sequence after a previous PR has been merged:

```bash
git fetch origin
git switch main
git pull --ff-only origin main
```

Then create a fresh task branch:

```bash
git switch -c feature/<short-task-name>
```

Concrete command sequence:

```bash
git fetch origin
git switch main
git pull --ff-only origin main
git switch -c feature/<short-task-name>

# implement task

python -m pytest tests/unit
python -m ruff check app tests
alembic heads

git status --short
git add <task files only>
git commit -m "<clear task message>"
git push -u origin HEAD

gh auth status
gh pr create \
  --base main \
  --head "$(git branch --show-current)" \
  --title "<PR title>" \
  --body "<summary, tests run, and scope constraints>"
```

---

## 11. Nginx deployment guidance

Provide an example Nginx config under `deploy/nginx/slaif-api-gateway.conf`.

It should proxy to the API container or localhost app port.

Important streaming settings:

```nginx
proxy_http_version 1.1;
proxy_buffering off;
proxy_cache off;
proxy_read_timeout 3600s;
proxy_send_timeout 3600s;
```

Also set:

```nginx
proxy_set_header Host $host;
proxy_set_header X-Real-IP $remote_addr;
proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
proxy_set_header X-Forwarded-Proto $scheme;
```

Set a sane body size, for example:

```nginx
client_max_body_size 20m;
```

If `/metrics` is exposed through Nginx, restrict it by IP allowlist, internal network, or admin authentication. Do not expose metrics publicly.

---

## 12. Security requirements in detail

### 12.1 Gateway keys

- Generate with CSPRNG.
- Store only HMAC-SHA-256 hash with server pepper and key version.
- Compare in constant time.
- Show once.
- Email only at creation or rotation time.
- Redact everywhere.

### 12.2 One-time secrets

- Required for asynchronous key email delivery.
- Store encrypted temporary secret material only.
- Use AES-256-GCM or equivalent authenticated encryption.
- Master encryption key must come from environment variables or Docker secrets.
- Use short expiration windows.
- Enforce single-use consumption.
- Do not put plaintext keys into Celery/Redis payloads.

### 12.3 Admin passwords

- Store with Argon2id.
- Never store plaintext.
- Implement secure password reset/change flows.

### 12.4 Admin sessions

- Secure cookies.
- HttpOnly.
- SameSite=Lax or Strict.
- Secure flag in HTTPS production.
- Session expiration.
- Server-side session invalidation.
- Store only hashes of session tokens in the database.

### 12.5 CSRF

- Required for every state-changing admin action.
- HTMX requests must include CSRF token.
- Store or derive CSRF state according to `docs/database-schema.md`.

### 12.6 Upstream provider secrets

- Default: environment variables or Docker secrets.
- Do not store in database by default.
- Do not display in dashboard.
- Do not log.
- If database storage is added later, use AES-256-GCM envelope encryption with a master key outside DB.

### 12.7 Logs

- Redact Authorization headers.
- Redact cookies.
- Redact API keys.
- Redact passwords.
- Redact CSRF tokens.
- Redact provider secrets.
- Redact SMTP passwords.

### 12.8 Prompt/response privacy

- Do not store prompts or responses by default.
- Store usage metadata only.
- If content logging is added later, make it explicit, opt-in, time-limited, and documented.

### 12.9 Personal data retention

The system stores personal data such as names, surnames, institutions, emails, and usage snapshots.

Required documentation:

- Define a retention period for owner records and usage snapshots.
- Define an export policy.
- Define anonymization/pseudonymization behavior for owners linked to historical usage.
- Deleting an owner should either be disallowed while ledger records exist, or should pseudonymize/anonymize owner-linked fields according to the documented policy.

Do not store prompts or completions as a workaround for reporting.

---

## 13. Implementation status and sequencing

AGENTS.md is future-oriented guidance, but it should not send Codex back to
completed foundation work. The current implemented core includes:

1. Python package skeleton, FastAPI app factory, `/healthz`, `/readyz`, and
   OpenAI-compatible `/v1` routing modules.
2. SQLAlchemy models, Alembic migrations, repository modules, and
   TEST_DATABASE_URL-aware integration-test helpers for the schema currently in
   `docs/database-schema.md`.
3. Gateway key generation, HMAC validation, authentication, endpoint allow-list
   checks, request policy checks, and configurable key prefixes.
4. Admin/key/institution/cohort/owner CLI commands, provider/routing/pricing/FX
   CLI commands, and safe usage summarize/export CLI commands.
5. Non-streaming `/v1/chat/completions` forwarding through OpenAI/OpenRouter
   adapters with provider-config-driven adapter construction, route resolution,
   pricing/FX lookup, PostgreSQL quota reservation, accounting finalization, and
   mocked OpenAI/OpenRouter E2E coverage.
6. FastAPI lifespan-managed database engine/sessionmaker setup and realistic DB
   readiness checks.

Remaining major milestones include:

1. Streaming proxy support with SSE tests and interrupted-stream accounting.
2. Redis-backed rate limiting.
3. Admin dashboard routes/templates with CSRF-protected state changes.
4. Email delivery through one-time secrets and Celery/Mailpit.
5. Prometheus metrics, structured logging expansion, and deployment hardening.
6. Full public docs and compatibility matrix.
7. Optional upstream smoke tests, Playwright dashboard tests, and OpenTelemetry tracing.

At every stage, keep OpenAI-compatible client usage working.

---

## 14. Non-negotiable constraints for Codex

- Do not store plaintext gateway keys.
- Do not put plaintext gateway keys in Celery/Redis payloads.
- Do not store plaintext one-time secrets.
- Do not log secrets.
- Do not require `SLAIF_API_KEY` or `SLAIF_BASE_URL`.
- Do not require real upstream API keys for normal tests.
- Do not implement hard quota enforcement only in Redis.
- Do not allow unbounded output tokens for cost-limited keys.
- Do not implement admin state changes without CSRF protection.
- Do not create a React/Vue SPA unless explicitly requested.
- Do not use CDN Tailwind in production.
- Do not add CI/CD requirements unless explicitly requested.
- Do not expose upstream provider keys to users or admins.
- Do not forward client `Authorization` headers to upstream providers.
- Do not silently allow unknown model pricing for cost-limited keys.
- Do not break streaming by buffering full provider responses.
- Do not return custom gateway-shaped errors from `/v1` routes; use OpenAI-style errors.
- Do not implement a command or dashboard action that resends an old plaintext key.
- Do not create schema fields/tables that conflict with `docs/database-schema.md`.
- Do not change OpenAI-compatible endpoint behavior without checking `docs/openai-compatibility.md` and `docs/compatibility-matrix.md`.
- Do not change provider forwarding behavior without checking `docs/provider-forwarding-contract.md`.
- Do not change streaming, accounting, or reconciliation behavior without checking the relevant compatibility and accounting docs.
- Do not change CLI secret-output behavior without updating operator-facing docs.
- Do not let README or compatibility docs claim support that code and tests do not implement.
- Do not leave documentation drift unreported in the final task report.
- Do not run apt-based PostgreSQL installation unless the maintainer explicitly requests the Codex container PostgreSQL test harness.
- Do not run destructive test setup against DATABASE_URL.
- Use TEST_DATABASE_URL for integration-test database setup and seeding.
- Do not seed real provider API keys.
- Do not seed real personal data.
- Do not store plaintext gateway keys or plaintext one-time secrets in seed data.
- Do not make the Codex/local PostgreSQL harness a requirement for normal unit tests.
- Do not hardcode the gateway API key prefix in key generation, parsing, authentication, tests, seed data, or documentation.
- New keys must use `GATEWAY_KEY_PREFIX`.
- Authentication/parsing must use `GATEWAY_KEY_ACCEPTED_PREFIXES`.

---

## 15. Success criteria

The implementation is successful when:

1. A user can run:

```bash
export OPENAI_API_KEY="sk-slaif-..."
export OPENAI_BASE_URL="https://api.ulfe.slaif.si/v1"
```

and use:

```python
from openai import OpenAI
client = OpenAI()
```

without changing application code.

2. The gateway validates the issued key, enforces hard per-key token/cost quotas, forwards to OpenAI/OpenRouter, and records usage.

3. Streaming works token-by-token and is not buffered by the app or Nginx.

4. Admins can create, revoke, suspend, activate, extend, reset, rotate, and email newly generated/replacement keys from both dashboard and CLI.

5. The database contains no plaintext gateway keys, no plaintext one-time secrets, and no upstream provider secrets.

6. Normal tests pass without real upstream API keys.

7. The repository can be cloned and run with Docker Compose.

8. Documentation clearly explains deployment, security, accounting, provider routing, database schema, and compatibility.
