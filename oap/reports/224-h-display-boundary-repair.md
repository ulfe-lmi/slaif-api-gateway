# OAP 224-h report — close verified display-publication gaps

Status: COMPLETE (implementation + report-only SELF on PR #383).
Objective 224 is NOT complete; the remaining 224 GUI panels and the
225 installed acceptance gate are still outstanding.

## 1. Order and state

* Order: `oap/orders/224-h-display-boundary-repair.md`
  SHA256 `23b443019a0d859537238a002b4f593f284dc96386f3b7cb261c4d36ef7536a4`
* `oap/active` = `224-h` (root-authored activation bytes committed at
  `d1901aefe6cf743930273bc0550dc50eff17d60f`, tree
  `a9dfc3849c7dcf0b317683fcdb6aa6b5cedc6aaf`).
* PR mode: AMEND_EXISTING_PR — objective 224, unique OPEN PR #383
  `oap/224-demo-web`, base remote main
  `d3762e51c9a323dee6b728c4a45fa21b0bffae86`.
* Reason: root source review found four concrete gaps on the 224-g
  file-publication seam despite green focused tests, and the 224-g
  exact-head hosted CI failed the admin usability inventory because
  the new 224-g files-preview table raised the sortable-table count
  (55 -> 56).
* Commits (all on the PR):
  * activation bytes: `d1901aef` (parent `434b5143`, the immutable
    224-g report-only SELF — untouched);
  * implementation: `5ff0fb60f3bc6a3b7297a7e2afcd5cea2415f3c1`,
    tree `9d499ad1090137733dce80c35c28a83de163734c`;
  * this report-only SELF: sole parent `5ff0fb60`, sole diff
    `oap/reports/224-h-display-boundary-repair.md`.
* The 224-a..224-g orders and reports are immutable and unmodified in
  this round; the 224-g report's four overclaims are superseded by
  this round's code/docs (its bytes were not edited).

## 2. Diff scope

Product (exactly the two files the order names):

* `app/slaif_gateway/services/demo_web_worker.py`
* `app/slaif_gateway/api/fake_admin.py`

Tests:

* `tests/unit/test_demo_web_worker.py` (+7 focused tests, fake txn
  updated to the context-manager API)
* `tests/unit/test_demo_web.py` (+2 focused tests)
* `tests/unit/test_admin_usability_inventory.py` (55 -> 56 + comment;
  direct CI-fixture correction for the 224-g table)

Docs: `docs/demo-admin.md` only. `demo_web.py`, the 223 verifier,
`demo_snapshot_sanitize.py`, migrations, Compose/Nginx, configuration
and CLI are untouched. No new settings, no new CLI, no schema change
(source or ordinary DB), no mounted panels, no provider call, no mail.

## 3. The four repairs

1. **Target equality before any connection.**
   `_ingest_verified_display` now requires the worker-held main
   manifest's EXACT `target_db` to equal the verified copy binding
   supplied to ingest, immediately after the anchored no-follow
   manifest re-proof and BEFORE any target connection. The retained
   closed target-name law, exact job/request association, anchored
   handle identity and no-follow re-proof are unchanged. A foreign
   but syntactically valid target name refuses with the existing safe
   code `WEB_DISPLAY_INGEST_FAILED` — no connection, no grant, no
   handoff, no copy publication. Caller-provided database names and
   private manifest paths are not authority.
2. **Count AND aggregate bytes before commit.**
   `_display_ingest_transaction` now requires BOTH
   `count == manifest.files_count` AND `total_bytes ==
   manifest.files_bytes` after fully exhausting the held re-proof
   iterator and its final name-binding/deadline checks. On mismatch
   the transaction rolls back the schema/table and the login fails
   closed. One-leaf-at-a-time bounded transfer, private-field
   exclusion, parameterized SQL and descriptor closure on all
   failures are unchanged.
3. **Real wall-clock deadline over connect/DDL/INSERT/commit.**
   An already-expired budget is refused BEFORE connecting. ONE
   `asyncio.timeout` (the existing file-job elapsed bound
   `DEMO_SNAPSHOT_FILES_MAX_ELAPSED_SECONDS`; no new setting) covers
   the connect, the DDL, every parameterized INSERT and the FINAL
   COMMIT — the commit is the transaction context-manager exit, which
   sits inside the timeout scope. The synchronous leaf reads between
   awaits keep an explicit monotonic check (and the generator's own
   per-leaf deadline check). A timed-out or uncertain commit fails
   closed: NO handoff and NO grant may follow. Honest cleanup
   semantics: the cancellation/rollback/connection-close cleanup that
   follows a timeout may still take extra time; the connection close
   is the rollback backstop, the exact request-associated copy
   cleanup remains authoritative, and a transient UNGRANTED
   target-only table (if a driver cancellation ever leaves one) is
   never browser-authoritative (the reader grant and handoff happen
   only on the confirmed-commit path). The existing connection
   (`command_timeout`/`timeout` 30 s) and statement timeouts remain
   tighter secondary caps. Source-inspection basis (installed
   sources, not guesswork): asyncpg 0.32.0 `Transaction` forbids
   manual commit inside an `async with` block (InterfaceError), so
   the context-manager transaction with the outer timeout is the
   design used; `asyncio.timeouts` (this runtime, 3.12.15) delivers
   exactly one task cancellation at the deadline and converts it to
   `TimeoutError` on exit.
4. **Preview response + time law.**
   EVERY response of `/fakeadmin/files-preview` is explicitly
   `Cache-Control: no-store`: login redirect, zero-active 404, safe
   note and successful page (the shared `_json` helper used by the
   other demo routes is untouched). The route formats only
   representable finite capture times; a stored value outside the
   representable range renders the SAME safe note — never a 500, raw
   exception or private value. The worker-side capture-time law was
   tightened from `< 9e15` to the representable range below
   `datetime`'s year-9999 ceiling:
   `_DISPLAY_CAPTURE_AT_MAX = 253_402_300_800.0` (exclusive), so
   8e15 refuses while 2038 and post-2038 capture times remain valid.
   Metadata-only preview is unchanged; there is still no
   body/download endpoint.

5. **Direct CI fixture correction (queued g-head finding).**
   `tests/unit/test_admin_usability_inventory.py` now expects 56
   sortable admin tables (+1 comment line for the 224-g
   files-preview metadata table). The new table already satisfied the
   structural law (first-position `data-ordinal` header, server-
   rendered ordinal cell, fixed `colspan="5"` empty-state row), so
   only the fixed count needed correction.

## 4. Evidence (distinguished)

Source inspection (no test): asyncpg 0.32.0 transaction/commit API
semantics and this runtime's `asyncio.timeouts` cancellation
mechanics, both read from the installed packages, informed the design
and the wording above.

Mocked async-timing unit tests (no database; the deadline/timing
evidence is mocked and is NOT real-PG proof):
`tests/unit/test_demo_web_worker.py` — 59 passed (52 carried from
224-g + 7 new):

* foreign syntactically-valid target: refused with the safe code and
  ZERO connect attempts (counted);
* aggregate-byte drift with unchanged count: DDL + the one leaf
  INSERT run, the aggregate check refuses, transaction rolled back;
* already-expired budget: refused BEFORE connecting (zero connect
  attempts);
* blocked connect past the deadline (mocked slow connect): no DDL,
  safe elapsed-bound refusal;
* blocked commit past the deadline (mocked stalled commit): the
  commit never confirmed (`committed == 0`), connection closed, safe
  elapsed-bound refusal — no handoff/grant can follow;
* blocked DDL past the deadline (mocked stalled DDL): no statement
  completed, NO INSERT, transaction rolled back, connection closed;
* capture-time representable range: 8e15 refuses;
  253402300799.0 (the year-9999 boundary) accepts and commits; the
  exclusive bound 253402300800.0 refuses.

Unit tests (web): `tests/unit/test_demo_web.py` — 104 passed (102 +
2 new): no-store asserted on the 404, the login-bounce redirect and
the safe-note page (the successful-page no-store was already
covered); a stored capture time of 9e15 renders the same safe note
with HTTP 200 (never a 500) and the copy name stays absent.

Real PostgreSQL 16 (owned target service, exact run-owned cleanup,
containers untouched and not recreated):
`tests/integration/test_demo_web_worker_postgres.py` — 14 passed
against the FINAL code. This rerun was required because the product
change altered the real transaction-control path: it covers the real
happy-path publish (real connect, real DDL/INSERT, real confirmed
commit inside the timeout, reader-grant law, table content and
canary absence), the real torn-transaction rollback on the real copy
(no published table, exact cleanup), and the real post-verification
leaf-tamper refusal. (An intermediate rerun of the same module also
passed against the first patch revision; the final-code run is the
authoritative one.)

Hosted CI: at the 224-g exact head (`434b5143`) the run completed
with 6 of 7 jobs SUCCESS and ONE failure — `Unit, lint, and
migration head`, failed solely at
`test_admin_usability_inventory.py::test_every_admin_table_has_structural_ordinal_column`
(56 tables found vs 55 expected; 7714 passed, 1 skipped) — the direct
fixture correction of section 3.5. The 224-h head CI was still
running at report time; root owns final-head CI/review/merge.

Local hygiene: scoped Ruff (repo policy E4/E7/E9/F) clean on all five
changed Python files; `git diff --check` clean;
`tests/unit/test_documentation_inventory.py` 16 passed after the doc
change.

Test commands (local, venv, `-p no:warnings`, addopts `-q`):

```
.venv/bin/python -m pytest tests/unit/test_demo_web_worker.py -q -p no:warnings
.venv/bin/python -m pytest tests/unit/test_demo_web.py -q -p no:warnings
.venv/bin/python -m pytest tests/unit/test_admin_usability_inventory.py -q -p no:warnings
export PATH="/tmp/pg16/bin:$PATH"
export DEMO_SAN_TEST_SOURCE_URL=postgresql+asyncpg://test:test@127.0.0.1:54351/slaif_gateway_test
export DEMO_SAN_TEST_TARGET_URL=postgresql+asyncpg://test:test@127.0.0.1:54352/postgres
.venv/bin/python -m pytest tests/integration/test_demo_web_worker_postgres.py -q -p no:warnings
```

## 5. Negative / privacy / accounting evidence

* No private manifest field (`source`, `source_ref`, `source_sha256`,
  inode identity, on-disk leaf name) is projected into SQL — the
  carried 224-g assertions on the happy path re-ran green.
* The caller's target name is never authority; the target DB
  name/DSN/credential never reach any web response (carried
  assertions re-ran green).
* The zero-active 404 and login bounce of the files-preview route
  carry no demo state beyond the pre-existing behavior, now with
  explicit no-store; the shared helper for other demo routes is
  unchanged.
* The preview remains metadata-only (name/kind/bytes/capture time);
  no body bytes are rendered; no download endpoint.
* `no-store` prevents normal HTTP caching of demo facts and makes
  dynamic reload recheck auth; it is not an absolute guarantee of
  browser history/BFCache erasure (documented as such).
* A law refusal that occurs after the deadline has already elapsed
  may surface with the finite elapsed-bound message (same safe code)
  instead of the specific refusal message — same code, still finite
  and safe.
* Accounting/key/provider paths are untouched: the ingest remains
  worker-only, strictly between the combined worker-held re-proof and
  the verified handoff; no route/quota/secret change.
* Protected untracked files (`CODEX-SESSIONS.md`, `codex.sh`,
  `uv.lock`) verified by hash before and after; never read, staged,
  modified, cleaned or stashed.

## 6. Docs

* `docs/demo-admin.md`: the 224-g Worker-ingest deadline bullet now
  states the real wall-clock cap with honest cleanup semantics (no
  absolute "no await can overrun" claim); the closed display law
  bullet now states the representable capture-time range and the
  count+bytes and target-equality additions; the Reader-law
  paragraph now states EVERY-response no-store and the safe-note
  time fallback; a new "Boundary repair (224-h)" subsection records
  the four repairs and the +1 inventory correction.
* `docs/configuration.md` / `docs/cli-reference.md`: rechecked — no
  existing claim is affected (no new setting/CLI; the existing
  files-elapsed setting is now a real wall-clock cap, which the
  current wording does not contradict). Unchanged.

## 7. Known limits (carried and new)

* The demo remains default-off and NOT usable for company
  demonstrations; all file-backed admin panels remain unmounted (a
  later 224 suffix wires them); objective 225 remains the installed
  acceptance gate.
* No verified TLS guarantee on the control/copy connections:
  explicit `ssl=False` private-network stage boundary.
* The target-only `demo_display` schema is disposable with the copy;
  the storage tradeoff (duplicated sanitized bytes, bounded by the
  223/224-b limits) is unchanged.
* Post-timeout cleanup awaits (rollback/close) are bounded only by
  the driver's secondary caps, not by the deadline itself; the
  guaranteed property is that no ingest/grant/handoff is confirmed
  after the deadline, with exact target cleanup authoritative.
* The single `asyncio.timeout` delivers one cancellation at the
  deadline; the synchronous leaf reads between awaits are bounded by
  the explicit monotonic check and the generator's per-leaf check,
  not by preemption.

## 8. Protocol state

* Implementation commit `5ff0fb60f3bc6a3b7297a7e2afcd5cea2415f3c1`
  (tree `9d499ad1090137733dce80c35c28a83de163734c`) on PR #383; this
  report-only SELF is its sole successor; the remote head will be
  this SELF with main still at `d3762e51`.
* One exact two-byte `OK` was sent on the response FIFO; one
  canonical detached control waiter was re-armed. No merge, no
  auto-merge, no helper agents, no second control signal.
