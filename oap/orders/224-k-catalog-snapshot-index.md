# OAP Work Order — 224-k

Read-only catalog snapshot index from the verified file display copy.

PR mode: AMEND_EXISTING_PR. Numeric objective 224, unique OPEN PR #383,
branch `oap/224-demo-web`, base remote main
`d3762e51c9a323dee6b728c4a45fa21b0bffae86`. The human authorized
a new per-login identity-masked PostgreSQL plus copied/sanitized file
snapshot, the existing admin GUI in read-only demo mode, all operational
actions quiet server-side no-ops, and exact disposable cleanup. 224-k makes
the captured catalog's safe FILE INDEX visible inside that GUI. It is not
full catalog browsing: body previews, run detail, uploads/proposals,
attachments, downloads, live apply status and process settings remain
closed for later same-PR suffixes. Objective 225 is the installed acceptance
gate. No second PR, merge, auto-merge, release, deployment, real company
snapshot, upstream provider call, mail, or source custody operation.

## Verified OAP/GitHub state and dependencies

224-j's detached root response watcher is CLOSED; durable
`/tmp/slaif-oap-224j-response.log` contains `CONTROL_OK_DELIVERED` then
`RESPONSE_OK_EXACT`. Never repoll or resignal 224-j. The 224-j order is
unchanged SHA256
`cc5b0f36f4424c29b2b10633290018d917c61d4984559ee59cc6bdc1a15b6e4a`;
its immutable report is unchanged SHA256
`01952d43e24474bf18f32476b77f8b3ab1b0f40d170d9a524275a5ac9134edd2`.
Remote PR383's head is the report-only SELF
`38a8466daf0ae332bf9023eadde76235c1bc3492`, sole parent
implementation `5127c0cfcfdd44a40fc3d69ad1bf321d86965a73`, SELF tree
`f5056021651c3ca8eb221f76bd022556b81373b5`, sole SELF diff
`oap/reports/224-j-db-backed-admin-reporting.md`. Active is exact `224-j`
before this activation. PR OPEN/MERGEABLE, main `d3762e51`; unrelated open
PRs #379 and #319. The only release is `v0.1.0-rc.1`. Main has no branch
protection API policy, but strategic final-head CI/review/material gates
still apply. All 224-i exact-head hosted checks were green. The 224-j
SELF-head hosted checks at preparation: Unit/lint, three analyses, E2E,
Compose, documentation and CodeQL SUCCESS; PostgreSQL and browser smoke
IN PROGRESS. Recheck outcomes; pending is not a pass. Zero unresolved
review threads: root resolved three new CodeQL false positives after
verifying they mark non-executable Protocol ellipsis declarations in
`demo_web.py`, not ineffective runtime statements. No merge while 224
remains incomplete.

The existing 224-g worker already publishes verified, sanitized file
leaves into the exact disposable copy's target-only `demo_display.leaves`
under a SELECT-only reader role. `DisplayReader.read_index()` reads the
closed safe metadata (logical name, kind, byte count, capture time) in
one verified database-side read-only transaction with current_database
binding, finite row cap, no custody path or body bytes. The normal
`admin_catalog_refresh` GETs call live operator custody, HMAC seal and
process settings. They MUST NOT be admitted unchanged in demo mode.

Protected untracked `CODEX-SESSIONS.md`, `codex.sh`, `uv.lock` remain
SHA256 respectively
`5ae1d77c17a367e86ef725a8f9d25aba3464b24f22fba77fd2808377f8c7feda`,
`66eda80258f6a4f13b88a9fe2ad5a69b9e7df226a4e503f57b35b6c6f03e1247`,
`d3d0e80db77da56e41795c619875ac14b5d25427d5169a7c9d2c8dee45b3b5b6`.
Hash only; never read, stage, modify, clean or stash. Root owns this order
and `oap/active=224-k` bytes under the shared checkout BEFORE one control
`OK`; the existing right-pane coding agent owns Git/report and never merges.
No helper agents or model/profile changes.

## Bounded product change

1. Add ONE demo-only read handler for exact
   `GET /admin/operations/catalog/`, mounted ahead of the normal catalog
   router only in `create_demo_app`. Add only that exact path to the
   central demo gate. No prefix allowlist; all deeper catalog GETs,
   downloads, original apply-status, preview/verify endpoints and
   unknown variants remain 404. Every unsafe `/admin` method remains
   the unchanged quiet 204 cut before body parsing and dispatch.
2. Build the page ONLY from the gate-validated request-local demo state
   and its exact session target via the already-existing
   `demo_display_reader_factory(...).read_index()` seam. The reader's
   read-only/current_database checks remain authoritative. Do not
   call `_setup_context`, `inspect_custody_setup`, original catalog
   handlers, live Settings catalog fields, source DB, Redis, HMAC
   seal, worker filesystem, provider network, or server-owned
   credentials. Do not add a schema, new file mount, generic body
   reader, download endpoint, background job or worker change in this
   round.
3. Render a coherent read-only catalog snapshot index with all
   catalog-kind metadata already in the verified finite index: saved
   run IDs, job IDs and other captured catalog artifacts may be
   grouped or displayed in a sortable, numbered table, with exact
   remapped logical names, kind, byte count and capture time. Escape
   every display value; no source path, original run/job ID, seal/HMAC
   or secret may appear. The page must not claim that a sanitized
   display copy is an authenticated original seal or apply bundle.
   Keep the 223 per-leaf capture times distinct from the database
   snapshot time; say file capture was a separate bounded phase.
   If no catalog leaves are present, say only that this copy has no
   captured catalog artifacts; do not infer whether operator storage
   was configured. If the display index is missing/corrupt/unreadable
   or a capture time is unrepresentable, return a fixed safe
   unavailable note and no raw DB/path/traceback. No silent prefix or
   completeness claim beyond the existing reader's bound.
4. Make the page reachable from a demo-only dashboard catalog card or
   another unobtrusive, already-admitted page link. Preserve normal
   admin dashboard/nav and current demo layout; do not add a fifteenth
   top-nav item without real desktop/mobile visual inspection.
   Any table must have first-column row ordinals and sortable headers
   using the current link-based table-sorting appearance. Operational
   controls may be shown only when their targets are admitted or
   intentionally use the existing quiet 204 no-op; no 404 links on
   this new page.

## Verification and publication

Expected product paths: a small demo-only catalog router/template,
`app/slaif_gateway/demo_web.py` mount order, exact gate addition in
`app/slaif_gateway/api/demo_admin_gate.py`, direct dashboard link,
focused unit and existing owned PostgreSQL/browser gate tests, and a
single 224-k section in `docs/demo-admin.md`. No ordinary catalog
router change, normal templates except a demo-only conditional link,
source/ordinary database schema, worker/sanitizer/custody, provider
adapter, Compose/Nginx or public API change. Explain any unavoidable
path expansion before publication.

Prove exact positive GET and near-miss 404, auth/zero-account/expired/
wrong-copy refusals, `private, no-store`, empty-vs-unavailable states,
escaping, bounded read and capture-time display, normal admin
unchanged, and 204 no-op for catalog unsafe methods. Use focused
mocked unit coverage for positive catalog metadata grouping plus an
owned PostgreSQL16 test for the real target-only reader and session
binding. If the available owned fixture has no configured catalog,
state that limitation honestly; do not claim a real catalog artifact
was displayed. Reuse prior 223 worker sanitization evidence and
reserve a complete configured-file installed workflow for 225. Exercise
the dashboard link and new page in real Chromium at desktop width,
inspect the layout; no unneeded broad local matrix. Verify no source
or copy DML/audit/quota/mail/provider/network/file effect and no
secret canaries in HTML/logs. Recheck any direct 224-j hosted CI defect
within this same order/PR, never call pending green.

Commit the unchanged strategic-authored order and active pointer first,
then implementation on SAME PR, then ONE immutable 224-k report in a
report-only SELF commit (sole parent implementation). Report exact order
hash, parent/tree/head, diff scope, true mocked-vs-owned PG/browser
results, negative security/privacy/accounting evidence, docs,
limitations, CI/reviews and protected file hashes. Push/verify remote
PR/head/main. Coding agent NEVER merges/auto-merges. Signal exactly
two bytes `OK` once on the verified response FIFO and rearm one
canonical control waiter. Root reviews and continues numeric objective
224 on this PR; no merge in 224-k.
