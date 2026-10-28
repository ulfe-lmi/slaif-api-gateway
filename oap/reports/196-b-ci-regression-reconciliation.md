# OAP Objective 196-b — final report: bounded CI regression reconciliation (tests/docs only)

Work order: `oap/orders/196-b-ci-regression-reconciliation.md`
(strategic-authored, committed unchanged on the objective branch with
`oap/active` = `196-b`; order sha256
`91516ba44e59ddaffd81f2dc3305732a680f6fb2289f574854935dbe4c34a493`,
verified before and after committing).
Branch: `oap/196-typed-key-policy`; base: `main`
`d8f6c8d731ad12f70d9b1fbd132d72cd6daaa9c7`.
PR mode: AMEND_EXISTING_PR — same unique PR #352,
https://github.com/ulfe-lmi/slaif-api-gateway/pull/352.
The coding agent never merges; no auto-merge is enabled; root reviews
independently and guard-merges.

Implementation head SHA: f622770e0a7f5e950d43c80e4cf9c87b04ad1d6a
Report publication commit: SELF

## Previous immutable state (196-a, unchanged)

- 196-a implementation: `5609162281bf37eb7bcf487399bdcb07d42979d5`;
  196-a report-only SELF: `34850df80f8adffedb04bcfe1a9a4c8c4a1cd59b`
  (first parent `5609162`, tree `d0e3879e0d200447af5cacc0c2b72e0a8df2d4c1`).
- 196-a order sha256 `79e7071b6a0b15471adc36d82c94b085ab90d18eacb758491cb92809ac0e0190`;
  196-a report sha256 `4561e32a6c810581280b9d781275ec67fca6525701ffde8b943e9ef0f15c7771`.
  Neither file's bytes were touched by this round.
- 196-a evidence (52+28 new unit, 146 affected unit, 8 owned-PG, 22
  governance/doc) stands as recorded; it was not re-run this round except
  where this round's order required.

## Implementation commits (branch order, this round)

1. `9fd5eb0bea09cf06cf9e1b1b7d1eb235d13245b7` — "Reconcile 196 CI
   regression oracles (tests/docs only, 196-b)": the strategic order
   (bytes verified unchanged, sha256 above) + exact `oap/active` =
   `196-b` (5 bytes) + the two test repairs + the verification addendum.
2. `f622770e0a7f5e950d43c80e4cf9c87b04ad1d6a` — "Correct 196-b addendum
   qualification prose (pre-publication review)": docs-only accuracy
   corrections (admin node = in-process ASGI TestClient + owned PG, no
   network HTTP/Redis; only the lazy node is real uvicorn HTTP + owned
   PG/Redis; 196 did not change the runtime auth/admission/lazy/Redis
   paths — 196-a changed authoring/policy code; the archived d8 baseline
   runs were not sleep-phase instrumented, only current code was).

No `app/` file, dependency, workflow, config, schema, migration, or
template was changed. No 197-205 feature was started.

## Allowed diff (implementation commits)

- `tests/integration/test_admin_bulk_key_import_execute_postgres.py` —
  the obsolete blanket "allowed_providers unsupported" 400-oracle is
  replaced by an authenticated admin preview -> execute proof of the
  provider policy (complete row: model/endpoint/quota/delivery/CSRF/
  confirmation/reason): preview non-mutating and rendering
  `Providers: openai`; execute persists `allowed_providers=["openai"]`
  on the new key with the rest of the row preserved; explicit empty JSON
  provider list previews as `Providers: deny-all` and persists
  `allowed_providers=[]` distinct from the omitted unrestricted default
  (asserted on the first legacy key); the minimal provider-only row is
  retained as a negative asserting its true stable execution-stage guard
  (`Bulk key import execution failed safely. No keys were created.`) with
  unchanged state and no new queued payloads. All prior
  missing-confirmation/reason/CSRF, strict-only external-tool,
  secret/token_hash/nonce leakage, all-or-nothing, one-time
  plaintext/channel and enqueue assertions are unchanged; count baselines
  extended explicitly for the two new successful imports.
- `tests/integration/test_lazy_throttling_postgres_redis.py` — ONLY
  `test_http_chat_waits_for_capacity_then_admits_once`: it now observes
  the phase its invariant asserts through
  `wait_for_rate_limit_admission`'s existing injectable `sleep` seam
  (test-local wrapper around the chat gateway's callsite): records
  `app.state.db_engine.pool.checkedout()` at entry AND exit of each
  bounded wait-loop sleep, deterministically (thread-safe event, bounded
  wait) requires FOUR consecutive sleeps (eight boundaries) while request
  1 still holds the slot before releasing it, and asserts zero at every
  boundary. Observer exceptions propagate through the request path into
  the final outcome assertions; the bounded-wait failure is a test
  assertion. The shared `_assert_no_checked_out_pool_connections` helper
  and all other nodes are unchanged; the lazy service, revalidation, real
  DB session lifetime, Redis code, single-provider-call,
  attribution/amount, permit-release, cleanup, and all final outcome
  assertions are untouched.
- `docs/verification/2026-10-27-cli-key-policy.md` — appended "196-b
  addendum" (stale-oracle exact source, test-only repairs, focused
  evidence with actual commands/exits/JUnit counts, qualification layer,
  honest CI state). No other doc file needed a correction, so
  `docs/cli-reference.md` / `docs/cli-field-administration.md` were
  untouched.
- `oap/orders/196-b-ci-regression-reconciliation.md` (unchanged bytes),
  `oap/active` (exact `196-b`).

## Focused verification (actual results, 0 skipped)

Environment: `PYTHONPATH=app /tmp/slaif192-coding-venv/bin/python`
(Python 3.12); owned services only (unique-labeled, loopback-bound,
tmpfs PostgreSQL 16 / no-persistence Redis 7, identity inspected before
readiness, exact-ID cleanup); no ambient `DATABASE_URL`, no shared test
DB, no Testcontainers fallback, no foreign PG version; no real provider
keys.

- Admin target node (self-run; owned PG through a TEMP outside-repo
  launcher reusing the existing `owned_pg_url` fixture via
  `__wrapped__()` and setting the explicitly owned `TEST_DATABASE_URL`
  before collection): **1 passed, 0 failed, 0 errors, 0 skipped**,
  actual exit 0. JUnit `/tmp/slaif196b/admin-provider-policy.xml`.
- Lazy target node (root-independently executed against the exact
  working-tree source
  `fa180549d94a79d3b8ec45e9d1fbb95615b1b84184c319208c41e53a7f1b7dc4`):
  **1 passed, 0 skipped**, actual exit 0. JUnit
  `/tmp/slaif196-root/196b-permanent-lazy-independent.xml`. Cited as
  root-provided independently inspected evidence (not claimed as
  self-run).
- Focused negative control (root-independently executed; TEMP
  outside-repo full-source copy replacing ONLY `_observing_sleep` so the
  app connection is held across the sleep): **EXPECTEDFAIL** — 1 failed,
  actual exit 1, at the intended assertion `the waiting request must
  hold no app DB connection at any observed sleep boundary: [1, 1, 1,
  1, 1, 1, 1, 1]` (not a timeout or setup failure). JUnit
  `/tmp/slaif196-root/196b-permanent-lazy-negative.xml`. Cited as
  root-provided independently inspected evidence; never a product passing
  test.
- The two 196-a export strictness regression nodes (unchanged, self-run):
  `test_export_stored_unknown_live_burn_member_fails_explicitly` and
  `test_export_stored_negative_rate_window_fails_explicitly` in
  `tests/unit/test_key_policy_configuration.py`: **2 passed, 0 skipped**,
  actual exit 0. JUnit `/tmp/slaif196b/export-strictness.xml`.
- Static gates on the changed Python (self-run): `ruff check` on both
  changed test files — all checks passed; `git diff --check` — clean;
  `scripts/check_documentation.py` — `DOCUMENTATION_CHECK=OK files=123`
  (re-run after the prose-correction commit).
- Governance/doc (self-run, at final state):
  `tests/unit/test_oap_governance.py` (9) +
  `tests/unit/test_documentation_inventory.py` (13) = **22 passed,
  0 skipped**, actual exit 0. JUnit `/tmp/slaif196b/gov-doc-final2.xml`.

Qualification layer: the lazy node is real uvicorn HTTP + owned
PostgreSQL/Redis with real accounting rows; the admin node is in-process
ASGI (FastAPI TestClient) + owned PostgreSQL (no network HTTP, no Redis
in that node); no real provider inference, no real SMTP, no real
external client anywhere in this round. The 196-a unit evidence remains
fakes/pure-layer as recorded there; nothing here upgrades it.

## CI state (honest, at publication)

- First implementation head `7762b08` (CI run 40609965209): ONLY the
  `PostgreSQL integration tests` job failed — 381 passed / 9 skipped /
  2 failed, exactly the two reconciled nodes; the other nine checks
  passed.
- 196-a report-only head `34850df`: final CI finished 9/10 success, the
  same two PG failures only.
- At this publication the fix-head CI is **PENDING — not a pass**. The
  final normal matrix is supplied by final-head CI; root owns
  final-head CI monitoring and the coding agent never merges. ALL
  final-head merge gates (strategic review + all checks successful)
  remain required.

## Boundaries and limitations

- Tests/docs only: no runtime was changed; this is an oracle
  reconciliation, not a completed runtime repair, and no broader
  196-brief scope or 197+ feature is declared done.
- The separate out-of-scope finding (malformed stored Responses
  known-field values leaking into the new configuration audit during a
  provider-only update) was NOT fixed here per the order; root holds
  merge and will activate a bounded 196-c continuation after this
  handoff. The 196-a report and order were not edited to absorb it.
- The CodeQuality note "unused owned_pg_url" on the old 7762 head is a
  fixture-re-export false positive (root-confirmed); no source edit was
  made for it.
- The root-provided lazy receipts are cited with that attribution; the
  remaining focused results were self-run in this execution with the
  actual exits and JUnit paths above.
