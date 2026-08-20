# OAP Work Order — 017-f

## Objective

Amend PR #242 with direct post-reconciliation gateway evidence for the two
gateway-created hold scenarios. This is tests-only. Do not change production
or documentation.

## Verified state

- Sole Objective 017 PR #242, same branch.
- 017-e implementation:
  `60cd321a365e4c7276b715d9e5d07ff36e18d33e`.
- 017-e report head:
  `a51c7e7883f08817451ece3221175a2e40fad8d1`.
- The report topology is valid; final checks were reported green; reviews were
  resolved; auto-merge is off.
- The 017-e reconciliation helper proves gateway-created holds, pre-reconcile
  blocking, both operator actions, exact counters, one ledger, and one audit.
  It then ends without sending a following request, despite reporting following
  admission/exhaustion behavior.

## Required evidence

Extend the existing gateway-created-hold reconciliation tests:

1. After `finalize-actual` records cost/tokens above the key limits, create a
   successful mocked provider client for the same key/route and send both a
   fitting ordinary request and the hosted web-search request. Prove both fail
   normal quota admission, no provider call occurs, no reservation/ledger/audit
   is added, and used/reserved counters/fence remain exactly unchanged.
2. After `release-no-charge`, create a successful mocked provider client for
   the same key/route and send a fitting hosted request. Prove it is admitted,
   invokes the provider exactly once, finalizes one new content-free ledger,
   clears the fence/reserved counters, and preserves the single prior
   reconciliation audit without duplicate hold/reconciliation mutation.
3. Keep provider/query/error canaries absent from responses and durable state;
   assert Redis release for each attempted following request.

You may refactor test helpers inside the integration file to use mutable
provider controllers or fresh clients. Do not weaken existing assertions.

## Allowed paths

```text
tests/integration/test_responses_external_tool_postgres.py
oap/active
oap/orders/017-f-prove-post-reconciliation-admission.md
```

Final report-only commit may add:

```text
oap/reports/017-f-prove-post-reconciliation-admission.md
```

If these tests expose a production defect, publish a truthful blocker report
without editing production paths.

## Verification

Create/migrate/drop one uniquely named disposable PostgreSQL DB and run
`tests/integration/test_responses_external_tool_postgres.py` with zero skips.
Run scoped Ruff/compileall, `git diff --check`, exact path check, and final
GitHub CI. Do not run a broad local suite.

Report exact post-reconciliation HTTP outcomes, provider/Redis call counts,
before/after reservations/ledgers/audits/counters/fence, privacy canaries, DB
cleanup, and CI/review state.

## PR/report protocol

Use existing PR #242; create no PR. Commit this order and exact
`oap/active=017-f`. Publish one immutable report with literal implementation
SHA and `Report publication commit: SELF`; report-only commit parents
implementation and changes only the report. Verify remote head/checks/reviews,
signal exact `OK`, return to control FIFO, and never merge/auto-merge.
