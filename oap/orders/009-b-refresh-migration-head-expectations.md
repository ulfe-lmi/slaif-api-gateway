# OAP Work Order — 009-b

## Objective

Resolve the exact CI-only blocker reported by 009-a by updating six legacy
current-Alembic-head expectations from `0013_codex_replay_references` to the
valid sole successor `0014_codex_context_accounting_compaction`, then return
PR #234 to an all-green report head without changing objective-009 product
logic, protocol evidence, migration history, or documentation.

## GitHub state

- Numeric objective `009`, round `009-b`.
- PR mode: `AMEND_EXISTING_PR`.
- Existing PR #234:
  `https://github.com/ulfe-lmi/slaif-api-gateway/pull/234`.
- Branch `oap/009-codex-context-output-cache-compaction-accounting`; base
  `main`.
- Starting remote/report head:
  `ceb6fda4b5d69f6b98e47a6ced2a2ddafef841b8`.
- 009-a implementation head:
  `1fcb90b2e947c1cd4a43c68b34e5f6ad04353600`.
- 009-a status: `BLOCKED` only by six out-of-scope stale migration-head
  assertions after its focused context/accounting/compaction tests, isolated
  PostgreSQL proof, migration lifecycle, and pinned CLI verifier passed.

Amend PR #234 only. Never create another objective-009 PR.

## Verified blocker

GitHub CI on 009-a implementation head had eight checks green and two red:

- full unit/lint/migration: 2,642 passed, five failed solely because the named
  legacy tests expected head 0013 but correctly observed 0014;
- PostgreSQL integration: 131 passed, one failed on the same stale current-head
  expectation after the migration itself upgraded successfully.

The exact six stale paths are:

```text
tests/integration/test_gateway_key_prefix_migration_postgres.py
tests/unit/test_alembic_accounting.py
tests/unit/test_alembic_email_jobs.py
tests/unit/test_alembic_key_prefix_default.py
tests/unit/test_alembic_provider_pricing.py
tests/unit/test_schema_status.py
```

The new 0014 migration test and its `down_revision` assertion are already
correct and must remain unchanged.

## Required work

1. Reconcile canonical GitHub, PR #234, the exact remote head, immutable 009-a
   order/report, this order, and applicable AGENTS/OAP instructions.
2. Commit the strategic `oap/active=009-b` pointer and this order unchanged.
3. In only the six named tests, replace the current-head expectation with
   `0014_codex_context_accounting_compaction`. Preserve all historical target,
   downgrade, database-safety, and behavioral assertions.
4. Do not modify product code, migration/model/schema, 009 verifier/evidence,
   documentation, dependencies, CI, or any other test. Do not weaken, skip,
   delete, xfail, or dynamically evade an assertion.
5. Push the repair to existing PR #234 and require every final implementation-
   head GitHub check to complete successfully before publishing the report.
   Failed, pending, skipped, cancelled, neutral, missing, or stale checks are
   not green.

## Allowed paths

Implementation may change only:

```text
oap/active
oap/orders/009-b-refresh-migration-head-expectations.md
tests/integration/test_gateway_key_prefix_migration_postgres.py
tests/unit/test_alembic_accounting.py
tests/unit/test_alembic_email_jobs.py
tests/unit/test_alembic_key_prefix_default.py
tests/unit/test_alembic_provider_pricing.py
tests/unit/test_schema_status.py
```

The final report-only commit adds only:

```text
oap/reports/009-b-refresh-migration-head-expectations.md
```

Do not edit any 009-a order/report or any other path.

## Focused verification and test economy

Run only:

- the five named unit test files;
- the one named PostgreSQL integration file against an explicitly named,
  disposable `TEST_DATABASE_URL` database if safe local PostgreSQL is
  available;
- `alembic heads`;
- focused OAP governance/documentation hygiene for the new transcript;
- `git diff --check` and exact path/topology checks.

Do not rerun the 009-a manual Codex verifier. Do not run full unit,
integration, E2E, browser, Docker/Compose, or HPC suites locally. GitHub CI
owns the broad rerun. Never use `DATABASE_URL` for destructive setup and never
make a real provider call.

The report must record literal commands/results, safe database lifecycle if
used, every broad suite NOT RUN, and exact final GitHub check state.

## Acceptance criteria

1. All six current-head expectations identify
   `0014_codex_context_accounting_compaction`; historical/down-revision
   assertions remain unchanged.
2. The implementation commit changes exactly the eight allowed pointer/order/
   test paths, with no weakened or skipped test.
3. Focused tests, single-head check, transcript checks, diff, and path checks
   pass.
4. Every required GitHub check is green on the literal implementation head
   recorded in the report.
5. PR #234 remains the only objective-009 PR; coding agent performs no merge or
   auto-merge.
6. The immutable final commit changes only the 009-b report and has the
   recorded implementation head as first parent.

## PR/report requirements

Commit the unchanged 009-b order/pointer with the six expectation repairs,
push to PR #234, wait for all implementation-head checks, and never merge or
enable auto-merge. Publish exactly one immutable report at
`oap/reports/009-b-refresh-migration-head-expectations.md` with the literal
implementation SHA, `Report publication commit: SELF`, exact path/test/CI
evidence, broad suites not run, documentation impact (`none; test/transcript
repair only`), and explicit no-merge statement. The final commit must contain
only that report and have the implementation SHA as first parent. Verify the
remote report head, then signal exact `OK`.

If any final check fails for a cause beyond these exact stale expectations,
report the blocker without broadening scope or hiding the failure. Do not merge.
