# OAP Work Order — 224-l

Verified catalog display-copy artifact downloads from the demo GUI.

PR mode: AMEND_EXISTING_PR. Numeric objective 224, unique OPEN PR #383,
branch `oap/224-demo-web`, base remote main
`d3762e51c9a323dee6b728c4a45fa21b0bffae86`. The human authorized
a fresh per-login anonymized PostgreSQL and copied/sanitized file snapshot,
the existing admin GUI in read-only demo mode, every operational action a
quiet server-side no-op, and exact disposable cleanup. 224-k exposed the
metadata-only catalog index. This 224-l suffix lets the authenticated demo
visitor DOWNLOAD those already-published sanitized catalog artifacts from
that visitor's exact copy. It does not restore original HMAC-sealed artifacts,
render active HTML inline, add apply authority, implement run-detail review,
or open other catalog pages; later same-PR suffixes do that as bounded
read-only display views. Objective 225 is the installed acceptance gate.
No second PR, merge, auto-merge, release, deployment, real company snapshot,
upstream provider call, mail or source custody operation.

## Verified OAP/GitHub state and dependencies

224-k's detached root response watcher is CLOSED; durable
`/tmp/slaif-oap-224k-response.log` contains `CONTROL_OK_DELIVERED` then
`RESPONSE_OK_EXACT`. Never repoll or resignal it. Its unchanged order SHA256
is `1dc122738dd6db1d803144feb0e463b635cb05dfd4806451af5def93023400d5`;
its immutable report SHA256 is
`aadbdc11bc857f4ec0d3cd1c1c308525b6f72309bba263fc2a58645c2a175c14`.
Remote PR383's report-only SELF head is
`0cd95d1a0ed8a4669170178ef6c7f9516640f996`, sole parent implementation
`06f2d548ecdae426c3d5b1bf4d42ecf306cdf0f6`, SELF tree
`a70e4d8e28d5e602e108ce8efa27e3f758c77022`, sole SELF diff
`oap/reports/224-k-catalog-snapshot-index.md`. Active is exact `224-k`
before this activation. PR OPEN/MERGEABLE, main `d3762e51`; unrelated open
PRs #379 and #319. Only release `v0.1.0-rc.1`; main branch protection API
reports no policy, but strategic final-head CI/review/material gates still
apply. The 224-j exact SELF checks were all green. The 224-k SELF-head CI
run `43483494108` has one DIRECT Unit/lint FAILURE: the existing
`tests/unit/test_admin_slaif_design.py::test_table_wrappers_are_labeled_and_focusable`
expects 51 wrappers but the new correctly labeled/focusable catalog table
makes 52 (job `132085919279`: 7,741 pass, one skip, one fail). Preserve
the strict wrapper checks and update ONLY this stale count/comment to 52
in this same order after verifying the new wrapper has role/label/tabindex;
do not edit immutable 224-k files or call the failed head green.
PostgreSQL integration is still IN PROGRESS at preparation; browser smoke
and all other checks are SUCCESS. Recheck actual terminal outcomes and correct any
direct defect within this same 224-l order/PR. Zero unresolved PR383
review threads. One canonical control waiter (PID 843942, PPID 1)
is blocked on the verified control FIFO; the 224-k root response watcher
is closed. No merge while objective 224 is incomplete.

224-k's demo-only index is already implemented and tested: the gate admits
only `/admin/operations/catalog/`, and the page projects safe remapped
catalog logical names from target-only `demo_display.leaves` via the
existing SELECT-only index reader. The 223/224-g worker already stored each
VERIFIED sanitized body as `bytea` with its SHA256 and byte_count in that
same target-only table; it grants the demo reader role SELECT only. The
existing demo gate binds each request to its exact verified, unexpired
`demo_snap_<20hex>` copy and installs a REQUEST-LOCAL sessionmaker on
`request.state.demo_admin`, with a read-only default and current_database
preflight. `get_sessionmaker_from_app(request)` returns only that factory
in the demo process. Reuse it; do not add another copy connection factory,
file mount or source-custody path.

Protected untracked `CODEX-SESSIONS.md`, `codex.sh`, `uv.lock` remain
SHA256 respectively
`5ae1d77c17a367e86ef725a8f9d25aba3464b24f22fba77fd2808377f8c7feda`,
`66eda80258f6a4f13b88a9fe2ad5a69b9e7df226a4e503f57b35b6c6f03e1247`,
`d3d0e80db77da56e41795c619875ac14b5d25427d5169a7c9d2c8dee45b3b5b6`.
Hash only; never read, stage, modify, clean or stash. Root owns this order
and `oap/active=224-l` bytes under the shared checkout BEFORE one control
`OK`; the existing right-pane coding agent owns Git/report and never merges.
No helper agents or model/profile changes.

## Bounded download change

1. Add ONE demo-only `GET /admin/operations/catalog/artifact` handler (exact
   path, not a prefix) to the 224-k demo catalog router, and admit ONLY that
   path through the central demo gate. The index page may link each safely
   projected artifact name to this handler as a normal hyperlink in the
   existing Artifact column. Keep ordinal first and current sortable
   headers; do not add a new action column. Normal admin and the original
   custody-backed catalog routes are untouched. Every unsafe `/admin`
   method remains the existing pre-body, pre-dispatch quiet 204 cut.
2. Accept exactly one bounded `name` query value and no duplicate/unknown
   query parameters. The name is a selector, never authorization, HMAC,
   replay, apply or source-file authority. Check the same 224-k closed
   catalog/remapped-name projection law before any body query; reject
   unknown, non-catalog, traversal, source-like or overlong values with a
   fixed safe 404 and no echo. Select only the corresponding
   worker-published target-only leaf by a PARAMETERIZED exact logical_name
   lookup; do not interpolate SQL identifiers or use a pathname. The gate's
   live account/session and exact-copy validation is required on EVERY
   request, not inherited from the index link.
3. Use `get_sessionmaker_from_app(request)` and the gate's SAME
   request-local copy engine/reader role. Before reading metadata/body in
   one read-only transaction, independently recheck `current_database()`
   equals `demo.target_db` and `transaction_read_only` is on. Query kind,
   byte_count and sha256 first; reject a missing row (404) or an invalid
   closed kind/name/size/hash (fixed 503). Enforce the existing 32 MiB
   catalog per-file maximum BEFORE fetching body; the worker's bundle cap
   is tighter. Fetch the bytea only after that bound, compare exact
   byte_count and SHA256 digest, and refuse on any mismatch or driver
   failure with one fixed safe 503. Never label an incomplete/corrupt
   artifact complete. Do not add a global cache or content persistence.
4. Serve ONLY the verified sanitized display body as a forced
   attachment (`Content-Disposition` with a safe ASCII basename),
   `application/octet-stream`, `X-Content-Type-Options: nosniff`,
   `Content-Security-Policy: default-src 'none'`, and `private, no-store`.
   Never render HTML/Markdown/JSON as active inline content, even for
   `REVIEW.html`. Do not expose stored SHA, DSN, credential, source path,
   raw original, HMAC receipt or server error in the public response.
   The page and docs call this a sanitized DISPLAY copy without original
   seal/apply authority. No provider or email effect.

## Verification, docs and publication

Expected product paths: `app/slaif_gateway/api/demo_admin_catalog.py`,
exact gate addition in `app/slaif_gateway/api/demo_admin_gate.py`, the one
catalog-index template, focused unit and owned PostgreSQL/browser tests,
the directly affected stale wrapper-count fixture in
`tests/unit/test_admin_slaif_design.py`, and a single 224-l section in
`docs/demo-admin.md`. No source or ordinary
schema migration, worker/sanitizer/custody change, normal catalog router,
provider adapter, Compose/Nginx or public endpoint. Explain any unavoidable
path expansion before publication.

Prove: exact admitted GET and near-miss 404; zero-account/unauthenticated/
expired/wrong-copy denial; repeated/extra/unknown selector refusal; source-
like names, traversal and credential-shaped input never echoed; normal
`/admin` operational POSTs still 204 without body parsing; no-store and
forced-attachment headers; byte-accurate sanitized body and digest/size
checks; no source/copy DML, audit, quota, mail, provider, file or network
side effects. Use focused mocked tests for input/response/error seams and
at least one owned PostgreSQL16 test of the REAL target-only table and
restricted reader role, including a test-only sanitized catalog leaf if
needed to prove positive body transport plus an integrity mismatch refusal.
If a test inserts a synthetic target-only leaf after the worker run, label
that honestly: it proves transport/binding, NOT source-file capture or
sanitization. The full configured-file installed artifact workflow remains
for objective 225. Exercise one index-download link in a real Chromium
fixture when available; if the owned browser fixture has no configured
catalog leaf, prove the honest empty page and use mocked ASGI for the
positive link instead, stating that limit. Avoid broad repeated matrices.
Recheck any direct 224-k hosted CI defect within this same order/PR.

Commit the unchanged strategic-authored order and active pointer first,
then implementation on SAME PR, then ONE immutable 224-l report in a
report-only SELF commit (sole parent implementation). Report exact order
hash, parent/tree/head, diff scope, true mocked-vs-owned PG/browser
results, negative security/privacy/accounting evidence, docs,
limitations, CI/reviews and protected file hashes. Push/verify remote
PR/head/main. Coding agent NEVER merges/auto-merges. Signal exactly two
bytes `OK` once on the verified response FIFO and rearm one canonical
control waiter. Root reviews and continues numeric objective 224 on this
PR; no merge in 224-l.
