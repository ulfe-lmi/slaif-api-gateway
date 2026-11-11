# OAP Coding-Agent Report — 220-a

## Work order
- Identifier: 220-a
- Work-order file: `oap/orders/220-a-demo-account-control.md` (root-authored, committed byte-identical; SHA256 `092a80e42c330f4d7e44239005235bf2bda5772e83334523aa62d6ad60e20cf9`, verified this turn)
- Numeric objective: 220
- PR mode: CREATED_NEW_PR

## Status
COMPLETE

## Executive summary
Objective-220 foundation implemented on one new PR (#377): CLI-managed fake-admin
accounts in an isolated `demo_control` PostgreSQL schema. One backward-compatible
Alembic successor of `0026_request_diagnostics` (0027) creates the schema,
`fake_admin_accounts`, and an append-only `fake_admin_account_events` table; no
roles are created and nothing is granted. A trusted operator CLI group
`slaif-gateway demo-admin` (create/list/enable/disable/reset-password) is the only
writable path. Passwords exist only as salted Argon2id hashes via the existing
primitive; input is via hidden prompt pair or bounded single-line
`--password-stdin` — there is no `--password` argv option. Account changes are
one owned PostgreSQL transaction with a monotonic `credential_generation` and one
bounded append-only event; a failed late write rolls back. Verified against a
real owned PostgreSQL 16 container including a least-privilege restricted role
(SELECT on fake accounts only; every DML/business read denied with SQLSTATE
42501). Foundation only: NO fake-admin login route, NO demo application, NO
Nginx/Compose profile; `/fakeadmin/login` remains 404 on the default live
gateway. One in-scope CI test repair (help-rendering dependency) was committed
and pushed as the final implementation commit before this report, per protocol
§12 step 15 and root direction.

## Authoritative GitHub state
- Repository: `ulfe-lmi/slaif-api-gateway`
- PR number: 377
- PR URL: https://github.com/ulfe-lmi/slaif-api-gateway/pull/377
- PR state at report time: OPEN (MERGEABLE)
- Base branch: `main`
- Head branch: `oap/220-demo-account-control`
- Starting remote SHA: `51677702cbc44673f2e60f924f6a1400eb2fa673`
- Implementation head SHA: `b134c429a16168ef8f907bed09d0aad946d6ec3d`
- Report publication commit: SELF
- Remote PR head after report publication: SELF (literal SHA derived from GitHub)
- Implementation commits pushed before the report commit:
  - `141115fd78bf366a458cf6550fbd63ee61976cdc` — 220-a implementation + unchanged root order + `oap/active` (22 files)
  - `b134c429a16168ef8f907bed09d0aad946d6ec3d` — in-scope repair of the new CLI test's terminal-width-dependent help assertion (1 file)
- Report commit first parent: same as Implementation head SHA
- Created a new PR this turn: yes
- Amended existing PR this turn: no
- Merge performed: NO

## Changes made
- `migrations/versions/0027_demo_admin_accounts.py`: successor head of
  `0026_request_diagnostics`. Creates `demo_control` schema,
  `fake_admin_accounts` (CITEXT `username` 3..64 shape/length-checked,
  case-insensitive unique `uq_demo_fake_admin_accounts_username`,
  Argon2id `password_hash`, `is_enabled`, monotonic nonnegative
  `credential_generation`, timestamps) and append-only
  `fake_admin_account_events` (FK `RESTRICT`, allowed-action CHECK, bounded
  reason, `credential_generation` at event time). Creates no roles, grants
  nothing, touches no business table. Downgrade drops both tables and
  `DROP SCHEMA demo_control` — documented as destructive for CLI-created demo
  state (hashes + event history), with required operator backup/review.
- `app/slaif_gateway/db/models.py`: the two demo-control SQLAlchemy models,
  consistent with the migration metadata.
- `app/slaif_gateway/db/repositories/fake_admin_accounts.py`: repository with
  database-side `COUNT(*)` scalar for the active-account count — disabling the
  last active account makes the count zero in the same transaction commit (the
  later demo login layer uses exactly this fact to 404).
- `app/slaif_gateway/services/fake_admin_accounts.py`: validation law
  (username 3..64 normalized `[A-Za-z][A-Za-z0-9_-]{2,63}`; password 16..128,
  not equal to username, credential-shaped input refused; reason 1..512,
  bounded, no-echo fixed errors); one-transaction state+event writes;
  idempotent enable/disable no-ops without fake audit; reset-password never
  re-enables; duplicate claimed ONLY for the exact username unique-constraint
  violation — every other `IntegrityError` (e.g. late event-insert fault)
  reports `demo_admin_account_create_unconfirmed` and rolls back.
- `app/slaif_gateway/cli/demo_admin.py` + `cli/main.py` registration:
  `demo-admin` group with `create`, `list`, `enable`, `disable`,
  `reset-password`. NO `--password` argv option (proven by a command-metadata
  assertion). Password input: hidden confirmation prompt pair or bounded
  single-line `--password-stdin` (≤128 Unicode chars; any extra line/trailing
  data/untranslated `\r` refused with one fixed no-echo error before any
  validation or DB access). `--reason` required; list bounds `--limit 1..100`,
  `--offset 0..1000000`. All failures (DB, duplicate, invalid parameter,
  BadParameter inside the async path) emit fixed safe errors via
  `handle_cli_error`; no raw DSN/password/hash/user-supplied secret reaches
  stdout/stderr/JSON/audit/OAP artifacts.
- Tests: `tests/unit/test_demo_admin_accounts.py` (43 tests: validator law,
  CLI safe-output and credential canaries, service transactional semantics,
  metadata-based no-`--password` argv proof) and
  `tests/integration/test_demo_admin_accounts_postgres.py` (8 tests on an
  owned PostgreSQL 16 container: migration upgrade, lifecycle, duplicate,
  idempotent disable/enable, reset-without-reenable, zero-after-last-disable,
  transactional late-failure rollback, and the restricted-role privilege
  boundary). Seven existing head-expectation tests updated to the new head
  `0027_demo_admin_accounts` (six alembic head tests + schema status).
- Documentation: `docs/database-schema.md` (actual successor head, new
  demo-control sections, 35-table inventory, explicit destructive-downgrade
  warning, least-privilege future demo-web role guidance with no live DSN),
  `docs/cli-reference.md` (new demo-admin section + command inventory), new
  `docs/demo-admin.md` (foundation/disabled labeling; precise control-role
  scope — the table-level SELECT includes the Argon2id `password_hash`, so a
  compromised web PROCESS holding that role could read the hashes while a
  compromised browser reaches no production business state and HTTP must never
  expose credential material; separate later snapshot read role),
  `docs/README.md` link.
- Root-authored `oap/orders/220-a-demo-account-control.md` and exact
  `oap/active` (`220-a`, 5 bytes) committed unchanged.

## Files changed
22 files in `main..b134c429`:
- `oap/orders/220-a-demo-account-control.md` (root-authored, unchanged)
- `oap/active` (exact `220-a`, unchanged)
- `migrations/versions/0027_demo_admin_accounts.py` (new)
- `app/slaif_gateway/db/models.py`
- `app/slaif_gateway/db/repositories/fake_admin_accounts.py` (new)
- `app/slaif_gateway/services/fake_admin_accounts.py` (new)
- `app/slaif_gateway/cli/demo_admin.py` (new)
- `app/slaif_gateway/cli/main.py`
- `docs/README.md`
- `docs/cli-reference.md`
- `docs/database-schema.md`
- `docs/demo-admin.md` (new)
- `tests/integration/test_demo_admin_accounts_postgres.py` (new)
- `tests/unit/test_demo_admin_accounts.py` (new)
- `tests/unit/test_alembic_accounting.py`
- `tests/unit/test_alembic_email_jobs.py`
- `tests/unit/test_alembic_external_tool_fence.py`
- `tests/unit/test_alembic_key_prefix_default.py`
- `tests/unit/test_alembic_provider_pricing.py`
- `tests/unit/test_alembic_quota_reservation_accounting_facts.py`
- `tests/unit/test_alembic_request_diagnostics.py`
- `tests/unit/test_schema_status.py`

## Acceptance-criteria evidence
### Criterion: isolated `demo_control` schema, backward-compatible successor migration
- Result: PASS
- Evidence: 0027 chains from `0026_request_diagnostics`; `alembic heads` →
  single head `0027_demo_admin_accounts`. Owned-PG16 integration run upgraded
  to head and ran the full lifecycle (8 passed). Downgrade path drops only the
  new schema/tables; docs state ordinary gateway business tables are
  unaffected in both directions.
### Criterion: no business-table, permission, quota, provider, or route changes
- Result: PASS
- Evidence: the migration creates only `demo_control` objects and no roles or
  grants; the probe role `slaif220a_probe` proves the migration grants it
  nothing. Restricted-role negatives: every INSERT/UPDATE/DELETE on accounts
  and events and every business-table SELECT failed with SQLSTATE 42501. No
  other production path modified (file list above).
### Criterion: CLI group with bounded commands; no `--password` argv; safe fixed errors
- Result: PASS
- Evidence: `test_no_literal_password_argv_option_anywhere` inspects
  `typer.main.get_command(app)` parameter metadata: password opts are exactly
  `{--password-stdin}` for `create`/`reset-password`, none elsewhere, and no
  `--password` anywhere (terminal-width independent). 43 unit tests cover
  validation bounds, hidden prompt, bounded stdin (oversized/two-line/CRLF
  transport), fixed no-echo errors, and credential canaries (synthetic
  hash/password/DSN never appear in any output).
### Criterion: one owned transaction, monotonic generation, idempotence, rollback, zero-active semantics
- Result: PASS
- Evidence: owned-PG tests assert state+event commit atomically, a simulated
  late-write failure rolls back the account change, repeat disable/enable are
  no-ops without extra events, reset-password on a disabled account stays
  disabled, and disabling the last active account returns active count zero
  in the same transaction (`COUNT(*)` scalar).
### Criterion: least-privilege restricted role on owned PostgreSQL 16, no live DSN printed
- Result: PASS
- Evidence: owned `postgres:16` container (label-guarded, loopback/tmpfs);
  synthetic role `slaif220a_web` granted only schema USAGE + SELECT on
  `fake_admin_accounts`: SELECT on accounts OK; all DML on accounts/events and
  all business-table reads → 42501; REVOKE then DROP ROLE cleanup. Only
  synthetic fixture credentials/DSNs are present in the test code; no LIVE DSN
  is printed anywhere (operator/bootstrap instructions contain no DSN at all).
### Criterion: documentation labels this PR foundation/disabled and documents rollback + role
- Result: PASS
- Evidence: `docs/demo-admin.md` states NO login route/demo app/Nginx profile
  in this PR; `docs/database-schema.md` documents the destructive downgrade
  with required operator backup/review and the least-privilege role guidance;
  `scripts/check_documentation.py` → OK (136 files); doc contract/asof/inventory
  tests pass (focused sweep below).

## Local verification
- `.venv/bin/python -m pytest tests/unit/test_demo_admin_accounts.py`: PASSED — 43 passed (re-run this turn at `b134c429`; also PASSED 43/43 in a disposable venv pinned to the CI-resolved versions typer 0.29.1 / click 8.5.1 / rich 15.0.0 / pytest 9.2.0)
- `.venv/bin/python -m pytest tests/integration/test_demo_admin_accounts_postgres.py`: PASSED — 8 passed (owned PostgreSQL 16 container, prefix `slaif220a`, loopback/tmpfs, label-guarded cleanup)
- Focused unit sweep at `b134c429` (demo-admin + all 40 `test_cli_*` files + all alembic head tests + schema status + OAP governance + documentation asof/contract/inventory/logo), `-n 8 --dist loadscope`, full output captured to a log: PASSED, direct pytest exit 0; exact count not emitted by quiet run
- `python scripts/check_documentation.py`: PASSED — OK, files=136
- `python -m ruff check` scoped to all 17 changed implementation/test/doc files: PASSED — All checks passed (re-run on the repaired test file this turn: PASSED)
- `git diff --check`: PASSED — clean
- `alembic heads`: PASSED — single head `0027_demo_admin_accounts`
- Full local suite / browser / client matrices: NOT RUN — explicitly deferred to the standard PR CI by the work order ("CI will run the broad standard checks; no full local suite..."). No GUI exists yet, so no browser feature qualification claim.

## GitHub CI / required checks
- Check state observed for implementation head `b134c429`: at report drafting,
  GitHub had not yet created check runs for this head (creation in progress
  immediately after the push); the check list is empty/new, so every required
  check for the implementation head is PENDING, not passed.
- Historical record (superseded head `141115fd` — NOT evidence for the
  implementation head): "Unit, lint, and migration head" FAILURE with 1 failed /
  7318 passed / 1 skipped; the single failure was this order's own new test
  `test_no_literal_password_argv_option_anywhere` — Rich-rendered help text
  wrapped `--password-stdin` under the CI runner's narrow terminal (locally
  green at width ≥ 60). Repaired in scope by `b134c429`, which asserts the
  exact argv surface from Click command metadata instead of rendered help text.
  Other superseded-head checks at last observation: 7 SUCCESS (CodeQL, Analyze
  (python), Analyze (javascript-typescript), Analyze Python, Docker Compose
  smoke, Documentation hygiene, OpenAI-compatible E2E tests) and 2 PENDING
  (PostgreSQL integration tests, Playwright browser smoke); the unit job is
  the 1 FAILURE described above (a failed job is never counted as PENDING).
- All required checks green for the implementation head at report drafting: no —
  PENDING (an empty/creating check list is recorded as PENDING, never as
  passed)
- Report-only commit may trigger fresh checks: strategic model must verify the
  `SELF` commit without rewriting this report
- Per updated root handoff instruction, strategic root holds the CI watch for
  `b134c429` and the `SELF` commit; this coding turn stops CI polling here.

## Local setup / dependencies
- Packages/tools/services installed or configured: none committed. Existing
  repo `.venv` (Python 3.12.15) used for focused verification; Docker
  `postgres:16` owned container for the integration tests; one disposable
  `/tmp` venv (typer 0.29.1, click 8.5.1, rich 15.0.0, pytest 9.2.0) used only
  to reproduce the CI-resolved rendering and validate the repaired test —
  never committed.
- `sudo`-level setup performed: none.
- Durable setup changes committed/documented: none.

## Documentation
- `docs/database-schema.md`: successor head 0027, demo-control schema/tables
  sections, 35-table inventory, explicit destructive-downgrade warning
  (CLI-created password hashes and append-only event history are deleted;
  operator backup/review required before downgrading past 0027; only ordinary
  gateway business tables are unaffected), and least-privilege future
  demo-web role guidance (no live DSN, no bootstrap secrets printed).
- `docs/cli-reference.md`: new `demo-admin` section and updated command
  inventory.
- `docs/demo-admin.md` (new): foundation/disabled labeling; implemented vs
  NOT-implemented boundaries; security law of the control path; precise
  control-role scope — it cannot read production business tables or mutate
  accounts, but its table-level SELECT includes the salted Argon2id
  `password_hash` (a compromised web PROCESS holding it could read those
  hashes; HTTP must never expose them), and it is separate from the later
  snapshot role that will read identity-masked copied business data.
- `docs/README.md`: link to the new guide.

## Safety and scope confirmations
- Unrelated files changed: no — only the work-order paths plus directly
  affected head-expectation tests and docs named by the order.
- Production secrets accessed: no.
- Production systems accessed: no — synthetic owned fixtures only; no live
  source snapshot, provider call, or mail.
- Required tests skipped/not run: focused runs returned direct pytest exit 0
  (quiet-run skip count not separately parsed, so no zero-skip claim); broad
  matrices NOT RUN by explicit work-order deferral to CI; 128-worker HPC
  qualification NOT RUN (root's responsibility per baseline).
- Scope deviation: no. The single extra implementation commit
  (`b134c429`) is an in-scope pre-report repair of this order's own new test,
  permitted by protocol §12 step 15 and directed by root; it changes only
  `tests/unit/test_demo_admin_accounts.py`.
- Extra PR created for same numeric objective: NO
- PR merged by coding agent: NO
- Activated order and `oap/active` edited by coding agent: NO (hash-verified
  this turn: order SHA256 `092a80e4…20cf9`; `oap/active` exactly `220-a`,
  SHA256 `1d7ee462…0f2b8`)
- Protected untracked files untouched: `CODEX-SESSIONS.md`
  (`5ae1d77c…feda`), `codex.sh` (`66eda802…1247`), `uv.lock`
  (`d3d0e80d…b5b6`) — hash-verified this turn; never read, staged, or modified.
- Report-publication commit changes only this report file: yes (verified
  post-commit: single changed path, first parent = implementation head)

## Known limitations / blockers
- Foundation stage only: no fake-admin login route, wait page, snapshot copy,
  identity masking, session invalidation platform, or demo application;
  objectives 221–224 own the rest. `/fakeadmin/login` remains 404.
- Final-head CI for `b134c429` is PENDING at report drafting; the strategic
  root independently watches/verifies it and the `SELF` commit before merge.
- The post-PR-220 128-worker HPC qualification remains NOT RUN (unchanged by
  this PR); no release, RC2, production, security, or compliance claim
  follows.
- No browser GUI exists yet; no browser feature qualification is claimed.

## Recommended strategic follow-up
Factual only: once the strategic root observes all required checks green for
`b134c429` and the `SELF` commit and is satisfied with the review, merge PR
#377 per root authority, then activate the next demo-round objective (221-a)
per `workorders/DEMO-ADMIN-ROUND-PLAN.md`.
