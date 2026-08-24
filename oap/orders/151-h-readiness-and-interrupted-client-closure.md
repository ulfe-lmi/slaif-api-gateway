# OAP Work Order — 151-h

PR mode: `AMEND_EXISTING_PR`
PR: `#286`
Branch: `oap/151-production-appliance-closure`
Base: `main @ ce0cf95685796477685a3aab6edacb39def6c27b`
Current remote head: `033ef4c3402338f7224533d400cd4d2ae5578b3b`
Title remains: `obj151: qualify production appliance boundary`

## Objective and reason

Close the final two production-qualification evidence omissions: exercise the
real API `/readyz` boundary across initial startup, Redis outage/recovery, API
restart, and API/PostgreSQL recreation; and prove that the active Responses
client thread terminates after the real API container kill. Preserve all 151-g
accounting, reconciliation, concurrency, privacy, restore, dashboard, metrics,
and cleanup behavior. This is the same objective and PR, with no product-code
change.

## Verified starting state and rejection provenance

- Remote `main` remains
  `ce0cf95685796477685a3aab6edacb39def6c27b`.
- PR #286 is open and mergeable with no auto-merge. Remote head
  `033ef4c3402338f7224533d400cd4d2ae5578b3b` is a valid report-only commit;
  its sole parent and 151-g implementation head is
  `cb404b495d14b63fcf51ef6a2099fe55cb17b2ee`. All required checks succeeded
  on the report head.
- The single 151-g no-keep run passed all 16 phases. Its exact project/report
  token and automatic/independent cleanup match. It proved deterministic Chat
  concurrency and a live HTTP-200 Responses stream with one provider forward,
  one Redis slot, and a pending correlated PostgreSQL reservation immediately
  before the real API container kill. Documented CLI reconciliation produced
  terminal `expired/failed` state with immutable route facts, cleared counters,
  and audit evidence. Preserve these accepted results.
- The 151-g order explicitly required the API readiness boundary, including
  PostgreSQL/schema and Redis, after restart. The frozen implementation instead
  waits for public HTTPS `/healthz`, directly pings the Redis container, and
  then sets `restart_ready=true`. Its report accurately describes those weaker
  checks. No production qualification path calls API `/readyz`, so the current
  evidence does not prove the application process sees current schema and
  Redis state at startup/recovery.
- After `docker compose kill api`, the harness calls `thread.join(timeout=15)`
  but never checks `thread.is_alive()`, response termination, or provider-count
  stability. It proves the client was alive before kill, not that the
  interrupted transport actually terminated afterward.
- No real provider credential is authorized. The inherited exposed credential
  remains unusable; never enumerate, validate, print, or call with it.

## Required implementation and evidence

### 1. Exact API readiness verifier

- Add a small qualification-only helper that requests the loopback diagnostic
  API at `http://127.0.0.1:<diagnostic-port>/readyz`, captures the actual HTTP
  status and JSON object, and returns only bounded readiness fields. Do not
  treat `<500`, a transport connection, `/healthz`, Docker health, or a direct
  dependency ping as readiness.
- A ready observation requires HTTP 200 and exact body facts
  `status=ok`, `database=ok`, `schema=ok`, and `redis=ok`. If a
  `provider_secrets` field is present it must not be `missing`; never emit
  missing environment names or free-form details.
- Require at least four consecutive exact-ready observations after each
  startup/recovery event, resetting the consecutive count on any non-ready
  response. This is a bounded multi-worker stability probe, not a single lucky
  worker response.
- Before operator traffic, prove initial API readiness after migrations and
  production Compose startup.
- Verify public HTTPS NGINX does not expose `/readyz`: only an exact bounded
  403/404 denial passes. The diagnostic body must remain loopback-only.

### 2. Readiness during dependency and process lifecycle

- While the actual Redis container is stopped, require loopback `/readyz` to
  return HTTP 503 with bounded facts `status=not_ready` and `redis=error`.
  Preserve the existing denied generation request, zero provider forward, and
  unchanged key-scoped PostgreSQL accounting proof.
- After Redis restart, require four consecutive exact-ready API observations
  before the existing recovered generation request. A direct `redis-cli PING`
  may remain a supplementary container check but cannot set readiness true.
- After the active-stream API kill and API/NGINX restart, require four
  consecutive exact-ready observations before recording `restart_ready=true`
  or reconciling the interrupted request.
- After API recreation and after PostgreSQL/API recreation with the named
  volume, require the same exact-ready sequence before persistence assertions.
- Emit one bounded `readiness` final JSON object with only integer statuses,
  exact low-cardinality state strings/booleans, consecutive-success counts,
  and public-denial boolean for: initial startup, Redis outage, Redis recovery,
  API restart, API recreation, and PostgreSQL/API recreation. Never emit the
  raw readiness body, URLs, schema revisions, missing variable names, keys, or
  other settings.

### 3. Interrupted client and provider terminal proof

- Immediately after killing the actual API container, join the active client
  thread to the existing bounded deadline and require that it is no longer
  alive before restarting API/NGINX. A lingering client thread fails the phase.
- Require the provider request count to remain exactly the established
  baseline plus one across kill and restart; the interruption path must not
  duplicate/retry provider transport.
- Preserve the exact request-ID-correlated pending reservation and immutable
  endpoint/provider/model/streaming facts before reconciliation, and all
  existing terminal accounting, counter, and audit assertions afterward.
- Extend bounded `api_termination` evidence with only
  `client_thread_terminated_after_kill` and
  `provider_count_stable_after_kill` booleans (or exact equivalents). Keep the
  pre-kill live-thread fact distinct. Do not emit thread errors, response/body
  fragments, request IDs, headers, or URLs.

### 4. Focused tests and honest documentation

- Add focused tests for exact ready/not-ready parsing, wrong status/body facts,
  malformed/non-object bodies, provider-secret missing rejection, consecutive
  success reset/threshold behavior, bounded readiness evidence, and the two
  new interrupted-client booleans.
- Preserve existing UUID, active-stream, recovery-503, exact-overlap, metrics,
  secret-loader, and production-contract tests.
- Append to
  `docs/verification/2026-08-24-production-appliance-qualification.md` that
  151-g passed the complete matrix and active termination correlation, but
  strategic review rejected `/healthz` plus direct Redis ping as proof of API
  readiness and found no post-kill client-thread terminal assertion.

### 5. One final no-rerun qualification and report

- Freeze the implementation, then run exactly one new complete no-keep
  qualification. If any phase or readiness observation fails, stop and publish
  that exact failure; do not rerun the whole matrix until green.
- Mechanically parse and regex-validate the final JSON project, use the exact
  value for independent container/network/volume/runtime checks, and require
  every project token in the report to equal it byte-for-byte.
- Publish exactly one immutable
  `oap/reports/151-h-readiness-and-interrupted-client-closure.md` as the sole
  path in a final report-only commit. Record bounded readiness, interrupted-
  client, concurrency, accounting/reconciliation, restore, dashboard, metrics,
  privacy, phase, and exact cleanup evidence with honest limitations.

## Exact allowed paths

```text
scripts/production-qualification/run.py
tests/unit/test_production_compose_contract.py
docs/verification/2026-08-24-production-appliance-qualification.md
oap/orders/151-h-readiness-and-interrupted-client-closure.md
oap/reports/151-h-readiness-and-interrupted-client-closure.md
oap/active
```

Use the narrowest subset. If real `/readyz` or post-kill behavior reveals a
product/deployment defect, stop and report it for strategic continuation; do
not widen this evidence-only order.

## Anti-false-positive acceptance

- `/healthz`, Docker health, direct PostgreSQL SQL, direct Redis PING, or later
  successful traffic cannot substitute for exact API `/readyz` observations.
- One ready response cannot establish stable recovery. Four consecutive exact
  observations are required after each named event, with reset on failure.
- Public NGINX `/readyz` must remain denied while loopback diagnostic readiness
  succeeds; exposing it to make the test pass fails the objective.
- The pre-kill thread-alive assertion and post-kill thread-terminated assertion
  are both required and represented separately.
- The provider count is correlated around the same interrupted request and
  remains exactly one forward; global historical provider traffic is not used
  as a substitute.
- PostgreSQL remains accounting truth. Readiness and Redis observations do not
  replace reservation, ledger, counter, immutable-route, or audit assertions.
- The exact 151-f/151-g concurrency and termination phases pass unchanged
  except for the stronger readiness/client-terminal checks.
- One post-fix no-keep run supplies evidence. No whole rerun, kept run, old
  run, manually cleaned project, prefix ID, or truncated report token passes.
- No provider credential is enumerated, printed, validated, or used. Explicitly
  unset `OPENAI_API_KEY`, `OPENAI_UPSTREAM_API_KEY`,
  `OPENROUTER_API_KEY`, and upstream-test toggles for every relevant command.
- Every final-report-head check succeeds. CI cannot override a failed phase,
  weak readiness observation, lingering client thread, or evidence mismatch.

## Required verification

```text
git diff --check
env -u OPENAI_API_KEY -u OPENAI_UPSTREAM_API_KEY -u OPENROUTER_API_KEY python -m ruff check <changed Python/tests>
env -u OPENAI_API_KEY -u OPENAI_UPSTREAM_API_KEY -u OPENROUTER_API_KEY python -m pytest <focused readiness/termination/concurrency production qualification tests> -q
env -u APP_ENV -u DATABASE_URL -u TEST_DATABASE_URL -u RUN_UPSTREAM_TESTS -u OPENAI_API_KEY -u OPENAI_UPSTREAM_API_KEY -u OPENROUTER_API_KEY ENABLE_EMAIL_DELIVERY=false .venv/bin/python scripts/production-qualification/run.py
<parse and regex-validate exact project from the single final JSON>
<independent exact container/network/volume/runtime checks using that variable>
<mechanically compare every project token in the authored report to that exact variable>
```

GitHub CI is required on the final report head. Do not run a broad local suite
merely for appearance.

## Boundaries and non-goals

- No application, health/readiness route, accounting service, rate-limit
  service, Compose, NGINX, provider adapter, migration, dashboard, or
  deployment feature change.
- No real provider, production/staging/shared database, real email, deployment,
  release, or credential-rotation work.
- No enterprise work, endpoint expansion, module/facial work, provider/adapter
  generalization, plugin SDK, polish, penetration test, certification,
  compliance, HA, invoice, support, or SLA work.
- Preserve auth, provider-secret isolation, policy, quota, accounting, privacy,
  diagnostic exposure, and fail-closed behavior. This is disposable evidence,
  not production certification.

## Publication and response duties

- Commit/push bounded implementation changes on PR #286; do not merge or
  enable auto-merge.
- Publish the one-file immutable report only after implementation and the
  single fresh run are frozen and mechanically correlated.
- Verify report SELF topology, exact cleanup/run/report identity, PR state, and
  every required check; then write exactly two bytes `OK` to the response FIFO
  and resume the control FIFO.
