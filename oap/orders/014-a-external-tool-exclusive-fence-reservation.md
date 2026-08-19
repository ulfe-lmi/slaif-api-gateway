# OAP Work Order — 014-a

## Objective

Implement the PostgreSQL-authoritative exclusive per-key external-tool fence
and full-remaining-balance reservation foundation. Prove concurrent workers,
ordinary admissions, retries, crashes, and unsafe key mutations cannot bypass
one unresolved external request. Keep provider-hosted tool forwarding disabled;
objective 015 owns accounting holds/reconciliation and objective 016 owns
selected provider execution.

## Authoritative start state

- Canonical repository: `ulfe-lmi/slaif-api-gateway`.
- Starting remote `main`:
  `72ac24d9820fef34bcf23021345c12ec8a57db34`, merge commit for PR #238.
- Objectives 012–013 are merged. Exact `external_tool_fenced` policy is durable
  and operator-visible but runtime provider-hosted tools remain denied.
- Current Alembic head is `0014_codex_context_accounting_compaction`.
- Existing PostgreSQL quota admission locks the `gateway_keys` row with
  `SELECT ... FOR UPDATE`, mutates reserved counters, and creates one
  `quota_reservations` row inside the caller transaction.
- Existing expired-reservation reconciliation can release ordinary stale
  pending reservations. It must not auto-release external-tool exposure.
- The only unrelated open PR is Dependabot #224. No objective-014 PR/branch
  existed at activation.
- PR mode: `CREATE_NEW_PR`.
- Required branch: `oap/014-external-tool-exclusive-fence-reservation`.
- Required PR title:
  `[OAP 014] Add exclusive external-tool quota fence`.
- Preserve `.local-provider-catalog/`, linked worktrees, secrets, user config,
  and unrelated artifacts.

Reconcile GitHub/governance/schema before editing and branch from current remote
`main`.

## Runtime boundary

This objective implements durable coordination and reservation only. No Chat or
Responses hosted/MCP/connector/URL-fetch request may become forwardable. Do not
call the acquisition service from hosted-tool request handlers, reconstruct
external tool bodies, or modify provider adapters. Current denial remains.

The normal runtime may and must reject a bearer/ordinary quota admission when a
durable unresolved fence already exists, including a fence left by tests or a
future worker. This is defensive enforcement, not tool enablement.

## Schema — Alembic successor 0015

Add one migration with down revision
`0014_codex_context_accounting_compaction`. Prefer fence state on the already
serialized `gateway_keys` row so the row lock is the single concurrency truth.

### `gateway_keys` fence fields

Add:

```text
external_tool_fence_state          text, not null, default 'none'
external_tool_fence_reservation_id uuid, nullable FK quota_reservations.id
external_tool_fence_request_id     text, nullable
external_tool_fence_acquired_at    timestamptz, nullable
external_tool_fence_expires_at     timestamptz, nullable
```

Allowed states are `none`, `active`, and reserved future `held`.

- `none` requires every other fence field null.
- `active`/`held` require reservation ID, request ID, acquired time, and expiry.
- request ID is bounded/safe and globally unique through the corresponding
  quota reservation.
- the reservation FK uses restrictive deletion; fence state cannot point to a
  missing reservation.
- index unresolved state/expiry for inspection.

Objective 014 sets only `none` and `active`; 015 owns transitions into/out of
`held`.

### `quota_reservations` external facts

Add:

```text
quota_mode                    text not null default 'strict_bounded'
external_tool_capabilities    jsonb not null default []
external_tool_destination_ids jsonb not null default []
```

Allowed modes are `strict_bounded` and `external_tool_fenced`. Existing rows
backfill strict with empty arrays. Strict reservations require empty external
arrays. External reservations require canonical non-empty capabilities and may
carry only canonical opaque destination IDs. Service validation remains the
primary exact-value validator; DB constraints enforce shape/non-null/mode and
safe lifecycle basics.

Do not store prompts, bodies, tool arguments/results, raw MCP values/URLs,
authorization, provider response bodies, or arbitrary metadata.

Update authoritative schema docs and all exact-head migration tests. Downgrade
must remove only these fields/constraints/indexes safely; never run a destructive
production downgrade.

## External fence service

Add a dedicated service/repository/schema boundary, e.g.
`ExternalToolFenceService`, using current key/quota/usage/audit repositories.
The service is flush-only; callers own commit/rollback.

### Atomic acquisition and reservation

Input must contain only:

- gateway key ID and unique bounded request ID;
- safe endpoint, requested model, provider and route UUID facts;
- canonical capability/destination tuples;
- the already-positive objective-012 `ExternalToolAdmissionDecision` with all
  four fenced obligations true;
- current time/TTL.

Validate all facts before mutation. Then in one transaction:

1. lock the gateway key row `FOR UPDATE`;
2. verify active/valid standard key, exact fenced stored policy, positive finite
   cost/token/request limits, and decision/policy facts;
3. if the same request ID already owns an exact matching fence/reservation,
   return it idempotently without changing counters;
4. if any other `active` or `held` fence exists, reject with fixed
   `external_tool_fence_active` before reservation/provider side effect;
5. compute remaining balances from authoritative used+reserved counters;
6. require at least one remaining request and positive remaining token/EUR
   balance;
7. reserve the complete remaining token and EUR balances plus exactly one
   request. Full-balance reservation is conservative and prevents a second
   request from multiplying the accepted single-request overrun;
8. create one pending `external_tool_fenced` quota reservation with canonical
   capability/destination snapshots;
9. increment key reserved counters exactly once;
10. set the key fence pointer/state/timestamps to that reservation.

The result DTO exposes only IDs, state, reserved numeric totals, expiry,
canonical capability/destination IDs, and idempotent/new status.

If transaction commit fails/rolls back, no fence, reservation, or counter may
remain. Never use Redis/in-memory locks as authority.

### Cross-worker ordinary blocking

Defend in both places:

- authentication must fail closed for a later bearer request when the matched
  key has `active` or `held` fence state;
- ordinary `QuotaService` reservation must recheck fence state under the locked
  key row, covering requests authenticated before another worker committed the
  fence.

Return a fixed OpenAI-shaped conflict/rate-limit error without request ID,
reservation ID, provider/tool content, or arbitrary reason. The in-flight
worker keeps its already-authenticated facts.

### Idempotency/conflicts

- Exact retry of the same request/key/route/capabilities/destinations returns
  the same fence/reservation and never increments counters twice.
- Same request ID with changed facts, another key, or terminal/conflicting
  reservation fails closed.
- Different request ID while unresolved always rejects.
- Acquisition after authoritative resolution may create a new fence only if
  normal quota limits allow it.

## Authoritative resolution foundation

Provide a narrow idempotent method to clear `active` only when durable evidence
is already authoritative:

- lock key, fence pointer and reservation in one consistent order;
- require the linked reservation to be terminal (`finalized` or `released`);
- require exactly one linked usage ledger in authoritative terminal state:
  finalized success for finalized reservation, or failed/false for released
  reservation;
- verify reserved counters have already been reconciled consistently;
- clear all key fence fields to `none` and add a safe audit event;
- repeated exact resolution is a no-op/same result, not double mutation.

Do not manufacture final usage/cost or release a pending reservation here.
Objective 015 supplies external failure/unknown-cost hold and reconciliation
transitions.

## Crash/stale behavior

Expiry is an inspection threshold, not permission to release. A committed
active fence survives process/service restart and continues blocking all later
bearer/quota admissions.

Modify stale-reservation inspection/reconciliation so external-mode pending
reservations are identified separately as requiring external-tool review and
are never automatically expired/released by the ordinary stale-reservation
path. Provide a safe read-only list/summary through the existing quota CLI or
reconciliation service with IDs/timestamps/state only. No auto-resolution.

## Key mutation safety

While a key fence is `active` or `held`, reject before mutation any operation
that could invalidate accounting or duplicate exposure, including:

- clearing/resetting used or reserved quota counters;
- changing limits, request policy, provider policy, Responses policy or
  external-tool policy;
- rotation or template replacement;
- validity changes that would invalidate the in-flight key.

Suspension/revocation may remain available as emergency admission stops, but
must not clear the fence/reservation/counters or represent accounting as
resolved. Document/test the exact behavior. Bearers cannot mutate anything.

## Verification

Add focused pure/unit and real PostgreSQL evidence:

- migration upgrade/default/backfill/constraint/FK/index/downgrade and one head;
- exact full-balance arithmetic and finite/negative/exhausted cases;
- 2-worker and at least 16-worker independent-session acquisition races: one
  winner, all others fixed rejection, one reservation/fence, exact counters;
- ordinary reservation racing before/after fence commit cannot bypass;
- exact same-request idempotency and changed-fact conflict;
- transaction rollback/commit failure leaves no partial state;
- service restart/new session sees and enforces committed fence;
- expiry never auto-releases external reservation;
- standard stale reconcile still handles ordinary reservations unchanged;
- authoritative resolve prerequisites, mismatch negatives and idempotency;
- held reserved state blocks though 014 does not create it;
- key mutations/reset/rotation behavior while fenced;
- auth/OpenAI error mapping and no-content/audit privacy;
- Redis absent/unavailable does not affect correctness.

Use one or a few dedicated focused PostgreSQL files and an explicit safe
disposable `TEST_DATABASE_URL`; tests must not skip. Do not call a provider.

## Documentation

Update schema, accounting, security, configuration, compatibility, forwarding,
reconciliation/runbook, and product-scope docs. State:

- fence/reservation foundation is implemented;
- external forwarding and unknown-cost hold are still not implemented;
- expiry never means safe release;
- PostgreSQL/key-row lock is authority, Redis is not;
- emergency suspend/revoke does not settle accounting;
- exact overrun/concurrency promise remains conditional on later provider
  activation.

## Allowed paths

Implementation may change only:

```text
AGENTS.md
app/slaif_gateway/api/dependencies.py
app/slaif_gateway/cli/quota.py
app/slaif_gateway/db/models.py
app/slaif_gateway/db/repositories/keys.py
app/slaif_gateway/db/repositories/quota.py
app/slaif_gateway/db/repositories/usage.py
app/slaif_gateway/schemas/auth.py
app/slaif_gateway/schemas/external_tool_fence.py
app/slaif_gateway/schemas/quota.py
app/slaif_gateway/schemas/reconciliation.py
app/slaif_gateway/services/auth_service.py
app/slaif_gateway/services/external_tool_fence.py
app/slaif_gateway/services/key_service.py
app/slaif_gateway/services/quota_errors.py
app/slaif_gateway/services/quota_service.py
app/slaif_gateway/services/reservation_reconciliation.py
app/slaif_gateway/workers/tasks_reconciliation.py
docs/accounting.md
docs/compatibility-matrix.md
docs/configuration.md
docs/database-schema.md
docs/product-scope.md
docs/provider-forwarding-contract.md
docs/responses-compatibility.md
docs/runbooks/stale-reservation-reconciliation.md
docs/security-model.md
migrations/versions/0015_external_tool_exclusive_fence.py
oap/active
oap/orders/014-a-external-tool-exclusive-fence-reservation.md
tests/integration/test_external_tool_fence_concurrency_postgres.py
tests/integration/test_external_tool_fence_postgres.py
tests/integration/test_gateway_key_prefix_migration_postgres.py
tests/integration/test_quota_accounting_invariants_postgres.py
tests/integration/test_reconciliation_tasks_postgres.py
tests/unit/key_management_fakes.py
tests/unit/test_alembic_accounting.py
tests/unit/test_alembic_codex_context_accounting_compaction.py
tests/unit/test_alembic_email_jobs.py
tests/unit/test_alembic_external_tool_fence.py
tests/unit/test_alembic_key_prefix_default.py
tests/unit/test_alembic_provider_pricing.py
tests/unit/test_auth_error_mapping.py
tests/unit/test_auth_service.py
tests/unit/test_documentation_contract_drift.py
tests/unit/test_external_tool_fence.py
tests/unit/test_key_management_service_limits.py
tests/unit/test_key_management_service_rotation.py
tests/unit/test_key_service_policy_update.py
tests/unit/test_key_service_safety.py
tests/unit/test_quota_service.py
tests/unit/test_cli_quota_reconciliation.py
tests/unit/test_cli_quota_reconciliation_safety.py
tests/unit/test_reconciliation_tasks.py
tests/unit/test_reservation_reconciliation_service.py
tests/unit/test_schema_status.py
tests/unit/test_v1_auth_dependency.py
```

The final report-only commit adds only:

```text
oap/reports/014-a-external-tool-exclusive-fence-reservation.md
```

If another exact path is genuinely required, do not edit it; report `BLOCKED`
for a narrow continuation. Do not modify Chat/Responses request reconstruction,
provider adapters, hosted-tool forwarding, external policy UI, DB tables beyond
the named migration/models, dependencies, CI, Compose, README, fixtures, or
prior OAP history.

## Test economy

Run only directly affected unit files and the new/adjacent focused PostgreSQL
fence/reconciliation files. The dedicated concurrency test must actually use
independent PostgreSQL sessions and pass without skip. Run scoped lint/format/
compile/docs/migration/path checks. Do not run the full local unit/integration/
E2E/browser/Docker/HPC/manual-Codex/provider suites. GitHub CI owns broad
routine coverage. No browser change exists.

## Acceptance criteria

1. PostgreSQL schema and key-row locking enforce one unresolved fence per key;
   existing rows/modes backfill strict safely.
2. Acquisition atomically reserves all remaining cost/token balance plus one
   request, sets the fence once, is exact-idempotent, and rolls back cleanly.
3. Independent concurrent workers yield exactly one winner; ordinary and
   pre-authenticated racing requests cannot bypass the committed fence.
4. Active/held fence survives restart/expiry and blocks bearer/quota admission;
   ordinary stale reconciliation never auto-releases it.
5. Resolution clears only after exact authoritative terminal reservation+ledger
   evidence and is idempotent; pending/ambiguous states remain blocked.
6. Unsafe key mutations/reset/rotation fail while fenced; emergency
   suspend/revoke does not clear accounting state.
7. Redis is irrelevant to correctness; no prompt/body/tool/credential data is
   stored or exposed; audit/CLI/error facts are safe.
8. Runtime provider-hosted forwarding remains denied and no provider call runs.
9. Focused unit/PostgreSQL/migration/docs/privacy/path evidence and every final
   GitHub check pass; broad local suites do not run.
10. One new objective-014 PR only; coding agent never merges/enables auto-merge;
    immutable report topology satisfies `SELF`.

## GitHub and report contract

Commit the unchanged order and `oap/active=014-a`, create the required PR,
inspect checks, and repair only in-scope failures. Never merge/auto-merge.

Publish exactly one immutable report at
`oap/reports/014-a-external-tool-exclusive-fence-reservation.md` with literal
implementation SHA, `Report publication commit: SELF`, schema/backfill,
full-balance arithmetic, race worker counts, idempotency/rollback/restart/
expiry/resolution/mutation/Redis/privacy evidence, actual PostgreSQL commands
and cleanup, focused/GitHub checks, broad suites not run, no-provider/no-
forwarding evidence, docs impact, and no-merge/no-auto-merge. The report-only
commit must parent the implementation head and change only that report. Verify
remote report head and required checks, then signal exact `OK`.
