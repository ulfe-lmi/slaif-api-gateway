# OAP Objective 195-a — final report: multi-value admin list filters with coherent selected chips

Work order: `oap/orders/195-a-list-filter-multiselection.md`
(strategic-authored, committed unchanged on the objective branch with
`oap/active` = `195-a`; order sha256
`c8ab9ae9c4da40aed47118cd8e37b77fa4a64f3f295694769fb5cc32a661b47a`).
Branch: `oap/195-list-filter-multiselection`, base `main`
`c5437bef6811cdfad2b0be3c273e6071572cbaa3` (PR #346 merge; remote
`main` verified at that base at publication).
PR mode: CREATE_NEW_PR (Objective 195 = exactly one new PR, #348,
https://github.com/ulfe-lmi/slaif-api-gateway/pull/348).
The coding agent never merges; no auto-merge is enabled; root reviews
independently and guard-merges.

Implementation head SHA: e47c3a9810eddf9fbdbe53ac3e74b78ca31d6b2b
 (initial implementation head:
`a4434159838b97b36fefd3e6eacf075851a9a97d`, first commit below)
Report publication commit: SELF

## Implementation commits (branch order)

1. `a4434159838b97b36fefd3e6eacf075851a9a97d` — "feat: support multiple
   selections in admin list filters": all implementation, docs, and
   tests together with the unchanged activated order and `oap/active`
   (44 files).
2. `9f9a7b1945bca0133834f5df11422a25a4a0fb96` — "Review fixes:
   unfiltered older-batch premise, final-CSS rerun evidence,
   parent-scope doc precision (195-a)" (3 files: one browser test,
   two docs; no product code).
3. `e47c3a9810eddf9fbdbe53ac3e74b78ca31d6b2b` — "Keep stable
   'Invalid filter.' 400 summary alongside fixed per-field detail
   (195-a)" (2 files: `api/admin.py` render sites + verification
   record; no validation/permission/schema change).

## Process honesty

This report closes the SAME continuously activated 195-a execution:
the original strategic control `OK` was delivered and consumed exactly
once (no re-signal, no new control reader, no profile/model/effort
change, no 195-b/196 activation). Strategic review notes received
during the execution were applied within the same bounded scope:
validator/predicate edge cases, the bounded-split detail, the
scalar-shape regression, the no-selection boundary + full parent-value
preservation, the R5 selected-label gaps with precise evidence, the
root-reproduced R5 scope/limit PostgreSQL regressions, the browser
older-record premise + final-CSS re-run evidence + doc precision, and
the CI stale-oracle diagnosis (see "CI status"). All WIP, the
activated order/active bytes, and the protected unrelated untracked
artifacts (`CODEX-SESSIONS.md`, `codex.sh`; gitignored `.codex/` and
`.local-provider-catalog/`) were preserved untouched.

## What changed

1. **Multi-value list filters.** The eleven GET admin list pages
   (keys, owners, institutions, cohorts, providers, routes, pricing,
   fx, usage, audit, email deliveries) plus the usage/audit CSV
   exports accept repeatable filter values: OR within a field, AND
   across fields. The multi predicate runs in SQL BEFORE
   `LIMIT`/`OFFSET` (exact pagination over the matching set);
   per-family repository normalization is preserved (scalar `==`
   shape for one value, bounded `IN` for many).
2. **Explicit bounds, safe 400.** Before any use: 20 unique accepted
   values per field (canonical for UUID fields), 100 submitted values
   (raw, incremental — repeats, blanks, newline-fallback members),
   1024 characters per value; one invalid UUID member rejects the
   WHOLE field. Fixed safe messages name only the fixed parameter and
   the limits — never an echoed value. All eleven list-filter 400
   render sites keep the stable pre-195 "Invalid filter." summary
   first, followed by the fixed per-field detail (commit 3 above).
3. **Scalar contract unchanged.** Legacy one-value links, service
   layers, and CLI are untouched: one-value requests reach the
   services as the exact legacy scalar call (`collapse_singleton`).
4. **Multi-value record-choice controls.** Chips below the
   integrated box (wrap down at narrow widths, no horizontal
   overflow); repeated hidden fields (or newline serialization);
   dependent pickers send EVERY accepted parent value (the
   `depValue` first-value-only read is fixed); label-only async
   refresh of selections the server re-hydrates (`renderChips()`
   extraction: no hidden-field rewrite, no `rc-change`, no input
   text/focus/caret disturbance; unknown/manual values keep their
   fallback chips).
5. **Lookup hydration repairs (R5).** `audit_target`: selected ids
   hydrate under the SAME parent `target_type` constraint as the
   initial query (an out-of-scope selection never becomes an
   eligible choice; its accepted chip/value is retained with a
   plain-id fallback), and one choice per selected id is guaranteed
   IN SQL before the 100-choice limit (per-id ranking over grouped
   events; only rank 1 reaches the limit); requested selection order
   preserved; minimal columns. `one_time_secret`: selected ids keep
   their public lifecycle label (id prefix + status; purpose
   sub-label) and the encrypted payload/nonce are never selected.
6. **Keys filter bar layout.** The bar carries six controls
   (institution_id added): desktop six-track single row, 960px
   five-track, 640px single-column override whose selector list
   explicitly includes `.filter-bar.keys-filters` (specificity fix),
   controls stay 42px and top-aligned; chips grow DOWN and the TABLE
   moves down while the Filter button stays fixed (193-a contract).
7. **Docs.** `docs/admin-usability.md` (multi-value semantics,
   bounds, scalar distinction, CSV exports, chips/labels, Rows-limit
   vs total, no migration, key-policy distinction, audit-target /
   one-time-secret vocabularies with parent-scope precision) and the
   verification record + index entry.

## Explicit non-changes

No schema, migration, model, quota/accounting, provider/adapter,
Responses-compatibility, transport, content-capture, or dependency
change. Auth/session/CSRF semantics unchanged. No production
DB/SSH/deploy/release/tag; no real provider/model/email/credential
use; all test data synthetic and fictional (key hints neutral
`synthetic-hint-*`; the only `sk-slaif-` strings are the app's
configured `GATEWAY_KEY_PREFIX` settings and the product's existing
display-prefix rendering of `public_key_id`).

## Verification (this objective; focused; ALL synthetic data)

Environment: venv `/tmp/slaif192-coding-venv`, `PYTHONPATH=app`,
PostgreSQL only through the `owned_pg_url` fixture (fresh
owner-labeled, 127.0.0.1-loopback, tmpfs PostgreSQL 16 container per
test module; no ambient `DATABASE_URL`, no foreign containers),
native Playwright Chromium, real pytest exits via `PIPESTATUS[0]`,
JUnit XML under `/tmp/slaif195/`.

- **Unit (no DB):** new `tests/unit/test_admin_list_filters_195.py`
  (28) + `tests/unit/test_admin_record_choices.py` (68, incl. 8 new
  R5 hydration regressions on fake sessions) = **96 passed**
  (`unit-195-final.xml`, exit 0); affected legacy 11 modules =
  **147 passed** (`unit-195-affected.xml`, exit 0).
- **Real PostgreSQL 16 (no HTTP/auth):**
  `tests/integration/test_admin_list_multiselection_postgres.py` =
  **13 passed** (`integration-195-scope3.xml`, exit 0), incl. the two
  R5 hydration regressions and real authenticated-HTTP uvicorn nodes
  (repeated/newline unions with SCOPED row identity, legacy
  one-value, 400 no-echo, lookup bounds). The root-reproduced R5
  scope/limit failures (actual PG16) went 2/2 failing before the fix
  to **2/2 passed** after it (`root-probe-recheck.xml`, exit 0).
- **Real authenticated admin + Chromium:** new
  `tests/browser/test_admin_list_multiselection.py` = **4 passed**
  AFTER the final CSS (`browser-195-new4.xml`, exit 0): two-cohort
  union via ACTUAL clicks (third cohort excluded, status AND,
  duplicate guard, chip removal, Clear-filters round-trip, custom
  Rows 3 with ordinals), label-only async refresh (mocked lookup
  response delivering exactly what the real fetch returns for
  resolvable ids; hidden values/order/input/focus untouched), the
  OLDER-cohort proof — UNFILTERED page first (latest-100 batch
  EXCLUDES both), THEN the selected URL (embedded options INCLUDE
  both with authoritative labels, friendly chips from load, exact
  rows, real server search) — and narrow-390 wrap-down. Screenshots
  recaptured after final CSS at `/tmp/slaif195/screenshots/`
  (visually verified, matching the approved 193/194 language).
  `test_admin_visual_screenshots.py` = **9 passed**
  (`browser-195-visual3.xml`) plus the five affected keys visual
  nodes re-run = **5 passed** (`browser-195-visual4.xml`);
  `test_admin_usability.py` = **10 passed** (`browser-195-usab2.xml`).
  All browser exits 0.
- **Static:** `ruff check app tests` clean; `git diff --check`
  clean; `scripts/check_documentation.py` OK (120 files); OAP
  governance unit suite 9 passed.
- **CI-failure reproduction (after the copy fix):** the affected
  unit node + the new 195 filter module = **32 passed**
  (`unit-cifix-1.xml`, exit 0) and the one existing browser design
  node = **1 passed** (`browser-cifix-1.xml`, exit 0).

Honest layer separation: unit evidence (pure helpers / mocked ASGI /
fake sessions) does not prove browser behavior; the async label
refresh browser test MOCKS the lookup HTTP (the page itself only
hydrates resolvable values); the unfiltered/older, search, and
chip-lifecycle proofs use the real PG + real server. Root's separate
native-widget probe (mocked HTTP) is not a full-gateway/PG
qualification and is not claimed as such. No full local matrix or
128-worker run (test economy; routine CI supplies the broad matrix).

## CI status at publication (truthful timeline)

| Head | Run (UTC) | Result |
| --- | --- | --- |
| `a443415` (initial implementation head) | 22:01:28 | 8/10 success; `Unit, lint, and migration head` + `Playwright browser smoke` FAILED |
| `9f9a7b1` (review fixes, tests/docs only) | 22:11:13 | 8/10 success; the SAME two jobs failed (product copy fix not yet in) |
| `e47c3a9` (error-copy compatibility fix) | 22:20:22 | queued/in_progress at publication |
| report commit (SELF, below) | pending | triggers the final-head run |

Both failures were diagnosed from the individual job logs (unit job
121304235953, browser job 121304235923) as ONE failure each —
pre-195 stale oracles expecting the generic "Invalid filter."
summary (`test_admin_records_routes.py::
test_admin_record_list_invalid_uuid_filters_are_safe`;
`test_admin_slaif_design.py::
test_design_error_surfaces_owner_form_flow_and_v1_contract`). The
bounded compatibility fix (commit 3) restores that stable summary
alongside the new fixed detail without echoing values; both oracles
were preserved unedited and both re-passed locally. Checks for the
report-containing head are PENDING at the moment this report is
published and remain the strategic/root final-head gate; no merge
gates are claimed complete by this report.

## Honest limits / skips

- No full local unit/browser/all-layer matrix or 128-worker sharded
  run; routine CI supplies the broad matrix at the PR head.
- Native Chromium on this machine only; no other browser/mobile
  claim. Screenshot/review directories (`/tmp/slaif195/`) are local
  review artifacts, not repository content.
- The async label-refresh proof uses a mocked lookup response by
  design (the page cannot resolve fabricated unknown UUIDs); the
  real-server proofs cover resolvable values.

## Docs impact statement

Updated: `docs/admin-usability.md` (multi-value list filter law,
audit-target / one-time-secret hydration vocabularies with
parent-scope precision), `docs/verification/README.md` (index entry).
New: `docs/verification/2026-10-25-admin-list-multiselection.md`
(bounded verification record: exact JUnit counts, layer separation,
real exits, honest skips, CI/publication state). Deployment: no
schema/migration/key change; the standard documented upgrade/restart
path applies; shared CSS/JS asset revision URLs change automatically
because their bytes changed.

## Safe boundary statement

- No schema/migration/model change; no quota/accounting/reservation/
  cost/ledger change; no provider/adapter, Responses-compatibility,
  transport, or content-capture change; no dependency change.
- Auth/session/CSRF semantics unchanged; hidden values, input
  focus, and form state verified preserved across chip operations
  and label refresh (Layer 3). 400 messages never echo submitted
  values (unit + HTTP proofs).
- The coding agent never merged and did not enable auto-merge; PR
  #348 remains open for strategic review, final-head check
  verification, and guarded merge. Objective 195-b is NOT activated
  by this execution.
