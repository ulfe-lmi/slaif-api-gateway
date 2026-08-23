# OAP Work Order — 147-b

PR mode: `CONTINUE_EXISTING_PR`
PR: [#282](https://github.com/ulfe-lmi/slaif-api-gateway/pull/282)
Branch: `oap/147-module-provider-foundation`
Base: `main @ ddf6688b93cda905e0bc38673f6138afb2385a28`
Current head: `be5c8ec57d6c41bee3696045db06926a753a7cf6`
Title: `feat: add module-provider foundation and fixed request billing`

## Objective and reason

Reconcile the six stale migration-head assertions exposed by the final CI for
147-a after its exact migration `0023_module_provider_foundation` was added.
This is a bounded continuation of the same PR. It restores the repository's
test contract to the actual single Alembic head without changing the module
foundation, billing behavior, facial-service scope, or any production code.

## Reconciled current state

- 147-a implementation commit `f4adaf98dd448bbac18ff1b3da4b31a252f3b3b6` is
  pushed to PR #282.
- 147-a report publication commit `be5c8ec57d6c41bee3696045db06926a753a7cf6`
  is pushed and changes only its immutable report.
- The PR is open and targets `main`; its final CI is unstable only because
  five unit migration-head assertions expect `0022_provider_governance` and
  one PostgreSQL migration test expects the same stale head.
- `migrations/versions/0023_module_provider_foundation.py` is the actual
  single Alembic head. The new module-provider and fixed-request implementation
  is otherwise outside this continuation's scope.
- No facial adapter, downstream facial-service call, endpoint activation,
  credential, image, or production data is authorized here.

## Requirements

1. Update only the six named test expectations from
   `0022_provider_governance` to the exact current head
   `0023_module_provider_foundation`.
2. Preserve each test's original purpose and all other assertions. Do not
   weaken, delete, skip, or broaden migration coverage.
3. Do not modify application code, migrations, schemas, accounting, quota,
   provider dispatch, configuration, docs, facial-scoring behavior, or CI.
4. Keep the change on PR #282 and its existing branch. Do not create a new PR,
   merge, enable auto-merge, or amend the immutable 147-a order/report.

## Explicit allowed paths

```text
tests/unit/test_alembic_accounting.py
tests/unit/test_alembic_email_jobs.py
tests/unit/test_alembic_external_tool_fence.py
tests/unit/test_alembic_key_prefix_default.py
tests/unit/test_schema_status.py
tests/integration/test_gateway_key_prefix_migration_postgres.py
oap/orders/147-b-refresh-migration-head-expectations.md
oap/reports/147-b-refresh-migration-head-expectations.md
oap/active
```

No other path may change for the implementation or report publication.

## Acceptance criteria

- All six stale expectations name exactly
  `0023_module_provider_foundation`.
- The affected unit tests pass, including the five migration-head assertions
  and schema-status expectation.
- The affected PostgreSQL integration test passes against an isolated,
  disposable test database and leaves no test data behind.
- The final PR-head required CI is green, including unit/lint/migration-head
  and PostgreSQL integration jobs. Pending, skipped, cancelled, missing, or
  environment-blocked checks are not passes.
- The final diff contains only the six expected test edits plus the required
  OAP order/active/report transcript files, with no production or facial
  service behavior changes.

## Required verification

Run on the final implementation head:

```text
python -m pytest \
  tests/unit/test_alembic_accounting.py \
  tests/unit/test_alembic_email_jobs.py \
  tests/unit/test_alembic_external_tool_fence.py \
  tests/unit/test_alembic_key_prefix_default.py \
  tests/unit/test_schema_status.py
python -m pytest tests/integration/test_gateway_key_prefix_migration_postgres.py
python -m ruff check tests/unit/test_alembic_accounting.py \
  tests/unit/test_alembic_email_jobs.py \
  tests/unit/test_alembic_external_tool_fence.py \
  tests/unit/test_alembic_key_prefix_default.py \
  tests/unit/test_schema_status.py \
  tests/integration/test_gateway_key_prefix_migration_postgres.py
alembic heads
git diff --check
```

Also inspect the final diff and CI logs to confirm that only stale expected
head values changed and that no test was weakened or made environment-specific.

## Security, privacy, and accounting boundaries

This continuation handles migration-test expectations only. It must not add
credentials, URLs, images, data URLs, raw request/response content, provider
calls, logs, fixtures containing secrets, or changes to quota/accounting truth.

## Report and publication contract

The coding agent must push the continuation on PR #282 and must not merge or
enable auto-merge. Its final report must identify the exact final PR head,
changed paths, six updated expectations, focused and CI evidence, and any
remaining failure. The report-publication commit must change only
`oap/reports/147-b-refresh-migration-head-expectations.md`; the report and
147-a artifacts are immutable.
