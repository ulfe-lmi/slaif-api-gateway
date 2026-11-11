# OAP Work Order — 218-b

PR mode: CONTINUE_EXISTING_PR

## Objective, reason, and verified state

Finish objective 218 on its ONE existing PR #375 by repairing the demonstrated
final-head CI fixture defect and correcting the accounts-list visual evidence.
The human's whole-GUI mandate remains active through objective 219. This round
does not add product functionality or reopen the accepted account/session design.

Verified by root on 2026-11-11 before activation:

- `oap/active` was exactly `218-a`. Its unchanged 19,325-byte order has SHA256
  `626a8e650a329d40e75f36d3925f6645d0237a904a166c8a4ee30d648ce92d9c`.
- Immutable report `oap/reports/218-a-gui-admin-accounts.md`: 19,837 bytes,
  SHA256 `ecf2a6a7e6affd6d752a2dfee9d28f0bf84aaa1885077c8082a485aef5f11f3f`.
  Local and GitHub bytes match. Preserve this report and order unchanged.
- PR375 is OPEN, ready, MERGEABLE, base main, head branch
  `oap/218-gui-admin-accounts`, exact SELF
  `f9d123faf9028f6c8095527c58b9d90fac9274b4`. SELF's sole parent is implementation
  `a8b62eaa1f2aaad52bf75daab09318cefafedf0b`; its only diff is that report.
- Actual remote main remains `aacdc7b396d68a29f769117b6487e44df3e9ffcc` (217
  terminal, all nine main checks / three workflows accepted). Do not switch,
  reset, amend, rebase, or force-push to repair this round: append to this PR.
- Final-SELF CI run42931378875 has a demonstrated failed Unit, lint, and
  migration head job130230805882: 4 failed, 7,252 passed, 1 skipped. All four
  failures are in `tests/unit/test_admin_role_semantics.py`: its `_AdminUsersRepo`
  fake lacks `get_admin_user_for_update`. The production repository has the
  method and native locking proof is accepted. PostgreSQL job is still running
  at this review; E2E, browser, Compose, docs and both CodeQL workflows passed.
  Refresh all exact-head conclusions before your final handoff.
- Five code-quality threads were independently reviewed and resolved by root:
  two unused initial `last=-1` assignments are harmless; three BaseException
  catches are fixture cleanup or cross-thread propagation, not swallowed product
  failures. No repair or new cleanup round is justified by these notices.
- Unrelated PR319 (Dependabot) and PR374 (Codex namespace) remain open. Do not
  touch them. Ruleset23580289 is active (deletion/non-fast-forward protection,
  no bypass); other listed rulesets disabled. Only release is prerelease
  v0.1.0-rc.1. No release/tag/deployment authority exists.
- Root consumed the ONE exact response through terminal64194, exit0,
  RESPONSE_OK_EXACT. That terminal is CLOSED forever. Never repoll it or
  resignal218-a. The canonical control waiter is PID721175, cwd strategic root,
  TMUX_PANE=%9; verified FIFO inodes control4501469 / response4501470. Root will
  signal THIS round once after shared activation and own its new sole response
  terminal. No independent response reader or extra control signal.
- Same existing coding CLI PID3308462/right pane%9, profile/model/effort
  unchanged. No helpers, subagents, nested Codex, or extra coding processes.

Refresh the live PR/head and shared order before execution. Any unexpected
identity or unowned change is a conflict to report, not permission to overwrite.

## Allowed paths and exact requirements

1. `tests/unit/test_admin_role_semantics.py`: update ONLY the fake repository's
   interface to supply the required authoritative locked read, using its
   existing ID lookup semantics. Keep all assertions and existing active/inactive
   role/login and ordinary-admin legacy-operation behavior. Do not add a
   production fallback, make the lock optional, remove the lock, skip tests,
   loosen role gates, or change password/session semantics.
2. `tests/browser/test_admin_accounts_218.py`: the first test navigates from
   accounts to Operations before saving `218-accounts-list-desktop.png`, so
   that file currently depicts Operations. Capture the actual loaded accounts
   table BEFORE that navigation, keeping its existing assertions and the
   Operations navigation assertions. Do not alter accepted product visuals or
   create another evidence framework. Keep the same screenshot filename.
3. `docs/verification/gui-cli-parity.md`: narrowly correct the current G17
   receipt provenance if needed and record the bounded continuation. Reuse
   accepted receipts below rather than rerunning them for timestamps or names.
   Other historical objective sections remain intact; 219 owns whole-document
   current-state consolidation and the final installed workflow.
4. Commit the strategic-authored current order and `oap/active` byte-unchanged,
   plus your unique immutable `218-b` report. Preserve all 218-a history.

No product Python, templates, CSS, JS, schema, migrations, dependencies,
client/provider adapters, routing, accounting, quotas, replay, authorization,
credential transport or delivery changes are authorized by this fixture repair.
If old-head CI reveals another blocking issue, inspect its exact trace and
report to root while continuing independent work; do not invent another repair
scope or silently weaken tests. Routine corrections to these named fixtures
and report/documentation stay in this round and the SAME PR.

## Accepted evidence to reuse; precise limits

Root independently inspected the final source, real Jinja templates, native
test implementations, real-browser test implementations, JUnit bytes and
actual execution exit receipts. Accepted:

- Shared final unit command: 205 tests, 0 fail/error/skip, direct exit0;
  `/tmp/slaif218/junit-218-final-unit.xml` SHA256
  `5be00f8f504cb6fa50b7c6de4b77fe18274bf1e1255a60a997db26123aaeaa4f`,
  start2026-11-11T00:18:58.698256Z, 23.405s. This focused list did not include the
  older role-semantics fake, which explains the later broad-CI discovery.
- Native real-HTTP owned-PG: 8 tests, 0 fail/error/skip, direct exit0;
  `junit-218-integration.xml` SHA256
  `a7c6a50b70fe199f34d211b47820300dfc0384bda4890923a628c8af7709d09a`,
  start00:17:30.970415Z, 12.904s. Covers real shared hash/session/audit transaction,
  exact password bytes, duplicate race, unrelated sessions, self-reset, both
  actual row-lock race orderings (real PG lock-state synchronization), and
  pre-commit audit rollback. Reuse; no rerun for a test-fake/screenshot correction.
- Real Chromium/uvicorn/owned-PG: 6 tests, 0 fail/error/skip, direct exit0;
  `junit-218-browser.xml` SHA256
  `9a2c58c5d0faf10b0e6a0c86ea3771bcb2144c543d0a2ad074e9b3c0adb7dd05`,
  start00:18:05.867519Z, 19.027s. Root visually accepted create desktop/narrow;
  the named list PNG is Operations, so it is NOT accepted as list visual proof.
  Other unchanged successful create/reset/self/denial/keyboard/no-JS flows stand.
- Existing native CLI consumer: 1 pass, direct pytest exit0 on a newly owned PG;
  `junit-218-cli-consumer.xml` actual SHA256
  `e8b7222b41e1cf783288f959d282dd29020931b0109216025526d2053fab721a`,
  start2026-11-11T00:00:22.191855Z, 3.704s. 218-a report has a transcription typo
  in this SHA; state the correction in the NEW report, never rewrite the old one.
- Docs59: SHA256 `17d904d1b00fe85bdc1b957ca1650eb5b699f8853470d57431ca2d93b0b2c6c8`,
  start00:15:27.221505Z, 3.054s, exit0. The old report's 00:15:30 is completion.
- SMTP claim2: SHA256 `34b1ba47ece27e3875ab2c06b0cd0560352977839f14112eb9e56f08a768e6f2`,
  start00:22:49.458224Z, 2.700s, exit0. Earlier accepted shared19 and scoped
  root ASGI/mock/render canaries remain separately qualified; do not sum repeats.
- Atomic publication of 218-a report was independently confirmed: corrected
  successful fsync/temp/rename command00:26:11Z, exact local/remote bytes.

No installed whole-GUI, real-provider, production or release evidence follows
from the above. 219 remains mandatory after218 is terminal on actual main.

## Verification, safety, and setup

Use the existing `/tmp/slaif216-qualification-venv`; do not reinstall tools.
Run only the changed role-semantics unit module and the changed first browser
case, plus scoped Ruff, diff and OAP checks directly affected by publication.
Use direct pytest with saved log/JUnit and capture its exit immediately before
display commands. No full local unit/integration/browser/CLI matrices, repeated
205/8/6/59/19/2 receipts, or another inventory. GitHub's ordinary final-head
workflows run as usual and ALL required checks must eventually pass.

```bash
env -u DATABASE_URL -u TEST_DATABASE_URL -u TEST_REDIS_URL \
  /tmp/slaif216-qualification-venv/bin/python -m pytest \
  tests/unit/test_admin_role_semantics.py -q -p no:cacheprovider

env -u DATABASE_URL -u TEST_DATABASE_URL -u TEST_REDIS_URL \
  /tmp/slaif216-qualification-venv/bin/python -m pytest \
  tests/browser/test_admin_accounts_218.py::test_login_and_accounts_list_safe_rendering \
  -m playwright -q -p no:cacheprovider
```

For the browser case reuse the qualified owned-PG fixture: unique owner labels,
verified full container ID and loopback/tmpfs, remove only exactly owned resources;
never ambient database/Redis, production secrets/providers/mail, broad cleanup,
or new setup infrastructure. Preserve protected untracked CODEX-SESSIONS.md
(SHA2565ae1d77c17a367e86ef725a8f9d25aba3464b24f22fba77fd2808377f8c7feda),
codex.sh (66eda80258f6a4f13b88a9fe2ad5a69b9e7df226a4e503f57b35b6c6f03e1247),
uv.lock (d3d0e80db77da56e41795c619875ac14b5d25427d5169a7c9d2c8dee45b3b5b6),
BY HASH ONLY, never read/stage/modify. Preserve ignored .env/.codex and unowned
worktrees/processes. Secret-free synthetic test data only.

Existing secret protection, per-request persisted-role/session checks, CSRF,
exact password bytes, PostgreSQL transaction truth, reset/login row locking,
audit actor/target/reason, provider credential isolation, quotas and replay
ownership must remain unchanged. Do not add new machinery or claim certification.

## Publication, report and handoff

Follow repository AGENTS.md and OAP-COMMUNICATION-coding-agent.md. Append
implementation/correction commit(s) on PR375; do not create a new PR, amend,
force-push, merge or enable auto-merge. Inspect and address actual review gates
with root; nonblocking notices do not justify cosmetic product edits.

Update PR title/body to describe the final delivered G17 behavior and validation
for a reviewer without chat history; state restart/upgrade/session consequences,
no schema/key-policy migration, and that219 installed qualification remains open.
Record Documentation updated: and checked/no-update impact in the report.

Write the new report draft away from its final path. Publish once via temporary
file in `oap/reports`, flush+fsync+close, atomic rename, directory fsync. Include
literal implementation head, Report publication commit: SELF, sole-parent and
report-only topology, exact accepted/reused receipts and provenance errata,
precise mock/native/browser/installed limits, remaining CI/review states, safety
and protected-file hashes. Never edit any published report/order.

Create report-only SELF whose sole parent is the literal implementation head,
push, independently verify exact remote head/topology/order/active/report bytes,
then write exactly ONE two-byte OK to the canonical response FIFO. Root owns
the sole reader. After response, rearm exactly ONE canonical control waiter
targeting the existing coding pane%9 and return to idle; do not self-activate219,
send duplicate OK, or mutate the repository after immutable handoff. Root
reviews all final-head CI/material/review gates, guarded-merges the exact head,
verifies actual main's nine checks/three workflows and records timing before219.
