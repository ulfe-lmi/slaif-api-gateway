# OAP Work Order — 151-c

PR mode: `AMEND_EXISTING_PR`
PR: `#286`
Branch: `oap/151-production-appliance-closure`
Base: `main @ ce0cf95685796477685a3aab6edacb39def6c27b`
Current remote head: `7f4bd49c5c4d4dbc0324ec5dea25486dae425611`
Title remains: `obj151: qualify production appliance boundary`

## Objective and reason

Close the two concrete blockers recorded truthfully by 151-b, plus the narrow
qualification false positives that are already visible in the unexecuted
later phases. Repair the canonical PostgreSQL restore verifier; preserve the
safe route/provider/streaming facts known at reservation time so process-crash
reconciliation does not fabricate `provider=unknown` and `streaming=false`;
then run the complete production-appliance qualification through every later
quota, dashboard, privacy, backup/restore, and automatic-cleanup phase.

This remains the same numeric objective and the same PR. Do not create another
PR, merge, enable auto-merge, or claim production certification.

## Verified starting state and blocker provenance

- Canonical remote `main` is
  `ce0cf95685796477685a3aab6edacb39def6c27b`.
- PR #286 is OPEN and mergeable from
  `oap/151-production-appliance-closure` into `main`; no auto-merge is set.
- Remote PR head is the valid 151-b report-only commit
  `7f4bd49c5c4d4dbc0324ec5dea25486dae425611`. Its first parent is the reported
  implementation head `81506538c77384f4704a27f99a582292a257af4c`, and that
  publication commit changes only
  `oap/reports/151-b-production-qualification-proof-closure.md`.
- The 151-b no-keep run `slaif-151-3605141-179932` passed prepare, TLS,
  production Compose, CLI operator setup, Celery worker/Beat liveness, normal
  and streaming Chat/Responses, failure/disconnect paths, Redis outage and
  real concurrency, API termination/CLI reconciliation, persistence, and
  exact automatic cleanup. It then failed at
  `scripts/verify_restore.py:40`, which sends SQLite-only
  `PRAGMA integrity_check` through PostgreSQL `asyncpg`.
- The exact process-killed Responses request had a committed pending
  PostgreSQL reservation and was repaired through the documented CLI, but the
  synthesized ledger row recorded `provider=unknown`, no resolved model, and
  `streaming=false` even though route resolution and the stream request shape
  were known before reservation.
- Canonical contracts require safe usage/accounting metadata to report
  endpoint, provider, requested/resolved model, streaming/interrupted state,
  and accounting status without content. `QuotaService` already receives the
  resolved route and normalized policy before it persists the reservation.
- Inspection of the not-yet-reached 151-b quota phase found three deterministic
  false-positive defects that must be repaired before citing a successful run:
  the admitted-overrun assertion compares one request's tokens with a
  cumulative limit instead of comparing authoritative cumulative counters;
  later denied requests compare provider count with the pre-overrun baseline;
  and revocation is tested while the same key is still expired, so expiry can
  mask a broken revocation path.
- The primary checkout contains unrelated user work and must remain untouched
  except for the strategic order and `oap/active` bytes. Continue in the
  existing linked worktree/branch used by PR #286.

## Required implementation

### 1. PostgreSQL-native canonical restore verification

- Repair `scripts/verify_restore.py` itself. Remove the SQLite `PRAGMA`; do not
  hide or strip it in a qualification wrapper.
- Retain its safe-target refusal. It must continue to reject a non-PostgreSQL
  URL and any database name outside the documented disposable/test naming
  boundary.
- Use PostgreSQL-native, read-only structural/readability checks. At minimum,
  prove every required table exists and is queryable. Emit bounded,
  machine-checkable structural evidence and safe row counts sufficient for the
  production qualification to compare the restored `gateway_keys` and
  `usage_ledger` dataset with the source snapshot. Do not print row content,
  credentials, connection URLs, prompts, completions, or secrets.
- Add focused tests for success, missing table, unsafe target, and PostgreSQL
  SQL shape. A mocked unit test alone does not replace the disposable
  PostgreSQL invocation in the final qualification.
- Keep `scripts/backup.sh` and `scripts/restore.sh` as the operator entrypoints;
  do not replace their proof with direct internal `pg_dump`/`pg_restore` calls.

### 2. Durable interrupted-request accounting facts

- Add one Alembic revision after current head `0023` that lets ordinary quota
  reservations snapshot the safe pre-provider facts needed after a process
  crash: selected provider, resolved model, and whether the admitted request
  is streaming. `endpoint` and `requested_model` already exist.
- Preserve semantic honesty for pre-migration and non-applicable rows. Do not
  backfill historical rows with a current route lookup, guessed provider,
  guessed resolved model, or a false non-streaming assertion. Nullable legacy
  facts or an explicit metadata-quality marker are acceptable; silent
  fabrication is not.
- Update the reservation model/repository and `QuotaService` so every new
  ordinary strict-bounded reservation stores exact `route.provider`,
  `route.resolved_model`, and the normalized policy's actual `stream` boolean
  before the provider call. This must cover ordinary Chat, Responses, Audio,
  Embeddings, Realtime admission, and fixed-request module reservations that
  use the same service without changing their policy or billing semantics.
- Do not weaken or repurpose the separate external-tool fence facts. Ordinary
  stale reconciliation must still skip `external_tool_fenced` reservations;
  hosted-tool hold semantics do not change.
- When ordinary expired-reservation reconciliation must synthesize a safe
  failure ledger, copy the persisted provider, requested/resolved model, and
  streaming facts. Use the existing honest legacy fallback only when the old
  reservation lacks those snapshots, and mark that evidence quality safely if
  needed. Do not infer from a mutable current route.
- Preserve the meaning of provider as the selected/attempted route, not proof
  that a killed process completed transport. Keep `success=false`, zero actual
  usage/cost, expired/released reservation handling, audit identity/reason,
  idempotency, and PostgreSQL counter repair unchanged.
- Add focused unit and real-PostgreSQL tests proving snapshot creation,
  migration behavior, exact metadata on synthesized crash ledgers, legacy
  fallback honesty, idempotency, counter repair, and continued external-fence
  exclusion. No content may be added to either reservation or ledger.

### 3. Qualification correctness and completion

- Extend the exact PostgreSQL evidence query/report to include persisted
  provider, requested/resolved model, and streaming facts. The process-killed
  Responses request must finish as failed/expired with provider
  `qualification-double`, resolved model `qualification-model`, and
  `streaming=true`; `unknown`/`false` does not pass for this newly created row.
- After backup and restore, compare safe source and restored table counts and
  require the repaired canonical verifier to exit zero. Merely printing
  `RESULT=OK` without querying the restored PostgreSQL database does not pass.
- Correct admitted-overrun arithmetic: use authoritative cumulative key
  counters before/after the admitted request to prove the configured remaining
  limit was crossed, correlate that request's ledger, and prove the immediately
  following request was denied without another provider call.
- Capture the provider-call baseline immediately before each later token,
  cost, request, expiry, and revocation denial. An earlier baseline that is
  invalidated by the admitted overrun is not evidence.
- Prove expiry and revocation independently. Restore a valid future expiry (or
  use an independently valid key) before revocation, execute revocation through
  the real CLI, then prove that otherwise-valid revoked key is denied before
  provider forwarding.
- Preserve bounded application-level Redis recovery polling. Container health
  alone is not client readiness; transient fail-closed 502/503/504 responses
  may be retried only to a fixed deadline, after which an exact 200 is required.
- Run every phase in one fresh final invocation without `--keep`: all defining
  normal/failure/streaming/accounting/concurrency/restart/reconciliation,
  persistence, documented backup/restore/verification, privacy-input, admitted
  overrun and key lifecycle, authenticated dashboard usage/audit, full
  privacy/secret scan, and automatic cleanup phases must report `OK`.
- Independently prove after process exit that the exact Compose project has no
  containers, networks, or volumes and its exact runtime directory, dump,
  plaintext copied keys, logs, and generated secret files are absent.

### 4. Documentation and immutable evidence

- Replace the blocked verification record only after a fresh complete run.
  Preserve the history that 151-a evidence was invalid and 151-b was blocked;
  do not rewrite those facts as if the failed runs passed.
- Document the new reservation snapshot fields and the distinction between
  selected provider identity and confirmed provider completion. Keep all
  invoice-grade, production-readiness, compliance, penetration-test, HA/SLA,
  and exact no-overrun disclaimers.
- Publish exactly one immutable
  `oap/reports/151-c-restore-and-interrupted-accounting-closure.md` in a final
  report-only commit. It must record the exact final implementation head,
  migration head, sanitized per-request accounting evidence, restore counts,
  overrun/following-block evidence, independent expiry and revocation evidence,
  dashboard/privacy evidence, and automatic plus independent cleanup proof.
- The report publication commit must have the reported implementation head as
  its first parent, change only that 151-c report path, say `Report publication
  commit: SELF`, be pushed as PR #286's remote head, and precede exact `OK`.

## Exact allowed paths

```text
app/slaif_gateway/db/models.py
app/slaif_gateway/db/repositories/quota.py
app/slaif_gateway/services/quota_service.py
app/slaif_gateway/services/reservation_reconciliation.py
migrations/versions/0024_quota_reservation_accounting_facts.py
scripts/verify_restore.py
scripts/production-qualification/run.py
scripts/production-qualification/provider_double.py
scripts/production-qualification/qualification-compose.yml
docker-compose.production.yml
scripts/verify_production_compose.py
tests/unit/test_quota_service.py
tests/unit/test_reservation_reconciliation_service.py
tests/unit/test_production_compose_contract.py
tests/unit/test_verify_restore.py
tests/integration/test_quota_reservation_postgres.py
tests/integration/test_reservation_reconciliation_postgres.py
tests/integration/test_reconciliation_tasks_postgres.py
tests/integration/test_external_tool_fence_postgres.py
docs/backup-restore.md
docs/database-schema.md
docs/security-model.md
docs/deployment-production.md
docs/deployment.md
docs/verification/2026-08-24-production-appliance-qualification.md
oap/orders/151-c-restore-and-interrupted-accounting-closure.md
oap/reports/151-c-restore-and-interrupted-accounting-closure.md
oap/active
```

Use the narrowest subset. If the migration filename must differ to satisfy the
actual repository revision convention, use exactly one `0024` revision and
record the path. Do not change endpoint matrices, provider adapters, policy
admission, pricing, external-tool behavior, module/facial code, dependency
files, workflows, release files, or unrelated tests. Any new application
defect discovered by the full run remains a 151 continuation on this PR.

## Anti-false-positive acceptance

- `scripts/verify_restore.py` executes successfully against restored disposable
  PostgreSQL and contains no SQLite statement or swallowed database exception.
- Restored-table evidence is derived from the restored database and correlated
  with a pre-backup source snapshot; table-existence mocks are supplementary.
- The new process-killed request's reservation is visible as pending before API
  kill. After documented CLI reconciliation, its ledger has exact selected
  provider/resolved-model/streaming facts from the immutable reservation
  snapshot, not a current route lookup.
- Migration upgrade creates the fields once, current Alembic head is singular,
  real PostgreSQL tests pass, and downgrade is structurally valid where the
  repository migration policy tests downgrades. Historical unknown facts are
  not rewritten as known.
- The admitted request is actually sent with remaining quota below its
  authoritative returned usage; cumulative used counters cross the limit; the
  next request is rejected and provider count does not increment.
- Each other denied control has its own immediate provider baseline. Revocation
  is not masked by expiry or another exhausted quota dimension.
- Dashboard proof uses the real HTTPS NGINX login/CSRF/secure-session path and
  reads usage and audit pages. Privacy proof scans logs, metrics, dashboard
  bodies, provider state, and full text representations of applicable metadata
  tables for every actually exercised canary and generated secret.
- The complete final no-keep command exits zero. Debug/failed runs, manual
  cleanup, phase output without assertions, aggregate counts without exact
  request IDs, and direct service calls do not pass.
- All required checks on the final report head are successful before strategic
  merge. The coding agent does not merge or enable auto-merge.

## Required verification

```text
git diff --check
python -m ruff check <all changed Python files and focused tests>
python -m pytest tests/unit/test_verify_restore.py tests/unit/test_quota_service.py tests/unit/test_reservation_reconciliation_service.py tests/unit/test_production_compose_contract.py -q
TEST_DATABASE_URL=<disposable objective-owned PostgreSQL URL> python -m pytest tests/integration/test_quota_reservation_postgres.py tests/integration/test_reservation_reconciliation_postgres.py tests/integration/test_reconciliation_tasks_postgres.py -q
TEST_DATABASE_URL=<disposable objective-owned PostgreSQL URL> python -m pytest <focused external-tool-fence regression tests> -q
python scripts/verify_production_compose.py
sudo -n docker compose -f docker-compose.production.yml config --quiet
alembic heads
.venv/bin/python scripts/production-qualification/run.py
<independent exact project/container/network/volume/runtime absence checks>
```

Use the production qualification's disposable PostgreSQL/Redis/Compose
environment where practical rather than connecting to any inherited database.
Do not run a broad local suite merely for appearance; routine broad coverage is
GitHub CI. A final phase-boundary run is explicitly required here.

## Security, privacy, accounting, and production boundaries

- No real OpenAI/OpenRouter/native provider credential or request is authorized.
- No production, staging, shared, inherited, or remotely managed database,
  Redis, SMTP, TLS endpoint, or deployment may be touched.
- No real email, webhook, release, tag, package publish, deployment, or external
  side effect is authorized.
- Preserve gateway-key hashes, provider-secret substitution, file-secret
  permissions, least-privilege production processes, fail-closed unknowns,
  PostgreSQL accounting authority, Redis acceleration-only semantics, and
  default no-content storage.
- Route/provider/model/streaming snapshots are safe low-cardinality metadata.
  Never store request bodies, prompts, completions, media, tool payloads,
  provider bodies, headers, URLs with secrets, or plaintext credentials in the
  new reservation fields, ledger, logs, docs, or report.

## Non-goals

All 151-a/151-b non-goals remain. This continuation does not add endpoints,
provider families, hosted tools, generic plugin/module SDKs, generic route
history, invoice billing, enterprise tenancy, SSO/SCIM/MFA/RBAC expansion,
Kubernetes/HA, formal penetration testing, compliance/certification, a release,
real-provider qualification, or production deployment. It does not make the
post-MVP facial-scoring extension part of the original Gateway MVP.

## Report and publication contract

The 151-c report must list every changed path and exact command/result, identify
PR #286/base/branch/starting head/implementation head, include the migration
and rollback evidence, disclose every failed precursor run and any remaining
limitation, and contain only sanitized IDs/counters/statuses. The final
report-only commit changes only the 151-c report, is pushed and verified as the
remote PR head, and then the coding agent sends exactly two bytes `OK`. Do not
merge.
