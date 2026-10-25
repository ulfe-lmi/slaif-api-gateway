# OAP Objective 192-a — final report: sortable admin tables and known-record/known-option choices

Work order: `oap/orders/192-a-gui-sorting-and-record-choices.md` (committed
unchanged with `oap/active` = `192-a`).
Branch: `oap/192-gui-sorting-and-record-choices`, base `main`
`4702065cab4a902ce8cf2a52d07f652dffb936ed` (incorporated via merge
`504d569`; remote `main` verified at the base at publication).
PR mode: CREATE_NEW_PR (Objective 192 = exactly one new PR, #342).
The coding agent never merges; no auto-merge is enabled; root reviews
independently.

Implementation head SHA: 9c4a119fde2052bcfb28a1bd6ecc43d319cc6a21
Report publication commit: SELF

## What changed

Operator-facing admin dashboard usability, in two bounded families:

1. **Sortable tables.** Every admin list table (25 `data-sortable`
   tables across 24 templates: owners, institutions, cohorts, keys,
   providers, routes, pricing, FX, usage, audit, email deliveries, key
   templates, all import preview/result tables, and the related-record
   tables on detail pages) is upgraded by the single fixed
   `web/static/js/table-sort.js`: real keyboard-focusable header
   buttons (Enter/Space), `aria-sort` announcement, typed column types
   (text/number/money/percent/date/boolean) with `data-sort-value` raw
   keys, EXACT comparison for in-DB-range decimal (Numeric(18,9)) and
   integer (BigInteger, full signed 64-bit) values via scaled-BigInt
   coefficient comparison, missing values last in BOTH directions,
   stable ties, grouped rows move with their details, table
   independence, no network/dynamic code/cell mutation. The generated
   catalog-refresh `REVIEW.html` embeds the SAME fixed script bytes
   (byte equality asserted); `provider_catalog_proposal`'s
   `model-review.md` remains a NON-GUI static Markdown export with no
   script.
2. **Known-record / known-option choices.** 102 known-reference /
   finite-choice fields across 34 templates are backed by searchable
   pickers over real local data (67 `record_choice`, 32 native
   `select`, 3 dual-list policy selectors), with a faithful no-JavaScript
   fallback. The shared `record-choices.js` combobox serves the
   read-only admin lookup `GET /admin/record-choices` (allowlisted
   kinds, minimal columns, bounded distinct/grouped SQL,
   touch=False session validation, NO CSRF refresh), the latest-~100
   page with server-side older search, selected-record hydration that
   never evicts a selected id, UUID spelling canonicalization,
   dependency refetch on real value change (provider→model,
   audit target-type→target-id, distinct-before-limit), multi-value
   chip lists with newline serialization preserved, and the clear
   stale-state law (pending debounce and in-flight results cannot
   reintroduce a cleared query; dependent controls re-fetch scoped to
   the CURRENT parent). The key-policy dual-list selector adds the
   latest-100 provider/model pages with a server search whose scope
   parameters mirror the all/none/one/many semantics exactly
   (explicitly-empty scope = no choices), the exact 22
   method-qualified `IMPLEMENTED_CLIENT_ENDPOINTS` tokens, manual
   textarea sync, and page-is-presentation-not-authority (an older
   provider found by search submits successfully; submitted provider
   ids are revalidated by a bounded enabled-provider DB lookup).
3. **Supporting bounded repairs found under review:** admin GET
   optional boolean filters normalize the "Any" blank value to no
   filter (9 filters; true/false/invalid unchanged; public `/v1`
   untouched); zero-cost display fidelity (`Decimal(0)` actual cost
   displays `0 EUR`, never falls through to estimate/`n/a`); the
   loader call-site spec shape (tuple of 3-tuples); CodeQL
   stack-trace and bad-tag-filter findings (fixed safe message;
   parser-based single-fixed-script audit gate, test-only helper
   `tests/unit/catalog_report_script_audit.py`); and the scoped
   `[hidden]` CSS rule so hidden record-choice menus never overlay
   table headers or other controls.

No core permission, auth, admission, or accounting change. No schema
change, no Alembic migration, no key-format change, no dependency
change. `services/key_import.py` is pristine (the preview/execute
policy-validation parity observation is recorded below as a follow-up
finding only).

## Scope inventory

- 25 sortable tables / 24 admin templates + generated `REVIEW.html`
  report family; `model-review.md` documented as non-GUI static export.
- 102 known-reference/finite-choice fields / 34 templates: 67
  `record_choice` (incl. institution/cohort list NAME filters as
  known-name pickers and the usage provider/model/endpoint/request_id
  filters), 32 native `select` (incl. usage status/streaming), 3
  dual-list policy selectors; justified non-picker families documented
  (new-record identity, record-identity editing incl. the provider
  edit slug's validated unique-slug rename, auth/credentials,
  dates/numbers/money/limits, reasons/notes, bulk documents, hidden
  transport). A raw-reference guard requires a picker/select (or a
  documented exception) for any NEW visible field with reference
  semantics, so coverage cannot silently regress.
- Full coverage matrix: `docs/admin-usability.md` Section 4
  (source-derived; the inventory test is the authority).

## Verification (this objective; focused; all SYNTHETIC data)

Environment: owned temporary PostgreSQL 16 (loopback/tmpfs), real
authenticated admin HTTP (uvicorn), native Chromium (Playwright 1.64.1,
Chrome 156.0.8078.4), venv `/tmp/slaif192-coding-venv`, `PYTHONPATH=app`,
JUnit XML + real exit codes, source-bound by sha256 checksums.

| Suite | Target | Result |
| --- | --- | --- |
| Usability inventory + raw-reference guard | `tests/unit/test_admin_usability_inventory.py` | 111 passed / 0 failed / 0 error / 0 skipped |
| Record-choice unit + Any-filter ASGI parser (24 + 36) | `tests/unit/test_admin_record_choices.py` | 60 passed / 0 failed / 0 error / 0 skipped |
| Key-create unit routes | `test_admin_key_create_routes.py`, `test_admin_keys_routes.py` | 63 passed / 0 failed / 0 error / 0 skipped |
| Related admin CI fixture repairs (10 files) | key-create templates; activity/catalog/records/keys routes + templates-safety; pricing/route actions | 53 passed / 0 failed / 0 error / 0 skipped |
| Catalog report unit modules (full) | `test_catalog_refresh_report.py`, `test_catalog_refresh_source_evidence.py`, `test_catalog_refresh_collection.py` | 180 passed / 0 failed / 0 error / 0 skipped |
| Report browser (one JUnit case auditing 13 generated cases + offline sort) | `tests/browser/test_catalog_refresh_report.py::test_browser_report_sort_script_js_on` | 1 passed / 0 failed / 0 error / 0 skipped |
| Lazy-throttling browser (JS + no-JS) | `tests/browser/test_admin_lazy_throttling.py` | 3 passed / 0 failed / 0 error / 0 skipped |
| Admin PG CI repairs | keys readonly, pricing/route actions PG | 3 passed / 0 failed / 0 error / 0 skipped |
| Multi-scope bounded HTTP (9 providers + 101 → 400) | `test_admin_record_choices_postgres.py::test_multi_scope_http_keeps_all_nine_providers` | 1 passed / 0 failed / 0 error / 0 skipped |
| Admin usability browser module (final, 9 tests) | `tests/browser/test_admin_usability.py` | 9 passed / 0 failed / 0 error / 0 skipped |
| Documentation asof + nav | `tests/unit/test_documentation_asof.py` | 13 passed / 0 failed / 0 error / 0 skipped |

The Any-filter row uses the real ASGI app: unauthenticated
parse-accepted requests get 303 (login redirect), invalid non-blank
values 422 — proving query parsing acceptance/rejection, not
authenticated DB semantics (the authenticated default-Any flow is the
real cohort/institution browser test in the module).

Browser facts (real rendered pages, real stylesheet, unforced
interaction): owner-list sorting not intercepted by menus;
record-choice batch-100/older search/selection; physical keystrokes
(`keyboard.type`, not `fill`) with focus retention, case/opaque-value
preservation (subject to existing trim/server normalization), decoded
lookup-query matching, clear/reopen with no stale typed candidate;
dependent provider→model scoping and clear-under-selected-parent
(fresh scoped lookup; other provider's models absent); policy selector
latest-100 page (oldest 7 providers + disabled provider absent),
explicitly-empty scope → no choices, multi-provider/endpoint scopes,
22 canonical endpoint tokens, older provider AND older model
search+select, real authenticated POST creating exactly one key scoped
to the older provider with the owner chosen via older search (DB
verified: owner, `metadata_json.allowed_providers`, allow-all
flags); one-time plaintext key cells never read.

HTTP/DB facts (owned PG): lookup leaves session/CSRF/domain/accounting
unchanged and the original CSRF token still POSTs; anonymized owners
never offered (q no-match isolation); selected-outside-batch hydration
across UUID/provider-slug/email/plain-model kinds; uppercase and
unhyphenated UUID spellings canonicalize; literal `%`/`\` escaped;
exactly-100 caps; 9 repeated provider scopes preserved, 101 rejected
with the fixed safe 400 message; older enabled provider submits,
disabled provider 400/no key; base catalog eligibility (enabled
provider + implemented endpoint) as a SQL predicate before GROUP/LIMIT;
explicit-scope bulk import preview 200/execute 200/3 rows/12→15
keys/no alerts.

Development receipts (strategic independent probes, source-stable at
their recorded hashes): shared sort 12/12, live-admin 21/21, free-typing
2/2, policy lookup 6/6, older-provider submit 4/4, many-scope 7/7,
name-filter flows, dependent-clear scoped recheck, inventory guard.
They are cited as review evidence; final source qualification rests on
the JUnit rows above plus the final PR-head CI run.

CI status at publication: the first head with the full docs/test batch
(`58eb563`) and the following docs-only head (`e766d40`) ran one unit
failure class unrelated to this objective's behavior — the two
catalog-CLI watchdog nodes in `test_cli_catalog_refresh.py` crashed
their driver subprocess (`ModuleNotFoundError: No module named 'tests'`)
because the new qualified import of the shared test helper
(`tests.unit.catalog_report_script_audit`) needed the repo root in the
driver's explicit import path. The bounded test-support fix (repo root
added to the driver template/path args; all watchdog duration/grace/
status/marker/no-publication assertions unchanged) is the implementation
head recorded above; both watchdog nodes were re-verified locally under
`PYTHONPATH=app` (genuine stall marker + genuine timeout
representations). The final SELF-head CI run is the publication gate.

## Honest limits / skips

- Native Chromium on this machine only; no other browser/mobile claim.
- No full 128-worker sharded matrix run for this objective; the
  required surface is the focused rows above + final-head CI.
- The no-JS fallback is exercised (raw field fill, visible original
  inputs), not a separate accessibility audit.
- Redis-backed throttling semantics are unchanged and covered by the
  pre-existing lazy-throttling suites only.

## Docs impact statement

Documentation updated: `docs/admin-usability.md` (new coverage
reference: sorting law, picker law, lookup boundary, policy-selector
page/search/authority, list filters, full coverage matrix, display
fidelity), `docs/catalog-refresh.md` (fixed single-sort-script
boundary for the generated report), `docs/security-model.md`
(read-only lookup boundary: touch=False, no CSRF refresh),
`docs/first-time-operator-guide.md` (dashboard basics +
update/reload note), `docs/verification/2026-10-25-admin-usability.md`
(new bounded verification record incl. deployment notes),
`docs/verification/README.md` (index entry), `docs/README.md`
(navigation link).

## Follow-up finding (NOT bundled, no product change)

Bulk key import: `key_import.execute` enforces explicit policy
columns (e.g. `allowed_endpoints`, `allowed_models`) and rejects a
row with omitted permission scopes, while the PREVIEW stage does not
surface the same per-row policy-validation classification (operators
see the denial only after confirming execution). Record as a strategic
follow-up; `services/key_import.py` intentionally left pristine —
defaulting omitted permissions to allow-all would widen key policy and
is out of scope.
