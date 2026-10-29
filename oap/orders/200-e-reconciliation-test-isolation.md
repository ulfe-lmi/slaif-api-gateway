# OAP Work Order — 200-e

PR mode: AMEND_EXISTING_PR
Objective: 200 — isolate held-fence reconciliation tests from unrelated expired fixtures
PR: #356 — https://github.com/ulfe-lmi/slaif-api-gateway/pull/356
Branch: oap/200-replay-reference-maintenance
Base: main at 4c265bc3c9668a66bb1643915d442fb8c411ff11
Current report-only head: f38d92dee1815f7a6bad6c87360ae8dc1277e6ca
Literal implementation parent: ce4a1ec5eaf9ef3ac43791e5a538d8aed4d3b9f6

## Business reason / verified state

Finish the SAME replay-maintenance objective/uniquePR; do not activate201 while200unresolved. Dproductfix is independentlyverified; current remaining gate is a demonstrated oldintegrationTESTisolation failure exposed by a longerCIrun, plus one factualreportcorrection. FullCLIgoal201–205/all11installed-executableDoDremain unproven. No new functional feature/schema/authority.

Reconciled2026-10-29UTC: sole dresponse40173 CLOSEDexactRESPONSE_OK_EXACT/actualexit0. UniquePR356OPEN/MERGEABLE/branchcorrect; main4c265bcunchanged/onlyotheropenPR319/mainruleset23580289active/onlyreleasev0.1.0-rc.1. dSELFf38d92dee1815f7a6bad6c87360ae8dc1277e6ca firstparentliteralimplce4a1ec5eaf9ef3ac43791e5a538d8aed4d3b9f6, whoseparentiscSELF032a3af. SELFreport-only/tree6ba21e5ded471b2469ab42ea6ceddf8890ca5d6a verified; reportSHAf55d18a3c51579856c04e0e638edceec850a7189aaac547c8fda9b506884bb9a/orderSHAbe4c09ac223691bb861cb4a7379baf38d3e1372406ff2c1fb1806b915b444d78. Protecteduntrackedfilesunchanged/onlythoseuntracked/trackedtreeclean. dnewSELFchecksstillpartlypending, no merge/201.

RootparsedGENUINEd74units(53service+21CLI),182affected(INCLUDES74),40govdisjoint,16ownedPG ALLPASS0fail/error/skip; initialdPG15PASS1test-assertionFAIL(dateserializedstringvsdatetime) wasfixedbyparsingstoredISOtimestampswithoutweakeningnumeric/range/rollbackoracles, thenactual16PASS. Root12actualservice+strictparser/fakeRepo scenariosPASSatFINALd service71699b94e1b23be603b6d11f67ce1541b135dd98eda3e96e597e4f8397da8b78/CLI0521d578b7aed6ff2672d1d24e6f87493f173a42d2245f430205cd9cd4b38510; wholepredecisionlock/clock/eligibilityprefix ASTunchanged; schema/Repo/inventory unchanged. dfunctionalfixverified; remainingtestisolation+reportfactualcorrectionbelow. Receipt200-d-independent-handoff-review.json; realcounterexample200-independent-ci-reconciliation-isolation-repro.json. Currentsolecodingcontrolwaiter3911790pane%9; rootwillONEsignalaftercompleteeorder/exactactiveexists.

Actual cSELF032a3af CI40789904468/job123172757105: PostgreSQLintegration **2failed,448passed,9skipped**; failedtests EXACTLY tests/integration/test_external_tool_fence_postgres.py::test_held_fence_blocks_and_never_auto_releases and tests/integration/test_external_tool_hold_postgres.py::test_hold_survives_engine_restart_expiry_and_ordinary_reconciliation. Both invokeGLOBAL expired-reservation batchreconciliation while testing onlytheirOWN heldreservation. They can encounter another test's expired ordinary reservation with ledger.response_metadata.needs_reconciliation=True. Corecorrectly raises ReconciliationInvariantError("Provider completed before accounting finalization failed; do not release as zero-cost stale reservation"). NEVER weaken this guard, release held money/tokens, or changeproductionbatchsemantics to make tests pass.

Root proved the exact dependency in a NEWownedPG16: /tmp/slaif200-root/test_ci_reconciliation_isolation_probe.py (onepytestharness PASS/exit0; terminal56770CLOSED), strategic receipt review-artifacts/cli-feature-round/200-independent-ci-reconciliation-isolation-repro.json. Both actualoldtestfunctions PASS onfreshDB; afteradding ONEunrelatedexpiredprovider-completed/needs_reconciliation reservation, BOTH failwiththeexactCIguard. Its ledger/reservation/keyreservedcounters remainunchanged. FixedUnixDocker/newuniqueownerlabel/loopback/tmpfs/identityBEFOREmigrate/exactIDcleanup, zeroowncontainersremaining; no foreignDB/provider/contact. This is successful DEFECTreproduction, NOT a claimoldtests passwithforeigncandidate. Source/log /tmp/slaif200-root/c-ci-pg-failure.log.

## Exact minimal repair — TESTS ONLY

Make these TWOtestbatches operate explicitly on their own knownreservationUUID, with realPostgreSQL-backed candidate selection. Use a tiny LOCALtestrepository/subclass/selector that fetches the actual ownedrow with the same pending/expired predicates and boundedselection, or equivalenttest-local dependencyinjection. Keep inherited REAL get-for-update/mutation/core service methods; the productionReservationReconciliationService andrepositories mustremain BYTEUNCHANGED. Do not replace the core with a fake or return[] toavoid the guard. Avoidglobalmonkeypatches, conftest/sharedfixtureframeworks, new DB infrastructure or broader refactors.

Retain/strengthen everyoriginaloracle: owncandidate observed (preferexactcandidate_count/skipped_count1 for scopedbatch), stillheld/fenced and unauthenticatable, ownreservationstillpending, unchangedreservedcost/tokens/requests, no zero-costledger/release/unintendedaudit. The tests are about ownheld-fence durability; unrelatedrequests mustnotenter their testbatch. The genericglobalcandidatequery/ordinaryprovider-completedfail-closedlaw remains unchanged and its existingcoverage mustnotbe removed, skipped, xfailed or suppressed.

Demonstrate the repaired TWOactualtests on a freshownedPG AND with an unrelatedexpiredprovider-completed/needs_reconciliation row present, deterministically (no minutes-long sleeps, expirytimebombs or retries-until-green). Root's smallownedfixture/probe canbe reused/adapted in /tmp for verification; no newcommittedharness required. In the foreign-row case, eachheldtest mustPASSwhile ALLforeignpoison key/ledger/reservation/counters remainunchanged; explicitlyinvoking the ordinarysingle-reservationreconcile on thatforeignrow must STILL raise the existingReconciliationInvariantError/no changes. This proves isolation ratherthan hiding an accountingregression. Keep exactownership/cleanup evidence and distinguish actualpytestnodes from a wrapperthatcalls actualtestfunctions; do not inflatecounts.

## Exact allowed paths / non-goals

ONLY tests/integration/test_external_tool_fence_postgres.py and tests/integration/test_external_tool_hold_postgres.py (targetedtwofunctions andtinyprivate test-local candidate selector ifneeded); docs/verification/2026-10-28-cli-replay-maintenance.md APPENDeaddendum; newimmutableeorder/exactactive/report. All product app/, other tests, migrations/schema, config, dependencies/workflows, security/accounting/holds/fences/reconciliation decisions, docscontracts/CLIbehavior, acceptedreplayimplementation andinventorychecker BYTEUNCHANGED fromd. Noproductionchange, no broaderfixture/engine cleanup or SQLeditor. Exactextra pathrequired => reportbeforeedit. Olda/b/c/dreports/orders andverificationprefiximmutable; rootstrategicfiles/protecteduntracked/ignoredsettings/catalog untouched.

## Factual documentation correction — use THIS exact table

The immutable dreport's attempted ccountcorrection copied dcounts and makes the impossibleclaim53+21=65. DoNOTeditoldreports/text. Append a clear ecorrection using these actualrecordedJUnitcounts (root200-c-unit-per-file-count-correction.json andtheactualXMLs), not estimates/current-filecollection:

| Recorded run | Service maintenance file | CLI replay file | Other unchanged files | Actual total |
|---|---:|---:|---|---:|
| c-unit-new.xml | 45 | 20 | none | 65 |
| c-unit-affected.xml | 45 | 20 | replay_service24 + replay_limits57 + cli_codex27 | 173 |
| d-unit-new.xml | 53 | 21 | none | 74 |
| d-unit-affected.xml | 53 | 21 | replay_service24 + replay_limits57 + cli_codex27 | 182 |

Both c/dgovernance runs40=inventory16+governance9+drift15; cownedPG15, downedPG16. Allthesefocusedruns had0fail/error/skip. The c/dper-filewordingerrors didNOTchange genuine65/173/74/182 totals or outcomes. State that d's correctionwasitselfwrong and this is its correction; preservehistory. Etest-isolation evidence hasitsowncounts anddoesnotreplace c/dproof. No completeAPI/provider/mail/clientqualification follows.

## Verification economy / boundaries

Focused ownedPG proof of bothchangedtests plus deterministicforeign-rowregression/corefail-closedcontrol, genuinePG source/read/writes/counters comparison, appropriate collection/help/tests asneeded for edits. Run gov/inventory/drift40, Ruff/diff/docschecker. No needrerun182unit/16replayPG suites orrootTWOclock/membershipprobes for aTESTONLYisolation change; verify allproduct hashes unchangedfromd. FinalSELF CIALLchecks remainbroad mandatorygate. IfactualcurrentCIshows additionaldistinctfailures outsideeallowlist, reportexactscope/evidence ratherthanchangingcoretoforcegreen.

ExistingPython3.12 /tmp/slaif192-coding-venv; unsetambientDATABASE_URL/TEST_DATABASE_URL beforeownedsetup. Temporaryverification maysetTEST_DATABASE_URL ONLYto its freshlycreatedidentity-verifiedownedPG16 endpoint, never an existingprovided/production/foreignDB. FixedUnixDocker/newuniqueownedlabel/loopback/tmpfs/inspectBEFOREmigrate/exactIDlabelcleanup. No foreigncontainers/worktrees/blanketcleanup/apt/HPC, no realprovider/client/model/SMTP/Redis/SSH/protectedcredentials/production/deploy/tag/release. SameRIGHTpane%9/profileearly-beta/qwen3.8-27bA100Q8medium/settings, nohelpers/subagents/model/effortchange/relaunch.

## Publication/report duties

Amend samePR356/branch/history. Commit unchangedstrategicorder/exactactive200-e andonlyallowedfiles. Report literal40heximplSHA+Report publication commit: SELF, exactscope/unchangedproducthashes/orderhash, actualCIcontext/reproduction/layers/testcommands/exits/JUnitfail/error/skip/overlaps/limitations. Includeexact Documentation updated: docs/verification/2026-10-28-cli-replay-maintenance.md line. KeepCI PENDING honestuntilactualfinalSELFchecks. Finalreport-onlySELF firstparentliteralimpl/onlynewreportdiff/pusheduniquePRhead/orderbytesverified BEFOREtworesponseOKbytesONCE, thenONEcontrolwaiter inexistingpane. Agentnevermerge/automerge/selfactivate. Rootindependentreviewchecksallsource/fixture/proof/security/privacy/accounting/docs/reviews/ALLfinalheadchecks, guardedexactheadmerge andactualmainchecks/timing BEFORE201. FullCLIgoal205stilloutstanding; no releaseclaim.
