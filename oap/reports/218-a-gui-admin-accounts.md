# 218-a immutable report — G17 GUI admin accounts (list/create/reset over the shared AdminService)

## Identity and activation

- Objective: 218, identifier `218-a` (CREATE_PR); ONE PR #375, branch
  `oap/218-gui-admin-accounts`; OPEN at publication, never merged, no
  auto-merge.
- Order: `oap/orders/218-a-gui-admin-accounts.md` (19,325 bytes,
  SHA-256 `626a8e650a329d40e75f36d3925f6645d0237a904a166c8a4ee30d648ce92d9c`),
  committed byte-unchanged (root-authored, bytes immutable).
- Active pointer: `oap/active` = exactly the five bytes `218-a`
  (no trailing newline; SHA-256
  `ade7c49ef61d3117cf73640472f540714506ff6aa76e426192d2eaabe7c35575`),
  unchanged.
- Base/remote main: `aacdc7b396d68a29f769117b6487e44df3e9ffcc`
  (merged PR #373 / predecessor 217-a: terminal, guarded merged, all 9
  checks / 3 workflows SUCCESS, root-recorded timing).
- The ONE exact control `OK` was consumed once by the canonical detached
  control waiter at activation (20:16Z, after root atomically published
  and re-verified the shared `oap/active` and order bytes). No further
  `control.fifo` reads, waits, or signals occurred in this turn.
- Protected untracked local files preserved BY HASH ONLY (never staged,
  never modified): `CODEX-SESSIONS.md`
  (`5ae1d77c17a367e86ef725a8f9d25aba3464b24f22fba77fd2808377f8c7feda`),
  `codex.sh` (`66eda80258f6a4f13b88a9fe2ad5a69b9e7df226a4e503f57b35b6c6f03e1247`),
  `uv.lock` (`d3d0e80db77da56e41795c619875ac14b5d25427d5169a7c9d2c8dee45b3b5b6`).

## Publication topology

Implementation head SHA: a8b62eaa1f2aaad52bf75daab09318cefafedf0b
Report publication commit: SELF

- ONE append-only implementation commit over base main `aacdc7b3`
  (no amend, no force-push):
  - `a8b62eaa` — 218-a: Implement G17 GUI admin accounts
    (list/create/reset over the shared AdminService) — shared
    service/transaction seams, the account router/templates, focused
    unit/native/browser qualification, documentation, and the
    root-authored order + active pointer.
- This report-only SELF commit has SOLE parent the literal
  implementation head `a8b62eaa1f2aaad52bf75daab09318cefafedf0b` and
  its diff contains ONLY this report file.
- PR #375: https://github.com/ulfe-lmi/slaif-api-gateway/pull/375
  (base `main`, head `oap/218-gui-admin-accounts`; title "Add
  privileged administrator account management to the console").
- GitHub checks on the final head are pending at publication; root
  verifies final-head checks, review, and the guarded merge.

## What this delivers (G17, bounded)

Closes the last open section 4 backlog item in
`docs/MISSING_GUI_FUNCTIONALITY.md` (section 20 delivery status): the
admin console's accounts area over the EXISTING shared services — no
new schema, no migrations, no dependencies, no second weaker reset.

- **Account list** (`/admin/accounts`): server-derived identity (name,
  email, exact stored role, active state, safe timestamps) with NO
  hashes/session tokens/secrets in the rendered HTML; bounded
  pagination through the existing list helper (a short page never
  implied complete); first ordinal, shared hyperlink sorting with its
  neutral marker, typed raw sort values, accessible scroll wrapper; a
  fixed-UUID reset-password link per row (server-derived target; no
  editable account UUID, hence no new record-choice kind).
- **Server-side authority**: every account view and action first passes
  the existing authenticated page/action context (`_admin_page_context`
  / `_admin_action_context` one-way reuse) and then requires the
  current persisted `superadmin` role on EVERY request (an ordinary
  `admin` gets a fixed 403 on every surface; hiding the link is not the
  gate). The existing dashboard-off gate, login rate limiting, and CSRF
  behavior are preserved.
- **Create** (`/admin/accounts/create`): ordinary `admin` by default;
  only the admin-vs-superadmin native choices; explicit confirmation
  REQUIRED for every create, with an additional explicit
  privileged-role acknowledgement for superadmin; bounded nonblank
  reason; bounded inputs validated BEFORE the expensive Argon2id
  hashing; email normalized/deduplicated through the shared service;
  the KNOWN duplicate-email condition answers fixed 409 (other faults
  give the honest fixed outcome, never raw SQL/exception text);
  passwords and hashes are never redisplayed.
- **Reset** (`/admin/accounts/reset?admin_id=<uuid>`): exact existing
  target entered from the list row link; server-derived identity
  displayed BEFORE confirmation, with the all-session consequence
  explained; the form is bound to its displayed fixed canonical target
  by URL (a conflicting hidden target is refused; the
  server-refetched identity re-renders on validation recovery);
  matching new password + confirmation, explicit confirmation, bounded
  reason; exact password bytes preserved (nonempty, at most 128
  characters, no trimming/normalization, NO minimum length, no
  strength policy); passwords never redisplayed on success OR failure,
  never in URLs/audit/logs; only the Argon2id hash persists.
- **Shared transaction** (root-verified design): a REQUIRED
  `AdminSessionsRepository` dependency on `AdminService` (all THREE
  existing CLI constructors and the new GUI composition supply the
  repository bound to the SAME session/transaction; no optional-None
  branch, no weaker fallback). Fresh locked target row
  (`get_admin_user_for_update` now performs a fresh ORM read under its
  existing row lock, `populate_existing=True`, preserving its existing
  SMTP consumer), new hash, revocation of ALL of the target's existing
  sessions, and the actor/target/reason audit commit together in ONE
  transaction (an audit failure rolls everything back; the committed
  audit carries the sanitizer-safe `revoked_count`). Login obtains the
  fresh locked row before password verification and the locked result
  is authoritative INCLUDING None (focused regression). Self-reset
  deliberately revokes the actor's own session, clears its cookie, and
  returns to safe login with a secret-free outcome. Sessions already
  running a request are NOT recalled; new requests with revoked
  sessions are refused from the moment the reset is committed.
- **Alias/secret guards**: free-text reason/name/email inputs matching
  a known incoming authentication value (existing request-aware alias
  helper) are refused before persistence and withheld on EVERY error
  re-render (no echo, full-response canaries); the reset-audit
  User-Agent is masked with the existing pure masker composition
  (`_safe_audit_user_agent`); fault paths use fixed secret-free
  outcomes (no raw exception/SQL parameter/hash traceback logging or
  rendering; a generic commit/connection fault is honest
  outcome-unconfirmed wording with account/audit verification before
  retry — never a false success or rollback promise).
- **CLI compatibility**: `admin create` / `admin reset-password` /
  `admin list` keep their commands, defaults, and outputs;
  `reset-password` now shares the console's transactional
  session-revocation behavior through the SAME shared service (one
  implementation), with honest offline CLI actor/reason provenance
  preserved.
- **No browser bootstrap**: no browser first-admin creation, no silent
  auto-elevation, no promotion path; first superadmin and break-glass
  remain CLI/offline; upgraded deployments with only ordinary admins
  get documented setup direction (CLI `admin create --superadmin`).
- **Bounded UI and ergonomics**: every visible entry/choice control
  carries meaningful linked field help (unique IDs, real DOM
  associations, no tooltip framework): 8 create + 4 reset controls;
  cream/teal/lime shell and local fonts retained; desktop/narrow
  (420 px, no horizontal overflow)/keyboard/no-JS flows; safe
  actionable error recovery.

## Concrete qualification commands and receipts

All commands run from the repository root; each direct pytest invocation
redirected to its log + `--junit-xml` with the exit captured IMMEDIATELY
before any display command (`PYTEST_EXIT=<rc>`), per the order's
provenance law. Venv: `/tmp/slaif216-qualification-venv`. Evidence dir:
`/tmp/slaif218/`.

1. **Order's exact shared-consumer unit list** (the order's literal
   command, final receipt):
   `env -u DATABASE_URL -u TEST_DATABASE_URL -u TEST_REDIS_URL
   /tmp/slaif216-qualification-venv/bin/python -m pytest
   tests/unit/test_admin_accounts_218.py
   tests/unit/test_admin_session_service.py
   tests/unit/test_admin_login_rate_limit.py tests/unit/test_cli_admin.py
   tests/unit/test_password_utils.py tests/unit/test_admin_usability_inventory.py
   tests/unit/test_admin_slaif_design.py tests/unit/test_oap_governance.py
   -q -p no:cacheprovider`
   → **PYTEST_EXIT=0**, 205 tests / 0 fail / 0 skip (junit-218-final-unit.xml,
   SHA-256 `5be00f8f504cb6fa50b7c6de4b77fe18274bf1e1255a60a997db26123aaeaa4f`,
   2026-11-11T00:18:58Z, 23.4 s), including the final-template
   inventory/design guards (111-field / 36-template baseline; 54
   sortable tables; 51 table wraps) and the 40-test 218 module.
2. **Native owned-PostgreSQL real-HTTP module**
   `tests/integration/test_admin_accounts_218_postgres.py` (reuses the
   qualified owned-PG fixture — ONE NEW labeled loopback tmpfs
   PostgreSQL 16, never an ambient database):
   `env -u DATABASE_URL -u TEST_DATABASE_URL -u TEST_REDIS_URL
   /tmp/slaif216-qualification-venv/bin/python -m pytest
   tests/integration/test_admin_accounts_218_postgres.py -q
   -p no:cacheprovider`
   → **PYTEST_EXIT=0**, 8 / 0 / 0 (junit-218-integration.xml,
   SHA-256 `a7c6a50b70fe199f34d211b47820300dfc0384bda4890923a628c8af7709d09a`,
   2026-11-11T00:17:30Z, 12.9 s). Covers real list/create/reset over
   HTTP, hashes-only persistence, exact actor/target/reason audit,
   EXACT password bytes (trailing space included), the KNOWN
   duplicate-email 409, the duplicate-commit race (uncommitted unique
   index entry; lock wait observed via `pg_stat_activity`), BOTH
   login-vs-reset race orderings with deterministic lock-wait
   synchronization (login-first: the committed login session is
   revoked, `revoked_count==1`, cookie refused; reset-first: the
   superseded password 401s with no session and the
   `admin_login_failed` row preserved — no sleeps as oracles, no
   mocked locks), and a pre-commit audit fault with FULL native
   rollback (hash unchanged, session not revoked, no audit row).
3. **Real-Chromium browser module**
   `tests/browser/test_admin_accounts_218.py` (real uvicorn app +
   owned PG + Chromium 158.0.8127.18; no Redis/Celery):
   `env -u DATABASE_URL -u TEST_DATABASE_URL -u TEST_REDIS_URL
   /tmp/slaif216-qualification-venv/bin/python -m pytest
   tests/browser/test_admin_accounts_218.py -m playwright -q
   -p no:cacheprovider`
   → **PYTEST_EXIT=0**, 6 / 0 / 0 (junit-218-browser.xml,
   SHA-256 `9a2c58c5d0faf10b0e6a0c86ea3771bcb2144c543d0a2ad074e9b3c0adb7dd05`,
   2026-11-11T00:18:05Z, 19.0 s): safe list rendering with
   server-derived UUID reset links (desktop capture); create with
   every visible control's resolved linked field help + native
   confirmation refusal + persisted outcome + duplicate 409 (full
   canaries, no raw SQL text); the list-link-bound reset flow with
   persisted consequences (new password signs in, old refused, in
   fresh browsers against real PG); self-reset logout + secret-free
   safe-login flash + revoked-session refusal; server-side
   ordinary-admin 403 on every account surface; narrow (420 px)
   no-overflow capture + keyboard-only REAL create + no-JS REAL reset.
4. **Existing native CLI consumer case** (shared reset/composition
   changed, as the order anticipated):
   `tests/integration/test_cli_admin_owner_records_postgres.py::test_admin_cli_create_reset_and_list_persist_safe_password_data`
   → **PYTEST_EXIT=0**, 1 / 0 / 0 (junit-218-cli-consumer.xml,
   SHA-256 `e8b7222b41e1cf783288f959d282dd20931b0109216025526d2053fab721a`,
   2026-11-11T00:00:22Z). The legacy module reads `TEST_DATABASE_URL`
   at collection, so a throwaway driver booted ONE NEW owned labeled
   loopback tmpfs PostgreSQL 16 (same label discipline as the
   qualified fixture), migrated it, pointed `TEST_DATABASE_URL` at it,
   and removed exactly the created container ID afterwards.
5. **Affected 215 SMTP claim cases** (the `get_admin_user_for_update`
   seam changed, as the order anticipated — only these two, no
   mail/browser matrix reruns):
   `tests/unit/test_admin_email_operations_215.py::test_claim_records_bound_identity_and_commits`
   and `::test_claim_refuses_duplicate_and_budget`
   → **PYTEST_EXIT=0**, 2 / 0 / 0 (junit-218-smtp-claim.xml,
   SHA-256 `34b1ba47ece27e3875ab2c06b0cd0560352977839f14112eb9e56f08a768e6f2`,
   2026-11-11T00:22:49Z).
6. **Documentation contract-drift/inventory/asof/logo/product-scope/rc2
   modules** (scoped to the actual docs updates):
   `tests/unit/test_documentation_asof.py
   tests/unit/test_documentation_contract_drift.py
   tests/unit/test_documentation_inventory.py
   tests/unit/test_documentation_logo.py
   tests/unit/test_product_scope_docs.py
   tests/unit/test_rc2_feature_scope_docs.py`
   → **PYTEST_EXIT=0**, 59 / 0 / 0 (junit-218-docs.xml,
   SHA-256 `17d904d1b00fe85bdc1b957ca1650eb5b699f8853470d57431ca2d93b0b2c6c8`,
   2026-11-11T00:15:30Z).
7. **Scoped Ruff** over all 13 changed/new Python files → 0 issues
   (after removing six unused imports/variables and one f-prefix in
   the NEW test files only); `git diff --check` → clean.

### Reused accepted receipts (no rerun)

- 19-test shared AdminSessionService/CLI/password unit module
  (junit-shared-unit.xml,
  SHA-256 `a2b550f6955c3b911d2bf8b97d3fdf528983d5a822169180f924cd112d7e71b2`,
  2026-11-10T21:05:26Z, PYTEST_EXIT=0) — independently verified and
  accepted by root; reused unchanged per the order's test economy.
- Earlier root-accepted scoped mock/ASGI/component proofs (auth-None
  fix, UA alias masking/clean metadata, real-template error canaries,
  synthetic unknown-commit outcomes, linked help) remain valid
  receipts for their seams.

### Honest provenance (superseded receipts and corrections)

- Standalone 40-test module run (junit-218-unit.xml, 2026-11-10T
  22:32:23Z, PYTEST_EXIT=0) predates the Ruff cleanup edits (unused
  imports/variables removed in the same files); the 00:18:58Z
  final-unit receipt is the authoritative run of the final module
  state.
- Browser run at 23:30Z (2 pass / 4 fail) and 23:54Z (4 pass / 2
  fail) exposed TEST-side artifacts only, corrected in
  `tests/browser/test_admin_accounts_218.py` within this same
  order/PR (no production change): (a) an assertion expecting the
  password field's live DOM value to be empty after a natively
  blocked submit (the browser keeps user-typed text; the
  server-redisplay law is proven by the full-body canary); (b) an
  action-attribute substring that included the attribute's closing
  quote (matches only an EMPTY target; replaced by the exact
  server-bound target assertions); (c) root2 login using the wrong
  per-account seeded password (the integration module seeds distinct
  passwords per account — `ROOT2_PASSWORD`); (d) the reset test
  relying on the 400 validation-recovery re-render to preserve the
  confirmation checkbox (it does not; safe fields such as reason ARE
  preserved, so the test re-types both password entries and
  re-checks the confirmation). The 00:18:05Z run is the final-state
  receipt.
- Unit run at 22:13Z (5 fail / 35 pass) corrected per root's review
  (obsolete min-12 expectation → the REQUIRED shared law is nonempty
  with the finite 128 GUI cap; cookie fixture domain scoping;
  full-body/log canary coverage; both password canaries; independent
  opaque provider secret) → 40/40 at 22:32:23Z.

## Documentation impact

Documentation updated:
`docs/MISSING_GUI_FUNCTIONALITY.md` (delivery-update paragraph +
section 20), `docs/admin-usability.md` (section 19),
`docs/verification/gui-cli-parity.md` (218-a shared-parity section),
`docs/runbooks/admin-access.md` (three enforced role boundaries,
console account administration, setup direction, lost-password GUI
path), `docs/security-model.md` (sessions paragraph, targeted role
boundaries, 218 section), `docs/database-schema.md` (§5.4 targeted
role semantics, §5.5 reset revocation rule; behavior prose only, no
DDL), `docs/cli-reference.md` (shared reset-session behavior),
`docs/configuration.md` (role semantics),
`docs/compatibility-matrix.md` (admin web auth row).
Documentation checked, no update needed because:
`docs/deployment.md` (the first-admin bootstrap sequence remains
accurate — first admin/break-glass are still CLI-first),
`docs/rc2-feature-scope.md` (no admin-account or GUI rows in scope),
and `README.md` (no admin-account claims present; logo preserved).
No schema/key-policy migration is claimed: there is none (no schema
change, no key-material/policy/quota/usage/replay change; existing
exceptions preserved). No claim that all GUI guidance or the final
installed qualification is complete — the 219 installed whole-GUI
gate remains open and is owned by 219.

## Honest limits (mock vs native vs browser vs installed)

- **Unit/ASGI**: preauthorized fake service/route/render seams with
  real Jinja template rendering where asserted — proves wiring,
  validation law, rendering canaries, and the locked-None
  authentication path; NOT native transaction or browser proof.
- **Native (owned PG, real HTTP)**: real FastAPI + real
  SQLAlchemy/asyncpg transactions on a real PostgreSQL 16: race
  orderings, revocation, rollback, and the CLI consumer are NATIVE
  proof (deterministic lock-wait synchronization via
  `pg_stat_activity`; no sleeps as oracles, no mocked locks).
- **Browser (real Chromium)**: real desktop Chromium against the real
  uvicorn app + owned PG — proves rendered DOM, linked help,
  keyboard/no-JS/narrow flows, and real user-visible outcomes; no
  Redis/Celery were involved (these flows require neither).
- **Installed/live**: NOT run. No installed-workflow,
  live-provider, deployment, or production claim follows from any
  result above. The final 219 installed whole-GUI qualification
  remains mandatory.
- GitHub final-head checks were still running at publication; root
  verifies them before the guarded merge.

## OAP governance and safety confirmations

- Coder never merges; no auto-merge, release, or deployment was
  enabled or performed. Root owns strategic review, the guarded merge
  of the exact reviewed SELF, and later objective 219. The full
  approved GUI goal remains ACTIVE through 219.
- ONE PR for objective 218 (PR #375); `218-a` created it. No 218
  commits existed before this turn's implementation commit; no 217
  commits were amended and no second 217 report was added.
- Predecessor 217-a / PR #373 is terminal (guarded merged; actual
  remote main `aacdc7b3…` with all 9 checks / 3 workflows SUCCESS);
  no 217 or 218 resignal occurred.
- Root's shared-worktree bytes (`oap/active`, the order) were
  committed byte-unchanged and re-verified after commit (hashes above
  match pre-commit values).
- No model/schema/migration/dependency/accounting/replay/provider/
  client-adapter changes; no new test framework or matrix; no helper
  agents/subagents/nested Codex; the SAME existing CLI/profile/model/
  effort was used throughout (native context maintenance at this
  boundary only).
- No secrets in logs, receipts, or this report; gateway/provider
  values in evidence are synthetic; the response OK and the single
  canonical control waiter rearm happen exactly once, AFTER this
  report is published and the remote topology is verified
  (response.fifo inode 4501470; root terminal 64194 is the sole live
  response reader; old terminals 94638/21178/24739 remain closed
  forever).
