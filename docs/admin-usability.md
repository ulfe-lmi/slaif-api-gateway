# Admin dashboard usability: sortable tables and known-record choices

Objective 192-a made the operator-facing admin surfaces consistently
usable: every list table is sortable in the browser, and every
known-record / finite-vocabulary field is backed by a searchable
picker over real local data (with a faithful no-JavaScript fallback).

Objective 194-a added the structural first-position row ordinal to
every admin table, split the combined usage/quota metric columns on
the key list (and the combined quota cells on the bulk-import
tables), gave every GET-limit list a visible Rows selector bound to
its filter form, and renamed the import provenance column "Row" to
"Source row" so it stays distinct from the structural ordinal.

This document is the coverage reference. It does not replace
`docs/security-model.md` (auth/CSRF/lookup boundary) or
`docs/database-schema.md` (field semantics).

## 1. Sortable tables

### How sorting works

- Every admin list `<table>` carries `data-sortable`. The shared
  fixed source `web/static/js/table-sort.js` upgrades each header
  into a real, keyboard-focusable text hyperlink
  (`<a class="ts-link" href="#ts-sort">`, a safe local fragment, no
  network) and announces direction through
  `<th aria-sort="ascending|descending|none">`.
- Hyperlink semantics: a normal click and Enter (native link
  activation) toggle the sort; Space does NOT activate a link, so
  button-style keyboard assertions do not apply. Hover/focus use a
  readable accent underline without a button background fill.
- Before the first click every sortable header shows a subtle
  NEUTRAL sortability marker (U+2195, reserved indicator space, no
  layout jump); after the first click it shows the specific
  up (U+2191) / down (U+2193) marker of the active direction.
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
only script, under `script-src 'unsafe-inline'` CSP, with its fixed
style carrying the hyperlink-header look. The report stays a single
self-contained file: no network on open, no eval/Function, no
user-controlled executable content, and it remains fully readable
with JavaScript disabled. Its `<main>` carries the local `ts-sort`
fragment target so the hyperlink sort headers resolve to an id that
exists in the document (the report's internal-link audit enforces
this).
The report renderer is versioned: the current CLI binds renderer
`194.1` (the structural ordinal column plus the `Plan #` relabel),
and sealed runs of the `183.1` era or earlier are refused explicitly
by the unsupported-renderer guard — see the [Renderer version
upgrade](catalog-refresh.md#renderer-version-upgrade-1831--1941)
section in the catalog-refresh documentation for regeneration and
rollback.

### Numbered rows, split metric columns, and the Rows selector (194-a)

- **Structural ordinal column.** Every admin table (all 25) and every
  generated `REVIEW.html` table carries a first-position plain
  `<th data-ordinal>` header and a first-position ordinal data cell
  (`<td class="row-ordinal">` in the admin tables; the report
  renderer's post-processing pass authors the same positional cell as
  `<td class="ord">`). The header is PLAIN (no sort
  link, no `aria-sort` state, no indicator) — it is a structural
  position, not a data column. The server renders `1..N` for the
  initial business order, so the numbering is coherent with
  JavaScript disabled; after any sort the fixed `table-sort.js`
  renumbers ONLY the positional values of the moved unit head cells
  (1..N in the new displayed order) and never touches data cells,
  ids, URLs, or form state.
- **Fixed rows are never numbered.** Empty-state rows carry
  `<tr data-no-sort>` and a single `colspan` equal to the table's
  column count; the sort script excludes them from both movement and
  numbering. Group rows (the keys table's plain `Key details` /
  `Usage` / `Quotas` group row) stay plain and above the complete
  leaf header row, which keeps one header cell per body column.
- **Split metric columns.** The key list separates the combined
  usage into `Requests` / `Tokens` / `Cost (EUR)` and the combined
  quota into `Requests` / `Tokens` / `Budget (EUR)` (typed raw keys:
  integer counts plain, money through the `dec` filter), under the
  plain `Usage` / `Quotas` group headers. A valid actual zero
  displays `0` (never "missing"); a `NULL` limit displays
  `Unlimited` with an EMPTY raw key, so it sorts last in both
  directions. The bulk-import preview/result tables split their
  combined quota cell into `Budget (EUR)` / `Tokens` / `Requests`
  the same way.
- **Rows selector.** Every GET-limit list (owners, institutions,
  cohorts, providers, routes, pricing, FX, usage, audit, email
  deliveries, keys) shows a toolbar between the filter form and the
  table: the displayed-row count and a visible `<select name="limit">`
  form-associated with the GET filter form. The presets are
  10/25/50/100/200; a valid custom limit outside the presets is
  preserved as an explicit `N (current)` option. There is no hidden
  duplicate limit field.
- **Provenance stays distinct.** Import preview/result tables label
  their CSV/plan row identity "Source row" (sortable number) — the
  structural ordinal and the provenance row reference are different
  columns; the report's apply-plan keeps its own stable sortable
  `Plan #` reference, distinct from its displayed-position ordinal.
- **Readability.** Identity columns carry per-column minimum widths
  (`col-key` 12rem, `col-owner` 9rem, `col-cohort` 7rem, email/subject
  13/14rem); numeric cells are tabular and right-aligned; the wide
  keys table scrolls INSIDE its labeled region on narrow viewports
  (390/768) instead of squeezing columns or overflowing the page.
- Pinned by `tests/unit/test_admin_usability_inventory.py`
  (`test_every_admin_table_has_structural_ordinal_column`,
  `test_import_tables_keep_source_row_provenance_distinct`) and
  `tests/unit/test_admin_table_rows_194.py` (real-rendered zero/one/
  many ordinals, empty-state, typed metric cells, Rows selector),
  with runtime proof in `tests/browser/test_admin_usability.py`
  (independent metric-column sorts, Enter activation, form/CSRF
  state across sorts) and
  `tests/browser/test_admin_visual_screenshots.py` (grouped thead,
  narrow-width containment, custom limit 37).

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
- Typed-entry law: in an `allow_new` field the primary input keeps
  focus while typing and its text is the submitted candidate value
  with its case and opaque characters preserved (model IDs, route
  aliases, and names may be opaque and case-sensitive — no implicit
  label normalization; subject to the existing edge trim and
  server-side normalization). Only an explicit option selection (mouse
  or keyboard on a rendered option) maps a display label to its stored
  id. The clear button tracks the current value, and clearing also
  drops stale search state (pending debounce and in-flight results
  cannot reintroduce the cleared query; dependent controls re-fetch
  scoped to the CURRENT parent value).
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

### Multi-value list filters (195-a)

The eleven GET admin list pages (keys, owners, institutions, cohorts,
providers, routes, pricing, fx, usage, audit, email deliveries) accept
**one or more values** per known-record/text filter field:

- **OR within a field, AND across fields.** Selecting two cohorts
  returns the union of both cohorts' rows; adding a status filter
  narrows that union. The multi predicate runs in SQL **before**
  `LIMIT`/`OFFSET`, so every page (and the row count) is exact over the
  matching set — never a post-filter of a fetched page.
- **Serialization.** JavaScript chip submission and the no-JS
  repeated-form submit REPEATED parameters; the no-JS multi textarea
  submits ONE newline-serialized value (the same serialization the
  server has always parsed). Legacy one-value links keep working
  unchanged.
- **Scalar service/CLI contracts are unchanged.** A one-value request
  reaches the service/repository layers as the exact legacy scalar call
  (`collapse_singleton`); only a real multi-selection crosses the
  boundary as a tuple. Per-family normalization (strip, case, LIKE)
  stays owned by the repository predicate, exactly as before.
- **Bounds (enforced before any use; excess is a 400, never a
  slice/ignore):** at most 20 unique accepted values per field (the
  UUID cap follows canonicalization — case/hyphen spellings of one id
  deduplicate), at most 100 submitted values per field (raw count,
  repeats and newline members included, checked incrementally), at
  most 1024 characters per value (the same bound the record-choice
  lookup hydration uses; this is NOT the 200-character search-term
  `q` limit, so an otherwise valid >200-character text selection
  round-trips). UUID fields parse strictly per member: ONE invalid
  member rejects the whole field. Error messages name only the fixed
  field and the limits — they never echo the submitted values.
- **CSV exports follow the same scope.** The usage and audit CSV
  export forms use the identical validated multi filters, and the
  persisted effective-filter metadata is JSON-safe (UUID/datetime
  tuples become lists; empty/blank selections drop out).
- **Chips and labels.** Selected values render as chips BELOW the
  integrated control (chips grow down; the control box itself does not
  move). Removing a chip only updates the managed hidden fields until
  the operator applies the form. A selection outside the initial
  latest-100 batch re-hydrates with its authoritative label when the
  menu opens or a lookup returns; the label-only refresh never changes
  the value, never emits a value-change event, and never disturbs the
  input text/focus. Unknown/manual values keep their fallback label.
- **Rows limit vs total.** The Rows selector (presets 10/25/50/100/200
  plus a preserved custom value) bounds DISPLAYED rows only; "N rows
  shown" reflects the page, and pagination walks the matching set.
- **No database migration.** Multi filters reuse the existing
  columns/indexes (`=` becomes a bounded `IN`); no schema, migration,
  or dependency change.
- **Not a key-policy selector.** The key create/edit policy lists keep
  their separate all/none/one/many policy semantics (an explicitly
  empty scope yields NO choices; submitted values are revalidated by
  bounded lookups) — list-filter OR semantics do not apply there.

### Visual contract (193-a)

The picker reads as ONE integrated control, not a field plus detached
buttons:

- The entry field, the compact clear affordance, and the arrow all sit
  INSIDE a single 42px bordered box (`.rc-main`, 6px radius). Single
  controls are one 42px line; multi controls keep their natural
  multi-line height WITHOUT JavaScript (the no-JS fallback stays fully
  usable) and collapse to one 42px line only after JavaScript
  enhancement (chips then carry the values).
- A single currently selected value remains a CHIP below the box; the
  box itself keeps a BLANK search prompt (the default prompt is
  "Search or select…" unless the caller supplies one) for the next
  search instead of duplicating the value. The submitted value is the
  managed hidden field, so scalar form authority is unchanged.
- Unified filter-bar typography: labels 13px/600 muted (native and
  picker labels share it), values 14px/400 (native selects and
  picker entry fields share it). Filter bars are TOP-aligned; chips,
  help, and new rows expand DOWNWARD and never move preceding
  headers/inputs or the Filter button.
- Native single dropdowns show a decorative arrow matching the picker
  chevron geometry; it is drawn from the theme tokens
  (`--accent`/`--accent-dark`) so an operator theme re-tints it with
  every other accent element. `multiple`/`size` listboxes (the
  policy dual-lists) keep the native box; native select behavior,
  keyboard, and option rendering are unchanged.
- Header actions (primary button + plain-text secondary links/signout)
  share one vertically-centered optical line; the dashboard groups the
  existing destinations under "Access management", "Providers and
  models", and "Usage and operations" with the product heading inside
  the dashboard body (no implementation-oriented status prose).
- Admin management pages are TOP-anchored: the content panel starts
  directly below the shared header and growth (long tables, chip
  rows) pushes the table DOWN; nothing is vertically centered.

### Asset revision URLs

Bundled admin CSS/JS are served under a deterministic local content
revision: `/admin/static/<asset>?v=<sha256 prefix of the exact bytes>`
(`web/assets.py`, a fixed allowlist of logical names). Changed bytes
produce a changed URL, so a browser that cached an old component picks
up the new one on the next page load; unchanged bytes stay stable.
The digest covers file content only (no paths, environment values, or
secret material in the URL); there is no remote asset service, cache
framework, service worker, database, or build step. An already-open
stale page may still need one hard refresh (browser choice); every
newly loaded page uses the current revision.

### Lookup endpoint boundary

`GET /admin/record-choices` is a read-only admin lookup: it validates
the current admin session with `touch=False` (no last-activity
mutation) and does NOT refresh the CSRF token, so dropdown searches
never invalidate the already-rendered form's CSRF token or mutate
database state. An unauthenticated request gets a clean redirect to
login. It serves only allowlisted kinds, minimal columns (no password
hashes, encrypted payloads, or raw usage bodies), bounded queries, and
bounded distinct/grouped SQL. See `docs/security-model.md`.

### Key-policy selector: page, search, and authority

The key create/edit policy selector (`keys/_policy_selector.html` +
`web/static/js/policy-selector.js`) is a dual-list picker with an
editable manual fallback:

- **The visible list is a latest-100 page, never an authority.** The
  provider list shows the latest 100 ENABLED provider configs (newest
  first); the model list the latest 100 eligible enabled routes.
  Older records are reached through the server-side search box, and a
  selected record outside the page keeps its label (hydration) without
  becoming a permission. Submitted provider ids are revalidated by a
  bounded enabled-provider database lookup — the page cap cannot widen
  or shrink what the key may use.
- **Search scopes mirror the client-side all/none/one/many semantics
  exactly:** no scope parameter = allow-all (unscoped search), a blank
  scope parameter = explicitly empty selection (the server returns NO
  choices), repeated parameters = bounded IN scope. An empty model
  search under an explicitly-empty endpoint selection therefore yields
  no candidates instead of silently searching everything.
- **Endpoint grants are method-qualified.** The endpoint list carries
  the exact `IMPLEMENTED_CLIENT_ENDPOINTS` tokens (22), so
  `GET /v1/...` and `POST /v1/...` remain distinct grants; the
  flattened path vocabulary is never reused for key-policy grants.
- The manual textareas (visible in the "Advanced manual policy
  strings" panel) stay editable for globs and free values and are kept
  in sync with the lists while JavaScript is enabled; editing one
  updates the other.

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
  targets out of the initial batch; scoped to the selected target
  type(s) (a multi parent selection OR-scopes BEFORE the limit, in
  full — parent values are not truncated). A selected target outside
  the initial batch keeps its authoritative label: the latest event's
  entity type wins, one choice per selected id, and the per-id
  reduction happens in SQL BEFORE the 100-choice limit. The selected
  parent scope constrains which ids are *eligible* choices: a
  selected id with no event under any selected parent type cannot be
  resolved from that scoped source (it may keep a plain-id fallback
  chip), but its selected value and chip are retained — the scope
  excludes out-of-scope ids from the eligible choices, it never
  silently evicts an accepted selection.

- **One-time secrets**: minimal public lifecycle metadata only (id,
  status, purpose — never the secret value, encrypted payload, or
  nonce); a selected secret outside the initial batch keeps its
  lifecycle label instead of degrading to a plain id==label fallback.
- **Request IDs**: the union of usage-ledger request ids (AI calls)
  and audit-log request ids (admin actions), each source bounded.
- **Page row limits (NOT reference pickers)**: the eleven GET-limit
  lists carry a bounded NUMERIC preset/custom Rows selector (presets
  10/25/50/100/200 plus a preserved custom value) bound to the GET
  filter form. These are presentation controls over the existing page
  limit — they are deliberately NOT part of the 102-field
  known-reference inventory and do no database reference lookup.
  Pinned by `tests/unit/test_admin_table_rows_194.py::
  test_all_eleven_get_limit_lists_have_bound_rows_selectors`.

## 3. Coverage inventory

The permanent unit audit
(`tests/unit/test_admin_usability_inventory.py`) encodes the full
known-reference/finite-choice field inventory — **102 fields across
34 templates** — and pins, field by field, the required control:

- `record_choice` — 67 fields (owner, institution, cohort, provider,
  model, endpoint-path, currency, key/public-key, owner-email,
  one-time-secret, audit action/type/target/actor/request-id, usage
  provider/model/endpoint/request-id filters, institution and cohort
  list NAME filters, import format record fields, external-tool
  destinations).
- native `select` — 32 fields over canonical/DB vocabularies (status,
  kind, match type, import format, email delivery mode, usage status
  and streaming, enabled/active/expired/visible, presets, endpoint
  scope, …).
- dual-list policy selector with manual-field sync — the key policy
  provider/endpoint/model allow-lists
  (`keys/_policy_selector.html` + `policy-selector.js`): the known
  options picker IS the dual-list; the advanced manual textareas stay
  editable for globs/free values and are kept synchronized with the
  lists while JavaScript is enabled.
- The institution and cohort list **name filters are known-name
  pickers** (record choice with `allow_new`): they offer the latest
  ~100 known names, reach older names through the server-side search,
  submit the NAME (not a UUID), and still accept a genuinely new typed
  name. They are NOT free-text exemptions.
- documented genuine free text (pinned by the raw-reference audit):
  owner create/edit `external_id` (an external system's identifier for
  the owner, not a SLAIF record reference) and the provider
  create/edit `provider` slug (the identity of the record being
  created/edited; a picker would require it to pre-exist).
- a raw-reference guard scans EVERY admin template for visible raw
  inputs/textareas with reference semantics (`*_id`/`*_uuid` patterns
  and the known reference field names) and requires either a picker/
  select control or one of the documented exceptions, so a NEW
  existing-record field cannot slip past the pinned 102-field map.

The same audit pins: the 6-value usage status vocabulary, the
email-delivery vocabulary equality with the model constants, the
key-policy endpoint token exactness, the dual-list/manual-sync
attributes, the openai-assisted multi model-glob controls
(`multi=true`, `serialize="newline"`), and the `model-review.md`
catalog proposal artifact as a NON-GUI static Markdown export (no
script injection surface; the catalog-refresh `REVIEW.html` is the
GUI surface that carries the fixed sort script).

## 4. Full coverage matrix

Derived from the same source the inventory test pins (one-time
derivation; the test is the authority if this table ever drifts).

### 4.1 Sortable tables — 24 admin templates, 25 tables

| Template | `data-sortable` tables |
| --- | --- |
| `audit/list.html` | 1 |
| `cohorts/detail.html` (related records) | 1 |
| `cohorts/list.html` | 1 |
| `email_deliveries/list.html` | 1 |
| `fx/import_preview.html` / `fx/import_result.html` | 1 / 1 |
| `fx/list.html` | 1 |
| `institutions/detail.html` (related records) | 1 |
| `institutions/list.html` | 1 |
| `keys/bulk_import_preview.html` / `keys/bulk_import_result.html` | 1 / 1 |
| `keys/list.html` | 1 |
| `owners/detail.html` (related records) | 1 |
| `owners/list.html` | 1 |
| `pricing/import_preview.html` / `pricing/import_result.html` | 1 / 1 |
| `pricing/list.html` | 1 |
| `providers/detail.html` (routes + related) | 2 |
| `providers/list.html` | 1 |
| `routes/import_preview.html` / `routes/import_result.html` | 1 / 1 |
| `routes/list.html` | 1 |
| `templates/list.html` (key templates) | 1 |
| `usage/list.html` | 1 |

Report families: the generated catalog-refresh `REVIEW.html` carries
the same fixed sort script (one self-contained file per generated
report; the browser test audits all generated cases plus real offline
sorting). Exception: `provider_catalog_proposal`'s `model-review.md`
is a NON-GUI static Markdown export (an HTML table inside Markdown)
and deliberately has no script.

### 4.2 Known-reference / finite-choice fields — 34 templates, 102 fields

Field names grouped by control per template (`RC` = `record_choice`,
`SEL` = native select, `DUAL` = dual-list policy selector):

| Template | RC | SEL | DUAL |
| --- | --- | --- | --- |
| `audit/list.html` | action, target_type, target_id, request_id, actor_admin_id | — | — |
| `cohorts/list.html` | name | active | — |
| `email_deliveries/list.html` | owner_email, gateway_key_id, one_time_secret_id | status | — |
| `fx/create.html` / `fx/edit.html` | base_currency, quote_currency, source | — | — |
| `fx/import.html` | — | import_format | — |
| `fx/list.html` | base_currency, quote_currency, source | active | — |
| `institutions/list.html` | name | — | — |
| `keys/_policy_selector.html` | — | — | allowed_providers, allowed_endpoints, allowed_models |
| `keys/bulk_import.html` / `keys/bulk_import_preview.html` | — | import_format | — |
| `keys/calibration_preview.html` | — | email_delivery_mode_default | — |
| `keys/create.html` / `keys/detail.html` | owner_id, cohort_id, external_tool_destination_ids | external_tool_mode, email_delivery_mode | — |
| `keys/list.html` | owner_email, public_key_id, cohort_id | status, expired | — |
| `openai_assisted/pricing.html` | proposal_model, currency, include_models, exclude_models | endpoint_scope | — |
| `openai_assisted/routes.html` | proposal_model, include_models, exclude_models | endpoint_scope | — |
| `owners/create.html` / `owners/edit.html` | institution_id | — | — |
| `owners/list.html` | email, institution_id, cohort_id | — | — |
| `pricing/create.html` / `pricing/edit.html` | provider, upstream_model, endpoint, currency | — | — |
| `pricing/import.html` | — | import_format | — |
| `pricing/list.html` | provider, model, endpoint, currency | enabled, active | — |
| `providers/create.html` / `providers/edit.html` | — | kind | — |
| `providers/discover_preview.html` | — | preset, pricing_mode | — |
| `providers/list.html` | provider | enabled | — |
| `routes/create.html` / `routes/edit.html` | requested_model, endpoint, provider, upstream_model | match_type | — |
| `routes/import.html` | — | import_format | — |
| `routes/list.html` | provider, requested_model | match_type, enabled, visible | — |
| `templates/detail.html` | owner_id, cohort_id | email_delivery_mode | — |
| `usage/list.html` | provider, model, endpoint, request_id | status, streaming | — |

### 4.3 Legitimate non-picker field families

The raw-reference guard (Section 3) requires a picker/select for every
visible field with reference semantics; these families are the
documented, justified non-picker groups:

- **New-record identity** — fields that CREATE a new record cannot be
  pickers over the record they create: owner create name/surname/email,
  institution create name, cohort create name, and the provider create
  slug (a free NEW unique slug).
- **Record-identity editing** — the provider EDIT slug edits the OWN
  record's identity: an editable unique slug the service revalidates
  (validated unique-slug rename); it never selects ANOTHER existing
  provider. Likewise owner create/edit `external_id` (an external
  system's identifier, not a SLAIF reference).
- **Auth / credentials** — login and admin password fields are
  credential inputs, never choices.
- **Dates, numbers, money, limits** — validity, quotas, rate limits,
  timeouts, margins: typed values with server validation.
- **Reasons, notes, display text** — audit reasons, notes, display
  names, descriptions.
- **Bulk documents** — CSV/JSON upload file inputs (keys/FX/routes/
  pricing import) and the raw manual policy strings.
- **Hidden transport** — CSRF tokens and action ids (never visible
  reference fields).

## 5. Import preview/result tables

Bulk key import (and FX/routes/pricing import) preview and result
pages are dry-run tables over the parsed rows: structural ordinal
(194-a), Source row (sortable numeric provenance, kept distinct from
the ordinal), status/action, owner, scope, validity (datetime), the
split quota cells Budget (EUR) / Tokens / Requests (bulk import),
policy, email, errors. They are `data-sortable` like every other
table; row associations (owner, created key public ID, quota) travel
with their row, and the execute form's checkboxes/CSRF state is
untouched by a sort. The confirmed-execution result page displays each
one-time plaintext key once (no-store); the permanent browser tests
read only the safe owner/key-metadata/quota/error cells and never the
plaintext cell.

## 6. Display fidelity notes

- A VALID actual cost of zero displays `0 EUR` (it is not "missing"
  and does not fall through to the estimate); an estimate-only row
  displays the estimate; a row with neither displays `n/a` and sorts
  last as missing. The usage DETAIL page applies the same explicit
  `is not none` preference: a present actual zero is shown in
  preference to the estimate.
- Import-preview quota cells use explicit `is not none` checks so the
  display and the typed sort key can never disagree for a present
  value. FX rates are positive-only by validation, so their
  truthiness handling stays as-is.

### Numeric display contract (206-a)

Human-visible read-only quantities across the admin GUI use a
locale-stable formatter (`app/slaif_gateway/web/formatting.py`,
exposed as the `num` / `tokm` / `inputnum` Jinja filters; `dec` now
delegates to the canonical raw-decimal helper):

- **Locale rule.** Digit thousands are comma-grouped, the decimal
  separator is a dot, and no scientific/exponent notation is rendered
  for ordinary finite quantities. int, Decimal, and legitimate numeric
  strings render EXACTLY (no float round-trip, so 64-bit counts and
  9-dp `Numeric(18,9)` money keep their low digits); unneeded
  fractional zeros are stripped.
- **Confirmed `0E-9` source.** PostgreSQL `Numeric(18,9)` values come
  back as `Decimal`; a stored zero quantized to the 9-dp quantum
  renders by `str()` as `0E-9` (seen in the keys-detail live-burn cost
  margin readout and its form input). `0E-9` is an EXACT zero and
  renders `0`. The distinct value `1E-9` is a true positive
  0.000000001 and renders `0.000000001` — a small positive price or
  margin is never replaced by a free zero. No data cleanup, epsilon,
  or accounting rounding is involved; this is presentation only.
- **Missing stays missing.** `None` never becomes `0`; templates keep
  their per-field labels (`Unlimited`, `n/a`, `Unknown`, `Not set`).
- **Token quantities in M.** Human-facing token counts (used/reserved
  limits, usage totals, per-request maxima, calibration and template
  readouts) display in millions of tokens with the unit in the VALUE
  (column headings stay unchanged, e.g. "Tokens"): `|v| >= 1,000,000`
  quantizes to at most 3 decimals with `ROUND_HALF_UP` and trailing
  zeros stripped (`1,500,000 -> 1.5M`; `937,826,734 -> 937.827M`;
  `999,999,500 -> 1,000M`); `|v| < 1,000,000` scales by an exact
  power-of-ten shift so no positive count rounds to zero
  (`1,000 -> 0.001M`; `1 -> 0.000001M`). The exact comma-grouped
  count is provided through `title`/accessibility text on the token
  readouts; the display is an approximation for reading, never policy
  authority. Already-per-1M prices/rates keep their monetary value and
  per-1M unit (never divided again).
- **Human policy summaries are in scope.** The service-built human
  policy summaries that the safe DTOs expose as strings (rate-limit
  `req/min` / `tokens/min` / `concurrent` / `s window` parts, the Chat
  live-burn summary, the lazy-throttling wait summary; plus the typed
  rate-limit policy dict on the key create-result page) are inside the
  numeric display contract. A narrow pure presentation formatter
  (`format_policy_summary` / `format_rate_limit_policy`, exposed as the
  `policysum` / `ratepolicy` Jinja filters) matches ONLY the exact known
  finite producer grammar before touching any digit, then renders the
  numeric quantities with the same accepted rules (grouped counts,
  token quantities in M, 9-dp money with unneeded zeros stripped) while
  preserving the unit, window, disabled/ignored, and inheritance
  wording verbatim. The raw unrounded service string stays in the
  `title`/accessibility text of the rounded readouts. Text that does not
  match the known grammar — arbitrary notes, provider metadata, URLs,
  raw JSON, code, identifiers — passes through byte-for-byte unchanged;
  there is no generic digit substitution.
- **Raw machine surfaces unchanged.** `data-sort-value` keys use the
  canonical ungrouped, unscaled exact integer/decimal (`dec`); `None`
  maps to the empty raw key (sorted last in both directions).
  Editable input values, placeholders, hidden fields, submitted
  payloads, identifiers, HTTP codes, ports, dates, versions, raw
  JSON, and code blocks remain literal. Editable inputs accept the
  same exact raw units as before (no comma/M parser was added): only a
  zero-valued valid numeric default is normalized to `0` (the `0E-9`
  / `-0E-9` exponent forms and padded zero strings such as
  `0.000000000`); valid non-zero values keep their exact digits and
  redisplayed user input — even invalid input — passes through
  unchanged. Those raw boundaries are intentional (machine
  round-trip and form transport must stay valid inputs/identifiers),
  not an omission of the human-facing contract.
- **No accounting/schema impact.** These are pure presentation
  helpers: no services, repositories, schema, migrations, API/CLI/CSV
  contracts, JS, or CSS changed.
- **Completion captions and zero-safe latency (206-b/c).** The
  remaining human quantities — the usage/audit export-cap captions,
  the OpenAI-assisted proposal summary readouts (rows, warnings, TSV
  size, preview ceiling), and the key-template default validity days —
  use the same `num` grouping, and the usage-detail latency readout
  uses explicit `None` handling so an actual zero displays `0 ms`
  while a missing value keeps `n/a ms`; every editable input, raw
  payload, and machine surface stays literal.

## 7. Verification

See `docs/verification/2026-10-25-admin-usability.md` for the
192-a verification record (focused JUnit counts, actual-browser
facts, owned-PostgreSQL facts, and honest skips) and
`docs/verification/2026-10-25-admin-visual-consolidation.md` for the
193-a visual-consolidation record (hyperlink headers, integrated
control appearance, asset-revision URLs, A1 screenshots) and
`docs/verification/2026-10-25-admin-numbered-tables-and-metric-columns.md`
for the 194-a record (ordinal/metric/Rows-selector focused groups,
owned-PG/Chromium facts, honest layer separation, and the
root-discovered renderer-identity follow-up).
and
`docs/verification/2026-10-25-admin-list-multiselection.md` for the
195-a multi-value list filter record (OR/AND bounded filters,
SQL-before-LIMIT pagination oracle, real-PG R5 selected-hydration
scope/limit regressions, chip UI, label-only async refresh, CSV multi
exports, honest layer separation).
and
`docs/verification/2026-10-29-admin-numeric-display.md` for the
206-a numeric-display record (confirmed `0E-9` source and `1E-9`
distinction, formatter matrix, ASGI render facts, actual
Chromium/owned-PG facts, screenshots, raw sort/input law, and
limitations) and
`docs/verification/gui-cli-parity.md` for the 207 (207-a + 207-b)
key-policy administration record (provider tri-state, advanced
configuration import/export, existing-key rate editor, effective
inspection and explain model access, the 207-b privacy/download/
reason-bound repairs, no-JS fallback facts, and screenshots).


## 8. Key policy administration (207-a + 207-b)

This section documents the key-management surfaces delivered by
objective 207-a (G01-G03 of `docs/MISSING_GUI_FUNCTIONALITY.md`) and
repaired by 207-b on the same PR (credential privacy at the new/touched
seams, the non-rotating configuration download, and the GUI-side
reason bound). They reuse the existing shared services; no new database
schema, table, or client/server module was added, and no new sortable
tables were introduced (the rate editor and inspection blocks are
grouped field cards, not tables).

### 8.1 Navigation

- **Create key** (`/admin/keys/create`): the existing guided form keeps all
  prior fields. The policy section gains the labeled provider mode
  checkboxes and a new "Policy Source" section that chooses between the
  guided fields and one advanced version-1 configuration document.
- **Key detail** (`/admin/keys/{id}`): a new "Effective Policy
  (configuration only)" readout section near the top, then the existing
  "Update Request Policy" form (with the tri-state provider controls), then
  the new "Operational Rate Limits (Redis)" editor, "Explain Model Access
  (configuration only)" panel, and "Advanced Configuration (versioned
  JSON)" section. All legacy sections (policy selector, lazy throttling,
  streaming live-burn, external tools, quotas, lifecycle, rotation, usage
  reset) remain unchanged.

### 8.2 Provider tri-state semantics

Exactly one provider mode applies, and it is expressed explicitly:

- **Allow all enabled providers (unrestricted)**: stored `null`. This is
  the guided create default (the checkbox starts checked); no-JS
  submissions carry the same visible state.
- **Selected providers (allow-list)**: leave both mode checkboxes off and
  choose at least one provider. On an existing key, stored providers that
  are now disabled or older stay listed (labeled `slug | manual entry`) and
  are preserved on save.
- **Deny all providers**: stored `[]`, an explicit checkbox. A deny-all key
  cannot use any provider route.

A submission with **neither** mode checked and an **empty** selection is
refused with a fixed error ("...an empty selection never grants
unrestricted access."); it never broadens authority. When JavaScript is
enabled the two mode checkboxes are mutually exclusive and either one locks
the selection grid; the server enforces the same law on every POST, so
no-JS forms and direct submissions follow the identical rules.

### 8.3 Advanced configuration document

The create page (document mode) and the key-detail "Apply configuration
update" form accept the SAME strict version-1 document the CLI uses:
`schema_version` must be `1`; unknown or duplicate fields are rejected with
fixed safe errors; the document is capped at 64 KB; `cost_limit_eur` accepts
a decimal string or number and exports with exact 9-dp Decimal rendering.

Semantics (presence-aware, matching the CLI `policy update --policy-file`
law):

- an **omitted** field leaves the key's current value untouched;
- `null` `allowed_providers` is unrestricted and `[]` denies all;
- null quotas are unlimited (null, never zero);
- null rate members inherit the deployment; null lazy policy means reject;
- explicit `null` and `[]` keep their distinct meanings.

Non-goals: the document carries policy only - never identity (owner,
cohort, validity, delivery), never secrets, never server environment.
Existing bound client-module repin/removal stays blocked and must use the
reviewed compatibility migration path, not this editor. Mutations require
the confirmation checkbox plus a bounded reason — nonblank, at most
512 Unicode characters, enforced server-side on these GUI seams with a
fixed safe refusal before mutation or audit, and matching `maxlength`
plus visible field help on the field (207-b; the unchanged CLI is not
claimed to enforce this bound) — with the actor from the session. A
rejected document is never redisplayed. Credential protection at
these seams is scoped by value kind (recognized through the existing
redaction rules, including configured accepted key prefixes):
credential-shaped MODEL identifiers in the document's
`allowed_models` are refused with a fixed safe message before the
shared validators (whose safe message would embed the rejected
model); credential-shaped values in the reason or other retained
fields are MASKED — a valid change with a credential-shaped reason
still succeeds and is stored/redisplayed masked. A recognized shape
never reaches the re-rendered form, the flash, the logs, the audit
note, or the export, and useful ordinary values are preserved. The
download link serves
only the service's allowlisted projection as an `attachment` with
`Cache-Control: no-store` and a
`slaif-key-configuration-<public_key_id>.json` filename; it authenticates
through a non-rotating read-only session context (same real
active/expired/revoked session checks, same login behavior) that does
NOT refresh the stored CSRF token, so the detail page can be downloaded
and then edited with its own still-displayed form (browser-qualified
in 207-b).

In document mode on the create page, the guided POLICY controls are reset
to off by the page script (the server additionally rejects guided policy
fields submitted alongside a document); identity fields always stay guided.
In guided mode the explicit defaults are preserved, so JavaScript and no-JS
submissions express the same state.

### 8.4 Rate editor: units, inheritance, and the no-op law

The per-member editor offers four independent actions - leave unchanged,
set a positive whole number, or clear (inherit the deployment). Counts are
requests-per-window, tokens-per-window, and concurrent requests; the window
member is seconds. Zero is not a value (inherit is the "clear" action),
and a submission that changes nothing is refused with a fixed message.
Clearing the window member has no deployment default: it falls back to the
runtime's standard window. The editor applies the shared
`KeyService.update_gateway_key_rate_limits` operation with the session
actor and the bounded reason (nonblank, at most 512 Unicode
characters, GUI-side bound with the fixed safe refusal before
mutation or audit); lifetime quotas, lazy mode, validity, replay/
module binding, material, usage, and reservations are never touched.
Readable values note that enforcement happens only while
`ENABLE_REDIS_RATE_LIMITS` is true; the page says so explicitly when Redis
rate limiting is disabled.

### 8.5 Configuration-only explanations

The "Effective Policy" section and "Explain Model Access" panel are
**configuration-only** projections built by the shared
`key_policy_inspection` functions (the same code the CLI uses): they show
configured/effective/source per control, the provider state, and - for a
requested model/endpoint - the shared verdict, blockers, resolution,
allow-list intersection, bounds, and not-evaluated states. They perform no
authentication as the key, no admission/quota/pricing check, no counter
reset, and no provider call, and they are labeled as such on the page. If
the inspection context cannot be built, the explain action answers with a
fixed 503 "Policy explanation is currently unavailable." rather than a
partial answer.

### 8.6 Privacy, authorization, and help patterns

- Every touched control is wrapped in a `<label>` and carries
  `aria-describedby` help beside or below the field (units, blank/default/
  inherit/deny meanings, and examples where useful); help is text, not
  placeholder-only.
- All mutations go through the existing session/CSRF contexts with the
  session as actor; reasons on the new/touched key mutations are
  nonblank and at most 512 Unicode characters (server-side refusal
  before mutation or audit; this corrects the 207-a record's
  unqualified "bounded" wording); confirmations are explicit
  checkboxes where the action is destructive or ambiguous.
- Fixed safe error messages never echo submitted values. On the 207
  surfaces, credential-shaped model identifiers are refused with a
  fixed safe message BEFORE reaching the shared validators, and
  credential-shaped values in reasons and the other retained form
  values are masked in every retained surface — the re-rendered
  form, flash errors, audit notes, and failure logs — while useful
  ordinary values remain readable for correction. Explain model
  access keeps the unchanged shared classifier on the original input
  and masks only its retained form display. Downloads are
  private/no-store and do not rotate the form CSRF; no plaintext key
  material is added to URLs, forms, or local storage.

### 8.7 Upgrade notes

Deploying this change is a normal rebuild/restart of the API assets; there
is **no schema migration** and no policy mass-update. Historical deny-all
keys stay deny-all, and stored allow-lists keep their values. The behavior
change for operators: a POST that leaves the provider selection empty with
no mode checked now **fails closed** instead of silently meaning
unrestricted - creating an unrestricted key requires the explicit
"Allow all enabled providers" mode (the guided default). A reason
longer than 512 characters on a new/touched key mutation is refused
with a fixed message (no mutation, no audit row); the affected fields
show `maxlength=512` and the matching visible help.

## 9. Reviewed key cloning (208-a)

This section documents the key-cloning surface delivered by objective
208-a (G04 of `docs/MISSING_GUI_FUNCTIONALITY.md`). It reuses the
existing shared services (`KeyCloneService`, record pickers, redaction
seam, session/CSRF contexts); no new database schema, table, or
client/server module was added, and no new sortable tables were
introduced (the review and result views are grouped field cards).

### 9.1 Navigation

- **Key detail** (`/admin/keys/{id}`): a new "Clone This Key" action
  panel (bounded, after the template-provenance section) with a
  "Clone this key" link and a "Check a clone outcome" recovery link.
  All prior detail sections and actions remain unchanged.
- **Clone form** (`/admin/keys/{id}/clone`): source identity card
  (public key ID, prefix, status, validity, purpose) with a read-only
  core eligibility line; the existing latest-100 record pickers for
  "Target owner" (required) and "Target cohort (optional)" (blank = no
  cohort), with plain-text UUID inputs when JavaScript is off; a
  three-way validity radio (copy source expiry / duration from
  execution time / exact UTC window) with seconds/minutes/hours/days
  units for the duration; and the one-time delivery select
  (none / pending / send-now / enqueue) whose options carry fixed
  plain-language channel descriptions.
- **Review** (`/admin/keys/{id}/clone/review` result of the form POST):
  the reviewed plan identity (operation UUID and fingerprints), a
  readable "Canonical Policy (copied exactly)" card, the reviewed
  target/validity/delivery summary, the raw non-secret plan and policy
  JSON as optional `<details>` blocks, and the apply form.
- **Result and recovery**: the apply result page (one-time plaintext
  where the channel allows, new-key identity, delivery status, recovery
  link) and the read-only outcome recovery view
  (`/admin/keys/{id}/clone/receipts?operation=...`).

### 9.2 Review readout semantics

- Provider/model/endpoint rows use the same tri-state wording as the
  207 policy surfaces (unrestricted / allow-list / deny-all).
- **Rate limits are labeled by the window the runtime meters in.**
  When the copied policy carries a non-minute `window_seconds`, the
  readout says e.g. "30 requests, 0.01M tokens per 10s window, max 2
  concurrent"; minute (60s) and omitted windows keep the existing
  "req/min / tokens/min" grammar. The exact raw policy stays in the
  optional JSON detail, and the `num`/`tokm` grouped/M formatting is
  unchanged.
- **Lazy throttling honors the explicit mode**: `wait` renders the max
  wait / max waiting counts; `reject` (or absent) renders "Reject
  immediately (default)" - never a truthiness-only "wait" claim.
- Live-burn, external-tool, and Responses rows reuse the existing
  summary helpers; the fenced external-tool policy additionally
  surfaces that a FRESH confirmation checkbox will be required at
  apply (it is never copied from the source key).
- The confirmation help states the binding honestly: the admin submits
  the confirmation and the audit reason, the acting admin is derived
  server-side from the signed-in session, and re-applying the SAME
  valid operation returns the already-applied target instead of a
  second key.

### 9.3 Safety and error behavior

- The review page carries a signed intent token (hidden input); the
  page itself never shows key material. The token is bounded in
  encoded and decoded size, expires, and is bound to the admin user,
  session, source, and delivery channel; tampered, expired,
  wrong-actor/session, wrong-source, or malformed states are refused
  with fixed safe messages BEFORE any mutation.
- A source that disappears (or never existed) yields a controlled 404
  on the form, the review, and the re-render path - never a form
  requiring absent key fields.
- Ineligible sources (non-standard purpose/mode, suspended or expired,
  fenced, secret-shaped policy) show a fixed controlled state on the
  form and are refused at review with the core's fixed message; the
  source policy is never reset or weakened to force eligibility.
- The generated key is displayed at most once, only for the
  none/pending channels, in a private no-store page; send-now/enqueue
  results never show it. A post-commit channel failure renders
  "Created With Delivery Failure" with the stable target/secret/
  delivery IDs and "A second clone is NOT needed".
- The reason is nonblank and at most 512 Unicode characters, refused
  server-side before mutation or audit, and masked through the existing
  redaction seam before storage; the recovery view redacts the
  operation input before redisplay while preserving useful ordinary
  UUID errors.

### 9.4 No-JS and narrow behavior

- Without JavaScript the record pickers fall back to plain-text UUID
  inputs (typed or pasted), the validity radios and duration inputs
  work as-is (the server reads only the selected mode's fields), and
  the whole flow through to the persisted clone is usable.
- The progressive-enhancement script only enables/disables the
  non-selected validity-mode inputs; it never converts or scales any
  value. The review and apply controls remain usable at the narrow
  desktop viewport (qualified at 768px).

### 9.5 Upgrade notes

Deploying this change is a normal rebuild/restart of the API assets;
there is **no schema migration** and no key mass-update. Existing keys
are not touched: cloning is an explicit two-step operator action that
creates a NEW key with independent material, identity, zero usage and
reservations, and its own replay ownership. The only operator-facing
behavior change on the key-detail page is the new action panel.
