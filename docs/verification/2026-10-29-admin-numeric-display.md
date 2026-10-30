# 2026-10-29 objective 206-a admin numeric display verification

Focused verification record for the 206-a admin GUI numeric-display
change (read-only presentation only; no services, schema, migrations,
API/CLI/CSV contracts, JS/CSS, or accounting changes).

## Scope and confirmed cause

- Root cause confirmed: PostgreSQL `Numeric(18,9)` values come back as
  `Decimal`; a stored zero quantized to the 9-dp quantum renders by
  `str()` as `0E-9`. The keys-detail Chat streaming live-burn cost
  margin readout (`keys/detail.html`) and its form input displayed
  that exponent form; most other readouts interpolated raw
  Decimals/ints with no grouping at all.
- `0E-9` is an EXACT zero (renders `0`); `1E-9` is a true positive
  0.000000001 (renders `0.000000001`) and is never displayed as a
  free zero. No data cleanup, epsilon, or accounting rounding was
  touched.
- Contract: locale-stable comma grouping + dot decimal, no
  scientific notation, exact int/Decimal/numeric-string rendering
  (no float round-trip), unneeded fractional zeros stripped; `None`
  stays missing (template labels `Unlimited`/`n/a`/`Unknown`);
  human-facing token quantities display in millions of tokens
  (>=1M: up to 3 decimals, `ROUND_HALF_UP`, trailing zeros stripped;
  <1M: exact power-of-ten scaling, no positive value rounds to
  zero) with the unit in the value and the exact comma-grouped count
  in `title`/accessibility text; `data-sort-value` keys stay
  canonical ungrouped/unscaled (empty for `None`, sorted last in both
  directions); editable inputs keep exact raw units with no
  comma/M parser — only a zero-valued valid numeric default
  (`0E-9`/`-0E-9`, `0.000000000`) normalizes to `0`, valid non-zero
  values keep their exact digits, and redisplayed user input (even
  invalid) passes through unchanged. Identifiers, HTTP codes, ports,
  dates, versions, raw JSON, code blocks, form values, hidden fields,
  and CSV/API/CLI/JSON surfaces remain literal.

## Implementation

- `app/slaif_gateway/web/formatting.py` (new): pure helpers
  `format_number`, `format_tokens_m`, `format_raw_decimal`,
  `format_input_decimal` (plain strings only; no Markup; bools/floats
  out of the quantity contract; non-numeric strings pass through).
  A sign-preservation fix in the internal grouping helper was found
  and covered by the unit matrix (negative sub-1 decimals).
- `app/slaif_gateway/api/admin.py` (presentation only): `dec` now
  delegates to `format_raw_decimal`; `num`, `tokm`, `inputnum`
  filters registered. No auth, dependency, handler, service, or DTO
  change.
- Templates: grouped/M readouts with exact-count `title`s on
  keys list/detail, usage list/detail, key create-result,
  calibration preview, bulk-import preview/result, pricing list/
  detail/import preview/result, FX list/detail/import preview,
  templates detail, routes detail, institutions/cohorts/owners
  count cells, and key-create ceiling captions. The live-burn cost
  margin INPUT uses `inputnum` (the single quantized-Decimal
  editable input). All `data-sort-value` attributes remain raw
  (canonical ungrouped via `dec` or raw ints/Decimals); the FX list
  rate cell gained its missing raw sort attribute. Forms, actions,
  CSRF, permissions, layout, links, IDs, and the policy-selector
  token (a route identifier, not a count) are untouched.

## Focused test evidence (local; GitHub CI pending)

Layer: pure formatter + real template renders through the ASGI app
with the existing unit fake-session seams (no DB, no server, no real
provider/mail).

- `tests/unit/test_admin_numeric_display_206.py` (NEW): 37 PASS,
  0 skip. Covers the `0E-9`/`-0E-9`/string-zero matrix, true `1E-9`,
  grouped money/counts, exact 2**53+1 and 2**63-1 integers (no float
  round-trip), numeric strings, None/label separation, M conversion
  (0, 1, 1000, 999999, 1,000,000, 1,500,000, 937,826,734,
  999,999,500 half-up boundary, negatives, large grouped magnitude),
  raw-decimal canonical form, input-decimal zero/nonzero/user-string
  cases, and ASGI renders: keys list (937,826,734 grouped;
  937.827M with title 937,826,734; `0E-9` cost renders 0; 1,000M
  rounding boundary; Unlimited/empty raw key; 1E-9 never zeroed),
  keys detail (live-burn `0` readout + `value="0"` raw input;
  `0.000000001` margin preserved), usage detail (actual-zero cost in
  preference to the estimate; estimate fallback; n/a), pricing list
  (9-dp `0.01`, zero `0`, missing `n/a`, raw sort key).
- Existing admin unit suites: `tests/unit/test_admin_*.py` total
  660 PASS, 0 skip (JUnit), including the 37 new cases and the four
  bounded literal-oracle updates below.
- Bounded literal oracle updates (intended display change only;
  semantic/security/sort assertions preserved):
  - `tests/unit/test_admin_table_rows_194.py`: token cells display
    `0.000123M` / `0.0015M` with exact raw sort keys `123`/`1500`
    and `title` `123`/`1,500`.
  - `tests/unit/test_admin_key_actions_templates.py`: usage-reset
    readouts assert grouped money + M tokens + exact titles.
  - `tests/unit/test_admin_activity_templates_safety.py`:
    `0.220000000` -> `0.22` readout.
  - `tests/unit/test_admin_catalog_routes.py`: FX detail rate
    `0.92` readout plus the raw `0.920000000` list sort key.

Layer: actual Chromium on an owned, labeled, loopback-bound,
tmpfs-backed PostgreSQL 16 container (fixture from
`tests/integration/test_lazy_throttling_postgres_redis.py`), real
uvicorn app, real stylesheet, real HTTP admin pages; exact created
container removed on teardown (no owned containers remain after the
runs).

- `tests/browser/test_admin_numeric_display_206.py` (NEW): 3 PASS,
  0 skip. (1) Keys list: `937,826,734` / `937.827M` readouts with
  `title="937,826,734"`, exponent-zero row displays `0` (no `0E-9`
  anywhere in the page), `0.001M`/`0.0015M`/`1,000M` with exact
  titles, and raw typed sorting: tokens-used ascending
  `0,0,1000,937826700,937826734,937826749` — three DISTINCT values
  sharing the `937.827M` label keep their exact order (descending
  reversed); token-limit ascending puts `1500` then `999999500`
  first with `None` last, descending reverses the set values with
  `None` still last; cost ascending keeps five real zeros before
  `7.75`. (2) Key detail: live-burn margin readout `0`, editable
  cost-margin input raw `0` (not `0M`, not `0E-9`), token-limit dd
  `1,000M` with title `999,999,500`. (3) Usage list + detail:
  `937.827M total` with title, actual-zero cost `0 EUR` in
  preference to the `9.99` estimate, `0.01 EUR` unpadded estimate,
  `n/a EUR`, and detail `937.827M`/`0` with exact titles.
- Existing browser contract re-run (unchanged test):
  `tests/browser/test_admin_usability.py` 10 PASS, 0 skip —
  header text, raw sort values, cost display fidelity (`0 EUR` /
  `7.75 EUR` / `n/a EUR`), row ordinals, and picker contracts all
  preserved.
- Screenshots (synthetic fixture data only, no secrets/session
  values): `/tmp/slaif206/keys-numeric-display.png`,
  `/tmp/slaif206/usage-numeric-display.png`.

## Static and governance checks

- `ruff check` on all touched Python files: clean.
- `git diff --check`: clean.
- `scripts/check_documentation.py`: `DOCUMENTATION_CHECK=OK`.
- `tests/unit/test_oap_governance.py`: 9 PASS, 0 skip.

## Honesty and limitations

- The ASGI renders are unit-fake-session renders (no DB); the
  Chromium cases are the actual-page proof. No real provider,
  email, or production traffic is involved; no release claim.
- Service-built policy summary strings (e.g. "500 tokens/min") are
  outside this presentation contract and still render their built
  text; rate-limit semantic window units stay in those strings.
- GitHub CI on the report head remains PENDING at publication
  (treated as pending, not pass); strategic review and guarded
  merge are the root's gates.
