# OAP Execution Report — Objective 182-c: Deterministic Accounting Evidence

Report status: IMMUTABLE (finalized at the exact final implementation
head `cf0bf38ed41c300a089fa505472e03a87d1027b4`; published atomically as
the immutable report; the report-only SELF commit is its publication
commit).

## 1. PR identity and merge state

- PR: #320 `feat: apply reviewed catalog changes atomically with pricing
  history` (the unique 182 PR; 182-c amends it, AMEND_EXISTING_PR).
- Branch: `oap/182-atomic-catalog-apply`.
- Implementation head: `cf0bf38ed41c300a089fa505472e03a87d1027b4`
  (first parent of the SELF commit).
- Parent chain: `5395c9db86570d49719a4fc0491cc9adc17ac390` (182-c
  activation: order + `oap/active`) on `73578577c04760ef0a5027ecb37c2e242b049781`
  (182-b report-only SELF).
- Report-only SELF commit: the publication commit of this report;
  first parent = implementation head; only this report path differs.
- Merge performed: NO. Auto-merge: not requested/enabled. Coding agent
  never merges.
- Order: `oap/orders/182-c-deterministic-accounting-evidence.md` committed
  unchanged by the activation commit; `oap/active` = `182-c` (5 bytes,
  no LF). The prior 182-a and 182-b orders/reports remain IMMUTABLE and
  untouched.

## 2. Environment

- Coding checkout `/home/janezp/codex-work/slaif-api-gateway`; strategic
  root `/home/janezp/codex-supervision/slaif-api-gateway`.
- Python 3.12.15 (`/tmp/slaif-181c-strategic-venv`), pytest 9.1.1, Ruff
  (venv).
- Owned PostgreSQL 16.15 container `slaif182a-pg-a76441e6` (label
  `slaif.182a.owned=true`, loopback 127.0.0.1:49839, synthetic user
  `slaif_synth`, no persistent volume), reused after ID/label
  verification with a NEW disposable database `slaif182ctest` migrated to
  head `0025_catalog_refresh_applications`. Derived
  `TEST_DATABASE_URL` only; credentials in an owned `chmod 600` file,
  never printed. 182-a and 182-b databases preserved.
- No system packages, no shared 5432, no `DATABASE_URL` contact, no real
  source GET, no provider key, no real email, no production import.

## 3. What 182-c proves (new evidence, this commit)

All new proofs run on the owned disposable PostgreSQL 16 (`slaif182ctest`)
with the exact command shape:

    TEST_DATABASE_URL=<derived owned URL> \
    /tmp/slaif-181c-strategic-venv/bin/python -m pytest <file(s)> \
    -p no:cacheprovider --no-header -q

Zero skips recorded as PASS for every file below.

### 3.1 Correction of 182-b report section 3.1 (bootstrap description)

Prior reports are IMMUTABLE; this correction is recorded here only. The
182-b section 3.1 wording for
`test_bootstrap_both_providers_usd_creates_required_fx` overstated the
bootstrap outcome by conflating it with the seeded refresh fixture. The
ACTUAL bootstrap flow asserted by that test is:

- The actual CLI review runs with `--first-install` and exits **10**
  (sealed `new_model_exposure` warnings), not exit 0; the apply is
  performed with `--ack-warnings new_model_exposure` (plus
  `--confirm`/actor/reason) and exits 0, `committed`.
- The bootstrap commit is EXACTLY: two providers, two routes, two USD
  pricing rows, and one USD->EUR FX row (rate `0.925925926`, derived
  reciprocal from the EUR-USD source pair, `new_valid_from` = the single
  effective T; both new pricing rows stamped at that same T).
- The retained third route/pricing row (the UNSELECTED retained model)
  and the selected OpenRouter pricing row's reviewed finite FUTURE
  validity end (now+30d) belong to the SEEDED refresh fixture
  (`_seed_catalog_usd`) that underlies the refresh tests; they are NOT
  part of the bootstrap commit. The 182-b refresh-scope evidence
  (supersession at one T, closure of the finite future end, rollback
  atomicity) remains valid as stated for the refresh tests, which do run
  against that seeded fixture.

### 3.2 C1 — deterministic writer pause in the default-isolation test
(`tests/integration/test_catalog_refresh_accounting_postgres.py`,
`test_default_isolation_paired_capture_price_and_fx_across_actual_apply`)

- The previous `lock_held` event signaled arrival but did not pause the
  writer; the mid-apply capture therefore raced the writer's commit.
  Now the test-local `lock_catalog_tables` wrapper sets `lock_held` only
  AFTER the ACTUAL catalog locks are acquired inside the writer's open
  transaction, and the writer then HOLDS its transaction and catalog
  locks until a second test-local release event `reader_done` is set.
- All waits are bounded (`asyncio.wait_for`: 120s for the lock signal,
  120s for the reader's wait on it, 180s for the writer task), and the
  release is guaranteed by the reader-side `finally` — the writer can
  never hang on reader failure, including exceptions. No sleeps are used
  as synchronization; no production hook, lock, isolation, or
  instrumentation change.
- Assertions: the reader's isolation level is read from the database
  (`current_setting('transaction_isolation')` = `read committed`, the
  default); the pre/mid/post captures are complete OLD / OLD / NEW fact
  tuples (values AND row IDs — the post-commit capture asserts the NEW
  pair including its new row IDs); the explicit `at=T±1s` boundary
  captures resolve the supersession history exactly; the paired-one-SQL
  and zero-extra-estimate-SQL evidence remains in the sibling tests of
  the same file, unchanged.

### 3.3 C2 — retry beyond the ACTUAL finite expiry
(`tests/integration/test_catalog_refresh_apply_postgres.py`,
`test_aged_retry_returns_original_outcome_and_refuses_new_stale_work`)

- The seeded refresh fixture's selected OpenRouter pricing row carries an
  ACTUAL reviewed finite future validity end (seed: now + 30d). The test
  now captures that end (`seeded["pricing_model_until"]`) and freezes the
  test clock at `end + 1 day` — strictly past the reviewed finite end
  (previously the test advanced only 3d, before that end), and it also
  records `bundle_created_at` and asserts the frozen now is strictly past
  `bundle_created_at + 72h`, the source-freshness block limit.
- Explicit assertions document both inequalities:
  `frozen > seeded["pricing_model_until"]` and
  `frozen > bundle_created_at + timedelta(hours=72)`.
- Behavior asserted is unchanged: the authenticated retry of the SAME
  bundle returns the original actor/T/counts (known-committed lookup
  before current gates); a different unapplied stale bundle is still
  refused; no extra rows/audit, no resealing, no archived timestamps
  refreshed, no freshness relaxation, no production clock change.

### 3.4 C3 — provider-completed recording via the production writer chain
(`tests/integration/test_catalog_refresh_accounting_postgres.py`,
`test_provider_completed_recovery_after_refresh_uses_real_old_capture_facts`)

- The recovery-state ledger row is no longer manually synthesized. The
  test reuses real capture -> real estimate -> reservation, then persists
  provider completion through the PRODUCTION writer chain:
  `AccountingService.record_provider_completed_before_finalization(
  reservation_id, authenticated_key, route, estimate, response,
  request_id, endpoint, started_at)` followed by the EXISTING state
  transition `mark_provider_completed_finalization_failed(usage_ledger_id,
  reservation_id, error)`; after commit the test reads the row back
  through the repository. The response is re-wrapped carrying a
  distinctive `json_body` content marker so metadata safety is
  testable; the now-unused `ActualUsage` import is removed.
- New assertions on the PRODUCTION-persisted row:
  `actual_cost_native = 0.0000405` (USD), `actual_cost_eur = 0.0000375`,
  `native_currency = "USD"`, `response_metadata.pricing_rule_id` /
  `fx_rate_id` = the OLD capture's row IDs, and the content marker is
  ABSENT from the serialized `response_metadata` (safe metadata:
  cost/provenance facts only, never response content).
- After the ACTUAL price+FX apply, `reconcile_provider_completed_recovery`
  (dry then execute) under a SQL listener issues ZERO
  `pricing_rules`/`fx_rates` statements — history is never re-priced from
  the refreshed catalog — and finalizes at the old persisted costs/IDs
  with the key counter at the old EUR cost `0.0000375`. The recovery
  phase itself is unchanged; the qualification is that the row under
  recovery was written by the real writer, qualifying
  capture-to-ledger propagation in production code.

### 3.5 C4 — honest documentation of DB network vs source traffic
(`docs/catalog-refresh.md`, Limits)

- The Limits paragraph now states the supported conditional DB contact:
  `collect` makes bounded live official-source retrieval calls and, only
  when `--refresh` is combined with `--db-url`, performs a read-only
  PostgreSQL baseline capture of the target database; it performs no
  Codex research. `verify` is fully offline. The other commands make no
  source, provider, or research traffic; their only possible network
  contact is the permitted PostgreSQL connection to their target
  database: `export-baseline` and `status` use it, `apply` uses the
  reviewed target, and `review` only when `--db-url` reads a live
  baseline. No broad doc rewrite; DB network is kept clearly distinct
  from source/provider/research traffic.

### 3.6 Focused totals

- `tests/integration/test_catalog_refresh_apply_postgres.py`: 16/16
  passed (7 inherited 182-a + 9 from 182-b), zero skips; C2 case among
  them.
- `tests/integration/test_catalog_refresh_accounting_postgres.py`: 7/7
  passed (3 inherited 182-a + 4 from 182-b), zero skips; C1 and C3 cases
  among them.
- Both files together: 23/23 passed, zero skips, exit 0. The three
  changed cases were first run as a focused set (3/3 PASS, node IDs
  `test_default_isolation_paired_capture_price_and_fx_across_actual_apply`,
  `test_aged_retry_returns_original_outcome_and_refuses_new_stale_work`,
  `test_provider_completed_recovery_after_refresh_uses_real_old_capture_facts`),
  then the two full files for their shared-fixture interactions.

## 4. Runtime repairs

NONE. C3 passed against the existing 182-a/182-b runtime; the order's
conditional repair clause (`services/accounting.py` /
`services/reservation_reconciliation.py`) was not triggered. No runtime
(non-test, non-doc) file changed in 182-c.

## 5. Verification (focused, per order)

- Focused real-PG boundary (owned `slaif182ctest`): 3 changed cases
  3/3 PASS, then both integration files 23/23 PASS, zero skips (exact
  command shape in section 3).
- `ruff check` on both changed test files: All checks passed
  (CI gate is `ruff check app tests`).
- `git diff --check`: clean.
- `scripts/check_documentation.py`: `DOCUMENTATION_CHECK=OK files=91`.
- No full local matrix (per order); units/browser/migrations inherited
  unchanged from the 182-b heads.

## 6. GitHub CI (required checks)

- INHERITED (not re-derived here): 182-b implementation head
  `16489a85d100b8918eb9c965aa85c0c2422ed640` and 182-b SELF
  `73578577c04760ef0a5027ecb37c2e242b049781` — all 10 checks SUCCESS on
  both; that evidence remains the authority for the A1–A4/AP1–AP5 apply
  mechanics and the 182-b proofs.
- NEW implementation head `cf0bf38ed41c300a089fa505472e03a87d1027b4`:
  all 10 required checks SUCCESS.
- Report-only SELF head: the report-only publication commit triggers a
  fresh run of the 10 required checks on the PR head; per protocol their
  acceptance is strategic. This report is immutable and is not rewritten
  for them.
- No merge; no auto-merge; no release/tag.

## 7. Files changed (implementation head, vs 182-b SELF)

Tests (allowed paths):
- `tests/integration/test_catalog_refresh_apply_postgres.py`
  (+7/−2: C2 real finite end + 72h freshness assertions)
- `tests/integration/test_catalog_refresh_accounting_postgres.py`
  (+68/−56: C1 two-event deterministic pause; C3 production writer
  chain + persisted-row assertions; unused import removed)

Docs (allowed path):
- `docs/catalog-refresh.md` (+8/−5: C4 Limits network-traffic wording)

Activation commit (separate, on the same branch/PR):
- `oap/orders/182-c-deterministic-accounting-evidence.md` (+116,
  strategic bytes unchanged) and `oap/active` (182-c, 5 bytes, no LF).

## 8. Preserved state

- Prior 182-a/182-b order/report bytes, `oap/active` history, all
  earlier reports/orders, `.codex`, local catalogs, the
  `/tmp/slaif-182a-baseline-check` worktree, the archived human edit
  `review-artifacts/182-a-review/human-local-apply-edit-20261013.py`,
  the broken copied venv, and untracked `CODEX-SESSIONS.md`/`codex.sh`
  all untouched.
- Owned PG container and its 182-a/182-b databases preserved; the new
  disposable `slaif182ctest` is owned and removable after publication.

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
  satisfied. No full-goal-complete claim at this intermediate boundary.
