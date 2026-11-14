# OAP Work Order — 224-g

PR mode: AMEND_EXISTING_PR. Objective 224, unique OPEN PR #383,
`oap/224-demo-web`, base remote main
`d3762e51c9a323dee6b728c4a45fa21b0bffae86`. No second PR,
merge, auto-merge, release, deployment, production/company snapshot,
provider call or mail. The human authorized a fresh per-login
identity-masked PostgreSQL AND copied/sanitized file-backed snapshot,
the existing admin GUI in read-only demo mode, silent no-op
operational actions and exact disposable cleanup. Objectives 221-223
built the private database/file copies; 224-a..f bound the demo
session to a fully verified database and opened reviewed DB-backed
admin pages. This suffix gives the SAME session-bound SELECT-only
reader access to ONLY the 223-verified sanitized file display
leaves. It is a bounded publication/reader foundation, not a new
file service or full panel UI. Later same-PR suffixes wire all
remaining form, operation and file-backed panels before objective
224 can merge; objective 225 remains the installed acceptance gate.

## Current GitHub/OAP truth

224-f response was exact `OK`: detached root watcher
`slaif-oap-224f-response` closed and durable
`/tmp/slaif-oap-224f-response.log` contains
`CONTROL_OK_DELIVERED` then `RESPONSE_OK_EXACT`. NEVER rerun that
signal or repoll a closed terminal. Remote PR383 head is immutable
224-f report-only SELF `ac59ae3af40f54b807243160bc80a31d6c3d8e66`,
sole parent implementation `f67dc807b6ec73c1c36d0fcffc01f4e6c8fc6248`,
sole diff `oap/reports/224-f-db-backed-admin-sections.md` SHA256
`2417a158d4cbb074820601d09fad7a5c2e39ccce69cb3c451f70788d2bcd6fdb`.
Immutable 224-f order SHA256 is
`00d27226d37d912b26c61b3057c15276acd4a8e89d34dddb6bffb685ec0709ba`;
`oap/active` is exact `224-f` before activation. Remote main
remains `d3762e51`; PR383 OPEN, mergeable, incomplete. Other open
PRs #379/#319 are unrelated. 224-f local evidence: 93 focused
demo-web units, 102 normal-admin regressions, 5 table-inventory
tests, 16 docs tests, owned PG16 two-copy/admin-page/no-op test and
real Chromium smoke, scoped Ruff/diff clean; synthetic screenshot
visually reviewed. Exact 224-f hosted CI Unit/E2E/Compose/docs/
CodeQL checks are SUCCESS while PostgreSQL/browser checks are
IN PROGRESS at this order's preparation; inspect actual terminal
results and repair only demonstrated direct defects on the SAME
PR. No unresolved review threads at last query. Recheck final
head and do not treat pending checks as passes.

Protected untracked `CODEX-SESSIONS.md`, `codex.sh`, `uv.lock`
retain respectively SHA256
`5ae1d77c17a367e86ef725a8f9d25aba3464b24f22fba77fd2808377f8c7feda`,
`66eda80258f6a4f13b88a9fe2ad5a69b9e7df226a4e503f57b35b6c6f03e1247`,
`d3d0e80db77da56e41795c619875ac14b5d25427d5169a7c9d2c8dee45b3b5b6`.
Hash only; never read, stage, modify, clean or stash. Root writes
this order and exact `oap/active=224-g` under the shared checkout
BEFORE one control `OK`. The existing right-pane coding agent owns
Git; no helper agent or model/profile change.

## Strategic design and resource boundary

The 223 display leaves are already typed-sanitized, independently
verified and flat under the worker-only 0700 custody job's `files/`
directory (0600 leaves). Its private `files_manifest.json` contains
source references/hashes and inode identities and MUST NEVER be
copied to or read by the demo web process. Mounting the worker
custody root in the web process would also expose raw dump/worker
authority and is not allowed. Use the existing separate disposable
TARGET PostgreSQL database as the publication boundary instead:
create a purpose-built `demo_display` schema/table ONLY inside the
exact fully verified copy, store the sanitized display bytes and a
minimal safe index there, then grant the existing static copy
reader role USAGE/SELECT. The web process already connects to this
one database under a session-bound, request-local, SELECT-only,
READ ONLY credential. No source/production schema migration, new
database service, operator file mount, web worker credential or
separate web file-reading authority is needed. The schema is
disposable with the copy and is never in the source `public`
inventory that 222 verifies.

This intentionally duplicates verified sanitized file bytes in
the target database until the copy is dropped. Reuse the 223
per-leaf/aggregate admission and 224-b retained-copy count bounds:
default 32 MiB per leaf / 128 MiB aggregate, configurable upper
128 MiB / 4 GiB, at most four retained copies. Thus the additional
target payload is bounded by those existing limits (default at
most 512 MiB, configured upper at most 16 GiB before PostgreSQL
storage overhead). The private 223 custody also retains its own
sanitized leaves until cleanup. Document this storage tradeoff and
operator target-disk sizing; a capacity/time failure fails the
login closed and never publishes partial file data. Do not
silently truncate or omit a configured source.

## 224-g requirements

1. After the exact 224-b worker-held re-proof of BOTH 222 DB
   sanitation and 223 file verification (job/request/target name,
   combined state, exact files tree/digests), and BEFORE the 224-a
   `record_verified_handoff`, ingest ONLY the verified sanitized
   display leaves for THAT job into a fresh target-only
   `demo_display` schema/table in THAT disposable database. The
   table may store closed safe metadata (`logical_name`, `kind`,
   display `sha256`, byte count, capture time) and the complete
   sanitized `bytea` body. It MUST NOT store private
   `source`/`source_ref`/`source_sha256`, raw paths/URLs, original
   file bodies, seal/receipt/apply authority, target-admin DSN or
   private manifest. Reject duplicate/unknown logical names,
   extra/missing leaves, symlinks/nonregular or changed inodes,
   digest/size/mode mismatch, unknown kind, and any out-of-bound
   bytes. Reuse the 223 anchored no-follow held-descriptor proof
   and per-kind display verifier; do not read a checked file again
   by an unguarded pathname. Stream/handle one bounded leaf at a
   time, not a 4-GiB aggregate in memory. Use parameterized data
   transfer (never body/password in argv, SQL text or logs). One
   finite deadline covers the target-only ingest; a failed/torn
   transaction leaves no published table and leads to the exact
   request-associated failure/cleanup state. No schema change on
   source or ordinary gateway DB.
2. The existing static reader role receives `USAGE` on
   `demo_display` and `SELECT` on its one leaves table ONLY after
   the entire ingest succeeds, in the SAME bounded grant
   transaction that currently grants exact-copy public-table
   SELECT. No DML/DDL, no raw/DB-only/failed/stale/wrong-request
   copy access, and no `PUBLIC` grants. A missing/incomplete
   `demo_display` schema causes the grant transaction to roll back
   CONNECT and public SELECT as well. Only after successful ingest
   and grants may the 224-a handoff CAS publish the copy. Handoff
   refusal promptly marks failure; cleanup drops the exact target
   database (and therefore the display schema/grants) plus private
   custody, retaining inspectable `cleanup_pending` on failure.
   Retried jobs must fail closed or be idempotent for the exact
   verified request, never mix leaves across jobs.
3. Give the standalone demo web process a small request-bound
   read-only display reader using its EXISTING `DEMO_WEB_COPY_*`
   credentials and validated session/request/target binding. No
   filesystem access, worker module import, source/owner connection
   or app-global per-visitor state. Verify `current_database()` and
   database-side read-only mode, use a finite query/byte/row bound
   and dispose connections. It may expose an authenticated
   `/fakeadmin/files-preview` page listing only safe bounded
   logical names, kinds, sizes and capture times as a proof of
   binding; do not render raw HTML/TSV body from a URL in this
   suffix. A future internal method may retrieve one validated
   leaf body for the later panel adapters, but no permissive
   download endpoint or arbitrary path/SQL name. Every response
   is no-store and never reveals DB name, credential, private
   manifest, raw source reference or secret.
4. Keep existing `/admin` admission and every unsafe no-op exactly
   as in 224-f. Do not mount any remaining file-backed panel yet,
   change normal gateway storage or route quotas/accounting, or
   alter 222's masking policy. The 221/222/223 verified copy
   remains unavailable to demo browsers until this additional
   display-publication requirement is satisfied for NEW logins.
   Existing pre-upgrade demo sessions lacking `demo_display` may
   keep their already-authorized DB-only pages until expiry, but
   the new file preview must fail closed for them; document this
   exact upgrade behavior.

## Scope, verification, publication

Expected product paths: narrow changes to
`services/demo_web_worker.py`, `services/demo_snapshot_files.py`
only to expose a held verified-leaf iterator/proof if needed,
`services/demo_snapshot.py` only for safe target-admin connection
reuse if needed, `demo_web.py`/`api/fake_admin.py` plus one small
reader helper and demo preview template if needed. `config.py`
ONLY if an explicit bounded ingest deadline cannot reuse the
existing file-job bound. Matching purpose-built unit and owned
PostgreSQL16 integration tests; `docs/demo-admin.md`,
`docs/configuration.md`, `docs/cli-reference.md` for target-only
schema, no new source migration, storage/timeout/operator setup,
rollback/cleanup and still-incomplete GUI status. Do NOT change
`main.py`, ordinary admin routers/templates, 0028 migration,
provider adapters, public quota/accounting, Compose/Nginx, or
production file mounts. Tell root before an unavoidable new path
or design expansion; routine direct fixture/doc corrections stay
in this same order/PR.

Use owned synthetic PG16 source/target, operator-owned scratch
custody and fake credentials only. Prove raw and DB-only-sanitized
copies have no readable `demo_display`; exact fully DB+files-
verified job publishes the complete closed leaf set/digests under
the real reader role; private manifest/source canaries absent from
the target table, HTML, JSON, CLI errors and logs; reader DML/DDL,
source-cluster and wrong-session/copy reads denied; two concurrent
sessions get distinct safe file projections; no source business
row, audit, quota, mail or provider effect. Inject a leaf changed
after verification, missing/extra leaf, target ingest failure,
grant failure and handoff refusal: none may produce a browser-
authoritative partial display, and exact cleanup removes the
right DB/custody with no unrelated copy touched. Verify default
and configured resource bounds, no 4-GiB aggregate allocation,
safe error codes and rollback. Test the preview with a sanitized
fixture leaf and no-store; distinguish mocked from real PG and
report skips. Reuse accepted 221/222/223 and 224-d/e/f component
evidence; do not rerun unchanged broad suites. Run scoped
Ruff/docs/diff and focused regression on existing demo login,
copy preview and admin pages. Hosted CI is root's final-head gate.

Commit root-authored order/active unchanged on the existing PR
branch, push implementation, then publish ONE immutable
`oap/reports/224-g-verified-file-display-publication.md`
report-only SELF (sole parent implementation, sole diff report).
Verify remote PR383 head/branch/base, order/active/report,
protected hashes; send one exact response FIFO `OK` and rearm one
canonical control waiter. Coding agent never merges; root
independently reviews and continues same PR. Objective 225 stays
inert and no demo deployment/release is authorized.
