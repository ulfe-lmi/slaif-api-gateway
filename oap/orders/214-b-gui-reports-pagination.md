# OAP Work Order — 214-b

PR mode: AMEND_EXISTING_PR

Continuation within unresolved objective214 / SAME PR370. Never activate215
while214PR370 remains unresolved. Do not rewrite214-a order/report.

## Objective, demonstrated defect and current state

Repair the demonstrated blocking final-head browser regression on the SAME
PR370 without changing accepted GUI behavior. On immutable214-a SELF
b5f7a80f7e0084141d66d1193d6d9e5550486a29 (IMPL
5547b93b3037d144e3566eb60e8024f0eac90bc3, base
7ede8cc54b72f2c8e0e81913082dfae0c97d2173), browser job124957397249
of run41343115263 failed19:48:32Z: 4 failed,91passed. ALLfour are the
parameterizations of tests/browser/test_admin_visual_screenshots.py::
test_keys_list_visual, atline226: old selector .table-toolbar .rows-shown
now legitimately matches BOTH the original12rows-shown toolbar and the new
Rows1–12 pagination range. Playwright strict locator rejects two matches.
This is a selector/fixture compatibility defect; no loss of visual semantics
or product failure is demonstrated by this exception.

Verified2026-11-01T20:00:05.170660+00:00: unique214PR370 OPEN / mergeable true / noauto-merge,
remotehead b5f7a80f7e0084141d66d1193d6d9e5550486a29, verifiedmain/base
7ede8cc54b72f2c8e0e81913082dfae0c97d2173 unchanged; onlyotheropenPR319
Dependabot remainsoutofscope. Activebeforepublication214-a; sharedtracked
worktreeclean atSELF, only3protecteduntrackedfiles, allhashes unchanged.
Order214-a16866bytes SHAad7245bd5401e1b9b33983289a62bc2729539ae17cbfe2bae10869efd584ff9b;
report214-a26238bytes SHA55347a9a2cc18b27fbd7842a742b0f7d46b690c4ce760417c6ed46e16f103507.
Exactremoteorder/active/reportbytes +SELFtopology verified. Activeprotection
23580289, other19441572/15649613disabled; no bypass. Releaseonlyv0.1.0-rc.1
published2026-05-01T21:33:27Z; no newrelease/tag/deploy. Fourautomatedtest-only
advisories reviewed/resolved byroot; rootmaterialCOMMENT5729905332 atSELF
acceptedsubjectCI. Eightof10checksSUCCESS, browserFAIL asabove, PGintegration
job124957397463 STILLINPROGRESS in41343115263. Root18503soleCIwatch LIVE.
ExactlyONEcanonicalcodingwaiter3117389 bashwait-control-and-wake.sh, target
%9, cwd/home/janezp/codex-supervision/slaif-api-gateway, existingCLI3308462/profile/effortunchanged.
TruecontrolFIFOinode4501469/response4501470 verified, no newreader.

PARALLEL WAIT ECONOMY: perform the known selector fix and focusedfourcases
while existing214-a PG CI finishes. Do NOT push/construct the immutable
214-breport until root sends ROOT_214A_CI_CLASSIFIED. This is a root CI
classification gate, not fresh human permission. Local work does not change
the running GitHubsnapshot. If oldPGreveals another actualblocker, rootwill
classifyandkeepits bounded repair in this order/samePR. Do not cancel/rerun
oldCI or poll rootterminal. No secondrepairround for routinefixtures.
Root214-a response9574 is CLOSED EXACTOK, neverrepoll/resignal214-a. Root
214-a finalCIwatch18503 is LIVE pendingPG; root consumes its eventual result
once, then closes it permanently. Do not poll it fromcoding-side. Immutable214-a order/report
remain byte-for-byte unchanged, already remoteverified. Preserve protected
CODEX-SESSIONS.md/codex.sh/uv.lock, operator.env/.codex/catalogs/worktrees.
Coding ownsGit, root ownsworkorder/active. No reset/clean/stash/forcepush,
helperagents/nestedCodex/model/profile/effort/configchange. Existingright
%9CLIonly. No merge/auto-merge, release/tag/deploy/production/provider/mail.

## Exact repair and non-goals

Change ONLY tests/browser/test_admin_visual_screenshots.py for this actual
selector ambiguity: target the existing stable #keys-rows-shown element,
assert it is unique, and preserve the literal12rows-shown assertion and ALL
other viewport/layout/typing/chips/sorting/ordinals/customlimit expectations.
Do not use .first(), remove an assertion, suppress strictness, skip/xfail,
weaken geometry, replace real browser/PG with stubs, or change product
templates/classes/pagination merely to hide the extra legitimate range.
If later assertions expose a genuine blocking defect, diagnose its actual
requirements before a minimal in-order repair; report before expanding
product paths. Do not preemptively clean analyzer nits: root reviewed and
resolved the four test-only advisories on214-a with rationale.

No application/DBschema/service/accounting/auth/privacy/CLI/adapter/replay
change. Reuse rootaccepted214-a 41unit/20nativePG/8browser component and
material/visual evidence, including real no-JS caprefusal->form->narrow
recovery, lockrefresh/rollback/accounting/fullknowncost behavior. This
repair is NOT permission for newfeatures or another wholeGUIinventory.

## Observable acceptance and proportionate verification

Run ONE focused real Chromium/ownedPG command covering ALLfour failed
viewportparameterizations:
  /tmp/slaif192-coding-venv/bin/python -m pytest \
    tests/browser/test_admin_visual_screenshots.py::test_keys_list_visual \
    -m playwright -q --junitxml=/tmp/slaif214/browser-214b-1.xml
Use existing qualified ownership/fullID/loopback/tmpfs fixture and current
installed Chromium. Clear ambient DATABASE_URL/TEST_DATABASE_URL from the
testprocess, never seed/touch ambientDB. No packages/newinfrastructure.
Allfour mustactuallyrun/pass; skipisnotpass. Preserve product shell/fonts/
controls/sort links/rowordinals/counts/keyboard/grow-down/overflow/custom
limits; existing test asserts these directly. Reuse accepted214-acaptures
unless this run exposes a visual failure; no newvisualmatrix or unrelated
full local suite. Then exactcurrentorder/active OAP9, scopedRuff ofchanged
test, docs/diffhygiene. FinalGitHubCIqualifiesbroadregressions once newSELF
is published; do not repeat unchanged214-a suites locally.

## Documentation, publication and immutable handoff

Allowedpaths: tests/browser/test_admin_visual_screenshots.py; minimal
214section of docs/verification/gui-cli-parity.md to record preciseactual
CIselectorfailure/fourviewportrepair +localfocusedreceipt (not duplicate
evidencecatalog); unchangedroot-authored oap/orders/214-b-gui-reports-pagination.md
and active; NEW oap/reports/214-b-gui-reports-pagination.md. Do not rewrite
214-a immutableorder/report. No product/featurestatus/upgrade rewrite needed
for this test-only correction.

Commit/push on EXISTING oap/214-gui-reports-pagination and amend PR370,
not a newPR. Readcurrentcontracts and exactactiveorder, no newbaseline/
inventory. Complete draftreport awayfromfinalpath; atomictemp+flush/fsync+
os.replace+dirfsync into ABSENT finalreportpath. One report-onlySELF whose
soleparent isliteralIMPL; solefilediffnew214-breport; remoteverify exact
PRhead/topology/bytes. Preserveoldreporthistory. Report exacttests/counts/
hashes/CIstatus/limits and nounfoundedfinal-code/fullGUIclaim. ONEresponseOK
to canonicalrootreader, then ONEcanonicalcodingwaiter in persistentexec
terminal(right%9). Do not shell-backgroundandlosewaiter, modifyhelper,
openextrareader, pollrootterminal or resignalcompletedrounds. Root final
headCI/review/materialgates -> guardedmerge -> actualmain3workflows/all9
checks/tree +authoritativetiming BEFORE215. WholeGUIgoalACTIVEthrough219.
