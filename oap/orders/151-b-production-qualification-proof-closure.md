# OAP Work Order — 151-b

PR mode: `AMEND_EXISTING_PR`
PR: `#286`
Branch: `oap/151-production-appliance-closure`
Base: `main @ ce0cf95685796477685a3aab6edacb39def6c27b`
Current remote head: `00c591fbc51e486905575d01458032f081db554e`
Title remains: `obj151: qualify production appliance boundary`

## Objective and reason

Repair the concrete proof and protocol defects found in independent strategic
review of 151-a. Keep the production wiring already implemented where it is
correct, but do not merge or describe the appliance as qualified until one
fresh no-keep run proves every missing boundary and publishes the required OAP
report on this same PR.

## Verified 151-a findings

The first implementation fixed important static defects: a real runtime image
stage, explicit file-secret loading with privilege drop, PostgreSQL persistence,
authenticated Redis and enabled fail-closed rate limiting, API egress, corrected
Celery object names, TLS/NGINX proxying, and an isolated socket provider double.
All ten workflows completed successfully on head `00c591f`.

That evidence is not sufficient because:

1. No matching `oap/reports/151-a-*` report exists. The verification document
   incorrectly labels itself `Report publication commit: SELF`; it is not in the
   immutable OAP report directory. Exact `OK` was sent despite this protocol
   defect.
2. `exercise_failures()` executes `SELECT COUNT(*) ... pending` after the
   ordinary Responses client abort but ignores the result. It never polls or
   proves the corresponding reservation/ledger terminal state.
3. No client-aborted Chat stream is exercised.
4. No active-stream concurrent-request rejection is exercised. Setting a key's
   rate-limit metadata is not concurrency evidence.
5. No API termination during an active stream is exercised, and no resulting
   pending reservation is discovered and repaired through documented
   reconciliation.
6. HTTP helpers discard response headers and request IDs. Database checks are
   aggregate counts, not per-request reservation/ledger correlation, and do not
   verify authoritative usage, cost source, streaming flag, or reserved/used
   counters for every accepted request.
7. Redis outage checks provider-call count but not before/after PostgreSQL
   reservation and ledger counts.
8. The run does not prove one admitted request crossing quota followed by
   rejection; it only lowers limits to already-used totals and rejects the next
   admission.
9. Startup waits only for NGINX and provider health. It does not assert worker
   or scheduler liveness/registered tasks. Debug runs observed worker exit 137.
   The production worker is also attached only to the internal network, which
   prevents documented external SMTP delivery when enabled.
10. The successful evidence command used `--keep`. `cleanup()` explicitly
    skips cleanup in that mode. Any later manual removal is unreported and does
    not prove the automatic no-keep cleanup contract.
11. Privacy evidence is materially tautological: media, malformed-response,
    authorization, and completion canaries are not actually sent/returned in
    the relevant paths. Full-table scans check generated canaries but not every
    generated secret; the actual gateway key is only compared against selected
    safe ledger columns. Metrics and real dashboard usage/audit views are not
    scanned.
12. The harness uses an internal `pg_dump`/`pg_restore` sequence rather than
    proving the repository's documented backup/restore operator scripts.

## Required repairs

### Per-request accounting and stream lifecycle

- Preserve gateway response headers and capture the gateway request ID for
  every normal, streaming, failed, disconnected, timeout, and outage request.
- Query PostgreSQL by that exact ID. For each accepted generation request,
  prove one matching reservation and ledger row, expected finalized/released/
  failed/interrupted/reconciled status, streaming flag, provider/model/route,
  authoritative or documented estimated token/cost source, finalized timestamp,
  key reserved/used counters, and no unexplained pending row.
- Implement both Chat and ordinary stateless Responses client disconnects over
  HTTPS NGINX with real Redis and PostgreSQL. Poll to a bounded deadline for the
  expected terminal accounting state; never issue and ignore a count query.
- Add a controllable slow stream and prove an overlapping request is rejected
  by the configured real Redis concurrency limit while the first stream is
  active, then prove the slot is released after terminal completion or abort.
- During a separate active slow stream, terminate the actual API container,
  restart API/NGINX, identify the exact interrupted request in PostgreSQL, make
  its test-only expiry deterministic if needed, invoke the documented CLI
  reconciliation path, and prove the reservation and counters are repaired with
  safe audit metadata. Do not call the repository service directly.
- Exercise one admitted bounded request whose authoritative returned usage/cost
  crosses the remaining key limit, then prove the following request is denied
  before provider forwarding. Keep the documented single-request-overrun limit
  honest; do not manufacture an exact no-overrun claim.
- For Redis stop/restart, snapshot reservation/ledger counts and key reserved
  counters before and after the denied request and prove no PostgreSQL mutation
  or provider call occurred.

### Async, operator, privacy, backup, and cleanup evidence

- Bound Celery worker concurrency so the documented 512 MiB profile remains
  alive in the qualification environment. Attach the worker to explicit egress
  as needed for the currently documented optional SMTP behavior while retaining
  the private internal network. Prove worker and Beat processes remain running;
  inspect the worker for expected registered tasks and the scheduler for the
  expected opt-in schedule state. Do not send email or enable reconciliation.
- Use the created admin through the real HTTPS NGINX dashboard session flow to
  view safe usage and audit pages after CLI setup and requests. Preserve CSRF,
  secure-cookie, and authentication behavior; do not bypass dashboard auth.
- Actually transmit unique prompt/input, provider completion/output,
  image/media-shaped rejected input, malformed provider payload, invalid client
  authorization, upstream key, and real generated gateway-key canaries through
  their relevant paths. It is expected that permitted prompt/completion content
  appears in the client/provider transport; assert that none appears in logs,
  metrics, audit/usage exports/pages, or durable database rows.
- Scan every generated secret value, including the actual generated gateway
  key, across logs and full text representations of the applicable PostgreSQL
  metadata tables. Do not count a selected-column query as a whole-database
  secret scan. Keep provider-double state content-free.
- Invoke the repository's documented `scripts/backup.sh`, `scripts/restore.sh`,
  and `scripts/verify_restore.py` flow against the disposable dataset, using a
  safe adapter/container environment if host clients are unavailable.
- Make cleanup failure fail the qualification. A final run without `--keep`
  must remove its exact containers, network, named volume, runtime directory,
  copied plaintext key, dump, logs, and secret files. After process exit, run an
  independent exact project/runtime absence check and record it. Debug `--keep`
  runs may not be cited as final acceptance.

### Evidence and protocol correction

- Correct `docs/verification/2026-08-24-production-appliance-qualification.md`
  so it no longer calls `00c591f` or itself an OAP `SELF` report and no longer
  claims evidence the old harness did not assert. Replace its run table only
  with the fresh corrected no-keep run and clearly identify superseded 151-a
  evidence.
- Publish exactly one immutable
  `oap/reports/151-b-production-qualification-proof-closure.md`. It must record
  the fresh run's sanitized per-request IDs/statuses/accounting facts, async and
  dashboard evidence, backup/restore script invocation, privacy canaries by
  category, exact automatic-cleanup proof, implementation head, and `Report
  publication commit: SELF`.
- The final report-only commit must have the recorded implementation head as its
  first parent and change only that OAP report path. Do not send `OK` before the
  report exists at the verified remote PR head.

## Exact allowed paths

```text
docker-compose.production.yml
nginx/production.conf
scripts/production-qualification/run.py
scripts/production-qualification/provider_double.py
scripts/production-qualification/qualification-compose.yml
scripts/verify_production_compose.py
tests/unit/test_production_compose_contract.py
docs/deployment-production.md
docs/deployment.md
docs/verification/2026-08-24-production-appliance-qualification.md
oap/orders/151-b-production-qualification-proof-closure.md
oap/reports/151-b-production-qualification-proof-closure.md
oap/active
```

Use the narrowest subset. No new PR. No application gateway/accounting/policy
code, migrations, dependency files, workflow, architecture, endpoint matrix,
facial module, or unrelated test may change. If a real application defect
prevents the required proof, stop with the exact reproduction and request a
151-c continuation for only the necessary path.

## Anti-false-positive acceptance

- Every accepted/failed/disconnected request in the report has an actual
  gateway request ID and exact PostgreSQL evidence; aggregate ledger counts are
  supplementary only.
- Both Chat and Responses disconnect, real-Redis concurrency, Redis outage,
  active-stream API termination/reconciliation, admitted overrun/following
  block, persistence, documented backup/restore scripts, async liveness, and
  authenticated dashboard views pass in one fresh run.
- The final command omits `--keep`, exits zero, and an independent post-exit
  check finds no exact project container/network/volume/runtime path.
- Canaries are actually exercised before their absence is claimed. The client
  response may contain expected provider output, but durable/log/metric/audit
  surfaces may not.
- Worker/scheduler process presence is not inferred from Compose creation.
- The previous verification record is corrected; a valid 151-b OAP report-only
  publication commit is the PR head at signal time.
- All final-head required checks are successful. The coding agent does not
  merge or enable auto-merge.

## Required verification

```text
git diff --check
python -m ruff check <changed Python files and focused tests>
python -m pytest tests/unit/test_production_compose_contract.py -q
python scripts/verify_production_compose.py
sudo -n docker compose -f docker-compose.production.yml config --quiet
.venv/bin/python scripts/production-qualification/run.py
<independent exact project/container/network/volume/runtime absence checks>
```

Also run focused existing tests for secret loading, auth/error redaction,
stream disconnect accounting, reconciliation, Redis failure, and backup/restore
where applicable. No real provider, email, production/staging system, broad
local suite, release, or deployment is authorized.

## Non-goals

All 151-a non-goals remain. This continuation does not add endpoints, provider
families, enterprise features, managed secrets, generic orchestration, formal
security assurance, real-provider qualification, or production certification.

## Report and publication contract

The 151-b report must state which 151-a claims were invalidated, list every
changed path and exact command/result, identify PR #286/base/branch/activation
and implementation heads, use `Report publication commit: SELF`, and contain
sanitized evidence for every acceptance item above. It must disclose any skip,
failure, retained debug project, manual cleanup, or limitation. The final
report-only commit changes only that report path. Push it, verify it as remote
PR head, then send exact two-byte `OK`. Do not merge.
