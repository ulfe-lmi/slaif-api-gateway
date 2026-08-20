# OAP 015-c execution report

Objective: prove the external-tool hold/reconciliation boundaries with focused
PostgreSQL and unit evidence on the existing PR #240.

Implementation head SHA: ee39226315d6c33313b682ad9d1406e84f74da3c
Report publication commit: SELF

## Scope and production defects

The round added focused tests only, except for two concrete defects exposed by
those tests:

1. The exact held validator rejected extra keys inside the hold object but
   accepted extra top-level response metadata. It now requires the exact
   pre-reconciliation metadata shape.
2. Hold listing validated each ledger independently and could list one valid
   ledger when a reservation had multiple linked ledgers. Listing now requires
   exactly one linked ledger, matching the candidate row.

No migration, schema, provider-forwarding, dashboard, dependency, CI, or
documentation changes were made. Prior 015-a and 015-b reports were not edited;
their broad evidence statements are corrected here by recording the actual
015-c test evidence.

## Local unit evidence

Command:

```text
/tmp/slaif-api-gateway-014c-venv/bin/python -m pytest tests/unit/test_cli_quota_reconciliation.py tests/unit/test_cli_quota_reconciliation_safety.py tests/unit/test_external_tool_fence.py tests/unit/test_external_tool_hold.py tests/unit/test_reconciliation_tasks.py -q -ra
```

Result: 115 passed, 0 failed, 0 skipped.

This directly covers CLI invalid action/UUID/decimal handling, finalize and
release flag matrices, execute authorization, safe domain errors, secret and
content exclusions, fence behavior, hold unit behavior, and reconciliation
task behavior.

## Local PostgreSQL evidence

Command:

```text
set -euo pipefail
DB_NAME="slaif_gateway_test_oap015c_<timestamp>_<pid>"
DB_URL="postgresql+asyncpg://ubuntu@/${DB_NAME}?host=/var/run/postgresql"
createdb "$DB_NAME"
trap 'dropdb --if-exists "$DB_NAME"' EXIT
DATABASE_URL="$DB_URL" /tmp/slaif-api-gateway-014c-venv/bin/alembic upgrade head
DATABASE_URL="$DB_URL" TEST_DATABASE_URL="$DB_URL" /tmp/slaif-api-gateway-014c-venv/bin/python -m pytest tests/integration/test_external_tool_hold_postgres.py tests/integration/test_external_tool_hold_concurrency_postgres.py tests/integration/test_external_tool_fence_postgres.py tests/integration/test_reconciliation_tasks_postgres.py -q -ra
```

The exact selected matrix was 50 tests: 34 hold tests, 3 hold-concurrency
tests, 12 fence tests, and 1 reconciliation-task test. Result: 50 passed, 0
failed, 0 skipped. The database was created with the generated
`slaif_gateway_test_oap015c_` prefix and dropped by the EXIT trap. No existing
or production database was used for destructive setup.

The hold PostgreSQL cases directly prove:

- all five canonical reason codes and interrupted/estimated status selection;
- explicit zero-token projection preservation;
- transaction rollback leaves active fence, no ledger, unchanged counters, and
  no hold-created audit;
- engine/session restart durability, forced expiry, and ordinary expired
  reconciliation non-mutation;
- exact single-ledger shape, including zero-ledger, multiple-ledger, and
  active-plus-ledger negatives;
- actual/native cost, raw usage, status, success, metadata, timestamp,
  endpoint, provider, model, request, fence-pointer, and counter corruption
  negatives;
- changed streaming, reason, evidence, partial-token, and estimated-cost retry
  facts conflict without repair;
- dry-run finalize/release are non-mutating and require no actor/reason;
- explicit no-charge release produces failed/false/zero terminal evidence,
  audited actor/reason, clears the fence, and permits later admission;
- within-limit and overrun finalization move counters once, clear terminal
  state, and reject subsequent fence admission after a limit overrun;
- charged provider failure finalization; and
- bounded exact reconciliation races at two and eight workers.

Both concurrency tests use `asyncio.wait_for(..., timeout=30)`. The 2-worker
exact race produced one mutation and one idempotent result. The retained
8-worker race produced one mutation and seven idempotent results. The changed
input 2-worker race produced one winner and one
`external_tool_accounting_reconciliation_conflict`, with no second mutation or
audit.

The ordinary fence PostgreSQL cases additionally prove bearer authentication,
quota admission, stale/expired reconciliation, and held-fence blocking. The
scheduled reconciliation task case remained content-free and did not make
provider or email calls.

## Static and schema checks

Scoped Ruff over the changed production/test files reported `All checks passed`.
`git diff --check` passed. Alembic upgraded the disposable database to the
single current migration head; no migration file changed.

## GitHub evidence

PR #240 is the sole objective-015 PR, remains OPEN and MERGEABLE, is based on
`main`, and has no auto-merge request. The implementation commit above was
pushed to the existing branch. All final-head checks completed successfully:

- Unit, lint, and migration head
- PostgreSQL integration tests
- OpenAI-compatible E2E tests
- Playwright browser smoke
- Docker Compose smoke
- Documentation hygiene
- Analyze (javascript-typescript)
- Analyze Python
- Analyze (python)
- CodeQL

No check was skipped, cancelled, pending, or described as passed without a
successful conclusion.

## Safety, privacy, and boundaries

No real provider calls, real email, production access, or secrets were used.
The tests stored and printed only bounded identifiers and accounting facts; no
prompts, responses, tool arguments/results, URLs, credentials, media, or
provider content were exposed or committed. PostgreSQL remained authoritative
for hard accounting; Redis was not used as hold truth. No full local suite,
E2E/browser/Docker/HPC suite, manual Codex evidence suite, or upstream suite
was run.

The coding agent did not merge PR #240, enable auto-merge, push to `main`, or
edit prior orders/reports. The report-only commit must have the implementation
commit as its first parent and this report as its only changed path.
