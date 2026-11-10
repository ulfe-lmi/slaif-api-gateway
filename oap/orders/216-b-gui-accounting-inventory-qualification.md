# OAP Work Order — 216-b

PR mode: AMEND_EXISTING_PR

Continue objective216 on SAME PR372, branch oap/216-gui-accounting-operations.
No new PR and no217 activation while216 remains unresolved. This is a bounded
qualification repair for demonstrated CI failures, not new GUI functionality.

## Objective, verified state and actual blocker

Verified2026-11-10: remote main remains
f2df0e82df8766740d9ac169ea56ffd7a3cb1f1e. Unique PR372 is OPEN/MERGEABLE,
no auto-merge, exact head216-a SELF4d83197ef5ee67f95a6505cb32184a9081e088d3,
sole parent IMPL95ca15d205523e4b7a5d9cdd794caa118e203eb6. Root verified
report-only diff, GitHub/local topology and remote immutable bytes. ReportA
16011bytes SHAce92dceed86143572eb1da77e8509e536d3654241f0d28a08ac60d3b6f19e3ef;
orderA18704bytes SHA7d5d9bb09acfb70357e071367889cbec1f496f341fd16677c8db5f7addd70f85.
Both remain byte-unchanged. Before activation active was exact216-a.

Final-head CI42730736624 unit job129547868912 FAILED at00:50:36Z:
2failed,7115passed,1skipped (the skip is NOT a pass). Exact blockers:
- tests/unit/test_admin_usability_inventory.py::test_every_admin_table_has_structural_ordinal_column
  expects40tables, actual46.
- tests/unit/test_admin_slaif_design.py::test_table_wrappers_are_labeled_and_focusable
  expects38wrappers, actual44.
The six added tables are expired, fences, holds, provider-completed, and TWO
review.html tables (reviewed rows and per-row outcomes). Update inventory
expectations for these actual additions while preserving every structural,
accessibility, sorting, empty-row and column assertion.

All other reported final-head checks are SUCCESS except PostgreSQL integration
which is STILL RUNNING at activation. Root watches the old immutable snapshot
in terminal25552, CI42730736624; do not poll root terminals, cancel or rerun it.
CodeQL runs42730736459/42730730821 succeeded. Ten analyzer advisories remain
for root assessment; they are not this repair's scope or an instruction to
clean unrelated code. Only other open PR319 is unrelated Dependabot.
Ruleset23580289 protect-main ACTIVE;19441572/15649613 disabled. Only published
releasev0.1.0-rc.1; no release/tag/deploy/production/provider/mail authority.

## Exact scope and non-goals

Primary paths ONLY:
- tests/unit/test_admin_usability_inventory.py;
- tests/unit/test_admin_slaif_design.py;
- this order, oap/active and the new matching immutable216-b report.
Optional minimal qualification note in the EXISTING216 section of
 docs/verification/gui-cli-parity.md; no new evidence catalog/document.

Change the stale expected counts to the verified46tables/44wrappers and add a
short explanation of the six G14 additions. Do not replace exact coverage with
>=, delete checks, change table discovery to ignore new pages, skip/xfail or
weaken data-sortable/first ordinal/leaf column/colspan/data-no-sort/accessible
wrapper/control/theme contracts. Do not redesign the inventory framework.
If reaching the existing structural assertions exposes an ACTUAL new-template
violation, minimally repair only the relevant
app/slaif_gateway/web/templates/accounting_operations/ markup, preserving
working forms/values/layout, and report the exact failed assertion. This
conditional markup allowance is not permission for aesthetic changes.

No application Python, CLI, DB/schema/migration, dependencies, adapters,
request acceptance, authorization, CSRF, secret protection, accounting math,
quotas, replay ownership, policy or provider permission change. No new store,
job platform, diagnostic mechanism or supporting infrastructure. Preserve all
working GUI and accepted visual style; no speculative analyzer cleanup.

## Reuse and precise evidence

Root accepted216-a unit43 (mocked), owned-PG20, current Chromium8 covering all
four action families/noJS/keyboard, consumer52 and choices+OAP84. Final visual
review was explicitly cleared on00:32:41 captures; same source/source-snapshot
limitations in immutableA report remain honest. Reuse unchanged evidence;
NO repeat of these modules just for a filename, documentation or inventory
constant. The earlier duplicate consumer52 execution is52unique, not104.

Root additionally verified the previously unexercised BEFORE_COMMIT fault at
SELF4d83197e using the EXISTING fresh-owned PostgreSQL16 fixture and current
HTTP/helper paths: fault hit; UI unconfirmed/NOTrollback; full relevant mapped
accounting state unchanged, no ledger/audit insertion, reservation pending;
exact owned container9fed1b63aa2c649233bfbe87bb41c3ba965883efd8e25513d8f0eec3af80c1cc
was owner-verified and removed. This is EXTRA root verification afterA report,
not part of its20-case receipt; do not rerun it or recast it as such.
A report's route-count shorthand says2applyPOSTs; actual source has3. Preserve
immutableA and qualify these points accurately in theB report/current proof
note; no new product work or retroactive report edits.

## Verification and publication dependency

Run exactly the TWO primary unit MODULES once with
/tmp/slaif216-qualification-venv/bin/python, ambient DATABASE_URL and
TEST_DATABASE_URL cleared, -q -p no:cacheprovider and one current JUnit under
/tmp/slaif216. Check TRUE pytest exit (no pipe masking). The current receipt
filename is a disposable label: reuse/cite/rename an existing valid receipt,
never rerun solely for its name. All applicable cases and complete structural
loops must pass, no weakened/removed/skipped coverage. Run OAP governance on
new order/active, scoped Ruff/compile for changed Python, diff/docs check.
No full local unit/integration/browser/CLI/provider matrix. If a conditional
markup repair is genuinely required, verify just its affected UI behavior;
unchanged backend evidence stays accepted.

PARALLEL WAIT: perform this known local repair while old PG CI finishes.
Do NOT push or create the immutableB report until root sends
ROOT_216A_CI_CLASSIFIED. This is the existing remaining-CI classification
dependency, not fresh human permission. Root will classify any additional
blocking old-PG failure within THIS continuation/samePR so routine fixture
corrections do not generate another round. Do not manufacture completion
from an observation timeout, pending check, missing log or skipped case.

Then commit the repair as NEW commit(s), push SAME branch/PR372 and update PR
description around final G14 behavior and qualification. Never amend a pushed
commit, force-push, create another PR, merge or enable auto-merge. Publish ONE
new immutable216-b report in a final report-only SELF commit with SOLE parent
its literal implementation head. Include exact fields
Implementation head SHA: <literal 40-hex>
Report publication commit: SELF
and exact PR/branch, changed paths, real commands/exits/counts/receipt timing,
source-snapshot reuse, blocked/not-run limits, no-source-change boundaries and
publication topology. Final-head checks pending are not passes. Verify remote
PR head/bytes, then send response FIFO exactly two bytes OK ONCE. Root owns
all final CI/review/merge/main verification and future objective activation.

## Setup, immutability and live handoff

Same existing coding CLI3308462 in RIGHT%9, unchanged early-beta qwen3.8-27b
A100(Q8)/medium. No helper/nested agents, model/profile/effort/config changes.
Native /compact is allowed solely for context maintenance. Current sole
canonical control waiter3357654 was verified wait_for_partner,
cwd/home/janezp/codex-supervision/slaif-api-gateway, TMUX_PANE=%9. True FIFOs:
control.fifo inode4501469, response.fifo inode4501470 under that strategic
root. A blocked builtin FIFO open without an fd/child is healthy: do not
repeat /proc inventories or create another reader.

Root publishes COMPLETE order + exact active216-b in shared repo filesystem
before ONE controlOK; coder owns Git execution and commits these root bytes
unchanged. Do not reset/clean/stash/switch state to replace root's activation,
rewrite message.txt or require fresh human approval for ordinary continuation.
Protected untracked CODEX-SESSIONS.md, codex.sh and uv.lock are HASH ONLY;
never read/stage/modify. Preserve ignored.env/.codex/catalogs/worktrees.
No installs or ambient DB/container use; no DB/browser resources are needed
for this test-only repair. Root response20174 is CLOSED; root probe59510 and
log-fetch71477 also CLOSED, never repoll/resignal216-a. Old-root CI25552 is
LIVE until root classifies its terminal result; thisB gets one NEW canonical
response wait after activation. Do not signal response before verifiedB
handoff. Maintain objective216/PR372 until root terminal resolution; the
whole GUI goal remains ACTIVE through final219 installed qualification.
