# OAP Work Order — 214-a

PR mode: CREATE_NEW_PR

## Objective and current-state preflight

Deliver G11/G13/G18 from docs/MISSING_GUI_FUNCTIONALITY.md: grouped usage and
live-burn reporting, safe JSON export, complete filter-preserving list navigation,
reviewed matching-model pricing disable and effective FX lookup. Preserve the
existing GUI, CLI, accounting and adapter contracts. The human approved the
complete207–219 GUI plan;215–219 remain required after this bounded objective.

Verified at 2026-11-01T15:28:14.761656+00:00: remote main 7ede8cc54b72f2c8e0e81913082dfae0c97d2173, tree
57b7c90be97ca44c629b016cefa4568711f05daf; unique preceding PR 369 merged 2026-11-01T15:16:09Z after all
final-head review/material/check gates. Actualmain all3workflows/all9checks
successful (lastmainjob2026-11-01T15:27:40Z, rootverified2026-11-01T15:28:14.761656Z), merge tree equals accepted SELF 2506e127f6bbec2005d8ccc4f08cbfb59b477a86, terminal timing
recorded. Pre-activation active213-a; exact prior order/report bytes order213-a SHA256ee6e394beb22b334fa3ace49a25cc6d50d2ff7e03b9e08a478802c04e06843df (16038bytes), immutable report213-a SHA256532219415253a42ec7f16d7b5c97f56367fd18c62a0cb7b2ca597360e222eb67 (19898bytes).
Open PRs: only unrelated Dependabot319; no open213/214 or duplicate objective PR, releases onlyv0.1.0-rc.1, published2026-05-01T21:33:27Z; no new release/tag, branch protection active23580289 deletion/non-fast-forward protection, no bypass;19441572/15649613 disabled; finalCI/material review remain mandatory, shared
worktree preservation clean tracked branch at213 reportSELF; protecteduntracked CODEX-SESSIONS.md/codex.sh/uv.lock hashes unchanged; ignoredoperator .env/.codex/catalogs/worktrees preserved, verified FIFOs/waiter solewaiter2908033 bash wait-control-and-wake.sh, cwd/home/janezp/codex-supervision/slaif-api-gateway, TMUX_PANE=%9; existingCLI3308462 unchanged; trueFIFOcontrol4501469/response4501470. Fresh SAMECLI conversation/currentworktree selected for next self-contained order; no model/profile/effort/process/config change.

Closed root handles40130mainCI/32737finalPRCI/81207merge and89521response must
NEVER be repolled or213-a re-signaled. The canonical root helper creates the
sole214 response reader only after this order and active are published.

Create ONE PR from that remote main on oap/214-gui-reports-pagination.
PR title: Add grouped reports, pagination and reviewed catalog tools to the admin GUI.
Coding agent owns Git; strategic owns unchanged order/active bytes. No reset/clean/
stash/forcepush, helper agents, nested models, profile/effort changes. Existing
right tmux pane only. Preserve protected files, ignored operator settings,
linked worktrees and generated catalogs. No deploy/release/tag or production.

Read current governance, GUI plan, admin-usability, usage/CLI/export/security
contracts and the selected inert proposal at
/home/janezp/codex-supervision/slaif-api-gateway/workorders/214-a-gui-reports-pagination-PROPOSAL.md
and GUI-PARITY-ROUND-PLAN.md beside it. Refresh only the concrete changed seams;
do not create another broad inventory or duplicate proof catalog.

## Shared reporting and bounded source evidence

Reuse services/usage_report_service.py UsageReportService and schemas/usage.py,
UsageReportFilters, canonical grouping/export and chat_live_burn_telemetry.
Seven supported dimensions: provider, model, provider_model, owner, cohort,
key and day. Retain existing ledger/detail/CSV workflows and clearly link the
new report surface from Usage and Operations. Do not repurpose a dynamic UUID
route or turn the existing filter form into a different reporting contract.

Current summarize_usage and summarize_chat_live_burn load matching source rows
with limit=None. Add a minimal OPTIONAL max-source-rows service seam, default
None so unchanged CLI behavior remains. GUI source ceiling10000 ledger rows;
fetch at most10001 using existing repository query and REFUSE overbroad scope
with useful time/key/model narrowing help. Never summarize a silent prefix,
count through a separate racing query, or duplicate aggregation in controllers.
No SQL aggregation/accounting rewrite or settings/schema platform. Group rows
are separately paged/rendered from the complete accepted bounded summary;
never confuse group display limit with source completeness.

Grouped estimated/actual cost sums currently coerce missing values to zero.
Preserve existing money aggregation/default CLI output, but add the smallest
shared availability projection needed for per-group known/missing evidence,
using the SAME bounded source rows and grouping law. CLI usage summarize serializes
UsageSummaryRow with dataclasses.asdict; adding fields to that existing result
would change its JSON output. Prefer an additive typed reporting result/wrapper
or equivalent opt-in availability result while keeping existing summary/export
return shapes and CLI JSON field sets unchanged. Prove that compatibility with
a focused actual CLI/shared-service consumer regression. Distinguish genuine known
zero, all-missing and mixed/incomplete costs. Do not label an incomplete sum as
final actual cost, infer missing cost, or unlock a hold. Provider-native reported
cost is optional and must not be presented as EUR or summed across incompatible
currencies without an existing authoritative rule. Keep live-burn provenance,
missing final provider usage, interrupted/estimated/held facts explicit.

Use the CLI's exact supported summary/export filters: inclusive aware UTC
start/end, provider, model, owner/cohort/key. Existing ledger's richer multi-
filter OR-within/AND-across contract remains; do not pretend new single-value
CLI report filters are an identical scope to that ledger. Existing-record
selectors use shared latest100+older-search or finite native selects, selected
records hydrated and validated against actual existence/eligibility. No bare
UUID field, new picker transport or secret-bearing query echo. Explain scope,
blank/defaults, units and complete-vs-bounded result semantics beside controls.

Safe JSON export uses the shared UsageExportRow allowlist, exact raw machine
units, nullable costs, strict JSON (no NaN), and explicit bounded scope. Use the
existing configured ADMIN_USAGE_EXPORT_MAX_ROWS for requested export ceilings;
fetch cap+1 and refuse overflow or explicitly describe partial output and exact
counts. Never claim first-page data is complete. No raw ORM/response_metadata,
prompts, media, reasoning, tool payloads, credentials or environment dump.
Preserve existing confirmed/reasoned CSV workflow/formula safety/caps. New
exports use session-derived actor, CSRF/confirmation/reason and existing safe
audit convention; private no-store attachments do not rotate an open form's
CSRF token. Safe fixed noecho failures and unknown-commit honesty remain.

## Complete stable navigation and lookup

Add reusable Previous/Next navigation to every actual offset/limit GUI list,
including related lists that really page; fixed bounded snapshot tables need
no invented database paginator. Inspect actual handlers/templates rather than
claiming every table is a paged database list. Use cap+1 service/repository
queries or existing real page metadata. A full page alone is not has_more.
Preserve valid custom1..200 limits, repeated selected query values, OR-within/
AND-across filters and chips. Build navigation URLs from the allowlisted, accepted normalized
filter pairs (retaining repeated values), not a raw copy of the incoming URL
or arbitrary unknown query parameters. Filter/row-limit changes coherently
start at first page; navigation carries scope and exact selected filters.
NoJS links work.
Display first ordinal offset+1, real page range/empty/more states and correct
previous/next availability. No all-database browser load, guessed total count,
new global sort engine, or hidden client-side pagination over a limited fetch.

Add deterministic identity tie-breaks to directly touched paged repository
orderings where required, retaining existing primary order and filter behavior.
Document ordinary offset paging can shift under concurrent inserts; do not
promise a frozen snapshot or add cursor/session infrastructure. Sorting remains
shared exact raw typed sorting OF THE DISPLAYED PAGE; neutral markers, missing-
last both directions, independent requests/tokens/cost columns. Retain current
comma/actual-zero/M-token formatters, exact identities and edit/download units.

Legacy _load_catalog_provider_choices list_providers(limit=200) feeds route
form validation. Verify an older eligible provider selected through existing
search beyond that batch can actually be saved. Replace finite-page membership
as an authorization/existence test with bounded exact service/repository lookup
if reproduced. Preserve unknown/ineligible provider refusal and the EXACT
existing eligibility and route parsing/Core rules. The legacy choice service
currently lists both enabled and disabled provider configurations; do not add
a new enabled-only restriction to preparation/editing as part of this lookup
fix. Runtime route admission is unchanged. Do not fetch every provider or
weaken selection gates.

## Small catalog operations through shared services

PricingRuleService.disable_model currently lacks actor/reason/review-set guards.
Add the minimal backwards-compatible shared-service/repository review seam for
at most1000 matching enabled rows: exact provider/model/optional normalized
endpoint, safe affected rows/counts and guarded source-state fingerprint.
Overbound scope refuses, never silently trims or nonatomically chunks. Signing
alone is not a service stale guard. Preserve default CLI behavior and existing
individual enable/disable forms. No raw arbitrary pricing metadata in review.

Review then separate confirmation/reason/apply; bind complete bounded plan,
exact scope, safe reason, session actor/session identity,15minute expiry and
one distinct purpose through existing admin_review_intent.py primitives.
Explicit bounded plan/token envelope (128KiB plan ceiling is sufficient for
1000 UUID+hash records without unbounded metadata); no storage/jobs/new secrets.
Core apply locks reviewed rows deterministically, refreshes relevant source
state and matching membership after blocking locks, refuses visible drift,
and disables ONLY exact reviewed rows in ONE caller transaction. A newly
matching unreviewed row is never disabled. Per-row audit carries real actor/
reason. No claim of serializable catalog-wide insert exclusion without proof.
Late audit failure rolls all changes back. Repeat may be honest no-op only
through shared validated semantics, never a second disable or invented receipt.

FxRateService.latest_fx_rate resolves explicit base/quote currencies at UTC
now. Add useful finite/searchable currency choices and field help, show selected
pair/rate/source/validity or honest missing state from this exact helper. Keep
existing FX create/edit/import. No historical-time feature, same-currency rate,
external fetch or accounting-rate selection rewrite is authorized.

## Paths, ergonomics, verification and boundaries

All app paths below are relative to app/slaif_gateway/. Allowed focused NEW
api/admin_reports.py, main.py composition, NEW web/templates/reports/ summary,
live-burn, pricing-review, FX and export forms/outcomes only; NEW
web/templates/partials/pagination.html and utils/admin_pagination.py if needed
for the one shared navigation implementation. Existing api/admin.py and
api/admin_review_intent.py only directly necessary paging, provider-validation,
navigation and one bounded pricing review purpose. Existing web/templates/
keys/list.html, owners/list.html, institutions/list.html, cohorts/list.html,
providers/list.html, routes/list.html, pricing/list.html, fx/list.html,
usage/list.html, audit/list.html and email_deliveries/list.html for navigation;
operations/index.html and genuinely affected related detail/form templates
within those same existing resource directories only for direct links, safe
older-provider save/recovery, or real paged-related navigation. Fixed bounded
detail snapshots keep their honest scope and useful filtered-list links; do
not invent paginators for snapshots that have no paging contract.

Services usage_report_service.py, pricing_rule_service.py, admin_key_dashboard.py,
admin_records_dashboard.py, admin_catalog_dashboard.py, admin_activity_dashboard.py
and admin_export_service.py only demonstrated bridges above; schemas/usage.py
for additive bounded shared reporting availability result. Repositories
db/repositories/keys.py, owners.py, institutions.py, cohorts.py,
provider_configs.py, routing.py, pricing.py, fx_rates.py, usage.py, audit.py and
email.py ONLY directly paged query/limit/tie-break seams and pricing review
lock/revalidation. Preserve runtime selection ordering and eligibility; a GUI
page tie-break must not change provider route/pricing resolution law. Existing
utils/admin_list_filters.py, services/admin_record_choices.py,
api/admin_record_choices.py and web/templates/_record_choice.html only a
demonstrated necessary shared filter/choice/page-limit seam, not a redesign. FxRateService is read-only reuse
unless a concrete required seam is reported first. No new business-rule layer,
CSS/JS sorter, schema/settings, workflow platform or blanket rewrite. If exact
existing shared helper filenames differ, report the equivalent existing seam
before modifying outside this list; do not create guessed paths.

Reuse SLAIF cream/teal/lime shell/local assets, current navigation hierarchy,
known-record controls, ordinal/hyperlink-sort tables, field-specific associated
help and responsive focusable scroll regions. Avoid flat-menu growth, framework,
theme replacement, new table sorter or moving filters as chips wrap. Every new/
touched entry/choice control has unique actual-control ID and useful associated
help. Normal page/mutation auth and CSRF semantics remain; background reads/
attachments never invalidate an already displayed form. NoJS remains usable.

Evidence in /tmp/slaif214; tests unit/test_admin_reports_214.py, integration/
test_admin_reports_214_postgres.py and browser/test_admin_reports_214.py plus
small existing consumer registrations/direct shared seam regressions. Actual
PG+HTTP proofs cover7dimensions, filters/time bounds, source cap+1 refusal,
zero/missing/mixed costs/provenance, exact JSON/safe CSV, all unchanged accounting/
ledger/key fields, pricing actor/reason/exact scope/stale/rollback and FXmissing.
First/middle/end/empty pages, tied primary order, custom limits, repeated filters
and older providers/records beyond100/200 must have observable correct results.
Chromium uses actual shared services/PG for navigation/export/pricing review/
apply/reload, existing displayed-form download then valid mutation, keyboard/
noJS recovery and desktop/narrow captures. Root visually reviews real synthetic
captures. No real provider/Codex/email/production qualification claim.

Canaries protect credential-shaped labels and current incoming authentication
aliases across rendered facts, links, signed review, downloads, logs and audit;
known arbitrary metadata/content never serialized. Negatives reach intended
validator with otherwise valid auth/CSRF; generic400 or login303 is not success.
Reuse unchanged accepted component/concurrency/sorter evidence; no huge scale
fixture or complete local matrix. Run focused relevant guards, OAP9, scoped
Ruff/docs/diff checks. Fixture/docs corrections remainA/samePR; suffix only for
proven blocking defect. Reuse /tmp/slaif192-coding-venv, installed Chromium and existing qualified
ownedPG fixtures; exact resource
owner/fullID/loopback/tmpfs verification before use/cleanup; no ambientDSN or
unowned resources touched. No schema, permission, accounting, adapters, runtime
request/replay law or deployment change. No helper agents/packages/infra.

Update living docs/MISSING_GUI_FUNCTIONALITY.md G11/G13/G18, admin-usability.md,
verification/gui-cli-parity.md, relevant reporting/CLI/operator docs and README
index only. Explain deliberate GUI bounds/filter differences and upgrade with
no schema migration, exact current scope and no liveclient/provider proof.

Publish unchanged order/active with implementation in ONE214PR; coding never
merges/enablesauto. Complete report draft away from finalpath; atomic temp in
reports+flush/fsync+os.replace+dirfsync to the absent final path
oap/reports/214-a-gui-reports-pagination.md; final report never revised. Report-only
SELF soleparent literalIMPL, onlyreportdiff; verify remote exacthead/bytes then
ONE responseOK and ONE canonical controlwaiter in%9. Root final CI/review/
material/visual gates -> guardedmerge -> actualmain3workflows/all9checks/tree ->
authoritative timing before215. FullGUIgoalACTIVE through219; no release/deploy.
