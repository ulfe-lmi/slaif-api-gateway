# OAP Coding-Agent Report — 214-a

## Work order
- Identifier: 214-a
- Work-order file: `oap/orders/214-a-gui-reports-pagination.md`
- Numeric objective: 214
- PR mode: CREATED_NEW_PR

## Status
COMPLETE

## Executive summary
Delivered G11/G13/G18 from `docs/MISSING_GUI_FUNCTIONALITY.md` in ONE new
PR from verified remote `main`: (G11) the grouped usage summary and
chat-live-burn reports plus the safe strict-JSON usage export, all reusing
the SAME shared `UsageReportService` and `UsageExportRow` allowlist the CLI
uses, with a minimal optional max-source-rows service seam (default None,
CLI unchanged), a 10,000-row GUI source ceiling fetched cap+1 and refused
overbound - the refusal renders on the report page WITH the existing
filter form (submitted scope prefilled) for in-page narrowing, no result
counts and never a silent prefix - and an additive
`UsageSummaryReport`/`UsageGroupCostAvailability` projection that
distinguishes genuine known zero, all-missing ("unavailable", never zero),
and partial sums (explicitly labelled incomplete, never a final actual
cost) without changing the existing summary/export result shapes or the
CLI JSON field set; (G13) one shared no-JS Previous/Next partial
(`web/templates/partials/pagination.html` +
`utils/admin_pagination.py`) on every ACTUAL offset/limit admin list
(keys, owners, institutions, cohorts, providers, routes, pricing, FX,
usage, audit, email deliveries) with cap+1 honest "more", continued row
ordinals (offset+1), allowlisted accepted normalized filter pairs (repeated
values preserved, alias-guarded), deterministic identity tie-breaks on the
touched paged admin orderings (including the usage list; runtime
selection/eligibility orderings unchanged), and the legacy 200-row
provider choice batch demoted to a display batch: route-form save now uses
a bounded exact provider-slug lookup (disabled configs included) so an
older provider beyond that batch saves while unknown/ineligible slugs are
still refused; (G18) the reviewed matching-model pricing disable
(preview -> signed bounded plan <= 128 KiB -> separate confirmation/apply;
deterministic row locking with `populate_existing`, post-lock fresh
source-fact/membership re-validation, fingerprint binding the private
canonical policy hash without rendering raw metadata, one caller
transaction, per-row audit with the verbatim bounded reason, honest no-op
repeat with zero duplicate audits, late-audit rollback) and the effective
FX lookup page over `FxRateService.latest_fx_rate`. The shared
`table-sort.js` gained ONLY an opt-in per-table `data-ordinal-offset`
value (default 0 preserves every existing table; paged templates supply
the accepted server offset) so second-page sorting keeps offset ordinals.
Admin-path 422s now use a narrow safe projection (fixed
loc/type vocabulary, raw input/ctx always omitted, credential-valued
location/message parts withheld via the existing alias helper, original
full string checked before any truncation; the /v1 OpenAI branch and
numeric rejection semantics are untouched). One new PR (#370); the
activated order and `oap/active` are committed unchanged with the
implementation; no merge performed.

## Authoritative GitHub state
- Repository: `ulfe-lmi/slaif-api-gateway`
- PR number: 370
- PR URL: https://github.com/ulfe-lmi/slaif-api-gateway/pull/370
- PR state at report time: OPEN (mergeable MERGEABLE)
- Base branch: main
- Head branch: oap/214-gui-reports-pagination
- Starting remote SHA: `7ede8cc54b72f2c8e0e81913082dfae0c97d2173` (verified `origin/main` by fetch at PR creation, 2026-11-01; merge of PR #369 / objective 213-a)
- Implementation head SHA: `5547b93b3037d144e3566eb60e8024f0eac90bc3`
- Report publication commit: SELF
- Remote PR head after report publication: SELF (literal SHA derived from GitHub)
- Implementation commits pushed before the report commit: exactly one - `5547b93b3037d144e3566eb60e8024f0eac90bc3` ("214-a: Add grouped reports, pagination and reviewed catalog tools to the admin GUI"), whose first parent is the verified `main` and which includes the unchanged activated order and `oap/active`
- Report commit first parent: same as Implementation head SHA
- Created a new PR this turn: yes (#370)
- Amended existing PR this turn: no
- Merge performed: NO

## Changes made
- NEW focused router `app/slaif_gateway/api/admin_reports.py` (prefix
  `/admin/reports`): usage summary (seven CLI group dimensions,
  single-value CLI-parity filters, aware-UTC normalization, 10,000-row
  source ceiling via cap+1, in-memory cap+1 pagination over the COMPLETE
  accepted group set with the stable grouping-key final tie-break,
  per-group cost availability, overbound refusal rendered WITH the
  existing filter form for in-page narrowing), live-burn (same bound law,
  Chat-telemetry-only aggregates, explicit provenance wording), safe
  strict-JSON export (allowlist only, exact raw machine units, nullable
  costs, no NaN, cap+1 refusal, private no-store attachment that never
  rotates the open form's CSRF), reviewed pricing disable (preview /
  apply with the signed bounded plan), FX lookup (finite searchable
  currency choices + selected pair/rate/source/validity from the exact
  shared helper), and the report-owned fixed no-echo error surface
  (`reports/error.html`, allowlisted recovery destinations only).
- `app/slaif_gateway/services/usage_report_service.py`: OPTIONAL
  `max_source_rows` seam (default None; CLI behavior unchanged) with
  cap+1 fetch through the existing repository query and
  `UsageReportSourceBoundError` refusal; additive
  `summarize_usage_report` returning `UsageSummaryReport` (rows keep the
  EXACT `UsageSummaryRow` shape/sort law; availability over the SAME
  bounded source rows and grouping law); live-burn aggregate unchanged.
- `app/slaif_gateway/schemas/usage.py`: additive
  `UsageGroupCostAvailability` + `UsageSummaryReport` (no fields added to
  the existing `UsageSummaryRow`/`UsageExportRow`; CLI `dataclasses.asdict`
  JSON field sets unchanged - proven by the real CLI projection/consumer
  regression).
- `app/slaif_gateway/services/pricing_rule_service.py` +
  `app/slaif_gateway/db/repositories/pricing.py`: backwards-compatible
  reviewed disable seam - at most 1,000 matching enabled rows, exact
  provider/model/optional normalized endpoint, safe compact rows
  [{id, fingerprint}] plan (private canonical policy hash; raw
  metadata never rendered/signed; notes/updated_at excluded), 128 KiB
  plan ceiling enforced in strict shared parsing, `FOR UPDATE` locking
  with `execution_options(populate_existing=True)` so already-loaded ORM
  instances are refreshed, post-lock fresh fingerprint/membership
  re-validation, all-enabled vs all-disabled vs mixed-flag membership law,
  one caller transaction, per-row audit, honest no-op repeat, late-audit
  rollback of everything.
- `app/slaif_gateway/api/admin_review_intent.py`: ONE new pricing-review
  purpose + strict bounded plan+reason envelope (existing primitives;
  15-minute expiry; session actor/session binding; one distinct purpose).
- `app/slaif_gateway/api/admin.py` (only directly necessary seams):
  bounded exact `provider_config_exists` lookup for the route form (the
  200-row legacy choice batch is display-only; disabled configs included,
  matching the legacy list), deterministic identity tie-breaks on the
  touched paged admin orderings (routing admin id tie-break ADDED by
  214-a; usage list created_at.id tie-break; provider list already
  deterministic via unique slug), paged handler navigation seams, and the
  `utc_datetime_local` display filter.
- `app/slaif_gateway/db/repositories/{keys,owners,institutions,cohorts,provider_configs,routing,pricing,fx_rates,usage,audit,email}.py`:
  only directly paged query/limit/tie-break seams and the pricing review
  lock/revalidation; runtime selection/eligibility ordering unchanged.
- `app/slaif_gateway/utils/admin_pagination.py` (NEW): one shared
  cap+1 page builder + allowlisted filter-pair navigation URL builder
  (accepted normalized pairs, repeated values preserved, known-alias
  refusal).
- NEW `app/slaif_gateway/web/templates/reports/` (summary, live-burn,
  export, pricing form/review, FX, error) +
  `web/templates/partials/pagination.html`: server-rendered,
  no-JS-usable, cream/teal/lime shell, existing `.table-wide`/`.num`/
  `.nowrap`/focusable-scroll classes, unique actual control IDs +
  associated field help, comma/M-token formatters with exact raw sort
  keys/titles, compact UTC window display with full ISO detail, one
  visible incomplete marker per partial sum, compact provider-cost
  "k/n known" counts with exact status in the cell title, and the
  overbound-refusal filter-form recovery state (no results, no counts).
- `app/slaif_gateway/web/static/js/table-sort.js`: ONLY the opt-in
  per-table `data-ordinal-offset` (default 0 preserves every existing
  table; sorter comparisons/groups/missing-last/links unchanged).
  Documented consumer impact: `catalog_refresh/sealing.py` recomputes
  REVIEW.html from the current bundled script bytes, so previously sealed
  runs containing old script bytes fail verification after upgrade (safe
  refusal); finish pending catalog runs before upgrading or review a
  fresh run after; NEVER rewrite an old seal.
- `app/slaif_gateway/api/errors.py`: narrow ADMIN-path
  `RequestValidationError` safe projection (fixed loc/type vocabulary;
  raw input/ctx/url always omitted; credential-valued location parts and
  messages withheld by the existing pure alias helper; the ORIGINAL full
  string is alias-checked BEFORE any truncation; numeric rejection
  semantics and the /v1 branch unchanged; disabled-dashboard 404 route
  guards untouched).
- `app/slaif_gateway/web/templates/_record_choice.html`: optional actual
  `control_id` on the visible control (default empty leaves all old
  callers unchanged); new 214 forms use unique IDs + help.
- Existing list templates (keys/owners/institutions/cohorts/providers/
  routes/pricing/fx/usage/audit/email_deliveries) + operations index +
  pricing detail/list: navigation partial + direct report links +
  safe older-provider save; fixed bounded snapshots untouched.
- NEW test modules: `tests/unit/test_admin_reports_214.py` (41),
  `tests/integration/test_admin_reports_214_postgres.py` (20 ordered
  native cases over an owned PostgreSQL + real HTTP),
  `tests/browser/test_admin_reports_214.py` (8, real Chromium + real
  uvicorn + owned PG, actual auth/session/CSRF).
- Existing consumer registrations updated ONLY where the 214 seams
  legitimately changed behavior: `test_admin_slaif_design.py`,
  `test_admin_usability_inventory.py`, `test_admin_keys_routes.py`,
  `test_admin_records_routes.py`, `test_admin_route_actions_routes.py`,
  `test_admin_catalog_routes.py`,
  `test_admin_provider_route_configuration_210.py` (e.g. the expected
  authorized cap+1 repository expectation; never restored
  first-200-membership authorization).
- Living docs: `docs/MISSING_GUI_FUNCTIONALITY.md` (G11/G13/G18 closed
  with exact scope; GUI-ledger-list filter truth; routing tie-break
  added-by-214-a truth), `docs/admin-usability.md` (section 15 operator
  walkthroughs: reports, navigation, reviewed pricing disable, FX),
  `docs/verification/gui-cli-parity.md` (214-a record),
  `docs/upgrade-runbook.md` (no schema migration; catalog sealed-run
  safe-refusal note).

## Files changed
```text
M app/slaif_gateway/api/admin.py
A app/slaif_gateway/api/admin_reports.py
M app/slaif_gateway/api/admin_review_intent.py
M app/slaif_gateway/api/errors.py
M app/slaif_gateway/db/repositories/audit.py
M app/slaif_gateway/db/repositories/cohorts.py
M app/slaif_gateway/db/repositories/email.py
M app/slaif_gateway/db/repositories/fx_rates.py
M app/slaif_gateway/db/repositories/institutions.py
M app/slaif_gateway/db/repositories/keys.py
M app/slaif_gateway/db/repositories/owners.py
M app/slaif_gateway/db/repositories/pricing.py
M app/slaif_gateway/db/repositories/routing.py
M app/slaif_gateway/db/repositories/usage.py
M app/slaif_gateway/main.py
M app/slaif_gateway/schemas/usage.py
M app/slaif_gateway/services/admin_catalog_dashboard.py
M app/slaif_gateway/services/pricing_rule_service.py
M app/slaif_gateway/services/usage_report_service.py
A app/slaif_gateway/utils/admin_pagination.py
M app/slaif_gateway/web/static/js/table-sort.js
M app/slaif_gateway/web/templates/_record_choice.html
M app/slaif_gateway/web/templates/audit/list.html
M app/slaif_gateway/web/templates/cohorts/list.html
M app/slaif_gateway/web/templates/email_deliveries/list.html
M app/slaif_gateway/web/templates/fx/list.html
M app/slaif_gateway/web/templates/institutions/list.html
M app/slaif_gateway/web/templates/keys/list.html
M app/slaif_gateway/web/templates/operations/index.html
M app/slaif_gateway/web/templates/owners/list.html
A app/slaif_gateway/web/templates/partials/pagination.html
M app/slaif_gateway/web/templates/pricing/detail.html
M app/slaif_gateway/web/templates/pricing/list.html
M app/slaif_gateway/web/templates/providers/list.html
A app/slaif_gateway/web/templates/reports/error.html
A app/slaif_gateway/web/templates/reports/fx_lookup.html
A app/slaif_gateway/web/templates/reports/pricing_disable.html
A app/slaif_gateway/web/templates/reports/pricing_disable_review.html
A app/slaif_gateway/web/templates/reports/usage_export.html
A app/slaif_gateway/web/templates/reports/usage_live_burn.html
A app/slaif_gateway/web/templates/reports/usage_summary.html
M app/slaif_gateway/web/templates/routes/list.html
M app/slaif_gateway/web/templates/usage/list.html
M docs/MISSING_GUI_FUNCTIONALITY.md
M docs/admin-usability.md
M docs/upgrade-runbook.md
M docs/verification/gui-cli-parity.md
M oap/active
A oap/orders/214-a-gui-reports-pagination.md
A tests/browser/test_admin_reports_214.py
A tests/integration/test_admin_reports_214_postgres.py
M tests/unit/test_admin_catalog_routes.py
M tests/unit/test_admin_keys_routes.py
M tests/unit/test_admin_provider_route_configuration_210.py
M tests/unit/test_admin_records_routes.py
A tests/unit/test_admin_reports_214.py
M tests/unit/test_admin_route_actions_routes.py
M tests/unit/test_admin_slaif_design.py
M tests/unit/test_admin_usability_inventory.py
```

## Acceptance-criteria evidence

### Criterion 1: shared reporting with bounded source evidence (G11)
- Result: PASS
- Seven dimensions render with proportional native oracles (tbody
  cardinality + summed request counts + representative seeded labels/IDs
  per dimension): PG `test_01_summary_renders_seven_dimensions`; browser
  `test_02_summary_seven_dimensions_render`.
- Filters/time bounds incl. end<start 400 + recovery link: PG
  `test_02_filters_and_time_bounds`.
- Source cap+1 refusal (monkeypatched bound): PG
  `test_05_summary_source_cap_plus_one_refusal` - overbound unfiltered
  scope refused, the refusal renders the EXISTING filter form (no
  results, no "no groups" state), and a narrowing provider filter
  submitted through it reaches an accepted report; live-burn analog in
  `test_06_live_burn_provenance_and_cap`. Unit:
  `test_summary_source_bound_refused` (form present, no completeness
  claims); the NO-JS variant is browser `test_07_nojs_validation_recovery`
  (in-process bound lowered to 3: unfiltered summary refused -> existing
  visible form -> prov-a narrowing -> accepted report, JavaScript
  disabled).
- Zero/known-zero/missing/mixed cost law for BOTH estimated and actual
  (distinct known sums; unavailable rendered once, never zero; one
  visible incomplete marker, exact label in the cell title): PG
  `test_03_cost_availability_zero_missing_mixed`; browser
  `test_02` render check; unit `test_cost_money_display_law` and
  `test_cost_status_counts_comma_display`.
- Live-burn provenance (triggered totals, stop-reason split, final
  provider usage available/missing, estimates labelled non-final): PG
  `test_06_live_burn_provenance_and_cap`; unit
  `test_live_burn_scope_and_bound` (the cap counts ALL matched ledger
  rows, Chat telemetry only aggregates).
- CLI compatibility: `summarize_usage` still returns
  `list[UsageSummaryRow]`; unit
  `test_cli_usage_summary_row_json_field_set_unchanged` runs the REAL CLI
  projection/consumer over the real service default path (no cap) and
  asserts the fixed field set/values plus observed repository
  limit=None; `test_cli_export_allowlist_unchanged` covers the export
  shape.
- Stable grouping-key final tie-break (GUI result only; CLI sort
  contract unchanged): PG `test_04_grouping_key_final_tie_break`
  (tied (request_count, last_seen_at) groups ordered by key).

### Criterion 2: safe strict-JSON export
- Result: PASS
- Unit: `test_export_rows_allowlist_exact_machine_units`,
  `test_export_refuses_overbound_scope_with_counts` (cap+1, exact
  counts, no partial), NaN-free strict JSON, alias canaries on scope/
  reason (withheld, never echoed), unknown-commit honesty.
- PG `test_07_export_exact_json_unchanged_accounting`: real download,
  exact row content (nullable costs exact strings), accounting
  unchanged, audit row with session actor + verbatim reason.
- Browser `test_04_export_download_then_valid_mutation`: real download
  then a second mutation on the UNCHANGED displayed form (form-SUBMIT
  attachments do not rotate the displayed CSRF; a full-page GET
  correctly would).

### Criterion 3: complete stable navigation and lookup (G13)
- Result: PASS
- 11 actual offset/limit lists carry the shared partial; cap+1 "more";
  first ordinal = offset+1; Previous/Next carry allowlisted accepted
  normalized filter pairs with repeated values (the singleton-tuple
  pagination bug and the None-as-unfiltered iteration misses were fixed
  and are covered by the repeated-filter navigation cases, incl.
  `test_admin_keys_routes`/`test_admin_records_routes` two-cohort/repeated
  next/previous URL assertions over the ACTUAL generated hrefs).
- Custom limits 1..200 round-trip; filter/limit changes restart page
  one; NoJS links work (browser `test_03_usage_list_second_page_sort_offset_ordinals`
  sorts page 2 both directions with offset ordinals via the new
  `data-ordinal-offset`; default 0 tables unchanged - the three catalog
  script consumers `test_script_audit_gate_accepts_fixed_and_rejects_extra_scripts`,
  `test_render_is_deterministic_and_byte_stable`,
  `test_render_injects_structural_ordinal_column` all green).
- Older provider beyond the 200-row choice batch saves through the
  bounded exact lookup; unknown provider refused ("Select a known
  provider config."): browser `test_06_older_provider_beyond_200_route_form`
  (real 201-provider seed; JS picker selects the searched option; the
  unknown-slug refusal is posted in the same browser context), unit
  `test_admin_provider_route_configuration_210.py` consumer cases
  (bounded existence seam; first-200-membership authorization NOT
  restored).
- Deterministic identity tie-breaks on touched paged orderings with the
  tied-primary-order qualification incl. the usage list; runtime
  selection/eligibility orderings unchanged.

### Criterion 4: reviewed matching-model pricing disable (G18)
- Result: PASS
- Unit: plan construction/binding (scope, <=1000 rows, 128 KiB plan
  ceiling separate from the wrapper envelope, private canonical policy
  hash fingerprint excluding notes/updated_at, stable fingerprint),
  strict parsing refusals (count, unique IDs, row/scope consistency,
  str-typed IDs), token purpose/expiry/actor/session refusal,
  `uuid.UUID` str() fixes.
- PG (real PG + real HTTP + real auth/CSRF): preview writes nothing
  (full state digest); successful apply changes ONLY enabled/updated_at
  on the reviewed IDs (all other price columns + unreviewed rows
  unchanged); stale source facts refused with zero writes; late audit
  failure after real `add_audit_log`/flush rolls back EVERYTHING (full
  pricing table + unrelated key/ledger/quota digests compared);
  honest repeat via the ORIGINAL signed token/CSRF is a no-op with zero
  new audits; per-row audit carries the actor + verbatim bounded
  reason; the cached-ORM interleaving case (two real AsyncSessions on
  the same owned PG: B locks+edits while A waits - observed via
  `pg_blocking_pids` - then A's apply refuses with fresh post-lock
  facts); per-test accounting preservation guard over all 20 cases.
- Browser `test_05_pricing_preview_apply_reload_repeat`: real
  preview/apply through the GUI, an actual metadata mutation (private
  export POST with the SAME session CSRF) between preview and apply
  proving the displayed review form stays valid, the unchanged visible
  apply form succeeds, the ORIGINAL token/CSRF replay is the honest
  no-op, and accounting components are unchanged.
- UX law: blank reason field with placeholder (no boilerplate reason),
  operator-terms copy ("will be disabled", future matching rows need a
  fresh review, disabling may block future requests and never
  recalculates past usage, UNCONFIRMED outcomes require checking
  pricing/audit before retry - no rollback promise for committed
  changes), result-only IDs, no verbatim-reason contradiction.

### Criterion 5: effective FX lookup (G18)
- Result: PASS
- Finite searchable currency choices + field help; selected
  pair/rate/source/validity from `FxRateService.latest_fx_rate` (UTC
  now) with honest missing state; no historical-time feature, no
  same-currency rate, no external fetch, no accounting-rate rewrite:
  unit FX cases in `test_admin_reports_214.py`; PG FX row in the
  ordered module (rate 1.10 EUR->USD rendered from the seeded pair).

### Criterion 6: privacy/alias canaries and safe admin 422s
- Result: PASS
- Known-incoming-alias withholding across rendered report facts,
  Previous/Next links (refusal rather than silent drop), signed review
  scope, export scope/reason, DTO leaves, audit, and the safe 422
  projection: unit canaries (`test_admin_validation_rejection_never_echoes_submitted_value`,
  `test_admin_validation_loc_long_credential_withheld_before_truncation` -
  the ORIGINAL full string is checked before truncation), real in-memory
  ASGI probes (no DB/network) showing `limit=<syntheticCredential>`
  422s no longer echo raw input on ADMIN paths while /v1 semantics are
  unchanged.

### Criterion 7: browser/visual gate
- Result: PASS
- 8/8 browser cases (real Chromium + real uvicorn + owned PG, actual
  auth/session/CSRF): login/nav, 7-dimension render, page-2 sort with
  offset ordinals (both directions), export-then-mutation, pricing
  preview/apply/reload/repeat, older-provider route form, no-JS
  validation + cap recovery, desktop/narrow captures incl. ONE
  populated pricing-review narrow capture. Root material/visual gate:
  ACCEPTED (normal-view summary readability after the layout
  corrections - table in the first viewport, single incomplete marker,
  unavailable once, compact "k/n known" provider counts, compact UTC
  windows with full ISO titles, condensed scope line, "Sorting applies
  to this page; new records may shift pages" pager note; populated
  narrow review accepted; extended case-07 no-JS cap proof accepted).

## Verification evidence (receipts under /tmp/slaif214)
- Native PG module (20 ordered cases, real PostgreSQL + real HTTP):
  `/tmp/slaif214/pg-214a-1.xml` - tests=20 failures=0 errors=0 skipped=0
  (2026-11-01T19:35:38Z), SHA256
  `e7753d41151738d4d1365c977394172536759f5d4101bee6e68a9246629b2921`.
  Independent strategic verification of the preceding 20/20 receipt
  recorded; the final code re-run is the superseding receipt.
- Browser module (8 cases): `/tmp/slaif214/browser-214a-1.xml` -
  tests=8 failures=0 errors=0 skipped=0 (2026-11-01T19:35:05Z), SHA256
  `42e5c7a02879598c062ba2e74cb7d0ccbc91e21e5fce485deee0d0e77acee8bf`.
- Unit reports module (final code): `/tmp/slaif214/unit-214a-3.xml` -
  tests=41 failures=0 errors=0 skipped=0 (2026-11-01T19:35:39Z), SHA256
  `9291fd3c9bc811cfb5648dba80434d06f59cc9ce591344426fe363f5bdf6976b`.
- Unit trio (reports + slaif-design + usability-inventory):
  `/tmp/slaif214/unit-214a-2.xml` - tests=174 failures=0 errors=0
  skipped=0 (2026-11-01T19:15:32Z, pre-final copy/cap-wording code);
  the design+inventory modules re-verified 133/133 (stdout) after the
  final wording, and the reports module by the final 41-case receipt.
- Affected-consumer unit receipt: `/tmp/slaif214/unit-214a-1.xml` -
  tests=289 failures=0 errors=0 skipped=0 (2026-11-01T17:21:05Z,
  intermediate code; superseded where later receipts exist). The full
  unit suite receipt `/tmp/slaif214/unit-214a-full.xml` (7,023 tests,
  2026-11-01T17:22:31Z) was run at an intermediate development state and
  is NOT a final-code claim.
- Catalog script consumers (the three named
  `test_catalog_refresh_report.py` selectors): green in the focused run
  and covered by the accepted full-unit receipt; not rerun after.
- OAP governance: `tests/unit/test_oap_governance.py` 9/9 (final code).
- Static: `ruff check` clean on every changed app/test file (CI gate is
  `ruff check` only; `ruff format` intentionally not applied to
  pre-existing accepted style).
- Screenshots: `/tmp/slaif214/214-summary-desktop.png`,
  `214-pricing-review-desktop.png`, `214-summary-narrow.png`,
  `214-pricing-narrow.png`, `214-pricing-review-narrow.png` (populated).

## Boundaries and honest limitations
- One PR, no merge, no auto-merge enabled; strategic-side review, final
  CI, and the guarded merge remain pending per the OAP protocol.
- No full HPC matrix was run this objective (scoped local qualification
  only, as ordered); no release/tag/deploy/production/real-provider/
  real-email claim follows.
- No schema, permission, accounting, adapter, runtime
  request/replay-law, or deployment change; the CLI contracts and the
  existing summary/export result shapes are unchanged.
- The `table-sort.js` byte change makes previously sealed catalog runs
  fail verification after upgrade (safe refusal); existing seals are
  NEVER rewritten (upgrade-runbook note).
- Browser receipts are local owned-PG/Chromium qualifications, not
  production guarantees.
- `docs/rc2-feature-scope.md` status is unchanged by this objective
  (GUI completeness is tracked in `docs/MISSING_GUI_FUNCTIONALITY.md`;
  215-219 remain required after this objective).
