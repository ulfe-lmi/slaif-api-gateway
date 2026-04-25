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
- Example local URL:

```bash
export DATABASE_URL="postgresql+asyncpg://slaif:slaif@localhost:5432/slaif_gateway"
```

## Migration status note

- The first Alembic migration currently creates foundational identity/admin/gateway-key tables (`institutions`, `cohorts`, `owners`, `admin_users`, `admin_sessions`, `gateway_keys`, `audit_log`).
- The second Alembic migration adds accounting schema tables only (`quota_reservations`, `usage_ledger`); quota reservation/finalization business logic is intentionally not implemented in this slice yet.
- The third Alembic migration adds schema-only provider/routing/pricing/FX tables (`provider_configs`, `model_routes`, `pricing_rules`, `fx_rates`); runtime routing and pricing logic are intentionally not implemented in this slice yet.
- The fourth Alembic migration adds schema-only encrypted key-delivery and email/job tracking tables (`one_time_secrets`, `email_deliveries`, `background_jobs`); runtime email sending, encryption/decryption helpers, and Celery worker logic are intentionally not implemented in this slice yet.
- Running migrations requires a configured PostgreSQL database (`DATABASE_URL`).
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

## Service-layer authentication status

- A dedicated gateway key authentication service is now implemented at the service layer.
- `/v1` routes currently wired in this slice (`GET /v1/models`) now require `Authorization: Bearer ...` gateway-key authentication and return OpenAI-shaped auth errors.
- `/healthz` and `/readyz` remain unauthenticated.
- `/v1/models` currently returns an empty model list (`{"object": "list", "data": []}`) until routing/model-catalog logic is implemented.
- Quota checks, rate limits, model-policy enforcement, and provider forwarding are intentionally not implemented in this slice.

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
