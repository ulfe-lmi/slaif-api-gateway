# OAP Work Order — 020-d

PR mode: `AMEND_EXISTING_PR`

## Objective

Amend only PR #246 with direct durable-state assertions for the actual generic
gateway matrix. The 020-c outcomes pass, but the test does not scan its new
Chat/Responses/local-zero/provider-error/missing-usage canaries across durable
ledger/audit state and does not reconcile refreshed key counters to ledger
costs. Add those assertions only; production code may change only if they expose
a real defect.

## Verified state

- PR #246 current report head
  `2674de3fbb5b9b276cf861f3fc18a78610e7d993`; 020-c implementation head
  `9d5e687adae068435bb25f79edaea2b2f4c64318`.
- All ten checks green, no review threads, PR open/clean/mergeable.
- Reuse this PR; do not edit prior orders/reports, merge, auto-merge, or create
  another PR.

## Required tests-first evidence

In `tests/integration/test_openai_compatible_conformance_postgres.py`:

1. Reload the gateway key after all matrix outcomes and assert cost/token/
   request reserved counters are zero.
2. Reconcile its used cost to the exact sum of charged ledger EUR costs under
   the existing accounting rules; prove the local-zero ledger contributes
   exactly zero and no duplicate charge exists. Assert token/request counters
   consistently reflect only the endpoint outcomes that existing accounting
   classifies as charged/used.
3. Serialize only durable safe ledger/audit fields/projections for every matrix
   row and assert absence of all request/provider canaries, including Chat,
   Responses, local-zero, remote-image, quota, provider-failure, missing-usage,
   inline-image/base64, tool schema/arguments/results, client key, backend key,
   Authorization/cookie/internal-header, and raw-body markers.
4. Assert the missing-usage row has one non-success/estimated-interrupted
   outcome, no duplicate, non-null non-invoice estimate, and no normal-success
   metadata.

Use existing repositories/models and bounded safe serialization. Do not query
or add prompt/completion/raw content columns.

## Allowed paths

```text
tests/integration/test_openai_compatible_conformance_postgres.py
oap/active
oap/orders/020-d-prove-durable-privacy-and-counter-reconciliation.md
oap/reports/020-d-prove-durable-privacy-and-counter-reconciliation.md
```

No production/doc/migration/E2E/UI change, real provider, or broad suite.

## Verification and publication

Run the exact focused integration file against a disposable
`TEST_DATABASE_URL` with zero skips, scoped Ruff/compileall, Alembic head, and
diff check. Publish one immutable 020-d report-only final commit with literal
implementation head and `Report publication commit: SELF`, verify all
final-head checks, send exact FIFO `OK`, and return to one control wait. Coding
agent never merges.
