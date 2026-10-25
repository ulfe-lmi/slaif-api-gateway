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
  targets out of the initial batch; scoped to the selected
  target type.
- **Request IDs**: the union of usage-ledger request ids (AI calls)
  and audit-log request ids (admin actions), each source bounded.

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
pages are dry-run tables over the parsed rows: Row number (numeric),
status/action, owner, scope, validity (datetime), quotas (money),
policy, email, errors. They are `data-sortable` like every other
table; row associations (owner, created key public ID, quota) travel
with their row. The confirmed-execution result page displays each
one-time plaintext key once (no-store); the permanent browser tests
read only the safe owner/key-metadata/quota/error cells and never the
plaintext cell.

## 6. Display fidelity notes

- A VALID actual cost of zero displays `0 EUR` (it is not "missing"
  and does not fall through to the estimate); an estimate-only row
  displays the estimate; a row with neither displays `n/a` and sorts
  last as missing.
- Import-preview quota cells use explicit `is not none` checks so the
  display and the typed sort key can never disagree for a present
  value. FX rates are positive-only by validation, so their
  truthiness handling stays as-is.

## 7. Verification

See `docs/verification/2026-10-25-admin-usability.md` for the
objective verification record (focused JUnit counts, actual-browser
facts, owned-PostgreSQL facts, and honest skips).
