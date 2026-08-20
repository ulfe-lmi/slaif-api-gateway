# OAP Work Order — 014-d

## Objective

Amend PR #239 to make reservation-first resolution revalidation genuinely
fresh under SQLAlchemy's identity map, prove actual lifecycle races terminate,
and correct the one code-quality construct/report claim that 014-c left
unchanged. This is the final narrow objective-014 merge repair. Do not alter the
fence schema, migration, product scope, or surrounding quota design.

## Authoritative current state

- Repository: `ulfe-lmi/slaif-api-gateway`.
- Remote `main`: `72ac24d9820fef34bcf23021345c12ec8a57db34`.
- Existing sole objective PR: #239,
  <https://github.com/ulfe-lmi/slaif-api-gateway/pull/239>.
- Existing branch: `oap/014-external-tool-exclusive-fence-reservation`.
- Current remote 014-c report head:
  `b9402546a76017e226e29fbc9638d8bd99d029f2`.
- Its first parent/implementation head:
  `d663825ddecaeff258b5ad51b34108e22df4189d`.
- PR is open and mergeable, auto-merge is null, and all ten final report-head
  checks are successful.
- 014-c correctly implements duplicate rejection, pending/same-key active
  retry, reservation-first resolve ordering, deterministic reservation-wait
  evidence, and formatting cleanup.
- Current SQLAlchemy is 2.0.52. `get_gateway_key_by_id()` loads an identity into
  the session; the later `get_gateway_key_for_update()` executes a locking
  select without `populate_existing`, so the locking query can return the
  already-loaded object's stale attributes rather than overwrite them with row
  state committed while resolve waited.
- The 014-c concurrency test proves resolve does not hold the key while waiting,
  but never changes the key during that wait and therefore does not prove the
  locked revalidation sees new state.
- The GitHub code-quality lambda thread remains current/unresolved because
  `lambda: object()` still exists. The 014-c report's statement that this
  construct was corrected is inaccurate. Its no-effect thread is now
  outdated/resolved.

The 014-a through 014-c orders/reports are immutable. Reconcile these named
facts once, then implement immediately.

## Execution discipline

Do not perform general reconnaissance or another plan pass.

1. First edit `db/repositories/keys.py` so the existing administrative
   `FOR UPDATE` lookup refreshes an already-loaded row.
2. Add the state-change-while-waiting PostgreSQL test.
3. Add the bounded actual release/resolve race and fix the one lambda.
4. Run only the named focused files and publish the report.

Read another file only for a concrete symbol or failing focused test. No
migration discovery, schema edits, broad formatting, or full local suite.

## Fresh locked key lookup

Make `GatewayKeysRepository.get_gateway_key_for_update()` execute its locking
select with SQLAlchemy `populate_existing=True` (or an equivalently explicit
refresh) so it both obtains `FOR UPDATE` and overwrites attributes of an
identity already loaded earlier in the transaction.

- Keep the method's existing signature and row-lock behavior.
- Do not change the separate ordinary quota-update method unless a focused
  failure proves that exact change necessary.
- Do not expire/refresh unrelated session identities.
- Add a focused repository/source or real-PostgreSQL assertion proving the
  refresh option is present and effective.

## Resolve revalidation race

Extend the independent-session reservation-lock test:

1. create an active fence and hold its reservation row lock in session A;
2. start resolve in session B so it performs the unlocked key read and blocks
   on the reservation;
3. in session C, lock the key, change the fence state from `active` to `held`
   while preserving all bound fields, and commit;
4. release session A's reservation lock;
5. assert resolve completes within a bounded timeout, freshly observes
   `held`, returns the held no-op, does not clear/mutate the fence, and writes
   no resolution audit.

This must fail against the stale 014-c lookup and pass only with fresh locked
revalidation.

## Actual lifecycle lock-order proof

Add one focused independent-session simulation using the real
`QuotaService.release_reservation` and `ExternalToolFenceService.resolve` on
the same external reservation. Exercise reservation→key order with a bounded
timeout. Accept only contractually expected terminal/invariant outcomes and
assert:

- no PostgreSQL deadlock or timeout;
- one reservation only;
- counters reconcile exactly once;
- the fence never clears without required ledger evidence;
- no second acquisition/audit/provider side effect occurs.

Do not wire provider execution or invent final usage. This is lock/lifecycle
evidence only.

## Review/report truth

- Replace the unchanged `lambda: object()` with `object` (the parametrized test
  already calls the supplied callable).
- Do not edit the immutable 014-c report. The 014-d report must state plainly
  that 014-c claimed the lambda was corrected when it was not.
- Query the four PR review threads once after implementation. Report exact
  resolved/outdated/current state. Do not claim resolution GitHub does not show.
- Do not introduce formatting-only churn.

## Allowed paths

Only:

```text
app/slaif_gateway/db/repositories/keys.py
app/slaif_gateway/services/external_tool_fence.py
oap/active
oap/orders/014-d-refresh-locked-state-and-close-review-gap.md
tests/integration/test_external_tool_fence_concurrency_postgres.py
tests/integration/test_external_tool_fence_postgres.py
tests/unit/test_external_tool_fence.py
```

The final report-only commit adds only:

```text
oap/reports/014-d-refresh-locked-state-and-close-review-gap.md
```

Do not modify models, migration 0015, quota/accounting services, docs, schemas,
provider/request handlers, dependencies, CI, prior OAP artifacts, or any other
path. If the actual `QuotaService` test requires an existing helper from
another file, recreate only the minimal fixture inside the allowed integration
file; do not widen scope.

## Focused verification

Run only:

- `tests/unit/test_external_tool_fence.py`;
- `tests/integration/test_external_tool_fence_postgres.py` and
  `tests/integration/test_external_tool_fence_concurrency_postgres.py` against
  one explicit safe disposable `TEST_DATABASE_URL`, no skips;
- scoped Ruff/format-check/compile, Alembic one-head, diff/path/privacy checks;
- final GitHub CI.

No full local unit/integration/E2E/browser/Docker/HPC/manual-Codex/provider
suite. No real provider, email, Redis authority, production data, or secret.

## Acceptance criteria

1. Locked key revalidation refreshes an already-loaded identity from row state
   acquired under `FOR UPDATE`.
2. A state change committed while resolve waits is observed exactly; `held` is
   not cleared and no stale-state audit/mutation occurs.
3. Actual quota release versus fence resolve terminates without deadlock and
   preserves reservation, counter, fence, and ledger prerequisites.
4. All 014-c duplicate/retry/lock-order behavior remains green.
5. The current lambda construct is actually removed and review-thread/report
   truth is accurate.
6. No unrelated formatting, schema, migration, provider, or forwarding change.
7. Focused tests and all ten final report-head checks pass.
8. PR #239 remains unique; coding agent does not merge/auto-merge; immutable
   report topology is exact.

## GitHub and immutable report

Commit the unchanged order and `oap/active=014-d` with implementation, push to
the existing PR #239 branch, and inspect/repair only in-scope CI failures.
Never merge or enable auto-merge.

Publish exactly one atomic immutable report at
`oap/reports/014-d-refresh-locked-state-and-close-review-gap.md` containing:

- implementation SHA and `Report publication commit: SELF`;
- exact refresh mechanism and stale-state reproduction result;
- actual release/resolve session ordering, timeout, outcome, counters, fence,
  reservation, ledger, and audit evidence;
- lambda correction and exact GitHub review-thread states;
- focused commands/counts/skips, disposable PostgreSQL setup/cleanup;
- diff/privacy/no-provider/no-broad-suite/no-merge evidence.

The final report commit must parent the implementation head and change only the
new report file. Verify the remote topology, then send exact `OK` to
`response.fifo` and return to `control.fifo`.
