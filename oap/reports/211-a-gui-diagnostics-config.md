# OAP Coding-Agent Report — 211-a

## Work order
- Identifier: 211-a
- Work-order file: `oap/orders/211-a-gui-diagnostics-config.md`
  (committed with its EXACT strategic-authored bytes in IMPL; sha256
  `2436b3d48c880c0b1ae6c5f436235cbb121ea943ac0523ba0fc9514fdd59abeb`,
  27,251 bytes)
- `oap/active` pointer: value `211-a` (5 bytes, no trailing newline),
  committed in IMPL
- Numeric objective: 211
- PR mode: CREATE_NEW_PR (PR 367 "Add content-free diagnostics and
  safe process inspection to the admin GUI"; branch
  `oap/211-gui-diagnostics-config`; base main at
  `f71f5799ee4f14ff5774f0e96775f1fd5f02d38e`, the merge commit of PR
  #366 (210))
- Implementation head SHA (literal): `ef41baecdcedd7d03274dba5548f5510a0dd5a1c`
  (one implementation commit on top of base main)
- Report publication commit: SELF (this report is the ONLY difference
  between SELF and IMPL; SELF's first parent is IMPL)

## Status

211-a COMPLETE; FOCUSED LOCAL VERIFICATION GREEN. G08 (content-free
request-failure diagnostics) and G16 (safe process-configuration and
profile inspection) are delivered on the EXISTING qualified
`RequestDiagnosticsService` / repository / schema law and the shared
`configuration_inspection` inspector - no schema, migration,
permission, API-request-acceptance, adapter, profile-data, capture,
provider, accounting, or worker change. CLI `diagnostics` and
`config show` signatures, defaults, and output text are unchanged
(inspected by the focused receipts below). No shared-law exception
was required: every root review finding was a routine correction
within the same order's allowed paths (no second suffix, no new PR).
No deploy, release, tag, or production mutation was performed.

## Delivered (per order requirement)

1. Coherent **Operations** landing area: dashboard "Usage and
   operations" group entry plus base-navigation entry; links Request
   diagnostics and Process configuration; no unimplemented actions
   advertised.
2. **Read-only diagnostics status + ID lookup** using the SAME
   service and typed outcomes as the CLI: recording on/off, retention,
   record cap, write timeout, store availability; ONE searchable
   picker (selection and entry) with bounded latest-100 choices for
   the selected namespace, safe bounded search, older selected-ID
   hydration, and deduplication by submitted value; explicit
   any/gateway/client namespace (native select); typed
   found / ambiguous / not_found / unavailable outcomes; ambiguity
   shows exact match_count, bounded candidates, and
   gateway-namespace disambiguation.
3. **Found view**: recorded correlation, timestamps, endpoint
   template, wire HTTP status SEPARATELY from stream_outcome (an
   HTTP-200 stream failure is visibly labelled a failure), recorded
   reason/error/param, position/count/limit facts, token estimates and
   allowances, route/deployment provenance, authenticated key UUID only
   when recorded; historical client module identity explicitly "Not
   recorded"; no guessed key attribution.
4. **Privacy**: arbitrary typed lookup input is POST-only (never a
   query URL/access log/redirect); the ONE kind-specific picker search
   branch (`diagnostic_request_id`) uses the fixed private POST
   endpoint with body CSRF, no CSRF rotation, and no-store JSON; known
   incoming authentication values are refused on input and withheld
   from choices output, found/detail display, usage-detail display,
   and prefill URLs (existing known-secret discovery; ENV variable
   names literal); all old picker kinds keep their exact GET
   transport.
5. **Bounded audited cleanup** in a labelled disclosure: current
   authentication, CSRF, deliberate confirmation, nonblank bounded
   reason (existing 512-character GUI bound); at most 1,000 expired
   rows per run; delete plus ONE actor/reason/count audit in ONE
   transaction (pre-commit failure, including a late audit write,
   rolls the run back; a lost commit acknowledgement renders the
   outcome unconfirmed for the operator to check in the audit log and
   retention status - never success); retained records, usage,
   audits, replay, key state, and capture files untouched; actual
   deleted count and batch limit shown; CLI `cleanup()` signature and
   default typed output preserved.
6. **Usage-detail entry**: stored client-namespace request ID links
   into the diagnostics lookup (client namespace; no
   gateway-namespace inference; guarded, no unsafe URL construction).
7. **Process configuration page**: EXACT 45-name allowlist with
   value, configured/default source, units/meaning, and restart/
   recreate scope in the **API process** scope (explicit new finite
   scope option in the shared inspector; CLI output/defaults
   unchanged); running package version via existing trusted identity;
   operator-declared deployment revision/provenance with safe bounded
   projection and explicit unavailable state (no Git at request
   time); validated upstream LLM startup-snapshot profiles with their
   exact version/profile/revision/sha256 selectors (empty/unavailable
   explicit); active Codex compatibility DATA snapshot identity only.
   No environment dump, no Settings `model_dump`, no settings writer,
   no request-capture control, no DB/Redis/provider connectivity
   claims.
8. **UX**: SLAIF theme preserved; ordinal-first table with shared
   sorting and raw typed sort keys; labelled keyboard-focusable
   scroll wrappers with correct empty rows; adjacent meaningful
   associated help with unique IDs on actual controls; keyboard and
   no-JS usable through success and validation recovery.

## Exact changed paths (IMPL vs base main `f71f5799`)

- NEW `app/slaif_gateway/api/admin_operations.py` - focused
  operations/diagnostics/process-configuration router (pages,
  POST-backed lookup, private bounded choices POST, bounded audited
  cleanup, configuration/profile inspection).
- `app/slaif_gateway/main.py` - composition only (router included).
- `app/slaif_gateway/api/admin.py` - usage-detail guarded
  client-namespace prefill context + projected displayed ID values;
  no-store headers on private choices refusals.
- `app/slaif_gateway/services/request_diagnostics.py` - namespace-
  aware bounded retained-ID choice read (dedupe before caps, latest-
  100 bound, search budget, selected hydration) and the audited
  cleanup seam (delete + one audit commit in ONE transaction; CLI
  `cleanup()` behavior preserved).
- `app/slaif_gateway/db/repositories/request_diagnostics.py` -
  matching minimal retained-ID queries and the shared atomic
  delete/audit seam (no storage law change).
- `app/slaif_gateway/schemas/request_diagnostics.py` - small
  immutable ID-choice projection only; stored-record/outcome schemas
  unchanged.
- `app/slaif_gateway/services/configuration_inspection.py` - explicit
  finite API-process scope option; 45 allowlist, CLI fields, and CLI
  text unchanged.
- `app/slaif_gateway/web/static/js/record-choices.js` - ONE
  kind-specific bounded POST branch (`diagnostic_request_id`, fixed
  endpoint, live namespace, page CSRF, short debounce); every old
  kind retains its exact GET behavior.
- NEW `app/slaif_gateway/web/templates/operations/index.html`,
  `diagnostics.html`, `process_configuration.html`.
- `app/slaif_gateway/web/templates/dashboard.html` (Usage/operations
  entry), `base.html` (coherent Operations entry),
  `usage/detail.html` (scoped lookup link/form).
- Tests: NEW `tests/unit/test_admin_operations_211.py`,
  `tests/integration/test_admin_operations_211_postgres.py`,
  `tests/browser/test_admin_operations_211.py`; updated affected
  guards `tests/unit/test_admin_activity_routes.py`,
  `tests/unit/test_admin_slaif_design.py`,
  `tests/unit/test_admin_usability_inventory.py` (exact new
  registrations/counts, guards retained).
- Docs: `docs/MISSING_GUI_FUNCTIONALITY.md`, `docs/admin-usability.md`,
  `docs/cli-field-administration.md`, `docs/deployment.md`,
  `docs/security-model.md`, `docs/verification/README.md`,
  `docs/verification/gui-cli-parity.md`.
- Activation: `oap/active`, `oap/orders/211-a-gui-diagnostics-config.md`
  (root-authored bytes committed unchanged).

## Focused evidence (local, /tmp/slaif211)

Final qualifying receipts (all JUnit-parsed; child pytest exit 0
recorded for PG runs; owned containers cleaned - exact owner filter
empty after each):

| Receipt | Result | Scope |
| --- | --- | --- |
| `unit-211a-format-2.xml` | 34 PASS / 0 skip (15.281s) | 211 unit module (found/ambiguity/overflow/not-found/unavailable, wire-200 stream failure, module identity, canaries, inspector API scope, version/revision unavailable) |
| `unit-211a-usage-alias-1.xml` | 4 PASS / 0 skip (4.372s) | usage-detail alias display withholding + prefill guard |
| `unit-211a-usage-alias-2.xml` | 61 PASS / 0 skip (9.528s) | usage rendering + numeric display (incl. activity-template safety) |
| `unit-211a-affected-1.xml` | 173 PASS / 0 skip (18.469s) | affected modules; overlaps 34 (211 unit) + 133 (121 usability-inventory + 12 SLAIF design) plus 6 new main-app-structure cases |
| `guards-2.xml` | 133 PASS / 0 skip (4.959s) | 121 usability-inventory + 12 SLAIF design (the design/inventory half of the 173) |
| `pg-211a-4.xml` | 8 distinct PASS / 0 skip (12.498s) | real owned-PG over authenticated HTTP: pre-admission + HTTP-200-stream records, collision/client ambiguity + namespace disambiguation, expiry, recording-disabled reads, bounded 1,000 cleanup with one real audit and atomic rollback on a late audit failure, native auth/CSRF denials on the new endpoints |
| `pg-211a-5.xml` | 3 PASS / 0 skip (10.388s) | recheck of the three strengthened found-result read cases (overlapping, not additive) |
| `browser-211a-8.xml` | 7 PASS / 0 skip (18.807s) | real Chromium: dashboard -> Operations -> Diagnostics lookup/disambiguation, cleanup with independent DB oracle, private POST credential canary never reaching any URL (real backend response forwarded), namespace change with same-page submit (no CSRF rotation), keyboard/no-JS recovery, legacy GET kinds unchanged, configuration/profile inspection, narrow/desktop captures |
| `unit-211a-final-1.xml` | 35 PASS / 0 skip (11.547s) | CLI configuration-inspection defaults intact + 9 OAP governance tests on the exact order + active + documentation contract drift (run after the doc edits) |
| `unit-211a-unit-2.xml` | 34 PASS / 0 skip (15.485s) | 211 unit module requalified after a scoped lint fix (unused-import removal) |

Receipt sha256 prefixes: format-2 `8df5a104`, usage-alias-1
`82711244`, usage-alias-2 `adc7eee2`, affected-1 `c0a4e1db`, guards-2
`74ac9a87`, pg-4 `9e5ee168`, pg-5 `2e0e83ce`, browser-8 `d24f38bc`,
final-1 `a996f919`, unit-2 `d59c6266`.

Honest chronology (brief): preliminary receipts
(unit-211a-format-1, pg-211a-1/pg-211a-3 fixture-only failures,
browser-211a-1..7) are superseded by the final receipts above. One
preliminary browser run (browser-6) STALLED after one test and was
interrupted under root authorization (single SIGINT to the owned test
PID; the cause was a fixture wait that starved Playwright event
pumping, fixed in the test, not the product); it is recorded as an
interruption, not a pass. All data in every receipt is synthetic
(owned disposable PostgreSQL, synthetic credentials/IDs; no real
provider, Codex, or gateway key; the privacy canary case forwards the
real backend through Playwright route interception and delivers the
unmodified response). Root independently verified and accepted the
native/browser receipts and the desktop/narrow visuals.

## Static and governance checks

- Scoped Ruff over all changed/new Python files: clean (two scoped
  lint fixes in the new test files: a `# noqa: F811` on a pytest
  fixture dependency that intentionally reuses the imported fixture
  name, and one unused-import removal).
- `git diff --check`: clean.
- 9 OAP governance tests on the exact order + active: PASS (in
  `unit-211a-final-1.xml`).
- Documentation contract drift checker: PASS after the doc edits
  (same receipt).
- CLI configuration-inspection compatibility (45 allowlist, CLI
  defaults, CLI text): PASS (same receipt).
- Finite table/wrapper/consumer registrations were inspected before
  publication via the retained usability-inventory / design /
  main-app-structure guards (173 receipt); guards were retained, not
  relaxed.

## CI chronology (per head, actual)

IMPL head `ef41baec` (queried at report publication, 2026-11-01
~09:30 UTC): CodeQL aggregate SUCCESS; Analyze Python SUCCESS;
Analyze (javascript-typescript) SUCCESS; Docker Compose smoke
SUCCESS; Documentation hygiene SUCCESS; IN PROGRESS: Unit, lint, and
migration head; PostgreSQL integration tests; OpenAI-compatible E2E
tests; Playwright browser smoke; CodeQL Analyze (python). Pending and
in-progress checks are NOT reported as passed; they are root-owned
final-head gates. The report-only SELF head's checks run after its
push and are likewise root-owned.

## Privacy invariants

- Diagnostics remain content-free: retained records store only the
  finite safe fact vocabulary; the GUI renders only those same
  projections and never request/response content.
- Known incoming authentication values (including the current admin
  session cookie alias) are refused as lookup input and withheld from
  choices output, found/detail display, usage-detail displayed IDs,
  and prefill URLs; ENV variable NAMES remain literal; no ledger rows
  are mutated.
- Arbitrary typed lookup input is POST-only; private lookup responses
  (including 400/403 refusals and store-unavailable) carry no-store
  headers; picker/lookup/attachments do not rotate a displayed form's
  CSRF.
- Cleanup is bounded (1,000 expired rows/run), audited (one
  actor/reason/count entry, actor from the session), and transactional
  (delete + audit commit together; pre-commit failure rolls back; lost
  commit acknowledgement = outcome unconfirmed, operator checks the
  audit log).
- The admin GUI has NO request-capture control and no diagnostics
  recording switch; operator request capture remains the strict
  local-only CLI facility (security-model boundary unchanged).
- Process configuration renders the exact 45-name allowlist only -
  no environment dump, no connection strings, no credential values,
  no server paths; profile display is startup-snapshot identity only
  (no file contents, no hot reload, no editor).

## Deployment

Deploying 211 is an application upgrade ONLY: rebuild the API/assets
image and recreate/restart the API so the new code runs. No Nginx
change (no new location or allowance) and no database schema
migration; no existing-key, route, or profile change or rotation
follows. Request-capture configuration and diagnostics recording
state are untouched by the upgrade; changing any of those environment
settings (or deployed profile/operator environment files) still
requires the normal env change plus recreate/restart of the affected
containers. NO deployment was performed by this objective. See
`docs/deployment.md`.

## Documentation

Living docs updated (operator navigation, semantics, upgrade and
restart scope; compact proof/limits in the living verification record;
no duplicate inventories): `docs/MISSING_GUI_FUNCTIONALITY.md` (G08/G16
delivered; G09-G15 and G17-G18 remain open; final 219 still
required), `docs/admin-usability.md` (section 12 operator walkthrough),
`docs/verification/gui-cli-parity.md` (211-a living record),
`docs/verification/README.md`, `docs/security-model.md` (admin GUI
consumer note in the diagnostics boundary), `docs/deployment.md`
(upgrade clarification), `docs/cli-field-administration.md` (GUI
counterpart pointer).

Documentation updated: docs/MISSING_GUI_FUNCTIONALITY.md, docs/admin-usability.md, docs/cli-field-administration.md, docs/deployment.md, docs/security-model.md, docs/verification/README.md, docs/verification/gui-cli-parity.md

## Pending and honest limitations

- G09-G15, G17-G18 remain open; the entire GUI goal stays active
  through objective 219, and the FINAL 219 installed whole-GUI test
  and the remaining stages are NOT complete here.
- All qualification evidence is synthetic: owned disposable
  PostgreSQL and Playwright Chromium with synthetic credentials/IDs;
  no real provider/Codex request, no installed transcript, no
  installed whole-GUI qualification.
- No native tamper/secret-injection replay beyond the scoped
  canary evidence listed above; no release/tag/deploy performed.
- At report publication, five IMPL-head CI jobs were still in
  progress; final-head checks, review, merge, and main verification
  are root-owned.
- Preliminary superseded runs are referenced once above and in the
  living record; they are not catalogued and are not evidence.
