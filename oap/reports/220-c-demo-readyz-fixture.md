# OAP Coding-Agent Report — 220-c

## Work order and result

- Identifier: `220-c`; order: `oap/orders/220-c-demo-readyz-fixture.md`, root-authored SHA256 `d75adbeec2a479e75e786bda71677cfb4bb06ac1df6af853bc6053552f7b2ffd`; `oap/active` exact `220-c`.
- Status: scoped test-fixture repair COMPLETE; numeric objective 220 and PR #377 remain OPEN pending final-head checks and strategic review.
- Repository: `ulfe-lmi/slaif-api-gateway`; existing PR #377, base `main`, branch `oap/220-demo-account-control`; starting PR head was 220-b report-only SELF `7e6b2dfbafcd1924099d7a7f66fe841249f1ed37`.
- Implementation head: `4feef6541a71ebf5c397b17068b6c539488e1703` (pushed). Report publication commit: SELF. Coding agent did not merge or enable auto-merge.

## Change and boundary

Only `tests/integration/test_readyz_postgres.py` changed as product-test code. Its disposable-DB reset helper now removes both application-owned schemas, `demo_control` and `public`, before the missing-schema `/readyz` probe and in the `finally` recovery before strict Alembic re-upgrade. It asserts `demo_control` is absent during the probe and that `public.alembic_version` and `demo_control.fake_admin_accounts` exist after recovery. The implementation commit also contains the unchanged root-authored order and exact active pointer. Migration 0027, gateway readiness behavior, admin authentication, quotas/accounting, provider/client paths, docs, and runtime code did not change. Prior 220-a/220-b orders/reports remain immutable.

## Verification and limitations

- Pre-fix owned-PostgreSQL16 sequence reproduced `DuplicateSchemaError` at migration 0027 `CREATE SCHEMA demo_control` after the `readyz` test's public-only reset; direct pytest exit 1.
- Post-fix focused sequence covering a preceding migration-using test, the bare fresh-upgrade fixture, the `readyz` missing-schema test and downstream migrated-table tests: 19 tests, direct pytest exit 0. Post-run owned DB: 34 `public` tables, two `demo_control` tables, Alembic `0027_demo_admin_accounts`.
- Scoped Ruff, `alembic heads` (one head), and `git diff --check`: pass. Owned labeled loopback PostgreSQL16 container was removed after ID/label verification; no unowned container was touched.
- The full local integration suite was NOT rerun in 220-c. The prior 220-b run remains FAILED (49 failed, 639 passed, 21 skipped): its second schema-reset failure is repaired here, while two catalog-refresh and two quota-reconciliation failures that preceded it remain distinct and unmodified. No full-suite pass is claimed. Hosted final-head CI is required; pending/missing checks are not passes.
- No production data, provider credentials, real provider calls, mail, deployment or release; synthetic owned test data only. Protected untracked `CODEX-SESSIONS.md`, `codex.sh`, `uv.lock` were not read, staged or changed; exact hashes were rechecked. No new schema or operator docs change was needed for this fixture-only repair.

## Publication and strategic follow-up

This report is published once as `oap/reports/220-c-demo-readyz-fixture.md` with same-directory temp, file fsync, atomic replace and directory fsync. Its report-only SELF commit must have sole parent `4feef6541a71ebf5c397b17068b6c539488e1703` and change only this report. The coding agent verifies remote PR head, report/order/active bytes and protected-file hashes before one exact response `OK`, then rearms one canonical control waiter. Strategic root must review all ten final-head checks and three workflows, material scope and any remaining CI failures before guarded merge; after merge it verifies actual-main nine checks/three workflows and records timing before activating 221-a. No current approval for release or production demo run.
