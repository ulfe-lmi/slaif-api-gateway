# OAP Work Order — 188-a

## Objective and human authority

Finish the approved branding mandate by creating the packaged SLAIF visual
styling, like SLAIF Asset Reservation, on the existing Gateway web interface.
Complete the visible branding integration across ALL admin pages, then verify
full operator-branding parity. The human explicitly authorized planning and
execution of all stages through the tested coding agent/OAP. No fresh approval
is needed for this stage or ordinary bounded corrections. This is the final
planned objective of this mandate; do not invent follow-on roadmap work.

PR mode: `CREATE_NEW_PR`
Repository: ulfe-lmi/slaif-api-gateway
Base: main at af4206cb7ada923f29c946f264461c8e237abac2
Branch: oap/188-slaif-visual-design
Title: feat: apply SLAIF visual design to the admin interface

## Verified state and required reading

187 PR325 MERGED2026-10-16T23:45:41Z as af4206cb. Accepted report SELF
31277f98db7e33d16e9e977805854798ec2ca8be, first parent
32fc43109840c0168383108800a20d153b5b256a; report SHA256 9bee43a297895e871f05f28ee44294d4b46177951ac90fa32eba03a2087385b0.
All ten exact SELF checks passed; all NINE actual merged-main checks and THREE
workflows SUCCESS. Only unrelated Dependabot319 open; no188 PR. Main ruleset
23580289 deletion/non-fast-forward, no bypass; release remainsv0.1.0-rc.1.
Current checkout is187-b SELF with only CODEX-SESSIONS.md/codex.sh untracked.
Preserve these, .codex/.local-provider-catalog, unrelated worktrees/resources,
all prior activated orders/reports, and objective-neutral message.txt.
Existing sole coding control waiter335185 in pane%9 verified before activation.

Read applicable AGENTS hierarchy and coding OAP; compact strategic OAP and
architecture; selected inert188 proposal and BRANDING-EXECUTION-PLAN.md. Read
SLAIF-VISUAL-DESIGN-CONTRACT.md COMPLETELY: its palette, typography, navigation,
error-surface and browser criteria are requirements of this active order.
Read current branding contract, template/CSS/JS seams, related tests and affected
admin HTML response paths before editing. No full root architecture/archive.

Pinned reference snapshot (read-only):
/home/janezp/codex-supervision/slaif-api-gateway/review-artifacts/branding-reference-dad6e29d
Source ulfe-lmi/slaif-asset-reservation at
 dad6e29d4f8e4fd941843b230474d35dafb69d1a.
Use docs/ux/visual-design.md and the CSS for visual reference. Exact font assets
and OFL notices are cached under src/slaif_reservation/web/static/web/fonts;
font-manifest.json verifies the published hashes. No font download is needed.
Existing Gateway packaged logo blob0d114503215fa4c0227b51b22dcc975c4476fc60 stays
unchanged, including the README header. Do not port Django or reservation logic.

## Exact permitted paths

Product presentation:
- app/slaif_gateway/web/templates/**/*.html (including small shared header,
  navigation/error partials as needed; preserve forms/actions/CSRF semantics)
- app/slaif_gateway/web/static/css/admin.css
- app/slaif_gateway/web/static/js/navigation.js (new, small menu behavior)
- app/slaif_gateway/web/static/fonts/Roboto.ttf, RobotoCondensed.ttf,
  roboto-OFL.txt, robotocondensed-OFL.txt (exact pinned files only)
- app/slaif_gateway/api/admin.py ONLY presentation wiring and replacing existing
  explicit bare HTML error responses with a shared error template/helper.
  Preserve statuses, safe messages, headers, authorization and mutation order.
  No domain/service/session/financial changes or JSON response changes.

Tests:
- tests/unit/test_admin_branding.py, test_admin_routes.py,
  test_admin_*_templates.py, test_admin_*_routes.py
- tests/unit/test_admin_slaif_design.py (new focused presentation tests)
- tests/unit/test_branding.py ONLY render expectations affected by the shell;
  do not weaken file/content/security/refresh controls
- tests/browser/test_admin_slaif_design.py (new main design evidence)
- tests/browser/test_admin_branding.py, test_admin_dashboard_smoke.py,
  test_admin_lazy_throttling.py (adjust legitimate presentation expectations or
  locators only; retain all auth/CSRF/policy/accounting/secret assertions)
- tests/fixtures/branding/custom/style.css (readable coordinated alternate theme;
  adjust affected expected styles in the permitted browser/unit files)

Docs:
- docs/visual-design.md (new palette/tokens/layout/font provenance guide)
- docs/branding.md (actual current surfaces, tokens, instructions)
- docs/README.md, README.md (navigation/status only; preserve top branding)
- docs/security-model.md only if HTML error presentation needs clarification
- docs/verification/slaif-visual-design.md (new honest evidence/parity matrix)
- docs/verification/README.md (single new entry)
- docs/verification/operator-branding.md (historical187 record: add crosslink/
  status context for188, do not rewrite historical evidence as new executions)

OAP: this order/oap/active and unique188-a report. Safe review screenshots may be
copied to strategic review-artifacts/188-a-review/screenshots (not committed).
Any additional product path needs a strategic scope decision BEFORE edit.
No main.py/config/router/branding-reader/PNG-validator/Compose/dependency/schema/
workflow/provider/accounting/auth-service change. Existing mechanisms are proven.

## Functional and visual requirements

R1 Apply the design contract: cream#fbfbf9, dark teal headings#16302e,
blue#086c86 actions, lime#a3cc32 highlights, pale-blue#c8e1e8 panels, coherent
text/surface/border colors and local Roboto/RobotoCondensed. Include original OFL
notices and exact source hashes. No external fonts/images/CSS/JS. Keep controls
legible and verify contrast in the tested default and alternate themes; do not
claim accessibility certification. Preserve CSS variable aliases when useful.

R2 Shared visible SLAIF identity and useful navigation on every existing admin
page, not just login/dashboard. Use base/header and existing per-request branding
helpers. Avoid duplicate decorative lockups. Respect wide/compact override
selection, default and per-slot fallback, favicon on all templates, login hero,
and CSS override loaded LAST. Keep product title SLAIF API Gateway. Do not
invent implemented capabilities or remove existing status limitations.

R3 Responsive desktop/tablet/mobile layout, keyboard menu with expanded state,
Escape/focus return, usable no-JS navigation, labeled focusable table scrolling,
no whole-page horizontal overflow at375px. Preserve semantic headings/tables,
labels, form IDs/names/actions, required/reason/confirmation fields and hidden
CSRF values. Existing lazy-throttling JS and no-JS controls remain functional.

R4 Existing explicit HTML admin errors receive the shared branding/presentation
where practical through one small helper/template. Inventory is in strategic
review-artifacts/188-a-design-surface-inventory.json (67 templates). Preserve
original status/safe message/headers; escape data. Preserve all existing JSON
and /v1 error contracts. No generic middleware/error framework, no new public
business dashboard, no offline catalog report redesign, no new authentication
or state writes. Review the diff to prove domain decisions are unchanged.

R5 Preserve every187 operator-branding contract: fixed slots and limits,
trusted read-only directory, no-follow/bounded reader, strict content validation,
per-request live refresh, no operator cache, no extra access rights, safe asset
fallbacks. New design must not bypass this mechanism or add user-upload/template/
script customization. The final parity matrix must account for all five slots,
all admin template surfaces, disabled/invalid/live-update behavior and both
Compose deployments; document existing non-HTML/API boundaries accurately.

## Focused verification and visual acceptance

V1 Focused unit tests for shared shell/fonts/navigation/HTML error status and
escaping, affected template/routes/branding assertions, documentation inventory,
unchanged OAP/main structure gates, Ruff on changed Python and git diff --check.
No test weakening or skip. Run the initial governance/header check early: exact
first line of this order must be '# OAP Work Order — 188-a'. No broad local suite.

V2 Native Chromium with owned synthetic PostgreSQL, existing qualified fixtures:
default + alternate branding at375/768/1440, actual computed palette and local
font loading (declared font faces loaded and local font HTTP bytes/hash), shared
branding on login/dashboard/key/provider-or-route pages, override CSS last and
wide/compact/fallback behavior. Keyboard navigation/menu/Escape/focus return and
no-JS behavior; contained table scrolling and no page overflow. Inspect labels,
contrast, focus, errors and long identifiers. Do not assert pixel-perfect goldens.

V3 Actual login and one key/policy form flow with existing reason/CSRF rules,
validation errors, unauthenticated access, bad-CSRF state unchanged, secret
redaction. Re-run affected187 branding and185 lazy browser cases rather than
inventing new domain fixtures. No real provider calls. Include branded explicit
HTML400/404 error examples and verify JSON /v1 responses stay unchanged.

V4 Capture representative safe screenshots: default desktop/mobile login,
dashboard, key form/detail and one alternate-theme/table/error view. Tests write
to portable temporary output paths; agent copies eligible review images to the
strategic screenshot directory and reports exact paths. NEVER capture even
synthetic plaintext gateway keys, passwords, session/CSRF values or provider
secrets; avoid one-time-key result screens. Root must view representative images
before accepting final design. This is a final visual product review, not only
a stylesheet diff. Fix actual layout/contrast/behavior findings within this PR.

V5 Unchanged filesystem validators and read-only-container mount need no repeat
matrix/build; their187 proof remains valid. Font packaging is covered by existing
static package-data/COPY patterns and actual local HTTP/font checks; no frontend
build platform or new dependency needed. Exact final SELF GitHub CI must pass.
After focused/browser/visual proof, publish an accurate report with any
intermediate CI pending; do NOT wait for an intermediate full matrix that the
report commit will rerun. Resolve actual in-scope failures when observed, and
never label pending/skipped checks passes. Strategy waits all final-head gates.

## Setup, privacy and boundaries

Reuse /tmp/slaif-181c-strategic-venv. Chromium command-scoped LD_LIBRARY_PATH:
/tmp/slaif-browser-runtime-8h8e0e6z/extract/usr/lib/x86_64-linux-gnu.
Use only newly owned labeled loopback/tmpfs synthetic PostgreSQL as needed;
existing187/185 fixture may be reused unchanged. No ambient URL fallback or
shared destructive setup. Exact created IDs + labels govern cleanup. Do not
start detached nohup jobs that disappear with the tool session: use foreground
tracked tool sessions and poll their returned handles. No system/daemon change.
No production data/credentials, real model/provider/email, release/tag/deploy,
new service/port/network or protected configuration access. Copy pinned public
font assets with notices; preserve logo and content/secret boundaries.

Docs must state actual implemented design, current slot surfaces/limits,
operator guidance and exact evidence, with real vs mocked distinctions and
honest limits. Existing financial/auth/API contracts remain unchanged. Preserve
historical187 reports and proof, and cite new executions separately.

## Publication and completion

Coding agent owns Git execution: branch from verified currentmain, preserve user
changes, commit/push strategic order and active bytes unchanged, create exactly
one188 PR, and update its final title/body for the completed implementation.
Never merge or enable auto-merge. Use body-file/REST for metadata when needed.
Publish unique immutable oap/reports/188-a-slaif-visual-design.md containing
literal Implementation head SHA: <fullSHA> and Report publication commit: SELF.
Its report-only SELF first parent equals that implementation head and only the
report path differs. Push/verify remote PRhead=SELF before signaling exactly
2bytesOK once onresponse.fifo; then attach the sole control waiter. Report
screenshots, commands/results/warnings/skips, exact docs impact and deviations.
Strategic model independently reviews product visuals/parity, report topology,
checks/reviews/scope and guarded-merges only after every final gate passes;
verify main/timings and full goal completion afterward. No189 activation.
