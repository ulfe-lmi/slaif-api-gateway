# OAP Work Order — 151-g

PR mode: `AMEND_EXISTING_PR`
PR: `#286`
Branch: `oap/151-production-appliance-closure`
Base: `main @ ce0cf95685796477685a3aab6edacb39def6c27b`
Current remote head: `3002cebe2c3bd63b04c38259ec566a79a962bcc1`
Title remains: `obj151: qualify production appliance boundary`

## Objective and reason

Close the active-stream prerequisite defect exposed by the single 151-f run.
Before terminating the real API container, prove that the Responses stream is
HTTP 200, live, provider-forwarded, represented by one real Redis slot, and
correlated to a pending PostgreSQL reservation. Then preserve the existing
container-kill, restart, documented CLI reconciliation, accounting, audit, and
cleanup proof. This is an evidence-harness continuation of objective 151 and
PR #286, not a Gateway feature rewrite.

## Verified starting state and failure provenance

- Remote `main` remains
  `ce0cf95685796477685a3aab6edacb39def6c27b`.
- PR #286 is open and mergeable with no auto-merge. Remote head
  `3002cebe2c3bd63b04c38259ec566a79a962bcc1` is the valid report-only 151-f
  commit; its sole parent and implementation head is
  `27f63601f6425eee5d6df9223b5f7f00cfac16b4`. All required report-head checks
  succeeded.
- The 151-f deterministic concurrency implementation is accepted. Its one
  frozen no-keep run proved a live HTTP-200 Chat stream, one provider forward,
  one Redis slot, a pending correlated PostgreSQL reservation, exact HTTP 429
  `concurrency_rate_limit_exceeded` for the overlap, no overlap provider or
  accounting mutation, finalized original accounting, released slot, and a
  following HTTP 200 request.
- That same run then failed honestly in
  `api-termination-and-cli-reconciliation` after 10.73 seconds because the
  captured request ID had no visible PostgreSQL reservation. No whole-matrix
  rerun occurred. Its exact cleanup was independently zeroed and its immutable
  report correctly records `FAIL`.
- `exercise_api_termination_reconciliation` currently repeats the weak pattern
  removed from concurrency: `stream_api` populates capture for both HTTP 200
  and HTTP errors, but this phase waits only for any request ID. It does not
  require status 200, a live thread, a provider forward, or a Redis slot before
  polling PostgreSQL. A fail-closed Redis response can therefore look like an
  active stream until the ten-second reservation poll times out. The failed
  run did not emit enough bounded status/provider/slot evidence to distinguish
  that case from an application defect.
- No real provider credential is authorized. The inherited exposed credential
  remains unusable; never enumerate, validate, print, or call with it.

## Required implementation and evidence

### 1. Reuse and generalize active-stream correlation safely

- Generalize the 151-f Redis slot probe to accept an explicitly validated
  Gateway key UUID, so the concurrency phase continues to query its dedicated
  key while the termination phase queries the ordinary qualification key.
  Shell metacharacters or malformed UUIDs must be rejected before command
  construction.
- Generalize the pure active-stream validator only as needed to accept the
  expected endpoint. Preserve its exact status, request-ID, live-thread,
  provider-delta, one-slot, pending-reservation, provider, resolved-model,
  streaming, and pending-accounting requirements.
- Preserve the complete 151-f Chat concurrency semantics and bounded final JSON
  unchanged. Focused tests and the composed run must prove it did not regress.

### 2. Establish the real active Responses stream before API kill

- Before each bounded establishment attempt, capture:
  - provider-double request count;
  - PostgreSQL reservation/ledger counts and reserved counters for the ordinary
    qualification key;
  - Redis concurrency-slot count for that key.
- Require the baseline Redis slot count to be zero.
- Start the existing 20-second `/v1/responses` stream through HTTPS NGINX. It
  qualifies for termination only after all of these are observed together:
  - HTTP status exactly 200 and a Gateway request ID;
  - the stream client thread remains alive;
  - provider request count increased by exactly one;
  - Redis contains exactly one active slot for the ordinary key;
  - PostgreSQL has a pending reservation for that exact request with endpoint
    `/v1/responses`, provider `qualification-double`, resolved model
    `qualification-model`, `streaming=true`, and pending accounting state.
- One bounded retry is permitted only for an initial HTTP 503 with exact OpenAI
  code `redis_rate_limit_unavailable`, a terminated thread, zero provider
  forward, zero Redis slot, and no PostgreSQL reservation/ledger/reserved-
  counter change. Do not accept 503 as an active stream, retry another status,
  or retry indefinitely.
- If the prerequisites cannot be established, fail with bounded booleans,
  status, safe error code, provider delta, slot count, and reservation-present
  state. Do not print a raw body, header, key, URL, prompt, completion, or
  provider payload, and do not kill the API.

### 3. Prove interruption and documented reconciliation

- Immediately before `docker compose kill api`, recheck that the original
  thread is alive, its capture remains HTTP 200, provider delta is exactly one,
  Redis slot is one, and its correlated PostgreSQL reservation remains pending
  with the immutable route facts above. A stale earlier observation does not
  pass.
- Kill the actual API container, not a worker object or internal service.
  Restart API and NGINX and require the API readiness boundary, including
  PostgreSQL/schema and Redis, to recover before continuing.
- Prove the exact interrupted request remains pending and retained provider,
  resolved-model, endpoint, and streaming facts. Make only that disposable
  reservation expired as already documented, then invoke the real
  `slaif-gateway quota reconcile-expired-reservations` CLI path.
- Require terminal non-pending ledger/reservation state allowed by the current
  reconciliation contract, exact immutable route facts, zero PostgreSQL
  reserved counters for the key, and the existing safe audit record. Do not
  call the reconciliation service directly or rewrite current application
  behavior.
- Emit a bounded `api_termination` final JSON object with only recovery-503
  count, active status/booleans, provider delta, slot count, pending-before-
  kill boolean, restart-ready boolean, terminal reservation/accounting status,
  counters-cleared boolean, and audit-present boolean. No request ID or raw
  content belongs in this bounded object; request-ID correlation remains in
  PostgreSQL and the sanitized per-request evidence already used by the run.

### 4. Focused tests, documentation, and one fresh run

- Add focused pure-helper tests for Responses endpoint matching, wrong endpoint,
  malformed UUID rejection, valid active facts, non-200/dead-thread/missing or
  extra provider/slot facts, mismatched or non-pending reservation facts, safe
  bounded 503 recovery, and content-free bounded termination evidence.
- Append honest history to
  `docs/verification/2026-08-24-production-appliance-qualification.md`: 151-f
  proved deterministic Redis concurrency on its single run but exposed the
  same weak request-ID-only prerequisite in the API-termination phase and
  stopped without rerun.
- After implementation is frozen, run exactly one new complete no-keep
  qualification. If any phase fails, stop and publish an exact failed report;
  do not rerun the whole matrix until green.
- Mechanically parse and regex-validate the final JSON project, use that exact
  value for independent container/network/volume/runtime cleanup checks, and
  mechanically require every project token in the authored report to equal it.

## Exact allowed paths

```text
scripts/production-qualification/run.py
tests/unit/test_production_compose_contract.py
docs/verification/2026-08-24-production-appliance-qualification.md
oap/orders/151-g-active-termination-prerequisite-closure.md
oap/reports/151-g-active-termination-prerequisite-closure.md
oap/active
```

Use the narrowest subset. If the strengthened phase establishes a real active
stream but application state is absent, corrupted, or unreconcilable, stop and
report the product defect for a later continuation; do not widen this order.

## Anti-false-positive acceptance

- A request ID or ten-second reservation timeout does not establish an active
  request. HTTP 200, live thread, one provider forward, one Redis slot, and the
  exact pending PostgreSQL reservation must coexist immediately before kill.
- An HTTP 503 is only bounded zero-side-effect recovery evidence and can never
  satisfy the interruption proof.
- The actual API container is killed only after the prerequisites pass; the
  documented CLI, not direct service invocation or manual SQL finalization,
  performs reconciliation.
- PostgreSQL remains accounting truth. Redis slot evidence proves operational
  admission only and does not replace reservation/ledger/counter evidence.
- The accepted 151-f exact 429 concurrency phase passes unchanged in the new
  complete run.
- Only one post-fix no-keep run supplies final evidence. A second whole rerun,
  kept run, old run, prefix project ID, or manual cleanup does not pass.
- The report project token and all independent cleanup targets equal the final
  JSON project byte-for-byte under the same mechanical equality gate used in
  151-f.
- No provider credential value is enumerated, printed, validated, or used.
  All relevant commands explicitly unset `OPENAI_API_KEY`,
  `OPENAI_UPSTREAM_API_KEY`, `OPENROUTER_API_KEY`, and upstream-test toggles.
- All final-report-head checks succeed. CI success cannot override a failed
  composed phase or evidence mismatch.

## Required verification

```text
git diff --check
env -u OPENAI_API_KEY -u OPENAI_UPSTREAM_API_KEY -u OPENROUTER_API_KEY python -m ruff check <changed Python/tests>
env -u OPENAI_API_KEY -u OPENAI_UPSTREAM_API_KEY -u OPENROUTER_API_KEY python -m pytest <focused termination/concurrency production qualification tests> -q
env -u APP_ENV -u DATABASE_URL -u TEST_DATABASE_URL -u RUN_UPSTREAM_TESTS -u OPENAI_API_KEY -u OPENAI_UPSTREAM_API_KEY -u OPENROUTER_API_KEY ENABLE_EMAIL_DELIVERY=false .venv/bin/python scripts/production-qualification/run.py
<parse and regex-validate exact project from the single final JSON>
<independent exact container/network/volume/runtime checks using that variable>
<mechanically compare every project token in the authored report to that exact variable>
```

GitHub CI is required on the final report head. Do not run a broad local suite
merely for appearance.

## Boundaries and non-goals

- No application, accounting-service, rate-limit-service, Compose, NGINX,
  provider-adapter, route, migration, dashboard, or deployment feature change.
- No real provider, production/staging/shared database, real email, deployment,
  release, or credential-rotation work.
- No enterprise feature, endpoint expansion, module/facial work, provider or
  adapter generalization, plugin SDK, polish, penetration test, certification,
  compliance, HA, invoice, support, or SLA work.
- Preserve auth, provider-secret isolation, policy, quota, accounting, privacy,
  metrics denial, and fail-closed behavior. This remains disposable evidence,
  not production certification.

## Publication and response duties

- Commit/push bounded implementation changes on PR #286; do not merge or
  enable auto-merge.
- Publish exactly one immutable
  `oap/reports/151-g-active-termination-prerequisite-closure.md` as the sole
  path in a final report-only commit after the implementation and single run
  are frozen.
- Verify report SELF topology, exact run/report/cleanup correlation, PR state,
  and every required check; then write exactly two bytes `OK` to the response
  FIFO and resume the control FIFO.
