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
- Optional integration repository smoke checks live in `tests/integration/test_repositories_foundation.py` and `tests/integration/test_repositories_accounting_and_pricing.py`, and run only when `DATABASE_URL` is configured against an already migrated database.
- Repositories do not own transaction boundaries (no internal commit); higher-level services will own transactions.

## Security utility note

- Gateway key utility helpers now generate OpenAI-compatible user tokens in `sk-ulfe-...` format.
- Persistence logic should store only HMAC token digests (never plaintext gateway keys).
- One-time key email payloads are intended to use encrypted temporary secret blobs.
- Current crypto helpers are pure utilities and do not create database rows by themselves.


## Service-layer key creation status

- A dedicated service-layer workflow now creates gateway keys and returns the plaintext key exactly once in a transient service result.
- Database persistence stores only the HMAC-SHA-256 token digest and key metadata in `gateway_keys` (never plaintext key material).
- One-time delivery data is stored as encrypted payload + nonce in `one_time_secrets` for a later email workflow.
- CLI key creation, dashboard key creation, and email sending workflows are intentionally not implemented in this slice yet.
