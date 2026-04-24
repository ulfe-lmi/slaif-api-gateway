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
- Running migrations requires a configured PostgreSQL database (`DATABASE_URL`).
- Current unit tests for this schema slice do not require PostgreSQL.
