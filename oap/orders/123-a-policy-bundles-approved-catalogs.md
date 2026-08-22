# OAP Work Order — 123-a

PR mode: `CREATE_NEW_PR`
Branch: `oap/123-policy-bundles-approved-catalogs`
Base: main @ 43c06a286cde

## Objective and reason

Implement versioned SME policy bundles and approved model/tool catalogs so
organizations can manage understandable policy packages rather than
hand-editing every key. Connects reviewed provider catalogs to approved
organizational catalogs with preview/diff/confirmation and immutable revision provenance.

## Verified state

- main = 43c06a286cde; no open non-Dependabot PR.
- Objectives 118–122 merged (org model, OIDC, RBAC, service accounts, budgets).
- Existing `model_routes` table has per-route capabilities JSONB.
- PostgreSQL remains the sole accounting truth source.

## Scope

1. Migration for policy bundle definitions:
   - New tables for versioned bundles, bundle revisions, catalog entries.
   - Link bundles to org/team/project scopes.
   - Immutable revision provenance (no in-place mutation).
2. Policy composition service:
   - Compose effective policy from org → team/project → key hierarchy.
   - Fail closed on unknown/removed models/tools with actionable drift report.
3. Preview/diff endpoints:
   - Before assignment, show the exact effective policy that would apply.
4. Catalog import:
   - Import provider catalog entries into approved organizational catalogs.
5. Admin dashboard + CLI management.

## Exact requirements

1. Operators can preview the exact effective policy before assignment.
2. Old assignments remain bound to their original revision (immutable provenance).
3. Unknown or removed models/tools fail closed with actionable drift report.
4. No silent mutation of existing identities or policies.
5. All policy changes produce audit records.

## Allowed paths

```
app/slaif_gateway/db/models.py
migrations/versions/0021_*.py
app/slaif_gateway/services/policy_bundles.py
app/slaif_gateway/api/admin.py
app/slaif_gateway/cli/
tests/unit/test_policy_bundles*.py
tests/integration/test_policy_bundles*_postgres.py
docs/database-schema.md
docs/compatibility-matrix.md
oap/orders/123-a-policy-bundles-approved-catalogs.md
oap/reports/123-a-policy-bundles-approved-catalogs.md
oap/active
```

## Non-goals

No silent mutation of existing identities. No production import without review.
No arbitrary policy code execution. No global allow-all.

## Observable acceptance

- Policy composition tests pass under PostgreSQL.
- Preview/diff shows exact effective policy before assignment.
- Drift detection catches removed/unknown models/tools.
- Revision immutability verified (old assignments still resolve to old revision).
- Dashboard/CLI management works end-to-end.
- All required final-head CI checks green.

## Verification commands

```bash
PYTHONPATH=.:app .venv/bin/pytest -q tests/unit/test_policy_bundles*.py
PYTHONPATH=.:app .venv/bin/pytest -q tests/integration/test_policy_bundles*_postgres.py
git diff --check
```

## Boundaries

PostgreSQL-only truth. Provider credentials never exposed. Non-production only.

## OAP contract

Objective 123-a creates one PR; remediation uses 123-b–z same PR.
Coding agent never merges.
