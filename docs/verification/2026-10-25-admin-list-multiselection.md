# 2026-10-25 Objective 195-a admin multi-value list filters verification

Recorded 2026-10-25 (UTC) in the OAP coding worktree for objective 195
(`oap/195-list-filter-multiselection`, base `origin/main`
`c5437bef6811cdfad2b0be3c273e6071572cbaa3`). This record describes what
the focused runs below actually proved. It is not a full-matrix rerun,
not a release/production claim, and it does not establish that every
195 merge gate is complete (final-head CI is gated by root; see
"Outstanding" below).

## Scope under test (195-a)

- OR-within / AND-across multi-value filters on the eleven GET admin
  list pages (keys, owners, institutions, cohorts, providers, routes,
  pricing, fx, usage, audit, email deliveries) plus the usage/audit CSV
  exports; legacy one-value links and scalar service/CLI contracts
  unchanged (one-value requests reach the service layers as the exact
  legacy scalar call).
- Explicit bounds before any use, 400 on excess with fixed safe
  messages that never echo values: 20 unique accepted values per field
  (canonical for UUID fields), 100 submitted values (raw, incremental),
  1024 characters per value; one invalid UUID member rejects the whole
  field.
- The multi predicate runs in SQL BEFORE `LIMIT`/`OFFSET` (exact
  pagination over the matching set); per-family repository
  normalization preserved (scalar `==` shape for single values, bounded
  `IN` for many).
- Multi-value record-choice controls: chips below the integrated box,
  repeated hidden fields (or newline-serialized), dependent pickers send
  every accepted parent value, and label-only async refresh of
  selections the server re-hydrates (no value change, no `rc-change`,
  no input text/focus disturbance; unknown/manual values keep their
  fallback).
- Lookup hydration repairs proven in this objective: `audit_target`
  selected ids hydrate with the SAME parent constraint as the initial
  query (an out-of-scope selection never becomes an eligible choice)
  and one choice per selected id is guaranteed IN SQL before the
  100-limit (per-id ranking, not Python dedup after the limit);
  `one_time_secret` selected ids keep their public lifecycle label
  (status + purpose; never the secret value/ciphertext).
- No database migration, no dependency/schema/adapter change.

## Environment

- Python: `/tmp/slaif192-coding-venv` (project dev venv),
  `PYTHONPATH=app`.
- Database: the qualified `owned_pg_url` fixture (fresh labeled,
  127.0.0.1-loopback, tmpfs PostgreSQL 16 per test module; ownership
  inspected before use; cleanup removes only the exact created
  container). No ambient `DATABASE_URL`, no foreign containers.
- Browser: native Playwright Chromium. Synthetic fictional data only —
  no real provider/model/email, no production DB/SSH/deploy.

## Layer 1 — unit (no DB; pure helpers / mocked ASGI / fake sessions)

- `tests/unit/test_admin_list_filters_195.py` (new, 28 passed): parser
  bounds and incremental raw counting, scalar contracts,
  `collapse_singleton`, HTTP round-trips (repeated/newline/single/
  400/no-echo), >200-char value round-trip, lookup bounds (no-selected
  all kinds, 100/1025/303 boundaries), `_target_type_values`
  full-value preservation, `_safe_filter_metadata` JSON-safety.
- `tests/unit/test_admin_record_choices.py` (68 passed, incl. 8 new
  195-a hydration regressions on fake sessions): `audit_target`
  selected hydration (authoritative label, cap + eviction protection,
  requested selection order, one-choice-per-id idempotence,
  parent-scope consistency incl. multi-parent OR, minimal-column
  statements) and `one_time_secret` lifecycle-label hydration
  (incl. unknown-id plain fallback, in-batch selection, and the
  never-select-encrypted-payload/nonce column guard).
- Affected legacy unit set (11 modules: keys/activity routes,
  catalog/records/activity/keys dashboard services, csv exports,
  export service, record choices, csrf, assets): 0 failures (see
  JUnit `unit-195-affected`).
- CI error-copy compatibility repair (after the first
  implementation-head CI run, which completed 8/10 with the two
  failures being pre-195 stale oracles expecting the generic
  "Invalid filter." summary): the eleven list-filter 400 render
  sites in `api/admin.py` now render the stable pre-195
  "Invalid filter." summary FIRST, then the fixed per-field detail
  (fixed parameter name + limit only; still never echoes submitted
  values; same 400/whole-field rejection). The two affected legacy
  oracles were NOT edited; both re-passed locally — the unit node
  plus the new 195 filter unit module (32 passed, JUnit
  `unit-cifix-1`, real exit 0) and the one existing browser design
  node (1 passed, JUnit `browser-cifix-1`, real exit 0).

Commands captured real pytest exits via `PIPESTATUS[0]` alongside the
JUnit files in `/tmp/slaif195/`.

## Layer 2 — real PostgreSQL 16 (owned fixture; no HTTP/auth)

`tests/integration/test_admin_list_multiselection_postgres.py` (13
passed): two-cohort union with the third cohort excluded and status
AND; duplicate-free owner membership across two cohorts (ANY/EXISTS,
no fan-out); the 64-row matching-set pagination oracle
(offset 45 -> full 10-row page of ONLY matching cohorts, 60 -> 4,
64 -> empty); usage provider multi LIKE semantics; audit multi-parent
OR scope before the 100-choice limit incl. a 252-char parent preserved
in full; the two R5 selected-hydration regressions (out-of-scope
selected target never hydrated under an `owner` parent scope; 6
selected ids x 20 eligible parent types = 120 groups all keep their
labels, proving per-id reduction precedes the limit); usage/audit CSV
multi scope with JSON-safe metadata; and real authenticated HTTP
uvicorn nodes: repeated-parameter AND newline-fallback unions with
SCOPED data-row identity (rows from both selected cohorts, NO gamma
row — options may legitimately list gamma), legacy one-value, 400
no-echo, no-selected lookup, and the explicit 100-value/1024-char
lookup bounds.

The root-reproduced R5 scope/limit failures
(`/tmp/slaif195-root/test_audit_hydration_scope_pg.py`, actual PG16,
2/2 failing before the fix) were re-run against the corrected service:
2/2 passed (JUnit `root-probe-recheck`).

## Layer 3 — real authenticated admin + Chromium

- `tests/browser/test_admin_list_multiselection.py` (new, 4 passed):
  two-cohort union through ACTUAL menu clicks (rows from both cohorts,
  third cohort excluded, status AND, duplicate-value guard, chip
  removal + "Clear filters" GET round-trip, custom Rows limit 3 with
  ordinals 1..3 and the preserved explicit option); label-only async
  refresh — two VALID-but-UNKNOWN cohort UUIDs render as raw-UUID
  fallback chips and a `selected=` lookup response (mocked, delivering
  exactly what the real fetch returns for resolvable ids) refreshes the
  chip labels in place with hidden values, order, input text, and
  focus untouched; resolvable OLDEST cohorts — the UNFILTERED page's
  embedded latest-100 batch is asserted to EXCLUDE both first
  (independent older-status proof from the real server), THEN the
  selected URL's embedded options INCLUDE both with their
  authoritative labels (page-load hydration), chips carry the
  friendly names from load, rows are exact, and both remain reachable
  by name through the real server search; and chips wrap down at
  narrow 390px with no horizontal overflow. Screenshots:
  `/tmp/slaif195/screenshots/keys-two-cohorts-desktop-1600.png`,
  `keys-two-cohorts-narrow-390.png`,
  `keys-chip-async-label-recovery.png`,
  `keys-selected-older-after-search.png`.
- `tests/browser/test_admin_usability.py` (10 passed) and
  `tests/browser/test_admin_visual_screenshots.py` (9 passed,
  193/194 visual pins re-proven: dashboard groups/heading, keys list
  A2 typography/geometry at all four viewports, and the grow-down
  proof with the six-control keys bar keeping the top-aligned Filter
  button fixed while chips push the table down).
- Final-CSS re-runs (after the keys filter bar CSS reached its final
  state: desktop six-track rule, 960px five-track rule, and the
  640px single-column override whose selector list explicitly
  includes `.filter-bar.keys-filters` so the higher-specificity
  six-track rule is overridden on small screens — controls stay
  42px, top-aligned): the new 4-test module re-ran to 4 passed
  (JUnit `browser-195-new4`) and the five affected keys visual nodes
  (four `test_keys_list_visual` viewports + `test_keys_chip_grow_down`)
  re-ran to 5 passed (JUnit `browser-195-visual4`); the recaptured
  screenshots replace the pre-final-CSS captures. Earlier overlapping
  runs with transient failures (`browser-195-adapted`,
  `browser-195-new2`, `browser-195-visual2`) are superseded and are
  not counted as new cases.

Layer honesty: the async label-refresh browser test MOCKS the lookup
response (the page itself only hydrates resolvable values); the
older-cohort proof uses the real server. No full local all-layer or
128-worker matrix run; final-head CI supplies the broad matrix.

## Documentation

- `docs/admin-usability.md`: multi-value list filter semantics
  (OR/AND, bounds, scalar service/CLI distinction, CSV exports,
  chips/labels, Rows-limit vs total, no migration, key-policy
  distinction) and the audit-target / one-time-secret hydration
  vocabularies, including the parent-scope precision: the selected
  parent scope constrains which selected ids are *eligible* choices
  (an id with no event under any selected parent type cannot be
  resolved from that scoped source and may keep a plain-id fallback
  chip), while its accepted selection value and chip are retained —
  the scope never silently evicts an accepted selection.
- This record + `docs/verification/README.md` index entry.

## Outstanding

- The first implementation head's CI run completed 8/10 successful;
  the two failures were exactly the stale "Invalid filter." oracles
  above and are repaired by the error-copy compatibility commit on
  this same branch/PR. CI at the subsequent heads (including the
  report publication commit) is the remaining gate.
- Final-head CI (all checks) is gated by root on the report
  publication commit; this record does not claim CI green.
- No merge, no release, no production/security/compliance claim.
