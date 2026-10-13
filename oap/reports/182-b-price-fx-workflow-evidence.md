# OAP Execution Report — Objective 182-b: Price/FX Workflow Evidence

Report status: IMMUTABLE (finalized at the exact final implementation
head `16489a85d100b8918eb9c965aa85c0c2422ed640`; published atomically as
the immutable report; the report-only SELF commit is its publication
commit).

## 1. PR identity and merge state

- PR: #320 `feat: apply reviewed catalog changes atomically with pricing
  history` (the unique 182 PR; 182-b amends it, AMEND_EXISTING_PR).
- Branch: `oap/182-atomic-catalog-apply`.
- Implementation head: `16489a85d100b8918eb9c965aa85c0c2422ed640`
  (first parent of the SELF commit).
- Parent chain: `9e613c231accd244800c4bdfe44f3960db610e46` (182-b
  activation: order + `oap/active`) on `a2a198a586a0187afd3f7725ab057eb3245f29a0`
  (182-a report-only SELF).
- Report-only SELF commit: the publication commit of this report;
  first parent = implementation head; only this report path differs.
- Merge performed: NO. Auto-merge: not requested/enabled. Coding agent
  never merges.
- Order: `oap/orders/182-b-price-fx-workflow-evidence.md` committed
  unchanged by the activation commit; `oap/active` = `182-b` (5 bytes,
  no LF). The prior 182-a order/report remain IMMUTABLE and untouched.

## 2. Environment

- Coding checkout `/home/janezp/codex-work/slaif-api-gateway`; strategic
  root `/home/janezp/codex-supervision/slaif-api-gateway`.
- Python 3.12.15 (`/tmp/slaif-181c-strategic-venv`), pytest 9.1.1, Ruff
  (venv).
- Owned PostgreSQL 16.15 container `slaif182a-pg-a76441e6` (label
  `slaif.182a.owned=true`, loopback 127.0.0.1:49839, synthetic user
  `slaif_synth`, no persistent volume), reused after ID/label
  verification with a NEW disposable database `slaif182btest` migrated to
  head `0025_catalog_refresh_applications`. Derived
  `TEST_DATABASE_URL` only; credentials in an owned `chmod 600` file,
  never printed. 182-a databases preserved.
- No system packages, no shared 5432, no `DATABASE_URL` contact, no real
  source GET, no provider key, no real email, no production import.

## 3. What 182-b proves (new evidence, this commit)

All new proofs run on the owned disposable PostgreSQL 16 (`slaif182btest`)
with the exact command shape:

    TEST_DATABASE_URL=<derived owned URL> \
    /tmp/slaif-181c-strategic-venv/bin/python -m pytest <file> \
    -p no:cacheprovider --no-header -q

Zero skips recorded as PASS for every file below.

### 3.1 B1 — both-provider USD bootstrap and price+FX refresh
(`tests/integration/test_catalog_refresh_apply_postgres.py`, 9 new tests)

- Minimal internally consistent captured official-source fixtures for
  BOTH providers: OpenRouter `/models` JSON with direct USD per-1M prices,
  official OpenAI pricing-docs markdown table (USD per 1M, legacy
  `gpt-…` identifier allowlist), and the ECB reference XML
  (EUR-USD direct quote; USD->EUR reciprocal derived by the validator).
  No real GET.
- `test_bootstrap_both_providers_usd_creates_required_fx`: actual CLI
  review (exit 0) -> apply --confirm/actor/reason commits one T creating
  both providers, both selected routes plus an UNSELECTED retained model
  route, three USD pricing rows (selected OpenRouter row carrying a
  reviewed finite FUTURE validity end, now+30d), and the required
  USD->EUR FX row with correct direction, 9-decimal Decimal
  `0.925925926` (= 1/1.08 at 9-decimal precision), IDs, and receipt
  binding; application + audit rows asserted exact.
- `test_refresh_supersedes_price_and_fx_at_one_t`: real exported
  baseline refresh with changed representable USD price AND FX yields
  `supersede_pricing` + `supersede_fx` in the sealed plan; the actual
  apply closes the reviewed old windows (including the finite future
  end) and opens the new rows at the SAME T; original values/currency/
  source metadata/IDs preserved; exact old/new `at`-boundary; durable
  affected IDs/counts; retained/unselected rows and provider/route
  flags unchanged.
- `test_fx_supersession_failure_rolls_back_price_fx_and_records_together`:
  failure injected after the actual FX (and price) mutation, before
  application/audit completion; ALL affected old windows/amounts and row
  sets plus provider/route/application/audit roll back together (not a
  EUR-only bootstrap rollback).

### 3.2 B2 — default-isolation admission and historical accounting
(`tests/integration/test_catalog_refresh_accounting_postgres.py`, 4 new
tests, plus the unit matrix in 3.5)

- `test_default_isolation_paired_capture_price_and_fx_across_actual_apply`:
  the reader's isolation level is asserted from the database
  (`current_setting('transaction_isolation')` = `read committed` — the
  default; no global isolation change, no lock held over HTTP). The
  interleaving is DETERMINISTIC, not a timing lottery: a test-local
  `lock_catalog_tables` wrapper sets an `asyncio.Event` only after the
  ACTUAL apply holds the catalog locks inside its open transaction.
  Captures: before = complete OLD pair; mid (writer locked, uncommitted)
  = complete OLD pair; after commit = complete NEW pair. Every observed
  (price row ID, values, currency, FX row ID, rate) tuple is a complete
  old-or-new fact tuple — never a mixed pair. Explicit `at=T±1s`
  captures resolve the supersession history exactly at one T. The
  inherited REPEATABLE READ snapshot test remains as a control only and
  is not the qualifying test.
- `test_one_paired_sql_capture_and_zero_extra_price_fx_sql`: an engine
  `before_cursor_execute` listener records that the admission capture
  executes EXACTLY ONE statement joining `pricing_rules` and `fx_rates`,
  and that `estimate_chat_completion_cost` supplied the captured
  pricing/fx issues ZERO additional statements; estimate IDs equal
  capture IDs (USD, rate `0.925925926`, total `0.000135`).
- `test_retained_capture_estimate_survives_refresh_to_finalization`:
  the REAL service-built admission estimate (capture row IDs included)
  is retained as the same object through reservation -> ACTUAL CLI
  apply (price AND FX superseded) -> finalization. The ledger bills the
  old facts: `actual_cost_native = 0.0000405` (USD),
  `actual_cost_eur = 0.0000375`, `native_currency = "USD"`,
  `response_metadata.pricing_rule_id/fx_rate_id` = the OLD capture's row
  IDs, key `cost_used_eur = 0.0000375`. A fresh admission after the
  refresh carries the NEW pair (0.28 / 1.08 USD, FX `0.952380952`, new
  row IDs). No estimate is reconstructed by hand after refresh.
- `test_provider_completed_recovery_after_refresh_uses_real_old_capture_facts`:
  the recovery-state ledger row is persisted from REAL
  capture-derived facts (service `compute_actual_cost` on the retained
  estimate, old pricing/FX IDs in `response_metadata`). After the ACTUAL
  refresh, `reconcile_provider_completed_recovery` (dry then execute)
  under a SQL listener issues ZERO `pricing_rules`/`fx_rates`
  statements — history is never re-priced from the refreshed catalog —
  and finalizes at the old costs/IDs.

### 3.3 B3 — real executor concurrency and recoverable outcomes
(`tests/integration/test_catalog_refresh_apply_postgres.py`, part of the
9 new tests)

- Identical authenticated bundle concurrent apply: one `committed`, the
  serialized other `already_committed` with the SAME prior
  actor/effective_at; exactly one history change, one application
  record, one `catalog_refresh_applied` audit; a distinct actor cannot
  overwrite the committed outcome.
- Ordinary catalog edit vs actual apply, both directions, with
  committed facts never silently lost: writer commits before the locked
  comparison -> `apply_baseline_stale` refusal (writer's fact preserved,
  reviewed finite end intact); writer waits on the apply locks ->
  commits AFTER the apply on top of the committed facts (apply row
  values intact, old row closed at T carrying the writer's note).
- Conflicting catalog lock held across the ACTUAL apply: production
  bounded lock wait (test-local 1s wait seam only; production settings
  unchanged) returns a safe `apply_database_error` refusal with no
  partial writes/records/audit and complete cleanup.
- Client result loss injected AFTER the database commit at the CLI
  return seam: first caller sees the simulated loss; a separate
  authenticated `status` plus retry recover the SAME committed outcome
  (one record, one audit, no duplicate writes).
- Test clock advanced past source freshness AND the reviewed finite
  validity end: authenticated retry of the same bundle still returns the
  original actor/T/counts (known-committed lookup before current
  gates); a different unapplied stale bundle is still refused; no
  archived timestamps refreshed/resealed, no freshness policy relaxed.

### 3.4 B1/B3 totals

`tests/integration/test_catalog_refresh_apply_postgres.py`: 16/16 passed
(7 inherited 182-a + 9 new), zero skips.
`tests/integration/test_catalog_refresh_accounting_postgres.py`: 7/7
passed (3 inherited 182-a + 4 new), zero skips.

### 3.5 B2 unit matrix and call-site integration

- `tests/unit/test_pricing_service.py` (42/42): new
  pair-capture repository fake mirroring the real one-statement
  semantics, with capture-vs-single-row call counting, and a compact
  matrix over the REAL `PricingService.capture_pricing_and_fx` + family
  estimates: Chat (USD FX), EUR identity (read-free rate 1, no FX row),
  missing-rate fail-closed (`FxRateNotFoundError`), strict
  Responses/Codex (complete metadata path + fail-closed on partial
  metadata), Audio speech (request price dominance), Embeddings,
  Realtime (max of token and request pricing), fixed-request module
  billing (zero tokens, `request_price * fx`), and hosted Responses
  pre-fence facts/reuse (external-tool pricing parsed into the single
  `PricingCapture`; estimate reuses it with zero further lookups).
  No new standard-v1 capabilities granted.
- Five HTTP call-site integration tests (one per existing forwarding
  file: `test_v1_chat_completions_forwarding.py`,
  `test_v1_responses_quota.py`, `test_v1_audio_forwarding.py`,
  `test_v1_embeddings_forwarding.py`, `test_v1_realtime_forwarding.py`):
  the actual happy-path request flow passes the captured price+FX facts
  (distinctive row IDs) into the family cost estimate — captured objects
  asserted to reach the estimate unchanged. No full HTTP matrix rebuilt.
- Unit totals, six files, zero skips, zero failures: 171/171
  (pricing 42, responses 83, chat 24, audio 7, embeddings 7, realtime 8).

### 3.6 B4 — documentation corrections

`docs/catalog-refresh.md` and `docs/cli-reference.md` now name the ACTUAL
implementation execution codes — `apply_baseline_stale` (was
`apply_stale_baseline`), `apply_admin_unknown` (was
`apply_unknown_admin`), `apply_supersession_guard_failed` (was
`apply_close_guard_drift`) — in the prose and the exit-code tables.
"One effective instant" now states T is chosen once inside the
transaction AFTER all checks pass (not necessarily at transaction
start). The Limits section distinguishes permitted DB network from
absent source/provider/research network: `apply`'s only network contact
is the authenticated PostgreSQL connection to the reviewed target; it
performs no source retrieval, provider inference, or research traffic.
`docs/accounting.md` and `docs/pricing-catalog.md` were checked; no
wrong statements found; unchanged.

## 4. Runtime repairs

NONE. No runtime (non-test, non-doc) file changed in 182-b. Every
focused case passed against the 182-a implementation; the order's
repair clause was not triggered.

## 5. Verification (focused, per order)

- Focused real-PG boundary (owned `slaif182btest`): 16/16 apply + 7/7
  accounting integration, zero skips (exact command in section 3).
- Focused unit boundary: 171/171 across the six files above, zero
  skips.
- `ruff check` on all changed Python files: All checks passed
  (CI gate is `ruff check app tests`).
- `git diff --check`: clean.
- `scripts/check_documentation.py`: `DOCUMENTATION_CHECK=OK files=91`.
- No full local matrix (per order); no new browser run (rendered
  behavior unchanged — inherited final-head browser evidence plus the
  fresh CI browser job on the implementation and SELF heads suffices).

## 6. GitHub CI (required checks)

- INHERITED (not re-derived here): CI run `38433431566` at
  `7f5965801cc1a97729abf2c630c9de770b84d880` — all 10 checks SUCCESS;
  the independent archive (62 passes: apply 15 / planning 10 /
  sealing 37) and the 543/543 19-file unit list, plus the 182-a
  integration evidence, remain the authority for the A1–A4/AP1–AP5
  apply mechanics.
- NEW implementation head `16489a85d100b8918eb9c965aa85c0c2422ed640`:
  all 10 required checks SUCCESS.
- Report-only SELF head: the report-only publication commit triggers a
  fresh run of the 10 required checks on the PR head; per protocol their
  acceptance is strategic. This report is immutable and is not rewritten
  for them.
- No merge; no auto-merge; no release/tag.

## 7. Files changed (implementation head)

Tests (primary allowed paths):
- `tests/integration/test_catalog_refresh_apply_postgres.py`
  (+1354: B1/B3 USD fixtures, helpers, 9 tests)
- `tests/integration/test_catalog_refresh_accounting_postgres.py`
  (+499: B2 block, 4 tests)
- `tests/unit/test_pricing_service.py` (+443: B2 matrix)
- `tests/unit/test_v1_chat_completions_forwarding.py` (+57)
- `tests/unit/test_v1_responses_quota.py` (+41)
- `tests/unit/test_v1_audio_forwarding.py` (+51)
- `tests/unit/test_v1_embeddings_forwarding.py` (+61)
- `tests/unit/test_v1_realtime_forwarding.py` (+59)

Docs (B4):
- `docs/catalog-refresh.md` (code names, T wording, network distinction)
- `docs/cli-reference.md` (code names)

Total: 10 files, 2573 insertions, 12 deletions.

## 8. Preserved state

- Prior 182-a order/report bytes, `oap/active` (182-b), all earlier
  reports/orders, `.codex`, local catalogs, the
  `/tmp/slaif-182a-baseline-check` worktree, the archived human edit
  `review-artifacts/182-a-review/human-local-apply-edit-20261013.py`,
  the broken copied venv, and untracked `CODEX-SESSIONS.md`/`codex.sh`
  all untouched.
- Owned PG container and its 182-a databases preserved; the new
  disposable `slaif182btest` is owned and removable after publication.

## 9. Remaining limits

- No production catalog import, no real upstream inference, no release/
  tag, no production-certification claim.
- The real-PG proofs use the owned disposable PostgreSQL 16 container
  (owned synthetic instance per the order's setup clause), not
  testcontainers.
- 182 solves A1–A4/AP1–AP5 for this PR only; objective 183 (isolated
  Codex research) and 184 (final wrappers/clean-install/full E2E) remain
  separate; 182 stays unresolved until all original acceptance gates
  (including strategic review and the fresh SELF-head checks) are
  satisfied.
