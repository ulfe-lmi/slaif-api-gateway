# OAP Work Order — 224-b: exact worker handoff and cleanup

PR mode: AMEND_EXISTING_PR. Objective 224, unique PR #383, branch
`oap/224-demo-web`, base remote `main`
`d3762e51c9a323dee6b728c4a45fa21b0bffae86`. Do not create another PR,
merge, enable auto-merge, deploy, release, or touch real company data. The
human approved the complete live fake-admin demo, including a NEW snapshot
after each login, a wait page, fictionalized identities with real usage
patterns, CLI-only fake-admin accounts, silent no-op GUI actions, and copied
and sanitized file-backed panels. This suffix supplies the private worker
handoff/cleanup boundary; later suffixes on THIS PR supply the web host,
session UI, copy-backed admin reads, no-op actions, and installed browser
qualification. The demo remains unavailable to browsers in 224-b.

## Verified starting state and ownership

224-a report is immutable at `oap/reports/224-a-demo-control-session-foundation.md`
SHA256 `975e175cbcec4b7429600c727b3241d9ea4c08a8b83244041bf8cba13baa8a1f`;
its order SHA256 is `1829d7375dc20e07e43620efb68bcca99c371a8eb67f4eb31a4cff026e86b8da`.
PR #383 is OPEN, unique, mergeable, remote head report-only SELF
`d23b13d72115c5b4a8cd13702802081a77e8e27c`, sole parent implementation
`6cf41974b9ba264afee0e79f44f2b3b81a7c0b9e`. The SELF diff contains only
the 224-a report. At root reconciliation 2026-11-13T01:50Z, seven of ten
intermediate-head checks were green and three were pending; none is a final
merge gate because this PR will be amended. Recheck CI during this round and
fix a demonstrated blocking 224-a failure within the SAME PR, reporting it.
There were no review threads. Other open PRs #379 and #319 are unrelated.

The shared coding checkout is on `oap/224-demo-web`. Protected untracked
`CODEX-SESSIONS.md`, `codex.sh`, and `uv.lock` have SHA256 respectively
`5ae1d77c17a367e86ef725a8f9d25aba3464b24f22fba77fd2808377f8c7feda`,
`66eda80258f6a4f13b88a9fe2ad5a69b9e7df226a4e503f57b35b6c6f03e1247`,
`d3d0e80db77da56e41795c619875ac14b5d25427d5169a7c9d2c8dee45b3b5b6`.
Hash only; do not read, stage, modify, or clean them. Root writes this exact
order and `oap/active=224-b` under the shared checkout before one control
`OK`; coding agent owns all Git actions. Use the existing right-pane coding
agent, no helper agents or model/profile changes. No further activation of
225 while PR383 remains unresolved.

## Exact-copy worker requirements

1. Add one purpose-built private worker orchestration path for a specific
   `demo_snapshot_requests.id`. It must claim a pending request through the
   224-a restricted worker control role, run ONE fresh 221 source export, run
   222 database sanitation and 223 file capture/verification for THAT new
   copy, re-read the private custody manifest and verified file manifest, and
   call `record_verified_handoff` with job ID, target DB, and exact combined
   verified state from that worker-held manifest. The public-safe `run`
   result currently omits job ID while `sanitize_copies` and `run_files_job`
   scan all eligible copies. Add the smallest internal exact-job selector or
   result contract needed; do not infer the selected job by directory order,
   timestamps, or target DB alone, and do not accidentally promote unrelated
   pre-existing copies. Preserve the safe existing CLI output contract.
2. The worker must prove that the manifest identity, target database,
   verified 222 state, 223 file state/digests, and copy expiry all agree
   immediately before publication. A string supplied by a caller is not
   verification. The worker, never the web role, owns the private custody
   path and seal key. Account disable or password reset during the job must
   prevent publication under the existing statement-time generation fence.
   A failed, interrupted, late, mismatched, or reused copy remains
   unpublished in a finite state and enters bounded cleanup/retry.
3. Provide a bounded worker-only invocation that can process a specific
   request and a recovery/cleanup invocation suitable for later scheduled
   operation. A finite claim/budget must prevent duplicate concurrent work;
   a stopped worker must leave an inspectable request and owned artifacts.
   Do not wire HTTP to spawn the privileged worker, normal Celery/Redis,
   provider forwarding, or inference. Any new control database connection
   must use a separate explicit worker-role credential, never the normal
   owner `DATABASE_URL`; document installation without printing secrets.
   Do not create production roles/grants implicitly. Provide exact operator
   grant/apply instructions for the reviewed 224-a matrix.
4. Cleanup must be exact and session-aware. A live, unexpired, enabled
   session's verified copy may not be deleted by a new job, generic expiry,
   copy-capacity pressure, or a concurrent cleanup worker. Logout/revocation,
   account disable/reset, request expiry, failed jobs, and restart recovery
   eventually mark `cleanup_pending`, drop ONLY the bound disposable target
   DB, and remove ONLY its owned file/dump custody leaves before marking
   `cleaned`. If removal fails, retain an inspectable state and retry safely;
   never claim cleaned while any bound artifact remains. Account disable must
   make the browser session unusable immediately by the 224-a per-use check;
   physical cleanup may be asynchronous. Do not delete an unbound/foreign
   job or a copy still owned by another request. Review the 221 startup
   `_expire_copies` and `max_copies` behavior explicitly so it cannot evict
   a published live copy. Prefer fail-closed admission over unsafe eviction.
5. Keep source-export, target-admin, control-worker, and later web roles
   distinct. Worker control role gets only 224-a column grants; web role
   never gets worker verification/custody or source business data. No new
   migration unless a concrete invariant is impossible with 0028; report
   that to root BEFORE adding schema. No general queue/job framework.

## Scope and verification

Expected product paths: a narrow new
`app/slaif_gateway/services/demo_web_worker.py`, small direct changes to
`services/demo_snapshot.py`, `services/demo_snapshot_sanitize.py`,
`services/demo_snapshot_files.py`, `services/demo_web_control.py`,
`cli/demo_snapshot_worker.py`, and `config.py` only as necessary for the
separate worker-control credential and exact-job interface. Matching
purpose-built tests in `tests/unit/` and `tests/integration/`, and
`docs/demo-admin.md` plus `docs/database-schema.md` only if schema/grant
facts change. Keep ordinary admin/API routes, `main.py`, provider adapters,
accounting/quota, migration 0028, templates, Compose/Nginx, and the public
demo UI untouched in this suffix. Tell root before an unavoidable new path
or scope expansion; routine direct test/fixture corrections are allowed when
their reason is documented. No duplicate evidence files or whole-suite
reruns for unchanged behavior.

Use synthetic owned PostgreSQL16 source and target plus restrictive roles;
verify one request produces one fresh exact 221→222→223 copy, manifest/job/
target binding matches persisted control row, and second request creates a
different copy. Verify two workers racing one request yield one claim and one
copy, no cross-request promotion by the global scanners, reset/disable and
late completion refuse publication, forged/foreign/missing manifest fails,
and copy-locator reuse fails. Test session-aware cleanup with a live session,
revoke/expiry, account disable, worker restart, missing/foreign leaves,
failure/retry, and no surviving bound artifacts after successful cleanup.
Use real PG role denials for web self-verification, worker credential reads,
and source business-table writes. Check safe CLI errors, logs and output for
secret/canary leaks. No production dump, provider call, mail, browser, or real
customer data. Focused tests plus scoped Ruff/Alembic/docs/diff; hosted CI
on the final amended head remains root's full gate. State honestly which
tests are mocked, owned PG, skipped, or not run. Existing gateway auth,
PostgreSQL quota/accounting, provider-secret isolation, and normal admin
behavior must remain untouched.

## Publication

Commit the already root-authored order and active pointer unchanged with
the implementation on the existing PR branch, push to PR383, and publish
one immutable `oap/reports/224-b-exact-worker-handoff-and-cleanup.md`. The
report states actual paths/commits, exact tests/exit codes, role and cleanup
evidence, CI/review status, limitations, and which later 224 suffixes remain.
Its report-only SELF commit has sole parent the implementation head and sole
diff the report. Check remote PR head, branch/base, order/active/report and
protected hashes; then write one exact response FIFO `OK` and rearm the
canonical control waiter. Do not merge or imply the demo is usable yet.
