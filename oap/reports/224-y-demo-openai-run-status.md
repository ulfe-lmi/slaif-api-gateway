# OAP 224-y — Final Report (captured-run apply-status trust + OpenAI-assisted read pages)

## Commit topology

- Activation commit: `e03898a7d0a239e652ad3075b43128442fd97555`
  (tree `cfcfe953265d8436d94138742e806e638eeea359`, sole parent
  `b4716f2ab041e0ab3af1b8987fce671de27c5dd4`, the x SELF) —
  committed the root-authored order and the exact
  `oap/active` = `224-y` pointer unchanged, FIRST.
- Immutable order: `oap/orders/224-y-demo-openai-run-status.md`,
  SHA256
  `befad6d57dcfebe6a002c2f629ec3f401b12b8e7a4fc272ab6b66daf8e94bdcc`.
- Implementation head (sole SELF parent):
  `e64269f79dbfd76caeb0f1a209a685087a59cafd`
  ("224-y: trustworthy captured-run apply status via the shared
  job-id display mapping, the three OpenAI-assisted read pages,
  the six exact review repairs, and the narrow FX
  display-verifier blocker fix"; 14 files, +2272/-196).
- This report: report-only SELF, sole parent = the implementation
  head, sole diff = this file. No merge; PR #383
  (`oap/224-demo-web`, base `main`) left open for strategic
  review.

## Prior objective state (224-x, terminal)

- x order SHA256
  `87ce496bb75f0de854aeb7ee43412e1cca5e07d47ca87d7a012b48540b3d3049`;
  x immutable report `oap/reports/224-x-demo-catalog-final-reads.md`
  SHA256
  `1f50f7c5bed36a32e646fb0d074dba331bbac13dd3e232721b6f101abc98a367`
  (untouched by this objective; corrected only via a dated
  224-y note in `docs/demo-admin.md`, as ordered).
- x report-only SELF `b4716f2ab041e0ab3af1b8987fce671de27c5dd4`
  (sole parent `d0c4ab0eadae98d2bff06c45a0f2982c7ad18262`, tree
  `474076a96c2cdd83055b761909d315613825c825`, sole diff the x
  report). Its exact two-byte response `OK` was delivered; the
  terminal log `/tmp/slaif-oap-224x-response.log` is CLOSED with
  `CONTROL_OK_DELIVERED`/`RESPONSE_OK_EXACT`; it was not repolled
  and x was not re-signaled.
- The three x SELF-head workflow runs were terminal SUCCESS with
  all ten checks SUCCESS (CI run `43583534453` including hosted
  PostgreSQL and real Chromium; CodeQL `43583534489`; CodeQL Code
  Quality `43583529756`).

## Review repairs (order item 0) — six exact threads

Each of the six unresolved Code Quality threads named in the
order is repaired by the implementation commit, behavior
unchanged, so root can resolve the exact threads after code
review:

1. `PRRT_kwDOSLm-qM63cdHp` — unused local
   `_selected_completion` removed from
   `api/demo_admin_route_configuration.py`.
2. `PRRT_kwDOSLm-qM63cdHt` — unused gate constant
   `_CATALOG_RUN_ARTIFACT_NAMES` inlined at its use site.
3. `PRRT_kwDOSLm-qM63cdHv` — unused gate constant
   `_CATALOG_JOB_UPLOAD_NAME_RE` inlined (the literal regex was
   corrected in the same repair: the concatenation produced
   literal `{{32}}` braces, so the inlined form uses the correct
   `{32}` quantifier; the positive/negative gate shapes are
   unit-covered).
4. `PRRT_kwDOSLm-qM63cdHz` — unused gate constant
   `_CATALOG_PROPOSAL_ARTIFACT_NAMES` inlined.
5. `PRRT_kwDOSLm-qM63cdH2` — unused gate constant
   `_CATALOG_PACKAGE_PRESETS` inlined.
6. `PRRT_kwDOSLm-qM63cdH9` — unused gate constant
   `_CATALOG_PACKAGE_FILE_NAMES` inlined.

No broader permissive regex was introduced by the cleanup.

## Shared captured-run identity (order item 1)

Verified from source that the common-input/common-seed premise
holds:

- The 223 file capture
  (`demo_snapshot_files.run_files_job`) seeds the per-copy remap
  with `manifest.job_id.encode("utf-8")`.
- The 222 sanitizer
  (`demo_snapshot_sanitize._sanitize_copy_async`) uses the SAME
  `manifest.job_id.encode("utf-8")` seed.
- The canonical raw run id is the worker's `bundle.run_id`,
  written as BOTH the sealed run directory name (review CLI) and
  the source application row's `run_id` — one value in both
  producers.

`_demo_run_id` now derives the display slug as `"demo-run-"` plus
the first 24 lowercase hex characters of the EXISTING
`remap_str_id(seed, run_id)` output — the same keyed `b"s"`
digest domain the sanitizer applies to copied
`catalog_refresh_applications.run_id` values. The URL shape,
per-copy unlinkability and zero raw-ID/seed exposure are
preserved; the mapping is a deterministic DISPLAY correlation
only — never identity, authorization or apply authority.
`tests/unit/test_demo_snapshot_files.py::test_demo_run_id_mapping_law_224y`
proves the shared-seed premise directly.

## Apply-status read law (order item 2)

`GET /admin/operations/catalog/runs/{run-id}/apply-status`
(query-free; exact canonical shape gate-admitted):

- ONE SELECT-only/read-only transaction on the gate's SAME
  request-local copy session, with the in-transaction
  `current_database()` / `transaction_read_only` recheck FIRST.
- The run must exist in THIS copy via the SAME closed seven-file
  metadata-only inventory as the 224-m run detail (no body
  transfer): missing run -> fixed 404; partial run,
  kind-mismatched leaf, or nonfinite/unrepresentable
  `captured_at` -> fixed safe 503 (corrupt-existing is never
  "not found", never a silent missing time).
- Copied `catalog_refresh_applications` rows are queried ONLY by
  the derived 96-bit prefix with bound parameters and a BOUND
  `LIMIT 5` (bound 4 + one over-bound probe). Any malformed row
  (mode not in `{bootstrap, refresh}`, outcome not `committed`,
  actor not sanitized-string grammar, bool/negative counts,
  non-UUID non-null admin), more than ONE distinct full remapped
  run id, or an over-bound result -> fixed safe 503.
- `admin_user_id` is NULLABLE (CLI-applied records may carry no
  admin identity); NULL renders `n/a`. A classifier FAILURE on a
  non-null admin value is a distinct error sentinel -> the fixed
  safe 503 (never an indistinguishable `n/a`, never a 500).
- For a unique full remapped run id, ONLY that id's typed, safe
  committed records are displayed: copied counts, the record's
  OWN historical event times (labeled record-event-time; the DB
  snapshot timestamp itself is not displayed) and the separately
  labeled file capture time (worker snapshot; may differ). NO
  bundle/plan/receipt-HMAC identity values are shown.
- A no-match is UNKNOWN/UNAVAILABLE — "no copied committed
  application record matches ... NOT a statement that the run was
  never applied" — which also keeps pre-upgrade active copies
  (old slug domain, no joinable value) safely unknown.
- Whole-page incoming-alias law: every dynamic displayed value
  (path slug, canonical/display time forms, raw and grouped count
  forms, every record string) equal to a known incoming
  bearer/cookie/session/proxy alias makes the WHOLE page the
  fixed safe refusal; a classifier error is the fixed safe
  refusal. No source run id, seed, seal/HMAC receipt authority,
  provider credential, copy locator or unbounded free text is
  shown.
- No source DB, live custody, seal key, network or DML; visible
  operational controls are labeled quiet no-ops; normal
  authoritative admin status unchanged.

## OpenAI-assisted read pages (order item 3)

- ONLY query-free GET `/admin/openai-assisted`,
  `/admin/openai-assisted/pricing`, `/admin/openai-assisted/routes`
  are admitted by the central gate before any copy access; exact
  near misses are denied (404); all proposal POSTs/unsafe methods
  are pre-body quiet 204 no-ops with the body never parsed,
  without generation, audit, source DB/file, network or provider
  access.
- The index performs NO copy read: frozen demo display framing,
  working navigation, and the packaged-reference model default,
  explicitly labeled as such (the 223 process-configuration leaf
  is numeric-only and does NOT record the source proposal model).
  Fixed official public source URL constants only — no live call,
  no discovery key/environment, no ambient settings or provider
  access.
- Pricing/routes forms are copy-backed: ONE transaction on the
  gate's request-local verified SELECT-only copy session with the
  in-transaction recheck, then the bounded existing
  `load_choices` seam (routes model options are copied model
  data; scope/currency/preset options are fixed product
  vocabularies, stated as such). A failed copy query is the fixed
  safe 503 (never a silent empty dropdown); choice values equal
  to known incoming aliases are withheld before render.
- Demo branches replace every normal "this calls OpenAI" /
  discovery-key-in-use / generated-success / runnable-proposal
  claim with truthful frozen/no-call/no-op wording while keeping
  inputs and hints ergonomic; form submission is a server-enforced
  pre-body quiet 204 no-op. Normal admin HTML and behavior remain
  byte-identical (byte oracle, below).

## FX display-verifier repair (demonstrated worker blocker)

The first real catalog-configured worker copy (owned-PG copy C)
exposed a pre-existing gap in the 223 file verifier:
`_JSON_DOC_VALIDATORS` omitted `KIND_FX_JSON`, so the sealed run's
`fx-proposal.json` leaf failed post-write verification with
`FILES_VERIFY_FAILED` ("A display leaf kind is unverifiable") and
the worker request failed closed without publishing. Confirmed
directly: `_verify_leaf_policy(KIND_FX_JSON, <valid sanitized
bytes>, None)` refused before the repair. The repair, authorized
as the demonstrated blocker within the existing file verifier, is
a NARROW typed display validator (`_v_doc_fx_json` plus
`_v_fx_rows`/`_v_currency`/`_v_positive_decimal`/`_v_opt_iso`)
matching the closed `_san_fx_json` output exactly: schema/kind
constants, the closed per-fact field set (three-letter currency
codes, positive finite decimal-text rate, ISO timestamps,
nullable `valid_until`), plus the source invariants the
sanitizer preserves (distinct base/quote currencies,
`valid_until` after `valid_from`). No source capture, sanitizer,
or verification bypass changed; any nonconforming leaf still
fails closed. The fresh-bundle vs tracked-fixture comparison did
not show a bundle-specific rejection — the same refusal occurs
for the proven tracked fixture's leaf — confirming the missing
validator as the sole cause.

## Verification evidence (all local/owned; hosted checks NOT observed at report time)

### Focused mocked units (green)

- `tests/unit/test_demo_web.py`: full file 296 passed (counted
  from source; 19 of them the new `test_y_` tests: 12
  apply-status — mapping-law premise, positive unique record,
  null-admin `n/a`, ambiguous prefix 503, over-bound 503,
  malformed row 503, alias withheld, path-slug / datetime-shaped
  / numeric-count incoming-alias cookie canaries 503, non-null
  admin classifier-error 503, bad `captured_at` 503 — and 7
  OpenAI-page: exact gate shapes, unsafe-method quiet 204 with
  the body unparsed, index positive with no copy read,
  copy-backed pricing/routes choices, choice alias withholding,
  copy failure 503).
- `tests/unit/test_demo_snapshot_files.py`: full file 76
  passed, including the 3 new tests
  (`test_demo_run_id_mapping_law_224y` and the two
  `test_fx_json_display_verifier_*` cases, the second covering
  17 adversarial mutations).
- The directly affected inventory files (catalog index,
  design/usability) and Ruff on every touched file are clean;
  no unchanged suite was rerun.

### Byte-identity oracle (normal rendering)

The bounded Jinja render comparison of every modified template
against the activation-commit originals under representative
normal-admin contexts reports zero failures
(`FAILURES: 0`); normal admin output is byte-identical.

### Owned PostgreSQL 16 (three simultaneous disposable copies)

Command (real pytest exit captured, `pipefail` in effect):

```
PATH=/tmp/pg16/bin:$PATH \
DEMO_SAN_TEST_SOURCE_URL=postgresql+asyncpg://test:test@127.0.0.1:54351/slaif_gateway_test \
DEMO_SAN_TEST_TARGET_URL=postgresql+asyncpg://test:test@127.0.0.1:54352/postgres \
.venv/bin/python -m pytest tests/integration/test_demo_web_admin_gate_postgres.py -p no:warnings -q
```

Result as observed: BOTH tests passed, pytest exit 0
(`test_e2e_admin_gate_two_sessions_distinct_copies` and
`test_browser_smoke_demo_copy_pages`). The fixture adds a THIRD
owned worker-processed copy (C) — the ONLY catalog-configured
worker — using the tracked sealed first-install fixture
(`tests/fixtures/catalog_refresh/bundle-first-install.json`,
exact raw run id `fixture-first-install-001`, synthetic, never
live-applied) reviewed against an owned seal key in a fresh
0700 catalog root (seal key outside it), plus ONE source
`catalog_refresh_applications` row (NULL admin, typed values,
exact-id cleanup finalizer). It proves:

- the POSITIVE worker-published mapping: the slug is discovered
  from C's OWN leaves; the copied application row is joined by
  the SAME 96-bit prefix the handler uses (NULL admin survived
  the copy); the positive page renders copied counts,
  record-event-time labels, `n/a` admin, the sealed-identity
  non-display note, and exposes no source run id, source DB,
  custody path, worker credential, target name, catalog root or
  seal key;
- cross-copy isolation: a NEW client carrying the still-valid
  B token gets a true 404 for C's slug (B's unconfigured copy
  holds no catalog run); C gets 404 for A's test-only x run; A's
  post-logout request is recorded ONLY as the session-revocation
  303 already proven in the sign-out section — NOT claimed as an
  A copy 404 after logout;
- test-only C negatives (exact-id cleaned in a finally):
  ambiguous second full id sharing the prefix -> 503, truncated
  prefix -> 503, over-bound five rows -> 503, and the
  incoming-alias cookie canary -> 503 with no echo, each on the
  fixed refusal wire law;
- invariance: source and all three copies' public-table counts
  unchanged after the whole read/POST/logout cycle.

The earlier fresh-bundle fixture variant
(`_fresh_first_install_bundle`) failed at the SAME verifier gap
described above; with the narrow FX validator in place the
tracked fixture is used for the committed test (proven artifact,
per strategic guidance), and both bundle shapes pass the direct
capture/verification law in local diagnostics.

### Real Chromium (owned browser fixture)

Within the same owned-PG run: the browser traverses the three
OpenAI-assisted pages (frozen display framing, packaged-reference
label, "source proposal-model setting was not captured", fixed
official URLs, working hrefs, no live-call / Admin-discovery /
environment-variable claim), performs a REAL pricing-form
submission through the browser returning the pre-body quiet 204,
and the near-miss 404; the 224-x browser evidence (non-empty
catalog index with the seven `?name=` hrefs, run detail with the
seven direct artifact hrefs, real authenticated-context download
with the forced attachment wire law, collect page, the UNKNOWN
apply-status for the test-only x run — "no copied committed
application record matches", never "not applied"/"rolled back" —
plus the no-op control, and key-config unavailability) is
preserved.

### Docs hygiene

`scripts/check_documentation.py` -> `DOCUMENTATION_CHECK=OK
files=137`. `docs/demo-admin.md` gains the dated 224-y
correction note under the 224-x apply-status subsection (the x
report itself is immutable) and the new final 224-y section
(mapping law, read law, OpenAI pages, FX repair, six thread
repairs, limits, evidence).

## Limitations (honest)

- The positive run-mapping proof starts from a CLI-reviewed
  sealed tracked fixture plus a synthetic source application
  row: it proves the REAL worker/sanitizer mapping and transport
  end to end, not a live operator apply.
- Pre-upgrade active copies (created before the slug-domain
  change) remain in the fixed UNKNOWN/UNAVAILABLE state; the
  handler never guesses and adds no mapping table.
- The key configuration export remains the fixed safe 503 (the
  pending human choice for a verified sanitized projection is
  unchanged); the 224-x direct artifact downloads and wire law
  are unchanged.
- The FX validator is a display-side re-proof of the sanitized
  output; it changes no capture, no sanitizer, and no
  fail-closed path.
- The A-direction post-logout 303 is session-revocation evidence
  only; cross-copy isolation for the logged-out copy is asserted
  through the still-authenticated B copy and C's view.
- The six test-only C rows and the source application row are
  disposable fixture data with exact-id cleanup; they are not
  evidence of production apply activity.
- Hosted CI is NOT observed at report time (nothing new pushed
  at evidence capture); root independently awaits/rechecks the
  final-head gates after this response.
- No real installed/company tests exist for this objective.

## GitHub state (observed at report time)

- PR #383 (`oap/224-demo-web`, base `main`) uniquely
  OPEN/MERGEABLE; head was the x SELF
  `b4716f2ab041e0ab3af1b8987fce671de27c5dd4` before this
  objective's push and becomes the y SELF (this commit) after it.
- Remote `main` `d3762e51c9a323dee6b728c4a45fa21b0bffae86`
  (unchanged by this objective); unrelated open PRs #379/#319
  untouched; only release `v0.1.0-rc.1`; `protect main` ruleset
  active.
- The six review threads listed above are the ONLY pending code
  cleanups and are fixed in the implementation commit for root's
  verification.

## Protected untracked files (untouched, unread, unstaged)

- `CODEX-SESSIONS.md` SHA256
  `5ae1d77c17a367e86ef725a8f9d25aba3464b24f22fba77fd2808377f8c7feda`
- `codex.sh` SHA256
  `66eda80258f6a4f13b88a9fe2ad5a69b9e7df226a4e503f57b35b6c6f03e1247`
- `uv.lock` SHA256
  `d3d0e80db77da56e41795c619875ac14b5d25427d5169a7c9d2c8dee45b3b5b6`

All three verified unchanged against the activation order's
recorded SHAs; final `git status --short` shows exactly these
three untracked entries and nothing else.

## Objective status

224-y is complete within its order: six exact review repairs,
the shared captured-run display mapping with a trustworthy
positive historical apply status (and UNKNOWN for pre-upgrade /
no-match), the three OpenAI-assisted read pages, the narrow FX
display-verifier blocker fix, docs and evidence as recorded
above. No merge, no auto-merge, no helper agent. The exact
two-byte response `OK` is sent ONCE after this SELF is pushed;
one durable control waiter is reattached to the existing coding
pane `%9`. Root independently reviews code/report, resolves only
verified review threads, awaits the exact final-head checks, and
continues Objective 224 on the same PR (224-z final audit if y is
accepted).
