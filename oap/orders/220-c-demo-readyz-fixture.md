# OAP Work Order — 220-c

PR mode: AMEND_EXISTING_PR (numeric objective 220; unique PR #377)

## Objective, reason and verified state

Repair the SECOND directly affected fresh-schema PostgreSQL test fixture after
Alembic 0027 introduced the dedicated `demo_control` schema. The change is
test-only and stays on the same objective PR. The human-authorized complete
demo feature still requires later objectives 221–224: fresh source snapshot
after successful fake-admin login, copied/sanitized file-backed admin data,
private disposable database, silent no-op operational actions, zero-account
404, logout/expiry cleanup and installed/browser proof. None of that is
implemented or exposed by this test repair; no production snapshot, real
provider/mail call, deployment, release or tag is authorized.

Verified 2026-11-11 ~22:05 UTC: remote `main` is
`51677702cbc44673f2e60f924f6a1400eb2fa673`; PR #377 is OPEN, base
`main`, head branch `oap/220-demo-account-control`, remote head
`7e6b2dfbafcd1924099d7a7f66fe841249f1ed37`. This is immutable 220-b
report-only SELF, sole parent implementation head
`824bfc0d6192bbb847a98745b6bd1da35d582b15`, only changed path
`oap/reports/220-b-demo-fresh-upgrade-fixture.md` SHA256
`54635917e17cf4912068e37085dee5e4466ba9435540f7bffaa2fcb8a8d35f08`.
220-b order SHA256
`0945bc0ebda2ec1f8f272fa3b18df0defa609cff557f1421b9d109fa5483f8fb`;
220-a order/report hashes `092a80e42c330f4d7e44239005235bf2bda5772e83334523aa62d6ad60e20cf9`
and `15a8a80491d15f4008cf08f78feab130f0119634009aae4645697f248bbfaf5f`.
`oap/active` is exact `220-b`. Preserve all prior orders/reports/commits
byte-for-byte. Only unrelated open PRs #374/#319 also exist; do not touch.
No release/deployment authority; only published release v0.1.0-rc.1.

220-b repaired `tests/integration/test_alembic_fresh_upgrade_postgres.py`
only: its reset helper now drops `demo_control` and `public` before/after a
bare upgrade; focused owned-PG sequence passed direct exit0; migration 0027
remains strict `CREATE SCHEMA demo_control`. Its complete owned CI-shaped
local integration run was executed ONCE and FAILED (49 failed, 639 passed,
21 skipped, 1748.73s). The first fresh-upgrade failure was eliminated.
A distinct later test `tests/integration/test_readyz_postgres.py::
test_readyz_reports_missing_schema_on_fresh_database` has its OWN
`_reset_public_schema()` helper at lines ~171–181. It drops only `public`,
then its `finally` calls `run_alembic_upgrade_head`; the existing
`demo_control` makes migration 0027 raise `DuplicateSchemaError` and leaves
the shared test DB unusable, cascading through subsequent tests. Root read
the exact local traceback (`test_readyz_postgres.py:198`, `CREATE SCHEMA
demo_control`) and the original hosted CI log confirmed the analogous first
fresh-upgrade failure. This is a demonstrated direct consequence of adding
the new schema; do NOT weaken production migration to IF NOT EXISTS.

The full local run also recorded independent pre-readyz failures: an
installed catalog report browser element ended at 916.5px in a 900px
viewport; an isolated Codex research fixture dated 2026-10-12 hit the FX
staleness gate on 2026-11-11; and two quota-reconciliation invariants raised
`ReconciliationInvariantError`. None is attributed to this order's test
fix without a reproducible causal link. Do not bundle repairs for those
subsystems, claim a full local pass, or call all 49 failures one cascade.
Root will classify them against final-head hosted evidence after this
focused repair. GitHub Actions had a documented major outage earlier; it
now schedules current SELF runs, but final-head checks on PR377 are pending.
Pending/missing/failed checks are not passes. No merge until all final gates.

Use the SAME existing coding CLI in right tmux pane `%9` (PID3308462,
profile `early-beta`, Qwen3.8-27B A100 Q8 medium). No helper/subagent/
nested Codex/model/profile change. The canonical rearmed control waiter
PID2226507 at strategic cwd `/home/janezp/codex-supervision/slaif-api-gateway`
has `TMUX_PANE=%9`, reads actual `control.fifo` inode4501469;
`response.fifo` inode4501470. Root publishes full order and exact active
pointer into the shared filesystem before ONE control OK. Permanent
`message.txt` stays objective-neutral and untouched.

Protected untracked `CODEX-SESSIONS.md` SHA256
`5ae1d77c17a367e86ef725a8f9d25aba3464b24f22fba77fd2808377f8c7feda`,
`codex.sh` SHA256
`66eda80258f6a4f13b88a9fe2ad5a69b9e7df226a4e503f57b35b6c6f03e1247`,
`uv.lock` SHA256
`d3d0e80db77da56e41795c619875ac14b5d25427d5169a7c9d2c8dee45b3b5b6`.
Preserve those files by HASH ONLY: never read/stage/change. Preserve
ignored `.env`/`.codex`, provider catalogs and all unowned processes,
worktrees and containers.

## Bounded implementation

Allowed implementation path: ONLY `tests/integration/test_readyz_postgres.py`,
plus unchanged root-authored `oap/orders/220-c-demo-readyz-fixture.md`, exact
`oap/active` (`220-c`) and one immutable matching report. In that test file,
make the fresh-missing-schema test reset BOTH application-owned schemas on
its explicitly disposable PostgreSQL test database, before the `/readyz`
probe and in `finally` before re-upgrading to head. Rename the helper to
`_reset_application_schemas` if clear. Preserve the test's assertions that
the DB is reachable but schema is missing and that migration recovery
restores readiness for downstream tests. Add only focused assertions needed
to prove `demo_control` was absent during the missing-schema probe and
restored afterwards, if appropriate. Do not touch app readiness behavior,
migration 0027, quota/accounting, catalog refresh, browser CSS, FX policy,
normal admin auth, provider/client modules, other tests or docs. No database
schema change. If an unrelated failure is confirmed, report it to root for
separate scope rather than broadening this order.

## Verification and negative/security evidence

Use an owned, labeled, disposable PostgreSQL16 test database on loopback
(tmpfs preferred) and exact `TEST_DATABASE_URL` guard; never use ambient
`DATABASE_URL` or an unowned/production DB. Reproduce the failure order:
first run a migration-using test, then the `readyz` missing-schema test,
then a downstream migrated-table test. Before the patch the middle test
must fail at 0027 strict schema creation; after the patch that three-part
sequence must pass by direct pytest exit, and both `public` and
`demo_control` must be usable after the `finally` recovery. Run the other
focused bare-upgrade fixture test in the sequence so both reset helpers
coexist. Verify no business tables/credentials/usage or runtime logic changed,
scoped Ruff, `alembic heads` one head, and `git diff --check`. A clean
disposable database must be used after the negative reproduction so stale
broken state cannot masquerade as a patch failure. Clean up ONLY exact
owned test containers after label/ID verification.

Do NOT rerun the unchanged complete 709-case local integration suite for a
count or to re-demonstrate known independent failures: 220-b already ran it
once and recorded its exact negative outcome. The hosted CI integration job
will rerun the complete suite on the new final head. If final-head CI
demonstrates another blocking defect, root will scope the next same-PR
continuation. No actual Codex/provider/mail/production access is authorized.
No docs change is expected for a test-fixture-only repair; report any needed
exception before broadening.

## Delivery

Commit/push ONLY the scoped test fixture change plus root-authored 220-c
order and active pointer unchanged on existing branch/PR #377. Report exact
commands/exits, owned-DB setup/cleanup, negative and positive evidence,
unrelated local failures not fixed, CI pending state and prior immutable
hashes. Prepare `oap/reports/220-c-demo-readyz-fixture.md` away from final
path; publish once with same-directory temp, file fsync, atomic replace and
directory fsync. Report literal implementation head SHA and `Report
publication commit: SELF`. The final report-only SELF has that implementation
head as SOLE parent and ONLY this report diff. Verify remote branch/PR head,
order/active/report bytes, scope and protected hashes before exactly one
two-byte response `OK` to canonical response FIFO. Rearm one canonical
control waiter on tmux `%9`; coding agent never merges or enables auto-merge.
Root independently reviews final-head ten checks/three workflows and all
material gates, merges only if green, verifies actual-main nine checks/three
workflows, records timing, then activates 221-a. No release/tag/deploy.
