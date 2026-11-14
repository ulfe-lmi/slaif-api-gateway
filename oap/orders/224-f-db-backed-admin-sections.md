# OAP Work Order — 224-f

PR mode: AMEND_EXISTING_PR. Objective 224, unique OPEN PR #383,
`oap/224-demo-web`, base remote main
`d3762e51c9a323dee6b728c4a45fa21b0bffae86`. No second PR,
merge, auto-merge, release, deployment, production/company snapshot,
provider call or mail. The human authorized a live fake-admin demo
of a fresh per-login identity-masked PostgreSQL AND copied/sanitized
file-backed snapshot: the existing admin GUI remains readable, all
operational actions are silent no-ops, and each exact copy is cleaned
up. This suffix expands the 224-e request-local read gate to the
remaining straightforward DATABASE-BACKED list/detail sections and
closes a demonstrated browser-cache privacy gap. It does NOT open
unreviewed file-backed/process/transport panels or claim the full
company demo usable. Continue the SAME PR through later suffixes
for the remaining forms, file-backed displays and installed
acceptance, then root performs final review/merge.

## Live OAP/GitHub truth and recovery qualification

224-e remote PR383 head is immutable report-only SELF
`c1494f28a3c86f6a368ba97446114f79405d41bd`, sole parent
implementation `f4b55b8b17434036bfa58d224e22f350fc1ff5e5`, sole
diff `oap/reports/224-e-demo-admin-core-read-gate.md` SHA256
`f81998a3ee11f108a4c4e228c6748835c3046ef998ea774eb9484f9a30b88a54`.
Its immutable order SHA256 is
`63b80bf59d663ad32f569913e987313ccca0ef7565e3230eb7523291d4736085`;
`oap/active` is exact `224-e` before this activation. Remote main
remains `d3762e51`; PR383 is OPEN, mergeable and incomplete. Other
open PRs #379/#319 are unrelated. 224-e local evidence: 91 focused
demo-web units, 102 normal-admin regressions, owned PostgreSQL16
two-copy/admin-page/no-op test, real Chromium packaged-assets/
sorting/logout smoke, scoped Ruff/docs/diff clean. The 224-e exact
hosted CI Unit/E2E/Compose/docs/CodeQL checks are SUCCESS while
PostgreSQL and browser jobs remain IN PROGRESS at order preparation;
inspect their actual terminal results and address any demonstrated
direct defect on this SAME PR. Root resolved two new e-head Code
Quality false positives on canonical `DemoWebFacade(Protocol)`
ellipsis methods; recheck the next head.

FIFO qualification (DO NOT fabricate an exact receipt): the coding
agent's `printf 'OK' > response.fifo` returned after 224-e push,
but root's long-lived FIFO terminal 53615 expired exit143 before
printing `RESPONSE_OK_EXACT`. Root independently reconciled the
unique immutable report, exact branch/head/parent/sole diff/hash,
active pointer, protected hashes and GitHub, recorded the lost
terminal in the timing ledger, and did NOT request/send a duplicate
response. The agent rearmed exactly one canonical control waiter:
PID505957 PPID1 with dd PID505958 blocked on the verified
`control.fifo` inode4501469. Never repoll terminal53615 or resignal
224-e. The 224-e immutable report slightly overstates one unit
test as covering the entire mounted route table; the actual test
samples representative unsafe paths (ten cases). The uniform
`DemoAdminGate.__call__` branch structurally cuts ALL authenticated
unsafe `/admin` methods before inner-app dispatch. Preserve the
immutable report and use precise evidence wording hereafter;
do not add an exhaustive test merely to make an old claim true.

Protected untracked `CODEX-SESSIONS.md`, `codex.sh`, `uv.lock`
retain respectively SHA256
`5ae1d77c17a367e86ef725a8f9d25aba3464b24f22fba77fd2808377f8c7feda`,
`66eda80258f6a4f13b88a9fe2ad5a69b9e7df226a4e503f57b35b6c6f03e1247`,
`d3d0e80db77da56e41795c619875ac14b5d25427d5169a7c9d2c8dee45b3b5b6`.
Hash only; never read, stage, modify, clean or stash. Root writes
this order and exact `oap/active=224-f` under the shared checkout
BEFORE one control `OK`. The existing right-pane coding agent owns
Git; no helper agent or model/profile change.

## Verified scope inventory and first fix

224-e admits dashboard, Keys/Owners/Institutions/Cohorts lists and
UUID details, and record-choice GET. The normal `api/admin.py` has
53 GET/56 POST routes; the whole ordinary admin surface spans 94
GET/96 POST routes. For this suffix, a strategic source inspection
found these additional database-backed GET list/detail families in
`api/admin.py` (all use current copied-public repositories and the
shared page/session helper; no external provider call is required):
`/admin/providers`, `/admin/providers/{uuid}`;
`/admin/pricing`, `/admin/pricing/{uuid}`;
`/admin/templates`, `/admin/templates/{uuid}`;
`/admin/fx`, `/admin/fx/{uuid}`;
`/admin/usage`, `/admin/usage/{uuid}`;
`/admin/audit`, `/admin/audit/{uuid}`;
`/admin/email-deliveries`, `/admin/email-deliveries/{uuid}`.
Inspect each exact handler for an unexpected file/process/network
read before admission; a concrete exception should be reported to
root and kept gated until the correct copied-display adapter exists.
Routes, operations, catalog, compatibility, OpenAI-assisted,
accounting-recovery, replay maintenance, admin accounts, key
batch/clone, all unreviewed form GETs, exports/downloads and
`/admin/branding` remain 404 this suffix. Their POSTs remain
the existing authenticated pre-handler 204 no-op; sign-out remains
the sole CSRF-checked mutation exception.

Material privacy gap in 224-e: successful admitted admin HTML and
record-choice JSON responses pass through without `Cache-Control:
no-store`; only refusals carry it. A browser can retain the
identity-masked usage-pattern snapshot after sign-out. First add
a central, demo-only ASGI response-start header guard for ALL
admitted dynamic `/admin` GET/HEAD responses (including JSON and
errors): `Cache-Control: private, no-store` (and other no-cache
headers only if needed), without duplicating/conflicting headers.
Keep packaged `/admin/static` revisioned assets cacheable and
ordinary app headers unchanged. Do not claim absolute erasure from
browser history; test reload/back behavior honestly.

## 224-f requirements

1. After reviewing the exact handlers above, extend only the
   closed GET admission law with these seven list and seven
   canonical-lowercase-UUID detail routes. Reuse the 224-e live
   session/account/generation/request fence, exact target-copy
   name, request-local SELECT-only/read-only sessionmaker and
   disposal. Never add a generic `/admin/{path}` passthrough or
   loosen the UUID grammar. A file/process/network-dependent GET
   remains gated until a copied source is wired in a later suffix.
2. Expand the demo nav to the admitted sections, preserving the
   existing SLAIF branding style and responsive behavior. Existing
   normal nav and rendering remain unchanged. In DEMO mode only,
   hide links from those list/detail pages to still-gated form,
   edit, export, network discovery or file-backed routes with a
   concise read-only hint where needed; avoid orphan separators,
   empty action panels and live-authority wording on copied rows.
   Visible operational POST buttons remain quiet no-ops. Keep the
   persistent demo banner, table sorting, structural row ordinals,
   filters, pagination, dropdown search and proper number formats.
   The screenshot of 224-e synthetic `/admin/keys` was visually
   coherent; one pre-existing grammar defect appears across its
   four core lists: `1 rows shown`. As a small in-scope GUI polish,
   use singular/plural correctly on all now-admitted list pages,
   with no data or accounting change.
3. These pages must read ONLY the verified copied `public` data
   and show the 222 fictionalized identities and neutralized
   secrets. Preserve real usage quantities, timestamps, model/
   route/pricing choices and relationships per the human's privacy
   decision. A copied provider credential, key hash, email subject,
   audit free text, or arbitrary JSON must never be revived or
   replaced with live data. Use neutral fixed display defaults,
   not ambient production settings. No source business DB,
   provider HTTP, mail, file custody or Redis read from the demo
   web process. Keep the ordinary gateway's auth, route, quota,
   accounting and provider behavior unchanged.

## Scope, verification, publication

Expected product paths: narrow changes to `api/demo_admin_gate.py`
for no-store and closed GET admission, `api/admin.py` only for the
demo nav context if needed; DEMO-only branches in the seven
selected list/detail templates and `web/templates/base.html` if
needed. One small shared list-count pluralization helper or
template conditional is fine; do not redesign tables. Matching
unit, owned-PG16 integration and browser/HTML tests;
`docs/demo-admin.md` and `docs/configuration.md` for the exact
new coverage and still-gated families. Do NOT change `main.py`,
`demo_web.py` core control/copy role, `db/session.py`, normal
admin auth/session, migration 0028, 221/222/223 masking/worker,
provider adapters, quota/accounting, Compose/Nginx or production
routes without a demonstrated direct defect. Tell root before an
unavoidable path expansion; routine direct fixture/doc corrections
stay in this same order/PR.

Verification: focused unit tests for each newly admitted path and
near-miss (extra suffix, malformed/noncanonical UUID, action GET),
zero-account and revoked-session refusal, and no-store on success,
JSON, failure and no-op where appropriate while packaged static
retains its existing cache policy. Run one owned synthetic PG16
workflow with real reader role and two distinct copies: every new
list/detail renders safely from its own copy, copied fictional
identity/secret canaries remain absent, usage quantities and
counts are preserved, source and both copies have no unintended
row/count/audit/quota changes from reads/no-ops; direct unsafe
methods still 204 before handler/body parse. Reuse 224-e component
evidence; do not rerun unchanged 221/222/223 matrices. Include a
real Chromium smoke of one new section's nav, sorting and no-store
response; confirm logout then reload of a dynamic page cannot
serve a cached snapshot without reauthorization. Do not overclaim
what a browser's history/back-forward cache guarantees. Run
scoped Ruff/docs/diff and focused normal-admin regression for
templates/headers; hosted CI is root's later final-head gate.
Report exact synthetic vs mocked vs browser evidence and skips,
and explicitly list the remaining form/file/process/network
panels for 224-g/h. No live company data or external provider/mail.

Commit root-authored order/active unchanged on the existing PR
branch, push implementation, then publish ONE immutable
`oap/reports/224-f-db-backed-admin-sections.md` report-only SELF
(sole parent implementation, sole diff report). Verify remote PR383
head/branch/base, order/active/report, protected hashes; send one
exact response FIFO `OK` and rearm one canonical control waiter.
Coding agent never merges; root independently reviews and continues
same PR. Objective 225 stays inert and no demo deployment/release
is authorized.
