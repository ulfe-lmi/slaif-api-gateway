# OAP 224-x — Final Report (catalog final reads: direct artifact downloads, frozen apply-status, w-repair coverage)

## Commit topology

- Activation commit: `bdda662b2457db1cd14ea33361e50ad56fb6f2f9`
  (tree `f8e00c839d30e15d4edb348dcd2d01ee885305fb`, sole parent
  `5c169f2659a86dd61cfdfcd64e9fc14e54d50dfc`) — committed the
  root-authored order and the exact `oap/active` = `224-x`
  pointer (five bytes) unchanged, FIRST.
- Immutable order: `oap/orders/224-x-demo-catalog-final-reads.md`,
  SHA256
  `87ce496bb75f0de854aeb7ee43412e1cca5e07d47ca87d7a012b48540b3d3049`.
- Implementation head (sole SELF parent):
  `d0c4ab0eadae98d2bff06c45a0f2982c7ad18262`
  ("224-x: repair w CI/key-config defects and add the four
  catalog final-read GETs"; 14 files, +2380/-352).
- This report: report-only SELF, sole parent = the implementation
  head, sole diff = this file. No merge; PR #383
  (`oap/224-demo-web`, base `main`) left open for strategic
  review.

## Prior objective state (224-w, terminal)

- w report-only SELF `5c169f2659a86dd61cfdfcd64e9fc14e54d50dfc`
  (sole parent `6b8bbbb85447d65d546b93f89b5b6651f8157ce8`, tree
  `a03d33d15233567130e673cde8d0ba63160f8469`, sole diff
  `oap/reports/224-w-demo-smtp-key-route-read.md`); the exact
  two-byte response `OK` was delivered and that terminal is
  CLOSED (`CONTROL_OK_DELIVERED`, `RESPONSE_OK_EXACT`). It was
  not repolled and w was not re-signaled.
- The exact w SELF-head CI workflow run `43572942901` terminal
  FAILURE at `2026-11-14T08:02:00Z`: 9 of 10 checks succeeded
  across three workflows (including hosted PostgreSQL, real
  Chromium, E2E, Compose, docs and both CodeQL workflows); the
  single failing Unit/lint job `132381029541` reported 7,917
  passed / 1 failed / 1 skipped, the one failure being
  `tests/unit/test_admin_key_actions_templates.py::test_q_detail_demo_shows_admitted_read_links` (w added a `configuration.json` demo href that the repaired link-inventory law refuses).

## w-defect repairs (order items 1-3)

1. **False key-configuration export -> safely unavailable.**
   `GET /admin/keys/{canonical-UUID}/configuration.json` in demo
   is now a FIXED safe 503 with NO JSON body and NO copy read:
   the 222/224-r sanitizer maps `gateway_keys.metadata` to KR
   (clone-receipt-only), discarding the ordinary policy members
   (`allowed_providers`, `responses_policy`, `rate_limit_policy`,
   `lazy_throttling_policy`, `live_burn`,
   `external_tool_policy`) that
   `KeyService.render_key_configuration_document` reads, and the
   demo process only carries fixed neutral settings (its
   operator ceilings are never the source deployment's).
   Rendering the version-1 document from the stripped copy plus
   neutral settings would fabricate default policy for real
   keys; until a separately verified policy projection exists
   (bounded follow-on work, a HUMAN CHOICE PENDING), the demo
   emits no configuration export - no source fallback, no raw
   metadata passthrough, no default guessing. The key-detail
   page keeps the action visible and labels it "unavailable in
   this demo" (no `configuration.json` link). The w docs
   overclaims were corrected in place in `docs/demo-admin.md`;
   the immutable w report was NOT edited. The hosted w-head
   unit failure was reproduced locally and repaired: the demo
   detail no longer renders the `configuration.json` href, the
   normal-admin href is unchanged, and
   `test_admin_key_actions_templates.py` passes 21/21 locally
   (the hosted run is the failure evidence; the repair is
   proven locally).
2. **Calibration selector.** A query-free
   `GET /admin/keys/{canonical-UUID}/calibration/summary.json`
   now uses the normal selector's DEFAULT multiplier 3 (proven
   byte-identical to an explicit `multiplier=3` over the same
   frozen copied rows); explicit invalid input remains a fixed
   safe 400. The gate enforces the rebuilt RAW query law before
   any copy binding: a small whole-raw-byte ceiling BEFORE any
   split; split on LITERAL `&`; each pair must carry exactly ONE
   literal `=` with an EXACT literal ASCII parameter name
   (encoded names such as `st%61rt_at` and encoded delimiters
   such as `%26` can never change a parameter boundary); each
   value bounded in RAW length, then percent-decoded EXACTLY
   ONCE (invalid/truncated escapes refused, `+` is not a
   space); unknown names, duplicates and oversized values
   refused; strict value grammars (ISO-8601 date/datetime or
   empty for the optional bounds; positive decimal for
   multiplier); and every NONEMPTY decoded value checked against
   the pure known-incoming-secret-alias classifier with the raw
   scope and the DEMO APP'S fixed neutral accepted-prefix tuple
   BEFORE session resolution (a date/numeric-shaped credential
   can fit the grammars). A classifier error or the unavailable
   prefix sentinel fails closed. Every refusal is a plain
   default-denied 404 with no echo. The handler re-runs the
   normal strict parsers (semantic refusal, e.g. month 13, is a
   fixed safe 400 before any copy read), recalculates over the
   FROZEN copied usage rows, and performs no accounting DML.
3. **Route choices/headers.** Captured completion-profile choice
   IDs and the selected ID are withheld (no echo, no link) when
   they equal a known incoming authentication alias. When the
   optional `profiles/completion-choices.json` leaf is absent,
   the picker shows the FINITE PACKAGED completion-profile
   defaults (the bundled profile data the normal form offers
   when the operator directory is absent), clearly labeled as
   package defaults - not copied source state; a corrupt
   configured leaf is the fixed safe 503. The demo
   key-attachment wire law is documented exactly: a SUCCESSFUL
   calibration download is application/json with the attachment
   disposition, and the gate normalizes EVERY dynamic /admin
   response to exactly one `Cache-Control: private, no-store`
   (pre-existing headers replaced, never duplicated) plus
   nosniff; 404/400/503 are fixed HTML refusals. Misleading
   SMTP demo readiness wording was corrected without altering
   normal content.

## Catalog read coverage (order items 4-6)

Four NEW exact query-free GET families are admitted (gate
enforced before session resolution; every unsafe method on the
admitted paths is the pre-body quiet 204; no query, subpath,
alternate-slash or non-canonical-ID variant is admitted - fixed
404):

- `/admin/operations/catalog/runs/{run-id}/artifact/{file}` (the
  run-id is exactly `demo-run-` plus 24 lowercase hex) - the
  closed seven worker-published run content files
  (`catalog-refresh.json`, `catalog-baseline.json`,
  `routes-proposal.tsv`, `pricing-proposal.tsv`,
  `fx-proposal.json`, `validation.json`, `REVIEW.html`), each
  intersected with the already-published sanitized leaf law for
  that exact file's worker-published kind.
- `/admin/operations/catalog/runs/{run-id}/apply-status` (same
  exact run-id shape) - the frozen historical apply status for
  one captured run.
- `/admin/operations/catalog/jobs/{32hex}/artifact/{file}` - the
  closed upload names (`bundle-`/`baseline-`/`baseline-export-`
  plus 32 hex; the gate regex and the handler both match the
  longest fixed prefix FIRST, so `baseline-export-<32hex>` is
  never misread as `baseline-<export-...>`) and the six
  sanitized proposal artifact names (`source-manifest.json`,
  `provider-catalog-normalized.json`, `routes-proposal.tsv`,
  `pricing-proposal.tsv`, `provider-catalog-report.md`,
  `warnings.json`).
- `/admin/operations/catalog/jobs/{32hex}/package/{preset}/{file}`
  - the finite five presets crossed with the five closed
  package file names (`routes-proposal.tsv`,
  `pricing-proposal.tsv`, `package-report.md`,
  `model-review.md`, `package-manifest.json`).

The existing safe `/admin/operations/catalog/artifact?name=...`
selector (224-l) is unchanged; the run detail page now links the
seven run files to the DIRECT downloads (never the `?name=`
selector), and links are rendered only where the corresponding
verified leaf exists (no dead links; a partial run is a fixed
safe 503, never a half page).

Each artifact GET runs in ONE SELECT-only/read-only transaction
on the gate-bound request-local copy engine with the
in-transaction `current_database()` / `transaction_read_only`
recheck: the FIRST query is metadata-only (parameterized exact
logical name, DB-computed `octet_length(body)` - no body
transfer) requiring the exact closed kind and nonnegative
`byte_count`/actual length no greater than 32 MiB and EQUAL;
the SECOND query fetches the body only under `kind` /
`byte_count` / `sha256` / `octet_length(body) <= :cap` re-
asserted as BOUND parameters, and the fetched bytes are
re-verified in memory for exact length and SHA256 before
release (an incomplete/corrupt artifact is never returned).
Missing leaf -> fixed 404; corruption, bound violation,
digest/size mismatch or driver failure -> the fixed safe 503
(never the bytes, never a partial artifact, never a source
value). No source custody, seal key, live catalog root, source
database, filesystem or network access occurs.

A SUCCESSFUL download carries `application/octet-stream`, a
forced `Content-Disposition: attachment` with the safe closed
base name, `X-Content-Type-Options: nosniff`,
`Content-Security-Policy: default-src 'none'`, and exactly one
`Cache-Control: private, no-store` (gate-normalized). 404/503
are fixed HTML refusals carrying
`X-Content-Type-Options: nosniff` plus that same gate-normalized
single `Cache-Control: private, no-store` header (no name, kind,
hash, DSN or error value echoed); focused refusal-header unit
asserts cover the 404 and 503 catalog refusals.

**Apply-status: fixed explicit unavailability (reported
limitation).** The apply-status page first verifies, with the
SAME closed seven-file metadata-only inventory, that the run
exists in THIS copy (missing run -> fixed 404 without ever
reading the applications table; a partial or kind-mismatched
run -> fixed safe 503). It then renders the FIXED explicit
"Apply status is unavailable for this run in this copy." state
with ZERO records, and the copied
`catalog_refresh_applications` table is NOT read or listed at
all. Verified-mapping analysis: the worker remaps captured run
identifiers for the display leaves by
`demo-run-` + keyed-HMAC-12-bytes over the ORIGINAL run id,
while the sanitizer remaps the copied
`catalog_refresh_applications.run_id` values by the INDEPENDENT
per-copy `remap_str_id` (`demo` + 60 keyed-HMAC hex); the web
process holds neither the original run id (never persisted) nor
the per-copy seed, so NO verified mapping exists between a
copied application record and the display run id. Presenting
copied rows as this run's status would mislead, so per order
item 4 the shape is fixed safe unavailability and this exact
limitation is reported; the unavailable state is a historical
display limitation of the sanitized copy, NOT a statement that
the run was never applied. Visible operational controls are
labeled quiet no-ops and cannot reach source DML.

**Path correction (order wording).** The order's allowed-path
list names `demo_web.py`; per the strategic clarification that
means the EXISTING `app/slaif_gateway/demo_web.py` (there is no
`app/slaif_gateway/api/demo_web.py`). No edit to that router
mount file was required: the named 224-x GETs are served by the
existing demo catalog router (`demo_admin_catalog.py`) behind
the demo gate, and the working tree leaves `demo_web.py`
byte-identical.

## Verification evidence (all local/owned; hosted checks NOT observed at report time)

### Focused mocked units (green)

- 17 NEW `test_x_` tests in `tests/unit/test_demo_web.py`
  (counted from source; the `-k "test_x_"` selection passes
  17/17): calibration default-multiplier-3 byte-identity and
  the rebuilt gate query law (literal names, encoded
  name/delimiter/equals negatives, oversized raw query,
  date-shaped and numeric cookie-alias negatives);
  route-picker packaged defaults and alias withholding;
  catalog gate exact-shape admission (303/404/near-misses,
  including that a 32-hex "original" job id is NOT a
  near-miss - same canonical shape) and unsafe-method 204s;
  run-artifact positive (exact bytes + wire law +
  metadata-first DB-computed `octet_length` + bound-parameter
  body re-assert), missing 404, seven corruption cases refused
  BEFORE any body query, body digest-mismatch 503; job
  artifact positives for ALL THREE closed upload kinds plus
  proposal, job missing 404, package positive; apply-status
  missing-run 404 (applications table never read) and
  partial-run 503, the run-present fixed-unavailable page, and
  the rows-never-rendered no-misattribution negative (101+
  copied rows, including a tampered row and an incoming-alias
  canary, are never read or echoed).
- The repaired 224-w admin key-actions template suite:
  `test_admin_key_actions_templates.py` 21/21 (the hosted
  w-head failure `test_q_detail_demo_shows_admitted_read_links`
  reproduced locally and repaired).
- The full directly-affected unit set ran green (0 failed,
  Ruff clean on every changed .py): `test_demo_web.py` (277),
  `test_admin_key_batch_209.py` (81),
  `test_admin_email_operations_215.py` (51),
  `test_admin_reports_214.py` (44),
  `test_catalog_refresh_apply.py` (16),
  `test_admin_key_actions_templates.py` (21) - 490 tests.

### Byte-identity oracle (normal rendering)

The 224-x-modified templates (apply_result, proposals,
smtp_test, configuration_form, keys/detail link block, run
detail, catalog jobs) render BYTE-IDENTICAL under
representative NORMAL contexts against the activation-commit
originals (`FAILURES: none`); the demo branches render the
expected content in separate demo smoke renders.

### Owned PostgreSQL 16, two simultaneous copies

Both tests in
`tests/integration/test_demo_web_admin_gate_postgres.py` pass
(EXIT=0, no failures) against the owned PG16 pair (source
`127.0.0.1:54351`, target `127.0.0.1:54352`, `test/test`,
disposable data preserved). The two-copy fixture proves:
snapshot A/B isolation (exact run/job/package artifact bytes +
wire law over session A's clients; session B's copy has none of
the test-only leaves -> fixed 404, no cross-copy read);
stored-SHA corruption -> fixed safe 503 without the bytes (with
digest restore); the seven near-miss shapes -> fixed 404;
apply-status fixed-unavailable page with ZERO records BEFORE and
AFTER inserting the ONE test-only
`catalog_refresh_applications` row (the row's values are never
rendered - no misattribution without a verified run-id
mapping), copy-B 404 for the same canonical run, the quiet 204
cuts with a 200,000-byte garbage body, and the partial-run
503; and the source-policy-divergence proof (a nondefault
policy seeded into the first source key's `gateway_keys.metadata`
and restored by a finalizer; BOTH copies' metadata for that key
proven clone-receipt-only with no policy fields;
`configuration.json` -> fixed safe 503 with NO JSON for both
sessions - copy A's inserted key and copy B's own key). The
test-only insertions are explicitly labeled transport/binding
evidence (NOT 222 source capture or worker publication) and are
cleaned by exact-name / exact-id deletes in a finally, with
cleanup-proven 404s.

### Real Chromium (owned browser fixture)

The browser copy is built by the REAL worker from the owned
source fixture. The fixture proves: the NON-EMPTY catalog index
with the seven `?name=` sanitized-selector hrefs (the 224-l
selector, unchanged; no empty-state note, no no-storage-
inference note); the run detail page with the seven DIRECT
`/runs/{run-id}/artifact/{file}` hrefs plus the apply-status
link; a REAL
authenticated-context artifact download (exact
`_san_validation_json` bytes + forced attachment wire law:
octet-stream, attachment, nosniff, CSP `default-src 'none'`,
the single `private, no-store` cache header); the collect page
listing exactly that one Captured run group; the apply-status
fixed-unavailable page with ZERO records DESPITE the real copied
applications row from the source fixture (the no-misattribution
negative in a real browser) plus the labeled no-op control; the
key detail page labeling the configuration action unavailable
with NO configuration.json link; the unlisted run id and the
unselected `?name=` selector both fixed 404 with the
gate-normalized cache header.

### Docs hygiene

`scripts/check_documentation.py` ->
`DOCUMENTATION_CHECK=OK files=137`.

## Limitations (honest)

- The six non-`validation.json` bodies in the owned-PG and
  browser fixtures are `b"{}"` TEST-ONLY placeholders, NOT
  valid typed outputs for their kinds; they prove
  route/reader/transport and the bounded-read law, not artifact
  content validation or worker publication. `validation.json`
  is REAL 223 `_san_validation_json` output.
- Apply-status: no verified run-id mapping exists between
  copied `catalog_refresh_applications` rows and the display
  run id, so the page is the fixed explicit unavailable state
  (zero records; the table is not read). A bounded follow-on
  order may add a verified projection.
- Key configuration export: the KR metadata projection retains
  only the clone receipt; a faithful version-1 export is
  pending the human's pending choice (bounded follow-on
  sanitizer projection; never a source fallback).
- The configured-file installed browser workflow remains
  objective 225; no installed/company-system verification is
  claimed from the owned synthetic tests.
- This order introduces no schema migration, role, grant,
  configuration, release, deployment or merge; the fake admin
  remains a sanitized display surface with no write authority.

## GitHub state (observed at report time)

PR #383 (`oap/224-demo-web`, base `main`) is OPEN and
MERGEABLE (merge state UNSTABLE until the new head's checks
run); before this push the remote head was the w SELF
`5c169f2659a86dd61cfdfcd64e9fc14e54d50dfc`, and this push
delivers the activation commit
`bdda662b2457db1cd14ea33361e50ad56fb6f2f9`, the
implementation head
`d0c4ab0eadae98d2bff06c45a0f2982c7ad18262`, and this
report-only SELF as the new head.

Hosted checks for the new head were NOT observed at report
time; root independently awaits/rechecks final-head gates after
the response.

## Protected untracked files (untouched, unread, unstaged)

- `CODEX-SESSIONS.md` SHA256
  `5ae1d77c17a367e86ef725a8f9d25aba3464b24f22fba77fd2808377f8c7feda`
- `codex.sh` SHA256
  `66eda80258f6a4f13b88a9fe2ad5a69b9e7df226a4e503f57b35b6c6f03e1247`
- `uv.lock` SHA256
  `d3d0e80db77da56e41795c619875ac14b5d25427d5169a7c9d2c8dee45b3b5b6`

(all three match the order's recorded SHAs; `git status`
shows them as the only untracked files and they were never
staged.)

## Objective status

224-x is COMPLETE as published: the w-defect repairs (false
key-configuration export safely disabled, calibration
selector, route choices/headers) and the four remaining
catalog-read GET shapes are implemented, tested (focused
units, byte oracle, owned-PG two-copy, real Chromium,
Ruff/docs hygiene) and documented. The immutable w report was
not edited. One implementation commit + this report-only SELF
on PR #383; no merge. The exact two-byte response `OK` is sent
once and one durable control waiter is rearmed for coding pane
`%9`.
