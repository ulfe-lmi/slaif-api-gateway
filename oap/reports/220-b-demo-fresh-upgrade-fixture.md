# OAP Coding-Agent Report — 220-b

## Work order
- Identifier: 220-b
- Work-order file: `oap/orders/220-b-demo-fresh-upgrade-fixture.md` (root-authored, committed byte-identical; SHA256 `0945bc0ebda2ec1f8f272fa3b18df0defa609cff557f1421b9d109fa5483f8fb`)
- Numeric objective: 220
- PR mode: AMENDED_EXISTING_PR

## Status
COMPLETE

## Executive summary
Repaired the one demonstrated PostgreSQL integration-suite fixture failure
caused by the new `demo_control` schema, with a single bounded change to
`tests/integration/test_alembic_fresh_upgrade_postgres.py`. The bare
fresh-upgrade test's reset helper dropped only `public`, so `demo_control`
left behind by earlier migrated tests in the shared session database made
`0027_demo_admin_accounts.py:41` (`CREATE SCHEMA demo_control`) fail with
`DuplicateSchemaError`, cascading through the suite. The helper is now
`_reset_application_schemas`, which drops BOTH application-owned schemas
(`demo_control`, then `public`) before the first upgrade and in the `finally`
recovery path; the post-upgrade state assertion additionally verifies the
`demo_control` schema and its two tables exist after a fresh upgrade.
Migration 0027 is UNCHANGED (still strict `CREATE SCHEMA demo_control`, no
IF NOT EXISTS), and no product code, CLI, service, model, policy, or unrelated
test was touched. The failure order and focused recovery were verified against an owned, labeled,
disposable PostgreSQL 16 database on tmpfs and an isolated ephemeral Redis 7
container on loopback. The complete integration suite was executed once
against those CI-shaped test URLs and FAILED: 49 failed, 639 passed, 21
skipped. Objective 220 remains unresolved; this round changes only its
assigned fixture.

## Authoritative GitHub state
- Repository: `ulfe-lmi/slaif-api-gateway`
- PR number: 377
- PR URL: https://github.com/ulfe-lmi/slaif-api-gateway/pull/377
- PR state at report time: OPEN (MERGEABLE)
- Base branch: `main`
- Head branch: `oap/220-demo-account-control`
- Starting remote SHA (220-a report-only SELF): `5efa48373d3793d168bf27de849ab0bd1e58a103`
- Implementation head SHA: `824bfc0d6192bbb847a98745b6bd1da35d582b15`
- Report publication commit: SELF
- Remote PR head after report publication: SELF (literal SHA derived from GitHub)
- Implementation commits pushed before the report commit: `824bfc0d6192bbb847a98745b6bd1da35d582b15` — 220-b fixture repair + unchanged root order + `oap/active`
- Report commit first parent: same as Implementation head SHA
- Created a new PR this turn: no
- Amended existing PR this turn: yes (PR #377, same branch)
- Merge performed: NO
- Immutable 220-a artifacts preserved: 220-a order SHA256
  `092a80e42c330f4d7e44239005235bf2bda5772e83334523aa62d6ad60e20cf9`, 220-a
  report `oap/reports/220-a-demo-account-control.md` SHA256
  `15a8a80491d15f4008cf08f78feab130f0119634009aae4645697f248bbfaf5f` — both
  unchanged in this round's commits

## Changes made
- `tests/integration/test_alembic_fresh_upgrade_postgres.py` (ONLY product-test
  path changed):
  - `_reset_public_schema` renamed to `_reset_application_schemas` with a
    docstring explaining the strict 0027 schema creation; it now executes
    `DROP SCHEMA IF EXISTS demo_control CASCADE` before the existing
    `DROP SCHEMA IF EXISTS public CASCADE` / `CREATE SCHEMA public` / grant.
  - Used at BOTH call sites: before the first `command.upgrade(config, "head")`
    and in the `finally` recovery path (which re-upgrades to head, restoring
    both application-owned schemas for downstream migrated tests).
  - `_assert_fresh_upgrade_state` additionally asserts the `demo_control`
    schema's two tables (`fake_admin_accounts`,
    `fake_admin_account_events`) exist after a fresh upgrade.
  - Kept unchanged: the `version_num` column-length check, the current-revision
    equality check, and the expected public-table assertion.
- `oap/orders/220-b-demo-fresh-upgrade-fixture.md` and exact `oap/active`
  (`220-b`) committed unchanged.
- NOT changed (verified by diff): `migrations/versions/0027_demo_admin_accounts.py`
  (strict `CREATE SCHEMA demo_control` retained — an unknown pre-existing
  schema must not be silently adopted), all app/ product code, all other
  tests, and all operator documentation (no doc change was needed for a
  test-fixture-only repair).

## Files changed
- `tests/integration/test_alembic_fresh_upgrade_postgres.py` (modified)
- `oap/orders/220-b-demo-fresh-upgrade-fixture.md` (new, root-authored, unchanged)
- `oap/active` (modified to exact `220-b`)

## Acceptance-criteria evidence
### Criterion: bare fresh-upgrade test resets BOTH application-owned schemas before first upgrade and in finally recovery
- Result: PASS
- Evidence: diff above; `DROP SCHEMA IF EXISTS demo_control CASCADE` precedes
  the public reset inside `_reset_application_schemas`, invoked at both call
  sites.
### Criterion: failure order proven before the repair (migrated test, then bare fresh-upgrade test)
- Result: PASS (failure reproduced exactly)
- Evidence: pre-fix run
  `pytest tests/integration/test_accounting_finalization_postgres.py tests/integration/test_alembic_fresh_upgrade_postgres.py`
  on the owned CI-like database → direct pytest exit 1;
  `asyncpg.exceptions.DuplicateSchemaError: schema "demo_control" already
  exists` raised at `migrations/versions/0027_demo_admin_accounts.py:41`
  (`op.execute("CREATE SCHEMA demo_control")`) while running upgrade
  `0026_request_diagnostics -> 0027_demo_admin_accounts`;
  `FAILED ...test_bare_fresh_alembic_upgrade_head_creates_wide_version_table`
  (bounded log preserved; synthetic test credentials only).
### Criterion: both `public` and `demo_control` correctly restored for a downstream migrated integration test
- Result: PASS
- Evidence: post-fix focused sequence in one pytest invocation —
  `test_accounting_finalization_postgres.py` (migrates, leaving
  `demo_control` behind) → `test_alembic_fresh_upgrade_postgres.py` (resets
  both schemas, upgrades, asserts) → `test_admin_accounts_218_postgres.py`
  (downstream migrated test) → direct pytest exit 0, progress
  `.............. [100%]`, no failed/error/skipped markers (14 tests).
  Post-run inspection of the owned test DB: `public` fully migrated (34
  tables), `demo_control` present with 2 tables,
  `alembic_version = 0027_demo_admin_accounts`.
### Criterion: migration stays strict; no IF NOT EXISTS
- Result: PASS
- Evidence: zero diff in `migrations/`; the pre-fix reproduction itself is the
  proof that 0027 still refuses to adopt a pre-existing `demo_control`
  (DuplicateSchemaError), i.e. production semantics unchanged.
### Criterion: bounded path — no business logic/CLI/service/model/admin/policy/quota/provider changes, no unrelated tests
- Result: PASS
- Evidence: round diff = one integration test file + order + active only
  (`git diff --name-only`); `git diff --check` clean; scoped Ruff clean.
### Criterion: complete integration suite run ONCE after repair against owned CI-like URLs
- Result: EXECUTED ONCE; FAILED — direct pytest exit 1 (49 failed, 639 passed, 21 skipped in 1748.73s). The focused migration repair passed; the whole suite did not.
- Evidence: The first bare fresh-upgrade test no longer fails. A second reset fixture in `test_readyz_postgres.py` leaves `demo_control` behind and fails when its `finally` recovery re-runs strict migration 0027, after which later database failures cascade. Before that, two local installed catalog-refresh cases failed (a browser element bottom at 916.5px versus 900px, and an FX-stale fixture dated 2026-10-12) and two quota reconciliation assertions failed with `ReconciliationInvariantError`. Those distinct failures were not changed or attributed to the 220-b patch. Root will scope a 220-c continuation for the second schema-reset fixture; final hosted CI remains necessary.

## Local verification
- Pre-fix failure reproduction (command in Criterion 2): FAILED as specified — direct pytest exit 1; `DuplicateSchemaError` at `0027_demo_admin_accounts.py:41`
- Post-fix focused sequence (Criterion 3): PASSED — direct pytest exit 0; 14 tests, no failed/error/skipped markers
- Complete `tests/integration` suite (owned CI-like `TEST_DATABASE_URL=postgresql+asyncpg://test:test@127.0.0.1:54341/slaif220btest`, `TEST_REDIS_URL=redis://127.0.0.1:6381/0`, serial exactly as CI): FAILED — direct pytest exit 1; 49 failed, 639 passed, 21 skipped in 1748.73s (0:29:08). The full run is negative evidence, not a pass.
- `python -m ruff check tests/integration/test_alembic_fresh_upgrade_postgres.py`: PASSED — All checks passed
- `python -m alembic heads`: PASSED — single head `0027_demo_admin_accounts (head)`
- `git diff --check`: PASSED — clean
- Distinguishing local vs hosted: local run used local dependency versions
  (venv Python 3.12.15; asyncpg 0.32.0, SQLAlchemy 2.1.8, pytest 9.2.0) against
  owned PostgreSQL 16.15 + Redis 7; hosted CI final-head checks remain the
  authoritative gate and are PENDING (see CI section). The full local suite reported 21 skips; the focused sequence returned direct exit 0. Local installed-client/browser/FX outcomes differ from hosted CI coverage and are reported separately, not silently waived.

## GitHub CI / required checks
- Check state observed for implementation head `824bfc0d6192bbb847a98745b6bd1da35d582b15` at report drafting: 9 of 10 checks SUCCESS (Analyze Python, CodeQL, Unit/lint/migration head, Analyze (javascript-typescript), Analyze (python), Docker Compose smoke, Documentation hygiene, OpenAI-compatible E2E tests, Playwright browser smoke) and 1 PENDING (PostgreSQL integration tests). The distinct `test_readyz_postgres.py` fixture defect documented above is present unmodified in the code at this head. All unfinished or queued required checks remain PENDING, not passed; the report-only SELF will require its own exact-head check inventory.
- Stale/broken GitHub state recorded as observed (NOT passes, NOT results for
  the implementation head): the initial-run (head `141115fd`) integration
  job's `Run integration tests` step completed FAILURE at 20:22:49 UTC.
  GitHub later reconciled the run as COMPLETED FAILURE and its hosted log
  confirmed `DuplicateSchemaError` at `CREATE SCHEMA demo_control`; the
  subsequent many failures were cascades. Earlier queued/in-progress and
  HTTP 502 observations were transient outage states, not passes. Root
  reproduced that first failure locally before this scoped fix.
- All required checks green for the implementation head at report drafting: no
  — PENDING
- Report-only commit may trigger fresh checks: strategic model must verify the
  `SELF` commit without rewriting this report
- Per root, final-head checks (all ten checks and three workflows on the
  report SELF) are root's merge gate.

## Local setup / dependencies
- Packages/tools/services installed or configured: none committed. Owned,
  labeled, disposable fixtures on loopback (PostgreSQL data on tmpfs): Docker `postgres:16`
  (PostgreSQL 16.15) container `slaif220b-pg` at 127.0.0.1:54341 (database
  `slaif220btest`, tmpfs data directory) and Docker `redis:7` container
  `slaif220b-redis` at 127.0.0.1:6381, both labeled `oap=220b`
  `owner=slaif-codex` and removed after verification.
- `sudo`-level setup performed: none.
- Durable setup changes committed/documented: none.

## Documentation
- No operator documentation change: this is a test-fixture-only repair with
  unchanged migration/product semantics; the work order states no doc change
  is expected and none was needed.

## Safety and scope confirmations
- Unrelated files changed: no — exactly one in-scope test file plus the
  root-authored order and `oap/active`.
- Production secrets accessed: no.
- Production systems accessed: no — owned labeled disposable containers on
  loopback only, with PostgreSQL data on tmpfs; no ambient `DATABASE_URL`, no provider calls, no mail,
  no real credentials (only synthetic fixture credentials in logs).
- Required tests skipped/not run: The full local suite had 21 skips and 49 failures; no full-suite pass is claimed. Hosted exact-final-head checks remain pending. No separate provider/live production tests were authorized or run.
- Scope deviation: no — distinct failures DID appear in the complete local
  suite, including the separate `readyz` fixture; they are reported to root
  here and no out-of-scope file was changed.
- Extra PR created for same numeric objective: NO
- PR merged by coding agent: NO
- Activated order and `oap/active` edited by coding agent: NO (220-b order
  committed byte-identical; `oap/active` exact `220-b`)
- Protected untracked files untouched: `CODEX-SESSIONS.md`
  (`5ae1d77c17a367e86ef725a8f9d25aba3464b24f22fba77fd2808377feda`),
  `codex.sh` (`66eda80258f6a4f13b88a9fe2ad5a69b9e7df226a4e503f57b35b6c6f03e1247`),
  `uv.lock` (`d3d0e80db77da56e41795c619875ac14b5d25427d5169a7c9d2c8dee45b3b5b6`)
  — hash-verified this turn; never read, staged, or modified.
- Test cleanup scope: only the owned labeled containers and the disposable
  test database were affected.
- Report-publication commit changes only this report file: yes (verified
  post-commit: single changed path, first parent = implementation head)

## Known limitations / blockers
- The complete local integration run FAILED (49 failed, 639 passed, 21
  skipped). It confirms the assigned fresh-upgrade fixture repair, but a
  second `readyz` reset fixture fails on `demo_control`; earlier installed
  catalog-refresh and quota assertions also failed locally. No full-suite
  pass or hosted-CI substitution is claimed.
- Final-head CI for `824bfc0d6192bbb847a98745b6bd1da35d582b15` and the `SELF` commit is PENDING at report
  drafting; root independently verifies all ten checks and three workflows
  before merge.
- The initial-run GitHub job (head `141115fd`) eventually reconciled as
  COMPLETED FAILURE; its hosted log confirms the pre-fix DuplicateSchema.
  Later implementation/report-head checks remain required and are not
  inferred from the local run.
- Foundation-stage context unchanged: no public demo access, real source
  snapshot, deployment, provider call, or release in this round.

## Recommended strategic follow-up
Factual next step: objective 220 is unresolved. Root should publish a
bounded 220-c order on the SAME PR for the separate `readyz` schema-reset
fixture, review the distinct local catalog-refresh/quota failures against
current hosted evidence, and merge only after all ten final-head checks and
three workflows succeed. Then verify actual main (nine checks / three
workflows), record timing, and only then activate 221-a.
