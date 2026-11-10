# OAP Work Order — 216-a

Identifier:216-a
Numeric objective:216
PR mode:CREATE_NEW_PR

## Objective and verified activation state

Deliver G14 of docs/MISSING_GUI_FUNCTIONALITY.md through the existing accounting
services. Add safe candidate views and deliberately reviewed recovery actions;
preserve working GUI, accounting calculations, authorization and CLI behavior.

Activation preflight independently verified2026-11-02: preceding215-a is FINAL
VERIFIED COMPLETE, PR371 merged2026-11-02T00:26:32Z, actual remote main
f2df0e82df8766740d9ac169ea56ffd7a3cb1f1e, tree
3d7ac2f653d73550aba5f852b2ef238a148ec670 equals accepted215 SELF
8aec4a7936b70ddd37e0bab224ea696c420e2b1c (sole parent IMPL
438f8b381005cf69f055c1a277f8809bc2d5e32e). All10finalPR checks and all9
actual-main checks/all3workflows SUCCESS (main CI41367166877,
CodeQL41367166861, Quality41367166379); final main job00:43:30Z; root terminal
verification2026-11-02T00:44:19.332031Z and authoritative timing already recorded
BEFORE this activation. Final-head root review5730948945 accepted material and
resolved10nonblocking advisories, with explicit immutable-report provenance
and disclosed process-deviation reconciliation; no further215repair required.
The wholeGUIgoal remains ACTIVE through219.

Previous215order21055bytes SHA37e8dfaa55a5d81f0dbc2d18cd4ea72f222655dbc27c4be205802012d514ce06
and215report33364bytes SHA9891a850801b47e8fd9d653fa6b7e33095e8bf2f811f9b981ac56005861ac5d3
remain immutable; before activation shared active was exact215-a. No216branch
locally/remotely, no216order/report/PR; sole open PR319 is unrelated Dependabot.
Ruleset23580289 active main deletion/non-fast-forward with NO bypass;19441572
and15649613 disabled; only published releasev0.1.0-rc.1(2026-05-01T21:33:27Z).
No release/tag/deployment/production/real-provider/mail authority is granted.

The shared coding checkout is clean at215SELF8aec4a79 on its existing215branch,
with ONLY protected untracked artifacts: CODEX-SESSIONS.md7881bytes
SHA5ae1d77c17a367e86ef725a8f9d25aba3464b24f22fba77fd2808377f8c7feda;
codex.sh492bytes SHA66eda80258f6a4f13b88a9fe2ad5a69b9e7df226a4e503f57b35b6c6f03e1247;
uv.lock405520bytes SHAd3d0e80db77da56e41795c619875ac14b5d25427d5169a7c9d2c8dee45b3b5b6.
HASH ONLY; never read/stage/modify these files. Preserve ignored.env/.codex,
local catalogs and unrelated worktrees. Root does not manipulate coding Git.
Fetch verified remote main and create the216branch yourself, preserving the
already-published root order/active bytes and unrelated local state.

Existing SAMECLI3308462 RIGHT%9 is natively refreshed in CURRENTworktree with
unchanged early-beta profile/qwen3.8-27b A100(Q8)/medium and startup governance
read. Sole canonical control waiter3319040, cwdSTRATEGIC,TMUX_PANE=%9,
wait_for_partner, confirmed healthy. Actual canonical FIFOs are
/home/janezp/codex-supervision/slaif-api-gateway/control.fifo inode4501469 and
response.fifo inode4501470 (both true FIFOs). A blocked builtin-read FIFO open
has no child or FIFO fd until a writer connects; do not repeat broad/proc/lsof
inventories or create another reader to interpret that normal state.
Canonical scripts/message.txt are unchanged; no helper/model/profile/effort
changes are permitted. Root has sole activation/merge authority under standing
human delegation; your execution starts only on exact controlOK.
Create exactly ONE PR from that verified main on oap/216-gui-accounting-operations.
Title: Add reviewed accounting recovery controls to the admin console.
Read the current repository AGENTS.md and OAP-COMMUNICATION-coding-agent.md,
docs/accounting.md, docs/security-model.md and the three reconciliation
runbooks; selected strategic background is
/home/janezp/codex-supervision/slaif-api-gateway/workorders/216-a-gui-accounting-operations-PROPOSAL.md
and GUI-PARITY-ROUND-PLAN.md beside it. Those proposals are background only;
THIS expanded order is the sole selected task.

The coder owns Git; root owns order/active filesystem bytes. Existing right
pane CLI only. No helper/nested agents or profile/model/effort changes.
No reset/clean/stash, amend of already-pushed commits, or force-push/force-with-lease,
including before PR creation. Correct pushed documentation with a NEW commit;
activated orders/reports retain identical bytes. Preserve unrelated local files.

## Four candidate views, four existing action families

Use an Operations/Accounting area for:
1. Expired pending reservations: list_expired_pending_reservations.
2. Unresolved external-tool fences: ExternalToolFenceService.list_unresolved_fences.
3. External-tool accounting holds: ExternalToolAccountingHoldService.list_holds.
4. Provider-completed/finalization-failed recovery: list_provider_completed_recovery_rows.

Safe exact identities, state/age, relevant current evidence and bounds; links
to existing key/usage detail. Views do not mutate or contact providers. The
fence view is READ ONLY: runtime ExternalToolFenceService.resolve is not an
administrator unblock primitive. Do not add a generic release/reset/unblock.

Expose these existing CLI reconciliation capabilities through dry run ->
review -> explicit confirmation/apply -> truthful result:
- one expired ordinary pending reservation;
- an explicit bounded selection of expired ordinary pending reservations;
- one external-tool hold (finalize-actual OR release-no-charge);
- one or an explicit bounded selection of provider-completed recovery rows.

Preserve CLI capabilities/defaults/output and the existing Core services and
strict schemas. Web code never imports/spawns CLI. No duplicated accounting
engine, ad hoc SQL settlement, provider evidence uploader or usage reset.

## Review, privileges, exact scope and atomicity

Existing authenticated admins may inspect; execution requires the authenticated
user's existing superadmin role, checked on the server. Explicit actor from
session, CSRF, target/action confirmation and nonblank bounded safe reason.
No browser actor/role/recipient/provider value grants authority. No general
RBAC redesign or deployment-wide revocation claims.

Use existing actor/session/purpose-bound expiring review primitives. A new
accounting review purpose is bounded (15 minutes) and carries the exact
selected IDs, action, validated proposed assertions, relevant source evidence
fingerprints and reason. A valid seal is not authorization or accounting truth.
Recheck everything on apply. Refuse tampering, wrong purpose/actor/session,
expiry, altered targets/assertions and changed relevant source facts safely.

Use explicit IDs, one action family and at most200 reviewed targets per
operation, with exact included/excluded identities/reasons. Never run a new
limit-based candidate scan at apply, never add newly matching/excluded rows.
The GUI's200 ceiling is deliberate; existing CLI positive limits stay unchanged.
Candidate methods have no offset contract. Provider-completed and hold
projections filter invalid/mismatched shapes AFTER source limit: a short
projected list does NOT prove no later candidates. State the cap, allow narrowing/exact lookup, and do not
invent totals/has_more/database-completeness from projected length.

All preview calls explicitly set dry_run=True (ordinary reconciliation
otherwise defaults False); hold previews explicitly use execute=False.
Preview writes no audit/ledger/counters, sends nothing and does not hold long
locks while awaiting human confirmation. Explain current observed balances
and distinguish proposed action from actual stored state.

Existing batch methods select fresh candidates and do not accept reviewed
source/IDs. Authorize ONLY the minimal backwards-compatible reviewed-target/
expected-source seam in shared services. Relevant evidence is reloaded and
checked AFTER existing canonical Core locks, BEFORE mutation. A FOR UPDATE
query can return cached identity-map objects; qualify freshness across cached
objects and a waited lock. Do not bind an entire key balance fingerprint;
unrelated ordinary traffic must not invalidate an otherwise valid review.

Selected batch execution is one transaction with deterministic target/lock
ordering consistent with Core; do not hold a key lock then acquire the next
selected row's prerequisite lock in arbitrary browser order. A late stale row,
validation or audit failure rolls back the whole selected mutation transaction.
An unknown commit acknowledgement is UNCONFIRMED, never a rollback promise.
Preserve Core counter arithmetic and eligibility checks. Distinguish excluded,
skipped, already resolved/refused, unchanged and actually settled outcomes.
Safe already-resolved409/no duplicate effects is acceptable; do not add a
receipt store just to make repeat return200. No partial/skipped success claim.

## Evidence and manual assertion semantics

Unknown final cost remains held and hosted concurrency remains fenced. Ordinary
expired reconciliation must refuse external-tool-fenced and provider-completed
needs_reconciliation rows; do not forgive them at zero cost.

Hold finalize-actual preserves the shared validation: explicit finite
nonnegative Decimal actual_cost_eur, nonnegative integer actual_total_tokens,
actual boolean success and nonblank reason at most500 CHARACTERS. Preserve
original validated reason and relevant safe operator audit. Display these
as manual authoritative operator assertions, with operator_reconciliation /
operator_asserted provenance, never provider-verified evidence. Do not silently
remove these existing CLI capabilities. Raw machine units in inputs; comma/
M-token presentation only in readouts and exact raw typed sort keys.

Release-no-charge requires its separate explicit no-charge confirmation and
forbids actual-cost/token/outcome fields under the shared validator. Never
default absent evidence to zero. The hold dry-run result shows CURRENT stored
facts: display proposed validated manual assertions separately in review.
Provider-completed recovery uses ONLY the authoritative stored evidence Core
accepts; no GUI actual-cost override on that path. Its current validator
requires positive final total tokens and actual cost; missing/nonpositive
facts refuse unchanged. This differs from the explicit nonnegative actuals
accepted for manual hold reconciliation; do not unify or relax those laws.
Missing/conflicting facts refuse without clearing a hold or duplicating accounting.

## Exact paths and ergonomic constraints

Relative app/slaif_gateway/:
- NEW api/admin_accounting_operations.py; main.py router composition only.
- NEW services/admin_accounting_operations.py and, only if necessary, a focused
  schemas/admin_accounting_operations.py for safe GUI plans/projections.
- services/reservation_reconciliation.py and external_tool_hold.py: directly
  necessary backwards-compatible reviewed-source/exact-target bridge only;
  external_tool_fence.py read projection reuse, no new generic resolve action.
- db/repositories/quota.py, usage.py, keys.py: minimal fresh canonical-lock /
  bounded exact selected read seam required by that bridge. No model changes.
- api/admin_review_intent.py: strict bounded new accounting purpose, existing
  HMAC primitives; unrelated purposes retain exact behavior.
- services/admin_record_choices.py, api/admin_record_choices.py and macro reuse
  ONLY if a missing reservation/ledger choice kind is necessary for actual
  existing-record input. Latest100+older search+selected hydration, minimal
  ID/state/time labels, no raw metadata/prose/credentials. Candidate checkbox
  selection is valid; no raw UUID-only field replacing a known-record picker.
- NEW web/templates/accounting_operations/ and operations/index.html navigation.
  api/admin.py only a directly necessary existing composition/navigation seam.
- cli/quota.py only if delegation is demonstrably necessary; preserve command
  defaults, output, schema and authorization. No unrelated CLI edits.
- Focused unit/PG/browser tests, directly affected existing tests, approved docs
  below and unchanged strategic OAP activation/report bytes.

No db/models.py, migrations, dependency/config/platform additions, adapter/
forwarding/request-policy/tool permissions/replay ownership or normal
accounting calculation changes. If a genuine Core boundary defect is found,
demonstrate it and report to root; do not bypass it in UI or redesign Core.

Use existing SLAIF shell/assets/fonts, link sorting, visible row numbers,
separate requests/tokens columns, numeric formatters and keyboard-focusable
scroll regions. Every new/touched entry/choice field gets an actual unique
control ID plus associated field-specific help: scope, units, blank/default,
consequences, examples. Use progressive views/review, clear blocked reasons,
finite selects/searchable known-record choices and useful no-JS recovery.

No full secrets, prompt/tool/response content, encrypted reasoning, provider
URLs/credentials, SMTP/diagnostic bodies or raw exception text in HTML, token,
logs, audits, downloads or OAP. Apply existing pure known-prefix/shape/current
incoming auth-alias protection before render/sign/audit. Keep ordinary safe
values faithful. Background lookups/exports must not rotate displayed CSRF;
real page/mutation checks remain authoritative. Login303 is not action success.

## Proportionate verification/setup

Reuse /tmp/slaif192-coding-venv, installed Chromium and existing fresh-owned
PostgreSQL fixtures. Verify exact owner/full resource IDs/loopback binding
and cleanup. NO ambient DB/password guesses, production data, real provider,
Codex, SMTP, package install or helper agent. Reuse unchanged accepted Core
accounting/CLI/concurrency evidence, not another complete local matrix.

Focused unit/ASGI: four read views/action families, strict manual/stored
provenance, explicit no-charge, raw numeric validation, source hashing,
review expiry/tamper/actor/session/purpose and auth/role/CSRF/reason/confirm
negatives. Valid auth+CSRF must reach intended guard. Safe fixed errors;
credential/content/replay canaries absent from render/log/audit/task output.

Owned PG with actual HTTP/session/CSRF: read/dry-run full-state preservation;
one expired settlement, selected batch, manual hold actual/no-charge, stored
provider-completed recovery; nonzero legal unrelated key/ledger/quota/policy
sentinels and full relevant mapped fields. Unknown cost stays held, fenced
ordinary release refuses, no duplicate settlement/counters/audit on repeat.
Exact reviewed IDs only, exclude newly matching rows, changed included-source
refusal, cached/waited-lock refresh, concurrent resolution/admission safety,
deterministic cross-key ordering, late audit rollback and commit-ack-loss
unconfirmed behavior at actual transaction seams. Controlled fault seams are
labelled. No fake persistence called native or empty-state proof called
accounting preservation.

Real Chromium/PG synthetic views and dry-run/review/apply/result through UI;
blocked/unknown-cost view without generic unblock, actual known-record
selection, keyboard/no-JS/help, desktop/narrow capture under /tmp/slaif216.
Root visually reviews BEFORE immutable handoff. Preserve working key lifecycle
and unchanged-form/background-read CSRF by accepted evidence or directly
affected regressions. Whole installed GUI/config/assets/identity gate remains
219; do not build or claim it here.

Exact new qualification paths:
- tests/unit/test_admin_accounting_operations_216.py;
- tests/integration/test_admin_accounting_operations_216_postgres.py;
- tests/browser/test_admin_accounting_operations_216.py.
Run each focused module with the qualified venv, ambient DATABASE_URL and
TEST_DATABASE_URL cleared, -q -p no:cacheprovider, one JUnit per layer under
/tmp/slaif216. Real PostgreSQL setup comes ONLY from the fresh-owned fixture.
Run directly affected shared/CLI unit consumers once:
tests/unit/test_reservation_reconciliation_service.py,
tests/unit/test_provider_completed_reconciliation_service.py,
tests/unit/test_external_tool_hold.py,
tests/unit/test_cli_quota_reconciliation.py,
tests/unit/test_cli_quota_reconciliation_safety.py,
tests/unit/test_provider_completed_reconciliation_cli.py;
include tests/unit/test_admin_record_choices.py only if that service changes.
Use tightly selected existing native reconciliation/hold cases if the changed
bridge requires them; reuse unchanged fence/concurrency/service evidence.
Run tests/unit/test_oap_governance.py on exact216order/active, scoped Ruff over
ALL changed Python files and docs/diff checks. No complete local accounting,
provider/Codex/CLI matrix or installed wholeGUI run here. Fixtures/documentation
fixes remain CURRENT_A; no extra immutable reports/evidence catalogs.

One current receipt per necessary layer; exact pytest exit status. Routine
fixture/docs corrections CURRENT A/same PR, new suffix only demonstrated
blocking defect after immutable handoff. Required OAP9 on exact order/active,
scoped Ruff/docs/diff plus directly affected consumers; rely on final-head CI
for broad regression. Skipped/pending/missing is never PASS.

## Documentation and immutable publication

Update G14 only in docs/MISSING_GUI_FUNCTIONALITY.md. Exact other allowed
documentation paths: docs/admin-usability.md, docs/accounting.md (only the
operator-workflow/shared-bridge contract if necessary; no changed arithmetic),
docs/security-model.md, docs/cli-reference.md, docs/upgrade-runbook.md,
docs/runbooks/stale-reservation-reconciliation.md,
docs/runbooks/provider-completed-reconciliation.md,
docs/runbooks/external-tool-hold-reconciliation.md, and the single incremental
docs/verification/gui-cli-parity.md plus docs/verification/README.md. State
GUI cap, privilege, manual-vs-stored provenance, observed-vs-proposed state,
unknown-cost holds, exact selections/atomicity, repeat/unconfirmed recovery,
no schema migration and honest synthetic/native/browser limitations. G15/G17
and219 remain open. No release/tag/deployment authority.

Commit/push unchanged root-authored order+active with implementation in one216
PR. Never merge/auto-merge. Draft report away from final filename; atomically
publish absent oap/reports/216-a-gui-accounting-operations.md via temp file,
flush/fsync/replace/directory fsync. Immutable report-only SELF has literal
IMPL sole parent and only report diff. Report exact commits/PR/tests/overlaps/
limitations/deviations. Verify remote bytes/head/topology then exact response
OK ONCE and ONE canonical coding control waiter. Root reviews all final-head
CI/review/material/visual gates, guarded merge, actual main3workflows/9checks/
tree and authoritative terminal timing before217 activation. Entire GUI goal
remains ACTIVE until final219 qualification and actual-main verification.
