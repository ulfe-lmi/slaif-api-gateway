# OAP Work Order — 220-b

PR mode: AMEND_EXISTING_PR (objective 220; unique PR #377)

## Objective, evidence and authority

Repair one demonstrated PostgreSQL integration-suite fixture failure caused by
the new `demo_control` schema, without changing the accepted demo-account
product implementation. This is a pre-merge continuation of the same numeric
objective and PR, not a new feature or PR. The human approved the full fresh-
at-login fake-admin demo through objectives 220–224, including copying and
sanitizing file-backed admin data. Those later stages remain inert; no public
demo access, real source snapshot, deployment, provider call or release is
authorized here.

Verified 2026-11-11 ~20:52 UTC: remote `main`
`51677702cbc44673f2e60f924f6a1400eb2fa673`; PR #377 OPEN/MERGEABLE,
base `main`, head branch `oap/220-demo-account-control`, exact remote head
`5efa48373d3793d168bf27de849ab0bd1e58a103`. That head is the immutable
220-a report-only SELF, sole parent implementation head
`b134c429a16168ef8f907bed09d0aad946d6ec3d`; its only changed file is
`oap/reports/220-a-demo-account-control.md`, SHA256
`15a8a80491d15f4008cf08f78feab130f0119634009aae4645697f248bbfaf5f`.
The root-authored 220-a order SHA256 is
`092a80e42c330f4d7e44239005235bf2bda5772e83334523aa62d6ad60e20cf9`;
`oap/active` is exact `220-a`. Preserve all 220-a bytes and history.

The initial CI run for implementation head `141115fd` had a failed unit job
(terminal-width-dependent new CLI test); accepted pre-report implementation
commit `b134c429` repaired that test, passed focused local/CI-version Typer
tests, and was included in the 220-a report. The same initial CI integration
job's `Run integration tests` step completed FAILURE at 20:22:49 UTC, although
GitHub still reports the job/run `in_progress` and rejects cancellation as
already stopped. Its logs endpoint returned HTTP 502. New-head/SELF workflow
runs are QUEUED, not passed; root owns exact-final-head CI review. Do not
classify this GitHub state as green or manufacture a check result.

Root independently reproduced the integration failure in an explicitly owned,
loopback/tmpfs PostgreSQL16 + Redis7 test setup matching CI's TEST_* URL shape.
The suite ran correctly through ~30% then `test_alembic_fresh_upgrade_postgres`
failed with `asyncpg.exceptions.DuplicateSchemaError: schema "demo_control"
already exists` at `0027_demo_admin_accounts.py:41` (`CREATE SCHEMA
demo_control`). Subsequent failures were cascading because the test's
`_reset_public_schema()` removes only `public` before/after a bare upgrade,
leaving the application-owned `demo_control` from earlier migrated tests.
The root stopped the cascading local suite after identifying that first
failure; it is NOT a complete local pass. An earlier run without explicit
TEST_DATABASE_URL hit a pre-existing Testcontainers psycopg2-URL fallback
issue and is NOT evidence for this defect. The 220-a new eight-test owned-PG
module itself passed locally. Only PR #377 is OAP objective220; unrelated
open PRs #374/#319 remain untouched.

Use the SAME existing Codex CLI in right tmux pane `%9` (PID3308462,
profile `early-beta`, Qwen3.8-27B A100 Q8 medium). No helper, subagent,
nested Codex or model/profile change. Canonical control waiter PID2057348
at strategic cwd `/home/janezp/codex-supervision/slaif-api-gateway`,
`TMUX_PANE=%9`, waits on actual FIFO `control.fifo` inode4501469;
`response.fifo` inode4501470. Root publishes this complete order and exact
`oap/active` into the shared worktree before ONE control OK. Permanent
`message.txt` remains objective-neutral and untouched.

Protected untracked `CODEX-SESSIONS.md` SHA256
`5ae1d77c17a367e86ef725a8f9d25aba3464b24f22fba77fd2808377f8c7feda`,
`codex.sh` SHA256
`66eda80258f6a4f13b88a9fe2ad5a69b9e7df226a4e503f57b35b6c6f03e1247`,
`uv.lock` SHA256
`d3d0e80db77da56e41795c619875ac14b5d25427d5169a7c9d2c8dee45b3b5b6`:
preserve by HASH ONLY; do not read/stage/change. Preserve ignored `.env`,
`.codex`, provider catalogs, unowned worktrees/containers/processes.

## Bounded repair

Allowed product-test path: ONLY
`tests/integration/test_alembic_fresh_upgrade_postgres.py`. The bare fresh
upgrade test must reset both application-owned schemas (`public` and
`demo_control`) in its safe disposable test database before its first upgrade
and in its `finally` recovery path. Rename the helper to reflect both schemas
if useful. Keep the explicit version-column/head and expected public-table
assertions; add an assertion that the new demo-control schema/tables exist
after a fresh upgrade if it strengthens the test without unrelated scope.
Do not change migration 0027 to `CREATE SCHEMA IF NOT EXISTS`, because an
unknown pre-existing schema must not be silently adopted in production.
Do not edit business logic, CLI, demo account model/service, normal admin auth,
policy, quotas/accounting, provider/route/client modules, or unrelated tests.
If a genuinely distinct failure appears after this correction, report it
precisely to root for a decision rather than broadening this order.

Publish the unchanged root-authored `oap/orders/220-b-demo-fresh-upgrade-fixture.md`
and exact `oap/active` (`220-b`) with the focused fix. Never edit 220-a order,
report or activation history. No schema change is needed: 0027 remains the
single Alembic head and its operational upgrade/downgrade semantics stay
unchanged. No operator docs change is expected for a test-fixture-only repair;
if one is needed, first explain why to root. Do not add infrastructure or a
new PR.

## Verification and negative evidence

Use only an owned, labeled, disposable PostgreSQL16 + Redis7 setup on
loopback/tmpfs, not ambient `DATABASE_URL` or any production DB. First prove
the failure order with a migration-using integration test followed by the bare
fresh-upgrade test, and prove both `public` and `demo_control` are correctly
restored for a downstream migrated integration test. Run that focused sequence
with direct pytest exit, scoped Ruff, single Alembic head, `git diff --check`,
and source/scope inspection. Because the initial full integration matrix had
a demonstrated cascade, run the complete `tests/integration` suite ONCE after
the repair against an explicitly owned CI-like TEST_DATABASE_URL/TEST_REDIS_URL,
with a direct pytest exit and bounded log. Distinguish skips and local
dependency versions from hosted CI. Do not repeatedly run unchanged suites
for counts or wait on stale GitHub check API state. Capture only safe
synthetic error excerpts; no real credentials, prompts, provider calls,
mail or production data. Show that the migration itself stays strict and
that test cleanup affects only the owned test database/containers.

GitHub final-head checks remain root's gate: all ten checks and three
workflows must succeed on final report SELF before merge. Pending, missing,
stale, failed or 502 GitHub results are not passes. Root may continue a later
repair round if the complete test reveals a distinct blocking defect.

## OAP delivery

Commit/push the root-authored order and active pointer UNCHANGED, plus the
one scoped test repair, on existing branch/PR #377. Report actual test
commands/exits/counts, any skips, exact failure/recovery evidence, unchanged
migration/product scope, protected-file hashes and GitHub CI status. Prepare
`oap/reports/220-b-demo-fresh-upgrade-fixture.md` away from its final path;
publish once with same-directory temp, file fsync, atomic replace and
directory fsync. Report literal implementation head SHA and `Report
publication commit: SELF`. Its final report-only SELF must have the
implementation head as SOLE parent and ONLY the matching report diff.
Verify exact remote head, PR identity, immutable 220-a artifacts,
root-authored 220-b order/active bytes, and new report before exactly one
two-byte response `OK` to canonical response FIFO. Rearm one canonical
control waiter on tmux `%9`; coding agent never merges or enables auto-merge.
Root reviews material/CI and merges only after final gates, verifies actual
main nine checks/three workflows, records timing, then activates 221-a.
