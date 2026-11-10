# 216-a immutable report — GUI reviewed accounting recovery (G14)

## Identity and activation

- Objective: 216-a (G14 of `docs/MISSING_GUI_FUNCTIONALITY.md`), PR mode
  CREATE_NEW_PR.
- Order: `oap/orders/216-a-gui-accounting-operations.md`, 18,704 bytes,
  SHA-256 `7d5d9bb09acfb70357e071367889cbec1f496f341fd16677c8db5f7addd70f85`,
  committed here byte-unchanged (root-authored, bytes immutable).
- Active pointer: `oap/active` = `216-a` (5 bytes, no trailing newline),
  committed byte-unchanged.
- Base: `f2df0e82df8766740d9ac169ea56ffd7a3cb1f1e` (verified
  `origin/main`, merge of PR #371 / 215-a).
- Branch: `oap/216-gui-accounting-operations`; IMPL head
  `95ca15d205523e4b7a5d9cdd794caa118e203eb6`; PR
  https://github.com/ulfe-lmi/slaif-api-gateway/pull/372 (ONE PR).
- Report head: this report-only SELF commit (sole parent = IMPL head;
  diff = this report file only).
- Model/profile: unchanged early-beta qwen3.8-27b (A100 Q8) medium;
  single pane CLI; no helpers/nested agents.

## What 216-a delivers (G14)

A bounded "Accounting operations" area under the existing `/admin`
exposure (Operations index link), built ONLY on the existing
reconciliation/hold services:

1. **Four read-only candidate views** (all signed-in admins): expired
   pending reservations; external-tool accounting holds;
   provider-completed recovery rows; external-tool fences (READ-ONLY;
   no release/reset/unblock surface exists). Each table renders an
   HONEST cap of at most 200 rows with explicit "Up to 200 rows / no
   completeness claim" help; no more/has_more/totals are invented from
   projected length. Token quantities use the existing millions-of-
   tokens readouts with exact raw `data-sort-value` sort keys; money
   keeps the monetary formatter; unknown/missing facts render
   "unknown", never zero. Credential-shaped values (manual fields,
   model metadata, picker initial options AND selected/AJAX
   hydration) are refused or withheld with the existing pure alias
   guards across FULL responses (the model kind applies a bounded
   post-hydration end filter; ordinary IDs are preserved and masked
   placeholders are not selectable identities).
2. **Exact known-record selection beyond the capped views** on each
   ACTIONABLE view: the existing searchable record-choice control
   (latest 100 plus older-value search and selected hydration; closed
   `quota_reservation`/`usage_ledger` kinds, ID-only labels) plus a
   no-JS exact-identifier textarea fallback. The new bounded
   selection parser accepts up to 200 canonical unique UUIDs (repeated
   widget values and newline no-JS input), refuses 201 predictably,
   retains the alias guards/dedup and exact targets, and does NOT
   raise the unrelated global list-filter cap (20) or truncate.
3. **Reviewed recovery actions** (dry-run preview -> stateless signed
   review -> explicit confirm-and-apply):
   - release ONE or a bounded selection of EXPIRED ordinary pending
     reservations (external-tool-fenced and provider-completed
     `needs_reconciliation` rows are refused, never forgiven at zero);
   - reconcile ONE external-tool hold as **finalize-actual** (explicit
     finite nonnegative cost, nonnegative integer tokens, explicit
     boolean outcome, nonblank reason <= 500 characters; sealed
     `operator_reconciliation / operator_asserted` MANUAL provenance,
     never provider-verified) or **release-no-charge** (its DISTINCT
     explicit confirmation checkbox; all actual values refused). The
     mutually exclusive intent contract is enforced at the form, in
     the signed review, and again by the shared Core at execution;
     confirmation is never inferred from the selected mode.
   - recover ONE or a bounded selection of provider-completed rows
     from STORED authoritative evidence only (no cost override;
     missing/nonpositive facts refuse unchanged).
4. **Privilege**: views/preview/review are available to every
   signed-in admin; confirm-and-apply requires the authenticated
   user's EXISTING `superadmin` role (fixed safe refusal otherwise).
   This is the only enforced role boundary in the current system;
   legacy broad admin authority elsewhere is unchanged, there is no
   promote command and no automatic elevation (superadmin is created
   explicitly via `admin create --superadmin`).
5. **Review token**: a bounded, escape-budgeted STATELESS signed
   token (HMAC) bound to the admin, the session, its 15-minute
   expiry, and the sealed source facts. It is NOT one-use: there is
   no durable consumption store. Replay is safe because apply
   re-verifies the signed facts (posted values confer nothing),
   re-locks everything under fresh canonical locks, and compares
   sealed fingerprints: a replay yields only a fixed refusal or a
   safe already-resolved outcome, never a duplicate settlement.
6. **Atomicity and truthfulness**: apply acquires all required
   ledger/reservation prerequisite locks, then acquires the DISTINCT
   linked gateway keys in ascending UUID order via the existing fresh
   `populate_existing` method BEFORE any source comparison or Core
   arithmetic (Core math reuses those locked fresh instances; running
   key balances stay OUT of fingerprints). Any INCLUDED relevant-
   source change (including terminal rows, which are never skipped
   before comparison) refuses and rolls back the WHOLE selection;
   excluded/newly-matching rows are never added. A single
   already-resolved row is a safe already-resolved outcome (accepted
   409-class refusal with no duplicate counters/audit). Dry-run
   statuses are CURRENT observed facts (pending / current accounting-
   reservation state), displayed as observed, never as post-apply
   predictions; the review page states the intended action and the
   if-applied RESERVED amounts that would be RELEASED (release/no-
   charge) or the operator-asserted actuals that would be BOOKED
   (finalize).
7. **Commit-fault truthfulness**: a lost commit acknowledgement is
   reported as UNCONFIRMED - the commit MAY have committed or rolled
   back; the UI explicitly says this is NOT a rollback promise and to
   verify row state and the audit log before acting again. The
   controlled after-commit fault test proves the durable-committed
   case; that does not mean every fault commits. Results distinguish
   committed, refused, and uncommitted-row outcomes per row.

## Change set (exact)

- NEW `app/slaif_gateway/api/admin_accounting_operations.py`
  (routes: 4 views, 3 preview POSTs, 2 apply POSTs; safe fixed
  refusal messages; display-only redaction; no arithmetic).
- NEW `app/slaif_gateway/services/admin_accounting_operations.py`
  (bridge: exact-target binding, fingerprint build/compare, fresh
  ordered lock prelocks, whole-batch refusal, outcome classification;
  no Core math duplicated).
- NEW `app/slaif_gateway/web/templates/accounting_operations/` (6
  templates: index, expired_reservations, holds, provider_completed,
  fences, review).
- `app/slaif_gateway/api/admin_review_intent.py` (additive: accounting
  review purpose with the corrected nonblank reason <= 500
  CHARACTERS boundary, 200-target escape-budgeted caps; existing
  purposes untouched).
- `app/slaif_gateway/api/admin_record_choices.py` +
  `app/slaif_gateway/services/admin_record_choices.py` (additive:
  closed `quota_reservation`/`usage_ledger` kinds; `accepted_prefixes`
  keyword on `load_choices` with model-kind credential-shape
  withholding including the post-hydration end filter).
- `app/slaif_gateway/db/repositories/quota.py` / `usage.py`
  (additive: fresh ordered `FOR UPDATE` bulk reads with
  `populate_existing`; no existing interface changed).
- `app/slaif_gateway/api/admin.py` (generic loader forwards the
  accepted prefixes; wiring only), `main.py` (router composition
  only), `web/templates/operations/index.html` (entry link).
- NEW tests: `tests/unit/test_admin_accounting_operations_216.py`
  (43), `tests/integration/test_admin_accounting_operations_216_postgres.py`
  (20), `tests/browser/test_admin_accounting_operations_216.py` (8).
- `tests/unit/test_oap_governance.py` (whitespace-only declaration
  parser fix; closed CREATE_NEW_PR value; negative cases and the
  one-objective-one-PR invariant unchanged).
- Docs (exact allowed paths, G14 scope only):
  `docs/MISSING_GUI_FUNCTIONALITY.md` (section 18 + header),
  `docs/admin-usability.md` (section 17), `docs/accounting.md`
  (operator-workflow pointer), `docs/security-model.md` (reviewed
  accounting recovery section), `docs/cli-reference.md` (parity note),
  `docs/upgrade-runbook.md` (recreate/restart note), the three
  reconciliation runbooks (Admin Console subsections),
  `docs/runbooks/admin-access.md` (legacy-authority qualification,
  G14 apply exception, offline `--superadmin` setup),
  `docs/verification/gui-cli-parity.md` (216-a section) and
  `docs/verification/README.md` (index entry).

Explicitly unchanged: every `app/slaif_gateway/cli/` file (zero CLI
diff; all `reconcile-*` commands byte-for-byte identical behavior),
Core accounting math/defaults/error taxonomy, schema (NO migration),
dependencies (no pyproject/lockfile change), Nginx/env surface.

## Evidence (exact receipts; scopes stated)

All runs: fresh disposable qualification venv
`/tmp/slaif216-qualification-venv` (root-rebuilt from pyproject
`.[dev]` via uv; Python 3.12.15, SQLAlchemy 2.1.8, pytest 9.2.0,
FastAPI 0.162.2, httpx 0.28.1, Playwright 1.65.0, Ruff 0.16.7;
Chromium 1254, browser 158.0.8127.18), ambient `DATABASE_URL` /
`TEST_DATABASE_URL` cleared, `-q -p no:cacheprovider`, JUnit under
`/tmp/slaif216/`.

1. Focused unit: `tests/unit/test_admin_accounting_operations_216.py`
   = 43 PASS / 0 fail / 0 error / 0 skip, 5.576 s, collected
   2026-11-09T23:48:22.640240+00:00
   (`/tmp/slaif216/unit-216.xml`,
   SHA-256 `bc7f32a92bf3e950c352d90678f159adad30b7bb15a326fc5cf059ac8d9e8743`).
   Scope: mocked DB/service seams - NOT native proof.
2. Native owned-PostgreSQL:
   `tests/integration/test_admin_accounting_operations_216_postgres.py`
   = 20 PASS / 0 fail / 0 error / 0 skip, 17.464 s, collected
   2026-11-10T00:02:44.922342+00:00
   (`/tmp/slaif216/integration-216.xml`,
   SHA-256 `31cda1abe911b8a11c756d53cbd7d2ac3ec544390b210065c1fb7d069e57d218`).
   Real HTTP against a fresh labeled tmpfs PostgreSQL 16 owned
   container with synthetic rows: exact counter chains, manual
   provenance, whole-batch source-change refusal, safe
   already-resolved repeat (no duplicate counters/audit), waited-row-
   lock refusal, cross-key ascending prelock order, beyond-200 exact
   selection (valid 200-acceptance distinct from 200-with-missing
   refusal), commit-fault pre-commit rollback and ack-loss durable
   row at real transaction seams (controlled per-session event hooks;
   labeled SYNTHETIC fault seams, not provider/installed evidence).
3. Playwright (real Chromium + real uvicorn + owned PG, synthetic
   seed): `tests/browser/test_admin_accounting_operations_216.py` =
   8 PASS / 0 fail / 0 error / 0 skip, 17.030 s, collected
   2026-11-10T00:32:41.015250+00:00
   (`/tmp/slaif216/browser-216.xml`,
   SHA-256 `cf136d7d5a803082fb9daf2dc5a06617a047e12ddd0fd7cdb71a8114c91ab465`).
   All FOUR action families through the actual existing forms
   (preview -> review -> confirm -> result) with DB oracles, FULL-
   response credential canaries (masked/withheld; no masked-
   placeholder identity), no-JS/keyboard paths (including the refused
   no-charge re-entry), beyond-cap picker search/preview/apply,
   desktop + narrow captures under `/tmp/slaif216` (viewport captures
   for the long 200-row views; right-scrolled Details and narrow
   review viewports for the review table). Root independently
   reviewed the refreshed desktop + narrow captures BEFORE this
   handoff and cleared the visual gate at the 00:32:41 snapshot.
4. Directly affected reconciliation/hold/CLI consumers (exact six):
   `test_reservation_reconciliation_service.py`,
   `test_provider_completed_reconciliation_service.py`,
   `test_external_tool_hold.py`, `test_cli_quota_reconciliation.py`,
   `test_cli_quota_reconciliation_safety.py`,
   `test_provider_completed_reconciliation_cli.py` = 52 PASS / 0 fail
   / 0 error / 0 skip, 13.457 s, collected 2026-11-10T00:21:29.389068+
   00:00 (`/tmp/slaif216/affected-consumers.xml`,
   SHA-256 `94d0ecd8ebf2728e28e0a46f85effdaf25f384be929443d491a564d10a8b048a`).
5. Record choices + OAP governance on the exact 216 order/active:
   `test_admin_record_choices.py` + `test_oap_governance.py` = 84
   PASS / 100%, pytest exit 0 (00:07:10Z run; root-accepted, cited).
6. Scoped static gate: Ruff 0.16.7 + `py_compile` over ALL changed
   Python files - clean (actual compilation; `ast.parse` alone was
   never accepted as proof). CLI byte-unchanged check: `git diff`
   over `app/slaif_gateway/cli/` empty. Docs/diff check: exactly the
   allowed doc paths changed.

## Evidence-scope reconciliation (honest)

- The unit43 and PG20 receipts predate the FINAL presentation- only
  corrections: human UTC-to-seconds display (template datetimes and
  the expired `observed.expires_at` display string; the RAW
  `isoformat()` fingerprint precision is unchanged), accessible
  `aria-label` row selectors (visual caption removed), and the review
  Details-column scoped `min-width`. No unit/PG asserted contract
  touches those strings (verified by grep of both modules), so those
  receipts are cited for their asserted contracts; the final browser
  run (00:32:41) covers the final presentation state.
- The PG module's repeat-row test received one PRESENTATION assertion
  correction after PG20 (raw `already_resolved` -> approved human
  label "Already resolved"); the no-duplicate financial/audit checks
  are untouched and the corrected assertion matches the page text the
  PG20 run already rendered. Per the accepted directive, the backend
  was not rerun merely for that label change.
- One redundant run of the six consumer modules occurred before the
  root filename clarification (first run wrote a different JUnit
  filename; both runs: 52/0/0/0). The 00:21:29Z receipt is cited.
- The initial browser run failed three NEW UI-flow tests (used-
  counter oracle column family; fixed-400 error-page re-entry for the
  refused no-charge preview); both were fixture corrections (no
  product change) and the module then passed and has passed at every
  subsequent final snapshot.
- The root-rebuilt disposable qualification venv is disclosed as the
  local execution environment for ALL runs above (the earlier
  designated venv was corrupted by missing package files; no source,
  dependency, schema, or lockfile change resulted).

## Limitations (never claimed)

- NOT an installed-qualification: the full 219 installed whole-GUI /
  config / assets / identity gate remains open and mandatory.
- No live provider, no real Codex, no real email, no upstream calls;
  all fixtures synthetic; the owned PostgreSQL fixture is a fresh
  labeled disposable tmpfs container; commit-fault seams are
  controlled per-session event hooks (labeled synthetic), not
  production fault injection.
- No schema migration, no new RBAC model, no release/tag, no
  deployment or production claim; RC2 release state is unchanged.
- G15 (catalog workflows), G17 (admin accounts) and the 219 gate
  remain open; nothing in 216-a touches them.

## Deviations and process notes

- Visual review was first BLOCKED (illegible review/provider
  captures) and cleared only after the accepted template corrections;
  the accepted snapshot is the 00:32:41Z capture set.
- No merge, no auto-merge, no force-push, no amend; the order and
  active pointer are committed byte-unchanged; protected untracked
  files (`CODEX-SESSIONS.md`, `codex.sh`, `uv.lock`) were never read,
  staged, or modified; no second control waiter was created (the
  canonical control waiter and the sole root response waiter
  remained the only readers).
- Response OK will be sent exactly ONCE, after this published
  handoff.
