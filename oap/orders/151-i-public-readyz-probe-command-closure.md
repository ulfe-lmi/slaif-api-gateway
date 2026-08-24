# OAP Work Order — 151-i

PR mode: `AMEND_EXISTING_PR`
PR: `#286`
Branch: `oap/151-production-appliance-closure`
Base: `main @ ce0cf95685796477685a3aab6edacb39def6c27b`
Current remote head: `638760f59da1830154b46415a2708074b437dfaa`
Title remains: `obj151: qualify production appliance boundary`

## Objective and reason

Repair only the qualification-only public `/readyz` denial probe command that
151-h proved incompatible with the installed Docker Compose CLI, then execute
one fresh complete no-keep production qualification. Preserve the accepted
151-h loopback readiness implementation and all earlier production, accounting,
privacy, concurrency, restore, dashboard, metrics, and interruption behavior.

## Verified starting state

- Remote `main` remains
  `ce0cf95685796477685a3aab6edacb39def6c27b`.
- PR #286 is open, mergeable, and has no auto-merge. Remote head
  `638760f59da1830154b46415a2708074b437dfaa` is a valid report-only commit;
  its sole parent and 151-h implementation head is
  `3ca2df52b1eb342e1369eedb42c21df0e07db74c`. Every final-head check passed.
- The single 151-h no-keep run used exact project
  `slaif-151-29395-ad93ea`. Initial loopback API `/readyz` passed four
  consecutive exact 200 observations with database, schema, Redis, and
  provider-secret readiness. The run then failed in `compose` because the
  harness invoked unsupported `docker compose run --network`. It did not
  accept public-denial evidence or reach later phases. Automatic and
  independent exact-project cleanup both found zero residual state. No rerun
  occurred; preserve the immutable failed report.
- No real provider credential is authorized. The inherited exposed credential
  remains unusable; never enumerate, validate, print, or call with it.

## Required implementation

### 1. Compatible non-allowlisted public probe

- Remove the unsupported Compose `run --network` invocation. Do not weaken the
  public denial assertion, probe from the host/loopback, or alter NGINX.
- Identify the already-running NGINX and provider-double containers only from
  this exact Compose project (`compose ps -q nginx` and `provider-double`), and
  fail on missing or ambiguous identity.
- Create a disposable named bridge on a fixed non-allowlisted benchmarking
  subnet within `198.18.0.0/15`. Connect both exact containers to it with raw,
  supported Docker network commands. Inspect the network and require both
  assigned IPv4 addresses to belong to that subnet; do not infer source
  isolation from the requested subnet alone.
- Execute the HTTPS probe from the connected provider-double container using
  its existing Python runtime and the NGINX container's inspected probe-network
  address. Require exact HTTP 403 or 404. A connection error, zero status,
  HTTP 200, host request, default-network address, or uninspected address fails.
- Always disconnect both exact containers and remove the disposable network in
  `finally`, including command, parse, HTTP, and assertion failures. Do not pull
  an image, create an untracked helper container, or leave cleanup dependent on
  Compose project labels.
- Emit only the existing bounded `public_denied=true` final fact. Do not emit
  container IDs/names, network name, IP addresses, URLs, response bodies,
  certificates, headers, or command output in successful final JSON.

### 2. Focused regression checks and documentation

- Add focused tests or pure-helper assertions for exact single container
  identity, inspected `198.18.0.0/15` membership, 403/404-only acceptance, and
  bounded evidence. Tests must make the old Compose `--network` command shape
  impossible to reintroduce unnoticed.
- Before freezing, verify the installed CLI supports every raw Docker command
  shape used by the replacement. This is a compatibility preflight, not a
  substitute for the real composed probe.
- Append to the canonical qualification document that 151-h stopped before
  public-denial evidence because Compose rejected `--network`; make no claim
  that its initial readiness observation qualified the remaining lifecycle.

### 3. One fresh complete qualification and report

- Freeze and push the implementation, then run exactly one new complete
  no-keep qualification. If any phase fails, stop and publish that exact result;
  do not rerun the whole matrix until green.
- The run must prove all 151-h readiness checkpoints: initial startup, exact
  public denial, Redis 503 `not_ready`/`redis=error`, four-success Redis
  recovery, API restart, API recreation, and PostgreSQL/API recreation.
- It must prove the post-kill client thread terminated before restart and the
  provider count remained exactly baseline plus one through restart, while all
  previously accepted 151-g accounting/reconciliation and 151-f concurrency
  invariants continue to pass.
- Mechanically parse and regex-validate the final JSON project, use that exact
  token for independent container/network/volume/runtime checks, and require
  every project token in the report to equal it byte-for-byte.
- Publish exactly one immutable
  `oap/reports/151-i-public-readyz-probe-command-closure.md` as the sole path in
  a final report-only commit. Record the bounded complete result and honest
  limitations.

## Exact allowed paths

```text
scripts/production-qualification/run.py
tests/unit/test_production_compose_contract.py
docs/verification/2026-08-24-production-appliance-qualification.md
oap/orders/151-i-public-readyz-probe-command-closure.md
oap/reports/151-i-public-readyz-probe-command-closure.md
oap/active
```

Use the narrowest subset. If the compatible probe exposes a product/NGINX
defect or another lifecycle phase fails, stop and report for strategic
continuation; do not widen this command-compatibility round.

## Anti-false-positive acceptance

- The unsupported `docker compose run --network` shape is absent from the
  executable path. Green unit tests cannot substitute for the real probe.
- Both exact project containers are visibly attached to the isolated subnet at
  probe time; the destination address is mechanically derived from that
  network inspection. Merely creating a network or trusting an alias fails.
- Only observed 403/404 passes public denial. Transport failure and HTTP 200 do
  not pass.
- Loopback `/readyz` remains the application readiness source; public NGINX
  remains denied. No health check or direct dependency ping substitutes.
- Four consecutive exact ready observations remain required after every named
  startup/recovery event, with reset on failure.
- PostgreSQL remains accounting truth. All exact reservation, ledger, counter,
  immutable-route, audit, concurrency, and interruption assertions remain.
- One post-fix no-keep run supplies evidence. No rerun, kept run, historical
  result, manually cleaned project, prefix ID, or truncated token passes.
- Explicitly unset `OPENAI_API_KEY`, `OPENAI_UPSTREAM_API_KEY`,
  `OPENROUTER_API_KEY`, and upstream-test toggles for every relevant command.
- Every final-report-head check succeeds; CI cannot override failed runtime or
  evidence assertions.

## Required verification

```text
git diff --check
docker network connect --help
docker exec --help
env -u OPENAI_API_KEY -u OPENAI_UPSTREAM_API_KEY -u OPENROUTER_API_KEY python -m ruff check <changed Python/tests>
env -u OPENAI_API_KEY -u OPENAI_UPSTREAM_API_KEY -u OPENROUTER_API_KEY python -m pytest <focused production qualification tests> -q
env -u APP_ENV -u DATABASE_URL -u TEST_DATABASE_URL -u RUN_UPSTREAM_TESTS -u OPENAI_API_KEY -u OPENAI_UPSTREAM_API_KEY -u OPENROUTER_API_KEY ENABLE_EMAIL_DELIVERY=false .venv/bin/python scripts/production-qualification/run.py
<parse and regex-validate the exact final project>
<independent exact cleanup checks using only that variable>
<mechanically compare every report project token to that exact variable>
```

GitHub CI is required on the final report head. Do not run a broad local suite
merely for appearance.

## Boundaries and non-goals

- No application, readiness route, NGINX, Compose, accounting, rate-limit,
  provider adapter, migration, dashboard, or deployment feature change.
- No real provider, production/staging/shared database, real email, deployment,
  release, or credential-rotation work.
- No enterprise, endpoint, module/facial, provider-generalization, plugin SDK,
  polish, penetration-test, certification, compliance, HA, invoice, support, or
  SLA work.
- This remains disposable qualification evidence, not production
  certification.

## Publication and response duties

- Commit/push bounded implementation changes on PR #286; do not merge or enable
  auto-merge.
- Publish the one-file immutable report only after the implementation and the
  single fresh run are frozen and mechanically correlated.
- Verify report SELF topology, exact cleanup/run/report identity, PR state, and
  every required check; then write exactly two bytes `OK` to the response FIFO
  and resume the control FIFO.
