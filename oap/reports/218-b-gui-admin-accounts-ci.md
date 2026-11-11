# 218-b immutable report — final-head CI fixture repair + accounts-list visual evidence (same PR #375)

## Identity and activation

- Objective: 218, identifier `218-b` (CONTINUE_EXISTING_PR); the SAME
  ONE PR #375, branch `oap/218-gui-admin-accounts`; OPEN at
  publication, never merged, no auto-merge, no force-push, no amend.
- Order: `oap/orders/218-b-gui-admin-accounts-ci.md` (11,584 bytes,
  SHA-256 `c76eebc72afa31f7f87e69dc4470d2bff58d0dd0770fd50f678ba647c6e7f4c1`),
  committed byte-unchanged (strategic-authored, bytes immutable).
- Active pointer: `oap/active` = exactly the five bytes `218-b`
  (SHA-256
  `c9fd9f358409f05556b6794181519ac13013af94a7664213070c1fdb95ade323`),
  committed byte-unchanged.
- 218-a preserved: its 19,325-byte order
  (`626a8e650a329d40e75f36d3925f6645d0237a904a166c8a4ee30d648ce92d9c`)
  and its immutable report
  `oap/reports/218-a-gui-admin-accounts.md` (19,837 bytes,
  `ecf2a6a7e6affd6d752a2dfee9d28f0bf84aaa1885077c8082a485aef5f11f3f`)
  are byte-unchanged in this round; all 218-a history is preserved.
- Base/actual remote main: `aacdc7b396d68a29f769117b6487e44df3e9ffcc`
  (217 terminal; nine checks / three workflows accepted). Not
  switched, reset, amended, rebased, or force-pushed.
- The ONE exact control `OK` for this round was consumed once by the
  canonical control waiter (PID 721175, the waiter armed at the 218-a
  handoff) and validated; it then exited. No further `control.fifo`
  reads occurred in this turn.
- Protected untracked files preserved BY HASH ONLY (never read, staged,
  or modified): `CODEX-SESSIONS.md`
  (`5ae1d77c17a367e86ef725a8f9d25aba3464b24f22fba77fd2808377f8c7feda`),
  `codex.sh` (`66eda80258f6a4f13b88a9fe2ad5a69b9e7df226a4e503f57b35b6c6f03e1247`),
  `uv.lock` (`d3d0e80db77da56e41795c619875ac14b5d25427d5169a7c9d2c8dee45b3b5b6`).

## Publication topology

Implementation head SHA: 10ecfaccb1eb8c6938c86c1f5b979035d53c6d16
Report publication commit: SELF

- ONE append-only correction commit over the 218-a SELF `f9d123fa`
  (no amend, no force-push):
  - `10ecfacc` — 218-b: final-head CI fixture repair (the
    role-semantics fake now supplies the 218-a required
    `get_admin_user_for_update` authoritative locked read with its
    existing ID lookup semantics; all assertions untouched) +
    accounts-list visual evidence capture order (the desktop capture
    is saved BEFORE the Operations navigation, same filename, all
    assertions kept) + the narrow `gui-cli-parity.md` G17
    provenance correction/218-b continuation + the strategic order
    and active pointer.
- This report-only SELF commit has SOLE parent the literal
  implementation head `10ecfaccb1eb8c6938c86c1f5b979035d53c6d16` and
  its diff contains ONLY this report file.
- PR #375: https://github.com/ulfe-lmi/slaif-api-gateway/pull/375
  (base `main`, head `oap/218-gui-admin-accounts`; title "Add
  privileged administrator account management to the console"; body
  updated to describe the final delivered G17 behavior,
  restart/upgrade/session consequences, no schema/key-policy
  migration, and that 219 installed qualification remains open).
  The title already described the delivered behavior and was
  retained.

## What this round changed (bounded; no product change)

- `tests/unit/test_admin_role_semantics.py`: the final-head broad CI
  failed 4 tests in this module (job 130230805882, run 42931378875:
  4 failed / 7,252 passed / 1 skipped) because its `_AdminUsersRepo`
  fake predates the 218-a required authoritative locked-read seam;
  the focused 205 list did not include this older fake, which is why
  it was discovered only in broad CI. The fake now supplies
  `get_admin_user_for_update` using its existing ID lookup semantics
  (same row or None). No production fallback was added, the lock is
  not optional, no test was skipped, no role gate was loosened, and
  no password/session semantics changed.
- `tests/browser/test_admin_accounts_218.py`: the first test saved
  `218-accounts-list-desktop.png` AFTER navigating from the accounts
  list to Operations, so the file depicted Operations and was NOT
  accepted as list visual proof. It now captures the actual loaded
  accounts table BEFORE that navigation (same filename; all existing
  list and Operations-navigation assertions kept; no other evidence
  framework). The re-captured image depicts the accounts table
  (ordinal column, sortable Name/Email/Role/Active/Created/Last-login
  columns, seeded rows with fixed-UUID Reset password links, and the
  bounded pagination footer).
- `docs/verification/gui-cli-parity.md`: narrow G17 receipt
  provenance correction (the three superseded intermediate runs are
  now cited to the final root-accepted JUnit receipts with SHA-256) +
  a short 218-b bounded-continuation record. Other historical
  objective sections untouched; 219 owns whole-document
  current-state consolidation and the final installed workflow.
- No product Python, templates, CSS, JS, schema, migrations,
  dependencies, client/provider adapters, routing, accounting,
  quotas, replay, authorization, credential transport, or delivery
  changes were made or authorized.

## Concrete verification commands and receipts (this round)

Direct pytest with saved log/JUnit; exit captured immediately before
display. Venv `/tmp/slaif216-qualification-venv` (no reinstall).

1. `env -u DATABASE_URL -u TEST_DATABASE_URL -u TEST_REDIS_URL
   /tmp/slaif216-qualification-venv/bin/python -m pytest
   tests/unit/test_admin_role_semantics.py -q -p no:cacheprovider`
   → **PYTEST_EXIT=0**, 5 / 0 / 0 (junit-218b-role-semantics.xml,
   2026-11-11T00:40:14Z, 4.05 s).
2. `env -u DATABASE_URL -u TEST_DATABASE_URL -u TEST_REDIS_URL
   /tmp/slaif216-qualification-venv/bin/python -m pytest
   tests/browser/test_admin_accounts_218.py::test_login_and_accounts_list_safe_rendering
   -m playwright -q -p no:cacheprovider`
   → **PYTEST_EXIT=0**, 1 / 0 / 0 (junit-218b-browser-list.xml,
   2026-11-11T00:40:43Z, 8.6 s) on the qualified owned-PG fixture
   (unique owner label, verified loopback/tmpfs identity, exactly the
   owned container removed; no ambient database/Redis, no production
   secrets/providers/mail, no new setup infrastructure).
3. Scoped checks directly affected by the changes/publication:
   `tests/unit/test_documentation_contract_drift.py
   tests/unit/test_documentation_asof.py tests/unit/test_oap_governance.py`
   → **PYTEST_EXIT=0**, 37 / 0 / 0 (junit-218b-docs-oap.xml,
   2026-11-11T00:44:19Z, 2.6 s); scoped Ruff over the two changed
   Python files → 0 issues; `git diff --check` → clean.

No full local unit/integration/browser/CLI matrices, no repeated
205/8/6/59/19/2 receipts, and no new inventory were run, per the
order's test economy.

## Accepted evidence reused (root-verified; not rerun)

- Shared final unit list: 205 / 0 / 0, exit 0;
  `/tmp/slaif218/junit-218-final-unit.xml`
  `5be00f8f504cb6fa50b7c6de4b77fe18274bf1e1255a60a997db26123aaeaa4f`,
  start 2026-11-11T00:18:58.698256Z, 23.405 s.
- Native real-HTTP owned-PG: 8 / 0 / 0, exit 0;
  `junit-218-integration.xml`
  `a7c6a50b70fe199f34d211b47820300dfc0384bda4890923a628c8af7709d09a`,
  start 2026-11-11T00:17:30.970415Z, 12.904 s (shared
  hash/session/audit transaction, exact password bytes, duplicate
  race, unrelated sessions, self-reset, both actual row-lock race
  orderings, pre-commit audit rollback).
- Real Chromium/uvicorn/owned-PG: 6 / 0 / 0, exit 0;
  `junit-218-browser.xml`
  `9a2c58c5d0faf10b0e6a0c86ea3771bcb2144c543d0a2ad074e9b3c0adb7dd05`,
  start 2026-11-11T00:18:05.867519Z, 19.027 s (create desktop/narrow
  visually accepted; the list PNG re-captured this round is the list
  visual proof; unchanged create/reset/self/denial/keyboard/no-JS
  flows stand).
- Existing native CLI consumer: 1 / 0 / 0, exit 0;
  `junit-218-cli-consumer.xml`, start
  2026-11-11T00:00:22.191855Z, 3.704 s.
- Docs contract modules: 59 / 0 / 0, exit 0;
  `junit-218-docs.xml`
  `17d904d1b00fe85bdc1b957ca1650eb5b699f8853470d57431ca2d93b0b2c6c8`,
  start 2026-11-11T00:15:27.221505Z, 3.054 s.
- SMTP claim cases: 2 / 0 / 0, exit 0; `junit-218-smtp-claim.xml`
  `34b1ba47ece27e3875ab2c06b0cd0560352977839f14112eb9e56f08a768e6f2`,
  start 2026-11-11T00:22:49.458224Z, 2.700 s.
- Earlier accepted shared 19-test unit receipt (2026-11-10T
  21:05:26.976195Z) and root's scoped ASGI/mock/render canaries
  remain separately qualified; repeats are not summed.

### Provenance errata (recorded here; the 218-a report is never rewritten)

- The immutable 218-a report transcribed the
  `junit-218-cli-consumer.xml` SHA-256 as a 61-character value
  (`e8b7222b41e1cf783288f959d282dd20931b0109216025526d2053fab721a`
  — three characters missing). The verified SHA-256 of the actual
  file bytes is
  `e8b7222b41e1cf783288f959d282dd29020931b0109216025526d2053fab721a`
  (64 hex characters), matching the value in the 218-b order. All
  other SHA-256 citations in the 218-a report were re-verified
  byte-exact against the actual files.
- The 218-a report's docs-module timestamp (00:15:30Z) is the
  completion time; the JUnit start timestamp is
  2026-11-11T00:15:27.221505Z.
- The `gui-cli-parity.md` G17 section originally cited three
  superseded intermediate runs (23:07:57Z native, 23:58:24Z browser,
  00:00:36Z unit list); it now cites the final root-accepted
  receipts above (narrow correction made in this round).

## Honest limits (mock vs native vs browser vs installed)

- Unit/ASGI evidence (including this round's 5-test role-semantics
  module) uses preauthorized fakes: it proves wiring and the
  authoritative-locked-read interface, NOT native transaction or
  browser proof.
- Native (owned PG, real HTTP) and browser (real Chromium + real
  uvicorn + owned PG) proofs stand at their accepted scopes above;
  no Redis/Celery, no live provider, no production secrets.
- Installed whole-GUI, real-provider, production, and release
  evidence: NOT run. The 219 installed whole-GUI qualification
  remains mandatory after 218 is terminal on actual main. No
  certification claim is made.

## Remaining CI and review state (refreshed at publication)

- On the pre-repair head `f9d123fa` (run 42931378875): the
  demonstrated failure was the `Unit, lint, and migration head` job
  130230805882 (4 failed / 7,252 passed / 1 skipped — all four in
  `tests/unit/test_admin_role_semantics.py`, the defect repaired
  above); E2E, browser, Compose, docs hygiene, and both CodeQL
  workflows passed; PostgreSQL integration was still running at
  that review.
- On the new exact head `10ecfacc` (CI run 42933846033, CodeQL runs
  42933846024 / 42933837707), refreshed at
  2026-11-11T00:47:07Z: CodeQL, Analyze (javascript-typescript),
  Docker Compose smoke, and Documentation hygiene have passed;
  Unit/lint/migration-head, PostgreSQL, E2E, Playwright, and
  Analyze (python) were still in progress at publication. GitHub's
  ordinary final-head workflows run as usual; ALL required checks
  must eventually pass, and root independently verifies the final
  head's checks/workflows, material and review gates before the
  guarded merge.
- Five code-quality threads on the 218-a head were independently
  reviewed and resolved by root (two unused `last=-1` initializations
  harmless; three BaseException catches are fixture cleanup /
  cross-thread propagation, not swallowed product failures). No
  repair or cosmetic cleanup was justified by these notices, and
  none was made.

## Documentation impact

Documentation updated:
`docs/verification/gui-cli-parity.md` (narrow G17 receipt
provenance correction + 218-b bounded-continuation record).
Documentation checked, no update needed because: the other 218-a
documentation updates remain accurate after this round (no product
behavior changed; only a test fixture, one test's capture order, and
the parity-doc provenance changed).

## OAP governance and safety confirmations

- Coder never merges; no auto-merge, release, tag, or deployment was
  enabled or performed. Root owns strategic review, the guarded
  merge of the exact head, actual-main nine-checks/three-workflow
  verification with terminal timing, and later objective 219. The
  full approved GUI goal remains ACTIVE through 219.
- One PR for objective 218 (PR #375); `218-b` amended the SAME PR
  (append-only). No new PR, no amend of earlier commits, no
  force-push. Unrelated PR319 (Dependabot) and PR374 (Codex
  namespace) were not touched. Ruleset protection (deletion /
  non-fast-forward, no bypass) respected.
- 218-a is closed out: its report/order remain immutable and
  byte-verified; the 218-a response terminal 64194 consumed the ONE
  exact response (RESPONSE_OK_EXACT, exit 0) and is CLOSED forever —
  never repolled, never resignedaled.
- Same existing coding CLI PID 3308462 / right pane %9, profile/model/
  effort unchanged; no helpers, subagents, nested Codex, or extra
  coding processes.
- Secret-free synthetic test data only; no secrets in logs,
  receipts, or this report. Existing secret protection,
  per-request persisted-role/session checks, CSRF, exact password
  bytes, PostgreSQL transaction truth, reset/login row locking,
  audit actor/target/reason, provider credential isolation, quotas,
  and replay ownership are unchanged; no new machinery added.
- Handoff: exactly ONE two-byte `OK` is written to the canonical
  response FIFO (inode 4501470) AFTER this report is published and
  the remote topology verified; root owns the sole reader for this
  round. Exactly ONE canonical control waiter is then re-armed
  targeting coding pane %9; 219 is NOT self-activated, no duplicate
  OK, and the repository is not mutated after the immutable
  handoff.
