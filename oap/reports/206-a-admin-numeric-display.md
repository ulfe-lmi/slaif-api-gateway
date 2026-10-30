# OAP Coding-Agent Report — 206-a

## Work order
- Identifier: 206-a
- Work-order file: `oap/orders/206-a-admin-numeric-display.md`
  (committed unchanged in IMPL; sha256
  `c1271db94f698fb8e1ca7726a8c0676848907ea33d2ae43801f450138a3f1e34`)
- `oap/active` pointer: value `206-a` (5 bytes, no trailing newline),
  committed unchanged in IMPL; sha256
  `83a77ffc9d2f829089897888d3f2fc8c141e36ad3563c8d4df7d6d12d3a1235a`
- Numeric objective: 206
- PR mode: CREATE_NEW_PR (unique PR #362, base main at
  `8d60d098b51cddb6351c6b843feb1a46db115616`)
- IMPL commit (literal): `dc532ba3a29e628c16e87e7997801e0649ed8f97`
- Report publication commit: SELF (this report is the ONLY difference
  between SELF and IMPL; SELF's first parent is IMPL)

## Status
Implementation COMPLETE within the order's allowed presentation
paths; focused verification green locally (unit 37 + admin batch 660
+ browser 3 new, existing browser 10, governance 9 — all 0 fail / 0
error / 0 skip). GitHub final-head checks on the report head are
PENDING (treated as pending, not pass); strategic review and guarded
merge are root-owned. This is NOT a release/tag claim.

## Executive summary
Small, presentation-only admin GUI fix: read-only numeric readouts
now render locale-stable (comma thousands, decimal dot, no
scientific notation, exact values), token quantities display in
millions of tokens with the exact comma-grouped count in
`title`/accessibility text, and the confirmed `0E-9` exponent-zero
rendering is corrected to `0` while true positive `1E-9` values keep
their exact digits. Machine-facing surfaces (raw `data-sort-value`
sort keys, editable inputs, hidden fields, payloads, CSV/API/CLI/
JSON, identifiers, dates, versions, raw JSON/code) are unchanged; no
services, schema, migrations, auth, JS/CSS, or accounting changes.

## Scope and confirmed cause
- Confirmed `0E-9` source: PostgreSQL `Numeric(18,9)` → Python
  `Decimal`; a stored zero quantized to the 9-dp quantum renders by
  `str()` as `0E-9` (visible in the keys-detail Chat streaming
  live-burn cost margin readout and its form input; most other
  readouts interpolated raw Decimals/ints without grouping).
- `0E-9` is an EXACT zero → renders `0`. `1E-9` is a true positive
  0.000000001 → renders `0.000000001`; a small positive price or
  margin is never displayed as a free zero. No data cleanup,
  epsilon, or accounting rounding is authorized or used.
- Missing values stay missing: `None` never becomes `0`; templates
  keep `Unlimited` / `n/a` / `Unknown` / `Not set` labels. A present
  actual cost of zero displays in preference to the estimate
  (usage detail previously fell through a truthiness chain).

## Changes (IMPL; all order-allowed paths)
- `app/slaif_gateway/web/formatting.py` (NEW, pure helpers, plain
  strings only, no Markup): `format_number` (grouped dot-decimal,
  exact int/Decimal/numeric-string, no float round-trip; unneeded
  fractional zeros stripped; actual zero → `0`), `format_tokens_m`
  (>=1M: 3-dp ROUND_HALF_UP, trailing zeros stripped, magnitude
  comma-grouped; <1M: exact power-of-ten shift, no positive value
  rounds to zero), `format_raw_decimal` (canonical ungrouped/
  unscaled exact decimal for sort keys; `None` → empty),
  `format_input_decimal` (raw editable input: a zero-valued valid
  numeric default — `0E-9`/`-0E-9` Decimals and numeric strings such
  as `0.000000000` — renders `0`; valid non-zero values keep their
  exact digits; non-numeric strings, including redisplayed invalid
  user input, pass through unchanged). During implementation the
  unit matrix exposed a sign-loss bug in the internal grouping
  helper for negative sub-1 decimals; fixed and covered.
- `app/slaif_gateway/api/admin.py` (presentation only): `dec` filter
  now delegates to `format_raw_decimal` (its fixed-point behavior
  preserved, plus the `-0E-9` → `0` correction); `num`, `tokm`,
  `inputnum` filters registered. No auth, dependency, handler,
  service, or DTO change.
- 22 admin templates: grouped/M readouts on keys list/detail, usage
  list/detail, key create-result, calibration preview, bulk-import
  preview/result, pricing list/detail/import preview/result, FX
  list/detail/import preview, templates detail, routes detail,
  institutions/cohorts/owners count cells, and key-create ceiling
  captions; token readouts carry the exact comma-grouped count in
  `title`. All `data-sort-value` attributes remain raw — canonical
  ungrouped via `dec` or raw ints/Decimals (empty for `None`, sorted
  last in both directions); the FX list rate cell gained its
  missing raw sort attribute. The live-burn cost margin INPUT uses
  `inputnum` (the single quantized-Decimal editable input); all
  other form inputs, placeholders, hidden fields, forms, actions,
  CSRF, permissions, layout, links, IDs, and the policy-selector
  route token remain literal.
- Tests: NEW `tests/unit/test_admin_numeric_display_206.py` and
  NEW `tests/browser/test_admin_numeric_display_206.py`; bounded
  literal-oracle updates in `test_admin_table_rows_194.py` (token
  cells display `0.000123M` / `0.0015M`; raw keys `123`/`1500` and
  titles preserved), `test_admin_key_actions_templates.py`
  (usage-reset readouts), `test_admin_activity_templates_safety.py`
  (`0.220000000` → `0.22`), `test_admin_catalog_routes.py` (FX
  detail `0.92` readout + raw `0.920000000` list sort key). No
  semantic, security, or sort assertion weakened.
- Docs: `docs/admin-usability.md` §6 gains the "Numeric display
  contract (206-a)" subsection (confirmed `0E-9` source, `1E-9`
  distinction, locale/M precision, exact tooltips, raw form and sort
  law, no accounting/schema impact); `docs/verification/
  2026-10-29-admin-numeric-display.md` record + README index entry.

## Verification evidence (local, focused; CI pending)
- Pure formatter + ASGI render (unit fake-session seams, no DB):
  `tests/unit/test_admin_numeric_display_206.py` 37 PASS, 0 skip —
  `0E-9`/`-0E-9`/string-zero matrix, true `1E-9`, grouped
  money/counts, exact `2**53+1` and `2**63-1` (no float
  round-trip), numeric strings, None/label separation, M
  conversion (0, 1, 1000, 999999, 1,000,000, 1,500,000,
  937,826,734, 999,999,500 → `1,000` half-up boundary, 999,999,499
  → `999.999`, negatives, 1,234,567,890,123 → `1,234,567.89`),
  raw-decimal canonical form, input-decimal zero/nonzero/user-
  string cases, and ASGI renders (keys list: `937,826,734`,
  `937.827M` + title `937,826,734`, `0E-9` cost → `0`, `1,000M`
  boundary, Unlimited/empty raw key, `1E-9` never zeroed; keys
  detail: live-burn `0` readout + `value="0"` raw input,
  `0.000000001` margin preserved; usage detail: actual-zero cost in
  preference to the estimate, estimate fallback, n/a; pricing
  list: `0.01` / `0` / `n/a` + raw sort key).
- All admin unit suites `tests/unit/test_admin_*.py`: 660 PASS,
  0 skip (JUnit), including the 37 new and 4 oracle-updated cases.
- Actual Chromium on an owned, labeled, loopback-bound, tmpfs-
  backed PostgreSQL 16 container (qualified fixture; exact created
  container removed on teardown, none remain), real uvicorn app,
  real stylesheet, real HTTP admin pages:
  `tests/browser/test_admin_numeric_display_206.py` 3 PASS, 0 skip
  — keys list readouts/titles + raw typed sorting (tokens-used
  ascending `0,0,1000,937826700,937826734,937826749`: three
  DISTINCT values sharing the `937.827M` label keep exact order;
  token-limit None last in both directions; five real zeros before
  `7.75` in cost order); key detail live-burn readout `0` with raw
  input `0`; usage list/detail `937.827M total` + titles, actual-
  zero `0 EUR` over the `9.99` estimate, `0.01 EUR` unpadded,
  `n/a EUR`.
- Existing browser contract re-run (unchanged test):
  `tests/browser/test_admin_usability.py` 10 PASS, 0 skip (header
  text, raw sort values, `0 EUR`/`7.75 EUR`/`n/a EUR` display
  fidelity, ordinals, picker contracts preserved).
- Screenshots (synthetic fixture data only; no plaintext secrets,
  session values, or real user data): `/tmp/slaif206/
  keys-numeric-display.png`, `/tmp/slaif206/usage-numeric-display.png`.
- Static/governance: `ruff check` clean on all touched Python
  files; `git diff --check` clean; `scripts/
  check_documentation.py` → `DOCUMENTATION_CHECK=OK`;
  `tests/unit/test_oap_governance.py` 9 PASS, 0 skip.
- Honesty: the ASGI renders are unit-fake-session renders (no DB);
  the Chromium cases are the actual-page proof. No real provider,
  mail, or production traffic; no production-certification claim.
  Service-built policy summary strings (e.g. "500 tokens/min") and
  rate-limit semantic window units stay in their built text
  (documented limitation in admin-usability §6).

## Publication
- ONE unique PR #362 from main `8d60d098b51cddb6351c6b843feb1a46db115616`
  (sole other open PR at publication: Dependabot #319, untouched).
- PR description leads with the observable before/after behavior
  (0E-9 → 0; 937826734 → 937,826,734; tokens → M) and the focused
  verification / no-schema statement.
- This report is committed as a report-only SELF: first parent is
  IMPL and ONLY this report differs. Remote PR head was verified
  equal to SELF before the OK signal. GitHub final-head checks on
  SELF are PENDING (not pass); strategic review and guarded merge
  are root-owned. No merge, auto-merge, release, or tag by the
  coding agent.
