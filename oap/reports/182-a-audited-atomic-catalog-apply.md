# OAP Execution Report — Objective 182-a: Audited Atomic Catalog Apply

Report status: IMMUTABLE (finalized at the exact final implementation
head `7f5965801cc1a97729abf2c630c9de770b84d880`; published atomically as
the immutable report; the report-only SELF commit is its publication
commit).

## 1. PR identity and merge state

- PR: #320 `feat: apply reviewed catalog changes atomically with pricing history`
  (exactly one 182 PR; CREATE_NEW_PR from verified remote main
  `60214c54226a9b488666e8a849fe9f326faf8218`).
- Branch: `oap/182-atomic-catalog-apply`.
- Implementation head: `7f5965801cc1a97729abf2c630c9de770b84d880`
  (first parent of the SELF commit)
- Report-only SELF commit: the publication commit of this report;
  first parent = implementation head; only this report path differs.
- Merge performed: NO. Auto-merge: not requested/enabled
  (`autoMergeRequest: null`). Coding agent never merges.
- Order: `oap/orders/182-a-audited-atomic-catalog-apply.md` committed
  byte-identical to the strategic workorder copy (sha256
  `448372eb53cd589108fcaf12dd18388d7826e2abc491fe47ab8e21b8eb9612c3`);
  `oap/active` = `182-a` (5 bytes, no LF).

## 2. Environment

- Coding checkout `/home/janezp/codex-work/slaif-api-gateway`; strategic root
  `/home/janezp/codex-supervision/slaif-api-gateway`.
- Python 3.12.15 (`/tmp/slaif-181c-strategic-venv`), pytest 9.1.1, Ruff (venv).
- Owned PostgreSQL 16.15 container `slaif182a-pg-a76441e6`
  (label `slaif.182a.owned=true`, loopback 127.0.0.1:49839, synthetic user
  `slaif_synth`, no persistent volume; databases `slaif182applytest`
  (migrated to 0025), `slaif182basetest` (pristine-migrated comparison),
  `slaif182applytest2` (fresh apply-lifecycle re-run DB), and
  `restore_local_182a` (safe-name migration-cycle DB)).
  Credentials archived outside the repo; never printed in full.
- Pristine comparison worktree at origin main `60214c5`
  (`/tmp/slaif-182a-baseline-check`) used only for pre-existing-failure
  isolation; no commits made there.
- Browser: JS-disabled Chromium, scoped `LD_LIBRARY_PATH` browser runtime
  (owned temp libraries, no system install).

## 3. A1 — single-transaction apply with durable record

- `app/slaif_gateway/services/catalog_refresh/apply.py` (new):
  `apply_intent_incomplete` (blank actor/reason, service-entry validated) ->
  real anchored verified capture (one read per file) -> state gate
  READY/RWW -> sealed plan gates (`apply_no_plan` / `apply_plan_unsupported`
  schema `1`) -> ONE `engine.begin()`: prelude (`SET LOCAL lock_timeout
  '10s'`, `SET LOCAL statement_timeout '60s'`) -> fixed-order
  `LOCK TABLE ... IN SHARE ROW EXCLUSIVE MODE` (fx_rates, model_routes,
  pricing_rules, provider_configs) -> `SELECT current_user` -> refresh target
  check -> known-committed lookup FIRST (`find_committed_by_bundle`:
  0 -> continue; 1 -> `already_committed` with the prior record, prior
  actor/effective_at unchanged; >1 -> `apply_duplicate_record`) -> current
  execution gates (`apply_freshness_blocked` / `apply_warnings_unacknowledged`
  / `apply_plan_mismatch`) -> same-transaction projection stale check
  (`apply_bootstrap_not_empty` / `apply_baseline_stale`, updated_at excluded)
  -> one `effective_at` -> admin check (`apply_admin_unknown`) -> plan-order
  ops (close-guard re-verification fail -> `apply_supersession_guard_failed`;
  row IDs recorded as `str(row.id)`) -> `create_application_record`
  (receipt HMAC from the held capture; unique (bundle_sha256, plan_sha256))
  -> audit `catalog_refresh_applied` -> commit. `IntegrityError` ->
  read-only re-lookup; other errors -> `apply_database_error` (type name
  only). Engine always disposed. No SQL writes before the gates.
- `status`: lock-free, read-only recovery of the committed outcome.
- Real owned PG proofs (`tests/integration/test_catalog_refresh_apply_postgres.py`,
  7/7 PASS, PostgreSQL 16.15, re-run at the final head on the fresh DB
  `slaif182applytest2` — a shared-DB re-run first hit leftover
  `quota_reservations` from the responses suite in the same database,
  database-state isolation, not code):
  1. bootstrap apply atomic + retry `already_committed` (prior actor/T
     unchanged) + status after simulated client loss + record fields
     (bundle_sha from receipt, plan_sha from sealed plan, db_actor = the
     actual `current_user`, receipt HMAC match, audit = 1, no duplicate on
     retry);
  2. refresh supersession closes the old active row at T and inserts the new
     row at the same T; retry idempotent;
  3. refusals mutate nothing (bootstrap-not-empty / stale-with-drift /
     admin-unknown, all inside the transaction);
  4. SHARE ROW EXCLUSIVE matrix on real PG while the apply lock is held:
     plain SELECT unblocked, second SRE requester blocked, ORDINARY INSERT
     hits `lock timeout` (ordinary-writer race, not only apply-vs-apply);
  5. two conflicting plans from one baseline raced via `asyncio.gather` on
     `apply_reviewed_run`: exactly one commits, the other
     `apply_baseline_stale`; loser re-run stays stale; winner retry ->
     `already_committed` with the prior actor/T (known-outcome-before-current
     gates ordering proof);
  6. injected mid-apply failure rolls back EVERYTHING (provider/route/
     pricing/record/audit all zero);
  7. manually injected second committed record -> `apply_duplicate_record`.
- Strategic independent corroboration: PG16.15 lock-compatibility probe
  (`review-artifacts/182-a-review/lock-compatibility-results.json`):
  SHARE UPDATE EXCLUSIVE did not block an ordinary INSERT (0.001s commit);
  SHARE ROW EXCLUSIVE blocked it (lock timeout 0.401s); plain SELECT and the
  ACCESS SHARE reads remained allowed — the matrix correction was
  independently confirmed and retained in the in-app race test.
- Checked-handle lifecycle (A1 captured-descriptor reuse, completed at the
  final head): the CLI's already-checked run-directory and seal-key-parent
  handles carry the apply and status paths — boundary re-checks
  (`assert_name_binding`, hop by hop through the held descriptors) before
  the key read and before the sensitive authenticated capture; the key is
  read through the held key-parent descriptor and the single authenticated
  capture runs through the held run descriptor (`load_verified_capture` and
  `load_seal_key_bytes` gained optional held-handle parameters; omitted
  handles preserve the legacy anchor-once/close-once behavior); the service
  never re-anchors a checked path by name and never closes a caller-owned
  descriptor; the engine cleanup `finally` blocks are intact. The
  intermediate syntactically-invalid local edit of this lifecycle was
  preserved verbatim in the strategic review artifact and replaced by the
  completed fix, per the CI-repair scope decision's explicit instruction.
- Unit proofs (`tests/unit/test_catalog_refresh_apply.py`, 15/15): intent
  before authentication, BLOCKED/no-plan/unsupported refusals with
  no-DB-contact guard, exact sealed-plan identity vs a real CliRunner run
  (operations/plan_sha256/bundle_sha256 == sealed validation.json + receipt,
  ACK pass-through), wrong seal key -> SealError pre-DB, target-mismatch
  fake engine proving the exact statement sequence (2 SET LOCAL, 4 SRE locks
  in fixed order, current_user, 7 statements, zero writes, disposal, no
  credential leak), status lock-free wiring; plus 7 new lifecycle
  regressions: swapped run directory -> SealError at the capture boundary
  before any DB contact; swapped key parent -> SealError before any key
  byte is read; intact held handles prove the real capture and the key read
  reuse the held descriptors with NO re-anchor (asserted by a raising
  `_open_anchored` guard) incl. CLI end-to-end apply and status, and the
  status path stays read-only with the engine disposed.
- Migration 0025 (`0025_catalog_refresh_applications.py`, additive):
  fresh owned DB upgrade head -> downgrade 0024 -> re-upgrade head all OK;
  structure verified in-container: pk (id uuid), `uq_catalog_refresh_application_identity
  (bundle_sha256, plan_sha256)`, ix_run_id, ix_effective_at,
  `outcome = 'committed'` check, NOT NULL audit fields.

## 4. A2 — actionable typed apply plan

- `planning.py` (new): `APPLY_PLAN_SCHEMA_VERSION = "1"`; operations sorted
  by `op_sort_key` (create_provider < create_route < create_pricing <
  supersede_pricing < create_fx < supersede_fx); `plan_sha256` hashes the
  list AS GIVEN (content- and order-sensitive; canonicity is
  `build_apply_plan`'s job — unit-tested).
- `validation.py`: each representable route/price operation derived
  INDEPENDENTLY; mixed public-alias + upstream price change yields
  `create_route + supersede_pricing` with `new_route_with_changed_pricing`
  (strategic overlay repro: EUR 0.4 -> 0.5, alias-v1 NEW route, same
  upstream — previously suppressed).
- All-new-model exposure to allow-all keys is a REVIEW warning requiring
  ACK: `new_model_exposure` (pure create/bootstrap) and
  `new_route_with_changed_pricing` (mixed) — first-install and every route
  create, not only refresh.
- Supersession requires EXACTLY ONE active eligible row: identical
  overlapping active rows BLOCK (`baseline_duplicate_active_rows`) instead
  of silently choosing/closing history; disabled rows ->
  `baseline_disabled_rows` (denial preserved, never inferred enablement);
  future rows -> `baseline_future_row_overlap`.
- Apply gates: warning without ACK -> `apply_warnings_unacknowledged` (CLI
  exit 10); re-derived plan mismatch -> `apply_plan_mismatch` (exit 20);
  schema `1` only.
- Strategic overlay probes (zero network): mixed-plan repro fixed
  (`draft-mixed-plan-results.json`); identical-overlap BLOCK confirmed
  (`draft-multiple-active-plan-results.json`); disabled-pricing branch
  corrected per the A2 authority decision (`draft-disabled-pricing-plan-results.json`).

## 5. A3 — coherent immutable admission capture

- `PricingRulesRepository.find_active_pricing_rule_with_fx` executes the
  paired price+FX selection in ONE statement (`_COHERENT_PAIR_SQL`); raw
  column mapping (no stale ORM identity-map reuse); `PricingService.
  capture_pricing_and_fx` wraps it: EUR captures the read-free identity
  conversion; non-EUR missing rate fail-closed (`FxRateNotFoundError`);
  missing pricing rule fail-closed (`PricingRuleNotFoundError`).
- All five affected gateway call sites (chat/responses/audio/embeddings/
  realtime) wired to the shared capture; `schemas/pricing.py` carries the
  safe immutable `PricingCapture` contract.
- Real PG financial/concurrency proofs
  (`tests/integration/test_catalog_refresh_accounting_postgres.py`, 3/3):
  1. REPEATABLE READ reader paused across the atomic supersession sees the
     complete OLD pair before AND after commit; new transaction sees the NEW
     pair; explicit at=T±1s resolves old/new rows (one effective T in
     history);
  2. reservation estimated from the OLD capture finalizes AFTER the refresh
     at the OLD cost 0.0000375 (DB shows the new price 0.26) — never the
     new cost 0.0000380;
  3. provider-completed recovery after refresh repairs from persisted
     ledger facts (same 0.0000375), dry-run no-op first.
- Strategic independent probe: ONE SQL capture, ZERO estimate SQL; after a
  concurrent atomic price/FX edit the old captured cost stays EUR 0.0015
  while a fresh complete pair reads EUR 0.0054; raw pair bypasses stale ORM
  cache; EUR/missing-price/missing-FX fail-closed
  (`draft-coherent-service-postgres-results.json`).
- Structural finalization preservation retained
  (`compute_actual_cost` keeps the explicit `at` parameter contract).
- No two-read production fallback for test stubs (per strategic direction).

## 6. A4 — preserved price/FX history

- Supersession closes the reviewed active window at the single effective T
  (close guard re-verifies identity/values/reviewed end; NULL->finite drift
  rejected via null-safe equality) and inserts the reviewed new row at T;
  amounts/sources/row identities preserved — history never re-priced in
  place. Finite future `valid_until` active rows are refreshed safely
  (closed at T), not blanket-BLOCKed.
- `fx_rates.py`: `close_active_fx_rate` added WITHOUT removing existing
  public methods — all five pre-existing public methods restored byte/AST
  identical to main (strategic AST verification of all eight original
  methods: `list_fx_rates_for_admin`, `get_fx_rate_for_admin_detail`,
  `update_fx_rate_metadata`, `find_latest_rate`, `list_rates_for_pair` +
  unchanged pricing/fx service call sites in dashboard/qualification).
- Version contract: historical 181 archives are explicitly refused by the
  182.1 renderer boundary (missing/supported-shape/version of the
  authenticated execution context); the unsupported-renderer error is a
  fixed code/message — NO echo of authenticated input (canary negative
  regression added, per the A1 safe-error finding).

## 7. AP5 — focused verification evidence (exact commands)

Unit (DB-free), all `-q -p no:cacheprovider`:
- 19 allowed/affected unit files at the final head: 543 collected,
  543 passed, 0 failed (collection 78, source_evidence 79, responses_quota
  82, policy 43, filesystem 38, seal 37, cli 34, report 11, planning 10,
  accounting_finalize 9, apply 15, realtime 7, audio 6, embeddings 6,
  chat_completions_forwarding 23, chat_completions_pricing 11,
  provider_completed 5, pricing_service 33, execution_identity 16).
- CI-repair file set at the final head (16 files, disjoint from the list
  above): 14 unit files 121 collected / 121 passed (alembic accounting 3,
  email_jobs 3, external_tool_fence 7, key_prefix_default 3,
  provider_pricing 3, quota_reservation_accounting_facts 2, schema_status
  6, chat_completion_transaction_boundaries 5, v1_chat_completions
  forwarding_errors 7, policy 47, quota 7, rate_limits 11, streaming 12,
  streaming_rate_limits 5); 2 integration files on the owned PG: 17/17
  (below).

Integration, owned PG 16.15, `TEST_DATABASE_URL` from the owned container
only:
- `test_catalog_refresh_baseline.py`: 21/21 PASS (fresh migrated DB).
- `test_catalog_refresh_apply_postgres.py` 7/7,
  `test_catalog_refresh_accounting_postgres.py` 3/3,
  `test_repositories_accounting_and_pricing.py` 1,
  `test_accounting_finalization_postgres.py` 3,
  `test_provider_completed_reconciliation_postgres.py` 3,
  `test_cli_routing_pricing_postgres.py` 6 — batch 23/23 PASS.
- `test_responses_external_tool_postgres.py`: 16/16 PASS at the final head
  (the pricing seam now supplies equivalent `PricingCapture` facts; all
  real-PG quota/fence/hold/rollback/reconciliation assertions and execution
  intact).
- `test_gateway_key_prefix_migration_postgres.py`: 1/1 PASS at the final
  head on the safe-name disposable DB `restore_local_182a` (the file's own
  schema drop/recreate runs only inside that DB).
- Migration cycle: upgrade head / downgrade 0024 / re-upgrade head on the
  fresh DB (see A1).

Browser (JS-disabled Chromium, scoped LD_LIBRARY_PATH runtime),
`tests/browser/test_catalog_refresh_report.py` (plan/action/stage facts):
9 cases (CLI-published first-install + blocked; in-process validate+render
for the rest, including actual mocked-collect both-provider LIVE and INTACT
supplied-collection) x viewports 1440x900 / 1280x800 / 375x812, collapsed
AND fully expanded: document widths <= viewport, first 1440x900 reading
surface complete, font floors, single-line short labels, visible full
  digest/values, zero external requests, static offline HTML, PDF artifacts
  for the two print cases. PASS locally at 72dd8d4 (10 cases x 3 viewports,
  collapsed and expanded); no rendering changes since, so the final-head
  browser proof is the green CI browser job below.

Static: `ruff check app tests` clean; `scripts/check_documentation.py`
OK (91 files); `git diff --check` clean.

CI (GitHub, PR #320) at final head 7f5965801cc1a97729abf2c630c9de770b84d880
(run 38433431566 + the paired analysis runs) — ALL 10 CHECKS PASS:
| Check | Result |
|---|---|
| Unit, lint, and migration head | pass (2m14s) |
| PostgreSQL integration tests | pass (2m0s) |
| Playwright browser smoke | pass (2m55s) |
| OpenAI-compatible E2E tests | pass (1m32s) |
| Documentation hygiene | pass (5s) |
| Docker Compose smoke | pass (55s) |
| CodeQL | pass (3s) |
| Analyze Python | pass (1m2s) |
| Analyze (python) | pass (2m35s) |
| Analyze (javascript-typescript) | pass (1m19s) |

The previous head's 67 unit/integration failures (16 files) are resolved:
Unit 2m14s pass and PostgreSQL integration 2m0s pass above. Browser CI
margin history (in-scope wording repairs only, no layout/font/viewport
assertion changes at any step): run 38344034020 failed 375px overflow
(385) -> compact apply-plan wording (2b52449); run 38346052756 failed
1440x900 first-screen (bottom 905.1) -> compact exposure labels / banner
tail / scope chips (9ee8fb7); run 38351673402 (9ee8fb7) still failed the
1440x900 first screen at #changes (top 884.14 CI vs 864.92 local — a
constant +19.2px shift traced per-element to CI's wider default sans: the
run-identity compact line was the only first-screen element whose
2->3-line wrap threshold fell below the CI width band) -> removed the
duplicated wall-clock instant from that line, keeping run id, generator
tool, short digest, and the full-identity link; two lines even at 1.29x
font width (72dd8d4); final head 7f59658 browser CI PASS.

## 8. Scope decisions and disclosures

Inside the order's exact allowed paths (no decision needed):
- `tests/integration/test_catalog_refresh_baseline.py` (F2 first-install
  step now expects exit 10 READY_WITH_WARNINGS with the
  new_model_exposure REVIEW finding and no blockers — the intended A2
  behavior; pristine-at-60214c5 comparison confirmed the flip is caused by
  the A2 warning, not by the apply machinery).
- `tests/browser/test_catalog_refresh_report.py` (first-install CLI exit
  0->10; collection/supplied-collection/two-provider builders now assert
  the A2 exposure findings set exactly, no blockers; all layout/font/
  viewport assertions unchanged).

Strategic scope decisions (test-only fixture updates outside the original
allowed list), all disclosed as required:
- `workorders/OBJECTIVE-182-A-TEST-FIXTURE-SCOPE-DECISION.md`:
  `test_catalog_refresh_filesystem.py` + `test_catalog_refresh_source_evidence.py`
  (exposure-warning state/exit fixtures; all security/provenance/no-network/
  escaping assertions preserved; authentic verify still exits 0).
- `workorders/OBJECTIVE-182-A-COLLECTION-FIXTURE-SCOPE-DECISION.md`:
  `test_catalog_refresh_collection.py` (18 sites: 14 validator + 4 CLI
  pytest counts; independent two-case reproductions failed only
  READY->READY_WITH_WARNINGS/new_model_exposure, zero physical network).
- `workorders/OBJECTIVE-182-A-CHAT-PRICING-TEST-SCOPE-DECISION.md`:
  `test_v1_chat_completions_pricing.py` (capture fake/signature/error-seam
  changes; 19 original assertions AST-verified intact; 11 tests pass, zero
  physical network).
- `workorders/OBJECTIVE-182-A-CI-REPAIR-SCOPE-DECISION.md` (2026-10-13T16:09,
  APPROVED): authorizes ONLY the 16 files identified in
  `coding-ci-repair-scope-identification.md` — Group A: 7 chat-completions
  unit files, minimal coherent-capture fake/signature/paired-result updates
  (equivalent `PricingCapture` facts at the `capture_pricing_and_fx` seam;
  estimate fakes gained the `pricing`/`fx` keyword arguments the shared
  capture now passes; transaction_boundaries pairs the new `:capture`
  event into its exact sequences); Group B: 1 responses external-tool
  integration file, the already-mocked pricing seam updated to equivalent
  `PricingCapture` facts with all real-PG quota/fence/hold/rollback and
  reconciliation assertions and execution intact; Group C: 8 migration-head
  expectation files, 0024 -> 0025 literals only, with upgrade/
  downgrade/re-upgrade and chain logic preserved. All error/order/quota/
  rate-limit/streaming/privacy/transaction assertions preserved; no
  production two-read fallback, no test-only runtime bypass, no removed
  negatives, no assertion weakening, no new dependencies.
- Coding scope-identification files (draft-before-notification deviations
  recorded transparently): `review-artifacts/182-a-review/
  coding-pricing-forwarding-test-scope-identification.md` (audio 6 /
  embeddings 6 / realtime 7 / responses_quota 26-of-82 pre-fix failures;
  the four forwarding test paths above) and
  `review-artifacts/182-a-review/coding-ci-repair-scope-identification.md`
  (first-CI fallout in 16 files NOT in the allowed list: 7 chat-completions
  unit files / 44 tests at the new paired-capture seam, 1 responses
  external-tool integration file / 15 of 16 tests, 8 migration-head
  0024->0025 expectation files; local reproduction commands included).
  STATUS: APPROVED by the CI-repair scope decision above, which
  authorizes exactly those 16 files; all repairs landed at final head
  7f59658 and the full unit + PostgreSQL CI jobs pass at that head.

No path outside this disclosure was edited. `CODEX-SESSIONS.md` and
`codex.sh` remain untracked and untouched.

## 9. Pre-existing issues observed (not introduced by 182-a)

- `tests/integration/test_catalog_refresh_baseline.py` export-redaction
  tests use the 4-char canary `FLOAT_METADATA = "0.97"` while the exporter
  carries real `now()` timestamps; a wall-clock timestamp whose seconds
  digit is 0 with microseconds starting "97" contains the canary as a
  substring (observed once: `...T03:31:20.978331Z`). The mechanism is
  identical at pristine 60214c5 (the exporter selects the same
  created_at/updated_at columns there); the same tests pass on re-run and
  in the final fresh-DB run. Not fixed here (files outside the allowed
  paths; reported for awareness).
- The shared-session-DB `model_disappeared` behavior in
  `test_live_db_snapshot_run_records_live_capture_and_verify_replay`
  (rows left by other integration files flip READY -> READY_WITH_WARNINGS)
  is documented in the F2 test comment; on a fresh database (CI and the
  final local run) the test passes with READY.

## 10. Remaining limits

- No full local HPC/DB/Redis/Docker matrix (per order AP5); no production
  catalog import, no real upstream inference, no release/tag, no
  production-certificate claim.
- 182 solves the full A1-A4/AP1-AP5 for this PR only; objective 183
  (isolated Codex research) and 184 (final wrappers/clean-install/full E2E)
  remain separate.
- The report-only SELF commit triggers fresh CI checks on the PR head;
  acceptance of those fresh checks is strategic. This report is immutable
  and is not rewritten for them.
