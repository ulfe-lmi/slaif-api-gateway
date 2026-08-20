# OAP Work Order — 014-c

## Objective

Amend the existing objective-014 PR #239 to close the final independently
verified merge blockers: duplicate request capabilities are silently accepted,
active-fence retries do not require a same-key pending reservation and can
mis-handle `held`/terminal state, and fence code locks key then reservation
while existing quota lifecycle code locks reservation then key. Correct the
014-b report overstatement through this new immutable continuation report and
remove its avoidable formatting-only churn.

Keep the working fence, schema, exclusivity, stale handling, key-mutation
blocking, and provider/route binding intact. External forwarding and provider
calls remain disabled.

## Authoritative current state

- Canonical repository: `ulfe-lmi/slaif-api-gateway`.
- Remote `main`:
  `72ac24d9820fef34bcf23021345c12ec8a57db34`.
- Existing objective PR: #239,
  <https://github.com/ulfe-lmi/slaif-api-gateway/pull/239>.
- Existing branch:
  `oap/014-external-tool-exclusive-fence-reservation`.
- Current remote report head:
  `86400d4171654b4d2df891a8420dbbfc29b8dfcc`.
- Its first parent/014-b implementation head is
  `7f6b3bee551c3a70d9fe5606e3710d28f0fbea1d`.
- PR #239 is the only objective-014 PR, is open/clean/mergeable, auto-merge is
  null, and all ten checks on the current report head are successful.
- The current Alembic head remains the unreleased
  `0015_external_tool_exclusive_fence`; do not add or edit a migration in this
  continuation.
- The 014-b order and report are immutable and must not be edited.

Strategic review reproduced duplicate acceptance directly:

```text
ExternalToolFenceService._validate_capabilities(
    ("provider_web_search", "provider_web_search")
)
=> ("provider_web_search",)
```

It also verified these actual lock orders:

```text
ExternalToolFenceService acquire retry / resolve: key -> reservation
QuotaService.release_reservation:              reservation -> key
```

Current review-thread truth includes two unresolved code-quality threads from
014-b: an unnecessary test lambda and an awaited task expression reported as a
statement with no effect. The 014-b report's assertion that no new findings
remained was therefore inaccurate. Preserve that report and correct the record
only in 014-c.

Reconcile these exact named facts once. If they changed materially, report the
conflict rather than creating another PR.

## Execution discipline — implement immediately

Do not perform general reconnaissance.

1. Read this order and the named service/tests once.
2. First edit `services/external_tool_fence.py` to reject duplicate request
   capabilities and harden the active-retry state checks.
3. Run the focused unit file.
4. Implement the reservation-first resolution lock order and its focused real
   PostgreSQL proof.
5. Perform the bounded diff/review hygiene slice last.

Read another file only for a concrete missing symbol or failing focused test.
Do not repeat repository/environment/migration/test discovery and do not run a
full local suite.

## Slice 1 — canonical capability input and exact active retry

In `ExternalToolFenceService`:

- reject duplicate request capability IDs before sorting/canonicalization;
- apply the absolute/operator ceiling to the original canonical list and do
  not use deduplication to bring an invalid request under the ceiling;
- keep existing unknown/malformed capability failures and destination checks;
- permit an idempotent retry only when the key fence is exactly `active`, the
  pointed reservation belongs to that same key, its request ID matches, its
  status is exactly `pending`, and all endpoint/model/provider/route/capability/
  destination/mode facts match;
- a `held` fence always remains blocking, including for the same request ID;
- a terminal, missing, cross-key, wrong-mode, or otherwise conflicting pointed
  reservation fails closed with a fixed safe conflict/invariant error;
- the retry path must not increment counters, create a reservation/audit row,
  or mutate fence state.

Do not weaken the unique pointer/FK checks or route/provider binding. Add focused
unit and PostgreSQL negatives for duplicate request capabilities, same-request
`held`, same-request terminal reservation, and a pointed reservation rebound to
another key.

## Slice 2 — one reservation-first lifecycle lock order

The established quota lifecycle order is reservation then gateway key. Remove
all fence paths that hold the key row lock while attempting to lock an existing
reservation.

### Acquire retry

New acquisition still locks the key row first because no reservation exists.
For an already-bound active retry, read the pointed reservation without taking
`FOR UPDATE`; this path is read-only and the held key lock prevents a
well-behaved lifecycle transition from committing through its later key lock.
Revalidate the exact pending/same-key identity before returning. It must never
wait on a reservation lock while holding the key lock.

### Resolve

For an active fence:

1. read the key without a row lock only to obtain the candidate fence pointer;
2. lock that reservation `FOR UPDATE` first;
3. then lock the gateway key row;
4. revalidate state, pointer, request ID, ownership, terminal status, ledger
   facts, and zero counters after both locks;
5. clear only on the already-required exact authoritative evidence.

If state/pointer changes between the initial read and the locked recheck, fail
closed or return the already-valid exact no-op without clearing unrelated/new
state. `none` remains idempotent; `held` remains blocking and is never cleared
by objective 014.

Add focused lock-order evidence:

- unit repository-call ordering asserts reservation lock precedes key lock for
  active resolution and active retry never calls the reservation-lock method;
- real PostgreSQL independent-session test holds the reservation lock, starts
  resolve, and proves another transaction can still lock the key while resolve
  waits—then all tasks finish within a bounded timeout without deadlock and the
  fence is not incorrectly cleared;
- a concurrent ordinary release/finalization versus retry/resolve simulation
  terminates under a bounded timeout, preserves accounting/fence invariants,
  and never creates a second reservation.

Do not redesign all quota/accounting services in this continuation. Align the
fence code to the established reservation→key order.

## Slice 3 — review truth and minimal diff hygiene

- Replace the unnecessary simple lambda in
  `tests/unit/test_external_tool_fence.py` with the direct callable or a named
  helper.
- Replace the no-effect-looking awaited task expression in the concurrency
  test with an explicit assignment/helper while preserving its exception
  assertion.
- Query PR #239 review threads once after the implementation push. Report exact
  resolved/outdated/unresolved state; do not claim all findings are closed
  unless GitHub proves it. Do not edit prior reports.
- Restore pre-014-b formatting for lines unrelated to objective-014 behavior in
  `db/models.py` and `db/repositories/quota.py`, retaining every functional
  014-b field, FK, check, index, relationship, and repository argument. The
  resulting comparison from `f9168909...` to the new implementation head must
  contain only functional fence/quota hunks in those two files, not whole-file
  formatter churn.
- Do not run whole-file autoformat on mature existing files. Apply formatting
  only to newly edited blocks and use Ruff check/format-check for proof.

The 014-c report must explicitly correct the immutable 014-b overclaims about
duplicate request rejection and new review findings.

## Allowed paths

This continuation may modify only:

```text
app/slaif_gateway/db/models.py
app/slaif_gateway/db/repositories/quota.py
app/slaif_gateway/services/external_tool_fence.py
docs/accounting.md
docs/security-model.md
oap/active
oap/orders/014-c-close-retry-lock-order-and-review-truth.md
tests/integration/test_external_tool_fence_concurrency_postgres.py
tests/integration/test_external_tool_fence_postgres.py
tests/unit/test_external_tool_fence.py
```

The final report-only commit adds only:

```text
oap/reports/014-c-close-retry-lock-order-and-review-truth.md
```

Do not edit migration 0015, schema shape, 012 policy-contract code, quota/
accounting lifecycle services, provider/request handlers, dependencies, CI,
README, 014-a/014-b orders or reports, or any path outside this list. A concrete
outside-path need is a blocker to report, not permission to expand.

## Focused verification and test economy

Run only:

1. `tests/unit/test_external_tool_fence.py`;
2. the two dedicated PostgreSQL fence files against one explicit safe
   disposable `TEST_DATABASE_URL`, without skips;
3. the existing documentation-contract drift file read-only if the focused
   service import boundary changes or CI identifies it;
4. scoped Ruff/format-check/compile, Alembic one-head, diff/path/privacy checks;
5. final GitHub CI for PR #239.

Do not run full local unit, integration, E2E, browser, Docker, HPC, manual-Codex,
or provider suites. Do not call a provider, use real credentials, send email,
or touch production. Remove only the disposable test database created for this
round.

## Acceptance criteria

1. Duplicate request capabilities fail before mutation; valid canonical input
   retains its existing behavior and ceilings.
2. Idempotent retry requires an active, pending, same-key, exact reservation;
   held/terminal/cross-key/conflicting facts stay blocked without mutation.
3. Fence code never waits for an existing reservation lock while holding the
   key lock; active resolution follows reservation→key with locked revalidation.
4. Deterministic unit/PostgreSQL evidence proves lock order and bounded
   deadlock-free lifecycle races without clearing or duplicating exposure.
5. Existing fence, accounting, privacy, stale, route/provider, and no-forwarding
   invariants remain intact.
6. The two new bot findings are code-corrected and their actual GitHub thread
   state is reported honestly; 014-b's overclaim is corrected immutably here.
7. Formatting-only unrelated churn is removed while every functional 014-b
   change remains.
8. Focused local evidence and every final report-head GitHub check pass; no
   broad local suite or provider call occurs.
9. PR #239 remains the sole objective-014 PR; no merge/auto-merge occurs; report
   `SELF` topology is exact.

## GitHub and report contract

Commit the unchanged order and `oap/active=014-c` with the repair, push to the
existing branch, and amend PR #239 only. Never merge or enable auto-merge.

Atomically publish exactly one immutable report at
`oap/reports/014-c-close-retry-lock-order-and-review-truth.md`. Include:

- literal implementation SHA and `Report publication commit: SELF`;
- duplicate, active/pending/same-key retry, held/terminal/cross-key negatives;
- exact old/new lock sequences and deterministic session/timeout outcomes;
- focused test commands/counts/skips, PostgreSQL URL safety and cleanup;
- diff-hygiene before/after evidence and exact review-thread states;
- correction of the two 014-b report overclaims;
- privacy/Redis/no-provider evidence, docs impact, scope, GitHub checks, and
  no-merge/no-auto-merge confirmation.

The final report commit must parent the implementation head and change only the
new report file. Verify the remote topology and checks, send exact `OK` through
`response.fifo`, then return to blocking on `control.fifo`.
