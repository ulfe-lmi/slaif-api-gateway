# OAP Work Order — 224-i

Core form and route read pages.

PR mode: AMEND_EXISTING_PR. Objective 224, unique OPEN PR #383,
`oap/224-demo-web`, base remote main
`d3762e51c9a323dee6b728c4a45fa21b0bffae86`. The human
authorized a fresh per-login identity-masked PostgreSQL and copied,
sanitized file snapshot, the existing administrator GUI in a read-only
demo, every operational action a quiet server-side no-op, and exact
disposable cleanup. Objective 224 remains incomplete; this suffix
admits the next CLOSED set of database-backed core forms and route
read pages. Later same-PR suffixes cover operations, reports,
file-backed panels/downloads, settings and the rest of the GUI.
Objective 225 is the installed acceptance gate. No second PR,
merge, auto-merge, release, deployment, production/company snapshot,
provider call or mail.

## Current verified GitHub/OAP state and reason

The root's detached 224-h watcher closed: durable
`/tmp/slaif-oap-224h-response.log` contains
`CONTROL_OK_DELIVERED` then `RESPONSE_OK_EXACT`. Do not resignal or
repoll it. `oap/active` is exact `224-h`; the immutable 224-h order
SHA256 is
`23b443019a0d859537238a002b4f593f284dc96386f3b7cb261c4d36ef7536a4`,
and its immutable report SHA256 is
`9fd5b20f197a8379a2818f985953126d5ba8cf54cd525c665459ae1b16d8088e`.
Remote PR383 head is report-only SELF
`1dd60875dc83a3a8aa0040ce14b76dbe6d22504d`, sole parent
implementation `5ff0fb60f3bc6a3b7297a7e2afcd5cea2415f3c1`,
sole SELF diff `oap/reports/224-h-display-boundary-repair.md`.
Remote main remains `d3762e51`; PR OPEN/MERGEABLE. Other open PRs
#379/#319 are unrelated and must not be touched. The 224-h exact-head
CI has ten checks: one FAILURE (Unit/lint/migration), eight SUCCESS
and one IN_PROGRESS (PostgreSQL) at final preparation;
inspect terminal outcomes, never treat pending as a pass. The unit
failure is solely
`tests/unit/test_oap_governance.py::test_active_identifier_resolves_exactly_one_matching_order`:
the immutable root-authored 224-h first line is
`# OAP Work Order — 224-h: close verified display-publication gaps`,
while this test requires the identifier alone. The test reads ONLY
the CURRENT active order, and this 224-i order uses the exact
identifier-only first line. Preserve the immutable 224-h order and
report AND the strict governance test unchanged. Run that focused
test against `oap/active=224-i` to prove final-head CI has recovered;
record the historical 224-h-head failure honestly. No OAP protocol,
test-policy or runtime permission relaxation. 224-h local evidence:
59 worker units, 104 web
units, admin-table inventory and docs checks, owned PostgreSQL16
worker14, scoped Ruff/diff green; no source/normal-DB schema change.

Three unresolved `github-code-quality` review threads on PR383 are
true, narrow findings from 224-g: unused globals
`_DEMO_RUN_ID_RE`, `_DEMO_JOB_ID_RE`, `_DEMO_UPLOAD_BASENAME` in
`services/demo_web_worker.py`. Remove ONLY those unused declarations
in this suffix; root will resolve the threads after confirming the
final diff. The 224-h immutable report miscounts the preceding
224-g CI workflow as six successes of seven jobs; its actual CI
workflow had five successes of six jobs and the one inventory
failure, while separate CodeQL workflows succeeded. Correct that
statement in THIS round's report, never edit earlier reports.

Protected untracked `CODEX-SESSIONS.md`, `codex.sh`, `uv.lock` retain
respectively SHA256
`5ae1d77c17a367e86ef725a8f9d25aba3464b24f22fba77fd2808377f8c7feda`,
`66eda80258f6a4f13b88a9fe2ad5a69b9e7df226a4e503f57b35b6c6f03e1247`,
`d3d0e80db77da56e41795c619875ac14b5d25427d5169a7c9d2c8dee45b3b5b6`.
Hash only; never read, stage, modify, clean or stash. Root writes this
order and `oap/active=224-i` to the shared checkout before exactly
one control `OK`. Existing right-pane coding agent owns Git; no
helper agent or model/profile change.

## Bounded product change

1. Keep the existing standalone default-off demo process, verified
   session/copy gate and SELECT-only request-local reader. Admit ONLY
   these existing GET/HEAD paths through the closed demo gate, after
   auditing each handler for its actual data source and ensuring it
   needs only the verified copy, fixed packaged data and safe demo
   display settings:

   * fixed form paths: `/admin/keys/create`,
     `/admin/keys/bulk-import`, `/admin/owners/new`,
     `/admin/institutions/new`, `/admin/cohorts/new`,
     `/admin/providers/new`, `/admin/routes/new`,
     `/admin/routes/import`, `/admin/pricing/new`,
     `/admin/pricing/import`, `/admin/fx/new`,
     `/admin/fx/import`;
   * exact canonical-lowercase-UUID edit forms:
     `/admin/{owners,institutions,cohorts,providers,routes,pricing,fx}/{uuid}/edit`;
   * `/admin/providers/{uuid}/discover` GET as a read-only FORM only
     (its POST preview remains an upstream-network-free 204 no-op);
   * `/admin/routes` list and `/admin/routes/{uuid}` detail.

   These are positive shapes, not a prefix or arbitrary suffix
   passthrough. Canonical UUID, method and exact segment-count rules
   remain. Unknown, extra, malformed or action GETs stay 404. If
   audit finds an existing handler would read ambient operator files,
   provider credentials, live source/owner DB, call a provider, or
   mutate state on GET, do not admit it; report the exact blocking
   path and provide a narrow copy-backed alternative in this PR if
   feasible. In particular, route detail must not construct a
   Codex profile with a live deployment base URL or credential;
   use only a safe demo URL/neutral presentation or omit that
   artifact link with a clear read-only hint until the later
   download stage. Do not create a new networking or file service.
2. Reuse the existing administrator router/templates and their
   field-choice hints. Forms and links should be usable as a demo
   of the real interface, with the persistent identity-masked,
   read-only banner and a concise local hint where clicking Submit
   or Import would otherwise be confusing. Operational buttons and
   POST/PUT/PATCH/DELETE/OPTIONS/... still produce the SAME quiet
   no-change 204 BEFORE handler routing and body parsing (demo
   sign-out remains the sole explicit exception). Do not silently
   disable or remove the core actions merely to make the preview
   look complete; their server-side no-op is the safety boundary.
   Preserve normal administrator GUI behavior and styles. Add
   `Routes` to the demo navigation only when its list/detail are
   actually admitted. Check layout and readable controls at a
   normal desktop viewport; keep the established SLAIF styling.
3. Every admitted page/JSON response must be bound to the exact
   session's verified, unexpired disposable copy, use the existing
   `private, no-store` demo response guard, and render only
   222-sanitized values plus fixed safe package data. No source
   session, real admin credential, provider secret/env value,
   private file manifest, raw path/URL or key material may appear.
   The route list/detail should show the copied routes and retain
   separate request/token quantities, sorting and row numbers.
   Keep provider credential isolation, PostgreSQL accounting truth,
   quota/replay ownership and the distinct local/hosted tool gates.
4. Remove the three genuinely unused 224-g constants named above;
   do not weaken the closed logical-name law or change the 224-h
   ingest/cleanup behavior. Do not expand the file display reader,
   add raw body downloads, or admit the still-gated operations,
   accounts, clone/batch, reports, catalog, compatibility, branding
   or process-configuration pages in this suffix.

## Verification, docs and publication

Expected product paths: narrow changes to
`app/slaif_gateway/api/demo_admin_gate.py`,
`app/slaif_gateway/api/admin.py` (demo nav and any route-detail
demo-safe presentation), and only directly affected core templates
for clear no-op hints if needed; three unused declarations in
`services/demo_web_worker.py`. Matching gate/unit and owned
PostgreSQL16 integration/browser tests; the unchanged
`tests/unit/test_oap_governance.py` against active 224-i;
`docs/demo-admin.md` for
coverage and remaining 404 families. Do not touch source/ordinary
DB migrations, worker custody/schema, provider adapters, public
gateway endpoints, Compose/Nginx or production file mounts. Any
unavoidable path expansion must be justified in the report.

Prove a representative NEW form in each core family and route
list/detail renders copied, identity-masked values under the real
reader role; two concurrent sessions remain distinct; an expired,
disabled, wrong-account or missing copy refuses; malformed and
extra path segments deny; unsafe methods never dispatch or parse a
body, and no source DML/audit/quota/mail/provider/network effect
occurs. Include credential/identity canary checks on HTML and
no-store headers. A focused real Chromium pass should follow a
visible new nav link, open at least one form and route detail,
click an operational submit and confirm no change, and inspect the
desktop layout. Run focused unit and owned PG/browser checks plus
scoped lint; reuse prior unchanged 224-g/h evidence. If the remaining
224-h exact-head CI later fails for a direct defect, correct it on
this same PR/order before reporting; do not invent a pass or loop blind
retries. Document exactly which of these checks are synthetic,
mocked or real PostgreSQL/browser. The stage remains incomplete
until later file-backed and operations rounds.

Commit the unchanged strategic-authored order and active pointer,
then implementation on the SAME PR, then publish ONE immutable
224-i report in a report-only SELF commit (sole parent the
implementation commit). Report exact order hash, parent/tree/head,
diff scope, test commands/results, negative security/privacy and
accounting evidence, CI/reviews, docs and limitations. Push and
verify exact remote PR/head/main. Coding agent NEVER merges or
enables auto-merge. Signal exactly two bytes `OK` once on the
verified response FIFO and rearm one canonical control waiter.
Root reviews report, exact PR/CI/reviews and the three former
CodeQL threads, then continues same objective 224; no merge in
224-i.
