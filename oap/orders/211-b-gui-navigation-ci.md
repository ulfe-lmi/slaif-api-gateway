# OAP Work Order — 211-b

PR mode: AMEND_EXISTING_PR
PR: 367
Base: existing PR head27082a43774d19fdd4b7ae4b9144316356d8157c
Branch: oap/211-gui-diagnostics-config
Title: Qualify the Operations navigation in the existing GUI design checks

## Objective, reason and verified state

Repair the demonstrated final-head browser CI blocker on the SAME211 PR367.
The new Operations navigation is intentional approvedG08/G16 behavior; two
legacy browser expectations still require14 links, while the real shell now
has15. Preserve the application and every substantive visual/keyboard/no-JS
assertion. This is a bounded test-oracle correction, not another feature round.

At 2026-11-01T09:38:56.264570+00:00, canonicalmain remains
f71f5799ee4f14ff5774f0e96775f1fd5f02d38e. Unique211 PR367 is OPEN/nondraft on
this branch, exacthead27082a43774d19fdd4b7ae4b9144316356d8157c (A SELF), parent
IMPLef41baecdcedd7d03274dba5548f5510a0dd5a1c. A report is immutable16722bytes,
SHA2561353cceaffb668f83d980455bc1215ba3efcb9536000c1ca9ed6208c85a2a89f;
A order27251bytes SHA2562436b3d48c880c0b1ae6c5f436235cbb121ea943ac0523ba0fc9514fdd59abeb.
Root independently verified remote order/active/report bytes, report-onlySELF
and firstparent. A material/security/privacy/accounting/native/browser/visual
review is accepted, but A finalCI is NOT accepted: Playwright job124809403688
ofCI41293439505 FAILED2026-11-01T09:36:22Z,2failed/70passed in242.95s.
Both failures are tests/browser/test_admin_slaif_design.py:
- test_design_default_theme_shell_fonts_navigation_and_tables, line395:
  assert nav.count()==14; actual15.
- test_design_no_javascript_navigation_usable, line548:
  assert page.locator('#admin-nav a').count()==14; actual15.
Root inspected source and completed-job log /tmp/slaif211/final-browser-job.log.
Other A final-head checks SUCCESS: unit/lint/migration, allthree analysis
checks plusCodeQL aggregate, E2E, Compose anddocumentation. PostgreSQL remains
IN_PROGRESS at activation, never a pass. Root A CIwatch46179 may still finish
and wake root for the OLD head; it is NOT a B gate. No coding merge/CI bypass.
Allthree COMMENTED review threads resolved after independent assessment:
accepted210-identical worker exception transport; pytest-used fixture import;
harmless unusedlocal_noop deferredinINERT219. No CHANGES_REQUESTED or auto-merge.
Ruleset23580289 remainsactive deletion/nonff/no bypass; sole releasev0.1.0-rc.1.

Root A response98556 is CLOSED exactOK; NEVER repoll or resignal A. One
canonical coding waiterPID2746025 is ready on the original controlFIFO.
Original trueFIFO inodes4501469/4501470 verified. Root publishes this complete
order and exactactive211-b in the SHARED worktree before ONE controlOK.
The detached waiter consumes control and wakes pane%9; do not open another
control reader at startup. Coding owns Git execution; root does not reset,
clean, stash, switch or stage codingGit. Commit activation bytes unchanged.

Human standing delegation covers this necessary same-PR continuation. Use
ONLY existing RIGHT pane%9 coding agent, same human model/profile/effort.
No helpers/nested sessions/merge/auto-merge/release/tag/deploy/provider/mail/
production. Entire GUI212–219 remains mandatory;212 draft is INERT, not active.
Read repository governance/coding protocol, this order, immutable A order/report,
relevant GUI contract and the TWO failing current browser cases. Reuse prior
architecture/component evidence; no full archive or repeated inventory.

## Requirements and allowed paths

1. In tests/browser/test_admin_slaif_design.py, update the two stale exact nav
   counts to15, and explicitly assert one correctly named Operations link to
   /admin/operations/ in BOTH the normal and no-JavaScript scenarios. Derive
   the intended accessible link from the accepted base template; do not accept
   any arbitrary extra link or weaken count to >=14/dynamic DOM self-count.
   Preserve ALL existing font-byte, theme/contrast, logo/branding, current-page,
   keyboard, responsive overflow, table and no-JS assertions and fixtures.
   Change no product/template/JS/CSS code and no fixture ownership/setup law.
2. Re-run ONLY those TWO complete existing browser cases locally with real
   Chromium and their existing qualified ownedPG fixture. This allows the
   downstream assertions previously blocked at nav-count to execute. No new
   tests mirroring counts, no entire local browser/native/CLI matrix. Reuse A
   unit173/35 and native8+overlap3/browser7 plus70other CIbrowserPASS evidence.
   Distinguish reused cases and overlapping rechecks, no count inflation.
3. Add a concise B addendum to SAME docs/verification/gui-cli-parity.md:
   A final-head CI genuinelyfailed on stale14-counts; B corrects only those
   oracles plus Operations identity, two focused cases pass if verified.
   No claim A was allgreen or product behavior repaired. Keep previous history.
   docs/verification/README.md only a short pointer if useful. No new document,
   inventories, fixture history appendix or unrelated unused-helper cleanup.
4. Run scoped Ruff on the touched test, git diff --check,9 OAP governance on
   exact B order/active and directly affected doc checker. No repeat unchanged
   diagnostics/config/accounting/provider/Codex suites. Required final-head CI
   will run normally and root reviews it; missing/pending is not passed.

Allowed repository changes ONLY: tests/browser/test_admin_slaif_design.py;
docs/verification/gui-cli-parity.md; optional docs/verification/README.md;
this B order/oap/active and ONE B report. Preserve ALL A orders/reports and
product bytes. Non-goals: application changes, accepting a different nav,
new infrastructure, schema, permission/acceptance, accounting/replay, settings,
profile/adapter/capture changes, review waiver, production/deploy/release.

## Setup, negative and privacy/accounting evidence

Use /tmp/slaif192-coding-venv, existingChromium and qualified imported
owned_pg_url fixture; receipts/screenshots syntheticonly under/tmp/slaif211.
No packages, helper agents, duplicated fixtures, ambientDB use, blanketpkill or
Dockerprune. Existing fixture verifies exact owner label/full ID/loopback/tmpfs
before use and removes only that resource. Record its existing _STATE metadata
via the established inline pytest-runner pattern if needed; no new fixture
framework. Verify owned cleanup. Preserve no-JS/authenticated scenarios and all
existing negative/layout assertions; root reuses A auth/CSRF/canary/transaction/
accounting proofs because no product boundary changes. No real credentials,
request bodies/provider calls/email. Do not print protectedfile contents.

Preserve untracked CODEX-SESSIONS.md SHA2565ae1d77c17a367e86ef725a8f9d25aba3464b24f22fba77fd2808377f8c7feda,
codex.sh SHA25666eda80258f6a4f13b88a9fe2ad5a69b9e7df226a4e503f57b35b6c6f03e1247,
uv.lock SHA256d3d0e80db77da56e41795c619875ac14b5d25427d5169a7c9d2c8dee45b3b5b6,
ignored.env/.codex/catalogs/worktrees and unrelated state; never commit them.
Actual paths remain /home/janezp/codex-work/slaif-api-gateway and strategic
/home/janezp/codex-supervision/slaif-api-gateway. Never rewrite message.txt.

## Acceptance and publication/handoff

Exact two browser cases pass on correctedB, all prior substantive guards remain,
Operations named/href asserted in both JS/noJS, only permitted paths differ,
A immutability/protectedhashes intact. B introduces no product change, schema
upgrade or new operator action; normal API/assets upgrade facts remain A.

Commit/push to EXISTING PR367 on the same branch; no newPR/forcepush/merge or
auto-merge. Update its body coherently for A+B with accurate per-head failure/
pass/pending facts and overlapping tests, never a copied wrongcasecount.
Write ONE immutable oap/reports/211-b-gui-navigation-ci.md with final literalIMPL,
exact tests/exit/results/proof limits, reusedA evidence and actualheadCI state;
include Documentation updated: <files>. Construct draft away from finalpath,
publish complete via reports-localtemporary+flush/fsync+os.replace+directory
fsync. Never append/revise a finalized report. Final report-onlySELF firstparent
must equal literalIMPL, ONLY B report diff. Independently verify remotePRhead=
SELF and exact order/active/report bytes before ONE responseOK(two bytes,noLF).
Then install ONE detached canonical wait-control-and-wake.sh with TMUX_PANE=%9,
verify actual script/PID, no adhoc reader/duplicates. Root reviews all finalhead
checks and A+B material, guardedmerges exactSELF, verifies actualmain3workflows/
all9checks/tree and terminaltiming BEFORE212. Do not selfactivate212 or stop
standing OAP delegation at a numeric boundary. Entire GUI goal remainsACTIVE.
