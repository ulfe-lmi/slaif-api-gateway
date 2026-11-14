# OAP Work Order — 224-j

Database-backed administrator reporting and review pages.

PR mode: AMEND_EXISTING_PR. Numeric objective 224, unique OPEN PR #383,
branch `oap/224-demo-web`, base remote main
`d3762e51c9a323dee6b728c4a45fa21b0bffae86`. The human
authorized a fresh per-login identity-masked PostgreSQL and copied,
sanitized file snapshot, the existing administrator GUI in read-only
demo mode, every operational action a quiet server-side no-op, and
exact disposable cleanup. 224-j admits the next bounded set of
database-backed reporting and administrator review GET pages. It is
NOT full GUI coverage; later same-PR suffixes cover replay/diagnostics,
compatibility, file-backed catalog/settings, remaining downloads and
final UI audit. Objective 225 is the installed acceptance gate. No
second PR, merge, auto-merge, release, deployment, real company
snapshot, upstream provider call or mail.

## Current GitHub/OAP truth and dependencies

224-i exact response: detached root watcher
`slaif-oap-224i-response` CLOSED; durable
`/tmp/slaif-oap-224i-response.log` contains
`CONTROL_OK_DELIVERED` then `RESPONSE_OK_EXACT`. Never resignal or
repoll it. `oap/active` is exact `224-i` before this activation.
Immutable 224-i order SHA256 is
`ff823500871c94b68f3d8b8c679ab0efdda9e680e17841030a7812dad9205fcc`;
immutable report SHA256 is
`aa3a0cf2379826874e41190d2a930962433300bc1f3a50edd78c04e2ff14057d`.
Remote PR383 head is report-only SELF
`cc7b02889162aac34c86c64f3f8c692ed913ab26`, sole parent
implementation `8f677b9948640c0334fe65828b84304ed46fcb11`, sole
SELF diff `oap/reports/224-i-core-forms-and-routes-read-pages.md`.
Remote main remains `d3762e51`; PR OPEN/MERGEABLE; open PRs
#379/#319 unrelated. Root resolved the three old true unused-global
CodeQL threads after verifying 224-i removed those declarations;
zero unresolved threads at last query. 224-i local evidence: 106
demo-web units, 9 strict OAP governance, 59 worker units, 126
usability and 16 docs tests, owned PostgreSQL16 two-copy e2e plus
real Chromium smoke, scoped Ruff/diff clean. Its exact-head hosted
checks at preparation: nine SUCCESS (including Unit/lint, browser,
E2E, CodeQL, Compose, docs), PostgreSQL IN PROGRESS. Recheck
actual terminal outcomes; pending is not a pass. No merge while
objective 224 is incomplete.

The historical 224-h-head unit job failed solely because the
immutable root-authored 224-h order used a titled first line. The
unchanged strict governance suite passes under active 224-i (local
9/9 and exact-head hosted Unit/lint SUCCESS). Never edit earlier
orders/reports or relax that test. 224-i's report accurately records
an implementation-preparation `git add -A` that temporarily staged
three protected untracked files, immediately unstaged before commit;
the remote implementation/SELF exclude them and hashes are unchanged.
Use ONLY explicit path staging in this suffix, without exception.

Protected untracked `CODEX-SESSIONS.md`, `codex.sh`, `uv.lock` retain
respectively SHA256
`5ae1d77c17a367e86ef725a8f9d25aba3464b24f22fba77fd2808377f8c7feda`,
`66eda80258f6a4f13b88a9fe2ad5a69b9e7df226a4e503f57b35b6c6f03e1247`,
`d3d0e80db77da56e41795c619875ac14b5d25427d5169a7c9d2c8dee45b3b5b6`.
Hash only; never read, stage, modify, clean or stash. Root owns this
order and the `oap/active=224-j` bytes under the shared checkout
BEFORE exactly one control `OK`; existing right-pane coding agent
owns Git and never merges. No helper agent or model/profile change.

## Bounded read-only GUI scope

1. Audit actual GET/HEAD dependencies first, then admit ONLY these
   existing fixed paths through the central demo gate, after proving
   each handler reads the session's verified disposable copy via
   `get_sessionmaker_from_app`, fixed packaged data and safe demo
   display settings, with no source/owner DB, Redis, provider,
   operator-file, live credential or mutation read:

   * reporting: `/admin/reports/`, `/admin/reports/live-burn`,
     `/admin/reports/export`, `/admin/reports/pricing-disable`,
     `/admin/reports/fx-lookup`;
   * accounting candidate/review entry: `/admin/accounting-operations/`,
     `/admin/accounting-operations/expired-reservations`,
     `/admin/accounting-operations/external-tool-fences`,
     `/admin/accounting-operations/external-tool-holds`,
     `/admin/accounting-operations/provider-completed-recovery`;
   * administrator accounts: `/admin/accounts`,
     `/admin/accounts/create`, `/admin/accounts/reset` (the latter
     accepts only the existing validated `admin_id` query semantics);
   * key batch entry: `/admin/key-batch`.

   These are exact positive paths, not prefix passthrough. All
   unknown, malformed, extra-suffix, POST review/result, export
   attachment, and file-backed GETs remain denied. If any listed GET
   needs a live/non-copy dependency or writes on GET, do NOT admit it
   or substitute the source: report the exact path and implement a
   narrow copy-only view on this PR if feasible; tell root before
   publication if that path cannot meet the boundary.
2. The fake administrator should see the copied administrator-account
   list and its create/reset forms like a real superadmin. If the
   existing fictional demo identity's `viewer` display role blocks
   these already-gated GET handlers, give only the isolated demo
   context a display `superadmin` role (or an equally narrow
   demo-only read admission); it must never alter real admin roles,
   source accounts, auth decisions outside this demo process, or
   the central 204 no-op boundary. The copied `admin_users` records
   remain 222-anonymized. No password hash, MFA secret, real email,
   session token or one-time secret appears in HTML.
3. Reports and accounting candidate lists operate on FROZEN copied
   rows. Where existing handlers evaluate a time-sensitive window,
   expiration or effective FX rate at REQUEST TIME, keep that fact
   explicit in a concise demo-only page hint (snapshot rows with a
   current-time calculation); do not call it a live production
   metric or silently imply the derived value was frozen at login.
   Keep original normal-admin behavior and labels unchanged.
   Preserve existing pagination, row numbers, sortable request/token
   columns, grouped amounts and numeric formatting. Do not create
   new aggregate accounting authority or invoice claims.
4. Restore only links to the now-admitted read pages (for example,
   reports from the dashboard/usage area, account list/create from
   the administrator area, and Change existing keys from Keys).
   Keep still-gated replay, diagnostic, catalog, compatibility,
   branding, clone/receipts, process-configuration, OpenAI-assisted,
   provider discovery POST, reviewed action GET and download links
   honest/hidden. The operational buttons on admitted forms remain
   visible where they belong; EVERY unsafe method, including report
   export, account create/reset, batch plan and accounting review,
   stays the SAME silent 204 no-op BEFORE body parsing/handler
   dispatch. Demo sign-out is the sole explicit exception.
   Existing session/copy/auth checks, `private, no-store` on all
   dynamic `/admin` responses, no content storage and exact copy
   cleanup remain unchanged.

## Verification, scope and publication

Expected product paths: narrow changes to
`app/slaif_gateway/api/demo_admin_gate.py`, demo-only presentation
in `app/slaif_gateway/api/admin.py`/the listed read routers ONLY if
needed for the role or time hint, and directly affected existing
templates/nav links. Matching focused gate/unit and owned
PostgreSQL16/browser tests; `docs/demo-admin.md` for this stage and
remaining 404 families. No source/ordinary DB schema migration,
worker/sanitizer/custody change, provider adapter, public endpoint,
Compose/Nginx or operator file mount. Explain any unavoidable path
expansion in the report. Do not add generic permissions, passthrough
or a new GUI framework.

Prove the exact allowlist and near-miss 404s; no-op unsafe methods
never parse a body or dispatch; two independent sessions see only
their own verified copy; report row counts/amounts match copied
PostgreSQL data within existing bounds; copied account identities
appear while source emails and all credential canaries do not; an
expired/disabled/wrong-account/missing copy refuses; no source/copy
DML, audit, quota, mail, provider or network effect. Exercise one
report and one accounting page plus account/batch navigation in
real Chromium at desktop width, inspect layout, and verify no-store.
Use focused checks and reuse unchanged prior evidence. Distinguish
mocked unit coverage from owned real PG/browser. If the pending
224-i exact-head CI later reveals a direct defect, correct it in
this same order/PR before reporting; never call pending green.

Commit the unchanged strategic-authored order and active pointer,
then the implementation on the SAME PR, then ONE immutable 224-j
report in a report-only SELF commit (sole parent implementation).
Report exact order hash, parent/tree/head, diff scope, test results,
negative security/privacy/accounting evidence, docs, limitations,
CI/reviews and any staging correction. Push and verify remote
PR/head/main. Coding agent NEVER merges or enables auto-merge.
Signal exactly two bytes `OK` once on the verified response FIFO
and rearm one canonical control waiter. Root reviews exact report,
CI, review gates and material correctness, then continues objective
224 on this same PR; no merge in 224-j.
