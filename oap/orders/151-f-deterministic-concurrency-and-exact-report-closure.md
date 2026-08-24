# OAP Work Order — 151-f

PR mode: `AMEND_EXISTING_PR`
PR: `#286`
Branch: `oap/151-production-appliance-closure`
Base: `main @ ce0cf95685796477685a3aab6edacb39def6c27b`
Current remote head: `958f892d767baa579ef3fa67d90fb39e82e330d3`
Title remains: `obj151: qualify production appliance boundary`

## Objective and reason

Close two independently demonstrated qualification defects without changing
Gateway feature code: make the real-Redis concurrency phase prove that its
first streamed request is admitted and actively holds the slot before testing
the overlap, and make the immutable report mechanically preserve the exact
Compose project identifier. This continues objective 151 and PR #286.

## Verified starting state and rejection provenance

- Remote `main` remains
  `ce0cf95685796477685a3aab6edacb39def6c27b`.
- PR #286 is open, mergeable, and has no auto-merge. Its remote head is the
  valid report-only 151-e commit
  `958f892d767baa579ef3fa67d90fb39e82e330d3`; its sole parent and 151-e
  implementation head is
  `87b3cfb6699d85a03d889bf5fab9fec7628bb6d3`. All required checks succeeded
  on the report head.
- The 151-e positive Prometheus sample parser, three-body dashboard privacy
  scan, bounded dashboard/metrics JSON, and exact automatic cleanup behavior
  are accepted and must be preserved.
- The first 151-e no-keep run failed the `redis-concurrency` phase in 0.17
  seconds: the alleged slow stream had an eight-second provider pause, yet the
  next request returned HTTP 200. `stream_api` populates the capture for both
  successful responses and HTTP errors, while `exercise_concurrency` waits
  only for any request ID. It does not require the first status to be 200, the
  worker thread to remain live, the provider to have received the first
  request, a Redis slot to exist, or a PostgreSQL reservation to be pending.
  A fail-closed request immediately after Redis restart can therefore satisfy
  the weak prerequisite, and the following request can be the first admitted
  request. The whole qualification was then rerun until that race happened to
  pass. This cannot count as skeptical concurrency evidence.
- The overlap currently accepts HTTP 503 as well as 429. The implemented
  concurrency-denial contract is HTTP 429 with OpenAI error code
  `concurrency_rate_limit_exceeded`; HTTP 503 means Redis rate limiting is
  unavailable and is not evidence that concurrency fencing worked.
- The successful 151-e final JSON contained exact project
  `slaif-151-4043410-43784c`. The immutable report again omitted the final
  character and claimed independent cleanup against the truncated value.
  Independent strategic checks used the actual full value and found zero
  containers, networks, volumes, and no runtime path, so cleanup occurred, but
  the report's central exact-correlation claim is false and is rejected.
- No real provider credential is authorized. The inherited credential exposed
  earlier is unusable; never enumerate, validate, print, or call with it.

## Required implementation and evidence

### 1. Deterministically establish the active first stream

- Before each bounded admission attempt, capture the qualification provider
  request count, PostgreSQL reservation/ledger/key-reserved counters for the
  concurrency key, and the real Redis concurrency-slot count for that key.
- Start the eight-second streamed Chat Completions request and wait for its
  capture. A first request qualifies as active only when all of these are
  simultaneously true:
  - HTTP status is exactly 200 and a Gateway request ID exists;
  - the client thread is still alive;
  - the provider request count increased by exactly one;
  - Redis reports exactly one active slot for the concurrency key;
  - PostgreSQL has the request's pending reservation with the expected
    endpoint, provider, resolved model, and `streaming=true` immutable facts.
- A bounded retry is allowed only for a first-attempt HTTP 503 immediately
  after the preceding Redis restart. Before retrying, require the exact safe
  OpenAI error code `redis_rate_limit_unavailable`, a terminated first thread,
  no provider forward, no Redis slot, and no PostgreSQL reservation/ledger or
  reserved-counter change for the concurrency key. Record a bounded retry
  count. Do not accept 503 as concurrency success, retry another status, or
  retry indefinitely.
- If no active first stream is established within the bounded attempts, fail
  honestly. Do not start a second whole qualification run to seek a pass.

### 2. Prove exact overlap denial and release

- Send the overlapping request only after the active-stream prerequisites
  above pass.
- Require HTTP 429 and exact OpenAI error code
  `concurrency_rate_limit_exceeded`. HTTP 200, HTTP 503, another 429 reason, a
  transport error, or an unparseable response fails.
- Prove the denied overlap did not increment provider traffic, did not create
  a new PostgreSQL reservation/ledger fact or change reserved counters, left
  the original reservation pending, left exactly one Redis slot, and left the
  original thread alive.
- Require the original stream itself to terminate at HTTP 200, then require
  terminal PostgreSQL accounting and a finalized reservation. Require the
  Redis slot to become zero before proving one following request is admitted
  at HTTP 200.
- Emit only bounded sanitized concurrency evidence in final JSON, such as the
  recovery-503 count, active status/slot boolean, exact overlap status/error
  code, provider-forward delta for the denied overlap, release-slot boolean,
  and following status. Do not emit keys, Redis key names, prompts,
  completions, raw bodies, headers, URLs, or credentials.

### 3. Focused anti-regression tests

- Add focused tests for the helper/validation logic covering:
  - a valid active first stream;
  - HTTP 503 accepted only as a bounded fail-closed recovery attempt with the
    exact error code and zero provider/accounting/slot effects;
  - rejection of a dead thread, non-200 active status, missing provider
    forward, missing/extra Redis slot, or non-pending/mismatched reservation;
  - rejection of overlap HTTP 200, HTTP 503, wrong 429 code, provider forward,
    PostgreSQL mutation, released original reservation, or dead first thread;
  - final evidence remains bounded and contains no response body or secret.
- The complete composed run is the decisive boundary test; a source-string
  assertion alone is not sufficient.

### 4. One fresh run and exact report correlation

- After the final implementation is frozen, run exactly one new complete
  no-keep qualification. The explicitly bounded in-phase Redis-recovery
  attempts above are part of that one run. If another phase fails, stop and
  report it; do not rerun the whole matrix until green.
- Parse the final JSON `project` value mechanically and validate it against
  `^slaif-151-[0-9]+-[0-9a-f]{6}$`. Use that exact variable for independent
  container-label, network-name, volume-name, and runtime-path checks.
- Publish exactly one immutable
  `oap/reports/151-f-deterministic-concurrency-and-exact-report-closure.md`.
  It must honestly record both rejected 151-e facts, the exact fresh result,
  bounded concurrency/accounting evidence, all phase results, bounded
  dashboard/metrics/restore evidence, and automatic plus independent cleanup.
- After authoring the report and before committing it, mechanically extract
  every token matching `slaif-151-[0-9]+-[0-9a-f]+` from the report. The sorted
  unique output must equal the exact final JSON project value byte-for-byte.
  The report must not contain a historical or truncated project token.
- The report commit must have the implementation head as first parent, change
  only that report path, say `Report publication commit: SELF`, be the remote
  PR head, and precede exact `OK`.

## Documentation

Append honest history to
`docs/verification/2026-08-24-production-appliance-qualification.md`: 151-e
closed the positive-metrics and privacy-body implementation gaps but its first
run exposed the weak concurrency synchronization, the run was improperly
rerun without repair, and its report again truncated the project identifier.
State the final 151-f boundary and limitations without production,
certification, provider-invoice, or release claims.

## Exact allowed paths

```text
scripts/production-qualification/run.py
tests/unit/test_production_compose_contract.py
docs/verification/2026-08-24-production-appliance-qualification.md
oap/orders/151-f-deterministic-concurrency-and-exact-report-closure.md
oap/reports/151-f-deterministic-concurrency-and-exact-report-closure.md
oap/active
```

Use the narrowest subset. If the deterministic probe reveals a product defect
requiring application, Redis service, Compose, provider, accounting, or route
code, stop and report it for strategic continuation; do not widen this order.

## Anti-false-positive acceptance

- A request ID alone never establishes the holding stream. The 200 status,
  live thread, one provider forward, one Redis slot, and pending correlated
  PostgreSQL reservation are all observed before overlap.
- Only 429 `concurrency_rate_limit_exceeded` proves overlap denial. A 503 is
  permitted solely as bounded, zero-side-effect Redis-recovery evidence before
  active-stream establishment.
- Provider and PostgreSQL evidence is captured immediately around the denied
  overlap and correlated to the concurrency key/request; global totals or a
  later terminal row do not substitute.
- One post-fix no-keep run supplies the final evidence. A previous run, a
  second whole rerun, a kept run, or manual cleanup does not pass.
- The report's project token and every independent cleanup target equal the
  final JSON project exactly. The post-authoring mechanical equality gate must
  pass before the report commit.
- No provider credential value is enumerated, printed, validated, or used.
  All relevant commands explicitly unset `OPENAI_API_KEY`,
  `OPENAI_UPSTREAM_API_KEY`, `OPENROUTER_API_KEY`, and upstream-test toggles.
- Every required check succeeds on the final report head; green CI does not
  waive any of the boundary or report-correlation conditions.

## Required verification

```text
git diff --check
env -u OPENAI_API_KEY -u OPENAI_UPSTREAM_API_KEY -u OPENROUTER_API_KEY python -m ruff check <changed Python/tests>
env -u OPENAI_API_KEY -u OPENAI_UPSTREAM_API_KEY -u OPENROUTER_API_KEY python -m pytest <focused concurrency/production qualification tests> -q
env -u APP_ENV -u DATABASE_URL -u TEST_DATABASE_URL -u RUN_UPSTREAM_TESTS -u OPENAI_API_KEY -u OPENAI_UPSTREAM_API_KEY -u OPENROUTER_API_KEY ENABLE_EMAIL_DELIVERY=false .venv/bin/python scripts/production-qualification/run.py
<parse and regex-validate exact project from the single final JSON>
<independent exact container/network/volume/runtime checks using that variable>
<mechanically compare every project token in the authored report to that exact variable>
```

GitHub CI is required at the final report head. Do not run a broad local suite
merely for appearance.

## Boundaries and non-goals

- No Gateway feature rewrite, real provider, production/staging/shared
  database, real email, deployment, release, or credential-rotation work.
- No enterprise feature, endpoint/field expansion, module/facial work,
  provider/adapter generalization, plugin SDK, dashboard polish, penetration
  test, certification, compliance, HA, invoice, support, or SLA work.
- Keep PostgreSQL authoritative and preserve auth, policy, key isolation,
  quota, accounting, privacy, metrics denial, and fail-closed behavior.
- This is disposable qualification evidence, not production certification.

## Publication and response duties

- Commit/push bounded implementation changes on PR #286; do not merge or
  enable auto-merge.
- Publish the one-file immutable report only after implementation and the
  single fresh run are frozen and all mechanical evidence checks pass.
- Verify final-report-head topology, PR state, exact report/run correlation,
  and every required check; then write exactly two bytes `OK` to the response
  FIFO and resume the control FIFO.
