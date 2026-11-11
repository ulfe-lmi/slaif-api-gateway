# OAP Work Order — 220-d

PR mode: AMEND_EXISTING_PR (numeric objective 220; unique PR #377)

## Objective, reason and verified state

Finish compatibility of the existing PostgreSQL migration tests with the new
isolated `demo_control` schema introduced by objective 220. This is the LAST
of three integration fixtures that explicitly drop the `public` schema; the
other two were repaired under 220-b/220-c. Repair its reset/recovery and its
stale current-head assertion together, on the SAME objective PR. The human-
approved complete fake-admin demo still requires later objectives 221–224;
this order adds no public demo access, snapshot, file-copy/sanitizer, read-only
UI, provider call, deployment, release or production-data work.

Verified 2026-11-11 ~22:38 UTC: remote `main`
`51677702cbc44673f2e60f924f6a1400eb2fa673`; PR #377 OPEN,
base `main`, branch `oap/220-demo-account-control`, remote head
`1df8243e5ae1877b8f27447b8009c7c683beb9f3`. This is the immutable
220-c report-only SELF with SOLE parent implementation
`4feef6541a71ebf5c397b17068b6c539488e1703`, only changed path
`oap/reports/220-c-demo-readyz-fixture.md` SHA256
`8d6b6c0afb37fe045916b966f8c34feb44642f15502020a9b10993145e983aeb`.
220-c order SHA256
`d75adbeec2a479e75e786bda71677cfb4bb06ac1df6af853bc6053552f7b2ffd`;
220-b order/report hashes
`0945bc0ebda2ec1f8f272fa3b18df0defa609cff557f1421b9d109fa5483f8fb`
and `54635917e17cf4912068e37085dee5e4466ba9435540f7bffaa2fcb8a8d35f08`;
220-a order/report hashes
`092a80e42c330f4d7e44239005235bf2bda5772e83334523aa62d6ad60e20cf9`
and `15a8a80491d15f4008cf08f78feab130f0119634009aae4645697f248bbfaf5f`.
`oap/active` exact `220-c`. Preserve all prior orders, reports and commits
byte-for-byte. Unrelated open PRs #374/#319 untouched. Only prerelease
v0.1.0-rc.1 published; no release/tag/deploy authority.

Hosted CI on 220-c IMPLEMENTATION head `4feef654` completed PostgreSQL
integration FAILURE, while the other nine PR checks succeeded. The FIRST
hosted failing test is
`tests/integration/test_gateway_key_prefix_migration_postgres.py::
test_migration_0005_normalizes_gateway_key_prefix_and_default`: it drops
only `public` from an already migrated test database; migration 0027 then
raises `DuplicateSchemaError: schema "demo_control" already exists` at
`CREATE SCHEMA demo_control`. The test's `finally` repeats the same
public-only reset, leaving the shared test DB without business tables; the
run finished with 34 failed/4 errors, and later missing-table outcomes are
cascades (`owners`, `model_routes`, etc. missing). This test also has
`CURRENT_HEAD = "0026_request_diagnostics"`
while the actual one head is `0027_demo_admin_accounts`; fixing only the
reset would expose a second stale assertion in this same test. Root searched
ALL `tests/` for public schema drops and 0026 current-head constants: the
only schema-dropping files are the two already-fixed fixtures plus this
third one; this is the only stale `CURRENT_HEAD` constant. Do not weaken
production migration to `IF NOT EXISTS` or add an alternate head.

The 220-c report records focused owned-PG sequence 19 passed direct exit0,
one test-only file changed, Ruff/Alembic/diff clean, and no complete local
matrix rerun. The earlier 220-b complete local run FAILED 49/639/21 with
time-sensitive installed catalog checks, two quota assertions, and a later
readyz cascade; none was changed or called a pass. The hosted run at 220-c
implementation head showed no independent catalog or quota failure BEFORE
this third migration fixture. Current 220-c report SELF checks are pending;
no merge until final-head checks/reviews/material gate are satisfactory.

Use the SAME existing coding CLI in right tmux pane `%9` (PID3308462,
profile `early-beta`, Qwen3.8-27B A100 Q8 medium). Same current worktree,
no helper/subagent/nested Codex/new model/profile. The rearmed canonical
control waiter PID2283440 at strategic cwd
`/home/janezp/codex-supervision/slaif-api-gateway`, `TMUX_PANE=%9`,
reads actual `control.fifo` inode4501469; `response.fifo` inode4501470.
Root publishes this full order and active pointer into the shared filesystem
before exactly ONE control OK. Permanent `message.txt` is objective-neutral
and untouched.

Protected untracked `CODEX-SESSIONS.md` SHA256
`5ae1d77c17a367e86ef725a8f9d25aba3464b24f22fba77fd2808377f8c7feda`,
`codex.sh` SHA256
`66eda80258f6a4f13b88a9fe2ad5a69b9e7df226a4e503f57b35b6c6f03e1247`,
`uv.lock` SHA256
`d3d0e80db77da56e41795c619875ac14b5d25427d5169a7c9d2c8dee45b3b5b6`:
preserve by HASH ONLY, never read/stage/change. Preserve ignored `.env`/
`.codex`, provider catalogs and all unowned containers/worktrees/processes.

## Bounded implementation

Allowed implementation path: ONLY
`tests/integration/test_gateway_key_prefix_migration_postgres.py`, plus
unchanged root-authored `oap/orders/220-d-demo-prefix-migration-fixture.md`,
exact `oap/active` (`220-d`), and one matching immutable report. In that
test file, make the explicitly disposable migration-test reset remove BOTH
application-owned schemas (`demo_control`, `public`) before the historical
0004→0005→current-head validation and again in `finally` before recovery
to current head. Rename `_reset_public_schema` to reflect both schemas if
clear. Update only its `CURRENT_HEAD` expectation to
`0027_demo_admin_accounts`. Preserve historical 0005 prefix normalization,
default, token-hash invariants and exact one-head assertion. Do not change
the existing test URL allowlist or permit a production DB. Add a focused
post-recovery check for both schemas if useful. No migration, runtime,
database model, CLI, provider, quota/accounting, key parser or docs change.
No new PR. If a distinct failure appears, report it instead of broadening.

## Verification and negative/security evidence

Use a newly owned, labeled, loopback-bound disposable PostgreSQL16 database
whose name is EXACTLY one of this test's allowlist values (recommended
`slaif_gateway_test`), with synthetic credentials. The earlier local
`slaif220btest` database name is NOT in this test's allowlist and would SKIP,
so a skipped test does not qualify. Never use ambient `DATABASE_URL`, an
unowned service, production data or real provider/mail. Hosted CI already
proves the pre-fix failure; do not waste time reproducing it locally unless
needed for diagnosis. Run a focused sequence with direct pytest exit:
a migrated-table test first to create `demo_control`, then both repaired
fresh-schema tests, then THIS 0005 prefix migration test, then a downstream
migrated-table test. Show that the prefix test actually EXECUTED (no skip),
the historical prefix/default/hash assertions still pass, and final
`public` + `demo_control` tables and Alembic head0027 are restored. Check
scoped Ruff, one Alembic head, `git diff --check`, exact changed paths,
prior artifact hashes and protected-file hashes. Clean only exact labeled
owned containers after ID/label verification.

Do NOT rerun the entire local integration suite: 220-b already ran it once,
and hosted CI will run it on final HEAD. Do not pull unrelated local
catalog-refresh/FX/browser/quota failures into this patch without a current
hosted causal finding. Final-head CI must have all ten checks and all three
workflows SUCCESS before root merge; pending/skipped/missing are not passes.
No new docs needed for a test fixture; report any justified exception.

## Delivery

Commit/push ONLY the scoped test change plus root-authored order and active
pointer unchanged on existing branch/PR #377. Keep report concise and
reviewable (focused evidence and known limitations, no duplicate inventory).
Prepare `oap/reports/220-d-demo-prefix-migration-fixture.md` away from final
path; publish once via same-directory temp, file fsync, atomic replace and
directory fsync. Report literal implementation head SHA and `Report
publication commit: SELF`. The final report-only SELF has sole parent
implementation head and ONLY the matching report diff. Verify remote PR head,
order/active/report bytes, protected hashes and prior immutable artifacts
before exactly one two-byte response `OK` to canonical response FIFO.
Rearm one canonical control waiter on tmux `%9`. Coding agent never merges or
enables auto-merge. Root reviews final-head ten checks/three workflows,
security/privacy/accounting/scope/docs, guarded merges if green, verifies
actual-main nine checks/three workflows, records timing, then activates
221-a. No release/tag/deploy.
