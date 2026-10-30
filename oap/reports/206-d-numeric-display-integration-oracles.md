# OAP Coding-Agent Report — 206-d

## Work order
- Identifier: 206-d
- Work-order file:
  `oap/orders/206-d-numeric-display-integration-oracles.md`
  (committed unchanged in IMPL; sha256
  `8d65e9b7f049a2efa7440afdf053076da1f5a016fd5c197b719311a37bc04028`)
- `oap/active` pointer: value `206-d` (no trailing newline), committed
  in IMPL; sha256
  `09dfdd8ac11e61faf80f9870395ef68cf1320ac44ef572b4a81e57802ab2ab9d`
- Numeric objective: 206
- PR mode: CONTINUE_EXISTING_PR (unique PR #362, base main at
  `8d60d098b51cddb6351c6b843feb1a46db115616`; starting head
  `39c045c3c507ba558232dd491effe2bfdb699bad` = the immutable 206-c
  report head)
- IMPL commit (literal): `cc9334b5ad3c180d61fb90e7ed25fa185a530685`
- Report publication commit: SELF (this report is the ONLY difference
  between SELF and IMPL; SELF's first parent is IMPL)

## Status
COMPLETE, test-only. The two stale pre-206 display expectations
reported by 206-c are corrected exactly as authorized; one focused
native run of the affected case on a fresh owned PostgreSQL 16
passed (1 PASS / 0 fail / 0 error / 0 skip) with exact-ID container
cleanup verified. No product code, template, shared formatter,
infrastructure, or policy change was made. GitHub final-head checks
on the C head were still IN_PROGRESS at execution (the PG
integration job was the known deterministic oracle failure); per the
order, that unchanged failure was not awaited. The final D head
requires every check successful before merge; those runs are PENDING
at publication (treated as pending, not pass). Strategic review and
guarded merge are root-owned. This is NOT a release/tag/deploy claim.

## Exact change (test-only)
In
`tests/integration/test_admin_catalog_readonly_postgres.py::
test_admin_catalog_readonly_pages` only:
- Line 227 replaced: `assert "0.100000000" in pricing_detail.text`
  now asserts the accepted `num`-rendered value bound to its named
  readout:
  `re.search(r"<dt>Input / 1M</dt>\s*<dd>0\.1</dd>", pricing_detail.text)`.
- Line 247 replaced: `assert "0.920000000" in fx_detail.text` now
  asserts `re.search(r"<dt>Rate</dt>\s*<dd>0\.92</dd>", fx_detail.text)`.
- Fixture Decimals `0.100000000` (line 70) / `0.920000000` (line 85)
  and ALL other assertions, persistence, auth, filtering, secret
  guards, and setup are unchanged. The new expectations accept only
  the exact rendered value in its named `<dd>` — not the old padded
  form and not a generic whole-page substring. The existing `import
  re` was sufficient; no product formatting was reverted.

## Source-scope proof
`git diff --stat 39c045c cc9334b` (C-SELF -> D-IMPL) shows exactly
five files: the one integration test, the short D note appended to
`docs/verification/2026-10-29-admin-numeric-display.md`, the
in-place `docs/verification/README.md` index update (206-a/b/c/d),
`oap/active` (206-c -> 206-d), and the unchanged D order. Zero files
under `app/`; no templates, settings, migrations, services, JS/CSS,
formatter, unit/browser files, conftest, dependencies, or workflow
changes.

## One focused verification (native PostgreSQL, owned)
- Method: the already-qualified existing fixture
  `tests.integration.test_lazy_throttling_postgres_redis.owned_pg_url`
  (its undecorated generator via `__wrapped__`) was opened by a tiny
  transient command (kept outside the repository,
  `/tmp/slaif206/run-206d-one-case.py`): it created ONE new owned,
  labeled (`slaif185a.owner`), 127.0.0.1-bound, tmpfs-backed
  `postgres:16` container, verified identity before use, migrated to
  head, and passed its URL to a child pytest as `TEST_DATABASE_URL`
  for exactly this one node. The generator was closed in `finally`;
  ambient `DATABASE_URL`/`TEST_DATABASE_URL` and real provider
  credentials were scrubbed, `APP_ENV=test` kept, and the URL was
  never printed (redaction applied to all captured output).
- Result: `test_admin_catalog_readonly_pages` — 1 PASS, 0 fail, 0
  error, 0 skip (3.413 s). JUnit retained locally at
  `/tmp/slaif206/pg-206d-1.xml` (sha256
  `135c28f908ffa428e1d4c8619d377fb7c4fd127d4c860bc4f28e7e2ddef4bca0`).
- Cleanup: the fixture's exact-ID removal reported
  `removed:46236e7f7685`; post-run `docker ps -a` for that exact ID
  and for the `slaif185a.owner` label returned no containers.
- No blocker was encountered, so no GitHub-gate fallback was needed;
  the final-head GitHub PG job still provides the full
  integration-suite regression gate.

## Static checks (touched paths only)
- Ruff clean on the touched test file; `git diff --check` clean;
  `scripts/check_documentation.py` OK (133 files); OAP governance
  (`tests/unit/test_oap_governance.py`) 9 PASS, 0 skip.
- NOT rerun (accepted proofs unchanged, per the order): the 206-c
  60/16 unit groups, the 206-b 54/309/3 groups, all browser/CLI/Codex/
  provider/Redis/accounting matrices.

## Reused accepted A/B/C proof
- Root's 206-b tree rerun: 55 PASS (54 numeric + stale oracle).
- 206-c local evidence: 60 numeric unit / 16 affected presentation /
  9 governance PASS, 0 skip; root's C actual-render 6 PASS.
- 206-a/b core evidence: confirmed `0E-9`/`1E-9` source distinction,
  raw-sort and exact-input law, accepted `num` formatter behavior —
  including the accepted rendering `Decimal("0.100000000") -> "0.1"`
  and `Decimal("0.920000000") -> "0.92"` that these corrected
  oracles now assert.
- Immutable earlier artifacts (verified by sha256 in the 206-c
  report and unchanged since): A/B/C orders and reports; C report
  = `284e51e4cc1c1b44003ecefca96b56be520f6c21d92143df9db433eb1dfb9e64`.

## Residual limitations and pending CI
- The local run proves exactly ONE node on one fresh owned PG16; it
  is not the full 519-case integration suite. That full gate is the
  final-head GitHub "PostgreSQL integration tests" check on the D
  head, PENDING at publication (pending is not pass).
- At execution, the C head's final checks were still in flight (PG
  integration IN_PROGRESS, inheriting the known deterministic
  oracle failure this order fixes); the D head supersedes them.
- No release, tag, deploy, merge, or production-certification claim.

## Publication invariants
- Single unique PR #362 amended (no second 206 PR/new objective);
  the remote PR head after push is this report-only SELF commit,
  whose first parent is IMPL
  `cc9334b5ad3c180d61fb90e7ed25fa185a530685` and whose only diff
  against IMPL is this report file.
- The D order and `oap/active` (value `206-d`) are committed in IMPL;
  the protected untracked files (`CODEX-SESSIONS.md`, `codex.sh`)
  remain untouched and uncommitted.
