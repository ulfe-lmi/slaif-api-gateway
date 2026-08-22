# OAP Work Order — 129-a

PR mode: `CREATE_NEW_PR`
Branch: `oap/129-organization-boundary-invariant-suite`
Base: main @ 7deac43777c7

## Objective and reason

Create a hostile negative test suite proving organization, role, policy, and
accounting boundary invariants for the single-organization SME model. This is
the Phase 4 gate: it must demonstrate that cross-unit access, privilege
escalation, and accounting bypass are all blocked before operational qualification.

## Verified state

- main = 7deac43777c7; no open non-Dependabot PR.
- Objectives 118–128 merged (org model through security hardening).
- PostgreSQL remains the sole accounting truth source.

## Scope

1. Cross-boundary access tests:
   - Team A cannot read/write Team B's resources.
   - Project X cannot access Project Y's budgets or keys.
   - Service account cannot escalate to admin.
   - Auditor cannot modify any resource.
2. Role ceiling tests:
   - Each role can only perform its permitted operations.
   - No role can grant itself higher permissions.
3. Budget/catalog/tool boundary tests:
   - Key outside budget scope cannot reserve against that budget.
   - Unknown/removed catalog entries fail closed.
   - External-tool fence cannot be bypassed via alternate endpoint.
4. Concurrent mutation tests:
   - Simultaneous budget reservations cannot overspend.
   - Concurrent policy updates maintain revision integrity.
5. Identifier confusion tests:
   - UUID collision/alias does not grant unauthorized access.
6. Export visibility tests:
   - Export only includes data within the caller's authorized scope.

## Exact requirements

1. Every invariant has at least one negative test proving the boundary holds.
2. Tests exercise API, CLI, dashboard, and worker paths where applicable.
3. Results are published as an invariant matrix mapped to code/tests.
4. Remaining post-MVP tenancy limits are documented honestly.

## Allowed paths

```
tests/integration/test_boundary_invariants_postgres.py
tests/unit/test_boundary_invariants.py
docs/boundary-invariant-matrix.md
oap/orders/129-a-organization-boundary-invariant-suite.md
oap/reports/129-a-organization-boundary-invariant-suite.md
oap/active
```

## Non-goals

No claim of hostile public multi-tenancy or PostgreSQL RLS isolation.

## Observable acceptance

- All boundary invariant tests pass under PostgreSQL.
- Invariant matrix documents each tested boundary with code reference.
- Post-MVP limitations stated honestly.
- All required final-head CI checks green.

## Verification commands

```bash
PYTHONPATH=.:app .venv/bin/pytest -q tests/unit/test_boundary_invariants.py
PYTHONPATH=.:app .venv/bin/pytest -q tests/integration/test_boundary_invariants_postgres.py
git diff --check
```

## Boundaries

Non-production only. Provider credentials never exposed.

## OAP contract

Objective 129-a creates one PR; remediation uses 129-b–z same PR.
Coding agent never merges.
