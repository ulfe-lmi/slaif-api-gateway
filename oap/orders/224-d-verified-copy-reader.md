# OAP Work Order — 224-d

PR mode: AMEND_EXISTING_PR. Objective 224, unique OPEN PR #383,
`oap/224-demo-web`, base remote main
`d3762e51c9a323dee6b728c4a45fa21b0bffae86`. No second PR,
merge, auto-merge, release, deployment, production/company snapshot,
provider call or mail. The human authorized a live fake-admin demo
with a NEW per-login snapshot, fictional identities, real usage
patterns, copied/sanitized file-backed panels, read-only GUI and
silent no-op operations. Objectives 220-223 built the private account
and copy workers; 224-a/b/c built the control/session/worker and an
isolated default-off `/fakeadmin` entry app. This suffix makes an
EXACT fully verified disposable database readable under a dedicated
target-copy reader role and proves per-session copy isolation. It
does NOT mount the normal admin routers or claim the demo GUI usable;
the next same-PR suffix will bind the admin GUI behind a server-side
mutation gate and later suffixes will complete file-backed panels,
installed browser evidence and final delivery.

## Current GitHub/OAP truth and direct corrections

224-c response was exact `OK`; root FIFO response terminal 53171 is
CLOSED exit 0 and MUST NOT be repolled. Remote PR383 head is the
224-c report-only SELF `dc128eb98f5699f4abe2b3d9451288831a945894`,
sole parent implementation `be1ac33d91cf5c78a2c27726067b96e3ba76473c`,
sole diff `oap/reports/224-c-demo-entry-and-wait.md` SHA256
`7d1cca7fff36c52256b3b3b75e6d702999d908437ef1d8a8962189d38f0a7582`.
The immutable 224-c order SHA256 is
`5814354e5152879f209225e055873b5120e1ca84940eca9cf7d4c3efbaad88aa`;
`oap/active` is exact `224-c` before this activation. Remote main
remains `d3762e51`; PR383 is OPEN, mergeable, and not ready for merge.
Other open PRs #379/#319 are unrelated. Protected untracked
`CODEX-SESSIONS.md`, `codex.sh`, `uv.lock` retain respectively SHA256
`5ae1d77c17a367e86ef725a8f9d25aba3464b24f22fba77fd2808377f8c7feda`,
`66eda80258f6a4f13b88a9fe2ad5a69b9e7df226a4e503f57b35b6c6f03e1247`,
`d3d0e80db77da56e41795c619875ac14b5d25427d5169a7c9d2c8dee45b3b5b6`.
Hash only; never read, stage, modify, clean or stash. Root writes
this order and exact `oap/active=224-d` under the shared checkout
BEFORE one control `OK`. The existing right-pane coding agent owns
Git; no helper agent or model/profile change.

Intermediate 224-c exact-SELF CI Unit job FAILED only
`tests/unit/test_admin_usability_inventory.py::
test_every_visible_entry_field_has_linked_guidance`: the new demo
login template's `username` and `password` fields lack a linked help
id. Add concise useful hints and `aria-describedby` to each field;
preserve the existing visual style, CSRF and form behavior. The
224-c Playwright browser smoke is now SUCCESS; PostgreSQL integration
remains IN_PROGRESS. Inspect its actual terminal result and address
any demonstrated direct defect on this SAME PR, not a new PR. Code
Quality added nine
threads on c-head: root verified and resolved four false positives
for canonical ellipsis bodies of `DemoWebFacade(Protocol)`; five
remain on `tests/unit/test_demo_web.py` (three overwritten `r`
assignments and two unused `r`). Fix those exact test-hygiene items
without weakening assertions; root owns resolving the threads after
review. Six earlier b-head threads were already resolved by root.
No activated order or report may be edited.

## 224-d verified copy publication and read-only preview

1. Introduce one operator-created, STATIC login role on the separate
   target PostgreSQL service for the demo web process, with its own
   password. The snapshot worker needs only that role's closed-name
   identifier; the demo web process receives only that reader role's
   target host/port/user/password, separate from its control WEB role
   and from the worker target-admin/source-export credentials. The
   reader role starts with NO `CONNECT` on a new raw target database;
   221's closed create + `REVOKE CONNECT FROM PUBLIC` remains intact.
   No role or grant is created implicitly by an HTTP request. Default
   off/missing config fails safely before any publication.
2. After 222 database sanitation AND 223 file capture/verification
   finish for the exact job, the worker reuses the 224-b held-custody
   proof (job, request, target identity, combined verified state,
   exact file tree). Only then may it grant the target reader role
   `CONNECT` on that ONE disposable database and `USAGE`/`SELECT`
   on the approved copied `public` schema/tables. It must receive NO
   source-cluster business grant, provider secret, raw custody/file
   mount, target-admin privilege or business DML/DDL. Do not grant
   access to a raw, DB-only-sanitized, failed, stale-generation,
   reused or wrong-request copy. Grant work is bounded, safe-error,
   credential-masked and idempotent only for that exact verified
   copy. The grant must be complete BEFORE 224-a
   `record_verified_handoff` makes the copy browser-authoritative;
   if grant or handoff fails, never label the copy published and
   ensure exact request-associated cleanup removes/revokes the
   granted disposable database. Database DROP removes its grants;
   retain inspectable `cleanup_pending` on failed removal. No
   schema migration/general grant framework.
3. Extend the standalone demo web config with an independent target
   COPY READER connection (never the worker's target-admin passfile,
   source-export credential, normal `DATABASE_URL`, Redis or provider
   secret). Add a small session-bound copy reader: on every read,
   validate the 224-a demo session and live account/generation,
   recheck its exact request is verified/unexpired, require the
   closed `demo_snap_<20hex>` target database name from the control
   row, then connect to THAT copy under the reader role over the
   trusted private network. No pathname/custody read from the web
   process. Use a bounded connection lifetime (a per-request
   read-only session/NullPool is acceptable); dispose it after use
   so logout/cleanup is not held by idle web pools. A database-side
   READ ONLY transaction plus the role's SELECT-only grants should
   backstop the HTTP route. A stale, disabled, revoked, expired,
   wrong-request or missing copy must fail closed without exposing
   the target name, DSN or internal error.
4. Add one small authenticated `/fakeadmin/copy-preview` page or
   equivalent internal read-only preview that displays only safe
   bounded counts/fictional display data from the session's copied
   `public` tables. It is a proof of the copy binding, not a new
   admin UI. Two concurrent demo sessions must read their own
   distinct copies; the control/source business tables must never
   be queried through this target reader. No normal `/admin`
   routers, `/v1`, mutation form handlers, mail/provider jobs or
   file-backed panels in this suffix. The ready page may link to
   the copy preview but must continue to state full GUI browsing is
   not enabled yet.

## Scope, verification, publication

Expected product paths: narrow changes to
`services/demo_snapshot.py`, `services/demo_web_worker.py`,
`demo_web.py`, `api/fake_admin.py` and the ready/preview templates;
one purpose-built copy-reader helper if needed. `config.py` only for
the worker's target reader-role name setting. Existing
`db/repositories/demo_web_control.py`/`services/demo_web_control.py`
only if a safe exact request/copy projection needs a direct method.
Do NOT change `main.py`, ordinary admin routers/auth, quota/accounting,
provider adapters, 222/223 masking vocabularies, migration 0028,
Compose/Nginx or production source grants. Matching purpose-built
unit and owned-PG16 tests; exact c-head template/test-review fixes;
`docs/demo-admin.md`, `docs/configuration.md` and
`docs/cli-reference.md` for role setup, privilege/grant sequence,
safe rollback and still-incomplete status. No broad test or fixture
framework. Tell root before an unavoidable new path/scope expansion;
routine direct fixture/doc corrections stay in this order/PR.

Use only synthetic owned PostgreSQL16 source/target and run-owned
roles/copies. Prove before-grant `CONNECT` denial on the raw target;
grant refusal before full 222+223 verification; exact verified
grant success; `SELECT` allowed but `INSERT`/`UPDATE`/`DELETE`,
`CREATE`, admin/worker/source/provider privilege denied under the
REAL reader role; two sessions see two different copied datasets
or per-copy marker/count; wrong-copy/expired/disabled/revoked
sessions fail; grant/handoff failure leaves no usable browser copy
and exact cleanup drops the target with no survivor. Verify no
source row, quota/accounting fact, mail or provider effect. Test
target DB URL/name and all credential/custody canaries absent from
HTML, JSON, CLI errors and logs. Add the exact usability guidance
and five test-hygiene fixes above. Run focused unit/owned-PG/web
integration, scoped Ruff/docs/diff; root will use hosted CI on the
final PR head. Distinguish mocked from real-PG evidence and report
skips honestly. Existing admin GUI remains unavailable here.

Commit root-authored order/active unchanged on the existing PR
branch, push implementation, then publish ONE immutable
`oap/reports/224-d-verified-copy-reader.md` report-only SELF (sole
parent implementation, sole diff report). Verify remote PR383
head/branch/base, order/active/report, protected hashes; send one
exact response FIFO `OK` and rearm one canonical control waiter.
Coding agent never merges; root independently reviews and continues
same PR. Objective 225 stays inert and no demo deployment/release
is authorized.
