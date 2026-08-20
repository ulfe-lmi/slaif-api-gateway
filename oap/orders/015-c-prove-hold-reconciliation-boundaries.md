# OAP Work Order — 015-c

## Objective

Amend PR #240 with the missing focused PostgreSQL and unit evidence for the
external-tool hold/reconciliation contract. 015-b repaired the implementation
shape, CLI, config, and audit rules, but added no PostgreSQL tests and its
report repeats evidence claims not present in the repository. This round is
tests-first: do not change production code unless a newly required focused test
demonstrates a concrete defect.

## Current state

- Remote `main`: `ef3fdb8ce37381327ebf784b141ab9f7d5f75729`.
- Existing sole objective PR: #240.
- Branch: `oap/015-external-tool-accounting-hold-reconciliation`.
- Current report head:
  `2028c8c90b5e609980e950d56008d37c4d21da01`.
- Its 015-b implementation parent:
  `32b3f741caec8c73b05cc21a23db466d8bd21013`.
- Existing hold PostgreSQL evidence is only:
  - durable basic placement/full reservation;
  - charged-failure finalize plus exact repeat;
  - one 8-worker exact finalize race.
- No migration/schema/provider forwarding is allowed.
- 015-a and 015-b orders/reports are immutable; 015-c must correct their
  evidence overclaims without editing them.

Reconcile PR/head once. Begin by editing the two dedicated hold PostgreSQL
files; do not perform general reconnaissance.

## Required test slices

### Placement, rollback, restart, expiry, and blocking

Add real PostgreSQL tests that:

1. parameterize all five canonical hold reason codes;
2. prove partial token and/or cost evidence produces `estimated`, while no
   partial evidence produces `interrupted`;
3. roll back placement and verify active fence, no ledger, unchanged counters,
   and no hold-created audit;
4. commit a hold, dispose/recreate engine/session, force expiry, and verify the
   held fence/ledger/full reservation survive;
5. verify held blocks bearer auth and ordinary quota admission;
6. run ordinary expired/scheduled reconciliation against the expired hold and
   prove zero mutation.

### Exact shape and corruption negatives

Add focused unit and/or PostgreSQL cases for:

- held fence with zero ledger and with multiple ledgers;
- active fence plus hold ledger;
- wrong ledger key/request/provider/endpoint/model;
- actual-cost/native-cost present, non-empty usage_raw, wrong status/success,
  malformed/extra/noncanonical metadata, naive/bad held timestamp;
- mismatched reservation/fence pointer and reserved counters;
- exact zero partial tokens remain present in projection;
- exact retry agrees on every safe fact; changed streaming/reason/evidence/
  partial values conflict.

Invalid shapes must never be listed, retried as valid, reconciled, or silently
repaired.

### Finalize, no-charge, overrun, and following admission

Add real PostgreSQL cases that:

1. finalize actual values within remaining limits, clear the fence, and permit
   one later normal quota reservation;
2. finalize actual cost and tokens above the full remaining reservation, move
   counters exactly once, clear only after terminal evidence, leave used
   counters over limit, and reject the next ordinary quota reservation;
3. finalize a charged provider failure with `success=false` and actual charge;
4. execute explicit release-no-charge, produce released + failed/false + zero
   actuals, clear, and permit later quota when balance remains;
5. prove dry-run for both actions requires no actor/reason, mutates nothing, and
   returns the held proposal;
6. prove execute missing actor/reason/confirmation, incompatible action fields,
   negative/non-finite values, changed exact repeat, and mismatched ledger/
   reservation/key all leave held and unchanged;
7. prove audit actor and sanitized operator reason are present exactly once.

### Bounded concurrency

- Add an explicit 2-worker exact reconciliation race and retain the 8-worker
  race; wrap both in `asyncio.wait_for` or equivalent bounded timeout.
- Assert exactly one mutation and N-1 idempotent outcomes, one reservation,
  one ledger, one reconciliation audit, exact counters, and no deadlock.
- Add a 2-worker changed-input race: one allowed outcome wins; the other returns
  the fixed conflict without a second mutation/audit.

### CLI evidence

Extend focused CLI tests for invalid action/UUID/decimal, finalize flag matrix,
release flag matrix, charged failure, safe domain error code, and forbidden
secret/content terms. Do not require a real DB in CLI unit tests.

## Production-code boundary

Production behavior from 015-b is presumed fixed. You may edit only the named
hold/fence/CLI/repository files if a required new test fails for a demonstrated
implementation defect. Record each such defect and repair in the report.
Never weaken a required test to preserve existing behavior.

## Allowed paths

```text
app/slaif_gateway/cli/quota.py
app/slaif_gateway/db/repositories/usage.py
app/slaif_gateway/services/external_tool_fence.py
app/slaif_gateway/services/external_tool_hold.py
oap/active
oap/orders/015-c-prove-hold-reconciliation-boundaries.md
tests/integration/test_external_tool_fence_postgres.py
tests/integration/test_external_tool_hold_concurrency_postgres.py
tests/integration/test_external_tool_hold_postgres.py
tests/integration/test_reconciliation_tasks_postgres.py
tests/unit/test_cli_quota_reconciliation.py
tests/unit/test_cli_quota_reconciliation_safety.py
tests/unit/test_external_tool_fence.py
tests/unit/test_external_tool_hold.py
tests/unit/test_reconciliation_tasks.py
```

Final report-only commit adds only:

```text
oap/reports/015-c-prove-hold-reconciliation-boundaries.md
```

No docs/config/schema/model/migration/provider/dashboard/dependency/CI/prior
OAP changes. If documentation becomes inaccurate because a test exposes a
behavior repair, report the exact blocker instead of editing outside scope.

## Verification and economy

Run exactly the focused hold/fence/CLI/task unit files affected and the four
named PostgreSQL files against one generated disposable `TEST_DATABASE_URL`,
with no skips. Run scoped Ruff/format-check/compile, Alembic one-head,
diff/path/privacy checks, then GitHub CI. No full local unit/integration/E2E/
browser/Docker/HPC/manual-Codex/provider suite and no provider/email/production.

## Acceptance criteria

1. Every placement reason/status plus rollback/restart/expiry/auth/quota/stale
   boundary has direct real PostgreSQL evidence.
2. Corrupt/noncanonical held shapes are excluded and never repaired silently.
3. Within-limit, overrun/next rejection, charged failure, and explicit
   no-charge outcomes are proven end to end through counters/ledger/fence.
4. Dry-run/execute authorization and mutually exclusive flags are proven with
   zero-mutation negatives and exact audit reason.
5. 2/8-worker exact and changed-input races are bounded, deadlock-free,
   exact-once, and fail closed.
6. CLI error/secret-output behavior is directly tested.
7. Reports state only executed evidence and explicitly correct 015-a/015-b
   overclaims.
8. Focused tests and all final report-head checks pass; provider/runtime/schema
   boundaries remain unchanged.
9. Same PR #240, no merge/auto-merge, exact `SELF` report topology.

## GitHub/report contract

Commit unchanged order plus `oap/active=015-c`, push to PR #240 only, inspect
and repair only in-scope CI failures, never merge. Publish one immutable
`oap/reports/015-c-prove-hold-reconciliation-boundaries.md` with literal
implementation SHA, `Report publication commit: SELF`, every exact test name/
command/count/timeout/outcome, any production defect found, PostgreSQL cleanup,
privacy/no-provider/no-broad-suite/scope/check/no-merge facts. Report commit
parents implementation and changes only itself; verify, signal `OK`, return to
control FIFO.
