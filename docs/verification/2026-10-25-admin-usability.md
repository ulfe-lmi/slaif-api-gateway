# 2026-10-25 Objective 192-a admin-usability verification record

Dated, commit-specific evidence for the admin-dashboard usability
objective (sortable tables + known-record/known-option pickers). All
evidence is local and synthetic: owned temporary PostgreSQL 16
instances, real authenticated admin HTTP (uvicorn on a loopback port),
and native Chromium (Playwright 1.64.1, Chrome 156.0.8078.4). No real
upstream provider key, model, or email was used; no production,
release, security, or compliance claim follows.

Coverage surface: 25 `data-sortable` tables across 24 admin templates
plus the standalone catalog-refresh `REVIEW.html`, and 102
known-reference/finite-choice fields across 34 templates (67
`record_choice`, 32 native `select`, 3 dual-list policy selectors),
pinned by `tests/unit/test_admin_usability_inventory.py` (111 tests).

## Focused pytest evidence (JUnit, real exit codes)

| Suite | Command target | Result |
| --- | --- | --- |
| Inventory + raw-reference guard | `tests/unit/test_admin_usability_inventory.py` | 111 passed / 0 failed / 0 error / 0 skipped |
| Record-choice unit regressions + Any-filter ASGI parser | `tests/unit/test_admin_record_choices.py` | 60 passed / 0 failed / 0 error / 0 skipped |
| Key-create unit routes | `tests/unit/test_admin_key_create_routes.py`, `tests/unit/test_admin_keys_routes.py` | 63 passed / 0 failed / 0 error / 0 skipped |
| Related admin CI fixture repairs | activity/catalog/records/keys routes + templates-safety + pricing/route actions | 53 passed / 0 failed / 0 error / 0 skipped |
| Catalog report unit modules (full) | `tests/unit/test_catalog_refresh_report.py`, `tests/unit/test_catalog_refresh_source_evidence.py`, `tests/unit/test_catalog_refresh_collection.py` | 180 passed / 0 failed / 0 error / 0 skipped |
| Report browser (generated cases + offline sort) | `tests/browser/test_catalog_refresh_report.py` | 1 passed / 0 failed / 0 error / 0 skipped |
| Lazy-throttling browser (JS + no-JS fill helper) | `tests/browser/test_admin_lazy_throttling.py` | 3 passed / 0 failed / 0 error / 0 skipped |
| Admin PG CI repairs | `test_admin_keys_readonly_postgres.py`, pricing/route actions PG | 3 passed / 0 failed / 0 error / 0 skipped |
| Multi-scope bounded HTTP (9 providers + 101 rejection) | `tests/integration/test_admin_record_choices_postgres.py::test_multi_scope_http_keeps_all_nine_providers` | 1 passed / 0 failed / 0 error / 0 skipped |
| Physical keystroke + record-choice flows | `tests/browser/test_admin_usability.py::test_allow_new_physical_keystroke_typed_value_is_authoritative` | 1 passed / 0 failed / 0 error / 0 skipped |
| Multi chips + dependent pickers (incl. scoped clear) | `tests/browser/test_admin_usability.py::test_multi_chips_and_dependent_pickers` | 1 passed / 0 failed / 0 error / 0 skipped |
| Policy selector page/search/scope/submit | `tests/browser/test_admin_usability.py::test_policy_provider_model_search_and_older_submit` | 1 passed / 0 failed / 0 error / 0 skipped |

The record-choice row includes 24 pre-existing regressions plus 36
new real-ASGI query-parser cases (9 admin GET boolean filters x
blank/true/false/invalid): the unauthenticated 303 / invalid 422
outcome proves QUERY PARSING acceptance and rejection, not
authenticated database semantics (the authenticated default-Any
flow is covered by the real cohort/institution browser test).

## Browser-layer facts (actual rendered pages, real stylesheet)

- Owner list header clicks: real ascending/descending clicks are not
  intercepted by record-choice menus (the scoped `[hidden]` CSS rule
  for `.rc` descendants is the fix; no forced clicks, no sleep).
- Record-choice: batch-100/older-search/selection, keyboard
  Enter/Space on table headers and pickers, Escape/clear/verbatim
  typed values, dependent provider→model scoping, and
  clear-under-selected-parent (fresh scoped lookup, stale query and
  stale typed candidate absent).
- Physical keystrokes (`keyboard.type`, not `fill`): focus stays on the
  primary input of `allow_new` controls, and the typed value is the
  submitted candidate with its case and opaque characters preserved
  (subject to the existing edge-trim and server-side normalization —
  not a byte-exact edge-whitespace claim); the debounced lookup
  searches the typed text (decoded-query matching; `URLSearchParams`
  encodes spaces as `+`).
- Policy selector: provider page is exactly the latest 100 enabled
  providers (oldest 7 and the disabled provider absent); explicit
  empty endpoint scope sends `endpoint=` and returns no choices;
  multi-provider + endpoint scopes are honored; 22 canonical
  method-qualified endpoint tokens; an older provider AND an older
  model (outside their latest-100 pages) are reached by server search
  and selected; a real authenticated POST creates exactly one key
  scoped to the older provider (owner also chosen via older search);
  submitted value verified in PostgreSQL.

## HTTP/DB-layer facts (owned PG + real authenticated HTTP)

- Lookup endpoint: `GET /admin/record-choices` validates the admin
  session with `touch=False` and does NOT refresh the CSRF token;
  session/CSRF/domain/accounting state is unchanged after lookups, and
  the original form CSRF token still POSTs successfully afterwards.
- Eligibility: anonymized owners are never offered (q no-match
  isolation), selected records outside the batch keep hydrated labels
  (UUID, provider slug, email, and plain-model kinds), uppercase and
  unhyphenated UUID spellings canonicalize, literal `%`/`\` in
  queries are escaped, and exactly-100 caps hold.
- Bounded scope: 9 legitimate repeated `provider=` values are all
  honored; 101 values are rejected with a fixed safe 400 message (no
  silent subset).
- Key-create policy: an older enabled provider found by search submits
  successfully (the visible 100 page is presentation, not authority);
  a disabled provider is denied with 400 and creates no key;
  base catalog eligibility (enabled provider + implemented endpoint)
  is a SQL predicate before GROUP/LIMIT.
- Bulk import: explicit-scope CSV (explicit `allowed_endpoints` +
  `allowed_models`) previews 200, executes 200, creates 3 rows,
  12→15 keys, no alerts; the one-time plaintext key cell is never read
  by tests (safe owner/key-metadata/quota/error cells only).
- Admin GET boolean filters: blank (the "Any" option) normalizes to
  no filter on the nine optional admin filters; `true`/`false` keep
  their meaning; invalid non-blank values still 422; public `/v1`
  behavior unchanged.

## Independent strategic review receipts (read-only)

Root-side independent probes (synthetic own-PG/native browser,
source-stable, receipts under the strategic
`review-artifacts/192-a-review/` tree): shared sort 12/12,
live-admin 21/21 (including the scoped-hidden CSS fix), free-typing
2/2, policy lookup 6/6, older-provider submit 4/4, many-scope 7/7,
name-filter flows, dependent-clear scoped recheck, and the
inventory guard. Each receipt is source-stable AT ITS RECORDED HASH
(a development checkpoint during the objective), not at the final
head; the final source qualification rests on the focused JUnit rows
above plus the final PR-head CI run.


## Deployment notes (objective 192-a)

- No database schema change: no Alembic migration is added or required;
  `alembic upgrade head` on the current head is a no-op for this
  objective.
- No gateway-key format or migration change: key hashes, prefixes,
  versions, and one-time-secret behavior are untouched.
- The change surface is Jinja templates plus local static assets
  (`web/static/js/table-sort.js`, `record-choices.js`,
  `policy-selector.js`) and admin route query normalization.
- Deploy by rebuilding and restarting the normal compose services
  (`docker compose up -d --build` — api, worker, scheduler; or a
  rolling restart of the api container on an existing deployment).
  No worker/scheduler behavior change is required, but a restart
  picks up the new templates/statics.
- Browsers: do a hard refresh (Ctrl/Cmd+Shift+R) after the restart so
  previously cached `table-sort.js` / `record-choices.js` /
  `policy-selector.js` are replaced; the pages are otherwise fully
  functional without JavaScript (progressive enhancement).

## Honest limits

- Browser evidence is native Chromium on this machine; no other
  browser or mobile evidence is claimed.
- The no-JS fallback is exercised in the lazy-throttling and
  record-choice suites (raw field fill, visible original inputs); it
  is not a separate accessibility audit.
- `provider_catalog_proposal` writes `model-review.md` (Markdown with
  an HTML table): a NON-GUI static export, deliberately without the
  sort script; the GUI catalog-refresh `REVIEW.html` carries the
  single fixed `table-sort.js` byte-identically.
- This record does not include a full 128-worker sharded matrix; the
  objective's required focused suites are the rows above plus the
  final PR head CI run.
