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
- Service-built policy summary strings were outside the 206-a scope;
  the 206-b completion section below closes that gap in the same
  presentation layer (known finite grammar only; raw unrounded
  strings preserved in titles; no shared service output changed).
- GitHub CI on the report head remains PENDING at publication
  (treated as pending, not pass); strategic review and guarded
  merge are the root's gates.

## 206-b completion (recorded 2026-10-30, same PR #362)

Scope: finish the remaining demonstrated missed readouts and fix the
one stale display oracle in the same PR. No services, schema,
migrations, API/CLI/CSV contracts, JS/CSS, or accounting changes.

### Implementation (presentation only)

- `app/slaif_gateway/web/formatting.py`: two new pure helpers,
  `format_policy_summary` (rate-limit / Chat live-burn /
  lazy-throttling wait grammars matched exactly before any digit is
  touched; everything else byte-for-byte unchanged) and
  `format_rate_limit_policy` (typed policy dict in the same known
  grammar, literal `str` fallback for unknown shapes).
- `app/slaif_gateway/api/admin.py`: `policysum` / `ratepolicy` filter
  registration only.
- Templates: grouped `num` on the remaining read-only counters and
  summary totals (cohorts/owners/institutions detail counters; keys
  bulk preview/result cards; pricing/FX/routes import preview/result
  counts; provider timeout/retry and route priority readouts); M
  display (`tokm`) with exact grouped counts in `title`/accessibility
  text for the key-detail output token margin (including negative
  margins), the usage-detail configured token margin, cached/reasoning
  (title on each value), and estimated-tokens-at-stop; the human
  policy summary sites (key detail, create-result, template detail,
  bulk preview/result rows) render through `policysum`/`ratepolicy`
  with the raw unrounded service string in the `title` attribute.
  Editable inputs stay exact raw units (the key-detail token-margin
  form label now says "(tokens)" next to the M readout). The
  bounded `rows shown` counters are left literal by design: page
  limits cap them below any grouping threshold and the 194-a source
  pin owns that exact interpolation.

### Stale oracle failure provenance (206-a report head)

- GitHub CI run 40980689318 on the 206-a report head
  `7070bd45db499ee9a7155420ac322306910fea77`: the unit job
  (`tests/unit/test_admin_key_actions_templates.py::
  test_key_detail_renders_chat_streaming_live_burn_form`, line 223)
  FAILED with 1 FAIL / 6546 PASS / 1 SKIP: the expectation still
  asserted the pre-206-a raw `value="0.000000000"` for the
  zero-valued editable cost-margin input, whose final intended value
  is `value="0"`. This is a stale display oracle, not a product
  regression; the fix updates exactly that expectation and preserves
  the non-zero `-0.250000000` exact-digits assertion in the
  disabled-form case.
- Qualification: the earlier "660 PASS" admin-unit total PREDATES the
  final zero-input representation change and is NOT a final-tree
  all-admin pass; the 206-b scoped run below is reported separately.

### 206-b focused results (local; GitHub CI pending)

- `tests/unit/test_admin_numeric_display_206.py`: 54 PASS, 0 skip
  (the 37 unchanged 206-a cases plus 17 new: the policy-summary /
  rate-policy formatter matrices including negative margins, true
  0E-9 vs 1E-9 money, non-grammar passthrough; ASGI renders of the
  key-detail rate/live-burn/margin readouts with exact titles, the
  usage-detail cached/reasoning + stop-estimate + configured-margin
  titles, a cohort detail with 937,826,734 / 1,234,567 grouped
  counters, and a bulk-import preview with 1,234,567-row grouped
  totals plus human-rendered row policy summaries).
- Directly affected existing presentation suites (23 files, including
  the exact previously failing test, the FX/pricing/routes/bulk
  import template and route tests, the record detail template tests,
  the key create/keys routes and template tests, the 194-a rows
  contract, the catalog FX oracles, and the usability inventory):
  309 PASS, 0 skip.
- `tests/browser/test_admin_numeric_display_206.py` (extended in
  place, same owned labeled loopback tmpfs PostgreSQL fixture, real
  Chromium/uvicorn, exact container cleanup): 3 PASS, 0 skip. The key
  detail case now additionally demonstrates the real rate-limit
  summary `937,826,734 req/min, 937.827M tokens/min` (title keeps the
  exact `937826734 req/min, 937826734 tokens/min`), the Chat
  live-burn summary `cost margin EUR 0, token margin -0.00025M`
  (title keeps `0.000000000` / `-250`), the direct `-0.00025M`
  token-margin readout with title `-250 tokens`, the raw `-250`
  editable input, and the usage-detail `937.827M / 1M` cached/
  reasoning readout with title `937,826,734 / 1,000,000`.
  Screenshot (synthetic data only):
  `/tmp/slaif206/key-detail-numeric-policy.png` alongside the two
  206-a screenshots.

### 206-b residual limitations

- Same layer separation as 206-a: ASGI renders are unit-fake-session;
  the Chromium cases are the actual-page proof. No real provider,
  mail, or production traffic; no release claim.
- GitHub CI on the 206-b report head is pending at publication
  (treated as pending, not pass); strategic review and guarded merge
  are the root's gates.

### 206-c focused results (local; GitHub CI pending)

- Five template caption/readout corrections reusing the existing `num`
  filter (no new formatter, service, or infrastructure): usage and
  audit list export caps render grouped in the caption (`capped at
  10,000 rows`) while the editable row-limit inputs keep the exact raw
  value; usage-detail latency uses explicit `None` handling plus `num`
  (0 → `0 ms`, 1234567 → `1,234,567 ms`, missing → `n/a ms`, an actual
  zero never reads as missing); the OpenAI-assisted result page groups
  row count, warning count, TSV byte size, and preview byte ceiling
  while the generated TSV payload stays byte-for-byte; the key-template
  detail groups the read-only default validity days and keeps `Not
  set` for missing, with the editable form placeholder/units
  unchanged.
- `tests/unit/test_admin_numeric_display_206.py`: 60 PASS, 0 skip in
  the current tree (the 54 accepted 206-a/b cases plus 6 new: the
  grouped export-cap captions with raw `limit` inputs on both list
  pages, the latency zero/large/None matrix, the assisted-result
  grouped readouts with the raw TSV preserved through the ASGI app,
  and the template validity-days render with raw editable default
  through the real app Jinja environment).
- Directly affected existing presentation suites
  (`test_admin_openai_assisted_catalog_routes.py`,
  `test_admin_activity_templates_safety.py`): 16 PASS, 0 skip, no
  assertion changes.
- Reused without rerun: root's 54+1 = 55 numeric/stale-oracle pass
  rerun, the 206-b 54/309/3 JUnit evidence, the 206-a core raw-sort
  and legacy browser evidence, and all A/B orders/reports
  (unchanged). No browser rerun: these are text-only existing-filter
  applications on already-accepted pages.

### 206-c residual limitations

- Same layer separation as A/B: the new checks are unit ASGI renders
  (fake session) plus one direct render of the real template file
  through the app's Jinja environment; no real provider, mail, or
  production traffic. The final C report head still requires all
  final-head checks; pending CI is pending, not pass.
