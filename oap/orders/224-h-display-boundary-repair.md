# OAP Work Order — 224-h: close verified display-publication gaps

PR mode: AMEND_EXISTING_PR. Objective 224, unique OPEN PR #383,
`oap/224-demo-web`, base remote main
`d3762e51c9a323dee6b728c4a45fa21b0bffae86`. This is a bounded
repair to the 224-g file-publication seam on the SAME PR, before the
remaining 224 GUI panels. No second PR, merge, auto-merge, release,
deployment, production/company snapshot, provider call or mail. The
human authorized the full fresh per-login anonymized DB and copied,
sanitized file snapshot, read-only existing admin GUI, silent no-op
operational controls and exact disposal. Later 224 suffixes finish the
GUI; 225 is the installed acceptance gate.

## Verified GitHub/OAP state and reason

The detached root watcher for 224-g closed with exactly
`CONTROL_OK_DELIVERED` then `RESPONSE_OK_EXACT` in
`/tmp/slaif-oap-224g-response.log`. Never resignal 224-g or repoll
that watcher. `oap/active` is exact `224-g`. The immutable 224-g order
SHA256 is
`09ecbff83f8e1e69b857021842374ef6a7e9b8b83690997cb652145818af1669`.
The immutable 224-g report SHA256 is
`de6e8bf4604f786399201569c59842c87bc58d8bbb202c223c0f2401d08439cb`.
Remote PR383 head is report-only SELF
`434b51439a6c59a2de50b6828c35159a1f17b97f`, sole parent
implementation `1dca080d8121c58fe416b6f7ff64cf044614d601`, sole
SELF diff `oap/reports/224-g-verified-file-display-publication.md`.
Remote main remains `d3762e51`; PR OPEN/MERGEABLE, no unresolved
review threads at root query. Other open PRs #379/#319 are unrelated.
At this order's preparation, 224-g head CI has ten checks: five
SUCCESS and five IN_PROGRESS, none yet a final-head merge gate.
Recheck actual CI; pending is not a pass. 224-g local evidence was
52 worker units, 102 web units, 68 file units, owned PostgreSQL16
worker14/admin-gate2/files1, scoped Ruff/diff clean. Preserve and
reuse that evidence; rerun only affected tests.

Root source review found four concrete gaps despite green focused
tests. `services/demo_web_worker.py` `_ingest_verified_display()`
re-reads the anchored main manifest but never checks its `target_db`
against the caller's exact target; `_display_ingest_transaction()`
checks leaf count but not aggregate bytes against
`manifest.files_bytes`; its claimed one finite elapsed deadline can
be exceeded by `_connect_copy()` (fixed timeout and a 100-ms floor)
or the final commit. `api/fake_admin.py` `/fakeadmin/files-preview`
sets `no-store` only on its rendered page, not its login redirects or
zero-account 404; it can raise while formatting a numerically
accepted but unrepresentable `captured_at` timestamp. The 224-g
report is immutable and overclaims these specific guarantees. This
repair closes them and corrects the *new* report/docs, not 224-g's
bytes.

Protected untracked `CODEX-SESSIONS.md`, `codex.sh`, `uv.lock` have
respectively SHA256
`5ae1d77c17a367e86ef725a8f9d25aba3464b24f22fba77fd2808377f8c7feda`,
`66eda80258f6a4f13b88a9fe2ad5a69b9e7df226a4e503f57b35b6c6f03e1247`,
`d3d0e80db77da56e41795c619875ac14b5d25427d5169a7c9d2c8dee45b3b5b6`.
Hash only; never read, stage, modify, clean or stash. Root writes this
order and `oap/active=224-h` to the shared checkout before exactly one
control `OK`. The existing right-pane coding agent owns Git; no
helper agent or model/profile change.

## Required bounded repair

1. Before ANY target connection/DDL, require the worker-held main
   manifest's exact `target_db` to equal the already verified
   `target_db` supplied to ingest. Retain the closed target-name law,
   exact job/request association, anchored handle identity and
   no-follow re-proof. A foreign but syntactically valid target name
   must refuse with the existing safe failure code, no connection,
   grant, handoff or copy publication. Do not accept authority from
   caller-provided database names or private manifest paths.
2. Before committing the target-only ingest transaction, require
   BOTH `count == manifest.files_count` and
   `total_bytes == manifest.files_bytes`, after fully exhausting the
   held iterator and its final name-binding/deadline check. On
   mismatch roll back the schema/table and fail the login closed.
   Keep one-leaf-at-a-time bounded transfer, private-field exclusion,
   parameterized SQL and descriptor closure on all failures.
3. Make the configured file-job elapsed bound a real wall-clock cap
   for connection, DDL/inserts and commit, not only leaf iteration.
   Refuse an already-expired budget before connecting; bound awaits
   with the SAME remaining deadline and preserve rollback/cancel
   cleanup. No handoff/grant if the operation times out or commit
   outcome is uncertain; exact target cleanup remains authoritative.
   The existing connection/statement timeouts may remain as tighter
   secondary caps. Do not add a setting or redesign worker custody.
   Document honestly if a driver cancellation can leave a transient
   ungranted target-only table until exact copy cleanup; never claim
   such a table is browser-authoritative.
4. Make EVERY response of the new `/fakeadmin/files-preview` route
   explicitly `Cache-Control: no-store`, including login redirects,
   zero-active 404, safe notes and successful page. Preserve the
   existing zero-account 404 behavior and session/account/request
   binding. Format only representable finite capture times, or return
   the same safe unavailable note on malformed/out-of-range values;
   never a 500, raw exception or private value. The worker-side
   capture-time law may be tightened to the representable range.
   Keep metadata-only preview, no body/download endpoint.
5. Add focused negative tests for foreign valid target mismatch,
   main-manifest aggregate-byte drift with unchanged count, expired
   before-connect and blocked connect/commit deadlines, and every
   preview response category plus extreme timestamp. Use mocked
   async timing only where necessary; distinguish it from real-PG
   tests. Rerun affected worker/web units, owned PostgreSQL worker
   chain and scoped lint. Reuse the existing 224-g positive PG
   evidence unless product changes make its rerun necessary; do not
   run unrelated complete suites. Add one real-PG refusal/rollback
   check if a new implementation seam demands it.
6. Correct `docs/demo-admin.md` if needed and state exact verified
   coverage/limits in the 224-h report. Do not edit the immutable
   224-g report or earlier orders. The report should distinguish
   source inspection, mocked deadline tests, real PG tests and hosted
   CI. Recheck `docs/configuration.md`/`docs/cli-reference.md` only
   where the repaired behavior affects an existing claim.

## Scope, negative boundaries and publication

Expected product edits are limited to
`app/slaif_gateway/services/demo_web_worker.py` and
`app/slaif_gateway/api/fake_admin.py`, with matching tests and the
small doc corrections above. Touch `demo_web.py` or the 223 verifier
only if the exact repair requires it; explain any expansion. Do not
alter the source/ordinary DB schema, 0028 migration, normal `/admin`
behavior, permission gates, key/provider secrets, route accounting,
quota ownership, replay ownership, file sanitizer outputs, mounted
panels, Compose/Nginx or product setup. No hosted-provider or real
company data. The static reader role remains SELECT-only on the
exact disposable copy; no `PUBLIC` grant or worker custody mount.

On completion, commit implementation to the SAME PR, then publish a
single immutable 224-h report in a report-only SELF commit whose sole
parent is the implementation commit. The report must give exact
order hash, parent/tree/head, diff scope, test commands/results,
negative/privacy/accounting evidence, docs, known limits and current
CI state. Push and independently verify PR/head/main state. Coding
agent NEVER merges or enables auto-merge. Signal exactly two bytes
`OK` on the verified response FIFO once; rearm one canonical control
waiter. Root reviews exact report/PR/CI/reviews, then continues the
remaining objective-224 GUI work on this PR. Do not claim objective
224 complete or merge it in 224-h.
