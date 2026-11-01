# OAP Coding-Agent Report — 213-a

## Work order
- Identifier: 213-a
- Work-order file: `oap/orders/213-a-gui-replay-maintenance.md`
- Numeric objective: 213
- PR mode: CREATED_NEW_PR

## Status
COMPLETE

## Executive summary
Delivered G09 from `docs/MISSING_GUI_FUNCTIONALITY.md`: an authenticated,
usable GUI for read-only inspection of retained Codex replay references
and the reviewed monotonic extension of their expiry, built in
`/admin/operations/replay-maintenance` on the SAME shared service the CLI
uses (`CodexReplayMaintenanceService.inspect_replay_references` /
`preview_replay_extend` / `apply_replay_extend`) inside a caller-owned
transaction. Scope is always explicit (one existing key, one cohort, or
explicitly every active key - never an implicit default); inspection
writes nothing; preview signs the strict bounded plan to the signed-in
actor/session with a 15-minute HMAC review token; apply runs in ONE
caller transaction where the shared service determines stale
scope/state/eligibility, HMAC availability, and the accepted
already-applied repeat under its lock law. No schema, permission,
adapter, request-acceptance, accounting, or replay-law change; the shared
replay schemas/service/repository/CLI/accounting modules are unchanged
read-only reuse. One new PR (#369) from verified remote `main`; the
activated order and `oap/active` are committed unchanged with the
implementation.

## Authoritative GitHub state
- Repository: `ulfe-lmi/slaif-api-gateway`
- PR number: 369
- PR URL: https://github.com/ulfe-lmi/slaif-api-gateway/pull/369
- PR state at report time: OPEN
- Base branch: main
- Head branch: oap/213-gui-replay-maintenance
- Starting remote SHA: `abc080140cb324da29bbc01b93bb57a8abeac1e1` (verified remote `main` at activation, 2026-11-01T13:06:29Z; merge of PR #368 / objective 212-a)
- Implementation head SHA: `ecd87abebb8a78d5051cfca15f5ce5762564cc50`
- Report publication commit: SELF
- Remote PR head after report publication: SELF (literal SHA derived from GitHub)
- Implementation commits pushed before the report commit: exactly one - `ecd87abebb8a78d5051cfca15f5ce5762564cc50` ("213-a: Add reviewed replay-reference maintenance to the admin GUI"), whose first parent is the verified `main` and which includes the unchanged activated order and `oap/active`
- Report commit first parent: same as Implementation head SHA
- Created a new PR this turn: yes (#369)
- Amended existing PR this turn: no
- Merge performed: NO

## Changes made
- NEW focused router `app/slaif_gateway/api/admin_replay_maintenance.py`
  (prefix `/admin/operations/replay-maintenance`): scope pages
  (index / key / cohort / explicit all-active) with canonical-UUID
  grammar + actual record existence checks; private-POST read-only
  `inspect`; private-POST `preview` (shared dry run, strict 32-KiB plan
  rendering, signed actor/session review token); private-POST `apply`
  (token/actor/session/purpose/expiry re-verification, this-request
  known-incoming-alias re-check, shared apply in ONE caller-owned
  transaction); fixed no-echo safe errors with recovery links that never
  re-expose a refused scope UUID; no-store on all
  SUCCESSFUL replay pages (index/scope/inspection/review) - the fixed
  safe error responses and the shared auth/disabled responses do not
  set that header.
- `app/slaif_gateway/api/admin_review_intent.py`: ONE new replay review
  purpose plus a strict bounded plan+reason envelope wrapper reusing the
  existing HMAC/session-secret primitives (15-minute expiry; envelope
  caps validated before allocation/signing); all old purposes unchanged.
- `app/slaif_gateway/main.py`: router registration (composition only).
- NEW templates `web/templates/replay_maintenance/`: `index.html`
  (three explicit scope choices, one table; no implicit default),
  `scope.html` (bound scope; inclusive-from/exclusive-until UTC bound
  fields; explicit TOTAL lifetime from ORIGINAL creation with in-page
  example; include-expired OFF by default; verbatim bounded reason),
  `inspection.html` (read-only totals/per-key/bounded
  route-model groups/labeled exclusions; existing
  `.table-wide`/`.col-key`/`.nowrap` classes on identity/date cells),
  `review.html` (reviewed facts, confirm + apply, truthful
  applied/already-applied/no-change/unconfirmed outcomes), `error.html`
  (fixed no-echo messages with safe recovery).
- `operations/index.html`: one card; `keys/detail.html` and
  `cohorts/detail.html`: one bound-scope link each (record selection
  stays in the existing searchable lists).
- NEW test modules: `tests/unit/test_admin_replay_maintenance_213.py`
  (43), `tests/integration/test_admin_replay_maintenance_213_postgres.py`
  (11, ordered scenario over a fresh owned PostgreSQL),
  `tests/browser/test_admin_replay_maintenance_213.py` (7, actual
  Chromium + real uvicorn + owned PG).
- Existing structural guards updated ONLY for the required new
  registrations: `test_admin_slaif_design.py` (+5 wrappers),
  `test_admin_usability_inventory.py` (+5 sortable tables), and
  cross-purpose token-refusal fixtures in `test_admin_key_clone_208.py`
  and `test_admin_provider_route_configuration_210.py` (the new review
  purpose must refuse their tokens; no weakened invariants).
- Living docs (G09 only; G11-G15/G17-G18 and 219 remain open):
  `docs/MISSING_GUI_FUNCTIONALITY.md` (section 15 + header delivery
  update), `docs/admin-usability.md` (section 14 operator walkthrough),
  `docs/verification/gui-cli-parity.md` (213-a record),
  `docs/verification/README.md` (index entry), `docs/cli-reference.md`
  (replay cross-reference note).
- `oap/orders/213-a-gui-replay-maintenance.md` and `oap/active`
  committed UNCHANGED (strategic bytes; `oap/active` now `213-a`).

## Files changed
```text
A app/slaif_gateway/api/admin_replay_maintenance.py
M app/slaif_gateway/api/admin_review_intent.py
M app/slaif_gateway/main.py
M app/slaif_gateway/web/templates/cohorts/detail.html
M app/slaif_gateway/web/templates/keys/detail.html
M app/slaif_gateway/web/templates/operations/index.html
A app/slaif_gateway/web/templates/replay_maintenance/error.html
A app/slaif_gateway/web/templates/replay_maintenance/index.html
A app/slaif_gateway/web/templates/replay_maintenance/inspection.html
A app/slaif_gateway/web/templates/replay_maintenance/review.html
A app/slaif_gateway/web/templates/replay_maintenance/scope.html
M docs/MISSING_GUI_FUNCTIONALITY.md
M docs/admin-usability.md
M docs/cli-reference.md
M docs/verification/README.md
M docs/verification/gui-cli-parity.md
A oap/orders/213-a-gui-replay-maintenance.md
M oap/active
A tests/browser/test_admin_replay_maintenance_213.py
A tests/integration/test_admin_replay_maintenance_213_postgres.py
M tests/unit/test_admin_key_clone_208.py
M tests/unit/test_admin_provider_route_configuration_210.py
A tests/unit/test_admin_replay_maintenance_213.py
M tests/unit/test_admin_slaif_design.py
M tests/unit/test_admin_usability_inventory.py
```

## Acceptance-criteria evidence

### Criterion 1: explicit scopes, bound navigation, no implicit default
- Result: PASS
- Evidence: unit cases `test_index_shows_three_explicit_scopes`,
  `test_key_scope_page_shows_bound_scope`,
  `test_cohort_scope_page_and_negatives`,
  `test_all_active_scope_page_is_explicit`,
  `test_key_scope_missing_key_404_with_recovery`,
  `test_key_scope_non_canonical_uuid_404` (canonical grammar; older
  records still resolvable); browser case 01 navigates Operations ->
  index and the bound key/cohort detail links.

### Criterion 2: read-only inspection, safe labels, no writes
- Result: PASS
- Evidence: unit `test_inspect_exact_service_call_is_read_only` (exact
  service invocation incl. UTC bound parsing; numeric "Keys in scope"
  render asserted); browser case 02 (real keyboard Enter submission;
  independent before/after oracle over every key/ledger/reference/
  reservation column, the entire expiry map, and the audit count); PG
  cases prove no domain/audit write.

### Criterion 3: guided bounds/TTL/expired/reason semantics
- Result: PASS
- Evidence: unit `test_preview_blank_ttl_uses_configured_default`,
  `test_preview_explicit_ttl_passed`, `test_preview_ttl_refusals`
  (1..31,536,000; whole seconds),
  `test_preview_include_expired_default_off_then_on`,
  `test_preview_reason_convention` (verbatim, never trimmed, bounded),
  `test_inspect_bad_time_bounds_refused` (inclusive/exclusive UTC law);
  PG cases cover original-age monotonic targets, explicit expired
  inclusion, and never-shortened rows.

### Criterion 4: preview = no-write strict plan + 15-minute signed review
- Result: PASS
- Evidence: unit `test_preview_signs_token_bound_to_actor_session`,
  `test_preview_rendered_plan_size_bound_before_signing`,
  `test_preview_review_doc_alias_refused_before_signing`, token round
  trip/cross-purpose/expired/tampered/envelope-cap cases; PG preview
  proves zero writes; browser case 03 reads the signed token from the
  displayed page.

### Criterion 5: apply = one transaction, shared service law
- Result: PASS
- Evidence: unit `test_apply_exact_single_call_with_signed_facts`
  (posted overrides confer no authority),
  `test_apply_wrong_actor_refused`, `test_apply_cross_purpose_compatibility_token_refused`,
  `test_apply_expired_token_refused`, `test_apply_tampered_token_refused`,
  `test_apply_stale_refused_with_fresh_preview_recovery`,
  `test_apply_generic_failure_unconfirmed`,
  `test_apply_alias_recheck_before_service`; PG cases: one
  session-actor/reason audit, exact reload/repeat no duplicate
  write/audit, stale scope and changed-eligibility refusal, late fault
  AFTER the real audit flush rolls back extension AND audit together
  with retry; independent before/after DB oracle compares ALL
  non-expiry key/material/ledger/quota/reservation/replay-ownership
  fields plus the ENTIRE expiry map.

### Criterion 6: truthful outcomes and repeat
- Result: PASS
- Evidence: unit `test_apply_repeat_already_applied_truthful`,
  `test_apply_noop_result_truthful`, `test_apply_generic_failure_unconfirmed`;
  browser case 04 (exact same-session repeat no-op) and case 05
  (original displayed token survives a real background read).

### Criterion 7: page/auth paths, no-echo recovery, no-JS, field guidance
- Result: PASS
- Evidence: unit `test_pages_require_auth`, `test_dashboard_disabled_refuses_every_route`,
  `test_inspect_requires_csrf`, the scope-alias refusal cases (recovery
  link never re-exposes the refused UUID),
  `test_inspect_requested_model_alias_withheld` (known-secret shape
  protection on dynamic labels); browser case 06 (no-JS inspect ->
  validation refusal -> recovery -> full UI apply); all touched fields
  carry unique control IDs with associated help; desktop/narrow
  captures visually reviewed by the strategic model (gate passed on
  the refreshed set, including the populated narrow inspection).

## Local verification
All runs used the existing `/tmp/slaif192-coding-venv`, the installed
Chromium, and fresh owned labeled loopback/tmpfs PostgreSQL containers
created and destroyed by the test fixtures (exact-ID cleanup
independently verified; the final targeted-capture container
`20b0813f1a603216c33c79a759967b97db31acd368e3f854bfd858ad70785a29` / owner `slaif185a-56d3efb73de94a9286b531fcce3561da` was verified NotFound with
owner_remaining 0). No real upstream keys, no real email, no ambient
DB mutation.

- `python -m pytest -q tests/unit/test_admin_replay_maintenance_213.py` (this activated turn; final state): PASSED — 43/43, 0 skip. Receipt `/tmp/slaif213/unit-213a-1.xml` (17.163 s, SHA `96af820bf596528fa846c5496e2b82f6dbdbbff658b1742caabacb9bd67793dc`), re-receipted after the keys_count fix as `/tmp/slaif213/unit-replay-template-rereceipt.xml` (43/43, 14.050 s, SHA `ec8cd866e2589dc6d8c6321e57ecef93aadaae97472bd8d2644596164e03f7d1`).
- `python -m pytest -q tests/unit/test_admin_replay_maintenance_213.py tests/unit/test_admin_slaif_design.py tests/unit/test_admin_usability_inventory.py tests/unit/test_oap_governance.py`: PASSED — 185/185 (43 new + 12 design + 121 inventory + 9 OAP governance on the exact activated order+active), 0 skip. Receipt `/tmp/slaif213/unit-guards-213a-1.xml` (20.316 s, SHA `5565c61ac36207d03618ca0a106659025305c130981a3afdbdad3455e4f3d4e4`). The 185 INCLUDES the 43 (not 228 distinct).
- `python -m pytest -q tests/integration/test_admin_replay_maintenance_213_postgres.py`: PASSED — 11/11 (one ordered scenario over real auth/HTTP/owned PG/Core), 0 skip. Receipt `/tmp/slaif213/pg-213a-1.xml` (14.131 s, SHA `c49c36ded860c9b0662e9e7db62b5f4ce845c2184d9784872355b5c8357ac7b2`).
- `python -m pytest -q tests/browser/test_admin_replay_maintenance_213.py`: PASSED — 7/7 (actual Chromium + real uvicorn + owned PG; no route mocks), 0 skip. Receipt `/tmp/slaif213/browser-213a-1.xml` (19.158 s, SHA `ae57bb6d462098157242b625fdc4da90045cb277a9429e191034410b599b4c9c`).
- Targeted post-visual-fix unit recheck: `python -m pytest -q tests/unit/test_admin_replay_maintenance_213.py::{test_index_shows_three_explicit_scopes,test_key_scope_page_shows_bound_scope,test_cohort_scope_page_and_negatives,test_all_active_scope_page_is_explicit,test_inspect_exact_service_call_is_read_only,test_inspect_requested_model_alias_withheld} tests/unit/test_admin_slaif_design.py tests/unit/test_admin_usability_inventory.py`: PASSED — 139/139, 0 skip (7.730 s). Receipt `/tmp/slaif213/unit-visual-213a-1.xml` (SHA `3862d3f8acbe865b436738601f8b0d9a9f26e4da90893019e2c518cc6d087cf9`). Overlaps the 185 (not new distinct totals).
- Targeted post-visual-fix browser recheck: `python -m pytest -q tests/browser/test_admin_replay_maintenance_213.py::test_02_inspect_form_is_read_only tests/browser/test_admin_replay_maintenance_213.py::test_07_desktop_and_narrow_captures`: PASSED — 2/2, 0 skip (11.691 s). Receipt `/tmp/slaif213/browser-213a-2.xml` (SHA `4d637da43626b3320222ef673e82d56e8d339e080d32ddf632b82e0a7812537f`). Case 02 now submits with a REAL keyboard Enter and asserts the numeric Keys-in-scope render; case 07 exercises REAL keyboard focus + Space toggle of the confirmation checkbox (restored before capture; no apply) and adds the narrow POPULATED inspection capture. Overlaps the accepted 7 (not a ninth workflow).
- `python -m ruff check` over all touched/new Python files: PASSED ("All checks passed!").
- `python scripts/check_documentation.py`: PASSED (`DOCUMENTATION_CHECK=OK files=135`).
- Reused unchanged: accepted objective-200/CLI concurrency and large-scope Core proofs (no 20k-row scale repetition); unchanged cross-purpose 208/210 consumer-guard stdout success. Strategic-model scoped component probes (10 scope-parser, 8 token, 14 ASGI; synthetic, component-level, not native evidence) and independent receipt parse/hash + visual review are recorded in the living verification record.

## GitHub CI / required checks
- ONE fresh check snapshot for implementation head
  `ecd87abebb8a78d5051cfca15f5ce5762564cc50` (PR #369), observed at
  2026-11-01T14:56:09Z:
- Unit, lint, and migration head: PASS (3m35s)
- PostgreSQL integration tests: PENDING (still pending at snapshot time)
- OpenAI-compatible E2E tests: PASS (1m59s)
- Playwright browser smoke: PASS (4m35s)
- Docker Compose smoke: PASS (1m3s)
- Documentation hygiene: PASS (4s)
- CodeQL: PASS (4s)
- Analyze (python): PASS (3m9s)
- Analyze (javascript-typescript): PASS (50s)
- Analyze Python (separate run): PASS (1m26s)
- All required checks green for the implementation head at report drafting: no (PostgreSQL integration tests PENDING at the snapshot; pending is reported as pending, never as passed)
- Report-only commit may trigger fresh checks: strategic model must verify the `SELF` commit without rewriting this report

## Local setup / dependencies
- Packages/tools/services installed or configured: none new; reused the existing `/tmp/slaif192-coding-venv`, installed Playwright Chromium, Docker (owned postgres:16 containers), and ImageMagick (screenshot crops only, local artifacts).
- `sudo`-level setup performed: none this turn.
- Durable setup changes committed/documented: none.

## Documentation
- `docs/MISSING_GUI_FUNCTIONALITY.md`: G09 marked delivered (section 15 + header delivery update); G11-G15, G17-G18, and the 219 installed whole-GUI qualification remain open; no duplicate map/evidence catalogs.
- `docs/admin-usability.md`: new section 14 operator walkthrough (navigation, scope/inspection semantics, TTL original-age/default/expired/eligibility/ceilings, preview/review/apply, truthful outcomes, no-JS, upgrade notes).
- `docs/verification/gui-cli-parity.md`: new 213-a record (scope/parity contract, accepted receipts table with SHAs, in-order corrections chronology, reused-unchanged evidence, resource evidence, limits).
- `docs/verification/README.md`: 213-a index entry.
- `docs/cli-reference.md`: brief cross-reference noting the GUI offers the same inspection/reviewed extension over exactly the CLI scopes (213-a); CLI commands, scope law, plan format, eligibility, ceilings, and audit behavior unchanged.
- No schema upgrade documented or made; no production/client proof claimed.

## Safety and scope confirmations
- Unrelated files changed: no - the diff against `abc08014` is exactly the 25 files above (allowed app paths, required test registrations, living docs, and the unchanged activated order/active). Protected untracked files (`CODEX-SESSIONS.md`, `codex.sh`, `uv.lock`), ignored operator config, `.local-provider-catalog/` trees, and linked worktrees were preserved and NOT committed; no reset/clean/stash/force-push.
- Production secrets accessed: no
- Production systems accessed: no
- Required tests skipped/not run: no skips in any run above (0 skip across all receipts); the unchanged accepted suites (objective-200 scale/concurrency components, cross-purpose guards) were deliberately REUSED, not rerun, per the order's economy rule.
- Scope deviation: no - Core/auth/accounting, the shared replay service/schemas/CLI, and all protected files untouched; no new digest/decryption verifier, key-recovery surface, schema, jobs, storage platform, or generic lookup infrastructure.
- Extra PR created for same numeric objective: NO (exactly PR #369)
- PR merged by coding agent: NO
- Activated order and `oap/active` edited by coding agent: NO (committed unchanged; `oap/active` = `213-a`)
- Report-publication commit changes only this report file: yes (verified before signal)

## Known limitations / blockers
- GitHub required checks for the implementation head were still PENDING at report publication (only Documentation hygiene had passed); the strategic final-head check/review/material/visual gate applies before any merge.
- The 11-case native module is ONE ordered scenario and the 7-case browser module is one ordered flow per case family - not 11/7 independent installations.
- Unit evidence fakes the shared service at the module seam (auth/repositories/maintenance effects); TTL range boundaries are proven by the shared `validate_ttl_seconds` directly, and apply outcomes are label-only at unit level - native PG/Chromium evidence carries the real-effect proof.
- No real Codex, provider, or mail request was made; no real replay usage, runtime-HMAC replay authentication, or installed/deployment qualification is claimed. The final 219 installed whole-GUI qualification remains mandatory.
- Execution chronology note (transparency): the coding CLI hit its context window mid-visual-fix on 2026-11-01 and this turn is the SAME-CLI/pane/worktree continuation of the already-activated 213-a; the control OK was consumed ONCE at activation (13:06 UTC); no resignal, no second control reader, no model/profile/effort change.

## Recommended strategic follow-up
Independent review of PR #369 (diff, report, required checks on the
`SELF` head, refreshed captures already reviewed), then merge per the
OAP gate; the whole-GUI goal remains ACTIVE through 219.
