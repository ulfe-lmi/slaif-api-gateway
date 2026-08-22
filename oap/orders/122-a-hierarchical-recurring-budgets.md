# OAP Work Order — 122-a

PR mode: `CREATE_NEW_PR`
Branch: `oap/122-hierarchical-recurring-budgets`
Base: main @ c8f0a8ce17c5

## Objective and reason

Implement hierarchical recurring organizational budgets so that a request is
admitted only when all applicable budgets (org, team/project, user/service,
and key) can reserve atomically in PostgreSQL. This moves the gateway from
lifetime workshop limits to SME organizational budget governance.

## Verified state

- main = c8f0a8ce17c5; no open non-Dependabot PR.
- Objectives 118–121 merged (org/team/project model, OIDC, RBAC, service accounts).
- Existing `gateway_keys` table already has `cost_limit_eur`, `token_limit_total`,
  `request_limit_total`, and reservation columns.
- PostgreSQL remains the sole accounting truth source.

## Scope

1. Add migration for budget period definitions:
   - New table or columns on `gateway_keys` for recurring budgets with
     fixed/rolling period types, start/end boundaries, carryover policy,
     and scope linkage (org/team/project/user/service).
2. Implement atomic multi-budget reservation logic in the accounting service.
3. Period transition handling (reset/carryover) consistent with documented rules.
4. Dashboard/CLI management endpoints for budget CRUD.
5. Audit entries for all budget mutations.

## Exact requirements

1. A request is admitted ONLY when every applicable budget can reserve atomically
   within a single PostgreSQL transaction.
2. Concurrent reservations cannot overspend any budget level.
3. Period transitions are deterministic and race-safe.
4. Existing lifetime limits coexist unchanged; no silent conversion.
5. All budget state changes produce audit records.

## Allowed paths

```
app/slaif_gateway/db/models.py
migrations/versions/0020_*.py
app/slaif_gateway/services/accounting.py
app/slaif_gateway/api/admin.py
app/slaif_gateway/cli/
tests/unit/test_budgets*.py
tests/integration/test_budgets*_postgres.py
docs/database-schema.md
docs/compatibility-matrix.md
oap/orders/122-a-hierarchical-recurring-budgets.md
oap/reports/122-a-hierarchical-recurring-budgets.md
oap/active
```

## Non-goals

No invoicing/payment collection. No Redis-only truth. No silent lifetime conversion.
No provider invoice replacement.

## Observable acceptance

- Multi-budget concurrent reservation tests pass under PostgreSQL.
- Period boundary tests pass (fixed and rolling).
- Existing lifetime limit regression suite passes unchanged.
- Dashboard/CLI budget management works end-to-end.
- All required final-head CI checks green.

## Verification commands

```bash
PYTHONPATH=.:app .venv/bin/pytest -q tests/unit/test_budgets*.py
PYTHONPATH=.:app .venv/bin/pytest -q tests/integration/test_budgets*_postgres.py
git diff --check
```

## Boundaries

PostgreSQL-only accounting truth. Provider credentials never exposed.
Non-production environment only.

## OAP contract

Objective 122-a creates one PR; remediation uses 122-b–z same PR.
Coding agent never merges.
