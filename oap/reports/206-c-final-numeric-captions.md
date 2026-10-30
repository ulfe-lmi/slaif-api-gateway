# OAP Coding-Agent Report — 206-c

## Work order
- Identifier: 206-c
- Work-order file: `oap/orders/206-c-final-numeric-captions.md`
  (committed unchanged in IMPL; sha256
  `e37dbcf82474181aff77265ace9234b569851841f1e371139af67b478b97dd30`)
- `oap/active` pointer: value `206-c` (no trailing newline), committed
  in IMPL; sha256
  `59ac01c193f2e76d5b0c1288313e86402fb42879e0174ab2667ff6be77cc0ef5`
- Numeric objective: 206
- PR mode: CONTINUE_EXISTING_PR (unique PR #362, base main at
  `8d60d098b51cddb6351c6b843feb1a46db115616`; starting head
  `e31a0d38b4929a2a5355c6f54bc890a2c3e19fde` = the immutable 206-b
  report head)
- IMPL commit (literal): `696518cfa4d37431c7052dd711dcbc036385395d`
- Report publication commit: SELF (this report is the ONLY difference
  between SELF and IMPL; SELF's first parent is IMPL)

## Status
Implementation COMPLETE within the order's allowed paths. All five
final caption/readout corrections are in place and green locally
(unit 60 + directly-affected presentation 16 + governance 9, all
0 fail / 0 error / 0 skip; Ruff, `git diff --check`, and the
documentation checker clean). ONE scope conflict is reported, not
resolved by this commit: the 206-b head's previously-pending
PostgreSQL integration check has now COMPLETED as FAILURE on a
stale pre-206 literal display oracle in
`tests/integration/test_admin_catalog_readonly_postgres.py` — a file
outside this order's allowed paths. See the dedicated section below;
the C head inherits that one deterministic failure until the
strategic model/root resolves it (authorize the two-line oracle
update on this PR or issue a scoped follow-up order). GitHub
final-head checks on the C report head are PENDING (treated as
pending, not pass); strategic review and guarded merge are
root-owned. This is NOT a release/tag claim.

## Executive summary
Tiny presentation-only correction finishing the original GUI-number
consistency request (no new formatter, service, browser run,
database fixture, or infrastructure):

- Usage and audit list export caps render grouped in the visible
  caption via the existing `num` filter (`capped at 10,000 rows` for
  the configured default); the editable row-limit inputs, hidden
  fields, CSV parameters, and the actual ceilings keep the exact raw
  value (`value="10000"`).
- Usage-detail latency uses explicit `None` handling plus `num`, so
  an actual zero displays `0 ms` (never "missing" via truthiness),
  large values stay grouped (`1,234,567 ms`), and a missing value
  keeps `n/a ms`.
- The OpenAI-assisted result page groups the read-only summary
  quantities (`result.row_count`, `warnings|length`,
  `import_bridge.tsv_bytes`, `import_bridge.max_bytes`) while the
  generated TSV payload, textarea contents, links, source label, and
  hidden preview payload stay byte-for-byte; no OpenAI/provider call.
- Key-template detail groups the read-only
  `validity_days_default` readout (`1,234`), keeps `Not set` for
  `None`, and leaves the editable form placeholder/units literal.
- No unsafe Markup; normal autoescaping unchanged; no
  admin.py/formatting.py/service/DTO/model/migration/settings/JS/CSS
  or transport change.

## Focused results (local, current tree)
- `tests/unit/test_admin_numeric_display_206.py`: 60 PASS, 0 skip
  (the 54 accepted 206-a/b cases plus 6 NEW 206-c cases: the grouped
  export-cap captions with raw `limit` inputs on both `/admin/usage`
  and `/admin/audit` through the ASGI app; the latency
  `0 / 1234567 / None` -> `0 ms / 1,234,567 ms / n/a ms` matrix on
  the usage detail; the assisted-result grouped readouts
  (`<strong>1,234</strong>`, `<strong>3</strong>`,
  `TSV size: 23,480 bytes`, `Preview limit: 1,048,576 bytes`) with
  the 23,480-byte TSV asserted byte-for-byte in the rendered page,
  using a controlled `OpenAIAssistedProposalTextResult` and a
  no-op audit seam; and the real `templates/detail.html` rendered
  through the app's Jinja environment asserting
  `<dd>1,234</dd>` / `<dd>Not set</dd>` against the raw
  `valid_days` form default and the literal placeholder).
- Directly affected existing presentation suites
  (`tests/unit/test_admin_openai_assisted_catalog_routes.py`,
  `tests/unit/test_admin_activity_templates_safety.py`): 16 PASS,
  0 skip, NO assertion changes.
- OAP governance (`tests/unit/test_oap_governance.py`): 9 PASS,
  0 skip.
- Static: Ruff clean on the touched Python; `git diff --check`
  clean; `scripts/check_documentation.py` OK (133 files).
- Docs (allowed, short): a dated 206-c results/limitations note
  appended to
  `docs/verification/2026-10-29-admin-numeric-display.md`; the
  `docs/verification/README.md` index entry updated in place to
  cover 206-a/b/c; one sentence in `docs/admin-usability.md` for the
  completion captions and zero-safe latency.

## B-head PostgreSQL integration check failure and scope conflict
- Current GitHub state at C execution (refreshed before
  implementation): PR #362 OPEN/MERGEABLE, head `e31a0d38` (B
  report head), base main `8d60d098`, no auto-merge; only other open
  PR #319. On the B head, 9 of 10 checks SUCCESS (Unit/lint/migration
  head, Analyze x3, OpenAI-compatible E2E, Playwright browser smoke,
  Docker Compose smoke, Documentation hygiene, CodeQL); the
  previously-pending "PostgreSQL integration tests" check has since
  COMPLETED as FAILURE. The order's handoff snapshot ("9 checks
  SUCCESS, PG integration pending, no failure") predates that
  completion; this report supersedes it with the observed state.
- Failure (run 40985644692, job "PostgreSQL integration tests",
  1 failed / 519 passed / 9 skipped, 933.39 s):
  `tests/integration/test_admin_catalog_readonly_postgres.py::
  test_admin_catalog_readonly_pages` —
  `assert '0.100000000' in pricing_detail.text` (test line 227).
- Diagnosis: a STALE pre-206 literal display oracle, not a product
  regression. The pricing detail page renders
  `input_price_per_1m | num` (`pricing/detail.html` line 35) and the
  accepted formatter maps `Decimal("0.100000000")` to `"0.1"`
  (re-verified locally in this run); the same test also asserts
  `'0.920000000' in fx_detail.text` (line 237) while
  `fx/detail.html` renders `fx_rate.rate | num` -> `"0.92"`. The
  integration test file is unchanged since commit `f7ec8f5`
  ("Add read-only admin catalog pages", pre-206). It is the
  integration twin of the documented 206-a stale unit oracle (CI
  run 40980689318), which 206-b fixed in the unit layer; 206-b's
  scoped 309-case run covered unit presentation files only, so the
  integration oracle was never reached. The failure is
  deterministic: the assertion can never pass against the accepted
  206-a/b product behavior.
- Scope conflict (reported, NOT resolved here): correcting the two
  literal assertions requires editing
  `tests/integration/test_admin_catalog_readonly_postgres.py`, which
  is NOT in the 206-c allowed-paths list (the five templates,
  `test_admin_numeric_display_206.py`, and the two named unit
  presentation files only). Per AGENTS.md section 0.1, no
  precedence exception was invented and no edit outside the allowed
  paths was made. The C head therefore inherits this one
  deterministic PG-integration failure. Resolution is
  strategic/root-owned: either authorize the two-line oracle
  update on this same PR or issue a narrowly scoped follow-up
  order; no product behavior change is involved.

## Reused accepted A/B proof (not rerun)
- Root's independent rerun on the 206-b tree: 54 numeric unit tests
  plus the previously failing stale-zero-oracle test, 55 PASS.
- 206-b JUnit evidence: 54 unit / 309 directly-affected unit /
  3 browser PASS, 0 skip (owned labeled tmpfs PostgreSQL fixture,
  real Chromium/uvicorn, exact container cleanup).
- 206-a core evidence: raw-sort/legacy browser proof and the
  confirmed `0E-9` vs `1E-9` source distinction.
- Immutable earlier artifacts verified by sha256 in this run:
  206-b report `oap/reports/206-b-admin-numeric-display-completion.md`
  = `0ab9eeb9b61e85edcc551cae22cb7a06da5c6d8a0764a0e9f90dac8f483aad98`,
  206-b order `oap/orders/206-b-admin-numeric-display-completion.md`
  = `4b52e2e86b561a298eae8c18327f2ed116daae4dc063e8b789d0c4ff0413c64f`,
  206-a report =
  `6a9f989a080bdc25c791e5efd39360a4105b2ebbba4761542e26ca3e869e485f`,
  206-a order =
  `c1271db94f698fb8e1ca7726a8c0676848907ea33d2ae43801f450138a3f1e34`.
- No browser rerun (text-only existing-filter applications on
  already-accepted pages); no 660/309 full repeat; no
  provider/CLI/Codex/Redis/accounting matrix.

## Residual limitations
- Same layer separation as A/B: the new checks are unit ASGI renders
  with the existing fake-session seams plus one direct render of the
  real `templates/detail.html` through the app's Jinja environment
  (stub context, no DB). No real provider, mail, or production
  traffic.
- The C head's final checks are PENDING at publication; the
  PostgreSQL integration check is EXPECTED to show the same single
  stale-oracle failure as the B head until the reported scope
  conflict is resolved. All other checks are expected to hold as on
  the B head.
- No release, tag, deploy, merge, or production-certification claim.

## Publication invariants
- Single unique PR #362 amended (no new PR/objective); the remote
  PR head after push is this report-only SELF commit, whose first
  parent is IMPL `696518cfa4d37431c7052dd711dcbc036385395d` and
  whose only diff against IMPL is this report file.
- The C order and `oap/active` (value `206-c`) are committed
  unchanged in IMPL; the protected untracked files
  (`CODEX-SESSIONS.md`, `codex.sh`) remain untouched and
  uncommitted.
