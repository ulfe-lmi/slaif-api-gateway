<div style="text-align: center;">
  <a href="https://www.slaif.si">
    <img src="https://slaif.si/img/logos/SLAIF_logo_ANG_barve.svg" width="400" height="400">
  </a>
</div>

# SLAIF API Gateway

SLAIF API Gateway is an open-source, OpenAI-compatible API gateway for educational and institutional LLM access. It lets users run ordinary OpenAI SDK examples by setting `OPENAI_API_KEY` and `OPENAI_BASE_URL`, while operators keep control over issued gateway keys, quotas, model access, provider routing, pricing, usage accounting, and audit logs.

The gateway is intended for workshops, courses, training events, and AI-factory environments where users need practical LLM API access but organizers must protect upstream provider credentials and spending.

## Current Status

Implemented:

- `GET /healthz` and `GET /readyz`.
- Authenticated `GET /v1/models` backed by local provider and route metadata.
- Non-streaming and SSE streaming `POST /v1/chat/completions` with request policy checks, route resolution, pricing/FX lookup, PostgreSQL quota reservation, provider forwarding through OpenAI/OpenRouter adapters, and accounting finalization.
- Gateway key generation/authentication with HMAC-only storage and configurable key prefixes.
- Typer CLI commands for admin bootstrap, institutions, cohorts, owners, key management, provider config, model routes, pricing, FX rates, usage summaries/exports, and DB migration helpers.
- PostgreSQL-backed quota/accounting, usage ledger metadata, model catalog, route resolution, and pricing/FX services.
- Manual stale quota-reservation reconciliation for operator repair of expired pending reservations after crashes.
- Redis-backed operational rate limiting for `/v1/chat/completions` when enabled, covering request, estimated-token, and concurrency limits.
- Observability foundation with request IDs, structured log redaction, basic Prometheus HTTP/provider metrics, and controlled `/metrics` exposure.
- Mocked OpenAI/OpenRouter E2E coverage using the official OpenAI Python client, including `stream=True` chat completions.

Not implemented yet:

- Admin dashboard pages.
- Email sending and Celery workers.
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

The FastAPI app creates one async SQLAlchemy engine/sessionmaker during lifespan and disposes the engine on shutdown. `/readyz` checks database configuration, reachability, and whether the database's `alembic_version` revision is current with the committed Alembic head. Redis is not required for readiness unless `ENABLE_REDIS_RATE_LIMITS=true`; when enabled, the app creates one Redis client during lifespan and `/readyz` requires a successful Redis ping.

Redis rate limiting is optional and controls temporary operational throttles only:

```bash
export ENABLE_REDIS_RATE_LIMITS=true
export REDIS_URL="redis://localhost:6379/0"
export DEFAULT_RATE_LIMIT_REQUESTS_PER_MINUTE=60
export DEFAULT_RATE_LIMIT_TOKENS_PER_MINUTE=120000
export DEFAULT_RATE_LIMIT_CONCURRENT_REQUESTS=5
```

When enabled, `/v1/chat/completions` checks Redis after request policy token estimation and before route resolution, pricing, PostgreSQL hard quota reservation, and provider forwarding. Rate-limit failures return OpenAI-shaped errors. PostgreSQL remains authoritative for durable hard quota and accounting.

## Observability

Every HTTP response includes an `X-Request-ID` header. A safe incoming `X-Request-ID` is preserved; otherwise the gateway generates one and binds it to structured logs.

Structured logs redact Authorization headers, gateway/provider keys, cookies, passwords, CSRF/session tokens, token hashes, encrypted payloads, and nonces. Prompts and completions are not logged by default.

`GET /metrics` exposes Prometheus text metrics in development/test when `ENABLE_METRICS=true`. In production, metrics access is restricted by default through `METRICS_REQUIRE_AUTH`; because admin auth for metrics is not implemented yet, production access is denied unless an explicit `METRICS_ALLOWED_IPS` allowlist permits the client IP. Redis is not required for metrics, and OpenTelemetry is not implemented yet.

## CLI Quickstart

Create prerequisite records and a gateway key:

```bash
slaif-gateway admin create --email admin@example.org --display-name "Admin User" --password-stdin
slaif-gateway institutions create --name "SLAIF Test Institute" --country SI
slaif-gateway cohorts create --name "SLAIF Workshop 2026"
slaif-gateway owners create --name Ada --surname Lovelace --email ada@example.org --institution-id <institution-id>
slaif-gateway keys create --owner-id <owner-id> --valid-days 30
```

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

Provider, route, pricing, FX, and usage CLI commands operate on local metadata only. They do not call upstream providers, fetch live pricing, or fetch live FX rates.
Quota reconciliation is manual/operator tooling for expired pending reservations; it defaults to dry-run and does not implement background or Celery cleanup.

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
Streaming E2E tests also use mocked upstream SSE responses for OpenAI and OpenRouter. Successful streaming finalization requires provider final usage metadata; if a stream completes without final usage, the gateway releases the reservation and records a failed/incomplete ledger event with zero actual cost. Client-disconnect timing under a real ASGI server is a future hardening test.

Redis rate-limit integration tests use `TEST_REDIS_URL` when set. If it is not set and `redis-server` is available locally, tests start a temporary user-owned Redis instance on a free localhost port.

## Security Notes

- Plaintext gateway keys are shown only once at creation or rotation.
- PostgreSQL stores gateway key HMAC digests, not plaintext gateway keys.
- Provider configs store provider API key environment variable names, not provider secret values.
- Usage summaries and exports include metadata, token counts, and costs. They do not include prompts, completions, request bodies, response bodies, token hashes, provider keys, or other secrets.
- Usage ledger rows do not store prompts or completions by default.
- Unknown pricing or required FX conversion data fails closed for cost-limited requests.
- Hard quota reservation uses PostgreSQL row locking and reserved counters, not Redis.
- Redis rate limiting is temporary operational throttling only; PostgreSQL remains the hard quota source of truth.

## Schema And Migrations

`docs/database-schema.md` is the authoritative schema source. Schema changes must update that document, SQLAlchemy models, Alembic migrations, and tests together.

Migrations are explicit operator actions and are not run during application startup or `/readyz`. Fresh `alembic upgrade head` runs create the project schema and version table from the committed migration chain.

## Roadmap

Near-term remaining work includes admin dashboard routes/templates, email delivery through Celery and one-time secrets, OpenTelemetry tracing, and fuller public deployment documentation.

For production streaming behind Nginx, disable proxy buffering and use long read/send timeouts so SSE chunks reach clients promptly.
