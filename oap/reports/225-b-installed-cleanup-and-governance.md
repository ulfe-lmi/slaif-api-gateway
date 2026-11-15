# OAP 225-b — Final Report (installed cleanup proof, review-thread
corrections, and canonical governance continuation)

## Commit topology

- Activation commit:
  `7a512a498a31dac177055c383ab667797b8d9a9a` (tree
  `97f1cad893fcdf71a43ca30d784ab0afe3bc515e`, sole parent
  `095900529fd20104127fcb4c5b2ad5a87e8ff85f`, the 225-a immutable
  report SELF) — committed the root-authored b order and the exact
  `oap/active` = `225-b` pointer unchanged, FIRST (2 files, +19/−1).
- Immutable order:
  `oap/orders/225-b-installed-cleanup-and-governance.md`, SHA256
  `5429af7f1d314f6cb6debecff3c3c4ed315686cc2e579c71216829465905bdfe`
  (re-verified at report time). First line exact
  `# OAP Work Order — 225-b`; `PR mode: AMEND_EXISTING_PR` is a
  standalone declaration line.
- Implementation head (sole SELF parent):
  `39d23a19dd20af1a9519df87f625e540bedcb8bb` ("225-b: post-logout
  physical cleanup proof, review-thread corrections, truthful current
  status"; sole parent the activation commit; 2 files, +168/−31:
  `tests/integration/test_demo_web_admin_gate_postgres.py`,
  `docs/demo-admin.md` — the exact allowed scope, nothing else).
- This report: report-only SELF, sole parent = the implementation
  head, sole diff = this file.
- PR: per the order's `AMEND_EXISTING_PR`, this commit amends the
  SAME unique PR #384 (branch `oap/225-demo-installed-acceptance`,
  base `main`). No second PR, no merge, no auto-merge.

## Item 0 — governance restored; immutable a-order defect preserved

- Focused `tests/unit/test_oap_governance.py`: 10/10, real exit 0
  (re-run at report time against the activation commit).
- 225-a order SHA256 `c5e288d721cd36425d14634c8b25a899b38af2a0b3d08f2013d175031e50fdb9`
  and 225-a report SHA256
  `87e17b55ffb787220adaebb7b6957998679d15c4ffba553f6ad7e49eff3f62d0`
  are byte-identical to the values recorded in the b order (re-verified
  at report time). The a order and the governance test were NOT edited.
- The a order's inline
  `PR mode: CREATE_NEW_PR. Objective 225: ...` line remains exactly as
  authored. The strict test passes on the b head because the active
  round is now the canonical `AMEND_EXISTING_PR` continuation — the
  same established canonical-metadata continuation pattern as
  Objective 190-d — not because the a-order defect was relaxed or
  rewritten.
- a-head hosted CI tracked to terminal (no rerun of unchanged local
  tests): run `43659243286` TERMINAL, conclusion failure — job
  results: Playwright browser smoke SUCCESS, PostgreSQL integration
  tests SUCCESS, Docker Compose smoke SUCCESS, OpenAI-compatible E2E
  tests SUCCESS, Documentation hygiene SUCCESS, and the sole failure
  `Unit, lint, and migration head` = the known a-order
  order-governance defect (independently reproduced locally). CodeQL
  `43659243371` SUCCESS and Code Quality `43659241012` SUCCESS per the
  activation-verified state. No a-head merge. a-head checks do not
  substitute for b-head checks.

## Review-thread corrections (the two exact automated threads,
gate-test file only)

- Removed the unused `_w_pub_key` assignment (original line 4570)
  together with the now-orphaned `_first_public_key_id` helper (its
  sole caller, original line 232) and the stale comment fragment
  referencing it. `_w_key`/`_w_route` remained in use and were kept.
- Replaced the `except BaseException as exc:  # noqa: B902` catch in
  the `_block_async` thread helper (original line 3858) with
  `except Exception as exc:`. This is the narrow safe handling for
  this helper: test-failure and error propagation is preserved via the
  result-dict re-raise at the join site (assertions still see the
  original exception), while `SystemExit`/`KeyboardInterrupt` now
  propagate naturally instead of being swallowed and re-raised. The
  helper was not refactored and error propagation was not weakened.
  (The unrelated `except BaseException:` at original line ~2676 in the
  224-v replay cleanup path is a different, legitimate failure-path
  catch and was deliberately untouched.)
- Ruff on the gate-test file at report time: All checks passed. Root
  may mark both threads resolved at the final head.

## Item 1 — post-logout physical disposal of copy A (installed
worker) in the existing real-Chromium test

Location: `test_browser_smoke_demo_copy_pages`, appended after browser
A's CSRF-verified sign-out and fresh-page authorization bounce; the
complete 225-a login/worker/no-op evidence in the same test is intact.

- The SEPARATE installed `demo-snapshot-worker cleanup --json` console
  script runs in its own subprocess under the existing minimal
  fixture-derived worker environment (225-a `_run_worker_subprocess`;
  provider/host secrets never enter; no raw streams into test output;
  failures would report a fixed safe code plus numeric rc).
- BEFORE the worker drops the bound database, the seven test-only run
  leaves are cleaned by EXACT name. The cleanup finalizer is
  idempotent and failure-safe: if the bound copy database is already
  gone it returns without error, so it can never mask the primary test
  outcome.
- Asserted in-test against the owned databases:
  - A's request row goes `verified_unpublished` (job-bound) →
    `cleaned`;
  - A's bound `demo_snap_` target database is physically dropped;
  - A's run-owned display-file custody (`custody/<job_a>/files`) is
    physically removed; the CLEANED manifest is retained for operator
    inspection (`STATE_CLEANED`);
  - still-active B remains `verified_unpublished`, its bound target
    database exists, and its copy is readable (leaf count >= 1) — the
    live-session copy retention law;
  - no unrelated source or target copy deletion: the `demo_snap_`
    database set after cleanup equals the pre-cleanup set minus
    exactly A's bound target;
  - source invariance: the source business-table digest plus
    `demo_control` request/session counts is identical before and
    after the cleanup;
  - worker cleanup stdout is safe vocabulary: contains no
    `demo_snap_` string, no target/copy database name, and no worker
    or web password.
- The order's refusal path (worker refuses cleanup for a genuine
  product reason → report the exact blocker for a same-PR c repair,
  no fence bypass, no authority broadening) did not occur: cleanup
  succeeded and all assertions held.

## Item 2 — truthful current status in docs/demo-admin.md

- The CURRENT top section's "Not a release claim" block no longer says
  Objective 225 is pending: it states that this PR (#384) supplies the
  acceptance, that the owned synthetic installed acceptance has
  **passed** (subject to final CI and merge), and that this is NOT a
  company deployment, release, or certification; no packaged
  Compose/demo-host automation exists.
- ONE dated note (2026-11-15, 225-b): the immutable a report's item 5
  describes the browser fixture's preservation (that test leaves its
  run-owned leaves and copies in place), while the separate
  `test_e2e_web_entry_full_cycle` in the same 6/6 owned run already
  proved worker cleanup (request `cleaned`, target database absent);
  225-b additionally proves physical cleanup in the real-browser A
  journey. Historical sections remain historical; no duplicate
  evidence ledger was added.

## Verification evidence

- Focused owned-PG16 browser test
  (`test_browser_smoke_demo_copy_pages`, including the new cleanup
  block): ROOT ran the exact test against the current 225-b diff
  using the known-good 225-a PG environment. Log
  `/tmp/225b-root-setup-check.log` shows a clean 100%-complete run
  with no failure summary; root reported `PYTEST_EXIT=0`, 1/1. This is
  labeled ROOT-RUN evidence, not a coding-side rerun.
- Focused `tests/unit/test_oap_governance.py`: 10/10, exit 0 (re-run
  at report time).
- Ruff on `tests/integration/test_demo_web_admin_gate_postgres.py`:
  All checks passed (report time). `py_compile` on the same file: OK.
- Docs hygiene: `DOCUMENTATION_CHECK=OK files=137` (report time).
- Reused, not rerun (order-allowed): the 225-a definitive 6/6 owned
  installed run (`/tmp/225a-pg-final.log`, `PYTEST_EXIT=0`,
  2026-11-15 00:29, real Chromium + installed worker/CLI), the 224
  component evidence, and the 225-a acceptance evidence. No unchanged
  local full matrix was rerun. The normal-admin byte oracle was not
  rerun because 225-b changes no templates or CSS.
- HONEST DISCLOSURE — owned-PG fixture credential instability
  (infrastructure, not a product or test defect): during 225-b,
  earlier coding-side invocations of this focused test failed at
  fixture setup with `InvalidPasswordError: password authentication
  failed for user "test"` on the source asyncpg connect (two identical
  attempts, log `/tmp/225b-pg-browser.log`; the test body never ran).
  Coding-side diagnostic experiments subsequently changed the fixture
  role state. Root then independently verified the fixture from their
  own shell (psql and the project .venv asyncpg, both owned ports, all
  four connections OK) and restored the two owned fixture roles. The
  focused test then passed in root's run (evidence above). No
  coding-side password change is in effect at report time; the owned
  fixture is root-owned and root-restored.

## Real vs mock (exact, b increment)

- REAL: the installed `demo-snapshot-worker cleanup` console script as
  a separate subprocess; the owned PG16 pair (real servers, real role
  matrix); the real Chromium browser session state (A signed out, B
  live) from the 225-a reworked test; physical database/file
  assertions against the real target and source servers.
- SYNTHETIC: all data remains the fictional 222 fixture with secret
  canaries; no real provider, mail, company data, or production
  credentials are involved. No docker image was built; no Redis.

## Limitations (honest)

- This is ACCEPTANCE continuation, not release, deployment, or
  certification; no such claim follows.
- Hosted CI on the final b SELF was PENDING at report time; root owns
  final-head reconciliation.
- The physical-cleanup proof covers the real-browser A journey in the
  owned synthetic fixture; the a-run e2e worker-cleanup proof covers
  the complementary scope. No new failure-mode or capacity surface was
  added by 225-b.

## GitHub state (observed at report time)

- PR #384: OPEN, MERGEABLE, base `main`
  `b593e5e96484dd9979dfe2960e0a7fbbc57c8301`, head branch
  `oap/225-demo-installed-acceptance`, head
  `095900529fd20104127fcb4c5b2ad5a87e8ff85f` (the 225-a report SELF)
  prior to this push. This report commit is pushed to the SAME PR per
  the order; no new PR, no merge, no auto-merge.
- Unrelated open PRs unchanged: #379, #319.

## Protected untracked files (untouched, unread, unstaged)

- `CODEX-SESSIONS.md`
  `5ae1d77c17a367e86ef725a8f9d25aba3464b24f22fba77fd2808377f8c7feda`
- `codex.sh`
  `66eda80258f6a4f13b88a9fe2ad5a69b9e7df226a4e503f57b35b6c6f03e1247`
- `uv.lock`
  `d3d0e80db77da56e41795c619875ac14b5d25427d5169a7c9d2c8dee45b3b5b6`
(SHAs re-verified at report time; they match the activation order's
recorded values exactly.)

## Objective status

Order items 0, 1 and 2 are complete with the local/owned and root-run
evidence above. The PR awaits hosted CI on the final b SELF and
strategic review; nothing is merged by the coding agent.
