# OAP Work Order — 008-c

## Objective

Resolve the exact CI-only blocker reported by 008-b by refreshing six legacy
migration-head expectations from `0012_conversation_references` to the valid
single successor `0013_codex_replay_references`, then return PR #233 to an
all-green final report head without changing the objective-008 implementation.

## GitHub state

- Numeric objective `008`, round `008-c`.
- PR mode: `AMEND_EXISTING_PR`.
- Existing PR #233:
  `https://github.com/ulfe-lmi/slaif-api-gateway/pull/233`.
- Branch `oap/008-codex-multiturn-reasoning-replay`; base `main`.
- Starting remote/report head:
  `8a3c526cc28cf2f3ab80e3abe03682c1f9aa470d`.
- 008-b implementation head:
  `f8a67a12b494295c04a77bd67b3be6379147ed49`.
- 008-b status: `BLOCKED` only by six out-of-scope stale migration-head
  assertions after all objective-specific local evidence passed.

Amend PR #233 only. Never create another objective-008 PR.

## Verified blocker

GitHub CI on implementation head `f8a67a1` completed with eight checks green
and two jobs red. The unit job passed 2,600 tests and failed five assertions;
the PostgreSQL job passed 130 tests and failed one assertion. Every failure
expected the former Alembic head `0012_conversation_references` even though
objective 008 correctly added the sole successor
`0013_codex_replay_references`. The upgrade itself reached 0013 successfully.

The exact six stale files are:

```text
tests/integration/test_gateway_key_prefix_migration_postgres.py
tests/unit/test_alembic_accounting.py
tests/unit/test_alembic_email_jobs.py
tests/unit/test_alembic_key_prefix_default.py
tests/unit/test_alembic_provider_pricing.py
tests/unit/test_schema_status.py
```

`tests/unit/test_alembic_codex_replay_references.py` correctly asserts that
0013's `down_revision` is 0012 and must remain unchanged.

## Required work

1. Reconcile canonical GitHub, PR #233, remote branch head, the immutable
   008-a/008-b orders and reports, this order, and the applicable AGENTS/OAP
   instructions before editing.
2. Commit the strategic `oap/active=008-c` pointer and this order unchanged.
3. In only the six named stale test files, update the current-head expectation
   to `0013_codex_replay_references`. Preserve each test's historical migration
   assertions, test purpose, database safety, and all other behavior.
4. Do not modify migration history, schema/model/replay code, the new 0013
   migration test, documentation, fixtures, dependencies, CI, or unrelated
   files. Do not weaken, skip, delete, or xfail a test.
5. Push the repair to the existing PR and require every final-head GitHub check
   to complete successfully before the final report. Pending, skipped,
   cancelled, missing, neutral, or failed checks are not green.

## Allowed paths

Implementation may change only:

```text
oap/active
oap/orders/008-c-refresh-migration-head-expectations.md
tests/integration/test_gateway_key_prefix_migration_postgres.py
tests/unit/test_alembic_accounting.py
tests/unit/test_alembic_email_jobs.py
tests/unit/test_alembic_key_prefix_default.py
tests/unit/test_alembic_provider_pricing.py
tests/unit/test_schema_status.py
```

The final report-only commit adds only:

```text
oap/reports/008-c-refresh-migration-head-expectations.md
```

Do not edit any 008-a/008-b order/report or any other path.

## Focused verification and test economy

Run only:

- the five named unit test files;
- the one named PostgreSQL integration test file against an explicitly named
  disposable `TEST_DATABASE_URL` database, if the safe local PostgreSQL
  prerequisite is available;
- Alembic single-head verification;
- scoped Ruff only if these test edits require it;
- OAP governance/documentation hygiene checks required for the new transcript;
- `git diff --check` and exact changed-path/topology checks.

Do not run the full unit, integration, E2E, browser, Docker/Compose, or HPC
suites locally. GitHub CI already owns the broad rerun. Never use
`DATABASE_URL` for destructive test setup and never make a real provider call.

The report must give literal commands/results, safe database lifecycle if used,
all broad suites explicitly NOT RUN, and the exact final GitHub check state.

## Acceptance criteria

1. All six stale current-head expectations identify
   `0013_codex_replay_references`; no historical/down-revision assertion is
   altered.
2. Only the eight implementation/order/pointer paths above change before the
   report commit; no test is weakened or skipped.
3. Focused tests, single-head check, transcript/governance checks, and diff/path
   checks pass.
4. Every required GitHub check is green on the literal implementation head
   recorded in the report.
5. The existing PR remains the only objective-008 PR; coding agent performs no
   merge or auto-merge.
6. The immutable final commit changes only the 008-c report and has the recorded
   implementation head as its first parent.

## PR/report requirements

Commit the unchanged 008-c order/pointer with the six expectation repairs,
push to PR #233, wait for and inspect all final implementation-head checks, and
never merge or enable auto-merge. Publish exactly one immutable report at
`oap/reports/008-c-refresh-migration-head-expectations.md` with the literal
implementation SHA, `Report publication commit: SELF`, exact path/test/CI
evidence, broad suites not run, documentation impact (`none; test/transcript
repair only`), and explicit no-merge statement. The final commit must contain
only that report and have the implementation SHA as first parent. Verify the
remote report head, then signal exact `OK`.

If any final check fails for a cause beyond these exact stale expectations,
report the blocker without broadening scope or hiding the failure. Do not merge.
