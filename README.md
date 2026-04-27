<div style="text-align: center;">
  <a href="https://www.slaif.si">
    <img src="https://slaif.si/img/logos/SLAIF_logo_ANG_barve.svg" width="400" height="400">
  </a>
</div>

# SLAIF API Gateway

SLAIF API Gateway is an open-source OpenAI-compatible API gateway for educational and institutional LLM access. It lets users run ordinary OpenAI SDK examples by setting `OPENAI_API_KEY` and `OPENAI_BASE_URL`, while administrators retain control over issued keys, quotas, model access, provider routing, usage accounting, and audit logs.

The gateway is intended for workshops, courses, training events, and AI-factory environments where users need practical access to LLM APIs but organizers must protect upstream provider credentials, control spending, and generate usage reports.

## Local non-Docker setup

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
pytest
uvicorn --app-dir app slaif_gateway.main:app --reload
```


## Database configuration note

- `DATABASE_URL` is optional for unit tests.
- PostgreSQL is required for future integration tests and actual DB operations.
- The FastAPI app creates its async SQLAlchemy engine and sessionmaker once during application lifespan and disposes the engine on shutdown.
- `/readyz` now checks database configuration and reachability. If `DATABASE_URL` is missing or unreachable, readiness reports not ready; Redis is not required for readiness until Redis-backed features are implemented.
- Migrations are still explicit operator actions and are not run during application startup.
- Example local URL:

```bash
export DATABASE_URL="postgresql+asyncpg://slaif:slaif@localhost:5432/slaif_gateway"
```

## Migration status note

- The first Alembic migration currently creates foundational identity/admin/gateway-key tables (`institutions`, `cohorts`, `owners`, `admin_users`, `admin_sessions`, `gateway_keys`, `audit_log`).
- The second Alembic migration adds accounting schema tables only (`quota_reservations`, `usage_ledger`); quota reservation/finalization business logic is intentionally not implemented in this slice yet.
- The third Alembic migration adds schema-only provider/routing/pricing/FX tables (`provider_configs`, `model_routes`, `pricing_rules`, `fx_rates`); provider forwarding and quota/accounting workflows remain intentionally unimplemented.
- The fourth Alembic migration adds schema-only encrypted key-delivery and email/job tracking tables (`one_time_secrets`, `email_deliveries`, `background_jobs`); runtime email sending, encryption/decryption helpers, and Celery worker logic are intentionally not implemented in this slice yet.
- Running migrations requires a configured PostgreSQL database (`DATABASE_URL`).
- Fresh `alembic upgrade head` runs create an Alembic version table wide enough for this project's long revision IDs; the integration harness does not need to pre-create or patch `alembic_version`.
- Current unit tests for this schema slice do not require PostgreSQL.


## Repository layer note

- Async SQLAlchemy repository modules are now available under `app/slaif_gateway/db/repositories/` for foundational identity/admin/key/audit/email/job tables **and** accounting/provider-routing/pricing/FX tables.
- Unit repository tests run without PostgreSQL and validate importability plus safety constraints.
- Optional integration repository smoke checks live in `tests/integration/test_repositories_foundation.py` and `tests/integration/test_repositories_accounting_and_pricing.py`, and run against `TEST_DATABASE_URL` or an automatic Testcontainers PostgreSQL instance.
- Repositories do not own transaction boundaries (no internal commit); higher-level services will own transactions.

## Gateway key prefix configuration

- Gateway keys use `<GATEWAY_KEY_PREFIX><public_key_id>.<secret>` format.
- Default `GATEWAY_KEY_PREFIX` is `sk-slaif-`.
- `GATEWAY_KEY_ACCEPTED_PREFIXES` controls which key prefixes are accepted during parsing/authentication and must include the active `GATEWAY_KEY_PREFIX`.
- Example:

```bash
export GATEWAY_KEY_PREFIX="sk-slaif-"
export GATEWAY_KEY_ACCEPTED_PREFIXES="sk-slaif-,sk-legacy-"
```

## Security utility note

- Gateway key utility helpers generate OpenAI-compatible user tokens with a configurable prefix (default `sk-slaif-`).
- Persistence logic should store only HMAC token digests (never plaintext gateway keys).
- One-time key email payloads are intended to use encrypted temporary secret blobs.
- Current crypto helpers are pure utilities and do not create database rows by themselves.


## Service-layer key creation status

- A dedicated service-layer workflow now creates gateway keys and returns the plaintext key exactly once in a transient service result.
- Database persistence stores only the HMAC-SHA-256 token digest and key metadata in `gateway_keys` (never plaintext key material).
- One-time delivery data is stored as encrypted payload + nonce in `one_time_secrets` for a later email workflow.
- CLI key creation, dashboard key creation, and email sending workflows are intentionally not implemented in this slice yet.

## Service-layer key management status

- Service-layer gateway key management now supports suspend, activate, revoke, update validity, update limits, reset usage counters, and rotate.
- Rotation returns the replacement plaintext key exactly once, stores only the new HMAC digest, and creates encrypted one-time delivery material for a later email workflow.
- Typer CLI commands now support admin bootstrap plus prerequisite key-owner records:
  - `slaif-gateway admin create --email admin@example.org --display-name "Admin User" --password-stdin`
  - `slaif-gateway institutions create --name "SLAIF Test Institute" --country SI`
  - `slaif-gateway cohorts create --name "SLAIF Workshop 2026"`
  - `slaif-gateway owners create --name Ada --surname Lovelace --email ada@example.org --institution-id <institution-id>`
- Typer CLI commands now expose service-backed key management:
  - `slaif-gateway keys create --owner-id <uuid> --valid-days 30`
  - `slaif-gateway keys list`
  - `slaif-gateway keys rotate <gateway-key-id>`
- Typer CLI commands now expose local provider/model catalog configuration:
  - `slaif-gateway providers add --provider openai --api-key-env-var OPENAI_UPSTREAM_API_KEY`
  - `slaif-gateway routes add --requested-model gpt-test-mini --match-type exact --provider openai --upstream-model gpt-test-mini`
  - `slaif-gateway pricing add --provider openai --model gpt-test-mini --endpoint chat.completions --currency EUR --input-price-per-1m 0.10 --output-price-per-1m 0.20`
  - `slaif-gateway fx add --base-currency USD --quote-currency EUR --rate 0.920000000`
- The provider, route, pricing, and FX commands configure local database metadata only. They do not call upstream providers, fetch live pricing, or fetch live FX rates.
- `slaif-gateway pricing import --file pricing.json --dry-run` validates a local JSON or CSV file before writing. JSON imports use a list of objects with fields such as `provider`, `model`, `endpoint`, `currency`, `input_price_per_1m`, `output_price_per_1m`, `valid_from`, and `enabled`.
- Typer CLI commands now expose safe usage ledger reporting:
  - `slaif-gateway usage summarize --group-by provider_model`
  - `slaif-gateway usage export --format csv --output usage.csv`
- Usage summaries and exports include safe metadata, token counts, and costs. They do not include prompts, completions, request bodies, response bodies, token hashes, provider keys, or other secrets.
- `keys create` and `keys rotate` print plaintext keys exactly once; list/show/status/limit/reset commands show safe metadata only.
- Admin password commands never print plaintext passwords or password hashes. Institution, cohort, and owner commands print safe metadata only.
- Dashboard pages, dashboard usage reports, admin routes, email sending, and Celery wiring are intentionally not implemented in this slice yet.
- PostgreSQL-backed CLI integration tests now cover key create/list/show/status/validity/limit/reset/rotation behavior, admin/institution/cohort/owner bootstrap commands, provider/routing/pricing/FX metadata commands, and usage summarize/export commands. They require `TEST_DATABASE_URL` and a migrated test database, and verify password hashing, safe command output, HMAC-only key storage, encrypted one-time delivery material, audit rows, persisted model visibility for `/v1/models`, route resolution, pricing lookup, FX conversion, and usage report output safety. Normal unit tests still do not require PostgreSQL or real upstream provider keys.

## Service-layer authentication status

- A dedicated gateway key authentication service is now implemented at the service layer.
- `/v1` routes currently wired in this slice (`GET /v1/models`) require `Authorization: Bearer ...` gateway-key authentication via FastAPI dependency wiring and return OpenAI-shaped auth errors.
- `/healthz` and `/readyz` remain unauthenticated.
- `/v1/models` now reads from configured model routes plus provider configuration metadata through the service layer and returns OpenAI-shaped model objects.
- `/v1/models` does not call upstream providers and may return an empty list until routes/providers are seeded and enabled.
- `/v1/chat/completions` now performs authentication, minimal request-shape validation (`model`, `messages`), request-cap policy validation/normalization, service-backed model route resolution, pricing/FX lookup, PostgreSQL-backed quota reservation, non-streaming provider forwarding, and accounting finalization.
- Chat Completions request-cap settings are configurable via `DEFAULT_MAX_OUTPUT_TOKENS` (default `1024`), `HARD_MAX_OUTPUT_TOKENS` (default `4096`), and `HARD_MAX_INPUT_TOKENS` (default `128000`).
- A service-layer pricing and FX lookup workflow can estimate the maximum possible cost for Chat Completions after request policy and route resolution have run.
- Pricing and FX calculations use `Decimal`; unknown pricing and unknown FX conversion data fail closed.
- `/v1/chat/completions` forwards non-streaming requests through the provider adapter layer and returns provider JSON only after accounting finalization succeeds.
- If provider forwarding fails after quota reservation, the route releases the reservation and writes failure accounting before returning an OpenAI-shaped provider error.
- Hard quota reservation uses PostgreSQL row locking and reserved counters, not Redis.
- Unsupported models from `/v1/chat/completions` return OpenAI-shaped route-resolution errors before any forwarding attempt.
- Unknown pricing or FX data fails closed before any quota reservation or provider forwarding attempt.
- Streaming behavior and Redis rate limiting are intentionally not implemented in this slice.

## Provider adapter status

- `/v1/chat/completions` now supports non-streaming provider forwarding through the OpenAI and OpenRouter adapter layer after authentication, request policy, route resolution, pricing, quota reservation, and accounting finalization.
- Mock-tested non-streaming OpenAI and OpenRouter adapters are implemented using `httpx.AsyncClient`, safe outbound header allowlists, upstream API-key injection, basic usage parsing, and safe provider-domain errors.
- Provider forwarding is covered by mocked tests; normal tests do not require real OpenAI or OpenRouter API keys and do not call real upstream providers.
- Streaming is still not implemented.
- Redis rate limiting is still not implemented.
- CLI, dashboard, email, Celery worker, and Docker deployment work remain out of scope for this slice.

## Accounting finalization status

- A service-layer accounting workflow can extract provider usage metadata, compute actual cost from the earlier pricing estimate, finalize pending quota reservations, move reserved counters into used counters, and create usage ledger rows.
- Provider failures can release pending reservations and create failure ledger rows without charging actual cost.
- `/v1/chat/completions` uses this accounting workflow for non-streaming provider responses.
- Quota counter updates now fail explicitly if release/finalization would underflow
  reserved counters; this avoids hiding double-release or double-finalization bugs.
- A PostgreSQL high-contention integration test covers concurrent hard quota
  reservations against one key and verifies reservations cannot overspend limits.
- Streaming remains out of scope for this slice.

## Testing modes

- Unit tests:

```bash
python -m pytest tests/unit
```

- Default integration tests (uses `TEST_DATABASE_URL` when set, otherwise attempts Docker/Testcontainers, otherwise skips cleanly):

```bash
python -m pytest tests/integration
```

- Integration tests with an existing test database:

```bash
TEST_DATABASE_URL="postgresql+asyncpg://..." python -m pytest tests/integration
```

- Explicit Codex/local PostgreSQL harness:

```bash
./scripts/codex-install-postgres.sh
./scripts/codex-start-postgres.sh
./scripts/create-test-db.sh
export TEST_DATABASE_URL="postgresql+asyncpg://slaif:slaif@localhost:5432/slaif_gateway_test"
alembic upgrade head
python scripts/seed_test_data.py
python -m pytest tests/integration
```

Integration tests never use `DATABASE_URL` for destructive setup by default.

- OpenAI Python client E2E test:

```bash
TEST_DATABASE_URL="postgresql+asyncpg://..." python -m pytest tests/e2e/test_openai_python_client_chat.py
```

This E2E test uses the official `openai` Python package with `OpenAI()` reading only
`OPENAI_API_KEY` and `OPENAI_BASE_URL` from the client environment. It runs the local
FastAPI app against a migrated PostgreSQL test database, issues a gateway key through
the safe key service, mocks upstream OpenAI HTTP with RESPX, and requires no real
OpenAI/OpenRouter API keys. Unit tests still do not require PostgreSQL or upstream keys.

- OpenRouter Python client E2E test:

```bash
TEST_DATABASE_URL="postgresql+asyncpg://..." python -m pytest tests/e2e/test_openrouter_python_client_chat.py
```

This E2E test uses the same official OpenAI Python client environment-variable flow,
but resolves the gateway route to OpenRouter and mocks upstream OpenRouter HTTP with
RESPX. It requires `TEST_DATABASE_URL` with a migrated test database and does not
require real OpenRouter keys. Unit tests still do not require PostgreSQL or upstream keys.
