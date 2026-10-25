# Admin dashboard usability: sortable tables and known-record choices

Objective 192-a made the operator-facing admin surfaces consistently
usable: every list table is sortable in the browser, and every
known-record / finite-vocabulary field is backed by a searchable
picker over real local data (with a faithful no-JavaScript fallback).

This document is the coverage reference. It does not replace
`docs/security-model.md` (auth/CSRF/lookup boundary) or
`docs/database-schema.md` (field semantics).

## 1. Sortable tables

### How sorting works

- Every admin list `<table>` carries `data-sortable`. The shared
  fixed source `web/static/js/table-sort.js` upgrades each header
  into a real, keyboard-focusable `<button type="button">` (Enter and
  Space work natively) and announces direction through
  `<th aria-sort="ascending|descending|none">`.
- First click on a header sorts that column ascending; the next click
  on the same header reverses to descending; clicking a different
  column selects it ascending. The initial server/business ordering is
  kept until the first click.
- Column types come from `<th data-sort-type="...">`:
  `text` (default, case-insensitive natural order, so `2` sorts before
  `10`), `number`, `money`, `percent`, `date`/`datetime`, `boolean`.
- Typed raw sort keys: `<td data-sort-value="raw">` overrides the
  displayed text where decorated or composite text would mislead
  (request counts, limits, timestamps, costs). A blank/missing raw key
  sorts as missing.
- Typed numeric keys inside the database bounds compare EXACTLY:
  money/price values are `Numeric(18,9)` and counts are integers
  (BigInteger, including the full signed 64-bit range); a scaled
  BigInt coefficient comparison keeps distinct allowed values distinct
  (e.g. `999999999.000000001` vs `999999999.000000002`, or
  `9007199254740992` vs `9007199254740993`, which plain floating-point
  comparison would collapse). Decorated, exponent, or out-of-bounds
  input falls back to a bounded numeric comparison.
- Missing values (`""`, `-`, `n/a`, `Unknown`, `Unlimited`, `Not
  set`, …) always sort LAST in BOTH directions. Ties are stable
  (original row order).
- `<tr data-no-sort>` rows (empty-state, summary, footer) never move;
  `<tr data-sort-group>` rows move together with their consecutive
  `data-sort-group-continue` detail rows.
- Sorting reorders only the rows of the DISPLAYED result set: existing
  filters and the page row limit stay in effect. Rows carry their
  links, forms, checkboxes, and selections with them. Tables are
  sorted independently.
- No network access, no dynamic code, no cell-content mutation.

### Covered tables

All 25 admin list/detail tables (owners, institutions, cohorts, keys,
providers, routes, pricing, FX, usage, audit, email deliveries, key
templates, import preview/result tables for keys/FX/routes/pricing,
and the related-record tables on institution/owner/provider detail
pages) are `data-sortable` — pinned by
`tests/unit/test_admin_usability_inventory.py::test_every_admin_table_is_sortable`.
Runtime proof (real Chromium, real stylesheet, unforced header clicks)
lives in `tests/browser/test_admin_usability.py` and
`tests/browser/test_catalog_refresh_report.py`.

### The catalog-refresh `REVIEW.html`

The one-page report embeds the SAME fixed `table-sort.js` bytes
(single source of truth; byte equality is asserted by tests) as its
only script, under `script-src 'unsafe-inline'` CSP. The report stays
a single self-contained file: no network on open, no eval/Function,
no user-controlled executable content, and it remains fully readable
with JavaScript disabled.

## 2. Known-record choices (searchable pickers)

### Control behavior

Fields rendered by the `record_choice` macro
(`web/templates/_record_choice.html`) are searchable comboboxes driven
by `web/static/js/record-choices.js`:

- The initial menu shows the server-rendered **latest ~100 eligible**
  records (recency ordering with a deterministic tie-breaker,
  eligibility filtered BEFORE the limit — e.g. anonymized owners are
  never offered). The selection is re-hydrated with its label when it
  falls outside that batch.
- Typing performs a bounded server lookup (`GET
  /admin/record-choices?kind=...&q=...`, at most 100 results) that
  reaches OLDER records; the form is never auto-submitted.
- Single-value fields submit the selected id through a managed hidden
  input; `allow_new` fields also accept a typed new value, and the
  server validation stays authoritative.
- Multi-value fields manage a chip list plus either one hidden input
  per value or one newline-serialized hidden input (`serialize=
  "newline"`), so existing server-side parsing and policy semantics
  are not broadened.
- Dependent controls refetch when the referenced control's value
  actually changes (`rc-change`): model choices follow the selected
  provider (`data-depends-param="provider"`), and the audit target-ID
  picker follows the target-type picker
  (`data-depends-param="target_type"`).
- Keyboard: ArrowDown/ArrowUp/Home/End navigate, Enter selects,
  Escape/Tab close; Backspace on the focused empty multi textarea
  removes the last chip.
- No-JavaScript fallback: single fields are plain text inputs
  (prefilled, raw value submitted); multi fields are real
  newline-preserving textareas. Existing server validation applies.

### Lookup endpoint boundary

`GET /admin/record-choices` is a read-only admin lookup: it validates
the current admin session with `touch=False` (no last-activity
mutation) and does NOT refresh the CSRF token, so dropdown searches
never invalidate the already-rendered form's CSRF token or mutate
database state. An unauthenticated request gets a clean redirect to
login. It serves only allowlisted kinds, minimal columns (no password
hashes, encrypted payloads, or raw usage bodies), bounded queries, and
bounded distinct/grouped SQL. See `docs/security-model.md`.

### Known-option vocabularies

- **Endpoints**: the key-policy picker carries the EXACT
  `IMPLEMENTED_CLIENT_ENDPOINTS` tokens, method prefixes included
  (`GET /v1/...`, `POST /v1/...`, `DELETE /v1/...` are distinct
  grants). The flattened path vocabulary (no method) is used only for
  fields that STORE paths (route/pricing/usage/audit filters).
- **Usage status**: the native select is rendered from
  `STATUS_VALUES_USAGE_LEDGER_ACCOUNTING`
  (pending/finalized/estimated/failed/interrupted/released).
- **Email delivery status**: rendered from
  `STATUS_VALUES_EMAIL_DELIVERIES`
  (pending/sending/sent/failed/ambiguous/cancelled) — the model truth,
  not an invented list.
- **Currencies / FX sources**: DB-derived (distinct values actually
  present in the fx/pricing tables, latest-observed first). No static
  invented vocabulary.
- **Model tokens**: route requested models AND upstream models are
  first-class (no coalescing that drops one), plus pricing upstream
  models and historically used requested/resolved models, each source
  bounded and provider-scoped when a provider is selected.
- **Audit targets**: distinct entity ids grouped BEFORE the limit, so
  many recent events for one entity cannot crowd all other known
  targets out of the initial batch; scoped to the selected
  target type.
- **Request IDs**: the union of usage-ledger request ids (AI calls)
  and audit-log request ids (admin actions), each source bounded.

## 3. Coverage inventory

The permanent unit audit
(`tests/unit/test_admin_usability_inventory.py`) encodes the
independent minimum-96 known-reference/finite-choice field inventory
and pins, field by field, the required control:

- `record_choice` — 34 fields (owner, institution, cohort, provider,
  model, endpoint-path, currency, key/public-key, owner-email,
  one-time-secret, audit action/type/target/actor/request-id, usage
  filters, import format record fields, external-tool destinations).
- native `select` — 36 fields over canonical/DB vocabularies (status,
  kind, match type, import format, email delivery mode, enabled/
  active/expired/visible, presets, endpoint scope, …).
- dual-list policy selector with manual-field sync — the key policy
  provider/endpoint/model allow-lists
  (`keys/_policy_selector.html` + `policy-selector.js`): the known
  options picker IS the dual-list; the advanced manual textareas stay
  editable for globs/free values and are kept synchronized with the
  lists while JavaScript is enabled.
- justified free text — institution and cohort `name` filters are
  text SEARCH filters (not record references); the institution
  RECORD reference on owner create/edit is a record choice.

The same audit pins: the 6-value usage status vocabulary, the
email-delivery vocabulary equality with the model constants, the
key-policy endpoint token exactness, the dual-list/manual-sync
attributes, the openai-assisted multi model-glob controls
(`multi=true`, `serialize="newline"`), and the `model-review.md`
catalog proposal artifact as a NON-GUI static Markdown export (no
script injection surface; the catalog-refresh `REVIEW.html` is the
GUI surface that carries the fixed sort script).

## 4. Import preview/result tables

Bulk key import (and FX/routes/pricing import) preview and result
pages are dry-run tables over the parsed rows: Row number (numeric),
status/action, owner, scope, validity (datetime), quotas (money),
policy, email, errors. They are `data-sortable` like every other
table; row associations (owner, created key public ID, quota) travel
with their row. The confirmed-execution result page displays each
one-time plaintext key once (no-store); the permanent browser tests
read only the safe owner/key-metadata/quota/error cells and never the
plaintext cell.

## 5. Display fidelity notes

- A VALID actual cost of zero displays `0 EUR` (it is not "missing"
  and does not fall through to the estimate); an estimate-only row
  displays the estimate; a row with neither displays `n/a` and sorts
  last as missing.
- Import-preview quota cells use explicit `is not none` checks so the
  display and the typed sort key can never disagree for a present
  value. FX rates are positive-only by validation, so their
  truthiness handling stays as-is.

## 6. Verification

See `docs/verification/2026-10-25-admin-usability.md` for the
objective verification record (focused JUnit counts, actual-browser
facts, owned-PostgreSQL facts, and honest skips).
