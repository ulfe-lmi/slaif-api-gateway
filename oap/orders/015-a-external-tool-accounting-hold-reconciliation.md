# OAP Work Order — 015-a

## Objective

Implement the durable unknown/ambiguous-cost accounting hold and explicit
operator reconciliation foundation for provider-hosted external-tool requests.
Use the merged objective-014 exclusive fence and existing reservation/ledger
schema: ambiguous completion moves `active` to `held`, keeps the full-balance
reservation and counters untouched, and records one content-free safe ledger.
Only an audited manual reconciliation may finalize authoritative actual usage
or explicitly confirm no charge and release. No provider forwarding is enabled
in this objective.

## Authoritative start state

- Canonical repository: `ulfe-lmi/slaif-api-gateway`.
- Starting remote `main`:
  `ef3fdb8ce37381327ebf784b141ab9f7d5f75729`, merge commit for PR #239.
- Objective 014 is merged with one PostgreSQL-authoritative exclusive key
  fence, exact provider/route-bound full-balance reservation, active/held
  blocking, reservation→key lifecycle locking, stale auto-release exclusion,
  exact terminal evidence clearing, and focused concurrency proof.
- Current Alembic head: `0015_external_tool_exclusive_fence`.
- Existing durable fields are sufficient; this objective must not add a
  migration or new database column. Durable hold truth is the combination of:
  held key fence + pending `external_tool_fenced` reservation + exactly one
  linked safe hold ledger.
- Existing usage-ledger accounting statuses include `estimated`,
  `interrupted`, `finalized`, and `failed`.
- Existing ordinary stale reconciliation skips external-tool reservations.
- Existing scheduled reconciliation inspection, metrics, and optional alert
  webhook cover expired and provider-completed backlogs; extend inspection for
  holds, but never schedule automatic hold mutation.
- The only unrelated open PR is Dependabot #224. No objective-015 PR or branch
  exists.
- PR mode: `CREATE_NEW_PR`.
- Required branch: `oap/015-external-tool-accounting-hold-reconciliation`.
- Required PR title:
  `[OAP 015] Add external-tool accounting holds and reconciliation`.
- Preserve `.local-provider-catalog/`, linked worktrees, secrets, user config,
  and unrelated artifacts.

Reconcile these named facts once, branch from current remote `main`, then start
implementing. GitHub is software truth.

## Execution discipline — action first

Do not enter a reconnaissance loop.

1. Read this order and the named fence/usage repositories once.
2. First create `schemas/external_tool_hold.py` and
   `services/external_tool_hold.py` with the pure validation/state contract.
3. Add the focused unit file and make the first hold/idempotency slice pass.
4. Add PostgreSQL reconciliation/concurrency slices.
5. Add CLI and inspection/alert integration last.

Read another file only for a concrete missing symbol or failing focused test.
Do not repeat repository/environment/migration/test discovery. Work in small
edit → focused-test slices. Do not run a full local suite.

## No-migration state contract

Define and document this exact durable matrix:

```text
key fence  reservation                         ledger
active     external_tool_fenced + pending      absent        in flight
held       external_tool_fenced + pending      estimated or interrupted
                                                           unresolved hold
active     finalized                           finalized     terminal charge,
                                                           awaiting exact clear
active     released                            failed        confirmed no charge,
                                                           awaiting exact clear
none       finalized or released               terminal      reconciled/cleared
```

`held` expiry is inspection age only. It never authorizes release. Ordinary
stale reconciliation must continue to skip it.

Use a versioned safe object inside `usage_ledger.response_metadata`, for
example `external_tool_accounting_hold`, containing only bounded facts:

```text
version = 1
state = held
reason_code = one canonical enum value
needs_reconciliation = true
evidence_quality = missing | partial_estimate | ambiguous
held_at timestamp
```

Allowed reason codes must be a closed enum covering at least missing final
usage, missing final cost, ambiguous final cost, interruption/disconnect, and
provider error with unknown charge. Optional known partial total tokens and
estimated EUR cost belong in typed ledger columns, not arbitrary metadata.

Never store raw provider/tool bodies, prompts, responses, tool arguments/
results, MCP values/URLs, authorization, credentials, chain of thought,
provider diagnostics, or arbitrary operator evidence.

## Hold placement service

Add a flush-only `ExternalToolAccountingHoldService`; caller owns transaction
commit/rollback. Inputs contain only reservation/key/request IDs, canonical
reason/evidence quality, optional safe non-negative partial total-token and
estimated-EUR facts, streaming boolean, current time, and no content.

Use reservation→key locking:

1. validate every input before mutation;
2. lock reservation `FOR UPDATE`, then key `FOR UPDATE` with fresh state;
3. require matching key/request, `external_tool_fenced`, pending reservation,
   active fence with exact pointer, provider/route/endpoint/model facts, and
   full reservation counters still present;
4. require zero existing ledgers for a new hold;
5. create exactly one linked ledger with the reservation request ID, safe
   provider/endpoint/model facts, `success=None`, actual cost null, usage_raw
   empty, and:
   - `estimated` only when an explicit partial estimate is supplied;
   - otherwise `interrupted`;
6. transition the key fence `active -> held` without changing reservation or
   any used/reserved counter;
7. append safe `external_tool_accounting_hold_created` audit metadata;
8. return a safe projection only.

Exact retry against an already-held key/ledger returns idempotently when every
safe fact agrees. Missing/multiple/mismatched ledger, changed reason/estimate,
terminal reservation, wrong key/route/provider, or non-held conflicting state
fails closed without mutation. Rollback leaves the original active fence and
no ledger/audit.

This service is callable foundation for objective 016; do not wire it into Chat
or Responses handlers in 015.

## Manual hold reconciliation

Provide safe list/dry-run/execute service and CLI paths. No dashboard mutation
and no scheduled automatic execution in this objective.

### Candidate listing

List only exact held shapes: held fence, matching pending fenced reservation,
and one linked ledger whose versioned metadata says `needs_reconciliation=true`.
Projection may include UUIDs, request ID, reason/evidence state, provider,
requested model, endpoint, held/created/expiry timestamps, reserved totals,
known partial total tokens, and estimated EUR. No content or secrets.

### Reconciliation actions

Support exactly:

1. `finalize-actual`
   - requires finite non-negative authoritative actual EUR cost, non-negative
     actual total tokens, explicit provider outcome success/failure, actor admin
     UUID, bounded non-empty reason, and `--execute`;
   - moves the full reservation out of reserved counters exactly once, adds the
     supplied actual cost/tokens/request to used counters even when they exceed
     the prior remaining balance, marks reservation finalized, and updates the
     existing ledger to `finalized` with actual EUR/tokens and explicit success;
   - records safe operator-reconciled cost source/confidence and overrun flags;
   - never claims provider-invoice equivalence.

2. `release-no-charge`
   - requires explicit `confirm_no_charge=true`, actor admin UUID, bounded
     non-empty reason, and `--execute`;
   - releases reserved counters exactly once, marks reservation released, and
     updates the existing ledger to `failed`, success false, actual EUR zero,
     total tokens zero, with a safe confirmed-no-charge marker;
   - absence of cost evidence is not confirmation and must remain held.

Both actions:

- lock the hold ledger, reservation, then key in a consistent order;
- revalidate exact ownership/facts and held state after locks;
- default to dry-run with zero mutation;
- append `external_tool_accounting_hold_reconciled` audit with actor/reason and
  safe old/new numeric/state facts;
- invoke/reuse the exact fence-resolution gate only after ledger, reservation,
  and counters are authoritative, then clear the fence in the same transaction;
- are exact-idempotent on repeat and reject changed repeated inputs;
- never call a provider or accept arbitrary database repair fields.

Extend objective-014 fence resolution so a finalized external reservation may
clear when its ledger is `finalized` and `success` is an explicit boolean,
because a provider may charge a failed request. A finalized ledger with
`success=None`, or any non-finalized accounting status, remains blocked.
Released still requires failed/false evidence.

## CLI contract

Add:

```text
slaif-gateway quota list-external-tool-holds --limit N --json
slaif-gateway quota reconcile-external-tool-hold \
  --reservation-id UUID \
  --action finalize-actual|release-no-charge \
  --dry-run|--execute \
  --actor-admin-id UUID \
  --reason TEXT \
  [--actual-cost-eur DECIMAL --actual-total-tokens INT --success|--failure] \
  [--confirm-no-charge] \
  --json
```

Dry-run remains default. Reject incompatible/missing action flags. Execute
requires actor and reason. Output contains safe projection only. Never accept a
provider URL, raw evidence body, credential, or content field.

## Backlog inspection, metrics, and alerts

Extend the existing scheduled **inspection** path only:

- add `RECONCILIATION_EXTERNAL_TOOL_HOLD_LIMIT` (positive, default 100);
- add `RECONCILIATION_ALERT_MIN_EXTERNAL_TOOL_HOLDS` (non-negative, default 1);
- inspect exact holds and add `external_tool_holds` count plus optional safe
  ledger/reservation IDs to the existing backlog payload;
- observe the existing generic reconciliation metrics with type
  `external_tool_accounting_hold`;
- include hold counts/optional IDs in the existing redacted webhook payload and
  threshold decision;
- never add an auto-execute-holds setting or Celery mutation task.

Alerting remains disabled by default. Existing expired/provider-completed
behavior must remain unchanged.

## Required PostgreSQL and negative evidence

Use independent sessions where concurrency matters and prove:

- missing usage, missing cost, ambiguous cost, disconnect/interruption, and
  unknown-charge provider error each create a durable held state through the
  service with no counter release;
- partial estimate produces `estimated`; no estimate produces `interrupted`;
- exact hold retry is idempotent; changed facts conflict;
- rollback/crash before commit leaves active/no-ledger; committed hold survives
  engine/session restart and expiry;
- auth and ordinary quota remain blocked for held;
- ordinary stale and scheduled reconciliation never auto-release/mutate holds;
- finalize actual within quota clears and permits later normal admission;
- finalize actual above cost/token remainder clears only after charging actual,
  leaves used counters above limit, and the next normal quota admission fails;
- charged provider failure (`success=false`) finalizes and clears with actual
  cost rather than being forgiven;
- release-no-charge requires explicit confirmation and clears with zero charge;
- missing actor/reason/confirmation, negative/non-finite values, ledger/fence/
  reservation mismatch, multiple ledgers, and changed repeats keep held;
- 2-worker and at least 8-worker concurrent reconciliation yields one mutation,
  exact counters/audits, and idempotent same outcome for exact repeats;
- no deadlock under ledger→reservation→key ordering;
- Redis absent/unavailable is irrelevant; no provider or content side effect.

## Documentation

Update implementation contracts and add an operator runbook. State clearly:

- hold/reconciliation foundation is implemented but provider forwarding is not;
- missing or ambiguous final cost never becomes zero-cost success;
- full balance stays reserved while held and expiry never releases it;
- only explicit audited manual reconciliation can finalize or confirm no charge;
- operator-supplied actual amounts are reconciliation evidence, not an invoice
  guarantee;
- actual overrun is charged and later quota admission fails normally;
- scheduled work inspects/alerts only and never mutates holds.

## Allowed paths

Implementation may change only:

```text
.env.example
AGENTS.md
app/slaif_gateway/cli/quota.py
app/slaif_gateway/config.py
app/slaif_gateway/db/repositories/usage.py
app/slaif_gateway/schemas/external_tool_hold.py
app/slaif_gateway/services/alert_service.py
app/slaif_gateway/services/external_tool_fence.py
app/slaif_gateway/services/external_tool_hold.py
app/slaif_gateway/workers/tasks_reconciliation.py
docs/accounting.md
docs/compatibility-matrix.md
docs/configuration.md
docs/product-scope.md
docs/provider-forwarding-contract.md
docs/responses-compatibility.md
docs/runbooks/external-tool-hold-reconciliation.md
docs/runbooks/stale-reservation-reconciliation.md
docs/security-model.md
oap/active
oap/orders/015-a-external-tool-accounting-hold-reconciliation.md
tests/integration/test_external_tool_fence_postgres.py
tests/integration/test_external_tool_hold_concurrency_postgres.py
tests/integration/test_external_tool_hold_postgres.py
tests/integration/test_reconciliation_tasks_postgres.py
tests/unit/test_alert_service.py
tests/unit/test_cli_quota_reconciliation.py
tests/unit/test_cli_quota_reconciliation_safety.py
tests/unit/test_config.py
tests/unit/test_documentation_contract_drift.py
tests/unit/test_external_tool_fence.py
tests/unit/test_external_tool_hold.py
tests/unit/test_reconciliation_metrics.py
tests/unit/test_reconciliation_tasks.py
```

The final report-only commit adds only:

```text
oap/reports/015-a-external-tool-accounting-hold-reconciliation.md
```

If a concrete missing symbol requires one additional exact path, stop and
report the blocker; do not expand. Do not modify models/migrations, provider
adapters, Chat/Responses handlers, admin dashboard, dependencies, CI, README,
or prior OAP history.

## Test economy

Run in slices:

1. new hold unit file plus affected fence unit file;
2. new dedicated hold PostgreSQL files plus affected fence/reconciliation-task
   PostgreSQL files against one explicit safe disposable `TEST_DATABASE_URL`,
   no skips;
3. focused CLI/config/task/alert/metrics/documentation unit files;
4. scoped Ruff/format-check/compile, Alembic one-head, diff/path/privacy checks;
5. GitHub CI.

Do not run full local unit/integration/E2E/browser/Docker/HPC/manual-Codex/
provider suites. No browser surface changes. Never call a provider, send real
email, use production data, or expose a secret.

## Acceptance criteria

1. Every supported unknown/ambiguous external accounting outcome atomically
   becomes a durable held fence, pending reservation, and one safe ledger with
   reserved counters unchanged.
2. Held state survives restart/expiry, blocks auth/quota, and cannot be released
   by ordinary/scheduled reconciliation.
3. Only explicit audited execute with actor/reason can finalize actual values or
   confirm no charge; dry-run and invalid evidence do not mutate.
4. Actual cost/tokens—including charged failure and overrun—finalize exactly
   once; over-limit keys reject following quota admission.
5. Confirmed no-charge release is explicit, exact-once, and never inferred from
   missing data.
6. Hold placement/reconciliation/retry/concurrency/rollback are fail-closed,
   deadlock-free, idempotent, and PostgreSQL-authoritative.
7. CLI, inspection metrics, alerts, runbook, accounting/security/compatibility
   docs expose only safe honest facts; scheduled work never auto-executes holds.
8. Redis is irrelevant, prohibited content is absent, forwarding remains
   denied, and no provider call occurs.
9. Focused tests and every final report-head GitHub check pass; broad local
   suites are not run.
10. Exactly one new PR # for objective 015; coding agent never merges or enables
    auto-merge; report `SELF` topology is exact.

## GitHub and immutable report

Commit the unchanged order and `oap/active=015-a`, create the required branch
and one new PR with the exact title, inspect checks, and repair only in-scope
failures. Never merge/auto-merge.

Publish exactly one immutable report at
`oap/reports/015-a-external-tool-accounting-hold-reconciliation.md` with:

- literal implementation SHA and `Report publication commit: SELF`;
- state matrix, reason/evidence contract, hold/partial/interrupted evidence;
- finalize/release/charged-failure/overrun/next-admission results;
- idempotency, rollback, restart, expiry, mismatch and worker counts;
- exact PostgreSQL/CLI/task/alert/metric commands, counts, skips, and cleanup;
- scheduled non-mutation, Redis/privacy/no-provider/no-forwarding evidence;
- docs impact, scope, GitHub checks, and no-merge/no-auto-merge confirmation.

The report commit must parent the implementation head and change only the new
report. Verify remote topology, send exact `OK` to `response.fifo`, then return
to `control.fifo`.
