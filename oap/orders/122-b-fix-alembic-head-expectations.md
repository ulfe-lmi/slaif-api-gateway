# OAP Work Order — 122-b

PR mode: `CONTINUE_EXISTING_PR`
PR: #261
Branch: `oap/122-hierarchical-recurring-budgets`

## Objective

Fix CI failures: alembic head revision tests expect `0019_service_accounts` but
the new migration `0020_hierarchical_recurring_budgets` is now the head.

## Exact fix

Update expected head revision from `'0019_service_accounts'` to
`'0020_hierarchical_recurring_budgets'` in ALL of:

- `tests/unit/test_alembic_accounting.py`
- `tests/unit/test_alembic_email_jobs.py`
- `tests/unit/test_alembic_external_tool_fence.py`
- `tests/unit/test_alembic_key_prefix_default.py`
- `tests/unit/test_alembic_provider_pricing.py`
- `tests/unit/test_schema_status.py`

Also check and update any integration test that references the old head.

## Verification

```bash
PYTHONPATH=.:app .venv/bin/pytest -q \
  tests/unit/test_alembic_accounting.py \
  tests/unit/test_alembic_email_jobs.py \
  tests/unit/test_alembic_external_tool_fence.py \
  tests/unit/test_alembic_key_prefix_default.py \
  tests/unit/test_alembic_provider_pricing.py \
  tests/unit/test_schema_status.py
```

All must pass with `'0020_hierarchical_recurring_budgets'`.
