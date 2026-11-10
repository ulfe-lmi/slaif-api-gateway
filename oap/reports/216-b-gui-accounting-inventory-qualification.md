# 216-b immutable report — final-head CI qualification repair (same PR)

## Identity and activation

- Objective: 216 (continuation 216-b, AMEND_EXISTING_PR); ONE PR #372,
  branch `oap/216-gui-accounting-operations`; no 217 activation while
  216 remains unresolved.
- Order: `oap/orders/216-b-gui-accounting-inventory-qualification.md`,
  committed here byte-unchanged (root-authored, bytes immutable).
- Active pointer: `oap/active` = `216-b`, committed byte-unchanged.
- Pre-activation verified state: remote main
  `f2df0e82df8766740d9ac169ea56ffd7a3cb1f1e`; PR #372
  OPEN/MERGEABLE, no auto-merge; 216-a SELF head
  `4d83197ef5ee67f95a6505cb32184a9081e088d3` (sole parent IMPL
  `95ca15d205523e4b7a5d9cdd794caa118e203eb6`); Report A (16,011
  bytes, SHA-256 `ce92dceed86143572eb1da77e8509e536d3654241f0d28a08ac60d3b6f19e3ef`)
  and order A (18,704 bytes, SHA-256
  `7d5d9bb09acfb70357e071367889cbec1f496f341fd16677c8db5f7addd70f85`)
  byte-unchanged and remain immutable (no retroactive edits).
- Demonstrated blocker (classified by root as
  ROOT_216A_CI_CLASSIFIED): final-head CI 42730736624 unit job 2
  failed / 7115 passed / 1 skipped (skip is NOT a pass) - stale
  admin-table inventory (expected 40, actual 46) and stale
  labeled-wrapper inventory (expected 38, actual 44); PostgreSQL
  integration job 129547868778: 7 failed / 639 passed / 9 skipped,
  all 7 in the 216 module, first failure the stale raw-HTML regex
  (review help text now reflows across "session for / 15 minutes")
  with downstream counter/preservation cascades from the missed
  settle_r1 checkpoint.

## Publication topology

Implementation head SHA: 85507732070d5129fcbc2aaf154db15b72a14cf4
Report publication commit: SELF

- Implementation head `85507732…` (sole parent = 216-a SELF
  `4d83197e…`); this report-only SELF commit has SOLE parent the
  literal implementation head and its diff contains ONLY this report
  file.
- PR: https://github.com/ulfe-lmi/slaif-api-gateway/pull/372 (ONE PR,
  never merged, no auto-merge); branch
  `oap/216-gui-accounting-operations`; PR description updated around
  the final G14 behavior and qualification.

## Changed paths (exact)

- `tests/unit/test_admin_usability_inventory.py` - expected 40 ->
  46 sortable admin tables, with the six G14 additions annotated
  (expired, fences, holds, provider-completed, review reviewed-rows,
  review per-row outcomes). Every structural, accessibility,
  sorting, empty-row and column assertion preserved; no `>=`, no
  deleted checks, no discovery changes, no skip/xfail.
- `tests/unit/test_admin_slaif_design.py` - expected 38 -> 44
  labeled/focusable table wrappers, annotated.
- `app/slaif_gateway/web/templates/accounting_operations/provider_completed.html`
  - empty-state row colspan 12 -> 11 (the leaf column count the
  existing structural assertion requires).
- `app/slaif_gateway/web/templates/accounting_operations/review.html`
  - added the two missing fixed `data-no-sort` empty-state rows
  (colspan 11 "No reviewed rows."; colspan 4 "No per-row
  outcomes.") using the standard `for...else` convention of every
  other admin table. Unknown-outcome truth and all guards preserved;
  working forms, values, layout and visual style unchanged; no
  aesthetic change.
- `tests/integration/test_admin_accounting_operations_216_postgres.py`
  - ONLY the session-bound 15-minute visible-hint assertion made
  whitespace-robust by normalizing visible/HTML whitespace before
  the search (the template reflows the line). All actual
  expiry/financial/audit/state checks retained verbatim.
- `docs/verification/gui-cli-parity.md` - minimal 216-b
  qualification note in the existing 216 section (allowed optional
  note; no new evidence catalog/document).
- `oap/active` (= `216-b`) and the 216-b order - root bytes,
  committed unchanged.

## No-source-change boundaries

No application Python, CLI, DB/schema/migration, dependency,
adapter, request-acceptance, authorization, CSRF, secret-protection,
accounting-math, quota, replay-ownership, policy, or provider-
permission change in 216-b. No new store, job platform, diagnostic
mechanism, or supporting infrastructure. No speculative analyzer
cleanup (the ten CodeQL advisories remain for root assessment and
are outside this repair's scope). Core accounting math/defaults and
all CLI `reconcile-*` behavior remain byte-for-byte as at 216-a.

## Evidence (exact receipts; fresh qualification venv
`/tmp/slaif216-qualification-venv`, ambient DATABASE_URL /
TEST_DATABASE_URL cleared, `-q -p no:cacheprovider`, true pytest
exits)

1. The TWO primary unit modules run once after the count update and
   the conditional markup repairs (the pre-repair run demonstrated
   the three real template violations; the cited receipt is the
   passing run): `test_admin_usability_inventory.py` +
   `test_admin_slaif_design.py` = 133 PASS / 0 fail / 0 error / 0
   skip, 4.952 s, collected 2026-11-10T01:10:26.636889+00:00
   (`/tmp/slaif216/inventory-216b.xml`,
   SHA-256 `431c4740bde1d4b0861dc11db6d3b5347c3dec7a6392e798520e28a9e0090014`),
   pytest exit 0.
2. Full 20-case owned-PostgreSQL module run ONCE after the
   whitespace-robust hint fix (required because the matrix actually
   failed at 216-a head): `test_admin_accounting_operations_216_postgres.py`
   = 20 PASS / 0 fail / 0 error / 0 skip, 17.209 s, collected
   2026-11-10T01:16:06.353688+00:00
   (`/tmp/slaif216/integration-216b.xml`,
   SHA-256 `4402a5e5f05f174287a468481871e27e71cdf89884f4bcb1adf8d43a1e8709af`),
   pytest exit 0; no unhandled-thread or unawaited-coroutine
   warnings in the run log. Fresh labeled owned PostgreSQL 16
   fixture; synthetic rows; controlled fault seams labeled
   synthetic (not provider/installed evidence).
3. OAP governance on the exact 216-b order/active:
   `test_oap_governance.py` = 9 PASS, pytest exit 0
   (2026-11-10, 01:12Z local run).
4. Scoped Ruff 0.16.7 + `py_compile` over ALL changed Python (the
   two unit modules, the PG module): clean.
5. Diff/docs check: exactly the allowed 216-b paths changed; no
   216-a order/report bytes touched; no protected untracked file
   (`CODEX-SESSIONS.md`, `codex.sh`, `uv.lock`) read, staged, or
   modified.

## Source-snapshot reuse (honest, per accepted directive)

- 216-a accepted evidence is reused unchanged: unit43 (mocked
  seams), owned-PG20 (superseded for the hint assertion only by the
  current 20-case run at the 216-b head), Chromium8 (all four
  action families / no-JS / keyboard; visual gate cleared by root
  on the 00:32:41Z captures), consumer52 (52 unique, not 104),
  choices+OAP84. None of the 216-b changes touches any of those
  modules' asserted contracts, so they were NOT rerun.
- Root additionally verified the previously unexercised
  BEFORE_COMMIT fault at SELF `4d83197e` using the existing fresh-
  owned PostgreSQL 16 fixture and current HTTP/helper paths: fault
  hit; UI unconfirmed / NOT-rollback; full relevant mapped
  accounting state unchanged, no ledger/audit insertion,
  reservation pending; the exact owned container
  `9fed1b63aa2c649233bfbe87bb41c3ba965883efd8e25513d8f0eec3af80c1cc`
  was owner-verified and removed. This is EXTRA root verification
  after the A report, NOT part of its 20-case receipt, and is not
  recast as such.
- Qualification of Report A shorthand (preserved, A immutable):
  Report A's route-count shorthand says "2 apply POSTs"; the actual
  source has 3 apply POST routes (expired, external-tool holds,
  provider-completed recovery). This B record states the accurate
  count; Report A is not edited.

## Blocked / not-run limits (not passes)

- Final-head GitHub checks for the 216-b head are PENDING at
  publication and are NOT claimed as passes; root owns final
  CI/review/merge/main verification.
- Not rerun in 216-b (no relevant change/failure): the full local
  unit/integration/browser/CLI/provider matrix, the Playwright
  module, the six consumer modules, record-choices+OAP (cited
  216-a receipts), and the broader integration suite.
- No installed-qualification, live-provider, real Codex, real
  mail, deployment, or production claim; the final 219 installed
  whole-GUI gate remains open and mandatory. G15 (catalog
  workflows) and G17 (admin accounts) remain open and are untouched.

## Deviations and process notes

- The first 216-b run of the two primary modules (133 collected,
  1 failed) demonstrated the three real new-template violations
  that the existing structural assertions exposed; the permitted
  conditional markup repair was applied minimally and the cited
  receipt is the single passing re-run of the same two modules.
- The 216-b publication waited on the explicit
  ROOT_216A_CI_CLASSIFIED classification of the old CI (terminal
  8 SUCCESS / 2 FAIL; PG job 129547868778) before any push or
  report - the existing remaining-CI dependency, not fresh human
  permission.
- No reset/clean/stash, no amend of a pushed commit, no force-push,
  no second PR, no merge, no auto-merge. The sole canonical control
  waiter and root response ownership were preserved throughout;
  response OK for 216-b is sent exactly ONCE after this verified
  handoff.
