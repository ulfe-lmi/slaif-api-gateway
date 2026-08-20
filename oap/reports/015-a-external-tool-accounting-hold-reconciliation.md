# OAP 015-a report — external-tool accounting holds and reconciliation

## Implementation and topology

Implementation head SHA: `ecb0400de0db0e9ef1a19fbf14cfb6c560f1e62b`
Report publication commit: SELF

- PR: #240, `[OAP 015] Add external-tool accounting holds and reconciliation`
- Branch: `oap/015-external-tool-accounting-hold-reconciliation`
- Base: `main`
- PR state: open and mergeable; no merge and no auto-merge performed.
- The active selector and order were committed unchanged on the implementation
  head: `oap/active=015-a` and `oap/orders/015-a-external-tool-accounting-hold-reconciliation.md`.
- The implementation head is the remote PR head. The worktree was clean before
  this report-only commit.

## Durable contract implemented

No migration or model/database column was added. Current Alembic head remains
`0015_external_tool_exclusive_fence`.

The durable matrix is:

| Fence | Reservation | Ledger | Meaning |
| --- | --- | --- | --- |
| `active` | fenced + pending | absent | request in flight |
| `held` | fenced + pending | `estimated` or `interrupted` | unresolved accounting hold |
| `active` | finalized | finalized | terminal charge, awaiting exact clear |
| `active` | released | failed | confirmed no charge, awaiting exact clear |
| `none` | finalized/released | terminal | reconciled and cleared |

`ExternalToolAccountingHoldService` validates reservation/key/request/fence/
route facts, locks reservation then key, creates exactly one content-free
ledger, and transitions `active` to `held` without changing reserved or used
counters. Exact retries return the safe projection; changed facts, duplicate or
mismatched ledgers, terminal reservations, and counter drift fail closed.

The schema uses a closed reason enum for missing final usage, missing final
cost, ambiguous final cost, interruption/disconnect, and provider error with
unknown charge. Evidence quality is `missing`, `partial_estimate`, or
`ambiguous`. Hold metadata is version 1 and contains only state, reason,
reconciliation flag, evidence quality, and timestamp. Optional partial token
and estimated EUR values stay in typed ledger columns. No raw provider/tool
bodies, prompts, responses, arguments/results, MCP values/URLs, credentials,
or diagnostics are accepted or stored.

Manual reconciliation is dry-run by default and requires explicit execute,
admin UUID, bounded reason, and either finite non-negative actual EUR/tokens
plus an explicit boolean provider outcome, or `confirm_no_charge`. Finalization
moves the full reservation into used counters, including charged failures and
overruns, marks the ledger `finalized`, and uses the held-fence resolution gate.
No-charge release marks the reservation released and ledger failed/false with
zero actual cost/tokens. Repeated identical actions are idempotent; changed
repeats conflict. Reconciliation locks ledger, reservation, then key.

The CLI provides `list-external-tool-holds` and
`reconcile-external-tool-hold` with safe JSON projections. Scheduled backlog
inspection and alerts include hold counts and optional IDs but never mutate or
auto-execute holds. Redis is not used as accounting authority, and no provider
forwarding path was enabled.

## Tests and evidence

Focused unit command:

```text
python -m pytest tests/unit/test_external_tool_hold.py tests/unit/test_external_tool_fence.py tests/unit/test_alert_service.py tests/unit/test_cli_quota_reconciliation.py tests/unit/test_cli_quota_reconciliation_safety.py tests/unit/test_config.py tests/unit/test_documentation_contract_drift.py tests/unit/test_reconciliation_metrics.py tests/unit/test_reconciliation_tasks.py -q -ra
```

Result: 183 passed, 0 skipped. This covered hold placement/idempotency,
partial-versus-interrupted status, charged-failure accounting, explicit
no-charge validation, fence behavior, CLI/config/task/alert contracts, and
documentation/privacy drift.

Disposable PostgreSQL command:

```text
DATABASE_URL="$DB_URL" alembic upgrade head
DATABASE_URL="$DB_URL" TEST_DATABASE_URL="$DB_URL" python -m pytest tests/integration/test_external_tool_hold_postgres.py tests/integration/test_external_tool_hold_concurrency_postgres.py tests/integration/test_external_tool_fence_postgres.py tests/integration/test_reconciliation_tasks_postgres.py -q -ra
```

The run used the explicit disposable database
`slaif_gateway_test_oap015a_20260820j`, migrated through head, and dropped it
after the run. Result: 16 passed, 0 skipped, with one existing Alembic
deprecation warning. It proved durable held state, full reservation retention,
restart/session-boundary finalization, charged provider failure, exact repeat,
8-worker reconciliation (one mutation and seven exact retries), fence lock
ordering, and existing reconciliation behavior. No production database,
Redis, provider, email, or user content was used.

Additional final-head local checks passed:

```text
ruff check <scoped implementation and focused test paths>
python -m compileall -q <scoped implementation paths>
git diff --check
slaif-gateway quota reconcile-external-tool-hold --help
```

## GitHub final-head checks

All ten checks passed on the implementation head:

- Unit, lint, and migration head
- PostgreSQL integration tests
- OpenAI-compatible E2E tests
- Playwright browser smoke
- Docker Compose smoke
- Documentation hygiene
- Analyze (javascript-typescript)
- Analyze (python)
- Analyze Python
- CodeQL

The initial implementation-head CI run exposed one in-scope fence concurrency
regression; the active resolver was corrected to preserve the existing held
transition no-op while allowing the explicit reconciliation gate. The amended
head above passed the complete final-head matrix. No broad local unit,
integration, E2E, browser, Docker, HPC, or provider suite was run beyond the
specified focused PostgreSQL slices; routine broad coverage came from GitHub
CI.

## Scope, privacy, and handoff

Changed paths are limited to the order allowlist. Provider adapters, Chat and
Responses handlers, admin dashboard, dependencies, CI, and migrations were not
changed. Documentation explains that the foundation is implemented but
provider forwarding is not, missing/ambiguous cost is not zero-cost success,
held expiry never releases balance, operator actuals are reconciliation
evidence rather than invoice truth, overruns are charged, and scheduled work
only inspects/alerts.

No secrets, prompts, responses, tool arguments/results, media, credentials, or
prohibited content were printed, stored, or committed. The coding agent did
not merge PR #240 or enable auto-merge. After this report-only commit, no
repository or remote mutation is authorized.
