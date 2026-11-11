# OAP Coding-Agent Report — 220-d

## Work order and result

- Identifier `220-d`; root-authored order `oap/orders/220-d-demo-prefix-migration-fixture.md` SHA256 `045ae6e67c7bcd0408c89ac42e6f25728fd6826dcdf321080ad260c2b23d9480`; `oap/active` exact `220-d`.
- Scoped test-fixture repair COMPLETE; numeric objective 220 and PR #377 remain OPEN pending final-head CI and strategic review.
- Existing PR #377, base `main`, branch `oap/220-demo-account-control`, prior head 220-c report-only SELF `1df8243e5ae1877b8f27447b8009c7c683beb9f3`. Pushed implementation head `703cdd38ae792f0ffa4630fc54f8e1cf226b0f05`. Report publication commit: SELF. Coding agent did not merge or enable auto-merge.

## Change and boundaries

Only `tests/integration/test_gateway_key_prefix_migration_postgres.py` changed as product-test code. Its explicitly disposable database reset now drops both `demo_control` and `public` before historical migration 0004→0005→current head and again in `finally` before recovery. The test's fixed current-head expectation is updated from 0026 to `0027_demo_admin_accounts`; original key-prefix normalization, default and token-hash assertions remain. A post-recovery assertion checks that `public.alembic_version` and `demo_control.fake_admin_accounts` exist. The implementation commit also contains the unchanged root order and active pointer. Migration 0027, application runtime, admin authentication, quota/accounting, provider/client paths, docs and all other tests are unchanged; prior OAP orders/reports remain immutable.

## Verification and limitations

- Hosted CI on preceding implementation head `4feef654` failed in the PostgreSQL integration job: this prefix fixture left `demo_control` behind, causing `DuplicateSchemaError` in strict migration 0027; its public-only `finally` then caused missing-table cascades. The same test also pinned obsolete head 0026. This is the precise reason for 220-d.
- A new owned, labeled, loopback PostgreSQL 16.15 container used the fixture's allowlisted database name `slaif_gateway_test`, with synthetic credentials. The focused sequence ran migrated-table tests, both previously repaired fresh-schema fixtures, THIS 0005 prefix test, and downstream migrated-table tests: **15 passed, 16 warnings, direct pytest exit 0**. The prefix test executed, not skipped. Post-run DB had 34 `public` tables, two `demo_control` tables and Alembic head `0027_demo_admin_accounts`.
- Scoped Ruff, `alembic heads` (one head) and `git diff --check` passed. The exact owned container was removed after ID/label verification; no unowned resource was touched.
- The full local integration suite was not rerun in this round; 220-b's 49/639/21 local result remains negative evidence, not a pass. Hosted CI on the FINAL report SELF must run the complete suite and all ten checks/three workflows. Pending, missing or failed checks are not passes.
- No production data or credentials, provider/mail calls, deployment, release or schema changes. Protected untracked `CODEX-SESSIONS.md`, `codex.sh`, `uv.lock` were hash-verified without reading, staging or changing them. No operator docs change was needed for a test-only correction.

## Publication and strategic follow-up

Publish this report once at `oap/reports/220-d-demo-prefix-migration-fixture.md` by same-directory temp, file fsync, atomic replace and directory fsync. Its report-only SELF commit has sole parent `703cdd38ae792f0ffa4630fc54f8e1cf226b0f05` and changes ONLY this report. Verify remote PR head, report/order/active bytes, prior immutable artifacts and protected hashes, then send one exact response `OK` and rearm one canonical waiter on tmux `%9`. Strategic root reviews all final-head CI/review/material gates, guarded merges PR377 only if green, verifies actual-main nine checks/three workflows, records timing, and only then activates 221-a. No release or production demo run is authorized.
